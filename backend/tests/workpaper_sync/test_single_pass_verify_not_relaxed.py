# -*- coding: utf-8 -*-
"""任务 9 · P5：verify 的判据一字不放宽（复用**解析** ≠ 复用**结论**）。

spec: oo-single-pass-materialize-and-room-leave · Requirement 2.3

═══ 命题 ═══════════════════════════════════════════════════════════════════════

任务 8 让 materialize / extract / verify 共用一份解析结果。本文件回答的是它带来的那个
问题：**共享解析之后，verify 还挡得住一份真的有缺陷的产物吗？**

与前四个判据文件分工（失败时从文件名就能分清是哪一问）：

| 文件 | 命题 |
|---|---|
| `test_single_pass_materialize.py` | 提速有没有发生（P1，趟数） |
| `test_single_pass_artifact_equivalence.py` | 提速是否以**少写**为代价（P2，产物等值） |
| `test_single_pass_parse_reuse.py` | 同一份字节读了几遍（P4，解析次数）+ 开关复用**结论相同** |
| **本文件** | verify 的**比较面**有没有被削，以及缺陷产物是否**真的**打红（P5） |

任务 8 已经断过「开/关复用结论相同」。本文件**不重跑那一条**，而是往前一步：断**比较面
本身**（比了哪些 key / 哪些部件 / 覆盖多少项）在两侧逐项相同 —— 结论相同只说明这次没
漂，比较面相同才挡得住「有人静默把面削窄」（那种改动会让结论继续「相同」地全绿）。

═══ 五个 verify 门与各自的比较面（实测，不是读注释得来）══════════════════════════

生产的 verify 不是一个函数，是 `ContentMutationService._stage_cpu_segment_scoped` 里
**三道**串起来的门（另两道在 OO→HTML 的 `verify_before_commit` 上）。需求 2.3 说的
「反读等值仍须逐字段比对」指名的是 G1；而任务 8 的解析共享真正碰到的是 G4 与 G5。

| 门 | 实现 | 比较面（真库 D4 实测） | 不红时 |
|---|---|---|---|
| **G1** 反读等值（生产发布门） | `ContentMutationService._assert_roundtrip_equivalent` | 受管 key 去掉 `word_only` + `PROTECTED_MODES` ⇒ 实测 **166**（218 个 key 里 52 个 `formula` 被排除），逐 key `merge.values_equal` | 缺 key / 多 key / 值不等 |
| **G2** 反读等值（OO→HTML） | `excel_extract.verify_roundtrip_equivalence` | 只含 `mode=editable` ⇒ 实测同为 **166** | 同上 |
| **G3** 受保护公式区 | `excel_extract.verify_formula_regions` | G1/G2 排除掉的那 52 个 `formula` 格由它管 | 公式被改写 / 被替字面量 |
| **G4** 未管理区域 | `adapters/excel.verify_unmanaged_regions` → `excel_extract.verify_unmanaged_regions` × 39 binding + `assert_equivalent()` | 8 个 aspect 的逐 part digest，实测每 binding 覆盖 132 个 part（`shared_strings_prefix` 1233 项 / `managed_sheet_unmanaged_cells` 225 项 …） | 受管区之外任何字节变化 |
| **G5** 发布时刻结构身份 | `publish_time_structure_hash.compute_structure_hash_from_artifact` → `collect_workbook_structure` + `assert_no_structure_drift` | 实测 **775** 条受管结构坐标（含转置 sheet 的字段格存在性，按 `ws._cells` 成员关系判） | 受管坐标少了 / 变了 |

🔴 实测结论：**每个门只看得见一类缺陷，另外两类它一定是绿的**（见 §二 的归因表）。
所以需求 2.3 的「verify 必红」要读成「verify **这一段**失败、发布被拦住」，而不是
「三个门同时红」；其余门保持绿是**分工正确**，不是盲区。
"""

# ═══ 为什么反证输入必须是**产物变异**，不是「漏写一个 binding」════════════════════
#
# design 五 P5 的反证方式写「产物少一字段 ⇒ verify 必红」。附录 B.4 已经警告过：在
# **自反读** projection 上「漏写一个 binding」不等于「产物少一个字段」。本任务把这件事
# 量到了底（§三）：steady-state substrate 是 materialize 的**不动点**（产物与 substrate
# 逐 entry 内容全同），于是漏写 `d4_10_rows` / `d4_32_groups` 的全部写入之后产物与正确
# 产物**逐字节相同** —— 连任务 4 那条字节判据都是绿的。那不是判据瞎，是**产物真的没缺陷**
# （写回去的值本来就在那儿、形态也一样）。
#
# ⇒ 真正的 P5 反证必须让**产物本身**缺东西：对产物字节做定点变异（抹掉一个受管格 /
#   抹掉行身份载体格 / 抹掉未管理格 / 抹掉转置字段格），再看哪个门红。这四条在 §二。
#
# 附录 F.8 第 1 条那条提醒也在这里落地：`collect_workbook_structure` 里那次
# `extract_transposed_workbook` 的返回值**被丢掉**（纯 fail-closed 校验器）⇒ 「转置 sheet
# 少一个字段」是被 **G5 结构漂移**抓住的，不是 G4。判据按实测归因，不把 G5 的功劳记给 verify。
from __future__ import annotations

import ast
import contextlib
import functools
import inspect
import re
import zipfile
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.excel_structure_fingerprint import clear_structure_fingerprint_cache
from app.services.workpaper_sync import content_mutation as CM
from app.services.workpaper_sync import excel_extract as EE
from app.services.workpaper_sync import excel_materialize as EM
from app.services.workpaper_sync import phase5_d4_revenue_detail as D4
from app.services.workpaper_sync.adapters.base import FieldMode, UnmanagedRegionReport
from app.services.workpaper_sync.content_mutation import (
    PROTECTED_MODES,
    ContentMutationService,
    RoundtripEquivalenceError,
)
from app.services.workpaper_sync.contracts import ContractDriftError
from app.services.workpaper_sync.excel_extract import (
    UNMANAGED_ASPECTS,
    verify_roundtrip_equivalence,
    workbook_read_scope,
)
from app.services.workpaper_sync.parse_cache import clear_all_parse_caches
from app.services.workpaper_sync.publish_time_structure_hash import (
    anchors_from_instrumentation_specs,
    compute_structure_hash_from_artifact,
)
from app.services.workpaper_sync.published_identity_observer import (
    collect_workbook_structure,
)
from app.services.workpaper_sync.transposed_registry import resolve_transposed_specs
from tests.workpaper_sync.d4_materialize_harness import (
    D4World,
    build_world,
    rebased_world,
)
from tests.workpaper_sync.test_single_pass_artifact_equivalence import (
    compare_zip_entries,
    drop_binding_writes,
    projection_differences,
)
from tests.workpaper_sync.test_single_pass_parse_reuse import reuse_disabled

# ═══════════════════════════════════════════════════════════════════════════
# 实测常数（改这些数必须同时刷新 design 附录 G）
# ═══════════════════════════════════════════════════════════════════════════

#: 真库 D4 的 binding 数。
BINDING_COUNT = 39

#: 产物反读出来的受管字段数（任务 4 附录 B.3 同一个数）。
EXTRACTED_FIELD_COUNT = 218

#: G1 / G2 实际比对的 key 数 = `mode=editable` 的字段数。剩下 52 个是 `formula`，
#: 由 G3（`verify_formula_regions`）管 —— 两条反读门排除它们是**有意**的（公式值由 OO
#: 重算，逐字节相等不是它们的正确性判据），不是把面削窄。
ROUNDTRIP_COMPARED_KEYS = 166
PROTECTED_FIELD_COUNT = EXTRACTED_FIELD_COUNT - ROUNDTRIP_COMPARED_KEYS

#: G4 的 `unmanaged_region_digest` 调用数 = 39 binding × (before + after)。
UNMANAGED_DIGEST_CALLS = BINDING_COUNT * 2

#: G5 观测到的受管结构坐标条数。
STRUCTURE_COORDINATE_COUNT = 775

#: 转置 sheet 数（D4-29 客户结构 + D4-12 合同）。
TRANSPOSED_SPECS = 2

#: 生产 CPU 段里三道门的调用标记（与 `test_single_pass_parse_reuse` 的 SEGMENT_STEP_MARKERS
#: 同一份口径，但这里只列**门**，不列 materialize / extract）。
PRODUCTION_GATE_MARKERS = (
    "self._assert_roundtrip_equivalent(",
    "adapter.verify_unmanaged_regions(",
    "unmanaged.assert_equivalent()",
    "self._projection_structure_hash(",
)


