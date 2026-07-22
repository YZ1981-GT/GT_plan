# -*- coding: utf-8 -*-
"""Enhance H8-8 使用权资产折旧测算表（不含减值 / 含减值）Excel template.

源模板问题：
1. 审计目标偏笼统，未区分「未减值直线法」与「减值后分段重算」
2. 含减值表用全局 F7 减值日，未提示按资产行级日期更优；与 H8-10 勾稽弱
3. 未写明 CAS21 折旧期=min(租赁期,使用寿命)、残值率实务常为0
4. 审计结论区空白，无结构化结论模板
5. 编制提示未强调：有减值须切含减值表；本期折旧应与 H8-1/H8-9 勾稽

改进：
- 强化两表审计目标/过程说明差异
- 补编制提示与结论勾选模板
- 表头注释链 H8-2 / H8-9 / H8-10
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
        if p not in TARGETS:
            TARGETS.append(p)

SHEET_NO = "折旧测算表（不含减值）H8-8"
SHEET_YES = "折旧测算表（含减值）H8-8"

OBJ_FONT = Font(size=10)
GUIDE_FONT = Font(color="0563C1", size=9)
TITLE_NOTE = Font(size=9, color="833C0C")
LEFT_WRAP = Alignment(wrap_text=True, vertical="center", horizontal="left")
NOTE_FILL = PatternFill("solid", fgColor="FFF8E7")


def _set(ws, addr: str, value: str, font=None, fill=None):
    ws[addr] = value
    if font:
        ws[addr].font = font
    if fill:
        ws[addr].fill = fill
    ws[addr].alignment = LEFT_WRAP


def enhance_no_impair(ws) -> None:
    _set(
        ws,
        "A5",
        "一、审计目标：确认未计提减值的使用权资产折旧以恰当金额计入报表；"
        "折旧期=min(租赁期,使用寿命)（能合理确定取得所有权时取使用寿命）；"
        "直线法月折旧=原值×(1−残值率)÷使用月限；本期及累计折旧测算与账面无重大差异；"
        "相关披露恰当（CAS21第21条）。",
        OBJ_FONT,
    )
    _set(
        ws,
        "A6",
        "二、审计过程：①自明细表H8-2带入类别/名称/编号/原值/累计折旧/开始使用日期；"
        "②核对使用年限与租赁期，确认折旧期取短；残值率无所有权转移预期时通常为0；"
        "③按折旧期初/期末测算本期月数、测算月折旧、当期折旧费用及累计差异；"
        "④差异>0.01查明原因；⑤本期折旧合计与审定表H8-1累计折旧本期计提、分配表H8-9勾稽。"
        "若资产已计提减值，改用「折旧测算表（含减值）H8-8」。",
        OBJ_FONT,
    )
    # 行7提示强化
    tip = (
        "各列顺序可按需调整；非公式列请「选择性粘贴-数值」。"
        "公式：使用月限J、测算到期日K、已提月份L、本期月数M、测算月折旧N=原值×(1−残值率)/J、"
        "当期折旧O=N×M、月折旧差异P=账面月折旧−N、累计测算Q=N×L、累计差异R=账面累计−Q。"
    )
    if ws["F7"].value:
        ws["F7"] = tip
        ws["F7"].font = GUIDE_FONT
    else:
        _set(ws, "F7", tip, GUIDE_FONT)

    # 结论模板：找空白区（约行37后）
    for r in range(36, 48):
        if ws.cell(r, 1).value is None:
            _set(
                ws,
                f"A{r}",
                "三、审计说明：参数来源（H8-2）、折旧期判断依据、重大差异原因、与H8-1/H8-9勾稽结果。",
                TITLE_NOTE,
                NOTE_FILL,
            )
            _set(
                ws,
                f"A{r+1}",
                "四、审计结论：□折旧测算准确、与账面无重大差异  □除下列差异外未见异常  "
                "□存在重大未调整差异不可确认。索引：H8-1 / H8-2 / H8-9。",
                TITLE_NOTE,
                NOTE_FILL,
            )
            break

    for col, text in [
        ("D8", "取自H8-2原值/入账值"),
        ("E8", "账面累计折旧期末，与H8-2勾稽"),
        ("N8", "测算月折旧=原值×(1−残值率)/使用月限"),
        ("O8", "应与H8-1累计折旧本期计提、H8-9分配合计勾稽"),
    ]:
        try:
            ws[col].comment = Comment(text, "H8-8", width=240, height=60)
        except Exception:
            pass


def enhance_with_impair(ws) -> None:
    _set(
        ws,
        "A5",
        "一、审计目标：确认已计提减值的使用权资产后续折旧以恰当金额计入报表；"
        "减值后月折旧=(原值×(1−残值率)−减值时累计折旧−减值准备)/剩余月数；"
        "本期折旧=减值前月数×原月折旧+减值后月数×新月折旧；"
        "减值一经确认不得转回（CAS21第21条+CAS8）；披露恰当。",
        OBJ_FONT,
    )
    _set(
        ws,
        "A6",
        "二、审计过程：①自H8-2带入原值/累计折旧/减值准备；②减值金额、时点与减值测算表H8-10、"
        "可收回金额测试表H8-11勾稽（本表F7为模板全局减值日示例，实务宜按资产填写减值日）；"
        "③测算减值前/后月数及新旧月折旧；④当期折旧费用与账面、H8-1本期计提、H8-9分配勾稽；"
        "⑤无减值资产请改用「不含减值」表。",
        OBJ_FONT,
    )
    tip = (
        "含减值关键公式：R=减值前月折旧；S=R×减值时已提月数；"
        "T=(原值×(1−残值率)−S−减值)/剩余月数；U=R×本期减值前月数+T×本期减值后月数；"
        "W=减值前累计+减值后累计。非公式列请粘贴数值。有⑧补提时须先完成H8-10再回本表重算。"
    )
    if ws["G7"].value is not None:
        ws["G7"] = tip
        ws["G7"].font = GUIDE_FONT
    else:
        _set(ws, "G7", tip, GUIDE_FONT)

    for r in range(36, 48):
        if ws.cell(r, 1).value is None:
            _set(
                ws,
                f"A{r}",
                "三、审计说明：减值迹象/可收回金额索引(H8-10/H8-11)、减值日与分段月数、"
                "新月折旧计算、与账面差异原因、与H8-9勾稽。",
                TITLE_NOTE,
                NOTE_FILL,
            )
            _set(
                ws,
                f"A{r+1}",
                "四、审计结论：□减值后折旧测算准确  □除下列差异外未见异常  "
                "□存在重大未调整差异不可确认。索引：H8-1 / H8-2 / H8-9 / H8-10 / H8-11。"
                "提示：减值不得转回。",
                TITLE_NOTE,
                NOTE_FILL,
            )
            break

    for col, text in [
        ("F8", "取自H8-2减值准备/或H8-10⑦已计提"),
        ("T8", "减值后月折旧=(可折旧额−减值时累计−减值)/剩余月数"),
        ("U8", "本期=减值前月数×R+减值后月数×T；勾稽H8-1/H8-9"),
    ]:
        try:
            ws[col].comment = Comment(text, "H8-8", width=260, height=70)
        except Exception:
            pass


def enhance(path: Path, save_as: Path | None = None) -> None:
    wb = openpyxl.load_workbook(path)
    if SHEET_NO not in wb.sheetnames or SHEET_YES not in wb.sheetnames:
        raise SystemExit(f"missing H8-8 sheets in {path}: {wb.sheetnames}")
    enhance_no_impair(wb[SHEET_NO])
    enhance_with_impair(wb[SHEET_YES])
    out = save_as or path
    try:
        wb.save(out)
        print("saved", out)
    except PermissionError:
        alt = out.with_name(out.stem + "_H88enhanced.xlsx")
        wb.save(alt)
        print("locked, saved", alt)


def main() -> None:
    seen = set()
    for p in TARGETS:
        if not p.exists() or p.name.startswith("~$"):
            continue
        if "_H88enhanced" in p.name or "_H810enhanced" in p.name or "_H813enhanced" in p.name:
            continue
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        print("enhance", p)
        enhance(p)


if __name__ == "__main__":
    main()
