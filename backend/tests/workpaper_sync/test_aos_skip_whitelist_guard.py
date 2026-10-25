"""跳过白名单**无失效条目** —— Requirement 4.3 的逐条核（Task 4.8）。

spec: workpaper-sync-adopt-overwrite-and-refresh-source · ADR-AOS-005
Requirement 4.3：「THE Test_Suite SHALL 校验跳过清单里的每个 item 确实仍属不可枚举形态
（白名单无失效条目）」

🔴 **为什么不能只核「是否取不到门面」** —— design §4.1b (7) 第 3 条明写：

> Task 4.8「跳过白名单无失效条目」的判据**必须逐条核原因类型**，不能只核「是否取不到门面」
> —— 否则 19 条 `kind=rows` 的条目会带着错误原因通过

⇒ 本文件的判据是**两检并列**，缺一不可（下面 M-A2 / M-B 两组变异证明两检互不冗余）：

* **检 ①「取不到枚举器」**：现读 provider 后 `diagnose_row_reader` 顶层必须给不出 reader；
* **检 ②「原因类型相符」**：该条登记的 `SkipReason` 成员，必须等于**独立第二判据**
  （:func:`_classify_skip_reason`，只用 `importlib` / `inspect` 现读重算）得出的成员。

单看检 ① 会让「原因写错」的条目蒙过去（M-B 证明）；单看检 ② 会让「门面路确实不可用、但
R3 已把它救回可枚举」的条目蒙过去（M-A2 证明 —— 那正是 ADR-AOS-005 采纳 R3 之后新出现的
失效形态）。

═══ 六个成员各自的可验证条件（现读 `SkipReason` docstring 逐条确认）═══

| 成员 | 可验证条件 | 本轮现算桶大小 |
| --- | --- | --- |
| `import_failed` | provider 模块 `importlib.import_module` 真的抛 | **0**（空桶） |
| `absent` | import 成功但**无** `iter_store_rows` 属性 | 8 |
| `item_blind` | 门面**在**，签名**不认** `store_item_id` 且硬绑的不是本 item | 54 |
| `item_unresolvable` | 门面 item-aware，喂本 item **真的抛**（且门面非 re-export） | **0**（空桶） |
| `row_reader_bound_to_other_entry` | 门面 `__module__` 指向**别家** | **0**（空桶） |
| `no_store_item` | adapter 级，**无** store item 可谈 | 2 |

🔴 **计数全是现算值，禁写死**（tasks.md 顶部纪律：「R3 相关判据禁写死 104 / 62 这类计数」）。
上表数字只是本轮交付时的观测记录；判据一律现算后与 ADR-AOS-005 §3 的**预期值**对账，
不符即在断言消息里点名差异。

🔴 **三个空桶是 ADR-AOS-005 采纳 R3 的直接后果，不是判据失效**：`item_unresolvable` 与
`row_reader_bound_to_other_entry` 原有的 4 条（`G3-2-detail-rows` / `G4-7-items` /
`G5-2-rows` / `G6-5-fair-value-data`）已由第 ② 级 R3 接住 ⇒ 它们现在**不该**在跳过清单里。
故本文件对空桶的处置是**如实登记 + 配变异对照**（同一判据在非空场景须命中非零），
而**不是**断言它非空 —— 见 :class:`TestEmptyBucketsAreRegisteredHonestly`。
"""
from __future__ import annotations

import importlib
import inspect
from types import SimpleNamespace
from typing import Any, Final

import pytest

from app.services.workpaper_sync.adopt_overwrite_compute import _ADAPTER_LEVEL_REASONS
from app.services.workpaper_sync.adopt_overwrite_plan import SkipReason
from app.services.workpaper_sync.adopt_row_reader import (
    FACADE_NAME,
    _diagnose_via_facade,
    diagnose_row_reader,
)
from app.services.workpaper_sync.adopt_row_reader_r3 import global_spec_index
from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY
from app.services.workpaper_sync.store_projection_response import (
    resolve_store_projection_provider,
)

#: ADR-AOS-005 §3 的预期值，在本文件里只当**棘轮上限**用（跳过清单只许变短）。
#: 🔴 不是等值断言的右操作数 —— 见 `test_denominator_is_non_empty_and_ratchets_against_adr`。
ADR_EXPECTED_SKIP_TOTAL: Final[int] = 69

#: L3 判据里那个关键字参数名 / item-blind 门面硬绑的模块常量名。**声明**，不是键名字面量。
_ITEM_PARAM: Final[str] = "store_item_id"
_HARD_BOUND_ITEM_CONST: Final[str] = "STORE_ITEM_ID"

#: adapter 级取 store item 清单的门面名（取不到 ⇒ `no_store_item` 的可验证条件之一）。
_ALL_ITEMS_NAME: Final[str] = "all_store_item_ids"

#: 检 ① / 检 ② 的失败前缀 —— 变异测试据此判定「是哪一检打红的」（两检互不冗余的证明）。
_FAIL_ENUMERABLE: Final[str] = "检①"
_FAIL_REASON: Final[str] = "检②"

