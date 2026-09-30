# -*- coding: utf-8 -*-
"""已提交代码不得 import 未提交模块 —— 「本地全绿 / CI 必挂」那一类的门禁。

═══ 为什么需要这条（2026-09-30 实测，一天内同型缺陷出现两次）═══

**第一次（我自己）**：`test_clear_path_byte_zero_regression.py`（spec
`workpaper-sync-row-deletion-multi-region-propagation` Task 18，596 行）与它的冻结基线
从未 `git add`，而**三个已提交**的测试文件 import 它。本地跑全绿，干净检出会在 import 期
挂 `ModuleNotFoundError`。根因是提交清单按文件名模式（`test_row_deletion_*`）手工枚举，
它不匹配那个模式。

**第二次（跨 6 个 spec）**：`backend/app/services/workpaper_sync/` 下 **13 个**模块同样
从未提交，而**11 个已提交模块**import 它们 —— 其中 `store_mirror.py`（518 行）被
`oo_to_html.py` 与 `adopt_substrate_response.py` 依赖，是**核心生产路径**；而
`workpaper-sync-managed-row-convergence` 的记录里它标着「✅ 已交付」，薄壳转发也确实
入库了，只有被转发的模块没入库 ⇒ 典型的「声明层已完备、接入层是空的」。

这与既有的 `test_ci_declared_gates_exist.py` 是同一形状的两面：那条管「workflow 声明的
路径必须已跟踪」，本条管「代码 import 的模块必须已跟踪」。

═══ 判据形态 ═══

* 用 **AST** 收集 import（不用文本匹配）：`ast.Import` / `ast.ImportFrom`，
  **函数体内的 import 也算** —— 本仓大量用局部 import 打断循环依赖，只扫顶层会漏掉
  `store_mirror`（`oo_to_html.py:2581` 就在函数体内）；
* **外加字符串式引用**（见下）；
* 判「已跟踪」用 `git ls-files`，**不是**「磁盘上存在」—— 后者恒真，判据会空转；
* 缺口清单要求**为空**。这不是拍脑袋的阈值：缺口非空意味着干净检出无法 import，
  没有「允许几个」的余地。

═══ 🔴 只扫 AST 会得到**假的 0** ═══

本判据首版只扫 AST，得「0 缺口」。复核时发现两处口径错，都会让它恒绿：

1. **字符串式动态引用看不见**：`adapters/registry.py` 与
   `adapters/delivered_contracts_ledger.py` 用**字符串常量**登记 provider 模块名
   （`"app.services.workpaper_sync.phase5_a51_cashflow_audit"`）+ `importlib.import_module`
   动态加载 ⇒ AST 里一个 `Import` 节点都没有。实测这样漏掉 **2 个**真缺口
   （`phase5_a51_cashflow_audit` / `phase5_c_control_test`）。
2. **子目录 stem 混比**：`git ls-files` 会返回 `adapters/base.py`，若按 `Path(t).stem`
   与顶层 `glob("*.py")` 比，`base`/`excel`/`registry`/`delivered_contracts_ledger`
   会被算成「已跟踪但磁盘无」⇒ 4 个假差集。必须限定**直接子文件**（路径深度相等）。

⇒ 本判据同时扫两种引用形态，并各配一条变异反证。这是「结构性零必须配变异证明」
   （扫描器报 0 ≠ 真的 0）的直接案例。

🔴 本文件不设豁免名单。若将来真有「故意不提交但被引用」的情形（例如本地实验模块），
   正确做法是让引用侧变成可选（`try/except ImportError` + 明确降级），
   而不是在这里加一行白名单 —— 白名单会让下一个 `store_mirror` 再次隐身。
"""

from __future__ import annotations

import ast
import functools
import re
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]

#: 扫描范围：同目录平铺 import 密集的两个包。
#:
#: 🔴 只扫这两个目录是**刻意收窄**，理由是本仓的「同目录模块名 import」形态集中在这里
#: （`from app.services.workpaper_sync import X` 与 `import test_xxx`）。
#: 下面 `test_scan_scope_is_not_silently_empty` 给它配了反空转断言 ——
#: 哪天目录改名或被清空，判据会打红而不是默默什么都不检查。
SCANNED_DIRS: tuple[str, ...] = (
    "backend/app/services/workpaper_sync",
    "backend/tests/workpaper_sync",
)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout


