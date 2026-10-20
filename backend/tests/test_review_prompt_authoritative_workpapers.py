"""复核提示词按权威编码表取底稿与科目（preexisting-test-failures-closure G12 第二轮）。

覆盖率分母与科目级降级原先都靠手写 ``_AUDIT_CYCLE_ALIASES``：它按旧编码写成，与致同 2025 编码 40 个前缀
错位（G1 交易性金融资产 → 长期股权投资提示词、N5 所得税费用 → 投资收益提示词…），整本底稿复核
（wp_ai 不带 sheet 名，必走科目级）加载的是别的科目的提示词。现改为 ``wp_account_mapping.json``。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services import review_prompt_service as rps

D_TO_N = "DEFGHIJKLMN"


def _subject_loaded(svc: rps.ReviewPromptService, wp_code: str) -> str | None:
    result = svc._load_subject_prompt(wp_code)
    return rps._subject_of(Path(result.file_path).stem) if result else None


def test_authoritative_list_covers_every_d_to_n_workpaper():
    """D~N 89 本底稿与模板库前缀逐个一致；编码表另含 A/B/C/S。"""
    import json

    workpapers = rps._authoritative_workpapers()
    library = json.loads(
        (Path(rps.__file__).resolve().parents[2] / "data" / "gt_template_library.json").read_text(encoding="utf-8")
    )
    template_prefixes = {
        rps._PREFIX_RE.match(t["code"]).group(1).upper()
        for t in library["templates"]
        if t["code"][:1] in D_TO_N and rps._PREFIX_RE.match(t["code"])
    }
    assert {p for p in workpapers if p[0] in D_TO_N} == template_prefixes
    assert len(template_prefixes) == 89
    assert {p[0] for p in workpapers} == set("ABCDEFGHIJKLMNS")


def test_subject_fallback_never_loads_another_subjects_prompt():
    """全部底稿：科目级降级要么不加载，要么加载的就是该底稿自己的科目（或核对过的同义名）。"""
    svc = rps.ReviewPromptService()
    for prefix, workpaper in rps._authoritative_workpapers().items():
        loaded = _subject_loaded(svc, prefix)
        assert loaded is None or loaded in workpaper.subject_names, (prefix, workpaper, loaded)


@pytest.mark.parametrize(("wp_code", "subject"), [
    ("G1", "交易性金融资产"),      # 原别名表：长期股权投资
    ("G4", "债权投资"),            # 原：其他权益工具
    ("H9", "租赁负债"),            # 原：无形资产
    ("I6", "研发费用"),            # 原：递延所得税负债
    ("L8", "财务费用"),            # 原：其他非流动负债
    ("M2", "实收资本或股本"),      # 原：资本公积（同义名：实收资本）
    ("M5", "盈余公积"),            # 原：未分配利润（无文件 ⇒ base）
    ("N1", "递延所得税资产"),      # 原：财务费用
    ("N5", "所得税费用"),          # 原：投资收益
    ("D4", "收入"),                # 同义名：营业收入
    ("F5", "成本"),                # 同义名：营业成本
    ("H10", "资产处置收益"),       # 同义名：资产处置损益
    ("F1", "预付账款"),            # 科目名「预付款项」无文件，底稿名去「审定表」命中
    ("J2", "长期应付职工薪酬"),    # 设定受益计划的科目
    ("M10", "其他权益工具"),
    ("D2-1", "应收账款"),          # sheet 子码按前缀取底稿
])
def test_subject_fallback_loads_the_workpapers_own_subject(wp_code, subject):
    assert _subject_loaded(rps.ReviewPromptService(), wp_code) == subject


@pytest.mark.parametrize("wp_code", [
    "D0",      # 函证底稿：没有「应收函证」科目级文件
    "G8",      # 其他权益工具投资 ≠ M10 的其他权益工具
    "N4",      # 税金及附加（原别名表给研发费用）
    "M1",      # 应付股利（原别名表给实收资本）
    "general",  # wp_ai 无编码时的占位
    "X9",      # 编码表里没有
])
def test_subject_fallback_returns_none_instead_of_a_neighbour(wp_code):
    assert rps.ReviewPromptService()._load_subject_prompt(wp_code) is None


def test_subject_match_is_exact_not_containment(tmp_path, monkeypatch):
    """只有「营业外收入」文件时 D4 不得命中它（包含匹配会命中），K12 照常命中。"""
    (tmp_path / "营业外收入审计复核提示词.md").write_text("## tips\n\n1. 营业外收入要点\n", encoding="utf-8")
    monkeypatch.setattr(rps, "_authoritative_workpapers", lambda: {
        "D4": rps._Workpaper("营业收入审定表", ("营业收入", "收入")),
        "K12": rps._Workpaper("营业外收入", ("营业外收入",)),
    })
    svc = rps.ReviewPromptService(base_dir=tmp_path)
    assert svc._load_subject_prompt("D4") is None
    assert svc.load_prompt("D4", None).source_level == "base"
    assert _subject_loaded(svc, "K12") == "营业外收入"


def test_synonym_table_has_no_stale_entries():
    """同义名表每条都在用：键是某本底稿的科目名 / 底稿名，值是真实存在的科目级文件。"""
    names = {n for w in rps._authoritative_workpapers().values() for n in w.subject_names}
    subjects = {rps._subject_of(f.stem) for f in rps._DEFAULT_TSJ_DIR.glob("*.md")}
    for key, targets in rps._SUBJECT_FILE_SYNONYMS.items():
        assert key in names, key
        assert any(t in subjects for t in targets), (key, targets)
