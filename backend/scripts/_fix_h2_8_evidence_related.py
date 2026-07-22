# -*- coding: utf-8 -*-
"""H2-8：按增加方式标注证据列 + 插入关联方列（供 H2-17）。"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

import win32com.client

# Excel ColorIndex / BGR
BLUE = 0xFF0000
RED = 0x0000FF
BLACK = 0x000000


def main() -> None:
    app = win32com.client.GetObject(Class="Ket.Application")
    wb = None
    for i in range(1, app.Workbooks.Count + 1):
        name = app.Workbooks(i).Name
        if "H2" in name and "在建" in name:
            wb = app.Workbooks(i)
            break
    if wb is None:
        raise SystemExit("请先在 WPS 中打开「H2 在建工程.xlsx」")

    ws = None
    for i in range(1, wb.Worksheets.Count + 1):
        n = wb.Worksheets(i).Name
        if "H2-8" in n or "增加检查" in n:
            ws = wb.Worksheets(i)
            break
    if ws is None:
        raise SystemExit("未找到 H2-8")

    print("editing", ws.Name)

    # 若尚未插入关联方列（以 V12 是否仍为「索引号」判断）
    v12 = str(ws.Range("V12").Value or "")
    if "索引" in v12 or v12 == "索引号":
        # 在 V 列前插入两列：是否关联方、关联方名称
        ws.Columns("V").Insert()
        ws.Columns("V").Insert()
        print("inserted 2 columns before 索引号")
    else:
        print("related-party columns seem present:", v12)

    # ── 增加方式列说明 ───────────────────────────────────────────────
    e = ws.Range("E12")
    e.Value = "增加方式"
    e.Font.Bold = True
    e.Font.Name = "宋体"
    e.Font.Size = 10
    # 批注
    try:
        if e.Comment:
            e.Comment.Delete()
    except Exception:
        pass
    e.AddComment(
        "填写：出包 / 自营 / 设备购置 / 其他。\n"
        "出包→重点填「监理/进度」；自营→重点填「领料」；设备购置→重点填「发票/验收」。\n"
        "不适用证据列填 N/A。"
    )
    e.Comment.Shape.Width = 280
    e.Comment.Shape.Height = 90

    # 数据验证：E14:E29
    try:
        ws.Range("E14:E29").Validation.Delete()
    except Exception:
        pass
    ws.Range("E14:E29").Validation.Add(
        Type=3,  # xlValidateList
        AlertStyle=1,
        Operator=1,
        Formula1="出包,自营,设备购置,其他",
    )
    ws.Range("E14:E29").Validation.IgnoreBlank = True
    ws.Range("E14:E29").Validation.InCellDropdown = True

    # ── 证据列按方式标注 ─────────────────────────────────────────────
    # L-M 出包
    ws.Range("L12").Value = "监理/进度(出包)"
    ws.Range("L12").Font.Bold = True
    ws.Range("L12").Font.Color = RED
    ws.Range("L12").Font.Name = "宋体"
    ws.Range("L12").Font.Size = 10
    ws.Range("L13").Value = "日期/编号"
    ws.Range("M13").Value = "完工/结算情况"
    for addr in ("L12", "L13", "M13"):
        ws.Range(addr).Font.Color = RED

    # N-Q 自营
    ws.Range("N12").Value = "领料单(自营)"
    ws.Range("N12").Font.Bold = True
    ws.Range("N12").Font.Color = RED
    ws.Range("N12").Font.Name = "宋体"
    for addr in ("N12", "N13", "O13", "P13", "Q13"):
        ws.Range(addr).Font.Color = RED
        ws.Range(addr).Font.Bold = True if addr == "N12" else False

    # R-T 设备（出包结算发票亦可填）
    ws.Range("R12").Value = "发票/验收(设备)"
    ws.Range("R12").Font.Bold = True
    ws.Range("R12").Font.Color = RED
    ws.Range("R12").Font.Name = "宋体"
    ws.Range("R13").Value = "日期/编号"
    ws.Range("S13").Value = "对手方/验收"
    ws.Range("T13").Value = "金额"
    for addr in ("R12", "R13", "S13", "T13"):
        ws.Range(addr).Font.Color = RED

    # 合同列为共用
    ws.Range("I12").Value = "合同/协议/订单(共用)"
    ws.Range("I12").Font.Bold = True
    ws.Range("I12").Font.Name = "宋体"
    ws.Range("I12").Font.Size = 10

    # ── 关联方列（插入后的 V、W）────────────────────────────────────
    ws.Range("V12").Value = "是否关联方"
    ws.Range("V12").Font.Bold = True
    ws.Range("V12").Font.Name = "宋体"
    ws.Range("V12").Font.Size = 10
    ws.Range("V12").HorizontalAlignment = -4108  # center
    try:
        if ws.Range("V12").Comment:
            ws.Range("V12").Comment.Delete()
    except Exception:
        pass
    ws.Range("V12").AddComment("填「是/否」。选「是」时填写右侧关联方名称，可供 H2-17 关联交易检查表带入。")
    ws.Range("V12").Comment.Shape.Width = 260
    ws.Range("V12").Comment.Shape.Height = 60

    ws.Range("W12").Value = "关联方名称"
    ws.Range("W12").Font.Bold = True
    ws.Range("W12").Font.Name = "宋体"
    ws.Range("W12").Font.Size = 10
    ws.Range("W12").HorizontalAlignment = -4108

    # 索引号、检查结论（应已右移至 X、Y）
    x12 = str(ws.Range("X12").Value or "")
    y12 = str(ws.Range("Y12").Value or "")
    if "索引" not in x12:
        ws.Range("X12").Value = "索引号"
        ws.Range("X12").Font.Bold = True
        ws.Range("X12").Font.Name = "宋体"
    if "检查" not in y12 and "结论" not in y12 and "异常" not in y12:
        ws.Range("Y12").Value = "检查结论"
        ws.Range("Y12").Font.Bold = True
        ws.Range("Y12").Font.Name = "宋体"

    # 合并 V12:V13 / W12:W13 / X12:X13 / Y12:Y13（若未合并）
    for col in ("V", "W", "X", "Y"):
        try:
            ws.Range(f"{col}12:{col}13").Merge()
        except Exception:
            pass
        ws.Range(f"{col}12").HorizontalAlignment = -4108
        ws.Range(f"{col}12").VerticalAlignment = -4108

    # 关联方数据验证
    try:
        ws.Range("V14:V29").Validation.Delete()
    except Exception:
        pass
    ws.Range("V14:V29").Validation.Add(
        Type=3, AlertStyle=1, Operator=1, Formula1="是,否"
    )
    ws.Range("V14:V29").Validation.IgnoreBlank = True
    ws.Range("V14:V29").Validation.InCellDropdown = True

    # 蓝色填写提示放在 Z13
    ws.Range("Z13").Value = (
        "证据列选用：出包→监理/进度；自营→领料；设备→发票/验收；共用→合同。"
        "不适用填 N/A。「是否关联方=是」时填名称 → H2-17。"
    )
    ws.Range("Z13").Font.Color = BLUE
    ws.Range("Z13").Font.Name = "Arial Narrow"
    ws.Range("Z13").Font.Size = 10
    ws.Range("Z13").WrapText = True

    # 更新测试说明中的方式切换提示
    ws.Range("A11").Value = (
        "测试内容说明：1.原始凭证是否齐全；2.记账凭证与原始凭证是否相符；"
        "3.账务处理是否正确（含资本化/费用化）；4.是否记录于恰当会计期间；"
        "5.按增加方式取证——出包：合同+监理/进度+结算付款；自营：合同/预算+领料+归集；"
        "设备购置：合同/订单+发票+验收+付款（不适用列填 N/A）；"
        "6.是否关联方=是时填写关联方名称（→H2-17）。"
    )
    ws.Range("A11").Font.Color = RED
    ws.Range("A11").Font.Name = "Arial Narrow"
    ws.Range("A11").Font.Size = 10
    ws.Range("A11").WrapText = True
    ws.Range("A11").EntireRow.RowHeight = 42

    # 使用说明补一句
    a44 = str(ws.Range("A44").Value or "")
    if "出包" not in a44 or "设备" not in a44:
        ws.Range("A44").Value = (
            "3.按增加方式切换证据重点：出包→监理/进度与结算；自营→领料与成本归集；"
            "设备购置→合同、发票与验收；利息/待摊交叉 H2-10/H2-11，避免本表重复详测。"
            "关联方标记后交叉 H2-17。"
        )
        ws.Range("A44").WrapText = True
        ws.Range("A44").EntireRow.RowHeight = 32

    # 列宽
    ws.Columns("V").ColumnWidth = 10
    ws.Columns("W").ColumnWidth = 14
    ws.Columns("E").ColumnWidth = 11

    wb.Save()
    print("SAVED OK")
    # verify headers
    for col in list("ABCDEFGHIJKLMNOPQRSTUVWXY"):
        v = ws.Range(f"{col}12").Value
        v2 = ws.Range(f"{col}13").Value
        if v or v2:
            print(f"{col}12={v} | {col}13={v2}")


if __name__ == "__main__":
    main()
