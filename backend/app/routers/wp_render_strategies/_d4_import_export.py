"""D4 营业收入 — 导入导出三级端点

3个端点：
- POST /api/workpapers/{wp_id}/d4/export-template?sheet={sheet_code}  空白模板xlsx
- POST /api/workpapers/{wp_id}/d4/export-data?sheet={sheet_code}      数据xlsx
- POST /api/workpapers/{wp_id}/d4/import-data?sheet={sheet_code}      解析xlsx写入

支持sheets: D4-2, D4-3, D4-12, D4-14~D4-20, D4-21~D4-36
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["d4-import-export"])

# ═══════════════════════════════════════════════════════════════════════════════
# Sheet 配置：每种sheet的列头定义
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

_SUPPORTED_SHEETS: set[str] = {
    "D4-2", "D4-3", "D4-4", "D4-6", "D4-7", "D4-8", "D4-9", "D4-10", "D4-11", "D4-12",
    "D4-14", "D4-15", "D4-16", "D4-17", "D4-18", "D4-19", "D4-20",
    "D4-20-provision", "D4-20-current", "D4-20-post",
    "D4-21", "D4-22", "D4-23", "D4-24", "D4-25", "D4-26", "D4-27",
    "D4-28", "D4-29", "D4-30", "D4-31", "D4-32",
    "D4-33", "D4-34", "D4-34-rental", "D4-34-consult", "D4-35", "D4-36", "D4-36-forward", "D4-36-backward",
}

_SHEET_HEADERS: dict[str, list[str]] = {
    "D4-2": [
        "产品/服务", "1月", "2月", "3月", "4月", "5月", "6月",
        "7月", "8月", "9月", "10月", "11月", "12月",
        "未审合计", "审计调整", "本期审定", "上期未审", "上期调整", "上期审定",
        "未审变动率", "审定变动率", "备注",
    ],
    "D4-3": [
        "项目", "本期未审数", "本期调整", "上期未审数", "上期调整", "备注",
    ],
    "D4-6": [
        "指标名称", "本期", "上期", "变化原因及合理性分析1",
        "同行业公司平均值", "变化原因及合理性分析2",
    ],
    "D4-7": [
        "产品名称", "本期数量", "本期平均单价", "本期主营业务收入", "本期结构比",
        "本期单位成本", "本期主营业务成本", "本期毛利", "本期毛利率",
        "上期主营业务收入", "上期主营业务成本", "上期毛利率", "变动比例", "备注",
    ],
    "D4-8": [
        "产品名称", "月份", "本期销量", "本期平均单价", "本期收入金额",
        "本期成本销量", "本期平均单位成本", "本期成本金额",
        "上期销量", "上期平均单价", "上期收入金额",
        "上期成本销量", "上期平均单位成本", "上期成本金额",
    ],
    "D4-9": [
        "客户名称", "销售金额", "销售数量", "上期排名",
    ],
    "D4-10": [
        "客户名称", "产品种类", "销售金额", "销售数量",
        "销售单价", "年度均价", "与均价差异原因", "市场价格", "与市场差异原因",
    ],
    "D4-11": [
        "客户名称", "品种规格", "销售单价", "销售数量", "开票日期",
        "销售订单", "订单日期", "定价表单价", "同期市场价格",
        "差异原因分析", "市场价格来源", "备注",
    ],
    "D4-4": [
        "摘要", "分类", "报表项目", "会计科目", "附注项目", "借方", "贷方", "索引号",
    ],
    "D4-12": [
        "索引号", "合同名称", "客户名称", "合同金额", "合同日期",
        "履约义务", "交易价格", "收入确认时点/时段", "可变对价", "合同变更", "结论", "备注",
    ],
    "D4-14": [
        "序号", "事项名称",
        "凭证月份", "凭证日期", "凭证编号", "凭证品名", "凭证数量", "凭证金额", "记账日期",
        "合同编号", "合同品名", "合同金额", "签发审批", "签收确认",
        "出库日期", "出库品名", "出库金额", "仓库保管员",
        "运输日期", "运输品名", "运输金额",
        "签收日期", "签收品名", "签收金额",
        "发票日期", "发票编号", "发票金额",
        "其他文件描述", "其他索引号",
        "一致性分数", "检查结论", "备注",
    ],
    "D4-15": [
        "序号",
        "发货单日期", "发货单编号", "发货单品名", "发货单数量", "发货单金额",
        "发票日期", "发票编号", "发票品名", "发票数量", "发票金额",
        "记账凭证日期", "记账凭证编号", "记账凭证品名", "记账凭证数量", "记账凭证金额",
        "核核信息是否一致", "备注",
    ],
    "D4-16": [
        "序号", "账面出口收入金额",
        "口岸期间", "口岸结关金额", "口岸差异", "口岸差异原因",
        "申报外营收入", "申报差异", "申报差异原因", "索引",
    ],
    "D4-17": [
        "序号",
        "凭证日期", "凭证编号", "凭证品名", "凭证数量", "凭证金额",
        "发货单日期", "发货单编号", "发货单品名", "发货单数量", "发货单金额",
        "是否跨期", "备注",
    ],
    "D4-18": [
        "序号",
        "发货单日期", "发货单编号", "发货单品名", "发货单数量", "发货单金额",
        "凭证日期", "凭证编号", "凭证品名", "凭证数量", "凭证金额",
        "是否跨期", "备注",
    ],
    "D4-19": [
        "序号", "客户名称", "折扣类型", "收入金额", "折扣金额", "折扣比例", "原因",
        "凭证日期", "凭证编号", "会计科目", "明细科目", "借方金额", "贷方金额",
        "审批日期", "审批人", "备注",
    ],
    "D4-20": [
        "序号", "客户名称", "产品名称", "退货日期", "退货数量", "退货金额", "退货原因",
        "凭证日期", "凭证编号", "业务内容", "科目名称", "二级明细", "借方金额", "贷方金额",
        "是否涉及诉讼", "是否异常", "索引号",
    ],
    "D4-20-provision": [
        "序号", "产品名称", "计提基数", "计提比例", "应计提金额", "账面已计提金额", "差异金额", "差异原因",
    ],
    "D4-20-current": [
        "序号", "凭证日期", "凭证编号", "业务内容", "科目名称", "二级明细", "借方金额", "贷方金额",
        "客户名称", "产品名称", "退货数量", "退货金额", "退货原因",
        "是否涉及诉讼", "是否异常", "索引号",
    ],
    "D4-20-post": [
        "序号", "凭证日期", "凭证编号", "业务内容", "科目名称", "二级明细", "借方金额", "贷方金额",
        "客户名称", "产品名称", "退货数量", "退货金额", "退货原因",
        "是否涉及诉讼", "是否异常", "索引号",
    ],
    "D4-21": [
        "序号", "关联方客户名称", "关联关系", "产品名称", "销售数量", "销售额",
        "销售额占比", "平均单价", "非关联方平均单价", "差异率",
        "可比公允价格", "差异率(公允)",
        "上年度占比", "上年度平均单价", "备注",
    ],
    "D4-22": [
        "指标名称", "本期", "上期",
        "同行业公司1", "同行业公司2", "同行业公司3",
        "合理性分析",
    ],
    "D4-23": [
        "月份", "主营业务收入", "其他业务收入", "营业收入合计",
        "增值税发票金额", "增值税发票份数", "普通发票金额", "普通发票份数",
        "开票金额合计", "差异", "索引号",
    ],
    "D4-24": [
        "序号", "客户名称", "本年度销售金额", "期末应收账款余额",
        "本年度第三方回款金额", "第三方回款方名称", "第三方回款原因",
        "第三方回款方与客户关系", "第三方回款方与被审计单位关系",
        "是否有代付协议", "是否函证", "合理性分析", "索引",
    ],
    "D4-25": [
        "序号", "客户名称", "经销商", "本期销售数量", "本期销售金额",
        "占同类交易比例", "期末应收账款余额", "是否关联方",
        "个人/企业", "销售费用承担方式", "补贴或返利", "终端销售金额", "备注",
    ],
    "D4-26": [
        "客户名称", "所在国家/地区", "产品种类", "业务模式",
        "本期销售金额", "占同类交易比例", "贸易模式", "主要贸易条款",
        "出口结算模式", "是否存在第三方回款", "第三方回款原因",
        "核查程序确认的销售金额", "差异", "差异原因分析",
        "实地走访", "交易函证", "海关函证", "核对报关单", "电子口岸数据查询",
    ],
    "D4-27": [
        "序号", "姓名", "个人客户", "客户法人", "合同签订人", "高管亲属",
        "财务部门", "管理部门", "技术部门", "生产部门", "营销部门", "其他",
        "总计", "重名(Y/N)", "公司股东/高管/亲属/员工", "年度销售额", "说明", "索引号",
    ],
    "D4-28": [
        "序号", "客户名称", "选取原因", "销售金额", "占总交易比重",
        "应收账款期末余额", "占期末余额比重", "合同负债期末余额", "占期末余额比重",
        "工商资料查询", "互联网信息查询", "函证", "视频电话访谈", "实地走访", "索引号",
    ],
    "D4-29": [
        "客户名称", "统一社会信用代码", "注册地址", "办公地址", "网站地址", "网站IP地址",
        "企业邮箱", "成立时间", "注册资本/实缴资本", "经营范围", "人员规模/社保缴纳人数",
        "法定代表人", "股东1及持股比例", "股东2及持股比例", "股东3及持股比例",
        "董事长", "总经理", "关键经办人员", "实际控制人",
        "是否为关联方", "是否同时为供应商", "开始合作时间",
        "是否长期拖欠款项", "经营状态", "是否列入失信人", "信息来源",
    ],
    "D4-32": [
        "序号", "单位名称/姓名", "本期交易金额", "占同类交易比例",
        "开户银行", "账号", "资金流水获取途径", "是否发现异常交易", "索引号",
    ],
    "D4-33": [
        "月份",
        "合计-收入", "合计-成本", "合计-毛利率",
        "出租固定资产-收入", "出租固定资产-成本", "出租固定资产-毛利率",
        "出租无形资产-收入", "出租无形资产-成本", "出租无形资产-毛利率",
        "销售材料-收入", "销售材料-成本", "销售材料-毛利率",
    ],
    "D4-34": [
        "序号", "承租方/委托方", "租赁期间/咨询项目", "租赁面积/委托期限",
        "合同单价/合同金额", "合同索引", "本期实际租赁月数",
        "本期应计收入", "本期实计收入", "差异", "索引号",
    ],
    "D4-34-rental": [
        "序号", "承租方", "租赁期间", "租赁面积", "合同单价",
        "合同索引", "本期实际租赁月数", "本期应计收入", "本期实计收入", "差异", "索引号",
    ],
    "D4-34-consult": [
        "序号", "委托方", "咨询项目", "委托期限", "合同金额",
        "合同索引", "本期应计收入", "本期实计收入", "差异", "索引号",
    ],
    "D4-35": [
        "日期", "凭证编号", "业务内容", "对方科目", "明细科目", "金额",
        "支持性文件", "核对1", "核对2", "核对3", "核对4", "核对5", "核对6",
        "索引号", "是否异常", "备注说明",
    ],
    "D4-36": [
        "凭证日期", "凭证编号", "凭证品名", "凭证数量", "凭证金额",
        "单据日期", "单据编号", "单据品名", "单据数量", "单据金额", "是否跨期",
    ],
    "D4-36-forward": [
        "凭证日期", "凭证编号", "凭证品名", "凭证数量", "凭证金额",
        "单据日期", "单据编号", "单据品名", "单据数量", "单据金额", "是否跨期",
    ],
    "D4-36-backward": [
        "单据日期", "单据编号", "单据品名", "单据数量", "单据金额",
        "凭证日期", "凭证编号", "凭证品名", "凭证数量", "凭证金额", "是否跨期",
    ],
}

# D4-22~D4-36使用通用列头
_GENERIC_HEADERS = ["序号", "项目", "金额", "说明", "结论", "备注"]


def _get_headers(sheet_code: str) -> list[str]:
    """获取sheet对应的列头，未定义则用通用列头"""
    return _SHEET_HEADERS.get(sheet_code, _GENERIC_HEADERS)


def _validate_sheet(sheet_code: str) -> None:
    """验证sheet_code是否支持"""
    if sheet_code not in _SUPPORTED_SHEETS:
        raise HTTPException(
            400,
            f"不支持的sheet: {sheet_code}。支持: {sorted(_SUPPORTED_SHEETS)}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# D4-4 数据验证辅助（报表项目/会计科目/附注项目下拉）
# ═══════════════════════════════════════════════════════════════════════════════


async def _add_d4_4_data_validation(
    ws, wp_id: str, db: AsyncSession, headers: list[str]
) -> None:
    """为D4-4模板的报表项目、会计科目、附注项目列添加下拉数据验证

    从working_paper关联的project的trial_balance取出科目列表。
    """
    import sqlalchemy as sa
    from openpyxl.worksheet.datavalidation import DataValidation

    # 获取project_id: working_paper → project_id
    result = await db.execute(
        sa.text("SELECT project_id FROM working_paper WHERE id = :wp_id LIMIT 1"),
        {"wp_id": wp_id},
    )
    row = result.fetchone()
    if not row:
        return
    project_id = str(row.project_id)

    # 查trial_balance获取科目列表（会计科目 = standard_account_code + account_name）
    result = await db.execute(
        sa.text("""
            SELECT DISTINCT standard_account_code, account_name
            FROM trial_balance
            WHERE project_id = :pid
            ORDER BY standard_account_code
        """),
        {"pid": project_id},
    )
    tb_rows = result.fetchall()

    if not tb_rows:
        return

    # 构建选项列表
    account_options = [f"{r.standard_account_code}-{r.account_name}" for r in tb_rows]
    # 报表项目=按科目编码顺序的account_name（去重保持顺序）
    seen_names: set[str] = set()
    report_item_options: list[str] = []
    for r in tb_rows:
        if r.account_name and r.account_name not in seen_names:
            seen_names.add(r.account_name)
            report_item_options.append(r.account_name)
    # 附注项目=同报表项目（按科目编码顺序）
    note_item_options = report_item_options

    # openpyxl数据验证：列表写入隐藏sheet，用公式引用（避免255字符限制）
    ws_data = ws.parent.create_sheet("_数据源")
    ws_data.sheet_state = "hidden"

    # 写入科目列表到隐藏sheet的A列（会计科目）
    for i, opt in enumerate(account_options[:500], start=1):
        ws_data.cell(row=i, column=1, value=opt)
    # B列（报表项目）
    for i, opt in enumerate(report_item_options[:500], start=1):
        ws_data.cell(row=i, column=2, value=opt)
    # C列（附注项目）
    for i, opt in enumerate(note_item_options[:500], start=1):
        ws_data.cell(row=i, column=3, value=opt)

    # 找到各列在headers中的位置（1-based Excel列号）
    def col_letter(col_name: str) -> str | None:
        try:
            idx = headers.index(col_name) + 1  # 1-based
            return chr(64 + idx) if idx <= 26 else None
        except ValueError:
            return None

    account_col = col_letter("会计科目")
    report_col = col_letter("报表项目")
    note_col = col_letter("附注项目")

    max_row = 501  # 验证应用范围（2~501行）

    # 会计科目列下拉
    if account_col and account_options:
        dv = DataValidation(
            type="list",
            formula1=f"=_数据源!$A$1:$A${len(account_options[:500])}",
            allow_blank=True,
        )
        dv.error = "请从下拉列表中选择会计科目"
        dv.errorTitle = "输入无效"
        dv.prompt = "请选择项目中的会计科目"
        dv.promptTitle = "会计科目"
        ws.add_data_validation(dv)
        dv.add(f"{account_col}2:{account_col}{max_row}")

    # 报表项目列下拉
    if report_col and report_item_options:
        dv = DataValidation(
            type="list",
            formula1=f"=_数据源!$B$1:$B${len(report_item_options[:500])}",
            allow_blank=True,
        )
        dv.error = "请从下拉列表中选择报表项目"
        dv.errorTitle = "输入无效"
        dv.prompt = "请选择报表项目"
        dv.promptTitle = "报表项目"
        ws.add_data_validation(dv)
        dv.add(f"{report_col}2:{report_col}{max_row}")

    # 附注项目列下拉
    if note_col and note_item_options:
        dv = DataValidation(
            type="list",
            formula1=f"=_数据源!$C$1:$C${len(note_item_options[:500])}",
            allow_blank=True,
        )
        dv.error = "请从下拉列表中选择附注项目"
        dv.errorTitle = "输入无效"
        dv.prompt = "请选择附注项目"
        dv.promptTitle = "附注项目"
        ws.add_data_validation(dv)
        dv.add(f"{note_col}2:{note_col}{max_row}")

    # 分类列下拉（固定选项）
    category_col = col_letter("分类")
    if category_col:
        dv = DataValidation(
            type="list",
            formula1='"账项调整,报表调整,其他"',
            allow_blank=True,
        )
        dv.error = "请选择：账项调整/报表调整/其他"
        dv.errorTitle = "输入无效"
        ws.add_data_validation(dv)
        dv.add(f"{category_col}2:{category_col}{max_row}")


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/api/workpapers/{wp_id}/d4/export-template")
async def d4_export_template(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码如D4-2"),
    include_guidance: bool = Query(True, description="是否包含编制说明"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白模板xlsx（含表头+格式+编制说明，无数据行）"""
    _validate_sheet(sheet)
    headers = _get_headers(sheet)

    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(headers)

    # 冻结首行+设置列宽
    ws.freeze_panes = "A2"
    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[chr(64 + min(col_idx, 26))].width = 16

    # D4-4特殊处理：为"报表项目""会计科目""附注项目"添加下拉数据验证
    if sheet == "D4-4":
        await _add_d4_4_data_validation(ws, wp_id, db, headers)

    # D4-6特殊处理：预填指标名称（固定12行不可改）
    if sheet == "D4-6":
        _d4_6_indicator_names = [
            "应收账款/总资产",
            "应收账款周转天数=应收账款平均余额/(销售收入/365)",
            "应收账款周转次数=销售收入/应收账款平均余额",
            "（末月/最后一个季度）销售情况/当期销售（金额或销量）",
            "销售折扣/销售额",
            "销售折让/销售额",
            "销货退回/销售额",
            "坏账准备金额/应收账款余额",
            "人均创收=销售收入/员工总数",
            "销售净利率=净利润/销售收入",
            "人均创利=净利润/员工总数",
            "当期销售金额/主要原材料采购金额",
        ]
        for name in _d4_6_indicator_names:
            ws.append([name, None, None, None, None, None])

    # D4-22特殊处理：预填12行固定KPI指标名称
    if sheet == "D4-22":
        _d4_22_indicator_names = [
            "年度预算",
            "主营业务收入",
            "销售人员数量",
            "销售人员人均创收",
            "销售区域分布是否变化（占比和区域数量等）",
            "销售人员业绩指标",
            "销售人员薪酬",
            "期末在手订单",
            "息税前利润（利润总额＋财务费用）",
            "薪酬总额（支付给职工以及为职工支付的现金+期末应付职工薪酬-期初应付职工薪酬）",
            "人力投入回报率(ROP)",
            "运输费用/营业收入",
        ]
        for name in _d4_22_indicator_names:
            ws.append([name] + [None] * (len(headers) - 1))

    # D4-23特殊处理：预填12个月份行
    if sheet == "D4-23":
        for m in ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"]:
            ws.append([m] + [None] * (len(headers) - 1))

    # D4-33特殊处理：预填16行（12月+合计+上年数+变动额+变动比例）
    if sheet == "D4-33":
        for label in ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月", "合计", "上年数", "变动额", "变动比例"]:
            ws.append([label] + [None] * (len(headers) - 1))

    # 添加编制说明 sheet
    if include_guidance:
        guidance = _get_guidance_text(sheet)
        if guidance:
            ws_guide = wb.create_sheet("编制说明")
            ws_guide.append(["编制说明"])
            ws_guide.append([])
            for line in guidance:
                ws_guide.append([line])
            ws_guide.column_dimensions["A"].width = 80

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"{sheet}_模板.xlsx"
    # HTTP headers must be ASCII; use RFC 5987 encoding for Chinese filename
    from urllib.parse import quote
    encoded_filename = quote(filename)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


