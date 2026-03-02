# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 개요

Claude Code 세션 JSONL 파일을 Markdown으로 변환하는 유틸리티.
CLI(`session-to-md.py`)와 REST API(`api.py`) 두 가지 인터페이스를 제공한다.

세션 파일 위치: `~/.claude/projects/<프로젝트폴더>/<세션ID>.jsonl`

## 파일 구조

```
scripts/
├── session_core.py     공유 비즈니스 로직 (변환 함수)
├── session-to-md.py    CLI 엔트리포인트
├── api.py              FastAPI 서버
└── requirements.txt    fastapi, uvicorn
```

## 실행 방법

### CLI

```bash
# 단일 파일 변환
python session-to-md.py <session.jsonl> [-o 출력.md]

# 특정 프로젝트의 모든 세션 변환
python session-to-md.py --project <프로젝트경로> [--outdir <출력디렉토리>]

# 모든 프로젝트 세션 변환
python session-to-md.py --all [--outdir <출력디렉토리>]

# 세션 목록 확인
python session-to-md.py --list

# tool_use/tool_result 블록 포함
python session-to-md.py <파일> --tools
```

### API 서버

```bash
pip install -r requirements.txt

# 개발 모드 (자동 리로드)
uvicorn api:app --reload --port 8000

# 또는
python api.py
```

Swagger UI: `http://localhost:8000/docs`

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/projects` | 프로젝트 목록 |
| GET | `/projects/{project}/sessions` | 세션 목록 |
| GET | `/projects/{project}/sessions/{session_id}` | 세션 Markdown 조회 |
| POST | `/projects/{project}/sessions/{session_id}/convert` | 세션 → 파일 저장 |
| POST | `/projects/{project}/convert` | 프로젝트 전체 변환 |
| POST | `/convert/all` | 전체 변환 |

공통 Query Parameters:
- `include_tools=true` — tool_use/tool_result 블록 포함 (기본: false)
- `outdir=<경로>` — 변환 저장 경로 (기본: `./claude-sessions`)
- `format=markdown` — 세션 조회 시 `text/markdown` 직접 반환 (기본: JSON)

## 코드 구조

### `session_core.py` — 공유 로직 (3계층)

1. **content 추출** (`extract_text`): JSONL `content` 블록을 Markdown으로 변환.
   `text`, `thinking`(`<details>`), `tool_use`, `tool_result` 타입 처리. 2000자 초과 결과는 축약.

2. **세션 변환** (`session_to_markdown`): JSONL 순회 → 메타데이터(cwd, gitBranch, version, 타임스탬프) + user/assistant 메시지 수집 → Markdown 문서 생성.
   `include_tools=False`이면 tool_result만 있는 user 메시지는 제거(노이즈 감소).

3. **파일 I/O** (`get_project_sessions`, `convert_session`): 세션 목록 조회 및 파일 저장.
   출력 파일명 형식: `YYYYMMDD-HHMMSS-{session_id[:8]}.md`

### `api.py` — FastAPI 레이어

- `resolve_project_dir`: 정확한 이름 → 부분 이름 매칭 순으로 프로젝트 디렉토리 조회. 모호하면 400, 없으면 404.
- Pydantic 모델: `ProjectInfo`, `SessionInfo`, `SessionContent`, `ConvertResult`, `BulkConvertResult`
