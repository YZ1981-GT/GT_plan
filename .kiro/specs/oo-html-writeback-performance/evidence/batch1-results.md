# OO/HTML 双向回写性能优化 — 批次 1 实施结果（据实记录）

## 真实 PG 探针复测（优化前 vs 优化后）

| 端点 | 优化前（日志实测） | 优化后（同一真实 PG，缓存命中） | 提速 |
|------|-----------------|----------------------------|------|
| `GET .../store-projection` | 34–46s | **0.05–0.07s** | ~500× |
| `POST .../pending-mutations` | 21.7–33s | **0.07s** | ~300× |
| `POST .../materialize` | 23–99s | 未直测（既有数据问题，见下）；两大头已代码覆盖 | — |

冷启动首次请求（进程内所有缓存 miss）仍 ~34s（首次必付一次全量注册 + 解析成本），
第二次起命中缓存 → 亚百毫秒。对多人平台：**每个 worker 首次冷、之后全热**，且缓存按
已发布状态指纹失效，publish/finalize 后自动重建。

## 定位过程（真实探针分段计时，非臆测）

真实 HTTP + 后端临时 `[PERF]` 分段计时定位到三层耗时（已撤计时器）：

1. **`_attach_pilot_adapters` = 21–27s（最大热点，此前未识别）**：每个 sync 端点
   （store-projection / pending / materialize / apply）在 guard 阶段都调它一次，跑完整
   `register_from_manifest`（186 条 entry 逐个 `_describe_entry_supply` = ~186×2 次 DB 往返）
   + 4 条 pilot provider 的 published-identity 观测（读 definition blob + 校 digest）。
   结果**每次都相同**（只依赖静态 manifest + 已发布状态），却每请求重算。
2. **`_overlay_with_published_substrate` baseline extract = 4.5–5.6s**：整簿 openpyxl 解析。
3. **`build_projection` = 21s（pending 路径）**：O(字段²) 线性扫描 + 事件循环阻塞。

关键教训：**最初以为最大头是"整簿 openpyxl 解析"（40s），真实分段计时才发现是
`_attach_pilot_adapters` 的每请求全量重注册（21-27s）**——它被 overlay 的解析成本掩盖，
且影响所有端点。**性能优化必须先真实分段计时定位，不能按代码直觉猜热点。**

## 实施（批次 1，零削校验）

| 项 | 改动 | 正确性保证 |
|----|------|-----------|
| **parse_cache.py** | 新建线程安全有界 LRU（内容寻址键） | 只存不可变派生产物；键=字节 sha256，字节变即失效；有界防泄漏；内部锁 |
| **ROI-0 registry 缓存** | `_attach_pilot_adapters` 按已发布状态指纹（一次 entry_state 查询 + manifest 大小）进程级缓存 `AdapterRegistration`，命中重放 `register()` | AdapterRegistration 由 frozen definitions 构建、不持会话；`register()` 重放时仍逐条全量跑 RG 判据（身份/document_type/bundle/authority/contract 双漂移/matcher 重叠），只跳过"查供给"DB 往返与观测器重跑 |
| **ROI-1 baseline 缓存** | store-projection 的 `adapter.extract` 结果按 `{contract_id}:{artifact_sha256}` 缓存 | Projection 是 substrate 字节纯函数；overlay 每次照常执行 |
| **ROI-4 verify before 缓存** | materialize verify 的 before 侧 digest 按 before 字节 sha256 + region/binding/extra 缓存 | 只缓存不变量；after 侧每次算；漂移比较逻辑不动；D4-29 after-dependent before 自然 miss |
| **ROI-5a `field_by_stable_key` O(1)** | `SyncContract` memoized `{stable_key: spec}` 索引（`setdefault` 保留首个） | 对拍 180 字段 0 mismatch；未登记仍抛 `ContractSchemaError` |
| **ROI-5b `build_projection` offload** | 包 `asyncio.to_thread` | 纯 CPU 无 DB/会话，offload 安全；不再阻塞事件循环 |

## 回归（据实）

- 我的改动**零新增失败**：349 passed（bp61 / d4-29 / callback / task37 extract / task38
  materialize）+ 153（task28 router + task40 pilot AST 守卫）+ 107（callback_pg /
  room_service_pg）。
- 发现 **23 处 pre-existing 失败**（task41 OrderingGate 6 / task28_pg 8 / task13 3 等）：
  全是 **real-manifest capability drift**（真实 manifest 现标某些 entry 为 `bidirectional`，
  而这些测试假设 pre-finalize 的 `single_onlyoffice`）。**stash 掉我的改动后同样失败**，
  与本次优化无关，属既有数据/契约漂移问题（另行处理）。

## 已知遗留（正交，非性能）

- **materialize 未直接复测到底**：store-projection 返回的 projection 含一个既有数据缺陷
  —— D4-6 `key_indicator_rows/运输费用/营业收入/metric_name`（中文标题被当 stable key 存进
  `checklist_responses`），契约未登记 → `projection_unknown_stable_field_key` 422。这是**既有
  数据问题**（某次写入把中文指标名当 key），与性能无关；且它 **0.07s 就 fail-closed 返回**
  （优化前要 21.7s 才走到这个校验），反证 O(1) + registry 缓存生效。materialize 的两大成本
  （registry 21s / verify before）已分别由 ROI-0 / ROI-4 覆盖，registry 缓存对 materialize
  同路径生效已由 pending 0.07s 间接证明。

## 批次 2（`*` 可选，待拍板）

