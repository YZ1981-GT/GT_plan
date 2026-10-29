"""ACNR 身份判定与取值的错误码 → 中文文案集中表（唯一来源）。

目标：`exact_identity`、`wp_cell_target`、acnr_targets 编排、V2 规范化、stale 引擎、
CCR 检查器都从这里取中文原因，避免各处散落、口径漂移。现状（段四审计 F4-13 更正）：
`exact_identity`、`resolve_identity`（停用条目原因，T10）与 `wp_cell_target`（取值原因细化与借名，T12）使用；
acnr_targets 取值编排 `acnr_target_values`（拒绝分类，T14）使用 `TARGET_REJECT_REASONS`；`v2_canonical`
（V2 节点与 stale 入口，T21）使用 `NODE_UNRESOLVED_REASONS`；CCR 检查器随 T22 接入。

只依赖标准库（供 `check_ccr_resolve` 等仅标准库的脚本复用，CI 无需新增依赖）。

设计依据：design.md §6.2 / §2.3 / §10.2。
"""
from __future__ import annotations

# ─── sheet / cell 身份判定（exact_identity） ───────────────────────────────

#: sheet_of 的状态 → 中文模板。用 {wp_code} / {text} / {candidates} / {codes} 填充。
SHEET_REASONS: dict[str, str] = {
    "wp_not_in_catalog": "底稿「{wp_code}」不在地址目录中，无法定位其子表",
    "ambiguous": "名称「{text}」在「{wp_code}」下对应多张表（{candidates}），请改用 sheet 编码指定",
    "alias_forbidden": "平台底稿名「{text}」在「{wp_code}」下同时用于多张表（{codes}），请改用 sheet 编码",
    "not_found": "在「{wp_code}」下找不到名称或编码为「{text}」的表",
}

#: cell_of 的状态 → 中文模板。
CELL_REASONS: dict[str, str] = {
    "bad_a1": "单元格坐标「{a1}」不是合法的 A1 地址（形如 C10）",
    "sheet_unresolved": "{sheet_reason}",
}


def sheet_reason(state: str, *, wp_code: str = "", text: str = "",
                 candidates: list[str] | None = None,
                 codes: list[str] | None = None) -> str:
    """组装 sheet_of 非 ok 状态的中文原因。"""
    tmpl = SHEET_REASONS.get(state, "无法解析表「{text}」")
    return tmpl.format(
        wp_code=wp_code,
        text=text,
        candidates="、".join(candidates or []),
        codes="、".join(codes or []),
    )


# ─── acnr_targets 逐项拒绝分类（design §2.3） ───────────────────────────────

#: error_code → 面向用户的中文说明（可带候选 / required_context 由调用方补）。
TARGET_REJECT_REASONS: dict[str, str] = {
    "resolve_unavailable": "地址解析服务暂不可用，未执行查询，请稍后重试",
    "external_namespace": "该引用属于外部模块，地址库不负责取值",
    "unsupported_domain": "该地址不是底稿单元格（tb / 报表 / 附注 / 辅助域），本功能暂不支持取值",
    "runtime_entry": "该地址是运行时动态条目，无法按静态目录取值",
    "sheet_level": "所选为整张表、不是单元格，请细化到具体单元格",
    "deprecated": "该地址已停用，建议改用 {replaced_by}",
    "ambiguous": "该引用在目录中有多处匹配，请补充上下文后再取值",
    "unresolvable": "无法在地址目录中解析该引用",
}


# ─── 取值状态原因（design §2.2 的 reason_code → 中文） ──────────────────────

#: 取值 missing / blocked / text 的 reason_code → 中文。
CELL_VALUE_REASONS: dict[str, str] = {
    "non_numeric": "该单元格为文本，不是数值",
    "year_mismatch": "项目中该底稿的年度与所取年度不一致",
    "wp_missing": "项目中尚未生成该底稿",
    "sheet_missing": "该底稿中没有找到对应的表",
    "cell_empty": "该单元格为空",
    "value_in_form_storage": "该底稿以表单方式录入，数据不在单元格中，本期暂不支持取值",
    "value_in_file": "该底稿只有在线编辑文件、未解析出单元格数据",
    "wp_ambiguous": "项目中该底稿有多份，无法确定取哪一份",
    "sheet_ambiguous": "表名有歧义，无法确定取哪一张表",
    "sheet_name_borrowed": "该表名被父级条目借用，无法唯一定位单元格所在表",
}


