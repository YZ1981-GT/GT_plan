# F 类底稿（采购存货循环）— 设计文档

## 1. 架构总览

F 类底稿复用已验证的渲染管线（与 B/C/D/E 类一致）：

```
wp_account_mapping.json (扩充 F 类 ~80 条)
  → WpClassificationService (_WP_CODE_OVERRIDE)
    → get_render_config (componentType 分发)
      → 前端 htmlRendererRegistry → 对应 Vue 组件
```

### 1.1 设计决策

**不使用 generic schema**：F 类各科目结构差异极大：
- F2（存货）有 72+ 子底稿，涵盖审定/明细/政策/分析/盘点/检查/计价/跌价/关联/合同成本/IPO
- F1（预付）/F3（应付票据）/F4（应付账款）/F5（营业成本）结构相对简单

因此按 wp_code 逐一映射 componentType，不设 F-generic.yaml。

### 1.2 componentType 路由规划

| wp_code 模式 | componentType | 前端组件 | 说明 |
|-------------|--------------|---------|------|
| F0A/F1A/F2A/F3A/F4A/F5A | `a-program-console` | GtAProgramConsole | 程序表 |
| F0 | `confirmation-hub` | ConfirmationHub | 函证路由 |
| F0-1~F0-5 | `d-form-table` | GtDFormTable | 函证辅助表 |
| F{n}-1（各科目审定表） | `d-form-table` | GtDFormTable | 审定表 |
| F{n} 附注披露 sheet | `c-note-table` | DisclosureEditor | disclosure_notes |
| F1-2/F1-3/F2-2~F2-10/F3-2/F4-2/F4-3/F5-2 | `audit-sheet` | GtAuditSheet | 含复杂公式/大数据量明细 |
| F1-4/F2-11/F2-12/F2-13/F2-14/F2-52/F3-4/F4-4 | `d-form-table` | GtDFormTable | 坏账/跌价/调整分录/关联方（结构化） |
| F2-16 | `d-form-table` | GtDFormTable | 会计政策检查 |
| F2-18~F2-20 | `audit-sheet` | GtAuditSheet | 分析程序 |
| F2-21~F2-26 | `audit-sheet` | GtAuditSheet | 存货监盘 |
| F2-29~F2-35 | `audit-sheet` | GtAuditSheet | 检查程序 |
| F2-38~F2-44 | `audit-sheet` | GtAuditSheet | 计价测试 |
| F2-47~F2-49 | `audit-sheet` | GtAuditSheet | 跌价准备测试 |
| F2-55~F2-58 | `audit-sheet` | GtAuditSheet | 合同履约成本 |
| F2-61~F2-72 | `audit-sheet` | GtAuditSheet | IPO/舞弊应对 |
| F3-3/F3-5/F3-6/F4-5/F4-6/F5-3~F5-6 | `audit-sheet` | GtAuditSheet | 检查/分析 |

## 2. 数据模型

### 2.1 wp_account_mapping 扩充（从 8 → ~80 条）

现有 8 条：F0/F1/F2/F3/F4/F5/F1-2/F1-3/F4-2

需新增（按科目组列出）：

**G0 函证：**

| wp_code | wp_name | must_have |
|---------|---------|-----------|
| F0 | 存货循环函证 | true | 已有 |
| F0-1 | 函证结果汇总 | false | 新增 |
| F0-2 | 核实被函证单位 | false | 新增 |
| F0-3 | 跟函控制 | false | 新增 |
| F0-4 | 差异调节 | false | 新增 |
| F0-5 | 替代程序 | false | 新增 |

**G1 预付账款：**

| wp_code | wp_name | must_have |
|---------|---------|-----------|
| F1 | 预付账款审定表 | true | 已有 |
| F1-1 | 预付账款审定表 | true | 新增 |
| F1-2 | 预付账款明细表 | false | 已有（名称改） |
| F1-3 | 预付账款账龄分析 | false | 已有（名称改） |
| F1-4 | 预付账款坏账准备 | false | 新增 |
| F1-5 | 预付账款调整分录汇总 | false | 新增 |
| F1-6 | 预付账款检查 | false | 新增 |

