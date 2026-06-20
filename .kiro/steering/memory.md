---
inclusion: always
---

# 持久记忆

每次对话自动加载，**保持 ≤ 200 行**。完成事项明细 → `#dev-history`；技术决策 → `#architecture`；规范铁律 → `#conventions`；spec 状态 → `.kiro/specs/INDEX.md`。

## 用户偏好

- 语言中文；本地优先轻量方案；启动 `start-dev.bat`（后端 9980 + 前端 3030）；打包 `build_exe.py`（PyInstaller 不要 .bat）
- **输出分步但连续做完**；**任务标记不能假绿**；**彻底解决不绕开**
- **🔴 codegraph 优先于 grep（铁律）**：搜符号/查调用链/看影响面第一选择永远是 codegraph（77k 节点/157k 边）；**grep 仅用于**非符号文本
- **触类旁通**：发现一处反模式立即全仓找同类一次修完
- **改动前先 spec 三件套**（>500 行/3+组件/跨前后端）；**改动后必 Playwright 实测**
- **UI 全中文化**；**报表金额默认"元"**；**中文场景全链路不能崩**
- 功能收敛；git 单 commit；**push 前必先 fetch**；**协作走 PR 不直推 main**
- 目标并发 6000 人；底稿编码致同 2025 修订版（`wp_account_mapping.json`）
- 审计循环代号：A报表 B控制了解 C控制测试 D销售 E货币 F采购存货 G投资 H固定 I无形 J薪酬 K管理 L筹资 M权益 N税费 S专项

## 底稿开发铁律

- **风险导向审计**：B50风险→D~N程序表→A13评价错报，全链可追溯
- **componentType 选型**：结构化联动=d-form-table / 复杂Excel=OnlyOffice / 文档=word-template / 程序表=a-program-console
- **三表HTML渲染**：底稿目录+审定表+附注全走HTML，仅复杂公式/DCF/图表保留OnlyOffice
- **联动是核心价值**：ref_index chip跳转/弹窗+auto_data_source实时取数；孤立底稿=无价值
- **通用schema复用**：`{wp_code}-generic.yaml` + pattern matching
- **开发前必先逐sheet读取源xlsx/docx模板**：从 `backend/wp_templates/{cycle}/` 实物提取
- **导入导出支持三级**（单个/勾选批量/全部一键）
- **适用性自动判断**：`applicable_when` 控制可见性

## 环境配置

- Python 3.12 / Docker / PG 16 / Redis；后端 9980 / 前端 3030 / vLLM 8100；DB `audit_platform`
- **rtk 0.42.1**：CLI token 压缩代理（git/pytest/vitest/playwright/eslint/tsc/docker 加前缀）
- Docker：`audit-postgres`(5432)/`audit-redis`(6379)/`audit-metabase`(3000)/`audit-pgbouncer`(6432)
- **host→Docker 连接失败**=vpnkit 端口转发卡死，`docker restart` 即恢复
- **DB_DISABLE_SSL=True**；连接池 150 但 PG max_connections=200（已提）
- **前端唯一路径**：`audit-platform/frontend/`
- **codegraph v0.9.8**：`npx -y @colbymchenry/codegraph`，双机免改配置；hook 自动 sync
- **OnlyOffice 9.4.0**：JWT secret=`onlyoffice-dev-2026`（config.py+docker-compose+local.json 三处一致）
- **scripts 规约**：`_` 前缀=临时用完即删；`backend/scripts/` 分 8 子目录
- **部署v2.0**：瘦客户端(Electron)+内网全栈服务器(FastAPI+PG+Redis+vLLM+MinIO)
- **MinerU 装服务器端**；OCR 走异步任务队列

## 迁移与 PG schema

- MigrationRunner 运行时迁移（非 alembic）；V+R 配对；`IF NOT EXISTS`；**最高 V088**
- **✅ A1-12 核查表完整实现（2026-06-21）**：`_parse_a1_12` 解析器(单表格17×3) + 前端 `GtChecklistSection` 增强：`hasStandardRef`(false隐藏准则列) + `allowCustomItems`(true隐藏备注列+显示添加按钮) + 自定义条目可编辑(textarea click-to-edit) + `polishWithLLM` 选中文字调 `/ai-suggest` 润色(prompt=审计专业措辞) + `updateItemContent` 持久化。29 parser 测试全绿
：源码7文件+测试19文件统一改为 `from app.`；`_execute_*` 抽到 `note_validation_executors.py`；`_chat_history` 已删（历史改DB持久化）；V083/V084/V086 补齐 R 回滚文件。16699 测试零 collection error
- **🔴 真实列速查**：trial_balance=standard_account_code/unadjusted_amount/aje_adjustment/audited_amount/opening_balance；working_paper 无 wp_code（在 wp_index，JOIN wp_index_id）
- **recalc 铁律**：`tb_balance` 保留 v1 口径（借正贷负），`trial_balance` 必 v2 正数；只汇总叶子；损益取发生额
- **报表引擎**：统一从 trial_balance 取数，TB()/SUM_TB() 公式路径
- **契约测试**：`test_raw_sql_schema_contract`(表级)+`test_raw_sql_column_contract`(列级)

## 任务状态

