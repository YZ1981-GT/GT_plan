# -*- coding: utf-8 -*-
"""撤销 `56acf363d` 对两份附注模板的陈旧副本覆盖（按章节粒度）。

═══ 事故 ═══

`56acf363d feat(g-foundation): G循环foundation spec 19/19` 在提交里**顺带**把
`note_template_listed.json`（-24199/+10018）与 `note_template_soe.json`（-17631/+7574）
换成了一份**两个月前的陈旧副本**。该提交的 spec 文档与提交信息**零处**提及附注模板
（grep `note_template_` 0 命中，commit message 不含「附注/note」）⇒ 不是有意改动，
是提交时把工作树里的旧文件一并带上了。

实测后果（`56acf363d^` → `56acf363d`）：

  * listed：带 `columns` 的表 **411 → 11**、带 `guidance` 的表 393 → 18、行 2868 → 2579
  * soe   ：带 `columns` 的表 **260 → 3**、带 `guidance` 的表 251 → 19，
             删掉 `八、94 一般风险准备` 整章，母公司章十二被改名覆盖成「股份支付」
  * 覆盖后的 listed 与 `833a37fa5`（2026-07-26）**201/204 个章节逐字相同**，
    soe **185/187** —— 即退回到 7 月下旬，抹掉 07-30 ~ 09-26 之间约十个 spec 的
    附注结构对齐成果（D/F/G/H/K/L/M/N 各循环 + 母公司章 …）
  * 表头里的 `<br/>` 从 **0** 变成 67 / 77（7 月份 md 重建的残留形态被带回）
  * 后果全部可见于既有守卫：note 相关 67 个测试文件从 ~48 红涨到 1258 红，
    其中 `test_note_columns_coverage.py` 的防回退棘轮当场就红了 —— 但这批测试不在
    pre-push 门里，于是没人被拦住

═══ 恢复策略：按章节三方比较，而不是整文件 checkout ═══

`56acf363d` 之后还有**合法**改动落在同样两个文件上（`6dd1002be` report_row_code 纠错、
`cace65a9f` 母公司章 / M 循环 / 八、94 修订）。整文件 `git checkout 56acf363d^` 会把
它们一起抹掉。故逐章节比较 good（`56acf363d^`）/ bad（`56acf363d`）/ cur（工作树）：

  ========================  =====================  =========================================
  情形                      判定                   动作
  ========================  =====================  =========================================
  good == bad               未被覆盖波及           保留 cur
  cur == good               已恢复                 保留
  cur == bad                **纯回退**             恢复为 good（`--apply`）
  其余（覆盖后又被改过）    **冲突**               恢复为 good（仅 `--apply --restore-conflicts`）
                                                   随后**必须**重跑 owner 脚本重放合法改动
  ========================  =====================  =========================================

「冲突章可以直接恢复为 good 再重放」的依据是**逐叶子实测**：冲突章里 cur 相对 bad 的
全部差异只有三类，且每一类都有幂等的 owner 脚本能在 good 底座上重放 ——

  * `tables[].rows[].report_row_code`（listed 96 / soe 33 处）→ `remap_note_report_row_codes.py`
  * M 循环章（股本/实收资本/其他权益工具/库存股/其他综合收益/一般风险准备/未分配利润）
    → `fix_note_m_equity_structure.py`（在 good 上跑是 **0 处变更**：good 本来就对齐好了，
    所谓「93 项欠账」同样是这次覆盖造成的）
  * 母公司章（listed 十六 / soe 十二 家族）→ `fix_note_parent_company_chapter.py`

═══ 两处必须特判的键 ═══

* **改名的章节**：bad 把 soe 十二家族的 `section_id` 改成了 `chapter-12-gu-fen-zhi-fu-*`，
  cur（经 `cace65a9f`）又改回 `chapter-12-mu-gong-si-*`。只按 `section_id` 配对时
  bad 侧找不到 ⇒ 会被误判「未被波及」而漏恢复（首版即此错，靠「恢复后仍有 `<br/>` 残留、
  母公司脚本仍报告警」才发现）。⇒ bad 侧按 id 找不到时回退到**唯一**的 `section_number`。
* **`八、94`**：good 侧的挂载字段本身是错的（`parent_section_id` 少了 `zhu-yao-` 段 ⇒ 悬空，
  `sort_order=594` 不连续），cur 已由 `fix_note_m_equity_structure.py` 纠正且内容与 good
  逐字相同 ⇒ good 侧**不做** section_number 回退，按 id 配不上即自然保留 cur。

═══ 幂等与防二次误用 ═══

* `--apply`（不带 `--restore-conflicts`）只动「cur 与陈旧副本逐字相同」的章 —— 永远安全。
* `--restore-conflicts` 是**一次性**动作：它的前提是「覆盖尚未被修复」。判据 =
  **已提交的** HEAD 里仍有章节与陈旧副本逐字相同。修复提交之后该判据为假 ⇒ 拒绝执行，
  防止有人事后再跑一遍把重放过的合法改动冲掉。
* `--check`：工作树里仍有章节与陈旧副本逐字相同 ⇒ exit 1。

序列化保持原文件行尾（CRLF/LF 探测），形态 `indent=2 + ensure_ascii=False + 尾换行`。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = {
    "listed": "backend/data/note_template_listed.json",
    "soe": "backend/data/note_template_soe.json",
}
BAD_COMMIT = "56acf363d"
GOOD_REV = f"{BAD_COMMIT}^"
OWNER_SCRIPTS = (
    "python backend/scripts/fix/fix_note_parent_company_chapter.py --apply",
    "python backend/scripts/fix/fix_note_m_equity_structure.py",
    "python backend/scripts/fix/remap_note_report_row_codes.py --apply",
)


def _git_json(rev: str, rel: str) -> dict[str, Any]:
    proc = subprocess.run(
        ["git", "show", f"{rev}:{rel}"], cwd=str(REPO_ROOT), capture_output=True
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"[ERR] 取不到 {rev}:{rel} —— 本脚本依赖 git 历史里的 {BAD_COMMIT}，"
            "浅克隆或历史被改写时无法使用"
        )
    return json.loads(proc.stdout.decode("utf-8"))


def _digest(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _id(section: dict[str, Any]) -> str:
    return str(section.get("section_id") or f"#num:{section.get('section_number')}")


def _num(section: dict[str, Any]) -> str:
    return str(section.get("section_number") or "").replace(" ", "")


class _StaleIndex:
    """陈旧副本的查找表：先按 section_id，找不到再按**唯一**的 section_number。"""

    def __init__(self, bad: dict[str, Any]) -> None:
        secs = bad.get("sections") or []
        self.by_id = {_id(s): s for s in secs}
        counts = Counter(_num(s) for s in secs)
        self.by_num = {_num(s): s for s in secs if _num(s) and counts[_num(s)] == 1}

    def match(self, section: dict[str, Any]) -> dict[str, Any] | None:
        return self.by_id.get(_id(section)) or self.by_num.get(_num(section))


def classify(
    cur: dict[str, Any], good: dict[str, Any], bad: dict[str, Any]
) -> list[tuple[str, dict[str, Any], dict[str, Any] | None]]:
    """逐章节返回 ``(判定, cur 章, good 章)``；判定 ∈ kept/done/pure/conflict。"""
    gmap = {_id(s): s for s in good.get("sections") or []}
    stale = _StaleIndex(bad)
    out: list[tuple[str, dict[str, Any], dict[str, Any] | None]] = []
    for sec in cur.get("sections") or []:
        g, b = gmap.get(_id(sec)), stale.match(sec)
        if g is None or b is None or _digest(g) == _digest(b):
            out.append(("kept", sec, g))
        elif _digest(sec) == _digest(g):
            out.append(("done", sec, g))
        elif _digest(sec) == _digest(b):
            out.append(("pure", sec, g))
        else:
            out.append(("conflict", sec, g))
    return out


def _pure_left_in(doc: dict[str, Any], good: dict[str, Any], bad: dict[str, Any]) -> int:
    return sum(1 for kind, _, _ in classify(doc, good, bad) if kind == "pure")


def _serialise(doc: dict[str, Any], like: bytes) -> bytes:
    data = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return data.replace(b"\n", b"\r\n") if b"\r\n" in like else data


def _stats(doc: dict[str, Any]) -> str:
    tables = [t for s in doc.get("sections") or [] for t in (s.get("tables") or [])]
    br = sum(
        1 for t in tables for h in (t.get("headers") or []) if "<br" in str(h).lower()
    )
    return (
        f"sections={len(doc.get('sections') or [])} tables={len(tables)} "
        f"带columns={sum(1 for t in tables if t.get('columns'))} "
        f"带guidance={sum(1 for t in tables if t.get('guidance'))} 表头<br/>={br}"
    )


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--apply", action="store_true", help="写入文件")
    grp.add_argument("--check", action="store_true", help="工作树仍有纯回退章节则 exit 1")
    ap.add_argument("--dry-run", action="store_true", help="只报告（默认）")
    ap.add_argument(
        "--restore-conflicts",
        action="store_true",
        help="一次性：冲突章也恢复为 good（随后必须重跑 owner 脚本）",
    )
    args = ap.parse_args()

    if args.restore_conflicts and not args.apply:
        ap.error("--restore-conflicts 只能与 --apply 同用")

    pending_total = 0
    for variant, rel in TEMPLATES.items():
        path = REPO_ROOT / rel
        raw = path.read_bytes()
        cur = json.loads(raw.decode("utf-8"))
        good, bad = _git_json(GOOD_REV, rel), _git_json(BAD_COMMIT, rel)

        if args.restore_conflicts:
            committed_pure = _pure_left_in(_git_json("HEAD", rel), good, bad)
            if committed_pure == 0:
                print(
                    f"[refuse] {variant}: 已提交的 HEAD 里已无与陈旧副本逐字相同的章节 ⇒ "
                    "覆盖已被修复并提交。--restore-conflicts 是一次性动作，再跑会把重放过的"
                    "合法改动冲掉，拒绝执行。"
                )
                return 2

        rows = classify(cur, good, bad)
        counts = Counter(kind for kind, _, _ in rows)
        pending_total += counts["pure"]

        new_sections: list[dict[str, Any]] = []
        for kind, sec, g in rows:
            restore = kind == "pure" or (kind == "conflict" and args.restore_conflicts)
            new_sections.append(json.loads(json.dumps(g, ensure_ascii=False)) if restore else sec)
        doc = dict(cur)
        doc["sections"] = new_sections

        print(f"=== {variant} ===")
        print(f"  现状  : {_stats(cur)}")
        print(f"  恢复后: {_stats(doc)}")
        print(
            f"  纯回退={counts['pure']}  冲突={counts['conflict']}  "
            f"已恢复={counts['done']}  未波及={counts['kept']}"
        )
        for kind, sec, _ in rows:
            if kind == "conflict":
                mark = "→ 恢复" if args.restore_conflicts else "（保留现状）"
                print(f"    冲突 {mark}: {sec.get('section_number')} {sec.get('section_title')}")
        if args.apply and doc["sections"] != cur["sections"]:
            path.write_bytes(_serialise(doc, raw))
            print(f"  [apply] 已写入 {rel}")

    if args.check:
        print(f"\n[check] 工作树仍与陈旧副本逐字相同的章节 = {pending_total}")
        return 1 if pending_total else 0
    if args.apply and args.restore_conflicts:
        print("\n[next] 冲突章已恢复为 good，必须按序重跑 owner 脚本重放覆盖后的合法改动：")
        for cmd in OWNER_SCRIPTS:
            print(f"  {cmd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
