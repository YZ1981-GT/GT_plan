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

🔴 本表已于 **Task 1.1** 全量重算（锚点 = 工作树 HEAD `21e198121` + 未提交改动）。
口径一律 **AST**，不用文本匹配 —— 本轮正是靠这一条抓出下表第 6 行的整条误报。

| 事实 | 现算值 | 取法 |
| --- | --- | --- |
| `all_store_item_ids` 定义数 | **47**（🔴 波动值：已跟踪 HEAD 树 43 + 未跟踪新 provider 3 + 已跟踪文件未提交改动 1） | AST `FunctionDef` / `AsyncFunctionDef` 名等值，扫 `backend/app/services/workpaper_sync/**.py` 全量（含 `adapters/` 与 `pilot_*`）。🔴 旧记 **46** 已作废：它静默排除了 `pilot_d2_large_json.py`（排除 pilot 或只取 `phase5_*` 两种口径都恰得 46）；上游 spec 的 **47** 在本表声明的口径下**可复现** ⇒ 旧注记「本轮修正」本身是错的 |
| `merge_projection_into_store_rows` 定义数 | **36**（波动：已跟踪 HEAD 树 35） | 同上 AST 口径；与旧记录一致 |
| `iter_store_rows` 定义数 | **25**（已跟踪 HEAD 树亦 25，本表唯一稳定项） | 同上 AST 口径（引擎 1 + 薄转发若干）；与旧记录一致 |
| `ROW_IDENTITY_STORE_KEY*` 赋值处 | **119 处 / 112 文件** | AST `AnnAssign` / `Assign` 且目标名以 `ROW_IDENTITY_STORE_KEY` 起。只扫 workpaper_sync 与扫 `backend/app` 全量**同值** ⇒ 该常量族不出 workpaper_sync，scope 已证不是误差源 |
| 行身份键字面量取值 | **7 种**：`rowId` 65 / `id` 29 / `rowKey` 5 / `key` 1 / `month` 1 / `metricName` 1 / `rowUuid` 1（合计 103；余 16 处 value 是 `ast.Attribute` = 跨模块引用常量，不产字面量）。对账 **103 + 16 = 119 ✓** | 同上 AST，取 `ast.Constant[str]`；与旧记录逐值一致，等式仍成立 |
| `row_section_field=` 非空**字面量** | **0 处**（🔴 旧记「7 处 / 6 文件」全为误报 —— 那 7 处经 tokenize 判别**无一处是可执行代码**：5 处在 docstring / 散文字符串，2 处在 `#` 注释） | 复现旧口径正则 `row_section_field=["'][^"'\\]` 得**恰 7 处 / 6 文件、文件名逐个相同** ⇒ 差异归因于口径而非树变化。这是平台铁律㉖的又一例：文本匹配被 docstring 骗过 |
| 引擎**功能**声明点（= 多分区 store item 数，Requirement 1.4 的真实分母） | **6 处 / 6 文件**：`phase5_g1_02_detail` / `phase5_g3_02_detail` / `phase5_g4_02_main_detail` / `phase5_g5_02_balance_detail` / `phase5_g6_02_main_detail` / `phase5_g9_02_detail`，值分别 `acctClass` / `agingCategory` / `maturityCategory` / `sectionKey` / `maturityCategory` / `section` | AST 穷举四形态（Call kwarg / AnnAssign / Attribute assign / dict 键）。🔴 这 6 处的 value 是 `ast.Name`（`ROW_SECTION_FIELD_G{102,302,402,502,602,902}`）**不是字面量** ⇒ 任何「只认字面量」的口径都会把全部真声明漏掉。全形态对账：**12 = 6 kwarg + 1 引擎默认 `""` + 5 合同清单描述性 dict 键** |
| 前端对 `adopt-substrate` 的引用 | **0**（扫 7451 个文件，0 解码失败） | 扫 `audit-platform/frontend/src/**` 的 `.vue/.ts/.js/.tsx/.jsx`（排除 `node_modules`）。**变异证明**：同一扫描器对 `row-name-alignment` 在 `GtWpRenderer.vue` 命中 **7**、全前端 **31 处 / 8 文件** ⇒ 该零值不是扫描器失效 |
| 后端对 `adopt-substrate` 的测试引用 | **4 处 / 3 文件**，但经 tokenize 判注释后**可执行代码仅 1 处**（`test_task28_sync_router.py` 的路由清单字面量 `("POST", "/adopt-substrate")`）；其余 3 处是注释（同文件 1 处 + `test_d2_store_value_equivalence` 1 处 + `test_d4_mirror_shape_invariants` 1 处） | 扫 `backend/**/*.py`：生产侧 4 处（router / `adopt_substrate_response` / `oo_to_html` / `store_mirror`），测试侧按 `test_*` 与 `/tests/` 归集。🔴 旧记「2 处，全在 `test_task28_sync_router.py`」两项均不准，但**结论不变且更强：无任何端点级行为测试** |

🔴 行身份键有 **7 种**取值（不是统一的 `rowId`）——
这一条直接否决「在通用层硬编码 `row.get("rowId")`」的任何实现。

🔴 **分区门的真实分母是 6 个 store item，不是旧表的 7**，且这 6 个的分区字段名**不统一**
（共 5 种取值：`acctClass` / `agingCategory` / `maturityCategory`（g4 与 g6 共用）/
`sectionKey` / `section`）
⇒ Requirement 1.4 的分区门与行身份键同理，**不得硬编码字段名**，必须取
`RowTableSheetSpec.row_section_field`。

🔴 **合同清单里的 `"row_section_field": "section"` 是描述性元数据，不是真源**：
5 处清单 dict 里 4 处与功能声明值不符（`phase5_g3_dividend_receivable` 写 `section` 而真值
`agingCategory`；g4 真值 `maturityCategory`；g5 真值 `sectionKey`；g6 真值 `maturityCategory`；
仅 g9 相符）。这是本 spec 范围外的既存漂移，**本轮只登记不修**。

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

解析器来源优先级（🔴 逐级现读确认，禁按命名习惯推）—— **三级**，裁决见 ADR-AOS-005：

1. **provider 门面**：provider 模块的 `iter_store_rows`（现算 **25** 个定义）——
   它已经做了「非数组即抛」「重复身份即抛」「分区过滤」三件事，正是 Requirement 4.4 要的；
   **降级条件**：L2~L4 任一级不成立（无门面 / 门面硬绑别的 item / 门面被借给别家 /
   门面覆盖面不全）⇒ 降到第 2 级。
