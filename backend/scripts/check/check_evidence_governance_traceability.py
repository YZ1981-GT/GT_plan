r"""
attachment-ocr-ai-evidence-governance-hardening — 三件套追溯与完成守卫 (Task 11.1)

解析 requirements.md / design.md / tasks.md 三件套，断言:

1. R1–R16 每条都出现，且被 ≥1 个任务的 `_Requirements:` 行引用，并出现在 design §13
   Requirements Traceability 表。
2. P1–P30 每条都出现在 requirements §5 Correctness Properties 表 AND design 的 P1–P30 同步表。
3. UAT-01～15 每条都出现在 requirements §6 UAT Scenarios AND design §12 UAT matrix AND
   被 Wave 9 (10.x) 任务覆盖。
4. tasks.md 恰好 55 个叶子任务 (X.Y)，11 个 wave (0–10)，11 个顶层任务 (1–11)。
5. Task Dependency Graph JSON: 每个叶子恰好出现一次 (无 missing/extra/duplicate)，
   wave 依赖只引用更早 wave 的叶子。
6. 无 optional (`*` / `\*`) 任务、无 ask-user / checkpoint 任务。

用法:
    python backend/scripts/check/check_evidence_governance_traceability.py [--strict]

--strict: 全部通过返回 exit 0，任一失败返回 exit 1
无 --strict: 输出报告但始终 exit 0 (报告模式)
"""
import sys
import re
import json
from pathlib import Path

# Windows GBK console 兼容
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ─── 路径常量 ─────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[3]  # GT_plan 根目录
SPEC_DIR = ROOT / ".kiro" / "specs" / "attachment-ocr-ai-evidence-governance-hardening"
REQUIREMENTS_MD = SPEC_DIR / "requirements.md"
DESIGN_MD = SPEC_DIR / "design.md"
TASKS_MD = SPEC_DIR / "tasks.md"

# ─── 预期计数 (来自 spec 明文声明) ─────────────────────────────────────────────

EXPECTED_R = list(range(1, 17))        # R1–R16
EXPECTED_P = list(range(1, 31))        # P1–P30
EXPECTED_UAT = list(range(1, 16))      # UAT-01～15
EXPECTED_LEAF_COUNT = 55               # 55 叶子任务 (plan 明文)
EXPECTED_WAVE_COUNT = 11               # 11 waves (0–10)
EXPECTED_TOPLEVEL_COUNT = 11           # 顶层任务 1–11
UAT_WAVE = 9                           # UAT 覆盖在 Wave 9 (10.x)

# ─── 检查结果收集 ──────────────────────────────────────────────────────────────

failures: list[str] = []
warnings: list[str] = []
report: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def note(msg: str) -> None:
    report.append(msg)


# ─── 工具: section 提取 ───────────────────────────────────────────────────────

def slice_between(content: str, start_marker: str, end_marker: str | None, label: str) -> str:
    """返回 start_marker 到 end_marker 之间的子串。找不到 marker 时记录失败并返回 ''。"""
    si = content.find(start_marker)
    if si < 0:
        fail(f"[{label}] 未找到起始标记: {start_marker!r}")
        return ""
    rest = content[si + len(start_marker):]
    if end_marker is None:
        return rest
    ei = rest.find(end_marker)
    if ei < 0:
        fail(f"[{label}] 未找到结束标记: {end_marker!r}")
        return rest
    return rest[:ei]


# ─── 加载文件 ──────────────────────────────────────────────────────────────────

def load(path: Path, label: str) -> str:
    if not path.exists():
        fail(f"{label} 不存在: {path}")
        return ""
    return path.read_text(encoding="utf-8")


# ─── 检查 1: R1–R16 定义 / 任务引用 / design 追溯表 ───────────────────────────

