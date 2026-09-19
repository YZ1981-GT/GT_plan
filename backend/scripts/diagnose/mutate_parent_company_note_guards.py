"""Task 17：母公司附注章节守卫的变异检验（改一处必红 + 必须还原）。

判据不是退出码而是**失败测试名集合的差集**（memory 铁律：基线可能本就有红，
按 rc 判会得出「全 GREEN = 守卫缺陷」的假结论）。三态：

- ``RED``          新增失败非空 ⇒ 守卫有效
- ``GREEN``        新增失败为空 ⇒ **守卫缺陷**（该变异静默逃逸）
- ``ANCHOR-MISS``  变异没施加上（锚点未命中 / 命中多处）⇒ **脚本缺陷**，
                   此时「测试仍绿」不能作为任何结论

还原：每个变异单独 ``try/finally`` 按**字节**写回 + 事后哈希核验；
中断也不会留变异残留（memory 已记「变异脚本被 Ctrl+C 中断留下残留」的实测事故）。

用法::

    python backend/scripts/diagnose/mutate_parent_company_note_guards.py
    python backend/scripts/diagnose/mutate_parent_company_note_guards.py --only soe_chapter_title
    python backend/scripts/diagnose/mutate_parent_company_note_guards.py --out report.txt

退出码：``0`` 全部 RED（守卫有效）/ ``1`` 存在 GREEN 或 ANCHOR-MISS。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent

LISTED = BACKEND / "data" / "note_template_listed.json"
SOE = BACKEND / "data" / "note_template_soe.json"
SCOPE = BACKEND / "app" / "services" / "parent_company_scope.py"
EXPORTER = BACKEND / "app" / "services" / "report_excel_exporter.py"
ENGINE = BACKEND / "app" / "services" / "disclosure_engine.py"
SECTIONS = BACKEND / "app" / "services" / "parent_company_note_sections.py"
EDITOR = REPO / "audit-platform" / "frontend" / "src" / "views" / "DisclosureEditor.vue"

BE_STRUCT = "backend/tests/test_note_parent_company_chapter.py"
BE_SCOPE = "backend/tests/test_parent_company_scope.py"
BE_SOURCING = "backend/tests/test_parent_company_note_sourcing.py"
BE_REPORT = "backend/tests/test_report_parent_column_scope.py"
FE_SOURCE = "parentCompanyNoteSource"


class AnchorMiss(RuntimeError):
    """变异锚点未命中或命中多处 —— 脚本缺陷，不是守卫缺陷。"""


# ─────────────────────────── 变异实现（纯字节/JSON 级） ───────────────────────────


def _sub_once(text: str, old: str, new: str) -> str:
    n = text.count(old)
    if n != 1:
        raise AnchorMiss(f"锚点命中 {n} 处（应为 1）：{old!r}")
    return text.replace(old, new)


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _dump(p: Path, doc: dict) -> None:
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _parent_children(doc: dict, chapter: str) -> list[dict]:
    return [
        s
        for s in doc.get("sections") or []
        if str(s.get("section_number") or "").startswith(chapter + "、")
        and int(s.get("level") or 0) == 2
    ]


def m_drop_subsection(p: Path) -> None:
    """删掉 soe 母公司章的一个子节（Property 1）。"""
    doc = _load(p)
    kids = _parent_children(doc, "十二")
    if not kids:
        raise AnchorMiss("soe 母公司章无 level=2 子节")
    victim = kids[0]
    doc["sections"] = [s for s in doc["sections"] if s is not victim]
    _dump(p, doc)


def m_soe_chapter_title(p: Path) -> None:
    """soe 第十二章标题改回「股份支付」（Property 5）。"""
    doc = _load(p)
    hit = 0
    for s in doc.get("sections") or []:
        if str(s.get("section_number") or "").strip() == "十二" or str(
            s.get("section_number") or ""
        ).startswith("十二"):
            if int(s.get("level") or 0) == 1:
                s["section_title"] = "股份支付"
                hit += 1
    if hit != 1:
        raise AnchorMiss(f"soe 第十二章标题行命中 {hit} 处（应为 1）")
    _dump(p, doc)


def m_align_subsection_sets(p: Path) -> None:
    """把 soe 独有的「现金流量表补充资料」改名成 listed 独有的「应收票据」
    ⇒ 两版子节集合被强行对齐（Property 3）。"""
    doc = _load(p)
    hit = 0
    for s in _parent_children(doc, "十二"):
        if "现金流量表补充资" in str(s.get("section_title") or "") or (
            "现金流量表补充资" in str(s.get("section_number") or "")
        ):
            s["section_title"] = "应收票据"
            s["section_number"] = "十二、应收票据"
            hit += 1
    if hit != 1:
        raise AnchorMiss(f"soe 现金流量表补充资料子节命中 {hit} 处（应为 1）")
    _dump(p, doc)


def m_equity_columns_wrong(p: Path) -> None:
    """长期股权投资表列数改错（Property 9）。"""
    doc = _load(p)
    hit = 0
    for s in _parent_children(doc, "十六"):
        if str(s.get("section_title") or "") != "长期股权投资":
            continue
        for tbl in s.get("tables") or []:
            cols = tbl.get("columns") or []
            if len(cols) > 2:
                tbl["columns"] = cols[:2]
                hit += 1
                break
        break
    if hit != 1:
        raise AnchorMiss(f"listed 长期股权投资表命中 {hit} 处（应为 1）")
    _dump(p, doc)


def m_investment_income_from_consolidated(p: Path) -> None:
    """母公司章投资收益套用合并章结构（多塞一张表，Property 11）。"""
    doc = _load(p)
    hit = 0
    for s in _parent_children(doc, "十六"):
        if not str(s.get("section_title") or "").startswith("投资收益"):
            continue
        tables = s.get("tables") or []
        if not tables:
            raise AnchorMiss("listed 投资收益子节无表")
        clone = json.loads(json.dumps(tables[0]))
        clone["name"] = str(clone.get("name") or "") + "（合并章结构）"
        s["tables"] = tables + [clone]
        hit += 1
        break
    if hit != 1:
        raise AnchorMiss(f"listed 投资收益子节命中 {hit} 处（应为 1）")
    _dump(p, doc)


def m_duplicate_table_name(p: Path) -> None:
    """把某子节内两张表改成同名（Property 14）。"""
    doc = _load(p)
    for s in _parent_children(doc, "十六"):
        tables = s.get("tables") or []
        if len(tables) >= 2:
            tables[1]["name"] = tables[0].get("name")
            _dump(p, doc)
            return
    raise AnchorMiss("listed 母公司章无「至少 2 张表」的子节")


def m_helper_drop_report_scope(p: Path) -> None:
    """helper 去掉 `report_scope` 条件（Property 16）。"""
    src = p.read_text(encoding="utf-8")
    old = '            Project.report_scope == "standalone",\n'
    src = _sub_once(src, old, "")
    p.write_text(src, encoding="utf-8")


def m_helper_drop_audit_year(p: Path) -> None:
    """helper 去掉 `audit_year` 条件（Property 16）。"""
    src = p.read_text(encoding="utf-8")
    old = "            Project.audit_year == consol_project.audit_year,\n"
    src = _sub_once(src, old, "")
    p.write_text(src, encoding="utf-8")


def m_exporter_back_to_parent_company_code(p: Path) -> None:
    """报表侧改回按 `parent_company_code` 定位（Property 25）。"""
    src = p.read_text(encoding="utf-8")
    old = "            parent_project = await resolve_parent_standalone_project(self.db, project)\n"
    new = (
        "            import sqlalchemy as _sa\n"
        "            _r = await self.db.execute(\n"
        "                _sa.select(Project).where(\n"
        "                    Project.company_code == project.parent_company_code,\n"
        "                    Project.is_deleted == _sa.false(),\n"
        "                )\n"
        "            )\n"
        "            parent_project = _r.scalars().first()\n"
    )
    src = _sub_once(src, old, new)
    p.write_text(src, encoding="utf-8")


def m_attach_meta_returns_none(p: Path) -> None:
    """`_attach_parent_source_meta` 改回返回 None（本轮实测的 P0 形态之一）。"""
    src = p.read_text(encoding="utf-8")
    old = """        if ctx.get(PARENT_PROJECT_MISSING_KEY):
            table_data[PARENT_PROJECT_MISSING_KEY] = True
        return table_data"""
    new = """        if ctx.get(PARENT_PROJECT_MISSING_KEY):
            table_data[PARENT_PROJECT_MISSING_KEY] = True
        return None"""
    src = _sub_once(src, old, new)
    p.write_text(src, encoding="utf-8")


def m_attach_meta_rejects_none_ctx(p: Path) -> None:
    """`_attach_parent_source_meta` 改回不容忍 ctx=None（P0 形态之二）。"""
    src = p.read_text(encoding="utf-8")
    old = "        if not isinstance(table_data, dict) or not ctx:\n"
    new = "        if not isinstance(table_data, dict):\n"
    src = _sub_once(src, old, new)
    p.write_text(src, encoding="utf-8")


def m_drop_resolution_failed_branch(p: Path) -> None:
    """删掉 `resolution_failed` 留空分支（DB 抖动时会静默显示合并数）。"""
    src = p.read_text(encoding="utf-8")
    old = "        if scope.resolution_failed:\n"
    new = "        if False and scope.resolution_failed:\n"
    src = _sub_once(src, old, new)
    p.write_text(src, encoding="utf-8")


def m_inject_code_level_alias_consumer(p: Path) -> None:
    """在 ``backend/app`` 下注入一个**真实 code-level** 表级 ``legacy_aliases`` 读取。

    对应 2026-08-07 把消费方扫描由裸文本改成 code-level 之后的判据：
    docstring 里提到该字段名不算消费方，真读它才算。
    """
    src = p.read_text(encoding="utf-8")
    old = "from __future__ import annotations\n"
    new = (
        "from __future__ import annotations\n\n"
        "def _mutation_probe_alias(tbl: dict) -> list:\n"
        '    return list(tbl.get("legacy_aliases") or [])\n'
    )
    src = _sub_once(src, old, new)
    p.write_text(src, encoding="utf-8")


def m_fabricate_removed_lineage(p: Path) -> None:
    """往 soe/其他应收款 的 ``_removed_table_keys`` 里补一个**不存在的**中间名。

    该中间名在工作树与 HEAD 均 0 命中（2026-08-07 实测）⇒ 出现即「凭空编造血缘」，
    条数断言与「中间名不得复现」断言都应打红。
    """
    doc = _load(p)
    for s in _parent_children(doc, "十二"):
        if s.get("section_title") != "其他应收款":
            continue
        keys = list(s.get("_removed_table_keys") or [])
        keys.append("其他应收款（表8）")
        s["_removed_table_keys"] = keys
        _dump(p, doc)
        return
    raise AnchorMiss("soe 母公司章下未找到「其他应收款」子节")


def m_drop_frontend_banner(p: Path) -> None:
    """删掉前端溯源横幅的渲染（Task 13 的 dead output 形态）。"""
    src = p.read_text(encoding="utf-8")
    old = 'class="gt-de-parent-source"'
    new = 'class="gt-de-parent-source-REMOVED"'
    src = _sub_once(src, old, new)
    p.write_text(src, encoding="utf-8")


@dataclass(frozen=True)
class Mutation:
    key: str
    title: str
    target: Path
    apply: Callable[[Path], None]
    kind: str  # "backend" | "frontend"
    tests: tuple[str, ...]


MUTATIONS: tuple[Mutation, ...] = (
    Mutation("drop_subsection", "删掉 soe 母公司章一个子节", SOE, m_drop_subsection,
             "backend", (BE_STRUCT,)),
    Mutation("soe_chapter_title", "soe 第十二章标题改回「股份支付」", SOE,
             m_soe_chapter_title, "backend", (BE_STRUCT,)),
    Mutation("align_subsection_sets", "两版子节集合被强行对齐", SOE,
             m_align_subsection_sets, "backend", (BE_STRUCT,)),
    Mutation("equity_columns_wrong", "长期股权投资表列数改错", LISTED,
             m_equity_columns_wrong, "backend", (BE_STRUCT,)),
    Mutation("investment_income_consolidated", "投资收益套用合并章结构", LISTED,
             m_investment_income_from_consolidated, "backend", (BE_STRUCT,)),
    Mutation("duplicate_table_name", "母公司章表名改成重名", LISTED,
             m_duplicate_table_name, "backend", (BE_STRUCT,)),
    Mutation("helper_drop_report_scope", "helper 去掉 report_scope 条件", SCOPE,
             m_helper_drop_report_scope, "backend", (BE_SCOPE, BE_REPORT)),
    Mutation("helper_drop_audit_year", "helper 去掉 audit_year 条件", SCOPE,
             m_helper_drop_audit_year, "backend", (BE_SCOPE, BE_REPORT)),
    Mutation("exporter_parent_company_code", "报表侧改回按 parent_company_code 定位",
             EXPORTER, m_exporter_back_to_parent_company_code, "backend", (BE_REPORT,)),
    Mutation("attach_meta_returns_none", "_attach_parent_source_meta 改回返回 None",
             ENGINE, m_attach_meta_returns_none, "backend", (BE_SOURCING,)),
    Mutation("attach_meta_rejects_none_ctx",
             "_attach_parent_source_meta 改回不容忍 ctx=None",
             ENGINE, m_attach_meta_rejects_none_ctx, "backend", (BE_SOURCING,)),
    Mutation("drop_resolution_failed", "删掉 resolution_failed 留空分支", ENGINE,
             m_drop_resolution_failed_branch, "backend", (BE_SOURCING,)),
    Mutation("inject_alias_consumer", "注入真实 code-level 表级 legacy_aliases 消费方",
             SECTIONS, m_inject_code_level_alias_consumer, "backend", (BE_STRUCT,)),
    Mutation("fabricate_removed_lineage", "往 removed_table_keys 补不存在的中间名",
             SOE, m_fabricate_removed_lineage, "backend", (BE_STRUCT,)),
    Mutation("drop_frontend_banner", "删掉前端溯源横幅渲染", EDITOR,
             m_drop_frontend_banner, "frontend", (FE_SOURCE,)),
)


# ─────────────────────────── 跑测试 + 差集判定 ───────────────────────────


def _run_backend(tests: tuple[str, ...]) -> set[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *tests, "-q", "--tb=no", "-p", "no:randomly"],
        cwd=REPO, capture_output=True,
    )
    txt = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
    return set(re.findall(r"^(?:FAILED|ERROR) (\S+)", txt, re.M))


def _run_frontend(pattern: str) -> set[str]:
    proc = subprocess.run(
        ["npx", "vitest", "run", pattern, "--reporter=json"],
        cwd=REPO / "audit-platform" / "frontend", capture_output=True, shell=True,
    )
    txt = proc.stdout.decode("utf-8", "replace")
    i, j = txt.find("{"), txt.rfind("}")
    fails: set[str] = set()
    if i != -1 and j > i:
        try:
            data = json.loads(txt[i : j + 1])
            for f in data.get("testResults") or []:
                for a in f.get("assertionResults") or []:
                    if a.get("status") == "failed":
                        fails.add(f"{f.get('name')}::{a.get('fullName')}")
        except Exception:
            fails.add("<vitest-json-parse-failed>")
    if not fails and proc.returncode != 0:
        fails.add("<vitest-nonzero-exit>")
    return fails


def _run(mut: Mutation) -> set[str]:
    if mut.kind == "frontend":
        return _run_frontend(mut.tests[0])
    return _run_backend(mut.tests)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="只跑指定 key")
    ap.add_argument("--out", help="报告落盘路径")
    args = ap.parse_args()

    muts = [m for m in MUTATIONS if not args.only or m.key == args.only]
    if not muts:
        print(f"没有匹配的变异 key：{args.only}")
        return 2

    lines: list[str] = ["母公司附注章节守卫 —— 变异检验", ""]
    baselines: dict[tuple[str, ...], set[str]] = {}
    bad = 0

    for mut in muts:
        key = mut.tests
        if key not in baselines:
            baselines[key] = _run(mut)
            lines.append(f"[baseline] {'/'.join(key)} 失败 {len(baselines[key])} 项")
        base = baselines[key]

        orig = mut.target.read_bytes()
        h0 = hashlib.sha256(orig).hexdigest()
        bak = mut.target.with_suffix(mut.target.suffix + ".mutbak")
        bak.write_bytes(orig)
        status = "?"
        detail = ""
        try:
            try:
                mut.apply(mut.target)
            except AnchorMiss as err:
                status, detail = "ANCHOR-MISS", str(err)
            else:
                after = _run(mut)
                new = after - base
                if new:
                    status = "RED"
                    detail = f"新增失败 {len(new)} 项，例：{sorted(new)[:3]}"
                else:
                    status = "GREEN"
                    detail = "守卫缺陷：该变异未被任何断言抓到"
        finally:
            mut.target.write_bytes(orig)
            assert hashlib.sha256(mut.target.read_bytes()).hexdigest() == h0, (
                f"还原失败！{mut.target}"
            )
            bak.unlink(missing_ok=True)

        if status != "RED":
            bad += 1
        lines.append(f"[{status:<12}] {mut.key} — {mut.title}")
        if detail:
            lines.append(f"{'':<15}{detail}")

    lines.append("")
    lines.append(
        f"结论：{len(muts) - bad}/{len(muts)} 个变异被守卫抓到"
        + ("（全部有效）" if bad == 0 else f"；{bad} 个需处理")
    )

    text = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"报告已写入 {args.out}")
    else:
        for ln in lines:
            try:
                print(ln)
            except UnicodeEncodeError:
                print(ln.encode("utf-8", "replace").decode("ascii", "replace"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
