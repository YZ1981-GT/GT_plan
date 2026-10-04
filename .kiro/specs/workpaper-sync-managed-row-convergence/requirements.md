# Requirements — 受管行双向收敛（刷新取数来源可选 + materialize 行收敛）

## 背景与触发

D4 entry（`xlsx/gt-d4-operating-revenue`）点「在线编辑」恒 500
（`roundtrip_projection_mismatch`），**整个 entry 的在线编辑不可用**。

第八轮实测把根因挖到底（完整证据见 `docs/operations/d4-bidirectional-writeback-inventory.md`
第八轮 ①~⑦）：

- `extra` = **402 字段 / 73 身份**（口径自证 `common=909`、`missing=0`）
- 主因**不是**测试污染（L2MARK 只占 6 字段 / 1.5%），而是：
  **行身份每次重建都重新 mint** ⇒ substrate 累积同一份业务数据的 **3 个副本**
  （`d4r-mtl69x8j-*` / `d4r-muclbqzb-*` / `d4r-muks1021-*`，内容逐字相同）
  ⇒ 叠加 **materialize 只插不删** ⇒ 孤儿只增不减

### 这是一个两难，两条现存路都不通

commit `e52e5e5ce`（2026-09-28 13:39）把 overlay 的 `row_keys` 合并规则从并集改为
「store 声明的 table 以 store 为权威」，用来阻止「materialize 写 33 行进只有 12 行数据区的
模板」的写爆事故（其注释记录的 `7→33` 与本轮独立实测逐值吻合）。结果：

| overlay 规则 | 后果 |
|---|---|
| 并集（改前） | 旧行被带回 intended ⇒ 写 33 行进 12 行数据区 ⇒ **写爆 / 旧数据残留** |
| store 权威（改后） | 旧行不在 intended ⇒ extract 仍读得到 ⇒ `extra` 402 ⇒ **materialize 恒 500** |

⇒ 缺的是**第三件事**：让两侧行集能真正收敛。而收敛有两个方向，平台目前**两个都缺入口**：

| 方向 | 现状 | 缺什么 |
|---|---|---|
| store → substrate | `materialize` 有，但**只插不删** | 收缩受管区到 store 行集的能力（`build_delete_plan` 已建但**生产零消费方**） |
| substrate → store | 能力在投影层，但入口**全锁在 room 内**（`forcesave` / `onlyoffice-callback` / `recovery-cases` 都要 `room_id`） | 一个不依赖 room 的入口；而 room 由 materialize 创建 ⇒ **死锁** |

### 本 spec 的两个优先级

- **P0（解阻，零引擎改动）**：把现有「刷新取数」按钮扩展成**可选取数来源**，
  新增「以在线编辑（OO）侧内容为准，覆盖表单」这一来源。
  它让 store 认领 substrate 现有行集 ⇒ `intended ⊇ extracted` ⇒ `extra = 0` ⇒ 解阻，
  且**不删任何数据**（多余行显示在 HTML 侧，由审计师判断后手工删）。
- **P1（根治）**：给 materialize 接上行收敛（`build_delete_plan` / `resolve_deleted_row_keys`），
  与 overlay 的取舍规则形成严格对偶。

---

## Requirement 1：刷新取数必须让用户显式选择数据来源

**User Story**：作为审计助理，当表单与在线编辑两侧数据不一致时，我要能明确指定「以哪一侧为准」
来刷新，而不是由系统隐式决定，也不必先能打开在线编辑。

### 现状（已现读确认，不是推测）

`GtWpRenderer.vue` L147 的「刷新取数」按钮绑定 `onRowNameAlignmentRefresh`，
它 `POST /api/workpapers/{wpId}/row-name-alignment` 后 `reload()` ——
方向是**上游科目数据 → store**，既不读 substrate 也不读 OO。
L154「批量刷新」（`BatchRefreshDialog`）是同一动作的多底稿批量版。
⇒ 两者都**无法**消除 `extra`，因为它们只改 store 内字段的值，不改行集。

### Acceptance Criteria

