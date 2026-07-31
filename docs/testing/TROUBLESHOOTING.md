# Troubleshooting

## The browser page or API docs do not open

For Docker, make sure Docker Desktop is running and check the service state:

~~~powershell
docker compose ps
docker compose logs app
~~~

The browser demo is on port 8001 only when Docker Compose is running. A local Python run uses port 8000 by default.

## The health endpoint is not ok

Docker starts PostgreSQL before the application. Wait for the database health check, then refresh the endpoint. For a local Python run, apply migrations before starting Uvicorn:

~~~powershell
python -m alembic upgrade head
~~~

## I cannot select a file in the browser demo

That is expected. The current browser screen accepts pasted text only. Use Swagger at /docs for .txt, .md, .pdf, or .docx file uploads.

## My file upload returns 422

Check these common causes:

- The file extension is unsupported.
- A .txt or .md file is not UTF-8 encoded.
- The PDF is scanned, encrypted, malformed, or has no extractable text.
- The document exceeds a safety limit.
- You tried to upload a second version with the same version label.

Use the included Markdown fixtures first. They are known-good inputs.

## My comparison returns 422

The two version IDs must:

- be different;
- belong to the same document;
- produce no more than 100 changed sections with the default limits.

Create the baseline document first, then add the revised file through the versions endpoint for that same document ID.

## I expected Ollama output but see heuristic:fallback

ClauseLens keeps the deterministic report even if the local model cannot respond. Confirm Ollama is running, the configured model was downloaded, and the base URL is reachable:

~~~powershell
ollama list
Invoke-RestMethod http://localhost:11434/api/tags
~~~

For Docker, the app uses host.docker.internal to reach Ollama on Windows. Make a real comparison and inspect each assessment provider field. The health endpoint reports configuration, not a successful inference.

## I want a completely clean local reset

There is no document-deletion endpoint in v1. With Docker, this command deletes the local ClauseLens PostgreSQL volume and all stored comparison data:

~~~powershell
docker compose down -v
~~~

With local SQLite, stop the app and delete only the clauselens.db file if you want to remove the local database. Do not delete a database that contains comparisons you want to keep.
