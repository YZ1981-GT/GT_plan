# -*- coding: utf-8 -*-
"""通过 WPS COM 向已打开的 H2 工作簿写入 H2-8 改进（文件被占用时用）。"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

import win32com.client


def set_cell(ws, addr: str, value, *, bold=False, color=None, wrap=True, row_height=None):
    cell = ws.Range(addr)
    cell.Value = value
    cell.Font.Name = "Arial Narrow"
    cell.Font.Size = 10
    cell.Font.Bold = bold
    if color == "blue":
        cell.Font.Color = 0xFF0000  # BGR: blue
    elif color == "red":
        cell.Font.Color = 0x0000FF  # BGR: red
    elif color == "black":
        cell.Font.Color = 0x000000
    if wrap:
        cell.WrapText = True
    if row_height is not None:
        ws.Range(addr).EntireRow.RowHeight = row_height


def main() -> None:
    app = win32com.client.GetObject(Class="Ket.Application")
    wb = None
    for i in range(1, app.Workbooks.Count + 1):
        cand = app.Workbooks(i)
        if "H2" in cand.Name and "在建工程" in cand.Name:
            wb = cand
            break
    if wb is None:
        raise SystemExit("未找到已打开的 H2 在建工程.xlsx")

    ws = None
    for i in range(1, wb.Worksheets.Count + 1):
        name = wb.Worksheets(i).Name
        if "H2-8" in name or "增加检查" in name:
            ws = wb.Worksheets(i)
            break
    if ws is None:
        raise SystemExit("未找到 H2-8 工作表")

    print("editing:", wb.FullName, "/", ws.Name)

    set_cell(
        ws,
        "A5",
        "一、审计目标：针对本期在建工程增加实施细节测试——"
        "（1）存在/发生：抽查的增加真实发生，对应工程项目存在；"
        "（2）准确性与计价：金额与合同/进度/发票等证据相符，资本化范围恰当（应资本化 vs 应费用化）；"
        "（3）截止：记入正确的会计期间；"
        "（4）权利与义务：相关合同权利义务归属于被审计单位。"
        "重大遗漏风险结合总体分析程序与 H2-2/H2-6 关注完整性。",
        bold=True,
        color="black",
        row_height=48,
    )

    set_cell(ws, "A6", "二、样本选取标准与规模：", bold=True, color="black")
    set_cell(ws, "A7", "测试总体：", color="black")
    set_cell(
        ws,
        "B7",
        "本期在建工程借方发生额（与 H2-2 本期增加合计勾稽），共 XX 笔、金额 XX",
        color="blue",
    )
    set_cell(ws, "F7", "特定样本：", color="black")
    set_cell(
        ws,
        "G7",
        "超过重要性/明显重大金额、关联方交易、异常对方科目/摘要、年末集中入账等全部详查，共 XX 笔、金额 XX",
        color="blue",
    )

    set_cell(ws, "A8", "抽样总体：", color="black")
    set_cell(ws, "B8", "测试总体扣除特定样本后剩余项目，共 XX 笔、金额 XX", color="blue")
    set_cell(ws, "F8", "确定的抽样样本量：", color="black")
    set_cell(
        ws,
        "G8",
        "抽取 XX 笔、金额 XX；计划检查比例 XX%（样本金额/本期增加合计）",
        color="blue",
    )
    set_cell(ws, "H8", "（若使用样本计算器，计算过程见 <XX> 底稿）", color="blue")

    set_cell(ws, "A9", "抽样方法：", color="black")
    set_cell(
        ws,
        "B9",
        "随机选样 / 系统选样 / 货币单元抽样 / 随意选样（非统计抽样）",
        color="blue",
    )
    set_cell(ws, "F9", "抽样过程：", color="black")
    set_cell(
        ws,
        "G9",
        "使用 IDEA（或其他抽样工具）选取样本；抽样过程与结果见 <XX> 底稿。特定样本与抽样样本合计构成检查总体。",
        color="blue",
    )

    set_cell(ws, "A10", "三、测试：", bold=True, color="black")
    set_cell(
        ws,
        "A11",
        "测试内容说明：1.原始凭证是否齐全；"
        "2.记账凭证与原始凭证是否相符；"
        "3.账务处理是否正确（含资本化/费用化划分、对方科目）；"
        "4.是否记录于恰当会计期间；"
        "5.合同金额、形象进度/监理报告、结算及付款是否勾稽一致；"
        "6.大额或关联交易是否单独识别（→H2-17）。"
        "不适用的证据列填 N/A；证据列可按被审计单位情况增删。",
        color="red",
        row_height=36,
    )

    # 表头
    cell_u = ws.Range("U12")
    cell_u.Value = "资本化判断"
    cell_u.Font.Bold = True
    cell_u.Font.Name = "宋体"
    cell_u.Font.Size = 10
    cell_u.Font.Color = 0x000000

    cell_w = ws.Range("W12")
    cell_w.Value = "检查结论"
    cell_w.Font.Bold = True
    cell_w.Font.Name = "宋体"
    cell_w.Font.Size = 10

    set_cell(
        ws,
        "X13",
        "检查的关键证据和要素根据被审计单位具体情况修改；不适用列填 N/A",
        color="blue",
    )

    set_cell(ws, "A30", "合计（已检查样本）", color="black")
    set_cell(ws, "A31", "本期增加在建工程合计（H2-2）", color="black")
    set_cell(ws, "A32", "检查比例", color="black")
    ws.Range("H32").Formula = '=IF(OR(H31="",H31=0),"",H30/H31)'
    ws.Range("H32").NumberFormat = "0.00%"

    set_cell(ws, "A33", "四、审计说明：", bold=True, color="black")
    set_cell(
        ws,
        "A34",
        "编制指引：①样本构成（特定样本+抽样样本）、抽样方法及计划/实际检查比例；"
        "比例偏低须扩大样本或说明原因。"
        "②逐项异常/存疑/需调整事项及证据索引；调整分录→H2-3。"
        "③利息资本化详见 H2-10/H2-11；关联方交易详见 H2-17。",
        color="red",
        row_height=36,
    )
    ws.Range("A35").Value = ""
    ws.Range("A36").Value = ""
    ws.Range("A37").Value = ""

    set_cell(ws, "A38", "五、审计结论：", bold=True, color="black")
    set_cell(
        ws,
        "A39",
        "基于上述检查，本期抽查的在建工程增加在存在性、准确性/资本化划分及截止方面"
        "未见重大异常 / 发现以下需调整事项（详见审计说明及 H2-3）：________。"
        "检查比例 ___%，可为相关认定提供充分、适当的审计证据。",
        color="blue",
        row_height=36,
    )

    for r in range(40, 58):
        ws.Cells(r, 1).Value = ""

    set_cell(ws, "A40", "附注", bold=True, color="black")
    set_cell(ws, "A41", "【使用说明】", bold=True, color="black")
    set_cell(
        ws,
        "A42",
        "1.本表汇总本期在建工程增加的细节测试。测试总体金额应与 H2-2 本期增加合计、H2-6 借方发生额勾稽。",
        color="black",
        row_height=28,
    )
    set_cell(
        ws,
        "A43",
        "2.取证范围：立项/批复、施工（采购）合同、进度确认/监理报告、工程结算单、发票、领料出库、付款回单及授权审批等；按增加方式选用证据列，不适用填 N/A。",
        color="black",
        row_height=28,
    )
    set_cell(
        ws,
        "A44",
        "3.出包工程重进度与结算勾稽；自营工程重领料与人工/机械归集；设备购置重合同、发票与验收；利息/待摊支出分别交叉 H2-10/H2-11 及费用类科目，避免在本表重复详测。",
        color="black",
        row_height=28,
    )
    set_cell(
        ws,
        "A45",
        "【执行核对清单】（完成情况在「审计说明」中简述，打勾仅为编制辅助）",
        bold=True,
        color="black",
    )
    checklist = [
        (46, "□ 工程款支付与合同、进度/监理报告及授权审批一致，会计处理正确"),
        (47, "□ 工程物资领用有审批，会计处理正确"),
        (48, "□ 借款费用资本化条件、方法、期间、金额正确（交叉 H2-10、H2-11）"),
        (49, "□ 工程管理费等资本化金额合理（交叉管理费用等科目）"),
        (50, "□ 土地使用权与地上建筑物分别核算（土地→无形资产，不挤占在建工程）"),
        (51, "□ 出包工程按合理估计进度及合同结算款入账；设备交付建造承包商时点恰当"),
        (52, "□ 工程物资盘盈盘亏、报废毁损净损益及残料/废料处置冲减成本处理正确"),
        (
            53,
            "□ 待摊支出（管理费、征地、可研、临时设施、监理、税费等）分配合理；"
            "达预定可使用状态时转入对应成本；付现与现金流量表「购建固定资产、无形资产和其他长期资产支付的现金」无重大未解释差异",
        ),
    ]
    for r, text in checklist:
        set_cell(ws, f"A{r}", text, color="black", row_height=22 if r != 53 else 32)

    set_cell(ws, "A54", "【舞弊与关联方提示】", bold=True, color="black")
    set_cell(
        ws,
        "A55",
        "参照《中国注册会计师审计准则问题解答第18号——识别和应对第三方配合实施财务舞弊》："
        "存在大额长期资产建造/采购时，关注是否通过虚增在建工程造价套取资金；"
        "若同时存在关联方资金占用或其他套取资金舞弊风险因素，应评价是否存在第三方配合舞弊并实施追加程序。"
        "已识别关联方增加应标记并交叉至 H2-17。",
        color="blue",
        row_height=48,
    )

    wb.Save()
    print("SAVED OK via COM")


if __name__ == "__main__":
    main()
