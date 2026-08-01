"""高级查询结果 Redis 缓存服务

高频相同查询（dashboard 卡片）结果加 Redis 短 TTL 缓存（query hash 为 key）。
不动白名单安全模型——缓存发生在安全校验之后。

设计要点：
- cache key = query_cache:{hash(user_id + project_id + query_params)}
  包含 user_id 防止跨租户数据泄漏
- 短 TTL（30~60 秒）适配 dashboard 刷新模式
- Redis 不可用时优雅降级（直接执行查询，不报错）
- 仅缓存成功结果（含 rows 的响应），错误结果不缓存

Validates: Requirements 4.1, 4.3
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 默认 TTL 30 秒（dashboard 刷新周期）
DEFAULT_TTL_SECONDS = 30

# Redis key 前缀
_KEY_PREFIX = "query_cache:"


def compute_cache_key(
    user_id: str,
    project_id: str,
    query_params: dict[str, Any],
) -> str:
    """计算查询缓存 key（含 user_id 防跨租户泄漏）。

    Parameters
    ----------
    user_id : str
        当前用户 ID（隔离租户）
    project_id : str
        项目 ID
    query_params : dict
        查询参数（source/filters/limit 等或 QueryDSL 字段）

    Returns
    -------
    str
        Redis key: query_cache:{sha256_hex[:16]}
    """
    # 构建稳定的 hash 输入（排序 key 保证相同参数产生相同 hash）
    payload = {
        "user_id": user_id,
        "project_id": project_id,
        "params": query_params,
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"{_KEY_PREFIX}{digest}"


async def get_cached_result(cache_key: str) -> dict[str, Any] | None:
    """从 Redis 读取缓存的查询结果。

    Returns None if:
    - Redis 不可用（降级）
    - key 不存在（未命中）
    - 反序列化失败
    """
    from app.core.redis import get_redis

    redis = await get_redis()
    if redis is None:
        return None

    try:
        raw = await redis.get(cache_key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning("query_cache get failed (key=%s): %s", cache_key, e)
        return None


async def set_cached_result(
    cache_key: str,
    result: dict[str, Any],
    ttl: int = DEFAULT_TTL_SECONDS,
) -> None:
    """将查询结果写入 Redis 缓存。

    仅缓存成功结果（无 error 字段）。
    Redis 不可用时静默跳过（降级）。
    """
    from app.core.redis import get_redis

    # 不缓存错误结果
    if "error" in result:
        return

    redis = await get_redis()
    if redis is None:
        return

    try:
        serialized = json.dumps(result, default=str, ensure_ascii=False)
        await redis.set(cache_key, serialized, ex=ttl)
    except Exception as e:
        logger.warning("query_cache set failed (key=%s): %s", cache_key, e)


# ═══════════════════════════════════════════════════════════════════════════════
# CanonicalRedisQueryCache / build_canonical_query_identity
# ═══════════════════════════════════════════════════════════════════════════════
#
# 归档 spec `_archive/04-infra/advanced-query-disclosure-integration-hardening`
# 设计 §3.3 CanonicalQueryIdentityBuilder + §3.2 ExecuteCompatibilityAdapter 默认
# cache 依赖。该 spec 的 tasks.md 把 Wave2 全部标了 [x]，但文末 Notes 自己承认
# 「Wave0–Wave2…尚未编写对应实现」——是假绿任务标记，实现代码从未落地，
# 只有测试 `test_advanced_query_hardening_wave012.py` 和引用它的
# `execute_compatibility.py` 被写了出来，导致两处模块级导入长期失败
# （破坏这两个测试文件的 collection，2026-08-01 实测）。
#
# 本节按设计文档 §3.3 / §4.2 与既有测试文件反推的精确契约补齐实现，不改设计。

#: canonical payload 契约版本（design §4.2 CanonicalQueryIdentityPayload）
_IDENTITY_CACHEABLE_WARNING = "CACHE_IDENTITY_UNSTABLE"


@dataclass(frozen=True)
class CanonicalQueryIdentity:
    """`build_canonical_query_identity` 的返回值（design §4.2）。

    Attributes:
        cacheable: 是否可安全缓存（含不可稳定序列化字段时为 ``False``）。
        key: 可缓存时的稳定缓存键（``aqi:{sha256}``）；不可缓存时为 ``None``。
        payload: 规范化后的完整 payload（供审计/调试；不可缓存时仍尽量填充，
            便于排查具体是哪个字段导致 ``cacheable=False``）。
        warnings: 不可缓存原因（如 ``["CACHE_IDENTITY_UNSTABLE: filters.bad"]``）。
    """

    cacheable: bool
    key: str | None
    payload: dict[str, Any]
    warnings: tuple[str, ...] = ()


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _canonicalize(value: Any, *, path: str, issues: list[str]) -> Any:
    """递归规范化：映射键递归排序；有序数组保序；不可稳定序列化类型记录 issue。

    - dict：键必须是 ``str``（非 str key → issue），值递归规范化，
      按键**排序**输出（Property P3「映射键置换不改变 identity」）。
    - list/tuple：**保序**（columns/sort/acnr_targets 等具有业务语义的数组
      顺序敏感，不得排序 —— design §3.3「具有业务语义的数组保持顺序」）。
    - bool/int/float/str/None：原样（float 需有限，NaN/Inf 记 issue）。
    - set：无确定顺序，直接记 issue（design Req 3.5）。
    - datetime/UUID/Decimal 等：转字符串（`default=str` 语义，可稳定序列化）。
    - 其它未知类型（如裸 ``object()``）：记 issue。
    """
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            issues.append(f"{_IDENTITY_CACHEABLE_WARNING}: {path} 非有限浮点({value!r})")
            return None
        return value
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                issues.append(f"{_IDENTITY_CACHEABLE_WARNING}: {path} 含非字符串键({k!r})")
                continue
            out[k] = _canonicalize(v, path=f"{path}.{k}", issues=issues)
        return dict(sorted(out.items(), key=lambda kv: kv[0]))
    if isinstance(value, (list, tuple)):
        return [
            _canonicalize(v, path=f"{path}[{i}]", issues=issues)
            for i, v in enumerate(value)
        ]
    if isinstance(value, set):
        issues.append(f"{_IDENTITY_CACHEABLE_WARNING}: {path} 为 set（无确定顺序）")
        return None
    # datetime / UUID / Decimal 等：转字符串即可稳定序列化
    try:
        return str(value)
    except Exception:  # noqa: BLE001
        issues.append(f"{_IDENTITY_CACHEABLE_WARNING}: {path} 类型不可序列化({type(value).__name__})")
        return None


def _user_scope_signature(user_scope: dict[str, Any] | None) -> str:
    """用户权限范围只存稳定摘要，不把敏感明细写入 cache key（design §4.2）。"""
    raw = json.dumps(user_scope or {}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_canonical_query_identity(
    *,
    project_id: str,
    year: int,
    source: str,
    filters: dict[str, Any] | None = None,
    columns: list[str] | None = None,
    limit: int = 500,
    offset: int = 0,
    sort: list[dict[str, Any]] | None = None,
    group: dict[str, Any] | None = None,
    pivot: dict[str, Any] | None = None,
    acnr_targets: list[str] | None = None,
    schema_version: str = "1",
    contract_version: str = "aq-disclosure-v1",
    user_scope: dict[str, Any] | None = None,
) -> CanonicalQueryIdentity:
    """构造版本化 canonical query identity（design §3.3 / §4.2，Property P3）。

    覆盖字段：``project_id`` / ``year`` / ``source`` / ``filters`` / ``columns`` /
    ``limit`` / ``offset`` / ``sort`` / ``group`` / ``pivot`` / ``acnr_targets`` /
    ``schema_version`` / ``contract_version`` / ``user_scope_signature``（原始
    ``user_scope`` 只存 SHA-256 摘要，不进 payload/key，防敏感信息落 Redis/日志）。

    映射键递归排序（对象等价即身份相同）；``columns``/``sort``/``acnr_targets``
    等有序数组保持原始顺序（不同排列即不同身份）。任一字段包含不可稳定序列化的值
    （``object()``、``set``、非字符串映射键、非有限浮点）时返回
    ``cacheable=False``、``key=None``，并在 ``warnings`` 记录
    ``CACHE_IDENTITY_UNSTABLE: <path>``（Req 3.5）——执行继续，只是跳过缓存。
    """
    issues: list[str] = []

    payload: dict[str, Any] = {
        "contract_version": contract_version,
        "schema_version": schema_version,
        "project_id": project_id,
        "year": year,
        "source": source,
        "filters": _canonicalize(filters or {}, path="filters", issues=issues),
        "columns": _canonicalize(columns or [], path="columns", issues=issues),
        "limit": limit,
        "offset": offset,
        "sort": _canonicalize(sort or [], path="sort", issues=issues),
        "group": _canonicalize(group, path="group", issues=issues) if group else None,
        "pivot": _canonicalize(pivot, path="pivot", issues=issues) if pivot else None,
        "acnr_targets": _canonicalize(acnr_targets or [], path="acnr_targets", issues=issues),
        "user_scope_signature": _user_scope_signature(user_scope),
    }

    if issues:
        return CanonicalQueryIdentity(
            cacheable=False, key=None, payload=payload, warnings=tuple(issues)
        )

    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return CanonicalQueryIdentity(
        cacheable=True, key=f"aqi:{digest}", payload=payload, warnings=()
    )


@dataclass
class CanonicalRedisQueryCache:
    """`ExecuteCompatibilityAdapter` 默认缓存依赖（design §3.2 / Architecture 图）。

    薄封装 `app.services.custom_query.query_cache.QueryCache`（单飞 + 短 TTL Redis
    降级实现），只是把 `QueryOrchestrator` 期望的
    ``cache_key(query_def, project_id, scope_sig) -> str`` /
    ``get_or_compute(key, compute, *, ttl) -> Any`` 接口对接到已实现的单例，
    不重造缓存逻辑。

    保持独立类名（而非直接把 `query_cache` 单例传给 orchestrator）是为了让
    `ExecuteCompatibilityAdapter()` 无参构造时有一个默认可用对象——调用方仍可
    显式传 ``cache=`` 覆盖（测试里的 ``_PassthroughCache`` / ``_HitCache`` 等）。
    """

    _delegate: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self._delegate is None:
            from app.services.custom_query.query_cache import query_cache as _singleton

            self._delegate = _singleton

    def cache_key(self, query_def: dict, project_id: str, scope_sig: str) -> str:
        return self._delegate.cache_key(query_def, project_id, scope_sig)

    async def get_or_compute(self, key: str, compute, *, ttl: int = DEFAULT_TTL_SECONDS):
        return await self._delegate.get_or_compute(key, compute, ttl=ttl)