#: 独立第二判据在「六个成员一个都不适用」时的返回值。它出现在白名单里即失效条目。
_NO_SKIP_APPLIES: Final[str] = "<门面结构可用，无成员适用>"


# ═════════════════════════════════════════════════════════════════════════════
# 独立第二判据 —— 六个成员逐条的可验证条件
#
# 🔴 刻意**不**复用 `_diagnose_via_facade` 的返回值来核原因：那等于拿同一份实现核自己，
#    「原因写错」永远不会被发现。本段只用 `importlib` / `inspect` 与门面的 `__module__`
#    现读重算，是一份**独立第二意见**。两份结论不等即打红（同一不变量的两种强度判据互咬）。
# 🔴 借用的是生产的**名字常量**（`FACADE_NAME` / `STORE_ITEM_ID` / `store_item_id`），
#    那些是声明；借用**逻辑**才会让第二意见退化成回声。
# ═════════════════════════════════════════════════════════════════════════════


def _facade_of(provider: Any) -> Any | None:
    fn = getattr(provider, FACADE_NAME, None)
    return fn if callable(fn) else None


def _accepts_item(fn: Any) -> bool:
    """签名里有**显式命名**的 `store_item_id` 吗（`**kwargs` 不算）。"""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    param = sig.parameters.get(_ITEM_PARAM)
    return param is not None and param.kind in (
        inspect.Parameter.KEYWORD_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )


def _facade_module(fn: Any) -> str:
    """门面的**定义**模块。G3~G6 的门面 re-export 自 `phase5_g9_store_facade` 即靠它识别。"""
    return str(getattr(fn, "__module__", "") or "")


def _hard_bound_item(fn: Any) -> str:
    owner = importlib.import_module(_facade_module(fn)) if _facade_module(fn) else None
    return str(getattr(owner, _HARD_BOUND_ITEM_CONST, "") or "")


def _raises_on_empty_payload(fn: Any, *, item_id: str, item_aware: bool) -> tuple[bool, str]:
    """真调 + **真消费**空载荷。

    🔴 消费是必需的：G 循环的门面是 `yield from` 生成器函数，`specs_for` 的抛错发生在
    **第一次迭代**而不是调用时 ⇒ 只调不 `list()` 会把 G3/G4/G5/G6 全判成不抛。
    """
    try:
        list(fn([], **{_ITEM_PARAM: item_id}) if item_aware else fn([]))
    except Exception as exc:  # noqa: BLE001 —— 本判据就是「抛不抛」
        return True, f"{type(exc).__name__}: {exc}"[:200]
    return False, ""


def _classify_skip_reason(
    *, adapter_id: str, item_id: str | None, loader: Any = resolve_store_projection_provider
) -> tuple[str, str]:
    """独立重算本条**应有**的原因类型，返回 `(成员字面值 | 哨兵, 依据)`。

    `loader` 可注入 —— `import_failed` 这个空桶的变异对照就靠替一个「import 不存在的模块」
    的 loader 进来（design §4.1b (5) 第 1 行的对照组同款）。
    `item_id is None` ⇒ 走 adapter 级（`no_store_item`）那一支。
    """
    try:
        provider = loader(adapter_id)
    except Exception as exc:  # noqa: BLE001
        return SkipReason.import_failed.value, f"{type(exc).__name__}: {exc}"[:200]

    if item_id is None:
        fn = getattr(provider, _ALL_ITEMS_NAME, None)
        items = tuple(fn()) if callable(fn) else ()
        single = str(getattr(provider, _HARD_BOUND_ITEM_CONST, "") or "")
        if not items and not single:
            return SkipReason.no_store_item.value, f"{_ALL_ITEMS_NAME} 空且无 {_HARD_BOUND_ITEM_CONST}"
        return _NO_SKIP_APPLIES, f"adapter 有 {len(items) or 1} 个 store item"

    facade = _facade_of(provider)
    if facade is None:
        return SkipReason.absent.value, f"{getattr(provider, '__name__', provider)} 无 {FACADE_NAME}"
    module = _facade_module(facade)
    reexported = module != str(getattr(provider, "__name__", "") or "")
    if not _accepts_item(facade):
        bound = _hard_bound_item(facade)
        if bound != item_id:
            return (
                SkipReason.item_blind.value,
                f"签名无 {_ITEM_PARAM}，硬绑 {module}.{_HARD_BOUND_ITEM_CONST}={bound!r}",
            )
        raised, why = _raises_on_empty_payload(facade, item_id=item_id, item_aware=False)
    else:
        raised, why = _raises_on_empty_payload(facade, item_id=item_id, item_aware=True)
    if raised and reexported:
        return SkipReason.row_reader_bound_to_other_entry.value, f"门面 __module__={module} ｜ {why}"
    if raised:
        return SkipReason.item_unresolvable.value, why
    return _NO_SKIP_APPLIES, f"门面 __module__={module} reexported={reexported}"


