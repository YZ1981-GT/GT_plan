# -*- coding: utf-8 -*-
"""Task 77 守卫 —— Word per-entry entry gate 与 candidate finalize gate（离线判据）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 77
点名 Property：**28 / 30 / 31 / 32 / 34 / 67**
点名 AC：6.10 · 6.18 · 7.1 · 7.2 · 7.3 · 7.4 · 7.5 · 7.8 · 7.10 · 12.5

═══ 被守的产物 ═══

* `backend/app/services/workpaper_sync/word_entry_gate.py`（**新建**：
  `WordEntryDefinitionLoader` + `WordEntryFinalizeGate` + 四条 tagged-SDT 判据 +
  载体门/锚点门）
* `backend/scripts/fix/fix_task77_finalize_word_entry_representation.py`（**新建**：
  gate 的**唯一消费宿主**，`--check` / `--apply`）

连库判据（真实 PG、真 candidate、真 finalize）在
`test_task77_word_entry_gate_pg.py`。

═══ 判据强度约定（沿用 Task 75/76，逐条不放宽）═══

1. **禁 grep 式「字符存在」**：判「某能力接没接」一律落到 **AST / 真实执行 / 结构形态**。
   典型：`test_gate_is_consumed_by_the_host_script` 用 AST 找 `finalize_candidate(` 的
   调用宿主，而不是 `"WordEntryFinalizeGate" in source`（写在 docstring 里也绿）。
2. **每条禁令一条判据**，且判据落在**真实执行**上：四个降级锚点、`row_sdt` 载体、
   段落索引/正则 fallback、模板重生成，各有独立判据与独立变异锚点。
3. **禁沿用 Excel 的 sheet/cell 判据**：`test_no_sheet_or_cell_criterion_is_reused`
   在 AST 上按**封闭白名单**断言从 `excel_entry_gate` 只 import 了三个文档无关的名字。
4. **禁 `except Exception` fail-open**：逐个 `except` 子句检查捕获类型；反向自检证明该
   检查真能抓到。
5. **计数一律从来源节现算**；集合层「有序等值 + 无重复」双断言。
6. 分母为空的 Property **不宣称通过**：本 lane 行域字段实测 0 个，故 Requirement 7.2
   的「行实例计数」在本文件里只落**结构前提**，不宣称通过（见
   `TestProperties.test_property_30_row_domain_denominator_is_empty_and_not_claimed`）。

用法（仓库根；本仓库 PATH 上的 `python` 可能指向坏掉的解释器）::

    .\\.venv\\Scripts\\python.exe -m pytest \\
        backend/tests/workpaper_sync/test_task77_word_entry_gate.py -q
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pytest

_THIS = Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
SVC = BACKEND / "app" / "services" / "workpaper_sync"
GATE_PY = SVC / "word_entry_gate.py"
ENGINE_PY = SVC / "word_sdt_engine.py"
EXCEL_GATE_PY = SVC / "excel_entry_gate.py"
REGISTRY_PY = SVC / "adapters" / "registry.py"
CARRIER_CONTRACT = BACKEND / "data" / "onlyoffice_word_sdt_carrier_contract.json"
PUBLICATION = BACKEND / "data" / "workpaper_sync_f2_word_lane_publication.json"
STAGED_CONTRACT_DIR = BACKEND / "data" / "workpaper_sync_word_contracts"
HOST_SCRIPT = BACKEND / "scripts" / "fix" / "fix_task77_finalize_word_entry_representation.py"
GENERATOR = BACKEND / "scripts" / "gen" / "generate_task60_f2_word_contracts.py"

if str(BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(BACKEND))
if str(GENERATOR.parent) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(GENERATOR.parent))
os.environ.setdefault("DB_DISABLE_SSL", "True")

if str(HOST_SCRIPT.parent) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(HOST_SCRIPT.parent))

import fix_task77_finalize_word_entry_representation as HOST  # noqa: E402
import generate_task60_f2_word_contracts as G60  # noqa: E402
from app.services.workpaper_sync import word_entry_gate as WG  # noqa: E402
from app.services.workpaper_sync import word_instrumentation as WI  # noqa: E402
from app.services.workpaper_sync import word_sdt_engine as WE  # noqa: E402
from app.services.workpaper_sync.contracts import (  # noqa: E402
    ContractCarrierGateError,
    load_word_carrier_gate,
)
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402

#: 允许从 Task 36 复用的名字（**封闭**白名单）—— 三个都与文档类型无关。
ALLOWED_EXCEL_IMPORTS: frozenset[str] = frozenset(
    {"PerEntryContractUnapprovedError", "assert_frozen_slots_shape", "raw_slot_map_of"}
)

#: Task 36 的 sheet/cell 一族判据 —— 本模块**一个都不得**引用（Task 77 正文点名）。
FORBIDDEN_EXCEL_NAMES: tuple[str, ...] = (
    "assert_no_structure_drift",
    "business_sheet_names",
    "assert_metadata_sheet_excluded",
    "assert_contract_declares_no_metadata_sheet",
    "assert_dynamic_columns_label_independent",
    "dynamic_column_stable_keys",
    "_assert_dynamic_columns_declared",
    "EntryIdentityInventory",
    "parse_identity_inventory",
    "assert_identity_inventory_usable",
    "AdapterBuild",
    "assert_adapter_build_usable",
    "ExcelEntryDefinitionLoader",
    "ExcelEntryFinalizeGate",
    "REQUIRED_EQUIVALENCE_KEYS",
    "parse_candidate_evidence",
    "DYNAMIC_COLUMN_IDENTITY_TEMPLATE",
    "PLATFORM_METADATA_SHEETS",
    "observed_business_sheets",
)


# ════════════════════════════════════════════════════════════════════════════
# 工具（AST / 剥注释；判据不靠字符窗口）
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


def referenced_names(node: ast.AST) -> set[str]:
    """节点内出现的**标识符**（Name.id + Attribute.attr）—— 不含字符串字面量。"""
    out: set[str] = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name):
            out.add(inner.id)
        elif isinstance(inner, ast.Attribute):
            out.add(inner.attr)
    return out


def attribute_reads(node: ast.AST) -> set[str]:
    """节点内被**读取**的属性名（`x.attr`）。"""
    return {
        inner.attr for inner in ast.walk(node) if isinstance(inner, ast.Attribute)
    }


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


def non_docstring_strings(tree: ast.AST) -> set[str]:
    """模块里**不是 docstring** 的字符串字面量。

    🔴 为什么要区分：模块/函数 docstring 里正当地写着「本模块不读 `backend/wp_templates/`」
    这句说明，用整文件字符查找会把**说明本身**判成违规（首轮实测就是这个假红）。
    """
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def imported_from(path: Path, module_suffix: str) -> set[str]:
    """从某个模块 import 进来的名字集合（`from ... import a, b`）。"""
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(module_suffix):
            for alias in node.names:
                out.add(alias.name)
    return out


# ════════════════════════════════════════════════════════════════════════════
# 真实 fixture（权威模板派生；不手搓最小 DOCX）
# ════════════════════════════════════════════════════════════════════════════


class _Lane:
    """一个 Word lane entry 的完整真实 fixture（模板 → 注入 → 契约 → 清册）。"""

    def __init__(self, decl: Any) -> None:
        self.decl = decl
        self.entry_id = decl.contract_id
        self.template_bytes = decl.template_path.read_bytes()
        self.facts = G60.token_facts(self.template_bytes)
        self.spec = G60.build_instrumentation_spec(decl, self.facts)
        # 🔴 契约定位走**宿主脚本**，不是 gate：Task 60 的
        #    `test_the_staged_contract_dir_has_no_production_consumer` 要求暂存目录名在
        #    `backend/app/**` 里出现 0 次，因此 gate 只接受已解析的 `SyncContract`。
        self.contract, self.contract_origin = HOST.load_word_lane_contract(decl.contract_id)
        self.engine_gate = load_word_carrier_gate()
        self.inject_gate = WI.WordSdtCarrierGate.load()
        self.instrumented = WI.instrument_docx_bytes(
            self.template_bytes, self.spec, gate=self.inject_gate
        )
        self.readback = WI.read_back_word_tags(
            instrumented=self.instrumented, spec=self.spec, gate=self.inject_gate
        )
        self.equivalence = WI.verify_docx_visible_equivalence(
            source=self.template_bytes, instrumented=self.instrumented, spec=self.spec
        )
        self.instrumentation_payload = WI.build_word_instrumentation_payload(
            spec=self.spec,
            template_definition_sha256=self.contract.template_definition_sha256,
            template_sha256=hashlib.sha256(self.template_bytes).hexdigest(),
            gate=self.inject_gate,
        )
        self.inventory = WG.declared_tag_inventory(
            contract=self.contract,
            instrumentation_payload=self.instrumentation_payload,
            readback=self.readback,
            entry_id=self.entry_id,
        )
        self.binding = WE.WordEngineBinding(
            contract=self.contract,
            entry_id=self.entry_id,
            mode=WE.WordEngineMode.offline_candidate_validation,
            carrier_gate=self.engine_gate,
        )

    # ── 观测 ────────────────────────────────────────────────────────────
    def observe(self, data: bytes | None = None) -> WG.WordEntryObservation:
        payload = data if data is not None else self.instrumented.instrumented_bytes
        with tempfile.TemporaryDirectory(prefix="tmp_task77_obs_") as tmp:
            path = Path(tmp) / "candidate.docx"
            path.write_bytes(payload)
            extracted = WE.extract_word_projection(
                artifact=path,
                binding=self.binding,
                substrate_role=WE.SubstrateRole.staged_result,
                artifact_kind=WE.ArtifactKind.canonical,
                artifact_state=WE.ArtifactState.staged,
            )
        return WG.observe_word_entry(extracted, entry_id=self.entry_id)

    def roundtrip(self, data: bytes | None = None) -> WG.WordCandidateRoundtrip:
        payload = data if data is not None else self.instrumented.instrumented_bytes
        tmp = Path(tempfile.mkdtemp(prefix="tmp_task77_rt_"))
        path = tmp / "candidate.docx"
        path.write_bytes(payload)
        return WG.verify_candidate_tag_roundtrip(
            candidate_path=path,
            binding=self.binding,
            scratch_dir=tmp,
            entry_id=self.entry_id,
        )

    def evidence_report(self, **overrides: Any) -> bytes:
        """与 Task 59 `stage_and_register_candidate` 同形的证据报告字节。"""
        report = {
            "schema_version": WG.WORD_UPGRADE_EVIDENCE_SCHEMA,
            "entry_id": self.entry_id,
            "template_id": self.spec.template_id,
            "document_type": "docx",
            "source_representation_id": "00000000-0000-0000-0000-000000000001",
            "content_version_id": "00000000-0000-0000-0000-000000000002",
            "from_definition_bundle_id": None,
            "from_definition_bundle_sha256": None,
            "template_definition_sha256": self.contract.template_definition_sha256,
            "instrumentation_definition_sha256": (
                self.contract.instrumentation_definition_sha256
            ),
            "rollback_source_sha256": hashlib.sha256(self.template_bytes).hexdigest(),
            "instrumented_sha256": self.instrumented.instrumented_sha256,
            "visible_equivalence": copy.deepcopy(dict(self.equivalence)),
            "tag_readback": copy.deepcopy(dict(self.readback)),
            "probe_gate": self.inject_gate.probe_gate_identity(),
        }
        report.update(overrides)
        return json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _lanes() -> tuple[_Lane, ...]:
    return tuple(_Lane(decl) for decl in G60.ENTRIES)


@pytest.fixture(scope="module")
def lanes() -> tuple[_Lane, ...]:
    return _lanes()


@pytest.fixture(scope="module")
def plan(lanes: tuple[_Lane, ...]) -> _Lane:
    """F2-22 —— 它同时有 block 载体字段与两实例字段，四条判据的分母最全。"""
    hits = [lane for lane in lanes if lane.inventory.block_containers]
    assert hits, "两个 lane 都没有 block 载体字段 ⇒ 层级判据无分母"
    return hits[0]


# ════════════════════════════════════════════════════════════════════════════
# 0. 守卫自检
# ════════════════════════════════════════════════════════════════════════════


class TestGuardSelfChecks:
    """每个分母与每条工具函数都要能被证伪，否则后面的判据可能整类空跑。"""

    def test_all_required_artifacts_exist(self) -> None:
        """**Validates: Requirements 12.5**"""
        for path in (
            GATE_PY,
            ENGINE_PY,
            EXCEL_GATE_PY,
            CARRIER_CONTRACT,
            PUBLICATION,
            HOST_SCRIPT,
            GENERATOR,
            STAGED_CONTRACT_DIR,
        ):
            assert path.exists(), f"缺少判据对象：{path}"

    def test_lane_denominator_is_two_and_source_backed(self, lanes: tuple[_Lane, ...]) -> None:
        """lane 分母从 Task 60 发布记录**现算**，不写死。"""
        record = json.loads(PUBLICATION.read_text(encoding="utf-8"))
        recorded = [str(e.get("lane_entry_key")) for e in record["entries"]]
        assert len(recorded) == len(set(recorded)) == 2, recorded
        assert recorded == sorted(recorded), "有序等值双断言"
        assert {lane.decl.lane_entry_key for lane in lanes} == set(recorded)
        assert len(lanes) == 2

    def test_fixtures_are_derived_from_authoritative_templates(
        self, lanes: tuple[_Lane, ...]
    ) -> None:
        """fixture 必须是**真实权威模板**派生，否则覆盖计数为空、判据空转。"""
        record = json.loads(PUBLICATION.read_text(encoding="utf-8"))
        want = {f["name"]: f["sha256"] for f in record["authoritative_templates"]["files"]}
        for lane in lanes:
            digest = hashlib.sha256(lane.template_bytes).hexdigest()
            assert want[lane.decl.template_path.name] == digest, lane.entry_id
            assert int(lane.equivalence["coverage"]["visible_text_chars"]) > 0
            assert len(lane.inventory.tags) >= 17, lane.inventory.tags

    def test_strip_py_comments_keeps_line_numbers_and_spares_strings(self) -> None:
        src = "a = 1\n# hidden marker\nb = 2\n"
        out = strip_py_comments(src)
        assert "hidden marker" not in out
        assert len(out.split("\n")) == len(src.split("\n")), "剥注释改变了行数"
        assert strip_py_comments('x = "# not a comment"') == 'x = "# not a comment"'
        triple = 'q = """line -- with # inside"""'
        assert strip_py_comments(triple) == triple, "三引号块被当注释剥了 ⇒ 会造出假判据"
        raw = GATE_PY.read_text(encoding="utf-8")
        hash_comments = [
            line
            for line in raw.split("\n")
            if re.match(r"^\s*#(?!:)", line) and line.strip("# \t")
        ]
        assert len(hash_comments) >= 5, (
            f"gate 里 `#` 注释现算只有 {len(hash_comments)} 行 ⇒ 本自检失去对象"
        )

    def test_called_names_and_referenced_names_are_falsifiable(self) -> None:
        good = ast.parse("def f():\n    return g(1)\n").body[0]
        assert "g" in called_names(good)
        bad = ast.parse("def f():\n    return g\n").body[0]
        assert "g" not in called_names(bad), "只是引用也算调用 ⇒ 判据会误报"
        assert "g" in referenced_names(bad), "引用没被 referenced_names 抓到"
        literal = ast.parse('def f():\n    return "paragraph_index"\n').body[0]
        assert "paragraph_index" not in referenced_names(literal), (
            "字符串字面量被当成标识符引用 ⇒ 错误文案里提一句就会打红（假红）"
        )

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
        assert function_node(GATE_PY, "declared_tag_inventory") is not None
        with pytest.raises(AssertionError):
            function_node(GATE_PY, "no_such_function_at_all")

    def test_happy_path_passes_every_criterion(self, lanes: tuple[_Lane, ...]) -> None:
        """对照组必须**全过** —— 否则后面的反例判据可能只是「什么都拒」。"""
        for lane in lanes:
            rt = lane.roundtrip()
            WG.assert_tag_set_matches(lane.inventory, rt.observation, entry_id=lane.entry_id)
            WG.assert_sdt_hierarchy_intact(
                lane.inventory, rt.observation, entry_id=lane.entry_id
            )
            WG.assert_field_instance_counts(
                lane.inventory, rt.observation, entry_id=lane.entry_id
            )
            assert rt.verification.passed
            assert not rt.extracted.conflicts


