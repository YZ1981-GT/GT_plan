"""批量建项服务 — 模板生成、批量导入、数据导出。

Feature: project-creation-enhancement, Task 8.1
"""

import logging
from datetime import date
from io import BytesIO
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import HTTPException
from openpyxl import Workbook, load_workbook
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.services.group_relation import (
    SELF_TOP,
    SELF_ULTIMATE,
    effective_parent_code,
    resolve_relation,
    self_reference_kind,
)

logger = logging.getLogger(__name__)


class BatchImportFailure(BaseModel):
    row_number: int
    errors: list[str]


class BatchImportResult(BaseModel):
    success_count: int
    fail_count: int
    failures: list[BatchImportFailure]


class RowError(BaseModel):
    """预校验行级错误（group-tree-architecture Task 7.2）。"""
    row_number: int
    errors: list[str]


class RowWarning(BaseModel):
    """预校验行级提示：不阻断导入，但要用户看一眼确认（consol-tree-three-code-autobuild 需求 1.5）。"""
    row_number: int
    messages: list[str]


class BatchValidateResponse(BaseModel):
    """批量导入预校验结果（dry-run，不入库，group-tree-architecture Task 7.2）。

    tree_preview: 由本批次行构建的集团树形预览（GroupTree 字典列表）
    errors: 行级错误（格式/必填/重复/循环引用）
    warnings: 行级提示（如上级代码与本企业相同 ⇒ 按「本企业就是上级企业」处理），不影响 valid
    """
    valid: bool
    total_rows: int
    tree_preview: list[dict]
    errors: list[RowError]
    warnings: list[RowWarning] = []


# 上级代码 = 本企业代码时的预校验提示（需求 1.5：批量导入没有交互确认，预校验即确认环节）
_SELF_REFERENCE_ROW_HINTS = {
    SELF_TOP: "上级企业代码与本企业代码相同，将按「本企业就是上级企业」处理（集团顶层企业，不另建上级节点）",
    SELF_ULTIMATE: "三个代码相同，将按「本企业即为最终控制方（集团总部或母公司）」处理",
}


# 数据表列标题（与模板一致）
# 注意：前 7 列为基础字段，第 8~9 列为集团架构代码（group-tree-architecture Task 7.1），
# 第 10 列为与上级关系（consol-tree-three-code-autobuild 需求 1/2）。新列只追加在末尾：
# 解析按位置取列，旧 9 列文件第 10 列视为空，按企业名称补默认关系（属性 P12）。
_TEMPLATE_COLUMNS = [
    "客户名称",
    "企业代码(USCC)",
    "项目简称",
    "审计年度",
    "项目类型",
    "会计准则",
    "报表类型",
    "上级企业代码(parent)",
    "最终控制方代码(ultimate)",
    "与上级关系(relation)",
]

# 与上级关系：中文 → 内部值（留空 = 按企业名称默认，见 group_relation.infer_relation_from_name）
_RELATION_MAP = {
    "子公司": "subsidiary",
    "分公司": "branch",
}
_RELATION_REVERSE = {v: k for k, v in _RELATION_MAP.items()}
# 第 10 列（0 基）在 _TEMPLATE_COLUMNS 中的位置
_RELATION_COL_INDEX = _TEMPLATE_COLUMNS.index("与上级关系(relation)")

# 项目类型映射：中文 → 内部值
_PROJECT_TYPE_MAP = {
    "年报审计": "annual",
    "专项审计": "special",
    "IPO审计": "ipo",
    "内控审计": "internal_control",
    "验资": "capital_verification",
    "税审": "tax_audit",
}

# 会计准则映射：中文 → 内部值
_ACCOUNTING_STANDARD_MAP = {
    "企业会计准则": "enterprise",
    "小企业会计准则": "small_enterprise",
    "金融企业会计准则": "financial",
    "政府会计准则": "government",
}

# 报表类型映射：中文 → 内部值
_REPORT_SCOPE_MAP = {
    "单户": "standalone",
    "合并": "consolidated",
}

# 最大导入行数
_MAX_IMPORT_ROWS = 500

