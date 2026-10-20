# 需求：M7 / M9 缺失 service 补齐 + lazy import 守卫不再跳过缺失模块

## 背景（2026-10-20 现读现算）

- `routers/m7_special_reserve.py` 函数体内 import `app.services.m7_special_reserve_service` 的 `generate_export_template` / `generate_export_data` / `import_data` / `run_accrual_test`；`routers/m9_other_comprehensive_income.py` import `app.services.m9_other_comprehensive_income_service` 的 `generate_export_template` / `generate_export_data` / `import_data` / `get_adjudication_rows`。两个模块全仓不存在 ⇒ 导出模板、导出数据、导入、计提测试、公式校验 8 个端点一调即 `ModuleNotFoundError`。
- 唯一写过的版本是 7 月误提交到 `audit-platform/backend/` 的草稿（dd620e430）：签名与路由调用不符（`run_accrual_test(params)`、无 `generate_*` / `get_adjudication_rows`），且依赖不存在的 ORM `ChecklistResponse`。
- `test_lazy_import_resolvability._scan_unresolved` 对 `import_module(mod)` 抛任何异常都 `skipped.add(mod)` 后跳过 ⇒ 整个模块缺失时一条都不报。现算被跳过的模块 3 个：上面两个 + F2-1 导出 / 导入引用的 `app.models.checklist_response_models`（同样不存在）。
- X-3 `Deviation_Registry` G6 把 m7 / m9 登记为 `SERVICE_MODULE_MISSING`（基线 10）。

## R1 M7-2 明细表导入导出

1. 导出模板、导出数据、导入三个端点对 `M7-2` 可用；`sheet` 缺省按 `M7-2`；不认识的 `sheet` 返回 400 并列出支持的 sheet。
2. 存储口径与界面一致：整表写 `M7-2-full-data`（remark，界面恢复优先读它），同步写 `M7-2-row-{i}-data` / `M7-2-row-{i}-auditedEnd`（0 起）/ `M7-2-auditedEndTotal`；本次行数以外的同族逐行键清空。
3. 导入整表替换；以下情况返回 400 且不写库：不是 xlsx、超过 10MB、找不到表头、缺列、表头重复、金额不是数字、项目名称为空、超过 500 行、没有数据行。
4. 导出数据的读回顺序与界面一致（`M7-2-full-data` → `M7-2-rows`）；库中 JSON 损坏时在「编制说明」页写明，不静默丢行。
5. 写库带 `project_id`（取自底稿）与 `updated_by`；service 只执行语句不提交，由路由提交。

## R2 M7 安全生产费计提测试

1. `accrual-test` 返回 `method / estimated / booked / diff / is_material / detail`。
2. 口径与前端引擎一致：按产量 = Σ(产量 × 标准)，按收入 = 收入 × 比例，差异 = 应计提 − 账面（正数为少计提），重大性阈值与前端 `DEFAULT_THRESHOLD` 一致（1000 元且相对差异 5%）。
3. 不支持的计提方式、非有限数字返回 400。

## R3 M9-2 明细表导入导出

同 R1，sheet 为 `M9-2`；整表写 `M9-2-detail-rows`（**conclusion**，界面 `getField('2','detail-rows')` 读该列），逐行键 `M9-2-row-{i}-data` / `M9-2-row-{i}-auditedEnd`、合计 `M9-2-auditedEndTotal`；「分类」列只接受不可重分类 / 可重分类。

## R4 M9 权益类公式校验

1. `validate-formulas` 的行取自 `M9-1-*-data`（remark JSON），与审定表界面恢复同一口径、同一顺序。
2. 期末 = 期初 + 贷方 − 借方，与该行「未审数」（期末账面数）核对，容差 1 元。
3. 损坏的 JSON 进 `warnings`；每行带行键与项目名称，能定位到哪一行不平。

## R5 前端

M9-2 导入成功后当页按同一口径重新加载明细行（与 M7-2 一致），不再停留在导入前的数据。

## R6 lazy import 守卫

1. 目标模块在源码树中不存在 ⇒ 该模块的每个导入名都判不可解析。
2. 目标模块存在但在当前环境 import 失败 ⇒ 按源码静态判定导入名，不再跳过；静态无法判定（星号导入 / 模块级 `__getattr__`）按不可解析处理。
3. 新判据配变异证明：恢复旧的跳过逻辑、静态判定恒真时，对应用例必须变红。
4. 修完后基线不新增条目：M7 / M9 由本 spec 补齐；F2-1 同类缺陷一并修复（改裸 SQL）。

## R7 登记与文档

1. X-3 `Deviation_Registry` G6 中 m7 / m9 收口，按脚本规范下调基线 10 → 8（`--emit --set-baselines --lowered-by-task`），`--check` 回到全组 OK。
2. 路由里关于「service 模块不存在」的注释、端点说明与实际支持的 sheet 一致。
3. memory 待修条目更新；INDEX.md 登记本 spec。
