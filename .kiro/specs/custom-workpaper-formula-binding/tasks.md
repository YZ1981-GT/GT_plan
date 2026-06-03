# Implementation Plan: 自定义底稿公式绑定 + 编制信息表头

## Overview

按设计两条主线 + 9 集成点拆解为增量编码任务；**组 ①~⑧ + 残留 14.x 均已 [x]**（2026-06-03）。**依赖顺序**：先打地基（① wp_formula 表/service → ② 注册表扩展 + extract_custom_cells + touch 钩子），再生成 working_paper（③），补编制信息后端（④）与 WP() 求值（⑤），最后前端表头（⑥）与公式编辑器接入（⑦），收尾契约/集成测试（⑧），补强求值写回与联动（14）。

**三层一致铁律**：涉及新表 `wp_formula` 的任务（组 ①）必须 DB 迁移 + ORM `Mapped[]` + service 方法齐全，任一缺失即伪绿。其余各组复用既有表不新增列。

**测试铁律**：后端属性测试用 hypothesis `@settings(max_examples=5)`、生成器含中文样本（中文底稿名/行名/项目名，覆盖 Req 9.4）；集成测试用 in-process ASGI（`httpx.ASGITransport(app=app)`，避免 stale uvicorn + staff_members FK 报错）；Playwright/vitest 实测类标 `[x]*` 且注明实测日期。每条正确性属性 P1~P14 对应一个 hypothesis 属性测试任务。

**工程铁律**：service 只 flush 不 commit、router 统一 commit；parsed_data JSONB 改后必 `flag_modified`；缓存失效在 commit 之后调用；UUID 主键 ORM `default=uuid.uuid4` 兜底；迁移 **V052**（本地 PG 已应用；生产须手工执行）；新 router 必在 `router_registry` 注册否则前端 404；UI 必用 GT 紫令牌（`--gt-color-primary #4b2d77`），`el-tag` scoped 覆盖默认蓝。

## Tasks

### 组 ① 后端数据层 — wp_formula 独立表（三层一致地基，最先做）

- [x] 1. 新建 wp_formula 表与公式持久化服务（DB 迁移 + ORM + service 三层一致）
  - [x] 1.1 编写 V052 迁移 + R052 回滚配对
    - 新建 `backend/migrations/V052__wp_formula.sql`：`CREATE TABLE IF NOT EXISTS wp_formula`（id UUID PK、project_id/wp_id FK、sheet_name、target_cell、expression、category、description、created_by、created_at/updated_at TIMESTAMPTZ），`CREATE UNIQUE INDEX IF NOT EXISTS uq_wp_formula_wp_sheet_cell (wp_id, sheet_name, target_cell)` + `idx_wp_formula_project`
    - 新建配对 `backend/migrations/R052__wp_formula_rollback.sql`：`DROP TABLE IF EXISTS wp_formula`
    - 注意：DDL DEFAULT 用 `gen_random_uuid()` 仅作裸 SQL 兜底；UUID 主键真正由 ORM `default=uuid.uuid4` 赋值（避免 PK 缺 default bug）；版本号 V052（已落地）
    - _Requirements: 6.3_

  - [x] 1.2 追加 WpFormula ORM 模型（Mapped[] 三层一致第二层）
    - 在 `backend/app/models/workpaper_models.py` 追加 `class WpFormula(Base)`：`__tablename__ = "wp_formula"`，`id` Mapped[uuid.UUID] PK `default=uuid.uuid4`，project_id/wp_id/sheet_name/target_cell/expression/category/description/created_by/created_at/updated_at 字段，`__table_args__` 含唯一索引 `uq_wp_formula_wp_sheet_cell` 与 `idx_wp_formula_project`
    - _Requirements: 6.3_

  - [x] 1.3 实现 WpFormulaService（save / list / delete，三层一致第三层）
    - 新建 `backend/app/services/wp_formula_service.py`：`save`（按 wp_id+sheet_name+target_cell 覆盖更新即 upsert）、`list_by_wp`、`delete`；只 flush 不 commit（router 统一 commit）
    - save 前调用 `address_registry.validate_formula_refs` 校验悬空引用，含 not_found 则不写库（返回 issues 供 router 转 422）
    - _Requirements: 6.3, 6.4_

  - [x] 1.4 编写公式持久化往返属性测试（P12）
    - 新建 `backend/tests/test_wp_formula_roundtrip_pbt.py`，`@settings(max_examples=5)`，生成器含中文 sheet_name
    - **Property 12: 公式持久化往返** — `load(save(formula)) == formula`，同 (wp_id, sheet_name, target_cell) 重复保存为覆盖更新而非新增
    - _Property: P12_
    - _Requirements: 6.3_

  - [x]* 1.5 编写公式引用校验完备属性测试（P6）
    - 新建 `backend/tests/test_formula_validate_pbt.py`，`@settings(max_examples=5)`，生成器混合已注册/未注册引用 + 中文 wp_name
    - **Property 6: 公式引用有效性校验完备** — `(∃ ref ∉ registry) ⟺ (validate_formula_refs(formula) 含该 ref 的 not_found)`
    - _Property: P6_
    - _Requirements: 6.4, 8.4_