# 默认报表类型
DEFAULT_REPORT_SCOPE = "standalone"

# 示例数据行（group-tree-architecture Task 7.1，Req 6.3；consol-tree-three-code-autobuild 需求 1）
# 展示「最终控制方（合并）→ 上级企业 → 子公司 / 分公司」集团层级填写方式。
# 四个 USCC 均为合法 18 位代码，仅作格式演示，正式导入前应删除或替换。
# 列顺序与 _TEMPLATE_COLUMNS 一致（10 列）。
_EX_ULTIMATE_CODE = "91110000100000000R"  # 最终控制方代码
_EX_PARENT_CODE = "911100002000000005"  # 上级企业代码
_EX_CHILD_CODE = "91110000300000000G"  # 子公司代码
_EX_BRANCH_CODE = "91110000400000000U"  # 分公司代码
_TEMPLATE_EXAMPLE_ROWS: list[list] = [
    # 最终控制方（集团顶层，报表类型=合并，无上级，ultimate 指向自身，关系留空）
    [
        "示例集团有限公司",
        _EX_ULTIMATE_CODE,
        "示例集团",
        2025,
        "年报审计",
        "企业会计准则",
        "合并",
        "",
        _EX_ULTIMATE_CODE,
        "",
    ],
    # 上级企业（中间层，上级为最终控制方，子公司）
    [
        "示例区域控股有限公司",
        _EX_PARENT_CODE,
        "区域控股",
        2025,
        "年报审计",
        "企业会计准则",
        "单户",
        _EX_ULTIMATE_CODE,
        _EX_ULTIMATE_CODE,
        "子公司",
    ],
    # 子公司（最底层，上级为区域控股，最终控制方为集团）
    [
        "示例子公司有限公司",
        _EX_CHILD_CODE,
        "示例子公司",
        2025,
        "年报审计",
        "企业会计准则",
        "单户",
        _EX_PARENT_CODE,
        _EX_ULTIMATE_CODE,
        "子公司",
    ],
    # 分公司（非独立法人，上级为集团，并入集团母公司汇总）
    [
        "示例集团有限公司上海分公司",
        _EX_BRANCH_CODE,
        "上海分公司",
        2025,
        "年报审计",
        "企业会计准则",
        "单户",
        _EX_ULTIMATE_CODE,
        _EX_ULTIMATE_CODE,
        "分公司",
    ],
]


