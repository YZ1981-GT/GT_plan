# Design — adopt 真覆盖 + 刷新取数来源选择

## Overview

本 spec 做两件事，顺序不可颠倒：

1. **先把 adopt 的行集语义补成真覆盖**（Requirement 1~4）——
   这是用户裁决的「第一个裁决点」；
2. **再把「刷新取数」改成来源选择弹窗**（Requirement 5~7）——
   选项集合依赖第 1 件的结果。

改动的**唯一实质缺口是删除侧**。这不是猜的，是本轮离线探针五例实测的结论
（见 requirements 的事实基线表）：merge 已经会更新、也会追加（受幽灵行门约束），
只是**永不删除** base 有而 projection 无的行。

因此本 design 的核心不是「怎么写一个覆盖函数」，而是**怎么在一条两方共用的执行层上
只给其中一方开删除侧**，以及**删除的行集边界到底划在哪**。

### 现算实证基线（🔴 全为现算值，禁写死；交付前须重算）

| 事实 | 现算值 | 取法 |
| --- | --- | --- |
| `all_store_item_ids` 定义数 | **46** | `backend/app/services/workpaper_sync/**.py` 行首正则（上游 spec 记 47，本轮修正） |
| `merge_projection_into_store_rows` 定义数 | **36** | 同上 |
| `iter_store_rows` 定义数 | **25** | 同上（引擎 1 + 薄转发若干） |
| `ROW_IDENTITY_STORE_KEY*` 赋值处 | **119 处 / 112 文件** | 行首 `Final[str] =` 正则 |
| 行身份键字面量取值 | **7 种**：`rowId` 65 / `id` 29 / `rowKey` 5 / `key` 1 / `month` 1 / `metricName` 1 / `rowUuid` 1（合计 103；余 16 处是跨模块引用常量，不产字面量） | 同上，捕获字符串字面量 |
| `row_section_field=` 非空字面量 | **7 处 / 6 文件**（`phase5_g1_02_detail` / `phase5_g1_trading_financial_assets` / `phase5_g9_02_detail` / `phase5_g9_other_noncurrent` / `delivered_contracts_ledger` / `store_item_registry`） | 同上 |
| 前端对 `adopt-substrate` 的引用 | **0** | 扫 `audit-platform/frontend/src/**`；变异证明 = 同一扫描器对 `row-name-alignment` 在 `GtWpRenderer.vue` 命中非零 |
| 后端对 `adopt-substrate` 的测试引用 | **2 处**，全在 `test_task28_sync_router.py` 的路由清单/handler 分母守卫 | 扫 `backend/**` ⇒ **无端点级行为测试** |

🔴 行身份键有 **7 种**取值（不是统一的 `rowId`）——
这一条直接否决「在通用层硬编码 `row.get("rowId")`」的任何实现。

---

## Architecture

### 2.1 三个方向与本 spec 的作业面

```
        ┌─────────────────────┐
        │  上游业务数据        │  TB / 序时账 / 其它底稿
        └──────────┬──────────┘
                   │ ① 刷新取数（既有，不改实现）
                   │   Workpaper_Renderer → POST /row-name-alignment
                   ▼
        ┌─────────────────────┐   ② materialize（上游 spec 已收敛，本 spec 不碰）
        │   HTML store        │ ─────────────────────────────►┌──────────────┐
        │ checklist_responses │                               │  substrate   │
        │                     │ ◄─────────────────────────────│   (xlsx)     │
        └─────────────────────┘   ③ adopt-substrate（本 spec 作业面） └──────────────┘
                   ▲
                   │  Refresh_Source_Dialog：把 ①②③ 的选择权交给用户（本 spec 作业面）
```

本 spec 只改 ③ 与弹窗。② 的 `stale_deleted` / `shrink_sheet_rows` /
`_shrink_managed_table_ref` 属 B 线 spec，**一行不动**。

### 2.2 改造后的 adopt 执行链

