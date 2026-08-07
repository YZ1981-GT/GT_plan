"""两份 ``WP()`` 实现的语义对照与已知差异登记（单一真源）。

spec: formula-management-runtime-closure Task 13（Requirements 5.1–5.4 / Property 17）

平台有**两个**公式引擎各实现一份 ``WP()``，语义并不等价：

===============  ===============================================  ==============================================
维度             ``prefill_engine._resolve_wp_formula``            ``formula_engine._handle_wp``
===============  ===============================================  ==============================================
实参             ``(wp_code, sheet_name, cell_ref)`` — **3 个**    ``(wp_code, col_name)`` — **2 个**
数据源           ``checklist_responses.remark``（经锚点映射）       ``ctx.wp_data[wp_code]``（调用方预载）
sheet 维度       有                                                **无**
取不到时         ``None``                                          ``Decimal('0')``
实测可用性       已修（2026-08-07 由对方 spec 换数据源）           可用（取决于调用方是否预载）
===============  ===============================================  ==============================================

🔴🔴 **2026-08-07：prefill 侧数据源已被对方 spec 换掉，本登记表随之同步过一次。**
原读 ``WorkingPaper.parsed_data['cells']`` 是**死链**（全库 0 行），
``prefill-wp-prev-resolution-repair`` 改为经 :mod:`app.services.prefill_anchor_map`
的声明式锚点映射读 ``checklist_responses(wp_id, item_id).remark``。
本守卫因此打红一次并被同步 —— **这正是 R5.3 设计的工作方式**，不是回归。

🔴 **本模块只做一致性登记与守卫，不改任何取值实现**（R5.4）——
死链修复本体归 spec ``prefill-wp-prev-resolution-repair``；改
``_handle_wp`` 的返回语义会波及 Tier A 求值（属范围外）。

🔴🔴 **spec design 首版把两者的实参写成「(wp_code, sheet, cell_ref) / 同」是错的**
（2026-08-07 逐个读源码实证）：``_handle_wp`` 只取两个实参，且第二个既可以是
**列名**也可以是**单元格地址**（正则 ``^[A-Z]+\\d+$`` 判别），压根没有 sheet 维度。
故 Property 17 的判据**不能**是「实参个数一致」（按现状必打红且红得没有意义），
而应是「**差异逐条登记且带理由**」——
`prefill-wp-prev-resolution-repair` 修其中一份时，本模块的登记必须同步更新，
否则守卫打红提醒。
"""
from __future__ import annotations

from dataclasses import dataclass

#: 两份实现的定位（``模块路径::函数名``）。
PREFILL_WP_IMPL = "app/services/prefill_engine.py::_resolve_wp_formula"
ENGINE_WP_IMPL = "app/services/formula_engine.py::_handle_wp"


@dataclass(frozen=True)
class WpImplSpec:
    """一份 ``WP()`` 实现的语义登记。"""

    impl: str
    #: 位置实参名（顺序即位置语义）
    positional_args: tuple[str, ...]
    data_source: str
    #: 取不到值时的返回（字面描述，不是可执行代码）
    on_missing: str
    #: 实测可用性，必须含实测日期
    measured: str


WP_IMPLS: tuple[WpImplSpec, ...] = (
    WpImplSpec(
        impl=PREFILL_WP_IMPL,
        positional_args=("wp_code", "sheet_name", "cell_ref"),
        data_source=(
            "checklist_responses(wp_id, item_id).remark，经 prefill_anchor_map."
            "resolve_anchor(wp_code, sheet_name, cell_ref) 把中文业务锚点名解析成 item_id；"
            "底稿定位经 wp_index JOIN（不读 parsed_data['wp_code']）"
        ),
        on_missing="None（调用方据此跳过该格，不写值）",
        measured=(
            "2026-08-07 由 spec `prefill-wp-prev-resolution-repair` 换数据源修复死链。"
            "改造前读 `parsed_data['cells']`，该键全库 **0 行**"
            "（2779 个未删除底稿 / 492 个有 parsed_data）⇒ 176 条 WP() 预设恒返 None；"
            "现读 checklist_responses.remark，锚点未登记时 logger.warning 不静默"
        ),
    ),
    WpImplSpec(
        impl=ENGINE_WP_IMPL,
        positional_args=("wp_code", "col_name"),
        data_source=(
            "ctx.wp_data[wp_code][col_name]；col_name 匹配 ^[A-Z]+\\d+$ 时按"
            "单元格地址取（大写归一），否则按列名取"
        ),
        on_missing="Decimal('0')（与「值确实为 0」不可区分）",
        measured=(
            "2026-08-07 实证可用，但取决于调用方是否预载 ctx.wp_data；"
            "未预载时因 on_missing 返 0 而静默"
        ),
    ),
)


