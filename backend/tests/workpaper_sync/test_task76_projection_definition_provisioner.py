r"""Task 76 守卫 —— 生产侧 `projection_contract` definition 链 provisioner 与
candidate 受控 attach 入口（离线判据；连库判据在 `_pg.py`）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 76
点名 Property：**4 / 5 / 10 / 28 / 67**
点名 AC：2.1 · 2.3 · 2.4 · 3.3 · 3.4 · 3.6 · 6.2 · 6.10 · 6.18 · 12.1

═══ 被守的产物 ═══

* `backend/app/services/workpaper_sync/projection_provisioning.py`（**新建**：provisioner
  + 五种伪造供给的 fail-closed 判据 + candidate 受控 attach 服务）
* `backend/app/services/workpaper_sync/repository.py`（新增 `attach_candidate_definitions`
  / `append_candidate_event` —— 补上「只有 create-with-bundle、没有 attach」那一格）
* `backend/migrations/V153__workpaper_representation_candidate_attach_event.sql`（**新建**：
  attach 的 append-only 审计轨）
* `backend/scripts/fix/fix_task76_provision_projection_definitions.py`（**新建**：
  provisioner 的**唯一消费宿主**，`--check` / `--apply`）

═══ 判据强度约定（沿用 Task 75，逐条不放宽）═══

1. **禁 grep 式「字符存在」**：判「某能力接没接」一律落到 **AST / 真实执行 / 结构形态**。
   典型：`test_provisioner_is_consumed_by_the_apply_script` 用 AST 找 `ensure(` 的调用宿主，
   而不是 `"ProjectionDefinitionProvisioner" in source`（写在 docstring 里也绿）。
2. **五种伪造供给各一条判据**，且每条都断言错误消息点出**首个非法 slot** ——
   只断言「抛了异常」会让「①的 uuid 伪造被③的空串判据接住」这类错位判据通过。
3. **禁 `except Exception` fail-open**：逐个 `except` 子句检查捕获类型；反向自检证明该
   检查真能抓到（`TestGuardSelfChecks.test_except_handler_types_catches_the_forbidden_shapes`）。
4. **不得靠放宽 opaque 通道复用**：对 `OpaqueAuthorityProvisioner.ensure()` 做**行为**
   断言（真调一次，projection_contract 必抛），而不是读它的源码有没有 `raise`。
5. **计数一律从来源节现算**；集合层「有序等值 + 无重复」双断言。
6. 分母为空的 Property **不宣称通过**：Property 5 / 10 的「注入失败后 pointer 不悬空」
   需要真库事务，本文件只落结构前提，正面证明在 `_pg.py`。

用法（仓库根；本仓库 PATH 上的 `python` 可能指向坏掉的解释器）::

    .\.venv\Scripts\python.exe -m pytest \
        backend/tests/workpaper_sync/test_task76_projection_definition_provisioner.py -q
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pytest

_THIS = Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
SVC = BACKEND / "app" / "services" / "workpaper_sync"
PROVISIONING_PY = SVC / "projection_provisioning.py"
REPOSITORY_PY = SVC / "repository.py"
WRITER_MIGRATION_PY = SVC / "writer_migration.py"
INSTRUMENTATION_PY = SVC / "excel_instrumentation.py"
MIGRATION_V151 = BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"
MIGRATION_V153 = (
    BACKEND / "migrations" / "V153__workpaper_representation_candidate_attach_event.sql"
)
APPLY_SCRIPT = BACKEND / "scripts" / "fix" / "fix_task76_provision_projection_definitions.py"

if str(BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import definitions as D  # noqa: E402
from app.services.workpaper_sync import models as M  # noqa: E402
from app.services.workpaper_sync import projection_provisioning as PP  # noqa: E402
from app.services.workpaper_sync.adapters import registry as RG  # noqa: E402

#: 四个 pilot provider（分母从交付登记表**现算**，不写第二份清单）。
PILOT_PROVIDERS: tuple[str, ...] = tuple(
    sorted(str(row["provider_module"]) for row in RG.DELIVERED_PER_ENTRY_CONTRACTS)
)
#: 本 provisioner 一次完整发布应当覆盖的五段（authority model 不在 PUBLISH_DAG 上，
#: 但它是 bundle 的必填 child，故五段而不是四段）。
EXPECTED_STAGES: frozenset[str] = frozenset(
    {"authority_model", "template", "instrumentation", "contract", "bundle"}
)
#: provisioner **不得**触碰的写入面（AC 3.4 / 6.18 / Property 67）。
FORBIDDEN_WRITE_SURFACES: tuple[str, ...] = (
    "set_entry_pointer",
    "create_representation",
    "create_content_version",
    "finalize_candidate",
    "bump_content_revision",
)


# ════════════════════════════════════════════════════════════════════════════
# 工具（AST / 剥注释；与 Task 75 同款，判据不靠字符窗口）
# ════════════════════════════════════════════════════════════════════════════


def strip_py_comments(src: str) -> str:
    """剥掉 `#` 注释但**保留行号与列数**（同长空白替换），不动字符串字面量。"""
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
    """按名字取函数/方法的 AST 节点（**不**用字符窗口截函数体）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{path.name} 里找不到函数 {name!r} ⇒ 判据无分母")


def called_names(node: ast.AST) -> set[str]:
    """节点内被调用的名字（`f(...)` 与 `x.f(...)` 都取末段）。"""
    out: set[str] = set()
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        func = inner.func
        if isinstance(func, ast.Name):
            out.add(func.id)
        elif isinstance(func, ast.Attribute):
            out.add(func.attr)
    return out


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