@router.post("/api/workpapers/{wp_id}/d4/export-data")
async def d4_export_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码如D4-2"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出当前数据xlsx"""
    _validate_sheet(sheet)
    headers = _get_headers(sheet)

    # 加载 checklist_responses 中的行数据
    import sqlalchemy as sa

    item_id = f"{sheet}-rows"
    # D4-6 uses a different item_id key
    if sheet == "D4-6":
        item_id = "D4-6-indicators-v2"
    elif sheet == "D4-7":
        item_id = "D4-7-products"
    elif sheet == "D4-8":
        item_id = "D4-8-products"
    elif sheet == "D4-9":
        item_id = "D4-9-data"
    elif sheet == "D4-10":
        item_id = "D4-10-data"
    elif sheet == "D4-11":
        item_id = "D4-11-data"
    elif sheet == "D4-12":
        item_id = "D4-12-contracts-v2"
    elif sheet == "D4-14":
        item_id = "D4-14-transactions"
    elif sheet == "D4-22":
        item_id = "D4-22-data"
    elif sheet == "D4-23":
        item_id = "D4-23-data"
    result = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
        ),
        {"wp_id": wp_id, "item_id": item_id},
    )
    row = result.fetchone()
    rows_data: list[dict] = []
    if row and row.remark:
        try:
            parsed = json.loads(row.remark)
            # D4-22 stores {rows: [...], peers: [...], transportExpense: ...}
            if sheet == "D4-22" and isinstance(parsed, dict):
                rows_data = parsed.get("rows", [])
            elif isinstance(parsed, list):
                rows_data = parsed
            else:
                rows_data = parsed
        except (json.JSONDecodeError, TypeError):
            pass

    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(headers)
    ws.freeze_panes = "A2"

    # 写入数据行
    for data_row in rows_data:
        if sheet == "D4-2":
            months = data_row.get("months", [0] * 12)
            period_total = sum(_safe_float(m) for m in months)
            audit_adj = _safe_float(data_row.get("auditAdjustment"))
            audited = period_total + audit_adj
            prior_unadj = _safe_float(data_row.get("priorUnadjusted"))
            prior_adj = _safe_float(data_row.get("priorAdjustment"))
            prior_audited = prior_unadj + prior_adj
            # 变动率
            unadj_rate = ((period_total - prior_unadj) / prior_unadj * 100) if prior_unadj != 0 else 0
            audited_rate = ((audited - prior_audited) / prior_audited * 100) if prior_audited != 0 else 0
            row_values = [
                data_row.get("product", ""),
                *[_safe_float(m) for m in months],
                period_total,
                audit_adj,
                audited,
                prior_unadj,
                prior_adj,
                prior_audited,
                round(unadj_rate, 2),
                round(audited_rate, 2),
                data_row.get("remark", ""),
            ]
        elif sheet == "D4-3":
            row_values = [
                data_row.get("item", ""),
                data_row.get("currentUnadjusted", 0),
                data_row.get("currentAdjustment", 0),
                data_row.get("priorUnadjusted", 0),
                data_row.get("priorAdjustment", 0),
                data_row.get("remark", ""),
            ]
        elif sheet == "D4-4":
            row_values = [
                data_row.get("description", ""),
                data_row.get("category", ""),
                data_row.get("reportItem", ""),
                data_row.get("accountName", ""),
                data_row.get("noteItem", ""),
                _safe_float(data_row.get("debitAmount")),
                _safe_float(data_row.get("creditAmount")),
                data_row.get("indexRef", ""),
            ]
        elif sheet == "D4-6":
            current = _safe_float(data_row.get("current"))
            prior = _safe_float(data_row.get("prior"))
            industry = data_row.get("industryAvg")
            row_values = [
                data_row.get("name", ""),
                current,
                prior,
                data_row.get("analysis1", ""),
                _safe_float(industry) if industry is not None else "",
                data_row.get("analysis2", ""),
            ]
        elif sheet == "D4-7":
            cur_qty = _safe_float(data_row.get("curQty"))
            cur_revenue = _safe_float(data_row.get("curRevenue"))
            cur_cost = _safe_float(data_row.get("curCost"))
            prior_qty = _safe_float(data_row.get("priorQty"))
            prior_revenue = _safe_float(data_row.get("priorRevenue"))
            prior_cost = _safe_float(data_row.get("priorCost"))
            # Auto-calc columns
            cur_avg_price = cur_revenue / cur_qty if cur_qty != 0 else 0
            cur_structure = 0  # requires total, skip for export
            cur_unit_cost = cur_cost / cur_qty if cur_qty != 0 else 0
            cur_profit = cur_revenue - cur_cost
            cur_margin = cur_profit / cur_revenue if cur_revenue != 0 else 0
            prior_margin = (prior_revenue - prior_cost) / prior_revenue if prior_revenue != 0 else 0
            row_values = [
                data_row.get("name", ""),
                cur_qty,
                cur_avg_price,
                cur_revenue,
                cur_structure,
                cur_unit_cost,
                cur_cost,
                cur_profit,
                cur_margin,
                prior_revenue,
                prior_cost,
                prior_margin,
                (cur_margin - prior_margin),
                data_row.get("remark", ""),
            ]
        elif sheet == "D4-8":
            # D4-8 special: data_row is a product with months[12]/priorMonths[12]
            # Output 12 rows per product (handled below after loop)
            continue
        elif sheet == "D4-14":
            # D4-14 穿行测试：TransactionItem → 32列平铺
            v = data_row.get("voucher", {})
            c = data_row.get("contract", {})
            d = data_row.get("delivery", {})
            s = data_row.get("shipping", {})
            r = data_row.get("receipt", {})
            inv = data_row.get("invoice", {})
            o = data_row.get("other", {})
            row_values = [
                data_row.get("indexNo", ""),
                data_row.get("label", ""),
                v.get("month", ""), v.get("date", ""), v.get("number", ""),
                v.get("productName", ""), v.get("quantity", ""), _safe_float(v.get("amount")), v.get("accountingDate", ""),
                c.get("number", ""), c.get("productName", ""), _safe_float(c.get("amount")),
                c.get("approver", ""), c.get("confirmor", ""),
                d.get("date", ""), d.get("productName", ""), _safe_float(d.get("amount")), d.get("warehouseKeeper", ""),
                s.get("date", ""), s.get("productName", ""), _safe_float(s.get("amount")),
                r.get("date", ""), r.get("productName", ""), _safe_float(r.get("amount")),
                inv.get("date", ""), inv.get("number", ""), _safe_float(inv.get("amount")),
                o.get("description", ""), o.get("indexNo", ""),
                data_row.get("consistencyScore", 0),
                data_row.get("conclusion", ""),
                "",  # 备注
            ]
        elif sheet == "D4-22":
            # D4-22: 固定指标行，动态peers列
            peers = data_row.get("peers", [])
            # 表头已有3个同行列位，不够的补空，多余的截断
            peer_count = len(headers) - 4  # 去掉 指标名称/本期/上期/合理性分析 = 动态列数
            peer_values = list(peers[:peer_count]) + [""] * max(0, peer_count - len(peers))
            row_values = [
                data_row.get("label", ""),
                data_row.get("currentPeriod", ""),
                data_row.get("priorPeriod", ""),
                *peer_values,
                data_row.get("analysis", ""),
            ]
        elif sheet == "D4-23":
            # D4-23: 12月收入vs发票比较
            row_values = [
                data_row.get("month", ""),
                _safe_float(data_row.get("mainRevenue")),
                _safe_float(data_row.get("otherRevenue")),
                _safe_float(data_row.get("revenueTotal")),
                _safe_float(data_row.get("vatAmount")),
                _safe_float(data_row.get("vatCount")),
                _safe_float(data_row.get("normalAmount")),
                _safe_float(data_row.get("normalCount")),
                _safe_float(data_row.get("invoiceTotal")),
                _safe_float(data_row.get("diff")),
                data_row.get("indexRef", ""),
            ]
        else:
            # 通用：按 headers 顺序提取值
            row_values = [data_row.get(h, "") for h in headers]
        ws.append(row_values)

    # D4-8 special: flatten products × 12 months
    if sheet == "D4-8":
        _months_labels = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"]
        for product in rows_data:
            p_name = product.get("name", "")
            months = product.get("months", [])
            prior_months = product.get("priorMonths", [])
            for m_idx in range(12):
                cur = months[m_idx] if m_idx < len(months) else {}
                pri = prior_months[m_idx] if m_idx < len(prior_months) else {}
                ws.append([
                    p_name,
                    _months_labels[m_idx],
                    _safe_float(cur.get("revQty")),
                    _safe_float(cur.get("revPrice")),
                    _safe_float(cur.get("revAmt")),
                    _safe_float(cur.get("costQty")),
                    _safe_float(cur.get("costPrice")),
                    _safe_float(cur.get("costAmt")),
                    _safe_float(pri.get("revQty")),
                    _safe_float(pri.get("revPrice")),
                    _safe_float(pri.get("revAmt")),
                    _safe_float(pri.get("costQty")),
                    _safe_float(pri.get("costPrice")),
                    _safe_float(pri.get("costAmt")),
                ])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"{sheet}_数据.xlsx"
    from urllib.parse import quote
    encoded_filename = quote(filename)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


