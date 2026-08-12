"""E1 受限制货币资金分类真源守卫。

**Validates: Requirements 11.2, 11.3, 11.4, 11.11**

Properties: 10（宁缺勿造）、15（顺序即优先级）

spec: .kiro/specs/e1-four-table-extraction-and-disclosure-alignment/ (Task 3.5)
"""
from __future__ import annotations

import dataclasses

import pytest

import re
from pathlib import Path

from app.services.four_table.e1_restricted_buckets import (
    E1_RESTRICTED_BUCKET_BY_KEY,
    E1_RESTRICTED_BUCKETS,
    E1_RESTRICTED_DOCX_ROW_ORDER,
    UNRESTRICTED,
    E1RestrictedBucket,
    bucket_defs_payload,
    classify_e1_restricted_leaf,
    display_order_of,
)

_REPO = Path(__file__).resolve().parents[3]
_FRONTEND = _REPO / "audit-platform" / "frontend" / "src"

# ── 源 xlsx「附注披露信息(国企)」R17~R21 的五个类别（逐字）──────────────────
#: 与 backend/wp_templates/E/E1-1至E1-11 …xlsx 的披露 sheet 逐字一致；
#: openpyxl 交叉比对由 test_note_e1_structure.py 负责，此处锁标签字面。
SOURCE_TEMPLATE_LABELS = {
    "bank_acceptance": "银行承兑汇票保证金",
    "letter_of_credit": "信用证保证金",
    "performance": "履约保证金",
    "pledged_deposit": "用于担保的定期存款或通知存款",
    "overseas": "放在境外且资金汇回受到限制的款项",
}

#: 活体实证叶子名（项目 df5b8403 的货币资金叶子）—— 必须**全部**不归类。
#: 叶子名是银行户名/支付渠道名，不含受限关键字，这是设计如此而非缺陷。
LIVE_LEAF_NAMES = (
    "金华招行基本户801",
    "金华结构性存款账户",
    "金华支付宝",
    "金华微信小程序",
    "聚合收款",
    "AFO",
    "小桔有车",
    "北京基本户202",
    "北京资本金户401",
    "北京三井住友801",
    "金华招行资本金户403",
    "西安聚合收款",
)


class TestBucketDefinitions:
    def test_labels_match_source_template(self):
        """五个命名桶的 label 必须与源模板逐字一致（反向自检：桶清单非空）。"""
        assert len(E1_RESTRICTED_BUCKETS) >= 6
        for key, label in SOURCE_TEMPLATE_LABELS.items():
            assert key in E1_RESTRICTED_BUCKET_BY_KEY, f"缺桶 {key}"
            assert E1_RESTRICTED_BUCKET_BY_KEY[key].label == label

    def test_five_named_buckets_carry_source_ref(self):
        """源模板行必须带 source_ref（供 openpyxl 守卫反查）；兜底桶为 None。"""
        for key in SOURCE_TEMPLATE_LABELS:
            assert E1_RESTRICTED_BUCKET_BY_KEY[key].source_ref, f"{key} 缺 source_ref"
        assert E1_RESTRICTED_BUCKET_BY_KEY["other"].source_ref is None

    def test_keys_unique_and_stable(self):
        keys = [b.key for b in E1_RESTRICTED_BUCKETS]
        assert len(keys) == len(set(keys))
        # UNRESTRICTED 是哨兵值，不能与任何桶 key 相同
        assert UNRESTRICTED not in keys

    def test_bucket_defs_payload_is_single_source_of_labels(self):
        """下发前端的 payload 即中文标签唯一来源。"""
        payload = bucket_defs_payload()
        assert [p["key"] for p in payload] == [b.key for b in E1_RESTRICTED_BUCKETS]
        assert [p["label"] for p in payload] == [b.label for b in E1_RESTRICTED_BUCKETS]
        assert payload[-1]["isPlatformExtra"] is True


