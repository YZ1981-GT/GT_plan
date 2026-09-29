"""Task 6.7 判据：**Property 11** —— 回滚快照可完整还原（round-trip）。

spec: workpaper-sync-adopt-overwrite-and-refresh-source
Requirements 6.9 · design § Correctness Properties / Property 11

Requirement 6.9 逐字：「THE 回滚快照 SHALL 足以恢复被覆盖 item 的原始载荷（**含被删除的行**）」。
design Property 11 逐字：「执行覆盖后以 `rollback_snapshot` 还原，还原结果应与覆盖前的原始载荷
相等（含被删除的行）」。

═══ 判据是**真还原一遍再比载荷**，不是「键在不在」 ═══

既有 Task 6.5 判据（`test_aos_audit_details_and_rollback_snapshot.py` §5）比的是「快照里有这个键
且值等于覆盖前原值」—— 那是**例子级**的完整性。本文件补的是 round-trip：把快照真的盖回去，
再与覆盖前的载荷逐项比。四档违规，逐档独立归因（判据越细，变异反证才指得准）：

| 档 | 含义 | 它是谁的盲区 |
| --- | --- | --- |
| R1 | item 被覆盖改写过，却**不在**快照覆盖面里 | 覆盖面塌成单一口径（被跳过的 item 当场丢） |
| R2 | 还原后**身份集合**不等（被删除的行没回来） | 「只比键集合」的判据看不见 |
| R3 | 身份都回来了但**行内字段**不是覆盖前的值 | 「只比身份集合」的判据看不见 |
| R4 | 身份与字段都对，但**字节**不等（重序列化漂移） | 「语义相等」的判据看不见 |

🔴 **R2 与 R3 合起来才是 Requirement 6.9 的「含被删除的行」**：被删的行既要**在**，其字段也要是
覆盖前那一份。另有一条专用判据 `judge_deleted_rows_are_back` 把这件事单独说一遍并点名身份 ——
它配的是**篡改反证**（把快照里某个被删行抠掉：只比键集合的判据会放过，本判据打红）。

🔴 **R4 = 字节精确档，实测结论：生产**是**字节精确的**。`rollback_snapshot` 存的就是
`before_snapshot` 里那一份原始 `remark` 串（`_record_rollback_and_audit` 的
`rollback_payload = {item: before_snapshot.get(item) …}`，中间没有任何 `json.loads`/`dumps`
往返），所以还原是逐字节复原 —— 包括前端写进去的**紧凑**分隔符形态。这不是理论推断：
`TestByteExactness` 里 R-M2 变异（在存快照那一步插一次 `json.loads`→`json.dumps` 往返）会让
**只有 R4** 打红而 R2 / R3 全过 ⇒ 字节档与语义档真的分得开，且生产落在字节档这一侧。

🔴 **被跳过的 item 在覆盖面里**（Task 6.5 把覆盖面做成「plan 口径 ∪ 字节差集」的并集正是为它）：
`TestSkippedItemIsInScopeOfTheRoundTrip` 正面断言它被还原，R-M1 变异（并集塌成 plan 一半）
让 R1 打红 —— 同一个生产锚点在 6.5 那边配的是「键在不在」的判据，这边配的是 round-trip
**内容**判据，两处判据不同故不是重复。

═══ 共用件 ═══

🔴 「跑一遍覆盖」的脚手架**只有一份**，在 `test_aos_property_apply_convergence.py`（Task 6.6）：
`Scenario` / `CORPUS` / `run_overwrite_once` / `merge_simulator` / `identities_of`。审计侧脚手架
（`_AuditSession` / `_record`）来自 `test_aos_audit_details_and_rollback_snapshot.py`（Task 6.5）。
两处都**只 import 不另造第二份**，且用**顶层模块名** —— 该目录无 `__init__.py`、pytest 走
`prepend`；写成 `tests.workpaper_sync.…` 会拿到第二个模块实例，`Scenario` / `CORPUS` 当场分家。

🔴 **变异一律进程内源码级**（`_source_mutant`：`inspect.getsource` → 换**唯一**锚点 → 在生产模块
`globals` 的**副本**里 `exec`），生产文件一字不改，也不用 `monkeypatch.setattr`（本域有并发会话）。
"""