# ═════════════════════════════════════════════════════════════════════════════
# 现算普查（B 分母 = adopt 真实枚举的集合）与白名单校验器
# ═════════════════════════════════════════════════════════════════════════════

_CENSUS_MEMO: dict[str, Any] = {}


def _census() -> dict[str, Any]:
    """三级优先级生效后的全域普查。🔴 现算，禁写死（ADR §3：62 是预期值而非承诺值）。

    进程内记忆一次 —— 与 ADR §5(1)「禁缓存 spec 清单」不冲突：那条约束的是**生产**代码
    （灰度开关一开就该多两段），而本文件在单次测试会话内树是固定的，且下面十余个判据
    都要用同一份普查。不记忆的代价是把同一次全域 import + 探活跑十余遍。
    """
    if _CENSUS_MEMO:
        return _CENSUS_MEMO
    from app.services.workpaper_sync.adapters import registry as reg

    out: dict[str, Any] = {
        "adapters": 0,
        "items": 0,
        "enumerable": [],
        "unruled": [],
        "item_level_skips": [],
        "adapter_level_skips": [],
    }
    for adapter_id in sorted(
        {str(r.get("contract_id") or "") for r in reg.DELIVERED_PER_ENTRY_CONTRACTS} - {""}
    ):
        out["adapters"] += 1
        try:
            provider = resolve_store_projection_provider(adapter_id)
        except Exception:  # noqa: BLE001 —— adapter 级 import 失败属 L1，本层观测不到
            continue
        fn = getattr(provider, _ALL_ITEMS_NAME, None)
        if callable(fn):
            items = tuple(str(x) for x in fn())
        else:
            single = str(getattr(provider, _HARD_BOUND_ITEM_CONST, "") or "")
            items = (single,) if single else ()
        if not items:
            out["adapter_level_skips"].append(
                (adapter_id, None, SkipReason.no_store_item.value)
            )
            continue
        for item in items:
            out["items"] += 1
            res = diagnose_row_reader(provider=provider, store_item_id=item)
            if res.is_enumerable:
                out["enumerable"].append((adapter_id, item, type(res.reader).__name__))
            elif res.is_unruled_shape:
                out["unruled"].append((adapter_id, item))
            else:
                out["item_level_skips"].append((adapter_id, item, res.skip_reason.value))
    _CENSUS_MEMO.update(out)
    return _CENSUS_MEMO


def _whitelist() -> tuple[tuple[str, str | None, str], ...]:
    """跳过白名单 = item 级跳过 + adapter 级跳过（`_ADAPTER_LEVEL_REASONS`，第一位放 adapter_id）。"""
    census = _census()
    return tuple(census["item_level_skips"]) + tuple(census["adapter_level_skips"])


def _verify_entry(adapter_id: str, item_id: str | None, reason: str) -> list[str]:
    """校验白名单一条：**两检并列**。返回失败说明（空列表 = 该条仍然有效）。"""
    failures: list[str] = []

    # ── 检 ①：确实取不到行枚举器 ────────────────────────────────────────────
    if item_id is None:
        try:
            provider = resolve_store_projection_provider(adapter_id)
        except Exception as exc:  # noqa: BLE001
            provider = None
            if reason != SkipReason.import_failed.value:
                failures.append(f"{_FAIL_ENUMERABLE} {adapter_id} 解析 provider 即抛 {exc!r}")
        if provider is not None:
            fn = getattr(provider, _ALL_ITEMS_NAME, None)
            items = tuple(fn()) if callable(fn) else ()
            single = str(getattr(provider, _HARD_BOUND_ITEM_CONST, "") or "")
            if items or single:
                failures.append(
                    f"{_FAIL_ENUMERABLE} {adapter_id} 以 {reason} 登记为 adapter 级跳过，"
                    f"但它现算有 {len(items) or 1} 个 store item ⇒ 失效条目"
                )
    else:
        provider = resolve_store_projection_provider(adapter_id)
        res = diagnose_row_reader(provider=provider, store_item_id=item_id)
        if res.is_enumerable:
            failures.append(
                f"{_FAIL_ENUMERABLE} {adapter_id}/{item_id} 以 {reason} 登记为跳过，"
                f"但现算可枚举（reader={type(res.reader).__name__}）⇒ 失效条目"
            )

    # ── 检 ②：登记的原因成员 == 独立第二判据重算的成员 ────────────────────
    expected, why = _classify_skip_reason(adapter_id=adapter_id, item_id=item_id)
    if expected != reason:
        failures.append(
            f"{_FAIL_REASON} {adapter_id}/{item_id} 登记原因 {reason!r}，"
            f"独立判据现算应为 {expected!r}（依据：{why}）⇒ 原因类型失效"
        )
    return failures


def _verify_whitelist(entries: tuple[tuple[str, str | None, str], ...]) -> list[str]:
    failures: list[str] = []
    for adapter_id, item_id, reason in entries:
        failures.extend(_verify_entry(adapter_id, item_id, reason))
    return failures


