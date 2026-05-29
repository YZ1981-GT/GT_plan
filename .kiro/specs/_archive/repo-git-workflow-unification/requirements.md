---
spec: repo-git-workflow-unification
status: draft
version: v0.1
created: 2026-05-29
owner: 全局改进 + 多用户协作治理
priority: P1（多用户协作每天遇到 / 单用户偶发但累积成债）
---

# 需求文档：仓库 git 工作流统一治理

## 一、问题陈述

### 实测痛点（2026-05-29）

1. **5 个本地孤儿分支**（gone）累积占空间：cursor/setup-dev-env-6f66 / feat/univer-import-framework-2026-05-02 / feature/cell-selection-comments-cleanup / feature/global-component-library / refactor/pinia-event-store
2. **default 分支错位**：`master` 是默认分支但 4 天没更新，真实工作在 `feature/disclosure-note-full-revamp`，新人 / CI 易混淆
3. **重名冲突频繁**：每次 merge 都涉及 `INDEX.md` / `memory.md` 热点文件冲突，逐次手解 ROI 低
4. **无 PR 流程**：直接 push 到远程 feature 分支，多用户推时易冲突 + 无 review
5. **本机 user 程序为主基线无机制保障**：纯口头约定，没有自动化卡点防止误推送他人版本

### 根因

- 分支命名无规约（`feature/` / `feat/` / `cursor/` / `refactor/` 混用）
- 没有"主线"语义 — `master` 还是 `main` 还是某个 feature？
- 热点文件锁定缺失 — INDEX.md/memory.md 谁先 push 谁覆盖
- 单用户与多用户模式混用 — 单用户可直接推，多用户必须 PR

## 二、范围

### 必做（P0）

- R1 **唯一主线 `main`**：替代 `master`，所有日常工作基于 main + PR 合并
- R2 **分支命名规约**：5 类前缀强制（main / spec/<name> / work/YYYY-MM-DD-<topic> / fix/<issue> / release/<version>）
- R3 **热点文件冲突预防**：memory.md / INDEX.md / file_size_whitelist.txt 等 3 文件改动前必须 `git pull --rebase`，pre-commit 卡点
- R4 **强制 PR 流程**（仅 multi-user 模式）：pre-push hook 拒绝直推 main，必走 PR
- R5 **single-user vs multi-user 双模式**：环境变量 `GIT_MODE=single|multi` 切换 hook 严格度
- R6 **6 维核查标准化**：把 memory 已沉淀的"声称 git 已同步前必须 6 维核查"做成 `check_git_sync_state.py` 脚本

### 不做（明确划出）

- ❌ 强制 conventional commits（commit message 格式约束太重，本仓库中文项目难推）
- ❌ 接 commitlint / husky 完整工具链（Python + bash hook 简化即可）
- ❌ rebase 历史 / 改写已 push commit（不动历史）
- ❌ 改 GitHub Actions workflow（现有 CI 不变）

## 三、用户故事

### US-1（单用户日常开发）

**作为**单用户，**我希望**保留单 commit 全部变更的快节奏，**以便**不被 PR 流程拖慢。

**验收**：
- AC-1.1 `GIT_MODE=single`（默认）时，可直接 push 到 main
- AC-1.2 single 模式下不强制 PR
- AC-1.3 single 模式下仍触发 6 维核查 + 热点文件 pull rebase 检查
- AC-1.4 `start-dev.bat` 启动时打印当前 GIT_MODE

### US-2（多用户协作）

**作为**多用户协作者，**我希望**有强制 PR 流程，**以便**避免推时直接覆盖他人工作。

**验收**：
- AC-2.1 `GIT_MODE=multi` 时 pre-push hook 拒绝 push 到 main（提示走 PR）
- AC-2.2 multi 模式下推 main 前必须 ahead/behind = 0/0（force pull rebase）
- AC-2.3 推前自动跑 6 维核查输出 OK / 失败列项
- AC-2.4 push 失败时给出具体提示（不只是退出码）