# ═══════════════════════════════════════════════════════════════════════════
# 观测器与变异器（一律只观测 / 只改**产物字节**，不动任何生产判据）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class GateRun:
    """一次 verify 的**全部结论** + **全部比较面**。

    结论与比较面刻意分开存：结论回答「这次红没红」，比较面回答「它比了什么」。任务 8 已经
    断过前者在开/关复用两侧相同；本文件要断的是后者（面被削窄时结论照样「相同」地全绿）。
    """

    label: str
    extract_ok: bool
    extract_error: str = ""
    extract_keys: tuple[str, ...] = ()
    g1_red: bool = False
    g1_error: str = ""
    g1_pairs: tuple[str, ...] = ()
    g4_verdicts: tuple[bool, ...] = ()
    g4_first_difference: str | None = None
    g4_raised: str = ""
    g4_surface: tuple[tuple[Any, ...], ...] = ()
    g5_red: bool = False
    g5_error: str = ""
    g5_hash: str = ""
    g5_structure: tuple[tuple[str, ...], ...] = ()
    reread_differences: tuple[str, ...] = dataclass_field(default_factory=tuple)

    @property
    def g4_red(self) -> bool:
        """抛了 / 有 binding 报漂移 / **一条结论都没收到** 三者任一即红。

        最后一条是刻意的：`all(())` 是 `True`，若不特判，「G4 压根没跑」与「G4 全绿」在
        判据里就是同一个答案 —— 而 §二 的归因表全靠「别的门是**绿**的」这句话有内容。
        """
        if self.g4_raised:
            return True
        return not self.g4_verdicts or not all(self.g4_verdicts)

    @property
    def g4_drifted(self) -> int:
        return sum(1 for verdict in self.g4_verdicts if not verdict)

    @property
    def red_gates(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, red in (("G1", self.g1_red), ("G4", self.g4_red), ("G5", self.g5_red))
            if red
        )


@contextlib.contextmanager
def g1_surface_witness() -> Iterator[list[str]]:
    """记录 G1 实际拿去比的**每一对值** —— 那就是它的比较面。

    打在 `content_mutation.values_equal` 的**模块属性**上：门在函数体里按模块全局名解析它
    （与 `MaterializeCallCounter` 对 `load_workbook` 的做法同一条纪律）。记 `repr` 而不是
    值本身：`0` / `0.0` / `Decimal('0')` 在 `==` 下相等，用值比会让「面变了」看不出来。
    """
    seen: list[str] = []
    original = CM.values_equal

    def watched(left: Any, right: Any, value_type: Any) -> Any:
        seen.append(f"{getattr(value_type, 'value', value_type)}|{left!r}|{right!r}")
        return original(left, right, value_type)

    CM.values_equal = watched  # type: ignore[assignment]
    try:
        yield seen
    finally:
        CM.values_equal = original  # type: ignore[assignment]


@contextlib.contextmanager
def g4_surface_witness() -> Iterator[list[tuple[Any, ...]]]:
    """记录每次 unmanaged digest 的**覆盖面**：aspect 名单 + 每 aspect 覆盖项数 + part 数。

    刻意**不记 digest 值**：digest 值是**结论**（任务 8 已经逐 binding 比过），覆盖面才是
    「它到底看了多少东西」。有人把某个 aspect 的采集范围悄悄缩小（少扫几个 part、少几行
    sharedStrings），digest 会变成另一个「两侧一致」的值而结论仍然全绿 —— 只有覆盖数会掉。
    """
    seen: list[tuple[Any, ...]] = []
    original = EE.unmanaged_region_digest

    def watched(path: Any, **kwargs: Any) -> Any:
        result = original(path, **kwargs)
        seen.append(
            (
                str(getattr(kwargs.get("region"), "sheet_part", "")),
                tuple(sorted(result.aspects)),
                tuple(sorted(result.coverage.items())),
                int(result.part_count),
            )
        )
        return result

    EE.unmanaged_region_digest = watched  # type: ignore[assignment]
    try:
        yield seen
    finally:
        EE.unmanaged_region_digest = original  # type: ignore[assignment]


@contextlib.contextmanager
def unmanaged_verdict_collector(sink: list[bool]) -> Iterator[None]:
    """把 `assert_equivalent` 换成收集器（同 design 附录 E.2 / F.5 的理由）。

    生产那个循环**逐 binding 比完就 assert**，第一个 binding 红就抛 ⇒ 不换成收集器的话
    39 条结论只拿到 1 条，「哪些 binding 红了」这件事看不见。换的是**测试侧的观察方式**，
    门本身的比较逻辑一字未动（`equivalent` 仍由生产算）。
    """
    original = UnmanagedRegionReport.assert_equivalent

    def collecting(self: Any) -> None:
        sink.append(bool(self.equivalent))

    UnmanagedRegionReport.assert_equivalent = collecting  # type: ignore[method-assign]
    try:
        yield
    finally:
        UnmanagedRegionReport.assert_equivalent = original  # type: ignore[method-assign]


@contextlib.contextmanager
def plan_witness() -> Iterator[list[Any]]:
    """记录每个 binding 的计划（sheet part + 逐处写入）—— 变异目标从这里来。

    目标坐标**不写死**：写死 `sheet7!A13` 会在契约一动时变成「测了一个不存在的格子」。
    从生产计划里取，则变异永远打在**本次真实受管**的格子上。
    """
    seen: list[Any] = []
    original = EM._plan_materialize_step

    def watched(**kwargs: Any) -> Any:
        step = original(**kwargs)
        seen.append(step)
        return step

    EM._plan_materialize_step = watched  # type: ignore[assignment]
    try:
        yield seen
    finally:
        EM._plan_materialize_step = original  # type: ignore[assignment]


_CELL_PAIRED = "<c r=\"{coord}\"[^>]*?>.*?</c>"
_CELL_SELF_CLOSING = "<c r=\"{coord}\"[^>]*/>"


def drop_cell_from_xml(data: bytes, coord: str) -> bytes:
    """从一个 sheet part 的 XML 里抹掉坐标为 `coord` 的那个 `<c>` 元素（**恰好一个**）。

    抹掉整个 `<c>` 而不是把 `<v>` 清空：前者才是「这一格在文件里不存在」，也正是
    `collect_workbook_structure` 判「转置字段格存不存在」用的那个事实。命中数必须是 1 ——
    0 说明坐标错了（变异空转），>1 说明 XML 里有重复坐标（那是另一个问题）。
    """
    paired = re.compile(_CELL_PAIRED.format(coord=re.escape(coord)).encode(), re.S)
    self_closing = re.compile(_CELL_SELF_CLOSING.format(coord=re.escape(coord)).encode())
    new, hits = paired.subn(b"", data, count=1)
    if hits == 0:
        new, hits = self_closing.subn(b"", data, count=1)
    if hits != 1:
        raise AssertionError(
            f"坐标 {coord} 在该 part 里命中 {hits} 次（应为 1）⇒ 变异是空转，反证不成立"
        )
    return new


def mutate_artifact(
    src: Path, dst: Path, *, part: str, transform: Callable[[bytes], bytes]
) -> Path:
    """把 `src` 逐 entry 拷成 `dst`，只对 `part` 应用 `transform`。

    重打一遍 zip（而不是原地改）是为了让变异产物是一份**独立文件**：同一路径改内容会把
    「结论有没有被缓存」那组判据的分母搅掉（缓存键含 mtime/size）。
    """
    hit = False
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == part:
                data = transform(data)
                hit = True
            zout.writestr(info, data)
    if not hit:
        raise AssertionError(f"part {part!r} 不在 {src.name} 里 ⇒ 变异空转")
    return dst


# ═══════════════════════════════════════════════════════════════════════════
# 三道门跑一遍（形态与生产 `_stage_cpu_segment_scoped` 同序，判据自检见 §一）
# ═══════════════════════════════════════════════════════════════════════════

_ANCHORS = anchors_from_instrumentation_specs(D4.instrumentation_specs())


def run_gates(
    *,
    world: D4World,
    before: Path,
    after: Path,
    projection: Any,
    label: str,
    reuse: bool = True,
    capture_surface: bool = False,
) -> GateRun:
    """在**一个** `workbook_read_scope()` 里跑 extract → G1 → G4 → G5。

    每个门各自 try/except：本文件要的是「哪个门红了、别的门有没有跟着红」这张归因表，
    第一个门一抛就整段中断的话，后两个门的结论就永远是「未知」而不是「绿」——那会让
    §二 的归因表退化成「至少有一个门红」，而那句话对任何缺陷都成立（近似空转）。
    """
    clear_all_parse_caches()
    clear_structure_fingerprint_cache()
    run = GateRun(label=label, extract_ok=False)
    verdicts: list[bool] = []
    gate = contextlib.nullcontext() if reuse else reuse_disabled()
    with gate, workbook_read_scope():
        try:
            extracted = world.adapter.extract(artifact=after, contract=world.contract)
        except Exception as exc:  # noqa: BLE001 - 门的红/绿本身就是被测对象
            run.extract_error = f"{type(exc).__name__}: {exc}"
            extracted = None
        else:
            run.extract_ok = True
            run.extract_keys = tuple(sorted(extracted.values))
        if extracted is not None:
            surface: list[str] = []
            witness = g1_surface_witness() if capture_surface else contextlib.nullcontext([])
            with witness as pairs:  # type: ignore[assignment]
                try:
                    ContentMutationService._assert_roundtrip_equivalent(  # noqa: SLF001
                        None,  # type: ignore[arg-type]
                        intended=projection,
                        extracted=extracted,
                        contract=world.contract,
                    )
                except RoundtripEquivalenceError as exc:
                    run.g1_red = True
                    run.g1_error = str(exc)
                surface = list(pairs or ())
            run.g1_pairs = tuple(sorted(surface))
            run.reread_differences = projection_differences(
                projection, extracted, left_label="intended", right_label="reread"
            )
        g4_witness = g4_surface_witness() if capture_surface else contextlib.nullcontext([])
        with g4_witness as g4_calls:  # type: ignore[assignment]
            try:
                with unmanaged_verdict_collector(verdicts):
                    report = world.adapter.verify_unmanaged_regions(
                        before=before,
                        after=after,
                        contract=world.contract,
                        row_shift=None,
                        total_formula_rows=(),
                        propagation=None,
                        per_table_shift=None,
                    )
                run.g4_first_difference = report.first_difference
            except Exception as exc:  # noqa: BLE001
                run.g4_raised = f"{type(exc).__name__}: {exc}"
            run.g4_surface = tuple(g4_calls or ())
        run.g4_verdicts = tuple(verdicts)
        try:
            run.g5_hash = compute_structure_hash_from_artifact(
                data=after.read_bytes(), contract=world.contract, anchors=_ANCHORS
            )
        except Exception as exc:  # noqa: BLE001
            run.g5_red = True
            run.g5_error = f"{type(exc).__name__}: {exc}"
        if capture_surface:
            _fp, _physical, _inv, structure = collect_workbook_structure(
                data=after.read_bytes(),
                contract=world.contract,
                sheet_anchors=list(_ANCHORS),
            )
            run.g5_structure = tuple(sorted(tuple(str(x) for x in row) for row in structure))
    return run


