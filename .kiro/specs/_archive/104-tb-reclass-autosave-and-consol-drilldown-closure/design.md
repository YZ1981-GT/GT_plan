# 设计：TB 重分类自动保存与合并汇总穿透收口

## 1 现状与根因

- `TrialBalance.vue` 的 `rcl_dr/rcl_cr` 格提交只调用 `recalcTbSummaryAudited()`；`saveTbSummary()` 才整表 PUT。旧保存不读版本，且 `validateStatus: s < 600` 会把 403/409/423/500 当成功。
- 合并页右键已写入真实行，但 `openCellDrillDown()` 随即改成“请在报表中选择科目”；加载函数因此提前返回。它还用 `selectedCells[0]` 重找行、报表不传节点、`Number(value) || null` 吞掉 0。
- 后端已有工作表整数 CAS 与 `POST /api/report-config/drill-down` 的 direct / leaf 企业树贡献，无需后端改动。

## 2 决策

### ADR-1 页面业务层自动保存

不改 `GtGridCell/GridKernel`。适配器已把所有最终编辑动作归一为 `change`，TrialBalance 只在 `rcl_dr/rcl_cr` 的 `change` 上标记手工格并排保存；禁止用 deep watch 触发写入。

### ADR-2 200ms 合批、单飞 CAS

新增 `useTbSummaryPersistence.ts`。待保存任务冻结 `context + rowsSnapshot + revision`；同上下文 200ms 内后任务替换前任务，飞行中任务进入下一批。版本由加载结果 prime，首次表为 0；每次成功采用响应版本。失败保留 dirty，409 阻断盲重试，显式保存可重试但仍带 CAS。

持久化行新增 `manual_rcl_dr/manual_rcl_cr`。只有用户提交过的格为 true；加载时这类格强制采用存值（含 null/0），未标格继续读已审批 RJE。旧行无标记时沿用“计算值为空才回填”的兼容规则。

### ADR-3 显式与自动保存同队列

`saveTbSummary()` 强制提交当前快照并 await 同一 flush；成功后提示并退出编辑。自动保存只更新轻量状态。加载失败不 prime 版本，保存 fail-closed。

### ADR-4 汇总穿透目标快照

新增纯函数 `consolDrillTarget.ts`，构造：

```ts
{ source, rowCode, reportType, nodeKey, period, itemName, colName, totalValue, accountCode? }
```

TB 从事件行取 `row_code/consolidated`、子组件 `reportType/nodeKey`；报表从本次单元格取 `row_code/current|prior`、`consolReportType/currentEntityNodeKey`。加载只使用快照，不读选区或活动 Tab。请求序号同时保护 direct / leaf 与 ACNR 跳转；上下文变化统一 reset。上期目标打开弹窗并显示限制说明，不发 POST。

## 3 文件

- 新建 `views/composables/useTbSummaryPersistence.ts` 及单测。
- 修改 `views/TrialBalance.vue`：格提交、版本加载、手工标记、自动保存状态、显式保存共用队列。
- 新建 `components/consolidation/composables/consolDrillTarget.ts` 及单测。
- 修改 `views/ConsolidationIndex.vue` 与 `ConsolidationIndex.grid.spec.ts`：目标建立、请求快照、陈旧响应、上下文清理。
- 后端与数据库不改；相关后端穿透 / CAS测试作为回归。

## 4 错误与生命周期

- 无权、归档、加载失败、未知版本：不发自动 PUT，保留本地输入并显示中文失败状态。
- 网络结果不确定：保留 dirty；重试仍用原 expected version，若服务器已提交则转成 409，不覆盖。
- 409：保留输入并提示重新加载；绝不降级为无版本 PUT。
- 组件卸载只清 timer / 使响应失效，不在卸载期启动新写入；页面上下文切换前已有批次按冻结旧 key 完成。

## 5 验证

- 纯函数 / composable 行为测试优先，页面测试钉接线，不用只检查“源码出现过赋值”的弱断言。
- 磁盘变异逐条删除：提交触发、CAS 版本更新、单飞循环、手工标记、目标 rowCode/nodeKey、上期门和请求序号，均须红在对应断言。
- 浏览器核对网络 payload 与刷新回读；测试项目变更前保存原 JSON，验收后经同端点 CAS 恢复。

## 6 实施结果与复盘

- 实现与 ADR-1~4 一致。浏览器验收额外确认：`shortcut:save` 的消费者虽存在，但 `registerDefaultShortcuts` 全仓没有调用，真实 Ctrl+S 不会发事件。为避免启用整套全局快捷键扩大影响，只在 TrialBalance 本页兜住 Ctrl+S；先 `commitAllGridEdits()`，再调用同一 `onShortcutSave()`。若以后全局层先处理，`defaultPrevented` 会阻止重复保存。
- 前端相关回归分组 219 passed，后端穿透 2 passed；定向 ESLint 0 error。40GB 单区域 vue-tsc 与同一基线逐项比较，本轮新增错误 0。
- 17 组磁盘变异覆盖提交入口、CAS 推进、单飞、逐格标记、0/null、generation、rowCode/nodeKey、上期门、主响应陈旧保护、Ctrl+S 格内提交、刷新失败保留本地输入、行集上下文绑定、旧 detached RCL、确认丢弃和路由更新重载。rowCode 与主响应陈旧检查首轮各存活一次，补成逐字段 / 精确顺序断言后复注入均打红。
- 【测试】单体项目自动保存后刷新回读 123.45，Ctrl+S 使 CAS 版本 0→1 并退出编辑；语义审查修正后复验 Enter 提交后立即点击路由，离页门先落库 77.77；【测试】集团 TB 与报表 BS-002 direct / leaf 合计均为 700，BS-003 真零仍请求并返回 0.00，上期无 POST。两轮验收产生的工作表行均已删除，恢复到验收前 0 行。

### 提交前语义审查修正

语义审查在首轮候选中确认四条边界：上下文往返可把旧行集配上缓存版本、卸载会清掉 200ms pending、旧 `formula_detached` 行的 RCL 兼容退化、409 后刷新入口与 dirty 状态互锁。最终实现增加“已加载行集 key”写入门、路由离开 / 更新与浏览器关闭守卫、旧 detached RCL 一次性迁移为逐格标记，以及“保存失败后仅经用户确认才丢弃并重载新版本”；对应测试和磁盘变异均已补齐。
