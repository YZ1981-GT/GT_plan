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


def _tracked_files() -> set[str]:
    return {line for line in _git("ls-files").split("\n") if line}


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
    return _gaps()


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
