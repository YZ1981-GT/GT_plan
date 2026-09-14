"""生成附注模板列元数据规则表 ``backend/data/note_columns_rules.json``（只读，不改模板）。

spec: note-template-columns-and-legacy-snapshot-closure（Task 8）

判据真源
--------
``backend/data/note_table_headers_source_facts.json``（由 Task 7 的
``extract_note_table_headers.py`` 从 ``docs/模版/`` 两份源 docx 抽出）。

🔴 只为「源真源确实给出表头且与 JSON 列数一致」的表生成规则
------------------------------------------------------------
R2.4 明确禁止「找不到对应表头就回退按 JSON ``headers`` 补」——JSON ``headers`` 本身
可能是 md 重建压扁的产物。故本脚本把 234 张作业面切成两块：

* **规则**（可直接补）= 源 docx 有该章节、表数一致、该表末级表头非空且**列数与 JSON
  ``headers`` 相等**、且为**单级表头** ⇒ 逐列 ``flat: true``；
* **欠账**（不生成规则，逐条登记原因）= `NO_SECTION` / `COUNT_MISMATCH` /
  `NO_HEADER` / `LEN_MISMATCH`（后者多为两级表头被 md 重建压扁，属行/列集修订，
  归 R2.7 登记 + 各 per-cycle spec）。

列字段口径
----------
* ``key`` **一律取模板 ``headers`` 原文** —— 快照与同步载荷都用这些中文键，改 key
  会让整表数据丢落点（平台既有铁律）。
* ``label`` 取源 docx 末级表头；但**若与 JSON headers 归一后相等则沿用 JSON 原文**，
  以保留 ``项  目`` / ``合 计`` 这类源模板有意的内部空格字面（R2.6）。
* 每条带 ``source_ref``（``docx:<heading 路径>#<表序>row0``）与 ``headers_equal``。
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
HEADERS_FACTS = DATA_DIR / "note_table_headers_source_facts.json"
DEFAULT_OUT = DATA_DIR / "note_columns_rules.json"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

VARIANTS = ("listed", "soe")
_HTML_RE = re.compile(r"<[^>]+>")

# ---------------------------------------------------------------------------
# 🔴 章归属闸门（2026-08-07 新增，见下方长注释）
# ---------------------------------------------------------------------------
#
# 原实现只按「末级 heading 归一后相等/互含」匹配 docx 章节，**不校验章归属**。
# 实测已生成的 85 条规则里 listed 23 章 + soe 2 章是跨章匹配。逐条核对后没有实质
# 错配，但缺口是真的 —— 挡住错配的唯一安全阀是「docx 列数恰好等于 JSON headers 数」：
#
#   JSON  三、长期股权投资（会计政策章）  headers = ['项  目','期末余额','上年年末余额']
#   docx  合并财务报表项目附注/长期股权投资  13 列两级变动表
#
# 这一对被 LEN_MISMATCH 挡住了；但**跨章同名且列数恰好相等**时会静默把别章的列头
# 写进来。故新增章归属闸门：跨章必须显式登记，否则记 deficit `CROSS_CHAPTER`。
#
# 两类合法跨章：
#   (a) CHAPTER_EQUIV —— JSON 章标题与 docx root 是同一章的两种写法；
#   (b) CROSS_CHAPTER_ALLOWLIST —— md 重建把 A 章内容重复/错落进 B 章，
#       docx 侧的归属才是正确的（memory 已记「md 重建把项目注释内容重复落进会计政策章」）。

CHAPTER_EQUIV: dict[str, list[tuple[str, str]]] = {
    "listed": [
        # JSON 第五章「合并财务报表项目注释」= docx root「合并财务报表项目附注」（注释/附注一字之差）
        ("合并财务报表项目注释", "合并财务报表项目附注"),
    ],
    "soe": [
        # JSON 第十一章「关联方及关联交易」= docx root「关联方关系及其交易」
        ("关联方及关联交易", "关联方关系及其交易"),
        # JSON 第五章「重要会计政策、会计估计的变更以及前期差错的更正」
        # = docx root「会计政策、会计估计变更及差错更正」（同章，用词长短不同）
        (
            "重要会计政策、会计估计的变更以及前期差错的更正",
            "会计政策、会计估计变更及差错更正",
        ),
    ],
}

# key = (variant, JSON 章标题归一, docx root 归一) -> 理由（必须写明依据，>=12 字）
CROSS_CHAPTER_ALLOWLIST: dict[tuple[str, str, str], str] = {
    # ---- listed：md 重建把多个章的内容重复落进「三、重要会计政策及会计估计」章 ----
    (
        "listed",
        "重要会计政策及会计估计",
        "合并财务报表项目附注",
    ): "md 重建把项目注释章内容重复落进会计政策章（memory 已记该现象），逐表核对列头语义正确",
    (
        "listed",
        "重要会计政策及会计估计",
        "在其他主体中的权益",
    ): "同上：企业合并/合营联营权益诸表被重复落进会计政策章，docx 侧归属正确",
    (
        "listed",
        "重要会计政策及会计估计",
        "政府补助",
    ): "同上：政府补助四表被重复落进会计政策章，docx 侧归属正确",
    (
        "listed",
        "重要会计政策及会计估计",
        "金融工具风险管理",
    ): "同上：风险管理/资本管理/套期诸表被重复落进会计政策章，docx 侧归属正确",
    (
        "listed",
        "重要会计政策及会计估计",
        "关联方及关联交易",
    ): "同上：母公司情况/合营联营企业情况被重复落进会计政策章，docx 侧归属正确",
    # ---- listed：JSON 把「其他重要事项」章的四节错落进「十四、资产负债表日后事项」 ----
    (
        "listed",
        "资产负债表日后事项",
        "其他重要事项",
    ): "前期差错更正/重要债务重组/终止经营/其他 在源 docx 属其他重要事项章，JSON 侧章归属是 md 重建错落",
    # ---- listed：关联方章内节，JSON 与 docx root 同名（因归一剥括注后仍需显式放行）----
    (
        "listed",
        "关联方及关联交易",
        "关联方及关联交易",
    ): "同章（归一后章标题与 docx root 相等），显式登记以便闸门统一走白名单",
    # ---- listed：研发支出同表被 md 重建重复落进三章（`三、研发支出`×2 + `六、1`）----
    (
        "listed",
        "重要会计政策及会计估计",
        "研发支出",
    ): (
        "实证 JSON 有三个同名 section（`三、研发支出`×2 + `六、1`）均 3 列，"
        "docx 唯一 `研发支出/研发支出` 是 5 列两级（费用化/资本化）"
        "⇒ docx 归属正确、列头语义一致，真缺陷是两级表头被压扁（应由 LEN_MISMATCH 如实报告）"
    ),
    # ---- soe：JSON 第五章标题较长，docx root 用简写 ----
    (
        "soe",
        "重要会计政策、会计估计的变更以及前期差错的更正",
        "会计政策、会计估计变更及差错更正",
    ): "同章异名：JSON 第五章全称 vs docx root 简写，逐字核对为同一章",
}


def _chapter_no(section_number: str) -> str:
    """从 `五、12` / `三、长期股权投资` 抽章号 `五` / `三`。"""
    return re.split(r"[、,.]", str(section_number or "").strip(), maxsplit=1)[0].strip()


def _docx_root(docx_key: str) -> str:
    """docx section key 形如 `合并财务报表项目附注 / 长期股权投资`，取 root heading。"""
    return norm_section(str(docx_key or "").split("/")[0])


def chapter_verdict(
    variant: str, json_chapter: str, docx_root: str
) -> tuple[bool, str]:
    """判定「JSON 章 ↔ docx root」是否允许跨章匹配。

    Returns:
        ``(ok, kind)``：``kind`` ∈ ``same`` / ``equiv`` / ``allowlisted`` / ``cross``
    """
    a, b = norm_section(json_chapter), norm_section(docx_root)
    if not a or not b:
        return True, "unknown"  # 章信息缺失时不拦（原行为），由列数闸门兜住
    if a == b:
        return True, "same"
    for x, y in CHAPTER_EQUIV.get(variant, []):
        if {a, b} == {norm_section(x), norm_section(y)}:
            return True, "equiv"
    if (variant, a, b) in CROSS_CHAPTER_ALLOWLIST:
        return True, "allowlisted"
    return False, "cross"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, path
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


PROBE = _load(
    BACKEND_ROOT / "scripts" / "diagnose" / "diagnose_note_columns_coverage.py",
    "note_columns_probe_for_rules",
)


def norm_section(s: str) -> str:
    s = re.sub(r"\s+", "", s or "")
    s = re.sub(r"[（(][^）)]*[)）]", "", s)
    return s.replace("【", "").replace("】", "").strip("：:、。")


def norm_label(s: str) -> str:
    """列名归一：剥 HTML + 去**全部**空白（源模板 `项  目` 与 docx `项 目` 只差空格）。"""
    return re.sub(r"\s+", "", _HTML_RE.sub("", str(s or "")))


def build(scanned: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "_source": (
            "生成自 backend/scripts/diagnose/build_note_columns_rules.py；"
            "列真源 = docs/模版 两份附注模板 docx（note_table_headers_source_facts.json）"
        ),
        "_key": "rules 以 section_id 为键（section_number 不唯一）",
        "rules": {v: {} for v in VARIANTS},
        "deficits": {v: [] for v in VARIANTS},
        "summary": {},
    }
    stat: Counter = Counter()

    for variant in VARIANTS:
        dsec = facts[variant]["sections"]
        by_leaf: dict[str, list[str]] = {}
        for key, meta in dsec.items():
            leaf = norm_section(str(meta.get("heading_text") or ""))
            if leaf:
                by_leaf.setdefault(leaf, []).append(key)

        raw = json.loads(
            (DATA_DIR / f"note_template_{variant}.json").read_text(encoding="utf-8")
        )
        raw_by_id = {
            str(s.get("section_id") or ""): s
            for s in (raw.get("sections") or [])
            if isinstance(s, dict)
        }
        # 章号 -> 章标题（`level == 1` 的顶层章），供章归属闸门用。
        # 🔴 键必须是 `_chapter_no()` 抽出的**章号**（`五`）而不是完整 `section_number`
        # （`五、合并财务报表项目注释`）—— 后者会让 `_chapter_no(sec[...])` 恒查不到、
        # `chapter_title` 恒空 ⇒ 闸门走 `unknown` 分支恒放行 = 死代码。
        chapters: dict[str, str] = {
            _chapter_no(str(s.get("section_number") or "")): str(
                s.get("section_title") or ""
            )
            for s in (raw.get("sections") or [])
            if isinstance(s, dict) and s.get("level") == 1
        }

        for sec in scanned[variant]["sections"]:
            if sec["scope"] != PROBE.SCOPE_UNREGISTERED:
                continue
            # 🔴 不能只取 `column_count == 0` 的表（本轮踩坑）
            # ------------------------------------------------------------------
            # 规则表同时承担两个角色：①补列脚本的判据 ②列真源的 provenance 记录
            # + 幂等 noop 判据。若只收 gap，则 `--apply` 之后重跑生成器会得到
            # **空规则表** —— 守卫 `test_rules_non_empty` 立刻打红，且「这 85 张
            # 的列是从哪来的」这一追溯信息永久丢失。
            #
            # 故改为收**全部**表：已有 columns 且与规则逐字段一致的照样进 rules
            # （补列脚本判 `noop` = 幂等）；已有 columns 但与规则不一致的进
            # deficits（原因 `EXISTING_DIFFERS`，fail-closed 不覆盖别人的成果）。
            gaps = list(sec["tables"])
            if not gaps:
                continue
            sid = sec["section_id"]
            rawsec = raw_by_id.get(sid) or {}
            raw_tables = rawsec.get("tables") or []

            title = norm_section(sec["section_title"])
            keys = by_leaf.get(title) or [
                k
                for leaf, ks in by_leaf.items()
                if title and (title in leaf or leaf in title)
                for k in ks
            ]
            # 🔴 章归属闸门：末级 heading 同名可能跨章（listed `三、长期股权投资` 在会计政策章，
            # 而 docx 同名表在项目注释章、是 13 列两级变动表）→ 按名匹配后必须校验章归属，
            # 跨章且未登记为等价/已知重复落章的一律拒绝（列数恰好相等时它是静默错配的唯一入口）
            chapter_title = chapters.get(_chapter_no(sec["section_number"]), "")
            rejected_cross: list[str] = []
            docx_key = None
            match_kind = ""
            for k in keys:
                ok, kind = chapter_verdict(variant, chapter_title, _docx_root(k))
                if ok:
                    docx_key, match_kind = k, kind
                    break
                rejected_cross.append(_docx_root(k))
            if docx_key is None and rejected_cross:
                stat[f"{variant}_cross_chapter_rejected"] += 1
            elif match_kind:
                stat[f"{variant}_chapter_{match_kind}"] += 1
            dtbls = dsec[docx_key]["tables"] if docx_key else []
            count_ok = bool(docx_key) and len(dtbls) == sec["table_count"]

            planned: list[dict[str, Any]] = []
            for t in gaps:
                idx = t["index"]
                json_headers = (
                    [str(h or "") for h in (raw_tables[idx].get("headers") or [])]
                    if idx < len(raw_tables)
                    else []
                )
                reason = ""
                if not docx_key and rejected_cross:
                    reason = (
                        "CROSS_CHAPTER（按末级 heading 命中 docx "
                        f"{'/'.join(sorted(set(rejected_cross)))} 但章归属不符且未登记为"
                        f"等价；JSON 章=「{chapter_title}」）"
                    )
                elif not docx_key:
                    reason = "NO_SECTION（源 docx 未映射到该章节）"
                elif not count_ok:
                    reason = f"COUNT_MISMATCH（docx {len(dtbls)} 表 vs JSON {sec['table_count']} 表）"
                else:
                    d = dtbls[idx]
                    level1 = [str(x or "") for x in d["level1"]]
                    if not level1:
                        reason = "NO_HEADER（源 docx 该表首行为空）"
                    elif len(level1) != len(json_headers):
                        reason = (
                            f"LEN_MISMATCH（docx {len(level1)} 列 vs JSON "
                            f"{len(json_headers)} 列；多为两级表头被 md 重建压扁）"
                        )
                    elif d["header_rows"] != 1:
                        reason = (
                            f"TWO_LEVEL（源 docx 两级表头，需 group 声明 + 可能拆主/续表）"
                        )
                if reason:
                    out["deficits"][variant].append(
                        {
                            "section_id": sid,
                            "section_number": sec["section_number"],
                            "section_title": sec["section_title"],
                            "index": idx,
                            "table_name": t["name"],
                            "json_header_count": len(json_headers),
                            "reason": reason,
                        }
                    )
                    stat[f"{variant}_deficit"] += 1
                    stat[f"{variant}_" + reason.split("（")[0]] += 1
                    continue

                d = dtbls[idx]
                level1 = [str(x or "") for x in d["level1"]]
                cols: list[dict[str, Any]] = []
                equal = True
                for i, jh in enumerate(json_headers):
                    src = level1[i]
                    if norm_label(src) == norm_label(jh):
                        label = jh  # 保留 JSON 原文的内部空格字面
                    else:
                        label = _HTML_RE.sub("", src).strip()
                        equal = False
                    col: dict[str, Any] = {"key": jh, "label": label, "flat": True}
                    if i == 0:
                        col["is_label"] = True
                    cols.append(col)
                # 🔴 fail-closed：已有 columns 但与规则不一致 → 不覆盖，进 deficits
                # （可能是某 per-cycle spec 或 A spec 的成果，本 spec 无权改；
                #  R10.7「发现别人的缺陷只登记不顺手修」）
                cur = raw_tables[idx].get("columns") if idx < len(raw_tables) else None
                if isinstance(cur, list) and cur and cur != cols:
                    out["deficits"][variant].append(
                        {
                            "section_id": sid,
                            "section_number": sec["section_number"],
                            "section_title": sec["section_title"],
                            "index": idx,
                            "table_name": t["name"],
                            "json_header_count": len(json_headers),
                            "reason": (
                                f"EXISTING_DIFFERS（已有 {len(cur)} 列与规则给的 "
                                f"{len(cols)} 列不一致；不覆盖，需人工裁决归属）"
                            ),
                        }
                    )
                    stat[f"{variant}_deficit"] += 1
                    stat[f"{variant}_EXISTING_DIFFERS"] += 1
                    continue

                planned.append(
                    {
                        "index": idx,
                        "table_name": t["name"],
                        "columns": cols,
                        "source_ref": f"docx:{docx_key}#{idx}row0",
                        "headers_equal": equal,
                    }
                )
                stat[f"{variant}_rule"] += 1
                if not equal:
                    stat[f"{variant}_rule_label_differs"] += 1

            if planned:
                out["rules"][variant][sid] = {
                    "section_number": sec["section_number"],
                    "section_title": sec["section_title"],
                    "docx_key": docx_key,
                    "tables": planned,
                }
                stat[f"{variant}_rule_sections"] += 1

    out["summary"] = dict(sorted(stat.items()))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__ or "")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    if not HEADERS_FACTS.exists():
        print(f"[ERR] 缺少 {HEADERS_FACTS}；先跑 extract_note_table_headers.py")
        return 2

    payload = build(PROBE.scan_templates(), json.loads(HEADERS_FACTS.read_text(encoding="utf-8")))
    for k, v in payload["summary"].items():
        print(f"[OK] {k}={v}")
    out = Path(args.out) if args.out else DEFAULT_OUT
    if not out.is_absolute():
        out = REPO_ROOT / out
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
