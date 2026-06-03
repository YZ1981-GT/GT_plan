---
inclusion: always
---

# 持久记忆

每次对话自动加载，**保持 ≤ 200 行**。完成事项明细 → `#dev-history`；技术决策 → `#architecture`；规范铁律 → `#conventions`；spec 状态 → `.kiro/specs/INDEX.md`。归档历史见 `git show <旧commit>:.kiro/steering/memory.md`。

## 用户偏好

- 语言中文；本地优先轻量方案；启动 `start-dev.bat`（后端 9980 + 前端 3030）；打包 `build_exe.py`（PyInstaller 不要 .bat）
- **输出分步但连续做完**：一次不要太长、大改动拆小批次，但要做完整个任务不要每段停问（只在真正需决策时停）
- **任务标记不能假绿**：标 completed 必须有实际代码+测试通过证据；外部依赖如实标 `[ ]*`
- **彻底解决不绕开**：错误必复现+定位根因+修主代码+加防御测试，绝不"换参数避开"
- **触类旁通 grep**：发现一处反模式立即 grep 全仓找同类一次修完
- **优先用 codegraph MCP**：改动前先看影响面（impact/callers/callees），比手动 grep 快且全
- **改动前先 spec 三件套**：>500 行文件 / 3+ 组件 / 跨前后端
- **改动后必 Playwright 实测**：getDiagnostics 过 ≠ 运行时无错
- **UI 全中文化**：用户可见文本中文（技术术语保留英文）；硬编码不接 i18n
- **中文场景全链路不能崩**：中文文件名下载（RFC5987）、中文项目名/客户名导出均须实测
- 功能收敛核心 6-8 页做到极致；前后端必须联动；删除二次确认+先进回收站；一次性脚本用完即删
- git 单 commit；**push 前必先 fetch 同步**；**协作走 PR 不直推 main**；默认分支 `main`
- 目标并发 6000 人；底稿编码致同 2025 修订版（206 条 v2025-R5）
- 审计循环代号：A 报表 B 控制了解 C 控制测试 D 销售 E 货币 F 采购存货 G 投资 H 固资 I 无形 J 薪酬 K 管理 L 筹资 M 股东权益 N 税费 S 专项

## 环境配置

- Python 3.12（仓库根 `.venv`）/ Docker / PG 16 / Redis；后端 9980 / 前端 3030 / vLLM 8100；DB `audit_platform`；测试用户 admin/admin123
- **venv 路径**：backend cwd 用 `..\.venv\Scripts\python.exe`；仓库根 cwd 用 `.venv\Scripts\python.exe`
- Docker：`audit-postgres`(5432)/`audit-redis`(6379)/`audit-metabase`(3000)
- **前端唯一路径**：`audit-platform/frontend/`（仓库根无 `frontend/`）
- **MCP 7 个已接入（67 工具）**：codegraph(10) / playwright(23) / js-reverse(21) / context7(2) / fetch(1) / thinking(1) / memory(9)
- **codegraph MCP**：`npx -y @colbymchenry/codegraph serve --mcp --no-watch -p D:/GT_plan`；路径 `D:/GT_plan`（非 D:/GT_workplan）；callers 对 Python class 偏弱需配 grep
- **scripts 规约**：`_` 前缀=一次性用完即删；`backend/scripts/` 分 8 子目录
- **底稿模板源**：`backend/wp_templates/`→`backend/data/gt_template_library.json`（331 条）
- **干净验证法**：in-process ASGI httpx（`httpx.ASGITransport(app=app)`）直调端点最快

## 迁移与 PG schema（D6 MigrationRunner，非 alembic）

- 启动跑 `backend/migrations/V*.sql`+`R*.sql` 配对；CREATE/ALTER 必 `IF NOT EXISTS`；**当前最高 V052**
- **真实列速查**：trial_balance=unadjusted/aje/rje/audited/opening_balance（无 closing）；financial_report=row_code/current_period_amount（无 amount）；adjustments=adjustment_no/review_status（无 status）；working_paper 无 year/wp_code（wp_code 在 wp_index）
- **🔴 projects 表无 year 列**：年度用 `EXTRACT(YEAR FROM audit_period_end)::int`
- **🔴 wp_template_registry 表不存在**：gt_template_library.json 是唯一权威源
- **🔴 明细账翻页余额错**：ledgerDisplay 按页重算余额，>100 笔第 2 页起全错（待修）
- **🔴 0 个 consolidated 项目**：合并 UAT 全 data-blocked
- **契约测试守护**：`test_raw_sql_schema_contract.py` + `test_raw_sql_column_contract.py`；裸 SQL 引用不存在表/列即 CI 红
- schema drift critical=0（V051 修复 51 列 + 2 enum）

