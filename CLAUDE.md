# CLAUDE.md — 致同审计作业平台（GT_plan）

FastAPI + Vue 3 审计作业平台。全中文交流与 UI 文案（技术术语保留英文）。本地优先轻量方案。

## 本地知识库（每次会话自动生效）

每次提问时，`UserPromptSubmit` hook（`.claude/kb/kb_search.py`，BM25 检索）自动注入 `[KB]` 相关知识片段：

- **优先参考**注入的 `[KB]` 片段，但片段可能截断——需要完整上下文时 Read 对应源文件
- **检索不足时**：Grep `knowledge/`、`docs/`、`.kiro/steering/`，或 Read `knowledge/INDEX.md` 知识地图
- **知识源**：`knowledge/`（本库）+ `.kiro/steering/*.md`（架构/规范/历史精华）+ `docs/**/*.md` + `README.md` + 外部目录（见下）

### 外部知识源（桌面「税务平台」等）

外部目录配置在 `.claude/kb/kb_search.py` 的 `EXTERNAL_DIRS`（当前：`C:\Users\baiji\Desktop\文件\税务平台`）：

- 外部目录中的 **md/txt** 自动纳入检索（排除 node_modules/dist/.git/zip/sourcemap 等代码与依赖）
- 外部目录中的 **docx/xlsx/pdf** 不直接检索——运行增量转换后入库：
  ```
  .venv/Scripts/python.exe .claude/kb/kb_convert.py          # 增量（按 mtime 跳过已转）
  .venv/Scripts/python.exe .claude/kb/kb_convert.py --force  # 全量重转
  ```
  产物在 `knowledge/external/<目录名>/`，头部 frontmatter 带 `source:` 原始路径可回溯
- **新增外部知识源**：往 `EXTERNAL_DIRS` 加路径 → 跑一次 `kb_convert.py` → 下次提问自动生效

### 知识沉淀约定（写后即记）

完成以下工作后，**必须**向 `knowledge/sessions/` 追加沉淀（同日同主题合并）：

| 场景 | 沉淀内容 |
|------|----------|
| 重要技术决策 | 决策 + 理由 + 撤销条件 |
| Bug 修复（排查 ≥30 分钟） | 根因 + 修复方式 + 防范点（文件:行号） |
| 新约定 / 新坑 | 规则 + 背景 |
| 选型 / 配置迁移 | 方案对比 + 结论 |

文件命名 `YYYYMMDD-主题.md`，格式：

```markdown
---
tags: [backend, tax-workpaper]   # 按领域打标签
---
## [HH:mm] 动作：摘要
- 文件/决策/验证证据
```

同时在本目录 `knowledge/INDEX.md` 第一节加一行索引。**外部资料**（审计准则、手册）放 `knowledge/external/`（md 格式）。

## 高频事实（详见 .kiro/steering/）

- **路径**：前端唯一路径 `audit-platform/frontend/`；后端 `backend/`；venv 为仓库根 `.venv`（Python 3.12）
- **端口**：后端 9980 / 前端 3030 / vLLM 8100；启动 `start-dev.bat`
- **不要新建分支**：直接提交推送到当前分支（push 前 fetch 同步）
- **UI 全中文化**；改动后 Playwright 实测；任务标记不得假绿
