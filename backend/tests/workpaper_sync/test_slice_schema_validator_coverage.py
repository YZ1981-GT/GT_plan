# -*- coding: utf-8 -*-
"""`slice_schema.validator` 的**覆盖面**判据：被点名的校验器必须真的走过每一份 slice。

spec: .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/
Requirements: 1.3, 12.1, 12.4

═══ 为什么存在这个文件 ═══

`workpaper_sync_migration_paradigm.json` 把 `slice_schema.validator` 点名成
`test_migration_paradigm_contract.py::validate_slice_against_schema` —— **一个**校验器，
**一份** schema。但那份守卫里对它的每一次调用，喂进去的都只有
`slice_schema.reference_instance`（E 循环 slice）或合成的 `{}`：`scan_glob` 命中的另外两份
slice（D / F 循环）从未被它校验过。本文件补上那个分母：`scan_glob` 命中几份就跑几条。

═══ G1（同一条 SR-3 两个判官）已收口 ═══

原始缺口：D 循环 slice 的 7 条 entry（后来 F 循环又加 8 条）是 `capability: null` +
`capability_verdict_stage`，喂给被点名的校验器报 SR-3（`capability=None` 不在
`capability_enum`），而同一条规则在 `test_task46_d_cycle_migration.py` /
`test_task48_f_cycle_migration.py` 里被**另外两份独立实现**放行 —— 严格的那个判官恰好从不
指向那两份 slice，于是「登记了」与「解决了」在报告里长得一样。

收口做法（范式 owner 侧）：`capability_enum` 的四个值**不动**（AC 1.3 原文派生），SR-3 改成
蕴含式 —— `capability` 落在枚举内 **或**（为 null 且 `required_pending_verdict_fields` 三字段
按 `pending_verdict_field_semantics` 齐备）。待裁决态由此成为范式的合法一等公民，同一份校验器
按同一强度检查 D / E / F 三份 slice，Tasks 49–57 落到同一形态时不再需要每次新增一条豁免。
实测三份 slice 违规数 0（`_UNJUDGED_SLICES` 因此清空，见下）。

🔴 2026-08-31 现状更新（Task 57）：`scan_glob` 命中的 slice 已从 3 份长到 **12 份**
（A/B/C/S+跨循环共享 / D / E / F / G / H / I / J / K / L / M / N），全部实测违规数 0，
`_UNJUDGED_SLICES` **仍为空**。分母是收集期从 `scan_glob` **现扫**的，新 slice 自动进入且
**不带**豁免标记 ⇒ 不通过即直接 FAIL。这一段只更新事实陈述，不改任何判据强度 —— 上一段里
「三份」是 G1 收口当时的数量，留着会让读者以为分母被写死成 3；同理这里的「12 份」也**不是**
判据（判据在 :func:`test_the_denominator_and_the_validator_are_both_non_vacuous` 里只要求
`>= 2`），后续任务再变时无需改这段文字之外的任何东西。
（上一轮此处写「11 份 …… 下一轮（Task 57 的 A/B/C/S）会自然再变」—— Task 57 已兑现，
它是 Wave 5 Excel lane 的收口 slice，覆盖 46 条 entry。）

第二个缺口同源：AP-1 的 `known_debt_inventory` 仍登记着那 7 条，可
`_single_onlyoffice_params()` 的分母按 `capability == "single_onlyoffice"` 过滤，7 条改裁之后
**一个 xfail 标记都不再挂在它们身上**。清单自己的 `release_condition` 承诺「届时 strict xfail
会因 XPASS 打红提醒」，而实际走的这条路（改裁成 `null`）让它们静默退出分母，一条红都没有；
`test_the_registered_debt_has_no_zombie_entries` 照旧全绿，因为它的谓词只问「entry_id 还在不
在 slice 里」，不问「这条登记还有没有承载者」。

═══ 处置：strict xfail，不用 skip ═══

范式 JSON 与两份 slice 都是本文件的**只读**约束（并发会话在改），所以这里不去改数据，只把
缺口变成**可见的红**。标记一律 `pytest.mark.xfail(strict=True)`：skip 记为通过 = fail-open，
正是要拦的东西；strict 让缺口被真正补上之后 XPASS 反过来打红，逼作者回来删登记。

解除条件逐条写在 `_UNJUDGED_SLICES` / :func:`test_every_registered_debt_entry_still_has_a_carrier`
的 reason 里。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_CONTRACT_PATH = Path(__file__).with_name("test_migration_paradigm_contract.py")

#: 已知未被 `slice_schema.validator` 校验、且校验会打红的 slice → 解除条件。
#:
#: 🔴 登记是**手写冻结**的，不是「现算哪些 slice 有违规」——后者会在缺口被补上时让标记自己
#: 消失，于是没有任何一条测试变红，作者也不会回来清理登记（那正是本文件在报的 AP-1 分母那
#: 个形态）。手写 ⇒ 补好即 XPASS(strict) 打红。新出现的 slice 若没登记又不通过校验，它的参数
#: 项没有标记 ⇒ 直接 FAIL。两个方向都咬。
#:
#: **当前为空 —— 这是 G1 收口的结果，不是登记机制失效。** 原先唯一一条（D 循环 slice 的 7 条
#: SR-3）的解除条件第 ① 项「`slice_schema` 显式接纳待裁决态」已兑现（SR-3 改成蕴含式 +
#: `required_pending_verdict_fields`），D / E / F 三份 slice 实测违规数全 0，登记必须删除 ——
#: 留着会因 `strict=True` 在 XPASS 时打红。空字典下仍有两条判据在跑：
#: :func:`test_every_slice_passes_the_json_nominated_validator` 的每个参数项都**没有**豁免标记
#: ⇒ 任何 slice（含 Tasks 49–57 新增的）不通过校验即直接 FAIL；
#: :func:`test_the_denominator_and_the_validator_are_both_non_vacuous` 保证分母与校验器不空跑。
#: 再登记的门槛不变：写清责任方 + 可兑现的解除条件，且被登记 slice 的任务号必须真的早于
#: `slice_schema.applies_to_tasks` 的下限（否则那是硬违规，不是历史遗留）。
_UNJUDGED_SLICES: dict[str, str] = {}


def _load_module(name: str, path: Path) -> ModuleType:
    """以 importlib 加载被点名的守卫模块（沿用本目录既有约定）。

    复用它的 `validate_slice_against_schema` 而不另写一份：JSON 点名的校验器只有一个，
    本文件守的是它的**覆盖面**，再实现一遍就变成第二个真源，两份实现漂移时谁都不红。
    """
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"无法以 importlib 加载 {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_contract = _load_module("_slice_schema_validator_host", _CONTRACT_PATH)


def _rel(path: Path) -> str:
    return path.relative_to(_REPO).as_posix()


def _slice_params() -> list:
    """`scan_glob` 命中的每一份 slice 一个参数项，已登记的缺口带 strict xfail。

    分母在**收集期**从范式自己的 `scan_glob` 现扫 —— 新增 slice 自动进入，不需要改守卫。
    """
    params: list = []
    for path in _contract.slice_paths():
        rel = _rel(path)
        reason = _UNJUDGED_SLICES.get(rel)
        marks: Any = ()
        if reason:
            marks = pytest.mark.xfail(strict=True, reason=reason)
        params.append(pytest.param(rel, marks=marks, id=Path(rel).stem))
    return params


_SLICE_PARAMS = _slice_params()


def _orphaned_registrations(
    *,
    registered: set[tuple[str, str]],
    carried: set[tuple[str, str]],
    validated_slices: set[str],
) -> list[tuple[str, str]]:
    """纯函数：登记在册却没有任何承载者的欠账。

    「有承载者」= 该 entry 落在 AP-1 的参数化分母里（`capability == single_onlyoffice`，
    因此带得上 xfail 标记），**或**它所在的 slice 真的被 `slice_schema.validator` 校验过。
    两者都不成立 ⇒ 这条登记既不会红、也不会在被清掉时 XPASS 打红，是一条哑登记。

    抽成纯函数是为了能喂合成输入做反向自检（见本文件末两条）：判据既不许恒红也不许恒绿。
    """
    return sorted(
        key
        for key in registered
        if key not in carried and key[0] not in validated_slices
    )


def _ap1() -> dict[str, Any]:
    return _contract._ap(_contract.load_paradigm_doc())


def _carrier_keys() -> set[tuple[str, str]]:
    """AP-1 参数化分母实际点名的 `(slice, entry_id)` —— 即「带得上 xfail 标记」的那些。"""
    carried: set[tuple[str, str]] = set()
    for path in _contract.slice_paths():
        slice_doc = json.loads(path.read_text(encoding="utf-8"))
        for entry in slice_doc.get("independent_entries") or []:
            if entry.get("capability") == "single_onlyoffice":
                carried.add((_rel(path), str(entry.get("entry_id"))))
    return carried


def _validated_slices() -> set[str]:
    """范式**自己声明**为被校验实例的 slice —— 即 `slice_schema.reference_instance`。

    🔴 这不是从源码里 grep 调用点得来的（那是字符判据，把调用改成 `if False:` 仍绿），
    而是从范式自己的声明推的。

    🔴 **G1 收口后为什么仍然只算 `reference_instance`**：收口之后 D / F 两份 slice 确实都被
    校验器走过了（本文件的 §2 参数化，以及 `test_migration_paradigm_contract.py::
    test_every_scanned_slice_passes_the_schema`），但那件事**不能**用来给 AP-1 的欠账登记当
    承载者 —— 欠账的内容是「裁 single_onlyoffice 却没给 `html_counterpart_verdict` 结论」，
    而校验器对 Task 48 之前的 slice 根本不施加那两个字段（`enforce_task48` 由任务号推导）。
    把「slice 被校验过」放宽成「所在 slice 出现在任何校验调用里」会让 :func:`_orphaned_registrations`
    对所有登记恒返回空 = 判据 fail-open，哑登记再也检测不出来。故此处**有意**保持窄义：
    只有范式声明为参照实例的那一份算「其结构被 schema 持续盯着」。

    G2 因此仍然成立，见 :func:`test_every_registered_debt_entry_still_has_a_carrier` 的 xfail。
    """
    return {str(_contract.load_paradigm_doc()["slice_schema"]["reference_instance"])}


# ═══ §1 分母与校验器都不空跑 ═══════════════════════════════════════════════════


def test_the_denominator_and_the_validator_are_both_non_vacuous() -> None:
    """**Validates: Requirements 12.4**

    三件事缺任一，本文件都会恒绿：
    * `scan_glob` 要真扫到 slice（glob 失效 ⇒ 参数化为空 ⇒ 没有一条判据在跑）；
    * 被点名的校验器要真会咬（喂空 dict 必须报违规）；
    * 登记的缺口必须真实存在（否则 xfail 标记挂空，看着像「已登记」其实什么都没管）。
    """
    paths = _contract.slice_paths()
    assert len(paths) >= 2, f"scan_glob 只命中 {len(paths)} 个 slice：{[_rel(p) for p in paths]}"
    assert _SLICE_PARAMS, "参数化为空 —— 覆盖面判据整体空跑"

    assert _contract.validate_slice_against_schema({}), (
        "被点名的 `slice_schema.validator` 对空 dict 都不报违规 ⇒ 它已经不是校验器，"
        "本文件的 xfail 全变成无意义的红"
    )

    known = set(_UNJUDGED_SLICES)
    on_disk = {_rel(p) for p in paths}
    zombies = sorted(known - on_disk)
    assert not zombies, (
        f"登记的缺口指向 scan_glob 扫不到的 slice {zombies} ⇒ xfail 标记挂空"
    )


def test_the_unvalidated_slices_really_are_unvalidated() -> None:
    """**Validates: Requirements 12.4**

    本文件的前提：`scan_glob` 里存在**不是** `reference_instance` 的 slice。缺了这条前提，
    「校验器只走参照实例」就无从谈起，登记与 xfail 都该整体删掉而不是留着看似在管。
    """
    validated = _validated_slices()
    unvalidated = sorted({_rel(p) for p in _contract.slice_paths()} - validated)
    assert unvalidated, (
        "scan_glob 命中的每一份 slice 都是 reference_instance ⇒ 覆盖面缺口不存在，"
        "请删掉本文件与 `_UNJUDGED_SLICES` 登记"
    )
    assert set(_UNJUDGED_SLICES) <= set(unvalidated), (
        f"登记里有已经在被校验的 slice {sorted(set(_UNJUDGED_SLICES) & validated)} ⇒ "
        "它的 xfail 该删了"
    )


def test_the_grandfathering_claim_is_derived_not_asserted() -> None:
    """**Validates: Requirements 12.4**

    登记 reason 里那句「某 slice 早于 schema 生效」不许是散文：`slice_schema.applies_to_tasks`
    的下限必须真的**晚于**被登记 slice 自己的任务号，否则「grandfathered」这个说法是编的。

    ⚠ G1 收口后 `_UNJUDGED_SLICES` 为空 ⇒ 本条**当前不循环任何一项**（空真）。这是正确的：
    没有登记就没有 grandfathering 声明要核。它是「再登记时的门槛」，不是可删的装饰 ——
    下一份带豁免的 slice 一登记就立刻恢复承重。
    """
    applies_from = min(_contract.load_paradigm_doc()["slice_schema"]["applies_to_tasks"])
    for rel in sorted(_UNJUDGED_SLICES):
        slice_doc = json.loads((_REPO / rel).read_text(encoding="utf-8"))
        task = _contract._task_number(slice_doc)
        assert task is not None, f"{rel} 解析不出任务号 —— grandfathering 无法核对"
        assert task < applies_from, (
            f"{rel} 是 Task {task}，而 slice_schema 自 Task {applies_from} 起生效 ⇒ "
            "它并不 grandfathered，缺口性质变了（是硬违规而不是历史遗留），登记 reason 要重写"
        )


# ═══ §2 存量缺口：strict xfail 冻结 ═══════════════════════════════════════════


@pytest.mark.parametrize("slice_rel", _SLICE_PARAMS)
def test_every_slice_passes_the_json_nominated_validator(slice_rel: str) -> None:
    """**Validates: Requirements 1.3, 12.4**

    `slice_schema.validator` 是范式**自己**点名的唯一校验器，`scan_glob` 是它**自己**声明的
    slice 面。两者必须相交到底：每一份 slice 都要能通过那一份 schema。

    G1 收口后三份 slice（D / E / F）实测违规数全 0，`_UNJUDGED_SLICES` 已清空 ⇒ **本条全部
    参数项都是硬判据，没有一条带豁免标记**。Tasks 49–57 新增的 slice 自动进入分母：不通过即
    直接 FAIL，不能靠往豁免表加一行绕过（那正是 G1 的形态）。
    """
    slice_doc = json.loads((_REPO / slice_rel).read_text(encoding="utf-8"))
    problems = _contract.validate_slice_against_schema(slice_doc)
    assert problems == [], (
        f"{slice_rel} 通不过范式自己的 slice_schema（{len(problems)} 条）：\n"
        + "\n".join("  !! " + p for p in problems)
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "AP-1 的 known_debt_inventory 登记了 8 条，但分母按 `capability == single_onlyoffice`"
        " 过滤 ⇒ D 循环那 7 条改裁成 `capability: null` 之后一个 xfail 标记都不挂了，"
        "清单自己承诺的「清掉时 XPASS 打红」也随之失效（静默退出分母，一条红都没有），"
        "而 `test_the_registered_debt_has_no_zombie_entries` 的谓词只问 entry_id 在不在。"
        " 责任方 = 范式 owner + Task 46 D 循环回填。解除条件（任一）：① 把 7 条登记从"
        " known_debt_inventory 里移除并在 Task 46 正文说明改裁已替代欠账；② 让 AP-1 的分母"
        "覆盖「待裁决态」（不再只按 single_onlyoffice 过滤）；③ 把 D slice 纳入"
        " slice_schema.validator 的校验面 —— 🔴 这里指的是**欠账内容**（"
        "`html_counterpart_verdict` 二值结论）真的落进校验器的判据，不是「有调用喂过这份"
        " slice」。G1 收口（SR-3 蕴含式）之后 D/F 两份 slice 确实都被喂过校验器了，但校验器对"
        " Task 48 之前的 slice 不施加那两个字段（`enforce_task48` 由任务号推导），欠账依旧无人"
        "盯着 ⇒ 条件 ③ **未**兑现，本条 xfail 仍成立（实测 2026-08-31 仍 XFAIL 而非 XPASS）。"
        "届时本条 XPASS(strict) 打红，必须回来删标记。"
        " 禁止改用 skip（skip 记为通过 = fail-open）。"
    ),
)
def test_every_registered_debt_entry_still_has_a_carrier() -> None:
    """**Validates: Requirements 12.1, 12.4**

    一条欠账登记只有在**有承载者**时才有意义：要么它还在 AP-1 的参数化分母里（带得上
    strict xfail，清掉即 XPASS 打红），要么它所在的 slice 真的被校验器走过。两者都不成立时，
    登记既不会红、也不会在债务真的还完时提醒任何人 —— 与「这条登记不存在」逐字相同。
    """
    orphaned = _orphaned_registrations(
        registered=_contract.debt_inventory_keys(_ap1()),
        carried=_carrier_keys(),
        validated_slices=_validated_slices(),
    )
    assert not orphaned, (
        f"known_debt_inventory 有 {len(orphaned)} 条哑登记（无 xfail 承载者、所在 slice 也没被"
        f"校验过）：\n" + "\n".join(f"  ?? {s} :: {e}" for s, e in orphaned)
    )


# ═══ §3 反向自检：孤儿谓词既非恒红也非恒绿 ════════════════════════════════════


def test_reverse_selfcheck_a_carried_registration_is_not_orphaned() -> None:
    """带 xfail 承载者的登记不算孤儿 —— 否则 §2 那条恒红，缺口补上也不会 XPASS。"""
    key = ("slice/a.json", "entry/1")
    assert (
        _orphaned_registrations(
            registered={key}, carried={key}, validated_slices=set()
        )
        == []
    )


def test_reverse_selfcheck_a_validated_slice_is_not_orphaned() -> None:
    """所在 slice 被校验器走过的登记也不算孤儿（第二条承载路径必须真的分得开）。"""
    assert (
        _orphaned_registrations(
            registered={("slice/a.json", "entry/1")},
            carried=set(),
            validated_slices={"slice/a.json"},
        )
        == []
    )


def test_reverse_selfcheck_an_uncarried_registration_is_orphaned() -> None:
    """两条承载路径都不成立时必须被点名 —— 否则 §2 那条恒绿。"""
    assert _orphaned_registrations(
        registered={("slice/a.json", "entry/1")},
        carried={("slice/b.json", "entry/1")},
        validated_slices={"slice/c.json"},
    ) == [("slice/a.json", "entry/1")]
