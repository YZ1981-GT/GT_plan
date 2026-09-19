# 说明

产出方式、字段约定、维护约定见 `.omm/d-cycle-sales/note.md`。

## 本 perspective 的事实来源

- 5 个 componentType + render 策略 → `backend/app/routers/wp_render_strategies/__init__.py`
  （`n1-deferred-tax-assets` / `n2-taxes-payable` / `n3-deferred-tax-liabilities` /
  `n4-taxes-and-surcharges` / `n5-income-tax-expense`）
- 前端目录 → `Get-ChildItem`（n1~n5）
- 科目码 → 各 `useN{n}FormData.ts` 的 `ACCOUNT_CODE` 常量（含注释标注方向/口径）：
  N1 1811 资产取期末余额 / N2 2221 负债 / N3 2901 负债 / N4 6403 损益取发生额 / N5 6801 损益取发生额
- 跨表 dead-key 修复 / render tb_balance 列名 / 类目发散 / 明细种子 / 带入 / N1 双期 / N5 有效税率调节表
  → N 循环大量既有复盘记录（memory）
- N1 附注 五、30 / 八、31（与 N3 共用节）→ n1-disclosure-note-linkage 记录

## 未核实项

- 各科目 sheet ↔ Tab 精确映射未逐一读主入口 `v-if` 分发链；本文按分组描述
- N2/N3/N5 的辅助 service 函数错列名/签名为既有记录（无 router 调用方，次要），本轮未重读后端
- N4 与 N2 车船税命名分歧的统一方案未定（本文陈述现状：模块内命名一致性优先，不单文件改名）
- N5-2 有效税率调节表重建为既有记录（需 spec），本轮未重读组件
- N2~N5 的附注结构化推送/跳转覆盖度未逐一核实（本文只确认 N1 已建 n1NoteSectionMap）