1. WHEN 用户点「刷新取数」 THEN 系统 SHALL 弹出来源选择弹窗，而不是直接执行取数
2. 弹窗 SHALL 至少提供三个来源，每项附一句人话说明其影响范围：
   - 「从上游业务数据取数」= 现有行为（行名对齐 + 重算取数字段），**不改行集**
   - 「以在线编辑（OO）侧为准，覆盖表单」= 反向收敛，**会改行集**
   - 「以表单为准，覆盖在线编辑」= 正向收敛（依赖 Requirement 4，未实现前置灰并注明原因）
3. 弹窗 SHALL 显示两侧当前行数差异摘要（如「表单 7 行 ｜ 在线编辑侧 33 行」），
   使用户在选择前就知道会发生什么
4. WHEN 用户未做选择而关闭弹窗 THEN 系统 SHALL 不执行任何取数
5. 🔴 「覆盖表单」选项 SHALL 有二次确认，并明示这是**破坏性操作**（覆盖当前表单数据）
6. 弹窗文案 SHALL 全中文（技术术语 OO / Excel 可保留）

---

## Requirement 2：反向收敛端点（substrate → store），不依赖 room

**User Story**：作为审计助理，即使在线编辑打不开（materialize 500），我也要能把在线编辑侧
已有的内容拉回表单，从而打破死锁。

### 可行性（零件已现算确认，全部已存在）

| 零件 | 位置 | 现算签名 / 说明 |
|---|---|---|
| published substrate → projection | `adapter.extract(artifact=, contract=)` | 本轮探针已实跑通（`rebased_world` 以 gen165 字节 rebase） |
| projection → store 载荷 | `phase5_d4_revenue_detail.py:1983` | `merge_projection_into_all_d4_stores(*, projection, base_by_item) -> dict[str, tuple[Any, int, int, set[str]]]` |
| store item 全集 | 同上 `:2273` | `all_store_item_ids() -> tuple[str, ...]`，docstring 明写「出/回**两方向**的唯一权威口径」 |
| 通用性 | 47 个 provider 均有 `all_store_item_ids` | ⇒ 本端点可做成**全 entry 通用**，非 D4 专用补丁 |

🔴 **不得复用 `OoToHtmlCoordinator`**：其准入门只接受 incoming artifact
（`SubstrateNotIncomingError` / `assert_coordinator_substrate_admissible(origin=, artifact_kind=,
artifact_state=, …)`），而本端点读的是 **published** substrate，会被门拒。
故走投影层纯函数，但**必须补上等价保护**（见下方 AC 5~9）。

### Acceptance Criteria

1. 系统 SHALL 提供 `POST {USER_SYNC_PREFIX}/adopt-substrate`，语义为
   「以当前 published substrate 的受管区内容为准，覆盖本 entry 的 store」
2. 端点 SHALL 复用 `_guard` 做 scope 鉴权，与同 router 其它端点一致（不新造鉴权口径）
3. 端点 SHALL 按 `provider.all_store_item_ids()` 取 base 载荷、调 provider 的
   `merge_projection_into_all_*_stores` 得到新载荷，**不自造字段映射**（第二真源禁令）
4. 端点 SHALL 返回逐 item 的 `(inserted, updated, row_keys)` 摘要，供前端展示"改了什么"
5. 🔴 substrate 准入：WHEN substrate 不是 published（quarantined / incoming / 缺失）
   THEN 端点 SHALL 拒绝并给出可读原因，不得降级成"空 projection 覆盖"（那等于清空整表）
6. 🔴 并发保护：端点 SHALL 要求客户端传 `expected_revision`，与服务端不符即 409，
   不得无条件覆盖（替代 `OoToHtmlCoordinator` 的 fence 保护）
7. 🔴 可回滚：端点 SHALL 在覆盖前把被覆盖的 store 原值落进可追溯位置
   （复用既有 version / 审计留痕机制，不新造表），使误操作可恢复
8. 🔴 原子性：多个 store item 的写入 SHALL 在**单个事务**内完成
   （service 只 flush，router 统一 commit —— 平台既有铁律）
9. 端点 SHALL 写审计日志，记录 entry / 来源 substrate 的 sha256 / 影响的 item 与行数

