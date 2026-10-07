# L2 / L3 / L4 孤儿孪生与 sheet 粒度折叠车道 — 需求

## 引言

**上游**：`l-cycle-sync-foundation-and-first-canary`（LC-1 ~ LC-26 共同裁决 + LF-P1 ~ LF-P48 + canary `L1-adj-*` 已闭环）+ L slice（`backend/data/workpaper_sync_l_cycle_manifest_slice.json`）+ 既存守卫 `backend/tests/workpaper_sync/test_task54_l_cycle_migration.py`。

**本 spec 的 entry 范围**（**3** 条，用 entry_id 全名）：
- `xlsx/gt-l2-interest-payable`（L2I，应付利息）
- `xlsx/gt-l3-long-term-loans`（L3L，长期借款）
- `xlsx/gt-l4-bonds-payable`（L4B，应付债券）

**切分依据**：slice 自身的 `capability_target_blocked_by`——这三条与 canary entry L1 同属 **含 BP-5、不含 BP-4 / BP-6** 的集合；其中 L4 额外含 **BP-8**（sheet 粒度折叠，全 L 域唯一）。**不是按科目相邻切的。**

🔴 **共同裁决只引用编号**：LC-1 ~ LC-26 的判据内容在 foundation 的 `design.md`，本 spec **不复述**。凡本 spec 出现 `LC-x`，即指该处裁决原文。

## 本 spec 的三条 entry 差异摘要（现算自 slice，供 Req 引用）

| entry | 载体 kind | `switch_is_redeemable` | sheets / dispatch / HTML 覆盖 / OO 兜底 | 额外 BP |
|---|---|---|---|---|
| `xlsx/gt-l2-interest-payable` | `shared_cycle_composable` | `true` | 8 / 8 / 8 / 0 | — |
| `xlsx/gt-l3-long-term-loans` | `none` | `null` | 14 / 13 / 13 / 1（`GT_Custom`） | — |
| `xlsx/gt-l4-bonds-payable` | `none` | `null` | 16 / 13 / **15** / 1（`GT_Custom`） | **BP-8** |

**算术自检**：HTML 覆盖 8 + 13 + 15 = 36；OO 兜底 0 + 1 + 1 = 2；sheets 8 + 14 + 16 = 38 = 36 + 2 ✓

## Requirement 1：三条 entry 的 BP 归位

**User Story:** 作为实施者，我需要这三条 entry 的阻塞项被逐条归位，这样我知道哪些能做完、哪些卡外部供给。

### 验收准则

1. WHEN 现算三条的 `capability_target_blocked_by` THEN 系统 SHALL 得到：L2 = BP-1/2/3/5/7/9（6 项）· L3 = BP-1/2/3/5/7/9（6 项）· L4 = BP-1/2/3/5/7/**8**/9（7 项），并断言三条均**不含** BP-4 / BP-6 / **BP-10**（BP-4 与 BP-6 只属 lane 3 的 L5~L8；BP-10 只属 foundation 的 L1）。
2. WHEN 处理 BP-1 / BP-2 / BP-3 THEN 本 spec SHALL 标 `[ ]*`，**不承诺完成**。
3. WHEN 处理 BP-9 THEN 系统 SHALL 引用 **LC-1**，不重新裁决。
4. WHEN 处理 BP-7 THEN 系统 SHALL 引用 **LC-14**；🔴 并须注意 L3 / L4 的 `ui_toolbar_gate.anchor` 为 `null`（宿主里没有模式切换工具条），故 notice 无既成锚点，须与 sync bridge 的编辑宿主一并落位。
5. WHEN 处理 BP-5 THEN 系统 SHALL 按 Requirement 2 收口。
6. WHEN 处理 BP-8 THEN 系统 SHALL 按 Requirement 4 收口，且范围**仅限 L4**。

## Requirement 2：BP-5 孤儿模块收口（含 L3 的双份与不分区）