def check_requirements_traceability(req: str, design: str, tasks: str) -> None:
    # 1a. requirements.md 中每条 R 有定义标题 "### Requirement N"
    defined = set(int(n) for n in re.findall(r"^### Requirement (\d+)\b", req, re.MULTILINE))
    missing_def = [f"R{n}" for n in EXPECTED_R if n not in defined]
    if missing_def:
        fail(f"requirements.md 缺少需求定义: {missing_def}")
    extra_def = sorted(n for n in defined if n not in EXPECTED_R)
    if extra_def:
        warn(f"requirements.md 存在预期外的需求定义: R{extra_def}")

    # 1b. tasks.md `_Requirements:` 行引用了每条 R
    # 注意: 行尾常以 markdown 斜体下划线结束 (如 "R16_")，而 `_` 是正则 word char，
    # 会破坏 `\b` 边界；改用 lookbehind/lookahead 精确匹配 R 编号。
    req_lines = re.findall(r"_Requirements?:\s*(.+)", tasks)
    referenced = set()
    for line in req_lines:
        for m in re.findall(r"(?<![A-Za-z])R(\d+)(?!\d)", line):
            referenced.add(int(m))
    missing_ref = [f"R{n}" for n in EXPECTED_R if n not in referenced]
    if missing_ref:
        fail(f"tasks.md `_Requirements:` 行未引用: {missing_ref}")

    # 1c. design §13 Requirements Traceability 表包含每条 R 行
    trace = slice_between(design, "## 13. Requirements Traceability", "## 14.", "design 追溯表")
    trace_rows = set(int(n) for n in re.findall(r"^\|\s*R(\d+)\s*\|", trace, re.MULTILINE))
    missing_trace = [f"R{n}" for n in EXPECTED_R if n not in trace_rows]
    if missing_trace:
        fail(f"design §13 追溯表缺少行: {missing_trace}")

    if not (missing_def or missing_ref or missing_trace):
        note(f"[OK] R1–R16 全部定义、被 {len(referenced)} 任务引用集覆盖、并在 design 追溯表 ({len(trace_rows)} 行)")


# ─── 检查 2: P1–P30 requirements 表 AND design 同步表 ─────────────────────────

def check_properties(req: str, design: str) -> None:
    # 2a. requirements §5 Correctness Properties 表
    # 只取表行首列的属性 ID (形如 "| **P1 项目隔离** |")，避免匹配描述文本里的 "P0"。
    req_props_section = slice_between(req, "## 5. Correctness Properties", "## 6. UAT Scenarios", "requirements 属性表")
    req_props = set(int(n) for n in re.findall(r"^\|\s*\*\*P(\d+)\b", req_props_section, re.MULTILINE))
    missing_req = [f"P{n}" for n in EXPECTED_P if n not in req_props]
    if missing_req:
        fail(f"requirements §5 属性表缺少: {missing_req}")

    # 2b. design P1–P30 同步表 (以 "同步表" 起，到 §12 止)
    design_sync = slice_between(design, "同步表", "## 12.", "design 同步表")
    # 表行形如 "| P1 | ... |"
    design_props = set(int(n) for n in re.findall(r"^\|\s*P(\d+)\s*\|", design_sync, re.MULTILINE))
    missing_design = [f"P{n}" for n in EXPECTED_P if n not in design_props]
    if missing_design:
        fail(f"design 同步表缺少行: {missing_design}")

    extra_req = sorted(n for n in req_props if n not in EXPECTED_P)
    if extra_req:
        warn(f"requirements 属性表存在预期外的属性: P{extra_req}")

    if not (missing_req or missing_design):
        note(f"[OK] P1–P30 全部在 requirements 属性表 ({len(req_props)}) 与 design 同步表 ({len(design_props)} 行)")


# ─── 检查 3: UAT-01～15 requirements / design matrix / Wave 9 覆盖 ────────────

def _uat_nums(text: str) -> set[int]:
    return set(int(n) for n in re.findall(r"UAT-0*(\d+)\b", text))


