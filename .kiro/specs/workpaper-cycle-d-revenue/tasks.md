# Implementation Plan: D 收入循环底稿内容预设数据

## 变更记录

| 版本 | 日期 | 摘要 | 触发原因 |
|------|------|------|----------|
| v1.0 | 2026-05-17 | 初始版本 | design.md 审批通过 |

## Overview

将 design.md 的 7 项数据组件（D1-D7）转化为可执行的编码任务。本 spec 是纯数据 spec——只产出 JSON 配置文件 + 测试，不改动 prefill_engine.py 代码或前端 UI。

- Sprint 1（2 天）：扩展 prefill_formula_mapping.json（15 条）+ 扩展 cross_wp_references.json（18 条）+ 新建 d_cycle_validation_rules.json（21 条）+ 新建 d_cycle_procedures.json（8 底稿 × 5-7 步）
- Sprint 2（1 天）：属性测试（10 Properties）+ 集成测试（真实数据验证）+ JSON schema 校验 + 最终验收

实现语言：Python（pytest + hypothesis）/ JSON 数据文件

## Tasks

- [ ] 1. Sprint 1：JSON 数据文件创建与扩展
  - [ ] 1.1 扩展 prefill_formula_mapping.json——Analysis_Sheet 公式（8 条）
    - 在 `backend/data/prefill_formula_mapping.json` 的 mappings 数组中为 D0-D7 各新增 1 条 Analysis_Sheet 条目
    - 每条包含 `sheet` 为分析程序 sheet 名（如"分析程序D2-5"）、`cells` 含"上年审定数"（formula_type=PREV）和"本年未审数"（formula_type=TB 或 TB_SUM）
    - D4 等多科目底稿（account_codes 含 6001+6051）使用 `=TB_SUM('6001~6051','期末余额')` 聚合
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ] 1.2 扩展 prefill_formula_mapping.json——Detail_Sheet 公式（5 条）
    - 新增 D2 客户明细表条目：formula_type=TB_AUX, formula=`=TB_AUX('1122','客户','期末余额')`
    - 新增 D2 账龄分析表条目：formula_type=TB_AUX, formula=`=TB_AUX('1122','账龄','期末余额')`
    - 新增 D2 坏账准备计算表条目
    - 新增 D1 票据明细表条目（按类型/到期日分类）
    - 新增 D4 收入明细表条目（按产品/客户/地区分类）
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ] 1.3 扩展 prefill_formula_mapping.json——D5 子科目 + D0 函证覆盖率（2 条）
    - D5 条目新增 sub-account 级公式：`=TB('112401','期末余额')` + `=TB('112402','期末余额')`（当有子科目时）
    - D0 条目新增"函证覆盖率"cell：formula=`=WP('D2','审定表D2-1','审定数')`
    - D0 条目新增"函证金额合计"cell（引用函证明细 sheet 合计）
    - _Requirements: 11.1, 11.2, 11.3, 12.1, 12.2_

  - [ ] 1.4 扩展 cross_wp_references.json——D 循环内部引用（4 条 CW-21~CW-24）
    - CW-21: D2 审定数 → D0 函证确认金额（category=revenue_cycle, severity=warning）
    - CW-22: D4 营业收入审定数 → D2 应收周转率分析
    - CW-23: D3 预收款项变动 → D4 收入确认分析
    - CW-24: D2 坏账准备 → D5 应收款项融资减值
    - 条目结构复用现有 schema（ref_id/source_wp/source_sheet/source_cell/targets/category/severity）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ] 1.5 扩展 cross_wp_references.json——D 循环→附注引用（7 条 CW-25~CW-31）
    - CW-25: D2 → 附注 5.7 应收账款（target_type=note_section, note_section_code="5.7"）
    - CW-26: D4 → 附注 5.14 营业收入
    - CW-27: D1 → 附注 5.3 应收票据
    - CW-28: D3 → 附注 5.15 合同负债/预收款项
    - CW-29: D5 → 附注 5.5 应收款项融资
    - CW-30: D6 → 附注 5.6 合同资产
    - CW-31: D7 → 附注 5.15 合同负债
    - 每条含 target_route（如 `/projects/{pid}/disclosure-notes?section=5.7`）+ target_label
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [ ] 1.6 扩展 cross_wp_references.json——D 循环→报表引用（7 条 CW-32~CW-38）
    - CW-32: D2 → 报表 BS-005 应收账款行（target_type=report_row, report_row_code="BS-005"）
    - CW-33: D4 → 报表 IS-001 营业收入行
    - CW-34: D1 → 报表 BS-003 应收票据行
    - CW-35: D3 → 报表 BS-034 预收款项行
    - CW-36: D5 → 报表 BS-006 应收款项融资行
    - CW-37: D6 → 报表 BS-007 合同资产行
    - CW-38: D7 → 报表 BS-035 合同负债行
    - 每条含 target_route + report_row_code + severity=info
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

  - [ ] 1.7 新建 d_cycle_validation_rules.json——balance_check 规则（8 条）
    - 新建 `backend/data/d_cycle_validation_rules.json`
    - 为 D0-D7 各定义 1 条 balance_check 规则（rule_id DV-001~DV-008）
    - formula: `audited == unaudited + aje + rje`，tolerance=0.01，severity=blocking，scope=all_lines
    - cells 引用各底稿审定表的审定数/未审数/AJE调整/RJE调整列
    - message_template: "借贷不平衡: 审定数({audited}) ≠ 未审数({unaudited}) + AJE({aje}) + RJE({rje}), 差异={diff}"
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ] 1.8 扩展 d_cycle_validation_rules.json——tb_consistency 规则（8 条）
    - 为 D0-D7 各定义 1 条 tb_consistency 规则（rule_id DV-009~DV-016）
    - account_codes 与 prefill_formula_mapping.json 中对应底稿的 account_codes 保持一致
    - tolerance=0.01，severity=blocking
    - message_template: "与试算表不一致: 底稿审定数({wp_amount}) ≠ TB审定数({tb_amount}), 差异={diff}"
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ] 1.9 扩展 d_cycle_validation_rules.json——note_consistency 规则（3 条）
    - DV-017: D2 审定数 = 附注 5.7 应收账款合计（severity=warning）
    - DV-018: D4 审定数 = 附注 5.14 营业收入合计
    - DV-019: D1 审定数 = 附注 5.3 应收票据合计
    - skip_if_missing=true，skip_message="附注章节未生成，跳过一致性校验"
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ] 1.10 扩展 d_cycle_validation_rules.json——detail_total_check 规则（2 条）
    - DV-020: D2 客户明细表合计 = 审定数（detail_sheet="客户明细表D2-6"）
    - DV-021: D2 账龄分析表合计 = 审定数（detail_sheet="账龄分析表D2-7"）
    - tolerance=0.01，severity=blocking
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ] 1.11 新建 d_cycle_procedures.json——D2 应收账款程序（7 步）
    - 新建 `backend/data/d_cycle_procedures.json`
    - D2 步骤：获取明细→核对总账→函证→替代程序→坏账准备→截止测试→结论
    - 每步含 step_order/step_name/description/is_required/related_sheet/category/evidence_type
    - _Requirements: 10.1, 10.5, 10.6_

  - [ ] 1.12 扩展 d_cycle_procedures.json——D4 营业收入程序（6 步）
    - D4 步骤：获取收入明细→分析程序→截止测试→收入确认→关联方交易→结论
    - _Requirements: 10.2, 10.5, 10.6_

  - [ ] 1.13 扩展 d_cycle_procedures.json——D0 函证程序（7 步）
    - D0 步骤：确定函证范围→编制函证→发函→回函统计→替代程序→差异调查→结论
    - _Requirements: 10.3, 10.5, 10.6_

  - [ ] 1.14 扩展 d_cycle_procedures.json——D1/D3/D5/D6/D7 程序（各 5 步）
    - D1 应收票据：获取明细→核对→检查→减值→结论
    - D3 预收款项：获取明细→核对→分析→截止→结论
    - D5 应收款项融资：获取明细→核对→分类→减值→结论
    - D6 合同资产：获取明细→核对→履约→减值→结论
    - D7 合同负债：获取明细→核对→分析→截止→结论
    - _Requirements: 10.4, 10.5, 10.6_

