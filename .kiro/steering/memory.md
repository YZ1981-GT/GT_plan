---
inclusion: always
---

# 持久记忆

每次对话自动加载。详见 `#architecture` / `#conventions` / `#dev-history`。
保持本文件 ≤ 100 行：完成事项 → dev-history，技术决策 → architecture，规范/铁律 → conventions。

## 用户偏好

- 语言中文；本地优先轻量方案；启动 `start-dev.bat`（后端 9980 + 前端 3030）；打包 `build_exe.py`（PyInstaller，不要 .bat）
- **输出控制**：分步输出/修改，大改动拆小批次；不一次出过多内容
- 功能收敛：停加新功能，核心 6-8 页做到极致，空壳标 developing
- 前后端必须联动；删除二次确认 + 先进回收站；一次性脚本用完即删
- git 提交不分多区，单 commit 提交所有变更
- 提建议前先验证（不引用过时记录），反复论证给最仔细可落地方案
- 判断前端模块存在性必须同时检查 `views/` 根目录 + `components/` 子目录
- 文档同步：功能变更后同步更新需求文档
- 死代码立即删除，不留 DEPRECATED/fallback 注释
- 复杂重构先做 spec 三件套（体系化、精准、可回滚，"全部改完再跑一次测试"）
- 避免折中方案，要"根本解决"
- **彻底解决问题不调整错误呈现**：错误绝不"换个参数避开"，必须复现 + 定位根因 + 修主代码 + 加防御测试
- **文档标 ⚠️ 必须配套修复**：标注前评估能否本轮修复，可修则一次修完代码+文档+测试+memory；设计选择类用中性 📌 替代
- 完整复盘要诚实暴露问题不粉饰
- PDCA 迭代模式：建议→spec 三件套→实施→复盘→新需求；5 角色轮转（合伙人/项目经理/质控/审计助理/EQCR）
- 目标并发规模 6000 人
- 底稿编码：致同 2025 修订版 D/F/K/N 循环（`backend/data/wp_account_mapping.json` 206 条 v2025-R5）
- 审计循环代号：A=报表/调整 / B=控制了解 / C=控制测试 / D=销售收入 / E=货币资金 / F=采购存货 / G=投资 / H=固定资产+在建工程+使用权资产+租赁负债 / I=无形资产+商誉+开发支出 / J=职工薪酬+股份支付 / K=管理 / L=筹资 / M=股东权益 / N=税费 / S=专项程序

## UI 视觉偏好（详 #conventions）

- 表格列宽充足不折行不省略号；数字列统一 `.gt-amt`
- 表格选中行 ≥14% 透明度 + 左 3px 紫竖线 + hover 浅反馈
- 工具栏按钮合并到 Tab 栏右侧（不独占行）；简单 CRUD 不用 GtPageHeader 紫渐变
- 所有表格统一 el-table（底稿编辑器仍 Univer，不引入 AG Grid）
- 标准分页非"加载更多"；四表联查支持全屏+行选择+右键菜单
- 溯源/穿透跳转支持 Backspace 返回（DefaultLayout `initGlobalBackspace`）
- 表格编辑支持查看/编辑模式切换；复制按钮命名"复制整表" vs 右键"复制选中区域"

## 环境配置

