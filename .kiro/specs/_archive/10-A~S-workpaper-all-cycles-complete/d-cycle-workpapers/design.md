# D 类底稿（销售收入循环）— 设计文档

## 1. 架构总览

D 类底稿复用已验证的渲染管线（与 B/C 类一致）：

```
wp_account_mapping.json (扩充 D 类 ~55 条)
  → WpClassificationService (_WP_CODE_OVERRIDE)
    → get_render_config (componentType 分发)
      → 前端 htmlRendererRegistry → 对应 Vue 组件
```

### 1.1 设计决策：不使用通用 generic schema

与 C 类不同，D 类各科目（D1~D7）的内部 sheet 结构差异显著：
- D6 有 9 个子底稿（审定+明细+减值+检查+测算+政策+关联方+转回）
- D3 仅有基本结构（程序表+审定表+明细+附注）
- D4 因营业收入重要性有 36 个子底稿

因此**不设计 D-generic.yaml**，而是：
1. 利用已有的 generated YAML schema（19 个）作为基础
2. 人工审核修正 componentType 分配
3. 对程序表（D{n}A）统一使用 `a-program-console` + procedure_table_templates
4. 对审定表（D{n}-1）统一使用 `d-form-table` + 标准审定表字段
5. 对含公式的明细/分析走 `audit-sheet`

### 1.2 componentType 路由规划

| wp_code 模式 | componentType | 前端组件 | 说明 |
|-------------|--------------|---------|------|
| D0A/D1A/D2A/D3A/D4A/D5A/D6A/D7A | `a-program-console` | GtAProgramConsole | 实质性程序表 |
| D{n}-1（各科目审定表） | `d-form-table` | GtDFormTable | 结构化审定金额 |
| D{n} 附注披露 sheet | `c-note-table` | DisclosureEditor | disclosure_notes 模块 |
| D1-2/D1-3/D2-2/D4-2~4/D5-2/D6-2/D6-3/D6-8 | `audit-sheet` | GtAuditSheet(OnlyOffice) | 含复杂公式/大数据量明细/测算 |
| D2-5/D4-6~11 分析程序 | `audit-sheet` | GtAuditSheet | 分析计算+图表 |
| D2-6~13/D4-13~20/D4-22~32 检查程序 | `audit-sheet` | GtAuditSheet | 大量 sheet 检查 |
| D1-4/D2-3/D2-4/D3-2/D4-5/D4-12/D4-21/D6-6/D6-9/D7-2 | `d-form-table` | GtDFormTable | 坏账准备/简单明细/检查/政策（HTML优先） |
| D6-7 | `d-form-paragraph` | GtDFormParagraph | 段落式政策描述 |
| D0 核心函证 | `confirmation-hub` | ConfirmationHub | 已有模块 |
| D0-1~D0-5 辅助 | `d-form-table` | GtDFormTable | 函证辅助表 |

## 2. 数据模型

### 2.1 wp_account_mapping 扩充（从 13 → ~55 条）

现有 13 条：D0/D1/D2/D2-2/D2-3/D2-4/D3/D4/D5/D5-1/D6/D6-1/D7/D7-1

需新增（按科目组列出）：

