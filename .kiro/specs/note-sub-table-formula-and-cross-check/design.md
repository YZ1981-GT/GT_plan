# 附注子表公式与跨表勾稽 — 设计文档

## 架构

在现有三层机制上做最小扩展，不重造基础设施。

### 扩展点 1：种子层扩展（plan_seed → plan_seed_sub）

新增 `plan_seed_sub(template_type, tables, single, report_rows)` 函数，专门给子表种公式：

- 不修改 `plan_seed` 原有逻辑
- 新增 `KIND_SUB_TABLE_TOTAL`（子表合计行 = 同表数据行之和）
- 新增 `KIND_CROSS_CHECK`（跨表校验：源表某行某列 = 目标表某行某列）
- 子表匹配不再依赖 `_single_table`（合并模板子表和单体模板表名不对应），改用 `section_id` 直接定位

种子写入同一个 `consol_note_formulas` 表，source 标记为 `seed_sub`（与主表 `seed` 区分）。

### 扩展点 2：check_rules 声明

在合并模板 JSON（`consol_note_sections_{soe,listed}.json`）中增加 `check_rules` 数组：

```json
{
  "section_id": "五-5-2",
  "check_rules": [
    {
      "check_id": "F4-8",
      "peer_section_id": "五-5-1",
      "peer_row_label": "合计",
      "peer_col_index": 1,
      "self_row_label": "合计",
      "self_col_index": 1,
      "relation": "equal",
      "description": "账龄表合计账面余额 = 坏账分类表合计账面余额"
    }
  ]
}
```

校验在后端由新函数 `check_note_cross_rules(db, project_id, year, section_id)` 执行：
- 读取两张子表的持久化数据
- 按 `row_label` + `col_index` 定位单元格值
- 返回 `[{check_id, status: "pass"|"fail"|"skipped", expected, actual, diff}]`

前端在附注页面展示勾稽结果（只读，不自动修正）。

### 扩展点 3：formula_push 子表规则

子表数据已存在于底稿披露表的 `sub_table_data` 中，通过 `sync_from_workpaper` 同步到附注。formula_push 的 note 规则只需定位这些已有子表并触发同步，不需要从零构建载荷。

在 `formula_push_rules.json` 中新增 E5 相关的 note 规则：

```json
{
  "rule_id": "E5.note.aging",
  "page_key": "workpaper:E5",
  "stage": "note",
  "target": {
    "domain": "note",
    "section_by_template": {"listed": "五、5", "soe": "八、5"},
    "table": "按账龄披露应收账款",
    "table_by_template": {"listed": "按账龄披露", "soe": "（1）按账龄披露应收账款"},
    "fields": ["end_amount", "prior_amount"]
  },
  "source": {"kind": "derivation", "name": "e5_aging"},
  "triggers": ["TRIAL_BALANCE_UPDATED", "WORKPAPER_SAVED", "manual"]
}
```

每个子表一条规则。binding 层的 `note_rows()` 从 E5 底稿披露表的 sub_table_data 中提取对应子表的行值——数据源已经在底稿里，不需要重新从 TB 取数。

### 扩展点 4：前端 E5 同步路径

确认 E5 底稿披露表的子表数据是否已经通过既有 `checklist-responses` 保存路径 → `WORKPAPER_SAVED` 事件 → `disclosure_stale_marker` 链路落入附注。如果已有路径，只需确保 formula_push 的 note 规则能触发 `_push_note` 定位到这些子表；如果缺失，则补齐 E5 的 `syncToDisclosureNotes` 前端调用。

## 实施顺序

1. **Phase 0**：check_rules 声明格式 + 后端校验函数 + 前端展示组件
2. **Phase 1**：E5 的 check_rules 声明（F4-3a/4/5/8/9）+ 校验端点
3. **Phase 2**：plan_seed_sub 子表种子 + E5 子表的 formula_push 规则
4. **Phase 3**：前端 E5 同步路径 + Playwright 验证
5. **Phase 4**：第二批科目（D 系列应收票据等）

## 风险

1. check_rules 声明依赖 headers 列索引——P1 列修复后索引可能变了，需对账
2. 子表行标签不稳定（如组合名称是可配置的"银行承兑汇票"、"商业承兑汇票"），匹配不能只靠文本
3. E5 没有 formula_push binding 实现——需要从零写 binding 层
