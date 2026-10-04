# -*- coding: utf-8 -*-
"""单趟写入结束后句柄必须**真的**释放（spec oo-single-pass-materialize-and-room-leave）。

Requirements: **1.4**　design: 二.4「句柄释放」/ 三「解析结果复用」/ 六「非目标」第 2 条

═══ 两个作用域函数的真实语义（读实现得来，不是猜的）═══

`excel_extract.workbook_read_scope()`：`ContextVar` 上挂一个 dict，键是
`(_file_cache_key(path), bool(data_only))`，其中 `_file_cache_key` =
`(str(path.resolve()), st.st_mtime_ns, st.st_size)`。**嵌套进入沿用外层缓存**，关闭责任留给
最外层；退出时无条件 `close()` 全部 workbook（含异常路径）。

`excel_extract.release_scoped_workbooks(path)`：按 `k[0][0] == str(path.resolve())` 匹配 ——
**只比路径、不比 mtime/size，也不比 `data_only`** ⇒ 一次调用同时清掉 `data_only=True/False`
**两个**视图（design 三点名的那条：两个视图是两条独立缓存项，漏一个就还留着一个句柄）。
作用域外（cache 为 None/空）是安全空操作。

进缓存的**唯一**入口是 `_acquire_read_only_workbook`，它只被 `_read_cell_view` 调，而
`_read_cell_view` 只被 `extract_projection` / `_extract_static_projection` 调。materialize 的
计划阶段走的正是 `extract_projection(artifact=substrate, …)`（`_plan_materialize_step` 唯一
实现）⇒ **substrate 路径**必然进缓存，单趟实测恰 2 条（两视图），链式实测 78 条（39 趟 × 2）。

═══ 判据的 oracle：`unlink` 到底成不成 ═══

本文件**不**断言「我们调用了 release 函数」—— 那种断言在 release 被改成空壳后照样绿。
断言的是 **`path.unlink()` 真的成功**，而反面（不释放就删）在 Windows 上抛
`PermissionError WinError 32`。这台机器实测确认 oracle 成立：

| 现场 | 结果 |
|---|---|
| 作用域内解析两个视图后**不**释放就 `unlink` | `PermissionError` **WinError 32**「另一个程序正在使用此文件」 |
| `release_scoped_workbooks(path)` 之后 `unlink` | 成功，且缓存里针对该路径的条目 2 → **0** |

⚠️ 这条 oracle 是**平台相关**的：POSIX 允许删已打开的文件，所以「不释放就删不掉」只能在
win32 上断。本文件因此**不 skip**、而是按平台分支断言（skip 会让文件在 CI 换 Linux 那天静默
变空壳）；`platform: win32` 是本平台的实际形态，Windows 分支就是被真实跑到的那条。

═══ 非空转：怎么证明句柄**真的**被持有过 ═══

「release 之后删得掉」单独看是可以空转的 —— 如果 workbook 压根没进缓存，不释放也删得掉。
三层各自独立地把分母立起来：

1. **缓存快照**：单趟写入**刚返回**那一刻（还在生产自己的作用域里）抓一次，必须恰有
   `data_only=False/True` 两条针对 substrate 的条目 ⇒ 句柄此刻确实被持有，释放不是可选动作；
2. **反证（同一条真实路径上跑）**：不释放就 `unlink` ⇒ 实测 `PermissionError WinError 32`；
3. **生产调用点承重反证**：把 `adapters.excel` 里的 `release_scoped_workbooks` 换成 no-op，
   真库链式回落路径的清理**立刻炸** `PermissionError WinError 32`，并在盘上留下 38 个中间产物
   ⇒ 生产那行 release 不是装饰。

═══ 2026-09-22 真库实测结论 ═══

| 判据 | 实测 |
|---|---|
| 单趟：写入结束那刻 substrate 缓存条目 | **2**（`data_only` False/True 各一），趟数 1 / substrate 解析 2 |
| 单趟：release → 条目数 | 2 → **0**（一次调用清掉两个视图） |
| 单趟：release 后 `unlink` | **成功** |
| 单趟：**不** release 就 `unlink` | **PermissionError WinError 32**（反证成立） |
| 单趟：`*.materializing` 是否进缓存 | **0 次** ⇒ 生产在它上面不调 release 是对的（没有句柄可放） |
| 链式回落：中间产物 | 38 个全部进过缓存、全部被 release、全部删净 |
| 链式回落：release 改 no-op | materialize 抛 `PermissionError WinError 32`，盘上残留 38 个中间产物 |

**生产代码本次零改动** —— 三处 `unlink`（链式中间产物 / `repaired` / `g7_sanitized`）都已按
「谁删文件，谁先释放句柄」写对，单趟自己的 `*.materializing` 无需释放（从不被解析）。
`verify_unmanaged_regions` 那两处无 release 的 `unlink`（`d429_before` /
`g7_before_sanitized`）也**不是**缺陷：实测它们从不进缓存（verify 只用 `zipfile`，不走
`_read_cell_view`），本文件用运行时判据把这个理由钉住，而不是靠读代码下结论。
"""
from __future__ import annotations

import ast
import contextlib
import sys
from pathlib import Path
from typing import Any, Iterator

import pytest