# ═══════════════════════════════════════════════════════════════════════════
# fixture：第一代 world / steady-state world / 四个变异产物
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SteadyState:
    """steady-state（第二代）world + 正确产物 + 从生产计划取来的变异靶点。"""

    world: D4World
    first_generation: Path
    artifact: Path
    targets: dict[str, tuple[str, str]]
    field_keys: dict[str, str]
    plan_write_counts: dict[str, int]


@pytest.fixture(scope="module")
def first_generation_world(tmp_path_factory: pytest.TempPathFactory) -> D4World:
    """真 D4 模板 + 真契约 + 真 39 binding（= `build_world` 的 instrumented 模板 substrate）。"""
    return build_world(tmp_path_factory.mktemp("d4-verify-p5"))


@pytest.fixture(scope="module")
def steady(first_generation_world: D4World) -> SteadyState:
    """把第一次物化的产物当 substrate，再物化一次 —— 这才是生产的形态。

    附录 F.8 第 2 条点名过：模板 substrate 上 verify 39/39 本来就红，拿它当变异反证的分母
    「必红」没有信号。靶点从**生产计划**里取（不写死坐标）：一个 `editable` 的受管格、
    一个行身份载体格、一个非受管 sheet 上的格、一个转置字段格。
    """
    gen1 = first_generation_world.materialize("generation-1.xlsx")
    world = rebased_world(
        first_generation_world, substrate_bytes=gen1.read_bytes(), label="steady"
    )
    with plan_witness() as steps:
        artifact = world.materialize("steady-good.xlsx")

    targets: dict[str, tuple[str, str]] = {}
    field_keys: dict[str, str] = {}
    managed_parts = {str(step.plan.sheet_part) for step in steps}
    for step in steps:
        part = str(step.plan.sheet_part)
        for write in step.plan.writes:
            if (
                "managed_editable" not in targets
                and write.stable_field_key
                and write.mode is FieldMode.editable
                and write.value not in (None, "")
            ):
                targets["managed_editable"] = (part, write.coord)
                field_keys["managed_editable"] = str(write.stable_field_key)
        if "row_identity" not in targets and step.binding.uuid_column:
            rows = sorted(
                {
                    int(re.sub(r"[A-Z]+", "", write.coord))
                    for write in step.plan.writes
                    if write.row_key and write.mode is FieldMode.editable
                }
            )
            if rows:
                targets["row_identity"] = (part, f"{step.binding.uuid_column}{rows[0]}")

    with zipfile.ZipFile(artifact) as archive:
        for name in sorted(archive.namelist()):
            if not name.startswith("xl/worksheets/sheet") or name in managed_parts:
                continue
            hit = re.search(rb"<c r=\"([A-Z]+\d+)\"[^>]*>\s*<v>", archive.read(name))
            if hit:
                targets["unmanaged_cell"] = (name, hit.group(1).decode())
                break
        specs = resolve_transposed_specs(world.contract)
        if specs:
            spec = specs[0]
            part = EE._sheet_parts(archive).get(spec.managed_sheet)
            if part:
                targets["transposed_field"] = (
                    str(part),
                    f"{spec.first_entity_column}{spec.header_row + 1}",
                )
    return SteadyState(
        world=world,
        first_generation=gen1,
        artifact=artifact,
        targets=targets,
        field_keys=field_keys,
        plan_write_counts={
            str(step.binding.table_key): len(step.plan.writes) for step in steps
        },
    )


@pytest.fixture(scope="module")
def steady_gates(steady: SteadyState) -> GateRun:
    """正确产物上的三道门 + 完整比较面（= 反证的**分母**）。"""
    return run_gates(
        world=steady.world,
        before=steady.world.base,
        after=steady.artifact,
        projection=steady.world.projection,
        label="steady-good",
        capture_surface=True,
    )


@pytest.fixture(scope="module")
def steady_gates_without_reuse(steady: SteadyState) -> GateRun:
    """同一份正确产物、同样三道门，但**掐掉解析复用** —— 比较面的对照侧。"""
    return run_gates(
        world=steady.world,
        before=steady.world.base,
        after=steady.artifact,
        projection=steady.world.projection,
        label="steady-good-reuse-off",
        reuse=False,
        capture_surface=True,
    )


@pytest.fixture(scope="module")
def first_generation_gates(
    first_generation_world: D4World, steady: SteadyState
) -> GateRun:
    """第一代（模板 substrate）上的三道门 —— 用来说明它**不能**当分母。"""
    return run_gates(
        world=first_generation_world,
        before=first_generation_world.base,
        after=steady.first_generation,
        projection=first_generation_world.projection,
        label="generation-1",
    )


@pytest.fixture(scope="module")
def mutated(steady: SteadyState) -> dict[str, Path]:
    """四个变异产物（只改**产物字节**，不改生产代码、不改 projection、不改契约）。"""
    out: dict[str, Path] = {}
    for name, (part, coord) in steady.targets.items():
        out[name] = mutate_artifact(
            steady.artifact,
            steady.artifact.with_name(f"mutated-{name}.xlsx"),
            part=part,
            transform=lambda data, c=coord: drop_cell_from_xml(data, c),
        )
    return out


@pytest.fixture(scope="module")
def mutation_gates(steady: SteadyState, mutated: dict[str, Path]) -> dict[str, GateRun]:
    """四个变异产物各跑一遍三道门 —— §二 的归因表就是它。"""
    return {
        name: run_gates(
            world=steady.world,
            before=steady.world.base,
            after=path,
            projection=steady.world.projection,
            label=f"mutated-{name}",
        )
        for name, path in sorted(mutated.items())
    }


# ═══════════════════════════════════════════════════════════════════════════
# 一、门的清册与分母（没有这一节，下面每条「必红」都可能是空转）
# ═══════════════════════════════════════════════════════════════════════════


def test_the_gate_map_matches_the_production_segment() -> None:
    """**Validates: Requirements 2.3**

    本文件量的是「生产那三道门」。生产的门清单一变，本文件就是在量一段不存在的代码。
    所以先对账：四个标记逐条在 `_stage_cpu_segment_scoped` 里找得到，且顺序与生产一致
    （反读等值在未管理区域之前、结构身份在最后）。

    同时钉住 design 六 第 3 条：门与 extract **不是**一个函数 —— `verify_unmanaged_regions`
    的形参里不得出现 extract 的产物（它必须自己从字节重算，而不是接受别人递过来的结论）。
    """
    from app.services.workpaper_sync.adapters.excel import ExcelSyncAdapter

    source = inspect.getsource(ContentMutationService._stage_cpu_segment_scoped)
    positions = []
    for marker in PRODUCTION_GATE_MARKERS:
        assert marker in source, (
            f"生产 CPU 段里找不到门 {marker!r} ⇒ 门被删了或改名了，本文件的归因表过期"
        )
        positions.append(source.index(marker))
    assert positions == sorted(positions), (
        f"生产三道门的顺序变了（实测偏移 {positions}）—— 本文件按「G1 → G4 → G5」跑，"
        "顺序不同的话归因表里「别的门是绿的」这句话就不可比"
    )
    signature = inspect.signature(ExcelSyncAdapter.verify_unmanaged_regions)
    leaked = {"extracted", "projection", "extract_outcome"} & set(signature.parameters)
    assert not leaked, (
        f"`verify_unmanaged_regions` 开始接受 extract 侧的产物 {leaked} ⇒ 复用了**结论**"
    )


def test_the_first_generation_world_cannot_be_the_denominator(
    first_generation_gates: GateRun,
) -> None:
    """**Validates: Requirements 2.3**

    附录 F.8 第 2 条的实测在这里被钉成判据：**模板 substrate 上 G4 本来就 39/39 红**
    （harness base 的 `styles.xml` 从未被 openpyxl 重序列化，而转置 sheet 的 `wb.save()`
    会重写整簿状态），首个差异恒为 `workbook_and_styles`。

    ⇒ 在第一代 world 上做「变异后 verify 必红」的反证是**假的**：不变异它也红。这条判据
    存在的意义就是把这个陷阱显式化 —— 哪天它变绿了（例如 harness 改了 base 的产生方式），
    下面那些「steady state 才是分母」的说法就要重写，而不是默默继续用。
    """
    assert first_generation_gates.g4_red, (
        "第一代 world 上 G4 竟然是绿的 —— 附录 E.2 / F.8 的「模板 → 第一代产物」效应没了，"
        "本文件关于分母的全部叙述需要重写"
    )
    assert first_generation_gates.g4_drifted == BINDING_COUNT, (
        f"第一代 world 上 G4 漂移 {first_generation_gates.g4_drifted} 个 binding"
        f"（实测应为全部 {BINDING_COUNT} 个）"
    )
    assert (first_generation_gates.g4_first_difference or "").startswith(
        "workbook_and_styles"
    ), (
        "第一代的首个差异面不再是 `workbook_and_styles`："
        f"{first_generation_gates.g4_first_difference}"
    )


