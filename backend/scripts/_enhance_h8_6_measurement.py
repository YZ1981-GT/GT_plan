# -*- coding: utf-8 -*-
"""Enhance H8-6 使用权资产/租赁负债初始及后续计量（按年 / 按月）Excel template.

源模板问题（对照致同底稿 + 公式审计）：
1. Sheet/标题笔误：「租赁负责」应为「租赁负债」
2. 审计目标偏笼统（存在/完整性），未突出 CAS21 初始计量与摊余成本/折旧
3. 按年：审计过程区几乎空白；结论无勾选模板；C20 用 E20=1 判断期初付款脆弱
4. 按年：折现率 H9 与增量借款利率 G9 未联动；折旧期未提示 min(租赁期,使用寿命)
5. 按月：E22 折现用年利率 POWER(1+r,n)，与后续行 POWER(1+r/12,n) 不一致（公式缺陷）
6. 按月：J22 累计折旧首月空白；审计说明编号 1/1/3 错乱；缺资产名称录入格
7. 两表未说明选用边界（按年适合简单固定年付；按月适合长租/月结）及勾稽关系
8. 递延所得税按账面余额×税率的简化处理未提示与税会差异政策相关

改进：
- 修正「负责→负债」标题与目录
- 强化审计目标/过程/结论与编制提示
- 修复按月 E22、J22；加固按年 C20；H9 联动 G9
- 补按月资产名称录入、月利率口径说明、两表勾稽提示
- 关键关键注释（不改动示例租金现金流主链，避免破坏已有示例）
"""
from __future__ import annotations

from pathlib import Path

import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(r"D:/GT_plan")
TARGETS = [ROOT / "backend" / "wp_templates" / "H" / "H8 使用权资产.xlsx"]
base = ROOT / "基础数据"
if base.exists():
    for p in base.rglob("H8 使用权资产.xlsx"):
        if p not in TARGETS and "_H8" not in p.name:
            TARGETS.append(p)

SHEET_ANN = "使用权资产 租赁负责初始及后续计量（按年）H8-6"
SHEET_MON = "使用权资产 租赁负责初始及后续计量（按月）H8-6"
SHEET_ANN_NEW = "使用权资产 租赁负债初始及后续计量（按年）H8-6"
SHEET_MON_NEW = "使用权资产 租赁负债初始及后续计量（按月）H8-6"
SHEET_CAT = "底稿目录"

OBJ_FONT = Font(size=10)
GUIDE_FONT = Font(color="0563C1", size=9)
TITLE_NOTE = Font(size=9, color="833C0C")
FIX_FONT = Font(size=9, color="C00000")
LEFT_WRAP = Alignment(wrap_text=True, vertical="center", horizontal="left")
NOTE_FILL = PatternFill("solid", fgColor="FFF8E7")
OK_FILL = PatternFill("solid", fgColor="E2EFDA")


def _set(ws, addr: str, value, font=None, fill=None) -> None:
    ws[addr] = value
    if font:
        ws[addr].font = font
    if fill:
        ws[addr].fill = fill
    ws[addr].alignment = LEFT_WRAP


def _comment(ws, addr: str, text: str, width: int = 260, height: int = 70) -> None:
    try:
        ws[addr].comment = Comment(text, "H8-6", width=width, height=height)
    except Exception:
        pass


def _fix_title_typo(text: str | None) -> str | None:
    if text is None:
        return None
    if not isinstance(text, str):
        return text
    return text.replace("租赁负责", "租赁负债")


def enhance_catalog(ws) -> None:
    for row in ws.iter_rows(max_row=min(80, ws.max_row or 1), max_col=8):
        for cell in row:
            if isinstance(cell.value, str) and "租赁负责" in cell.value:
                cell.value = _fix_title_typo(cell.value)