2. **R3 兜底**：**全域 spec 索引** + 引擎 `phase5_row_table_sheet.iter_store_rows(spec, payload)`
   —— 绕开门面，直接用**本 item 自己的**行表 spec 逐条枚举（现算 **42** 条 item 有此路径）。
   仍是**声明驱动**（`RowTableSheetSpec.row_identity_key` / `row_section_field`），
   不是键名兜底。**降级条件**：全域索引里查不到本 item 的 spec，或引擎在合成载荷上探活不通过
   ⇒ 降到第 3 级。
   🔴 **两路都可用时门面优先、R3 兜底**，并须对这类 item 做**一致性对账**：同一载荷经两路枚举
   出的身份集合必须相等，不等即 fail visible（防「换了条路悄悄换了语义」）。详见 ADR-AOS-005。
   🔴 R3 是**逐 spec 遍历**，因此必须按 `(store_item_id, row_section_value)` 去重 ——
   `D1-memo-rows` / `I5-2-rows` 各 2 个 spec 却无分区字段（§4.1b (4b)），不去重会把同一行数两次。
3. 两级都取不到 ⇒ 该 item **跳过删除侧**并进显式清单，`skipped_reason` 取**封闭枚举**
   `SkipReason`（已落地在 `backend/app/services/workpaper_sync/adopt_overwrite_plan.py`，
   Task 3.1 交付）中与真实成因对应的成员：`import_failed`（provider 模块 import 抛）/
   `absent`（import 成功但无 `iter_store_rows` 属性）/ `item_blind`（门面在但签名不认
   `store_item_id` ⇒ 硬绑别的 item）/ `item_unresolvable`（门面 item-aware 但喂本 item 即抛）/
   `row_reader_bound_to_other_entry`（门面 re-export 自别家、被借给别的 entry，见 §4.1b (6)）/
   `no_store_item`（adapter 级根本没有 store item 可谈）。
   🔴 **原因必须按真实成因分桶，禁粗粒度兜底**：§4.1b (4) 交叉核实测，判为不可枚举但注册表
   `StoreItemSpec.kind` 明写 `rows` 的条目有 **18** 条（B 分母 ｜ A 分母 **19**）⇒ 把它们一律
   登记成「没有行读取器」这一个粗原因，就是**失效的白名单条目**，Requirement 4.3 的
   「白名单无失效条目」判据会打红。
   🔴 该域**封闭**，域外取值由 `OverwritePlanShapeError` 当场拒收；**新增成员必须同时更新
   Requirement 4.3 的白名单校验（Task 4.8）**，否则等于开了个后门。
   🔴 载荷**不可解析**不在本域内 —— 非法 JSON / JSON 对象 / JSON 标量 / 含非对象元素的数组按
   Requirement 4.4 fail visible（`AdoptStorePayloadUnreadableError`，Task 6.2），不得降级成「跳过」。
4. 🔴 **不**自造 `row.get("rowId")` 兜底 —— 行身份键现算 **7** 种取值，兜底必错。
   （这条是 Requirement 4.5，与 R3 无关：R3 的身份键同样取自**声明**而非字面量。）

### 4.1b store item 行枚举器可用性普查（Task 1.2 现算）

🔴 全部为**现算值**（探针真 `importlib` + 真调门面 + 消费生成器），禁写死；交付时须重算。

#### (0) 分母有**两条**，不是一条 —— 先把这件事说清楚

任务书写「按 `store_item_registry` 找 provider 模块」，但**adopt 真实走的不是它**：
`adopt_substrate_response._store_item_ids` → `store_projection_response.resolve_store_projection_provider`
→ `adapters/registry.DELIVERED_PER_ENTRY_CONTRACTS`。两份映射现算对账：

| 对账项 | 现算 |
| --- | --- |
| A `STORE_MERGE_REGISTRY` 的 adapter 数 | **42** |
| B `DELIVERED_PER_ENTRY_CONTRACTS` 的 adapter 数 | **51** |
| 只在 A | **0 个** |
| 只在 B | **9 个**：`a51.cashflow_audit` / `c2.control_test_summary` / `i1`~`i6` / `j1.accrual_check_short_term`（⇒ 这 9 条走 OO 镜像会撞 `store_merge_plan_or_skip` 的「像 adapter_id 却未注册 ⇒ 抛错」分支） |
| 同 adapter 但 provider 模块**不一致** | **1 个**：`d2.receivable_detail`（A=`d2_bidirectional_bridge` ｜ B=`pilot_d2_large_json`）⇒ 两侧取到的 store item 清单一个 **1** 条、一个 **10** 条 |
| item 集合关系 | A 的 113 条 **⊂** B 的 129 条（B 多 16 条 = D2 多出的 9 + I1~I6 的 6 + J1 的 1） |

⇒ Requirement 4.1 的跳过集合基线**以 B 为准**（那是 adopt 真实枚举的集合），A 一并给出以满足任务书口径。

#### (1) 判定链（逐级现读，每级都有变异对照）

| 级 | 问题 | 判为 |
| --- | --- | --- |
| L1 | provider 模块能 `importlib.import_module` 吗 | 不能 ⇒ `import_failed`（**缺陷，要修**） |
| L2 | 该模块暴露 `iter_store_rows` 属性吗（含 re-export） | 没有 ⇒ `absent` |
| L3 | 门面签名认 `store_item_id` 吗 | 认 ⇒ 只认「显式传本 item」这一种调法；不认 ⇒ `item_blind`，只对「门面**定义模块**的 `STORE_ITEM_ID`」那一个 item 有效 |
| L4 | 真调 + **消费生成器** + 正面判据 | 合成 1 行必须真 yield 出那个身份，才判 `enumerable` |

🔴 L3 的「不回退」是**修出来的**：探针 v1 在 item-aware 调法失败后回退到不传
`store_item_id` 的调法，而那条调法会落到门面定义模块自己的 `STORE_ITEM_ID`
⇒ **任何假 item_id 都判可枚举**。v1 自带的变异对照第 4 条把它打红后才改成两分。
🔴 L4 的「消费生成器」也是必需的：G 循环那几家的 `iter_store_rows` 是 `yield from`
生成器函数，`specs_for` 的抛错发生在**第一次迭代**而不是调用时 ⇒ 只调不 `list()` 会全判通过。

#### (2) 清单一：可枚举（B 分母 **25** 条 ｜ A 分母 **24** 条）

两个分母只差 `d2.receivable_detail / D2-detail-rows` 一条（A 把 D2 指到没有门面的
`d2_bidirectional_bridge`）。B 的 25 条按 adapter：