@router.post("/api/workpapers/{wp_id}/d4/import-data")
async def d4_import_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码如D4-2"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """解析上传xlsx，校验格式，写入 checklist_responses"""
    _validate_sheet(sheet)

    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(400, "文件大小不能超过10MB")

    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(400, "无法解析xlsx文件，请确认文件格式正确")

    ws = wb.active
    if ws is None:
        raise HTTPException(400, "xlsx文件中无活动工作表")

    # 验证列头
    expected_headers = _get_headers(sheet)
    actual_headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    actual_headers = [str(h).strip() if h else "" for h in actual_headers]

    errors: list[str] = []
    missing_cols = [h for h in expected_headers if h not in actual_headers]
    if missing_cols:
        errors.append(f"缺少列: {', '.join(missing_cols)}")

    if errors:
        return {"ok": False, "errors": errors, "imported_count": 0}

    # 解析数据行
    rows_data: list[dict] = []
    truncated = False
    row_count = 0

    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None for v in row):
            continue
        row_count += 1
        if row_count > _ROW_LIMIT:
            truncated = True
            break

        if sheet == "D4-2":
            row_dict = _parse_d4_2_row(row, actual_headers, expected_headers)
        elif sheet == "D4-3":
            row_dict = _parse_d4_3_row(row, actual_headers, expected_headers)
        elif sheet == "D4-4":
            row_dict = _parse_d4_4_row(row, actual_headers, expected_headers)
        elif sheet == "D4-6":
            row_dict = _parse_d4_6_row(row, actual_headers)
        elif sheet == "D4-7":
            row_dict = _parse_d4_7_row(row, actual_headers)
        elif sheet == "D4-8":
            row_dict = _parse_d4_8_row(row, actual_headers)
        elif sheet == "D4-14":
            row_dict = _parse_d4_14_row(row, actual_headers)
        elif sheet == "D4-22":
            row_dict = _parse_d4_22_row(row, actual_headers)
        elif sheet == "D4-23":
            row_dict = _parse_d4_23_row(row, actual_headers)
        else:
            row_dict = _parse_generic_row(row, actual_headers)

        rows_data.append(row_dict)

    wb.close()

    # D4-8 post-processing: group flat rows by product name into products array
    if sheet == "D4-8":
        from collections import OrderedDict
        _month_map = {"1月": 0, "2月": 1, "3月": 2, "4月": 3, "5月": 4, "6月": 5,
                      "7月": 6, "8月": 7, "9月": 8, "10月": 9, "11月": 10, "12月": 11}
        products_dict: OrderedDict = OrderedDict()
        for r in rows_data:
            p_name = r.get("productName", "")
            if not p_name:
                continue
            if p_name not in products_dict:
                empty_m = [{"revQty": 0, "revPrice": 0, "revAmt": 0, "costQty": 0, "costPrice": 0, "costAmt": 0} for _ in range(12)]
                products_dict[p_name] = {
                    "name": p_name,
                    "months": [dict(m) for m in empty_m],
                    "priorMonths": [dict(m) for m in empty_m],
                    "industry": [
                        {"name": "同行业A企业", "revQty": 0, "revPrice": 0, "revAmt": 0, "costQty": 0, "costPrice": 0, "costAmt": 0},
                        {"name": "同行业B企业", "revQty": 0, "revPrice": 0, "revAmt": 0, "costQty": 0, "costPrice": 0, "costAmt": 0},
                        {"name": "行业平均水平", "revQty": 0, "revPrice": 0, "revAmt": 0, "costQty": 0, "costPrice": 0, "costAmt": 0},
                    ],
                }
            m_idx = _month_map.get(r.get("month", ""), -1)
            if m_idx < 0:
                continue
            products_dict[p_name]["months"][m_idx] = {
                "revQty": r.get("curRevQty", 0), "revPrice": r.get("curRevPrice", 0), "revAmt": r.get("curRevAmt", 0),
                "costQty": r.get("curCostQty", 0), "costPrice": r.get("curCostPrice", 0), "costAmt": r.get("curCostAmt", 0),
            }
            products_dict[p_name]["priorMonths"][m_idx] = {
                "revQty": r.get("priorRevQty", 0), "revPrice": r.get("priorRevPrice", 0), "revAmt": r.get("priorRevAmt", 0),
                "costQty": r.get("priorCostQty", 0), "costPrice": r.get("priorCostPrice", 0), "costAmt": r.get("priorCostAmt", 0),
            }
        rows_data = list(products_dict.values())

    # 写入 checklist_responses
    import sqlalchemy as sa
    from uuid import uuid4

    item_id = f"{sheet}-rows"
    # D4-6 uses a different item_id key
    if sheet == "D4-6":
        item_id = "D4-6-indicators-v2"
    elif sheet == "D4-7":
        item_id = "D4-7-products"
    elif sheet == "D4-8":
        item_id = "D4-8-products"
    elif sheet == "D4-9":
        item_id = "D4-9-data"
    elif sheet == "D4-10":
        item_id = "D4-10-data"
    elif sheet == "D4-11":
        item_id = "D4-11-data"
    elif sheet == "D4-12":
        item_id = "D4-12-contracts-v2"
    elif sheet == "D4-14":
        item_id = "D4-14-transactions"
    elif sheet == "D4-22":
        item_id = "D4-22-data"
    elif sheet == "D4-23":
        item_id = "D4-23-data"

    # D4-22 特殊：保留已有peers和transportExpense，只替换rows
    if sheet == "D4-22":
        # 读取已有数据
        existing_result = await db.execute(
            sa.text("SELECT remark FROM checklist_responses WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"),
            {"wp_id": wp_id, "item_id": item_id},
        )
        existing_row = existing_result.fetchone()
        existing_data = {}
        if existing_row and existing_row.remark:
            try:
                existing_data = json.loads(existing_row.remark)
            except (json.JSONDecodeError, TypeError):
                pass
        # 合并：导入的rows替换，peers/transportExpense保留
        merged = {
            "rows": rows_data,
            "peers": existing_data.get("peers", []),
            "transportExpense": existing_data.get("transportExpense", ""),
        }
        remark_json = json.dumps(merged, ensure_ascii=False)
    else:
        remark_json = json.dumps(rows_data, ensure_ascii=False)

    await db.execute(
        sa.text("""
            INSERT INTO checklist_responses (id, wp_id, item_id, remark, updated_at)
            VALUES (:id, :wp_id, :item_id, :remark, NOW())
            ON CONFLICT (wp_id, item_id)
            DO UPDATE SET remark = :remark, updated_at = NOW()
        """),
        {
            "id": str(uuid4()),
            "wp_id": wp_id,
            "item_id": item_id,
            "remark": remark_json,
        },
    )
    await db.commit()

    result: dict[str, Any] = {
        "ok": True,
        "imported_count": len(rows_data),
        "errors": errors,
    }
    if truncated:
        result["warning"] = f"数据行数超过{_ROW_LIMIT}行限制，已截断"
        result["truncated"] = True

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 行解析辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _safe_float(val: Any) -> float:
    """安全转换为float，失败返回0"""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _safe_str(val: Any) -> str:
    """安全转换为str"""
    if val is None:
        return ""
    return str(val).strip()


def _parse_d4_2_row(row: tuple, actual_headers: list[str], expected_headers: list[str]) -> dict:
    """解析D4-2行：产品+12月+计算列(忽略)+调整+上期+变动率(忽略)+备注"""
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    months = [_safe_float(_col_val(f"{m}月")) for m in range(1, 13)]

    return {
        "rowId": str(uuid4()),
        "product": _safe_str(_col_val("产品/服务")),
        "months": months,
        "auditAdjustment": _safe_float(_col_val("审计调整")),
        "priorUnadjusted": _safe_float(_col_val("上期未审")),
        "priorAdjustment": _safe_float(_col_val("上期调整")),
        "remark": _safe_str(_col_val("备注")),
        # 自动计算列（未审合计/本期审定/上期审定/变动率）导入时忽略，前端重算
    }


def _parse_d4_3_row(row: tuple, actual_headers: list[str], expected_headers: list[str]) -> dict:
    """解析D4-3行"""
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    return {
        "rowId": str(uuid4()),
        "item": _safe_str(_col_val("项目")),
        "currentUnadjusted": _safe_float(_col_val("本期未审数")),
        "currentAdjustment": _safe_float(_col_val("本期调整")),
        "priorUnadjusted": _safe_float(_col_val("上期未审数")),
        "priorAdjustment": _safe_float(_col_val("上期调整")),
        "remark": _safe_str(_col_val("备注")),
    }


def _parse_d4_4_row(row: tuple, actual_headers: list[str], expected_headers: list[str]) -> dict:
    """解析D4-4调整分录行"""
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    return {
        "rowId": str(uuid4()),
        "description": _safe_str(_col_val("摘要")),
        "category": _safe_str(_col_val("分类")) or "账项调整",
        "reportItem": _safe_str(_col_val("报表项目")),
        "accountName": _safe_str(_col_val("会计科目")),
        "noteItem": _safe_str(_col_val("附注项目")),
        "debitAmount": _safe_float(_col_val("借方")),
        "creditAmount": _safe_float(_col_val("贷方")),
        "indexRef": _safe_str(_col_val("索引号")),
    }


def _parse_d4_14_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析D4-14穿行测试行 → TransactionItem结构"""
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    return {
        "id": f"t-{uuid4().hex[:10]}",
        "indexNo": _safe_str(_col_val("序号")),
        "label": _safe_str(_col_val("事项名称")),
        "voucher": {
            "month": _safe_str(_col_val("凭证月份")),
            "date": _safe_str(_col_val("凭证日期")),
            "number": _safe_str(_col_val("凭证编号")),
            "productName": _safe_str(_col_val("凭证品名")),
            "quantity": _safe_str(_col_val("凭证数量")),
            "amount": _safe_float(_col_val("凭证金额")),
            "accountingDate": _safe_str(_col_val("记账日期")),
        },
        "contract": {
            "number": _safe_str(_col_val("合同编号")),
            "productName": _safe_str(_col_val("合同品名")),
            "amount": _safe_float(_col_val("合同金额")),
            "approver": _safe_str(_col_val("签发审批")),
            "confirmor": _safe_str(_col_val("签收确认")),
        },
        "delivery": {
            "date": _safe_str(_col_val("出库日期")),
            "productName": _safe_str(_col_val("出库品名")),
            "amount": _safe_float(_col_val("出库金额")),
            "warehouseKeeper": _safe_str(_col_val("仓库保管员")),
        },
        "shipping": {
            "date": _safe_str(_col_val("运输日期")),
            "productName": _safe_str(_col_val("运输品名")),
            "amount": _safe_float(_col_val("运输金额")),
        },
        "receipt": {
            "date": _safe_str(_col_val("签收日期")),
            "productName": _safe_str(_col_val("签收品名")),
            "amount": _safe_float(_col_val("签收金额")),
        },
        "invoice": {
            "date": _safe_str(_col_val("发票日期")),
            "number": _safe_str(_col_val("发票编号")),
            "amount": _safe_float(_col_val("发票金额")),
        },
        "other": {
            "description": _safe_str(_col_val("其他文件描述")),
            "indexNo": _safe_str(_col_val("其他索引号")),
        },
        "consistencyScore": 0,
        "consistencyDetails": None,
        "conclusion": _safe_str(_col_val("检查结论")),
        "isAnomalous": False,
    }


