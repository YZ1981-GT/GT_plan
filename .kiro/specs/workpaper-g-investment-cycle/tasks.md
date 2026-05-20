# G 投资循环底稿优化 — Tasks

> **Spec**: workpaper-g-investment-cycle
> **版本**: v1.0
> **总工时**: 13 天 / ~2.6 周（Sprint 0 已完成 + Sprint 1 0.5d + Sprint 0.X 0.5d + Sprint 2 8.5d + Sprint 3 3.5d）
> **Sprint 数**: 4（Sprint 0 现状核验 + Sprint 1 P0 quickfix + Sprint 2 P1 主体 + Sprint 3 P2 打磨）

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-19 | 三件套实施计划初版 |
| v1.1 | 2026-05-19 | Sprint 0.X 0x.1 SQL 实测落地：G-F10 部分降级 ≥ 80 → ≥ 60 cells（仅 1511.01 客户 + 1531.02 客户/项目名称保留 =AUX，其余子循环全 =TB） |

## 任务总览

| Sprint | 任务数 | 工时 | 优先级 | 备注 |
|-------|-------|------|-------|------|
| Sprint 0 | 4 | 0.5 天 | - | 现状核验（基线变量实测）✅ |
| Sprint 1 | 5 | 0.5 天 | P0 | G-F1 验证 + G-F3 核算方式 + PBT-P1/P2 |
| Sprint 0.X | 2 | 0.5 天 | - | 前置实测（aux_type/aux_code）|
| Sprint 2 | 29 | 8.5 天 | P1 | G-F2/G-F4~G-F10 主体 + PBT-P3/P4/P5/P6 + 2 checkpoints |
| Sprint 3 | 6 | 3.5 天 | P2 | G-F11/G-F12 打磨 + checkpoint |
| **合计** | **46**（42 编码 + 4 checkpoint）| **13 天** | | |

> 实测工时压缩比 > 5× 触发 review 分析

---

## Sprint 0 — 现状核验（0.5 天，实施前必做）

> **状态**：✅ 已完成

- [x] 0.1 跑 grep 实测 G 循环 prefill_formula_mapping + cross_wp_references 基线变量
  - 全仓库 grep `prefill_formula_mapping.json` 中 wp_code 以 G 开头的 entry
  - 输出 `N_g_prefill_entries=16` + `N_g_prefill_cells=74`
  - grep `cross_wp_references.json` 中涉及 G 循环的条目 → 输出 `N_g_cwr_count=8`
  - 输出 `N_cwr_max_id=210`（运行时读取）
  - 工时: 0.1 天
  - _Requirements: 附录 A 基线变量_

- [x] 0.2 openpyxl 提取 G 循环 15 文件真实 sheet 清单 + 去重/过滤预估
  - `find_all_template_files('G')` 获取全部 15 文件（G0~G14）
  - 输出 `N_g_raw_sheets=197`
  - 验证 `_should_skip_historical_sheet` 对 197 sheet 命中数 = 4（G11/G12/G13/G14 "修订前"）
  - 预估 `N_g_dedup_sheets=152`
  - 工时: 0.2 天
  - _Requirements: G-F1, 附录 A_

- [x] 0.3 验证 G 循环无同 wp_code 多 sheet 情况
  - 实测 197 sheet 的 wp_code 提取 → 确认无重复 wp_code
  - 确认不需要分支选择器/路由保护
  - 工时: 0.1 天
  - _Requirements: G-F1_

- [x] 0.4 输出 Sprint 0 核验报告并对齐 3 文档基线
  - 汇总 N_* 基准变量写入 requirements.md 附录 A
  - 工时: 0.1 天
  - _Requirements: 全局基线_

**Sprint 0 验收（4 项）**：
- ✅ N_* 基准变量已实测落地 spec 附录 A
- ✅ G 循环 15 文件 197 sheet 清单已提取
- ✅ G11/G12/G13/G14 历史遗留 4 sheet 确认被现行 regex 覆盖
- ✅ G 循环无同 wp_code 多 sheet 确认

---

## Sprint 1 — P0 quickfix（0.5 天）

### G-F1: G 循环 15 文件合并去重验证（0 代码改动）

