#!/usr/bin/env python3
"""
Claude Code 세션 JSONL → Markdown 변환기

사용법:
  # 특정 세션 파일 변환
  python session-to-md.py <session.jsonl> [출력파일.md]

  # 프로젝트의 모든 세션 변환
  python session-to-md.py --project <프로젝트경로> [--outdir <출력디렉토리>]

  # 모든 프로젝트의 모든 세션 변환
  python session-to-md.py --all [--outdir <출력디렉토리>]

예시:
  python session-to-md.py ~/.claude/projects/my-project/abc123.jsonl
  python session-to-md.py --project C:/JnJ/... --outdir ./docs/sessions
  python session-to-md.py --all --outdir C:/sessions
"""

import sys
import argparse
from datetime import datetime
from pathlib import Path

from session_core import (
    PROJECTS_DIR,
    fmt_ts,
    session_to_markdown,
    get_project_sessions,
    convert_session,
)


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Claude Code 세션 JSONL → Markdown 변환기"
    )
    parser.add_argument("file", nargs="?", help="변환할 .jsonl 파일 경로")
    parser.add_argument("-o", "--output", help="출력 .md 파일 경로")
    parser.add_argument("--project", help="프로젝트 경로 (해당 프로젝트의 모든 세션 변환)")
    parser.add_argument("--all", action="store_true", help="모든 프로젝트의 모든 세션 변환")
    parser.add_argument("--outdir", default="./claude-sessions", help="출력 디렉토리 (기본: ./claude-sessions)")
    parser.add_argument("--tools", action="store_true", help="tool_use/tool_result 포함")
    parser.add_argument("--list", action="store_true", help="프로젝트/세션 목록만 출력")
    args = parser.parse_args()

    outdir = Path(args.outdir)

    # ── 목록 출력 ──
    if args.list:
        for proj_dir in sorted(PROJECTS_DIR.iterdir()):
            if not proj_dir.is_dir():
                continue
            sessions = get_project_sessions(proj_dir)
            if not sessions:
                continue
            print(f"\n[DIR] {proj_dir.name}")
            for s in sessions:
                mtime = datetime.fromtimestamp(s.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                size_kb = s.stat().st_size // 1024
                print(f"   {mtime}  {size_kb:>5}KB  {s.name}")
        return

    # ── 단일 파일 변환 ──
    if args.file:
        jsonl_path = Path(args.file).expanduser()
        if not jsonl_path.exists():
            print(f"오류: 파일을 찾을 수 없습니다: {jsonl_path}")
            sys.exit(1)

        md = session_to_markdown(jsonl_path, include_tools=args.tools)

        if args.output:
            outpath = Path(args.output)
        else:
            outpath = jsonl_path.with_suffix(".md")

        outpath.write_text(md, encoding="utf-8")
        print(f"✓ 저장됨: {outpath}")
        return

    # ── 프로젝트 단위 변환 ──
    if args.project:
        project_path = Path(args.project)
        # 마지막 경로 구성요소(폴더 이름)로 ~/.claude/projects/ 아래에서 매칭
        last_part = project_path.name
        matches = [d for d in PROJECTS_DIR.iterdir() if d.is_dir() and last_part in d.name]

        if not matches:
            # 직접 경로로 시도
            matches = [project_path] if project_path.exists() else []

        if not matches:
            print(f"오류: 프로젝트를 찾을 수 없습니다: {args.project}")
            print(f"사용 가능한 프로젝트:")
            for d in PROJECTS_DIR.iterdir():
                if d.is_dir():
                    print(f"  {d.name}")
            sys.exit(1)

        for proj_dir in matches:
            print(f"\n프로젝트: {proj_dir.name}")
            sessions = get_project_sessions(proj_dir)
            proj_outdir = outdir / proj_dir.name
            for s in sessions:
                convert_session(s, proj_outdir, include_tools=args.tools)
        return

    # ── 전체 변환 ──
    if args.all:
        for proj_dir in sorted(PROJECTS_DIR.iterdir()):
            if not proj_dir.is_dir():
                continue
            sessions = get_project_sessions(proj_dir)
            if not sessions:
                continue
            print(f"\n[DIR] {proj_dir.name}")
            proj_outdir = outdir / proj_dir.name
            for s in sessions:
                convert_session(s, proj_outdir, include_tools=args.tools)
        print(f"\n완료. 출력 위치: {outdir.resolve()}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
