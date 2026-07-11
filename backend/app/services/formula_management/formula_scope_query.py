"""公式作用域过滤查询服务（formula-management-library Req 24 / Task 20.2）。

按 ``Formula_Scope``（7 类页面作用域）过滤公式列表，供：
- Req 24 前端公式弹窗按当前页面作用域加载本域公式（``list_by_scope``）；
- 全局公式管理页跨全部作用域取并集（``list_grouped_by_scope``）。

存储真源（已 codegraph 实证）：``wp_formula`` 表是**底稿域（WP domain）**的自定义
公式统一存储（``id/project_id/wp_id/sheet_name/target_cell/expression/formula_type
/refs/...``，见 ``workpaper_models.py:WpFormula``），本身不带 ``scope`` 列。作用域是
**页面类别**维度，需由该公式所属底稿（``wp_id → working_paper → wp_index``）的
``wp_code`` / ``wp_name`` 派生。因此本服务不新建并行存储，而是在既有 ``wp_formula``
之上做**确定性作用域分类 + 过滤**（``classify_scope``），把每条公式归入唯一作用域。

作用域隔离保证（Req 24.5）：``classify_scope`` 是 ``(wp_code, wp_name)`` 的**纯确定性
单值函数** → 全部公式据此划分为**互斥**的作用域子集。因此对某一作用域内公式的
增/改/删只会改变该作用域的列表，其余作用域列表逐一不变（隔离由划分不相交保证）。

工程铁律（遵循 memory）：
- 本服务只做**查询**，只 ``flush``（实际无写入）、不 ``commit``（router 层负责）。
- 全 async；JOIN 走 ORM ``select``；对无 wp_index 的公式 LEFT JOIN 回退默认作用域。
- 不臆造：``wp_formula`` 是 WP 域存储 → 未命中显式域标记的公式一律归 ``workpaper``
  （WP 域的正确默认），而非猜测其属于报表/附注/试算等他域。
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WorkingPaper, WpFormula, WpIndex

# ── Formula_Scope 7 类（与前端 FormulaManagerScope 对齐，见 design §15）──
#   note / consol_note / consol_worksheet / consol_report / report / tb / workpaper
FORMULA_SCOPES: tuple[str, ...] = (
    "note",
    "consol_note",
    "consol_worksheet",
    "consol_report",
    "report",
    "tb",
    "workpaper",
)

# 作用域中文标签（与前端 SCOPE_LABEL_MAP 一致，供响应展示用）。
SCOPE_LABEL_MAP: dict[str, str] = {
    "note": "单体附注",
    "consol_note": "合并附注",
    "consol_worksheet": "合并工作底稿",
    "consol_report": "合并报表",
    "report": "报表",
    "tb": "试算平衡表",
    "workpaper": "底稿",
}

# WP 域的默认作用域：wp_formula 是底稿域存储，未命中显式域标记时归此。
_DEFAULT_SCOPE = "workpaper"


def _as_uuid(value: uuid.UUID | str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def classify_scope(wp_code: str | None, wp_name: str | None = None) -> str:
    """把一条公式所属底稿的 ``(wp_code, wp_name)`` 分类到唯一 Formula_Scope。

    确定性单值函数（作用域隔离的基石）。分类优先级（自上而下，命中即返回）：

    1. 合并族（consolidation）：``wp_code`` 以 ``CONSOL`` 前缀，或 ``wp_name`` 以
       "合并" 开头 → 再按名称细分 ``consol_note`` / ``consol_report`` /
       ``consol_worksheet``（默认合并工作底稿）。
    2. 顶层他域（``wp_code`` 前缀约定优先）：``TB*`` → ``tb``；``REPORT*`` / ``RPT*``
       → ``report``；``NOTE*`` → ``note``。
    3. 兜底：``workpaper``（WP 域正确默认，不臆造归他域）。

    Args:
        wp_code: 所属底稿编码（可为 None，如公式无 wp_index）。
        wp_name: 所属底稿名称（可选，仅用于合并族细分）。

    Returns:
        7 类 Formula_Scope 之一。
    """
    code = (wp_code or "").strip().upper()
    name = (wp_name or "").strip()

    # ① 合并族 ──────────────────────────────────────────────
    if code.startswith("CONSOL") or name.startswith("合并"):
        if "附注" in name:
            return "consol_note"
        if "报表" in name:
            return "consol_report"
        return "consol_worksheet"

    # ② 顶层他域（wp_code 前缀约定）────────────────────────────
    if code.startswith("TB"):
        return "tb"
    if code.startswith("REPORT") or code.startswith("RPT"):
        return "report"
    if code.startswith("NOTE"):
        return "note"

    # ③ 兜底：底稿域默认 ────────────────────────────────────
    return _DEFAULT_SCOPE


def formula_to_dict(f: WpFormula, scope: str) -> dict:
    """将 WpFormula 序列化为前端可消费的 dict（含派生 scope 标注）。"""
    return {
        "id": str(f.id),
        "project_id": str(f.project_id),
        "wp_id": str(f.wp_id),
        "sheet_name": f.sheet_name,
        "target_cell": f.target_cell,
        "expression": f.expression,
        "category": f.category,
        "description": f.description,
        "formula_type": f.formula_type,
        "formula_source": getattr(f, "formula_source", None),
        "refs": f.refs,
        "issue_description": f.issue_description,
        "hint_text": f.hint_text,
        "last_computed_at": (
            f.last_computed_at.isoformat() if f.last_computed_at else None
        ),
        "scope": scope,
        "scope_label": SCOPE_LABEL_MAP.get(scope, scope),
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


class FormulaScopeQueryService:
    """公式作用域过滤查询（list_by_scope / list_grouped_by_scope）。"""

    async def _load_project_formulas(
        self, db: AsyncSession, project_id: uuid.UUID
    ) -> list[tuple[WpFormula, str]]:
        """加载某项目全部 wp_formula 并计算各自作用域。

        经 ``wp_formula → working_paper → wp_index`` LEFT OUTER JOIN 取
        ``wp_code`` / ``wp_name``（缺失回退默认作用域），返回 ``[(公式, scope)]``。
        """
        stmt = (
            sa.select(WpFormula, WpIndex.wp_code, WpIndex.wp_name)
            .select_from(WpFormula)
            .outerjoin(WorkingPaper, WorkingPaper.id == WpFormula.wp_id)
            .outerjoin(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
            .where(WpFormula.project_id == project_id)
            .order_by(
                WpFormula.wp_id, WpFormula.sheet_name, WpFormula.target_cell
            )
        )
        rows = (await db.execute(stmt)).all()
        return [(row[0], classify_scope(row[1], row[2])) for row in rows]

    async def list_by_scope(
        self, db: AsyncSession, *, project_id: uuid.UUID | str, scope: str
    ) -> list[WpFormula]:
        """列出某项目下**指定作用域**的公式（供弹窗按域加载，Req 24.1）。

        Args:
            db: AsyncSession。
            project_id: 项目 id。
            scope: 目标 Formula_Scope（须属 FORMULA_SCOPES，否则 ValueError）。

        Returns:
            仅属于 ``scope`` 的公式列表（其余作用域公式被过滤，Req 24.2）。
        """
        if scope not in FORMULA_SCOPES:
            raise ValueError(
                f"非法作用域 '{scope}'，须为 {'/'.join(FORMULA_SCOPES)} 之一"
            )
        project_uuid = _as_uuid(project_id)
        classified = await self._load_project_formulas(db, project_uuid)
        return [f for (f, s) in classified if s == scope]

    async def list_grouped_by_scope(
        self, db: AsyncSession, *, project_id: uuid.UUID | str
    ) -> dict[str, list[WpFormula]]:
        """列出某项目下全部公式，按作用域分组（供全局公式页取并集，Req 24.3）。

        Returns:
            ``{scope: [公式,...]}``，含全部 7 类作用域键（无公式的作用域为空列表），
            使前端全局页可据此渲染各域根节点。各作用域列表互不相交（Req 24.5）。
        """
        project_uuid = _as_uuid(project_id)
        classified = await self._load_project_formulas(db, project_uuid)
        grouped: dict[str, list[WpFormula]] = {s: [] for s in FORMULA_SCOPES}
        for formula, scope in classified:
            grouped[scope].append(formula)
        return grouped


# 模块级单例（与 wp_formula_service / address_registry 等一致的使用风格）
formula_scope_query_service = FormulaScopeQueryService()
