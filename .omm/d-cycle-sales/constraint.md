# 约束（改 D 循环必须遵守）

## 会计与审计口径

- **科目方向**：资产期末 = 期初 + 借 − 贷；负债/权益 = 期初 + 贷 − 借。D1/D2/D5/D6 是资产（借方），D3/D7 是负债（贷方），D4 是损益（贷方，取发生额而非余额）。
- **只汇总叶子科目**：从 `tb_balance` 取数必须过滤叶子（某 code 不是任何其它 code 的前缀），否则父子双算。
- **损益类取发生额**：D4 不能取余额，须取 `tb_ledger` 借贷发生额净额。
- **审定数 = 未审 + AJE + RJE**，回写只写 `audited_amount`，不动 `unadjusted_amount`。
- **来源模板权威**：底稿列结构、附注表头、检查项文字一律对照致同 2025 修订版源模板，**禁止自造披露内容或列头**。

## 数据流方向

- 附注表格/叙述**单向**由底稿推送（`sync_from_workpaper`），附注模块侧编辑不回流底稿。
- 集中调整登记对 `origin='workpaper'` 的分录**禁止在中央页编辑**（底稿是唯一真源，再同步会覆盖）。
- `trial_balance` recalc 过滤 `origin != 'workpaper'`，避免审定表回写与集中调整双计。

## 工程红线

- **不新造持久化通道**：一律 `checklist_responses` + `useDxFormData`，不得直写 DB 或另起表。
- **跨表读写键必须两端一致**：消费端读的 `item_id` 必须有生产端真的在写；计算列（如 endBalance）不落库时消费端要现算。
- **动态行必须 JSON 单键存储 + hydrate**（`Dx-n-rows` 存整行数组），禁止 flat per-field 键 + 无 hydration（刷新即丢数据）。
- **UTF-8**：禁止用 PowerShell `Set-Content`/`Get-Content` 改 `.vue`/`.md`（会破坏中文编码或加 BOM），只用编辑工具的字符串替换。
- **验证三件套**：`get_diagnostics` 全清 + Vite transform 200（SFC/import 崩溃只有它能抓）+ 相关 vitest/pytest 绿；崩溃类问题以 Vite transform 为准。
