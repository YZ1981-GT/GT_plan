"""ACNR Resolver — 统一 resolve 决策树 + resolve_instance + ProjectBinding

resolve() 是平台四大消费库的唯一解析入口（R5），执行完整决策树。
resolve_instance(project_id, parent_wp_code, sheet_code) 是平台唯一的 wp_id
解析出口 (R13.1)。通过运行时查询 WpIndex → WorkingPaper 链实现 ProjectBinding。

决策树（design.md §6.1.1）：
  1. grammar 规范化（URI profile + 索引 ns 映射）
  2. 若带 project_id：先应用 L2 overlay 补丁（R5.2, R5.8）
  3. L1 CellCatalogEntry 精确 match
  4. L1 SheetCatalogEntry + aliases → cell 级 match
     └─ 多命中 → disambiguation（candidates[] / HTTP 409）（R5.5）
  5. 同 sheet semantic_label 包含匹配
  6. L3 RuntimeCellEntry（project-scoped）
  7. 非 wp 域（tb/report/note/aux）→ 委托 V1 动态 build（R5.7）
  8. miss → metrics + 相近项推荐（candidates ≤ 5）（R5.6）

M1 阶段 ProjectBinding 为运行时查询（非物化缓存），M2+ 可选 DB 物化。

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.1, 6.2, 6.3, 6.4, 13.1
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpIndex, WorkingPaper
from app.services.acnr.catalog import (
    get_catalog,
    CatalogIndex,
    _uri_to_addr_id,
    _formula_ref_to_addr_id,
    _index_ref_to_addr_id,
    _find_candidates,
    _hit_cell_response,
    _hit_response,
    _ambiguous_response,
    _build_jump_route,
)
from app.services.acnr.immutability import get_project_registry_version
from app.services.acnr.overlay import get_project_overlay, ProjectOverlay
from app.services.acnr.runtime import get_runtime_entries, RuntimeCellEntry

logger = logging.getLogger(__name__)


# ─── VersionNotFoundError ─────────────────────────────────────────────────────


class VersionNotFoundError(Exception):
    """请求的 registry_version 不存在对应 catalog 快照。

    Requirements: Req-9.3 — 版本缺失返回明确治理错误。
    """

    def __init__(self, version: str) -> None:
        self.version = version
        super().__init__(
            f"Catalog snapshot not found for registry_version={version!r}. "
            f"Requested version does not have an archived snapshot."
        )


# ─── Versioned Catalog Loading (Req-9) ───────────────────────────────────────

_CATALOG_SNAPSHOTS_DIR = Path(__file__).resolve().parents[3] / "data" / "acnr" / "catalog_snapshots"


@lru_cache(maxsize=5)
def load_versioned_catalog(version: str) -> CatalogIndex:
    """加载指定版本的 catalog 快照（LRU 缓存大小=5）。

    从 data/acnr/catalog_snapshots/{version}.json 读取历史版本 catalog，
    构建 CatalogIndex 并缓存。

    Requirements:
        Req-9.1 — full_resolve 版本不同时加载对应版本快照
        Req-9.2 — load_versioned_catalog(version) 方法实现
        Req-9.3 — 版本缺失返回明确治理错误（VersionNotFoundError）

    Args:
        version: registry_version 字符串

    Returns:
        CatalogIndex — 对应版本的索引

    Raises:
        VersionNotFoundError — 快照文件不存在
    """
    snapshot_path = _CATALOG_SNAPSHOTS_DIR / f"{version}.json"

    if not snapshot_path.exists():
        raise VersionNotFoundError(version)

    try:
        data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise VersionNotFoundError(version) from e

    catalog_index = CatalogIndex(data)
    logger.info(
        "ACNR versioned catalog loaded: version=%s sheets=%d cells=%d",
        version,
        len(catalog_index.sheets_by_addr_id),
        len(catalog_index.cells_by_addr_id),
    )
    return catalog_index


# ─── Metrics (R5.6 — miss 指标) ──────────────────────────────────────────────

_resolve_metrics: dict[str, int] = {"hit": 0, "miss": 0, "ambiguous": 0, "v1_delegate": 0}


def get_resolve_metrics() -> dict[str, int]:
    """返回 resolve 调用指标（可观测）。"""
    return dict(_resolve_metrics)


def reset_resolve_metrics() -> None:
    """重置指标（测试用）。"""
    for k in _resolve_metrics:
        _resolve_metrics[k] = 0


# ─── Non-wp Domain Detection (R5.7) ──────────────────────────────────────────

_NON_WP_DOMAINS = {"tb", "report", "note", "aux"}
_NON_WP_URI_PREFIXES = ("tb://", "report://", "note://", "aux://")
_NON_WP_FORMULA_FUNCS = ("TB(", "ROW(", "SUM_ROW(", "SUM_TB(", "REPORT(", "NOTE(", "AUX(")
_NON_WP_INDEX_NS = {"tb", "note", "adj", "att", "eqcr", "calc", "sample", "confirm"}


# ─── Result Types ─────────────────────────────────────────────────────────────


@dataclass
class ProjectBinding:
    """L2 ProjectBinding — 运行时解析结果。

    Fields per design.md §ProjectBinding:
    - project_id: 项目 UUID
    - parent_wp_code: 父底稿码（WP() 第一参）
    - sheet_code: Tab 编码
    - wp_id: 解析到的 WorkingPaper 实例 UUID
    - wp_index_id: WpIndex 条目 UUID
    - resolved_at: 解析时刻
    """

    project_id: UUID
    parent_wp_code: str
    sheet_code: str
    wp_id: UUID
    wp_index_id: UUID
    resolved_at: datetime


@dataclass
class ResolveInstanceResult:
    """resolve_instance 返回值。"""

    found: bool
    wp_id: Optional[UUID] = None
    wp_index_id: Optional[UUID] = None
    jump_route: Optional[str] = None
    binding: Optional[ProjectBinding] = None
    error: Optional[str] = None
    candidates: Optional[list[dict]] = None


# ─── Full Resolve Decision Tree (R5.1) ────────────────────────────────────────


@dataclass
class ResolveResult:
    """full_resolve() 返回值 — 统一响应契约。

    R5.3: 命中返回 found=True + addr_id + entry_type + cell_address + semantic_label
           + formula_ref + uri + jump_route
    R5.4: 带 project_id 且命中时附 wp_id
    R5.5: 同 sheet 多候选 → found=False + error="ambiguous" + candidates
    R5.6: miss → found=False + candidates ≤ 5
    R5.7: 非 wp 域 → 委托 V1 动态 build 返回统一契约
    """

    found: bool
    addr_id: Optional[str] = None
    entry_type: Optional[str] = None
    cell_address: Optional[str] = None
    semantic_label: Optional[str] = None
    formula_ref: Optional[str] = None
    uri: Optional[str] = None
    jump_route: Optional[str] = None
    wp_id: Optional[str] = None  # R5.4: 带 project_id 时附加
    error: Optional[str] = None
    candidates: Optional[list[dict]] = None
    # 内部元数据
    source_layer: Optional[str] = None  # "L1_cell" / "L1_sheet" / "L2" / "L3" / "V1"


def _detect_non_wp_domain(
    uri: str | None,
    formula_ref: str | None,
    index_ref: str | None,
) -> str | None:
    """检测输入是否为非 wp 域（tb/report/note/aux）。

    返回域名（如 "tb"）或 None（wp 域 / 无法判定）。
    """
    if uri:
        for prefix in _NON_WP_URI_PREFIXES:
            if uri.startswith(prefix):
                return prefix.split("://")[0]

    if formula_ref:
        upper = formula_ref.strip().upper()
        for func in _NON_WP_FORMULA_FUNCS:
            if upper.startswith(func):
                return func.rstrip("(").lower()
                # 映射 ROW/SUM_ROW → report, SUM_TB → tb
        # 细粒度映射
        if upper.startswith("ROW(") or upper.startswith("SUM_ROW(") or upper.startswith("REPORT("):
            return "report"
        if upper.startswith("TB(") or upper.startswith("SUM_TB("):
            return "tb"
        if upper.startswith("NOTE("):
            return "note"
        if upper.startswith("AUX("):
            return "aux"

    if index_ref and ":" in index_ref:
        ns = index_ref.split(":", 1)[0].lower()
        if ns in _NON_WP_INDEX_NS:
            return ns if ns in _NON_WP_DOMAINS else "report"  # adj/att/etc → 外部模块

    return None


def _delegate_v1(
    uri: str | None,
    formula_ref: str | None,
    index_ref: str | None,
    domain: str,
) -> ResolveResult:
    """委托 V1 address_registry 解析非 wp 域，返回统一契约（R5.7）。

    消费者无需区分数据来自 L1 JSON 还是 V1 动态 build（R22.3, R22.5）。
    """
    from app.services.address_registry import (
        parse_uri as v1_parse_uri,
        formula_ref_to_uri as v1_formula_ref_to_uri,
        uri_to_formula_ref as v1_uri_to_formula_ref,
        build_uri as v1_build_uri,
    )

    # 标准化：确保有 URI
    resolved_uri = uri
    if not resolved_uri and formula_ref:
        resolved_uri = v1_formula_ref_to_uri(formula_ref)
    if not resolved_uri and index_ref and ":" in index_ref:
        ns, target = index_ref.split(":", 1)
        ns_lower = ns.lower()
        # 按 grammar_v1 索引命名空间映射表
        if ns_lower == "tb":
            # TB:1001 → tb://1001#审定数（默认列=审定数，R11.2）
            resolved_uri = v1_build_uri("tb", target, cell="审定数")
        elif ns_lower == "note":
            # Note:五、3 → note://五、3
            resolved_uri = v1_build_uri("note", target)
        else:
            # 外部模块（Adj/Att/EQCR/Calc/Sample/Confirm）
            # 首期只登记不解析物理格（R11.4），返回 miss
            return ResolveResult(
                found=False,
                error="external_module_not_resolved",
                candidates=[],
                source_layer="V1",
            )

    if not resolved_uri:
        _resolve_metrics["miss"] += 1
        return ResolveResult(found=False, candidates=[], source_layer="V1")

    # 解析 URI
    parts = v1_parse_uri(resolved_uri)
    if not parts:
        _resolve_metrics["miss"] += 1
        return ResolveResult(found=False, candidates=[], source_layer="V1")

    # 构造统一契约（R5.7：同一出口统一响应）
    resolved_formula_ref = formula_ref
    if not resolved_formula_ref:
        resolved_formula_ref = v1_uri_to_formula_ref(resolved_uri)

    _resolve_metrics["v1_delegate"] += 1
    return ResolveResult(
        found=True,
        addr_id=f"{parts['domain']}://{parts['source']}/{parts['path']}"
        if parts["path"]
        else f"{parts['domain']}://{parts['source']}",
        entry_type=parts["domain"],
        cell_address=parts.get("cell"),
        semantic_label=None,
        formula_ref=resolved_formula_ref,
        uri=resolved_uri,
        jump_route=None,  # jump_route 需要 project context，调用方自行 build
        source_layer="V1",
    )


async def full_resolve(
    *,
    uri: str | None = None,
    formula_ref: str | None = None,
    addr_id: str | None = None,
    index_ref: str | None = None,
    project_id: str | None = None,
    db: AsyncSession | None = None,
    _instance_memo: dict | None = None,
) -> ResolveResult:
    """统一 resolve 决策树入口 — 四库唯一解析方法（R5.1）。

    输入接受四种语法（五域 URI / WP() 公式 / 索引 ns:target / 裸 addr_id），
    按设计文档 §6.1.1 的八步决策树依次执行，输出统一 canonical 响应。

    Args:
        uri: 五域 URI（如 wp://D2/明细表D2-2#E100）
        formula_ref: 公式引用（如 WP('D2','明细表D2-2','E100')）
        addr_id: 裸 addr_id（如 D2/D2-2/E100）
        index_ref: 索引命名空间引用（如 cell:D2-2!E100）
        project_id: 项目 ID（有值时触发 L2 overlay 和 wp_id 附加）
        db: 数据库会话（resolve_instance 需要，project_id 时必传）
        _instance_memo: 请求级 resolve_instance 缓存（Req-17），
            key = "project_id:parent_wp_code:sheet_code"，命中则跳过 DB。
            由 resolve-batch 端点创建并传入各次 full_resolve，
            单次请求结束后自动丢弃（request-scoped）。
            disambiguation 结果不缓存。

    Returns:
        ResolveResult — 统一响应契约

    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, Req-12.1, Req-17
    """
    import time as _time
    from app.services.acnr.metrics import get_acnr_metrics

    _t0 = _time.perf_counter()
    _metrics = get_acnr_metrics()

    cat = get_catalog()
    overlay = get_project_overlay()

    # ─── Req-9: 版本锁定解析（归档项目按锁定 registry_version 解析）──────
    # 完整实现：
    #   - locked_version == current catalog version → 使用当前 catalog（最常见）
    #   - locked_version != current → 加载对应版本快照
    #   - 快照缺失 → 抛出 VersionNotFoundError（明确治理错误）
    if project_id:
        locked_version = get_project_registry_version(project_id)
        if locked_version:
            current_version = cat.registry_version
            if locked_version != current_version:
                # Req-9.1: 加载对应版本的 Catalog 快照进行解析
                try:
                    cat = load_versioned_catalog(locked_version)
                except VersionNotFoundError:
                    # Req-12.5: version mismatch 告警
                    _metrics.record_version_mismatch(
                        locked_version,
                        f"Catalog snapshot missing for version={locked_version}",
                    )
                    # Req-12.2: 记录 fallback 到当前版本
                    _metrics.record_fallback(
                        f"snapshot fallback: version={locked_version} not found, using current",
                        domain="wp",
                    )
                    # Req-9.3: 版本缺失返回明确治理错误
                    logger.warning(
                        "ACNR version-locked resolve fallback: project=%s locked=%s current=%s — using current catalog",
                        project_id, locked_version, current_version,
                    )
                    raise

    # ─── Step 7 (前置判断): 非 wp 域检测 → 委托 V1（R5.7）──────────────
    non_wp_domain = _detect_non_wp_domain(uri, formula_ref, index_ref)
    if non_wp_domain:
        result = _delegate_v1(uri, formula_ref, index_ref, non_wp_domain)
        # Req-12.1: 记录 fallback 指标
        _latency = (_time.perf_counter() - _t0) * 1000
        _result_str = "fallback" if result.found else "miss"
        _metrics.record_resolve(
            domain=non_wp_domain,
            layer_hit="V1",
            result=_result_str,
            latency_ms=_latency,
        )
        # Req-12.2: 记录 fallback 事件
        if result.found:
            _metrics.record_fallback(
                f"非wp域委托V1: domain={non_wp_domain}",
                domain=non_wp_domain,
            )
        return result

    # ─── Step 1: grammar 规范化 → 推导 addr_id ──────────────────────────
    resolved_addr_id: str | None = None
    if addr_id:
        resolved_addr_id = addr_id
    elif uri:
        resolved_addr_id = _uri_to_addr_id(uri)
    elif formula_ref:
        resolved_addr_id = _formula_ref_to_addr_id(formula_ref)
    elif index_ref:
        resolved_addr_id = _index_ref_to_addr_id(index_ref)

    if not resolved_addr_id:
        # 无法解析输入
        _resolve_metrics["miss"] += 1
        query = uri or formula_ref or addr_id or index_ref or ""
        candidates = _find_candidates(query, max_results=5)
        # Req-12.1: 记录 miss 指标
        _latency = (_time.perf_counter() - _t0) * 1000
        _metrics.record_resolve(
            domain="unknown",
            layer_hit=None,
            result="miss",
            latency_ms=_latency,
        )
        return ResolveResult(found=False, candidates=candidates, source_layer=None)

    # ─── Canonical normalization (Req-6): 内部使用 CanonicalAddress 比较 ───
    # 通过 CanonicalAddress round-trip 确保 addr_id 格式规范
    from app.services.acnr.canonical import CanonicalAddress as _CA
    try:
        _canonical = _CA.from_addr_id(resolved_addr_id)
        resolved_addr_id = _canonical.addr_id
    except (ValueError, IndexError):
        pass  # 非标准格式，保持原值继续

    # ─── Step 2: 若带 project_id → 先应用 L2 overlay（R5.2, R5.8）────
    # overlay 修改的是 catalog 的 sheet 条目（sheet_name_aliases 等），
    # 使得后续匹配使用项目级补丁后的数据
    project_aliases: dict[str, list[str]] = {}
    if project_id:
        project_aliases = overlay.get_project_aliases(project_id)

    # ─── Step 3: L1 CellCatalogEntry 精确 match ─────────────────────────
    cell_entry = cat.cells_by_addr_id.get(resolved_addr_id)
    if cell_entry:
        result = _build_cell_resolve_result(cell_entry, project_id, overlay)
        # R5.4: 带 project_id 时附 wp_id
        if project_id and db:
            result = await _attach_wp_id(result, project_id, db, _instance_memo)
        _resolve_metrics["hit"] += 1
        # Req-12.1: 记录 hit 指标
        _latency = (_time.perf_counter() - _t0) * 1000
        _metrics.record_resolve(
            domain="wp",
            layer_hit="L1_cell",
            result="found",
            latency_ms=_latency,
        )
        return result

    # ─── Step 4: L1 SheetCatalogEntry + aliases → cell 级 match ──────────
    # 4a. 先尝试 sheet 精确匹配
    sheet_entry = cat.sheets_by_addr_id.get(resolved_addr_id)
    if sheet_entry:
        # 如果 project_id 存在，应用单条目 overlay
        if project_id:
            sheet_entry = overlay.apply_to_single(project_id, sheet_entry)
        result = _build_sheet_resolve_result(sheet_entry, project_id, overlay)
        if project_id and db:
            result = await _attach_wp_id(result, project_id, db, _instance_memo)
        _resolve_metrics["hit"] += 1
        return result

    # 4b. 尝试 addr_id 的 sheet 部分（前两段）+ 别名匹配
    parts = resolved_addr_id.split("/")
    if len(parts) >= 2:
        # 尝试 parent/sheet_code 作为 sheet addr_id + 末段作为 cell_desc
        sheet_addr_id = f"{parts[0]}/{parts[1]}"
        cell_desc = "/".join(parts[2:]) if len(parts) > 2 else None

        sheet_entry = cat.sheets_by_addr_id.get(sheet_addr_id)
        if sheet_entry and cell_desc:
            # 在该 sheet 下搜索 cell
            cells = cat.cells_by_parent.get(sheet_addr_id, [])

            # 精确 cell_address 匹配
            exact = [c for c in cells if c.get("cell_address") == cell_desc]
            if len(exact) == 1:
                result = _build_cell_resolve_result(exact[0], project_id, overlay)
                if project_id and db:
                    result = await _attach_wp_id(result, project_id, db, _instance_memo)
                _resolve_metrics["hit"] += 1
                return result

            # 多命中 → ambiguous (R5.5)
            if len(exact) > 1:
                _resolve_metrics["ambiguous"] += 1
                return ResolveResult(
                    found=False,
                    error="ambiguous",
                    candidates=[
                        {
                            "addr_id": c.get("addr_id"),
                            "display_label": c.get("semantic_label") or c.get("addr_id"),
                            "score": 1.0,
                        }
                        for c in exact
                    ],
                    source_layer="L1_cell",
                )

            # ─── Step 5: semantic_label 包含匹配 ────────────────────────
            semantic = [
                c for c in cells
                if cell_desc and cell_desc in (c.get("semantic_label") or "")
            ]
            if len(semantic) == 1:
                result = _build_cell_resolve_result(semantic[0], project_id, overlay)
                if project_id and db:
                    result = await _attach_wp_id(result, project_id, db, _instance_memo)
                _resolve_metrics["hit"] += 1
                return result
            if len(semantic) > 1:
                _resolve_metrics["ambiguous"] += 1
                return ResolveResult(
                    found=False,
                    error="ambiguous",
                    candidates=[
                        {
                            "addr_id": c.get("addr_id"),
                            "display_label": c.get("semantic_label") or c.get("addr_id"),
                            "score": 1.0,
                        }
                        for c in semantic
                    ],
                    source_layer="L1_cell",
                )

    # 4c. 单段 → 裸 sheet_code 匹配
    if len(parts) == 1:
        code_matches = cat.sheets_by_code.get(parts[0], [])
        # 应用项目别名补充
        if project_id:
            code_matches = overlay.apply(project_id, code_matches) if code_matches else code_matches
        if len(code_matches) == 1:
            result = _build_sheet_resolve_result(code_matches[0], project_id, overlay)
            if project_id and db:
                result = await _attach_wp_id(result, project_id, db, _instance_memo)
            _resolve_metrics["hit"] += 1
            return result
        if len(code_matches) > 1:
            _resolve_metrics["ambiguous"] += 1
            return ResolveResult(
                found=False,
                error="ambiguous",
                candidates=[
                    {
                        "addr_id": e.get("addr_id"),
                        "display_label": e.get("display_label") or e.get("sheet_name") or e.get("addr_id"),
                        "score": 1.0,
                    }
                    for e in code_matches
                ],
                source_layer="L1_sheet",
            )

    # 4d. 别名反查（含项目级别名）
    if len(parts) >= 2:
        # 尝试 parts[1] 作为别名
        alias_key = parts[1] if len(parts) >= 2 else parts[0]
        alias_matches = cat.sheets_by_alias.get(alias_key, [])
        # 加上项目别名
        if project_id and project_aliases:
            for aid, aliases in project_aliases.items():
                if alias_key in aliases:
                    extra = cat.sheets_by_addr_id.get(aid)
                    if extra and extra not in alias_matches:
                        alias_matches = alias_matches + [extra]

        # 按 parent_wp_code 过滤
        if parts[0] and alias_matches:
            filtered = [m for m in alias_matches if m.get("parent_wp_code") == parts[0]]
            if filtered:
                alias_matches = filtered

        if len(alias_matches) == 1 and len(parts) > 2:
            # 有 cell 部分
            cell_desc = "/".join(parts[2:])
            cells = cat.cells_by_parent.get(alias_matches[0].get("addr_id", ""), [])
            exact = [c for c in cells if c.get("cell_address") == cell_desc]
            if len(exact) == 1:
                result = _build_cell_resolve_result(exact[0], project_id, overlay)
                if project_id and db:
                    result = await _attach_wp_id(result, project_id, db, _instance_memo)
                _resolve_metrics["hit"] += 1
                return result
            # semantic 包含
            semantic = [c for c in cells if cell_desc in (c.get("semantic_label") or "")]
            if len(semantic) == 1:
                result = _build_cell_resolve_result(semantic[0], project_id, overlay)
                if project_id and db:
                    result = await _attach_wp_id(result, project_id, db, _instance_memo)
                _resolve_metrics["hit"] += 1
                return result

        elif len(alias_matches) == 1:
            result = _build_sheet_resolve_result(alias_matches[0], project_id, overlay)
            if project_id and db:
                result = await _attach_wp_id(result, project_id, db, _instance_memo)
            _resolve_metrics["hit"] += 1
            return result

    # ─── Step 6: L3 RuntimeCellEntry（project-scoped）────────────────────
    # Req-19: L3 模糊搜索收紧 — 移除 startswith(wp_code) 宽松条件
    # 仅保留：精确 addr_id / cell_address 精确 / endswith("/" + cell_address)
    # 多候选 → ambiguous（与 L1 行为对齐）
    if project_id:
        runtime_entries = get_runtime_entries(project_id)
        if runtime_entries:
            # 精确匹配 addr_id
            rt_entry = runtime_entries.get(resolved_addr_id)
            if rt_entry:
                result = _build_runtime_resolve_result(rt_entry)
                _resolve_metrics["hit"] += 1
                return result

            # 收紧的模糊搜索：仅 cell_address 精确 + endswith("/" + cell_address)
            # 不再使用 startswith(wp_code)，避免 D2 vs D2-2 互相错格
            l3_candidates: list[RuntimeCellEntry] = []
            for rt_addr_id, rt_entry in runtime_entries.items():
                if (
                    resolved_addr_id == rt_entry.cell_address
                    or resolved_addr_id.endswith(f"/{rt_entry.cell_address}")
                ):
                    l3_candidates.append(rt_entry)

            if len(l3_candidates) == 1:
                result = _build_runtime_resolve_result(l3_candidates[0])
                _resolve_metrics["hit"] += 1
                return result
            elif len(l3_candidates) > 1:
                # 多候选 → ambiguous（Req-19.3, Req-5.3 残留漏洞修复）
                _resolve_metrics["ambiguous"] += 1
                return ResolveResult(
                    found=False,
                    error="ambiguous",
                    candidates=[
                        {
                            "addr_id": c.addr_id,
                            "display_label": c.semantic_label or c.addr_id,
                            "score": 1.0,
                        }
                        for c in l3_candidates
                    ],
                    source_layer="L3",
                )

    # ─── Step 8: miss → metrics + 相近项推荐（≤5）（R5.6）─────────────────
    _resolve_metrics["miss"] += 1
    candidates = _find_candidates(resolved_addr_id, max_results=5)
    _result = ResolveResult(found=False, candidates=candidates, source_layer=None)

    # Req-12.1: 记录 miss 指标
    _latency = (_time.perf_counter() - _t0) * 1000
    _metrics.record_resolve(
        domain="wp",
        layer_hit=None,
        result="miss",
        latency_ms=_latency,
    )
    return _result


# ─── Resolve Result Builders ──────────────────────────────────────────────────


def _build_cell_resolve_result(
    cell: dict,
    project_id: str | None,
    overlay: ProjectOverlay,
) -> ResolveResult:
    """从 L1 CellCatalogEntry 构建命中响应（R5.3）。"""
    cat = get_catalog()
    parent_id = cell.get("parent_addr_id", "")
    parent = cat.sheets_by_addr_id.get(parent_id)

    jump_route: str | None = None
    if parent:
        template = parent.get("jump_route_template", "")
        jump_route = template  # wp_id 由 _attach_wp_id 后续填充

    return ResolveResult(
        found=True,
        addr_id=cell.get("addr_id"),
        entry_type="cell",
        cell_address=cell.get("cell_address"),
        semantic_label=cell.get("semantic_label"),
        formula_ref=cell.get("formula_ref"),
        uri=cell.get("uri"),
        jump_route=jump_route,
        source_layer="L1_cell",
    )


def _build_sheet_resolve_result(
    sheet: dict,
    project_id: str | None,
    overlay: ProjectOverlay,
) -> ResolveResult:
    """从 L1 SheetCatalogEntry 构建命中响应。"""
    return ResolveResult(
        found=True,
        addr_id=sheet.get("addr_id"),
        entry_type="sheet",
        cell_address=None,
        semantic_label=None,
        formula_ref=None,
        uri=None,
        jump_route=sheet.get("jump_route_template"),
        source_layer="L1_sheet",
    )


def _build_runtime_resolve_result(entry: RuntimeCellEntry) -> ResolveResult:
    """从 L3 RuntimeCellEntry 构建命中响应。"""
    return ResolveResult(
        found=True,
        addr_id=entry.addr_id,
        entry_type="runtime_cell",
        cell_address=entry.cell_address,
        semantic_label=entry.semantic_label,
        formula_ref=entry.formula_ref,
        uri=entry.uri,
        jump_route=None,  # runtime entry 无 jump_route_template，需显式 resolve_instance
        wp_id=entry.wp_id or None,
        source_layer="L3",
    )


async def _attach_wp_id(
    result: ResolveResult,
    project_id: str,
    db: AsyncSession,
    _instance_memo: dict | None = None,
) -> ResolveResult:
    """R5.4: 带 project_id 且 L1 命中 → 通过 resolve_instance 附 wp_id。

    解析 addr_id 的 parent_wp_code + sheet_code → 查 WpIndex → 获取 wp_id。
    成功时同时更新 jump_route（模板填充 wp_id）。

    Req-17: 支持请求级缓存（_instance_memo）。
    - key = f"{project_id}:{parent_wp_code}:{sheet_code}"
    - 命中则跳过 DB 查询
    - disambiguation 结果不缓存（每次重新查询以获取最新状态）
    """
    if not result.found or not result.addr_id:
        return result

    parts = result.addr_id.split("/")
    if len(parts) < 2:
        return result

    parent_wp_code = parts[0]
    sheet_code = parts[1]

    try:
        # Req-17: 请求级缓存查询
        memo_key = f"{project_id}:{parent_wp_code}:{sheet_code}"
        if _instance_memo is not None and memo_key in _instance_memo:
            instance_result = _instance_memo[memo_key]
        else:
            instance_result = await resolve_instance(
                db=db,
                project_id=UUID(project_id),
                parent_wp_code=parent_wp_code,
                sheet_code=sheet_code,
            )
            # Req-17.4: disambiguation 结果不缓存
            if _instance_memo is not None and instance_result.error != "disambiguation":
                _instance_memo[memo_key] = instance_result

        if instance_result.found and instance_result.wp_id:
            result.wp_id = str(instance_result.wp_id)
            # 用解析到的 wp_id 填充 jump_route 模板
            if result.jump_route and "{wp_id}" in result.jump_route:
                result.jump_route = result.jump_route.replace(
                    "{wp_id}", str(instance_result.wp_id)
                )
            elif instance_result.jump_route:
                result.jump_route = instance_result.jump_route
    except Exception as e:
        # 附加 wp_id 失败不影响解析结果（命中仍为 True）
        logger.debug(
            "attach_wp_id failed: project=%s addr=%s error=%s",
            project_id, result.addr_id, e,
        )

    return result


# ─── Core resolve_instance function ──────────────────────────────────────────


async def resolve_instance(
    db: AsyncSession,
    project_id: UUID,
    parent_wp_code: str,
    sheet_code: str,
    *,
    explicit_wp_id: Optional[UUID] = None,
) -> ResolveInstanceResult:
    """解析项目内 wp_id — 唯一 wp_id 出口 (R13.1)。

    逻辑：
    1. 查 WpIndex 表：project_id 匹配 AND wp_code 匹配 sheet_code
       (因为 WpIndex.wp_code 对应 sheet 级编码如 "D2-2")
    2. 恰好 1 条 → 查 WorkingPaper 获取 wp_id → 返回 jump_route + wp_id
    3. 多条 → disambiguation error (R6.3)，除非 explicit_wp_id
    4. 0 条 → not found

    Args:
        db: 异步数据库会话
        project_id: 项目 UUID
        parent_wp_code: 父底稿码（如 D2），用于 jump_route 与 catalog 查找
        sheet_code: Tab 编码（如 D2-2），用于 WpIndex 查询
        explicit_wp_id: 调用方显式传入的 wp_id，多实例时跳过消歧

    Returns:
        ResolveInstanceResult
    """
    # ─── R6.3: 显式传入 wp_id 时直接验证并返回 ───────────────────────────
    if explicit_wp_id is not None:
        return await _resolve_with_explicit_wp_id(
            db, project_id, parent_wp_code, sheet_code, explicit_wp_id
        )

    # ─── Step 1: 查 WpIndex ──────────────────────────────────────────────
    stmt = (
        sa.select(WpIndex)
        .where(
            WpIndex.project_id == project_id,
            WpIndex.wp_code == sheet_code,
            WpIndex.is_deleted == sa.false(),
        )
    )
    result = await db.execute(stmt)
    indices = result.scalars().all()

    # ─── Step 4: 0 条 → not found ────────────────────────────────────────
    if not indices:
        logger.debug(
            "resolve_instance miss: project=%s parent=%s sheet=%s",
            project_id, parent_wp_code, sheet_code,
        )
        return ResolveInstanceResult(found=False, error="not_found")

    # ─── Step 3: 多条 → disambiguation error (R6.3) ──────────────────────
    if len(indices) > 1:
        candidates = [
            {
                "wp_index_id": str(idx.id),
                "wp_code": idx.wp_code,
                "wp_name": idx.wp_name,
            }
            for idx in indices
        ]
        return ResolveInstanceResult(
            found=False,
            error="disambiguation",
            candidates=candidates,
        )

    # ─── Step 2: 恰好 1 条 → 获取 wp_id ─────────────────────────────────
    wp_index_entry = indices[0]
    return await _resolve_single_index(
        db, project_id, parent_wp_code, sheet_code, wp_index_entry
    )


# ─── Internal helpers ─────────────────────────────────────────────────────────


async def _resolve_single_index(
    db: AsyncSession,
    project_id: UUID,
    parent_wp_code: str,
    sheet_code: str,
    wp_index_entry: WpIndex,
) -> ResolveInstanceResult:
    """从单个 WpIndex 条目解析到 wp_id + jump_route。"""
    # 查 WorkingPaper：通过 wp_index_id 定位底稿实例
    wp_stmt = (
        sa.select(WorkingPaper.id)
        .where(
            WorkingPaper.wp_index_id == wp_index_entry.id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
        .limit(1)
    )
    wp_result = await db.execute(wp_stmt)
    wp_id_row = wp_result.scalar_one_or_none()

    if wp_id_row is None:
        # WpIndex 存在但 WorkingPaper 未创建（底稿未生成）
        return ResolveInstanceResult(
            found=False,
            wp_index_id=wp_index_entry.id,
            error="working_paper_not_created",
        )

    wp_id = wp_id_row

    # 构建 jump_route (R6.2)
    jump_route = _build_jump_route(project_id, wp_id, parent_wp_code, sheet_code)

    # 构建 ProjectBinding
    binding = ProjectBinding(
        project_id=project_id,
        parent_wp_code=parent_wp_code,
        sheet_code=sheet_code,
        wp_id=wp_id,
        wp_index_id=wp_index_entry.id,
        resolved_at=datetime.now(timezone.utc),
    )

    return ResolveInstanceResult(
        found=True,
        wp_id=wp_id,
        wp_index_id=wp_index_entry.id,
        jump_route=jump_route,
        binding=binding,
    )


async def _resolve_with_explicit_wp_id(
    db: AsyncSession,
    project_id: UUID,
    parent_wp_code: str,
    sheet_code: str,
    explicit_wp_id: UUID,
) -> ResolveInstanceResult:
    """R6.3: 显式传入 wp_id 时直接验证并返回。

    验证 wp_id 确实属于该项目且未删除。
    """
    wp_stmt = (
        sa.select(WorkingPaper)
        .where(
            WorkingPaper.id == explicit_wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    wp_result = await db.execute(wp_stmt)
    wp = wp_result.scalar_one_or_none()

    if wp is None:
        return ResolveInstanceResult(
            found=False,
            error="explicit_wp_id_not_found",
        )

    # 构建 jump_route
    jump_route = _build_jump_route(project_id, explicit_wp_id, parent_wp_code, sheet_code)

    binding = ProjectBinding(
        project_id=project_id,
        parent_wp_code=parent_wp_code,
        sheet_code=sheet_code,
        wp_id=explicit_wp_id,
        wp_index_id=wp.wp_index_id,
        resolved_at=datetime.now(timezone.utc),
    )

    return ResolveInstanceResult(
        found=True,
        wp_id=explicit_wp_id,
        wp_index_id=wp.wp_index_id,
        jump_route=jump_route,
        binding=binding,
    )


def _build_jump_route(
    project_id: UUID,
    wp_id: UUID,
    parent_wp_code: str,
    sheet_code: str,
) -> str:
    """构建跳转路由（R6.2）。

    使用 catalog 的 jump_route_template（如有），否则构建默认路由。
    模板格式: /workpapers/{wp_id}?sheet={sheet_code}
    """
    # 尝试从 catalog 获取 jump_route_template
    cat = get_catalog()
    sheet_addr_id = f"{parent_wp_code}/{sheet_code}"
    sheet_entry = cat.sheets_by_addr_id.get(sheet_addr_id)

    if sheet_entry:
        template = sheet_entry.get("jump_route_template", "")
        if template:
            # 替换模板中的 {wp_id} 占位符
            return template.replace("{wp_id}", str(wp_id))

    # 默认路由模板
    return f"/workpapers/{wp_id}?sheet={sheet_code}"