def code_only_source(path: Path) -> str:
    """整文件源码剥掉 `#` 注释后的文本（docstring 仍在，故只用于**存在**类判据的补充）。"""
    return strip_py_comments(path.read_text(encoding="utf-8"))


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _valid_slots() -> dict[M.BundleSlot, Any]:
    """三个 typed definition slot 全非空的合法声明（伪造判据的对照组）。"""
    return {
        slot: D.definition_slot_spec(
            slot, definition_id=uuid.uuid4(), definition_sha256=_d(f"t76-{slot.value}")
        )
        for slot in M.BundleSlot
    }


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _assert_authentic(
    *,
    slots: Any,
    contract_payload: dict[str, Any] | None = None,
    session: Any = None,
    entry_id: str = "xlsx/b60/gt-b60-bundle",
) -> Any:
    """调真判据函数；`session=None` 证明拒绝发生在**任何 DB 访问之前**。"""
    payload = contract_payload if contract_payload is not None else _reviewed_contract_payload()
    return await PP.assert_projection_supply_authentic(
        session=session,
        entry_id=entry_id,
        authority_model=M.AuthorityModel.projection_contract,
        authority_model_definition_sha256=_d("t76-authority"),
        slots=slots,
        contract_payload=payload,
    )


def _reviewed_contract_payload() -> dict[str, Any]:
    """已人工审核的 contract canonical payload（`contract_id` 与登记表现取，不写死）。"""
    row = next(
        r
        for r in RG.DELIVERED_PER_ENTRY_CONTRACTS
        if str(r.get("entry_id")) == "xlsx/b60/gt-b60-bundle"
    )
    return {"review_status": "reviewed", "contract_id": str(row["contract_id"])}


# ════════════════════════════════════════════════════════════════════════════
# 0. 守卫自检
# ════════════════════════════════════════════════════════════════════════════


class TestGuardSelfChecks:
    """每个分母与每条工具函数都要能被证伪，否则后面的判据可能整类空跑。"""

    def test_all_required_artifacts_exist(self) -> None:
        """**Validates: Requirements 12.1**"""
        for path in (
            PROVISIONING_PY,
            REPOSITORY_PY,
            WRITER_MIGRATION_PY,
            MIGRATION_V151,
            MIGRATION_V153,
            APPLY_SCRIPT,
        ):
            assert path.is_file(), f"缺少判据对象：{path}"

    def test_pilot_denominator_is_four_and_source_backed(self) -> None:
        assert len(PILOT_PROVIDERS) == 4, PILOT_PROVIDERS
        assert len(set(PILOT_PROVIDERS)) == 4, "provider_module 有重复"
        assert PILOT_PROVIDERS == tuple(sorted(PILOT_PROVIDERS)), "有序等值双断言"
        for module_path in PILOT_PROVIDERS:
            assert module_path in RG._ALLOWED_PROVIDER_MODULES, module_path

    def test_strip_py_comments_keeps_line_numbers_and_spares_strings(self) -> None:
        src = "a = 1\n# hidden marker\nb = 2\n"
        out = strip_py_comments(src)
        assert "hidden marker" not in out
        assert len(out.split("\n")) == len(src.split("\n")), "剥注释改变了行数"
        assert strip_py_comments('x = "# not a comment"') == 'x = "# not a comment"'
        triple = 'q = """line -- with # inside"""'
        assert strip_py_comments(triple) == triple, "三引号块被当注释剥了 ⇒ 会造出假判据"
        raw = PROVISIONING_PY.read_text(encoding="utf-8")
        hash_comments = [
            line
            for line in raw.split("\n")
            if re.match(r"^\s*#(?!:)", line) and line.strip("# \t")
        ]
        assert len(hash_comments) >= 2, (
            f"provisioner 里 `#` 注释现算只有 {len(hash_comments)} 行 ⇒ 本自检失去对象"
        )
        stripped = strip_py_comments(raw)
        for line in hash_comments:
            marker = line.strip().lstrip("#").strip()
            assert marker not in stripped, f"注释未被剥掉: {marker[:30]}"

    def test_called_names_is_falsifiable(self) -> None:
        good = ast.parse("def f():\n    return g(1)\n").body[0]
        assert "g" in called_names(good)
        bad = ast.parse("def f():\n    return g\n").body[0]
        assert "g" not in called_names(bad), "只是引用也算调用 ⇒ 判据会误报"
        attr = ast.parse("def f():\n    return o.m()\n").body[0]
        assert "m" in called_names(attr)

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

    def test_function_node_is_falsifiable(self) -> None:
        assert function_node(PROVISIONING_PY, "load_projection_supply") is not None
        with pytest.raises(AssertionError):
            function_node(PROVISIONING_PY, "no_such_function_at_all")

    def test_valid_slots_are_actually_accepted(self) -> None:
        """对照组必须**通过** —— 否则五条伪造判据可能只是「什么都拒」。"""
        normalized = D.normalize_bundle_slot_map(_valid_slots())
        M.validate_bundle_slots(
            authority_model=M.AuthorityModel.projection_contract,
            authority_model_definition_sha256=_d("t76-authority"),
            slots=normalized,
        )
        assert set(normalized) == set(M.BundleSlot)
        assert all(spec.is_definition for spec in normalized.values())


# ════════════════════════════════════════════════════════════════════════════
# 1. 五种伪造供给各一条 fail-closed 判据（AC 2.3 / 3.3 / 6.2 / 6.10 / Property 28）
# ════════════════════════════════════════════════════════════════════════════


