# 说明

产出方式、字段约定、维护约定见 `.omm/d-cycle-sales/note.md`。

## 本 perspective 的事实来源

- 20 个 componentType → `htmlRendererRegistry.ts`（`g1-trading-financial-assets` / `g2-interest-receivable` /
  `g3-dividend-receivable` / `g4-bond-investment-main|sppi|ecl` / `g5-long-term-receivable` /
  `g6-other-bond-investment-main|sppi|ecl` / `g7-long-term-equity-main|method|subsidiary` /
  `g8-other-equity-instruments` / `g9-other-noncurrent-financial` / `g10-trading-financial-liabilities` /
  `g11-investment-income` / `g12-net-hedge-gains` / `g13-fair-value-changes` / `g14-credit-impairment-loss`）
- 20 个后端 render 策略 → `backend/app/routers/wp_render_strategies/__init__.py` 的 `RENDERER_DISPATCH`
- 前端目录结构 → `Get-ChildItem` 逐个 `g*` 目录（21 个目录，含 `g0-confirmation`）
- 科目码 → 各 `g{n}Constants.ts` / `g{n}AdjudicationItems.ts` / `g{n}CrossHelpers.ts` 的 `G{n}_ACCOUNT_CODE`
- 科目码对照 → `backend/data/standard_account_chart.json`（1101 交易性金融资产 / 1504 债权投资 /
  1505 债权投资减值准备 / 1506 其他债权投资 / 1507 其他权益工具投资 / 1511 长期股权投资 /
  1519 其他非流动金融资产 / 1531 长期应收款 / 2101 交易性金融负债）
- 附注章节号 → 各 `g{n}NoteSectionMap.ts`（G1 五、2+五、3 / G2 五、8 / G8 五、19 / G9 五、20 /
  G10 五、34+五、35 / G11 五、69 / G12 五、70 / G13 三、公允价值变动收益 / G14 三、信用减值损失）

## 未核实项

- **后端 render 策略文件路径为 `backend/app/routers/wp_render_strategies/`**（本仓库后端根是 `backend/`，
  不是 `audit-platform/backend/`；前端才在 `audit-platform/frontend/`）
- G3 / G4 / G5 / G6 / G7 的附注章节号未在本轮逐一读取（G7 按既有复盘记录 五、18 / 八、18）
- 各入口 sheet ↔ Tab 的精确映射未逐一读主入口 `v-if` 分发链；本文按目录/组件分组描述
- G1/G4/G6/G8 科目码与标准科目表的偏差**只做事实陈述，未判定对错**（见 `concern.md` §1）
