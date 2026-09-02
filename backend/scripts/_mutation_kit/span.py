"""跨行锚点变异骨架（`\\n` 编写 + 按目标文件换行自动升级 + sha256 还原自证）。

新增自 spec `.kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/`
Wave 0 Task 8 · Requirements 14.7 · Property 57。**纯增量**：不修改 `_mutation_kit` 的任何
既有模块，`anchor.find_anchor` 的「锚点不得含换行」那道断言与它的守卫全部原样保留。

## 为什么本模块存在，而不是改 `find_anchor`

`anchor.find_anchor` 走**整行相等**匹配，因此它必须拒绝跨行锚点 —— 那是对的，也有守卫
（`test_find_anchor_rejects_multiline_anchor`）锁着。但平台上确实存在只能用跨行锚点表达
的判据：判据本体是**相邻两行的组合**（例如「先 `hits = ...` 再 `if hits:`」），把它拆成
单行锚点就会变成另一条判据。这类脚本目前各自手写了一套「按目标文件换行升级锚点」的逻辑：

* `backend/scripts/check/mutate_workpaper_writer_inventory_gates.py`（`_dominant_newline`/`_localise`）
* `backend/scripts/diagnose/mutate_task4_callback_contract_guards.py`（`_apply` 内联 CRLF 升级 + `ALLOW_MULTI`）

`_LEGACY_NOT_REQUIRED` 里 `mutate_g7_column_alignment_guards.py` 的迁移阻塞原因正是这一条
（两条跨行锚点在 CRLF 工作树下恒 0 命中）。本模块把这套能力收敛成一份实现，并保留共享件
既有的四态判定、覆盖面分母与只读自检语义。

## 与 `cli.run_cli` 的分工

| | `cli.run_cli` | 本模块 `run_cli` |
|---|---|---|
| 锚点 | 单行、整行相等、支持 scope/offset 相对定位 | 跨行、子串定位、`\\n` 自动升级为目标 EOL |
| 还原核验 | md5 | sha256（本 spec design.md 明文要求） |
| 报告 | `--out` | `--report-path`（沿用 Task 4 runner 的参数名） |
| 判定 | `verdict.judge` 差集 | **同一个** `verdict.judge` |

判定、失败名收集、覆盖面分母都直接复用共享件，不另起一套 —— 四态的定义只能有一份。

## 三条不变量（都有反向自检）

1. **锚点必须唯一命中**：0 命中和 >1 命中都是 ANCHOR-MISS，不是「改第一处」。
   `allow_multi=True` 才允许多命中并全量替换，且必须写明 `multi_reason`。
2. **注入与还原都走字节**：`Path.read_text/write_text` 在 Windows 上会按 `os.linesep`
   重写换行，于是「内容没变而 hash 变了」，或者反过来把整文件换行改掉。
3. **还原后 sha256 必须等于变异前**：不相等立刻抛 `RestoreFailed` 并中止全部后续变异，
   否则后一条变异跑在被污染的工作树上，全部判定都变成 WRONG-TEST。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .anchor import AnchorMiss
from .apply import RestoreFailed
from .coverage import CoverageTally, guard_files_of
from .runner import RunResult, run_pytest
from .verdict import ANCHOR_MISS, ANY_RED, ERROR, GREEN, RED, WRONG_TEST, judge

__all__ = [
    "SpanMutation",
    "dominant_eol",
    "localise",
    "locate_span",
    "sha256_bytes",
    "sha256_of",
    "span_mutated",
    "validate_span",
    "validate_spans",
    "run_cli",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_of(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def dominant_eol(text: str) -> str:
    """目标文件实际使用的换行。

    仓库是混合的：`backend/app/**.py` 与 `.jsonl` 多为 CRLF，`backend/data/*.json` 与
    脚本多为 LF。判据只看「有没有出现过 CRLF」而不是「哪种更多」—— 混合换行的文件里，
    一条跨行锚点只要跨过任意一个 CRLF 就会 0 命中，所以宁可按 CRLF 升级后再判命中数，
    命中不到会如实报 ANCHOR-MISS，而不是悄悄改到别处。
    """
    return "\r\n" if "\r\n" in text else "\n"


def localise(text: str, eol: str) -> str:
    """把用 `\\n` 编写的锚点/替换文本升级成目标文件的换行。"""
    return text.replace("\n", eol) if eol != "\n" else text


@dataclass(frozen=True)
class SpanMutation:
    """一条跨行锚点变异声明。

    :param id: 变异编号，同一脚本内唯一
    :param path: 仓库相对路径（POSIX 分隔符）
    :param anchor: 待替换文本，**用 `\\n` 编写**，可跨行；按目标文件换行自动升级
    :param new: 替换文本，同样用 `\\n` 编写（空串 = 删除该段）
    :param want: 期望打红的测试名；`"*"` 表示任何新增失败即 RED（弱判据）
    :param why: 为什么这条变异不是无效变异 —— 必填
    :param wants: 多目标期望，任一命中即 RED
    :param allow_multi: 允许锚点多处命中并全部替换
    :param multi_reason: `allow_multi` 为真时必须写明理由
    :param expect_green: 对照项 —— 预期**不**打红（如「只加一条无害项」）
    """

    id: str
    path: str
    anchor: str
    new: str
    want: str
    why: str
    wants: tuple[str, ...] = field(default_factory=tuple)
    allow_multi: bool = False
    multi_reason: str = ""
    expect_green: bool = False

    def abspath(self, repo: Path) -> Path:
        return repo / self.path


def validate_span(m: SpanMutation) -> list[str]:
    """声明期校验，返回问题列表（空 = 合规）。坏声明不该有机会跑起来。"""
    errs: list[str] = []
    if not m.id:
        errs.append("id 为空")
    if not m.path:
        errs.append("path 为空")
    elif "\\" in m.path:
        errs.append(f"path 应用 POSIX 分隔符：{m.path!r}")
    if not m.anchor:
        errs.append("anchor 为空 —— 空串会命中任意位置")
    elif "\r" in m.anchor:
        errs.append(
            "anchor 含 \\r —— 锚点必须只用 \\n 编写，CRLF 升级由 localise() 负责；"
            "手写 \\r\\n 在 LF 文件上必然 0 命中"
        )
    elif not m.anchor.strip():
        errs.append("anchor 是纯空白 —— 无法定位")
    if "\r" in m.new:
        errs.append("new 含 \\r —— 同 anchor，只用 \\n 编写")
    if m.new == m.anchor:
        errs.append("new 与 anchor 相同 = 无效变异（改动不落盘）")
    if not m.want and not m.wants:
        errs.append('want / wants 都为空 —— 无期望目标则判不出 RED/WRONG-TEST；'
                    '迁移等价场景请显式写 want="*"')
    if m.expect_green and (m.want or m.wants) and ANY_RED not in ((m.want,) + tuple(m.wants)):
        errs.append("expect_green 的对照项不应同时声明具体 want —— 二者语义冲突")
    if not m.why or len(m.why) < 8:
        errs.append("why 缺失或过短 —— 必须写明为什么这条变异不是无效变异")
    if m.allow_multi and not m.multi_reason:
        errs.append("allow_multi=True 必须写 multi_reason —— 否则等于放弃唯一性约束")
    if m.multi_reason and not m.allow_multi:
        errs.append("给了 multi_reason 但 allow_multi=False —— 声明自相矛盾")
    return errs


def validate_spans(mutations: list[SpanMutation]) -> list[str]:
    problems: list[str] = []
    if not mutations:
        return ["变异清单为空 —— 空清单会让全部子命令恒成功（假绿）"]
    seen: dict[str, int] = {}
    for m in mutations:
        seen[m.id] = seen.get(m.id, 0) + 1
    for mid, count in sorted(seen.items()):
        if count > 1:
            problems.append(f"{mid}: id 重复 {count} 次 —— `--run {mid}` 只会跑到第一条")
    for m in mutations:
        problems.extend(f"{m.id or '<无 id>'}: {e}" for e in validate_span(m))
    return problems


def locate_span(text: str, anchor: str, *, allow_multi: bool = False) -> list[int]:
    """返回锚点（已按 `text` 的换行升级）的全部命中偏移。

    命中 0 处一律 :class:`AnchorMiss`；命中 >1 处除 `allow_multi` 外也是 ANCHOR-MISS ——
    「改第一处」是横跨全平台的假绿入口：同名多处时改错行，而判定照常给 RED。
    """
    localised = localise(anchor, dominant_eol(text))
    hits: list[int] = []
    start = text.find(localised)
    while start >= 0:
        hits.append(start)
        start = text.find(localised, start + 1)
    if not hits:
        raise AnchorMiss(
            f"锚点 0 命中（已按 {dominant_eol(text)!r} 升级）：{anchor[:120]!r}"
        )
    if len(hits) > 1 and not allow_multi:
        raise AnchorMiss(
            f"锚点命中 {len(hits)} 次（应为 1，偏移 {hits[:8]}）：{anchor[:120]!r}"
        )
    return hits


@contextmanager
def span_mutated(m: SpanMutation, repo: Path) -> Iterator[bytes]:
    """在上下文内使目标文件处于变异态，退出时无条件还原并核验 sha256。

    yield 出变异后的**文件字节**，供调用方做作用域自证。定位失败时不落盘。
    """
    target = m.abspath(repo)
    before = target.read_bytes()
    text = before.decode("utf-8")
    eol = dominant_eol(text)
    hits = locate_span(text, m.anchor, allow_multi=m.allow_multi)
    anchor = localise(m.anchor, eol)
    replacement = localise(m.new, eol)
    mutated_text = text.replace(anchor, replacement, -1 if m.allow_multi else 1)
    after = mutated_text.encode("utf-8")
    if sha256_bytes(after) == sha256_bytes(before):
        raise AnchorMiss(
            f"变异后 sha256 未变 —— 改动未落盘（无效变异），命中 {len(hits)} 处"
        )
    before_digest = sha256_bytes(before)
    try:
        target.write_bytes(after)
        yield after
    finally:
        target.write_bytes(before)
        restored = sha256_of(target)
        if restored != before_digest:
            raise RestoreFailed(
                f"{m.id} 还原后 sha256 不符：{restored} != {before_digest}（目标 {m.path}）"
            )


def _reconfigure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 - 老版本 Python 无 reconfigure
            pass


def _select(mutations: list[SpanMutation], spec: str) -> list[SpanMutation]:
    if not spec or spec == "all":
        return list(mutations)
    ids = {chunk.strip().upper() for chunk in spec.split(",") if chunk.strip()}
    picked = [m for m in mutations if m.id.upper() in ids]
    missing = ids - {m.id.upper() for m in picked}
    if missing:
        raise SystemExit(f"未知变异 id：{sorted(missing)}")
    return picked


def _check_anchors(mutations: list[SpanMutation], repo: Path) -> tuple[int, list[dict]]:
    """只读锚点自检；跑完核验目标文件 sha256 全部未变。"""
    before = {
        m.path: (sha256_of(m.abspath(repo)) if m.abspath(repo).is_file() else None)
        for m in mutations
    }
    records: list[dict] = []
    bad = 0
    for m in mutations:
        target = m.abspath(repo)
        if not target.is_file():
            bad += 1
            records.append({"id": m.id, "verdict": ANCHOR_MISS, "detail": "目标文件不存在"})
            print(f"[MISS] {m.id} {m.path} 目标文件不存在")
            continue
        text = target.read_bytes().decode("utf-8")
        try:
            hits = locate_span(text, m.anchor, allow_multi=m.allow_multi)
            eol = "CRLF" if dominant_eol(text) == "\r\n" else "LF"
            lineno = text[: hits[0]].count("\n") + 1
            span_lines = m.anchor.count("\n") + 1
            records.append(
                {"id": m.id, "verdict": "OK", "hits": len(hits), "line": lineno, "eol": eol}
            )
            print(f"[OK  ] {m.id} L{lineno} 跨 {span_lines} 行 命中 {len(hits)} 处 {eol} {m.path}")
        except AnchorMiss as exc:
            bad += 1
            records.append({"id": m.id, "verdict": ANCHOR_MISS, "detail": str(exc)})
            print(f"[MISS] {m.id} {m.path}\n        {exc}")
    changed = [
        m.path
        for m in mutations
        if m.abspath(repo).is_file() and sha256_of(m.abspath(repo)) != before[m.path]
    ]
    print(f"\n锚点自检：{len(mutations) - bad}/{len(mutations)} OK，{bad} MISS")
    if changed:
        print(f"[FATAL] --check-anchors 必须只读，但以下文件被改动：{changed}")
        return 2, records
    print("只读性核验：目标文件 sha256 全部未变")
    return (1 if bad else 0), records


def run_cli(
    *,
    mutations: list[SpanMutation],
    guard_files: dict[str, str],
    repo: Path,
    pytest_args: list[str],
    description: str = "跨行锚点守卫变异检验",
    baseline_passed: int | None = None,
    allow_dirty_baseline: bool = False,
    runner: Callable[[], RunResult] | None = None,
    argv: list[str] | None = None,
) -> int:
    """统一入口：`--list` / `--check-anchors` / `--run` / `--report-path`。

    :param guard_files: **必填** 覆盖面分母（守卫文件名 → 归属说明），语义同 `cli.run_cli`
    :param runner: 替身 runner，仅供本模块自测注入；生产调用不要传
    """
    _reconfigure_stdio()
    tally = CoverageTally(guard_files)  # 空分母在此直接抛

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--list", action="store_true", help="列出并校验全部变异声明")
    parser.add_argument("--check-anchors", action="store_true", help="只读锚点自检")
    parser.add_argument("--run", metavar="SPEC", help="执行：all | M01,M02")
    parser.add_argument("--report-path", metavar="PATH", help="四态汇总 JSON 落盘路径")
    args = parser.parse_args(argv)

    problems = validate_spans(mutations)
    if problems:
        print(f"[FAIL] 变异声明校验不通过（{len(problems)} 项）：")
        for p in problems:
            print(f"  !! {p}")
        return 6

    if args.list:
        for m in mutations:
            print(f"{m.id}  {m.path}  跨 {m.anchor.count(chr(10)) + 1} 行")
            print(f"      want: {m.want or list(m.wants)}{'  (对照 GREEN)' if m.expect_green else ''}")
            print(f"      why : {m.why[:150]}")
        return 0

    picked = _select(mutations, args.run or ("all" if args.check_anchors else ""))
    if args.check_anchors:
        code, records = _check_anchors(picked, repo)
        _write_report(args.report_path, records, {}, pytest_args, mode="check-anchors")
        return code
    if not args.run:
        parser.print_help()
        return 2

    run_tests = runner or (lambda: run_pytest(repo, list(pytest_args)))
    print("── 基线 ──")
    baseline = run_tests()
    print(f"  {baseline.summary}")
    print(f"  失败名集合：{sorted(baseline.failed) or '空集'}")
    if baseline.failed and not allow_dirty_baseline:
        print("  [ABORT] 基线非空，变异差集判定不可信")
        return 4
    if baseline_passed is not None and baseline.passed != baseline_passed:
        print(f"  [WARN] 与冻结基线 {baseline_passed} passed 不符（实测 {baseline.passed}）"
              " —— 改基线必须同时说明来源")

    records: list[dict] = []
    for m in picked:
        print(f"\n── {m.id} {m.path} ──")
        print(f"   {m.why[:180]}")
        record: dict = {"id": m.id, "path": m.path, "want": m.want, "why": m.why}
        started = time.time()
        digest_before = sha256_of(m.abspath(repo)) if m.abspath(repo).is_file() else None
        try:
            with span_mutated(m, repo):
                result = run_tests()
                verdict, added, gone, hit = judge(m.want, baseline.failed, result.failed, m.wants)
                if m.expect_green:
                    verdict = RED if verdict == GREEN else WRONG_TEST
                record.update(
                    verdict=verdict, summary=result.summary, added=added, gone=gone, hit=hit,
                    added_files=sorted(guard_files_of(added, result.name2file)),
                )
        except AnchorMiss as exc:
            record.update(verdict=ANCHOR_MISS, detail=str(exc))
        except RestoreFailed as exc:
            record.update(verdict=ERROR, detail=str(exc))
            records.append(record)
            print(f"   [FATAL] {exc}")
            _write_report(args.report_path, records, {}, pytest_args, mode="run")
            return 5
        except Exception as exc:  # noqa: BLE001 - 记录并继续；还原已在 finally 完成
            record.update(verdict=ERROR, detail=f"{type(exc).__name__}: {exc}")
        digest_after = sha256_of(m.abspath(repo)) if m.abspath(repo).is_file() else None
        record["restored"] = digest_before == digest_after
        record["restored_sha256"] = digest_after
        record["seconds"] = round(time.time() - started, 1)
        records.append(record)
        print(f"   判定 {record['verdict']}  ({record['seconds']}s)  还原={record['restored']}")
        if record.get("detail"):
            print(f"   detail: {record['detail']}")
        if record["verdict"] in (RED, WRONG_TEST):
            print(f"   新增失败 {len(record.get('added') or [])} 条，命中 {record.get('hit')}")
            tally.record(record.get("added_files") or [])
        elif record["verdict"] == GREEN:
            print("   [守卫缺陷] 变异未被任何守卫捕获")
        if not record["restored"]:
            print("   [FATAL] 还原核验失败，停止后续变异")
            break

    counts: dict[str, int] = {}
    for record in records:
        counts[record["verdict"]] = counts.get(record["verdict"], 0) + 1
    print("\n" + "=" * 72)
    for key in (RED, GREEN, WRONG_TEST, ANCHOR_MISS, ERROR):
        if key in counts:
            print(f"  {key:<12} {counts[key]}")
    for record in records:
        flag = "OK " if record["verdict"] == RED else "!! "
        print(f"  {flag}{record['id']}  {record['verdict']:<12} {str(record['want'])[:44]}")
    full_run = len(picked) == len(mutations)
    print()
    for line in tally.report(full_run):
        print(line)
    _write_report(args.report_path, records, counts, pytest_args, mode="run")
    all_red = bool(records) and counts.get(RED) == len(records)
    coverage_ok = tally.is_complete(True) if full_run else True
    return 0 if (all_red and coverage_ok) else 1


def _write_report(
    path: str | None,
    records: list[dict],
    counts: dict[str, int],
    pytest_args: list[str],
    *,
    mode: str,
) -> None:
    if not path:
        return
    payload = {
        "generated_by": "backend/scripts/_mutation_kit/span.py::run_cli",
        "mode": mode,
        "pytest_args": list(pytest_args),
        "tally": counts,
        "mutations": records,
    }
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"报告已写入 {path}")