| adapter | 可枚举 item | 门面形态 |
| --- | --- | --- |
| `d4.revenue_detail` | `D4-2-rows` | item-blind 但**硬绑的正是它** |
| `d2.receivable_detail` | `D2-detail-rows` | 同上（`pilot_d2_large_json`） |
| `h1.disposal_check` | `H1-8-rows` | 同上（`pilot_h1_grouped_dynamic`） |
| `e1` / `h3` / `h7` 各 2 条 | `E1-cash-detail-rows`+`E1-digital-rows`、`H3-2-cost-rows`+`H3-2-fair-rows`、`H7-2-cost-rows`+`H7-2-fair-rows` | item-aware 薄转发框架层引擎 |
| `g1` `g2` `g8` `g9` `g10` `g11` `g12` `g13` `g14` `h2` `h4` `h5` `h6` `h8` `h9` `h10` 各 1 条 | `G1-2-rows` `G2-2-detail-rows` `G8-detail-rows` `G9-detail-rows` `G10-detail-rows` `G11-detail-rows` `G12-hedge-detail-rows` `G13-detail-skeleton` `G14-detail-rows` `H2-2-rows` `H4-2-rows` `H5-2-rows` `H6-2-rows` `H8-2-rows` `H9-2-rows` `H10-adjustment-rows` | item-aware 薄转发框架层引擎 |

逐项对账：`3（item-blind 硬绑本 item）+ 6（三家各 2 条）+ 16（各 1 条）= 25` ✅
**25 条全部通过正面合成判据**（合成 1 行 → 恰 yield 1 条、身份等于合成值、元组元数 2）。
⇒ `RowReader.iter_rows` 直接适配这 25 条即可，**无需**任何键名兜底。

#### (3) 清单二：不可枚举（B 分母 **104** 条 ｜ A 分母 **89** 条）—— 按原因分桶

🔴 「import 失败」与「本来就没有」**严格分开**，这是本任务的核心纪律：

| 原因桶 | B | A | 性质 | 处置 |
| --- | --- | --- | --- | --- |
| `import_failed`（provider 模块 import 抛） | **0** | **0** | 缺陷 | 空桶（配变异证明，见 (5)） |
| `absent`（import 成功但无 `iter_store_rows` 属性） | **46** | **40** | 多数是欠门面，不是形态使然 | 见 (4) 再分 |
| `item_blind`（门面在，签名无 `store_item_id` ⇒ 硬绑别的 item） | **54** | **45** | 混合 | 见 (4) 再分 |
| `item_unresolvable`（门面 item-aware，喂本 item 即抛） | **4** | **4** | 🔴 真缺陷 | 见 (6) 立案 |
| `no_store_item`（adapter 级，无 item 可谈） | **2** | 0 | 无 store 面 | `a51.cashflow_audit` / `c2.control_test_summary` |

**条数对账（显式）**：B 分母 `25 + 104 + 2 = 131` 行，其中 item 行 `25 + 104 = 129`，
等于逐 adapter 求和的 129（去重后仍 129，无跨 adapter 重名）✅；
A 分母 `24 + 89 + 0 = 113`，等于逐 adapter 求和的 113（去重后仍 113）✅；
A 的 item 集合 ⊂ B 的 item 集合（差 16 条）✅

#### (4) 🔴 跳过原因**不能一律写 `no_row_reader`** —— 交叉核发现 19 条其实是行数组

交叉核：判为不可枚举、但注册表 `StoreItemSpec.kind` 明写 **`rows`** 的条目 —— A 分母 **19** 条 / B 分母 **18** 条
（差的 1 条是 D2 那个 provider 不一致项）。把它们登记成
「载荷不是可按行身份枚举的行数组」就是**失效的白名单条目**（Requirement 4.3 会打红）。

再往下查「全域有没有替代路径」（R1 别的模块的 item-aware 门面认它 / R2 别的模块的 item-blind 门面硬绑它 /
R3 全域有它的行表 spec ⇒ 引擎 `iter_store_rows(spec, payload)` 走得通）：

| 分组 | B 条数 | 事实 |
| --- | --- | --- |
| 有替代路径 | **42** | 全部是 R3（引擎 + spec）；R1 **0 命中**（门面都是 entry-bound）、R2 **1 命中**（仅 A 分母的 D2） |
| 无替代路径 | **62** | 见下 |

有替代路径的 42 条按 adapter：`d1` **17** · `f3` 5 · `f2.stocktake_bundle` 2 · `f5` 2 ·
`f1` `f2.inventory_main` `f2.inventory_special` `f2.inventory_valuation` `f4` `g3` `g4` `g5` `g6`
`i1` `i2` `i3` `i4` `i5` `i6` `j1` 各 1。
🔴 其中 D1 的 17 条 spec 住在**伴生模块** `phase5_d1_expansion`（registry 指向的
`phase5_d1_notes_receivable` 没有 `managed_row_table_specs()`）—— 这正是「只看 registry 指定模块会假阴」
的实证，与平台铁律⑬「查已交付边界必须同时查伴生模块」同源。
🔴 R3 观测到的身份键现算只有 **3 种**：`rowId` / `id` / `rowKey`（另有 `key` 出现在 D1-cat-rows）——
与 design § Overview 的「7 种字面量」不矛盾（那是全仓常量取值域，这里是这 42 条的实际取值）。
🔴 分区维度在 R3 里**真实存在且跨度很大**：`g5.long_term_receivable_detail / G5-2-rows` 一个 store item
**12 个真分区**（`sectionKey` = `s1_/s2_/s3_ × finance_lease/installment_sale/installment_service/other`），
`g3.dividend_receivable_detail / G3-2-detail-rows` **2 个真分区**（`agingCategory`）
⇒ Requirement 1.4 的分区门不是理论风险。
🔴 另有 `I5-2-rows` / `D1-memo-rows` 各 **2 个 spec 但无分区字段** —— 那**不是**分区，
是下面 (4b) 登记的重复计数陷阱，两者不可混为一谈。

无替代路径的 62 条按 adapter：`d4` **45** · `d2` **9** · `b60` `d1` `d3` `d5` `d6` `d7` `g7` `l1` 各 1。
其中 D4 的 45 条按 provider **自己的常量**（`store_mirror` 正是按这些常量把它们从 rows 循环里排除的）再切：

| D4 子形态 | 条数 | item |
| --- | --- | --- |
| dict store | 5 | `D4-9-data` `D4-33-data` `D4-34-data` `D4-35-data` `D4-36-data` |
| list store | 1 | `D4-8-products` |
| 纯文本固定项 | 8 | `D4-5-biz-{scene,order,produce,sales,pricing,delivery}` + `D4-13-{process,conclusion}` |
| D4-7 专用块 | 2 | `D4-7-products` `D4-7-monthly` |
| 走 rows 循环 | 29 | 余下（`D4-2-rows` 是第 30 个，它可枚举） |

