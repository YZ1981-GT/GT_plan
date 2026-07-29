"""公式预设库读取/收敛适配层（Formula Management Library · preset_library）。

本模块把平台已有的三处分散预设**收敛到统一预设库口径**（Task 14.1 / Req 22.3），
并提供 Preset Inventory（逐页登记）与覆盖度（presetted/pending 分布）的读取能力：

三处收敛源（**单一真源，读时收敛，不复制不漂移**）：

1. ``prefill_formula_mapping.json``  —— 审定表/明细表预填公式（``mappings[].cells[]``：
   ``cell_ref`` / ``formula`` / ``formula_type`` ∈ {TB, TB_SUM, ADJ, PREV, WP}）。
   这些均为**计算并回填**语义 → 统一映射为 ``auto_calc``。page_key = ``workpaper:{wp_code}``。
2. ``note_check_preset_formulas.json`` —— 附注勾稽/汇总预设（``soe`` / ``listed``：
   ``id`` / ``note_section`` / ``category`` ∈ {logic_check, auto_calc} / ``formula``）。
   page_key = ``note:{note_section}``。
3. 宽表公式预设（MD，``load_wide_table_presets``）—— 附注宽表横向/纵向公式。
   横向（期初+增-减=期末）与纵向（明细之和=合计）平衡校验 → ``auto_calc``（回填/校验）。
   page_key = ``note:{section_code}``。

统一预设条目（PresetEntry）字段：``page_key`` / ``target_cell`` / ``expression`` /
``formula_type``（三类型 auto_calc/logic_check/reasonability）/ ``refs``（ACNR
``addr_id`` 或 ``formula_ref``，经 ``full_resolve`` 可解析，禁裸坐标串，Req 22.7）/
``source`` / ``description``。

预设库 = ``formula_presets_seed.json``（**新增/显式**预设，如报表勾稽 logic_check）
∪ 上述三源**读时收敛**结果，按 ``(page_key, target_cell)`` **去重**（Req 22.3）。

Requirements: 22.1, 22.3, 22.5, 22.7
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# ── 目录常量 ──────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
PRESET_DIR = DATA_DIR / "formula_presets"
INVENTORY_PATH = PRESET_DIR / "inventory.json"
SEED_PATH = PRESET_DIR / "formula_presets_seed.json"
# 自定义预设隔离存储（与致同基线 seed 分离，平台级共享；template-library-formula-preset-custom）
CUSTOM_PATH = PRESET_DIR / "formula_custom_presets.json"

# 三类型枚举（与 engine.FormulaRecord.formula_type 一致）
VALID_FORMULA_TYPES = {"auto_calc", "logic_check", "reasonability"}

# prefill formula_type（TB/TB_SUM/ADJ/PREV/WP）→ 三类型：均为"计算回填" → auto_calc
_PREFILL_TYPE_TO_TRITYPE = "auto_calc"


# ── 统一预设条目模型 ──────────────────────────────────────────────────────────
@dataclass
class PresetEntry:
    """统一预设条目（跨底稿/报表/附注的单一口径）。"""

    page_key: str
    target_cell: str
    expression: str
    formula_type: str  # auto_calc | logic_check | reasonability
    refs: list[Any] = field(default_factory=list)
    source: str = "manual"
    description: str = ""
    variant: str | None = None  # soe / listed / None（宽表/报表无变体）

    def dedup_key(self) -> tuple[str, str]:
        """去重键：(page_key, target_cell)（Req 22.3）。"""
        return (self.page_key, self.target_cell)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "page_key": self.page_key,
            "target_cell": self.target_cell,
            "expression": self.expression,
            "formula_type": self.formula_type,
            "refs": self.refs,
            "source": self.source,
            "description": self.description,
        }
        if self.variant:
            d["variant"] = self.variant
        return d


@dataclass
class PresetPage:
    """Preset Inventory 中的一页登记项（承载公式的页面/sheet）。"""

    page_key: str
    scope: str  # workpaper | report | note
    preset_status: str  # presetted | pending
    formula_count: int = 0
    cycle: str | None = None
    wp_code: str | None = None
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "page_key": self.page_key,
            "scope": self.scope,
            "preset_status": self.preset_status,
            "formula_count": self.formula_count,
        }
        if self.cycle:
            d["cycle"] = self.cycle
        if self.wp_code:
            d["wp_code"] = self.wp_code
        if self.sources:
            d["sources"] = sorted(set(self.sources))
        return d


# ── JSON 安全读取 ─────────────────────────────────────────────────────────────
def _safe_load_json(path: Path) -> Any:
    if not path.exists():
        logger.warning("preset source missing: %s", path)
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("failed to load preset source %s: %s", path, exc)
        return None


def _map_formula_type(raw: str | None, default: str) -> str:
    """把来源 formula_type/category 归一化到三类型，未知回退 default。"""
    if raw and raw in VALID_FORMULA_TYPES:
        return raw
    return default


def _formula_ref_from_expr(formula: str | None) -> list[dict[str, str]]:
    """从 ``=TB('..')`` 形态的 formula 提取并**归一化**为 ACNR ``formula_ref``。

    formula_ref 经 ACNR ``grammar_v1`` 归一化（旧格式 ``TB_SUM``→``SUM_TB`` /
    ``TB_AUX``→``AUX``），使其经 ``full_resolve`` 可解析（Req 22.7 / Req 24.1、24.4）；
    此处不拼接裸 ``wp_code+sheet+cell`` 串（Req 11.5）。每项附带 ``acnr_status``
    （``migrated`` / ``pending``）供模板库 Ledger 标注待迁移项（Req 24.3）。
    """
    if not formula or not isinstance(formula, str):
        return []
    from app.services.formula_management.preset_acnr_migration import normalize_ref

    ref = normalize_ref(formula).to_ref_dict()
    return [ref] if ref else []


# ── 收敛源 1：prefill_formula_mapping ────────────────────────────────────────
def convert_prefill_presets() -> list[PresetEntry]:
    """收敛 ``prefill_formula_mapping.json`` → 预设条目（Req 22.3）。"""
    data = _safe_load_json(DATA_DIR / "prefill_formula_mapping.json")
    if not isinstance(data, dict):
        return []
    entries: list[PresetEntry] = []
    for m in data.get("mappings", []) or []:
        wp_code = (m.get("wp_code") or "").strip()
        if not wp_code:
            continue
        page_key = f"workpaper:{wp_code}"
        cycle = wp_code[0] if wp_code and wp_code[0].isalpha() else None
        for cell in m.get("cells", []) or []:
            cell_ref = (cell.get("cell_ref") or "").strip()
            formula = cell.get("formula") or ""
            if not cell_ref or not formula:
                continue
            entries.append(
                PresetEntry(
                    page_key=page_key,
                    target_cell=cell_ref,
                    expression=formula,
                    formula_type=_PREFILL_TYPE_TO_TRITYPE,
                    refs=_formula_ref_from_expr(formula),
                    source="prefill_formula_mapping",
                    description=cell.get("description") or "",
                    variant=None,
                )
            )
    return entries


# ── 收敛源 2：note_check_preset_formulas ─────────────────────────────────────
def convert_check_presets() -> list[PresetEntry]:
    """收敛 ``note_check_preset_formulas.json`` → 预设条目（Req 22.3）。"""
    data = _safe_load_json(DATA_DIR / "note_check_preset_formulas.json")
    if not isinstance(data, dict):
        return []
    entries: list[PresetEntry] = []
    for variant in ("soe", "listed"):
        for item in data.get(variant, []) or []:
            note_section = (item.get("note_section") or "").strip()
            item_id = (item.get("id") or "").strip()
            formula = item.get("formula") or ""
            if not note_section or not item_id or not formula:
                continue
            entries.append(
                PresetEntry(
                    page_key=f"note:{note_section}",
                    # 同一 section 下多条以 id 区分承载单元，附加 variant 避免 soe/listed 撞键
                    target_cell=f"{item_id}@{variant}",
                    expression=formula,
                    formula_type=_map_formula_type(item.get("category"), "logic_check"),
                    refs=[],  # 附注自然语言公式，ACNR addr_id 化留 Task 14.3 增量
                    source="check_presets",
                    description=item.get("description") or "",
                    variant=variant,
                )
            )
    return entries


# ── 收敛源 3：宽表公式预设（MD） ──────────────────────────────────────────────
def convert_wide_table_presets() -> list[PresetEntry]:
    """收敛宽表公式预设（``load_wide_table_presets``）→ 预设条目（Req 22.3）。

    宽表 MD 缺失时容错返回空（无回归）。
    """
    try:
        from app.services.note_wide_table_engine import load_wide_table_presets
    except Exception as exc:  # noqa: BLE001
        logger.warning("wide_table_presets 收敛不可用: %s", exc)
        return []

    entries: list[PresetEntry] = []
    for variant in ("soe", "listed"):
        try:
            presets = load_wide_table_presets(variant)
        except Exception as exc:  # noqa: BLE001
            logger.warning("load_wide_table_presets(%s) 失败: %s", variant, exc)
            continue
        for p in presets or []:
            section_code = (getattr(p, "section_code", "") or "").strip()
            if not section_code:
                continue
            ftype_raw = getattr(p, "formula_type", "horizontal")
            expr = getattr(p, "expression", "") or ""
            table_name = getattr(p, "table_name", "") or ""
            # 横向/纵向平衡与汇总均为"计算/校验回填"语义 → auto_calc
            entries.append(
                PresetEntry(
                    page_key=f"note:{section_code}",
                    target_cell=f"widetable:{ftype_raw}:{table_name or 'default'}@{variant}",
                    expression=expr,
                    formula_type="auto_calc",
                    refs=[],
                    source="wide_table_presets",
                    description=getattr(p, "description", "") or "",
                    variant=variant,
                )
            )
    return entries


# ── 显式 seed（新增预设，如报表勾稽 logic_check） ─────────────────────────────
def load_seed_presets() -> list[PresetEntry]:
    """读取 ``formula_presets_seed.json`` 的显式预设条目。"""
    data = _safe_load_json(SEED_PATH)
    if not isinstance(data, dict):
        return []
    entries: list[PresetEntry] = []
    for p in data.get("presets", []) or []:
        page_key = (p.get("page_key") or "").strip()
        target_cell = (p.get("target_cell") or "").strip()
        expression = p.get("expression") or ""
        if not page_key or not target_cell:
            continue
        entries.append(
            PresetEntry(
                page_key=page_key,
                target_cell=target_cell,
                expression=expression,
                formula_type=_map_formula_type(p.get("formula_type"), "auto_calc"),
                refs=list(p.get("refs") or []),
                source=p.get("source") or "seed",
                description=p.get("description") or "",
                variant=p.get("variant"),
            )
        )
    return entries


# ── 自定义预设（用户在致同基线之上新增，隔离存储，平台级共享） ────────────────
def load_custom_presets() -> list[PresetEntry]:
    """读取 ``formula_custom_presets.json`` 的自定义预设条目（``source='custom'``）。

    镜像 ``load_seed_presets``：文件缺失/损坏/空 → 返回 ``[]``（容错，不阻断
    ``build_preset_library``）。自定义与显式 seed 同属**显式预设源**，但存于**隔离
    文件**（``upsert_custom_presets`` 绝不触碰 seed，Property 2）。
    """
    data = _safe_load_json(CUSTOM_PATH)
    if not isinstance(data, dict):
        return []
    entries: list[PresetEntry] = []
    for p in data.get("presets", []) or []:
        page_key = (p.get("page_key") or "").strip()
        target_cell = (p.get("target_cell") or "").strip()
        expression = p.get("expression") or ""
        if not page_key or not target_cell:
            continue
        entries.append(
            PresetEntry(
                page_key=page_key,
                target_cell=target_cell,
                expression=expression,
                formula_type=_map_formula_type(p.get("formula_type"), "auto_calc"),
                refs=list(p.get("refs") or []),
                source="custom",  # 强制 custom（隔离来源标注，Property 3）
                description=p.get("description") or "",
                variant=p.get("variant"),
            )
        )
    return entries


# ── 合并 + 去重（Req 22.3） ──────────────────────────────────────────────────
def build_preset_library(
    *, include_sources: bool = True
) -> tuple[list[PresetEntry], dict[str, int]]:
    """构建统一预设库：custom ∪ seed ∪ 收敛源，按 ``(page_key, target_cell)`` 去重。

    **自定义（custom）置于最前** → 同 ``(page_key, target_cell)`` 键覆盖通用（seed/
    收敛源），"去重首个赢"（Property 4）。显式 seed 次之，收敛源最后；相同去重键的
    后来者跳过（skipped）。

    **🔴 custom 与 ``include_sources`` 正交、恒前置**：``include_sources`` 只控制
    prefill/check/wide_table 三个**收敛源**是否并入；custom 与 seed 同属**显式预设源**，
    两个分支都含。零回归依据 = custom 初始为空（空 custom 使 ``[custom=[], seed, ...]``
    去重结果与改前 ``[seed, ...]`` 逐字节一致，Property 7）。

    Returns:
        (entries, stats)；stats 含 ``inserted`` / ``skipped`` / 各 source 计数。
    """
    ordered: list[Iterable[PresetEntry]] = [load_custom_presets(), load_seed_presets()]
    if include_sources:
        ordered.extend(
            [
                convert_prefill_presets(),
                convert_check_presets(),
                convert_wide_table_presets(),
            ]
        )

    seen: set[tuple[str, str]] = set()
    result: list[PresetEntry] = []
    stats: dict[str, int] = {"inserted": 0, "skipped": 0}
    for group in ordered:
        for entry in group:
            key = entry.dedup_key()
            src_key = f"source:{entry.source}"
            if key in seen:
                stats["skipped"] += 1
                continue
            seen.add(key)
            result.append(entry)
            stats["inserted"] += 1
            stats[src_key] = stats.get(src_key, 0) + 1
    return result, stats


# ── Preset Inventory 构建（逐页登记，Req 22.1） ───────────────────────────────
def _scope_of(page_key: str) -> str:
    return page_key.split(":", 1)[0] if ":" in page_key else "unknown"


def build_inventory(entries: list[PresetEntry] | None = None) -> list[PresetPage]:
    """从预设库条目聚合逐页登记（page_key → formula_count + sources）。

    出现在预设库中的页面标 ``presetted``（Req 22.1）；``pending``（承载公式但
    未预设）由覆盖度视图在运行时对照页面全集派生（见 ``compute_preset_coverage``）。
    """
    if entries is None:
        entries, _ = build_preset_library()

    pages: dict[str, PresetPage] = {}
    for e in entries:
        page = pages.get(e.page_key)
        if page is None:
            scope = _scope_of(e.page_key)
            wp_code = None
            cycle = None
            if scope == "workpaper":
                wp_code = e.page_key.split(":", 1)[1]
                cycle = wp_code[0] if wp_code and wp_code[0].isalpha() else None
            page = PresetPage(
                page_key=e.page_key,
                scope=scope,
                preset_status="presetted",
                formula_count=0,
                cycle=cycle,
                wp_code=wp_code,
                sources=[],
            )
            pages[e.page_key] = page
        page.formula_count += 1
        page.sources.append(e.source)

    return sorted(pages.values(), key=lambda p: (p.scope, p.page_key))


# ── 按 page_key 查预设（一键刷新/底稿生成套用，Req 22.4） ─────────────────────
def build_preset_index(
    entries: list[PresetEntry] | None = None,
) -> dict[str, list[PresetEntry]]:
    """把预设库条目按 ``page_key`` 建索引（一次构建，多次按页查询）。

    供一键刷新 / 底稿生成按 page_key 批量套用预设时避免逐页扫全表（Req 22.4）。
    同一 page_key 下的多条预设按其在预设库中的顺序保留（显式 seed 优先于收敛源）。
    """
    if entries is None:
        entries, _ = build_preset_library()
    index: dict[str, list[PresetEntry]] = {}
    for e in entries:
        index.setdefault(e.page_key, []).append(e)
    return index


def find_presets_for_page(
    page_key: str,
    *,
    entries: list[PresetEntry] | None = None,
    index: dict[str, list[PresetEntry]] | None = None,
) -> list[PresetEntry]:
    """查某页面（page_key）的预设条目；无预设返回空列表（页面为 pending，Req 22.6）。

    Args:
        page_key: 页面/sheet 标识（``workpaper:{wp_code}`` / ``report:{...}`` / ``note:{...}``）。
        entries: 预设库条目（缺省则构建）；给定 ``index`` 时忽略。
        index: 预先构建的 page_key 索引（批量查询时传入以复用，见 ``build_preset_index``）。

    Returns:
        该页面的预设条目列表（可能多条）；页面未预设时为空列表（调用方据此跳过，无回归）。
    """
    if index is not None:
        return list(index.get(page_key, []))
    if entries is None:
        entries, _ = build_preset_library()
    return [e for e in entries if e.page_key == page_key]


def is_page_presetted(
    page_key: str,
    *,
    entries: list[PresetEntry] | None = None,
    index: dict[str, list[PresetEntry]] | None = None,
) -> bool:
    """页面是否已预设（预设库中存在该 page_key 的条目）。

    ``True`` → presetted（可套用预设为初稿公式）；``False`` → pending（跳过保留现状，Req 22.6）。
    """
    return bool(find_presets_for_page(page_key, entries=entries, index=index))


# ── 覆盖度（presetted/pending 分布，Req 22.5） ────────────────────────────────
def compute_preset_coverage(
    *,
    eligible_workpaper_codes: Iterable[str] | None = None,
    entries: list[PresetEntry] | None = None,
) -> dict[str, Any]:
    """计算预设覆盖度：presetted/pending 分布（供 ``get_formula_coverage`` 扩展）。

    Args:
        eligible_workpaper_codes: 应承载公式的底稿主编码全集（univer/hybrid），
            用于派生 workpaper 域的 pending（应预设但未预设）。缺省则仅报 presetted。
        entries: 预设库条目（缺省则构建）。

    Returns:
        {
          "total_preset_pages", "total_preset_formulas",
          "by_status": {"presetted", "pending"},
          "by_scope": [{scope, presetted_pages, pending_pages, total_pages,
                        coverage_percent, formula_count}, ...],
        }
    """
    if entries is None:
        entries, _ = build_preset_library()

    inventory = build_inventory(entries)

    # 按 scope 聚合 presetted 页数 + 公式数
    scope_presetted: dict[str, int] = {}
    scope_formula: dict[str, int] = {}
    presetted_wp_codes: set[str] = set()
    for page in inventory:
        scope_presetted[page.scope] = scope_presetted.get(page.scope, 0) + 1
        scope_formula[page.scope] = scope_formula.get(page.scope, 0) + page.formula_count
        if page.scope == "workpaper" and page.wp_code:
            presetted_wp_codes.add(page.wp_code)

    # workpaper pending = 应承载公式的主编码 − 已预设主编码
    scope_pending: dict[str, int] = {}
    if eligible_workpaper_codes is not None:
        eligible = {c for c in eligible_workpaper_codes if c}
        scope_pending["workpaper"] = len(eligible - presetted_wp_codes)

    all_scopes = sorted(set(scope_presetted) | set(scope_pending))
    by_scope: list[dict[str, Any]] = []
    total_presetted = 0
    total_pending = 0
    for scope in all_scopes:
        presetted = scope_presetted.get(scope, 0)
        pending = scope_pending.get(scope, 0)
        total = presetted + pending
        total_presetted += presetted
        total_pending += pending
        by_scope.append(
            {
                "scope": scope,
                "presetted_pages": presetted,
                "pending_pages": pending,
                "total_pages": total,
                "coverage_percent": (
                    round(presetted / total * 100, 1) if total > 0 else 0.0
                ),
                "formula_count": scope_formula.get(scope, 0),
            }
        )

    return {
        "total_preset_pages": len(inventory),
        "total_preset_formulas": len(entries),
        "by_status": {"presetted": total_presetted, "pending": total_pending},
        "by_scope": by_scope,
    }


# ── 显式 seed 幂等 upsert（导入回填，Req 23.4「有效项入库」） ─────────────────
def upsert_seed_presets(entries: list[PresetEntry]) -> dict[str, int]:
    """把导入的有效预设条目幂等写入 ``formula_presets_seed.json``（Req 23.4）。

    按 ``(page_key, target_cell)`` 去重更新（遵循 ``seed_note_account_mappings``
    幂等模式）：已存在则覆盖表达式/类型/引用/说明，不存在则追加。仅写入**收敛源
    之外**的显式 seed 文件，不触碰 prefill/check/wide_table 三源（读时收敛）。

    Returns:
        stats：``{"inserted": n, "updated": m, "total": k}``。
    """
    data = _safe_load_json(SEED_PATH)
    if not isinstance(data, dict):
        data = {
            "description": "公式预设库显式种子（新增预设条目）。",
            "version": "2025-R1",
            "presets": [],
        }
    presets: list[dict[str, Any]] = list(data.get("presets") or [])

    # 现有条目按去重键建索引
    index: dict[tuple[str, str], int] = {}
    for i, p in enumerate(presets):
        key = ((p.get("page_key") or "").strip(), (p.get("target_cell") or "").strip())
        index[key] = i

    inserted = 0
    updated = 0
    for entry in entries:
        key = entry.dedup_key()
        payload = entry.to_dict()
        if key in index:
            presets[index[key]] = payload
            updated += 1
        else:
            index[key] = len(presets)
            presets.append(payload)
            inserted += 1

    data["presets"] = presets
    try:
        PRESET_DIR.mkdir(parents=True, exist_ok=True)
        SEED_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        logger.error("写入预设 seed 失败 %s: %s", SEED_PATH, exc)
        raise

    return {"inserted": inserted, "updated": updated, "total": len(presets)}


# ── 自定义预设幂等 upsert（平台级自定义写入，隔离于 seed） ────────────────────
def upsert_custom_presets(entries: list[PresetEntry]) -> dict[str, int]:
    """把自定义预设条目幂等写入 ``formula_custom_presets.json``（隔离于 seed）。

    镜像 ``upsert_seed_presets`` 的幂等语义（按 ``(page_key, target_cell)`` 覆盖/追加），
    但**只写 ``formula_custom_presets.json``，绝不触碰 ``formula_presets_seed.json``**
    （Property 2）。写入条目 ``source`` 一律标 ``custom``。

    Returns:
        stats：``{"inserted": n, "updated": m, "total": k}``。
    """
    data = _safe_load_json(CUSTOM_PATH)
    if not isinstance(data, dict):
        data = {
            "description": "公式预设库自定义条目（用户在致同通用基线之上新增，与 formula_presets_seed.json 隔离，平台级共享）。",
            "version": "2025-R1",
            "presets": [],
        }
    presets: list[dict[str, Any]] = list(data.get("presets") or [])

    index: dict[tuple[str, str], int] = {}
    for i, p in enumerate(presets):
        key = ((p.get("page_key") or "").strip(), (p.get("target_cell") or "").strip())
        index[key] = i

    inserted = 0
    updated = 0
    for entry in entries:
        key = entry.dedup_key()
        payload = entry.to_dict()
        payload["source"] = "custom"  # 隔离来源标注（Property 3）
        if key in index:
            presets[index[key]] = payload
            updated += 1
        else:
            index[key] = len(presets)
            presets.append(payload)
            inserted += 1

    data["presets"] = presets
    try:
        PRESET_DIR.mkdir(parents=True, exist_ok=True)
        CUSTOM_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        logger.error("写入自定义预设失败 %s: %s", CUSTOM_PATH, exc)
        raise

    return {"inserted": inserted, "updated": updated, "total": len(presets)}
