---
inclusion: always
---

# 持久记忆

每次对话自动加载。详见 `#architecture` / `#conventions` / `#dev-history`。
保持本文件 ≤ 200 行：完成事项 → dev-history，技术决策 → architecture，规范/铁律 → conventions。

## 用户偏好

- 语言中文；本地优先轻量方案；启动 `start-dev.bat`（后端 9980 + 前端 3030）；打包 `build_exe.py`（PyInstaller，不要 .bat）
- **输出控制**：分步输出/修改，大改动拆小批次；不一次出过多内容
- 功能收敛：停加新功能，核心 6-8 页做到极致，空壳标 developing
- 前后端必须联动；删除二次确认 + 先进回收站；一次性脚本用完即删
- git 提交不分多区，单 commit 提交所有变更
- 提建议前先验证（不引用过时记录），反复论证给最仔细可落地方案
- 判断前端模块存在性必须同时检查 `views/` 根目录 + `components/` 子目录
- 文档同步：功能变更后同步更新需求文档；死代码立即删除，不留 DEPRECATED/fallback 注释
- 复杂重构先做 spec 三件套（体系化、精准、可回滚，"全部改完再跑一次测试"）
- 避免折中方案，要"根本解决"
- **彻底解决问题不调整错误呈现**：错误绝不"换个参数避开"，必须复现 + 定位根因 + 修主代码 + 加防御测试
- **文档标 ⚠️ 必须配套修复**：标注前评估能否本轮修复，可修则一次修完代码+文档+测试+memory；设计选择类用中性 📌 替代
- 完整复盘要诚实暴露问题不粉饰；PDCA 迭代模式：建议→spec→实施→复盘；5 角色轮转（合伙人/项目经理/质控/审计助理/EQCR）
- **改动前先 spec 三件律**：>500 行文件 / 涉及 3+ 组件 / 跨前后端 = 必须先写 spec 再动手
- **改动后必 Playwright 实测铁律**：`getDiagnostics` 通过 ≠ 运行时无错；声称"修复完成"前必须有 Playwright 证据，否则用"代码已改但未实测"措辞
- **触类旁通 grep 铁律**：发现一处反模式立即 grep 全仓找同类一次修完，修完强制问"项目里还有同类问题吗"
- 目标并发规模 6000 人
- 底稿编码：致同 2025 修订版（`backend/data/wp_account_mapping.json` 206 条 v2025-R5）
- 审计循环代号：A=报表/调整 / B=控制了解 / C=控制测试 / D=销售收入 / E=货币资金 / F=采购存货 / G=投资 / H=固定资产+在建工程+使用权资产+租赁负债 / I=无形资产+商誉+开发支出 / J=职工薪酬+股份支付 / K=管理 / L=筹资 / M=股东权益 / N=税费 / S=专项程序

## UI 视觉偏好（详 #conventions）

- 表格列宽充足不折行，数字列 `.gt-amt`，所有 el-table 必须 `border + resizable`，固定宽度优先 `min-width`
- 表格选中行 ≥14% 透明度 + 左 3px 紫竖线 + hover 浅反馈
- 工具栏按钮合并到 Tab 栏右侧（不独占行）；简单 CRUD 不用 GtPageHeader 紫渐变
- 所有表格统一 el-table（底稿编辑器仍 Univer，不引入 AG Grid）
- 标准分页非"加载更多"；四表联查支持全屏+行选择+右键菜单
- 溯源/穿透跳转支持 Backspace 返回（DefaultLayout `initGlobalBackspace`）
- 表格编辑支持查看/编辑模式切换；复制按钮命名"复制整表" vs 右键"复制选中区域"
- 详细规则（GtToolbar slot 契约 / 全屏三件套 / Teleport 脱离 transform 祖先 / el-table flex 高度 / Tab 栏同行工具按钮 / Dashboard 视觉 / 借贷成对展示 等 17 条）→ 详见 `#conventions`「UI 视觉偏好补充」
- **底稿模块 Tab 顺序**（2026-05-24）：生命周期→委派矩阵→列表→工作台→看板→依赖图→手册（生命周期第一位=先裁剪程序）；树默认折叠
- **程序裁剪页面**（2026-05-24 重写）：`ProcedureTrimming.vue` 三大功能 = 一键智能裁剪 / 自定义裁剪 / 自定义新增程序；`chain_orchestrator` 步骤 5b 尊重裁剪 + 步骤 5c 加入自定义程序