对账：`16 特殊形态 + 30 走 rows 循环 = 46 = all_store_item_ids()` ✅
⇒ **只有 16 条**（其中 45 条不可枚举里的 16 条）属「形态使然、可登记豁免」；另 **29** 条是
「走 rows 循环但门面 item-blind」。🔴 且 `store_mirror` 的注释明写 `D4-10`（`{rows,…}`）/
`D4-30`（`{customers,customDimensions}`）/ `D4-31`（singleton）三条的 base **可能是 dict**
⇒ 这 29 条里至少 3 条的真实形态需逐条确认后才能进豁免清单，不得按「在 rows 循环里」一概而论。

🔴 **D4 的 item-blind 门面为什么绝不能「凑合用」**：它硬绑 `STORE_ITEM_ID='D4-2-rows'` 且
写死 `ROW_IDENTITY_STORE_KEY='rowId'`，而同模块另有 7 个身份键常量，其中
`ROW_IDENTITY_STORE_KEY_D422='metricName'` · `_D423='month'` · `_D435='id'` ——
拿 `rowId` 去枚举 D4-22/D4-23/D4-35 会**取不到身份而抛错或错配**。
这是「禁自造 `row.get('rowId')` 兜底」这条裁决的**现场实证**，也是探针 v1 假阳的实际危害。

#### (4b) 分区维度的**运行时**分母 —— 与 § Overview 的「6 处声明点」是两个口径，不是偏差

§ Overview（Task 1.1）现算的是 **AST 声明点 6 处 / 6 文件**。本任务现算的是
**运行时真能枚举到的**分区 spec，两者可逐条对上：

| 类别 | 现算 | 明细 |
| --- | --- | --- |
| 声明了 `row_section_field` 的 store item（静态） | **6** | `G1-2-rows`(3 段/`acctClass`) · `G3-2-detail-rows`(2/`agingCategory`) · `G4-2-rows`(2/`maturityCategory`) · `G5-2-rows`(**12**/`sectionKey`) · `G6-2-rows`(2/`maturityCategory`) · `G9-detail-rows`(3/`section`) |
| 其中**当前运行时可达**（在 `all_store_item_ids()` 里） | **4** | G1 / G3 / G5 / G9 |
| 声明了但当前不可达 | **2** | `G4-2-rows` / `G6-2-rows` —— G4/G6 的 `managed_row_table_specs()` 现算只返 `('G4-7-items','')` / `('G6-5-fair-value-data','')`（灰度开关未开主明细表） |
| 🔴 **多 spec 共享一个 item 但无分区字段** | **2** | `D1-memo-rows`（`phase5_d1_expansion` 2 个 spec）· `I5-2-rows`（`phase5_i5_other_noncurrent_assets` 2 个 spec，其 `all_store_item_ids` docstring 明写「两个 spec 共享一个 item ⇒ 去重后长度为 1」） |
| 单 spec 却声明了分区字段 | **0** | 空集。变异对照 = **同一个扫描器、同一个字段**在「多 spec」侧命中 **4** 非零 ⇒ 这个 0 不是「没读到 `row_section_field`」 |

🔴 `D1-memo-rows` / `I5-2-rows` 这 2 条是 `prune` 的**重复计数陷阱**：逐 spec 调引擎枚举会把**同一行数两次**
（无 `row_section_field` ⇒ 引擎不过滤，两个 spec 都 yield 全表）。
⇒ Task 4.1 的分区门实现**必须按 `(store_item_id, row_section_value)` 去重**，
不能写成「for spec in specs: 累加」。这条不是推演，是上表两条实测样本。

#### (5) 变异证明（每条结论都配对照组，含**三个**空桶：`import_failed` 0 / R1 0 命中 / 单 spec 有分区字段 0）

| # | 对照组 | 期望 | 实得 |
| --- | --- | --- | --- |
| 1 | import 一个不存在的模块 | 检出 import 失败 | PASS（`import_failed` 桶为 0 是**真的 0**，不是探针瞎） |
| 2 | `store_mirror`（确无门面） | `absent` | PASS |
| 3 | `g10` + 真 item | `enumerable` | PASS |
| 4 | `g10` + 假 item `NOT-A-REAL-ITEM` | **不得** `enumerable` | PASS（v1 在此打红 ⇒ 修掉回退） |
| 5 | `d4` + 非绑定 item（`D4-10-data`） | `item_blind` | PASS |
| 6 | `d4` + 绑定 item（`D4-2-rows`） | 仍 `enumerable` | PASS |
| 7 | `g9` 合成 1 行 | 正面判据 True | PASS |
| 8 | 喂一行**不含任何身份键**的载荷 | 正面判据必须 False | PASS（引擎抛「缺少稳定行身份 'rowId'」⇒ 正面判据非恒真） |
| 9 | 把已判可枚举的真 item 冒充跳过项 | 判据识破 | PASS（Requirement 4.3 的反向变异雏形） |
| 10 | 全域 spec 索引查不存在的 item | 不命中 | PASS |
| 11 | 全域 spec 索引查 `G10-detail-rows` | 命中 | PASS |
| 12 | 引擎路判据对无 spec 清单的模块 | 判「不行」 | PASS |
| 13 | R1 全 0 命中（没有任何「别的模块的 item-aware 门面认外家 item」） | 同一段代码在**本家**门面上必须命中 | PASS（#3 即该对照：同一个 `_call` 在 g10 自家门面上 enumerable）⇒ R1 的 0 是「门面都 entry-bound」的事实，不是探针没调 |

另：全域扫 **264** 个模块建 spec 索引，**import/调用失败 0 个**，覆盖 **84** 个 store item ——
「import 失败 0」这个结论有 #1 与 #12 两条对照组撑着，不是「没查到就说没有」。

#### (6) 🔴 本次普查抓到的 **1 个真缺陷（4 条 item）**：G3/G4/G5/G6 的 store 门面被借给了 G9

`phase5_g3_dividend_receivable` / `phase5_g4_bond_investment` /
`phase5_g5_long_term_receivable` / `phase5_g6_other_bond` 四家的
`build_store_projection` / `merge_projection_into_store_rows` / `iter_store_rows` /
`split_store_payload_by_section` **四个门面全部 re-export 自 `phase5_g9_store_facade`**
（`__module__` 现算确认），而该模块的 `specs_for` 惰性取的是 **G9 主模块**：

```
phase5_g3_dividend_receivable.specs_for(None, None) -> ('G9-detail-rows',)×3
phase5_g4_bond_investment.specs_for(None, None)     -> ('G9-detail-rows',)×3
phase5_g5_long_term_receivable.specs_for(None, None)-> ('G9-detail-rows',)×3
phase5_g6_other_bond.specs_for(None, None)          -> ('G9-detail-rows',)×3
```

⇒ 两个观测面，**危害不同**：

1. 传 `store_item_id` 时（本普查的调法）**抛** `EntrySelectionError: store item 'G3-2-detail-rows'
   不在 G9 受管清单里` ⇒ 这 4 条落进 `item_unresolvable` 桶；
