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
    service.repository.get_last_reset_token_by_user.return_value = None

    with pytest.raises(HTTPException) as exc:
        service.reset_password(1, "WrongPass99", "NewPass456")

    assert exc.value.status_code == 400
    service.repository.update_user_password.assert_not_called()
    service.repository.delete_reset_tokens_by_user.assert_not_called()


# ── 6. Temp password login returns must_reset_password flag ──────────────────


def test_login_with_temp_password_sets_must_reset_flag():
    """Logging in with a temp password should return must_reset_password: True."""
    import bcrypt

    service = make_service()

    temp_password = "TempPass1"
    hashed_temp = bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt()).decode()

    user = make_user(password_hash="$2b$12$normalhashedpassword")
    user.role = MagicMock()
    user.role.role_name = "labic"
    user.lab_group_id = None
    user.lab_id = 1
    user.lab = MagicMock()
    user.lab.lab_code = "E2-02-02"
    user.staff_id = "TEST-001"
    service.repository.get_user_by_email.return_value = user

    active_token = make_token()
    active_token.temp_password = hashed_temp
    service.repository.get_active_reset_token_by_user.return_value = active_token

    response_mock = MagicMock()

    with patch.object(service, "_create_access_token", return_value="mocked.jwt.token"):
        result = service.login("test@sit.edu.sg", temp_password, response_mock)

    assert result["user"]["must_reset_password"] is True
    service.repository.mark_token_used.assert_called_once_with(service.db, active_token)


# ── 7. Normal login does not set must_reset_password ─────────────────────────


def test_login_with_normal_password_does_not_set_must_reset_flag():
    """Logging in with a normal password should return must_reset_password: False."""
    import bcrypt

    service = make_service()

    password = "NormalPass1"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    user = make_user(password_hash=hashed)
    user.role = MagicMock()
    user.role.role_name = "admin"
    user.lab_group_id = None
    user.lab_id = None
    user.lab = None
    user.lab_group = None
    user.staff_id = "ADMIN-001"
    service.repository.get_user_by_email.return_value = user

    response_mock = MagicMock()

    with patch.object(service, "_create_access_token", return_value="mocked.jwt.token"):
        result = service.login("test@sit.edu.sg", password, response_mock)

    assert result["user"]["must_reset_password"] is False


# ── 8. Reset with temp password updates real password_hash ───────────────────


def test_reset_with_temp_password_updates_real_hash():
    """When no current_password provided but active token exists, reset should succeed."""
    import bcrypt

    service = make_service()

    new_password = "BrandNew123"
    user = make_user(password_hash="$2b$12$someoldhash")
    service.repository.get_user_by_id.return_value = user

    active_token = make_token()
    service.repository.get_last_reset_token_by_user.return_value = active_token

    service.reset_password(1, None, new_password)

    service.repository.update_user_password.assert_called_once()
    call_args = service.repository.update_user_password.call_args[0]
    new_hash = call_args[2]
    assert bcrypt.checkpw(new_password.encode(), new_hash.encode())


# ── 9. Reset clears temp tokens ───────────────────────────────────────────────


def test_reset_password_deletes_all_reset_tokens():
    """After a successful reset, all temp tokens for the user should be deleted."""
    import bcrypt

    service = make_service()

    current_password = "CurrentPass1"
    hashed = bcrypt.hashpw(current_password.encode(), bcrypt.gensalt()).decode()
    user = make_user(password_hash=hashed)
    service.repository.get_user_by_id.return_value = user

    service.reset_password(1, current_password, "NewPass456")

    service.repository.delete_reset_tokens_by_user.assert_called_once_with(
        service.db, 1
    )


# ── 10. Expired temp password cannot log in ───────────────────────────────────


def test_login_rejects_expired_temp_password_explicitly():
    """Expired token should not be returned by repository, so login must fail."""
    import bcrypt

    service = make_service()

    temp_password = "ExpiredTemp1"
    user = make_user(password_hash="$2b$12$differenthash")
    user.role = MagicMock()
    service.repository.get_user_by_email.return_value = user

    # Repository returns None for expired tokens (filtered by expires_at in query)
    service.repository.get_active_reset_token_by_user.return_value = None

    response_mock = MagicMock()
    with pytest.raises(HTTPException) as exc:
        service.login("test@sit.edu.sg", temp_password, response_mock)

    assert exc.value.status_code == 401
    service.repository.mark_token_used.assert_not_called()


# ── 11. Inactive user cannot log in ───────────────────────────────────────────


def test_login_rejects_inactive_user():
    """Inactive users should receive a 403 regardless of password correctness."""
    service = make_service()
    service.repository.get_user_by_email.return_value = make_user(is_active=False)

    response_mock = MagicMock()
    with pytest.raises(HTTPException) as exc:
        service.login("test@sit.edu.sg", "AnyPassword1", response_mock)

    assert exc.value.status_code == 403


# ── 12. Inactive user is rejected by get_current_user ────────────────────────


def test_get_current_user_rejects_inactive_user():
    """get_current_user should raise 401 if the resolved user is inactive."""
    import jwt as pyjwt

    service = make_service()

    inactive_user = make_user(is_active=False)
    service.repository.get_user_by_id.return_value = inactive_user

    # Build a valid token pointing to user_id=1
    token = pyjwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "a" * 64,
        algorithm="HS256",
    )

    with patch("app.services.auth_service.SECRET_KEY", "a" * 64):
        with pytest.raises(HTTPException) as exc:
            service.get_current_user(token)

    assert exc.value.status_code in (401, 403)


# ── 13. Expired JWT token is rejected by get_current_user ────────────────────


def test_get_current_user_rejects_expired_token():
    """An expired JWT should raise 401."""
    import jwt as pyjwt

    service = make_service()

    token = pyjwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        "a" * 64,
        algorithm="HS256",
    )

    with patch("app.services.auth_service.SECRET_KEY", "a" * 64):
        with pytest.raises(HTTPException) as exc:
            service.get_current_user(token)

    assert exc.value.status_code == 401


# ── 14. Missing token is rejected by get_current_user ────────────────────────


def test_get_current_user_rejects_missing_token():
    """No token at all should raise 401."""
    service = make_service()

    with pytest.raises(HTTPException) as exc:
        service.get_current_user(None)

    assert exc.value.status_code == 401