def _missing_from_whitelist(
    entries: tuple[tuple[str, str | None, str], ...]
) -> list[tuple[str, str | None, str]]:
    """完整性检：真跳过项**漏登记**即返回它们（Requirement 4.2 要的是显式清单）。"""
    declared = {(a, i) for a, i, _r in entries}
    return [t for t in _whitelist() if (t[0], t[1]) not in declared]


class TestSkipWhitelistHasNoStaleEntry:
    """Requirement 4.3 主判据：白名单逐条仍然有效（两检并列全过）。"""

    def test_every_entry_fails_both_checks(self) -> None:
        failures = _verify_whitelist(_whitelist())
        assert failures == [], "\n".join(failures)

    def test_denominator_is_non_empty_and_ratchets_against_adr(self) -> None:
        """🔴 分母非空 + 分桶不漏项 + 跳过清单**只许变短**的棘轮。

        🔴 刻意**不**断言「恰等于 62」—— tasks.md 顶部纪律明写「R3 相关判据禁写死 104 / 62
        这类计数…不得断言等于某个常量」。等值断言还会把「有人给某个 provider 补上门面」
        这种**改善**判成失败。故取棘轮方向（先例 = Task 3.7 的 `TestUnruledShapeRatchet`
        「只许变短，新增一条必须打红」）：变短 ⇒ 绿并在消息里可见，变长 ⇒ 红。
        「恰等于 ADR §3 预期」那条对账归 Task 3.7 的
        `test_aos_row_reader_r3.TestSkipCensusRecount`，本文件不复述。
        """
        census = _census()
        item_level = len(census["item_level_skips"])
        assert item_level > 0, "跳过清单为空 ⇒ 上面那条「逐条全过」恒真，判据形同虚设"
        assert len(census["enumerable"]) > 0, "可枚举集合为空 ⇒ 普查没真跑"
        by_reason: dict[str, int] = {}
        for _a, _i, reason in census["item_level_skips"]:
            by_reason[reason] = by_reason.get(reason, 0) + 1
        assert sum(by_reason.values()) == item_level, "分桶登记漏项"
        assert item_level <= ADR_EXPECTED_SKIP_TOTAL, (
            f"跳过清单现算 {item_level} > ADR-AOS-005 §3 预期上限 "
            f"{ADR_EXPECTED_SKIP_TOTAL} ⇒ 有 item 退回了不可枚举；分桶 {by_reason} ｜ "
            f"adapter 级 {len(census['adapter_level_skips'])} ｜ 未裁决 {census['unruled']}"
        )

    def test_whitelist_reasons_are_all_inside_the_closed_domain(self) -> None:
        """白名单取值域 ⊆ `SkipReason` 六成员；adapter 级那一位放的必须是允许的原因。"""
        domain = {m.value for m in SkipReason}
        adapter_level = {m.value for m in _ADAPTER_LEVEL_REASONS}
        for adapter_id, item_id, reason in _whitelist():
            assert reason in domain, f"{adapter_id}/{item_id} 原因 {reason!r} 出封闭域"
            if item_id is None:
                assert reason in adapter_level, (
                    f"{adapter_id} 以 adapter_id 作键，但 {reason!r} 不在 "
                    f"_ADAPTER_LEVEL_REASONS {sorted(adapter_level)} 内"
                )


class TestPerMemberVerifiableConditions:
    """六个成员**各自**的可验证条件 —— 逐条核，而不是核「是否取不到门面」。"""

    def test_absent_bucket_really_has_no_facade_attribute(self) -> None:
        """`absent` 的条件：import 成功但**无** `iter_store_rows` 属性。"""
        bucket = [
            (a, i)
            for a, i, r in _whitelist()
            if r == SkipReason.absent.value
        ]
        for adapter_id, item_id in bucket:
            provider = resolve_store_projection_provider(adapter_id)
            assert _facade_of(provider) is None, (
                f"{adapter_id}/{item_id} 登记 absent，但 {FACADE_NAME} 属性**在** ⇒ 原因写错"
            )
        assert bucket, "absent 桶为空 —— 若确实为空须走 TestEmptyBucketsAreRegisteredHonestly"

    def test_item_blind_bucket_really_has_a_facade_bound_elsewhere(self) -> None:
        """`item_blind` 的条件：门面**在**、签名**不认** `store_item_id`、硬绑的不是本 item。"""
        bucket = [
            (a, i) for a, i, r in _whitelist() if r == SkipReason.item_blind.value
        ]
        for adapter_id, item_id in bucket:
            provider = resolve_store_projection_provider(adapter_id)
            facade = _facade_of(provider)
            assert facade is not None, f"{adapter_id}/{item_id} 登记 item_blind 却没有门面"
            assert not _accepts_item(facade), (
                f"{adapter_id}/{item_id} 登记 item_blind，但门面签名**认** {_ITEM_PARAM} ⇒ 原因写错"
            )
            bound = _hard_bound_item(facade)
            assert bound != item_id, (
                f"{adapter_id}/{item_id} 登记 item_blind，但门面硬绑的**正是它** ⇒ 原因写错"
            )
        assert bucket, "item_blind 桶为空 —— 若确实为空须走 TestEmptyBucketsAreRegisteredHonestly"

    def test_no_store_item_bucket_really_has_no_store_item(self) -> None:
        """`no_store_item` 的条件：adapter 级，**无** store item 可谈。"""
        bucket = [a for a, i, r in _whitelist() if r == SkipReason.no_store_item.value]
        for adapter_id in bucket:
            provider = resolve_store_projection_provider(adapter_id)
            fn = getattr(provider, _ALL_ITEMS_NAME, None)
            items = tuple(fn()) if callable(fn) else ()
            single = str(getattr(provider, _HARD_BOUND_ITEM_CONST, "") or "")
            assert not items and not single, (
                f"{adapter_id} 登记 no_store_item，但现算有 store item {items or single!r}"
            )
        assert bucket, "no_store_item 桶为空 —— 若确实为空须走空桶登记"


