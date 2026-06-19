# E 类底稿（货币资金循环）— 设计文档

## 1. 架构总览

E 类底稿复用已验证的渲染管线（与 B/C/D 类一致）：

```
wp_account_mapping.json (扩充 E 类 ~35 条)
  → WpClassificationService (_WP_CODE_OVERRIDE)
    → get_render_config (componentType 分发)
      → 前端 htmlRendererRegistry → 对应 Vue 组件
```

### 1.1 设计决策：E 类为单科目循环

货币资金仅 1 个主科目（E1），但内部 sheet 按功能细分为：常规(E1-1~11) + 分析(E1-14~15) + 检查(E1-18~23) + IPO(E1-26~32)。编号不连续的原因是致同 2025 模板的历史编号规则。

**不使用 generic schema**：E 类各子底稿结构差异大（审定表 vs 余额调节表 vs 利息测算 vs IPO 检查），不适合统一 schema。

### 1.2 componentType 路由规划

| wp_code 模式 | componentType | 前端组件 | 说明 |
|-------------|--------------|---------|------|
| E0A/E1A | `a-program-console` | GtAProgramConsole | 程序表 |
| E0 | `confirmation-hub` | ConfirmationHub | 函证路由 |
| E0-1~E0-5 | `d-form-table` | GtDFormTable | 函证辅助表 |
| E1-1 | `d-form-table` | GtDFormTable | 审定表 |
| E1 附注披露 sheet | `c-note-table` | DisclosureEditor | disclosure_notes |
| E1-2/E1-6/E1-10 | `d-form-table` | GtDFormTable | 简单结构明细 |
| E1-3/E1-4/E1-5/E1-7/E1-8/E1-9/E1-11 | `audit-sheet` | GtAuditSheet(OnlyOffice) | 含公式/大数据量 |
| E1-14/E1-15 | `audit-sheet` | GtAuditSheet | 分析程序 |
| E1-18~E1-23 | `audit-sheet` | GtAuditSheet | 检查程序 |
| E1-26~E1-32 | `audit-sheet` | GtAuditSheet | IPO/舞弊应对 |

## 2. 数据模型

### 2.1 wp_account_mapping 扩充（从 5 → ~35 条）

现有 5 条：E0/E1/E1-1/E1-2/E1-3

需新增：

| wp_code | wp_name | must_have | 新增/已有 |
|---------|---------|-----------|----------|
| E0 | 银行询证函 | true | 已有 |
| E0-1 | 函证结果汇总 | false | 新增 |
| E0-2 | 核实被函证银行 | false | 新增 |
| E0-3 | 跟函控制 | false | 新增 |
| E0-4 | 差异调节 | false | 新增 |
| E0-5 | 替代程序 | false | 新增 |
| E1 | 货币资金 | true | 已有 |
| E1-1 | 货币资金审定表 | true | 已有 |
| E1-2 | 库存现金明细表 | false | 已有 |
| E1-3 | 银行存款明细表 | false | 已有 |
| E1-4 | 其他货币资金明细表 | false | 新增 |
| E1-5 | 银行存款余额调节表 | false | 新增 |
| E1-6 | 受限货币资金明细 | false | 新增 |
| E1-7 | 大额现金收支检查 | false | 新增 |
| E1-8 | 银行存款检查 | false | 新增 |
| E1-9 | 利息测算 | false | 新增 |
| E1-10 | 调整分录汇总 | false | 新增 |
| E1-11 | 未达账项明细 | false | 新增 |
| E1-14 | 货币资金分析程序（一） | false | 新增 |
| E1-15 | 货币资金分析程序（二） | false | 新增 |
| E1-18 | 货币资金检查（一） | false | 新增 |
| E1-19 | 货币资金检查（二） | false | 新增 |
| E1-20 | 货币资金检查（三） | false | 新增 |
| E1-21 | 货币资金检查（四） | false | 新增 |
| E1-22 | 货币资金检查（五） | false | 新增 |
| E1-23 | 货币资金检查（六） | false | 新增 |
| E1-26 | IPO舞弊应对（一） | false | 新增 |
| E1-27 | IPO舞弊应对（二） | false | 新增 |
| E1-28 | IPO舞弊应对（三） | false | 新增 |
| E1-29 | IPO舞弊应对（四） | false | 新增 |
| E1-30 | IPO舞弊应对（五） | false | 新增 |
| E1-31 | IPO舞弊应对（六） | false | 新增 |
| E1-32 | IPO舞弊应对（七） | false | 新增 |

