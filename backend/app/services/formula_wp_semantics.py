"""``WP()`` 取数路径的语义对照与已知差异登记（单一真源）。

spec: formula-management-runtime-closure Task 13（Requirements 5.1–5.4 / Property 17）；
formula-fetch-followup-defect-closure 6.5 按收敛后的现状改写。

两条取数路径的值都由 L1 ``formula_engine._handle_wp`` 求值，数据来源不同：

============  ================================================  ================================================
维度          预填路径 ``formula_preloader._load_wp``            报表 / 自定义公式路径 ``WPExecutor.execute``
============  ================================================  ================================================
实参          ``(wp_code, sheet_name, cell_ref)`` — 3 个         ``(wp_code, column[, field])`` — field 为 D2-3 字段或 A1
数据源        ``checklist_responses.remark``（经中文锚点映射）   ``working_paper.parsed_data``（顶层键 / 单元格）
存进 ctx 的键 ``wp_data[wp_code]['表!锚点']``                    ``wp_data[wp_code][列名]``
取不到时      不存键 ⇒ L1 三参报错，该格不写                     两参与 D2-3 ``Decimal('0')``（与「值确实为 0」不可区分）；第三参为 A1 时返回 None
============  ================================================  ================================================

🔴 2026-10-24（formula-fetch-followup 6.5）：预填收敛到「预载 + L1」（formula-execution-path-convergence）后，
``_handle_wp`` 只取两个实参、把第二参（表名）当列名取，而 ``_load_wp`` 按第三参（锚点）存值 ⇒ 预填与用户公式预览里的
三参 WP 即使锚点已对齐、底稿已录入也恒为 0（``ok=True``，没有任何告警）。本登记表当时还指向已删除的
``prefill_engine._resolve_wp_formula``（2638b32fd），守卫整文件红了却没人看 —— 「修一份时另一份不会被忘掉」正是在这里失效的。
现在两侧三参都写「表!锚点」，守卫 ``test_formula_wp_semantics`` 端到端钉住（预载 → 求值得到录入值、未对齐报错）。

🔴 本模块只做登记，不被任何取值实现引用（引用即双真源，守卫钉住）。
"""
from __future__ import annotations

from dataclasses import dataclass

#: 三处实现的定位（``模块路径::函数名`` / ``模块路径::类名.方法名``）。
PREFILL_WP_IMPL = "app/services/formula_preloader.py::_load_wp"
ENGINE_WP_IMPL = "app/services/formula_engine.py::_handle_wp"
EXECUTOR_WP_IMPL = "app/services/formula_engine.py::WPExecutor.execute"
#: 共享单元格读取函数（formula-hub ADR-FHIC-06 第 1 点 / §8.2；acnr-foundation-defect-closure T11 先落地）
WP_CELL_READER_IMPL = "app/services/wp_cell_reader.py::resolve_wp_cell"


@dataclass(frozen=True)
class WpImplSpec:
    """一处 ``WP()`` 实现的语义登记。"""

    impl: str
    #: 公式位置实参名（顺序即位置语义）
    positional_args: tuple[str, ...]
    data_source: str
    #: 取不到值时的结果（字面描述，不是可执行代码）
    on_missing: str
    #: 实测状态，必须含实测日期
    measured: str


