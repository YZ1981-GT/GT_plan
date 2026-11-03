# 需求文档：S4　公式设置的持久化 outbox

> **本 spec 由 `formula-hub-integrity-closure` 按需求 17.5 创建（design §8.1 的 S 系列交接）。**
> 创建时只有本文件：它的作用是让「formula-hub-integrity-closure 没做、但已知必须做」的事有明确的负责范围与触发条件，
> 不在归档时丢失。实施前需补 design.md 与 tasks.md，并按三件套纪律先做「现状 grep 确认」
> —— 下面每条都是 `formula-hub-integrity-closure` 实施期的现读结论，**启动时必须重新现算**（memory 方法论铁律①②）。

## 1. 负责范围
- 定义写入与 outbox 同事务（现在发布成功但扇出失败会静默丢传播）。
- 幂等 worker。
- 扇出分批（大项目一次扇出会把事件循环占满）。
- 过期标记进发布事务（本 spec ADR-FHIC-04 已把报表域的标过期放进发布事务，其余域仍在提交后）。
- 对应阶段一评估的 P1-7 / P1-14 / P2-11。

## 2. 依赖与先后
独立；建议**在 S1 之前**做 —— S1 的全域 resolver 迁移会大量改写定义写入路径，先有 outbox 更安全。

## 3. 触发条件

出现「发布显示成功但其他项目没收到」的真实工单时立即启动。

## 4. 承接自 `formula-hub-integrity-closure` 的具体欠账
本 spec 任务 15 登记的「不经三个出口、同样改报表有效定义的写入方」（`template_sync` / `legacy_report.sync_project_to_global` / `apply_ops.apply_to_projects` / `project_ops.resolve_items`）仍只靠提交后传播标过期。

## 5. 不属于本 spec

- `formula-hub-integrity-closure` 已交付的部分不回填改写（历史档案 append-only）；本 spec 只做上面第 1 节列出的事。
- 决策项 X1~X5（共享库迁移与推送、存量归属行升级、真实项目报表重算、门禁切 enforce、D1~D15 默认值确认）
  属用户决定，不由本 spec 代为执行。

## 6. 设计阶段补充（2026-10-29）

- 已补 design.md / tasks.md。现状复核新发现：事件总线派发时吞掉处理器异常，`on_formula_config_changed` 自己也吞，只把「发事件」做成耐久不够，投递要直接调用传播处理器（design §1 第 2 行、ADR-SDO-02）。
- 复用平台已有的耐久事件表与重放 worker，不建第二套（design ADR-SDO-01）；发布循环分批先测量后决定（design ADR-SDO-07）。
