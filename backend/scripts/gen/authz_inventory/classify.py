"""附注写端点清册的归类与目标门禁（spec partner-manager-edit-permission，需求 1.2 / 1.8 / 1.9，design §4.12 第 3~5 步）。

- ``classify(file, result)``：按 S → C → G → E → R → X → I 的先后，归入第一个定义被满足的类别，且只归这一类（需求 1.2）。
  识别结果有问题的端点不归类（问题由调用方逐项报错，需求 1.7）；一个定义都满足不了的返回「无法归类」与原因。
- ``current_gate(result)``：现门禁的产物视图（需求 1.8）：逐项列出非中性门禁（来源、条件执行、辅助函数链、级别、静态参数），
  汇总最高级别、操作矩阵权限点、合并锁、EQCR 排除、全局角色、仅登录与桩端点的错误。
- ``parse_declarations(data)``：校验目标门禁声明文件（design §5.4），返回按（方法，完整路径）索引的声明与中文问题清单。
- ``resolve_target(category, declaration)``：类别默认值与声明合并（需求 1.9）；I 类没有默认值，未声明时 ``kind`` 为 None。
- ``target_met(result, target)``：现门禁是否已等于目标门禁。保持现门禁恒为是，待 design 核对恒为否；附注编辑门禁要求除仅登录
  以外的非中性判定全部是附注编辑门禁三形态之一；design 定级门禁要求它们全部是声明的那个门禁、静态参数与声明逐项相等；
  两者都要求至少有一处、且都不是条件执行。声明里的「判定项目来源」不能静态核对；「是否放行本项目 EQCR」只核对与门禁
  自身是否排除 EQCR 一致（``parse_declarations`` 里校验）。

本模块只消费 ``gates`` 的识别结果，不读文件，不导入被扫描的树。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from . import gates
from .routes import WRITE_METHODS

CATEGORY_ORDER = ("S", "C", "G", "E", "R", "X", "I")
CATEGORY_NAMES = {
    "S": "桩端点", "C": "合并附注", "G": "交付中心门禁", "E": "edit 级（改走附注编辑门禁）",
    "R": "readonly 级预览类", "X": "只按全局角色判定", "I": "只校验登录或无鉴权依赖",
}
STUB_ERRORS = frozenset({"HTTP 410", "HTTP 501", "NotImplementedError"})  # 「已废弃」410；「未实现」501 / NotImplementedError
STUB_SIGNATURE_KINDS = frozenset({"db_session", "upload_file", "background_tasks"})
CONSOL_PREFIX = "consol_"
COVERAGE_CATEGORIES = frozenset({"E", "I"})  # 需求 1.9：覆盖集合 = 这两类中目标门禁为附注编辑门禁的端点

TARGET_KINDS = ("note_edit_gate", "design_gate", "keep_current", "pending_design_review")
TARGET_NAMES = {"note_edit_gate": "附注编辑门禁", "design_gate": "design 定级门禁", "keep_current": "保持现门禁",
                "pending_design_review": "待 design 核对"}
DEFAULT_TARGETS: dict[str, str | None] = {"S": "keep_current", "C": "keep_current", "G": "keep_current",
                                          "E": "note_edit_gate", "R": "keep_current", "X": "keep_current", "I": None}
DESIGN_GATE_CATEGORIES = frozenset({"project", "design"})  # design_gate 可声明的门禁类别（项目级 / design 定级）
PROJECT_SOURCES = ("path", "query", "body", "object_id")
EQCR_CHOICES = ("deny", "allow")
DECLARATIONS_SCHEMA = "note_write_target_declarations/v1"
_VIA_RANK = {"registration": 0, "router": 1, "route": 2, "signature": 3, "body": 4}
_PATH_PROJECT = re.compile(r"\{project_id(?::[^}]*)?\}")
_COMMON = frozenset({"method", "path", "target", "reason"})
_KEYS: dict[str, tuple[frozenset[str], frozenset[str]]] = {  # 目标 → (必填字段, 可选字段)
    "note_edit_gate": (_COMMON, frozenset({"project_from"})),
    "design_gate": (_COMMON | {"gate", "params", "project_from", "eqcr"}, frozenset()),
    "keep_current": (_COMMON, frozenset()),
    "pending_design_review": (_COMMON, frozenset()),
}


# ─── 归类（需求 1.2）───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Verdict:
    category: str | None  # None = 不归类（识别有问题或无法归类）
    reason: str


def _gate_uses(result: gates.EndpointGates) -> list[gates.GateUse]:
    return [u for u in result.uses if u.category != "neutral"]


def classify(file: str, result: gates.EndpointGates) -> Verdict:
    """``file`` 为端点所在文件（相对仓库根或文件名均可，只看文件名）。"""
    if result.issues:
        return Verdict(None, "识别有问题，不归类：" + "；".join(issue.message() for issue in result.issues))
    uses = _gate_uses(result)
    found = {u.category for u in uses}
    level = gates.max_level(uses)
    if result.stub and set(result.stub) <= STUB_ERRORS and not result.signature_kinds & STUB_SIGNATURE_KINDS:
        return Verdict("S", f"函数体只抛出 {'、'.join(result.stub)}，签名不声明数据库会话、上传文件或后台任务")
    if PurePosixPath(file).name.startswith(CONSOL_PREFIX):
        return Verdict("C", f"文件名以 {CONSOL_PREFIX} 开头")
    if "deliverable" in found:
        return Verdict("G", "已走交付中心门禁")
    if "note_edit" in found:
        return Verdict("E", "已走附注编辑门禁")
    if level in ("edit", "review"):
        return Verdict("E", f"项目级判定的最高级别为 {level}")
    if level == "readonly":
        return Verdict("R", "项目级判定的最高级别为 readonly")
    if "global_role" in found:
        return Verdict("X", "有全局角色判定，没有项目级判定")
    if found <= {"identity"}:
        return Verdict("I", "只校验登录" if found else "没有任何鉴权依赖")
    names = "、".join(sorted(gates.CATEGORIES[c] for c in found))
    return Verdict(None, f"无法按需求 1.2 归类：现门禁为 {names}，不满足 S / C / G / E / R / X / I 任一类的定义")


# ─── 现门禁视图（需求 1.8）─────────────────────────────────────────────────────


def _plain(value: Any) -> Any:
    """识别结果里的取值 → JSON 取值（元组 → 列表，集合 → 排序列表）。"""
    if isinstance(value, (frozenset, set)):
        return sorted(_plain(v) for v in value)
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    return value


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def current_gate(result: gates.EndpointGates) -> dict[str, Any]:
    uses = _gate_uses(result)
    forms = [{"name": u.name, "via": u.via, "conditional": u.conditional, "helper": list(u.chain) or None,
              "level": u.level, "params": {key: _plain(value) for key, value in u.params}} for u in uses]
    forms.sort(key=lambda f: (_VIA_RANK.get(f["via"], len(_VIA_RANK)), f["name"], _canon(f)))
    overlays = [(key, value) for u in uses for key, value in gates.REGISTRY[u.name].overlays]
    operations = {value for key, value in overlays if key == "operation"}
    operations |= {dict(u.params).get("operation") for u in uses if u.category == "operation"} - {None}
    roles = {role for u in uses if u.category == "global_role" for role in dict(u.params).get("roles") or ()}
    return {
        "forms": forms,
        "max_level": gates.max_level(uses),
        "operations": sorted(operations),
        "consol_lock": any(u.category == "consol_lock" or dict(u.params).get("consol_lock") is True for u in uses),
        "eqcr_exclusion": ("eqcr_exclusion", True) in overlays,
        "global_roles": sorted(roles),
        "identity_only": bool(uses) and all(u.category == "identity" for u in uses),
        "stub": list(result.stub) if result.stub else None,
    }


# ─── 目标门禁声明（design §5.4）与合并（需求 1.9）──────────────────────────────


@dataclass(frozen=True)
class Target:
    """一个写端点的目标门禁。``kind`` 为 None = I 类且未声明（I 类没有默认值）。"""

    kind: str | None
    declared: bool
    reason: str | None = None
    gate: str | None = None
    params: tuple[tuple[str, Any], ...] | None = None  # 按键排序；字符串集合为排序元组
    project_from: tuple[str, ...] | None = None
    eqcr: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "declared": self.declared, "reason": self.reason, "gate": self.gate,
                "params": None if self.params is None else {key: _plain(value) for key, value in self.params},
                "project_from": None if self.project_from is None else list(self.project_from), "eqcr": self.eqcr}


@dataclass(frozen=True)
class Declaration:
    method: str
    path: str
    target: Target

    @property
    def key(self) -> tuple[str, str]:
        return self.method, self.path


def param_rules(spec: gates.GateSpec) -> tuple[gates.Arg, ...]:
    """门禁的静态参数（级别由实参给出的，其 ``level`` 规则在前）。声明的 ``params`` 键 = 这些规则的 ``key``。"""
    return ((spec.level,) if isinstance(spec.level, gates.Arg) else ()) + spec.args


def comparable_params(use: gates.GateUse) -> tuple[tuple[str, Any], ...]:
    """识别出的一处门禁的静态参数（含实参给出的级别），与声明的 ``params`` 同一形态。"""
    spec = gates.REGISTRY[use.name]
    items = dict(use.params)
    if isinstance(spec.level, gates.Arg):
        items[spec.level.key] = use.level
    return tuple(sorted(items.items()))


def _declared_value(rule: gates.Arg, value: Any, is_level: bool) -> tuple[bool, Any]:
    if is_level:
        return value in gates.LEVELS, value
    if rule.form == "bool":
        return isinstance(value, bool), value
    if rule.form == "names":
        ok = isinstance(value, list) and all(isinstance(v, str) for v in value) and len(set(value)) == len(value)
        return ok, (tuple(sorted(value)) if ok else None)
    return isinstance(value, (str, int, bool)) and value != "", value


def _design_gate(name: Any, params: Any, errors: list[str]) -> tuple[str | None, tuple[tuple[str, Any], ...] | None]:
    spec = gates.REGISTRY.get(name) if isinstance(name, str) else None
    if spec is None or spec.category not in DESIGN_GATE_CATEGORIES:
        allowed = sorted(n for n, s in gates.REGISTRY.items() if s.category in DESIGN_GATE_CATEGORIES)
        errors.append(f"gate {name!r} 不是登记表里的项目级或 design 定级门禁（可选：{'、'.join(allowed)}）")
        return None, None
    rules = {rule.key: rule for rule in param_rules(spec)}
    if not isinstance(params, dict) or set(params) != set(rules):
        got = sorted(params) if isinstance(params, dict) else params
        errors.append(f"params 须为 JSON 对象且键恰为 {sorted(rules)}（门禁 {spec.name} 的静态参数），实际 {got!r}")
        return spec.name, None
    normalized = []
    for key in sorted(rules):
        ok, value = _declared_value(rules[key], params[key], rules[key] is spec.level)
        if not ok:
            errors.append(f"params.{key} 取值 {params[key]!r} 不符合门禁 {spec.name} 的参数形态")
        normalized.append((key, value))
    return spec.name, tuple(normalized)


def _project_from(value: Any, path: Any, errors: list[str]) -> tuple[str, ...] | None:
    if not (isinstance(value, list) and value and all(isinstance(v, str) for v in value)
            and len(set(value)) == len(value) and set(value) <= set(PROJECT_SOURCES)):
        errors.append(f"project_from 须为不重复的非空列表，取值限 {' / '.join(PROJECT_SOURCES)}，实际 {value!r}")
        return None
    if "path" in value and isinstance(path, str) and not _PATH_PROJECT.search(path):
        errors.append("project_from 含 path，但完整路径里没有 {project_id} 段")
        return None
    return tuple(value)


def _parse_one(item: Any, errors: list[str]) -> Declaration | None:
    if not isinstance(item, dict):
        errors.append("不是 JSON 对象")
        return None
    kind = item.get("target")
    if kind not in _KEYS:
        errors.append(f"target 取值 {kind!r} 不在 {' / '.join(TARGET_KINDS)} 之内")
        return None
    required, optional = _KEYS[kind]
    missing, extra = sorted(required - item.keys()), sorted(item.keys() - required - optional)
    if missing:
        errors.append(f"{TARGET_NAMES[kind]}的声明缺少字段 {'、'.join(missing)}")
    if extra:
        errors.append(f"{TARGET_NAMES[kind]}的声明不允许字段 {'、'.join(extra)}")
    method, path, reason = item.get("method"), item.get("path"), item.get("reason")
    if not (isinstance(method, str) and method in WRITE_METHODS):
        errors.append(f"method 须为 {' / '.join(sorted(WRITE_METHODS))} 之一（大写），实际 {method!r}")
    if not (isinstance(path, str) and path.startswith("/")):
        errors.append(f"path 须为以 / 开头的完整路径，实际 {path!r}")
    if not (isinstance(reason, str) and reason.strip()):
        errors.append("reason 不能为空（每条声明必带理由：需求编号、Q 编号或「范围外」条目）")
    gate = params = project_from = eqcr = None
    if "project_from" in item and "project_from" in required | optional:
        project_from = _project_from(item["project_from"], path, errors)
    if kind == "design_gate":
        gate, params = _design_gate(item.get("gate"), item.get("params"), errors)
        eqcr = item.get("eqcr")
        if eqcr not in EQCR_CHOICES:
            errors.append(f"eqcr 须为 deny（拒绝本项目 EQCR）或 allow（放行），实际 {eqcr!r}")
        elif gate is not None and (eqcr == "deny") != (("eqcr_exclusion", True) in gates.REGISTRY[gate].overlays):
            errors.append(f"eqcr 为 {eqcr}，与门禁 {gate} 自身{'排除' if eqcr == 'allow' else '不排除'} EQCR 不一致")
    if errors:
        return None
    return Declaration(method, path, Target(kind, True, reason, gate, params, project_from, eqcr))


def parse_declarations(data: Any) -> tuple[dict[tuple[str, str], Declaration], list[str]]:
    """校验声明文件（已按 JSON 解析）。返回（声明索引，中文问题清单）；问题非空时调用方按需求 1.7 失败。"""
    if not (isinstance(data, dict) and set(data) == {"schema", "declarations"}
            and data["schema"] == DECLARATIONS_SCHEMA and isinstance(data["declarations"], list)):
        return {}, [f"目标门禁声明文件格式不符：须为恰含 schema（{DECLARATIONS_SCHEMA}）与 declarations（列表）的 JSON 对象"]
    found: dict[tuple[str, str], Declaration] = {}
    problems: list[str] = []
    for index, item in enumerate(data["declarations"], start=1):
        label = f"目标门禁声明第 {index} 条"
        if isinstance(item, dict) and isinstance(item.get("method"), str) and isinstance(item.get("path"), str):
            label += f"（{item['method']} {item['path']}）"
        errors: list[str] = []
        declaration = _parse_one(item, errors)
        problems.extend(f"{label}：{error}" for error in errors)
        if declaration is None:
            continue
        if declaration.key in found:
            problems.append(f"{label}：与前面的声明重复（同一方法与完整路径只能声明一次）")
            continue
        found[declaration.key] = declaration
    return found, problems


def resolve_target(category: str, declaration: Declaration | None) -> Target:
    """有声明取声明，否则取类别默认值（I 类无默认值 ⇒ ``kind`` 为 None，调用方报错）。"""
    if declaration is not None:
        return declaration.target
    return Target(DEFAULT_TARGETS[category], False)


def target_met(result: gates.EndpointGates, target: Target) -> bool:
    """现门禁是否已等于目标门禁（判据见模块说明）。"""
    if target.kind == "keep_current":
        return True
    uses = [u for u in _gate_uses(result) if u.category != "identity"]
    if not uses or any(u.conditional for u in uses):
        return False
    if target.kind == "note_edit_gate":
        return all(u.category == "note_edit" for u in uses)
    if target.kind == "design_gate":
        return all(u.name == target.gate and comparable_params(u) == target.params for u in uses)
    return False  # 待 design 核对 / 未声明


def in_coverage(category: str, target: Target) -> bool:
    """需求 1.9：E、I 两类中目标门禁为附注编辑门禁的端点 = 附注编辑门禁覆盖集合。"""
    return category in COVERAGE_CATEGORIES and target.kind == "note_edit_gate"
