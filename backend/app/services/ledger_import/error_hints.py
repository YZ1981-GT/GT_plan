"""Sprint 10 Task 6.11 / F32: 错误码 → 用户友好提示映射。

每条 ``ErrorCode`` 对应一条 ``ErrorHint``：
- ``title``       ：短标题（前端对话框标题）
- ``description`` ：一句话说明根因
- ``suggestions`` ：2-4 条可操作建议（列表）
- ``severity``    ：fatal / blocking / warning / info（与 DEFAULT_SEVERITY 对齐）

使用方式：
    >>> from app.services.ledger_import.error_hints import get_error_hint
    >>> hint = get_error_hint("L2_LEDGER_YEAR_OUT_OF_RANGE")
    >>> hint.title
    '序时账年度超出范围'

CI 一致性：``test_all_error_codes_have_hints.py`` 保证 ``ErrorCode`` 中每个
枚举值在 ``ERROR_HINTS`` 中都有条目。
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from .errors import DEFAULT_SEVERITY, ErrorCode

HintSeverity = Literal["fatal", "blocking", "warning", "info"]


class ErrorHint(BaseModel):
    """用户友好的错误码文案（F32）。"""

    model_config = ConfigDict(extra="forbid")

    title: str
    description: str
    suggestions: list[str]
    severity: HintSeverity


ERROR_HINTS: dict[str, ErrorHint] = {
    # ===============================================================
    # fatal — 文件层面无法继续处理
    # ===============================================================
    "FILE_TOO_LARGE": ErrorHint(
        title="文件过大",
        description="上传的文件超过平台允许的大小上限",
        suggestions=[
            "将账套拆分为多个较小的文件分批上传",
            "仅导出本年度需要审计的科目范围",
            "如确需上传超大文件，联系系统管理员放宽上限",
        ],
        severity="fatal",
    ),
    "UNSUPPORTED_FILE_TYPE": ErrorHint(
        title="不支持的文件类型",
        description="仅支持 .xlsx / .xlsm / .csv / .tsv / .zip 格式",
        suggestions=[
            "将 .xls 另存为 .xlsx 后重新上传",
            "如为扫描件/PDF，需先转换为 Excel",
        ],
        severity="fatal",
    ),
    "CORRUPTED_FILE": ErrorHint(
        title="文件损坏或格式异常",
        description="系统无法正常读取该文件的内容",
        suggestions=[
            "用 Excel 打开确认文件可正常显示",
            "重新从财务软件导出账套",
            "如文件来自邮件传输，请确认下载完整",
        ],
        severity="fatal",
    ),
    "XLS_NOT_SUPPORTED": ErrorHint(
        title=".xls 旧格式暂不支持",
        description="平台未引入旧版 Excel (.xls) 解析库",
        suggestions=[
            "打开文件 → 另存为 → 选择 Excel 工作簿 (*.xlsx)",
            "Office 2007+ 的默认格式即为 .xlsx",
        ],
        severity="fatal",
    ),
    "ENCODING_DETECTION_FAILED": ErrorHint(
        title="CSV 编码无法识别",
        description="系统试过 UTF-8 / GBK / GB18030 / Big5 都无法正常解码",
        suggestions=[
            "用 Notepad++ 打开查看文件编码，另存为 UTF-8 BOM 后重新上传",
            "用 Excel 打开后另存为 xlsx 格式，跳过 CSV",
            "如含特殊二进制字符，先在原软件导出为标准 CSV",
        ],
        severity="fatal",
    ),
    # ===============================================================
    # blocking — 校验失败，必须修复或人工确认后才能继续
    # ===============================================================
    "NO_VALID_SHEET": ErrorHint(
        title="未识别到任何有效账表",
        description="整个 workbook 的所有 sheet 都无法识别为余额表/序时账/辅助表",
        suggestions=[
            "检查 sheet 名是否含关键字（如'科目余额表'/'序时账'）",
            "检查表头是否为首行，是否有横幅/标题干扰",
            "如 sheet 名为通用'sheet1'，在文件名加识别关键字（'-科目余额表.xlsx'）",
        ],
        severity="blocking",
    ),
    "MISSING_KEY_COLUMN": ErrorHint(
        title="缺少关键列",
        description="表头未识别出该表类型必须的关键列（如科目编码 / 借贷金额）",
        suggestions=[
            "检查表头行是否正确（常见问题：前两行是公司名/年度横幅）",
            "在列映射编辑器手动指定该列的标准字段",
            "如确实无此列，联系数据源方在导出时补充",
        ],
        severity="blocking",
    ),
    "AMOUNT_NOT_NUMERIC_KEY": ErrorHint(
        title="关键金额列含非数字值",
        description="借方/贷方/余额列中出现了无法转换为数字的值",
        suggestions=[
            "检查是否有全角数字、带空格/货币符号的值",
            "Excel 中先将该列格式改为'常规'或'数值'",
            "删除合计行、小计行等非数据行",
        ],
        severity="blocking",
    ),
    "DATE_INVALID_KEY": ErrorHint(
        title="关键日期列格式错误",
        description="凭证日期列中的值无法解析为日期",
        suggestions=[
            "检查日期格式：YYYY-MM-DD / YYYY/MM/DD / YYYYMMDD 都可识别",
            "Excel 中全选日期列，设置单元格格式为'日期'",
            "去掉日期列中的汉字（如'2024年1月1日'改成 2024-01-01）",
        ],
        severity="blocking",
    ),
    "EMPTY_VALUE_KEY": ErrorHint(
        title="关键列含空值",
        description="关键列（科目编码等）出现空单元格",
        suggestions=[
            "检查是否有只填金额没填科目的行（通常是小计行）",
            "使用合并单元格时先取消合并、向下填充",
            "如确实是有意的空值，改为使用 0 / NULL 占位",
        ],
        severity="blocking",
    ),
    "BALANCE_UNBALANCED": ErrorHint(
        title="借贷不平衡",
        description="余额表 / 序时账的借方累计 ≠ 贷方累计",
        suggestions=[
            "检查是否有漏录的凭证或科目",
            "核对期初/期末余额的借贷方向",
            "在'数据校验'页面查看具体差异科目和凭证号",
        ],
        severity="blocking",
    ),
    "ACCOUNT_NOT_IN_CHART": ErrorHint(
        title="科目编码未在科目表中",
        description="序时账 / 辅助表中的某科目编码在科目表中找不到定义",
        suggestions=[
            "先上传完整的科目表",
            "检查科目编码是否有前后空格、全半角差异",
            "如为新增科目，在财务软件中补充后重新导出",
        ],
        severity="blocking",
    ),
    "BALANCE_LEDGER_MISMATCH": ErrorHint(
        title="余额表与序时账不一致",
        description=(
            "按科目统计序时账借贷累计后，和余额表的期末余额不符；"
            "容差 = min(1 + 最大金额 × 0.00001, 100) 元"
        ),
        suggestions=[
            "查看'数据校验'页面的差异详情（含公式和代入值）",
            "点击差异行'查看明细'打开该科目所有凭证",
            "常见原因：凭证未过账 / 期初余额录错 / 币种混乱",
        ],
        severity="blocking",
    ),
    "L2_LEDGER_YEAR_OUT_OF_RANGE": ErrorHint(
        title="序时账年度超出范围",
        description="序时账中的凭证日期不在本次导入的年度内",
        suggestions=[
            "检查文件是否混入了跨年度凭证（如 2024 底 + 2025 初）",
            "删除不属于本年度的行后重新上传",
            "如为合规跨年结转，联系管理员启用'允许跨年数据'选项",
        ],
        severity="blocking",
    ),
    # ===============================================================
    # warning — 次关键列 / 非阻断问题
    # ===============================================================
    "MISSING_RECOMMENDED_COLUMN": ErrorHint(
        title="缺少推荐列",
        description="某些非必需但强烈推荐的列（如科目名称/币种）未能识别",
        suggestions=[
            "如需要完整字段，在列映射编辑器中手动指定",
            "该列缺失会被保留为空，不影响核心业务查询",
        ],
        severity="warning",
    ),
    "AMOUNT_NOT_NUMERIC_RECOMMENDED": ErrorHint(
        title="推荐金额列含非数字",
        description="非关键金额列中出现无法转换的值；该值被置为空",
        suggestions=[
            "如不影响审计，可忽略该警告",
            "如需保留原值，可在导入后从 raw_extra 中查询",
        ],
        severity="warning",
    ),
    "DATE_INVALID_RECOMMENDED": ErrorHint(
        title="推荐日期列格式错误",
        description="非关键日期列有值但无法解析；该值被置为空",
        suggestions=[
            "如不影响审计，可忽略",
            "如需修复，在 Excel 中统一日期格式后重新上传",
        ],
        severity="warning",
    ),
    "YEAR_MISMATCH": ErrorHint(
        title="检测到的年度与申报年度不一致",
        description="自动从文件名/sheet 名检测的年度与用户选择的年度不同",
        suggestions=[
            "若用户选择正确，忽略此警告即可",
            "若检测结果正确，在上传页面修改年度后重新提交",
        ],
        severity="warning",
    ),
    "AUX_DIMENSION_PARSE_FAILED": ErrorHint(
        title="辅助维度列解析失败",
        description=(
            "某些辅助维度值（如'客户:C001,华为公司'）不符合已知的 8 种格式"
        ),
        suggestions=[
            "检查该列是否混杂多种分隔符（中英文逗号/冒号）",
            "复杂维度可保留在 raw_extra 中不走结构化解析",
            "联系管理员扩展辅助维度解析规则",
        ],
        severity="warning",
    ),
    "HEADER_ROW_AMBIGUOUS": ErrorHint(
        title="表头行位置不明确",
        description="系统检测到多个候选表头行，选择了最可能的一行",
        suggestions=[
            "核对'检测预览'中识别出的表头是否正确",
            "如不正确，在列映射编辑器中手动调整 data_start_row",
        ],
        severity="warning",
    ),
    "SHEET_MERGE_HEURISTIC": ErrorHint(
        title="多 sheet 合并策略启用",
        description="workbook 内多个同类型 sheet 被自动合并为一个数据集",
        suggestions=[
            "核对'检测预览'中的合并决策",
            "如不希望合并（如月度分开的序时账），在高级选项中禁用",
        ],
        severity="warning",
    ),
    "AUX_ACCOUNT_MISMATCH": ErrorHint(
        title="辅助表科目在主表中缺失",
        description="辅助余额/序时账中出现的科目未在主余额表中定义",
        suggestions=[
            "核对是否遗漏了主余额表的某些科目",
            "如为辅助核算新增科目，在科目表补充",
        ],
        severity="warning",
    ),
    "EXTRA_TRUNCATED": ErrorHint(
        title="非关键列内容被截断",
        description="raw_extra 存储单个值超过 8KB，已截断保留前 8KB",
        suggestions=[
            "原值过长通常是 OCR / 导出异常，检查原数据",
            "如需完整值，请改用外部链接存储",
        ],
        severity="warning",
    ),
    "CURRENCY_MIX": ErrorHint(
        title="检测到多币种",
        description="同一科目下混有多个币种（CNY / USD / HKD 等）",
        suggestions=[
            "确认财务软件是否正确记录了币种列",
            "审计时注意按币种分别核对借贷平衡",
        ],
        severity="warning",
    ),
    "ROW_SKIPPED_KEY_EMPTY": ErrorHint(
        title="脏行已跳过",
        description="某些行关键列全空（通常是尾部空白或分组小计行），系统已自动跳过",
        suggestions=[
            "如跳过行数少（<5%），可忽略",
            "如跳过行数多，可能是数据质量问题，核对原文件",
        ],
        severity="warning",
    ),
    # ===============================================================
    # info — 前端不弹窗，仅供追溯
    # ===============================================================
    "RAW_EXTRA_COLUMNS_PRESERVED": ErrorHint(
        title="非关键列已保留到 raw_extra",
        description="用户文件中的额外列（非标准字段）已保存到 raw_extra JSONB",
        suggestions=[
            "如需查询，使用账表穿透 API 带 extra_keys 参数",
            "后续可按需迁移为正式字段",
        ],
        severity="info",
    ),
    "AI_FALLBACK_USED": ErrorHint(
        title="使用 AI 兜底识别",
        description="规则识别置信度低，已调用 LLM 辅助确定列映射",
        suggestions=[
            "核对识别结果是否准确，必要时手动修正",
            "用户确认后可保存为历史映射，下次自动复用",
        ],
        severity="info",
    ),
    "HISTORY_MAPPING_APPLIED": ErrorHint(
        title="自动应用了历史映射",
        description="检测到与之前导入文件指纹一致，已自动套用上次确认的列映射",
        suggestions=[
            "核对映射是否仍正确（数据格式可能变化）",
            "如不正确，修改后将覆盖历史记录",
        ],
        severity="info",
    ),
    # ===============================================================
    # 通用码 — 视 column_tier 严重度可变
    # ===============================================================
    "MISSING_COLUMN": ErrorHint(
        title="缺少列",
        description="通用缺列提示，具体影响视列所在层级",
        suggestions=[
            "关键列缺失会 blocking，推荐列缺失仅 warning",
            "在列映射编辑器查看哪些列未映射",
        ],
        severity="warning",
    ),
    "AMOUNT_NOT_NUMERIC": ErrorHint(
        title="金额列含非数字",
        description="通用金额校验失败提示，视列层级可 blocking 或 warning",
        suggestions=[
            "检查原始单元格格式和内容",
            "统一改为'数值'格式后重新上传",
        ],
        severity="warning",
    ),
    "DATE_INVALID": ErrorHint(
        title="日期列格式错误",
        description="通用日期校验失败，视列层级严重度不同",
        suggestions=[
            "统一日期格式为 YYYY-MM-DD",
            "避免中文日期、带时区后缀",
        ],
        severity="warning",
    ),
    "EMPTY_VALUE": ErrorHint(
        title="列含空值",
        description="通用空值提示，视列层级可 blocking（关键列）或 warning",
        suggestions=[
            "检查合并单元格是否向下填充",
            "小计行/空白行应删除",
        ],
        severity="warning",
    ),
}


def get_error_hint(code: str) -> Optional[ErrorHint]:
    """根据错误码返回 ErrorHint；未登记返回 None。"""
    return ERROR_HINTS.get(code)


def enrich_finding_with_hint(finding: dict) -> dict:
    """给一条 finding dict 附加 ``hint`` 字段（如果有登记）。

    用于 /diagnostics 端点响应增强。
    """
    code = finding.get("code")
    if not code:
        return finding
    hint = get_error_hint(code)
    if hint is None:
        return finding
    return {**finding, "hint": hint.model_dump()}


def all_registered_codes() -> set[str]:
    """返回所有已登记的错误码字符串集合（CI 一致性检查使用）。"""
    return set(ERROR_HINTS.keys())


def all_error_code_values() -> set[str]:
    """返回 ErrorCode 枚举的全部字符串值（CI 一致性检查使用）。"""
    return {c.value for c in ErrorCode}


__all__ = [
    "ErrorHint",
    "ERROR_HINTS",
    "get_error_hint",
    "enrich_finding_with_hint",
    "all_registered_codes",
    "all_error_code_values",
]
