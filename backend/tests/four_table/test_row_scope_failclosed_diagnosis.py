"""`_row_scope` fail-closed 必须给出**可诊断**原因（Property 40 / Requirement 11.3）。

段边界解析失败时后端跳过该表写入（fail closed，绝不退化成整表覆盖）。原先只把
表名放进 `row_scope_unresolved`、把原因写进日志 ⇒ 审计师界面上只能看到
「这张表没同步成功」，而三种成因的**修法完全不同**：

- `variant_unresolved` → 项目适用准则没填（去项目设置改）
- `template_table_not_found` → 底稿声明的表名与附注模板不一致
- `owner_row_code_not_in_template` → 附注模板缺段首码（跑 `fix_note_*` 幂等脚本）

把三条岔路合成一条死胡同就是「静默」的另一种形式。故本守卫要求原因**随返回值下发**
且逐码有可操作话术。

判据不用「字符串存在」，而是：
1. 从 `_merge_rows_by_scope` 源码里**抽出它真正会返回的错误码**，逐个要求有话术
   ⇒ 将来加第 4 种成因忘了配话术会打红（拦「兜底吞掉新码」）。
2. 真调 `_apply_row_scoped_merge` 走一遍三种成因，断言 reasons 里有对应话术，
   且既有数据逐字未变（fail closed 的另一半）。

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
      Requirements 11.3 / Property 40
"""

from __future__ import annotations

import inspect
import json
import re

import pytest

from app.services.wp_disclosure_sync_service import (
    _ROW_SCOPE_ERROR_FALLBACK,
    _ROW_SCOPE_ERROR_HINTS,
    RowScope,
    _apply_row_scoped_merge,
    _merge_rows_by_scope,
    describe_row_scope_error,
)

#: 一张真实存在的多段共享表（K 循环 Task 14 补码后新增）
_SECTION = "五、42"
_TABLE = "其他应付款"
_OWNER = "BS-050"


def _returned_error_codes() -> set[str]:
    """从 `_merge_rows_by_scope` 源码抽出它会返回的错误码字面量。

    形态是 ``return baseline, "xxx"`` —— 只认这一种，抽不到就打红（见下一条自检）。
    """
    src = inspect.getsource(_merge_rows_by_scope)
    return set(re.findall(r"return\s+baseline\s*,\s*\"([a-z_]+)\"", src))


def test_error_code_extractor_really_found_codes() -> None:
    """反向自检：抽不到码时下一条会「无对象可查」而全绿。"""
    codes = _returned_error_codes()
    assert len(codes) >= 3, f"只抽到 {codes}，抽取器与源码形态脱钩了"
    assert "owner_row_code_not_in_template" in codes


def test_every_returned_error_code_has_actionable_hint() -> None:
    """每个真会返回的错误码都要有话术 —— 拦「加了新码忘配话术」。"""
    missing = sorted(_returned_error_codes() - set(_ROW_SCOPE_ERROR_HINTS))
    assert not missing, (
        f"这些成因没有可操作话术，会落到兜底文案：{missing}\n"
        "兜底只用于「未登记的原因码」，不该成为常态 —— 请在 "
        "_ROW_SCOPE_ERROR_HINTS 里补上「该找谁改什么」。"
    )


def test_hints_are_actionable_not_restatements() -> None:
    """话术必须说「怎么办」，不能只是把错误码翻成中文。"""
    for code, hint in _ROW_SCOPE_ERROR_HINTS.items():
        assert len(hint) >= 20, f"{code} 话术过短，说不清怎么办：{hint!r}"
        assert any(k in hint for k in ("请", "需", "核对", "改")), (
            f"{code} 话术没给动作：{hint!r}"
        )


def test_no_stale_hints() -> None:
    """话术表里不许有源码已不返回的死码（否则读者以为还会发生）。"""
    stale = sorted(set(_ROW_SCOPE_ERROR_HINTS) - _returned_error_codes())
    assert not stale, f"话术表里有源码已不返回的码：{stale}"


def test_describe_includes_table_section_and_owner() -> None:
    """一句话里要能定位到「哪张表的哪一段」，否则多表推送时对不上号。"""
    msg = describe_row_scope_error(
        "owner_row_code_not_in_template",
        section_number=_SECTION,
        table_name=_TABLE,
        scope=RowScope(table_name=_TABLE, owner_row_code=_OWNER),
    )
    assert _TABLE in msg and _SECTION in msg and _OWNER in msg
    assert _ROW_SCOPE_ERROR_HINTS["owner_row_code_not_in_template"] in msg


