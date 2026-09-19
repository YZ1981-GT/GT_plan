# C 类底稿（控制测试）— 设计文档

## 1. 架构总览

C 类底稿复用 B 类已验证的渲染管线（设计决策：不新增 componentType）：

```
wp_account_mapping.json (注册 36 条)
  → WpClassificationService (_WP_CODE_OVERRIDE)
    → get_render_config (componentType 分发)
      → 前端 htmlRendererRegistry → 对应 Vue 组件
```

### 1.1 componentType 路由规划

| wp_code 模式 | componentType | 前端组件 | 说明 |
|-------------|--------------|---------|------|
| C1 | `a-program-console` | GtAProgramConsole | 企业层面控制测试程序表（136步） |
| C2~C15 | `d-form-table` | GtDFormTable(多sheet) | 循环控制测试（C-generic.yaml） |
| C2-2~C15-2 | `d-form-table` | GtDFormTable | 偏差评价（C-deviation-generic.yaml） |
| C21 | `d-form-table` | GtDFormTable | IT专业人员资质 |
| C21-1 | `d-form-table` | GtDFormTable | IT审计发现汇总 |
| C22 | `audit-sheet` | GtAuditSheet(OnlyOffice) | IT一般控制（34 sheet） |
| C23 | `d-form-table` | GtDFormTable(3 sheet) | 会计分录控制测试 |
| C24 | `d-form-table` | GtDFormTable(2 sheet) | 会计分录细节测试 |
| C25 | `d-form-table` | GtDFormTable | 利用内审工作 |
| C26 | `d-form-table` | GtDFormTable | 信息处理控制测试 |

### 1.2 设计决策：复用现有渲染管线

与 B 类一致，C 类所有 d-form-table 通过 YAML schema 配置驱动，不新增 componentType。
C22（34 sheet IT 一般控制）因结构复杂走 OnlyOffice audit-sheet，配合 address_registry 坐标注册实现平台联动。

## 2. 数据模型

### 2.1 wp_account_mapping 新增条目（36 条）

在 `wp_account_mapping.json` 中一次性注册全部 C 类 wp_code：

| wp_code | wp_name | audit_cycle | must_have |
|---------|---------|-------------|-----------|
| C1 | 企业层面控制测试 | C | true |
| C2 | 销售循环控制测试 | C | true |
| C3 | 货币资金循环控制测试 | C | true |
| C4 | 存货循环控制测试 | C | true |
| C5 | 投资循环控制测试 | C | true |
| C6 | 固定资产循环控制测试 | C | true |
| C7 | 在建工程循环控制测试 | C | false |
| C8 | 无形资产循环控制测试 | C | false |
| C9 | 研发循环控制测试 | C | false |
| C10 | 职工薪酬循环控制测试 | C | true |
| C11 | 管理循环控制测试 | C | true |
| C12 | 税金循环控制测试 | C | true |
| C13 | 债务循环控制测试 | C | false |
| C14 | 租赁循环控制测试 | C | false |
| C15 | 关联方循环控制测试 | C | false |
| C2-2 | 销售循环评价控制偏差 | C | false |
| C3-2 | 货币资金循环评价控制偏差 | C | false |
| C4-2 | 存货循环评价控制偏差 | C | false |
| C5-2 | 投资循环评价控制偏差 | C | false |
| C6-2 | 固定资产循环评价控制偏差 | C | false |
| C7-2 | 在建工程循环评价控制偏差 | C | false |
| C8-2 | 无形资产循环评价控制偏差 | C | false |
| C9-2 | 研发循环评价控制偏差 | C | false |
| C10-2 | 职工薪酬循环评价控制偏差 | C | false |
| C11-2 | 管理循环评价控制偏差 | C | false |
| C12-2 | 税金循环评价控制偏差 | C | false |
| C13-2 | 债务循环评价控制偏差 | C | false |
| C14-2 | 租赁循环评价控制偏差 | C | false |
| C15-2 | 关联方循环评价控制偏差 | C | false |
| C21 | IT专业人员资质 | C | true |
| C21-1 | IT审计发现汇总表 | C | false |
| C22 | IT一般控制测试 | C | true |
| C23 | 会计分录控制测试 | C | true |
| C24 | 会计分录细节测试 | C | true |
| C25 | 利用内审工作 | C | false |
| C26 | 信息处理控制测试 | C | false |