2. 🔴 **不**传 `store_item_id` 时（`store_mirror` 的真实调法就是
   `merge_rows_fn(projection=…, base_rows=…)`，不传）**不抛**，而是**静默按 G9 的 3 个 spec 合并** ——
   这是「像 D4-35 恒空那一族」的静默错配形态，不是本 spec 引入的。

本 spec **不修它**（Task 1.2 是纯普查，且它落在 OO 镜像共用路径上，属 Requirement 2 的
「不得连带改变」保护区）。处置：登记为**跨 spec 工单**，并在本 spec 内按 Requirement 4.1
把这 4 条放进跳过清单，原因写 `row_reader_bound_to_other_entry`（**不是**
`no_row_reader`，也**不是**形态使然）。它们的 R3 替代路径成立（各自模块的
`managed_row_table_specs()` 都有自己的 spec）⇒ 一旦工单修好即可转入可枚举。

##### 🔴 Task 3.4 现算勘误：这 4 条的 item_id 有两个写错了

本节**原句不改**（§4.1b 是 Task 1.2 产出，历史结论 append-only），勘误另记于此。

| | 本节原写法 | Task 3.4 现算更正值 |
| --- | --- | --- |
| G3 | `G3-2-detail-rows` | `G3-2-detail-rows`（无误） |
| G4 | **`G4-2-rows`** | **`G4-7-items`** |
| G5 | `G5-2-rows` | `G5-2-rows`（无误） |
| G6 | **`G6-2-rows`** | **`G6-5-fair-value-data`** |

依据 = **与同文件 §(4b) 一致**：§(4b) 已现算登记「g4/g6 的 `managed_row_table_specs()` 现算只返
`('G4-7-items','')` / `('G6-5-fair-value-data','')`（灰度开关未开主明细表）」
⇒ `G4-2-rows` / `G6-2-rows` 这两个 item 当前**运行时不可达**，adopt 真实路径上落进
`row_reader_bound_to_other_entry` 桶的是 g4/g6 **当前可达的那一条**。

⇒ 即 §(6) 与 §(4b) 此前**自相矛盾**，本次以 §(4b) 与 Task 3.4 的现算为准。
受影响的下游表述：ADR-AOS-005 第 2 条列举的 4 条 item 用的是更正值
（`G3-2-detail-rows` / `G4-7-items` / `G5-2-rows` / `G6-5-fair-value-data`）。
🔴 这 4 条**落进哪个桶**、以及「门面 re-export 自 `phase5_g9_store_facade` ⇒ 门面路无解」
这个**归因**均不受勘误影响 —— 错的只是 item_id 字面值。

#### (7) 交付给后续任务的结论

1. Requirement 4.1 的跳过集合基线 = **B 分母的 104 条**，且**必须按四个原因桶分别登记**，
   其中只有 **16 条 D4 特殊形态 + 1 条 G7 state store = 17 条**现有证据支持「形态使然」豁免；
2. 其余 **87** 条（104 − 17）属**能力缺口**而非形态使然，**其中 42 条已有 R3 替代路径**
   （引擎 + 全域 spec，仍是声明驱动，不是键名兜底）⇒ Task 3.4 的 `RowReader`
   若采纳 R3 作第 2 优先级，跳过清单可从 104 缩到 **62**；采不采由 design 裁决，本任务只给事实。
   三层对账：`104 = 42（有 R3）+ 62（无 R3）`，而 `62 = 17（形态使然候选）+ 45（缺口且暂无替代）`，
   缺口合计 `42 + 45 = 87` ✅；
3. Task 4.8「跳过白名单无失效条目」的判据**必须逐条核原因类型**，不能只核「是否取不到门面」——
   否则 19 条 `kind=rows` 的条目会带着错误原因通过；
4. 🔴 Requirement 4.5 的「不依赖硬编码键名」有了现场反例：D4 同一模块 **8** 个身份键常量、
   **4** 种取值（`rowId` ×5 / `metricName` / `month` / `id`），拿一个键套全部 item 必错；
