# Task 3 — 缺刷新入口的底稿清册（禁 grep 按钮文字）

**判据：结构性（registry 条目 + 宿主存在 + slot 有消费方），非按钮文案字符串、非写死页面数量。**

## 入口宿主的结构性事实

实读 `frontend/src/components/workpaper/GtWpRenderer.vue`：
- 它是**所有 HTML/grid/onlyoffice 底稿的统一渲染宿主**（按 `componentType` 分发到
  `htmlRendererRegistry` 的组件 / GtGridSheet / GtOnlyOfficeSheet）。
- 它渲染 `GtWpToolbar` 的条件是 `componentType !== 'a1-dashboard'` ⇒
  **除 a1-dashboard 外的每一个渲染底稿都会挂 `GtWpToolbar`**。
- `GtWpToolbar` 的 `#page-capabilities-compatibility` named slot（F-SHELL compatibility outlet）
  已被 `GtWpRenderer` 消费（现放「公式管理」按钮）。

⇒ **入口覆盖是结构性全覆盖**：本 spec 刷新按钮注入同一 slot 后，所有走 `GtWpRenderer`
的底稿都获得刷新入口，无需逐 wp_code 加按钮。这天然满足 Requirement 4.3
「清单从真实 renderer registry / 已挂载宿主推导」。

## 「有四表取数能力」的宿主集（结构性推导）

判据 = 后端 render 策略是否消费 `app.services.four_table.*`（`select_leaves` /
`aggregate_aux_by_name` / `fetch_tb_subtree` / `resolve_leaf_totals` 等）。
实测 grep（符号引用，非按钮文字）命中的取数消费循环：

- D 循环（d_cycle_extraction）：D1 应收票据 / D3~D7 等
- E 循环：E1 银行账户（`e1_bank_accounts` / aux 逐户）
- F 循环：F1 预付（aux 归集）/ F2 存货 / F3~F5 分类披露
- G 循环：G1~G7（投资/利息/减值分桶）
- H 循环：H0~H10 审定表 prefill
- I 循环：I1~I4 资产类
- J 循环：应付职工薪酬等（负债）
- K 循环：K1 其他应收款款项性质
- L 循环：L0~L8 长期借款/应付债券
- M / N 循环：权益 / 专项

这些循环的**审定表（X-1）与附注披露表**是「按行名取数」的重灾区（模板固定行名 vs
账套自命名明细），即本 spec 名称对齐层的目标场景。

## 现有「取数刷新」链（Task 8 扩展点，非新建）

实读 `GtWpRenderer.vue`：
- 子组件 `@formula-saved="reload"`：公式保存后整体 reload render-config（重取数）。
- `openPageFormulaManager()` → `eventBus.emit('open-formula-manager', {...})`：打开公式管理中心。
- 无「独立的取数刷新按钮」——刷新目前隐含在「公式保存后 reload」与公式管理中心内。

⇒ 本 spec 的「刷新」入口是**补齐**：显式触发「按当前映射重新取数并回传每行 match_state」，
Task 8 扩展既有取数/刷新响应逐行带 `match_state`，Task 11 在 compatibility slot 加显式刷新按钮。

## 清册三列（wp_code → 宿主 → 现有入口）

| 宿主类别 | 渲染宿主 | 现有刷新入口 |
|---|---|---|
| 全部非 a1-dashboard HTML/grid/oo 底稿 | `GtWpRenderer` + `GtWpToolbar` | 无独立刷新按钮（仅公式保存后 reload + 公式管理中心）→ **本 spec 补齐** |
| a1-dashboard | 自管工具栏（`componentType === 'a1-dashboard'` 跳过 GtWpToolbar） | 不适用（非取数底稿） |

结论：**缺独立刷新入口的宿主 = 全部经 `GtWpRenderer` 渲染的取数底稿**；
补齐方式 = 单点注入 compatibility slot，覆盖全量，非逐页写死。
