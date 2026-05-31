# ADR-CONSOL-204: cross_template 随 V2 接线（接通国企↔上市孤儿）

## 状态
已接受 (2026-05-30)

## 背景

`consol_cross_template_service`（3 API：translate_child_section / aggregate_cross_template / build_cross_template_provenance）已写好但 **0 router 引用，仅文件内部互调**（与 generate_full_consol_notes 并列"两大孤儿"，且是用户点名 5 大能力之一）。接 V2 附注时若不一并接 cross_template，国企子公司↔上市母公司混合集团的附注汇总仍不可用。

## 决策

- cross_template 随 V2 附注汇总路径接线：`generate_full_consol_notes` → `_aggregate_common_section(consol_type=...)` → `_maybe_apply_cross_template` → `apply_cross_template_to_children` → `translate_child_section` + `build_cross_template_provenance`（live 调用，消除孤儿）。
- `_fetch_subsidiary_list` 补每个子公司的 `Project.template_type`（批量 IN 查询，失败降级 None=视为同模板）。
- feature flag 受控：仅 `CONSOL_NOTES_V2_ENABLED AND CONSOL_CROSS_TEMPLATE_ENABLED`（新增，默认 False，defense-in-depth）同时为 True 且存在跨模板子公司时才介入（同模板集团零开销短路）。
- 无匹配映射（unknown/target_only）或翻译异常 → 降级原样汇总 + warning（EH7）。
- **属性 S7（不丢章节）**：`apply_cross_template_to_children` 输出长度恒等于输入长度（每分支恰 append 一个 child），`_maybe_apply_cross_template` 加 `len(out)==len(in)` 防御断言。

## 后果

- 正向：消除第二个孤儿 + 国企↔上市混合集团附注可用。
- 代价：依赖 V2 启用（与 ADR-202 同前提）+ 真实映射卡审计师（Phase 4 mock CSV 替换）。
- 守门：S7 由 `test_consol_phase2_cross_template_pbt.py`（9 测试）验证任意翻译分类/异常下长度守恒 + 同模板透传 + 降级 warning。