async def generate_template() -> BytesIO:
    """生成建项模板 Excel（数据表 + 说明事项 sheet）。

    数据表列：客户名称, 企业代码(USCC), 项目简称, 审计年度, 项目类型, 会计准则,
              报表类型, 上级企业代码(parent), 最终控制方代码(ultimate), 与上级关系(relation)
    说明事项 sheet：各字段填写规则说明（含集团架构三代码与关系填写规则）
    数据表附示例数据行：展示「最终控制方 → 上级企业 → 子公司 / 分公司」集团层级填写方式
    与上级关系列带下拉（子公司 / 分公司），留空按企业名称默认
    """
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()

    # 数据表
    ws_data = wb.active
    ws_data.title = "数据"
    ws_data.append(_TEMPLATE_COLUMNS)

    # 示例数据行：展示集团层级填写方式（最终控制方 → 上级企业 → 子公司 / 分公司）
    # 注意：示例代码仅作格式演示，导入前请删除或替换为真实数据
    for example_row in _TEMPLATE_EXAMPLE_ROWS:
        ws_data.append(example_row)

    # 与上级关系列下拉（覆盖到最大导入行数，允许留空）
    relation_col = get_column_letter(_RELATION_COL_INDEX + 1)
    dv = DataValidation(
        type="list",
        formula1=f'"{",".join(_RELATION_MAP.keys())}"',
        allow_blank=True,
        showErrorMessage=True,
        errorTitle="与上级关系",
        error="只能选择 子公司 或 分公司，或留空按企业名称默认",
    )
    dv.add(f"{relation_col}2:{relation_col}{_MAX_IMPORT_ROWS + 1}")
    ws_data.add_data_validation(dv)

    # 说明事项 sheet
    ws_notes = wb.create_sheet("说明事项")
    instructions = [
        ["字段", "填写规则"],
        ["客户名称", "必填，被审计单位全称"],
        ["企业代码(USCC)", "必填，18位统一社会信用代码（不含I、O、Z、S、V）"],
        ["项目简称", "必填，用于审计报告等文档引用"],
        ["审计年度", "必填，4位数字年份（如 2025）"],
        ["项目类型", "必填，可选值：年报审计、专项审计、IPO审计、内控审计、验资、税审"],
        ["会计准则", "必填，可选值：企业会计准则、小企业会计准则、金融企业会计准则、政府会计准则"],
        ["报表类型", "选填，可选值：单户、合并（默认单户）"],
        [
            "上级企业代码(parent)",
            "选填，本企业直接上级（母公司）的18位统一社会信用代码（不含I、O、Z、S、V）；"
            "应指向同批次或系统中已存在某企业的「企业代码(USCC)」，用于构建集团层级；"
            "顶层最终控制方本身无上级，留空即可；填成本企业代码表示本企业就是上级企业"
            "（集团顶层，不另建上级节点），预校验会列出这些行供确认",
        ],
        [
            "最终控制方代码(ultimate)",
            "选填，本企业所属集团最终控制方的18位统一社会信用代码（不含I、O、Z、S、V）；"
            "同一集团内所有企业填写相同的最终控制方代码以归入同一棵集团树；"
            "留空表示该企业为独立企业，不纳入任何集团架构",
        ],
        [
            "与上级关系(relation)",
            "选填，可选值：子公司（独立法人，合并时抵销）、分公司（非独立法人，并入母公司汇总）；"
            "仅在上级企业代码已填且不是本企业代码时生效；留空则按企业名称默认"
            "（名称以分公司、分店、营业部、办事处等结尾，或「公司」二字后仍有字符的，默认为分公司，其余为子公司）",
        ],
        [
            "示例说明",
            "数据表中已附示例数据行（最终控制方→上级企业→子公司/分公司），仅作格式演示，"
            "正式导入前请删除示例行或替换为真实数据",
        ],
    ]
    for row in instructions:
        ws_notes.append(row)

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output


class ParsedRow(BaseModel):
    """单行解析结果（共享解析函数输出，group-tree-architecture Task 7.2）。

    仅包含格式/必填级别的解析结果，不含 DB 唯一性校验（那是 import-only）。
    """
    client_name: str
    company_code: str
    short_name: str
    audit_year: int | None
    project_type: str | None          # 内部值（已映射）
    accounting_standard: str | None   # 内部值（已映射）
    report_scope: str                 # 内部值（已映射，默认 standalone）
    parent_company_code: str          # 空串表示未填
    ultimate_company_code: str        # 空串表示未填
    relation_to_parent: str | None = None  # subsidiary / branch；None = 未填（导入时按名称默认）


def _load_data_sheet(file_bytes: bytes):
    """加载工作簿并定位「数据」sheet，返回数据行列表（不含表头）。

    超过最大行数限制时抛 HTTPException。
    """
    try:
        wb = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="文件格式不正确，请使用标准建项模板")

    # 定位数据 sheet
    if "数据" in wb.sheetnames:
        ws = wb["数据"]
    else:
        ws = wb.active

    rows = list(ws.iter_rows(min_row=2, values_only=True))
    if len(rows) > _MAX_IMPORT_ROWS:
        raise HTTPException(status_code=413, detail=f"文件超过最大行数限制（{_MAX_IMPORT_ROWS} 行）")
    return rows


def _is_blank_row(row) -> bool:
    """判断是否为全空行（应跳过）。"""
    return not row or all(cell is None or str(cell).strip() == "" for cell in row)


