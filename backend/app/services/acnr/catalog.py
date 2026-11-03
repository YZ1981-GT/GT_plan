"""ACNR L1 GlobalCatalog — 只读 catalog 服务层

读取 `global_catalog.json`（懒加载 + 缓存），构建索引，
提供 list_sheets / list_cells / lookup / resolve（首期 L1 only）。

Requirements: 2.1, 2.2, 2.3, 2.4, 5.1, 5.3, 5.6, 23.4, 23.5
"""
from __future__ import annotations

import json
import logging
import os
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple

from app.services.acnr import catalog_integrity as _integrity
from app.services.acnr.catalog_integrity import use_catalog  # noqa: F401  门禁 / 测试经 catalog.use_catalog 调用

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _wp_name_index() -> dict[str, dict[str, str]]:
    """构建 {wp_code: {account_name, wp_name}} 索引，源自 wp_account_mapping.json。

    用于为 sheet 目录补充「科目简称」(account_name) 与「规范底稿名」(wp_name)，
    使导航树/选字段树可用「科目简称 + 名称」区分重名 sheet（如 D2 全部子表
    catalog 名重复为「应收账款实质性程序表」）。降级：加载失败返回空 dict 不阻断。
    """
    try:
        from app.services.wp_mapping_service import _load_mappings

        idx: dict[str, dict[str, str]] = {}
        for m in _load_mappings():
            code = m.get("wp_code")
            if not code:
                continue
            idx[code] = {
                "account_name": m.get("account_name") or m.get("wp_name") or "",
                "wp_name": m.get("wp_name") or "",
            }
        return idx
    except Exception as exc:  # pragma: no cover - 降级不阻断
        logger.warning("build wp_name_index failed: %s", exc)
        return {}


# 按文件 mtime 缓存 sheet_display_names.json（修改后无需重启即生效）
_SHEET_DISPLAY_CACHE: dict[str, dict[str, str]] = {}


def _sheet_display_names() -> dict[str, str]:
    """{sheet_code: 规范底稿名} 索引，源自 sheet_display_names.json。

    初值取自 workpaper_sheet_classification（每张 sheet 真实 tab 名以自身
    wp_code 结尾），现为手工维护的目录生成器输入（生成脚本已删除，T29）。作为
    wp_account_mapping 的兜底，补齐重名占位 sheet（如 D2-7~13/D4-14~36）的
    可区分名称。按 mtime 缓存：JSON 重生成后自动生效，无需重启。
    降级：文件缺失/加载失败返回空 dict 不阻断。
    """
    try:
        fp = Path(__file__).resolve().parents[3] / "data" / "acnr" / "sheet_display_names.json"
        if not fp.exists():
            return {}
        key = str(fp.stat().st_mtime_ns)
        cached = _SHEET_DISPLAY_CACHE.get(key)
        if cached is not None:
            return cached
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        data = data if isinstance(data, dict) else {}
        _SHEET_DISPLAY_CACHE.clear()  # 仅保留最新 mtime
        _SHEET_DISPLAY_CACHE[key] = data
        return data
    except Exception as exc:  # pragma: no cover - 降级不阻断
        logger.warning("load sheet_display_names failed: %s", exc)
        return {}


# ─── 异常定义 ──────────────────────────────────────────────────────────────────


class CatalogLoadError(Exception):
    """Catalog 加载失败且无可用的上一版缓存时抛出。

    触发此异常意味着操作整体失败，需人工介入。
    Requirements: R23.5
    """
    pass


class CatalogIntegrityError(CatalogLoadError):
    """目录自身完整性破坏（addr_id 重复 / 加载期互校不一致）时抛出。

    继承 `CatalogLoadError`，`_load_catalog` 的降级分支与 `load_versioned_catalog`
    按同一路径处理（§8 映射 409）。消息列前 10 个问题与总数。
    Requirements: design §5.5 / D4
    """
    pass

