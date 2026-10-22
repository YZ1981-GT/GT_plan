# 公式推送子表级规则扩展 — 设计文档

## §1 规则结构示例

以 D2（应收账款）的坏账准备变动表为例：

```json
{
  "rule_id": "D2.note.movement",
  "page_key": "workpaper:D2",
  "stage": "note",
  "policy": "editable",
  "target": {
    "domain": "note",
    "section_by_template": {
      "listed": "五、5",
      "soe": "八、5"
    },
    "table_by_template": {
      "listed": "坏账准备变动",
      "soe": "（3）本期计提、收回或转回的坏账准备情况"
    },
    "table": "坏账准备变动",
    "fields": [
      "prior_amount",
      "provision_amount",
      "reversal_amount",
      "writeoff_amount",
      "end_amount"
    ]
  },
  "source": {
    "kind": "derivation",
    "name": "d2_note_movement",
    "formula_text": "数据来源：披露表 → 附注。从底稿 D2 的坏账准备变动子表读取全部行"
  },
  "triggers": ["WORKPAPER_SAVED", "manual"],
  "description": "应收账款坏账准备变动表推送（5 列：期初/计提/转回/核销/期末）"
}
```

## §2 NOTE_FIELDS 扩展

当前 NOTE_FIELDS 只有 8 个条目。子表有更多列需要注册：

```python
# 变动表类
"provision_amount": ("provision_amount", "end"),     # 本期计提
"reversal_amount": ("reversal_amount", "end"),       # 本期转回
"writeoff_amount": ("writeoff_amount", "end"),       # 本期核销
"transfer_amount": ("transfer_amount", "end"),       # 本期转销
"increase_other": ("increase_other", "end"),         # 本期其他增加
"decrease_other": ("decrease_other", "end"),         # 本期其他减少

# 分类表类
"ratio": ("ratio", "end"),                           # 比例(%)
"loss_rate": ("loss_rate", "end"),                   # 预期信用损失率(%)
"carrying_value": ("carrying_value", "end"),         # 账面价值
"book_amount": ("book_amount", "end"),               # 账面金额

# 明细表类
"aging": ("aging", "end"),                           # 账龄（文本列）
"basis": ("basis", "end"),                           # 计提理由（文本列）
```

## §3 规则数量估算

| 循环 | 科目数 | 平均子表数 | 估计新增规则数 |
|------|--------|-----------|---------------|
| D | 7 | 10 | ~70 |
| E+F | 6 | 5 | ~30 |
| G/H/I | 29 | 4 | ~116 |
| J/K/L/M/N | 38 | 2 | ~76 |
| **合计** | **80** | — | **~292** |

加上现有 80 条主表规则，总规则数约 372 条。

## §4 整表替换路径的适配

子表级规则走 `_push_note_disclosure_replace` 路径时，每条规则对应一张子表的整表替换。engine 的 `_push_workpaper` 按 rule 迭代，每条 note 规则调一次 `_push_note`，整表替换把该子表的行全部覆盖——无冲突，因为不同子表名不会撞到同一行。

## §5 生成工具

手写 292 条规则不现实。需要一个生成脚本：

```python
# scripts/gen/gen_subtable_push_rules.py
# 输入：note_template_{soe|listed}.json 的子表结构
# 输出：追加到 formula_push_rules.json 的新规则
```

脚本从模板 JSON 的 `sections[].tables[]` 提取子表名和列定义，为每张表生成一条规则。

## §6 与 spec 4 的联动

spec 4 的后端 builder 产出 `sub_table_data`，spec 5 的子表级规则消费它。两者通过 `table_name` 对齐：builder 产出的 key = 规则的 `target.table`。

如果 spec 4 未实现某科目的 builder，子表级规则仍然能从前端同步的 `sub_table_data` 取数（已有机制，spec note-data-from-disclosure-table Phase 2 已实现）。