**G2 存货（最大组）：**

| wp_code | wp_name | must_have |
|---------|---------|-----------|
| F2 | 存货及跌价准备审定表 | true | 已有 |
| F2-1 | 存货审定表 | true | 新增 |
| F2-2 | 存货分类明细 | false | 新增 |
| F2-3 | 存货增减变动 | false | 新增 |
| F2-4 | 原材料明细 | false | 新增 |
| F2-5 | 在产品明细 | false | 新增 |
| F2-6 | 库存商品明细 | false | 新增 |
| F2-7 | 在途物资明细 | false | 新增 |
| F2-8 | 委托加工物资明细 | false | 新增 |
| F2-9 | 工程施工明细 | false | 新增 |
| F2-10 | 开发产品明细 | false | 新增 |
| F2-11 | 跌价准备明细 | false | 新增 |
| F2-12 | 跌价准备变动 | false | 新增 |
| F2-13 | 存货调整分录汇总 | false | 新增 |
| F2-14 | 存货担保质押 | false | 新增 |
| F2-16 | 存货会计政策检查 | false | 新增 |
| F2-18 | 存货分析程序（一） | false | 新增 |
| F2-19 | 存货分析程序（二） | false | 新增 |
| F2-20 | 存货分析程序（三） | false | 新增 |
| F2-21 | 存货监盘计划 | false | 新增 |
| F2-22 | 盘点观察记录 | false | 新增 |
| F2-23 | 盘点抽盘测试 | false | 新增 |
| F2-24 | 存货截止测试 | false | 新增 |
| F2-25 | 盘点差异汇总 | false | 新增 |
| F2-26 | 监盘结论 | false | 新增 |
| F2-29 | 存货检查（一） | false | 新增 |
| F2-30 | 存货检查（二） | false | 新增 |
| F2-31 | 存货检查（三） | false | 新增 |
| F2-32 | 存货检查（四） | false | 新增 |
| F2-33 | 存货检查（五） | false | 新增 |
| F2-34 | 存货检查（六） | false | 新增 |
| F2-35 | 存货检查（七） | false | 新增 |
| F2-38 | 计价测试（一） | false | 新增 |
| F2-39 | 计价测试（二） | false | 新增 |
| F2-40 | 计价测试（三） | false | 新增 |
| F2-41 | 计价测试（四） | false | 新增 |
| F2-42 | 计价测试（五） | false | 新增 |
| F2-43 | 计价测试（六） | false | 新增 |
| F2-44 | 计价测试（七） | false | 新增 |
| F2-47 | 跌价准备测试（一） | false | 新增 |
| F2-48 | 跌价准备测试（二） | false | 新增 |
| F2-49 | 跌价准备测试（三） | false | 新增 |
| F2-52 | 存货关联交易检查 | false | 新增 |
| F2-55 | 合同履约成本（一） | false | 新增 |
| F2-56 | 合同履约成本（二） | false | 新增 |
| F2-57 | 合同履约成本（三） | false | 新增 |
| F2-58 | 合同履约成本（四） | false | 新增 |
| F2-61 | 存货IPO舞弊应对（一） | false | 新增 |
| F2-62 | 存货IPO舞弊应对（二） | false | 新增 |
| F2-63 | 存货IPO舞弊应对（三） | false | 新增 |
| F2-64 | 存货IPO舞弊应对（四） | false | 新增 |
| F2-65 | 存货IPO舞弊应对（五） | false | 新增 |
| F2-66 | 存货IPO舞弊应对（六） | false | 新增 |
| F2-67 | 存货IPO舞弊应对（七） | false | 新增 |
| F2-68 | 存货IPO舞弊应对（八） | false | 新增 |
| F2-69 | 存货IPO舞弊应对（九） | false | 新增 |
| F2-70 | 存货IPO舞弊应对（十） | false | 新增 |
| F2-71 | 存货IPO舞弊应对（十一） | false | 新增 |
| F2-72 | 存货IPO舞弊应对（十二） | false | 新增 |

