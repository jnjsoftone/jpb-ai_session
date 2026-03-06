---
name: version-control
description: 소스 코드 및 개발/운영 문서의 버전 관리를 전담한다. "현재까지의 변경사항을 적용해줘" 요청 시 자동으로 호출되어야 한다.
tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# 버전 관리 에이전트

소스 코드 GitHub push와 문서 Obsidian 볼트 동기화를 담당한다.

## 트리거

"현재까지의 변경사항을 적용해줘" (또는 유사한 표현)

## 경로 상수

- **저장소 루트**: `C:/dev/shared/backends/jpb-ai_session`
- **Obsidian 볼트**: `.env`의 `OBSIDIAN_ROOT` 값 사용 (기본값 없음 — 반드시 설정되어 있어야 함)

## 실행 절차

### 1단계 — 소스 코드 및 문서 업데이트

현재 대화에서 논의된 변경사항을 소스 코드와 개발/운영 문서(README.md, CLAUDE.md 등)에 반영한다.
이미 반영되어 있다면 이 단계를 건너뛴다.

### 2단계 — GitHub Push

```bash
cd "C:/dev/shared/backends/jpb-ai_session"

# 변경된 소스 파일만 스테이징 (환경 파일 제외)
git status
git add -A -- ':!*.env' ':!*.env.local' ':!*.env.*'

# 커밋 메시지는 실제 변경 내용을 요약해서 작성
git commit -m "<변경 내용 요약>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

git push
```

> 커밋할 변경사항이 없으면 push를 건너뛴다.

### 3단계 — Obsidian 볼트 동기화

아래 대상 경로의 파일을 Obsidian 볼트로 동기화한다.
**새로 생성되었거나 내용이 변경된 파일만** 복사하고, 변경 없는 파일은 건너뛴다.

#### 동기화 대상

| 저장소 경로 | 볼트 내 경로 |
|---|---|
| `_docs/` | `_docs/` |
| `_drafts/` | `_drafts/` |
| `_backups/` | `_backups/` |
| `.claude/` | `.claude/` |
| `.env` | `.env` |
| `.env.local` | `.env.local` |
| `.env.sample` | `.env.sample` |

#### 동기화 로직 (Python 스크립트로 실행)

```bash
python - <<'EOF'
import shutil, hashlib, os
from pathlib import Path
from dotenv import load_dotenv

SRC = Path("C:/dev/shared/backends/jpb-ai_session")
load_dotenv(SRC / ".env")

obsidian_root = os.environ.get("OBSIDIAN_ROOT", "").strip().strip('"')
if not obsidian_root:
    raise SystemExit("ERROR: OBSIDIAN_ROOT가 .env에 설정되어 있지 않습니다.")

DST = Path(obsidian_root)
if not DST.exists():
    raise SystemExit(f"ERROR: Obsidian 볼트 경로에 접근할 수 없습니다: {DST}")

def md5(path):
    return hashlib.md5(path.read_bytes()).hexdigest()

def sync_file(src_file, dst_file):
    if not src_file.exists():
        return
    dst_file.parent.mkdir(parents=True, exist_ok=True)
    if dst_file.exists() and md5(src_file) == md5(dst_file):
        print(f"  SKIP (unchanged): {dst_file.relative_to(DST)}")
        return
    shutil.copy2(src_file, dst_file)
    print(f"  SYNCED: {dst_file.relative_to(DST)}")

def sync_dir(src_dir, dst_dir):
    if not src_dir.exists():
        return
    for src_file in src_dir.rglob("*"):
        if src_file.is_file():
            rel = src_file.relative_to(src_dir)
            sync_file(src_file, dst_dir / rel)

# 디렉토리 동기화
for d in ["_docs", "_drafts", "_backups", ".claude"]:
    print(f"\n[{d}/]")
    sync_dir(SRC / d, DST / d)

# 단일 파일 동기화
print("\n[root files]")
for f in [".env", ".env.local", ".env.sample"]:
    sync_file(SRC / f, DST / f)

print("\nDone.")
EOF
```

## 주의사항

- `.env`, `.env.local` 등 환경 파일은 **git에 커밋하지 않는다**. Obsidian 볼트에만 동기화한다.
- `_backups/` 내 대용량 바이너리가 있을 경우 동기화 시간이 길어질 수 있다.
- Obsidian 볼트 경로(`G:` 드라이브)가 마운트되어 있지 않으면 동기화 단계에서 오류가 발생한다. 이 경우 사용자에게 알린다.
