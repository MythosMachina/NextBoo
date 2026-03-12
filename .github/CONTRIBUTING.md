# Contributing

## Before You Start

- open an issue for substantial changes before coding
- keep changes scoped and reviewable
- avoid mixing refactors with behavior changes
- do not include runtime data, local secrets, or generated media

## Local Setup

1. Copy `.env.example` to `.env`.
2. Start the stack:

```bash
docker compose up --build
```

3. Create first admin access if needed:

```bash
./scripts/bootstrap-admin-invite.sh
```

## Development Rules

- preserve the current project structure under `backend/`, `frontend/`, and `worker/`
- prefer focused commits and small pull requests
- update docs when behavior or operator workflows change
- if you touch auth, queueing, or moderation flows, include validation notes

## Pull Requests

Each pull request should include:

- what changed
- why it changed
- how it was tested
- any migration or operator impact

Use the pull request template in this repository.