def _parse_d4_22_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析D4-22重要指标分析行 → IndicatorRow结构

    表头: 指标名称 | 本期 | 上期 | 同行业公司1~N | 合理性分析
    """
    values = list(row) + [None] * (len(actual_headers) - len(row))

    # 固定列：指标名称(0), 本期(1), 上期(2), 合理性分析(末列)
    label = _safe_str(values[0]) if values[0] else ""
    current_period = values[1] if values[1] is not None else ""
    prior_period = values[2] if values[2] is not None else ""
    analysis = _safe_str(values[-1]) if values[-1] else ""

    # 中间列为同行业公司值（动态数量）
    peer_values = []
    for i in range(3, len(actual_headers) - 1):
        if i < len(values):
            peer_values.append(values[i] if values[i] is not None else "")
        else:
            peer_values.append("")

    # 根据label匹配key
    _LABEL_KEY_MAP = {
        "年度预算": "budget",
        "主营业务收入": "revenue",
        "销售人员数量": "salesHeadcount",
        "销售人员人均创收": "revenuePerCapita",
        "销售区域分布是否变化（占比和区域数量等）": "regionDistribution",
        "销售人员业绩指标": "performanceTarget",
        "销售人员薪酬": "salesCompensation",
        "期末在手订单": "backlog",
        "息税前利润（利润总额＋财务费用）": "ebit",
        "薪酬总额（支付给职工以及为职工支付的现金+期末应付职工薪酬-期初应付职工薪酬）": "totalCompensation",
        "人力投入回报率(ROP)": "rop",
        "运输费用/营业收入": "transportRatio",
    }
    key = _LABEL_KEY_MAP.get(label, label)
    is_auto = key in ("revenuePerCapita", "rop", "transportRatio")

    return {
        "key": key,
        "label": label,
        "currentPeriod": current_period,
        "priorPeriod": prior_period,
        "peers": peer_values,
        "analysis": analysis,
        "isAutoCalc": is_auto,
    }


def _parse_d4_23_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析D4-23收入与发票比较行 → InvoiceCompareRow结构

    表头: 月份 | 主营业务收入 | 其他业务收入 | 营业收入合计 | 增值税发票金额 | 增值税发票份数 | 普通发票金额 | 普通发票份数 | 开票金额合计 | 差异 | 索引号
    导入时忽略自动计算列(营业收入合计/开票金额合计/差异)，前端会自动重算。
    """
    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    main_rev = _safe_float(_col_val("主营业务收入"))
    other_rev = _safe_float(_col_val("其他业务收入"))
    vat_amt = _safe_float(_col_val("增值税发票金额"))
    normal_amt = _safe_float(_col_val("普通发票金额"))
    revenue_total = main_rev + other_rev
    invoice_total = vat_amt + normal_amt

    return {
        "month": _safe_str(_col_val("月份")),
        "mainRevenue": main_rev if main_rev else "",
        "otherRevenue": other_rev if other_rev else "",
        "revenueTotal": revenue_total,
        "vatAmount": vat_amt if vat_amt else "",
        "vatCount": _safe_float(_col_val("增值税发票份数")) or "",
        "normalAmount": normal_amt if normal_amt else "",
        "normalCount": _safe_float(_col_val("普通发票份数")) or "",
        "invoiceTotal": invoice_total,
        "diff": revenue_total - invoice_total,
        "indexRef": _safe_str(_col_val("索引号")),
    }