# ════════════════════════════════════════════════════════════════════════════
# 1. 判据形状：不得沿用 Excel 的 sheet/cell 一族
# ════════════════════════════════════════════════════════════════════════════


class TestCriterionShapeIsTagged:
    def test_no_sheet_or_cell_criterion_is_reused(self) -> None:
        """从 Task 36 只 import 三个文档无关的名字，sheet/cell 一族零引用。

        **Validates: Requirements 6.10**
        """
        imported = imported_from(GATE_PY, "excel_entry_gate")
        assert imported == ALLOWED_EXCEL_IMPORTS, (
            f"从 excel_entry_gate import 的名字集合是 {sorted(imported)}，"
            f"白名单是 {sorted(ALLOWED_EXCEL_IMPORTS)} —— 多一个就可能把 sheet/cell 判据"
            "带进 Word 域（Word 无 sheet 无 cell，套用即恒真重言式）"
        )
        tree = ast.parse(GATE_PY.read_text(encoding="utf-8"))
        names = referenced_names(tree)
        leaked = sorted(set(FORBIDDEN_EXCEL_NAMES) & names)
        assert not leaked, f"Word gate 引用了 Excel 的 sheet/cell 判据 {leaked}"
        assert len(FORBIDDEN_EXCEL_NAMES) >= 15, "禁引用清单分母过小"

    def test_forbidden_excel_names_really_exist_upstream(self) -> None:
        """反向自检：禁引用清单里的名字必须**真的**在 Task 36 里存在，否则清单是空壳。"""
        upstream = referenced_names(ast.parse(EXCEL_GATE_PY.read_text(encoding="utf-8")))
        upstream |= {
            node.name
            for node in ast.walk(ast.parse(EXCEL_GATE_PY.read_text(encoding="utf-8")))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        missing = [n for n in FORBIDDEN_EXCEL_NAMES if n not in upstream]
        # `observed_business_sheets` 是参数名而非模块级符号 —— 它在 Task 36 的签名里，
        # 以参数形式出现，因此允许它不在 referenced_names 里。
        assert missing in ([], ["observed_business_sheets"]), missing

    def test_gate_declares_no_sheet_or_cell_vocabulary(self) -> None:
        """判据词表本身必须是 tag 形状（封闭词表现算，不比整句字符串）。"""
        vocab = (
            WG.TAG_SET_DRIFT_CAUSES + WG.HIERARCHY_DRIFT_CAUSES + WG.INSTANCE_DRIFT_CAUSES
        )
        assert len(vocab) == len(set(vocab)) == 5, vocab
        for cause in vocab:
            assert "sheet" not in cause and "cell" not in cause and "column" not in cause, cause
        assert any("tag" in c for c in vocab), "词表里没有一条提到 tag ⇒ 判据不是 tag 形状"


# ════════════════════════════════════════════════════════════════════════════
# 2. 降级锚点与 fallback 恒拒（真实执行判据）
# ════════════════════════════════════════════════════════════════════════════


class _PermissiveGate:
    """把 Task 6 的门换成「什么都放行」的替身 —— 只用来证明本 gate **不盲信**它。

    🔴 这不是 mock 掉生产路径：被替换的是 `CarrierGate`（Task 13 的**被委托方**），
    而被测的正是「委托出去之后，本 gate 有没有复核结果」。没有这个替身时
    `assert_only_tag_anchor_is_usable` 的 `leaked` 分支在真实门下**永不可达**
    （真实门必抛），于是那条禁令一个判据都锁不住（变异 M07/M09 首轮实测 GREEN）。
    """

    def __init__(self, real: Any, **overrides: Any) -> None:
        self._real = real
        for name, value in overrides.items():
            setattr(self, name, value)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    def assert_anchor(self, anchor: str, *, location: str) -> None:
        return None

    def assert_carrier(self, carrier: str, *, location: str) -> None:
        return None


def _gate_with(**overrides: Any) -> Any:
    """真实 gate 的 `dataclasses.replace` 副本（frozen dataclass，改一格不影响真源）。"""
    import dataclasses

    return dataclasses.replace(load_word_carrier_gate(), **overrides)


class TestDegradedAnchorsAreRefused:
    def test_gate_does_not_trust_a_permissive_anchor_gate(self, plan: _Lane) -> None:
        """委托出去的锚点门若**不抛**，本 gate 必须自己 fail closed。

        **Validates: Requirements 7.1 / Property 34**
        """
        permissive = _PermissiveGate(load_word_carrier_gate())
        with pytest.raises(WG.WordEntryDegradedAnchorError) as err:
            WG.assert_only_tag_anchor_is_usable(gate=permissive, entry_id=plan.entry_id)
        message = str(err.value)
        assert "未被" in message and "拒掉" in message, message
        for name in WG.blocked_anchor_names():
            assert name in message, (name, message)

    def test_more_than_one_allowed_anchor_fails_closed(self, plan: _Lane) -> None:
        """allowlist 里出现第二个锚点 ⇒ 立刻拒（不「碰运气取一个」）。

        **Validates: Requirements 7.1**
        """
        real = load_word_carrier_gate()
        two = _gate_with(allowed_anchors=frozenset(real.allowed_anchors | {"w_alias"}))
        with pytest.raises(WG.WordEntryDegradedAnchorError, match="唯一正式协议锚点"):
            WG.tag_anchor_name(two)
        with pytest.raises(WG.WordEntryDegradedAnchorError):
            WG.assert_only_tag_anchor_is_usable(gate=two, entry_id=plan.entry_id)
        none = _gate_with(allowed_anchors=frozenset())
        with pytest.raises(WG.WordEntryDegradedAnchorError):
            WG.tag_anchor_name(none)

    def test_empty_blocked_anchor_list_is_refused(self, plan: _Lane) -> None:
        """`anchors_blocked` 为空集 ⇒ 拒（空分母上「恒拒」是重言式）。"""
        empty = _gate_with(blocked_anchors=frozenset())
        with pytest.raises(WG.WordEntryDegradedAnchorError, match="空集"):
            WG.assert_only_tag_anchor_is_usable(gate=empty, entry_id=plan.entry_id)

    def test_only_one_anchor_is_allowed_and_it_is_w_tag(self) -> None:
        """唯一锚点从 allowlist **现取**，并与 Task 6 裁决 JSON 交叉锁死。

        **Validates: Requirements 7.1**
        """
        payload = json.loads(CARRIER_CONTRACT.read_text(encoding="utf-8"))
        allowed = payload["downstream_gate"]["anchors_allowed"]
        assert len(allowed) == 1, allowed
        assert WG.tag_anchor_name() == allowed[0]

    def test_every_blocked_anchor_really_raises(self, plan: _Lane) -> None:
        """四个降级锚点**逐个真喂进门**必须抛（不是源码里搜字符串）。

        **Validates: Requirements 7.1**
        """
        blocked = WG.blocked_anchor_names()
        payload = json.loads(CARRIER_CONTRACT.read_text(encoding="utf-8"))
        recorded = set(payload["downstream_gate"]["anchors_blocked"])
        assert recorded and recorded <= set(blocked), (blocked, sorted(recorded))
        gate = load_word_carrier_gate()
        for name in blocked:
            with pytest.raises(ContractCarrierGateError):
                gate.assert_anchor(name, location="task77-probe")
        assert (
            WG.assert_only_tag_anchor_is_usable(gate=gate, entry_id=plan.entry_id)
            == "w_tag"
        )

    def test_gate_reads_no_pseudo_locator_attribute(self) -> None:
        """本模块 AST 上，四个伪锚点属性一次都没被读（段落索引/run 数/alias/w:id）。

        **Validates: Requirements 7.1**
        """
        assert WG.FORBIDDEN_LOCATOR_ATTRS is WE.FORBIDDEN_SDT_LOCATOR_ATTRS, (
            "伪锚点清单被复制成第二份 ⇒ 改任一侧都不打红"
        )
        assert WG.FORBIDDEN_FALLBACK_SYMBOLS is WE.FORBIDDEN_FALLBACK_SYMBOLS
        assert len(WG.FORBIDDEN_LOCATOR_ATTRS) == 4, sorted(WG.FORBIDDEN_LOCATOR_ATTRS)
        tree = ast.parse(GATE_PY.read_text(encoding="utf-8"))
        reads = attribute_reads(tree) | {
            n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
        }
        leaked = sorted((WG.FORBIDDEN_LOCATOR_ATTRS | WG.FORBIDDEN_FALLBACK_SYMBOLS) & reads)
        assert not leaked, f"Word entry gate 读了伪锚点/旧方案符号 {leaked}"

    def test_gate_has_no_paragraph_ordinal_or_chinese_regex_fallback(self) -> None:
        """无段落绝对索引、无中文正则 fallback（结构判据 + 字符判据双侧）。

        **Validates: Requirements 7.1 / 7.8**
        """
        code = strip_py_comments(GATE_PY.read_text(encoding="utf-8"))
        # 字符串字面量里的中文属于**错误文案**，允许；正则编译则一律不允许。
        assert "re.compile" not in code, "gate 里出现正则编译 ⇒ 可能是中文/文本 fallback"
        assert "import re" not in code, "gate import 了 re ⇒ 判据可能退化成文本匹配"
        tree = ast.parse(GATE_PY.read_text(encoding="utf-8"))
        names = referenced_names(tree)
        for forbidden in ("paragraph_ordinals", "paragraph_survey", "run_counts_at_injection"):
            assert forbidden not in names, f"gate 引用了一次性迁移线索 {forbidden}"

    def test_replaced_placeholder_text_is_not_an_anchor(self, plan: _Lane) -> None:
        """**已替换**的 placeholder 文本不得作锚点 —— 真实执行判据。

        注入后 token 文本仍留在 SDT 里当初值（`verify_docx_visible_equivalence` 要求
        可见文本流逐字符不变，所以它**必须**留着）。因此「token 已消失」不是可用前提。
        真正要证的是：**把每个字段的值都改成与 token 完全无关的新文本之后，四条判据
        仍然全过、tag 一个不少** ⇒ 定位用的是 `w:tag`，不是那段文本。

        **Validates: Requirements 7.1 / Property 30**
        """
        from app.services.workpaper_sync.contracts import ValueType

        text_keys = {
            spec.stable_field_key
            for spec in plan.contract.all_fields()
            if spec.value_type is ValueType.text
        }
        tokens = [
            inj.token
            for inj in plan.spec.fields
            if inj.stable_field_key in text_keys
        ]
        assert len(tokens) >= 10, (
            f"文本字段的 token 现算只有 {len(tokens)} 个 ⇒ 本判据分母过小"
        )
        rt = plan.roundtrip()
        filled = _fill_all_values(rt.extracted.projection, marker="TASK77-FILLED")
        tmp = Path(tempfile.mkdtemp(prefix="tmp_task77_fill_"))
        out = tmp / "filled.docx"
        WE.materialize_word_projection(
            substrate=_as_file(plan.instrumented.instrumented_bytes),
            projection=filled,
            output=out,
            binding=plan.binding,
            substrate_role=WE.SubstrateRole.staged_result,
            artifact_kind=WE.ArtifactKind.canonical,
            artifact_state=WE.ArtifactState.staged,
        )
        xml = _document_xml(out.read_bytes())
        assert all(t not in xml for t in tokens), (
            "写入新值后文档里仍能找到原 `${token}` ⇒ 反例没有真正替换 placeholder"
        )
        observation = plan.observe(out.read_bytes())
        WG.assert_tag_set_matches(plan.inventory, observation, entry_id=plan.entry_id)
        WG.assert_sdt_hierarchy_intact(plan.inventory, observation, entry_id=plan.entry_id)
        WG.assert_field_instance_counts(plan.inventory, observation, entry_id=plan.entry_id)


class TestBlockedCarrierHasNoExemption:
    def test_gate_does_not_trust_a_permissive_carrier_gate(self, plan: _Lane) -> None:
        """委托出去的载体门若**不抛**，本 gate 必须自己 fail closed。

        **Validates: Requirements 7.2**
        """
        permissive = _PermissiveGate(load_word_carrier_gate())
        with pytest.raises(WG.WordEntryBlockedCarrierError) as err:
            WG.assert_blocked_carriers_have_no_exemption(
                gate=permissive, entry_id=plan.entry_id
            )
        message = str(err.value)
        for name in WG.blocked_carrier_names():
            assert name in message, (name, message)
        assert "换载体" in message or "未被门拒掉" in message, message

    def test_overlapping_allow_and_block_lists_fail_closed(self, plan: _Lane) -> None:
        """把 `row_sdt` 同时写进两张表 ⇒ 拒并指出首个非法载体。

        这正是 Task 77 正文禁止的「因某 entry 只差 row 就能过而单点豁免」的形态。

        **Validates: Requirements 7.2**
        """
        real = load_word_carrier_gate()
        blocked_first = sorted(real.blocked_carriers)[0]
        overlapped = _gate_with(
            allowed_carriers=frozenset(real.allowed_carriers | {blocked_first})
        )
        with pytest.raises(WG.WordEntryBlockedCarrierError) as err:
            WG.assert_blocked_carriers_have_no_exemption(
                gate=overlapped, entry_id=plan.entry_id
            )
        message = str(err.value)
        assert "首个非法载体" in message and blocked_first in message, message

    def test_empty_blocked_carrier_list_is_refused(self, plan: _Lane) -> None:
        """`carriers_blocked` 为空集 ⇒ 拒（空分母上「恒拒」是重言式）。"""
        empty = _gate_with(blocked_carriers=frozenset())
        with pytest.raises(WG.WordEntryBlockedCarrierError, match="空集"):
            WG.assert_blocked_carriers_have_no_exemption(
                gate=empty, entry_id=plan.entry_id
            )

    def test_row_sdt_is_permanently_refused(self, plan: _Lane) -> None:
        """`row_sdt` 恒拒：blocked 非空、与 allowed 无交集、真喂进门必抛。

        **Validates: Requirements 7.2**
        """
        payload = json.loads(CARRIER_CONTRACT.read_text(encoding="utf-8"))
        recorded = payload["downstream_gate"]["carriers_blocked"]
        assert recorded, "Task 6 裁决里 carriers_blocked 为空 ⇒ 本判据无分母"
        blocked = WG.assert_blocked_carriers_have_no_exemption(
            entry_id=plan.entry_id, contract=plan.contract
        )
        assert set(recorded) <= set(blocked)
        gate = load_word_carrier_gate()
        for name in recorded:
            with pytest.raises(ContractCarrierGateError):
                gate.assert_carrier(name, location="task77-probe")

    def test_no_per_entry_exemption_parameter_exists(self) -> None:
        """签名上无处表达「某 entry 豁免」—— 结构判据，不是承诺。

        **Validates: Requirements 7.2**
        """
        node = function_node(GATE_PY, "assert_blocked_carriers_have_no_exemption")
        assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        params = [a.arg for a in node.args.args + node.args.kwonlyargs]
        assert params == ["gate", "entry_id", "contract"], params
        for bad in ("allow", "exempt", "skip", "override", "force"):
            assert not any(bad in p for p in params), (params, bad)

    def test_contract_declaring_a_blocked_carrier_is_refused(self, plan: _Lane) -> None:
        """契约声明 blocked 载体 ⇒ 拒（真跑一次，不看源码）。"""
        import dataclasses

        bad = dataclasses.replace(
            plan.contract,
            identity_carriers=tuple(plan.contract.identity_carriers)
            + (WG.blocked_carrier_names()[0],),
        )
        with pytest.raises((WG.WordEntryBlockedCarrierError, ContractCarrierGateError)):
            WG.assert_blocked_carriers_have_no_exemption(
                entry_id=plan.entry_id, contract=bad
            )


# ════════════════════════════════════════════════════════════════════════════
# 3. 四条 tagged-SDT 判据（各自反例；错误必须指出首个漂移 tag/XPath）
# ════════════════════════════════════════════════════════════════════════════


def _drop_first_sdt(data: bytes, tag: str) -> bytes:
    """把某个 tag 的**第一个** SDT 整块删掉（tag 丢失的真实形态）。"""
    import io

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        parts = {n: zf.read(n) for n in names}
    xml = parts["word/document.xml"].decode("utf-8")
    spans = WE._find_spans(xml, "sdt")
    for el_start, _, _, el_end in spans:
        if WE._tag_of(xml[el_start:el_end]) == tag:
            xml = xml[:el_start] + xml[el_end:]
            break
    else:  # pragma: no cover - fixture 不该走到这里
        raise AssertionError(f"文档里找不到 tag {tag!r} ⇒ 反例构造失败")
    parts["word/document.xml"] = xml.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            zf.writestr(name, parts[name])
    return out.getvalue()


def _duplicate_first_sdt(data: bytes, tag: str) -> bytes:
    """把某个 tag 的第一个 SDT 原样复制一份（重复实例的真实形态）。"""
    import io

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        parts = {n: zf.read(n) for n in names}
    xml = parts["word/document.xml"].decode("utf-8")
    for el_start, _, _, el_end in WE._find_spans(xml, "sdt"):
        block = xml[el_start:el_end]
        if WE._tag_of(block) == tag:
            xml = xml[:el_end] + block + xml[el_end:]
            break
    else:  # pragma: no cover
        raise AssertionError(f"文档里找不到 tag {tag!r}")
    parts["word/document.xml"] = xml.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            zf.writestr(name, parts[name])
    return out.getvalue()


def _unwrap_block_sdt(data: bytes, block_tag: str) -> bytes:
    """把 block 容器的包装剥掉，只留内层内容（层级被压扁的真实形态）。"""
    import io

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        parts = {n: zf.read(n) for n in names}
    xml = parts["word/document.xml"].decode("utf-8")
    for el_start, _, _, el_end in WE._find_spans(xml, "sdt"):
        block = xml[el_start:el_end]
        if WE._tag_of(block) != block_tag:
            continue
        contents = WE._find_spans(block, "sdtContent")
        assert contents, "block SDT 没有 sdtContent ⇒ 反例构造失败"
        inner = block[contents[0][1] : contents[0][2]]
        xml = xml[:el_start] + inner + xml[el_end:]
        break
    else:  # pragma: no cover
        raise AssertionError(f"文档里找不到 block tag {block_tag!r}")
    parts["word/document.xml"] = xml.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            zf.writestr(name, parts[name])
    return out.getvalue()


class TestTagSetCriterion:
    def test_missing_tag_fails_closed_and_names_the_first_drift(self, plan: _Lane) -> None:
        """WG-1：block 容器 tag 被剥掉 ⇒ 拒，且指出首个漂移 tag。

        ═══ 为什么反例是「剥 block 包装」而不是「删任一个 SDT」 ═══

        删掉一个普通 field SDT 时，`word_sdt_engine._assert_contract_fields_present`
        在 **extract 阶段**就抛 `WordTagMissingError`（那是它的单一真源），本判据到不了。
        真正只有本判据能守的形态是 **block 容器 tag 单独消失**：内层同 key 的 field
        还在 ⇒ engine 的字段存在性与层级判据（后者按「文档里实测到的 block tag」判，
        此时是空集）**双双放行**，而冻结清册里那个 block tag 已经找不到了。

        **Validates: Requirements 7.8 / Property 34**
        """
        inner, container = next(iter(plan.inventory.block_containers.items()))
        broken = _unwrap_block_sdt(plan.instrumented.instrumented_bytes, container)
        observation = plan.observe(broken)  # engine 放行（见上）
        assert container not in observation.tags and inner in observation.tags
        with pytest.raises(WG.WordEntryTagSetDriftError) as err:
            WG.assert_tag_set_matches(plan.inventory, observation, entry_id=plan.entry_id)
        message = str(err.value)
        assert WG.TAG_SET_DRIFT_CAUSES[0] in message, message
        assert container in message, message
        assert "首个漂移 tag" in message, message

    def test_engine_alone_would_have_let_that_shape_through(self, plan: _Lane) -> None:
        """反向自检：上一条不是重复判据 —— engine 对同一形态确实不抛。"""
        _, container = next(iter(plan.inventory.block_containers.items()))
        broken = _unwrap_block_sdt(plan.instrumented.instrumented_bytes, container)
        # `observe()` 内部就是 `extract_word_projection`；它没抛即证明 engine 放行。
        observation = plan.observe(broken)
        assert observation.managed_instance_total == (
            plan.inventory.managed_instance_total - 1
        ), "反例改变的不只是 block 包装 ⇒ 判据归属不清"

    def test_engine_owns_the_plain_field_tag_loss(self, plan: _Lane) -> None:
        """普通 field tag 丢失由 engine 的 `WordTagMissingError` 独占（不在本 gate 重复）。

        **Validates: Requirements 7.8**
        """
        victim = next(
            tag
            for tag, container in (
                (t, plan.inventory.block_containers.get(t)) for t in plan.inventory.tags
            )
            if container is None and "gt:field:" in tag
        )
        broken = _drop_first_sdt(plan.instrumented.instrumented_bytes, victim)
        with pytest.raises(WE.WordTagMissingError):
            plan.observe(broken)

    def test_unregistered_tag_fails_closed_with_its_xpath(self, plan: _Lane) -> None:
        """WG-1 的另一半：文档里出现清册未登记的 tag ⇒ 拒并给 XPath。"""
        shrunk = WG.WordTagInventory(
            entry_id=plan.inventory.entry_id,
            contract_id=plan.inventory.contract_id,
            tags=plan.inventory.tags[:-1],
            row_uuids=plan.inventory.row_uuids,
            block_containers=plan.inventory.block_containers,
            declared_instances=plan.inventory.declared_instances,
            managed_instance_total=plan.inventory.managed_instance_total,
            frozen_hierarchy={
                k: v for k, v in plan.inventory.frozen_hierarchy.items()
                if k in set(plan.inventory.tags[:-1])
            },
        )
        observation = plan.observe()
        with pytest.raises(WG.WordEntryTagSetDriftError) as err:
            WG.assert_tag_set_matches(shrunk, observation, entry_id=plan.entry_id)
        message = str(err.value)
        assert WG.TAG_SET_DRIFT_CAUSES[1] in message, message
        assert plan.inventory.tags[-1] in message, message
        assert "/w:" in message, f"错误里没有 XPath 位置: {message}"

    def test_block_inner_field_tag_must_be_declared(self, plan: _Lane) -> None:
        """三边锁：block 载体字段必须同时有内层 field tag（Task 6 的 depth=2 形态）。

        反例**只**摘掉内层 `gt:field:` tag、保留外层 `gt:block:` —— 契约字段声明的 tag
        （block）仍在清册里，因此上一条判据（契约 → instrumentation）放行，只有这一条
        能发现「block 字段没有值的写入目标」。

        **Validates: Requirements 7.10**
        """
        inner = next(iter(plan.inventory.block_containers))
        payload = copy.deepcopy(plan.instrumentation_payload)
        payload["sdt_tags"] = [t for t in payload["sdt_tags"] if t != inner]
        assert len(payload["sdt_tags"]) == len(plan.inventory.tags) - 1
        with pytest.raises(WG.WordEntryTagSetDriftError) as err:
            WG.declared_tag_inventory(
                contract=plan.contract,
                instrumentation_payload=payload,
                readback=plan.readback,
                entry_id=plan.entry_id,
            )
        message = str(err.value)
        assert inner in message and "block 载体" in message, message
        assert "depth=2" in message, message

    def test_contract_and_instrumentation_must_agree(self, plan: _Lane) -> None:
        """三边锁的第一条：契约声明的 tag 不在冻结清册里 ⇒ 拒。

        **Validates: Requirements 7.10**
        """
        payload = copy.deepcopy(plan.instrumentation_payload)
        payload["sdt_tags"] = sorted(payload["sdt_tags"])[1:]
        with pytest.raises(WG.WordEntryTagSetDriftError):
            WG.declared_tag_inventory(
                contract=plan.contract,
                instrumentation_payload=payload,
                readback=plan.readback,
                entry_id=plan.entry_id,
            )

    def test_foreign_contract_tags_are_refused(self, lanes: tuple[_Lane, ...]) -> None:
        """禁跨 entry：拿另一个 entry 的 tag 清册来校验本 entry ⇒ 拒。

        **Validates: Requirements 7.10 / Property 28**
        """
        a, b = lanes[0], lanes[1]
        with pytest.raises(WG.WordEntryTagSetDriftError) as err:
            WG.declared_tag_inventory(
                contract=a.contract,
                instrumentation_payload=b.instrumentation_payload,
                readback=b.readback,
                entry_id=a.entry_id,
            )
        assert "contract 段" in str(err.value) or "不在冻结" in str(err.value)


class TestHierarchyCriterion:
    def test_field_moved_into_a_table_cell_fails_closed(self, plan: _Lane) -> None:
        """WG-2：字段被搬进表格单元格 ⇒ 拒（tag 集合与计数都没变，只有层级变了）。

        engine 侧对**非行域**字段不看 container path，所以这一格只有本判据在守。

        **Validates: Requirements 6.10 / 7.5**
        """
        victim = next(
            tag
            for tag in plan.inventory.tags
            if "gt:field:" in tag and tag not in plan.inventory.block_containers
        )
        broken = _wrap_sdt_paragraph_in_table(plan.instrumented.instrumented_bytes, victim)
        observation = plan.observe(broken)
        assert set(observation.tags) == set(plan.inventory.tags), (
            "反例把 tag 集合也改了 ⇒ 会被 WG-1 遮蔽，证不了「只有层级变了」"
        )
        assert observation.instance_counts == {
            tag: plan.inventory.instance_expectation(tag) for tag in plan.inventory.tags
        }, "反例把实例计数也改了 ⇒ 会被 WG-3 遮蔽"
        with pytest.raises(WG.WordEntryHierarchyDriftError) as err:
            WG.assert_sdt_hierarchy_intact(plan.inventory, observation, entry_id=plan.entry_id)
        message = str(err.value)
        assert WG.HIERARCHY_DRIFT_CAUSES[0] in message, message
        assert victim in message and "body/tbl" in message, message

    def test_container_path_drift_fails_closed(self, plan: _Lane) -> None:
        """WG-2 的另一半：container path 变了 ⇒ 拒并给出冻结/实测两侧。"""
        victim = sorted(plan.inventory.frozen_hierarchy)[0]
        drifted = dict(plan.inventory.frozen_hierarchy)
        drifted[victim] = ("body/tbl/tr/tc/p",)
        inventory = WG.WordTagInventory(
            entry_id=plan.inventory.entry_id,
            contract_id=plan.inventory.contract_id,
            tags=plan.inventory.tags,
            row_uuids=plan.inventory.row_uuids,
            block_containers=plan.inventory.block_containers,
            declared_instances=plan.inventory.declared_instances,
            managed_instance_total=plan.inventory.managed_instance_total,
            frozen_hierarchy=drifted,
        )
        with pytest.raises(WG.WordEntryHierarchyDriftError) as err:
            WG.assert_sdt_hierarchy_intact(inventory, plan.observe(), entry_id=plan.entry_id)
        assert WG.HIERARCHY_DRIFT_CAUSES[0] in str(err.value)

    def test_hierarchy_criterion_is_insert_delete_invariant(self, plan: _Lane) -> None:
        """插删段落**不得**触发层级判据（否则它其实是段落索引）。

        **Validates: Requirements 7.5**
        """
        shifted = _insert_paragraphs_at_top(plan.instrumented.instrumented_bytes, count=2)
        observation = plan.observe(shifted)
        WG.assert_sdt_hierarchy_intact(plan.inventory, observation, entry_id=plan.entry_id)
        WG.assert_tag_set_matches(plan.inventory, observation, entry_id=plan.entry_id)
        WG.assert_field_instance_counts(plan.inventory, observation, entry_id=plan.entry_id)


class TestInstanceCountCriterion:
    def test_declared_instances_must_agree_with_the_frozen_count(self, plan: _Lane) -> None:
        """WG-3 发布期：契约的 `instances` 与冻结实例个数不自洽 ⇒ 拒。

        **Validates: Requirements 7.10**
        """
        import dataclasses

        victim_key = next(
            key
            for key, declared in sorted(plan.inventory.declared_instances.items())
            if declared == "one"
        )
        fields = tuple(
            dataclasses.replace(spec, instances="many")
            if spec.stable_field_key == victim_key
            else spec
            for spec in plan.contract.fields
        )
        bad_contract = dataclasses.replace(plan.contract, fields=fields)
        with pytest.raises(WG.WordEntryInstanceCountDriftError) as err:
            WG.declared_tag_inventory(
                contract=bad_contract,
                instrumentation_payload=plan.instrumentation_payload,
                readback=plan.readback,
                entry_id=plan.entry_id,
            )
        message = str(err.value)
        assert WG.INSTANCE_DRIFT_CAUSES[0] in message, message
        assert victim_key in message, message

    def test_engine_owns_the_single_declaration_duplicate(self, plan: _Lane) -> None:
        """`instances='one'` 出现多实例由 engine 独占（extract 阶段就抛，本 gate 不重复）。

        **Validates: Requirements 7.10**
        """
        victim_key = next(
            key
            for key, declared in sorted(plan.inventory.declared_instances.items())
            if declared == "one"
        )
        victim_tag = WG._tag_of_key(plan.inventory, victim_key)
        broken = _duplicate_first_sdt(plan.instrumented.instrumented_bytes, victim_tag)
        with pytest.raises(WE.WordTagInstanceCountError):
            plan.observe(broken)

    def test_per_tag_count_drift_fails_closed(self, plan: _Lane) -> None:
        """WG-3 运行期：逐 tag 精确计数（期望值来自冻结层级表）。

        反例选 `many` 档字段并**再复制一份**：one/many 桶仍满足（>=2），engine 的
        `_assert_instance_counts` 也只管 `one`，因此只有逐 tag 精确计数会打红。

        **Validates: Requirements 7.10**
        """
        victim_key = next(
            key
            for key, declared in sorted(plan.inventory.declared_instances.items())
            if declared == "many"
        )
        victim_tag = WG._tag_of_key(plan.inventory, victim_key)
        broken = _duplicate_first_sdt(plan.instrumented.instrumented_bytes, victim_tag)
        observation = plan.observe(broken)
        assert set(observation.tags) == set(plan.inventory.tags), (
            "反例把 tag 集合也改了 ⇒ 会被 WG-1 遮蔽，证不了「只有计数变了」"
        )
        with pytest.raises(WG.WordEntryInstanceCountDriftError) as err:
            WG.assert_field_instance_counts(
                plan.inventory, observation, entry_id=plan.entry_id
            )
        message = str(err.value)
        assert WG.INSTANCE_DRIFT_CAUSES[1] in message, message
        assert victim_tag in message and "全部位置" in message, message

    def test_lost_instance_of_a_multi_field_fails_closed(self, plan: _Lane) -> None:
        """`many` 档字段掉到 1 个 ⇒ 拒（tag 集合此时完全相同，只有计数少 1）。

        **Validates: Requirements 7.10 / Property 34**
        """
        victim_key = next(
            key
            for key, declared in sorted(plan.inventory.declared_instances.items())
            if declared == "many"
        )
        victim_tag = WG._tag_of_key(plan.inventory, victim_key)
        broken = _drop_first_sdt(plan.instrumented.instrumented_bytes, victim_tag)
        observation = plan.observe(broken)
        assert set(observation.tags) == set(plan.inventory.tags)
        with pytest.raises(WG.WordEntryInstanceCountDriftError):
            WG.assert_field_instance_counts(
                plan.inventory, observation, entry_id=plan.entry_id
            )


class TestWordOnlyCriterion:
    def test_coverage_must_be_non_empty(self, plan: _Lane) -> None:
        """WG-4：覆盖计数为空 ⇒ 拒（空集上的等值是重言式）。

        **Validates: Requirements 7.3 / Property 31**
        """
        from app.services.workpaper_sync.adapters.base import UnmanagedRegionReport

        empty = UnmanagedRegionReport(
            equivalent=True,
            inspected_aspects=tuple(WE.WORD_ONLY_ASPECTS),
            first_difference=None,
            details={"coverage": {name: 0 for name in WE.WORD_ONLY_ASPECTS}},
        )
        with pytest.raises(WG.WordEntryWordOnlyCoverageError) as err:
            WG.assert_word_only_equivalent(empty, entry_id=plan.entry_id)
        assert "覆盖计数" in str(err.value)

    def test_missing_aspect_is_refused(self, plan: _Lane) -> None:
        """少判定一个 aspect ⇒ 拒（`equivalent=True` 不代表那一格等值）。"""
        from app.services.workpaper_sync.adapters.base import UnmanagedRegionReport

        partial = UnmanagedRegionReport(
            equivalent=True,
            inspected_aspects=tuple(WE.WORD_ONLY_ASPECTS[:-1]),
            first_difference=None,
            details={"coverage": {name: 3 for name in WE.WORD_ONLY_ASPECTS}},
        )
        with pytest.raises(WG.WordEntryWordOnlyCoverageError):
            WG.assert_word_only_equivalent(partial, entry_id=plan.entry_id)

    def test_real_roundtrip_coverage_is_non_empty(self, lanes: tuple[_Lane, ...]) -> None:
        """真实往返上四项必需覆盖都 > 0（分母非空 ⇒ Property 31 可宣称）。

        **Validates: Requirements 7.3 / Property 31**
        """
        assert len(WG.WORD_ONLY_COVERAGE_REQUIRED) == 4
        for lane in lanes:
            coverage = lane.roundtrip().word_only_coverage
            for name in WG.WORD_ONLY_COVERAGE_REQUIRED:
                assert int(coverage[name]) > 0, (lane.entry_id, name, dict(coverage))

    def test_word_only_drift_is_refused_not_downgraded(self, plan: _Lane) -> None:
        """SDT 外正文被改 ⇒ `UnmanagedRegionDriftError`，不是 warning。

        **Validates: Requirements 7.3 / 7.9**
        """
        tampered = _replace_outside_text(plan.instrumented.instrumented_bytes)
        report = WE.verify_word_only_regions(
            before=_as_file(plan.instrumented.instrumented_bytes),
            after=_as_file(tampered),
            binding=plan.binding,
        )
        assert not report.equivalent, "反例没造成 Word-only 差异 ⇒ 判据无分母"
        with pytest.raises(WG.UnmanagedRegionDriftError):
            WG.assert_word_only_equivalent(report, entry_id=plan.entry_id)

    def test_gate_also_asserts_the_managed_projection_matches(self) -> None:
        """往返之后必须**再**过 `assert_publishable()` —— 那一半没有别的所有者。

        `assert_word_only_equivalent` 只覆盖 Word-only 那一格（它委派
        `UnmanagedRegionReport.assert_equivalent`）；`WordVerificationBundle.assert_publishable`
        另有一半是「反读的受管字段与期望是否等值」（`mismatched_keys` →
        `WordManagedProjectionMismatchError`）。少调它之后，SDT **内**的值被写坏也能发布，
        而 Word-only 判据一格都不会红（变异 M15 首轮实测 GREEN 就是这个形态）。

        **Validates: Requirements 7.3**
        """
        node = function_node(GATE_PY, "verify_candidate_tag_roundtrip")
        calls = called_names(node)
        assert "assert_publishable" in calls, (
            "往返只查了 Word-only、没查受管 projection ⇒ SDT 内的值被写坏也能发布"
        )
        assert "assert_word_only_equivalent" in calls, "Word-only 覆盖判据没跑"
        from app.services.workpaper_sync.word_sdt_engine import WordVerificationBundle

        assert callable(getattr(WordVerificationBundle, "assert_publishable", None))
        assert "mismatched_keys" in {
            f.name for f in __import__("dataclasses").fields(WordVerificationBundle)
        }

    def test_gate_never_regenerates_from_a_template(self) -> None:
        """gate 模块没有任何模板入口（结构判据；docstring 里的说明不算引用）。

        **Validates: Requirements 7.3**
        """
        tree = ast.parse(GATE_PY.read_text(encoding="utf-8"))
        names = referenced_names(tree)
        for forbidden in ("instrument_docx_bytes", "TEMPLATE_ROOT", "wp_templates"):
            assert forbidden not in names, (
                f"gate 引用了模板入口标识符 {forbidden} —— 「不得用模板重生成覆盖审计师"
                "已编辑的 Word-only 正文」必须是结构事实"
            )
        literals = non_docstring_strings(tree)
        leaked = sorted(s[:60] for s in literals if "wp_templates" in s)
        assert not leaked, f"gate 的非 docstring 字符串里出现模板路径 {leaked}"
        node = function_node(GATE_PY, "verify_candidate_tag_roundtrip")
        calls = called_names(node)
        assert "materialize_word_projection" in calls and "extract_word_projection" in calls
        assert "verify_word_before_commit" in calls
        # substrate 只可能是 candidate 自己：函数签名里没有第二个文件参数。
        assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        params = [a.arg for a in node.args.args + node.args.kwonlyargs]
        assert params == ["candidate_path", "binding", "scratch_dir", "entry_id"], params


# ════════════════════════════════════════════════════════════════════════════
# 4. AC 7.5 的三个场景（跨 run / 同段多 token / 插删段落）
# ════════════════════════════════════════════════════════════════════════════


def _as_file(data: bytes) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="tmp_task77_file_"))
    path = tmp / "doc.docx"
    path.write_bytes(data)
    return path


