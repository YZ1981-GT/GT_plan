# ADR-028: 默认分支 main 替代 master

- **Date**: 2026-05-29
- **Status**: Accepted
- **Spec**: repo-git-workflow-unification

## Context

仓库历史使用 `master` 作为默认分支，2026-05-29 实测发现：

- `master` 落后真实工作 ~227 commit（4 天没更新）
- 真实工作在 `feature/disclosure-note-full-revamp` 分支
- 新人 / CI / IDE 看到 `master` 误认为是真理基线

GitHub 2020 后行业惯例是 `main` 替代 `master`（默认新仓库）。

## Decision

**默认分支重命名为 `main`**：

1. push 当前真理 `feature/disclosure-note-full-revamp` → 新建 `main` 远程分支
2. GitHub web UI 把默认分支切到 `main`（用户操作）
3. 删 `master` + `feature/disclosure-note-full-revamp` 远程分支
4. 本地切到 `main`

## Consequences

### 正面

- 单一真理基线 = `main`
- 行业惯例（GitHub 默认 / 文档常见）
- 减一个分支减一份维护负担
- pre-push hook 可以"main 唯一可直推"作为 single 模式默认

### 负面

- 历史 git URL 引用（旧 PR / 旧文档）可能含 `master` 字样需手动改
- 本地老 clone 需重新 `git remote set-head origin --auto`

## Migration

```powershell
# 1. push main（已完成）
git push origin feature/disclosure-note-full-revamp:main

# 2. 用户在 GitHub web 切默认分支（待用户操作）
#    Settings → Branches → Default branch → main

# 3. 删旧远程分支（待第 2 步完成后）
git push origin --delete master
git push origin --delete feature/disclosure-note-full-revamp

# 4. 本地切 main（已完成）
git checkout main
git branch --set-upstream-to=origin/main main
```

## Verification

- `origin/main` 存在 + HEAD = a865f864（与真理一致）
- 本地 `main` 跟踪 `origin/main`
- 新工作直接基于 `main`
