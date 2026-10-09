# -*- coding: utf-8 -*-
"""binding 写入失败 ⇒ **整趟失败、磁盘零残留**（spec oo-single-pass-materialize-and-room-leave）。

Requirements: **1.3**　　Property: **P3**　　design: 二.3「失败即整趟回滚」

═══ 三个断言面，各自在钉什么 ═══

| 面 | 钉住的事 | 本文件怎么验 |
|---|---|---|
| ① 无 staged artifact | 半成品不得被当产物发布 | `output` **不存在**（新写）/ **逐字节未变**（已有产物被重物化时）两种形态分开断言；⚠️ 原子改名**之后**还有一段写入，边界另有一条判据钉住（见下） |
| ② 临时目录扫描为空 | 不得留写了一半的临时文件 | 把 `tempfile.tempdir` 重定向到私有目录 ⇒ 扫描面 = workdir（含 `.staging`）+ 该私有目录，**前后快照求差** |
| ③ DB 无半条记录 | 不得留半条库记录 | **见下面「③ 的诚实答案」** —— 不是在这里数行数 |

① 不能只断「output 不存在」：链式路径的中间产物本来就不在 `output` 上（它们是 `tempfile`
建的中间文件）。只看 `output` 的判据对「临时目录里躺着 38 个中间产物」一个字都不会说。
所以②是独立的一面，而且是**目录求差**而不是「猜几个文件名去查」—— 猜名字会漏掉猜不到的。

═══ ③「DB 无半条记录」的诚实答案：materialize **根本不碰数据库** ═══

实证（`test_the_write_path_imports_no_database_module` + `test_no_database_access_...`）：

* `excel_materialize.py` / `adapters/excel.py` / `excel_extract.py` / `workpaper_sync/models.py`
  的**全部** import（含函数体内的延迟 import）里没有任何 DB 模块 —— 没有 sqlalchemy、没有
  `app.core.database`、没有 session、没有 repository；
* 一次**注入失败**的 materialize 全程，SQLAlchemy 侧的 `Engine.connect` /
  `AsyncEngine.connect` / `Session.execute` / `AsyncSession.execute` 调用数为 **0**（观察者
  自身的非空转由 `test_the_database_witness_is_not_a_no_op` 反证）。

⚠️ 诚实边界（不把话说过头）：上面第一条是**直接** import 面的完整扫描，不是传递闭包 ——
`workpaper_sync` 包里确实有 `repository.py` 与 ORM 模型模块，同包其它模块会用到它们。本文件
的主张是「写盘这条路径上没有 session」，由第二条**运行时**证据支撑，而不是由「整个包都不碰库」
这种更强也更假的说法支撑。

那么 DB 侧的原子性**真正住在哪**：`ContentMutationService.commit()`。它的顺序是
（该方法 docstring 自陈、`test_db_atomicity_lives_in_content_mutation_commit` 按 AST 钉住）：

    4. materialize → 反读等值 → 未管理区域比对（**全在事务外**）
    5. publish artifact（文件侧，此刻对库不可见 = orphan）
    6. **一个** DB 事务：revision CAS → content version → representation → pointer → outbox
       → 恰一次 commit（`_CommitLatch`）

⇒ binding 写入失败发生在第 4 步，**第 6 步根本不会开始**：不是「写了半条再回滚」，而是
一行都还没写。本文件因此**不**伪造一条「查库发现 0 行」的断言 —— 那条断言在任何实现下都绿
（连 DB 都没连过），是假绿；能证伪的是「写盘层拿不到 session」+「全程零 DB 调用」这两条。
需要 PG 的那条判据（`_stage_and_verify` 抛错 ⇒ 事务零写入）属 coordinator 层，归
`test_task15_content_mutation*.py` 的事务见证机制（`_TransactionWitness` / `_CommitLatch`），
不在本任务范围内。

═══ 覆盖面（k × 路径 × 注入点）═══

* **k**：第一个 / 中间 / 最后一个 binding。只测最后一个会漏掉「前面已经写了东西才失败」；
  只测第一个会漏掉「累积到一半才失败」。
* **路径**：单趟（默认）**与**链式（`force_chained_path()`，decline 三条的正式回落路径）。
  链式天然有「前 N 个 binding 已落盘」的中间态（design 二.3 点名的那条），必须显式钉。
* **注入点**三处，越靠后盘上的中间态越真：
  1. `_plan_materialize_step`（算计划时炸）—— 单趟侧此刻一个字节都没写（单趟把全部计划
     排在全部写入之前，这正是 design 二.3 说「单趟让这条更容易做实」的机制）；链式侧此刻
     前 k 个中间产物**已在盘上**；
  2. `_apply_step_to_bytes`（改字节时炸）—— 单趟侧已在内存里叠了 k−1 个 binding 的改写；
  3. `os.replace(tmp, output)`（改名时炸）—— 此刻 `*.materializing` **真的在盘上且非空**
     （探针记下它的字节数：实测 237925），是唯一能让「写了一半的临时文件」真实存在的注入点。
     需求 1.3 的「不得留下写了一半的临时文件」字面上说的就是它。

═══ 2026-09-22 真库实测结论（22 条判据 / 15 次注入失败的 materialize）═══

**binding 写入失败**（需求 1.3 的正文，14 次）全部：`output` 不存在或**逐字节未变**、扫描面
新增条目 **0**、DB 调用 **0**。分路径的中间态：

| 现场 | 盘上中间态（失败那一刻真实存在） | 失败后 |
|---|---|---|
| 单趟 · 计划/改写阶段 | 无（中间态全在内存）—— 临时文件创建数 0 | 零残留 |
| 单趟 · 改名阶段 | `*.materializing` **237925 字节**（整本工作簿量级；与最终产物 246110 的差额见下） | 被 `finally` 删净 |
| 链式 · k=first/middle/last | 中间产物 **1 / 20 / 38** 个（`trips` = k+1） | 一个不剩 |
| 链式 · 末趟改名 | 38 个中间产物 **+** 237925 字节的 `*.materializing` | 全部删净 |

⇒ 需求 1.3 正文范围内**未发现原子性缺陷**：两条路径都做实了，单趟侧甚至是结构性的（写入只在
最后发生一次），链式侧靠 `finally` 里的 `release_scoped_workbooks + unlink` 清册兜住。

🔴 **实测发现（第 15 次注入，本任务顺带挖出来的）**：`os.replace` **不是**最后一步 —— 改名
之后 `adapter.materialize` 还要把转置 sheet 就地写进 `output`（D4 实测补 8185 字节：237925 →
246110）。那一段抛错会在 `output` 上留下一份「只完成 zip 改写、缺转置列」的文件。判据
`test_writes_continue_after_the_atomic_rename_and_the_residue_is_bounded` 如实钉住这个事实
并把边界锁死（残留**恰好**只有 `output` 一个条目）。

它**不算**需求 1.3 说的「把半成品当 staged artifact 发布」，理由是可查的而不是自我安慰：
`output` 路径由 `_stage_and_verify` 用 `uuid4()` 的 `stage_id` **每次尝试现开**一个 staging
目录算出来 ⇒ 不覆盖任何既有产物、不被下次读到；发布是后面独立的内容寻址
`stage_stream + publish_representation`，materialize 抛错时它压根不执行。所以那是该协议明文
定义的 **orphan**（由 Task 11 reconciliation 收）。要连它一起收干净的正解是「转置写 `tmp`、
改名放最后」，属独立改动，不在本任务内（详见那条判据的 docstring）。

**判据非空转已由定向变异实测**（改生产码、跑判据、复原）：

| 变异 | 结果 |
|---|---|
| `materialize_projection_single_pass` 的 `finally` 不删 `tmp` | 单趟侧两条改名判据**红**：扫描面多出 `atomicity-publish-*.xlsx.materializing`；链式侧仍绿（它的 `.materializing` 由另一处 `finally` 管）⇒ 归因精确 |
| 链式循环 `finally` 里不 `unlink` 中间产物 | 链式 k=first **红 1 个**残留、k=middle **红 20 个**；单趟侧全绿 ⇒ 同样精确。顺带实测确认了 design 二.3 说的「前 N 个 binding 已落盘」中间态**真实存在**（20 个文件躺在临时目录里） |
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import inspect
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest

from app.services.workpaper_sync import excel_materialize as EM
from tests.workpaper_sync.d4_materialize_harness import (
    D4World,
    MaterializeCallCounter,
    build_world,
    force_chained_path,
)
from tests.workpaper_sync.test_single_pass_materialize import BASELINE_BINDINGS

#: 写盘这条路径上的**全部**模块。③ 的静态面扫它们的每一条 import（含函数体内的）。
_WRITE_PATH_MODULES = (
    "app/services/workpaper_sync/excel_materialize.py",
    "app/services/workpaper_sync/adapters/excel.py",
    "app/services/workpaper_sync/excel_extract.py",
    "app/services/workpaper_sync/models.py",
)
#: 只要写盘路径 import 到其中任何一个，「materialize 不碰库」就不再成立。
_DB_IMPORT_MARKERS = (
    "sqlalchemy",
    "asyncpg",
    "psycopg",
    "aiosqlite",
    "app.core.database",
    "app.models",
    "app.repositories",
    "app.crud",
    "app.services.workpaper_sync.repository",
)
#: 生产写盘用的临时文件后缀（`materialize_projection*` 里 `output.name + ".materializing"`）。
_MATERIALIZING_SUFFIX = ".materializing"


class InjectedBindingFailure(RuntimeError):
    """本判据注入的「第 k 个 binding 写入失败」。

    自定义异常类型而不是复用 `RuntimeError`：断言 `pytest.raises` 抓到的**就是它**，才能
    把「注入生效了」与「碰巧撞上别的真实错误」分开 —— 后者也会让 `output` 不存在，于是
    「零残留」会在一个完全不同的原因上变绿。
    """


class InjectedPublishFailure(RuntimeError):
    """在 `os.replace(tmp, output)` 处注入的失败（此刻临时文件已落盘）。"""


# ═══════════════════════════════════════════════════════════════════════════
# 注入：一律拦**生产内核**，只让它抛，不改判据 / 不改 adapter / 不改契约
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class Injection:
    """一次注入的现场记录。`fired` 空 ⇒ 注入根本没打中 ⇒ 判据是空转。"""

    site: str
    victim: str
    fired: list[str] = field(default_factory=list)
    #: `os.replace` 注入点专用：抛错**那一刻**临时文件的存在性与字节数。
    half_written: list[tuple[str, bool, int]] = field(default_factory=list)


@contextlib.contextmanager
def fail_at_plan(victim: str) -> Iterator[Injection]:
    """第 k 个 binding 的**计划**阶段抛错（与 `drop_binding_writes` 同一种注入法）。"""
    record = Injection("plan", victim)
    original = EM._plan_materialize_step

    def poisoned(**kwargs: Any) -> Any:
        binding = kwargs.get("binding")
        if str(getattr(binding, "table_key", binding)) != victim:
            return original(**kwargs)
        record.fired.append(victim)
        raise InjectedBindingFailure(f"注入：binding {victim} 的计划阶段失败")

    EM._plan_materialize_step = poisoned  # type: ignore[assignment]
    try:
        yield record
    finally:
        EM._plan_materialize_step = original  # type: ignore[assignment]


@contextlib.contextmanager
def fail_at_apply(victim: str) -> Iterator[Injection]:
    """第 k 个 binding 的**字节改写**阶段抛错（计划已算完，前 k−1 个改写已叠上）。"""
    record = Injection("apply", victim)
    original = EM._apply_step_to_bytes

    def poisoned(*, source_bytes: bytes, step: Any, definitions: Any) -> Any:
        if str(step.binding.table_key) != victim:
            return original(
                source_bytes=source_bytes, step=step, definitions=definitions
            )
        record.fired.append(victim)
        raise InjectedBindingFailure(f"注入：binding {victim} 的字节改写失败")

    EM._apply_step_to_bytes = poisoned  # type: ignore[assignment]
    try:
        yield record
    finally:
        EM._apply_step_to_bytes = original  # type: ignore[assignment]


@contextlib.contextmanager
def fail_when_publishing(only_target: Path | None = None) -> Iterator[Injection]:
    """在 `os.replace(tmp, output)` 处抛错 —— 此刻 `*.materializing` **真的在盘上**。

    这是唯一能让需求 1.3 那句「不得留下写了一半的临时文件」有真实对象的注入点：另外两个
    注入点都在落盘之前，临时文件压根没被创建过（零残留成立，但成立得太便宜）。

    探针顺手记下抛错那一刻 `src` 的存在性与字节数：事后断言「它不在了」才有分母 ——
    否则「临时文件不存在」可能只是它从未被创建。

    `only_target` 限定「改名到**这个**目标时才炸」。链式路径上每个 binding 都要改一次名，
    不限定就会炸在第 0 趟；限定成 `output` 之后，链式侧会先把前 38 个中间产物真写到盘上、
    再在最后一趟的改名处失败 —— 那是本文件里盘上中间态最重的一种现场。

    只拦 `.materializing` 后缀、其余一律转发给真的 `os.replace`：把 `os.replace` 整个打死
    会把 pytest 自己的临时文件操作也炸掉，那种红与本判据无关。
    """
    record = Injection("publish", str(only_target) if only_target else "<first>")
    original = os.replace

    def poisoned(src: Any, dst: Any, **kwargs: Any) -> Any:
        if not str(src).endswith(_MATERIALIZING_SUFFIX) or (
            only_target is not None and Path(str(dst)) != only_target
        ):
            return original(src, dst, **kwargs)
        path = Path(str(src))
        exists = path.is_file()
        record.half_written.append(
            (str(path), exists, path.stat().st_size if exists else -1)
        )
        record.fired.append(str(dst))
        raise InjectedPublishFailure(f"注入：{path.name} → {Path(str(dst)).name} 改名失败")

    os.replace = poisoned  # type: ignore[assignment]
    try:
        yield record
    finally:
        os.replace = original  # type: ignore[assignment]


# ═══════════════════════════════════════════════════════════════════════════
# 残留扫描：前后快照求差（不是「猜几个文件名去查」）
# ═══════════════════════════════════════════════════════════════════════════


def scan(*roots: Path) -> dict[str, tuple[int, str]]:
    """递归列出扫描面上的每一个条目 → `(字节数, sha256)`（目录记 `(-1, "<dir>")`）。

    连内容摘要一起记，这样「文件数没变但某个文件被改写了」也能被求差看见 —— 只比路径集合
    的快照对「已有产物被半成品覆盖」是瞎的，而那正是需求 1.3 第二句要防的事。
    """
    found: dict[str, tuple[int, str]] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_dir():
                found[str(path)] = (-1, "<dir>")
                continue
            try:
                payload = path.read_bytes()
            except OSError as exc:  # pragma: no cover - 读不到也算异常现场，如实记
                found[str(path)] = (-2, f"<unreadable {exc.__class__.__name__}>")
                continue
            found[str(path)] = (len(payload), hashlib.sha256(payload).hexdigest())
    return found


@dataclass(frozen=True)
class DiskDiff:
    """两次快照之间的**完整**差异（三类各自成项，排序确定）。"""

    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not (self.added or self.removed or self.changed)


def diff_scans(
    before: dict[str, tuple[int, str]], after: dict[str, tuple[int, str]]
) -> DiskDiff:
    return DiskDiff(
        added=tuple(sorted(set(after) - set(before))),
        removed=tuple(sorted(set(before) - set(after))),
        changed=tuple(
            sorted(key for key in set(before) & set(after) if before[key] != after[key])
        ),
    )


@contextlib.contextmanager
def temp_file_witness() -> Iterator[list[str]]:
    """记录本段内经 `tempfile.NamedTemporaryFile` 建出来的**每一个**文件名。

    链式路径正是用它建中间产物（`adapters/excel.py` 的 `NamedTemporaryFile(delete=False)`）。
    有了这份清册，②才不是「目录里没东西」这种可能空转的绿：

    * 链式侧能证明中间产物**真的被创建过** k 个（design 二.3 说的「前 N 个 binding 已落盘」
      中间态确实存在，不是传说），而事后一个不剩；
    * 单趟侧能证明它**一个都没建**（单趟只写一个 `*.materializing` 再改名）—— 两条路径的
      残留面本来就不同，混在一起断言会把这个结构差异糊掉。
    """
    created: list[str] = []
    original = tempfile.NamedTemporaryFile

    def counted(*args: Any, **kwargs: Any) -> Any:
        handle = original(*args, **kwargs)
        created.append(str(getattr(handle, "name", "<anonymous>")))
        return handle

    tempfile.NamedTemporaryFile = counted  # type: ignore[assignment]
    try:
        yield created
    finally:
        tempfile.NamedTemporaryFile = original  # type: ignore[assignment]


@contextlib.contextmanager
def db_access_witness() -> Iterator[list[str]]:
    """记录本段内**任何** SQLAlchemy 连接/执行尝试（不阻断，只记）。

    ③ 的运行时一半。打在 SQLAlchemy 的四个入口上而不是打在 `app.core.database` 上：后者只
    盖住「走平台 session 工厂」这一条路，自己 `create_engine` 也能碰库。观察者自身的非空转
    由 `test_the_database_witness_is_not_a_no_op` 反证。
    """
    calls: list[str] = []
    undo: list[Callable[[], None]] = []

    def wrap(owner: Any, name: str, label: str) -> None:
        original = getattr(owner, name, None)
        if original is None:  # pragma: no cover - 版本差异，缺了就少一个探针
            return

        def counted(*args: Any, **kwargs: Any) -> Any:
            calls.append(label)
            return original(*args, **kwargs)

        undo.append(lambda: setattr(owner, name, original))
        setattr(owner, name, counted)

    from sqlalchemy.engine import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
    from sqlalchemy.orm import Session

    wrap(Engine, "connect", "Engine.connect")
    wrap(AsyncEngine, "connect", "AsyncEngine.connect")
    wrap(Session, "execute", "Session.execute")
    wrap(AsyncSession, "execute", "AsyncSession.execute")
    assert len(undo) == 4, f"DB 观察者只装上了 {len(undo)}/4 个探针 ⇒ ③ 的运行时面有缺口"
    try:
        yield calls
    finally:
        for restore in reversed(undo):
            restore()


# ═══════════════════════════════════════════════════════════════════════════
# 一次「注入失败的 materialize」的全部观测
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class AtomicityObservation:
    """一次注入失败跑完之后，三个断言面各自需要的原始事实。"""

    label: str
    output: Path
    output_sha_before: str | None
    raised: BaseException
    injection: Injection
    diff: DiskDiff
    temp_files_created: tuple[str, ...]
    temp_files_left: tuple[str, ...]
    db_calls: tuple[str, ...]
    trips: int
    single_pass_trips: int
    scanned_roots: tuple[Path, ...]

    @property
    def output_exists(self) -> bool:
        return self.output.is_file()

    @property
    def output_sha_after(self) -> str | None:
        if not self.output.is_file():
            return None
        return hashlib.sha256(self.output.read_bytes()).hexdigest()


def staged_output(world: D4World, label: str) -> Path:
    """本模块每次跑各自的产物路径 —— **唯一**一处构造。

    `fail_when_publishing(only_target=...)` 要在调用点先知道这个路径，而 runner 也要用它。
    两边各拼一次的写法实测立刻咬人：label 与文件名差一个后缀，注入就永远打不中，materialize
    直接成功 ⇒ 判据在「DID NOT RAISE」上红（这次是 `fired` 反空转前提替我们抓到的）。
    """
    return world.staged(f"atomicity-{label}.xlsx")


def run_failing_materialize(
    *,
    world: D4World,
    tmp_root: Path,
    inject: Callable[[], Any],
    label: str,
    chained: bool = False,
    seed_output: bytes | None = None,
    expected_error: type[BaseException] = InjectedBindingFailure,
) -> AtomicityObservation:
    """跑一次**必然失败**的 materialize，并把三个断言面需要的现场全部取回来。

    顺序有意义：先把 `tempfile.tempdir` 重定向到私有目录（扫描面才能既完整又无噪声 ——
    共享的系统临时目录里别的进程随时在写，在它上面求差必然假红），再拍**前**快照，再注入、
    跑、拍**后**快照。

    `seed_output` 非空 ⇒ 先把一份**成功的**产物放到 `output` 上，用来断言需求 1.3 的第二句
    形态：已有 staged 产物在一次失败的重物化后必须**逐字节未变**（而不是「不存在」）。
    """
    private_tmp = tmp_root / "systemp"
    private_tmp.mkdir(parents=True, exist_ok=True)
    output = staged_output(world, label)
    if seed_output is not None:
        output.write_bytes(seed_output)
    sha_before = (
        hashlib.sha256(output.read_bytes()).hexdigest() if output.is_file() else None
    )

    roots = (world.base.parent, private_tmp)
    previous_tempdir = tempfile.tempdir
    tempfile.tempdir = str(private_tmp)
    counter = MaterializeCallCounter()
    try:
        before = scan(*roots)
        with contextlib.ExitStack() as stack:
            record: Injection = stack.enter_context(inject())
            created = stack.enter_context(temp_file_witness())
            db_calls = stack.enter_context(db_access_witness())
            if chained:
                stack.enter_context(force_chained_path())
            stack.enter_context(counter.installed())
            with pytest.raises(expected_error) as raised:
                world.adapter.materialize(
                    substrate=world.base,
                    projection=world.projection,
                    output=output,
                    contract=world.contract,
                )
        after = scan(*roots)
    finally:
        tempfile.tempdir = previous_tempdir

    return AtomicityObservation(
        label=label,
        output=output,
        output_sha_before=sha_before,
        raised=raised.value,
        injection=record,
        diff=diff_scans(before, after),
        temp_files_created=tuple(created),
        temp_files_left=tuple(name for name in created if Path(name).exists()),
        db_calls=tuple(db_calls),
        trips=counter.trip_count,
        single_pass_trips=counter.single_pass_trip_count,
        scanned_roots=roots,
    )


def assert_zero_residue(obs: AtomicityObservation) -> None:
    """三个断言面 + 两条反空转前提，一处不过就报出**完整**现场。

    反空转前提放在最前面：注入没打中（`fired` 空）或异常类型不是注入的那个，后面三条「零
    残留」就可能在一个完全不同的原因上变绿 —— 例如 world 根本没跑起来。
    """
    assert obs.injection.fired, (
        f"[{obs.label}] 注入点 {obs.injection.site} 一次都没打中（victim="
        f"{obs.injection.victim}）⇒ 本判据是空转：materialize 可能压根没走到那个 binding"
    )
    assert isinstance(obs.raised, (InjectedBindingFailure, InjectedPublishFailure)), (
        f"[{obs.label}] materialize 抛的不是注入的异常而是 {obs.raised!r} ⇒ "
        "「零残留」可能来自另一个原因"
    )

    # ① 无 staged artifact：两种形态分开断言，不含糊成一句。
    if obs.output_sha_before is None:
        assert not obs.output_exists, (
            f"[{obs.label}] ① 失败却留下了 staged 产物 {obs.output}"
            f"（{obs.output.stat().st_size} 字节）—— 半成品被当产物发布了"
        )
    else:
        assert obs.output_sha_after == obs.output_sha_before, (
            f"[{obs.label}] ① 已有 staged 产物在一次**失败**的重物化后被改动了："
            f"{obs.output_sha_before} → {obs.output_sha_after}"
        )

    # ② 扫描面求差：新增 = 残留；消失/变更 = 失败路径误伤了既有文件。
    assert obs.diff.added == (), (
        f"[{obs.label}] ② 扫描面上多出了 {len(obs.diff.added)} 个条目（残留）："
        f"{obs.diff.added}；扫描根：{[str(r) for r in obs.scanned_roots]}"
    )
    assert obs.diff.removed == (), (
        f"[{obs.label}] ② 失败路径把既有条目删了：{obs.diff.removed}"
    )
    assert obs.diff.changed == (), (
        f"[{obs.label}] ② 失败路径改动了既有条目：{obs.diff.changed}"
    )
    assert obs.temp_files_left == (), (
        f"[{obs.label}] ② 中间临时文件仍在盘上：{obs.temp_files_left}"
        "（⚠️ Windows 上「删不掉」也可能是句柄未释放而非原子性缺陷 —— 任务 6 专管句柄，"
        "两者要分开归因）"
    )

    # ③ DB：不是「查库 0 行」，而是「全程没碰过库」。理由见模块 docstring。
    assert obs.db_calls == (), (
        f"[{obs.label}] ③ 写盘路径在失败前碰了数据库：{obs.db_calls} —— "
        "materialize 应当是纯文件操作，DB 侧原子性归 ContentMutationService.commit"
    )


# ═══════════════════════════════════════════════════════════════════════════
# world（module 作用域：铺 world 十几秒，全模块共用一份）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> D4World:
    """真 D4 模板 + 真契约 + 真 39 binding，projection 取自 substrate 自身的反读结果。"""
    return build_world(tmp_path_factory.mktemp("d4-atomicity"))


@pytest.fixture(scope="module")
def binding_keys(world: D4World) -> tuple[str, ...]:
    """写入顺序下的 binding table_key 序列（= 契约声明序，两条路径同一序）。"""
    return tuple(str(binding.table_key) for binding in world.adapter._all_bindings())


@pytest.fixture(scope="module")
def good_artifact(world: D4World) -> bytes:
    """一份**成功**物化的产物字节 —— 用作「已有 staged 产物」的种子。

    顺带是个前提自检：world 在没有注入时确实物化得出来。它要是本来就失败，下面每一条
    「失败后零残留」都会在错误的理由上变绿。
    """
    return world.materialize("atomicity-successful-baseline.xlsx").read_bytes()


#: 第 k 个 binding：第一个 / 中间 / 最后一个。只测最后一个会漏掉「前面已经写了东西才失败」；
#: 只测第一个会漏掉「累积到一半才失败」。
K_CASES = (
    ("first", 0),
    ("middle", BASELINE_BINDINGS // 2),
    ("last", BASELINE_BINDINGS - 1),
)


# ═══════════════════════════════════════════════════════════════════════════
# ⓞ 前提：k 的三个取值真的落在 binding 序列的三个位置上
# ═══════════════════════════════════════════════════════════════════════════


def test_the_victim_indices_really_span_the_binding_list(
    binding_keys: tuple[str, ...]
) -> None:
    """**Validates: Requirements 1.3**

    参数化里的 `first/middle/last` 是**下标**，它们指向谁取决于真实契约。契约受管表集合一变，
    下标可能越界或三者撞成同一个 binding —— 那时「k 的三种位置」就名存实亡了。先钉住它。
    """
    assert len(binding_keys) == BASELINE_BINDINGS, (
        f"binding 数 {len(binding_keys)} ≠ 基线 {BASELINE_BINDINGS} —— 契约变了是正当变化，"
        "但要同步刷新本模块的 k 取值（否则 middle/last 指向的位置已经不是原来那个意思）"
    )
    victims = [binding_keys[index] for _, index in K_CASES]
    assert len(set(victims)) == 3, f"三个 k 撞成了同一个 binding：{victims}"
    assert victims[0] == binding_keys[0] and victims[-1] == binding_keys[-1]


# ═══════════════════════════════════════════════════════════════════════════
# ① 注入点一：计划阶段失败（k × 两条路径 = 6 条）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("chained", [False, True], ids=["single_pass", "chained"])
@pytest.mark.parametrize("position,index", K_CASES, ids=[name for name, _ in K_CASES])
def test_plan_stage_failure_leaves_zero_residue(
    world: D4World,
    binding_keys: tuple[str, ...],
    tmp_path: Path,
    position: str,
    index: int,
    chained: bool,
) -> None:
    """**Validates: Requirements 1.3**　**Property: P3**

    第 k 个 binding 在**算计划**时抛错 ⇒ 整趟失败、盘上零残留。

    两条路径此刻的中间态完全不同，因此断言也分开：

    * **单趟**：全部计划排在全部写入之前 ⇒ 此刻一个字节都没写过，连临时文件都没创建过。
      这正是 design 二.3 说「单趟化让失败回滚更容易做实」的机制本身，钉住它免得将来有人
      把「边算边写」改回去（那样这条会红在 `temp_files_created`/`trips` 上）。
    * **链式**：前 k 个中间产物**已经在盘上**（design 二.3 点名的「前 N 个 binding 已落盘」
      中间态）⇒ 判据要的是「失败后它们一个不剩」，而不是「它们从未存在」。
    """
    victim = binding_keys[index]
    obs = run_failing_materialize(
        world=world,
        tmp_root=tmp_path,
        inject=lambda: fail_at_plan(victim),
        label=f"plan-{position}-{'chained' if chained else 'single'}",
        chained=chained,
    )
    assert_zero_residue(obs)
    assert victim in str(obs.raised), f"异常没带上受害 binding：{obs.raised}"

    if chained:
        # 趟数 = 已发起的 `materialize_projection` 次数（计数器在调用**前**记）⇒ 恰 k+1：
        # 前 k 趟真写完了，第 k+1 趟炸在计划上。这是「中间态真实存在」的直接证据。
        assert obs.trips == index + 1, (
            f"链式在第 {index} 个 binding 失败，趟数应为 {index + 1}，实得 {obs.trips}"
        )
        # 末趟写的是 `output` 本身、不建临时文件 ⇒ 最后一个 k 少一个。
        expected_created = min(index + 1, BASELINE_BINDINGS - 1)
        assert len(obs.temp_files_created) == expected_created, (
            f"链式中间临时文件创建数 {len(obs.temp_files_created)} ≠ 预期 "
            f"{expected_created}（前 k 趟各一个）：{obs.temp_files_created}"
        )
        if index > 0:
            assert obs.temp_files_created, (
                "链式在中途失败却一个中间文件都没建过 ⇒ 「前 N 个已落盘」这条中间态不存在，"
                "本条判据对链式路径是空转，需要重新设计注入点"
            )
    else:
        assert obs.trips == 0 and obs.single_pass_trips == 0, (
            f"单趟在计划阶段就失败，不该记成一趟写入：趟数 {obs.trips}"
            f"（单趟 {obs.single_pass_trips}）"
        )
        assert obs.temp_files_created == (), (
            f"单趟在写入之前失败却建了临时文件：{obs.temp_files_created} —— "
            "「全部计划先于全部写入」这条结构性质变了"
        )


# ═══════════════════════════════════════════════════════════════════════════
# ② 注入点二：字节改写阶段失败（单趟 × k 三种 + 链式中间一条）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("position,index", K_CASES, ids=[name for name, _ in K_CASES])
def test_single_pass_write_stage_failure_leaves_zero_residue(
    world: D4World,
    binding_keys: tuple[str, ...],
    tmp_path: Path,
    position: str,
    index: int,
) -> None:
    """**Validates: Requirements 1.3**　**Property: P3**

    单趟路径在第 k 个 binding 的 `_apply_step_to_bytes` 抛错 —— 此刻前 k−1 个 binding 的改写
    **已经叠在内存字节上**了。这是单趟侧真正的「写到一半」现场（计划阶段那条还没开始写）。

    单趟把中间态留在内存里、只在全部 binding 都改完之后才落一次盘，所以「零残留」在这条
    路径上是**结构性**的而不是靠清理代码兜的：`k=last`（前 38 个 binding 的改写都叠好了，
    就差最后一个）也一样零残留。
    """
    victim = binding_keys[index]
    obs = run_failing_materialize(
        world=world,
        tmp_root=tmp_path,
        inject=lambda: fail_at_apply(victim),
        label=f"apply-{position}-single",
    )
    assert_zero_residue(obs)
    assert obs.temp_files_created == (), (
        f"单趟侧不该建任何中间临时文件：{obs.temp_files_created}"
    )
    assert obs.trips == 0 and obs.single_pass_trips == 0, (
        f"失败的单趟被记成了一趟写入：{obs.trips}/{obs.single_pass_trips}"
    )


def test_chained_write_stage_failure_leaves_zero_residue(
    world: D4World, binding_keys: tuple[str, ...], tmp_path: Path
) -> None:
    """**Validates: Requirements 1.3**　**Property: P3**

    链式路径在中间某个 binding 的 `_apply_step_to_bytes` 抛错：前 k 个中间产物已落盘、第 k+1
    个中间文件也已被创建（`NamedTemporaryFile` 先建空文件再写）⇒ 失败后必须一个不剩。

    只测中间 k 一条：链式的清理逻辑是**同一个** `finally`（按 `tmp_paths` 清册逐个
    `release_scoped_workbooks` + `unlink`），k 换成别的值走的是同一段代码 —— 而计划阶段那条
    判据已经把 k 的三个位置在链式上跑遍了。这里要补的是「炸在写字节时」这个更晚的时刻。
    """
    index = BASELINE_BINDINGS // 2
    victim = binding_keys[index]
    obs = run_failing_materialize(
        world=world,
        tmp_root=tmp_path,
        inject=lambda: fail_at_apply(victim),
        label="apply-middle-chained",
        chained=True,
    )
    assert_zero_residue(obs)
    assert obs.trips == index + 1, f"趟数 {obs.trips} ≠ {index + 1}"
    assert len(obs.temp_files_created) == index + 1, (
        f"中间临时文件创建数 {len(obs.temp_files_created)} ≠ {index + 1}："
        f"{obs.temp_files_created}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# ③ 注入点三：改名阶段失败 —— 唯一能让「写了一半的临时文件」真实存在的现场
# ═══════════════════════════════════════════════════════════════════════════


def _assert_half_written_temp_was_real_and_is_gone(obs: AtomicityObservation) -> None:
    """探针记下的 `*.materializing` 必须**当时非空、事后不存在**。

    两头都要：只断「事后不存在」的话，临时文件从未被创建也算绿 —— 那正是需求 1.3 这句话
    最容易被空转掉的地方。
    """
    assert len(obs.injection.half_written) == 1, (
        f"[{obs.label}] 期望恰一次改名被拦下，实得 {obs.injection.half_written}"
    )
    path, existed, size = obs.injection.half_written[0]
    assert existed and size > 0, (
        f"[{obs.label}] 抛错那一刻 {path} 不存在或是空文件（{size} 字节）⇒ "
        "「写了一半的临时文件」这个对象根本不存在，本条判据是空转"
    )
    assert not Path(path).exists(), (
        f"[{obs.label}] 半成品临时文件仍在盘上：{path}（{size} 字节）—— "
        "`finally: if tmp.exists(): tmp.unlink()` 没兜住"
    )


@pytest.mark.parametrize("chained", [False, True], ids=["single_pass", "chained"])
def test_publish_stage_failure_keeps_the_existing_artifact_and_removes_the_temp(
    world: D4World, good_artifact: bytes, tmp_path: Path, chained: bool
) -> None:
    """**Validates: Requirements 1.3**　**Property: P3**

    最重的一种现场，三件事同时成立：

    1. `output` 上**已有**一份成功的 staged 产物（重物化的真实形态）；
    2. 一份**完整写好**的 `*.materializing` 临时文件正躺在盘上（探针记下它的字节数）；
    3. 改名（`os.replace`）失败。

    要求：已有产物**逐字节未变**（`os.replace` 的原子性 + 失败不得半覆盖），临时文件被删净。

    链式侧额外把「中间态最重」的情形跑到：限定只在改名到 `output` 时炸 ⇒ 前 38 个 binding
    的中间产物**都真写到盘上**了，才在最后一趟失败。
    """
    label = f"publish-{'chained' if chained else 'single'}"
    output = staged_output(world, label)
    obs = run_failing_materialize(
        world=world,
        tmp_root=tmp_path,
        inject=lambda: fail_when_publishing(only_target=output),
        label=label,
        chained=chained,
        seed_output=good_artifact,
        expected_error=InjectedPublishFailure,
    )
    assert obs.output == output, f"注入目标与实际产物路径不一致：{output} / {obs.output}"
    assert_zero_residue(obs)
    _assert_half_written_temp_was_real_and_is_gone(obs)

    # 被拦下的临时文件必须是**整本工作簿量级**的产物，不是一个几字节的残渣（`size > 0`
    # 这个下界太松）。
    #
    # 🔴 实测 237925 字节 < 成功产物 246110 字节，差 8185 —— 这不是「写了一半」，而是一个
    #    真实结构：zip 级改写的产物在 `os.replace` 处就完整了，**转置 sheet 是在改名之后**
    #    才写进 `output` 的（`_transposed_materialize_file(output, ...)`，见
    #    `test_writes_continue_after_the_atomic_rename_and_the_residue_is_bounded`）。
    #    所以这里断的是「同量级且小于最终产物」，而不是相等 —— 断相等会把一个与本判据无关的
    #    实现结构（转置后写）误报成原子性缺陷。
    _, _, size = obs.injection.half_written[0]
    assert size < len(good_artifact), (
        f"被拦下的临时文件 {size} 字节 ≥ 成功产物 {len(good_artifact)} 字节 —— "
        "转置 sheet 改到改名之前去了？那是好事，但本条的量化关系要同步更新"
    )
    assert size > len(good_artifact) * 0.9, (
        f"被拦下的临时文件只有 {size} 字节（成功产物 {len(good_artifact)}）—— "
        "它不是整本工作簿量级的产物，本条对「半成品」的分母不成立"
    )

    if chained:
        assert obs.trips == BASELINE_BINDINGS, (
            f"限定在末趟改名失败，前 {BASELINE_BINDINGS - 1} 趟应当都跑完："
            f"趟数 {obs.trips}"
        )
        assert len(obs.temp_files_created) == BASELINE_BINDINGS - 1, (
            f"中间临时文件创建数 {len(obs.temp_files_created)} ≠ "
            f"{BASELINE_BINDINGS - 1}：{obs.temp_files_created}"
        )


def test_publish_stage_failure_publishes_nothing_when_there_was_no_artifact(
    world: D4World, tmp_path: Path
) -> None:
    """**Validates: Requirements 1.3**

    同一个注入点的另一种形态：`output` 此前**不存在** ⇒ 失败后它必须仍然不存在。

    与上一条分开写：那条断的是「已有产物未变」，这条断的是「不产出半成品产物」。合成一条的
    话，`output` 在失败后被创建出来（半成品发布）与既有产物被覆盖，在失败信息里分不开。
    """
    label = "publish-fresh-single"
    output = staged_output(world, label)
    output.unlink(missing_ok=True)
    obs = run_failing_materialize(
        world=world,
        tmp_root=tmp_path,
        inject=lambda: fail_when_publishing(only_target=output),
        label=label,
        expected_error=InjectedPublishFailure,
    )
    assert obs.output == output, f"注入目标与实际产物路径不一致：{output} / {obs.output}"
    assert obs.output_sha_before is None, "前提没成立：output 本来就该不存在"
    assert_zero_residue(obs)
    _assert_half_written_temp_was_real_and_is_gone(obs)


# ═══════════════════════════════════════════════════════════════════════════
# ④ 判据机器本身可反证（毫秒级，不碰 world）
# ═══════════════════════════════════════════════════════════════════════════


def test_the_residue_scan_catches_a_leftover_file(tmp_path: Path) -> None:
    """**Validates: Requirements 1.3**

    扫描面必须真的看得见残留。三类各验一次：新增文件 / 内容被改写 / 既有文件被删。

    只验「新增」是不够的：需求 1.3 第二句要防的是「半成品当产物发布」，它在已有产物上表现为
    **内容被改写**而不是「多了一个文件」—— 只比路径集合的快照对它是瞎的。
    """
    (tmp_path / "keep.bin").write_bytes(b"keep")
    (tmp_path / "doomed.bin").write_bytes(b"doomed")
    before = scan(tmp_path)

    (tmp_path / "leftover.materializing").write_bytes(b"half written")
    (tmp_path / "keep.bin").write_bytes(b"tampered")
    (tmp_path / "doomed.bin").unlink()
    diff = diff_scans(before, scan(tmp_path))

    assert not diff.clean
    assert diff.added == (str(tmp_path / "leftover.materializing"),), diff.added
    assert diff.changed == (str(tmp_path / "keep.bin"),), diff.changed
    assert diff.removed == (str(tmp_path / "doomed.bin"),), diff.removed
    # 反向：什么都不动 ⇒ 干净。判据不是「总报红」。
    assert diff_scans(scan(tmp_path), scan(tmp_path)).clean


def test_assert_zero_residue_is_red_on_residue(tmp_path: Path) -> None:
    """**Validates: Requirements 1.3**

    把一个「有残留」的观测喂给断言函数，它必须红。少了这条，`assert_zero_residue` 哪天被改成
    空壳（例如某个断言被注释掉）没有任何判据看得见。
    """
    residue = tmp_path / "left.materializing"
    residue.write_bytes(b"x")
    dirty = AtomicityObservation(
        label="synthetic",
        output=tmp_path / "never-written.xlsx",
        output_sha_before=None,
        raised=InjectedBindingFailure("注入：binding victim 的计划阶段失败"),
        injection=Injection("plan", "victim", fired=["victim"]),
        diff=DiskDiff(added=(str(residue),), removed=(), changed=()),
        temp_files_created=(str(residue),),
        temp_files_left=(str(residue),),
        db_calls=(),
        trips=0,
        single_pass_trips=0,
        scanned_roots=(tmp_path,),
    )
    with pytest.raises(AssertionError, match="残留"):
        assert_zero_residue(dirty)


def test_the_injection_fired_guard_is_red_when_nothing_was_injected(
    tmp_path: Path,
) -> None:
    """**Validates: Requirements 1.3**

    反空转前提自身的反证：`fired` 为空（注入没打中）时必须红，哪怕盘上确实零残留。
    否则「victim 名字写错了」这类失效会表现为一条永远绿的判据。
    """
    vacuous = AtomicityObservation(
        label="synthetic",
        output=tmp_path / "never-written.xlsx",
        output_sha_before=None,
        raised=InjectedBindingFailure("注入没打中"),
        injection=Injection("plan", "typo-key"),
        diff=DiskDiff((), (), ()),
        temp_files_created=(),
        temp_files_left=(),
        db_calls=(),
        trips=0,
        single_pass_trips=0,
        scanned_roots=(tmp_path,),
    )
    with pytest.raises(AssertionError, match="空转"):
        assert_zero_residue(vacuous)


# ═══════════════════════════════════════════════════════════════════════════
# ⑤ 断言面③：「DB 无半条记录」的诚实形态（详见模块 docstring）
# ═══════════════════════════════════════════════════════════════════════════


def _every_imported_module(path: Path) -> set[str]:
    """一个源文件里**全部** import 的模块名（含函数体内的延迟 import）。

    本仓库大量使用函数体内 import（循环依赖与冷启动开销），只扫模块头的判据会漏掉它们 ——
    而「谁偷偷在写盘路径里 import 了 session」恰恰最可能写成函数体内 import。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def test_the_write_path_imports_no_database_module() -> None:
    """**Validates: Requirements 1.3**（断言面③ 的静态一半）

    写盘路径的四个模块，**每一条** import 都不得是 DB 模块。这条比「本次跑下来库里没多出行」
    强得多：它对**所有**输入成立，而数行数只对这一次成立。

    ⚠️ 诚实边界：这是**直接** import 面的完整扫描，不是传递闭包 —— `workpaper_sync` 包里
    确有 `repository.py` 与 ORM 模型模块，同包其它模块（coordinator / content_mutation）当然
    要用它们。本条主张的是「写盘这四个模块自己不碰库」，配合下一条运行时判据一起，才构成
    「materialize 全程没碰库」。
    """
    backend = Path(__file__).resolve().parents[2]
    offenders: list[str] = []
    for relative in _WRITE_PATH_MODULES:
        source = backend / relative
        assert source.is_file(), f"写盘路径模块不在了：{source}（本判据的分母没了）"
        for module in sorted(_every_imported_module(source)):
            if any(marker in module for marker in _DB_IMPORT_MARKERS):
                offenders.append(f"{relative} → {module}")
    assert offenders == [], (
        "写盘路径 import 了数据库模块 ⇒ materialize 不再是纯文件操作，"
        f"需求 1.3 的「DB 无半条记录」必须改由事务判据承担：{offenders}"
    )


