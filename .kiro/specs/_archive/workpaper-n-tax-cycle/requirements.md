# N 税金循环底稿优化 — Requirements

> **Spec**: `workpaper-n-tax-cycle` | **版本**: v1.0 | **基线日期**: 2026-05-19

## 〇、依赖矩阵

| 上游 spec | 状态 | 本 spec 依赖 |
|-----------|------|------------|
| `workpaper-d-sales-cycle` | ✅ | `_normalize_sheet_name` / `_merge_sheets_dedup` / `_should_skip_historical_sheet` / 4-arg AUX |
| `workpaper-h-fixed-assets-cycle` | ✅ | VR 三角勾稽 / consistency_gate / `_ensure_ipo_loaded(prefix)` |
| `workpaper-j-payroll-cycle` | 待执行 | cross_wp_ref 起编须在 J+L 之后（运行时 max+1）|
| `workpaper-l-debt-cycle` | 待执行 | 同上 |

---

## 一、为什么做

### 业务痛点（7 类）
1. **N2 应交税费期末勾稽无自动校验**：期末=期初+计提−缴纳，涉及多税种
2. **N5 所得税费用与利润总额×税率无自动勾稽**：N5=利润总额×税率±递延调整
3. **N1/N3 递延所得税与暂时性差异无联动**：应与 H/F/G 各资产负债底稿联动
4. **N4 税金及附加与增值税无自动勾稽**：附加税=增值税×(7%+3%+2%)
5. **N 循环已有 14 条 cross_wp_ref 但仍有缺口**（N1/N3→各资产负债路径缺失；原 45 系与 dedup_sheets 混淆）
6. **前置底稿 C12 无联动**
7. **prefill 仅覆盖审定表层（6 entries / 28 cells）**

### 技术根因
- 历史遗留 1 个（`出口退税额复核示例`），现行 regex 已覆盖（0 代码改动）
- 末尾空格 1 个：`税金及附加审计程序表N4A `
- N 循环与所有循环都有联动（D增值税/J社保/L利息代扣/H房产税等）

---

## 一·B、Sprint 0 实测基线

| 变量 | 值 | 变量 | 值 |
|------|---|------|---|
| `N_n_files` | 5 | `N_n_raw_sheets` | 59 |
| `N_n_historical_sheets` | 1 | `N_n_dedup_sheets` | 45 |
| `N_n_trailing_space` | 1 | `N_n_prefill_entries` | 6 |
| `N_n_prefill_cells` | 28 | `N_n_cwr_count` | **14**（Sprint 0.2 实测修正，原 45 与 dedup_sheets 混淆）|

> **Sprint 0.2 偏差修正**：原 `N_n_cwr_count=45` 系与 `N_n_dedup_sheets=45` 混淆。
> 实测 cross_wp_references.json 中涉及 N 循环（source_wp 或 target wp_code 以 N+数字开头）的条目仅 14 条。
> N-F4 目标相应修正：14 + ≥10 = ≥ 24（而非原 ≥55）。
> CWR 起编：max(ref_id) = CW-369，N 循环新增起编 CW-370。

---

## 三、功能需求（N-F1 至 N-F8）

### N-F1 多文件合并 + 历史遗留过滤（P0）
- WHEN N 循环 5 文件合并时, THE chain_orchestrator SHALL 输出 45 有效 sheet（59-1-13）
- THE `_should_skip_historical_sheet` SHALL 命中 1 个（`出口退税额复核示例`）
- **量化**：59→45；0 代码改动

### N-F2 sheet 分组 8 类规则（P1）
- 索引/程序表/审定表/明细表/税费计算/递延所得税/附注+调整/其他
- 任意 N sheet 恰好匹配 1 类（PBT 验证）

### N-F3 三角勾稽 VR 规则 ≥ 2 条（P0）
- **VR-N2-01**（blocking）：N2 应交税费期末 = 期初 + 计提 − 缴纳
- **VR-N5-01**（warning）：N5 所得税费用 ≈ 利润总额 × 税率 ± 递延调整（N1变动−N3变动）
- VR-N5-01 涉及利润总额未保存时 skip（汇总类规则时机铁律）

