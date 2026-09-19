"""Task 6（真实 OO 9.4 Word tagged SDT 载体）证据**独立重算器**。

为什么要有这个文件
------------------
`probe_oo94_word_sdt.py` 既采集又判定，`operation_matrix.json` 是它自己的输出。
如果验收只读那份 JSON，就等于让被测方自证 —— 属于 memory 里记的假绿第②源
（守卫只查字符串/摘要存在）。本脚本**不 import 探针任何函数**，只吃两样东西：

1. `evidence/task6-oo94-word-tagged-sdt/staging/{doc}_instrumented.docx`（基线字节）
2. `evidence/task6-oo94-word-tagged-sdt/artifacts/*.docx`（真实 OO 回传字节）

并用另一套实现（**按 sdtContent 的内容形态**判层级，而非按父节点标签）重新推出
Property 33 的三项判据 + Requirement 7.3 的 SDT 外正文判据，最后与探针矩阵逐格比对。
两套实现结论不一致 ⇒ 报 MISMATCH，宁可打红也不合并。

用法（Windows）::

    python backend/scripts/diagnose/verify_task6_word_sdt_evidence.py
    python backend/scripts/diagnose/verify_task6_word_sdt_evidence.py --write

本脚本是 probe 证据的重算器，**不是**生产 extractor：它不产业务 projection、不做
merge、不写模板库、不提供 paragraph/regex 兜底。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVIDENCE_DIR = (
    REPO_ROOT
    / ".kiro"
    / "specs"
    / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
    / "evidence"
    / "task6-oo94-word-tagged-sdt"
)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

#: artifact 文件名前缀 → doc key（probe 的命名约定）
DOC_KEYS = ("f222", "f223", "b30112")

ROW_TAG_RE = re.compile(r"^gt:row:[^:]+:[^:]+:([0-9a-fA-F-]{36})$")
FIELD_ROW_TAG_RE = re.compile(r"^gt:field:[^:]+:rows/([0-9a-fA-F-]{36})/.+$")

#: 探针操作者**故意**改动 SDT 外正文的操作（取证 Requirement 7.3 的「自由正文可被人改」）。
#: 这些 op 及其之后的 op 继承该外部改动，故 SDT 外正文允许与基线不同；
#: 其余 op 的 SDT 外正文必须**零行丢失**。新增行永远允许（Word-only 自由正文可增长）。
INTENTIONAL_EXTERNAL_EDIT_OPS: set[tuple[str, str]] = {
    ("f222", "edit_outside_sdt"),
    ("f222", "insert_paragraph"),
    ("f222", "delete_paragraph"),
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _squash(text: str) -> str:
    """全角空格归一 + 去掉所有空白。

    OO 会重排 run（一个 `w:t` 被拆成多个），逐行比会把纯重排误报成正文丢失，
    所以 SDT 外正文的判据用**连写串**。
    """
    return re.sub(r"\s+", "", text.replace("\u3000", " "))


def _document_xml(docx: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        return z.read("word/document.xml")


def _shape_of(sdt: ET.Element) -> str:
    """按 `w:sdtContent` 的**直接子节点形态**判层级（与探针的父节点判法互为独立实现）。"""
    content = sdt.find(f"{W}sdtContent")
    if content is None:
        return "no_content"
    kinds = {child.tag.split("}")[-1] for child in content}
    if "tr" in kinds:
        return "row"
    if "tc" in kinds:
        return "cell"
    if "tbl" in kinds and "p" not in kinds:
        return "table"
    if "p" in kinds:
        return "block"
    if kinds & {"r", "hyperlink", "fldSimple", "bookmarkStart", "sdt", "ins", "del"}:
        return "inline"
    return "shape:" + ",".join(sorted(kinds)) if kinds else "empty"


def inventory(docx: bytes) -> dict[str, Any]:
    """独立采集一份 DOCX 的 SDT 载体清册。"""
    root = ET.fromstring(_document_xml(docx))

    parent: dict[ET.Element, ET.Element] = {}
    for el in root.iter():
        for child in el:
            parent[child] = el

    def sdt_ancestors(el: ET.Element) -> list[str]:
        chain: list[str] = []
        cur = parent.get(el)
        while cur is not None:
            if cur.tag == f"{W}sdt":
                t = cur.find(f"{W}sdtPr/{W}tag")
                chain.append(t.get(f"{W}val", "<no-tag>") if t is not None else "<no-tag>")
            cur = parent.get(cur)
        return list(reversed(chain))

    instances: list[dict[str, Any]] = []
    untagged = 0
    for sdt in root.iter(f"{W}sdt"):
        tag_el = sdt.find(f"{W}sdtPr/{W}tag")
        tag = tag_el.get(f"{W}val") if tag_el is not None else None
        if tag is None:
            untagged += 1
        content = sdt.find(f"{W}sdtContent")
        instances.append(
            {
                "tag": tag,
                "shape": _shape_of(sdt),
                "ancestors": sdt_ancestors(sdt),
                "depth": len(sdt_ancestors(sdt)),
                "text": _squash("".join(t.text or "" for t in content.iter(f"{W}t")))
                if content is not None
                else "",
            }
        )

    tags = [i["tag"] for i in instances if i["tag"]]
    multiset = dict(sorted(Counter(tags).items()))

    # SDT 外正文：不在任何 sdtContent 子树内的 w:t
    inside: set[ET.Element] = set()
    for sdt in root.iter(f"{W}sdt"):
        content = sdt.find(f"{W}sdtContent")
        if content is not None:
            inside.update(content.iter())
    external = _squash("".join(t.text or "" for t in root.iter(f"{W}t") if t not in inside))

    #: SDT 外正文的「行」= 按**所属段落**聚合（探针按单个 `w:t` 聚合）。
    #: 段落级聚合对 OO 的 run 重排更不敏感，也让两套实现的 line 判据真正独立。
    external_lines: list[str] = []
    for para in root.iter(f"{W}p"):
        if para in inside:
            continue
        text = _squash("".join(t.text or "" for t in para.iter(f"{W}t") if t not in inside))
        if text:
            external_lines.append(text)

    row_from_row_sdt = sorted(
        {m.group(1).lower() for t in tags if (m := ROW_TAG_RE.match(t or ""))}
    )
    row_from_field = sorted(
        {m.group(1).lower() for t in tags if (m := FIELD_ROW_TAG_RE.match(t or ""))}
    )

    tables: list[dict[str, Any]] = []
    for tbl in root.iter(f"{W}tbl"):
        trs = list(tbl.iter(f"{W}tr"))
        tables.append(
            {
                "row_count": len(trs),
                "rows_wrapped_in_sdt": sum(
                    1
                    for tr in trs
                    if parent.get(tr) is not None and parent[tr].tag == f"{W}sdtContent"
                ),
            }
        )

    return {
        "sdt_count": len(instances),
        "untagged_sdt_count": untagged,
        "tag_multiset": multiset,
        "shapes": {t: sorted({i["shape"] for i in instances if i["tag"] == t}) for t in sorted(set(tags))},
        "ancestor_chains": {
            t: sorted({tuple(i["ancestors"]) for i in instances if i["tag"] == t})
            for t in sorted(set(tags))
        },
        "row_uuids_from_row_sdt": row_from_row_sdt,
        "row_uuids_from_field_tags": row_from_field,
        "external_body_digest": _sha256(external.encode("utf-8")),
        "external_body_chars": len(external),
        "external_body_concat": external,
        "external_body_lines": external_lines,
        "tables": tables,
        "instances": instances,
    }


def _is_row_tag(tag: str) -> bool:
    return tag.startswith("gt:row:")


def _chain_without_row_ancestors(chain: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(c for c in chain if not _is_row_tag(c))


def _doc_key_of(name: str) -> str | None:
    for key in DOC_KEYS:
        if name.startswith(key + "_"):
            return key
    return None


def _cumulative_intentional(matrix_doc_ops: list[str], declared: list[str], deletions: dict[str, list[str]], doc: str, op: str) -> list[str]:
    """「这一格及之前」声明过的有意删除（按 declared 操作序累积）。"""
    out: list[str] = []
    if op not in declared:
        return out
    upto = declared.index(op)
    for i, name in enumerate(declared):
        if i <= upto:
            out.extend(deletions.get(f"{doc}/{name}", []))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Task 6 Word SDT 证据独立重算器")
    ap.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE_DIR))
    ap.add_argument("--write", action="store_true", help="把重算结果写入 independent_recompute.json")
    args = ap.parse_args(argv)

    ev = Path(args.evidence_dir)
    matrix = json.loads((ev / "operation_matrix.json").read_text(encoding="utf-8"))
    instr = json.loads((ev / "instrumentation_report.json").read_text(encoding="utf-8"))

    findings: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recomputed_by": "backend/scripts/diagnose/verify_task6_word_sdt_evidence.py",
        "independence": "不 import probe；层级按 sdtContent 内容形态判定，probe 按父节点标签判定",
        "baselines": {},
        "template_identity": {},
        "artifacts": [],
        "mismatches": [],
        "verdict": {},
    }

    # ---- 1. 权威模板 ↔ staging before 副本 ↔ instrumented 基线 三点对齐 ----
    for doc, meta in instr["docs"].items():
        tpl = REPO_ROOT / meta["template_rel"]
        live_sha = _sha256(tpl.read_bytes()) if tpl.exists() else None
        before = ev / "staging" / f"{doc}_before.docx"
        before_sha = _sha256(before.read_bytes()) if before.exists() else None
        inst = ev / "staging" / f"{doc}_instrumented.docx"
        inst_bytes = inst.read_bytes()
        row = {
            "template_rel": meta["template_rel"],
            "template_sha256_in_report": meta["template_sha256"],
            "template_sha256_live_now": live_sha,
            "staging_before_sha256": before_sha,
            "live_matches_report": live_sha == meta["template_sha256"],
            "before_copy_matches_report": before_sha == meta["template_sha256"],
            "instrumented_sha256_in_report": meta["instrumented_sha256"],
            "instrumented_document_xml_sha256_in_report": meta["instrumented_document_xml_sha256"],
            "instrumented_document_xml_sha256_recomputed": _sha256(_document_xml(inst_bytes)),
        }
        row["instrumented_document_xml_matches"] = (
            row["instrumented_document_xml_sha256_recomputed"]
            == row["instrumented_document_xml_sha256_in_report"]
        )
        findings["template_identity"][doc] = row
        if not row["live_matches_report"]:
            findings["mismatches"].append(
                f"{doc}: 权威模板当前 sha256 与 instrumentation_report 记录不一致（模板可能被改动）"
            )
        if not row["before_copy_matches_report"]:
            findings["mismatches"].append(f"{doc}: staging before 副本 sha256 与权威模板不一致")
        if not row["instrumented_document_xml_matches"]:
            findings["mismatches"].append(f"{doc}: instrumented 基线 document.xml sha256 与报告不一致")

        base_inv = inventory(inst_bytes)
        findings["baselines"][doc] = {
            "sdt_count": base_inv["sdt_count"],
            "tag_multiset": base_inv["tag_multiset"],
            "shapes": base_inv["shapes"],
            "row_uuids_from_row_sdt": base_inv["row_uuids_from_row_sdt"],
            "row_uuids_from_field_tags": base_inv["row_uuids_from_field_tags"],
            "external_body_digest": base_inv["external_body_digest"],
            "external_body_chars": base_inv["external_body_chars"],
            "tables": base_inv["tables"],
        }

    baselines = {doc: inventory((ev / "staging" / f"{doc}_instrumented.docx").read_bytes()) for doc in instr["docs"]}

    declared_by_doc = {doc: matrix["coverage"][doc]["declared_operations"] for doc in instr["docs"]}
    deletions = matrix.get("intentional_deletions", {})
    matrix_by_artifact = {row["artifact_file"]: row for row in matrix["matrix"]}

    # ---- 2. 逐 artifact 独立重算 ----
    for path in sorted((ev / "artifacts").glob("*.docx")):
        doc = _doc_key_of(path.name)
        if doc is None:
            findings["mismatches"].append(f"{path.name}: 无法归属 doc key")
            continue
        raw = path.read_bytes()
        art_sha = _sha256(raw)
        inv = inventory(raw)
        base = baselines[doc]
        rel = f"artifacts/{path.name}"
        mrow = matrix_by_artifact.get(rel)

        op = (mrow or {}).get("op")
        intentional = _cumulative_intentional(
            [], declared_by_doc[doc], deletions, doc, op or ""
        )
        # 有意删除的注入 → 允许其 tag / row_uuid 消失
        removed_tags: set[str] = set()
        removed_uuids: set[str] = set()
        for inj in instr["docs"][doc]["manifest"].get("rows", []):
            if inj["inj_id"] in intentional:
                removed_tags.update({inj["row_tag"], inj["field_tag"]})
                removed_uuids.add(inj["row_uuid"].lower())
        for inj in instr["docs"][doc]["manifest"].get("fields", []):
            if inj.get("inj_id") in intentional:
                removed_tags.add(inj["tag"])

        base_ms = dict(base["tag_multiset"])
        now_ms = dict(inv["tag_multiset"])
        expected_ms = {t: c for t, c in base_ms.items() if t not in removed_tags}
        missing = sorted(t for t in expected_ms if t not in now_ms)
        reduced = {
            t: [expected_ms[t], now_ms.get(t, 0)]
            for t in expected_ms
            if now_ms.get(t, 0) < expected_ms[t]
        }
        added = sorted(t for t in now_ms if t not in base_ms)
        #: 🔴 按载体分桶，禁止把 row-level SDT 的失败摊进 field/block 桶（反之亦然）。
        missing_row_tags = sorted(t for t in missing if _is_row_tag(t))
        missing_field_block_tags = sorted(t for t in missing if not _is_row_tag(t))
        reduced_row_tags = {t: v for t, v in reduced.items() if _is_row_tag(t)}
        reduced_field_block_tags = {t: v for t, v in reduced.items() if not _is_row_tag(t)}

        expected_row_sdt_uuids = sorted(set(base["row_uuids_from_row_sdt"]) - removed_uuids)
        expected_field_uuids = sorted(set(base["row_uuids_from_field_tags"]) - removed_uuids)
        row_sdt_lost = sorted(set(expected_row_sdt_uuids) - set(inv["row_uuids_from_row_sdt"]))
        field_uuid_lost = sorted(set(expected_field_uuids) - set(inv["row_uuids_from_field_tags"]))

        shape_regressions = {
            t: {"baseline": base["shapes"][t], "now": inv["shapes"].get(t, [])}
            for t in expected_ms
            if t in inv["shapes"] and inv["shapes"][t] != base["shapes"][t]
        }
        chain_regressions: dict[str, Any] = {}
        chain_row_strip_side_effects: dict[str, Any] = {}
        for t in expected_ms:
            if t not in inv["ancestor_chains"]:
                continue
            was, now = base["ancestor_chains"][t], inv["ancestor_chains"][t]
            if was == now:
                continue
            payload = {"baseline": [list(c) for c in was], "now": [list(c) for c in now]}
            # 差异只是「row 祖先被剥掉」⇒ 记为 row 载体失败的连带后果，不算 field 桶的层级回归
            if {_chain_without_row_ancestors(c) for c in was} == {
                _chain_without_row_ancestors(c) for c in now
            }:
                chain_row_strip_side_effects[t] = payload
            else:
                chain_regressions[t] = payload

        # SDT 外正文：段落级行丢失/新增
        base_lines = Counter(base["external_body_lines"])
        now_lines = Counter(inv["external_body_lines"])
        lines_lost = sorted((base_lines - now_lines).elements())
        lines_added = sorted((now_lines - base_lines).elements())
        external_edit_declared = bool(
            op
            and any(
                (doc, name) in INTENTIONAL_EXTERNAL_EDIT_OPS
                for name in declared_by_doc[doc][: declared_by_doc[doc].index(op) + 1]
            )
            if op in declared_by_doc[doc]
            else False
        )

        entry = {
            "artifact_file": rel,
            "doc": doc,
            "op": op,
            "status": (mrow or {}).get("status"),
            "artifact_sha256_recomputed": art_sha,
            "artifact_sha256_in_matrix": (mrow or {}).get("artifact_sha256"),
            "artifact_sha256_matches": art_sha == (mrow or {}).get("artifact_sha256"),
            "in_matrix": mrow is not None,
            "intentionally_removed": intentional,
            "sdt_count": inv["sdt_count"],
            "untagged_sdt_count": inv["untagged_sdt_count"],
            "tag_missing": missing,
            "tag_counts_reduced": reduced,
            "tag_added": added,
            "tag_set_not_reduced": not missing and not reduced,
            "field_block_tag_missing": missing_field_block_tags,
            "field_block_tag_counts_reduced": reduced_field_block_tags,
            "field_block_tag_set_not_reduced": not missing_field_block_tags
            and not reduced_field_block_tags,
            "row_tag_missing": missing_row_tags,
            "row_tag_counts_reduced": reduced_row_tags,
            "row_tag_set_not_reduced": not missing_row_tags and not reduced_row_tags,
            "shape_regressions": shape_regressions,
            "ancestor_chain_regressions": chain_regressions,
            "ancestor_chain_row_strip_side_effects": chain_row_strip_side_effects,
            "hierarchy_preserved": not shape_regressions and not chain_regressions,
            "hierarchy_preserved_including_row_ancestors": not shape_regressions
            and not chain_regressions
            and not chain_row_strip_side_effects,
            "row_uuid_from_row_sdt_expected": expected_row_sdt_uuids,
            "row_uuid_from_row_sdt_present": inv["row_uuids_from_row_sdt"],
            "row_uuid_from_row_sdt_lost": row_sdt_lost,
            "row_uuid_from_field_tags_expected": expected_field_uuids,
            "row_uuid_from_field_tags_present": inv["row_uuids_from_field_tags"],
            "row_uuid_from_field_tags_lost": field_uuid_lost,
            "row_sdt_carrier_survived": (
                None if not expected_row_sdt_uuids else not row_sdt_lost
            ),
            "row_uuid_set_not_reduced": not (row_sdt_lost and field_uuid_lost)
            and not (set(expected_row_sdt_uuids) | set(expected_field_uuids))
            - (set(inv["row_uuids_from_row_sdt"]) | set(inv["row_uuids_from_field_tags"])),
            "external_body_digest": inv["external_body_digest"],
            "external_body_baseline_digest": base["external_body_digest"],
            "external_body_matches_baseline": inv["external_body_digest"] == base["external_body_digest"],
            "external_body_lines_lost": lines_lost,
            "external_body_lines_added": lines_added,
            "external_edit_declared_for_this_op": external_edit_declared,
            "external_body_no_unexplained_loss": (not lines_lost) or external_edit_declared,
            "tables": inv["tables"],
        }

        # ---- 与探针矩阵逐格比对 ----
        if mrow:
            claim = mrow["carriers"]
            pairs = [
                ("tag_set_not_reduced", entry["tag_set_not_reduced"], claim["w_tag"]["tag_set_not_reduced"]),
                # 与探针对齐用**严格**层级判据（row 祖先被剥掉也算层级回归）。
                # 分桶后的 lenient 版本只用于「把失败归因到哪个载体」，不参与一致性比对。
                (
                    "hierarchy_preserved",
                    entry["hierarchy_preserved_including_row_ancestors"],
                    claim["hierarchy"]["hierarchy_preserved"],
                ),
                (
                    "row_uuid_set_not_reduced",
                    entry["row_uuid_set_not_reduced"],
                    claim["row_uuid"]["row_uuid_set_not_reduced"],
                ),
                (
                    "sdt_external_body_matches_baseline",
                    entry["external_body_matches_baseline"],
                    claim["sdt_external_body"]["matches_baseline"],
                ),
                (
                    "row_sdt_carrier_survived",
                    entry["row_sdt_carrier_survived"],
                    claim["row_uuid"]["row_sdt_carrier_survived"],
                ),
            ]
            for name, mine, theirs in pairs:
                if bool(mine) != bool(theirs) if (mine is not None and theirs is not None) else mine != theirs:
                    findings["mismatches"].append(
                        f"{rel}/{name}: 独立重算={mine!r} 探针矩阵={theirs!r}"
                    )
            if not entry["artifact_sha256_matches"]:
                findings["mismatches"].append(f"{rel}: artifact sha256 与矩阵记录不一致")
        else:
            findings["mismatches"].append(f"{rel}: 不在 operation_matrix.json 里")

        findings["artifacts"].append(entry)

    # ---- 3. 汇总判定 ----
    arts = findings["artifacts"]
    by_doc: dict[str, dict[str, Any]] = {}
    for doc in instr["docs"]:
        rows = [a for a in arts if a["doc"] == doc]
        by_doc[doc] = {
            "artifact_count": len(rows),
            "field_block_tag_set_not_reduced_all": all(
                a["field_block_tag_set_not_reduced"] for a in rows
            ),
            "row_tag_set_not_reduced_all": all(a["row_tag_set_not_reduced"] for a in rows),
            "hierarchy_preserved_all": all(a["hierarchy_preserved"] for a in rows),
            "hierarchy_preserved_strict_all": all(
                a["hierarchy_preserved_including_row_ancestors"] for a in rows
            ),
            "external_body_no_unexplained_loss_all": all(
                a["external_body_no_unexplained_loss"] for a in rows
            ),
            "external_body_lines_lost_unexplained": sorted(
                {
                    line
                    for a in rows
                    if not a["external_edit_declared_for_this_op"]
                    for line in a["external_body_lines_lost"]
                }
            ),
            "row_sdt_carrier_survived_any": any(
                a["row_sdt_carrier_survived"] is True for a in rows
            ),
            "row_sdt_carrier_stripped_in": [
                a["artifact_file"] for a in rows if a["row_sdt_carrier_survived"] is False
            ],
            "row_uuid_via_field_tags_intact_all": all(
                not a["row_uuid_from_field_tags_lost"] for a in rows
            ),
            "row_uuid_set_not_reduced_all": all(a["row_uuid_set_not_reduced"] for a in rows),
        }
    row_probed = [d for d in by_doc.values() if d["row_sdt_carrier_stripped_in"] or d["row_sdt_carrier_survived_any"]]
    findings["verdict"] = {
        "per_doc": by_doc,
        "mismatch_count": len(findings["mismatches"]),
        "field_and_block_sdt_carrier": "PASS"
        if all(
            v["field_block_tag_set_not_reduced_all"] and v["hierarchy_preserved_all"]
            for v in by_doc.values()
        )
        else "FAIL",
        "row_level_sdt_carrier": (
            "NOT_PROBED"
            if not row_probed
            else (
                "FAIL"
                if any(v["row_sdt_carrier_stripped_in"] for v in by_doc.values())
                else "PASS"
            )
        ),
        "row_uuid_identity_via_cell_field_tags": "PASS"
        if all(v["row_uuid_via_field_tags_intact_all"] for v in by_doc.values())
        else "FAIL",
        "sdt_external_body_no_unexplained_loss": "PASS"
        if all(v["external_body_no_unexplained_loss_all"] for v in by_doc.values())
        else "FAIL",
    }
    findings["verdict"]["property_33"] = (
        "PASS"
        if (
            findings["verdict"]["field_and_block_sdt_carrier"] == "PASS"
            and findings["verdict"]["row_level_sdt_carrier"] == "PASS"
            and findings["verdict"]["sdt_external_body_no_unexplained_loss"] == "PASS"
            and findings["verdict"]["mismatch_count"] == 0
        )
        else "FAIL"
    )

    out = json.dumps(findings, ensure_ascii=False, indent=2, sort_keys=False)
    if args.write:
        (ev / "independent_recompute.json").write_text(out + "\n", encoding="utf-8")
        print(f"written: {(ev / 'independent_recompute.json')}")

    v = findings["verdict"]
    print("=== Task 6 独立重算汇总 ===")
    print(f"artifacts recomputed : {len(arts)}")
    print(f"mismatch vs probe    : {v['mismatch_count']}")
    for m in findings["mismatches"]:
        print(f"  ! {m}")
    print(f"field/block SDT      : {v['field_and_block_sdt_carrier']}")
    print(f"row-level SDT        : {v['row_level_sdt_carrier']}")
    print(f"row_uuid via cell tag: {v['row_uuid_identity_via_cell_field_tags']}")
    print(f"SDT 外正文无非预期丢失: {v['sdt_external_body_no_unexplained_loss']}")
    print(f"Property 33          : {v['property_33']}")
    for doc, d in by_doc.items():
        print(f"  [{doc}] {json.dumps(d, ensure_ascii=False)}")
    for doc, t in findings["template_identity"].items():
        print(
            f"  [{doc}] 权威模板 live=={t['live_matches_report']} before副本=={t['before_copy_matches_report']}"
        )
    return 0 if v["mismatch_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