# ─── Catalog 数据路径 ───────────────────────────────────────────────────────
_CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "acnr" / "global_catalog.json"


# ─── 降级缓存（上一版成功加载的 catalog） ──────────────────────────────────────
_last_good_catalog: CatalogIndex | None = None


def _alert_admin(event_type: str, details: str) -> None:
    """向管理端发出告警（当前实现：日志 + 指标占位）。

    后续可接入运维告警系统（邮件/Slack/PagerDuty 等）。
    Requirements: R23.4, R23.5
    """
    logger.warning(
        "ACNR 管理告警 [%s]: %s",
        event_type,
        details,
    )
    # TODO: 接入实际运维告警系统（metrics / webhook）


class CatalogIndex:
    """内存索引，按需构建一次。"""

    def __init__(self, data: dict[str, Any]) -> None:
        self.version: str = data.get("version", "1")
        self.registry_version: str = data.get("registry_version", "unknown")

        sheets: list[dict] = data.get("sheets", [])
        cells: list[dict] = data.get("cells", [])

        # 主索引: addr_id → entry
        self.sheets_by_addr_id: dict[str, dict] = {}
        # sheet_code → list[entry]（可能多个 → ambiguous）
        self.sheets_by_code: dict[str, list[dict]] = {}
        # alias → list[sheet entry]
        self.sheets_by_alias: dict[str, list[dict]] = {}
        # parent_addr_id → list[cell entry]
        self.cells_by_parent: dict[str, list[dict]] = {}
        # cell addr_id → entry
        self.cells_by_addr_id: dict[str, dict] = {}
        # 父级 wp_code → 该父级下的 sheet 列表（§6.2 第 1 步用）
        self.sheets_by_parent: dict[str, list[dict]] = {}

        # fail-closed：三类 addr_id 重复（design §5.5）；sheet_code 重复不在此拦（解析时报歧义）。
        dup_problems = _integrity.duplicate_addr_id_problems(sheets, cells)
        if dup_problems:
            raise CatalogIntegrityError(_integrity.format_duplicate_problems(dup_problems))

        for s in sheets:
            aid = s.get("addr_id", "")
            self.sheets_by_addr_id[aid] = s

            code = s.get("sheet_code", "")
            self.sheets_by_code.setdefault(code, []).append(s)
            self.sheets_by_parent.setdefault(s.get("parent_wp_code", ""), []).append(s)

            # 别名索引（含 sheet_name 本身作为 alias key）
            name = s.get("sheet_name", "")
            if name:
                self.sheets_by_alias.setdefault(name, []).append(s)
            for alias in s.get("sheet_name_aliases", []):
                self.sheets_by_alias.setdefault(alias, []).append(s)

        for c in cells:
            aid = c.get("addr_id", "")
            self.cells_by_addr_id[aid] = c
            parent = c.get("parent_addr_id", "")
            self.cells_by_parent.setdefault(parent, []).append(c)

        # 禁止别名：同父一名多码 ∪ 顶层 alias_policy.forbidden（exact_identity 第 3 步优先读此属性）
        self.forbidden_aliases = _integrity.forbidden_alias_index(sheets, data.get("alias_policy"))
        # 加载期 release 互校状态（_load_catalog 写入；直接构造的索引为 None）
        self.release_check_status: str | None = None

        # 合并全部条目（sheet + cell）用于 fuzzy 搜索
        self._all_entries: list[dict] = sheets + cells


# ─── 全局 catalog 单例（懒加载） ─────────────────────────────────────────────
_catalog: CatalogIndex | None = None


