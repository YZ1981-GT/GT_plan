# 任务：M7 / M9 缺失 service 补齐 + lazy import 守卫

- [x] 1. 共用内核 `m_detail_sheet_io.py`（规格、模板 / 数据工作簿、读回、解析、整表替换写库）
  - _需求：R1、R3_
  - `backend/app/services/m_detail_sheet_io.py`（754 行，LF）：`DetailSheetSpec` / `InputColumn` / `ComputedColumn`；`export_template` / `export_data` / `load_rows` / `parse_workbook` / `replace_rows` / `import_sheet`；`js_number`（整数不带小数点，node V8 实测一致）/ `lenient_number` / `parse_amount`（千分位、`(123)` 负数、`-`=0）；`require_wp_uuid` / `require_project_id` / `like_prefix`。写库裸 SQL `ON CONFLICT (wp_id, item_id)`，列名白名单校验（防注入），只用 PG/SQLite 共有语法（`CURRENT_TIMESTAMP` / `excluded` / `LIKE ... ESCAPE`）。
  - 证据：`test_m7_m9_equity_detail_io.py` 74 passed（SQLite 真 SQL）；变异 B1~B11 全 RED 并逐字节恢复。

- [x] 2. M7 service：M7-2 规格 + `generate_export_template` / `generate_export_data` / `import_data` / `run_accrual_test`
  - _需求：R1、R2_
  - `m7_special_reserve_service.py`：`M7_DETAIL_SPEC`（输入列 + 公式列，存储键逐字对齐 `useM7Detail`）；`SUPPORTED_SHEETS={M7-2}`，`resolve_sheets` 对未知 sheet 抛 `HTTPException(400, unknown_sheet_message(...))`；`run_accrual_test`（按产量 Σ、按收入）、`is_accrual_diff_material` 逐字照前端 `isDiffExceedThreshold`，阈值 `ACCRUAL_THRESHOLD_ABSOLUTE=1000.0` / `_RELATIVE=0.05`（测试读 TS 源码钉住）。
  - 证据：浏览器 `accrual-test` 返回 estimated=2000/booked=1800/diff=200/is_material=false；非法 method → 400；未知 sheet → 400。

- [x] 3. M9 service：M9-2 规格 + `generate_export_template` / `generate_export_data` / `import_data` / `get_adjudication_rows`
  - _需求：R3、R4_
  - `m9_other_comprehensive_income_service.py`：`M9_DETAIL_SPEC`（`full_storage=conclusion`，与 `M9-2-detail-rows` 读写列一致）；`get_adjudication_rows` 返回 `(rows, warnings)`，按 `item_id` 排序读全部 `M9-1-*-data` 的 remark JSON，映射 `begin/credit/debit/reportedEnd(=unadjusted)/rowKey/itemName`，坏 JSON 入 warnings。
  - 证据：PG 用例 `test_m9_import_and_formula_check_through_real_routes` 校验 total=2/valid=1/invalid=1、`M9-2-detail-rows` 存 conclusion 且 remark 为 NULL。

- [x] 4. 路由：导入传 `updated_by`、计提测试 400、公式校验 `warnings` / 行定位、注释与端点说明对齐
  - _需求：R1.5、R2.3、R4.3、R7.2_
  - 两路由导入都传 `updated_by=current_user.id`；M7 `accrual-test` 的 `ValueError` → 400；M9 `validate-formulas` 改用 `(rows, warnings)`，响应加 `row_key` / `item_name` / `warnings`；删掉「service 模块不存在」的注释段，端点 docstring 改成实际只支持 M7-2 / M9-2。
  - 证据：PG 用例断言 `updated_by == admin.id`；浏览器 `validate-formulas` 返回含 warnings / formula_description。

- [x] 5. 前端：M9-2 导入成功后当页重载明细行
  - _需求：R5_
  - `M9TabDetail.vue` `onImportFile` 成功后 `await formData.loadData(); _initDefaultRows()` 再 `emit('imported')`。
  - 证据：`m9-detail-import-refresh.spec.ts` 2 passed；变异（撤回该修复）成功用例变红。

- [x] 6. lazy import 守卫：缺失模块判不可解析、import 失败改静态判定、合成用例 + 变异证明
  - _需求：R6.1~R6.3_
  - `_scan` 三分：能 import 走原判据 / 缺的是目标模块（或父包）→ 该模块全部导入名记 `missing_modules` / 其他 import 失败 → 源码静态判定（`_static_resolvable`，含顶层 if·try·with·for·while 块、子模块文件；星号导入 / 模块级 `__getattr__` → 无法判定按不可解析）。fixture `synthetic_package` 只替换字节来源；新类 `TestWholeModuleAndImportFailureVerdicts` 6 例。从基线删僵尸条目 `phase5_f4_01_adjudication`（5cb7ebe70 已入库，预存红）。
  - 证据：守卫 15 passed；变异 M1~M6 全 RED 并逐字节恢复；把 M7 service 挪走后主守卫打红并标「← 目标模块不存在」。

