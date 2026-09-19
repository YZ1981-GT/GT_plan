"""公式管理库（Formula Management Library）服务包。

统一治理公式编辑/计算/保存三能力及其全链路契约。
当前导出：
- resolve_ref / ResolveRefResult: 封装 ACNR full_resolve 的统一引用解析入口（fail-open）
- execute_formula: 三类型（auto_calc / logic_check / reasonability）分派执行入口
- FormulaRecord / FormulaExecResult / IssueItem / HintItem: 公式定义与执行结果结构
- AdjudicationWritebackService / AdjudicationWritebackResult: 审定表回写 audited_amount（Req 13）
- guard_four_table_leaf_readonly / is_four_table_target: 四表库叶子源只读守卫（Req 12.2）
- tb_value / prev_value / aux_value: TB()/PREV()/AUX() 四表库取数契约（Req 12.1/12.3/12.4/12.5）
"""

from app.services.formula_management.adjudication_writeback import (
    AdjudicationWritebackResult,
    AdjudicationWritebackService,
)
from app.services.formula_management.delivery_export import (
    DanglingRef,
    FlattenResult,
    content_disposition_attachment,
    flatten_workbook_formulas,
)
from app.services.formula_management.engine import (
    FormulaExecResult,
    FormulaRecord,
    HintItem,
    IssueItem,
    ResolveRefResult,
    execute_formula,
    resolve_ref,
)
from app.services.formula_management.four_table_source import (
    FOUR_TABLE_NAMES,
    FourTableReadonlyError,
    aux_value,
    guard_four_table_leaf_readonly,
    is_four_table_target,
    prev_value,
    tb_value,
)
from app.services.formula_management.formula_import_export import (
    ImportResult,
    ImportSkip,
    build_data_workbook,
    build_template_workbook,
    parse_import_rows,
    workbook_to_bytes,
)
from app.services.formula_management.reporting_instructions import (
    DOC_TITLE,
    DOC_VERSION,
    get_reporting_instructions,
    instructions_as_dict,
    instructions_as_markdown,
    instructions_as_rows,
)

__all__ = [
    "ResolveRefResult",
    "resolve_ref",
    "execute_formula",
    "FormulaRecord",
    "FormulaExecResult",
    "IssueItem",
    "HintItem",
    "AdjudicationWritebackService",
    "AdjudicationWritebackResult",
    # 交付导出：公式解析为静态值 + RFC5987 文件名（Task 10.1 / Req 18）
    "flatten_workbook_formulas",
    "FlattenResult",
    "DanglingRef",
    "content_disposition_attachment",
    # 四表库叶子源只读守卫 + 取数契约（Task 2.3）
    "FOUR_TABLE_NAMES",
    "FourTableReadonlyError",
    "is_four_table_target",
    "guard_four_table_leaf_readonly",
    "tb_value",
    "prev_value",
    "aux_value",
    # 公式模块导入导出（Task 14.4 / Req 23）
    "build_template_workbook",
    "build_data_workbook",
    "parse_import_rows",
    "workbook_to_bytes",
    "ImportResult",
    "ImportSkip",
    # 编报说明/说明文档单一源（Req 23.6 / 25.3）
    "DOC_TITLE",
    "DOC_VERSION",
    "get_reporting_instructions",
    "instructions_as_dict",
    "instructions_as_markdown",
    "instructions_as_rows",
]