- [x] 2. 新建公式持久化端点并注册 router
  - [x] 2.1 实现 GET/PUT/DELETE /api/workpapers/{wp_id}/formulas
    - 新建 router（如 `backend/app/routers/wp_formula.py`）：`GET /formulas`（list_by_wp）、`PUT /formulas`（保存，悬空引用转 422 + issues）、`DELETE /formulas/{formula_id}`；router 层统一 commit；commit 后调用缓存失效（见任务 4.3 钩子，本任务先预留调用点）
    - **在 `backend/app/router_registry/{group}.py` 注册该 router**（否则前端 404）
    - _Requirements: 6.3, 6.4_

  - [x]* 2.2 编写公式端点往返 + 悬空 422 单元测试
    - in-process ASGI（`httpx.ASGITransport(app=app)`）：保存→列出→删除往返 + 悬空引用 422 各一例
    - _Requirements: 6.3, 6.4_

- [x] 3. 检查点 — 确保数据层与端点测试通过
  - Ensure all tests pass, ask the user if questions arise.

### 组 ② 后端注册表扩展 — 自定义单元格进 WP 域 + 缓存失效钩子

- [x] 4. extract_custom_cells 纯函数 + build_workpaper_entries 追加自定义条目 + 缓存失效钩子
  - [x] 4.1 实现 extract_custom_cells 兼容两种 parsed_data 结构
    - 在 `backend/app/services/address_registry.py`（或同模块）新增纯函数 `extract_custom_cells(parsed_data) -> list[CellRecord]`，兼容 `html_data[sheet].cells[cell]` 嵌套（cell 值标量或 `{"value":..,"v":..}` 字典）+ `[sheet][field]` 扁平两种结构；行名称取同行 A 列或 cell 自带 label/name
    - 新增 `CellRecord` dataclass（sheet/cell/row_label/value）
    - None/{}/结构异常/中文坏数据 → 返回 `[]` 不抛异常
    - _Requirements: 4.2, 4.4_

  - [x] 4.2 实现 _build_custom_wp_cell_entries 并接入 build_workpaper_entries
    - 新增 `_build_custom_wp_cell_entries(db, project_id)`：SELECT `working_paper.parsed_data` JOIN `wp_index`（wp_code/wp_name），对每底稿 `extract_custom_cells` 生成 `AddressEntry`（domain='wp'、uri `wp://{wp_code}/{cell}`、cell、label 含 `{wp_name} > {row_label}（{cell}）`、formula_ref `WP('{wp_code}','{cell}')`、tags 含中文行名）
    - 单底稿用独立 try/except 包裹，异常记 `logger.warning` 并跳过该底稿，不影响标准条目与其他底稿
    - 在 `build_workpaper_entries` 末尾 `return entries` 前 append 自定义条目（标准固定列条目恒保留）
    - _Requirements: 4.1, 4.3, 4.5, 9.2_

  - [x] 4.3 实现 touch 缓存失效钩子并接线（router 层全覆盖）
    - `wp_parsed_data_service.touch_after_parsed_data_commit` → `invalidate_async(domain='wp')`（try/except 仅 warning，TTL 120s 兜底）
    - **router 层**全部 `wp.parsed_data=` + `commit` 路径已接（含公式端点、上传、底稿保存等）；`test_touch_wp_registry_wiring.py` 静态守护
    - **未接**：`wopi`/`ocr`/`conversion` 等 service 层裸 SQL 写 `parsed_data`（仍靠 TTL）
    - parsed_data JSONB 修改处确保已 `flag_modified(wp, 'parsed_data')`
    - _Requirements: 8.3_

  - [x]* 4.4 编写 WP 域并集属性测试（P1）
    - 新建 `backend/tests/test_wp_domain_union_pbt.py`，`@settings(max_examples=5)`，生成器随机 parsed_data 集 + 含重复 wp_code + 中文 wp_name
    - **Property 1: WP 域并集不丢失** — `set(standard_entries) ⊆ set(build_workpaper_entries(project))`，相同 wp_code 标准与自定义条目共存不覆盖
    - _Property: P1_
    - _Requirements: 4.1, 4.5_

  - [x]* 4.5 编写 URI/formula_ref 往返属性测试（P2）
    - 新建 `backend/tests/test_wp_uri_roundtrip_pbt.py`，`@settings(max_examples=5)`，生成器随机 wp_code/cell + 中文 wp_name
    - **Property 2: URI / formula_ref 往返一致** — `uri_to_formula_ref(formula_ref_to_uri(e.formula_ref)) == e.formula_ref`，uri 形如 `wp://{wp_code}/{cell}`（path 承载单元格，避免 `#` 与 source 粘连）、formula_ref 形如 `WP('{wp_code}','{cell}')`
    - _Property: P2_
    - _Requirements: 4.3, 5.3_

  - [x]* 4.6 编写注册幂等属性测试（P3）
    - 新建 `backend/tests/test_wp_registry_idempotence_pbt.py`，`@settings(max_examples=5)`，生成器固定 parsed_data 重复构建 + 中文样本
    - **Property 3: 注册幂等** — `build(parsed_data) == build(build(parsed_data) 重建)`（去重后数量与内容一致）
    - _Property: P3_
    - _Requirements: 4.1, 8.3_

  - [x]* 4.7 编写解析数据缺失/异常不崩属性测试（P5）
    - 新建 `backend/tests/test_build_wp_bad_parsed_pbt.py`，`@settings(max_examples=5)`，生成器 None/{}/结构异常 dict/含中文坏数据
    - **Property 5: 解析数据缺失/异常不崩且保留标准条目** — `∀ bad_input. build_workpaper_entries(...) does not raise ∧ standard_entries ⊆ result`
    - _Property: P5_
    - _Requirements: 4.4, 9.1, 9.2_

  - [x]* 4.8 编写自定义单元格条目完备性属性测试（P10）
    - 新建 `backend/tests/test_custom_entry_complete_pbt.py`，`@settings(max_examples=5)`，生成器随机单元格 + 中文行名
    - **Property 10: 自定义单元格条目完备性** — `∀ e ∈ custom_entries. e.cell == 单元格地址 ∧ 行名称 ∈ e.label ∧ e.wp_code == 底稿编码 ∧ e.domain == 'wp'`
    - _Property: P10_
    - _Requirements: 4.2, 5.2_

  - [x]* 4.9 编写缓存失效后读到最新属性测试（P9）
    - 新建 `backend/tests/test_wp_invalidate_fresh_pbt.py`，`@settings(max_examples=5)`，生成器 update→invalidate→get 序列 + 中文样本
    - **Property 9: 缓存失效后读到最新** — `update(parsed_data) ; invalidate(wp) ; get(wp) == build(updated_parsed_data)`
    - _Property: P9_
    - _Requirements: 8.1, 8.3_

  - [x]* 4.10 编写 extract_custom_cells 两结构单元测试
    - html_data.cells 嵌套（标量 + 字典 cell 值）/ 扁平 sheet.field 各一例 + 含中文行名一例
    - _Requirements: 4.2_

