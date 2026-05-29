# ADR-027: git hook 工具链选型

- **Date**: 2026-05-29
- **Status**: Accepted
- **Spec**: repo-git-workflow-unification

## Context

需要选 git hook 实现技术：

1. **husky + lint-staged + commitlint**（行业流行）
   - 优点：生态成熟 / GitHub PR template 集成好
   - 缺点：引入 Node.js 工具链 / package.json 依赖污染 / 中文 commit message 不友好

2. **git 原生 hook + Python 脚本**（本仓库选）
   - 优点：无新依赖（已有 Python） / 与现有 `.pre-commit-config.yaml` 一致 / 跨 Windows/Linux/Mac
   - 缺点：手动安装（不进 git 仓库）

3. **pre-commit framework 全替代**（python 生态）
   - 优点：所有 hook 一站式
   - 缺点：pre-push 阶段支持不完整 / 学习曲线陡

## Decision

**选方案 2：git 原生 hook + Python 脚本 + .pre-commit-config.yaml 共存**：

- pre-commit hook（commit 前）走 `.pre-commit-config.yaml`
- pre-push hook（push 前）走 `.git-hooks/pre-push`（bash）
- 检测脚本统一 Python（`backend/scripts/check_git_*.py`）
- 安装方式：`.git-hooks/install.ps1` 一键 copy 到 `.git/hooks/`

## Consequences

### 正面

- 0 新依赖（无 Node.js / 无 npm install）
- 与现有 Python 工具链一致（test_check_*.py 单测 + pre-commit hook 复用）
- 跨平台（PowerShell + bash 双适配）
- 紧急救急通道清晰（`git push --no-verify`）

### 负面

- 新人需手动跑 `install.ps1`（克隆后一次性，不复杂）
- 不能直接借用 husky 生态成熟工具

## Verification

- 22 单元测试覆盖核心逻辑
- 实测安装 + 触发：分支命名 / 6 维核查 / 热点文件检测都按预期工作
