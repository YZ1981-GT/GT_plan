"""四版 Word 附注白名单：每条差异的类别与证据（只读，不连库）。

spec: note-disclosure-pull-regression-and-headless-backend 任务 6 / R3.3（design §4.3）

用户 2026-10-17（disclosure-note-template-word-realignment US-8）：有底稿披露表的节，种子表格以底稿为准，与 Word 的表格
差异只登记、不作待修。原白名单只写「消费方 = 某脚本」—— 节上有 ``_aligned_by`` 标记就整节放行，没有底稿披露表的节也照样
放行，新出现的差异重跑生成器即被吸收。这里把「为什么允许」改成能核对的证据，由
``scripts/gen/gen_note_word_table_allowlist.py`` 现算写入、守卫逐字比对：

- ``workpaper_authority``：表键（``节#tN``）—— 这张表配上了底稿披露表，evidence ``{"paired_with": 底稿编码}``；
  节键（``table_count``）—— 节内每张表要么配上底稿、要么与 Word 同位置那张一致，evidence ``{"paired_tables": "k/n"}``，
  有没配上的另记 ``"word_consistent": [表序…]``。配对用 ``note_template_workpaper_alignment.compare_all``。
- ``word_placeholder``：Word 这一节不列表、正文写「…参照…」，evidence ``{"word_tables": 0, "word_text": 那一段}``。
- ``user_decision``：用户逐条拍板（手工维护的章节树条目），evidence ``{"decided_on", "decision_ref", "quote"}``，
  ``decision_ref`` 是仓库内的文档、``quote`` 须在文档里逐字出现（``evidence_problems``）。
- ``todo``：以上都证不了 —— 节没有登记底稿披露表 / 本表没配上 / 节内没配上的表与 Word 也不一致。条数只许减少（守卫钉住）；
  节上有 ``_aligned_by`` 标记的记进 evidence（只是过程标记，不算证据）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.services.note_word_tree import WORD_ALLOWLIST_CATEGORIES, Diff, VariantMatch

#: 用户决定的出处（仓库根相对路径）以仓库根为基准
REPO_ROOT = Path(__file__).resolve().parents[3]
_TABLE_KEY = re.compile(r"^(?P<sec>.+?)#t(?P<t>\d+)$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: 用户 2026-10-17 US-8 的出处（workpaper_authority 条目的理由里引用）
US8 = "用户 2026-10-17 US-8「有底稿披露表的节，种子表格以底稿为准」"


def split_key(key: str) -> tuple[str, int | None]:
    """报告键 → （章节号, 表序或 None）。同号第 n 个的「编号#n」按编号算。"""
    m = _TABLE_KEY.match(key)
    if m:
        return m.group("sec").split("#", 1)[0], int(m.group("t"))
    return key.split("#", 1)[0], None


def pairing_index(results: Iterable[Any]) -> tuple[dict[tuple[str, str], dict[int, str]], set[tuple[str, str]]]:
    """``compare_all`` 的各节配对结果 → （(口径, 章节) → {模板表序: 底稿编码}, 登记了底稿的节）。"""
    paired: dict[tuple[str, str], dict[int, str]] = {}
    registered: set[tuple[str, str]] = set()
    for r in results:
        registered.add((r.std, r.section))
        for p in r.pairs:
            for j in p.tpl_idx:
                paired.setdefault((r.std, r.section), {})[j] = p.wp_code
    return paired, registered


@dataclass(frozen=True)
class WordSide:
    tables: int
    placeholder: str  # Word 写「参照 / 参考附注…」的那一段（没有为空）


_REFER = re.compile(r"参照|参考附注")


def word_side(match: VariantMatch, section: str) -> WordSide | None:
    """种子节在 Word 里对上的节（或章正文叶子）：表数与「参照」段。先看节标题 / 节正文（上市「应收票据（披露格式参考
    附注五、4）」），再看章正文里点到本节名的那段（国企母公司章「…应收账款、其他应收款…应参照上述相应项目的要求加以
    注释」）。没对上返回 None。"""
    for pos, s in match.sections_by_position().items():
        if s.key != section:
            continue
        if pos in match.matches:
            wc, ws = match.matches[pos]
            own = [ws.title, *ws.body, *(t for _lvl, t in ws.blocks)]
            hit = next((t for t in own if _REFER.search(t)), "")
            if not hit and len(ws.norm) >= 4:
                hit = next((t for t in wc.body if _REFER.search(t) and ws.norm[:4] in t), "")
            return WordSide(len(ws.tables), hit)
        if pos in match.body_leaves:
            wc = match.body_leaves[pos]
            return WordSide(len(wc.tables), next((t for t in wc.body if _REFER.search(t)), ""))
    return None


