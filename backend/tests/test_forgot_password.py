# tests/test_forgot_password.py
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from app.services.auth_service import AuthService
from app.models.auth import User, PasswordResetToken
from app.repositories.auth_repository import AuthRepository


def make_service():
    service = AuthService.__new__(AuthService)
    repo = MagicMock(spec=AuthRepository)
    repo.configure_mock(
        **{
            "get_user_by_email.return_value": None,
            "get_user_by_id.return_value": None,
            "get_active_reset_token_by_user.return_value": None,
        }
    )
    service.repository = repo
    service.db = MagicMock()
    return service


def make_user(is_active=True, password_hash="$2b$12$hashedpassword"):
    user = MagicMock(spec=User)
    user.user_id = 1
    user.email = "test@sit.edu.sg"
    user.full_name = "Test User"
    user.is_active = is_active
    user.password_hash = password_hash
    return user


def make_token(used=False, expires_at=None):
    token = MagicMock(spec=PasswordResetToken)
    token.used = used
    token.expires_at = expires_at or (datetime.now(timezone.utc) + timedelta(hours=1))
    token.temp_password = "$2b$12$hashedtemppassword"
    return token


# ── 1. Unknown email returns generic success ──────────────────────────────────


def test_forgot_password_unknown_email_returns_silently():
    """Unknown email should not raise — avoids leaking whether email exists."""
    service = make_service()
    service.repository.get_user_by_email.return_value = None

    # Should not raise, should not call create_reset_token
    service.forgot_password("unknown@sit.edu.sg")

    service.repository.create_reset_token.assert_not_called()


# ── 2. Inactive user does not receive reset ───────────────────────────────────


def test_forgot_password_inactive_user_does_not_send():
    """Inactive users should be silently skipped — no token created, no email sent."""
    service = make_service()
    service.repository.get_user_by_email.return_value = make_user(is_active=False)

    with patch.object(service, "_send_temp_password_email") as mock_send:
        service.forgot_password("test@sit.edu.sg")
        mock_send.assert_not_called()

    service.repository.create_reset_token.assert_not_called()


# ── 3. Reset creates temp token ───────────────────────────────────────────────


def test_forgot_password_active_user_creates_token_and_sends_email():
    """Active user should have old tokens invalidated, new token created, email sent."""
    service = make_service()
    service.repository.get_user_by_email.return_value = make_user()

    with patch.object(service, "_send_temp_password_email") as mock_send:
        service.forgot_password("test@sit.edu.sg")

        service.repository.invalidate_reset_tokens.assert_called_once_with(
            service.db, 1
        )
        service.repository.create_reset_token.assert_called_once()
        mock_send.assert_called_once()

        # Verify the email was sent to the right address
        call_args = mock_send.call_args[0]
        assert call_args[0] == "test@sit.edu.sg"


# ── 4. Temp password expiry works ─────────────────────────────────────────────


def test_login_rejects_expired_temp_password():
    """An expired temp password token should not allow login."""
    import bcrypt

    service = make_service()

    temp_password = "TempPass1"
    hashed = bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt()).decode()

    user = make_user(password_hash="$2b$12$differenthash")
    service.repository.get_user_by_email.return_value = user

    expired_token = make_token(
        used=False,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # already expired
    )
    expired_token.temp_password = hashed
    service.repository.get_active_reset_token_by_user.return_value = (
        None  # expired = not returned
    )

    response_mock = MagicMock()
    with pytest.raises(HTTPException) as exc:
        service.login("test@sit.edu.sg", temp_password, response_mock)

    assert exc.value.status_code == 401


# ── 5. Successful reset updates password and clears tokens ────────────────────


def test_reset_password_updates_hash_and_clears_tokens():
    """Correct current password should update hash and delete all reset tokens."""
    import bcrypt

    service = make_service()

    current_password = "OldPass123"
    new_password = "NewPass456"
    hashed_current = bcrypt.hashpw(current_password.encode(), bcrypt.gensalt()).decode()

    user = make_user(password_hash=hashed_current)
    service.repository.get_user_by_id.return_value = user

    service.reset_password(1, current_password, new_password)

    service.repository.update_user_password.assert_called_once()
    call_args = service.repository.update_user_password.call_args[0]
    assert call_args[1] == 1  # user_id
    new_hash = call_args[2]
    assert bcrypt.checkpw(new_password.encode(), new_hash.encode())

    service.repository.delete_reset_tokens_by_user.assert_called_once_with(
        service.db, 1
    )


def test_reset_password_rejects_wrong_current_password():
    """Wrong current password with no active token should raise 400."""
    import bcrypt

    service = make_service()

    hashed = bcrypt.hashpw("CorrectPass1".encode(), bcrypt.gensalt()).decode()
    user = make_user(password_hash=hashed)
    service.repository.get_user_by_id.return_value = user
    service.repository.get_active_reset_token_by_user.return_value = None

    with pytest.raises(HTTPException) as exc:
        service.reset_password(1, "WrongPass99", "NewPass456")

    assert exc.value.status_code == 400
    service.repository.update_user_password.assert_not_called()
    service.repository.delete_reset_tokens_by_user.assert_not_called()
