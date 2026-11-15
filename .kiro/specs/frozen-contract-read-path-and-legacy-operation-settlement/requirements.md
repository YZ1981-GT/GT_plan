# 需求：冻结契约的读侧重建 + 遗留 operation 结算

## 背景

承接 `wp-sync-conflict-adjudication-and-d4-32-modeling` 归档时如实登记的**范围外项**
（其 tasks.md 12.f）。那里在真库【测试】项目上把 OO→HTML 往返跑通后，留下一个
**无法结算的遗留 operation**：

```
operation  11809f53-a34e-44fc-8182-efc5bc68e019
state      conflict / conflict_count 24
bundle     1504768f-d61f-47a7-a6a2-1e8b2f6212dd
contract_slot_ref     definition:2e43f68a-e879-4811-aa9a-b8b26a2a3a3a
contract_slot_digest  75fca57d9d2c9bf1bb3c54399c99520f5e26ca84365f76096212dd0fd99bd2b8
```

它冻结的是**旧版** `d4.revenue_detail` 契约（`75fca57d…`）；那次 spec 修 D4-32 建模时把
契约改成 `645e0500…`。此后任何读侧入口（冲突预览 / 裁决 / retry）都返回
`frozen_contract_digest_drift`：

> 传入 contract 的 canonical digest `645e0500…` 与 frozen bundle 的 contract slot
> `75fca57d…` 不一致 —— 历史 operation 只读 frozen bundle，不得按 registry 当前 alias 重组

**这个拒绝是正确的**：按 registry 当前 alias 渲染历史 operation，审计师看到的业务标签与
单元格地址会漂移到新模板上。但拒绝之后**没有任何出口** —— 这条 operation 永远停在
`conflict`，它的 24 条冲突既不能裁决也不能丢弃，构成一条只增不减的僵死记录。

## 现场实测（2026-11-15，共享库只读）

**冻结契约在库里完好无损，缺的只是「按冻结 slot 读回来」这一步**：

| 对象 | 实测值 |
| --- | --- |
| `working_paper_sync_definition_artifact` 行 `2e43f68a…` | `kind=contract` / `state=approved` / `sha256=75fca57d…` |
| 它的 `blob_artifact_id` → `working_paper_artifact` | `state=published` / `size_bytes=352678` |
| `relative_path` | `definition_store/contracts/75fca57d9d2c9bf1…json` |
| 磁盘文件 | 存在（352,678 B） |

⇒ 不是数据丢失，是**读路径缺失**。

## 现有可复用能力（已核实，不是新建）

* `parse_contract(payload, *, adapter_id=None)` —— 把 canonical contract payload 强校验成
  `SyncContract`，`canonical_sha256` 由 payload 现算（`contracts.py`）。
* `PublishedIdentityObserver._read_definition_payload()` —— 读 child definition 的 canonical
  payload 字节并按 `sha256` 复核（`published_identity_observer.py`）。
* `PublishedIdentityObserver._resolve_definition_blob()` —— 按冻结 FK 读 artifact row 再交仓储
  解析相对路径，**明确不自拼** `definition_store/{kind}/…` 布局（那是
  `ArtifactStorageLayout` 的领地）。
* `ConflictResolutionService.preview()` 内部已有
  `assert_frozen_contract_matches_bundle(contract, slot_digest, where)` —— 判据本身是对的，
  缺的是**调用方拿不到该传哪份 contract**。

🔴 **关键缺口**：上述两个 `_read_definition_payload` / `_resolve_definition_blob` 是
`PublishedIdentityObserver` 的**私有方法**，且只在 instrumentation / template 两个 slot 上
被调用过；**contract slot 从未走过这条路**。

## Requirements

### Requirement 1：按冻结 slot 读回契约（唯一真源）

1. WHEN 需要读取某个 operation / application 的**冻结契约** THEN 必须按该 bundle 的
   `contract_slot_ref`（形如 `definition:<uuid>`）取 definition 行、按其 `blob_artifact_id`
   读 blob、按 `sha256` 复核后 `parse_contract()`；不得按 `contract_id` 从 registry / 磁盘
   现取。
