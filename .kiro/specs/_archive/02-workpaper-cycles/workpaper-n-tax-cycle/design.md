# N 税金循环底稿优化 — Design

> **Spec**: `workpaper-n-tax-cycle` | **版本**: v1.0 | **配套**: requirements.md v1.0

## ADR 索引

| ADR | 标题 | 决策摘要 |
|-----|------|---------|
| ADR-N1 | 合并+历史过滤 | 复用现有（1命中，0代码改动）|
| ADR-N2 | VR 规则 | 2 条 VR + consistency_gate |
| ADR-N3 | prefill 维度 | 4-arg AUX + 末尾空格 sheet |
| ADR-N4 | 所得税引擎 | 税率调节表 + 递延调整 + stub |

---

## ADR-N1: 合并（Sprint 0 实测）

```python
N_n_raw_sheets = 59
N_n_historical_sheets = 1   # '出口退税额复核示例'（"示例"模式命中）
N_n_dedup_sheets = 45       # 59 - 1 - 13 = 45
N_n_trailing_space = 1      # '税金及附加审计程序表N4A '
N_n_prefill_entries = 6     # Sprint 0.2 实测确认
N_n_prefill_cells = 28      # Sprint 0.2 实测确认
N_n_cwr_count = 14          # Sprint 0.2 实测修正（原 45 系与 dedup_sheets 混淆）
# CWR 起编: CW-370 (max=CW-369)
```
决策：复用 `_merge_sheets_dedup` + `_should_skip_historical_sheet`，0 代码改动。

---

## ADR-N2: VR 规则

```json
[
  {"rule_id": "VR-N2-01", "severity": "blocking", "tolerance": 1.0,
   "formula": "N2_closing = N2_opening + N2_accrued - N2_paid",
   "trigger": "N2-1 saved"},
  {"rule_id": "VR-N5-01", "severity": "warning", "tolerance": 1.0,
   "formula": "N5_total = profit_before_tax * rate + deferred_adjustment",
   "trigger": "N5-1 AND PL saved"}
]
```
VR-N5-01 涉及利润表 → 汇总类规则时机铁律（利润总额未保存时 skip）。

---

## ADR-N3: prefill 维度

**Sprint 0.X 实测结果**（2026-05-20 task 0x.1 落地）：

```
tb_aux_balance 实测：
- 2221% 应交税费：3840 行，118 distinct (aux_type, aux_code)
  aux_type 分布：'税率'(18 codes, 1483 rows) / '抵扣方式'(7, 1024) / '区域2'(26, 772) / '成本中心'(42, 463) / '客户'(25, 98)
  子科目 23 个（2221.01~2221.99，含增值税/城建/教育/印花/所得税等）
  → ✓ 保留 =AUX(4-arg)，aux_type='税率' 最有业务价值（按税率区分增值税明细）

- 6401% 税金及附加：204654 行，13515 distinct (aux_type, aux_code)
  aux_type 分布：'客户'(12840, 68218) / '成本中心'(623, 68218) / '税率'(15, 65206) / '物流成本明细'(35, 2988) / '经营类往来款'(2, 24)
  ⚠ 注意：6401 实际是"营业成本"科目（非税金及附加），tb_balance 确认 6401=营业成本
  → N4 税金及附加实际科目应为 6403（待 0x.2 表头实测确认）

- 1811% 递延所得税资产：0 行 aux，但 tb_balance 有 423 行（8 个子科目：公允价值变动/资产减值准备/长期职工薪酬/可抵扣亏损/预提费用/递延收益/租赁年金）
  → ✗ 降级为 =TB only

- 1812% 递延所得税负债：0 行 aux，tb_balance 也 0 行
  → ✗ 降级为 =TB only（科目未使用）

- 6402% 税金及附加-其他：0 行 aux，tb_balance 也 0 行
  → ✗ 无数据

- 6801% 所得税费用：0 行 aux，tb_balance 有 165 行
  → ✗ 降级为 =TB only
```

**降级判定**：
- N2 应交税费（2221）：**保留 =AUX(4-arg)**，aux_type='税率' 按税率维度取数
- N4 税金及附加：6401 实为营业成本（数据错位），真实税金及附加科目待确认 → 暂降级 =TB
- N1 递延所得税资产（1811）：**降级 =TB**（有余额无辅助账）
- N3 递延所得税负债（1812）：**降级 =TB**（无数据）
- N5 所得税费用（6801）：**降级 =TB**（有余额无辅助账）

| sheet | cells | 公式 | 备注 |
|-------|-------|------|------|
| N1 递延资产明细 | ≥6 | =TB | 按 1811 子科目（8 类暂时性差异）|
| N2 应交税费明细 | ≥8 | =AUX(4-arg) | aux_type='税率'，按税率维度 |
| N3 递延负债明细 | ≥4 | =TB | 1812 无数据，仅占位 |
| N4 税金及附加明细 | ≥4 | =TB | 6401 实为营业成本，真实科目待确认 |
| N5 所得税费用 | ≥3 | =TB+=WP | 利润总额+税率+递延 |

**末尾空格铁律**：`'税金及附加审计程序表N4A '`
**降级结论**：仅 N2 保留 =AUX，其余降级 =TB/=PREV；总目标仍 ≥25 cells（不触发全面降级 ≥18 阈值）

---

## ADR-N4: 所得税费用测算引擎

```
POST /api/projects/{pid}/workpapers/{wid}/n5/income-tax-calc
Request: {profit_before_tax, statutory_rate, permanent_differences{}, temporary_differences{},
          deferred_tax_asset_change, deferred_tax_liability_change, apply_to_sheet}
Response: {current_income_tax, deferred_income_tax, total_income_tax, effective_rate,
           reconciliation_items[], is_llm_stub, applied_to_sheet}
```

**税率调节表逻辑**：
- 当期所得税 = (利润总额 + 永久性差异) × 法定税率
- 递延所得税 = -(递延资产变动 - 递延负债变动)
- 总所得税 = 当期 + 递延
- 有效税率 = 总所得税 / 利润总额

写回：`parsed_data.income_tax_calcs[sheet]`；RBAC：`require_project_access("edit")`

---

## Correctness Properties

| # | Property | 验证 |
|---|---------|------|
| CP-1 | VR-N2-01: drift∈[-2,2], passes↔|drift|<tol | PBT 200+9 |
| CP-2 | 8 类 sheet 分组完备（恰好 1 类）| PBT 200 |
| CP-3 | ref_id 全局唯一+闭区间 | PBT 50 |
| CP-4 | Sheet 名归一化幂等 | PBT 100 |

---

## 错误处理

| 场景 | 处理 |
|------|------|
| VR-N5-01 利润总额未保存 | skip 不 blocking |
| 所得税引擎 profit=0 | 返回 total=0（合法） |
| statutory_rate > 1.0 | 400 |
| AUX 无匹配 | COALESCE→0 |
| IPO codes=[] | empty result |