class TestProperty10NeverInvent:
    """Property 10：未命中一律返 None（宁缺勿造）。"""

    @pytest.mark.parametrize("name", LIVE_LEAF_NAMES)
    def test_live_leaf_names_are_never_classified(self, name):
        assert classify_e1_restricted_leaf(name) is None, (
            f"{name!r} 被归类了 —— 活体叶子名是银行户名/支付渠道名，"
            "臆造归属会把正常资金说成受限资金"
        )

    @pytest.mark.parametrize("name", ["", "   ", None])
    def test_blank_name_returns_none(self, name):
        assert classify_e1_restricted_leaf(name) is None

    def test_plain_overseas_account_is_not_restricted(self):
        """🔴 光是境外 ≠ 受限：香港子公司基本户不得被判成「汇回受限」。"""
        assert classify_e1_restricted_leaf("香港基本户") is None
        assert classify_e1_restricted_leaf("境外基本户") is None
        assert classify_e1_restricted_leaf("海外一般户") is None

    def test_structured_deposit_excluded_from_pledged(self):
        """结构性存款不等于质押受限（exclude_keywords 生效）。"""
        assert classify_e1_restricted_leaf("结构性存款") is None
        assert classify_e1_restricted_leaf("金华结构性存款账户") is None


class TestProperty15OrderIsPriority:
    """Property 15：声明顺序即优先级。"""

    @pytest.mark.parametrize(
        "name,expected",
        [
            # 三者名称都含「保证金」→ 必须命中各自专属桶而非兜底桶
            ("信用证保证金", "letter_of_credit"),
            ("银行承兑汇票保证金", "bank_acceptance"),
            ("履约保证金", "performance"),
            # 「境外」优先于「冻结」（上市规则要求境外汇回受限单独披露）
            ("境外冻结存款", "overseas"),
            ("境外资金汇回受限账户", "overseas"),
            # 无境外时才落质押桶
            ("冻结存款", "pledged_deposit"),
            ("质押定期存款", "pledged_deposit"),
            ("用于担保的通知存款", "pledged_deposit"),
            # 兜底桶：确属受限但非五个命名类别
            ("投标保证金", "other"),
            ("专项监管专户", "other"),
        ],
    )
    def test_classification(self, name, expected):
        assert classify_e1_restricted_leaf(name) == expected

    def test_reverse_selfcheck_shuffled_order_breaks_letter_of_credit(self, monkeypatch):
        """反向自检：把兜底桶提到最前，「信用证保证金」会被它的『保证金』吃掉。

        证明「顺序即优先级」不是空话，也证明上面的断言不是恒真。
        """
        import app.services.four_table.e1_restricted_buckets as mod

        shuffled = (
            E1_RESTRICTED_BUCKET_BY_KEY["other"],
            *[b for b in E1_RESTRICTED_BUCKETS if b.key != "other"],
        )
        monkeypatch.setattr(mod, "E1_RESTRICTED_BUCKETS", shuffled)
        assert mod.classify_e1_restricted_leaf("信用证保证金") == "other"

    def test_reverse_selfcheck_overseas_after_pledged_breaks(self, monkeypatch):
        """反向自检：境外桶排到质押桶之后，`境外冻结存款` 会被质押桶抢走。"""
        import app.services.four_table.e1_restricted_buckets as mod

        reordered = tuple(
            sorted(
                E1_RESTRICTED_BUCKETS,
                key=lambda b: 0 if b.key == "pledged_deposit" else 1,
            )
        )
        monkeypatch.setattr(mod, "E1_RESTRICTED_BUCKETS", reordered)
        assert mod.classify_e1_restricted_leaf("境外冻结存款") == "pledged_deposit"

    def test_require_any_of_is_actually_used(self):
        """反向自检：确有桶声明了 require_any_of（否则该分支是死代码）。"""
        with_req = [b for b in E1_RESTRICTED_BUCKETS if b.require_any_of]
        assert with_req, "没有任何桶使用 require_any_of，共现分支成了死代码"
        assert {b.key for b in with_req} == {"overseas"}


