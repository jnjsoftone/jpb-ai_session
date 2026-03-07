"""
Claude Code 세션 핵심 비즈니스 로직

session-to-md.py(CLI)와 api.py(FastAPI)가 공유하는 함수 모음.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))

CLAUDE_DIR = Path(os.environ.get("CLAUDE_DIR", Path.home() / ".claude"))
PROJECTS_DIR = CLAUDE_DIR / "projects"

SEP_QA = "=" * 37   # Q&A 쌍 구분자
SEP_UC = "=" * 6    # User/Claude 구분자


# ── 타임스탬프 헬퍼 ──────────────────────────────────────

def fmt_ts(ts_str: str) -> str:
    """ISO 타임스탬프 → 로컬 시간 문자열 변환."""
    if not ts_str:
        return ""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts_str


def fmt_file_ts(dt: datetime) -> str:
    """datetime → frontmatter 형식 (YYYY-MM-DDTHH:mm:ss)."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def fmt_filename_ts(dt: datetime) -> str:
    """datetime → 파일명 형식 (YYYY-MM-DDTHH-mm-ss, ':' → '-')."""
    return dt.strftime("%Y-%m-%dT%H-%M-%S")


# ── 파일명 헬퍼 ──────────────────────────────────────────

def sanitize_title_for_filename(title: str) -> str:
    """
    제목 문자열을 파일명에 안전한 형식으로 변환합니다.
    - 공백 → '-'
    - '-', '_', 한글, 영문, 숫자는 그대로 유지
    - 그 외 특수문자 제거
    """
    # 공백을 '-'로 변환
    title = title.replace(" ", "-")
    # 허용 문자 외 제거: 한글, 영문, 숫자, '-', '_'
    title = re.sub(r"[^\w가-힣\-]", "", title, flags=re.ASCII)
    # 연속 '-' 정리
    title = re.sub(r"-{2,}", "-", title)
    return title.strip("-")


def make_filename(created_at_dt: datetime, title: str) -> str:
    """<createdAt>_<title>.md 형식의 파일명을 생성합니다."""
    ts_part = fmt_filename_ts(created_at_dt)
    title_part = sanitize_title_for_filename(title)
    return f"{ts_part}_{title_part}.md"


# ── 시스템 주입 메시지 필터 ──────────────────────────────

# Claude Code가 자동으로 삽입하는 시스템 메시지 패턴
_SYSTEM_INJECTED_PATTERNS = re.compile(
    r"^(Tool loaded\.|<system-reminder>|<available-deferred-tools>)",
    re.IGNORECASE,
)

def _is_system_injected(text: str) -> bool:
    """Claude Code가 삽입한 시스템 메시지인지 확인합니다."""
    stripped = text.strip()
    return bool(_SYSTEM_INJECTED_PATTERNS.match(stripped))


# ── content 추출 ─────────────────────────────────────────

def extract_text(content, include_tools: bool = False) -> str:
    """
    content(str | list)에서 텍스트를 추출합니다.
    - thinking 블록: 항상 제외 (session-save 스펙)
    - tool_use / tool_result: include_tools=True 일 때만 포함
    """
    if isinstance(content, str):
        return content.strip()

    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")

        if btype == "text":
            text = block.get("text", "").strip()
            if text:
                parts.append(text)

        elif btype == "thinking":
            # session-save 스펙: thinking/reasoning 과정은 절대 포함하지 않음
            pass

        elif btype == "tool_use" and include_tools:
            name = block.get("name", "unknown")
            inp = block.get("input", {})
            inp_str = json.dumps(inp, ensure_ascii=False, indent=2)
            parts.append(f"```tool-use\n[{name}]\n{inp_str}\n```")

        elif btype == "tool_result" and include_tools:
            tool_use_id = block.get("tool_use_id", "")
            result_content = block.get("content", "")
            if isinstance(result_content, list):
                result_text = "\n".join(
                    b.get("text", "") for b in result_content if b.get("type") == "text"
                )
            else:
                result_text = str(result_content)
            if len(result_text) > 2000:
                result_text = result_text[:2000] + "\n... (생략)"
            parts.append(f"```tool-result\n[{tool_use_id}]\n{result_text.strip()}\n```")

    return "\n\n".join(parts)


# ── YAML Frontmatter 생성 ────────────────────────────────

def make_frontmatter(
    title: str,
    session_path: str,
    session_id: str,
    created_at: datetime,
    updated_at: datetime,
    model: str = "claude-sonnet-4-6",
) -> str:
    """
    session-save 스펙에 맞는 YAML frontmatter를 생성합니다.
    techs, phase, scope, agents, description, remark 등
    AI 판단이 필요한 필드는 빈 값으로 남깁니다.
    """
    lines = [
        "---",
        f'title: "{title}"',
        f'sessionPath: "{session_path}"',
        f'sessionId: "{session_id}"',
        f'createdAt: "{fmt_file_ts(created_at)}"',
        f'updatedAt: "{fmt_file_ts(updated_at)}"',
        f'model: "{model}"',
        'mode: ""',
        "techs: []",
        'phase: ""',
        "scope: []",
        "agents: []",
        'description: ""',
        'remark: ""',
        "---",
    ]
    return "\n".join(lines)


