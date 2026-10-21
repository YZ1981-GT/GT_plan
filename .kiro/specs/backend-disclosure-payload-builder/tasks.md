# 后端披露表 payload builder — 任务清单

## Phase 1：基础设施

- [x] 1. 新建 `disclosure_payload_builder_service.py`：builder 注册表 + `build_for_wp_code()` 入口
  - 已实现：PayloadBuildResult / DisclosurePayloadBuilder ABC / register_builder / _BUILDER_REGISTRY / build_for_wp_code / build_and_sync
  - 已被 `note_disclosure_refresh_service.py` 引用
- [x] 2. 实现 `load_disclosure_entries()`：从 checklist_responses 按 wp_code 读数据
  - 🔴 **已修：SQL 原含 `cr.is_deleted = false`（checklist_responses 表无此列），已删除该条件**
- [x] 3. 定义 `PayloadBuildResult` 数据类 + `DisclosurePayloadBuilder` 抽象基类
- [x] 4. 接入 `WORKPAPER_SAVED` handler
  - `build_and_sync()` 已由 `note_disclosure_refresh_service.py` 引用
  - `_ensure_builders_loaded()` 懒加载：首次调用自动 import `disclosure_builders` 包

## Phase 2：第一批核心 8 科目

- [x] 5. E1 货币资金 builder（主表 6/8 行 + 受限明细 + 披露说明，16 个单测全绿）
- [x] 6. D1 应收票据 builder（3 行，从 D1-adj-tb-amount 取审定数）
- [x] 7. D2 应收账款 builder（7 行账龄，从 555KB JSON 聚合 agingAudited）
- [x] 8. F2 存货 builder（7 行，6 字段 end_gross/end_impairment/end_net/prior_*）
- [x] 9. H1 固定资产 builder（2 行，从 H1-1-audited-net）
- [x] 10. I1 无形资产 builder（2 行，从 I1-1-audited-net）
- [x] 11. G7 长期股权投资 builder（2 行，真库合计 40,459,060.60）
- [x] 12. K1 其他应收款 builder（9 行账龄，从 K1-note-{variant}-rows JSON 解析）
- [x] 13. 第一批一致性测试：44 个单测全绿（注册表 + 核心 8 builder 回归 + 契约）

## Phase 3：第二批次核心 15 科目

- [x] 14. D3~D7 builder（5 个，standard_builder 工厂批量注册）
- [x] 15. F1 F3~F4 builder（3 个）
- [x] 16. H2~H10 builder（8 个，含 H5~H9）
- [x] 17. I2~I6 builder（5 个）
- [x] 18. 第二批一致性测试：12 个 parametrize 用例全绿（D3/D5/F1/F3/G1/H2/I2/J1/K2/L1/M2/N1）

## Phase 4：第三批剩余 46 科目

- [x] 19. G 循环剩余 builder（G1~G6 G8~G14，13 个）
- [x] 20. J/K 循环 builder（J1~J2 K2~K13，14 个）
- [x] 21. L 循环 builder（L1~L8，7 个）
- [x] 22. M 循环 builder（M1~M10，10 个）
- [x] 23. N 循环 builder（N1~N5，4 个）
- [x] 24. 第三批一致性测试：与 Phase 3 合并，standard_builder parametrize 覆盖全循环

## Phase 5：全量回归

- [x] 25. 全量 dry-run：78 个 builder 对真库和平药房_2025 执行
  - 76 成功 / 2 无数据（H5 listed=None + M3 soe=None）/ 0 失败
- [x] 26. 性能基准：全量 0.19s = **2ms/科目**（目标 500ms/科目，远超）
  - 44 个单测 1.42s 全绿
