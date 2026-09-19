# 说明

产出方式、字段约定、维护约定见 `.omm/d-cycle-sales/note.md`。

## 本 perspective 的事实来源

- 13 个 componentType + render 策略 → `backend/app/routers/wp_render_strategies/__init__.py`
  （`k1-other-receivables` … `k13-non-operating-expense`）
- 前端目录 → `Get-ChildItem`（k1~k13 + 共享 `kit/`）
- 科目码 → 各 `useK{n}FormData.ts` 顶部常量（K1 1221+1231 / K2 1231 / K3 2241 / K4 2245 / K5 2701 /
  K6 1481+2605 / K7 2401 / K8 6601 / K9 6602 / K10 6117 / K11 6701 / K12 6301 / K13 6711）
- K1 附注章节 `k1NoteSectionMap.K1_NOTE_SECTION`（五、8 / 八、9）+ `K1_ACCOUNT_CODE='1221'`
- 凭证检查复用 `useK1VoucherCheck`、截止测试 `useK8Cutoff`/`useK9Cutoff`、序时账取数 `expenseLedgerMonthlyPull`、
  减值 18 类 `useK11Adjudication`、带入 `useAdjudicationBringIn` → 各自既有复盘记录
- 双模式 / AI / 附注死链 / 目录 E1 标准 / persistence 四连环 → K 循环大量既有复盘记录（memory）

## 未核实项

- 三组同码（1231 / 2701 / 6602）的**实际回写行为**（是否两者都回写、有无互斥保护）未逐一读代码，
  按"共码风险"陈述（见 `concern.md` §1）
- K1 坏账进 K11 还是 G14 的报表口径未核（本文按历史"进 K11"陈述）
- 各科目 sheet ↔ Tab 精确映射未逐一读主入口 `v-if` 分发链；本文按分组描述
- K5/K6/K7 专项检查表的源模板对齐完成度部分沿用既有复盘记录，未逐一重读组件
