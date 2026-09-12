# Task 2 — F-SHELL outlet 可用性核实（入口前置闸）

**结论：F-SHELL outlet 契约已交付且可用 ⇒ Task 11 不 BLOCKED，可通过 compatibility outlet 注入刷新按钮。**

_同时更新本 spec 红基线 1：`GtWpToolbar.vue` 已不再是「只有 CSS 容器无 slot」。_

## F-SHELL 交付状态（实读前置 spec）

来源：`.kiro/specs/workpaper-page-formula-toolbar-closure/`

- tasks.md：Task 1–16 全部 `[x]`；仅 Task 17（localhost 登录态 Playwright 补验）未勾选，
  且其未勾原因是「无可用登录态、未 commit」，**不影响 outlet 契约本身的交付**。
- Task 13 已发布 `F-SHELL` contract，证据 `evidence/F-SHELL/{contract.json, envelope.json, INDEX.md}`。
- 契约模块 `frontend/src/shell/formula/fShellContract.ts` 存在，
  `FSHELL_CAPABILITIES` 含 `toolbarOutletArbiter`（本 spec 入口所需能力）。

## 红基线复核（已变化，需更新本 spec 设计）

本 spec requirements 写「`GtWpToolbar.vue` 只有 `.gt-wp-toolbar__right` CSS 容器，没有 Vue slot」。
**实读发现该基线已被前置 spec Task 5 推进：**

`frontend/src/components/workpaper/GtWpToolbar.vue`（实读）现有真实 named slot：
```
<span data-toolbar-outlet="page-capabilities-compatibility"
      data-testid="page-capabilities-compatibility">
  <slot name="page-capabilities-compatibility" />
</span>
```
位于 `.gt-wp-toolbar__right` 容器内。CSS class 仍只作样式，真实能力 = named slot + data 属性。

⇒ 红基线「无 slot」已过期。**新基线**：`GtWpToolbar` 有 `page-capabilities-compatibility` named slot，
本 spec 刷新入口消费该 slot，**仍禁止**在 `GtWpToolbar` 内新增第二个按钮 owner 或改 DOM（红基线 1 精神不变）。

## 注入 API 形态（Task 11 落地依据）

两个 named outlet（`frontend/src/shell/formula/outletSlots.ts` 实读）：
- `PRIMARY_OUTLET_SLOT = 'page-capabilities-primary'` — 紫色主工具栏（`ThreeColumnLayout`，AI 后/金额单位前）
- `COMPATIBILITY_OUTLET_SLOT = 'page-capabilities-compatibility'` — 底稿工具栏 `GtWpToolbar.__right`

Arbiter（`toolbarOutletArbiter.ts` 实读）：primary 优先，compatibility 仅在 primary 显式不可用时选中；
跨 epoch / 重复 kind / 多 primary ⇒ collision（不静默覆盖）。注册 API：
`arbiter.beginCycle(epoch)` → `arbiter.register({hostInstanceId, ownerEpoch, kind, outletElement, namedSlot})` → `arbiter.settle()`。

## 本 spec 的注入落点（对照 Requirement 4.4「导入右侧」）

实读 `frontend/src/components/workpaper/GtWpRenderer.vue`（所有底稿统一渲染宿主）：
- 它渲染 `GtWpToolbar`，`导入` 按钮在 `__left`；
- 已在 `#page-capabilities-compatibility` slot（`__right`）挂「公式管理」按钮：
  ```
  <template #page-capabilities-compatibility>
    <el-button :disabled="!runtimeProjectId || !runtimeWpCode || loading"
               @click="openPageFormulaManager">公式管理</el-button>
  </template>
  ```
- ⇒ 本 spec 刷新按钮注入**同一 slot**，紧邻「公式管理」，天然落在「导入（`__left`）右侧」的 `__right` 区，
  且复用既有 `:disabled` 只读/上下文门控约定。**这是 Requirement 4.1 + 4.4 的合法落点，无需改 `GtWpToolbar`。**

## 只读态门控约定

既有「公式管理」按钮 `:disabled="!runtimeProjectId || !runtimeWpCode || loading"`。
本 spec 刷新按钮除此之外，Requirement 4.4 要求「只读态禁用」⇒ 追加 `|| readonly`（`GtWpRenderer` 有 `readonly` prop）。