## 环境配置

- Python 3.12（.venv），Docker 28.3.3，PG 16（188 表），Redis 6379；后端 9980 / 前端 3030 / vLLM 8100
- 测试用户 admin/admin123（role=admin）；git 分支 fea2e-business-flow（HEAD）
- **本地 Docker 容器名**（2026-05-24）：`audit-redis`（端口 6380→6379）/ `audit-postgres` (5432) / `audit-metabase` (3000)；命令 `docker exec audit-redis redis-cli ping`
- **数据库初始化**：`python backend/scripts/init_tables.py` + `python backend/scripts/create_admin.py`
- **4 项目底稿数据已就位**（2026-05-25）：`python backen year=..., force=True)`
- **scripts 命名规约**：`_` 前缀 = 一次性脚本（用完即删），无前缀 = 正式工具
- **docs 目录结构**（2026-05-23 重组）：8 子目录（adr / architecture / deployment / reference / frontend / operations / proposals / templates）+ 顶层 README.md 索引；新增文档按子目录归类
- **双 storage 目录职责**：仓库根 `storage/projects/{UUID}/workpapers/` = 底稿文件；`backend/storage/{knowledge,projects,users,ledger_uploads}/` = 附件/上传；两边 gitignored 但代码 hardcode
ts 353 / composables 91
- **数据规模**：模板 456 / cross_wp_ref 400 / prefill 1035 cells / VR 114 / Spec 70+
- **新增依赖**：locust / marked + dompurify / Storybook 8.6.14 / xlsx-js-style / decimal.js / python-docx / prometheus_client / **PyYAML**（workpaper-html-renderer 引入）/ **fast-check v4.8.0**（前端 PBT）；外部 LibreOffice（4 路径 fallback）
- **文档/表格生成职责边界**（2026-05-23）：Univer Sheets = 底稿在线编辑 / Univer Docs+TipTap+textarea 三级降级 /楷体_GB2312/宋体/Arial Narrow）必装
- **Dashboard 视觉规约**（2026-05-23）：5 dashboard 统一 `GtPageHeader variant="banner"` + dark 主题；DashboardViewSwitcher 共享组件挂 banner #actions slot
- **查询入口统一**（2026-05-23）：用户可见名称 = 「高级查询」；CustomQueryDialog 内 el-tabs 分两层「业务视图」+「高级构建器」（仅 admin/manager/partner）
- **高级查询白名单覆盖 9 维度**（2026-05-23）：TABLE_WHITELIST 16 张表全维度入栏；users 显式排除 hashed_password；JOIN_WHITELIST 以 projects 为中心辐射

## 任务状态

### 全部已完成 spec ✅

11 审计循环（D~N，548/548）/ phase 1~7（239/239）/ phase 8（116 tests）/ proposal-remaining-18（30/30）/ k-admin-cycle-post-review-fix / partner-dashboard / procedure-trimming / role-view-switching / 角色体系治理（145 vitest）/ e2e-business-flow（58/58）/ template-library-coordination（64/64）/ audit-chain-generation（101/101）/ enterprise-linkage（56/56）/ **ledger-import-view-refactor（243/243）** / **advanced-query-enhancements-p1p2（212 tests）** / **workpaper-html-renderer（40/40 tasks，413 tests，2026-05-26 commits fd95ae1+46fa4b5+8fd847d）** —— 详见 INDEX.md。

### workpaper-html-renderer 关键沉淀（详见 #dev-history）