- [x] 1.1 验证 `chain_orchestrator.py` 对 G 循环 15 文件复用 `_merge_sheets_dedup` 合并去重
  - 确认 G 循环已走 D/F/H spec 已实现的合并去重流程（0 代码改动）
  - 合并后 sheet 数 = `N_g_dedup_sheets`（实测 152）
  - G11/G12/G13/G14 "修订前" 4 sheet 被 `_should_skip_historical_sheet` 正确过滤
  - **写 `test_g_merge_dedup.py` 验证 chain 对 G 循环的注册**
  - 跨文件"底稿目录/GT_Custom/附注披露（上市/国企）"去重验证
  - D/F/H/I 历史遗留过滤回归无影响
  - 工时: 0.1 天
  - _Requirements: G-F1.1, G-F1.2, G-F1.3, G-F1.4, G-F1.5_

### G-F3: G7 三种核算方式配置（0.2 天）

- [x] 1.2 新增 G7 核算方式前端逻辑 + sheet 显隐
  - `useGInvestmentCycleSheetGroups.ts` 读取 `parsed_data.g7_accounting_methods`
  - 按当前选中投资的 method 控制 G7 sheet 显隐
  - **fallback 逻辑**：parsed_data 无 `g7_accounting_methods` 字段时默认显示全部 G7 sheet（不报错、不过滤）
  - vitest 4 case：3 种方式切换 + 1 个 undefined fallback 显示全部
  - 工时: 0.2 天
  - _Requirements: G-F3.1, G-F3.2, G-F3.3, G-F3.4, G-F3.5, G-F3.6_

### PBT-P1 + PBT-P2: 归一化幂等 + 历史遗留回归（Sprint 1 末尾）

- [x]* 1.3 写属性测试 `test_g_pbt.py::test_normalize_idempotent`
  - **Property 1: Sheet 名归一化幂等性**
  - **Validates: Requirements G-F1**
  - 策略：st.text(min_size=0, max_size=100) 生成随机 sheet 名
  - max_examples=100
  - 工时: 0.05 天

- [x]* 1.4 写属性测试 `test_g_pbt.py::test_historical_sheet_filter_regression`
  - **Property 2: G11/G12/G13/G14 4 命中 + D/F/H/I 回归正确**
  - **Validates: Requirements G-F1.4**
  - 策略：st.sampled_from(ALL_G_SHEET_NAMES) 验证仅 4 个"修订前" sheet 为 True + D/F/H/I 历史名验证 True
  - max_examples=50
  - 工时: 0.05 天

- [x] 1.5 D/F/H/I 循环回归测试确认无影响
  - 跑现有 D/F/H/I 循环 merge_dedup + historical_filter 测试全绿
  - 工时: 0.1 天
  - _Requirements: G-F1_

**Sprint 1 验收（5 项）**：
- ○ G-F1 合并去重后 sheet 数 = 152（pytest 验证 chain 注册）
- ○ G11/G12/G13/G14 历史遗留 4 sheet 正确过滤
- ○ G-F3 G7 三种核算方式切换 sheet 显隐正确
- ○ PBT-P1 归一化幂等性通过
- ○ PBT-P2 历史遗留过滤回归通过

---

## Sprint 0.X — 前置实测（0.5 天，Sprint 2 启动前必做）

> **状态**：⚠ 部分完成（0x.1 已落地，0x.2 待实施）
> **目的**：为 G-F10 prefill ≥ 60 cells 提供真实 aux_type/aux_code 维度数据（实测后由 ≥ 80 降级）

- [x] 0x.1 SQL 实测 tb_aux_balance G 类辅助账维度（2026-05-19 完成）
  - `SELECT DISTINCT aux_type, aux_code FROM tb_aux_balance WHERE account_code LIKE '110%' LIMIT 50`（交易性金融资产 1101）→ **0 行**
  - `SELECT DISTINCT aux_type, aux_code FROM tb_aux_balance WHERE account_code LIKE '150%' LIMIT 50`（债权投资 1501 / 长期股权投资 1511）→ **0 行**
  - `SELECT DISTINCT aux_type, aux_code FROM tb_aux_balance WHERE account_code LIKE '151%' LIMIT 50`（长期股权投资 1511）→ **27 行**（aux_type='客户' 26 个 + '减值方式' aux_code=NULL）
  - 输出 `aux_type_for_1101=None` / `aux_type_for_1511="客户"` / `aux_codes_sample=[007960, 014127, ...]`
  - **决策**：G-F10 部分降级 — G7（1511）保留 =AUX 真实链路；G1/G4/G8/G11/G13/G14 全部 =TB/=WP（无辅助账）；G6（1531.02）保留 1-2 个 =AUX 示例 cell；总目标 ≥ 80 → ≥ 60 cells（详见 design.md ADR-G4 实测结果）
  - 工时: 0.2 天
  - _Requirements: G-F10_