def check_uat(req: str, design: str, tasks: str, wave9_task_text: str) -> None:
    # 3a. requirements §6 UAT Scenarios
    req_uat_section = slice_between(req, "## 6. UAT Scenarios", "## 7. Dependencies", "requirements UAT")
    req_uat = _uat_nums(req_uat_section)
    missing_req = [f"UAT-{n:02d}" for n in EXPECTED_UAT if n not in req_uat]
    if missing_req:
        fail(f"requirements §6 缺少场景: {missing_req}")

    # 3b. design §12 UAT matrix
    design_uat_section = slice_between(design, "## 12.", "## 13.", "design UAT matrix")
    design_uat = _uat_nums(design_uat_section)
    missing_design = [f"UAT-{n:02d}" for n in EXPECTED_UAT if n not in design_uat]
    if missing_design:
        fail(f"design §12 UAT matrix 缺少: {missing_design}")

    # 3c. Wave 9 (10.x) 任务文本覆盖
    wave9_uat = _uat_nums(wave9_task_text)
    missing_wave9 = [f"UAT-{n:02d}" for n in EXPECTED_UAT if n not in wave9_uat]
    if missing_wave9:
        fail(f"Wave 9 (10.x) 任务未覆盖: {missing_wave9}")

    if not (missing_req or missing_design or missing_wave9):
        note(f"[OK] UAT-01～15 全部在 requirements §6、design §12、Wave 9 任务覆盖")


# ─── 检查 4+5+6: tasks 叶子/wave/依赖图/optional ─────────────────────────────

def parse_tasks(tasks: str) -> dict:
    """解析 tasks.md，返回结构化信息。"""
    lines = tasks.splitlines()

    toplevel = []   # [(mark, num, text)]
    leaves = []     # [(mark, "X.Y", full_line)]
    leaf_lines_by_wave = {}  # top_num -> [leaf ids]

    # 顶层任务: "- [x] 1. Wave 0 ..."
    toplevel_re = re.compile(r"^- \[(.)\]\s+(\d+)\.\s")
    # 叶子任务: "  - [x] 1.1 ..."
    leaf_re = re.compile(r"^\s*- \[(.)\]\s+(\d+)\.(\d+)\b(.*)$")

    for ln in lines:
        m_top = toplevel_re.match(ln)
        if m_top:
            toplevel.append((m_top.group(1), int(m_top.group(2)), ln))
            continue
        m_leaf = leaf_re.match(ln)
        if m_leaf:
            top_num = int(m_leaf.group(2))
            leaf_id = f"{m_leaf.group(2)}.{m_leaf.group(3)}"
            leaves.append((m_leaf.group(1), leaf_id, ln))
            leaf_lines_by_wave.setdefault(top_num, []).append(leaf_id)

    return {
        "toplevel": toplevel,
        "leaves": leaves,
        "leaf_ids": [lid for _, lid, _ in leaves],
    }


def check_task_counts(parsed: dict) -> None:
    # 4a. 叶子数 == 55
    leaf_ids = parsed["leaf_ids"]
    n_leaf = len(leaf_ids)
    if n_leaf != EXPECTED_LEAF_COUNT:
        fail(f"叶子任务数 = {n_leaf}，预期 {EXPECTED_LEAF_COUNT}")
    else:
        note(f"[OK] 叶子任务数 = {n_leaf}")

    # 叶子重复检测
    dupes = sorted({x for x in leaf_ids if leaf_ids.count(x) > 1})
    if dupes:
        fail(f"tasks.md 中叶子任务编号重复: {dupes}")

    # 4b. 顶层任务 == 11
    n_top = len(parsed["toplevel"])
    top_nums = sorted(t[1] for t in parsed["toplevel"])
    if n_top != EXPECTED_TOPLEVEL_COUNT:
        fail(f"顶层任务数 = {n_top} ({top_nums})，预期 {EXPECTED_TOPLEVEL_COUNT}")
    else:
        note(f"[OK] 顶层任务数 = {n_top} (1–{max(top_nums)})")


