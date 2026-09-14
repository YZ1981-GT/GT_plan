"""只读 component capability registry。

manifest 由 ``generate_component_capability_manifest.py`` 生成；本模块只负责严格
校验和不可变投影，不重新推导能力，也不在运行时修复坏数据。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "component_capabilities.json"
)
HOST_POLICIES = frozenset(
    {"skip", "redirect", "univer", "onlyoffice", "confirmation", "html", "unresolved"}
)
STATUSES = frozenset({"active", "deprecated", "experimental", "blocked"})
_COMPONENT_FIELDS = frozenset(
    {
        "owner",
        "has_backend_renderer",
        "has_frontend_component",
        "override_allowed",
        "host_policy",
        "status",
        "sources",
    }
)
_ROOT_FIELDS = frozenset({"schema_version", "components", "exemptions"})
_COMPONENT_TYPE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class ComponentCapabilityManifestError(ValueError):
    """manifest 结构或语义不可信。"""


@dataclass(frozen=True, slots=True)
class ComponentCapability:
    component_type: str
    owner: str
    has_backend_renderer: bool
    has_frontend_component: bool
    override_allowed: bool
    host_policy: str
    status: str
    sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ComponentCapabilityExemption:
    component_type: str
    owner: str
    reason: str
    source_digest: str
class ComponentCapabilityRegistry:
    """经校验的不可变 registry 与正交能力投影。"""

    def __init__(
        self,
        components: Mapping[str, ComponentCapability],
        exemptions: tuple[ComponentCapabilityExemption, ...],
    ) -> None:
        self._components = MappingProxyType(dict(components))
        self._exemptions = exemptions

    @property
    def components(self) -> Mapping[str, ComponentCapability]:
        return self._components

    @property
    def exemptions(self) -> tuple[ComponentCapabilityExemption, ...]:
        return self._exemptions

    @property
    def component_types(self) -> frozenset[str]:
        return frozenset(self._components)

    def get(self, component_type: str) -> ComponentCapability | None:
        return self._components.get(component_type)

    def require(self, component_type: str) -> ComponentCapability:
        capability = self.get(component_type)
        if capability is None:
            raise KeyError(f"未登记 componentType: {component_type}")
        return capability

    def by_host_policy(self, policy: str) -> frozenset[str]:
        if policy not in HOST_POLICIES:
            raise ValueError(f"未知 host policy: {policy}")
        return frozenset(
            key for key, value in self._components.items() if value.host_policy == policy
        )

    @property
    def backend_renderer_types(self) -> frozenset[str]:
        return frozenset(
            key for key, value in self._components.items() if value.has_backend_renderer
        )

    @property
    def frontend_component_types(self) -> frozenset[str]:
        return frozenset(
            key for key, value in self._components.items() if value.has_frontend_component
        )

    @property
    def override_allowed_types(self) -> frozenset[str]:
        return frozenset(
            key for key, value in self._components.items() if value.override_allowed
        )

    def types_from_source(self, source_name: str) -> frozenset[str]:
        """Project componentTypes that list ``source_name`` in their provenance."""
        return frozenset(
            key for key, value in self._components.items() if source_name in value.sources
        )


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ComponentCapabilityManifestError(f"JSON 重复键: {key}")
        result[key] = value
    return result
def _expect_non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ComponentCapabilityManifestError(f"{field} 必须为非空字符串")
    return value


def _parse_capability(component_type: str, raw: Any) -> ComponentCapability:
    if not _COMPONENT_TYPE_RE.fullmatch(component_type):
        raise ComponentCapabilityManifestError(f"非法 componentType: {component_type!r}")
    if not isinstance(raw, dict) or set(raw) != _COMPONENT_FIELDS:
        actual = sorted(raw) if isinstance(raw, dict) else type(raw).__name__
        raise ComponentCapabilityManifestError(
            f"{component_type} 字段不等于契约: {actual}"
        )
    for field in (
        "has_backend_renderer",
        "has_frontend_component",
        "override_allowed",
    ):
        if type(raw[field]) is not bool:
            raise ComponentCapabilityManifestError(f"{component_type}.{field} 必须为 bool")
    policy = _expect_non_empty_string(raw["host_policy"], f"{component_type}.host_policy")
    if policy not in HOST_POLICIES:
        raise ComponentCapabilityManifestError(f"{component_type} host_policy 非法: {policy}")
    status = _expect_non_empty_string(raw["status"], f"{component_type}.status")
    if status not in STATUSES:
        raise ComponentCapabilityManifestError(f"{component_type} status 非法: {status}")
    sources = raw["sources"]
    if not isinstance(sources, list) or not sources or not all(
        isinstance(source, str) and source for source in sources
    ):
        raise ComponentCapabilityManifestError(f"{component_type}.sources 必须为非空字符串数组")
    if len(sources) != len(set(sources)):
        raise ComponentCapabilityManifestError(f"{component_type}.sources 存在重复值")
    source_set = set(sources)
    source_flags = {
        "RENDERER_DISPATCH": raw["has_backend_renderer"],
        "REGISTRY_LIST": raw["has_frontend_component"],
        "VALID_COMPONENT_TYPES": raw["override_allowed"],
    }
    for source, enabled in source_flags.items():
        if (source in source_set) != enabled:
            raise ComponentCapabilityManifestError(
                f"{component_type}.{source} 与能力布尔值不一致"
            )
    return ComponentCapability(
        component_type=component_type,
        owner=_expect_non_empty_string(raw["owner"], f"{component_type}.owner"),
        has_backend_renderer=raw["has_backend_renderer"],
        has_frontend_component=raw["has_frontend_component"],
        override_allowed=raw["override_allowed"],
        host_policy=policy,
        status=status,
        sources=tuple(sources),
    )
def _parse_exemptions(
    raw: Any,
    component_types: frozenset[str],
) -> tuple[ComponentCapabilityExemption, ...]:
    if not isinstance(raw, list):
        raise ComponentCapabilityManifestError("exemptions 必须为数组")
    exemptions: list[ComponentCapabilityExemption] = []
    seen: set[str] = set()
    required = {"component_type", "owner", "reason", "source_digest"}
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or set(item) != required:
            raise ComponentCapabilityManifestError(f"exemptions[{index}] 字段不等于契约")
        component_type = _expect_non_empty_string(
            item["component_type"], f"exemptions[{index}].component_type"
        )
        if component_type not in component_types:
            raise ComponentCapabilityManifestError(
                f"exemption 指向未登记 componentType: {component_type}"
            )
        if component_type in seen:
            raise ComponentCapabilityManifestError(f"exemption 重复: {component_type}")
        seen.add(component_type)
        exemptions.append(
            ComponentCapabilityExemption(
                component_type=component_type,
                owner=_expect_non_empty_string(item["owner"], "exemption.owner"),
                reason=_expect_non_empty_string(item["reason"], "exemption.reason"),
                source_digest=_expect_non_empty_string(
                    item["source_digest"], "exemption.source_digest"
                ),
            )
        )
    return tuple(exemptions)


def load_component_capability_registry(
    path: Path = DEFAULT_MANIFEST_PATH,
) -> ComponentCapabilityRegistry:
    """严格读取 manifest；任何结构漂移都 fail-closed。"""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except (OSError, json.JSONDecodeError) as exc:
        raise ComponentCapabilityManifestError(f"无法读取 capability manifest: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != _ROOT_FIELDS:
        actual = sorted(raw) if isinstance(raw, dict) else type(raw).__name__
        raise ComponentCapabilityManifestError(f"manifest 根字段不等于契约: {actual}")
    if raw["schema_version"] != 1 or type(raw["schema_version"]) is not int:
        raise ComponentCapabilityManifestError("仅支持 schema_version=1")
    raw_components = raw["components"]
    if not isinstance(raw_components, dict) or not raw_components:
        raise ComponentCapabilityManifestError("components 必须为非空对象")
    components = {
        component_type: _parse_capability(component_type, item)
        for component_type, item in raw_components.items()
    }
    registry = ComponentCapabilityRegistry(
        components,
        _parse_exemptions(raw["exemptions"], frozenset(components)),
    )
    return registry