- [x] 5. 检查点 — 确保注册表扩展测试通过
  - Ensure all tests pass, ask the user if questions arise.

### 组 ③ 后端 working_paper 生成 — 指派后自动生成 + 手动入口

- [x] 6. WorkpaperGenerationService 幂等生成 + 指派接线 + 手动入口
  - [x] 6.1 实现 WorkpaperGenerationService.ensure_working_paper（幂等）
    - 新建 `backend/app/services/workpaper_generation_service.py`：`ensure_working_paper(project_id, wp_index_id, source_type=WpSourceType.manual) -> WorkingPaper`
    - 先查后建：已存在（`uq_working_paper_project_index` 维度）直接返回，不重复创建；UUID 主键 ORM `default=uuid.uuid4`；只 flush 不 commit
    - parsed_data 尚未上传时仍创建空 working_paper（`parsed_data=NULL`，status 过渡"未生成→已生成（待上传）"）
    - _Requirements: 7.1, 7.3_

  - [x] 6.2 在指派流程接线自动生成
    - 在 `backend/app/services/procedure_service.py` 的 `assign_procedures` 内，对 `is_custom=True` + 有 `wp_index_id`（或可由 wp_code 解析）+ 无 `working_paper` 的程序，调用 `ensure_working_paper`
    - router 统一 commit；遵循 service 只 flush
    - _Requirements: 7.1_

  - [x] 6.3 新增手动生成入口端点
    - 新增 `POST /api/workpapers/generate-from-index { wp_index_id }` → `ensure_working_paper`（source_type=manual），router commit；在 router_registry 注册
    - _Requirements: 7.1, 7.3_

  - [x]* 6.4 编写 working_paper 幂等生成属性测试（P14）
    - 新建 `backend/tests/test_ensure_wp_idempotent_pbt.py`，`@settings(max_examples=5)`，生成器重复 ensure 调用 + 中文 wp_name
    - **Property 14: working_paper 幂等生成** — `ensure_working_paper(p, idx)` 后 `∃! working_paper(p, idx)`；`ensure(ensure(x)) == ensure(x)`
    - _Property: P14_
    - _Requirements: 7.1_

  - [x]* 6.5 编写 ensure_working_paper 单元测试
    - in-process ASGI：首次创建 + 重复指派幂等不重复 各一例
    - _Requirements: 7.1_