from app.services.workpaper_sync import excel_extract as EE
from app.services.workpaper_sync import excel_materialize as EM
from app.services.workpaper_sync.adapters import excel as AX
from app.services.workpaper_sync.excel_extract import (
    release_scoped_workbooks,
    workbook_read_scope,
)
from tests.workpaper_sync.d4_materialize_harness import (
    D4World,
    MaterializeCallCounter,
    build_world,
    force_chained_path,
)
from tests.workpaper_sync.test_single_pass_failure_atomicity import (
    diff_scans,
    scan,
    temp_file_witness,
)
from tests.workpaper_sync.test_single_pass_materialize import (
    BASELINE_BINDINGS,
    SINGLE_PASS_SUBSTRATE_LOADS,
)

#: Windows「另一个程序正在使用此文件」。句柄未释放时 `unlink` 抛的就是它 —— 本文件的 oracle。
WINERROR_SHARING_VIOLATION = 32

#: 一个文件在缓存里应有的两条视图（`sorted(bool)` ⇒ False 在前）。design 三：两者不可互相冒充。
BOTH_DATA_ONLY_VIEWS = (False, True)

_ON_WINDOWS = sys.platform == "win32"


# ═══════════════════════════════════════════════════════════════════════════
# 观测器：缓存条目 / 进缓存的路径 / release 调用 / release 被掐死
# ═══════════════════════════════════════════════════════════════════════════


def scoped_views_for(path: Path) -> tuple[bool, ...]:
    """当前作用域缓存里针对 `path` 的 `data_only` 视图集合（排序，确定）。

    直接读生产的 `ContextVar`，与 `release_scoped_workbooks` 的匹配口径**同一条**
    （`k[0][0] == str(path.resolve())`，不比 mtime/size）⇒ 「释放前有几条、释放后有几条」
    这个分母不是自己另算一套算出来的。
    """
    cache = EE._workbook_scope.get() or {}
    target = str(path.resolve())
    return tuple(
        sorted(
            bool(key[1])
            for key in cache
            if isinstance(key[0], tuple) and key[0][0] == target
        )
    )


@contextlib.contextmanager
def scoped_cache_witness() -> Iterator[list[tuple[str, bool]]]:
    """记录本段内**真正进了作用域缓存**的 `(文件名, data_only)`。

    只记「进了缓存」而不是「被 acquire 过」：作用域外、或 `stat` 不到时
    `_acquire_read_only_workbook` 退化成即用即关（不留句柄），把那些也记上会让
    「谁需要 release」这条判据的分母虚高。落在**文件名**上而不是完整路径上：临时文件事后
    已被删，删掉之后 Windows 的 `Path.resolve()` 不再展开 8.3 短名（`ADMINI~1`），用完整
    路径比会在「同一个文件」上比出两种写法。
    """
    seen: list[tuple[str, bool]] = []
    original = EE._acquire_read_only_workbook

    @contextlib.contextmanager
    def watched(path: Any, *, data_only: bool) -> Iterator[Any]:
        with original(path, data_only=data_only) as workbook:
            cache = EE._workbook_scope.get()
            if cache:
                target = str(Path(path).resolve())
                cached = any(
                    isinstance(key[0], tuple)
                    and key[0][0] == target
                    and bool(key[1]) is bool(data_only)
                    for key in cache
                )
                entry = (Path(path).name, bool(data_only))
                if cached and entry not in seen:
                    seen.append(entry)
            yield workbook

    EE._acquire_read_only_workbook = watched  # type: ignore[assignment]
    try:
        yield seen
    finally:
        EE._acquire_read_only_workbook = original  # type: ignore[assignment]


@contextlib.contextmanager
def release_witness() -> Iterator[list[str]]:
    """记录每一次 `release_scoped_workbooks` 的目标文件名，**不改行为**。

    必须同时打 `excel_extract` 与 `adapters.excel` 两处：后者在模块头
    `from …excel_extract import release_scoped_workbooks` 按**值**导入 ⇒ 只打前者的话，生产
    写盘路径上那三处调用一次都记不到（观察者静默失效，判据变空转）。
    """
    seen: list[str] = []
    original = EE.release_scoped_workbooks

    def watched(path: Path) -> None:
        seen.append(Path(path).name)
        original(path)

    for module in (EE, AX):
        setattr(module, "release_scoped_workbooks", watched)
    try:
        yield seen
    finally:
        for module in (EE, AX):
            setattr(module, "release_scoped_workbooks", original)


@contextlib.contextmanager
def neutered_release() -> Iterator[list[str]]:
    """把 `release_scoped_workbooks` 换成 **no-op**（只记不放）—— 承重反证用。

    这是「生产那行 release 是不是装饰」的唯一诚实问法：留着它跑一遍全绿，说明不了它有用；
    掐死它之后**真库链式路径必须炸**，才说明它承重。
    """
    skipped: list[str] = []
    original = EE.release_scoped_workbooks

    def no_op(path: Path) -> None:
        skipped.append(Path(path).name)

    for module in (EE, AX):
        setattr(module, "release_scoped_workbooks", no_op)
    try:
        yield skipped
    finally:
        for module in (EE, AX):
            setattr(module, "release_scoped_workbooks", original)


