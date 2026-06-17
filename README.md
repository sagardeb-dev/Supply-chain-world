# supply-chain-pomdp

This repository contains a FastAPI backend and a static frontend for the supply-chain POMDP benchmark.

## What runs where

- backend/ contains the Python app, world engine, oracles, and tests.
- frontend/ contains a static browser UI served by the backend.
- uv only manages the Python side. The frontend has no package.json or Node-based dependency install step today.

## Prerequisites

- Python 3.12+
- uv
- A browser

## Quick start

From the repo root:

    cd backend
    uv sync
    uv run uvicorn src.api.app:app --host 0.0.0.0 --port 9000

Open:

    http://localhost:9000

The backend serves the frontend on the same origin, so you do not start a separate frontend server.

## Development

Run the backend in reload mode:

    cd backend
    uv run uvicorn src.api.app:app --reload --host 0.0.0.0 --port 9000

Run the regression suite:

    cd backend
    uv run pytest test_world.py -q

Run the benchmark/oracle summary:

    cd backend
    uv run python report_oracle.py

## Frontend dependency resolution

There is no frontend package manager in this repo right now. The frontend loads its only external runtime dependency, three, from an import map in frontend/index.html:

- three
- three/addons/

Those URLs point to a CDN at runtime, so uv does not resolve frontend dependencies. If we later add npm-managed frontend code, that would need its own package.json and install step; it would not be handled by uv.

## Repository layout

    backend/   Python app, world engine, oracles, tests, pyproject.toml
    frontend/  Static JS/CSS/UI served by FastAPI
