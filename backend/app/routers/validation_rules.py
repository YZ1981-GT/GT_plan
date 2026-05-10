"""F48 / Sprint 8.8: 校验规则说明文档 API。

端点：

- ``GET /api/ledger-import/validation-rules``       — 返回全量规则目录
- ``GET /api/ledger-import/validation-rules/{code}`` — 返回单条规则；404 未命中

规则目录的单一真源见 ``app.services.ledger_import.validation_rules_catalog``。

权限：只要登录用户即可访问（供所有审计助理学习校验规则），不绑定具体项目。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_current_user
from app.models.core import User
from app.services.ledger_import.validation_rules_catalog import (
    VALIDATION_RULES_CATALOG,
    ValidationRuleDoc,
    get_rule_by_code,
)

router = APIRouter(
    prefix="/api/ledger-import/validation-rules",
    tags=["ledger-import-validation-rules"],
)


@router.get("", response_model=list[ValidationRuleDoc])
async def list_validation_rules(
    _current_user: User = Depends(get_current_user),
) -> list[ValidationRuleDoc]:
    """返回全量校验规则目录（F48）。

    前端 ``/ledger-import/validation-rules`` 页面调用此接口按 level
    (L1 / L2 / L3) 分组展示。
    """

    return list(VALIDATION_RULES_CATALOG)


@router.get("/{code}", response_model=ValidationRuleDoc)
async def get_validation_rule(
    code: str,
    _current_user: User = Depends(get_current_user),
) -> ValidationRuleDoc:
    """按 ``code`` 查询单条规则（F48）。

    未命中返回 404；前端从 ``ValidationFinding.code`` 直接跳转到规则详情页时使用。
    """

    rule = get_rule_by_code(code)
    if rule is None:
        raise HTTPException(
            status_code=404,
            detail=f"未登记的校验规则 code={code!r}",
        )
    return rule
