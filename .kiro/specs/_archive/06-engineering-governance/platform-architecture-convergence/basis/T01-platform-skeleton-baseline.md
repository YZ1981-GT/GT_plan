# Task 1 — 平台骨架六域红基线冻结

_Requirements: 1.2, 2.2, 4.3, 5.3, 7.3, 12.1, 12.2_  
_Properties: 1, 3, 7, 9, 13, 23_

取证日期 **2026-09-08**。机器可读真源：[`T01-platform-skeleton-baseline.json`](./T01-platform-skeleton-baseline.json)。  
复现：`python backend/scripts/diagnose/_freeze_pac_t01_baseline.py`；只读探针：`python backend/scripts/diagnose/probe_platform_baseline.py`。

> **归档/commit 必读：** 本节是 **Task 1 冻结快照**。PAC 收口后现网见下方 **「冻结当时 vs 现网」**；后人禁止把现网数字改写回冻结栏，也禁止按冻结栏的 `trace_id.like` / ~5349 debt 去操作生产守卫。完整移交见 [`T23-post-closure-followups.md`](./T23-post-closure-followups.md)。

---

## 冻结当时 vs 现网（双栏）

| 维度 | 冻结当时（Task 1 / T01 JSON） | 现网（PAC 22/22 收口后，2026-09-08） |
|------|------------------------------|-------------------------------------|
| Domain debt | 尚未作为 PAC 正式产物定基 | **4761** current = baseline；`new=0`。过程中曾见 ~**5349**，已作废 |
| TaskEvent 幂等 | 算 hash，去重 **`trace_id.like`**，**未写** `idempotency_key` | 写/查 **`idempotency_key` 等值**；回退 `trace_id.like` ⇒ 变异 M03 RED |
| `app.core.event_bus` 坏 import | review/independence/adjustments 仍指向缺失模块 | 调用点守卫 + envelope 路径已收；见 Task 17–18 证据 |
| Startup registry | lifespan 线序，无 `StartupTaskSpec` | `startup_registry` + health.startup |
| Router | 单文件 path 字面量 117；无 `domains/` | `router/domains/*` 11 域 |
| Registry | 单文件 + `startsWith`；无 `entries/` | `registry/entries/*` 6 域合计 216 |
| Wire reserved | 含 `decision_trace` | `decision_trace`→**active**；仍 reserved：`scope`/`guidance`/`sign_status`/`permissions`（邻域消费，PAC 不造假 UI） |
| Confirmation 挂载 | 未在 T01 验收 | 仍 **light-stub**；深度挂载见 T23 分批冒烟 |

---

## A. 八真源差集（派生，非手抄）

| 真源 | 条数 |
|------|------|
| `VALID_COMPONENT_TYPES` | 214 |
| `RENDERER_DISPATCH` | 159 |
| `REGISTRY_LIST`（含 D_FORM spread） | 216 |
| `HtmlComponentType` | 216 |
| `wp_code_overrides` values | 184 |
| `_ONLYOFFICE_HTML_WHITELIST` | 37 |
| `_CONFIRMATION_COMPONENTS` | 18 |
| manifest `components` | **220**（exemptions=0） |

差集（冻结时）：
- **backend_only**：`univer`（1）
- **frontend_only**：58（bundle / confirmation 前端专属等）
- **manifest 缺后端/前端**：0 / 0
- **manifest_only**：`confirmation-hub` / `redirect-materiality` / `skip`（3）

探针旧实现用 `ast.literal_eval` 读 `RENDERER_DISPATCH`（值是 Callable）⇒ 恒报 0；已改为复用 generator AST 键提取。

---

## B. render-config / wire（并发 WIP 实况）

- `wp_render_config.py`：**726** 行；`_get_render_config_impl` 已薄编排七阶段（`stages_extracted=true`）
- `wp_render_pipeline.py` / `render_config_contract.py` / golden fixture **已存在**
- endpoint 已绑定 `response_model=RenderConfigResponse`
- `_ONLYOFFICE_HTML_WHITELIST` / `_CONFIRMATION_COMPONENTS` **仍定义在** `wp_render_config.py`（generator 声明源）；planner 已改读 manifest `host_policy`

---

## C. lifespan / workers

启动顺序 24 步（迁移 → Ready）与关停 8 步已冻入 JSON。  
workers **12**：sla / import_recover / outbox_replay / audit_log_writer / budget_alert / dataset_purge / staged_orphan_cleaner / export_cleanup / time_machine_cleanup / procedure_dispatcher / invalidation_dispatcher / ImportJobRunner。  
**无** `StartupTaskSpec` registry。

---

## D. 事件确定缺陷（冻结当时仍红；现网已修 — 见双栏）

- **冻结当时：** `TaskEventBus.publish` 算了 hash，去重走 `trace_id.like`，**未写** `idempotency_key` 列（列在 `phase15_models.TaskEvent` **已存在**，非缺迁移）
- **冻结当时：** `app.core.event_bus` **不存在**；`review_workflow_service` / `independence_signing_service` / `adjustments` 仍 import
- **冻结当时：** `CanonicalEventEnvelopeV1` 路径尚无
- **现网：** 等值幂等 + envelope + 调用点守卫已闭环（Task 16–18）；本段保留为红基线史实，勿当操作手册

---

## E. 前端装配

- router：`index.ts` 单文件，`path` 字面量 **117**，`beforeEach`=1，**无** `router/domains/`
- registry：`htmlRendererRegistry.ts` ~2209 行；Map **前**已有 `assertUniqueRegistryComponentTypes`；**无** `registry/entries/`；`registry/index.ts` 仍 `startsWith` 分类

---

## F. 并发脏文件允许区间

| 文件 | PAC 允许 | 禁止 |
|------|----------|------|
| `.kiro/specs/INDEX.md` | 仅本 spec 进度行精确合并 | 整文件重写 / 改他 spec |
| `wp_render_config.py` | 编排/绑定/白名单→投影的小块合并 | 整文件重写；须保留 canonical sheet identity |
| `GtWpRenderer.vue` | 挂载契约钩子小块 | 视觉/公式工具栏范围 |
| `useWpRenderer.ts` | 类型投影与 wire 导入 | 业务渲染逻辑重写 |

禁止混入 `workpaper-page-formula-toolbar-closure`。最高迁移冻结为 **V155**。

---

## G. 已在途 WIP（不得当 Task 1 完成证据，仅登记）

manifest 生成器 / registry / 前端 `componentCapabilities.generated.ts` / `RenderConfigWire` / pipeline / wire checker / `check_component_capabilities.py` 均已落盘；对应任务须各自验收后才能标 `[x]`。

Task 1 完成判据 = 本基线 JSON + 本说明 + 可复现探针，**不是**「WIP 文件存在」。
