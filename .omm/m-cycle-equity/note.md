# 说明

产出方式、字段约定、维护约定见 `.omm/d-cycle-sales/note.md`。

## 本 perspective 的事实来源

- 10 个 componentType + render 策略 → `backend/app/routers/wp_render_strategies/__init__.py`
  （`m1-dividends-payable` … `m10-other-equity-instruments`）
- 前端目录 → `Get-ChildItem`（m1~m10）
- 科目码 → 各 `useM{n}FormData.ts` 的 `ACCOUNT_CODE` 常量（含注释标注方向）：
  M1 2232 负债 / M2 4001 / M3 4002 备抵借方 / M4 4002 / M5 4101 / M6 4104 / M7 4201 /
  M8 4104 金融专属 / M9 4103 / M10 4003
- 明细表 full-data 键 / AI generateAiText / 双模式 useMxEntryDualMode / 科目名纠偏 / M3 增强
  → M 循环大量既有复盘记录（memory）

## 未核实项

- 两组同码（4002 / 4104）的**实际回写行为**未逐一读代码，按"共码风险"陈述
- 各科目 sheet ↔ Tab 精确映射未逐一读主入口 `v-if` 分发链；本文按分组描述
- M6 利润分配与本年利润结转的自动勾稽程度未逐一核实
- 附注章节号未在本轮逐一读 map 文件（本文未列 M 各科目附注章节号，权益类附注在所有者权益变动表相关节）
