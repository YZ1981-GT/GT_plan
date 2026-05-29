---
spec: repo-frontend-layout-unification
status: draft
version: v0.1
created: 2026-05-29
total_tasks: 9
total_estimate: 0.5 人天
---

# 实施任务

## Task 1 ✅ 5 空壳组件引用扫描
- `backend/scripts/_verify_orphan_frontend_components.py` 一次性脚本（用完已删） ✅
- 扫描结果：**5 个全部 0 引用（C 类死代码）** ✅

## Task 2 ✅ 5 空壳组件按建议处理
- 5 个全是 C 类（0 引用）→ 直接 `git rm` ✅

## Task 3 ✅ git tag 防回退
- `git tag pre-frontend-cleanup-2026-05-29` 已建 ✅

## Task 4 ✅ git rm -r frontend/ 整目录
- 整目录已删（`Test-Path frontend` = False） ✅

## Task 5 ✅ 配置文件 grep 检查
- 全仓 grep `frontend/src` 排除真路径后 **0 业务命中**（仅 todo-inventory + docs/templates 等历史档案）✅

## Task 6 ✅ 启动 + 测试 smoke
- `from app.main import app` 通过 ✅
- spec 全集 96/96 测试全绿 ✅
- 前端 vue-tsc / vitest（用户自行验证，不在本轮范围）

## Task 7 ✅ pre-commit hook
- `backend/scripts/check_no_root_frontend.py` 写完 ✅
- `.pre-commit-config.yaml` 已加 ✅
- 单测正向（exit=0）+ 反向（exit=1）✅

## Task 8 ✅ memory.md 同步
- 删旧铁律「同时检查 `views/` 根目录 + `components/` 子目录」 ✅
- 加新铁律「前端唯一路径 = audit-platform/frontend/」+ pre-commit hook 防回归 ✅

## Task 9 ✅ ADR-026 沉淀
- `docs/adr/ADR-026-repo-frontend-layout-selection.md` ✅

## 工作量

| Task | 工作量 |
|------|--------|
| 1 引用扫描 | 0.05 |
| 2 5 文件处理 | 0.05 |
| 3 git tag | 0.01 |
| 4 git rm 目录 | 0.01 |
| 5 配置 grep | 0.05 |
| 6 测试 smoke | 0.15 |
| 7 hook + 单测 | 0.10 |
| 8 memory 同步 | 0.05 |
| 9 ADR | 0.03 |
| **合计** | **0.5 人天** |