| wp_code | wp_name | must_have | 新增/已有 |
|---------|---------|-----------|----------|
| D0 | 收入循环函证 | true | 已有 |
| D0-1 | 函证结果汇总 | false | 新增 |
| D0-2 | 核实被函证单位 | false | 新增 |
| D0-3 | 跟函控制 | false | 新增 |
| D0-4 | 差异调节 | false | 新增 |
| D0-5 | 替代程序 | false | 新增 |
| D1 | 应收票据审定表 | true | 已有 |
| D1-1 | 应收票据审定表 | true | 新增 |
| D1-2 | 应收票据原值明细（按类） | false | 新增 |
| D1-3 | 应收票据原值明细（按客户） | false | 新增 |
| D1-4 | 应收票据坏账准备 | false | 新增 |
| D2 | 应收账款审定表 | true | 已有 |
| D2-1 | 应收账款审定表 | true | 新增 |
| D2-2 | 应收账款明细表 | false | 已有 |
| D2-3 | 应收账款坏账准备明细表 | false | 已有 |
| D2-4 | 应收账款调整分录汇总表 | false | 已有 |
| D2-5 | 应收账款分析程序 | false | 新增 |
| D2-6 | 应收账款检查 | false | 新增 |
| D3 | 预收账款审定表 | true | 已有 |
| D3-1 | 预收账款审定表 | true | 新增 |
| D3-2 | 预收账款明细表 | false | 新增 |
| D4 | 营业收入审定表 | true | 已有 |
| D4-1 | 营业收入审定表 | true | 新增 |
| D4-2 | 收入明细（按类别） | false | 新增 |
| D4-3 | 收入明细（按客户） | false | 新增 |
| D4-4 | 收入明细（按月份） | false | 新增 |
| D4-5 | 营业收入会计政策 | false | 新增 |
| D4-6 | 营业收入分析程序 | false | 新增 |
| D4-12 | 营业收入合同检查 | false | 新增 |
| D4-13 | 主营业务收入检查 | false | 新增 |
| D4-21 | 营业收入关联方检查 | false | 新增 |
| D4-22 | 营业收入IPO舞弊应对 | false | 新增 |
| D4-33 | 其他业务收入 | false | 新增 |
| D5 | 合同资产审定表 | true | 已有（名称改"应收款项融资"） |
| D5-1 | 应收款项融资审定表 | true | 已有 |
| D5-2 | 应收款项融资明细 | false | 新增 |
| D6 | 合同负债审定表 | true | 已有（名称改"合同资产"） |
| D6-1 | 合同资产明细表 | false | 已有 |
| D6-2 | 合同资产明细表（详细） | false | 新增 |
| D6-3 | 合同资产减值准备明细 | false | 新增 |
| D6-4 | 合同资产调整分录汇总 | false | 新增 |
| D6-5 | 合同资产关联方检查 | false | 新增 |
| D6-6 | 合同资产检查表 | false | 新增 |
| D6-7 | 合同资产减值准备政策检查 | false | 新增 |
| D6-8 | 合同资产减值测算 | false | 新增 |
| D6-9 | 合同资产减值转回核销检查 | false | 新增 |
| D7 | 应收款项融资审定表 | true | 已有（名称改"合同负债"） |
| D7-1 | 合同负债明细表 | false | 已有 |
| D7-2 | 合同负债明细（详细） | false | 新增 |

**注意**：wp_account_mapping 中 D5/D6/D7 的 wp_name 存在错配（D5 名称为"合同资产审定表"但实际应为"应收款项融资"，D6 为"合同负债审定表"但实际应为"合同资产"，D7 为"应收款项融资审定表"但应为"合同负债"），P0 阶段需修正。

### 2.2 _WP_CODE_OVERRIDE 完整映射表

在 `wp_classification_service.py` 的 `_WP_CODE_OVERRIDE` 中添加：

```python
# D 类 — 销售收入循环实质性程序
# 函证
"D0": "confirmation-hub",
"D0-1": "d-form-table",
"D0-2": "d-form-table",
"D0-3": "d-form-table",
"D0-4": "d-form-table",
"D0-5": "d-form-table",
# 应收票据
"D1": "d-form-table",
"D1-1": "d-form-table",
"D1-2": "audit-sheet",
"D1-3": "audit-sheet",
"D1-4": "d-form-table",
# 应收账款
"D2": "d-form-table",
"D2-1": "d-form-table",
"D2-2": "audit-sheet",
"D2-3": "audit-sheet",
"D2-4": "d-form-table",
"D2-5": "audit-sheet",
"D2-6": "audit-sheet",
# 预收账款
"D3": "d-form-table",
"D3-1": "d-form-table",
"D3-2": "audit-sheet",
# 营业收入
"D4": "d-form-table",
"D4-1": "d-form-table",
"D4-2": "audit-sheet",
"D4-3": "audit-sheet",
"D4-4": "audit-sheet",
"D4-5": "d-form-table",
"D4-6": "audit-sheet",
"D4-12": "d-form-table",
"D4-13": "audit-sheet",
"D4-21": "d-form-table",
"D4-22": "audit-sheet",
"D4-33": "d-form-table",
# 应收款项融资
"D5": "d-form-table",
"D5-1": "d-form-table",
"D5-2": "audit-sheet",
# 合同资产
"D6": "d-form-table",
"D6-1": "d-form-table",
"D6-2": "audit-sheet",
"D6-3": "audit-sheet",
"D6-4": "d-form-table",
"D6-5": "d-form-table",
"D6-6": "d-form-table",
"D6-7": "d-form-paragraph",
"D6-8": "audit-sheet",
"D6-9": "d-form-table",
# 合同负债
"D7": "d-form-table",
"D7-1": "d-form-table",
"D7-2": "audit-sheet",
```

