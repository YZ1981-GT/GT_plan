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
import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import (
    authorize_wp_edit,
    authorize_wp_read,
    check_consol_lock,
    get_current_user,
)
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["d4-import-export"])


def _parse_wp_uuid(wp_id: str) -> UUID:
    """把路径参数 wp_id（str）解析为 UUID（供权限助手/合并锁使用）。

    非法 UUID → 404（与「底稿不存在」同语义，不泄露内部错误）。
    """
    try:
        return UUID(str(wp_id))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(404, "底稿不存在")

# ═══════════════════════════════════════════════════════════════════════════════
# Sheet 配置：每种sheet的列头定义
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

_SUPPORTED_SHEETS: set[str] = {
    "D4-1", "D4-2", "D4-3", "D4-4", "D4-6", "D4-7", "D4-8", "D4-9", "D4-10", "D4-11", "D4-12",
    "D4-13", "D4-14", "D4-15", "D4-16", "D4-17", "D4-18", "D4-19",
    # D4-20 主 sheet 是死配置（前端只用 provision/current/post 三子表，从不导入导出裸 D4-20）→ 删（DEC-1）
    "D4-20-provision", "D4-20-current", "D4-20-post",
    "D4-21", "D4-22", "D4-23", "D4-24", "D4-25", "D4-26", "D4-27",
    "D4-28", "D4-29", "D4-30", "D4-31", "D4-32",
    "D4-33", "D4-34-rental", "D4-34-consult", "D4-35", "D4-36-forward", "D4-36-backward",
}