### 🔵 进行中 spec：workpaper-account-multifile-aggregation（2026-06-21 重写，design-first）
- **目标**：科目底稿(D2=3 Excel)多文件聚合+前端格式修正(HTML优先)+底稿间联动+行业可扩展+用户自定义模板导出/导入
- **🔴 重写关键发现**：平台**已实施** `account_package_registry.json`+`account_package_registry_service.py`(pilot workpaper-account-package-d1-d2-pilot)，已声明 D2 全 14 sheet 来源/sheet_type，但 render-config **未消费它**→聚合没生效。**改为消费已有注册表，不重写扫描器**
- **🔴 前端格式铁律**：上版误用 univer 致空白。sheet_type→componentType 必 HTML 类：control_panel/procedure→a-program-console，audit_sheet/detail_table/analysis→audit-sheet(非univer)，disclosure→c-note-table，adjustment→d-form-table，conclusion→d-form-paragraph，目录→b-index。遵 memory「三表HTML，仅复杂公式/DCF/图表留OnlyOffice」
- **新增范围**：①行业维度(registry 加 industry 字段，项目>事务所>行业>通用优先级)②导出模板端点(xlsx/YAML含sheet_type+字段)③导入自定义(custom_account_packages 表+校验)④同名 sheet 内容哈希合并(用户铁律:比内容非比名)
- **真实模板**：D 循环 13 系列 169 底稿，底稿间索引号交叉引用(D0-1→D0-4→D0-5/6→D1/D2审定)，当前偏制造业需兼容他行业
- **5 Sprint/15任务/7验收门槛**，待执行
- **✅ 三件套复盘验证通过（2026-06-21）**：sheet_type→componentType 映射逐项核对全落在已注册 HTML 白名单（useWpRenderer.ts 9类+univer+skip）；analysis→audit-sheet 非 univer 是上版"显示不出来"根治点；registry 14 sheet 与 D收入模板库 D2 系列(15底稿)吻合
- **✅ Sprint 1 完成（2026-06-21，4任务+12测试全绿，零回归）**：新建 `wp_account_package_resolver.py`（`resolve_package_sheets` 消费 account_package_registry，D2 聚合 14 sheet→list[ClassificationResult]；`_SHEET_TYPE_TO_CLASS`→class_code_to_component 全落 `HTML_RENDERABLE_COMPONENTS` 白名单守卫，analysis→audit-sheet 非 univer；GT_Custom skip；无条目返回 None；忽略 mapping_status）；`ClassificationResult`+`RenderContext` 加 `source_files` 字段（为 Sprint2 多源合并铺路）；`get_render_config` Step4b 接入（命中替换 classifications/未命中零回归/异常降级）；回归 registry+summary 43 + render-config 冒烟 1102 全绿
- **✅ Sprint 2 完成（2026-06-21，3任务+13测试含PBT全绿，零回归）**：新建 `wp_multifile_sheet_merge.py`（`content_hash` 单元格值 md5+LRU(mtime入key)；`merge_or_dedup` 按内容哈希判重非比名/相同去重/不同合并；`merge_sheet_content` 多源纵向拼接+【来源：xxx】标识行，输出形状同 extract_grid）；`_c_note.py` source_files>1 调 merge_sheet_content 否则单源/全局回退；`_audit_sheet.py` 优先 source_files[0]；PBT 幂等(restrict 字符集避 openpyxl IllegalCharacter + tempfile 避 function-scoped fixture health check)；render-config 冒烟 1102 全绿
- **✅ Sprint 3 完成（2026-06-21，联动+9测试全绿，零回归）**：🔴关键修复——聚合审定表保存联动断裂。根因：聚合后审定表是父码(D2)底稿内的 sheet，走 `/save`(html_data) 端点**从不发 WORKPAPER_SAVED**，且回写 handler `_on_d_audit_determination_saved` 匹配子码 `^[D-N]\d+-1$`(D2-1) 非父码 D2。修=①`wp_account_package_resolver.extract_determination_wp_code` 从 sheet 名提子码("审定表D2-1"→"D2-1") ②`wp_html_save._maybe_publish_determination_writeback`：审定表 sheet 保存→实时 TB 取数算审定数(公式同前端 `current_unadjusted+(adj??sys_aje??0)+(reclass??sys_rje??0)`)→发 WORKPAPER_SAVED(子码+rows) 触发既有回写。四表库取数(7.x)/调整/披露(8.2/8.3)复用既有机制零改。test_account_package_linkage 9 passed；smoke+cycle 联动 1155 全绿
- **✅ Sprint 4 完成（2026-06-21，行业维度+自定义模板导出/导入，89测试全绿）**：registry 每 package 加 `industry:["通用"]`；迁移 V090/R090 `custom_account_packages` 表(scope/scope_id/wp_code/industry/package_json JSONB+唯一约束，已 apply 到 dev PG)；`custom_account_package_service`(export_package_template 导出 YAML 含 sheet_type 合法值+字段；validate_package_json 校验 wp_code/account_name/sheets/sheet_type 白名单+可渲染 HTML；parse_and_validate 剔除 `_` 辅助键；import_custom_package upsert；get_custom_package 项目>事务所优先级)；`resolve_package_sheets` 重构抽 `_build_results`，先查 custom 表(优先级)再读内置 registry；`account_packages.py` 加 `GET {wp_code}/export-template`+`POST import-template`(校验失败返回明确 errors 清单不静默)；test_custom_account_package 11+1pg_only(真 PG 往返:导入自定义 2 sheet 覆盖内置 14 验证优先级)全绿
- **✅ Sprint 5 完成（2026-06-21，前端+通用性+Playwright 实测，全绿）**：前端美化(displayWpName/GtBArchitectureTree 4阶段 上轮已做)；resolver `_build_results` 首位插合成「底稿目录」(B-目录→b-index) 供架构树 4 阶段导航(聚合替换 classifications 后仍有目录)；D4 营业收入补 registry 条目(14 sheet 全 HTML 验证)；test_account_package_summary D-cycle 数 2→3；smoke+cycle+D/E/F 回写 1348 全绿。**🟢 Playwright D2 三项目实测**：API 层 3 项目各 15 sheet 0 非HTML；首汽租车 UI 实测——标题"D2 应收账款"、15 tab 全渲染、底稿目录 b-index 4 阶段(计划4/审定1/实质7/披露2)、审定表D2-1 完整 48 行 HTML el-table(原值/坏账/净值/账龄/试算平衡/差异+审计说明结论)、附注披露 c-note 渲染 0 新错误(3 个 `/api/projects/{pid}` 404 是预存元数据接口问题与渲染无关)
- **✅ workpaper-account-multifile-aggregation 全部完成（5 Sprint/全任务/7验收门槛 V1-V7 全勾）**：科目底稿多文件聚合(D2=14sheet/D4=14sheet)+前端 HTML 格式选型+同名内容哈希合并+底稿间联动(审定→TB回写打通)+行业维度+自定义模板导出/导入(V090 表)。新增 4 service+2 端点+V090 迁移+5 测试文件(90 测试)，全程零回归。
- **✅ 聚合 UI 两问修复（2026-06-21，Playwright 实测 0 error）**：①顶部冗余"导出/导入"移除→GtWpRenderer 多 sheet 区加「🗂️ 切换底稿」el-popover(弹 GtBArchitectureTree 4 阶段树,navigation_rows 从 visibleSheets 直接构造排除 b-index,点节点 onJumpToSection 跳转+关弹窗)；WorkpaperEditor HTML 路径顶栏仅留 返回+code+科目名(univer 路径导出/导入不动)②**根因修复**:已软删项目底稿仍可打开→`get_render_config` Step1.5 加 `SELECT is_deleted FROM projects` 守卫,删除项目 404。首汽租车_2025(df5b8403)是已删项目我误测;存活 D2=重药控股安徽(0ec33ac9)/重庆和平药房(2aa00f57)。实测重药控股:标题"应收账款"/被审计单位正确显示"重药控股安徽_2025"/切换底稿树 4 阶段14卡/点审定表D2-1 跳转渲染 0 error;smoke 1102+GtBIndex 19 全绿
- **✅ 聚合 UI 二轮修复（2026-06-21，Playwright 实测）**：①切换按钮文字"切换底稿"→"切换"，emoji 图标 🗂️→element-plus `<Switch>` 矢量图标②**🔴程序控制台空白根因修复**：`_a_program.render` 用父码 wp_code(D2) 查 procedure_table 模板，但 `get_template("D2")=None`(只有 "D2A" 有模板 20 项)→程序表空。修=从 sheet 名正则提取**sheet 级编码**(D2A/D4A/D2-6)查模板+用 sheet 的 `source_files[0]` 读模板(非全局 template_path)。实测重药控股 D2A 从空白→20 条程序行(进度 0/20)，0 error
- **✅ 程序表子步骤二级明细（2026-06-21）**：后端 `_parse_sub_steps` 从 content 解析 `（N）...` 编号子步骤为 `sub_steps:[{no,text}]`，父行 program_desc 只保留概要；前端 `hasExpandContent` 含 sub_steps，展开区 ol 有序列表+虚线分隔(默认折叠,20 行全有展开箭头)。实测 D2A 第 1 行:5 项子步骤完整渲染。**铁律**：聚合程序表必须用 sheet 级编码(D2A 非 D2)查 procedure_table 模板
- **🔴 D2 registry 遗漏 9 sheet 已补（2026-06-21 核对模板目录）**：模板底稿目录声明但 registry 缺失=D0-1~D0-4/D0-6~D0-8(函证7个,source=D0)+D2-11(坏账转回)+D2-12(质押出售)(source=D2-6)。附注披露国企版与上市公司版共用一个 sheet 支持切换(不新增独立 sheet)。D0 函证 sheet 放入 D2 工作包展示+支持跳转到 D0 底稿
- **🔴 D2-C 科目结论删除+底稿目录分类修正（2026-06-21）**：①D2-C 是虚构 sheet(模板无独立结论tab，结论嵌审定表末尾 audit_sections)，已从 registry 删除 ②`classifyStage` 修正：仅 sheet 名含"程序表"的 a-program-console 归"审计计划"(D2A 1项)，函证(D0系列)/检查表(D2-6~D2-12)虽也是 a-program-console 但归"实质性程序"(19项)。**铁律**：函证是实质性测试手段≠审计计划
- **✅ 循环底稿目录隐藏聚合子码（2026-06-21）**：`build_cycle_workpapers` 从 registry 收集各 package primary 的子码(仅 `startsWith(primary)` 才隐藏)，过滤掉 D2-2/D2-3/D2-4/D2-5~D2-13 等。D0/D5/D6/D7 等独立 primary 保留不隐藏。**铁律**：隐藏规则=子码以其 primary_wp_code 开头才隐藏，不同 primary 的底稿永远保留
- **🔴 registry sheet_name 必须与 xlsx tab 名完全一致（2026-06-21 踩坑）**：不一致导致 extract_grid/extract_audit_rows 找不到 sheet→空白。修正4处(明细表D2-2/程序表D2A/D2-11/附注披露)。**铁律**：补 registry 条目前必先 `openpyxl.load_workbook().sheetnames` 核对真实 tab 名