**G3 应付票据：**

| wp_code | wp_name | must_have |
|---------|---------|-----------|
| F3 | 应付票据审定表 | true | 已有 |
| F3-1 | 应付票据审定表 | true | 新增 |
| F3-2 | 应付票据明细表 | false | 新增 |
| F3-3 | 应付票据检查 | false | 新增 |
| F3-4 | 应付票据调整分录汇总 | false | 新增 |
| F3-5 | 应付票据分析程序 | false | 新增 |
| F3-6 | 应付票据到期日分析 | false | 新增 |

**G4 应付账款：**

| wp_code | wp_name | must_have |
|---------|---------|-----------|
| F4 | 应付账款审定表 | true | 已有 |
| F4-1 | 应付账款审定表 | true | 新增 |
| F4-2 | 应付账款明细表 | false | 已有 |
| F4-3 | 应付账款账龄分析 | false | 新增 |
| F4-4 | 应付账款调整分录汇总 | false | 新增 |
| F4-5 | 应付账款检查 | false | 新增 |
| F4-6 | 应付账款分析程序 | false | 新增 |

**G5 营业成本：**

| wp_code | wp_name | must_have |
|---------|---------|-----------|
| F5 | 营业成本审定表 | true | 已有 |
| F5-1 | 营业成本审定表 | true | 新增 |
| F5-2 | 营业成本明细表 | false | 新增 |
| F5-3 | 成本结转测试 | false | 新增 |
| F5-4 | 毛利率分析 | false | 新增 |
| F5-5 | 营业成本检查 | false | 新增 |
| F5-6 | 营业成本分析程序 | false | 新增 |

### 2.2 _WP_CODE_OVERRIDE 完整映射表