```
POST {USER_SYNC_PREFIX}/adopt-substrate
  body: { dry_run, expected_revision, plan_digest? }
  │
  ├─ _guard(action="adopt_substrate")           ← 既有，不改（已在 _WRITE_ACTIONS）
  ├─ _registration(svc, scope) → contract       ← 既有，不改
  ├─ _current_revision → expected_revision 比对 ← 既有，不改（409）
  ├─ _resolve_published_substrate               ← 既有，不改（fail-closed，不空覆盖）
  ├─ adapter.extract(artifact, contract) → substrate_projection
  │
  ├─ ★ compute_overwrite_plan(                  ← 新增纯函数（单一真源）
  │       substrate_projection,
  │       store_snapshot,                       ← 逐 item 原始载荷（现有 _snapshot_store 扩展）
  │       item_row_readers,                     ← 由 provider 门面提供的行枚举器
  │   ) -> OverwritePlan
  │
  ├─ dry_run=True  ⇒ 直接返回 plan（含 plan_digest）★ 终止
  │
  ├─ plan_digest 回传值与重算值比对 ⇒ 不符即 409     ← 新增
  │
  ├─ mirror_projection_into_store(..., commit=False)   ← 既有（base 权威，不变）
  ├─ ★ apply_overwrite_deletions(plan, commit=False)   ← 新增：只做删除侧
  ├─ ★ 提交前复读 + 与 plan 比对，不符即 rollback       ← 新增
  ├─ _record_rollback_and_audit（含删除侧身份清单）     ← 既有 + 扩展 details
  └─ session.commit()                                  ← 既有
```

🔴 注意顺序：**先 merge（追加+更新），后删除**。理由在「§ 头号约束的裁定」。

---

## 🔴 头号约束的裁定：删除侧落在哪一层

### 3.1 约束陈述

`store_mirror.mirror_projection_into_store` 是 OO callback 与 adopt 共用的**同一份**执行层，
抽取它的目的就是消除第二真源（模块 docstring 明写）。而**真正决定行集的合并策略不在
`store_mirror` 里**，它在各 provider 的 merge 函数里 —— `store_mirror` 只负责：
读 base 载荷、调 provider merge、按 `applied <= 0 and base` 跳过、UPSERT、commit。

⇒ 「把 merge 改成真覆盖」这句话本身需要先定位**改哪一层**。

### 3.2 四个候选方案，逐条取舍

#### 方案 1：给 merge 加显式 mode 参数（`base_authoritative` / `substrate_authoritative`）

- **优点**：语义最显式，落点就在决定行集的那一层；两条路径各传各的，读代码时一目了然。
- **缺点**：
  - 改动面 = 现算 **36** 个 `merge_projection_into_store_rows` 定义 + D4 一家另有
    `merge_d45_fixed_from_projection` / `merge_d413_fixed_from_projection` /
    `merge_projection_into_d410_rows` / `merge_projection_into_d420_stores` /
    `merge_interview_projection_into_store` 等专用门面。虽然多数薄转发到引擎，
    但**门面签名要逐个改**，且新 provider 接入时忘传 mode 就会静默退化。
  - 违反 Requirement 2.3（不改 Provider_Merge 公开签名）。
  - 最致命的一条：mode 若落在 merge 内部，删除决策就发生在**引擎不知道 row_section 全貌**
    的地方 —— 引擎 merge 的入参 `base_rows` 是**整个** store 数组（含其它分区的行，
    引擎 docstring 明写），mode 参数会诱导实现者在那里做 `base - projection` 全量差集，
    **直接删掉兄弟分区的行**。
- **裁决**：❌ 不采。保留为兜底（若方案 4 的行枚举在某些形态上取不到，可退回给**引擎一家**
  加 mode，而不是 36 个门面）。

#### 方案 2：adopt 走独立 overwrite 函数，与 merge 并列在 `store_mirror` 内

- **优点**：OO 路径**零改动**，这是最强的「不破坏」判据（可用 git diff + 文件 sha256 钉死）。
- **缺点**：若 overwrite 自己实现「分发 + 逐 item 读写」，就是把 `store_mirror` 抽取时刚消灭的
  第二真源重新造出来（provider 门面命名 / dedicated item 清单必然漂移）。
- **裁决**：⚠️ 部分采纳 —— 采纳「独立函数、OO 零改动」这一点，但**不重造分发**：
  独立函数只做删除侧，追加/更新仍复用 `mirror_projection_into_store`。

#### 方案 3：adopt 侧**先清**受管行集再 merge（两步，前置）

- **中间态可见性**：不成问题。adopt 已经是 `commit=False` + 统一 commit + 异常 rollback
  （上游第九轮为原子性专门改的），中间态不落库、对其它会话不可见。