### 🔵 进行中 spec：bad-debt-sheet-enhancement（2026-06-21，requirements-first）
- **目标**：坏账准备明细表(GtBadDebtSheet)功能增强=导出模板+导出数据+Excel导入(预览弹窗)+账龄段枚举字典弹窗(三年/五年/自定义+自动更新信用风险组合子行)
- **状态**：✅ 全部必做任务完成(5 Sprint/29测试全绿)，已 commit+push(`a22c3b8b`)
- **关键设计**：复用 BadDebtExportService(加 template_only)+新建 BadDebtImportService(parse→preview→commit 两阶段)+新建 AgingSegmentService(V091 aging_segments 表 wp_index_id 级唯一+JSONB 段列表+子行同步)+前端 ImportPreviewDialog+AgingDictionaryDialog
- **注意点**：导入跳过表头行需按分组表头检测数据起始行(勿硬编码R12)；拖拽排序需确认 vuedraggable 依赖；静态路径在 /{row_id} 之前

### 🔴 D2 聚合底稿 12 个空白 tab 待修复（2026-06-21 Playwright 扫描）
- **空白 a-program-console(9个)**：D0-2/D0-3/D0-4/D0-6/D0-8 + D2-6/D2-7/D2-8/D2-11/D2-12 — 这些底稿无 procedure_table 模板(`get_template`返回 None)，且 `extract_program_rows` 从 xlsx 提取也失败（sheet_name 找不到/结构不适合 program 行提取）
- **空白 audit-sheet(3个)**：D2-9/D2-10/D2-13 — analysis 类型映射到 audit-sheet，但 `extract_audit_rows_with_values_from_file` 在 xlsx 中用 registry sheet_name 找不到对应 sheet 或结构不匹配
- **根因分析**：这些底稿是**表格型检查表/测算表**，不适合用程序中控台(a-program-console)渲染——它们没有"序号/程序描述/认定/索引号"的程序行结构，而是**固定列头+数据行**的网格。正确做法=改 sheet_type 为 `audit_sheet`(表格型→audit-sheet) 或用 `c-note-table`(只读网格兜底)；同时需确认 xlsx 中的实际 sheet tab 名与 registry 一致
- **工作量**：逐个确认 12 个 xlsx sheet 的实际结构（程序行/网格/段落），调整 registry sheet_type + 验证提取成功。建议独立 spec 或调研后批量修复### ✅ 编制指导面板修复（2026-06-21，3 项，30 guidance 测试全绿）
- **ai_enabled 缺失**：后端 `wp_guidance_chat.py` GET guidance 端点无 `ai_enabled` 字段 → 前端 undefined→false→AI 对话 Tab 隐藏。修=注入 `guidance_response["ai_enabled"] = settings.WP_AI_SERVICE_ENABLED`
- **矛盾提示文案**：`GuidanceTabContent.vue:260` 写死"有疑问？切换到 AI 对话 Tab"不受开关控制。修=加 `v-if="guidanceStore.aiEnabled"`
- **A1 排版丑**：A1 不在 `_complexity.json` high/medium 列表→落 low→只显示 100 字截断纯文本。修=加入 high 列表；同时去掉 `_load_complexity_config` 的 lru_cache（文件极小每次读可忽略，避免改 JSON 后必须重启）
- **程序表样式丑**：`GtAProgramConsole` 用 `gt-compact-table`(24px 行高) 导致文字挤一坨。修=移除该 class，新增专属样式：表头淡紫#f3eef8+深紫字/38px 行高/数据行 36px+10px padding/斑马纹/hover 淡紫。影响所有 a-program-console 底稿（A1/A8/A9/A17/A30/B10 等），`gt-compact-table` 仅留给数字密集型表格(TB/科目表/报表)


