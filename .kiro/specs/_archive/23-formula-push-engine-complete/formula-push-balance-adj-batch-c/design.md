# 设计：公式推送批 C — 资产负债类审定表族

> 细化 `formula-push-all-subjects-rollout` design §十三。

## 一、`BalanceAdjudicationBinding` 族 binding

一个类服务全部资产负债类审定表科目，通过 `AdjudicationSpec` 实例化差异：

```python
@dataclass(frozen=True)
class AdjudicationSpec:
    wp_code: str
    account_codes: tuple[str, ...]
    portfolio_rows: tuple[PortfolioRowDef, ...]
    audited_total_keys: tuple[str, str, str]  # receivable, baddebt, net
    has_provision: bool = True
    nature_rows: tuple[NatureRowDef, ...] | None = None
    fs_reconciliation_keys: tuple[str, ...] | None = None
    extra_derivations: dict[str, Callable] = field(default_factory=dict)
    is_liability: bool = False
```

- `load_sources` = `load_tb_audited(db, project_id, year, spec.account_codes)`
- `workpaper_targets`：`formula` 分支走 `formula_engine.execute`（兼容 Tier A 锚点规则）；`derivation` 分支走 `_row_audited` 模式
- 审定合计 = Σ(unadj+aje+rje) 按组合行（复用 K1 的 `_round2` 模式）
- `apply` = `js_number_to_string(float(value))`

## 二、覆盖范围

| 循环 | 候选码 | 备注 |
|------|--------|------|
| K | K2~K7 | K4 `has_account=False` 仅落派生合计 |
| G | G1~G10 | G10 结构最复杂（8 子表），canary 不选 |
| H | H1~H10 | H5~H10 同时有 Tier A 锚点，须兼容执行 |
| I | I1~I5 | I6 损益类归批 D |
| J | J1~J2 | J3 渲染策略不取四表，暂不入 |

## 三、与批 B 的边界

同一 `wp_code`（如 H5~H10）可同时有批 B 锚点规则和批 C 审定表规则，`item_id` 不交叉。
注册表一码一 binding → 批 C 接管后，批 B 的 `formula` 规则由 `BalanceAdjudicationBinding.workpaper_targets` 的 `formula` 分支执行。

## 四、canary = K2

K2（其他流动资产）：无性质行、无备抵、单兜底行、`KCycleSpec` 声明已存在。最小验证集合。

## 五、铺开顺序

1. K2 canary → K3/K5/K7（负债）→ K4（无科目）→ K6
2. G1~G10
3. H1~H10（H5~H10 接管 Tier A）
4. I1~I5、J1~J2

## 六、规则结构

每科目生成：
- 组合行 editable 规则（`{code}-1-{receivable,baddebt}-r{n}-{begin,unadj}` 等）
- 审定合计 derived 规则（`{code}-1-audited-{receivable,baddebt,net}`）
- 可选：性质行 editable 规则（K 循环部分科目）
- 可选：FS 核对区 editable 规则
