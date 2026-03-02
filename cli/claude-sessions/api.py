#!/usr/bin/env python3
"""
Claude Code 세션 관리 FastAPI 서버

실행:
  uvicorn api:app --reload --port 8000
  python api.py

Swagger UI: http://localhost:8000/docs
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from session_core import (
    PROJECTS_DIR,
    fmt_ts,
    session_to_markdown,
    get_project_sessions,
    convert_session,
)

app = FastAPI(
    title="Claude Code Session API",
    description="Claude Code 세션 JSONL 파일 조회 및 Markdown 변환 API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Response Models ───────────────────────────────────────

class ProjectInfo(BaseModel):
    name: str
    session_count: int
    latest_mtime: Optional[str]


class SessionInfo(BaseModel):
    id: str
    filename: str
    size_kb: int
    mtime: str


class SessionContent(BaseModel):
    session_id: str
    project: str
    markdown: str


class ConvertResult(BaseModel):
    input_file: str
    output_file: str


class BulkConvertResult(BaseModel):
    converted: list[ConvertResult]
    total: int


# ── 유틸리티 ─────────────────────────────────────────────

def resolve_project_dir(project_name: str) -> Path:
    """프로젝트 이름으로 디렉토리 경로를 반환합니다. 부분 이름 매칭 지원."""
    if not PROJECTS_DIR.exists():
        raise HTTPException(status_code=404, detail="~/.claude/projects 디렉토리가 없습니다.")

    exact = PROJECTS_DIR / project_name
    if exact.exists() and exact.is_dir():
        return exact

    matches = [d for d in PROJECTS_DIR.iterdir() if d.is_dir() and project_name in d.name]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = [d.name for d in matches]
        raise HTTPException(
            status_code=400,
            detail=f"프로젝트 이름이 모호합니다. 더 구체적으로 입력하세요: {names}",
        )
    raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_name}")


# ── Endpoints ────────────────────────────────────────────

@app.get("/projects", response_model=list[ProjectInfo], summary="프로젝트 목록")
def list_projects():
    """모든 Claude Code 프로젝트 목록을 반환합니다."""
    if not PROJECTS_DIR.exists():
        return []

    result = []
    for proj_dir in sorted(PROJECTS_DIR.iterdir()):
        if not proj_dir.is_dir():
            continue
        sessions = get_project_sessions(proj_dir)
        latest = None
        if sessions:
            latest = fmt_ts(
                datetime.fromtimestamp(sessions[-1].stat().st_mtime).isoformat()
            )
        result.append(
            ProjectInfo(
                name=proj_dir.name,
                session_count=len(sessions),
                latest_mtime=latest,
            )
        )
    return result


@app.get(
    "/projects/{project_name}/sessions",
    response_model=list[SessionInfo],
    summary="세션 목록",
)
def list_sessions(project_name: str):
    """특정 프로젝트의 세션 목록을 반환합니다."""
    proj_dir = resolve_project_dir(project_name)
    sessions = get_project_sessions(proj_dir)
    return [
        SessionInfo(
            id=s.stem,
            filename=s.name,
            size_kb=s.stat().st_size // 1024,
            mtime=fmt_ts(datetime.fromtimestamp(s.stat().st_mtime).isoformat()),
        )
        for s in sessions
    ]


@app.get(
    "/projects/{project_name}/sessions/{session_id}",
    summary="세션 Markdown 조회",
)
def get_session(
    project_name: str,
    session_id: str,
    include_tools: bool = Query(False, description="tool_use/tool_result 블록 포함"),
    format: str = Query("json", description="응답 형식: json | markdown"),
):
    """
    세션을 Markdown으로 변환하여 반환합니다.

    - `format=json` (기본): `{"session_id": ..., "markdown": ...}` JSON 반환
    - `format=markdown`: `text/markdown` 원문 반환
    """
    proj_dir = resolve_project_dir(project_name)
    jsonl_path = proj_dir / f"{session_id}.jsonl"
    if not jsonl_path.exists():
        raise HTTPException(status_code=404, detail=f"세션을 찾을 수 없습니다: {session_id}")

    md = session_to_markdown(jsonl_path, include_tools=include_tools)

    if format == "markdown":
        return PlainTextResponse(md, media_type="text/markdown; charset=utf-8")

    return SessionContent(session_id=session_id, project=project_name, markdown=md)


@app.post(
    "/projects/{project_name}/sessions/{session_id}/convert",
    response_model=ConvertResult,
    summary="세션 → 파일 변환",
)
def convert_session_endpoint(
    project_name: str,
    session_id: str,
    outdir: str = Query("./claude-sessions", description="출력 디렉토리"),
    include_tools: bool = Query(False, description="tool_use/tool_result 블록 포함"),
):
    """세션을 Markdown 파일로 변환하여 저장합니다."""
    proj_dir = resolve_project_dir(project_name)
    jsonl_path = proj_dir / f"{session_id}.jsonl"
    if not jsonl_path.exists():
        raise HTTPException(status_code=404, detail=f"세션을 찾을 수 없습니다: {session_id}")

    outpath = convert_session(jsonl_path, Path(outdir), include_tools=include_tools)
    return ConvertResult(input_file=str(jsonl_path), output_file=str(outpath))


@app.post(
    "/projects/{project_name}/convert",
    response_model=BulkConvertResult,
    summary="프로젝트 전체 변환",
)
def convert_project(
    project_name: str,
    outdir: str = Query("./claude-sessions", description="출력 디렉토리"),
    include_tools: bool = Query(False, description="tool_use/tool_result 블록 포함"),
):
    """프로젝트의 모든 세션을 Markdown 파일로 변환합니다."""
    proj_dir = resolve_project_dir(project_name)
    sessions = get_project_sessions(proj_dir)

    results = []
    for s in sessions:
        proj_outdir = Path(outdir) / proj_dir.name
        outpath = convert_session(s, proj_outdir, include_tools=include_tools)
        results.append(ConvertResult(input_file=str(s), output_file=str(outpath)))

    return BulkConvertResult(converted=results, total=len(results))


@app.post(
    "/convert/all",
    response_model=BulkConvertResult,
    summary="전체 변환",
)
def convert_all(
    outdir: str = Query("./claude-sessions", description="출력 디렉토리"),
    include_tools: bool = Query(False, description="tool_use/tool_result 블록 포함"),
):
    """모든 프로젝트의 모든 세션을 Markdown 파일로 변환합니다."""
    if not PROJECTS_DIR.exists():
        return BulkConvertResult(converted=[], total=0)

    results = []
    for proj_dir in sorted(PROJECTS_DIR.iterdir()):
        if not proj_dir.is_dir():
            continue
        proj_outdir = Path(outdir) / proj_dir.name
        for s in get_project_sessions(proj_dir):
            outpath = convert_session(s, proj_outdir, include_tools=include_tools)
            results.append(ConvertResult(input_file=str(s), output_file=str(outpath)))

    return BulkConvertResult(converted=results, total=len(results))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
