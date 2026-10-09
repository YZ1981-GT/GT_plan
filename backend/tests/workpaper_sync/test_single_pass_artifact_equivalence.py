# -*- coding: utf-8 -*-
"""链式 vs 单趟：**产物等值**判据（spec oo-single-pass-materialize-and-room-leave）。

Requirements: 1.2　　Property: **P2**

═══ 为什么另起一个文件，不并进 `test_single_pass_materialize.py` ═══

那个文件的标题命题是**趟数**（P1 / 需求 1.1 / 1.5）：提速有没有发生。本文件的标题命题是
**产物**（P2 / 需求 1.2）：提速有没有以「少写了某些 binding」为代价。两问分开，失败时
「没提速」与「写少了」在文件名上就分得开；合进去会得到一个 headline 是两件事的文件。

world 仍由 `d4_materialize_harness.build_world` 铺 —— 它才是「同一个 39」的单一来源
（`_frozen_d4()` 带 `lru_cache` ⇒ 同一次 pytest 进程里真模板只 instrument 一次，多一个
测试模块只多付一次 `build_world`）。

═══ 「旧链式」从哪来：不必 git 检出历史实现 ═══

任务文本允许「git 检出的历史实现**或等价模拟**」。这里用的是比两者都强的第三种：链式路径
**仍是活代码** —— 它是单趟 decline 三条（插行 / openpyxl 全量重写 / 同格 payload 冲突）的
正式回落路径（design 附录 A.7）。`force_chained_path()` 只把单趟入口摘掉，`adapter.materialize`
就走它。于是本判据比的不是「今天的实现 vs 一份考古复刻」，而是**两条今天都会被走到的真实
路径**；复刻件与真实实现漂移这一类风险从判据里消失了。

═══ 为什么不比 sha256、也不比裸字节 ═══

任务 1 实测（证据 `docs/operations/evidence/oo-single-pass-materialize/README.md` 末节）：
同一 projection 连续两次物化，`sha256` 就**本来**不同 —— 142 个 zip entry 的字节全同，差异
只在 zip 条目时间戳。拿 sha256 或裸字节比新旧，会红在一个与单趟化无关的原因上。

需求 1.2 指名的判据是**反读等值**：两份产物各 `extract` 一遍，projection 逐字段比。本文件
另加一条更强的：逐 zip entry 比字节、**显式忽略** `date_time`。

🔴 **那条「更强的」不是装饰，它补住了反读判据的一个真实窟窿**（本文件实测）：把
`d4_10_rows` 的 49 处写入整个漏掉，`extract` 出来的 218 个字段**逐字段全等** —— projection
取自 substrate 自身，漏写等于「保留原值」，反读自然读回同样的值；而 `sheet15.xml` 实际少了
95 字节。谁把字节判据当冗余删掉，这一类漏写就再没有判据看得见。

═══ 2026-09-22 真库实测（本文件的三条判据各自的量） ═══

| 量 | 链式（`force_chained_path()`） | 单趟（默认路径） |
|---|---|---|
| 写入趟数 / 其中单趟 | 39 / 0 | 1 / 1 |
| substrate 解析 | 78 | 2 |
| `extract` 字段数 | 218 | 218（0 缺 / 0 多 / 0 改） |
| zip entry | 142 | 142（内容全同；142/142 `date_time` 不同 ⇒ sha256 不同） |

| 变异（只注入单趟侧） | 反读判据 | 字节判据 |
|---|---|---|
| 漏写 `d4_32_groups`（34 处 `inline_text`） | **红**：24 个字段 `'1'` → `1` | 红：`sheet41.xml` |
| 漏写 `d4_10_rows`（49 处写入） | **绿（窟窿）** | **红**：`sheet15.xml` −95 字节 |
"""
from __future__ import annotations

import contextlib
import dataclasses
import zipfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

import pytest

from app.services.workpaper_sync.adapters.base import FieldValue, Projection
from app.services.workpaper_sync.contracts import FieldMode, ValueType
from app.services.workpaper_sync.excel_extract import verify_roundtrip_equivalence
from app.services.workpaper_sync.projection_digest_value import (
    canonical_value_for_digest,
)
from tests.workpaper_sync.d4_materialize_harness import (
    D4World,
    MaterializeCallCounter,
    build_world,
    force_chained_path,
)

# 趟数基线从**趟数判据那个文件**引进来，不在这里再抄一份：抄一份的话「回落路径的趟数变了」
# 会在两个文件里各自成立，而它们本该是同一个事实。
from tests.workpaper_sync.test_single_pass_materialize import (
    BASELINE_BINDINGS,
    BASELINE_SUBSTRATE_LOADS,
    SINGLE_PASS_SUBSTRATE_LOADS,
)