def enhance_annual(ws) -> None:
    # 标题
    if isinstance(ws["A2"].value, str):
        ws["A2"] = _fix_title_typo(ws["A2"].value)

    # 审计目标：突出计量准确性
    _set(
        ws,
        "A5",
        "一、审计目标：确认使用权资产与租赁负债按 CAS21 以恰当金额初始确认并后续计量；"
        "初始计量：使用权资产=租赁付款额现值(未付部分)+租赁期开始日或之前支付的租赁付款额"
        "+初始直接费用+预计复原成本−租赁激励；租赁负债=尚未支付的租赁付款额按增量借款利率/内含利率折现；"
        "后续：负债按实际利率法摊余成本，资产按直线法(或其他系统合理方法)折旧，折旧期=min(租赁期,使用寿命)"
        "（能合理确定取得所有权时取使用寿命）；相关递延所得税与披露恰当。",
        OBJ_FONT,
    )

    # 审计过程
    _set(
        ws,
        "A6",
        "二、审计过程：①核对合同/H8-4识别结论与H8-5租赁期（含续租/终止选择权）；"
        "②复核折现率（优先合同内含利率，否则增量借款利率）与付款时点（期初/期末）；"
        "③验算表2现值合计=表3负债期初，使用权资产入账=现值+预付+初始直接费用±复原/激励；"
        "④抽查后续利息=(期初负债−本期付款)×年折现率、折旧=入账价值/摊销年限，期末勾稽H8-1/H9；"
        "⑤复杂长租、非固定年付或需月结时改用「按月」表，并与本表年化结果交叉复核。"
        "索引：H8-4 / H8-5 / H8-7 / H8-8 / H9。",
        OBJ_FONT,
    )

    # 加固期初付款判定：整列用折现期=0（C20-C29 原先仅首行或仍用 E=1）
    for r in range(20, 30):
        cell = ws.cell(r, 3)
        val = str(cell.value or "")
        if val.startswith("=") and (f"E{r}" in val or f"D{r}=0" in val or "IF(" in val):
            cell.value = f"=IF(D{r}=0,0,B{r})"
    _comment(ws, "C20", "期初付款：折现期D=0 时不计入负债本金，转入预付列G；C21:C29 同步按D判定。")

    # 折现率默认联动增量借款利率（仍可手工覆盖为内含利率）
    h9 = ws["H9"].value
    if h9 == 0.05 or h9 == ws["G9"].value or str(h9) == "=G9":
        ws["H9"] = "=G9"
        _comment(ws, "H9", "默认=增量借款利率G9；若采用合同内含利率，可覆盖为具体数值。")

    # 折旧期取 min(租赁期, 摊销年限)；取得所有权时请直接填使用寿命到 I9 并使 E9≥I9
    h35 = str(ws["H35"].value or "")
    if h35 in ("=$I$30/$I$9", "=$I$30/MIN($E$9,$I$9)") or (h35.startswith("=") and "$I$30" in h35):
        ws["H35"] = "=$I$30/MIN($E$9,$I$9)"
        _comment(ws, "H35", "年折旧=入账/MIN(租赁期E9,摊销年限I9)。能合理确定取得所有权时改用使用寿命（通常令折旧期=I9）。")

    _comment(ws, "G9", "增量借款利率；与H9折现率通常一致，除非改用内含利率。")
    _comment(ws, "I9", "摊销年限（年）。CAS21：折旧期取min(租赁期,使用寿命)；能合理确定取得所有权则取使用寿命。")
    _comment(ws, "E9", "租赁期（年，含续租可能）。应与H8-5结论一致。跨年月份复杂时请人工核对，勿仅依赖YEAR差。")
    _comment(ws, "F30", "尚未支付租赁付款额现值合计→表3负债期初B35。")
    _comment(ws, "I30", "使用权资产初始确认=现值F30+预付G30+初始直接费用H30（±复原/激励视合同补充）。")
    _comment(ws, "E35", "期初付款模型：利息=(期初余额−本期付款)×年折现率。")
    _comment(ws, "J35", "简化：递延所得税资产≈负债账面×税率；需结合企业税会政策，非一律确认。")
    _comment(
        ws,
        "F13",
        "计算区递延所得税引用表3第1年期末J35/K35，便于与后续计量勾稽；"
        "若要反映起租日初始暂时性差异，可改为F30×税率 / I30×税率。",
    )
    _comment(
        ws,
        "A19",
        "表2行数为本表示例固定约10期；租赁期更长/更短请手工插入或删除行并扩展SUM与表3引用。",
    )

    # 自检行（合计旁）
    _set(
        ws,
        "A46",
        "自检：①利息合计E45≈付款合计C45−初始负债F30（尾差为四舍五入）；"
        "②折旧合计H45应≈入账I30；③最后一年负债期末F44应接近0；"
        "④表2/表3行数是否覆盖完整租赁期；⑤与「按月」表年利息/年折旧交叉复核（允许尾差）。",
        GUIDE_FONT,
        OK_FILL,
    )

    # 审计说明 / 结论模板
    _set(
        ws,
        "A47",
        "三、审计说明：合同与租赁期索引(H8-4/H8-5)；折现率选择依据；付款时点(期初/期末)；"
        "初始计量验算；后续利息/折旧抽查；与H8-1、H9勾稽；若未用按月表说明理由。",
        TITLE_NOTE,
        NOTE_FILL,
    )
    _set(
        ws,
        "A49",
        "四、审计结论：□初始及后续计量准确、与账面/H9无重大差异  □除下列差异外未见异常  "
        "□存在重大未调整差异不可确认。差异说明：__________。索引：H8-1 / H8-4 / H8-5 / H9。",
        TITLE_NOTE,
        NOTE_FILL,
    )

    # 编制提示强化
    _set(
        ws,
        "A52",
        "提示（按年计量适用边界与勾稽）：",
        GUIDE_FONT,
    )
    _set(
        ws,
        "A53",
        "1、能合理确定租赁期届满取得租赁资产所有权的，应在资产剩余使用寿命内计提折旧；"
        "否则折旧期=min(租赁期,使用寿命)。残值率无所有权转移预期时通常为0。",
        GUIDE_FONT,
    )
    _set(
        ws,
        "A54",
        "2、本表按「年付+年利率」简化；固定年付、条款简单、审计只需年末余额时可优先本表。"
        "租金月付/季付、租赁期长、或需每月结账时请用「按月」H8-6，折旧明细可衔接H8-8/H8-9。",
        GUIDE_FONT,
    )
    _set(
        ws,
        "A55",
        "3、期初预付请用预付列；变更用H8-7；减值后折旧切H8-8(含减值)。"
        "递延所得税列为余额表法示意，是否确认/如何列报以被审计单位税会政策及CAS18为准。"
        "期初余额衔接可用S3-8/S3-9/S3-10。",
        GUIDE_FONT,
    )


