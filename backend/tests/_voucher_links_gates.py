"""挂凭端点测试共用：把底稿级读写门换成放行（SQLite 世界没有委派与可见性数据）。

门本身的接线（动作、拒绝时的错误码、不回编码）由 ``test_voucher_links_ownership.py`` 单独验证。
"""

from __future__ import annotations


def allow_wp_gates(monkeypatch) -> None:
    from app.routers import voucher_links

    async def _yes(_db, _user, _wp_id):
        return True

    async def _all(_db, _user, wp_ids):
        return set(wp_ids)

    monkeypatch.setattr(voucher_links, "_wp_writable", _yes)
    monkeypatch.setattr(voucher_links, "_wp_readable", _yes)
    monkeypatch.setattr(voucher_links, "_visible_wp_ids", _all)