def _marker(seed: dict[str, Any] | None, by_id: dict[str, dict[str, Any]], table: int | None) -> str:
    if seed is None:
        return ""
    tables = seed.get("tables") or []
    if table is not None and table < len(tables) and isinstance(tables[table], dict) and tables[table].get("_aligned_by"):
        return str(tables[table]["_aligned_by"])
    if seed.get("_aligned_by"):
        return str(seed["_aligned_by"])
    return str((by_id.get(seed.get("parent_section_id") or "") or {}).get("_aligned_by") or "")


def derive(diff: Diff, *, seed: dict[str, Any] | None, by_id: dict[str, dict[str, Any]],
           paired: dict[int, str], registered: bool, word: WordSide | None,
           table_diff_keys: set[str]) -> dict[str, Any]:
    """一条表格差异 → ``{category, evidence, reason}``（生成器用；输入都是现算的）。"""
    section, table = split_key(diff.key)
    n = len((seed or {}).get("tables") or [])
    if table is not None and table in paired:
        return {"category": "workpaper_authority", "evidence": {"paired_with": paired[table]},
                "reason": f"表格以底稿披露表为准（{US8}）：本表配上底稿 {paired[table]} 的披露表"}
    if table is None and paired and n:
        unpaired = [j for j in range(n) if j not in paired]
        word_n = word.tables if word else 0
        if all(j < word_n and f"{section}#t{j}" not in table_diff_keys for j in unpaired):
            ev: dict[str, Any] = {"paired_tables": f"{n - len(unpaired)}/{n}"}
            why = f"本节 {n - len(unpaired)}/{n} 张表配上底稿披露表"
            if unpaired:
                ev["word_consistent"] = unpaired
                why += f"，其余 {', '.join(f't{j}' for j in unpaired)} 与 Word 同位置的表一致"
            return {"category": "workpaper_authority", "evidence": ev, "reason": f"表格以底稿披露表为准（{US8}）：{why}"}
    if word is not None and word.tables == 0 and word.placeholder:
        return {"category": "word_placeholder", "evidence": {"word_tables": 0, "word_text": word.placeholder},
                "reason": f"Word 本节不列表、写「{word.placeholder}」；种子按所参照的章节列表"}
    ev = {}
    if table is None and paired:
        why = f"本节 {len(paired)}/{n} 张表配上底稿，没配上的表与 Word 也不一致"
        ev["paired_tables"] = f"{len(paired)}/{n}"
    elif registered:
        why = "本节登记了底稿披露表，但" + ("这张表没配上" if table is not None else "一张都没配上")
        ev["pairing"] = "unpaired"
    else:
        why = "本节没有登记底稿披露表（note_workpaper_sync_registry.json），US-8 不覆盖"
        ev["pairing"] = "unregistered"
    marker = _marker(seed, by_id, table)
    if marker:
        ev["aligned_by"] = marker
        why += f"；节上的过程标记 _aligned_by = {marker} 只说明改过，不证明以底稿为准"
    return {"category": "todo", "evidence": ev, "reason": f"未经底稿核实：{why}"}


def evidence_problems(entry: dict[str, Any], repo_root: Path = REPO_ROOT) -> list[str]:
    """手工维护条目的证据核对（生成的表格条目由生成器现算、守卫逐字比对，不走这里）。"""
    cat = entry.get("category")
    if cat not in WORD_ALLOWLIST_CATEGORIES:
        return [f"类别 {cat!r} 不在 {WORD_ALLOWLIST_CATEGORIES}"]
    if cat != "user_decision":
        return []
    ev = entry.get("evidence") or {}
    out = []
    if not _DATE.match(str(ev.get("decided_on") or "")):
        out.append("decided_on 须为 YYYY-MM-DD")
    ref = repo_root / str(ev.get("decision_ref") or "")
    if not ev.get("decision_ref") or not ref.is_file():
        return [*out, f"decision_ref 指向的文档不存在：{ev.get('decision_ref')!r}"]
    text = ref.read_text(encoding="utf-8")
    quote = str(ev.get("quote") or "")
    if not quote or quote not in text:
        out.append(f"quote 不在 {ev['decision_ref']} 里：{quote!r}")
    if str(ev.get("decided_on") or "") not in text:
        out.append(f"decided_on {ev.get('decided_on')} 不在 {ev['decision_ref']} 里")
    return out
