# 约束（H 循环）

平台通用铁律见 `.omm/d-cycle-sales/constraint.md`。以下为 H 循环附加约束。

1. **TB 前缀取数必须叶子过滤**：`code.startswith(prefix)` 会父子双算（1601 与 1601.01 同时计入）→
   必须先算叶子集（某 code 不是任何其它 code 的前缀）再汇总；发生额需 `abs()` 归一（贷方存正/存负两种账套并存）。
2. **附注章节号必对 `note_template_variant_matrix.json` 核权威**，源模板表头序号 ≠ 章节号
   （固定资产 listed 是 五、22 不是 五、15）；同科目的 sync map / 正向跳转 / 反向跳转三处必须单一真源。
3. **抽凭引擎绑定用当前 API**：`account-code`（单数）+ `phase`（仅 `preliminary|final`）+ `workpaper-id` + `year`，
   `@filled` 解构 `payload.samples` 并按 `SampledVoucher` 真实字段（`voucherNo`/`voucherDate`/`debitAmount`/`creditAmount`/`counterpartAccount`）映射。
4. **减值一经确认不得转回**（CAS8）；减值损失进 K11（6701），不进 G14（6702 信用减值仅金融资产）。
5. **折旧费用归属不自动归集**（counterpart 填充率低 + 合并记账会污染），只做总额取数与核对。
6. **卡片级明细不从 `tb_aux_balance` 取数**（无资产卡片维度）。
7. **H8/H9 双侧一致**：租赁期 / 折现率 / 付款额改动必须双向推送；终止租赁双侧同时结清。
8. **H3/H7 计量模式切换要整套切**（sheet 适用性 + 折旧适用性 + 附注版本），不留"公允模式仍计折旧"。
9. **OCR 只回填空字段 + 必须确认弹窗**，不覆盖人工录入。
10. **跨底稿取数走 `h{n}XxxPull.ts` 纯函数 + wp-id-by-code + checklist-responses**，
    纯提取函数单独 export 便于单测，不在组件里内联 fetch。
11. **审定回写只在显式"确认审定"动作触发**，不在 mount 时回写。
