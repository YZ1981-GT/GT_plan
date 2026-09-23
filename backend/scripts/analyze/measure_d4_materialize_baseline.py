"""真库 D4 entry 单次物化的计时 / 内存 / 调用计数证据。

spec: oo-single-pass-materialize-and-room-leave · Requirement 1.1 / 1.5

用法（仓库根）：

    .venv\\Scripts\\python.exe backend/scripts/analyze/measure_d4_materialize_baseline.py
    .venv\\Scripts\\python.exe backend/scripts/analyze/measure_d4_materialize_baseline.py \\
        --mode default --label after-single-pass

证据落 `docs/operations/evidence/oo-single-pass-materialize/<label>.json`。任务 7 的
「前后对照」就是把本脚本在改动前后各跑一次 —— 因此它是**常驻工具**（无 `_` 前缀），
且与基线测试共用 `tests/workpaper_sync/d4_materialize_harness.py` 那一份 world：
两边各拼一份 binding 列表就不是同一个 39 了。

`--mode`：
* `chained`  —— 显式摘掉单趟入口，量**逐 binding 链式**路径（改动前基线）；
* `default`  —— 量当前默认路径（单趟化落地后用它记「后」）；
* `both`     —— 仅 `--segment` 模式可用：同一轮里两条路径**交错**各跑一次。

任务 7 的 like-for-like 前后对照（`--segment`，见本文件下半部分）：

    .venv\\Scripts\\python.exe backend/scripts/analyze/measure_d4_materialize_baseline.py \\
        --segment --mode both --repeat 3 --label task7-segment-before-after

`--segment` 与上面的单段模式差三件事，三件都是为了让证据能回答需求 1.5：

1. 量的不是 `adapter.materialize` 一段，而是生产 CPU 段
   （`ContentMutationService._stage_cpu_segment_scoped`）的**五步逐段计时** ——
   requirements 1.5 的「~30s」是用户在真实切 OO 时观测的 materialize + extract + verify
   合计，拿单段的数字去比它是**换了口径**；
2. `--repeat N` 多轮，证据里记 min/median/max —— 单样本墙钟在本路径上run-to-run 漂
   （同一 HEAD 上见过 16.7 / 19.8 / 20.3 / 22.2s），单样本不算证据；
3. 两条路径**交错**跑并在每轮前清结构指纹缓存，免得先跑的那条替后跑的那条付了钱。
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

DEFAULT_OUT_DIR = _REPO / "docs" / "operations" / "evidence" / "oo-single-pass-materialize"


def _peak_rss_bytes() -> int | None:
    """进程 RSS 峰值（拿不到就 None —— 证据里如实留空，不编数）。"""
    try:
        import psutil
    except ImportError:  # pragma: no cover - 环境缺 psutil
        return None
    info = psutil.Process().memory_info()
    return int(getattr(info, "peak_wset", None) or info.rss)


class _LogCollector:
    """把某个 logger 的 INFO 记录收进列表（脚本里没有 caplog 可用）。"""

    def __init__(self, logger_name: str) -> None:
        self._logger_name = logger_name
        self._records: list[str] = []

    @contextlib.contextmanager
    def capturing(self) -> Any:
        import logging

        collector = self

        class _Handler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                collector._records.append(record.getMessage())

        logger = logging.getLogger(self._logger_name)
        handler = _Handler(level=logging.INFO)
        previous_level = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            yield
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

    def matching(self, needle: str) -> list[str]:
        seen = {message for message in self._records if needle in message}
        return sorted(seen)


def measure(mode: str, *, with_tracemalloc: bool = True) -> dict[str, Any]:
    """铺 world → 计时物化一次（干净墙钟）→ 可选再物化一次量内存峰值。"""
    from tests.workpaper_sync.d4_materialize_harness import (
        ENTRY_ID,
        MaterializeCallCounter,
        build_world,
        force_chained_path,
    )

    with tempfile.TemporaryDirectory(prefix="d4-materialize-evidence-") as raw:
        workdir = Path(raw)
        prepare_started = time.perf_counter()
        world = build_world(workdir)
        prepare_seconds = time.perf_counter() - prepare_started

        def gate() -> Any:
            return force_chained_path() if mode == "chained" else contextlib.nullcontext()

        # 抓 `[single_pass] …` 日志：default 模式下「为什么还是 39 趟」只能从它看出来，
        # 只写墙钟的证据会让读者以为单趟已经生效。
        notes = _LogCollector("app.services.workpaper_sync.adapters.excel")

        # ═══ 第一趟：计时 + 计数，**不开** tracemalloc ═══
        # tracemalloc 对这条路径的开销是数量级的（实测 69s vs 26s）。墙钟证据要拿来和
        # 「≤10s」比，掺了 profiler 开销的数字既高估现状、又会在改动后高估提速。
        counter = MaterializeCallCounter()
        rss_before = _peak_rss_bytes()
        started = time.perf_counter()
        with gate(), counter.installed(), notes.capturing():
            output = world.materialize("baseline.xlsx")
        elapsed = time.perf_counter() - started
        rss_after = _peak_rss_bytes()
        artifact = output.read_bytes()

        # ═══ 第二趟：只量内存峰值（墙钟作废，不进 timing）═══
        traced_peak: int | None = None
        if with_tracemalloc:
            tracemalloc.start()
            try:
                with gate():
                    world.materialize("baseline-tracemalloc.xlsx")
                _, peak = tracemalloc.get_traced_memory()
                traced_peak = int(peak)
            finally:
                tracemalloc.stop()
        # 🔴 尺寸必须在临时目录**还在**的时候取：`with` 一出去 substrate 就没了。
        substrate_bytes = world.base.stat().st_size
        binding_count = world.binding_count
        field_count = len(world.projection.values)

    return {
        "label": None,  # 由 main 填
        "captured_at": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "spec": "oo-single-pass-materialize-and-room-leave",
        "requirements": ["1.1", "1.5"],
        "scope": {
            "entry_id": ENTRY_ID,
            "path_mode": mode,
            "binding_count": binding_count,
            "substrate_bytes": substrate_bytes,
            "projection_field_count": field_count,
        },
        "timing": {
            "materialize_wall_seconds": round(elapsed, 3),
            "harness_prepare_seconds": round(prepare_seconds, 3),
            "measured_without_tracemalloc": True,
        },
        "memory": {
            # tracemalloc 只统计 Python 堆分配；openpyxl 的 zip/lxml 侧不在里面 ⇒ 两个
            # 指标都留，谁也不能单独代表「内存峰值」。
            "tracemalloc_peak_bytes": traced_peak,
            "tracemalloc_peak_mib": (
                round(traced_peak / 1024 / 1024, 1) if traced_peak else None
            ),
            "process_peak_rss_bytes": rss_after,
            "process_peak_rss_mib": (
                round(rss_after / 1024 / 1024, 1) if rss_after else None
            ),
            "process_peak_rss_before_bytes": rss_before,
            "process_peak_rss_note": (
                "peak_wset 是进程生命周期峰值，含 harness 铺 world（instrument 真模板）"
            ),
        },
        "calls": dict(counter.as_dict()),
        "single_pass_log": notes.matching("[single_pass]"),
        "artifact": {
            "bytes": len(artifact),
            "sha256": hashlib.sha256(artifact).hexdigest(),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "openpyxl": __import__("openpyxl").__version__,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("chained", "default", "both"),
        default="chained",
        help=(
            "chained=显式走逐 binding 链式（改动前基线）；default=当前默认路径；"
            "both=交错各跑一次（仅 --segment）"
        ),
    )
    parser.add_argument(
        "--label",
        default=None,
        help="证据文件名（默认 baseline-chained / current-default）",
    )
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument(
        "--no-tracemalloc",
        action="store_true",
        help="跳过第二趟内存量测（只要墙钟时用；证据里内存字段留 null）",
    )
    parser.add_argument(
        "--segment",
        action="store_true",
        help=(
            "任务 7 模式：量生产 CPU 段五步（materialize/extract/roundtrip/unmanaged/"
            "structure_hash）逐段耗时，多轮取 min/median/max"
        ),
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=3,
        help="--segment 下每条路径跑几轮（默认 3；单样本不作为证据）",
    )
    args = parser.parse_args(argv)

    if args.segment:
        return _main_segment(args)
    if args.mode == "both":
        parser.error("--mode both 只在 --segment 模式下可用")

    label = args.label or (
        "baseline-chained" if args.mode == "chained" else "current-default"
    )
    evidence = measure(args.mode, with_tracemalloc=not args.no_tracemalloc)
    evidence["label"] = label

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{label}.json"
    target.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    calls = evidence["calls"]
    print(f"[evidence] {target}")
    print(
        f"  趟数 materialize_projection = {calls['materialize_trips']}"
        f"  load_workbook = {calls['load_workbook']}"
        f"  Workbook.save = {calls['workbook_save']}"
    )
    print(
        f"  墙钟 {evidence['timing']['materialize_wall_seconds']}s"
        f"  tracemalloc 峰值 {evidence['memory']['tracemalloc_peak_mib']}MiB"
        f"  进程 RSS 峰值 {evidence['memory']['process_peak_rss_mib']}MiB"
    )
    return 0


# ═════════════════════════════════════════════════════════════════════════════
# 任务 7：like-for-like 前后对照（生产 CPU 段五步 · 多轮 · 交错）
# ═════════════════════════════════════════════════════════════════════════════

#: 生产 CPU 段 `ContentMutationService._stage_cpu_segment_scoped` 的五步，按生产顺序。
#: 本节的分段计时是那一段的**复刻**（脚本里没有 session / plan / artifacts layout），
#: 所以必须带一条「复刻没跑偏」的自检：生产源码里少了任何一步、或多出一步没被计时，
#: 都得在证据里如实记，而不是假装量的就是全段。
_SEGMENT_STEPS: tuple[tuple[str, str], ...] = (
    ("materialize", "adapter.materialize("),
    ("extract", "adapter.extract("),
    ("roundtrip_verify", "self._assert_roundtrip_equivalent("),
    ("unmanaged_verify", "adapter.verify_unmanaged_regions("),
    ("structure_hash", "self._projection_structure_hash("),
)

#: CPU 段**之外**的成本 —— 它们不在本证据的 total 里，读者不该拿 total 当端到端。
_SEGMENT_EXCLUSIONS: tuple[str, ...] = (
    "stage_stream / publish_representation（内容寻址落库前的文件 IO，在 CPU 段之后）",
    "projection artifact 序列化与 publish_projection",
    "DB 单事务（`_commit_once`）与 outbox",
    "HTTP / OO 握手 / 前端加载态 —— 用户感知的 ~30s 里含这些",
    "复用判定（命中时整段压根不跑；本证据量的是复用**落空**那条路径）",
)


def _replica_fidelity() -> dict[str, Any]:
    """「脚本计时的步骤」与「生产 CPU 段真实调用的步骤」逐条对账。"""
    import inspect

    from app.services.workpaper_sync.content_mutation import ContentMutationService

    scoped = inspect.getsource(ContentMutationService._stage_cpu_segment_scoped)
    outer = inspect.getsource(ContentMutationService._stage_cpu_segment)
    roundtrip = inspect.getsource(ContentMutationService._assert_roundtrip_equivalent)
    # 脚本以 `self=None` 调它（生产里它不碰实例状态）。哪天它开始用 `self.`，这条会亮，
    # 而不是让脚本在 `NoneType` 上炸一个看不懂的 AttributeError。
    uses_self = "self." in roundtrip
    return {
        "production_function": "ContentMutationService._stage_cpu_segment_scoped",
        "timed_steps_found_in_production": [
            name for name, marker in _SEGMENT_STEPS if marker in scoped
        ],
        "timed_steps_missing_from_production": [
            name for name, marker in _SEGMENT_STEPS if marker not in scoped
        ],
        "production_wraps_one_workbook_read_scope": (
            "with workbook_read_scope():" in outer
        ),
        "roundtrip_verify_touches_instance_state": uses_self,
        "excluded_from_total": list(_SEGMENT_EXCLUSIONS),
    }


def _structure_anchors() -> Any:
    """发布时刻 structure_hash 的锚点 —— 与生产同一来源（instrumentation specs 派生）。

    生产从 DB 取冻结锚点（`load_frozen_structure_anchors`），但那份冻结值本身就是
    `anchors_from_instrumentation_specs(provider.instrumentation_specs())` 存进去的
    （`projection_first_publication`），所以脚本直接派生 = 同一口径、不需要 PG。
    """
    from app.services.workpaper_sync import phase5_d4_revenue_detail as D4
    from app.services.workpaper_sync.publish_time_structure_hash import (
        anchors_from_instrumentation_specs,
    )

    return anchors_from_instrumentation_specs(D4.instrumentation_specs())


@contextlib.contextmanager
def _collecting_unmanaged_verdicts(sink: list[bool]) -> Any:
    """把 `UnmanagedRegionReport.assert_equivalent` 暂换成**收集器**（只在 verify 段内）。

    🔴 为什么必须这么量：`ExcelSyncAdapter.verify_unmanaged_regions` 逐 binding 比对、
    **每个 binding 比完就 assert**。harness world 上第 1 个 binding 就报 unmanaged drift
    （见下），assert 直接抛 ⇒ 那一段的墙钟只含 39 分之一的比对量。把它当 verify 成本记进
    证据 = 把「后」这一侧记少，正好是本任务最不该犯的那种错。

    换成收集器让**生产那个循环**跑完全部 39 个 binding（生产里 verify 通过时也是跑完
    39 个），量到的才是完整比对成本；每个 report 的 `equivalent` 逐一收进证据，
    结论一个字都不藏（verify 的**结论**是任务 9 的命题，本任务只量成本）。
    """
    from app.services.workpaper_sync.adapters.base import UnmanagedRegionReport

    original = UnmanagedRegionReport.assert_equivalent

    def collecting(self: Any) -> None:
        sink.append(bool(self.equivalent))

    UnmanagedRegionReport.assert_equivalent = collecting  # type: ignore[method-assign]
    try:
        yield
    finally:
        UnmanagedRegionReport.assert_equivalent = original  # type: ignore[method-assign]


def measure_segment(
    world: Any, *, mode: str, output_name: str, substrate: Path | None = None
) -> dict[str, Any]:
    """跑一次生产形态的 CPU 段，五步逐段计时。

    `substrate` 默认用 world 的 base（= 刚 instrument 出来的模板）。传别的路径可以量
    **第二代** substrate（上一次物化的产物）—— 那才是生产的常态形态，见
    `measure_segment_runs` 里的 steady-state 探针。
    """
    from app.services.excel_structure_fingerprint import (
        clear_structure_fingerprint_cache,
    )
    from app.services.workpaper_sync.content_mutation import ContentMutationService
    from app.services.workpaper_sync.excel_extract import workbook_read_scope
    from app.services.workpaper_sync.publish_time_structure_hash import (
        compute_structure_hash_from_artifact,
    )
    from tests.workpaper_sync.d4_materialize_harness import (
        MaterializeCallCounter,
        force_chained_path,
    )

    base = substrate or world.base
    gate = force_chained_path() if mode == "chained" else contextlib.nullcontext()
    # 🔴 结构指纹缓存按**字节内容**记忆化，而 substrate 在各轮之间逐字节相同 ⇒ 不清的话
    # 第一轮付 `_structure_fingerprint_uncached`、后面几轮白捡。两条路径必须付同样的钱，
    # 否则「前后对照」就退化成「先后对照」。
    clear_structure_fingerprint_cache()

    counter = MaterializeCallCounter()
    anchors = _structure_anchors()
    output = world.staged(output_name)
    spans: dict[str, float] = {}
    unmanaged_verdicts: list[bool] = []
    started_all = time.perf_counter()
    # 一个 scope 包住五步 —— 与生产 `_stage_cpu_segment` 同形（它就是这么包的）。
    with gate, counter.installed(), workbook_read_scope():
        mark = time.perf_counter()
        materialized = world.adapter.materialize(
            substrate=base,
            projection=world.projection,
            output=output,
            contract=world.contract,
        )
        spans["materialize"] = time.perf_counter() - mark

        mark = time.perf_counter()
        extracted = world.adapter.extract(artifact=output, contract=world.contract)
        spans["extract"] = time.perf_counter() - mark

        mark = time.perf_counter()
        # 生产判据本体（`self` 未被消费，见 `_replica_fidelity` 的自检）—— 不重写第二套
        # 「反读等值」，那样量的就不是生产那一段了。
        ContentMutationService._assert_roundtrip_equivalent(  # noqa: SLF001
            None,  # type: ignore[arg-type]
            intended=world.projection,
            extracted=extracted,
            contract=world.contract,
        )
        spans["roundtrip_verify"] = time.perf_counter() - mark

        mark = time.perf_counter()
        # assert 换成收集器：让生产那个「逐 binding 比对」的循环跑完 39 个，量到完整成本。
        # 结论（每个 binding 等价与否）逐一进证据，不替谁遮掩。
        with _collecting_unmanaged_verdicts(unmanaged_verdicts):
            report = world.adapter.verify_unmanaged_regions(
                before=base,
                after=output,
                contract=world.contract,
                row_shift=materialized.row_shift,
                total_formula_rows=materialized.total_formula_rows,
                propagation=materialized.workbook_row_change,
                per_table_shift=materialized.per_table_shift,
            )
        spans["unmanaged_verify"] = time.perf_counter() - mark

        mark = time.perf_counter()
        structure_hash = compute_structure_hash_from_artifact(
            data=output.read_bytes(), contract=world.contract, anchors=anchors
        )
        spans["structure_hash"] = time.perf_counter() - mark
    total = time.perf_counter() - started_all

    artifact = output.read_bytes()
    # 产物读完就删：6 轮 × 246KB 本身不算什么，但把它留着会让「临时目录扫描为空」这类
    # 判据将来误以为有残留。
    output.unlink(missing_ok=True)
    return {
        "mode": mode,
        "substrate": "world_base_instrumented_template"
        if substrate is None
        else "previous_generation_artifact",
        "spans_seconds": {name: round(value, 3) for name, value in spans.items()},
        "segment_total_seconds": round(total, 3),
        "spans_sum_seconds": round(sum(spans.values()), 3),
        "calls": dict(counter.as_dict()),
        "extracted_field_count": len(extracted.values),
        "unmanaged_verify": {
            # 39 个 binding 各一条 report —— 分母在这里，不是「反正没报错所以绿」。
            "reports": len(unmanaged_verdicts),
            "reports_equivalent": sum(1 for ok in unmanaged_verdicts if ok),
            "reports_drifted": sum(1 for ok in unmanaged_verdicts if not ok),
            "last_report_equivalent": bool(report.equivalent),
            "last_report_first_difference": report.first_difference,
        },
        "structure_hash": structure_hash,
        "artifact": {
            "bytes": len(artifact),
            "sha256": hashlib.sha256(artifact).hexdigest(),
        },
    }


def _assert_paths_really_differ(run: dict[str, Any], *, binding_count: int) -> None:
    """反空转：两侧必须真的走了不同的写入路径。

    `force_chained_path()` 哪天静默变成 no-op，两条路径就跑同一份代码，「前后对照」
    会得出「提速 0%」或「提速全是噪声」这种读起来正常、实际上分母没了的结论。
    """
    calls = run["calls"]
    if run["mode"] == "chained":
        if calls["materialize_trips"] != binding_count or calls["single_pass_trips"]:
            raise RuntimeError(
                f"chained 侧趟数 {calls['materialize_trips']}（期望 {binding_count}）/ "
                f"单趟趟次 {calls['single_pass_trips']}（期望 0）—— "
                "force_chained_path() 没生效，本次对照无效"
            )
    elif calls["single_pass_trips"] != 1 or calls["materialize_trips"] != 1:
        raise RuntimeError(
            f"default 侧趟数 {calls['materialize_trips']} / 单趟趟次 "
            f"{calls['single_pass_trips']}（各期望 1）—— 单趟未命中，本次对照无效"
        )


def _stats(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "min": round(ordered[0], 3),
        "median": round(statistics.median(ordered), 3),
        "max": round(ordered[-1], 3),
    }


def _summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for mode in sorted({run["mode"] for run in runs}):
        mine = [run for run in runs if run["mode"] == mode]
        per_span = {
            name: _stats([float(run["spans_seconds"][name]) for run in mine])
            for name, _marker in _SEGMENT_STEPS
        }
        per_span["segment_total"] = _stats(
            [float(run["segment_total_seconds"]) for run in mine]
        )
        summary[mode] = per_span
    return summary


#: 需求 1.5 的目标（秒）。
TARGET_SECONDS = 10.0


def _verdict(summary: dict[str, Any]) -> dict[str, Any]:
    """需求 1.5 的判定 —— **从数字算出来**，不手写结论（手写会和数字漂移）。

    判两个口径，因为「≤10s」落在哪个 span 上会得到不同答案，而含糊其辞正是这条需求
    最容易被糊过去的地方：

    * `materialize_span` —— 只算 `adapter.materialize`，与 requirements 1.5 的
      「物化耗时」字面最近，也是本 spec 阶段 2 唯一动过的那一段；
    * `full_cpu_segment` —— materialize + extract + roundtrip + unmanaged + structure_hash，
      与用户那份 cProfile（42.8 + 6.0 + 6.9）的口径最近。任务 8/9（解析复用）没落地之前，
      后三段一点没优化过。
    """
    before = summary.get("chained")
    after = summary.get("default")
    if not before or not after:
        return {
            "requirement": "1.5",
            "status": "indeterminate",
            "why": "缺一侧路径的样本（需要 --mode both 才能给出前后对照）",
        }

    def judge(key: str) -> dict[str, Any]:
        return {
            "span": key,
            "target_seconds": TARGET_SECONDS,
            "before_chained": before[key],
            "after_single_pass": after[key],
            # 用 max（最慢那轮）判，不用 median —— 墙钟漂移时挑最有利的样本不叫证据。
            "met_on_worst_run": after[key]["max"] <= TARGET_SECONDS,
            "met_on_median": after[key]["median"] <= TARGET_SECONDS,
            "speedup_on_median": (
                round(before[key]["median"] / after[key]["median"], 2)
                if after[key]["median"]
                else None
            ),
        }

    materialize = judge("materialize")
    segment = judge("segment_total")
    remaining = {
        name: after[name]["median"]
        for name, _marker in _SEGMENT_STEPS
        if name != "materialize"
    }
    if segment["met_on_worst_run"]:
        status = "met"
    elif materialize["met_on_worst_run"]:
        status = "partial"
    else:
        status = "not_met"
    return {
        "requirement": "1.5",
        "status": status,
        "materialize_span": materialize,
        "full_cpu_segment": segment,
        "remaining_median_seconds_outside_materialize": remaining,
        "remaining_median_seconds_total": round(sum(remaining.values()), 3),
        "next_lever": (
            "任务 8/9（materialize/extract/verify 共用一个 workbook_read_scope，"
            "全流程对同一份字节只解析一次）—— 本证据里 materialize 之外那几段尚未优化"
        ),
    }


def _steady_state_probe(world: Any) -> dict[str, Any]:
    """在**第二代** substrate（上一次物化的产物）上再量一段。

    存在的理由：harness 的 base 是刚 instrument 出来的模板，它的 `xl/styles.xml` 从未被
    openpyxl 重序列化过；而物化里的转置 sheet 会经 openpyxl `wb.save()` 重写整簿状态 ⇒
    「模板 → 第一代产物」这一步天然带一批与本 spec 无关的非受管字节变化。生产的 substrate
    恒是**上一次发布的产物**（已被 openpyxl 归一化过），所以第二代才是生产的常态形态。

    本探针只回答一个问题：正常 runs 里那些 unmanaged drift 是不是「第一代」造成的。
    - 若第二代 `reports_drifted == 0` ⇒ 是；那么 runs 里的 verify **成本**照样有效
      （比对量一样），只有「结论」是 harness 首代特有。
    - 若第二代照样 drift ⇒ 与首代无关，如实登记给任务 9。
    """
    gen2 = world.staged("steady-state-gen2.xlsx")
    world.adapter.materialize(
        substrate=world.base,
        projection=world.projection,
        output=gen2,
        contract=world.contract,
    )
    run = measure_segment(
        world, mode="default", output_name="steady-state-gen3.xlsx", substrate=gen2
    )
    gen2.unlink(missing_ok=True)
    run["question"] = (
        "正常 runs 的 unmanaged drift 是否由「模板 → 第一代产物」造成"
    )
    run["answer"] = (
        "是：第二代 substrate 上 verify 全部等价"
        if run["unmanaged_verify"]["reports_drifted"] == 0
        else "不是：第二代 substrate 上仍有 drift ⇒ 与首代无关，登记给任务 9"
    )
    return run


def measure_segment_runs(*, modes: tuple[str, ...], repeat: int) -> dict[str, Any]:
    """同一 world / 同一 projection 上，两条路径交错各跑 `repeat` 轮。"""
    from tests.workpaper_sync.d4_materialize_harness import ENTRY_ID, build_world

    fidelity = _replica_fidelity()
    if fidelity["timed_steps_missing_from_production"]:
        raise RuntimeError(
            "生产 CPU 段的调用清单变了，脚本的复刻已过期："
            f"{fidelity['timed_steps_missing_from_production']}"
        )
    if fidelity["roundtrip_verify_touches_instance_state"]:
        raise RuntimeError(
            "`_assert_roundtrip_equivalent` 开始消费 `self` 了 —— 脚本不能再用 self=None 调它"
        )

    runs: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="d4-materialize-task7-") as raw:
        workdir = Path(raw)
        prepare_started = time.perf_counter()
        world = build_world(workdir)
        prepare_seconds = time.perf_counter() - prepare_started
        for round_index in range(1, repeat + 1):
            # 交错：同一轮里两条路径紧邻跑，机器忙/闲的漂移不会整段落在一侧。
            for mode in modes:
                run = measure_segment(
                    world, mode=mode, output_name=f"{mode}-r{round_index}.xlsx"
                )
                _assert_paths_really_differ(run, binding_count=world.binding_count)
                run["round"] = round_index
                run["order"] = len(runs) + 1
                runs.append(run)
                print(
                    f"  [{run['order']}] {mode} r{round_index}"
                    f"  total={run['segment_total_seconds']}s"
                    f"  {run['spans_seconds']}"
                )
        scope = {
            "entry_id": ENTRY_ID,
            "binding_count": world.binding_count,
            "substrate_bytes": world.base.stat().st_size,
            "projection_field_count": len(world.projection.values),
        }
        steady = _steady_state_probe(world)

    summary = _summarize(runs)
    return {
        "label": None,
        "captured_at": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "spec": "oo-single-pass-materialize-and-room-leave",
        "task": "7 真库前后对照计时证据",
        "requirements": ["1.5"],
        "scope": scope,
        "protocol": {
            "rounds": repeat,
            "modes": list(modes),
            "interleaved": len(modes) > 1,
            "same_world_same_projection": True,
            "harness_prepare_seconds": round(prepare_seconds, 3),
            "tracemalloc": False,
            "structure_fingerprint_cache_cleared_before_each_run": True,
            "replica_fidelity": fidelity,
        },
        "runs": runs,
        "steady_state_probe": steady,
        "summary": summary,
        "verdict": _verdict(summary),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "openpyxl": __import__("openpyxl").__version__,
        },
    }


def _main_segment(args: argparse.Namespace) -> int:
    modes: tuple[str, ...] = (
        ("chained", "default") if args.mode == "both" else (args.mode,)
    )
    if args.repeat < 1:
        raise SystemExit("--repeat 至少 1")
    label = args.label or f"task7-segments-{'-'.join(modes)}-x{args.repeat}"
    evidence = measure_segment_runs(modes=modes, repeat=args.repeat)
    evidence["label"] = label

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{label}.json"
    target.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"[evidence] {target}")
    for mode, spans in evidence["summary"].items():
        print(f"  {mode}:")
        for name, stat in spans.items():
            print(
                f"    {name:<18} min={stat['min']:>7.3f}  median={stat['median']:>7.3f}"
                f"  max={stat['max']:>7.3f}  (n={stat['n']})"
            )
    verdict = evidence["verdict"]
    print(f"  需求 1.5 判定：{verdict['status']}")
    if verdict["status"] != "indeterminate":
        for key in ("materialize_span", "full_cpu_segment"):
            block = verdict[key]
            print(
                f"    {key}: 改动前 median {block['before_chained']['median']}s"
                f" → 改动后 median {block['after_single_pass']['median']}s"
                f" / max {block['after_single_pass']['max']}s"
                f" ⇒ ≤{TARGET_SECONDS}s "
                f"{'达标' if block['met_on_worst_run'] else '未达标（按最慢轮判）'}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