class TestForgedSupplyIsFailClosed:
    """五种形态各一条，且每条都要求错误消息点出**首个非法 slot**。"""

    def test_form1_forged_definition_uuid_is_rejected_by_db_readback(self) -> None:
        """① 自造 uuid：判据是 DB 现读 ⇒ 无 session 时**不得**静默放行。

        **Validates: Requirements 6.10**
        """
        node = function_node(PROVISIONING_PY, "assert_projection_supply_authentic")
        calls = called_names(node)
        assert "validate_definition_child" in calls, (
            "① 的判据必须委托 `models.validate_definition_child`（kind/state/digest 三项），"
            "本函数只负责把 DB 行读出来"
        )
        assert "select" in calls, "① 必须真查 `working_paper_sync_definition_artifact`"
        # `session=None` 时判据只可能**报错**，绝不可能通过：这就是「不靠 DB 也不放行」。
        with pytest.raises((AttributeError, TypeError)):
            _run(_assert_authentic(slots=_valid_slots(), session=None))

    def test_form2_typed_null_marker_cannot_impersonate_a_contract(self) -> None:
        """② 在 `projection_contract` 的 contract slot 用版本化 typed null marker 冒充。

        **Validates: Requirements 2.3**
        """
        slots = _valid_slots()
        slots[M.BundleSlot.contract] = D.marker_slot_spec(M.BundleSlot.contract)
        assert not D.normalize_bundle_slot_map(slots)[M.BundleSlot.contract].is_definition
        with pytest.raises(M.BundleIntegrityError) as err:
            _run(_assert_authentic(slots=slots))
        assert "contract" in str(err.value), str(err.value)
        assert "marker" in str(err.value) or "definition" in str(err.value), str(err.value)

    @pytest.mark.parametrize(
        "bad_digest",
        ["", "0" * 64, " " * 64],
        ids=["empty", "all_zero", "blank"],
    )
    def test_form3_empty_or_all_zero_hash_is_rejected(self, bad_digest: str) -> None:
        """③ 空串 / 全零 hash 不得进入 canonical bytes。

        **Validates: Requirements 6.2**
        """
        slots = dict(_valid_slots())
        slots[M.BundleSlot.template] = {
            "type": "definition",
            "ref": f"definition:{uuid.uuid4()}",
            "digest": bad_digest,
        }
        with pytest.raises(M.BundleIntegrityError) as err:
            _run(_assert_authentic(slots=slots))
        assert "template" in str(err.value), str(err.value)

    @pytest.mark.parametrize("mode", ["omission", "sql_null"])
    def test_form4_slot_omission_or_sql_null_is_rejected(self, mode: str) -> None:
        """④ slot omission 或 SQL NULL。

        **Validates: Requirements 6.2**
        """
        slots: dict[Any, Any] = dict(_valid_slots())
        if mode == "omission":
            slots.pop(M.BundleSlot.instrumentation)
        else:
            slots[M.BundleSlot.instrumentation] = None
        with pytest.raises(M.BundleIntegrityError) as err:
            _run(_assert_authentic(slots=slots))
        assert "instrumentation" in str(err.value), str(err.value)

    def test_form5_generator_candidate_cannot_pass_as_reviewed_contract(self) -> None:
        """⑤ generator 候选冒充已人工审核的 per-entry contract。

        `definitions.validate_contract_payload` **不看** `review_status`，故这一格必须由
        provisioner 自己补 —— 判据同时覆盖「review_status 不是 reviewed」与「contract_id
        与交付登记表不符」两种冒充。

        **Validates: Requirements 3.3**
        """
        payload = _reviewed_contract_payload()
        with pytest.raises(PP.ProjectionEntryNotReviewedError) as err:
            _run(
                _assert_authentic(
                    slots=_valid_slots(),
                    contract_payload={**payload, "review_status": "candidate"},
                )
            )
        assert "contract" in str(err.value), str(err.value)
        assert "review_status" in str(err.value), str(err.value)

        with pytest.raises(PP.ProjectionEntryNotReviewedError) as err2:
            _run(
                _assert_authentic(
                    slots=_valid_slots(),
                    contract_payload={**payload, "contract_id": "someone.elses.contract"},
                )
            )
        assert "contract" in str(err2.value), str(err2.value)

    def test_unknown_entry_has_no_reviewed_contract_at_all(self) -> None:
        """未登记 entry 一律拒绝（generator 只产 `candidate` 骨架）。

        **Validates: Requirements 3.3**
        """
        with pytest.raises(PP.ProjectionEntryNotReviewedError) as err:
            PP.load_projection_supply("xlsx/does-not-exist/never-reviewed")
        assert "contract" in str(err.value), str(err.value)

    def test_every_forged_form_raises_a_bundle_integrity_subclass(self) -> None:
        """五条判据必须走同一条可见路径（AC 3.3 的「同类拒绝同一条路径」）。"""
        for exc_type in (
            PP.ProjectionEntryNotReviewedError,
            PP.ForgedDefinitionIdentityError,
            PP.ProjectionAuthorityModelMismatchError,
        ):
            assert issubclass(exc_type, M.BundleIntegrityError), exc_type.__name__
            assert getattr(exc_type, "error_code", ""), f"{exc_type.__name__} 缺 error_code"


# ════════════════════════════════════════════════════════════════════════════
# 2. 不得靠放宽 opaque 通道复用（任务正文明令）
# ════════════════════════════════════════════════════════════════════════════