@contextlib.contextmanager
def snapshot_when_single_pass_returns(substrate: Path) -> Iterator[list[tuple[bool, ...]]]:
    """在**单趟写入刚返回**那一刻抓一次缓存快照 —— 需求 1.4 说的「写入结束后」就是这一刻。

    打在 `excel_materialize` 模块属性上（`_try_single_pass_materialize` 在函数体内 import，
    每次调用重新取模块属性）。此刻还在生产自己的 `workbook_read_scope()` 里，快照反映的是
    生产要释放句柄时的**真实**缓存状态，不是测试另外摆出来的现场。
    """
    taken: list[tuple[bool, ...]] = []
    original = EM.materialize_projection_single_pass

    def watched(*args: Any, **kwargs: Any) -> Any:
        outcome = original(*args, **kwargs)
        taken.append(scoped_views_for(substrate))
        return outcome

    EM.materialize_projection_single_pass = watched  # type: ignore[assignment]
    try:
        yield taken
    finally:
        EM.materialize_projection_single_pass = original  # type: ignore[assignment]


def unlink_now(path: Path) -> BaseException | None:
    """删一次，把**真实**结果带回来（成功返回 `None`，失败返回异常本体）。

    判据要报「到底抛了什么」而不是只报「删失败了」：WinError 32 与「文件不存在」「权限不足」
    是三件事，混成一句话之后归因就没了。
    """
    try:
        path.unlink()
    except OSError as exc:
        return exc
    return None


def assert_blocked_without_release(path: Path, *, label: str) -> str:
    """不释放就删 —— Windows 上必须被拒，POSIX 上如实记录它删得掉。

    返回一句人读的实测结论，供判据把「这条判据在本平台值多少」写进失败信息与证据里。
    需求 1.4 点名的是 Windows，本函数因此**不 skip**：换平台时它照样跑，只是断言换成 POSIX
    的真实语义（删得掉，但句柄还在 ⇒ release 依旧是正确性要求，只是不再由 `unlink` 兜底）。
    """
    assert scoped_views_for(path) == BOTH_DATA_ONLY_VIEWS, (
        f"[{label}] 删之前缓存里针对 {path.name} 的视图是 {scoped_views_for(path)}，"
        f"不是 {BOTH_DATA_ONLY_VIEWS} ⇒ 句柄压根没被持有，本条反证是空转"
    )
    failure = unlink_now(path)
    if _ON_WINDOWS:
        assert isinstance(failure, PermissionError), (
            f"[{label}] Windows 上句柄未释放却删成功了（{failure!r}）—— 那说明本文件全部"
            "「release 之后删得掉」的判据都失去了分母：删得掉不再证明句柄被释放了。"
            "需求 1.4 的前提（未释放会导致临时文件删不掉）在本机不再成立，必须重新设计 oracle"
        )
        assert getattr(failure, "winerror", None) == WINERROR_SHARING_VIOLATION, (
            f"[{label}] 抛的是 PermissionError 但 winerror={getattr(failure, 'winerror', None)}"
            f"，不是共享冲突 {WINERROR_SHARING_VIOLATION} ⇒ 失败原因可能与句柄无关"
        )
        return f"win32: unlink 被拒 PermissionError WinError {WINERROR_SHARING_VIOLATION}"
    assert failure is None, f"[{label}] POSIX 上 unlink 反而失败了：{failure!r}"
    return "posix: unlink 成功（已打开的文件可删）⇒ 本条反证在非 Windows 上无判别力"


# ═══════════════════════════════════════════════════════════════════════════
# world（module 作用域：铺 world 十几秒，全模块共用一份）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> D4World:
    """真 D4 模板 + 真契约 + 真 39 binding，projection 取自 substrate 自身的反读结果。"""
    return build_world(tmp_path_factory.mktemp("d4-handles"))


def temp_substrate(world: D4World, tmp_path: Path, name: str) -> Path:
    """一份**临时** substrate 副本 —— 生产里 `repaired` / `g7_sanitized` 的形态。

    为什么非得是副本：需求 1.4 要的是「写完之后这个文件删得掉」。`world.base` 是后面判据还要
    复用的 world 资产，删它会把同模块其它判据一起带走；而生产里真正需要被删的那个 substrate
    恰恰**就是**临时副本（OO→HTML 的 `repaired`、G7 的 `g7-noif`）⇒ 副本不是为了方便，
    它就是被判对象本身。
    """
    path = tmp_path / name
    path.write_bytes(world.base.read_bytes())
    return path


# ═══════════════════════════════════════════════════════════════════════════
# §0 oracle 与两个作用域函数的语义（毫秒级，不碰 world）
# ═══════════════════════════════════════════════════════════════════════════


def _tiny_book(path: Path, *, a1: str = "hello") -> Path:
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "S1"
    sheet["A1"] = a1
    workbook.save(path)
    workbook.close()
    return path


def _both_views(path: Path) -> None:
    for data_only in (True, False):
        EE._read_cell_view(
            path,
            sheet_name="S1",
            columns=frozenset({"A"}),
            rows=range(1, 2),
            data_only=data_only,
        )


