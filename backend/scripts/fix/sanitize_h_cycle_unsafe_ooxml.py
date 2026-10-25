# -*- coding: utf-8 -*-
"""净化 H 循环 6 本权威模板的危险 OOXML 包，不放宽安全门。

* H2/H3/H4/H5/H7：Equation.3 OLE → 保留 WMF/EMF 静态预览，删除可执行 OLE 包；
* H8：115 个断开的 enhanced-workbook 外链 → 本册同 sheet 引用，删除 externalLinks 包。

用法::

    python backend/scripts/fix/sanitize_h_cycle_unsafe_ooxml.py --check
    python backend/scripts/fix/sanitize_h_cycle_unsafe_ooxml.py --apply
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import posixpath
import re
import tempfile
import zipfile
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from xml.etree import ElementTree as ET

_REPO: Final[Path] = Path(__file__).resolve().parents[3]
_BACKEND: Final[Path] = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
_H_ROOT: Final[Path] = _BACKEND / "wp_templates" / "H"
_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
# ElementTree 重写 .rels 时必须保留默认命名空间。若变成 `ns0:Relationships`，
# instrumentation 的字节级锚点 `</Relationships>` 会找不到（H8 实测即此）。
ET.register_namespace("", _PKG_REL_NS)


class HTemplateSanitizationError(RuntimeError):
    """模板危险载荷形态与已复核事实不一致；拒绝自动净化。"""


@dataclass(frozen=True)
class OleTemplate:
    file_name: str
    object_count: int
    host_sheet: str


_OLE_TEMPLATES: Final[tuple[OleTemplate, ...]] = (
    OleTemplate("H2 在建工程.xlsx", 2, "可收回金额测试表H2-16"),
    OleTemplate("H3 投资性房地产.xlsx", 2, "可收回金额测试表H3-11"),
    OleTemplate("H4 工程物资.xlsx", 2, "可收回金额测试表H4-8"),
    OleTemplate("H5 油气资产.xlsx", 2, "可收回金额测试表H5-15"),
    OleTemplate("H7 生产性生物资产.xlsx", 3, "可收回金额测试表H7-16"),
)
_H8 = "H8 使用权资产.xlsx"
_EXTERNAL_FORMULA_RE = re.compile(r"<f(?P<attrs>[^>]*)>(?P<body>[^<]*\[\d+\][^<]*)</f>")
_EXTERNAL_REF_RE = re.compile(r"(?:'\[\d+\]([^']+)'|\[\d+\]([^!]+))!")
_OLE_REL_SUFFIX = "/oleObject"
_IMAGE_REL_SUFFIX = "/image"


def _rels_path(part: str) -> str:
    return posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")


def _sheet_parts(entries: dict[str, bytes]) -> dict[str, str]:
    workbook = ET.fromstring(entries["xl/workbook.xml"])
    rels = ET.fromstring(entries["xl/_rels/workbook.xml.rels"])
    target_by_id = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
    result: dict[str, str] = {}
    for sheet in workbook.findall(f".//{{{_MAIN_NS}}}sheet"):
        target = target_by_id[sheet.attrib[f"{{{_REL_NS}}}id"]].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        result[sheet.attrib["name"]] = target.replace("xl//", "xl/")
    return result


def _remove_relationships(xml: bytes, *, suffix: str) -> tuple[bytes, list[dict[str, str]]]:
    root = ET.fromstring(xml)
    removed: list[dict[str, str]] = []
    for rel in list(root):
        if str(rel.attrib.get("Type") or "").endswith(suffix):
            removed.append(dict(rel.attrib))
            root.remove(rel)
    if not removed:
        return xml, []
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), removed


def _rewrite_zip(source: bytes, changes: dict[str, bytes], removed: set[str]) -> bytes:
    """保持每个未删除 ZipInfo 的时间/权限/压缩法；内容不变时返回原字节。"""
    if not changes and not removed:
        return source
    src = io.BytesIO(source)
    dst = io.BytesIO()
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            if info.filename in removed:
                continue
            data = changes.get(info.filename, zin.read(info.filename))
            zout.writestr(info, data)
    return dst.getvalue()


def _repair_ns0_relationships(entries: dict[str, bytes]) -> dict[str, bytes]:
    """修复旧版 sanitizer 产出的 ns0 前缀，保住 instrumentation 的字节锚点。"""
    changes: dict[str, bytes] = {}
    open_ns0 = f'<ns0:Relationships xmlns:ns0="{_PKG_REL_NS}">'
    open_default = f'<Relationships xmlns="{_PKG_REL_NS}">'
    for name, data in entries.items():
        if not name.endswith(".rels"):
            continue
        text = data.decode("utf-8", errors="strict")
        if open_ns0 not in text:
            continue
        fixed = (
            text.replace(open_ns0, open_default)
            .replace("<ns0:Relationship ", "<Relationship ")
            .replace("</ns0:Relationships>", "</Relationships>")
        )
        changes[name] = fixed.encode("utf-8")
    return changes


def _preview_inventory(entries: dict[str, bytes]) -> dict[str, str]:
    """静态预览 image part 的 sha256；净化前后必须逐项相等。"""
    return {
        name: hashlib.sha256(data).hexdigest()
        for name, data in entries.items()
        if name.startswith("xl/media/")
    }


def sanitize_ole_equations(source: bytes, expected: OleTemplate) -> tuple[bytes, dict[str, Any]]:
    """删 Equation.3 可执行对象，保留 VML Pict + WMF/EMF 预览。"""
    with zipfile.ZipFile(io.BytesIO(source)) as zf:
        entries = {i.filename: zf.read(i.filename) for i in zf.infolist()}
    embedding_parts = {n for n in entries if n.startswith("xl/embeddings/")}
    embeddings = sorted(n for n in embedding_parts if not n.endswith("/"))
    if not embeddings:
        repairs = _repair_ns0_relationships(entries)
        repaired = _rewrite_zip(source, repairs, set())
        return repaired, {
            "state": "normalized_relationship_namespace" if repairs else "already_clean",
            "removed_ole_objects": 0,
            "normalized_relationship_parts": len(repairs),
        }
    if len(embeddings) != expected.object_count:
        raise HTemplateSanitizationError(
            f"{expected.file_name}: embedding 实测 {len(embeddings)}，复核基线 {expected.object_count}"
        )

    sheets = _sheet_parts(entries)
    part = sheets.get(expected.host_sheet)
    if not part:
        raise HTemplateSanitizationError(f"{expected.file_name}: 找不到宿主 sheet {expected.host_sheet}")
    sheet_xml = entries[part].decode("utf-8")
    blocks = re.findall(r"<oleObjects>[\s\S]*?</oleObjects>", sheet_xml)
    if len(blocks) != 1:
        raise HTemplateSanitizationError(
            f"{expected.file_name}: oleObjects 块实测 {len(blocks)}（应 1）"
        )
    # Choice + Fallback 各有一份同 id 标签；按唯一 r:id 数真实对象。
    rids = set(re.findall(r'<oleObject\b[^>]*\br:id="([^"]+)"', blocks[0]))
    prog_ids = set(re.findall(r'<oleObject\b[^>]*\bprogId="([^"]+)"', blocks[0]))
    if len(rids) != expected.object_count or prog_ids != {"Equation.3"}:
        raise HTemplateSanitizationError(
            f"{expected.file_name}: OLE 不是复核过的 Equation.3 集合（rids={rids}, progIds={prog_ids}）"
        )

    changes: dict[str, bytes] = _repair_ns0_relationships(entries)
    removed = set(embedding_parts)
    preview_before = _preview_inventory(entries)
    changes[part] = re.sub(
        r"<oleObjects>[\s\S]*?</oleObjects>", "", sheet_xml, count=1
    ).encode("utf-8")

    sheet_rels = _rels_path(part)
    if sheet_rels not in entries:
        raise HTemplateSanitizationError(f"{expected.file_name}: OLE 宿主没有 rels")
    new_rels, ole_rels = _remove_relationships(entries[sheet_rels], suffix=_OLE_REL_SUFFIX)
    if len(ole_rels) != expected.object_count:
        raise HTemplateSanitizationError(
            f"{expected.file_name}: oleObject relationship 实测 {len(ole_rels)}（应 {expected.object_count}）"
        )
    changes[sheet_rels] = new_rels

    # VML 静态 Pict 预览必须完整存在，且其 image 关系与媒体部件留在包里。
    vml_parts: list[str] = []
    rel_root = ET.fromstring(entries[sheet_rels])
    image_relationships = [
        dict(r.attrib) for r in rel_root if str(r.attrib.get("Type") or "").endswith(_IMAGE_REL_SUFFIX)
    ]
    if len(image_relationships) != expected.object_count:
        raise HTemplateSanitizationError(
            f"{expected.file_name}: 静态 preview image 关系 {len(image_relationships)}，"
            f"应与 OLE 对象 {expected.object_count} 一一对应"
        )
    for rel in rel_root:
        if str(rel.attrib.get("Type") or "").endswith("/vmlDrawing"):
            target = rel.attrib["Target"]
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(part), target))
            vml_parts.append(resolved)
    pict_count = 0
    for vml in vml_parts:
        text = entries[vml].decode("utf-8")
        pict_count += len(re.findall(r'<x:ClientData\s+ObjectType="Pict">', text))
        # H2~H5 的 preview shape 带 o:ole="t"；去掉交互语义，保留 v:imagedata + Anchor。
        cleaned = text.replace(' o:ole="t"', "")
        if cleaned != text:
            changes[vml] = cleaned.encode("utf-8")
    if pict_count < expected.object_count:
        raise HTemplateSanitizationError(
            f"{expected.file_name}: VML Pict preview 仅 {pict_count}，少于 OLE {expected.object_count}"
        )

    # 移除 embedding 专属 content-type overrides；保留 .bin Default（打印设置仍使用）。
    ct = entries["[Content_Types].xml"].decode("utf-8")
    ct2 = re.sub(r'<Override\s+PartName="/xl/embeddings/[^"]+"[^>]*/>', "", ct)
    if ct2 != ct:
        changes["[Content_Types].xml"] = ct2.encode("utf-8")

    result = _rewrite_zip(source, changes, removed)
    with zipfile.ZipFile(io.BytesIO(result)) as zf:
        after_entries = {i.filename: zf.read(i.filename) for i in zf.infolist()}
    if _preview_inventory(after_entries) != preview_before:
        raise HTemplateSanitizationError(f"{expected.file_name}: 静态预览媒体发生变化")
    return result, {
        "state": "sanitized",
        "removed_ole_objects": expected.object_count,
        "removed_embedding_bytes": sum(len(entries[n]) for n in embeddings),
        "preserved_preview_images": len(image_relationships),
        "preserved_preview_media": len(preview_before),
    }


def _external_formula_bodies(entries: dict[str, bytes]) -> list[tuple[str, str]]:
    sheets = _sheet_parts(entries)
    found: list[tuple[str, str]] = []
    for sheet, part in sheets.items():
        text = entries[part].decode("utf-8")
        for match in _EXTERNAL_FORMULA_RE.finditer(text):
            found.append((sheet, match.group("body")))
    return found


def sanitize_h8_external_links(source: bytes) -> tuple[bytes, dict[str, Any]]:
    """将 115 个断链 enhanced-workbook 公式内化为本册同 sheet 引用。"""
    with zipfile.ZipFile(io.BytesIO(source)) as zf:
        entries = {i.filename: zf.read(i.filename) for i in zf.infolist()}
    ext_parts = {n for n in entries if n.startswith("xl/externalLinks/")}
    formulas = _external_formula_bodies(entries)
    if not ext_parts and not formulas:
        repairs = _repair_ns0_relationships(entries)
        repaired = _rewrite_zip(source, repairs, set())
        return repaired, {
            "state": "normalized_relationship_namespace" if repairs else "already_clean",
            "internalized_formulas": 0,
            "normalized_relationship_parts": len(repairs),
        }
    if len(formulas) != 115:
        raise HTemplateSanitizationError(
            f"{_H8}: 外链公式实测 {len(formulas)}，复核基线 115；拒绝按过期口径改"
        )
    local_sheets = set(_sheet_parts(entries))
    missing: list[str] = []
    for _host, formula in formulas:
        refs = _EXTERNAL_REF_RE.findall(formula)
        if not refs:
            raise HTemplateSanitizationError(f"{_H8}: 无法解析外链公式 {formula!r}")
        missing.extend((a or b) for a, b in refs if (a or b) not in local_sheets)
    if missing:
        raise HTemplateSanitizationError(
            f"{_H8}: 外链引用了本册不存在的 sheet {sorted(set(missing))}，不得自动内化"
        )

    changes: dict[str, bytes] = _repair_ns0_relationships(entries)
    sheet_parts = _sheet_parts(entries)
    changed_formula_count = 0
    for _sheet, part in sheet_parts.items():
        text = entries[part].decode("utf-8")

        def _internalize(match: re.Match[str]) -> str:
            nonlocal changed_formula_count
            changed_formula_count += 1
            # 只删外部工作簿 index；sheet 名、单元格/范围、公式其它字符逐字保留。
            body = re.sub(r"\[\d+\]", "", match.group("body"))
            return f"<f{match.group('attrs')}>{body}</f>"

        rewritten = _EXTERNAL_FORMULA_RE.sub(_internalize, text)
        if rewritten != text:
            changes[part] = rewritten.encode("utf-8")
    if changed_formula_count != 115:
        raise HTemplateSanitizationError(
            f"{_H8}: 实际内化 {changed_formula_count}，复核基线 115"
        )

    workbook = entries["xl/workbook.xml"].decode("utf-8")
    workbook2, n_ref = re.subn(
        r"<externalReferences>[\s\S]*?</externalReferences>", "", workbook
    )
    if n_ref != 1:
        raise HTemplateSanitizationError(f"{_H8}: externalReferences 块实测 {n_ref}（应 1）")
    changes["xl/workbook.xml"] = workbook2.encode("utf-8")

    wb_rels, removed_rels = _remove_relationships(
        entries["xl/_rels/workbook.xml.rels"], suffix="/externalLink"
    )
    if len(removed_rels) != 3:
        raise HTemplateSanitizationError(f"{_H8}: externalLink 关系 {len(removed_rels)}（应 3）")
    changes["xl/_rels/workbook.xml.rels"] = wb_rels

    ct = entries["[Content_Types].xml"].decode("utf-8")
    ct2 = re.sub(r'<Override\s+PartName="/xl/externalLinks/[^"]+"[^>]*/>', "", ct)
    if ct2 != ct:
        changes["[Content_Types].xml"] = ct2.encode("utf-8")

    result = _rewrite_zip(source, changes, ext_parts)
    with zipfile.ZipFile(io.BytesIO(result)) as zf:
        after_entries = {i.filename: zf.read(i.filename) for i in zf.infolist()}
    if _external_formula_bodies(after_entries):
        raise HTemplateSanitizationError(f"{_H8}: 净化后仍有外链公式")
    if any(n.startswith("xl/externalLinks/") for n in after_entries):
        raise HTemplateSanitizationError(f"{_H8}: 净化后仍有 externalLinks part")
    return result, {
        "state": "sanitized",
        "internalized_formulas": changed_formula_count,
        "removed_external_parts": len(ext_parts),
        "removed_external_relationships": len(removed_rels),
        "all_reference_sheets_local": True,
    }


def _validate_package(data: bytes) -> None:
    """安全门 + openpyxl 双校验；命令退出 0 不算完成。"""
    import openpyxl
    from app.services.workpaper_sync.artifacts import load_limits, validate_ooxml_artifact

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as fh:
        fh.write(data)
        temp = Path(fh.name)
    try:
        validate_ooxml_artifact(temp, document_type="xlsx", limits=load_limits())
        wb = openpyxl.load_workbook(temp, read_only=True, data_only=False, keep_links=True)
        try:
            if not wb.sheetnames:
                raise HTemplateSanitizationError("净化后工作簿没有 sheet")
        finally:
            wb.close()
    finally:
        temp.unlink(missing_ok=True)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(*, apply: bool) -> dict[str, Any]:
    report: dict[str, Any] = {"mode": "apply" if apply else "check", "templates": []}
    for spec in _OLE_TEMPLATES:
        path = _H_ROOT / spec.file_name
        before = path.read_bytes()
        after, facts = sanitize_ole_equations(before, spec)
        _validate_package(after)
        if apply and after != before:
            temp = path.with_suffix(".xlsx.sanitizing")
            temp.write_bytes(after)
            temp.replace(path)
        report["templates"].append(
            {"file": spec.file_name, "before_sha256": _sha(before),
             "after_sha256": _sha(after), "changed": before != after, **facts}
        )

    path = _H_ROOT / _H8
    before = path.read_bytes()
    after, facts = sanitize_h8_external_links(before)
    _validate_package(after)
    if apply and after != before:
        temp = path.with_suffix(".xlsx.sanitizing")
        temp.write_bytes(after)
        temp.replace(path)
    report["templates"].append(
        {"file": _H8, "before_sha256": _sha(before), "after_sha256": _sha(after),
         "changed": before != after, **facts}
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只读预演（默认）")
    mode.add_argument("--apply", action="store_true", help="原子写回 6 本权威模板")
    parser.add_argument("--json", default=None, help="报告写入路径")
    args = parser.parse_args()
    try:
        report = run(apply=bool(args.apply))
    except Exception as exc:  # noqa: BLE001 - CLI 必须给出单一非零结算
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        return 1
    for row in report["templates"]:
        print(
            f"[{row['state']}] {row['file']}: changed={row['changed']} "
            f"{row['before_sha256'][:12]} -> {row['after_sha256'][:12]}"
        )
        for key in (
            "removed_ole_objects", "preserved_preview_images", "internalized_formulas",
            "removed_external_parts",
        ):
            if key in row:
                print(f"    {key}={row[key]}")
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print("[OK] 安全门 + openpyxl 校验全部通过" + ("，已写盘" if args.apply else "，一行未写"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
