# 设计：用户自定义公式 — 跨表格 / 跨科目 / 跨模块

## 一、新增求值函数

### 1.1 `WP()` — 跨底稿引用

```python
WP('D2', 'D2-1', 'D2-1-audited-receivable')
#   wp_code  sheet_code  item_id
# → 读 checklist_responses WHERE wp_code='D2' AND item_id=…
```

实现路径：
- `formula_engine` 的 `_execute_function` 新增 `WP` 分派
- 求值时需 `db` + `project_id` + `year` → 须在 FormulaContext 中注入异步取数回调
- 🔴 `formula_engine.execute` 当前是**同步**纯函数；`WP()` 需要查库 → 选项：
  - **A**：FormulaContext 预载（调用方传入已查好的 wp_data dict）→ 纯函数不变
  - **B**：改 execute 为 async → 影响面大
  - **建议选项 A**：调用方（公式管理面板后端）预查需要的底稿值，塞进 FormulaContext

### 1.2 `NOTE()` — 跨模块引用

```python
NOTE('五、1', '货币资金', '库存现金', 'end_amount')
#    section   table       row_label    field
# → 读 disclosure_notes WHERE note_section='五、1' → table_data → 定位行列
```

实现路径同 `WP()`：调用方预查附注数据，塞进 FormulaContext。

### 1.3 FormulaContext 扩展

```python
@dataclass
class FormulaContext:
    tb_data: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    adj_data: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    # 新增：
    wp_data: dict[str, Any] = field(default_factory=dict)     # {item_id: value}
    note_data: dict[str, Any] = field(default_factory=dict)   # {"五、1/货币资金/库存现金/end_amount": value}
    report_data: dict[str, Any] = field(default_factory=dict) # {"BS-001/期末": value}
```

## 二、用户公式 vs 系统推送优先级

| 目标类型 | 用户能否写自定义公式 | 推送是否覆盖 |
|----------|---------------------|-------------|
| `policy=system` | ❌ 面板禁止 | 推送总是覆盖 |
| `policy=derived` | ❌ 面板禁止 | 推送总是覆盖 |
| `policy=editable` | ✅ 允许 | 推送按三态判定（用户改过保留） |
| 无推送规则的 `item_id` | ✅ 允许 | 不推送 |

实现：面板加载规则后，system/derived 目标的「编辑」按钮置灰 + 提示「此单元格由系统公式维护」。

## 三、触发时机

- **公式管理面板打开时**：对当前底稿/报表/附注的全部用户公式求值一次，展示计算值
- **用户点「应用自动运算」**：把计算值写入对应 `checklist_responses` / `financial_report` / `disclosure_notes`
- **不自动持久化**：避免用户还在编辑时半成品值落库
- **跨科目依赖**（可选 Phase 2）：D2 审定合计变化后，引用它的 K1 用户公式在下次打开时显示 stale

## 四、跨科目依赖图（Phase 2）

```
address_registry_v2 的 l3 依赖图：
  K1-1/K1-1/K1-1-adj-total-1221 → deps: [D2-1/D2-1/D2-1-audited-receivable]
```

当 D2 审定合计被推送更新时：
1. 查依赖图找到引用方 K1
2. 标 K1 的用户公式 stale
3. 用户打开 K1 公式管理面板时重算

## 五、公式管理面板 UI

### 5.1 跨引用函数自动补全

在公式编辑输入框中：
- 输入 `WP(` → 弹出底稿选择器（已有 ACNR catalog 目录）
- 输入 `NOTE(` → 弹出附注章节选择器
- 输入 `REPORT(` → 弹出报表行选择器

### 5.2 错误提示

- `WP('D2','D2-1','不存在的键')` → 红色标记 + tooltip「D2-1 中未找到该键」
- `NOTE('五、99','不存在的表',...)` → 「附注无此章节」

### 5.3 表间审核 tab 扩展

公式管理已有「表间审核」tab（`crossCheckRules`）。当前只支持 `REPORT()` 和 `ROW()` 引用。
扩展支持 `WP()` 和 `NOTE()`：
- 左侧：`REPORT('BS-002','期末')` 报表货币资金
- 右侧：`NOTE('五、1','货币资金','合计','end_amount')` 附注货币资金合计
- 校验：左 == 右 → 绿色；差异 → 红色 + 差额

## 六、不改的部分

- `formula_engine.execute` 保持同步纯函数（调用方预载数据）
- 推送规则不可由用户编辑
- 公式语法（`TB()`/`SUM_TB()`/`ADJ()`/`ROW()`/`REPORT()`）不变