def _load_catalog() -> CatalogIndex:
    """懒加载 catalog JSON 并构建索引，含降级处理。

    Branch 1: 加载失败但有旧缓存 → 只读上一版 + 管理端告警
              禁止静默退回分散 JSON（R23.4）
    Branch 2: 加载失败且无旧缓存 → 操作整体失败（R23.5）

    Requirements: R23.4, R23.5
    """
    global _catalog, _last_good_catalog
    if _catalog is not None:
        return _catalog

    catalog_path = Path(os.environ.get("ACNR_CATALOG_PATH", str(_CATALOG_PATH)))

    try:
        raw = catalog_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        release_status = _cross_check_release_report(catalog_path, raw, data)
        _catalog = CatalogIndex(data)
        _catalog.release_check_status = release_status
        _last_good_catalog = _catalog  # 保存为下次降级缓存
        logger.info(
            "ACNR catalog 加载完成: version=%s, sheets=%d, cells=%d, release_check=%s",
            _catalog.registry_version,
            len(_catalog.sheets_by_addr_id),
            len(_catalog.cells_by_addr_id),
            release_status,
        )
        return _catalog
    except (FileNotFoundError, json.JSONDecodeError, OSError, CatalogIntegrityError) as e:
        # Branch 1: 有旧缓存 → 只读上一版 + 告警
        if _last_good_catalog is not None:
            logger.error(
                "ACNR catalog 加载失败，降级为只读上一版: %s", e
            )
            event = (
                "catalog_integrity_failed"
                if isinstance(e, CatalogIntegrityError)
                else "catalog_load_failed"
            )
            _alert_admin(event, str(e))
            _catalog = _last_good_catalog
            return _catalog

        # Branch 2: 无旧缓存 → 操作整体失败，需人工介入
        logger.critical(
            "ACNR catalog 加载失败且无可用缓存，需人工介入: %s", e
        )
        _alert_admin("catalog_load_failed_no_cache", str(e))
        if isinstance(e, CatalogIntegrityError):
            raise
        raise CatalogLoadError(
            "Catalog 加载失败且不存在可用的上一版缓存，操作整体失败"
        ) from e


def _cross_check_release_report(catalog_path: Path, raw: str, data: dict[str, Any]) -> str:
    """加载期互校（规则见 catalog_integrity.check_release_report）：返回执行状态，
    问题即抛 CatalogIntegrityError。默认生产路径缺报告同样失败；其他目录缺报告跳过。"""
    is_default = catalog_path.resolve() == _CATALOG_PATH.resolve()
    status, problem = _integrity.check_release_report(
        catalog_path, raw, data, is_default_path=is_default
    )
    if problem:
        raise CatalogIntegrityError(problem)
    return status


def get_catalog() -> CatalogIndex:
    """获取 catalog 索引（已缓存）。use_catalog() 作用域内返回被覆盖的索引。"""
    override = _integrity.current_override()
    if override is not None:
        return override
    return _load_catalog()


def reload_catalog() -> CatalogIndex:
    """强制重新加载 catalog（用于测试或热重载）。"""
    global _catalog
    _catalog = None
    return _load_catalog()


# ─── 公共服务方法 ─────────────────────────────────────────────────────────────


def list_sheets(
    cycle: str | None = None,
    import_export_only: bool = False,
    include_deprecated: bool = False,
) -> list[dict]:
    """列出 sheet 目录条目，可按 cycle 和 import_export 过滤；停用条目默认不列（design §3.3）。

    Requirements: R14.1, R15.3
    """
    cat = get_catalog()
    result = list(cat.sheets_by_addr_id.values())

    if cycle:
        result = [s for s in result if s.get("cycle", "").upper() == cycle.upper()]
    if import_export_only:
        result = [s for s in result if s.get("import_export", {}).get("enabled")]
    if not include_deprecated:
        result = [s for s in result if not s.get("deprecated")]

    # 附加「科目简称」(account_name，取父底稿) 与「规范底稿名」(mapped_sheet_name，
    # 取本 sheet_code)，只增不改（统一显示名已由生成器写进 display_label，口径同 display.NameSources）。
    # 返回浅拷贝避免污染 catalog 缓存。
    # mapped_sheet_name 优先 wp_account_mapping 的策管名，兜底 classification 真名。
    name_idx = _wp_name_index()
    disp_names = _sheet_display_names()
    if name_idx or disp_names:
        enriched: list[dict] = []
        for s in result:
            sheet_code = s.get("sheet_code") or ""
            parent_meta = name_idx.get(s.get("parent_wp_code") or "", {})
            sheet_meta = name_idx.get(sheet_code, {})
            account_name = parent_meta.get("account_name") or sheet_meta.get("account_name") or ""
            mapped_name = sheet_meta.get("wp_name") or disp_names.get(sheet_code) or ""
            if account_name or mapped_name:
                enriched.append({**s, "account_name": account_name, "mapped_sheet_name": mapped_name})
            else:
                enriched.append(s)
        return enriched

    return result