WP_IMPLS: tuple[WpImplSpec, ...] = (
    WpImplSpec(
        impl=PREFILL_WP_IMPL,
        positional_args=("wp_code", "sheet_name", "cell_ref"),
        data_source=(
            "checklist_responses(wp_id, item_id).remark，经 prefill_anchor_map.resolve_anchor(wp_code, sheet_name, "
            "cell_ref) 把中文业务锚点名解析成 item_id；底稿定位经 wp_index JOIN；存 ctx.wp_data[wp_code]['表!锚点']"
        ),
        on_missing="不存键（未对齐记 warning、取值失败带堆栈）⇒ L1 三参报错，调用方不写该格",
        measured=(
            "2026-10-24 由 formula-fetch-followup 6.5 改为按「表!锚点」存值；此前按锚点存、L1 按表名取，"
            "预填路径三参 WP 恒为 0（2026-08-07 修过数据源的那份 prefill_engine 实现已在 2638b32fd 删除）"
        ),
    ),
    WpImplSpec(
        impl=ENGINE_WP_IMPL,
        positional_args=("wp_code", "sheet_name", "cell_ref"),
        data_source=(
            "ctx.wp_data[wp_code]：三参取 '表!锚点'（预填路径写入）；两参取列名，列名匹配 ^[A-Z]+\\d+$ 时按单元格地址"
            "（大写归一）"
        ),
        on_missing="三参报错（FormulaColumnError）；两参 Decimal('0')",
        measured="2026-10-24 实测：三参取到预载值、未对齐报错；两参行为未变",
    ),
    WpImplSpec(
        impl=EXECUTOR_WP_IMPL,
        positional_args=("wp_code", "column", "field"),
        data_source=(
            "working_paper.parsed_data：审定数 / 未审数 / 期初余额 / 期末余额映射顶层键，单元格地址经 ACNR 定位后从 "
            "extract_custom_cells 取；第二参含「坏账准备明细表」时走 D2-3 嵌套表（field 为第三参）；"
            "第三参为 A1 时经 acnr.wp_cell_target.read_formula_cell 按目录 sheet 精确取值（先 sheet 级底稿、无则父底稿），"
            "取不到返回 None"
        ),
        on_missing="Decimal('0')（两参：底稿不存在 / 键缺失 / 异常一律 0）；三参 A1 取不到返回 None",
        measured=(
            "2026-10-28 acnr-foundation-defect-closure T13：三参 A1 改为按 sheet 精确取值（原来把表名当列名、恒 0）；"
            "报表引擎与 FormulaEngine.execute 预载的两参 WP 与 D2-3 分支未改动"
        ),
    ),
    WpImplSpec(
        impl=WP_CELL_READER_IMPL,
        positional_args=("wp_code", "sheet_key", "cell"),
        data_source=(
            "working_paper.parsed_data（经 extract_custom_cells）；底稿经 wp_index.wp_code JOIN 未删 working_paper，"
            "工作表按 normalize_sheet_key 归一后与可接受键比较（sheet_key 为 None 时不判表）"
        ),
        on_missing="state=missing / blocked + 中文 reason，value=None（不代 0）",
        measured=(
            "2026-10-28 acnr-foundation-defect-closure T11 新建（formula-hub 任务 23 未入库）；当时尚无生产调用方，"
            "WPExecutor 两参分支改调它归 formula-hub 任务 23"
        ),
    ),
)


@dataclass(frozen=True)
class WpKnownDifference:
    """一条已知差异登记（未登记的差异即打红）。"""

    #: 差异维度键（守卫按它做集合精确相等断言）
    dimension: str
    detail: str
    #: 为什么不在这里统一
    reason: str
    #: 归属 spec（谁负责收敛）
    owner_spec: str


WP_KNOWN_DIFFERENCES: tuple[WpKnownDifference, ...] = (
    WpKnownDifference(
        dimension="positional_arg_count",
        detail=(
            "预填路径三参读 checklist_responses；WPExecutor 三参只对 A1 第三参按 sheet 精确取值，语义第三参仍不支持；"
            "报表路径三参报错"
        ),
        reason=(
            "统一实参要么给 WPExecutor 加 sheet 维度（改 parsed_data 取数口径，波及报表与全部 Tier A 求值），要么让预填路径"
            "丢掉 sheet（丢信息），均需另立 spec 裁决"
        ),
        owner_spec="formula-fetch-followup-defect-closure",
    ),
    WpKnownDifference(
        dimension="on_missing_return",
        detail="预填路径（三参）取不到报错、该格不写；WPExecutor 与 L1 两参取不到返 Decimal('0')（与「值确实为 0」不可区分）",
        reason=(
            "两参改为报错会让所有含两参 WP() 的报表 / Tier A 公式在缺数据时整格失败（现为取 0），属口径变更需单独裁决"
        ),
        owner_spec="formula-fetch-followup-defect-closure",
    ),
    WpKnownDifference(
        dimension="data_source",
        detail=(
            "预填路径读 checklist_responses.remark（经中文锚点 → item_id 声明式映射）；WPExecutor 读 working_paper.parsed_data"
            " ⇒ 同一个底稿数在两条路径里取的是两个不同容器的值"
        ),
        reason=(
            "让 WPExecutor 也走 checklist_responses 需逐个底稿登记锚点（ANCHOR_MAP 只覆盖部分底稿）并改报表取数口径，超出本 spec"
        ),
        owner_spec="formula-fetch-followup-defect-closure",
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