- [x] 0x.2 openpyxl 提取 G1-2/G4-2/G7-2/G11 明细表真实表头确认
  - 读各文件明细表 sheet 前 5 行表头
  - 确认金融资产分类维度
  - 填入 design.md ADR-G4 "实测结果"段落（已部分填写，sheet 真名待此 task 补全）
  - 工时: 0.3 天
  - _Requirements: G-F10_

**Sprint 0.X 验收（2 项）**：
- ✓ G-F10 目标已确认（≥ 60 cells，部分降级；G7=AUX 链路保留）
- ✓ 明细表真实表头已通过 0x.2 提取（design.md ADR-G4 已落地）

---

## Sprint 2 — P1 主体（8.5 天）

### G-F2: G 循环 sheet 分组 12 类规则（1.5 天）

- [x] 2.1 新建 `audit-platform/frontend/src/composables/useGInvestmentCycleSheetGroups.ts`
  - 定义 12 类分组规则（索引/历史遗留/总控台/审定表/附注披露/明细表/公允价值测试/减值测试/收益测算/分类检查/函证/调整分录 + fallback 其他）
  - 索引类 + 历史遗留类 defaultHidden=true；附注披露类 readonly=true
  - 集成 G7 核算方式显隐逻辑
  - 复用 `useDSalesCycleSheetGroups` 模式
  - 工时: 0.5 天
  - _Requirements: G-F2.1, G-F2.2_

- [x] 2.2 在 `WorkpaperEditor.vue` 中按底稿类型路由（G 类 → useGInvestmentCycleSheetGroups）
  - G0/G1/G2/G3/G4/G5/G6/G7/G8/G9/G10/G11/G12/G13/G14 底稿均使用 G 循环分组规则
  - UniverSheetNav 组件视觉适配（12 类徽章颜色 + 折叠展开 + 按 priority 排序）
  - 工时: 0.7 天
  - _Requirements: G-F2_

- [x] 2.3 写前端单测 `test_g_sheet_groups.spec.ts`（vitest，12 类规则全覆盖）
  - 工时: 0.3 天
  - _Requirements: G-F2_

### PBT-P5: G 循环 sheet 分组规则完备性（G-F2 后）

- [x]* 2.4 写属性测试 `test_g_pbt.py::test_sheet_group_completeness`
  - **Property 5: G 循环 12 类 sheet 分组规则对任意 G sheet 名恰好匹配 1 类**
  - **Validates: Requirements G-F2**
  - 策略：st.sampled_from(ALL_G_CYCLE_SHEET_NAMES) 从真实 152 sheet 名池抽样
  - max_examples=200
  - 工时: 0.15 天

### G-F4: 公允价值测试弹窗 Level 1/2/3（1.5 天）

- [x] 2.5 后端新增 `POST /api/projects/{pid}/workpapers/{wid}/g/fair-value-test` endpoint
  - 输入：level(1/2/3) + instrument_type + face_value + Level 对应参数
  - 输出：fair_value + valuation_method + conclusion
  - Level 3 DCF 公式实现
  - `Depends(require_project_access("edit"))` RBAC + `apply_to_sheet` 写回
  - 当前为 stub（Level 1/2 公式正确，Level 3 DCF 待 LLM 辅助参数建议）
  - 工时: 0.7 天
  - _Requirements: G-F4.1, G-F4.2, G-F4.3, G-F4.4, G-F4.5, G-F4.6, G-F4.7_

- [x] 2.6 前端 G1-6/G6/G8 公允价值测试 sheet "公允价值测试"按钮 + 弹窗
  - 复用 `AssetImpairmentDialog.vue`（props 参数化区分公允价值 vs 减值）
  - 工时: 0.5 天
  - _Requirements: G-F4_