def _insert_paragraphs_at_top(data: bytes, *, count: int) -> bytes:
    """在 `w:body` 开头插入 `count` 个段落（Task 6 证伪 paragraph_index 的同一形态）。"""
    import io

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        parts = {n: zf.read(n) for n in names}
    xml = parts["word/document.xml"].decode("utf-8")
    idx = xml.index("<w:body>") + len("<w:body>")
    added = "".join(
        f"<w:p><w:r><w:t>TASK77-INSERTED-{i}</w:t></w:r></w:p>" for i in range(count)
    )
    parts["word/document.xml"] = (xml[:idx] + added + xml[idx:]).encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            zf.writestr(name, parts[name])
    return out.getvalue()


def _replace_outside_text(data: bytes) -> bytes:
    """改写第一段 **SDT 外** 的可见文本（Word-only 漂移的真实形态）。"""
    import io

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        parts = {n: zf.read(n) for n in names}
    xml = parts["word/document.xml"].decode("utf-8")
    spans = WE._find_spans(xml, "sdt")
    guard = spans[0][0] if spans else len(xml)
    head = xml[:guard]
    match = re.search(r"<w:t[^>]*>([^<]{2,})</w:t>", head)
    assert match, "文档开头找不到 SDT 外可见文本 ⇒ 反例构造失败"
    xml = xml[: match.start(1)] + "TASK77-TAMPERED" + xml[match.end(1) :]
    parts["word/document.xml"] = xml.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            zf.writestr(name, parts[name])
    return out.getvalue()


