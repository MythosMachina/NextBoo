# NextBoo

**Like Booru. Reimagined.**

A modern AI-powered image index with automatic tagging, faceted search, and a scalable architecture.

## Overview

NextBoo is a self-hosted booru-style image board built for curated archives, AI-assisted tagging, moderation workflows, and long-term growth. It combines a classic image-board browsing model with a modern service split:

- `Next.js` frontend
- `FastAPI` backend
- dedicated worker containers for media processing
- `PostgreSQL` for metadata
- `Redis` for queue coordination

The platform is designed for real tagging and moderation workflows, not a mock gallery shell.

## Core Features

- AI-powered ingest pipeline for images, GIF, WebM and animated WebP
- automatic thumbnails and media derivatives
- automatic system tags such as `image` and `animated`
- tag browser with namespace-aware sections
- search with include, exclude and rating filters
- persistent browse filters and view counts
- four-stage rating model:
  - `G` = General
  - `S` = Sensitive
  - `Q` = Questionable
  - `X` = Explicit
- moderation queue with reporting, review and hard delete
- admin tools for user management, upload access, strikes and rating rules
- invite-only registration with social-gate enforcement
- account-level content preferences and tag blacklist
- bulk upload flow with processing status
- planned horizontal worker scaling for higher ingest throughput
- Docker-first deployment

## Architecture

Services in the default stack:

- `frontend`: NextBoo web UI
- `backend`: FastAPI API under `/api/v1`
- `worker`: ingest and retag worker using Camie Tagger
- `postgres`: metadata database
- `redis`: queue and coordination service

## Repository Layout

```text
backend/   FastAPI application and API models
frontend/  Next.js application
worker/    media processing and tagging workers
infra/     deployment-related assets
gallery/   local runtime storage root for development
```

## Quick Start

1. Copy `.env.example` to `.env`.
2. Adjust credentials, ports and storage settings as needed.
3. Start the stack:

```bash
docker compose up --build
```

4. Create first admin access:

```bash
./scripts/bootstrap-admin-invite.sh
```

5. Redeem the printed invite code at:

- Frontend invite page: `http://localhost:13000/invite`

6. Open:

- Frontend: `http://localhost:13000`
- Backend health: `http://localhost:18000/api/v1/health`

## Storage Model

All host-mounted runtime data is controlled through `GALLERY_ROOT`.

Default:

```bash
GALLERY_ROOT=./gallery
```

This keeps runtime data relative to the checked-out repository root.

Mounted runtime paths below `GALLERY_ROOT`:

```text
queue/
processing/
processing_failed/
content/
content_thumbs/
imports/
models/
database/
```

### Recommended Layout

If you want to keep code and runtime data in a dedicated app root, use your own parent directory and clone the repository there.

Example:

```bash
cd /NextBoo
git clone <your-repo-url> app
cd app
cp .env.example .env
```

With the default `GALLERY_ROOT=./gallery`, runtime data stays inside that chosen app root.

## Configuration

Main settings live in `.env`.

Important variables:

- `FRONTEND_PORT`
- `API_PORT`
- `JWT_SECRET`
- `POSTGRES_*`
- `REDIS_*`
- `GALLERY_ROOT`
- `PUBLIC_API_BASE_URL`
- `CORS_ORIGINS`

See `./.env.example` for the full baseline.

## Admin Bootstrap and Recovery

NextBoo does not create a default `admin/admin` account.

Use:

- `./scripts/bootstrap-admin-invite.sh`
  - creates the first admin invite only when no active admin exists
- `./scripts/rescue-admin-access.sh`
  - creates an emergency admin invite with explicit confirmation

Both scripts are intended to be run locally on the host where Docker is running.

## Media and Tagging Pipeline

The worker pipeline supports:

- static images
- animated GIF
- WebM
- animated WebP

Static media is processed directly. Animated and video media keep their original format, while extracted frames are used for tagging and thumbnail generation.

Current tagging state:

- `Camie Tagger`
  - default ingest and retag provider
  - broader namespace coverage including general, character, copyright, artist, meta and richer rating output

The admin panel includes a full-library `Prune All Tags and Retag` action for Camie-based maintenance runs.

Planned next step for throughput:

- multiple ingest workers with scaler-style horizontal expansion based on queue pressure

## Ratings and Visibility

NextBoo currently uses four rating levels:

- `G` / `general`
- `S` / `sensitive`
- `Q` / `questionable`
- `X` / `explicit`

Typical visibility rules:

- guests: `general` only
- members: `general` and `sensitive`
- members with `Q` enabled: `questionable`
- members with explicit opt-in: `explicit`
- staff: unrestricted for moderation purposes

## Moderation and Accounts

Built-in administration includes:

- moderation queue and report handling
- post editing and hard delete
- tag correction on individual posts
- rating override rules based on tags
- user administration
- upload permission requests
- invite management and invite history
- strike system with social responsibility chain

Account features include:

- content preferences
- explicit opt-in
- questionable opt-out
- personal tag blacklist
- invite management
- upload access request flow
- upload ownership area
- password change

## Search Model

Search supports:

- include tags: `tag_name`
- exclude tags: `-tag_name`
- rating filter: `rating:general`
- sort order: `sort:recent`

The UI also exposes quick filters for:

- ratings
- media type
- page size

## Deployment Notes

The stack is designed to run cleanly in Docker on a single host with host-mounted persistent storage.

For a clean deployment target:

- choose a dedicated app root such as `/NextBoo`
- clone the repository there
- keep runtime storage inside or adjacent to that root via `GALLERY_ROOT`
- configure domain, reverse proxy and secrets outside the repository as needed

## Current State

This repository contains a live, working application stack, not just a scaffold. The codebase includes:

- running frontend and backend
- real worker-based processing pipeline
- real ingestion and tagging
- moderation and account flows
- invite-only onboarding
- admin settings for tagger and sidebar behavior