- **致命缺陷（探针实证）**：清空 base 会让 projection 里的**每一行都变成「本次新增身份」**
  ⇒ **幽灵行门全面生效** ⇒ 探针用例 B 的形态被放大到全表：
  任何锚点业务名为空的行都会被剔除。而探针用例 E 证明「已存在行被清空是合法编辑、不剔除」——
  前置清 base 会把 E 类行错误地降级成 B 类行处理。
  ⇒ 前置清空**会意外改变幽灵行门的语义**，而那不是本 spec 想改的东西。
- **裁决**：❌ 不采。这条缺陷只有真调过 merge 才会发现，是本轮探针的直接产出。

#### 方案 4（采纳）：**后置 prune** —— merge 正常跑完，再按声明行集剪枝删除侧

```
merged_payload = provider_merge(projection, base)        # 追加 + 更新 + 幽灵门（语义不变）
final_payload  = prune_undeclared_rows(                  # 只做删除侧
     merged_payload,
     declared_identities = projection.row_keys[table_key],
     row_reader          = provider 的行枚举门面,
)
```

- **优点**：
  1. OO 路径零改动（prune 只在 adopt 链上调用）；
  2. 幽灵行门语义**完全不变**（prune 在 merge 之后，不改变「谁是新增身份」的判定）；
  3. prune 的输入输出都是载荷，可写成**纯函数** ⇒ 可 PBT、可单测、可变异反证；
  4. 删除决策集中在**一处**，与 overlay 读方向、materialize 侧收敛构成**三处同一条规则**
     （`declared_table` 才动，未声明不碰）。
- **代价**：prune 需要「从载荷枚举行身份」的能力，而行身份键有 **7 种**取值 ⇒
  必须走 provider 既有门面（现算 `iter_store_rows` 定义 **25** 个，引擎版
  `iter_store_rows(spec, payload)` yield `(identity, row)`），不得硬编码键名。
  取不到枚举器的形态（dict store / 纯文本固定项）⇒ 按 Requirement 4 跳过并**显式登记**。
- **裁决**：✅ 采纳。ADR-AOS-001。

### 3.3 为什么方案 4 不破坏 OO 路径 —— 判据（可执行，不是论证）

| # | 判据 | 形态 |
| --- | --- | --- |
| J1 | `oo_to_html.py` 的三个 `_mirror_*` 转发方法**不出现** prune 相关符号 | AST/源码锁断言 |
| J2 | `store_mirror.mirror_projection_into_store` 的签名与函数体**不新增**删除逻辑 | 会话基线 sha256 + 「本 spec 符号在该函数体内命中为零」双条件（🔴 工作树可能被并发会话改动，单靠 `git diff == 0` 不是判据 —— 这是 INDEX.md 第十四次现扫登记的教训） |
| J3 | 同一 `(base, projection)` 经 OO 路径与 adopt 路径执行，**删除侧结果不同** | 变异反证（相同即判据失效） |
| J4 | OO callback 既有引用面回归零红 | 定向跑既有测试面 |
| J5 | prune 的调用点在全仓**恰 1 处**且位于 adopt 链上 | 全仓 grep + 逐条判注释/代码 |

### 3.4 「真覆盖」的行集语义 —— 追加与删除分开裁定

用户明确要求：不能含混成一句「覆盖」。逐条给出：

| 侧 | 语义 | 破坏性 | 保护 |
| --- | --- | --- | --- |
| **更新**（命中身份的字段） | substrate 为权威 | 低（既有行为） | 无新增（已有 revision 锁 + 回滚快照） |
| **追加**（substrate 有 / store 无） | 追加，**保留幽灵行门** | 低（只增不减） | 被剔除的身份进响应清单（Requirement 1.6） |
| **删除**（store 有 / substrate 无） | **只在 declared_table ∩ 本 row_section 内删** | 🔴 **高** | 见下方六道 |

#### 删除侧的六道保护

1. **作用域门**：仅 `table_key ∈ projection.row_keys` 的表参与；未声明一律不碰
   （Requirement 1.2）。这与 overlay 的 `in` 判据、materialize 收敛的
   `dynamic_table.table_key in projection.row_keys` 是**同一条规则的第三处落地**。
2. **分区门**：同一载荷承载多分区时，只删本次 projection 声明的分区
   （Requirement 1.4）。🔴 这是删除侧最容易出事的一条 ——
   引擎 `iter_store_rows` 明写「三段读同一个数组」，做全量差集就会删掉兄弟分区。