### 2.2 _WP_CODE_OVERRIDE 完整映射表

在 `wp_classification_service.py` 的 `_WP_CODE_OVERRIDE` 中添加：

```python
# C 类 — 控制测试
"C1": "a-program-console",
"C2": "d-form-table",
"C3": "d-form-table",
"C4": "d-form-table",
"C5": "d-form-table",
"C6": "d-form-table",
"C7": "d-form-table",
"C8": "d-form-table",
"C9": "d-form-table",
"C10": "d-form-table",
"C11": "d-form-table",
"C12": "d-form-table",
"C13": "d-form-table",
"C14": "d-form-table",
"C15": "d-form-table",
"C2-2": "d-form-table",
"C3-2": "d-form-table",
"C4-2": "d-form-table",
"C5-2": "d-form-table",
"C6-2": "d-form-table",
"C7-2": "d-form-table",
"C8-2": "d-form-table",
"C9-2": "d-form-table",
"C10-2": "d-form-table",
"C11-2": "d-form-table",
"C12-2": "d-form-table",
"C13-2": "d-form-table",
"C14-2": "d-form-table",
"C15-2": "d-form-table",
"C21": "d-form-table",
"C21-1": "d-form-table",
"C22": "audit-sheet",
"C23": "d-form-table",
"C24": "d-form-table",
"C25": "d-form-table",
"C26": "d-form-table",
```

### 2.3 procedure_table_templates.json 扩展

仅 C1 需要程序表模板（136 步），格式同 B1A：

```json
{
  "C1": {
    "name": "企业层面控制测试程序表",
    "items": [
      {"seq": 1, "content": "一、控制环境", "is_header": true},
      {"seq": 2, "content": "1.1 管理层对诚信和道德价值观的沟通和践行", "ref_index": "C1-1"},
      {"seq": 3, "content": "1.2 治理层独立于管理层，并对内控进行监督", "ref_index": null},
      ...
      {"seq": 136, "content": "五、监督活动 5.2 评价并沟通内部控制缺陷", "ref_index": null}
    ]
  }
}
```

### 2.4 auto_data_source 新增 resolvers

| source 名 | 用途 | 数据来源 | 返回格式 |
|-----------|------|---------|---------|
| `control_test_result_for_cycle` | D~N 读取 C 类测试结论 | field_overrides scope=`control_test_result:{cycle}` | `{summary, cycle, deviation_count, tested_controls}` |
| `b23_walkthrough_for_cycle` | C 类读取 B23 穿行测试结论 | field_overrides scope=`b23_walkthrough:{cycle}` | `{summary, conclusion, cycle_name}` — **已存在** |
| `b22_entity_control_list` | C1 读取 B22 企业层面控制清单 | field_overrides scope LIKE `b22%` | `{summary, completed, dimensions}` |
| `itgc_test_result` | D~N 读取 IT 控制测试结论 | field_overrides scope=`itgc_test_result` | `{summary, sa, pe, pm, ns, overall, finding_count}` |
| `je_filter_from_ledger` | C24 从序时账筛选分录 | tb_ledger 表 | `{summary, candidate_count, filter_criteria}` |
| `internal_audit_reliance` | 影响审计范围 | field_overrides scope=`internal_audit_reliance` | `{summary, conclusion, scope_reduction}` |

## 3. C-generic.yaml Schema 设计

C2~C15 共用一套通用 schema（仅 `cycle_name` 参数化）：