def parse_dependency_graph(tasks: str) -> dict | None:
    block = slice_between(tasks, "## Task Dependency Graph", None, "依赖图")
    m = re.search(r"```json\s*(\{.*?\})\s*```", block, re.DOTALL)
    if not m:
        fail("Task Dependency Graph JSON 代码块未找到")
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as e:
        fail(f"Task Dependency Graph JSON 解析失败: {e}")
        return None


def check_dependency_graph(graph: dict, parsed: dict) -> None:
    if not graph or "waves" not in graph:
        fail("依赖图缺少 'waves' 键")
        return

    waves = graph["waves"]

    # 4c. wave 数 == 11 (0–10)
    wave_nums = sorted(w.get("wave") for w in waves)
    if len(waves) != EXPECTED_WAVE_COUNT:
        fail(f"依赖图 wave 数 = {len(waves)}，预期 {EXPECTED_WAVE_COUNT}")
    if wave_nums != list(range(0, EXPECTED_WAVE_COUNT)):
        fail(f"依赖图 wave 编号 = {wave_nums}，预期 0–{EXPECTED_WAVE_COUNT - 1}")
    else:
        note(f"[OK] 依赖图 wave = {wave_nums}")

    # 5. 每个叶子在依赖图 tasks 中恰好出现一次 vs tasks.md 叶子集合
    graph_leaves = []
    wave_of = {}   # leaf -> wave number
    for w in waves:
        wn = w.get("wave")
        for t in w.get("tasks", []):
            graph_leaves.append(t)
            wave_of[t] = wn

    graph_set = set(graph_leaves)
    md_set = set(parsed["leaf_ids"])

    # duplicate in graph
    graph_dupes = sorted({x for x in graph_leaves if graph_leaves.count(x) > 1})
    if graph_dupes:
        fail(f"依赖图 tasks 中重复的叶子: {graph_dupes}")

    missing = sorted(md_set - graph_set)   # 在 tasks.md 但依赖图缺
    extra = sorted(graph_set - md_set)      # 在依赖图但 tasks.md 无
    if missing:
        fail(f"依赖图缺少叶子 (missing): {missing}")
    if extra:
        fail(f"依赖图多出叶子 (extra): {extra}")

    if not (graph_dupes or missing or extra):
        note(f"[OK] 依赖图叶子 = {len(graph_leaves)}，与 tasks.md 叶子集合一致 (无 missing/extra/duplicate)")

    # 5b. wave 依赖只引用更早 wave 的叶子
    dep_violations = []
    for w in waves:
        wn = w.get("wave")
        for dep in w.get("depends_on", []):
            dep_wave = wave_of.get(dep)
            if dep_wave is None:
                dep_violations.append(f"wave {wn} depends_on 未知叶子 {dep}")
            elif dep_wave >= wn:
                dep_violations.append(f"wave {wn} depends_on {dep} (属 wave {dep_wave}，非更早 wave)")
    if dep_violations:
        fail("依赖图 wave 依赖违规:\n    " + "\n    ".join(dep_violations))
    else:
        note("[OK] 依赖图 wave 依赖只引用更早 wave 的叶子")