from __future__ import annotations

import json
from typing import Any, Mapping

import pytest
from hypothesis import example, given, settings

from app.services.workpaper_sync import adopt_overwrite_apply as AOA
from app.services.workpaper_sync import adopt_substrate_response as ASR

from test_aos_adopt_plan_wiring import _IDENTITY_KEY, _source_mutant  # noqa: E402
from test_aos_audit_details_and_rollback_snapshot import _record  # noqa: E402
from test_aos_property_apply_convergence import (  # noqa: E402
    BLIND,
    BLIND_BEFORE,
    CORPUS,
    ITEM,
    NAME_FIELD,
    Overwritten,
    Scenario,
    _STORE_NAME,
    identities_of,
    run_overwrite_once,
    scenarios,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 覆盖 → 留存快照 → 还原
# ═══════════════════════════════════════════════════════════════════════════════


def rollback_coverage(run: Overwritten, *, items_fn: Any = None) -> list[str]:
    """回滚快照的覆盖面 = **生产的**两口径并集（Requirement 6.9）。

    :param items_fn: 变异体入口（默认 `AOA.rollback_snapshot_items`）。
    """
    return (items_fn or AOA.rollback_snapshot_items)(
        plan_changed=AOA.changed_items_from_plan(run.applied.plan),
        snapshot_changed=ASR._diff_snapshots(dict(run.before), dict(run.final)),
    )


def snapshot_of(
    run: Overwritten, *, items_fn: Any = None, record_fn: Any = None
) -> dict[str, str | None]:
    """真跑 `_record_rollback_and_audit`（或其变异体），从**审计 payload** 里取出回滚快照。

    🔴 刻意取自 payload 而不是「我自己拼一份」：Requirement 6.7 要的是「业务变更 + 回滚快照 +
    审计」同事务，快照的**权威副本**就住在审计 details 里。自己拼一份会把「拼得对」当成
    「存进去了」（Task 6.5 §4 的同一条理由）。
    """
    details = _record(
        applied=run.applied,
        before_snapshot=dict(run.before),
        changed_items=AOA.changed_items_from_plan(run.applied.plan),
        rollback_items=rollback_coverage(run, items_fn=items_fn),
        record_fn=record_fn,
    )
    return dict(json.loads(str(details.get("rollback_snapshot") or "{}")))


def restore(run: Overwritten, snapshot: Mapping[str, str | None]) -> dict[str, str | None]:
    """把快照盖回**覆盖之后**的库状态上 —— 这就是运维照着审计轨迹回滚时会做的事。

    🔴 起点是 `run.final`（覆盖后）而不是 `run.before`：从 before 起还原是自证循环。
    """
    restored = dict(run.final)
    restored.update(snapshot)
    return restored


def _rows_by_id(payload: str | None) -> dict[str, dict[str, Any]]:
    if payload is None:
        return {}
    return {str(row[_IDENTITY_KEY]): dict(row) for row in json.loads(payload)}


def _original_row(identity: str) -> dict[str, str]:
    """覆盖前那一行的**完整**字段（`_store_payload` 的构造，本文件不另写一份字面量）。"""
    return {_IDENTITY_KEY: identity, NAME_FIELD: _STORE_NAME.format(identity)}


# ═══════════════════════════════════════════════════════════════════════════════
# 判据：四档 round-trip + 「含被删除的行」专用判据
# ═══════════════════════════════════════════════════════════════════════════════


def _tier(item: str, *, want: str | None, got: str | None) -> str:
    """把一处不等归到 R2 / R3 / R4 三档之一（越靠后的档越细，只有前面几档都过才会落到它）。"""
    if item == ITEM:
        want_ids, got_ids = identities_of(want), identities_of(got)
        if set(want_ids) != set(got_ids):
            return (
                f"R2 破：{item} 还原后身份集合不等 —— 没回来 "
                f"{sorted(set(want_ids) - set(got_ids))}（Requirement 6.9 的「含被删除的行」）、"
                f"多出 {sorted(set(got_ids) - set(want_ids))}"
            )
        if _rows_by_id(want) != _rows_by_id(got):
            differing = sorted(
                i for i, row in _rows_by_id(want).items() if _rows_by_id(got).get(i) != row
            )
            return f"R3 破：{item} 身份都回来了但这些行的字段不是覆盖前的值：{differing}"
        if want_ids != got_ids:
            return f"R3 破：{item} 行**顺序**没还原（{got_ids} vs {want_ids}）"
        return f"R4 破：{item} 语义相等但字节不等（重序列化漂移）：{got!r} vs {want!r}"
    if json.loads(str(want)) != json.loads(str(got)):
        return f"R3 破：{item} 的载荷内容没还原（实得 {got!r}，应为 {want!r}）"
    return f"R4 破：{item} 语义相等但字节不等（重序列化漂移）：{got!r} vs {want!r}"


def judge_roundtrip(
    run: Overwritten,
    *,
    snapshot: Mapping[str, str | None],
    restored: Mapping[str, str | None],
) -> list[str]:
    """Property 11：还原结果必须与**覆盖前的原始载荷**逐项相等（模块 docstring 的 R1~R4）。"""
    violations: list[str] = []
    original = dict(run.before)
    for item in sorted(set(original) | set(restored)):
        want, got = original.get(item), restored.get(item)
        if want == got:
            continue
        if str(run.final.get(item)) != str(want) and item not in snapshot:
            violations.append(
                f"R1 破：{item} 被本次覆盖改写过却不在 rollback_snapshot 里 —— 它的原值再也拿"
                "不回来（Requirement 6.9）"
            )
            continue
        violations.append(_tier(item, want=want, got=got))
    return violations


def judge_deleted_rows_are_back(
    run: Overwritten, restored: Mapping[str, str | None]
) -> list[str]:
    """Requirement 6.9 逐字的「**含被删除的行**」—— 单独说一遍并点名身份。

    🔴 判据是**行内容**不是键集合：被删的行要回来，且其字段必须是覆盖前那一份
    （只比身份集合会放过「回来了但内容被换成 substrate 值」这一类）。
    """
    deleted = set(run.applied.rows_deleted_by_item.get(ITEM, ()))
    rows = _rows_by_id(restored.get(ITEM))
    violations: list[str] = []
    for identity in sorted(deleted):
        if identity not in rows:
            violations.append(f"D 破：被删除的行 {identity!r} 没回来（键在不算，行必须在）")
        elif rows[identity] != _original_row(identity):
            violations.append(
                f"D 破：{identity!r} 回来了但字段不是覆盖前的原值 —— 实得 {rows[identity]!r}，"
                f"应为 {_original_row(identity)!r}"
            )
    return violations


def _key_set_only_judge(
    run: Overwritten, restored: Mapping[str, str | None]
) -> list[str]:
    """🔴 **对照判据**（刻意弱）：只比 item 键集合 + 行身份键是否都在场。

    它存在的唯一目的是证明上面两条判据**比它强** —— 变异 / 篡改之下它会全绿而它们打红。
    """
    deleted = set(run.applied.rows_deleted_by_item.get(ITEM, ()))
    present = set(identities_of(restored.get(ITEM)))
    missing_items = sorted(set(run.before) - set(restored))
    return [f"弱判据：item {missing_items} 不在还原结果里"] if missing_items else (
        [] if deleted <= present else ["弱判据：被删身份的键没回来"]
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Property 11 本体
# ═══════════════════════════════════════════════════════════════════════════════


def roundtrip(run: Overwritten) -> tuple[dict[str, str | None], dict[str, str | None]]:
    snapshot = snapshot_of(run)
    return snapshot, restore(run, snapshot)


class TestProperty11RollbackRoundTrip:
    """**Property 11: 回滚快照可完整还原（round-trip）**

    **Validates: Requirements 6.9**
    """

    @settings(max_examples=5, deadline=None)
    @given(scenarios())
    @example(CORPUS[0])
    @example(CORPUS[1])
    @example(CORPUS[2])
    @example(CORPUS[3])
    @example(CORPUS[4])
    @example(CORPUS[5])
    @example(CORPUS[6])
    def test_restoring_the_snapshot_yields_the_original_payload(
        self, scenario: Scenario
    ) -> None:
        run = run_overwrite_once(scenario)
        assert run.mismatches == [], f"{scenario.label}：生产复读比对先打红了 {run.mismatches}"
        snapshot, restored = roundtrip(run)
        assert judge_roundtrip(run, snapshot=snapshot, restored=restored) == [], scenario.label
        assert judge_deleted_rows_are_back(run, restored) == [], scenario.label
        # 🔴 最强形态一并钉死：还原结果与覆盖前**整体逐字节相等**（不是逐项近似）
        assert restored == dict(run.before), scenario.label

    @pytest.mark.parametrize("scenario", CORPUS, ids=[s.label for s in CORPUS])
    def test_corpus_member_round_trips(self, scenario: Scenario) -> None:
        """语料逐条单独跑，便于定位是哪一条红（四类非平凡性的普查在 6.6 那份文件里）。"""
        run = run_overwrite_once(scenario)
        snapshot, restored = roundtrip(run)
        assert judge_roundtrip(run, snapshot=snapshot, restored=restored) == []
        assert judge_deleted_rows_are_back(run, restored) == []

    def test_deleted_rows_really_are_in_the_sample(self) -> None:
        """🔴 反空转：语料里真的有「被删除的行」，否则 `judge_deleted_rows_are_back` 空转。

        现算：7 条语料里有 3 条真删过行，删掉的身份共 4 个。
        """
        deleted_per_scenario = [
            run_overwrite_once(s).applied.rows_deleted_by_item.get(ITEM, ()) for s in CORPUS
        ]
        nonempty = [d for d in deleted_per_scenario if d]
        assert len(nonempty) == 3, deleted_per_scenario
        assert sum(len(d) for d in nonempty) == 4, deleted_per_scenario

    def test_updated_rows_field_values_really_change_before_restore(self) -> None:
        """🔴 反空转：被更新行的字段在覆盖后**确实**变了 ⇒ R3 档不是空转。"""
        run = run_overwrite_once(CORPUS[0])
        after = _rows_by_id(run.final[ITEM])
        assert after["r1"][NAME_FIELD] != _original_row("r1")[NAME_FIELD]
        restored = restore(run, snapshot_of(run))
        assert _rows_by_id(restored[ITEM])["r1"] == _original_row("r1")


# ═══════════════════════════════════════════════════════════════════════════════
# 被跳过的 item 在 round-trip 覆盖面里（Task 6.5 的并集口径正是为它而设）
# ═══════════════════════════════════════════════════════════════════════════════

#: 并集口径的生产锚点（与 6.5 §5 的 RB-M2 / RB-M3 同一行；那边配「键在不在」判据，
#: 这边配 round-trip **内容**判据 ⇒ 判据不同，不是重复）。
_UNION_ANCHOR = (
    "return sorted({*(str(x) for x in plan_changed), *(str(x) for x in snapshot_changed)})"
)


class TestSkippedItemIsInScopeOfTheRoundTrip:
    def test_the_skipped_item_is_only_visible_to_the_byte_diff(self) -> None:
        """前提实测：被跳过的 item **只有**字节差集看得见（plan 三清单对它恒空）。"""
        run = run_overwrite_once(CORPUS[1])
        assert BLIND not in AOA.changed_items_from_plan(run.applied.plan)
        assert BLIND in ASR._diff_snapshots(dict(run.before), dict(run.final))
        assert BLIND in rollback_coverage(run)

    def test_the_skipped_item_is_restored_byte_exactly(self) -> None:
        run = run_overwrite_once(CORPUS[1])
        snapshot, restored = roundtrip(run)
        assert snapshot[BLIND] == BLIND_BEFORE
        assert restored[BLIND] == BLIND_BEFORE, "被跳过的 item 没被还原成覆盖前那一份字节"

    def test_mutant_rm1_coverage_collapsed_to_plan_only_breaks_r1(self) -> None:
        """R-M1：覆盖面塌成 plan 那一半 ⇒ 被跳过的 item 的原值丢了 ⇒ R1 打红。"""
        run = run_overwrite_once(CORPUS[1])
        mutant = _source_mutant(
            AOA.rollback_snapshot_items,
            old=_UNION_ANCHOR,
            new="return sorted({*(str(x) for x in plan_changed)})",
            module=AOA,
        )
        assert rollback_coverage(run, items_fn=mutant) == [ITEM], "变异没生效"
        snapshot = snapshot_of(run, items_fn=mutant)
        restored = restore(run, snapshot)
        got = judge_roundtrip(run, snapshot=snapshot, restored=restored)
        assert len(got) == 1 and got[0].startswith("R1 破") and BLIND in got[0], got
        # 变异生效断言：受管 item 仍还原了（红的是「少了被跳过那条」不是「整个快照没了」）
        assert judge_deleted_rows_are_back(run, restored) == []
        assert restored[ITEM] == run.before[ITEM]

    def test_the_weak_judge_would_pass_that_mutant(self) -> None:
        """🔴 对照：只比「item 键 + 被删身份键」的弱判据在 R-M1 下**全绿** ⇒ R1 档有存在必要。"""
        run = run_overwrite_once(CORPUS[1])
        mutant = _source_mutant(
            AOA.rollback_snapshot_items,
            old=_UNION_ANCHOR,
            new="return sorted({*(str(x) for x in plan_changed)})",
            module=AOA,
        )
        restored = restore(run, snapshot_of(run, items_fn=mutant))
        assert _key_set_only_judge(run, restored) == [], (
            "弱判据也打红了 ⇒ 这一例证不了 R1 档比它强，得换一个只在 R1 档可见的失效"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 字节精确 vs 语义相等（实测结论：生产**是**字节精确的）
# ═══════════════════════════════════════════════════════════════════════════════

#: 存快照那一行的生产锚点。
_PAYLOAD_ANCHOR = "rollback_payload = {item: before_snapshot.get(item) for item in rollback_items}"
#: R-M2：插一次 `json.loads` → `json.dumps` 往返 ⇒ 语义一模一样、字节漂移。
_RESERIALISE = (
    "rollback_payload = {item: json.dumps(json.loads(before_snapshot[item]), "
    "ensure_ascii=False) for item in rollback_items}"
)


def _semantic_only_judge(
    run: Overwritten, restored: Mapping[str, str | None]
) -> list[str]:
    """🔴 **对照判据**（刻意只到语义档）：逐 item 比 `json.loads` 之后的值。"""
    out: list[str] = []
    for item, want in dict(run.before).items():
        got = restored.get(item)
        if json.loads(str(want)) != json.loads(str(got)):
            out.append(f"语义判据：{item} 不等")
    return out


class TestByteExactness:
    def test_production_restores_the_exact_bytes_including_compact_separators(self) -> None:
        """🔴 实测结论：还原是**字节精确**的 —— 连前端写进去的紧凑分隔符都原样回来。

        机理（现读 `_record_rollback_and_audit`）：`rollback_payload` 直接取
        `before_snapshot.get(item)`，中间**没有任何** `json.loads`/`dumps` 往返 ⇒ 存的就是原串。
        """
        run = run_overwrite_once(CORPUS[0])
        snapshot, restored = roundtrip(run)
        assert snapshot[ITEM] == run.before[ITEM] and snapshot[BLIND] == BLIND_BEFORE
        assert restored == dict(run.before)
        # 覆盖后确实是**带空格**形态（否则「字节精确」是因为两侧同形，什么都没证到）
        assert str(run.final[ITEM]) != str(run.before[ITEM])
        assert '", "' in str(run.final[ITEM]) or '": "' in str(run.final[ITEM])
        assert '", "' not in str(restored[ITEM]) and '": "' not in str(restored[ITEM])

    def test_mutant_rm2_reserialisation_breaks_only_the_byte_tier(self) -> None:
        """R-M2：存快照时插一次 JSON 往返 ⇒ **只有 R4** 打红（R1/R2/R3 全过）。

        这一组是「字节档与语义档真的分得开」的证明，也是生产落在字节档这一侧的反证：
        同一个变异下，只到语义档的对照判据**全绿**。
        """
        run = run_overwrite_once(CORPUS[1])
        mutant = _source_mutant(
            ASR._record_rollback_and_audit, old=_PAYLOAD_ANCHOR, new=_RESERIALISE, module=ASR
        )
        snapshot = snapshot_of(run, record_fn=mutant)
        restored = restore(run, snapshot)
        got = judge_roundtrip(run, snapshot=snapshot, restored=restored)
        assert got and all(v.startswith("R4 破") for v in got), got
        assert sorted(v.split("：")[1].split(" ")[0] for v in got) == [BLIND, ITEM], got
        # 语义档对照：同一个变异下它全绿 ⇒ 判据若降级成「语义相等」就抓不到重序列化
        assert _semantic_only_judge(run, restored) == []
        # 「含被删除的行」那条也全绿（漂的是字节不是行集）
        assert judge_deleted_rows_are_back(run, restored) == []

    def test_the_reserialisation_really_changes_bytes(self) -> None:
        """变异生效断言：往返之后字节真的变了（不变则上一条什么都没在测）。"""
        assert json.dumps(json.loads(BLIND_BEFORE), ensure_ascii=False) != BLIND_BEFORE
        run = run_overwrite_once(CORPUS[1])
        original = str(run.before[ITEM])
        assert json.dumps(json.loads(original), ensure_ascii=False) != original


# ═══════════════════════════════════════════════════════════════════════════════
# 篡改反证：「含被删除的行」判据比「键集合」判据强
#
# 🔴 这一组篡改的是**快照内容**（测试侧），不是生产代码 —— 因为「快照里少了一行」这种失效在
#    现行生产实现里造不出来（快照存的是整串原值，不可能只少一行）。篡改的目的是证明**判据**
#    抓得住这类失效，不是假装生产有这个缺陷。
# ═══════════════════════════════════════════════════════════════════════════════


def _tamper_drop_row(snapshot: Mapping[str, str | None], identity: str) -> dict[str, str | None]:
    tampered = dict(snapshot)
    rows = [r for r in json.loads(str(tampered[ITEM])) if str(r[_IDENTITY_KEY]) != identity]
    tampered[ITEM] = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return tampered


def _tamper_swap_field(snapshot: Mapping[str, str | None], identity: str) -> dict[str, str | None]:
    tampered = dict(snapshot)
    rows = json.loads(str(tampered[ITEM]))
    for row in rows:
        if str(row[_IDENTITY_KEY]) == identity:
            row[NAME_FIELD] = "被换成了 substrate 侧的值"
    tampered[ITEM] = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return tampered


class TestJudgeIsStrongerThanKeySets:
    def test_dropping_a_deleted_row_from_the_snapshot_is_caught(self) -> None:
        """篡改：把快照里**被删除的那一行**抠掉 ⇒ R2 + D 打红，而弱判据全绿。"""
        run = run_overwrite_once(CORPUS[0])
        deleted = run.applied.rows_deleted_by_item[ITEM]
        assert deleted == ("r2",), deleted
        tampered = _tamper_drop_row(snapshot_of(run), "r2")
        restored = restore(run, tampered)
        got = judge_roundtrip(run, snapshot=tampered, restored=restored)
        assert len(got) == 1 and got[0].startswith("R2 破") and "'r2'" in got[0], got
        dead = judge_deleted_rows_are_back(run, restored)
        assert len(dead) == 1 and "没回来" in dead[0] and "r2" in dead[0], dead
        assert _key_set_only_judge(run, restored) != [], (
            "本例弱判据也该红（它确实只比键 —— 而 r2 的键就是没了）"
        )

    def test_dropping_an_updated_row_is_caught_while_the_weak_judge_passes(self) -> None:
        """🔴 篡改：抠掉一行**被更新**的行（不是被删的那行）⇒ R2 打红而弱判据**全绿**。

        弱判据只看「被删身份的键回来了没」⇒ 它对「其它行丢了」完全免疫。这一例才是
        「比键集合强」的决定性证据。
        """
        run = run_overwrite_once(CORPUS[0])
        tampered = _tamper_drop_row(snapshot_of(run), "r1")
        restored = restore(run, tampered)
        got = judge_roundtrip(run, snapshot=tampered, restored=restored)
        assert len(got) == 1 and got[0].startswith("R2 破") and "'r1'" in got[0], got
        assert _key_set_only_judge(run, restored) == [], (
            "弱判据也红了 ⇒ 这一例证不了「比键集合强」"
        )

    def test_swapping_a_restored_row_field_is_caught_by_the_content_tier(self) -> None:
        """篡改：身份全在、把被删行的**字段**换掉 ⇒ R3 + D 打红，弱判据与语义判据都全绿。"""
        run = run_overwrite_once(CORPUS[0])
        tampered = _tamper_swap_field(snapshot_of(run), "r2")
        restored = restore(run, tampered)
        got = judge_roundtrip(run, snapshot=tampered, restored=restored)
        assert len(got) == 1 and got[0].startswith("R3 破") and "'r2'" in got[0], got
        dead = judge_deleted_rows_are_back(run, restored)
        assert len(dead) == 1 and "字段不是覆盖前的原值" in dead[0], dead
        assert _key_set_only_judge(run, restored) == [], "弱判据该全绿（键都在）"

    def test_the_order_tier_is_reachable(self) -> None:
        """R3 的「行顺序」分支：身份与字段都对、只是顺序反了 ⇒ 仍打红（载荷是有序的）。"""
        run = run_overwrite_once(CORPUS[0])
        snapshot = dict(snapshot_of(run))
        rows = list(reversed(json.loads(str(snapshot[ITEM]))))
        snapshot[ITEM] = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        restored = restore(run, snapshot)
        got = judge_roundtrip(run, snapshot=snapshot, restored=restored)
        assert len(got) == 1 and "顺序" in got[0], got


# ═══════════════════════════════════════════════════════════════════════════════
# 指针：相邻判据在哪
# ═══════════════════════════════════════════════════════════════════════════════
#
# · **Property 7（收敛 / Task 6.6）与共用场景建造器**在
#   `test_aos_property_apply_convergence.py` —— 含四类非平凡场景的**现算普查**（反空转）、
#   merge 模拟器的保真判据、以及 design 逐字文本适用域的裁定证据。
# · 回滚快照覆盖面的**例子级**完整性（键在 + 值等于原值）与它的三组变异 RB-M1~RB-M3 →
#   `test_aos_audit_details_and_rollback_snapshot.py` §5（本文件只 import 它的 `_record`）。
# · 审计 details 追加三字段 / `event_type` 不登记 schema → 同上 §4。
# · 端点级「三者同事务」（Requirement 6.7）真发 HTTP → Task 8.x，本文件不假装覆盖它。