### ✅ 多 sheet 底稿 override 压平修复（2026-06-21，🔴核心架构修复）
- **根因**：`get_render_config` 主循环 `ovr = _WP_CODE_OVERRIDE.get(wp_code); component_type = ovr if ovr else derive(cls)`——wp_code 级 override 对多 sheet 底稿（如 D2 含 11 sheet：底稿目录/程序表D2A/审定表/附注/明细表）一刀切压平成同一 componentType（d-form-table），导致目录/程序表/附注全变空白表单
- **修复**：①`derive_component_type` 加 `ignore_wp_code_override` 参数（默认 False 不改原行为，内部跳过 `_WP_CODE_OVERRIDE` 检查）②主循环检测 `_is_multi_sheet`（排除 GT_Custom 后真实 sheet>1），多 sheet 时 `derive_component_type(cls, ignore_wp_code_override=True)` 各 sheet 按 class_code 独立派生；单 sheet 保持 override 优先原行为
- **效果**：D2 各 sheet 正确派生 底稿目录→b-index/程序表D2A→a-program-console/审定表→audit-sheet/附注→c-note-table/坏账明细→bad-debt-sheet。D~I cycle 验证 561 passed，单 sheet 底稿(D1等)不受影响
- **🟢 Playwright 实测通过(2026-06-21)**：D2 应收账款底稿目录正确渲染——标题"应收账款"(displayWpName 去后缀)、底稿架构按 4 阶段分类汇总(①审计计划:程序表D2A ②科目审定:审定表 ③实质性程序:坏账/明细 ④披露与调整:4附注+调整分录)、本循环底稿目录 8 项可跳转。底稿渲染层 0 error(4 个 `/api/projects/{pid}` 404 是项目元数据接口预存问题，与渲染无关)
- **②目录空白补修(2026-06-21)**：`_b_index.py` 生成 navigation_rows 时 `derive_component_type(cls)` 也漏传 `ignore_wp_code_override`，多 sheet 场景每行 component_type 被压平成 d-form-table→架构树阶段分类错乱。已改为 `ignore_wp_code_override=_multi`
- **①标题规范化(2026-06-21)**：`WorkpaperEditor.vue` 加 `displayWpName` computed 去掉"审定表/及明细表/明细表"后缀显示纯科目名（多 sheet 科目底稿是整科目集合，标题应为科目名而非单 sheet 名）
- **🔴 b-index 脏数据复用 bug(2026-06-21 修)**：`_b_index.py` 原逻辑 `if ctx.sheet_html_data: return None`——只要有持久化数据就复用。但 override 压平时期"底稿目录" sheet 被当 d-form-table 保存了 `{rows,context,conclusion}` 脏数据(缺 navigation_rows)→策略复用脏数据→架构树空白。**同 wp_code 不同项目数据独立**(重药控股 0ec33ac9 空白 vs 首汽 df5b8403 正常=脏数据只在部分项目)。修=只当持久化数据含非空 `navigation_rows` 才复用，否则重新生成 + 合并保留旧 conclusion/context。3 项目 D2 全 navigation_rows=9，22 测试零回归
- **🔴 教训**：误删 43 条 D~I 父底稿 override 是错的——它们是 d-form-table 单 sheet 审定表，override 正确；真问题在多 sheet 派生逻辑而非 override 本身。已全部恢复
- **预存失败(非本次)**：`test_wp_classification_service.py` 30 项 + render_config_checklist/analytical_review 2 项 git stash 验证均预存（mock wp_code 命中 override / event loop closed），与本修复无关


### 底稿模块（A~S 全循环 2026-06-19 完成）
- **568 任务全绿**，31 个 spec 统一归档到 `_archive/10-A~S-workpaper-all-cycles-complete/`
- wp_account_mapping 900+ 条；_WP_CODE_OVERRIDE 550+ 条；procedure_table_templates 100+ 程序表；auto_data_resolvers 35+ 个
- **render-config 冒烟测试 1096 passed**（覆盖全部 wp_code+componentType+端点调用链）
- **各循环验证测试**：C(75+43)+D(63)+E(50)+F(124)+G(172)+H(144)+I(107)+J(126)+K(262)+L(110)+M(114)+N(87)+S(72) = **2457 passed**
- **event_handlers_cycle_linkage.py**：C/F/D~N 联动（~500行拆出），`register_cycle_linkage_handlers()` 注册5个handler
- **auto_data_resolvers.py**：28 passed（含 control_deficiency_count），异常返回 `{"_error":True}` 供前端区分

### 其他已完成模块
- 合并模块 4 Phase ✅（归档 `_archive/09-consolidation-phases/`）；卡点=0个consolidated项目
- 全局 7 模块改进 ✅；LLM vLLM 跑通（embedding 404 降级 ilike）；知识库收口完成
- A7-A15/A16/A17/A18 完成阶段底稿 ✅；a21-a25 复核底稿 ✅；核对表/弹窗/分析复核 ✅