def _parse_row(row) -> tuple[ParsedRow, list[str]]:
    """共享行解析逻辑：解析单行 → (ParsedRow, 格式/必填级错误)。

    被 parse_and_import 与 validate_batch 共用。负责：
    - 字段提取（容错列数不足）
    - 必填校验、年度范围、类型/准则映射
    - company_code / parent / ultimate 的 USCC 格式校验
    不含 DB 唯一性校验（那需要 DB，仅 import 阶段执行）。
    """
    from app.services.uscc_validator import validate_uscc

    errors: list[str] = []

    def _cell(col_idx: int) -> str:
        if col_idx < len(row) and row[col_idx] is not None:
            return str(row[col_idx]).strip()
        return ""

    client_name = _cell(0)
    company_code = _cell(1)
    short_name = _cell(2)
    audit_year_str = _cell(3)
    project_type_cn = _cell(4)
    accounting_standard_cn = _cell(5)
    report_scope_cn = _cell(6)
    parent_company_code = _cell(7)
    ultimate_company_code = _cell(8)
    relation_cn = _cell(_RELATION_COL_INDEX)  # 旧 9 列文件恒为空串（兼容，P12）

    # 校验必填字段
    if not client_name:
        errors.append("客户名称为必填项")
    if not short_name:
        errors.append("项目简称为必填项")
    if not company_code:
        errors.append("企业代码为必填项")
    else:
        uscc_valid, uscc_error = validate_uscc(company_code)
        if not uscc_valid:
            errors.append(uscc_error or "企业代码格式错误")

    # 集团架构两代码（选填，非空时校验 USCC 格式）
    if parent_company_code:
        p_valid, p_error = validate_uscc(parent_company_code)
        if not p_valid:
            errors.append(f"上级企业代码格式错误：{p_error or 'USCC 格式不合规'}")
    if ultimate_company_code:
        u_valid, u_error = validate_uscc(ultimate_company_code)
        if not u_valid:
            errors.append(f"最终控制方代码格式错误：{u_error or 'USCC 格式不合规'}")
    # 上级代码 = 本企业代码 不是错误（需求 1.5）：表示本企业就是上级企业，预校验以提示列出

    # 与上级关系（选填；没有有效上级时忽略 —— 上级为空或就是本企业）
    relation_to_parent: str | None = None
    if relation_cn:
        relation_to_parent = _RELATION_MAP.get(relation_cn)
        if relation_to_parent is None:
            errors.append(f"与上级关系无效：{relation_cn}（只能填 子公司 或 分公司）")
    if effective_parent_code(company_code, parent_company_code) is None:
        relation_to_parent = None

    # 审计年度
    audit_year: int | None = None
    if not audit_year_str:
        errors.append("审计年度为必填项")
    else:
        try:
            audit_year = int(float(audit_year_str))
            if audit_year < 2000 or audit_year > 2100:
                errors.append("审计年度须在 2000-2100 之间")
        except (ValueError, TypeError):
            errors.append("审计年度必须为数字")

    # 项目类型
    project_type = _PROJECT_TYPE_MAP.get(project_type_cn)
    if not project_type_cn:
        errors.append("项目类型为必填项")
    elif project_type is None:
        errors.append(f"项目类型无效：{project_type_cn}")

    # 会计准则
    accounting_standard = _ACCOUNTING_STANDARD_MAP.get(accounting_standard_cn)
    if not accounting_standard_cn:
        errors.append("会计准则为必填项")
    elif accounting_standard is None:
        errors.append(f"会计准则无效：{accounting_standard_cn}")

    # 报表类型（选填，默认单户）
    report_scope = DEFAULT_REPORT_SCOPE
    if report_scope_cn:
        mapped = _REPORT_SCOPE_MAP.get(report_scope_cn)
        if mapped is None:
            errors.append(f"报表类型无效：{report_scope_cn}")
        else:
            report_scope = mapped

    parsed = ParsedRow(
        client_name=client_name,
        company_code=company_code,
        short_name=short_name,
        audit_year=audit_year,
        project_type=project_type,
        accounting_standard=accounting_standard,
        report_scope=report_scope,
        parent_company_code=parent_company_code,
        ultimate_company_code=ultimate_company_code,
        relation_to_parent=relation_to_parent,
    )
    return parsed, errors