def list_cells(sheet_addr_id: str) -> list[dict]:
    """列出某 sheet 下的所有 cell 条目。

    Requirements: R14.1, R15.3
    """
    cat = get_catalog()
    return cat.cells_by_parent.get(sheet_addr_id, [])


def lookup(
    wp_code: str | None = None,
    sheet: str | None = None,
    cell_desc: str | None = None,
) -> dict:
    """正向查找：按 wp_code / sheet_code / cell_desc 组合查询。

    返回统一响应契约 data 部分：
      - hit: {found:true, addr_id, entry_type, ...}
      - miss: {found:false, candidates:[...]}
      - ambiguous: {found:false, error:"ambiguous", candidates:[...]}

    Requirements: R2.1, R2.2, R2.3, R2.4
    """
    cat = get_catalog()

    # 1. 尝试按 sheet_code 精确查找
    if sheet:
        matches = cat.sheets_by_code.get(sheet, [])

        # 如果有 wp_code 约束，进一步过滤
        if wp_code and matches:
            matches = [m for m in matches if m.get("parent_wp_code") == wp_code]

        if len(matches) == 1:
            entry = matches[0]
            # 如果指定了 cell_desc，在该 sheet 下搜索 cell
            if cell_desc:
                return _lookup_cell_in_sheet(entry, cell_desc)
            return _hit_response(entry, "sheet")

        if len(matches) > 1:
            return _ambiguous_response(matches)

    # 2. 仅提供 wp_code 时：查找对应 parent_wp_code 的 sheets
    if wp_code and not sheet:
        matches = [
            s for s in cat.sheets_by_addr_id.values()
            if s.get("parent_wp_code") == wp_code
        ]
        if len(matches) == 1:
            entry = matches[0]
            if cell_desc:
                return _lookup_cell_in_sheet(entry, cell_desc)
            return _hit_response(entry, "sheet")
        if len(matches) > 1:
            # wp_code 下多个 sheet 是正常的（bundle），返回 ambiguous
            return _ambiguous_response(matches)

    # 3. 别名反查
    if sheet:
        alias_matches = cat.sheets_by_alias.get(sheet, [])
        if wp_code and alias_matches:
            alias_matches = [m for m in alias_matches if m.get("parent_wp_code") == wp_code]
        if len(alias_matches) == 1:
            entry = alias_matches[0]
            if cell_desc:
                return _lookup_cell_in_sheet(entry, cell_desc)
            return _hit_response(entry, "sheet")
        if len(alias_matches) > 1:
            return _ambiguous_response(alias_matches)

    # 4. Miss — 返回相近候选（≤5）
    query = " ".join(filter(None, [wp_code, sheet, cell_desc]))
    candidates = _find_candidates(query, max_results=5)
    return {"found": False, "candidates": candidates}


