"""生成底稿时的保留范围判定（粗裁结果的唯一读取实现）。

spec procedure-trim-generation-delegation-chain 需求 2 / ADR-3。

粗裁结果存在 ``procedure_instances``：每行一个程序，``wp_code``（缺省用 ``procedure_code``）是它对应的
底稿编码，``status`` 为 ``execute`` / ``skip`` / ``not_applicable``。生成入口（模板集生成、按编码生成、
全链生成、B60 附件、IPO 加载、跨项目模板复制、准则转换、自定义底稿）都用本模块判断某个底稿编码是否已被裁掉。

判定规则 —— **最近一级有程序行的编码决定**（与程序裁剪页面每一行显示的状态一致）：

1. 从编码本身往上逐级找母码：``B22A-4-1`` → ``B22A-4`` → ``B22A`` → ``B22``；
   ``M4A``（资本公积程序表）→ ``M4``；``G10-1`` → ``G10``（``G10`` 不是 ``G1`` 的子表）。
2. 每一级先看同码的普通程序行，再看覆盖该码的区间程序行（``D2-1至D2-4`` 展开为 D2-1~D2-4）。
3. 第一个命中的行决定结果：状态 ``skip`` / ``not_applicable`` ⇒ 已裁；``execute`` ⇒ 保留。
   同一级多行冲突时 ``execute`` 优先（用户在页面上看到的是「执行」）。
4. 实质性程序循环（D~N）的科目母码：本身和各级母码都没有程序行、但有下级程序行（普通行或区间行的成员）
   ⇒ 跟随下级：下级程序行全部已裁才算已裁（spec trim-generation-plan-linkage R4）。``D2`` 应收账款审定表
   只有 ``D2-1至D2-4`` / ``D2-5`` / ``D2-6至D2-13`` 三条下级程序行，三条都裁掉时审定表也不再生成；
   B / C / A / S 不用这条（计划类文档不能因为附表被裁就整份裁掉）。只对母码本身生效，不传给它没有
   程序行的其他下级；按普通编码处理的不合法区间（``F1-5至F2-9``）不算任何编码的下级。
5. 一直找不到程序行 ⇒ 保留（程序库没覆盖的底稿不受粗裁影响）。

所以裁掉 ``H3``（投资性房地产）会连带 ``H3-1``~``H3-6`` 与 ``H3A``；而 ``A1`` 被裁时，自己有程序行且为
「执行」的 ``A1-11`` 仍然保留。

读取失败抛 :class:`TrimScopeUnavailable`，生成入口一律停止生成（fail-closed）—— 此前全链生成在读取失败时
跳过过滤、照样整套生成，被裁掉的底稿又回来了。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.procedure_task_transition_service import SCOPE_TRIMMED_STATUSES

#: 区间程序行的分隔符（``D2-6至D2-13``）。
RANGE_SEPARATOR = "至"
#: 单个区间最多展开的编码数（防御异常数据，真实区间最长 14 个）。
MAX_RANGE_SPAN = 200
#: ``IN (...)`` 分批大小。
_IN_CHUNK = 500

_RANGE_LEFT = re.compile(r"^(.*-)(\d+)$")
_RANGE_RIGHT_BARE = re.compile(r"^\d+$")

#: 母码跟随下级程序行的循环（科目余额驱动的实质性程序循环，与程序裁剪页 DATA_DRIVEN_CYCLES 同一集合）。
SUBSTANTIVE_CYCLES = frozenset("DEFGHIJKLMN")

TRIM_SCOPE_UNAVAILABLE = "trim_scope_unavailable"
TRIM_SCOPE_UNAVAILABLE_MESSAGE = "无法读取程序裁剪结果，已停止生成底稿，请稍后重试"
#: 粗裁状态与底稿生命周期共锁的 advisory namespace（``PS`` = Procedure Scope）。
_PROCEDURE_SCOPE_LOCK_NAMESPACE = 0x5053


class TrimScopeUnavailable(RuntimeError):
    """粗裁结果读不到（库错误 / 事务已中止）。生成入口据此停止，不得按「没有裁剪」继续。"""

    def http_detail(self) -> dict:
        return {"error": TRIM_SCOPE_UNAVAILABLE, "message": TRIM_SCOPE_UNAVAILABLE_MESSAGE}


async def lock_project_procedure_scope(db: AsyncSession, project_id: UUID) -> None:
    """串行化同一项目的粗裁状态变更与底稿创建（事务结束自动释放）。

    生成若在读 scope 后与粗裁并发提交，会留下「已裁剪但仍在用」的底稿；两条下级程序并发裁剪也会各自
    看见另一条仍执行，漏回收母码审定表。所有生成入口经 :func:`plan_generation` 取本锁；粗裁 apply、
    初始化与自定义程序变更也取同一把锁。SQLite 测试库跳过。
    """
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        await db.execute(
            sa.text("SELECT pg_advisory_xact_lock(:ns, hashtext(:key))"),
            {"ns": _PROCEDURE_SCOPE_LOCK_NAMESPACE, "key": f"procedure_scope:{project_id}"},
        )


def normalize_code(code: str | None) -> str:
    """去首尾空白、英文字母转大写；空值返回空串。"""
    return (code or "").strip().upper()


def expand_range_code(code: str | None) -> list[str]:
    """区间编码展开：``D2-1至D2-4`` → ``[D2-1, D2-2, D2-3, D2-4]``；右侧可省略前缀（``D2-6至13``）。

    非区间码、两侧前缀不一致、终点小于起点或跨度超过 :data:`MAX_RANGE_SPAN` 返回 ``[]``。
    """
    text = (code or "").strip()
    if RANGE_SEPARATOR not in text:
        return []
    left, _, right = text.partition(RANGE_SEPARATOR)
    left, right = left.strip(), right.strip()
    m_left = _RANGE_LEFT.match(left)
    if not m_left:
        return []
    prefix, start = m_left.group(1), int(m_left.group(2))
    m_right = _RANGE_LEFT.match(right)
    if m_right:
        if m_right.group(1) != prefix:
            return []
        end = int(m_right.group(2))
    elif _RANGE_RIGHT_BARE.match(right):
        end = int(right)
    else:
        return []
    if end < start or end - start + 1 > MAX_RANGE_SPAN:
        return []
    return [f"{prefix}{n}" for n in range(start, end + 1)]


def code_lineage(code: str | None) -> list[str]:
    """编码本身 + 各级母码（由近到远）：``B22A-4-1`` → ``[B22A-4-1, B22A-4, B22A, B22]``。

    断点有两种：``-`` 之前（``D2-1`` → ``D2``），以及数字后面紧跟非数字之前（``M4A`` → ``M4``、
    ``B5附件`` → ``B5``、``D2-1A`` → ``D2-1``）。数字与数字之间不是断点：``G10`` 不是 ``G1`` 的子表。
    """
    text = normalize_code(code)
    if not text:
        return []
    out = [text]
    for i in range(len(text) - 1, 0, -1):
        prev, nxt = text[i - 1], text[i]
        if nxt == "-" or (prev.isdigit() and not nxt.isdigit()):
            parent = text[:i].rstrip("-")
            if parent and parent != out[-1]:
                out.append(parent)
    return out


def _merge(target: dict[str, bool], code: str, trimmed: bool) -> None:
    # 同一编码多行：任一行「执行」即保留（与页面显示一致）
    target[code] = target.get(code, True) and trimmed


@dataclass(frozen=True, eq=False)
class TrimmedScope:
    """一个项目的粗裁结果快照。``exact`` / ``ranged`` / ``ranges`` 的值都是「是否已裁」。

    ``ranged_from``：区间成员 → 包含它的区间程序行编码（决定者回报区间行本身，如 ``D2-7`` → ``D2-6至D2-13``）。
    ``children``：母码 → 它下级的程序行编码（普通行按编码谱系、区间行按成员的谱系登记；按编码字符串升序），
    只供实质性循环母码跟随下级（规则 4）使用。
    """

    exact: Mapping[str, bool] = field(default_factory=lambda: MappingProxyType({}))
    ranged: Mapping[str, bool] = field(default_factory=lambda: MappingProxyType({}))
    ranges: Mapping[str, bool] = field(default_factory=lambda: MappingProxyType({}))
    ranged_from: Mapping[str, tuple[str, ...]] = field(default_factory=lambda: MappingProxyType({}))
    children: Mapping[str, tuple[str, ...]] = field(default_factory=lambda: MappingProxyType({}))

    @classmethod
    def from_rows(cls, rows: Iterable[tuple[str | None, str | None]]) -> "TrimmedScope":
        """由 ``(编码, 状态)`` 行构建；编码为区间码时同时登记展开后的每个成员。"""
        exact: dict[str, bool] = {}
        ranged: dict[str, bool] = {}
        ranges: dict[str, bool] = {}
        ranged_from: dict[str, set[str]] = {}
        children: dict[str, set[str]] = {}

        def _register_child(row_code: str, member: str) -> None:
            for parent in code_lineage(member)[1:]:
                children.setdefault(parent, set()).add(row_code)

        for raw_code, status in rows:
            code = normalize_code(raw_code)
            if not code:
                continue
            trimmed = (status or "").strip().lower() in SCOPE_TRIMMED_STATUSES
            members = expand_range_code(code)
            if members:
                _merge(ranges, code, trimmed)
                for member in members:
                    _merge(ranged, normalize_code(member), trimmed)
                    ranged_from.setdefault(normalize_code(member), set()).add(code)
                    _register_child(code, normalize_code(member))
            else:
                _merge(exact, code, trimmed)
                # 不合法区间（两侧前缀不一致等）按普通编码判定，但不算任何编码的下级：
                # 它的谱系是字符串切出来的（F1-5至F2-9 → F1-5至F2 / F1-5 / F1），并不是真实的母码。
                if RANGE_SEPARATOR not in code:
                    _register_child(code, code)
        return cls(
            MappingProxyType(exact), MappingProxyType(ranged), MappingProxyType(ranges),
            MappingProxyType({m: tuple(sorted(c)) for m, c in ranged_from.items()}),
            MappingProxyType({p: tuple(sorted(c)) for p, c in children.items()}),
        )

    @property
    def trimmed_codes(self) -> frozenset[str]:
        """被标为已裁的程序行编码（普通码 + 区间码原文）。"""
        return frozenset(c for c, t in self.exact.items() if t) | frozenset(
            c for c, t in self.ranges.items() if t
        )

    def _row_trimmed(self, row_code: str) -> bool:
        """一条程序行自己的状态（普通行 / 区间行原文）。"""
        if row_code in self.exact:
            return self.exact[row_code]
        return self.ranges.get(row_code, False)

    def _decide(self, wp_code: str | None) -> tuple[str, bool, str] | None:
        """``(决定者, 是否已裁, 来源)``，来源 ``range`` / ``lineage`` / ``children``；没有程序行覆盖时 ``None``。"""
        code = normalize_code(wp_code)
        if not code:
            return None
        if code in self.ranges:
            return code, self.ranges[code], "range"
        members = expand_range_code(code)
        if members:
            # 区间编码（模板集里存在这种底稿）：成员全部已裁才算裁掉
            verdicts = [self.decided_by(m) for m in members]
            if verdicts and all(v is not None and v[1] for v in verdicts):
                return verdicts[0][0], True, "range"  # type: ignore[index]
            return None if all(v is None for v in verdicts) else (code, False, "range")
        for level in code_lineage(code):
            if level in self.exact:
                return level, self.exact[level], "lineage"
            if level in self.ranged:
                # 同一成员可能落在多个重叠区间里；execute 优先合并后，代表决定者必须来自与合并结论一致的来源。
                # 原先无条件取排序第一条，会出现「结论=执行、回报的决定者却是裁剪行」。
                trimmed = self.ranged[level]
                sources = self.ranged_from.get(level) or (level,)
                owner = next((source for source in sources if self._row_trimmed(source) == trimmed), sources[0])
                return owner, trimmed, "lineage"
        kids = self.children.get(code) if code[:1] in SUBSTANTIVE_CYCLES else None
        if kids:
            # 规则 4：下级全部已裁才算已裁；决定者 = 第一条与结论一致的下级行（按编码升序，两端实现结果一致）
            trimmed = all(self._row_trimmed(k) for k in kids)
            owner = next(k for k in kids if self._row_trimmed(k) == trimmed)
            return owner, trimmed, "children"
        return None

    def decided_by(self, wp_code: str | None) -> tuple[str, bool] | None:
        """返回 ``(决定该编码的程序行编码, 是否已裁)``；没有任何程序行覆盖时返回 ``None``。"""
        verdict = self._decide(wp_code)
        return (verdict[0], verdict[1]) if verdict else None

    def follows_children(self, wp_code: str | None) -> bool:
        """该编码是不是按规则 4 跟随下级程序行（实质性循环的科目母码，如 ``D2`` 审定表）。"""
        verdict = self._decide(wp_code)
        return bool(verdict and verdict[2] == "children")

    def deciders(self, wp_code: str | None) -> tuple[str, ...]:
        """参与决定该编码的全部程序行（与各行当前状态无关）。

        同码普通行优先时只有该行；重叠区间返回最近层级的全部区间来源；区间型底稿返回各成员来源并集；
        跟随下级的母码返回全部下级行。联动回收 / 恢复必须用完整集合，不能只用当前结论的代表决定者。
        """
        code = normalize_code(wp_code)
        if not code:
            return ()
        if code in self.ranges:
            return (code,)
        members = expand_range_code(code)
        if members:
            return tuple(sorted({source for member in members for source in self.deciders(member)}))
        for level in code_lineage(code):
            if level in self.exact:
                return (level,)
            if level in self.ranged:
                return self.ranged_from.get(level) or (level,)
        kids = self.children.get(code) if code[:1] in SUBSTANTIVE_CYCLES else None
        return kids or ()

    def is_trimmed(self, wp_code: str | None) -> bool:
        verdict = self.decided_by(wp_code)
        return bool(verdict and verdict[1])

    def trim_owner(self, wp_code: str | None) -> str | None:
        """已裁时返回决定它的程序行编码（如 ``H3-2`` → ``H3``），否则 ``None``。"""
        verdict = self.decided_by(wp_code)
        return verdict[0] if verdict and verdict[1] else None

    def split(self, codes: Sequence[str]) -> tuple[list[str], list[str]]:
        """按输入顺序拆成 ``(保留, 已裁)``。"""
        kept: list[str] = []
        trimmed: list[str] = []
        for code in codes:
            (trimmed if self.is_trimmed(code) else kept).append(code)
        return kept, trimmed

    def decide(self, wp_code: str) -> dict:
        """单码判定（契约 trimmed-scope ``$defs/decision``）：``wp_code`` 原样回填，没有程序行覆盖时 ``decided_by`` 为 None。"""
        verdict = self.decided_by(wp_code)
        return {"wp_code": wp_code, "decided_by": verdict[0] if verdict else None,
                "trimmed": bool(verdict and verdict[1])}

    def to_payload(self) -> dict:
        """快照规范形（契约 docs/contracts/procedure-chain/trimmed-scope.schema.json）：编码 → 是否已裁，键排序。"""
        return {"exact": dict(sorted(self.exact.items())), "ranges": dict(sorted(self.ranges.items()))}


def scope_decision_revision(scope: TrimmedScope, codes: Sequence[str]) -> str:
    """本次编码集合真正影响生成的裁剪布尔判定摘要。

    决定者或无关程序行变化但每个所选编码的最终裁剪结论不变时不制造假 stale；新增/恢复/裁剪任何
    会改变生成集合的行都会改变摘要。编码先规范化、去重、排序，调用顺序不影响 revision。
    """
    payload = [
        {"wp_code": code, "trimmed": scope.is_trimmed(code)}
        for code in sorted({normalize_code(code) for code in codes if normalize_code(code)})
    ]
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


async def load_trimmed_scope(db: AsyncSession, project_id: UUID) -> TrimmedScope:
    """读取项目的粗裁结果。读取失败抛 :class:`TrimScopeUnavailable`（调用方不得按「无裁剪」继续）。"""
    from app.models.procedure_models import ProcedureInstance

    stmt = sa.select(
        sa.func.coalesce(ProcedureInstance.wp_code, ProcedureInstance.procedure_code),
        ProcedureInstance.status,
    ).where(
        ProcedureInstance.project_id == project_id,
        ProcedureInstance.is_deleted == sa.false(),
    )
    try:
        async with db.begin_nested():
            rows = (await db.execute(stmt)).all()
    except SQLAlchemyError as exc:
        raise TrimScopeUnavailable(f"读取程序裁剪结果失败：{exc}") from exc
    return TrimmedScope.from_rows((r[0], r[1]) for r in rows)


async def wp_index_states(
    db: AsyncSession, project_id: UUID, codes: Iterable[str]
) -> dict[str, bool]:
    """``{编码: 是否已软删}``，只含本项目已有 ``wp_index`` 行的编码。

    ``uq_wp_index_project_code (project_id, wp_code)`` 不含 ``is_deleted`` ⇒ 同码只会有一行；
    软删的行只能从回收站恢复，不能再新建同码底稿。
    """
    from app.models.workpaper_models import WpIndex

    wanted = sorted({c for c in codes if c})
    states: dict[str, bool] = {}
    for i in range(0, len(wanted), _IN_CHUNK):
        chunk = wanted[i:i + _IN_CHUNK]
        rows = await db.execute(
            sa.select(WpIndex.wp_code, WpIndex.is_deleted).where(
                WpIndex.project_id == project_id, WpIndex.wp_code.in_(chunk)
            )
        )
        states.update({code: bool(deleted) for code, deleted in rows.all()})
    return states


async def recycled_codes(db: AsyncSession, project_id: UUID, codes: Iterable[str]) -> set[str]:
    """``codes`` 中底稿已在回收站（``wp_index`` 软删）的编码。"""
    return {c for c, deleted in (await wp_index_states(db, project_id, codes)).items() if deleted}


@dataclass
class GenerationPlan:
    """一次生成的分流结果（各列表保持输入顺序）。"""

    to_create: list[str]
    skipped_trimmed_codes: list[str]
    in_recycle_codes: list[str]
    existing_codes: list[str]
    scope: TrimmedScope

    def receipt(self) -> dict[str, list[str]]:
        return {
            "skipped_trimmed_codes": list(self.skipped_trimmed_codes),
            "in_recycle_codes": list(self.in_recycle_codes),
        }

    def to_payload(self) -> dict[str, list[str]]:
        """四类分流（契约 generation-plan.schema.json），各列表保持输入顺序。"""
        return {
            "to_create": list(self.to_create),
            "skipped_trimmed_codes": list(self.skipped_trimmed_codes),
            "in_recycle_codes": list(self.in_recycle_codes),
            "existing_codes": list(self.existing_codes),
        }


async def plan_generation(
    db: AsyncSession,
    project_id: UUID,
    codes: Sequence[str],
    *,
    scope: TrimmedScope | None = None,
) -> GenerationPlan:
    """把待生成编码分成：要新建 / 已被粗裁 / 在回收站 / 已存在。

    已被粗裁优先于其他三类（被裁的编码不查库、也不报「在回收站」）。``scope`` 不传时现读，读不到抛
    :class:`TrimScopeUnavailable`。
    """
    await lock_project_procedure_scope(db, project_id)
    # ``scope`` 只曾用于同事务内复用；锁在本函数里取得后必须现读，不能信任调用方在取锁前读到的旧快照。
    # 保留参数仅为兼容既有调用签名。
    scope = await load_trimmed_scope(db, project_id)
    kept, trimmed = scope.split(list(codes))
    states = await wp_index_states(db, project_id, kept)
    to_create: list[str] = []
    in_recycle: list[str] = []
    existing: list[str] = []
    for code in kept:
        state = states.get(code)
        if state is None:
            to_create.append(code)
        elif state:
            in_recycle.append(code)
        else:
            existing.append(code)
    return GenerationPlan(to_create, trimmed, in_recycle, existing, scope)


def describe_skips(plan_receipt: Mapping[str, Sequence[str]], *, max_listed: int = 10) -> str:
    """回执提示文字（为空表示没有跳过项）：``3 个编码已在程序裁剪中标为不执行，未生成：H3、H3-1、M4A``。"""

    def _codes(items: Sequence[str]) -> str:
        shown = "、".join(items[:max_listed])
        return shown + (" 等" if len(items) > max_listed else "")

    parts: list[str] = []
    trimmed = list(plan_receipt.get("skipped_trimmed_codes") or [])
    recycled = list(plan_receipt.get("in_recycle_codes") or [])
    if trimmed:
        parts.append(f"{len(trimmed)} 个编码已在程序裁剪中标为不执行，未生成：{_codes(trimmed)}")
    if recycled:
        parts.append(f"{len(recycled)} 个编码的底稿在回收站中，请从回收站恢复：{_codes(recycled)}")
    return "；".join(parts)