- Python 3.12（.venv），Docker 28.3.3，PG 16（188 表），Redis 6379；后端 9980 / 前端 3030 / vLLM 8100
- 测试用户 admin/admin123（role=admin）；git 分支 feature/e2e-business-flow（HEAD）
- **数据库初始化命令**（2026-05-23 重命名后）：`python backend/scripts/init_tables.py` + `python backend/scripts/create_admin.py`（旧 `_init_tables.py` / `_create_admin.py` 已重命名，文档/spec 引用已同步）
- **scripts 命名规约**：`_` 前缀 = 一次性脚本（用完即删），无前缀 = 正式工具（保留可复用）；本轮清理 backend/scripts 65→49 / scripts/ 19→14
- **docs 目录新结构**（2026-05-23 重组）：从平铺 29 文件 → 8 子目录（`adr/` / `architecture/` / `deployment/` / `reference/` / `frontend/` / `operations/` / `proposals/` / `templates/`）+ 顶层 `README.md` 索引 + `requirements.md`；新增文档必须按子目录归类不要平铺；文件名英文小写连字符；活跃代码引用 14 处已同步更新
- **双 storage 目录职责**（2026-05-23 厘清）：仓库根 `storage/projects/{UUID}/workpapers/` = 底稿文件落地（DB `working_papers.file_path` 引用）+ `storage/consume` 是 docker-compose Paperless 挂载点；`backend/storage/{knowledge,projects,users,ledger_uploads}/` = 附件/知识库/上传文件落地；两边都 gitignored 但代码 hardcode 路径
- **空目录清理判定原则**：纯安装残骸（如 univer-server）= 直接删；运行时数据目录（storage 下 UUID 目录）即使空也不能简单删，必须先比对 DB 引用作"数据维护"，建议走 `cleanup_orphan_storage_dirs.py` dry-run 工具 + 回收站
- **程序规模**：后端 routers 271 / services 345 / models 58 / workers 12 / tests 464 / Alembic 61 + 28 SQL；前端 views 99 / components 353 / composables 81 / stores 9 / services 37 / utils 39
- **数据规模**：模板 456 / cross_wp_ref 400 / prefill 1035 cells / VR 114 条 / Spec 70
- **新增依赖（Phase 3+）**：locust / marked + dompurify / Storybook 8.6.14 / xlsx-js-style / decimal.js / python-docx / prometheus_client；外部 LibreOffice（4 路径 fallback，本地已装 2026-05-23）
- **文档/表格生成职责边界**（2026-05-23 厘清，禁止越界）：Univer Sheets = 底稿在线编辑（纯前端） / Univer Docs + TipTap + textarea 三级降级 = WorkpaperWordEditor 看 docx / python-docx = 程序化生成附注/EQCR/年报（内容可控可单测） / LibreOffice = 仅承担 docx+xlsx → PDF 转换（weasyprint 优先 → LibreOffice 降级，office_preview + archive_pdf_generators 共享 `_find_libreoffice`）；LibreOffice 不替换 python-docx 不接入编辑回环；6000 并发场景需队列化 + 信号量保护避免 soffice 被打挂；中文字体（仿宋/楷体_GB2312/宋体/Arial Narrow）必须装齐否则 PDF 出方块
- **底稿右栏附件 Tab**（2026-05-23 接入 AT-2）：`WorkpaperSidePanel` 附件 Tab = `AttachmentTabPanel`（列表 + 拖拽上传 + 点击预览） / `AttachmentPreviewDrawer` Office 文件走 `attachments.previewPdf` 端点 LibreOffice 转 PDF iframe，503 时降级下载提示（`officePreview.health` 探测结果模块级缓存避免重复打）；模板库 `WpTemplateDetail` 主文件区已接入同款管线（`/wp-templates/{wp_code}/preview-pdf` + drawer iframe + health 缓存）
- **Dashboard 视觉规约**（2026-05-23 沉淀）：4 个 dashboard（Dashboard / ManagerDashboard / PartnerDashboard / EqcrWorkbench / EqcrMetrics）统一 `GtPageHeader variant="banner"` + icon + dark 主题；`DashboardViewSwitcher` 共享组件挂 banner #actions slot 监听 route.path 自动同步；刷新按钮做成 row1 默认 slot 内的圆形小图标（`.gt-header-refresh-wrap` margin-left:auto）+ 可选下方 "X 前" 时间标；filter 类 radio 在紫色 banner 用 dark 风格（半透白底白字 / 选中白底紫字）；表格列必须 `min-width` 不用 `width` + 加 `resizable` 让用户拖宽；多按钮操作列用 `display: inline-flex; gap:8px; white-space:nowrap` 防竖排折行；KPI 数字字段用 `?? 0` 或空值兜底成 `—` 避免 `undefined%`；横幅/告警卡的「本次会话关闭」用组件级 `ref = true` 默认值（不用 sessionStorage） + `position: absolute; top:8px; right:8px` 关闭 X 按钮，组件 unmount 即重置语义 = 切换路由再回来重新提示
- **Backspace 返回栈使用规约**（2026-05-23 沉淀）：`initGlobalBackspace` 仅注册全局监听器，不会自动记录来源；任何 `router.push()` 跳转**必须显式调用** `useNavigationStack().push({ source_view, query })` 把当前位置入栈，否则按 Backspace 不会返回；推荐在页面级定义 `recordOrigin()` 包装函数集中调用（见 ManagerDashboard / PartnerDashboard 实现）；判定 = 跳转后用户期望按 Backspace 能回来 → 必须 push
- **查询入口统一**（2026-05-23 沉淀）：用户可见名称 = 「高级查询」（侧栏 / 快捷操作 / 弹窗标题 / 模板库 Tab / CustomQuery 独立页 / 导出文件名）；CustomQueryDialog 内部用 el-tabs 分两层 — 「业务视图」（CustomQueryDialog 原内容，预设数据源 + 转置导出，全员）/「高级构建器」（嵌入 AdvancedQueryBuilder 加 `embedded` prop，表+字段+多条件+SQL 预览，仅 admin/manager/partner，按 effectiveRole v-if 显示）；触发模式 = `eventBus.emit('open-custom-query', { tab? })` ThreeColumnLayout 监听打开 + 设 initialTab；代码内部 `customQuery` const / `/api/custom-query/*` 路径 / `customQuery` 路由保持不动（仅文案统一，避免内部大重构）
- **高级查询白名单覆盖 9 维度**（2026-05-23 扩展）：query_builder TABLE_WHITELIST 从 11 张 → 16 张表，全维度入栏 — 项目 projects / 单位 (projects.client_name+parent+ultimate) / 报表 (report_config+report_line_mapping) / 附注 disclosure_notes / 底稿 (working_paper+wp_index) / 账簿 (tb_balance+tb_ledger+account_chart+trial_balance+adjustments) / 人员 (staff_members+users) / 工时 work_hours / 重要性 materiality；users 白名单**显式排除 hashed_password** 等敏感字段；JOIN_WHITELIST 以 projects 为中心辐射所有业务表 + 人员↔工时↔项目三方互连
- **CustomQueryDialog 业务视图 P0-P3 收尾**（2026-05-23 沉淀）：左树↔右下拉双向联动 — `clickedCategory` ref 记录大类 key，`sourceOptions` 改 computed 从 `indicatorTree` 扁平化派生（叶子带 parentKey，树未加载时 `STATIC_SOURCES` 兜底），点大类自动选第一子项 + 设 category，点叶子反查父大类同步 `clickedCategory`，「重置筛选」`RefreshLeft` 图标按钮清空回到全部；树折叠默认 `[]` / 项目+年度选择器（输入号控件）/ 上下文 chip / 友好空态 / 全屏切换 `el-dialog :fullscreen` + 自定义 header（FullScreen/Aim/Close）/ 导出文件名 `${projName}_${srcName}_${year}.xlsx` / >500 行导出二次确认 / sessionStorage 缓存 indicators / `goToFullCustomQuery` 跳独立页支持模板保存
- **高级查询左树按项目动态联动**（2026-05-23 沉淀）：`/api/custom-query/indicators` 接 `project_id` query — 读 `Project.template_type` (soe/listed) + `report_scope` (standalone/consolidated) 推 `applicable_standard` 三档（`soe_standalone` / `listed_standalone` / `listed_consolidated`，soe 暂无 consolidated）；报表树 6 张对齐 `report_config_seed.json` 实际 report_type — `balance_sheet / income_statement / cash_flow_statement / cash_flow_supplement / equity_statement / impairment_provision`，其中 `impairment_provision` 仅 soe 有 seed 数据，listed 项目自动隐藏避免空查询；附注大类→明细两层从 `backend/data/consol_note_sections_{soe,listed}.json` 按 `parent_section` 分组（91 大类，每个下含「五-1-1 货币资金」式明细），叶子 key 形如 `disclosure_note:五-1-1`，后端 execute 路由 split 冒号注入 filters.section_id；**合并模块「🏢 合并范围」顶层节点**仅合并项目可见（`report_scope=consolidated` 或 `consol_scope` 有数据），从 `consol_scope` 按 distinct company_code 取最新年度，每家单位下挂 4 明细（科目余额 / 序时账 / 试算表（个体）/ 调整分录），叶子 key 形如 `consol_unit:S01:account_balance`，execute 路由 split 注入 `filters.company_code` 复用现有 `_query_account_balance/_query_ledger_entries/_query_trial_balance/_query_adjustments`；**底稿树 3 层结构**循环（D 销售收入）→ 主底稿（D2 应收账款 + 科目名）→ sheet 程序（按 step_sheet_mapping.json 真实 Excel sheet 名）— **sheet 全集权威源 = `backend/data/step_sheet_mapping.json`**（179 底稿 / 1040 sheet / 100% 覆盖，不要用 wp_account_mapping 推断 `wp_code-N` 形式 D2 只能拿到 4 个会严重不全），主底稿数据源双轨：传 `project_id` 走 `wp_index`（裁剪后），未传走 `wp_account_mapping.json` 全集 + step_sheet_mapping 补充（A~N+S 全 15 循环 184 主底稿 / 2503 sheet 节点）；sheet 叶子 key 形如 `workpaper:D2|审定表D2-1`（用 **`|` 分隔避免和命名空间 `:` 冲突**保留中文 sheet 名），execute 路由 split `|` 注入 `filters.sheet_name` 作为返回字段 echo（不参与 SQL WHERE，因 working_paper.parsed_data 的 sheet 维度需 JSONB 路径查询本接口暂不深入）；点 E1 同时带出 E1-1/E1-2 走精确+前缀模糊匹配；内嵌 `_CYCLE_NAMES` 字典（A=报表/调整 / B=控制了解 / C=控制测试 / D=销售收入 / E=货币资金 / F=采购存货 / G=投资 / H=固定资产+在建+使用权 / I=无形资产+商誉 / J=职工薪酬+股份支付 / K=管理 / L=筹资 / M=股东权益 / N=税费 / S=专项程序）；前端按 project_id 独立缓存 sessionStorage 键 `gt:custom-query:indicators-v{N}:{pid}`，切项目自动重拉，**树结构改动后升 v 号强制刷新旧缓存**（v1→v2→v3→v4→v5→v6 演进）；`allSources` computed 改递归 walk 支持 N 层嵌套（顶层/中间层/叶子三态），**每个叶子记录完整 `ancestorKeys` 路径**（从顶到自己），`sourceOptions` 按 `ancestorKeys.includes(clickedCategory)` 过滤而非仅顶层 parentKey 匹配（否则点 D2 主底稿下拉会显示全集 2503 sheet 而不是 D2 下 20 个），`onIndicatorClick` 大类/中间层节点直接 `clickedCategory = data.key` 不再反查顶层，叶子节点设为直接父节点（ancestorKeys 倒数第二）让下拉只显示同 sheet 范围；加 `findFirstLeaf` + `findTopCategoryOf` 工具让中间层点击也能反查顶层 category；判定 = 任何按项目模板差异化展示的树都走"项目维度查询参数 + 项目级缓存键 + 递归扁平化 + seed 对齐 + ancestorKeys 精确过滤"五件套
- **working_paper 表 schema 红线**（2026-05-23 沉淀，pre-existing bug 修复教训）：`working_paper` 表**无 year 列**（年度信息在 wizard_state JSONB 派生 / Project.audit_year），任何 `wp.year = :y` 过滤条件都永远报错；`wp_index` 真实字段是 `audit_cycle` 不是 `cycle`（与 procedure_models / workhour_entry_models 一致），写 SQL 必须用 `wi.audit_cycle`；判定 = 修底稿相关 SQL 时优先 `\d working_paper` + `\d wp_index` 核对真实字段，不要凭 ORM 类的属性名直接拼（ORM 字段名 vs 表列名差异通常出在历史命名调整后）
- **openpyxl 不支持 tzinfo**（2026-05-23 沉淀）：PG `timestamptz` 字段导出 Excel 时 openpyxl 抛 `TypeError: Excel does not support timezones in datetimes`；查询/报表导出工具必须在 cell value 转换层 `v.replace(tzinfo=None) if v.tzinfo is not None else v` 显式 strip（保留壁钟时间符合用户本地化预期）；判定 = 任何走 openpyxl 写 datetime 的导出端点都需此兜底
- **Project.audit_year 派生而非列**（2026-05-23 沉淀）：`audit_year` 不是 `Project` 表的真实列，而是 `_extract_project_audit_year(project)` 从 `wizard_state.steps.basic_info.data.audit_year` JSONB 路径派生；未走完向导的项目 = audit_year=null；前端 `listProjectsWithProgress` 已封装暴露；写 SQL 不能 `SELECT projects.audit_year`，要 JOIN wizard_state 或后端调 `_to_project_response`；建议项 = Alembic 加列 + 一次性回填脚本

