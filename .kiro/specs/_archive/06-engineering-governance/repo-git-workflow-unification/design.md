---
spec: repo-git-workflow-unification
status: draft
version: v0.1
created: 2026-05-29
---

# 设计文档：仓库 git 工作流统一治理

## 一、架构总览

```
本地工作:
  GIT_MODE=single (默认)              GIT_MODE=multi
       │                                    │
       ↓                                    ↓
  ┌─────────────────────┐         ┌─────────────────────┐
  │ pre-commit          │         │ pre-commit          │
  │  - 热点文件 pull     │         │  - 热点文件 pull     │
  │    检测（提示）      │         │    检测（拒绝）      │
  └─────────────────────┘         └─────────────────────┘
            │                              │
            ↓                              ↓
  ┌─────────────────────┐         ┌─────────────────────┐
  │ pre-push            │         │ pre-push            │
  │  - 6 维核查（提示） │         │  - 6 维核查（拒绝） │
  │  - 直推 main 允许   │         │  - 直推 main 拒绝   │
  │  - 命名规约检测     │         │  - 命名规约检测     │
  └─────────────────────┘         └─────────────────────┘
            │                              │
            ↓                              ↓
       push 远程                       gh pr create
                                        │
                                        ↓
                                    PR review → squash-merge
                                        │
                                        ↓
                                    push 到 main
```

## 二、文件清单

### 新增

- `backend/scripts/check_git_sync_state.py` — 6 维核查 CLI 工具（约 200 行）
- `backend/scripts/check_git_branch_naming.py` — 分支命名规约检测（约 80 行）
- `backend/scripts/git_hotspot_files.txt` — 热点文件清单
- `.git-hooks/pre-push` — pre-push hook（bash + 调用上述脚本）
- `.git-hooks/install.ps1` — 一键安装 hook 到 `.git/hooks/`
- `docs/operations/git-workflow.md` — 工作流文档

### 修改

- `.pre-commit-config.yaml` — 加 hotspot-pull-check hook
- `start-dev.bat` — 启动时输出 GIT_MODE

## 三、核心逻辑

### 3.1 GIT_MODE 检测

```python
import os
def get_git_mode() -> str:
    return os.environ.get("GIT_MODE", "single").lower()
```

### 3.2 分支命名规约（check_git_branch_naming.py）

```python
import re

VALID_PREFIXES = {
    "main": re.compile(r"^main$"),
    "spec": re.compile(r"^spec/[a-z0-9-]+$"),
    "work": re.compile(r"^work/\d{4}-\d{2}-\d{2}-[a-z0-9-]+$"),
    "fix": re.compile(r"^fix/[a-z0-9-]+$"),
    "release": re.compile(r"^release/v\d+\.\d+(\.\d+)?$"),
}

def validate_branch_name(name: str) -> tuple[bool, str]:
    for prefix, pat in VALID_PREFIXES.items():
        if pat.match(name):
            return True, prefix
    return False, ""
```

### 3.3 热点文件 pull 检测

```python
HOTSPOT_FILES = [
    ".kiro/steering/memory.md",
    ".kiro/specs/INDEX.md",
    "backend/scripts/file_size_whitelist.txt",
]

def check_hotspot_files_safe(staged_files: list[str], behind: int) -> bool:
    """staged 含热点文件且本地 behind > 0 即返 False。"""
    if behind == 0:
        return True
    has_hotspot = any(f in HOTSPOT_FILES for f in staged_files)
    return not has_hotspot
```

### 3.4 6 维核查（check_git_sync_state.py）

```python
def check_six_dimensions() -> dict:
    """
    6 维核查：
    1. 工作树 = clean
    2. 本地 HEAD == 远程 HEAD
    3. ahead 数
    4. behind 数
    5. 未跟踪文件数
    6. 最新 commit 信息
    """
    return {
        "working_tree_clean": ...,
        "local_eq_remote": ...,
        "ahead": ...,
        "behind": ...,
        "untracked_count": ...,
        "last_commit": ...,
    }
```

## 四、Hook 安装策略

### .pre-commit-config.yaml 增量

```yaml
- id: check-hotspot-pull
  name: check-hotspot-pull
  entry: python backend/scripts/check_hotspot_files.py
  language: system
  files: '^(\.kiro/steering/memory\.md|\.kiro/specs/INDEX\.md|backend/scripts/file_size_whitelist\.txt)$'
```

### .git/hooks/pre-push（git 原生 hook）

```bash
#!/usr/bin/env bash
GIT_MODE="${GIT_MODE:-single}"
BRANCH=$(git symbolic-ref --short HEAD)

# 1. 命名规约
python backend/scripts/check_git_branch_naming.py "$BRANCH" || exit 1

# 2. multi 模式直推 main 拒绝
if [ "$GIT_MODE" = "multi" ] && [ "$BRANCH" = "main" ]; then
    echo "❌ multi 模式禁止直推 main，请走 PR 流程"
    echo "   gh pr create --base main --title '...' --body '...'"
    exit 1
fi

# 3. 6 维核查
python backend/scripts/check_git_sync_state.py --for-push || exit 1

exit 0
```

## 五、Hook 安装方式

git 原生 hooks 默认在 `.git/hooks/`（每人本地，不进 git）。提供 `install.ps1` 一键安装：

```powershell
# .git-hooks/install.ps1
Copy-Item .git-hooks/pre-push .git/hooks/pre-push -Force
# Linux/Mac 还需 chmod +x，Windows 不需
```

新人克隆仓库后跑 `.\.git-hooks\install.ps1` 即生效。

## 六、ADR

- ADR-027：选 git 原生 hook + Python 脚本（拒绝 husky / lint-staged Node.js 工具链）
- ADR-028：default 分支选 main 而非 master（行业惯例 + GitHub 默认）

## 七、版本

- v0.1（2026-05-29）：初版