_SHEET_HEADERS: dict[str, list[str]] = {
    "D4-13": [
        "区块", "内容",
    ],
    "D4-1": [
        "区块", "行键", "项目",
        "本期未审", "本期AJE", "本期RJE",
        "上期未审", "上期AJE", "上期RJE",
    ],
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
    # D4-9 重要客户结构：本期/上期两区各 Top10 + 4 总额。导出含期间标识 + 占比列（计算值，
    # 不可回导覆盖公式）。导入按「期间」列判本期/上期，按「客户名称=本期销售总额/上期销售总额」
    # 识别总额行（spec d4-9-customer-structure-bidirectional-writeback Req 6）。
    "D4-9": [
        "期间", "序号", "客户名称", "销售金额", "销售金额占比", "销售数量", "销售数量占比", "上期排名",
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
        "凭证月份", "凭证客户名称", "凭证日期", "凭证编号", "凭证品名", "凭证数量", "凭证金额", "记账日期",
        "合同日期", "合同编号", "合同品名", "合同金额", "签发审批", "签收确认",
        "出库日期", "出库编号", "出库品名", "出库数量", "出库金额", "仓库保管员", "发货审批人",
        "运输日期", "运输编号", "运输品名", "运输数量", "运输金额", "运输公司", "运输地址",
        "签收日期", "签收品名", "签收数量", "签收金额", "签收人", "盖章类型", "盖章单位",
        "发票日期", "发票编号", "发票品名", "发票数量", "发票金额",
        "其他文件描述", "其他索引号", "是否异常",
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
    # D4-20 主 sheet header 删除（死配置，DEC-1）：前端只用 provision/current/post 三子表
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
        "工商资料查询", "互联网信息查询", "函证", "视频、电话访谈", "实地走访", "索引号",
    ],
    "D4-29": [
        "客户名称", "统一社会信用代码", "注册地址", "办公地址", "网站地址", "网站IP地址",
        "企业邮箱", "成立时间", "注册资本/实缴资本", "经营范围", "人员规模/社保缴纳人数",
        "法定代表人", "股东1及持股比例", "股东2及持股比例", "股东3及持股比例",
        "董事长", "总经理", "关键经办人员", "实际控制人",
        "是否为关联方", "是否同时为供应商", "开始合作时间",
        "是否长期拖欠款项", "经营状态", "是否列入失信人", "信息来源",
    ],
    # D4-30 客户访谈记录汇总表：转置矩阵在导出侧投影为「一客户一行」(客户名称 + 16 访谈维度列)
    # 自定义维度(customDimensions)作为尾部动态列追加(仿 D4-22 peers)，导入按表头恢复。
    "D4-30": [
        "客户名称", "访谈时间", "访谈原因", "访谈方式", "被访谈公司注册地址",
        "实地走访公司地址", "接受访谈人员及身份", "参与访谈的审计人员", "参与访谈的其他人员",
        "访谈人员行程信息", "是否现场函证", "访谈关注要点", "合同执行核对情况",
        "交易金额核对是否一致", "往来余额核对是否一致", "访谈结论", "访谈表索引",
    ],
    # D4-31 客户访谈记录：单份问卷，导出为「字段/值」键值对(单对象非行集)
    "D4-31": [
        "字段", "值",
    ],
    # D4-32 资金流水检查：6 组扁平化时加显式「组别」列，导入按组别恢复分组(非按行号硬切)
    "D4-32": [
        "组别", "序号", "单位名称/姓名", "本期交易金额", "占同类交易比例",
        "开户银行", "账号", "资金流水获取途径", "是否发现异常交易", "索引号",
    ],
    "D4-33": [
        "月份",
        "合计-收入", "合计-成本", "合计-毛利率",
        "出租固定资产-收入", "出租固定资产-成本", "出租固定资产-毛利率",
        "出租无形资产-收入", "出租无形资产-成本", "出租无形资产-毛利率",
        "销售材料-收入", "销售材料-成本", "销售材料-毛利率",
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
    """导出空白模板xlsx（含表头+格式+编制说明，无数据行）

    权限门禁（P0-项5）：读操作，按 readonly 项目权限收口（``authorize_wp_read``），
    不误伤只读成员，但拒绝非项目成员。
    """
    await authorize_wp_read(db, current_user, _parse_wp_uuid(wp_id))
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

    # D4-13特殊处理：预填两行区块名（核对过程/核对结论），叙述式
    if sheet == "D4-13":
        ws.append(["核对过程", None])
        ws.append(["核对结论", None])

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
    """导出当前数据xlsx

    权限门禁（P0-项5）：读操作，按 readonly 项目权限收口（``authorize_wp_read``）。
    """
    await authorize_wp_read(db, current_user, _parse_wp_uuid(wp_id))
    _validate_sheet(sheet)
    if sheet == "D4-13":
        return await _handle_d4_13_export(wp_id, db)
    headers = _get_headers(sheet)

    # 加载 checklist_responses 中的行数据
    import sqlalchemy as sa

    item_id = f"{sheet}-rows"
    if sheet == "D4-1":
        item_id = "D4-1-adj-rows"
    elif sheet == "D4-6":
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
    elif sheet == "D4-15":
        item_id = "D4-15-items"
    elif sheet == "D4-22":
        item_id = "D4-22-data"
    elif sheet == "D4-23":
        item_id = "D4-23-data"
    elif sheet == "D4-33":
        item_id = "D4-33-data"
    elif sheet in ("D4-34-rental", "D4-34-consult"):
        item_id = "D4-34-data"
    elif sheet == "D4-35":
        item_id = "D4-35-data"
    elif sheet in ("D4-36-forward", "D4-36-backward"):
        item_id = "D4-36-data"
    elif sheet == "D4-29":
        item_id = "D4-29-customers"
    elif sheet == "D4-30":
        item_id = "D4-30-customers"
    elif sheet == "D4-31":
        item_id = "D4-31-interview"
    elif sheet == "D4-32":
        item_id = "D4-32-groups"
    # D4-20 子表键错位修复（DEC-2，导出侧与导入侧对称）
    elif sheet == "D4-20-current":
        item_id = "D4-20-current-returns"
    elif sheet == "D4-20-post":
        item_id = "D4-20-post-returns"
    elif sheet == "D4-20-provision":
        item_id = "D4-20-provision"
    result = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
        ),
        {"wp_id": wp_id, "item_id": item_id},
    )
    row = result.fetchone()

    # D4-31 单份问卷：键值对导出（单对象非行集），字段顺序固定
    if sheet == "D4-31":
        data: dict = {}
        if row and row.remark:
            try:
                _p = json.loads(row.remark)
                if isinstance(_p, dict):
                    data = _p
            except (json.JSONDecodeError, TypeError):
                pass
        return _export_d4_31_questionnaire(sheet, data)

    rows_data: list[dict] = []
    _d4_33_store: dict = {}  # D4-33 嵌套 store（bizTypes/months/priorYear），循环后展开
    _d4_30_custom_dims: list[dict] = []  # D4-30 自定义维度（尾部动态列）
    _d4_10_formula_meta: dict | None = None  # D4-10 公式真源元数据（随行导出）
    if row and row.remark:
        try:
            parsed = json.loads(row.remark)
            # D4-22 stores {rows: [...], peers: [...], transportExpense: ...}
            if sheet == "D4-22" and isinstance(parsed, dict):
                rows_data = parsed.get("rows", [])
            # D4-29 stores [{id,name,fields}]（客户列表，一客户一行）
            elif sheet == "D4-29" and isinstance(parsed, list):
                rows_data = parsed
            # D4-30 stores {customers:[...], customDimensions:[...]}（转置矩阵投影为一客户一行）
            elif sheet == "D4-30" and isinstance(parsed, dict):
                rows_data = parsed.get("customers", [])
                _d4_30_custom_dims = parsed.get("customDimensions", []) or []
            # D4-32 stores [{key,rows}]×6（+ 可能 __unknown__ 组）→ 扁平化加组别列
            elif sheet == "D4-32" and isinstance(parsed, list):
                _flat: list[dict] = []
                for _g in parsed:
                    if not isinstance(_g, dict):
                        continue
                    _gkey = _g.get("key", "")
                    _glabel = _D4_32_GROUP_KEY_TO_LABEL.get(_gkey, _gkey)
                    for _seq, _r in enumerate(_g.get("rows", []), start=1):
                        _rr = dict(_r)
                        # 未知组别（__unknown__）保真：优先用每行保留的原始来源 label（中文），
                        # 不能用 key→label 查表退化成字面量 "__unknown__"，否则往返丢原始组别名。
                        if _gkey == "__unknown__":
                            _rr["_groupLabel"] = _rr.get("groupLabel") or _glabel
                        else:
                            _rr["_groupLabel"] = _glabel
                        _rr["_seq"] = _seq
                        _flat.append(_rr)
                rows_data = _flat
            # D4-9 stores {current:{rows,totalAmount,totalQuantity}, prior:{…}} →
            # 导出本期区（数据行 + 总额行）+ 上期区（数据行 + 总额行），每行带 _period/_seq，
            # 总额行 _isTotal=True。占比列由 row-builder 计算导出（不可回导覆盖公式）。
            elif sheet == "D4-9" and isinstance(parsed, dict):
                rows_data = _build_d4_9_export_rows(parsed)
            # D4-10 stores {rows, totalAmount, formula…}
            elif sheet == "D4-10" and isinstance(parsed, dict):
                rows_data = parsed.get("rows", []) or []
                _d4_10_formula_meta = {
                    "totalAmount": parsed.get("totalAmount", 0),
                    "totalQuantity": parsed.get("totalQuantity", 0),
                    "totalAmountManualOverride": parsed.get(
                        "totalAmountManualOverride", False
                    ),
                    "totalAmountFormulaRef": parsed.get("totalAmountFormulaRef")
                    or "WP('D4-2','本期未审合计')",
                }
            # D4-34 stores {rentals: [...], consults: [...]}；按导出子区取对应区
            elif sheet == "D4-34-rental" and isinstance(parsed, dict):
                rows_data = parsed.get("rentals", [])
            elif sheet == "D4-34-consult" and isinstance(parsed, dict):
                rows_data = parsed.get("consults", [])
            # D4-35 stores {rows: [...], sampling: {...}, periodAmount: ...}
            elif sheet == "D4-35" and isinstance(parsed, dict):
                rows_data = parsed.get("rows", [])
            # D4-36 stores {forward: [...], backward: [...]}；按导出子区取对应区
            elif sheet == "D4-36-forward" and isinstance(parsed, dict):
                rows_data = parsed.get("forward", [])
            elif sheet == "D4-36-backward" and isinstance(parsed, dict):
                rows_data = parsed.get("backward", [])
            # D4-33 stores {bizTypes: [...], months: {...}, priorYear: {...}}（嵌套，循环后特殊展开）
            elif sheet == "D4-33" and isinstance(parsed, dict):
                rows_data = []  # D4-33 由循环后专属分支从 parsed 展开
                _d4_33_store = parsed
            elif isinstance(parsed, list):
                rows_data = parsed
            else:
                rows_data = parsed
        except (json.JSONDecodeError, TypeError):
            pass

    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    # D4-30 自定义维度作尾部动态列追加到表头
    if sheet == "D4-30" and _d4_30_custom_dims:
        headers = list(headers) + [str(d.get("label", d.get("key", ""))) for d in _d4_30_custom_dims]
    ws.append(headers)
    ws.freeze_panes = "A2"

    # 写入数据行
    for data_row in rows_data:
        if sheet == "D4-1":
            row_values = _export_d4_1_row(data_row)
        elif sheet == "D4-29":
            _fields = data_row.get("fields", {}) or {}
            row_values = [data_row.get("name", "")] + [
                _fields.get(_D4_29_HEADER_TO_KEY[h], "") for h in headers if h in _D4_29_HEADER_TO_KEY
            ]
        elif sheet == "D4-30":
            _fields = data_row.get("fields", {}) or {}
            _rv = [data_row.get("name", "")]
            for h in headers:
                if h == "客户名称":
                    continue
                if h in _D4_30_HEADER_TO_KEY:
                    _rv.append(_fields.get(_D4_30_HEADER_TO_KEY[h], ""))
                else:
                    # 自定义维度列：key=label（与 parse 侧一致）
                    _rv.append(_fields.get(h, ""))
            row_values = _rv
        elif sheet == "D4-32":
            _amt = data_row.get("amount", "")
            row_values = [
                data_row.get("_groupLabel", ""),
                data_row.get("_seq", "") or "",
                data_row.get("name", ""),
                _safe_float(_amt) if _amt not in (None, "") else "",
                data_row.get("ratio", ""),
                data_row.get("bank", ""),
                data_row.get("account", ""),
                data_row.get("method", ""),
                data_row.get("hasAnomaly", ""),
                data_row.get("indexRef", ""),
            ]
        elif sheet == "D4-2":
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
        elif sheet == "D4-15":
            # D4-15 完整性检查：嵌套 {delivery,invoice,voucher} → 18列平铺
            d = data_row.get("delivery", {})
            inv = data_row.get("invoice", {})
            v = data_row.get("voucher", {})
            _consistent = data_row.get("isConsistent")
            _consistent_cell = "√" if _consistent is True else ("×" if _consistent is False else "")
            row_values = [
                data_row.get("indexNo", ""),
                d.get("date", ""), d.get("number", ""), d.get("productName", ""), d.get("quantity", ""), _safe_float(d.get("amount")),
                inv.get("date", ""), inv.get("number", ""), inv.get("productName", ""), inv.get("quantity", ""), _safe_float(inv.get("amount")),
                v.get("date", ""), v.get("number", ""), v.get("productName", ""), v.get("quantity", ""), _safe_float(v.get("amount")),
                _consistent_cell,
                data_row.get("remark", ""),
            ]
        elif sheet == "D4-16":
            # D4-16 出口核对：ExportCheckRow 英文 key → 中文列头，差异列重算
            _book = _safe_float(data_row.get("bookAmount"))
            _ports = _safe_float(data_row.get("portsAmount"))
            _tax = _safe_float(data_row.get("taxReportAmount"))
            row_values = [
                data_row.get("indexNo", ""),
                _book,
                data_row.get("portsPeriod", ""),
                _ports,
                _book - _ports,
                data_row.get("portsReason", ""),
                _tax,
                _book - _tax,
                data_row.get("taxReason", ""),
                data_row.get("taxIndex", ""),
            ]
        elif sheet == "D4-14":
            # D4-14 穿行测试：TransactionItem → 48列平铺（路线A全受管，与 _SHEET_HEADERS["D4-14"] 严格同序）
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
                v.get("month", ""), v.get("customerName", ""), v.get("date", ""), v.get("number", ""),
                v.get("productName", ""), v.get("quantity", ""), _safe_float(v.get("amount")), v.get("accountingDate", ""),
                c.get("date", ""), c.get("number", ""), c.get("productName", ""), _safe_float(c.get("amount")),
                c.get("approver", ""), c.get("confirmor", ""),
                d.get("date", ""), d.get("number", ""), d.get("productName", ""), d.get("quantity", ""),
                _safe_float(d.get("amount")), d.get("warehouseKeeper", ""), d.get("shippingApprover", ""),
                s.get("date", ""), s.get("number", ""), s.get("productName", ""), s.get("quantity", ""),
                _safe_float(s.get("amount")), s.get("company", ""), s.get("address", ""),
                r.get("date", ""), r.get("productName", ""), r.get("quantity", ""), _safe_float(r.get("amount")),
                r.get("signer", ""), r.get("sealType", ""), r.get("sealEntity", ""),
                inv.get("date", ""), inv.get("number", ""), inv.get("productName", ""), inv.get("quantity", ""), _safe_float(inv.get("amount")),
                o.get("description", ""), o.get("indexNo", ""), o.get("anomalyNote", ""),
                data_row.get("consistencyScore", 0),
                data_row.get("conclusion", ""),
                "",  # 备注
            ]
        elif sheet == "D4-17":
            # D4-17 截止（账到单据）：凭证→发货单；是否跨期派生列导出留空（前端 checkCutoff 重算）
            row_values = [
                "",  # 序号
                data_row.get("voucherDate", ""), data_row.get("voucherNo", ""), data_row.get("voucherProduct", ""),
                data_row.get("voucherQty", ""), _safe_float(data_row.get("voucherAmount")),
                data_row.get("deliveryDate", ""), data_row.get("deliveryNo", ""), data_row.get("deliveryProduct", ""),
                data_row.get("deliveryQty", ""), _safe_float(data_row.get("deliveryAmount")),
                "",  # 是否跨期（派生，前端 checkCutoff 重算，导出留空）
                data_row.get("remark", ""),
            ]
        elif sheet == "D4-18":
            # D4-18 截止（单据到账）：发货单→凭证
            row_values = [
                "",
                data_row.get("deliveryDate", ""), data_row.get("deliveryNo", ""), data_row.get("deliveryProduct", ""),
                data_row.get("deliveryQty", ""), _safe_float(data_row.get("deliveryAmount")),
                data_row.get("voucherDate", ""), data_row.get("voucherNo", ""), data_row.get("voucherProduct", ""),
                data_row.get("voucherQty", ""), _safe_float(data_row.get("voucherAmount")),
                "",  # 是否跨期（派生）
                data_row.get("remark", ""),
            ]
        elif sheet == "D4-19":
            # D4-19 销售折扣与折让：折扣比例派生列导出留空（前端重算）
            row_values = [
                "",  # 序号
                data_row.get("customerName", ""),
                data_row.get("discountType", ""),
                _safe_float(data_row.get("revenueAmount")),
                _safe_float(data_row.get("discountAmount")),
                "",  # 折扣比例（派生，前端 calcRate 重算）
                data_row.get("reason", ""),
                data_row.get("voucherDate", ""),
                data_row.get("voucherNo", ""),
                data_row.get("accountSubject", ""),
                data_row.get("detailSubject", ""),
                _safe_float(data_row.get("debitAmount")),
                _safe_float(data_row.get("creditAmount")),
                data_row.get("approvalDate", ""),
                data_row.get("approver", ""),
                data_row.get("remark", ""),
            ]
        elif sheet in ("D4-20-current", "D4-20-post"):
            # D4-20 退货明细（current/post 同构 ReturnCheckRow）
            row_values = [
                "",  # 序号
                data_row.get("voucherDate", ""), data_row.get("voucherNo", ""),
                data_row.get("bizContent", ""), data_row.get("subjectName", ""), data_row.get("detailSubject", ""),
                _safe_float(data_row.get("debitAmount")), _safe_float(data_row.get("creditAmount")),
                data_row.get("customerName", ""), data_row.get("productName", ""),
                data_row.get("returnQty", ""), _safe_float(data_row.get("returnAmount")),
                data_row.get("returnReason", ""),
                data_row.get("hasLitigation", ""), data_row.get("isAbnormal", ""),
                data_row.get("indexRef", ""),
            ]
        elif sheet == "D4-20-provision":
            # D4-20 退货计提：应计提/差异派生列导出留空（前端 calcProvision 重算）
            row_values = [
                "",  # 序号
                data_row.get("productName", ""),
                _safe_float(data_row.get("base")),
                _safe_float(data_row.get("rate")),
                "",  # 应计提金额（派生）
                _safe_float(data_row.get("alreadyProvided")),
                "",  # 差异金额（派生）
                data_row.get("diffReason", ""),
            ]
        elif sheet == "D4-21":
            # D4-21 关联方销售/价格：camelCase store 键 → 中文列头顺序。
            # 差异率/差异率(公允) 是派生列，导出侧按公式重算供展示（导入侧忽略，Req 4.2）。
            _g = _safe_float(data_row.get("avgPrice"))
            _h = _safe_float(data_row.get("nonrelatedAvgPrice"))
            _j = _safe_float(data_row.get("fairPrice"))
            _diff_nr = round((_g - _h) / _h * 100, 2) if _h else ""
            _diff_fair = round((_g - _j) / _j * 100, 2) if _j else ""
            row_values = [
                "",  # 序号（展示列，导入忽略）
                data_row.get("partyName", ""),
                data_row.get("relationship", ""),
                data_row.get("product", ""),
                _safe_float(data_row.get("qty")),
                _safe_float(data_row.get("salesAmount")),
                _safe_float(data_row.get("salesRatio")),
                _g,
                _h,
                _diff_nr,          # 差异率（派生，展示用）
                _j,
                _diff_fair,        # 差异率(公允)（派生，展示用）
                _safe_float(data_row.get("priorSalesRatio")),
                _safe_float(data_row.get("priorAvgPrice")),
                data_row.get("remark", ""),
            ]
        elif sheet == "D4-24":
            # D4-24 第三方回款：camelCase store 键 → 中文列头顺序（无派生列）。
            row_values = [
                "",  # 序号（展示列，导入忽略）
                data_row.get("customerName", ""),
                _safe_float(data_row.get("annualSales")),
                _safe_float(data_row.get("endingAr")),
                _safe_float(data_row.get("thirdPartyAmount")),
                data_row.get("payerName", ""),
                data_row.get("reason", ""),
                data_row.get("payerCustomerRelation", ""),
                data_row.get("payerEntityRelation", ""),
                data_row.get("hasPaymentAgreement", ""),
                data_row.get("isConfirmed", ""),
                data_row.get("rationality", ""),
                data_row.get("indexNo", ""),
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
        elif sheet == "D4-33":
            # D4-33 嵌套结构，由循环后专属分支展开（此处不应有行）
            continue
        elif sheet == "D4-9":
            # 期间/序号/客户名称/销售金额/销售金额占比/销售数量/销售数量占比/上期排名。
            # 占比 = 计算值（金额/总额），导出供人读，不可回导（parser 忽略占比列）。
            _period = data_row.get("_period", "本期")
            _amt = _safe_float(data_row.get("amount"))
            _qty = _safe_float(data_row.get("quantity"))
            _ta = _safe_float(data_row.get("_totalAmount"))
            _tq = _safe_float(data_row.get("_totalQuantity"))
            _amt_ratio = (_amt / _ta) if _ta else 0.0
            _qty_ratio = (_qty / _tq) if _tq else 0.0
            if data_row.get("_isTotal"):
                # 总额行：客户名称列写「本期销售总额」/「上期销售总额」，金额/数量为总额。
                row_values = [
                    _period,
                    "",
                    "本期销售总额" if _period == "本期" else "上期销售总额",
                    _ta,
                    "",
                    _tq,
                    "",
                    "",
                ]
            else:
                row_values = [
                    _period,
                    data_row.get("_seq", ""),
                    data_row.get("name", ""),
                    _amt,
                    _amt_ratio,
                    _qty,
                    _qty_ratio,
                    data_row.get("priorRank", ""),
                ]
        elif sheet == "D4-10":
            row_values = [
                data_row.get("customer", ""),
                data_row.get("product", ""),
                _safe_float(data_row.get("amount")),
                _safe_float(data_row.get("quantity")),
                _safe_float(data_row.get("unitPrice")),
                _safe_float(data_row.get("avgPrice")),
                data_row.get("avgReason", ""),
                _safe_float(data_row.get("marketPrice")),
                data_row.get("marketReason", ""),
            ]
        elif sheet == "D4-11":
            row_values = [
                data_row.get("customer", ""),
                data_row.get("product", ""),
                _safe_float(data_row.get("unitPrice")),
                _safe_float(data_row.get("quantity")),
                data_row.get("invoiceDate", ""),
                data_row.get("orderNo", ""),
                data_row.get("orderDate", ""),
                _safe_float(data_row.get("listPrice")),
                _safe_float(data_row.get("marketPrice")),
                data_row.get("reason", ""),
                data_row.get("priceSource", ""),
                data_row.get("remark", ""),
            ]
        elif sheet == "D4-34-rental":
            row_values = _export_d4_34_rental_row(data_row)
        elif sheet == "D4-34-consult":
            row_values = _export_d4_34_consult_row(data_row)
        elif sheet == "D4-35":
            row_values = _export_d4_35_row(data_row)
        elif sheet == "D4-36-forward":
            row_values = _export_d4_36_forward_row(data_row)
        elif sheet == "D4-36-backward":
            row_values = _export_d4_36_backward_row(data_row)
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

    # D4-33 special: 按实际 bizTypes 动态列头 + 展开 16 行（12月+合计+上年数+变动额+变动比例）
    if sheet == "D4-33":
        biz_types = _d4_33_store.get("bizTypes", []) if isinstance(_d4_33_store, dict) else []
        months_map = _d4_33_store.get("months", {}) if isinstance(_d4_33_store, dict) else {}
        prior_map = _d4_33_store.get("priorYear", {}) if isinstance(_d4_33_store, dict) else {}
        # 用动态列头覆盖首行（合计3列 + 每业务类型3列）
        dyn_headers = _d4_33_dynamic_headers(biz_types)
        ws.delete_rows(1)  # 删掉先前 append 的静态 headers
        ws.insert_rows(1)
        for c_idx, h in enumerate(dyn_headers, start=1):
            ws.cell(row=1, column=1 + (c_idx - 1), value=h)
        _write_d4_33_rows(ws, biz_types, months_map, prior_map)

    # D4-10：附加「公式元数据」sheet，保证导出可再导入时还原 preset/override
    if sheet == "D4-10" and _d4_10_formula_meta is not None:
        meta_ws = wb.create_sheet("公式元数据")
        meta_ws.append(["字段", "值"])
        for key in (
            "totalAmount",
            "totalQuantity",
            "totalAmountManualOverride",
            "totalAmountFormulaRef",
        ):
            meta_ws.append([key, _d4_10_formula_meta.get(key, "")])

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
    base_version: int | None = Query(
        None,
        description="乐观锁基线版本（If-Match）。提供时若服务端当前版本不符返回409；不提供按创建/覆盖处理。",
    ),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """解析上传xlsx，校验格式，写入 checklist_responses

    权限门禁（P0-项5）：导入是**写操作**，函数体首句显式校验目标底稿编辑权
    （``authorize_wp_edit`` —— readonly/qc/非项目成员 → 403，底稿不存在 → 404），
    并检查合并锁（``check_consol_lock`` —— 锁定 → 423）。校验先于任何 xlsx 解析与
    DB 写入，任何早退分支（含 D4-13）都在其后，确保无权者不产生任何数据变更。

    并发一致性（P0-项4）：写入走 ``_upsert_checklist_response`` 乐观锁。传 ``base_version``
    时做 If-Match 冲突检测（版本不符 → 409，不静默覆盖）；不传时按创建/覆盖处理（兼容旧客户端）。
    响应回带 ``content_version`` 供客户端下次 If-Match。
    """
    _wp_uuid = _parse_wp_uuid(wp_id)
    await authorize_wp_edit(db, current_user, _wp_uuid)
    await check_consol_lock(wp_id=_wp_uuid, db=db)

    _validate_sheet(sheet)

    if sheet == "D4-13":
        return await _handle_d4_13_import(wp_id, file, db, base_version=base_version)

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

    # D4-10：单独打开一份 workbook 读「公式元数据」副表（避免 read_only 主表迭代冲突）
    _d4_10_xlsx_meta: dict = {}
    if sheet == "D4-10":
        try:
            wb_meta = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            _d4_10_xlsx_meta = _extract_d4_10_formula_meta_from_wb(wb_meta)
            wb_meta.close()
        except Exception:
            _d4_10_xlsx_meta = {}

    errors: list[str] = []
    if sheet == "D4-33":
        # D4-33 业务类型列是动态的，只校验固定列（月份 + 合计三列）
        _d4_33_fixed = ["月份", "合计-收入", "合计-成本", "合计-毛利率"]
        missing_cols = [h for h in _d4_33_fixed if h not in actual_headers]
    else:
        missing_cols = [h for h in expected_headers if h not in actual_headers]
    if missing_cols:
        errors.append(f"缺少列: {', '.join(missing_cols)}")

    if errors:
        return {"ok": False, "errors": errors, "imported_count": 0}

    # D4-31 单份问卷：键值对 → 单对象，item_id=D4-31-interview（非行集，独立落库）
    if sheet == "D4-31":
        import sqlalchemy as sa
        from uuid import uuid4

        data = _parse_d4_31_questionnaire(ws, actual_headers)
        wb.close()
        remark_json = json.dumps(data, ensure_ascii=False)
        project_id = await _resolve_project_id(db, wp_id)
        new_version = await _upsert_checklist_response(
            db,
            project_id=project_id,
            wp_id=wp_id,
            item_id="D4-31-interview",
            remark=remark_json,
            base_version=base_version,
        )
        await db.commit()
        return {"ok": True, "imported_count": 1 if data else 0, "errors": [], "content_version": new_version}

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

        if sheet == "D4-1":
            row_dict = _parse_d4_1_row(row, actual_headers, expected_headers)
        elif sheet == "D4-2":
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
        elif sheet == "D4-9":
            row_dict = _parse_d4_9_row(row, actual_headers)
        elif sheet == "D4-10":
            row_dict = _parse_d4_10_row(row, actual_headers)
        elif sheet == "D4-11":
            row_dict = _parse_d4_11_row(row, actual_headers)
        elif sheet == "D4-14":
            row_dict = _parse_d4_14_row(row, actual_headers)
        elif sheet == "D4-15":
            row_dict = _parse_d4_15_row(row, actual_headers)
        elif sheet == "D4-16":
            row_dict = _parse_d4_16_row(row, actual_headers)
        elif sheet == "D4-17":
            row_dict = _parse_d4_17_row(row, actual_headers)
        elif sheet == "D4-18":
            row_dict = _parse_d4_18_row(row, actual_headers)
        elif sheet == "D4-19":
            row_dict = _parse_d4_19_row(row, actual_headers)
        elif sheet in ("D4-20-current", "D4-20-post"):
            row_dict = _parse_d4_20_return_row(row, actual_headers)
        elif sheet == "D4-20-provision":
            row_dict = _parse_d4_20_provision_row(row, actual_headers)
        elif sheet == "D4-21":
            row_dict = _parse_d4_21_row(row, actual_headers)
        elif sheet == "D4-24":
            row_dict = _parse_d4_24_row(row, actual_headers)
        elif sheet == "D4-22":
            row_dict = _parse_d4_22_row(row, actual_headers)
        elif sheet == "D4-23":
            row_dict = _parse_d4_23_row(row, actual_headers)
        elif sheet == "D4-29":
            row_dict = _parse_d4_29_row(row, actual_headers)
        elif sheet == "D4-30":
            row_dict = _parse_d4_30_row(row, actual_headers)
        elif sheet == "D4-32":
            row_dict = _parse_d4_32_row(row, actual_headers)
        elif sheet == "D4-33":
            row_dict = _parse_d4_33_row(row, actual_headers)
        elif sheet == "D4-34-rental":
            row_dict = _parse_d4_34_rental_row(row, actual_headers)
        elif sheet == "D4-34-consult":
            row_dict = _parse_d4_34_consult_row(row, actual_headers)
        elif sheet == "D4-35":
            row_dict = _parse_d4_35_row(row, actual_headers)
        elif sheet == "D4-36-forward":
            row_dict = _parse_d4_36_forward_row(row, actual_headers)
        elif sheet == "D4-36-backward":
            row_dict = _parse_d4_36_backward_row(row, actual_headers)
        else:
            row_dict = _parse_generic_row(row, actual_headers)

        if not row_dict:
            continue
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

    # D4-33 post-processing: 行(每月一行含各业务列) → {bizTypes, months, priorYear} 嵌套 store
    d4_33_store: dict | None = None
    if sheet == "D4-33":
        d4_33_store = _rebuild_d4_33_store(rows_data, actual_headers)

    # 写入 checklist_responses
    import sqlalchemy as sa
    from uuid import uuid4

    item_id = f"{sheet}-rows"
    if sheet == "D4-1":
        item_id = "D4-1-adj-rows"
    elif sheet == "D4-6":
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
    elif sheet == "D4-15":
        item_id = "D4-15-items"
    elif sheet == "D4-22":
        item_id = "D4-22-data"
    elif sheet == "D4-23":
        item_id = "D4-23-data"
    elif sheet == "D4-33":
        item_id = "D4-33-data"
    elif sheet in ("D4-34-rental", "D4-34-consult"):
        item_id = "D4-34-data"
    elif sheet == "D4-35":
        item_id = "D4-35-data"
    elif sheet in ("D4-36-forward", "D4-36-backward"):
        item_id = "D4-36-data"
    elif sheet == "D4-29":
        item_id = "D4-29-customers"
    elif sheet == "D4-30":
        item_id = "D4-30-customers"
    elif sheet == "D4-32":
        item_id = "D4-32-groups"
    # 🔴 D4-20 子表键错位修复（DEC-2：改后端映射对齐前端键，不改前端键）：
    #   前端 store 用 D4-20-current-returns / D4-20-post-returns（6 处引用），
    #   sheet 码 D4-20-current / D4-20-post 默认会落 {sheet}-rows 前端读不到。
    elif sheet == "D4-20-current":
        item_id = "D4-20-current-returns"
    elif sheet == "D4-20-post":
        item_id = "D4-20-post-returns"
    elif sheet == "D4-20-provision":
        item_id = "D4-20-provision"  # 前端键即 D4-20-provision（非 {sheet}-rows）

    async def _load_existing(iid: str) -> dict:
        """读取既有 item_id 的 remark（dict），用于多子区合并写回；损坏/缺失返回空 dict。"""
        _res = await db.execute(
            sa.text("SELECT remark FROM checklist_responses WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"),
            {"wp_id": wp_id, "item_id": iid},
        )
        _r = _res.fetchone()
        if _r and _r.remark:
            try:
                _d = json.loads(_r.remark)
                if isinstance(_d, dict):
                    return _d
            except (json.JSONDecodeError, TypeError):
                pass
        return {}

    # D4-22 特殊：保留已有peers和transportExpense，只替换rows
    if sheet == "D4-22":
        existing_data = await _load_existing(item_id)
        # 合并：导入的rows替换，peers/transportExpense保留
        merged = {
            "rows": rows_data,
            "peers": existing_data.get("peers", []),
            "transportExpense": existing_data.get("transportExpense", ""),
        }
        remark_json = json.dumps(merged, ensure_ascii=False)
    elif sheet == "D4-33":
        # D4-33 一次导入即完整 store（含全部月份/业务），整体写回
        remark_json = json.dumps(d4_33_store or {"bizTypes": [], "months": {}, "priorYear": {}}, ensure_ascii=False)
    elif sheet == "D4-34-rental":
        # 合并写回：替换 rentals，保留既有 consults
        existing_data = await _load_existing(item_id)
        merged = {"rentals": rows_data, "consults": existing_data.get("consults", [])}
        remark_json = json.dumps(merged, ensure_ascii=False)
    elif sheet == "D4-34-consult":
        # 合并写回：替换 consults，保留既有 rentals
        existing_data = await _load_existing(item_id)
        merged = {"rentals": existing_data.get("rentals", []), "consults": rows_data}
        remark_json = json.dumps(merged, ensure_ascii=False)
    elif sheet == "D4-35":
        # 合并写回：替换 rows，保留既有 sampling/periodAmount（抽样设计不被行导入冲掉）
        existing_data = await _load_existing(item_id)
        merged = {
            "rows": rows_data,
            "sampling": existing_data.get("sampling", {}),
            "periodAmount": existing_data.get("periodAmount", ""),
        }
        remark_json = json.dumps(merged, ensure_ascii=False)
    elif sheet == "D4-36-forward":
        # 合并写回：替换 forward，保留既有 backward 及配置
        existing_data = await _load_existing(item_id)
        merged = dict(existing_data)
        merged["forward"] = rows_data
        merged.setdefault("backward", existing_data.get("backward", []))
        remark_json = json.dumps(merged, ensure_ascii=False)
    elif sheet == "D4-36-backward":
        # 合并写回：替换 backward，保留既有 forward 及配置
        existing_data = await _load_existing(item_id)
        merged = dict(existing_data)
        merged["backward"] = rows_data
        merged.setdefault("forward", existing_data.get("forward", []))
        remark_json = json.dumps(merged, ensure_ascii=False)
    elif sheet == "D4-30":
        # 一客户一行 → {customers, customDimensions}（自定义维度按尾部动态列并集恢复）
        remark_json = json.dumps(_reshape_d4_30_rows(rows_data), ensure_ascii=False)
    elif sheet == "D4-32":
        # 扁平行 → 6 组 [{key,rows}]（显式组别列恢复，未知组别独立保留供人工映射）
        remark_json = json.dumps(_reshape_d4_32_rows(rows_data), ensure_ascii=False)
    elif sheet == "D4-10":
        # 🔴 D4-10 HTML store 是 dict（{rows, totalAmount, formula…}），不得整表写成裸数组。
        # 导入只替换 rows；总额/公式覆盖位保留既有值（公式真源不被 I/O 冲掉）。
        # 若 xlsx 含「公式元数据」副表，用其补全空缺位（导出往返）。
        existing_data = await _load_existing(item_id)
        merged = merge_d4_10_import_rows(existing_data, rows_data, _d4_10_xlsx_meta)
        remark_json = json.dumps(merged, ensure_ascii=False)
    elif sheet == "D4-9":
        # D4-9 store = {current:{rows,totalAmount,totalQuantity}, prior:{…}}。
        # rows_data 含本期/上期两区数据行 + 总额行（_isTotal），按 _period 分流回两区；
        # 每区导入替换其 rows（补 rowId）+ 用总额行回填 totalAmount/totalQuantity；
        # 缺某区数据时保留既有值（避免冲掉对侧期间）。占比列已在 parser 忽略（Req 6.4）。
        existing_data = await _load_existing(item_id)
        current = dict(existing_data.get("current") or {})
        prior = dict(existing_data.get("prior") or {})

        def _region_from_import(period: str, base: dict) -> dict:
            out = dict(base)
            data_rows = [
                {k: v for k, v in r.items() if not k.startswith("_")}
                for r in rows_data
                if isinstance(r, dict) and not r.get("_isTotal") and r.get("_period") == period
            ]
            total_rows = [
                r for r in rows_data
                if isinstance(r, dict) and r.get("_isTotal") and r.get("_period") == period
            ]
            # 有导入数据行才替换该区 rows（否则保留既有，不冲掉对侧/空导入）。
            if data_rows:
                out["rows"] = data_rows
            else:
                out.setdefault("rows", base.get("rows", []) or [])
            if total_rows:
                out["totalAmount"] = _safe_float(total_rows[-1].get("amount"))
                out["totalQuantity"] = _safe_float(total_rows[-1].get("quantity"))
            else:
                out.setdefault("totalAmount", base.get("totalAmount", 0) or 0)
                out.setdefault("totalQuantity", base.get("totalQuantity", 0) or 0)
            return out

        current = _region_from_import("本期", current)
        prior = _region_from_import("上期", prior)
        remark_json = json.dumps({"current": current, "prior": prior}, ensure_ascii=False)
    else:
        # D4-11 等：store 即为行数组
        remark_json = json.dumps(rows_data, ensure_ascii=False)

    project_id = await _resolve_project_id(db, wp_id)
    new_version = await _upsert_checklist_response(
        db,
        project_id=project_id,
        wp_id=wp_id,
        item_id=item_id,
        remark=remark_json,
        base_version=base_version,
    )
    await db.commit()

    result: dict[str, Any] = {
        "ok": True,
        "imported_count": len(rows_data),
        "errors": errors,
        "content_version": new_version,
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


# openpyxl 禁止写入的控制字符（除 \t \n \r 外的 C0 控制符及部分 C1）
_ILLEGAL_XLSX_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _strip_illegal_xlsx_chars(val: str) -> str:
    """去除 openpyxl 不允许写入 worksheet 的非法控制字符（防 IllegalCharacterError）。"""
    if not val:
        return val
    return _ILLEGAL_XLSX_CHARS_RE.sub("", val)


async def _resolve_project_id(db: AsyncSession, wp_id: str) -> str:
    """从 working_paper 解析 project_id（checklist_responses.project_id NOT NULL 必填）。"""
    import sqlalchemy as sa

    res = await db.execute(
        sa.text("SELECT project_id FROM working_paper WHERE id = :wp_id LIMIT 1"),
        {"wp_id": wp_id},
    )
    row = res.fetchone()
    if not row or row.project_id is None:
        raise HTTPException(404, "底稿不存在或未关联项目")
    return str(row.project_id)


async def _upsert_checklist_response(
    db: AsyncSession,
    *,
    project_id: str,
    wp_id: str,
    item_id: str,
    remark: str,
    base_version: int | None,
) -> int:
    """带乐观锁的 checklist_responses upsert（P0-项4）。

    并发一致性口径（基于真实表结构 + 调用链定，非硬套 ContentMutationService）：
      - checklist_responses 按 (wp_id,item_id) 唯一，导入写整张 sheet 的 JSON blob。
      - 首次写（无既有行）或 ``base_version=None`` → 按"创建/覆盖"语义写入（兼容存量与旧客户端）。
      - 提供 ``base_version`` 时做 If-Match：先 ``SELECT ... FOR UPDATE`` 锁住既有行读当前
        content_version，与 base_version 不符 → 抛 409（``VERSION_CONFLICT``），**不静默覆盖**；
        相符 → content_version+1 写入。``FOR UPDATE`` 把「读版本→比对→写」串行化，
        消除 READ COMMITTED 下的检查-写竞争窗口。

    Returns:
        写入后的新 content_version（供客户端下次 If-Match 用）。

    Raises:
        HTTPException 409（版本冲突，detail 含当前版本供客户端刷新后重试）。

    SQLite 兼容：``FOR UPDATE`` 在 SQLite 上被忽略（无行级锁），逻辑仍正确（单测环境无并发）。
    """
    import sqlalchemy as sa
    from uuid import uuid4

    # ① 锁行读当前版本（存量行可能无 content_version 概念时按 1 起算，COALESCE 兜底）
    cur = await db.execute(
        sa.text(
            "SELECT content_version FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id = :item_id FOR UPDATE"
        ),
        {"wp_id": wp_id, "item_id": item_id},
    )
    row = cur.fetchone()
    current_version = int(row.content_version) if row and row.content_version is not None else None

    # ② If-Match：仅当调用方声明 base_version 且行已存在时做冲突检测
    if base_version is not None and current_version is not None and base_version != current_version:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "VERSION_CONFLICT",
                "message": "底稿数据已被其他用户更新，请刷新后重试",
                "current_version": current_version,
                "your_base_version": base_version,
                "item_id": item_id,
            },
        )

    next_version = (current_version or 0) + 1

    # ③ upsert（版本 +1）。ON CONFLICT 兜住"读时无行但写前被他人插入"的极端竞态：
    #    此时按 checklist_responses.content_version + 1 递增（不覆盖版本计数）。
    await db.execute(
        sa.text(
            """
            INSERT INTO checklist_responses
                (id, project_id, wp_id, item_id, remark, content_version, updated_at)
            VALUES (:id, :project_id, :wp_id, :item_id, :remark, :version, NOW())
            ON CONFLICT (wp_id, item_id)
            DO UPDATE SET
                remark = :remark,
                content_version = checklist_responses.content_version + 1,
                updated_at = NOW()
            """
        ),
        {
            "id": str(uuid4()),
            "project_id": project_id,
            "wp_id": wp_id,
            "item_id": item_id,
            "remark": remark,
            "version": next_version,
        },
    )
    return next_version


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