**程序表不在 _WP_CODE_OVERRIDE 中**：D{n}A 程序表 wp_code 以字母 A 结尾（如 D1A/D2A...），通过 generated schema 的 `component_type: a-program-console` 已正确标记。但需确认 render-config 路径能正确解析 D{n}A 格式。

### 2.3 procedure_table_templates.json 扩展

需从 xlsx 模板提取 D0A~D7A 共 8 个程序表的步骤结构：

```json
{
  "D0A": {
    "name": "收入循环函证程序表",
    "items": [/* 从 D0 xlsx Sheet "函证程序表D0A" 提取 */]
  },
  "D1A": {
    "name": "应收票据实质性程序表",
    "items": [/* 从 D1 xlsx Sheet "程序表D1A" 提取 */]
  },
  "D2A": {
    "name": "应收账款实质性程序表",
    "items": [/* 从 D2-1至D2-4 xlsx Sheet "程序表D2A" 提取 */]
  },
  "D3A": {
    "name": "预收账款实质性程序表",
    "items": [/* 从 D3 xlsx 提取 */]
  },
  "D4A": {
    "name": "营业收入实质性程序表",
    "items": [/* 从 D4-1至D4-4 xlsx Sheet "程序表D4A" 提取 */]
  },
  "D5A": {
    "name": "应收款项融资实质性程序表",
    "items": [/* 从 D5 xlsx 提取 */]
  },
  "D6A": {
    "name": "合同资产实质性程序表",
    "items": [/* 从 D6 xlsx Sheet "合同资产实质性程序表 D6A" 提取 */]
  },
  "D7A": {
    "name": "合同负债实质性程序表",
    "items": [/* 从 D6 xlsx Sheet "合同资产实质性程序表 D7A（原）" 提取 — 注：D7A 程序表物理上在 D6.xlsx 中 */]
  }
}
```


### 2.4 auto_data_source resolvers

| source 名 | 用途 | 状态 |
|-----------|------|------|
| `risk_for_cycle` | D 程序表读取 B50 风险评估 | ✅ 已有 |
| `control_test_result_for_cycle` | D 程序表读取 C2 控制测试结论 | ✅ 已有 |
| `audited_amount_writeback` | D 审定表保存→回写 trial_balance | 🔴 需新增 |
| `related_party_transactions` | D4-21 读取关联方交易 | ✅ 已有（A7 共用） |
| `confirmation_summary_for_cycle` | D0/D2A 读取函证摘要 | 🔴 需新增（从 ConfirmationHub 取） |

新增 resolver 设计：

```python
@auto_resolver("audited_amount_writeback")
async def _resolve_audited_amount_writeback(db, project_id, year, **kw):
    """D 类审定表保存时触发 — 回写 audited_amount 到 trial_balance。
    
    注意：这不是读取型 resolver，而是写入型 handler。
    实际通过 EventBus WORKPAPER_SAVED + handler 实现。
    此 resolver 仅返回当前审定状态摘要。
    """
    # 查 trial_balance 中该循环科目的 audited_amount 填写状态
    ...

@auto_resolver("confirmation_summary_for_cycle")
async def _resolve_confirmation_summary(db, project_id, year, **kw):
    """从 ConfirmationHub 读取该循环的函证摘要。"""
    cycle = kw.get("cycle", "D")
    # 查 confirmation 表中 cycle=D 的汇总
    return {
        "summary": f"D循环函证: 已发{sent}函/回函{received}封/差异{diff}笔",
        "sent_count": sent,
        "received_count": received,
        "response_rate": f"{rate:.0%}",
        "diff_count": diff,
    }
```

## 3. 审定表 D{n}-1 标准字段

