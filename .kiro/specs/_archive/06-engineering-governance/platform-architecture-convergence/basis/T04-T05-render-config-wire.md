# Task 4–5 — render-config wire / golden 验收

_Requirements: 2.1–2.7_ · _Properties: 3, 4_

取证日期 **2026-09-08**。

## Task 4

| AC | 证据 |
|----|------|
| 2.1 `response_model` 绑定 | `wp_render_config.get_render_config` → `RenderConfigResponse` + `exclude_unset=True`；`test_render_config_route_binds_strict_response_model` |
| 2.2 真实库 golden | `capture_render_config_wire_golden.py` 直调 `_get_render_config_impl`；fixture `tests/fixtures/platform_architecture/render_config_wire_golden.json`；`source=live_database_production_render_path` |
| 2.6 active/reserved | 模型 `extra=forbid`；未消费字段不得静默丢失；golden model-only=`permissions`/`sign_status` 已在前端 reserved |
| 2.7 禁止构造 fixture 冒充 | 采集器缺代表底稿即 RuntimeError；`--check` 对真库重跑比对 shape |

**覆盖**：html / onlyoffice / confirmation / program / redirect / multi_sheet（6/6）。  
样本码：D2, D2-6, D0, B15, B50-1, A14-4。  
**真库复核**：`python backend/scripts/diagnose/capture_render_config_wire_golden.py --check` → `[OK] live render-config shape matches golden (6 samples)`。

## Task 5

| AC | 证据 |
|----|------|
| 2.3 前端字段覆盖 | `RenderConfigWire` 含 `guidance` / `applicable_standards` / `sign_status` / `permissions` |
| 2.4 四类 nullability | `schema` / `html_data` / `template_version` / `cross_refs.cell` 前后端均可空；`test_known_nullability_quartet_is_aligned_bidirectionally` |
| 2.5 双向差集 | `scripts/check/check_render_config_wire_contract.py` + 三态变异 RED |
| 2.6 reserved 清单 | `RENDER_CONFIG_FIELD_STATUS`；**冻结/T04–5 时** reserved=`scope`/`guidance`/`sign_status`/`permissions`/`decision_trace`；前端 `renderConfig.wire.spec.ts` |

**收口后现网：** `decision_trace` → **active**（`WpDecisionTracePanel`）。仍 reserved：`scope` / `guidance` / `sign_status` / `permissions` — 由邻域真实消费，**禁止**在 PAC 硬造 UI 清 reserved。见 `basis/T23-post-closure-followups.md`。

**测试**：backend `test_render_config_wire_contract.py`；frontend `types/__tests__/renderConfig.wire.spec.ts`。