def resolve(
    uri: str | None = None,
    formula_ref: str | None = None,
    addr_id: str | None = None,
    index_ref: str | None = None,
) -> dict:
    """统一解析入口（首期 M0 只读 L1）。

    输入接受四种语法之一，输出统一响应契约。
    决策树（M0 精简版）：
      1. 规范化输入 → 推导 addr_id
      2. L1 Cell 精确 match
      3. L1 Sheet + aliases match
      4. miss → candidates ≤ 5

    Requirements: R5.1, R5.3, R5.5, R5.6
    """
    cat = get_catalog()
    resolved_addr_id: str | None = None

    # 1. 规范化输入 → 推导 addr_id
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
        query = uri or formula_ref or addr_id or index_ref or ""
        candidates = _find_candidates(query, max_results=5)
        return {"found": False, "candidates": candidates}

    # 2. L1 Cell 精确 match
    cell = cat.cells_by_addr_id.get(resolved_addr_id)
    if cell:
        return _hit_cell_response(cell)

    # 3. L1 Sheet 精确 match
    sheet_entry = cat.sheets_by_addr_id.get(resolved_addr_id)
    if sheet_entry:
        return _hit_response(sheet_entry, "sheet")

    # 4. 尝试按 sheet_code 部分匹配（addr_id 可能只有 sheet 部分）
    # 例如 addr_id="D2-2" 实际应该查 "D2/D2-2"
    parts = resolved_addr_id.split("/")
    if len(parts) == 1:
        # 可能是裸 sheet_code
        code_matches = cat.sheets_by_code.get(parts[0], [])
        if len(code_matches) == 1:
            return _hit_response(code_matches[0], "sheet")
        if len(code_matches) > 1:
            return _ambiguous_response(code_matches)

    # 5. miss
    candidates = _find_candidates(resolved_addr_id, max_results=5)
    return {"found": False, "candidates": candidates}


# ─── 内部辅助 ─────────────────────────────────────────────────────────────────


def _lookup_cell_in_sheet(sheet_entry: dict, cell_desc: str) -> dict:
    """在某个 sheet 下按 cell_desc 搜索 cell。"""
    cat = get_catalog()
    parent_id = sheet_entry.get("addr_id", "")
    cells = cat.cells_by_parent.get(parent_id, [])

    # 精确匹配 cell_address
    exact = [c for c in cells if c.get("cell_address") == cell_desc]
    if len(exact) == 1:
        return _hit_cell_response(exact[0])

    # semantic_label 包含匹配
    semantic = [c for c in cells if cell_desc in (c.get("semantic_label") or "")]
    if len(semantic) == 1:
        return _hit_cell_response(semantic[0])
    if len(semantic) > 1:
        return _ambiguous_response(semantic)

    # miss
    candidates = _find_candidates(
        f"{parent_id}/{cell_desc}",
        max_results=5,
        scope_entries=cells,
    )
    return {"found": False, "candidates": candidates}


def _hit_response(entry: dict, entry_type: str) -> dict:
    """构造命中响应（sheet 级）。"""
    result: dict[str, Any] = {
        "found": True,
        "addr_id": entry.get("addr_id"),
        "entry_type": entry_type,
        "sheet_name": entry.get("sheet_name"),
        "parent_wp_code": entry.get("parent_wp_code"),
        "sheet_code": entry.get("sheet_code"),
    }
    # 附带 import_export 信息（如有）
    ie = entry.get("import_export")
    if ie:
        result["import_export"] = ie
    return result


def _hit_cell_response(cell: dict) -> dict:
    """构造命中响应（cell 级）。"""
    return {
        "found": True,
        "addr_id": cell.get("addr_id"),
        "entry_type": "cell",
        "cell_address": cell.get("cell_address"),
        "semantic_label": cell.get("semantic_label"),
        "formula_ref": cell.get("formula_ref"),
        "uri": cell.get("uri"),
        "jump_route": _build_jump_route(cell),
    }


def _ambiguous_response(entries: list[dict]) -> dict:
    """构造 ambiguous 响应。"""
    candidates = [
        {
            "addr_id": e.get("addr_id"),
            "display_label": e.get("display_label") or e.get("sheet_name") or e.get("semantic_label") or e.get("addr_id"),
            "score": 1.0,
        }
        for e in entries
    ]
    return {"found": False, "error": "ambiguous", "candidates": candidates}


