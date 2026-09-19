"""重算 note_template_variant_matrix.json 的 variants 快照（只读）.

Spec: .kiro/specs/parent-company-note-chapter-and-sourcing/ Task 10
配套守卫: backend/tests/test_variant_matrix.py::test_variants_snapshot_unchanged

用途
----
该矩阵被 D/G/H/K/L/N 多个 spec 共享，是回退高发文件。守卫用「102 科目 variants
的 sha256 快照」当回退探测器。**该断言打红不等于回归** —— 若那批取值被有意裁决
改写（如并发 spec ``soe-listed-note-conversion-correctness`` 的 35 条 null 三态），
用本脚本重算常量，然后把新值填回守卫，并在提交说明里写清改了哪些科目。

输出**不使用 emoji**（Windows GBK 控制台会 UnicodeEncodeError）。

Usage:
    python backend/scripts/diagnose/audit_variant_matrix_snapshot.py
    python backend/scripts/diagnose/audit_variant_matrix_snapshot.py --diff-head
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
REL = "backend/data/note_template_variant_matrix.json"
MATRIX_PATH = REPO_ROOT / REL
VARIANT_KEYS = (
    "soe_standalone",
    "soe_consolidated",
    "listed_standalone",
    "listed_consolidated",
)
PARENT_FIELD = "parent_company_sections"


def variants_payload(doc: dict[str, Any]) -> str:
    return json.dumps(
        [[a["account_key"], a["variants"]] for a in doc["accounts"]],
        ensure_ascii=False,
        sort_keys=True,
    )


def digest_of(doc: dict[str, Any]) -> str:
    return hashlib.sha256(variants_payload(doc).encode("utf-8")).hexdigest()


def load_head() -> dict[str, Any] | None:
    try:
        raw = subprocess.run(
            ["git", "show", f"HEAD:{REL}"], cwd=REPO_ROOT, capture_output=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"[WARN] cannot read HEAD version: {exc}")
        return None
    return json.loads(raw.decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diff-head", action="store_true", help="与 HEAD 版逐科目比对 variants")
    args = ap.parse_args()

    doc = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    print(f"[INFO] accounts={len(doc['accounts'])}")
    print(f"VARIANTS_SNAPSHOT_SHA256 = {digest_of(doc)!r}")
    for vk in VARIANT_KEYS:
        n = sum(1 for a in doc["accounts"] if a["variants"].get(vk))
        print(f"  non-null {vk}: {n}")
    carried = [a["account_key"] for a in doc["accounts"] if PARENT_FIELD in a]
    print(f"  accounts carrying {PARENT_FIELD}: {len(carried)} -> {sorted(carried)}")

    if not args.diff_head:
        return 0

    head = load_head()
    if head is None:
        return 1
    print(f"[INFO] HEAD digest = {digest_of(head)}")
    hmap = {a["account_key"]: a["variants"] for a in head["accounts"]}
    cmap = {a["account_key"]: a["variants"] for a in doc["accounts"]}
    only_head = sorted(set(hmap) - set(cmap))
    only_cur = sorted(set(cmap) - set(hmap))
    if only_head or only_cur:
        print(f"[DIFF] account set changed: only-HEAD={only_head} only-CUR={only_cur}")
    diffs = [k for k in hmap if k in cmap and hmap[k] != cmap[k]]
    print(f"[INFO] variants differing accounts: {len(diffs)}")
    for k in diffs:
        print(f"  {k}: HEAD={json.dumps(hmap[k], ensure_ascii=False)}")
        print(f"  {' ' * len(k)}  CUR ={json.dumps(cmap[k], ensure_ascii=False)}")
    return 0 if not diffs and not only_head and not only_cur else 1


if __name__ == "__main__":
    raise SystemExit(main())