def test_all_four_mutation_targets_were_located_in_the_real_artifact(
    steady: SteadyState,
) -> None:
    """**Validates: Requirements 2.3**

    §二 的四类变异各要一个真实靶点，全部从**生产计划 / 真实产物**里取（不写死坐标）。四个
    里少一个，对应那条反证就会 `KeyError`，而不是静默变绿 —— 但那时报错读起来像「测试坏了」。
    这条先把「靶点都找到了、而且互不相同」说清楚。

    转置 sheet 数一并钉住（`TRANSPOSED_SPECS`）：一张转置 sheet 都没有的话，附录 F.8 第 1 条
    那条归因（转置字段缺失归 G5）在本 world 上就没有分母。
    """
    assert set(steady.targets) == {
        "managed_editable",
        "row_identity",
        "unmanaged_cell",
        "transposed_field",
    }, f"变异靶点没凑齐：{sorted(steady.targets)}"
    assert len(set(steady.targets.values())) == 4, (
        f"有两类变异打在同一个格子上 ⇒ 归因表会混：{steady.targets}"
    )
    assert steady.field_keys.get("managed_editable"), "受管 editable 靶点没有 stable key"
    assert len(resolve_transposed_specs(steady.world.contract)) == TRANSPOSED_SPECS, (
        "转置 spec 数变了 —— 本文件的常数与 design 附录 G 必须一起刷新"
    )
    managed_parts = {part for part, _coord in steady.targets.values()}
    assert steady.targets["unmanaged_cell"][0] not in {
        steady.targets["managed_editable"][0],
        steady.targets["row_identity"][0],
    }, f"「非受管」靶点落在了受管 sheet 上：{steady.targets['unmanaged_cell']}"
    assert len(managed_parts) >= 2


def test_the_steady_state_substrate_is_a_fixed_point_and_every_gate_is_green(
    steady: SteadyState, steady_gates: GateRun
) -> None:
    """**Validates: Requirements 2.3**　（§二 全部反证的**分母**）

    生产的 substrate 恒是上一次发布的产物。把第一代产物当 substrate 再物化一次，实测：

    * 产物与 substrate **逐 zip entry 内容全同**（`date_time` 分流，同附录 B.3 口径）
      ⇒ materialize 在 steady state 上是**不动点**；
    * 三道门**全绿**：G1 不抛、G4 39/39 等价、G5 算得出结构身份。

    这才是「变异之后必须红」能成立的分母。三条一起断：少了不动点那条，「全绿」可能是
    因为门恰好没看那一块；少了 39 这个数，循环跑了一个 binding 也叫「全绿」。
    """
    comparison = compare_zip_entries(steady.world.base, steady.artifact)
    assert comparison.namelist_equal and not comparison.name_differences, (
        f"steady 产物与 substrate 的 zip 条目集合不同：{comparison.name_differences}"
    )
    assert comparison.content_differences == (), (
        "steady state 不是不动点（产物与 substrate 内容不同）："
        f"{comparison.content_differences}"
    )
    assert steady_gates.extract_ok and len(steady_gates.extract_keys) == EXTRACTED_FIELD_COUNT, (
        f"steady 产物反读 {len(steady_gates.extract_keys)} 个字段"
        f"（实测应 {EXTRACTED_FIELD_COUNT}）：{steady_gates.extract_error}"
    )
    assert not steady_gates.g1_red, f"分母上 G1 就红了：{steady_gates.g1_error}"
    assert steady_gates.reread_differences == (), (
        "分母上反读与 intended 已有差异：\n" + "\n".join(steady_gates.reread_differences[:5])
    )
    assert len(steady_gates.g4_verdicts) == BINDING_COUNT, (
        f"G4 只产出 {len(steady_gates.g4_verdicts)} 条结论（应 {BINDING_COUNT} 条）⇒ "
        "循环没跑完，「全绿」只覆盖了一部分 binding"
    )
    assert not steady_gates.g4_red, (
        f"分母上 G4 就红了（漂移 {steady_gates.g4_drifted} 个）："
        f"{steady_gates.g4_first_difference}{steady_gates.g4_raised}"
    )
    assert not steady_gates.g5_red and steady_gates.g5_hash, (
        f"分母上 G5 就红了：{steady_gates.g5_error}"
    )
    assert steady_gates.red_gates == (), f"分母上已有红门：{steady_gates.red_gates}"


# ═══════════════════════════════════════════════════════════════════════════
# 二、P5 的变异反证：产物**真的**缺东西 ⇒ 对应的门必红（附带归因：别的门是绿的）
#
# 实测归因表（steady state，四个变异各只改一个 `<c>` 元素）：
#
# | 变异 | extract | G1 反读等值 | G4 未管理区域 | G5 结构身份 |
# |---|---|---|---|---|
# | 抹掉受管 editable 格 | 218 → **217** | **红**（缺该受管字段） | 绿 | 绿 |
# | 抹掉行身份载体格 | 218（行被重新铸号） | **红**（缺该受管字段） | 绿 | 绿 |
# | 抹掉未受管 sheet 的格 | 218 | 绿 | **红** 39/39（`other_sheet_parts`） | 绿 |
# | 抹掉转置字段格 | 218 | 绿 | 绿 | **红**（`ContractDriftError` 结构漂移） |
#
# ⇒ 三个门各看一类缺陷，两两不重叠。需求 2.3 的「verify 必红」= verify **这一段**失败，
#   由**拥有那类缺陷**的门负责；别的门保持绿是分工，不是盲区。
# ═══════════════════════════════════════════════════════════════════════════


def test_removing_one_managed_field_from_the_artifact_turns_the_roundtrip_gate_red(
    steady: SteadyState, mutation_gates: dict[str, GateRun]
) -> None:
    """**Validates: Requirements 2.3**　**Property: P5**（本文件的**主判据**）

    需求 2.3 与 design 五 P5 的字面反证：「故意让产物少一个字段 ⇒ verify 必红」。这里让产物
    **真的**少一个字段 —— 把一个受管 `editable` 格的 `<c>` 元素从产物 XML 里抹掉。实测：

    * 反读字段数 218 → **217**（少的恰是被抹掉那个 key）；
    * G1 抛 `RoundtripEquivalenceError`，消息**点名**那个 stable key。

    三条一起断（缺一条都能被糊过去）：门红了、字段真的少了一个、少的就是靶点那个。
    只断「红了」的话，红也可能来自别的字段的巧合。
    """
    run = mutation_gates["managed_editable"]
    victim_key = steady.field_keys["managed_editable"]
    assert run.extract_ok, f"变异产物反读直接失败了：{run.extract_error}"
    assert len(run.extract_keys) == EXTRACTED_FIELD_COUNT - 1, (
        f"抹掉一个受管格后反读 {len(run.extract_keys)} 个字段"
        f"（应 {EXTRACTED_FIELD_COUNT - 1}）⇒ 变异没让产物少字段，反证前提不成立"
    )
    assert victim_key not in run.extract_keys, (
        f"少的不是靶点 {victim_key!r} ⇒ 变异打偏了"
    )
    assert run.g1_red, (
        f"产物少了受管字段 {victim_key!r}，G1 竟然是绿的 —— 需求 2.3 失守"
    )
    assert victim_key in run.g1_error, (
        f"G1 红了但没点名缺的那个字段（只报「不等值」无法定位）：{run.g1_error}"
    )
    assert "缺少受管字段" in run.g1_error, (
        f"G1 的红不是「缺字段」这一类：{run.g1_error}"
    )


def test_removing_the_row_identity_carrier_turns_the_roundtrip_gate_red(
    mutation_gates: dict[str, GateRun]
) -> None:
    """**Validates: Requirements 2.3**　**Property: P5**

    第二类「少一个字段」：抹掉**行身份载体格**（隐藏 UUID 列那一格）。实测 extract 并不报错，
    而是给那一行**重新铸号**（`GTROW-MINTED-…`）⇒ 原 row_key 下的字段整行消失、换成一批
    新 key。G1 因此报「缺少受管字段」。

    这条与上一条是**两种**缺陷形态（值没了 vs 行身份没了），刻意都覆盖：只测前者的话，
    「identity 载体丢失」这类缺陷有没有门看得见就没有答案。
    """
    run = mutation_gates["row_identity"]
    assert run.extract_ok, f"变异产物反读直接失败了：{run.extract_error}"
    assert run.g1_red, "行身份载体格被抹掉，G1 竟然是绿的"
    assert "缺少受管字段" in run.g1_error or "反读出未提交的受管字段" in run.g1_error, (
        f"G1 的红不是 key 集合类：{run.g1_error}"
    )
    minted = [key for key in run.extract_keys if EE.MINTED_ROW_IDENTITY_PREFIX in key]
    assert minted, (
        "抹掉 identity 载体后没有出现 minted 行身份 ⇒ extract 的行扫描形态变了，"
        f"本条的叙述要同步更新（reread 差异：{run.reread_differences[:2]}）"
    )