def test_no_database_access_during_a_failed_materialize(
    world: D4World, binding_keys: tuple[str, ...], tmp_path: Path
) -> None:
    """**Validates: Requirements 1.3**（断言面③ 的运行时一半）

    一次注入失败的 materialize 全程，SQLAlchemy 侧连接/执行调用数为 **0**。

    这就是「DB 无半条记录」在本层的**诚实**形态：不是「查库发现 0 行」（那条断言在任何实现下
    都绿，因为连库都没连过 —— 假绿），而是「这一层拿不到也没用过 session」。DB 侧真正的原子性
    在 `ContentMutationService.commit`（见下一条与模块 docstring）。
    """
    obs = run_failing_materialize(
        world=world,
        tmp_root=tmp_path,
        inject=lambda: fail_at_plan(binding_keys[BASELINE_BINDINGS // 2]),
        label="db-witness-middle-single",
    )
    assert obs.injection.fired, "注入没打中 ⇒ 本条是空转"
    assert obs.db_calls == (), f"失败的 materialize 碰了数据库：{obs.db_calls}"


def test_the_database_witness_is_not_a_no_op() -> None:
    """**Validates: Requirements 1.3**

    观察者自身的反证：真去连一次库（内存 sqlite，不需要任何外部服务），它必须记到。
    少了这条，「零 DB 调用」可能只是探针压根没装上。
    """
    import sqlalchemy

    with db_access_witness() as calls:
        engine = sqlalchemy.create_engine("sqlite://")
        with engine.connect() as connection:
            connection.execute(sqlalchemy.text("select 1"))
        engine.dispose()
    assert "Engine.connect" in calls, f"观察者没记到连接：{calls}"


def test_db_atomicity_lives_in_content_mutation_commit() -> None:
    """**Validates: Requirements 1.3**

    既然 materialize 不碰库，「DB 无半条记录」这条承诺必须在别处有落点 —— 本条把那个落点钉住：
    `ContentMutationService.commit()` 里 `_stage_and_verify(...)`（内含 materialize）**先于**
    `_commit_once(...)`（持有唯一那次 `session.commit()`），且在 `_stage_and_verify` 之前
    `commit()` 一次都没碰过 `self._session`。

    ⇒ binding 写入失败发生在 DB 事务**开始之前**：不是「写了半条再回滚」，而是一行都还没写。

    ⚠️ 这是一条**源码结构**判据（AST，仓库既有形态：`test_task26_oo_to_html.py` /
    `test_projection_structure_hash_semantics.py` 也这么钉顺序），比运行时判据弱一档。真正的
    运行时证据（`_stage_and_verify` 抛错 ⇒ 事务零写入）需要 PG，归 coordinator 层既有的事务
    见证机制（`_TransactionWitness` / `_CommitLatch`，见 `test_task15_content_mutation*.py`）
    —— 本任务不越界去那层重造一套。
    """
    from app.services.workpaper_sync import content_mutation as CM

    body = ast.parse(
        inspect.cleandoc(inspect.getsource(CM.ContentMutationService.commit))
    ).body[0]
    assert isinstance(body, (ast.AsyncFunctionDef, ast.FunctionDef))
    order: list[tuple[int, str]] = []
    for index, statement in enumerate(body.body):
        rendered = ast.unparse(statement)
        for marker in ("_stage_and_verify(", "_commit_once(", "self._session"):
            if marker in rendered:
                order.append((index, marker))
    seen = [marker for _, marker in order]
    assert "_stage_and_verify(" in seen and "_commit_once(" in seen, (
        f"`commit()` 的结构变了，本判据的分母没了：{seen}"
    )
    stage_at = min(index for index, marker in order if marker == "_stage_and_verify(")
    commit_at = min(index for index, marker in order if marker == "_commit_once(")
    assert stage_at < commit_at, (
        "`_commit_once`（唯一那次 session.commit 所在）跑在 materialize 之前了 ⇒ "
        "binding 写入失败将发生在 DB 事务**之内**，需求 1.3 的第三面必须重新设计判据"
    )
    session_before = [
        index for index, marker in order if marker == "self._session" and index < stage_at
    ]
    assert session_before == [], (
        f"`commit()` 在 materialize 之前就动了 session（语句下标 {session_before}）⇒ "
        "「失败时一行都还没写」不再成立"
    )


# ═══════════════════════════════════════════════════════════════════════════
# ⑥ 本任务实测发现：原子改名**之后**还有写入 —— 残留边界必须钉死
# ═══════════════════════════════════════════════════════════════════════════


@contextlib.contextmanager
def fail_in_transposed_post_pass() -> Iterator[Injection]:
    """让原子改名**之后**那段转置 sheet 写入抛错（不是 binding 写入，是它后面那一段）。"""
    from app.services.workpaper_sync import phase5_transposed_sheet as TS

    record = Injection("transposed", "<post-pass>")
    original = TS.materialize_file

    def poisoned(*args: Any, **kwargs: Any) -> Any:
        record.fired.append("transposed")
        raise InjectedBindingFailure("注入：转置 sheet 写入失败（改名之后）")

    TS.materialize_file = poisoned  # type: ignore[assignment]
    try:
        yield record
    finally:
        TS.materialize_file = original  # type: ignore[assignment]


def test_writes_continue_after_the_atomic_rename_and_the_residue_is_bounded(
    world: D4World, tmp_path: Path
) -> None:
    """**Validates: Requirements 1.3**

    🔴 **本任务的实测发现，登记在案。** 需求 1.3 的「无 staged artifact」在 `os.replace` 处
    **并没有**讲完整个故事：改名之后 `adapter.materialize` 还要把转置 sheet 就地写进
    `output`（`_transposed_materialize_file(output, ...)`，D4 实测两张，`Workbook.save` 那 2
    次就是它；产物 246110 字节 − 改名那刻的 237925 字节 = 这一段补的 8185 字节）。
    `ContentMutationService._stage_and_verify` 的注释也明写「此时 adapter.materialize 已完成
    全部写入（**含转置 sheet 覆盖**）」⇒ 这是**有意的**结构，不是疏漏。

    后果：这一段抛错时 `output` 上留着一份**只完成 zip 改写、缺转置列**的文件。本条如实断言
    这个事实，并把它的**边界**钉死 —— 这才是这里真正该保证的东西：

    * 残留**恰好**只有 `output` 一个条目（不是加上临时文件、中间产物、别处的副产品）；
    * `*.materializing` 半成品仍被删净（那一段的 `finally` 照旧生效）；
    * materialize 仍然整趟失败（异常照旧传播），DB 仍然零调用。

    为什么这不是需求 1.3 说的「把半成品当 staged artifact 发布」，也因此**不在本任务修**：
    `output` 的路径由 `ContentMutationService._stage_and_verify` 用 `uuid4()` 的
    `stage_id` 现开一个 staging 工作目录算出来（`work_dir / f"materialized.{document_type}"`）
    ⇒ 每次尝试各自一个目录，**永远不会**覆盖上一次的产物，也不会被下一次读到；发布是后面
    独立的 `stage_stream` + `publish_representation`（内容寻址），materialize 抛错时它压根
    不会执行。落在 per-attempt staging 目录里的不完整文件正是该协议定义的 **orphan**
    （content_mutation 模块 docstring：「commit 失败它就是 orphan，由 Task 11 的
    reconciliation 收」）。

    ⇒ 结论：这是「孤儿 scratch 文件」而不是「半成品被发布」，也不会破坏任何已有产物。真要
    把它一起收干净，正解是把转置 sheet 写到 `tmp` 上、改名放最后一步（那样 `output` 只会以
    完整形态出现），但那是对 `materialize` 三条分支（单 binding / 单趟 / 链式）与
    `artifact_sha256` 口径的改造，属独立改动 —— 本任务只负责把事实与边界钉住并上报。
    """
    label = "transposed-post-pass"
    output = staged_output(world, label)
    output.unlink(missing_ok=True)
    obs = run_failing_materialize(
        world=world,
        tmp_root=tmp_path,
        inject=fail_in_transposed_post_pass,
        label=label,
    )
    assert obs.injection.fired, "注入没打中 ⇒ 本条是空转（D4 可能已经没有转置 sheet 了）"

    # ① 残留边界：恰好只有 `output`，一个条目都不许多。
    assert obs.diff.added == (str(output),), (
        f"改名后失败的残留不止 `output` 一个：{obs.diff.added} —— 边界变了，"
        "本条的结论（孤儿 scratch 文件，影响面仅此一个 per-attempt 文件）必须重新裁定"
    )
    assert obs.diff.removed == () and obs.diff.changed == (), (
        f"失败路径误伤了既有条目：removed={obs.diff.removed} changed={obs.diff.changed}"
    )
    # ② 那份残留确实是「缺转置列」的不完整产物，而不是空文件或半个 zip。
    assert output.is_file() and output.read_bytes()[:2] == b"PK", "残留甚至不是个 zip"
    # ③ `*.materializing` 与中间临时文件仍被删净（改名前那两段的清理照旧生效）。
    assert obs.temp_files_left == (), f"临时文件残留：{obs.temp_files_left}"
    assert not output.with_name(output.name + _MATERIALIZING_SUFFIX).exists(), (
        "`*.materializing` 半成品残留 —— 改名前那段的 finally 失效了"
    )
    # ④ 整趟失败 + DB 零调用（这两条与 binding 写入失败时同口径）。
    assert isinstance(obs.raised, InjectedBindingFailure)
    assert obs.db_calls == (), f"碰了数据库：{obs.db_calls}"