```yaml
# backend/data/ledger_adapters/wp_render_schema/C-generic.yaml
wp_code_pattern: "C{n}"
template_version: "v2025-R5"
sheets:
  控制测试汇总表:
    component_type: d-form-table
    fields:
      - {field: sub_process, label: 子流程, type: text}
      - {field: control_id, label: 控制编号, type: text}
      - {field: control_name, label: 控制名称, type: text}
      - {field: control_description, label: 控制描述, type: textarea}
      - {field: affected_accounts, label: 受影响科目, type: text}
      - field: assertion
        label: 认定
        type: enum
        enum: [存在, 完整性, 准确性, 截止, 分类, 列报, 权利和义务, 计价和分摊]
      - field: control_attribute
        label: 控制属性
        type: enum
        enum: [预防性, 检查性]
      - field: frequency
        label: 频率
        type: enum
        enum: [每次发生, 每日, 每周, 每月, 每季, 每年]
      - field: test_method
        label: 测试方法
        type: enum
        enum: [检查, 观察, 重新执行, 询问]
      - field: sample_size
        label: 样本量
        type: number
        auto_recommend: true
      - field: test_conclusion
        label: 测试结论
        type: enum
        enum: [有效, 无效, 不适用]
    dynamic_table:
      add_row_button: true
      max_rows: 100
  控制测试过程记录:
    component_type: d-form-table
    fields:
      - {field: sample_no, label: 样本编号, type: text}
      - {field: sample_description, label: 样本描述, type: textarea}
      - {field: test_steps, label: 测试步骤, type: textarea}
      - field: test_result
        label: 测试结果
        type: enum
        enum: [通过, 偏差]
      - {field: deviation_note, label: 偏差说明, type: textarea, visible_when: "test_result=='偏差'"}
    dynamic_table:
      add_row_button: true
      group_by: control_id
      max_rows: 500
```

### 3.1 样本量自动推荐逻辑

当 `auto_recommend: true` 时，前端根据 `frequency` 字段值自动推荐：

| 频率 | 总体量 | 推荐样本量 |
|------|--------|-----------|
| 每次发生 | ≥25件 | 25 |
| 每日 | ≥250件 | 25 |
| 每周 | 52件 | 5 |
| 每月 | 12件 | 2 |
| 每季 | 4件 | 1 |
| 每年 | 1件 | 1 |

用户可手动覆盖，覆盖后显示 `(手动)` 标记。

## 4. C-deviation-generic.yaml Schema 设计

C2-2~C15-2 共用偏差评价 schema：

```yaml
# backend/data/ledger_adapters/wp_render_schema/C-deviation-generic.yaml
wp_code_pattern: "C{n}-2"
template_version: "v2025-R5"
sheets:
  评价控制偏差:
    component_type: d-form-table
    fields:
      - {field: control_id, label: 控制编号, type: text, readonly: true, source: "C{n}"}
      - {field: exception_description, label: 例外事项描述, type: textarea}
      - field: step1_isolated
        label: 评价步骤1：该偏差是否属于孤立事件
        type: enum
        enum: [是, 否]
      - {field: step2_cause, label: 评价步骤2：该偏差的原因, type: textarea}
      - field: step3_design_defect
        label: 评价步骤3：是否表明控制设计存在缺陷
        type: enum
        enum: [是, 否]
      - {field: step4_supplementary_procedures, label: 评价步骤4：已执行的补充审计程序, type: textarea}
      - field: step5_reliance_impact
        label: 评价步骤5：对拟信赖程度的影响
        type: enum
        enum: [无影响, 降低信赖, 不信赖]
      - {field: step6_substantive_impact, label: 评价步骤6：对实质性程序性质时间范围的影响, type: textarea}
      - field: step7_report_deficiency
        label: 评价步骤7：是否构成控制缺陷需上报
        type: enum
        enum: [是, 否]
      - field: conclusion
        label: 结论
        type: enum
        enum: [有效但存在偏差, 无效需扩大测试, 无效且已放弃信赖]
    dynamic_table:
      add_row_button: true
      max_rows: 50
```

## 5. Pattern Matching 实现

在 `wp_render_schema_service.py` 的 `_PATTERN_SCHEMA_MAP` 中新增两条规则：

```python
_PATTERN_SCHEMA_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^B23-(\d{1,2})$"), "B23-generic.yaml"),
    # C 类通用 schema
    (re.compile(r"^C(\d{1,2})$"), "C-generic.yaml"),         # C2~C15
    (re.compile(r"^C(\d{1,2})-2$"), "C-deviation-generic.yaml"),  # C2-2~C15-2
]
```