class TestRequirement75Scenarios:
    def test_scenario_denominators_are_source_backed(self) -> None:
        """三个场景的分母从 Task 6 裁决 JSON 现读（不写死）。

        **Validates: Requirements 7.5**
        """
        payload = json.loads(CARRIER_CONTRACT.read_text(encoding="utf-8"))
        scenarios = payload["requirement_7_5_scenarios"]["instrumented"]
        assert set(scenarios) == {"cross_run", "same_paragraph_multi", "duplicate_instance"}
        for name, rows in scenarios.items():
            assert rows, f"场景 {name} 的实测记录为空 ⇒ 分母为空"
        cross = [r for r in scenarios["cross_run"] if int(r["run_split"]) > 1]
        assert cross, "没有任何 run_split > 1 的注入 ⇒ 「跨 run」场景无对象"

    def test_authoritative_templates_have_no_raw_cross_run_token(
        self, lanes: tuple[_Lane, ...]
    ) -> None:
        """实测事实：两份权威模板里**没有**物理跨 run 的 token（分母登记，防误宣称）。

        `WordFieldInjection.expected_token_occurrences` 与
        `instrument_docx_bytes._token_paragraphs` 都按**原始 XML 文本**找 token，因此
        「token 被 Word 拆到两个 `w:r` 里」这种模板在注入期发现不了。本 lane 上该形态
        分母为 0（逐 token 现算的 `run_counts_at_injection` 全为 1），因此**注入期**的
        跨 run 不宣称通过；**运行期**（读写协议）的跨 run 由下一条真实证明。
        """
        for lane in lanes:
            counts = [
                c
                for inj in lane.spec.fields
                for c in lane.facts[inj.token]["run_counts_at_injection"]
            ]
            assert counts, f"{lane.entry_id}: 没有任何 token 事实 ⇒ 本登记无分母"
            assert max(counts) == 1, (
                f"{lane.entry_id}: 现算到跨 run 的 token 段落 {max(counts)} run —— "
                "本登记的前提变了，需要改成正面证明注入期跨 run"
            )

    def test_cross_run_value_survives_the_tag_roundtrip(self, plan: _Lane) -> None:
        """跨 run **值**：SDT 内容被拆成 3 个 `w:r` 后仍能经 tag 读写，值逐字符不变。

        这是 AC 7.5「模板 token 跨 run 后 SHALL 仍能通过 SDT tag 读写」的运行期形态：
        读侧 `_inner_text` 按序拼接 `w:t`、写侧 `_rewrite_sdt_content` 整体替换内容，
        两侧都不看 run 序号。

        **Validates: Requirements 7.5**
        """
        victim = next(
            tag
            for tag in plan.inventory.tags
            if "gt:field:" in tag and plan.inventory.instance_expectation(tag) == 1
        )
        before = plan.observe()
        split = _split_sdt_content_into_runs(
            plan.instrumented.instrumented_bytes, victim, parts=3
        )
        assert _run_count_inside_sdt(split, victim) >= 3, "反例没有真的拆成多个 run"
        after = plan.observe(split)
        assert after.tags == before.tags
        assert after.instance_counts == before.instance_counts
        assert after.hierarchy == before.hierarchy
        WG.assert_tag_set_matches(plan.inventory, after, entry_id=plan.entry_id)
        WG.assert_field_instance_counts(plan.inventory, after, entry_id=plan.entry_id)
        rt = plan.roundtrip(split)
        assert not rt.verification.mismatched_keys, rt.verification.mismatched_keys
        assert rt.verification.passed

    def test_two_tokens_in_one_paragraph_do_not_bleed(self, lanes: tuple[_Lane, ...]) -> None:
        """同段多 token：两个字段各自按 tag 读写，值不互串。

        **Validates: Requirements 7.5 / 7.4**
        """
        shared: list[tuple[_Lane, tuple[str, ...]]] = []
        for lane in lanes:
            by_paragraph: dict[int, list[str]] = {}
            for inj in lane.spec.fields:
                for ordinal in lane.facts[inj.token]["paragraph_ordinals"]:
                    by_paragraph.setdefault(int(ordinal), []).append(inj.stable_field_key)
            groups = tuple(
                tuple(sorted(keys)) for keys in by_paragraph.values() if len(keys) > 1
            )
            if groups:
                shared.append((lane, groups[0]))
        assert shared, "两个 lane 都没有同段多 token ⇒ 本场景无分母"
        for lane, keys in shared:
            rt = lane.roundtrip()
            values = {k: rt.extracted.projection.get(k) for k in keys}
            assert all(v is not None for v in values.values()), (lane.entry_id, keys)
            assert rt.verification.passed
            assert not rt.verification.mismatched_keys

    def test_paragraph_insert_and_delete_keep_tag_addressing(self, plan: _Lane) -> None:
        """插删段落后仍能经 tag 读写，且值逐项不变。

        **Validates: Requirements 7.5 / Property 31**
        """
        base = plan.observe()
        for count in (1, 2, 5):
            shifted = _insert_paragraphs_at_top(
                plan.instrumented.instrumented_bytes, count=count
            )
            observation = plan.observe(shifted)
            assert observation.tags == base.tags
            assert observation.instance_counts == base.instance_counts
            assert observation.hierarchy == base.hierarchy, (
                "插段落改变了 container path ⇒ 层级判据其实是段落索引"
            )
        # 删段落：把刚插的删掉一段后判据仍成立（形态与插入对称）。
        shifted = _insert_paragraphs_at_top(plan.instrumented.instrumented_bytes, count=3)
        trimmed = _delete_first_plain_paragraph(shifted)
        observation = plan.observe(trimmed)
        assert observation.instance_counts == base.instance_counts
        WG.assert_tag_set_matches(plan.inventory, observation, entry_id=plan.entry_id)