所有 D 类审定表共享统一字段结构（参照 generated D6.yaml 中 `审定表D6-1` 的 component_type: univer 改为 d-form-table 后的字段）：

```yaml
# D 类审定表通用字段（各科目 D{n}-1 共享）
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

## 4. 联动实现方案

### 4.1 D 审定表→trial_balance 回写（EventBus handler）

```python
async def _on_d_audit_determination_saved(payload: EventPayload) -> None:
    """D 类审定表保存 → 回写 audited_amount 到 trial_balance。

    触发条件：
    - event_type == WORKPAPER_SAVED
    - payload.extra['wp_code'] 匹配 D{n}-1 模式（审定表）

    写入目标：
    - trial_balance.audited_amount（按 project_id + year + standard_account_code）
    """
    wp_code = payload.extra.get("wp_code", "")
    # 识别审定表：D1-1, D2-1, D3-1, D4-1, D5-1, D6-1, D7-1
    if not re.match(r"^D\d-1$", wp_code):
        return

    parsed_data = payload.extra.get("parsed_data", {})
    # 提取各行审定金额，按 account_code 回写
    for row in parsed_data.get("rows", []):
        account_code = row.get("account_code")
        audited = row.get("audited_amount")
        if account_code and audited is not None:
            await tb_service.update_audited_amount(
                project_id, year, account_code, Decimal(str(audited))
            )