_D4_1_SECTION_BY_LABEL: dict[str, str] = {
    "主营业务收入": "main-revenue",
    "其他业务收入": "other-revenue",
}
_D4_1_SECTION_LABEL: dict[str, str] = {
    "main-revenue": "主营业务收入",
    "other-revenue": "其他业务收入",
}


def _export_d4_1_row(data: dict) -> list:
    section = data.get("sectionKey", "main-revenue")
    return [
        _D4_1_SECTION_LABEL.get(section, section),
        _safe_str(data.get("rowKey")),
        _safe_str(data.get("label")),
        _safe_float(data.get("currentUnadjusted")),
        _safe_float(data.get("currentAje")),
        _safe_float(data.get("currentRje")),
        _safe_float(data.get("priorUnadjusted")),
        _safe_float(data.get("priorAje")),
        _safe_float(data.get("priorRje")),
    ]


def _parse_d4_1_row(row: tuple, actual_headers: list[str], expected_headers: list[str]) -> dict:
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    section_label = _safe_str(_col_val("区块"))
    row_key = _safe_str(_col_val("行键"))
    label = _safe_str(_col_val("项目"))
    if not row_key and not label:
        return {}

    section_key = _D4_1_SECTION_BY_LABEL.get(section_label, "main-revenue")
    if not row_key:
        row_key = f"row-{uuid4().hex[:8]}"

    return {
        "rowKey": row_key,
        "label": label or row_key,
        "isFixed": False,
        "sectionKey": section_key,
        "currentUnadjusted": _safe_float(_col_val("本期未审")),
        "currentAje": _safe_float(_col_val("本期AJE")),
        "currentRje": _safe_float(_col_val("本期RJE")),
        "priorUnadjusted": _safe_float(_col_val("上期未审")),
        "priorAje": _safe_float(_col_val("上期AJE")),
        "priorRje": _safe_float(_col_val("上期RJE")),
        "isFromCrossSheet": False,
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
            "customerName": _safe_str(_col_val("凭证客户名称")),
            "date": _safe_str(_col_val("凭证日期")),
            "number": _safe_str(_col_val("凭证编号")),
            "productName": _safe_str(_col_val("凭证品名")),
            "quantity": _safe_str(_col_val("凭证数量")),
            "amount": _safe_float(_col_val("凭证金额")),
            "accountingDate": _safe_str(_col_val("记账日期")),
        },
        "contract": {
            "date": _safe_str(_col_val("合同日期")),
            "number": _safe_str(_col_val("合同编号")),
            "productName": _safe_str(_col_val("合同品名")),
            "amount": _safe_float(_col_val("合同金额")),
            "approver": _safe_str(_col_val("签发审批")),
            "confirmor": _safe_str(_col_val("签收确认")),
        },
        "delivery": {
            "date": _safe_str(_col_val("出库日期")),
            "number": _safe_str(_col_val("出库编号")),
            "productName": _safe_str(_col_val("出库品名")),
            "quantity": _safe_str(_col_val("出库数量")),
            "amount": _safe_float(_col_val("出库金额")),
            "warehouseKeeper": _safe_str(_col_val("仓库保管员")),
            "shippingApprover": _safe_str(_col_val("发货审批人")),
        },
        "shipping": {
            "date": _safe_str(_col_val("运输日期")),
            "number": _safe_str(_col_val("运输编号")),
            "productName": _safe_str(_col_val("运输品名")),
            "quantity": _safe_str(_col_val("运输数量")),
            "amount": _safe_float(_col_val("运输金额")),
            "company": _safe_str(_col_val("运输公司")),
            "address": _safe_str(_col_val("运输地址")),
        },
        "receipt": {
            "date": _safe_str(_col_val("签收日期")),
            "productName": _safe_str(_col_val("签收品名")),
            "quantity": _safe_str(_col_val("签收数量")),
            "amount": _safe_float(_col_val("签收金额")),
            "signer": _safe_str(_col_val("签收人")),
            "sealType": _safe_str(_col_val("盖章类型")),
            "sealEntity": _safe_str(_col_val("盖章单位")),
        },
        "invoice": {
            "date": _safe_str(_col_val("发票日期")),
            "number": _safe_str(_col_val("发票编号")),
            "productName": _safe_str(_col_val("发票品名")),
            "quantity": _safe_str(_col_val("发票数量")),
            "amount": _safe_float(_col_val("发票金额")),
        },
        "other": {
            "description": _safe_str(_col_val("其他文件描述")),
            "indexNo": _safe_str(_col_val("其他索引号")),
            "anomalyNote": _safe_str(_col_val("是否异常")),
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


def _parse_d4_15_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析D4-15完整性检查行 → CompletenessItem 嵌套结构（发货单×发票×记账凭证）"""
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    return {
        "id": f"c-{uuid4().hex[:10]}",
        "indexNo": "",
        "delivery": {
            "date": _safe_str(_col_val("发货单日期")),
            "number": _safe_str(_col_val("发货单编号")),
            "productName": _safe_str(_col_val("发货单品名")),
            "quantity": _safe_str(_col_val("发货单数量")),
            "amount": _safe_float(_col_val("发货单金额")),
        },
        "invoice": {
            "date": _safe_str(_col_val("发票日期")),
            "number": _safe_str(_col_val("发票编号")),
            "productName": _safe_str(_col_val("发票品名")),
            "quantity": _safe_str(_col_val("发票数量")),
            "amount": _safe_float(_col_val("发票金额")),
        },
        "voucher": {
            "date": _safe_str(_col_val("记账凭证日期")),
            "number": _safe_str(_col_val("记账凭证编号")),
            "productName": _safe_str(_col_val("记账凭证品名")),
            "quantity": _safe_str(_col_val("记账凭证数量")),
            "amount": _safe_float(_col_val("记账凭证金额")),
        },
        # isConsistent 留 None，由前端 checkConsistency 重算（不双写派生值）
        "isConsistent": None,
        "remark": _safe_str(_col_val("备注")),
    }


def _parse_d4_16_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析D4-16出口核对行 → ExportCheckRow 英文 key，差异列重算（防手改文件造假）"""
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    book = _safe_float(_col_val("账面出口收入金额"))
    ports = _safe_float(_col_val("口岸结关金额"))
    tax = _safe_float(_col_val("申报外营收入"))

    return {
        "id": f"r-{uuid4().hex[:10]}",
        "bookAmount": book,
        "portsAmount": ports,
        "portsDiff": book - ports,          # 重算，不读文件差异列
        "portsReason": _safe_str(_col_val("口岸差异原因")),
        "portsAmount2": 0,
        "portsPeriod": _safe_str(_col_val("口岸期间")),
        "taxReportAmount": tax,
        "taxDiff": book - tax,              # 重算
        "taxReason": _safe_str(_col_val("申报差异原因")),
        "taxIndex": _safe_str(_col_val("索引")),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# D4-17/18/19/20 截止/折扣/退货专用 parser（spec d4-cutoff-return-writeback-formula-io）
#
# 派生列单源：D4-17/18 `isCutoff`、D4-19 `discountRate`、D4-20 provision `shouldProvide/diff`
# 均由前端公式重算（导入不采信文件派生值，parser 留 None / 重算 / 0），对齐 D4-15/16 口径。
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_d4_17_row(row: tuple, actual_headers: list[str]) -> dict:
    """D4-17 截止（账到单据）：凭证 → 发货单方向。isCutoff 留 None 由前端 checkCutoff 重算。"""
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    return {
        "id": f"r-{uuid4().hex[:10]}",
        "voucherDate": _safe_str(_col_val("凭证日期")),
        "voucherNo": _safe_str(_col_val("凭证编号")),
        "voucherProduct": _safe_str(_col_val("凭证品名")),
        "voucherQty": _safe_str(_col_val("凭证数量")),
        "voucherAmount": _safe_float(_col_val("凭证金额")),
        "deliveryDate": _safe_str(_col_val("发货单日期")),
        "deliveryNo": _safe_str(_col_val("发货单编号")),
        "deliveryProduct": _safe_str(_col_val("发货单品名")),
        "deliveryQty": _safe_str(_col_val("发货单数量")),
        "deliveryAmount": _safe_float(_col_val("发货单金额")),
        "isCutoff": None,  # 前端 checkCutoff 重算（不双写派生跨期判定）
        "remark": _safe_str(_col_val("备注")),
    }


def _parse_d4_18_row(row: tuple, actual_headers: list[str]) -> dict:
    """D4-18 截止（单据到账）：发货单 → 凭证方向。isCutoff 留 None 由前端 checkCutoff 重算。"""
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    return {
        "id": f"r-{uuid4().hex[:10]}",
        "deliveryDate": _safe_str(_col_val("发货单日期")),
        "deliveryNo": _safe_str(_col_val("发货单编号")),
        "deliveryProduct": _safe_str(_col_val("发货单品名")),
        "deliveryQty": _safe_str(_col_val("发货单数量")),
        "deliveryAmount": _safe_float(_col_val("发货单金额")),
        "voucherDate": _safe_str(_col_val("凭证日期")),
        "voucherNo": _safe_str(_col_val("凭证编号")),
        "voucherProduct": _safe_str(_col_val("凭证品名")),
        "voucherQty": _safe_str(_col_val("凭证数量")),
        "voucherAmount": _safe_float(_col_val("凭证金额")),
        "isCutoff": None,
        "remark": _safe_str(_col_val("备注")),
    }


def _parse_d4_19_row(row: tuple, actual_headers: list[str]) -> dict:
    """D4-19 销售折扣与折让：discountRate 由前端重算（折扣额/收入额，防手改文件造假）。"""
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    revenue = _safe_float(_col_val("收入金额"))
    discount = _safe_float(_col_val("折扣金额"))
    return {
        "id": f"r-{uuid4().hex[:10]}",
        "customerName": _safe_str(_col_val("客户名称")),
        "discountType": _safe_str(_col_val("折扣类型")),
        "revenueAmount": revenue,
        "discountAmount": discount,
        # 派生列单源：折扣比例后端重算，不读文件「折扣比例」列
        "discountRate": (discount / revenue) if revenue > 0 and discount > 0 else 0,
        "reason": _safe_str(_col_val("原因")),
        "voucherDate": _safe_str(_col_val("凭证日期")),
        "voucherNo": _safe_str(_col_val("凭证编号")),
        "accountSubject": _safe_str(_col_val("会计科目")),
        "detailSubject": _safe_str(_col_val("明细科目")),
        "debitAmount": _safe_float(_col_val("借方金额")),
        "creditAmount": _safe_float(_col_val("贷方金额")),
        "approvalDate": _safe_str(_col_val("审批日期")),
        "approver": _safe_str(_col_val("审批人")),
        "remark": _safe_str(_col_val("备注")),
    }


def _parse_d4_20_return_row(row: tuple, actual_headers: list[str]) -> dict:
    """D4-20 退货明细（current/post 共用）：ReturnCheckRow 结构。无派生列。"""
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    return {
        "id": f"r-{uuid4().hex[:10]}",
        "voucherDate": _safe_str(_col_val("凭证日期")),
        "voucherNo": _safe_str(_col_val("凭证编号")),
        "bizContent": _safe_str(_col_val("业务内容")),
        "subjectName": _safe_str(_col_val("科目名称")),
        "detailSubject": _safe_str(_col_val("二级明细")),
        "debitAmount": _safe_float(_col_val("借方金额")),
        "creditAmount": _safe_float(_col_val("贷方金额")),
        "customerName": _safe_str(_col_val("客户名称")),
        "productName": _safe_str(_col_val("产品名称")),
        "returnQty": _safe_str(_col_val("退货数量")),
        "returnAmount": _safe_float(_col_val("退货金额")),
        "returnReason": _safe_str(_col_val("退货原因")),
        "hasLitigation": _safe_str(_col_val("是否涉及诉讼")),
        "isAbnormal": _safe_str(_col_val("是否异常")),
        "indexRef": _safe_str(_col_val("索引号")),
    }


def _parse_d4_20_provision_row(row: tuple, actual_headers: list[str]) -> dict:
    """D4-20 退货计提：shouldProvide/diff 后端重算（计提基数×比例；应计提−已计提）。"""
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    base = _safe_float(_col_val("计提基数"))
    rate = _safe_float(_col_val("计提比例"))
    already = _safe_float(_col_val("账面已计提金额"))
    should = base * rate
    return {
        "id": f"r-{uuid4().hex[:10]}",
        "productName": _safe_str(_col_val("产品名称")),
        "base": base,
        "rate": rate,
        # 派生列单源：应计提=基数×比例、差异=应计提−已计提，不读文件派生列
        "shouldProvide": should,
        "alreadyProvided": already,
        "diff": should - already,
        "diffReason": _safe_str(_col_val("差异原因")),
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


def _build_d4_9_export_rows(parsed: dict) -> list[dict]:
    """把 D4-9 store {current,prior} 展平成导出行：每区数据行 + 一条总额行。

    每行携带 _period（本期/上期）、_seq（序号）、_totalAmount/_totalQuantity（供占比计算）；
    总额行 _isTotal=True。spec d4-9 Req 6.1：导出含本期/上期两区 + 总额。
    """
    out: list[dict] = []
    for period_label, region_key in (("本期", "current"), ("上期", "prior")):
        region = parsed.get(region_key) or {}
        if not isinstance(region, dict):
            region = {}
        ta = _safe_float(region.get("totalAmount"))
        tq = _safe_float(region.get("totalQuantity"))
        rows = region.get("rows") or []
        if not isinstance(rows, list):
            rows = []
        for seq, r in enumerate(rows, start=1):
            if not isinstance(r, dict):
                continue
            item = dict(r)
            item["_period"] = period_label
            item["_seq"] = seq
            item["_totalAmount"] = ta
            item["_totalQuantity"] = tq
            out.append(item)
        # 每区末尾追加总额行。
        out.append({
            "_period": period_label,
            "_isTotal": True,
            "_totalAmount": ta,
            "_totalQuantity": tq,
        })
    return out


def _parse_d4_9_row(row: tuple, actual_headers: list[str]) -> dict:
    """D4-9 重要客户结构专用 parser（spec d4-9 Req 6.2/6.3/6.4）。

    - 判本期/上期归属（「期间」列，缺列或空默认本期）。
    - 识别总额行（客户名称含「销售总额」）→ 返回 {_isTotal, _period, amount, quantity}。
    - 普通行补 rowId（与 Requirement 3 同规则），返回
      {rowId, name, amount, quantity, priorRank, _period}。
    - 占比列（销售金额占比/销售数量占比）**不解析**（公式列，不可回导覆盖，Req 6.4）。
    """
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    period_raw = _safe_str(_col_val("期间"))
    period = "上期" if "上期" in period_raw else "本期"
    name = _safe_str(_col_val("客户名称"))
    amount = _safe_float(_col_val("销售金额"))
    quantity = _safe_float(_col_val("销售数量"))

    # 总额行：客户名称列写「本期销售总额/上期销售总额」，金额/数量为总额标量。
    if "销售总额" in name:
        return {
            "_isTotal": True,
            "_period": period,
            "amount": amount,
            "quantity": quantity,
        }

    return {
        "rowId": str(uuid4()),
        "name": name,
        "amount": amount,
        "quantity": quantity,
        "priorRank": _safe_str(_col_val("上期排名")),
        "_period": period,
    }


def merge_d4_10_import_rows(
    existing_data: dict,
    imported_rows: list[dict],
    xlsx_meta: dict | None = None,
) -> dict:
    """合并 D4-10 导入行与既有公式元数据（公式真源不被 I/O 冲掉）。

    优先级：xlsx「公式元数据」副表显式字段 > existing store > 预设默认。
    """
    meta = xlsx_meta or {}
    existing = existing_data or {}

    def _pick(key: str, default: Any) -> Any:
        if key in meta and meta[key] not in (None, ""):
            return meta[key]
        if key in existing and existing[key] not in (None, ""):
            return existing[key]
        return default

    override = _pick("totalAmountManualOverride", False)
    if isinstance(override, str):
        override = override.strip().lower() in ("1", "true", "yes", "y")

    return {
        "rows": imported_rows,
        "totalAmount": _safe_float(_pick("totalAmount", 0)),
        "totalQuantity": _safe_float(_pick("totalQuantity", 0)),
        "totalAmountManualOverride": bool(override),
        "totalAmountFormulaRef": str(
            _pick("totalAmountFormulaRef", "WP('D4-2','本期未审合计')")
        ),
    }


def _extract_d4_10_formula_meta_from_wb(wb: Any) -> dict:
    """从导出的「公式元数据」副表还原 D4-10 公式字段；无副表返回 {}。"""
    try:
        if "公式元数据" not in getattr(wb, "sheetnames", []):
            return {}
        ws = wb["公式元数据"]
    except Exception:
        return {}
    out: dict = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or row[0] is None:
            continue
        key = str(row[0]).strip()
        val = row[1] if len(row) > 1 else None
        if key in (
            "totalAmount",
            "totalQuantity",
            "totalAmountManualOverride",
            "totalAmountFormulaRef",
        ):
            out[key] = val
    return out


def _parse_d4_10_row(row: tuple, actual_headers: list[str]) -> dict:
    """D4-10 客户价格：中文列 → PriceRow 英文字段（录入列；派生列前端重算）。"""
    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    return {
        "seq": None,
        "customer": _safe_str(_col_val("客户名称")),
        "product": _safe_str(_col_val("产品种类")),
        "amount": _safe_float(_col_val("销售金额")),
        "quantity": _safe_float(_col_val("销售数量")),
        "unitPrice": _safe_float(_col_val("销售单价")),
        "avgPrice": _safe_float(_col_val("年度均价")),
        "avgReason": _safe_str(_col_val("与均价差异原因")),
        "marketPrice": _safe_float(_col_val("市场价格")),
        "marketReason": _safe_str(_col_val("与市场差异原因")),
    }


def _parse_d4_11_row(row: tuple, actual_headers: list[str]) -> dict:
    """D4-11 产品价格：中文列 → PriceRow 英文字段。"""
    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    return {
        "customer": _safe_str(_col_val("客户名称")),
        "product": _safe_str(_col_val("品种规格")),
        "unitPrice": _safe_float(_col_val("销售单价")),
        "quantity": _safe_float(_col_val("销售数量")),
        "invoiceDate": _safe_str(_col_val("开票日期")),
        "orderNo": _safe_str(_col_val("销售订单")),
        "orderDate": _safe_str(_col_val("订单日期")),
        "listPrice": _safe_float(_col_val("定价表单价")),
        "marketPrice": _safe_float(_col_val("同期市场价格")),
        "reason": _safe_str(_col_val("差异原因分析")),
        "priceSource": _safe_str(_col_val("市场价格来源")),
        "remark": _safe_str(_col_val("备注")),
    }


def _parse_d4_21_row(row: tuple, actual_headers: list[str]) -> dict:
    """D4-21 关联方销售/价格：中文列头 → 契约 camelCase 键（与 phase5_d4_ipo_related_sheets
    descriptor 的 json_path 逐字对齐）。

    🔴 Req 4.2「派生列不采信」：差异率 I=(G-H)/H、差异率(公允) K=(G-J)/J 是模板内部
    OO 公式（FORMULA_MASK），**不从文件读**、不写入 store —— 前端/OOXML 按公式重算。
    序号是展示列也不入 store（行身份用 rowId）。
    """
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
        "partyName": _safe_str(_col_val("关联方客户名称")),
        "relationship": _safe_str(_col_val("关联关系")),
        "product": _safe_str(_col_val("产品名称")),
        "qty": _safe_float(_col_val("销售数量")),
        "salesAmount": _safe_float(_col_val("销售额")),
        "salesRatio": _safe_float(_col_val("销售额占比")),
        "avgPrice": _safe_float(_col_val("平均单价")),
        "nonrelatedAvgPrice": _safe_float(_col_val("非关联方平均单价")),
        # 差异率 / 差异率(公允) 是派生列 —— 不采信、不写 store（Req 4.2 / FORMULA_MASK I/K）
        "fairPrice": _safe_float(_col_val("可比公允价格")),
        "priorSalesRatio": _safe_float(_col_val("上年度占比")),
        "priorAvgPrice": _safe_float(_col_val("上年度平均单价")),
        "remark": _safe_str(_col_val("备注")),
    }


def _parse_d4_24_row(row: tuple, actual_headers: list[str]) -> dict:
    """D4-24 第三方回款：中文列头 → 契约 camelCase 键（descriptor json_path 对齐）。

    无内部公式（FORMULA_MASK 空），13 列全录入。序号为展示列不入 store（行身份 rowId）。
    """
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
        "customerName": _safe_str(_col_val("客户名称")),
        "annualSales": _safe_float(_col_val("本年度销售金额")),
        "endingAr": _safe_float(_col_val("期末应收账款余额")),
        "thirdPartyAmount": _safe_float(_col_val("本年度第三方回款金额")),
        "payerName": _safe_str(_col_val("第三方回款方名称")),
        "reason": _safe_str(_col_val("第三方回款原因")),
        "payerCustomerRelation": _safe_str(_col_val("第三方回款方与客户关系")),
        "payerEntityRelation": _safe_str(_col_val("第三方回款方与被审计单位关系")),
        "hasPaymentAgreement": _safe_str(_col_val("是否有代付协议")),
        "isConfirmed": _safe_str(_col_val("是否函证")),
        "rationality": _safe_str(_col_val("合理性分析")),
        "indexNo": _safe_str(_col_val("索引")),
    }


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


# ═══════════════════════════════════════════════════════════════════════════════
# D4-13 叙述式导入导出（双 item_id：核对过程 / 核对结论）
# ═══════════════════════════════════════════════════════════════════════════════

_D4_13_SECTIONS = [("核对过程", "D4-13-process"), ("核对结论", "D4-13-conclusion")]
_D4_13_SECTION_BY_LABEL = {label: iid for label, iid in _D4_13_SECTIONS}


async def _handle_d4_13_export(wp_id: str, db: AsyncSession) -> StreamingResponse:
    """D4-13 导出：从 D4-13-process / D4-13-conclusion 读文本，各输出一行。"""
    import sqlalchemy as sa

    texts: dict[str, str] = {}
    for _label, iid in _D4_13_SECTIONS:
        res = await db.execute(
            sa.text("SELECT remark FROM checklist_responses WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"),
            {"wp_id": wp_id, "item_id": iid},
        )
        r = res.fetchone()
        texts[iid] = (r.remark if r and r.remark else "") or ""

    wb = Workbook()
    ws = wb.active
    ws.title = "D4-13"
    ws.append(_get_headers("D4-13"))
    ws.freeze_panes = "A2"
    for label, iid in _D4_13_SECTIONS:
        ws.append([label, texts.get(iid, "")])
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 80

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    from urllib.parse import quote
    encoded_filename = quote("D4-13_数据.xlsx")
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


async def _handle_d4_13_import(
    wp_id: str, file: UploadFile, db: AsyncSession, *, base_version: int | None = None
) -> dict[str, Any]:
    """D4-13 导入：按「区块」列把内容写回 D4-13-process / D4-13-conclusion 两个 item_id。

    并发一致性（P0-项4）：两个 item_id 各自走 ``_upsert_checklist_response`` 乐观锁；
    ``base_version`` 对每个 item_id 分别做 If-Match（D4-13 两块通常一起编辑，版本各自独立递增）。
    """
    import sqlalchemy as sa

    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(400, "无法解析xlsx文件，请确认文件格式正确")
    ws = wb.active
    if ws is None:
        raise HTTPException(400, "xlsx文件中无活动工作表")

    expected_headers = _get_headers("D4-13")
    actual_headers = [str(c.value).strip() if c.value else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
    missing = [h for h in expected_headers if h not in actual_headers]
    if missing:
        wb.close()
        return {"ok": False, "errors": [f"缺少列: {', '.join(missing)}"], "imported_count": 0}

    try:
        block_idx = actual_headers.index("区块")
        content_idx = actual_headers.index("内容")
    except ValueError:
        wb.close()
        return {"ok": False, "errors": ["列头缺少 区块/内容"], "imported_count": 0}

    project_id = await _resolve_project_id(db, wp_id)
    written = 0
    versions: dict[str, int] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or all(v is None for v in row):
            continue
        label = _safe_str(row[block_idx] if block_idx < len(row) else "")
        text = _safe_str(row[content_idx] if content_idx < len(row) else "")
        iid = _D4_13_SECTION_BY_LABEL.get(label)
        if not iid:
            continue
        versions[iid] = await _upsert_checklist_response(
            db,
            project_id=project_id,
            wp_id=wp_id,
            item_id=iid,
            remark=text,
            base_version=base_version,
        )
        written += 1
    await db.commit()
    wb.close()
    return {"ok": True, "imported_count": written, "errors": [], "content_versions": versions}


# ═══════════════════════════════════════════════════════════════════════════════
# D4-29/30/31/32 IPO/舞弊组专用 parser（reshape 见 d4_import_data 后处理段）
#
# 设计要点（对齐源 xlsx 单一真源，见 spec d4-ipo-fraud-writeback-formula-io）：
#   - D4-29 客户信息检查表：源为转置矩阵（行=检查字段，列=客户），IO 侧按「一客户一行」
#     投影；表头中文 label ↔ CUSTOMER_FIELDS.key（与 useD4CustomerDetail 双侧一致）。
#   - D4-30 客户访谈汇总：同为转置矩阵，一客户一行；自定义维度(customDimensions)作尾部
#     动态列，导入按「非固定表头」恢复，不丢客户维度也不丢自定义维度。
#   - D4-31 客户访谈记录：单份问卷键值对；q1_relation 始终是 string[]（导出以 ; 连接，
#     导入按 ; / ； / 、 拆回数组），问卷单对象仅一份。
#   - D4-32 资金流水：6 组由显式「组别」列恢复（非按行号/数量硬切）；未知组别进入人工
#     映射(_removed/unknown)而非自动归「其他」。异常/占比为人工判断，原样保留不重算成 0。
# ═══════════════════════════════════════════════════════════════════════════════

# D4-29 中文表头 → CUSTOMER_FIELDS.key（与前端 useD4CustomerDetail.CUSTOMER_FIELDS 双向锁死）
_D4_29_HEADER_TO_KEY: dict[str, str] = {
    "统一社会信用代码": "creditCode",
    "注册地址": "regAddress",
    "办公地址": "officeAddress",
    "网站地址": "website",
    "网站IP地址": "websiteIp",
    "企业邮箱": "email",
    "成立时间": "establishDate",
    "注册资本/实缴资本": "registeredCapital",
    "经营范围": "bizScope",
    "人员规模/社保缴纳人数": "headcount",
    "法定代表人": "legalRep",
    "股东1及持股比例": "shareholder1",
    "股东2及持股比例": "shareholder2",
    "股东3及持股比例": "shareholder3",
    "股东4及持股比例": "shareholder4",
    "股东5及持股比例": "shareholder5",
    "董事长": "chairman",
    "总经理": "gm",
    "其他关键管理人员": "otherMgmt",
    "关键经办人员": "keyHandler",
    "实际控制人": "actualController",
    "是否为关联方": "isRelated",
    "是否同时为供应商": "isAlsoSupplier",
    "开始合作时间": "cooperationStart",
    "是否长期拖欠款项": "hasOverdue",
    "经营状态": "bizStatus",
    "是否列入失信人": "isBlacklisted",
    "信息来源": "infoSource",
}

# D4-30 固定访谈维度中文表头 → INTERVIEW_FIELDS.key（与前端 D4TabInterviewSummary 双向锁死）
_D4_30_HEADER_TO_KEY: dict[str, str] = {
    "访谈时间": "time",
    "访谈原因": "reason",
    "访谈方式": "method",
    "被访谈公司注册地址": "regAddress",
    "实地走访公司地址": "visitAddress",
    "接受访谈人员及身份": "interviewee",
    "参与访谈的审计人员": "auditor",
    "参与访谈的其他人员": "others",
    "访谈人员行程信息": "travelInfo",
    "是否现场函证": "onSiteConfirm",
    "访谈关注要点": "keyPoints",
    "合同执行核对情况": "contractCheck",
    "交易金额核对是否一致": "amountMatch",
    "往来余额核对是否一致": "balanceMatch",
    "访谈结论": "conclusion",
    "访谈表索引": "indexRef",
}

# D4-31 问卷字段中文标签 → InterviewData.key（与前端 D4TabInterviewDetail 双向锁死）
_D4_31_FIELD_LABELS: list[tuple[str, str]] = [
    ("访谈对象", "target"),
    ("访谈时间及地点", "timePlace"),
    ("接受访谈人员及职务", "interviewee"),
    ("访谈人", "interviewer"),
    ("一、接受访谈人介绍", "introduction"),
    ("公司名称", "companyName"),
    ("注册资本", "regCapital"),
    ("成立日期", "establishDate"),
    ("经济性质", "bizNature"),
    ("法定代表人", "legalRep"),
    ("股权结构", "equityStructure"),
    ("业务关系(多选)", "q1_relation"),  # string[]：导出 ; 连接
    ("客户向发行人采购结算方式", "q2a_payment"),
    ("客户向发行人销售结算方式", "q2b_collection"),
    ("是否签订合同", "q3a_hasContract"),
    ("产品质量情况", "q3b_quality"),
    ("是否约定退换货条款", "q3c_returnClause"),
    ("退换货金额", "q3d_returnAmount"),
    ("产品验收入库情况", "q3e_acceptance"),
    ("是否存在返利约定", "q3f_hasRebate"),
    ("返利支付方式", "q3f_rebateMethod"),
    ("返利金额", "q3f_rebateAmount"),
    ("经销商货物是否已最终销售", "q3g_finalSold"),
    ("是否存在其他资金往来", "q4_otherFunds"),
    ("其他重要事项", "q5_otherMatters"),
    ("关联方是否持有股份", "q6_hasShares"),
    ("关联方是否担任职务", "q6_hasPosition"),
    ("关联方是否和客户有交易", "q6_hasTransaction"),
    ("接受访谈人员签字", "signInterviewee"),
    ("审计人员签字", "signAuditor"),
    ("其他人员签字", "signOther"),
    ("签字日期", "signDate"),
]
_D4_31_LABEL_TO_KEY: dict[str, str] = {label: key for label, key in _D4_31_FIELD_LABELS}
_D4_31_MULTI_KEYS: set[str] = {"q1_relation"}

# D4-32 组别中文 label → group key（与前端 D4TabFundFlow.GROUPS 双向锁死）
_D4_32_GROUP_LABEL_TO_KEY: dict[str, str] = {
    "主要供应商": "supplier",
    "主要客户": "customer",
    "控股股东": "shareholder",
    "实际控制人": "controller",
    "关键管理人员": "management",
    "其他关联方": "related",
}
_D4_32_GROUP_KEY_TO_LABEL: dict[str, str] = {v: k for k, v in _D4_32_GROUP_LABEL_TO_KEY.items()}
# 6 组的固定顺序（源 xlsx B 列组头顺序）
_D4_32_GROUP_ORDER: list[str] = ["supplier", "customer", "shareholder", "controller", "management", "related"]


def _parse_d4_29_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析 D4-29 客户信息行 → CustomerItem {id,name,fields}。表头 label→key，未知列忽略。"""
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    name = _safe_str(_col_val("客户名称"))
    fields: dict[str, str] = {}
    for header, key in _D4_29_HEADER_TO_KEY.items():
        v = _col_val(header)
        if v is not None:
            fields[key] = _safe_str(v)
    if not name and not any(fields.values()):
        return {}
    return {
        "id": f"cust-{uuid4().hex[:10]}",
        "name": name,
        "fields": fields,
    }


def _parse_d4_30_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析 D4-30 访谈汇总行 → InterviewCustomer {id,name,fields}。

    固定维度按 label→key；非固定表头（客户名称/固定16列之外）视为自定义维度，
    key 用中文 label 本身（前端合并 customDimensions 时以 label 去重恢复）。
    """
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    name = _safe_str(_col_val("客户名称"))
    fields: dict[str, str] = {}
    custom_labels: list[str] = []
    for header in actual_headers:
        if header == "客户名称" or not header:
            continue
        v = _col_val(header)
        if header in _D4_30_HEADER_TO_KEY:
            key = _D4_30_HEADER_TO_KEY[header]
        else:
            # 未知列 = 自定义维度：key 用 label（不猜测、不归并到固定维度）
            key = header
            custom_labels.append(header)
        if v is not None:
            fields[key] = _safe_str(v)
    if not name and not any(fields.values()):
        return {}
    return {
        "id": f"iv-{uuid4().hex[:10]}",
        "name": name,
        "fields": fields,
        "_customLabels": custom_labels,  # 后处理据此恢复 customDimensions（reshape 后删除）
    }


def _parse_d4_32_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析 D4-32 资金流水行 → FlowRow + _groupKey（由显式「组别」列恢复分组）。

    异常/占比为人工判断字段，原样保留字符串，不重算、不把 '否'/空当异常。
    未知组别 label 落 _groupKey='__unknown__'，进入人工映射（不自动归「其他」）。
    """
    from uuid import uuid4

    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    group_label = _safe_str(_col_val("组别"))
    name = _safe_str(_col_val("单位名称/姓名"))
    amount_raw = _col_val("本期交易金额")
    if not name and not group_label and amount_raw in (None, ""):
        return {}
    group_key = _D4_32_GROUP_LABEL_TO_KEY.get(group_label, "__unknown__")
    # 金额：可空（保持三态），有值才转 float，否则保留空串
    amount: Any = ""
    if amount_raw not in (None, ""):
        amount = _safe_float(amount_raw)
    return {
        "_groupKey": group_key,
        "_groupLabel": group_label,
        "id": f"ff-{uuid4().hex[:10]}",
        "name": name,
        "amount": amount,
        "ratio": _safe_str(_col_val("占同类交易比例")),
        "bank": _safe_str(_col_val("开户银行")),
        "account": _safe_str(_col_val("账号")),
        "method": _safe_str(_col_val("资金流水获取途径")),
        "hasAnomaly": _safe_str(_col_val("是否发现异常交易")),
        "indexRef": _safe_str(_col_val("索引号")),
    }


def _reshape_d4_30_rows(rows_data: list[dict]) -> dict:
    """D4-30 一客户一行 → {customers:[{id,name,fields}], customDimensions:[{key,label}]}。

    customDimensions 由各行 _customLabels 并集恢复（保序去重），key=label。
    """
    seen_labels: list[str] = []
    customers: list[dict] = []
    for r in rows_data:
        labels = r.pop("_customLabels", [])
        for lb in labels:
            if lb not in seen_labels:
                seen_labels.append(lb)
        customers.append(r)
    custom_dims = [{"key": lb, "label": lb} for lb in seen_labels]
    return {"customers": customers, "customDimensions": custom_dims}


def _reshape_d4_32_rows(rows_data: list[dict]) -> list[dict]:
    """D4-32 扁平行 → 6 组 [{key,rows}]（固定顺序）。未知组别行原样保留到 __unknown__ 组，
    不自动归「其他」，供前端人工映射。"""
    buckets: dict[str, list[dict]] = {k: [] for k in _D4_32_GROUP_ORDER}
    unknown: list[dict] = []
    for r in rows_data:
        gkey = r.pop("_groupKey", "__unknown__")
        glabel = r.pop("_groupLabel", "")
        if gkey in buckets:
            buckets[gkey].append(r)
        else:
            # Preserve the source label on every unknown row for later manual mapping.
            r["groupLabel"] = glabel
            unknown.append(r)
    groups = [{"key": k, "rows": buckets[k]} for k in _D4_32_GROUP_ORDER]
    if unknown:
        # 未知组别不并入六组，独立保留供人工认定（前端可提示待映射）
        groups.append({"key": "__unknown__", "rows": unknown})
    return groups


def _parse_d4_31_questionnaire(ws: Any, actual_headers: list[str]) -> dict:
    """解析 D4-31 键值对问卷 → 单份 InterviewData 对象。

    label→key；q1_relation 按 ; / ； / 、 拆回 string[]；未知 label 忽略。
    """
    try:
        field_idx = actual_headers.index("字段")
        value_idx = actual_headers.index("值")
    except ValueError:
        return {}

    data: dict[str, Any] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row is None:
            continue
        label = _safe_str(row[field_idx]) if field_idx < len(row) else ""
        raw = row[value_idx] if value_idx < len(row) else None
        if not label:
            continue
        key = _D4_31_LABEL_TO_KEY.get(label)
        if not key:
            continue  # 未知字段忽略（不猜测）
        if key in _D4_31_MULTI_KEYS:
            s = _safe_str(raw)
            parts = [p.strip() for p in re.split(r"[;；、]", s) if p.strip()] if s else []
            data[key] = parts  # 始终 string[]
        else:
            data[key] = _safe_str(raw)
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# D4-33/34/35/36 其他业务收入组 —— 专用 parser / export 行构造
#   spec: d4-33-36-writeback-formula-and-io-closure（Wave-1）
#   范式照抄 D4-15/16/22/23：按列头名映射（非列序）、派生列重算/留空、item_id 落 -data 键
# ═══════════════════════════════════════════════════════════════════════════════


def _safe_amount_or_blank(val: Any) -> float | str:
    """金额兜底：空/None → 空串（不写 0）；有值 → float。用于导入时保留「未填」语义。"""
    if val is None:
        return ""
    if isinstance(val, str) and val.strip() == "":
        return ""
    try:
        return float(val)
    except (ValueError, TypeError):
        return ""


def _make_col_val(row: tuple, actual_headers: list[str]):
    """构造按列头名取值的闭包（复用范式，防列序错位）。"""
    values = list(row) + [None] * (len(actual_headers) - len(row))

    def _col_val(col_name: str) -> Any:
        try:
            idx = actual_headers.index(col_name)
            return values[idx] if idx < len(values) else None
        except ValueError:
            return None

    return _col_val


# ─── D4-33 其他业务毛利率分析（{bizTypes, months, priorYear} 嵌套 store）──────────

_D4_33_FIXED_ROW_LABELS = ["合计", "上年数", "变动额", "变动比例"]
_D4_33_MONTH_LABELS = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"]


def _d4_33_dynamic_headers(biz_types: list[dict]) -> list[str]:
    """按实际业务类型生成 D4-33 列头：月份 + 合计(收入/成本/毛利率) + 每业务(收入/成本/毛利率)。"""
    headers = ["月份", "合计-收入", "合计-成本", "合计-毛利率"]
    for b in biz_types:
        name = b.get("name", "") if isinstance(b, dict) else str(b)
        headers += [f"{name}-收入", f"{name}-成本", f"{name}-毛利率"]
    return headers


def _fmt_margin_pct(rev: float, cost: float) -> float:
    """毛利率百分比口径（与前端 fmtMargin / 引擎 calcGrossMarginRate*100 一致）。"""
    if not rev:
        return 0.0
    return round((rev - cost) / rev * 100, 2)


def _write_d4_33_rows(ws, biz_types: list[dict], months_map: dict, prior_map: dict) -> None:
    """导出 D4-33 的 16 行：12 月（录入）+ 合计/上年数/变动额/变动比例（派生）。"""
    def _cell(biz_id: str, m_idx: int, field: str) -> float:
        arr = months_map.get(biz_id, [])
        if 0 <= m_idx < len(arr):
            return _safe_float(arr[m_idx].get(field))
        return 0.0

    def _prior(biz_id: str, field: str) -> float:
        return _safe_float(prior_map.get(biz_id, {}).get(field))

    def _total(biz_id: str, field: str) -> float:
        arr = months_map.get(biz_id, [])
        return sum(_safe_float(m.get(field)) for m in arr)

    # 12 月行（录入值）
    for m_idx, m_label in enumerate(_D4_33_MONTH_LABELS):
        tot_rev = sum(_cell(b.get("id", ""), m_idx, "revenue") for b in biz_types)
        tot_cost = sum(_cell(b.get("id", ""), m_idx, "cost") for b in biz_types)
        row = [m_label, tot_rev, tot_cost, _fmt_margin_pct(tot_rev, tot_cost)]
        for b in biz_types:
            bid = b.get("id", "")
            rev = _cell(bid, m_idx, "revenue")
            cost = _cell(bid, m_idx, "cost")
            row += [rev, cost, _fmt_margin_pct(rev, cost)]
        ws.append(row)

    # 合计行（派生）
    grand_rev = sum(_total(b.get("id", ""), "revenue") for b in biz_types)
    grand_cost = sum(_total(b.get("id", ""), "cost") for b in biz_types)
    row_total = ["合计", grand_rev, grand_cost, _fmt_margin_pct(grand_rev, grand_cost)]
    for b in biz_types:
        bid = b.get("id", "")
        rev = _total(bid, "revenue")
        cost = _total(bid, "cost")
        row_total += [rev, cost, _fmt_margin_pct(rev, cost)]
    ws.append(row_total)

    # 上年数行（录入值）
    prior_rev_all = sum(_prior(b.get("id", ""), "revenue") for b in biz_types)
    prior_cost_all = sum(_prior(b.get("id", ""), "cost") for b in biz_types)
    row_prior = ["上年数", prior_rev_all, prior_cost_all, _fmt_margin_pct(prior_rev_all, prior_cost_all)]
    for b in biz_types:
        bid = b.get("id", "")
        rev = _prior(bid, "revenue")
        cost = _prior(bid, "cost")
        row_prior += [rev, cost, _fmt_margin_pct(rev, cost)]
    ws.append(row_prior)

    # 变动额行（派生：合计 - 上年数；毛利率列留空）
    row_delta = ["变动额", grand_rev - prior_rev_all, grand_cost - prior_cost_all, ""]
    for b in biz_types:
        bid = b.get("id", "")
        row_delta += [_total(bid, "revenue") - _prior(bid, "revenue"),
                      _total(bid, "cost") - _prior(bid, "cost"), ""]
    ws.append(row_delta)

    # 变动比例行（派生：变动额 / 上年数 * 100；毛利率列留空）
    def _rate(cur: float, prior: float) -> float | str:
        return round((cur - prior) / prior * 100, 2) if prior else ""

    row_rate = ["变动比例", _rate(grand_rev, prior_rev_all), _rate(grand_cost, prior_cost_all), ""]
    for b in biz_types:
        bid = b.get("id", "")
        row_rate += [_rate(_total(bid, "revenue"), _prior(bid, "revenue")),
                     _rate(_total(bid, "cost"), _prior(bid, "cost")), ""]
    ws.append(row_rate)


def _parse_d4_33_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析 D4-33 一行（一个月份/上年数含各业务列）→ 中间形态 {label, cells:{biz_name:{revenue,cost}}}。
    合计/变动额/变动比例等派生行在 rebuild 时忽略（由前端重算）。"""
    _col_val = _make_col_val(row, actual_headers)
    label = _safe_str(_col_val("月份"))
    if not label:
        return {}
    # 从动态列头提取业务类型名（形如 "{name}-收入"）
    cells: dict[str, dict] = {}
    for h in actual_headers:
        if h.endswith("-收入") and not h.startswith("合计"):
            biz_name = h[:-len("-收入")]
            rev = _col_val(f"{biz_name}-收入")
            cost = _col_val(f"{biz_name}-成本")
            cells[biz_name] = {
                "revenue": _safe_amount_or_blank(rev),
                "cost": _safe_amount_or_blank(cost),
            }
    return {"label": label, "cells": cells}


def _rebuild_d4_33_store(rows_data: list[dict], actual_headers: list[str]) -> dict:
    """把 D4-33 行列表重组成 {bizTypes, months, priorYear} 嵌套 store。
    仅取 12 月行填 months、上年数行填 priorYear；派生行（合计/变动额/变动比例）忽略。"""
    # 从列头提取业务类型顺序（形如 "{name}-收入"，排除合计）
    biz_names: list[str] = []
    for h in actual_headers:
        if h.endswith("-收入") and not h.startswith("合计"):
            biz_names.append(h[:-len("-收入")])

    biz_types = [{"id": f"biz-imp-{i}", "name": n} for i, n in enumerate(biz_names)]
    name_to_id = {b["name"]: b["id"] for b in biz_types}
    months: dict[str, list] = {b["id"]: [{"revenue": "", "cost": ""} for _ in range(12)] for b in biz_types}
    prior_year: dict[str, dict] = {b["id"]: {"revenue": "", "cost": ""} for b in biz_types}

    month_idx = {lbl: i for i, lbl in enumerate(_D4_33_MONTH_LABELS)}
    for r in rows_data:
        label = r.get("label", "")
        cells = r.get("cells", {})
        if label in month_idx:
            m_idx = month_idx[label]
            for biz_name, cell in cells.items():
                bid = name_to_id.get(biz_name)
                if bid:
                    months[bid][m_idx] = {"revenue": cell.get("revenue", ""), "cost": cell.get("cost", "")}
        elif label == "上年数":
            for biz_name, cell in cells.items():
                bid = name_to_id.get(biz_name)
                if bid:
                    prior_year[bid] = {"revenue": cell.get("revenue", ""), "cost": cell.get("cost", "")}
        # 合计/变动额/变动比例：派生行，忽略（前端重算）

    return {"bizTypes": biz_types, "months": months, "priorYear": prior_year}


# ─── D4-34 合同测算（{rentals, consults} 两区）─────────────────────────────────


def _export_d4_34_rental_row(data: dict) -> list:
    """RentalRow → D4-34-rental 列头顺序（差异列重算，不读文件）。"""
    expected = _safe_float(data.get("expectedRevenue"))
    actual = _safe_float(data.get("actualRevenue"))
    return [
        "",  # 序号（占位，导入时忽略）
        _safe_str(data.get("tenant")),
        _safe_str(data.get("period")),
        _safe_str(data.get("area")),
        _safe_float(data.get("unitPrice")),
        _safe_str(data.get("contractRef")),
        _safe_str(data.get("actualMonths")),
        expected,
        actual,
        actual - expected,  # 差异重算
        _safe_str(data.get("indexRef")),
    ]


def _parse_d4_34_rental_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析 D4-34-rental 行 → RentalRow（差异列重算，不读文件）。"""
    from uuid import uuid4
    _col_val = _make_col_val(row, actual_headers)
    tenant = _safe_str(_col_val("承租方"))
    if not tenant:
        return {}
    expected = _safe_amount_or_blank(_col_val("本期应计收入"))
    actual = _safe_amount_or_blank(_col_val("本期实计收入"))
    diff = (_safe_float(actual) - _safe_float(expected))
    return {
        "id": f"rt-imp-{uuid4().hex[:8]}",
        "tenant": tenant,
        "period": _safe_str(_col_val("租赁期间")),
        "area": _safe_str(_col_val("租赁面积")),
        "unitPrice": _safe_amount_or_blank(_col_val("合同单价")),
        "contractRef": _safe_str(_col_val("合同索引")),
        "actualMonths": _safe_amount_or_blank(_col_val("本期实际租赁月数")),
        "expectedRevenue": expected,
        "actualRevenue": actual,
        "diff": diff,  # 重算
        "indexRef": _safe_str(_col_val("索引号")),
    }


def _export_d4_34_consult_row(data: dict) -> list:
    """ConsultRow → D4-34-consult 列头顺序（差异列重算）。"""
    expected = _safe_float(data.get("expectedRevenue"))
    actual = _safe_float(data.get("actualRevenue"))
    return [
        "",  # 序号占位
        _safe_str(data.get("client")),
        _safe_str(data.get("project")),
        _safe_str(data.get("duration")),
        _safe_float(data.get("contractAmount")),
        _safe_str(data.get("contractRef")),
        expected,
        actual,
        actual - expected,  # 差异重算
        _safe_str(data.get("indexRef")),
    ]


def _parse_d4_34_consult_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析 D4-34-consult 行 → ConsultRow（差异列重算）。"""
    from uuid import uuid4
    _col_val = _make_col_val(row, actual_headers)
    client = _safe_str(_col_val("委托方"))
    if not client:
        return {}
    expected = _safe_amount_or_blank(_col_val("本期应计收入"))
    actual = _safe_amount_or_blank(_col_val("本期实计收入"))
    diff = (_safe_float(actual) - _safe_float(expected))
    return {
        "id": f"cs-imp-{uuid4().hex[:8]}",
        "client": client,
        "project": _safe_str(_col_val("咨询项目")),
        "duration": _safe_str(_col_val("委托期限")),
        "contractAmount": _safe_amount_or_blank(_col_val("合同金额")),
        "contractRef": _safe_str(_col_val("合同索引")),
        "expectedRevenue": expected,
        "actualRevenue": actual,
        "diff": diff,  # 重算
        "indexRef": _safe_str(_col_val("索引号")),
    }


# ─── D4-35 检查表（{rows, sampling, periodAmount}；isAnomalous 保持 string）───────


def _export_d4_35_row(data: dict) -> list:
    """CheckRow → D4-35 列头顺序（16 列，含 check1..6 √/空）。"""
    return [
        _safe_str(data.get("date")),
        _safe_str(data.get("voucherNo")),
        _safe_str(data.get("content")),
        _safe_str(data.get("counterAccount")),
        _safe_str(data.get("detailAccount")),
        data.get("amount", "") if data.get("amount") not in (None,) else "",
        _safe_str(data.get("supportDoc")),
        _safe_str(data.get("check1")),
        _safe_str(data.get("check2")),
        _safe_str(data.get("check3")),
        _safe_str(data.get("check4")),
        _safe_str(data.get("check5")),
        _safe_str(data.get("check6")),
        _safe_str(data.get("indexRef")),
        _safe_str(data.get("isAnomalous")),
        _safe_str(data.get("remark")),
    ]


def _parse_d4_35_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析 D4-35 行 → CheckRow（16 字段；isAnomalous 保持 string；amount 空串保持空串）。"""
    from uuid import uuid4
    _col_val = _make_col_val(row, actual_headers)
    voucher_no = _safe_str(_col_val("凭证编号"))
    date = _safe_str(_col_val("日期"))
    content = _safe_str(_col_val("业务内容"))
    if not (voucher_no or date or content):
        return {}
    return {
        "id": f"ck-imp-{uuid4().hex[:8]}",
        "date": date,
        "voucherNo": voucher_no,
        "content": content,
        "counterAccount": _safe_str(_col_val("对方科目")),
        "detailAccount": _safe_str(_col_val("明细科目")),
        "amount": _safe_amount_or_blank(_col_val("金额")),  # 空串保持空串，不写 0
        "supportDoc": _safe_str(_col_val("支持性文件")),
        "check1": _safe_str(_col_val("核对1")),
        "check2": _safe_str(_col_val("核对2")),
        "check3": _safe_str(_col_val("核对3")),
        "check4": _safe_str(_col_val("核对4")),
        "check5": _safe_str(_col_val("核对5")),
        "check6": _safe_str(_col_val("核对6")),
        "indexRef": _safe_str(_col_val("索引号")),
        "isAnomalous": _safe_str(_col_val("是否异常")),  # 保持 string（是/否/空），不转 boolean
        "remark": _safe_str(_col_val("备注说明")),
    }


# ─── D4-36 截止性测试（{forward, backward} 两区；按列头名映射防交叉错位）──────────


def _export_d4_36_forward_row(data: dict) -> list:
    """CutoffRow → D4-36-forward 列头顺序（凭证在前、单据在后；跨期判定重算，此处留空由前端判）。"""
    return [
        _safe_str(data.get("voucherDate")),
        _safe_str(data.get("voucherNo")),
        _safe_str(data.get("voucherProduct")),
        _safe_str(data.get("voucherQty")),
        _safe_amount_or_blank(data.get("voucherAmount")),
        _safe_str(data.get("docDate")),
        _safe_str(data.get("docNo")),
        _safe_str(data.get("docProduct")),
        _safe_str(data.get("docQty")),
        _safe_amount_or_blank(data.get("docAmount")),
        _safe_str(data.get("isCrossing")),
    ]


def _export_d4_36_backward_row(data: dict) -> list:
    """CutoffRow → D4-36-backward 列头顺序（单据在前、凭证在后，与 forward 相反）。"""
    return [
        _safe_str(data.get("docDate")),
        _safe_str(data.get("docNo")),
        _safe_str(data.get("docProduct")),
        _safe_str(data.get("docQty")),
        _safe_amount_or_blank(data.get("docAmount")),
        _safe_str(data.get("voucherDate")),
        _safe_str(data.get("voucherNo")),
        _safe_str(data.get("voucherProduct")),
        _safe_str(data.get("voucherQty")),
        _safe_amount_or_blank(data.get("voucherAmount")),
        _safe_str(data.get("isCrossing")),
    ]


def _parse_d4_36_forward_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析 D4-36-forward 行 → CutoffRow（按列头名映射，跨期判定留空由前端 autoJudge 重算）。"""
    from uuid import uuid4
    _col_val = _make_col_val(row, actual_headers)
    voucher_date = _safe_str(_col_val("凭证日期"))
    doc_date = _safe_str(_col_val("单据日期"))
    if not (voucher_date or doc_date):
        return {}
    return {
        "id": f"ct-imp-{uuid4().hex[:8]}",
        "voucherDate": voucher_date,
        "voucherNo": _safe_str(_col_val("凭证编号")),
        "voucherProduct": _safe_str(_col_val("凭证品名")),
        "voucherQty": _safe_str(_col_val("凭证数量")),
        "voucherAmount": _safe_amount_or_blank(_col_val("凭证金额")),
        "docDate": doc_date,
        "docNo": _safe_str(_col_val("单据编号")),
        "docProduct": _safe_str(_col_val("单据品名")),
        "docQty": _safe_str(_col_val("单据数量")),
        "docAmount": _safe_amount_or_blank(_col_val("单据金额")),
        "isCrossing": "",  # 派生：由前端 autoJudgeForward 重算
    }


def _parse_d4_36_backward_row(row: tuple, actual_headers: list[str]) -> dict:
    """解析 D4-36-backward 行 → CutoffRow（按列头名映射，与 forward 同字段结构，防列序交叉错位）。"""
    from uuid import uuid4
    _col_val = _make_col_val(row, actual_headers)
    voucher_date = _safe_str(_col_val("凭证日期"))
    doc_date = _safe_str(_col_val("单据日期"))
    if not (voucher_date or doc_date):
        return {}
    return {
        "id": f"ct-imp-{uuid4().hex[:8]}",
        "voucherDate": voucher_date,
        "voucherNo": _safe_str(_col_val("凭证编号")),
        "voucherProduct": _safe_str(_col_val("凭证品名")),
        "voucherQty": _safe_str(_col_val("凭证数量")),
        "voucherAmount": _safe_amount_or_blank(_col_val("凭证金额")),
        "docDate": doc_date,
        "docNo": _safe_str(_col_val("单据编号")),
        "docProduct": _safe_str(_col_val("单据品名")),
        "docQty": _safe_str(_col_val("单据数量")),
        "docAmount": _safe_amount_or_blank(_col_val("单据金额")),
        "isCrossing": "",  # 派生：由前端 autoJudgeBackward 重算
    }


def _export_d4_31_questionnaire(sheet: str, data: dict) -> StreamingResponse:
    """D4-31 单份问卷导出为「字段/值」键值对 xlsx（单对象，非行集）。

    q1_relation（string[]）以 ; 连接；字段顺序固定（_D4_31_FIELD_LABELS）。
    """
    from urllib.parse import quote

    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(["字段", "值"])
    ws.freeze_panes = "A2"
    for label, key in _D4_31_FIELD_LABELS:
        val = data.get(key, "")
        if key in _D4_31_MULTI_KEYS:
            if isinstance(val, list):
                val = "；".join(str(x) for x in val)
            else:
                val = _safe_str(val)
        else:
            val = _safe_str(val)
        # 去除 xlsx 非法控制字符（否则 openpyxl 写入抛 IllegalCharacterError）
        ws.append([label, _strip_illegal_xlsx_chars(val)])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    filename = f"{sheet}_数据.xlsx"
    encoded_filename = quote(filename)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )
