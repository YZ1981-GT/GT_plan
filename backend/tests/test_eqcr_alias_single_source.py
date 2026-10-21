"""需求 7.2：EQCR 别名集合只有角色映射一处来源（partner-manager-edit-permission 任务 2.8）。

扫描范围：后端生产代码，即 ``backend/app`` 下全部 ``.py``（递归）。``backend/tests`` 整个目录不在范围内，
包括不以 ``test_`` 开头的期望表 ``role_map_expected.py``。前端的 EQCR 判定按需求 10 处理，不在本条。

判据（纯 AST，``ast.parse``）：

- ① 以 EQCR 别名集合全部成员为元素（集合 / 列表 / 元组）或键（映射）的字面量容器，只有 ``ROLE_MAP`` 一处；
- ② 字面量「独立复核合伙人」作为委派角色取值，即集合 / 列表 / 元组的元素、映射的键、比较的操作数
  （``ast.Compare`` 两侧，以及 ``match`` 语句的值模式 ``case "独立复核合伙人":``，它与 ``==`` 同义），
  只出现在 ``ROLE_MAP``。

不计：映射的值（如委派通知的显示名映射 ``{"eqcr": "独立复核合伙人"}``）、函数实参（日志、异常、``HTTPException``
的文案）、f-string 片段、下标取值。docstring 是语句级的字符串表达式，注释不进 AST，两者都落不到上面几种位置。
需求 7.2 只数字面量：先把别名赋给变量、再把变量放进集合的写法不在本扫描的口径内。

位置写成「文件::类.函数.赋值目标」，不用行号（行号随改动漂移）。任务 19.4 ⑥ 的变异（在 EQCR 判定所在模块
写回一份别名字面量集合）应使两条判据都红在「别名集合来源不唯一」上。
"""
from __future__ import annotations

import ast
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tests.role_map_expected import EXPECTED_EQCR_ALIASES

_APP = Path(__file__).resolve().parents[1] / "app"

# EQCR 别名全集取需求 2.5 的期望表，不从生产代码的 ROLE_MAP 现推。理由：
# - 本扫描数的是「别名字面量有几处来源」，判据不该随 ROLE_MAP 的取值浮动。若现推，把 ROLE_MAP 中
#   「独立复核合伙人」改为 (partner, edit)（任务 19.4 ⑥ 的第二项变异，应只红在需求 7.4 的用例上）会让全集
#   缩成 {"eqcr"}，判据①随之把生产代码里每一个含 "eqcr" 的角色名单都算成违规，红在与该变异无关的地方。
# - 「ROLE_MAP 中取值为 (partner, review) 的键恰是这两个」已由需求 2.5 的两处前提测试钉住，这里不重复。
_EQCR_ALIASES: frozenset[str] = EXPECTED_EQCR_ALIASES
_CN_ALIAS = "独立复核合伙人"
_ROLE_MAP_LOCATION = "app/services/assignment_service.py::ROLE_MAP"
_NOT_UNIQUE = "别名集合来源不唯一"
_CONTAINER_KINDS: dict[type[ast.AST], str] = {
    ast.Set: "集合", ast.List: "列表", ast.Tuple: "元组", ast.Dict: "映射"}


@dataclass(frozen=True)
class Hit:
    location: str  # 「相对 backend 的路径::类.函数.赋值目标」
    kind: str  # 判据①：容器种类；判据②：集合元素 / 映射键 / 比较操作数

    def __str__(self) -> str:
        return f"{self.location}（{self.kind}）"


@dataclass
class AliasSourceScan:
    root: Path
    files: int = 0
    parse_errors: list[str] = field(default_factory=list)
    full_set_hits: list[Hit] = field(default_factory=list)  # 判据①
    cn_alias_hits: list[Hit] = field(default_factory=list)  # 判据②