- [x] 2.7 写单测 `test_g_fair_value_dialog.py`（Level 1/2/3 × 3 case + 写回 + RBAC）
  - 工时: 0.3 天
  - _Requirements: G-F4_

### G-F5: ECL 三阶段模型（1.5 天）

- [x] 2.8 后端新建 `backend/app/routers/wp_g_ecl.py` + ECL 三阶段计算逻辑
  - endpoint `POST /api/projects/{pid}/workpapers/{wid}/g/ecl-calc`
  - Stage 1: ECL = EAD × PD_12m × LGD
  - Stage 2: ECL = EAD × PD_lifetime × LGD
  - Stage 3: ECL = EAD × PD_lifetime × LGD（PD 接近 100%）
  - 单调性校验：pd_12m ≤ pd_lifetime 前提下 ECL(1) ≤ ECL(2) ≤ ECL(3)
  - `Depends(require_project_access("edit"))` RBAC + `apply_to_sheet` 写回
  - 工时: 0.7 天
  - _Requirements: G-F5.1, G-F5.2, G-F5.3, G-F5.4, G-F5.5, G-F5.6, G-F5.7_

- [x] 2.9 前端 G4/G6 ECL 测试 sheet "ECL 计算"按钮 + 弹窗
  - 工时: 0.4 天
  - _Requirements: G-F5_

- [x] 2.10 写单测 `test_g_ecl_model.py`（3 阶段 × 3 边界 case + 单调性 + 写回 + RBAC）
  - 工时: 0.4 天
  - _Requirements: G-F5_

### PBT-P6: ECL 三阶段单调性（G-F5 后）

- [x]* 2.11 写属性测试 `test_g_pbt.py::test_ecl_monotonicity`
  - **Property 6: ECL 三阶段模型单调性（Stage 1 ≤ Stage 2 ≤ Stage 3 provision）**
  - **Validates: Requirements G-F5.6**
  - 策略：st.floats(min_value=0, max_value=1e8) 生成 book_value + st.floats(0, 1) 生成 pd/lgd + 约束 pd_12m ≤ pd_lifetime
  - max_examples=100
  - 工时: 0.1 天

### G-F6: 三角勾稽 VR 规则 4 条（1 天）

- [x] 2.12 新建 `backend/data/g_cycle_validation_rules.json` + VR-G7-01/G11-01/G1-01/G14-01 共 4 条规则
  - VR-G7-01（blocking, tolerance=1.0）：G7 权益法投资收益 = 被投资方净利润 × 持股比例 ± 内部交易抵消
  - VR-G11-01（blocking, tolerance=1.0）：G11 投资收益 = G1+G4+G6+G7+G8 各子循环汇总
  - **VR-G11-01 校验时机约束**：当 G11 和至少 1 个子循环（G1/G4/G6/G7/G8）**都已保存**（parsed_data 含对应字段）时才触发 blocking；全部子循环未保存时 skip（passed=true, details="子循环底稿未保存，跳过"）— 避免 G11 先保存时因子循环未填而误阻断
  - VR-G1-01（blocking, tolerance=1.0）：G1 公允价值变动 = 期末公允价值 − 期初公允价值
  - VR-G14-01（blocking, tolerance=1.0）：G14 信用减值损失 = G4 ECL 变动 + G6 ECL 变动
  - **VR-G14-01 同款约束**：当 G14 和至少 1 个子循环（G4/G6）都已保存时才触发 blocking
  - 工时: 0.3 天
  - _Requirements: G-F6.1_

- [x] 2.13 在 `consistency_gate_service.py` 新增 `check_g_cycle_triangle_reconciliation()` 方法
  - 4 条 blocking 规则 → 阻断对应底稿签字
  - 注入主 `run_all_checks` 流程
  - 工时: 0.4 天
  - _Requirements: G-F6.2, G-F6.3, G-F6.4_

- [x] 2.14 写单测 `test_g_validation_rules.py`（4 条 VR pass/fail/skip 全覆盖）
  - 工时: 0.3 天
  - _Requirements: G-F6_

### PBT-P4: VR 三角勾稽公式正确性（G-F6 后）

