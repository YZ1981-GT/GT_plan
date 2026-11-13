# 需求文档：S1　公式语法与取数器单一来源

> **本 spec 由 `formula-hub-integrity-closure` 按需求 17.5 创建（design §8.1 的 S 系列交接）。**
> 创建时只有本文件：它的作用是让「formula-hub-integrity-closure 没做、但已知必须做」的事有明确的负责范围与触发条件，
> 不在归档时丢失。实施前需补 design.md 与 tasks.md，并按三件套纪律先做「现状 grep 确认」
> —— 下面每条都是 `formula-hub-integrity-closure` 实施期的现读结论，**启动时必须重新现算**（memory 方法论铁律①②）。

## 1. 负责范围
- 单一 registry 生成**前后端**函数表：现在前端另有 `PRIOR`、`%` 两处自带语法，与后端 `_REGISTRY` 不同源。
- 多余参数报错：现在只强制参数个数下限与 `IF` 的上限（ADR-FHIC-02 求值期口径），上限整体收严归本 spec。
- `value=None` 全量迁移：ADR-FHIC-01 明确否决了「失败时 value=None」—— 约 20 个 `Decimal` 运算调用方会崩，
  要先把这些调用方改成判 `ok`，再把 L1 的 `value` 改成 `None`。
- note / cell 求值器 float → Decimal。
- 底稿公式全轨读 effective 定义（含 S5 的旧保存路径）。
- 报表按依赖排序求值（现在是行次序 + 缺行报错，拓扑序归本 spec）。
- 收敛 `formula_wp_semantics.py` 登记的 `typed_eval_strictness` 差异维度：typed_eval 与严格轨缺数 `blocked`，
  而 `WPExecutor` 两参与默认调用缺数返回 0 —— 两种语义并存是本 spec 刻意登记的已知差异，统一归 S1。
- `formula-governance-coverage-closure` 承接项：L1 的「期间」与列名两处口径。

## 2. 依赖与先后
- 依赖 `formula-hub-integrity-closure` 的 ADR-01 / 02 / 03 / 06 / 18 / 19（失败语义所有者、参数个数表、叶子口径、
  WP 读取契约、「未审数」规范列、中央执行合同）已落地；
- 依赖 `acnr-foundation-defect-closure` 的目录与 `exact_identity` 落地（`wp_cell_reader._catalog_sheet_keys`
  在本 spec 落地时恒为 `not_found`，要等 ACNR 接 `exact_identity.sheet_of` 之后才有真实可接受键）。

## 3. 触发条件

ADR-FHIC-01 的「value=None 否决」要被推翻，或前端再出现一处自带语法时启动。

## 4. 承接自 `formula-hub-integrity-closure` 的具体欠账
- 本 spec `formula_wp_semantics.py` 登记的 4 个差异维度里，`typed_eval_strictness` 的 owner 写的就是本 spec（S1）；
- 本 spec 任务 8 的「未改 / 交后续」②：`REPORT` 缺行仍按 0（不在 ADR-01 清单）；③正则降级路径出错时 `value` 是部分结果；
  ④`cell_formula_evaluator` 除零仍为 0（底稿 Excel 语法域）；⑤`_REGISTRY.register(arity=…)` 的展示元数据未与 `ARITY` 统一。

## 5. 不属于本 spec

- `formula-hub-integrity-closure` 已交付的部分不回填改写（历史档案 append-only）；本 spec 只做上面第 1 节列出的事。
- 决策项 X1~X5（共享库迁移与推送、存量归属行升级、真实项目报表重算、门禁切 enforce、D1~D15 默认值确认）
  属用户决定，不由本 spec 代为执行。

## 6. 设计阶段补充（2026-10-29）

- 已补 design.md / tasks.md。现状复核见 design §1：参数个数表实有 4 份；`PRIOR` 是附注执行器的合法函数，函数目录须按求值器分域；PREV 的列名问题母 spec 已修，只剩 REPORT 的期间。
- §2 的依赖「等 ACNR 接 `exact_identity.sheet_of`」已过时：ACNR 有意让 `_catalog_sheet_keys` 保持 `not_found`，由 `acnr/wp_cell_target.py` 判身份后传入（design §1 第 11 行、ADR-FGR-07）。
- 「报表按依赖排序求值」建议移交 S9（design §5 D4）；其余待拍板见 design §5。