#: 两条路径 `extract` 出来的受管字段数（真库实测）。钉住它是**非空转**判据：两边都变成
#: 空 projection 时「逐字段相等」也成立，那种绿是假的。契约受管表集合变了要同步刷新。
EXTRACTED_FIELD_COUNT = 218
#: 产物 zip 的 entry 数（真库实测）。同上，防「两边都只剩几个 entry 也算相等」。
ARTIFACT_ZIP_ENTRIES = 142

#: 变异反证的两个受害 binding。刻意挑**两类**：
#: * `d4_32_groups`：34 处全是 `inline_text`，且模板里那些格存的是**数字** ⇒ 漏写之后反读
#:   回 int 而不是 str ⇒ 反读判据直接红（这是 design P2 写的那条反证）；
#: * `d4_10_rows`：49 处写入（28 `inline_text` + 21 `number_literal`），漏写之后反读**全等**
#:   ⇒ 只有字节判据看得见。它是本文件坚持保留字节判据的理由。
TEXT_VICTIM = "d4_32_groups"
TEXT_VICTIM_PART = "xl/worksheets/sheet41.xml"
#: 漏写 `d4_32_groups` 的 34 处写入后，反读出来发生变化的字段数（真库实测）。
TEXT_VICTIM_CHANGED_FIELDS = 24
SILENT_VICTIM = "d4_10_rows"
SILENT_VICTIM_PART = "xl/worksheets/sheet15.xml"

# ═══════════════════════════════════════════════════════════════════════════
# 比较面：`Projection` / `FieldValue` 的**每个** dataclass 字段
# ═══════════════════════════════════════════════════════════════════════════

#: 判据覆盖的 `Projection` 字段。`test_comparison_surface_covers_every_dataclass_field`
#: 拿它与真实 dataclass 比 —— 将来给 Projection 加字段而忘了进判据面，那条会红。
_PROJECTION_FIELDS = frozenset(
    {"contract_id", "semantic_version", "document_type", "values", "row_keys"}
)
_FIELD_VALUE_FIELDS = frozenset(
    {"stable_key", "value", "value_type", "mode", "row_key"}
)


def _field_signature(field: FieldValue) -> tuple[str, str, str, str, str]:
    """一个 projection 字段在本判据下的比较面（与 `_FIELD_VALUE_FIELDS` 一一对应）。

    🔴 `value` 取 `repr` 而不是值本身。`0` / `0.0` / `Decimal('0')` / `False` 在 `==` 下
    **两两相等**，落盘字节却不同 —— 用 `==` 比，「单趟把 int 0 写成了 float 0.0」这类改变
    会静默通过，P2 就退化成一句空话。口径与生产的
    `excel_materialize._write_payload` / `analyze_d4_binding_dependencies._write_signature`
    **同一套**（那两处也是为了同一个理由取 `repr`）。

    ═══ 为什么不复用既有的两个「等值」helper ═══

    仓库里确实已有两套 projection 比较口径，但**两套都刻意比本判据松**，复用等于把 P2 写松：

    * `projection_digest_value.canonical_value_for_digest()` —— 它存在的**目的**就是让
      `0` 与 `0.0` 算出同一个 digest（否则业务身份复用恒不命中，见该模块 docstring）。拿它
      当等值判据，等于主动放弃本判据最该抓的那一类差异。
      判据见 `test_a_loose_comparison_would_make_this_judgement_vacuous`。
    * `excel_extract.verify_roundtrip_equivalence()` —— 生产的反读发布门，比较范围刻意
      **只含 `mode=editable`**（公式 / auto_source 的值由服务端写、不以逐字节相等为正确性
      判据）。本判据要抓的是「漏写了某个 binding」，而 binding 可以整个落在受保护字段上
      （D4 的 `revenue_detail_rows` 那 12 处全是 `cached_value_only`）⇒ 用它会漏。
      判据见 `test_the_production_verify_gate_is_strictly_weaker_than_this_judgement`。

    所以这里自建一套 **更严**的比较面，并用上面两条判据把「更严」钉成可执行事实，而不是
    写在注释里的自我声明。
    """
    return (
        str(field.stable_key),
        field.value_type.value,
        field.mode.value,
        repr(field.value),
        "" if field.row_key is None else str(field.row_key),
    )


def _header(projection: Projection) -> tuple[str, str, str]:
    return (
        str(projection.contract_id),
        str(projection.semantic_version),
        str(projection.document_type),
    )


def _row_keys(projection: Projection) -> dict[str, tuple[str, ...]]:
    return {str(k): tuple(str(v) for v in values) for k, values in projection.row_keys.items()}


