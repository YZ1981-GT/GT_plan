# 待办（N 循环）

## 已立 spec 未实现

- **`n1-loss-check-source-alignment`**（requirements-first）：N1-5 未确认亏损结构重建
  （到期年度行/本期数三列/确认与不确认拆分/依据/应纳税所得额来源三选/检查底稿索引）+ 附注"未确认"节数据源

## 需 spec（未做）

- **N5-2 有效税率调节表重建**：源模板是审定利润总额 → 法定税率 → 各调整项 → 所得税费用的调节表，
  现渲染"当期/递延分项分解表"；跨前后端 >500 行（含导入导出）

## 需核实

- **N1/N3/N5 的辅助函数科目码/签名**：`n1_deferred_tax_assets_service` / `n2_taxes_payable_service` /
  `n3_deferred_tax_liabilities_service` 的 `get_tb_data` / `get_cross_wp_total` 曾有同款错列名 +
  `get_active_filter` 签名错（四参异步被当同步单参）→ 这几个函数无 router 调用方（次要）但仍待修
- **N4↔N2 车船税命名分歧**（N2"车船牌照税" vs N4"车船使用税"）是否需统一到源模板权威名

## 已知未做

- **N1 P0/P1 剩余**：N1-2↔N1-4 双录且带入方向反（源模板账面/计税基础在 N1-4，应 N1-4→N1-2 字段级带入）、
  N1-5→N1-4/N1-1 只读提示无回填按钮、N1-4 差异不推 N1-3 建议 AJE、TB 回写 watch 每次总额变化即 PUT（建议 debounce）、
  N1-1 审计说明/结论无异步 hydrate、孤儿死字段（`useN1EntryDualMode.ts`、`N1-1-adjudicated-amount` 前端从不写、
  `loss-check:recognizable-updated`/`deferred-tax:liability-from-n1` 无消费者）、主入口未 provide getThreadDot/getRowDot
- **N 循环附注结构化推送 + 跳转**：N1 已建 `n1NoteSectionMap` + `buildN1SyncPayload`（五、30/八、31，
  与 N3 共用节，owner 归 N1）+ 正反向跳转 + covergae 守卫；N2~N5 覆盖度待核
- **N1/N3 共用五、30/八、31 节**：前两张子表同表混资产段+负债段，owner 统一 N1，N3 不推共用表只发布跨底稿键

## 已完成（本平台历史）

- N1~N5 全部完成；N4（多税种测算与 N2 同源）
- N 循环跨表 dead-key 系统性修复（N2↔N4 计提勾稽、N5↔N1/N3/N4）
- N4/N5 render 策略 tb_balance 列名修复（begin_balance→opening_balance 等）
- N1 步骤 1-5 修复（get_active_filter 异步、hydrate、死链、IE 对齐、TB 核对、从明细带入）+ n1-disclosure-note-linkage spec
- N1/N2/N3 明细表默认种子；N3 递延所得税负债（真双模式 OO + AI 真实填充 + TB 预填 + N3-3 联动 + 快照）
