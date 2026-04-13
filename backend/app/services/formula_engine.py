"""取数公式引擎 — 底稿公式驱动取数 + Redis缓存 + 错误处理

支持5种公式类型：
- TB(account_code, column_name) — 从 trial_balance 取数
- WP(wp_code, cell_ref) — 跨底稿引用（MVP stub）
- AUX(account_code, aux_type, aux_name, column_name) — 从辅助余额表取数
- PREV(inner_formula) — 上年数据（year-1 递归）
- SUM_TB(account_range, column_name) — 科目范围汇总

Validates: Requirements 2.1-2.10
"""

from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbAuxBalance, TrialBalance

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FormulaError
# ---------------------------------------------------------------------------

class FormulaError:
    """公式执行错误对象"""

    def __init__(self, code: str = "FORMULA_ERROR", message: str = ""):
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


# ---------------------------------------------------------------------------
# Column name mapping (Chinese → TrialBalance field)
# ---------------------------------------------------------------------------

TB_COLUMN_MAP: dict[str, str] = {
    "期末余额": "audited_amount",
    "未审数": "unadjusted_amount",
    "AJE调整": "aje_adjustment",
    "RJE调整": "rje_adjustment",
    "年初余额": "opening_balance",
}

AUX_COLUMN_MAP: dict[str, str] = {
    "期初余额": "opening_balance",
    "借方发生额": "debit_amount",
    "贷方发生额": "credit_amount",
    "期末余额": "closing_balance",
}


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

class TBExecutor:
    """TB(account_code, column_name) → 从 trial_balance 取数

    Validates: Requirements 2.1, 2.2
    """

    async def execute(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        params: dict,
    ) -> Decimal | FormulaError:
        account_code = params.get("account_code", "")
        column_name = params.get("column_name", "")

        field = TB_COLUMN_MAP.get(column_name)
        if not field:
            return FormulaError(
                message=f"未知列名'{column_name}'，支持: {', '.join(TB_COLUMN_MAP.keys())}"
            )

        result = await db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code == account_code,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return FormulaError(message=f"科目{account_code}不存在")

        val = getattr(row, field, None)
        return val if val is not None else Decimal("0")


class WPExecutor:
    """WP(wp_code, cell_ref) → 跨底稿引用（MVP stub）

    Validates: Requirements 2.1, 2.3
    """

    async def execute(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        params: dict,
    ) -> Any | FormulaError:
        wp_code = params.get("wp_code", "")
        cell_ref = params.get("cell_ref", "")

        if not wp_code or not cell_ref:
            return FormulaError(message="WP函数需要wp_code和cell_ref参数")

        # MVP stub: return placeholder
        # Full implementation would query working_paper table for file_path,
        # then use openpyxl to read the cell value
        return FormulaError(
            message=f"WP({wp_code},{cell_ref})暂不支持，MVP阶段请使用离线编辑"
        )


