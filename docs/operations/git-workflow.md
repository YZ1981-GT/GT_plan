# Git 工作流（repo-git-workflow-unification spec）

> 2026-05-29 落地。本仓库所有 git 操作遵循此文档。

## 一、分支命名规约（强约束）

5 类合法前缀，pre-push hook 自动校验：

| 前缀 | 用途 | 示例 |
|------|------|------|
| `main` | 唯一主线（替代历史 `master`） | - |
| `spec/<spec-name>` | spec 实施分支（必须对应 `.kiro/specs/<name>/` 真实存在） | `spec/migration-runner-resilience` |
| `work/YYYY-MM-DD-<topic>` | 单次工作分支（短期，含日期） | `work/2026-05-30-report-module-fix` |
| `fix/<issue>` | bug 热修 | `fix/health-endpoint-degraded` |
| `release/v<version>` | 发布候选 | `release/v1.0` `release/v1.0.1` |

不符合规约的分支名 push 时被 hook 拒绝。

## 二、双模式（GIT_MODE 环境变量）

### single（默认）— 单用户快节奏

- 适用：你独自工作
- 特点：保留 `git 提交不分多区，单 commit 全部变更` 偏好
- pre-commit / pre-push hook 仅警告不阻断
- 可直推 `main`

### multi — 多用户严格 PR

- 适用：与他人协作
- 特点：强制 PR 流程，避免推时直接覆盖他人工作
- pre-push hook 拒绝直推 `main`
- 热点文件（memory.md / INDEX.md / file_size_whitelist.txt）改动前必须 `git pull --rebase`

### 切换方式

```powershell
# 临时
$env:GIT_MODE = "multi"

# 永久（系统环境变量）
[Environment]::SetEnvironmentVariable("GIT_MODE", "multi", "User")
```

`start-dev.bat` 启动时打印当前模式，方便确认。

## 三、热点文件冲突预防

3 个高频冲突文件由 pre-commit hook `check-hotspot-files` 监控：

- `.kiro/steering/memory.md`
- `.kiro/specs/INDEX.md`
- `backend/scripts/file_size_whitelist.txt`

修改前自动检测本地是否落后远程，落后即提示：

```
❌ 检测到热点文件改动 + 本地 behind 远程 N commit
   建议先 `git pull --rebase origin <branch>` 再 commit
```

multi 模式阻断，single 模式仅警告。

## 四、6 维核查工具

```powershell
# 查看当前分支同步状态（markdown 报表）
.\.venv\Scripts\python.exe backend/scripts/check_git_sync_state.py

# pre-push 严格模式（仅退出码）
.\.venv\Scripts\python.exe backend/scripts/check_git_sync_state.py --for-push --quiet

# 指定分支
.\.venv\Scripts\python.exe backend/scripts/check_git_sync_state.py --branch=main
```

6 维：
1. 工作树 = clean
2. 本地 HEAD == 远程 HEAD
3. ahead 数 = 0
4. behind 数 = 0
5. 未跟踪文件数 = 0（仅 strict 模式）
6. 最新 commit 信息

## 五、Hook 安装

新人克隆仓库后跑：

```powershell
.\.git-hooks\install.ps1
```

把 `.git-hooks/pre-push` 复制到 `.git/hooks/`。

`.git/hooks/` 是每人本地状态，不进 git 仓库，所以新成员需手动安装。

## 六、紧急救急通道

任何 hook 阻塞时可用 `--no-verify` 绕过：

```powershell
git push --no-verify
git commit --no-verify
```

**仅紧急情况**（如修线上 bug），事后必须补做 6 维核查 + 解决遗留问题。

## 七、常见操作示例

### 单用户日常（GIT_MODE=single）

```powershell
# 直接在 main 上工作
git pull --rebase
# ... 编辑 ...
git add -A
git commit -m "..."
git push origin main
```

### 多用户协作（GIT_MODE=multi）

```powershell
# 1. 同步 main
git checkout main
git pull --rebase

# 2. 开新分支
git checkout -b spec/my-spec-name
# 或: git checkout -b work/2026-05-30-bug-fix

# 3. 工作 + commit
git add -A
git commit -m "..."

# 4. push + 创 PR
git push -u origin spec/my-spec-name
gh pr create --base main --title "..." --body "..."

# 5. PR review 通过后 squash-merge 到 main（GitHub UI）
```

### 启动新 spec 分支

```powershell
# 1. 先建 spec 三件套
mkdir .kiro/specs/my-new-spec
# 写 requirements.md / design.md / tasks.md

# 2. 切分支（hook 会校验目录存在）
git checkout -b spec/my-new-spec
```

## 八、参考

- 三件套：`.kiro/specs/repo-git-workflow-unification/`
- 检测脚本：`backend/scripts/check_git_*.py`
- Hook：`.git-hooks/pre-push` + `.pre-commit-config.yaml`
