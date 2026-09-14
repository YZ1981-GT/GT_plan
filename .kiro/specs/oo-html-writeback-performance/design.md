# OO/HTML 双向回写性能优化 — Design

## 现状 grep 确认（设计前实证，不臆测）

| 事实 | 实证位置 | 对设计的影响 |
|------|---------|-------------|
| `content_revision` 由业务应用 CAS `+1` 推进，纯定义升级不变 | `repository.py:277` `UPDATE working_paper SET content_revision = content_revision + 1 WHERE ... content_revision = :expected`；`representations.py:13-15` 注释 | substrate representation 只在 revision 变化时才变 → revision 可作失效依据 |
| `resolution.resolve()` 返回的 `resolved` 带 `artifact_sha256`（来自 DB artifact row，内容寻址） | `resolution.py:412` `artifact_sha256=artifact.sha256`；`store_projection_response.py:117` `substrate = Path(resolved.artifact_path)` | **用 `resolved.artifact_sha256` 作缓存键最严格**：字节一变键即变，无需推理 revision 语义 |
| `SyncContract.field_by_stable_key` 是 O(n) 线性扫描 + 每次重建 `all_fields()` tuple | `contracts.py:711-724` | `build_projection` 每字段调 2 次 → O(字段²)，28431 字段=30s；需 memoized `{stable_key: spec}` 索引 |
| `build_projection` 每字段调 `field_by_stable_key` 2 次 | `endpoint_payloads.py:393`（`_resolve_stable_key` 内）+ `:497`（模板取 spec） | 建索引后两处都变 O(1) |
| `build_projection` 在事件循环上跑，无 to_thread | `wp_sync_router.py:919`（`_materialize_request` 直接 await） | 需包 `asyncio.to_thread` |
| materialize CPU 段已 offload，但 verify before 侧每次重算不变量 | `content_mutation.py:1585` `asyncio.to_thread(_stage_cpu_segment)`；`excel_extract.py:1794` before digest | before digest 按 substrate sha256 缓存 |
| substrate extract 已 offload 到 to_thread，但无结果缓存 | `store_projection_response.py:122` `asyncio.to_thread(adapter.extract, ...)` | 加缓存层，命中时连 to_thread 都省 |

## 缓存基础设施：进程内 LRU（新模块）

新建 `backend/app/services/workpaper_sync/parse_cache.py`：

```python
# 伪代码骨架
class _LruCache(Generic[K, V]):
    """线程安全、有界的进程内 LRU。用 OrderedDict + 一把 threading.Lock。
    - to_thread 工作线程与事件循环线程都会读写 → 必须加锁。
    - 有界（maxsize）：LRU 淘汰，绝不无界增长。
    - 只存不可变派生产物（Projection / digest bytes），不存可变状态、不存会话。
    """
    def get_or_compute(self, key: K, compute: Callable[[], V]) -> V: ...
    def invalidate(self, key: K) -> None: ...
    def clear(self) -> None: ...

# 两个模块级单例（各自独立上限）：
_BASELINE_EXTRACT_CACHE = _LruCache(maxsize=64)   # ROI-1
_BEFORE_DIGEST_CACHE = _LruCache(maxsize=128)     # ROI-4
```

- `maxsize` 保守（baseline 64、digest 128），单条是一个 Projection / digest bytes，内存可控；后续按实测调。
- 键都用**内容寻址 sha256**（见下），值是解析产物。缓存本身不感知 wp/revision 语义——sha256 变即 key 变即天然失效。
- 提供 `clear()`（测试隔离用）与 metrics 计数（hit/miss，供后续观测）。

### 为什么进程内 LRU 正确（约束 2/3）
- 键 = substrate 字节的 sha256（内容寻址）。substrate 是**已发布不可变 artifact**（canonical/published），同一 sha256 的字节永远解析出同一 Projection/digest。故缓存命中返回的产物与重新解析**逐字节等价**（约束 4）。
- 无失效逻辑负担：不需要"何时清除"——新 substrate = 新 sha256 = 新 key = 自然 miss。旧 key 由 LRU 淘汰。
- 多 worker 不共享 = 正确性无损（每 worker 独立算，结果相同）；重启失效 = 冷启动重算。

## ROI-1：store-projection baseline extract 缓存

**改点**：`store_projection_response.py::_overlay_with_published_substrate`

```python
# 当前（每次全量 extract）：
baseline = await asyncio.to_thread(
    registration.adapter.extract, artifact=substrate, contract=contract
)
# 改为（sha256 命中则直接返回缓存的 Projection）：
sha = resolved.artifact_sha256   # resolution 已带，内容寻址
baseline = _BASELINE_EXTRACT_CACHE.get(sha)
if baseline is None:
    baseline = await asyncio.to_thread(
        registration.adapter.extract, artifact=substrate, contract=contract
    )
    _BASELINE_EXTRACT_CACHE.put(sha, baseline)
```

- 键：`resolved.artifact_sha256`（含 contract_id 前缀防跨 entry 串：key = f"{contract.contract_id}:{sha}"）。
- 值：`extract` 返回的 `Projection`（frozen dataclass，不可变，跨请求安全）。
- **正确性**：Projection 是 substrate 字节的纯函数；同 sha256 必同 Projection。`overlay_store_on_baseline_projection(baseline, store_projection)` 每次仍照常执行（它依赖每次不同的 store，不缓存）。
- 预期：37–46s → miss 时不变、hit 时 <1s（extract 是 40s 的全部；overlay 是毫秒级）。