2. WHEN 读回的 payload canonical digest 与 `contract_slot_digest` 不一致 THEN 必须 fail
   visible 并点名两者，不得降级为「用当前契约继续」。
3. WHEN definition 行不存在 / 非 `approved` / blob 不在盘 THEN 必须给出可区分的中文原因
   （数据缺失 vs 状态非法 vs 文件缺失），不得统一报「契约漂移」。
4. WHEN 该能力被实现 THEN 它必须是**单一实现**：observer 的私有读法与本能力不得各写一份
   字节读取与 digest 复核。

### Requirement 2：读侧入口改为默认取冻结契约

1. WHEN 冲突预览 / 裁决 / retry 需要 contract THEN 默认必须取**冻结**的那份；调用方
   （router）不再从 registry 现取后传进来。
2. WHEN 调用方**显式**传入 contract（既有测试与工具路径）THEN 保留现有
   `assert_frozen_contract_matches_bundle` 判据：不符即拒。不得因为新增默认路径而放宽它。
3. WHEN 冻结契约与当前 registry 契约不同 THEN 预览必须照常工作（用冻结那份渲染
   `business_label` / `value_type` / `oo_location`），并在响应里**如实标注**这是历史契约
   （例如带 `contract_source="frozen"` 与两个 digest），使审计师知道看到的是哪一版。
4. WHEN 冻结契约可用 THEN `frozen_contract_digest_drift` 不得再出现在「用户无法继续」的
   路径上；它只应保留为「显式传入了不匹配的 contract」这一种情形的判据。

### Requirement 3：遗留 operation 可被正式结算

1. WHEN 一条 `state=conflict` 的 operation 的冻结契约可读 THEN 必须能经**正式裁决端点**
   把它的冲突逐条裁决并落地，operation 离开 `conflict`；不得用裸 SQL 改状态。
2. WHEN 裁决落地 THEN 版本链与审计链必须完整：新 representation 代际、content revision、
   裁决轨迹（`resolved_by` / `resolved_at` / `resolved_value`）三者齐备。
3. WHEN 该 operation 的冲突在当前视角下已无意义（契约变更后业务上不再需要）THEN 必须提供
   **显式的作废出口**（supersede / abandon），带中文原因与操作者，且不删除冲突行
   （append-only 审计）。不得留成「永远 conflict」。
4. WHEN 结算完成 THEN 必须能复核：该 operation 终态、冲突行的 resolved/superseded 状态、
   版本链指针与审计轨迹逐项可查。

### Requirement 4：不制造第二真源与假绿

1. WHEN 新增「读冻结契约」能力 THEN `parse_contract` / `canonical_digest` /
   `ArtifactStorageLayout` 三者必须**复用**，不得各抄一份。
2. WHEN 判据声称「用冻结契约」THEN 必须有变异证明：把读路径改回 registry 现取 ⇒ 判据必须
   打红；且红的形态必须是「取到了新契约」而不是别的失败。
3. WHEN 只有冻结契约能通过的场景（旧 digest）THEN 必须有正面用例；只用「当前契约」的用例
   通过**不构成**该能力已被验证的证据。

## Correctness Properties

### Property 1
**Validates: Requirements 1.1-1.4**
对任意 bundle 的 `contract_slot_ref`，读回的 `SyncContract.canonical_sha256` 必须等于该
bundle 的 `contract_slot_digest`；把读路径换成「按 contract_id 从磁盘现取」即被证伪。

### Property 2
**Validates: Requirements 2.1-2.4**
对一条冻结旧契约的 operation，冲突预览必须成功返回且逐项使用旧契约的
`business_label` / `value_type`；响应里如实标注 `contract_source="frozen"`。

### Property 3
**Validates: Requirements 3.1-3.4**
经正式端点结算后，operation 离开 `conflict`，且新 representation / revision / 裁决轨迹
三者齐备可复核；不出现「状态变了但内容没落地」。

### Property 4
**Validates: Requirements 4.1-4.3**
读冻结契约的能力只有一个实现；变异回 registry 现取即打红且形态正确。