### US-3（热点文件防冲突）

**作为**任何用户，**我希望**修改 memory.md/INDEX.md 时自动提醒 pull，**以便**不再制造可避免的冲突。

**验收**：
- AC-3.1 stage 含热点文件时 pre-commit 检测本地 behind > 0 即拒
- AC-3.2 提示信息含具体命令 `git pull --rebase origin <branch>`
- AC-3.3 热点文件清单可配置（`backend/scripts/git_hotspot_files.txt`）
- AC-3.4 single 模式可绕过（hook 检测 GIT_MODE 跳过）

### US-4（分支命名约束）

**作为**新人 / 审计人员，**我希望**所有分支命名遵循统一规约，**以便**一眼看出分支用途。

**验收**：
- AC-4.1 pre-push hook 检测分支名前缀（main / spec/ / work/ / fix/ / release/）
- AC-4.2 不符合规约的分支名拒绝 push
- AC-4.3 work/ 前缀必须含日期 `YYYY-MM-DD`
- AC-4.4 spec/<name> 必须对应 `.kiro/specs/<name>/` 真实存在
- AC-4.5 examples 列表清晰（README 文档）

### US-5（同步状态可视化）

**作为**任何用户，**我希望**一条命令查看完整 git 健康度，**以便**快速判断是否可以推。

**验收**：
- AC-5.1 `python backend/scripts/check_git_sync_state.py` 输出 6 维核查表
- AC-5.2 表含：工作树状态 / 本地 vs 远程 HEAD / ahead/behind / 未跟踪文件 / tags / 最新 commit
- AC-5.3 任一项异常即非零退出码
- AC-5.4 可作为 pre-push hook 调用（`--for-push` 模式）
- AC-5.5 可作为 cli 工具调用（`--report` 输出 markdown 表格）

## 四、卡点 CI

| 编号 | 描述 | 实施位置 |
|------|------|----------|
| CI-1 | 不符合命名规约的分支推送拒绝 | pre-push hook 检测分支前缀 |
| CI-2 | multi 模式下 main 直推拒绝 | pre-push hook + GIT_MODE 检测 |
| CI-3 | 热点文件 + behind > 0 拒提交 | pre-commit hook |
| CI-4 | check_git_sync_state.py 6 维全绿才允许 push | pre-push hook |
| CI-5 | start-dev.bat 启动时显示 GIT_MODE | bat 脚本检测 |

## 五、依赖前置

| 编号 | 描述 | 责任方 | 状态 |
|------|------|--------|------|
| P-1 | GitHub web 把默认分支切到 main | 用户 | ⏳ 待办 |
| P-2 | 远程 master 删除 | 切默认后自动可删 | ⏳ |
| P-3 | 远程 feature/disclosure-note-full-revamp 删除（合并到 main 后） | 自动 | ⏳ |
| P-4 | pre-commit / pre-push hook 框架（已有 .pre-commit-config.yaml） | 自有 | ✅ |

## 六、风险

| 风险 | 等级 | 缓解 |
|------|------|------|
| single→multi 切换不及时导致协作冲突 | 中 | 默认 single + 邀请新协作者时手动改 multi |
| 热点文件 hook 误拦截单用户日常 | 中 | single 模式直接跳过 |
| 命名规约太严阻塞临时分支 | 低 | work/YYYY-MM-DD-<topic> 是宽松前缀 |
| pre-push hook 阻塞紧急修复 | 低 | 提供 `--no-verify` 救急通道（强警告日志）|

## 七、验收数字

- 验收 AC：5 user stories × 平均 4 = **22 AC**
- CI 卡点：**5**
- 必做范围：**6 R**
- 测试：**3 hook 单测 + 1 e2e smoke = 4 测试**
- 工作量：**0.7 人天**（设计 0.1 + R1-R2 0.1 + R3-R6 0.3 + 测试 0.2）

## 八、版本

- v0.1（2026-05-29）：初版