## 任务状态

### 全部已完成 spec ✅

11 审计循环（D~N，548/548）/ phase 1~7（239/239）/ phase 8（116 tests）/ proposal-remaining-18（30/30）/ k-admin-cycle-post-review-fix / partner-dashboard / procedure-trimming / role-view-switching / 角色体系治理（145 vitest）/ e2e-business-flow（58/58）/ template-library-coordination（64/64）/ audit-chain-generation（101/101）/ enterprise-linkage（56/56）/ **ledger-import-view-refactor（243/243）** —— 详见 INDEX.md。

小迭代 v2（2026-05-22 完成，详 #dev-history）：S-3 v2 JOIN 白名单 + DT-3 枚举覆盖 + AT-3 KB 版本接入，67 tests passed。

### 真正待办（外部依赖）

- LLM 真实接入：phase3 UAT-3 + K-1 / 6 stub 引擎（H/I/G/K/J/N，`settings.WP_AI_SERVICE_ENABLED` 一键切换）
- 6000 并发压测：phase3 UAT-5（需真 PG 大数据量 + Locust）
- W-3 钉钉/企微集成（外部对接）
- Sentinel failover 真实验证：phase4 UAT-8
- 业务测试：合并模块需真实项目（技术 85%/业务 60%）

### 首页 UX 复盘已完成（2026-05-23 P0+P1+P2 全 11 项，3 commit ec4ae76 / 5a6eab4 / f6c7e0f）