### 组 ④ 后端编制信息 — _build_preparation_info 抽取 + 端点 + 删会计期间

- [x] 7. 抽取 _build_preparation_info + preparation-info 端点 + B-Index 删会计期间
  - [x] 7.1 抽取 _build_preparation_info(db, project_id, wp_id)
    - 从 `wp_render_config.py` 的 `_generate_b_index_data` 提取人员/项目 JOIN 为 `_build_preparation_info`：projects.name/audit_period_end、project_assignments JOIN staff_members.name（preparer/reviewer，users 无 name）
    - **新增** `prep_date=working_paper.created_at`、`index_no=wp_index.wp_code`；**移除** `accounting_period`（会计期间）
    - 缺失字段留空串（前端渲染"—"）
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.2_

  - [x] 7.2 实现 GET /api/workpapers/{wp_id}/preparation-info 端点
    - 查 working_paper → project_id/created_at/wp_index_id → `_build_preparation_info`；返回 7 字段（entity_name/period_end/preparer/prep_date/reviewer/review_date/index_no），**无 accounting_period**；在 router_registry 注册
    - _Requirements: 2.1-2.6, 3.1_

  - [x] 7.3 _generate_b_index_data 改调用 _build_preparation_info（删会计期间）
    - B-Index 的 preparation_info 改为复用 `_build_preparation_info`，不再生成 accounting_period（保持 B-Index 兼容但删会计期间字段）
    - _Requirements: 3.2, 3.3_

  - [x]* 7.4 编写编制信息字段映射与降级属性测试（P7）
    - 新建 `backend/tests/test_preparation_info_pbt.py`，`@settings(max_examples=5)`，生成器随机元数据组合含缺失字段 + 中文项目名/人名
    - **Property 7: 编制信息字段映射与缺失降级** — `∀ field. render(field) ∈ {对应来源真实值, "—"}`，永不 null/undefined/抛错，单字段缺失不影响其他
    - _Property: P7_
    - _Requirements: 2.1-2.6, 9.3_

  - [x]* 7.5 编写"会计期间"恒不渲染属性测试（P8）
    - 新建 `backend/tests/test_no_accounting_period_pbt.py`，`@settings(max_examples=5)`，生成器随机数据含残留 accounting_period
    - **Property 8: "会计期间"字段恒不渲染** — `∀ data. "会计期间" ∉ rendered_fields(data)`
    - _Property: P8_
    - _Requirements: 3.1, 3.2, 3.3_

  - [x]* 7.6 编写 _build_preparation_info 单元测试
    - in-process ASGI：齐全项目一例 + audit_period_end 为 NULL 占位"—"一例
    - _Requirements: 2.6_