#: 🔴 `git ls-files` 在本仓返回两万多条，而下面有 6 条判据要用它；
#:    不缓存的话每条各扫一遍全仓（实测把本文件从 20 秒拖到分钟级，一度以为跑挂了）。
#:    缓存按进程生命周期有效 —— 判据运行期间工作树不变，这个假设成立。
@functools.lru_cache(maxsize=1)
def _tracked_files() -> frozenset[str]:
    return frozenset(line for line in _git("ls-files").split("\n") if line)


@functools.lru_cache(maxsize=None)
def _spec_completion_cached(spec_name: str) -> tuple[int, int] | None:
    return _spec_completion(spec_name)


#: 字符串式模块引用（`importlib.import_module` 的实参多为这种形态）。
_STRING_REF_RE = re.compile(
    r"""['"]app\.services\.workpaper_sync\.([A-Za-z_][A-Za-z0-9_]*)['".]"""
)


def _sibling_module_names(path: Path) -> set[str]:
    """该文件引用的**同目录**模块名：AST import ∪ 字符串式模块路径。

    AST 覆盖三种写法（现读本仓实例）：
      * `from app.services.workpaper_sync import store_mirror`
      * `from app.services.workpaper_sync.store_mirror import X`
      * `import test_row_deletion_apply_propagation as AP`（测试目录的平铺 import）

    字符串形态覆盖 registry / ledger 里的动态加载登记（见模块 docstring 第 1 条）。
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:  # pragma: no cover - 坏文件不是本判据的对象
        return set()
    names: set[str] = set(_STRING_REF_RE.findall(text))
    try:
        tree = ast.parse(text)
    except SyntaxError:  # pragma: no cover
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.endswith("workpaper_sync"):
                names |= {a.name for a in node.names}
            else:
                names.add(node.module.rsplit(".", 1)[-1])
        elif isinstance(node, ast.Import):
            names |= {a.name.rsplit(".", 1)[-1] for a in node.names}
    return names


def _direct_child_stems(rel_dir: str, paths: set[str]) -> set[str]:
    """`paths` 里属于 `rel_dir` **直接子文件**的模块名。

    🔴 必须限定深度：`git ls-files` 会返回 `adapters/base.py`，不限定的话它的 stem
    `base` 会与顶层 `glob("*.py")` 混比，凭空造出 4 个假差集（实测）。
    """
    depth = rel_dir.count("/") + 1
    return {
        Path(p).stem
        for p in paths
        if p.startswith(rel_dir + "/") and p.endswith(".py") and p.count("/") == depth
    }


@functools.lru_cache(maxsize=1)
def _gaps_cached() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """`_gaps()` 的可缓存形态（dict 不可 hash，转 tuple）。

    🔴 它对全仓两万多个已提交 `.py` 逐个 AST 解析，是本文件最贵的一步。
    多条判据共用同一份结果，不缓存会重复付这个代价。
    """
    return tuple((k, tuple(v)) for k, v in sorted(_gaps().items()))


def _gaps() -> dict[str, list[str]]:
    """未提交模块 → 引用它的**已提交**文件。

    🔴 引用方扫**全仓已提交 .py**，不只扫同目录 —— 那 2 个字符串式缺口的引用方在
    `adapters/` 子目录里（`registry.py` / `delivered_contracts_ledger.py`），
    只扫同目录会再次漏掉它们。
    """
    tracked = _tracked_files()
    all_tracked_py = sorted(t for t in tracked if t.endswith(".py"))
    untracked_by_dir: dict[str, set[str]] = {}
    for rel_dir in SCANNED_DIRS:
        directory = _REPO / rel_dir
        if not directory.is_dir():  # pragma: no cover - 由 scope 判据兜住
            continue
        on_disk = {p.stem for p in directory.glob("*.py")}
        untracked_by_dir[rel_dir] = on_disk - _direct_child_stems(rel_dir, tracked)

    all_untracked = set().union(*untracked_by_dir.values()) if untracked_by_dir else set()
    if not all_untracked:
        return {}

    out: dict[str, list[str]] = {}
    for rel in all_tracked_py:
        for name in _sibling_module_names(_REPO / rel) & all_untracked:
            out.setdefault(name, []).append(rel)
    return out


@pytest.fixture(scope="module")
def gaps() -> dict[str, list[str]]:
    return {k: list(v) for k, v in _gaps_cached()}


def test_no_committed_file_imports_an_uncommitted_module(
    gaps: dict[str, list[str]]
) -> None:
    """🔴 主判据：缺口必须为空。

    缺口非空 = 干净检出（CI / 新同事 clone / 容器构建）在 import 期就挂，
    而本地因为磁盘上有那个文件而全绿。
    """
    assert gaps == {}, (
        "以下模块**未提交**，却被已提交代码 import ⇒ 干净检出必挂 ModuleNotFoundError：\n"
        + "\n".join(
            f"  {mod}.py  ← {len(sites)} 处：{', '.join(sites[:3])}"
            for mod, sites in sorted(gaps.items())
        )
        + "\n处置：把那些文件 `git add` 入库（它们是已提交代码的硬依赖），"
        "或把 import 侧改成可选依赖并显式降级。"
    )


def test_scan_scope_is_not_silently_empty() -> None:
    """🔴 反空转：扫描范围必须真的有文件，且**真的跟踪到了** import 关系。

    少了这条，目录改名 / 清空 / `SCANNED_DIRS` 写错都会让主判据恒绿。
    """
    tracked = _tracked_files()
    for rel_dir in SCANNED_DIRS:
        assert (_REPO / rel_dir).is_dir(), f"扫描目录不存在：{rel_dir}"
        n = len(
            [t for t in tracked if t.startswith(rel_dir + "/") and t.endswith(".py")]
        )
        assert n > 20, f"{rel_dir} 只扫到 {n} 个已跟踪 .py ⇒ 范围可疑"


def test_scanner_sees_imports_written_inside_function_bodies() -> None:
    """🔴 变异反证①：扫描器必须能看到**函数体内**的 import。

    本仓大量用局部 import 打断循环依赖 —— `oo_to_html.py` 对 `store_mirror` 的 import
    就在函数体内。只扫顶层的扫描器会把那个 518 行的核心缺口判成「无缺口」。
    """
    import tempfile

    sample = (
        "def f():\n"
        "    from app.services.workpaper_sync import made_up_module_xyz\n"
        "    return made_up_module_xyz\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "probe.py"
        p.write_text(sample, encoding="utf-8")
        found = _sibling_module_names(p)
    assert "made_up_module_xyz" in found, (
        f"扫描器看不到函数体内的 import（只得 {sorted(found)}）—— "
        "它会漏掉本仓最常见的那种写法"
    )


def test_scanner_sees_all_three_import_shapes() -> None:
    """🔴 变异反证②：三种写法都要认（现读自本仓真实实例）。"""
    import tempfile

    sample = (
        "from app.services.workpaper_sync import alpha_mod\n"
        "from app.services.workpaper_sync.beta_mod import Thing\n"
        "import gamma_mod as G\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "probe.py"
        p.write_text(sample, encoding="utf-8")
        found = _sibling_module_names(p)
    for expected in ("alpha_mod", "beta_mod", "gamma_mod"):
        assert expected in found, f"漏掉写法：{expected} 不在 {sorted(found)}"


def test_scanner_sees_string_style_dynamic_references() -> None:
    """🔴 变异反证③：扫描器必须看到**字符串式**模块引用。

    `adapters/registry.py` 与 `adapters/delivered_contracts_ledger.py` 用字符串常量
    登记 provider 模块名 + `importlib.import_module` 动态加载。只扫 AST 的扫描器
    在这两处得到的是**假的 0**（实测漏掉 `phase5_a51_cashflow_audit` /
    `phase5_c_control_test` 两个真缺口）。
    """
    import tempfile

    sample = (
        "_ALLOWED = {\n"
        '    "app.services.workpaper_sync.made_up_provider_abc",\n'
        "}\n"
        "def load():\n"
        "    import importlib\n"
        '    return importlib.import_module("app.services.workpaper_sync.made_up_provider_abc")\n'
    )
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "probe.py"
        p.write_text(sample, encoding="utf-8")
        found = _sibling_module_names(p)
    assert "made_up_provider_abc" in found, (
        f"扫描器看不到字符串式动态引用（只得 {sorted(found)}）—— "
        "registry 登记的 provider 会全部隐身"
    )


def test_direct_child_filter_excludes_subpackage_files() -> None:
    """🔴 变异反证④：模块名集合必须只取**直接子文件**。

    不限定深度时 `adapters/base.py` 的 stem `base` 会被当成顶层模块，
    与顶层 `glob` 比出 4 个假差集（实测 `base`/`excel`/`registry`/
    `delivered_contracts_ledger`）。
    """
    rel_dir = SCANNED_DIRS[0]
    tracked = _tracked_files()
    direct = _direct_child_stems(rel_dir, tracked)
    naive = {
        Path(t).stem for t in tracked if t.startswith(rel_dir + "/") and t.endswith(".py")
    }
    subpackage_only = naive - direct
    assert subpackage_only, (
        f"{rel_dir} 下没有任何子目录 .py ⇒ 本条反证空转（无法证明深度过滤起作用）"
    )
    on_disk = {p.stem for p in (_REPO / rel_dir).glob("*.py")}
    assert direct <= on_disk, (
        f"直接子文件过滤后仍有「已跟踪但磁盘无」：{sorted(direct - on_disk)[:5]}"
    )
    assert not (subpackage_only <= on_disk), (
        f"子目录模块名 {sorted(subpackage_only)[:4]} 恰好也都是顶层文件名 ⇒ "
        "本条反证在当前仓库形态下无区分力，需换样本"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 🔴 第二类缺口：spec 标 100% 完成，但它的交付物没入库
#
# 上面那条主判据只管「**被引用**的模块必须已跟踪」。它有一个天然盲区：
# 没有任何已提交代码 import 的模块（孤岛）天然通过 —— 而 `store_mirror` 与
# `phase5_d3_01_adjudication` 都恰好是这种：
#   * store_mirror 被 import，主判据抓到了；
#   * phase5_d3_01_adjudication **没有任何引用方**（`phase5_d3_expansion` 现读确认未引用它），
#     主判据抓不到，而它的 spec `d3-sync-coverage-via-row-table-engine` 是 **17/17 全勾**、
#     requirements 里明文要求「D3-1 审定表接入」，同族 5 个兄弟模块全部已入库 —— 只它漏了。
#
# ⇒ 本节把判据换成另一个轴：**模块自报的 spec 若已 100% 完成，该模块必须已入库**。
#    「spec 说做完了」与「产物在库里」是两件事，本仓一天内出现两次。
#
# 🔴 反过来的情形不判红：spec 还在飞（如 `d567-…` 现算 2/23）时它的模块未入库是**正常**的，
#    那是别人没写完，不是缺陷。现算这类 16 个，全部合法。
# ═══════════════════════════════════════════════════════════════════════════

_SPEC_HEADER_RE = re.compile(r"spec:?\s*`?([a-z0-9][a-z0-9\-]{6,})`?")
_CHECKBOX_RE = re.compile(r"-\s*\[( |x|X)\]")


def _self_reported_spec(path: Path) -> str | None:
    """模块头部自报的 spec 名（本仓约定：docstring 里一行 `spec: xxx`）。"""
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:  # pragma: no cover
        return None
    m = _SPEC_HEADER_RE.search(head)
    return m.group(1) if m else None


def _spec_completion(spec_name: str) -> tuple[int, int] | None:
    """spec 的勾选进度 `(已完成, 总数)`；找不到 tasks.md 返回 None。"""
    base = _REPO / ".kiro" / "specs"
    candidates = [base / spec_name / "tasks.md", *base.glob(f"_archive/**/{spec_name}/tasks.md")]
    for p in candidates:
        if p.is_file():
            text = p.read_bytes().decode("utf-8")
            boxes = _CHECKBOX_RE.findall(text)
            if not boxes:
                return None
            return sum(1 for b in boxes if b.lower() == "x"), len(boxes)
    return None


@functools.lru_cache(maxsize=1)
def _untracked_modules_with_completed_spec() -> list[tuple[str, str, str]]:
    """未入库模块 → (模块名, spec, 进度)，只留 spec 已 100% 完成的。"""
    tracked = _tracked_files()
    out: list[tuple[str, str, str]] = []
    for rel_dir in SCANNED_DIRS:
        directory = _REPO / rel_dir
        if not directory.is_dir():  # pragma: no cover
            continue
        tracked_stems = _direct_child_stems(rel_dir, tracked)
        for path in sorted(directory.glob("*.py")):
            if path.stem in tracked_stems:
                continue
            spec = _self_reported_spec(path)
            if not spec:
                continue
            progress = _spec_completion_cached(spec)
            if progress is None:
                continue
            done, total = progress
            if done == total and total > 0:
                out.append((path.stem, spec, f"{done}/{total}"))
    return out


#: 🔴 「spec 已 100% 但产物未入库」的**已知未决项**（棘轮，只许变短）。
#:
#: 每条：模块名 -> (归属 spec, 为什么现在不能入库)
#:
#: 这张表的存在理由：本条判据抓到的东西有**两种**，处置完全相反 ——
#:
#:   ① **忘了提交**（`store_mirror` / `phase5_d3_01_adjudication`）⇒ `git add` 即可，
#:      本轮已全部入库；
#:   ② **spec 的 tasks.md 假绿**：spec 标 100%，但它的部分判据其实还是红的
#:      （实现没做完）。这些测试**不能**入库 —— CI 的 `backend-tests` 是
#:      `pytest backend/tests/ -x` 全量带 `-x`，一条红就整个 job 中断，影响所有 lane。
#:
#: 判据不能把 ② 误判成 ①（那会诱导人把红测试推上去把 CI 打死），也不能对 ② 闭眼
#: （那就回到「spec 说做完了、其实没有」的假绿）。⇒ 显式登记 + 棘轮。
#:
#: 🔴 每条都必须写明「为什么不能入库」，且下面有一条反向判据检查本表无失效条目
#: （某文件入库后必须从这里删掉）。
UNCOMMITTED_WITH_COMPLETED_SPEC: dict[str, tuple[str, str]] = {
    "test_d3_03_single_html_adjudication": (
        "d3-sync-coverage-via-row-table-engine",
        "实测 3 failed / 16 passed：D3-3 单 HTML 审定表路径未接完。spec 标 17/17 属假绿。",
    ),
    "test_d3_04_dual_zone_shift_and_verify": (
        "d3-sync-coverage-via-row-table-engine",
        "实测失败：ContractSchemaError: contract d3.prepaid_receipts_detail … "
        "⇒ D3-4 双区契约未扩容。",
    ),
    "test_d3_06_offline_materialize_and_verify": (
        "d3-sync-coverage-via-row-table-engine",
        "实测 2 passed / 4 errors：「默认契约应含 D3-6（d36-managed），实得 "
        "['d32-managed']」⇒ 契约受管区未扩容。spec 标 17/17 属假绿。",
    ),
    "test_d3_07_dual_zone_shift_and_verify": (
        "d3-sync-coverage-via-row-table-engine",
        "实测 10 failed：ContractSchemaError: contract d3.prepaid_receipts_detail …"
        "⇒ 契约未扩容。",
    ),
    "test_d3_frontend_managed_sheet_parity": (
        "d3-sync-coverage-via-row-table-engine",
        "实测 4 failed：AttributeError on phase5_d3_expansion（前端受管 sheet 对账所需的"
        "导出还没加）。",
    ),
    "test_d3_property3_4_dual_zone_baseline": (
        "d3-sync-coverage-via-row-table-engine",
        "实测 3 failed：「Property 3 目标（受管区达到 4）未达到」/「Property 4（7）未达到」"
        "—— 这本来就是 spec 里「**先红**」的验收判据。",
    ),
    "test_task5_d3_performance_baseline": (
        "d3-sync-coverage-via-row-table-engine",
        "实测 1 failed：`test_real_registration_path_fails_before_reaching_d3` "
        "DID NOT RAISE —— 注册路径已能走到 D3，该红判据的前提变了，需该 lane 重判。",
    ),
    "test_workbook_propagation_ref_collision": (
        "d3-sync-coverage-via-row-table-engine",
        "实测 25 failed：PropagationDriftError（excel_materialize.py:3313）。"
        "🔴 与其余几份**不同型**，且已排除是删行 lane 引入 —— `git blame` 该区间得 "
        "d76a423c8（别 lane，2026-09-30）+ eed3a34ff（09-06）。归属待该 lane 归因。",
    ),
    "test_frontend_reference_index_memo": (
        "startup-prewarm-event-loop-unblocking",
        "spec 标 10/10，但该文件未入库且未经本轮实跑验证；归 startup lane 自行确认后入库。",
    ),
}


def test_no_completed_spec_has_an_uncommitted_deliverable() -> None:
    """🔴 spec 标 100% 完成 ⇒ 它的产物必须已入库，**或**在棘轮表里登记原因。

    这条抓的是主判据的盲区：**没有引用方**的交付物。实测两例
    （`store_mirror` 有引用方 / `phase5_d3_01_adjudication` 没有），后者只有本条能抓，
    两者都已于本轮入库。

    剩下的进 `UNCOMMITTED_WITH_COMPLETED_SPEC`：它们是「spec 假绿」而不是「忘了提交」，
    推上去会把 CI 打死（`pytest backend/tests/ -x` 一条红即中断）。
    """
    offenders = [
        (m, s, p)
        for m, s, p in _untracked_modules_with_completed_spec()
        if m not in UNCOMMITTED_WITH_COMPLETED_SPEC
    ]
    assert offenders == [], (
        "以下产物未入库，而它们自报的 spec 已标 **100% 完成** ⇒ "
        "「spec 说做完了」与「产物在库里」不一致：\n"
        + "\n".join(f"  {m}.py  spec={s} 进度={p}" for m, s, p in offenders)
        + "\n处置二选一：①若只是忘了提交 ⇒ `git add`；"
        "②若它其实还红（spec 假绿）⇒ 登记进 UNCOMMITTED_WITH_COMPLETED_SPEC 并写明"
        "实测失败形态，**不要**直接推上去（CI 全量带 -x，一条红就整个 job 中断）。"
    )


def test_ratchet_has_no_stale_entries() -> None:
    """🔴 反向：棘轮表里不得有失效条目。

    某文件一旦入库（或被删除），必须从表里删掉 —— 否则这张表会变成一份
    没人知道还管不管用的清单，而那正是它要治的毛病。
    """
    detected = {m for m, _s, _p in _untracked_modules_with_completed_spec()}
    stale = sorted(set(UNCOMMITTED_WITH_COMPLETED_SPEC) - detected)
    assert not stale, (
        f"棘轮表里这些条目已不再命中（可能已入库或已删除）：{stale}\n"
        "请从 UNCOMMITTED_WITH_COMPLETED_SPEC 删掉它们。"
    )


def test_ratchet_entries_carry_a_real_reason() -> None:
    """🔴 每条登记必须写明「为什么不能入库」，只填 spec 名等于没有依据。"""
    for mod, (spec, reason) in UNCOMMITTED_WITH_COMPLETED_SPEC.items():
        assert spec and len(spec) > 6, f"{mod} 的归属 spec 可疑：{spec!r}"
        assert len(reason) > 30, (
            f"{mod} 的原因太短，说不出「为什么不能入库」：{reason!r}"
        )


def test_in_flight_specs_are_not_flagged() -> None:
    """🔴 反向：spec 还在飞时，它的模块未入库是**正常**的，不得被上一条判红。

    少了这条，上一条可能因为「把所有未入库模块都判红」而恰好是绿的
    —— 那样它就不是在测「spec 完成度」这个轴。
    现算：`d567-sync-coverage-via-row-table-engine`（2/23 在飞）有 16 个未入库模块。
    """
    tracked = _tracked_files()
    in_flight: dict[str, list[str]] = {}
    for rel_dir in SCANNED_DIRS:
        directory = _REPO / rel_dir
        if not directory.is_dir():  # pragma: no cover
            continue
        tracked_stems = _direct_child_stems(rel_dir, tracked)
        for path in sorted(directory.glob("*.py")):
            if path.stem in tracked_stems:
                continue
            spec = _self_reported_spec(path)
            if not spec:
                continue
            progress = _spec_completion(spec)
            if progress and progress[0] < progress[1]:
                in_flight.setdefault(spec, []).append(path.stem)

    assert in_flight, (
        "现算没有任何「spec 在飞 + 模块未入库」的样本 ⇒ 上一条判据失去对照，"
        "无法区分「按完成度判」与「把所有未入库模块都判红」"
    )
    flagged = {m for m, _s, _p in _untracked_modules_with_completed_spec()}
    for spec, mods in in_flight.items():
        for m in mods:
            assert m not in flagged, (
                f"{m} 属在飞 spec {spec}（进度 {_spec_completion(spec)}）却被判红 —— "
                "判据把别人没写完的工作当成了缺陷"
            )