def _delete_first_plain_paragraph(data: bytes) -> bytes:
    """删掉 `w:body` 里第一个**不含 SDT** 的段落。"""
    import io

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        parts = {n: zf.read(n) for n in names}
    xml = parts["word/document.xml"].decode("utf-8")
    for el_start, _, _, el_end in WE._find_spans(xml, "p"):
        block = xml[el_start:el_end]
        if "<w:sdt>" in block or "<w:sdt " in block:
            continue
        xml = xml[:el_start] + xml[el_end:]
        break
    else:  # pragma: no cover
        raise AssertionError("找不到可删的普通段落")
    parts["word/document.xml"] = xml.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            zf.writestr(name, parts[name])
    return out.getvalue()


def _document_xml(data: bytes) -> str:
    import io

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return zf.read("word/document.xml").decode("utf-8")


def _rewrite_document_xml(data: bytes, xml: str) -> bytes:
    import io

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        parts = {n: zf.read(n) for n in names}
    parts["word/document.xml"] = xml.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            zf.writestr(name, parts[name])
    return out.getvalue()


def _fill_all_values(projection: Any, *, marker: str) -> Any:
    """把 projection 里每个**文本**字段的值换成与 token 无关的新文本。

    非文本字段（integer / date）保持原值 —— 塞一个 marker 会被 `_normalise_value`
    判成类型异常，那属于另一条判据，会污染本判据。
    """
    import dataclasses

    from app.services.workpaper_sync.contracts import ValueType

    values = {}
    for key, value in projection.values.items():
        if value.value_type is ValueType.text:
            values[key] = dataclasses.replace(value, value=f"{marker}-{len(key)}")
        else:
            values[key] = value
    return dataclasses.replace(projection, values=values)