### 组 ⑤ 后端 WP() 求值扩展 — 单元格地址分流

- [x] 8. WPExecutor 扩展支持自定义底稿单元格地址取值
  - [x] 8.1 WPExecutor.execute + _handle_wp 单元格地址分流
    - 在 `backend/app/services/formula_engine.py` 的 `WPExecutor.execute`（及 `_handle_wp` ctx 装填）扩展：第二参匹配 `^[A-Z]+\d+$`（单元格地址）时走 `extract_custom_cells(parsed_data)` 按 cell 取值；否则保持原 col_map 顶层 key 语义（向后兼容标准底稿）
    - 单元格地址在 parsed_data 不存在 → 返回 `Decimal('0')` + trace 记 `not_found`，不中断重算
    - _Requirements: 8.1, 8.2, 8.4_

  - [x]* 8.2 编写 WP() 单元格地址求值属性测试（P11）
    - 新建 `backend/tests/test_wp_eval_cell_pbt.py`，`@settings(max_examples=5)`，生成器随机 parsed_data 单元格 + 列名分支 + 中文 sheet
    - **Property 11: WP() 单元格地址求值正确** — `WP(wp_code, cell) == extract_custom_cells(parsed_data)[wp_code][cell].value`，列名分支保持 col_map 语义
    - _Property: P11_
    - _Requirements: 8.2_

- [x] 9. 检查点 — 确保后端全链路（注册表→公式→求值→生成→编制信息）测试通过
  - Ensure all tests pass, ask the user if questions arise.

### 组 ⑥ 前端编制信息表头 — GtWpPreparationHeader.vue

- [x] 10. 新建 GtWpPreparationHeader.vue 并挂载到 GtWpRenderer
  - [x] 10.1 实现 GtWpPreparationHeader.vue
    - 新建 `audit-platform/frontend/src/components/workpaper/GtWpPreparationHeader.vue`：props `wpId`/`readonly`；`GET /api/workpapers/{wpId}/preparation-info` 加载 7 字段；每字段渲染 `value || '—'`（永不 null）
    - 折叠状态 `collapsed`（折叠后仅最小高度 + 保留展开入口控件）
    - **无 accounting_period 字段**
    - 样式仅用 GT 紫令牌（`--gt-color-primary:#4b2d77`/`--gt-color-primary-bg:#f4f0fa`/`--gt-color-border-purple-light:#d8b8ee`），`el-tag`/标题色 `:deep()` scoped 覆盖默认蓝
    - _Requirements: 1.3, 1.4, 1.5, 2.1-2.6, 3.1_

  - [x] 10.2 挂载到 GtWpRenderer 内容区上方（所有 sheet 共享）
    - 在 `GtWpRenderer.vue` 的 `<div class="gt-wp-renderer__content">` 之前、sheet-tabs 之上插入 `<GtWpPreparationHeader :wp-id="wpId" :readonly="readonly" />`，确保切换 sheet 不重置显示、内容不随 sheet 变化
    - _Requirements: 1.1, 1.2_

  - [x]* 10.3 Playwright 实测编制信息表头（2026-06-03 通过）
    - `npm run test:e2e:custom-wp`（`PW_API_BASE=http://localhost:9980`）：**3 passed**
    - 表头在内容区上方 + 切 sheet 保持显示且内容不变（Req 1.1/1.2）；折叠/展开切换 + 折叠保留入口（Req 1.3/1.4）；计算样式取 GT 紫非 #409eff（Req 1.5）；中文项目名/人名不乱码；audit_period_end NULL 显示"—"
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 9.4_

### 组 ⑦ 前端公式编辑器接入 — WP 数据源切换 + GtCustomWpEditor

