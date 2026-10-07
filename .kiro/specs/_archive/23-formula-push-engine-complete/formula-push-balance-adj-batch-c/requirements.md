# 需求：公式推送批 C — 资产负债类审定表族

> 前置：批 B（TierA 锚点）canary 通过。
> 交叉引用：`formula-push-all-subjects-rollout` design §十三。

## 1. 目标

用 `BalanceAdjudicationBinding` 族 binding 接管 K2~K7 / G1~G10 / H1~H10 / I1~I5 / J1~J2 共约 35 个科目的审定表推送。

## 2. 范围

| # | 需求 | 验收标准 |
|---|------|----------|
| C1 | 族 binding 实现 | `AdjudicationSpec` 数据类 + `BalanceAdjudicationBinding` 通过协议校验 |
| C2 | 逐科目声明 | 每科目的 spec 经现读确认（`account_codes`/`portfolio_rows`/`has_provision`/`nature_rows`/`fs_keys`） |
| C3 | 审定合计 | 全部科目复用 `_row_audited` 模式，双侧夹具对拍 |
| C4 | K2 canary L4 | 规则 / 夹具 / 真 ORM / 真 PG / 端点 / 前端 |
| C5 | Tier A 兼容 | H5~H10 / I1~I5 接管后锚点值不变 |
| C6 | 负债方向 | K3/K5/K7 备抵取绝对值、方向正确 |
| C7 | 无科目处理 | K4 只落派生合计 |
| C8 | 独占键 + 清册 | 生成器 `--check` 通过 |
| C9 | 推送→报表标 stale | 推送写入审定合计后，对应报表行 `is_stale=True` |
| C10 | 报表公式逐值对拍 | `ReportFormulaParser.resolve_tb(code,'期末余额')` == 推送审定合计 |
| C11 | `is_stale` 清除 | 报表重算后 `is_stale=False` + `current_period_amount` = 新值 |
| C12 | TB 回写一致性 | 审定表发布门写 `trial_balance.audited_amount` → 推送从同一字段取值，不存在双写竞争 |
| C13 | 明细表→审定表联动 | 明细表 `{code}-2` 保存 → 审定表组合行 unadj 自动更新（editable 策略） |
| C14 | 调整分录汇总联动 | `ADJ(code,'aje_net')` 推送写入审定表 aje 列（editable 策略，用户手录保留） |

## 3. 不做

- E1 / K1 单独 binding（已完成）
- 损益类审定表（归批 D）
- 附注推送铺开（归批 E）
