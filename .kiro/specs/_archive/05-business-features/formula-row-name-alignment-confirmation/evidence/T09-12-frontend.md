# Task 9/10/11/12 — 前端（弹窗 / 行内标识 / 入口注入 / 全局告警）

产物：
- `frontend/src/components/formula/GtRowNameAlignmentDialog.vue`（Task 9 对齐确认弹窗）
- `frontend/src/components/formula/GtRowNameAlignmentTag.vue`（Task 10 行内标识 + 溯源 + 直达）
- `frontend/src/components/workpaper/GtWpRenderer.vue`（Task 11 刷新入口注入 + 挂弹窗 + 事件链）
- `frontend/src/components/formula/GtRefreshScopeDialog.vue`（Task 12 全局告警展示 + DEC-4 隔离）
- `frontend/src/utils/eventBus.ts`（新增 open-row-name-alignment / row-name-alignment:confirmed 事件 + wire 类型）
- 守卫 `frontend/src/components/formula/__tests__/GtRowNameAlignmentDialog.spec.ts`（6 passed）
- 既有 `GtRefreshScopeDialog.spec.ts` 11 passed（我的改动零回归）

## Task 9：对齐确认弹窗

- 两栏：左底稿行名（状态 tag：自动匹配/待确认多候选/未匹配/已确认）+ 右候选账套明细名（金额 fmtAmount + 相似度% + 多对一标识）
- 支持 1:N / N:1 / N:M：每行独立 selection Map（row_key → dimension_key → TargetIdentity）
- 多对一（同一 dimension_key 被多行选中）→ `multiToOneRows` 非空 → 确认前 `ElMessageBox.confirm` 口径二次确认（Requirement 2.4）
- 确认调 `POST /{wpId}/row-name-mapping/confirm`，rows 带 `base_mapping_version`（来自行 wire 的 mapping_version，供版本冲突检测）；409 冲突有专门文案
- 取消**零写入**：`@closed` 只清本地草稿，不发任何 http.post（Property 4，守卫 `test 取消零写入`）
- 🔴 fmtAmount 走 `inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()`（来源 `@/composables/displayPrefsKey`，非 stores；平台已登记的整页崩溃形态已规避）
- 不复制 GtRefreshScopeDialog 的 scope 树（红基线 2）

## Task 10：行内标识 + 溯源 + 直达

`GtRowNameAlignmentTag.vue`（可复用行内组件，子组件在取数行放它）：
- unmatched → 红 tag「未匹配·去对齐」+ 点击 emit `open-row-name-alignment` 直达（禁止静默 0）
- ambiguous → 橙 tag「待确认·多候选」+ 点击直达
- user_confirmed → 绿 tag + hover popover 溯源（映射到哪些 aux_name/aux_type、confirmed_by、confirmed_at、version）+「重新确认」入口
- auto_matched → 轻量 info tag

## Task 11：刷新入口注入（消费 F-SHELL compatibility outlet）

- 在 `GtWpRenderer` 的 `#page-capabilities-compatibility` slot（F-SHELL outlet，`GtWpToolbar.__right`，「导入」在 `__left` 右侧）加「刷新取数」按钮
- `:disabled="!runtimeProjectId || !runtimeWpCode || loading || readonly"`（只读态禁用，Requirement 4.4）
- **未改 GtWpToolbar，未新增按钮 owner，未改 DOM**（红基线 1）
- 点击 `onRowNameAlignmentRefresh`：从子组件 `getRowNameAlignmentRows()` 收集行 → 调 `/row-name-alignment` → `has_pending` 则 emit 打开弹窗，否则提示已全部匹配并 reload
- 确认后 `row-name-alignment:confirmed` 事件 → 宿主 reload 重算

### 🔴 子组件契约（逐底稿接线点）
入口依赖子组件 `defineExpose({ getRowNameAlignmentRows() })` → `[{row_key, row_label, account_prefixes}]`。
这是本 spec 定义的新契约；具体底稿子组件的接线属逐底稿增强，Task 14 真栈实测验证样板底稿。
未暴露的子组件点击「刷新取数」得到「当前底稿暂不支持按行名对齐刷新」提示（诚实降级，不伪造）。

## Task 12：全局一键刷新汇总告警（DEC-4）

- `GtRefreshScopeDialog` 遇「行名未匹配」类 warning → 单独黄色告警条「N 项底稿存在行名未匹配，需到对应底稿逐行确认」+ 导向提示（不弹行级弹窗）
- warnings 分离：`rowNamePendingWarnings`（含标记 `行名未匹配`/`row_name_pending`/`名称未对齐`/`待确认行名`）vs `otherWarnings`
- **DEC-4 隔离守卫**（源码断言）：`GtRefreshScopeDialog.vue` 不引用 `GtRowNameAlignmentDialog`、不 emit `open-row-name-alignment`（不误挂第二触发点）
- 后端全局刷新产出待确认告警字符串属既有 draft-refresh 编排的增强（本 spec 不改其取数口径），前端展示能力已就绪

## 守卫覆盖（6 passed + 隔离 2）

- eventBus 打开弹窗渲染
- 多对一检测 multiToOneRows
- 确认调端点 + base_mapping_version 携带 + target dimension_key
- 取消零写入
- DEC-4：全局弹窗不引用行级弹窗 / 不 emit 触发事件