3. **空值二分**：`table_key` 不在 `row_keys` 键集合 ⇒ 不碰；在键集合但值为空元组 ⇒ 清空
   （Requirement 1.3）。沿用 overlay 已有的 `in` vs `get` 裁决，不得混用。
4. **确认绑定**：`plan_digest` 把「用户在弹窗上看到并确认的那份计划」与「服务端将执行的计划」
   钉在一起，不符即 409（Requirement 3.4）。
   🔴 刻意**不用百分比阈值闸**（如「删除超过 30% 就拒」）—— 那是拍脑袋数字，
   既会误拦合法的大批删除，也会放过小批误删。逐条绑定是精确判据。
5. **提交前复读比对**：写完在同事务复读，与 plan 不符即回滚（Requirement 3.5）。
6. **可回滚**：删除的行随原始载荷整体进 `rollback_snapshot`，删除身份清单进审计 details
   （Requirement 1.8 / 6.9）。

---

## Components and Interfaces

### 4.1 新增纯函数（同一真源，dry_run 与真实执行共用）

落点：`backend/app/services/workpaper_sync/adopt_overwrite_plan.py`（新模块）。
🔴 **不**放进 `store_mirror.py` —— 那是两方共用文件，新增内容会让 J2 判据变弱。

```python
@dataclass(frozen=True)
class ItemOverwriteDelta:
    item_id: str
    table_key: str | None          # None = 不可枚举形态（跳过删除侧）
    rows_added: tuple[str, ...]
    rows_deleted: tuple[str, ...]
    rows_updated: tuple[str, ...]
    rows_ghost_dropped: tuple[str, ...]
    skipped_reason: str | None      # 非 None 即被跳过，原因逐条可读

@dataclass(frozen=True)
class OverwritePlan:
    deltas: tuple[ItemOverwriteDelta, ...]
    store_row_count: int
    substrate_row_count: int
    store_rows_by_table: Mapping[str, int]
    substrate_rows_by_table: Mapping[str, int]
    skipped_items: tuple[tuple[str, str], ...]   # (item_id, reason) —— 显式清单非总数
    @property
    def digest(self) -> str: ...                 # 顺序无关的稳定 sha256

def compute_overwrite_plan(
    *, substrate_projection, store_payloads: Mapping[str, str | None],
    row_readers: Mapping[str, RowReader],
) -> OverwritePlan: ...

def prune_undeclared_rows(
    payload: Any, *, declared: frozenset[str], reader: RowReader
) -> tuple[Any, tuple[str, ...]]: ...            # 返回 (新载荷, 被删身份)
```

`RowReader` 是对 provider 既有门面的**薄适配**，不是新真源：

```python
class RowReader(Protocol):
    def iter_rows(self, payload: Any) -> Iterator[tuple[str, Mapping[str, Any]]]: ...
    def section_of(self, row: Mapping[str, Any]) -> str | None: ...
```

解析器来源优先级（🔴 逐级现读确认，禁按命名习惯推）：

1. provider 模块的 `iter_store_rows`（现算 **25** 个定义）——
   它已经做了「非数组即抛」「重复身份即抛」「分区过滤」三件事，正是 Requirement 4.4 要的；
2. 取不到 ⇒ 该 item 记为 `skipped_reason="no_row_reader"`，**跳过删除侧**并进显式清单；
3. 🔴 **不**自造 `row.get("rowId")` 兜底 —— 行身份键现算 **7** 种取值，兜底必错。

### 4.2 Adopt_Service 的改造点（`adopt_substrate_response.py`）

| 现有 | 改造 |
| --- | --- |
| `_dry_run_summary` 只返回 substrate 逐表行数 | 改为返回完整 `OverwritePlan`（含 digest、两侧行数、三清单、跳过清单） |
| `_snapshot_store` 只取 `remark`，返回 `dict[item, str\|None]` | 保留（回滚快照仍需全文），另加取值供 `compute_overwrite_plan` 用 |
| `changed_item_count` 来自 `_diff_snapshots` | 改为取自 `plan`（Requirement 3.6）；`_diff_snapshots` 降级为**提交前复读比对**的实现手段 |
| 无 `plan_digest` 校验 | 新增：`payload.get("plan_digest")` 非空则重算比对，不符抛 `AdoptPlanDigestMismatchError` → 409 |
| 无删除侧 | 新增 `apply_overwrite_deletions`：在 `mirror_projection_into_store(commit=False)` 之后、审计之前执行 |