def _parse_generic_row(row: tuple, actual_headers: list[str]) -> dict:
    """通用行解析"""
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))
    result = {"rowId": str(uuid4())}
    for i, header in enumerate(actual_headers):
        if i < len(values):
            val = values[i]
            result[header] = val if val is not None else ""
    return result


def _parse_d4_6_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析D4-6重要指标分析行"""
    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    return {
        "name": _safe_str(_col_val("指标名称")),
        "current": _safe_float(_col_val("本期")),
        "prior": _safe_float(_col_val("上期")),
        "analysis1": _safe_str(_col_val("变化原因及合理性分析1")),
        "industryAvg": _safe_float(_col_val("同行业公司平均值")) or None,
        "analysis2": _safe_str(_col_val("变化原因及合理性分析2")),
    }


def _parse_d4_7_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析D4-7按产品毛利分析行（手填列：产品名称/本期数量/本期主营业务收入/本期主营业务成本/上期主营业务收入/上期主营业务成本/备注）"""
    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    return {
        "name": _safe_str(_col_val("产品名称")),
        "curQty": _safe_float(_col_val("本期数量")),
        "curRevenue": _safe_float(_col_val("本期主营业务收入")),
        "curCost": _safe_float(_col_val("本期主营业务成本")),
        "priorQty": 0,  # 上期数量不在简化导入列中，默认0
        "priorRevenue": _safe_float(_col_val("上期主营业务收入")),
        "priorCost": _safe_float(_col_val("上期主营业务成本")),
        "remark": _safe_str(_col_val("备注")),
    }