范围校验逻辑需更新 `_resolve_schema_path`：
- `^C(\d{1,2})$`：匹配 n∈[2,15] → C-generic.yaml
- `^C(\d{1,2})-2$`：匹配 n∈[2,15] → C-deviation-generic.yaml

同时为 C-generic.yaml 添加 `_inject_c_cycle_name` 参数化注入（参照 B23 模式）：

```python
_C_CYCLE_NAMES: dict[str, str] = {
    "C2": "销售收入", "C3": "货币资金", "C4": "采购存货",
    "C5": "投资", "C6": "固定资产", "C7": "在建工程",
    "C8": "无形资产", "C9": "研发", "C10": "职工薪酬",
    "C11": "管理", "C12": "税费", "C13": "债务",
    "C14": "租赁", "C15": "关联方",
}
```

## 6. 联动实现方案

### 6.1 B23→C 读取（已完成）

C 类底稿通过 `auto_data_source: "b23_walkthrough_for_cycle"` 读取对应循环 B23 穿行测试结论。
该 resolver 读取 `field_overrides` scope=`b23_walkthrough:{cycle}`。

**已在 B 类 P4 实现**（`_on_b23_saved` handler 写入端）。

### 6.2 C→D~N 写入（EventBus handler）

```python
async def _on_c_control_test_saved(payload: EventPayload) -> None:
    """C 类控制测试保存 → 写入 field_overrides 供 D~N 读取。

    触发条件：
    - event_type == WORKPAPER_SAVED
    - payload.extra['wp_code'] 匹配 ^C(\d{1,2})$（2≤n≤15）

    写入目标：
    - scope = control_test_result:{cycle}
    - fields: cycle, conclusion, deviation_count, tested_controls
    """
    wp_code = payload.extra.get("wp_code", "")
    m = re.match(r"^C(\d{1,2})$", wp_code)
    if not m:
        return
    n = int(m.group(1))
    if not (2 <= n <= 15):
        return

    cycle = _C_CYCLE_NAMES.get(wp_code, "")
    # 从保存数据中聚合测试结论
    parsed_data = payload.extra.get("parsed_data", {})
    summary_rows = parsed_data.get("控制测试汇总表", [])
    tested = len(summary_rows)
    deviations = sum(1 for r in summary_rows if r.get("test_conclusion") == "无效")

    if deviations == 0:
        conclusion = "有效"
    elif deviations < tested:
        conclusion = "部分有效"
    else:
        conclusion = "无效"

    # 写入 field_overrides
    scope = f"control_test_result:{cycle}"
    await svc.set_batch(project_id, year, scope, {
        "conclusion": conclusion,
        "deviation_count": str(deviations),
        "tested_controls": str(tested),
        "deviation_refs": f"C{n}-2" if deviations > 0 else "",
    })
```

### 6.3 C偏差→issue_tickets 自动创建

当 C{n}-2 偏差评价 `step7_report_deficiency == "是"` 时：

```python
# 自动创建 IssueTicket
IssueTicket(
    project_id=project_id,
    category="control_deficiency",
    severity=infer_severity(conclusion),  # 无效且放弃→major, 无效扩大→minor
    title=f"{cycle}循环控制偏差 - {control_id}",
    description=exception_description,
    source="c_deviation_eval",
    source_ref_id=workpaper_id,
    owner_id=current_user_id,
)
```

### 6.4 C22→C21-1 发现自动创建

当 C22 步骤 sheet 结论单元格值为"无效"时：

```python
# 通过 address_registry 读取 C22 各步骤结论坐标
# 如 SA-3 结论 = Sheet "SA-3" Cell "E28" 值为"无效"
# → 自动在 C21-1 创建一条发现记录
finding = {
    "source_wp": "C22",
    "control_area": "SA",  # 从 sheet name 解析
    "description": "",     # 待填写
    "risk_level": None,    # 待填写
    "status": "未整改",
}
```

### 6.5 C24→sampled_vouchers 一键抽凭

用户在 C24 细节测试中检查某条分录时，一键添加到 `sampled_vouchers` 表：