新增 domain 错误类（与既有三个并列，`error_code` 命名同风格）：

- `AdoptPlanDigestMismatchError` → `adopt_plan_digest_mismatch` → 409
- `AdoptStorePayloadUnreadableError` → `adopt_store_payload_unreadable` → 422（Requirement 4.4）
- `AdoptPlanVerificationError` → `adopt_plan_verification_failed` → 500 并回滚（Requirement 3.5）

### 4.3 Adopt_Endpoint 的改造点（`wp_sync_router.py`）

只加状态码映射，不改 guard。🔴 `adopt_substrate` 已在 `_WRITE_ACTIONS`，
不得因为 dry_run 只读就把它挪进 `_READ_ONLY_ACTIONS` —— 同端点同 action，按写从严
（既有注释已如此裁决）。

🔴 `test_task28_sync_router.py` 有 3 处跟随性守卫（handler 分母 / 路由清单 / slashed 路由
suffixes 表），本 spec **不新增路由** ⇒ 这三处**不应**变化；若变了说明误加了路由，
应打红。这是一条反向判据。

### 4.4 前端：`Refresh_Source_Dialog`

新增组件 `audit-platform/frontend/src/components/workpaper/shared/RefreshSourceDialog.vue`，
在 `GtWpRenderer.vue` 内挂载；「刷新取数」按钮的 `@click` 由 `onRowNameAlignmentRefresh`
改为 `onOpenRefreshSourceDialog`。

🔴 锚点用**符号名**不用行号（`.vue` 行号会漂）：
`@click="onRowNameAlignmentRefresh"` → `@click="onOpenRefreshSourceDialog"`；
既有 `onRowNameAlignmentRefresh` **函数体一字不改**，成为弹窗第一个选项的处理器。

弹窗交互：

```
打开 → 并行请求 dry_run（POST adopt-substrate {dry_run:true}）
     → 成功：渲染摘要「表单 N 行 ｜ 在线编辑侧 M 行；将新增 a 行、删除 d 行、更新 u 行」
     → 409 adopt_substrate_not_published / 422 adopt_contract_required
       ⇒ 「覆盖表单」选项禁用 + 就地显示原因（Requirement 5.7）
选「上游业务数据」 → 直接调既有 onRowNameAlignmentRefresh
选「覆盖表单」    → 二次确认（明示破坏性 + 删除行数）
                 → POST adopt-substrate {dry_run:false, expected_revision, plan_digest}
                 → 成功：reload() + 提示实际增删条数
                 → 409 plan_digest 不符 ⇒ 提示「两侧已变化，请重新查看差异」并重取 dry_run
说明项「以表单为准，同步到在线编辑」→ 不可选，文案指引点「在线编辑」按钮
```

🔴 `apiProxy` 单层解构铁律：本弹窗若用 `api.post` 则返回值**已是**业务数据；
若用 `http.post`（`utils/http`）需 `.data`。现读 `GtWpRenderer.vue` 用的是 `http.post`
⇒ 新代码与同文件保持一致，并在任务里要求现读确认，不得混用。

---

## Data Models

**不新增数据库表、不新增迁移。** 现算确认：

- 回滚快照复用既有 hash-chain 审计的 `details.rollback_snapshot`（`append_audit_log`）；
- `event_type` 沿用 `workpaper_sync_adopt_substrate`，**有意**不进 `EVENT_TYPE_SCHEMAS`
  （既有注释已记该裁决），本 spec 只在 `details` 里**追加**字段：
  `rows_deleted_by_item` / `plan_digest` / `skipped_items`；
- store 载荷形态不变（`checklist_responses.remark` 存 JSON）。

响应体（dry_run 与真实执行同构，便于前端一套渲染）：

```json
{
  "dry_run": true,
  "substrate_sha256": "…",
  "expected_revision": 166,
  "plan_digest": "…",
  "store_row_count": 7,
  "substrate_row_count": 33,
  "store_rows_by_table": { "revenue_detail_rows": 7 },
  "substrate_rows_by_table": { "revenue_detail_rows": 33 },
  "changed_item_count": 12,
  "deltas": [
    { "item_id": "D4-2-rows", "table_key": "revenue_detail_rows",
      "rows_added": ["…"], "rows_deleted": ["…"], "rows_updated": ["…"],
      "rows_ghost_dropped": [], "skipped_reason": null }
  ],
  "skipped_items": [["D4-10-data", "no_row_reader"]]
}
```

