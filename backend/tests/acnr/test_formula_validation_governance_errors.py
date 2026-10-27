"""T10：`validate_refs_via_acnr` 的 fail-open 不吞治理错误（design §6.5）。

- `full_resolve` 抛 `VersionNotFoundError`（锁定快照缺失）或 `CatalogIntegrityError`（目录完整性失败）→ 原样上抛，
  不回退 legacy 校验（否则锁定项目会被按当前目录静默放行）；
- 其他异常（resolver 暂不可用）→ 仍回退 legacy `validate_formula_refs`，结果即 legacy 的结果。
故障注在被测函数的下一层（`resolver.full_resolve`），被测的 `validate_refs_via_acnr` 是生产函数本身。
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.acnr import formula_validation, resolver
from app.services.acnr.catalog import CatalogIntegrityError
from app.services.acnr.resolver import VersionNotFoundError

_EXPR = "=WP('D2','D2-2','E100')"
_LEGACY = [{"ref": "legacy", "status": "not_found"}]


def _run(exc: BaseException):
    legacy = AsyncMock(return_value=_LEGACY)
    with patch.object(resolver, "full_resolve", AsyncMock(side_effect=exc)), \
            patch.object(formula_validation.address_registry, "validate_formula_refs", legacy):
        try:
            return asyncio.run(formula_validation.validate_refs_via_acnr(None, "p", 2025, _EXPR)), legacy
        except BaseException as e:  # noqa: BLE001
            return e, legacy


@pytest.mark.parametrize("exc", [VersionNotFoundError("20260101000000 快照缺失"),
                                 CatalogIntegrityError("release 段 catalog_sha256 不符")])
def test_governance_errors_propagate(exc):
    got, legacy = _run(exc)
    assert got is exc
    legacy.assert_not_awaited()


def test_other_errors_fall_back_to_legacy():
    got, legacy = _run(RuntimeError("resolver 暂不可用"))
    assert got == _LEGACY
    legacy.assert_awaited_once()
