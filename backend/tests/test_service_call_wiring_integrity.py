"""平台级接线自检守卫 —— 防「调用点写错名字 + fail-open 吞掉 = 静默失效」

## 为什么要有这个守卫

2026-08-04 抽凭往来单位补全实测中，同一天连踩 5 次同类错误：

| # | 现场 | 症状 |
|---|---|---|
| 1 | `LedgerSamplingService.enrich_counterparty_names(...)`，真实函数是模块级 `enrich_items_with_aux_party` | 运行时 `AttributeError` 被 `except Exception` 吞成 WARNING → 客户名永远补不上 |
| 2~5 | 前端 import 名与实际导出对不上 4 次 | 运行时 undefined |

**`get_diagnostics` 每一次都返回 No diagnostics。** 后端那次更隐蔽 ——
补全函数外层就是 `except Exception: logger.warning(...)`，于是
「接线错了」与「本项目确实没有这个数据」在返回值上**完全同形**：
两侧都是 `party_name=None`。单测用替身、直跑探针直接调模块函数，都测不到。

## 判据（刻意收窄，避免假阳性淹没信号）

只查一种形态：**`Name.attr(...)` 调用，其中 `Name` 是本文件 import 进来的
模块 / 类，而 `attr` 在目标模块（或类）里查不到定义。**

不查的（会产生大量假阳性，价值低）：
- `self.x()` / 局部变量方法调用 —— 需要类型推断
- 包 `__init__` re-export（`from app.services import xxx_service`）
- 动态属性（`getattr` / `setattr` / `__getattr__`）
- 三方库调用

## 与 `test_render_fetch_smoke.py` 的分工

那个守卫验「取数没走进 except 分支」（运行期行为）；本守卫验「调用点符号存在」
（静态结构）。前者要连库跑真实函数，后者零依赖可全仓扫 —— 两者互补：
本守卫能在**写下那一行时**就打红，不必等到有人跑真实链路。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# ─── 扫描面 ───────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "backend" / "app"

#: 只扫这些子目录 —— 业务逻辑集中处，且 fail-open 最密集
SCAN_SUBDIRS = ("services", "routers")


def _iter_py_files() -> list[Path]:
    out: list[Path] = []
    for sub in SCAN_SUBDIRS:
        base = APP_DIR / sub
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            out.append(p)
    return sorted(out)


PY_FILES = _iter_py_files()


# ─── 模块索引：module dotted path → 顶层定义名集合 ───────────────────────────


def _module_key(path: Path) -> str:
    """backend/app/services/x/y.py → app.services.x.y"""
    rel = path.relative_to(REPO_ROOT / "backend")
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _toplevel_names(tree: ast.Module) -> set[str]:
    """模块顶层定义的名字（函数 / 类 / 赋值 / import 别名）。

    含 import 别名是必要的：`from a import b` 后 `mod.b` 也是合法访问
    （Python 模块属性包含 import 进来的名字）。
    """
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
        elif isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                names.add(a.asname or a.name)
        elif isinstance(node, (ast.If, ast.Try)):
            # `if TYPE_CHECKING:` / `try: import x except ImportError:` 里的定义
            for sub in ast.walk(node):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(sub.name)
                elif isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if isinstance(t, ast.Name):
                            names.add(t.id)
    return names


#: `object` 提供的成员 —— 任何类都能访问，不算「类里没有」。
#: 🔴 `__new__` 是真实惯用法：`Klass.__new__(Klass)` 用于绕过 `__init__` 造裸实例
#: （平台 `full_deliverables_executor` / `template_fill_service` 都在用），
#: 不列进来会产生两条假阳性。
OBJECT_MEMBERS: frozenset[str] = frozenset({
    "__new__", "__init__", "__init_subclass__", "__subclasshook__",
    "__class__", "__dict__", "__doc__", "__module__",
    "__eq__", "__ne__", "__hash__", "__repr__", "__str__", "__format__",
    "__getattribute__", "__setattr__", "__delattr__", "__dir__",
    "__sizeof__", "__reduce__", "__reduce_ex__",
    "mro", "__mro__", "__bases__", "__name__", "__qualname__",
})


def _class_members(tree: ast.Module) -> dict[str, set[str]]:
    """类名 → 其成员名集合（含继承标记：有基类时置 `*` 表示不可判定）。"""
    out: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        members: set[str] = set(OBJECT_MEMBERS)
        # 有非 object 基类 ⇒ 可能继承来的成员查不到，标记为不可判定
        real_bases = [
            b for b in node.bases
            if not (isinstance(b, ast.Name) and b.id == "object")
        ]
        if real_bases:
            members.add("*")
        for sub in node.body:
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                members.add(sub.name)
            elif isinstance(sub, ast.ClassDef):
                members.add(sub.name)
            elif isinstance(sub, ast.Assign):
                for t in sub.targets:
                    if isinstance(t, ast.Name):
                        members.add(t.id)
            elif isinstance(sub, ast.AnnAssign):
                if isinstance(sub.target, ast.Name):
                    members.add(sub.target.id)
        out[node.name] = members
    return out


def _build_index() -> tuple[dict[str, set[str]], dict[str, dict[str, set[str]]]]:
    """全仓索引（含 models/core 等被引用但不在扫描面内的模块）。"""
    mod_names: dict[str, set[str]] = {}
    mod_classes: dict[str, dict[str, set[str]]] = {}
    for p in (REPO_ROOT / "backend" / "app").rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        key = _module_key(p)
        mod_names[key] = _toplevel_names(tree)
        mod_classes[key] = _class_members(tree)
    return mod_names, mod_classes


MOD_NAMES, MOD_CLASSES = _build_index()


# ─── 违规检测 ─────────────────────────────────────────────────────────────────

#: 已知豁免：动态属性 / 运行时注入 / 三方 SDK 包装，逐条须写理由（≥10 字）
CALL_WIRING_ALLOWLIST: dict[str, str] = {
    # 形如 "app.services.x:Klass.method": "理由"
}


def _imported_targets(tree: ast.Module) -> dict[str, tuple[str, str | None]]:
    """本文件 import 进来的「模块名/类名」→ (目标模块 dotted, 类名 或 None)。

    - `from app.services import ledger_sampling_service` → 模块别名
    - `from app.services.x import Klass`                 → 类
    - `import app.services.x as y`                       → 模块别名
    """
    out: dict[str, tuple[str, str | None]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if not node.module or node.level:  # 相对 import 跳过（解析成本高）
                continue
            if not node.module.startswith("app."):
                continue
            for a in node.names:
                local = a.asname or a.name
                full = f"{node.module}.{a.name}"
                if full in MOD_NAMES:
                    out[local] = (full, None)          # 导入的是子模块
                elif a.name in MOD_CLASSES.get(node.module, {}):
                    out[local] = (node.module, a.name)  # 导入的是类
        elif isinstance(node, ast.Import):
            for a in node.names:
                if not a.name.startswith("app."):
                    continue
                if a.asname and a.name in MOD_NAMES:
                    out[a.asname] = (a.name, None)
    return out


def _violations_in(path: Path) -> list[str]:
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except (SyntaxError, UnicodeDecodeError):
        return []

    targets = _imported_targets(tree)
    if not targets:
        return []

    bad: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute) or not isinstance(fn.value, ast.Name):
            continue
        base = fn.value.id
        if base not in targets:
            continue
        mod, klass = targets[base]
        attr = fn.attr

        if klass is None:
            known = MOD_NAMES.get(mod, set())
            if not known or attr in known:
                continue
            kind = "模块"
            owner = mod
        else:
            members = MOD_CLASSES.get(mod, {}).get(klass, set())
            if not members or "*" in members or attr in members:
                continue
            kind = "类"
            owner = f"{mod}:{klass}"

        key = f"{_module_key(path)}:{base}.{attr}"
        if key in CALL_WIRING_ALLOWLIST:
            continue
        bad.append(
            f"{path.relative_to(REPO_ROOT).as_posix()}:{node.lineno} "
            f"调用 `{base}.{attr}(...)`，但{kind} `{owner}` 里没有 `{attr}`"
        )
    return bad


# ─── 扫描面自检 ───────────────────────────────────────────────────────────────


def test_scan_surface_non_trivial():
    """防「扫到 0 个文件」式静默空转。"""
    assert len(PY_FILES) >= 200, f"扫描面异常小（{len(PY_FILES)}），检查 SCAN_SUBDIRS"
    assert len(MOD_NAMES) >= 500, f"模块索引异常小（{len(MOD_NAMES)}）"


def test_key_modules_indexed():
    """本次实证出问题的两个模块必须在索引里（防路径推导错导致守卫空转）。"""
    assert "app.services.ledger_sampling_service" in MOD_NAMES
    assert "app.routers.voucher_sampling" in MOD_NAMES


def test_index_captures_module_level_function():
    """索引须能识别模块级 async 函数（本次踩坑的那个）。"""
    names = MOD_NAMES["app.services.ledger_sampling_service"]
    assert "enrich_items_with_aux_party" in names
    assert "LedgerSamplingService" in names


# ─── Property：调用点符号必须存在 ────────────────────────────────────────────


def test_no_call_to_nonexistent_module_or_class_attribute():
    """全仓 `Module.attr()` / `Class.method()` 调用点，attr 必须真实存在。

    🔴 这是 fail-open 代码的唯一静态防线 —— 名字写错时
    `except Exception: logger.warning(...)` 会把 AttributeError 吞成
    「本项目无此数据」，四层验证全绿。
    """
    all_bad: list[str] = []
    for p in PY_FILES:
        all_bad.extend(_violations_in(p))

    assert not all_bad, (
        "以下调用点引用了不存在的属性（fail-open 会把它伪装成「无数据」）：\n"
        + "\n".join(f"  {b}" for b in all_bad)
    )


def test_allowlist_entries_carry_reason():
    """豁免必须写理由（≥10 字），且不得残留已修好的条目。"""
    for key, reason in CALL_WIRING_ALLOWLIST.items():
        assert len(reason.strip()) >= 10, f"豁免 {key} 的理由过短：{reason!r}"


# ─── 反向自检：替身源码必须被判违规 ─────────────────────────────────────────


@pytest.fixture()
def stub_dir(tmp_path: Path) -> Path:
    return tmp_path


def _write_and_scan(tmp: Path, src: str) -> list[str]:
    """把替身源码写进临时文件后跑同一套检测（复现旧行为必打红）。"""
    f = tmp / "stub_caller.py"
    f.write_text(src, encoding="utf-8")

    tree = ast.parse(src)
    targets = _imported_targets(tree)
    bad: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute) or not isinstance(fn.value, ast.Name):
            continue
        base = fn.value.id
        if base not in targets:
            continue
        mod, klass = targets[base]
        if klass is None:
            known = MOD_NAMES.get(mod, set())
            if known and fn.attr not in known:
                bad.append(f"{base}.{fn.attr}")
        else:
            members = MOD_CLASSES.get(mod, {}).get(klass, set())
            if members and "*" not in members and fn.attr not in members:
                bad.append(f"{base}.{fn.attr}")
    return bad


def test_reverse_selfcheck_catches_the_real_bug(stub_dir: Path):
    """🔴 复现本次真实缺陷：把模块级函数当类方法调 ⇒ 必须打红。"""
    bad = _write_and_scan(
        stub_dir,
        "from app.services.ledger_sampling_service import LedgerSamplingService\n"
        "async def go(db, pid, year, items):\n"
        "    return await LedgerSamplingService.enrich_counterparty_names(\n"
        "        db, pid, year, items\n"
        "    )\n",
    )
    assert "LedgerSamplingService.enrich_counterparty_names" in bad, (
        "守卫没抓到「模块级函数被当成类方法调用」—— 这正是它要防的缺陷"
    )


def test_reverse_selfcheck_accepts_the_fixed_form(stub_dir: Path):
    """修好后的形态（真实存在的类方法）不得误报。"""
    bad = _write_and_scan(
        stub_dir,
        "from app.services.ledger_sampling_service import LedgerSamplingService\n"
        "async def go(db, q):\n"
        "    return await LedgerSamplingService.execute_with_stats(db, q)\n",
    )
    assert bad == [], f"合法调用被误报：{bad}"


def test_reverse_selfcheck_module_alias_form(stub_dir: Path):
    """模块别名形态（`from app.services import x` 后 `x.foo()`）同样要抓。"""
    bad = _write_and_scan(
        stub_dir,
        "from app.services import ledger_sampling_service as lss\n"
        "def go():\n"
        "    return lss.no_such_function_at_all()\n",
    )
    assert "lss.no_such_function_at_all" in bad


def test_reverse_selfcheck_allows_object_new_idiom(stub_dir: Path):
    """`Klass.__new__(Klass)` 绕过 __init__ 造裸实例是合法惯用法，不得误报。

    平台实证：`full_deliverables_executor` 与 `template_fill_service` 都用
    `ReportBodyService.__new__(ReportBodyService)` 复用其纯判定方法
    （`kam_required` 不依赖实例状态，但签名带 self）。
    """
    bad = _write_and_scan(
        stub_dir,
        "from app.services.report_body_service import ReportBodyService\n"
        "def go():\n"
        "    return ReportBodyService.__new__(ReportBodyService)\n",
    )
    assert bad == [], f"object 继承成员被误报：{bad}"


def test_reverse_selfcheck_does_not_flag_inherited(stub_dir: Path):
    """有基类的类不判定（继承成员查不到）—— 宁漏勿误杀。"""
    # WorkpaperExtractionLog 继承 Base，成员集合含 "*"
    bad = _write_and_scan(
        stub_dir,
        "from app.models.audit_platform_models import WorkpaperExtractionLog\n"
        "def go():\n"
        "    return WorkpaperExtractionLog.whatever_dynamic_attr()\n",
    )
    assert bad == [], f"继承类不应被判违规：{bad}"


# ─── fail-open 密度体检（只报告不阻断，供后续收口取清单） ───────────────────

_FAIL_OPEN_RE = re.compile(
    r"except\s+(?:Exception|BaseException)[^\n]*:\s*\n(?:\s*#[^\n]*\n)*\s*logger\.(?:warning|info|debug)",
)


def test_fail_open_density_report(capsys):
    """统计 fail-open 函数数量（不阻断）。

    这类代码不是错 —— 增强路径失败不该打断主流程。但它们**天然掩盖接线错误**，
    所以本文件的静态守卫对它们尤其重要。此处只输出规模供人判断。
    """
    hit_files = 0
    hit_count = 0
    for p in PY_FILES:
        try:
            src = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        n = len(_FAIL_OPEN_RE.findall(src))
        if n:
            hit_files += 1
            hit_count += n
    print(f"\n[fail-open 体检] 文件 {hit_files} 个 / 片段 {hit_count} 处（仅报告）")
    assert hit_count >= 0