5. 🔴 Requirement 1.4 的分区门有两个必须同时处理的形态（见 (4b)）：**4** 个运行时可达的真分区
   store item（最多 12 段）+ **2** 个「多 spec 无分区字段」⇒ 后者要求按
   `(store_item_id, row_section_value)` 去重，否则同一行被数两次。

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
  "skipped_items": [["D4-10-data", "item_blind"]]
}
```

🔴 `skipped_reason` 与 `skipped_items` 第二位的取值域 = **封闭枚举** `SkipReason`
（已落地在 `backend/app/services/workpaper_sync/adopt_overwrite_plan.py`，Task 3.1 交付）：
`import_failed` / `absent` / `item_blind` / `item_unresolvable` /
`row_reader_bound_to_other_entry` / `no_store_item` —— 域外取值由 `OverwritePlanShapeError`
当场拒收，**禁自由字符串、更禁粗粒度兜底**（原因必须按真实成因分桶，理由见 §4.1b (4)：
判为不可枚举但 `kind` 明写 `rows` 的条目有 **18** 条，粗原因会让它们全成为失效的白名单条目）。
示例里 `D4-10-data` 取 `item_blind` 的依据 = §4.1b (5) 变异证明第 **5** 行
（`d4` + 非绑定 item `D4-10-data` ⇒ 期望 `item_blind`，实得 PASS）：D4 的门面硬绑
`STORE_ITEM_ID='D4-2-rows'`、签名不认 `store_item_id`。
🔴 **新增成员必须同时更新 Requirement 4.3 的白名单校验（Task 4.8）** —— 那条判据是
「逐条核原因类型」而不是「是否取不到门面」，新原因没进校验表就等于开了个后门。

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

50 条 AC 经 prework 逐条分类后得 property（其余归 EXAMPLE / EDGE_CASE / INTEGRATION /
SMOKE）：**prework 初算 11，写作时把 5.3 也判为 property 后为 12**（P1~P12，与下文
「§ prework 合并记录」末尾的对齐说明一致）。合并记录见「§ prework 合并记录」。

### Property 1: 声明侧行集等式

*For any* substrate projection 与任意 store 载荷，覆盖执行后每个 declared_table 在 store 侧的
受管行身份集合，应等于该 table 的 `row_keys` 集合**减去**被观测到并经 `ghost_dropped_by_item`
回喂的幽灵身份集合。

🔴 **计划期该集合恒空**：幽灵行门的三个输入（`spec` + `managed_field_specs` 锚点 / merge
**之后**的行 / merge 私有的两处 `continue`）无一出现在 `compute_overwrite_plan` 的输入面上
⇒ 等式在计划期退化为 `row_keys == rows_added ∪ rows_updated`。非空场景由 Task 6.3 在
**落库后**按「`plan.rows_added` − merge 后真实存在的身份」观测得出，再经 `ghost_dropped_by_item`
回喂，连带约束 **`rows_ghost_dropped ⊆ rows_added`**。🔴 刻意**不**在计划期预测幽灵集 ——
预测即第二真源，与 merge 的实际行为一漂就在测两件不同的事。

**Validates: Requirements 1.1, 1.3, 1.5**

### Property 2: 作用域外的行逐元素不变

*For any* store 载荷与任意 projection，凡不在本次收敛作用域内的行，其身份序列在覆盖前后逐元素
相等。作用域外包含两个维度，两者都必须成立：(a) `table_key` 不在 `row_keys` 键集合中的表；
(b) 同一载荷内不属本次 projection 声明分区的行 —— 含**两类**：**兄弟分区**（有 spec、
`section_of` 判得出，但其 table 不在 `row_keys`）与**未被任何 spec 覆盖因而读不到的分区值**。
🔴 后一类才是「按 `reader.iter_rows` 重建载荷」这类实现错误唯一能被打红的地方（实测 M4 变异
仅凭此类见红）⇒ 只造兄弟分区的生成器会让 (b) 维假绿。

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
| P1 与 P3 不合并 | 🔴 有幽灵行时 P1 的裸「集合相等」**不成立** ⇒ P1 文本必须写成「减去幽灵剔除集」，P3 再单独断言剔除集非空的场景。不改 P1 表述就会得到两条互相矛盾的 property。🔴 **两条的边界**：P1 只管**等式**（计划期幽灵集恒空 ⇒ 退化为裸并集相等），P3 只管**门的语义 + 如实登记**（新增且锚点为空的行既不出现在结果行集、又必出现在 `rows_ghost_dropped`；且覆盖前已存在的空锚点行**必须仍在**）—— P1 不断言登记清单的内容，P3 不断言行集等式，两者互不蕴含，故都不可省 |
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

### ADR-AOS-003 附注：`changed_item_count` 报 0 成因的真库判别（Task 2 现算）

**裁决：成因是 B「`applied <= 0 and base_rows` ⇒ 跳过写库」，不是 A「同事务快照读不到
未提交写」。** 上游 `workpaper-sync-managed-row-convergence` §更正 3 局限②的归因 A
**被真库实测否证**，不得沿用。

判别在真实 PostgreSQL 16.14（`audit_platform`；现算 `checklist_responses` 1,034,740 行、
`working_paper` 2,813 行 ⇒ 分母非空，不是空表假零）上做。四组场景全部**真调生产函数**
（`adopt_substrate_response._snapshot_store` / `._diff_snapshots` /
`store_mirror.mirror_projection_into_store` / provider 的
`merge_projection_into_store_rows`），载体 = `b60.hour_budget`（单 item rows 形态）。

#### 观测手段与其变异证明

只看「after == before」**无法**区分「写了读不到」与「根本没写」⇒ 另挂
`before_cursor_execute` 事件做 **SQL 录音机**，直接观测有没有写语句发到
`checklist_responses`。这是区分 A/B 的决定性仪器。

🔴 仪器变异证明（组 c）：同一 session 内发一条**未提交**裸 UPDATE（rowcount = 1）后再调
`_snapshot_store` —— 快照**看得见**（diff 非空）⇒ 组 b 的「after == before」不是仪器瞎了。

#### 四组实测（逐值）

| 组 | base（store 侧） | projection | `applied` | mirror 发出的写 | after vs before（remark 摘要前 16） | `changed_item_count` |
| --- | --- | --- | --- | --- | --- | --- |
| a0 空 base | 该 item 无行 | r1 + r2（均有姓名） | 3 | `UPDATE`(rowcount 0) → `INSERT` | `null` → `31d11547b4368650` | **1** |
| a 内容不同 | `[r1 grade=A]` | r1.grade=B + 新增 r2 | **3** | `UPDATE` 1 条 | `12ebef5e0ff96aad` → `73832e495acc3ddf` | **1** |
| b 内容相同 | `[r1 grade=A]` | r1 逐字段等于 base | **0** | **零条** | `12ebef5e0ff96aad` → `12ebef5e0ff96aad` | **0** |
| c 仪器对照 | `[r1 grade=A]` | 不调 mirror，发未提交裸 UPDATE | — | `UPDATE` 1 条（rowcount 1） | `12ebef5e0ff96aad` → `cb72e4f9f0680424` | 1 |

- **A 被否证**：组 a 与 a0 证明**未提交的 UPDATE 与 INSERT 都对 after 快照可见**
  （同 session / 同事务 / 同连接，`commit=False`）。
- **B 成立**：组 b 直接测到 `applied == 0`（`visited == 2`、`touched_rows == []`）且
  `base_rows` 非空 ⇒ 判定式 `applied <= 0 and base_rows` 逐字复算为 `True` ⇒
  `store_mirror` 在 UPSERT 之前 `return`，**一条写都没发** ⇒ 报 0 是对当次执行的**如实**描述。

#### 第三候选成因已排除

「`_snapshot_store` 的 item 清单为空 ⇒ diff 恒空 ⇒ 也报 0」同样能解释现象，故一并查：
逐 adapter 走生产解析链（`resolve_store_projection_provider` → `all_store_item_ids()` 或回退
`STORE_ITEM_ID`，与 `_store_item_ids` 逐字同构）现算 **42** 个 adapter，
`item_count == 0` 的有 **0** 个；上游观测到报 0 的那次用的 `d4.revenue_detail` 现算 **46** 个
item（`b60.hour_budget` 为 1）⇒ 分母不空，该候选不成立。

#### 跳过写库的出口不止一处

`store_mirror.py`（现算 519 行）内 `applied <= 0` 判定点现算 **7** 处，构成 **6** 个跳过出口
（`return` 2 + `continue` 4），横跨 3 个函数：

| 函数 | 判定式 | 出口 |
| --- | --- | --- |
| `mirror_projection_into_store`（state 形态） | `applied <= 0 and base_state` | `return` |
| `mirror_projection_into_store`（rows 形态） | `applied <= 0 and base_rows` | `return` ← **本次实测命中的是这条** |
| `_mirror_dedicated_dict_stores` | `applied <= 0 and base_state` 或 `… is not None`（按 `base_kind` 二分，两个判定点一个出口） | `continue` |
| `_mirror_dual_stores` | `applied <= 0 and base_rows` | `continue` |
| `_mirror_dual_stores` | `applied <= 0 and not merged_rows` | `continue` |
| `_mirror_dual_stores`（D4-7 专用块） | `applied <= 0 and d47_base.get(item_id) is not None` | `continue` |

🔴 **实证范围如实声明**：A 的否证与分支无关（同事务可见性是 session/事务性质，不因走哪条
mirror 分支而变）⇒ 普适成立。B 是在 rows 形态那条出口上**真执行**实证的；上游观测到 0 的
D4 走 `_mirror_dual_stores`，其判定式与本次命中那条**逐字同型**（见上表），但**未**用真 D4
artifact 复现 —— 这是源码同型判断，不是执行实证。

#### 副产物：`changed_item_count` 两个方向都不可信（虚报也成立）

`_diff_snapshots` 比的是 **`remark` 字符串**；`store_mirror` 写回一律
`json.dumps(..., ensure_ascii=False)`（带空格分隔符），而前端 `JSON.stringify` 写的是**紧凑**
形态。真库取最大的 200 条 JSON 载荷现算：`json.dumps(json.loads(remark), ensure_ascii=False)
== remark` 仅 **45** 条成立、**155** 条漂移（不可解析 **0** 条）—— 例如 `K8-6-rows` 存
195,960 字节、重序列化成 214,731 字节。⇒ 只要一次 adopt 的 `applied > 0`，即便语义零净变化，
也会写回一个**重新序列化**的字符串，字符串差集必报该 item 变了。

复现一例：projection 新增一个无姓名身份（被幽灵行门剔除）⇒ `applied = 1`、`merged == base`
（语义相等）、跳过判定式为 `False` ⇒ 写回 `[{"rowUuid": "r1", …}]`，而库里存的是
`[{"rowUuid":"r1",…}]` ⇒ 差集报「变了」。

⇒ 对 ADR-AOS-003 的支撑因此**不是**「归因错了、要改读取时机」，而是**这个观测量本身就不该
用**：它同时会漏报（本次实测的 B）与虚报（序列化漂移）。`changed_item_count` 改由 plan 供出
后，两个方向的失真一起消失。

#### 真库操作纪律与复原 verify

持久写入**仅 1 行**（靶点 wp 的 `B60-1-hour-budget-rows`，先验现算不存在；载荷内嵌
`_AOS_TASK2_PROBE` 标记）；三组 adopt 形态实验全程单事务并 `rollback()`；已存在的另一条 B60
store 行只读校验、未触碰。收尾 DELETE 后以独立只读探针对账先验值，五项全绿：靶点该 item
行数回 **0**、靶点 checklist 行数回 **1**、全库该 item 行数回 **1**、`_AOS_TASK2_PROBE` 残留
**0** 行、原有那条 B60 行的 md5 / 长度 / `updated_at` 逐值不变。

#### 同型误判的可迁移纪律

1. **「差集为 0」必须先区分「没写」与「写了读不到」** —— 两者处置相反（前者说明报 0 正确，
   后者要改读取时机）；只看前后快照无法区分，须另挂一条**独立通路**（本次是 SQL 录音机）。
   与「读出为空先排除解析失败」同源。
2. **观测仪器必须配变异证明** —— 组 c 用一条未提交裸 UPDATE 证明快照看得见未提交写；
   没有这一组，「after == before」可能只是仪器瞎了。
3. **候选成因要穷举到「分母为空」这一类** —— 第三候选（item 清单为空）与前两个候选现象
   完全一样，不查就会在「二选一」里选出一个错答案。
4. **未经实证的归因不得沿用** —— 上游把 A 写进已封板文档，本轮实测为假；沿用它会去改
   `_snapshot_store` 的读取时机，那是修一个不存在的 bug。

### ADR-AOS-004：弹窗选项集合 = 2 可执行 + 1 说明项

- 「以表单为准，覆盖在线编辑」不再置灰，也不新增执行入口：该方向已由 materialize 收敛
  真实实现，弹窗只把它**说清楚并指引**到「在线编辑」按钮。
- 否决「在弹窗里直接触发 materialize」：那会新增一条「不打开编辑器也创建 room/descriptor」
  的路径，属新增语义而非把既有行为显式化，超出本 spec 范围（登记为遗留②）。

### ADR-AOS-005：采纳 R3 替代路径，解析器来源优先级扩为三级

**背景**：Task 3.4 交付时报出一个 `SkipReason` 封闭域装不下的新缺陷
（`RowReaderResolution.is_unruled_shape`，现算恰 1 例 = `G1-2-rows`），并给出两条出路。
**用户裁决：采纳 (b)，即本 ADR。**

#### 1. 裁决：优先级从两级扩为三级

| 级 | 来源 | 降级条件 |
| --- | --- | --- |
| ① | **provider 门面** `iter_store_rows`（现算 **25** 个定义） | L2~L4 任一级不成立 ⇒ 降 ② |
| ② | 🆕 **R3**：全域 spec 索引 + 引擎 `phase5_row_table_sheet.iter_store_rows(spec, payload)` | 索引里无本 item 的 spec，或引擎在合成载荷上探活不通过 ⇒ 降 ③ |
| ③ | **跳过删除侧** + 登记 `SkipReason`（封闭域，六成员不变） | —— 终态 |

🔴 **三级里不设 R1 / R2**，理由是现算：R1（别家 item-aware 门面认外家 item）**0 命中**
且该 0 配了变异证明（§4.1b (5) 第 **13** 行：同一段 `_call` 在**本家**门面上必须命中，
实得 PASS ⇒ 0 是「门面都 entry-bound」的事实而非探针没调）；R2（别家 item-blind 门面硬绑它）
现算 **1 命中**且只在 A 分母的 D2 上成立，而 adopt 真实枚举走的是 B 分母（§4.1b (0)）
⇒ 为 1 条非真实路径的命中引入第四级不划算。

#### 2. 为什么需要它 —— 两个门面路**解不了**的问题

**(a) `G1-2-rows` 覆盖不全（1 条）**：G1 声明 **3** 段（`acctClass` =
`trading` / `classified_fvpl` / `designated_fvpl`，`table_key` = `g1_2_rows_r1/r2/r3`），
而它的门面是**单 spec 薄转发**（`_spec_of_store_item(store_item_id or STORE_ITEM_ID)` 取**首个**
匹配 spec），实测只 yield 第 ① 段，第 ②③ 段**无从寻址**（门面无 `section` 参数）。
R3 按 spec 逐条枚举 ⇒ 3 段都能寻址。
🔴 **不修的危害**：substrate 侧 `row_keys` 含全部三个 table，store 侧只读到 r1 ⇒
r2/r3 的**既有行会被算成 `rows_added`**，而 merge 走同一个单 spec 门面、同样只处理 r1、
**根本不会去加** ⇒ **计划报了增删而落库没动，Requirement 3.8（dry_run 摘要 == 实际落库变更）
当场破**。

**(b) `row_reader_bound_to_other_entry` 4 条**：`G3-2-detail-rows` / `G4-7-items` /
`G5-2-rows` / `G6-5-fair-value-data`（item_id 取 §4.1b (6) 的 Task 3.4 勘误值）。
四家的门面**全部 re-export 自 `phase5_g9_store_facade`**（`__module__` 现算确认），
而该模块的 `specs_for` 惰性取 **G9 主模块** ⇒ 传本 item 即抛 `EntrySelectionError`
⇒ **门面路无解**（换调法只会落回 G9 的 spec，那是更坏的静默错配）。
R3 绕开门面、直接用**本 entry 自己的** `managed_row_table_specs()` ⇒ 故可解。

#### 3. 收益

跳过清单 **104 → 62**。
🔴 **现算值，禁写死，实施期（Task 3.7）须复算** —— 上游 §4.1b (7) 的三层对账为
`104 = 42（有 R3）+ 62（无 R3）`，采纳 R3 后这 42 条转入可枚举，故 62 是**预期值**而非承诺值：
真实可转入数取决于 Task 3.7 逐条探活的实得结果（探活不通过的仍留在跳过清单）。

#### 4. R3 的两个前置事实（Task 1.2 已现算，此处引用不重算）

1. 🔴 **全域 spec 索引不能只看 registry 指定模块**：有 R3 路径的 42 条里，**D1 的 17 条**
   spec 住在**伴生模块** `phase5_d1_expansion` —— registry 指向的
   `phase5_d1_notes_receivable` **没有** `managed_row_table_specs()`（现读确认：该文件存在、
   无此 def、但文内引用了 `phase5_d1_expansion`）⇒ 只扫 registry 指定模块会把这 17 条**假阴**。
   与平台铁律⑬「查已交付边界必须同时查伴生模块」同源。
2. **R3 覆盖面与身份键分布**：全域扫 **264** 个模块建索引、import/调用失败 **0** 个、
   覆盖 **84** 个 store item（该「0」有 §4.1b (5) 的 #1 与 #12 两条对照组撑着）；
   这 42 条实际观测到的身份键只 **3~4** 种（`rowId` / `id` / `rowKey`，另 `key` 出现在
   `D1-cat-rows`）—— 与 § Overview 的「全仓 7 种」不矛盾（一个是常量取值域，一个是这 42 条的
   实际取值）。分区维度在 R3 里**真实存在且跨度大**：`G5-2-rows` 一个 item **12** 个真分区、
   `G3-2-detail-rows` **2** 个。

#### 5. 风险与边界（🔴 逐条显式，不得省）

**(1) R3 绕开了 provider 门面 ⇒ 不再享有门面的任何额外校验。**
Requirement 4.4 仍然成立，依据是**引擎本身**已做四件事（§4.1b 已实证，本次现读复核
`phase5_row_table_sheet.iter_store_rows` 逐条确认）：非法 JSON 即抛
（`RowTableStorePayloadError: remark 不是合法 JSON`）· 非数组即抛（「必须是行对象数组…
不得静默当成零行」）· 元素非对象即抛 · 缺稳定行身份即抛（「不得退回数组下标作身份」）·
重复身份即抛。⇒ fail-visible 语义由引擎兜住，不因绕开门面而弱化。
🔴 但**「门面额外做的事」不等于零**：门面层还可能做 entry 级筛选与灰度开关判断
（`managed_row_table_specs()` 内有 manifest 判断）⇒ Task 3.7 **禁缓存 spec 清单**
（缓存会让「开关一开就多两段」被一次进程内的旧结论盖住）。

**(2) 🔴 R3 与门面路对同一 item 可能给出不同结果 ⇒ 必须裁定优先级并对账。**
裁定：**门面优先、R3 兜底**（门面是既有执行侧真源，merge 也走它 —— 若读侧改走 R3 而写侧仍走
门面，就会重演 (a) 那类「读写口径不等」）。
**并**要求 Task 3.7 对「两路都可用」的 item 做**一致性对账**：同一载荷经两路枚举出的
**身份集合必须相等**，不等即 **fail visible**（不得取并集、不得择一静默）。
这条是防「换了条路悄悄换了语义」—— 没有它，R3 就成了一个无人对账的第二真源。

**(3) 分区去重仍是调用方的活，且 R3 让这条更容易踩。**
`D1-memo-rows`（`phase5_d1_expansion` 2 个 spec）与 `I5-2-rows`
（`phase5_i5_other_noncurrent_assets` 2 个 spec）各有 **2 个 spec 但无 `row_section_field`**
⇒ 引擎不过滤、**两个 spec 都 yield 全表** ⇒ 逐 spec 枚举会把**同一行数两次**。
🔴 R3 **本来就是逐 spec 遍历**，因此这个陷阱从「Task 4.1 要小心」升级为「R3 的固有形态」：
Task 3.7 与 Task 4.1 都**必须**按 `(store_item_id, row_section_value)` 去重。
`_declared_scopes` 的去重只对 `(table_key, 分区)` 整对生效，**不替调用方兑现这条**
（该函数 docstring 已如此声明）。

**(4) 不擅自扩 `SkipReason`。** 本 ADR 走 R3 解题，故封闭域**六成员不变**
⇒ Requirement 4.3 的白名单校验（Task 4.8）无需为本 ADR 增项。
`is_unruled_shape` 的冻结集合应因 R3 而变为**空集**；🔴 若 Task 3.7 实测不为空，
**如实登记剩余条目与原因，不得为凑空集而放宽判据**。

#### 6. 否决出路 (a)：新增 `SkipReason.section_coverage_incomplete`

- 它把一个**可修的能力缺口写成永久豁免** —— G1 的 3 段不是「形态使然」，
  是门面少一个寻址参数；登记成豁免之后，Requirement 3.8 的破口就**合法化**了。
- 且 R3 的事实基础（**42** 条替代路径、全域 **264** 模块索引、D1 伴生模块陷阱）
  Task 1.2 **已经现算出来了**，不用它等于白查。
- 附带代价：新成员必须同时改 Task 4.8 的白名单校验（`SkipReason` docstring 的硬要求），
  即为「不修」付出与「修」相当的改动面。

🔴 **本 ADR 与已落地代码的一致性核查（现读 `adopt_row_reader.py` 624 行 / `adopt_overwrite_plan.py`）**：
`is_unruled_shape` 的 docstring 已把两条出路写成待裁决项并点名「②…后者能同时解掉这 1 条与
`row_reader_bound_to_other_entry` 的 4 条」⇒ 与本 ADR 的裁决**方向一致、无冲突**。
代码当前只实现第 ① 级（`_FacadeRowReader` 是 `RowReader` 的**唯一**实现），第 ② 级尚未实现
⇒ 这不是「代码与 ADR 不符」，而是 **Task 3.7 的待实现面**（本 ADR 即其权威依据）。
