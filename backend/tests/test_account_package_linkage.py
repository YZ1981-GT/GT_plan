"""科目工作包聚合 — 底稿间联动测试

spec workpaper-account-multifile-aggregation 需求 4：
- 聚合审定表 sheet 名能提取审定表子码（[D-N]\\d+-1），供回写 handler 匹配
- 聚合审定表保存 → 计算审定数 → 发布 WORKPAPER_SAVED(wp_code=子码) 触发 TB 回写
- 审定数公式与前端一致：current_unadjusted + (adj??sys_aje??0) + (reclass??sys_rje??0)

Requirements: 4.1, 4.4
"""

from __future__ import annotations

import re

import pytest

from app.services.wp_account_package_resolver import extract_determination_wp_code


# ─── 审定表子码提取（联动回写匹配的关键）────────────────────────────────


class TestExtractDeterminationWpCode:
    _PATTERN = re.compile(r"^[D-N]\d+-1$")

    def test_d2_audit_sheet_name(self):
        """'审定表D2-1' → 'D2-1'（聚合场景 handler 匹配）。"""
        assert extract_determination_wp_code("审定表D2-1") == "D2-1"

    def test_d1_audit_sheet_name(self):
        assert extract_determination_wp_code("审定表D1-1") == "D1-1"

    def test_extracted_code_matches_handler_regex(self):
        """提取的子码必须匹配 _on_d_audit_determination_saved 的 ^[D-N]\\d+-1$。"""
        for name in ("审定表D2-1", "审定表D1-1", "K8-1 审定表", "应收账款审定表D2-1"):
            code = extract_determination_wp_code(name)
            assert code is not None
            assert self._PATTERN.match(code), f"{name}→{code} 不匹配 handler 正则"

    def test_non_determination_sheet_returns_none(self):
        """非审定表 sheet（明细表/分析表/检查表）→ None，不触发回写。"""
        assert extract_determination_wp_code("应收账款明细表D2-2") is None
        assert extract_determination_wp_code("应收账款分析表D2-5") is None
        assert extract_determination_wp_code("D2A 应收账款实质性程序表") is None
        assert extract_determination_wp_code("应收账款附注披露信息") is None

    def test_none_or_empty(self):
        assert extract_determination_wp_code(None) is None
        assert extract_determination_wp_code("") is None


# ─── 聚合审定表保存 → TB 回写联动（计算 + 事件发布）────────────────────


class TestDeterminationWritebackPublish:
    @pytest.mark.asyncio
    async def test_publishes_workpaper_saved_with_computed_audited(self, monkeypatch):
        """聚合审定表 sheet 保存 → 计算审定数 → 发布 WORKPAPER_SAVED(子码 + rows)。"""
        from app.routers import wp_html_save

        published = []

        class _StubBus:
            async def publish(self, payload):
                published.append(payload)

        # stub TB 取数（返回每行的 current_unadjusted/sys_aje/sys_rje）
        async def _stub_fetch(audit_rows, *, db, project_id):
            return {
                "row-1": {"current_unadjusted": 100000.0, "sys_aje": 5000.0, "sys_rje": None},
            }

        monkeypatch.setattr(
            "app.services.wp_audit_sheet_tb_service.fetch_audit_sheet_tb_values",
            _stub_fetch,
        )
        monkeypatch.setattr("app.services.event_bus.event_bus", _StubBus())

        # stub 年度查询
        class _StubResult:
            def first(self):
                return (2025,)

        class _StubDB:
            async def execute(self, *a, **k):
                return _StubResult()

        from uuid import uuid4
        pid = uuid4()
        html_data = {
            "audit_rows": [
                {"id": "row-1", "item": "应收账款", "account_code": "1122",
                 "adj_amount": None, "reclass_amount": None},
            ]
        }

        await wp_html_save._maybe_publish_determination_writeback(
            db=_StubDB(), project_id=pid, sheet_name="审定表D2-1", html_data=html_data,
        )

        assert len(published) == 1
        payload = published[0]
        assert payload.extra["wp_code"] == "D2-1"
        rows = payload.extra["parsed_data"]["rows"]
        assert len(rows) == 1
        assert rows[0]["account_code"] == "1122"
        # 100000 + 5000(sys_aje 回退) + 0 = 105000
        assert rows[0]["audited_amount"] == 105000.0

    @pytest.mark.asyncio
    async def test_non_determination_sheet_no_publish(self, monkeypatch):
        """非审定表 sheet 保存 → 不发布事件。"""
        from app.routers import wp_html_save
        from uuid import uuid4

        published = []

        class _StubBus:
            async def publish(self, payload):
                published.append(payload)

        monkeypatch.setattr("app.services.event_bus.event_bus", _StubBus())

        await wp_html_save._maybe_publish_determination_writeback(
            db=None, project_id=uuid4(),
            sheet_name="应收账款明细表D2-2",
            html_data={"audit_rows": [{"id": "row-1", "account_code": "1122"}]},
        )
        assert len(published) == 0

    @pytest.mark.asyncio
    async def test_no_audit_rows_no_publish(self, monkeypatch):
        """审定表 sheet 但无 audit_rows → 不发布。"""
        from app.routers import wp_html_save
        from uuid import uuid4

        published = []

        class _StubBus:
            async def publish(self, payload):
                published.append(payload)

        monkeypatch.setattr("app.services.event_bus.event_bus", _StubBus())

        await wp_html_save._maybe_publish_determination_writeback(
            db=None, project_id=uuid4(),
            sheet_name="审定表D2-1", html_data={"cells": {}},
        )
        assert len(published) == 0

    @pytest.mark.asyncio
    async def test_user_override_adj_takes_precedence(self, monkeypatch):
        """用户填写 adj_amount 覆盖 sys_aje 回退。"""
        from app.routers import wp_html_save
        from uuid import uuid4

        published = []

        class _StubBus:
            async def publish(self, payload):
                published.append(payload)

        async def _stub_fetch(audit_rows, *, db, project_id):
            return {"row-1": {"current_unadjusted": 100000.0, "sys_aje": 5000.0, "sys_rje": 2000.0}}

        monkeypatch.setattr(
            "app.services.wp_audit_sheet_tb_service.fetch_audit_sheet_tb_values", _stub_fetch)
        monkeypatch.setattr("app.services.event_bus.event_bus", _StubBus())

        class _StubResult:
            def first(self):
                return (2025,)

        class _StubDB:
            async def execute(self, *a, **k):
                return _StubResult()

        html_data = {
            "audit_rows": [
                {"id": "row-1", "account_code": "1122",
                 "adj_amount": 8000, "reclass_amount": 0},
            ]
        }
        await wp_html_save._maybe_publish_determination_writeback(
            db=_StubDB(), project_id=uuid4(), sheet_name="审定表D2-1", html_data=html_data)

        # 100000 + 8000(用户覆盖) + 0(用户显式 0 覆盖 sys_rje) = 108000
        assert published[0].extra["parsed_data"]["rows"][0]["audited_amount"] == 108000.0
