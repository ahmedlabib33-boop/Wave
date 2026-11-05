from pathlib import Path
from alembic import command
from alembic.config import Config


def migrate():
    configuration = Path("alembic.ini").resolve()
    if not configuration.is_file():
        raise RuntimeError("Start from the project root: alembic.ini is required")
    command.upgrade(Config(str(configuration)), "head")


if __name__ == "__main__":
    migrate()