async def _ensure_consolidated_root(
    ultimate_code: str,
    audit_year: int,
    name_hint: str,
    db: AsyncSession,
    created_by_code: dict,
) -> "Project | None":
    """确保 ultimate_code 对应的合并根项目存在，不存在则自动创建（Req 7.4）。

    判定顺序：
    1. 本批次已创建一个 company_code==ultimate_code 且 report_scope='consolidated'
       的项目 → 直接复用，不重复创建
    2. DB 中已存在同 company_code + 同年度 + report_scope='consolidated' 的项目
       → 复用
    3. 否则自动创建一个 report_scope='consolidated' 根项目（项目名默认取 ultimate
       企业名 name_hint，缺省回退 ultimate_code）

    auto_commit=False：由 parse_and_import 统一 commit。返回 Project（含已 flush 的 id）
    供后续 parent_project_id 链接使用；创建失败（唯一性冲突等）时返回已存在的项目或 None。
    """
    from app.models.audit_platform_schemas import BasicInfoSchema
    from app.services.project_wizard_service import create_project

    # 1. 本批次已创建的合并根项目
    in_batch = created_by_code.get(ultimate_code)
    if in_batch is not None and getattr(in_batch, "report_scope", None) == "consolidated":
        return in_batch

    # 2. DB 已存在同年度合并项目
    res = await db.execute(
        select(Project).where(
            Project.company_code == ultimate_code,
            Project.report_scope == "consolidated",
            Project.audit_year == audit_year,
            Project.is_deleted == False,  # noqa: E712
        )
    )
    db_existing = res.scalars().first()
    if db_existing is not None:
        return db_existing

    # 3. 自动创建合并根项目（项目名默认取 ultimate 企业名）
    display_name = (name_hint or "").strip() or f"{ultimate_code}（自动创建合并项目）"
    data = BasicInfoSchema(
        client_name=display_name,
        audit_year=audit_year,
        project_type="annual",
        accounting_standard="enterprise",
        company_code=ultimate_code,
        short_name=display_name[:100],
        report_scope="consolidated",
        ultimate_company_code=ultimate_code,
        ultimate_company_name=(name_hint or "").strip() or None,
    )
    try:
        # 自动建的合并根只继承同企业单户项目的集团关系，不外推（design §七）；链接整批统一重算
        proj = await create_project(
            data, db, auto_commit=False, propagate_group=False, sync_links=False
        )
        return proj
    except HTTPException:
        # 唯一性冲突等 → 复用已存在的合并项目（容错，不阻塞导入）
        res2 = await db.execute(
            select(Project).where(
                Project.company_code == ultimate_code,
                Project.report_scope == "consolidated",
                Project.audit_year == audit_year,
                Project.is_deleted == False,  # noqa: E712
            )
        )
        return res2.scalars().first()