---

## Error Handling

| 情形 | 行为 | 状态码 | 判据来源 |
| --- | --- | --- | --- |
| 未认证 | `get_current_user` 抛 | 401 | Requirement 6.1 |
| action 未授权 / `workflow_locked` | `_guard` 拒 | 403 | Requirement 6.2 |
| `expected_revision` 不符 | `AdoptRevisionConflictError`（既有） | 409 | Requirement 6.3 |
| 无已发布 substrate | `AdoptSubstrateNotPublishedError`（既有） | 409 | Requirement 6.4 |
| 无 approved contract | `AdoptContractRequiredError`（既有） | 422 | Requirement 6.5 |
| `plan_digest` 不符 | `AdoptPlanDigestMismatchError`（新） | 409 | Requirement 3.4 |
| store 载荷不可解析 | `AdoptStorePayloadUnreadableError`（新） | 422 | Requirement 4.4 |
| 提交前复读与 plan 不符 | `AdoptPlanVerificationError`（新）+ rollback | 500 | Requirement 3.5 |
| 某 item 无行枚举器 | 不报错，记 `skipped_items` 显式清单 | 200 | Requirement 4.1 / 4.2 |

🔴 **绝不降级成空覆盖**：既有 `_resolve_published_substrate` 的 fail-closed 语义不得弱化。
本 spec 新增的删除侧让这条更关键 —— 改动前空 projection 最多「不更新」，
改动后空 projection 若被接受就是**清空整表**。⇒ Requirement 6.4 的测试必须同时断言
「返回 409」**和**「store 行数未变」两件事，只断言状态码不够。

---

## Testing Strategy

### 7.1 分层

| 层 | 目标 | 手段 |
| --- | --- | --- |
| 纯函数 | `compute_overwrite_plan` / `prune_undeclared_rows` 的语义 | 单测 + PBT（hypothesis，`max_examples=5`） |
| 执行层隔离 | OO 路径未被连带改变 | 源码锁 + 变异反证（J1/J2/J3/J5） |
| 端点级 | 鉴权 / 并发 / 状态码 / 信封 | **TestClient 真发 HTTP**，参照既有 `test_task28_sync_router_pg.py` 的注入形态：override `get_db` / `get_current_user` / `SR._services` |
| 真库口径 | dry_run 摘要与实际落库对账、快照 diff 成因判别 | 真实 PostgreSQL（🔴 SQLite 内存库测不出数据分布问题） |
| 真实链路 | 弹窗时序、包装体解包、重载 | Playwright |

### 7.2 🔴 端点级测试的两个既有坑（必须绕开）

1. **依赖工厂不能直接作 override 键**：`require_project_access("readonly")` 这类工厂
   每次调用返回**新函数对象**，`dependency_overrides` 按它做键会静默失效、全部 401。
   本 router 用的是 `Depends(_services)` + 内层 `get_db` / `get_current_user`
   （现读确认：router docstring 明写 `get_current_user` 是唯一 401 产生点）⇒
   override 内层两个稳定函数对象即可让真实判定跑。
2. **采集阶段异常不得穿透**：既有 pg 测试的教训是 —— 穿透会让整个 module 变成
   collection ERROR，而 `-rf` 只列 FAILED 不列 ERROR ⇒ 定向变异看不到预期失败 ⇒ 误判 GREEN。
   新增 pg 测试须沿用「一次 `asyncio.run` 采集进快照 + 异常记录不穿透 +
   `test_no_phase_crashed_during_collection`」这一对做法。

### 7.3 变异证明清单（每条「结构性零」都要配）

| 结论 | 变异组 |
| --- | --- |
| 前端对 `adopt-substrate` 引用为 0 | 同扫描器对 `row-name-alignment` 命中非零 |
| prune 调用点恰 1 处 | 人为在测试夹具里加第二处 ⇒ 判据打红 |
| OO 路径删除侧无变化 | 同 `(base, projection)` 两模式结果不同（J3） |
| 跳过清单无失效条目 | 把一个 list-store item 塞进跳过白名单 ⇒ 判据打红 |
| 幽灵行门语义未变 | 探针用例 B（新行无名 ⇒ 剔除）与 E（已存在行清空 ⇒ 保留）都必须仍成立 |

### 7.4 PBT 配置

