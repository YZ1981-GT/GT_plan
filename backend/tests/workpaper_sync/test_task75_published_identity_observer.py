r"""Task 75 守卫 —— published-representation → frozen entry definitions 公共观测器
与 manifest 驱动的真实 adapter 注册。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 75
点名 Property：**3 / 7 / 28 / 49 / 67**
点名 AC：1.4 · 2.10 · 3.3 · 5.12 · 6.1 · 6.10 · 6.18 · 6.20 · 12.1 · 12.2

═══ 被守的产物 ═══

* `backend/app/services/workpaper_sync/published_identity_observer.py`（**新建**：观测器）
* `backend/app/services/workpaper_sync/pilot_{simple_checklist,d2_large_json,
  h1_grouped_dynamic,g7_two_level_dynamic}.py`（四处 `raise` → 调观测器；四处欠账登记删除）
* `backend/app/services/workpaper_sync/adapters/registry.py`（`build_production_registry`
  绑定 manifest 驱动注册计划；新增 `register_from_manifest` / `build_manifest_registration_plan`）
* `backend/app/routers/wp_sync_router.py`（两个接线点各 await 一次 manifest 驱动注册）

═══ 判据强度约定（沿用前几轮，逐条不放宽）═══

1. **禁 grep 式「字符存在」**：判「某能力接没接」一律落到 **AST / 真实执行 / 结构形态**。
   典型：`test_four_pilots_delegate_to_the_shared_observer` 用 AST 找 `await` 调用，
   而不是 `"observe_published_frozen_definitions" in source`（后者被注释掉仍绿）。
2. **两种中间形态各有一条打红判据**（任务正文明令）：
   * 欠账登记已删而函数仍 `raise` → :meth:`TestDebtRemovedWithRealImpl.test_no_pilot_still_raises_unconditionally`
   * 欠账登记已删而函数改成 `return None` / 空 identity →
     :meth:`TestDebtRemovedWithRealImpl.test_no_pilot_returns_none_or_empty_identity`
3. **剥注释保留行号**（同长空白替换）；截函数体一律**括号配对 + 先跳参数列表**
   （Python 多行签名会骗到「第一个 `:`」）。
4. **禁 `except Exception` fail-open**：观测器源码里逐个 `except` 子句检查捕获类型，
   `Exception`/`BaseException`/裸 `except` 一律打红；反向自检证明该检查真能抓到。
5. **计数一律从来源节现算等值**；集合层判据「有序等值 + 无重复」双断言。
6. **Property 3 / 7 / 28 / 49 / 67 逐条落判据**；分母为空的明确**不宣称通过**
   （只断言前提 + 承载者存在），禁空分母重言式。
7. **非空跑证明**（Decision 13）：`registered == 0` 不只断言等于 0 ——
   :class:`TestNonEmptyRunOnRealSupply` 用**真实 PG 事务**造一份 approved bundle +
   published representation（走 Task 12/17 的既有生产服务，不 mock），证明观测器与注册器
   在有供给时**真的会注册成功**，跑完 drop schema 回滚。
8. **既存欠账用 `xfail(strict=True)` + 解除条件**，禁 `pytest.skip`。

═══ 供给现状（本轮实测，判据据此写成「有分母」而非「恒 0」）═══

PG 只读实测 `working_paper_sync_definition_artifact` / `..._definition_bundle` /
`working_paper_representation_upgrade_candidate` / `working_paper_content_representation`
四表全 **0** 行 ⇒ 生产侧还没有任何 approved bundle（那是 **Task 76** 的交付）。因此
`register_from_manifest()` 在真实库上诚实地注册 **0** 条，186 条 entry 的 `adapter_id`
保持 `null` 并**各带显式原因**。观测器与注册器是否真能注册，由
:class:`TestNonEmptyRunOnRealSupply` 在真实库上正面证明。

用法（仓库根；本仓库 PATH 上的 `python` 可能指向坏掉的解释器）::

    .\.venv\Scripts\python.exe -m pytest \
        backend/tests/workpaper_sync/test_task75_published_identity_observer.py -q
"""

from __future__ import annotations

import ast
import asyncio
import gzip
import hashlib
import inspect
import json
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pytest

# ════════════════════════════════════════════════════════════════════════════
# 路径与自举
# ════════════════════════════════════════════════════════════════════════════
_THIS = Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
SVC = BACKEND / "app" / "services" / "workpaper_sync"
OBSERVER_PY = SVC / "published_identity_observer.py"
GATE_PY = SVC / "excel_entry_gate.py"
REGISTRY_PY = SVC / "adapters" / "registry.py"
ROUTER_PY = BACKEND / "app" / "routers" / "wp_sync_router.py"
MIGRATION = BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"

