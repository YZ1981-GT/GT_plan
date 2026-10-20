# 设计：M7 / M9 缺失 service 补齐 + lazy import 守卫

## 0. 现状确认（设计前现读）

| 项 | 现状 | 依据 |
|---|---|---|
| 两个 service 模块 | 全仓不存在；git 历史只在 dd620e430 的 `audit-platform/backend/`（误提交副本，已删）出现过，签名与路由调用不符 | `git log --all -- "*m7_special_reserve_service*"` |
| 前端调用面 | 只调导出模板 / 导出数据 / 导入，sheet 只有 `M7-2` / `M9-2`；`accrual-test`、`validate-formulas`、`tb-writeback` 前端无调用方 | `useM7ImportExport.ts` / `useM9ImportExport.ts` |
| 导入的 `sheet` | 前端放在 multipart 表单字段，路由按 query 参数收 ⇒ 导入时恒为 `None` | 同上 + 路由签名 |
| 授权 | 两个 router 注册时挂 `dedicated_wp_gate`（GET=dedicated_read，POST=dedicated_write，reviewer / 历史只读拒写） | `router_registry/workpaper.py` |
| `checklist_responses` | `project_id` NOT NULL、`(wp_id, item_id)` 唯一、无 ORM 模型、无触发器 | PG 现查 |
| 兄弟 service（m1~m6/m8/m10） | 多处查不存在的列（`status` / `evidence`）或不存在的 ORM，不可照抄 | X-3 spec 记录 + 现读 m5/m8 |
| 守卫跳过的模块 | 3 个：m7 / m9 service + `app.models.checklist_response_models`（F2-1 导出 / 导入） | 探针逐个 `import_module` |
| X-3 G6 | m7 / m9 = `SERVICE_MODULE_MISSING`，`--check` 现为 11 组 OK | `check_x3_deviation_registry.py --check` |

## 1. 存储映射（与界面逐键一致）

| 键 | 列 | 内容 | 界面读写方 |
|---|---|---|---|
| `M7-2-full-data` | remark | 行数组（输入字段 + key） | `M7TabDetail._restoreRowsFromResponses` 优先读；`useM7Detail._syncFullData` 写 |
| `M7-2-rows` | remark | 旧版行数组 | 恢复降级（只读） |
| `M7-2-row-{i}-data` / `-auditedEnd` | remark | 单行 JSON / 审定期末 | `useM7Detail._triggerSave`（i 从 0 起） |
| `M7-2-auditedEndTotal` | remark | 审定期末合计 | 同上 |
| `M9-2-detail-rows` | **conclusion** | 行数组（19 个输入字段） | `M9TabDetail._initDefaultRows` 经 `getField` 读 conclusion |
| `M9-2-row-{i}-data` / `-auditedEnd`、`M9-2-auditedEndTotal` | remark | 同 M7 | `useM9Detail._triggerSave` |
| `M9-1-{key}-data` | remark | 审定表行 | `M9TabAdjudication._restoreRows` 读全部 `M9-1-*-data` |

数字写法与前端 `String(number)` 一致（整数不带小数点）。行 key 由导入生成 `m7-detail-import-{i}-{批次}`，界面恢复保留该 key。

## 2. 模块结构

- `app/services/m_detail_sheet_io.py`：M7-2 / M9-2 共用内核。`DetailSheetSpec`（列定义、存储键、计算函数）+ 模板 / 数据工作簿、读回、解析、整表替换写库。两张表机制完全相同，抽一份避免两份实现漂移。
- `app/services/m7_special_reserve_service.py`：M7-2 规格 + 计提测试纯函数。
- `app/services/m9_other_comprehensive_income_service.py`：M9-2 规格 + 审定表行读取。
- 路由改动：导入传 `updated_by`；计提测试 `ValueError` → 400；公式校验返回 `warnings` / `row_key` / `item_name`；删掉「模块不存在」注释，端点说明改成实际支持的 sheet。

### 错误分层

- 不认识的 sheet → service 直接抛 `HTTPException(400)`（导出也要可读错误；X-3 G6 的判据就是看 service 里有没有这个）。
- 底稿 id 不是 UUID / 底稿不存在 → `HTTPException(404, "资源不存在或不可访问")`，与 gate 拒绝同文案。
- 文件内容问题 → `ValueError`，路由既有的 `except ValueError` 转 400。

## 3. 导入

