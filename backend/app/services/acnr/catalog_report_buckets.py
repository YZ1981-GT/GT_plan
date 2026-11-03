"""ACNR 目录报告四组分组（design §7.1 / 需求 6.1，T09）——纯计算，不写文件。

`catalog_report.json` 的可追责部分是四组 `{"count": n, "items": [...]}`，`count` 恒为 `len(items)`：

- blocking：发布门禁违规（含未处置的别名冲突与未登记别名、过期或失效的豁免）；生成器只在它为 0 时写出，
  故已提交报告恒为 0；
- acknowledged：有效豁免（id / kind / owner / expires_on / covers）；
- deprecated：停用条目与 replaced_by；
- info：父级限定别名、禁止别名、非地址标签与并入别名的处置、沿用的旧别名、补登 sheet、经 overrides 登记的 I/E、
  显示名为纯编码的 sheet、带 skip_reason 的 sheet。

`summary` 只留 `total_sheets`、`total_cells` 与四组计数。到期判定只在门禁运行时计算、不写进报告。
只依赖标准库。
"""
from __future__ import annotations

import json
from typing import Any, Iterable

BUCKETS = ("blocking", "acknowledged", "deprecated", "info")


def _bucket(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = sorted(items, key=lambda r: json.dumps(r, ensure_ascii=False, sort_keys=True))
    return {"count": len(rows), "items": rows}


def _acknowledged(acknowledgements: Any) -> list[dict[str, Any]]:
    entries = acknowledgements.get("entries", []) if isinstance(acknowledgements, dict) else (acknowledgements or [])
    keep = ("id", "kind", "owner", "expires_on", "covers", "head_resolvable_at")
    return [{k: e[k] for k in keep if k in e} for e in entries if isinstance(e, dict)]


def _deprecated(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for kind, seg in (("sheet", "sheets"), ("cell", "cells")):
        for e in catalog.get(seg, []):
            if e.get("deprecated"):
                out.append({"kind": kind, "addr_id": e.get("addr_id", ""), "replaced_by": e.get("replaced_by")})
    return out


def _info(catalog: dict[str, Any], *, alias_entries: list[dict[str, Any]], parent_qualified: dict[str, dict[str, str]],
          carried_over: dict[str, list[str]], merged: dict[str, list[str]], sheet_verdicts: dict[str, Any] | None,
          overrides: dict[str, Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, by_parent in sorted(parent_qualified.items()):
        out.append({"kind": "parent_qualified_alias", "alias": name, "sheets": dict(sorted(by_parent.items()))})
    for parent, by_alias in sorted(((catalog.get("alias_policy") or {}).get("forbidden") or {}).items()):
        for alias, codes in sorted(by_alias.items()):
            out.append({"kind": "forbidden_alias", "parent_wp_code": parent, "alias": alias, "sheet_codes": list(codes)})
    for e in alias_entries:
        if e.get("disposition") in ("non_address_label", "merge_into", "project_context"):
            row = {"kind": e["disposition"], "alias": e.get("alias", ""), "reason": e.get("reason", "")}
            if e.get("target"):
                row["target"] = e["target"]
                row["merged_aliases"] = list(merged.get(e["target"], []))
            out.append(row)
    for aid, aliases in sorted(carried_over.items()):
        out.append({"kind": "carried_over_alias", "addr_id": aid, "aliases": list(aliases)})
    for v in (sheet_verdicts or {}).get("sheet_verdicts", []):
        if isinstance(v, dict) and v.get("verdict") == "add_platform_sheet":
            out.append({"kind": "platform_sheet_added", "addr_id": v.get("addr_id", "")})
    for o in (overrides or {}).get("overrides", []):
        if isinstance(o, dict) and "import_export" in (o.get("fields") or {}):
            out.append({"kind": "override_import_export", "addr_id": o.get("addr_id", ""), "source": o.get("source", "")})
    for s in catalog.get("sheets", []):
        if s.get("sheet_name") == s.get("sheet_code"):
            out.append({"kind": "display_name_is_code", "addr_id": s.get("addr_id", "")})
        if s.get("skip_reason"):
            out.append({"kind": "skip_reason", "addr_id": s.get("addr_id", ""), "skip_reason": s["skip_reason"]})
    return out


def build_buckets(catalog: dict[str, Any], *, violations: Iterable[Any], acknowledgements: Any,
                  alias_entries: list[dict[str, Any]], parent_qualified: dict[str, dict[str, str]],
                  carried_over: dict[str, list[str]], merged: dict[str, list[str]],
                  sheet_verdicts: dict[str, Any] | None, overrides: dict[str, Any] | None) -> dict[str, Any]:
    """四组 + summary（见模块文档）。violations 为 `catalog_release.GateViolation` 列表。"""
    groups = {
        "blocking": _bucket({"check": v.check, "addr_id": v.addr_id, "detail": v.detail} for v in violations),
        "acknowledged": _bucket(_acknowledged(acknowledgements)),
        "deprecated": _bucket(_deprecated(catalog)),
        "info": _bucket(_info(catalog, alias_entries=alias_entries, parent_qualified=parent_qualified,
                              carried_over=carried_over, merged=merged, sheet_verdicts=sheet_verdicts,
                              overrides=overrides)),
    }
    summary = {"total_sheets": len(catalog.get("sheets", [])), "total_cells": len(catalog.get("cells", []))}
    summary.update({name: groups[name]["count"] for name in BUCKETS})
    return {"summary": summary, **groups}


def bucket_problems(report: dict[str, Any]) -> list[str]:
    """报告结构自检：四组都在、`count == len(items)`、summary 计数与各组一致（读取方与守卫共用）。"""
    problems: list[str] = []
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    for name in BUCKETS:
        group = report.get(name)
        if not (isinstance(group, dict) and isinstance(group.get("items"), list)):
            problems.append(f"缺少分组 {name}（须为 {{count, items}}）")
            continue
        if group.get("count") != len(group["items"]):
            problems.append(f"{name}.count={group.get('count')} 与 items 条数 {len(group['items'])} 不符")
        if summary.get(name) != group.get("count"):
            problems.append(f"summary.{name}={summary.get(name)} 与 {name}.count={group.get('count')} 不符")
    return problems


__all__ = ["BUCKETS", "bucket_problems", "build_buckets"]