def test_unknown_code_falls_back_loudly() -> None:
    """未登记的码要有明确兜底文案，不得返回空串（空串 = 静默）。

    🔴 判据用**字面量**而不是 `_ROW_SCOPE_ERROR_FALLBACK` 本身：写
    ``assert _ROW_SCOPE_ERROR_FALLBACK in msg`` 会在常量被改成 ``""`` 时依然通过
    （空串是任何字符串的子串）—— 守卫把错值当基线锁死。变异检验实测过这一条
    （把常量改空得到 GREEN），故改为下面这种「不自我引用」的写法。
    """
    assert len(_ROW_SCOPE_ERROR_FALLBACK) >= 10, (
        f"兜底文案过短/为空（={_ROW_SCOPE_ERROR_FALLBACK!r}）—— 空串等于静默"
    )
    msg = describe_row_scope_error(
        "some_new_failure_mode",
        section_number=_SECTION,
        table_name=_TABLE,
        scope=RowScope(table_name=_TABLE, owner_row_code=_OWNER),
    )
    assert "段边界解析失败" in msg, f"兜底路径没说清发生了什么：{msg!r}"
    assert "日志" in msg, f"兜底路径没告诉读者去哪查：{msg!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 行为面：真跑三种成因
# ─────────────────────────────────────────────────────────────────────────────


def _run(*, variant: str | None, table: str, owner: str) -> tuple[dict, list, dict]:
    prev = [{"label": "应付利息"}, {"label": "其他应付款"}]
    merged = {table: [{"label": "推来的行"}]}
    scoped, unresolved, reasons = _apply_row_scoped_merge(
        merged,
        {table: [{"label": "推来的行"}]},
        {table: RowScope(table_name=table, owner_row_code=owner)},
        variant=variant,
        section_number=_SECTION,
        baselines={table: prev},
    )
    assert scoped == [], "解析失败却仍写入了 —— fail closed 被破坏"
    assert unresolved == [table]
    # fail closed 的另一半：既有数据逐字未变
    assert json.dumps(merged[table], ensure_ascii=False, sort_keys=True) == json.dumps(
        prev, ensure_ascii=False, sort_keys=True
    )
    return merged, unresolved, reasons


@pytest.mark.parametrize(
    ("variant", "table", "owner", "code"),
    [
        (None, _TABLE, _OWNER, "variant_unresolved"),
        ("listed", "这张表在模板里不存在", _OWNER, "template_table_not_found"),
        ("listed", _TABLE, "BS-999", "owner_row_code_not_in_template"),
    ],
)
def test_each_cause_yields_its_own_reason(
    variant: str | None, table: str, owner: str, code: str
) -> None:
    _merged, _unresolved, reasons = _run(variant=variant, table=table, owner=owner)
    assert table in reasons, f"{code} 没给原因 —— 又变成「只知道失败」"
    assert _ROW_SCOPE_ERROR_HINTS[code] in reasons[table], (
        f"{code} 的原因话术不对：{reasons[table]!r}"
    )


def test_reasons_empty_when_everything_resolves() -> None:
    """成功路径不得留下原因（否则前端会误报）。

    用 K 循环 Task 14 补过码的真实共享表 —— 顺带证明那次补码确实生效。
    """
    merged = {_TABLE: [{"label": "推来的行"}]}
    scoped, unresolved, reasons = _apply_row_scoped_merge(
        merged,
        {_TABLE: [{"label": "推来的行"}]},
        {_TABLE: RowScope(table_name=_TABLE, owner_row_code=_OWNER)},
        variant="listed",
        section_number=_SECTION,
        baselines={},
    )
    assert unresolved == [], f"补过码的表仍解析失败：{reasons}"
    assert scoped == [_TABLE]
    assert reasons == {}


def test_reason_keys_are_exactly_the_unresolved_tables() -> None:
    """原因字典的键集合必须**恰好**等于 unresolved 列表（不多不少）。

    多了 = 成功的表也带原因（前端误报）；少了 = 有表失败却说不出原因。
    """
    merged = {_TABLE: [{"label": "x"}], "另一张不存在的表": [{"label": "y"}]}
    scopes = {
        _TABLE: RowScope(table_name=_TABLE, owner_row_code="BS-999"),
        "另一张不存在的表": RowScope(table_name="另一张不存在的表", owner_row_code=_OWNER),
    }
    _scoped, unresolved, reasons = _apply_row_scoped_merge(
        merged,
        dict(merged),
        scopes,
        variant="listed",
        section_number=_SECTION,
        baselines={},
    )
    assert sorted(reasons) == sorted(unresolved) == sorted(scopes)
