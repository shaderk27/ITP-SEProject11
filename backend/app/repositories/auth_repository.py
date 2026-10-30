from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence
from sqlalchemy import select, delete, update
import json
from sqlalchemy.orm import Session, joinedload
from app.models.config import Lab, LabGroup, LabIcAssignment
from app.models.auth import User, Role, PasswordResetToken


class AuthRepository:
    def get_user_by_email(self, db: Session, email: str) -> Optional[User]:
        return (
            db.query(User)
            .options(
                joinedload(User.role),
                joinedload(User.lab_group),
                joinedload(User.lab_assignments).joinedload(LabIcAssignment.lab),
            )
            .filter(User.email == email)
            .first()
        )

    def get_user_by_id(self, db: Session, user_id: int) -> Optional[User]:
        return (
            db.execute(
                select(User)
                .options(
                    joinedload(User.role),
                    joinedload(User.lab_group),
                    joinedload(User.lab_assignments).joinedload(LabIcAssignment.lab),
                )
                .where(User.user_id == user_id)
            )
            .unique()
            .scalar_one_or_none()
        )

    def create_user(
        self,
        db: Session,
        role_id: int,
        full_name: str,
        email: str,
        password_hash: str,
        staff_id: Optional[str] = None,
        lab_group_id: Optional[int] = None,
        lab_ids: Optional[List[int]] = None,
        primary_lab_id: Optional[int] = None,
        creator_admin_id: Optional[int] = None,
        commit: bool = True,
    ) -> User:
        """Create and persist a new user in the system with lab assignments.

        With commit=False the rows are only flushed, so the caller can add more
        changes (e.g. lab assignments) and commit or roll back everything at once.
        """
        db_user = User(
            role_id=role_id,
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            staff_id=staff_id,
            lab_group_id=lab_group_id,
            is_active=True,
        )
        db.add(db_user)
        db.flush()  # populates db_user.user_id

        # Handle lab assignments via lab_ic_assignments
        assigned_labs = set(lab_ids or [])
        if primary_lab_id:
            assigned_labs.add(primary_lab_id)

        for lid in assigned_labs:
            is_primary = lid == primary_lab_id
            assignment = LabIcAssignment(
                lab_id=lid,
                user_id=db_user.user_id,
                is_primary=is_primary,
                assigned_by=creator_admin_id,
            )
            db.add(assignment)

        if commit:
            db.commit()
            db.refresh(db_user)
        else:
            db.flush()
        return db_user

    def set_user_activation_status(
        self,
        db: Session,
        user_id: int,
        is_active: bool,
        acting_admin_id: Optional[int] = None,
    ) -> Optional[User]:
        """Activate or deactivate a user and log the action to audit_logs."""
        user = self.get_user_by_id(db, user_id)
        if not user or user.is_active == is_active:
            return user

        old_status = user.is_active
        user.is_active = is_active

        # Audit log insertion according to project specification
        action_type = "user_reactivated" if is_active else "user_deactivated"
        from sqlalchemy import text

        audit_stmt = text(
            """
            INSERT INTO audit_logs (user_id, action_type, entity_name, record_id, old_value, new_value)
            VALUES (:admin_id, :action_type, 'users', :record_id, :old_val, :new_val)
            """
        )
        db.execute(
            audit_stmt,
            {
                "admin_id": acting_admin_id,
                "action_type": action_type,
                "record_id": str(user_id),
                "old_val": json.dumps({"is_active": old_status}),
                "new_val": json.dumps({"is_active": is_active}),
            },
        )

        db.commit()
        db.refresh(user)
        return user

    def assign_lab_to_user(
        self,
        db: Session,
        user_id: int,
        lab_id: int,
        is_primary: Optional[bool] = None,
        assigned_by: Optional[int] = None,
        commit: bool = True,
    ) -> None:
        """Assign a user to a lab via lab_ic_assignments.

        If is_primary is None, the user becomes primary only when the lab
        has no other primary IC; otherwise they are added as secondary.
        """
        existing = (
            db.query(LabIcAssignment)
            .filter(
                LabIcAssignment.lab_id == lab_id,
                LabIcAssignment.user_id == user_id,
            )
            .first()
        )

        if is_primary is None:
            # Is there a primary IC other than this user?
            other_primary_exists = (
                db.query(LabIcAssignment.user_id)
                .filter(
                    LabIcAssignment.lab_id == lab_id,
                    LabIcAssignment.is_primary.is_(True),
                    LabIcAssignment.user_id != user_id,
                )
                .first()
                is not None
            )
            if other_primary_exists:
                # Keep an existing primary status if this user already holds it
                is_primary = bool(existing.is_primary) if existing else False
            else:
                is_primary = True

        if is_primary:
            # Demote any other primary IC for this lab
            db.query(LabIcAssignment).filter(
                LabIcAssignment.lab_id == lab_id,
                LabIcAssignment.is_primary.is_(True),
                LabIcAssignment.user_id != user_id,
            ).update({"is_primary": False})

        if existing:
            existing.is_primary = is_primary
            existing.assigned_by = assigned_by
        else:
            db.add(
                LabIcAssignment(
                    lab_id=lab_id,
                    user_id=user_id,
                    is_primary=is_primary,
                    assigned_by=assigned_by,
                )
            )

        if commit:
            db.commit()

    def assign_labgroup_to_user(
        self, db: Session, user_id: int, lab_group_id: int, commit: bool = True
    ) -> Optional[User]:
        """Update the lab_group_id column on the User model."""
        stmt = (
            update(User)
            .where(User.user_id == user_id)
            .values(lab_group_id=lab_group_id)
        )
        db.execute(stmt)

        if commit:
            db.commit()

        # Return updated user model instance
        return self.get_user_by_id(db, user_id)

    def unassign_lab_from_user(
        self, db: Session, user_id: int, lab_id: int, commit: bool = True
    ) -> None:
        """Remove a lab IC assignment for a specific user and lab."""
        db.query(LabIcAssignment).filter(
            LabIcAssignment.lab_id == lab_id, LabIcAssignment.user_id == user_id
        ).delete()
        if commit:
            db.commit()

    def update_password_hash(
        self, db: Session, user_id: int, new_password_hash: str
    ) -> Optional[User]:
        user = self.get_user_by_id(db, user_id)
        if user:
            user.password_hash = new_password_hash
            db.commit()
            db.refresh(user)
        return user

    def get_role_by_id(self, db: Session, role_id: int) -> Optional[Role]:
        return db.query(Role).filter(Role.role_id == role_id).first()

    def get_all_roles(self, db: Session) -> Sequence[Role]:
        return db.query(Role).all()

    def get_all_users(self, db: Session) -> Sequence[User]:
        return (
            db.query(User)
            .options(
                joinedload(User.role),
                joinedload(User.lab_group),
                joinedload(User.lab_assignments).joinedload(LabIcAssignment.lab),
            )
            .order_by(User.user_id)
            .all()
        )

    def get_users_by_role(self, db: Session, role_name: str) -> List[User]:
        """Fetch all users assigned to a given role name."""
        stmt = (
            select(User)
            .join(Role, User.role_id == Role.role_id)
            .where(Role.role_name.ilike(role_name))
        )
        return list(db.execute(stmt).unique().scalars().all())

    def get_lab_by_id(
        self, db: Session, lab_id: int, for_update: bool = False
    ) -> Optional[Lab]:
        """Fetch a lab. With for_update=True the lab row is locked until the
        transaction ends, so concurrent primary-IC decisions for it are serialised.
        """
        query = db.query(Lab).filter(Lab.lab_id == lab_id)
        if for_update:
            query = query.with_for_update(of=Lab)
        return query.first()

    def get_lab_group_by_id(self, db: Session, lab_group_id: int) -> Optional[LabGroup]:
        return db.query(LabGroup).filter(LabGroup.lab_group_id == lab_group_id).first()

    def get_user_by_role_and_lab_group(
        self, db: Session, role_id: int, lab_group_id: int
    ) -> Optional[User]:
        return (
            db.query(User)
            .filter(User.role_id == role_id, User.lab_group_id == lab_group_id)
            .filter(User.is_active.is_(True))
            .first()
        )

    def get_assignments(self, db: Session) -> list[dict]:
        """Return current lab group and lab IC assignments for admin UIs."""
        rows = (
            db.query(
                User.user_id,
                User.full_name,
                User.email,
                User.role_id,
                User.lab_group_id,
                LabIcAssignment.lab_id,
                LabIcAssignment.is_primary,
                Role.role_name,
            )
            .join(Role, Role.role_id == User.role_id)
            .outerjoin(LabIcAssignment, LabIcAssignment.user_id == User.user_id)
            .filter(
                (User.lab_group_id.isnot(None))
                | (LabIcAssignment.assignment_id.isnot(None))
            )
            .filter(User.is_active.is_(True))
            .all()
        )
        return [
            {
                "user_id": row.user_id,
                "full_name": row.full_name,
                "email": row.email,
                "role_id": row.role_id,
                "role_name": row.role_name,
                "lab_group_id": row.lab_group_id,
                "lab_id": row.lab_id,
                "is_primary": row.is_primary,
            }
            for row in rows
        ]

    def invalidate_reset_tokens(self, db: Session, user_id: int) -> None:
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user_id, ~PasswordResetToken.used
        ).update({"used": True})

    def create_reset_token(
        self, db: Session, user_id: int, hashed_temp_password: str
    ) -> PasswordResetToken:
        token = PasswordResetToken(
            user_id=user_id,
            temp_password=hashed_temp_password,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(token)
        db.commit()
        return token

    def mark_token_used(self, db: Session, token: PasswordResetToken) -> None:
        token.used = True
        db.commit()

    def delete_reset_tokens_by_user(self, db: Session, user_id: int) -> None:
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user_id
        ).delete()
        db.commit()

    def update_user_password(
        self, db: Session, user_id: int, hashed_password: str
    ) -> None:
        db.query(User).filter(User.user_id == user_id).update(
            {"password_hash": hashed_password}
        )
        db.commit()

    def get_active_reset_token_by_user(
        self, db: Session, user_id: int
    ) -> Optional[PasswordResetToken]:
        """Fetch the latest active (non-expired and non-used) reset token for a user."""
        stmt = (
            select(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                ~PasswordResetToken.used,  # noqa: E712
                # If you have an expiration column:
                PasswordResetToken.expires_at > datetime.now(timezone.utc),
            )
            .order_by(PasswordResetToken.created_at.desc())
        )
        return db.execute(stmt).scalars().first()

    def get_last_reset_token_by_user(
        self, db: Session, user_id: int
    ) -> Optional[PasswordResetToken]:
        """Fetch the most recent reset token generated for a user."""
        stmt = (
            select(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id)
            .order_by(PasswordResetToken.created_at.desc())
        )
        return db.execute(stmt).scalars().first()

    def unassign_all_labs_from_user(
        self, db: Session, user_id: int, commit: bool = True
    ) -> None:
        """Remove all lab assignments for a specific user from lab_ic_assignments."""
        stmt = delete(LabIcAssignment).where(LabIcAssignment.user_id == user_id)
        db.execute(stmt)
        if commit:
            db.commit()