def _raising_item_aware_facade(payload: Any, *, store_item_id: str | None = None) -> Any:
    """合成门面：item-aware 且喂任何 item 即抛 —— `item_unresolvable` 的变异对照用。"""
    raise RuntimeError(f"合成缺陷：store item {store_item_id!r} 不在受管清单里")
    yield  # pragma: no cover —— 使它成为生成器函数，抛错落在第一次迭代


def _bogus_loader(_adapter_id: str) -> Any:
    """import 一个不存在的模块 —— design §4.1b (5) 第 1 行的对照组同款。"""
    return importlib.import_module("app.services.workpaper_sync._aos48_not_a_real_module")


class TestEmptyBucketsAreRegisteredHonestly:
    """🔴 三个空桶**如实登记** + 逐个配变异对照（结构性零必配变异证明）。

    ADR-AOS-005 §5(4) 明写 `is_unruled_shape` 的冻结集合应因 R3 变为空集、
    「若实测不为空，如实登记剩余条目与原因，不得为凑空集而放宽判据」——
    同一纪律反向也成立：**不得为了「桶非空看起来更有覆盖」而断言空桶非空**。
    """

    #: R3 接住之后**预期**转为空的两个成员 + 本层观测不到的那一个。
    EXPECTED_EMPTY = (
        SkipReason.import_failed.value,  # L1，本层收到的已是 import 好的模块
        SkipReason.item_unresolvable.value,  # 4 条已由 R3 救回
        SkipReason.row_reader_bound_to_other_entry.value,  # 同上（G3/G4/G5/G6）
    )

    def test_empty_buckets_are_exactly_the_expected_three(self) -> None:
        """现算哪几个桶空了，并与预期对账 —— 不符即点名，不得默认沿用。"""
        present = {r for _a, _i, r in _whitelist()}
        empty = tuple(m.value for m in SkipReason if m.value not in present)
        assert empty == self.EXPECTED_EMPTY, (
            f"空桶现算 {empty}，预期 {self.EXPECTED_EMPTY} —— 非空的那个成员说明 R3 没能"
            f"接住它（如实登记），空掉的那个说明有条目被静默转走（须查归因）。"
            f"当前白名单取值域 = {sorted(present)}"
        )

    def test_control_import_failed_still_detects_a_real_import_failure(self) -> None:
        """空桶对照 ①：同一判据对「真的 import 不了」必须命中非零。"""
        got, why = _classify_skip_reason(
            adapter_id="任意", item_id="ANY-ITEM", loader=_bogus_loader
        )
        assert got == SkipReason.import_failed.value, (got, why)
        assert "ModuleNotFoundError" in why

    def test_control_item_unresolvable_still_detects_a_raising_item_aware_facade(self) -> None:
        """空桶对照 ②：item-aware 门面喂本 item 即抛（且非 re-export）必判 `item_unresolvable`。"""
        synthetic = SimpleNamespace(
            __name__=__name__, **{FACADE_NAME: _raising_item_aware_facade}
        )
        got, why = _classify_skip_reason(
            adapter_id="任意", item_id="SYNTH-ITEM", loader=lambda _a: synthetic
        )
        assert got == SkipReason.item_unresolvable.value, (got, why)
        # 生产判定器对同一场景必须给出同一成员（两份实现互咬）
        production = _diagnose_via_facade(provider=synthetic, store_item_id="SYNTH-ITEM")
        assert production.skip_reason is SkipReason.item_unresolvable

    def test_control_bound_to_other_entry_still_detects_the_four_g_items(self) -> None:
        """空桶对照 ③：**真实数据** —— 4 条 G 的门面路至今仍是「被借给别家」。

        它们不在白名单里正是因为第 ② 级 R3 把它们救回了可枚举（ADR §2(b)）。
        """
        four = (
            ("g3.dividend_receivable_detail", "G3-2-detail-rows"),
            ("g4.bond_main", "G4-7-items"),
            ("g5.long_term_receivable_detail", "G5-2-rows"),
            ("g6.other_bond_main", "G6-5-fair-value-data"),
        )
        for adapter_id, item_id in four:
            got, why = _classify_skip_reason(adapter_id=adapter_id, item_id=item_id)
            assert got == SkipReason.row_reader_bound_to_other_entry.value, (item_id, got, why)
            assert "phase5_g9_store_facade" in why, why
        whitelisted = {(a, i) for a, i, _r in _whitelist()}
        assert not (set(four) & whitelisted), "这 4 条已被 R3 救回，不该再出现在跳过清单里"

    def test_classifier_can_emit_every_member_of_the_closed_domain(self) -> None:
        """🔴 无后门：六成员**每一个**都有可验证条件能把它产出来。

        `SkipReason` docstring 明写「新增成员必须同时更新 Requirement 4.3 的白名单校验
        （Task 4.8）—— 新原因没进校验表就等于开了个后门」。这条即那句话的可执行形态：
        新增第七个成员时，本断言会因「它无从被产出」而打红。
        """
        emitted = {r for _a, _i, r in _whitelist()}
        emitted.add(
            _classify_skip_reason(adapter_id="任意", item_id="X", loader=_bogus_loader)[0]
        )
        synthetic = SimpleNamespace(
            __name__=__name__, **{FACADE_NAME: _raising_item_aware_facade}
        )
        emitted.add(
            _classify_skip_reason(
                adapter_id="任意", item_id="X", loader=lambda _a: synthetic
            )[0]
        )
        emitted.add(
            _classify_skip_reason(
                adapter_id="g5.long_term_receivable_detail", item_id="G5-2-rows"
            )[0]
        )
        assert emitted == {m.value for m in SkipReason}, (
            f"以下成员无任何可验证条件能产出它 ⇒ 后门："
            f"{sorted({m.value for m in SkipReason} - emitted)}"
        )