def test_an_unreleased_scoped_handle_really_blocks_deletion(tmp_path: Path) -> None:
    """**Validates: Requirements 1.4**

    本文件的 **oracle 自身**。没有这一条，后面每一句「release 之后删得掉」都只是「删得掉」，
    与句柄有没有被释放无关 —— 那是最典型的假绿形态。

    实测（win32）：作用域内解析两个视图后不释放就 `unlink` ⇒ `PermissionError WinError 32`。
    """
    book = _tiny_book(tmp_path / "oracle.xlsx")
    with workbook_read_scope():
        _both_views(book)
        verdict = assert_blocked_without_release(book, label="oracle")
        release_scoped_workbooks(book)
        assert unlink_now(book) is None, "释放之后仍然删不掉"
    assert not book.exists(), verdict


def test_release_clears_both_data_only_views_in_one_call(tmp_path: Path) -> None:
    """**Validates: Requirements 1.4**　design 三

    `data_only=True/False` 是**两条**缓存项（键里含 `data_only`），漏掉一条就还留着一个句柄
    ⇒ 文件照样删不掉。`release_scoped_workbooks` 按路径匹配、不比 `data_only` ⇒ 一次清两条。

    判据分两半：条目数 2 → 0（结构），以及 `unlink` 成功（后果）。只断后果的话，「它恰好清掉了
    那一条恰好被 Windows 计入的句柄」与「两条都清了」分不开。
    """
    book = _tiny_book(tmp_path / "two-views.xlsx")
    with workbook_read_scope():
        _both_views(book)
        assert scoped_views_for(book) == BOTH_DATA_ONLY_VIEWS, (
            f"两个视图没各自进缓存：{scoped_views_for(book)} —— "
            "要么复用把它们串成了一条（design 三明令不可互相冒充），要么没进缓存"
        )
        release_scoped_workbooks(book)
        assert scoped_views_for(book) == (), (
            f"release 之后仍有残留视图 {scoped_views_for(book)} ⇒ 还握着一个句柄"
        )
        assert unlink_now(book) is None, "两个视图都清了却仍删不掉"
    assert not book.exists()


def test_release_only_touches_the_named_path(tmp_path: Path) -> None:
    """**Validates: Requirements 1.4**

    释放必须是**定点**的：链式路径按清册逐个释放并删除，顺手把别人的句柄也关了会让后续趟
    读到已关闭的 workbook（openpyxl 对已 close 的 read_only 簿抛 `AttributeError`/`ValueError`）。
    """
    doomed = _tiny_book(tmp_path / "doomed.xlsx", a1="doomed")
    keeper = _tiny_book(tmp_path / "keeper.xlsx", a1="keeper")
    with workbook_read_scope():
        _both_views(doomed)
        _both_views(keeper)
        release_scoped_workbooks(doomed)
        assert scoped_views_for(doomed) == ()
        assert scoped_views_for(keeper) == BOTH_DATA_ONLY_VIEWS, (
            "release 把别的文件的缓存也清了 ⇒ 定点释放退化成清空"
        )
        # 被留下的那份必须仍然**可用**（不是只剩个 key）。
        view = EE._read_cell_view(
            keeper,
            sheet_name="S1",
            columns=frozenset({"A"}),
            rows=range(1, 2),
            data_only=True,
        )
        assert view["A1"] == "keeper", "留下的 workbook 已被关闭 ⇒ 后续趟会读炸"
        assert unlink_now(doomed) is None
    keeper.unlink()


def test_release_outside_a_scope_is_a_safe_no_op(tmp_path: Path) -> None:
    """**Validates: Requirements 1.4**

    作用域外本就即用即关，没有缓存可清。生产的 `finally` 会在**任何**退出路径上调它（包括
    作用域从未建立的情形，例如 decline 发生在建作用域之前的将来重构），所以它必须不抛。
    """
    book = _tiny_book(tmp_path / "unscoped.xlsx")
    assert EE._workbook_scope.get() is None, "前提不成立：本条要求当前没有作用域"
    release_scoped_workbooks(book)  # 不抛即通过
    release_scoped_workbooks(tmp_path / "does-not-exist.xlsx")  # 连文件都没有也不许抛
    assert unlink_now(book) is None


# ═══════════════════════════════════════════════════════════════════════════
# §1 单趟写入路径（任务 6 点名的那条）—— 真 D4 world
# ═══════════════════════════════════════════════════════════════════════════


def _run_single_pass(
    world: D4World, substrate: Path, label: str
) -> tuple[MaterializeCallCounter, list[tuple[bool, ...]]]:
    """在**外层**作用域里跑一次真单趟物化，返回计数器与「写入刚返回那刻」的缓存快照。

    为什么要套一层外层作用域：`adapter.materialize` 自己开的作用域在返回时就关句柄了，那时
    再断言「句柄被持有」永远是空的。而生产里需要被删的 `repaired` / `g7_sanitized` 恰恰是在
    **作用域仍然打开**的时候被 `release + unlink` 的（`_materialize_within_scope` 的
    `finally` 在 `with workbook_read_scope():` 之内）。嵌套语义（内层沿用外层缓存、关闭责任
    留给最外层）让外层作用域精确复现那个时刻，而不是另造一个现场。
    """
    counter = MaterializeCallCounter()
    with snapshot_when_single_pass_returns(substrate) as snapshots, counter.installed():
        world.adapter.materialize(
            substrate=substrate,
            projection=world.projection,
            output=world.staged(label),
            contract=world.contract,
        )
    return counter, snapshots


