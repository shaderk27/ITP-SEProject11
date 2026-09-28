from pathlib import Path

from dotenv import load_dotenv


def load_environment() -> None:
    root_dir = Path(__file__).resolve().parents[2]
    backend_dir = Path(__file__).resolve().parents[1]

    load_dotenv(root_dir / ".env")
    load_dotenv(backend_dir / ".env", override=True)