#: 门面定义模块上「本 item 的行数组落在哪张表」的声明常量（tasks.md Task 4.2 点名的三条
#: 裸 `_FacadeRowReader` item 就靠它给出 table_key）。用它筛出 **list-store** 形态的 item。
_ROWS_TABLE_KEY_CONST: Final[str] = "ROWS_TABLE_KEY"


def _pick_enumerable_list_store() -> tuple[str, str, str]:
    """现算挑一条**可枚举的 list-store item**（反向变异用），返回 `(adapter, item, table_key)`。"""
    for adapter_id, item_id, reader_kind in _census()["enumerable"]:
        if reader_kind != "_FacadeRowReader":
            continue
        facade = _facade_of(resolve_store_projection_provider(adapter_id))
        owner = importlib.import_module(_facade_module(facade))
        table_key = str(getattr(owner, _ROWS_TABLE_KEY_CONST, "") or "")
        if table_key:
            return adapter_id, item_id, table_key
    raise AssertionError("现算取不到「可枚举的 list-store item」⇒ 反向变异无从构造")


def _pick_r3_rescued() -> tuple[str, str]:
    """现算挑一条**门面路不可用、被 R3 救回**的可枚举 item（检 ① 不冗余的证明用）。"""
    for adapter_id, item_id, reader_kind in _census()["enumerable"]:
        if reader_kind == "EngineRowReader":
            return adapter_id, item_id
    raise AssertionError("现算无 EngineRowReader ⇒ R3 没生效，M-A2 变异无从构造")


class TestInjectingAnEnumerableItemGoesRed:
    """🔴 反向变异 M-A（子项明写）：塞一个**可枚举的 list-store item** 进白名单 ⇒ 必打红。"""

    def test_enumerable_list_store_item_in_whitelist_goes_red(self) -> None:
        adapter_id, item_id, table_key = _pick_enumerable_list_store()
        assert table_key, "被挑中的 item 必须真有行数组声明，否则它不是 list-store"
        mutated = _whitelist() + ((adapter_id, item_id, SkipReason.item_blind.value),)
        failures = _verify_whitelist(mutated)
        assert failures, f"塞入可枚举 item {item_id}（{table_key}）后判据仍全绿 ⇒ 判据失效"
        assert any(f.startswith(_FAIL_ENUMERABLE) and item_id in f for f in failures), failures
        # 这一条同时被两检抓住：它的门面硬绑的**正是它** ⇒ 登记成 item_blind 也是错的原因
        assert any(f.startswith(_FAIL_REASON) and item_id in f for f in failures), failures

    def test_r3_rescued_item_is_caught_by_check_one_only(self) -> None:
        """🔴 检 ① 不冗余：R3 救回的 item 用它**真实的**门面路原因登记时，只有检 ① 能抓住。

        这正是 ADR-AOS-005 之后新出现的失效形态 —— 门面确实不可用（检 ② 无异议），
        但顶层已可枚举 ⇒ 它不该再在跳过清单里。
        """
        adapter_id, item_id = _pick_r3_rescued()
        true_reason, why = _classify_skip_reason(adapter_id=adapter_id, item_id=item_id)
        assert true_reason in {m.value for m in SkipReason}, (true_reason, why)
        failures = _verify_entry(adapter_id, item_id, true_reason)
        assert failures, f"{item_id} 已被 R3 救回却未被判据抓住 ⇒ 检 ① 失效"
        assert all(f.startswith(_FAIL_ENUMERABLE) for f in failures), (
            f"本场景应**只**由检 ① 打红（检 ② 对它无异议），实得 {failures}"
        )