def projection_differences(
    left: Projection,
    right: Projection,
    *,
    left_label: str = "chained",
    right_label: str = "single_pass",
) -> tuple[str, ...]:
    """两份 projection 的**完整**差异清单（排序确定，空元组 = 逐字段等值）。

    「完整 + 确定」与 decline 原因同一条纪律（design 附录 A.6 第 2 条）：只报第一处差异，
    就没法回答「到底漏了几个字段、漏在哪张表」。三类差异各自成行：缺字段 / 多字段 / 值变。
    """
    diffs: list[str] = []

    left_header, right_header = _header(left), _header(right)
    if left_header != right_header:
        diffs.append(
            f"projection header 不同：{left_label}={left_header} / "
            f"{right_label}={right_header}"
        )

    left_rows, right_rows = _row_keys(left), _row_keys(right)
    for table in sorted(set(left_rows) | set(right_rows)):
        if left_rows.get(table) != right_rows.get(table):
            diffs.append(
                f"row_keys[{table}] 不同：{left_label}={left_rows.get(table)} / "
                f"{right_label}={right_rows.get(table)}"
            )

    left_values = {key: _field_signature(value) for key, value in left.values.items()}
    right_values = {key: _field_signature(value) for key, value in right.values.items()}
    for key in sorted(set(left_values) - set(right_values)):
        diffs.append(f"{key}: {right_label} 缺该字段（{left_label}={left_values[key]}）")
    for key in sorted(set(right_values) - set(left_values)):
        diffs.append(f"{key}: {right_label} 多出该字段（{right_values[key]}）")
    for key in sorted(set(left_values) & set(right_values)):
        if left_values[key] != right_values[key]:
            diffs.append(
                f"{key}: {left_label}={left_values[key]} != "
                f"{right_label}={right_values[key]}"
            )
    return tuple(diffs)


@dataclass(frozen=True)
class ZipComparison:
    """逐 entry 的字节比对结果（`date_time` 单独列，不混进 `content_differences`）。"""

    entry_count: int
    namelist_equal: bool
    name_differences: tuple[str, ...]
    content_differences: tuple[str, ...]
    timestamp_differences: tuple[str, ...]
    sha256_equal: bool
    byte_sizes: tuple[int, int]


def compare_zip_entries(left: Path, right: Path) -> ZipComparison:
    """两份 xlsx 逐 zip entry 比字节，**显式**把 `date_time` 分流出去。

    忽略 `date_time` 不是「放宽判据」而是把一个已知的、与本 spec 无关的噪声源摘掉：任务 1
    实测同一 projection 连续两次物化的 142 个 entry 字节全同、142 个时间戳全不同。不摘掉它，
    这条判据永远红；摘掉之后剩下的每一个字节差异都是真差异。
    """
    import hashlib

    with zipfile.ZipFile(left) as zip_left, zipfile.ZipFile(right) as zip_right:
        left_names, right_names = zip_left.namelist(), zip_right.namelist()
        shared = [name for name in left_names if name in set(right_names)]
        content = tuple(
            name for name in shared if zip_left.read(name) != zip_right.read(name)
        )
        left_stamps = {item.filename: item.date_time for item in zip_left.infolist()}
        right_stamps = {item.filename: item.date_time for item in zip_right.infolist()}
        stamps = tuple(
            name for name in shared if left_stamps.get(name) != right_stamps.get(name)
        )
    return ZipComparison(
        entry_count=len(left_names),
        # 顺序也比：entry 顺序变了说明打包方式变了，那是产物层面的真差异。
        namelist_equal=left_names == right_names,
        name_differences=tuple(sorted(set(left_names) ^ set(right_names))),
        content_differences=tuple(sorted(content)),
        timestamp_differences=tuple(sorted(stamps)),
        sha256_equal=hashlib.sha256(left.read_bytes()).hexdigest()
        == hashlib.sha256(right.read_bytes()).hexdigest(),
        byte_sizes=(left.stat().st_size, right.stat().st_size),
    )


# ═══════════════════════════════════════════════════════════════════════════
# world / 两条路径各跑一次（module 作用域：铺 world + 两趟物化 + 两次反读 ≈ 40s）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class BothPaths:
    """同一份 projection 分别走链式与单趟的全部产物与观测。"""

    world: D4World
    chained_artifact: Path
    single_artifact: Path
    chained_extract: Projection
    single_extract: Projection
    chained_counter: MaterializeCallCounter
    single_counter: MaterializeCallCounter


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> D4World:
    """真 D4 模板 + 真契约 + 真 39 binding，projection 取自 substrate 自身的反读结果。

    自反读的 projection 是「全部 binding 都被写一遍」的最诚实输入：合成 projection 只会
    命中其中几张表，那样「漏写某个 binding」就可能落在判据覆盖不到的地方。
    """
    return build_world(tmp_path_factory.mktemp("d4-equivalence"))


@pytest.fixture(scope="module")
def both_paths(world: D4World) -> BothPaths:
    """先链式、后单趟各物化一次**同一份** projection，再各反读一次。

    两次物化用同一个 `world`（同一份 substrate 字节、同一份 projection、同一个 adapter
    实例）—— 需求 1.2 的「同一份 projection 走新旧两条路径」就是这个意思。
    """
    chained_counter = MaterializeCallCounter()
    with force_chained_path(), chained_counter.installed():
        chained_artifact = world.materialize("equivalence-chained.xlsx")

    single_counter = MaterializeCallCounter()
    with single_counter.installed():
        single_artifact = world.materialize("equivalence-single-pass.xlsx")

    return BothPaths(
        world=world,
        chained_artifact=chained_artifact,
        single_artifact=single_artifact,
        chained_extract=world.adapter.extract(
            artifact=chained_artifact, contract=world.contract
        ),
        single_extract=world.adapter.extract(
            artifact=single_artifact, contract=world.contract
        ),
        chained_counter=chained_counter,
        single_counter=single_counter,
    )


