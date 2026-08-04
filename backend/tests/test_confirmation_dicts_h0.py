"""test_confirmation_dicts_h0.py — H0 函证枚举与源模板数据验证交叉锁死.

spec: h0-confirmation-source-fidelity-and-linkage
  Requirements 1.2 / 1.6 / 7.1 / 7.4 / 7.5 / 7.6 / 7.7 / 12.1 / 12.2
  Property 1 / 19 / 21 / 30

裁决者 = 源模板 xlsx（`backend/wp_templates/H/H0 固定资产循环函证.xlsx`）。

🔴 判定数据验证（DV）必须用 ``coord in dv.sqref`` 逐格测试 ——
openpyxl 打印 ``dv.sqref`` 时会带出 ``JF/JK/TG/ACX`` 等远端列范围，那是 Excel
列重复产生的残留 sqref，**不落在真实列上**。若照打印顺序取第一个 sqref，
会得出「H0-1 的 G 列（函证方式）DV = 跟函/邮寄/电邮/其他」这类错误结论
（实测 H0-1 真实 DV 只有 C / L / N / X 四列）。
"""
from __future__ import annotations

import json
from pathlib import Path

import openpyxl
import pytest

from app.routers.system_dicts import _DICTS

_REPO_ROOT = Path(__file__).resolve().parents[2]
H0_XLSX = _REPO_ROOT / "backend" / "wp_templates" / "H" / "H0 固定资产循环函证.xlsx"
WP_SYSTEM_MAP = _REPO_ROOT / "backend" / "data" / "wp_system_map.json"

# H 循环 9 个函证品种（「资产处置损益」= H10 损益类不函证，故排除）
H_CYCLE_CONFIRM_CATEGORIES = [
    "固定资产",
    "在建工程",
    "投资性房地产",
    "工程物资",
    "油气资产",
    "固定资产清理",
    "生产性生物资产",
    "使用权资产",
    "租赁负债",
]


# ─── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def wb():
    if not H0_XLSX.exists():
        pytest.fail(f"源模板不存在，无法裁决: {H0_XLSX}")
    return openpyxl.load_workbook(H0_XLSX)


def dv_of(ws, coord: str) -> list[str]:
    """返回覆盖 ``coord`` 的全部 DV 的 formula1（逐格判定，忽略镜像列 sqref）."""
    return [dv.formula1 for dv in ws.data_validations.dataValidation if coord in dv.sqref]


def dv_options(ws, coord: str) -> list[str]:
    """把该格的 list 型 DV 拆成选项列表（源模板取值逐字，不做 strip）."""
    hits = dv_of(ws, coord)
    assert len(hits) == 1, f"{ws.title}!{coord} 期望恰好一个 DV，实得 {hits!r}"
    raw = hits[0]
    assert raw.startswith('"') and raw.endswith('"'), f"{coord} DV 非内联清单: {raw!r}"
    return raw[1:-1].split(",")


def labels(dict_key: str) -> list[str]:
    return [e["label"] for e in _DICTS[dict_key]]


# ─── Property 19: 四组枚举取值与源模板 DV 逐字一致 ──────────────────────────


def test_send_channel_matches_source_dv(wb):
    """发函渠道 = H0-2!C7 的 DV，逐字."""
    opts = dv_options(wb["核实被函证单位信息H0-2"], "C7")
    assert opts == ["邮寄", "跟函", "电子函证", "其他"]
    assert labels("confirmation_send_channel") == opts


def test_sample_purpose_matches_source_dv(wb):
    """选取样本目的 = H0-1!C8 的 DV，逐字（含空格/标点不一致原样保留）."""
    opts = dv_options(wb["函证结果汇总表H0-1"], "C8")
    assert opts == ["A. 大额", "B.异常", "C.余额为0", "D.账龄长", "E.随机"]
    # 🔴 源模板首项带空格、其余不带 —— 不得「顺手统一」
    assert opts[0] == "A. 大额" and opts[1] == "B.异常"
    assert labels("confirmation_sample_purpose") == opts


def test_addr_verify_matches_source_dv(wb):
    """地址不一致的核实方式 = H0-2!L7 的 DV，逐字."""
    opts = dv_options(wb["核实被函证单位信息H0-2"], "L7")
    assert opts == [
        "发票/合同地址核实",
        "电话核实",
        "官网/公告查询",
        "地图查询",
        "邮件确认",
        "其他方式",
    ]
    assert labels("confirmation_addr_verify") == opts


def test_reply_method_covers_source_dv(wb):
    """回函方式字典须覆盖源模板两处 DV 的全部取值.

    H0-2!P7 = 纸质原件/电子函证/其他介质（回函介质）
    H0-6!D7 = 传真/电子邮件（仅电子回函两种）
    """
    p7 = dv_options(wb["核实被函证单位信息H0-2"], "P7")
    d7 = dv_options(wb["邮件传真回函可靠性验证H0-6"], "D7")
    assert p7 == ["纸质原件", "电子函证", "其他介质"]
    assert d7 == ["传真", "电子邮件"]

    dict_labels = set(labels("confirmation_reply_method"))
    missing = (set(p7) | set(d7)) - dict_labels
    assert not missing, f"confirmation_reply_method 缺源模板取值: {sorted(missing)}"


def test_yes_no_columns_use_yes_no_dv(wb):
    """H0-1 的是否类列（L/N/X）DV 为「是,否」——与 yes_no 字典一致."""
    ws = wb["函证结果汇总表H0-1"]
    for coord in ("L8", "N8", "X8"):
        assert dv_options(ws, coord) == ["是", "否"], coord
    assert labels("yes_no") == ["是", "否"]


