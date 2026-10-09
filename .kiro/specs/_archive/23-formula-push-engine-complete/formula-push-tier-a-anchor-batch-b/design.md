# 设计：公式推送批 B — Tier A 单公式锚点族

> 细化 `formula-push-all-subjects-rollout` design §九。

## 一、TierAAnchorBinding

```python
class TierAAnchorBinding:
    """单公式锚点族 binding：只有 system 单值目标、无派生、无附注。"""

    def __init__(self, wp_code: str, account_codes: tuple[str, ...]):
        self.wp_code = wp_code
        self.account_prefixes = account_codes
        self.derivations = frozenset()
        self.four_table_slots = frozenset()
        self.tb_columns = frozenset({"期末余额", "年初余额", "本期发生额"})
        self.paper_codes = (wp_code,)
```

- `load_sources` = `load_tb_audited(db, project_id, year, account_codes)`
- `workpaper_targets` = `formula_engine.execute(expression, context)` → `WorkpaperTarget`
- `apply` = `js_number_to_string(float(value))`
- `note_rows` = `[]`（Tier A 无附注）
- 注册表：`_REGISTRY[code] = f"...tier_a:binding_for('{code}')"`

## 二、规则迁移

每条锚点 → 一条规则：
```json
{
  "rule_id": "{code}.tb_reconcile.{suffix}",
  "page_key": "workpaper:{code}",
  "stage": "source",
  "policy": "system",
  "target": { "domain": "workpaper", "wp_code": "{code}", "sheet_code": "{code}-1", "item_id": "{item_id}" },
  "source": { "kind": "formula", "expression": "{expression}", "context": { "tb": "trial_balance_audited" } },
  "triggers": ["TRIAL_BALANCE_UPDATED", "manual"],
  "description": "试算平衡表数核对（{中文说明}）"
}
```

### 「审定数」列名改写（4 条）

D4-1 两条、H10、I6 的表达式含 `TB(code,'审定数')`。「审定数」是 `BANNED_COLUMNS`（与「期末余额」折叠）。
- 资产负债类（期末余额 = audited_amount）：改写为 `TB(code,'期末余额')`，等价。
- 损益类（发生额语义）：改写为 `TB(code,'本期发生额')`，context 改为 `trial_balance_audited_occurrence`。
- 逐条现读后在 tasks 证据栏写明选择依据。

## 三、D1/D2 减项码

`1231-01`（应收账款坏账）/ `1231-02`（其他应收款坏账）是带连字符的标准码。
- `load_tb_audited` 的 `LIKE '{code}%'` 能命中 `1231-01*` 不吞 `1231`。
- 测试：SQLite 造 `1231`（100）+ `1231-01`（50）+ `1231-02`（30），断言 `1231-01` 前缀只取 50。

## 四、canary = D4

首选理由：真库唯一有锚点数据的科目；损益类覆盖「审定数」改写。
- L4 验收：规则通过 / 合成 SQLite ORM / 真 PG 片段 / 端点 / 前端真挂载。

## 五、与批 C 的边界

批 B 只管 `*-tb-reconcile-*` 锚点键。批 C 管审定表组合行 / 审定合计。
同一 `wp_code` 可同时有两批的规则，`item_id` 不交叉。
批 C 的 `BalanceAdjudicationBinding` 须兼容执行批 B 的 `formula` 规则（注册表一码一 binding，批 C 接管后批 B 的规则由批 C binding 执行）。
