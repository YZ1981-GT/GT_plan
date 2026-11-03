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

## 六、无绕过通道

Hook 阻塞时必须修复根因或按错误提示补齐验证。禁止使用 `--no-verify` 绕过 pre-commit / pre-push；紧急修复同样要保留版本标签、远端同步和最小回归证据。

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

## 八、PR Checklist 治理

每个 PR 自动填充 `.github/pull_request_template.md` 中的全局治理自检清单。

提交 PR 时必须逐项确认（不涉及的打 N/A）：

| 检查项 | 说明 |
|--------|------|
| 全局组件 | 新增页面是否复用已有全局组件 |
| 金额 Decimal | 新增金额字段是否使用 Decimal 序列化 |
| 枚举字典 | 新增状态/类型是否进入 `system_dicts` |
| 路由权限 | 新增 API 是否在 `router_registry` 注册 + 配权限和错误码 |
| AI 确认 | 新增 AI 输出是否有人工确认流程 |
| 穿透契约 | 跨模块引用是否使用 LinkageContract |
| 跨 spec 共享原子 | 依赖 ProjectContext/PermissionMatrix/LinkageContract/EvidenceRef/useEditStateMachine 时，确认该原子已 merge main 且测试绿 |
| 数据库三层一致 | migration + ORM + service 三层是否对齐 |

详见模板文件：[`.github/pull_request_template.md`](../../.github/pull_request_template.md)

## 九、远端前移时安全重放（2026-10-29）

`push_version.py push` 保持 fail-closed：fetch 或远端版本标签查询失败立即停止；远端分支已经前移时不自动 rebase / cherry-pick。只有第一次 atomic push 返回失败，且远端分支与完整版本标签视图都未变化时，才原样重试一次。标签说明中的提交范围以远端版本标签剥离后的提交为先，不依赖本地是否已抓取标签对象。

多人并发时按以下流程处理：

1. `git fetch --prune --no-tags origin`，记录目标远端分支 SHA。
2. 在该 SHA 上创建**分离头**临时 worktree，不新建分支。
3. 将本任务提交或明确的文件块重放到临时 worktree；路径无重叠只能作为提示，仍须检查生成物、注册表和跨文件接口的语义冲突。
4. 在候选树运行本任务测试和 `check_staged_tree_self_consistency.py`。
5. 推送前再次 `git ls-remote`；远端 SHA 与第 1 步不同则停止，基于新 SHA 重新构建候选树。
6. 在分离头 worktree 调 `push_version.py push --branch <目标分支> --notes-file <说明>`，由工具原子推送分支和附注标签。

禁止自动 rebase、force push、`--force-with-lease`、`git stash` 和 `--no-verify`。候选树验证通过也不能覆盖会话开始后新增的远端提交。

## 十、参考

- 三件套：`.kiro/specs/repo-git-workflow-unification/`
- 检测脚本：`backend/scripts/check_git_*.py`
- Hook：`.git-hooks/pre-push` + `.pre-commit-config.yaml`
- PR 模板：`.github/pull_request_template.md`