class TestOpaqueChannelStaysClosed:
    def test_opaque_provisioner_still_refuses_projection_contract(self) -> None:
        """行为断言：真调一次，`projection_contract` 必抛（不是读源码有没有 raise）。

        🔴 Task 65 把 `ensure()`（查不到就发布）拆成 `resolve()`（只查，业务写路径用）与
        `provision()`（查+发布，唯一宿主是 fix 脚本）。判据跟到 `provision()` 上 —— 它是
        现在唯一还收 `authority_model` 参数、因而唯一还能被喂进 `projection_contract`
        的入口。**行为断言一字未改**：真调一次、必抛、异常类型不放宽；并额外钉住
        `ensure()` 已消失，否则会留下一条不被本判据覆盖的旧旁路。

        **Validates: Requirements 2.3**
        """
        from app.services.workpaper_sync.writer_migration import (
            OpaqueAuthorityProvisioner,
            ProjectionAuthorityNotAllowedError,
        )

        assert not hasattr(OpaqueAuthorityProvisioner, "ensure"), (
            "`ensure()` 又回来了 —— 本判据只挂在 `provision()` 上，留着旧入口就等于"
            "留了一条「查不到就顺手给自己发证」且不被覆盖的通道"
        )
        provisioner = OpaqueAuthorityProvisioner(
            session=None, repository=None, artifacts=None, resolution=None
        )
        with pytest.raises(ProjectionAuthorityNotAllowedError):
            _run(
                provisioner.provision(
                    project_id=uuid.uuid4(),
                    wp_id=uuid.uuid4(),
                    authority_model=M.AuthorityModel.projection_contract,
                )
            )

    def test_opaque_marker_slots_are_untouched(self) -> None:
        """opaque 通道仍用 typed null marker —— Task 76 一个字节都没改它。"""
        from app.services.workpaper_sync import writer_migration as WM

        slots = D.normalize_bundle_slot_map(WM._marker_slots())
        assert set(slots) == set(M.BundleSlot)
        assert all(not spec.is_definition for spec in slots.values()), (
            "opaque 通道的 slot 变成 definition ⇒ 两条通道被混用了"
        )

    def test_projection_provisioner_refuses_non_projection_authority(self) -> None:
        """反向对称：本 provisioner 遇到非 projection authority 也必须拒。

        **Validates: Requirements 2.3**
        """
        model_by_entry = {
            str(row["entry_id"]): str(row["authority_model"])
            for row in RG.DELIVERED_PER_ENTRY_CONTRACTS
        }
        assert model_by_entry, "交付登记表为空 ⇒ 分母为空"
        assert set(model_by_entry.values()) == {"projection_contract"}, model_by_entry
        with pytest.raises(M.BundleIntegrityError):
            _run(_raise_on_opaque_authority())


async def _raise_on_opaque_authority() -> None:
    """把 opaque authority 喂给本 provisioner 的判据函数（必须拒）。"""
    await PP.assert_projection_supply_authentic(
        session=None,
        entry_id="xlsx/b60/gt-b60-bundle",
        authority_model=M.AuthorityModel.opaque_single_onlyoffice,
        authority_model_definition_sha256=_d("t76-authority"),
        slots=_valid_slots(),
        contract_payload=_reviewed_contract_payload(),
    )


# ════════════════════════════════════════════════════════════════════════════
# 3. 写入面禁令与 fail-open 禁令（AC 2.1 / 3.4 / 6.18 / Property 4 / 67）
# ════════════════════════════════════════════════════════════════════════════


class TestForbiddenSurfacesAndFailOpen:
    def test_provisioner_has_no_broad_except(self) -> None:
        """**Validates: Requirements 6.18**"""
        found = except_handler_types(PROVISIONING_PY)
        forbidden = [t for t in found if t in {"Exception", "BaseException", "<bare>"}]
        assert not forbidden, (
            f"provisioner 里出现宽泛 except {forbidden} —— 会把接线错误吞成「本项目无此数据」"
        )

    @pytest.mark.parametrize("surface", FORBIDDEN_WRITE_SURFACES)
    def test_provisioner_never_touches_forbidden_write_surfaces(self, surface: str) -> None:
        """provisioner 不切 pointer、不建 representation/content version、不 finalize。

        **Validates: Requirements 3.4**
        """
        tree = ast.parse(PROVISIONING_PY.read_text(encoding="utf-8"))
        hits = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Attribute) and node.func.attr == surface)
                or (isinstance(node.func, ast.Name) and node.func.id == surface)
            )
        ]
        assert not hits, f"provisioner 在 {hits} 行调用了禁面 {surface}()"

    def test_provisioner_does_not_commit(self) -> None:
        """事务边界属于调用方 —— 服务层自己 commit 会让「失败只留 orphan」不可控。

        **Validates: Requirements 2.4**
        """
        tree = ast.parse(PROVISIONING_PY.read_text(encoding="utf-8"))
        hits = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"commit", "rollback"}
        ]
        assert not hits, f"provisioner 在 {hits} 行自己 commit/rollback"

    def test_revision_drift_is_an_error_not_a_warning(self) -> None:
        """`content_revision` 变了必须抛（Property 4 的可观察判据，不是文档承诺）。

        **Validates: Requirements 2.1**
        """
        assert issubclass(PP.ContentRevisionDriftError, PP.ProjectionProvisioningError)
        for func in ("ensure", "attach"):
            node = function_node(PROVISIONING_PY, func)
            raised = {
                inner.exc.func.id
                for inner in ast.walk(node)
                if isinstance(inner, ast.Raise)
                and isinstance(inner.exc, ast.Call)
                and isinstance(inner.exc.func, ast.Name)
            }
            assert "ContentRevisionDriftError" in raised, (
                f"{func}() 没有 revision 漂移的 raise ⇒ Property 4 无判据"
            )

    def test_revision_and_pointer_snapshot_has_a_single_implementation(self) -> None:
        """前后比对必须同源：两处各写一份会让其中一处被短路时仍绿。"""
        source = code_only_source(PROVISIONING_PY)
        assert source.count("async def _revision_and_pointer") == 1, "快照实现不唯一"
        for func in ("ensure", "_snapshot"):
            assert "_revision_and_pointer" in called_names(function_node(PROVISIONING_PY, func))


# ════════════════════════════════════════════════════════════════════════════
# 4. candidate 受控 attach 的四条禁令（AC 3.4 / 6.18 / Property 67）
# ════════════════════════════════════════════════════════════════════════════