- 库：`hypothesis`（仓库既有）
- 🔴 `max_examples=5`（用户明确要求，禁默认 100）
- 每条 property test 一个测试函数，注释标
  `Feature: workpaper-sync-adopt-overwrite-and-refresh-source, Property N: <文本>`

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions
of a system—essentially, a formal statement about what the system should do. Properties serve
as the bridge between human-readable specifications and machine-verifiable correctness
guarantees.*

50 条 AC 经 prework 逐条分类后，得 **11** 条 property（其余归 EXAMPLE / EDGE_CASE /
INTEGRATION / SMOKE）。合并记录见「§ prework 合并记录」。

### Property 1: 声明侧行集等式

*For any* substrate projection 与任意 store 载荷，覆盖执行后每个 declared_table 在 store 侧的
受管行身份集合，应等于该 table 的 `row_keys` 集合**减去**被幽灵行门剔除的身份集合。

**Validates: Requirements 1.1, 1.3, 1.5**

### Property 2: 作用域外的行逐元素不变

*For any* store 载荷与任意 projection，凡不在本次收敛作用域内的行，其身份序列在覆盖前后逐元素
相等。作用域外包含两个维度，两者都必须成立：(a) `table_key` 不在 `row_keys` 键集合中的表；
(b) 同一载荷内不属本次 projection 声明分区的行。

**Validates: Requirements 1.2, 1.4**

### Property 3: 幽灵行门语义不变且被如实登记

*For any* 覆盖执行，凡本次新增且锚点业务名列为空的行身份，既不出现在结果行集中，也必定出现在
响应的 `rows_ghost_dropped` 清单中；而覆盖前已存在的行即使锚点为空也必定仍在结果行集中。

**Validates: Requirements 1.6**

### Property 4: Overwrite_Plan 内部自洽

*For any* Overwrite_Plan，四个计数分别等于其对应身份清单的长度，且
`rows_added` / `rows_deleted` / `rows_updated` 三个集合两两不相交。

**Validates: Requirements 1.7**

### Property 5: 模式二分（OO 不被连带改变）

*For any* 满足「base 独有身份非空」的 `(base, projection)` 组合，base 权威模式下这些身份全部
保留、substrate 权威模式下这些身份全部消失，且两模式的结果行集不相等。

**Validates: Requirements 2.1, 2.4**

### Property 6: plan_digest 顺序无关且内容敏感

*For any* Overwrite_Plan，随机置换其任意清单的元素顺序后 `plan_digest` 不变；
而修改其中任一行身份或任一计数后 `plan_digest` 必定改变。

**Validates: Requirements 3.3**

### Property 7: 应用计划后重算计划为空（收敛）

*For any* `(substrate projection, store 载荷)`，按 Overwrite_Plan 应用一次之后，以同一 substrate
projection 对新载荷重算 Overwrite_Plan，其 `rows_added` / `rows_deleted` / `rows_updated`
三个清单均为空。

**Validates: Requirements 3.8**

### Property 8: 不可枚举形态的载荷不被改动且被登记

*For any* 含不可枚举形态 store item（dict 形态 / 纯文本固定项）的输入，该 item 的载荷在删除侧
逐字节不变，且该 item 必定以 `(item_id, reason)` 形式出现在 `skipped_items` 清单中。

**Validates: Requirements 4.1**

### Property 9: 非法载荷一律 fail visible

*For any* 不可解析为行对象数组的 store 载荷（非法 JSON、JSON 对象、JSON 标量、含非对象元素的
数组），计划计算应抛出携带该 item_id 的错误，且不得把该 item 当成零行处理。

**Validates: Requirements 4.4**

### Property 10: 行身份识别与键名无关

*For any* 现算得到的行身份键名（现算 7 种：`rowId` / `id` / `rowKey` / `key` / `month` /
`metricName` / `rowUuid`），以该键名承载身份的载荷都应被正确枚举出全部行身份。

**Validates: Requirements 4.5**

### Property 11: 回滚快照可完整还原（round-trip）

*For any* `(store 载荷, substrate projection)`，执行覆盖后以 `rollback_snapshot` 还原，
还原结果应与覆盖前的原始载荷相等（含被删除的行）。

**Validates: Requirements 6.9**

### Property 12: 前端摘要与计划逐值相等

*For any* Overwrite_Plan 响应，Refresh_Source_Dialog 展示的两侧行数与增 / 删 / 改条数应与响应中
对应字段逐值相等（前端不得自行重算）。