def check_no_optional_or_askuser(parsed: dict, tasks: str) -> None:
    """
    6. 无 optional (`*`/`\\*`) 任务、无 ask-user / checkpoint 类型任务。

    只按“任务标记约定”判定，不扫描描述性正文:
    - optional: 任务标题行以 `*`/`\\*` 结尾，或含显式括注 `(optional)`/`（可选）`/`(可选)`。
    - checkpoint / ask-user: 任务标题(编号后的动作)以 checkpoint / ask-user / 询问用户 起头。
    这样可避免把技术正文里的 "M1 checkpoint backfill"、"checkpoint/quality snapshot"
    或 11.1 自述文本 "无 optional/ask-user checkpoint" 误判为 optional 任务。
    """
    violations = []

    # 行尾 optional 星号 / 转义星号 / 显式括注
    trailing_star = re.compile(r"(?:\\?\*)\s*$")
    explicit_optional = re.compile(r"\(optional\)|（可选）|\(可选\)", re.IGNORECASE)
    # 标题(编号后)以 checkpoint/ask-user/询问用户 起头 => checkpoint 类型任务
    leading_checkpoint = re.compile(r"^\s*(checkpoint\b|ask[-_ ]?user\b|询问用户|请用户确认)", re.IGNORECASE)
    # 提取叶子标题: "N.M <title>"
    title_re = re.compile(r"^\s*- \[.\]\s+\d+\.\d+\s*(.*)$")
    top_title_re = re.compile(r"^- \[.\]\s+\d+\.\s*(.*)$")

    def title_of(ln: str) -> str:
        m = title_re.match(ln) or top_title_re.match(ln)
        return m.group(1) if m else ln

    all_task_lines = [ln for _, _, ln in parsed["leaves"]] + [ln for _, _, ln in parsed["toplevel"]]
    for ln in all_task_lines:
        title = title_of(ln)
        if trailing_star.search(title):
            violations.append(f"行尾 optional 星号: {ln.strip()[:90]}")
        if explicit_optional.search(title):
            violations.append(f"显式 optional 括注: {ln.strip()[:90]}")
        if leading_checkpoint.search(title):
            violations.append(f"checkpoint/ask-user 类型任务: {ln.strip()[:90]}")

    if violations:
        fail("检测到 optional / ask-user / checkpoint 任务:\n    " + "\n    ".join(violations))
    else:
        note("[OK] 无 optional / ask-user / checkpoint 任务 (全部 55 叶子为必做项)")


# ─── 主函数 ────────────────────────────────────────────────────────────────────

def main() -> int:
    strict = "--strict" in sys.argv

    print("=" * 68)
    print("attachment-ocr-ai-evidence-governance-hardening 三件套追溯与完成守卫")
    print("=" * 68)
    print()

    req = load(REQUIREMENTS_MD, "requirements.md")
    design = load(DESIGN_MD, "design.md")
    tasks = load(TASKS_MD, "tasks.md")

    if req and design and tasks:
        parsed = parse_tasks(tasks)

        # Wave 9 任务文本 (10.x 叶子行)
        wave9_text = "\n".join(ln for _, lid, ln in parsed["leaves"] if lid.startswith("10."))

        print("[1/6] R1–R16 定义 / 任务引用 / design 追溯表...")
        check_requirements_traceability(req, design, tasks)

        print("[2/6] P1–P30 requirements 属性表 / design 同步表...")
        check_properties(req, design)

        print("[3/6] UAT-01～15 requirements / design matrix / Wave 9 覆盖...")
        check_uat(req, design, tasks, wave9_text)

        print("[4/6] 任务计数 (55 叶子 / 11 wave / 11 顶层)...")
        check_task_counts(parsed)

        print("[5/6] Task Dependency Graph (missing/extra/duplicate + wave 依赖)...")
        graph = parse_dependency_graph(tasks)
        if graph is not None:
            check_dependency_graph(graph, parsed)

        print("[6/6] 无 optional / ask-user / checkpoint...")
        check_no_optional_or_askuser(parsed, tasks)
        print()

    # ─── 结果汇总 ──────────────────────────────────────────────────────────────
    if report:
        print("检查明细:")
        for r in report:
            print(f"  {r}")
        print()

    print("=" * 68)
    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  ! {w}")
        print()

    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f_msg in failures:
            print(f"  X {f_msg}")
        print()
        print("结论: FAIL — 未通过三件套追溯与完成检查")
        return 1 if strict else 0
    else:
        print("结论: PASS — 三件套追溯与完成检查全部通过")
        return 0


if __name__ == "__main__":
    sys.exit(main())