async def parse_and_import(file_bytes: bytes, db: AsyncSession) -> BatchImportResult:
    """解析上传文件，逐行执行校验（与单项目相同：USCC格式+short_name非空+唯一性）并创建项目。

    集团架构扩展（group-tree-architecture Task 8.1，Req 7.1/7.2/7.4/7.5）：
    - 解析并写入 parent_company_code / ultimate_company_code 到 Project
    - ultimate 对应 report_scope='consolidated' 根项目不存在 → 自动创建
    - 派生链接 parent_project_id 整批结束后按年度调 group_links.sync_group_links 重算
      （同批次互引、先子后母、跨批次都一致；consol-tree-three-code-autobuild 需求 7.2/7.3）
    - 端点签名不变；service 只在编排边界统一 commit，flush 用于在 commit 前分配 PK

    返回成功数+失败明细。
    """
    from app.services.uniqueness_checker import check_uniqueness

    rows = _load_data_sheet(file_bytes)

    success_count = 0
    failures: list[BatchImportFailure] = []
    # company_code → 已创建的 Project（含 flush 后的 id），用于 ultimate 复用 + parent 链接
    created_by_code: dict[str, Project] = {}
    # 成功导入的解析行（用于 ultimate 集合 + 年度/名称查找）
    imported_parsed: list[ParsedRow] = []
    # company_code → client_name（用于自动建合并根时默认项目名）
    name_by_code: dict[str, str] = {}

    for idx, row in enumerate(rows, start=2):
        # 跳过全空行
        if _is_blank_row(row):
            continue

        # 共享解析（格式/必填/映射/USCC）
        parsed, row_errors = _parse_row(row)

        company_code = parsed.company_code
        audit_year = parsed.audit_year
        report_scope = parsed.report_scope

        # 唯一性校验（仅在前面基础校验通过后执行，import-only）
        if not row_errors and company_code and audit_year:
            is_unique, uniqueness_error = await check_uniqueness(
                company_code, audit_year, report_scope, db
            )
            if not is_unique:
                row_errors.append(uniqueness_error or "唯一性校验失败")

        if row_errors:
            failures.append(BatchImportFailure(row_number=idx, errors=row_errors))
            continue

        # 创建项目（auto_commit=False，由 batch service 统一 commit）
        try:
            from app.models.audit_platform_schemas import BasicInfoSchema
            from app.services.project_wizard_service import create_project

            data = BasicInfoSchema(
                client_name=parsed.client_name,
                audit_year=audit_year,
                project_type=parsed.project_type,
                accounting_standard=parsed.accounting_standard,
                company_code=company_code,
                short_name=parsed.short_name,
                report_scope=report_scope,
                # Req 7.1：写入集团架构两代码 + 与上级关系（持久化由 _sync_basic_info_to_project
                # 完成；关系留空时 create_project 内按企业名称补默认）
                parent_company_code=parsed.parent_company_code or None,
                ultimate_company_code=parsed.ultimate_company_code or None,
                relation_to_parent=parsed.relation_to_parent,
            )
            # 派生链接整批结束后按年度统一重算（sync_links=False），与行顺序无关
            project = await create_project(data, db, auto_commit=False, sync_links=False)
            created_by_code[company_code] = project
            name_by_code[company_code] = parsed.client_name
            imported_parsed.append(parsed)
            success_count += 1
        except HTTPException as e:
            failures.append(BatchImportFailure(row_number=idx, errors=[e.detail]))
        except Exception as e:
            # IntegrityError 等 DB 级约束违反（并发唯一性冲突）
            err_msg = str(e)
            if "uq_project_company_year_scope" in err_msg or "UNIQUE" in err_msg.upper():
                failures.append(BatchImportFailure(
                    row_number=idx, errors=["已存在该单位该年度的项目（并发冲突）"]
                ))
            else:
                failures.append(BatchImportFailure(row_number=idx, errors=[err_msg]))
            # 事务可能被污染，尝试 rollback 恢复
            try:
                await db.rollback()
            except Exception:
                pass

    # --- Req 7.4：为每个 ultimate 确保合并根项目存在（不存在则自动创建）---
    # 仅在有成功导入行时处理（保持 success_count + fail_count == 数据行数 的语义，
    # 自动创建的合并根不计入 success_count）
    if success_count > 0:
        # 收集 ultimate → 代表年度（取首个该 ultimate 成员的年度）
        ultimate_year: dict[str, int] = {}
        for p in imported_parsed:
            u = (p.ultimate_company_code or "").strip()
            if not u or p.audit_year is None:
                continue
            ultimate_year.setdefault(u, p.audit_year)

        for ultimate_code, year in ultimate_year.items():
            # 名称优先取本批次中 company_code==ultimate 的行的客户名
            name_hint = name_by_code.get(ultimate_code, "")
            await _ensure_consolidated_root(ultimate_code, year, name_hint, db, created_by_code)

    # --- 需求 7.2 / 7.3：派生链接 parent_project_id 按三码整年重算（与行顺序无关）---
    # 原实现逐行按上级代码找项目直接写链接：单体子公司会指向上级的单体项目、跨年时取到别的年度，
    # 且先建子后建母就挂不上。现改为整批结束后每个涉及的年度调一次 sync_group_links。
    if success_count > 0:
        from app.services.group_links import sync_group_links

        batch_years = sorted({p.audit_year for p in imported_parsed if p.audit_year})
        for year in batch_years:
            await sync_group_links(db, year)

    # 全部行处理完毕后统一 commit
    if success_count > 0:
        try:
            await db.commit()
        except Exception as e:
            # commit 阶段 IntegrityError（并发冲突）→ 全部回滚
            await db.rollback()
            err_msg = str(e)
            if "uq_project_company_year_scope" in err_msg or "UNIQUE" in err_msg.upper():
                return BatchImportResult(
                    success_count=0,
                    fail_count=success_count + len(failures),
                    failures=failures + [BatchImportFailure(
                        row_number=0, errors=["批量提交时检测到唯一性冲突，全部回滚"]
                    )],
                )
            raise

    return BatchImportResult(
        success_count=success_count,
        fail_count=len(failures),
        failures=failures,
    )