@contextlib.contextmanager
def drop_binding_writes(victim: str) -> Iterator[None]:
    """变异注入：让某个 binding 的写入清单变成空（= 单趟「漏写了这个 binding」）。

    拦的是**生产内核** `_plan_materialize_step` 的返回，不改判据、不改 adapter、不改契约 ——
    只改输入。与 `test_payload_conflict_really_falls_back_to_the_chained_path` 同一种注入法。

    注入前断言受害 binding **本来有写入**：没有的话变异什么也没干，反证就变成空转。
    """
    from app.services.workpaper_sync import excel_materialize as EM

    original = EM._plan_materialize_step
    seen: list[int] = []

    def poisoned(**kwargs: Any) -> Any:
        step = original(**kwargs)
        if str(step.binding.table_key) != victim:
            return step
        assert step.plan.writes, (
            f"受害 binding {victim} 本来就没有任何写入 ⇒ 变异是空转，反证不成立"
        )
        seen.append(len(step.plan.writes))
        return dataclasses.replace(
            step, plan=dataclasses.replace(step.plan, writes=())
        )

    EM._plan_materialize_step = poisoned  # type: ignore[assignment]
    try:
        yield
    finally:
        EM._plan_materialize_step = original  # type: ignore[assignment]
    assert seen, f"受害 binding {victim} 一次都没被计划到 ⇒ table_key 写错了，反证是空转"


def materialize_with_dropped_binding(
    world: D4World, victim: str
) -> tuple[Path, Projection, MaterializeCallCounter]:
    """单趟路径 + 漏写 `victim` ⇒ 产物 / 反读结果 / 调用计数。"""
    counter = MaterializeCallCounter()
    with drop_binding_writes(victim), counter.installed():
        artifact = world.materialize(f"equivalence-dropped-{victim}.xlsx")
    return (
        artifact,
        world.adapter.extract(artifact=artifact, contract=world.contract),
        counter,
    )


# ═══════════════════════════════════════════════════════════════════════════
# ① 反空转前提：两份产物真的来自**两条不同的代码路径**
# ═══════════════════════════════════════════════════════════════════════════


def test_both_artifacts_really_came_from_different_code_paths(
    both_paths: BothPaths,
) -> None:
    """**Validates: Requirements 1.2**

    🔴 这条是整个 P2 的**前提**，不是锦上添花：谁把 `force_chained_path()` 弄失效（或哪天
    单趟入口的名字改了、helper 静默变成 no-op），两侧就会跑同一条路径，「逐字段相等」当然
    成立 —— 一条永远绿的判据比没有判据更糟。

    用趟数与 substrate 解析次数**两个独立信号**交叉确认：趟数证明「写入 pass 的条数」不同，
    解析次数证明「解析的次数」不同。只看趟数的话，一个只改了计数口径的改动就能骗过它。
    """
    chained, single = both_paths.chained_counter, both_paths.single_counter

    assert chained.trip_count == BASELINE_BINDINGS, (
        f"链式侧趟数 {chained.trip_count} ≠ {BASELINE_BINDINGS} ⇒ 它没走逐 binding 链式；"
        f"趟次：{chained.trips[:5]}…"
    )
    assert chained.single_pass_trip_count == 0, (
        f"链式侧记到了单趟趟次 {chained.single_pass_trips} ⇒ "
        "`force_chained_path()` 没把单趟入口摘掉，两侧其实是同一条路径"
    )
    assert single.trip_count == 1 and single.single_pass_trip_count == 1, (
        f"单趟侧趟数 {single.trip_count}（其中单趟 {single.single_pass_trip_count}）"
        f" ≠ 恰 1 ⇒ 它回落了或根本没走单趟；趟次：{single.trips}"
    )
    assert chained.substrate_load_count == BASELINE_SUBSTRATE_LOADS, (
        f"链式侧 substrate 解析 {chained.substrate_load_count} ≠ {BASELINE_SUBSTRATE_LOADS}"
    )
    assert single.substrate_load_count == SINGLE_PASS_SUBSTRATE_LOADS, (
        f"单趟侧 substrate 解析 {single.substrate_load_count} ≠ "
        f"{SINGLE_PASS_SUBSTRATE_LOADS}"
    )
    assert both_paths.chained_artifact != both_paths.single_artifact, "两侧写到了同一个文件"
    for artifact in (both_paths.chained_artifact, both_paths.single_artifact):
        assert artifact.is_file() and artifact.read_bytes()[:2] == b"PK", (
            f"{artifact.name} 不是 xlsx"
        )


