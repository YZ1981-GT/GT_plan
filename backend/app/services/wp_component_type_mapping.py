"""class_code → componentType 纯函数映射（单一真源）

此模块是 derive_component_type 的共享核心，被两处调用方包装：
- wp_classification_service.derive_component_type: None 时抛 ClassificationNotFoundError
- generate_wp_render_schema.derive_component_type: None 时 fallback "univer"

设计参见 spec design §2。
"""

from __future__ import annotations

# ─── 9 类 class_code 前缀 → componentType 映射 ─────────────────────────────
_CLASS_TO_COMPONENT: dict[str, str] = {
    "A-": "a-program-console",
    "B-": "b-index",
    "C-": "c-note-table",
    "E-": "e-control-test",
    "F-": "univer",
    "G-": "univer",
    "H-": "h-static-doc",
    "I-": "skip",
}

# D 类子路由映射（基于 class_code 具体值）
_D_SUB_ROUTING: dict[str, str] = {
    "D-函证": "d-form-confirmation",
    "D-盘点": "d-form-confirmation",
    "D-访谈": "d-form-confirmation",
    "D-询证": "d-form-confirmation",
    "D-政策检查": "d-form-paragraph",
    "D-业务模式": "d-form-qa",
    "D-复核记录": "d-form-review",
    "D-复核": "d-form-review",
}

# D 类默认 componentType（表格型检查表）
_D_DEFAULT = "d-form-table"

# F 类子路由映射（精确匹配优先于 _CLASS_TO_COMPONENT["F-"] 前缀 fallback）
# F-审定表 / F-明细表 → audit-sheet（可编辑表格组件，列结构从模板动态解析）；
# 其余 F-（F-分析表/F-汇总表 等）仍 fallback 到 univer
_F_SUB_ROUTING: dict[str, str] = {
    "F-审定表": "audit-sheet",
    "F-明细表": "audit-sheet",
}


def class_code_to_component(class_code: str) -> str | None:
    """纯函数：class_code → componentType，None 表示未匹配。

    映射规则：
    - D- 前缀：查 _D_SUB_ROUTING 精确匹配，fallback 到 _D_DEFAULT ("d-form-table")
    - F- 前缀：查 _F_SUB_ROUTING 精确匹配，fallback 到 "univer"
    - 其他前缀：遍历 _CLASS_TO_COMPONENT 前缀匹配
    - 均未匹配：返回 None（由调用方决定 fallback 策略）
    """
    if class_code.startswith("D-"):
        return _D_SUB_ROUTING.get(class_code, _D_DEFAULT)

    if class_code.startswith("F-"):
        component_type = _F_SUB_ROUTING.get(class_code)
        if component_type:
            return component_type
        # fallback: 其余 F- 返回 univer
        return "univer"

    for prefix, component_type in _CLASS_TO_COMPONENT.items():
        if class_code.startswith(prefix):
            return component_type

    return None