**Validates: Requirements 5.3**

---

## prework 合并记录（消冗余的依据）

| 合并 | 理由 |
| --- | --- |
| 1.5 并入 P1 | 「集合相等」蕴含「缺失的必须被追加」，单列一条追加 property 是同文重复 |
| 1.3 降为 P1 的边界 | declared 为空 ⇒ 结果为空，由 P1 生成器覆盖；另配一个**显式对照单测**钉死「不在键集合」与「在键集合但空」行为不同 |
| 1.2 + 1.4 → P2 | 两者形态同构（作用域外不变），但代码路径不同（表级 vs 分区过滤）⇒ 合并为一条、参数化两维，避免两条几乎同文 |
| 2.1 + 2.4 → P5 | 2.4 是 2.1 的变异证明。若拆两条，2.1 可能因「删除侧根本没接」而假绿；合并后三个断言互为变异证明 |
| 3.3 两半 → P6 | 顺序无关与内容敏感是同一条 property 的两个断言 |
| P1 与 P3 不合并 | 🔴 有幽灵行时 P1 的裸「集合相等」**不成立** ⇒ P1 文本必须写成「减去幽灵剔除集」，P3 再单独断言剔除集非空的场景。不改 P1 表述就会得到两条互相矛盾的 property |
| P1 与 P7 不合并 | P1 说单次结果对，P7 说再跑不再有动作 —— 后者能抓「计数虚报 / 清单与落库脱钩」 |
| P4 与 P7 不合并 | P4 查 plan 内部自洽，P7 查 plan 与落库一致，是两个不同的脱钩面 |

🔴 **12 条 property 与「§ Correctness Properties」的条目数相等**（P1~P12；prework 初算 11，写作时把 5.3 也判为
property 后成 12 —— 计数与列举项数必须相等，此处已对齐）。

---

## ADR

### ADR-AOS-001：删除侧以「后置 prune」落地，OO 路径零改动

- **裁决**：方案 4（merge 之后剪枝），独立模块 `adopt_overwrite_plan.py`。
- **否决方案 1**（merge 加 mode 参数）：改 36 个门面签名、违反 Requirement 2.3；
  且 mode 落在 merge 内会诱导在「入参含其它分区行」的地方做全量差集，直接删兄弟分区。
- **否决方案 3**（前置清 base）：探针实证前置清空会让全表行变成「新增身份」⇒
  幽灵行门全面生效 ⇒ 意外改变既有语义（探针 B 与 E 两例是该结论的直接证据）。
- **部分采纳方案 2**：采纳「独立函数 + OO 零改动」，但不重造 provider 分发。
- **兜底**：若某形态确实取不到行枚举器且必须支持，退回给**引擎一家**（
  `phase5_row_table_sheet`）加 mode 参数，而不是 36 个门面。

### ADR-AOS-002：删除侧作用域 = declared_table ∩ 本 row_section

- 与 overlay 读方向、materialize 侧收敛构成**同一条规则的三处落地**：声明了才动，未声明不碰。
- 「不在键集合」与「在键集合但值为空」严格二分，沿用 overlay 既有 `in` vs `get` 裁决。
- 🔴 不使用百分比阈值闸。改用 `plan_digest` 逐条绑定 —— 阈值是拍脑袋数字，
  既误拦合法大批删除，也放过小批误删。

### ADR-AOS-003：dry_run 与真实执行共用同一计划纯函数

- 摘要可信不靠「两处算法算出同样的数」，靠**只有一处算法**。
- `changed_item_count` 改由 plan 供出，彻底移除对「覆盖前后 remark 快照差集」的依赖 ——
  上游登记的局限②由此从根上消失，无需先判明其归因即可解除；
  但归因仍须用真库查清并登记（Requirement 3.7），否则同型误判会在别处重演。

### ADR-AOS-004：弹窗选项集合 = 2 可执行 + 1 说明项

- 「以表单为准，覆盖在线编辑」不再置灰，也不新增执行入口：该方向已由 materialize 收敛
  真实实现，弹窗只把它**说清楚并指引**到「在线编辑」按钮。
- 否决「在弹窗里直接触发 materialize」：那会新增一条「不打开编辑器也创建 room/descriptor」
  的路径，属新增语义而非把既有行为显式化，超出本 spec 范围（登记为遗留②）。