class TestCandidateAttachContract:
    def test_finalized_candidate_has_no_out_edges(self) -> None:
        """「不得修改已 finalize 的 candidate」的单点：`CANDIDATE_EDGES`。

        **Validates: Requirements 6.18**
        """
        assert M.CANDIDATE_EDGES[M.CandidateState.finalized] == frozenset()
        assert (
            M.CandidateState.ready in M.CANDIDATE_EDGES[M.CandidateState.awaiting_contract]
        ), "awaiting_contract → ready 不在状态机里 ⇒ attach 无合法边"
        with pytest.raises(M.SyncDomainError):
            M.assert_transition(
                "candidate", M.CandidateState.finalized.value, M.CandidateState.ready
            )

    def test_attach_delegates_state_edge_and_bundle_check(self) -> None:
        """attach 不复制一份 slot / 状态边校验（复制一份 ⇒ 短路任一侧都不改变行为）。"""
        node = function_node(REPOSITORY_PY, "attach_candidate_definitions")
        calls = called_names(node)
        assert "assert_transition" in calls, "attach 没走状态机单点"
        assert "assert_bundle_usable" in calls, "attach 没走 bundle 可用性单点"
        assert "append_candidate_event" in calls, "attach 没写 append-only 审计事件"
        assert "with_for_update" in calls, "attach 没对 candidate 行加锁"

    def test_attach_service_rejects_wrong_state_before_touching_repository(self) -> None:
        """`state != awaiting_contract` 的 candidate 必须在**调仓储之前**被拒。

        **Validates: Requirements 6.18**
        """
        node = function_node(PROVISIONING_PY, "attach")
        raised = [
            inner.exc.func.id
            for inner in ast.walk(node)
            if isinstance(inner, ast.Raise)
            and isinstance(inner.exc, ast.Call)
            and isinstance(inner.exc.func, ast.Name)
        ]
        for name in (
            "CandidateNotAwaitingContractError",
            "CandidateScopeMismatchError",
            "ContentRevisionDriftError",
        ):
            assert name in raised, f"attach 缺 {name} 的 raise"

    def test_attach_does_not_reach_resolver_room_pointer_or_evidence(self) -> None:
        """attach 不得让 candidate 进入 resolver / room / current pointer / evidence。

        **Validates: Requirements 6.18**
        """
        referenced = called_names(ast.parse(PROVISIONING_PY.read_text(encoding="utf-8")))
        for forbidden in (
            "set_entry_pointer",
            "load_bundle_snapshot",
            "resolve",
            "ensure_room",
            "record_evidence",
        ):
            assert forbidden not in referenced, f"provisioner 调了 {forbidden}()"

    def test_candidate_only_repository_still_lacks_attach(self) -> None:
        """Task 17 的 upgrader 门面**不得**因本任务获得 attach 面（它无权发布 contract）。

        **Validates: Requirements 6.18**
        """
        from app.services.workpaper_sync.excel_instrumentation import CandidateOnlyRepository

        assert not hasattr(CandidateOnlyRepository, "attach_candidate_definitions"), (
            "instrumentation 门面拿到了 attach 面 ⇒ upgrader 可以自己补 contract 了"
        )
        forbidden = function_node(INSTRUMENTATION_PY, "_candidate_forbidden_methods")
        assert forbidden is not None


# ════════════════════════════════════════════════════════════════════════════
# 5. 幂等复用的尺度是 canonical bytes（AC 6.2 / 3.6 / Property 10 / 28）
# ════════════════════════════════════════════════════════════════════════════


class TestIdempotentReuseScale:
    def test_reuse_lookup_keys_on_digest_not_logical_id(self) -> None:
        """按 `logical_id` 猜会复用一个身份已漂移的 definition（Property 28 要打红的形态）。

        **Validates: Requirements 6.2**
        """
        for method in ("_find_approved_definition", "_find_approved_bundle"):
            node = function_node(PROVISIONING_PY, method)
            src = ast.dump(node)
            assert "sha256" in src or "canonical_payload_sha256" in src, f"{method} 未按 digest 查"
            assert "logical_id" not in src, f"{method} 按 logical_id 复用 ⇒ 身份漂移风险"
            assert "approved" in src, f"{method} 未限定 approved"

    def test_payload_validation_runs_before_the_reuse_branch(self) -> None:
        """复用分支之前必须先校验 payload，否则非法 payload 会被「已存在」免检放行。"""
        node = function_node(PROVISIONING_PY, "publish_definition")
        body = list(getattr(node, "body", []))

        def _lines(predicate: Any) -> list[int]:
            return [
                inner.lineno
                for stmt in body
                for inner in ast.walk(stmt)
                if isinstance(inner, ast.Call) and predicate(inner.func)
            ]

        # 🔴 两条判据分开断言，**不用 `or`**：写成
        # `{"validate_definition_payload", "canonical_digest"}` 的集合成员判据时，
        # 删掉校验调用后 `canonical_digest` 还在前面 ⇒ 判据恒绿（本轮变异 M09 实测 GREEN）。
        validate_lines = _lines(
            lambda f: isinstance(f, ast.Name) and f.id == "validate_definition_payload"
        )
        digest_lines = _lines(lambda f: isinstance(f, ast.Name) and f.id == "canonical_digest")
        reuse_lines = _lines(
            lambda f: isinstance(f, ast.Attribute) and f.attr == "_find_approved_definition"
        )
        assert validate_lines, "publish_definition 不再校验 payload ⇒ 非法 payload 可入库"
        assert digest_lines, "publish_definition 不再现算 canonical digest ⇒ 复用尺度失守"
        assert reuse_lines, "publish_definition 没有复用查询 ⇒ 幂等承诺无实现"
        assert min(validate_lines) < min(reuse_lines), (
            "payload 校验在复用查询之后 ⇒ 已存在同 digest 的行会让非法 payload 免检"
        )
        assert min(digest_lines) < min(reuse_lines), "digest 现算晚于复用查询"

    def test_bundle_canonical_payload_has_no_uuid(self) -> None:
        """bundle canonical bytes 只含 type + digest ⇒ 同内容 bundle 跨库可复现。

        **Validates: Requirements 6.2**
        """
        payload = D.build_bundle_canonical_payload(
            authority_model=M.AuthorityModel.projection_contract,
            authority_model_definition_sha256=_d("t76-authority"),
            slots=_valid_slots(),
        )
        flat = repr(payload)
        assert "definition:" not in flat, f"bundle canonical payload 内嵌了 slot ref: {flat}"
        assert set(payload) == {"schema_version", "authority_model"} | {
            slot.value for slot in M.BundleSlot
        }, sorted(payload)

    def test_settlement_vocabulary_is_closed(self) -> None:
        """representation 阶段的结局是封闭词表（自由文本让守卫只能比字符串）。"""
        assert PP.REPRESENTATION_SETTLEMENT_STATES == (
            "reused_current",
            "reused_candidate",
            "attached_candidate",
            "blocked",
        )
        node = function_node(PROVISIONING_PY, "_settle_representation_stage")
        returned = {
            elt.value
            for inner in ast.walk(node)
            if isinstance(inner, ast.Return) and isinstance(inner.value, ast.Tuple)
            for elt in inner.value.elts[:1]
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        }
        assert returned == set(PP.REPRESENTATION_SETTLEMENT_STATES), returned

    def test_supply_tables_list_matches_the_task_scope(self) -> None:
        """四张供给表清单只有一份（守卫与 `--check` 共用）。"""
        assert PP.SUPPLY_TABLES == (
            "working_paper_sync_definition_artifact",
            "working_paper_sync_definition_bundle",
            "working_paper_representation_upgrade_candidate",
            "working_paper_content_representation",
        )
        assert len(set(PP.SUPPLY_TABLES)) == 4


