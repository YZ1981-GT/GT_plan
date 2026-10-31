"""spec attachment-voucher-evidence-binding 测试共用（不是测试文件，不被收集）。"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

from app.services.voucher_identity import VoucherKey


def vk(no: str = "0003", *, date: str = "2025-01-07", vtype: str = "记", company: str = "default", year: str = "2025") -> str:
    """凭证键规范串。"""
    return VoucherKey.of(year=year, company_code=company, voucher_date=date, voucher_type=vtype, voucher_no=no).to_str()


@contextmanager
def visible_only(*wp_ids):
    """在被测函数的下一层（统一门的静默判定 ``try_gate_wp``）放行给定底稿、拒绝其余（SQLite 世界没有可见性表）。"""
    allowed = {str(w) for w in wp_ids}

    async def _gate(db, user, **kw):
        return object() if str(kw.get("wp_id")) in allowed else None

    with patch("app.services.wp_visibility.entry_integration.try_gate_wp", _gate):
        yield
