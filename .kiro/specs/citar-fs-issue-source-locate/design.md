# 设计：不平差额拆到源头行

## 1. 差额怎么拆（新模块 `backend/app/services/tax_assurance/fs_balance_sources.py`）

记 D = 资产总计 − 负债和所有者权益总计（某一列）。报表每行对科目余额都是线性的，所以不计手工值时
`D_auto = Σ_c k_c·b_c + k_PL·PL_CLOSE`：b_c 是该标准科目代入报表的金额（期末取 `balances_of` 的 closing，上年年末取 opening），
k_c 用「只给这一个科目 1 元余额」现算（`compute_statement` 同一函数，不手写系数）。e_c = 损益类 0、其余 1。

期末列：
```
D_eff = (D_eff − D_auto)                                   手工修改（本页格）
      + Σ_c (k_c − e_c)·b_c + (k_PL − 1)·PL_CLOSE           没进 / 重复进资产负债表（试算平衡表行）
      + Σ_非损益 (b_c − adjusted_closing_c)                  审定数与余额表 + 调整不一致（试算平衡表行，未重算）
      + A_net（已批准非底稿调整 借 − 贷）                    调整分录借贷不平（调整分录页）
      + W（Σ wp_adjustment 借正贷负）                       底稿发布调整合计不为 0（试算平衡表行）
      − U_cl（未映射末级科目期末合计）                       有余额未映射（底稿映射行）
      + L_cl（全部末级科目期末合计）
L_cl = Σ期初 + Σ(期末 − 期初 − 借 + 贷)行内不一致 + Σ(借 − 贷)
Σ(借 − 贷) = Σ_叶 [(借 − 贷)余额表 − (借 − 贷)序时账归到该叶] + 序时账借 − 贷 − 序时账未归到任何叶的(借 − 贷)
```
序时账按科目编码「最长前缀」归到余额表末级科目（编码先剥 `.0`）。没有序时账时 Σ(借 − 贷) 只能指到科目余额表页。

上年年末列（PL_CLOSE = 0；试算表损益类期初恒 0）：
```
D_eff = 手工 + Σ_非损益 (k_c − 1)·b_c
      + Σ_非损益 (b_c − 映射末级期初_c)                      试算表期初未重算
      − U_op − Σ 损益类末级期初                             未映射 / 损益类有期初（余额表行）
      + Σ 全部末级期初                                      余额表期初不平（只能指到页）
```
算完 `残差 = D_eff − Σ各项`，|残差| ≥ 0.005 单列「其余差额未能定位」。

只在校验不通过、且不限循环范围时算；导出不算。失败只记日志、报表照常返回（只读）。

## 2. 数据形状
`checks[i].sources` / `notice_sources[提示文字]`：
```json
{"kind": "ledger_mismatch", "title": "科目余额表本期发生额与序时账不一致", "amount": {"n": "-11340.42"},
 "page": "balance", "rows": [{"code": "5801", "name": "以前年度损益调整", "amount": {"n": "-11340.42"},
 "note": "余额表 借 -11,340.42 贷 0.00；序时账 借 0.00 贷 0.00", "journal": true}], "more": 0}
```
`page`：balance / journal / mapping / trial_balance / adjustments / ledger_import / reports / statement（statement 行带 statement / r / column）。
后端只给语义，路由在前端 `fsIssueSources.ts::sourceLink` 一处换算。

## 3. 前端
- `CitarFsIssueSources.vue`（新）：问题下列「数据源头」，每行一个按钮；单体财务报表页只接线。
- 源头页读 `?locate=`：`useCitarRowLocate.ts`（新）滚到 `[data-locate="编码"]` 并高亮，样式 `citar-data.css` `.citar-located`。
  科目余额表清关键字 / 只看末级 / 只看已修改；试算平衡表清关键字、零余额行切到底稿取数余额表；底稿映射切到「客户科目 → 标准科目」。
- 账务查询 `?tab=balance&locate=`；切页签去掉 `locate`。
- 「去审定报表」按钮改由 `notice_sources` 给出。

## 4. 不做
- 序时账里定位到某张凭证（按科目筛选已能看到全部分录）；CAS 格式平衡校验；期初不平再往上年追。