```python
# F 类 — 采购存货循环实质性程序
# 函证
"F0": "confirmation-hub",
"F0-1": "d-form-table",
"F0-2": "d-form-table",
"F0-3": "d-form-table",
"F0-4": "d-form-table",
"F0-5": "d-form-table",
# 预付账款
"F1": "d-form-table",
"F1-1": "d-form-table",
"F1-2": "audit-sheet",
"F1-3": "audit-sheet",
"F1-4": "d-form-table",
"F1-5": "d-form-table",
"F1-6": "audit-sheet",
# 存货 - 审定明细
"F2": "d-form-table",
"F2-1": "d-form-table",
"F2-2": "audit-sheet",
"F2-3": "audit-sheet",
"F2-4": "audit-sheet",
"F2-5": "audit-sheet",
"F2-6": "audit-sheet",
"F2-7": "audit-sheet",
"F2-8": "audit-sheet",
"F2-9": "audit-sheet",
"F2-10": "audit-sheet",
"F2-11": "d-form-table",
"F2-12": "d-form-table",
"F2-13": "d-form-table",
"F2-14": "d-form-table",
# 存货 - 会计政策
"F2-16": "d-form-table",
# 存货 - 分析
"F2-18": "audit-sheet",
"F2-19": "audit-sheet",
"F2-20": "audit-sheet",
# 存货 - 盘点
"F2-21": "audit-sheet",
"F2-22": "audit-sheet",
"F2-23": "audit-sheet",
"F2-24": "audit-sheet",
"F2-25": "audit-sheet",
"F2-26": "audit-sheet",
# 存货 - 检查
"F2-29": "audit-sheet",
"F2-30": "audit-sheet",
"F2-31": "audit-sheet",
"F2-32": "audit-sheet",
"F2-33": "audit-sheet",
"F2-34": "audit-sheet",
"F2-35": "audit-sheet",
# 存货 - 计价
"F2-38": "audit-sheet",
"F2-39": "audit-sheet",
"F2-40": "audit-sheet",
"F2-41": "audit-sheet",
"F2-42": "audit-sheet",
"F2-43": "audit-sheet",
"F2-44": "audit-sheet",
# 存货 - 跌价
"F2-47": "audit-sheet",
"F2-48": "audit-sheet",
"F2-49": "audit-sheet",
# 存货 - 关联交易
"F2-52": "d-form-table",
# 存货 - 合同履约成本
"F2-55": "audit-sheet",
"F2-56": "audit-sheet",
"F2-57": "audit-sheet",
"F2-58": "audit-sheet",
# 存货 - IPO
"F2-61": "audit-sheet",
"F2-62": "audit-sheet",
"F2-63": "audit-sheet",
"F2-64": "audit-sheet",
"F2-65": "audit-sheet",
"F2-66": "audit-sheet",
"F2-67": "audit-sheet",
"F2-68": "audit-sheet",
"F2-69": "audit-sheet",
"F2-70": "audit-sheet",
"F2-71": "audit-sheet",
"F2-72": "audit-sheet",
# 应付票据
"F3": "d-form-table",
"F3-1": "d-form-table",
"F3-2": "audit-sheet",
"F3-3": "audit-sheet",
"F3-4": "d-form-table",
"F3-5": "audit-sheet",
"F3-6": "audit-sheet",
# 应付账款
"F4": "d-form-table",
"F4-1": "d-form-table",
"F4-2": "audit-sheet",
"F4-3": "audit-sheet",
"F4-4": "d-form-table",
"F4-5": "audit-sheet",
"F4-6": "audit-sheet",
# 营业成本
"F5": "d-form-table",
"F5-1": "d-form-table",
"F5-2": "audit-sheet",
"F5-3": "audit-sheet",
"F5-4": "audit-sheet",
"F5-5": "audit-sheet",
"F5-6": "audit-sheet",
```

### 2.3 procedure_table_templates.json 扩展

```json
{
  "F0A": {
    "name": "存货循环函证程序表",
    "items": [/* 从 F0 xlsx 提取 */]
  },
  "F1A": {
    "name": "预付账款实质性程序表",
    "items": [/* 从 F1 xlsx 提取 */]
  },
  "F2A": {
    "name": "存货实质性程序表",
    "items": [/* 从 F2-1至F2-14 xlsx 提取 — 注：F2A 物理上在此文件中 */]
  },
  "F3A": {
    "name": "应付票据实质性程序表",
    "items": [/* 从 F3 xlsx 提取 */]
  },
  "F4A": {
    "name": "应付账款实质性程序表",
    "items": [/* 从 F4 xlsx 提取 */]
  },
  "F5A": {
    "name": "营业成本实质性程序表",
    "items": [/* 从 F5 xlsx 提取 */]
  }
}
```

### 2.4 auto_data_source resolvers

| source 名 | 用途 | 状态 |
|-----------|------|------|
| `risk_for_cycle` | F 程序表读取 B50 风险评估 | ✅ 已有 |
| `control_test_result_for_cycle` | F 程序表读取 C4 控制测试结论 | ✅ 已有 |
| `audited_amount_writeback` | F 审定表保存→回写 trial_balance | ✅ 复用统一 handler |
| `confirmation_summary_for_cycle` | F0/F4A 读取函证摘要 | ✅ 复用（cycle="F"） |
| `related_party_transactions` | F2-52 读取关联方交易 | ✅ 已有（A7 共用） |
| `accounting_estimate_b51` | F2-47~49 读取 B51 舞弊三因素 | 🔴 需新增 |

新增 resolver 设计：