---

## Requirement 3：反向收敛必须真的解除 500（端到端判据）

**User Story**：作为使用者，我要的不是"端点返回 200"，而是"在线编辑能打开了"。

### Acceptance Criteria

1. WHEN 对 D4 entry 执行 adopt-substrate 成功 THEN 随后的 `store-projection`
   SHALL 满足 `extracted - intended = ∅`（即 `extra = 0`）
2. WHEN 随后点「在线编辑」 THEN materialize SHALL 返回 200 并给出 descriptor
3. 🔴 判据 SHALL 用**离线 harness 复算**而非只看 HTTP 状态码：
   以真 substrate 字节 + 收敛后 store 复跑 extract 与差集，钉死 `extra=0`
4. 🔴 **必须验证不会复现 `7→33` 写爆**：
   `e52e5e5ce` 防的是「以**模板**为 substrate 时写 33 行进 12 行数据区」，
   而 adopt 后 substrate 已是 33 行（受管区已扩张）⇒ 推断无需插行。
   ⚠ **该推断本轮未实测**，SHALL 用 harness 钉死后才可采纳；若实测证伪则本方案退回 P1
5. adopt 后 D4 的 13 张受管 sheet SHALL 全部仍可正常 extract（不得只验 D4-2 一张）

---

## Requirement 4：materialize 的受管行收敛（正向根治）

**User Story**：作为审计助理，当我在表单里删掉一行并保存后，在线编辑侧也应该不再有那一行，
而不是永久残留、最终把 entry 卡死。

### 现状（已现算，含变异证明）

删行能力**已建齐但生产零消费方**（`_d4p_delete_wiring.py` 探针扫 6887 个 `.py`，
逐条判注释 vs 代码；四个函数的"生产代码引用"各为 1，而那 1 处**就是探针自己**
⇒ 扣除后为 **0**，探针自身命中即扫描器有效性的变异证明）：

| 函数 | 位置 | 现算签名 |
|---|---|---|
| `build_delete_plan` | `excel_workbook_row_change.py:1903` | `(scan, *, managed_sheet_name, managed_sheet_part, at: int, count: int, region_first_row, region_last_row, row_uuids=None, stable_ordinals=None, allow_ref_errors: bool = False) -> WorkbookRowChangePlan` |
| `resolve_deleted_row_keys` | 同上 `:1785` | `(rows: Iterable[int], *, row_uuids=None, stable_ordinals=None) -> tuple[str, ...]` |
| `shrink_sheet_rows` | 同上 `:1836` | `(xml: str, *, delete_at: int, count: int) -> tuple[str, int]` |

`excel_materialize.py` 实际只 import `plan_workbook_row_change_for_insert`(L174) 与
`PropagationDriftError, _escape`(L2390)。
⇒ 与上游 spec `excel-workbook-wide-row-change-propagation`（30/30 全绿）自己声明的原则
**自相矛盾**：该 spec Task 28 明写「只加参数不接消费方 = 平台明令禁止的死代码/假绿第①源」，
为此刻意把 `propagate_sheets` 与消费方合并交付；而删行三件恰恰处于零消费方状态。

### 分流判据（🔴 更正第七轮结论：不需要新协议）

第七轮认为「必须先让前端传删除意图才能区分『用户删行』与『模板占位行』」。**该判断不成立**。
判据可直接取自 projection 自身，且与 overlay 的取舍规则**严格对偶**：

> 凡 store 在本次 projection 的 `row_keys` 里**声明了**该 table，
> 则该 table 受管区内 store 未列出的受管行 = 应收敛；
> store **未声明**的 table 一律不碰。

因为 overlay 在读方向已按同一条规则丢弃 baseline 旧行，写方向按同规则收敛即两侧自洽；
且"store 未声明 ⇒ 不动"保证不会误删。

### 收敛动作：优先「清空业务格」而非「删物理行」（🔴 实测支撑）

本轮实测：substrate 上「有身份但业务格全空」的行共 **130** 个，其中进 `extracted` 的为 **0**
⇒ **extract 只对非空业务格产字段** ⇒ 清空业务格即足以消除 `extra`，无需改变行结构。