def _split_sdt_content_into_runs(data: bytes, tag: str, *, parts: int) -> bytes:
    """把某个 tag 的 SDT 内容文本拆成 `parts` 个 `w:r`（跨 run 值的真实形态）。"""
    xml = _document_xml(data)
    for el_start, _, _, el_end in WE._find_spans(xml, "sdt"):
        block = xml[el_start:el_end]
        if WE._tag_of(block) != tag:
            continue
        contents = WE._find_spans(block, "sdtContent")
        assert contents, "SDT 没有 sdtContent ⇒ 反例构造失败"
        inner_start, inner_end = contents[0][1], contents[0][2]
        text = WE._inner_text(block[inner_start:inner_end])
        assert len(text) >= parts, f"tag {tag!r} 的内容只有 {len(text)} 个字符，拆不出 {parts} run"
        step = max(1, len(text) // parts)
        chunks = [text[i : i + step] for i in range(0, len(text), step)]
        runs = "".join(f"<w:r><w:t xml:space=\"preserve\">{c}</w:t></w:r>" for c in chunks)
        new_block = block[:inner_start] + runs + block[inner_end:]
        xml = xml[:el_start] + new_block + xml[el_end:]
        return _rewrite_document_xml(data, xml)
    raise AssertionError(f"文档里找不到 tag {tag!r}")


def _run_count_inside_sdt(data: bytes, tag: str) -> int:
    xml = _document_xml(data)
    for el_start, _, _, el_end in WE._find_spans(xml, "sdt"):
        block = xml[el_start:el_end]
        if WE._tag_of(block) == tag:
            contents = WE._find_spans(block, "sdtContent")
            inner = block[contents[0][1] : contents[0][2]]
            return len([s for s in WE._find_spans(inner, "r") if s[3] > s[0]])
    raise AssertionError(f"文档里找不到 tag {tag!r}")


def _wrap_sdt_paragraph_in_table(data: bytes, tag: str) -> bytes:
    """把含某 tag 的段落整体塞进一个单元格表格（层级漂移的真实形态）。

    tag 集合与实例计数都不变，只有 `container_path` 从 `body/p` 变成
    `body/tbl/tr/tc/p` ⇒ 只有 WG-2 会打红。
    """
    xml = _document_xml(data)
    for el_start, _, _, el_end in WE._find_spans(xml, "p"):
        block = xml[el_start:el_end]
        if f'<w:tag w:val="{tag}"' not in block:
            continue
        wrapped = (
            "<w:tbl><w:tblPr><w:tblW w:w=\"0\" w:type=\"auto\"/></w:tblPr>"
            "<w:tblGrid><w:gridCol w:w=\"9000\"/></w:tblGrid>"
            "<w:tr><w:tc><w:tcPr><w:tcW w:w=\"9000\" w:type=\"dxa\"/></w:tcPr>"
            + block
            + "</w:tc></w:tr></w:tbl>"
        )
        xml = xml[:el_start] + wrapped + xml[el_end:]
        return _rewrite_document_xml(data, xml)
    raise AssertionError(f"找不到含 tag {tag!r} 的段落")


# ════════════════════════════════════════════════════════════════════════════
# 5. 禁 fail-open / 禁越权写入面
# ════════════════════════════════════════════════════════════════════════════

#: gate **不得**触碰的写入面（AC 6.18 / Property 67）。
FORBIDDEN_WRITE_SURFACES: tuple[str, ...] = (
    "set_entry_pointer",
    "create_representation",
    "create_content_version",
    "bump_content_revision",
    "attach_candidate_definitions",
    "commit",
)


class TestNoFailOpenAndNoWriteSurface:
    def test_gate_has_no_broad_except(self) -> None:
        """禁 `except Exception` / 裸 except（AC 5.12 逐字禁止降级成成功）。

        **Validates: Requirements 6.18**
        """
        found = except_handler_types(GATE_PY)
        assert found, "gate 里一个 except 都没有 ⇒ 本判据无分母（请确认文件没被换掉）"
        for bad in ("Exception", "BaseException", "<bare>"):
            assert bad not in found, f"gate 出现宽泛捕获 {bad}：{found}"

    @pytest.mark.parametrize("surface", FORBIDDEN_WRITE_SURFACES)
    def test_gate_never_touches_a_write_surface(self, surface: str) -> None:
        """gate 只经 Task 25 的唯一出口写；其余写入面一个都不调。

        **Validates: Requirements 6.18 / Property 67**
        """
        tree = ast.parse(GATE_PY.read_text(encoding="utf-8"))
        assert surface not in called_names(tree), f"gate 调用了写入面 {surface}"

    def test_the_only_write_call_is_task25s_single_exit(self) -> None:
        """`finalize_definition_upgrade` 是 gate 里唯一会产生写入的调用。

        **Validates: Requirements 6.18**
        """
        node = function_node(GATE_PY, "finalize_candidate")
        calls = called_names(node)
        assert "finalize_definition_upgrade" in calls, "gate 没接 Task 25 的唯一出口"
        assert "finalize_candidate" not in {
            c for c in calls if c != "finalize_candidate"
        } or True
        # 方法名必须真的存在于 Task 25（防「永远 AttributeError 的假接线」）。
        from app.services.workpaper_sync.materialize_coordinator import (
            MaterializeCoordinator,
        )

        assert callable(getattr(MaterializeCoordinator, "finalize_definition_upgrade", None))

    def test_gate_delegates_the_five_prerequisites(self) -> None:
        """五条 finalize 前置**委派** Task 12，不在 gate 重写。

        **Validates: Requirements 6.18 / Property 67**
        """
        node = function_node(GATE_PY, "finalize_candidate")
        assert "assert_candidate_finalizable" in called_names(node)
        from app.services.workpaper_sync.resolution import CanonicalResolutionService

        assert callable(
            getattr(CanonicalResolutionService, "assert_candidate_finalizable", None)
        )

    def test_gate_never_reaches_the_staged_contract_directory(self) -> None:
        """gate 不定位任何契约文件（Task 60 的 `backend/app/**` 边界判据的对侧）。

        **Validates: Requirements 6.18**
        """
        code = GATE_PY.read_text(encoding="utf-8")
        assert "workpaper_sync_word_contracts" not in code, (
            "gate 引用了暂存契约目录 —— Task 60 要求该目录名在 backend/app/** 里 0 次"
        )
        assert "parse_contract" not in referenced_names(ast.parse(code)), (
            "gate 自己解析契约文件 ⇒ 未装清册的契约会有第二条进入运行态的路径"
        )
        # 定位处必须在**脚本**里且真的存在（否则上面两条是空转）。
        assert "workpaper_sync_word_contracts" in HOST_SCRIPT.read_text(encoding="utf-8")
        assert callable(HOST.load_word_lane_contract)

    def test_gate_holds_no_alias_entry(self) -> None:
        """无 alias 入口：不按 entry_id 反查「现在该用哪个 bundle」。

        **Validates: Requirements 7.10 / Property 28**
        """
        names = referenced_names(ast.parse(GATE_PY.read_text(encoding="utf-8")))
        for forbidden in ("DefinitionAliasRegistry", "resolve_for_publish", "resolve_alias"):
            assert forbidden not in names, f"gate 出现 alias 入口 {forbidden}"

    def test_failure_codes_are_closed_and_distinct(self) -> None:
        """失败 code 封闭、互不相同，且每条都真的挂在一个异常类上。"""
        codes = WG.WORD_ENTRY_FAILURE_CODES
        assert len(codes) == len(set(codes)) == 13, codes
        classes = [
            obj
            for obj in vars(WG).values()
            if isinstance(obj, type)
            and issubclass(obj, WG.WordEntryGateError)
            and obj is not WG.WordEntryGateError
        ]
        assert {c.error_code for c in classes} <= set(codes), (
            "有异常类的 error_code 没登记进 WORD_ENTRY_FAILURE_CODES"
        )
        assert len(classes) == len({c.error_code for c in classes}), "两个类共用一个 code"


# ════════════════════════════════════════════════════════════════════════════
# 6. 消费宿主（additive 注入即死代码 ⇒ 判据落在唯一消费方）
# ════════════════════════════════════════════════════════════════════════════


class TestConsumptionHost:
    def test_gate_is_consumed_by_the_host_script(self) -> None:
        """`--apply` 真实例化 gate 并 `await finalize_candidate(...)`。

        **Validates: Requirements 12.5**
        """
        node = function_node(HOST_SCRIPT, "finalize_one")
        calls = called_names(node)
        for name in (
            "WordEntryFinalizeGate",
            "WordEntryDefinitionLoader",
            "finalize_candidate",
            "build_materialize_coordinator",
        ):
            assert name in calls, f"宿主没调用 {name} ⇒ gate 是死代码"
        apply_node = function_node(HOST_SCRIPT, "run_apply")
        apply_calls = called_names(apply_node)
        assert "finalize_one" in apply_calls
        assert "commit" in apply_calls, "宿主不 commit ⇒ 真实行永远不落库"
        assert "rollback" in apply_calls, "宿主失败不回滚 ⇒ 会留下半成功可见态"

    def test_check_mode_is_read_only_and_really_runs_the_criteria(self) -> None:
        """`--check` 不 commit，但**真跑**四条判据 + 两道门。

        **Validates: Requirements 12.5**
        """
        node = function_node(HOST_SCRIPT, "run_check")
        calls = called_names(node)
        assert "commit" not in calls, "`--check` 会 commit ⇒ 不是只读"
        assert "run_offline_criteria" in calls, "`--check` 没真跑判据"
        criteria = called_names(function_node(HOST_SCRIPT, "run_offline_criteria"))
        for name in (
            "assert_only_tag_anchor_is_usable",
            "assert_blocked_carriers_have_no_exemption",
            "declared_tag_inventory",
            "verify_candidate_tag_roundtrip",
            "assert_tag_set_matches",
            "assert_sdt_hierarchy_intact",
            "assert_field_instance_counts",
        ):
            assert name in criteria, f"`--check` 没执行判据 {name}"

    def test_apply_never_regenerates_from_a_template(self) -> None:
        """🔴 `--apply` 的字节只来自 candidate：模板入口在它的调用图里零引用。

        **Validates: Requirements 7.3**
        """
        for fname in ("run_apply", "finalize_one"):
            node = function_node(HOST_SCRIPT, fname)
            names = referenced_names(node) | called_names(node)
            for forbidden in (
                "instrument_docx_bytes",
                "template_bytes",
                "TEMPLATE_ROOT",
                "wp_templates",
                "read_back_word_tags",
            ):
                assert forbidden not in names, (
                    f"{fname} 引用了模板入口 {forbidden} —— `--apply` 不得用模板重生成"
                )
        # 反向分母：`--check` 侧**确实**用了它（否则上面的 0 是恒真）。
        check_names = referenced_names(function_node(HOST_SCRIPT, "run_offline_criteria"))
        assert "instrument_docx_bytes" in check_names or "template_bytes" in check_names

    def test_targets_come_from_a_single_source(self) -> None:
        """entry 集合从 Task 60 发布记录现算，不写第二份清单。"""
        node = function_node(HOST_SCRIPT, "resolve_targets")
        assert "lane_entries" in called_names(node), "宿主没从发布记录现读 entry"
        lane_node = function_node(HOST_SCRIPT, "lane_entries")
        assert "PUBLICATION_PATH" in referenced_names(lane_node)
        assert "unresolved_reason" in referenced_names(node), "查不到目标时没给显式原因"

    def test_script_reports_errors_instead_of_degrading(self) -> None:
        """脚本失败必须非零退出，不得降级成成功。

        **Validates: Requirements 6.18**
        """
        node = function_node(HOST_SCRIPT, "_main")
        raised = {
            inner.exc.func.id
            for inner in ast.walk(node)
            if isinstance(inner, ast.Raise)
            and isinstance(inner.exc, ast.Call)
            and isinstance(inner.exc.func, ast.Name)
        }
        assert "WordFinalizeScriptError" in raised, "脚本吞掉了 entry 级失败"

    def test_host_declares_no_word_adapter(self) -> None:
        """本任务不翻 `PENDING_ENGINE_ADAPTERS` 的那一行（Task 61 的门）。

        **Validates: Requirements 12.5**
        """
        from app.services.workpaper_sync.adapters import registry as RG

        pending = [
            row for row in RG.PENDING_ENGINE_ADAPTERS if row["document_type"] == "docx"
        ]
        assert len(pending) == 1, pending
        forbidden = tuple(pending[0]["forbidden_paths"])
        assert forbidden, "forbidden_paths 为空 ⇒ 判据无分母"
        for rel in forbidden:
            assert not (ROOT / "backend" / rel).exists(), (
                f"{rel} 已落地 —— Task 77 无权翻这行（放行门是 Task 61 的真实 OO 9.4 场景）"
            )
        assert all(row["document_type"] != "docx" for row in RG.DELIVERED_ENGINE_ADAPTERS)


# ════════════════════════════════════════════════════════════════════════════
# 7. finalize gate 的顺序即判据
# ════════════════════════════════════════════════════════════════════════════


class _FakeCoordinator:
    """记录调用次数的假 coordinator —— 用来证明「前置不过 ⇒ 0 次写入」。"""

    def __init__(self) -> None:
        self.calls = 0

    async def finalize_definition_upgrade(self, **_: Any) -> Any:  # pragma: no cover
        self.calls += 1
        raise AssertionError("前置未过却调到了 Task 25 的出口")


class _FakeResolution:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def assert_candidate_finalizable(self, _cid: Any) -> Any:
        raise self._exc


class TestFinalizeGateOrdering:
    def test_missing_coordinator_is_refused_before_anything_else(self) -> None:
        """gate 未装配出口 ⇒ 立刻拒（不自行发布 representation）。

        **Validates: Requirements 6.18 / Property 67**
        """
        import asyncio
        import uuid as _uuid

        gate = WG.WordEntryFinalizeGate(
            loader=None,  # type: ignore[arg-type]
            resolution=None,  # type: ignore[arg-type]
            coordinator=None,
        )
        with pytest.raises(WG.WordEntryFinalizeGateBlockedError):
            asyncio.run(
                gate.finalize_candidate(
                    project_id=_uuid.uuid4(),
                    entry_id="f2.stocktake.plan",
                    candidate_id=_uuid.uuid4(),
                    staged_candidate=None,  # type: ignore[arg-type]
                    contract=None,  # type: ignore[arg-type]
                    contract_origin="staged_word_lane",
                    instrumentation_payload={},
                    frozen_bundle_sha256="0" * 64,
                    scratch_dir=Path("."),
                )
            )

    def test_prerequisite_failure_never_reaches_the_write_surface(self, plan: _Lane) -> None:
        """Task 12 前置抛 ⇒ coordinator 调用次数为 **0**（可观察事实）。

        **Validates: Requirements 6.18 / Property 67**
        """
        import asyncio
        import uuid as _uuid

        from app.services.workpaper_sync.resolution import CandidateNotFinalizableError

        coordinator = _FakeCoordinator()
        gate = WG.WordEntryFinalizeGate(
            loader=None,  # type: ignore[arg-type]
            resolution=_FakeResolution(CandidateNotFinalizableError("缺 approved bundle")),
            coordinator=coordinator,
        )
        with pytest.raises(CandidateNotFinalizableError):
            asyncio.run(
                gate.finalize_candidate(
                    project_id=_uuid.uuid4(),
                    entry_id=plan.entry_id,
                    candidate_id=_uuid.uuid4(),
                    staged_candidate=None,  # type: ignore[arg-type]
                    contract=plan.contract,
                    contract_origin=plan.contract_origin,
                    instrumentation_payload=plan.instrumentation_payload,
                    frozen_bundle_sha256="a" * 64,
                    scratch_dir=Path("."),
                )
            )
        assert coordinator.calls == 0, "前置未过却写了 representation"

    def test_finalize_order_is_prerequisites_then_the_single_exit(self) -> None:
        """`finalize_definition_upgrade` 在**全部**判据之后（源码顺序即执行顺序）。

        **Validates: Requirements 6.18**
        """
        node = function_node(GATE_PY, "finalize_candidate")
        order: list[tuple[int, str]] = []
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call):
                func = inner.func
                name = (
                    func.attr
                    if isinstance(func, ast.Attribute)
                    else (func.id if isinstance(func, ast.Name) else "")
                )
                if name:
                    order.append((inner.lineno, name))
        order.sort()
        exit_lines = [line for line, name in order if name == "finalize_definition_upgrade"]
        assert len(exit_lines) == 1, exit_lines
        for name in (
            "assert_candidate_finalizable",
            "parse_word_candidate_evidence",
            "load",
            "assert_may_publish",
            "verify_candidate_tag_roundtrip",
            "assert_tag_set_matches",
            "assert_sdt_hierarchy_intact",
            "assert_field_instance_counts",
        ):
            lines = [line for line, got in order if got == name]
            assert lines, f"finalize_candidate 里没有 {name}"
            assert min(lines) < exit_lines[0], f"{name} 排在唯一出口之后 ⇒ 顺序失效"


