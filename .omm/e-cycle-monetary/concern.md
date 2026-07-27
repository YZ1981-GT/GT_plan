# 关注点 / 已知脆弱处（E1）

## 1. "审定合计 ≠ TB 数"类假差异有三层历史根因

- **camelCase / snake_case 键名不匹配**：前端读 `projectContext` 而 render 输出 `project_context` → 整个 seeding 块静默跳过 → TB 锚点从不 seed → 差异 = 全额审定合计
- **期初 TB 从不 seed**：早期只 seed `-ending`；`trial_balance` 无期初列 → 改为后端从四表 prefill 叶子 opening 合计出期初
- **聚合键陈旧 0**：明细行有数据但聚合键被早期竞态写成 '0' → 审定合计漏该项（差异恰等于该项金额）

现在的做法：审定表从持久化明细行权威重算聚合，仅当聚合陈旧 0/空而行合计非 0 时纠正。

## 2. 顶部全局告警容易误报

`globalAlerts` 若读 `E1-adj-total-{code}`（只有审定表 `writebackTrialBalance` 才写），
在审定表未编辑时恒为 0 → 顶部黄条误报"审定合计 0.00 ≠ TB 数"。
正确做法：从**跨 sheet 未审聚合键 + 账项调整实时算**（与 writeback 归组一致：1001=现金、1002=银行本金、1012=其他+数字货币），
writeback 键非 0 时优先。同理 `E1-adj-total-*` 需随 detailRows immediate watch 同步到共享 `allResponses`，
不能只在 `writebackTrialBalance` 里写（该函数常常没被调用）。

## 3. 存量 / 流量不要强行做等式勾稽

E1-20 是**期末应计利息存量**，E1-15 是**全年利息收入流量**，维度不同；早期做过等式告警属误报，已删除。
E1 审定合计与现金流量表"期末现金及现金等价物"之间只给 info 级提示（差额 = 受限资金 + 非现金等价物存款），不做硬勾稽。

## 4. Element Plus 组件的两个坑（E1 踩过）

- `el-segmented` 的 `:options` 传 ComputedRef 对象（composable 返回的普通对象里的嵌套 ref 模板**不自动解包**）→ 类型校验失败渲染成 `<!--v-if-->`，双模式切换从来不显示。必须显式 `.value` 或本地 computed 包装。
- `el-segmented` 选中态是**空 pill**（`.el-segmented__item-selected` 绝对定位无文字）+ 真文字（`.el-segmented__item.is-selected`）两层；测色/改色要针对后者的 label，测 pill 会取到空元素继承色误判。

## 5. 前端读 render 数据的类型是松散的

`htmlData` 无严格类型 → 键名写错不报错、只是静默 undefined（`project_context` 那次就是这样）。
改 render 契约时必须两端同时核对，并优先做 `props.htmlData?.project_context ?? projectContext` 双兜底。