清空优于删行的理由：不动行号 ⇒ 不触发 `build_delete_plan` 的悬空引用门、
不影响跨 sheet 公式、不需要处理"多个不连续区间必须从下往上删"的顺序问题
（`build_delete_plan` 的 `at`/`count` 是**连续区间**语义，而本例 73 个孤儿散布在 25 张 sheet）。

### Acceptance Criteria

1. materialize SHALL 对「store 声明了的 table」执行受管行收敛，store 未声明的 table 不碰
2. 收敛动作 SHALL 默认为**清空受管业务格**；删物理行仅在明确需要压缩行数时才用
3. 🔴 公式格不得被清空：实测每个 D4-2 孤儿行都有 **5 个公式格**（N/P/S/T…），
   且 `GTROW-D42-0013~0023` 是"公式格 5 / 字面格 0"、其 `extra` 恰为 `period_total`
   ⇒ 该 extra 来自**模板公式**。清空它会破坏模板，不清它 extra 消不掉
   ⇒ SHALL 把这类"公式产生的 extra"纳入**豁免**（见 Requirement 5）
4. WHEN 收敛涉及删物理行 AND 被删行存在悬空引用 THEN SHALL 沿用既有 fail-closed（不静默删）
5. SHALL 有变异反证：故意让 store 不声明某 table，断言该 table 的行**未**被碰

---

## Requirement 5：公式格产生的 extra 必须被豁免

**User Story**：作为平台维护者，我不希望"模板自带的公式"被当成"用户多出来的数据"而把 entry 卡死。

### 现状

`e52e5e5ce` 的注释承诺「roundtrip 校验中 extract 读到但投影没有的 **protected** 字段会被豁免」。
本轮 402 个 extra 即该承诺的**反例**：其中 `GTROW-D42-0013~0023` 的 `period_total`
来自模板公式格（该行字面格为 0），却出现在 extra 里 ⇒ 豁免机制**未覆盖公式列**。

### Acceptance Criteria

1. roundtrip 判据 SHALL 把「值来源为公式格」的字段纳入豁免，与既有 protected 豁免同一机制
2. 🔴 豁免 SHALL 仅限公式格：字面值格产生的 extra **不得**豁免
   （否则等于把 fail-closed 判据整体弱化，那是本轮明确拒绝的方向）
3. SHALL 有变异反证：把同一格从公式改成字面值，断言它**重新**进入 extra

---

## 非目标（明确排除）

1. **不弱化 roundtrip fail-closed 判据**（除 Requirement 5 的公式格豁免，且须带变异反证）
2. **不改权威模板**（D4-10 受管区的占位骨架另案处理，见下方遗留）
3. **不改 `importFromLedger` 的既有语义**（其身份幂等性缺陷见遗留 ③）
4. **不 hack live 数据、不造假数据**

## 遗留待裁决

1. **D4-10 占位骨架**：store 恒 `rows: []` 而模板受管区 R13~R33 预置占位内容
   （`大额客户一`/`产品1` + E/G/J/M 的 `=IF(...)`）。收敛后用户下次填写将没有模板样式行 ——
   UX 取舍，非正确性问题
2. **谁整批替换了 `D4-2-rows`** 尚未定位（已排除 `useD4RevenueDetail.ts:78` fallback，
   因 store 带 `rowId`；也已排除 `importFromLedger`，其为 push 语义）
3. **`importFromLedger` 身份幂等性**（`useD4RevenueDetail.ts:308`）：
   每个台账产品无条件 `rowId: generateRowId()`，同产品重复导入即产生"内容同、身份异"的行,
   是持续制造孤儿的上游。改它属行为变更（现提示语承诺「现有行保留」），需产品裁决

---

# 🔴 方向裁决与需求更正（2026-09-28 实施中追加，以本节为准）

> 本节是实施过程中的实证更正，**优先于上方原始需求**。原文保留备查（append-only）。

## 更正 1：Requirement 5（公式格豁免）**作废** —— 豁免本已存在且生效