```python
POST /api/projects/{pid}/ledger/sample-voucher
{
    "voucher_no": "记-2025-001234",
    "year": 2025,
    "source": "C24",
    "working_paper_id": c24_wp_id,
}
```

复用已有 sampled_vouchers 端点（V084 迁移已建表）。

## 7. 前端路由

不需要新的顶层页面。复用现有底稿路由：

```
/projects/:pid/workpapers/:wpId → GtWpRenderer → componentType 路由
```

C22 走 `audit-sheet` componentType → OnlyOffice 渲染（与 B30-2A/B60-1 相同）。
其余走 `d-form-table` 或 `a-program-console`（与 B 类完全相同的前端链路）。


## 8. 正确性属性 (Correctness Properties)

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: C 类循环控制测试 pattern matching

*For any* wp_code 格式为 `C{n}`（其中 n 为整数且 2≤n≤15），调用 `WpRenderSchemaService.load_schema(wp_code)` 应返回 C-generic.yaml 的解析内容，且所有 14 个有效 wp_code 均解析到同一 schema 文件。

**Validates: Requirements G1-1.1, G1-1.2**

### Property 2: C 类偏差评价 pattern matching

*For any* wp_code 格式为 `C{n}-2`（其中 n 为整数且 2≤n≤15），调用 `WpRenderSchemaService.load_schema(wp_code)` 应返回 C-deviation-generic.yaml 的解析内容，且所有 14 个有效 wp_code 均解析到同一 schema 文件。

**Validates: Requirements G2-1.1, G2-1.2**

### Property 3: Schema 完整性校验

*For any* 通过 pattern matching 加载的 C-generic.yaml schema，其"控制测试汇总表" sheet 必须包含全部 11 个必需字段（sub_process, control_id, control_name, control_description, affected_accounts, assertion, control_attribute, frequency, test_method, sample_size, test_conclusion），且不包含名为"选项清单"的 sheet。*For any* 加载的 C-deviation-generic.yaml schema，其"评价控制偏差" sheet 必须包含全部 10 个必需字段且不包含"示例" sheet。

**Validates: Requirements G1-1.4, G1-1.6, G2-1.3, G2-1.4**

### Property 4: 控制测试结论写入-读取 round-trip

*For any* 项目和循环，当控制测试汇总表保存结论后，通过 `control_test_result_for_cycle` resolver 读取该循环的结论数据，应得到与写入时一致的 conclusion/deviation_count/tested_controls 值。

**Validates: Requirements G1-4.1, G1-4.2, G1-4.3, G1-4.4**

### Property 5: ITGC 测试结论写入-读取 round-trip

*For any* 项目，当 C22 全部 4 个领域（SA/PE/PM/NS）测试完成后写入 field_overrides scope=`itgc_test_result`，通过 `itgc_test_result` resolver 读取应得到与写入时一致的 sa/pe/pm/ns/overall/finding_count 结构。

**Validates: Requirements G4-5.1, G4-5.2, G4-5.3**

### Property 6: 偏差自动创建

*For any* C{n}（2≤n≤15）控制测试过程记录中标记为"偏差"的样本，保存后对应的 C{n}-2 偏差评价底稿应自动包含一条与该偏差关联的待评价记录。偏差记录的 control_id 应与源控制测试中的控制编号一致。

**Validates: Requirements G2-2.1**

### Property 7: 偏差上报自动创建 issue_ticket

*For any* C{n}-2 偏差评价中 step7_report_deficiency 为"是"的记录，系统应自动在 issue_tickets 中创建一条 category='control_deficiency' 的记录，且 source_ref_id 指向该偏差评价底稿的 working_paper_id。

**Validates: Requirements G2-3.2**

### Property 8: C22 步骤无效自动创建 C21-1 发现

*For any* C22 步骤 sheet 的结论单元格值为"无效"，系统应自动在 C21-1 IT 审计发现汇总表中创建一条记录，source_wp='C22' 且 control_area 与步骤 sheet 所属领域（SA/PE/PM/NS）一致。

**Validates: Requirements G4-3.3**

### Property 9: 序时账分录筛选正确性