- **修复要点**：`/api/staff/my/assignments` 404 改 `/api/projects/my/assignments` + 删 staff.myAssignments 死常量 / 顶栏 3 emoji EQCR 链接合并为 1 dropdown + emoji 全替换 element-plus icons / 删 KPI 卡假环比百分比 / 最近项目 3 列→5 列（项目名/年度/类型/阶段/创建）+ 表格/卡片视图切换
- **新增能力**：仪表盘 banner 角色视图 4 tab（我的/团队/项目/EQCR，按 effectiveRole 过滤路由分发） / 顶栏 Search 按钮 emit `open-global-search`（Ctrl+K 仍可用） / 侧栏工具 8 项加 4 分组小标题（📚知识/🤖AI/🔎查询/💬反馈，扁平不折叠）
- **遗留**：首页甘特视图（`Project` 模型 + `/api/projects` 需补 start_date/due_date/overall_progress/partner_name/manager_name 5 字段后接 ProjectGanttChart）；统计卡真实环比待接 statsTrend 端点

## 关键引用指南

- 详细技术事实 / 端点速查 / PG schema → `#dev-history` grep 关键词
- 项目架构 / 系统规模 / 数据流 → `#architecture`
- 编码规范 / UI 规范 / Spec 工作流 / PG 运维铁律 / 批量入库脚本 → `#conventions`
- spec 状态总览 → `.kiro/specs/INDEX.md`

