"""roundtrip 等值判据：materialize 写进 OOXML 的受管值，反读回来必须等值（Property 65）。

为什么独立成模块（spec onlyoffice-sheet-open-via-published-artifact 批 2）：
判据本身有**两处**要共用同一个「空表示」口径（missing 判据 + 逐键比较），
放在 `content_mutation` 里既撑破行数门，也让「判据住哪」不清晰。
本模块**只读纯函数**：不碰 DB、不碰磁盘、不构造操作。

🔴 空表示的第三态（本批修的真缺陷）：
`extract` 对空格 `<c r=".."/>` **不产出该键**（`excel_extract._collect_fields` 的
`if not present: continue`），而 materialize 刻意把「未勾 / 空 enum-text」写成空格
（写 `<v>0</v>` 会把「未填」变成「填了 false」）。裸键级差集会把「双方都表示无值」
误判成「materialize 没写进去」⇒ 提交侧为空而反读缺键**不算 missing**（fail-closed：
提交侧非空而缺键照样报）。
"""

from __future__ import annotations

from typing import Any

from app.services.workpaper_sync.adapters.base import Projection
from app.services.workpaper_sync.contracts import (
    FieldMode,
    SyncContract,
    is_template_skeleton_identity,
)
from app.services.workpaper_sync.merge import (
    PROTECTED_MODES,
    values_equal,
)