# ── 세션 변환 ────────────────────────────────────────────

def session_to_markdown(
    jsonl_path: Path,
    include_tools: bool = False,
    title: str = "",
) -> str:
    """JSONL 세션 파일을 Markdown 문자열로 변환합니다."""
    with open(jsonl_path, encoding="utf-8") as f:
        lines = f.readlines()

    session_id = jsonl_path.stem
    session_path = jsonl_path.parent.name
    model = "claude-sonnet-4-6"
    messages = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = obj.get("type", "")

        # 모델 정보 추출 (assistant 메시지에서)
        if msg_type == "assistant":
            msg_model = obj.get("message", {}).get("model", "")
            if msg_model:
                model = msg_model

        if msg_type not in ("user", "assistant"):
            continue

        message = obj.get("message", {})
        role = message.get("role", msg_type)
        content = message.get("content", "")

        # tool_result만 있는 user 메시지는 제외 (include_tools=False)
        if role == "user" and isinstance(content, list):
            all_tool_result = all(
                b.get("type") == "tool_result" for b in content if isinstance(b, dict)
            )
            if all_tool_result and not include_tools:
                continue

        text = extract_text(content, include_tools=include_tools)
        if text and not _is_system_injected(text):
            messages.append((role, text))

    # 파일 타임스탬프 (JSONL ctime/mtime)
    stat = jsonl_path.stat()
    created_at = datetime.fromtimestamp(stat.st_ctime)
    updated_at = datetime.fromtimestamp(stat.st_mtime)

    # 제목: 인자로 주어지지 않으면 첫 번째 user 메시지에서 생성
    if not title:
        first_user = next((t for r, t in messages if r == "user"), "")
        first_line = first_user.split("\n")[0].strip()
        title = first_line[:60] + ("..." if len(first_line) > 60 else "")
        if not title:
            title = session_id[:8]

    # frontmatter
    fm = make_frontmatter(
        title=title,
        session_path=session_path,
        session_id=session_id,
        created_at=created_at,
        updated_at=updated_at,
        model=model,
    )

    md_lines = [
        fm,
        "",
        f"# 세션 기록: {title}",
        "",
        "---",
        "",
    ]

    # User+Claude 쌍으로 묶어서 Q&A 블록 생성
    # 여러 연속 user 메시지는 마지막 것만 사용 (tool loading 등 중간 메시지 제거)
    pairs: list[tuple[str, str]] = []
    user_buf: list[str] = []

    for role, text in messages:
        if role == "user":
            user_buf.append(text)
        elif role == "assistant":
            # 연속 user 메시지 중 실질적인 것만 선택 (가장 마지막)
            user_text = user_buf[-1] if user_buf else ""
            pairs.append((user_text, text))
            user_buf = []

    # 끝에 답변 없는 user 메시지 처리
    for ut in user_buf:
        pairs.append((ut, ""))

    for user_text, assistant_text in pairs:
        # 사용자 메시지가 비어있는 쌍은 제외 (tool-only 순서 등)
        if not user_text.strip():
            continue
        md_lines.append(SEP_QA)
        md_lines.append("")
        md_lines.append("## User 요청")
        md_lines.append("")
        md_lines.append(user_text)
        md_lines.append("")
        md_lines.append(SEP_UC)
        md_lines.append("")
        if assistant_text:
            md_lines.append("## Claude 답변")
            md_lines.append("")
            md_lines.append(assistant_text)
            md_lines.append("")

    md_lines.append(SEP_QA)
    md_lines.append("")

    return "\n".join(md_lines)


# ── 프로젝트 디렉토리 탐색 ───────────────────────────────

def get_project_sessions(project_dir: Path) -> list:
    """프로젝트 디렉토리에서 세션 jsonl 파일 목록을 반환합니다."""
    return sorted(
        [f for f in project_dir.glob("*.jsonl") if f.stat().st_size > 100],
        key=lambda f: f.stat().st_mtime,
    )


def convert_session(
    jsonl_path: Path,
    outdir: Path,
    include_tools: bool = False,
    title: str = "",
) -> Path:
    """단일 세션 파일을 변환해서 outdir에 저장합니다."""
    outdir.mkdir(parents=True, exist_ok=True)
    stat = jsonl_path.stat()
    created_at = datetime.fromtimestamp(stat.st_ctime)

    md = session_to_markdown(jsonl_path, include_tools=include_tools, title=title)

    # frontmatter에서 최종 title 추출 (session_to_markdown 내부에서 결정됨)
    _title_match = re.search(r'^title: "(.+)"', md, re.MULTILINE)
    effective_title = _title_match.group(1) if _title_match else jsonl_path.stem[:8]

    filename = make_filename(created_at, effective_title)
    outpath = outdir / filename
    outpath.write_text(md, encoding="utf-8")
    print(f"  ✓ {filename}")
    return outpath
