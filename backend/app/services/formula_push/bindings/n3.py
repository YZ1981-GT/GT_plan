"""N3 递延所得税负债 binding（conclusion 列）。

与 NoteDirectBinding 同形，唯一区别是 ``storage_field = "conclusion"``：
N3 前端 ``useN3FormData.setField()`` 全部写 ``checklist_responses.conclusion``，
而非 E1/K1/L6 等使用的 ``remark``。

spec: formula-push-all-subjects-rollout（L6/N3 接入批次）
"""
from __future__ import annotations

from app.services.formula_push.bindings.note_direct import NoteDirectBinding, note_direct_for


class N3Binding(NoteDirectBinding):
    """N3 递延所得税负债 — conclusion 列 binding。

    继承 NoteDirectBinding 的全部五方法协议，仅覆写 ``storage_field``。
    engine 在 ``_push_workpaper`` 中通过 ``getattr(binding, 'storage_field', 'remark')``
    读取此属性，决定从 ``checklist_responses`` 的哪个列读写。
    """

    storage_field: str = "conclusion"


def n3_binding() -> N3Binding:
    """工厂函数：从 ``wp_account_mapping.json`` 加载 N3 科目信息并创建实例。"""
    base = note_direct_for("N3")
    binding = N3Binding(
        wp_code=base.wp_code,
        account_codes=base.account_prefixes,
        account_name=base._account_name,
        is_income=False,
    )
    return binding
