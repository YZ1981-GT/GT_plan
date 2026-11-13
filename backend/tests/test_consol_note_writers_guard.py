from __future__ import annotations

import ast
import copy
import hashlib
import re
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Iterator

import pytest

from app.services.consol_note_writers import (
    CONSOL_NOTE_WRITER_EXCLUSIONS,
    CONSOL_NOTE_WRITERS,
    PERMISSION_LEVELS,
    ROLES,
)

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
APP = BACKEND / "app"

_CONTENT_SHAPES = frozenset(
    {
        "orm_constructor",
        "orm_data_assignment",
        "orm_update_data",
        "source_projection",
        "raw_sql_data",
    }
)
_PERSISTENCE_SHAPES = _CONTENT_SHAPES | {"stale_assignment", "orm_update_stale"}
_RAW_DATA_UPDATE = re.compile(
    r"\bUPDATE\s+consol_note_data\b.*\bSET\s+data\s*=",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class _Definition:
    entrypoint: str
    path: Path
    node: ast.AST
    kind: str


@dataclass
class _Shapes:
    kinds: set[str]
    names: set[str]
    calls: set[str]


class _DefinitionCollector(ast.NodeVisitor):
    """收集真实源码定义，限定名来自 AST 的类/函数嵌套关系。"""

    def __init__(self, module: str, path: Path) -> None:
        self.module = module
        self.path = path
        self.stack: list[str] = []
        self.definitions: list[_Definition] = []

    def _record(self, node: ast.AST, kind: str) -> None:
        qualname = ".".join((*self.stack, getattr(node, "name")))
        self.definitions.append(_Definition(f"{self.module}:{qualname}", self.path, node, kind))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._record(node, "class")
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record(node, "function")
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record(node, "function")
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_and_return(self, tree: ast.AST) -> list[_Definition]:
        self.visit(tree)
        return self.definitions


def _module(path: Path) -> str:
    return ".".join(path.relative_to(BACKEND).with_suffix("").parts)


def _load_definitions(
    *,
    extra_sources: Iterable[tuple[str, Path, str]] = (),
) -> dict[str, _Definition]:
    """建立生产 AST 索引，并允许变异测试追加临时源码。"""
    sources = [
        (_module(path), path, path.read_text(encoding="utf-8-sig", errors="replace"))
        for path in sorted(APP.rglob("*.py"))
    ]
    sources.extend(extra_sources)
    definitions: dict[str, _Definition] = {}
    for module, path, source in sources:
        tree = ast.parse(source, filename=str(path))
        for definition in _DefinitionCollector(module, path).visit_and_return(tree):
            if definition.entrypoint in definitions:
                previous = definitions[definition.entrypoint]
                # 同一模块的条件分支可能重复声明枚举/模型辅助类；这些非写入
                # 重定义不影响入口解析。若重复定义包含写入形态，必须显式暴露，
                # 不能被索引策略吞掉。
                duplicate_shapes = _analyze_definition(definition).kinds | _analyze_definition(previous).kinds
                assert not duplicate_shapes & _PERSISTENCE_SHAPES, (
                    f"同一生产限定名存在重复且包含写入形态：{definition.entrypoint}"
                )
                continue
            definitions[definition.entrypoint] = definition
    return definitions


@lru_cache(maxsize=1)
def _production_definitions() -> dict[str, _Definition]:
    """当前测试进程内复用一次源码索引；变异探针应调用未缓存的 loader。"""
    return _load_definitions()


def _production_source_hashes() -> dict[str, str]:
    """获取生产源码树的字节级哈希快照，供内置变异的恢复围栏使用。"""
    return {
        str(path.relative_to(APP)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(APP.rglob("*.py"))
    }


@contextmanager
def _temporary_definition_mutation(
    definitions: dict[str, _Definition],
) -> Iterator[dict[str, _Definition]]:
    """只允许在临时 AST 索引中变异，并在 finally 中恢复索引与源码快照。"""
    original = dict(definitions)
    source_hashes = _production_source_hashes()
    try:
        yield definitions
    finally:
        definitions.clear()
        definitions.update(original)
        if set(definitions) != set(original) or any(
            definitions[key] is not value for key, value in original.items()
        ):
            raise AssertionError("内置变异 AST 索引未恢复")
        restored_hashes = _production_source_hashes()
        if restored_hashes != source_hashes:
            raise AssertionError("内置变异未恢复生产源码：文件内容或文件集合发生变化")


def _is_docstring_expr(node: ast.AST) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def _walk_definition(root: ast.AST, *, include_nested: bool = False) -> Iterable[ast.AST]:
    """遍历定义并跳过字符串表达式，避免 docstring 成为 SQL/名称证据。

    默认不把嵌套函数归给外层入口；保护引用检查显式要求 include_nested=True。
    """

    def walk(node: ast.AST, is_root: bool = False) -> Iterable[ast.AST]:
        if not is_root and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not include_nested:
            return
        if _is_docstring_expr(node):
            return
        yield node
        for child in ast.iter_child_nodes(node):
            yield from walk(child)

    yield from walk(root, True)


def _call_tail(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


class _RemoveCallByTail(ast.NodeTransformer):
    """把一个保护函数调用替换为常量，模拟生产入口漏接保护依据。"""

    def __init__(self, target: str) -> None:
        self.target = target
        self.removed = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        if _call_tail(node.func) == self.target:
            self.removed += 1
            return ast.copy_location(ast.Constant(value=None), node)
        return self.generic_visit(node)


def _is_model_expr(node: ast.AST) -> bool:
    return (isinstance(node, ast.Name) and node.id == "ConsolNoteData") or (
        isinstance(node, ast.Attribute) and node.attr == "ConsolNoteData"
    )


def _is_consol_note_update(node: ast.AST) -> bool:
    """判断 ``sa.update(ConsolNoteData).where(...).values(...)`` 的调用链。"""

    if isinstance(node, ast.Call):
        if _call_tail(node.func) == "update" and any(_is_model_expr(arg) for arg in node.args):
            return True
        return _is_consol_note_update(node.func.value) if isinstance(node.func, ast.Attribute) else False
    if isinstance(node, ast.Attribute):
        return _is_consol_note_update(node.value)
    return False


def _raw_sql_data_update(node: ast.Call) -> bool:
    if _call_tail(node.func) not in {"text", "sql"} or not node.args:
        return False
    sql = node.args[0]
    return isinstance(sql, ast.Constant) and isinstance(sql.value, str) and bool(_RAW_DATA_UPDATE.search(sql.value))


def _attribute_targets(node: ast.AST) -> Iterable[str]:
    for target in ast.walk(node):
        if isinstance(target, ast.Attribute):
            yield target.attr


@lru_cache(maxsize=None)
def _analyze_definition(definition: _Definition, *, include_nested: bool = False) -> _Shapes:
    kinds: set[str] = set()
    names: set[str] = set()
    calls: set[str] = set()
    nodes = list(_walk_definition(definition.node, include_nested=include_nested))

    for node in nodes:
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)

        if isinstance(node, ast.Assign):
            target_names = set(name for target in node.targets for name in _attribute_targets(target))
            if "data" in target_names:
                kinds.add("orm_data_assignment")
            if "is_stale" in target_names:
                kinds.add("stale_assignment")
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            target_names = set(_attribute_targets(node.target))
            if "data" in target_names:
                kinds.add("orm_data_assignment")
            if "is_stale" in target_names:
                kinds.add("stale_assignment")

        if not isinstance(node, ast.Call):
            continue
        tail = _call_tail(node.func)
        if tail:
            calls.add(tail)
        if tail == "ConsolNoteData":
            kinds.add("orm_constructor")
        if tail == "update_source_projection":
            kinds.add("source_projection")
        if tail == "values" and isinstance(node.func, ast.Attribute):
            keywords = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
            if "data" in keywords and _is_consol_note_update(node.func.value):
                kinds.add("orm_update_data")
            if "is_stale" in keywords and _is_consol_note_update(node.func.value):
                kinds.add("orm_update_stale")
        if _raw_sql_data_update(node):
            kinds.add("raw_sql_data")

    return _Shapes(kinds, names, calls)


def _resolve(entrypoint: str, definitions: dict[str, _Definition]) -> _Definition:
    try:
        return definitions[entrypoint]
    except KeyError as exc:
        raise AssertionError(f"登记入口无法在当前生产源码解析：{entrypoint}") from exc


def _writer_entrypoints() -> set[str]:
    return {spec.entrypoint for spec in CONSOL_NOTE_WRITERS}


def _definition_by_tail(definitions: dict[str, _Definition]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for entrypoint in definitions:
        tail = entrypoint.rsplit(":", 1)[-1].rsplit(".", 1)[-1]
        result.setdefault(tail, []).append(entrypoint)
    return result


def _reaches_registered_writer(
    entrypoint: str,
    definitions: dict[str, _Definition],
    by_tail: dict[str, list[str]],
    writers: set[str],
    cache: dict[str, bool],
    visiting: set[str] | None = None,
) -> bool:
    if entrypoint in writers:
        return True
    if entrypoint in cache:
        return cache[entrypoint]
    visiting = visiting or set()
    if entrypoint in visiting:
        return False
    visiting.add(entrypoint)
    shapes = _analyze_definition(definitions[entrypoint])
    result = any(
        target != entrypoint
        and _reaches_registered_writer(target, definitions, by_tail, writers, cache, visiting)
        for call in shapes.calls
        for target in by_tail.get(call, ())
    )
    visiting.remove(entrypoint)
    cache[entrypoint] = result
    return result


def _direct_persistence(definition: _Definition, shapes: _Shapes) -> bool:
    """只把能证明目标是合并附注的形态计入写入观测。

    ``record.data = ...`` 在平台上也用于报表、工作表和向导 JSON；单看属性名
    会把其它模型的写入误报成合并附注 writer。CND 构造、CND update、原生
    consol_note_data SQL、来源投影，或带保护函数的附注写入函数才满足身份证据。
    """

    if shapes.kinds & {"orm_constructor", "orm_update_data", "source_projection", "raw_sql_data"}:
        return True
    if "orm_data_assignment" in shapes.kinds:
        return "ConsolNoteData" in shapes.names or bool(
            {"protected_cells", "section_locked"} & shapes.names
        )
    if shapes.kinds & {"stale_assignment", "orm_update_stale"}:
        return "ConsolNoteData" in shapes.names
    return False


def _observed_entries(definitions: dict[str, _Definition]) -> dict[str, _Shapes]:
    writer_tails = {
        entrypoint.rsplit(":", 1)[-1].rsplit(".", 1)[-1]
        for entrypoint in _writer_entrypoints()
    }
    observed: dict[str, _Shapes] = {}
    for entrypoint, definition in definitions.items():
        if definition.kind == "class" and entrypoint.endswith(":ConsolNoteData"):
            observed[entrypoint] = _Shapes({"model_definition"}, {"ConsolNoteData"}, set())
            continue
        shapes = _analyze_definition(definition)
        directly_persistent = _direct_persistence(definition, shapes)
        model_reference = "ConsolNoteData" in shapes.names
        direct_writer_call = bool(shapes.calls & writer_tails)
        registered_exclusion = entrypoint in CONSOL_NOTE_WRITER_EXCLUSIONS
        if directly_persistent or model_reference or direct_writer_call or registered_exclusion:
            observed[entrypoint] = shapes
    return observed


def _exclusion_evidence(
    entrypoint: str,
    definition: _Definition,
    shapes: _Shapes,
    definitions: dict[str, _Definition],
) -> set[str]:
    evidence: set[str] = set()
    if definition.kind == "class" and entrypoint.endswith(":ConsolNoteData"):
        evidence.add("model_definition")
    if "ConsolNoteData" in shapes.names:
        evidence.add("model_reference")
    if shapes.kinds & {"raw_sql_data", "orm_update_data", "orm_update_stale", "stale_assignment"}:
        evidence.add("write_shape")
    by_tail = _definition_by_tail(definitions)
    if _reaches_registered_writer(
        entrypoint,
        definitions,
        by_tail,
        _writer_entrypoints(),
        {},
    ):
        evidence.add("writer_call_chain")
    if shapes.calls & {"source_digest", "canonical_json", "note_cell_values", "formula_snapshot"}:
        evidence.add("read_or_projection_helper")
    return evidence


def test_registry_entrypoints_roles_and_protection_basis_match_production_ast():
    definitions = _production_definitions()
    assert CONSOL_NOTE_WRITERS, "登记表不能为空"
    writer_ids = [spec.writer_id for spec in CONSOL_NOTE_WRITERS]
    entrypoints = [spec.entrypoint for spec in CONSOL_NOTE_WRITERS]
    assert len(writer_ids) == len(set(writer_ids)), "writer_id 必须唯一"
    assert len(entrypoints) == len(set(entrypoints)), "writer entrypoint 必须唯一"

    for spec in CONSOL_NOTE_WRITERS:
        assert spec.role in ROLES
        assert spec.permission
        assert set(spec.permission) <= PERMISSION_LEVELS
        definition = _resolve(spec.entrypoint, definitions)
        shapes = _analyze_definition(definition)
        assert shapes.kinds & _PERSISTENCE_SHAPES, f"登记入口没有可观测写入形态：{spec.entrypoint}"

        if spec.role == "automatic":
            assert spec.protection_basis, f"automatic writer 必须登记 protection_basis：{spec.entrypoint}"
            refs = _analyze_definition(definition, include_nested=True).names
            missing = sorted(set(spec.protection_basis) - refs)
            assert missing == [], f"automatic writer 未引用登记的保护函数 {missing}：{spec.entrypoint}"
            assert shapes.kinds & _CONTENT_SHAPES
        elif spec.role == "manual":
            assert shapes.kinds & _CONTENT_SHAPES
            assert not spec.protection_basis
        elif spec.role == "structural":
            assert "orm_constructor" in shapes.kinds
            assert not shapes.kinds & (_CONTENT_SHAPES - {"orm_constructor"})
            assert not shapes.kinds & {"stale_assignment", "orm_update_stale"}
            assert not spec.protection_basis
        elif spec.role == "stale":
            assert shapes.kinds & {"stale_assignment", "orm_update_stale"}
            assert not shapes.kinds & _CONTENT_SHAPES
            assert not spec.protection_basis


def _assert_persistence_registry_is_complete(definitions: dict[str, _Definition]) -> None:
    """执行双向完整性守卫；变异测试只替换输入 AST 索引，不复制这段判定。"""
    observed = _observed_entries(definitions)
    observed_persistence = {
        entrypoint
        for entrypoint, shapes in observed.items()
        if _direct_persistence(definitions[entrypoint], shapes)
    }
    registered = _writer_entrypoints()
    assert observed_persistence, "生产写入观测集合不能为空"
    assert observed_persistence == registered, (
        "生产源码写入入口与登记表不一致："
        f"未登记={sorted(observed_persistence - registered)}，"
        f"登记但未观测={sorted(registered - observed_persistence)}"
    )

    observed_kinds = set().union(*(observed[entry].kinds for entry in observed_persistence))
    assert {"orm_constructor", "orm_data_assignment", "raw_sql_data", "stale_assignment"} <= observed_kinds


def _assert_automatic_writer_protection_references(definitions: dict[str, _Definition]) -> None:
    """执行 automatic writer 的保护依据守卫。"""
    automatic = [spec for spec in CONSOL_NOTE_WRITERS if spec.role == "automatic"]
    assert automatic
    for spec in automatic:
        refs = _analyze_definition(_resolve(spec.entrypoint, definitions), include_nested=True).names
        missing = sorted(set(spec.protection_basis) - refs)
        assert missing == [], f"automatic writer 未引用登记的保护函数 {missing}：{spec.entrypoint}"


def test_all_production_persistence_shapes_are_registered_bidirectionally():
    _assert_persistence_registry_is_complete(_production_definitions())


def test_all_registered_exclusions_are_real_non_writers_with_verifiable_evidence():
    definitions = _production_definitions()
    observed = _observed_entries(definitions)
    assert CONSOL_NOTE_WRITER_EXCLUSIONS, "排除表不能为空"

    for entrypoint, reason in CONSOL_NOTE_WRITER_EXCLUSIONS.items():
        definition = _resolve(entrypoint, definitions)
        shapes = observed.get(entrypoint) or _analyze_definition(definition)
        assert len(reason.strip()) >= 12, f"排除理由过短：{entrypoint}"
        assert entrypoint in observed or entrypoint.endswith(":ConsolNoteData"), (
            f"排除入口未被生产源码观测：{entrypoint}"
        )
        assert not _direct_persistence(definition, shapes), f"排除项实际包含写入形态：{entrypoint}"
        evidence = _exclusion_evidence(entrypoint, definition, shapes, definitions)
        assert evidence - {"write_shape"}, f"排除理由没有可验证的源码证据：{entrypoint}"


def test_automatic_writer_protection_references_include_nested_functions():
    _assert_automatic_writer_protection_references(_production_definitions())


def test_mutation_unregistered_data_writer_is_rejected(tmp_path: Path):
    """新增真实 CND data 写入入口时，双向守卫必须报告未登记入口。"""
    entrypoint = "app.services._mutation_unregistered_writer:write_note_data"
    source = """
from app.models.consol_note_data_models import ConsolNoteData


def write_note_data(db, project_id):
    db.add(ConsolNoteData(project_id=project_id, data={"rows": []}))
"""
    definitions = dict(_production_definitions())
    with _temporary_definition_mutation(definitions):
        definitions.update(
            _load_definitions(
                extra_sources=((entrypoint.rsplit(":", 1)[0], tmp_path / "mutation_writer.py", source),)
            )
        )
        with pytest.raises(
            AssertionError,
            match=r"未登记=.*app\.services\._mutation_unregistered_writer:write_note_data",
        ):
            _assert_persistence_registry_is_complete(definitions)


def test_mutation_automatic_writer_without_protection_is_rejected():
    """移除真实 automatic writer 的保护调用时，保护依据守卫必须打红。"""
    spec = next(item for item in CONSOL_NOTE_WRITERS if item.writer_id == "consol-note-detail-mapping")
    original = _resolve(spec.entrypoint, _production_definitions())
    mutated_node = copy.deepcopy(original.node)
    remover = _RemoveCallByTail("protected_cells")
    mutated_node = remover.visit(mutated_node)
    ast.fix_missing_locations(mutated_node)
    assert remover.removed, "变异靶点未命中 protected_cells 调用"

    definitions = dict(_production_definitions())
    with _temporary_definition_mutation(definitions):
        definitions[spec.entrypoint] = _Definition(
            spec.entrypoint,
            original.path,
            mutated_node,
            original.kind,
        )
        with pytest.raises(
            AssertionError,
            match=r"未引用登记的保护函数.*protected_cells",
        ):
            _assert_automatic_writer_protection_references(definitions)


def test_ast_observer_ignores_comments_and_docstrings_and_detects_orm_update_shape():
    source = '''
import sqlalchemy as sa

def fake(db, record):
    """UPDATE consol_note_data SET data = 'not a write'."""
    # UPDATE consol_note_data SET data = 'not a write'
    return sa.update(ConsolNoteData).where(record.id == 1).values(data={})
'''
    tree = ast.parse(source)
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
    definition = _Definition("synthetic:fake", Path("synthetic.py"), function, "function")
    shapes = _analyze_definition(definition)
    assert "orm_update_data" in shapes.kinds
    assert "raw_sql_data" not in shapes.kinds


def test_ast_observer_does_not_treat_docstring_as_stale_or_constructor_write():
    source = '''
def fake(record):
    """ConsolNoteData(data={}); record.is_stale = True"""
    # ConsolNoteData(data={}); record.is_stale = True
    return record
'''
    tree = ast.parse(source)
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
    definition = _Definition("synthetic:fake", Path("synthetic.py"), function, "function")
    shapes = _analyze_definition(definition)
    assert not shapes.kinds & _PERSISTENCE_SHAPES


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def f(record):\n    record.data = {}\n", "orm_data_assignment"),
        ("def f():\n    return ConsolNoteData(data={})\n", "orm_constructor"),
        ("def f(record):\n    record.is_stale = True\n", "stale_assignment"),
        (
            'def f(db):\n    return db.execute(text("UPDATE consol_note_data SET data = :data"))\n',
            "raw_sql_data",
        ),
    ],
)
def test_shape_scanner_has_positive_probes_for_each_write_family(source: str, expected: str):
    tree = ast.parse(source)
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
    definition = _Definition("synthetic:fake", Path("synthetic.py"), function, "function")
    assert expected in _analyze_definition(definition).kinds