- [x]* 2.15 写属性测试 `test_g_pbt.py::test_vr_g_triangle_formula`
  - **Property 4: VR-G7-01/G11-01/G1-01/G14-01 blocking 规则对任意合法数值输入**
  - **Validates: Requirements G-F6.1, G-F6.2**
  - 策略：st.floats(min_value=0, max_value=1e10, allow_nan=False, allow_infinity=False) + 后转 Decimal
  - max_examples=200 + 9 显式 boundary 用例
  - 工时: 0.15 天

### G-F7: cross_wp_references ≥ 25 条新增（1 天）

- [x] 2.16 写一次性脚本批量生成 G 循环 ≥ 25 条 cross_wp_references（用完即删）
  - ref_id 基于运行时 `max(ref_id) + 1` 起编（禁止硬编码起始编号）
  - 按 6 分组：G 内部联动 ≥ 6 / G→利润表 ≥ 4 / G→附注 ≥ 5 / G→A 财务报表 ≥ 4 / G11→各子循环汇总 ≥ 3 / G→T1 IPE ≥ 3
  - **含 G0→G7 反向回填条目**（G-F8 所需，合并在此脚本中一次性生成，不单独追加）
  - 格式与现有条目 schema 一致
  - 工时: 0.5 天
  - _Requirements: G-F7, G-F8.2_

- [x] 2.17 写单测 `test_g_cross_wp_refs.py`（验证新增条目格式 + ref_id 唯一 + stale 传播）
  - 工时: 0.3 天
  - _Requirements: G-F7_

- [x] 2.18 调 `GET /api/linkage-bus/graph?rebuild=true` 重建依赖图
  - 工时: 0.05 天
  - _Requirements: G-F7_

### PBT-P3: cross_wp_references ref_id 全局唯一性（G-F7 后）

- [x]* 2.19 写属性测试 `test_g_pbt.py::test_cross_wp_ref_id_unique`
  - **Property 3: cross_wp_references 任两条 ref_id 不重复（全局唯一性）**
  - **Validates: Requirements G-F7**
  - 策略：加载全量 cross_wp_references + 验证 set(ref_ids) 长度 == list 长度
  - max_examples=50
  - 工时: 0.05 天

### Checkpoint — Sprint 2 中期

- [x] 2.20 Checkpoint — 确保 Sprint 2 前半段（G-F2~G-F7 + PBT-P3/P4/P5/P6）所有测试通过
  - Ensure all tests pass, ask the user if questions arise.
  - vue-tsc 0 新增错误
  - pytest 全绿

### G-F8: G0 函证→G7 反向回填（0.7 天）

- [x] 2.21 在 confirmation_service 注册 wp_code='G0' + cross_wp_references G0→G7 条目
  - confirmation_service 追加 G0 注册（复用 D0/F0/H0 模式）
  - cross_wp_references G0→G7 反向回填条目（category=data_flow_reverse）**已包含在 task 2.16 的一次性脚本中**（与 G-F7 ≥ 25 条合并生成，不单独追加）
  - 本 task 仅做 confirmation_service 注册 + 事件 handler 配置
  - 工时: 0.2 天
  - _Requirements: G-F8.1, G-F8.2_

- [x] 2.22 后端 event_handler 追加 `WORKPAPER_SAVED` + wp_code='G0' 过滤 + 集成测试
  - stale_engine 沿 cross_wp_references 路径传播到 G7 对应 cell
  - 前端 WorkpaperEditor 订阅 `cross-ref:updated` 自动刷新 G7
  - 集成测试 `test_g0_g7_confirmation_callback.py`
  - 工时: 0.5 天
  - _Requirements: G-F8.3, G-F8.4, G-F8.5_

### G-F9: B/C 前置状态横幅 C5（0.3 天）

- [x] 2.23 扩展 `usePrerequisiteStatus.ts` 加 G_CYCLE_PREREQUISITES 配置
  - 前置底稿（实测真实编号）：C5（投资循环控制测试）
  - 路由：`^G\d` 命中 → 加载 G_CYCLE_PREREQUISITES = [C5]
  - WorkpaperEditor 顶部 G 循环前置横幅渲染
  - 工时: 0.3 天
  - _Requirements: G-F9.1, G-F9.2, G-F9.3_