class AUXExecutor:
    """AUX(account_code, aux_type, aux_name, column_name) → 从辅助余额表取数

    Validates: Requirements 2.1, 2.4
    """

    async def execute(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        params: dict,
    ) -> Decimal | FormulaError:
        account_code = params.get("account_code", "")
        aux_type = params.get("aux_type", "")
        aux_name = params.get("aux_name", "")
        column_name = params.get("column_name", "")

        field = AUX_COLUMN_MAP.get(column_name)
        if not field:
            return FormulaError(
                message=f"未知辅助列名'{column_name}'，支持: {', '.join(AUX_COLUMN_MAP.keys())}"
            )

        result = await db.execute(
            sa.select(TbAuxBalance).where(
                TbAuxBalance.project_id == project_id,
                TbAuxBalance.year == year,
                TbAuxBalance.account_code == account_code,
                TbAuxBalance.aux_type == aux_type,
                TbAuxBalance.aux_name == aux_name,
                TbAuxBalance.is_deleted == sa.false(),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return FormulaError(
                message=f"辅助余额不存在: 科目{account_code}, {aux_type}={aux_name}"
            )

        val = getattr(row, field, None)
        return val if val is not None else Decimal("0")


class PREVExecutor:
    """PREV(inner_formula) → 递归调用 year-1

    Validates: Requirements 2.1, 2.5
    """

    async def execute(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        params: dict,
        engine: "FormulaEngine",
    ) -> Any | FormulaError:
        inner_type = params.get("inner_type", "")
        inner_params = params.get("inner_params", {})

        if not inner_type:
            return FormulaError(message="PREV函数需要inner_type参数")

        return await engine.execute(
            db=db,
            project_id=project_id,
            year=year - 1,
            formula_type=inner_type,
            params=inner_params,
        )


class SumTBExecutor:
    """SUM_TB(account_range, column_name) → 科目范围汇总

    Validates: Requirements 2.1, 2.6
    """

    async def execute(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        params: dict,
    ) -> Decimal | FormulaError:
        account_range = params.get("account_range", "")
        column_name = params.get("column_name", "")

        field = TB_COLUMN_MAP.get(column_name)
        if not field:
            return FormulaError(
                message=f"未知列名'{column_name}'，支持: {', '.join(TB_COLUMN_MAP.keys())}"
            )

        parts = account_range.split("~")
        if len(parts) != 2:
            return FormulaError(
                message=f"无效科目范围'{account_range}'，格式应为'start~end'"
            )

        start_code, end_code = parts[0].strip(), parts[1].strip()

        result = await db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code >= start_code,
                TrialBalance.standard_account_code <= end_code,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        rows = result.scalars().all()

        total = Decimal("0")
        for row in rows:
            val = getattr(row, field, None)
            total += val if val is not None else Decimal("0")

        return total


# ---------------------------------------------------------------------------
# FormulaEngine
# ---------------------------------------------------------------------------

class FormulaEngine:
    """取数公式引擎 — 公式类型注册 + Redis缓存 + 批量执行 + 自定义函数扩展

    Validates: Requirements 2.8, 2.9, 2.10, 4.3
    """

    FORMULA_TYPES: dict[str, Any] = {
        "TB": TBExecutor,
        "WP": WPExecutor,
        "AUX": AUXExecutor,
        "PREV": PREVExecutor,
        "SUM_TB": SumTBExecutor,
    }

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._executors: dict[str, Any] = {
            k: v() for k, v in self.FORMULA_TYPES.items()
        }
        # 用户自定义函数注册表 {name: CustomFunctionDef}
        self._custom_functions: dict[str, "CustomFunctionDef"] = {}

    # ------------------------------------------------------------------
    # 自定义函数 DSL 扩展（Task 6.4）
    # ------------------------------------------------------------------

    def register_custom_function(
        self,
        name: str,
        expression: str,
        description: str = "",
        param_names: list[str] | None = None,
    ) -> dict:
        """注册用户自定义公式函数

        Args:
            name: 函数名（大写，如 "NET_ASSET"）
            expression: 公式表达式，引用内置函数，如 "TB(account_code, '期末余额') - TB(account_code, '年初余额')"
            description: 函数说明
            param_names: 参数名列表，如 ["account_code"]

        Returns:
            注册结果 dict
        """
        name = name.upper().strip()
        if not name:
            raise ValueError("函数名不能为空")
        if name in self.FORMULA_TYPES:
            raise ValueError(f"'{name}' 是内置函数，不能覆盖")
        if not _validate_custom_expression(expression):
            raise ValueError(f"表达式语法不合法: {expression}")

        func_def = CustomFunctionDef(
            name=name,
            expression=expression,
            description=description,
            param_names=param_names or [],
        )
        self._custom_functions[name] = func_def
        logger.info("注册自定义函数: %s = %s", name, expression)
        return {
            "name": name,
            "expression": expression,
            "description": description,
            "param_names": func_def.param_names,
        }

    def unregister_custom_function(self, name: str) -> bool:
        """注销自定义函数"""
        name = name.upper().strip()
        if name in self._custom_functions:
            del self._custom_functions[name]
            return True
        return False

    def list_custom_functions(self) -> list[dict]:
        """列出所有已注册的自定义函数"""
        return [
            {
                "name": f.name,
                "expression": f.expression,
                "description": f.description,
                "param_names": f.param_names,
            }
            for f in self._custom_functions.values()
        ]

    def list_all_functions(self) -> list[dict]:
        """列出所有可用函数（内置 + 自定义）"""
        built_in = [
            {"name": k, "type": "built_in", "description": v.__doc__ or ""}
            for k, v in self.FORMULA_TYPES.items()
        ]
        custom = [
            {"name": f.name, "type": "custom", "description": f.description, "expression": f.expression}
            for f in self._custom_functions.values()
        ]
        return built_in + custom

    @staticmethod
    def _cache_key(project_id: UUID, year: int, formula_type: str, params: dict) -> str:
        """Generate Redis cache key"""
        params_hash = hashlib.md5(
            json.dumps(params, sort_keys=True, default=str).encode()
        ).hexdigest()
        return f"formula:{project_id}:{year}:{formula_type}:{params_hash}"

    async def execute(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        formula_type: str,
        params: dict,
    ) -> dict:
        """Execute a single formula. Returns FormulaResult dict.

        Validates: Requirements 2.8, 2.9, 2.10
        """
        # Validate formula type
        if formula_type not in self._executors:
            # Check custom functions
            if formula_type in self._custom_functions:
                return await self._execute_custom(
                    db, project_id, year, formula_type, params
                )
            return {
                "value": None,
                "cached": False,
                "error": f"未知公式类型'{formula_type}'，支持: {', '.join(list(self.FORMULA_TYPES.keys()) + list(self._custom_functions.keys()))}",
            }

        cache_key = self._cache_key(project_id, year, formula_type, params)

        # Check Redis cache
        if self._redis:
            try:
                cached = await self._redis.get(cache_key)
                if cached is not None:
                    return {"value": json.loads(cached), "cached": True, "error": None}
            except Exception:
                logger.warning("Redis cache read failed, proceeding without cache")

        # Execute formula
        executor = self._executors[formula_type]
        if formula_type == "PREV":
            result = await executor.execute(db, project_id, year, params, self)
            # PREV returns a dict from recursive call
            if isinstance(result, dict):
                # Cache the result
                if self._redis and result.get("error") is None:
                    try:
                        await self._redis.set(
                            cache_key,
                            json.dumps(result["value"], default=str),
                            ex=300,  # TTL 5 min
                        )
                    except Exception:
                        logger.warning("Redis cache write failed")
                return result
        else:
            result = await executor.execute(db, project_id, year, params)

        # Handle FormulaError
        if isinstance(result, FormulaError):
            return {"value": None, "cached": False, "error": result.message}

        # Convert Decimal to float for JSON serialization
        value = float(result) if isinstance(result, Decimal) else result

        # Write to cache
        if self._redis:
            try:
                await self._redis.set(
                    cache_key,
                    json.dumps(value, default=str),
                    ex=300,  # TTL 5 min
                )
            except Exception:
                logger.warning("Redis cache write failed")

        return {"value": value, "cached": False, "error": None}

    async def batch_execute(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        formulas: list[dict],
    ) -> list[dict]:
        """Batch execute formulas. Each item: {formula_type, params}

        Validates: Requirements 2.9
        """
        results = []
        for f in formulas:
            r = await self.execute(
                db=db,
                project_id=project_id,
                year=year,
                formula_type=f.get("formula_type", ""),
                params=f.get("params", {}),
            )
            results.append(r)
        return results

    async def invalidate_cache(
        self,
        project_id: UUID,
        year: int,
        affected_accounts: list[str] | None = None,
    ) -> int:
        """Invalidate formula cache entries.

        affected_accounts=None → invalidate all for project/year
        affected_accounts=[...] → invalidate all (simple approach for MVP)

        Returns count of deleted keys.
        """
        if not self._redis:
            return 0

        try:
            pattern = f"formula:{project_id}:{year}:*"
            deleted = 0
            async for key in self._redis.scan_iter(match=pattern):
                await self._redis.delete(key)
                deleted += 1
            return deleted
        except Exception:
            logger.warning("Redis cache invalidation failed")
            return 0

    # ------------------------------------------------------------------
    # 自定义函数执行（Task 6.4）
    # ------------------------------------------------------------------

    async def _execute_custom(
        self,
        db: AsyncSession,
        project_id: UUID,
        year: int,
        func_name: str,
        params: dict,
    ) -> dict:
        """执行自定义函数：解析表达式中的内置函数调用并求值"""
        func_def = self._custom_functions.get(func_name)
        if not func_def:
            return {"value": None, "cached": False, "error": f"自定义函数 '{func_name}' 不存在"}

        try:
            # 将参数替换到表达式中
            expr = func_def.expression
            for pname in func_def.param_names:
                if pname in params:
                    expr = expr.replace(pname, repr(params[pname]))

            # 解析并执行表达式中的内置函数调用
            value = await _eval_custom_expression(self, db, project_id, year, expr)
            return {"value": value, "cached": False, "error": None}
        except Exception as e:
            logger.warning("自定义函数 %s 执行失败: %s", func_name, e)
            return {"value": None, "cached": False, "error": f"自定义函数执行失败: {e}"}


# ---------------------------------------------------------------------------
# 自定义函数定义
# ---------------------------------------------------------------------------

class CustomFunctionDef:
    """自定义函数定义"""

    def __init__(
        self,
        name: str,
        expression: str,
        description: str = "",
        param_names: list[str] | None = None,
    ):
        self.name = name
        self.expression = expression
        self.description = description
        self.param_names = param_names or []


# ---------------------------------------------------------------------------
# 自定义函数表达式验证与求值
# ---------------------------------------------------------------------------

import re as _re

_FUNC_CALL_RE = _re.compile(
    r"(TB|WP|AUX|PREV|SUM_TB)\s*\(([^)]*)\)"
)

_ALLOWED_EXPR_RE = _re.compile(
    r"^[\d\s\+\-\*/\(\)\.,\'\"a-zA-Z_\u4e00-\u9fff]+$"
)


def _validate_custom_expression(expression: str) -> bool:
    """验证自定义函数表达式语法安全性

    允许：内置函数调用、四则运算、数字、字符串参数
    禁止：import、exec、eval、__等危险操作
    """
    if not expression or not expression.strip():
        return False
    dangerous = ["import", "exec", "eval", "__", "open", "os.", "sys."]
    lower = expression.lower()
    for d in dangerous:
        if d in lower:
            return False
    # 必须包含至少一个内置函数调用或纯数字表达式
    if not _FUNC_CALL_RE.search(expression) and not expression.strip().replace(".", "").replace("-", "").isdigit():
        return False
    return True


async def _eval_custom_expression(
    engine: FormulaEngine,
    db: "AsyncSession",
    project_id: "UUID",
    year: int,
    expression: str,
) -> float | None:
    """安全求值自定义表达式：提取内置函数调用→逐个执行→替换为结果→算术求值"""
    expr = expression

    # 逐个替换内置函数调用为数值
    for match in _FUNC_CALL_RE.finditer(expression):
        func_type = match.group(1)
        args_str = match.group(2)
        # 解析参数
        args = [a.strip().strip("'\"") for a in args_str.split(",")]
        params: dict = {}
        if func_type == "TB" and len(args) >= 2:
            params = {"account_code": args[0], "column_name": args[1]}
        elif func_type == "SUM_TB" and len(args) >= 2:
            params = {"account_range": args[0], "column_name": args[1]}
        elif func_type == "AUX" and len(args) >= 4:
            params = {"account_code": args[0], "aux_type": args[1], "aux_name": args[2], "column_name": args[3]}
        elif func_type == "WP" and len(args) >= 2:
            params = {"wp_code": args[0], "cell_ref": args[1]}

        result = await engine.execute(db, project_id, year, func_type, params)
        val = result.get("value")
        if val is None:
            val = 0
        expr = expr.replace(match.group(0), str(float(val)), 1)

    # 安全算术求值（仅允许数字和四则运算）
    expr = expr.strip()
    if not _re.match(r"^[\d\s\+\-\*/\(\)\.]+$", expr):
        raise ValueError(f"表达式包含不安全字符: {expr}")

    try:
        return float(eval(expr))  # noqa: S307 — 已验证仅含数字和运算符
    except Exception as e:
        raise ValueError(f"表达式求值失败: {expr} → {e}") from e