class TestProperty21NewBucketDoesNotStealClassification:
    """Property 21：新增第 6 桶 `statutory_reserve` 不抢夺既有分类。

    **Validates: Requirements 6.3, 11.5**

    真实库实证（`_wip_e_t13probe.py`，2026-08-09）：212 个去重货币资金叶子科目名里
    **无一含**本桶关键词 ⇒ 新增前后分类结果逐条相同（差异 0 条）。此处用「剔除新桶后
    复现旧口径」的方式把该不变量固化，不依赖连库。
    """

    NEW_KEY = "statutory_reserve"

    #: 真实库 212 个叶子名的代表样本（LIVE_LEAF_NAMES 已覆盖）+ 五类命名样本
    REGRESSION_NAMES = (
        *LIVE_LEAF_NAMES,
        "信用证保证金",
        "银行承兑汇票保证金",
        "履约保证金",
        "境外冻结存款",
        "冻结存款",
        "质押定期存款",
        "投标保证金",
        "专项监管专户",
        "结构性存款",
    )

    @staticmethod
    def _classify_without_new(name: str) -> str | None:
        """复现「未加新桶」的口径（同一算法，序列里剔除新桶）。"""
        text = (name or "").strip()
        if not text:
            return None
        for b in E1_RESTRICTED_BUCKETS:
            if b.key == TestProperty21NewBucketDoesNotStealClassification.NEW_KEY:
                continue
            if any(kw in text for kw in b.exclude_keywords):
                continue
            if not any(kw in text for kw in b.keywords):
                continue
            if b.require_any_of and not any(kw in text for kw in b.require_any_of):
                continue
            return b.key
        return None

    def test_new_bucket_exists(self):
        assert self.NEW_KEY in E1_RESTRICTED_BUCKET_BY_KEY, (
            "缺第 6 桶 `statutory_reserve` —— 源 docx 有「金融企业法定存款准备金或备付金」"
            "（附注行集真源是 docx 不是底稿 xlsx，R6.1）"
        )
        assert (
            E1_RESTRICTED_BUCKET_BY_KEY[self.NEW_KEY].label
            == "金融企业法定存款准备金或备付金"
        )

    @pytest.mark.parametrize("name", REGRESSION_NAMES)
    def test_classification_unchanged_by_new_bucket(self, name):
        assert classify_e1_restricted_leaf(name) == self._classify_without_new(name), (
            f"{name!r} 的分类被新桶改变了 —— 新桶必须只承接自己的关键词"
        )

    @pytest.mark.parametrize(
        "name", ["法定存款准备金", "存放中央银行法定准备金专户", "备付金存款", "存款准备金"]
    )
    def test_new_bucket_captures_its_own_names(self, name):
        assert classify_e1_restricted_leaf(name) == self.NEW_KEY, (
            f"{name!r} 未归入新桶 —— 关键词覆盖不足"
        )

    def test_declared_before_fallback_bucket(self):
        """🔴 必须声明在兜底桶 `other` 之前 —— `other` 的「专户/监管」会抢走它。"""
        keys = [b.key for b in E1_RESTRICTED_BUCKETS]
        assert keys.index(self.NEW_KEY) < keys.index("other")

    def test_reverse_selfcheck_new_bucket_after_other_breaks(self, monkeypatch):
        """反向自检：把新桶挪到 `other` 之后，含「专户」的准备金科目会被兜底桶吃掉。"""
        import app.services.four_table.e1_restricted_buckets as mod

        reordered = tuple(
            [b for b in E1_RESTRICTED_BUCKETS if b.key != self.NEW_KEY]
            + [E1_RESTRICTED_BUCKET_BY_KEY[self.NEW_KEY]]
        )
        monkeypatch.setattr(mod, "E1_RESTRICTED_BUCKETS", reordered)
        assert mod.classify_e1_restricted_leaf("存放中央银行法定准备金专户") == "other"