def enhance_monthly(ws) -> None:
    if isinstance(ws["A2"].value, str):
        ws["A2"] = _fix_title_typo(ws["A2"].value)

    # 填表说明增强
    _set(
        ws,
        "A6",
        "填表说明（按月）：适用于需按月计提利息/折旧、付款频率非一年一次、或长期复杂租赁。"
        "月利率口径本表采用名义月利率=年折现率/12（非(1+r)^(1/12)-1）；与「按年」表并用时年化合计允许尾差。"
        "折旧默认次月起计提、直线法；变更见H8-7，折旧测算见H8-8。",
        GUIDE_FONT,
        NOTE_FILL,
    )
    _set(
        ws,
        "C7",
        "必填项，实际起租/交接日，填写格式为YYYY-MM-DD 如：2021-01-01（驱动B列逐月序列）。",
        GUIDE_FONT,
    )
    _set(
        ws,
        "C8",
        "必填项，考虑续租可能后的租赁期届满日（应与H8-5一致），格式YYYY-MM-DD；摊销期限C18据此计算。",
        GUIDE_FONT,
    )
    _set(
        ws,
        "C9",
        "按合同内含利率或增量借款利率确定年折现率；利息列使用年利率/12。与按年表H9应一致。",
        GUIDE_FONT,
    )
    _set(
        ws,
        "C10",
        "已设公式=起止日间隔月数。若折旧期短于租赁期（使用寿命更短），请手工覆盖为实际摊销月数。",
        GUIDE_FONT,
    )
    _set(
        ws,
        "C11",
        "默认直线法月折旧=(E349+H349)/C18，次月起计提；若要求租赁期内折尽，"
        "可改为(E349+H349)/MAX(C18-1,1)，或改为起租当月开始计提。其他方法请改I列。",
        GUIDE_FONT,
    )

    # 资产名称录入格
    if ws["C14"].value in (None, ""):
        ws["C14"] = "XX设备"
    _comment(ws, "C14", "录入使用权资产名称/合同标的，与H8-2、按年表A9对应。")

    # 示例对齐按年表：预付5万+初始直接费用1.5万均进H（使用权资产调整），勿放入D（D会折进负债）
    if ws["D22"].value == 15000:
        ws["D22"] = None
    h22 = ws["H22"].value
    if h22 in (50000, 65000, None, ""):
        ws["H22"] = 65000
    _comment(
        ws,
        "H22",
        "示例：预付租金50,000+初始直接费用15,000=65,000，与按年表G20+H20对齐；"
        "只增加使用权资产，不增加租赁负债。复原成本若需计入负债请填D列。",
    )
    _comment(ws, "D22", "复原成本/终止罚款等计入负债的项目；初始直接费用请填H列而非本列。")

    # 关键参数注释
    _comment(ws, "C15", "租赁期开始日，与明细首月B22联动。")
    _comment(ws, "C16", "约满日（含续租可能），应勾稽H8-5。")
    _comment(ws, "C17", "年折现率；月利息=余额×C17/12。")
    _comment(ws, "C18", "摊销月数；可手工改为min(租赁月数,使用寿命月数)。")
    _comment(ws, "E349", "各期租赁付款额现值合计→初始负债主要部分；汇总区F16引用。")
    _comment(ws, "H349", "开始日或之前支付的租金/复原等成本调整合计→使用权资产加项。")
    _comment(ws, "K22", "使用权资产净值首月=E349+H349−当月折旧；汇总区E15引用。")

    # 修复 E22：与后续行一致使用月利率
    e22 = str(ws["E22"].value or "")
    if "POWER((1+$C$17)," in e22 and "/12" not in e22:
        ws["E22"] = "=(D22+C22)/(POWER((1+$C$17/12),A22-1))"
        _comment(ws, "E22", "已修复：折现统一用月利率 r/12，与E23及以下一致。")
    elif "/12" in e22:
        _comment(ws, "E22", "折现使用月利率 r/12；D22+C22 一并折现。")

    # 首月累计折旧置0，避免J23引用空单元格
    if ws["J22"].value in (None, ""):
        ws["J22"] = 0
    _comment(ws, "J22", "首月累计折旧起点为0；次月起I列计提后累加。")

    if ws["I22"].value in (None, ""):
        ws["I22"] = 0
    else:
        ws["I22"] = 0

    # 折旧截止：序数超摊销期或月份已过约满日则停止（减轻次月起溢出到租期后）
    for r in range(23, 349):
        formula = str(ws.cell(r, 9).value or "")
        if "E$349" in formula or "E349" in formula:
            ws.cell(r, 9).value = (
                f'=IF(OR(($A{r}-1)>$C$18,B{r}>$C$16),0,($E$349+$H$349)/$C$18)'
            )
    _comment(ws, "I23", "次月起计提；超过摊销月数或已过约满日C16则停止。租期内折尽见C11说明。")

    _comment(ws, "F22", "首月利息=年利率/12×初始现值合计E349（开始日尚未扣减后续付款）。")
    _comment(ws, "G22", "首月负债余额=E349+首月利息；嗣后G=上期末−本月付款+本月利息。")
    _comment(ws, "C34", "示例为每年1月支付年租金；请按合同付款日在对应月份填合同租金（不含税）。")

    # 自检提示放在合计行旁
    _set(
        ws,
        "A350",
        "自检：①名义租金C349与现值E349+利息F349勾稽；②I349折旧合计应≈E349+H349"
        "（次月起可能留尾差，见C11）；③约满后G/K接近0；④与按年表交叉复核；"
        "⑤D列复原/初始直接费用是否已填。",
        GUIDE_FONT,
        OK_FILL,
    )

    # 审计说明编号修正 + 内容强化
    _set(
        ws,
        "A352",
        "三、审计说明：",
        TITLE_NOTE,
        NOTE_FILL,
    )
    _set(
        ws,
        "A353",
        "1.租赁条件是否真实、完整（合同/补充协议/续租与终止选择权，索引H8-4/H8-5）",
        TITLE_NOTE,
    )
    _set(
        ws,
        "A354",
        "2.所采用的折现率是否正确（内含利率或增量借款利率；月利率=年利率/12的口径是否披露）",
        TITLE_NOTE,
    )
    _set(
        ws,
        "A355",
        "3.使用权资产入账价值是否正确（现值+预付/初始直接费用/复原成本−激励；与H9负债初始一致）",
        TITLE_NOTE,
    )
    _set(
        ws,
        "A356",
        "4.按月利息/折旧计提时点、付款归属月是否与合同一致；与按年表或H8-1/H9年末余额勾稽结果。",
        TITLE_NOTE,
    )
    _set(
        ws,
        "A357",
        "四、审计结论：□按月计量准确、与账面/H9及按年表无重大差异  □除下列差异外未见异常  "
        "□存在重大未调整差异不可确认。差异说明：__________。索引：H8-1 / H8-4 / H8-5 / H8-8 / H9。",
        TITLE_NOTE,
        NOTE_FILL,
    )


