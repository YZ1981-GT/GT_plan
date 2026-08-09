"""生成附注模板表名正名真源 ``backend/data/note_table_name_corrections.json``（只读，不改模板）。

spec: note-template-columns-and-legacy-snapshot-closure（Task 4）

为什么需要正名
--------------
``sub_table_data`` **以表名为键** —— 空名与章节内重名会让两张表互相覆盖**丢整表**；
表头首格泄漏名（`项  目` / `子公司名称` …）既不可读，也让迁移器的 `_name_is_meaningful`
判 False 从而拒绝 `by_name` 自动迁移。

正名真源优先级（顺序即优先级，每条落 `basis` 可追溯）
------------------------------------------------------
1. ``section_title``  —— 单表章节，表名就是章节名（最自然且必然唯一）
2. ``source_docx``    —— 多表章节且源 docx 表数与 JSON 相同、且该表在 docx 里有
   **合格业务标题**（见 `_is_business_title`）
3. ``fallback_index`` —— 其余：``{section_title}（表N）``。序号兜底是**中性**的，
   不自造披露语义（比编造一个像业务名的标题安全）

🔴 三条硬约束
--------------
* **不改 `rows` / `headers` / `columns`**（行集修订归各 per-cycle spec 与 A spec）。
* **母公司章排除**（归 A spec），判定走 `parent_company_note_sections` 真源，
  **不是** `section_id` 前缀 —— listed 的 `chapter-12-*` 是「十二、股份支付」。
* **`registry_covered` 章节排除**（有 `*NoteSectionMap.ts` 消费，改名会立刻产生孤儿
  子表；归各 per-cycle spec），但仍在报告里登记。

用法
----
    python backend/scripts/diagnose/build_note_table_name_corrections.py
    python backend/scripts/diagnose/build_note_table_name_corrections.py --out <path>
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
BACKEND_ROOT = _HERE.parents[2]
REPO_ROOT = _HERE.parents[3]
DATA_DIR = BACKEND_ROOT / "data"
DEFAULT_OUT = DATA_DIR / "note_table_name_corrections.json"
HEADERS_FACTS = DATA_DIR / "note_table_headers_source_facts.json"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

VARIANTS = ("listed", "soe")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, path
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


PROBE = _load(
    BACKEND_ROOT / "scripts" / "diagnose" / "diagnose_note_columns_coverage.py",
    "note_columns_probe_for_names",
)

# ---------------------------------------------------------------------------
# 标题合格性判据
# ---------------------------------------------------------------------------

_GUIDANCE_MARKERS = (
    "15号文",
    "号文第",
    "应披露",
    "应说明",
    "参考披露格式",
    "不适用的",
    "可删除",
    "请删除",
    "确定方法及依据",
    # 「…如下」「…列示如下」是**引导句**不是表标题（首版放过了 5 条，逐条实证后补）
    "如下",
    "列示",
    "等信息",
)
# 以这些收尾的是句子而非标题
_SENTENCE_TAIL = ("；", ";", "。", "，", ",", "、")
# 以这些开头的是示例/占位说明
_BAD_HEAD = ("[", "【", "（注", "(注")
_YEAR_ONLY_RE = re.compile(r"^2[0X][0-9X]{2}\s*年?$")
_HTML_RE = re.compile(r"<[^>]+>")


def is_business_title(text: str) -> bool:
    """docx 抽出的标题是否可当业务表名。

    排除四类：空/过长/过短、指引文字（15 号文条款、「应披露…」）、
    整句（含句号）、纯年份（套期章节里 16 张表大量重复 `2025年`/`2024年`）。
    """
    t = (text or "").strip().strip("：:")
    if not (2 <= len(t) <= 40):
        return False
    if any(m in t for m in _GUIDANCE_MARKERS):
        return False
    if t.endswith(_SENTENCE_TAIL):
        return False
    if t.startswith(_BAD_HEAD):
        return False
    if "。" in t or (t.startswith("（") and t.endswith("）")):
        return False
    if _YEAR_ONLY_RE.match(t):
        return False
    if _HTML_RE.search(t):
        return False
    return True


def _norm_key(s: str) -> str:
    s = re.sub(r"\s+", "", s or "")
    s = re.sub(r"[（(][^）)]*[)）]", "", s)
    return s.replace("【", "").replace("】", "").strip("：:、。")


def _clean_name(s: str) -> str:
    """表名清洗：剥 HTML、折叠首尾空白，**保留中间空格**（源模板 `项  目` 是有意字面）。"""
    return _HTML_RE.sub("", str(s or "")).strip()


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def _docx_index(facts: dict[str, Any], variant: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for key, meta in (facts.get(variant, {}).get("sections") or {}).items():
        leaf = _norm_key(str(meta.get("heading_text") or ""))
        if leaf:
            out.setdefault(leaf, []).append(key)
    return out


def _resolve_docx_section(
    facts: dict[str, Any], variant: str, idx: dict[str, list[str]], section_title: str
) -> tuple[str | None, list[dict[str, Any]]]:
    title = _norm_key(section_title)
    keys = idx.get(title) or [
        k
        for leaf, ks in idx.items()
        if title and (title in leaf or leaf in title)
        for k in ks
    ]
    if not keys:
        return None, []
    key = keys[0]
    return key, (facts[variant]["sections"][key].get("tables") or [])


def build(scanned: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "_source": (
            "生成自 backend/scripts/diagnose/build_note_table_name_corrections.py；"
            "判据 = 模板 JSON 现状 + docs/模版 源 docx（note_table_headers_source_facts.json）"
        ),
        "_key": (
            "corrections 以 section_id 为键 —— 🔴 section_number **不唯一**"
            "（listed 有两个 `三、研发支出`，section_id 以 `-2` 后缀区分），"
            "按 section_number 索引会让 _note_structure_kit.find_section 只命中第一个"
        ),
        "corrections": {v: {} for v in VARIANTS},
        "excluded": {v: {} for v in VARIANTS},
        "summary": {},
    }
    stats: Counter = Counter()

    for variant in VARIANTS:
        idx = _docx_index(facts, variant)
        for sec in scanned[variant]["sections"]:
            tables = sec["tables"]
            if not tables:
                continue
            names = [t["name"] for t in tables]
            dup = {n for n, c in Counter(names).items() if c > 1}
            offenders = [
                t
                for t in tables
                if t["is_empty_name"]
                or t["is_leak_name"]
                or t["name"] in dup
                or _HTML_RE.search(t["name"])
            ]
            if not offenders:
                continue
            num = sec["section_id"] or sec["section_number"]
            if sec["scope"] != PROBE.SCOPE_UNREGISTERED:
                result["excluded"][variant][num] = {
                    "section_number": sec["section_number"],
                    "section_title": sec["section_title"],
                    "scope": sec["scope"],
                    "offender_indices": [t["index"] for t in offenders],
                    "reason": (
                        "母公司章归 A spec"
                        if sec["scope"] == PROBE.SCOPE_PARENT
                        else "该章节已被 *NoteSectionMap.ts 消费，改名会产生孤儿子表 → 归对应 per-cycle spec"
                    ),
                }
                stats[f"{variant}_excluded_tables"] += len(offenders)
                continue

            docx_key, docx_tables = _resolve_docx_section(
                facts, variant, idx, sec["section_title"]
            )
            count_match = bool(docx_key) and len(docx_tables) == len(tables)

            # 该章节 docx 标题若有重复，整章退回序号兜底（套期 16 张表大量 `2025年`）
            docx_titles = (
                [str(t.get("title_candidate") or "") for t in docx_tables]
                if count_match
                else []
            )
            usable = [t if is_business_title(t) else "" for t in docx_titles]
            dup_docx = {t for t, c in Counter([u for u in usable if u]).items() if c > 1}

            plan: list[dict[str, Any]] = []
            offender_idx = {t["index"] for t in offenders}
            taken = {
                _clean_name(t["name"])
                for t in tables
                if t["index"] not in offender_idx and _clean_name(t["name"])
            }
            # 🔴 候选新名不得撞**同章其它表的旧名** —— 旧名会被写进那些表的
            # `legacy_aliases`，若与本表新名相同，一个旧名同时命中「按名」与「按 alias」
            # 两张表 ⇒ 迁移时写错落点（Property 8）。实证一例：`三、套期` 的
            # docx 标题 `公允价值套期` 正是同章 #6/#7 的表头泄漏旧名。
            reserved_aliases = {
                _clean_name(t["name"]) for t in tables if _clean_name(t["name"])
            }
            for t in offenders:
                cur = t["name"]
                cand = ""
                basis = ""
                if len(tables) == 1:
                    cand = sec["section_title"]
                    basis = "section_title（单表章节）"
                elif count_match and usable[t["index"]] and usable[t["index"]] not in dup_docx:
                    cand = usable[t["index"]]
                    basis = f"source_docx:{docx_key}#{t['index']}"
                if not cand:
                    cand = f"{sec['section_title']}（表{t['index'] + 1}）"
                    why = (
                        "docx 未映射"
                        if not docx_key
                        else "docx 表数不等"
                        if not count_match
                        else "docx 标题重复"
                        if usable[t["index"]] in dup_docx
                        else "docx 标题不合格（指引文字/纯年份/整句）"
                    )
                    basis = f"fallback_index（{why}）"
                cand = _clean_name(cand)
                others_old = reserved_aliases - {_clean_name(cur)}
                if cand in others_old:
                    cand = f"{sec['section_title']}（表{t['index'] + 1}）"
                    basis = "fallback_index（候选名与同章其它表旧名冲突，避免 alias 歧义）"
                # 唯一化
                final = cand
                bump = t["index"] + 1
                while final in taken or final in others_old:
                    final = f"{cand}（表{bump}）"
                    bump += 1
                taken.add(final)
                plan.append(
                    {
                        "index": t["index"],
                        "current_name": cur,
                        "correct_name": final,
                        "basis": basis,
                        "flags": [
                            f
                            for f, on in (
                                ("empty", t["is_empty_name"]),
                                ("leak", t["is_leak_name"]),
                                ("dup", cur in dup),
                                ("html", bool(_HTML_RE.search(cur))),
                            )
                            if on
                        ],
                        "header_count": t["header_count"],
                    }
                )
                stats[f"{variant}_planned"] += 1
                stats[f"{variant}_basis_" + basis.split("（")[0].split(":")[0]] += 1

            result["corrections"][variant][num] = {
                "section_number": sec["section_number"],
                "section_title": sec["section_title"],
                "section_id": sec["section_id"],
                "table_count": len(tables),
                "docx_key": docx_key,
                "docx_table_count": len(docx_tables),
                "tables": plan,
            }
            stats[f"{variant}_sections"] += 1

    result["summary"] = dict(sorted(stats.items()))
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__ or "")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    if not HEADERS_FACTS.exists():
        print(
            f"[ERR] 缺少列头事实文件 {HEADERS_FACTS}；"
            "先跑 backend/scripts/diagnose/extract_note_table_headers.py"
        )
        return 2

    scanned = PROBE.scan_templates()
    facts = json.loads(HEADERS_FACTS.read_text(encoding="utf-8"))
    payload = build(scanned, facts)

    for k, v in payload["summary"].items():
        print(f"[OK] {k}={v}")
    out = Path(args.out) if args.out else DEFAULT_OUT
    if not out.is_absolute():
        out = REPO_ROOT / out
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[OK] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