1. 校验文件：空 / >10MB / 解析失败 → 400。
2. 找表：标题含 sheet 码的工作表优先，其余按顺序；前 10 行内含「项目名称」/「OCI项目」的行为表头。
3. 表头归一（去空白、全角括号转半角）；缺任何输入列、重复列 → 400；计算列（导出数据带的）忽略；其他列写入 warnings。
4. 逐行：全空跳过；名称为「合计 / 小计 / 总计」跳过并计数；名称空、金额非数字、分类非法记错误；最多报 10 条、整批拒绝。金额接受千分位、`(123)` 负数、`-` 表示 0。
5. 写库：整表键 + 逐行键 + 合计键一次批量 upsert（`ON CONFLICT (wp_id, item_id)` 只更新本键存储列），超出本次行数的逐行键置空（清空而非删行）。SQL 只用 PG 与 SQLite 共有语法（`CURRENT_TIMESTAMP` / `excluded` / `LIKE ... ESCAPE`）。

## 4. 计提测试（M7-4）

纯函数，与 `useM7AccrualEngine` / `useM7AccrualTest` 同式：按产量 Σ(output × rate)、按收入 revenue × rate、diff = estimated − booked；`is_material` 规则逐字照前端 `isDiffExceedThreshold`（|diff| ≤ 1000 → 否；应计提为 0 → |diff| > 1000；否则 |diff / 应计提| > 5%）。`detail` 给分档明细、阈值与结论文字。阈值与前端常量由测试读 TS 源码钉住。

## 5. 公式校验（M9-1）

`get_adjudication_rows` 返回 `(rows, warnings)`：按 `item_id` 排序读 `M9-1-*-data`（与界面恢复同口径同顺序），映射为 `begin / credit / debit / reportedEnd(=unadjusted) / rowKey / itemName`。路由保持原有计算与 1 元容差。

## 6. lazy import 守卫

`_scan` 对每个目标模块三分：

| 情形 | 判定 |
|---|---|
| 能 import | 原逻辑（属性 → 子模块） |
| `ModuleNotFoundError` 且缺的就是该模块或其父包 | 该模块全部导入名不可解析，记入 `missing_modules` |
| 其他 import 失败（模块存在但本环境执行出错） | 读源码静态判定（顶层定义 / 赋值 / 导入，含模块级 if / try 块；子模块文件）；星号导入或模块级 `__getattr__` 判「无法判定」⇒ 按不可解析 |

静态判定与既有的 HEAD 判定（分类三）合为一个函数、只换字节来源（工作树 / `git show HEAD:`）。新增用例：合成「整模块缺失」「模块存在但 import 抛错」两类条目，钉死判定；变异（恢复跳过 / 静态判定恒真）须打红。

## 7. X-3 G6

m7 / m9 的 service 里有 `raise HTTPException(400, …sheet…)` ⇒ 探针判 `RAISE_ON_SHEET`、两条移出 G6，实测 8 < 基线 10 ⇒ `NEEDS_BASELINE_LOWERING`。按脚本规范 `--emit --set-baselines --lowered-by-task <本 spec 任务号> --no-ci-probe` 下调到 8，并改探针说明文字里「m7·m9 = SERVICE_MODULE_MISSING」的描述。

## 8. 验证

- SQLite：测试内建与真实 schema 同列的两张表（`working_paper` 最小列 + `checklist_responses` 全列），跑 service 与最小 FastAPI 应用上的三态端点。
- PG（pg_only）：真实应用路由 + 真实 gate（admin）+ 事务内建项目 / 底稿，会话用 `create_savepoint` 吸收路由的 commit，结束整体回滚。
- 前端：M9TabDetail 挂载测试（导入成功后行被替换）。
- 浏览器：真实项目上只做导出（只读）；导入写库只在测试数据上验（库内【测试】项目没有 M7 / M9 底稿）。

## 9. 范围外发现（只登记）

### 9.1 回归里遇到的红（均非本 spec 引入）