def _is_roundtrip_empty(value: Any) -> bool:
    """roundtrip 等值判据里「该单元格无值」的空表示。

    仅用于 `_assert_roundtrip_equivalent`：提交空 enum/text（`""`）写进 OOXML 得到空
    单元格，extract 反读空单元格得到 `None` —— 二者表示同一件事。`None` 与空白字符串
    都算空；数值 `0` / `False` / `Decimal("0")` **不算**（它们是真实值，不得折叠成空）。
    不改全局 `merge.normalize_value`（那里刻意区分 `""`/`None`/`MISSING`）。
    """
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def assert_roundtrip_equivalent(
    *, intended: Projection, extracted: Projection, contract: SyncContract
) -> None:
    """反读出来的受管 projection 必须与要提交的逐字段等值（Property 65）。

    比较口径复用 `merge.values_equal`（金额 Decimal / 日期 ISO / 文本仅归一
    CRLF），不自己写第二套。`word_only` 字段被排除：它们按定义永不进 HTML
    projection，拿它们比较会让 Word 底稿恒判不等值。
    """
    # 🔴 异常类型定义在 `content_mutation`（继承 `ContentMutationError`），
    #    本模块不能模块级 import 它（`content_mutation` 会转发本模块的函数 ⇒ 循环）。
    #    延迟导入既避免循环，也保证**抛的仍是同一个类对象**（调用方
    #    `except RoundtripEquivalenceError` 照常生效）。
    from app.services.workpaper_sync.content_mutation import RoundtripEquivalenceError

    word_only = {
        spec.stable_field_key
        for spec in contract.all_fields()
        if spec.mode is FieldMode.word_only
    }
    # formula / auto_source 不由 materialize 写值；Excel 空公式格反读常为 0，
    # store 侧多为 None —— 把它们拉进 Property 65 会在 OO 重算后假红（G4-0d）。
    protected = {
        spec.stable_field_key
        for spec in contract.all_fields()
        if spec.mode in PROTECTED_MODES
    }

    def _key_excluded(key: str, templates: set[str]) -> bool:
        if key in templates:
            return True
        return any(
            "{row_uuid}" in tpl
            and key.startswith(tpl.split("{row_uuid}")[0])
            and key.endswith(tpl.split("{row_uuid}")[-1])
            for tpl in templates
        )

    def _managed(proj: Projection) -> dict[str, Any]:
        return {
            key: value
            for key, value in proj.values.items()
            if not _key_excluded(key, word_only) and not _key_excluded(key, protected)
        }

    left = _managed(intended)
    right = _managed(extracted)
    # 空表示第三态：提交侧空 + 反读侧「键不存在」= 同一件事，不算 missing。
    #   `extract` 对空格 `<c r=".."/>` **不产出该键**（`_collect_fields` 的
    #   `if not present: continue`），而 materialize 刻意把「未勾 / 空 enum-text」写成空格
    #   （写成 `<v>0</v>` 会把「未填」变成「填了 false」）。裸键级差集会把这类
    #   「双方都表示无值」误判成「materialize 没写进去」。
    # 🔴 仍 fail-closed：只豁免**提交侧确实是空表示**的键；非空而缺键照样报。
    #   `False`/`0`/`Decimal("0")` 不算空（`_is_roundtrip_empty` 刻意排除）。
    #   口径与下方逐键比较共用同一个 `_is_roundtrip_empty`（两套必漂移）。
    missing = sorted(
        key
        for key in set(left) - set(right)
        if not _is_roundtrip_empty(left[key].value)
    )
    if missing:
        raise RoundtripEquivalenceError(
            f"staged representation 反读后缺少受管字段 {missing[:5]}"
            f"（共 {len(missing)} 个）—— materialize 没有把它们写进 OOXML，"
            "或 extract 找不到 identity 载体"
        )
    extra = sorted(set(right) - set(left))
    # ── 模板骨架行的 extra 豁免（spec workpaper-sync-managed-row-convergence E3）──
    #
    # ═══ 为什么必须豁免 ═══
    #
    # instrumentation 给模板的**每个**受管行预生成 `GTROW-{template}-{row:04d}` 身份，
    # 而模板在受管区内**自带非空业务值**（实测 D4 权威模板：166 个 editable 非空字段，
    # 含 `年度预算`/`1月`~`12月`/`1.销售商品收入` 这类**模板应有内容**，以及
    # `大额客户一`/`产品1` 这类示例）。store 只声明「有业务数据的行」，所以这些骨架行
    # 不在 `intended.row_keys` 里是**常态**。
    #
    # 后果：extract 反读出模板自带的值 ⇒ 它们恒为 `extra` ⇒ `roundtrip_projection_mismatch`
    # 恒 500（D4 实测 77 个 extra 全部来自 46 个骨架身份），而三条显而易见的出路都不通：
    #   * 当 stale 删掉骨架行 → `IdentityRetentionError`（Property 23/66，实测 4 红）
    #   * 清空模板占位内容    → 会连 `年度预算`/`1月` 一起清掉，破坏模板业务语义
    #   * 让 store 认领它们    → store 侧 merge 语义「不追加 base 没有的行」，追不上
    #
    # ═══ 豁免条件是**合取**，不弱化 fail-closed ═══
    #
    #   ① 身份是模板骨架（`is_template_skeleton_identity`，与收敛判据共用真源）
    #   ② **且** store 在本次 projection 里**完全没声明**这一行
    #
    # ②是关键：它把豁免限定在「store 不负责的行」上。语义是诚实的 —— 那一行的 Excel
    # 侧内容不是 materialize 写的（materialize 只写 projection 里有的东西），所以判它
    # 「反读出未提交的受管字段」本就是归因错误。
    #
    # 反之两种情形**仍然报错**（fail-closed 未被削弱）：
    #   * store **声明了**某骨架行却缺字段 ⇒ ②不成立 ⇒ 仍报（store 认领了就要字段完整）
    #   * 非骨架身份（`d4r-*` / `xsheet-*` / `GTROW-MINTED-*`）的孤儿 ⇒ ①不成立 ⇒ 仍报
    #     （那才是真孤儿，由 `excel_materialize` 的受管行收敛负责删除/清空）
    if extra:
        declared: set[str] = set()
        for ids in (intended.row_keys or {}).values():
            declared.update(str(x) for x in (ids or ()))
        retained = []
        for key in extra:
            parts = key.split("/")
            identity = parts[1] if len(parts) >= 3 else ""
            if (
                identity
                and identity not in declared
                and is_template_skeleton_identity(identity)
            ):
                continue  # 模板自带内容，且 store 未声明该行 ⇒ 豁免
            retained.append(key)
        extra = retained
    if extra:
        raise RoundtripEquivalenceError(
            f"staged representation 反读出未提交的受管字段 {extra[:5]}"
            f"（共 {len(extra)} 个）—— 受管区域被写入了不属于本次 projection 的值"
        )
    for key in sorted(left):
        if key not in right:
            # 已被上方 missing 判据豁免（提交侧空表示、反读侧无该键）。
            continue
        mine, theirs = left[key], right[key]
        # roundtrip 空值等价：提交「空 enum/text」（`""`）写进 OOXML 得到空单元格，
        # extract 反读空单元格得到 `None` —— 两者表示同一件事「该格无值」。全局
        # `normalize_value` 刻意不折叠 `""`/`None`/`MISSING`（merge 场景「清空」与
        # 「从未设置」有别），故这里**仅在 roundtrip 场景**、且**两侧都为空表示**时
        # 视为等值；只要有一侧非空就仍走严格 `values_equal`（不会放过真实漂移）。
        if _is_roundtrip_empty(mine.value) and _is_roundtrip_empty(theirs.value):
            continue
        # 🔴 归一化失败必须**点名字段**。`normalize_value` 抛的
        #    `ValueNormalizationError` 只说「amount 字段收到 time
        #    datetime.time(0, 0)」，不说是哪个 stable_field_key ——
        #    18 张表 360 个值的 entry 上这等于无法定位（本仓库已登记过
        #    同族教训：平台报错不点名会把排查带向错误方向）。
        #    这里只补上下文再原样抛出，不改判定语义。
        try:
            equal = values_equal(mine.value, theirs.value, mine.value_type)
        except Exception as exc:  # noqa: BLE001 —— 补上下文后原样抛
            raise type(exc)(
                f"受管字段 {key} 归一化失败（value_type={mine.value_type.value}，"
                f"提交 {mine.value!r} → 反读 {theirs.value!r}）：{exc}"
            ) from exc
        if not equal:
            raise RoundtripEquivalenceError(
                f"受管字段 {key} 反读不等值：提交 {mine.value!r} → 反读 {theirs.value!r}"
                f"（value_type={mine.value_type.value}）—— Property 65 要求 projection "
                "与同 revision representation 等值"
            )