# ════════════════════════════════════════════════════════════════════════════
# 6. 消费宿主（additive 注入即死代码 ⇒ 判据落在唯一消费方）
# ════════════════════════════════════════════════════════════════════════════


class TestConsumptionHost:
    def test_provisioner_is_consumed_by_the_apply_script(self) -> None:
        """`--apply` 真实例化 provisioner 并 `await ensure(...)` 后 commit。

        **Validates: Requirements 12.1**
        """
        node = function_node(APPLY_SCRIPT, "run_apply")
        calls = called_names(node)
        assert "ProjectionDefinitionProvisioner" in calls, "宿主没实例化 provisioner"
        assert "ensure" in calls, "宿主没调 ensure() ⇒ provisioner 是死代码"
        assert "commit" in calls, "宿主不 commit ⇒ 真实行永远不落库"
        assert "rollback" in calls, "宿主失败不回滚 ⇒ 会留下半成功可见态"

    def test_check_mode_is_read_only(self) -> None:
        """`--check` 不得 commit（只读预演）。

        **Validates: Requirements 2.4**
        """
        node = function_node(APPLY_SCRIPT, "run_check")
        calls = called_names(node)
        assert "commit" not in calls, "`--check` 会 commit ⇒ 不是只读"
        assert "publish_pilot_definitions" in calls, "`--check` 没真跑一次 payload 组装"

    def test_publish_pilot_definitions_is_no_longer_test_only(self) -> None:
        """Task 76 正文：`publish_pilot_definitions` 不得继续只被 `test_task4x_*_pg.py` 调用。

        **Validates: Requirements 12.1**
        """
        production_callers: dict[str, list[int]] = {}
        for path in sorted(SVC.rglob("*.py")) + [APPLY_SCRIPT]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            lines = [
                node.lineno
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and (
                    (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr == "publish_pilot_definitions"
                    )
                    or (
                        isinstance(node.func, ast.Name)
                        and node.func.id == "publish_pilot_definitions"
                    )
                )
            ]
            if lines:
                production_callers[path.name] = lines
        # 定义处（四个 pilot 模块）不算调用方；调用方必须至少有 provisioner + 宿主脚本
        assert "projection_provisioning.py" in production_callers, production_callers
        assert APPLY_SCRIPT.name in production_callers, production_callers

    def test_apply_script_resolves_targets_from_a_single_source(self) -> None:
        """`entry → wp_code` 只有一份真源 —— **reviewed 裁决表**，不写第二份清单。

        🔴 2026-09-04 更正判据。本条原先断言宿主必须
        `getattr(provider, "PILOT_WP_CODES")`，与
        `test_task76_wp_code_adjudication.py::test_resolve_targets_does_not_read_PILOT_WP_CODES`
        **方向完全相反** —— 两条守卫互相否定，其中必有一条恒红。实测（对 HEAD 版宿主源码
        跑同一条 AST 判据）确认恒红的是本条：宿主早已改读裁决表，本条是裁决表引入**之前**
        的设计残留。

        为什么真源换了：`PILOT_WP_CODES` 追溯到 manifest 的 `wp_code_patterns`，那是
        `generate_workpaper_sync_manifest._source_match()` 从宿主 Vue 文件名 CamelCase 抽的
        启发式产物，正则会把下一个词首字母吞进来，产出 `D2A` / `G7L` / `H1F` 三个在
        `wp_index` 里 **0 命中**的幻影码 ⇒ 四份契约全部 unresolved，且给出的原因还是错的。
        真源改为 `backend/data/workpaper_sync_entry_wp_code_adjudication.json`
        （`review_status: reviewed`）。

        判据仍落在「真的做了一次取值」而非「源码里出现过这个名字」：本函数的
        `unresolved_reason` 文案里正当地提到了 `PILOT_WP_CODES`（解释为什么不用它），
        子串判据会假绿（本轮变异 M20 实测 GREEN）。
        """
        node = function_node(APPLY_SCRIPT, "resolve_targets")
        attributes = {
            inner.attr for inner in ast.walk(node) if isinstance(inner, ast.Attribute)
        } | {inner.id for inner in ast.walk(node) if isinstance(inner, ast.Name)}

        # ① 必须真的调了裁决表加载器（不是在注释里提它）
        loader_calls = [
            inner
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Name)
            and inner.func.id == "load_wp_code_adjudication"
        ]
        assert loader_calls, (
            "宿主没调 `load_wp_code_adjudication()` ⇒ entry→wp_code 又成了第二份清单"
        )

        # ② 反向：不得回落到会产幻影码的启发式
        phantom = [
            inner
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Name)
            and inner.func.id == "getattr"
            and len(inner.args) >= 2
            and isinstance(inner.args[1], ast.Constant)
            and inner.args[1].value == "PILOT_WP_CODES"
        ]
        assert not phantom, (
            "宿主又从 provider 取 `PILOT_WP_CODES` 了 —— 那是 manifest 文件名启发式的"
            "产物，实测产 D2A / G7L / H1F 三个 wp_index 0 命中的幻影码"
        )

        # ③ provisioning 准入判据必须**下标取值**，且缺键必须先被拦住。
        #
        # 🔴 判据不能只查「字符串出现过」：改成 `verdict.get(KEY, True)` 时字符串照样在，
        #    而语义已经从「缺键即抛」翻成「缺键默认放行」= fail-open。故判据落在两处**语法
        #    形态**：(a) 存在 `verdict[KEY]` 形态的下标取值；(b) 不存在以该键为第一实参的
        #    `.get(KEY, <默认>)` 调用。
        KEY = "resolvable_for_provisioning"
        subscripts = [
            inner
            for inner in ast.walk(node)
            if isinstance(inner, ast.Subscript)
            and isinstance(inner.slice, ast.Constant)
            and inner.slice.value == KEY
        ]
        assert subscripts, (
            f"宿主没有 `verdict[{KEY!r}]` 形态的下标取值 ⇒ 「该 entry 能否定位宿主底稿」"
            "这条准入没了；旧键 `resolvable_today` 把它与 matcher 域冲突混在一个布尔里，"
            "实测让 G7 恒不 provision"
        )
        defaulted = [
            inner
            for inner in ast.walk(node)
            if isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "get"
            and len(inner.args) == 2
            and isinstance(inner.args[0], ast.Constant)
            and inner.args[0].value == KEY
        ]
        assert not defaulted, (
            f"宿主用 `.get({KEY!r}, <默认>)` 取准入判据 —— 缺键默认放行是 fail-open："
            "「裁决表漏填」会被静默当成「已裁决可解析」"
        )
        # 🔴 判据必须是「该比较**门控了一个 raise**」，不能只是「存在这样一个比较」：
        #    把 `if KEY not in verdict:` 短路成 `if False and KEY not in verdict:` 时
        #    Compare 节点仍在，只查存在性的判据照样绿（本轮变异 M1 实测 GREEN）。
        #    故要求：存在一个 `ast.If`，其 test **恰为**该 Compare（不是被 `and` 包起来的
        #    子项），且 body 里有 `raise`。
        def _is_missing_key_compare(test: ast.expr) -> bool:
            return (
                isinstance(test, ast.Compare)
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.NotIn)
                and isinstance(test.left, ast.Constant)
                and test.left.value == KEY
            )

        guarded_raises = [
            inner
            for inner in ast.walk(node)
            if isinstance(inner, ast.If)
            and _is_missing_key_compare(inner.test)
            and any(isinstance(stmt, ast.Raise) for stmt in ast.walk(inner))
        ]
        assert guarded_raises, (
            f"宿主没有「`{KEY!r} not in verdict` 直接门控一个 raise」的缺键拦截 —— "
            "缺键会走到下标取值抛 KeyError，而那条错误不带「该键是准入判据、"
            "不得默认放行」的可读诊断；把该比较包进 `False and …` 也算没有拦截"
        )

        assert "DELIVERED_PER_ENTRY_CONTRACTS" in attributes, (
            "宿主没从交付登记表现算 entry 集合"
        )
        assert "unresolved_reason" in attributes, "查不到目标时没给显式原因 ⇒ 静默跳过"

    def test_script_reports_errors_instead_of_degrading(self) -> None:
        """脚本失败必须非零退出，不得降级成成功。

        **Validates: Requirements 6.18**
        """
        node = function_node(APPLY_SCRIPT, "_main")
        raised = {
            inner.exc.func.id
            for inner in ast.walk(node)
            if isinstance(inner, ast.Raise)
            and isinstance(inner.exc, ast.Call)
            and isinstance(inner.exc.func, ast.Name)
        }
        assert "ProvisionScriptError" in raised, "脚本吞掉了 entry 级失败"


