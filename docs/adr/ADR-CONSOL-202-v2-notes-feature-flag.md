# ADR-CONSOL-202: V2 附注 feature flag 灰度接线（不破坏老版）

## 状态
已接受 (2026-05-30)

## 背景

`generate_full_consol_notes`（V2，consol_disclosure_service.py，消费子公司单体附注汇总）是孤儿，consol_notes 路由 3 端点调的是老版 `generate_consol_notes_sync`（只生成 7 骨架章节不消费子公司数据）。直接切 V2 风险高（V2 未经真实数据验证）；且 V2 返回 `list[dict]`、老版返回 Pydantic `list[ConsolDisclosureSection]`，路由 `response_model` 约束导致不能裸切。

## 决策

- 新增开关 `CONSOL_NOTES_V2_ENABLED: bool = False`（默认老版兼容）。
- 新增统一入口 `generate_consol_notes_with_flag(db, project_id, year) -> list[ConsolDisclosureSection]`：flag=True 调 V2 + 经适配器 `_adapt_v2_sections_to_schema` 归一化为 Pydantic 契约；flag=False 调老版。
- **S4 契约归一化层**：`_adapt_v2_sections_to_schema` / `_adapt_v2_row_to_schema` 把任意 V2 dict（dict 行 / list 行 / 缺键 / None 行 / 非 dict 章节）映射为合法 `ConsolDisclosureSection`，保证路由 response_model 始终成立。
- V2 异常自动回退老版 + warning 日志（EH3/R2，不破坏既有可用性）。
- consol_notes 路由 3 端点（create/get/save）改调 `generate_consol_notes_with_flag`。

## 后果

- 正向：V2 接通且可灰度 + 老版兜底不破坏可用性；返回结构契约一致（S4）。
- 代价：双版本并存维护（待 Phase 4 真实数据验证后默认 V2 并收敛）。
- 守门：S4 由 `test_consol_phase2_v2_contract.py`（10 测试）验证适配器对任意 V2 形态永不抛错且字段集与老版一致。
