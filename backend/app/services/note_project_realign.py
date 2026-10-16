"""存量项目附注按现行种子对齐 —— 计划（spec disclosure-note-template-word-realignment Phase 3，design §4.1）。

本模块是**纯函数**：输入行快照 + 生成链同口径的模板列表（``DisclosureEngine._load_templates``：口径过滤、
编号已归一、标题按口径），输出「改编号 / 脱树改挂 / 树字段 / 子节点跟随 / 补章 / 关联表」动作与只报告不动的
待人工项。执行、备份、恢复见 ``note_project_realign_apply``。

规则（逐条对应 design §4.1）：

1. 改编号：行编号经 ``normalize_section_code``（种子 ``legacy_section_numbers`` 别名 + 国企「五、N → 八、N」）
   得到现行编号；现行编号已被同项目同年度任何行占用（**含软删**：唯一索引不排除软删行）⇒ 不改，记冲突。
2. 树字段：对上模板的行按模板重写 ``parent_section_id / level / sort_index / sort_order / section_id``；
   ``section_title`` 只在行标题是该节某个已知标题（现名、口径名、``legacy_titles``）时改 —— 用户改过的不动。
   ``section_id`` 一律对齐模板（子节点的 ``parent_section_id`` 按模板写，上级不对齐树就断）；目标 id 被别的行
   占用（且那一行不会让出）时不改并报告。
3. 补章：模板有、项目没有的编号由生成链补（``generate_notes(only_sections=…)``，不复制构造逻辑）；编号被软删行
   占用 ⇒ 不补（用户删除 / 裁剪过，回收站可恢复）。
5. 脱树旧行：编号不在模板、且上级不在树上的活动行，按「规范化标题 + 章节类型」**唯一**对上模板节、且该编号无人
   占用 ⇒ 改挂；对上但已被占用 ⇒ 报告两行正文 / 表格是否相同；对不上或多处对上 ⇒ 报告。一律不删。
6. 关联表：公式推送状态（``note_section`` 与 ``addr_id`` 的 ``note://{旧}/`` 前缀）、裁剪页章节实例、未释放的
   章节锁按同一「旧 → 新」表改写；推送状态的新 ``addr_id`` 已存在（唯一索引）⇒ 不改并报告。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.note_section_catalog import normalize_section_code
from app.services.note_section_kind import canonical_title, classify_note_section

#: 对上模板的行要对齐的树字段（与 ``disclosure_engine._fill_tree_fields`` 同一组，外加 sort_order）
TREE_FIELDS = ("section_id", "parent_section_id", "level", "sort_index", "sort_order")


@dataclass(frozen=True)
class NoteRow:
    """``disclosure_notes`` 一行的计划所需字段（含软删行）。哈希只用于报告两行内容是否相同。"""

    id: str
    note_section: str
    section_title: str
    section_id: str | None = None
    parent_section_id: str | None = None
    level: int | None = None
    sort_index: int | None = None
    sort_order: int | None = None
    is_deleted: bool = False
    text_hash: str = ""
    table_hash: str = ""


@dataclass(frozen=True)
class RelatedRow:
    """关联表一行：``table`` ∈ formula_push_state / note_section_instances / note_section_locks。"""

    table: str
    id: str
    code: str
    addr_id: str | None = None


@dataclass
class RealignPlan:
    renames: list[dict[str, Any]] = field(default_factory=list)
    rehangs: list[dict[str, Any]] = field(default_factory=list)
    tree_updates: list[dict[str, Any]] = field(default_factory=list)
    child_reparents: list[dict[str, Any]] = field(default_factory=list)
    inserts: list[str] = field(default_factory=list)
    related_updates: list[dict[str, Any]] = field(default_factory=list)
    # —— 只报告、不动 ——
    rename_conflicts: list[dict[str, Any]] = field(default_factory=list)
    insert_blocked: list[dict[str, Any]] = field(default_factory=list)
    orphan_conflicts: list[dict[str, Any]] = field(default_factory=list)
    orphan_unmatched: list[dict[str, Any]] = field(default_factory=list)
    sid_conflicts: list[dict[str, Any]] = field(default_factory=list)
    related_conflicts: list[dict[str, Any]] = field(default_factory=list)
    titles_kept: list[dict[str, Any]] = field(default_factory=list)

    ACTION_KEYS = ("renames", "rehangs", "tree_updates", "child_reparents", "inserts", "related_updates")
    REPORT_KEYS = ("rename_conflicts", "insert_blocked", "orphan_conflicts", "orphan_unmatched", "sid_conflicts",
                   "related_conflicts", "titles_kept")

    def action_count(self) -> int:
        return sum(len(getattr(self, k)) for k in self.ACTION_KEYS)

    def counts(self) -> dict[str, int]:
        return {k: len(getattr(self, k)) for k in (*self.ACTION_KEYS, *self.REPORT_KEYS)}

    def code_changes(self) -> dict[str, str]:
        """本计划的「旧编号 → 新编号」（改编号 + 改挂），关联表按它改写。"""
        return {c["old"]: c["new"] for c in (*self.renames, *self.rehangs)}

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["counts"] = self.counts()
        return out


def _order_key(r: NoteRow) -> tuple:
    return (r.sort_order if r.sort_order is not None else 1 << 30, r.note_section, r.id)


def known_titles(seed: dict[str, Any] | None, template_title: str) -> set[str]:
    """该节的已知标题：现名（口径名）、种子 ``section_title``、各口径名、``legacy_titles``。"""
    out = {template_title}
    if seed:
        out.add(seed.get("section_title") or "")
        out.update((seed.get("scope_titles") or {}).values())
        out.update(seed.get("legacy_titles") or [])
    out.discard("")
    return out


def _match_key(title: str, code: str, template_type: str, report_scope: str | None) -> tuple[str, str]:
    kind = classify_note_section(code, template_type, report_scope, section_title=title)
    return canonical_title(title), kind


def _title_index(templates: list[dict], seeds: dict[str, dict], template_type: str,
                 report_scope: str | None) -> dict[tuple[str, str], set[str]]:
    """（规范化标题, 章节类型）→ 模板编号集合；每节按全部已知标题各建一个键。"""
    index: dict[tuple[str, str], set[str]] = {}
    for t in templates:
        code = t["note_section"]
        kind = classify_note_section(code, template_type, report_scope, section_title=t["section_title"])
        for title in known_titles(seeds.get(code), t["section_title"]):
            key = canonical_title(title)
            if key:
                index.setdefault((key, kind), set()).add(code)
    return index


def plan_realignment(
    rows: list[NoteRow],
    templates: list[dict[str, Any]],
    *,
    template_type: str,
    report_scope: str | None,
    seeds: dict[str, dict[str, Any]] | None = None,
    related: list[RelatedRow] | None = None,
) -> RealignPlan:
    """计划（无副作用）。``seeds``：现行编号 → 原始种子节（取 ``legacy_titles`` / ``scope_titles``）。"""
    seeds = seeds or {}
    by_code = {t["note_section"]: t for t in templates}
    occupied: dict[str, NoteRow] = {r.note_section: r for r in rows}
    active = sorted((r for r in rows if not r.is_deleted), key=_order_key)
    plan = RealignPlan()
    final: dict[str, str] = {r.id: r.note_section for r in active}

    for r in active:  # 1 改编号
        new = normalize_section_code(r.note_section, template_type=template_type)
        if new == r.note_section:
            continue
        holder = occupied.get(new)
        if holder is not None:
            plan.rename_conflicts.append({"note_id": r.id, "old": r.note_section, "new": new,
                                          "holder_id": holder.id, "holder_deleted": holder.is_deleted})
            continue
        plan.renames.append({"note_id": r.id, "old": r.note_section, "new": new, "title": r.section_title})
        occupied[new] = r
        final[r.id] = new

    _plan_orphans(plan, active, final, occupied, templates, seeds, template_type, report_scope)
    _plan_tree(plan, active, final, by_code, seeds)

    for t in templates:  # 3 补章
        holder = occupied.get(t["note_section"])
        if holder is None:
            plan.inserts.append(t["note_section"])
        elif holder.is_deleted:
            plan.insert_blocked.append({"note_section": t["note_section"], "holder_id": holder.id})

    plan_related(plan, related or [])
    return plan


def _on_tree_ids(active: list[NoteRow], final: dict[str, str], templates: list[dict]) -> set[str]:
    """在树上的行：对上模板的行，以及（递归地）上级在树上的非模板行（用户自建节）。"""
    by_code = {t["note_section"] for t in templates}
    sids = {t.get("section_id") for t in templates if t.get("section_id")}
    on = {r.id for r in active if final[r.id] in by_code}
    sids |= {r.section_id for r in active if r.id in on and r.section_id}
    grew = True
    while grew:
        grew = False
        for r in active:
            if r.id not in on and r.parent_section_id and r.parent_section_id in sids:
                on.add(r.id)
                if r.section_id:
                    sids.add(r.section_id)
                grew = True
    return on


def _plan_orphans(plan: RealignPlan, active: list[NoteRow], final: dict[str, str], occupied: dict[str, NoteRow],
                  templates: list[dict], seeds: dict[str, dict], template_type: str, report_scope: str | None) -> None:
    on_tree = _on_tree_ids(active, final, templates)
    index = _title_index(templates, seeds, template_type, report_scope)
    for r in active:
        code = final[r.id]
        if r.id in on_tree:
            continue  # 对上模板，或用户自建且挂在树上的节
        hits = sorted(index.get(_match_key(r.section_title, code, template_type, report_scope), ()))
        if len(hits) != 1:
            # 编号在种子里但被口径过滤掉 ⇒ 另一口径专属（单体项目里的合并章节，目录树与导出按口径隐藏）
            plan.orphan_unmatched.append({"note_id": r.id, "note_section": code, "title": r.section_title,
                                          "candidates": hits, "other_scope": code in seeds})
            continue
        target = hits[0]
        holder = occupied.get(target)
        if holder is not None:
            plan.orphan_conflicts.append({
                "note_id": r.id, "note_section": code, "title": r.section_title, "matched": target,
                "holder_id": holder.id, "holder_deleted": holder.is_deleted,
                "same_text": holder.text_hash == r.text_hash, "same_table": holder.table_hash == r.table_hash})
            continue
        plan.rehangs.append({"note_id": r.id, "old": code, "new": target, "title": r.section_title})
        occupied[target] = r
        final[r.id] = target


def _plan_tree(plan: RealignPlan, active: list[NoteRow], final: dict[str, str], by_code: dict[str, dict],
               seeds: dict[str, dict]) -> None:
    # section_id 先定终值：多行要同一个 id 时，原本就持有它的行留下，其余（会改成它的）不改并报告
    want_sid: dict[str, str | None] = {}
    for r in active:
        t = by_code.get(final[r.id])
        want_sid[r.id] = (t.get("section_id") or r.section_id) if t else r.section_id
    claimants: dict[str, list[NoteRow]] = {}
    for r in active:
        if want_sid[r.id]:
            claimants.setdefault(want_sid[r.id], []).append(r)
    for sid, rs in claimants.items():
        if len(rs) > 1:
            for r in rs:
                if r.section_id != sid:
                    plan.sid_conflicts.append({"note_id": r.id, "note_section": final[r.id], "section_id": sid,
                                               "holders": sorted(x.id for x in rs if x.section_id == sid)})
                    want_sid[r.id] = r.section_id
    moved = {r.section_id: want_sid[r.id] for r in active
             if r.section_id and want_sid[r.id] != r.section_id}

    for r in active:
        code = final[r.id]
        t = by_code.get(code)
        if t is None:  # 不在模板的行：上级 id 被对齐了就跟着改，其余不动
            if r.parent_section_id in moved:
                plan.child_reparents.append({"note_id": r.id, "note_section": code,
                                             "old": r.parent_section_id, "new": moved[r.parent_section_id]})
            continue
        changes: dict[str, list[Any]] = {}
        wanted = {"section_id": want_sid[r.id], "parent_section_id": t.get("parent_section_id"),
                  "level": t.get("level"), "sort_index": t.get("sort_index"), "sort_order": t.get("sort_order")}
        for f in TREE_FIELDS:
            new = wanted[f]
            if f in ("sort_index", "sort_order") and not isinstance(new, int):
                continue  # 模板没给整数序号 ⇒ 不动（生成链同口径：sort_index 非整数不写）
            if getattr(r, f) != new:
                changes[f] = [getattr(r, f), new]
        title = t["section_title"]
        if r.section_title != title:
            if r.section_title in known_titles(seeds.get(code), title):
                changes["section_title"] = [r.section_title, title]
            else:
                plan.titles_kept.append({"note_id": r.id, "note_section": code, "title": r.section_title,
                                         "template_title": title})
        if changes:
            plan.tree_updates.append({"note_id": r.id, "note_section": code, "changes": changes})


def _rewrite_addr(addr_id: str | None, changes: dict[str, str]) -> str | None:
    for old, new in changes.items():
        prefix = f"note://{old}/"
        if addr_id and addr_id.startswith(prefix):
            return f"note://{new}/" + addr_id[len(prefix):]
    return addr_id


def plan_related(plan: RealignPlan, related: list[RelatedRow]) -> None:
    """关联表改写。``related`` 须含新旧两组编号下的全部推送状态行（新 ``addr_id`` 撞唯一索引要靠它判）。"""
    changes = plan.code_changes()
    if not changes:
        return
    taken_addrs = {r.addr_id for r in related if r.table == "formula_push_state" and r.addr_id}
    for r in related:
        new_code = changes.get(r.code) if r.code else None
        new_addr = _rewrite_addr(r.addr_id, changes)
        if new_code is None and new_addr == r.addr_id:
            continue
        if new_addr != r.addr_id and new_addr in taken_addrs:
            plan.related_conflicts.append({"table": r.table, "id": r.id, "addr_id": r.addr_id, "new_addr_id": new_addr})
            continue
        plan.related_updates.append({"table": r.table, "id": r.id, "old": r.code, "new": new_code or r.code,
                                     "old_addr_id": r.addr_id, "new_addr_id": new_addr})
        taken_addrs.add(new_addr)