# ════════════════════════════════════════════════════════════════════════════
# 7. V153 迁移形态（append-only 审计轨）
# ════════════════════════════════════════════════════════════════════════════


class TestV153Shape:
    def test_migration_is_idempotent_and_additive_only(self) -> None:
        """**Validates: Requirements 12.1**"""
        sql = MIGRATION_V153.read_text(encoding="utf-8")
        body = "\n".join(
            line for line in sql.split("\n") if not line.strip().startswith("--")
        )
        assert "CREATE TABLE IF NOT EXISTS working_paper_representation_candidate_event" in body
        for forbidden in ("DROP TABLE", "TRUNCATE", "DROP COLUMN", "ALTER COLUMN"):
            assert forbidden not in body.upper(), f"V153 出现破坏性语句 {forbidden}"
        for stmt in [s.strip() for s in body.split(";") if s.strip()]:
            head = stmt.split("\n", 1)[0].upper()
            if head.startswith("CREATE TABLE"):
                assert "IF NOT EXISTS" in head, stmt[:80]
            if head.startswith("CREATE INDEX"):
                assert "IF NOT EXISTS" in head, stmt[:80]
            if head.startswith("CREATE TRIGGER") or head.startswith("CREATE OR REPLACE TRIGGER"):
                assert head.startswith("CREATE OR REPLACE TRIGGER"), stmt[:80]

    def test_append_only_trigger_reuses_the_v151_function(self) -> None:
        """复用 V151 的 `wpsync_forbid_timeline_mutation()`，不复制第二份实现。

        **Validates: Requirements 6.18**
        """
        sql = MIGRATION_V153.read_text(encoding="utf-8")
        assert "wpsync_forbid_timeline_mutation()" in sql
        assert "CREATE OR REPLACE FUNCTION wpsync_forbid_timeline_mutation" not in sql, (
            "V153 自己又定义了一份 append-only 函数 ⇒ 短路任一侧都不改变行为"
        )
        assert "wpsync_forbid_timeline_mutation" in MIGRATION_V151.read_text(encoding="utf-8")

    def test_attach_edge_is_constrained_in_the_database(self) -> None:
        """审计轨自己也不得记录本入口无权做的迁移（DB 层 CHECK，不是应用层承诺）。

        **Validates: Requirements 6.18**
        """
        sql = MIGRATION_V153.read_text(encoding="utf-8")
        assert "ck_wprce_attach_edge" in sql
        assert "from_state = 'awaiting_contract'" in sql and "to_state = 'ready'" in sql
        assert "ck_wprce_attached_identity" in sql, "attach 事件可以缺 contract/bundle 身份"
        assert "wpsync_is_digest(definition_bundle_sha256)" in sql

    def test_orm_model_matches_the_migration_columns(self) -> None:
        """ORM 与迁移双向锁死（少一列 ⇒ 写入静默丢字段）。"""
        from app.models.workpaper_sync_models import WorkpaperRepresentationCandidateEvent as E

        sql = MIGRATION_V153.read_text(encoding="utf-8")
        columns = {c.name for c in E.__table__.columns}
        assert E.__tablename__ == "working_paper_representation_candidate_event"
        for name in columns:
            assert re.search(rf"\b{name}\b", sql), f"ORM 有列 {name} 而迁移里没有"
        for required in (
            "candidate_id",
            "sequence_no",
            "event_type",
            "from_state",
            "to_state",
            "contract_definition_id",
            "definition_bundle_id",
            "definition_bundle_sha256",
            "correlation_id",
        ):
            assert required in columns, f"ORM 缺列 {required}"


