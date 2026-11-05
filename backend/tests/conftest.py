import os
import tempfile
from pathlib import Path
import pytest

TEST_ROOT = Path(tempfile.mkdtemp(prefix="nile-test-"))
os.environ["DATABASE_URL"] = "sqlite:///" + str(TEST_ROOT / "test.db")
os.environ["DATA_DIR"] = str(TEST_ROOT)
os.environ["APP_API_KEY"] = "test-only-access-token-0123456789"
os.environ["POLLING_ENABLED"] = "false"
for variable in ["CAMERA_TEST_URL", "TOMTOM_API_KEY", "AISSTREAM_API_KEY", "OPENAQ_API_KEY"]:
    os.environ[variable] = ""

from app.db import Base, Session, engine  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    with TestClient(app) as c:
        c.headers["Authorization"] = "Bearer " + os.environ["APP_API_KEY"]
        yield c


@pytest.fixture
def db(client):
    with Session() as session:
        yield session