*For any* 筛选条件集合（金额阈值/非工作时间/非常规科目/整数金额）和 tb_ledger 数据，`je_filter_from_ledger` resolver 返回的候选分录应全部满足至少一个筛选条件，且不遗漏满足条件的分录。

**Validates: Requirements G5-2.4, G5-2.5**

### Property 10: C24 抽凭 round-trip

*For any* C24 细节测试中检查的分录，一键添加到 sampled_vouchers 后，查询 sampled_vouchers 表应包含该分录且 source='C24'、working_paper_id 指向 C24 底稿。

**Validates: Requirements G5-3.1**

### Property 11: 偏差评价结论联动更新

*For any* C{n}-2 偏差评价结论为"无效需扩大测试"或"无效且已放弃信赖"时，对应循环的 field_overrides scope=`control_test_result:{cycle}` 中的 conclusion 应被更新为"部分有效"或"无效"。

**Validates: Requirements G2-3.1**

### Property 12: B23 穿行测试结论可读性

*For any* 已完成 B23 穿行测试的循环，C 类底稿通过 `b23_walkthrough_for_cycle` resolver 应能读取到有效的 conclusion 值（"设计有效"/"设计无效"），且 cycle_name 与目标循环一致。

**Validates: Requirements G1-3.1**

## 9. 错误处理

| 场景 | 处理方式 |
|------|---------|
| C-generic.yaml 文件不存在 | `load_schema` 抛 FileNotFoundError，前端显示降级提示 |
| pattern matching n 超出 [2,15] 范围 | 不匹配任何 pattern，走 prefix fallback 或 404 |
| field_overrides 写入失败 | EventBus handler 捕获异常，记录 WARNING，不阻断保存 |
| C22 address_registry 坐标未注册 | custom_query 返回空值，前端显示"数据未就绪" |
| je_filter_from_ledger 无序时账数据 | resolver 返回 `{summary: "序时账未导入", candidate_count: 0}` |
| issue_ticket 重复创建（幂等） | 通过 source_ref_id 唯一约束防重，IntegrityError 静默跳过 |
| B23 穿行测试未完成（无数据） | resolver 返回 `{summary: "穿行测试未完成", conclusion: null}` |

## 10. 测试策略

### 10.1 单元测试

- `_WP_CODE_OVERRIDE` 覆盖全部 36 个 C 类 wp_code（扩展 smoke test）
- C1 程序表 JSON 模板校验（136 步 seq 连续、ref_index 合法）
- 样本量推荐逻辑 6 种频率 → 正确样本量映射
- 偏差评价 7 步字段 enum 值校验

### 10.2 属性测试（Hypothesis, min 100 iterations）

- **Feature: c-cycle-workpapers, Property 1**: Pattern matching C2~C15
- **Feature: c-cycle-workpapers, Property 2**: Pattern matching C2-2~C15-2
- **Feature: c-cycle-workpapers, Property 3**: Schema 完整性
- **Feature: c-cycle-workpapers, Property 4**: 控制测试结论 round-trip
- **Feature: c-cycle-workpapers, Property 5**: ITGC 结论 round-trip
- **Feature: c-cycle-workpapers, Property 9**: 序时账筛选正确性

### 10.3 集成测试

- auto_data_resolvers 新增 resolver 覆盖（扩展 `test_auto_data_resolvers.py`）
- EventBus handler `_on_c_control_test_saved` 端到端写入验证
- C偏差→issue_tickets 自动创建验证

### 10.4 E2E（Playwright）

- C2 循环控制测试：打开→多 sheet 切换→填写→保存
- C1 企业层面程序表：136 步渲染→步骤执行→ref_index chip
- C22 IT 一般控制：OnlyOffice 打开→34 sheet Tab 展示
- C24 会计分录细节测试：筛选→检查→抽凭联动
- C2-2 偏差评价：7 步填写→结论→issue_ticket 创建确认

### 10.5 属性测试库

Python: `hypothesis`（已配置，max_examples=5 遵循用户偏好）

每个 property test 必须以注释引用设计属性：
```python
# Feature: c-cycle-workpapers, Property 1: C 类循环控制测试 pattern matching
@given(n=st.integers(min_value=2, max_value=15))
def test_c_generic_pattern_matching(n):
    ...
```
