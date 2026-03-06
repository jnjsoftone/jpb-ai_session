"""
Claude Code 세션 핵심 비즈니스 로직

session-to-md.py(CLI)와 api.py(FastAPI)가 공유하는 함수 모음.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

CLAUDE_DIR = Path(os.environ.get("CLAUDE_DIR", Path.home() / ".claude"))
PROJECTS_DIR = CLAUDE_DIR / "projects"


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


# ── content 추출 ─────────────────────────────────────────

def extract_text(content) -> str:
    """content(str | list)에서 텍스트만 추출합니다."""
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
            thinking = block.get("thinking", "").strip()
            if thinking:
                parts.append(
                    f"<details>\n<summary>💭 thinking</summary>\n\n{thinking}\n\n</details>"
                )

        elif btype == "tool_use":
            name = block.get("name", "unknown")
            inp = block.get("input", {})
            inp_str = json.dumps(inp, ensure_ascii=False, indent=2)
            parts.append(f"```tool-use\n[{name}]\n{inp_str}\n```")

        elif btype == "tool_result":
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
            parts.append(
                f"```tool-result\n[{tool_use_id}]\n{result_text.strip()}\n```"
            )

    return "\n\n".join(parts)


# ── 세션 변환 ────────────────────────────────────────────

def session_to_markdown(jsonl_path: Path, include_tools: bool = False) -> str:
    """JSONL 세션 파일을 Markdown 문자열로 변환합니다."""
    with open(jsonl_path, encoding="utf-8") as f:
        lines = f.readlines()

    session_id = jsonl_path.stem
    cwd = git_branch = version = first_ts = last_ts = ""
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

        if not cwd and obj.get("cwd"):
            cwd = obj["cwd"]
        if not git_branch and obj.get("gitBranch"):
            git_branch = obj["gitBranch"]
        if not version and obj.get("version"):
            version = obj["version"]
        if obj.get("timestamp"):
            ts = obj["timestamp"]
            if not first_ts:
                first_ts = ts
            last_ts = ts

        if msg_type not in ("user", "assistant"):
            continue

        message = obj.get("message", {})
        role = message.get("role", msg_type)
        content = message.get("content", "")
        timestamp = obj.get("timestamp", "")

        if role == "user" and isinstance(content, list):
            all_tool_result = all(
                b.get("type") == "tool_result" for b in content if isinstance(b, dict)
            )
            if all_tool_result and not include_tools:
                continue

        text = extract_text(content)
        if text:
            messages.append((role, text, timestamp))

    project_name = jsonl_path.parent.name
    md_lines = [
        "# Claude Code 세션",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 세션 ID | `{session_id}` |",
        f"| 프로젝트 | `{project_name}` |",
        f"| 작업 경로 | `{cwd}` |",
        f"| 브랜치 | `{git_branch}` |",
        f"| Claude 버전 | `{version}` |",
        f"| 시작 | {fmt_ts(first_ts)} |",
        f"| 종료 | {fmt_ts(last_ts)} |",
        f"| 메시지 수 | {len(messages)} |",
        "",
        "---",
        "",
    ]

    for role, text, ts in messages:
        md_lines.append("## 👤 User" if role == "user" else "## 🤖 Assistant")
        if ts:
            md_lines.append(f"*{fmt_ts(ts)}*")
            md_lines.append("")
        md_lines.append(text)
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    return "\n".join(md_lines)


# ── 프로젝트 디렉토리 탐색 ───────────────────────────────

def get_project_sessions(project_dir: Path) -> list:
    """프로젝트 디렉토리에서 세션 jsonl 파일 목록을 반환합니다."""
    return sorted(
        [f for f in project_dir.glob("*.jsonl") if f.stat().st_size > 100],
        key=lambda f: f.stat().st_mtime,
    )


def convert_session(jsonl_path: Path, outdir: Path, include_tools: bool = False) -> Path:
    """단일 세션 파일을 변환해서 outdir에 저장합니다."""
    outdir.mkdir(parents=True, exist_ok=True)
    mtime = datetime.fromtimestamp(jsonl_path.stat().st_mtime)
    filename = f"{mtime.strftime('%Y%m%d-%H%M%S')}-{jsonl_path.stem[:8]}.md"
    outpath = outdir / filename
    md = session_to_markdown(jsonl_path, include_tools=include_tools)
    outpath.write_text(md, encoding="utf-8")
    return outpath