- [x] 7. F2-1 导出 / 导入改裸 SQL（同类缺陷）
  - _需求：R6.4_
  - `_f2_import_export.py`：`_export_f2_1_data` 原 `from app.models.checklist_response_models import ...`（全仓不存在，一调即 ModuleNotFoundError）改裸 SQL `SELECT item_id, conclusion ... LIKE 'F2-1-%'`；`_import_f2_1_data` 删掉没用到的同一 import（它本就走裸 SQL upsert）。
  - 证据：新增 `test_f2_1_import_export_pg.py` 2 passed（真实路由，逐字段落库 / 唯一约束 ON CONFLICT / 空值不覆盖 / 只读本底稿本 sheet 行）；变异（换回 HEAD 版）导入导出两条都红在 `ModuleNotFoundError: No module named 'app.models.checklist_response_models'`（_f2_import_export.py:147 与 :228），逐字节恢复校验 sha256 一致。

- [x] 8. 测试：SQLite service / 端点、PG 真实路由、前端挂载
  - _需求：R1~R5_
  - `test_m7_m9_equity_detail_io.py` 74 passed（SQLite 真 SQL + 最小 FastAPI 端点 + 前端源码契约 + 真实 app gate 挂载）；`test_m7_m9_equity_detail_io_pg.py` 3 passed（真实 PG + 真实路由 + gate：admin 放行 / 项目外 404、整表替换、逐行键清空、合计、`project_id` 非空、`updated_by` 外键，事务回滚，事后现查 0 残留）；`test_f2_1_import_export_pg.py` 2 passed；`m9-detail-import-refresh.spec.ts` 2 passed。全部关键路径配变异证明并逐字节恢复。

- [x] 9. X-3 G6 下调 10 → 8，`--check` 全组 OK
  - _需求：R7.1_
  - 改 `check_x3_deviation_registry.py` 里 G6 的 `mechanism_note` / `owner_spec` 文字；执行 `--emit --set-baselines --lowered-by-task 9 --no-ci-probe`；`deviation_registry.json` G6 10→8（写 `baseline_lowered_from:10`、`lowered_by_task:"9"`，删 m7/m9 两条，合计 91→89）。同次 emit 顺带如实刷新 G8 的 `row3_duplicated_labels`（模板 c0713ac80 净化后已无重复「编制人：」，第 2 行标题笔误仍在，条数不变）。
  - 证据：`--check` 输出「[OK] 十一组全部收口」，G6 基线 8 实测 8，exit 0。

- [x] 10. 浏览器实测（导出）+ 回归 + memory / INDEX 更新
  - _需求：R7.3_
  - 浏览器（chrome-devtools）：和平药房_2025 的 M7-2 / M9-2「导出模板」「导出数据」均 200，文件名 `M7专项储备_M7-2_模板.xlsx` 等正确，openpyxl 读回是合法 xlsx（表头与编制说明齐全；数据页只有表头，与库中该底稿 0 行一致）；另在浏览器上下文直调 `accrual-test`（200）、`validate-formulas`（200）、未知 sheet（400）。实测期间 editing_locks 已释放、`checklist_responses` 0 条新增。
  - 写入型（导入 / 计提落库 / 公式校验落库）由 PG 真实路由测试覆盖：库内【测试】项目都已软删除且无 M7 / M9 底稿，不在共享开发库造持久底稿（见 design §8）。
  - 回归（干净 worktree 复跑「要提交的那棵树」= HEAD + 本 spec 全部文件）：`test_lazy_import_resolvability` / `test_m7_m9_equity_detail_io` / `f2_extraction/test_f2_1_import_export` / `test_f2_import_export_roundtrip` / `test_ie_route_inventory` / `test_router_registry_completeness` / `test_router_registry_split` / `four_table/test_semantic_resolver_coverage` / `test_ie_prefix_reachability` / `test_project_endpoint_authorization_baseline` / `test_x3_same_origin_property` / `test_x3_column_alignment` 共 **310 passed**（worktree 不含并发会话未提交的 `app/services/formula_settings/` 包，故 lazy import 守卫全绿）；PG 用例 5 passed；前端 2 passed；`--check` exit 0；改动文件 ruff F,E9 无新增。
  - 主工作树跑 lazy import 守卫另有 2 条红，均由并发会话未跟踪的 `app/services/formula_settings/` 触发（`project_ops.py` 惰性 import 不存在的 `app.services.formula_settings.templates`）；排除该包后全仓 0 新增 / 0 缺失模块，HEAD 上无此包故不红，归该包作者。`test_m_cycle_export_import_verification` 56 红与 x3 两测试的红也都在 HEAD 5283f3a67 干净检出复现，与本 spec 无关（x3 两处过期路径已顺手修）。见 design §9.1。
  - memory / INDEX 更新见下一步。
