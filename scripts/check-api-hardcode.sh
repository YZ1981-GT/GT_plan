#!/bin/bash
# 检查 Vue 文件中硬编码 API 路径数量
# 用法: bash scripts/check-api-hardcode.sh
# 基线只允许减少不允许增加

BASELINE=173
DIR="audit-platform/frontend/src"

COUNT=$(grep -r --include="*.vue" -E "['\`\"/]/api/" "$DIR/views" "$DIR/components" \
  | grep -v "apiPaths" | grep -v "^\s*//" | grep -v "^\s*\*" | wc -l)

echo "📊 Vue 文件硬编码 API 路径: $COUNT (基线: $BASELINE)"

if [ "$COUNT" -gt "$BASELINE" ]; then
  echo "❌ 硬编码数量增加了！请使用 apiPaths 常量。"
  echo "   新增的硬编码:"
  grep -rn --include="*.vue" -E "['\`\"/]/api/" "$DIR/views" "$DIR/components" \
    | grep -v "apiPaths" | grep -v "^\s*//" | grep -v "^\s*\*" | tail -20
  exit 1
elif [ "$COUNT" -lt "$BASELINE" ]; then
  echo "✅ 硬编码减少了 $((BASELINE - COUNT)) 处，记得更新 CI 基线！"
else
  echo "✅ 硬编码数量未增加"
fi