### N-F4 cross_wp_references 新增 ≥ 10 条（P0）
- 起编运行时 max+1（当前 CW-370）；4 分组：N内部(≥2) / N→报表(≥3) / N→跨循环(≥3) / N→附注(≥2)
- 闭区间 + cycle membership 双重过滤；severity info < 25%
- **量化**：14 → ≥ 24（基线 Sprint 0.2 实测修正：原 45 系与 dedup_sheets 混淆）

### N-F5 前置状态横幅（P1）
- `N_CYCLE_PREREQUISITES = [C12]`（税金循环控制测试）
- `^N\d` 路由加载 C12 前置状态

### N-F6 prefill 扩展 ≥ 25 cells（P0）
- N1(≥6,=TB暂时性差异) / N2(≥8,=AUX按税种) / N3(≥4,=TB) / N4(≥4,=TB税种分项) / N5(≥3,=TB+=WP)
- 4-arg AUX 强制；sheet 字段含真实末尾空格（`税金及附加审计程序表N4A `）
- Sprint 0.X 实测 2221 应交税费 aux 维度；降级→仅=TB/=PREV ≥18 cells
- **量化**：28 → ≥ 53

### N-F7 所得税费用测算引擎 stub（P2）
- `POST .../n5/income-tax-calc`；税率调节表 + 递延调整 + apply_to_sheet + RBAC
- `is_llm_stub` 由 `settings.WP_AI_SERVICE_ENABLED` 驱动

### N-F8 IPO 占位（P2）
- `_IPO_CONFIG['N2']` 注册 codes=[]；全循环 IPO 回归

---

## 四、非功能需求

| 指标 | 目标 | 兼容性 |
|------|------|--------|
| chain 生成 | < 15s（5 文件） | D/E/F/G/H/I/J/L/M 不受影响 |
| VR 校验 | < 500ms | 不修改现有引擎 |

---

## 五、UAT 验收清单

| # | 验收项 | P | # | 验收项 | P |
|---|-------|---|---|-------|---|
| 1 | 合并后 45 sheet + 1 历史过滤 | P0 | 6 | N2 前置横幅 C12 | P1 |
| 2 | 8 类 sheet 分组 | P1 | 7 | N2 prefill ≥ 8 cell | P0 |
| 3 | VR-N2-01 blocking | P0 | 8 | N1 prefill ≥ 6 cell | P0 |
| 4 | VR-N5-01 warning | P1 | 9 | 所得税引擎+stub | P2 |
| 5 | cross_wp_ref ≥ 24 | P0 | 10 | IPO 注册+回归 | P2 |

**上线门槛**：≥ 8 项 ✓ + P0（#1/#3/#5/#7/#8）全部 ✓

---

## 六、测试矩阵

| 测试文件 | 覆盖 | PBT |
|---------|------|-----|
| `test_n_merge_dedup.py` | N-F1 | P1 归一化幂等(100) |
| `test_n_validation_rules.py` | N-F3 | P2 VR-N2-01(200+9) |
| `test_n_cross_wp_refs.py` | N-F4 | P3 分组完备(200) |
| `test_n_prefill_extension.py` | N-F6 | P4 ref_id唯一(50) |
| `test_n_sheet_groups.py` | N-F2 | |
| `test_n_income_tax_calc.py` | N-F7 | |

## 七、术语表

| 术语 | 定义 |
|------|------|
| N 循环 | 税金循环（N1递延所得税资产/N2应交税费/N3递延所得税负债/N4税金及附加/N5所得税费用，5文件）|
| 核心 VR | N2 期末=期初+计提−缴纳 / N5=利润总额×税率±递延调整 |
| C12 | 税金循环控制测试（前置底稿）|
| 暂时性差异 | 账面价值与计税基础之差（产生递延所得税）|