# ════════════════════════════════════════════════════════════════════════════
# 8. Property 收束
# ════════════════════════════════════════════════════════════════════════════


class TestProperties:
    def test_property_4_revision_orthogonality_has_an_observable_judgment(self) -> None:
        """P4：纯 definitions 变化不动 `content_revision` —— 判据是前后现读比对 + 抛错。

        **Validates: Requirements 2.1**
        """
        assert hasattr(PP.ProvisionOutcome, "revision_unchanged")
        assert hasattr(PP.CandidateAttachOutcome, "revision_unchanged")
        assert "_revision_and_pointer" in called_names(function_node(PROVISIONING_PY, "ensure"))
        # attach 经 `_snapshot` 一跳到同一份实现（不是另抄一份读法）。
        attach_calls = called_names(function_node(PROVISIONING_PY, "attach"))
        assert "_snapshot" in attach_calls, "attach() 没做前后快照"
        assert "_revision_and_pointer" in called_names(
            function_node(PROVISIONING_PY, "_snapshot")
        ), "attach 的快照没走共享实现 ⇒ 其中一处被短路时仍绿"

    def test_property_5_failure_leaves_no_dangling_visible_state(self) -> None:
        """P5 的结构前提：服务层不 commit + 宿主失败即 rollback（正面证明在 `_pg.py`）。

        **Validates: Requirements 2.4**
        """
        tree = ast.parse(PROVISIONING_PY.read_text(encoding="utf-8"))
        assert not [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "commit"
        ]
        assert "rollback" in called_names(function_node(APPLY_SCRIPT, "run_apply"))

    def test_property_10_idempotent_reuse_is_digest_scoped(self) -> None:
        """P10：同 canonical bytes 必须复用而不是发第二份。

        **Validates: Requirements 3.6**
        """
        def digest(slots: Any) -> str:
            return D.bundle_canonical_digest(
                authority_model=M.AuthorityModel.projection_contract,
                authority_model_definition_sha256=_d("t76-authority"),
                slots=slots,
            )

        # 复用尺度 = canonical bytes：**child digest 相同、uuid 不同**必须算出同一个
        # bundle digest（否则每次 provision 都会因为新 uuid 造出第二份同内容 bundle）。
        assert digest(_valid_slots()) == digest(_valid_slots()), (
            "同 child digest 不同 uuid 算出两个 bundle digest ⇒ 幂等复用不可能成立"
        )
        # 反过来：child digest 变一位，bundle digest 必须变（否则漂移不可见）。
        drifted = _valid_slots()
        drifted[M.BundleSlot.contract] = D.definition_slot_spec(
            M.BundleSlot.contract,
            definition_id=uuid.uuid4(),
            definition_sha256=_d("t76-contract-drifted"),
        )
        assert digest(drifted) != digest(_valid_slots()), "contract digest 变了 bundle 却不变"

    def test_property_28_drift_fails_closed_with_first_illegal_slot(self) -> None:
        """P28：slot omission / 非法 marker / 缺 contract 一律 fail closed 且指出位置。

        **Validates: Requirements 6.10**
        """
        cases: list[tuple[str, dict[Any, Any]]] = []
        slots = dict(_valid_slots())
        slots.pop(M.BundleSlot.contract)
        cases.append(("contract", slots))
        slots2 = dict(_valid_slots())
        slots2[M.BundleSlot.template] = D.marker_slot_spec(M.BundleSlot.template)
        cases.append(("template", slots2))
        for expected_slot, bad in cases:
            with pytest.raises(M.BundleIntegrityError) as err:
                _run(_assert_authentic(slots=bad))
            assert expected_slot in str(err.value), (expected_slot, str(err.value))

    def test_property_67_candidate_never_becomes_current(self) -> None:
        """P67：attach 只把 candidate 推到 `ready`，finalize 仍归 Task 36 的门。

        **Validates: Requirements 6.18**
        """
        node = function_node(REPOSITORY_PY, "attach_candidate_definitions")
        src = ast.dump(node)
        assert "CandidateState" in src and "ready" in src
        assert "finalized_representation_id" not in src, "attach 写了 finalize 字段"
        assert "finalize_candidate" not in called_names(node), "attach 直接 finalize 了"
        # `ready` 不是 current：pointer 只由 `set_entry_pointer` 切，而它不在本模块。
        assert "set_entry_pointer" not in called_names(
            ast.parse(PROVISIONING_PY.read_text(encoding="utf-8"))
        )
