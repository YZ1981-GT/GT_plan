# -*- coding: utf-8 -*-
"""契约受管字段名 ↔ 前端字段名对拍守卫（spec oo-writeback-template-parity-closure R3.2，design §4）。

契约受管字段的 json 键（含行表的行身份键）必须是前端处理该 store item 的代码真的在读写的键 —— 否则 OO 侧
改的值写进前端从不读的键、HTML 侧的值投影不到 OO（字段名对不上，两边各说各话，单测各自全绿）。

现算口径见 `contract_field_names_scan.py`（① 前端全无 / ② 前端有、但不在处理该 store item 的代码里）。
例外登记 `data/contract_field_names_frontend_exceptions.json`：按「契约 | store item」分组、每组写理由，**只许减少**：

1. 现算对不上、却没登记 ⇒ 红（新契约 / 新改名又把字段接错了）；
2. 登记了、现算已对得上 ⇒ 红（接通了，删掉登记并改小基线）；
3. 登记条数等于基线；每组理由非空、不是占位。

判据自检：同一套现算对构造的语料逐类报得出来（防扫描器失效成恒绿）；已接通的表（D5-2）一个都不报。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.workpaper_sync import contract_field_names_scan as S

REGISTRY = Path(__file__).resolve().parent / "data" / "contract_field_names_frontend_exceptions.json"

#: 登记的组数 / 字段名数（只许减少：接通一组删一组并改小这里；新增要在评审里说明为什么不改契约或前端）
BASELINE_GROUPS = 28
BASELINE_NAMES = 337


@pytest.fixture(scope="module")
def corpus() -> S.Corpus:
    return S.load_corpus()


@pytest.fixture(scope="module")
def misses(corpus: S.Corpus) -> dict[str, set[str]]:
    return S.compute_misses(corpus)


@pytest.fixture(scope="module")
def registry() -> dict[str, dict]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_every_mismatch_is_registered(misses: dict[str, set[str]], registry: dict[str, dict]) -> None:
    """现算对不上的字段名都在登记里（没登记的就是新接错的）。"""
    new = {k: sorted(v - set(registry.get(k, {}).get("fields", []))) for k, v in misses.items()}
    new = {k: v for k, v in new.items() if v}
    assert new == {}, (
        "这些契约受管字段名在前端处理该 store item 的代码里找不到：改契约 json 键对齐前端（或前端补列）；"
        f"确实暂不能对齐的写理由登记并改基线：{json.dumps(new, ensure_ascii=False, indent=1)}"
    )


def test_registry_has_no_stale_entries(misses: dict[str, set[str]], registry: dict[str, dict]) -> None:
    """登记了、现算已对得上的字段名必须删掉（接通了却不删 ⇒ 登记表永远不会变短）。"""
    stale = {k: sorted(set(v["fields"]) - misses.get(k, set())) for k, v in registry.items()}
    stale = {k: v for k, v in stale.items() if v}
    assert stale == {}, f"这些登记已接通，请删掉并同步改小基线：{json.dumps(stale, ensure_ascii=False, indent=1)}"


def test_registry_only_shrinks_and_every_group_has_a_reason(registry: dict[str, dict]) -> None:
    total = sum(len(v["fields"]) for v in registry.values())
    assert (len(registry), total) == (BASELINE_GROUPS, BASELINE_NAMES), (
        "登记组数 / 字段名数与基线不等：删了条目请同步改小 BASELINE_GROUPS / BASELINE_NAMES；不许新增"
    )
    weak = [k for k, v in registry.items() if len(str(v.get("reason", "")).strip()) < 8]
    assert weak == []
    assert all(v["fields"] == sorted(set(v["fields"])) for v in registry.values()), "字段名须去重排序（diff 才看得清）"


def test_extra_scope_entries_exist(corpus: S.Corpus) -> None:
    """手工登记的入口文件都还在（文件挪了 / 删了，登记就成了静默放行）。"""
    gone = {item: [f for f in files if f not in corpus.texts] for item, files in S.EXTRA_SCOPE.items()}
    assert {k: v for k, v in gone.items() if v} == {}


def test_wired_table_reports_nothing(misses: dict[str, set[str]]) -> None:
    """正面对照：字段名已对齐的表（D5-2 / D3-4 / F3-4 / E1-4，批 B 起 D3-5 / F4-2 / G6-5 / D3-7 / D7-7 / D6-5，
    批 D 起 L4-3）一个都不报 —— 现算不是「什么都报」。"""
    for key in ("d5.receivables_financing_detail|D5-2-rows", "d3.prepaid_receipts_detail|D3-ana-credit-rows",
                "f3.notes_payable_detail|F3-4-rows", "e1.monetary_fund_detail|E1-digital-rows",
                "d3.prepaid_receipts_detail|D3-lt-rows", "f4.accounts_payable_detail|F4-2-rows",
                "g6.other_bond_main|G6-5-fair-value-data", "g4.bond_main|G4-7-items",
                "d3.prepaid_receipts_detail|D3-vc-current-rows", "d3.prepaid_receipts_detail|D3-vc-post-rows",
                "d7.contract_liabilities_detail|D7-7-period-rows", "d7.contract_liabilities_detail|D7-7-post-rows",
                "d6.contract_assets_detail|D6-5-rows",
                "l4.bonds_payable|L4-3-rows"):
        assert key not in misses, (key, sorted(misses.get(key, ())))


def test_scanner_reports_each_kind_on_a_constructed_corpus() -> None:
    """判据自检：① 前端全无、② 不在本 item 的代码里、占位 store item、动态键与常量拼键各按口径报 / 不报。"""
    texts = {
        "a/useX.ts": "const KEY = 'X-rows'\nexport interface Row { fooBar: number; rowKey: string }",
        "a/XTab.vue": "import { useX } from './useX'\nconst row = { quxQuux: 1 }",
        "b/other.ts": "export const bazQux = 1\nconst ITEM_PREFIX = 'K9-3-adj'\nsave(`${ITEM_PREFIX}-entries`, { memoText: '' })",
        "c/cells.ts": "const sections = ['aging', 'customer']\nconst k = `D9-adj-${section}-prior-aje`",
    }
    corpus = S.Corpus(
        texts=texts,
        tokens={k: frozenset(S._TOKEN.findall(v)) for k, v in texts.items()},
        imports={"a/XTab.vue": {"a/useX.ts"}},
        importers={"a/useX.ts": {"a/XTab.vue"}},
        all_tokens=frozenset().union(*(frozenset(S._TOKEN.findall(v)) for v in texts.values())),
        derived_keys={k: S._derived_keys(v) for k, v in texts.items()},
    )
    names = [
        ("c1", "X-rows", "fooBar"),       # 本 item 的 composable 里有 ⇒ 不报
        ("c1", "X-rows", "quxQuux"),      # import 本 item composable 的 tab 里有 ⇒ 不报
        ("c1", "X-rows", "bazQux"),       # 前端有、但在别的文件 ⇒ ② 报
        ("c1", "X-rows", "nowhereAtAll"),  # 前端全无 ⇒ ① 报
        ("c2", "", "nowhereEither"),       # 无 store item 的表只判 ① ⇒ 报
        ("c2", "", "fooBar"),              # 无 store item、前端有 ⇒ 不报
        ("c3", "placeholder", "fooBar"),   # 占位 store item ⇒ 一律报
        ("c4", "K9-3-adj-entries", "memoText"),  # 常量拼出的键 ⇒ 认得出本 item 的文件 ⇒ 不报
        ("c4", "K9-3-adj-entries", "fooBar"),    # …但别的文件里的名字不算 ⇒ 报
        ("c5", "D9-adj-aging-prior-aje", "D9-adj-aging-prior-aje"),  # 逐格动态键：片段都在 ⇒ 不报
        ("c5", "D9-adj-zzz-prior-aje", "D9-adj-zzz-prior-aje"),      # 片段 zzz 前端无 ⇒ ① 报
    ]
    got = {k: sorted(v) for k, v in S.compute_misses(corpus, names).items()}
    assert got == {
        "c1|X-rows": ["bazQux", "nowhereAtAll"],
        "c2|": ["nowhereEither"],
        "c3|placeholder": ["fooBar"],
        "c4|K9-3-adj-entries": ["fooBar"],
        "c5|D9-adj-zzz-prior-aje": ["D9-adj-zzz-prior-aje"],
    }


def test_contract_scan_sees_row_identity_keys_and_nested_paths() -> None:
    """名单含行身份键（D3-4 两区 rowKey）与嵌套路径各段（D4-2 的 months/*），不只是末段字段名。"""
    names = set(S.contract_names())
    assert ("d3.prepaid_receipts_detail", "D3-ana-credit-rows", "rowKey") in names
    assert ("d3.prepaid_receipts_detail", "D3-ana-credit-rows", "counterCheck") in names
    assert any(cid == "d4.revenue_detail" and item == "D4-2-rows" and seg == "months" for cid, item, seg in names)
    assert len(names) > 3000
# ═══ 「词干 × 后缀」拼键（spec oo-writeback-template-parity-closure R3.2 批 D，L4-3 教训）═══
# L4-3 的 38 个契约 json 键与前端运行时键**逐字相同**，但整个键名在源码里从不逐字出现：
# 词干在 `const PAIR_STEMS = ['priorAje', …]`，后缀在 `for (const unit of ['Qty','Amount'])`，
# 键在 `` `${stem}${unit}` `` 与 `row[g.stem + unit.suffix]` 里拼出来。旧口径逐字比对 ⇒ 27 条假阴。


def test_composed_keys_recognise_real_composition_shapes() -> None:
    """三种真实写法各自产出键；合成的键不是「凡以 Qty/Amount 结尾」都算。"""
    src = (
        "const STEMS = ['priorAje', 'auditedEnd'] as const\n"
        "type S = (typeof STEMS)[number]\n"
        "for (const stem of STEMS) {\n"
        "  row[`${stem}Qty`] = 0\n"
        "  out[`${stem}${unit}`] = 0\n"
        "}\n"
        "for (const unit of ['Qty', 'Amount'] as const) {\n"
        "  x = 1\n"
        "}\n"
        "const LABELS: Record<S, string> = {\n"
        "  priorAje: 'a',\n"
        "  auditedEnd: 'b',\n"
        "}\n"
        "const g = { stem: 'priorAje', formula: false }\n"
        "v = row[g.stem + unit.suffix]\n"
        "const SUFFIXES = [{ suffix: 'Qty' }, { suffix: 'Amount' }]\n"
    )
    keys = S.composed_keys(src)
    assert {"priorAjeQty", "priorAjeAmount", "auditedEndQty", "auditedEndAmount"} <= keys
    # 反向：词干没配后缀 / 后缀没配词干 / 纯虚构，都不得被合成出来
    assert "QtyQty" not in keys and "AmountQty" not in keys
    assert "instrumentNameQty" not in keys, "非词干池里的名字不得被拼"


def test_composed_keys_do_not_invent_keys_for_a_file_without_composition() -> None:
    """阴性对照：没有拼法的文件产不出任何键（否则判据会「什么都认」）。"""
    assert S.composed_keys("const KEY = 'L4-3-rows'\nexport const x = { a: 1 }") == frozenset()


def test_l4_3_composed_keys_are_the_27_exchange_names(corpus: S.Corpus) -> None:
    """L4-3：30 个以 `Qty`/`Amount` 结尾的契约键里，3 个在处理范围内**字面出现**（两个标量 +
    `auditedEndAmount`，后者在 tab 的 `applyL4_3Formulas(r).auditedEndAmount` 里），其余 **27 个配对键
    源码里从不逐字出现、只能靠拼键识别** —— 这 27 个正是旧口径逐字比对误报的那些，双向断言防「什么都认」。"""
    keys = S.scope_composed_keys(corpus, "L4-3-rows")
    contracted = {
        f["json_pointer"].rsplit("/", 1)[-1]
        for f in json.loads(
            (S.CONTRACTS_DIR / "l4.bonds_payable.json").read_text(encoding="utf-8")
        )["sheets"][0]["tables"][0]["fields"]
    }
    suffixed = {n for n in contracted if n.endswith(("Qty", "Amount"))}
    assert len(suffixed) == 30, f"以 Qty/Amount 结尾的契约键数变了：{len(suffixed)}"
    scope = frozenset().union(*(corpus.tokens[f] for f in S.scope_files(corpus, "L4-3-rows")
                               if f in corpus.tokens))
    literal = {n for n in suffixed if n in scope}
    assert literal == {"auditedEndAmount", "issueAmount", "issueQty"}, f"字面出现的集合变了：{sorted(literal)}"
    only_composed = suffixed - literal
    assert len(only_composed) == 27, f"只能靠拼键识别的应有 27 个：{len(only_composed)}"
    assert only_composed <= keys, f"这些配对键拼不出来：{sorted(only_composed - keys)}"
    assert "unauditedPriorBogus" not in keys and "accountingClassQty" not in keys


def test_mutation_renamed_pair_stem_is_reported(corpus: S.Corpus) -> None:
    """磁盘变异等价物：把契约的配对键改成前端拼不出的名字 ⇒ 必须报（分母 = 改名的那些）。"""
    real = S.contract_names()
    renamed = []
    hit = 0
    for cid, item, seg in real:
        if cid == "l4.bonds_payable" and seg.startswith("priorAje"):
            renamed.append((cid, item, "priorAjeRenamed" + seg[len("priorAje"):]))
            hit += 1
        else:
            renamed.append((cid, item, seg))
    assert hit == 2, f"变异靶点没命中（改名前缀改了？）：{hit}"
    misses = S.compute_misses(corpus, renamed)
    got = sorted(misses.get("l4.bonds_payable|L4-3-rows", ()))
    assert got == ["priorAjeRenamedAmount", "priorAjeRenamedQty"], got