async def validate_batch(file_bytes: bytes, db: AsyncSession) -> BatchValidateResponse:
    """批量导入预校验（dry-run，绝不写库）。

    Feature: group-tree-architecture, Task 7.2
    Requirements: 8.1, 8.2, 8.3, 8.4, 7.3, 7.6

    流程：
    1. 复用共享解析函数 _parse_row 解析每行 → 收集格式/必填/USCC 错误
    2. 同批次重复 company_code 检测（Req 7.6）→ 在重复行追加错误（含重复行号）
    3. 用本批次解析行构建轻量 Project-like 对象 → 调
       consol_tree_service.build_group_trees_from_projects 构建树形预览
       （循环引用检测内含于 builder，标记 isCycleBreak）
    4. valid = 无任一行存在错误；total_rows = 非空数据行数
    5. 🔴 绝无 DB 写入：db 仅作只读签名占位（本实现不查 DB），不调 create_project/commit

    Args:
        file_bytes: 上传的 Excel 文件字节
        db: 数据库会话（保持与 parse_and_import 一致的签名；本函数不写库）

    Returns:
        BatchValidateResponse(valid, total_rows, tree_preview, errors)
    """
    from app.services import consol_tree_service

    rows = _load_data_sheet(file_bytes)

    # 行号 → 错误列表（仅记录非空数据行）
    row_errors_map: dict[int, list[str]] = {}
    # 行号 → 解析结果（用于后续构建树形预览 + 重复检测）
    parsed_by_row: dict[int, ParsedRow] = {}

    for idx, row in enumerate(rows, start=2):
        if _is_blank_row(row):
            continue
        parsed, errors = _parse_row(row)
        row_errors_map[idx] = errors
        parsed_by_row[idx] = parsed

    total_rows = len(parsed_by_row)

    # --- 同批次重复 company_code 检测（Req 7.6）---
    code_to_rows: dict[str, list[int]] = {}
    for idx, parsed in parsed_by_row.items():
        code = (parsed.company_code or "").strip()
        if not code:
            continue
        code_to_rows.setdefault(code, []).append(idx)

    for code, idx_list in code_to_rows.items():
        if len(idx_list) >= 2:
            dup_rows_str = "、".join(str(i) for i in sorted(idx_list))
            for idx in idx_list:
                row_errors_map[idx].append(
                    f"企业代码重复（与行 {dup_rows_str} 重复）"
                )

    # --- 构建树形预览（本批次行，不入库）---
    # 与集团架构森林同一构建函数（需求 8.6）：企业实体、上级边、年度解析都同源。
    # SimpleNamespace 构造 Project-like 对象，缺省属性由构建函数按空处理。
    preview_projects: list = []
    for idx, parsed in parsed_by_row.items():
        ape = None
        if parsed.audit_year:
            try:
                ape = date(parsed.audit_year, 12, 31)
            except (ValueError, TypeError):
                ape = None
        preview_projects.append(
            SimpleNamespace(
                id=uuid4(),
                company_code=parsed.company_code or "",
                parent_company_code=parsed.parent_company_code or None,
                ultimate_company_code=parsed.ultimate_company_code or None,
                relation_to_parent=resolve_relation(
                    parsed.relation_to_parent,
                    parsed.parent_company_code,
                    parsed.client_name,
                    parsed.company_code,
                ),
                client_name=parsed.client_name or parsed.company_code or "",
                report_scope=parsed.report_scope,
                status=None,
                audit_period_end=ape,
                audit_year=parsed.audit_year,
                consol_level=1,
            )
        )

    try:
        tree_result = consol_tree_service.build_group_trees_from_projects(preview_projects)
        tree_preview = list(tree_result.get("trees", []))
        independents = tree_result.get("independents", [])
        if independents:
            # 独立节点（没有上下级与控制方 / 缺企业代码）作为一棵虚拟"独立企业"树附加
            tree_preview.append({
                "key": "__independent__",
                "ultimateCode": None,
                "ultimateName": "独立企业",
                "rootProjectId": None,
                "year": None,
                "children": independents,
            })
    except Exception:
        # 树形预览构建失败不应阻塞行级校验结果返回，但要留痕（否则构建函数的缺陷只表现为「预览为空」）
        logger.exception("批量导入预览树构建失败")
        tree_preview = []

    # --- 汇总行级错误 ---
    errors: list[RowError] = [
        RowError(row_number=idx, errors=errs)
        for idx, errs in sorted(row_errors_map.items())
        if errs
    ]

    # --- 行级提示（不影响 valid）：上级代码 = 本企业代码 ⇒ 本企业就是上级企业（需求 1.5）---
    warnings: list[RowWarning] = []
    for idx, parsed in sorted(parsed_by_row.items()):
        kind = self_reference_kind(
            parsed.company_code, parsed.parent_company_code, parsed.ultimate_company_code
        )
        if kind is not None:
            warnings.append(RowWarning(row_number=idx, messages=[_SELF_REFERENCE_ROW_HINTS[kind]]))

    valid = len(errors) == 0

    return BatchValidateResponse(
        valid=valid,
        total_rows=total_rows,
        tree_preview=tree_preview,
        errors=errors,
        warnings=warnings,
    )