def test_a_missing_managed_field_is_invisible_to_the_other_two_gates(
    mutation_gates: dict[str, GateRun]
) -> None:
    """**Validates: Requirements 2.3**（归因，不是抱怨）

    同一份「少一个受管字段」的产物：G4 与 G5 **全绿**。这是**正确**的分工 —— 受管区域按
    定义被排除在未管理区域比对之外（否则每次合法写入都判漂移），而受管**坐标**没变（格子
    不存在与格子为空在 `<dimension>` 之内是同一件事）。

    把它做成判据，是为了让「verify 必红」这句话有精确含义：红的是**拥有这类缺陷**的那个门。
    有人哪天把 G1 关掉（或把它的比较面削成空），这份产物就会**一个门都不红** —— 那时本条
    会和上面那条一起红，而不是只剩一条孤立的「G1 红」在守。
    """
    run = mutation_gates["managed_editable"]
    assert run.red_gates == ("G1",), (
        f"少一个受管字段时红的门是 {run.red_gates}（实测应恰为 G1）—— 归因表变了"
    )
    assert not run.g4_red and run.g4_drifted == 0, (
        f"G4 对受管区域内的缺失也红了（漂移 {run.g4_drifted}）：{run.g4_first_difference}"
    )
    assert not run.g5_red, f"G5 对受管值缺失也红了：{run.g5_error}"


def test_unmanaged_drift_is_caught_only_by_the_unmanaged_gate(
    steady: SteadyState, mutation_gates: dict[str, GateRun]
) -> None:
    """**Validates: Requirements 2.3**

    第三类缺陷：抹掉一个**非受管** sheet 上的格。实测 G4 39/39 红、首个差异面
    `other_sheet_parts`；G1 与 G5 全绿（反读的是受管字段，它们一个都没动）。

    这条同时是 G4 的**承重反证**：分母那条说 G4 在 steady state 上 39/39 绿，单看可能是
    「它什么都没比」。这里改一个字节它就全红 ⇒ 它真的在比。
    """
    run = mutation_gates["unmanaged_cell"]
    part, coord = steady.targets["unmanaged_cell"]
    assert run.g4_red, (
        f"抹掉 {part}!{coord}（非受管 sheet）后 G4 仍是绿的 ⇒ 未管理区域判据形同虚设"
    )
    assert run.g4_drifted == BINDING_COUNT, (
        f"G4 只有 {run.g4_drifted} 个 binding 报漂移（应 {BINDING_COUNT}：整簿级 aspect "
        "对每个 binding 都一样）"
    )
    assert (run.g4_first_difference or "").startswith("other_sheet_parts"), (
        f"首个差异面不是 `other_sheet_parts`：{run.g4_first_difference}"
    )
    assert run.red_gates == ("G4",), (
        f"未管理区域漂移时红的门是 {run.red_gates}（实测应恰为 G4）"
    )
    assert len(run.extract_keys) == EXTRACTED_FIELD_COUNT and not run.g1_red