class TestSwappingTheReasonGoesRed:
    """🔴 反向变异 M-B：把某条的原因换成**另一个**成员 ⇒ 逐条核原因类型必打红。

    这组是 design §4.1b (7) 第 3 条「不能只核是否取不到门面」的**直接**证明：
    换过原因的条目在检 ① 下毫无异样（它确实取不到枚举器），只有检 ② 能抓住它。
    """

    def _one(self, reason: str) -> tuple[str, str | None]:
        for adapter_id, item_id, got in _whitelist():
            if got == reason:
                return adapter_id, item_id
        pytest.skip(f"白名单里没有 {reason} 的条目，本变异无从构造")

    def test_item_blind_relabelled_as_absent_goes_red(self) -> None:
        adapter_id, item_id = self._one(SkipReason.item_blind.value)
        failures = _verify_entry(adapter_id, item_id, SkipReason.absent.value)
        assert failures, f"{item_id} 的 item_blind 被改写成 absent 后判据仍全绿 ⇒ 判据失效"
        assert all(f.startswith(_FAIL_REASON) for f in failures), (
            f"本场景应**只**由检 ② 打红（检 ① 对它无异议），实得 {failures}"
        )

    def test_absent_relabelled_as_item_blind_goes_red(self) -> None:
        """反向同做一次 —— 单方向变异会把「判据只认一个方向」这种半失效漏掉。"""
        adapter_id, item_id = self._one(SkipReason.absent.value)
        failures = _verify_entry(adapter_id, item_id, SkipReason.item_blind.value)
        assert failures, f"{item_id} 的 absent 被改写成 item_blind 后仍全绿 ⇒ 判据失效"
        assert all(f.startswith(_FAIL_REASON) for f in failures), failures

    @pytest.mark.parametrize("wrong", sorted(m.value for m in SkipReason))
    def test_every_wrong_member_is_rejected_on_one_real_entry(self, wrong: str) -> None:
        """同一条真实条目换上**每一个**成员：只有它自己的那个成员该通过，其余五个必红。"""
        adapter_id, item_id, real = _whitelist()[0]
        failures = _verify_entry(adapter_id, item_id, wrong)
        if wrong == real:
            assert failures == [], failures
        else:
            assert any(f.startswith(_FAIL_REASON) for f in failures), (
                f"{item_id} 真实原因 {real!r}，换成 {wrong!r} 却没打红 ⇒ 原因类型未被逐条核"
            )


class TestWhitelistOmissionGoesRed:
    """🔴 反向变异 M-C：白名单**漏登记**一条真跳过项 ⇒ 完整性检必打红。"""

    def test_full_whitelist_has_no_omission(self) -> None:
        assert _missing_from_whitelist(_whitelist()) == []

    def test_dropping_one_real_entry_is_detected(self) -> None:
        full = _whitelist()
        assert len(full) > 1, "白名单太短，漏登记变异无从构造"
        dropped, rest = full[0], full[1:]
        missing = _missing_from_whitelist(rest)
        assert missing == [dropped], (missing, dropped)

    def test_dropping_the_adapter_level_entry_is_detected(self) -> None:
        """adapter 级那一档（`_ADAPTER_LEVEL_REASONS`）同样不许漏 —— 它的键是 adapter_id。"""
        adapter_level = tuple(_census()["adapter_level_skips"])
        assert adapter_level, "adapter 级跳过为空 ⇒ 本变异无从构造（须如实登记该桶已空）"
        rest = tuple(t for t in _whitelist() if t not in adapter_level[:1])
        assert _missing_from_whitelist(rest) == [adapter_level[0]]


class TestNoZombieEntry:
    """🔴「无失效条目」的第二个方向：清单里不该有**其实现在已经可枚举**的僵尸条目。

    先例 = Task 3.7 的 `TestUnruledShapeRatchet.test_baseline_has_no_zombie_entry`
    （基线条目必须**仍然**符合条件，修好了就该从基线移除）。本文件的静态基线只有
    :attr:`TestEmptyBucketsAreRegisteredHonestly.EXPECTED_EMPTY` 一处，它用**相等**而非
    子集断言 ⇒ 某个桶一旦不再为空，那条也会打红，僵尸方向两处都有覆盖。
    """

    def test_no_whitelist_entry_is_enumerable_at_the_top_level(self) -> None:
        zombies = [
            (a, i, r)
            for a, i, r in _whitelist()
            if i is not None
            and diagnose_row_reader(
                provider=resolve_store_projection_provider(a), store_item_id=i
            ).is_enumerable
        ]
        assert zombies == [], f"这些条目现在已可枚举，应从跳过清单移除：{zombies}"

    def test_no_whitelist_entry_has_an_r3_path(self) -> None:
        """更早一步的僵尸信号：item 在全域 spec 索引里就意味着 R3 本该接住它。"""
        index = global_spec_index()
        leaked = [(a, i, r) for a, i, r in _whitelist() if i is not None and i in index]
        assert leaked == [], f"这些条目有 R3 路径却仍在跳过清单里：{leaked}"

    def test_control_the_index_really_covers_enumerable_items(self) -> None:
        """🔴 上一条是结构性零 ⇒ 配变异对照：同一索引对可枚举侧必须命中非零。"""
        index = global_spec_index()
        hit = [i for _a, i, _k in _census()["enumerable"] if i in index]
        assert len(hit) > 0, "全域 spec 索引对可枚举侧也命中 0 ⇒ 上一条的 0 是索引失效"
        assert len(index) > 0


