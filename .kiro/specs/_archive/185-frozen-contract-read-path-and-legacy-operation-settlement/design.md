# 设计：冻结契约的读侧重建 + 遗留 operation 结算

## §0 结论先行

**问题不是数据丢失，是读路径缺失。** 冻结的旧契约在库里完好（definition 行 `approved`、
blob `published`、磁盘文件 352,678 B 在位），但**没有任何代码会按 `contract_slot_ref` 把
它读回来** —— 所有读侧入口都要求调用方先传一份 contract 进来，而调用方只能从 registry /
磁盘现取，于是恒得新契约、恒撞 `frozen_contract_digest_drift`。

修法 = **补一条读路径**（按冻结 slot 读回 + 复用既有 `parse_contract` 与 blob 读取），
并把读侧入口的默认值改成它。判据（`assert_frozen_contract_matches_bundle`）**一个字不改** ——
它是对的，缺的是它需要的输入。

## §1 现状实证

### 1.1 拒绝是正确的，但没有出口

`conflict_resolution.py` 的 `preview()`：

```python
canonical = await self._requests.read_operation(...)
app = await self._load_application(application_id)
bundle = await self._resolution.load_bundle_snapshot(app.definition_bundle_id)
assert_frozen_contract_matches_bundle(
    contract=contract,                                   # ← 调用方传进来的
    slot_digest=bundle.slots[BundleSlot.contract].slot_digest,
    where=f"conflict preview of application {application_id}",
)
```

`contract` 是 `preview()` 的**入参**。router 侧经 `_registration(svc, scope)` 取的是
**当前**注册的契约 ⇒ 只要契约改过一次，历史 operation 的预览就永久 422。

### 1.2 冻结契约完好（2026-11-15 共享库只读实测）

```
operation 11809f53-… / state=conflict / bundle 1504768f-…
  contract_slot_type  definition
  contract_slot_ref   definition:2e43f68a-e879-4811-aa9a-b8b26a2a3a3a
  contract_slot_digest 75fca57d9d2c9bf1bb3c54399c99520f5e26ca84365f76096212dd0fd99bd2b8

definition_artifact 2e43f68a-…  kind=contract  state=approved
                                sha256=75fca57d…  blob_artifact_id=72a4a8e2-…
working_paper_artifact 72a4a8e2-…  state=published  size_bytes=352678
  relative_path definition_store/contracts/75fca57d9d2c9bf1…json
磁盘文件            存在 352,678 B
```

同 `logical_id=d4.revenue_detail` 的新契约行 `3d1fe35a…`（`645e0500…`）也在 —— 两代并存，
这正是「历史 operation 应读旧那份」的正常状态。

### 1.3 可复用的三件既有能力

| 能力 | 位置 | 现状 |
| --- | --- | --- |
| `parse_contract(payload, *, adapter_id=None)` | `contracts.py` | 已强校验；`canonical_sha256` 由 payload 现算 |
| `_read_definition_payload(child, context)` | `published_identity_observer.py` | 读 blob 字节 + `json.loads` + `canonical_digest` 复核；**私有** |
| `_resolve_definition_blob(child, context)` | 同上 | 按冻结 FK 读 artifact row 再交仓储解析路径；**明确不自拼布局**；**私有** |

🔴 **contract slot 从未走过这条路**：那两处只在 instrumentation / template slot 上被调用。
所以本 spec 的主体工作不是「发明读法」，而是**把已有的读法提取成公共能力并让 contract 用上它**。

## §2 ADR

### ADR-FC-001：读路径收敛为「按 slot ref 读」，不按 contract_id 现取

* **选**：新增 `FrozenContractReader`（或等价函数），输入 `bundle_snapshot`（已含三个
  slot 的 `type/ref/digest`），输出 `SyncContract`。内部严格三步：
  ① `slot_ref` 解析出 `definition:<uuid>` → 读 definition 行；
  ② 该行 `blob_artifact_id` → artifact row → 仓储 `resolve_relative_path()` → 读字节；
  ③ `json.loads` → `parse_contract()` → 断言 `canonical_sha256 == slot_digest`。
* **拒**：按 `contract_id` 从 `backend/data/workpaper_sync_contracts/` 现取 —— 那是 registry
  当前 alias，正是本缺陷的成因。
* **拒**：把 contract payload 冗余存进 `working_paper_sync_conflict` 或 operation 行 ——
  那是第二真源，且违反「历史只读 frozen bundle」。
* **拒**：为历史 operation 单独维护一份「旧契约快照表」—— definition store 本身就是
  内容寻址的不可变快照，再存一份等于同一事实两处。

### ADR-FC-002：字节读取与 digest 复核只保留一个实现

`PublishedIdentityObserver._read_definition_payload` / `_resolve_definition_blob` 已正确实现
（含「不自拼 `definition_store` 布局」这条纪律）。**提取到公共模块**，observer 与新的
`FrozenContractReader` 共用；observer 侧改为委派。

* **拒**：复制一份到 conflict_resolution 侧 —— 两份字节读取与 digest 复核必然漂移，且
  「布局是 `ArtifactStorageLayout` 的领地」这条纪律会在第二份里被忘掉。
