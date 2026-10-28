"""附注写端点清册：生成与检查（spec partner-manager-edit-permission，需求 1；design §4.12 流程 1~8、§5.3、§5.4）。

用法（仓库根执行）::

    python backend/scripts/gen/gen_note_write_inventory.py [--check] [--out PATH] [--root REPO]

- ``--root``：被扫描的仓库根，默认本脚本所在仓库。可指向另一棵树（如改造前的基线 worktree）：该树的源码只被读取，
  运行时路由表在子进程里导入该树收集（``-I -B``，不落 ``.pyc``，副作用一律拦下，见 ``authz_inventory.routes``）。
- ``--out``：清册文件。生成模式写到这里，检查模式与它比对；默认本脚本所在仓库的
  ``backend/data/authz/note_write_inventory.json``。
- 目标门禁声明固定读本脚本所在仓库的 ``backend/data/authz/note_write_target_declarations.json``，不随 ``--root`` 变化。

流程：① 内置合成样例自检（需求 1.6 的 9 个，``selfcheck.NOTE_INVENTORY_SAMPLES``）→ ② 扫描文件与写端点（源码路由声明与
运行时路由表对账；未注册的照记）→ ③ 现门禁（``gates``）→ ④ 归类 → ⑤ 目标门禁（``classify``）→ ⑥ 前端调用点（任务 8.3
接入，见 ``scan_frontend``）→ ⑦ 需求 1.5 的四项校验 → ⑧ 输出。出现需求 1.7 的任一失败条件时用中文逐项列出原因，
退出码 1，不写任何文件（已提交的清册保持不变）。

退出码：0 = 生成完成 / 检查一致（打印「附注写端点清册与仓库现状一致」）；1 = 自检判错、参数错误或需求 1.7 的失败；
2 = 检查模式下现算结果与清册不一致或清册不存在（逐条列出新增 / 消失 / 变化；沿用本仓 ``--check`` 漂移退出码 2 的约定）。
控制台一律按 UTF-8 输出（Windows 下被管道捕获时也是），不随 ``PYTHONIOENCODING`` 变化。

前端调用点（需求 1.3 / 1.4 与 1.5 第 3 项）尚未接入：``scan_frontend`` 返回 None 时，E、I 两类条目的
``editor_call_points`` / ``outside_editor_files`` 与顶层 ``editor_unmatched`` / ``editor_write_call_total`` 记 null，
``scan.frontend`` 写明待接入，第 3 项校验记「待接入」，不算作通过。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

sys.dont_write_bytecode = True  # 先于导入本包：不在仓库里落 __pycache__
from authz_inventory import classify, gates, render, routes, selfcheck  # noqa: E402

SCHEMA = "note_write_inventory/v1"
SCRIPT_REPO = Path(__file__).resolve().parents[3]
DECLARATIONS = SCRIPT_REPO / "backend" / "data" / "authz" / "note_write_target_declarations.json"
DEFAULT_OUT = SCRIPT_REPO / "backend" / "data" / "authz" / "note_write_inventory.json"
FRONTEND_PENDING = "待接入（任务 8.3）"
CONSISTENT = "附注写端点清册与仓库现状一致"
EXIT_OK, EXIT_FAILED, EXIT_DRIFT = 0, 1, 2


class InventoryFailure(Exception):
    """需求 1.7 的失败；``problems`` 为中文逐项原因（去重、保持先后）。"""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = list(dict.fromkeys(problems))
        super().__init__("\n".join(self.problems))


# ─── ⑥ 前端调用点：任务 8.3 的接入点 ─────────────────────────────────────────────


@dataclass(frozen=True)
class FrontendScan:
    """需求 1.3 / 1.4 的扫描结果（任务 8.3 由 ``authz_inventory.frontend`` 产出）。

    ``call_points`` / ``outside_files`` 以（方法，完整路径）为键，只含 E、I 两类端点：前者为附注编辑器范围内的调用点
    （design §5.3 的 key / form / wrapper / ambiguous；没有调用点的端点给空序列），后者为范围外有调用点的前端文件。
    ``write_call_total`` 为编辑器范围内的写方法调用数，``matched_call_total`` 为其中命中扫描端点的调用数；需求 1.5 第 3 项
    即 ``write_call_total == matched_call_total + len(table_c) + len(table_d) + len(unresolved)``。"""

    call_points: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]]
    outside_files: Mapping[tuple[str, str], Sequence[str]]
    table_c: Sequence[Mapping[str, Any]]
    table_d: Sequence[Mapping[str, Any]]
    unresolved: Sequence[Mapping[str, Any]]
    write_call_total: int
    matched_call_total: int


def scan_frontend(root: Path, endpoints: Sequence[Mapping[str, Any]], table: routes.RouteTable) -> FrontendScan | None:
    """前端调用点扫描（任务 8.3 实现）。``endpoints`` 为本次现算的清册条目（含 method / path / category），``table`` 为
    运行时路由表（表 C / 表 D 与全部已注册路由比对用）。未接入时返回 None，清册如实记为待接入。"""
    return None


def _apply_frontend(entries: list[dict[str, Any]], frontend: FrontendScan) -> None:
    for entry in entries:
        if entry["category"] in classify.COVERAGE_CATEGORIES:
            key = (entry["method"], entry["path"])
            entry["editor_call_points"] = [dict(point) for point in frontend.call_points.get(key, ())]
            entry["outside_editor_files"] = sorted(frontend.outside_files.get(key, ()))


# ─── ②～⑤ 扫描、识别、归类、目标门禁 ───────────────────────────────────────────


def _scan_files(root: Path, problems: list[str]) -> tuple[tuple[str, ...], dict[str, gates.ModuleInfo]]:
    if not (root / "backend" / "app" / "routers").is_dir():
        raise InventoryFailure([f"--root 指向的不是本仓库（缺少 backend/app/routers/）：{root}"])
    files = routes.note_router_files(root)
    if not files:
        raise InventoryFailure(["扫描到的附注路由文件数为 0（backend/app/routers/ 直接子文件中没有匹配 "
                                f"{' / '.join(routes.NOTE_FILE_PATTERNS)} 的 .py）"])
    infos: dict[str, gates.ModuleInfo] = {}
    failed: list[str] = []
    for file in files:
        try:
            infos[file] = gates.analyze_module(file, (root / file).read_bytes())
        except gates.ParseFailure as exc:
            failed.append(f"文件无法解析：{exc}")
    if failed:
        raise InventoryFailure([*failed, "有文件无法解析，未收集运行时路由表（导入同样会失败）"])
    problems.extend(f"模块级问题：{issue.message()}" for info in infos.values() for issue in info.issues)
    return files, infos


def _route_table(root: Path, problems: list[str]) -> routes.RouteTable:
    try:
        return routes.collect_route_table(root)
    except routes.RouteCollectionError as exc:
        raise InventoryFailure([*problems, f"收集运行时路由表失败：{exc}"]) from exc


def _write_routes(infos: Mapping[str, gates.ModuleInfo], files: Sequence[str], table: routes.RouteTable,
                  problems: list[str]) -> list[tuple[routes.DeclaredRoute, routes.RouteRecord]]:
    declared = [route for info in infos.values() for route in info.declared_routes()]
    match = routes.match_declared_routes(table, declared, files)
    problems.extend(f"不支持的写法：运行时路由 {r.method} {r.path}（{r.file}::{r.function}）对不上源码里的路由声明"
                    for r in match.unmatched_runtime)
    pairs = [(d, r) for d, r in (*match.registered, *match.unregistered) if d.method in routes.WRITE_METHODS]
    if not pairs:
        problems.append("扫描到的写端点数为 0（POST / PUT / PATCH / DELETE）")
    return pairs


def _declarations(path: Path, problems: list[str]) -> dict[tuple[str, str], classify.Declaration]:
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except FileNotFoundError:
        problems.append(f"目标门禁声明文件不存在：{path}")
        return {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        problems.append(f"目标门禁声明文件无法解析：{path}（{exc}）")
        return {}
    found, issues = classify.parse_declarations(data)
    problems.extend(issues)
    return found


def _entries(infos: Mapping[str, gates.ModuleInfo], pairs: Sequence[tuple[routes.DeclaredRoute, routes.RouteRecord]],
             declarations: Mapping[tuple[str, str], classify.Declaration], problems: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for decl, record in pairs:
        where = f"{decl.method} {record.path}（{decl.file}::{decl.function}）"
        result = gates.recognize_endpoint(infos[decl.file], decl, record if record.registered else None)
        if result.issues:
            problems.extend(f"{decl.method} {record.path}：{issue.message()}" for issue in result.issues)
            continue
        verdict = classify.classify(decl.file, result)
        if verdict.category is None:
            problems.append(f"{where}：{verdict.reason}")
            continue
        target = classify.resolve_target(verdict.category, declarations.get((decl.method, record.path)))
        if target.kind is None:
            problems.append(f"{where}：I 类端点缺少目标门禁声明（需求 1.9：I 类没有默认值，须逐个声明为附注编辑门禁、"
                            "design 定级门禁、保持现门禁或待 design 核对）")
            continue
        entry: dict[str, Any] = {
            "file": PurePosixPath(decl.file).name, "function": decl.function, "method": decl.method,
            "path": record.path, "registered": record.registered, "registry_group": record.group,
            "current_gate": classify.current_gate(result), "category": verdict.category,
            "target_gate": target.to_json(), "current_equals_target": classify.target_met(result, target),
        }
        if verdict.category in classify.COVERAGE_CATEGORIES:  # 需求 1.3 只要求 E、I 两类列调用点
            entry["editor_call_points"] = None
            entry["outside_editor_files"] = None
        entries.append(entry)
    return entries


# ─── ⑦ 校验（需求 1.5）───────────────────────────────────────────────────────────


def _validate(pairs: Sequence[tuple[routes.DeclaredRoute, routes.RouteRecord]], entries: Sequence[Mapping[str, Any]],
              declarations: Mapping[tuple[str, str], classify.Declaration], frontend: FrontendScan | None,
              problems: list[str]) -> list[tuple[str, str]]:
    checks: list[tuple[str, str]] = []

    def check(name: str, failures: list[str]) -> None:
        checks.append((name, "不成立" if failures else "成立"))
        problems.extend(f"需求 1.5 校验不成立（{name}）：{failure}" for failure in failures)

    counted = sum(Counter(entry["category"] for entry in entries).values())
    check("各类计数之和等于写端点总数",
          [] if counted == len(pairs) else [f"各类计数之和 {counted} ≠ 写端点总数 {len(pairs)}（未归类的端点见上）"])
    repeated = sorted(k for k, n in Counter((d.method, r.path) for d, r in pairs).items() if n > 1)
    check("每个（方法，完整路径）恰好出现一次", [f"{method} {path} 出现不止一次" for method, path in repeated])
    if frontend is None:
        checks.append(("编辑器内写调用数守恒", FRONTEND_PENDING + "，本次未校验"))
    else:
        parts = (frontend.matched_call_total, len(frontend.table_c), len(frontend.table_d), len(frontend.unresolved))
        check("编辑器内写调用数守恒", [] if frontend.write_call_total == sum(parts) else [
            f"编辑器范围内写方法调用 {frontend.write_call_total} ≠ 命中 {parts[0]} + 表 C {parts[1]} + 表 D {parts[2]}"
            f" + 未解析 {parts[3]}"])
    existing = {(d.method, r.path) for d, r in pairs}
    check("每条声明都对应现存写端点", [  # 比需求「与默认值不同的声明」更严：全部声明都须对上
        f"声明 {method} {path}（目标 {declaration.target.kind}）对不上现存的写端点"
        for (method, path), declaration in sorted(declarations.items()) if (method, path) not in existing])
    return checks


# ─── ⑧ 输出 ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Built:
    payload: dict[str, Any]
    text: str
    summary: tuple[str, ...]


def _payload(files: Sequence[str], entries: list[dict[str, Any]], frontend: FrontendScan | None) -> dict[str, Any]:
    counts = {category: 0 for category in classify.CATEGORY_ORDER}
    for entry in entries:
        counts[entry["category"]] += 1
    unmatched: dict[str, Any] | None = None
    if frontend is not None:
        _apply_frontend(entries, frontend)
        unmatched = {"table_c": [dict(x) for x in frontend.table_c], "table_d": [dict(x) for x in frontend.table_d],
                     "unresolved": [dict(x) for x in frontend.unresolved]}
    return {
        "schema": SCHEMA,
        "scan": {"files": [PurePosixPath(file).name for file in files], "write_endpoint_total": len(entries),
                 "frontend": FRONTEND_PENDING if frontend is None else "已扫描"},
        "counts": counts,
        "endpoints": render.sort_entries(entries),
        "editor_unmatched": unmatched,
        "editor_write_call_total": None if frontend is None else frontend.write_call_total,
    }


def _summary(files: Sequence[str], entries: Sequence[Mapping[str, Any]],
             checks: Sequence[tuple[str, str]]) -> tuple[str, ...]:
    counts = Counter(entry["category"] for entry in entries)
    kinds = Counter(entry["target_gate"]["kind"] for entry in entries)
    declared = Counter(entry["target_gate"]["kind"] for entry in entries if entry["target_gate"]["declared"])
    coverage = sum(1 for e in entries if e["category"] in classify.COVERAGE_CATEGORIES
                   and e["target_gate"]["kind"] == "note_edit_gate")
    redundant = sum(1 for e in entries if e["target_gate"]["declared"]
                    and e["target_gate"]["kind"] == classify.DEFAULT_TARGETS[e["category"]])
    met = sum(1 for entry in entries if entry["current_equals_target"])
    unregistered = sum(1 for entry in entries if not entry["registered"])
    return (
        f"扫描文件 {len(files)} 个；写端点 {len(entries)} 个（其中未注册 {unregistered} 个）",
        "各类计数：" + " / ".join(f"{c} {counts.get(c, 0)}" for c in classify.CATEGORY_ORDER),
        "目标门禁：" + " / ".join(f"{classify.TARGET_NAMES[k]} {kinds.get(k, 0)}（其中声明 {declared.get(k, 0)}）"
                              for k in classify.TARGET_KINDS) + f"；与类别默认值相同的声明 {redundant} 条",
        f"附注编辑门禁覆盖集合（E、I 两类中目标门禁为附注编辑门禁）：{coverage} 个",
        f"现门禁已等于目标门禁：{met} 个；现门禁未等于目标门禁：{len(entries) - met} 个",
        "需求 1.5 校验：" + "；".join(f"{name}——{status}" for name, status in checks),
    )


def build(root: Path, declarations_path: Path = DECLARATIONS) -> Built:
    """现算清册（不写文件）。任一失败条件抛 ``InventoryFailure``。"""
    problems: list[str] = []
    files, infos = _scan_files(root, problems)
    table = _route_table(root, problems)
    pairs = _write_routes(infos, files, table, problems)
    declarations = _declarations(declarations_path, problems)
    entries = _entries(infos, pairs, declarations, problems)
    frontend = scan_frontend(root, entries, table)
    checks = _validate(pairs, entries, declarations, frontend, problems)
    if problems:
        raise InventoryFailure(problems)
    payload = _payload(files, entries, frontend)
    try:
        text = render.dumps(payload, roots=(root, SCRIPT_REPO))
    except render.RenderError as exc:
        raise InventoryFailure([str(exc)]) from exc
    return Built(payload, text, _summary(files, entries, checks))


def _drift(committed: Any, payload: Mapping[str, Any]) -> list[str]:
    """检查模式的逐条差异：条目按（文件，完整路径，方法）比对，顶层其余字段逐个比对。"""
    lines: list[str] = []
    old = committed.get("endpoints") if isinstance(committed, dict) else None
    if isinstance(old, list) and all(isinstance(entry, dict) for entry in old):
        try:
            lines += render.describe_diff(render.diff_entries(old, payload["endpoints"]))
        except render.RenderError as exc:
            lines.append(str(exc))
    else:
        lines.append("已提交的清册没有 endpoints 条目列表")
    committed_top = committed if isinstance(committed, dict) else {}
    for key in sorted((set(committed_top) | set(payload)) - {"endpoints"}):
        before, after = (json.dumps(side.get(key, "（缺失）"), ensure_ascii=False, sort_keys=True)
                         for side in (committed_top, payload))
        if before != after:
            lines.append(f"顶层字段变化：{key}")
    return lines


def check_against(out: Path, built: Built) -> int:
    """检查模式：不写任何文件，与 ``out`` 逐条比对。"""
    if not out.is_file():
        print(f"附注写端点清册与仓库现状不一致：已提交的清册不存在（{out}）", file=sys.stderr)
        return EXIT_DRIFT
    # 换行归一：index 是 LF，Windows 检出（autocrlf）是 CRLF —— 只差换行不算漂移（spec note-pull-followup-closure R21）
    raw = render.normalize_newlines(out.read_bytes())
    if raw == built.text.encode("utf-8"):
        print(CONSISTENT)
        return EXIT_OK
    try:
        lines = _drift(json.loads(raw.decode("utf-8")), built.payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        lines = [f"已提交的清册无法解析（{exc}）"]
    print(f"附注写端点清册与仓库现状不一致（{out}；检查模式不写任何文件）：", file=sys.stderr)
    for line in lines or ["条目与顶层字段逐项相同，但文本不同（格式或换行被改动）；以生成模式重写即可"]:
        print(f"- {line}", file=sys.stderr)
    return EXIT_DRIFT


def run(*, root: Path, out: Path, check: bool, declarations: Path = DECLARATIONS,
        samples: Sequence[selfcheck.Sample] = selfcheck.NOTE_INVENTORY_SAMPLES) -> int:
    """生成或检查一次（供命令行与测试调用）；返回退出码。"""
    title = "附注写端点清册内置合成样例自检"
    try:
        count = selfcheck.ensure_samples(samples, title=title)
    except selfcheck.SelfCheckFailed as exc:
        print(exc, file=sys.stderr)
        return EXIT_FAILED
    print(f"{title}通过：{count} 个样例全部按期望")
    try:
        built = build(root, declarations)
    except InventoryFailure as exc:
        print(f"附注写端点清册{'检查' if check else '生成'}失败（{len(exc.problems)} 项；不写出清册，已提交的清册保持不变）：",
              file=sys.stderr)
        for problem in exc.problems:
            print(f"- {problem}", file=sys.stderr)
        return EXIT_FAILED
    print("\n".join(built.summary))
    if check:
        return check_against(out, built)
    render.write_text(out, built.text)
    print(f"已写出附注写端点清册：{out}")
    return EXIT_OK


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:  # 参数错误按失败（1）处理，与检查模式的漂移（2）区分
        self.print_usage(sys.stderr)
        self.exit(EXIT_FAILED, f"参数错误：{message}\n")


def main(argv: Sequence[str] | None = None) -> int:
    render.utf8_console()
    parser = _Parser(prog="gen_note_write_inventory.py", description="附注写端点清册（需求 1）：生成或检查。")
    parser.add_argument("--check", action="store_true", help="检查模式：不写任何文件，与清册逐条比对；不一致退出码 2")
    parser.add_argument("--out", type=Path, help="清册文件（生成模式写出、检查模式比对）；默认本脚本所在仓库的 "
                                               "backend/data/authz/note_write_inventory.json")
    parser.add_argument("--root", type=Path, help="被扫描的仓库根；默认本脚本所在仓库")
    args = parser.parse_args(argv)
    root = (args.root or SCRIPT_REPO).resolve()
    out = (args.out or DEFAULT_OUT).resolve()
    return run(root=root, out=out, check=args.check)


if __name__ == "__main__":
    sys.exit(main())