class TestRowsKindCrossCheckStaysVisible:
    """design §4.1b (4) 的交叉核不得消失：判为跳过、但注册表 `kind` 明写 `rows` 的那些条目。

    🔴 它们是**能力缺口**（欠门面），不是「载荷不是行数组」的形态使然 —— 把它们登记成粗原因
    正是 Requirement 4.3 要打红的失效条目。`SkipReason` 封闭域里没有任何形态类成员
    （`no_row_reader` 那种粗写法已被四个原因桶取代），本组即那件事的可执行守卫。
    """

    @staticmethod
    def _registry_kinds() -> dict[str, str]:
        out: dict[str, str] = {}
        for plan in STORE_MERGE_REGISTRY.values():
            for spec in getattr(plan, "items", ()) or ():
                item_id = str(getattr(spec, "item_id", "") or "")
                kind = getattr(spec, "kind", None)
                kind_value = str(getattr(kind, "value", kind) or "")
                if item_id and kind_value:
                    out[item_id] = kind_value
        return out

    def test_skipped_rows_kind_entries_are_capability_gaps(self) -> None:
        kinds = self._registry_kinds()
        rows_kind = [
            (a, i, r) for a, i, r in _whitelist() if kinds.get(str(i), "") == "rows"
        ]
        # 🔴 现算值，禁写死：R3 采纳前 design 记 18 条，救回后本轮现算已大幅缩小。
        for adapter_id, item_id, reason in rows_kind:
            assert reason != SkipReason.no_store_item.value, (
                f"{adapter_id}/{item_id} 的 kind 明写 rows，却登记成 no_store_item ⇒ 失效条目"
            )
        assert rows_kind, (
            "交叉核分母为空 —— 若确为空须如实登记（说明 kind=rows 的条目已全部可枚举）"
        )

    def test_control_the_kind_scanner_hits_the_enumerable_side(self) -> None:
        """🔴 变异对照：同一 kind 扫描器在可枚举侧必须命中非零（证明 kind 真读到了）。"""
        kinds = self._registry_kinds()
        assert "rows" in set(kinds.values()), "registry 里读不到 kind=rows ⇒ 扫描口径失效"
        enumerable_rows = [
            i for _a, i, _k in _census()["enumerable"] if kinds.get(i, "") == "rows"
        ]
        assert len(enumerable_rows) > 0, "kind 扫描器在可枚举侧命中 0 ⇒ 上一条的分母不可信"


# ══════════════════════════════════════════════════════════════════════════════
# ── Task 4.7 落点 ──
#
# Task 4.7「单测：`in` 与空元组的显式对照」落在本文件之后的部分，**不得**塞进上面任何类。
# 两例（tasks.md 原文）：table 不在 `row_keys` 键集合 ⇒ 行不变；在键集合但值为 `()` ⇒ 清空。
# 被测对象是 `adopt_overwrite_plan.prune_undeclared_rows`（Task 4.1 交付），与本文件上面
# 的普查判据没有共享 fixture ⇒ 新建独立测试类，不要复用 `_census()` / `_whitelist()`。
#
# 🔴 **行数余量**：`.py` 门禁上限 **800**（`backend/scripts/check/check_file_size.py`），
#    Task 4.8 交付时本文件现算 **707** 行（口径 `len(text.split("\n"))`，🔴 PowerShell 的
#    `Measure-Object -Line` 在本文件少报 176 行，不可信）⇒ 余量约 **93** 行。两例 + 类
#    docstring 放得下；若 4.7 的判据超出这个余量，**另开伴生文件**（域内已四次同样处置），
#    不要挤到门禁边缘。
# 🔴 Task 4.8 **未**替它实现任何部分：上面 8 个类没有一条断言碰 `prune_undeclared_rows`。
# ══════════════════════════════════════════════════════════════════════════════

# ── Task 4.7 的落点结论（交付后回填指针）──
#
# 实测超出上面登记的 93 行余量（两例 + 对照断言 + 两组源码级变异反证 + 反空转判据 = 413 行）
# ⇒ 按上面给的处置抽伴生文件 **`test_aos_declared_table_binary.py`**（域内第五次同样处置）。
# 本文件一条断言未改，仅补此指针。