def _assert_really_went_single_pass(
    counter: MaterializeCallCounter, snapshots: list[tuple[bool, ...]], substrate: Path
) -> None:
    """反空转前提：真的走了单趟，而且 substrate 真的被解析进了缓存。

    少了这三条，「release 之后删得掉」可能是因为压根没走单趟（decline 回落链式）、或者
    substrate 从未被解析（那就没有句柄，删得掉与释放无关）。
    """
    assert counter.single_pass_trip_count == 1 and counter.trip_count == 1, (
        f"没走单趟路径：趟数 {counter.trip_count}（单趟 {counter.single_pass_trip_count}）"
        " —— 任务 6 点名的是单趟写入，回落到链式时本判据测的不是它"
    )
    assert counter.substrate_load_count == SINGLE_PASS_SUBSTRATE_LOADS, (
        f"substrate 解析次数 {counter.substrate_load_count} ≠ {SINGLE_PASS_SUBSTRATE_LOADS}"
        "（需求 1.1 的两个 data_only 视图各一次）⇒ 缓存里该有几条句柄这个分母变了"
    )
    assert snapshots == [BOTH_DATA_ONLY_VIEWS], (
        f"单趟写入**刚返回**那一刻，缓存里针对 {substrate.name} 的视图是 {snapshots}，"
        f"不是 [{BOTH_DATA_ONLY_VIEWS}] ⇒ 需求 1.4 说的「写入结束后」这一刻并没有句柄被持有，"
        "本条判据失去对象（要么解析没进缓存，要么有人提前关了）"
    )


def test_single_pass_substrate_handle_is_released_and_the_temp_substrate_unlinks(
    world: D4World, tmp_path: Path
) -> None:
    """**Validates: Requirements 1.4**

    任务 6 的**主判据**：真库 D4 单趟写入结束后 `release_scoped_workbooks(path)`，临时
    substrate 必须能被 `unlink` —— 而且是**真的删成功**，不是「我们调了 release」。

    四步各自独立可证伪：

    1. 真走了单趟（趟数 1 / substrate 解析 2）；
    2. 写入刚返回那刻缓存里恰有两个视图 ⇒ 句柄确实被持有（释放不是可选动作）；
    3. `release_scoped_workbooks` 之后缓存条目 2 → 0；
    4. `unlink()` 返回 `None`（成功）。句柄泄漏时这一步在 Windows 上抛 WinError 32 ——
       反面由 `test_without_the_release_the_temp_substrate_cannot_be_unlinked` 实测。
    """
    substrate = temp_substrate(world, tmp_path, "single-pass-temp-substrate.xlsx")
    with workbook_read_scope():
        counter, snapshots = _run_single_pass(
            world, substrate, "handle-release-single.xlsx"
        )
        _assert_really_went_single_pass(counter, snapshots, substrate)

        assert scoped_views_for(substrate) == BOTH_DATA_ONLY_VIEWS, (
            f"materialize 返回后缓存里只剩 {scoped_views_for(substrate)} ⇒ "
            "嵌套作用域提前关了句柄，本条不再复现生产的释放时刻"
        )
        release_scoped_workbooks(substrate)
        assert scoped_views_for(substrate) == (), (
            f"release 之后仍有视图残留：{scoped_views_for(substrate)}"
        )
        failure = unlink_now(substrate)
        assert failure is None, (
            f"release 之后临时 substrate 仍删不掉：{failure!r} —— "
            "需求 1.4 不成立（Windows 上 WinError 32 = 句柄仍被持有）"
        )
    assert not substrate.exists()


def test_without_the_release_the_temp_substrate_cannot_be_unlinked(
    world: D4World, tmp_path: Path
) -> None:
    """**Validates: Requirements 1.4**

    上一条的**反证**，跑在同一条真实路径上：单趟写完之后**不**调 release 直接删 ⇒ Windows 上
    必须被拒（`PermissionError WinError 32`）。

    这条是整个文件的分母。没有它，「release 之后删得掉」在「本来就删得掉」的世界里也是绿的，
    需求 1.4 就成了一句无法证伪的话。

    ⚠️ 平台诚实：POSIX 允许删已打开的文件 ⇒ 在非 Windows 上这条没有判别力，
    `assert_blocked_without_release` 会如实断成「删成功」并把结论写进 `verdict`。
    需求 1.4 点名 Windows，本平台是 win32 ⇒ 被真实跑到的是 Windows 分支。
    """
    substrate = temp_substrate(world, tmp_path, "no-release-temp-substrate.xlsx")
    with workbook_read_scope():
        counter, snapshots = _run_single_pass(
            world, substrate, "handle-release-counterproof.xlsx"
        )
        _assert_really_went_single_pass(counter, snapshots, substrate)

        verdict = assert_blocked_without_release(substrate, label="single_pass")
        # 反证做完把现场收干净：证明「加上 release 就删得掉」是同一次运行里的对照。
        release_scoped_workbooks(substrate)
        assert unlink_now(substrate) is None, f"补上 release 之后仍删不掉（{verdict}）"
    assert not substrate.exists(), verdict


