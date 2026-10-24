"""四表口径单一来源的「声明科目」统一入口 —— 按底稿编码查兜底标准码。

各循环的单一来源写法不同：K 循环是 ``KCycleSpec``（``fallback_standard`` / ``fallback_provision`` /
``extra_standard_codes``），E1 / J 循环与 D/F/G/H/I/L/M/N 是语义规格（``slots[*].fallback_standard_codes``）。
映射表守卫、推送 binding 守卫等需要「这张底稿在单一来源里声明了哪些科目」时一律从这里取，禁止各写一份
（各写一份就会出现两个守卫对同一底稿得出不同结论）。

返回值约定：
- ``None``：该底稿在单一来源里**没有声明**（A/B/C/S 类、函证底稿等）；
- 空元组：声明了、但**没有标准科目码**（宁缺勿造：L7 其他非流动负债、M8 一般风险准备、K4 其他流动负债……）；
- 非空元组：按声明顺序去重。

spec: .kiro/specs/formula-fetch-followup-defect-closure/ R1.6
"""

from __future__ import annotations

import importlib
from typing import Any

#: D/F/G/H/I/L/M/N 循环的语义规格表（模块名, 变量名）
_SEMANTIC_SPEC_TABLES: tuple[tuple[str, str], ...] = (
    ("d_cycle_specs", "D_CYCLE_SPECS"),
    ("f_cycle_specs", "F_CYCLE_SPECS"),
    ("g_cycle_specs", "G_CYCLE_SPECS"),
    ("h_cycle_specs", "H_CYCLE_SPECS"),
    ("i_cycle_specs", "I_CYCLE_SPECS"),
    ("l_cycle_specs", "L_CYCLE_SPECS"),
    ("m_cycle_specs", "M_CYCLE_SPECS"),
    ("n_cycle_specs", "N_CYCLE_SPECS"),
)


def _dedupe(codes) -> tuple[str, ...]:
    return tuple(dict.fromkeys(c for c in codes if c))


def _k_spec(wp_code: str):
    from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS

    return K_CYCLE_SPECS.get(wp_code)


def _semantic_spec(wp_code: str) -> Any | None:
    if wp_code == "E1":
        from app.services.four_table.e_cycle_specs import E1_MONETARY_FUND_SPEC

        return E1_MONETARY_FUND_SPEC
    if wp_code[:1] == "J":
        from app.services.four_table.j_cycle_account_scope import j_semantic_spec_of

        return j_semantic_spec_of(wp_code)
    for module, name in _SEMANTIC_SPEC_TABLES:
        specs = getattr(importlib.import_module(f"app.services.four_table.{module}"), name)
        if wp_code in specs:
            return specs[wp_code]
    return None


def declared_codes(wp_code: str) -> tuple[str, ...] | None:
    """该底稿声明的全部科目（原值 / 备抵 / 附加槽）。"""
    k = _k_spec(wp_code)
    if k is not None:
        return _dedupe([k.fallback_standard, *k.fallback_provision, *k.extra_standard_codes])
    spec = _semantic_spec(wp_code)
    if spec is None:
        return None
    return _dedupe(c for slot in spec.slots for c in slot.fallback_standard_codes)


def declared_gross_codes(wp_code: str) -> tuple[str, ...] | None:
    """该底稿原值槽的兜底码（K 循环 = ``fallback_standard``；E1 = 现金 / 银行 / 其他货币资金三槽；其余 = ``gross`` 槽）。"""
    k = _k_spec(wp_code)
    if k is not None:
        return _dedupe([k.fallback_standard])
    spec = _semantic_spec(wp_code)
    if spec is None:
        return None
    if wp_code == "E1":
        return _dedupe(c for slot in spec.slots for c in slot.fallback_standard_codes)
    return _dedupe(c for slot in spec.slots if slot.key == "gross" for c in slot.fallback_standard_codes)


__all__ = ["declared_codes", "declared_gross_codes"]