## ROI-5：build_projection O(1) 化 + offload

### 5a. `SyncContract` 加 memoized stable-key 索引（`contracts.py`）

```python
@property
def _field_index(self) -> Mapping[str, FieldSpec]:
    # functools.cached_property 或私有惰性 dict；contract 是 frozen，索引一次建成
    idx = getattr(self, "__field_index_cache", None)
    if idx is None:
        idx = {f.stable_field_key: f for f in self.all_fields()}
        object.__setattr__(self, "__field_index_cache", idx)
    return idx

def field_by_stable_key(self, stable_key: str) -> FieldSpec:
    try:
        return self._field_index[stable_key]
    except KeyError:
        raise ContractSchemaError(...)  # 行为不变
```

- **正确性**：dict 由同一份 `all_fields()` 建，查找结果与线性扫描**完全一致**；找不到仍抛 `ContractSchemaError`（约束）。若同一 stable_key 有重复（理论上不该有），dict 取最后一个——需先验证契约无重复 key（build 时可加断言）。
- 复杂度：O(字段²) → O(字段)。

### 5b. `build_projection` offload（`wp_sync_router.py::_materialize_request`）

```python
# 当前：projection = build_projection(payload=..., contract=contract)  # 事件循环
# 改为：projection = await asyncio.to_thread(build_projection, payload=..., contract=contract)
```
- pending-mutations 与 materialize 两条路径都经 `_materialize_request`，一处改两受益。
- **正确性**：`build_projection` 是纯 CPU、无 DB、无会话，offload 安全。

## ROI-4：verify before 侧 digest 缓存

**改点**：`excel_extract.py::unmanaged_region_digest`（before 侧）经由 `verify_unmanaged_regions` 调用。

- before 侧 digest 是 `(substrate 字节, region, binding, extra_managed_sheet_parts)` 的纯函数，substrate 是不可变 published artifact。
- 缓存键：`(substrate_sha256, region.sheet_part, binding.table_key, sorted(extra_managed_sheet_parts))` 的 hash。
- **只缓存 before 侧**（`shared_strings_limit=None` 那次调用）；after 侧带 `shared_strings_limit` 且是本次产物，必变，不缓存。
- **正确性**：漂移判定 = `base.aspects[aspect] != target.aspects[aspect]` 逐 aspect 比较（`verify_unmanaged_regions:1830`）。缓存只让 `base`（不变量）不重算，`target` 照常算，比较逻辑一字不动 → 判定结果完全一致（约束 1）。
- 落点：在 `adapters/excel.py::verify_unmanaged_regions` 或 `excel_extract.verify_unmanaged_regions` 里，对 before digest 包一层 `get_or_compute(before_key, lambda: unmanaged_region_digest(before, ...))`。
- 注意 D4-29 的 before-normalization（`adapters/excel.py:500-508` 用 `materialize_transposed_workbook(before, extract_transposed_workbook(after))` 生成 `before_for_compare`）：这个 before 依赖 **after**（每次变），**不能**用 substrate sha256 缓存。ROI-4 只对**非 D4-29** 的稳定 before 生效；D4-29 的 before-normalization 归 ROI-3（可选）。

## 锁临界区（ROI-6，可选，本批不做）

- `lock_room_oo_apply`（`oo_to_html.py:2463`）横跨 commit + 全 CPU rematerialize。ROI-2/3 把 CPU 段缩短后，串行窗口按比例缩小，先靠 ROI-2/3 间接受益。
- 真要缩临界区（CPU 移锁外）需在锁内重验产物，风险高，本批不动，留 `*` 评估。

## 风险与约束复述（实施时逐条守）

1. **绝不砍校验**：roundtrip / unmanaged drift / structure_hash / identity carrier / final fence / value_type-from-contract 全保留（约束 1）。缓存只避免重算**不变量**，比较/校验逻辑不动。
2. **缓存键必须内容寻址**：用 substrate `artifact_sha256`，字节变即失效。绝不用可变的 wp_id 单独作键。
3. **缓存值必须不可变**：只存 frozen `Projection` / digest bytes，绝不存会话/可变状态。
4. **线程安全**：to_thread 工作线程与事件循环都访问缓存 → LRU 内部加锁。
5. **有界**：LRU maxsize 上限，防内存泄漏。
6. **行为等价**：所有现有测试全绿；返回值缓存命中与否逐字节一致。
7. **contract 无重复 stable_key**：5a 建 dict 前需确认（或加断言），否则 dict 覆盖会与线性扫描"取首个"语义不同（实际 field_by_stable_key 取首个匹配，dict 取最后写入——需对齐：用 `setdefault` 保留首个）。

## 验证策略

- 每个 ROI 落地后跑焦点回归（callback / room_service / d4-29 / bp61 / router），确保全绿。
- 真实 PG 探针复测三端点耗时：优化前 vs 优化后，据实记录数字（不假绿）。
- 缓存正确性专项测试：同 sha256 两次调用返回同一对象 / 结果逐字节等价；不同 sha256 各自 miss；LRU 淘汰不影响正确性。
- `field_by_stable_key` O(1) 化：加一个大字段量的性能/正确性对拍测试（dict 结果 == 原线性扫描结果）。