# ═══════════════════════════════════════════════════════════════════════════
# ② P2 正文：反读逐字段等值（需求 1.2 指名的那条）
# ═══════════════════════════════════════════════════════════════════════════


def test_extract_of_both_paths_is_equal_field_by_field(both_paths: BothPaths) -> None:
    """**Validates: Requirements 1.2**　**Property: P2**

    同一份 projection 走链式与单趟，两份产物各 `extract` 一遍，projection **逐字段**相等：
    key 集合、值（`repr` 口径）、`value_type`、`mode`、`row_key`、`row_keys` 行身份、header
    三项，一项都不许差。

    先钉非空转（字段数 == 实测 218）再钉相等：两边都退化成空 projection 时「相等」也成立。
    """
    chained, single = both_paths.chained_extract, both_paths.single_extract
    assert len(chained.values) == len(single.values) == EXTRACTED_FIELD_COUNT, (
        f"反读字段数 链式 {len(chained.values)} / 单趟 {len(single.values)} ≠ 实测 "
        f"{EXTRACTED_FIELD_COUNT} —— 契约受管表集合变了是正当变化，但必须同步刷新本常数；"
        "字段数掉到 0 附近则是 extract 本身出了问题，此时「相等」是假绿"
    )
    differences = projection_differences(chained, single)
    assert differences == (), (
        f"单趟产物与链式产物反读不等值，共 {len(differences)} 处（完整清单）：\n"
        + "\n".join(differences[:40])
    )


def test_artifact_zip_entries_are_byte_identical_ignoring_timestamps(
    both_paths: BothPaths,
) -> None:
    """**Validates: Requirements 1.2**

    比反读更强的一条：逐 zip entry 比字节，只把 `date_time` 摘出去。

    🔴 它**不是**反读判据的冗余备份 —— 见
    `test_dropping_a_silent_bindings_writes_is_caught_only_by_the_byte_judgement`：
    有一整类「漏写」在反读侧完全看不出来，只有它能抓。

    同时把「为什么不比 sha256」钉成可执行事实：允许 sha256 不等，但**必须**能由时间戳解释
    （sha256 不等而时间戳全同 ⇒ 差异来自真字节 ⇒ 上面那条 content 判据会红）。
    """
    comparison = compare_zip_entries(
        both_paths.chained_artifact, both_paths.single_artifact
    )
    assert comparison.entry_count == ARTIFACT_ZIP_ENTRIES, (
        f"zip entry 数 {comparison.entry_count} ≠ 实测 {ARTIFACT_ZIP_ENTRIES} —— "
        "模板变了要刷新本常数；掉到个位数则是产物本身坏了，此时「逐 entry 相等」是假绿"
    )
    assert comparison.name_differences == (), (
        f"两侧 entry 清单不同（只在一侧出现）：{comparison.name_differences}"
    )
    assert comparison.namelist_equal, "entry **顺序**不同 ⇒ 打包方式变了，那是真差异"
    assert comparison.content_differences == (), (
        f"逐 entry 字节不同（已排除时间戳）：{comparison.content_differences}；"
        f"字节数 {comparison.byte_sizes}"
    )
    assert comparison.sha256_equal or comparison.timestamp_differences, (
        "sha256 不等，却没有任何 entry 的时间戳不同 ⇒ 差异不是时间戳造成的，"
        "但逐 entry 内容又全同 —— 这两件事不能同时成立，比对实现自己出了问题"
    )


# ═══════════════════════════════════════════════════════════════════════════
# ③ 变异反证：漏写一个 binding ⇒ 必须红（design 五 P2 的反证方式）
# ═══════════════════════════════════════════════════════════════════════════


