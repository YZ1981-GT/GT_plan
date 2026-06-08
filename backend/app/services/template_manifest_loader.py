"""审计报告模板 manifest 加载与路径解析（唯一索引入口）."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.note_section_catalog import build_variant_key, normalize_report_scope

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DEFAULT_BASE_DIR = DATA_DIR / "audit_report_templates"
MANIFEST_FILENAME = "template_manifest.json"
ALLOWED_SUFFIXES = frozenset({".docx", ".xlsx", ".json"})


def resolve_template_base_dir() -> Path:
    """解析模板根目录（settings.TEMPLATE_MANIFEST_DIR 或默认 data 路径）."""
    from app.core.config import settings

    raw = (settings.TEMPLATE_MANIFEST_DIR or "").strip()
    if not raw:
        return DEFAULT_BASE_DIR
    p = Path(raw)
    if p.is_absolute():
        return p.resolve()
    # 相对路径：优先相对 backend 根（与 cwd 常见启动目录一致）
    backend_root = Path(__file__).resolve().parent.parent.parent
    candidate = (backend_root / p).resolve()
    if candidate.exists():
        return candidate
    return (Path.cwd() / p).resolve()


@dataclass(frozen=True)
class ManifestEntry:
    rel_path: Path
    abs_path: Path
    exists: bool


class TemplateManifestLoader:
    """加载 ``template_manifest.json`` 并解析三类模板路径."""

    def __init__(self, base_dir: Path | None = None):
        self._base_dir = (base_dir or resolve_template_base_dir()).resolve()
        self._manifest: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        manifest_path = self._base_dir / MANIFEST_FILENAME
        if not manifest_path.exists():
            logger.warning("Template manifest not found: %s", manifest_path)
            self._manifest = {}
            return
        with manifest_path.open(encoding="utf-8") as f:
            self._manifest = json.load(f)

    def validate(self) -> list[str]:
        """返回缺失文件或非法扩展名的 warning 列表."""
        warnings: list[str] = []
        if not self._manifest:
            warnings.append(f"manifest missing or empty under {self._base_dir}")
            return warnings

        for rel in self._iter_manifest_paths():
            suffix = rel.suffix.lower()
            if suffix == ".doc":
                warnings.append(f"manifest references legacy .doc: {rel}")
            elif suffix not in ALLOWED_SUFFIXES:
                warnings.append(f"disallowed extension {suffix}: {rel}")
            entry = self._entry_from_rel(rel)
            if not entry.exists:
                warnings.append(f"template file missing: {entry.abs_path}")
        return warnings

    def version(self) -> str:
        return str(self._manifest.get("version", ""))

    def get_sheet_aliases(self, variant_key: str) -> dict[str, Any]:
        """返回报表 xlsx 的 ``report_type`` → 实际 sheet 名映射."""
        block = self._manifest.get("sheet_aliases", {})
        entry = block.get(variant_key, {})
        return dict(entry) if isinstance(entry, dict) else {}

    def resolve_report_body(
        self,
        opinion_type: str,
        company_subtype: str,
        variant: str = "simple",
    ) -> ManifestEntry:
        body = self._manifest.get("report_body", {})
        opinion = body.get(opinion_type)
        if opinion is None:
            raise KeyError(f"unknown opinion_type: {opinion_type}")

        subtype_entry = opinion.get(company_subtype)
        if subtype_entry is None:
            raise KeyError(
                f"unknown company_subtype {company_subtype!r} for {opinion_type}"
            )

        if isinstance(subtype_entry, str):
            rel_str = subtype_entry
        else:
            rel_str = subtype_entry.get(variant)
            if rel_str is None:
                raise KeyError(
                    f"unknown variant {variant!r} for {opinion_type}/{company_subtype}"
                )
        return self._entry_from_rel(Path(rel_str))

    def resolve_financial_statements(
        self,
        template_type: str,
        report_scope: str | None,
    ) -> ManifestEntry:
        key = build_variant_key(template_type, report_scope)
        return self._resolve_variant_section("financial_statements", key)

    def resolve_disclosure_notes(
        self,
        template_type: str,
        report_scope: str | None,
    ) -> ManifestEntry:
        """附注路径 **必须** 使用 ``build_variant_key``，不得仅用 template_type."""
        key = build_variant_key(template_type, report_scope)
        return self._resolve_variant_section("disclosure_notes", key)

    def _resolve_variant_section(self, section: str, variant_key: str) -> ManifestEntry:
        block = self._manifest.get(section, {})
        rel_str = block.get(variant_key)
        if not rel_str:
            raise KeyError(f"no manifest entry for {section}/{variant_key}")
        return self._entry_from_rel(Path(rel_str))

    def _entry_from_rel(self, rel_path: Path) -> ManifestEntry:
        rel = Path(rel_path)
        abs_path = (self._base_dir / rel).resolve()
        return ManifestEntry(rel_path=rel, abs_path=abs_path, exists=abs_path.is_file())

    def _iter_manifest_paths(self) -> list[Path]:
        paths: list[Path] = []

        def walk(node: Any) -> None:
            if isinstance(node, str):
                paths.append(Path(node))
            elif isinstance(node, dict):
                for v in node.values():
                    walk(v)

        for section in ("report_body", "financial_statements", "disclosure_notes"):
            walk(self._manifest.get(section, {}))
        return paths


@lru_cache(maxsize=1)
def get_template_manifest_loader() -> TemplateManifestLoader:
    return TemplateManifestLoader()
