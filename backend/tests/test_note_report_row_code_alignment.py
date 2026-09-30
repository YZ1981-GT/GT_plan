"""附注模板 `report_row_code` 与 `report_config` 编号体系一致性守卫。

134 行陈旧编号（固定资产→BS-014 实为其他流动资产、短期借款→BS-031 实为使用权资产等）
已用 `remap_note_report_row_codes.py --apply` 按**标签反查**重映射（位移量不一致，
统一偏移会出错）。本守卫防止再次漂移。

数据源 = `report_row_code_index.json`（离线快照，由 `--dump-index` 从
`report_config` DB 表物化，CI 无 DB 时用它）。

spec: .kiro/specs/h-cycle-legacy-cleanup-and-platform-hygiene/ R6（Property 4/5）
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_FIX = _ROOT / "scripts" / "fix" / "remap_note_report_row_codes.py"
_INDEX_PATH = _ROOT / "data" / "report_row_code_index.json"
_PATHS = [
    _ROOT / "data" / "note_template_listed.json",
    _ROOT / "data" / "note_template_soe.json",
]

# 每条须写理由：'ambiguous' = 库内该标签本身对应多个编号，**且现绑定就是其中之一**；
# 'not_found' = 标签在 report_config 查不到（如「其他货币资金」是货币资金子分类，
# 不是独立报表行）。
#
# 🔴 **2026-09-30 全表重写：原来这里有 5 条在给「确定错的绑定」背书**。
#
# 原条目的理由都写成「ambiguous：BS-041/BS-055 两码同名『短期借款』」—— 这句话本身是
# 真的，但它描述的是**标签**的歧义，而键里那个 `BS-031` **根本不在候选集里**
# （`BS-031` 实为「使用权资产」）。于是守卫看到「有理由、已登记」就放过，
# 一个把「短期借款」绑到「使用权资产」的错绑定被合法化了半年。同型 5 条：
#
#   listed 三、… 资本公积  BS-052 = 一年内到期的非流动负债  → 已纠为 BS-083
#   soe 八、81 短期借款    BS-031 = 使用权资产              → 已纠为 BS-041
#   soe 八、91 短期借款    BS-031 = 使用权资产              → 已纠为 BS-041
#   soe 八、91 其他应付款  BS-037 = 其他非流动资产          → 已纠为 BS-050
#   soe 八、92 短期借款    BS-031 = 使用权资产              → 已纠为 BS-041
#
# 另 3 条同型但当时未登记（守卫因此正确地报了红）：soe 八、18 其他综合收益 BS-053
# （= 其他流动负债）→ BS-085；soe 八、53 长期应付款 BS-044（= 应付票据）→ BS-064；
# soe 八、93 存货 BS-008（= 预付款项）→ BS-010（**回归**：restricted-assets spec
# 当年已按公式实证选过 BS-010，后被改回 BS-008）。
#
# 裁决依据与逐条结构性证据见 `remap_note_report_row_codes.AMBIGUOUS_ADJUDICATION`。
# 防复发：新增 `test_allowlist_codes_are_real_candidates` —— 每条 ambiguous 型条目的
# 编号**必须在候选集内**，把「有理由就放过」换成可伪证的断言。
#
# 🔴 **2026-09-30 二次重导（模板撤销陈旧覆盖之后）**：上面那轮重写是在
# `56acf363d` 的**陈旧副本**上做的（该提交把两份模板整体换回了 7 月下旬的版本）。
# 模板经 `restore_note_templates_from_stale_overwrite.py` 恢复后逐条重算：
#   * 移出 3 条 —— 恢复后的模板里这三行**本来就不带** report_row_code
#     （`五、1 其他货币资金` / `八、18 其他综合收益` / `八、53 长期应付款`），
#     那三个编号是陈旧副本自带的错码，经上一轮「纠正」后才登记进来；
#   * 补入 4 条 —— 恢复后才重新出现的行（下方 `八、9` / `十二、其他应收款` /
#     `八、42` / `八、31`），逐条附候选集与主表位置证据。
_MANUAL_ALLOWLIST: dict[str, str] = {
    "listed|三、重要会计政策、会|资本公积|BS-083": (
        "ambiguous：BS-079/BS-083 两码同名『资本公积』；BS-083 在「所有者权益：」段内"
        "（081 实收资本 / 082 其他权益工具 / 083 资本公积），BS-079 在所有者权益段之前"
    ),
    "soe|八、9|其他应收款项|BS-009": (
        "not_found：国企版把该行写作「其他应收款项」，report_config 只有「其他应收款」；"
        "BS-009 即主表其他应收款行（008 预付款项 与 010 存货 之间）"
    ),
    "soe|十二、其他应收款|其他应收款项|BS-009": (
        "not_found：母公司章该子节按合并章 八、9 同构复制，行标签同为「其他应收款项」，"
        "绑定同为 BS-009『其他应收款』"
    ),
    "soe|八、42|其他应付款项|BS-050": (
        "not_found：国企版写作「其他应付款项」，report_config 只有「其他应付款」；"
        "BS-050 在 049 应交税费 与 051 持有待售负债 之间（主表行），同名 BS-075 在扩展块"
    ),
    "soe|八、31|递延所得税负债|BS-067": (
        "ambiguous：BS-067/BS-096 两码同名；BS-067 在 066 递延收益 与 068 其他非流动负债 之间"
        "（主表非流动负债段），BS-096 在 091 所有者权益合计 之后的扩展块"
        "（095 递延收益 / 097 其他非流动负债）"
    ),
    "soe|八、81|短期借款|BS-041": (
        "ambiguous：BS-041/BS-055 两码同名；BS-041 紧随 040「流动负债：」，"
        "BS-055 在 054 流动负债合计 之后、紧邻 △向中央银行借款（金融企业扩展块）"
    ),
    "soe|八、91|短期借款|BS-041": "ambiguous：同 八、81，主表行是 BS-041",
    "soe|八、91|其他应付款|BS-050": (
        "ambiguous：BS-050/BS-075 两码同名；BS-050 在 049 应交税费 与 051 持有待售负债 之间，"
        "BS-075 紧邻 ▲应付手续费及佣金（扩展块）"
    ),
    "soe|八、92|短期借款|BS-041": "ambiguous：同 八、81，主表行是 BS-041",
    "soe|八、93|存货|BS-010": (
        "ambiguous：BS-010/BS-018 两码同名；BS-010 在 009 其他应收款 与 011 合同资产 之间"
        "（公式 SUM_TB 1401~1499），BS-018 在 015 流动资产合计 之后、紧邻 △买入返售金融资产。"
        "与 restricted-assets-note-row-scope-rollout Task 3 的既有裁决一致"
    ),
}


def _load_fix():
    import sys

    spec = importlib.util.spec_from_file_location("_fix_row_code", _FIX)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # 🔴 `@dataclass` 内部按 `sys.modules[cls.__module__]` 反查模块做类型解析，
    # 未注册进 sys.modules 时该查找返回 None → AttributeError。
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


FIX = _load_fix()


@pytest.fixture(scope="module")
def index() -> dict:
    if not _INDEX_PATH.exists():
        pytest.skip(f"缺 {_INDEX_PATH.name}，先跑 --dump-index（需 DATABASE_URL）")
    return json.loads(_INDEX_PATH.read_text(encoding="utf-8"))


def test_index_not_empty(index: dict) -> None:
    """反向自检：索引确实有内容，否则后续断言全在空转。"""
    assert index["row_count"] > 100
    for family in ("listed", "soe"):
        assert len(index["label_to_codes"][family]) > 50


def test_normalize_label_strips_prefixes() -> None:
    assert FIX.normalize_label("其中：短期借款") == "短期借款"
    assert FIX.normalize_label("减：坏账准备") == "坏账准备"
    assert FIX.normalize_label("△结算备付金") == "结算备付金"
    assert FIX.normalize_label("一、流动资产：") == "流动资产"
    assert FIX.normalize_label(None) == ""


@pytest.mark.parametrize("path", _PATHS, ids=lambda p: p.name)
def test_no_stale_report_row_codes(path: Path, index: dict) -> None:
    """Property 4/5: 全库带 report_row_code 的行，标签唯一解析时必与当前编号一致。"""
    doc = json.loads(path.read_text(encoding="utf-8"))
    variant = "listed" if "listed" in path.name else "soe"
    results = FIX.resolve_doc(doc, variant, index, apply=False)
    stale = [r for r in results if r.reason == "ok"]
    assert not stale, (
        f"{path.name} 残留 {len(stale)} 处陈旧编号：" + " / ".join(str(r) for r in stale[:10])
        + "；请重跑 python backend/scripts/fix/remap_note_report_row_codes.py --apply"
    )


@pytest.mark.parametrize("path", _PATHS, ids=lambda p: p.name)
def test_manual_entries_are_allowlisted(path: Path, index: dict) -> None:
    """`ambiguous`/`not_found` 必须逐条登记在 allowlist 并写明理由。"""
    doc = json.loads(path.read_text(encoding="utf-8"))
    variant = "listed" if "listed" in path.name else "soe"
    results = FIX.resolve_doc(doc, variant, index, apply=False)
    manual = [r for r in results if r.reason in ("ambiguous", "not_found")]
    undeclared = []
    for r in manual:
        raw_label = r.label.split("（现")[0]
        key = f"{r.variant}|{r.section}|{raw_label}|{r.old_code}"
        if key not in _MANUAL_ALLOWLIST:
            undeclared.append(key)
    assert not undeclared, (
        f"以下待人工条目未登记 allowlist：{undeclared}"
    )


def test_allowlist_has_no_stale_entries(index: dict) -> None:
    """allowlist 不得残留已可唯一解析的条目（否则守卫形同虚设）。"""
    all_keys: set[str] = set()
    for path in _PATHS:
        doc = json.loads(path.read_text(encoding="utf-8"))
        variant = "listed" if "listed" in path.name else "soe"
        results = FIX.resolve_doc(doc, variant, index, apply=False)
        for r in results:
            if r.reason in ("ambiguous", "not_found"):
                raw_label = r.label.split("（现")[0]
                all_keys.add(f"{r.variant}|{r.section}|{raw_label}|{r.old_code}")
    stale = sorted(k for k in _MANUAL_ALLOWLIST if k not in all_keys)
    assert not stale, f"以下 allowlist 条目已可解析或已消失，请移出：{stale}"


def test_allowlist_codes_are_real_candidates(index: dict) -> None:
    """🔴 `ambiguous` 型条目的编号**必须在候选集内** —— 把理由从"说法"变成可伪证断言。

    立此判据的由来（2026-09-30 实证）：原 allowlist 有 5 条理由写着
    「ambiguous：BS-041/BS-055 两码同名『短期借款』」，而键里的编号是 `BS-031`
    （实为「使用权资产」）—— **压根不在那两个候选里**。理由句描述的是标签歧义，
    却被当成了对那个具体编号的背书，于是把「短期借款绑到使用权资产」放过了半年。

    本判据只问一件可验证的事：你登记的这个编号，是不是这个标签的候选之一。
    不是 ⇒ 打红，逼着去 `AMBIGUOUS_ADJUDICATION` 裁决而不是写句理由绕过。
    `not_found` 型（标签在库里查不到，如「其他货币资金」）天然没有候选集，跳过。
    """
    bad: list[str] = []
    checked = 0
    for key, reason in _MANUAL_ALLOWLIST.items():
        variant, _section, label, code = key.split("|")
        candidates = index["label_to_codes"][variant].get(label)
        if not candidates:
            # 没有候选 ⇒ 必须是 not_found 型，理由里也要这么写
            assert reason.startswith("not_found"), (
                f"{key} 的标签在索引里无候选，理由却写成 {reason[:24]!r}"
            )
            continue
        checked += 1
        assert reason.startswith("ambiguous"), (
            f"{key} 的标签有候选 {candidates}，理由却不是 ambiguous 型：{reason[:24]!r}"
        )
        if code not in candidates:
            real = index["code_to_labels"][variant].get(code) or ["?"]
            bad.append(f"{key} —— {code} 实为「{'/'.join(real)}」，不在候选集 {candidates} 内")
    assert checked >= 5, f"只校到 {checked} 条 ambiguous 型条目 —— 判据可能在空转"
    assert not bad, (
        "以下 allowlist 条目登记的编号不是该标签的候选（= 确定错的绑定被理由句背书）：\n"
        + "\n".join(f"  {b}" for b in bad)
        + "\n→ 请在 remap_note_report_row_codes.AMBIGUOUS_ADJUDICATION 里裁决正确编号后 --apply"
    )


def test_resolve_doc_does_not_touch_account_codes() -> None:
    """Property 5: 改写只动 report_row_code，其余字段逐字不变。"""
    fixture = {
        "sections": [
            {
                "section_number": "测、1",
                "rows": [
                    {
                        "label": "短期借款",
                        "report_row_code": "BS-031",
                        "account_codes": ["2001"],
                        "unrelated": {"x": 1},
                    }
                ],
            }
        ]
    }
    index = {
        "label_to_codes": {"fixture": {"短期借款": ["BS-041"]}},
        "code_to_labels": {"fixture": {}},
    }
    before = json.dumps(fixture, sort_keys=True)
    results = FIX.resolve_doc(fixture, "fixture", index, apply=True)
    assert len(results) == 1 and results[0].reason == "ok"
    row = fixture["sections"][0]["rows"][0]
    assert row["report_row_code"] == "BS-041"
    assert row["account_codes"] == ["2001"]
    assert row["unrelated"] == {"x": 1}
    assert row["label"] == "短期借款"
    # 除 report_row_code 外没有其它字段被动过
    after_without_code = dict(row)
    after_without_code.pop("report_row_code")
    before_dict = json.loads(before)["sections"][0]["rows"][0]
    before_dict.pop("report_row_code")
    assert after_without_code == before_dict


def test_resolve_doc_ambiguous_foreign_and_not_found_unchanged() -> None:
    """反向自检：三种「不敢改」的情形一律原样保留，但**分类必须分得开**。

    🔴 判据加强（2026-09-30）。本用例原来只有两行 fixture，且那行「多义行」的现绑定
    `BS-999` **不在**候选集 `['BS-001','BS-002']` 里 —— 即它其实是「确定错」的样本，
    却被断言成 `ambiguous`。也就是说**这个反向自检本身就在为混淆背书**：只要脚本把
    「绑了个不在候选里的编号」也叫 ambiguous，它就绿。真实数据里 8 条错绑定能藏半年，
    与这里的口径是同一个根。

    现在三种分开：候选内 → `ambiguous`；候选外 → `foreign`（确定错，必须被看见）；
    无候选 → `not_found`。三种都**不改写**（脚本仍然不猜）。
    """
    fixture = {
        "sections": [
            {
                "section_number": "测、1",
                "rows": [
                    {"label": "多义行", "report_row_code": "BS-001"},   # 在候选集内
                    {"label": "错绑行", "report_row_code": "BS-999"},   # 不在候选集内
                    {"label": "查不到", "report_row_code": "BS-888"},
                ],
            }
        ]
    }
    index = {
        "label_to_codes": {
            "fixture": {"多义行": ["BS-001", "BS-002"], "错绑行": ["BS-001", "BS-002"]},
        },
        "code_to_labels": {"fixture": {"BS-999": ["使用权资产"]}},
    }
    results = FIX.resolve_doc(fixture, "fixture", index, apply=True)
    by_label = {r.label.split("（现")[0]: r for r in results}
    assert by_label["多义行"].reason == "ambiguous"
    assert by_label["错绑行"].reason == "foreign"
    assert by_label["查不到"].reason == "not_found"
    # `foreign` 必须把候选集带在报文里，人工裁决时不用再去翻索引
    assert by_label["错绑行"].candidates == ("BS-001", "BS-002")
    rows = fixture["sections"][0]["rows"]
    assert [r["report_row_code"] for r in rows] == ["BS-001", "BS-999", "BS-888"]


def test_adjudication_rewrites_foreign_binding() -> None:
    """裁决表命中时，`foreign` 必须被改写成裁决值（否则裁决表形同摆设）。"""
    key = "fixture|测、1|错绑行"
    fixture = {
        "sections": [
            {"section_number": "测、1",
             "rows": [{"label": "错绑行", "report_row_code": "BS-999"}]}
        ]
    }
    index = {
        "label_to_codes": {"fixture": {"错绑行": ["BS-001", "BS-002"]}},
        "code_to_labels": {"fixture": {}},
    }
    FIX.AMBIGUOUS_ADJUDICATION[key] = "BS-002"
    try:
        results = FIX.resolve_doc(fixture, "fixture", index, apply=True)
    finally:
        FIX.AMBIGUOUS_ADJUDICATION.pop(key, None)
    assert [r.reason for r in results] == ["ok"]
    assert fixture["sections"][0]["rows"][0]["report_row_code"] == "BS-002"


def test_adjudication_table_targets_are_valid_candidates(index: dict) -> None:
    """裁决表自身的每个目标编号必须是该标签的候选之一（防裁错码）。"""
    assert FIX.AMBIGUOUS_ADJUDICATION, "裁决表为空 —— 判据空转"
    bad: list[str] = []
    for key, chosen in FIX.AMBIGUOUS_ADJUDICATION.items():
        variant, _section, label = key.split("|")
        candidates = index["label_to_codes"][variant].get(label) or []
        if chosen not in candidates:
            bad.append(f"{key} → {chosen}，候选集为 {candidates}")
    assert not bad, "裁决表指向了非候选编号：\n" + "\n".join(f"  {b}" for b in bad)


def test_check_mode_returns_ok() -> None:
    if not _INDEX_PATH.exists():
        pytest.skip("缺索引快照")
    index = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    for path in _PATHS:
        ok, log = FIX.process(path, index, apply=False, check_only=True)
        assert ok, "\n".join(log)