## 操作铁律（标题级，详细规则见 #conventions）

- **彻底解决不绕开**：错误必须复现+根因+修主代码+防御测试
- **三层一致校验**：DB 迁移 + ORM `Mapped[]` + service 方法，任一缺失即伪绿（AT-3 实战教训）
- **可复用脚本沉淀**：批量入库/UAT/迁移类工具放 `backend/scripts/{name}.py`（非 `_{tmp}.py`）配 docstring + 多场景；判定 = 操作目标可能再发生即保留
- **PG 运维**：SET 不支持绑定参数（用 set_config）/ superuser bypass RLS / CONCURRENTLY 必须 asyncpg raw conn + lock_timeout / 失败留 _ccnew 残骸需先 cleanup
- **router_registry 必查铁律**（2026-05-23 沉淀）：新建 router 文件后必须在 `backend/app/router_registry/{system,collaboration,workpaper,...}.py` 对应分组 `from app.routers.X import router as X_router` + `include_router(X_router, ...)`；漏挂时 endpoint 写好但前端 404（如 independence.py / `/api/my/pending-independence` 漏挂事件）；判定 = `grep -r "from app.routers.NAME"` 在 router_registry 下找得到即 OK
- **WpFileStatus 完成语义**（2026-05-23 沉淀）：「底稿已完成」= `status in (review_passed, archived)`；不要猜 `locked / done / completed` 等不存在枚举值（PG 会爆 InvalidTextRepresentationError）；完整枚举见 `backend/app/models/workpaper_models.py::WpFileStatus`
- **临时文件不进 commit**（2026-05-23 沉淀）：写长 commit message 时若用 fsWrite 创建 `commit-msg.txt` 中转，必须 `git rm --cached commit-msg.txt` 后 `--amend` 清掉；更稳的做法 = 用 `git commit -m "..." -m "..."` 多 -m 拼接或反斜杠续行
- **SQLite 测试 set_rls_context 兼容**（2026-05-23 沉淀）：set_rls_context 调 PG 的 `set_config(...)` 在 SQLite in-memory 测试会爆 `no such function`；admin 路径走 require_project_access 仍会触发；测试侧 `patch("app.deps.set_rls_context", new=AsyncMock())` 绕开（不在 conftest 全局短路，按需测试 mock 保留生产语义）
- **FastAPI dep_overrides 闭包陷阱**（2026-05-23 沉淀）：`require_project_access("readonly")` 工厂每次返回新闭包，`app.dependency_overrides[require_project_access("readonly")]` 不会命中路由实际 Depends 对象；正确做法 = 仅 override `get_current_user` + `get_db`，让 admin 路径自身短路，配合上一条 mock set_rls_context 即可
- **PowerShell**：写中文/emoji 用 fsWrite 工具；`Out-File` 文件锁需先 Stop-Process powershell + 用 `cmd /c "... > log 2>&1"`；多 `-m` 长 commit message 含 `()` / `→` / 中文冒号会被 pwsh 当子表达式或 pathspec 错切，必须 `git commit --% -m "..." -m "..."` 用 stop-parsing token 把后续参数原样交给 git（`commit-msg.txt` 临时文件方案不进 commit 是底线，`--%` 是优选）
- **agent 调 service 优于 Playwright UI**：大文件入库直调 ledger_import 管线快 10x，Playwright 仅做前端可见性验证
- **历史档案不回填修改铁律**（2026-05-23 沉淀）：`.kiro/steering/dev-history.md` / `.kiro/specs/*/tasks.md` 等历史记录是 append-only 审计轨迹；做目录重组/路径迁移时**不回填**这些文档中的旧路径（保持时点准确性），只更新活跃代码 + 当前文档；判定边界 = "记录写入时该路径是真的吗" → 是即保留
- **vue-tsc 类型债务清理 SOP**（2026-05-23 沉淀，143→0 实战）：mitt `Events` 类型表是中央枢纽，新事件必须显式补 key（漏一个则订阅/发布两端都爆）；`SyncEventPayload` 扩展用 `[key: string]: any` escape hatch + `project_id` optional 兼容编辑锁/导出等带顶层自定义字段的 SSE 推送；spec test 引用的 composable 导出（如 `useEditTransition` / `EDIT_TRANSITION_MS` / `LockConflictInfo` / `transitioning`）必须真的实现并导出，不是占位；element-plus ElTag/ElBadge `type` 不接受 `''`，要用 `undefined` + 联合改具体字面量；el-radio-group `@change` 签名是 `(string|number|boolean|undefined)` 不能直接收窄到业务枚举，需在 handler 内 cast；el-dialog `@close` 是无参 `() => any`（`:before-close` 才有 `done` 参数，别混淆）；FUniver / xlsx SDK 有未对外暴露的方法（如 `createUnit`）用 `(api as any).method()` cast 避免阻塞编译；判定 = 任何"理论上对"但 vue-tsc 报错的位置都先看类型源头不要绕开 ts-ignore
