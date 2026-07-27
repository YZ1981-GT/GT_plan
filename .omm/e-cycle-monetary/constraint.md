# 约束（改 E1 必须遵守）

## 取数与口径

- **叶子科目提取**：`tb_balance` 有多级子科目，四表取数必须 `_is_leaf` 过滤（父级不参与），否则父子双算；同时过滤全零空账户。
- **资产借方方向**：增加 = `debit_amount`，减少 = `credit_amount`，期末 = `closing_balance`。
- **TB 核对科目走 `report_config` 规则映射**（BS-002），不得硬编码 `1001%/1002%/1012%` 前缀；无配置时回退硬编码保零回归。
- **`trial_balance` 存标准码级**（1001/1002/1012，无子科目行）→ LIKE 前缀不双算；`tb_balance` 有多级 → 必须叶子提取。
- **审定表依赖的跨 sheet 聚合键可能陈旧**：明细 sheet 未挂载时聚合键可能是历史写入的 0 → 审定表须从持久化明细行**权威重算**（`reconcileCashAggregateFromRows`），不能只信独立持久化的聚合键。

## 前后端契约

- **render 输出的 `project_context` 是 snake_case**：前端必须读 `props.htmlData?.project_context`，写成 `projectContext`（camelCase）会静默 undefined、整块 seeding 被跳过。
- **四表种子 persist-first**：仅当 rows 键缺失才 seed，已有编制数据一律不覆盖；「🔄重新取数」才允许覆盖持久化。
- **surfaced 公式必须带 `sheet_codes`** 且给非 null 稳定 id（只读行 id 为 null 会让 `editingId === row.id` 恒真，渲染出空编辑框）。

## 展示

- 只读金额一律 `displayPrefs.fmtAmount()`；可编辑金额格用 `el-input` + `wpAmountInput` 的 formatter/parser（`el-input-number` 忽略 `:formatter`）。
- 金额列必须 `align="right"` 才命中全局防折行 CSS；超宽列按 13→12→11px 缩字号，仍不够才调列宽。
- 附注/报表呈现类默认单位 **元**（不是万元）。

## 来源模板

E1-23 收支检查是**凭证级 15 列**（方向/所属科目/日期/凭证编号/业务内容/对方科目/对方明细科目/金额/银行回单日期·对方·金额/其他支持性文件/索引号/是否异常/异常说明），
不是汇总 5 列；外币性质货币资金表按模板归属附注 **五、81**，不并入五、1。
改这些结构前必须对照致同源模板，禁止自造列头或披露内容。
