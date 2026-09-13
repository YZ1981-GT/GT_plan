"""禁 DTD/entity/external fetch 的受限 XML 扫描（Requirement 4.2）。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 4.2, 3.3

本模块**不**用 lxml / 默认 ElementTree 的解析器去加载用户 XML：那两条路径
都会解析 DTD 或允许外部实体。这里只用 ``xml.parsers.expat``，并在回调里：

* 拒绝 DOCTYPE；
* 拒绝内部/外部/未解析实体；
* 拒绝 ``ExternalEntityRef``；
* 累计节点数、嵌套深度、字节数，超政策阈值即停。

公式文本只当字节流过 expat，不求值。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable
from xml.parsers import expat

from app.services.custom_template_ingestion.policy import (
    CustomTemplateIngestionPolicy,
    POLICY_V1,
)


class XmlRejectionCode(str, Enum):
    DTD = "PACKAGE.xml_dtd"
    ENTITY = "PACKAGE.xml_entity"
    EXTERNAL_ENTITY = "PACKAGE.xml_external_entity"
    DEPTH = "PACKAGE.xml_depth_exceeded"
    NODES = "PACKAGE.xml_nodes_exceeded"
    BYTES = "PACKAGE.xml_bytes_exceeded"
    MALFORMED = "PACKAGE.xml_malformed"


@dataclass(frozen=True, slots=True)
class XmlScanStats:
    bytes_read: int
    depth: int
    nodes: int


@dataclass(frozen=True, slots=True)
class XmlScanRejection:
    code: XmlRejectionCode
    locator: str
    detail: str
    stats: XmlScanStats


class _XmlBudgetExceeded(Exception):
    """内部控制流：预算超限，不是畸形 XML。"""

    def __init__(self, rejection: XmlScanRejection) -> None:
        super().__init__(rejection.detail)
        self.rejection = rejection


class _XmlPolicyRejected(Exception):
    def __init__(self, rejection: XmlScanRejection) -> None:
        super().__init__(rejection.detail)
        self.rejection = rejection


def scan_xml_bytes(
    payload: bytes,
    *,
    locator: str,
    policy: CustomTemplateIngestionPolicy = POLICY_V1,
    start_element_hook: Callable[[str, dict[str, str]], None] | None = None,
) -> XmlScanStats | XmlScanRejection:
    """扫描一段 XML。成功返回统计；失败返回结构化拒绝，不抛给调用方当放行。"""
    if len(payload) > policy.max_xml_bytes:
        return XmlScanRejection(
            code=XmlRejectionCode.BYTES,
            locator=locator,
            detail=f"XML 字节 {len(payload)} 超过 max_xml_bytes={policy.max_xml_bytes}",
            stats=XmlScanStats(bytes_read=len(payload), depth=0, nodes=0),
        )

    depth = 0
    max_depth = 0
    nodes = 0
    parser = expat.ParserCreate()
    # 🔴 禁止外部实体解析器被安装：保持默认 None，并显式拒绝回调。
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)

    def _stats() -> XmlScanStats:
        return XmlScanStats(bytes_read=len(payload), depth=max_depth, nodes=nodes)

    def _reject(code: XmlRejectionCode, detail: str) -> None:
        raise _XmlPolicyRejected(XmlScanRejection(
            code=code,
            locator=locator,
            detail=detail,
            stats=_stats(),
        ))

    def start(name: str, attrs: dict[str, str]) -> None:
        nonlocal depth, max_depth, nodes
        depth += 1
        nodes += 1
        if depth > max_depth:
            max_depth = depth
        if depth > policy.max_xml_depth:
            raise _XmlBudgetExceeded(XmlScanRejection(
                code=XmlRejectionCode.DEPTH,
                locator=locator,
                detail=f"XML 深度 {depth} 超过 max_xml_depth={policy.max_xml_depth}",
                stats=_stats(),
            ))
        if nodes > policy.max_xml_nodes:
            raise _XmlBudgetExceeded(XmlScanRejection(
                code=XmlRejectionCode.NODES,
                locator=locator,
                detail=f"XML 节点 {nodes} 超过 max_xml_nodes={policy.max_xml_nodes}",
                stats=_stats(),
            ))
        if start_element_hook is not None:
            start_element_hook(name, attrs)

    def end(_name: str) -> None:
        nonlocal depth
        depth -= 1

    def doctype(name: str, *_rest: object) -> None:
        _reject(XmlRejectionCode.DTD, f"DOCTYPE 被拒绝: {name}")

    def entity(*_args: object) -> None:
        _reject(XmlRejectionCode.ENTITY, "内部/外部实体声明被拒绝")

    def external_entity(*_args: object) -> int:
        _reject(XmlRejectionCode.EXTERNAL_ENTITY, "外部实体引用被拒绝")
        return 0

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.StartDoctypeDeclHandler = doctype
    parser.EntityDeclHandler = entity
    parser.UnparsedEntityDeclHandler = entity
    parser.ExternalEntityRefHandler = external_entity

    try:
        parser.Parse(payload, True)
    except _XmlPolicyRejected as exc:
        return exc.rejection
    except _XmlBudgetExceeded as exc:
        return exc.rejection
    except expat.ExpatError as exc:
        return XmlScanRejection(
            code=XmlRejectionCode.MALFORMED,
            locator=locator,
            detail=f"XML 损坏: {exc}",
            stats=_stats(),
        )
    return _stats()