# ─── V2 / stale 节点规范化（design §10.2） ─────────────────────────────────

#: 节点无法得到规范 addr_id 时的 unresolved_code → 中文。
NODE_UNRESOLVED_REASONS: dict[str, str] = {
    "cell_not_in_catalog": "该单元格所在表在目录中，但单元格坐标未登记",
    "label_not_a1": "引用末段是语义标签、不是 A1 单元格坐标",
    "ambiguous_sheet_name": "表名在该底稿下有多处匹配，无法确定唯一表",
    "alias_forbidden": "表名被多张表共用，请改用 sheet 编码",
    "sheet_not_in_catalog": "该表不在地址目录中",
    "wp_not_in_catalog": "该底稿不在地址目录中",
    "not_wellformed": "引用形态不符合「底稿:表:末段」规范",
    # T21 补充（design §10.2 表外）：V2 读端点里的附注 / 报表目标节点
    "not_workpaper_node": "该节点不是底稿单元格，地址库不为其分配底稿地址",
}


# ─── full_resolve 多命中（design §12.2；T31） ─────────────────────────────
#
# `step1_identity`（表名多义 / 禁止别名）已自带 reason 与 required_context；这里补的是
# 它之后、按坐标或语义标签在表内多命中、以及裸编码在多张底稿下多命中的几种。

#: 多命中类型 → (原因模板, 需补的上下文, 下一步)
_AMBIGUOUS: dict[str, tuple[str, list[str], str]] = {
    "cell": (
        "该引用在同一张表下匹配到多个单元格",
        ["cell_address"],
        "请改用单元格坐标（形如 C10）指定，或从候选中选择一个",
    ),
    "sheet_code": (
        "编码「{text}」在多张底稿下都登记了",
        ["parent_wp_code"],
        "请补上所属底稿编码再解析，或从候选中选择一个",
    ),
    "runtime": (
        "该自定义底稿下有多个同名单元格",
        ["cell_address"],
        "请改用单元格坐标指定，或从候选中选择一个",
    ),
}

#: 多命中类型（供守卫遍历，避免写死清单）
AMBIGUOUS_KINDS: tuple[str, ...] = tuple(_AMBIGUOUS)


def ambiguous_fields(kind: str, *, text: str = "") -> dict[str, object]:
    """多命中时的 reason / required_context / next_step（直接展开进 ResolveResult）。"""
    reason, ctx, next_step = _AMBIGUOUS[kind]
    return {
        "reason": reason.format(text=text),
        "required_context": list(ctx),
        "next_step": next_step,
    }


# ─── 外部命名空间（design §12.4；T31） ────────────────────────────────────
#
# 地址库登记 Adj/Att/EQCR/Calc/Sample/Confirm 这六类引用，但不把它们解析到物理
# 单元格。标签与下一步文案的唯一来源是 grammar_v1.json 的 label_zh / next_step_zh
# （经 `grammar.external_namespace_meta` 读取），这里只放拼装模板，避免同一句话在
# 前后端各写一份。

#: 外部命名空间不可定位时的原因；{label_zh} 填 grammar 里的中文标签。
EXTERNAL_NAMESPACE_REASON = "「{label_zh}」类引用暂不支持定位到物理地址"


def external_namespace_reason(label_zh: str) -> str:
    """组装外部命名空间的中文原因。label_zh 为空时退化为「外部模块」。"""
    return EXTERNAL_NAMESPACE_REASON.format(label_zh=label_zh or "外部模块")


# ─── 停用条目（design §3.3） ───────────────────────────────────────────────

#: full_resolve 命中停用条目时的原因；{replaced_by} 填替代地址的显示名。
DEPRECATED_REASON = "该地址已停用，建议改用 {replaced_by}"


# ─── 版本锁 / 快照（design §8.3） ──────────────────────────────────────────

REGISTRY_SNAPSHOT_MISSING = (
    "项目锁定的地址目录版本 {version} 快照缺失，无法按归档时的目录解析；请联系管理员恢复快照"
)
REGISTRY_SNAPSHOT_INVALID = "项目锁定的地址目录版本 {version} 快照内容损坏：{detail}"
REGISTRY_LOCK_FAILED = "无法记录归档时的地址目录版本：{detail}；本次归档未生效"
