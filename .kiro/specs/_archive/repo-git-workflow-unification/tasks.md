---
spec: repo-git-workflow-unification
status: draft
version: v0.1
created: 2026-05-29
total_tasks: 11
total_estimate: 0.7 人天
---

# 实施任务

## Sprint 1：核心脚本（0.3 人天）

### Task 1.1 ⏳ check_git_sync_state.py 6 维核查脚本
- 约 200 行
- 输出 markdown 表格（--report）或非零退出码（--for-push）
- 支持 --branch=<name> 指定分支查任意分支状态

### Task 1.2 ⏳ check_git_branch_naming.py 分支命名规约
- 约 80 行
- 5 类前缀正则（main / spec/ / work/YYYY-MM-DD-* / fix/ / release/v*）
- spec/ 前缀必须对应 `.kiro/specs/<name>/` 真实存在

### Task 1.3 ⏳ check_hotspot_files.py 热点文件检测
- 检查 staged 文件是否含 git_hotspot_files.txt 中的项
- 若含且本地 behind > 0 即返非零
- single 模式跳过

### Task 1.4 ⏳ git_hotspot_files.txt 配置
- 内容：memory.md / INDEX.md / file_size_whitelist.txt（3 项基线）

## Sprint 2：Hook 安装（0.2 人天）

### Task 2.1 ⏳ .git-hooks/pre-push 脚本
- bash 脚本调用上述 3 个 Python 检测脚本
- 退出码非零即拒绝 push

### Task 2.2 ⏳ .git-hooks/install.ps1 一键安装
- 复制到 .git/hooks/
- 兼容 Windows / Linux / Mac

### Task 2.3 ⏳ .pre-commit-config.yaml 加 check-hotspot-pull hook
- files 正则匹配热点文件
- 调用 check_hotspot_files.py

## Sprint 3：环境集成（0.1 人天）

### Task 3.1 ⏳ start-dev.bat 显示 GIT_MODE
- 启动时打印 `[GT] GIT_MODE=single` 或 `multi`
- 不影响后续启动

### Task 3.2 ⏳ docs/operations/git-workflow.md 工作流文档
- 5 类分支命名 examples
- single vs multi 模式切换
- 紧急救急通道（--no-verify）

## Sprint 4：测试 + 沉淀（0.1 人天）

### Task 4.1 ⏳ 测试 test_check_git_sync_state.py
- 5 用例：正常/工作树脏/local!=remote/behind>0/untracked

### Task 4.2 ⏳ 测试 test_check_git_branch_naming.py
- 5 用例：5 类前缀各 1 + 不合规 1 + 无 spec/ 目录 1

### Task 4.3 ⏳ memory.md 同步 + ADR-027/028
- 删旧"声称 git 已同步前必须 6 维核查铁律"（已自动化进 hook）
- 加新"GIT_MODE 双模式 + hook 自动检测"铁律
- ADR-027 git hook 选型 / ADR-028 main 替代 master

## 工作量

| Sprint | 任务 | 工作量 |
|--------|------|--------|
| 1 核心脚本 | 4 | 0.3 |
| 2 Hook 安装 | 3 | 0.2 |
| 3 环境集成 | 2 | 0.1 |
| 4 测试沉淀 | 3 | 0.1 |
| **合计** | **12** | **0.7 人天** |
