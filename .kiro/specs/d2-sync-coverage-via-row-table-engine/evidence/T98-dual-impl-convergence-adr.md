# ADR · D 循环受管 sheet 声明的双实现收敛（2026-09-26）

**背景**：本 spec 执行期间（work 分支 `work/2026-09-14-d4-dual-mode-p0-fixes`），并发会话提交了
2 个 commit（`fbb55eead` 行表引擎框架层 + `f1ec1c67d` AdjudicationSheetSpec + D1 声明层），实施了
D2 spec 原设计假设的抽象层类。结果 D 循环出现两套受管 sheet 声明范式并存。

## 一、两套范式的实测现状

| 范式 | 载体 | 谁在用 | 是否真接入父契约 |
|---|---|---|---|
| **A. 抽象层类** | `phase5_row_table_sheet.RowTableSheetSpec` / `phase5_adjudication_sheet.AdjudicationSheetSpec` | D1 扩容（`phase5_d1_04_bad_debt.py` 等）声明 `SPEC_D104_*` | 🔴 **否** —— `phase5_d1_notes_receivable.build_contract_payload` 未 import 任何扩容模块 / 抽象层类；D1 扩容目前是孤立声明 |
| **B. per-sheet 模块** | `phase5_d2_03_bad_debt.py` / `phase5_d2_01_adjudication.py`（模块级 `Final` 常量 + `sheet_payload_*` 函数） | D2-3 / D2-1 | ✅ **是** —— 已进 `pilot_d2_large_json.build_contract_payload` 的 sheets[]，`parse_contract` 强校验通过，磁盘契约双向锁死 |

实测结论：**抽象层类目前是「框架件 + 孤立声明」，尚无任何生产 entry 真正靠它接入并跑通
parse_contract**。范式 B（per-sheet）是 D 循环当前唯一真接入父契约的路径（D4 全系 + D2 全用它）。

## 二、裁决：D2 保持范式 B（per-sheet 模块），不迁抽象层类

依据三条：

1. **D4 全系（30+ 受管 sheet）已用范式 B 且真接入跑通**。D2 照 D4 落地是本 spec 的用户明确
   要求（「基于 D4 中的底稿及功能」）。迁到范式 A 等于把 D2 从「已跑通」退回「与 D1 一样孤立」。
2. **抽象层类尚未证明能真接入**。范式 A 连 D1 自己都没接进主契约，把 D2 迁过去是拿已跑通的
   换未验证的 —— 违背「不把已跑通的换成未验证的」原则。
3. **两范式产出的契约 payload 同构**（都是 `sheets[].tables[].fields[]` 的 canonical JSON，
   经同一个 `parse_contract` 校验）。差异只在**声明层的组织方式**（数据类实例 vs 模块级常量），
   不影响契约字节、不影响 materialize/merge。故「双实现」不是运行时分叉，只是声明风格分叉。

## 三、收敛方向（登记，不在本 spec 做）

真正的收敛应在**抽象层类被证明能真接入生产**之后，由 D1 spec（抽象层的 owner）统一：

1. D1 spec 先让 `RowTableSheetSpec`/`AdjudicationSheetSpec` 真接入 `phase5_d1_notes_receivable`
   的 `build_contract_payload`（当前缺口），跑通 parse_contract + 磁盘锁 + 真栈。
2. 证明后，若范式 A 确实更优（消除模块级常量样板），再评估把 D4/D2 的 per-sheet 模块**逐张**
   迁到抽象层类 —— 但每张迁移都必须保持契约 golden digest 逐字节不变（否则是行为漂移）。
3. 在此之前，D 循环**声明层双范式并存是可接受的既有状态**，因为二者契约同构、无运行时分叉。

## 四、本 spec 的处置

- D2-3 / D2-1 保持 per-sheet 模块（范式 B），已真接入父契约（受管区 1→4）。
- 不引入范式 A 到 D2（避免拿已跑通换未验证）。
- 本 ADR 登记双实现现状 + 收敛前提（抽象层先证明可接入），供 D1 spec owner 后续收敛参考。

⚠️ **反模式警示**：若将来有会话看到「D1 用抽象层、D2 用 per-sheet」就想「统一到抽象层」而直接
迁 D2，必须先确认抽象层已真接入生产并跑通真栈 —— 否则会把 D2 从可用退回孤立（本 ADR 第二条）。
