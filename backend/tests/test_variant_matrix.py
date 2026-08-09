"""note_template_variant_matrix.json ↔ section_code_index.json 一致性校验.

Spec:   .kiro/specs/audit-report-template-integration/ task 0.6.2.1 / 0.6.2.2
Source: scripts/build_variant_matrix.py / scripts/normalize_note_bindings.py

断言：
- 矩阵每个账户每个变体的 code 必存在于 section_code_index 对应变体的「项目注释」章。
- legacy_aliases 与 index 一致。
- 关键账户（货币资金 / 固定资产）码与 index 对齐（防 POC 错码 五、12 回潮）。
- bindings 国企 八、N 已标注 legacy_aliases，且 loader 仍能用 五、N 别名解析。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "backend" / "data"
INDEX_PATH = DATA / "audit_report_templates" / "section_code_index.json"
MATRIX_PATH = DATA / "note_template_variant_matrix.json"

VARIANTS = ("soe_standalone", "soe_consolidated", "listed_standalone", "listed_consolidated")
PROJECT_CHAPTER = {
    "soe_standalone": "八",
    "soe_consolidated": "八",
    "listed_standalone": "五",
    "listed_consolidated": "五",
}


def _chapter(code: str) -> str:
    return code.split("、")[0] if "、" in code else code


@pytest.fixture(scope="module")
def index() -> dict:
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def matrix() -> dict:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def index_project_codes(index: dict) -> dict[str, set[str]]:
    """每变体「项目注释」章内的 section_code 集合."""
    out: dict[str, set[str]] = {}
    for vk in VARIANTS:
        chap = PROJECT_CHAPTER[vk]
        codes = {
            s["section_code"]
            for s in index["variants"][vk]["sections"]
            if _chapter(s["section_code"]) == chap
        }
        out[vk] = codes
    return out


@pytest.fixture(scope="module")
def index_alias_by_code(index: dict) -> dict[str, dict[str, list[str]]]:
    """每变体 section_code → legacy_aliases."""
    out: dict[str, dict[str, list[str]]] = {}
    for vk in VARIANTS:
        out[vk] = {
            s["section_code"]: (s.get("legacy_aliases") or [])
            for s in index["variants"][vk]["sections"]
        }
    return out


def test_matrix_non_empty(matrix: dict) -> None:
    assert matrix.get("accounts"), "matrix accounts empty"


#: 矩阵取值**不在 index「项目注释章」内**的已知条目 —— 逐条带成因。
#:
#: 判据修订（spec soe-listed-note-conversion-correctness / Task 12）：
#: 原断言假设「矩阵 code 一律落在项目注释章」（listed 五 / soe 八）。两条实证
#: 推翻该假设，且都不是错码：
#:
#: 1. **listed 模板把部分损益类/政策类科目放在别的章** —— 「三、重要会计政策」
#:    章下有 公允价值变动收益 / 信用减值损失 / 资产减值损失 / 资产处置收益 /
#:    营业外收支 / 所得税费用 / 现金流量表项目注释 / 债务重组 / 借款费用，
#:    「十四、日后事项」章下有 终止经营。这是模板结构事实（`section_number`
#:    的章前缀就是「三」「十四」），改矩阵去凑「五」反而制造错码。
#:    其中 3 条（公允价值变动收益 / 信用减值损失 / 所得税费用）在 Task 12 之前
#:    就已存在于矩阵，本断言长期为红 —— 属**判据缺陷**不是数据回归。
#:
#: 2. **`section_code_index.json` 是 POC 产物且已落后** —— `version='poc-v1'`，
#:    生成器 `build_section_code_index.py` 自述「仅扫描已打标的章节；未打标节
#:    输出到 stdout 供人工补录」。故「三、」章 43 节里多数未收录，「十四、」章
#:    只收录 4 节，soe 的 `八、94`（由 spec m-cycle 的 fix 脚本新建）完全缺失
#:    （index 的 `八、9x` 段只到 `八、93`）。
#:
#: 故判据分两级：
#:   **强**（无豁免）：code 必须存在于目标模板 `note_template_{listed,soe}.json`
#:          —— 那才是矩阵取值的真源（index 自身也是从模板+docx 派生的）。
#:   **弱**（可登记豁免）：code 若已被 index 收录，则必须落在该变体的项目注释章
#:          —— 保留原断言防错码回潮（如 POC 错码 五、12）。
#:
#: 值 = 成因分类；index 补全打标后应逐条移出（数量只许缩短，由自检钉死）。
INDEX_UNCOVERED_CODES: dict[tuple[str, str], str] = {
    # --- 成因 1+2：listed 模板放在「三、重要会计政策」章，且 index 未收录 ---
    ("gong_yun_jia_zhi_bian_dong_shou_yi", "三、公允价值变动收益"): (
        "listed 模板置于「三、重要会计政策」章；index(poc-v1) 未打标该节。"
        "Task 12 之前即存在，属预存在的判据缺陷。"
    ),
    ("xin_yong_jian_zhi_sun_shi", "三、信用减值损失"): (
        "listed 模板置于「三、重要会计政策」章；index(poc-v1) 未打标该节。"
        "Task 12 之前即存在，属预存在的判据缺陷。"
    ),
    ("suo_de_shui_fei_yong", "三、所得税费用"): (
        "listed 模板置于「三、重要会计政策」章；index(poc-v1) 未打标该节。"
        "Task 12 之前即存在，属预存在的判据缺陷。"
    ),
    ("zi_chan_jian_zhi_sun_shi", "三、资产减值损失（损"): (
        "listed 模板置于「三、」章（level=2 / 1 表），章节号是 md 重建的 10 字"
        "截断值；index(poc-v1) 未打标。Task 12 由 null 补记。"
    ),
    ("zi_chan_chu_zhi_shou_yi", "三、资产处置收益（损"): (
        "listed 模板置于「三、」章（level=2 / 2 表），md 截断值；index 未打标。"
    ),
    ("ying_ye_wai_shou_ru", "三、营业外收入（注："): (
        "listed 模板置于「三、」章（level=2 / 1 表），md 截断值；index 未打标。"
    ),
    ("ying_ye_wai_zhi_chu", "三、营业外支出（注："): (
        "listed 模板置于「三、」章（level=2 / 1 表），md 截断值；index 未打标。"
    ),
    ("xian_jin_liu_liang_biao_xiang_mu_zhu_shi", "三、现金流量表项目注"): (
        "listed 模板置于「三、」章（level=2 / 9 表），md 截断值；index 未打标。"
    ),
    ("zhong_zhi_jing_ying", "十四、终止经营"): (
        "listed 模板置于「十四、资产负债表日后事项」章（level=2 / 1 表）；"
        "index 的「十四、」段只收录 4 节，该节未打标。"
    ),
    # --- 成因 1：index **已收录**，但归在「三、」章而非项目注释章 ---
    ("zhai_wu_chong_zu", "三、债务重组【不适用"): (
        "index 已收录该 code，但章前缀是「三」（会计政策章）而非「五」。"
        "listed 模板该节 level=2 / 0 表 / 15 段 text_sections = 纯文字披露节，"
        "是合法落点（listed 模板有 48 个同形节，现有落点 五、72 亦是这种形态）。"
    ),
    ("jie_kuan_fei_yong", "三、借款费用"): (
        "同上；listed 模板该节 level=2 / 0 表 / 5 段 text_sections。"
    ),
    # --- 成因 2：章前缀正确，纯 index 落后 ---
    ("yi_ban_feng_xian_zhun_bei", "八、94"): (
        "章前缀「八」本就是 soe 项目注释章，问题在 index(poc-v1) 的 八、9x 段"
        "只到 八、93 —— 该章由 spec m-cycle 的 fix_note_m_equity_structure.py "
        "新建（sort_index 插位），index 未重建。"
    ),
}


@pytest.fixture(scope="module")
def template_section_numbers() -> dict[str, set[str]]:
    """两份附注模板的 section_number 全集 —— 矩阵取值的**真源**."""
    out: dict[str, set[str]] = {}
    for side in ("listed", "soe"):
        doc = json.loads((DATA / f"note_template_{side}.json").read_text(encoding="utf-8"))
        out[side] = {
            str(s.get("section_number"))
            for s in doc.get("sections", [])
            if isinstance(s, dict) and s.get("section_number")
        }
        assert out[side], f"note_template_{side}.json has no section_number (fixture broken)"
    return out


def test_every_matrix_code_exists_in_template(
    matrix: dict, template_section_numbers: dict[str, set[str]]
) -> None:
    """强断言（无豁免）：每个矩阵取值必须存在于对应侧的附注模板.

    这是取代 `test_every_matrix_code_exists_in_index` 强度的那一条 —— index 是
    POC 产物会漏收录，模板 JSON 才是矩阵取值的真源。编造的章节号在这里必红。
    """
    bad: list[str] = []
    for acct in matrix["accounts"]:
        for vk in VARIANTS:
            code = acct["variants"].get(vk)
            if code is None:
                continue
            side = "listed" if vk.startswith("listed") else "soe"
            if code not in template_section_numbers[side]:
                bad.append(f"{acct['account_key']}.{vk}={code!r} not in note_template_{side}.json")
    assert not bad, "matrix codes not found in the source templates:\n" + "\n".join(bad[:15])


def test_every_matrix_code_exists_in_index(
    matrix: dict, index_project_codes: dict[str, set[str]]
) -> None:
    """弱断言：已被 index 收录的 code 必落在该变体的项目注释章.

    未被 index 收录 / 归在别的章的条目须登记进 `INDEX_UNCOVERED_CODES`（带成因）。
    """
    bad: list[str] = []
    for acct in matrix["accounts"]:
        key = acct["account_key"]
        for vk in VARIANTS:
            code = acct["variants"].get(vk)
            if code is None or code in index_project_codes[vk]:
                continue
            if (key, code) in INDEX_UNCOVERED_CODES:
                continue
            bad.append(f"{key}.{vk}={code!r}")
    assert not bad, (
        "matrix codes not in index project-note chapter and not registered:\n"
        + "\n".join(bad[:15])
        + "\n=> either it is a real wrong code (fix the matrix), or the section legitimately "
        "lives in another chapter / index(poc-v1) has not indexed it yet — in that case "
        "register it in INDEX_UNCOVERED_CODES with evidence."
    )


def test_index_uncovered_registry_is_not_stale(
    matrix: dict, index_project_codes: dict[str, set[str]]
) -> None:
    """反向自检：登记表每条都必须**仍然**命中，且条目数只许缩短.

    - 某条已被 index 收录进项目注释章 ⇒ 立刻打红要求移出（防登记表变永久盲区）
    - 某条已不在矩阵里 ⇒ 同样要求移出（防表与数据脱节）
    - 上限锁死：index 重建后应逐条移出，不得反向往表里加条目来消红
    """
    live = {
        (a["account_key"], code)
        for a in matrix["accounts"]
        for vk in VARIANTS
        if (code := a["variants"].get(vk)) is not None and code not in index_project_codes[vk]
    }
    stale = sorted(set(INDEX_UNCOVERED_CODES) - live)
    assert not stale, (
        f"these registry entries no longer apply: {stale} => remove them "
        "(the code is now indexed in the project-note chapter, or left the matrix)"
    )
    assert len(INDEX_UNCOVERED_CODES) <= 12, (
        f"registry grew to {len(INDEX_UNCOVERED_CODES)} entries (cap 12). "
        "New unindexed codes must be justified by rebuilding section_code_index.json, "
        "not by enlarging the escape hatch."
    )
    for (key, code), reason in INDEX_UNCOVERED_CODES.items():
        assert len(reason.strip()) >= 30, f"{key}/{code}: reason too short to be evidence"
        assert "index" in reason or "模板" in reason, (
            f"{key}/{code}: reason must state whether it is a template-structure fact "
            "or an index(poc-v1) coverage gap"
        )


def test_account_keys_unique(matrix: dict) -> None:
    keys = [a["account_key"] for a in matrix["accounts"]]
    assert len(keys) == len(set(keys)), "duplicate account_key in matrix"


def test_legacy_aliases_match_index(
    matrix: dict, index_alias_by_code: dict[str, dict[str, list[str]]]
) -> None:
    """矩阵 legacy_aliases 必与 index 对应节一致."""
    bad: list[tuple] = []
    for acct in matrix["accounts"]:
        for vk, aliases in acct.get("legacy_aliases", {}).items():
            code = acct["variants"].get(vk)
            idx_aliases = index_alias_by_code[vk].get(code, [])
            if sorted(aliases) != sorted(idx_aliases):
                bad.append((acct["account_key"], vk, aliases, idx_aliases))
    assert not bad, f"legacy_aliases mismatch with index: {bad[:10]}"


def test_monetary_funds_codes(matrix: dict) -> None:
    """货币资金：soe 八、1 / listed 五、1 / soe legacy 五、1."""
    acct = next(a for a in matrix["accounts"] if a["section_title"] == "货币资金")
    assert acct["variants"]["soe_standalone"] == "八、1"
    assert acct["variants"]["listed_standalone"] == "五、1"
    assert acct["legacy_aliases"].get("soe_standalone") == ["五、1"]


def test_fixed_assets_codes_match_index_not_poc(matrix: dict) -> None:
    """固定资产：必为 index 真实码 八、22 / 五、22（非 POC 错码 五、12）."""
    acct = next(a for a in matrix["accounts"] if a["section_title"] == "固定资产")
    assert acct["variants"]["soe_standalone"] == "八、22"
    assert acct["variants"]["listed_standalone"] == "五、22"
    assert acct["variants"]["soe_standalone"] != "八、12"
    assert acct["variants"]["listed_standalone"] != "五、12"


def test_bindings_soe_legacy_alias_annotated() -> None:
    """bindings: 国企 canonical 八、1/八、2 已追加 legacy_aliases（镜像 index）."""
    try:
        from app.services import note_template_bindings_loader as loader
    except ModuleNotFoundError:
        from app.services import note_template_bindings_loader as loader

    loader.reload()
    b1 = loader.get_binding_for_section("八、1")
    assert b1 is not None, "八、1 binding missing"
    assert b1.get("legacy_aliases") == ["五、1"], b1.get("legacy_aliases")

    b2 = loader.get_binding_for_section("八、2")
    assert b2 is not None, "八、2 binding missing"
    assert b2.get("legacy_aliases") == ["五、2"], b2.get("legacy_aliases")


def test_catalog_resolves_soe_legacy_to_canonical() -> None:
    """catalog: 国企历史 五、N 归一到 八、N（loader 查表时所依赖的规则）."""
    try:
        from app.services.note_section_catalog import resolve_binding_key
    except ModuleNotFoundError:
        from app.services.note_section_catalog import resolve_binding_key

    # 八、3 衍生金融资产 不在 bindings，但归一规则本身必须把 五、3 → 八、3
    assert resolve_binding_key("五、3", template_type="soe") == "八、3"
    assert resolve_binding_key("五、1", template_type="soe") == "八、1"


# --------------------------------------------------------------------------- #
# Task 10（spec parent-company-note-chapter-and-sourcing）：
# parent_company_sections 母公司章维度守卫
#
# Requirements: 8.1, 10.4 / design Property 19
# 生成/校验脚本：backend/scripts/fix/fix_variant_matrix_parent_sections.py
#
# 判据取向说明（为什么用「文件内冻结快照」而不是 `git show HEAD:`）：
#   `git show HEAD:` 的语义是「相对上一次提交未变」—— 一旦本次改动被提交，
#   该判据就退化成「相对最近一次提交未变」，无法再钉住「Task 10 之前的取值」。
#   而冻结快照是**永久基线**（不依赖 git 可用性、不随提交漂移），
#   任何后续会话若要改这 102 个取值，必须显式修改基线并写明理由。
#   ⚠️ 接缝登记：并发 spec `soe-listed-note-conversion-correctness` 的
#   Task 12/13 计划填充其中 35 条 null。届时该 spec 需连带更新本基线并留证。
# --------------------------------------------------------------------------- #

import importlib.util

PARENT_FIELD = "parent_company_sections"
PARENT_SIDES = ("listed", "soe")

# 冻结基线：account_key -> [soe_standalone, soe_consolidated,
#                          listed_standalone, listed_consolidated, legacy_aliases]
# 取自 Task 10 落地前的 note_template_variant_matrix.json（git HEAD）。
_BASELINE_ORDER = (
    "soe_standalone",
    "soe_consolidated",
    "listed_standalone",
    "listed_consolidated",
)
_VARIANTS_BASELINE_JSON = """
{
    "huo_bi_zi_jin": ["八、1","八、1","五、1","五、1",{"soe_standalone":["五、1"],"soe_consolidated":["五、1"]}],
    "jiao_yi_xing_jin_rong_zi_chan": ["八、2","八、2","五、2","五、2",{"soe_standalone":["五、2"],"soe_consolidated":["五、2"]}],
    "yan_sheng_jin_rong_zi_chan": ["八、3","八、3","五、3","五、3",{"soe_standalone":["五、3"],"soe_consolidated":["五、3"]}],
    "ying_shou_piao_ju": ["八、4","八、4","五、4","五、4",{}],
    "ying_shou_zhang_kuan": ["八、5","八、5","五、5","五、5",{}],
    "ying_shou_kuan_xiang_rong_zi": ["八、6","八、6","五、6","五、6",{}],
    "yu_fu_kuan_xiang": ["八、7","八、7","五、7","五、7",{}],
    "ying_shou_zi_jin_ji_zhong_guan_li_kuan": ["八、8","八、8",null,null,{}],
    "qi_ta_ying_shou_kuan": ["八、9","八、9","五、8","五、8",{}],
    "cun_huo": ["八、10","八、10","五、9","五、9",{}],
    "he_tong_zi_chan": ["八、11","八、11","五、10","五、10",{}],
    "chi_you_dai_shou_zi_chan": ["八、12","八、12",null,null,{}],
    "yi_nian_nei_dao_qi_de_fei_liu_dong_zi_chan": ["八、13","八、13","五、12","五、12",{}],
    "qi_ta_liu_dong_zi_chan": ["八、14","八、14","五、13","五、13",{}],
    "zhai_quan_tou_zi": ["八、15","八、15","五、14","五、14",{}],
    "qi_ta_zhai_quan_tou_zi": ["八、16","八、16","五、15","五、15",{}],
    "chang_qi_ying_shou_kuan": ["八、17","八、17","五、16","五、16",{}],
    "chang_qi_gu_quan_tou_zi": ["八、18","八、18","五、18","五、18",{}],
    "qi_ta_quan_yi_gong_ju_tou_zi": ["八、19","八、19","五、19","五、19",{}],
    "qi_ta_fei_liu_dong_jin_rong_zi_chan": ["八、20","八、20","五、20","五、20",{}],
    "tou_zi_xing_fang_di_chan": ["八、21","八、21","五、21","五、21",{}],
    "gu_ding_zi_chan": ["八、22","八、22","五、22","五、22",{}],
    "zai_jian_gong_cheng": ["八、23","八、23","五、23","五、23",{}],
    "sheng_chan_xing_sheng_wu_zi_chan": ["八、24","八、24","五、24","五、24",{}],
    "you_qi_zi_chan": ["八、25","八、25",null,null,{}],
    "shi_yong_quan_zi_chan": ["八、26","八、26","五、25","五、25",{}],
    "wu_xing_zi_chan": ["八、27","八、27","五、26","五、26",{}],
    "kai_fa_zhi_chu": ["八、28","八、28","五、27","五、27",{}],
    "shang_yu": ["八、29","八、29","五、28","五、28",{}],
    "chang_qi_dai_tan_fei_yong": ["八、30","八、30","五、29","五、29",{}],
    "di_yan_suo_de_shui_zi_chan_he_di_yan_suo_de": ["八、31","八、31","五、30","五、30",{}],
    "qi_ta_fei_liu_dong_zi_chan": ["八、32","八、32","五、31","五、31",{}],
    "duan_qi_jie_kuan": ["八、33","八、33","五、33","五、33",{}],
    "jiao_yi_xing_jin_rong_fu_zhai": ["八、34","八、34","五、34","五、34",{}],
    "yan_sheng_jin_rong_fu_zhai": ["八、35","八、35","五、35","五、35",{}],
    "ying_fu_piao_ju": ["八、36","八、36","五、36","五、36",{}],
    "ying_fu_zhang_kuan": ["八、37","八、37","五、37","五、37",{}],
    "yu_shou_kuan_xiang": ["八、38","八、38","五、38","五、38",{}],
    "he_tong_fu_zhai": ["八、39","八、39","五、39","五、39",{}],
    "ying_fu_zhi_gong_xin_chou": ["八、40","八、40","五、40","五、40",{}],
    "ying_jiao_shui_fei": ["八、41","八、41","五、41","五、41",{}],
    "qi_ta_ying_fu_kuan": ["八、42","八、42","五、42","五、42",{}],
    "chi_you_dai_shou_fu_zhai": ["八、43","八、43",null,null,{}],
    "yi_nian_nei_dao_qi_de_fei_liu_dong_fu_zhai": ["八、44","八、44","五、43","五、43",{}],
    "yi_nian_nei_dao_qi_de_chang_qi_jie_kuan": ["八、45","八、45",null,null,{}],
    "yi_nian_nei_dao_qi_de_ying_fu_zhai_quan": ["八、46","八、46",null,null,{}],
    "yi_nian_nei_dao_qi_de_chang_qi_ying_fu_kuan": ["八、47","八、47",null,null,{}],
    "qi_ta_liu_dong_fu_zhai": ["八、48","八、48","五、44","五、44",{}],
    "chang_qi_jie_kuan": ["八、49","八、49","五、45","五、45",{}],
    "ying_fu_zhai_quan": ["八、50","八、50","五、46","五、46",{}],
    "you_xian_gu_yong_xu_zhai_deng_jin_rong_gong": ["八、51","八、51",null,null,{}],
    "zu_lin_fu_zhai": ["八、52","八、52","五、47","五、47",{}],
    "chang_qi_ying_fu_kuan": ["八、53","八、53","五、48","五、48",{}],
    "chang_qi_ying_fu_zhi_gong_xin_chou": ["八、54","八、54","五、49","五、49",{}],
    "yu_ji_fu_zhai": ["八、55","八、55","五、50","五、50",{}],
    "di_yan_shou_yi": ["八、56","八、56","五、51","五、51",{}],
    "qi_ta_fei_liu_dong_fu_zhai": ["八、57","八、57","五、52","五、52",{}],
    "shi_shou_zi_ben": ["八、58","八、58",null,null,{}],
    "qi_ta_quan_yi_gong_ju": ["八、59","八、59","五、54","五、54",{}],
    "zi_ben_gong_ji": ["八、60","八、60","五、55","五、55",{}],
    "zhuan_xiang_chu_bei": ["八、61","八、61","五、58","五、58",{}],
    "ying_yu_gong_ji": ["八、62","八、62","五、59","五、59",{}],
    "wei_fen_pei_li_run": ["八、63","八、63","五、61","五、61",{}],
    "ying_ye_shou_ru_ying_ye_cheng_ben": ["八、64","八、64","五、62","五、62",{}],
    "xiao_shou_fei_yong": ["八、65","八、65","五、64","五、64",{}],
    "guan_li_fei_yong": ["八、66","八、66","五、65","五、65",{}],
    "yan_fa_fei_yong": ["八、67","八、67","五、66","五、66",{}],
    "cai_wu_fei_yong": ["八、68","八、68","五、67","五、67",{}],
    "qi_ta_shou_yi": ["八、69","八、69","五、68","五、68",{}],
    "tou_zi_shou_yi_xia_biao_zhong_bu_shi_yong_d": ["八、70","八、70",null,null,{}],
    "jing_chang_kou_tao_qi_shou_yi": ["八、71","八、71","五、70","五、70",{}],
    "gong_yun_jia_zhi_bian_dong_shou_yi": ["八、72","八、72","三、公允价值变动收益","三、公允价值变动收益",{}],
    "xin_yong_jian_zhi_sun_shi": ["八、73","八、73","三、信用减值损失","三、信用减值损失",{}],
    "zi_chan_jian_zhi_sun_shi": ["八、74","八、74","三、资产减值损失（损","三、资产减值损失（损",{}],
    "zi_chan_chu_zhi_shou_yi": ["八、75","八、75","三、资产处置收益（损","三、资产处置收益（损",{}],
    "ying_ye_wai_shou_ru": ["八、76","八、76","三、营业外收入（注：","三、营业外收入（注：",{}],
    "ying_ye_wai_zhi_chu": ["八、77","八、77","三、营业外支出（注：","三、营业外支出（注：",{}],
    "suo_de_shui_fei_yong": ["八、78","八、78","三、所得税费用","三、所得税费用",{}],
    "gui_shu_yu_mu_gong_si_suo_you_zhe_de_qi_ta": ["八、79","八、79",null,null,{}],
    "mei_gu_shou_yi": ["八、80","八、80",null,null,{}],
    "xian_jin_liu_liang_biao_xiang_mu_zhu_shi": ["八、81","八、81","三、现金流量表项目注","三、现金流量表项目注",{}],
    "fei_huo_bi_xing_zi_chan_jiao_huan": ["八、82","八、82",null,null,{}],
    "gu_fen_zhi_fu": ["八、83","八、83",null,null,{}],
    "zhai_wu_chong_zu": ["八、84","八、84","三、债务重组【不适用","三、债务重组【不适用",{}],
    "jie_kuan_fei_yong": ["八、85","八、85","三、借款费用","三、借款费用",{}],
    "wai_bi_zhe_suan": ["八、86","八、86",null,null,{}],
    "zu_lin": ["八、87","八、87","五、74","五、74",{}],
    "zhong_zhi_jing_ying": ["八、89","八、89","十四、终止经营","十四、终止经营",{}],
    "fen_bu_xin_xi": ["八、90","八、90",null,null,{}],
    "he_bing_xian_jin_liu_liang_biao_xiang_guan": ["八、91","八、91",null,null,{}],
    "wai_bi_huo_bi_xing_xiang_mu": ["八、92","八、92","五、73","五、73",{}],
    "suo_you_quan_he_shi_yong_quan_shou_dao_xian": ["八、93","八、93","五、32","五、32",{}],
    "chi_you_dai_shou_zi_chan_he_chi_you_dai_sho": [null,null,"五、11","五、11",{}],
    "she_ding_shou_yi_ji_hua_jing_zi_chan": [null,null,"五、17","五、17",{}],
    "gu_ben": [null,null,"五、53","五、53",{}],
    "ku_cun_gu": [null,null,"五、56","五、56",{}],
    "qi_ta_zong_he_shou_yi": [null,null,"五、57","五、57",{}],
    "yi_ban_feng_xian_zhun_bei": ["八、94","八、94","五、60","五、60",{}],
    "shui_jin_ji_fu_jia": [null,null,"五、63","五、63",{}],
    "tou_zi_shou_yi": [null,null,"五、69","五、69",{}],
    "xian_jin_liu_liang_biao_bu_chong_zi_liao": [null,null,"五、71","五、71",{}],
    "gu_dong_quan_yi_bian_dong_biao_xiang_mu_zhu": [null,null,"五、72","五、72",{}]
}
"""
VARIANTS_BASELINE: dict[str, list] = json.loads(_VARIANTS_BASELINE_JSON)


def _canon(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


@pytest.fixture(scope="module")
def fix_script():
    """加载幂等脚本，复用其**声明式常量**（章节标题集 / 标题别名表）作单一真源.

    只取常量，遍历与断言由本守卫独立实现 —— 否则脚本自身的派生 bug 无从暴露。
    """
    path = REPO_ROOT / "backend" / "scripts" / "fix" / "fix_variant_matrix_parent_sections.py"
    assert path.exists(), f"fix script missing: {path}"
    spec = importlib.util.spec_from_file_location("fix_variant_matrix_parent_sections", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def parent_subsections(fix_script) -> dict[str, dict[str, str]]:
    """独立遍历两份模板 JSON，取母公司章 level-2 子节 {side: {title: section_number}}."""
    out: dict[str, dict[str, str]] = {}
    for side in PARENT_SIDES:
        doc = json.loads((DATA / f"note_template_{side}.json").read_text(encoding="utf-8"))
        sections = doc["sections"]
        chapters = [
            s
            for s in sections
            if s.get("level") == 1
            and s.get("section_title") in fix_script.CHAPTER_TITLES[side]
        ]
        assert len(chapters) == 1, (
            f"{side}: expected exactly 1 parent-company chapter, got "
            f"{[c.get('section_title') for c in chapters]}"
        )
        sid = chapters[0]["section_id"]
        subs = {
            s["section_title"]: s["section_number"]
            for s in sections
            if s.get("parent_section_id") == sid
        }
        assert subs, f"{side}: parent-company chapter has no level-2 subsections"
        out[side] = subs
    return out


@pytest.fixture(scope="module")
def expected_parent_accounts(
    matrix: dict, parent_subsections: dict[str, dict[str, str]], fix_script
) -> dict[str, dict[str, str]]:
    """{account_key: {side: section_number}}，缺落点的侧不出现该键."""
    by_title: dict[str, list[str]] = {}
    for a in matrix["accounts"]:
        by_title.setdefault(a["section_title"], []).append(a["account_key"])
    out: dict[str, dict[str, str]] = {}
    for side in PARENT_SIDES:
        for title, number in parent_subsections[side].items():
            match_title = fix_script.SECTION_TITLE_ALIASES.get(title, title)
            hits = by_title.get(match_title, [])
            assert len(hits) == 1, (
                f"{side} subsection {title!r} -> matrix title {match_title!r}: "
                f"expected exactly 1 account, got {hits}"
            )
            out.setdefault(hits[0], {})[side] = number
    return out


# --- additive / 零回归 ------------------------------------------------------ #


def test_parent_sections_baseline_covers_all_accounts(matrix: dict) -> None:
    """冻结基线必须与当前 102 个 account_key 完全对齐（防基线失效空转）."""
    keys = [a["account_key"] for a in matrix["accounts"]]
    assert len(keys) == 102, f"account count changed: {len(keys)}"
    assert set(keys) == set(VARIANTS_BASELINE), (
        f"baseline out of sync: only-in-matrix={sorted(set(keys) - set(VARIANTS_BASELINE))} "
        f"only-in-baseline={sorted(set(VARIANTS_BASELINE) - set(keys))}"
    )


def test_parent_sections_additive_variants_unchanged(matrix: dict) -> None:
    """Property 19 / R10.4：102 个 account 的 variants 与 legacy_aliases 逐字不变.

    双重比对：`==` 结构相等 + `json.dumps(sort_keys=True)` 规范化字符串相等。
    """
    bad: list[str] = []
    for acct in matrix["accounts"]:
        key = acct["account_key"]
        row = VARIANTS_BASELINE[key]
        want_variants = {vk: row[i] for i, vk in enumerate(_BASELINE_ORDER)}
        want_aliases = row[4]
        if acct["variants"] != want_variants:
            bad.append(f"{key}.variants eq-mismatch: {acct['variants']} != {want_variants}")
        if _canon(acct["variants"]) != _canon(want_variants):
            bad.append(f"{key}.variants canon-mismatch")
        if acct.get("legacy_aliases") != want_aliases:
            bad.append(f"{key}.legacy_aliases eq-mismatch")
        if _canon(acct.get("legacy_aliases")) != _canon(want_aliases):
            bad.append(f"{key}.legacy_aliases canon-mismatch")
    assert not bad, "variant_matrix regression (must stay byte-identical):\n" + "\n".join(bad[:12])


def test_parent_sections_no_fifth_variant_key(matrix: dict) -> None:
    """不新增变体键：variants 恒为 4 键且键序不变."""
    bad = [
        (a["account_key"], list(a["variants"].keys()))
        for a in matrix["accounts"]
        if tuple(a["variants"].keys()) != _BASELINE_ORDER
    ]
    assert not bad, f"variants key set/order changed: {bad[:5]}"


def test_parent_sections_no_unexpected_top_level_keys(matrix: dict) -> None:
    """account 条目只许出现既有 4 键 + parent_company_sections."""
    allowed = {"account_key", "section_title", "variants", "legacy_aliases", PARENT_FIELD}
    bad = [
        (a["account_key"], sorted(set(a) - allowed))
        for a in matrix["accounts"]
        if set(a) - allowed
    ]
    assert not bad, f"unexpected account keys: {bad[:5]}"


# --- 母公司维度：正反双向 --------------------------------------------------- #


def test_parent_sections_present_on_exactly_parent_chapter_accounts(
    matrix: dict, expected_parent_accounts: dict[str, dict[str, str]]
) -> None:
    """正反双向：该出现的都有、不该出现的都没有."""
    actual = {a["account_key"] for a in matrix["accounts"] if PARENT_FIELD in a}
    expected = set(expected_parent_accounts)
    assert expected, "template-derived parent-company account set is empty (fixture broken)"
    assert actual == expected, (
        f"missing={sorted(expected - actual)} unexpected={sorted(actual - expected)}"
    )


def test_parent_sections_values_match_template_subsections(
    matrix: dict, expected_parent_accounts: dict[str, dict[str, str]]
) -> None:
    """取值逐字等于模板派生真值（含 md 截断值），且键集与模板落点一致."""
    by_key = {a["account_key"]: a for a in matrix["accounts"]}
    bad: list[str] = []
    for key, want in expected_parent_accounts.items():
        got = by_key[key].get(PARENT_FIELD)
        if got != want:
            bad.append(f"{key}: {got} != {want}")
    assert not bad, "parent_company_sections mismatch:\n" + "\n".join(bad)


def test_parent_sections_values_resolvable_in_templates(
    matrix: dict, parent_subsections: dict[str, dict[str, str]]
) -> None:
    """交叉锁死：每个章节号必须能在对应模板 JSON 的母公司章子节里查到.

    禁把测试内的字面量当唯一真源 —— 真源是 note_template_{listed,soe}.json。
    """
    valid = {side: set(subs.values()) for side, subs in parent_subsections.items()}
    bad: list[str] = []
    for acct in matrix["accounts"]:
        pcs = acct.get(PARENT_FIELD)
        if not pcs:
            continue
        for side, number in pcs.items():
            if side not in PARENT_SIDES:
                bad.append(f"{acct['account_key']}: unknown side {side!r}")
                continue
            if not isinstance(number, str) or not number.strip():
                bad.append(f"{acct['account_key']}.{side}: empty/non-str value {number!r}")
                continue
            if number not in valid[side]:
                bad.append(
                    f"{acct['account_key']}.{side}: {number!r} not a parent-company "
                    f"subsection number in note_template_{side}.json"
                )
    assert not bad, "\n".join(bad)


def test_parent_sections_asymmetry_preserved(
    matrix: dict, parent_subsections: dict[str, dict[str, str]]
) -> None:
    """两版子节集合不对称，禁对齐成相等（Property 3 在本字段上的投影）.

    listed 母公司章独有「应收票据」、soe 独有「现金流量表补充资料」
    ⇒ 至少一条 account 只有 listed 键、至少一条只有 soe 键。
    """
    listed_titles = set(parent_subsections["listed"])
    soe_titles = set(parent_subsections["soe"])
    assert listed_titles != soe_titles, "templates became symmetric (must not be aligned)"
    assert "应收票据" in listed_titles - soe_titles
    assert "现金流量表补充资料" in soe_titles - listed_titles

    only_listed = [
        a["account_key"]
        for a in matrix["accounts"]
        if set((a.get(PARENT_FIELD) or {})) == {"listed"}
    ]
    only_soe = [
        a["account_key"]
        for a in matrix["accounts"]
        if set((a.get(PARENT_FIELD) or {})) == {"soe"}
    ]
    assert only_listed, "no account carries a listed-only parent_company_sections"
    assert only_soe, "no account carries a soe-only parent_company_sections"
    assert "ying_shou_piao_ju" in only_listed, only_listed
    assert "xian_jin_liu_liang_biao_bu_chong_zi_liao" in only_soe, only_soe


def test_parent_sections_no_null_values(matrix: dict) -> None:
    """缺落点必须表现为「键缺失」，不得写 null（否则与「有落点」不可区分）."""
    bad = [
        (a["account_key"], k)
        for a in matrix["accounts"]
        for k, v in (a.get(PARENT_FIELD) or {}).items()
        if v is None
    ]
    assert not bad, f"null values in {PARENT_FIELD}: {bad}"


def test_parent_sections_script_check_is_clean(fix_script) -> None:
    """幂等脚本的判据与落盘数据一致：build_plan 无待办变更."""
    raw = MATRIX_PATH.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    expected = fix_script.build_expected(doc["accounts"])
    _new_doc, changes = fix_script.build_plan(doc, expected)
    assert not changes, f"fix script still has pending changes: {changes}"


def test_parent_sections_serializer_round_trips(fix_script) -> None:
    """round-trip 自检：脚本的序列化器逐字节复现磁盘原文（防全文件重排）."""
    raw = MATRIX_PATH.read_bytes()
    assert fix_script.serialize(json.loads(raw.decode("utf-8"))) == raw


# --------------------------------------------------------------------------- #
# Task 10 追加断言（与上方同 Task 的守卫**不重复**，只补它没覆盖的四件事）
#
# 上方守卫已覆盖：102 科目 variants/legacy_aliases 冻结基线、字段作用域正反双向、
# 取值可在模板定位、两版不对称、脚本 build_plan 0 欠账、序列化 round-trip。
# 下面补的是：
#   A. 冻结字面锚点 —— 上方的期望值是从「脚本常量 + 模板」派生的，若两者一起
#      漂移（例如有人改了子节标题并同步改了脚本别名表）会静默跟随；一份独立
#      冻结的字面量能把这种"共同漂移"打红。
#   B. 「母公司侧有落点、合并侧 variants 为 null」的两个科目逐条登记裁决理由 ——
#      该字段与 `variants` **相互独立**，不得断言「母公司侧非空 ⇒ 合并侧非空」。
#   C. md 重建截断值双向锁死（矩阵存截断值 / 模板该子节 title 是完整值）。
#   D. 生成器 `build_variant_matrix.py --write` 不得抹掉该 additive 字段
#      —— 它从 section_code_index.json 全量重建矩阵，不搬这个字段就等于
#      「重生成一次，母公司维度静默消失」。
#
# 非空转证据不写在本文件内（替身自检），而由外部变异检验提供：对真实数据/真实
# 源码逐条做一处变异 → 上方与本节断言必须打红 → 再无条件还原（.bak + finally +
# 还原后 md5 校验）。7 个变异（删字段 / 改 variants 取值 / 指向不存在章节 /
# 两版对称化 / 生成器不调 carry-over / 截断值改完整值 / ADDITIVE 清单清空）
# 实测全部打红。
#
# 上方 `VARIANTS_BASELINE` 若因**有意裁决**需要更新，用只读工具重算并留证：
#   python backend/scripts/diagnose/audit_variant_matrix_snapshot.py --diff-head
# --------------------------------------------------------------------------- #

T10_BUILDER_PATH = REPO_ROOT / "backend" / "scripts" / "build_variant_matrix.py"

# A. 冻结字面锚点（取值 = 模板 level-2 子节的 section_number 真值，含 md 截断）
T10_EXPECTED_PARENT_SECTIONS: dict[str, dict[str, str]] = {
    "ying_shou_piao_ju": {"listed": "十六、应收票据"},
    "ying_shou_zhang_kuan": {"listed": "十六、应收账款", "soe": "十二、应收账款"},
    "qi_ta_ying_shou_kuan": {"listed": "十六、其他应收款", "soe": "十二、其他应收款"},
    "chang_qi_gu_quan_tou_zi": {"listed": "十六、长期股权投资", "soe": "十二、长期股权投资"},
    "ying_ye_shou_ru_ying_ye_cheng_ben": {
        "listed": "十六、营业收入与营业成本",
        "soe": "十二、营业收入与营业成本",
    },
    "tou_zi_shou_yi": {"listed": "十六、投资收益（注：以", "soe": "十二、投资收益"},
    "xian_jin_liu_liang_biao_bu_chong_zi_liao": {"soe": "十二、现金流量表补充资"},
}

# B. 母公司侧有落点、但该侧合并章 variants 为 null 的科目 → 逐条登记裁决理由
T10_PARENT_SIDE_WITHOUT_MERGED: dict[str, str] = {
    "tou_zi_shou_yi": (
        "投资收益在矩阵里被拆成两个科目：本科目（listed 五、69）与 "
        "tou_zi_shou_yi_xia_biao_zhong_bu_shi_yong_d（soe 八、70）。成因是 "
        "build_variant_matrix.normalize_title 只剥【】符号不剥括注文本，"
        "「投资收益【下表中不适用的项目，删除】」与「投资收益」归一后不相等 ⇒ "
        "两者未配对（既有矩阵缺陷；本 spec 不改 variants 故不修）。soe 母公司章"
        "子节标题是无编者注的「投资收益」，按 section_title 精确匹配落到本科目，"
        "因此本科目 soe 侧有母公司落点而 soe 合并侧为 null。"
    ),
    "xian_jin_liu_liang_biao_bu_chong_zi_liao": (
        "soe 合并章（八）实测无「现金流量表补充资料」子节（只有 八、81 现金流量表"
        "项目注释 与 八、91 合并现金流量表相关事项）⇒ variants.soe_* 为 null；"
        "而 soe 母公司章确有独立子节「十二、现金流量表补充资料」，listed 母公司章"
        "反而没有 —— 这正是两版不对称的实证之一（requirements 1.3）。"
    ),
}

# C. md 重建截断的 section_number → 该子节完整 section_title
T10_MD_TRUNCATED_NUMBERS: dict[tuple[str, str], str] = {
    ("listed", "十六、投资收益（注：以"): "投资收益",
    ("soe", "十二、现金流量表补充资"): "现金流量表补充资料",
}


def test_t10_expected_parent_sections_frozen_anchor(
    expected_parent_accounts: dict[str, dict[str, str]]
) -> None:
    """A：模板+脚本派生的期望值必须等于独立冻结的字面锚点（防两者共同漂移）."""
    assert expected_parent_accounts == T10_EXPECTED_PARENT_SECTIONS, (
        "template/script-derived expectation drifted away from the frozen anchor:\n"
        f"  derived={_canon(expected_parent_accounts)}\n"
        f"  frozen ={_canon(T10_EXPECTED_PARENT_SECTIONS)}\n"
        "If a source-template subsection was genuinely renamed, update BOTH the anchor "
        "and the spec Notes, and say why. Do not delete this assertion."
    )
    sides = [s for v in T10_EXPECTED_PARENT_SECTIONS.values() for s in v]
    assert sides.count("listed") == 6 and sides.count("soe") == 6, (
        f"each side must cover its 6 parent-chapter subsections, got {sides}"
    )


def test_t10_parent_side_without_merged_side_is_registered(matrix: dict) -> None:
    """B：`parent_company_sections` 与 `variants` 相互独立，两个例外逐条登记理由."""
    actual = {
        a["account_key"]
        for a in matrix["accounts"]
        for side in (a.get(PARENT_FIELD) or {})
        if not a["variants"].get(f"{side}_standalone")
    }
    assert actual == set(T10_PARENT_SIDE_WITHOUT_MERGED), (
        "the 'parent side present but merged side is null' set drifted: "
        f"actual={sorted(actual)} registered={sorted(T10_PARENT_SIDE_WITHOUT_MERGED)}"
    )
    for key, reason in T10_PARENT_SIDE_WITHOUT_MERGED.items():
        assert len(reason.strip()) >= 60, f"{key}: reason too short to be evidence"
        assert "、" in reason, f"{key}: reason must cite a concrete section number"


def test_t10_md_truncated_section_numbers_double_locked(
    parent_subsections: dict[str, dict[str, str]]
) -> None:
    """C：矩阵存截断值 / 模板该子节 title 是完整值；上游修好截断即打红."""
    for (side, truncated), full_title in T10_MD_TRUNCATED_NUMBERS.items():
        subs = parent_subsections[side]
        owners = [title for title, number in subs.items() if number == truncated]
        assert owners == [full_title], (
            f"{side}: section_number {truncated!r} is owned by {owners} "
            f"(expected exactly [{full_title!r}])"
        )
        prefix = truncated.split("、")[0]
        assert truncated != f"{prefix}、{full_title}", (
            f"{side}: {truncated!r} is no longer truncated - the md-rebuild truncation was "
            "fixed upstream. Re-run fix_variant_matrix_parent_sections.py --apply and "
            "update T10_MD_TRUNCATED_NUMBERS."
        )
    stored = {
        (side, number)
        for a in json.loads(MATRIX_PATH.read_text(encoding="utf-8"))["accounts"]
        for side, number in (a.get(PARENT_FIELD) or {}).items()
    }
    for pair in T10_MD_TRUNCATED_NUMBERS:
        assert pair in stored, (
            f"matrix no longer stores the truncated literal {pair} - somebody 'fixed' the "
            "value by hand; downstream locates sections by the template literal."
        )


def test_t10_builder_additive_field_registry_and_noop() -> None:
    """D：生成器侧只补下方 `test_parent_sections_survive_matrix_regeneration` 没覆盖的两点.

    那条已断言「carry-over 存在 + main() 真的调用 + 母公司科目被搬 / 非母公司科目不被搬」。
    这里只补：
      1. 字段已登记进 `ADDITIVE_ACCOUNT_FIELDS`（清单漏一项 = 该字段静默不被搬，
         而 carry-over 函数本身仍在 → 上面那条断言照样绿）；
      2. `existing=None`（首次生成、磁盘尚无输出）时必须原样返回，不得凭空造字段。
    """
    assert T10_BUILDER_PATH.exists(), f"builder missing: {T10_BUILDER_PATH}"
    spec = importlib.util.spec_from_file_location("_t10_build_variant_matrix", T10_BUILDER_PATH)
    assert spec and spec.loader
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)

    assert PARENT_FIELD in getattr(builder, "ADDITIVE_ACCOUNT_FIELDS", ()), (
        f"{PARENT_FIELD} is not registered in ADDITIVE_ACCOUNT_FIELDS -> regeneration "
        "drops it even though carry_over_additive_fields() exists and is called"
    )
    assert PARENT_FIELD not in builder.carry_over_additive_fields(
        {"accounts": [{"account_key": "ying_shou_piao_ju"}]}, None
    )["accounts"][0], "carry-over must be a no-op when there is no existing output"


def test_parent_sections_survive_matrix_regeneration() -> None:
    """生成器重跑不得抹掉 additive 字段（否则 --write 一次即静默丢失该维度）.

    `note_template_variant_matrix.json` 由 `backend/scripts/build_variant_matrix.py`
    从 `section_code_index.json` 生成，而 index 里没有母公司章 ⇒ 朴素重生成会把
    `parent_company_sections` 整批抹掉。故要求生成器暴露 carry-over 并**真的调用**
    （只写函数不接线 = 又一个死代码）。
    """
    builder = REPO_ROOT / "backend" / "scripts" / "build_variant_matrix.py"
    assert builder.exists(), f"builder missing: {builder}"
    src = builder.read_text(encoding="utf-8")
    assert "def carry_over_additive_fields(" in src, (
        "build_variant_matrix.py must expose carry_over_additive_fields(); without it a "
        "regeneration silently drops parent_company_sections"
    )
    assert "def main(" in src, "builder has no main()"
    main_body = src.split("def main(", 1)[1]
    assert "carry_over_additive_fields(" in main_body, (
        "build_variant_matrix.main() does not call carry_over_additive_fields() "
        "-> the function is dead code and regeneration still drops the field"
    )

    spec = importlib.util.spec_from_file_location("_build_variant_matrix_guard", builder)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    existing = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    fresh = {
        "accounts": [
            {"account_key": "ying_shou_piao_ju", "variants": {}, "legacy_aliases": {}},
            {"account_key": "huo_bi_zi_jin", "variants": {}, "legacy_aliases": {}},
        ]
    }
    merged = mod.carry_over_additive_fields(fresh, existing)
    got = {a["account_key"]: a.get(PARENT_FIELD) for a in merged["accounts"]}
    assert got["ying_shou_piao_ju"] == {"listed": "十六、应收票据"}, got
    assert got["huo_bi_zi_jin"] is None, "carried the field onto a non-parent account"