| 测试 | 红数 | 原因与归因依据 | 处置 |
|---|---|---|---|
| `test_x3_same_origin_property.py` / `test_x3_column_alignment.py` | 11 / 1 | x3 spec 2026-08-16 归档（d96245a9a）后仍读未归档路径，登记表 / 实证快照恒「不存在」。HEAD 5283f3a67 干净检出同红 | **已改**（各 1 处路径）：它们读的正是任务 9 下调过的登记表，不修就验不了下调；改后 86 passed |
| `test_m_cycle_export_import_verification.py` | 56 | 断言 M 类 wp_code 的 componentType 为 `audit-sheet` / `d-form-*`，`wp_code_overrides.json` 早已改映射到专属组件（如 `M7-2 → m7-special-reserve`）；测试 2026-07-09 后未更新。HEAD 干净检出同为 56 | 未改 |
| `test_lazy_import_resolvability.py` | 2 | 工作树里并发会话新建、未跟踪的包 `app/services/formula_settings/`：`project_ops.py` 惰性 import `app.services.formula_settings.templates`，该模块不存在（HEAD 上没有这个包，所以 HEAD 不红）。守卫按新判据报「目标模块不存在」，正是本 spec 要的效果；用守卫自身的扫描函数排除该包后，全仓 0 新增、0 缺失模块 | 未改，归该包作者 |

同形的过期路径全仓还有：按 `"specs" / "<名>"` 字面拼接、目录已归档的测试 13 个文件（`test_workpaper_ac_coverage_matrix` / `test_workpaper_staged_artifact_boundary_contract` / `workpaper_sync/` 下 a / k×2 / l / m / n×3 / migration_paradigm / phase5_e1 / workbook_row_change 共 11 个）、脚本 11 个文件（含 x3 的 `emit_x3_equivalence_proof` / `verify_x3_roundtrip_live` / `fix_x3_adjustment_ie_registration`；`snapshot_x3_baseline` 用变量拼接，同样过期）。与本 spec 改动无关，未改。

### 9.2 代码层发现（未改）

1. 兄弟 M service 查不存在的列 / ORM：m4 / m5 查 `checklist_responses.evidence, status`，m10 查 `evidence`（两处），m8 用 `app.models.audit_platform_models.ChecklistResponse`（该 ORM 不存在，已在守卫待修基线）。
2. `wp_render_strategies/_m9_other_comprehensive_income.py` 的渲染期公式校验读 `conclusion` 列里的 `M9-1-*` / `M9-2-*` 对象、找 `begin / opening / end_balance`、`pre_tax / after_tax_net` 等键；界面实际把审定表行存在 `M9-1-*-data` 的 remark、字段名是 `beginning / creditAmount / debitAmount / unadjusted`，`M9-2-detail-rows` 是数组 ⇒ 该校验恒取不到行。
3. `useM7CrossSheet.ts` 读 `M7-M7-1-total-end-audited`、`M7-M7-2-total-end-amount`、`M7-M7-2-row-*-end` / `-capital-exp` 双前缀键，生产代码里没有写入方（明细表实际写 `M7-2-row-{i}-*`、`M7-2-auditedEndTotal`）⇒ 审定表与明细表的勾稽恒按 0 比较。M1 / M2 / M4 / M5 / M8 / M9 的集成测试里有同形键，未逐个核实。
4. `wp_render_strategies/_m7_import_export.py` / `_m9_import_export.py`：全仓无引用，运行期路由表里 `/api/workpapers/{wp_id}/m7|m9/*` 由 `_x3_adjustment_import_export` 提供；两者的 M7-2 / M9-2 是 7 列通用明细，与真实 27 / 30 列不符。属死代码，删除走删旧代码流程。
5. 导入的 `sheet`：前端放在 multipart 表单字段，路由按 query 读 ⇒ 导入时恒为 `None`、按默认 M7-2 / M9-2 处理。现在每个 service 只支持一张表，结果正确；以后支持多张表时必须先对齐。
6. 科目码两套：前端 M7 用 `4201`、M9 用 `4103`（`useM7FormData` / `useM9FormData` 的 `ACCOUNT_CODE`、EventBus `accountCode`），M9 路由 `TbWritebackRequest.account_code` 默认 `4103`；渲染策略与四表语义裁决用 `4301` / `4003`（`test_semantic_resolver_coverage` 记录 report_config 的旧码是错码）。
7. lint：`m9_other_comprehensive_income.py` 的 `import sqlalchemy as sa` 未使用、`_f2_import_export.py` 余 `PatternFill` / `Alignment` 未使用，均为 HEAD 已有（本次改动后 F / E9 告警只减不增）。

### 9.3 登记表同次刷新的 G8 证据

`--emit` 会按现读结果重写所有组的证据。G8（`N3-3` 源模板笔误）这次有一处变化：模板第 3 行已没有重复的「编制人：」，`row3_duplicated_labels` 由 `["编制人："]` 变为 `[]`。原因是 c0713ac80（2026-10-08，模板净化）晚于登记表写入（d96245a9a，2026-08-16）改了模板；第 2 行标题笔误仍在，条数仍为 1，基线不动。