原 Requirement 5 的前提「`e52e5e5ce` 承诺的 protected 豁免未覆盖公式列」是**裸差集口径
误判**造成的假命题。

实证：生产判据 `_assert_roundtrip_equivalent`（`content_mutation.py:1819`）在算 extra
**之前**先跑 `_managed()`，按 `PROTECTED_MODES = {formula, auto_source}` 的
`stable_field_key` 模板（含 `{row_uuid}` 展开）剔除。D4 的 73 个公式字段
（`period_total` 33 + `amount_ratio` 20 + `quantity_ratio` 20，对应 5 个 `mode=formula`
契约模板）**逐 key 验证全部已被豁免命中**。

⇒ **Task 10 无需实现**。豁免机制正确，不得为它改动 roundtrip 判据（改了反而是弱化）。

## 更正 2：extra 真实规模是 **77**，不是 402/126

| 口径 | extracted | intended | extra |
|---|---|---|---|
| 裸差集（Req 背景里的 402、实施首算的 126） | 1311 | 1185 | 虚高 |
| `_managed`（**生产判据**） | 1238 | 1161 | **77** |

⇒ 凡本 spec 内的 extra 数字，**一律以 `_managed` 口径为准**；验收判据必须用生产口径复算，
禁自造差集（这是本 spec 踩过三次的同型问题）。

## 更正 3：Requirement 2/3（P0 反向收敛）**降级为运维工具**，不再是解阻路径

实证：`store_mirror` 的 merge 语义是「以 base（当前 store）行集为权威，只更新已有行、
**不追加** base 没有的行」——与 overlay 读方向「store 为权威」是**一致的设计**。
故 adopt 永远追不上 substrate（extra 停在 77，`changed_item_count` 报 0）。

⇒ Requirement 3（「反向收敛必须真的解除 500」）**不可达**，作废。
Requirement 2 的端点**保留并已交付**，定位改为运维工具，并登记两条已知局限：
①merge≠覆盖（覆盖不完整）②`changed_item_count` 不可信（同事务快照读不到未提交写）。

## 更正 4：Requirement 4（materialize 收敛）**提为唯一主线**，动作改为删物理行

原 Requirement 4 AC 2 写「收敛动作 SHALL 默认为**清空受管业务格**；删物理行仅在明确需要
压缩行数时才用」。**经用户裁决改为删物理行**：

理由：动态插行能力**已具备且生产在用**（`plan_managed_writes` 6.2 的 `_plan_row_shift` +
`plan_workbook_row_change_for_insert`）。既然行数不够时能动态插，就不该靠预留空行凑数 ——
留空行是半吊子，且会让下次「插行 vs 复用空行」的判定复杂化。删行后 substrate 行集精确跟随
store，这才是「只插不删」病根的真正闭合。

🔴 删行的悬空引用风险**由引擎自带保护化解**（无需自写判定）：
`build_delete_plan`（`excel_workbook_row_change.py:1903`）首步即 `find_dangling_sites`，
删行会让任何公式变 `#REF!` 时抛 `DanglingReferenceError`（默认 `allow_ref_errors=False`
fail-closed）。⇒ Design §六 R2「删行是否撞悬空引用未知」**已解除**（我自写的正则口径已证
失效，不得复用；引擎判定是权威）。

### 新增 AC（替代原 Req 4 AC 2/3）

1. 收敛动作 SHALL 删除 stale 物理行（不再是清空业务格）
2. stale 行 SHALL 按 `(sheet, 连续区间)` 分组，每组一个 `build_delete_plan`，
   且 SHALL **从下往上删**（先删高行号，避免行号位移影响后续区间定位）
3. WHEN 任一 stale 区间存在悬空引用 THEN SHALL 沿用 `DanglingReferenceError` fail-closed，
   **不得**传 `allow_ref_errors=True` 绕过
4. 🔴 公式格**不因删行而被特殊处理**：删的是整行，公式格随行消失是正确语义
   （与「清空业务格需保留公式格」不同——那条随清空方案一起作废）

## 更正 5：live 污染保留为回归靶子（不清理）

