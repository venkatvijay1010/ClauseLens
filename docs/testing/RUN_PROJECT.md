# Run ClauseLens

## Before you start

Choose one path:

- Docker is the easiest way to run the complete application with PostgreSQL.
- Local Python is useful when you want to debug the backend. It defaults to a local SQLite database.

The default configuration uses the free heuristic provider. You do not need an OpenAI key, an Ollama installation, or a downloaded model to run the testing kit.

## Option A: Docker

Requirements:

- Docker Desktop is installed and running.
- Docker Compose is available.

From the repository root:

~~~powershell
Set-Location D:\Dev\clauselens
Copy-Item .env.example .env
docker compose up --build
~~~

The first start can take several minutes because Docker downloads the PostgreSQL image and installs Python packages. Leave that terminal running.

Open these addresses:

- Browser demo: http://localhost:8001
- API documentation and file upload controls: http://localhost:8001/docs
- Health check: http://localhost:8001/health

The health response should include status: ok and assessment_provider: heuristic.

To stop the app while keeping your local comparison data:

~~~powershell
docker compose down
~~~

To remove the local PostgreSQL data as well, run the following command only when you intentionally want a clean reset. It deletes the ClauseLens Docker volume:

~~~powershell
docker compose down -v
~~~

## Option B: local Python

Requirements:

- Python 3.11 or later.
- A terminal opened in the repository root.

~~~powershell
Set-Location D:\Dev\clauselens
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
python -m alembic upgrade head
uvicorn app.main:app --reload --env-file .env
~~~

Open:

- Browser demo: http://localhost:8000
- API documentation: http://localhost:8000/docs
- Health check: http://localhost:8000/health

The local path creates a SQLite database named clauselens.db unless DATABASE_URL is set in your environment.

## Optional: use local Ollama

Only do this after the heuristic flow works. Install Ollama, download the default model, and verify that it is available:

~~~powershell
ollama run gemma3
Invoke-RestMethod http://localhost:11434/api/tags
~~~

Then set these values in .env and restart ClauseLens:

~~~text
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma3
~~~

For Docker, leave OLLAMA_DOCKER_BASE_URL set to http://host.docker.internal:11434. A successful health endpoint only proves that the Ollama adapter is configured. Run a real comparison and inspect the returned provider field to confirm that the model itself is available. If it is not, ClauseLens returns a labelled heuristic fallback instead of losing the comparison.

## Verify the codebase itself

Run these commands from the repository root:

~~~powershell
python -m ruff check .
python -m pytest -p no:cacheprovider
python scripts/run_evaluation.py
~~~

The test suite should pass. The benchmark uses synthetic cases and should report 16 cases, 84 labelled changes, and 1.0 for its detection, alignment, severity, citation, and structured-output metrics. Processing-time values vary by machine.