- [x] 11. FormulaEditDialog WP 弹窗数据源切换 + GtCustomWpEditor componentType=custom 注册
  - [x] 11.1 改写 openSourceBrowserForWP 数据源
    - 在 `FormulaEditDialog.vue` 仅改 `openSourceBrowserForWP()`：从 `/api/working-papers` 改为 `api.get('/api/address-registry', { params: { project_id, year, domain: 'wp' } })`，映射 AddressEntry → sourceBrowserRows（row_code=wp_code、row_name=label 含单元格+行名、_ref=formula_ref `WP('{wp_code}','{cell}')`）
    - 注册表失败/空 → 降级回退 `/api/working-papers` 底稿级列表 + 空态提示（保留标准固定列选项）
    - 新增可选 props `projectId`/`year`/`wpContext`；搜索过滤复用 `filteredBrowserRows`、插入复用 `onBrowserRowClick`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 9.1_

  - [x] 11.2 新建 GtCustomWpEditor.vue 并注册 componentType=custom
    - `GtCustomWpEditor.vue`：**只读** `GtGridSheet` + 工具栏「公式」按钮；`wpGenerated=false` 时禁用 + `ElMessage.warning`；保存 emit `formula-saved` → `GtWpRenderer.reload()`
    - 打开 FormulaEditDialog 传 `row={row_code: 'CUSTOM:{wpId}:{sheet}'}` + wpContext；保存 emit → `PUT /api/workpapers/{wpId}/formulas`（含目标单元格定位弹窗选址）
    - **在 `htmlRendererRegistry.ts` 注册新 componentType=`custom`** → GtCustomWpEditor（含 lazy import + icon + label）；同步 `useWpRenderer` 的 HtmlComponentType 类型与 HTML_RENDERER_REGISTRY
    - _Requirements: 6.1, 6.2, 7.4_

  - [x]* 11.3 编写弹窗可选项 ⊆ 注册表属性测试（P4，前端逻辑可抽纯函数测）
    - 新建测试（vitest 或后端注册表层），生成器随机注册表条目集 + 空自定义场景
    - **Property 4: 弹窗可选项 ⊆ 注册表条目** — `set(picker_options) ⊆ set(registry.wp_domain_entries)` 且空自定义时 `standard_entries ⊆ picker_options`
    - _Property: P4_
    - _Requirements: 5.1, 5.5_

  - [x]* 11.4 编写弹窗搜索过滤属性测试（P13）
    - 新建测试，生成器随机关键词 + 条目（含中文行名）
    - **Property 13: 弹窗搜索过滤正确性** — `set(filter(kw,rows)) ⊆ set(rows) ∧ ∀ r∈filter. kw∈lower(code)∨kw∈lower(name)`
    - _Property: P13_
    - _Requirements: 5.4_

  - [x]* 11.5 Playwright 实测公式编辑器接入（2026-06-03 通过）
    - 同上 spec（含 create-custom → `componentType=custom` → 公式/定位弹窗/保存公式 API）；与 10.3 同批 **3 passed**
    - _Requirements: 5.1, 5.2, 5.3, 6.1, 6.2, 7.2, 7.4, 9.4_

### 组 ⑧ 契约测试 + 集成测试（守护 + 全链路）

- [x] 12. 契约测试守护 wp_formula 新表 + 全链路集成测试
  - [x] 12.1 wp_formula 纳入 schema/column 契约测试
    - 在 `test_raw_sql_schema_contract.py` / `test_raw_sql_column_contract.py` 纳入 `wp_formula` 表/列引用；三层一致校验（V052 迁移 + ORM WpFormula + WpFormulaService 齐全，任一缺失即伪绿）；V052 不撞号 + R052 配对
    - _Requirements: 6.3_

  - [x]* 12.2 全链路集成测试（in-process ASGI）
    - 链路：上传解析 parsed_data → 指派生成 working_paper → 注册表追加单元格 → `GET /api/address-registry?domain=wp` 含自定义条目 → 保存公式（wp_formula）→ `WP()` 求值取到值；`GET /api/workpapers/{wp_id}/preparation-info` 返回 7 字段无 accounting_period
    - 用 `httpx.ASGITransport(app=app)` 全 app 加载（避免 staff_members FK NoReferencedTableError）
    - _Requirements: 4.1, 5.1, 6.3, 7.1, 8.2, 2.1, 3.1_

