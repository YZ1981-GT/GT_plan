# 设计：公式推送附注铺开 · 批 D

## §1 族 binding 架构

```
bindings/
  __init__.py          # PushBinding 协议 + _REGISTRY
  e1.py / e1_calc.py   # E1（L3 完整实现）
  k1.py / k1_calc.py   # K1
  tier_a.py            # Tier A 锚点族（18 码）
  note_direct.py       # 📌 新建：附注直推族 binding
```

### NoteDirectBinding

```python
class NoteDirectBinding:
    """简单型附注直推族 binding：底稿审定表锚点 + 附注主表推送。"""
    def __init__(self, wp_code, account_codes, is_income=False):
        self.wp_code = wp_code
        self.account_prefixes = tuple(account_codes)
        self.tb_columns = frozenset({"期末余额", "年初余额", "本期发生额"})
        self.derivations = frozenset()
        self.four_table_slots = frozenset()
        self.paper_codes = (wp_code,)
        self._is_income = is_income  # 损益类用发生额口径

    async def load_sources(self, db, project_id, year, wp_id):
        tb = await load_tb_audited(db, project_id, year, self.account_prefixes)
        return NoteDirectSources(formula=FormulaSources(tb=tb))

    def workpaper_targets(self, rule, entries, sources, *, paper_code=None):
        # 同 TierA：单值公式目标
        ...

    def apply(self, entries, target, value):
        # 同 TierA：单值键写入
        ...

    def note_rows(self, entries, template_type, rule):
        # 从 TB 取数构建附注行
        ...

    def entry_warnings(self, entries):
        return []
```

### 工厂函数

```python
def note_direct_for(code: str) -> NoteDirectBinding:
    """按 wp_account_mapping 自动实例化。"""
    mapping = _load_mapping()
    item = mapping[code]
    is_income = _is_income_account(item["account_codes"][0])
    return NoteDirectBinding(code, item["account_codes"], is_income)
```

### 损益类识别

科目编码首位 `6` = 损益类，附注取数用 `'本期发生额'` 列：
- 6001（主营业务收入）→ K8（销售费用）
- 6301（营业外收入）→ K12
- 6602（研发费用）→ I6
- 6701/6702（资产减值/信用减值）→ K11/G14
- 6801（所得税费用）→ N5

## §2 与 Tier A 的关系

`NoteDirectBinding` 是 `TierAAnchorBinding` 的**超集**：Tier A 只有底稿锚点无附注，NoteDirectBinding 有两者。但不合并——Tier A 已在生产运行且有 250 个测试守护，改动 Tier A 的风险高于新建。

长期可以把 Tier A 迁移到 NoteDirectBinding（Tier A 的预设库可以生成规则），但不在本 spec 范围。

## §3 规则生成

每个科目生成两条规则：
1. **底稿锚点**（`stage: "source"`, `domain: "workpaper"`）—— `TB(code, '期末余额')`
2. **附注推送**（`stage: "note"`, `domain: "note"`）—— 章节编号从映射表取

规则由脚本从 `wp_account_mapping.json` + 章节映射表批量生成，手写风险太高。

## §4 注册与独占键

- 注册表 `_REGISTRY` 追加每个新科目一行
- 独占键生成器重跑：底稿锚点进独占集合（`policy: "system"`），附注规则不进
- 清册重生成：`has_note_rules` 更新

## §5 风险

- **科目码不全**：`wp_account_mapping.json` 可能缺子码（如减项备抵），单科目取数会漏。降级：先推主码，子码留给后续精修
- **附注行标签不匹配**：推送引擎 `find_row` 按标签找行，模板行标签与底稿科目名不完全一致时跳过。降级：记 warning 不报错，后续按 warning 逐个修正
