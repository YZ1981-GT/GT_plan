# Design — 受管行双向收敛

## 一、问题的结构：三个方向，两个缺口

底稿数据有三个可能的"权威源"，平台的取数/同步动作各对应一个方向。
把它们摊开后，缺口位置就一目了然（本表全部已现读确认）：

```
        ┌─────────────────────┐
        │  上游业务数据        │  TB / 序时账 / 其它底稿
        │  (trial_balance …)  │
        └──────────┬──────────┘
                   │ ① 刷新取数（已有）
                   │   GtWpRenderer.vue:147 → onRowNameAlignmentRefresh
                   │   POST /api/workpapers/{id}/row-name-alignment + reload()
                   ▼
        ┌─────────────────────┐   ② materialize（已有，但只插不删）
        │   HTML store        │ ─────────────────────────────►┌──────────────┐
        │ checklist_responses │                               │  substrate   │
        │                     │ ◄─────────────────────────────│   (xlsx)     │
        └─────────────────────┘   ③ 反向收敛（能力有，入口无） └──────────────┘
```

| 方向 | 入口 | 缺口 |
|---|---|---|
| ① 上游 → store | 「刷新取数」/「批量刷新」 | 无缺口，但**只改字段值不改行集** ⇒ 对 `extra` 无效 |
| ② store → substrate | `materialize` | **只插不删**；`build_delete_plan` 已建但生产零消费方 |
| ③ substrate → store | 全部锁在 room 内（`forcesave` / `onlyoffice-callback` / `recovery-cases` 都要 `room_id`） | **没有不依赖 room 的入口**；而 room 由 materialize 创建 ⇒ **死锁** |

**死锁是本 spec 的第一目标**：只要 ③ 有了入口，用户在 materialize 失败时仍有出路。

## 二、为什么 P0 选 ③ 而不是 ②

| 维度 | ③ 反向收敛（P0） | ② materialize 收敛（P1） |
|---|---|---|
| 引擎改动 | **零**（`excel_materialize.py` 一行不动） | 改 3600+ 行核心写入路径 |
| 数据风险 | 不删任何东西（store 多认领，多余行用户可见可手工删） | 接错会**静默删用户数据**，比现在的 fail-closed 500 危险 |
| 影响面 | 新增端点 + 新增弹窗选项，既有路径零变化 | 影响**所有** entry 的每次物化 |
| 零件齐备度 | 全齐（见下 §三） | 齐但需设计区间切分与顺序 |
| 能否解阻 D4 | 能 | 能 |

⇒ 先用 ③ 解阻并让用户拿回控制权，再用 ② 根治。两者不互斥。

## 三、③ 反向收敛的实现路径（零件全部已存在）

```
POST {USER_SYNC_PREFIX}/adopt-substrate
  body: { expected_revision: int, sheet_key?: str }
  │
  ├─ _guard(action="adopt_substrate")            ← 复用既有 scope 鉴权，不新造口径
  ├─ _registration(svc, scope) → contract
  ├─ 解析 published substrate
  │    🔴 必须校验 artifact_kind/state 为 published
  │       （不能是 incoming / quarantined / 缺失）
  ├─ adapter.extract(artifact=substrate, contract=contract) → Projection
  │    ✅ 本轮探针已实跑通此路径（harness.rebased_world 以 gen165 字节 rebase）
  ├─ base_by_item = { item: 现 store 载荷 for item in provider.all_store_item_ids() }
  │    ✅ all_store_item_ids docstring：「出/回两方向的**唯一**权威口径」
  ├─ provider.merge_projection_into_all_*_stores(projection=…, base_by_item=…)
  │    → dict[item_id, (新载荷, inserted, updated, row_keys)]
  ├─ 落库前：把被覆盖的原值写入可追溯位置（Requirement 2 AC 7）
  ├─ 逐 item upsert checklist_responses   ← service 只 flush
  └─ router 统一 commit                    ← 平台既有铁律（跨 service 编排原子性）
```

### 3.1 为什么不能复用 `OoToHtmlCoordinator`

它的准入门只接受 **incoming** artifact：

- `SubstrateNotIncomingError` / `SubstrateOriginForbiddenError` / `LEGAL_SUBSTRATE_ORIGIN`
- `assert_coordinator_substrate_admissible(*, origin, artifact_kind, artifact_state,
  durable_at, published_at, declared_incoming_artifact_id, resolved_artifact_id)`

