"""编制说明 SourceRef 的模板 lineage 冻结。

从 ``backend/wp_templates/_index.json`` 解析一次 render context 允许引用的
canonical→active 模板集合，并投影成 per-wp_code 的验证上下文。任何歧义、越界或
缺失都进入 ``blockers`` 并 fail-closed —— 本模块只冻结事实，不裁决 guidance 是否
exact，也不放宽 ``guidance_source_refs`` 的定位判据。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.services.guidance_source_refs import (
    SourceRefContext,
    TemplateAuthority,
    _stable_digest,
    file_sha256,
)
from app.services.workpaper_sync.canonical_paths import (
    REPO_ROOT,
    TEMPLATE_ROOT,
    PathBoundaryError,
    assert_within_root,
    resolve_within_root,
)

__all__ = [
    "TemplateAuthoritySnapshot",
    "build_template_authority_snapshot",
    "build_source_ref_contexts",
]


def _authority_payload(item: TemplateAuthority) -> dict[str, Any]:
    return {
        "canonical_path": item.canonical_path,
        "active_path": str(item.active_path) if item.active_path is not None else None,
        "wp_codes": list(item.wp_codes),
        "origin": item.origin,
        "version": item.version,
        "expected_active_digest": item.expected_active_digest,
    }


@dataclass(frozen=True)
class TemplateAuthoritySnapshot:
    """一次 render context 冻结的 canonical→active 模板 lineage。"""

    parent_wp_code: str
    authorities: tuple[TemplateAuthority, ...]
    blockers: tuple[str, ...]
    facts_digest: str
    repo_root: Path = REPO_ROOT
    template_root: Path = TEMPLATE_ROOT

    def version_facts(self) -> dict[str, Any]:
        return {
            "parent_wp_code": self.parent_wp_code,
            "authorities": [_authority_payload(item) for item in self.authorities],
            "blockers": list(self.blockers),
            "facts_digest": self.facts_digest,
        }


def _snapshot(
    *,
    parent_wp_code: str,
    authorities: Sequence[TemplateAuthority],
    blockers: Sequence[str],
    repo_root: Path,
    template_root: Path,
) -> TemplateAuthoritySnapshot:
    ordered_authorities = tuple(
        sorted(
            authorities,
            key=lambda item: (
                item.canonical_path,
                str(item.active_path or ""),
                item.origin,
                item.version or "",
            ),
        )
    )
    normalized_blockers = tuple(dict.fromkeys(blockers))
    payload = {
        "parent_wp_code": parent_wp_code,
        "authorities": [_authority_payload(item) for item in ordered_authorities],
        "blockers": list(normalized_blockers),
    }
    return TemplateAuthoritySnapshot(
        parent_wp_code=parent_wp_code,
        authorities=ordered_authorities,
        blockers=normalized_blockers,
        facts_digest=_stable_digest(payload),
        repo_root=repo_root,
        template_root=template_root,
    )


def _canonical_paths_from_index(
    *,
    index_path: Path,
    template_root: Path,
    target_codes: set[str],
    parent: str,
    blockers: list[str],
) -> list[Path] | None:
    """返回索引中命中的 canonical 模板；索引本身不可用时返回 ``None``。"""
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        files = data.get("files") if isinstance(data, dict) else None
        if not isinstance(files, list):
            raise ValueError("files_not_array")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None

    canonical_paths: list[Path] = []
    for item in files:
        if not isinstance(item, Mapping):
            continue
        code = str(item.get("wp_code") or "").strip()
        fmt = str(item.get("format") or "").lower().strip()
        if code not in target_codes and code != parent:
            continue
        if fmt not in {"xlsx", "xlsm", "docx"}:
            continue
        relative = str(item.get("relative_path") or "").strip()
        if not relative:
            blockers.append("template_index_relative_path_missing")
            continue
        try:
            candidate = resolve_within_root(template_root, relative, boundary="template_root")
        except PathBoundaryError:
            blockers.append("template_index_path_outside_root")
            continue
        if candidate not in canonical_paths:
            canonical_paths.append(candidate)
    return canonical_paths


def build_template_authority_snapshot(
    *,
    parent_wp_code: str,
    render_sheets: Sequence[Mapping[str, Any]],
    active_template_path: Path | str | None,
    template_version: str | None = None,
    template_origin: str | None = None,
    index_path: Path | None = None,
    repo_root: Path = REPO_ROOT,
    template_root: Path = TEMPLATE_ROOT,
) -> TemplateAuthoritySnapshot:
    """从模板索引冻结当前 context 的唯一 lineage；任何歧义均 fail-closed。"""
    parent = str(parent_wp_code or "").strip()
    if not parent:
        raise ValueError("parent_wp_code 为空")
    repo_root = Path(repo_root).resolve()
    template_root = Path(template_root).resolve()
    index_path = Path(index_path or (template_root / "_index.json"))
    target_codes = {parent}
    for raw in render_sheets:
        code = str(raw.get("sheet_code") or "").strip()
        if code:
            target_codes.add(code)

    blockers: list[str] = []
    canonical_paths = _canonical_paths_from_index(
        index_path=index_path,
        template_root=template_root,
        target_codes=target_codes,
        parent=parent,
        blockers=blockers,
    )
    if canonical_paths is None:
        return _snapshot(
            parent_wp_code=parent,
            authorities=(),
            blockers=("template_index_invalid",),
            repo_root=repo_root,
            template_root=template_root,
        )

    if not canonical_paths:
        blockers.append("canonical_template_not_found")
        return _snapshot(
            parent_wp_code=parent,
            authorities=(),
            blockers=blockers,
            repo_root=repo_root,
            template_root=template_root,
        )

    resolved_active: Path | None = None
    if active_template_path is not None and str(active_template_path).strip():
        candidate = Path(active_template_path)
        try:
            resolved_active = (
                assert_within_root(repo_root, candidate, boundary="repo")
                if candidate.is_absolute()
                else resolve_within_root(repo_root, str(candidate), boundary="repo")
            )
        except PathBoundaryError:
            blockers.append("active_template_outside_repo")
            return _snapshot(
                parent_wp_code=parent,
                authorities=(),
                blockers=blockers,
                repo_root=repo_root,
                template_root=template_root,
            )
        if not resolved_active.is_file():
            blockers.append("active_template_missing")
            return _snapshot(
                parent_wp_code=parent,
                authorities=(),
                blockers=blockers,
                repo_root=repo_root,
                template_root=template_root,
            )

    pairs: list[tuple[Path, Path]] = []
    if resolved_active is None:
        pairs = [(path, path) for path in canonical_paths]
    else:
        exact_matches = [path for path in canonical_paths if path.resolve() == resolved_active]
        if len(exact_matches) == 1:
            pairs = [(exact_matches[0], resolved_active)]
        elif len(canonical_paths) == 1:
            pairs = [(canonical_paths[0], resolved_active)]
        else:
            blockers.append("active_template_lineage_ambiguous")

    authorities: list[TemplateAuthority] = []
    for canonical_path, active_path in pairs:
        if not canonical_path.is_file():
            blockers.append("canonical_template_missing")
            continue
        try:
            canonical_relative = canonical_path.resolve().relative_to(repo_root).as_posix()
            active_digest = file_sha256(active_path)
        except (OSError, ValueError):
            blockers.append("template_authority_unreadable")
            continue
        authorities.append(
            TemplateAuthority(
                canonical_path=canonical_relative,
                active_path=active_path,
                wp_codes=tuple(sorted(target_codes)),
                origin=template_origin
                or ("canonical" if active_path == canonical_path else "runtime_resolved"),
                version=template_version,
                expected_active_digest=active_digest,
            )
        )
    if not authorities:
        blockers.append("template_authority_missing")
    return _snapshot(
        parent_wp_code=parent,
        authorities=authorities,
        blockers=blockers,
        repo_root=repo_root,
        template_root=template_root,
    )


def build_source_ref_contexts(
    snapshot: TemplateAuthoritySnapshot,
    render_sheets: Sequence[Mapping[str, Any]],
    *,
    additional_wp_codes: Sequence[str] = (),
) -> dict[str, SourceRefContext]:
    """把一份冻结 snapshot 投影为 per-guidance-code validator context。"""
    sheet_names: dict[str, str | None] = {snapshot.parent_wp_code: None}
    for raw in render_sheets:
        code = str(raw.get("sheet_code") or "").strip()
        if not code:
            continue
        name = str(raw.get("sheet_name") or "").strip() or None
        if code in sheet_names and sheet_names[code] != name:
            sheet_names[code] = None
        else:
            sheet_names[code] = name
    for raw_code in additional_wp_codes:
        code = str(raw_code or "").strip()
        if code:
            sheet_names.setdefault(code, None)
    return {
        code: SourceRefContext(
            target_wp_code=code,
            template_authorities=snapshot.authorities,
            target_sheet_code=code if code != snapshot.parent_wp_code else None,
            target_sheet_name=sheet_name,
            repo_root=snapshot.repo_root,
            template_root=snapshot.template_root,
        )
        for code, sheet_name in sorted(sheet_names.items())
    }