def test_the_single_pass_materializing_temp_never_enters_the_scope_cache(
    world: D4World,
) -> None:
    """**Validates: Requirements 1.4**

    生产里单趟自己那个 `*.materializing` 临时文件的 `finally` 只有 `tmp.unlink()`、**没有**
    release。这是不对称的，所以要么它是缺陷、要么有理由 —— 本条把理由做成运行时判据：
    `*.materializing` 从头到尾**没进过**作用域缓存（它被 `write_bytes` 写出来、立刻
    `os.replace` 改名，没有任何代码去解析它）⇒ 它上面没有句柄可释放。

    这条同时是**未来的守卫**：哪天有人在改名前去反读 `tmp`（例如想就地校验一下），它会立刻
    红，提醒补上 release —— 否则 Windows 上那个 `unlink` 会变成偶发 PermissionError。
    """
    with scoped_cache_witness() as cached:
        world.materialize("handle-release-materializing-probe.xlsx")
    assert cached, "一个文件都没进作用域缓存 ⇒ 观察者没装上，本条是空转"
    offenders = sorted({name for name, _ in cached if name.endswith(".materializing")})
    assert offenders == [], (
        f"`*.materializing` 进了作用域缓存：{offenders} ⇒ 它上面有句柄，而生产在删它之前"
        "**没有** release（`excel_materialize.materialize_projection_single_pass` 的 finally）"
        "—— Windows 上会偶发 PermissionError，必须补 `release_scoped_workbooks(tmp)`"
    )


# ═══════════════════════════════════════════════════════════════════════════
# §2 链式回落路径：38 个中间产物 —— 以及生产那行 release 是否**承重**
# ═══════════════════════════════════════════════════════════════════════════


def test_the_chained_fallback_releases_every_temp_substrate_before_deleting_it(
    world: D4World,
) -> None:
    """**Validates: Requirements 1.4**

    链式回落是 decline 三条（插行 / openpyxl 全量重写 / payload 冲突）的正式路径（design 附录
    A.7 末段），盘上的句柄压力比单趟大一个数量级：38 个中间产物**每一个都被当成下一趟的
    substrate 解析过** ⇒ 每一个都进过缓存、每一个都要先释放才能删。

    三条一起才不空转：

    * 中间产物**真的进过缓存**（否则「先释放再删」无对象）；
    * 每一个被删掉的中间产物都**先被 release 过**（生产 `finally` 里那两行的顺序）；
    * 它们现在**都不在盘上**了（结果面；任务 5 的原子性判据从另一个角度也盯着这条）。
    """
    counter = MaterializeCallCounter()
    with force_chained_path(), temp_file_witness() as created, release_witness() as released:
        with scoped_cache_witness() as cached, counter.installed():
            world.materialize("handle-release-chained.xlsx")

    assert counter.trip_count == BASELINE_BINDINGS, (
        f"没走链式回落：趟数 {counter.trip_count} ≠ {BASELINE_BINDINGS}"
    )
    intermediates = [Path(name) for name in created]
    assert len(intermediates) == BASELINE_BINDINGS - 1, (
        f"中间产物创建数 {len(intermediates)} ≠ {BASELINE_BINDINGS - 1}（末趟直写 output）"
    )
    names = {path.name for path in intermediates}
    cached_names = {name for name, _ in cached}
    assert names <= cached_names, (
        f"有 {len(names - cached_names)} 个中间产物从未进过作用域缓存："
        f"{sorted(names - cached_names)[:5]} ⇒ 它们上面没有句柄，「先释放再删」对它们是空转"
    )
    released_names = set(released)
    assert names <= released_names, (
        f"有 {len(names - released_names)} 个中间产物被删之前没有 release："
        f"{sorted(names - released_names)[:5]} ⇒ Windows 上那次 unlink 靠运气"
    )
    left = [path for path in intermediates if path.exists()]
    assert left == [], f"中间产物仍在盘上：{[p.name for p in left]}"