而本端点读的是 **published** substrate ⇒ 必被拒。
🔴 但那些门是有理由的，绕开就**必须补等价保护**，逐条对应：

| 协调器的保护 | 本端点的替代 |
|---|---|
| fence / 写栅栏（防并发覆盖） | `expected_revision` 不符即 409（Req 2 AC 6） |
| substrate 准入（防脏源） | 显式校验 published（Req 2 AC 5），缺失/隔离即拒，**不得降级成空 projection** |
| 三路合并 + adjudication | 本端点语义是**单向覆盖**，由用户显式选择并二次确认（Req 1 AC 5） |
| 应用留痕 / 可重放 | 覆盖前留存原值 + 审计日志（Req 2 AC 7 / AC 9） |

🔴 **「不得降级成空 projection」是本设计最关键的一条**：
若 substrate 缺失时返回空 projection 并据此覆盖 store，等于**一键清空整张表**。
这与 `store_projection_response` 既有注释「失败一律 fail visible（不返回空 projection ——
空 projection = 清空整表）」是同一条铁律。

### 3.2 通用性：不是 D4 专用

`all_store_item_ids()` 在 **47 个 provider** 里都有定义（D1/D3/D5/D6/D7/E1/F1~F5/G1~G14/
H2~H10/I1~I6/J1/L1/D2 pilot…）。端点按 provider 门面调用即可对全部 entry 生效
⇒ 实现一次，所有卡在同类问题上的 entry 都有出路。

## 四、① 刷新取数的来源选择弹窗

### 4.1 落点

`GtWpRenderer.vue` L147 的「刷新取数」按钮：现直接调 `onRowNameAlignmentRefresh`，
改为先开弹窗。**既有行为成为弹窗里的第一个选项**（不改其实现，只是改触发时机）。

### 4.2 弹窗内容

```
┌─ 刷新取数 ─────────────────────────────────────────────┐
│  当前差异：表单 7 行 ｜ 在线编辑侧 33 行                 │
│                                                        │
│  ○ 从上游业务数据取数                                   │
│     按行名对齐重新计算取数字段。不改变行的增减。         │
│                                                        │
│  ○ 以在线编辑（OO）侧为准，覆盖表单                     │
│     把在线编辑里的内容拉回表单，行的增减以在线编辑为准。 │
│     ⚠ 会覆盖表单当前数据                                │
│                                                        │
│  ○ 以表单为准，覆盖在线编辑        〔暂不可用〕          │
│     需要「受管行收敛」能力，见 Requirement 4。           │
└────────────────────────────────────────────────────────┘
```

差异摘要的数据来源：`store-projection` 端点已返回 `row_count` / `field_count` /
`store_field_count` / `overlay_applied`，可直接用；两侧行数差异需要 baseline 与 store
分别的行数 —— 🔴 **现有响应给不出"未收缩的 baseline 行数"**（overlay 已把旧行丢掉），
故端点需**补一个只读字段**（如 `baseline_row_count`），或弹窗改用 adopt 的 dry-run。
**Task 阶段必须先确认**，不得假设现有响应够用。

### 4.3 为什么把选择权交给用户而不是自动判断

系统无法可靠区分"两侧不一致"的成因（用户在 OO 里改了 / 用户在表单里删了 / 身份漂移造成的
假不一致）。三者的正确处置完全相反，猜错的代价是静默丢数据。
⇒ 显式选择 + 差异摘要，让做判断的人是唯一掌握业务意图的人（审计师）。

## 五、② materialize 受管行收敛（P1）

### 5.1 判据：与 overlay 严格对偶

overlay（`projection_first_publication.py` 的 `overlay_store_on_baseline_projection`，
commit `e52e5e5ce` 后）的读方向规则：

```python
store_table_keys = set(store_projection.row_keys.keys())
for table_key in {*baseline.row_keys, *store_projection.row_keys}:
    if table_key in store_table_keys:
        row_keys[table_key] = store_projection.row_keys[table_key]   # store 为权威
    else:
        row_keys[table_key] = baseline.row_keys.get(table_key, ())   # baseline 原样
```

写方向按**同一条**规则收敛：

