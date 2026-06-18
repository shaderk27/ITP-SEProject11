# backend/app/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# IMPORTANT: Update this string with your actual local pgAdmin credentials!
# Format: postgresql://<username>:<password>@localhost:5432/<database_name>
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:<PASSWORD>@localhost:5432/budget_system"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()