def test_a_missing_transposed_field_is_caught_by_structure_drift_not_by_verify(
    steady: SteadyState, mutation_gates: dict[str, GateRun]
) -> None:
    """**Validates: Requirements 2.3**　（附录 F.8 第 1 条落地为判据）

    第四类缺陷：抹掉**转置 sheet** 的一个字段格。附录 F.8 第 1 条已经指出
    `collect_workbook_structure` 里那次 `extract_transposed_workbook` 的返回值被丢掉
    （纯 fail-closed 校验器），所以这类缺陷是被 **G5 结构漂移**抓住的。实测证实：

    * G5 抛 `ContractDriftError`，消息点名 `sheet='d4-29-managed'` 与缺失的那个字段；
    * G1 绿（转置字段不在受管 projection 的反读面上）、G4 绿（转置 sheet part 被显式并入
      `all_managed_parts`，见 `adapters/excel` 的注释）。

    ⇒ 不把这条红记到 verify 的账上。哪天有人「优化」掉 `assert_no_structure_drift`，
    这类缺陷就**没有任何门**看得见 —— 本条就是那一天的告警。
    """
    run = mutation_gates["transposed_field"]
    part, coord = steady.targets["transposed_field"]
    assert run.g5_red, (
        f"抹掉转置字段格 {part}!{coord} 后 G5 仍是绿的 ⇒ 结构身份门失守"
    )
    assert ContractDriftError.__name__ in run.g5_error, (
        f"G5 的红不是结构漂移这一类：{run.g5_error}"
    )
    assert "结构漂移" in run.g5_error and "sheet=" in run.g5_error, (
        f"G5 红了但没点名漂移位置：{run.g5_error}"
    )
    assert run.red_gates == ("G5",), (
        f"转置字段缺失时红的门是 {run.red_gates}（实测应恰为 G5 —— 附录 F.8 第 1 条）"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 三、为什么「漏写一个 binding」**不是** P5 的反证（附录 B.4 末段的实测答案）
# ═══════════════════════════════════════════════════════════════════════════

#: 任务 4 用过的两个受害 binding：一个在第一代上反读判据抓得到（34 处 `inline_text`），
#: 一个抓不到、只有字节判据抓得到（49 处 = 28 `inline_text` + 21 `number_literal`）。
NAIVE_VICTIMS = ("d4_10_rows", "d4_32_groups")


@pytest.fixture(scope="module")
def naive_runs(steady: SteadyState) -> dict[str, tuple[Path, GateRun]]:
    """在 **steady state** 上按 design 五 P5 的字面做法变异：漏写某个 binding 的全部写入。"""
    out: dict[str, tuple[Path, GateRun]] = {}
    for victim in NAIVE_VICTIMS:
        with drop_binding_writes(victim):
            artifact = steady.world.materialize(f"naive-dropped-{victim}.xlsx")
        out[victim] = (
            artifact,
            run_gates(
                world=steady.world,
                before=steady.world.base,
                after=artifact,
                projection=steady.world.projection,
                label=f"naive-dropped-{victim}",
            ),
        )
    return out


@pytest.mark.parametrize("victim", NAIVE_VICTIMS)
def test_the_naive_dropped_binding_mutation_produces_a_byte_identical_artifact(
    steady: SteadyState, naive_runs: dict[str, tuple[Path, GateRun]], victim: str
) -> None:
    """**Validates: Requirements 2.3**　（design 五 P5 反证方式的**精度修正**，非放宽）

    🔴 本文件最重要的一条「否证」：在 steady state 上漏写一个 binding 的**全部**写入，产物
    与正确产物**逐 zip entry 内容全同**（142/142，字节数相同）。三道门全绿 —— 而这**不是**
    盲区：产物根本没有缺陷。

    原因是不动点：steady-state substrate 上每处写入都是把**已经在那儿、形态也一样**的值再
    写一遍（恒等覆盖）⇒ 不写 == 写。附录 B.4 在**第一代** substrate 上测到的是另一半：那里
    漏写会改变单元格的表示形态（inline string vs shared string / 数字格式），所以字节判据
    （任务 4）抓得到、反读判据抓不到。两者合起来给出结论：

        「漏写一个 binding」是**计划层**的省略，在自反读 projection 上**不产生**缺陷产物；
        P5 要的「产物少一个字段」必须是**产物层**的缺陷（§二 的四个变异）。

    ⇒ design 五 P5 的「反证方式」一栏需要写清这一点（附录 G）。**判据没有放宽**：§二 那四条
    比原措辞更严（它们要求点名缺的那个 key / 那个 aspect / 那个 sheet）。
    """
    artifact, run = naive_runs[victim]
    comparison = compare_zip_entries(steady.artifact, artifact)
    assert comparison.namelist_equal and not comparison.name_differences, (
        f"漏写 {victim} 改变了 zip 条目集合：{comparison.name_differences}"
    )
    assert comparison.content_differences == (), (
        f"漏写 {victim} 在 steady state 上居然改变了产物字节 —— 这是**好事**（说明存在可检测"
        "的缺陷），但说明不动点前提变了：请把本条与 design 附录 G 的叙述一起更新，"
        f"别让「计划层省略在 steady state 上不可检测」这个结论挂在一个已不成立的实测上。\n"
        f"差异条目：{comparison.content_differences}"
    )
    assert comparison.byte_sizes[0] == comparison.byte_sizes[1]
    assert run.red_gates == (), (
        f"漏写 {victim} 后有门变红了：{run.red_gates}（产物与正确产物逐字节相同，"
        "任何门在这里变红都意味着门的结论依赖了字节之外的东西）"
    )
    assert len(run.extract_keys) == EXTRACTED_FIELD_COUNT
    assert run.reread_differences == ()


def test_the_naive_mutation_really_fired(
    steady: SteadyState, naive_runs: dict[str, tuple[Path, GateRun]]
) -> None:
    """**Validates: Requirements 2.3**

    上一条的结论（「漏写之后产物逐字节相同」）只有在**漏写真的发生了**的前提下才有意义。
    `drop_binding_writes` 自带两条前提断言（受害 binding 本来有写入 / 它真的被计划到过，
    否则抛），本条把「那两条断言确实会在本 world 上被触发」显式化：受害 binding 在
    steady-state 计划里各有多少处写入，实测必须 > 0。
    """
    by_key = steady.plan_write_counts
    assert len(by_key) == BINDING_COUNT, (
        f"steady-state 计划里只有 {len(by_key)} 个 binding（应 {BINDING_COUNT}）"
    )
    for victim in NAIVE_VICTIMS:
        assert victim in by_key, (
            f"受害 binding {victim} 不在 steady-state 计划里（实有 {sorted(by_key)[:5]}…）"
            " ⇒ 上一条是空转"
        )
        assert by_key[victim] > 0, f"{victim} 在 steady state 上一处写入都没有 ⇒ 变异空转"


# ═══════════════════════════════════════════════════════════════════════════
# 四、比较面被钉住：解析复用**没有**削掉任何一寸判据面
#
# 任务 8 已断「开/关复用**结论**相同」。本节往前一步断**面**：比了哪些 key、看了哪些
# aspect、每个 aspect 覆盖多少项、观测了多少条结构坐标。理由是「结论相同」对**削面**这类
# 改动天生免疫 —— 面窄了，两侧会一起变绿，差分看不出来。
# ═══════════════════════════════════════════════════════════════════════════


def test_the_roundtrip_surface_is_the_editable_field_set_measured_three_ways(
    steady: SteadyState, steady_gates: GateRun
) -> None:
    """**Validates: Requirements 2.3**

    G1 的比较面用**三条互不依赖**的路子各算一遍，三个数必须相等（实测 166）：

    1. G1 自己实际拿去比的值对数（拦 `content_mutation.values_equal` 记下来的）；
    2. intended projection 里 `mode=editable` 的字段数（按 `FieldValue.mode` 数，不复述
       门的排除逻辑）；
    3. G2（`excel_extract.verify_roundtrip_equivalence`）报出来的 `compared_keys` 数
       —— 它是**另一份实现**的「editable 面」。

    一个门的面被静默削窄，三条就不再相等 ⇒ 红。只断「166」这一个常数的话，三处一起改的
    重构照样绿；只断「两侧相同」的话，两侧一起削窄照样绿。

    同时断分工：被排除的 52 个字段**全部**是 `PROTECTED_MODES` 里的 mode（实测全为
    `formula`），它们归 G3 管 —— 排除是有意的，不是漏掉。
    """
    intended = steady.world.projection
    editable = {
        key for key, value in intended.values.items() if value.mode is FieldMode.editable
    }
    protected = {
        key for key, value in intended.values.items() if value.mode in PROTECTED_MODES
    }
    with workbook_read_scope():
        extracted = steady.world.adapter.extract(
            artifact=steady.artifact, contract=steady.world.contract
        )
        g2 = verify_roundtrip_equivalence(
            expected=intended, extracted=extracted, contract=steady.world.contract
        )
    assert len(steady_gates.g1_pairs) == ROUNDTRIP_COMPARED_KEYS, (
        f"G1 实际比了 {len(steady_gates.g1_pairs)} 对值（实测应 {ROUNDTRIP_COMPARED_KEYS}）"
        " ⇒ 生产发布门的比较面变了"
    )
    assert len(editable) == ROUNDTRIP_COMPARED_KEYS, (
        f"intended 里 editable 字段 {len(editable)} 个 ≠ G1 的比较面 "
        f"{ROUNDTRIP_COMPARED_KEYS} —— 门要么少比了、要么多比了"
    )
    assert len(g2.compared_keys) == ROUNDTRIP_COMPARED_KEYS, (
        f"G2 的 compared_keys {len(g2.compared_keys)} ≠ {ROUNDTRIP_COMPARED_KEYS} ⇒ "
        "两份「editable 面」实现漂了"
    )
    assert set(g2.compared_keys) == editable, (
        "G2 的比较面与「mode=editable」这个事实不一致，差集："
        f"{sorted(set(g2.compared_keys) ^ editable)[:5]}"
    )
    assert len(protected) == PROTECTED_FIELD_COUNT, (
        f"被两条反读门排除的受保护字段 {len(protected)} 个（实测应 {PROTECTED_FIELD_COUNT}）"
    )
    assert editable | protected == set(intended.values), (
        "intended 里出现了既非 editable 也非受保护的 mode ⇒ 它落在**任何门之外**，"
        f"请核对：{sorted(set(intended.values) - editable - protected)[:5]}"
    )
    assert len(intended.values) == EXTRACTED_FIELD_COUNT


def test_the_unmanaged_aspect_list_is_pinned_and_still_has_its_catch_all() -> None:
    """**Validates: Requirements 2.3**

    G4 的面由 `UNMANAGED_ASPECTS` 定义。把它**逐项**钉住（不是只钉个数）：删掉一个 aspect
    就是把一整类部件从判据里拿掉，而报告仍会给出 `equivalent=True`。

    最后一项 `other_parts` 是 **catch-all**（该常量自己的注释也这么写）：没有它，新出现的
    部件类别会悄悄不被任何 aspect 覆盖 —— 那正是「只检查了列出来的东西」这类假绿的入口。
    """
    assert UNMANAGED_ASPECTS == (
        "managed_sheet_unmanaged_cells",
        "managed_sheet_structure",
        "other_sheet_parts",
        "protected_parts",
        "shared_strings_prefix",
        "workbook_and_styles",
        "relationships",
        "other_parts",
    ), f"未管理区域的 aspect 清单变了：{UNMANAGED_ASPECTS}"
    assert UNMANAGED_ASPECTS[-1] == "other_parts", (
        "catch-all aspect 不再是最后一项 —— 新部件类别可能落在所有 aspect 之外"
    )


def test_the_unmanaged_comparison_loop_skips_no_aspect() -> None:
    """**Validates: Requirements 2.3**

    🔴 实测发现的一个判据缺口，本条补上：`UnmanagedRegionReport.inspected_aspects` 是
    **硬编码**成 `UNMANAGED_ASPECTS` 的（`verify_unmanaged_regions` 两个 return 都这么填），
    所以报告**说不出**「这次其实跳过了某个 aspect」。有人在比对循环里加一句
    `if aspect == "other_sheet_parts": continue`，报告照样声称检查了全部 8 项、结论照样
    `equivalent=True` —— 覆盖面判据（上一条记的是 digest 的**采集**面）也看不见它。

    因此这里按 **AST** 钉住比对循环的形态：遍历 `UNMANAGED_ASPECTS` 的那个 `for` 里
    * 只有一条语句，且是 `if`；
    * `if` 的判据是 `base.aspects[aspect] != target.aspects[aspect]`（两侧同一个下标）；
    * 循环体内没有 `continue` / `break` —— 任一出现即意味着某些 aspect 会被跳过。

    检查器自带反证：一份人为写了 `continue` 的源码必须被它报出来（见下面的自检）。
    """

    def offending_aspects(source: str) -> list[str]:
        tree = ast.parse(source.lstrip())
        loops = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.For)
            and isinstance(node.iter, ast.Name)
            and node.iter.id == "UNMANAGED_ASPECTS"
        ]
        problems: list[str] = []
        if len(loops) != 1:
            return [f"遍历 UNMANAGED_ASPECTS 的循环有 {len(loops)} 个（应恰 1 个）"]
        loop = loops[0]
        if any(isinstance(node, (ast.Continue, ast.Break)) for node in ast.walk(loop)):
            problems.append("比对循环里出现 continue/break ⇒ 有 aspect 会被跳过")
        if len(loop.body) != 1 or not isinstance(loop.body[0], ast.If):
            problems.append(
                f"循环体不是「单条 if」（实得 {[type(n).__name__ for n in loop.body]}）"
            )
            return problems
        branch = loop.body[0]
        if branch.orelse:
            problems.append("比对 if 带了 else 分支 ⇒ 形态变了，本判法需重写")
        test = branch.test
        if not (
            isinstance(test, ast.Compare)
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.NotEq)
            and all(
                isinstance(side, ast.Subscript)
                and isinstance(side.slice, ast.Name)
                and side.slice.id == loop.target.id  # type: ignore[union-attr]
                for side in (test.left, test.comparators[0])
            )
        ):
            problems.append("比对判据不再是「两侧按同一个 aspect 下标取值后不等」")
        return problems

    assert offending_aspects(inspect.getsource(EE.verify_unmanaged_regions)) == [], (
        "未管理区域的比对循环形态被改了 —— 它可能在静默跳过某些 aspect，而报告仍会声称"
        f"检查了全部 {len(UNMANAGED_ASPECTS)} 项：\n"
        + "\n".join(offending_aspects(inspect.getsource(EE.verify_unmanaged_regions)))
    )
    # 检查器自身的反证：跳过一个 aspect 的源码必须被报出来（否则本条是空转）。
    weakened = (
        "def gate(base, target):\n"
        "    for aspect in UNMANAGED_ASPECTS:\n"
        "        if aspect == 'other_sheet_parts':\n"
        "            continue\n"
        "        if base.aspects[aspect] != target.aspects[aspect]:\n"
        "            return False\n"
        "    return True\n"
    )
    assert offending_aspects(weakened), "检查器放过了一份明确跳过 aspect 的源码"


