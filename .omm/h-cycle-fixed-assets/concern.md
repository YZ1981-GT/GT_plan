# 关注点 / 已知脆弱处（H 循环）

## 1. 🔴 H3 的 1503/1504 与 G6/G8 撞码

`useH3FormData` 用 `ACCOUNT_CODE_1503='1503'`（投资性房地产）+ `1504`（累计折旧），
但 `backend/data/standard_account_chart.json` 里 **1503 = 可供出售金融资产、1504 = 债权投资、1521 = 投资性房地产**，
而 G6（其他债权投资）/ G8（其他权益工具投资）前端也都用 `1503`。
→ 三个底稿（H3 / G6 / G8）对同一 TB 科目取数与回写会互相覆盖。**未核实是否刻意迁就旧准则账套，不擅自改**。

## 2. H1 曾经的四类真实缺陷（勿回退）

- **render 取数父子双算**：`_build_category_prefill` / `_fetch_tb_data` 用 `code.startswith(prefix)` 会把父级 1601
  与子级 1601.01~.99 同时累加 → 预填约 2×；必须叶子过滤（`_leaf_codes`：某 code 不是任何其它 code 的前缀）+ 发生额 `abs()` 归一
  （两种账套并存：贷方有存正数也有存负数）
- **附注章节号错**：`H1_NOTE_SECTION.listed` 曾写 `五、15`（那是源模板表头序号），权威 `note_template_variant_matrix.gu_ding_zi_chan`
  是 **五、22**；而 listed 的 五、15 实际是"其他债权投资" → 同步会把固定资产表塞进别的附注并覆盖其正文。H6 复用 H1 map 同样错过
- **折旧月度 resolver 死了很久**：`h1_depreciation_monthly` 查 `tb_ledger.occurrence_date`（该列不存在，真实是 `voucher_date`），
  且裸 `is_deleted=false` 跨 dataset 重复 → 查询恒失败被 except 吞成"数据获取失败"
- **抽凭引擎 stale binding**：H1-7/H1-8 曾用 `:account-codes="['1601']"` + `dialog-mode` + `@filled(samples:array)`，
  与引擎真实 API（`account-code` 单数 + `phase` + `workpaper-id` + `year`，emit 对象 `{samples,...}`）不符 → 一直是坏的

## 3. H2 抽凭同款 stale（已修）

H2-8/H2-9 曾同样用旧 API（`:account-codes` + `dialog-mode` + `onSampleFilled(samples)` 把对象当数组）→ 缺 required props 必 422 + 静默 no-op。

## 4. 折旧费用归属不可自动归集

`tb_ledger.counterpart_account` 填充率极低（H1 实测 1602 仅 ~9%），按 `voucher_no` 归集同凭证借方会混入
银行存款 / 应付账款等合并记账科目（实测数亿 vs 当年折旧数百万）→ **折旧费用按部门/科目自动归集是宁缺勿造项**，
只做总额层取数与核对。

## 5. `tb_aux_balance` 无资产卡片维度

H1 实测 160% 科目仅 87 行、`aux_type=FFLEX10` 只有 3 个 name → **卡片级明细不做自动取数**。
资产明细只能从明细表人工/导入，不要臆造"从辅助账取卡片"。

## 6. H3/H7 计量模式分叉容易漏

成本模式与公允价值模式的 sheet 集合、是否计折旧、公允变动去处都不同。
模式切换要同时切审定表结构、折旧表适用性、附注版本，任一处没跟就会出现"公允模式还在算折旧"。

## 7. H8/H9 双侧不一致是最常见错

租赁期 / IBR / 付款额三者在 H8 与 H9 必须一致；H8-5 改租赁期若未推送 H8-6/H8-8/H9，
就会出现"资产按 5 年折旧、负债按 3 年摊销"。终止租赁必须双侧同时结清。

## 8. H6 是过渡科目，期末通常应为零

1606 固定资产清理是过渡科目，期末有余额需解释（未完成清理）。
H6 的净损益要流向 H10（6115），不能挂账不结转。

## 9. `working_papers` 表名 bug（平台级，H 相关 loader 曾中招）

多个跨底稿 loader 写了 `JOIN working_papers`（复数），真实表名是 `working_paper`（单数）→ 查询直接抛错被静默吞。
已修 4 处（A9 缺陷函 / A27-1 IT 备忘录 / A12-1 律师函 / A10-1 治理沟通），其余待排查。