def _parse_d4_8_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析D4-8重要产品毛利分析行（产品名称+月份+本期6列+上期6列，按产品groupby后重组）"""
    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    return {
        "productName": _safe_str(_col_val("产品名称")),
        "month": _safe_str(_col_val("月份")),
        "curRevQty": _safe_float(_col_val("本期销量")),
        "curRevPrice": _safe_float(_col_val("本期平均单价")),
        "curRevAmt": _safe_float(_col_val("本期收入金额")),
        "curCostQty": _safe_float(_col_val("本期成本销量")),
        "curCostPrice": _safe_float(_col_val("本期平均单位成本")),
        "curCostAmt": _safe_float(_col_val("本期成本金额")),
        "priorRevQty": _safe_float(_col_val("上期销量")),
        "priorRevPrice": _safe_float(_col_val("上期平均单价")),
        "priorRevAmt": _safe_float(_col_val("上期收入金额")),
        "priorCostQty": _safe_float(_col_val("上期成本销量")),
        "priorCostPrice": _safe_float(_col_val("上期平均单位成本")),
        "priorCostAmt": _safe_float(_col_val("上期成本金额")),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 编制说明文本（导出模板时附加）
# ═══════════════════════════════════════════════════════════════════════════════

_SHEET_GUIDANCE: dict[str, list[str]] = {
    "D4-2": [
        "D4-2 主营业务收入明细表 编制说明",
        "",
        "一、本表目的",
        "按产品/服务类别列示各月主营业务收入（科目6001），反映收入的季节性分布和波动趋势。",
        "",
        "二、填写要求",
        "1. 「产品/服务」列：填写公司产品/服务大类名称，与D4-1审定表对应。",
        "2. 「1月~12月」列：填写各月未审收入金额（含税/不含税按公司口径一致）。",
        "3. 「审计调整」列：如有AJE/RJE涉及该产品，在此填写调整净额。",
        "4. 「上期未审」「上期调整」列：填写上年同期数据供对比分析。",
        "5. 灰底列为自动计算列（未审合计/本期审定/上期审定/变动率），导入时会忽略。",
        "",
        "三、自动计算列说明",
        "未审合计 = SUM(1月~12月)",
        "本期审定 = 未审合计 + 审计调整",
        "上期审定 = 上期未审 + 上期调整",
        "未审变动率 = (未审合计 - 上期未审) / 上期未审 × 100%",
        "审定变动率 = (本期审定 - 上期审定) / 上期审定 × 100%",
        "",
        "四、审计关注",
        "1. 各月收入波动是否合理，有无年末突击确认收入的迹象。",
        "2. 变动率超过30%的产品需在审计说明中解释原因。",
        "3. 本表合计应与D4-1审定表「主营业务收入」行一致。",
        "",
        "五、数据来源",
        "从序时账（tb_ledger）按科目6001+辅助维度（产品/服务）按月汇总导入。",
        "或从ERP系统销售明细导出后按本模板格式整理。",
    ],
    "D4-3": [
        "D4-3 其他业务收入明细表 编制说明",
        "",
        "一、本表目的",
        "列示其他业务收入（科目6051）各项目的本期/上期对比。",
        "",
        "二、填写要求",
        "1. 「项目」列：填写其他业务收入项目名称（如租赁收入、材料销售等）。",
        "2. 「本期未审数」「本期调整」列：填写本期金额及AJE/RJE调整。",
        "3. 「上期未审数」「上期调整」列：填写上年同期对比数据。",
        "",
        "三、审计关注",
        "1. 其他业务收入占比是否异常增大。",
        "2. 与主营业务收入增长趋势是否匹配。",
    ],
    "D4-6": [
        "D4-6 重要指标分析表 编制说明",
        "",
        "一、本表目的",
        "计算与营业收入相关的重要财务指标，与上期及同行业公司对比分析，识别异常波动。",
        "",
        "二、填写要求",
        "1. 「指标名称」列：已预设12项指标（如应收账款/总资产、应收账款周转天数等），不可修改。",
        "2. 「本期」列：填写本期指标计算值（来源于试算表自动取数或手工计算）。",
        "3. 「上期」列：填写上年同期指标值。",
        "4. 「同行业公司平均值」列：填写行业可比数据（来源于行业报告/上市公司年报披露）。",
        "5. 「变化原因及合理性分析1」列：解释与上期对比的变动原因。",
        "6. 「变化原因及合理性分析2」列：解释与行业均值的差异原因。",
        "",
        "三、自动计算列说明（导入时忽略）",
        "差异1 ③ = (本期① - 上期②) / |上期②|",
        "差异2 ⑥ = (本期① - 行业均值⑤) / |行业均值⑤|",
        "差异超过30%自动标红，需重点关注。",
        "",
        "四、审计关注",
        "1. 应收账款周转率显著下降可能意味着收入质量恶化。",
        "2. 末季销售占比过高可能存在突击确认收入。",
        "3. 人均创收/创利异常增长需分析是否有虚增收入迹象。",
        "4. 与行业均值差异较大的指标需解释业务合理性。",
        "",
        "五、数据来源",
        "本期/上期：从trial_balance取数（科目6001收入/1122应收/4103净利润/资产总计等）。",
        "行业数据：手动填写，参考Wind/同花顺行业均值或可比公司年报。",
    ],
    "D4-7": [
        "D4-7 主营业务收入毛利率分析表 编制说明",
        "",
        "一、本表目的",
        "分析各月和各产品主营业务收入毛利率的变动情况，识别异常波动。",
        "",
        "二、填写要求（按产品毛利分析部分，即导入区域）",
        "1. 「产品名称」列：填写公司各产品/服务大类名称。",
        "2. 「本期数量」列：填写本期销售数量。",
        "3. 「本期主营业务收入」列：填写本期该产品收入金额。",
        "4. 「本期主营业务成本」列：填写本期该产品成本金额。",
        "5. 「上期主营业务收入」列：填写上期该产品收入金额。",
        "6. 「上期主营业务成本」列：填写上期该产品成本金额。",
        "7. 「备注」列：填写需要备注的信息。",
        "",
        "三、自动计算列说明（导入时忽略）",
        "本期平均单价 = 主营业务收入 / 数量",
        "结构比 = 本产品收入 / 合计收入",
        "单位成本 = 主营业务成本 / 数量",
        "毛利 = 主营业务收入 - 主营业务成本",
        "毛利率 = IF(收入=0, 0, 毛利/收入)",
        "变动比例(平均单价) = (本期单价-上期单价)/上期单价",
        "变动比例(单位成本) = (本期单位成本-上期单位成本)/上期单位成本",
        "变动比例(收入) = (本期收入-上期收入)/上期收入",
        "变动比例(成本) = (本期成本-上期成本)/上期成本",
        "变动比例(毛利率) = 本期毛利率 - 上期毛利率",
        "",
        "四、审计关注",
        "1. 毛利率变动超过5个百分点的产品需重点分析原因。",
        "2. 单价变动超过20%的产品需检查是否符合定价政策。",
        "3. 关注是否存在联产品/副产品，如有应同时分析其毛利变化。",
        "",
        "五、数据来源",
        "从D4-2主营明细按产品汇总，或从ERP系统产品利润表导出。",
    ],
    "D4-4": [
        "D4-4 营业收入调整分录汇总表 编制说明",
        "",
        "一、本表目的",
        "汇总记录D4营业收入循环审计中发现的所有需要调整的会计分录。",
        "本表与调整分录模块双向联动，涉及科目6001/6051的调整自动同步。",
        "",
        "二、填写要求",
        "1. 「摘要」列：简要描述调整原因。",
        "2. 「分类」列：选择账项调整(AJE)/报表调整(RJE)/其他。",
        "3. 「会计科目」列：填写完整科目编码+名称，如 6001-主营业务收入。",
        "4. 「借方」「贷方」列：填写调整金额，借贷必须平衡。",
        "5. 「索引号」列：填写关联底稿索引（如D4-2）。",
        "",
        "三、联动说明",
        "1. 确认后自动更新D4-1审定表AJE/RJE列。",
        "2. 可推送至A13错报汇总表。",
        "3. 与调整分录模块双向同步（科目6001/6051范围内）。",
    ],
    "D4-12": [
        "D4-12 合同检查表 编制说明",
        "",
        "一、本表目的",
        "对收入确认所依据的重大合同进行检查，评价CAS14收入准则的应用。",
        "",
        "二、填写要求",
        "1. 选取重大/异常合同（金额较大、条款特殊、新客户、年末签署等）。",
        "2. 每份合同识别履约义务个数、交易价格分摊、收入确认时点/时段。",
        "3. 关注可变对价（折扣/返利/奖金条款）和合同变更的会计处理。",
        "",
        "三、审计关注",
        "1. 是否存在捆绑销售未拆分履约义务的情形。",
        "2. 可变对价是否使用了适当的估计方法（期望值法/最可能金额法）。",
        "3. 合同变更是否按CAS14进行了正确处理（作为单独合同/终止原合同等）。",
    ],
    "D4-14": [
        "D4-14 营业收入发生检查表（穿行测试）编制说明",
        "",
        "一、本表目的",
        "对收入交易进行穿行测试，追溯完整证据链（记账凭证→销售合同→出库单→运输单→签收单→发票→其他支持性文件），",
        "验证收入交易的发生认定，检查各维度数据一致性。",
        "",
        "二、表格结构（32列）",
        "本表每行代表一笔被检查的交易事项，按7个证据链维度横向展开：",
        "  序号 | 事项名称",
        "  凭证维度(7列): 月份/日期/编号/品名/数量/金额/记账日期",
        "  合同维度(5列): 编号/品名/金额/签发审批/签收确认",
        "  出库单维度(4列): 日期/品名/金额/仓库保管员",
        "  运输单维度(3列): 日期/品名/金额",
        "  签收单维度(3列): 日期/品名/金额",
        "  发票维度(3列): 日期/编号/金额",
        "  其他文件(2列): 文件描述/索引号",
        "  一致性分数 | 检查结论 | 备注",
        "",
        "三、填写要求",
        "1. 从序时账导入或手动添加待检查交易（至少覆盖收入总额60%）。",
        "2. 逐维度录入各环节的关键信息（编号/品名/金额/日期），可通过OCR附件自动识别。",
        "3. 销售合同维度可引用D4-12合同检查表已检查的合同数据。",
        "4. 系统自动交叉比对金额/品名/日期的一致性，生成0~100分的一致性分数。",
        "5. 根据一致性检验结果和人工判断，对每笔事项选择检查结论。",
        "",
        "四、检查结论选项",
        "  无异常 — 各维度数据一致，证据链完整",
        "  存在差异已解释 — 存在差异但已获取合理解释（在备注说明）",
        "  存在重大异常 — 发现不可解释的重大差异，需追加程序或报告",
        "",
        "五、灰底自动计算列",
        "  一致性分数列为系统自动计算，导入时忽略。",
    ],
    "D4-15": [
        "D4-15 营业收入完整性检查表 编制说明",
        "",
        "一、本表目的",
        "验证营业收入的完整性认定：所有应当记录的营业收入均已记录，",
        "所有应当包括在财务报表中的相关披露均已包括。",
        "",
        "二、审计过程",
        "1. 在报告期内选择一个重要时期，测试收入确认依据的资料文件（如发货单、验收单等）。",
        "2. 选定大额或者异常的项目进行测试（如果收入完整性评估为高风险，则应当采用抽样的方式）。",
        "3. 检查每个所选项目的单证，并追查到交易记录（如：销售日记账）。",
        "",
        "三、表格结构（18列）",
        "本表每行代表一笔从发货单出发追溯的交易，按3个维度横向展开：",
        "  序号",
        "  发货单维度(5列): 日期/编号/品名/数量/金额",
        "  发票维度(5列): 日期/编号/品名/数量/金额",
        "  记账凭证维度(5列): 日期/编号/品名/数量/金额",
        "  核核信息是否一致(√/×) | 备注",
        "",
        "四、填写要求",
        "1. 从发货单/出库单清单中选取样本（非从账簿出发），追溯到发票和记账凭证。",
        "2. 核对三个维度的品名、数量、金额是否一致。",
        "3. 「核核信息是否一致」列：三维度信息完全一致填√，存在差异填×并在备注说明。",
        "4. 关注是否存在已发货但未开票/未入账的情形（遗漏收入）。",
        "",
        "五、审计关注",
        "1. 测试方向为发货单→发票→凭证（与D4-14的凭证→单据方向相反）。",
        "2. 重点关注期末大额发货但次年才确认收入的情形。",
        "3. 结果写入下方审计说明和审计结论区域。",
    ],
    "D4-17": [
        "D4-17 营业收入截止测试（账到单据）编制说明",
        "",
        "一、本表目的",
        "测试期末收入是否存在跨期确认（从账簿→支持单据方向）。",
        "",
        "二、填写要求",
        "1. 选取资产负债表日前后N天的收入凭证。",
        "2. 追溯到发货单/签收单/验收单，确认收入确认时点正确。",
        "3. 标注是否跨期及跨期天数，>5天需进一步关注。",
    ],
    "D4-18": [
        "D4-18 营业收入截止测试（单据到账）编制说明",
        "",
        "一、本表目的",
        "测试期末是否有已发货未入账的收入（从单据→账簿方向）。",
        "",
        "二、填写要求",
        "1. 选取资产负债表日前后N天的发货/出库单据。",
        "2. 追溯到对应收入凭证，确认是否及时入账。",
        "3. 标注未入账项目，评估是否需要做截止调整。",
    ],
    "D4-22": [
        "D4-22 主营业务收入重要指标分析表 编制说明",
        "",
        "一、本表目的",
        "通过纵向（本期vs上期）和横向（与同行业公司）对比经营指标，",
        "分析主营业务收入变动的合理性，识别异常波动。",
        "",
        "二、填写要求",
        "1. 「指标名称」列已预填（12项固定指标），不可修改。",
        "2. 「本期」填写审计年度数据，「上期」填写上一会计年度数据。",
        "3. 「同行业公司」列可灵活扩展（选取业务模式相近的上市公司）。",
        "4. 「合理性分析」逐项填写变动原因及合理性判断。",
        "5. 自动计算指标（人均创收/ROP/运输费率）无需手动填写。",
        "",
        "三、导入说明",
        "1. 请勿修改第1行表头列名，否则导入校验失败。",
        "2. 指标名称列的文字应与模板完全一致。",
        "3. 如需添加同行业公司列，在表头追加列名即可。",
    ],
    "D4-23": [
        "D4-23 收入与开具发票金额比较分析 编制说明",
        "",
        "一、本表目的",
        "按月比较账面确认收入与开具发票金额的差异，",
        "识别是否存在虚假收入（有收入无发票）或隐瞒收入（有发票无收入）的迹象。",
        "",
        "二、填写要求",
        "1. 「月份」列已预填（1-12月），不可修改。",
        "2. 「主营业务收入」「其他业务收入」从账面取数，应与D4-2收入明细一致。",
        "3. 「增值税发票金额」「普通发票金额」从防伪税控系统或金税系统导出。",
        "4. 「营业收入合计」「开票金额合计」「差异」为自动计算列，无需填写。",
        "5. 「索引号」用于关联差异原因的证据底稿。",
        "",
        "三、导入说明",
        "1. 请勿修改第1行表头列名。",
        "2. 月份列文字应为'1月'~'12月'。",
        "3. 自动计算列的值导入时会被忽略（系统自动重算）。",
    ],
    "D4-35": [
        "D4-35 其他业务收入检查表 编制说明",
        "",
        "一、审计目标",
        "1.利润表中记录的其他业务收入已发生，且与被审计单位有关，已记录于恰当的账户。",
        "2.与其他业务收入有关的金额及其他数据已恰当记录，相关披露已得到恰当计量和描述。",
        "",
        "二、样本选取标准与规模",
        "测试总体：如借方发生额所有凭证共XX笔金额XX、贷方发生额所有凭证共XX笔金额XX。",
        "特定样本：XX金额以上（大额）、关联方/关联交易形成的款项、异常款项全部测试。",
        "抽样总体：测试总体扣除特定样本以外的样本。",
        "抽样方法：随机选样/系统选样/货币单元抽样/随意选样（非统计抽样适用）。",
        "抽样过程：使用IDEA等工具选择样本进行测试。",
        "",
        "三、测试内容说明",
        "核对1：原始凭证是否齐全。",
        "核对2：记账凭证与原始凭证是否相符。",
        "核对3：账务处理是否正确。",
        "核对4：是否记录于恰当的会计期间。",
        "核对5、6：可根据项目实际情况自定义补充检查内容。",
        "",
        "四、填写要求",
        "1. 每行对应一笔抽取的凭证/交易。",
        "2. 核对1~6列填√表示通过、留空表示不适用。",
        "3. 发现异常的行在「是否异常」列选择「是」。",
        "4. 合计行为系统自动汇总金额列。",
        "5. 检查比例 = 检查金额合计 ÷ 本期发生额（自动计算）。",
        "",
        "五、导入说明",
        "1. 请勿修改第1行表头列名。",
        "2. 核对列填「√」或留空。",
        "3. 是否异常列填「是」或「否」。",
    ],
}

# 通用编制说明（未单独定义的sheet）
_GENERIC_GUIDANCE = [
    "编制说明",
    "",
    "一、填写要求",
    "1. 按表头列名依次填写各字段数据。",
    "2. 金额列填写数值（正数），无需添加千分位。",
    "3. 日期格式：YYYY-MM-DD。",
    "4. 「备注」列用于记录审计发现或需关注事项。",
    "",
    "二、导入说明",
    "1. 请勿修改表头（第1行列名），否则导入时会校验失败。",
    "2. 空行将被自动跳过。",
    "3. 最多支持500行数据。",
]


def _get_guidance_text(sheet_code: str) -> list[str]:
    """获取sheet对应的编制说明文本"""
    return _SHEET_GUIDANCE.get(sheet_code, _GENERIC_GUIDANCE)
