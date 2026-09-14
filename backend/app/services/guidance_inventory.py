"""编制说明清册、九段契约与 sheet 身份解析。

本模块只分析已有权威输入，不生成业务文案。legacy guidance 可以继续展示，
但缺段或缺 source_ref 时必须保持 ``missing``，不能计入 exact 完成数。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Sequence

from app.services.guidance_source_refs import SourceRefContext, validate_source_refs

GUIDANCE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "wp_guidance"

CANONICAL_SECTION_KEYS: tuple[str, ...] = (
    "purpose",
    "materials",
    "data_sources",
    "steps",
    "formulas",
    "judgments",
    "evidence",
    "common_errors",
    "completion",
)

_SECTION_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("purpose", ("编制目的", "适用范围", "目的", "本表用途", "本表目的")),
    ("materials", ("资料准备", "所需资料", "准备资料", "原始凭证")),
    ("data_sources", ("数据来源", "取数来源", "来源")),
    (
        "steps",
        (
            "编制步骤",
            "操作步骤",
            "检查要素",
            "执行程序",
            "使用方法",
            "测试方法与程序",
            "测试方法",
        ),
    ),
    ("formulas", ("计算公式", "公式", "计算口径", "检查比例", "偏差率计算")),
    (
        "judgments",
        ("审计判断", "判断", "适用条件", "重要性", "抽样", "常见波动原因分类"),
    ),
    (
        "evidence",
        ("审计证据", "证据", "索引", "凭证要求", "与其他底稿的关联", "与其他底稿关联"),
    ),
    ("common_errors", ("常见错误", "异常处理", "易错", "注意事项")),
    ("completion", ("完成标准", "审计结论", "完成条件", "结论")),
)

# 支持 D0A、D0-4b、C1-4-4、F1-CONF；保留数字后的语义小写后缀。
_SHEET_CODE_TOKEN = r"[A-Z]\d+(?:[A-Z])?(?:-\d+[a-z]?)*(?:-[A-Z]+)?"
SHEET_CODE_RE = re.compile(rf"(?<![A-Za-z0-9])({_SHEET_CODE_TOKEN})(?![A-Za-z0-9])")


GuidanceSourceRefState = Literal[
    "valid",
    "missing",
    "invalid",
    "stale",
    "cross_template",
    "unvalidated",
]
GuidanceExactStatus = Literal["exact", "missing", "invalid", "stale"]


@dataclass(frozen=True)
class GuidanceSectionSourceValidation:
    section_key: str
    status: GuidanceSourceRefState
    facts_digest: str
    issue_codes: tuple[str, ...]


@dataclass(frozen=True)
class GuidanceDocumentAnalysis:
    wp_code: str
    schema_version: int
    present_sections: tuple[str, ...]
    missing_sections: tuple[str, ...]
    sections_without_source_ref: tuple[str, ...]
    duplicate_sections: tuple[str, ...]
    unmapped_section_count: int
    exact_blockers: tuple[str, ...]
    status: GuidanceExactStatus
    source_ref_status: GuidanceSourceRefState
    source_ref_facts_digest: str
    source_ref_issues: tuple[str, ...]
    section_source_validations: tuple[GuidanceSectionSourceValidation, ...]


@dataclass(frozen=True)
class GuidanceInventoryEntry:
    wp_code: str
    path: str
    parse_status: Literal["ok", "invalid", "bundle"]
    source_digest: str
    exact_status: GuidanceExactStatus
    missing_sections: tuple[str, ...]
    reason: str
    exact_blockers: tuple[str, ...] = ()
    source_ref_status: GuidanceSourceRefState = "unvalidated"
    source_ref_facts_digest: str = ""
    source_ref_issues: tuple[str, ...] = ()


def stable_digest(value: Any) -> str:
    """对 JSON 可序列化事实生成稳定 SHA-256。"""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def infer_section_key(title: str) -> str | None:
    """仅按标题识别九段语义；不根据正文臆造缺失内容。"""
    normalized = re.sub(
        r"^[一二三四五六七八九十\d①②③④⑤⑥⑦⑧⑨⑩、.．)）\s]+",
        "",
        title or "",
    ).strip()
    for key, aliases in _SECTION_ALIASES:
        if any(alias in normalized for alias in aliases):
            return key
    return None


def normalize_source_refs(raw: Any) -> tuple[dict[str, Any], ...]:
    """保留 source_ref 的完整 JSON 结构；合法性只由权威 validator 裁决。"""
    if not isinstance(raw, list):
        return ()
    return tuple(dict(item) for item in raw if isinstance(item, Mapping))


def section_content(raw: dict[str, Any]) -> str:
    """兼容 canonical content 与历史 items/formula，但不改写语义。"""
    content = raw.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    lines: list[str] = []
    items = raw.get("items")
    if isinstance(items, list):
        for item in items:
            text = item.get("text") if isinstance(item, dict) else item
            if text is not None and str(text).strip():
                lines.append(str(text).strip())
    formula = raw.get("formula")
    if formula is not None and str(formula).strip():
        lines.append(str(formula).strip())
    return "\n".join(lines)


def _parse_schema_version(raw: Any) -> int:
    if raw is None:
        return 1
    if isinstance(raw, bool):
        raise ValueError("invalid_schema_version")
    try:
        version = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_schema_version") from exc
    if version < 1 or str(raw).strip() != str(version):
        raise ValueError("invalid_schema_version")
    return version


def _aggregate_source_ref_state(
    states: Sequence[GuidanceSourceRefState],
    *,
    structurally_missing: bool,
) -> GuidanceSourceRefState:
    if "stale" in states:
        return "stale"
    if "invalid" in states:
        return "invalid"
    if "cross_template" in states:
        return "cross_template"
    if "unvalidated" in states:
        return "unvalidated"
    if structurally_missing or "missing" in states:
        return "missing"
    return "valid"


def analyze_guidance_document(
    data: dict[str, Any],
    *,
    fallback_wp_code: str = "",
    source_ref_context: SourceRefContext | None = None,
) -> GuidanceDocumentAnalysis:
    """分析九段并按冻结模板 lineage 验证来源；任一 blocker 均不得计 exact。"""
    wp_code = str(data.get("wp_code") or fallback_wp_code).strip()
    schema_version = _parse_schema_version(data.get("schema_version"))
    raw_sections = data.get("sections")
    if not isinstance(raw_sections, list):
        raw_sections = []

    present: list[str] = []
    no_ref: list[str] = []
    duplicates: list[str] = []
    source_validations: list[GuidanceSectionSourceValidation] = []
    source_issues: list[str] = []
    for raw in raw_sections:
        if not isinstance(raw, dict) or not section_content(raw):
            continue
        explicit = str(raw.get("key") or "").strip()
        # v2 只接受显式 canonical key；标题别名推断仅用于 legacy 诊断。
        key = (
            explicit if explicit in CANONICAL_SECTION_KEYS else None
        ) if schema_version >= 2 else (
            explicit if explicit in CANONICAL_SECTION_KEYS else infer_section_key(
                str(raw.get("title") or raw.get("heading") or "")
            )
        )
        if key is None:
            continue
        if key in present:
            duplicates.append(key)
            continue
        present.append(key)
        refs = normalize_source_refs(raw.get("source_refs"))
        if not refs:
            no_ref.append(key)
        if source_ref_context is None:
            section_state: GuidanceSourceRefState = "unvalidated" if refs else "missing"
            section_digest = stable_digest(
                {
                    "section_key": key,
                    "source_refs": list(refs),
                    "validation": "context_missing" if refs else "empty",
                }
            )
            issue_codes = (
                ("source_ref_context_missing",) if refs else ("ref_list_empty",)
            )
        else:
            batch = validate_source_refs(raw.get("source_refs"), source_ref_context)
            statuses = tuple(item.status for item in batch.results)
            section_state = (
                "valid"
                if batch.all_valid
                else _aggregate_source_ref_state(
                    statuses, structurally_missing=not bool(refs)
                )
            )
            section_digest = batch.facts_digest
            issue_codes = tuple(
                dict.fromkeys(
                    issue.code
                    for result in batch.results
                    for issue in result.issues
                )
            )
        source_validations.append(
            GuidanceSectionSourceValidation(
                section_key=key,
                status=section_state,
                facts_digest=section_digest,
                issue_codes=issue_codes,
            )
        )
        source_issues.extend(f"{key}:{code}" for code in issue_codes)

    missing = tuple(
        key for key in CANONICAL_SECTION_KEYS if key not in present or key in no_ref
    )
    raw_unmapped = data.get("unmapped_sections")
    unmapped_valid = raw_unmapped is None or isinstance(raw_unmapped, list)
    unmapped_count = len(raw_unmapped) if isinstance(raw_unmapped, list) else 0
    blockers: list[str] = []
    if schema_version < 2:
        blockers.append("schema_version")
    if missing:
        blockers.append("canonical_sections")
    if duplicates:
        blockers.append("duplicate_sections")
    if not unmapped_valid:
        blockers.append("unmapped_sections_invalid")
    elif unmapped_count:
        blockers.append("unmapped_sections")

    source_ref_status = _aggregate_source_ref_state(
        tuple(item.status for item in source_validations),
        structurally_missing=bool(missing) or len(source_validations) != len(CANONICAL_SECTION_KEYS),
    )
    source_blocker = {
        "stale": "source_refs_stale",
        "invalid": "source_refs_invalid",
        "cross_template": "source_refs_cross_template",
        "unvalidated": "source_ref_context_missing",
        "missing": "source_refs_missing",
    }.get(source_ref_status)
    if source_blocker:
        blockers.append(source_blocker)

    if source_ref_status == "stale":
        status: GuidanceExactStatus = "stale"
    elif source_ref_status in {"invalid", "cross_template", "unvalidated"}:
        status = "invalid"
    elif blockers:
        status = "missing"
    else:
        status = "exact"
    source_ref_facts_digest = stable_digest(
        [asdict(item) for item in source_validations]
    )
    return GuidanceDocumentAnalysis(
        wp_code=wp_code,
        schema_version=schema_version,
        present_sections=tuple(present),
        missing_sections=missing,
        sections_without_source_ref=tuple(no_ref),
        duplicate_sections=tuple(duplicates),
        unmapped_section_count=unmapped_count,
        exact_blockers=tuple(dict.fromkeys(blockers)),
        status=status,
        source_ref_status=source_ref_status,
        source_ref_facts_digest=source_ref_facts_digest,
        source_ref_issues=tuple(dict.fromkeys(source_issues)),
        section_source_validations=tuple(source_validations),
    )


def load_guidance_document(
    wp_code: str,
    *,
    guidance_dir: Path = GUIDANCE_DIR,
) -> dict[str, Any] | None:
    path = guidance_dir / f"{wp_code}.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: guidance 根节点必须是对象")
    return data


def _invalid_static_entry(
    path: Path,
    digest: str,
    reason: str,
    *,
    wp_code: str | None = None,
) -> GuidanceInventoryEntry:
    return GuidanceInventoryEntry(
        wp_code=wp_code or path.stem,
        path=str(path),
        parse_status="invalid",
        source_digest=digest,
        exact_status="invalid",
        missing_sections=CANONICAL_SECTION_KEYS,
        reason=reason,
        exact_blockers=("invalid_document",),
        source_ref_status="invalid",
        source_ref_facts_digest=stable_digest({"path": str(path), "reason": reason}),
        source_ref_issues=(reason,),
    )


def _static_entry_from_path(
    path: Path,
    *,
    source_ref_context: SourceRefContext | None,
) -> GuidanceInventoryEntry:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return _invalid_static_entry(
            path,
            stable_digest({"path": str(path), "missing": True}),
            f"guidance_unreadable:{type(exc).__name__}",
        )
    digest = hashlib.sha256(raw).hexdigest()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _invalid_static_entry(path, digest, f"invalid_json:{exc.__class__.__name__}")
    if not isinstance(data, dict):
        return _invalid_static_entry(path, digest, "root_not_object")
    if "wp_codes" in data:
        return GuidanceInventoryEntry(
            wp_code=path.stem,
            path=str(path),
            parse_status="bundle",
            source_digest=digest,
            exact_status="invalid",
            missing_sections=CANONICAL_SECTION_KEYS,
            reason="second_schema_bundle",
            exact_blockers=("second_schema_bundle",),
            source_ref_status="invalid",
            source_ref_facts_digest=stable_digest({"path": str(path), "bundle": True}),
            source_ref_issues=("second_schema_bundle",),
        )
    try:
        analysis = analyze_guidance_document(
            data,
            fallback_wp_code=path.stem,
            source_ref_context=source_ref_context,
        )
    except (TypeError, ValueError) as exc:
        reason = (
            "invalid_schema_version"
            if str(exc) == "invalid_schema_version"
            else "invalid_document_contract"
        )
        return _invalid_static_entry(path, digest, reason)

    filename_matches = analysis.wp_code == path.stem
    exact_status: GuidanceExactStatus = analysis.status if filename_matches else "invalid"
    exact_blockers = (
        analysis.exact_blockers if filename_matches else ("filename_wp_code_mismatch",)
    )
    if not filename_matches:
        reason = "filename_wp_code_mismatch"
    elif exact_status == "exact":
        reason = "ok"
    elif exact_status == "stale":
        reason = "stale:" + ",".join(exact_blockers)
    elif exact_status == "invalid":
        reason = "invalid:" + ",".join(exact_blockers)
    else:
        reason = "incomplete:" + ",".join(exact_blockers)
    return GuidanceInventoryEntry(
        wp_code=analysis.wp_code or path.stem,
        path=str(path),
        parse_status="ok" if filename_matches else "invalid",
        source_digest=digest,
        exact_status=exact_status,
        missing_sections=analysis.missing_sections,
        reason=reason,
        exact_blockers=exact_blockers,
        source_ref_status=analysis.source_ref_status,
        source_ref_facts_digest=analysis.source_ref_facts_digest,
        source_ref_issues=analysis.source_ref_issues,
    )


def build_static_guidance_inventory(
    *,
    guidance_dir: Path = GUIDANCE_DIR,
    source_ref_contexts: Mapping[str, SourceRefContext] | None = None,
) -> tuple[GuidanceInventoryEntry, ...]:
    """实时扫描静态 guidance；只有给定 context 的来源可被判为 exact。"""
    contexts = source_ref_contexts or {}
    return tuple(
        _static_entry_from_path(path, source_ref_context=contexts.get(path.stem))
        for path in sorted(guidance_dir.glob("*.json"), key=lambda item: item.name.lower())
        if not path.stem.startswith("_")
    )


def revalidate_static_guidance_inventory(
    entries: Sequence[GuidanceInventoryEntry],
    *,
    source_ref_contexts: Mapping[str, SourceRefContext],
) -> tuple[GuidanceInventoryEntry, ...]:
    """按当前 context 重读 static 文件，禁止复用其他 active template 的 exact。"""
    return tuple(
        _static_entry_from_path(
            Path(entry.path),
            source_ref_context=source_ref_contexts.get(entry.wp_code),
        )
        for entry in entries
    )


def inventory_digest(entries: Iterable[GuidanceInventoryEntry]) -> str:
    return stable_digest([asdict(entry) for entry in entries])


def extract_sheet_code(sheet_name: str | None) -> str | None:
    """从真实 sheet 名提取 canonical code；无法确定时返回 None。"""
    if not sheet_name:
        return None
    matches = list(SHEET_CODE_RE.finditer(str(sheet_name).strip()))
    return matches[-1].group(1) if matches else None


def sheet_code_belongs_to_wp(parent_wp_code: str, sheet_code: str) -> bool:
    """仅供 legacy/orphan 投影使用；不得作为 render membership authority。"""
    parent = (parent_wp_code or "").strip()
    child = (sheet_code or "").strip()
    if not parent or not child:
        return False
    if child == parent:
        return True
    return child.startswith(parent + "-") or (
        child.startswith(parent)
        and len(child) == len(parent) + 1
        and child[-1:].isalpha()
    )


def __getattr__(name: str) -> Any:
    """运行时 inventory 已迁至 ``guidance_runtime_inventory``；保留既有导入路径。

    延迟解析而非顶层 import —— 该模块依赖本模块的静态分析符号，直接 import 会成环。
    """
    from app.services import guidance_runtime_inventory

    try:
        return getattr(guidance_runtime_inventory, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
