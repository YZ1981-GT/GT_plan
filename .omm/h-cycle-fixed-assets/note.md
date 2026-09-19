# 说明

产出方式、字段约定、维护约定见 `.omm/d-cycle-sales/note.md`。

## 本 perspective 的事实来源

- 10 个 componentType + render 策略 → `backend/app/routers/wp_render_strategies/__init__.py` 的 `RENDERER_DISPATCH`
  （`h1-fixed-assets` / `h2-construction-in-progress` / `h3-investment-property` / `h4-engineering-materials` /
  `h5-oil-gas-assets` / `h6-asset-disposal-clearing` / `h7-biological-assets` / `h8-right-of-use-assets` /
  `h9-lease-liabilities` / `h10-asset-disposal-income`）
- 前端目录与子目录 → `Get-ChildItem` 逐个 `h1`~`h10`（另有共享 `handbooks/module-editing-handbook.md`）
- 科目码 → 各 `useH{n}FormData.ts` 顶部常量（H1 1601/1602、H3 1503/1504、H4 1605+1604、H5 1631/1632、
  H6 1606、H7 1621、H8 1901/1902、H9 2205/1802）+ `h10Constants.H10_ACCOUNT_CODE='6115'`；
  H2 的 1604/1605 来自 `h2/core/H2TabAdjudication.vue`、`h2/handbooks/preparation.md`、`H2TabAdjustment.vue`
- H2 带入调整的参数（`subjectPrefix:'1604'` / `direction:'debit'` / 单一账项调整列增量累加）→ `H2TabAdjudication.vue`
- 科目码对照 → `backend/data/standard_account_chart.json`
- 折旧/减值/pull/OCR/双侧一致等机制 → 既有复盘记录（memory）+ 各 Tab 的编制提示文本

## 未核实项

- **H2 无独立科目码常量文件**，1604/1605 分散在 Tab 与手册中（本文按其文本记载）
- 各科目 sheet ↔ Tab 精确映射未逐一读主入口 `v-if` 分发链；本文按子目录分组描述
- H3 的 1503/1504 与 G6/G8 撞码**只做事实陈述未判定对错**（见 `concern.md` §1）
- H9/H8 附注章节号沿用既有复盘记录（H8 五、25/八、26；H9 五、47/八、52），本轮未重新读 map 文件
- H7 的 TB 取数/回写用 `account_codes` 参数 + `POST {items:[...]}` 批量形态，与其余科目 `account_prefix` + `PUT` 不同（已核实，属实现差异）