### 2.2 _WP_CODE_OVERRIDE 完整映射表

```python
# E 类 — 货币资金循环实质性程序
# 函证
"E0": "confirmation-hub",
"E0-1": "d-form-table",
"E0-2": "d-form-table",
"E0-3": "d-form-table",
"E0-4": "d-form-table",
"E0-5": "d-form-table",
# 货币资金 - 常规
"E1": "d-form-table",
"E1-1": "d-form-table",
"E1-2": "d-form-table",
"E1-3": "audit-sheet",
"E1-4": "audit-sheet",
"E1-5": "audit-sheet",
"E1-6": "d-form-table",
"E1-7": "audit-sheet",
"E1-8": "audit-sheet",
"E1-9": "audit-sheet",
"E1-10": "d-form-table",
"E1-11": "audit-sheet",
# 货币资金 - 分析
"E1-14": "audit-sheet",
"E1-15": "audit-sheet",
# 货币资金 - 检查
"E1-18": "audit-sheet",
"E1-19": "audit-sheet",
"E1-20": "audit-sheet",
"E1-21": "audit-sheet",
"E1-22": "audit-sheet",
"E1-23": "audit-sheet",
# 货币资金 - IPO
"E1-26": "audit-sheet",
"E1-27": "audit-sheet",
"E1-28": "audit-sheet",
"E1-29": "audit-sheet",
"E1-30": "audit-sheet",
"E1-31": "audit-sheet",
"E1-32": "audit-sheet",
```

### 2.3 procedure_table_templates.json 扩展

```json
{
  "E0A": {
    "name": "货币资金函证程序表",
    "items": [/* 从 E0 xlsx Sheet "函证程序表E0A" 提取 */]
  },
  "E1A": {
    "name": "货币资金实质性程序表",
    "items": [/* 从 E1-1至E1-11 xlsx Sheet "程序表E1A" 提取 */]
  }
}
```

### 2.4 auto_data_source resolvers

| source 名 | 用途 | 状态 |
|-----------|------|------|
| `risk_for_cycle` | E 程序表读取 B50 风险评估 | ✅ 已有 |
| `control_test_result_for_cycle` | E 程序表读取 C3 控制测试结论 | ✅ 已有 |
| `audited_amount_writeback` | E 审定表保存→回写 trial_balance | ✅ 复用 D 类 handler |
| `confirmation_summary_for_cycle` | E0/E1A 读取函证摘要 | ✅ 复用 D 类（cycle="E"） |

## 3. 审定表 E1-1 标准字段

复用 D 类审定表通用字段结构：

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

E1-1 特殊行结构：分 3 组（库存现金 1001 / 银行存款 1002 / 其他货币资金 1012），每组独立审定+合计行。

## 4. 联动实现方案

### 4.1 E 审定表→trial_balance 回写

复用 D 类 `_on_audit_determination_saved` handler，正则扩展匹配 `^E\d+-1$`：

```python
# 扩展后统一 handler 匹配模式
if not re.match(r"^[D-N]\d+-1$", wp_code):
    return
```

### 4.2 B50→E 风险展示（已就绪）

E1A 程序表通过 `auto_data_source: "risk_for_cycle"` + `cycle="E"` 自动读取 B50-3 中与 E 循环相关的认定层次风险。

### 4.3 C3→E 控制测试结论展示（已就绪）

E1A 程序表通过 `auto_data_source: "control_test_result_for_cycle"` + `cycle="E"` 读取 C3 控制测试结论。

### 4.4 E0 函证→ConfirmationHub 路由