D4 的 39 个 store item 中 30 个带测试污染，多为 2026-09-25 及更早的历史遗留，
**无干净基线可回退**。单清 store 会让 extra 从 77 涨到接近 1238（store 空 + substrate 满）；
双侧重置后 extra 天然为 0 ⇒ 失去验证 C 的靶子。

⇒ 当前 77 个 extra（覆盖模板占位 49 / 双重身份 24 / L2 污染 4 三种成因）SHALL 作为
Task 11~13 的**验收样本**：C 落地后它们应被收敛逻辑自动清掉，extra→0（`_managed` 口径）。

---

# 🔴 更正 6：收敛动作改为**按受管区容量分级**（离线实测确立，取代纯删行）

## 实测依据（改引擎前的可行性验证，全部离线只读）

**判据有效性 ✅**：77 个 extra（`_managed` 生产口径）**100% 落在「store 声明过的 table」内**，
判据未覆盖为 **0** ⇒ 对偶判据（Req 4 / 更正 4）充分，不存在「删了也解决不了」的残留。

映射到 **46 个 stale 身份**，分布 4 个 sheet，且**每个 sheet 恰好一个连续区间**：

| sheet | stale 区间 | 身份数 |
|---|---|---|
| `客户访谈记录 D4-31` | R5 | 1 |
| `收入与开具发票金额比较分析D4-23` | R12~R23 | 12 |
| `重要客户销售价格分析D4-10` | R13~R33 | 21 |
| `重要指标分析表D4-22` | R12~R23 | 12 |

⇒ 更正 4 里担心的「连续区间切分」实际**只有 4 个区间、零碎片**，复杂度远低于预估。

**悬空引用 ✅**：真删这 46 行的过程**零触发**（`悬空/异常拦截: 0 处`）
⇒ 这批行未被任何公式引用，删除在引用层面安全。

**撞到一个真实边界 🔴**：删完后 `adapter.extract` 抛 `IdentityCarrierMissingError`：

> 受管区 sheet='客户访谈记录 D4-31' table_ref='A5:K5' uuid_col='K'
> 在 Table ref 覆盖的行区间内**一个 row identity 都没反读到**（空 UUID 行 1 个）

根因：**D4-31 的受管区就是那 1 行**（`A5:K5` 单行区），它同时是 stale 行 ⇒ 删掉即把受管区
删空 ⇒ 引擎按 Requirement 6.15/6.20 fail-closed 拒绝整个 entry。
而 `shrink_sheet_rows` 只删行、**不同步收缩 Table ref**（那是 apply 期另一步的职责）。

## 裁决：分级处置（「清空」与「删行」不是二选一，而是按容量分流）

| 情形 | 动作 | 理由 |
|---|---|---|
| 删后受管区仍剩 **≥1 行**有身份的数据行 | **删物理行** | 行数精确跟随 store，闭合「只插不删」病根 |
| 删后受管区**归零**（如 D4-31 单行区） | **清空业务格**（保留物理行与身份载体，只清 editable 字面值） | 保住引擎结构前提（受管区不得无身份行） |

⇒ 这也解释了为何最初的「清空」建议与后来的「删行」裁决**都对但都不完整**：
它们各自覆盖了分级的一侧。

## 新增 AC（追加到 Requirement 4，与更正 4 的 AC 1~4 并存）

5. 收敛前 SHALL 先算「删后受管区剩余有身份数据行数」；`≤ 0` 时 SHALL 退回清空业务格，
   **不得**执行物理删行
6. 清空分支 SHALL 只清 `editable` 字面值格，**保留**身份载体列与公式格
   （否则触发同一个 `IdentityCarrierMissingError`）
7. SHALL 有覆盖两个分支的测试：一个「可删」样本（如 D4-10 的 21 行）+ 一个「会删空」样本
   （D4-31 的单行区），后者断言**未**发生物理删行且 extract 仍成功
8. 🔴 删行分支 SHALL 同步收缩受管 Excel Table 的 `ref` 行区间
   （`MaterializePlan.table_part` 已为插行场景做过 ref 增长，删行需对称收缩）