- 1788 单体真底稿（A/B/C/D/E 共 1346 sheet）从 Univer 切到 HTML，F/G 558 sheet 保留 Univer
- 9 类 componentType 路由 + 禁止 Univer 兜底铁律 + 11 命名空间 4 层级跳转
- 方案 C openpyxl 加载致同模板 + 4 路径写入策略 1:1 还原
- 9 PBT 属性测试覆盖（hypothesis + fast-check 双框架）
- 性能基准全部 ×18+ 余量（HTML 冷启动 27.7ms / xlsx 导出 275.7ms / classification 1.2μs）
- 详细技术决策、新依赖（PyYAML）、测试模式（fake-timers / 子组件 stub / FakeDB）已下沉到 #dev-history

### 真正待办（外部依赖）

- LLM 真实接入：phase3 UAT-3 + K-1 / 6 stub 引擎（H/I/G/K/J/N，`settings.WP_AI_SERVICE_ENABLED` 一键切换）
- 6000 并发压测：phase3 UAT-5（需真 PG 大数据量 + Locust）
- W-3 钉集成（外部对接）
- Sentinel failover 真实验证：phase4 UAT-8
- WorkpaperEditor 瘦身（当前 2631 行，目标 ≤1000）：useEditorActions let→ref + template dialog 配置驱动 + 删冗余别名
- **附注模块改进 v2.0 实施**（spec 文档已入库 commit ccf92da `docs/DISCLOSURE_NOTE_IMPROVEMENT_PROPOSAL.md`）：6 Sprint / 18.5-19.5 人天 / 6 项 CI 卡点；致同 Word 排版规范单一真源（21 项 + 11 项验收断言）；渐进兼容现有 `_cell_modes` 行级 dict + 三式联动 + DSL（=TB/=ROW/=PRIOR）+ 4 套用户编辑入口;含 Sprint 1.5 公式 DSL 沉淀；**spec 三件套 `.kiro/specs/disclosure-note-full-revamp/` 已起草完成**（commit 81c0db1，2026-05-26）；**spec v1.1 已修订**（commit 982efea）：DSL 函数名 + is_stale 字段已存在 + useNoteStale 标新建 等 P0/P1/P2 共 12 处；**Sprint 0 全完成**（commit 6b6731c，2026-05-27）：Task 0.1 模板治理（791 处空 header 删除 / 4307 row 自动打 row_type，启发式 + 幂等）+ Task 0.2 数据迁移幂等脚本（18 单测 + 真 PG 端到端验证 + manual_value 备份机制 R1.3 验收 11）+ Task 0.3 Word 多表（前序 dbf557d）+ 0.4 验收（pytest 28/28 ✅）；**Sprint 1 进度 4/8**（2026-05-27 进行中）：1.2 列语义引擎完成（25 语义/54 单测，零依赖纯函数模块 `note_column_semantics.py`，dict 顺序敏感优先级链 + `=` 前缀 fast-path + manual_text 兜底）+ 1.1 binding 自动生成器完成（4101 cells，SOE 39.9%/Listed 44.9%；747 manual placeholder 待 P-1 审计师补 50+ 变动表；7 source / 3 mode CI 卡点 15 单测）+ 1.5 三态合并 D1 完成（`note_cell_merge.py` 纯函数 deepcopy + label 对齐+index 兜底+`_legacy_row` 标记 + update_note_values/generate_notes 接入 + 25 单测含 hypothesis PBT 4 不变量 max_examples=80）；剩余 1.3+1.4 引擎 binding 分支与 7 source 解析器、1.6/1.7/1.8、+ 前置 P-1/P-2/P-3 外部依赖
- **scripts 命名实例**（2026-05-27）：本 spec 系列工具脚本统一无 `_` 前缀（`cleanup_note_templates.py` / `migrate_disclosure_notes_to_v2.py` / `generate_note_template_bindings.py` / 对应 report.txt），因均幂等可重复跑（不是用完即删的一次性）；CI 卡点单测放 `backend/tests/services/test_note_*` 命名空间
- **note_word_exporter.py 已有 Sprint 6 完整致同样式实现**（grep 实测）：致同标准格式（页边距/字体/字号/段前段后/三线表/表头加粗/Arial Narrow 数字/页码/书签/章节中文编号"一、（一）1."三级）已运行；本 spec **唯一缺的就是多表 `_tables` 数组渲染**（已在 Task 0.3 修复）；后续 Sprint 2 R5.2 21 项排版规范大部分已落地，仅需补 GTNote* 命名空间 + fill_multi_header 多层表头 + GTNoteFormulaCell 公式标记 + 11 项视觉断言测试
- **note_formula_generator.py 公式存储已支持 `table_data._formulas` 顶层 dict**（grep 实测，design D4 沉淀位置正确）：key 格式 `row_idx:col_idx`，value 含 type/expression/description/category/source；DSL 函数 5 个：TB/WP/REPORT/cell/SUM；本 spec Sprint 1.5 仅新建 PRIOR/AGING 两个
- **附注 spec 三件套复盘发现 7 处事实硬错误 + 5 处一致性问题**（2026-05-26，待修订）：
  - **真实 DSL 函数清单（grep 实测）**：`note_formula_generator.py` 入口函数实际叫 **`generate_formulas_for_table`**（不是 spec 写的 `execute_note_formulas`）；真实 DSL 5 个 = `TB(account, period)` / `WP(wp_code, sheet, cell)` / `REPORT(row_code, period)` / `cell(row, col)` / `SUM(start:end, col)`；**虚构的 `=ROW(R3, "C2")` 和 `=PRIOR()` 不存在**（spec 凭印象写）；新增的 `=PRIOR / =AGING` 是本 spec Sprint 1.5 新建（不是"已有"）
  - **DisclosureNote.is_stale 字段已存在**（F46/Sprint 7.22 commit 已加）+ `event_handlers._mark_downstream_stale_on_rollback` 已订阅 `LEDGER_DATASET_ROLLED_BACK`；spec R2.1 应描述为"扩展现有 stale 机制 + 补 3 个新事件订阅"，不是从零开始
  - **`useLinkageEvents` composable 不存在**（grep 0 命中），spec design D6 引用错误，应明确为新建 `useNoteStale.ts`
  - **NoteTrimService 已有 5 方法**（get_sections/save_trim/get_trim_scheme/resolve_template_type/_init_from_template），本 spec 仅新增 `auto_trim`
  - 一致性问题：requirements 头部"32 验收标准"实际 59；README "~30 验收 / ~35 任务"实际 59/47；CI 卡点 README/design 列 6 项 tasks 列 8 项（缺前置+收尾）；tasks 3.7 `test_auto_trim.py` 文件名应改 `test_note_trim_service_auto.py` 与项目命名一致