**User Story:** 作为实施者，我需要这三条的孤儿 dual-mode 模块被安全删除，这样「orphan 不是无害」的风险被真正消除。

### 验收准则

1. WHEN 现算本 spec 三条的 orphan 孪生模块 THEN 系统 SHALL 定位：L2 → `components/workpaper/composables/useL2DualMode.ts` · L3 → **两份**（`src/composables/useL3DualMode.ts` 与 `components/workpaper/composables/useL3DualMode.ts`）· L4 → `components/workpaper/composables/useL4DualMode.ts`。
2. WHEN 断言 L3 的双份 THEN 系统 SHALL 说明成因是 LC-25 的 L1↔L3 同构复制（L1 侧对应模块在 `src/composables/`，L3 被连带复制了一份），🔴 **两份都要删**，只删一份即残留。
3. WHEN 判每个 orphan 的可删性 THEN 系统 SHALL 现算其生产消费边 == 0，并断言是一阶 orphan（barrel 不存在 ⇒ 二阶恒 0，引用 **LC-24** 第 5/6 项）。
4. WHEN 处理不分区的那一份 THEN 系统 SHALL 引用 **LC-18** 并断言 `components/workpaper/composables/useL3DualMode.ts` 用 `const STORAGE_KEY` 无 wpId 拼接 ⇒ 它一旦被接上会让所有底稿共享同一模式偏好（这是「orphan 不是无害」的实证，删除理由之一）。
5. WHEN 删除执行 THEN 系统 SHALL 遵守删旧代码铁律：删前 grep 0 调用方 · 删前后测试全绿 · 独立 commit。
6. WHEN 删除后核算 THEN 系统 SHALL 现算剩余 dual-mode 模块数与行数合计，并与删除前的现算值做差，断言差额等于被删模块的行数之和。

## Requirement 3：L2 的真库跨 entry 键污染清理

**User Story:** 作为实施者，我需要 L2 命名空间落在别的底稿上的数据被发现并治理，这样契约的 entry 归属才是真的。

### 验收准则

1. WHEN 查真库 THEN 系统 SHALL 引用 **LC-22** 的判据形态：断言「任一 `item_id ~ '^L{n}-'` 的行，其 `wp_id` 对应的 `wp_code` 必以 `L{n}` 开头」。
2. WHEN 现存违例被发现 THEN 系统 SHALL 逐行登记（`item_id` / 实际 `wp_code` / 项目 / 载荷长度），并断言现算违例数与 `design.md` 等值。
3. WHEN 判违例成因 THEN 系统 SHALL 在两个候选之间给出证据：① 测试数据残留；② `wp_id` 解析错。🔴 未取得证据前**不得断言成因**，只登记现象。
4. WHEN 本 spec 处理数据 THEN 它 SHALL **只加守卫不动生产数据**；清理动作 SHALL 单列为 `[ ]*`（需业务确认该行是否有效底稿数据）。
5. WHEN 守卫落地 THEN 它 SHALL 覆盖 8 条 entry 全集（不只 L2），防同类复发。

## Requirement 4：L4 sheet 粒度折叠（BP-8）

**User Story:** 作为实施者，我需要 L4 的两对同码 sheet 在契约层被区分开，这样字段映射不会两张表共用一套。

### 验收准则