class TestProperty36DisplayOrderSeparatedFromPriority:
    """Property 36：受限桶**展示序**与**优先级序**双向锁死（两个语义已分离）。

    **Validates: Requirements 6.7, 6.8, 6.9**

    一份声明序此前同时承担两个语义 —— 声明序被「包含关系必须先声明」绑住
    （`信用证保证金` 含「保证金」须先于兜底桶；`境外冻结存款` 同含「冻结」与「境外」
    须境外优先），而附注行序由源 docx 决定，两者 **1↔2、4↔5 互换**。
    前端推送排序原用桶数组下标 ⇒ 附注行序与 docx 不符（既存缺陷）。

    🔴 **与 design.md 初稿的偏离（已在 tasks.md Notes 登记）**：初稿写「按 `source_ref`
    的单元格行号升序派生 `displayOrder`」，而第 6 桶的真源是 **docx**（`r6`）不是
    xlsx（`A17~A21`），两套行号不在同一坐标系、混排会把它排到最前。故展示序真源改为
    显式元组 `E1_RESTRICTED_DOCX_ROW_ORDER`，并**保留**初稿的洞察作交叉锁：
    五个 xlsx 源桶的元组顺序必须与其 `source_ref` 行号升序一致。
    """

    def test_display_order_matches_docx_six_categories(self):
        """展示序 == 源 docx 六类行序（冻结基线，与 test_note_e1_structure 的 DOCX_SIX 同源）。"""
        want = [
            "银行承兑汇票保证金",
            "信用证保证金",
            "履约保证金",
            "用于担保的定期存款或通知存款",
            "放在境外且资金汇回受到限制的款项",
            "金融企业法定存款准备金或备付金",
        ]
        got = [E1_RESTRICTED_BUCKET_BY_KEY[k].label for k in E1_RESTRICTED_DOCX_ROW_ORDER]
        assert got == want, f"展示序与 docx 六类不符：{got}"

    def test_display_order_differs_from_declaration_order(self):
        """🔴 两序必须**不同** —— 相同即说明有人「顺手统一」了，缺陷会复发。"""
        declared = [b.key for b in E1_RESTRICTED_BUCKETS if b.source_ref]
        assert list(E1_RESTRICTED_DOCX_ROW_ORDER) != declared, (
            "展示序与声明序一致了 —— 若确有意统一，需先解掉「包含关系必须先声明」"
            "这条硬约束并重写 Property 15 的反向自检"
        )

    def test_docx_order_covers_exactly_the_source_buckets(self):
        """元组必须恰好覆盖全部「有 source_ref」的桶（无遗漏无多余）。"""
        source_keys = {b.key for b in E1_RESTRICTED_BUCKETS if b.source_ref}
        assert set(E1_RESTRICTED_DOCX_ROW_ORDER) == source_keys, (
            f"展示序元组与源类桶集合不符：{set(E1_RESTRICTED_DOCX_ROW_ORDER) ^ source_keys}"
        )
        assert len(set(E1_RESTRICTED_DOCX_ROW_ORDER)) == len(E1_RESTRICTED_DOCX_ROW_ORDER)

    def test_platform_extra_buckets_sort_last(self):
        """平台补充桶（`source_ref=None`）一律排最后，且彼此序号不相同（排序稳定）。"""
        extras = [b.key for b in E1_RESTRICTED_BUCKETS if b.source_ref is None]
        assert extras, "未找到平台补充桶 —— 桶定义结构变了？"
        max_source = max(display_order_of(k) for k in E1_RESTRICTED_DOCX_ROW_ORDER)
        orders = [display_order_of(k) for k in extras]
        assert all(o > max_source for o in orders), f"平台补充桶未排最后：{orders}"
        assert len(set(orders)) == len(orders), "平台补充桶序号重复 ⇒ 排序不稳定"

    def test_xlsx_source_refs_agree_with_docx_order(self):
        """交叉锁：五个 xlsx 源桶的元组顺序 == 其 `source_ref` 单元格行号升序。

        这是 design.md 初稿提出的机制，作为**交叉验证**保留 —— 两个独立口径互证，
        任一侧被改动都会打红。第 6 桶不参与（它的真源是 docx，无 xlsx 行号）。
        """
        pairs: list[tuple[int, str]] = []
        for key in E1_RESTRICTED_DOCX_ROW_ORDER:
            ref = E1_RESTRICTED_BUCKET_BY_KEY[key].source_ref or ""
            m = re.search(r"!A(\d+)$", ref)
            if m:
                pairs.append((int(m.group(1)), key))
        assert len(pairs) == 5, f"xlsx 源桶应 5 个（A17~A21），实为 {len(pairs)}：{pairs}"
        by_row = [k for _, k in sorted(pairs)]
        by_tuple = [k for k in E1_RESTRICTED_DOCX_ROW_ORDER if k in dict(map(reversed, pairs))]
        assert by_row == by_tuple, (
            f"展示序与 source_ref 行号升序不一致：按行号={by_row} / 按元组={by_tuple}"
        )

    def test_payload_carries_display_order(self):
        """payload 数组顺序仍是声明序（优先级），展示序另由 `displayOrder` 承载。"""
        payload = bucket_defs_payload()
        assert [p["key"] for p in payload] == [b.key for b in E1_RESTRICTED_BUCKETS]
        assert all("displayOrder" in p for p in payload)
        by_display = [p["key"] for p in sorted(payload, key=lambda p: p["displayOrder"])]
        assert by_display[: len(E1_RESTRICTED_DOCX_ROW_ORDER)] == list(
            E1_RESTRICTED_DOCX_ROW_ORDER
        )

    def test_shuffled_declaration_breaks_classification_not_display_order(self, monkeypatch):
        """双向锁死①：打乱声明序 → 分类结果变、`displayOrder` 序列不变。"""
        import app.services.four_table.e1_restricted_buckets as mod

        before = [display_order_of(k) for k in E1_RESTRICTED_DOCX_ROW_ORDER]
        shuffled = (
            E1_RESTRICTED_BUCKET_BY_KEY["other"],
            *[b for b in E1_RESTRICTED_BUCKETS if b.key != "other"],
        )
        monkeypatch.setattr(mod, "E1_RESTRICTED_BUCKETS", shuffled)
        assert mod.classify_e1_restricted_leaf("信用证保证金") == "other"  # 分类变了
        after = [mod.display_order_of(k) for k in E1_RESTRICTED_DOCX_ROW_ORDER]
        assert after == before, "打乱声明序把展示序也带歪了 ⇒ 两序未分离"

    def test_reordered_display_source_breaks_display_order_not_classification(
        self, monkeypatch
    ):
        """双向锁死②：改展示序真源 → `displayOrder` 变、分类结果不变。"""
        import app.services.four_table.e1_restricted_buckets as mod

        cls_before = classify_e1_restricted_leaf("信用证保证金")
        swapped = (
            "letter_of_credit",
            "bank_acceptance",
            *E1_RESTRICTED_DOCX_ROW_ORDER[2:],
        )
        monkeypatch.setattr(mod, "E1_RESTRICTED_DOCX_ROW_ORDER", swapped)
        assert mod.display_order_of("letter_of_credit") == 0  # 展示序变了
        assert mod.display_order_of("bank_acceptance") == 1
        assert classify_e1_restricted_leaf("信用证保证金") == cls_before, (
            "改展示序把分类也带歪了 ⇒ 两序未分离"
        )