def test_dropping_a_text_bindings_writes_turns_the_extract_judgement_red(
    both_paths: BothPaths,
) -> None:
    """**Validates: Requirements 1.2**　design 五 P2 的反证：「故意漏写一个 binding ⇒ 红」。

    受害者 `d4_32_groups`（34 处 `inline_text`）：模板里那些格存的是**数字**，materialize 的
    `text` 归一会把它们写成字符串。漏写之后反读回 int ⇒ 24 个字段的 `repr` 从 `'1'` 变成 `1`
    ⇒ 反读判据红。

    🔴 实测更正了 design P2 反证措辞里的一个细节：漏写一个 binding 在这里表现为
    「**字段值/类型变了**」而不是「字段缺失」。原因是 projection 取自 substrate 自身 ——
    漏写等于保留原值，key 集合不会少一个（218 → 218，0 缺 0 多）。要求 1.2 的判据面因此必须
    同时覆盖「缺字段 / 多字段 / 值变」三类，只查 key 集合的判据在这条反证下是绿的。
    """
    artifact, extracted, counter = materialize_with_dropped_binding(
        both_paths.world, TEXT_VICTIM
    )
    assert counter.single_pass_trip_count == 1 and counter.trip_count == 1, (
        f"变异侧没走单趟（趟数 {counter.trip_count} / 单趟 {counter.single_pass_trip_count}）"
        " ⇒ 抓到的红可能来自回落而不是漏写"
    )

    differences = projection_differences(
        both_paths.chained_extract, extracted, right_label="single_pass_missing_binding"
    )
    assert len(differences) == TEXT_VICTIM_CHANGED_FIELDS, (
        f"漏写 {TEXT_VICTIM} 后反读差异 {len(differences)} 处 ≠ 实测 "
        f"{TEXT_VICTIM_CHANGED_FIELDS} 处；清单：\n" + "\n".join(differences[:10])
    )
    assert all(item.startswith(f"{TEXT_VICTIM}/") for item in differences), (
        f"差异跑到了受害 binding 之外 ⇒ 变异注入不干净：\n" + "\n".join(differences[:10])
    )
    # key 集合没少一个 —— 这正是上面 docstring 说的那条更正，钉住它免得下游又去只查 key。
    assert len(extracted.values) == EXTRACTED_FIELD_COUNT, (
        f"漏写后字段数 {len(extracted.values)} ≠ {EXTRACTED_FIELD_COUNT}：本反证的价值就在于"
        "「漏写不会让 key 少」，它变了说明前提变了，反证措辞要同步更新"
    )
    # 字节侧同样红，且**只**红在受害 binding 那张 sheet 上。
    byte_diff = compare_zip_entries(both_paths.chained_artifact, artifact)
    assert byte_diff.content_differences == (TEXT_VICTIM_PART,), (
        f"字节差异不是恰好落在 {TEXT_VICTIM_PART}：{byte_diff.content_differences}"
    )