```

### 4.2 B50→D 风险展示（已就绪）

D{n}A 程序表通过 `auto_data_source: "risk_for_cycle"` + `cycle="D"` 自动读取 B50-3 中与 D 循环相关的认定层次风险。前端 GtAProgramConsole 已支持 auto_data_source 展示面板。

### 4.3 C2→D 控制测试结论展示（已就绪）

D{n}A 程序表通过 `auto_data_source: "control_test_result_for_cycle"` + `cycle="D"` 读取 C2 控制测试结论。已由 C 类 spec `_on_c_control_test_saved` handler 写入。

### 4.4 D0 函证→ConfirmationHub 路由

D0 底稿不独立渲染，而是路由到 ConfirmationHub 模块：
- `_WP_CODE_OVERRIDE["D0"] = "confirmation-hub"` 
- 前端 render-config 识别 `confirmation-hub` → 路由到 `/projects/:pid/confirmation?cycle=D`
- D0-1~D0-5 辅助底稿仍以 `d-form-table` 独立渲染

## 5. address_registry 坐标注册

所有 `audit-sheet` componentType 的 D 类底稿必须注册地址坐标：

| wp_code | 关键坐标 | 用途 |
|---------|---------|------|
| D1-2/D1-3 | 合计行余额列 | 与审定表交叉验证 |
| D2-2/D2-3 | 合计行、账龄分布列 | 明细汇总+账龄分析 |
| D2-5 | 结论单元格 | 分析程序结论 |
| D2-6 | 各检查 sheet 结论 | 检查结论汇总 |
| D4-2~D4-4 | 合计行 | 收入明细汇总 |
| D4-6 | 各分析 sheet 结论 | 分析结论 |
| D4-13 | 各检查 sheet 结论 | 检查结论 |
| D4-22 | IPO 各 sheet 结论 | IPO 结论 |
| D5-2 | 合计行 | 明细汇总 |
| D6-2/D6-3 | 合计行 | 明细汇总 |
| D6-8 | 测算结果 | 减值金额 |

坐标数据以 JSON seed 文件形式维护：`backend/data/d_address_registry_seed.json`

## 6. 前端路由

不需要新的顶层页面。复用现有底稿路由：

```
/projects/:pid/workpapers/:wpId → GtWpRenderer → componentType 路由
```

D0 走 `confirmation-hub` → 路由到 ConfirmationHub 页面。
audit-sheet 走 OnlyOffice（与 B30-2A/C22 相同）。
其余走 `d-form-table` 或 `a-program-console`。

## 7. 正确性属性 (Correctness Properties)

### Property 1: D 类 wp_code 注册完整性

*For any* D 类模板文件中的 sheet，如果该 sheet 有独立 wp_code（非导航/选项/示例 sheet），则该 wp_code 必须存在于 `wp_account_mapping.json` 中。

**Validates: Requirements P0 完整注册**

### Property 2: _WP_CODE_OVERRIDE 覆盖率

*For any* 在 `wp_account_mapping.json` 中注册的 D 类 wp_code，必须在 `_WP_CODE_OVERRIDE` 中存在对应的 componentType 映射条目。

**Validates: Requirements P0 componentType 映射**

### Property 3: 审定表回写 round-trip

*For any* D{n}-1 审定表保存的审定金额，通过 `trial_balance` 查询该项目/年度/科目的 `audited_amount` 应等于保存值。

**Validates: Requirements G1-2.3, G2-2.4, G3-1.4, G4-2.3, G5-1.4, G6-1.6, G7-1.4**

### Property 4: 程序表模板完整性

*For any* D{n}A 程序表，其在 `procedure_table_templates.json` 中注册的步骤数应 ≥ xlsx 模板中程序步骤的行数（允许 ≥ 因为可能包含分组头）。

**Validates: Requirements G0-2.2, G1-1.2, G2-1.2, G4-1.2**

### Property 5: address_registry 坐标有效性

*For any* 在 `d_address_registry_seed.json` 中注册的 D 类坐标，其 sheet_name 必须存在于对应 xlsx 模板文件中，且 cell_address 格式合法（A1 引用格式）。

**Validates: Requirements G1-4.3, G2-3.2, G4-4.2, G6-1.5**

### Property 6: componentType 与 sheet 类型一致性

*For any* D 类 wp_code 的 componentType 映射，程序表类（含"程序表"/"D{n}A"字样）必须映射为 `a-program-console`，审定表类（含"审定表"/"D{n}-1"模式）必须映射为 `d-form-table`。

**Validates: Requirements 各组 componentType 分配**

### Property 7: D4 适用性控制

*For any* business_category 为 'annual_audit'（普通年审）的项目，D4-22~D4-32 的 applicable_when 评估结果应为 False。*For any* business_category 为 'ipo'/'listed'/'neeq' 的项目，评估结果应为 True。

**Validates: Requirements G4-7.2, G4-7.3**

## 8. 错误处理

| 场景 | 处理方式 |
|------|---------|
| generated YAML schema 不存在 | 走 render-config 自动生成兜底 |
| audited_amount 回写失败 | handler 记录 WARNING，不阻断保存 |
| trial_balance 无对应科目 | 审定表 auto_source 字段显示空值，允许手动填写 |
| ConfirmationHub 无 D 循环数据 | D0 显示"尚未发起函证"提示 |
| address_registry 坐标未注册 | custom_query 返回空值 |
| D4-22~32 适用性判定失败 | 默认显示（不隐藏），手动判断 |

## 9. 测试策略

### 9.1 单元测试

- wp_account_mapping D 类条目完整性校验（覆盖全部 ~55 个 wp_code）
- _WP_CODE_OVERRIDE D 类覆盖率校验
- 审定表标准字段 schema 校验
- 程序表模板 JSON 结构校验（seq 连续、ref_index 合法）
- D4 适用性条件评估

### 9.2 属性测试（Hypothesis, max_examples=5）

- **Property 1**: wp_code 注册完整性
- **Property 2**: _WP_CODE_OVERRIDE 覆盖率
- **Property 3**: 审定表回写 round-trip
- **Property 6**: componentType 与 sheet 类型一致性

### 9.3 集成测试

- 审定表保存→trial_balance.audited_amount 回写验证
- auto_data_resolvers 新增 resolver 覆盖
- confirmation_summary_for_cycle 读取验证

### 9.4 E2E（Playwright）

- D2A 程序表打开 + 风险/控制联动面板展示
- D2-1 审定表编辑 + 保存 + trial_balance 回写确认
- D6 合同资产多 sheet Tab 切换
- D4-22 IPO 底稿适用性灰显
- D0 函证底稿→ConfirmationHub 路由跳转

### 9.5 属性测试库

Python: `hypothesis`（已配置，max_examples=5）

```python
# Feature: d-cycle-workpapers, Property 3: 审定表回写 round-trip
@given(amount=st.decimals(min_value=0, max_value=10**12, places=2))
def test_audit_determination_writeback_roundtrip(amount):
    ...
```