### git 状态（2026-06-21）
- 分支 `work/2026-05-30-wp-specs`，HEAD `35bfa9f4`（补 3 条联动链运行时测试 + 归档 6 底稿治理 spec，22 文件 +415/-15，已推送），最高迁移 V089
- **active spec=0（2026-06-21 归档完成）**：6 个底稿治理 spec 全部归档到 `_archive/07-workpaper-slimdown/`（render-config-refactor/health-pass2/silent-exception-cleanup/large-file-split/-pass4/frontend-large-component-split）；INDEX.md 总数 149→155、active 1→0、07 分类 9→15 已同步；render-config V1-V5 验收已勾、frontend 守卫父任务已勾
- **底稿关联调整闭环（2026-06-21 全 6 条链运行时实测通过）**：6 条联动链全部有运行时集成测试实证。`test_cycle_linkage_handlers_integration.py`(19) 覆盖 C控制→D~N/F→F2A/D~N审定表→TB→A13级联；**新增 `test_cycle_linkage_remaining_chains.py`(10)** 补齐此前缺测的 3 条：C偏差→IssueTicket+控制结论覆写(_on_c_deviation_saved，真 session.add(IssueTicket))/C22→C21-1 findings(_on_c22_itgc_saved，list+dict 两种 step 形态)/B50-3→risk_assessment override(_on_b50_saved 闭包，经 event_bus._handlers 取出直调，既验注册又验写入)。读取端 resolver 契约 test_auto_data_resolvers 80 passed。合计 130 passed 零回归。**坑**：B50 handler 内 `invalidate_auto_cache` 是 register 函数内局部 import 无法 monkeypatch→让其真实执行(仅清进程缓存无副作用)；`async_session_factory` 是 event_handlers 模块级可 patch
- **铁律提醒**：勿凭静态阅读下"全链可追溯"乐观结论，须区分"代码存在"vs"运行时实测通过"
- **远程默认分支隐患**：`origin/HEAD→origin/master` 落后 main 298 commit，需 GitHub 改

### wp_render_config 策略拆分（2026-06-19 完成，spec: workpaper-render-config-refactor）
- **✅ P0~P2 全部 21 任务完成**，3772 测试全绿零回归
- `wp_render_config.py` 1474→1156 行；`get_render_config` 475→119 行（dispatch 模式）
- 7 策略文件 `wp_render_strategies/`：_b_index/_a_program/_audit_sheet/_checklist/_analytical_review/_c_note/_univer_grid
- `_resolve_legacy_source` 已删；`control_deficiency_count` 迁入 _REGISTRY（28 测试）
- `wp_component_type_mapping.py` 单一真源；两处 derive_component_type 已改造
- `_WP_CODE_OVERRIDE` 910 条按 15 循环分区注释
- 新增 19 个 cycle_linkage_handlers 集成测试（D/C/F handler）
- **🟡 待 commit**：无（已推送 1fc133da）

### A1-11 签字流转控制表（2026-06-20 修复）
- **修复**：注册 `wp-popup-signing` componentType → `WpPopupSigning.vue`（已有组件，之前仅弹窗模式使用）
- override `"univer"` → `"wp-popup-signing"`；前后端 4 文件改动；1096 冒烟全绿

### 待办
- **✅ workpaper-module-health-pass2（2026-06-21 全部完成，2026-06-20 复查健康）**：9 项 P1/P2 治理，1152 测试零回归
  - `wp_render_config.py` 1156→747；`wp_classification_service.py` 1319→310；`wp_template_files.py` 1160→301
  - 新建 5 service + 2 router（xlsx 652/docx 77）+ 1 JSON（910 条热重载）+ 20 新测试；51 resolver docstring 全覆盖
  - router_registry 启动校验 + CI 测试就位；`_EXCLUDED_ROUTERS` 现仅剩 eqcr 子模块（父包聚合注册），3 个待注册模块已正式注册
  - **复查验证**：app 正常加载 1522 路由、xlsx(4)/docx(1) 端点可达、启动校验无遗漏 WARNING；核心 26 + 冒烟/auto_data 1124 全绿
- **✅ 5 项后续治理 + 6 PBT 已完成（2026-06-21）**：注册 router + 精简 xlsx(758) + skip stub + 联动文档化 + 删 8 孤儿 + 6 PBT(P2~P7) 全绿；workpaper_summaries 无需拆分(37+299行)
- **✅ workpaper-silent-exception-cleanup（P1，2026-06-20 完成）**：底稿模块 70 处宽异常静默吞全部补分级日志留痕，零控制流变更
  - A:working_paper(9) B:模板/网格(16) C+D:交叉核对/离线(8) E:18循环router UUID解析(18) F+G+H:render/其它router/填充(19)
  - 分级:DB/IO/事务/取数失败→warning，样式/UUID入参/LLM降级→debug
  - 新建 `test_wp_silent_exception_guard.py` AST 守卫(CI 阻断新增，白名单空)；守卫 70→0 全绿；1144 测试零回归；app 1522 路由不变
- **底稿改进建议（2026-06-20 调研）**：~~①P0 大文件拆分~~ spec 已立项 `workpaper-module-large-file-split`（pass3）；~~②P1 吞异常~~ ✅；~~③P2 override key 契约~~ ✅；~~④P3 spec 收口~~ ✅
- **✅ P2 override key 契约（2026-06-20）**：新建 `test_wp_code_override_key_contract.py`，聚合全部 data JSON 的 wp_code 全集，override key 须命中或去合法后缀(程序表 A/子表 -N)后命中；30 个孤儿全部通过后缀归一；3 passed
- **✅ P3 spec 收口（2026-06-20）**：`audit-report-template-integration` 归档至 `_archive/05-business-features/`（185/190，剩 3 项 `[ ]*` 人工/外部依赖）；INDEX 更新 active=3（均底稿治理 spec：render-config-refactor/health-pass2/silent-exception-cleanup，待归档）
- **✅ workpaper-module-large-file-split（P0/pass3，2026-06-21 全部完成）**：3 文件拆 ≤800，零行为变更
  - Sprint A `auto_data_resolvers` 1626→域子包(__init__ 97行+6子模块)，51 source 不变；`test_k_cycle` inspect.getsource 改查 `get_registered_sources()`
  - Sprint B `workpaper_fill_service` 1819→30行 Mixin 组合（`wp_fill/` 5 mixin，45 方法仍挂实例供 `service._x()` 测试）；⚠`_review_prompt.load_review_prompt` 因深一层加 1 次 `os.path.dirname` 保 TSJ 路径不变（唯一非逐字改）；顺手删孤儿测试 `TestAIChatService`（引用已删模块 ai_chat_service）
  - Sprint C `working_paper` 1937→400行，共享请求模型抽到 `schemas/workpaper_requests.py`，拆 4 子 router：`wp_editor_router`(727)/`wp_review_router`(405)/`wp_batch_router`(261)/`wp_relation_router`(312)，全部同前缀注册到 router_registry「生命周期/复核」组；helper 随唯一调用方迁移 + working_paper re-export 保向后兼容（test_a16/test_reassignment 依赖）
  - 守卫 `test_wp_large_file_size_guard.py` 转绿；1193+18 测试零回归；app 1522 路由不变；无循环导入