def _find_candidates(
    query: str,
    max_results: int = 5,
    scope_entries: list[dict] | None = None,
) -> list[dict]:
    """模糊搜索候选项（≤ max_results）。"""
    if not query:
        return []

    cat = get_catalog()
    entries = scope_entries if scope_entries is not None else cat._all_entries
    query_lower = query.lower()

    scored: list[tuple[float, dict]] = []
    for e in entries:
        # 取多个字段做比较
        targets = [
            e.get("addr_id", ""),
            e.get("sheet_code", ""),
            e.get("sheet_name", ""),
            e.get("semantic_label", ""),
            e.get("cell_address", ""),
        ]
        # 别名也参与
        for alias in e.get("sheet_name_aliases", []):
            targets.append(alias)

        best_score = 0.0
        for t in targets:
            if not t:
                continue
            t_lower = t.lower()
            # 前缀匹配加分
            if t_lower.startswith(query_lower) or query_lower.startswith(t_lower):
                score = 0.8
            else:
                score = SequenceMatcher(None, query_lower, t_lower).ratio()
            best_score = max(best_score, score)

        if best_score > 0.3:
            scored.append((best_score, e))

    scored.sort(key=lambda x: -x[0])
    return [
        {
            "addr_id": e.get("addr_id"),
            "display_label": e.get("display_label") or e.get("sheet_name") or e.get("semantic_label") or e.get("addr_id"),
            "score": round(score, 3),
        }
        for score, e in scored[:max_results]
    ]


def _build_jump_route(cell: dict) -> str | None:
    """从 cell 条目构建 jump_route。"""
    cat = get_catalog()
    parent_id = cell.get("parent_addr_id", "")
    parent = cat.sheets_by_addr_id.get(parent_id)
    if parent:
        template = parent.get("jump_route_template", "")
        # M0 不填 wp_id（无 ProjectBinding），保留模板
        return template
    return None


class RefIdentity(NamedTuple):
    """写法 → 身份的结构化结果（design §6.2，T10）。

    addr_id：推导出的地址（未命中为 None）；match：`exact_identity.sheet_of` 的判定
    （非 WP 写法、无 sheet 段或 custom_flat 时为 None）。`blocked` 为真（多义 / 命中禁止别名）时
    调用方须把 match 直接作为结果，不得再按别的规则猜。
    """

    addr_id: str | None
    match: Any = None

    @property
    def blocked(self) -> bool:
        return self.match is not None and self.match.state in ("ambiguous", "alias_forbidden")


def _parse_quoted_args(formula_ref: str) -> list[str]:
    """提取 WP(...) / PREV(...) 里单引号包围的参数。"""
    try:
        args_str = formula_ref[formula_ref.index("(") + 1: formula_ref.rindex(")")]
    except ValueError:
        return []
    args: list[str] = []
    in_quote = False
    current = ""
    for ch in args_str:
        if ch == "'":
            if in_quote:
                args.append(current)
                current = ""
            in_quote = not in_quote
        elif in_quote:
            current += ch
    return args


def _custom_flat(cat: CatalogIndex, wp_code: str, cell: str) -> str | None:
    """custom_flat 语法 `WP('{sheet_code}','{cell}')` / `wp://{sheet_code}#{cell}`：编码在目录内唯一才成立。"""
    matches = cat.sheets_by_code.get(wp_code, [])
    return f"{matches[0]['addr_id']}/{cell}" if len(matches) == 1 else None


def _sheet_match(cat: CatalogIndex, parent: str, text: str):
    from app.services.acnr.exact_identity import sheet_of

    return sheet_of(parent, text, index=cat)


