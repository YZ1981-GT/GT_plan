"""附注章节旧编号别名：节改挂到别的章、编号换章号后，旧编号仍能解析到现行编号。

spec: disclosure-note-template-word-realignment Task 3（design §3.4，NFR-3）
"""

from __future__ import annotations

import json

import pytest

from app.services import note_section_catalog as catalog


def _write_seed(tmp_path, std: str, sections: list[dict]):
    path = tmp_path / f"note_template_{std}.json"
    path.write_text(json.dumps({"sections": sections}, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def synthetic_seeds(tmp_path, monkeypatch):
    paths = {
        "listed": _write_seed(tmp_path, "listed", [
            {"section_number": "五、75", "section_title": "所得税费用", "legacy_section_numbers": ["三、所得税费用"]},
            {"section_number": "五、1", "section_title": "货币资金"},
        ]),
        "soe": _write_seed(tmp_path, "soe", [
            {"section_number": "四、递延所得税资产及递延所得税负债", "section_title": "递延所得税资产及递延所得税负债",
             "legacy_section_numbers": ["六、递延所得税资产及递延所得税负债"]},
            {"section_number": "八、1", "section_title": "货币资金"},
        ]),
    }
    monkeypatch.setattr(catalog, "template_json_path", lambda tt: paths[catalog.normalize_template_type(tt)])
    catalog.clear_template_caches()
    yield
    catalog.clear_template_caches()


def test_legacy_codes_resolve_for_both_standards(synthetic_seeds):
    assert catalog.normalize_section_code("三、所得税费用", template_type="listed") == "五、75"
    assert catalog.normalize_section_code("六、递延所得税资产及递延所得税负债", template_type="soe") == (
        "四、递延所得税资产及递延所得税负债"
    )
    assert catalog.normalize_section_code("五、75", template_type="listed") == "五、75"
    assert catalog.normalize_section_code("三、存货", template_type="listed") == "三、存货"  # 不在别名表：原样
    assert catalog.normalize_section_code("五、1", template_type="soe") == "八、1"  # 国企五→八旧规则不受影响
    assert catalog.resolve_binding_key("三、所得税费用", template_type="listed") == "五、75"


def test_scope_lookup_follows_alias(synthetic_seeds):
    assert catalog.section_scope_for_code(
        "三、所得税费用", {"五、75": "consolidated_only"}, template_type="listed",
    ) == "consolidated_only"


@pytest.mark.parametrize("std", ["soe", "listed"])
def test_real_seed_aliases_never_shadow_current_codes(std):
    """别名不得与任何现行编号相同（否则旧编号会把现行节吞掉），且一个旧编号只指向一节。"""
    sections = json.loads(catalog.template_json_path(std).read_text(encoding="utf-8"))["sections"]
    current = {s["section_number"] for s in sections}
    owners: dict[str, list[str]] = {}
    for s in sections:
        for old in s.get("legacy_section_numbers") or []:
            owners.setdefault(old, []).append(s["section_number"])
    assert not (set(owners) & current), sorted(set(owners) & current)
    assert all(len(v) == 1 for v in owners.values()), {k: v for k, v in owners.items() if len(v) > 1}


def test_realigned_codes_do_not_collide_across_standards():
    """改挂 / 补节分配的编号若在另一准则也存在，必须是同一节（标题相同）。

    绑定 / 公式 / 列规则等数据文件只按编号作键、不分准则：同号不同义会互相覆盖（2026-10-16 首轮实测：
    上市「八、5」= 政府补助，把国企「八、5 应收账款」的绑定挤掉）。
    """
    from app.services.note_section_kind import normalize_title

    seeds = {std: json.loads(catalog.template_json_path(std).read_text(encoding="utf-8"))["sections"]
             for std in ("soe", "listed")}
    titles = {std: {s["section_number"]: normalize_title(s.get("section_title")) for s in secs}
              for std, secs in seeds.items()}
    clashes = []
    for std, other in (("soe", "listed"), ("listed", "soe")):
        for s in seeds[std]:
            created = s.get("legacy_section_numbers") or s.get("_aligned_by") == "disclosure-note-template-word-realignment"
            code = s["section_number"]
            if created and code in titles[other] and titles[other][code] != titles[std][code]:
                clashes.append((std, code, s.get("section_title"), titles[other][code]))
    assert not clashes, clashes


def test_chapter_title_follows_report_scope():
    """上市项目附注章：单体「财务报表项目附注」、合并「合并财务报表项目附注」（四版 Word）。"""
    sections = json.loads(catalog.template_json_path("listed").read_text(encoding="utf-8"))["sections"]
    chapter = next(s for s in sections if s.get("level") == 1 and s["section_number"] == "五")
    assert catalog.section_title_for_scope(chapter, "standalone") == "财务报表项目附注"
    assert catalog.section_title_for_scope(chapter, "consolidated") == "合并财务报表项目附注"
    assert catalog.section_title_for_scope({"section_title": "税项"}, "standalone") == "税项"


@pytest.mark.asyncio
@pytest.mark.parametrize("rs,title", [("standalone", "财务报表项目附注"), ("consolidated", "合并财务报表项目附注")])
async def test_generation_uses_scope_chapter_title(rs, title):
    """生成链（``_load_templates``）按项目口径取章名：上市单体项目的第五章叫「财务报表项目附注」（Task 7）。"""
    import uuid

    from tests.test_disclosure_note_generation_text_order import _make_engine

    got = await _make_engine()._load_templates(uuid.uuid4(), "listed", report_scope=rs)
    chapter = next(t for t in got if t["note_section"] == "五")
    assert chapter["section_title"] == title