def test_the_chained_deletion_really_depends_on_the_production_release_call(
    world: D4World, tmp_path: Path
) -> None:
    """**Validates: Requirements 1.4**

    🔴 **生产调用点承重反证。** 上一条留着 release 跑一遍全绿，只说明「没坏」，不说明它有用。
    这一条把 `adapters.excel` 里的 `release_scoped_workbooks` 换成 no-op，真库链式路径必须
    **当场炸**：`finally` 里第一个中间产物的 `unlink(missing_ok=True)` 在 Windows 上抛
    `PermissionError WinError 32`，materialize 整趟失败，盘上留下一串删不掉的中间产物。

    这就是 design 六「不引入 workbook 的模块级长存缓存」那条非目标的实测依据 —— 长存缓存
    等于把这里的 no-op 变成永久状态。

    ⚠️ 本条会真的在盘上留下残留（那正是它要证明的事），判据末尾用
    `scan`/`diff_scans`（复用任务 5 的残留扫描机具，不另造一套）把残留量出来再清掉。
    """
    output = world.staged("handle-release-neutered.xlsx")
    before = scan(tmp_path, world.staged_dir)
    with force_chained_path(), temp_file_witness() as created, neutered_release() as skipped:
        if _ON_WINDOWS:
            with pytest.raises(PermissionError) as raised:
                world.adapter.materialize(
                    substrate=world.base,
                    projection=world.projection,
                    output=output,
                    contract=world.contract,
                )
            assert raised.value.winerror == WINERROR_SHARING_VIOLATION, (
                f"抛的 PermissionError winerror={raised.value.winerror}，"
                f"不是共享冲突 {WINERROR_SHARING_VIOLATION}"
            )
        else:
            world.adapter.materialize(
                substrate=world.base,
                projection=world.projection,
                output=output,
                contract=world.contract,
            )
    assert skipped, (
        "被掐死的 release 一次都没被调用 ⇒ 生产写盘路径压根没走到那行，本条反证无对象"
        "（observer 打在 adapters.excel 的模块属性上，import 形态若改成 `EE.release_…(…)` "
        "则需同步改观察者）"
    )

    leftovers = [Path(name) for name in created if Path(name).exists()]
    # 作用域已随异常退出 ⇒ 句柄全关 ⇒ 此刻可以删掉。删之前先把事实记下来。
    residue = diff_scans(before, scan(tmp_path, world.staged_dir))
    for path in leftovers:
        path.unlink(missing_ok=True)

    if _ON_WINDOWS:
        assert leftovers, (
            "release 被掐死却一个残留都没有 ⇒ 要么中间产物没进缓存、要么 unlink 在本机不受"
            "句柄影响：两种情况下「生产那行 release 承重」这个结论都没有被证明"
        )
        assert len(leftovers) == BASELINE_BINDINGS - 1, (
            f"残留 {len(leftovers)} 个 ≠ 中间产物总数 {BASELINE_BINDINGS - 1}：清理在第一个"
            "就抛了 ⇒ 后面的一个都没删过，数目应当相等（对不上说明清理结构变了）"
        )
    else:  # pragma: no cover - 本平台为 win32；换平台时如实记录 POSIX 语义
        assert leftovers == [], (
            f"POSIX 上不该有残留（已打开的文件也删得掉）：{[p.name for p in leftovers]}"
        )
        assert residue.added == (), f"POSIX 上扫描面多出条目：{residue.added}"


# ═══════════════════════════════════════════════════════════════════════════
# §3 结构守卫：「谁删文件，谁先释放句柄」这条纪律不得被后来的改动破掉
# ═══════════════════════════════════════════════════════════════════════════

_ADAPTER_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "services"
    / "workpaper_sync"
    / "adapters"
    / "excel.py"
)
def _unlink_receiver(statement: ast.stmt) -> str | None:
    """这条语句**本身**是否就是一次 `X.unlink(...)`；是则返回 `X` 的源码写法。

    只认叶子语句（`ast.Expr` 包一个 `Attribute` 调用）。首版按 `ast.unparse(statement)` 里有没有
    `.unlink(` 判，当场被自己咬：`ast.unparse` 会把**整棵子树**摊平，于是外层的 `try:` /
    `for:` / `if:` 语句文本里都含 `.unlink(`，同一处删除被算成 5~8 处，而且外层语句的「前一条」
    必然不是 release ⇒ 三处写对了的生产代码被报成违规。
    """
    if not isinstance(statement, ast.Expr):
        return None
    call = statement.value
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
        return None
    if call.func.attr != "unlink":
        return None
    return ast.unparse(call.func.value)


def _is_release_of(statement: ast.stmt, receiver: str) -> bool:
    """这条语句是否就是 `release_scoped_workbooks(<receiver>)`。"""
    if not isinstance(statement, ast.Expr):
        return False
    call = statement.value
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
        return False
    if call.func.id != "release_scoped_workbooks" or len(call.args) != 1:
        return False
    return ast.unparse(call.args[0]) == receiver


def _unlink_sites_without_release(source: str, *, function: str) -> tuple[list[str], int]:
    """`function` 里每处 `X.unlink(...)` 的前一条语句是否为 `release_scoped_workbooks(X)`。

    返回 `(违规清单, 命中的 unlink 处数)` —— 第二项是**分母**：一处都没找到时「零违规」是空转
    （函数被改名 / 清理搬走了，判据必须看得见这件事）。

    判据落 **AST 结构**而不是子串：本文件与生产注释里都写着「release 之后再 unlink」这句话，
    子串型判据会被注释本身糊成绿。逐 block（`body`/`orelse`/`finalbody`）看**相邻**语句，
    因为生产的形态就是这两行贴在一起（`for path in tmp_paths:` 与两个 `if … is not None:`）。

    形态覆盖自检：函数里 `.unlink` 的 `Call` 节点总数必须等于被识别成叶子语句的处数。不等说明
    出现了本检查器不认的写法（`x = p.unlink()`、`await`、推导式里删…），那时**报错而不是放过**
    —— 检查器看不懂的形态不能算通过。
    """
    tree = ast.parse(source)
    target = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function
        ),
        None,
    )
    assert target is not None, f"{function} 不在 {_ADAPTER_SOURCE.name} 里了 ⇒ 判据的分母没了"

    offenders: list[str] = []
    hits = 0
    for node in ast.walk(target):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if not isinstance(block, list):
                continue
            for index, statement in enumerate(block):
                receiver = _unlink_receiver(statement)
                if receiver is None:
                    continue
                hits += 1
                previous = block[index - 1] if index else None
                if previous is None or not _is_release_of(previous, receiver):
                    offenders.append(
                        f"{function}: `{ast.unparse(statement)}` 之前没有 "
                        f"release_scoped_workbooks({receiver})（前一条是 "
                        f"`{ast.unparse(previous) if previous is not None else '<块首>'}`）"
                    )
    every_call = sum(
        1
        for node in ast.walk(target)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "unlink"
    )
    assert every_call == hits, (
        f"{function} 里有 {every_call} 次 `.unlink` 调用，但只有 {hits} 处被识别成"
        "「独立语句」形态 ⇒ 出现了本检查器不认的写法，判据会静默漏掉它，必须扩展 "
        "`_unlink_receiver`"
    )
    return offenders, hits


