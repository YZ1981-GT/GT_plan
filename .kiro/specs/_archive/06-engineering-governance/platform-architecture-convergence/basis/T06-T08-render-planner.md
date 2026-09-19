# Task 6–8 — render planner 七阶段拆分验收

_Requirements: 3.1–3.2, 4.1–4.7_ · _Properties: 5, 7, 8_

取证日期 **2026-09-08**。

## Task 6 — subject / classification / scope redirect

| AC | 证据 |
|----|------|
| 显式阶段类型 | `wp_render_pipeline.py`：`RenderSubject` / `ClassificationResolution` / `ScopeResolution` |
| 阶段函数 | `load_render_subject` / `resolve_classification_sources` / `resolve_scope_redirect` |
| `/api/wp-classifications` 复用公共核 | `resolve_common_classification_resolution` → 同 Stage 2；endpoint 再调 `plan_sheets` |
| 同身份分叉显式原因 | `ClassificationItem.divergence_reason` + `render_plan_componentType`；`format_classification_plan_divergence`；禁止静默覆盖 |
| 测试 | `tests/test_wp_classification_pipeline.py`（含 divergence 显式断言） |

## Task 7 — common facts / sheet plan / decision trace

| AC | 证据 |
|----|------|
| 阶段函数 | `load_common_render_facts` / `plan_sheets`；`SheetPlan` / `RenderDecision` / `RenderPlan` |
| host_policy 唯一裁决 | `plan_sheets` 读 `ComponentCapabilityRegistry.host_policy`；`winning_source=manifest_host_policy` |
| 禁止第二套白名单 | Stage 5/6 源码不含 `_ONLYOFFICE_HTML_WHITELIST` / `_CONFIRMATION_COMPONENTS` 成员测试；`wp_render_config` 仅经 `types_from_source` 导出投影 |
| `_WP_CODE_OVERRIDE` | 仍为 wp→componentType 映射输入（允许）；不是 host 白名单 |
| fail-open 入 trace | `package_resolver_error:*` 等写入 `ClassificationResolution.fallback_reason` / `RenderDecision.fallback_reason` |

## Task 8 — materialize / finalize / 协调器

| AC | 证据 |
|----|------|
| 阶段函数 | `materialize_sheet` / `finalize_render_response` |
| 入口只编排 | `_get_render_config_impl` 七段 await/call；`test_orchestrator_preserves_seven_stage_order` |
| 阶段守卫 RED | `tests/test_render_pipeline_stage_guards.py`：交换 redirect/facts、删除 package fail-open、host_policy 替代白名单 |
| 特征测试 | `tests/test_render_config_pipeline_characterization.py`（既有） |
| golden | `capture_render_config_wire_golden.py --check`（真库 shape） |

**复现**：

```text
pytest backend/tests/test_render_config_pipeline_characterization.py backend/tests/test_render_pipeline_stage_guards.py backend/tests/test_wp_classification_pipeline.py -q
python backend/scripts/diagnose/capture_render_config_wire_golden.py --check
```
