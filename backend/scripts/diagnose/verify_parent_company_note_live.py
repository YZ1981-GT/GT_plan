"""Task 18：母公司附注章节取数 —— 真实库验收（只读，默认 dry-run）。

覆盖「合并项目 + 母公司单体项目」这一对的端到端取数：口径定位 → 母公司章判定 →
resolver ctx 切换 → 溯源三项 → 缺失态留空不填零。

🔴 诚实报告红线（需求 10.6 / Property 30）
-----------------------------------------
真实库若**没有** ``report_scope='consolidated'`` 的项目，本脚本必须明确输出
「无法验收：本库无合并项目」并把该结论标成 ``UNVERIFIABLE``，**禁止**用 fixture
合成一对项目冒充通过。2026-08-05 实测该库 8 个项目全为 ``standalone``。

退出码
------
``0`` = 全部检查通过 **或** 诚实报告为不可验收（两者都不是失败）。
``1`` = 有检查项失败（真实库里存在合并项目却取数不对）。
``2`` = 脚本自身异常（连不上库等）。

用法::

    python backend/scripts/diagnose/verify_parent_company_note_live.py
    python backend/scripts/diagnose/verify_parent_company_note_live.py --out report.txt
    python backend/scripts/diagnose/verify_parent_company_note_live.py --strict

``--strict`` 把「不可验收」也视为失败（退出码 1），供将来建了合并项目后在 CI 里
强制要求真实验收；默认关闭，因为当前库无合并项目是**合法**状态。

本脚本**只读**：不写库、不改文件（除 ``--out`` 指定的报告文件）。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import sqlalchemy as sa  # noqa: E402

from app.core.database import async_session  # noqa: E402
from app.models.core import Project  # noqa: E402
from app.services.parent_company_note_sections import (  # noqa: E402
    PARENT_PROJECT_MISSING_KEY,
    PARENT_SOURCE_META_KEYS,
    is_parent_company_section,
    load_parent_company_sections,
    resolve_parent_scope_for_notes,
)
from app.services.parent_company_scope import (  # noqa: E402
    is_parent_company_project,
    resolve_consolidated_sibling,
    resolve_parent_standalone_project,
)

PASS = "PASS"
FAIL = "FAIL"
INFO = "INFO"
UNVERIFIABLE = "UNVERIFIABLE"


@dataclass
class Report:
    lines: list[str] = field(default_factory=list)
    failures: int = 0
    unverifiable: int = 0

    def add(self, status: str, title: str, detail: str = "") -> None:
        self.lines.append(f"[{status:<12}] {title}")
        if detail:
            for ln in detail.splitlines():
                self.lines.append(f"{'':<15}{ln}")
        if status == FAIL:
            self.failures += 1
        elif status == UNVERIFIABLE:
            self.unverifiable += 1

    def section(self, title: str) -> None:
        self.lines.append("")
        self.lines.append(f"=== {title} ===")


async def _project_inventory(db) -> tuple[list[Project], list[Project]]:
    result = await db.execute(
        sa.select(Project).where(Project.is_deleted == sa.false())
    )
    projects = list(result.scalars().all())
    consolidated = [p for p in projects if (p.report_scope or "") == "consolidated"]
    return projects, consolidated


async def _check_matrix_judgement(rep: Report) -> None:
    """判据侧：母公司章节号集合可加载、两版互斥（不连库，恒可验收）。"""
    rep.section("判据：母公司章节号集合（variant_matrix.parent_company_sections）")
    sections = load_parent_company_sections()
    listed = sorted(sections.get("listed", ()))
    soe = sorted(sections.get("soe", ()))
    rep.add(
        PASS if listed and soe else FAIL,
        f"两版母公司章节号非空（listed {len(listed)} / soe {len(soe)}）",
        f"listed = {listed}\nsoe    = {soe}",
    )
    overlap = set(listed) & set(soe)
    rep.add(
        PASS if not overlap else FAIL,
        "两版章节号集合交集为空（并集判定无歧义的前提）",
        f"交集 = {sorted(overlap)}" if overlap else "",
    )
    if listed:
        probe = listed[0]
        rep.add(
            PASS if is_parent_company_section(probe) else FAIL,
            f"逐字命中判定可用（探针 {probe!r}）",
        )
        rep.add(
            PASS if not is_parent_company_section(probe + "X") else FAIL,
            "非母公司章节号不被误判（逐字相等而非前缀匹配）",
        )


async def _check_pair(rep: Report, db, consol: Project) -> None:
    """对一个合并项目做端到端验收。"""
    rep.section(
        f"合并项目 {consol.name!r}（id={consol.id} company_code={consol.company_code!r} "
        f"audit_year={consol.audit_year!r}）"
    )

    parent = await resolve_parent_standalone_project(db, consol)
    if parent is None:
        rep.add(
            INFO,
            "未定位到母公司单体项目（合法状态：尚未建同代码同年度 standalone 兄弟）",
        )
    else:
        rep.add(
            PASS,
            f"母公司单体项目已定位：{parent.name!r}（id={parent.id}）",
            f"company_code={parent.company_code!r} audit_year={parent.audit_year!r} "
            f"report_scope={parent.report_scope!r}",
        )
        ok = (
            parent.company_code == consol.company_code
            and parent.audit_year == consol.audit_year
            and (parent.report_scope or "") == "standalone"
            and parent.id != consol.id
        )
        rep.add(
            PASS if ok else FAIL,
            "三条件齐备（同企业代码 / 同年度 / standalone）且不是合并项目自身",
        )
        back = await resolve_consolidated_sibling(db, parent)
        rep.add(
            PASS if back is not None and back.id == consol.id else FAIL,
            "反向定位自洽（母公司单体 → 同一个合并兄弟）",
        )
        rep.add(
            PASS if await is_parent_company_project(db, parent) else FAIL,
            "该单体项目被判定为母公司",
        )
        rep.add(
            PASS if not await is_parent_company_project(db, consol) else FAIL,
            "合并项目本身不被判定为母公司",
        )

    year = consol.audit_year
    if year is None:
        rep.add(INFO, "该合并项目 audit_year 为空，跳过 ctx 取数检查")
        return

    scope = await resolve_parent_scope_for_notes(db, consol.id, year)
    rep.add(
        PASS if scope.is_consolidated else FAIL,
        "附注取数入口识别为合并口径",
        f"resolution_failed={scope.resolution_failed}",
    )
    if parent is None:
        rep.add(
            PASS if scope.source.missing else FAIL,
            "无兄弟项目时标记缺失（前端据此显示「本项目未建母公司单体」灰态）",
        )
        rep.add(
            PASS if scope.parent_project_id is None else FAIL,
            "缺失时不回落合并项目 id（回落即静默显示合并数）",
        )
        return

    rep.add(
        PASS if scope.parent_project_id == parent.id else FAIL,
        "取数 project_id 已切到母公司单体项目",
        f"实际 = {scope.parent_project_id}",
    )
    payload = {
        "source_project_name": scope.source.project_name,
        "source_company_code": scope.source.company_code,
        "source_scope": scope.source.scope,
    }
    missing_keys = [k for k in PARENT_SOURCE_META_KEYS if payload.get(k) in (None, "")]
    rep.add(
        PASS if not missing_keys else FAIL,
        "溯源三项齐备（来源项目名 / 企业代码 / 口径）",
        f"payload = {payload}"
        + (f"\n缺失键 = {missing_keys}" if missing_keys else ""),
    )
    rep.add(
        PASS if PARENT_PROJECT_MISSING_KEY not in payload else FAIL,
        "已定位到来源项目时不带缺失标记",
    )


async def main_async(args: argparse.Namespace) -> int:
    rep = Report()
    rep.lines.append("母公司附注章节取数 —— 真实库验收（只读）")

    await _check_matrix_judgement(rep)

    async with async_session() as db:
        projects, consolidated = await _project_inventory(db)
        rep.section("真实库项目盘点")
        scopes: dict[str, int] = {}
        for p in projects:
            scopes[p.report_scope or "(null)"] = scopes.get(p.report_scope or "(null)", 0) + 1
        rep.add(INFO, f"未软删项目 {len(projects)} 条", f"report_scope 分布 = {scopes}")

        if not consolidated:
            rep.add(
                UNVERIFIABLE,
                "无法验收：本库无合并项目（report_scope='consolidated' 0 条）",
                "母公司口径只在合并项目下成立 ⇒ 端到端取数无对象可验。\n"
                "建一个「合并 + 同企业代码同年度 standalone」项目对后重跑本脚本即可完成验收。\n"
                "🔴 禁用 fixture 合成项目对冒充通过（需求 10.6）。",
            )
        else:
            for consol in consolidated:
                await _check_pair(rep, db, consol)

    rep.section("结论")
    if rep.failures:
        rep.add(FAIL, f"{rep.failures} 项检查失败")
    elif rep.unverifiable:
        rep.add(
            UNVERIFIABLE,
            f"{rep.unverifiable} 项无法验收（判据侧检查已通过），"
            f"{'按 --strict 视为失败' if args.strict else '非失败'}",
        )
    else:
        rep.add(PASS, "全部检查通过")

    text = "\n".join(rep.lines)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"报告已写入 {args.out}")
    else:
        # Windows GBK 控制台对部分字符不可编码 → 逐行降级，避免脚本本身崩
        for ln in rep.lines:
            try:
                print(ln)
            except UnicodeEncodeError:
                print(ln.encode("utf-8", "replace").decode("ascii", "replace"))

    if rep.failures:
        return 1
    if rep.unverifiable and args.strict:
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", help="报告落盘路径（默认打到 stdout）")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="把「无法验收」也视为失败（建了合并项目后在 CI 里用）",
    )
    args = ap.parse_args()
    try:
        return asyncio.run(main_async(args))
    except Exception as err:  # pragma: no cover - 脚本层
        print(f"[{FAIL:<12}] 脚本异常：{type(err).__name__}: {err}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