```python
@auto_resolver("accounting_estimate_b51")
async def _resolve_accounting_estimate_b51(db, project_id, year, **kw):
    """从 B51 读取舞弊三因素评估结论（管理层偏向/估计不确定性/复杂性）。
    
    用于跌价准备等会计估计底稿展示风险评估上下文。
    """
    # 查 field_overrides scope='b51_fraud_factors' 中的三因素
    return {
        "management_bias": "...",
        "estimation_uncertainty": "...",
        "complexity": "...",
        "overall_risk_level": "high/medium/low",
    }
```

## 3. 审定表 F{n}-1 标准字段

复用 D/E 类审定表通用字段结构：

```yaml
fields:
  - {field: account_code, label: 科目编码, type: text, readonly: true}
  - {field: account_name, label: 科目名称, type: text, readonly: true}
  - {field: opening_balance, label: 期初余额, type: number, auto_source: trial_balance.opening_balance}
  - {field: unadjusted_amount, label: 未审金额, type: number, auto_source: trial_balance.unadjusted_amount}
  - {field: aje_debit, label: 审计调整借方, type: number}
  - {field: aje_credit, label: 审计调整贷方, type: number}
  - {field: rje_debit, label: 重分类调整借方, type: number}
  - {field: rje_credit, label: 重分类调整贷方, type: number}
  - {field: audited_amount, label: 审定金额, type: number, formula: "unadjusted + aje_debit - aje_credit + rje_debit - rje_credit"}
  - {field: prior_year_audited, label: 上年审定金额, type: number, auto_source: trial_balance.prior_audited}
  - {field: variance_amount, label: 变动金额, type: number, formula: "audited - prior_year_audited"}
  - {field: variance_pct, label: 变动比例, type: percent, formula: "variance_amount / prior_year_audited"}
  - {field: variance_note, label: 差异说明, type: textarea}
```

F2-1 特殊行结构：存货分多类（原材料/在产品/库存商品/在途物资/委托加工等），每类独立行+合计行+跌价准备扣减行+净额行。

## 4. 联动实现方案

### 4.1 F 审定表→trial_balance 回写

复用统一 handler，正则扩展：`^[D-N]\d+-1$` 匹配 F1-1/F2-1/F3-1/F4-1/F5-1。

### 4.2 B50→F 风险展示（已就绪）

F{n}A 程序表通过 `auto_data_source: "risk_for_cycle"` + `cycle="F"` 读取 B50-3 认定层次风险。

### 4.3 C4→F 控制测试结论展示（已就绪）

F{n}A 程序表通过 `auto_data_source: "control_test_result_for_cycle"` + `cycle="F"` 读取 C4 结论。

### 4.4 F0 函证→ConfirmationHub 路由

与 D0/E0 模式一致：`_WP_CODE_OVERRIDE["F0"] = "confirmation-hub"` → 路由到 `/projects/:pid/confirmation?cycle=F`

### 4.5 B51→F2 跌价准备联动

F2-47~F2-49 跌价准备测试需展示 B51 舞弊三因素评估上下文：
- auto_data_source: `accounting_estimate_b51`
- 在跌价准备测试顶部展示会计估计风险等级面板
- 风险等级为"高"时在界面显示红色警示

### 4.6 F5→F2 成本结转联动

F5（营业成本）与 F2（存货）存在逻辑联动：
- F5-3 成本结转测试需读取 F2-1 存货审定金额
- 通过 ref_index chip 实现跳转（非自动取数）

## 5. address_registry 坐标注册

| wp_code | 关键坐标 | 用途 |
|---------|---------|------|
| F1-2/F1-3 | 合计行余额列 | 预付账款明细汇总 |
| F2-2~F2-10 | 各类存货合计行 | 存货分类汇总 |
| F2-18~F2-20 | 结论单元格 | 分析程序结论 |
| F2-21~F2-26 | 盘点日期/差异金额/结论 | 监盘结论 |
| F2-29~F2-35 | 各检查 sheet 结论 | 检查结论汇总 |
| F2-38~F2-44 | 计价差异/结论 | 计价测试结论 |
| F2-47~F2-49 | 跌价准备结论 | 跌价测试结论 |
| F2-55~F2-58 | 合同成本结论 | 合同履约成本结论 |
| F2-61~F2-72 | 各 IPO sheet 结论 | IPO 结论 |
| F3-2/F3-5/F3-6 | 合计行 | 应付票据汇总 |
| F4-2/F4-3 | 合计行 | 应付账款汇总 |
| F5-2/F5-3/F5-4 | 合计行/毛利率 | 营业成本汇总 |