- **底稿改进调研（2026-06-21，pass3 后）**：silent-exception 清零、override 契约已守卫、3 P0 大文件已拆。剩余项：
  - **①pass4 大文件(P1，2026-06-21 完成，spec workpaper-module-large-file-split-pass4)**：3 服务文件拆 ≤800，零行为变更，1222 测试零回归，app 1522 路由不变
    - Sprint A `wp_template_init_service` 1208→769：平级子模块 `wp_template_finder.py`(283)+`wp_template_xlsx_ops.py`(223)，主文件 re-export 保导入路径
    - Sprint B `wp_standard_conversion_service` 934→584：`wp_conversion/_generate.py` WpConversionGenerateMixin(生成6方法)，mixin 组合保方法挂实例
    - Sprint C `wp_fine_rule_engine` 892→569：`wp_fine_rule_checks.py`(315)+`wp_fine_rule_util.py`(24,_safe_num)，单向链 engine→checks→util 避循环
    - 守卫扩 pass4 三目标转绿；`workpaper_models`(826) 本轮未拆(ORM 循环导入风险，后续单独评估)
  - **②skip 测试盲区(P2)**：~~已实测推翻~~ 真实 D1 模板在仓库内(`wp_templates/D/D1 应收票据.xlsx`)，3 文件 31 测试全 PASSED；skipif 仅精简环境降级且各有合成模板兜底，非盲区，**撤销此建议**
  - **③凭证 OCR(P2)**：`wp_evidence_ocr_service.py:224` TODO LLM 链路待接入(stub,外部依赖 vLLM/MinerU)
  - **④resolver 契约(P3,2026-06-21 完成 A 增强版)**：新增全量 resolver 成功契约守卫 PBT(`test_auto_data_resolvers.py`,参数化遍历 51 resolver 喂空结果 mock 断言①不裸抛②返回含非空 summary 的 dict)；**当场抓出 2 个真 bug 并修**：`b3_independence_status`(导入不存在的 ORM 类 ChecklistResponse + 查不存在的 wp_code 列→改裸 SQL JOIN checklist_responses→working_paper→wp_index 按 wp_code='B3')、`related_party_disclosure_check`(导入不存在的 app.models.disclosure_models→改 report_models)；resolver 测试 80 passed,1214 测试零回归,app 1522 路由不变
  - **⚠ 预存失败(非本次范围)**：`test_checklist_responses_crud` 422(PUT body 校验失败,checklist 路由 schema 问题)，依赖真实 DB、与 resolver 改动无关，先于本次存在，待单独修
  - **⑤前端底稿组件健康度（2026-06-21 扫描+清理）**：`components/workpaper/` 反模式债≈0（无空 catch）；**已清 3 处预留 console.log→emit 事件**：GtAnalyticalReview(navigate-row)/AccountPackageFieldSource(navigate-sheet)/AccountPackageConclusionEntry(enter-conclusion)，非破坏(父组件原未监听)，GtAnalyticalReview spec 6 passed。剩唯一债=大文件 8 个>800(GtAProgramConsole 1625/GtChecklistTable 1437/GtAuditSheet 1405/GtAnalyticalReview 1336 等，.vue 含 template+script+style 三段)。**前端拆分风险/成本远高于后端**(抽 composable+拆子组件易破坏响应式/事件流，且每个拆完必 Playwright 实测)，建议单独立 spec 逐组件验证、非紧急。views 层更大(LedgerPenetration 3977/TrialBalance 2945)但非底稿核心组件。**已立 spec `workpaper-frontend-large-component-split`(2026-06-21,vitest/tsc 完成，Playwright 待实测)**：Top 3 抽 composable+子组件
    - Sprint A `GtAProgramConsole` 1626→1144：3 composable(useAProgramReview/Data/Popups)+1 子组件(GtAProgramLinkedChips)。**800 红线结构性达不到**(模板465+样式109+必留script280含 emit-wiring 不能进 composable)，公认地板，30 测试绿零行为变更
    - Sprint B `GtChecklistTable` 1438→752 ✅：3 composable(useChecklistResponses/Search/Applicability)+2 子组件(GtChecklistNav/Section)+checklistTypes.ts，4 测试绿
    - Sprint C `GtAuditSheet` 1406→786 ✅：3 composable(useAuditSheetTable/Columns/Sections)+auditSheetTypes.ts，71 测试绿
    - 守卫 `large_component_guard.spec.ts`：GtChecklistTable/GtAuditSheet 断言 ≤800，GtAProgramConsole 设上限 1200 防回升(不强求≤800)；2 个预存失败(htmlRendererRegistry/GtIndexChip)经 git stash 验证与拆分无关
    - **结论：前端硬 800 红线不普适**，emit-wiring 不能进 composable；composable 不 emit(回调 wire)、保响应式、单向依赖
    - **🟢 Playwright 实测通过(2026-06-21)**：GtAProgramConsole(A1程序表:21行渲染/4阶段/chip点击跳转A15成功/状态下拉)、GtChecklistTable(A15-1调查表:左导航+右条目+适用性弹窗+填 Y 进度 0→1/22 自动保存)均 0 组件级 error；GtAuditSheet 实时 bundle import 无错+71 vitest 覆盖(项目无 audit-sheet 数据未走 UI)。spec 全部任务收口
    - **⚠ 预存非本次**：`/api/workpapers/{id}/save` 422(缺 html_data) 由 GtWpRenderer 父组件(未碰)构造 save body 引起，与拆分无关，同 test_checklist_responses_crud 422 同源，待单独修
