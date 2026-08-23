"""Integration test: snapshot_writer → orchestrator → event_bus (cross_ref/stale/SSE)

Validates: Requirements 1.3, 3.1, 3.2

验证 snapshot_writer 写回成功后：
- orchestrator.after_save 被调用
- 主 event_bus 收到 WORKPAPER_SAVED 事件（而非孤立总线）
- 触发下游 cross_ref/stale/SSE
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.custom_query.snapshot_writer import SnapshotWriter


def _make_snapshot_with_cell(sheet_name: str, row: int, col: int, value):
    return {
        "univer_snapshot": {
            "sheets": {
                "sheet1": {
                    "name": sheet_name,
                    "cellData": {
                        str(row): {str(col): {"v": value}},
                    },
                }
            }
        }
    }


def _make_mock_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = "integration_test_user"
    return user


def _make_mock_wp(wp_id: str, project_id: str, now):
    """orchestrator.after_save 需要的 WorkingPaper ORM 替身。"""
    wp = MagicMock()
    wp.id = uuid.UUID(wp_id)
    wp.project_id = uuid.UUID(project_id)
    wp.wp_code = "D2"
    wp.file_version = 1
    wp.updated_at = now
    wp.status = "draft"
    return wp


def _resolved_target(addr_id: str):
    """Step 4 的 addr_id 解析结果替身（解析本身有专属守卫，此处只固定为已解析）。"""
    from app.services.custom_query.addressing_service import ResolvedTarget

    return ResolvedTarget(raw=addr_id, found=True, addr_id=addr_id, entry_type="cell")


class TestSnapshotWriterOrchestratorIntegration:
    """集成测试：snapshot_writer → orchestrator → 主 event_bus"""

    @pytest.mark.asyncio
    async def test_writeback_triggers_main_event_bus(self):
        """snapshot_writer 写回后，通过 orchestrator 发布 WORKPAPER_SAVED 到主 event_bus"""
        sheet_name = "审定表"
        parsed_data = _make_snapshot_with_cell(sheet_name, 6, 1, 100.0)
        now = datetime.now(timezone.utc)
        wp_id = str(uuid.uuid4())
        project_id = str(uuid.uuid4())

        wp_obj = _make_mock_wp(wp_id, project_id, now)

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, "text") else str(stmt)
            if "SELECT" in stmt_str and "FOR UPDATE" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = (
                    now, parsed_data, "D2", "/path/to/file.xlsx", project_id
                )
                return mock_result
            if "UPDATE" in stmt_str:
                return MagicMock()
            # select(WorkingPaper) for ORM —— 必须返回实例，否则 orchestrator 整段被跳过，
            # 本测试就退化成「只验证 write_cell 不抛异常」，验不到它声称的事件发布。
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = wp_obj
            return mock_result

        mock_db = AsyncMock()
        mock_db.execute = mock_execute
        mock_db.flush = AsyncMock()
        # db.add 在 SQLAlchemy 里是同步方法；AsyncMock 会把它变成协程，产生
        # coroutine-never-awaited 警告，噪声会掩盖真问题。
        mock_db.add = MagicMock()

        events_published = []

        async def capture_publish(payload):
            events_published.append(payload)

        with patch("app.services.custom_query.snapshot_writer.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
            with (
                patch("app.services.event_bus.event_bus.publish", side_effect=capture_publish),
                # Step 4 的 addr_id 解析走 ACNR，需要真库；它有自己的专属守卫
                # （test_advanced_query_* 的回写身份用例），此处只关心 Step 8 的联动，
                # 故把解析结果固定为「已解析」。
                patch.object(
                    SnapshotWriter,
                    "_resolve_writeback_identity",
                    new=AsyncMock(return_value=_resolved_target("D2/审定表/B7")),
                ),
            ):
                writer = SnapshotWriter()
                result = await writer.write_cell(
                    db=mock_db,
                    user=_make_mock_user(),
                    wp_id=wp_id,
                    sheet_name=sheet_name,
                    cell_ref="B7",
                    new_value=200.0,
                    opened_at=now,
                )

        assert result["success"] is True
        assert result["addr_id"] == "D2/审定表/B7"
        # 联动没触发时必须暴露出来，不能静默（Step 8 的 fail-open 已改为记 ERROR + warnings）
        assert "warnings" not in result, f"下游联动未触发：{result.get('warnings')}"

        # 本测试的**真正断言**：事件发到了主 event_bus（而非孤立总线）
        assert events_published, (
            "write_cell 未向主 event_bus 发布事件 —— orchestrator.after_save 没被调到，"
            "下游 cross_ref / stale / SSE 都不会触发"
        )
        kinds = [
            getattr(p, "event_type", None) or getattr(p, "type", None) or str(p)
            for p in events_published
        ]
        assert any("WORKPAPER_SAVED" in str(k) or "workpaper_saved" in str(k) for k in kinds), (
            f"发布的事件里没有 WORKPAPER_SAVED：{kinds}"
        )

    @pytest.mark.asyncio
    async def test_downstream_failure_is_surfaced_not_silent(self):
        """orchestrator 挂掉时：数据仍写回，但必须在返回体里暴露「联动未触发」。

        原实现把整段 orchestrator（含 ORM select 返回 None）吞成一条 WARNING —— 接线
        错了也表现为「保存成功」，是最贵的一类 fail-open。
        """
        sheet_name = "审定表"
        parsed_data = _make_snapshot_with_cell(sheet_name, 6, 1, 100.0)
        now = datetime.now(timezone.utc)
        wp_id = str(uuid.uuid4())
        project_id = str(uuid.uuid4())

        async def mock_execute(stmt, params=None):
            stmt_str = str(stmt.text) if hasattr(stmt, "text") else str(stmt)
            if "SELECT" in stmt_str and "FOR UPDATE" in stmt_str:
                mock_result = MagicMock()
                mock_result.first.return_value = (
                    now, parsed_data, "D2", "/path/to/file.xlsx", project_id
                )
                return mock_result
            if "UPDATE" in stmt_str:
                return MagicMock()
            # ORM 取不到实例 → 联动无法进行
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            return mock_result

        mock_db = AsyncMock()
        mock_db.execute = mock_execute
        mock_db.flush = AsyncMock()
        # db.add 在 SQLAlchemy 里是同步方法；AsyncMock 会把它变成协程，产生
        # coroutine-never-awaited 警告，噪声会掩盖真问题。
        mock_db.add = MagicMock()

        with patch("app.services.custom_query.snapshot_writer.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
            with patch.object(
                SnapshotWriter,
                "_resolve_writeback_identity",
                new=AsyncMock(return_value=_resolved_target("D2/审定表/B7")),
            ):
                result = await SnapshotWriter().write_cell(
                    db=mock_db,
                    user=_make_mock_user(),
                    wp_id=wp_id,
                    sheet_name=sheet_name,
                    cell_ref="B7",
                    new_value=200.0,
                    opened_at=now,
                )

        assert result["success"] is True, "数据已写回，不应因联动失败而报失败"
        assert result.get("warnings"), "联动未触发却没有任何提示 —— 又回到静默 fail-open"
        # 文案要可行动：ORM 取不到实例是个明确的、可判定的前置条件，应显式识别并说清楚，
        # 而不是让 None 掉进外层 except、把 AttributeError 的字符串抛给用户。
        assert result["warnings"] == ["下游联动未触发：底稿 ORM 实例不可用"], (
            f"警告文案不是显式识别的那条（说明走的是异常兜底路径）：{result['warnings']}"
        )

    @pytest.mark.asyncio
    async def test_orphan_event_bus_no_longer_exists(self):
        """确认 custom_query.metrics 中不再有 _EventBus 类和 event_bus 实例"""
        from app.services.custom_query import metrics

        assert not hasattr(metrics, "_EventBus"), "_EventBus 类应已被删除"
        # event_bus 属性不应存在于模块中
        # (注意：如果有其他 event_bus import，检查它不是 _EventBus 实例)
        if hasattr(metrics, "event_bus"):
            # 如果存在，确保它不是 _EventBus 实例
            assert not hasattr(metrics.event_bus, "emit"), (
                "metrics.event_bus 仍是孤立 _EventBus 实例"
            )


class TestRouterSurfacesDownstreamWarnings:
    """router 必须把「联动未触发」透传给调用方。

    service 层加了 ``warnings`` 而 router 自己另组响应体把它丢掉 —— 那就是
    additive 注入即死代码：日志里有、API 里没有，用户照样只看到 success。
    """

    @staticmethod
    def _fake_db(project_id: str, wp_id: str):
        class _Result:
            def __init__(self, row=None, scalar=None):
                self._row = row
                self._scalar = scalar

            def first(self):
                return self._row

            def scalar_one_or_none(self):
                return self._scalar

        class _Db:
            def __init__(self):
                self.committed = False

            async def execute(self, stmt, params=None):
                stmt_str = str(getattr(stmt, "text", stmt))
                if "working_paper" in stmt_str:
                    return _Result(row=(uuid.UUID(wp_id),))
                return _Result(scalar=None)

            async def commit(self):
                self.committed = True

            async def rollback(self):
                pass

        return _Db()

    @pytest.mark.asyncio
    async def test_warnings_reach_response(self, monkeypatch):
        from app.routers import custom_query as router_mod

        project_id = str(uuid.uuid4())
        wp_id = str(uuid.uuid4())
        user = MagicMock()
        user.id = uuid.uuid4()
        user.role = MagicMock()
        user.role.value = "admin"

        async def _visible(_user, _db):
            return {uuid.UUID(project_id)}

        monkeypatch.setattr(router_mod, "get_visible_project_ids", _visible)

        from app.services.custom_query import snapshot_writer as sw_mod

        async def _write_cell(**kwargs):
            return {
                "success": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "old_value": 1,
                "addr_id": "D2/审定表/B7",
                "column_metadata": {},
                "audit_logged": True,
                "warnings": ["下游联动未触发：底稿 ORM 实例不可用"],
            }

        monkeypatch.setattr(sw_mod.snapshot_writer, "write_cell", _write_cell)

        body = router_mod.CellWritebackRequest(
            project_id=project_id,
            wp_code="D2",
            sheet_name="审定表",
            cell_ref="B7",
            new_value=200.0,
            module="workpaper",
        )
        request = MagicMock()
        request.headers = {"X-File-Opened-At": datetime.now(timezone.utc).isoformat()}

        out = await router_mod.cell_writeback(
            body=body,
            response=MagicMock(),
            request=request,
            db=self._fake_db(project_id, wp_id),
            current_user=user,
        )

        assert out["success"] is True
        assert out.get("warnings") == ["下游联动未触发：底稿 ORM 实例不可用"], (
            "router 把 service 的 warnings 丢了 —— 联动失效对调用方依然不可见"
        )

    @pytest.mark.asyncio
    async def test_no_warnings_key_when_all_good(self, monkeypatch):
        """反向：一切正常时响应里不该出现 warnings 键（否则前端会常显警告）。"""
        from app.routers import custom_query as router_mod
        from app.services.custom_query import snapshot_writer as sw_mod

        project_id = str(uuid.uuid4())
        wp_id = str(uuid.uuid4())
        user = MagicMock()
        user.id = uuid.uuid4()
        user.role = MagicMock()
        user.role.value = "admin"

        async def _visible(_user, _db):
            return {uuid.UUID(project_id)}

        monkeypatch.setattr(router_mod, "get_visible_project_ids", _visible)

        async def _write_cell(**kwargs):
            return {
                "success": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "old_value": 1,
                "addr_id": "D2/审定表/B7",
                "column_metadata": {},
                "audit_logged": True,
            }

        monkeypatch.setattr(sw_mod.snapshot_writer, "write_cell", _write_cell)

        body = router_mod.CellWritebackRequest(
            project_id=project_id,
            wp_code="D2",
            sheet_name="审定表",
            cell_ref="B7",
            new_value=200.0,
            module="workpaper",
        )
        request = MagicMock()
        request.headers = {"X-File-Opened-At": datetime.now(timezone.utc).isoformat()}

        out = await router_mod.cell_writeback(
            body=body,
            response=MagicMock(),
            request=request,
            db=self._fake_db(project_id, wp_id),
            current_user=user,
        )
        assert "warnings" not in out