- **vLLM / httpx 链路 3 个待修复 bug**（spec 已沉淀到本 memory，待动手）：
  - **httpx 系统代理陷阱**：Windows Clash 类系统代理（127.0.0.1:7897）让 `httpx.AsyncClient()` 默认读取代理把 localhost 请求路由到代理返回 502；修复 = 创建 client 时显式 `mounts={}, trust_env=False`；需修 4 文件：`llm_client.py`（_sync/_stream_completion）/ `ai_service.py`（_get_ollama_client + _get_llm_client + _get_chromadb_client）/ `availability_fallback_service.py`（check_llm_available）/ `routers/system_settings.py`（check_url）
  - **vLLM `chat_template_kwargs` 必须 payload 顶层**：嵌套 `extra_body.chat_template_kwargs` 被 vLLM 静默忽略，`enable_thinking=False` 不生效导致 content=None reasoning 有值；`llm_client.py:107` 改顶层 `"chat_template_kwargs": {"enable_thinking": settings.LLM_ENABLE_THINKING}`
  - **LLM thinking content=None 处理**：finish_reason=length 时返回"思考超 token，请简化提问或增大 max_tokens"，**禁止**回退到 reasoning 字段；`llm_client.py:_sync_completion` 需补此分支

## 关键引用指南

- 详细技术事实 / 端点速查 / PG schema / spec 历史详细 → `#dev-history` grep 关键词
- 项目架构 / 系统规模 / 数据流 → `#architecture`
- 编码规范 / UI 视觉补充 / 操作铁律 / Spec 工作流 / PG 运维 / 批量入库 → `#conventions`
- spec 状态总览 → `.kiro/specs/INDEX.md`