def test_dropping_a_silent_bindings_writes_is_caught_only_by_the_byte_judgement(
    both_paths: BothPaths,
) -> None:
    """**Validates: Requirements 1.2**

    🔴 本文件最重要的一条实测，它说明**需求 1.2 指名的反读判据单独不够用**：

    受害者 `d4_10_rows`（49 处写入 = 28 `inline_text` + 21 `number_literal`）整个漏写之后，
    `extract` 出来的 218 个字段**逐字段全等**（0 缺 / 0 多 / 0 改）—— 因为 projection 取自
    substrate 自身，漏写 = 保留原值，而那些格的原值反读回来与 projection 声明的一致。
    与此同时 `xl/worksheets/sheet15.xml` 实际少了 95 字节：产物**真的**不同。

    结论（登记在案，供需求 1.2 后续措辞与任务 9 的 verify 判据参考）：
    「反读等值」这一族判据对「写入只改变了单元格的**表示形态**而不改变反读值」这一类漏写
    天生是盲的。因此本文件的字节判据是**必需项**而不是加强项；删掉它，这一整类漏写在 CI 上
    没有任何判据看得见。

    本条同时给字节判据做了非空转证明：它确实抓到了反读判据抓不到的东西。
    """
    artifact, extracted, counter = materialize_with_dropped_binding(
        both_paths.world, SILENT_VICTIM
    )
    assert counter.single_pass_trip_count == 1 and counter.trip_count == 1, (
        f"变异侧没走单趟（趟数 {counter.trip_count}）⇒ 观察到的现象不可归因于漏写"
    )

    # ① 反读侧：全等（这是窟窿本身，不是「判据坏了」）。
    reread = projection_differences(
        both_paths.chained_extract, extracted, right_label="single_pass_missing_binding"
    )
    assert reread == (), (
        f"漏写 {SILENT_VICTIM} 居然被反读判据抓到了 {len(reread)} 处差异 —— 这是**好事**，"
        "但说明前提变了（写入形态或 extract 口径改了）：请把本条的叙述与 design 附录同步"
        "更新，别让「反读判据有窟窿」这个结论继续挂在一个已经不成立的实测上。\n"
        + "\n".join(reread[:10])
    )
    # ② 字节侧：红，且恰好红在受害 binding 那张 sheet 上。
    byte_diff = compare_zip_entries(both_paths.chained_artifact, artifact)
    assert byte_diff.content_differences == (SILENT_VICTIM_PART,), (
        f"字节差异不是恰好落在 {SILENT_VICTIM_PART}：{byte_diff.content_differences}；"
        f"字节数 {byte_diff.byte_sizes}"
    )
    assert byte_diff.byte_sizes[1] < byte_diff.byte_sizes[0], (
        f"漏写了 49 处却没让产物变小：{byte_diff.byte_sizes}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# ④ 比较面本身可反证（不需要真库，毫秒级）
# ═══════════════════════════════════════════════════════════════════════════


def _field(
    key: str,
    value: Any,
    *,
    value_type: ValueType = ValueType.amount,
    mode: FieldMode = FieldMode.editable,
    row_key: str | None = None,
) -> FieldValue:
    return FieldValue(
        stable_key=key, value=value, value_type=value_type, mode=mode, row_key=row_key
    )


def _tiny(
    *fields: FieldValue,
    row_keys: dict[str, tuple[str, ...]] | None = None,
    semantic_version: str = "1.0.0",
) -> Projection:
    """只为反证比较面而造的最小 projection（不过 contract 校验，本判据也不需要）。"""
    return Projection(
        contract_id="c",
        semantic_version=semantic_version,
        document_type="xlsx",
        values={str(field.stable_key): field for field in fields},
        row_keys=dict(row_keys or {}),
    )


def test_comparison_surface_covers_every_dataclass_field() -> None:
    """**Validates: Requirements 1.2**

    判据面必须覆盖 `Projection` / `FieldValue` 的**每个** dataclass 字段。将来谁给它们加一个
    字段而忘了进 `_field_signature` / `projection_differences`，这条立刻红 —— 否则 P2 会从
    「逐字段相等」悄悄退化成「我们当年想到的那几个字段相等」，而退化过程没有任何判据看得见。
    """
    assert {f.name for f in dataclasses.fields(Projection)} == _PROJECTION_FIELDS, (
        "Projection 的字段集变了，比较面未同步：实测 "
        f"{sorted(f.name for f in dataclasses.fields(Projection))}"
    )
    assert {f.name for f in dataclasses.fields(FieldValue)} == _FIELD_VALUE_FIELDS, (
        "FieldValue 的字段集变了，比较面未同步：实测 "
        f"{sorted(f.name for f in dataclasses.fields(FieldValue))}"
    )
    # 比较面不是「声明了就算覆盖」：`_field_signature` 的元数必须与字段数一致。
    assert len(_field_signature(_field("t/x", 1))) == len(_FIELD_VALUE_FIELDS)


#: 在 `==` 下**相等**、落盘字节却不同的值对。判据若用 `==`，这些全会被判成等值。
_LOOSELY_EQUAL_PAIRS: tuple[tuple[Any, Any, ValueType], ...] = (
    (0, 0.0, ValueType.amount),
    (0, Decimal("0"), ValueType.amount),
    (1, 1.0, ValueType.amount),
    (Decimal("1.50"), Decimal("1.5"), ValueType.amount),
    (0, False, ValueType.integer),
    (1, True, ValueType.integer),
)


@pytest.mark.parametrize("left,right,value_type", _LOOSELY_EQUAL_PAIRS)
def test_a_loose_comparison_would_make_this_judgement_vacuous(
    left: Any, right: Any, value_type: ValueType
) -> None:
    """**Validates: Requirements 1.2**

    每个值对都先自证「`==` 看不出来」，再要求本判据**必须**看出来。把 `_field_signature` 的
    `repr(field.value)` 换成 `field.value`，这一整组立刻红。
    """
    assert left == right, f"{left!r} 与 {right!r} 在 `==` 下本就不等，这个值对选错了"
    differences = projection_differences(
        _tiny(_field("t/x", left, value_type=value_type)),
        _tiny(_field("t/x", right, value_type=value_type)),
    )
    assert len(differences) == 1 and "t/x" in differences[0], (
        f"{left!r} vs {right!r}（{value_type.value}）被判成等值 —— 比较面退化成 `==` 了："
        f"{differences}"
    )


@pytest.mark.parametrize(
    "left,right",
    [(0, 0.0), (0, Decimal("0")), (1, 1.0), (Decimal("1.50"), Decimal("1.5"))],
)
def test_the_digest_canonicalisation_is_deliberately_looser_than_this_judgement(
    left: Any, right: Any
) -> None:
    """**Validates: Requirements 1.2**

    为什么不复用 `projection_digest_value.canonical_value_for_digest()`：它的**设计目的**
    就是把这些值对折叠成同一个表示（否则业务身份复用恒不命中，见该模块 docstring 与需求
    3.2 / 3.3）。复用它当等值判据，等于主动放弃 P2 最该抓的那一类差异。

    这条把「更松」钉成可执行事实而不是注释里的自我声明：哪天 digest 口径改成不折叠了，它会
    红，届时「本判据与 digest 口径的关系」需要重新裁定（而不是继续照抄本文件的说法）。
    """
    assert canonical_value_for_digest(
        _field("t/x", left)
    ) == canonical_value_for_digest(_field("t/x", right)), (
        f"digest 口径不再把 {left!r} 与 {right!r} 折叠成同一表示 —— "
        "两套口径的分工变了，请重新裁定本判据是否仍需自建比较面"
    )


class TestEveryKindOfDifferenceIsRed:
    """缺字段 / 多字段 / 值变 / 类型变 / mode 变 / row_key 变 / 行身份变 / header 变。

    **Validates: Requirements 1.2**

    逐类各一条而不是合成一条：合成一条时漏掉其中任何一类，剩下那些仍会让它绿。
    """

    def test_missing_field_is_red(self) -> None:
        differences = projection_differences(
            _tiny(_field("t/a", 1), _field("t/b", 2)), _tiny(_field("t/a", 1))
        )
        assert len(differences) == 1 and "缺该字段" in differences[0], differences

    def test_extra_field_is_red(self) -> None:
        differences = projection_differences(
            _tiny(_field("t/a", 1)), _tiny(_field("t/a", 1), _field("t/b", 2))
        )
        assert len(differences) == 1 and "多出该字段" in differences[0], differences

    def test_changed_value_is_red(self) -> None:
        differences = projection_differences(
            _tiny(_field("t/a", 1)), _tiny(_field("t/a", 2))
        )
        assert len(differences) == 1 and "t/a" in differences[0], differences

    def test_changed_value_type_is_red(self) -> None:
        differences = projection_differences(
            _tiny(_field("t/a", "1", value_type=ValueType.text)),
            _tiny(_field("t/a", "1", value_type=ValueType.enum)),
        )
        assert len(differences) == 1, differences

    def test_changed_mode_is_red(self) -> None:
        differences = projection_differences(
            _tiny(_field("t/a", 1, mode=FieldMode.editable)),
            _tiny(_field("t/a", 1, mode=FieldMode.auto_source)),
        )
        assert len(differences) == 1, differences

    def test_changed_row_key_is_red(self) -> None:
        differences = projection_differences(
            _tiny(_field("t/a", 1, row_key="GTROW-1")),
            _tiny(_field("t/a", 1, row_key="GTROW-2")),
        )
        assert len(differences) == 1, differences

    def test_changed_row_identity_order_is_red(self) -> None:
        """行身份是**有序**的：顺序变了就是产物变了，不得按集合比。"""
        differences = projection_differences(
            _tiny(row_keys={"t": ("r1", "r2")}), _tiny(row_keys={"t": ("r2", "r1")})
        )
        assert len(differences) == 1 and "row_keys[t]" in differences[0], differences

    def test_changed_header_is_red(self) -> None:
        differences = projection_differences(
            _tiny(semantic_version="1.0.0"), _tiny(semantic_version="1.0.1")
        )
        assert len(differences) == 1 and "header" in differences[0], differences

    def test_identical_projections_are_green(self) -> None:
        """反向一条：判据不是「什么都报红」。"""
        assert (
            projection_differences(
                _tiny(_field("t/a", 1, row_key="r1"), row_keys={"t": ("r1",)}),
                _tiny(_field("t/a", 1, row_key="r1"), row_keys={"t": ("r1",)}),
            )
            == ()
        )

    def test_the_difference_list_is_complete_not_first_only(self) -> None:
        """三处差异就报三处 —— 与 decline 原因同一条纪律（完整、确定）。"""
        differences = projection_differences(
            _tiny(_field("t/a", 1), _field("t/b", 2), _field("t/c", 3)),
            _tiny(_field("t/a", 9), _field("t/b", 8), _field("t/c", 7)),
        )
        assert len(differences) == 3, differences
        assert differences == tuple(sorted(differences)), f"输出不确定：{differences}"


# ═══════════════════════════════════════════════════════════════════════════
# ⑤ 与生产发布门的关系：本判据严格更强（所以不能拿发布门代替它）
# ═══════════════════════════════════════════════════════════════════════════


def test_the_production_verify_gate_is_strictly_weaker_than_this_judgement(
    both_paths: BothPaths,
) -> None:
    """**Validates: Requirements 1.2**

    `excel_extract.verify_roundtrip_equivalence()` 是生产的反读**发布门**，比较范围刻意只含
    `mode=editable`（公式 / auto_source 的值由服务端写、由 OO 重算，逐字节相等不是它们的
    正确性判据 —— 那一格归 `verify_formula_regions`）。

    两条断言合起来说明它**不能**代替本判据：

    * 它对本次两份产物给出 `equivalent=True` —— 与本判据结论一致，没有矛盾；
    * 但它比对的 key 是全量 key 的**真子集** ⇒ 一个整体落在受保护字段上的 binding（D4 的
      `revenue_detail_rows` 那 12 处全是 `cached_value_only`）漏写了，它一句话都不会说。

    ⚠️ 本条不是在挑发布门的毛病：发布门放宽受保护字段是**对的**（不放宽会在真实数据上恒不
    通过）。它只是说明「发布门通过」不等于「新旧产物等值」，需求 1.2 要的是后者。
    """
    report = verify_roundtrip_equivalence(
        expected=both_paths.chained_extract,
        extracted=both_paths.single_extract,
        contract=both_paths.world.contract,
    )
    assert report.equivalent, (
        f"生产发布门判两份产物不等值，与本判据结论冲突：{report.first_difference}"
    )
    compared = set(report.compared_keys)
    every_key = set(both_paths.chained_extract.values)
    assert compared < every_key, (
        f"发布门比对的 key（{len(compared)}）不再是全量 key（{len(every_key)}）的真子集 —— "
        "它的范围变了，本判据与它的分工需要重新裁定"
    )
    assert compared, "发布门一个 key 都没比 ⇒ `_is_editable` 匹配全落空，那是它自己的缺陷"
