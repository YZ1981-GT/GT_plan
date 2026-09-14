#!/usr/bin/env bash
# CI 构建期版本注入脚本
# 在构建前执行，将 git 版本信息写入 backend/app/_build_version.json
# Feature: zero-downtime-deployment, Component 1a
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_FILE="$REPO_ROOT/backend/app/_build_version.json"

# 获取版本信息
GIT_COMMIT=$(git rev-parse --short HEAD)
BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SEMANTIC_VERSION=$(git describe --tags --abbrev=0 2>/dev/null || echo "0.0.0-dev")

# 写入 JSON
cat > "$OUTPUT_FILE" << EOF
{
  "semantic_version": "$SEMANTIC_VERSION",
  "git_commit": "$GIT_COMMIT",
  "build_time": "$BUILD_TIME"
}
EOF

# 校验
if [ ! -f "$OUTPUT_FILE" ]; then
  echo "ERROR: Failed to create $OUTPUT_FILE"
  exit 1
fi

COMMIT_IN_FILE=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['git_commit'])" 2>/dev/null || python -c "import json; print(json.load(open('$OUTPUT_FILE'))['git_commit'])")
if [ "$COMMIT_IN_FILE" = "unknown" ]; then
  echo "ERROR: git_commit is 'unknown' — injection failed"
  exit 1
fi

echo "Build version injected: $OUTPUT_FILE"
echo "  semantic_version: $SEMANTIC_VERSION"
echo "  git_commit: $GIT_COMMIT"
echo "  build_time: $BUILD_TIME"