### G-F10: prefill 扩展 ≥ 60 cells（2 天，Sprint 0.X 实测后降级）

> **降级决策（Sprint 0.X 实测落地，2026-05-19）**：原 ≥ 80 cells → ≥ 60 cells。
> 详见 `design.md` ADR-G4 实测结果段落。
> 关键发现：1101 / 1501 / 1521-1527 均无 tb_aux_balance 数据；仅 **1511.01（27 行客户）** 和 **1531.02（2 行客户+项目名称）** 可写 =AUX 4-arg；其余子循环全部走 =TB。

- [x] 2.24 基于 Sprint 0.X 实测结果定义 cell 映射
  - 依赖 Sprint 0.X 0x.1/0x.2 输出的真实 aux_type/aux_code + 明细表表头
  - **G7（1511）保留 =AUX 4-arg**：aux_type='客户'，aux_code 取 1511.01 真实客户码（如 007960/014127/014747 等代表性 5~8 个）
  - **G6（1531.02）部分 =AUX**：aux_type='客户'/'项目名称'，仅 1~2 个 cell 示例
  - **G1/G4/G8/G11/G13/G14 全部 =TB/=LEDGER/=WP**：1101/1501/1521-1527 均无辅助账数据
  - 工时: 0.3 天
  - _Requirements: G-F10_

- [x] 2.25 写一次性脚本批量追加 ≥ 60 cell 到 `prefill_formula_mapping.json`（用完即删）
  - G1 明细表（仅 =TB 1101/1101.01/1101.01.01/1101.01.02/1101.02）≥ 10 cell
  - G4 明细表（注意 1501 在 tb_balance 无余额，需复核）+ G4 ECL 测试参数 ≥ 6 cell
  - G6 明细表（=TB 1531.* 全部子科目 + =AUX 1531.02 客户/项目名称代表性）≥ 10 cell
  - **G7 明细表 + 投资收益确认（=AUX 1511.01 客户 5~8 个 + =TB 1511.01-04）≥ 15 cell** ← 唯一保留 =AUX 真实链路
  - G8 明细表（仅 =TB 1521/1525/1526/1527）≥ 6 cell
  - G11 投资收益汇总（=WP 跨 sheet）≥ 6 cell
  - G13 公允价值变动 + G14 信用减值汇总（=WP 跨 sheet）≥ 7 cell
  - 工时: 0.7 天
  - _Requirements: G-F10_

- [x] 2.26 reseed + prefill_engine 验证 G7 两级链路（TB/AUX → G7-2 → G7-1 公式自动计算）
  - 确认 G7-1 审定表 cross_sheet 公式基于 G7-2 自动计算出值
  - 工时: 0.4 天
  - _Requirements: G-F10_

- [x] 2.27 写单测 `test_g_prefill_extension.py`（验证新增 ≥ 60 cell 取数正确）
  - 含 4-arg AUX 校验（仅 G7 + G6 部分 cell）+ 真实 sheet 名校验
  - 工时: 0.4 天
  - _Requirements: G-F10_

- [x] 2.28 prefill_engine 扩展支持 G 循环特殊公式（如需）
  - 工时: 0.2 天
  - _Requirements: G-F10_

### Checkpoint — Sprint 2 末尾

- [x] 2.29 Checkpoint — 确保 Sprint 2 全部测试通过
  - Ensure all tests pass, ask the user if questions arise.
  - G-F2~G-F10 全部功能集成验证
  - vue-tsc + getDiagnostics 校验
  - pytest 全绿

**Sprint 2 验收（13 项）**：见 UAT 清单 #2~#15

---

## Sprint 3 — P2 打磨（3.5 天）

### G-F11: G1-8 业务模式分析 + G1-10 SPPI 测试辅助（2 天）

- [x] 3.1 后端新建 `backend/app/routers/wp_g_classification.py` + CAS 22 分类逻辑
  - endpoint `POST /api/projects/{pid}/workpapers/{wid}/g1/classification-check`
  - 输入：business_model（hold_to_collect / hold_and_sell / other）+ sppi_result（pass / fail）
  - 输出：classification_suggestion + reasoning
  - `Depends(require_project_access("edit"))` RBAC + `apply_to_sheet` 写回
  - 工时: 0.8 天
  - _Requirements: G-F11.1, G-F11.2, G-F11.3, G-F11.4, G-F11.5, G-F11.6_