## 任务状态

### LLM（vLLM localhost:8100，Qwen3.5-27B-NVFP4）
- `.env` `WP_AI_SERVICE_ENABLED=True`；两套客户端：`llm_client`（httpx+熔断）/ `AIService(db)`
- **🔴 embedding 404**：RAG 降级 ilike；恢复需另起 embed 实例
- 知识库收口完成：旧 KnowledgeService/AIChatService 已删；doc_ai_chat 用 DB 持久化
- **铁律：原生 fetch 调后端必手动解 `{code,message,data}` 信封**

### 合并模块（4 Phase 全完成，归档 09）
- 代码 147+ tests passed + 16 ADR + 24 service；**卡点 = 0 个 consolidated 项目**

### git 状态（2026-06-03）
- 分支 `work/2026-05-30-wp-specs`（最新 `9712c6a7`，已 push）；**待走 PR 合 main**
- **specs 全部归档/清零**：active=0，archived=103；所有功能已实现或被覆盖
- **🔴 远程默认分支隐患**：`origin/HEAD→origin/master` 但活跃主干是 main（需 GitHub Settings 改）
- **🔴 分叉分支 `feature/report-module-enhancement-closure`**：含旧版 WorkpaperWorkbenchView，合并时勿覆盖 work 版
- 远程 `origin = https://github.com/YZ1981-GT/GT_plan.git`（HTTPS）

### 真正待办（外部依赖）
- LLM embedding 实例 / 6000 并发压测 / 钉集成 / 合并模块真实集团数据 UAT / GitHub 默认分支改 main / 走 PR 合入 / 生产 V052 手工迁移

### 近期已完成（明细→`#dev-history`）
- 底稿渲染三自动生成（B-Index/A-Program/GtGridSheet）+ 公式标注 UI
- 审计程序裁剪两层粒度 + 自定义新增程序修复 + 底稿编制信息表头
- custom-workpaper-formula-binding spec（V052 wp_formula + WP() 求值 + 联动）
- frontend-consistency-m1（GtAmountCell 全量化 + handleApiError + 死代码删除 + statusEnum）
- 全局 7 模块改进 spec 全部完成 + 14 个 GET 500 清零 + schema drift 0
- 明细账月小计 off-by-one 修复 + 知识库收口 + doc-chat DB 持久化
- migration advisory lock + V051 schema drift 二次修复

## 操作铁律（详见 `#conventions`）

- **三层一致校验**：DB 迁移 + ORM `Mapped[]` + service 方法，任一缺失即伪绿
- **router_registry 必查**：新建 router 必注册否则前端 404
- **service 只 flush 不 commit**：router 统一 commit 保原子
- **PG 运维**：SET 不支持绑定参数 / ALTER TYPE ADD VALUE 不可事务内即用
- **PowerShell**：写中文用 fsWrite；长 commit msg 用 `git commit --% -m "..."`
- **fsWrite ≥100 行会截断**：大文件分 fsWrite(≤50)+多次小 fsAppend
- **apiProxy 单层解构**：`api.get/post` 已返业务数据；`http.get/post` 需 `.data`
- **`dict.get(k, default)` 陷阱**：key=None 时不返回 default→写库前用 `(data.get(k) or fallback)`
- **CORS/307**：前端 3030 须在 CORS_ORIGINS；FastAPI 无尾斜杠 307 会跨域
- **UI 必用 GT 紫令牌**：`--gt-color-primary:#4b2d77`；禁用 Element 默认蓝
- **hypothesis PBT**：max_examples=5

## 关键引用指南

- **仅 memory.md 是 `inclusion: always`（≤200 行）**；其余 steering 均 manual
- 端点速查/PG schema/修复明细 → `#dev-history`
- 架构/数据流 → `#architecture`；编码规范/铁律详解 → `#conventions`
- spec 索引 → `.kiro/specs/INDEX.md`