- [ ] 2. Checkpoint - Sprint 1 数据完整性验证
  - 确认 prefill_formula_mapping.json 新增 15 条（8 Analysis + 5 Detail + 2 特殊）
  - 确认 cross_wp_references.json 新增 18 条（4 内部 + 7 附注 + 7 报表）
  - 确认 d_cycle_validation_rules.json 共 21 条（8 balance + 8 tb + 3 note + 2 detail）
  - 确认 d_cycle_procedures.json 共 8 底稿程序（D0 7步 + D2 7步 + D4 6步 + D1/D3/D5/D6/D7 各5步）
  - JSON 格式校验（python -m json.tool 无报错）
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Sprint 2：属性测试 + 集成测试 + 验证
  - [ ] 3.1 新建测试文件骨架
    - 新建 `backend/tests/test_d_cycle_revenue_properties.py`
    - 导入 hypothesis、json、pathlib
    - 加载 4 个 JSON 文件为 module-level fixtures
    - _Requirements: 1.3, 3.6, 4.8, 5.8_

  - [ ]* 3.2 Property 1: Analysis_Sheet formula coverage
    - **Property 1: Analysis_Sheet formula coverage**
    - **Validates: Requirements 1.1, 1.2, 1.3**
    - 验证 D0-D7 每个 wp_code 在 prefill_formula_mapping.json 中至少有 1 条 Analysis_Sheet 条目
    - 每条含"上年审定数"（PREV）和"本年未审数"（TB/TB_SUM）两个 cell

  - [ ]* 3.3 Property 2: Multi-account TB_SUM consistency
    - **Property 2: Multi-account TB_SUM consistency**
    - **Validates: Requirements 1.4**
    - 验证 account_codes 含多个编码的条目，Analysis_Sheet 使用 TB_SUM 而非单独 TB

  - [ ]* 3.4 Property 3: D-cycle internal reference categorization
    - **Property 3: D-cycle internal reference categorization**
    - **Validates: Requirements 3.6**
    - 验证 source_wp 和 target wp_code 都在 D0-D7 范围内的引用，category=revenue_cycle 且 severity=warning

  - [ ]* 3.5 Property 4: Cross-module reference structural completeness
    - **Property 4: Cross-module reference structural completeness**
    - **Validates: Requirements 4.8, 5.8**
    - 验证 target_type=note_section 的条目含 target_route + note_section_code
    - 验证 target_type=report_row 的条目含 target_route + report_row_code

  - [ ]* 3.6 Property 5: Balance check validation correctness
    - **Property 5: Balance check validation correctness**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
    - 用 hypothesis 生成随机金额四元组（audited, unaudited, aje, rje）
    - 验证 |audited - (unaudited + aje + rje)| > 0.01 时产出 blocking finding
    - 验证 |audited - (unaudited + aje + rje)| <= 0.01 时无 finding
    - max_examples=50

  - [ ]* 3.7 Property 6: TB consistency validation correctness
    - **Property 6: TB consistency validation correctness**
    - **Validates: Requirements 7.1, 7.2, 7.3**
    - 用 hypothesis 生成随机 wp_amount/tb_amount 对
    - 验证差异超容差时产出 blocking finding，容差内无 finding
    - max_examples=50

  - [ ]* 3.8 Property 7: Cross-file account code consistency
    - **Property 7: Cross-file account code consistency**
    - **Validates: Requirements 7.4**
    - 加载 prefill_formula_mapping.json 和 d_cycle_validation_rules.json
    - 验证每个 D 底稿的 tb_consistency 规则 account_codes 与 prefill_formula_mapping 审定表条目一致

  - [ ]* 3.9 Property 8: Procedure step schema and completeness
    - **Property 8: Procedure step schema and completeness**
    - **Validates: Requirements 10.4, 10.5**
    - 验证每个程序步骤含 step_order(int)/step_name(非空)/description(非空)/is_required(bool)/related_sheet(str|null)
    - 验证 D0-D7 每个底稿至少 5 个步骤

  - [ ]* 3.10 Property 9: Sub-account dynamic formula generation
    - **Property 9: Sub-account dynamic formula generation**
    - **Validates: Requirements 11.1, 11.2**
    - 验证 D5 条目含子科目级 TB 公式（112401/112402）或单一 TB('1124',...) 公式

  - [ ]* 3.11 Property 10: Validation rule tolerance symmetry
    - **Property 10: Validation rule tolerance symmetry**
    - **Validates: Requirements 6.2, 9.4**
    - 用 hypothesis 生成边界值（恰好等于容差 / 略超容差）
    - 验证 |diff| == tolerance 时 pass，|diff| > tolerance 时 fail
    - max_examples=50

  - [ ] 3.12 集成测试：真实数据验证（陕西华氏 D2）
    - 新建 `backend/tests/test_d_cycle_validation_integration.py`
    - 验证 D2 的 tb_consistency 规则 account_codes=["1122"] 与 prefill_formula_mapping 一致
    - 验证 D2 balance_check 规则结构完整（cells 含 audited/unaudited/aje/rje 四个引用）
    - 验证 cross_wp_references CW-25 target 指向附注 5.7（note_section_code="5.7"）
    - 验证 d_cycle_procedures D2 步骤数 = 7 且包含"函证"和"坏账准备"
    - _Requirements: 全部 12 个需求的交叉验证_

  - [ ] 3.13 JSON Schema 校验测试
    - 在集成测试中验证 d_cycle_validation_rules.json 的 rule_type 枚举值仅含 balance_check/tb_consistency/note_consistency/detail_total_check
    - 验证 d_cycle_procedures.json 每个 step 的 category 枚举值合法（substantive/confirmation/conclusion）
    - 验证 cross_wp_references.json 新增条目的 ref_id 唯一性（CW-21~CW-38 无重复）
    - 验证 prefill_formula_mapping.json 新增条目的 formula_type 枚举值合法（TB/TB_SUM/PREV/TB_AUX/WP）
    - _Requirements: 全部需求的结构完整性_

- [ ] 4. Final checkpoint - 全部验证通过
  - 运行 `python -m pytest backend/tests/test_d_cycle_revenue_properties.py backend/tests/test_d_cycle_validation_integration.py -v --tb=short`
  - 确认所有属性测试和集成测试通过
  - 确认 4 个 JSON 文件格式正确且可被 json.load 正常解析
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 本 spec 是纯数据 spec，不涉及 prefill_engine.py 代码改动或前端 UI 变更
- 所有 JSON 条目结构复用现有 schema，无需新建 Alembic 迁移
- 属性测试使用 hypothesis 库（已安装 6.152.4），P0 关键属性 max_examples=50
- 真实数据验证基于陕西华氏项目 D2（1122 应收账款期末 6,290,044,665.30）
- d_cycle_procedures.json 步骤顺序遵循致同 2025 修订版审计程序模板