坐标数据维护：`backend/data/f_address_registry_seed.json`

## 6. 前端路由

不需要新的顶层页面。复用现有底稿路由：

```
/projects/:pid/workpapers/:wpId → GtWpRenderer → componentType 路由
```

F0 走 `confirmation-hub` → ConfirmationHub（cycle=F）。

## 7. 正确性属性 (Correctness Properties)

### Property 1: F 类 wp_code 注册完整性

*For any* F 类模板文件中的 sheet（非导航/选项/示例），其 wp_code 必须存在于 `wp_account_mapping.json` 中。

### Property 2: _WP_CODE_OVERRIDE 覆盖率

*For any* 在 `wp_account_mapping.json` 中注册的 F 类 wp_code，必须在 `_WP_CODE_OVERRIDE` 中存在对应映射。

### Property 3: 审定表回写 round-trip

*For any* F{n}-1 审定表保存的审定金额，trial_balance 查询结果应等于保存值。

### Property 4: 程序表模板完整性

*For any* F{n}A 程序表，procedure_table_templates.json 中步骤数应 ≥ xlsx 模板程序步骤行数。

### Property 5: address_registry 坐标有效性

*For any* f_address_registry_seed.json 中的坐标，sheet_name 必须存在于对应模板文件中。

### Property 6: componentType 与 sheet 类型一致性

程序表类必须映射 `a-program-console`，审定表类必须映射 `d-form-table`。

### Property 7: IPO 适用性控制

普通年审项目 F2-61~F2-72 的 applicable_when 评估结果为 False。

### Property 8: 跌价准备联动（会计估计）

*For any* F2-47~F2-49 底稿打开时，accounting_estimate_b51 resolver 必须返回非空的风险等级。

## 8. 错误处理

| 场景 | 处理方式 |
|------|---------|
| audited_amount 回写失败 | handler 记录 WARNING，不阻断保存 |
| trial_balance 无对应科目 | auto_source 字段显示空值，允许手动填写 |
| ConfirmationHub 无 F 循环数据 | F0 显示"尚未发起函证"提示 |
| address_registry 坐标未注册 | custom_query 返回空值 |
| F2-61~72 适用性判定失败 | 默认显示，手动判断 |
| B51 数据不存在 | 跌价准备底稿显示"尚未完成 B51 评估"提示 |
| F5→F2 审定金额未填写 | 成本结转测试提示"请先完成 F2-1 审定" |

## 9. 测试策略

### 9.1 单元测试

- wp_account_mapping F 类条目完整性校验（~80 条）
- _WP_CODE_OVERRIDE F 类覆盖率校验
- 审定表标准字段 schema 校验
- 程序表模板 JSON 结构校验
- IPO 适用性条件评估
- accounting_estimate_b51 resolver 返回结构校验

### 9.2 集成测试

- 审定表保存→trial_balance.audited_amount 回写验证（F1-1/F2-1/F3-1/F4-1/F5-1 全部）
- confirmation_summary_for_cycle cycle="F" 读取验证
- accounting_estimate_b51 读取验证

### 9.3 E2E（Playwright）

- F2A 程序表打开 + 风险/控制联动面板展示
- F2-1 审定表编辑 + 保存 + trial_balance 回写确认
- F2-21 存货监盘 OnlyOffice 打开 + 多 sheet Tab
- F2-47 跌价准备测试 + B51 联动面板
- F2-61 IPO 底稿适用性灰显
- F0 函证底稿→ConfirmationHub 路由跳转