1. WHEN 现算 L4 的 dispatch 折叠 THEN 系统 SHALL 断言 16 张权威 sheet → 13 个 dispatch code，且重复码集合恰为两个（后续计量 / 账面核对各一对）。
2. WHEN 逐字确认两对 sheet 名 THEN 系统 SHALL 断言四张 sheet 名逐字不同，且其中一张带**内部空格**（引用 **LC-10**）。
3. WHEN 判 router 层危害 THEN 系统 SHALL 引用 **LC-10** 并现算断言：两张账面核对表**同时** `endswith` 同一尾码 ⇒ 解析器取第一个。
4. WHEN 断言 router 歧义码 THEN 系统 SHALL **两个数都断言**：歧义码总数，与**真正可达**的歧义码数（后者远小于前者，其余是裸循环码）。🔴 只断言一个数即口径不全。
5. WHEN contract 层设计 THEN `sheet_key` SHALL 用**能区分两对 sheet 的稳定标识**（不能用尾码），并在契约里登记「同码不同表」的映射关系。
6. WHEN 前端层评估 THEN 系统 SHALL 现算确认页内分支选择器（`bondBranch`）是**当前唯一**的区分手段，并引用 **LC-15** 断言它**不是**模式开关。
7. WHEN 本 spec 收口 BP-8 THEN 它 SHALL 交付契约层的区分方案 + 守卫；🔴 **模板改名不在范围内**（改名会打断既有 render schema 与 prefill，须另立 spec）。

## Requirement 5：L3 侧的同构对收口（LC-25）

**User Story:** 作为实施者，我需要 L3 的同构缺陷与 L1 侧同步修复，这样不会只修一半。

### 验收准则

1. WHEN 本 spec 处理 L3 的 `#REF!` 死公式 THEN 系统 SHALL 引用 **LC-11 / LC-25**，断言 `逾期贷款检查表L3-7` 的 4 处与 `逾期贷款检查表L1-7` 的 4 处**同源同形**。
2. WHEN 修复动作被定义 THEN 它 SHALL 与 foundation 的对应 task **交叉引用**；🔴 改一不改二 = 半修。
3. WHEN 现算 L3 的 definedName 污染 THEN 系统 SHALL 断言 L3 册有污染且与 L6 / L7 的 broken 数相同（引用 **LC-9**），并确认 L1 册为 0 ⇒ 污染不是从 L1 复制来的，而是 L3 另有来源。
4. WHEN 处理 L3 的 OCR THEN 系统 SHALL 引用 **LC-19** 断言 `L3TabContractCheck.vue` 与 L1 侧同借 D4 端点、同按 `$index` 传行。
5. WHEN 处理 L3 的 `removeRow(originalIndex)` THEN 系统 SHALL 引用 **LC-7** 并与 L1 侧的同名签名一并登记。

## Requirement 6：本 spec 的位置化范围

**User Story:** 作为实施者，我需要位置化收口的范围在三份 spec 之间不重不漏。

### 验收准则

1. WHEN 本 spec 收口位置化 THEN 范围 SHALL 限于本 spec 三条 entry 名下的命中：L4 的 `L4-3-row-${n}-data`（`L4TabFinLiabOther.vue`）+ L3 的 `rowId` 生成模块（`useL3VoucherCheck`，属**已安全**的一侧，只登记不改）+ L2 的两个 rowId 生成模块（同为已安全侧）。
2. WHEN 断言「已安全侧」THEN 系统 SHALL 引用 **LC-6** 的交叉验证结论：L2 / L3 的三个动态行表模块**正是**全 L 域唯一能按行身份删的模块 ⇒ 它们是正面样板，其 rowId 生成形态 SHALL 被抽为其余 entry 的参考实现。
3. WHEN 断言三个模块的 rowId 前缀 THEN 系统 SHALL 现算并断言**两两不同**（防跨表串档）。
4. WHEN L6 / L7 的位置化命中被提及 THEN 本 spec SHALL 声明它们归 lane 3，**不在本 spec 范围**。

## Requirement 7：空分母与结构性零

### 验收准则

1. WHEN 本 spec 的任一 Property 分母为空 THEN 它 SHALL 标「不宣称通过」并指明承载者。
2. WHEN 引用结构性零 THEN 系统 SHALL 引用 **LC-24**，不重复列十项。
3. WHEN L2 的真库载荷被用于闭环 THEN 系统 SHALL 如实说明其唯一非空载荷是违例数据 ⇒ **L2 的闭环验证须标 `[ ]*`**（待造合规数据）。