def test_parse_reuse_changes_no_comparison_surface(
    steady_gates: GateRun, steady_gates_without_reuse: GateRun
) -> None:
    """**Validates: Requirements 2.3**　**Property: P5**

    同一份产物、同样三道门，开复用与关复用（`reuse_disabled()`）两侧的**比较面**逐项相同：

    * G1：实际比过的值对**多重集**（含 `value_type` 与两侧 `repr`）全同；
    * G4：39 binding × (before + after) 共 78 次 digest 的 **aspect 名单 + 每 aspect 覆盖
      项数 + part 数**全同（刻意不比 digest 值 —— 那是结论，任务 8 已经比过）；
    * G5：775 条受管结构坐标全同（含转置 sheet 的字段格存在性，它对共享对象最敏感）。

    这是任务 8 那条「结论相同」的**加强**：面窄了两侧会一起变绿，差分看不出来；面的逐项
    对账看得出来。
    """
    assert steady_gates.extract_keys == steady_gates_without_reuse.extract_keys, (
        "两侧反读出来的 key 集合不同 ⇒ 复用改了 extract 的面"
    )
    assert steady_gates.g1_pairs == steady_gates_without_reuse.g1_pairs, (
        "两侧 G1 的比较面不同（值对多重集）⇒ 复用改了反读等值门比的东西；差集："
        f"{sorted(set(steady_gates.g1_pairs) ^ set(steady_gates_without_reuse.g1_pairs))[:5]}"
    )
    assert len(steady_gates.g1_pairs) == ROUNDTRIP_COMPARED_KEYS
    assert len(steady_gates.g4_surface) == UNMANAGED_DIGEST_CALLS, (
        f"G4 的 digest 调用 {len(steady_gates.g4_surface)} 次 ≠ "
        f"{UNMANAGED_DIGEST_CALLS}（{BINDING_COUNT} binding × before/after）⇒ "
        "要么有 binding 没被比，要么 before 侧被缓存吃掉了（本文件每次跑前清缓存）"
    )
    assert steady_gates.g4_surface == steady_gates_without_reuse.g4_surface, (
        "两侧 G4 的覆盖面不同 ⇒ 复用削了未管理区域的比对范围；首个不同："
        + next(
            (
                f"{a} != {b}"
                for a, b in zip(steady_gates.g4_surface, steady_gates_without_reuse.g4_surface)
                if a != b
            ),
            "(长度不同)",
        )
    )
    assert all(aspects == tuple(sorted(UNMANAGED_ASPECTS)) for _p, aspects, _c, _n in steady_gates.g4_surface), (
        "有 digest 的 aspect 名单不是全量 UNMANAGED_ASPECTS ⇒ 某次比对少看了一类部件"
    )
    assert all(
        all(count > 0 for _name, count in coverage) for _p, _a, coverage, _n in steady_gates.g4_surface
    ), (
        "有 aspect 的覆盖项数为 0 ⇒ 那一类部件这次**什么都没比**（面是空的，结论必然绿）："
        + str([c for _p, _a, c, _n in steady_gates.g4_surface if any(v == 0 for _k, v in c)][:1])
    )
    assert len(steady_gates.g5_structure) == STRUCTURE_COORDINATE_COUNT, (
        f"G5 观测到 {len(steady_gates.g5_structure)} 条受管结构坐标"
        f"（实测应 {STRUCTURE_COORDINATE_COUNT}）⇒ 结构身份的面变了"
    )
    assert steady_gates.g5_structure == steady_gates_without_reuse.g5_structure, (
        "两侧 G5 的结构坐标集合不同 ⇒ 共享的完整 DOM 被就地改过（`ws._cells` 惰性新建污染"
        "是最可能的原因），发布时刻的结构身份因此漂了"
    )
    assert steady_gates.g5_hash == steady_gates_without_reuse.g5_hash


def test_the_reuse_off_side_really_disabled_sharing(
    steady_gates_without_reuse: GateRun,
) -> None:
    """**Validates: Requirements 2.3**

    上一条的对照侧必须**真的**关掉了复用，否则两侧跑的是同一条路径、「面相同」永远绿。
    `reuse_disabled()` 的非空转在任务 8 已由解析计数实测（8 个消费方各解析一遍、整段
    `load_workbook` 回到 19）。本条只断本文件这一侧确实跑完了整套门（结论齐全、面非空），
    不重造那边的计数判据。
    """
    assert steady_gates_without_reuse.extract_ok
    assert len(steady_gates_without_reuse.g4_verdicts) == BINDING_COUNT
    assert steady_gates_without_reuse.red_gates == ()
    assert steady_gates_without_reuse.g1_pairs and steady_gates_without_reuse.g5_structure


# ═══════════════════════════════════════════════════════════════════════════
# 五、复用的是**解析**，不是**结论**（需求 2.3 的字面命题）
#
# 本节抓的是一种具体的写法：有人图快把 verify 的**判决**记忆化（「这个 scope / 这个契约 /
# 这个路径已经验过了」）。那样一来第二次调用会拿到上一次的绿，而产物已经换了。
# ═══════════════════════════════════════════════════════════════════════════


def test_the_roundtrip_verdict_is_recomputed_for_every_artifact_in_one_scope(
    steady: SteadyState, mutated: dict[str, Path]
) -> None:
    """**Validates: Requirements 2.3**

    在**同一个** `workbook_read_scope()` 里按「好 → 坏 → 好」三次跑 extract + G1，结论必须
    逐次跟着产物翻：绿 → 红 → 绿。

    * 第二次是红：说明结论没有被「这个 scope 已经验过了」之类的记忆化吃掉；
    * 第三次回绿：说明红也没有被粘住（粘住的话它就不是「每次重算」，而是另一种缓存缺陷）。

    刻意共用一个作用域 —— 分开作用域的话，任何 scope 级缓存都会自然失效，这条判据就测不到
    它要测的东西。
    """
    sequence: list[tuple[str, bool, int]] = []
    clear_all_parse_caches()
    clear_structure_fingerprint_cache()
    with workbook_read_scope():
        for label, artifact in (
            ("good", steady.artifact),
            ("field_removed", mutated["managed_editable"]),
            ("good_again", steady.artifact),
        ):
            extracted = steady.world.adapter.extract(
                artifact=artifact, contract=steady.world.contract
            )
            try:
                ContentMutationService._assert_roundtrip_equivalent(  # noqa: SLF001
                    None,  # type: ignore[arg-type]
                    intended=steady.world.projection,
                    extracted=extracted,
                    contract=steady.world.contract,
                )
                red = False
            except RoundtripEquivalenceError:
                red = True
            sequence.append((label, red, len(extracted.values)))
    assert sequence == [
        ("good", False, EXTRACTED_FIELD_COUNT),
        ("field_removed", True, EXTRACTED_FIELD_COUNT - 1),
        ("good_again", False, EXTRACTED_FIELD_COUNT),
    ], (
        "同一个作用域内 G1 的结论没有跟着产物翻 —— 反读**结论**被缓存了（需求 2.3 明令"
        f"「复用解析结果不等于复用结论」）：{sequence}"
    )


def test_the_unmanaged_verdict_is_recomputed_for_every_artifact_in_one_scope(
    steady: SteadyState, mutated: dict[str, Path]
) -> None:
    """**Validates: Requirements 2.3**

    同一条纪律加在 G4 上：同一个作用域、同一个 `before`、after 换成变异产物 ⇒ 39 条结论
    必须从「0 漂移」翻成「39 漂移」，再换回好产物必须回到 0。

    G4 里确实有一层缓存（`BEFORE_DIGEST_CACHE`），但它缓存的是 **before 侧的 digest**
    （不变量），不是**结论**；after 侧每次重算。下一条判据把这件事按键的构造钉住。
    """
    drifted: list[tuple[str, int, int]] = []
    clear_all_parse_caches()
    clear_structure_fingerprint_cache()
    with workbook_read_scope():
        for label, artifact in (
            ("good", steady.artifact),
            ("unmanaged_removed", mutated["unmanaged_cell"]),
            ("good_again", steady.artifact),
        ):
            verdicts: list[bool] = []
            with unmanaged_verdict_collector(verdicts):
                steady.world.adapter.verify_unmanaged_regions(
                    before=steady.world.base,
                    after=artifact,
                    contract=steady.world.contract,
                    row_shift=None,
                    total_formula_rows=(),
                    propagation=None,
                    per_table_shift=None,
                )
            drifted.append((label, sum(1 for v in verdicts if not v), len(verdicts)))
    assert drifted == [
        ("good", 0, BINDING_COUNT),
        ("unmanaged_removed", BINDING_COUNT, BINDING_COUNT),
        ("good_again", 0, BINDING_COUNT),
    ], (
        "同一个作用域内 G4 的结论没有跟着 after 翻 —— 未管理区域的**结论**被缓存了："
        f"{drifted}"
    )


