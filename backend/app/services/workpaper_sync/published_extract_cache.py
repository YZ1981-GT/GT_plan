# -*- coding: utf-8 -*-
"""已发布形态 / 物化反读的整簿提取结果跨请求缓存（R3 · P9），也是 adapter 提取的复用入口。

spec: oo-return-to-form-dead-end-and-save-speed · R3.2

═══ 为什么 ═══

一次 OO 保存的 apply 先整簿提取 base（= 上次发布的 representation）。这份字节与上一次保存
物化后反读的那份相同，也与打开在线编辑时 store-projection 读的基线相同 —— 同一份不可变字节在
每个请求里重新解析一遍（和平药房 D2 实测 base 提取约 1 s）。提取是「文件字节 + 冻结定义 +
binding + limits」的纯函数，按这些输入的内容摘要做键即可跨请求复用。

═══ 键（任一输入不同 ⇒ 键不同 ⇒ 不命中）═══

文件字节 sha256 · 契约 canonical digest · 冻结定义逐字段（bundle / authority / adapter build /
identity 清册全字段 / 业务 sheet / 动态列 / 结构清册大小；契约只取 digest）· 全部 binding 逐字段
且保序（含 tombstone / 动态列）· limits 全字段。提取里的门（身份门、OOXML 预算、受管区解析、
载体与保留门、行 / 字段预算、契约匹配）只依赖这些输入 ⇒ 命中 = 上次同样的输入过了同样的门。
转置 sheet 由契约决定（已在键内）。规范化不认识的类型 ⇒ 这次不缓存（照常提取），不猜。

═══ 何时查 / 填 ═══

只在读已发布形态或物化反读（非 incoming）、且没有退役身份时。incoming 永不进缓存：它按
「用户在 OO 里键入的数字读成文本」的口径读，且每次保存都是新文件 —— 它走 P8
（`incoming_view_reuse`，同一次物化内复用）。
值 = 合并后的 Projection + 主 binding 的 (projection, 公式清册)。读的是冻结 base 时照旧填
`_baseline["pair"]`：命中与未命中走同一份判据（只写在 :func:`_seeds_baseline_pair`）。

═══ 不可变约定 ═══

缓存值被多个请求共享，调用方只读（merge / overlay / 往返校验都不改写入参，判据钉住）。
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import enum
import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from app.services.workpaper_sync.adapters.base import SubstrateRole
from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.incoming_view_reuse import record_incoming_views
from app.services.workpaper_sync.parse_cache import PUBLISHED_EXTRACT_CACHE

__all__ = ["PublishedExtract", "begin_extract", "published_extract_key"]

logger = logging.getLogger(__name__)
_SCHEMA = "published-extract:v1"
_WARNED: set[str] = set()


class _Uncacheable(Exception):
    """键里有规范化不认识的输入：这次不缓存。"""


@dataclasses.dataclass(frozen=True)
class PublishedExtract:
    projection: Any
    #: 主 binding 的 (projection, 公式清册)：命中时给冻结 base 填 `_baseline["pair"]`。
    primary_pair: tuple[Any, Mapping[str, str]] | None


def _canon(value: Any, depth: int = 0) -> Any:
    """输入 → 可 JSON 序列化的确定形态。不认识的类型抛 `_Uncacheable`。"""
    if depth > 24:
        raise _Uncacheable("嵌套过深")
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, enum.Enum):
        return f"{type(value).__name__}.{value.name}"
    if isinstance(value, (uuid.UUID, Path, _dt.date, _dt.datetime)):
        return str(value)
    if isinstance(value, (bytes, bytearray)):  # 如 OOXML 策略里的 ZIP magic
        return {"__bytes__": bytes(value).hex()}
    if isinstance(value, SyncContract):
        return {"contract_sha256": value.canonical_sha256}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            "__type__": type(value).__qualname__,
            **{f.name: _canon(getattr(value, f.name), depth + 1) for f in dataclasses.fields(value)},
        }
    if isinstance(value, Mapping):
        pairs = [[_canon(k, depth + 1), _canon(v, depth + 1)] for k, v in value.items()]
        return {"__map__": sorted(pairs, key=lambda kv: json.dumps(kv[0], sort_keys=True))}
    if isinstance(value, (list, tuple)):
        return [_canon(item, depth + 1) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_canon(item, depth + 1) for item in value), key=lambda x: json.dumps(x, sort_keys=True))
    raise _Uncacheable(type(value).__qualname__)


def published_extract_key(adapter: Any, *, artifact: Path, contract: Any) -> str:
    """缓存键（见模块 docstring）。规范化不了 ⇒ `_Uncacheable`。"""
    payload = {
        "schema": _SCHEMA,
        "artifact_sha256": hashlib.sha256(Path(artifact).read_bytes()).hexdigest(),
        "contract_sha256": contract.canonical_sha256,
        "definitions": _canon(adapter.definitions),
        "bindings": [_canon(binding) for binding in adapter._all_bindings()],
        "limits": _canon(adapter._limits),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _role(shape: Iterable[Any]) -> str:
    head = next(iter(shape))
    return str(getattr(head, "value", head))


def _seeds_baseline_pair(adapter: Any, *, artifact: Path, role: str, retired: tuple[str, ...]) -> bool:
    """读的正是冻结 base（已发布形态、无退役身份）且还没填过 ⇒ 用主 binding 的结果填 pair。

    主 binding 的结果与 `derive_baseline_from_representation` 的入参逐项相同（spec save-path R3）。
    """
    base = adapter.baseline_representation
    return (
        role == SubstrateRole.published_representation.value
        and not retired
        and base is not None
        and "pair" not in adapter._baseline
        and Path(artifact).resolve() == Path(base).resolve()
    )


class _Recorder:
    """逐 binding 回调：转给 P8 登记、记下主 binding 的 pair（需要时填 `_baseline`）；收尾填缓存。"""

    def __init__(self, adapter: Any, *, incoming: Callable[..., None], key: str | None, seed: bool) -> None:
        self._adapter, self._incoming, self._key, self._seed = adapter, incoming, key, seed
        self._primary_pair: tuple[Any, Mapping[str, str]] | None = None

    def __call__(self, binding: Any, primary: bool, outcome: Any) -> None:
        self._incoming(binding, primary, outcome)
        if primary:
            self._primary_pair = (outcome.projection, dict(outcome.formula_inventory))
            if self._seed:
                self._adapter._baseline["pair"] = self._primary_pair

    def finish(self, projection: Any) -> Any:
        if self._key is not None:
            PUBLISHED_EXTRACT_CACHE.put(self._key, PublishedExtract(projection, self._primary_pair))
        return projection


def begin_extract(
    adapter: Any, *, artifact: Path, contract: Any, shape: Iterable[Any], retired: Iterable[str]
) -> tuple[Any | None, _Recorder]:
    """`ExcelSyncAdapter.extract` 开头调：返回 (命中的 Projection 或 None, 逐 binding 回调)。"""
    shape = tuple(shape)
    retired = tuple(retired or ())
    role = _role(shape)
    incoming = record_incoming_views(adapter, artifact=artifact, shape=shape, retired=retired)
    seed = _seeds_baseline_pair(adapter, artifact=artifact, role=role, retired=retired)
    if role == SubstrateRole.incoming.value or retired:
        return None, _Recorder(adapter, incoming=incoming, key=None, seed=seed)
    try:
        key: str | None = published_extract_key(adapter, artifact=artifact, contract=contract)
    except _Uncacheable as exc:
        # 照常提取（正确性不受影响），但缓存对这个 entry 静默失效会看不见 ⇒ 每种类型告警一次。
        if str(exc) not in _WARNED:
            _WARNED.add(str(exc))
            logger.warning("[published_extract_cache] 键里有不认识的类型 %s，本类提取不缓存", exc)
        key = None
    except OSError:  # 读不了文件：交给提取本身按原错误收场
        key = None
    hit = PUBLISHED_EXTRACT_CACHE.get(key) if key is not None else None
    if isinstance(hit, PublishedExtract):
        if seed and hit.primary_pair is not None:
            adapter._baseline["pair"] = hit.primary_pair
        return hit.projection, _Recorder(adapter, incoming=incoming, key=None, seed=False)
    return None, _Recorder(adapter, incoming=incoming, key=key, seed=seed)