def test_every_unlink_in_the_materialize_scope_is_preceded_by_a_release() -> None:
    """**Validates: Requirements 1.4**

    `_materialize_within_scope` 是**在作用域内**删文件的那个函数（`with workbook_read_scope():`
    包着它），它删的三种文件（链式中间产物 / `repaired` / `g7_sanitized`）都会被当成 substrate
    解析进缓存 ⇒ 每一处 `unlink` 之前都必须有对同一个对象的 `release_scoped_workbooks`。

    运行时判据只能证明「今天这条路径上成立」；这条结构判据守的是「以后新加一处 unlink 时也
    成立」—— 真库上句柄泄漏表现为**偶发** PermissionError，靠跑一次测试抓不到。
    """
    offenders, hits = _unlink_sites_without_release(
        _ADAPTER_SOURCE.read_text(encoding="utf-8"), function="_materialize_within_scope"
    )
    assert hits == 3, (
        f"`_materialize_within_scope` 里找到 {hits} 处 unlink，预期 3（链式中间产物 / "
        "repaired / g7_sanitized）—— 结构变了就同步刷新本数字，不要放宽判据"
    )
    assert offenders == [], "\n".join(offenders)


def test_the_release_before_unlink_checker_is_not_a_no_op() -> None:
    """**Validates: Requirements 1.4**

    上一条的反证：把同一个检查器喂一段**缺** release 的源码，它必须报出来。
    少了这条，检查器哪天写歪（正则不匹配、`function` 找错）会变成一条永远绿的判据。
    """
    source = (
        "def _materialize_within_scope(self):\n"
        "    try:\n"
        "        pass\n"
        "    finally:\n"
        "        for path in tmp_paths:\n"
        "            release_scoped_workbooks(path)\n"
        "            path.unlink(missing_ok=True)\n"
        "        if repaired is not None:\n"
        "            repaired.unlink(missing_ok=True)\n"
    )
    offenders, hits = _unlink_sites_without_release(
        source, function="_materialize_within_scope"
    )
    assert hits == 2, hits
    assert len(offenders) == 1 and "repaired" in offenders[0], offenders


def test_the_verify_side_temp_files_never_enter_the_scope_cache(
    world: D4World,
) -> None:
    """**Validates: Requirements 1.4**

    🔴 **触类旁通的结果，如实登记。** 全仓 grep `unlink` 之后，写盘/校验面上只有两处删除
    **没有**配 release：`verify_unmanaged_regions` 的 `d429_before`（转置 sheet 重投影副本）
    与 `g7_before_sanitized`。本条把「它们为什么不需要 release」做成运行时判据而不是读代码
    下结论：verify 全程只用 `zipfile` 与字节比对，不走 `_read_cell_view` ⇒ 这两个临时文件
    从不进作用域缓存、上面没有句柄。

    D4 有 2 张转置 sheet ⇒ `d429_before` 这条路径是**真实被走到**的（`temp_file_witness` 的
    清册给分母），不是「反正没命中所以绿」。

    ⚠️ 本条**不断言 verify 的结论**：这里传的是裸 before/after（不带 row_shift / propagation
    声明），verify 判等价与否是任务 9 的命题。异常照样接住并继续检查句柄面 —— 把两件事混在
    一条判据里，失败时分不清是句柄泄漏还是 verify 判据变了。
    """
    output = world.materialize("handle-release-verify-probe.xlsx")
    verdict: BaseException | None = None
    with workbook_read_scope():
        with temp_file_witness() as created, scoped_cache_witness() as cached:
            try:
                world.adapter.verify_unmanaged_regions(
                    before=world.base, after=output, contract=world.contract
                )
            except Exception as exc:  # noqa: BLE001 - 结论归任务 9，本条只看句柄
                verdict = exc

    verify_temps = [
        Path(name)
        for name in created
        if Path(name).name.endswith((".transposed-before.xlsx", ".g7-noif-before.xlsx"))
    ]
    assert verify_temps, (
        "verify 一个临时副本都没建过 ⇒ 本条没有被判对象（D4 有 2 张转置 sheet，"
        f"`d429_before` 本应被创建；verify 结论={verdict!r}）"
    )
    cached_names = {name for name, _ in cached}
    offenders = sorted({path.name for path in verify_temps} & cached_names)
    assert offenders == [], (
        f"verify 的临时副本进了作用域缓存：{offenders} ⇒ 它们上面有句柄，而生产删它们之前"
        "**没有** release（`verify_unmanaged_regions` 的 finally）—— Windows 上会偶发 "
        "PermissionError，必须补 `release_scoped_workbooks`"
    )
    left = [path for path in verify_temps if path.exists()]
    assert left == [], f"verify 的临时副本仍在盘上：{[p.name for p in left]}"
