# M 权益循环底稿优化 — Requirements

> **Spec**: `workpaper-m-equity-cycle` | **版本**: v1.0 | **基线日期**: 2026-05-19

## 〇、依赖矩阵

| 上游 spec | 状态 | 本 spec 依赖 |
|-----------|------|------------|
| `workpaper-d-sales-cycle` | ✅ | `_normalize_sheet_name` / `_merge_sheets_dedup` / `_should_skip_historical_sheet` / 4-arg AUX |
| `workpaper-h-fixed-assets-cycle` | ✅ | VR 三角勾稽 / consistency_gate / `_ensure_ipo_loaded(prefix)` |
| `workpaper-j-payroll-cycle` | 待执行 | cross_wp_ref 起编须在 J+L 之后（运行时 max+1）|
| `workpaper-l-debt-cycle` | 待执行 | 同上 |

---

## 一、为什么做

### 业务痛点（6 类）
1. **权益变动表勾稽无自动校验**：期末=期初+本期增减，当前无 VR 规则
2. **M6 未分配利润与利润表无自动勾稽**：M6 期末=期初+净利润−盈余公积−股利
3. **M9 其他综合收益与 G 公允价值变动无联动**
4. **prefill 仅覆盖审定表层（11 entries / 52 cells）**
5. **cross_wp_references M 相关仅 6 条**
6. **M 循环无独立控制测试**（由 A 类总体审计策略覆盖）

### 技术根因
- 历史遗留 4 个（3"修订前"+1"-删除"），现行 regex 已覆盖（0 代码改动）
- 末尾空格 3 个：`未分配利润实质性程序表 M6A ` / ` 专项储备实质性程序表 M7A ` / `一般风险准备实质性程序表 M8A `
- **已知数据问题**：wp_account_mapping 编号与模板文件编号不一致，**以模板文件 sheet 名为准**

---

## 一·B、Sprint 0 实测基线

| 变量 | 值 | 变量 | 值 |
|------|---|------|---|
| `N_m_files` | 10 | `N_m_raw_sheets` | 102 |
| `N_m_historical_sheets` | 4 | `N_m_dedup_sheets` | 65 |
| `N_m_trailing_space` | 3 | `N_m_prefill_entries` | 11 |
| `N_m_prefill_cells` | 52 | `N_m_cwr_count` | 8 |

### Sprint 0 偏差段

| 变量 | 起草值 | 实测值 | 偏差原因 | 修正方案 |
|------|--------|--------|---------|---------|
| `N_m_cwr_count` | 6 | 8 | L spec 执行后新增 CW-349/CW-352 两条以 M 为 target 的跨循环引用 | 基线修正 6→8；M-F4 目标同步 +2（保持 +15 新增不变）：≥ 21→≥ 23 |

> **偏差归零说明**：L spec 执行完毕后 `max(ref_id)=CW-352`，其中 CW-349（L→M2 实收资本关联）和 CW-352（L→M6 未分配利润关联）以 M 循环 sheet 为 target_wp，导致 M 基线 cross_wp_ref 从 6 升至 8。M spec 起编 CW-353，新增 ≥ 15 条目标不变，总量目标从 ≥ 21 调整为 ≥ 23。

---

## 三、功能需求（M-F1 至 M-F8）

### M-F1 多文件合并 + 历史遗留过滤（P0）
- WHEN M 循环 10 文件合并时, THE chain_orchestrator SHALL 输出 65 有效 sheet（102-4-33）
- THE `_should_skip_historical_sheet` SHALL 命中 4 个（3"修订前"+1"-删除"）
- **量化**：102→65；0 代码改动

### M-F2 sheet 分组 8 类规则（P1）
- 索引/程序表/审定表/明细表/变动分析/检查表/附注+调整/其他
- 任意 M sheet 恰好匹配 1 类（PBT 验证）

### M-F3 三角勾稽 VR 规则 ≥ 2 条（P0）
- **VR-M6-01**（blocking）：M6 期末 = 期初 + 净利润 − 盈余公积 − 股利
- **VR-M2-01**（warning）：M2 期末 = 期初 + 增资 − 减资
- VR-M6-01 涉及利润表净利润未保存时 skip（汇总类规则时机铁律）

### M-F4 cross_wp_references 新增 ≥ 15 条（P0）
- 起编运行时 max+1；4 分组：M内部(≥3) / M→报表(≥4) / M→附注(≥4) / M→跨循环(≥4)
- 闭区间 + cycle membership 双重过滤；severity info < 25%
- **量化**：8 → ≥ 23

### M-F5 前置状态横幅（P1）
- `M_CYCLE_PREREQUISITES = []`（无独立 C 类，由 A 类覆盖）
- `^M\d` 路由返回 ready

### M-F6 prefill 扩展 ≥ 30 cells（P0）
- M2(≥6,=AUX股东) / M4(≥6,=TB) / M5(≥4,=TB) / M6(≥8,=TB+=WP) / M9(≥4,=TB) / M10(≥2,=TB)
- 4-arg AUX 强制；sheet 字段含真实末尾空格
- Sprint 0.X 实测 4001/4002/4101/4104 aux 维度；降级→仅=TB/=PREV ≥20 cells
- **量化**：52 → ≥ 82

### M-F7 权益变动表引擎 stub（P2）
- `POST .../m6/equity-movement`；6 列变动汇总 + apply_to_sheet + RBAC
- `is_llm_stub` 由 `settings.WP_AI_SERVICE_ENABLED` 驱动

### M-F8 IPO 占位（P2）
- `_IPO_CONFIG['M2']` 注册 codes=[]；全循环 IPO 回归

---

## 四、非功能需求

| 指标 | 目标 | 兼容性 |
|------|------|--------|
| chain 生成 | < 30s | D/E/F/G/H/I/J/L 不受影响 |
| VR 校验 | < 500ms | 不修改现有引擎 |

---

## 五、UAT 验收清单

| # | 验收项 | P | # | 验收项 | P |
|---|-------|---|---|-------|---|
| 1 | 合并后 65 sheet + 4 历史过滤 | P0 | 6 | 前置状态=ready | P1 |
| 2 | 8 类 sheet 分组 | P1 | 7 | M6 prefill ≥ 8 cell | P0 |
| 3 | VR-M6-01 blocking | P0 | 8 | M2 prefill ≥ 6 cell | P0 |
| 4 | VR-M2-01 warning | P1 | 9 | 权益变动引擎+stub | P2 |
| 5 | cross_wp_ref ≥ 23 | P0 | 10 | IPO 注册+回归 | P2 |

**上线门槛**：≥ 8 项 ✓ + P0（#1/#3/#5/#7/#8）全部 ✓

---

## 六、测试矩阵

| 测试文件 | 覆盖 | PBT |
|---------|------|-----|
| `test_m_merge_dedup.py` | M-F1 | P1 归一化幂等(100) |
| `test_m_validation_rules.py` | M-F3 | P2 VR-M6-01(200+9) |
| `test_m_cross_wp_refs.py` | M-F4 | P3 分组完备(200) |
| `test_m_prefill_extension.py` | M-F6 | P4 ref_id唯一(50) |
| `test_m_sheet_groups.py` | M-F2 | |
| `test_m_equity_movement.py` | M-F7 | |

## 七、术语表

| 术语 | 定义 |
|------|------|
| M 循环 | 权益循环（M1应付股利/M2实收资本/M3库存股/M4资本公积/M5盈余公积/M6未分配利润/M7专项储备/M8一般风险准备/M9其他综合收益/M10其他权益工具）|
| 核心 VR | M6 期末=期初+净利润−盈余公积−股利（权益变动表勾稽）|