* 提取时**保留 observer 的 stage/context 错误语义**（`FrozenChildUnusableError` 带
  `stage`），新调用方按需映射成自己的错误类型 —— 不让新能力把 observer 的诊断降级。

### ADR-FC-003：读侧入口默认取冻结契约，显式传入仍是判据

* **选**：`preview()` / `resolve()` / `retry()` 的 `contract` 参数改为**可选**：
  省略 ⇒ 内部按 `bundle` 读冻结契约；显式传入 ⇒ 仍跑
  `assert_frozen_contract_matches_bundle`。
* **拒**：直接把参数删掉改成必走冻结 —— 既有测试与工具（`republish_*` / `fix_*` 宿主）
  大量显式传 contract，删参数会把它们的诊断一起改掉；且「显式传入必须匹配」这条判据本身
  有价值（防调用方拿错契约）。
* 响应侧新增 `contract_source`（`frozen` / `explicit`）与两个 digest（`frozen_digest` /
  `current_registry_digest` 若可现取），让审计师知道看到的是哪一版。**不新增静默行为**。

### ADR-FC-004：遗留 operation 的两种出口，都不删冲突行

一条 `conflict` operation 的冲突在契约变更后可能**业务上已无意义**（本 spec 的对象正是
如此：那 24 条是 D4-32 建模缺陷产生的，缺陷已修）。两种出口：

1. **正式裁决**（R3.1/R3.2）：逐条选边 / 输入合并值，走既有 resolve 端点，落地成新
   representation + 裁决轨迹。
2. **显式作废**（R3.3）：新增 supersede/abandon 语义，**保留冲突行**（append-only），
   标 `superseded_at` + 原因 + 操作者；operation 落终态。

* **拒**：裸 SQL 改 `state` —— 破坏版本链与审计链（这正是上一个 spec 拒绝做的事）。
* **拒**：物理删除冲突行 —— 审计事实不可删。
* 选哪条由用户拍板（见 §5 待拍板）。

## §3 改动面（预估）

| 文件 | 改动 |
| --- | --- |
| `published_identity_observer.py` | 把 `_read_definition_payload` / `_resolve_definition_blob` 提取为模块级公共函数；observer 委派 |
| 新模块 `frozen_contract_reader.py`（或并入 `resolution.py`） | 按 slot ref 读回 `SyncContract`；错误分型（数据缺失 / 状态非法 / 文件缺失 / digest 不符） |
| `conflict_resolution.py` | `preview` / `resolve` / `retry` 的 `contract` 参数改可选 + 默认取冻结；`ConflictPreview` 加 `contract_source` 与 digest 字段 |
| `wp_sync_router.py` | 冲突预览端点不再预取 registry 契约；透传 `contract_source` |
| 前端 `workpaperSyncDto.ts` / 冲突面板 | 解析并显示「这是历史契约」标注 |
| 新增守卫 | Property 1（对任意 bundle 读回 digest 相等）+ Property 4（变异回 registry 即红） |

**不改**：`assert_frozen_contract_matches_bundle`（判据正确）、`load_bundle_snapshot`
（校验完备）、definition store 布局、任何迁移（本 spec **预期零迁移**）。

## §4 风险

* **把「读冻结」误扩成「写冻结」**：本 spec 只做读侧。裁决落地仍写**当前**契约下的新
  representation —— 那是正常的内容演进，不是「改写历史」。
* **`contract_source` 被前端当成能力开关**：它只是标注，不得用它门控按钮可用性。
* **旧契约 payload 可能与新 `parse_contract` 不兼容**（字段增删）：
  `parse_contract` 是强校验，旧 payload 若过不了就是真问题（说明契约演化不向后兼容）。
  处置 = fail visible 并如实报「该历史契约无法按当前解析器读回」，**不静默降级**；
  是否为此写兼容层见 §5 待拍板。
* **同一 logical_id 多代并存**（实测 `d4.revenue_detail` 已有 2 行、`d2.inspection` 2 行）：
  读路径必须**只按 bundle 的 slot_ref** 取，不得按 `logical_id + 最新版本` 取。

## §5 待拍板

1. **遗留 operation `11809f53…` 走哪条出口**：正式裁决（逐条选边，产出新 representation）
   还是显式作废（保留冲突行 + 原因）？前者能真正落地内容，但 24 条冲突的「正确答案」
   在缺陷修复后已无业务意义；后者干净但需要新增 supersede 语义。
2. **是否写旧契约的解析兼容层**：若旧 payload 过不了当前 `parse_contract`，是写兼容
   还是如实拒绝。
3. **`contract_source` 的展示位置与文案**（冲突面板顶部横幅？逐条标注？）。

## §6 验收口径

* Property 1 / 4：读回 digest 相等 + 变异回 registry 即红且形态正确。
* Property 2：对**冻结旧契约**的 operation 预览成功且逐项用旧契约标签。
* Property 3：结算后 operation 离开 `conflict`，representation / revision / 裁决轨迹齐备。
* 真库只用【测试】项目；写入前存全文快照，验收后逐值复原对账（沿用上一个 spec 的纪律）。
