#!/bin/bash
# 테스트 통과 시 자동 커밋·푸시 트리거
# Stop 훅에서 실행됨

set -euo pipefail

REPO="/home/jimmy/Developer/SideProject/facade-inspect"
cd "$REPO"

# 변경된 파일 없으면 스킵
if git diff --quiet HEAD 2>/dev/null && [ -z "$(git status --porcelain)" ]; then
  echo "[auto-deploy] 변경 없음. 스킵."
  exit 0
fi

echo "[auto-deploy] 변경 감지. 테스트 실행 중..."

# ── 백엔드 Python 테스트 ──────────────────────────────────
PY_TESTS=$(find . -name "test_*.py" -not -path "*/node_modules/*" -not -path "*/.venv/*" 2>/dev/null | head -1)
if [ -n "$PY_TESTS" ]; then
  echo "[auto-deploy] pytest 실행..."
  if ! python -m pytest -x -q --tb=short 2>&1; then
    echo "[auto-deploy] ❌ Python 테스트 실패. 커밋 중단."
    exit 0
  fi
  echo "[auto-deploy] ✅ Python 테스트 통과."
else
  echo "[auto-deploy] Python 테스트 파일 없음. 스킵."
fi

# ── 프론트엔드 TypeScript 타입체크 ───────────────────────
CHANGED_FRONTEND=$(git status --porcelain 2>/dev/null | grep "frontend/" | head -1 || true)

if [ -n "$CHANGED_FRONTEND" ] && [ -f "frontend/tsconfig.json" ]; then
  echo "[auto-deploy] TypeScript 타입체크 실행..."
  if ! (cd frontend && npx tsc --noEmit 2>&1); then
    echo "[auto-deploy] ❌ TypeScript 타입체크 실패. 커밋 중단."
    exit 0
  fi
  echo "[auto-deploy] ✅ TypeScript 타입체크 통과."
fi

# ── 자동 커밋·푸시 ───────────────────────────────────────
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
CHANGED_FILES=$(git status --porcelain | wc -l | tr -d ' ')

git add -A

# 커밋 메시지: 변경 파일 수 + 타임스탬프
if ! git commit -m "auto: 코드 변경 자동 커밋 (${CHANGED_FILES}개 파일, ${TIMESTAMP})

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" 2>&1; then
  echo "[auto-deploy] 커밋할 변경사항 없음."
  exit 0
fi

echo "[auto-deploy] ✅ 커밋 완료. Push 중..."
if git push origin main 2>&1; then
  echo "[auto-deploy] ✅ Push 완료."
else
  echo "[auto-deploy] ❌ Push 실패. 로컬 커밋은 유지됩니다."
fi