def test_the_before_side_digest_cache_is_content_addressed_not_path_addressed(
    steady: SteadyState, mutated: dict[str, Path]
) -> None:
    """**Validates: Requirements 2.3**

    G4 的 before 侧 LRU 若按**路径**做键，就会出现「同一个 substrate 路径换了内容仍命中旧
    digest」⇒ 一份被改过的 substrate 会被拿旧 digest 去比，门静默失效。

    两面都断：
    * **结构**：`verify_unmanaged_regions` 的缓存键表达式里含 `before_sha`（AST 层面确认
      它真的进了键，而不是只在注释里写了「内容寻址」）；
    * **后果**：同一个路径先放好字节、再放坏字节，两次结论必须不同（0 漂移 → 39 漂移）。
      单有结构那一半也可能是「键里有它但被别的层吃掉了」。
    """
    tree = ast.parse(inspect.getsource(EE.verify_unmanaged_regions).lstrip())
    key_assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "before_key"
            for target in node.targets
        )
    ]
    assert key_assignments, "`verify_unmanaged_regions` 里找不到 before 侧缓存键的构造"
    key_names = {
        node.id for node in ast.walk(key_assignments[0]) if isinstance(node, ast.Name)
    }
    assert "before_sha" in key_names, (
        f"before 侧缓存键不含 `before_sha`（键里只有 {sorted(key_names)}）⇒ 它按路径/身份"
        "做键，换内容会误命中"
    )

    probe = steady.artifact.with_name("same-path-before.xlsx")
    drifted: list[tuple[str, int]] = []
    clear_all_parse_caches()
    try:
        with workbook_read_scope():
            for label, source in (
                ("before=good", steady.artifact),
                ("before=unmanaged_removed", mutated["unmanaged_cell"]),
            ):
                probe.write_bytes(source.read_bytes())
                verdicts: list[bool] = []
                with unmanaged_verdict_collector(verdicts):
                    steady.world.adapter.verify_unmanaged_regions(
                        before=probe,
                        after=steady.artifact,
                        contract=steady.world.contract,
                        row_shift=None,
                        total_formula_rows=(),
                        propagation=None,
                        per_table_shift=None,
                    )
                drifted.append((label, sum(1 for v in verdicts if not v)))
            EE.release_scoped_workbooks(probe)
    finally:
        probe.unlink(missing_ok=True)
    assert drifted == [("before=good", 0), ("before=unmanaged_removed", BINDING_COUNT)], (
        "同一个 before 路径换了内容之后结论没变 ⇒ before 侧 digest 被按路径缓存了，"
        f"一份被改过的 substrate 会被拿旧 digest 去比：{drifted}"
    )


def test_no_verify_gate_memoises_its_verdict() -> None:
    """**Validates: Requirements 2.3**

    「复用解析 ≠ 复用结论」的**结构**一半：三道门（以及 G2/G3）都不得被 `functools` 的
    记忆化包起来 —— 那是最省事、也最静默的「缓存结论」写法。

    判法不看名字看**对象**：`functools.lru_cache` / `cache` 包出来的函数带
    `cache_info` / `cache_clear` 属性，且 `__wrapped__` 指向原函数。顺带断它们不是
    `functools.partial` 之类的替身（那种替身可以在别处偷偷加缓存）。
    """
    gates: dict[str, Any] = {
        "G1": ContentMutationService._assert_roundtrip_equivalent,
        "G2": verify_roundtrip_equivalence,
        "G3": EE.verify_formula_regions,
        "G4": EE.verify_unmanaged_regions,
        "G4.assert": UnmanagedRegionReport.assert_equivalent,
        "G5": compute_structure_hash_from_artifact,
    }
    for name, gate in gates.items():
        assert not hasattr(gate, "cache_info"), (
            f"{name} 被 functools 记忆化了（有 cache_info）⇒ 它会复用**结论**"
        )
        assert not hasattr(gate, "cache_clear"), f"{name} 带 cache_clear ⇒ 结论被缓存"
        assert not isinstance(gate, functools.partial), (
            f"{name} 是 functools.partial 替身 —— 真实实现可能在别处加了缓存"
        )
        assert inspect.isfunction(gate) or inspect.ismethod(gate), (
            f"{name} 不是普通函数/方法（实得 {type(gate)!r}）⇒ 形态变了，本条的判法要重写"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 六、变异器自身可反证（毫秒级，不碰真库）
#
# §二 的四条全靠 `drop_cell_from_xml` 打得准。它要是静默变成 no-op，那四条会变成「好产物
# 上门也红」—— 不，会变成「门是绿的」而结论被读成「门失守」。所以变异器本身要有判据。
# ═══════════════════════════════════════════════════════════════════════════


def _one_sheet_xml(coords: tuple[str, ...]) -> bytes:
    cells = "".join(f'<c r="{coord}"><v>{index}</v></c>' for index, coord in enumerate(coords))
    return (
        '<?xml version="1.0"?><worksheet><sheetData><row r="1">'
        f"{cells}</row></sheetData></worksheet>"
    ).encode("utf-8")


@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    victim_index=st.integers(min_value=0, max_value=3),
    extra=st.integers(min_value=0, max_value=3),
)
def test_the_cell_mutation_removes_exactly_the_targeted_cell(
    victim_index: int, extra: int
) -> None:
    """**Validates: Requirements 2.3**　（变异器的非空转与定点性）

    命题：`drop_cell_from_xml(xml, coord)` 恰好抹掉 `coord` 那一个 `<c>`，其余**逐字节**
    不动。property 形态而不是单例：靶点落在第一个 / 中间 / 最后一个格子上都得成立，否则
    §二 里「抹掉的是不是我指的那个」就只在某个位置上被验过。

    同时断两条边界：坐标不存在时**必须抛**（不能静默返回原字节 —— 那正是变异空转的形态），
    坐标是别的坐标的前缀时（`A1` vs `A12`）不得误伤。
    """
    coords = tuple(f"A{i + 1}" for i in range(4 + extra))
    xml = _one_sheet_xml(coords)
    victim = coords[min(victim_index, len(coords) - 1)]
    mutated = drop_cell_from_xml(xml, victim)
    assert f'<c r="{victim}">'.encode() not in mutated, f"{victim} 没被抹掉"
    for coord in coords:
        if coord == victim:
            continue
        assert f'<c r="{coord}">'.encode() in mutated, (
            f"抹 {victim} 顺手把 {coord} 也抹了 ⇒ 变异不定点，§二 的归因不可信"
        )
    # 其余字节逐字不动：把被抹掉那段补回去必须还原成原文。
    removed = re.search(
        ('<c r="' + re.escape(victim) + '">.*?</c>').encode(), xml, re.S
    )
    assert removed is not None
    assert mutated == xml[: removed.start()] + xml[removed.end() :], (
        "变异除了删那一格还改了别处字节"
    )
    with pytest.raises(AssertionError, match="空转"):
        drop_cell_from_xml(xml, "ZZ999")


def test_the_cell_mutation_does_not_confuse_prefix_coordinates() -> None:
    """**Validates: Requirements 2.3**

    `A1` 是 `A12` 的前缀。正则若写成 `<c r="A1"`（不带收尾引号）就会误伤 `A12` —— 那种误伤
    会让 §二 的「恰好红在这一处」变成「红在两处」，归因当场失效。这里正面钉住引号边界。
    """
    xml = _one_sheet_xml(("A1", "A12", "A123"))
    mutated = drop_cell_from_xml(xml, "A1")
    assert b'<c r="A1">' not in mutated
    assert b'<c r="A12">' in mutated and b'<c r="A123">' in mutated


def test_the_artifact_mutation_rewrites_only_the_targeted_part(tmp_path: Path) -> None:
    """**Validates: Requirements 2.3**

    `mutate_artifact` 只许改指定 part：别的 entry 必须**逐字节**原样过去（否则 §二 里
    「G4 首个差异面是 other_sheet_parts」这类归因就可能是重打包造成的，而不是变异造成的）。
    同时断 part 不存在时必须抛（空转守卫）。
    """
    src = tmp_path / "src.xlsx"
    with zipfile.ZipFile(src, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", _one_sheet_xml(("A1", "B1")))
        archive.writestr("xl/styles.xml", b"<styleSheet/>")
    dst = mutate_artifact(
        src,
        tmp_path / "dst.xlsx",
        part="xl/worksheets/sheet1.xml",
        transform=lambda data: drop_cell_from_xml(data, "A1"),
    )
    comparison = compare_zip_entries(src, dst)
    assert comparison.namelist_equal and not comparison.name_differences
    assert comparison.content_differences == ("xl/worksheets/sheet1.xml",), (
        f"变异改动了别的 part：{comparison.content_differences}"
    )
    with pytest.raises(AssertionError, match="空转"):
        mutate_artifact(
            src, tmp_path / "miss.xlsx", part="xl/no-such-part.xml", transform=lambda d: d
        )


def test_the_gate_runner_reports_every_gate_independently(tmp_path: Path) -> None:
    """**Validates: Requirements 2.3**

    §二 的归因表建立在「一个门抛了，另外两个门仍然跑完」之上。`GateRun.red_gates` 的分流
    逻辑因此不能靠运气：这里用纯数据构造三种形态各断一遍（门抛 / 门给出不等价结论 / 全绿），
    确保「G4 绿」不会是「G4 压根没跑」的同义词。
    """
    assert GateRun(label="x", extract_ok=True, g4_verdicts=(True,) * 39).red_gates == ()
    assert GateRun(
        label="x", extract_ok=True, g4_verdicts=(True, False)
    ).red_gates == ("G4",)
    assert GateRun(label="x", extract_ok=True, g4_raised="boom").red_gates == ("G4",)
    assert GateRun(
        label="x", extract_ok=True, g1_red=True, g4_verdicts=(True,), g5_red=True
    ).red_gates == ("G1", "G5")
    # 一条结论都没收集到时不得被读成「绿」—— `all(())` 是 True，这里正面钉住它会被算红。
    assert GateRun(label="x", extract_ok=True, g4_verdicts=()).g4_red, (
        "G4 一条结论都没有时被判成绿 ⇒ 「循环没跑」与「全绿」不可区分"
    )