# 反向映射（内部值 → 中文）
_PROJECT_TYPE_REVERSE = {v: k for k, v in _PROJECT_TYPE_MAP.items()}
_ACCOUNTING_STANDARD_REVERSE = {v: k for k, v in _ACCOUNTING_STANDARD_MAP.items()}
_REPORT_SCOPE_REVERSE = {v: k for k, v in _REPORT_SCOPE_MAP.items()}


async def export_projects(project_ids: list[UUID], db: AsyncSession) -> BytesIO:
    """导出选中项目为 Excel（字段结构与模板数据表一致）。"""
    result = await db.execute(
        select(Project).where(
            Project.id.in_(project_ids),
            Project.is_deleted == False,  # noqa: E712
        )
    )
    projects = result.scalars().all()

    wb = Workbook()
    ws = wb.active
    ws.title = "数据"
    ws.append(_TEMPLATE_COLUMNS)

    for p in projects:
        ws.append([
            p.client_name,
            p.company_code or "",
            p.short_name or "",
            p.audit_year or "",
            _PROJECT_TYPE_REVERSE.get(p.project_type.value if p.project_type else "", ""),
            _ACCOUNTING_STANDARD_REVERSE.get(
                _get_accounting_standard(p), ""
            ),
            _REPORT_SCOPE_REVERSE.get(p.report_scope or DEFAULT_REPORT_SCOPE, "单户"),
            p.parent_company_code or "",
            p.ultimate_company_code or "",
            _RELATION_REVERSE.get(p.relation_to_parent or "", ""),
        ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def _get_accounting_standard(project: Project) -> str:
    """从 wizard_state 提取 accounting_standard 值。

    create_project() 将 BasicInfoSchema.model_dump() 写入
    wizard_state.steps.basic_info.data，因此字符串值一定在此路径下。
    """
    ws = project.wizard_state or {}
    steps = ws.get("steps", {})
    # 兼容两种 key 格式：直接 "basic_info" 或嵌套对象
    basic_info_step = steps.get("basic_info", {})
    data = basic_info_step.get("data", {})
    return data.get("accounting_standard", "")
