from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from alembic import command
from alembic.config import Config
from app.config import Settings
from app.main import create_app


def test_fresh_alembic_database_serves_the_api() -> None:
    runtime_dir = Path("test-runtime") / uuid4().hex
    runtime_dir.mkdir(parents=True, exist_ok=False)
    database_url = f"sqlite:///{runtime_dir / 'migrated.db'}"
    project_root = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(project_root / "alembic.ini"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_config, "head")
    settings = Settings(
        database_url=database_url,
        upload_dir=runtime_dir / "uploads",
        max_upload_bytes=5_242_880,
        max_extracted_chars=500_000,
        max_sections_per_version=250,
        max_changed_sections=100,
        max_assessment_calls=10,
        llm_provider="heuristic",
        openai_api_key=None,
        openai_model="unused",
        llm_timeout_seconds=1.0,
    )
    app = create_app(database_url, settings=settings)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        response = client.post(
            "/api/v1/documents",
            json={"title": "Migrated document", "version_label": "v1", "content": "1. Scope\nReady."},
        )
        assert response.status_code == 201
