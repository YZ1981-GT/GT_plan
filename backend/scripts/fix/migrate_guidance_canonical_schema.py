#!/usr/bin/env python
"""将 legacy guidance 无损迁移到 canonical schema v2。

本脚本只整理结构，不生成业务文案、不伪造 source_ref，也不把 legacy 内容计为 exact：

* 可由稳定标题别名识别的 section 增加 canonical ``key``；
* 同一 key 的多个真实子主题合并并保留原标题顺序；
* 无法高置信分类的内容移入 ``unmapped_sections``，仍由 Extractor 展示；
* 所有原始正文逐字保留，``source_refs`` 缺失时明确写空数组；
* 写入确定性 lineage digest，支持幂等检查和后续人工复核。

用法：
    python backend/scripts/fix/migrate_guidance_canonical_schema.py
    python backend/scripts/fix/migrate_guidance_canonical_schema.py --check
    python backend/scripts/fix/migrate_guidance_canonical_schema.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.guidance_inventory import (  # noqa: E402
    CANONICAL_SECTION_KEYS,
    GUIDANCE_DIR,
    infer_section_key,
    normalize_source_refs,
    section_content,
    stable_digest,
)

CANONICAL_TITLES = {
    "purpose": "编制目的",
    "materials": "资料准备",
    "data_sources": "数据来源",
    "steps": "编制步骤",
    "formulas": "公式与逻辑",
    "judgments": "项目判断",
    "evidence": "证据与索引",
    "common_errors": "常见错误",
    "completion": "完成标准",
}


def _legacy_payload(document: dict[str, Any]) -> dict[str, Any]:
    """只含原始业务正文的稳定 lineage；不含格式化或迁移元数据。"""
    return {
        "wp_code": str(document.get("wp_code") or "").strip(),
        "title": str(document.get("title") or "").strip(),
        "sections": [
            {
                "title": str(raw.get("title") or raw.get("heading") or "").strip(),
                "content": section_content(raw),
            }
            for raw in document.get("sections", [])
            if isinstance(raw, dict) and section_content(raw)
        ],
    }


def _canonical_body_payload(document: dict[str, Any]) -> dict[str, Any]:
    """生成 v2 业务正文指纹投影；排除可独立演进的来源引用和迁移元数据。"""
    sections: list[dict[str, Any]] = []
    raw_sections = document.get("sections")
    if isinstance(raw_sections, list):
        for raw in raw_sections:
            if not isinstance(raw, dict):
                sections.append({"invalid": deepcopy(raw)})
                continue
            item: dict[str, Any] = {
                "key": str(raw.get("key") or "").strip(),
                "title": str(raw.get("title") or raw.get("heading") or "").strip(),
                "content": section_content(raw),
            }
            if "legacy_subsections" in raw:
                legacy_subsections = raw.get("legacy_subsections")
                item["legacy_subsections"] = [
                    {
                        "title": str(sub.get("title") or sub.get("heading") or "").strip(),
                        "content": section_content(sub),
                    }
                    if isinstance(sub, dict)
                    else {"invalid": deepcopy(sub)}
                    for sub in legacy_subsections
                ] if isinstance(legacy_subsections, list) else deepcopy(legacy_subsections)
            if "source_indices" in raw:
                item["source_indices"] = deepcopy(raw.get("source_indices"))
            sections.append(item)

    unmapped: list[dict[str, Any]] = []
    raw_unmapped = document.get("unmapped_sections")
    if isinstance(raw_unmapped, list):
        for raw in raw_unmapped:
            if not isinstance(raw, dict):
                unmapped.append({"invalid": deepcopy(raw)})
                continue
            unmapped.append(
                {
                    "title": str(raw.get("title") or raw.get("heading") or "").strip(),
                    "content": section_content(raw),
                    "source_index": deepcopy(raw.get("source_index")),
                }
            )

    return {
        "wp_code": str(document.get("wp_code") or "").strip(),
        "title": str(document.get("title") or "").strip(),
        "sections": sections,
        "unmapped_sections": unmapped,
    }


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _normalize_unmapped(raw: dict[str, Any], *, source_index: int) -> dict[str, Any]:
    title = str(raw.get("title") or raw.get("heading") or f"原始段落 {source_index + 1}").strip()
    return {
        "title": title,
        "content": section_content(raw),
        "source_refs": [dict(ref) for ref in normalize_source_refs(raw.get("source_refs"))],
        "source_index": source_index,
        "classification": "unmapped",
    }


def _merge_group(key: str, items: list[tuple[int, dict[str, Any]]]) -> dict[str, Any]:
    titles = [
        str(raw.get("title") or raw.get("heading") or CANONICAL_TITLES[key]).strip()
        for _, raw in items
    ]
    refs = [
        dict(ref)
        for _, raw in items
        for ref in normalize_source_refs(raw.get("source_refs"))
    ]
    if len(items) == 1:
        content = section_content(items[0][1])
        title = titles[0]
    else:
        # 多个真实子主题不能 first-wins 丢弃；标题作为正文内稳定子段保留。
        content = "\n\n".join(
            f"【{sub_title}】\n{section_content(raw)}"
            for sub_title, (_, raw) in zip(titles, items, strict=True)
        )
        title = CANONICAL_TITLES[key]
    section: dict[str, Any] = {
        "key": key,
        "title": title,
        "content": content,
        "source_refs": refs,
    }
    if len(items) > 1:
        section["legacy_titles"] = titles
        section["source_indices"] = [index for index, _ in items]
        section["legacy_subsections"] = [
            {
                "title": sub_title,
                "content": section_content(raw),
                "source_refs": [
                    dict(ref) for ref in normalize_source_refs(raw.get("source_refs"))
                ],
            }
            for sub_title, (_, raw) in zip(titles, items, strict=True)
        ]
    return section


def migrate_document(document: dict[str, Any], *, filename_code: str) -> dict[str, Any]:
    """返回无损 canonical 投影；v2 文档只允许补齐可验证的指纹元数据。"""
    if not isinstance(document, dict):
        raise ValueError("guidance 根节点必须是对象")
    declared = str(document.get("wp_code") or "").strip()
    if declared != filename_code:
        raise ValueError(f"filename/wp_code mismatch: {filename_code!r} != {declared!r}")
    raw_version = document.get("schema_version")
    if isinstance(raw_version, int) and not isinstance(raw_version, bool) and raw_version >= 2:
        upgraded = deepcopy(document)
        raw_migration = upgraded.get("migration")
        if raw_migration is not None and not isinstance(raw_migration, dict):
            raise ValueError("migration 必须是对象")
        migration = deepcopy(raw_migration) if isinstance(raw_migration, dict) else {}
        raw_metadata_version = migration.get("version")
        metadata_version = (
            raw_metadata_version
            if isinstance(raw_metadata_version, int) and not isinstance(raw_metadata_version, bool)
            else 0
        )
        current_digest = stable_digest(_canonical_body_payload(upgraded))
        stored_digest = migration.get("canonical_body_digest")
        # 已有指纹一律不自动重封；正文或摘要被改动时必须由稳态校验打红。
        if stored_digest is not None and stored_digest != current_digest:
            return upgraded
        if metadata_version < 2 or stored_digest is None:
            migration.setdefault("kind", "canonical_schema_v2_fingerprint")
            migration["version"] = 2
            migration["canonical_section_count"] = len(upgraded.get("sections") or [])
            migration["unmapped_section_count"] = len(upgraded.get("unmapped_sections") or [])
            migration["canonical_body_digest"] = current_digest
            upgraded["migration"] = migration
        return upgraded

    raw_sections = document.get("sections")
    if not isinstance(raw_sections, list):
        raise ValueError("sections 必须是数组")
    groups: dict[str, list[tuple[int, dict[str, Any]]]] = {
        key: [] for key in CANONICAL_SECTION_KEYS
    }
    unmapped: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_sections):
        if not isinstance(raw, dict):
            raise ValueError(f"sections[{index}] 必须是对象")
        if not section_content(raw):
            raise ValueError(f"sections[{index}] 正文为空")
        explicit = str(raw.get("key") or "").strip()
        key = explicit if explicit in CANONICAL_SECTION_KEYS else infer_section_key(
            str(raw.get("title") or raw.get("heading") or "")
        )
        if key is None:
            unmapped.append(_normalize_unmapped(raw, source_index=index))
        else:
            groups[key].append((index, raw))

    canonical_sections = [
        _merge_group(key, groups[key])
        for key in CANONICAL_SECTION_KEYS
        if groups[key]
    ]
    lineage = _legacy_payload(document)
    migrated: OrderedDict[str, Any] = OrderedDict()
    migrated["schema_version"] = 2
    migrated["wp_code"] = declared
    migrated["title"] = str(document.get("title") or declared).strip()
    migrated["sections"] = canonical_sections
    if unmapped:
        migrated["unmapped_sections"] = unmapped

    for key, value in document.items():
        if key not in {"schema_version", "wp_code", "title", "sections", "unmapped_sections", "migration"}:
            migrated[key] = deepcopy(value)
    migrated["migration"] = {
        "kind": "legacy_structure_preserved",
        "version": 2,
        "legacy_content_digest": stable_digest(lineage),
        "legacy_section_count": len(lineage["sections"]),
        "canonical_section_count": len(canonical_sections),
        "unmapped_section_count": len(unmapped),
        "canonical_body_digest": stable_digest(_canonical_body_payload(migrated)),
    }
    return dict(migrated)


def _all_business_files() -> list[Path]:
    return [
        path
        for path in sorted(GUIDANCE_DIR.glob("*.json"), key=lambda item: item.name.lower())
        if not path.stem.startswith("_")
    ]


def _lineage_leaf_contents(document: dict[str, Any]) -> list[str]:
    contents: list[str] = []
    raw_sections = document.get("sections")
    if isinstance(raw_sections, list):
        for raw in raw_sections:
            if not isinstance(raw, dict):
                continue
            legacy_subsections = raw.get("legacy_subsections")
            if isinstance(legacy_subsections, list) and legacy_subsections:
                contents.extend(
                    section_content(item)
                    for item in legacy_subsections
                    if isinstance(item, dict) and section_content(item)
                )
            elif section_content(raw):
                contents.append(section_content(raw))
    raw_unmapped = document.get("unmapped_sections")
    if isinstance(raw_unmapped, list):
        contents.extend(
            section_content(raw)
            for raw in raw_unmapped
            if isinstance(raw, dict) and section_content(raw)
        )
    return contents


def _validate_lineage_shape(document: dict[str, Any]) -> list[str]:
    """校验可从 v2 自身验证的 lineage 形态，防止把损坏数据封成新基线。"""
    errors: list[str] = []
    migration = document.get("migration")
    if not isinstance(migration, dict):
        return ["migration 元数据缺失或非对象"]

    sections = document.get("sections")
    canonical_count = len(sections) if isinstance(sections, list) else 0
    unmapped_sections = document.get("unmapped_sections")
    unmapped_count = len(unmapped_sections) if isinstance(unmapped_sections, list) else 0
    if migration.get("canonical_section_count") != canonical_count:
        errors.append("canonical_section_count 与正文不一致")
    if migration.get("unmapped_section_count") != unmapped_count:
        errors.append("unmapped_section_count 与正文不一致")

    if "legacy_section_count" in migration:
        if migration.get("legacy_section_count") != len(_lineage_leaf_contents(document)):
            errors.append("legacy_section_count 与 lineage 叶子不一致")
        if not _is_sha256(migration.get("legacy_content_digest")):
            errors.append("legacy_content_digest 缺失或非法")

    if isinstance(sections, list):
        for index, raw in enumerate(sections):
            if not isinstance(raw, dict) or "legacy_subsections" not in raw:
                continue
            legacy_subsections = raw.get("legacy_subsections")
            if not isinstance(legacy_subsections, list) or len(legacy_subsections) < 2:
                errors.append(f"sections[{index}].legacy_subsections 无效")
                continue
            if any(not isinstance(item, dict) or not section_content(item) for item in legacy_subsections):
                errors.append(f"sections[{index}].legacy_subsections 含无效正文")
                continue
            titles = [
                str(item.get("title") or item.get("heading") or "").strip()
                for item in legacy_subsections
            ]
            expected_content = "\n\n".join(
                f"【{title}】\n{section_content(item)}"
                for title, item in zip(titles, legacy_subsections, strict=True)
            )
            if section_content(raw) != expected_content:
                errors.append(f"sections[{index}] 合并正文与 lineage 不一致")
            if raw.get("legacy_titles") != titles:
                errors.append(f"sections[{index}].legacy_titles 与 lineage 不一致")
            source_indices = raw.get("source_indices")
            if (
                not isinstance(source_indices, list)
                or len(source_indices) != len(legacy_subsections)
                or any(not isinstance(item, int) or isinstance(item, bool) for item in source_indices)
                or len(set(source_indices)) != len(source_indices)
            ):
                errors.append(f"sections[{index}].source_indices 无效")
    return errors


def validate_lossless(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """分别校验首次 legacy 转换与 v2 稳态正文指纹，禁止正文变异假绿。"""
    errors: list[str] = []
    raw_before_version = before.get("schema_version")
    before_is_v2 = (
        isinstance(raw_before_version, int)
        and not isinstance(raw_before_version, bool)
        and raw_before_version >= 2
    )
    if before_is_v2:
        if _canonical_body_payload(before) != _canonical_body_payload(after):
            errors.append("v2 业务正文被迁移器改写")
    else:
        expected = sorted(item["content"] for item in _legacy_payload(before)["sections"])
        actual = sorted(_lineage_leaf_contents(after))
        if actual != expected:
            errors.append("legacy 正文多重集不一致")
        migration = after.get("migration")
        if not isinstance(migration, dict) or migration.get("legacy_content_digest") != stable_digest(
            _legacy_payload(before)
        ):
            errors.append("legacy_content_digest 不一致")

    errors.extend(_validate_lineage_shape(after))
    migration = after.get("migration")
    if isinstance(migration, dict):
        metadata_version = migration.get("version")
        if (
            not isinstance(metadata_version, int)
            or isinstance(metadata_version, bool)
            or metadata_version < 2
        ):
            errors.append("migration.version < 2")
        stored_digest = migration.get("canonical_body_digest")
        if not _is_sha256(stored_digest):
            errors.append("canonical_body_digest 缺失或非法")
        elif stored_digest != stable_digest(_canonical_body_payload(after)):
            errors.append("canonical_body_digest 不一致")
    return errors


def validate_canonical_structure(document: dict[str, Any], *, filename_code: str) -> list[str]:
    errors: list[str] = []
    if document.get("schema_version") != 2:
        errors.append("schema_version != 2")
    if str(document.get("wp_code") or "") != filename_code:
        errors.append("filename/wp_code 不一致")
    if not str(document.get("title") or "").strip():
        errors.append("title 为空")
    sections = document.get("sections")
    if not isinstance(sections, list):
        return [*errors, "sections 非数组"]
    seen: set[str] = set()
    for index, raw in enumerate(sections):
        if not isinstance(raw, dict):
            errors.append(f"sections[{index}] 非对象")
            continue
        key = str(raw.get("key") or "")
        if key not in CANONICAL_SECTION_KEYS:
            errors.append(f"sections[{index}].key 非 canonical")
        elif key in seen:
            errors.append(f"sections[{index}].key 重复: {key}")
        seen.add(key)
        if not str(raw.get("title") or "").strip():
            errors.append(f"sections[{index}].title 为空")
        if not section_content(raw):
            errors.append(f"sections[{index}].content 为空")
        if not isinstance(raw.get("source_refs"), list):
            errors.append(f"sections[{index}].source_refs 非数组")
    questions = document.get("recommended_questions", [])
    if not isinstance(questions, list) or any(
        not isinstance(item, str) or not item.strip() for item in questions
    ):
        errors.append("recommended_questions 必须是非空字符串数组")
    for index, raw in enumerate(document.get("unmapped_sections", [])):
        if not isinstance(raw, dict) or not section_content(raw):
            errors.append(f"unmapped_sections[{index}] 无效")
    return errors


def run(*, apply: bool) -> tuple[int, int, list[str]]:
    changed = 0
    unmapped = 0
    errors: list[str] = []
    for path in _all_business_files():
        try:
            before = json.loads(path.read_text(encoding="utf-8"))
            after = migrate_document(before, filename_code=path.stem)
            file_errors = validate_lossless(before, after)
            file_errors.extend(validate_canonical_structure(after, filename_code=path.stem))
            if file_errors:
                errors.extend(f"{path.name}: {error}" for error in file_errors)
                continue
            unmapped += len(after.get("unmapped_sections", []))
            serialized = json.dumps(after, ensure_ascii=False, indent=2) + "\n"
            current = path.read_text(encoding="utf-8")
            if current != serialized:
                changed += 1
                if apply:
                    path.write_text(serialized, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 — 汇总全部文件，不能首错掩盖后续欠账
            errors.append(f"{path.name}: {exc}")
    return changed, unmapped, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="写入 canonical schema v2")
    group.add_argument("--check", action="store_true", help="CI：仍需迁移或结构非法时返回 1")
    args = parser.parse_args()

    changed, unmapped, errors = run(apply=args.apply)
    mode = "apply" if args.apply else ("check" if args.check else "dry-run")
    print(f"mode={mode} files={len(_all_business_files())} changed={changed} unmapped={unmapped} errors={len(errors)}")
    for error in errors[:50]:
        print(f"ERROR {error}")
    if len(errors) > 50:
        print(f"ERROR ... 其余 {len(errors) - 50} 项省略")
    if errors:
        return 2
    if args.check and changed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