ROI-2（单簿单次 load）/ ROI-3（D4-29 转置手术去冗余）/ ROI-6（缩小 per-room 锁临界区）
动 materialize/apply 核心路径，风险高，需充分回归 + 多人并发压测。批次 1 已解决"点开在线
编辑等 40 秒"与"一人操作卡住所有人轮询"两个最刺眼的问题，批次 2 待用户按收益决定。

## 可复用教训（其他底稿/端点性能优化照此）

1. **先真实分段计时再优化**：代码直觉指向"整簿解析"，实测才发现最大头是"每请求全量重注册
   registry"。用真实 HTTP + 临时 `[PERF]` stderr 计时逐段定位，撤计时器前先据实记录。
2. **每请求重算的确定性结果 = 头号缓存目标**：`_attach_pilot_adapters` 结果只依赖静态
   manifest + 已发布状态，却每请求重算 21-27s。这类"结果恒定、每次重跑"的重活是最高 ROI。
3. **缓存键用内容寻址（sha256）或廉价状态指纹**：baseline/verify 用 substrate 字节 sha256；
   registry 用一次 entry_state 查询的 `{entry→current_representation_id}` 摘要。字节/指纹变即
   失效，无需"何时清除"的推理。
4. **缓存不可变派生产物、重放时全量重校验**：registry 缓存存 `AdapterRegistration`，命中时
   `register()` 重放仍跑全部准入判据 —— 只跳 DB 往返与观测器重跑，不弱化任何校验。
5. **O(n²) 常藏在"每元素调一次线性查找"**：`build_projection` 对 28431 key 各调
   `field_by_stable_key` 2 次，每次线性扫 180 字段 = 千万次比较。memoized dict 一次建成。
6. **纯 CPU 重活必须 offload 出事件循环**：否则一个人的 30s 请求会把所有人的轻量轮询连累到
   数秒（active-job 被连累 12s 是实证）。

---

## 后续修复：D4-22 含 `/` 指标名撑破 stable key（阻塞 materialize 复测的既有缺陷）

批次 1 复测 materialize 时被一个**既有数据缺陷**挡住（`projection_unknown_stable_field_key:
key_indicator_rows/运输费用/营业收入/metric_name`）。根因**不是**存坏数据，而是 **D4-22 设计缺陷**：

- D4-22（重要指标分析）用 `ROW_IDENTITY_STORE_KEY_D422='metricName'`（自由文本中文指标名）作行身份，
  而 stable key 形态是 `表/{身份}/字段`，`/` 是段分隔符。
- 指标 `运输费用/营业收入` 含 `/` → stable key `key_indicator_rows/运输费用/营业收入/metric_name`
  变 4 段，而 `endpoint_payloads._resolve_stable_key` 的段级匹配（分段数须与模板一致，这是
  **故意**的 fail-closed 反 `remark`↔`remark_typo` 误挂）判为未登记 → 422。
- 库里确有此数据（wp b3ab3c46 的 `D4-22-rows` 含该指标），故不能改身份方案（要迁移）。

**修复（localized，不迁移数据、不弱化段级匹配）**：`phase5_d4_ipo_related_sheets.py` 加
`_encode_identity_segment` / `_decode_identity_segment`（百分号编码 `%`→`%25`、`/`→`%2F`，可逆），
`_build_projection` 把身份编码成**单段**再嵌 stable key（row_key 同编码形态，避免
`_resolve_stable_key` 的 `embedded != row_key` 误判）；4 个 merge 函数（D4-21/22/23/24）读
`row_key` 后 `_decode` 回原始身份查 store。store 数据一字不动；D4-21/23/24 身份本 `/`-free，编码恒等无副作用。

**验证**：进程内 round-trip PASS（`运输费用/营业收入` → 编码 → build_projection OK → merge 解码回
原始名，currentPeriod 值正确落回）。回归：`test_d4_21_24_import_export_roundtrip` 8 /
`test_d4_ipo_fraud_io_pbt` + `test_d4_29_customer_detail_sync` 36 全绿。真实 HTTP：pending 从
**422 → 200（0.11s）**。

## materialize 真实复测（性能目标达成 + 暴露另一既有 config 缺陷）

修 D4-22 后 materialize 真实跑到（6s，registry 已缓存无 21s 注册），停在一个**合法的
materialize 正确性门**（非性能、非本次范围）：

```
excel_materialize_footer_formula_range_stale: footer 格 B36 的公式 'SUM(B12:B23)' 区间只到第23行，
而受管行区间已到第35行（含本次声明的 +12 行插入）—— 合计漏算 12 行。未声明即 fail closed。
```

即 D4-2 明细现有 151 行、footer SUM 公式区间没随插行扩张。这是**既有 D4-2 config 问题**（footer
`carries_total_formula` 声明与实际行数不符），正确的 fail-closed，正交于性能与 D4-22 stable key
修复。**materialize 从 23-99s → 6s 已达成**（reaches business gate fast）；余下 footer-range 门
是独立的 D4-2 数据/配置事项。

## 性能优化最终结论（真实 PG 实测）

| 端点 | 优化前 | 优化后（热） |
|------|--------|------------|
| store-projection | 32-46s | **0.09s** |
| pending-mutations | 21.7-33s | **0.11s** |
| materialize | 23-99s | **6s**（到业务门；registry 已缓存） |

冷启动每 worker 首次仍 ~32s（首次全量注册 + 解析），之后全热。多人平台的"点开在线编辑等 40 秒"
与"一人操作卡住所有人轮询"两个致命问题已解决。
