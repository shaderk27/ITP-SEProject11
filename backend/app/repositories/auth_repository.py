from typing import List, Optional, Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from app.models.auth import User, Role


class AuthRepository:
    def get_user_by_email(self, db: Session, email: str) -> Optional[User]:
        return (
            db.query(User)
            .options(joinedload(User.lab_group), joinedload(User.lab))
            .filter(User.email == email)
            .first()
        )

    def get_user_by_id(self, db: Session, user_id: int) -> Optional[User]:
        return db.execute(
            select(User)
            .options(
                joinedload(User.role), joinedload(User.lab_group), joinedload(User.lab)
            )
            .where(User.user_id == user_id)
        ).scalar_one_or_none()

    def get_user_by_staff_id(self, db: Session, staff_id: str) -> Optional[User]:
        """Fetch a user by their unique institutional staff identifier."""
        return db.query(User).filter(User.staff_id == staff_id).first()

    def create_user(
        self,
        db: Session,
        role_id: int,
        full_name: str,
        email: str,
        password_hash: str,
        staff_id: Optional[str] = None,
        lab_group_id: Optional[int] = None,
        lab_id: Optional[int] = None,
    ) -> User:
        """Create and persist a new user in the system."""
        db_user = User(
            role_id=role_id,
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            staff_id=staff_id,
            lab_group_id=lab_group_id,
            lab_id=lab_id,
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    def update_password_hash(
        self, db: Session, user_id: int, new_password_hash: str
    ) -> Optional[User]:
        """Update a user's password hash.

        The updated_at field will automatically refresh via SQLAlchemy/DB triggers.
        """
        user = self.get_user_by_id(db, user_id)
        if user:
            user.password_hash = new_password_hash
            db.commit()
            db.refresh(user)
        return user

    def get_role_by_id(self, db: Session, role_id: int) -> Optional[Role]:
        """Fetch a role record by its primary key ID."""
        return db.query(Role).filter(Role.role_id == role_id).first()

    def get_role_by_name(self, db: Session, role_name: str) -> Optional[Role]:
        """Fetch a role by its unique name string (e.g., 'admin', 'teamlead', 'labic')."""
        return db.query(Role).filter(Role.role_name == role_name).first()

    def get_all_roles(self, db: Session) -> Sequence[Role]:
        """Retrieve all defined roles in the system."""
        return db.query(Role).all()

    def get_all_users(self, db: Session) -> Sequence[User]:
        """Retrieve all users with role and scope relationships."""
        return (
            db.query(User)
            .options(
                joinedload(User.role), joinedload(User.lab_group), joinedload(User.lab)
            )
            .order_by(User.user_id)
            .all()
        )
    def get_users_by_role_id(
        self, db: Session, role_id: int
    ) -> List[User]:
        """Fetch all users assigned to a given role."""
        return (
            db.query(User)
            .filter(User.role_id == role_id)
            .all()
        )

    def get_user_by_role_and_lab_group(
        self, db: Session, role_id: int, lab_group_id: int
    ) -> Optional[User]:
        """Fetch a user assigned to a role/lab-group pair."""
        return (
            db.query(User)
            .filter(User.role_id == role_id, User.lab_group_id == lab_group_id)
            .first()
        )

    def get_user_by_role_and_lab(
        self, db: Session, role_id: int, lab_id: int
    ) -> Optional[User]:
        """Fetch a user assigned to a role/lab pair."""
        return (
            db.query(User)
            .filter(User.role_id == role_id, User.lab_id == lab_id)
            .first()
        )

    def get_assignments(self, db: Session) -> list[dict]:
        """Return current lab group/lab role assignments for admin validation UIs."""
        rows = (
            db.query(
                User.user_id,
                User.full_name,
                User.email,
                User.role_id,
                User.lab_group_id,
                User.lab_id,
                Role.role_name,
            )
            .join(Role, Role.role_id == User.role_id)
            .filter((User.lab_group_id.isnot(None)) | (User.lab_id.isnot(None)))
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
            }
            for row in rows
        ]