| table 是否在 `store_projection.row_keys` | 读方向（overlay 现状） | 写方向（本 spec 新增） |
|---|---|---|
| 在 | 用 store 行集，丢弃 baseline 旧行 | **收敛**：受管区内 store 未列出的行 → 清空业务格 |
| 不在 | 保留 baseline 原样 | **一律不碰** |

⇒ 这保证了：① 两侧自洽（读方向丢掉的，写方向真的清掉）
② 不会误删（store 没声明 ⇒ 不动，这是"少做"而非"多做"）
③ 不需要新协议（🔴 更正第七轮"必须先传删除意图"的判断）

### 5.2 动作选型：清空业务格 ≫ 删物理行

**实测依据**：substrate 上「有身份但业务格全空」的行共 **130** 个，
进 `extracted` 的为 **0** ⇒ extract 只对非空业务格产字段
⇒ 清空业务格已足以消除 `extra`。

| 维度 | 清空业务格 | 删物理行 |
|---|---|---|
| 行号变化 | 无 | 有 ⇒ 需重算所有后续引用 |
| 悬空引用门 | 不触发 | `build_delete_plan` 会在计划阶段抛 |
| 多区间顺序 | 无此问题 | `at`/`count` 是**连续区间**语义，而 D4 的 73 个孤儿散布在 25 张 sheet ⇒ 需切区间 + 从下往上删 |
| 模板样式 | 保留 | 丢失 |
| 残留空行 | 有（行还在，内容空） | 无 |

⇒ 默认清空；仅当明确需要压缩行数时才走删行（那时才需要 `build_delete_plan`）。

🔴 **公式格必须排除**（Requirement 5）：实测每个 D4-2 孤儿行都有 5 个公式格（N/P/S/T…），
且 `GTROW-D42-0013~0023` 是"公式格 5 / 字面格 0"、其 extra 恰为 `period_total`。
清空公式会破坏模板 ⇒ 公式格产生的 extra 走**豁免**而非清空。

### 5.3 与既有 fail-closed 的关系

本 spec **不弱化** roundtrip 判据。唯一的豁免扩展是"公式格产生的 extra"，
且要求变异反证（把同一格改成字面值 ⇒ 必须重新进 extra）。
字面值格产生的 extra 仍然 fail-closed。

## 六、风险与未验证项（诚实标注）

| # | 项 | 状态 |
|---|---|---|
| R1 | adopt 后不会复现 `7→33` 写爆 | 🔴 **推断，未实测**。理由：`e52e5e5ce` 防的是以**模板**为 substrate 写 33 行进 12 行区，而 adopt 后 substrate 已是 33 行（受管区已扩张）⇒ 无需插行。**必须用 harness 钉死**；若证伪则 P0 退回 P1 |
| R2 | 删行是否撞悬空引用 | 🔴 **未知**。本轮扫"是否有公式引用 D4-2 R24~R37"得 0，但**变异探针同时得 0** ⇒ 扫描器口径失效（中文 sheet 名 + 引号形态未覆盖），该结论**作废不可用**。走清空方案可绕开此风险 |
| R3 | 有并发会话在改同一块代码 | `e52e5e5ce` 即本日别的会话所提。实施前**必须**重新确认 `projection_first_publication.py` / `excel_materialize.py` 状态 |
| R4 | 弹窗差异摘要的数据来源 | overlay 已丢弃 baseline 旧行 ⇒ 现有响应**给不出**未收缩的 baseline 行数，需补只读字段或用 dry-run。Task 阶段先确认 |
| R5 | adopt 会把重复/占位行带进 store | **已知且接受**：D4 会变成 33 行（14 重复副本 + 12 占位）。它们在 HTML 侧可见，由审计师判断后手工删。这是"可见的脏"优于"不可用的干净" |

## 七、验证策略

1. **离线 harness 为主判据**，HTTP 状态码为辅
   （复用 `backend/tests/workpaper_sync/d4_materialize_harness.py` 的
   `build_world` / `rebased_world`，本轮已实跑通）
2. **每条"结构性零"结论必配变异证明** —— 本轮 R2 就是被变异探针拦下的错误断言，
   若无变异探针会写成"删行安全"
3. **口径自证**：差集类判据必须同时报 `common` / `missing`，`common=0` 即口径不可比
4. **不得只验 D4-2**：D4 有 13 张受管 sheet、43 个 table，收敛后需全部仍可 extract
5. **反向变异**：故意让 store 不声明某 table ⇒ 断言该 table 行未被碰
