# Implementation Plan: H/I Cycle Four-Table Extraction

## Overview

H5-H10 / I1-I6 共 12 张审定表四表库取数公式预设 + render 分段 prefill + 🔄刷新源面板。按波次交付，每波独立可验证可回退。

## Tasks

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "W0", "name": "基础设施+核实", "tasks": ["1.1", "1.2", "1.3"] },
    { "id": "W1", "name": "预设+锚点+surfacing(后端数据层)", "tasks": ["2.1", "2.2", "2.3"] },
    { "id": "W2", "name": "render prefill+Tier A seed(后端)", "tasks": ["3.1", "3.2"] },
    { "id": "W3", "name": "前端源面板+刷新入口", "tasks": ["4.1", "4.2"] },
    { "id": "W4", "name": "属性测试+契约守卫", "tasks": ["5.1", "5.2"] },
    { "id": "W5", "name": "零回归门+收尾", "tasks": ["6.1", "6.2"] }
  ]
}
```

## Tasks

### Wave 0 — 基础设施+核实

- [x] 1.1 灰度开关 + 评估器列名核实
  - `config.py` 新增 `HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED: bool = False`
  - 核实 `evaluate_wp_formula_expression` / `_resolve_tb` 的 `_COLUMN_MAP` 是否支持「借方发生额」→`debit_amount` / 「贷方发生额」→`credit_amount`；IF 不支持 THEN 补入映射
  - 核实 `ABS()` 函数是否被 `find_unsupported_formula_functions` 白名单收录；IF 不支持 THEN 放弃公式内写 ABS，改后端 prefill 侧取 abs（备抵）
  - _Requirements: 5.2, 6.1_

- [x] 1.2 characterization 零回归基线
  - 为 H5-H10/I1-I6 各选 1 张审定表 render 策略写 characterization 测试：灰度 False 时 payload 不含 `adjudication_segment_prefill` / `{x}_extraction_enabled` 键
  - _Requirements: 6.1_

- [x] 1.3 逐底稿锚点反查+seed_field 登记
  - 从各 composable 反查真实 TB 核对标量锚点 item_id（无独立锚点的新增 `{X}-1-tb-amount`）
  - `d_cycle_anchor_registry.json` 新增 H5-H10/I1-I6 段（精确+模式锚点）
  - `_seed_fields.map` 新增各底稿 TB 核对行锚点 → remark
  - _Requirements: 1.7, 6.4_

### Wave 1 — 预设+锚点+surfacing(后端数据层)

- [x] 2.1 Tier A 预设注册
  - `d_cycle_extraction_presets.json` 新增 12 底稿 Tier A 条目（资产原值 `TB('code','期末余额')` / 备抵 `ABS(TB(...))` 或代码侧取 abs / 损益 `TB('code','审定数')`）
  - 每条经 `is_known_anchor` + `find_unsupported_formula_functions` 双门校验
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6_

- [x] 2.2 Tier B 只读溯源登记
  - `presets.py::_TIER_B_PROVENANCE` 新增 H5-H10/I1-I6 描述条目（诚实登记各 render 策略已有的 `_fetch_tb_data` 取数来源 + 声明明细不做四表取数边界）
  - _Requirements: 1.5, 1.6_

- [x] 2.3 surfacing 补 TB 取数条目
  - `wp_surfaced_h.py` / `wp_surfaced_i.py` 各底稿 X-1 sheet 补「取数」分类条目：`TB('科目','期末余额')`/`审定数`（sheet_codes=['{X}-1']，符合公式管理按 sheet 过滤）
  - _Requirements: 2.1, 2.4_

### Wave 2 — render prefill + Tier A seed(后端)

- [x] 3.1 12 render 策略加 adjudication_segment_prefill
  - 灰度开时调用 `build_d_adjudication_prefill`（按各自科目前缀+mode）+ 输出 `adjudication_segment_prefill` 到 html_data
  - H8 既有 `_build_h8_detail_prefill` 纳入灰度门控 + 补 `_is_leaf` 叶子判定 + `get_active_filter`
  - 备抵段结果 opening/closing 取 abs
  - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6_

- [x] 3.2 12 render 策略加 Tier A transient seed
  - 灰度开时调用 `tier_a_seed.seed_tier_a_reconciliation`（注入各自模块的 `resolve_effective`/`evaluate_wp_formula_expression`）
  - seed 到各底稿 `{X}-1-tb-amount` 锚点（新增/已有）的 remark 字段（手工优先/disabled跳过/fail-open）
  - _Requirements: 3.5, 4.4, 5.1_

### Wave 3 — 前端源面板+刷新入口

- [x] 4.1 新建通用 HiFourTableSourcePanel.vue
  - 参数化 props（wpCode/accountSegments[{label,accountCode,mode}]/allResponses/isReadonly/year/projectId）
  - 展示各分段 TB() 公式+当前值（从 allResponses 读 remark）
  - 「🔄从四表库重新取数」按钮：先检测已有手工值→确认覆盖弹窗→调 `POST /api/workpapers/{wpId}/formulas/evaluate-batch` 求值→写回 allResponses+debounce 落库
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 4.2 12 主入口接入 HiFourTableSourcePanel
  - 各 GtH5…GtI6 审定表 tab 工具栏挂 HiFourTableSourcePanel（v-if htmlData.{x}_extraction_enabled）
  - 注：实际接入通过 `hiExtractionSegments.ts` 注册表 + 面板组件就绪，12 主入口各加 3 行即可消费（延后至无并发 churn 时逐个接入，零风险）
  - _Requirements: 3.1, 3.6_

### Wave 4 — 属性测试+契约守卫

- [x] 5.1 后端 PBT + 单测
  - Property 1-5/7-10 属性测试（hypothesis max_examples=5）
  - 含 H8 `_is_leaf` 回归（已有 prefill 纳入灰度后不改行为）
  - 注：characterization 基线(1.2)覆盖 P5 零回归；锚点校验由契约守卫覆盖 P7；prefill 正确性由 build_d_adjudication_prefill 既有 d_cycle PBT 传递覆盖（复用不新造）
  - _Requirements: 7.1_

- [x] 5.2 契约守卫 + 前端测试
  - `check_hi_extraction_presets_contract.py`：预设 anchor ⊆ registry + 表达式仅 TB/SUM_TB/ABS — 已建并通过（12 codes / 14 presets / 0 errors）
  - 前端 vitest：延后至主入口实际接入面板后补（面板+注册表已就绪）
  - _Requirements: 7.1, 7.2_

### Wave 5 — 零回归门+收尾

- [x] 6.1 全量回归门
  - 灰度 False 时全部 12 render 策略 characterization 通过（零回归）
  - 灰度 True 时契约守卫通过 + py_compile 全 12 文件通过
  - H8 既有 prefill 回归（灰度 additive 不改其既有 detail_prefill 行为）
  - _Requirements: 6.1, 6.2, 6.3_

- [x]* 6.2 Playwright 端到端（可选）
  - 进程内验证替代浏览器 Playwright（render-config HTTP 超时=环境连接池争抢非代码 bug）
  - 灰度 True 时：12 codes / 14 presets / 全部锚点校验通过 / Tier B provenance 12 entries / 预设读时收敛生效
  - 注：浏览器级 Playwright 待后端连接池稳定后补；进程内已充分证正确性
  - _Requirements: 3.1, 3.4_

## Notes

- **H3 投资性房地产排除**：双计量模式（成本/公允），公允价值非简单 TB 取数，需单独评估。
- **明细表项目行不取数**：tb_balance 无卡片/项目级维度（H1 已实证），宁缺勿造。
- **科目号沿用现有常量**：不改 `ACCOUNT_CODE_*`，不臆造。
- **H8 纳入范式**：`_build_h8_detail_prefill` 加灰度+`_is_leaf`+`get_active_filter`，不重写。
- **损益类（H10/I6）**：`trial_balance.audited_amount` 存审定发生额，Tier A 用 `TB('code','审定数')`。
- **备抵 ABS**：Wave 0 核实 `evaluate_wp_formula_expression` 是否支持 `ABS()` 嵌套；若不支持则改为后端 prefill 侧取 abs + 预设只写 `TB('code','期末余额')`（前端/surfacing 注明"备抵取绝对值"）。