@dataclass(frozen=True)
class WpKnownDifference:
    """一条已知差异登记（未登记的差异即打红）。"""

    #: 差异维度键（守卫按它做集合精确相等断言）
    dimension: str
    detail: str
    #: 为什么**不在本 spec 修**（R5.4：本 spec 只建守卫）
    reason: str
    #: 归属 spec（谁负责收敛）
    owner_spec: str


WP_KNOWN_DIFFERENCES: tuple[WpKnownDifference, ...] = (
    WpKnownDifference(
        dimension="positional_arg_count",
        detail=(
            "prefill 侧 3 个实参（含 sheet_name），engine 侧 2 个（无 sheet 维度）"
            "⇒ 同一条 `WP('D1','明细表D1-2','B5')` 在两个引擎里的第 2 个实参语义完全不同"
            "（前者是 sheet 名、后者会被当成列名/单元格地址）"
        ),
        reason=(
            "统一实参要么给 engine 侧加 sheet 维度（改 ctx.wp_data 的键结构，"
            "波及全部 Tier A 求值与 40+ 预载点），要么让 prefill 侧丢掉 sheet"
            "（丢信息）⇒ 两条都超出本 spec 半径"
        ),
        owner_spec="prefill-wp-prev-resolution-repair",
    ),
    WpKnownDifference(
        dimension="on_missing_return",
        detail="prefill 返 None（可区分「取不到」），engine 返 Decimal('0')（不可区分）",
        reason=(
            "改 `_handle_wp` 返 None 会让所有含 WP() 的 Tier A 公式在缺数据时"
            "整格失败（当前是静默取 0），属口径变更需单独裁决"
        ),
        owner_spec="prefill-wp-prev-resolution-repair",
    ),
    WpKnownDifference(
        dimension="data_source",
        detail=(
            "prefill 读 DB（`checklist_responses.remark`，经 prefill_anchor_map 中文锚点"
            "→ item_id 声明式映射）；engine 读内存（`ctx.wp_data`，由调用方预载）"
            "⇒ 同一条 WP() 在两个引擎里取的是两个不同容器的值"
        ),
        reason=(
            "让 engine 侧也走 checklist_responses 需要给 Tier A 求值加异步 DB 访问"
            "（`_handle_wp` 是同步纯函数、ctx 预载模型由 40+ 调用方共享）⇒ 超本 spec 半径"
        ),
        owner_spec="prefill-wp-prev-resolution-repair",
    ),
)

#: 已登记差异维度集合（守卫用它做精确相等断言 —— 新增差异必须登记）。
REGISTERED_DIFFERENCE_DIMENSIONS: frozenset[str] = frozenset(
    d.dimension for d in WP_KNOWN_DIFFERENCES
)


def impl_of(impl: str) -> WpImplSpec | None:
    """按实现定位取登记条目。"""
    for spec in WP_IMPLS:
        if spec.impl == impl:
            return spec
    return None


def difference_of(dimension: str) -> WpKnownDifference | None:
    """按差异维度取登记条目；未登记返回 ``None``（调用方打红）。"""
    for diff in WP_KNOWN_DIFFERENCES:
        if diff.dimension == dimension:
            return diff
    return None