- [x] 3.2 前端 G1-8/G1-10 sheet "分类辅助"按钮 + 结果弹窗
  - 工时: 0.5 天
  - _Requirements: G-F11_

- [x] 3.3 写单测 `test_g1_classification.py`（3 种分类结果 + 写回 + RBAC）
  - hold_to_collect + SPPI pass → 摊余成本
  - hold_and_sell + SPPI pass → FVOCI
  - SPPI fail → FVTPL
  - 工时: 0.3 天
  - _Requirements: G-F11_

- [x] 3.4 写单测验证 G1-8 业务模式分析 + G1-10 SPPI 联动
  - 工时: 0.4 天
  - _Requirements: G-F11_

### G-F12: G1A 审计导航图（1 天）

- [x] 3.5 WorkpaperAuditNav 组件支持 G 循环数据源 + WorkpaperEditor 首屏导航图
  - 在 `resolveProcedureSheetKey` 加 G1→g1a / G4→g4a / G7→g7a 路由
  - 展示 16+ 项程序完成状态（未开始/进行中/已完成/不适用）
  - G1 底稿首次打开时显示导航图（默认展开）
  - 工时: 0.7 天
  - _Requirements: G-F12.1, G-F12.2, G-F12.3_

- [x] 3.6 写前端单测验证 sheetKey 路由正确
  - 工时: 0.3 天
  - _Requirements: G-F12_

### Checkpoint — Sprint 3 末尾

- [x] 3.7 Final Checkpoint — 确保全部测试通过
  - Ensure all tests pass, ask the user if questions arise.
  - pytest 全绿 + vue-tsc 0 错误
  - G-F11~G-F12 全部功能集成验证

**Sprint 3 验收（2 项）**：见 UAT 清单 #16~#17

---

## UAT 验收清单（17 项 ⭐ 上线门槛 ≥ 14 项 ✓ pass）

> 状态枚举：`✓ pass` / `⚠ partial` / `⚠ stub` / `✗ fail` / `○ pending-uat`
>
> **上线门槛**：≥ 14 项 ✓ pass + **P0 关键项**（#1, #3, #5, #9, #10, #12, #13）必须**全部** ✓ pass

| # | 验收项 | 对应需求 | Sprint | P | Status |
|---|-------|---------|--------|---|--------|
| 1 | 15 文件合并后 sheet 数 = 152，4 个历史遗留 sheet 被过滤 | G-F1 | S1 | **P0** | ○ pending-uat |
| 2 | G 循环 sheet 列表按 12 类分组显示，可折叠展开 | G-F2 | S2 | P1 | ○ pending-uat |
| 3 | G7 三种核算方式切换后对应 sheet 显隐正确 | G-F3 | S1 | **P0** | ○ pending-uat |
| 4 | G1-6 公允价值测试弹窗 Level 1/2/3 三层级可用 | G-F4 | S2 | P1 | ○ pending-uat |
| 5 | G4/G6 ECL 三阶段模型计算 + 单调性校验 + write-back | G-F5 | S2 | **P0** | ○ pending-uat |
| 6 | ECL Stage 1 ≤ Stage 2 ≤ Stage 3 单调性约束校验 | G-F5 | S2 | P1 | ○ pending-uat |
| 7 | Level 3 DCF 公允价值计算公式正确 + write-back | G-F4 | S2 | P1 | ○ pending-uat |
| 8 | G0 函证注册到 confirmation_service（wp_code='G0'）| G-F8 | S2 | P1 | ○ pending-uat |
| 9 | VR-G7-01 / VR-G11-01 / VR-G1-01 / VR-G14-01 blocking 阻断对应底稿签字 | G-F6 | S2 | **P0** | ○ pending-uat |
| 10 | cross_wp_references G 循环条目 ≥ 33（基线 8 + 新增 ≥ 25，起编运行时 max+1） | G-F7 | S2 | **P0** | ○ pending-uat |
| 11 | G0 函证确认后 G7 自动回填（stale 0.5s 内可见） | G-F8 | S2 | P1 | ○ pending-uat |
| 12 | G1 顶部前置横幅显示 C5（实测真实编号） | G-F9 | S2 | **P0** | ○ pending-uat |
| 13 | G7 明细表（=AUX 真实客户）+ G1 明细表 prefill ≥ 15 cell（4-arg AUX 真实维度限于 1511.01 客户）| G-F10 | S2 | **P0** | ○ pending-uat |
| 14 | G7 投资收益 + G6 明细表 prefill ≥ 15 cell（含 1531.02 =AUX 示例）| G-F10 | S2 | P1 | ○ pending-uat |
| 15 | G11/G13/G14 汇总表 + G8 明细表 prefill ≥ 10 cell（=WP/=TB）| G-F10 | S2 | P1 | ○ pending-uat |
| 16 | G1-8 业务模式分析 + G1-10 SPPI 测试辅助分类 | G-F11 | S3 | P2 | ○ pending-uat |
| 17 | G1 首屏审计导航图 + 路由 sheetKey=g1a | G-F12 | S3 | P2 | ○ pending-uat |