- [x] 13. 最终检查点 — 全部测试通过 + 三层一致 + router 已注册
  - Ensure all tests pass; 确认 wp_formula 三层一致、新 router 在 router_registry 注册、迁移 V052/R052 配对不撞号、UI GT 紫令牌生效。ask the user if questions arise。

---

## 残留与补强（2026-06-03 复盘后）

- [x] 14. 保存 wp_formula 后求值写回 target_cell（`wp_formula_eval_service` + `write_cell_to_parsed_data` + 前端 `formula-saved`→`reload`）
- [x] 14.1 保存后求值写回（已由 14 覆盖；早期 `propagate_stale_by_wp_code` 最小接线已 supersede 由 14.3 联动服务承担）
- [x]* 14.2 `touch_wp_registry` 覆盖 router 层全部 `wp.parsed_data=` + `commit` 路径（`touch_after_parsed_data_commit` + `test_touch_wp_registry_wiring.py` 静态守护）；service 层裸 SQL 写 parsed_data（wopi/ocr/conversion）仍靠 TTL
- [x]* 14.3 Req 8.1 依赖联动：`wp_formula_linkage_service` 动态扫描 `WP('code','cell')` 引用→标记引用方 `prefill_stale` + `stale_engine.on_change` 静态图 BFS；`PUT /formulas` 返回 `linkage` 摘要；`test_wp_formula_linkage.py`
- [x]* 14.4 三件套文档与实现对齐（2026-06-03）：requirements/design/tasks URI=`wp://{wp_code}/{cell}`、实现状态、验收记录、复核人/只读网格/联动说明

---

## 验收记录（2026-06-03）

| 层级 | 命令 / 范围 | 结果 |
|------|-------------|------|
| 后端 spec pytest | `test_touch_wp_registry_wiring` + `test_wp_formula_eval` + `test_wp_formula_linkage` + `test_custom_wp_formula_full_chain` + `test_wp_formula_endpoint` 等 | **44 passed, 2 skipped** |
| vitest | `wpFormulaPicker.spec.ts` | **4 passed** |
| Playwright | `npm run test:e2e:custom-wp`（9980+3030） | **3 passed** |

### 第二轮（前端视角 PBT + UAT 复验，同日）

| 层级 | 命令 | 结果 | 备注 |
|------|------|------|------|
| 后端 PBT + 集成 | 16 文件 / 30 条（P1–P10,P12–P14 + eval/linkage/touch/endpoint） | **30 passed** | ~11s |
| 契约 + 全链 + grid | `test_wp_formula_schema_contract` + `layer_contract` + `full_chain` + `wp_grid_extract` | **14 passed, 2 skipped** | schema 对 live PG 2 条 skip |
| 合计（去重） | — | **44 passed, 2 skipped** | 与首轮一致 |
| vitest P4/P13 | `npm run test:unit -- wpFormulaPicker.spec.ts` | **4 passed** | ~1s |
| Playwright UAT | `PW_API_BASE=9980 npm run test:e2e:custom-wp` | **3 passed** | ~10s；9980/3030 探活 200 |

**第三轮收口（同日）**：补 `test_wp_eval_cell_pbt.py`（P11）、`test_wp_picker_subset_pbt.py`（P4）；Playwright **6** 条（+写回 API、只读网格、linkage）；`GtCustomWpEditor` 网格强制 `readonly`；列表/详情 API 返回 `prefill_stale`；WOPI fine-extract 后 `touch`；create-custom 重试 + 保存后 `invalidate` 注册表。

**UAT**：`npm run test:e2e:custom-wp` → **6 passed**（含 linkage + 写回 + 只读）；后端 spec 套件 **33 passed**（+P11/P4 共 3 条）。

**部署**：生产须手工执行 `V052__wp_formula.sql`；本地 PG 已应用。

**已知边界**（与 requirements/design 一致）：复核人=派单角色非复核轨迹；网格只读；联动=动态扫描+静态图 BFS（非全量 runtime 建边）；service 层裸 SQL 写 parsed_data 未 touch。
