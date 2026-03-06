# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Python backend for converting Claude Code session JSONL files (`~/.claude/projects/<project>/<session_id>.jsonl`) to Markdown. Two interfaces: a CLI and a FastAPI REST server. Core logic is shared in `session_core.py`.

The main code lives in `backend/`. See `cli/claude-sessions/CLAUDE.md` for detailed API/endpoint documentation.

## Python Environment

`backend/` uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
cd backend
uv sync          # install dependencies into .venv
uv add <pkg>     # add a new dependency
```

> `uvicorn[standard]` extras (httptools) require C build tools on Windows. Use plain `uvicorn` instead.

## Running the CLI

```bash
cd backend

# Convert a single session file
uv run python session-to-md.py <session.jsonl> [-o output.md]

# Convert all sessions for a project
uv run python session-to-md.py --project <project-path> [--outdir <dir>]

# Convert all projects
uv run python session-to-md.py --all [--outdir <dir>]

# List available sessions
uv run python session-to-md.py --list

# Include tool_use/tool_result blocks
uv run python session-to-md.py <file> --tools
```

## Running the API Server

```bash
cd backend
uv run uvicorn api:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

## Architecture

Three-layer design in `session_core.py`:
1. `extract_text` — converts a JSONL `content` block (str or list) to Markdown; handles `text`, `thinking` (collapsed `<details>`), `tool_use`, `tool_result` (truncated at 2000 chars)
2. `session_to_markdown` — iterates JSONL lines, collects metadata (cwd, gitBranch, version, timestamps), filters out tool-only user messages when `include_tools=False`, returns full Markdown string
3. `convert_session` / `get_project_sessions` — file I/O; output filenames use `YYYYMMDD-HHMMSS-{session_id[:8]}.md`

`api.py` is a thin FastAPI layer on top. `resolve_project_dir` does exact-then-partial name matching; ambiguous matches return 400, missing return 404.