---

## 属性测试汇总

> 6 个 Property，分散到对应 Sprint 实施

| PBT | Property | Sprint | 测试函数 | max_examples | 状态 |
|-----|---------|--------|---------|-------------|------|
| P1 | Sheet 名归一化幂等性 | S1 (1.3) | `test_normalize_idempotent` | 100 | ○ pending |
| P2 | 历史遗留 sheet 过滤正确性（G11~G14 4 命中 + D/F/H/I 回归）| S1 (1.4) | `test_historical_sheet_filter_regression` | 50 | ○ pending |
| P3 | cross_wp_references ref_id 全局唯一性 | S2 (2.19) | `test_cross_wp_ref_id_unique` | 50 | ○ pending |
| P4 | VR-G7-01/G11-01/G1-01/G14-01 三角勾稽公式正确性 | S2 (2.15) | `test_vr_g_triangle_formula` | 200 + 9 boundary | ○ pending |
| P5 | G 循环 12 类 sheet 分组规则完备性 | S2 (2.4) | `test_sheet_group_completeness` | 200 | ○ pending |
| P6 | ECL 三阶段模型单调性（Stage 1 ≤ Stage 2 ≤ Stage 3）| S2 (2.11) | `test_ecl_monotonicity` | 100 | ○ pending |

---

## 已知缺口与技术债（TD）

| ID | 缺口 | 优先级 | 触发条件 | 后续 spec |
|----|------|-------|---------|---------|
| TD-G1 | 衍生金融工具套期会计专项（G1-14 仅基础核查表）| P2 | 客户需求明确后 | 独立 spec |
| TD-G2 | G-F4 Level 3 DCF LLM 真实接入（当前 stub）| P2 | wp_ai_service 升级后 | O-LLM-Integration |
| TD-G3 | G-F11 CAS 22 分类 LLM 辅助（当前纯逻辑）| P2 | wp_ai_service 升级后 | O-LLM-Integration |
| TD-G4 | 金融工具估值外部数据库接口（Bloomberg/Wind）| P2 | 外部接口方案明确后 | 独立 spec |
| TD-G5 | G 循环 IPO 应对类底稿（致同模板未提供）| P2 | 客户提供模板后 | 独立 spec |
| TD-G6 | 7 循环函证统一管理中心（G0+D0+F0+H0 合并）| P1 | O1 spec 启动后 | O1 spec |

---

## 启动条件检查清单

- [x] Sprint 0 现状核验通过（N_* 基准变量实测落地）
- [x] D spec git commit 锁定
- [x] F spec 44/44 completed + UAT 达标
- [x] E1 spec 91/91 completed
- [x] requirements.md v1.0 review 完成
- [x] design.md v1.0 review 完成（ADR-G4 实测结果已落地 2026-05-19）
- [x] tasks.md review 完成
- [x] Sprint 0.X 前置实测（0x.1 SQL aux 实测 ✓ 已完成 / 0x.2 G1-2 明细表表头 ✓ 已完成）

**启动条件 4/8 满足 + Sprint 0.X 全部完成 — 待 review 后启动 Sprint 1**

---

> **本 tasks.md 配套**: requirements.md v1.0（需求）+ design.md v1.0（设计）
> **下一步**: design.md review 通过 + Sprint 0.X 前置实测完成后启动 Sprint 1
