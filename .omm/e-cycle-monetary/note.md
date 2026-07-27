# 说明

产出方式、字段约定、维护约定与 D 循环一致 → 见 `.omm/d-cycle-sales/note.md`。

## 本 perspective 的事实来源

- componentType `e1-monetary-fund` → `htmlRendererRegistry.ts`
- **sheet → Tab 组件映射**（E1-1…E1-23、variant 分派、IPO 族）→ 直接读 `GtE1MonetaryFund.vue` 的 `v-if` 分发链
- IPO/舞弊族具体表名（E1-26/29/30/31/32）→ 各 Tab 组件文件头部注释
- 四表取数 / TB 规则映射 / 聚合键重算 / 双模式封装 / 公式 surfacing → `_e1_monetary_fund.py`、`e1FourTablePrefill.ts`、`E1FourTableSourcePanel.vue`、`useWpDualMode.ts`、`wp_formula.py`（均为已落地实现）

标注"未核实"的（E1-27/E1-28、`E1TabIpoSpecial` 内部分发）请勿当既有事实引用。

## 与 D 循环文档的关系

E 循环不重复描述共享运行时（渲染边界、持久化工厂、账龄、抽凭、截止、集中调整、附注联动三件套、版本链、复核），
那些在 `.omm/d-cycle-sales/shared-runtime/`。本目录只写 E1 特有或 E1 首发的机制。