def _str_members(nodes: list[ast.expr] | list[ast.expr | None]) -> set[str]:
    return {n.value for n in nodes if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _cn_alias_kind(const: ast.Constant, parent: ast.AST | None) -> str | None:
    """「独立复核合伙人」常量按直接父节点归类；None 表示不计（映射的值、实参、f-string 片段、下标等）。"""
    if isinstance(parent, (ast.Set, ast.List, ast.Tuple)):
        return "集合元素"
    if isinstance(parent, ast.Dict):
        return "映射键" if any(key is const for key in parent.keys) else None
    if isinstance(parent, (ast.Compare, ast.MatchValue)):
        return "比较操作数"
    return None


def _locator(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    """所在的类 / 函数（由外到内）加同一作用域内最近的赋值目标；两者都没有时为 <module>。"""
    scopes: list[str] = []
    target: str | None = None
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scopes.append(cur.name)
        elif not scopes and target is None and isinstance(cur, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = cur.targets if isinstance(cur, ast.Assign) else [cur.target]
            target = " = ".join(ast.unparse(t) for t in targets)
        cur = parents.get(cur)
    return ".".join([*reversed(scopes), *([target] if target else [])]) or "<module>"


def scan_eqcr_alias_sources(
    root: Path, aliases: frozenset[str] = _EQCR_ALIASES, cn_alias: str = _CN_ALIAS
) -> AliasSourceScan:
    """扫描 root 下全部 .py（递归）；位置相对 root 的上一级给出（root 为 backend/app 时形如 app/...）。"""
    if not aliases:
        raise ValueError("别名集合为空：判据①会把每个容器都算作命中")
    scan = AliasSourceScan(root)
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root.parent).as_posix()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)  # 无效转义等告警与本扫描无关
                tree = ast.parse(path.read_bytes(), filename=str(path))
        except (SyntaxError, ValueError) as exc:  # 如实登记，由「扫描器不空转」打红，不静默跳过
            scan.parse_errors.append(f"{rel}：{exc}")
            continue
        scan.files += 1
        full_sets: list[ast.Set | ast.List | ast.Tuple | ast.Dict] = []
        cn_consts: list[ast.Constant] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Set, ast.List, ast.Tuple, ast.Dict)):
                if aliases <= _str_members(node.keys if isinstance(node, ast.Dict) else node.elts):
                    full_sets.append(node)
            elif isinstance(node, ast.Constant) and node.value == cn_alias:
                cn_consts.append(node)
        if not full_sets and not cn_consts:
            continue  # 本文件两条判据都没有候选，不必建父节点表
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for container in full_sets:
            container_kind = _CONTAINER_KINDS[type(container)]
            scan.full_set_hits.append(Hit(f"{rel}::{_locator(container, parents)}", container_kind))
        for const in cn_consts:
            value_kind = _cn_alias_kind(const, parents.get(const))
            if value_kind is not None:
                scan.cn_alias_hits.append(Hit(f"{rel}::{_locator(const, parents)}", value_kind))
    return scan


@pytest.fixture(scope="module")
def app_scan() -> AliasSourceScan:
    return scan_eqcr_alias_sources(_APP)


def _not_unique(criterion: str, hits: list[Hit]) -> str:
    others = [h for h in hits if h.location != _ROLE_MAP_LOCATION]
    listing = "\n".join(f"  - {h}" for h in others) or "  （无）"
    return (
        f"{_NOT_UNIQUE}（{criterion}）：应只有 {_ROLE_MAP_LOCATION} 一处；现算 ROLE_MAP 处 "
        f"{len(hits) - len(others)} 次，其他位置 {len(others)} 处：\n{listing}\n"
        "EQCR 别名请经 assignment_service.EQCR_ROLE_ALIASES（由 ROLE_MAP 推导）取用，不另写字面量副本。"
    )


def test_scanner_is_not_idle(app_scan: AliasSourceScan) -> None:
    """扫描器不空转：读到了文件、没有读不出 AST 的文件，两条判据都在 ROLE_MAP 处恰命中 1 次。"""
    assert _CN_ALIAS in _EQCR_ALIASES, f"期望表的 EQCR 别名集合不含「{_CN_ALIAS}」：{sorted(_EQCR_ALIASES)}"
    assert app_scan.files > 0, f"扫描器空转：{app_scan.root} 下没有扫到 .py 文件"
    assert app_scan.parse_errors == [], "扫描器空转：以下文件读不出 AST：\n" + "\n".join(app_scan.parse_errors)
    full_at_role_map = [h for h in app_scan.full_set_hits if h.location == _ROLE_MAP_LOCATION]
    assert full_at_role_map == [Hit(_ROLE_MAP_LOCATION, "映射")], (
        f"扫描器空转：判据①应在 ROLE_MAP 处恰命中 1 次（映射），现算 {[str(h) for h in full_at_role_map]}")
    cn_at_role_map = [h for h in app_scan.cn_alias_hits if h.location == _ROLE_MAP_LOCATION]
    assert cn_at_role_map == [Hit(_ROLE_MAP_LOCATION, "映射键")], (
        f"扫描器空转：判据②应在 ROLE_MAP 处恰命中 1 次（映射键），现算 {[str(h) for h in cn_at_role_map]}")


def test_full_alias_set_literal_only_in_role_map(app_scan: AliasSourceScan) -> None:
    """判据①：以 EQCR 别名全集为元素或键的字面量集合 / 列表 / 元组 / 映射只有 ROLE_MAP 一处。"""
    criterion = f"判据①：以 EQCR 别名全集 {sorted(_EQCR_ALIASES)} 为元素或键的字面量集合 / 列表 / 元组 / 映射"
    assert [h.location for h in app_scan.full_set_hits] == [_ROLE_MAP_LOCATION], _not_unique(
        criterion, app_scan.full_set_hits)


def test_cn_alias_role_value_only_in_role_map(app_scan: AliasSourceScan) -> None:
    """判据②：「独立复核合伙人」作委派角色取值只在 ROLE_MAP；显示名映射的值与用户可见文案不计。"""
    criterion = f"判据②：「{_CN_ALIAS}」作集合元素、映射键或比较操作数"
    assert [h.location for h in app_scan.cn_alias_hits] == [_ROLE_MAP_LOCATION], _not_unique(
        criterion, app_scan.cn_alias_hits)
