"""级别回填迁移真 PG 测试的模型、生成器与样例（partner-manager-edit-permission 任务 7.2 起；需求 4.2~4.7、4.9、4.11；
design Property 3~5，§5.2、§8.3）。

辅助模块，不是测试文件（文件名不匹配 ``test_*.py``，不被收集）。使用方：``test_level_backfill_migration_pg.py``（测试函数与断言）；
数据世界与执行器驱动在 ``level_backfill_world.py``。任务 7.4 把 7.2 / 7.3 的模型、生成器、``@example`` 世界、固定样例与需求 4.5
用例的数据和模型从测试文件原样挪到这里（代码逐行未改，只换了文件），7.4 的往返模型、生成器与样例接在其后。

模型（需求 4.2~4.4 原文；不读生产代码的 ``ROLE_MAP`` / ``EQCR_ROLE_ALIASES``，也不读迁移 SQL）：现行委派 = 委派与人员库记录
都未删除且记录已关联用户（不看项目是否软删、不看全局角色）；委派角色按字符串精确比对；别名取需求 2.5 期望表
``tests/role_map_expected.py``：合伙人 / 经理别名 = 取值为 (partner, edit) 或 (manager, edit) 的键，EQCR 别名 =
``EXPECTED_EQCR_ALIASES``。未删除的成员行：持 EQCR 别名现行委派 ⇒ (原项目角色, review)、rule ``eqcr``（4.3，优先于 4.2）；
否则持合伙人 / 经理别名现行委派 ⇒ (partner 或 manager, edit)、rule ``partner_manager``，同时持映射为 partner 与 manager 的
取 partner（4.2）；其余成员行与已删除的行不动（4.4）；目标值已等于现值的不改、不记（4.2、4.3）。

生成维度（需求 4.6）：1~3 个项目各自现行 / 已软删；1~4 名用户，全局角色取 ``UserRole`` 全部取值；每人 0~3 条随机人员库
记录（约三分之一已删除、约三分之一未关联用户），每条记录在每个项目至多一条现行委派、另可带已删除委派
（``idx_assignment_project_staff``）——同一用户因此可经多条记录在同一项目持多条现行委派；委派角色取四个别名集合的全部键
（另单列会触发改动的合伙人 / 经理与 EQCR 别名以提高命中）、大小写变体、首尾空白（含制表符与全角空格）变体、长度 0~30 的
任意串；每人在每个项目至多一条未删除成员行（``idx_project_users_project_user``）、另可带已删除行，（项目角色，级别）任取，
约一半带循环 / 科目范围与有效期。用户 0 另有一个「焦点」：在第一个项目一条现行、已关联的人员库记录持一条合伙人 / 经理或
EQCR 别名委派，外加一条未删除成员行（不加焦点时首轮统计 5 个样例全部 0 行改动）。

往返（任务 7.4；需求 4.6、4.9）：``_rollback_model`` 按 4.9 原文独立推导回滚后的值（有回填记录且回滚前仍等于记录的目标值 ⇒
记录的迁移前值，其余保持回滚前的现值）；``_roundtrip_cases`` 在 ``_worlds`` 之上另加「正向执行一次或两次」与「回滚前的他途改动」
两个维度；``_R49`` / ``_R49_STEPS`` 是 4.9 各分支的显式样例。

执行语义与对账（任务 7.5；需求 4.1、4.10、12.7）：``_R41_MIXED``（正向会改动需求 4.2 / 4.3 的行，另有不改不记的行）与
``_R41_NOOP``（正向不改任何行，其中几行持合伙人 / 经理或 EQCR 别名委派、已在目标值上）；需求 4.10 制造冲突的测试数据语句
（预建不兼容的同名表、给回填记录表建依赖视图）及其预期的报错片段；需求 12.7 的别名取自期望表（合伙人 / 经理 5 个 + EQCR 2 个），
``_reconcile_world`` 给每个别名一个世界。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace

from hypothesis import strategies as st

from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from tests.level_backfill_world import BACKFILL_TABLE, ROLE_MAX_LEN, Asg, Outcome, Pair, Person, Row, RowKey, Staff, World
from tests.role_map_expected import EXPECTED_EQCR_ALIASES, EXPECTED_ROLE_MAP

# ─── 模型（需求 4.2~4.4 原文；不调用被测迁移，不读生产代码） ─────────────────

# 合伙人 / 经理别名集合 → 映射给出的项目角色：需求 2.5 期望表中取值为 (partner, edit) 或 (manager, edit) 的键
_PM_ROLE: dict[str, str] = {
    alias: role for alias, (role, level) in EXPECTED_ROLE_MAP.items() if level == "edit" and role in ("partner", "manager")
}
_EQCR_ALIASES: frozenset[str] = EXPECTED_EQCR_ALIASES


def _pm(role: str) -> Outcome:
    """需求 4.2 的目标：级别 edit，项目角色取映射给出的 partner / manager。"""
    return (role, "edit", "partner_manager")


def _eq(role: str) -> Outcome:
    """需求 4.3 的目标：级别 review，项目角色保持迁移前的值。"""
    return (role, "review", "eqcr")


def _live_roles(world: World) -> dict[tuple[str, int], set[str]]:
    """（项目键，用户下标）→ 现行委派角色集合：委派与人员库记录都未删除、记录已关联用户；不看项目是否软删、不看全局角色。"""
    live: dict[tuple[str, int], set[str]] = defaultdict(set)
    for pi, person in enumerate(world.people):
        for staff in person.staff:
            if staff.linked and not staff.deleted:
                for item in staff.assignments:
                    if not item.deleted:
                        live[(item.project, pi)].add(item.role)
    return live


def _model(world: World) -> dict[RowKey, Outcome | None]:
    """每个成员行的期望：被改动行给（项目角色，级别，rule），其余为 None（不改、不记）。"""
    live = _live_roles(world)
    expected: dict[RowKey, Outcome | None] = {}
    for pi, person in enumerate(world.people):
        for ri, row in enumerate(person.rows):
            roles = live.get((row.project, pi), set())
            partner_manager = roles & _PM_ROLE.keys()
            target: Outcome | None = None
            if row.deleted:
                target = None  # 4.4：已删除的成员行不动
            elif roles & _EQCR_ALIASES:
                target = _eq(row.role)  # 4.3：持 EQCR 别名现行委派，不论是否另持其他委派
            elif partner_manager:
                has_partner = any(_PM_ROLE[alias] == "partner" for alias in partner_manager)
                target = _pm("partner" if has_partner else "manager")  # 4.2
            if target is not None and target[:2] == (row.role, row.level):
                target = None  # 已等于目标值：不改写，也不计为被改动行
            expected[(pi, ri)] = target
    return expected


# ─── 生成器（需求 4.6） ──────────────────────────────────────────────────────

_ROLE_KEYS = tuple(sorted(EXPECTED_ROLE_MAP))  # 四个别名集合的全部键
_HOT_KEYS = (*sorted(_PM_ROLE), *sorted(_EQCR_ALIASES))  # 会触发改动的别名，单列一支以提高命中
_BLANKS = (" ", "  ", "\t", "\u3000")
_PROJECT_ROLES = tuple(role.value for role in ProjectUserRole)
_LEVELS = tuple(level.value for level in PermissionLevel)
_GLOBAL_ROLES = tuple(role.value for role in UserRole)


def _pad(key: str, blank: str, side: str) -> str:
    return (blank if side != "trail" else "") + key + (blank if side != "lead" else "")


_role_strings = st.one_of(
    st.sampled_from(_HOT_KEYS),
    st.sampled_from(_ROLE_KEYS),
    st.sampled_from(_ROLE_KEYS).flatmap(lambda key: st.sampled_from((key.upper(), key.capitalize(), key.swapcase()))),
    st.builds(_pad, st.sampled_from(_ROLE_KEYS), st.sampled_from(_BLANKS), st.sampled_from(("lead", "trail", "both"))),
    # PG 的 varchar 存不了 NUL，真实委派角色里不会有它
    st.text(st.characters(exclude_categories=("Cs",), exclude_characters="\x00"), max_size=ROLE_MAX_LEN),
)
_one_in_three = st.sampled_from((False, False, True))
_two_in_three = st.sampled_from((True, True, False))


@st.composite
def _worlds(draw: st.DrawFn) -> World:
    """随机世界。用户 0 在 P0 另有一个「焦点」：一条现行、已关联的人员库记录持一条会触发改动的别名委派，外加一条未删除
    成员行，让每个样例都有迁移要判定的行（焦点行本身也可能已等于目标值，或被同一用户的其他委派改判）；其余全部随机。"""
    projects = tuple((f"P{index}", draw(st.booleans())) for index in range(draw(st.integers(1, 3))))
    keys = [key for key, _ in projects]

    def member(project: str, deleted: bool) -> Row:
        role, level = draw(st.sampled_from(_PROJECT_ROLES)), draw(st.sampled_from(_LEVELS))
        return Row(project, role, level, deleted=deleted, scoped=draw(st.booleans()))

    people: list[Person] = []
    for pi in range(draw(st.integers(1, 4))):
        staff: list[Staff] = [Staff((Asg(keys[0], draw(st.sampled_from(_HOT_KEYS))),))] if pi == 0 else []
        for _ in range(draw(st.integers(0, 3))):
            items: list[Asg] = []
            for key in keys:  # 每条记录在每个项目至多一条现行委派，另可带一条已删除委派
                if draw(_two_in_three):
                    items.append(Asg(key, draw(_role_strings)))
                if draw(_one_in_three):
                    items.append(Asg(key, draw(_role_strings), deleted=True))
            staff.append(Staff(tuple(items), deleted=draw(_one_in_three), linked=not draw(_one_in_three)))
        rows: list[Row] = []
        for key in keys:  # 每个项目至多一条未删除成员行，另可带一条已删除行
            if (pi == 0 and key == keys[0]) or draw(_two_in_three):
                rows.append(member(key, False))
            if draw(_one_in_three):
                rows.append(member(key, True))
        people.append(Person(draw(st.sampled_from(_GLOBAL_ROLES)), tuple(staff), tuple(rows)))
    return World(projects, tuple(people))


# ─── 显式样例（hypothesis @example） ────────────────────────────────────────

_E1 = World((("P0", True),), name="E1-empty-world")  # 只有一个已软删项目：回填记录表照建且为空，版本照登记
_E2 = World(  # 有现行委派、没有成员行：不补建成员行，也没有回填记录（4.4）
    (("P0", False), ("P1", True)),
    (
        Person("auditor", (Staff((Asg("P0", "manager"), Asg("P1", "eqcr"))), Staff((Asg("P0", "独立复核合伙人"),)))),
        Person("admin", (Staff((Asg("P1", "合伙人"),)),)),
    ),
    name="E2-assignments-without-member-rows",
)


# ─── 固定样例：期望按需求原文逐行写死（Row.expect） ─────────────────────────


def _s(*items: Asg, deleted: bool = False, linked: bool = True) -> Staff:
    return Staff(items, deleted=deleted, linked=linked)


def _a(project: str, role: str, *, deleted: bool = False) -> Asg:
    return Asg(project, role, deleted)


def _r(project: str, role: str, level: str, expect: Outcome | None = None, *, deleted: bool = False,
       scoped: bool = False) -> Row:
    return Row(project, role, level, deleted=deleted, scoped=scoped, expect=expect)


def _u(global_role: str, *staff: Staff, rows: tuple[Row, ...]) -> Person:
    return Person(global_role, staff, rows)


_P = (("P", False),)
_P_Q = (("P", False), ("Q", False))
_P_Q_D = (("P", False), ("Q", False), ("D", True))  # D 为已软删项目

_F1 = World(_P_Q, (  # 需求 4.2：五个合伙人 / 经理别名各一条现行委派，全局角色各异
    _u("auditor", _s(_a("P", "signing_partner")), rows=(_r("P", "auditor", "readonly", _pm("partner"), scoped=True),)),
    _u("readonly", _s(_a("P", "partner")), rows=(_r("P", "auditor", "readonly", _pm("partner")),)),
    _u("qc", _s(_a("P", "合伙人")), rows=(_r("P", "readonly", "readonly", _pm("partner")),)),
    _u("auditor", _s(_a("P", "manager")), rows=(_r("P", "auditor", "readonly", _pm("manager")),)),
    _u("partner", _s(_a("P", "项目经理")), rows=(_r("P", "qc", "review", _pm("manager"), scoped=True),)),
    # P 上有现行委派、没有成员行：不补建；Q 上的成员行没有委派：不动
    _u("manager", _s(_a("P", "manager")), rows=(_r("Q", "auditor", "readonly"),)),
), name="f1-pm-five-aliases")

_F2 = World(_P, (  # 需求 4.2：同时持合伙人与经理取 partner；全局角色不参与判定；只差项目角色也算改动
    _u("auditor", _s(_a("P", "manager")), _s(_a("P", "partner")), rows=(_r("P", "auditor", "readonly", _pm("partner")),)),
    _u("admin", _s(_a("P", "manager")), rows=(_r("P", "manager", "review", _pm("manager")),)),
    _u("eqcr", _s(_a("P", "manager")), rows=(_r("P", "auditor", "readonly", _pm("manager")),)),  # 全局 eqcr、无 EQCR 委派
    _u("qc", _s(_a("P", "项目经理")), _s(_a("P", "合伙人")), rows=(_r("P", "qc", "review", _pm("partner")),)),
    _u("auditor", _s(_a("P", "partner")), rows=(_r("P", "auditor", "edit", _pm("partner")),)),
    _u("partner", _s(_a("P", "manager")), rows=(_r("P", "partner", "edit", _pm("manager"), scoped=True),)),
), name="f2-pm-partner-wins-global-role-ignored")

_F3 = World(_P_Q_D, (  # 需求 4.2：已软删项目上的行照改；委派只作用于所在项目
    _u("auditor", _s(_a("D", "manager")),
       rows=(_r("D", "auditor", "readonly", _pm("manager")), _r("P", "auditor", "readonly"))),
    _u("auditor", _s(_a("Q", "manager")), rows=(_r("P", "qc", "review"), _r("Q", "auditor", "readonly", _pm("manager")))),
    _u("manager", _s(_a("D", "signing_partner")), rows=(_r("D", "manager", "edit", _pm("partner"), scoped=True),)),
), name="f3-pm-soft-deleted-project-and-project-scope")

_F4 = World((("P", False), ("D", True)), (  # 需求 4.3：两个 EQCR 别名，原级别 edit / readonly 都改为 review，项目角色不动
    _u("auditor", _s(_a("P", "eqcr")), rows=(_r("P", "auditor", "edit", _eq("auditor"), scoped=True),)),
    _u("readonly", _s(_a("P", "独立复核合伙人")), rows=(_r("P", "readonly", "readonly", _eq("readonly")),)),
    _u("partner", _s(_a("P", "独立复核合伙人")), rows=(_r("P", "manager", "edit", _eq("manager")),)),
    _u("eqcr", _s(_a("P", "eqcr")), rows=(_r("P", "partner", "review"),)),  # 原级别已是 review：不计为改动
    _u("admin", _s(_a("D", "eqcr")), rows=(_r("D", "qc", "edit", _eq("qc")),)),  # 已软删项目
), name="f4-eqcr-aliases-to-review")

_F5 = World(_P, (  # 需求 4.3：与合伙人 / 经理委派同持时 EQCR 优先（经两份人员库记录）
    _u("auditor", _s(_a("P", "manager")), _s(_a("P", "eqcr")), rows=(_r("P", "manager", "edit", _eq("manager")),)),
    _u("partner", _s(_a("P", "partner")), _s(_a("P", "独立复核合伙人")), rows=(_r("P", "partner", "review"),)),  # 不升 edit
    _u("auditor", _s(_a("P", "signing_partner")), _s(_a("P", "eqcr")),
       rows=(_r("P", "auditor", "readonly", _eq("auditor")),)),
    _u("manager", _s(_a("P", "项目经理")), _s(_a("P", "独立复核合伙人")),
       rows=(_r("P", "readonly", "readonly", _eq("readonly")),)),
), name="f5-eqcr-priority-over-partner-manager")

_F6 = World(_P, (  # 需求 4.4：只持有质控 / 审计员 / 未登记委派，或没有委派：都不动
    _u("auditor", _s(_a("P", "qc")), rows=(_r("P", "auditor", "readonly"),)),
    _u("qc", _s(_a("P", "质控")), rows=(_r("P", "qc", "review"),)),
    _u("auditor", _s(_a("P", "auditor")), rows=(_r("P", "readonly", "readonly"),)),
    _u("auditor", _s(_a("P", "审计员")), rows=(_r("P", "auditor", "edit"),)),
    _u("manager", _s(_a("P", "assistant")), rows=(_r("P", "manager", "review"),)),
    _u("partner", _s(_a("P", "助理")), rows=(_r("P", "partner", "readonly"),)),
    _u("admin", _s(_a("P", "观察员")), rows=(_r("P", "manager", "review"),)),
    _u("auditor", _s(_a("P", "")), rows=(_r("P", "auditor", "readonly"),)),
    _u("qc", _s(_a("P", "qc")), _s(_a("P", "观察员")), rows=(_r("P", "qc", "review", scoped=True),)),
    _u("manager", rows=(_r("P", "manager", "review"),)),  # 没有任何委派
), name="f6-only-qc-auditor-unregistered")

_F7 = World(_P, (  # 需求 4.2：精确字符串比对，大小写与首尾空白都不归一（变体按未登记角色处理）
    _u("auditor", _s(_a("P", "Manager")), rows=(_r("P", "auditor", "readonly"),)),
    _u("auditor", _s(_a("P", " manager")), rows=(_r("P", "manager", "review"),)),
    _u("auditor", _s(_a("P", "manager ")), rows=(_r("P", "auditor", "readonly"),)),
    _u("auditor", _s(_a("P", "PARTNER")), rows=(_r("P", "auditor", "readonly"),)),
    _u("auditor", _s(_a("P", "Signing_Partner")), rows=(_r("P", "qc", "review"),)),
    _u("auditor", _s(_a("P", "EQCR")), rows=(_r("P", "manager", "edit"),)),  # EQCR 变体也不降为 review
    _u("auditor", _s(_a("P", " eqcr")), rows=(_r("P", "partner", "edit"),)),
    _u("auditor", _s(_a("P", "独立复核合伙人 ")), rows=(_r("P", "auditor", "edit"),)),
    _u("auditor", _s(_a("P", "\u3000项目经理")), rows=(_r("P", "auditor", "readonly"),)),
), name="f7-case-and-whitespace-variants")

_F8 = World(_P, (  # 需求 4.2、4.4：已删除的成员行 / 委派 / 人员库记录，以及未关联用户的记录，都不构成现行委派
    _u("auditor", _s(_a("P", "manager")), rows=(_r("P", "auditor", "readonly", deleted=True),)),
    _u("auditor", _s(_a("P", "manager")),
       rows=(_r("P", "qc", "review", deleted=True, scoped=True), _r("P", "auditor", "readonly", _pm("manager")))),
    _u("auditor", _s(_a("P", "manager", deleted=True)), rows=(_r("P", "auditor", "readonly"),)),
    _u("auditor", _s(_a("P", "manager"), deleted=True), rows=(_r("P", "auditor", "readonly"),)),
    _u("auditor", _s(_a("P", "manager"), linked=False), rows=(_r("P", "auditor", "readonly"),)),
    # EQCR 委派所在的人员库记录已删 / EQCR 委派已删 ⇒ 不按 4.3，按另一条现行经理委派走 4.2
    _u("auditor", _s(_a("P", "manager")), _s(_a("P", "eqcr"), deleted=True),
       rows=(_r("P", "manager", "review", _pm("manager")),)),
    _u("auditor", _s(_a("P", "manager")), _s(_a("P", "eqcr", deleted=True)),
       rows=(_r("P", "auditor", "readonly", _pm("manager")),)),
    _u("auditor", _s(_a("P", "eqcr"), deleted=True), rows=(_r("P", "manager", "edit"),)),
    # 同一人员库记录在同一项目：一条已删除的 eqcr + 一条现行的 manager
    _u("auditor", _s(_a("P", "eqcr", deleted=True), _a("P", "manager")),
       rows=(_r("P", "auditor", "readonly", _pm("manager")),)),
), name="f8-deleted-and-unlinked")

_F9 = World(_P, (  # 需求 4.2、4.3：项目角色与级别已等于目标值的行不改写、不记录
    _u("auditor", _s(_a("P", "manager")), rows=(_r("P", "manager", "edit"),)),
    _u("auditor", _s(_a("P", "signing_partner")), rows=(_r("P", "partner", "edit", scoped=True),)),
    _u("auditor", _s(_a("P", "partner")), _s(_a("P", "manager")), rows=(_r("P", "partner", "edit"),)),
    _u("auditor", _s(_a("P", "eqcr")), rows=(_r("P", "auditor", "review"),)),
    _u("auditor", _s(_a("P", "独立复核合伙人")), rows=(_r("P", "partner", "review"),)),
    _u("auditor", _s(_a("P", "合伙人")), rows=(_r("P", "manager", "edit", _pm("partner")),)),  # 对照：只差项目角色 ⇒ 改动
), name="f9-already-at-target-not-recorded")

_FIXED: tuple[World, ...] = (_F1, _F2, _F3, _F4, _F5, _F6, _F7, _F8, _F9)


# ─── 需求 4.5：两次执行之间有他途改动（不是 Property 4 本体） ────────────────

_R45 = World((("P", False), ("D", True)), (  # 第一次的期望写在 Row.expect：改动 7 行（4.2 五行、4.3 两行），3 行不改
    _u("auditor", _s(_a("P", "manager")), rows=(_r("P", "auditor", "readonly", _pm("manager")),)),
    _u("auditor", _s(_a("P", "partner")), rows=(_r("P", "auditor", "readonly", _pm("partner")),)),
    _u("auditor", _s(_a("P", "eqcr")), rows=(_r("P", "auditor", "edit", _eq("auditor")),)),
    _u("partner", _s(_a("P", "独立复核合伙人")), rows=(_r("P", "qc", "edit", _eq("qc")),)),
    _u("manager", _s(_a("P", "signing_partner")), rows=(_r("P", "auditor", "readonly", _pm("partner"), scoped=True),)),
    _u("auditor", _s(_a("P", "项目经理")), rows=(_r("P", "readonly", "readonly", _pm("manager")),)),
    _u("auditor", _s(_a("D", "manager")), rows=(_r("D", "auditor", "readonly", _pm("manager")),)),  # 已软删项目
    _u("auditor", _s(_a("P", "manager")), rows=(_r("P", "manager", "edit"),)),  # 已等于目标值
    _u("eqcr", _s(_a("P", "manager")), _s(_a("P", "eqcr")), rows=(_r("P", "partner", "review"),)),  # 已等于目标值（EQCR 优先）
    _u("auditor", _s(_a("P", "qc")), rows=(_r("P", "auditor", "readonly"),)),  # 只持质控委派
), name="r4.5-existing-records-not-overwritten")

_FIRST = "first"  # 与第一次的回填记录逐值相同（含 recorded_at）
Step = tuple[Pair | None, Pair, str | tuple[Pair, Outcome] | None]
# 成员行键 →（他途改成的值，None 为不改；第二次执行后的值；第二次执行后的回填记录：_FIRST、（迁移前值，目标值与 rule）为第二次
# 新增、None 为没有记录）。按需求 4.2~4.5 原文写死；4.3 的项目角色取第二次执行前的值。
_R45_STEPS: dict[RowKey, Step] = {
    (0, 0): (("manager", "review"), ("manager", "edit"), _FIRST),  # 4.2 行被改了级别：再次改为目标值，记录不覆盖
    (1, 0): (None, ("partner", "edit"), _FIRST),  # 未被他途改动：行与记录都不变
    (2, 0): (("auditor", "readonly"), ("auditor", "review"), _FIRST),  # 4.3 行被改了级别
    (3, 0): (("manager", "readonly"), ("manager", "review"), _FIRST),  # 4.3 行被改了项目角色：记录的目标值仍是 (qc, review)
    (4, 0): (("manager", "review"), ("partner", "edit"), _FIRST),  # 4.2 行被改了项目角色与级别
    (5, 0): (("partner", "edit"), ("manager", "edit"), _FIRST),  # 4.2 行只被改了项目角色
    (6, 0): (("auditor", "readonly"), ("manager", "edit"), _FIRST),  # 已软删项目上的行被改回迁移前值
    (7, 0): (("manager", "readonly"), ("manager", "edit"), (("manager", "readonly"), _pm("manager"))),  # 第二次改动并新增记录
    (8, 0): (None, ("partner", "review"), None),  # 不改不记
    (9, 0): (("manager", "edit"), ("manager", "edit"), None),  # 被他途改动，第二次也不碰
}


def _with_pairs(world: World, pairs: dict[RowKey, Pair]) -> World:
    """成员行（项目角色，级别）换成 ``pairs`` 给出的值之后的世界。"""
    return replace(world, people=tuple(
        replace(person, rows=tuple(
            replace(row, role=pairs[(pi, ri)][0], level=pairs[(pi, ri)][1], expect=None) if (pi, ri) in pairs else row
            for ri, row in enumerate(person.rows)))
        for pi, person in enumerate(world.people)))


def _r45_from_model(world: World, steps: dict[RowKey, Step]) -> dict[RowKey, Step]:
    """按模型推导 ``steps`` 的后两列，核对写死的期望：第二次执行前的值 = 他途改成的值，否则为第一次后的值；第二次被改动的行
    第一次已有记录则保留原记录（4.5），否则新增一条。"""
    first = _model(world)
    rows = {(pi, ri): row for pi, person in enumerate(world.people) for ri, row in enumerate(person.rows)}
    before = {key: steps[key][0] or (outcome[:2] if outcome else (rows[key].role, rows[key].level))
              for key, outcome in first.items()}
    second = _model(_with_pairs(world, before))
    return {key: (steps[key][0], outcome[:2] if outcome else before[key],
                  _FIRST if first[key] is not None else ((before[key], outcome) if outcome is not None else None))
            for key, outcome in second.items()}


# ─── 往返（需求 4.6、4.9，任务 7.4） ─────────────────────────────────────────

Overrides = dict[RowKey, Pair]  # 一步他途改动：成员行键 → 改成的（项目角色，级别）
_PAIRS: tuple[Pair, ...] = tuple((role, level) for role in _PROJECT_ROLES for level in _LEVELS)  # 6 × 3 种


def _original(world: World) -> dict[RowKey, Pair]:
    """每个成员行迁移前的（项目角色，级别）。"""
    return {(pi, ri): (row.role, row.level) for pi, person in enumerate(world.people) for ri, row in enumerate(person.rows)}


def _rollback_model(world: World, steps: tuple[Overrides, ...]) -> dict[RowKey, Pair]:
    """回滚后每个成员行的（项目角色，级别），按需求 4.9 原文：有回填记录、且回滚前（项目角色，级别）仍等于记录的目标值 ⇒ 恢复为
    记录的迁移前值；其余行（没有记录的，以及已被他途改成其他值的）保持回滚前的现值。回填记录 = 第一次正向执行的被改动行
    （迁移前值，目标值），第二次正向执行不加、不改（需求 4.5、4.7）；回滚前的现值 = 正向之后的值（被改动行取目标值，其余取迁移前
    值）再依次套用 ``steps``。"""
    original, first = _original(world), _model(world)
    current = {key: outcome[:2] if outcome is not None else original[key] for key, outcome in first.items()}
    for step in steps:
        current.update(step)
    return {key: original[key] if outcome is not None and current[key] == outcome[:2] else current[key]
            for key, outcome in first.items()}


@dataclass(frozen=True)
class RoundTripCase:
    """Property 5 的一个样例：世界、正向执行次数（1 或 2）、回滚前的一步他途改动。"""

    world: World
    runs: int
    overrides: Overrides


@st.composite
def _roundtrip_cases(draw: st.DrawFn) -> RoundTripCase:
    """随机往返样例：世界同 ``_worlds``；正向执行一次或两次；约三分之一的样例没有他途改动，其余从全部成员行（有回填记录的、
    没有记录的、已删除的）中逐行约三分之二概率选中，改成的值在 6 × 3 种（项目角色，级别）中任取，另单列「迁移前值」，以及有记录
    的行的「恰为目标值」「与目标值只差一列」两支以提高命中。"""
    world = draw(_worlds())
    first, original = _model(world), _original(world)
    overrides: Overrides = {}
    if not draw(_one_in_three):
        for key in world.row_keys():
            if not draw(_two_in_three):
                continue
            options = [st.sampled_from(_PAIRS), st.just(original[key])]
            outcome = first[key]
            if outcome is not None:
                role, level = outcome[:2]
                near = [(other, level) for other in _PROJECT_ROLES if other != role]
                near += [(role, other) for other in _LEVELS if other != level]
                options += [st.just((role, level)), st.sampled_from(near)]
            overrides[key] = draw(st.one_of(*options))
    return RoundTripCase(world, draw(st.sampled_from((1, 2))), overrides)


# ─── 需求 4.9 各分支（Property 5 的显式样例，任务 7.4） ─────────────────────

_R49 = World((("P", False),), (  # 第一次正向的期望写在 Row.expect：改动 7 行（4.2 五行、4.3 两行），3 行不改不记
    _u("auditor", _s(_a("P", "manager")), rows=(_r("P", "auditor", "readonly", _pm("manager")),)),
    _u("auditor", _s(_a("P", "partner")), rows=(_r("P", "readonly", "readonly", _pm("partner")),)),
    _u("manager", _s(_a("P", "signing_partner")), rows=(_r("P", "auditor", "readonly", _pm("partner"), scoped=True),)),
    _u("auditor", _s(_a("P", "manager")), rows=(_r("P", "qc", "review", _pm("manager")),)),
    _u("partner", _s(_a("P", "项目经理")), rows=(_r("P", "auditor", "readonly", _pm("manager")),)),
    _u("auditor", _s(_a("P", "manager")), rows=(_r("P", "manager", "edit"),)),  # 已等于目标值：没有记录
    _u("auditor", _s(_a("P", "qc")), rows=(_r("P", "auditor", "readonly"),)),  # 只持质控委派：没有记录
    _u("auditor", _s(_a("P", "eqcr")), rows=(_r("P", "auditor", "edit", _eq("auditor")),)),
    _u("eqcr", _s(_a("P", "独立复核合伙人")), rows=(_r("P", "manager", "readonly", _eq("manager")),)),
    _u("auditor", _s(_a("P", "manager")), rows=(_r("P", "auditor", "readonly", deleted=True),)),  # 已删除：没有记录
), name="r4.9-rollback-branches")

# 成员行键 →（回滚前依次套用的他途改动，回滚后的（项目角色，级别））。按需求 4.9 原文写死。
_R49_STEPS: dict[RowKey, tuple[tuple[Pair, ...], Pair]] = {
    (0, 0): ((), ("auditor", "readonly")),  # 有记录且仍为目标值：恢复为迁移前值
    (1, 0): ((("manager", "review"),), ("manager", "review")),  # 有记录、被改成非目标值：保持现值
    (2, 0): ((("auditor", "edit"), ("partner", "edit")), ("auditor", "readonly")),  # 被改走后又改回目标值：恢复
    (3, 0): ((("manager", "review"),), ("manager", "review")),  # 项目角色同目标值、级别不同：保持
    (4, 0): ((("partner", "edit"),), ("partner", "edit")),  # 级别同目标值、项目角色不同：保持
    (5, 0): ((("auditor", "readonly"),), ("auditor", "readonly")),  # 没有记录（迁移时已等于目标值）、被他途改动：保持
    (6, 0): ((("manager", "edit"),), ("manager", "edit")),  # 没有记录、被改成经理的目标形态：保持
    (7, 0): ((), ("auditor", "edit")),  # 需求 4.3 的行未被改动：恢复为迁移前值
    (8, 0): ((("manager", "edit"),), ("manager", "edit")),  # 需求 4.3 的行被改动（项目角色同、级别不同）：保持
    (9, 0): ((("partner", "edit"),), ("partner", "edit")),  # 已删除的成员行（没有记录）被他途改动：保持
}


def _r49_steps() -> tuple[Overrides, ...]:
    """``_R49_STEPS`` 第一列展开成依次执行的他途改动：第 i 步改每行序列里的第 i 个值。"""
    depth = max(len(seq) for seq, _ in _R49_STEPS.values())
    return tuple({key: seq[i] for key, (seq, _) in _R49_STEPS.items() if len(seq) > i} for i in range(depth))


# ─── 执行语义与角色映射对账（需求 4.1、4.10、12.7，任务 7.5） ─────────────────

_R41_MIXED = World((("P", False), ("D", True)), (  # 正向改动 3 行（4.2 两行，其一在已软删项目；4.3 一行），另 3 行不改不记
    _u("auditor", _s(_a("P", "manager")), rows=(_r("P", "auditor", "readonly", _pm("manager"), scoped=True),)),
    _u("qc", _s(_a("D", "合伙人")), rows=(_r("D", "readonly", "readonly", _pm("partner")),)),
    _u("partner", _s(_a("P", "独立复核合伙人")), rows=(_r("P", "manager", "edit", _eq("manager")),)),
    _u("auditor", _s(_a("P", "signing_partner")), rows=(_r("P", "partner", "edit"),)),  # 已等于目标值：没有记录
    _u("auditor", _s(_a("P", "qc")), rows=(_r("P", "auditor", "readonly"),)),  # 只持质控委派
    _u("auditor", _s(_a("P", "manager")), rows=(_r("P", "qc", "review", deleted=True),)),  # 已删除的成员行
), name="r4.1-changed-and-unchanged-rows")

_R41_NOOP = World((("P", False), ("D", True)), (  # 正向不改任何行（回填记录表建出且为空）；前 4 行持别名委派、已在目标值上
    _u("auditor", _s(_a("P", "manager")), rows=(_r("P", "manager", "edit"),)),
    _u("auditor", _s(_a("D", "signing_partner")), rows=(_r("D", "partner", "edit", scoped=True),)),
    _u("auditor", _s(_a("P", "eqcr")), rows=(_r("P", "auditor", "review"),)),
    _u("eqcr", _s(_a("P", "partner")), _s(_a("P", "独立复核合伙人")), rows=(_r("P", "partner", "review"),)),
    _u("auditor", _s(_a("P", "Manager")), rows=(_r("P", "auditor", "readonly"),)),  # 大小写变体：按未登记处理
    _u("auditor", _s(_a("P", "manager"), deleted=True), rows=(_r("P", "auditor", "readonly"),)),  # 人员库记录已删
    _u("auditor", _s(_a("P", "manager")), rows=(_r("P", "auditor", "readonly", deleted=True),)),  # 已删除的成员行
), name="r4.1-nothing-to-backfill")

# 需求 4.10 正向失败：预建与回填记录表同名、结构不同的表（含一行）；V 的建表语句因 IF NOT EXISTS 跳过，随后的 INSERT 列名解析失败
_CONFLICT_ID = "5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1eff"
_CONFLICT_NOTE = "预建的不兼容同名表"
_CONFLICTING_BACKFILL = (
    f"CREATE TABLE {BACKFILL_TABLE} (project_user_id UUID PRIMARY KEY, note TEXT NOT NULL)",
    f"INSERT INTO {BACKFILL_TABLE} (project_user_id, note) VALUES ('{_CONFLICT_ID}', '{_CONFLICT_NOTE}')",
)
_CONFLICT_ERROR = ("UndefinedColumnError", f'column "prior_role" of relation "{BACKFILL_TABLE}" does not exist')
# 需求 4.10 回滚失败：正向成功后给回填记录表建一个依赖视图；R 的 UPDATE 照常执行，其后的 DROP TABLE（不带 CASCADE）报错
_DEPENDENT_VIEW = f"{BACKFILL_TABLE}_dependent"
_BLOCK_DROP = (f"CREATE VIEW {_DEPENDENT_VIEW} AS SELECT project_user_id FROM {BACKFILL_TABLE}",)
_DROP_ERROR = ("DependentObjectsStillExistError", f"cannot drop table {BACKFILL_TABLE} because other objects depend on it")

# 需求 12.7：别名取需求 2.5 期望表（合伙人 / 经理 5 个 + EQCR 2 个），不从生产代码推导
_RECONCILE_ALIASES: tuple[str, ...] = (*sorted(_PM_ROLE), *sorted(_EQCR_ALIASES))


def _reconcile_world(alias: str) -> World:
    """需求 12.7：一名用户、一条人员库记录、该别名一条现行委派、一条 (auditor, readonly) 成员行。"""
    return World((("P", False),), (_u("auditor", _s(_a("P", alias)), rows=(_r("P", "auditor", "readonly"),)),),
                 name=f"r12.7-{alias}")