与 D0 模式完全一致：
- `_WP_CODE_OVERRIDE["E0"] = "confirmation-hub"`
- 前端 render-config 识别 `confirmation-hub` → 路由到 `/projects/:pid/confirmation?cycle=E`
- E0-1~E0-5 辅助底稿以 `d-form-table` 独立渲染

## 5. address_registry 坐标注册

| wp_code | 关键坐标 | 用途 |
|---------|---------|------|
| E1-3 | 合计行余额列 | 银行存款汇总 |
| E1-4 | 合计行余额列 | 其他货币资金汇总 |
| E1-5 | 调节后余额单元格 | 余额调节结果 |
| E1-9 | 测算利息合计/差异 | 利息测算结论 |
| E1-14/E1-15 | 结论单元格 | 分析程序结论 |
| E1-18~E1-23 | 各检查 sheet 结论 | 检查结论汇总 |
| E1-26~E1-32 | 各 IPO sheet 结论 | IPO 结论 |

坐标数据维护：`backend/data/e_address_registry_seed.json`

## 6. 前端路由

不需要新的顶层页面。复用现有底稿路由：

```
/projects/:pid/workpapers/:wpId → GtWpRenderer → componentType 路由
```

E0 走 `confirmation-hub` → 路由到 ConfirmationHub 页面（cycle=E）。

## 7. 正确性属性 (Correctness Properties)

### Property 1: E 类 wp_code 注册完整性

*For any* E 类模板文件中的 sheet，如果该 sheet 有独立 wp_code（非导航/选项/示例 sheet），则该 wp_code 必须存在于 `wp_account_mapping.json` 中。

### Property 2: _WP_CODE_OVERRIDE 覆盖率

*For any* 在 `wp_account_mapping.json` 中注册的 E 类 wp_code，必须在 `_WP_CODE_OVERRIDE` 中存在对应的 componentType 映射条目。

### Property 3: 审定表回写 round-trip

*For any* E1-1 审定表保存的审定金额，通过 `trial_balance` 查询该项目/年度/科目的 `audited_amount` 应等于保存值。

### Property 4: 程序表模板完整性

*For any* E{n}A 程序表，其在 `procedure_table_templates.json` 中注册的步骤数应 ≥ xlsx 模板中程序步骤的行数。

### Property 5: address_registry 坐标有效性

*For any* 在 `e_address_registry_seed.json` 中注册的坐标，其 sheet_name 必须存在于对应 xlsx 模板文件中，且 cell_address 格式合法。

### Property 6: componentType 与 sheet 类型一致性

*For any* E 类 wp_code 的 componentType 映射，程序表类必须映射为 `a-program-console`，审定表类必须映射为 `d-form-table`。

### Property 7: IPO 适用性控制

*For any* business_category 为 'annual_audit'（普通年审）的项目，E1-26~E1-32 的 applicable_when 评估结果应为 False。

## 8. 错误处理

| 场景 | 处理方式 |
|------|---------|
| audited_amount 回写失败 | handler 记录 WARNING，不阻断保存 |
| trial_balance 无对应科目 | 审定表 auto_source 字段显示空值，允许手动填写 |
| ConfirmationHub 无 E 循环数据 | E0 显示"尚未发起函证"提示 |
| address_registry 坐标未注册 | custom_query 返回空值 |
| E1-26~32 适用性判定失败 | 默认显示（不隐藏），手动判断 |

## 9. 测试策略

### 9.1 单元测试

- wp_account_mapping E 类条目完整性校验
- _WP_CODE_OVERRIDE E 类覆盖率校验
- 审定表标准字段 schema 校验
- 程序表模板 JSON 结构校验
- IPO 适用性条件评估

### 9.2 集成测试

- 审定表保存→trial_balance.audited_amount 回写验证
- confirmation_summary_for_cycle cycle="E" 读取验证

### 9.3 E2E（Playwright）

- E1A 程序表打开 + 风险/控制联动面板展示
- E1-1 审定表编辑 + 保存 + trial_balance 回写确认
- E1-5 银行存款余额调节表 OnlyOffice 打开
- E1-26 IPO 底稿适用性灰显
- E0 函证底稿→ConfirmationHub 路由跳转