def _strip_ts_comments(src: str) -> str:
    """剥 TS/Vue 注释（`//` / `/* */` / `<!-- -->`），**保留字符串字面量**。

    🔴 字符状态机而非正则 —— 正则剥块注释会被 `accept="image/*"` 里的 `/*` 骗
    （memory 已记该坑），也会把 URL 的 `//` 当行注释。
    """
    out: list[str] = []
    i, n = 0, len(src)
    quote: str | None = None
    while i < n:
        ch = src[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if src.startswith("<!--", i):
            j = src.find("-->", i + 4)
            i = n if j < 0 else j + 3
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _standalone_literals(src: str) -> set[str]:
    """抽出全部**独立字符串字面量**（`'x'` / `"x"` / `` `x` ``，内容不含引号与换行）。"""
        # 「抄一份桶标签」的形态一定是独立字面量；源模板提示句里出现同样文字属正当引用
    found: set[str] = set()
    for m in re.finditer(r"'([^'\n]*)'|\"([^\"\n]*)\"|`([^`\n]*)`", src):
        for g in m.groups():
            if g is not None:
                found.add(g.strip())
    return found


class TestProperty22LabelsAreSingleSource:
    """Property 22：桶中文标签单一真源 —— 前端不得把桶标签抄成字面量。

    **Validates: Requirements 11.5**

    🔴 判据是「标签**作为独立字符串字面量**出现」而非「文件里出现该文字」：
    实测三处命中全是正当引用 —— 两处在注释里（`e1RestrictedScope.ts` 的 JSDoc、
    `E1TabDisclosure.vue` 的实现说明），一处是**源模板红字提示原文**
    （琥珀提示句「…不存在抵押、质押或冻结以及存放在境外且资金汇回受到限制的款项。」
    整句引自源 xlsx，其中恰好含某个桶标签的文字）。按「文件里出现即打红」会逼人
    删掉源模板原文与解释性注释 = 判据过宽制造无谓 churn。
    """

    #: 扫描面：E1 受限相关前端源码（排除 `__tests__`）
    SCAN_GLOBS = (
        "components/workpaper/composables/e1RestrictedScope.ts",
        "components/workpaper/composables/e1NoteSectionMap.ts",
        "components/workpaper/e1/E1TabDisclosure.vue",
    )

    def test_scan_face_is_not_empty(self):
        """反向自检：扫描面文件必须存在（否则整条断言空转）。"""
        missing = [g for g in self.SCAN_GLOBS if not (_FRONTEND / g).exists()]
        assert missing == [], f"扫描面文件缺失：{missing}"

    def test_stripper_selfcheck(self):
        """反向自检：剥注释器不误伤字符串字面量、不被 `image/*` 骗。"""
        src = (
            "const a = '保留我'\n"
            "// 注释里的 '删掉我'\n"
            "/* 块注释 '也删掉我' */\n"
            'const b = "accept=image/*"\n'
            "<!-- 模板注释 '删掉我2' -->\n"
        )
        stripped = _strip_ts_comments(src)
        lits = _standalone_literals(stripped)
        assert "保留我" in lits
        assert "accept=image/*" in lits, "块注释正则误伤了含 `/*` 的字符串"
        assert "删掉我" not in lits and "也删掉我" not in lits and "删掉我2" not in lits

    def test_offender_form_would_be_caught(self):
        """反向自检：真 offender（把标签抄成独立字面量）必被抓到。"""
        label = E1_RESTRICTED_BUCKETS[0].label
        fake = f"const LABELS = ['{label}']\n"
        assert label in _standalone_literals(_strip_ts_comments(fake))

    @pytest.mark.parametrize("rel", SCAN_GLOBS)
    def test_no_bucket_label_literal_in_frontend(self, rel):
        src = _strip_ts_comments((_FRONTEND / rel).read_text(encoding="utf-8"))
        lits = _standalone_literals(src)
        hits = [b.label for b in E1_RESTRICTED_BUCKETS if b.label in lits]
        assert hits == [], (
            f"{rel} 把受限桶中文标签抄成了字面量 {hits} —— 标签只许从 `bucketDefs` 取"
            "（后端 `bucket_defs_payload()` 是唯一真源），抄一份必漂移"
        )


class TestBucketDataclassContract:
    def test_frozen_dataclass(self):
        b = E1_RESTRICTED_BUCKETS[0]
        assert dataclasses.is_dataclass(b)
        with pytest.raises(dataclasses.FrozenInstanceError):
            b.label = "改不了"  # type: ignore[misc]

    def test_custom_bucket_can_be_constructed_without_optional_fields(self):
        """自定义类别（审计师新建）只需 key/label/keywords。"""
        b = E1RestrictedBucket(key="custom_x", label="某自定义类别", keywords=("某某",))
        assert b.exclude_keywords == ()
        assert b.require_any_of == ()
        assert b.source_ref is None