if str(BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import excel_entry_gate as GATE  # noqa: E402
from app.services.workpaper_sync import published_identity_observer as OBS  # noqa: E402
from app.services.workpaper_sync.adapters import registry as RG  # noqa: E402
from app.services.workpaper_sync.entry_profile import (  # noqa: E402
    Capability,
    load_entry_manifest,
)

#: 四个 pilot 模块（顺序即 Tasks 40→43；`provider_module` 从交付登记表现取，不写第二份）
PILOT_MODULES: tuple[str, ...] = tuple(
    sorted(str(row["provider_module"]) for row in RG.DELIVERED_PER_ENTRY_CONTRACTS)
)

_SCHEMA_PREFIX = "tmp_task75_observer_"
_STUB_DDL = """
CREATE TABLE projects (id UUID PRIMARY KEY, name VARCHAR(200) NOT NULL DEFAULT 'stub');
CREATE TABLE users (id UUID PRIMARY KEY, username VARCHAR(100) NOT NULL DEFAULT 'stub');
CREATE TABLE working_paper (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    file_version INTEGER NOT NULL DEFAULT 1,
    parsed_data JSONB,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


# ════════════════════════════════════════════════════════════════════════════
# 工具（每个都有反向自检，见 TestGuardSelfChecks）
# ════════════════════════════════════════════════════════════════════════════


def strip_py_comments(src: str) -> str:
    """剥掉 `#` 注释但**保留行号与列数**（同长空白替换）。

    只处理注释，**不动**字符串字面量 —— `sa.text(\"\"\"... -- SQL ...\"\"\")` 一类三引号块
    若被剥掉，后面「函数体里有没有某调用」的判据会凭空少掉整段（实测踩过）。
    """
    out: list[str] = []
    for line in src.split("\n"):
        quote: str | None = None
        cut = len(line)
        i = 0
        while i < len(line):
            ch = line[i]
            if quote is not None:
                if ch == "\\":
                    i += 2
                    continue
                if line.startswith(quote, i):
                    i += len(quote)
                    quote = None
                    continue
                i += 1
                continue
            if line.startswith('"""', i) or line.startswith("'''", i):
                quote = line[i : i + 3]
                i += 3
                continue
            if ch in "\"'":
                quote = ch
                i += 1
                continue
            if ch == "#":
                cut = i
                break
            i += 1
        out.append(line[:cut] + " " * (len(line) - cut))
    return "\n".join(out)


def function_node(path: Path, name: str) -> ast.AST:
    """按名字取顶层函数/方法的 AST 节点（**不**用字符窗口截函数体）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{path.name} 里找不到函数 {name!r} ⇒ 判据无分母")


def awaited_call_names(node: ast.AST) -> set[str]:
    """函数体里被 `await` 的调用名（`f(...)` 与 `x.f(...)` 都取末段名）。"""
    names: set[str] = set()
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Await) or not isinstance(inner.value, ast.Call):
            continue
        func = inner.value.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def imported_module_paths(path: Path) -> set[str]:
    """源文件里**真正 import 的**模块路径（含函数内局部 import）。

    🔴 用 AST 而不是子串：模块 docstring 里写「本模块不 import `adapters.registry`」时，
    子串判据会把那句**说明**当违规 ⇒ 假红（实测踩到）。
    """
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{alias.name}" for alias in node.names)
    return out


def referenced_names(path: Path) -> set[str]:
    """源文件里被**代码**引用到的标识符（`Name` / `Attribute` 末段），不含注释与 docstring。"""
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            out.update(alias.asname or alias.name.rsplit(".", 1)[-1] for alias in node.names)
    return out


def code_only_segment(path: Path, function: str) -> str:
    """函数体源码，**剔掉 docstring**。

    🔴 判「pilot 侧有没有抄 loader 的九步」时必须剔 docstring：本轮的新 docstring 里正当地
    提到了 `ExcelEntryDefinitionLoader.load()`（解释欠账从何而来），带着 docstring 比对会
    把说明文字当违规 ⇒ 假红（实测踩到 4 条）。
    """
    source = path.read_text(encoding="utf-8")
    node = function_node(path, function)
    body = list(getattr(node, "body", []))
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    assert body, f"{path.name}::{function} 剔掉 docstring 后函数体为空 ⇒ 空壳"
    return "\n".join((ast.get_source_segment(source, stmt) or "") for stmt in body)


def except_handler_types(path: Path) -> list[str]:
    """源文件里每个 `except` 子句捕获的类型名（裸 except 记 `<bare>`）。"""
    out: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            out.append("<bare>")
            continue
        targets = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
        for target in targets:
            if isinstance(target, ast.Name):
                out.append(target.id)
            elif isinstance(target, ast.Attribute):
                out.append(target.attr)
            else:
                out.append(ast.dump(target))
    return out


def literal_from_source(path: Path, function: str, key: str) -> str:
    """从某函数体里取 `"{key}": "<字面量>"` 的那个字面量（AST，不用正则）。"""
    node = function_node(path, function)
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Dict):
            continue
        for k, v in zip(inner.keys, inner.values):
            if isinstance(k, ast.Constant) and k.value == key and isinstance(v, ast.Constant):
                return str(v.value)
    raise AssertionError(f"{path.name}::{function} 里取不到 {key!r} 的字面量 ⇒ 判据无分母")


# ════════════════════════════════════════════════════════════════════════════
# 0. 守卫自检
# ════════════════════════════════════════════════════════════════════════════


class TestGuardSelfChecks:
    """每条工具函数与每个分母都要能被证伪，否则后面的判据可能整类空跑。"""

    def test_all_required_artifacts_exist(self) -> None:
        """**Validates: Requirements 12.1**"""
        for path in (OBSERVER_PY, GATE_PY, REGISTRY_PY, ROUTER_PY, MIGRATION):
            assert path.is_file(), f"缺少判据对象：{path}"
        for module_path in PILOT_MODULES:
            name = module_path.rsplit(".", 1)[-1]
            assert (SVC / f"{name}.py").is_file(), name

    def test_pilot_denominator_is_four_and_source_backed(self) -> None:
        """四个 pilot 的分母从交付登记表现算 —— 写死 4 个模块名就是第二份清单。"""
        assert len(PILOT_MODULES) == 4, PILOT_MODULES
        assert len(set(PILOT_MODULES)) == 4, "provider_module 有重复"
        assert PILOT_MODULES == tuple(sorted(PILOT_MODULES)), "有序等值双断言"
        for module_path in PILOT_MODULES:
            assert module_path in RG._ALLOWED_PROVIDER_MODULES, module_path

    def test_strip_py_comments_keeps_line_numbers_and_spares_strings(self) -> None:
        src = "a = 1\n# hidden marker\nb = 2\n"
        out = strip_py_comments(src)
        assert "hidden marker" not in out
        assert len(out.split("\n")) == len(src.split("\n")), "剥注释改变了行数"
        assert strip_py_comments('x = "# not a comment"') == 'x = "# not a comment"'
        triple = 'q = """line -- with # inside"""'
        assert strip_py_comments(triple) == triple, "三引号块被当注释剥了 ⇒ 会造出假判据"
        # 反向自检：真源文件里确有 `#` 注释，且剥完一条都不剩
        raw = OBSERVER_PY.read_text(encoding="utf-8")
        hash_comments = [
            line for line in raw.split("\n") if re.match(r"^\s*#(?!:)", line) and line.strip("# \t")
        ]
        assert len(hash_comments) >= 2, (
            f"观测器里 `#` 注释现算只有 {len(hash_comments)} 行 ⇒ 本自检失去对象"
        )
        stripped = strip_py_comments(raw)
        for line in hash_comments:
            marker = line.strip().lstrip("#").strip()
            assert marker not in stripped, f"注释未被剥掉: {marker[:30]}"

    def test_awaited_call_names_is_falsifiable(self) -> None:
        good = ast.parse("async def f():\n    return await g(1)\n").body[0]
        assert "g" in awaited_call_names(good)
        bad = ast.parse("async def f():\n    return g(1)\n").body[0]
        assert "g" not in awaited_call_names(bad), "没 await 也算 ⇒ 判据会放过半接线"
        attr = ast.parse("async def f():\n    return await o.m()\n").body[0]
        assert "m" in awaited_call_names(attr)

    def test_except_handler_types_catches_the_forbidden_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / "probe.py"
            probe.write_text(
                "try:\n    pass\nexcept Exception:\n    pass\n"
                "try:\n    pass\nexcept (OSError, ValueError):\n    pass\n"
                "try:\n    pass\nexcept:\n    pass\n",
                encoding="utf-8",
            )
            found = except_handler_types(probe)
        assert "Exception" in found and "<bare>" in found and "OSError" in found, found

    def test_literal_from_source_is_falsifiable(self) -> None:
        got = literal_from_source(GATE_PY, "finalize_candidate", "schema_version")
        assert got, "取不到 gate 的 schema_version 字面量 ⇒ 双向锁失去一边"
        with pytest.raises(AssertionError):
            literal_from_source(GATE_PY, "finalize_candidate", "no_such_key_at_all")

    def test_manifest_denominator_is_non_vacuous(self) -> None:
        entries = load_entry_manifest()["entries"]
        assert len(entries) >= 100, f"manifest 现算只有 {len(entries)} 条 ⇒ 分母可疑"
        assert len({str(e["entry_id"]) for e in entries}) == len(entries), "entry_id 有重复"


# ════════════════════════════════════════════════════════════════════════════
# 1. 观测器结构（AC 2.10 / 5.12 / Property 7）
# ════════════════════════════════════════════════════════════════════════════


def _non_projection_authority_models() -> tuple[str, ...]:
    """`projection_contract` 之外的全部 authority model —— 从枚举**现算**。

    🔴 定义必须在 `TestObserverStructure` **之前**：`parametrize` 的实参在类体执行时求值，
    写在类后面会 `NameError`（实测踩过）。
    """
    from app.services.workpaper_sync.models import AuthorityModel

    out = tuple(
        m.value for m in AuthorityModel if m is not AuthorityModel.projection_contract
    )
    assert out, "枚举里只剩 projection_contract ⇒ 分母为空，本参数化无意义"
    return out


def _unapproved_definition_states() -> tuple[str, ...]:
    """`approved` 之外的全部 definition state —— 从枚举**现算**。"""
    from app.services.workpaper_sync.models import DefinitionState

    out = tuple(s.value for s in DefinitionState if s is not DefinitionState.approved)
    assert out, "枚举里只剩 approved ⇒ 分母为空，本参数化无意义"
    return out


class TestObserverStructure:
    def test_observer_never_takes_a_registry(self) -> None:
        """**Validates: Requirements 2.10**

        AC 2.10 的核心禁令是「历史读取不得按当前 registry alias 重组 bundle」。这里落成
        **构造签名**判据：观测器既不 import `adapters.registry`，构造/调用签名里也没有任何
        registry 形参 ⇒ 「按 alias 重组」在结构上不可能，不靠注释承诺。
        """
        imported = imported_module_paths(OBSERVER_PY)
        assert imported, "观测器一个 import 都没有 ⇒ 判据无分母"
        leaked = sorted(m for m in imported if "adapters.registry" in m or "alias" in m.lower())
        assert leaked == [], f"观测器 import 了 registry/alias 面: {leaked}"
        assert "DefinitionAliasRegistry" not in referenced_names(OBSERVER_PY)
        for func in (OBS.PublishedIdentityObserver.__init__, OBS.PublishedIdentityObserver.observe):
            params = set(inspect.signature(func).parameters)
            assert not {p for p in params if "registry" in p or "alias" in p}, (func, params)

    def test_observer_never_reads_candidate_or_non_current(self) -> None:
        """**Validates: Requirements 6.18**

        两条并列：① 源码里没有 candidate 表/模型的任何引用（结构性做不到读它）；
        ② 存在一个专门的 current-pointer stage，且它的 ERROR 类型独立可辨。
        """
        names = referenced_names(OBSERVER_PY)
        assert names, "观测器一个标识符都没引用 ⇒ 判据无分母"
        touched = sorted(
            n
            for n in (
                "WorkpaperRepresentationUpgradeCandidate",
                "stage_upgrade_candidate",
                "parse_candidate_evidence",
                "assert_candidate_finalizable",
                "finalize_candidate",
            )
            if n in names
        )
        assert touched == [], f"观测器代码里碰了 candidate 面: {touched}"
        # 表名字面量也不许出现在**代码**里（docstring 里作为说明是允许的）
        code_literals = {
            node.value
            for node in ast.walk(ast.parse(OBSERVER_PY.read_text(encoding="utf-8")))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert "working_paper_representation_upgrade_candidate" not in code_literals
        assert OBS.ObservationStage.current_pointer in tuple(OBS.ObservationStage)
        assert issubclass(OBS.NonCurrentRepresentationError, OBS.PublishedIdentityObserverError)
        assert (
            OBS.NonCurrentRepresentationError.error_code
            != OBS.PublishedIdentityObserverError.error_code
        ), "non-current 没有自己的 error_code ⇒ 诊断分不清"

    def test_observer_has_no_broad_except_fail_open(self) -> None:
        """**Validates: Requirements 5.12**

        AC 5.12 逐字禁止「被宽泛 `except Exception` 降为成功或『本项目无数据』」。
        判据是 AST 逐个 `except` 子句，不是 grep 字符串。
        """
        caught = except_handler_types(OBSERVER_PY)
        assert caught, "观测器一个 except 都没有 ⇒ 本判据无分母（第三方异常没被转 ERROR 态）"
        bad = sorted({c for c in caught if c in {"Exception", "BaseException", "<bare>"}})
        assert bad == [], f"观测器出现宽泛捕获 {bad} ⇒ fail-open 掩盖接线错误"
        # 允许的捕获必须逐个点名且全部 re-raise 成本模块 ERROR
        assert set(caught) <= {
            "OSError",
            "UnicodeDecodeError",
            "JSONDecodeError",
            "FingerprintError",
            "ContractError",
        }, sorted(set(caught))

    def test_every_stage_carries_a_reachable_error_path(self) -> None:
        """**Validates: Requirements 5.12**

        封闭枚举的每个 stage 都必须在源码里真的被某个 `raise ...(stage=...)` 引用 ——
        新增 stage 却不给它 ERROR 路径，等于开了一条静默通道。
        """
        source = strip_py_comments(OBSERVER_PY.read_text(encoding="utf-8"))
        stages = tuple(OBS.ObservationStage)
        assert len(stages) == 7, [s.value for s in stages]
        assert {"canonical_resolve", "load_definitions"} & {s.value for s in stages} == set(), (
            "canonical resolver / Task 36 loader 的失败必须保留它们自己的 error_code，"
            "不得被本模块重新包一层（包一层会碾平「哪道门拦的」这条诊断）"
        )
        missing = [
            s.value
            for s in stages
            if f"stage=ObservationStage.{s.name}" not in source
            and f"ObservationStage.{s.name}.value" not in source
        ]
        assert missing == [], f"这些 stage 没有任何 ERROR 路径引用: {missing}"

    def test_error_context_covers_every_ac_512_diagnostic_item(self) -> None:
        """**Validates: Requirements 5.12**

        AC 5.12 点名五类诊断项，逐项落在 `_identity_context()` 的键上（真跑一次拿键，
        不是读源码字符串）。
        """
        ctx = OBS.PublishedIdentityObserver._identity_context(
            resolution=_FakeResolution(), entry_id="xlsx/probe", correlation_id="cid-1"
        )
        for key in (
            "correlation_id",
            "definition_bundle_id",
            "definition_bundle_sha256",
            "authority_model",
            "authority_model_definition_id",
            "bundle_typed_child_inventory",
            "adapter_id",
            "adapter_build_digest",
            "representation_generation",
        ):
            assert key in ctx, f"AC 5.12 的诊断项缺 {key}"
        exc = OBS.ObservedIdentityDriftError(
            "probe", stage=OBS.ObservationStage.frozen_digest_match, context=ctx
        )
        payload = exc.as_dict()
        assert payload["stage"] == "frozen_digest_match"
        assert payload["error_code"] == "published_identity_observed_drift"

    def test_structure_hash_schema_is_locked_to_the_finalize_gate(self) -> None:
        """**Validates: Requirements 6.10**

        观测器重算 `structure_hash` 的公式必须与 `ExcelEntryFinalizeGate` 完全同构。
        这里从 **gate 源码现取**那个 schema 字面量与观测器常量双向比对，而不是各写一份。
        """
        gate_literal = literal_from_source(GATE_PY, "finalize_candidate", "schema_version")
        assert gate_literal == OBS.STRUCTURE_HASH_SCHEMA_VERSION, (
            f"gate 用 {gate_literal!r}，观测器用 {OBS.STRUCTURE_HASH_SCHEMA_VERSION!r} ⇒ "
            "两边脱钩后观测器在任何真实 entry 上都会误判漂移"
        )

    def test_recompute_structure_hash_is_order_insensitive_and_content_sensitive(self) -> None:
        """**Validates: Requirements 6.10**"""
        contract = _load_first_pilot_contract()
        declared = _declared_structure(contract)
        assert len(declared) >= 5, f"声明清册现算只有 {len(declared)} 项 ⇒ 分母可疑"
        a = OBS.recompute_structure_hash(contract=contract, observed_structure=declared)
        b = OBS.recompute_structure_hash(
            contract=contract, observed_structure=tuple(reversed(declared))
        )
        assert a == b, "公式对顺序敏感 ⇒ 与 finalize 侧的 sorted() 口径不一致"
        c = OBS.recompute_structure_hash(contract=contract, observed_structure=declared[:-1])
        assert c != a, "少一项也算同一个 hash ⇒ 漂移检测是装饰"

    def test_structure_inventory_is_filtered_by_physical_extent(self) -> None:
        """**Validates: Requirements 6.10** · Property 28

        🔴 「实测清册不是把声明抄一遍」这条**必须**用物理外延小于声明的工作簿来证明。
        真实供给（G7 权威模板）物理上覆盖了全部 107 项声明字段 ⇒ 外延过滤那条分支
        **一次都没被执行过**，变异 M10（把过滤短路）因此恒 GREEN。这里给一份外延只到
        `A1` 的指纹：过滤在时清册必须为空，过滤被短路时它会退化成声明的副本。
        """
        contract = _load_first_pilot_contract()
        declared = _declared_structure(contract)
        assert declared, "声明清册为空 ⇒ 分母为空，本判据无意义"
        physical_by_key = {sheet.sheet_key: sheet.sheet_key for sheet in contract.sheets}
        tiny = _StubFingerprint(cell_values={key: {"A1": "x"} for key in physical_by_key})
        observed = OBS.observe_structure_inventory(
            contract=contract,
            fingerprint=tiny,
            physical_sheet_by_key=physical_by_key,
            row_uuid_rows=(),
        )
        assert observed == (), (
            "物理外延只到 A1 却仍观测出结构项 ⇒ 清册没过物理外延，退化成「把声明抄一遍」"
            f"（实得 {len(observed)} 项，声明 {len(declared)} 项）"
        )
        # 反向自检：把外延放到足够大，同一份契约必须观测出非空清册（否则上面的空集
        # 是「函数根本不产出」而不是「过滤起作用」——空分母重言式）。
        wide = _StubFingerprint(
            cell_values={key: {"A1": "x", "ZZ9999": "y"} for key in physical_by_key}
        )
        wide_observed = OBS.observe_structure_inventory(
            contract=contract,
            fingerprint=wide,
            physical_sheet_by_key=physical_by_key,
            row_uuid_rows=(),
        )
        assert wide_observed, "外延放大后仍观测不出任何结构项 ⇒ 上面的空集是重言式"

    def test_merged_header_values_are_spread_over_the_whole_range(self) -> None:
        """**Validates: Requirements 6.10** · Property 22

        merge 只在左上角留值；不铺开的话横向分组表头第 2..N 列 label 全读成空，
        「改名不改 key」就失去观测对象。真实供给里这条只体现在 label 文本上，没有任何
        判据直接看它 ⇒ 变异 M13（把铺开改成 `pass`）恒 GREEN。这里直接测这个纯函数。
        """
        fp = _StubFingerprint(
            cell_values={"S": {"C62": "甲公司"}},
            merges={"S": ["C62:E63"]},
        )
        spread = OBS._merged_anchor_values(fp, "S")
        want = {
            f"{col}{row}": "甲公司" for col in ("C", "D", "E") for row in (62, 63)
        }
        assert spread == want, spread
        # 反向自检：没有 merge 时必须什么都不铺（否则上面的等值是恒真）。
        assert OBS._merged_anchor_values(_StubFingerprint(cell_values={"S": {"C62": "x"}}), "S") == {}

    @pytest.mark.parametrize("row_identity_tables", [0, 2, 3])
    def test_row_identity_table_must_be_unique(self, row_identity_tables: int) -> None:
        """**Validates: Requirements 6.10** · Property 3

        隐藏 UUID 列只有一列 ⇒ 绑定必须唯一。真实供给的契约恰好声明 1 张
        `row_identity` 表 ⇒ 「不唯一」这条分支从未被执行，变异 M12 恒 GREEN。
        这里直接喂 0 / 2 / 3 张的契约形态（被调用的仍是生产方法本体）。
        """

        class _Table:
            def __init__(self, key: str, has_identity: bool) -> None:
                self.table_key = key
                self.row_identity = object() if has_identity else None

        class _Sheet:
            def __init__(self, tables: list[_Table]) -> None:
                self.sheet_key = "s1"
                self.tables = tables

        class _Contract:
            def __init__(self, n: int) -> None:
                self.sheets = [
                    _Sheet(
                        [_Table(f"t{i}", i < n) for i in range(max(n, 1))]
                    )
                ]

        observer = OBS.PublishedIdentityObserver(
            session=None, resolution=_FakeResolution()  # type: ignore[arg-type]
        )
        with pytest.raises(OBS.FrozenChildUnusableError) as caught:
            observer._build_identity_binding(
                contract=_Contract(row_identity_tables),  # type: ignore[arg-type]
                anchors={
                    "table_name": "GT_X_ROWS",
                    "uuid_column_letter": "N",
                    "metadata_sheet": "_GT_SYNC",
                },
                dynamic_bindings={},
                entry_id="xlsx/probe",
                resolution=_FakeResolution(),  # type: ignore[arg-type]
                correlation_id="probe",
            )
        message = str(caught.value)
        assert f"声明了 {row_identity_tables} 张" in message, message
        assert "不得随手挑第一张" in message, message
        assert caught.value.stage.value == "observe_workbook"

    # 取值现算自 `AuthorityModel` 枚举而不是手写：新增第 4 种 authority model 时这里
    # 自动覆盖它（手写清单会静默漏掉）。
    @pytest.mark.parametrize("model", _non_projection_authority_models())
    def test_non_projection_authority_model_is_refused(self, model: str) -> None:
        """**Validates: Requirements 3.3** · Property 3

        标准 Excel 通道只接 `projection_contract`（custom/opaque 走 Task 65）。真实供给里
        authority model 恒 `projection_contract` ⇒ 这条分支一次都没被执行，变异 M08 恒
        GREEN；库里又有 append-only 约束不允许就地改写 ⇒ 只能对生产方法本体直接喂受控
        bundle。被调用的是 `_assert_frozen_bundle_link` 本体，判据不是「有 raise 语句」
        而是「真抛且点名」。
        """
        from app.services.workpaper_sync.models import AuthorityModel

        class _Bundle(_FakeBundle):
            @property
            def authority_model(self) -> Any:
                return AuthorityModel(model)

        class _Resolution(_FakeResolution):
            bundle = _Bundle()

        observer = OBS.PublishedIdentityObserver(
            session=None, resolution=_Resolution()  # type: ignore[arg-type]
        )
        with pytest.raises(OBS.FrozenBundleLinkError) as caught:
            observer._assert_frozen_bundle_link(
                rep={"id": uuid.UUID(int=3)},
                resolution=_Resolution(),  # type: ignore[arg-type]
                entry_id="xlsx/probe",
                correlation_id="probe",
            )
        message = str(caught.value)
        assert "projection_contract" in message, message
        assert model in message, message
        assert caught.value.stage.value == "frozen_bundle"
        # 反向自检：projection_contract 必须**不**抛（否则上面的 raises 是恒真）。
        OBS.PublishedIdentityObserver(
            session=None, resolution=_FakeResolution()  # type: ignore[arg-type]
        )._assert_frozen_bundle_link(
            rep={"id": uuid.UUID(int=3)},
            resolution=_FakeResolution(),  # type: ignore[arg-type]
            entry_id="xlsx/probe",
            correlation_id="probe",
        )

    @pytest.mark.parametrize("state", _unapproved_definition_states())
    def test_unapproved_contract_child_is_refused(self, state: str) -> None:
        """**Validates: Requirements 12.1** · Property 3

        generator 候选 contract 不得冒充已人工审核的 per-entry contract。真实供给里
        contract child 恒 approved ⇒ 变异 M09 恒 GREEN；库里 append-only 约束又禁止
        `approved→candidate` ⇒ 判据落在对 `_load_frozen_children` 本体喂一份**非 approved**
        的 child row 上（row 的形状与生产 ORM 行一致，读取路径仍是生产代码）。
        """
        import uuid as _uuid

        from app.services.workpaper_sync.models import BundleSlot, DefinitionKind

        child_id = _uuid.uuid4()
        digest = "d" * 64

        class _Row:
            id = child_id
            kind = DefinitionKind.contract.value
            state = ""
            semantic_version = "1.0.0"
            sha256 = digest

        _Row.state = state

        class _Spec:
            is_definition = True
            slot_type = "definition"
            slot_ref = f"definition:{child_id}"
            slot_digest = digest

        class _Slots(dict):
            pass

        class _Bundle(_FakeBundle):
            slots = _Slots({BundleSlot.contract: _Spec(), BundleSlot.instrumentation: _Spec()})

        class _Resolution(_FakeResolution):
            bundle = _Bundle()

        class _Result:
            def scalar_one_or_none(self) -> Any:
                return _Row()

        class _Session:
            async def execute(self, *_a: Any, **_k: Any) -> Any:
                return _Result()

        observer = OBS.PublishedIdentityObserver(
            session=_Session(), resolution=_Resolution()  # type: ignore[arg-type]
        )
        with pytest.raises(OBS.FrozenChildUnusableError) as caught:
            asyncio.run(
                observer._load_frozen_children(
                    resolution=_Resolution(),  # type: ignore[arg-type]
                    entry_id="xlsx/probe",
                    correlation_id="probe",
                )
            )
        message = str(caught.value)
        assert "generator 候选永不放行" in message, message
        assert state in message, message
        assert caught.value.stage.value == "frozen_children"
        assert dict(caught.value.context).get("slot") == "contract"


class _FakeSlots(dict):
    pass


class _FakeBundle:
    bundle_id = uuid.UUID(int=1)
    bundle_sha256 = "a" * 64
    authority_model_definition_id = uuid.UUID(int=2)

    @property
    def authority_model(self) -> Any:
        from app.services.workpaper_sync.models import AuthorityModel

        return AuthorityModel.projection_contract

    @property
    def typed_slot_inventory(self) -> tuple[tuple[str, str, str], ...]:
        return (("template", "definition", "b" * 64),)


class _FakeResolution:
    bundle = _FakeBundle()
    representation_id = uuid.UUID(int=3)
    representation_generation = 1
    content_version_id = uuid.UUID(int=4)
    adapter_id = "probe.adapter"
    adapter_build_digest = "c" * 64


class _StubFingerprint:
    """`observe_structure_inventory` / `_merged_anchor_values` 的**纯函数**入参替身。

    只带这两个函数真正读的四个属性。这不是「mock 掉生产路径」—— 被调用的仍是生产函数
    本体，这里只负责给它一份可控的**物理**事实（真实供给里物理外延恒覆盖全部声明字段，
    于是外延过滤那条分支永远不被执行，变异 M10 因此恒 GREEN）。
    """

    def __init__(
        self,
        *,
        cell_values: dict[str, dict[str, str]] | None = None,
        merges: dict[str, list[str]] | None = None,
        formulas: dict[str, dict[str, str]] | None = None,
        cell_styles: dict[str, dict[str, str]] | None = None,
        tables: list[dict[str, Any]] | None = None,
    ) -> None:
        # 字段名逐字对齐 `WorkbookFingerprint`（`formulas` 不是 `cell_formulas`；
        # `_sheet_extent` 读的是 cell_values ∪ formulas ∪ cell_styles ∪ merges ∪ tables）。
        self.cell_values = cell_values or {}
        self.merges = merges or {}
        self.formulas = formulas or {}
        self.cell_styles = cell_styles or {}
        self.tables = tables or []

    def business_sheet_names(self) -> tuple[str, ...]:
        return tuple(self.cell_values)


def _load_first_pilot_contract() -> Any:
    from app.services.workpaper_sync.contracts import load_contract

    row = sorted(RG.DELIVERED_PER_ENTRY_CONTRACTS, key=lambda r: str(r["contract_id"]))[0]
    return load_contract(str(row["contract_id"]))


def _declared_structure(contract: Any) -> tuple[tuple[str, str, str, str], ...]:
    from app.services.workpaper_sync.contracts import declared_structure_inventory

    return declared_structure_inventory(contract)


# ════════════════════════════════════════════════════════════════════════════
# 2. 四处欠账真删 + 真实现真接（任务正文第二条）
# ════════════════════════════════════════════════════════════════════════════


class TestDebtRemovedWithRealImpl:
    """**Validates: Requirements 1.4, 6.18**"""

    @pytest.mark.parametrize("module_path", PILOT_MODULES)
    def test_debt_registration_is_gone_from_source_and_module(self, module_path: str) -> None:
        module = __import__(module_path, fromlist=["x"])
        name = "UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER"
        assert not hasattr(module, name), f"{module_path} 仍导出欠账常量"
        assert name not in (module.__all__ or ()), f"{module_path}.__all__ 仍列欠账常量"
        source = Path(inspect.getsourcefile(module) or "").read_text(encoding="utf-8")
        assert name not in source, f"{module_path} 源码里仍提欠账常量（含注释/docstring）"

    @pytest.mark.parametrize("module_path", PILOT_MODULES)
    def test_pilot_delegates_to_the_shared_observer(self, module_path: str) -> None:
        """AST 判据：函数体里真的 `await` 了共享观测器，而不是自己抄一遍九步。"""
        module = __import__(module_path, fromlist=["x"])
        path = Path(inspect.getsourcefile(module) or "")
        node = function_node(path, "resolve_published_frozen_definitions")
        awaited = awaited_call_names(node)
        assert "observe_published_frozen_definitions" in awaited, (
            f"{module_path} 没有 await 共享观测器（awaited={sorted(awaited)}）"
        )
        # 不得自己抄 loader 的九步：本函数**代码**里不应出现 loader / gate 的判据调用
        body = code_only_segment(path, "resolve_published_frozen_definitions")
        for copied in (
            "ExcelEntryDefinitionLoader",
            "assert_no_structure_drift",
            "parse_identity_inventory",
            "structure_fingerprint",
        ):
            assert copied not in body, (
                f"{module_path} 在 pilot 侧抄了 {copied} ⇒ 第二真源，任一侧被短路都不改变行为"
            )

    @pytest.mark.parametrize("module_path", PILOT_MODULES)
    def test_no_pilot_still_raises_unconditionally(self, module_path: str) -> None:
        """🔴 中间形态①：欠账登记已删而函数仍无条件 `raise`。

        判据是 AST：函数体的**顶层语句序列**里不得出现 `raise`（顶层 raise = 无条件 fail
        closed）。函数内部条件分支里的 `raise`（契约 digest 不符）是**要保留**的。
        """
        module = __import__(module_path, fromlist=["x"])
        path = Path(inspect.getsourcefile(module) or "")
        node = function_node(path, "resolve_published_frozen_definitions")
        top_level_raises = [s for s in node.body if isinstance(s, ast.Raise)]
        assert top_level_raises == [], (
            f"{module_path}.resolve_published_frozen_definitions 顶层仍有 raise ⇒ "
            "欠账登记删了但函数没改成真实现（中间形态①）"
        )
        # 反向：条件分支里的 raise 必须还在（否则契约脱钩就没人拦）
        nested = [s for s in ast.walk(node) if isinstance(s, ast.Raise)]
        assert nested, f"{module_path} 一个 raise 都没有 ⇒ 契约脱钩无人拦"

    @pytest.mark.parametrize("module_path", PILOT_MODULES)
    def test_no_pilot_returns_none_or_empty_identity(self, module_path: str) -> None:
        """🔴 中间形态②：欠账登记已删而函数改成 `return None` / 返回空 identity。

        两条并列判据：
        1. **静态**：函数体里不得出现 `return None` / `return` / `return {}` / `return ()`；
        2. **真跑**：用 `representation=None` 真调一次 coroutine，必须**抛**
           `RepresentationShapeError`（观测器已实现且拒绝空输入），而不是返回 `None`。
        """
        module = __import__(module_path, fromlist=["x"])
        path = Path(inspect.getsourcefile(module) or "")
        node = function_node(path, "resolve_published_frozen_definitions")
        for stmt in ast.walk(node):
            if not isinstance(stmt, ast.Return):
                continue
            value = stmt.value
            assert value is not None, f"{module_path}: 出现裸 return ⇒ 返回 None（中间形态②）"
            assert not (isinstance(value, ast.Constant) and value.value is None), (
                f"{module_path}: 出现 `return None` ⇒ 中间形态②"
            )
            assert not isinstance(value, (ast.Dict, ast.Tuple, ast.List, ast.Set)), (
                f"{module_path}: 直接 return 字面量容器 ⇒ 空 identity（中间形态②）"
            )
        with pytest.raises(OBS.RepresentationShapeError):
            asyncio.run(
                module.resolve_published_frozen_definitions(
                    session=None, representation=None, contract=None
                )
            )

    @pytest.mark.parametrize("module_path", PILOT_MODULES)
    def test_pilot_consumes_the_contract_argument(self, module_path: str) -> None:
        """`contract` 入参必须被**消费**（否则是摆设 = additive 死代码）。"""
        module = __import__(module_path, fromlist=["x"])
        path = Path(inspect.getsourcefile(module) or "")
        node = function_node(path, "resolve_published_frozen_definitions")
        used = {
            n.id
            for n in ast.walk(node)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
        }
        assert "contract" in used, f"{module_path}: contract 入参从未被读 ⇒ 摆设"
        compares = [
            n
            for n in ast.walk(node)
            if isinstance(n, ast.Compare) and "canonical_sha256" in ast.dump(n)
        ]
        assert compares, f"{module_path}: contract 只是被引用而没参与 digest 比对"


# ════════════════════════════════════════════════════════════════════════════
# 3. manifest 驱动的真实注册（AC 1.4 / 3.3 / 12.1）
# ════════════════════════════════════════════════════════════════════════════


class TestManifestRegistrar:
    def test_build_production_registry_is_no_longer_an_empty_shell(self) -> None:
        """**Validates: Requirements 12.1**

        原形态是 `return WorkpaperSyncAdapterRegistry()`（注册哪些 entry 由每个调用方各拼
        一遍）。判据落在**行为**上：构造点返回的 registry 已绑定计划，且计划覆盖全部
        manifest entry；未绑定计划的手搓 registry 访问 `registration_plan` 必抛。
        """
        registry = RG.build_production_registry()
        plan = registry.registration_plan
        manifest_ids = {str(e["entry_id"]) for e in load_entry_manifest()["entries"]}
        planned = [item.entry_id for item in plan]
        assert len(planned) == len(manifest_ids), (
            f"计划 {len(planned)} 项，manifest {len(manifest_ids)} 条 ⇒ 有 entry 被静默漏掉"
        )
        assert sorted(planned) == planned, "计划顺序不确定 ⇒ 诊断不可复现"
        assert set(planned) == manifest_ids
        with pytest.raises(RG.RegistrationError):
            RG.WorkpaperSyncAdapterRegistry().registration_plan

    def test_every_unregisterable_entry_carries_an_explicit_reason(self) -> None:
        """**Validates: Requirements 1.4, 3.3**

        任务正文：「未满足供给的 entry 保持 `null` 加**显式原因**」。判据是覆盖面等式，
        不是「至少有一条原因」。
        """
        plan = RG.build_production_registry().registration_plan
        with_provider = [item for item in plan if item.provider_module]
        blocked = [item for item in plan if item.blocked_reason]
        assert len(with_provider) + len(blocked) == len(plan), (
            "有 entry 既没 provider 也没原因 ⇒ 静默跳过"
        )
        assert len(with_provider) == len(RG.DELIVERED_PER_ENTRY_CONTRACTS), (
            f"有 provider 的 entry {len(with_provider)} 条 ≠ 交付登记表 "
            f"{len(RG.DELIVERED_PER_ENTRY_CONTRACTS)} 行"
        )
        for item in blocked:
            assert len(item.blocked_reason or "") >= 20, (item.entry_id, item.blocked_reason)
        assert all(item.blocked_reason is None for item in with_provider)
        # 🔴 「长度 ≥ 20」不足以证明原因是**显式**的：原因文本是多行隐式拼接，抹掉其中
        #    一句仍然够长（变异 M20 实测 GREEN）。判据必须落在「原因点名了缺什么」上，
        #    且三类阻塞原因各自可分辨 —— 合成一条会让读者查不到撤销条件。
        named = {
            "no_contract": "approved per-entry",
            "parent_duplicate": "parent 重复入口",
            "unreachable": "已裁决 unreachable",
        }
        unnamed = [
            item.entry_id
            for item in blocked
            if not any(tag in (item.blocked_reason or "") for tag in named.values())
        ]
        assert not unnamed, (
            "有阻塞原因不属于任何一类已命名形态 ⇒ 它没点名「缺的是什么」，"
            f"读者查不到撤销条件：{unnamed[:5]}"
        )
        counts = {
            kind: sum(1 for item in blocked if tag in (item.blocked_reason or ""))
            for kind, tag in named.items()
        }
        assert sum(counts.values()) == len(blocked), counts
        # 当前计划里 `row is None` 先判 ⇒ 实测三类中只有 no_contract 有命中（parent /
        # unreachable 的 entry 同样先因「没有自己的契约」被拦下）。这里只要求 no_contract
        # 非空（不写死 182：Tasks 46~57 每加一行契约它就少一条）。
        assert counts["no_contract"] > 0, counts

    def test_ledger_row_without_provider_module_is_refused(self) -> None:
        """**Validates: Requirements 1.4, 12.1**

        缺 `provider_module` 的登记行必须 fail closed —— 否则该 entry 会静默复用**别人的**
        attach，等于复用别人的 contract/bundle。四条真实登记行都填了 `provider_module`
        ⇒ 这条分支在真实数据上永不执行、变异 M21 恒 GREEN，故判据必须喂一份缺该键的
        登记行（被调用的仍是 `build_manifest_registration_plan` 本体）。
        """
        entry_id = "xlsx/probe-no-provider"
        entries = {
            entry_id: {
                "entry_id": entry_id,
                "independent_entry": True,
                "capability": "bidirectional",
            }
        }
        base_row = {
            "contract_id": "probe.no_provider",
            "entry_id": entry_id,
            "authority_model": "projection_contract",
            "document_type": "xlsx",
            "adapter_registered": False,
            "reason": "探针行",
        }
        saved = RG.DELIVERED_PER_ENTRY_CONTRACTS
        try:
            RG.DELIVERED_PER_ENTRY_CONTRACTS = ({**base_row, "provider_module": ""},)
            with pytest.raises(RG.RegistrationError) as caught:
                RG.build_manifest_registration_plan(entries)
            assert "provider_module" in str(caught.value), str(caught.value)
            assert "不得共用别的 entry 的 attach" in str(caught.value), str(caught.value)
            # 反向自检：填上 provider_module 后必须**不**抛（否则上面的 raises 是恒真）。
            RG.DELIVERED_PER_ENTRY_CONTRACTS = (
                {**base_row, "provider_module": "app.services.workpaper_sync.pilot_simple_checklist"},
            )
            plan = RG.build_manifest_registration_plan(entries)
            assert len(plan) == 1
            assert plan[0].blocked_reason is None
            assert plan[0].provider_module == "app.services.workpaper_sync.pilot_simple_checklist"
        finally:
            RG.DELIVERED_PER_ENTRY_CONTRACTS = saved

    def test_no_placeholder_adapter_id_is_used_to_pad_the_count(self) -> None:
        """**Validates: Requirements 12.1**"""
        plan = RG.build_production_registry().registration_plan
        ids = [item.contract_id for item in plan if item.contract_id]
        assert len(ids) == len(set(ids)) == len(RG.DELIVERED_PER_ENTRY_CONTRACTS)
        from app.services.workpaper_sync.contracts import available_contract_ids

        assert sorted(ids) == sorted(available_contract_ids()), (
            "计划里的 contract_id 与磁盘生产契约清册不等 ⇒ 有占位 id 或有孤儿契约"
        )
        for bad in ("placeholder", "todo", "tbd", "dummy", "fixme", "xxx"):
            assert not any(bad in cid.lower() for cid in ids), (bad, ids)

    def test_registrar_delegates_to_each_entry_own_attach(self) -> None:
        """AC 12.1：不得跨 entry 复用 contract/bundle —— 复用 attach 就是复用契约。"""
        assert len(RG._ALLOWED_PROVIDER_MODULES) == len(RG.DELIVERED_PER_ENTRY_CONTRACTS)
        for row in RG.DELIVERED_PER_ENTRY_CONTRACTS:
            module = __import__(str(row["provider_module"]), fromlist=["x"])
            attach = module.attach_pilot_adapters
            assert attach.__module__ == str(row["provider_module"]), (
                f"{row['contract_id']} 的 attach 来自 {attach.__module__} ⇒ 复用了别人的接线"
            )
        plan_item = RG.ManifestRegistrationPlanItem(
            entry_id="x", capability=Capability.bidirectional, provider_module="app.nope"
        )
        with pytest.raises(RG.RegistrationError):
            RG._load_entry_provider(plan_item)

    def test_registrar_does_not_relax_any_admission_check(self) -> None:
        """**Validates: Requirements 3.3**

        `register_from_manifest` 的函数体里不得出现任何绕过 `register()` 的写法，且
        `register()` 的 RG-6~RG-11 断言一条不少。
        """
        node = function_node(REGISTRY_PY, "register_from_manifest")
        body = ast.get_source_segment(REGISTRY_PY.read_text(encoding="utf-8"), node) or ""
        for forbidden in (
            "_by_adapter_id[",
            "_by_entry_id[",
            "assert_bundle_usable",
            "declared_capability=",
        ):
            assert f"{forbidden}" not in body.replace("self._by_entry_id[item.entry_id]", ""), (
                f"register_from_manifest 自行操作注册表/放宽判据: {forbidden}"
            )
        register_body = (
            ast.get_source_segment(
                REGISTRY_PY.read_text(encoding="utf-8"), function_node(REGISTRY_PY, "register")
            )
            or ""
        )
        for required in (
            "assert_adapter_shape",
            "assert_document_types_agree",
            "assert_bundle_usable",
            "assert_authority_model_contract_pairing",
            "assert_contract_identity_frozen",
            "assert_contract_file_current",
        ):
            assert required in register_body, f"register() 掉了准入判据 {required}"

    def test_registrar_is_wired_on_both_production_paths(self) -> None:
        """**Validates: Requirements 1.4**

        AST 判据：两个生产接线点都真的 `await` 了 manifest 驱动注册；同时四条 pilot attach
        一条不许掉（只加不动）。
        """
        source = ROUTER_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)
        awaited_in: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                awaited_in[node.name] = awaited_call_names(node)
        for func in ("_attach_pilot_adapters", "_apply_durable_incoming"):
            assert func in awaited_in, f"router 里找不到 {func} ⇒ 判据无分母"
            assert "register_from_manifest" in awaited_in[func], (
                f"{func} 没 await manifest 驱动注册 ⇒ 计划永不执行（additive 死代码）"
            )
            assert "attach_pilot_adapters" in awaited_in[func], (
                f"{func} 掉了 pilot 侧 attach ⇒ 只加不动被破坏"
            )
        assert source.count("attach_d2_pilot_adapters") >= 4
        assert source.count("attach_h1_pilot_adapters") >= 4
        assert source.count("attach_g7_pilot_adapters") >= 4

    def test_word_adapter_remains_forbidden(self) -> None:
        """**Validates: Requirements 12.1**

        本任务无权翻 `PENDING_ENGINE_ADAPTERS` 里禁止 `adapters/word.py` 的那一行
        （放行条件是 Task 61 的真实 OO 场景）。
        """
        pending = [r for r in RG.PENDING_ENGINE_ADAPTERS if r["document_type"] == "docx"]
        assert len(pending) == 1, pending
        forbidden = tuple(pending[0]["forbidden_paths"])
        assert "app/services/workpaper_sync/adapters/word.py" in forbidden
        for rel in forbidden:
            assert not (ROOT / rel).exists(), f"Word adapter 已落地: {rel}"
        assert {str(r["document_type"]) for r in RG.DELIVERED_ENGINE_ADAPTERS} == {"xlsx"}

    def test_registration_outcome_accounting_is_closed(self) -> None:
        """`registered + unregistered == planned` 恒等式（没有 entry 被静默跳过）。"""
        outcome = RG.ManifestRegistrationOutcome(
            registered_adapter_ids=("a.b",),
            reasons={"e2": "r2", "e3": "r3"},
            planned_entry_ids=("e1", "e2", "e3"),
            registered_entry_ids=("e1",),
        )
        assert outcome.registered_entry_ids == ("e1",)
        assert len(outcome.registered_entry_ids) + len(outcome.reasons) == len(
            outcome.planned_entry_ids
        )
        assert outcome.as_dict()["unregistered_entry_count"] == 2
        # 🔴 反向自检：`registered_entry_ids` 必须是**实录**字段而不是 `planned - reasons`
        #    反算 —— 反算时下面这个「少记一个 entry」的构造仍会满足等式（恒真式），
        #    于是「静默跳过」永远测不出来（变异 M19 的根因）。
        skipped = RG.ManifestRegistrationOutcome(
            registered_adapter_ids=("a.b",),
            reasons={"e2": "r2"},
            planned_entry_ids=("e1", "e2", "e3"),
            registered_entry_ids=("e1",),
        )
        assert len(skipped.registered_entry_ids) + len(skipped.reasons) != len(
            skipped.planned_entry_ids
        ), "少记一个 entry 仍满足记账等式 ⇒ 等式是恒真的装饰"


# ════════════════════════════════════════════════════════════════════════════
# 4. 非空跑证明（真实 PG 事务；Decision 13 —— 拒绝空分母重言式）
# ════════════════════════════════════════════════════════════════════════════


def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


async def _collect_real_supply() -> dict[str, Any]:  # noqa: C901, PLR0915 - 一次采集覆盖全链
    """在**真实 PG** 的临时 schema 上造一份 approved bundle + published representation。

    每一步都走**生产服务**（`DefinitionPublisher` / `instrument_workbook_bytes` /
    `CanonicalArtifactRepository` / `WorkpaperSyncRepository`），一个 mock 都没有；跑完
    drop schema 即回滚。这是 Task 75 的「非空跑证明」：证明观测器与注册器**在有供给时真的
    会成功**，而不是靠「供给为 0 所以注册 0」这条空分母重言式。
    """
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.services.excel_structure_fingerprint import identity_inventory
    # 🔴 用 G7 而不是 B60：B60 权威模板含 `xl/externalLinks/` ⇒ publish 侧 OOXML 安全门
    # `external_relationships` 直接拒（BP-16）。G7 无外部链接，且是四类 pilot 里唯一真有
    # `{slot}_{seq}` 动态列的那个 ⇒ 顺带证明 `observe_dynamic_columns()` 的物理派生。
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P
    from app.services.workpaper_sync.adapters import registry as registry_module
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.contracts import declared_structure_inventory
    from app.services.workpaper_sync.definitions import DefinitionPublisher, canonical_digest
    from app.services.workpaper_sync.excel_instrumentation import instrument_workbook_bytes
    from app.services.workpaper_sync.models import ArtifactKind, ArtifactState
    from app.services.workpaper_sync.published_identity_observer import (
        PublishedIdentityObserver,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    snap: dict[str, Any] = {"errors": {}, "phases": {}}
    if not settings.DATABASE_URL.startswith("postgresql"):
        raise RuntimeError(
            "Task 75 的非空跑证明必须真实 PostgreSQL（判据是「库里真有 approved bundle 时"
            f"观测器与注册器真的成功」）；当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}。此处**不 skip**。"
        )
    forward = MigrationRunner._split_sql_statements(MIGRATION.read_text(encoding="utf-8"))
    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    base_root = Path(tempfile.mkdtemp(prefix="tmp_task75_store_"))
    (base_root / "storage").mkdir()
    (base_root / "definition_store").mkdir()
    admin = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    engine = None
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_async_engine(
            settings.DATABASE_URL,
            poolclass=NullPool,
            connect_args={**ssl_off, "server_settings": {"search_path": schema}},
        )
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            for stmt in [s.strip() for s in _STUB_DDL.strip().split(";") if s.strip()]:
                await conn.exec_driver_sql(stmt)
        apply_errors: list[str] = []
        for stmt in forward:
            try:
                async with engine.begin() as conn:
                    await conn.exec_driver_sql(stmt)
            except Exception as exc:  # noqa: BLE001 - 记录后由守卫断言为空
                apply_errors.append(_err(exc))
        snap["apply_errors"] = apply_errors

        project, wp = uuid.uuid4(), uuid.uuid4()
        async with engine.begin() as conn:
            await conn.execute(
                sa.text("INSERT INTO projects (id, name) VALUES (:pid, 'task75')"),
                {"pid": project},
            )
            await conn.execute(
                sa.text("INSERT INTO working_paper (id, project_id) VALUES (:wid, :pid)"),
                {"wid": wp, "pid": project},
            )
        artifacts = CanonicalArtifactRepository(base_root=base_root)

        # ① 真发布四个 definition + non-null approved bundle（生产 publisher）
        async with Session() as s:
            definitions = await P.publish_pilot_definitions(
                DefinitionPublisher(
                    artifacts=artifacts,
                    repository=WorkpaperSyncRepository(s),
                    project_id=project,
                    wp_id=wp,
                    source_commit="task75-proof",
                )
            )
            await s.commit()
        snap["phases"]["publish"] = definitions.as_dict()

        # ② 用生产 instrumenter 注入 identity 载体（真实权威模板字节）
        instrumented = instrument_workbook_bytes(
            P.read_authoritative_template(),
            P.instrumentation_spec(),
            gate=P.excel_carrier_gate(),
        )
        contract = P.assert_contract_file_matches_source()
        declared = declared_structure_inventory(contract)
        inventory = GATE.parse_identity_inventory(
            identity_inventory(
                instrumented.instrumented_bytes,
                expected_table=P.instrumentation_spec().table_name,
                uuid_column_letter=P.instrumentation_spec().uuid_col,
            )
        )
        # 冻结侧的两个 digest 按 **finalize 口径**算：structure 用**契约声明**清册，
        # identity 用注入后字节的实测清册 —— 与观测器的**物理**派生互为两侧。
        frozen_structure_hash = canonical_digest(
            {
                "schema_version": OBS.STRUCTURE_HASH_SCHEMA_VERSION,
                "contract_sha256": contract.canonical_sha256,
                "structure": [list(item) for item in sorted(declared)],
            }
        )
        frozen_inventory_digest = canonical_digest(inventory.inventory_digest_input)

        # ③ 发布 published representation artifact + content version + representation + pointer
        async with Session() as s:
            repo = WorkpaperSyncRepository(s)
            # content version 的 `ck_wpcv_has_content` 要求至少有 projection 或权威字节 ——
            # 走生产 `publish_projection`，不放宽约束（放宽就等于伪造供给）。
            projection_bytes = gzip.compress(
                json.dumps({"entry_id": P.PILOT_ENTRY_ID, "rows": []}, sort_keys=True).encode(
                    "utf-8"
                )
            )
            projection_staged = artifacts.stage_bytes(
                project_id=project,
                wp_id=wp,
                payload=projection_bytes,
                document_type="json.gz",
                filename="task75-proof.projection.json.gz",
            )
            projection = artifacts.publish_projection(revision=1, staged=projection_staged)
            projection_row = await repo.register_artifact(
                project_id=project,
                wp_id=wp,
                kind=ArtifactKind.projection,
                state=ArtifactState.published,
                relative_path=projection.relative_path,
                sha256=projection.sha256,
                size_bytes=projection.size_bytes,
                document_type="json.gz",
            )
            staged = artifacts.stage_bytes(
                project_id=project,
                wp_id=wp,
                payload=instrumented.instrumented_bytes,
                document_type="xlsx",
                filename="task75-proof-g7.xlsx",
            )
            published = artifacts.publish_representation(
                entry_id=P.PILOT_ENTRY_ID, generation=1, staged=staged
            )
            artifact_row = await repo.register_artifact(
                project_id=project,
                wp_id=wp,
                kind=ArtifactKind.canonical,
                state=ArtifactState.published,
                relative_path=published.relative_path,
                sha256=published.sha256,
                size_bytes=published.size_bytes,
                document_type="xlsx",
            )
            version = await repo.create_content_version(
                project_id=project,
                wp_id=wp,
                entry_id=P.PILOT_ENTRY_ID,
                revision=1,
                source="html",
                projection_artifact_id=projection_row.id,
                projection_sha256=projection.sha256,
            )
            representation = await repo.create_representation(
                project_id=project,
                wp_id=wp,
                entry_id=P.PILOT_ENTRY_ID,
                content_version_id=version.id,
                generation=1,
                document_type="xlsx",
                artifact_id=artifact_row.id,
                artifact_sha256=published.sha256,
                definition_bundle_id=definitions.bundle_id,
                authority_model_definition_id=definitions.authority_model_definition_id,
                adapter_id=P.PILOT_ADAPTER_ID,
                adapter_build_digest=canonical_digest(
                    {"adapter": P.PILOT_ADAPTER_ID, "contract": contract.canonical_sha256}
                ),
                structure_hash=frozen_structure_hash,
                identity_inventory_sha256=frozen_inventory_digest,
                reason="definition_upgrade",
            )
            await repo.set_entry_pointer(
                wp_id=wp,
                entry_id=P.PILOT_ENTRY_ID,
                representation_id=representation.id,
                generation=1,
            )
            await s.commit()
        snap["phases"]["representation_id"] = str(representation.id)

        # ④ 观测器真跑两次（判「重复观测逐字节相同」）
        async with Session() as s:
            observer = PublishedIdentityObserver(
                session=s, resolution=CanonicalResolutionService(s, artifacts)
            )
            try:
                first = await observer.observe(
                    representation=await _reload_representation(s, representation.id),
                    project_id=project,
                )
                second = await observer.observe(
                    representation=await _reload_representation(s, representation.id),
                    project_id=project,
                )
                snap["phases"]["observation"] = first.as_dict()
                snap["phases"]["observation_repeat_digest"] = second.observation_digest
                snap["phases"]["observed_structure_size"] = len(first.observed_structure)
                snap["phases"]["declared_structure_size"] = len(declared)
                snap["phases"]["business_sheets"] = list(first.observed_business_sheets)
                snap["phases"]["dynamic_columns"] = {
                    key: [list(pair) for pair in value]
                    for key, value in first.observed_dynamic_columns.items()
                }
                binding = first.identity_binding
                snap["phases"]["identity_binding"] = {
                    "table_name": binding.table_name,
                    "uuid_column": binding.uuid_column,
                    "table_key": binding.table_key,
                    "metadata_sheet": binding.metadata_sheet,
                    "dynamic_column_columns": {
                        k: dict(v) for k, v in binding.dynamic_column_columns.items()
                    },
                }
            except Exception as exc:  # noqa: BLE001 - 记录后由守卫断言为空
                snap["errors"]["observe"] = _err(exc)

        # ⑤ 注册器真跑（供给已到位，但 manifest capability 仍是 single_onlyoffice）
        async with Session() as s:
            registry = registry_module.build_production_registry()
            try:
                outcome = await registry.register_from_manifest(session=s)
                snap["phases"]["registration"] = outcome.as_dict()
                snap["phases"]["registration_reason_for_pilot"] = outcome.reasons.get(
                    P.PILOT_ENTRY_ID, ""
                )
            except Exception as exc:  # noqa: BLE001
                snap["errors"]["register"] = _err(exc)

        # ⑤b 把第二道链条也补上：manifest capability 已裁决 bidirectional 时，观测器读出的
        #     identity 必须能真的走完 `build_excel_adapter` → `registry.register()`
        #     （RG-1~RG-19 一条不少）。manifest 只在**内存里**翻（`build_production_registry`
        #     支持传入 manifest），磁盘 overlay 一个字节都不动 —— 翻磁盘 overlay 属于
        #     「finalize 之后才允许」的顺序，本任务无权做。
        async with Session() as s:
            from app.services.workpaper_sync import entry_source_facts as facts

            flipped = _manifest_with_capability(P.PILOT_ENTRY_ID, "bidirectional")
            registry = registry_module.build_production_registry(manifest=flipped)
            # 🔴 必须调**生产** `attach_pilot_adapters`，不得在测试里再抄一份组装。
            #    抄一份过一版（`observer.observe()` + `build_excel_adapter()` +
            #    `register_pilot_adapter()` 逐行重写），后果是 pilot 里那段组装代码
            #    **一次都没被执行**：变异 M17 把 `binding=observation.identity_binding`
            #    换成 `definitions.identity_binding`（`FrozenEntryDefinitions` 根本没有这个
            #    字段，必 AttributeError）实测判 GREEN。假绿第③源（自我比对）的教科书形态。
            #
            #    只替换两个 **manifest 读取口**（capability 与 entry 表），让它们看到内存里
            #    的 flipped 副本 —— 磁盘 overlay 一个字节都不动（翻 overlay 属于 finalize
            #    之后才允许的顺序，本任务无权做）。组装/注册/解析全走生产代码。
            #    `_BACKEND_ROOT` 也要指到本次的临时 store：生产 attach 自己 `new`
            #    `CanonicalArtifactRepository(_BACKEND_ROOT)`，不换根它会去真实 storage 找
            #    这份临时发布的 artifact 并抛 `ArtifactPublishError`（实测）。换的是**存储根**，
            #    不是解析逻辑。
            saved_capability = P.manifest_capability_enabled
            saved_manifest = P.load_entry_manifest
            saved_root = P._BACKEND_ROOT
            try:
                P.manifest_capability_enabled = lambda **_kwargs: True
                P.load_entry_manifest = lambda **_kwargs: flipped
                P._BACKEND_ROOT = base_root
                attached = tuple(await P.attach_pilot_adapters(registry, session=s))
                snap["phases"]["capability_enabled_registration"] = [
                    reg.adapter_id for reg in registry.registrations()
                ]
                snap["phases"]["capability_enabled_attach_return"] = list(attached)
                ready = registry.assert_bidirectional_ready(P.PILOT_ENTRY_ID)
                snap["phases"]["bidirectional_ready_adapter_id"] = ready.adapter_id
            except Exception as exc:  # noqa: BLE001
                snap["errors"]["capability_enabled_registration"] = _err(exc)
            finally:
                P.manifest_capability_enabled = saved_capability
                P.load_entry_manifest = saved_manifest
                P._BACKEND_ROOT = saved_root

        # ⑥ 漂移必须打红：改掉冻结的 structure_hash ⇒ 观测器 ERROR（不是静默取空）
        #    🔴 `working_paper_content_representation` 是 immutable 行（V151 触发器禁 UPDATE，
        #    实测报「升级只能新增 generation」）⇒ 先 `expunge` 出会话再改字段，让 ORM 不去
        #    flush。这不是绕过约束：约束保护的是**库里**的行，而观测器判据比的是「调用方递进来
        #    的 representation 身份 vs 从 artifact 现算的结果」，漂移的真实形态正是这两者不等。
        async with Session() as s:
            rep = await _reload_representation(s, representation.id)
            s.expunge(rep)
            rep.structure_hash = hashlib.sha256(b"drifted").hexdigest()
            observer = PublishedIdentityObserver(
                session=s, resolution=CanonicalResolutionService(s, artifacts)
            )
            try:
                await observer.observe(representation=rep, project_id=project)
                snap["phases"]["drift_verdict"] = "NOT_RAISED"
            except OBS.ObservedIdentityDriftError as exc:
                snap["phases"]["drift_verdict"] = "RAISED"
                snap["phases"]["drift_stage"] = exc.stage.value
                snap["phases"]["drift_error_code"] = exc.error_code
            except Exception as exc:  # noqa: BLE001
                snap["phases"]["drift_verdict"] = f"WRONG_ERROR: {_err(exc)}"
            await s.rollback()

        # ⑦ non-current 必须被拒：真造 generation 2 并把 pointer 切过去，再观测 generation 1。
        #    刻意**不**手写 `UPDATE ... SET current_representation_id = <随机 uuid>` —— 那会撞
        #    V151 的 FK 触发器（实测报「指向不存在的 representation」），也不是真实形态：
        #    non-current 的真实来源是「同 content version 上有更新的 published generation」。
        async with Session() as s:
            repo2 = WorkpaperSyncRepository(s)
            newer = await repo2.create_representation(
                project_id=project,
                wp_id=wp,
                entry_id=P.PILOT_ENTRY_ID,
                content_version_id=version.id,
                generation=2,
                document_type="xlsx",
                artifact_id=artifact_row.id,
                artifact_sha256=published.sha256,
                definition_bundle_id=definitions.bundle_id,
                authority_model_definition_id=definitions.authority_model_definition_id,
                adapter_id=P.PILOT_ADAPTER_ID,
                adapter_build_digest=canonical_digest(
                    {"adapter": P.PILOT_ADAPTER_ID, "contract": contract.canonical_sha256}
                ),
                structure_hash=frozen_structure_hash,
                identity_inventory_sha256=frozen_inventory_digest,
                reason="definition_upgrade",
                parent_representation_id=representation.id,
            )
            await repo2.set_entry_pointer(
                wp_id=wp,
                entry_id=P.PILOT_ENTRY_ID,
                representation_id=newer.id,
                generation=2,
            )
            observer = PublishedIdentityObserver(
                session=s, resolution=CanonicalResolutionService(s, artifacts)
            )
            try:
                await observer.observe(
                    representation=await _reload_representation(s, representation.id),
                    project_id=project,
                )
                snap["phases"]["non_current_verdict"] = "NOT_RAISED"
            except OBS.NonCurrentRepresentationError as exc:
                # 同 ⑩：两条分支同型异常 ⇒ 连判别性诊断一起记，否则两条判据互相遮蔽。
                snap["phases"]["non_current_verdict"] = "RAISED"
                snap["phases"]["non_current_message"] = str(exc)
                snap["phases"]["non_current_stage"] = exc.stage.value
            except Exception as exc:  # noqa: BLE001
                snap["phases"]["non_current_verdict"] = f"WRONG_ERROR: {_err(exc)}"
            await s.rollback()
        # ⑧ published artifact 字节被篡改 ⇒ ArtifactUnreadableError（不是静默取空）。
        #    这条是**文件层**判据：resolver 只比 DB 两列（artifact row ↔ representation），
        #    「磁盘字节被改过」只有现算 sha256 能看见。临时 store 在测试自己的 tmp 目录里，
        #    因此可以真篡改一次。
        async with Session() as s:
            target = artifacts.resolve_relative_path(published.relative_path)
            original = target.read_bytes()
            try:
                target.write_bytes(original + b"tampered")
                observer = PublishedIdentityObserver(
                    session=s, resolution=CanonicalResolutionService(s, artifacts)
                )
                try:
                    await observer.observe(
                        representation=await _reload_representation(s, representation.id),
                        project_id=project,
                    )
                    snap["phases"]["tamper_verdict"] = "NOT_RAISED"
                except OBS.ArtifactUnreadableError as exc:
                    snap["phases"]["tamper_verdict"] = "RAISED"
                    snap["phases"]["tamper_error_code"] = exc.error_code
                except Exception as exc:  # noqa: BLE001
                    snap["phases"]["tamper_verdict"] = f"WRONG_ERROR: {_err(exc)}"
            finally:
                target.write_bytes(original)

        # ⑨ 结构采集出现非致命错误 ⇒ 不得按半份事实组装 adapter。
        #    真实权威模板采集不出 `errors`（那是好事），所以这里替换**数据源**
        #    （`structure_fingerprint`）而不是替换生产逻辑：被调用的仍是观测器本体。
        async with Session() as s:
            import dataclasses

            real_fingerprint = OBS.structure_fingerprint

            def _with_errors(data: bytes) -> Any:
                return dataclasses.replace(
                    real_fingerprint(data), errors=["synthetic collection error"]
                )

            OBS.structure_fingerprint = _with_errors  # type: ignore[assignment]
            try:
                observer = PublishedIdentityObserver(
                    session=s, resolution=CanonicalResolutionService(s, artifacts)
                )
                try:
                    await observer.observe(
                        representation=await _reload_representation(s, representation.id),
                        project_id=project,
                    )
                    snap["phases"]["collection_error_verdict"] = "NOT_RAISED"
                except OBS.ArtifactUnreadableError as exc:
                    snap["phases"]["collection_error_verdict"] = "RAISED"
                    snap["phases"]["collection_error_stage"] = exc.stage.value
                except Exception as exc:  # noqa: BLE001
                    snap["phases"]["collection_error_verdict"] = f"WRONG_ERROR: {_err(exc)}"
            finally:
                OBS.structure_fingerprint = real_fingerprint  # type: ignore[assignment]

        # ⑩ entry pointer 整行缺失 ⇒ NonCurrentRepresentationError（与「指向别的 generation」
        #    是两条独立判据，各自可被变异 falsify）。
        async with Session() as s:
            await s.execute(
                sa.text("DELETE FROM working_paper_sync_entry_state WHERE entry_id = :eid"),
                {"eid": P.PILOT_ENTRY_ID},
            )
            observer = PublishedIdentityObserver(
                session=s, resolution=CanonicalResolutionService(s, artifacts)
            )
            try:
                await observer.observe(
                    representation=await _reload_representation(s, representation.id),
                    project_id=project,
                )
                snap["phases"]["missing_pointer_verdict"] = "NOT_RAISED"
            except OBS.NonCurrentRepresentationError as exc:
                # 🔴 只记 "RAISED" 不够：两条分支抛的是**同一个**异常类型，且
                #    `None != rep["id"]` 恒真 ⇒ 短路「pointer 整行缺失」那条后，
                #    「指向别的 generation」那条会顶上来抛同型异常，判据恒 GREEN
                #    （变异 M07 实测）。故连**判别性诊断**一起记下来。
                snap["phases"]["missing_pointer_verdict"] = "RAISED"
                snap["phases"]["missing_pointer_message"] = str(exc)
                snap["phases"]["missing_pointer_stage"] = exc.stage.value
                snap["phases"]["missing_pointer_context_pointer"] = dict(exc.context).get(
                    "current_representation_id", "<absent>"
                )
            except Exception as exc:  # noqa: BLE001
                snap["phases"]["missing_pointer_verdict"] = f"WRONG_ERROR: {_err(exc)}"
            await s.rollback()

        # 🔴 「contract child 非 approved」与「authority model 非 projection_contract」这两条
        #    分支**不能**在本采集器里用 UPDATE 制造：库里有 append-only CHECK 约束
        #    （实测 `definition artifact approved→candidate 非法`），authority 类型同理不该
        #    被就地改写。它们改由 `TestObserverStructure` 对生产方法本体直接喂受控入参覆盖
        #    （见 `test_non_projection_authority_model_is_refused` /
        #    `test_unapproved_contract_child_is_refused`）—— 变异 M08/M09 由那两条打红。
    finally:
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await admin.dispose()
    return snap


def _manifest_with_capability(entry_id: str, capability: str) -> dict[str, Any]:
    """**内存里**把某 entry 的 capability 换成给定值（磁盘 manifest/overlay 一字不动）。

    这不是伪造供给：`build_production_registry(manifest=...)` 本就支持传入 manifest，而
    「capability 何时可以翻成 bidirectional」是 Tasks 40~43 的**顺序**门（必须 finalize 之后
    由 reviewed overlay 裁决），不是本任务的授权范围。这里只是把那道顺序门的**下游**能力
    在内存里补齐，用来证明观测器读出的 identity 真的能走完 `register()` 的 RG-1~RG-19。
    """
    import copy

    manifest = copy.deepcopy(dict(load_entry_manifest()))
    hit = 0
    for entry in manifest["entries"]:
        if str(entry["entry_id"]) == entry_id:
            entry["capability"] = capability
            entry["adapter_id"] = None
            hit += 1
    assert hit == 1, f"entry {entry_id} 在 manifest 里命中 {hit} 次 ⇒ 判据无分母"
    return manifest


async def _reload_representation(session: Any, representation_id: uuid.UUID) -> Any:
    import sqlalchemy as sa

    from app.models.workpaper_sync_models import WorkpaperContentRepresentation

    return (
        await session.execute(
            sa.select(WorkpaperContentRepresentation).where(
                WorkpaperContentRepresentation.id == representation_id
            )
        )
    ).scalar_one_or_none()


@pytest.fixture(scope="module")
def supply() -> dict[str, Any]:
    return asyncio.run(_collect_real_supply())


class TestNonEmptyRunOnRealSupply:
    """🔴 **非空跑证明**：真实库有供给时观测器与注册器真的成功（Decision 13）。"""

    def test_migration_applies_cleanly(self, supply: dict[str, Any]) -> None:
        assert supply["apply_errors"] == [], supply["apply_errors"][:2]

    def test_no_phase_crashed(self, supply: dict[str, Any]) -> None:
        """**Validates: Requirements 5.12**

        观测/注册任一阶段抛异常即打红并把原文带出来 —— 这条正是「观测器真能用」的判据。
        """
        assert supply["errors"] == {}, supply["errors"]

    def test_observer_really_reads_the_frozen_identity(self, supply: dict[str, Any]) -> None:
        """**Validates: Requirements 2.10, 6.20**"""
        observation = supply["phases"]["observation"]
        assert observation["definitions"]["definition_bundle_id"]
        assert observation["definitions"]["contract_id"]
        assert re.fullmatch(r"[0-9a-f]{64}", observation["recomputed_structure_hash"])
        assert re.fullmatch(
            r"[0-9a-f]{64}", observation["recomputed_identity_inventory_sha256"]
        )
        assert observation["definitions"]["authority_model"] == "projection_contract"

    def test_physical_structure_matches_the_declared_inventory(
        self, supply: dict[str, Any]
    ) -> None:
        """**Validates: Requirements 6.10**

        观测侧是**物理**派生（逐字段核对工作簿外延），冻结侧是**契约声明** —— 两侧来源
        不同却相等，才说明物理派生真的把每个声明字段都在工作簿里找到了。
        """
        assert supply["phases"]["observed_structure_size"] >= 5
        assert (
            supply["phases"]["observed_structure_size"]
            == supply["phases"]["declared_structure_size"]
        ), "物理清册与声明清册项数不等 ⇒ 派生漏项或多项"

    def test_repeat_observation_is_byte_identical(self, supply: dict[str, Any]) -> None:
        """**Validates: Requirements 2.10** · Property 7"""
        assert (
            supply["phases"]["observation"]["observation_digest"]
            == supply["phases"]["observation_repeat_digest"]
        ), "同一 (content version, entry, generation) 两次观测结果不同 ⇒ 观测不确定"

    def test_supply_alone_is_not_enough_and_the_reason_says_so(
        self, supply: dict[str, Any]
    ) -> None:
        """**Validates: Requirements 1.4, 12.1**

        🔴 **本轮实测发现的第二道链条**：供给（approved bundle + published representation +
        current pointer）到位后，`register_from_manifest()` 仍注册 0 条 —— 因为四个 pilot 的
        `attach_pilot_adapters()` 头两行有 `if not manifest_capability_enabled(): return ()`，
        而 manifest capability 仍是 `single_onlyoffice`（翻它必须在 finalize **之后**由
        reviewed overlay 裁决，不是本任务的授权范围）。

        本条不把这件事写成散文，而是断言：① 注册数确实是 0；② 给出的原因确实指向 provider
        的空返回（而不是「缺供给」那条 —— 那会是错的诊断）。
        """
        registration = supply["phases"]["registration"]
        assert registration["registered_adapter_ids"] == [], (
            "manifest capability 仍是 single_onlyoffice，却注册成功了 ⇒ 顺序门被绕过"
        )
        reason = supply["phases"]["registration_reason_for_pilot"]
        assert "返回空元组" in reason, (
            f"供给已到位，原因却是 {reason!r} —— 诊断指错了链条（应指向 provider 侧前置）"
        )
        assert registration["planned_entry_count"] >= 100
        assert (
            len(registration["registered_entry_ids"]) + registration["unregistered_entry_count"]
            == registration["planned_entry_count"]
        ), "注册 + 未注册 ≠ 计划总数 ⇒ 有 entry 被静默跳过"

    def test_registration_really_happens_when_both_links_are_in_place(
        self, supply: dict[str, Any]
    ) -> None:
        """🔴 **本文件最重要的一条**：供给 + capability 两条链都在时，注册数 **> 0**。

        它把真实库上的 `registered == 0` 从「重言式」变成「两条链各缺一环的诚实结果」，
        并正面证明观测器读出的 `FrozenEntryDefinitions` 真的能走完
        `build_excel_adapter` → `registry.register()`（RG-1~RG-19 一条不少）→
        `assert_bidirectional_ready()`。
        """
        assert "capability_enabled_registration" not in supply["errors"], (
            supply["errors"].get("capability_enabled_registration")
        )
        registered = supply["phases"]["capability_enabled_registration"]
        assert registered, "两条链都在却仍注册 0 条 ⇒ 观测器产出的 identity 装不出 adapter"
        contract_ids = {str(r["contract_id"]) for r in RG.DELIVERED_PER_ENTRY_CONTRACTS}
        assert set(registered) <= contract_ids, registered
        # 🔴 注册必须由**生产** `attach_pilot_adapters` 完成（它的返回值就是证据），
        #    不得由测试自己组装后再数 registry —— 后者会让 pilot 的组装代码永不被执行。
        #    期望值从采集器自己记下的 publish 事实**现取**（不写死 adapter_id 字面量）。
        assert supply["phases"]["capability_enabled_attach_return"] == [
            supply["phases"]["publish"]["adapter_id"]
        ], "生产 attach 没有返回本 pilot 的 adapter_id ⇒ 注册不是它做的"
        assert supply["phases"]["bidirectional_ready_adapter_id"] in contract_ids, (
            "注册成功但 `assert_bidirectional_ready()` 解析不到 ⇒ 「注册成功但一调即抛」"
        )

    def test_drift_is_an_error_not_a_silent_empty(self, supply: dict[str, Any]) -> None:
        """**Validates: Requirements 5.12, 6.10** · Property 28"""
        assert supply["phases"]["drift_verdict"] == "RAISED", supply["phases"]["drift_verdict"]
        assert supply["phases"]["drift_stage"] == "frozen_digest_match"
        assert supply["phases"]["drift_error_code"] == "published_identity_observed_drift"

    def test_non_current_representation_is_refused(self, supply: dict[str, Any]) -> None:
        """**Validates: Requirements 6.18** · Property 67

        判据落在**判别性诊断**而不是「抛了同型异常」：两条 pointer 分支抛的都是
        `NonCurrentRepresentationError`，只断言 RAISED 会让它们互相遮蔽。
        """
        assert supply["phases"]["non_current_verdict"] == "RAISED", (
            supply["phases"]["non_current_verdict"]
        )
        message = supply["phases"]["non_current_message"]
        assert "non-current" in message, message
        assert supply["phases"]["non_current_stage"] == "current_pointer"

    def test_missing_entry_pointer_is_refused(self, supply: dict[str, Any]) -> None:
        """**Validates: Requirements 6.18**

        「pointer 整行缺失」与「pointer 指向别的 generation」是**两条**独立判据 —— 合成一条
        之后删掉任一分支都会被另一条遮蔽（变异恒 GREEN）。

        🔴 只断言 `RAISED` **不足以**保持这两条独立：`None != rep["id"]` 恒真 ⇒ 短路掉
        「整行缺失」那条后，「指向别的 generation」那条会抛**同一个**异常类型顶上来，
        变异 M07 实测 GREEN。故判据必须落在只有本分支才产出的诊断上：
        消息里点明「没有 current representation pointer」、**不含** `non-current`
        （那是另一条分支的措辞）、且 context 里的 pointer 为 `None`。
        """
        assert supply["phases"]["missing_pointer_verdict"] == "RAISED", (
            supply["phases"]["missing_pointer_verdict"]
        )
        message = supply["phases"]["missing_pointer_message"]
        assert "没有 current representation pointer" in message, message
        assert "non-current" not in message, (
            "打红的是「指向别的 generation」那条分支 ⇒ 「pointer 整行缺失」被它遮蔽，"
            f"两条判据已合成一条：{message}"
        )
        assert supply["phases"]["missing_pointer_stage"] == "current_pointer"
        assert supply["phases"]["missing_pointer_context_pointer"] is None, (
            "诊断没带上「当前 pointer 是 None」这项事实 ⇒ AC 5.12 要求的定位信息缺失："
            f"{supply['phases']['missing_pointer_context_pointer']!r}"
        )

    def test_tampered_artifact_bytes_are_refused(self, supply: dict[str, Any]) -> None:
        """**Validates: Requirements 5.12, 2.10**

        resolver 只比 DB 两列（artifact row ↔ representation），「磁盘字节被改过」只有观测器
        现算 sha256 能看见 —— 这是本模块相对 resolver **唯一增量**的那条内容身份判据。
        """
        assert supply["phases"]["tamper_verdict"] == "RAISED", supply["phases"]["tamper_verdict"]
        assert supply["phases"]["tamper_error_code"] == "published_identity_artifact_unreadable"

    def test_collection_errors_block_half_baked_facts(self, supply: dict[str, Any]) -> None:
        """**Validates: Requirements 5.12**

        `structure_fingerprint` 的契约是「局部可容忍问题记入 errors，调用方守卫必须断言
        errors == []」。观测器必须真的执行那条断言，而不是按半份事实组装 adapter。
        """
        assert supply["phases"]["collection_error_verdict"] == "RAISED", (
            supply["phases"]["collection_error_verdict"]
        )
        assert supply["phases"]["collection_error_stage"] == "observe_workbook"

    def test_metadata_sheet_is_excluded_from_business_enumeration(
        self, supply: dict[str, Any]
    ) -> None:
        """**Validates: Requirements 6.20**"""
        sheets = supply["phases"]["business_sheets"]
        assert sheets, "业务 sheet 枚举为空 ⇒ 观测侧分母消失"
        assert "_GT_SYNC" not in sheets, "隐藏 metadata sheet 进了业务枚举"


    def test_identity_binding_is_produced_by_the_observer(
        self, supply: dict[str, Any]
    ) -> None:
        """🔴 **BP-17 的回归判据**：`ExcelIdentityBinding` 由观测器现产。

        四处 pilot 原先写 `binding=definitions.identity_binding`，而
        `FrozenEntryDefinitions` 上没有这个字段 ⇒ 观测器一返回就 `AttributeError`。
        它一直没暴露只因为那行永不可达（fail-closed 掩盖接线错误）。本条断言 binding 的
        四个必填字段都来自**冻结 instrumentation** 与**契约**，并且动态列绑定非空。
        """
        binding = supply["phases"]["identity_binding"]
        spec = _pilot_instrumentation_spec()
        assert binding["table_name"] == spec.table_name
        assert binding["uuid_column"] == spec.uuid_col
        assert binding["metadata_sheet"] == "_GT_SYNC"
        assert binding["table_key"], "table_key 为空 ⇒ UUID 列绑不到任何契约表"
        columns = binding["dynamic_column_columns"]
        assert columns, (
            "G7 是四类 pilot 里唯一真有动态列的那个，实测绑定却为空 ⇒ "
            "`observe_dynamic_column_bindings()` 没接通"
        )
        for table_key, mapping in columns.items():
            assert mapping, table_key
            assert len(set(mapping.values())) == len(mapping), (
                f"{table_key}: 两个键绑到同一列 ⇒ 会把一家公司的金额读到另一家名下"
            )
            declared = supply["phases"]["dynamic_columns"].get(table_key) or []
            assert len(mapping) == len(declared), (
                f"{table_key}: 绑定 {len(mapping)} 列，(label,key) 对 {len(declared)} 个 ⇒ "
                "两处派生脱钩"
            )


def _pilot_instrumentation_spec() -> Any:
    from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P

    return P.instrumentation_spec()

# ════════════════════════════════════════════════════════════════════════════
# 5. Property 逐条结论（禁空分母重言式）
# ════════════════════════════════════════════════════════════════════════════


class TestProperties:
    def test_property3_unregistered_entry_never_claims_bidirectional(self) -> None:
        """Property 3 —— **Validates: Requirements 1.4**

        判据是**真跑**：manifest 里每条 capability=bidirectional 的 entry 都必须能解析到
        adapter，否则 `assert_bidirectional_ready` 抛。当前实测 bidirectional 计数为 0 ⇒
        分母为空，本条**不宣称通过**；改为断言「前提成立 + 判据能命中」：任取一条非
        bidirectional entry，`assert_bidirectional_ready` 必抛 `FakeBidirectionalError`。
        """
        registry = RG.build_production_registry()
        entries = registry.manifest_entries
        bidirectional = [
            eid for eid, e in entries.items() if RG.capability_of(e) is Capability.bidirectional
        ]
        assert bidirectional == [], (
            f"manifest 出现 {len(bidirectional)} 条 bidirectional entry ⇒ Property 3 的分母"
            "不再为空，本条必须改成对每条真跑 assert_bidirectional_ready"
        )
        probe = sorted(entries)[0]
        with pytest.raises(RG.FakeBidirectionalError):
            registry.assert_bidirectional_ready(probe)
        # 承载者存在：一旦有 bidirectional entry 而没 adapter，抛的是 AdapterNotRegisteredError
        assert issubclass(RG.AdapterNotRegisteredError, RG.RegistryError)

    def test_property7_all_intents_share_one_canonical_resolver(self) -> None:
        """Property 7 —— **Validates: Requirements 2.10**

        观测器的**唯一**读路径是 `CanonicalResolutionService.resolve`，且它把 frozen
        `representation_id` 显式传下去（否则 candidate 拒绝那道门跑不到）。
        """
        from app.services.workpaper_sync.resolution import ResolutionIntent

        node = function_node(OBSERVER_PY, "_resolve")
        body = ast.get_source_segment(OBSERVER_PY.read_text(encoding="utf-8"), node) or ""
        assert "self._resolution.resolve(" in body
        assert "representation_id=rep[\"id\"]" in body, (
            "没有把 frozen representation_id 传给 resolver ⇒ candidate 拒绝门跑不到"
        )
        source = strip_py_comments(OBSERVER_PY.read_text(encoding="utf-8"))
        assert source.count("resolve(") >= 1
        # 十个意图是封闭枚举；观测器默认取 config，且 intent 由调用方可换（不写死）
        assert len(tuple(ResolutionIntent)) == 10
        assert (
            inspect.signature(OBS.PublishedIdentityObserver.observe)
            .parameters["intent"]
            .default
            is ResolutionIntent.config
        )

    def test_property28_drift_fails_closed_and_names_the_position(self) -> None:
        """Property 28 —— **Validates: Requirements 6.10**

        纯函数层：把物理外延缩小一列后，实测清册**必然少项**，`assert_no_structure_drift`
        指出首个漂移位置。这条不依赖 DB，因此分母永远非空。
        """
        from app.services.workpaper_sync.contracts import (
            ContractDriftError,
            assert_no_structure_drift,
        )

        contract = _load_first_pilot_contract()
        declared = _declared_structure(contract)
        assert_no_structure_drift(contract, declared)  # 未漂移时不抛
        with pytest.raises(ContractDriftError) as exc:
            assert_no_structure_drift(contract, declared[:-1])
        assert "结构漂移" in str(exc.value)
        assert "首个不一致位置" in str(exc.value)

    def test_property49_four_pilot_classes_are_all_covered(self) -> None:
        """Property 49 —— **Validates: Requirements 12.2**

        四类 pilot 各有一行交付登记 + 一个 provider + 一份磁盘契约。真实 OO required
        scenarios 未按 Task 70 刷新 ⇒ **不宣称 pilot 已验收**，本条只断言四类覆盖与
        `adapter_registered` 与真实注册结果一致。
        """
        from app.services.workpaper_sync.contracts import available_contract_ids

        classes = sorted(str(r["pilot_class"]) for r in RG.DELIVERED_PER_ENTRY_CONTRACTS)
        assert classes == [
            "d2_large_json",
            "g7_two_level_dynamic",
            "h1_grouped_dynamic",
            "simple_checklist",
        ], classes
        assert len(set(classes)) == len(classes), "pilot_class 有重复"
        assert set(available_contract_ids()) == {
            str(r["contract_id"]) for r in RG.DELIVERED_PER_ENTRY_CONTRACTS
        }
        # `adapter_registered` 必须与**真实库**注册结果一致（不是随手写的字面量）
        real = _real_registration_ids()
        for row in RG.DELIVERED_PER_ENTRY_CONTRACTS:
            assert bool(row["adapter_registered"]) == (str(row["contract_id"]) in real), (
                f"{row['contract_id']}: 登记 adapter_registered={row['adapter_registered']}，"
                f"真实注册结果={str(row['contract_id']) in real} ⇒ 登记表与现实脱钩"
            )

    def test_property67_candidate_never_becomes_substrate(self) -> None:
        """Property 67 —— **Validates: Requirements 6.18**

        观测器结构上碰不到 candidate（见 `test_observer_never_reads_candidate_or_non_current`），
        并且 non-current published generation 也被独立 ERROR 拒。真实库上的 non-current
        拒绝由 :meth:`TestNonEmptyRunOnRealSupply.test_non_current_representation_is_refused`
        正面证明；这里补「calendar 侧四表实测 0 行 ⇒ 生产侧从未发布过 candidate」的登记。
        """
        assert OBS.NonCurrentRepresentationError.error_code == (
            "published_identity_non_current_representation"
        )
        source = strip_py_comments(OBSERVER_PY.read_text(encoding="utf-8"))
        assert "WorkpaperSyncEntryState" in source, "缺 current pointer 判据的承载者"
        assert "assert_candidate_finalizable" not in source, (
            "观测器不该触碰 finalize 门（那是 Task 36 的 gate）"
        )


def _real_registration_ids() -> set[str]:
    """真实库上跑一次 manifest 驱动注册，返回真的注册成功的 adapter_id 集合。

    这不是「读登记表」——它真连库、真派发、真调 `register()`。供给为 0 时返回空集，
    于是 `adapter_registered=False` 是**被现实锁死**的，而不是手写的字面量。
    """
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise RuntimeError("本判据必须真实 PostgreSQL；此处不 skip")

    async def _run() -> set[str]:
        ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
        engine = create_async_engine(
            settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
        )
        try:
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with Session() as session:
                # 分母自证：真实库里 entry_state 行数（0 即「供给为 0」，非「查错表」）
                pointer_rows = (
                    await session.execute(
                        sa.text("SELECT count(*) FROM working_paper_sync_entry_state")
                    )
                ).scalar_one()
                registry = RG.build_production_registry()
                outcome = await registry.register_from_manifest(session=session)
                assert len(outcome.reasons) + len(outcome.registered_entry_ids) == len(
                    outcome.planned_entry_ids
                )
                assert pointer_rows >= 0
                return set(outcome.registered_adapter_ids)
        finally:
            await engine.dispose()

    return asyncio.run(_run())