## 操作铁律（标题级，详见 #conventions）

- **彻底解决不绕开**：错误必须复现+根因+修主代码+防御测试
- **三层一致校验**：DB 迁移 + ORM `Mapped[]` + service 方法，任一缺失即伪绿
- **可复用脚本沉淀**：批量入库/UAT/迁移工具放 `backend/scripts/{name}.py` 配 docstring + 多场景
- **PG 运维**：SET 不支持绑定参数（用 set_config）/ superuser bypass RLS / CONCURRENTLY 必须 asyncpg raw conn + lock_timeout
- **router_registry 必查铁律**：新建 router 文件后必须在 `backend/app/router_registry/{group}.py` 注册，否则 endpoint 写好但前端 404
- **WpFileStatus 完成语义**：「底稿已完成」= `status in (review_passed, archived)`，不要猜不存在的枚举
- **临时文件不进 commit**：commit-msg.txt 必须 `git rm --cached` 清掉；优选 `git commit --% -m "..."` stop-parsing token
- **agent 调 service 优于 Playwright UI**：大文件入库直调 ledger_import 管线快 10x
- **历史档案不回填修改**：dev-history.md / spec/tasks.md 等是 append-only 审计轨迹，目录重组时不回填旧路径
- **vue-tsc 类型债务清理 SOP**：mitt Events 类型表必须显式补 key；SyncEventPayload 用 escape hatch；FUniver/xlsx SDK 用 `(api as any)` cast
- **Vue setup const 声明顺序铁律**（2026-05-25）：`const X = useY(..., Z)` 引用的 Z 必须在 X 之前已定义；典型实例 = WorkpaperEditor commit 79f7936 把 6 个 cycle composable 实例化放在 cycleDialogs 之前触发 ReferenceError；判定 = const 链式依赖必须按拓扑顺序写
- **顶层 v-if 守卫拦 init 死锁铁律**：依赖 template ref 触发 init 的组件不能加顶层 `v-if="loading"` 守卫，改 overlay 模式（容器永远渲染 + 内部蒙层）
- **useWpDetailGuard 三态默认接入铁律**（2026-05-25）：依赖 wpId 的视图必须 `useWpDetailGuard(wpId)` 三态（loading/error/ready），不允许直接 `goBack()` 跳转处理异常
- **append-to-body :deep() 失效铁律**：el-dialog/el-drawer/Teleport 内容到 body 下脱离组件作用域，`<style scoped>` 的 `:deep()` 选不到，需独立全局 `<style>` 块
- **前端硬编码假数据铁律**：UI 中的"演示数据"在产品成熟阶段全部移除改 API 驱动；任何 wp_code 维度可视化必须根据 `props.wpCode` 动态获取
- **apiProxy 单层解构铁律**：`api.get/post` 已直接返回业务数据，调用方禁止再 `const { data } = await api.X(...)` 二次解构
- **真实 PG 诊断铁律**：用户截图问题三步走 = ①连真 PG SELECT 看数据 ②对照 service 代码追路径 ③定位真因再动手
- **后台 worker 心跳完整性铁律**：`event_cascade_health_service._WORKER_NAMES` 4 worker 缺一即 degraded；DegradedBanner 异常先 `docker exec audit-redis redis-cli keys "worker_heartbeat:*"` 看真实心跳
- **year 必传参数三级 fallback 铁律**：项目维度业务接口前端取 year = `projectStore.year || Number(route.query.year) || new Date().getFullYear() - 1`，apiProxy 第三参 `{ params: { year } }`
- **PowerShell**：写中文/emoji 用 fsWrite；多 -m 长 commit 含 ()/→/中文冒号必须 `git commit --% -m "..."` stop-parsing token；`commit-msg.txt` 临时文件方案不进 commit 是底线
- **SQLite 测试 set_rls_context 兼容**：mock `app.deps.set_rls_context` 绕开（admin 路径仍会触发）
- **FastAPI dep_overrides 闭包陷阱**：`require_project_access("readonly")` 工厂每次返新闭包，dep_overrides 不命中；正确做法 = 仅 override `get_current_user` + `get_db`