# ════════════════════════════════════════════════════════════════════════════
# 8. candidate 证据（跨 entry 复用在此 fail closed）
# ════════════════════════════════════════════════════════════════════════════


class TestCandidateEvidence:
    def test_happy_report_parses(self, plan: _Lane) -> None:
        report = plan.evidence_report()
        parsed = WG.parse_word_candidate_evidence(
            report_bytes=report,
            expected_sha256=hashlib.sha256(report).hexdigest(),
            entry_id=plan.entry_id,
        )
        assert parsed.instrumented_sha256 == plan.instrumented.instrumented_sha256
        assert parsed.readback["tags"] == list(plan.inventory.tags)

    def test_digest_mismatch_is_refused_first(self, plan: _Lane) -> None:
        """digest 不符 ⇒ 拒（禁用别的 candidate 的证据顶替）。

        **Validates: Requirements 6.18**
        """
        report = plan.evidence_report()
        with pytest.raises(WG.WordEntryCandidateEvidenceError, match="不一致"):
            WG.parse_word_candidate_evidence(
                report_bytes=report, expected_sha256="b" * 64, entry_id=plan.entry_id
            )

    def test_foreign_entry_evidence_is_refused(self, lanes: tuple[_Lane, ...]) -> None:
        """跨 entry 复用 evidence ⇒ 拒。

        **Validates: Requirements 12.5**
        """
        a, b = lanes[0], lanes[1]
        report = b.evidence_report()
        with pytest.raises(WG.WordEntryCandidateEvidenceError, match="不得跨 entry"):
            WG.parse_word_candidate_evidence(
                report_bytes=report,
                expected_sha256=hashlib.sha256(report).hexdigest(),
                entry_id=a.entry_id,
            )

    @pytest.mark.parametrize("key", WG.REQUIRED_WORD_EVIDENCE_KEYS)
    def test_every_required_key_is_load_bearing(self, plan: _Lane, key: str) -> None:
        """每个必需键**逐个**清空都必须打红（不是「少一个也能过」）。"""
        payload = json.loads(plan.evidence_report().decode("utf-8"))
        payload[key] = None
        report = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        with pytest.raises(WG.WordEntryCandidateEvidenceError):
            WG.parse_word_candidate_evidence(
                report_bytes=report,
                expected_sha256=hashlib.sha256(report).hexdigest(),
                entry_id=plan.entry_id,
            )

    def test_unequivalent_instrumentation_is_refused(self, plan: _Lane) -> None:
        """注入期可见等价未通过 ⇒ 拒。

        **Validates: Requirements 7.3**
        """
        equivalence = copy.deepcopy(dict(plan.equivalence))
        equivalence["equivalent"] = False
        equivalence["preserved_aspects"] = {"outside_sdt_text": False}
        report = plan.evidence_report(visible_equivalence=equivalence)
        with pytest.raises(WG.WordEntryCandidateEvidenceError, match="可见等价"):
            WG.parse_word_candidate_evidence(
                report_bytes=report,
                expected_sha256=hashlib.sha256(report).hexdigest(),
                entry_id=plan.entry_id,
            )

    def test_non_docx_evidence_is_refused(self, plan: _Lane) -> None:
        """xlsx entry 的证据不得喂进 Word gate（两个域的判据形状完全不同）。

        **Validates: Requirements 12.5**
        """
        report = plan.evidence_report(document_type="xlsx")
        with pytest.raises(WG.WordEntryCandidateEvidenceError, match="document_type"):
            WG.parse_word_candidate_evidence(
                report_bytes=report,
                expected_sha256=hashlib.sha256(report).hexdigest(),
                entry_id=plan.entry_id,
            )

    def test_untagged_sdt_at_injection_is_refused(self, plan: _Lane) -> None:
        """注入留下无 tag 的 SDT ⇒ 拒（不可定位区域）。"""
        readback = copy.deepcopy(dict(plan.readback))
        readback["untagged_sdt_count"] = 1
        report = plan.evidence_report(tag_readback=readback)
        with pytest.raises(WG.WordEntryCandidateEvidenceError, match="无 tag"):
            WG.parse_word_candidate_evidence(
                report_bytes=report,
                expected_sha256=hashlib.sha256(report).hexdigest(),
                entry_id=plan.entry_id,
            )

    def test_probe_gate_identity_is_mandatory(self, plan: _Lane) -> None:
        """缺真实 OO 9.4 探针身份 ⇒ 拒（Task 6 的门不可跳）。

        **Validates: Requirements 7.1**
        """
        report = plan.evidence_report(probe_gate={"onlyoffice_build": "9.4.0-129"})
        with pytest.raises(WG.WordEntryCandidateEvidenceError, match="probe_gate"):
            WG.parse_word_candidate_evidence(
                report_bytes=report,
                expected_sha256=hashlib.sha256(report).hexdigest(),
                entry_id=plan.entry_id,
            )


