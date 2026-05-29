# N 税金循环底稿优化 — Tasks

> **Spec**: workpaper-n-tax-cycle | **版本**: v1.0
> **总工时**: 5 天 | **Sprint 数**: 5

## 任务总览

| Sprint | 任务数 | 工时 | 优先级 |
|-------|-------|------|-------|
| Sprint 0 | 3 | 0.35 天 | - |
| Sprint 0.X | 2 | 0.3 天 | - |
| Sprint 1 | 5 | 0.9 天 | P0 |
| Sprint 2 | 9 | 2.2 天 | P1 |
| Sprint 3 | 5 | 1.25 天 | P2 |
| **合计** | **24** | **5 天** | |

---

## Sprint 0 — 现状核验（0.35 天）

- [x] 0.1 openpyxl 提取 N 循环 5 文件真实 sheet 清单（59 raw / 1 历史 / 1 末尾空格）
- [x] 0.2 grep 实测 prefill(6/28) + cross_wp_ref(**14**, 原 45 系与 dedup_sheets 混淆) 基线变量 + **列出现有 14 条 N 循环 CWR 清单识别缺口路径**
- [x] 0.3 输出核验报告 + 对齐 3 文档基线

---

## Sprint 0.X — 前置实测（0.3 天，待实测标注）

- [x] 0x.1 SQL 实测 2221/1811 应交税费/递延所得税 aux 维度（降级判定）
- [x] 0x.2 openpyxl 提取 N1/N2/N3/N4/N5 明细表真实表头

---

## Sprint 1 — P0 核心（0.9 天）

- [x] 1.1 验证 chain_orchestrator N 循环合并（59→45）+ `test_n_merge_dedup.py`
  - _Requirements: N-F1_
- [x] 1.2 创建 VR-N2-01/N5-01 + `check_n_cycle_triangle_reconciliation()` + `test_n_validation_rules.py`
  - _Requirements: N-F3_
- [x] 1.3 追加 ≥10 条 cross_wp_ref（起编 max+1）+ `test_n_cross_wp_refs.py`
  - _Requirements: N-F4_
- [x] 1.4 追加 ≥25 cells prefill + `test_n_prefill_extension.py`
  - _Requirements: N-F6_
- [x] 1.5 D/F/H/I/G/J/L/M 回归验证

---

## Sprint 2 — P1 主体（2.2 天）

- [x] 2.1 新建 `useNTaxCycleSheetGroups.ts`（8 类规则）
- [x] 2.2 `test_n_sheet_groups.py` + vitest
- [x] 2.3 配置 N_CYCLE_PREREQUISITES=[C12] + `^N\d` 路由
- [x] 2.4 vitest 验证 N2 前置横幅 C12 状态
- [x] 2.5 resolveProcedureSheetKey N2→n2a / N5→n5a
- [x] 2.6 PBT-P1: 归一化幂等(100)
- [x] 2.7 PBT-P2: VR-N2-01 勾稽(200+9 boundary)
- [x] 2.8 PBT-P3: 8 类分组完备(200)
- [x] 2.9 PBT-P4: ref_id 唯一(50)

---

## Sprint 3 — P2 打磨（1.25 天）

- [x] 3.1 新建 `wp_n_income_tax_calc.py` 路由 + RBAC + apply_to_sheet + `test_n_income_tax_calc.py`
  - _Requirements: N-F7, ADR-N4_
- [x] 3.2 新建 `IncomeTaxCalcDialog.vue` 前端弹窗
- [x] 3.3 `_IPO_CONFIG['N2']` 注册 + 全循环 IPO 回归 + `test_n_ipo_trigger.py`
  - _Requirements: N-F8_
- [x] 3.4 全量回归 + 10 项 UAT 验收
- [x] 3.5 复盘 + 已知缺口标注

---

## 已知缺口

| # | 项 | 决策 | 原因 |
|---|-----|------|------|
| 1 | N4 税金及附加真实科目编号未确认 | prefill 暂用 =TB 占位 | 6401 实为营业成本，6403 待确认 |
| 2 | N2 =AUX aux_code 覆盖度有限 | 仅覆盖 6 个代表值 | '税率'维度 18 codes 中取 13%/9%/6%/0%/免税/即征即退 |
| 3 | N5 截断 sheet 名缺右括号 | 不影响功能 | 模板原始数据：'附注披露信息（国企' 缺 ')' |
| 4 | 所得税引擎为 stub | 待 wp_ai_service 接入后切换 | is_llm_stub=True，config 驱动 |
| 5 | N2 IPO codes=[] 占位 | 无实际内容 | 无 IPO 应对底稿 |
| 6 | VR-N5-01 递延调整跨底稿联动未实现 | 仅从 N5 parsed_data 读取 | N1/N3 变动数据需跨底稿联动 |
| 7 | CWR 基线从 45 修正为 14 | 已修正，新增≥10→目标≥24 | Sprint 0.2 偏差：原与 dedup_sheets 混淆 |
| — | 转让定价分析 | 不做 | 外部数据源 |
| — | 出口退税复核 | 不做 | 已过滤为历史遗留 |

---

## 测试矩阵

### pytest
| 文件 | 覆盖 | Sprint |
|------|------|--------|
| `test_n_merge_dedup.py` | N-F1 | S1 |
| `test_n_validation_rules.py` | N-F3 | S1 |
| `test_n_cross_wp_refs.py` | N-F4 | S1 |
| `test_n_prefill_extension.py` | N-F6 | S1 |
| `test_n_sheet_groups.py` | N-F2 | S2 |
| `test_n_income_tax_calc.py` | N-F7 | S3 |
| `test_n_ipo_trigger.py` | N-F8 | S3 |

### PBT
| ID | Property | examples |
|----|---------|----------|
| P1 | 归一化幂等 | 100 |
| P2 | VR-N2-01 勾稽 | 200+9 |
| P3 | 8类分组完备 | 200 |
| P4 | ref_id唯一 | 50 |

### vitest
`test_n_sheet_groups.spec.ts` / `IncomeTaxCalcDialog.spec.ts` / `test_n_prerequisite.spec.ts` / `test_n_audit_nav.spec.ts`

---

## 启动条件

- [x] D/F/H/I/G spec 全部完成
- [x] J+L spec 执行完毕（cross_wp_ref 起编依赖）— J ✅ + L ✅ 均已完成
- [x] Sprint 0 + Sprint 0.X 完成