def rename_sheets(wb) -> None:
    mapping = {
        SHEET_ANN: SHEET_ANN_NEW,
        SHEET_MON: SHEET_MON_NEW,
    }
    for old, new in mapping.items():
        if old in wb.sheetnames and new not in wb.sheetnames:
            wb[old].title = new


def resolve_sheet(wb, *names: str):
    for n in names:
        if n in wb.sheetnames:
            return wb[n]
    # fuzzy fallback
    for s in wb.sheetnames:
        if "H8-6" in s and "按年" in s:
            if any("按年" in n for n in names):
                return wb[s]
        if "H8-6" in s and "按月" in s:
            if any("按月" in n for n in names):
                return wb[s]
    return None


def enhance(path: Path, save_as: Path | None = None) -> None:
    """Text/catalog polish + ensure dynamic term rebuild is applied."""
    import importlib.util

    rebuild_path = Path(__file__).with_name("_rebuild_h8_6_dynamic.py")
    spec = importlib.util.spec_from_file_location("rebuild_h86_dyn", rebuild_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {rebuild_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.rebuild(path, save_as=save_as)

    # 轻量二次润色：仅改审计目标等不破坏动态区的单元格
    wb = openpyxl.load_workbook(save_as or path)
    if SHEET_CAT in wb.sheetnames:
        enhance_catalog(wb[SHEET_CAT])
    ws_ann = resolve_sheet(wb, SHEET_ANN_NEW, SHEET_ANN)
    if ws_ann is not None:
        a5 = str(ws_ann["A5"].value or "")
        if "CAS21" not in a5:
            enhance_annual(ws_ann)
        _comment(
            ws_ann,
            "E9",
            "租赁期(年)。改E9→L9有效付款期数自动变，表2/表3按L9启用（最多30年）。也可直接覆盖L9为整数。",
        )
        _comment(ws_ann, "L9", "有效付款期数：默认=ROUND(E9)。直接输入整数亦可，底稿按此动态计算。")
        _comment(ws_ann, "K9", "年租金：改一处即可，各有效年自动引用。")
        _comment(ws_ann, "M9", "初始直接费用：集中录入，首行H列引用。")
    out = save_as or path
    try:
        wb.save(out)
        print("enhance-polish saved", out)
    except PermissionError:
        alt = out.with_name(out.stem + "_H86enhanced.xlsx")
        wb.save(alt)
        print("locked, saved", alt)


def main() -> None:
    seen: set[str] = set()
    for p in TARGETS:
        if not p.exists() or p.name.startswith("~$"):
            continue
        if any(x in p.name for x in ("_H86enhanced", "_H88enhanced", "_H810enhanced", "_H813enhanced")):
            continue
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        print("enhance", p)
        enhance(p)


if __name__ == "__main__":
    main()
