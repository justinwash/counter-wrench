#!/bin/sh
# Bring the database up to date, then serve. Each step is idempotent: migrations apply once,
# the seed syncs the catalog to the YAML files, and ingestion re-embeds only changed chunks.
set -e
python -m counterwrench.db.migrate
python -m counterwrench.db.seed
python -m counterwrench.rag.ingest
exec uvicorn counterwrench.api.app:app --host 0.0.0.0 --port 8000