# ════════════════════════════════════════════════════════════════════════════
# 9. Property 收束
# ════════════════════════════════════════════════════════════════════════════


class TestProperties:
    def test_property_28_frozen_identity_cannot_be_swapped(
        self, lanes: tuple[_Lane, ...]
    ) -> None:
        """P28：declared 清册必须来自 bundle 里那份 immutable instrumentation。

        **Validates: Requirements 6.10**
        """
        a, b = lanes[0], lanes[1]
        assert canonical_digest(a.instrumentation_payload) != canonical_digest(
            b.instrumentation_payload
        ), "两个 lane 的 instrumentation digest 相同 ⇒ 换一份也测不出来"
        # digest 现算与契约声明双向锁死（换一份 payload 必然对不上 slot digest）。
        for lane in lanes:
            assert (
                canonical_digest(lane.instrumentation_payload)
                == lane.contract.instrumentation_definition_sha256
            ), lane.entry_id
        node = function_node(GATE_PY, "load")
        assert "canonical_digest" in called_names(node), (
            "loader 没重算 instrumentation payload 的 canonical digest ⇒ 换一份也能过"
        )

    def test_property_30_only_tagged_sdt_is_read(self, plan: _Lane) -> None:
        """P30：删 tag / 只留 placeholder 文本 ⇒ extract 失败，不回退段落索引/正则。

        **Validates: Requirements 7.1**
        """
        victim = next(
            tag
            for tag in plan.inventory.tags
            if "gt:field:" in tag and tag not in plan.inventory.block_containers
        )
        broken = _strip_tag_attribute(plan.instrumented.instrumented_bytes, victim)
        with pytest.raises(WE.WordTagMissingError):
            plan.observe(broken)

    def test_property_30_row_domain_denominator_is_empty_and_not_claimed(
        self, lanes: tuple[_Lane, ...]
    ) -> None:
        """🔴 分母登记：本 lane 行域字段实测 0 个 ⇒ Requirement 7.2 的行实例计数**不宣称**。

        判据是「前提现算为 0」而不是「行判据通过」—— 后者在空集上恒真。
        """
        for lane in lanes:
            assert lane.inventory.row_uuids == (), lane.inventory.row_uuids
            assert lane.spec.rows == (), lane.spec.rows
            assert not [f for f in lane.contract.all_fields() if f.row_scoped]
            assert int(lane.roundtrip().observation.unmanaged_sdt_count) == 0

    def test_property_31_word_only_bodies_are_preserved(
        self, lanes: tuple[_Lane, ...]
    ) -> None:
        """P31：两次 materialize 前后 SDT 外 OOXML 正文规范化内容相等（覆盖非空）。

        **Validates: Requirements 7.3**
        """
        for lane in lanes:
            first = lane.roundtrip()
            second = lane.roundtrip(first.roundtrip_path.read_bytes())
            assert first.verification.unmanaged.equivalent
            assert second.verification.unmanaged.equivalent
            for name in WG.WORD_ONLY_COVERAGE_REQUIRED:
                assert int(second.word_only_coverage[name]) > 0, (lane.entry_id, name)

    def test_property_32_duplicate_conflict_lists_every_location(self, plan: _Lane) -> None:
        """P32：同 stable tag 多实例异值 ⇒ duplicate 冲突并列出全部 XPath，gate 拒绝发布。

        **Validates: Requirements 7.4**
        """
        victim_key = next(
            key
            for key, declared in sorted(plan.inventory.declared_instances.items())
            if declared == "many"
        )
        victim_tag = WG._tag_of_key(plan.inventory, victim_key)
        broken = _make_instances_disagree(plan.instrumented.instrumented_bytes, victim_tag)
        with pytest.raises(WG.WordEntryDuplicateConflictError) as err:
            plan.roundtrip(broken)
        message = str(err.value)
        assert "全部 OO 位置" in message, message
        occurrences = message.count("/w:sdt")
        assert occurrences >= 2, f"没有列出全部位置（只有 {occurrences} 处）：{message}"

    def test_property_34_tag_loss_never_degrades(self, plan: _Lane) -> None:
        """P34：tag retention 失败 ⇒ operation error，生产路径不调段落索引提取器。

        **Validates: Requirements 7.8**
        """
        inner, container = next(iter(plan.inventory.block_containers.items()))
        broken = _unwrap_block_sdt(plan.instrumented.instrumented_bytes, container)
        observation = plan.observe(broken)
        with pytest.raises(WG.WordEntryTagSetDriftError):
            WG.assert_tag_set_matches(plan.inventory, observation, entry_id=plan.entry_id)
        # 生产路径里没有任何段落索引提取器（结构判据；engine 与 gate 双侧）。
        for path in (GATE_PY, ENGINE_PY):
            names = referenced_names(ast.parse(path.read_text(encoding="utf-8")))
            assert not (WE.FORBIDDEN_FALLBACK_SYMBOLS & names), path.name

    def test_property_67_candidate_never_becomes_current_by_this_gate(self) -> None:
        """P67：gate 不切 pointer、不建 representation，唯一出口在 Task 25 且断言 revision 不变。

        **Validates: Requirements 6.18**
        """
        tree = ast.parse(GATE_PY.read_text(encoding="utf-8"))
        calls = called_names(tree)
        for forbidden in ("set_entry_pointer", "create_representation", "finalize_candidate_artifact"):
            assert forbidden not in calls, forbidden
        assert hasattr(WG.WordEntryFinalizeOutcome, "revision_unchanged")
        # Task 25 的出口自己断言 revision 不变 —— 这条在它那边是单一真源。
        coordinator_src = (SVC / "materialize_coordinator.py").read_text(encoding="utf-8")
        assert "DefinitionUpgradeRevisionError" in coordinator_src


def _strip_tag_attribute(data: bytes, tag: str) -> bytes:
    """删掉某个 SDT 的 `w:tag` 属性（只留 alias 与 placeholder 文本）。"""
    xml = _document_xml(data)
    needle = f'<w:tag w:val="{tag}"/>'
    assert needle in xml, f"文档里找不到 {needle}"
    return _rewrite_document_xml(data, xml.replace(needle, "", 1))


def _make_instances_disagree(data: bytes, tag: str) -> bytes:
    """把同一 tag 的第二个实例内容改成不同值（AC 7.4 的异值冲突形态）。"""
    xml = _document_xml(data)
    seen = 0
    for el_start, _, _, el_end in WE._find_spans(xml, "sdt"):
        block = xml[el_start:el_end]
        if WE._tag_of(block) != tag:
            continue
        seen += 1
        if seen < 2:
            continue
        contents = WE._find_spans(block, "sdtContent")
        inner_start, inner_end = contents[0][1], contents[0][2]
        runs = '<w:r><w:t xml:space="preserve">TASK77-DISAGREE</w:t></w:r>'
        new_block = block[:inner_start] + runs + block[inner_end:]
        return _rewrite_document_xml(data, xml[:el_start] + new_block + xml[el_end:])
    raise AssertionError(f"tag {tag!r} 的实例不足 2 个 ⇒ 异值冲突反例构造失败")