- 外部依赖：LLM embedding / 合并 UAT 数据 / GitHub 默认分支改 main
- A 循环 docx 弹窗（30个待加 WpPopupDocxEditor）
- A3-8 商誉减值 / A4 经营分部 / A5 现金流（spec 已建未实施）
- 数据管理"删除"后重导入唯一约束冲突（需 hard_delete 或 DELETE+INSERT）
- 预设映射 seed 权益类 10 条待补

## 操作铁律摘要

完整明细见 `#conventions`（已补 event_bus/测试反模式/asyncpg/router/前端UI/附注/导入/OnlyOffice 各章节）。此处列最高频踩坑（带关键细节避免再犯）：

- **🔴 大文件导入期间禁改后端代码**：app/*.py mtime 变化→uvicorn `--reload` 杀 worker→导入卡死无报错。**含 git stash/pop/checkout/pull**（重写工作区文件）。诊断=`py-spy dump` 看 worker StartTime 晚于 job started_at
- **🔴 event_bus publish 只传 EventPayload**：禁裸 dict/关键字参数（`_build_dedup_key` 访问 `.event_type` 抛异常被 `try/except:pass` 吞→联动断裂）；轻量通知用 `broadcast_raw(event_type, extra)`
- **🔴 测试掩盖 bug 反模式**：mock 不存在的方法/错误签名=把 bug 编进测试（永绿但生产崩）；禁 `try/except:pass` 包被测调用；用 `assert_awaited_once` 验真调用
- **🔴 余额表 KEY_COLUMNS 勿加 account_name**（升 key 会整行跳过删汇总行）；SELECT tb_balance 返前端的端点必须含 direction 字段
- **🔴 同名项目陷阱**：报"修复没生效"先查 `client_name LIKE` 是否多个同名项目+比对 created_at
- **🔴 contenteditable v-model** 必加 isInternalChange/focus guard（否则光标丢失）
- **🔴 el-tooltip 包非单元素根组件**失效→套 `<span style="display:inline-block">`
- **🔴 附注按 sort_order 排序**，禁中文 note_section 字符串排序（Unicode 码点乱套）
- **🔴 freeze_panes xlsx 加载 crash**：`coordinate_to_tuple(str(ws.freeze_panes))`（影响所有冻结窗格底稿）
- **router_registry 必查**：新 router 必注册；静态路径在通配之前；改后重启
- **后端端点双态返回**必在前端 API 层归一化（`Array.isArray` 兜底）
- **service 只 flush 不 commit**：router 统一 commit 保原子；asyncpg 事务 aborted 后修最先失败的 SQL
- **数据管理删除后重导入唯一约束冲突**：需 `hard_delete:true` 或 recalc 改 DELETE+INSERT
- **OnlyOffice 调试**：先确认 git HEAD 正确→只改 .env 对齐 secret+重启；禁 docker exec 手改容器
- **PowerShell 写中文用 fsWrite**；fsWrite ≥100 行会截断→分批 append；长 commit msg 用 `git commit --% -m`

## 关键引用指南

- **仅 memory.md `inclusion: always`**（≤200 行）；其余 manual 引用
- 技术事实/修复明细 → `#dev-history`
- 架构/MCP/数据流 → `#architecture`
- 编码规范/UI/PG运维 → `#conventions`
- spec 状态 → `.kiro/specs/INDEX.md`

- **✅ A 类底稿 Playwright 实操体检（2026-06-20，项目经理视角逐张测）**：项目 `0ec33ac9`(94 张 A 类)，发现并修复 **5 个真 bug**（均导致底稿打不开/报错/保存失败的硬故障）：
  1. **10 张 docx 文档底稿空白页**(A18/A18-1/A26/A26-1~4/A27/A27-1)：根因 seed 脚本只从 xlsx 扫描的 `workpaper_template_analysis.json` 灌分类，docx 函件/清单/备忘录从未入 `workpaper_sheet_classification` → render-config 返回空 sheets。新建 `backend/scripts/seed/seed_docx_document_classification.py`(幂等补 10 行，class_code=`A-报告文档`)。componentType 走 class_code 派生=`a-program-console`(与同类 docx 函件 A9-1/A10-1/A12-1 一致)，**不要**用 word-template(那是 A16 声明书硬编码专用组件 WorkpaperWordEditor，误用会渲染成声明书界面)
  2. **6 文件裸 SQL 表名错** `working_papers`(复数)→`working_paper`(单数,真实表名)：`review_checklist_service`/`a16_version_service`(+列 `wp.wp_code` 不存在改 JOIN wp_index + `pi.working_paper_id`→`pi.wp_id`)/`completion_phase`(3处)/`time_machine`(3处 table_map)/`status_machine`(1处 table_map)。导致复核签字状态/A16 推荐版本等多端点 500。`adjustments`/`disclosure_notes`/`procedure_instances` 是对的复数，勿动
  3. **GtRegulatoryLetter.vue 导入路径错** `@/components/common/GtIndexChip.vue`→`@/components/workpaper/GtIndexChip.vue`(全仓唯一错处)：A18-2 监管沟通函永远打不开(Vite 500)
  4. **AuditLegendPanel.vue field-overrides 契约错**：用了 `/api/workpapers/{wpId}/field-overrides?scope&key`(路径含 wpId+key 参数)，真实契约是 `/api/workpapers/field-overrides` POST body `{project_id,year,scope,item_key,field,value}` / GET query `{project_id,year,scope}` 返回 `{item_key:{field:value}}` 批量。补 year prop(GtWpRenderer 已传)，GET 读 `data.custom_items.value`。A31 审计标识 404 修复
  5. **GtWpRenderer.onSave 缺防御 → /save 422**(memory 预存问题根因)：WpPopupSigning 等自持久化组件(PUT checklist-responses)`emit('save')` 无参，onSave 仍包装成 `{sheet_name, html_data:undefined}` emit save-success → 外层 POST /save 缺 html_data 触发 422。修复:onSave 判 data 为空(null/非 object/数组)时改 `emit('saved-notify')` 仅刷新不发 /save；新增 saved-notify emit 声明 + WorkpaperEditor `@saved-notify="onChildSaved"` wiring。A1-11 切 tab/签字自动保存 422 消除
  6. **extractTableCode undefined 崩溃**(a11-bundle/a15-bundle 嵌套渲染 GtAProgramConsole，sheetName 为 undefined)：`useAProgramPopups.ts`+`useAProgramReview.ts` 两处 `sheetName.match(...)` 改 `sheetName?.match(...)`。A11/A15 bundle 从 8 error→0（拆分前同款无防御代码，bundle 场景才暴露）
  7. **prefill-suggestions 500**(`review_checklist_service.get_prefill_suggestions`)：查 `WorkingPaper.status.in_(["completed","reviewed"])` 但 `wp_file_status` 枚举无这俩值（合法值 draft/edit_complete/under_review/revision_required/review_passed/archived）→ 改 `["edit_complete","review_passed","archived"]`。A21 复核表 500 修复
  8. **review-definitions 父码 404**(A21/A22…父码)：`get_review_definition_for_wp` 对父码 A2[1-5] 先调 `resolve_review_wp_code` 解析为适用子码(A21-1/A21-2)再查定义。前端无需改，所有调用方受益
  - **已 UI 实测 0 error 的 A 类 componentType（全覆盖）**：a1-dashboard(A1)/a-program-console(A18/A8/A9-1/A30/A17系列)/checklist-table(A1-12/A17-5-1)/analytical-review(A1-13)/misstatement-workpaper(A13)/audit-sheet(A4-1/A5-1)/a2-adjustment-console(A2)/a3-consolidation-console(A3)/audit-legend(A31)/regulatory-letter(A18-2)/wp-popup-signing(A1-11,含4tab+签字)/word-template(A16)/cf-verification(A5)/c-note-table(A5-4/A7-2)/b-index(A6-1)/d-form-confirmation(A10-2)/a11-bundle(A11)/a15-bundle(A15)/a14-3-workbook(A14-3)/e-control-test(A14-6)/review-checklist(A21)/a17-summary(A17-1)/d-form-table(A7-1)。**A 类 94 张全部体检通过，0 残留 error**
  - **🟢 B/C 类底稿体检（2026-06-20 续）**：B 类 18 张 + C 类 21 张全部测完。C 类全绿（a-program-console/d-form-table/audit-sheet 三型）。B 类发现 **第 9 个 bug + 1 个同类 docx 缺失**：
    - **B5 业务约定书控制表空白页**：同 A18 docx 模式（docx 未被 xlsx 扫描器收录 → 分类缺失）。扩展 `seed_docx_document_classification.py` 支持 per-entry class_code，补 B5(`B-报告文档`)+ override JSON `B5→a-program-console`。⚠ `find_template_file_any("B5")` 前缀模糊匹配误命中 `B50`（已知小瑕疵，未修）
    - **9. procedure_table 未知 code 500 → 优雅空表降级**：`procedure_table_auto_service.get_procedure_table` 对无模板 code 原 `raise ValueError`→FastAPI 500。改为返回空表 `{items:[]}`（前端 a-program-console 渲染空表+可手动加行，绝不 500）。系统级健壮性，所有无模板/自定义底稿受益。B5 走 a-program-console 渲染空程序表（临时方案，理想是配真实控制表模板，记待办）
    - B15 重要性计算表 `redirect:true→/materiality` 空 sheets 是**预期**（重定向重要性模块），非 bug
    - **已 UI 实测 0 error**：B 类 univer/e-control-test/h-static-doc(B23)/d-form-table(B1)/checklist-table(B3)/audit-sheet(B60)/a-program-console(B10/B5)；C 类 a-program-console(C1)/d-form-table(C10)/audit-sheet(C22)
    - **🟡 待 commit 追加**：`procedure_table_auto_service.py`(空表降级) + seed 脚本 per-entry class_code + override JSON(B5)+1 行 DB(B5 分类)
  - **🟢 D~N+S 全循环体检（2026-06-20，后端 API 全扫 + 前端抽测）**：D/E/F/G/H/I/J/L/M/N 全绿 0 problems。componentType 分布:DEFGH=confirmation-hub/d-form-table/audit-sheet；I=d-form-table/audit-sheet；J=单底稿八合一(b-index/a-program-console/audit-sheet/c-note-table/univer/d-form-table/skip/h-static-doc)；KLMN=c-note-table/audit-sheet/confirmation-hub；S=a-program-console/d-form-table/audit-sheet/h-static-doc/skip
    - **K14~K18 + S17 空白页修复**：本项目 wp_index 用了标准模板库无的编码(K14资产处置收益/K15其他收益/K16投资收益/K17公允价值变动收益/K18递延收益审定表，标准 K 模板仅到 K13)；S17 非经常性损益模板是旧版 `.xls`(analyze 脚本只扫 .xlsx 漏)。均分类缺失→空白。扩展 seed 补 6 行(class_code K-审定表/S-审定表)+override JSON K14~K18→audit-sheet(S17 已有)。audit-sheet 无模板优雅降空表(K14 UI 实测:工具栏齐全+空态提示「请等待模板初始化或手动新增行」+一键刷新 TB 取数)，0 error
    - **已 UI 实测 0 error**：confirmation-hub(D0)/audit-sheet(D2-2/K14/S17)/八合一(J1)/c-note-table(K1/M1)
    - **B15 同类**：重要性计算表 redirect→/materiality 空 sheets 是预期非 bug
    - **🟡 遗留小瑕疵**：`find_template_file_any` 前缀模糊匹配(B5 误命中 B50、K14 命中 None 但实际无模板)+ analyze 脚本只扫 .xlsx 漏 .xls/.docx → 待单独修模板查找器；K14~K18 用非标准编码是该项目 wp_index seed 数据问题(其他项目同码 name 各异)，根治需规范 wp_index 编码
    - **🟡 待 commit 追加**：seed 脚本(K14~K18/S17 共 6 entry) + override JSON(K14~K18) + 6 行 DB
  - **render-config 体检法**：`GET /api/workpapers/{id}/render-config` 看 `sheets[].componentType`，sheets 空=分类缺失；override JSON 改后需 touch 一个 app/*.py 触发 uvicorn reload(JSON 改动不触发 reload，且 `_WP_CODE_OVERRIDE` 是模块级快照非热重载到消费方)
