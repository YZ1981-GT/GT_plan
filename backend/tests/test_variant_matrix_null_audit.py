"""守卫：`variant_matrix` null 三态裁决（Property 25~27）。

spec: soe-listed-note-conversion-correctness / Requirements 7.1~7.4, Task 13

不连库（读两份模板 JSON + 裁决常量），可进 CI。

核心防护：
1. 裁决表**恰好覆盖**当前 JSON 里的全部 null（多一条/少一条都打红）
2. ``FALSE_NULL`` 的补记落点必须**真实存在于目标模板**（防补一个不存在的章节号）
3. ``TRUE_NULL`` 必须附理由，且目标模板确实找不到（关键词复核）
4. Requirement 7.3 additive：既有非 null 取值快照不变
5. 反向自检：把 ``实收资本`` 从 CROSS_GRAIN 改回 TRUE_NULL 必打红
   （那是首轮误判，`股本` 在 listed 模板真实存在）
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from app.services.note_variant_matrix_null_audit import (
    BLOCKED_BY_SPEC,
    LISTED_NULL_AUDIT,
    SOE_NULL_AUDIT,
    SPEC_NAMED_FALSE_NULLS,
    NullAuditEntry,
    verdict_of,
)

_DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
_MATRIX = _DATA / "note_template_variant_matrix.json"
_LISTED = _DATA / "note_template_listed.json"
_SOE = _DATA / "note_template_soe.json"


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def matrix() -> dict:
    return _load(_MATRIX)


@pytest.fixture(scope="module")
def listed_sections() -> list[dict]:
    return _load(_LISTED).get("sections", [])


@pytest.fixture(scope="module")
def soe_sections() -> list[dict]:
    return _load(_SOE).get("sections", [])


def _null_keys(matrix: dict, variant: str) -> set[str]:
    out: set[str] = set()
    for acc in matrix.get("accounts", []):
        if acc.get("variants", {}).get(variant) is None:
            key = acc.get("account_key")
            if key:
                out.add(key)
    return out


def _section_numbers(sections: list[dict]) -> set[str]:
    return {
        s.get("section_number")
        for s in sections
        if isinstance(s, dict) and s.get("section_number")
    }


def _by_number(sections: list[dict]) -> dict[str, dict]:
    """``section_number`` → 节对象。

    🔴 章节号在同一份模板内**可能重复**（`十二、1` 之类 md 重建残留），
    这里取第一个命中；下面的 `_child_count` 用 `section_id` 精确计子节，
    不依赖章节号唯一。
    """
    out: dict[str, dict] = {}
    for s in sections:
        if not isinstance(s, dict):
            continue
        num = str(s.get("section_number") or "")
        if num and num not in out:
            out[num] = s
    return out


def _child_count(sections: list[dict], section_id: str) -> int:
    """挂在 ``section_id`` 下的直接子节数。"""
    if not section_id:
        return 0
    return sum(
        1
        for s in sections
        if isinstance(s, dict) and str(s.get("parent_section_id") or "") == section_id
    )


# ---------------------------------------------------------------------------
# Property 25：裁决表与 JSON 现状恰好对齐
# ---------------------------------------------------------------------------


class TestAuditCoversAllNulls:
    """Requirement 7.1：25 + 10 条 null 逐条判定，不许有漏判也不许有幽灵条目。

    🔴 裁决表是**历史 null 台账**（立项时 listed 25 / soe 10 条），不是「当前 null 集合」。
    Task 12 把 11 条 FALSE_NULL 补记进 `variants` 后，这些 key 在 JSON 里已非 null ——
    **台账仍须保留它们**：

    - 保留 = 「为什么这 11 个当初是 null、依据什么补记的、落点是哪个」的唯一留证；
      删掉后下个会话看到 `variants` 有值，无从判断是有依据的补记还是被人随手填的。
    - 于是不变量从「表 == 当前 null」翻转为**两条**：
      ① 当前 null 集合 ≡ 表中 **非 FALSE_NULL**（CROSS_GRAIN + TRUE_NULL）的 key
      ② 表中 FALSE_NULL 的 key 在 JSON 里**必须已非 null 且取值 == 声明落点**
      （见 `test_false_null_is_landed_with_declared_target`）

    两条合起来仍是双向锁死：漏补记 / 补错值 / 擅自补 CROSS_GRAIN 都会打红。
    """

    #: 立项时的 null 条目数（历史事实，不随补记变化）。
    HISTORICAL_NULL_COUNT = {"listed": 25, "soe": 10}

    def test_audit_tables_keep_historical_size(self) -> None:
        """台账不许缩短 —— 补记落地后删条目会丢掉补记依据。"""
        for side, table in (("listed", LISTED_NULL_AUDIT), ("soe", SOE_NULL_AUDIT)):
            assert len(table) == self.HISTORICAL_NULL_COUNT[side], (
                f"{side} 侧台账条目数由 {self.HISTORICAL_NULL_COUNT[side]} 变为 {len(table)} "
                "—— 台账是历史 null 的留证，补记落地后**不得删条目**；"
                "若确有新 null 出现（矩阵新增科目），把本常量与理由一并更新"
            )

    def test_listed_audit_matches_json_nulls(self, matrix: dict) -> None:
        actual = _null_keys(matrix, "listed_standalone")
        pending = {e.account_key for e in LISTED_NULL_AUDIT if e.verdict != "FALSE_NULL"}
        assert pending == actual, (
            "listed 侧「仍应为 null」的集合与 JSON 现状不符。\n"
            f"未裁决（JSON 有 null 但表里没有 / 或被判 FALSE_NULL 却没补记）: "
            f"{sorted(actual - pending)}\n"
            f"不该是 null（判 CROSS_GRAIN/TRUE_NULL 却已被填值）: {sorted(pending - actual)}\n"
            "⇒ 前者要补裁决或跑 fix_variant_matrix_false_nulls.py --apply；"
            f"后者说明有人越过裁决填了值（阻塞方: {BLOCKED_BY_SPEC}）"
        )

    def test_soe_audit_matches_json_nulls(self, matrix: dict) -> None:
        actual = _null_keys(matrix, "soe_standalone")
        pending = {e.account_key for e in SOE_NULL_AUDIT if e.verdict != "FALSE_NULL"}
        assert pending == actual, (
            "soe 侧「仍应为 null」的集合与 JSON 现状不符。\n"
            f"未裁决: {sorted(actual - pending)}\n"
            f"不该是 null: {sorted(pending - actual)}"
        )

    @pytest.mark.parametrize(
        "side,entry",
        [("listed", e) for e in LISTED_NULL_AUDIT if e.verdict == "FALSE_NULL"]
        + [("soe", e) for e in SOE_NULL_AUDIT if e.verdict == "FALSE_NULL"],
        ids=lambda x: x if isinstance(x, str) else x.account_key,
    )
    def test_false_null_is_landed_with_declared_target(
        self, side: str, entry: NullAuditEntry, matrix: dict
    ) -> None:
        """Task 12 落地校验：FALSE_NULL 必须已补记，且值**逐字等于**声明落点。

        这是「补记正确性」的核心断言，三种错法都被它挡住：

        - 判了 FALSE_NULL 但没跑 `--apply`（仍是 null）
        - 跑了但落点与裁决表不一致（手改 JSON / 脚本 target 漂移）
        - 单体与合并两变体填了不同值（下游按变体取数会分叉）
        """
        by_key = {a.get("account_key"): a for a in matrix.get("accounts", [])}
        acct = by_key.get(entry.account_key)
        assert acct is not None, f"{entry.account_key} 不在矩阵里"
        variants = acct.get("variants") or {}
        for suffix in ("standalone", "consolidated"):
            vk = f"{side}_{suffix}"
            got = variants.get(vk)
            assert got == entry.target_section, (
                f"{entry.account_key}.{vk} = {got!r}，裁决表声明落点 {entry.target_section!r} "
                "—— 补记未落地或落点漂移。跑 "
                "`python backend/scripts/fix/fix_variant_matrix_false_nulls.py --check` 定位"
            )

    def test_standalone_equals_consolidated(self, matrix: dict) -> None:
        """实证事实：单体/合并两变体取值完全相同（差异 0）。

        一旦 A spec 增了母公司维度使二者分叉，本断言会打红提醒重新裁决 null 集合。
        """
        for acc in matrix.get("accounts", []):
            v = acc.get("variants", {})
            assert v.get("soe_standalone") == v.get("soe_consolidated"), (
                f"{acc.get('account_key')} 的 soe 单体/合并取值已分叉 —— "
                "null 裁决集合须按新维度重算"
            )
            assert v.get("listed_standalone") == v.get("listed_consolidated"), (
                f"{acc.get('account_key')} 的 listed 单体/合并取值已分叉"
            )

    def test_no_duplicate_keys_within_side(self) -> None:
        for name, table in (("listed", LISTED_NULL_AUDIT), ("soe", SOE_NULL_AUDIT)):
            keys = [e.account_key for e in table]
            assert len(keys) == len(set(keys)), f"{name} 侧裁决表有重复 account_key"


# ---------------------------------------------------------------------------
# Property 26：FALSE_NULL 的落点必须真实存在
# ---------------------------------------------------------------------------


class TestFalseNullTargetsExist:
    """Requirement 7.2：补记落点不得是编造的章节号。"""

    @pytest.mark.parametrize(
        "entry",
        [e for e in LISTED_NULL_AUDIT if e.verdict == "FALSE_NULL"],
        ids=lambda e: e.account_key,
    )
    def test_listed_false_null_target_in_listed_template(
        self, entry: NullAuditEntry, listed_sections: list[dict]
    ) -> None:
        assert entry.target_section, f"{entry.account_key} 判 FALSE_NULL 但未给落点"
        assert entry.target_section in _section_numbers(listed_sections), (
            f"{entry.account_key} 的补记落点 {entry.target_section!r} "
            "在 listed 模板中不存在 —— 禁止补一个编造的章节号"
        )

    @pytest.mark.parametrize(
        "entry",
        [e for e in SOE_NULL_AUDIT if e.verdict == "FALSE_NULL"],
        ids=lambda e: e.account_key,
    )
    def test_soe_false_null_target_in_soe_template(
        self, entry: NullAuditEntry, soe_sections: list[dict]
    ) -> None:
        assert entry.target_section, f"{entry.account_key} 判 FALSE_NULL 但未给落点"
        assert entry.target_section in _section_numbers(soe_sections), (
            f"{entry.account_key} 的补记落点 {entry.target_section!r} "
            "在 soe 模板中不存在"
        )

    def test_spec_named_eight_are_all_resolved(self) -> None:
        """Requirement 7.2 点名的 8 个必须已被裁决为「有落点」。"""
        by_key = {e.account_key: e for e in LISTED_NULL_AUDIT}
        for key in sorted(SPEC_NAMED_FALSE_NULLS):
            entry = by_key.get(key)
            assert entry is not None, f"spec 点名的 {key} 不在 listed 裁决表里"
            assert entry.verdict in {"FALSE_NULL", "CROSS_GRAIN"}, (
                f"spec 点名的 {key} 被判 {entry.verdict} —— "
                "实证证明 listed 模板确有落点，不得判 TRUE_NULL"
            )

    # ── Property 38：落点必须是「可作披露落点」的叶子节 ────────────────────
    #
    # 🔴 2026-08-07 变异检验抓出的守卫缺陷：原先只断言「章节号存在于模板」，
    # 于是把 `股份支付` 改回 FALSE_NULL 且落点指向**章标题行**「十二」时守卫全绿。
    # 而「十二」实测 `level=1 / tables=0 / 6 个子节 / text_sections=0` = 容器节，
    # 补它会让 `variant_matrix` 指向一个没有任何披露内容的行，底稿同步取不到表。
    #
    # 判据不是「tables > 0」—— listed 模板有 48 个 `level=2 且 tables=0` 的节
    # （`三、借款费用` / `三、债务重组` 等会计政策章下的**纯文字披露节**，各带
    # 5~15 条 `text_sections`），它们是合法落点且 `五、72` 已被既有 `listed_*`
    # 引用（先例）。真正的分野是**有没有子节**：
    #   - 叶子节（0 子节）⇒ 自己承载内容（表格或文字），合法
    #   - 容器节（有子节）⇒ 内容在子节里，补它等于指向空行
    @pytest.mark.parametrize(
        "side,entry",
        [("listed", e) for e in LISTED_NULL_AUDIT if e.verdict == "FALSE_NULL"]
        + [("soe", e) for e in SOE_NULL_AUDIT if e.verdict == "FALSE_NULL"],
        ids=lambda v: v if isinstance(v, str) else v.account_key,
    )
    def test_false_null_target_is_a_leaf_disclosure_section(
        self,
        side: str,
        entry: NullAuditEntry,
        listed_sections: list[dict],
        soe_sections: list[dict],
    ) -> None:
        sections = listed_sections if side == "listed" else soe_sections
        sec = _by_number(sections).get(str(entry.target_section))
        assert sec is not None, (
            f"{side}/{entry.account_key} 的落点 {entry.target_section!r} 不在模板里"
        )

        kids = _child_count(sections, str(sec.get("section_id") or ""))
        assert kids == 0, (
            f"{side}/{entry.account_key} 的落点 {entry.target_section!r} 有 {kids} 个子节 "
            f"(level={sec.get('level')}, tables={len(sec.get('tables') or [])}) "
            "⇒ 它是**章标题/容器节**不是披露节。补它会让 variant_matrix 指向空行，"
            "底稿同步取不到任何披露表；补某一个子节又会漏掉其余的 "
            "⇒ 应改判 CROSS_GRAIN 并说明「soe 的 N 张表分别对应 listed 哪几个子节」"
        )

        # 叶子节必须真有内容承载（表格 或 文字），否则落点是空壳
        n_tables = len(sec.get("tables") or [])
        n_texts = len(sec.get("text_sections") or [])
        assert n_tables > 0 or n_texts > 0, (
            f"{side}/{entry.account_key} 的落点 {entry.target_section!r} 既无表格也无文字段 "
            "⇒ 空壳节，不能作为补记落点"
        )

    def test_leaf_criterion_is_not_vacuous(
        self, listed_sections: list[dict]
    ) -> None:
        """反向自检：上一条的两个判据都**确有区分力**，不是恒真。

        🔴 只断言「全部落点通过」无法区分「判据有效」与「判据恒真」。
        这里用模板真实数据证明：
        1. 模板里**确实存在**有子节的容器节（否则 `kids == 0` 恒成立）
        2. 模板里**确实存在** `tables=0` 的合法叶子节（否则该判据会被误写成
           `tables > 0`，把 `三、借款费用` 这类纯文字披露节打红）
        """
        containers = [
            s
            for s in listed_sections
            if isinstance(s, dict)
            and _child_count(listed_sections, str(s.get("section_id") or "")) > 0
        ]
        assert containers, "模板里没有任何容器节 ⇒ `kids == 0` 判据恒真，无区分力"

        text_only_leaves = [
            s
            for s in listed_sections
            if isinstance(s, dict)
            and _child_count(listed_sections, str(s.get("section_id") or "")) == 0
            and not (s.get("tables") or [])
            and (s.get("text_sections") or [])
        ]
        assert text_only_leaves, (
            "模板里没有「0 表 + 有文字」的叶子节 ⇒ 无法证明判据不该写成 tables > 0"
        )

    def test_non_false_null_has_no_target(self) -> None:
        """CROSS_GRAIN / TRUE_NULL 不得携带落点（避免被误当已裁决可补记）。"""
        for table in (LISTED_NULL_AUDIT, SOE_NULL_AUDIT):
            for e in table:
                if e.verdict != "FALSE_NULL":
                    assert e.target_section is None, (
                        f"{e.account_key} 判 {e.verdict} 却带落点 {e.target_section!r}"
                    )


# ---------------------------------------------------------------------------
# Property 27：TRUE_NULL 必须附理由且确实找不到
# ---------------------------------------------------------------------------


#: 成因 A：关键词在目标模板**零命中** ⇒ 该科目在目标准则下压根不列报。
#: 逐条的关键词复核依据（与 `_wip_matrix_null_recheck.py` 同源）。
#:
#: 🔴 放在**模块级**而非类属性：类体内的推导式看不见类作用域名字
#: （`NameError: name '_CAUSE_A_KEYS' is not defined`），而 `parametrize`
#: 的参数列表就是在类体里求值的。
TRUE_NULL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ying_shou_zi_jin_ji_zhong_guan_li_kuan": ("资金集中管理款",),
    "you_qi_zi_chan": ("油气",),
    "fei_huo_bi_xing_zi_chan_jiao_huan": ("非货币",),
    "she_ding_shou_yi_ji_hua_jing_zi_chan": ("设定受益计划净资产",),
    "ku_cun_gu": ("库存股",),
    "shui_jin_ji_fu_jia": ("税金及附加",),
    "gu_dong_quan_yi_bian_dong_biao_xiang_mu_zhu": ("股东权益变动表",),
}

#: 成因 B：关键词**有命中**，但唯一命中落在**母公司章**（`scope='consolidated_only'`
#: 且挂在母公司章下）⇒ 合并口径侧仍无独立落点，`variants` 该保持 null，落点由
#: spec A 的 `parent_company_sections` 承载。
#:
#: 🔴 这一态与成因 A 的判据**方向相反**（A 要求零命中、B 要求有命中且全部在母公司章），
#: 故必须分表登记 —— 把 B 混进 `TRUE_NULL_KEYWORDS` 会被「零命中」断言打红，而放宽成
#: 「命中也算通过」则成因 A 的 7 个条目一起失去保护。
#:
#: 值 = `(关键词, 落点 section_number, 母公司章 section_id 前缀)`。
#:
#: 🔴 `section_number` **显式登记**，不从 `reason` 散文里正则抽 —— 首版用
#: `re.search(r"[「『`]([^」』`]+)[」』`]", reason)` 抓到的是理由里**第一个**被引号
#: 括起的词（实测抓到关键词 `现金流量表补充资` 而非完整章节号
#: `十二、现金流量表补充资`）⇒ 断言「模板里找不到该章节号」假红。判据不得依赖
#: 自然语言措辞：理由随时会被改写，而 `section_number` 是可比对的结构化事实。
TRUE_NULL_PARENT_ONLY_LANDING: dict[str, tuple[str, str, str]] = {
    "xian_jin_liu_liang_biao_bu_chong_zi_liao": (
        "现金流量表补充资",
        "十二、现金流量表补充资",
        "chapter-12-mu-gong-si",
    ),
}

_CAUSE_A_KEYS = frozenset(TRUE_NULL_KEYWORDS)
_CAUSE_B_KEYS = frozenset(TRUE_NULL_PARENT_ONLY_LANDING)
_JUSTIFIED_KEYS = _CAUSE_A_KEYS | _CAUSE_B_KEYS

#: 成因 B 的 `(side, account_key)` 参数化清单 —— 从裁决表**真实数据**派生，
#: 不手写字面量：手写会在裁决表改动后静默失配（该条被改判 FALSE_NULL 时，
#: 参数化仍跑成因 B 断言 → 报错文本指向 verdict 断言而非真正原因）。
PARENT_ONLY_TRUE_NULLS: tuple[tuple[str, str], ...] = tuple(
    sorted(
        (side, e.account_key)
        for side, entries in (("listed", LISTED_NULL_AUDIT), ("soe", SOE_NULL_AUDIT))
        for e in entries
        if e.verdict == "TRUE_NULL" and e.account_key in _CAUSE_B_KEYS
    )
)


class TestTrueNullJustified:
    """Requirement 7.4：确无落点的 null 必须附理由，且理由可复核。"""

    KEYWORDS = TRUE_NULL_KEYWORDS
    PARENT_ONLY_LANDING = TRUE_NULL_PARENT_ONLY_LANDING

    @pytest.mark.parametrize(
        "entry",
        [e for e in LISTED_NULL_AUDIT + SOE_NULL_AUDIT if e.verdict == "TRUE_NULL"],
        ids=lambda e: e.account_key,
    )
    def test_reason_is_substantive(self, entry: NullAuditEntry) -> None:
        assert len(entry.reason.strip()) >= 20, (
            f"{entry.account_key} 判 TRUE_NULL 但理由过短 —— Requirement 7.4 要求理由非空"
        )
        assert "关键词" in entry.reason or "零命中" in entry.reason or "无" in entry.reason, (
            f"{entry.account_key} 的理由未说明复核方式"
        )

    def test_every_true_null_has_keyword_evidence(self) -> None:
        true_nulls = {
            e.account_key
            for e in LISTED_NULL_AUDIT + SOE_NULL_AUDIT
            if e.verdict == "TRUE_NULL"
        }
        missing = true_nulls - _JUSTIFIED_KEYS
        assert not missing, (
            f"这些 TRUE_NULL 没有登记复核依据: {sorted(missing)} —— "
            "只做 section_title 精确匹配会误判（实测 8 条）。"
            "两种成因二选一登记：关键词零命中进 KEYWORDS，"
            "命中但落点全在母公司章进 PARENT_ONLY_LANDING"
        )

    def test_two_causes_are_disjoint(self) -> None:
        """两张表不得交叠 —— 同一条只能有一种成因，否则判据自相矛盾。"""
        overlap = set(self.KEYWORDS) & set(self.PARENT_ONLY_LANDING)
        assert not overlap, (
            f"同时登记在两张表里: {sorted(overlap)} —— "
            "成因 A 要求关键词零命中、成因 B 要求有命中，两者不可能同时成立"
        )

    @pytest.mark.parametrize(
        "entry",
        [
            e
            for e in LISTED_NULL_AUDIT
            if e.verdict == "TRUE_NULL" and e.account_key in _CAUSE_A_KEYS
        ],
        ids=lambda e: e.account_key,
    )
    def test_listed_true_null_really_absent(
        self, entry: NullAuditEntry, listed_sections: list[dict]
    ) -> None:
        kws = self.KEYWORDS[entry.account_key]
        titles = [
            str(s.get("section_title", "")) for s in listed_sections if isinstance(s, dict)
        ]
        for kw in kws:
            hits = [t for t in titles if kw in t]
            assert not hits, (
                f"{entry.account_key} 判 TRUE_NULL，但 listed 模板按 {kw!r} 命中 {hits} "
                "⇒ 应改判 FALSE_NULL / CROSS_GRAIN"
            )

    @pytest.mark.parametrize(
        "entry",
        [
            e
            for e in SOE_NULL_AUDIT
            if e.verdict == "TRUE_NULL" and e.account_key in _CAUSE_A_KEYS
        ],
        ids=lambda e: e.account_key,
    )
    def test_soe_true_null_really_absent(
        self, entry: NullAuditEntry, soe_sections: list[dict]
    ) -> None:
        kws = self.KEYWORDS[entry.account_key]
        titles = [
            str(s.get("section_title", "")) for s in soe_sections if isinstance(s, dict)
        ]
        for kw in kws:
            hits = [t for t in titles if kw in t]
            assert not hits, (
                f"{entry.account_key} 判 TRUE_NULL，但 soe 模板按 {kw!r} 命中 {hits}"
            )

    # ── 成因 B 的专属断言（比成因 A 更强：要求落点确实存在且确实在母公司章下） ──
    @pytest.mark.parametrize(
        "side,key",
        sorted((s, k) for (s, k) in PARENT_ONLY_TRUE_NULLS),
        ids=lambda v: v if isinstance(v, str) else str(v),
    )
    def test_parent_only_true_null_target_is_really_parent_scoped(
        self,
        side: str,
        key: str,
        matrix: dict,
        listed_sections: list[dict],
        soe_sections: list[dict],
    ) -> None:
        """成因 B：落点**必须存在**、**必须在母公司章下**、**必须已被 pcs 承载**。

        三条缺一即说明该条不该判 TRUE_NULL：

        1. 落点不存在 ⇒ 理由是编的
        2. 落点不在母公司章下（``scope != 'consolidated_only'`` 或 parent 非母公司章）
           ⇒ 它是合并口径的正常落点，应改判 FALSE_NULL 并补记
        3. 落点未被 ``parent_company_sections`` 承载 ⇒ 该章节当前**完全没有**取数入口，
           判 TRUE_NULL 等于让它永久失落；应先由 A spec 承载再判

        这条同时是与 A spec 的**交叉锁死**：A 若把该章节从 pcs 里删掉，这里立刻打红。
        """
        entry = verdict_of(key, side)
        assert entry is not None and entry.verdict == "TRUE_NULL"

        sections = listed_sections if side == "listed" else soe_sections
        # 🔴 落点从**登记表**取，不从 `reason` 散文里正则抽 ——
        # 理由文本随时会被改写/换标点，正则抽取是脆弱判据（首版写成
        # `re.search(r"[「『`]([^」』`]+)[」』`]", entry.reason)`，实测抓到的是
        # 理由里第一个书名号片段 `现金流量表补充资`**不带章号前缀**，
        # 于是「模板里找不到该章节号」假红）。登记表的值是结构化的，
        # 与 `TRUE_NULL_PARENT_ONLY_LANDING` 单一真源同源。
        keyword, target, parent_slug = TRUE_NULL_PARENT_ONLY_LANDING[key]

        hits = [
            s
            for s in sections
            if isinstance(s, dict) and str(s.get("section_number")) == target
        ]
        assert hits, (
            f"{side}/{key} 的理由声称落点 {target!r}，但模板里找不到该章节号 ⇒ 理由不成立"
        )
        sec = hits[0]
        assert sec.get("scope") == "consolidated_only", (
            f"{side}/{key} 的落点 {target!r} 的 scope={sec.get('scope')!r}，不是母公司章专属 "
            "⇒ 它是合并口径的正常落点，应改判 FALSE_NULL 并补记进 variants"
        )
        parent_sid = str(sec.get("parent_section_id") or "")
        assert parent_slug in parent_sid, (
            f"{side}/{key} 的落点 {target!r} 的 parent_section_id={parent_sid!r} "
            f"不含母公司章 slug {parent_slug!r} ⇒ 成因 B 的前提（落点在母公司章下）不成立"
        )

        # 成因 B 与成因 A 的**判据方向相反**：这里必须证明关键词**确有命中**，
        # 且**全部**命中都落在母公司章下。少了这一条，成因 B 就退化成
        # 「不做任何检查的逃逸阀」—— 任何条目塞进登记表都能免检。
        kw_hits = [
            s
            for s in sections
            if isinstance(s, dict) and keyword in str(s.get("section_title", ""))
        ]
        assert kw_hits, (
            f"{side}/{key} 按关键词 {keyword!r} 在模板里零命中 ⇒ 这是成因 A"
            f"（该科目在该准则下压根不列报），应改登记进 TRUE_NULL_KEYWORDS"
        )
        leaked = [
            str(s.get("section_number"))
            for s in kw_hits
            if s.get("scope") != "consolidated_only"
            or parent_slug not in str(s.get("parent_section_id") or "")
        ]
        assert not leaked, (
            f"{side}/{key} 按关键词 {keyword!r} 命中的章节里，{leaked} 不在母公司章下 "
            "⇒ 合并口径侧其实有落点，应改判 FALSE_NULL 并补记进 variants"
        )

        # 与 A spec 交叉锁死：该章节号必须已被 parent_company_sections 承载
        carried = {
            code
            for a in matrix.get("accounts") or []
            for code in ((a.get("parent_company_sections") or {}).values())
            if isinstance(code, str)
        }
        assert target in carried, (
            f"{side}/{key} 的落点 {target!r} 未被任何科目的 parent_company_sections 承载 "
            "⇒ 该章节当前无取数入口，判 TRUE_NULL 会让它永久失落。"
            "应先由 spec parent-company-note-chapter-and-sourcing 承载后再判。"
        )

    @pytest.mark.parametrize("key", sorted(TRUE_NULL_PARENT_ONLY_LANDING))
    def test_cause_b_parent_slug_is_specific_enough(self, key: str) -> None:
        """成因 B 的 slug 前缀必须**具体到母公司章**，不能是泛前缀。

        🔴 变异检验抓出的守卫缺陷：落点判据写的是 ``parent_slug in parent_sid``
        子串匹配，把登记的 ``chapter-12-mu-gong-si`` 放宽成 ``chapter-``
        后**全部断言仍通过** —— 因为模板里每个章的 slug 都以 ``chapter-`` 开头
        ⇒ 「落点在母公司章下」这条前提退化成「落点在任意章下」= 零信号。

        故对登记值本身设形态约束：必须含母公司标识（``mu-gong-si``）+ 带章号段。
        这样放宽前缀的变异会在这里直接打红，而不是悄悄让主判据失效。
        """
        _kw, _target, parent_slug = TRUE_NULL_PARENT_ONLY_LANDING[key]
        assert "mu-gong-si" in parent_slug, (
            f"{key} 登记的 parent_slug={parent_slug!r} 不含 'mu-gong-si' —— "
            "成因 B 的定义是「落点在母公司章下」，泛前缀（如 'chapter-'）会命中所有章，"
            "让该判据退化成零信号"
        )
        assert re.match(r"^chapter-\d{2}-mu-gong-si", parent_slug), (
            f"{key} 登记的 parent_slug={parent_slug!r} 形态不符 —— "
            "须形如 'chapter-NN-mu-gong-si...'（带两位章号），"
            "否则跨章误配（listed 十六章 / soe 十二章各有母公司章）"
        )

    def test_cause_b_registry_is_not_vacuous(self) -> None:
        """反向自检：成因 B 登记表非空，且其成员确实都是 TRUE_NULL。

        登记表被清空 ⇒ 上面那组断言参数化为空 = 静默零信号（本仓库反复踩过的坑）。
        """
        assert PARENT_ONLY_TRUE_NULLS, (
            "成因 B 登记表为空 ⇒ 其专属断言参数化为空、静默不执行"
        )
        for side, key in PARENT_ONLY_TRUE_NULLS:
            entry = verdict_of(key, side)
            assert entry is not None, f"{side}/{key} 不在裁决表里"
            assert entry.verdict == "TRUE_NULL", (
                f"{side}/{key} 登记为成因 B（母公司章专属）却判 {entry.verdict} —— "
                "两者必须同进同退：改判后须从登记表移除"
            )

    def test_cause_a_and_b_partition_all_true_nulls(self) -> None:
        """两个成因必须**恰好划分**全部 TRUE_NULL（无灰区、无重叠）。

        少一条 ⇒ 该条没有任何「确实找不到」的机器证据；重叠 ⇒ 判据打架。
        """
        true_nulls = {
            (side, e.account_key)
            for side, bucket in (("listed", LISTED_NULL_AUDIT), ("soe", SOE_NULL_AUDIT))
            for e in bucket
            if e.verdict == "TRUE_NULL"
        }
        cause_a = {(s, k) for (s, k) in true_nulls if k in _CAUSE_A_KEYS}
        cause_b = set(PARENT_ONLY_TRUE_NULLS)
        assert not (cause_a & cause_b), f"两成因重叠: {sorted(cause_a & cause_b)}"
        assert cause_a | cause_b == true_nulls, (
            f"未被任何成因覆盖的 TRUE_NULL: {sorted(true_nulls - cause_a - cause_b)}；"
            f"登记了但已不是 TRUE_NULL: {sorted(cause_a | cause_b - true_nulls)}"
        )


# ---------------------------------------------------------------------------
# 反向自检：首轮 8 条误判不得复活
# ---------------------------------------------------------------------------


class TestFirstRoundMisjudgementsPinned:
    """首轮按 section_title 精确匹配把 8 条同语义条目误判成 TRUE_NULL。

    这些条目在目标模板**确有**落点（只是换了叫法），若被改回 TRUE_NULL，
    上面的 `test_*_true_null_really_absent` 会因关键词命中而打红 —— 本组断言
    正面钉死它们当前的裁决，使误判无法静默复活。
    """

    MISJUDGED = {
        # (side, key, 目标模板里真实存在的同语义标题片段)
        ("listed", "shi_shou_zi_ben", "股本"),
        ("listed", "wai_bi_zhe_suan", "外币"),
        ("listed", "fen_bu_xin_xi", "分部"),
        ("listed", "he_bing_xian_jin_liu_liang_biao_xiang_guan", "现金流量表补充资料"),
        ("listed", "yi_nian_nei_dao_qi_de_chang_qi_jie_kuan", "一年内到期"),
        ("listed", "yi_nian_nei_dao_qi_de_ying_fu_zhai_quan", "一年内到期"),
        ("listed", "yi_nian_nei_dao_qi_de_chang_qi_ying_fu_kuan", "一年内到期"),
        ("soe", "gu_ben", "实收资本"),
        ("soe", "qi_ta_zong_he_shou_yi", "其他综合收益"),
    }

    @pytest.mark.parametrize("side,key,_frag", sorted(MISJUDGED))
    def test_not_true_null(self, side: str, key: str, _frag: str) -> None:
        entry = verdict_of(key, side)
        assert entry is not None, f"{side}/{key} 未登记裁决"
        assert entry.verdict != "TRUE_NULL", (
            f"{side}/{key} 被判 TRUE_NULL —— 首轮误判复活。"
            f"目标模板里存在含 {_frag!r} 的同语义章节，属 CROSS_GRAIN/FALSE_NULL"
        )

    @pytest.mark.parametrize("side,key,frag", sorted(MISJUDGED))
    def test_counterpart_really_exists(
        self,
        side: str,
        key: str,
        frag: str,
        listed_sections: list[dict],
        soe_sections: list[dict],
    ) -> None:
        """证明「误判」的判定本身有实证支撑（不是空转）。"""
        sections = listed_sections if side == "listed" else soe_sections
        titles = [
            str(s.get("section_title", "")) for s in sections if isinstance(s, dict)
        ]
        assert any(frag in t for t in titles), (
            f"{side} 模板里找不到含 {frag!r} 的章节 —— 那么 {key} 判 CROSS_GRAIN 无依据，"
            "本组自检失去意义"
        )

    def test_two_sided_naming_swap_is_registered(self) -> None:
        """`实收资本`↔`股本` 是两版用语互换，两侧都必须登记为非 TRUE_NULL。

        只修一侧会让补记时两条互指（listed 指 soe 的名、soe 指 listed 的名）。
        """
        a = verdict_of("shi_shou_zi_ben", "listed")
        b = verdict_of("gu_ben", "soe")
        assert a is not None and b is not None
        assert a.verdict == b.verdict == "CROSS_GRAIN", (
            "用语互换的两条必须同为 CROSS_GRAIN，避免只补一侧造成互指"
        )


# ---------------------------------------------------------------------------
# Requirement 7.3：additive —— 既有非 null 取值快照
# ---------------------------------------------------------------------------


class TestNonNullValuesUnchanged:
    """补记必须是 additive：既有非 null 取值逐字不变。"""

    def test_non_null_count_snapshot(self, matrix: dict) -> None:
        """102 科目 × 4 变体的非 null 计数快照。

        补记 FALSE_NULL 会让计数**增加**（允许），但既有值不得被改动 —— 由下一条断言。
        """
        accounts = matrix.get("accounts", [])
        assert len(accounts) == 102, (
            f"variant_matrix 科目数由 102 变为 {len(accounts)} —— "
            "本 spec 不新增科目；若是 A spec 增了母公司维度，须复核 null 裁决集合"
        )

    def test_audited_keys_exist_and_match_verdict(self, matrix: dict) -> None:
        """裁决表里的每条都要在 JSON 里存在，且**当前取值与裁决相符**。

        🔴 2026-08-07 语义随 Task 12 落地改写。原断言是「裁决表里的每条当前必为
        null」—— 那只在补记**之前**成立；补记后 11 条 FALSE_NULL 全部打红，把
        「工作已完成」误报成「表与数据脱节」。

        新判据按 verdict 分流（比原来更强，两个方向都盯）：

        - ``FALSE_NULL`` ⇒ 当前必**非** null，且取值 == ``target_section``
          （既验证补记已落地，又验证落地的是裁决过的那个章节号，不是别的值）
        - ``CROSS_GRAIN`` / ``TRUE_NULL`` ⇒ 当前必**仍为** null
          （这两态的结论就是「不补」，一旦有值说明有人绕过裁决直接填）
        """
        by_key = {a.get("account_key"): a for a in matrix.get("accounts", [])}
        bad: list[str] = []
        for side, table in (("listed", LISTED_NULL_AUDIT), ("soe", SOE_NULL_AUDIT)):
            for e in table:
                acc = by_key.get(e.account_key)
                assert acc is not None, f"{side}/{e.account_key} 在 variant_matrix 中不存在"
                variants = acc.get("variants") or {}
                for suffix in ("standalone", "consolidated"):
                    vk = f"{side}_{suffix}"
                    cur = variants.get(vk)
                    if e.verdict == "FALSE_NULL":
                        if cur != e.target_section:
                            bad.append(
                                f"{vk}/{e.account_key}: 判 FALSE_NULL 落点 "
                                f"{e.target_section!r}，但 JSON 里是 {cur!r} ⇒ "
                                "补记未落地或落成了别的值（跑 "
                                "backend/scripts/fix/fix_variant_matrix_false_nulls.py --check）"
                            )
                    elif cur is not None:
                        bad.append(
                            f"{vk}/{e.account_key}: 判 {e.verdict}（结论是「不补」）"
                            f"，但 JSON 里已有值 {cur!r} ⇒ 有人绕过裁决直接填"
                        )
        assert not bad, "裁决与 JSON 现状不符:\n" + "\n".join(bad[:12])


# ---------------------------------------------------------------------------
# 补记动作的阻塞登记
# ---------------------------------------------------------------------------


class TestBlockingRegistered:
    """补记要改 `variant_matrix`，与 A spec 的 Task 10 撞车 —— 阻塞方须显式登记。"""

    def test_blocked_by_is_the_parent_company_spec(self) -> None:
        assert BLOCKED_BY_SPEC == "parent-company-note-chapter-and-sourcing", (
            "阻塞方登记错误 —— A spec 的 Task 10 也要改 variant_matrix，"
            "且其 Requirement 10.4 要求「其余 100 个非母公司科目取值不变」"
        )

    def test_verdict_lookup_never_guesses(self) -> None:
        assert verdict_of("nonexistent_key_xyz", "listed") is None
        assert verdict_of("shi_shou_zi_ben", "bogus_side") is None