# ─── Property 19 反向自检：镜像列 sqref 不得被采信 ──────────────────────────


def test_mirror_column_sqref_must_not_be_trusted(wb):
    """反向自检：H0-1 的 G 列（函证方式）在源模板里**没有** DV.

    openpyxl 打印的 DV 列表中存在 formula1="跟函,邮寄,电邮,其他" 的条目，
    但其 sqref 只落在 JK/TG/ADC 等镜像列上。若守卫按打印顺序取值，
    会误判「H0-1!G 列 DV = 跟函/邮寄/电邮/其他」并据此把发函渠道写成那四项
    （注意顺序与真实的 H0-2!C7「邮寄,跟函,电子函证,其他」都不同）。
    """
    ws = wb["函证结果汇总表H0-1"]
    assert dv_of(ws, "G8") == [], "H0-1!G8 不应有 DV（真实渠道枚举在 H0-2!C7）"
    assert dv_of(ws, "M8") == [], "H0-1!M8 不应有 DV（真实回函方式枚举在 H0-2!P7）"

    # 该镜像 DV 确实存在于文件中（证明本自检不是空转）
    all_formulas = {dv.formula1 for dv in ws.data_validations.dataValidation}
    assert '"跟函,邮寄,电邮,其他"' in all_formulas, (
        "源模板里应存在这条只落在镜像列上的 DV；若它消失，本自检失去意义需重写"
    )


# ─── Property 2 / 30: H 类品种与 wp_system_map 逐字一致 ─────────────────────


def test_h_categories_match_wp_system_map():
    """9 个 H 类品种标签逐字取自 wp_system_map.json，不得自拟简称."""
    data = json.loads(WP_SYSTEM_MAP.read_text(encoding="utf-8"))
    cycles = [c for c in data["business_cycles"] if c.get("name") == "固定资产循环"]
    assert len(cycles) == 1, "wp_system_map.json 应恰有一个「固定资产循环」"
    accounts = cycles[0]["accounts"].split("/")

    # 源真相 10 项；函证品种 = 前 9 项（资产处置损益是损益类不函证）
    assert accounts == H_CYCLE_CONFIRM_CATEGORIES + ["资产处置损益"], accounts


@pytest.mark.parametrize("dict_key", ["confirmation_account_type", "confirmation_subject"])
def test_h_categories_present_in_dict(dict_key: str):
    """两个品种字典均含 9 项 H 类科目（H0-1 上区列 / H0-4 差异表列）."""
    dict_labels = set(labels(dict_key))
    missing = set(H_CYCLE_CONFIRM_CATEGORIES) - dict_labels
    assert not missing, f"{dict_key} 缺 H 类品种: {sorted(missing)}"


def test_h_categories_labels_identical_across_two_dicts():
    """同一份品种在两个字典中的标签必须逐字一致（防漂移）."""
    a = [l for l in labels("confirmation_account_type") if l in H_CYCLE_CONFIRM_CATEGORIES]
    b = [l for l in labels("confirmation_subject") if l in H_CYCLE_CONFIRM_CATEGORIES]
    assert a == b == H_CYCLE_CONFIRM_CATEGORIES


# ─── Property 21: additive（既有取值为新列表前缀） ─────────────────────────

# 改造前基线（2026-08-04 实测，`git show HEAD:` 可复核）
_PRE_CHANGE_BASELINE: dict[str, list[str]] = {
    "confirmation_account_type": [
        "应收账款", "合同负债", "其他应收款", "预付账款", "应付账款", "其他应付款",
        "短期借款", "长期借款", "银行存款", "定期存款", "理财产品", "其他货币资金",
    ],
    "confirmation_reply_method": ["原件寄回", "传真", "电子邮件", "当面确认"],
    "confirmation_subject": [
        "应收账款", "合同负债", "销售收入", "应收票据", "合同资产", "预付账款",
        "应付账款", "预收账款", "其他应收款", "其他应付款", "银行存款",
        "短期借款", "长期借款",
    ],
}


@pytest.mark.parametrize("dict_key", sorted(_PRE_CHANGE_BASELINE))
def test_dict_change_is_additive(dict_key: str):
    """既有取值必须是新列表的前缀 —— 只许追加，不许改序/改值/删除.

    例外：``confirmation_account_type`` 的「其他」是兜底项，源模板语义上应排末位，
    故 H 类 9 项插在它之前 → 基线是「去掉末尾『其他』后的前缀」。
    """
    current = labels(dict_key)
    baseline = _PRE_CHANGE_BASELINE[dict_key]
    assert current[: len(baseline)] == baseline, (
        f"{dict_key} 既有取值被改动（非 additive）：\n"
        f"  基线前缀 = {baseline}\n"
        f"  实际前缀 = {current[: len(baseline)]}"
    )
    if dict_key == "confirmation_account_type":
        assert current[-1] == "其他", "兜底项「其他」应保持末位"


def test_confirmation_method_untouched():
    """积极式/消极式枚举必须原样保留（R7.3）."""
    assert labels("confirmation_method") == ["积极式", "消极式"]


def test_all_dict_values_unique():
    """新增/追加后各字典内 value 仍唯一."""
    for key in (
        "confirmation_account_type",
        "confirmation_subject",
        "confirmation_reply_method",
        "confirmation_send_channel",
        "confirmation_sample_purpose",
        "confirmation_addr_verify",
    ):
        values = [e["value"] for e in _DICTS[key]]
        assert len(values) == len(set(values)), f"{key} value 重复: {values}"
