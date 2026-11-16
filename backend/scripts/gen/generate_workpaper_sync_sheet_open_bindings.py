"""生成 Sheet → published sync entry 的显式绑定清单。

Usage from repository root::

    python backend/scripts/gen/generate_workpaper_sync_sheet_open_bindings.py --apply
    python backend/scripts/gen/generate_workpaper_sync_sheet_open_bindings.py --check

本生成器只把当前 manifest 的 source-backed 事实投影为待审核 binding；它不会在运行时
读取模板目录、按 sheet 名猜父级编码，也不会把 `xlsx-sheet/*` 伪造进 manifest。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "backend" / "data"
MANIFEST = DATA / "workpaper_sync_entry_manifest.json"
OVERLAY = DATA / "workpaper_sync_entry_overlay.json"
ADJUDICATION = DATA / "workpaper_sync_entry_wp_code_adjudication.json"
#: 输出路径。**可被 `GT_SHEET_BINDINGS_OUT` 覆盖** —— 变异套件用它把生成结果写到
#: 沙箱目录，从而完全不碰已跟踪的真实产物（否则 `_tracked_write_guard` 会报警，
#: 且进程被打断时可能留下变异态产物 —— 本仓踩过这个坑）。
OUTPUT = Path(
    os.environ.get("GT_SHEET_BINDINGS_OUT")
    or str(DATA / "workpaper_sync_sheet_open_bindings.json")
)
SCHEMA_VERSION = "sheet-open-binding:v1"
STATUSES = {"pending", "ready", "migrated", "draining", "retired", "out_of_scope"}
MAPPING_KINDS = {"exact", "provider", "whole_workbook", "ambiguous", "out_of_scope"}

#: `pending` 的**封闭**原因集（spec 1.4）。
#:
#: 🔴 为什么必须封闭：`reason` 是前端与运维唯一的归因线索。开放字符串会让「新加一条
#: 未登记原因」静默通过 —— 用户看到一句没人写过的中文、监控按前缀分组时落进「其他」，
#: 而没人知道该找谁。封闭域 + 生成器断言 = 加原因必须同时改这里（一次显式决策）。
PENDING_REASONS = {
    # 文档类型不适用本迁移（custom / Word / single_onlyoffice）
    "document_type_out_of_scope",
    # 整册入口：需人工审核 target scope 后才可晋级
    "whole_workbook_target_requires_reviewed_binding",
    # exact 候选：sheet 名与 wp_code 都是字面量，但仍需确认 published artifact 里真有它
    "exact_candidate_requires_published_artifact_review",
    # provider 候选：sheet 名是运行时表达式，必须由 provider 声明 target sheet
    "runtime_sheet_name_requires_provider_binding",
    # 多义：同一 wp_code 命中多张 sheet，不得猜
    "ambiguous_sheet_target",
    # 没有声明任何 sheet 目标
    "sheet_target_not_declared",
    # manifest / overlay / adjudication 源 digest 在生成后变过
    "source_digest_stale",
    # entry 不在 manifest（binding 引用了已删除 entry）
    "manifest_entry_missing",
}

#: provider binding 的 resolver identity 前缀。
#:
#: 🔴 为什么需要**稳定** identity：provider 的 `sheet_name` 是运行时表达式，解析时要由
#: provider 自己给出 target sheet。若 identity 按 entry 名或行号临时算，manifest 一重排
#: 全部 provider binding 的 `binding_id` 就变 ⇒ 已审核的 binding 集体失效、需要重审。
#: 用 `wp_code_patterns` + `sheet_expressions` 的规范化摘要，与 manifest 顺序无关。
PROVIDER_RESOLVER_PREFIX = "provider:"


def digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path) -> tuple[Any, str]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), digest_bytes(raw)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def source_digest(path: Path) -> str | None:
    return digest_bytes(path.read_bytes()) if path.is_file() else None


def mount_text(entry: dict[str, Any]) -> str:
    return canonical_json(entry.get("mounts") or [])


def has_whole_workbook_marker(entry: dict[str, Any]) -> bool:
    text = mount_text(entry).lower()
    return any(marker in text for marker in ("whole-workbook", "whole_workbook", "wholeworkbook"))


def binding_for(entry: dict[str, Any], *, input_digest: str) -> dict[str, Any]:
    entry_id = str(entry.get("entry_id") or "").strip()
    effective_id = str(entry.get("effective_entry_id") or entry_id).strip()
    document_type = str(entry.get("document_type") or "").strip()
    wp_match = entry.get("wp_match") or {}
    wp_patterns = [str(x).strip() for x in (wp_match.get("wp_code_patterns") or []) if str(x).strip()]
    sheet_literals = [str(x).strip() for x in (wp_match.get("sheet_literals") or []) if str(x).strip()]
    sheet_expressions = [str(x).strip() for x in (wp_match.get("sheet_expressions") or []) if str(x).strip()]
    source_host = str(wp_match.get("source_host") or entry.get("host_path") or "").strip() or None

    if document_type != "xlsx":
        kind = "out_of_scope"
        status = "out_of_scope"
        reason = "document_type_out_of_scope"
        scope = "out_of_scope"
    elif has_whole_workbook_marker(entry):
        kind = "whole_workbook"
        status = "pending"
        reason = "whole_workbook_target_requires_reviewed_binding"
        scope = "whole_workbook"
    elif len(wp_patterns) > 1:
        # 🔴 多 wp_code 必须**先于** exact / provider 判（spec 1.4）：一个 entry 声明多个
        # wp_code 时，一个 sheet 请求可能命中多张表，任何「挑第一个」都是猜。放在 provider
        # 之后就永远进不来（`wp_patterns` 非空 ⇒ provider 分支先命中）—— 实测踩过。
        kind = "ambiguous"
        status = "pending"
        reason = "ambiguous_sheet_target"
        scope = "single_sheet"
    elif len(sheet_literals) == 1 and len(wp_patterns) == 1:
        kind = "exact"
        status = "pending"
        reason = "exact_candidate_requires_published_artifact_review"
        scope = "single_sheet"
    elif sheet_expressions or wp_patterns:
        kind = "provider"
        status = "pending"
        reason = "runtime_sheet_name_requires_provider_binding"
        scope = "single_sheet"
    else:
        kind = "ambiguous"
        status = "pending"
        reason = "sheet_target_not_declared"
        scope = "single_sheet"

    row: dict[str, Any] = {
        "entry_id": entry_id,
        "effective_entry_id": effective_id,
        "source_wp_code": wp_patterns[0] if len(wp_patterns) == 1 else None,
        "document_scope": scope,
        "target_sheet": sheet_literals[0] if len(sheet_literals) == 1 else None,
        "sheet_key": sheet_literals[0] if len(sheet_literals) == 1 else None,
        "mapping_kind": kind,
        "status": status,
        "reason": reason,
        "manifest_entry_digest": digest_bytes(canonical_json(entry).encode("utf-8")),
        "source_refs": [source_host] if source_host else [],
        "owner": None,
        "input_digest": input_digest,
        "independent_entry": bool(entry.get("independent_entry", False)),
        "document_type": document_type,
        "capability": entry.get("capability"),
        "wp_code_patterns": wp_patterns,
        "sheet_expressions": sheet_expressions,
        "sheet_literals": sheet_literals,
        # provider 候选的稳定 resolver identity（spec 1.3）。与 manifest 顺序无关：
        # 只由「声明了哪些 wp_code / sheet 表达式」决定，重排 manifest 不改它。
        "resolver_identity": (
            PROVIDER_RESOLVER_PREFIX
            + digest_bytes(
                canonical_json({
                    "wp_code_patterns": sorted(wp_patterns),
                    "sheet_expressions": sorted(sheet_expressions),
                }).encode("utf-8")
            )[:16]
            if kind == "provider"
            else None
        ),
    }
    binding_material = {k: v for k, v in row.items() if k != "binding_id"}
    row["binding_id"] = "sha256:" + digest_bytes(canonical_json(binding_material).encode("utf-8"))
    return row


def build() -> dict[str, Any]:
    manifest, manifest_digest = read_json(MANIFEST)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("entries"), list):
        raise RuntimeError("manifest 缺少 entries 数组")
    overlay_digest = source_digest(OVERLAY)
    adjudication_digest = source_digest(ADJUDICATION)
    # 只对**被读的那张表**算摘要：整份文件里还有别的段落，改它们不该让 binding 变 stale。
    wp_code_adjudication_digest = digest_bytes(
        canonical_json(
            (read_json(ADJUDICATION)[0] or {}).get("wp_code_adjudication") or {}
        ).encode("utf-8")
    )
    input_material = {
        "manifest_digest": manifest_digest,
        "overlay_digest": overlay_digest,
        "adjudication_digest": adjudication_digest,
        "wp_code_adjudication_digest": wp_code_adjudication_digest,
        "schema_version": SCHEMA_VERSION,
    }
    input_digest = digest_bytes(canonical_json(input_material).encode("utf-8"))
    rows = [binding_for(dict(entry), input_digest=input_digest) for entry in manifest["entries"]]
    rows.sort(key=lambda row: (row["entry_id"], row["effective_entry_id"]))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "manifest": str(MANIFEST.relative_to(REPO)).replace("\\", "/"),
            "manifest_digest": manifest_digest,
            "overlay": str(OVERLAY.relative_to(REPO)).replace("\\", "/"),
            "overlay_digest": overlay_digest,
            "adjudication": str(ADJUDICATION.relative_to(REPO)).replace("\\", "/"),
            "adjudication_digest": adjudication_digest,
            # Requirement 8.1 点名：`wp_code` 裁决表本身的摘要（adjudication 文件里
            # 真正被读的那张表）。它与 `adjudication_digest`（整份文件）不同 ——
            # 整份文件里还有别的段落，改那些段落不该让 binding 变 stale。
            "wp_code_adjudication_digest": wp_code_adjudication_digest,
        },
        "input_digest": input_digest,
        "summary": {"entry_count": len(rows), "status_counts": counts},
        "bindings": rows,
    }


def render(payload: dict[str, Any], *, newline: str = "\n") -> bytes:
    """渲染生成物。

    🔴 `newline` 必须与**目标文件当前行尾**一致：`core.autocrlf=true` 下工作树是 CRLF
    而本函数默认 LF ⇒ `--check` 读工作树字节与输出恒不等 ⇒ 恒红。
    目标文件不存在时用 LF（git 会归一，不产生 churn）。

    与 `generate_legacy_onlyoffice_caller_ledger.render` 同族 —— 两个生成器都踩过。
    """
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if newline != "\n":
        text = text.replace("\n", newline)
    return text.encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    # 行尾与目标文件一致（见 render 的说明）。
    newline = "\n"
    if OUTPUT.is_file() and b"\r\n" in OUTPUT.read_bytes():
        newline = "\r\n"
    expected = render(build(), newline=newline)
    current = OUTPUT.read_bytes() if OUTPUT.is_file() else None
    if args.check:
        if current != expected:
            print(f"[FAIL] {OUTPUT}: generated binding projection is stale or missing")
            return 1
        print(f"[OK] {OUTPUT}: {len(json.loads(expected)['bindings'])} bindings")
        return 0
    OUTPUT.write_bytes(expected)
    print(f"[APPLIED] {OUTPUT}: {len(json.loads(expected)['bindings'])} bindings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