def _uri_to_sheet_match(uri: str, *, index: CatalogIndex | None = None) -> RefIdentity:
    """从 URI 推导身份（sheet 判定只用 exact_identity，删去子串与拼接启发式）。

    standard: wp://{parent}/{sheet}#{cell} → {sheet.addr_id}/{cell}
    custom_flat: wp://{sheet_code}#{cell}
    """
    if not uri.startswith("wp://"):
        return RefIdentity(None)
    cat = index if index is not None else get_catalog()
    body = uri[5:]
    path_part, _, cell_part = body.rpartition("#") if "#" in body else (body, "", "")
    parts = path_part.split("/")
    if len(parts) == 2:
        sm = _sheet_match(cat, parts[0], parts[1])
        if not sm.ok:
            return RefIdentity(None, sm)
        sheet_addr = sm.entry["addr_id"]
        return RefIdentity(f"{sheet_addr}/{cell_part}" if "#" in body else sheet_addr, sm)
    if len(parts) == 1:
        if "#" in body:
            return RefIdentity(_custom_flat(cat, parts[0], cell_part))
        return RefIdentity(parts[0])  # 裸 wp_code（由后续按 sheet_code 查找）
    return RefIdentity(None)


def _formula_ref_to_sheet_match(formula_ref: str, *, index: CatalogIndex | None = None) -> RefIdentity:
    """从 formula_ref 推导身份（sheet 判定只用 exact_identity）。

    WP('D2','明细表D2-2','E100') → D2/D2-2/E100；WP('D2','D2-2') → D2/D2-2；
    WP('D2-2','E100') → custom_flat。父级不在目录（自定义底稿，wp_not_in_catalog）时原样拼成
    `{第一参}/…` 交给 L3 运行时条目匹配——这不是对目录的猜测；父级在目录内而表找不到即未命中。
    """
    if not formula_ref.startswith("WP(") and not formula_ref.startswith("PREV("):
        return RefIdentity(None)
    args = _parse_quoted_args(formula_ref)
    if len(args) not in (2, 3):
        return RefIdentity(None)
    cat = index if index is not None else get_catalog()
    sm = _sheet_match(cat, args[0], args[1])
    if sm.ok:
        sheet_addr = sm.entry["addr_id"]
        return RefIdentity(f"{sheet_addr}/{args[2]}" if len(args) == 3 else sheet_addr, sm)
    if sm.state == "wp_not_in_catalog":
        return RefIdentity("/".join(args), sm)
    if len(args) == 2 and sm.state == "not_found":
        flat = _custom_flat(cat, args[0], args[1])
        if flat:
            return RefIdentity(flat)
    return RefIdentity(None, sm)


def _uri_to_addr_id(uri: str) -> str | None:
    """薄壳（原签名）：多义 / 禁止别名 / 未命中返回 None。"""
    return _uri_to_sheet_match(uri).addr_id


def _formula_ref_to_addr_id(formula_ref: str) -> str | None:
    """薄壳（原签名）：多义 / 禁止别名 / 未命中返回 None。"""
    return _formula_ref_to_sheet_match(formula_ref).addr_id


def _index_ref_to_addr_id(index_ref: str, *, index: CatalogIndex | None = None) -> str | None:
    """从索引命名空间语法推导 addr_id。

    cell:D2-2!E100 → D2/D2-2/E100
    wp:D2-2 → D2/D2-2
    sheet:D2-2 → D2/D2-2
    TB:1001 → 非 wp 域，首期返回 None（委托 V1）
    """
    if ":" not in index_ref:
        return None

    ns, target = index_ref.split(":", 1)
    ns_lower = ns.lower()
    cat = index if index is not None else get_catalog()

    if ns_lower == "cell":
        # cell:D2-2!E100 → sheet_code=D2-2, cell=E100
        if "!" in target:
            sheet_code, cell = target.split("!", 1)
            return _custom_flat(cat, sheet_code, cell)
        return None

    elif ns_lower in ("wp", "sheet"):
        # wp:D2-2 / sheet:D2-2 → sheet_code=D2-2
        matches = cat.sheets_by_code.get(target, [])
        if len(matches) == 1:
            return matches[0]["addr_id"]
        return None

    # TB/Note/Adj/Att/EQCR/Calc/Sample/Confirm → 非 wp 域，M0 不解析
    return None
