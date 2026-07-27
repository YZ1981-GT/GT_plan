# 说明

产出方式、字段约定、维护约定见 `.omm/d-cycle-sales/note.md`。

## 本 perspective 的事实来源

- 6 个 componentType + render 策略 → `backend/app/routers/wp_render_strategies/__init__.py`
  （`i1-intangible-assets` / `i2-development-expenditure` / `i3-goodwill` / `i4-long-term-prepaid` /
  `i5-other-noncurrent-assets` / `i6-research-development-expense`）
- 前端目录与子目录 → `Get-ChildItem` 逐个 `i1`~`i6`
- 科目码 → 各 `useI{n}FormData.ts` / `useI{n}Adjudication.ts` 顶部常量
  （I1 1701/1702/1703、I2 1717、I3 1711、I4 1801、I5 1911、I6 6602）
- I4 默认类别（装修费/开办费/租赁改良/技术转让费/其他）→ `useI4Adjudication.DEFAULT_CATEGORIES`
- I5 三层矩阵 + 期初账项/重分类调整 + 内置 10 类 + 从 D7/M12/G2-13 带入 → 既有 I5 复盘记录
- 附注章节号 → 既有复盘记录中登记的 `noteDisclosureReverseJump` 条目
  （I1 五、26/八、27、I2 五、27/八、28、I3 五、28/八、29、I4 五、29/八、30、I5 五、31/八、32、I6 五、66/八、67）
- 截止测试机制 → `useCycleCutoff`（I2/I6 共用基座）+ `cutoffCanonical` 收敛记录

## 未核实项

- 各科目 sheet ↔ Tab 精确映射未逐一读主入口 `v-if` 分发链；本文按子目录分组描述
- I3/I4/I5 的 `shared/` 目录具体内容与复用边界未逐一读取
- I6 与 K9 共用 6602 的**实际回写行为**（是否两者都回写、有无互斥保护）未逐一读代码确认，
  本文按"共码风险"陈述，见 `concern.md` §1
- I2 是否仍有缺 `/api` 前缀的保存路径残留未在本轮 grep 确认
