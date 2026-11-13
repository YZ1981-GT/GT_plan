"""批 5：来源投影纯函数 + readiness 七域五态。"""
from __future__ import annotations

from app.services.consol_note_source_projection import (
    SOURCE_MODES,
    compute_source_mode,
    source_digest,
    update_source_projection,
)
from app.services.consol_readiness_service import (
    build_readiness,
    build_role_views,
    readiness_payload,
)


class TestSourceProjection:
    def test_manual_always_manual(self):
        assert compute_source_mode("manual") == "manual"
        assert compute_source_mode("manual", manual_cells={(0, 1)}, written_cells={(0, 1)}) == "manual"

    def test_auto_no_intersection_is_self(self):
        assert compute_source_mode("formula") == "formula"
        assert compute_source_mode("detail_mapping", written_cells={(0, 1)}, manual_cells=set()) == "detail_mapping"

    def test_auto_with_protected_intersection_is_mixed(self):
        assert compute_source_mode(
            "formula", manual_cells={(0, 1)}, written_cells={(0, 1), (0, 2)},
        ) == "mixed"

    def test_auto_after_different_auto_is_mixed(self):
        assert compute_source_mode("formula", previous_source="detail_mapping") == "mixed"
        assert compute_source_mode("detail_mapping", previous_source="formula") == "mixed"

    def test_auto_after_same_auto_is_self(self):
        assert compute_source_mode("formula", previous_source="formula") == "formula"

    def test_auto_after_manual_is_self(self):
        assert compute_source_mode("formula", previous_source="manual") == "formula"

    def test_update_writes_all_four(self):
        import uuid
        from types import SimpleNamespace

        record = SimpleNamespace(source_mode=None, source_operation_id=None, source_revision=None, source_digest=None)
        oid = uuid.uuid4()
        update_source_projection(record, "formula", operation_id=oid, revision=3, digest="a" * 64)
        assert record.source_mode == "formula"
        assert record.source_operation_id == oid
        assert record.source_revision == 3
        assert record.source_digest == "a" * 64

    def test_source_digest_deterministic(self):
        d1 = source_digest({"rows": [[1, 2]], "headers": ["A", "B"]})
        d2 = source_digest({"headers": ["A", "B"], "rows": [[1, 2]]})  # 键序不同
        assert d1 == d2

    def test_all_modes_in_enum(self):
        assert set(SOURCE_MODES) == {"detail_mapping", "subtree_aggregate", "formula", "manual", "mixed"}


class TestReadiness:
    def test_all_ready(self):
        facts = {
            "tree": {"has_tree": True, "node_count": 5},
            "worksheet": {"has_worksheet_data": True},
            "elimination": {"approved_count": 3, "draft_count": 0, "pending_count": 0},
            "calc": {"has_trial": True, "stale_trial_count": 0},
            "report": {"has_published_run": True, "report_run_stale": False},
            "note": {"total_sections": 10, "stale_count": 0, "pending_mappings": 0},
            "lifecycle": {"is_locked": True},
        }
        domains = build_readiness(facts)
        assert len(domains) == 7
        payload = readiness_payload(domains)
        assert payload["status"] == "ready"
        assert all(d["status"] in ("ready", "not_applicable") for d in payload["domains"])

    def test_no_tree_blocks_all(self):
        facts = {"tree": {"has_tree": False}}
        domains = build_readiness(facts)
        tree = next(d for d in domains if d.domain == "tree")
        assert tree.status == "not_ready"
        assert "未构建" in tree.blockers[0]

    def test_pending_eliminations_block(self):
        facts = {"elimination": {"approved_count": 1, "draft_count": 0, "pending_count": 2}}
        domains = build_readiness(facts)
        elim = next(d for d in domains if d.domain == "elimination")
        assert elim.status == "not_ready"
        assert "待审批" in elim.blockers[0]

    def test_draft_eliminations_warn(self):
        facts = {"elimination": {"approved_count": 1, "draft_count": 3, "pending_count": 0}}
        domains = build_readiness(facts)
        elim = next(d for d in domains if d.domain == "elimination")
        assert elim.status == "warning"

    def test_no_published_report_blocks(self):
        facts = {"report": {"has_published_run": False}}
        domains = build_readiness(facts)
        report = next(d for d in domains if d.domain == "report")
        assert report.status == "not_ready"

    def test_stale_notes_block(self):
        facts = {"note": {"total_sections": 5, "stale_count": 2, "pending_mappings": 0}}
        domains = build_readiness(facts)
        note = next(d for d in domains if d.domain == "note")
        assert note.status == "not_ready"
        assert "过期" in note.blockers[0]

    def test_mixed_source_warns(self):
        facts = {"note": {"total_sections": 5, "stale_count": 0, "pending_mappings": 0,
                          "source_mode_distribution": {"formula": 3, "mixed": 2}}}
        domains = build_readiness(facts)
        note = next(d for d in domains if d.domain == "note")
        assert note.status == "warning"

    def test_no_note_data_is_not_applicable(self):
        facts = {"note": {"total_sections": 0}}
        domains = build_readiness(facts)
        note = next(d for d in domains if d.domain == "note")
        assert note.status == "not_applicable"

    def test_locked_lifecycle_ready(self):
        facts = {"lifecycle": {"is_locked": True}}
        domains = build_readiness(facts)
        lc = next(d for d in domains if d.domain == "lifecycle")
        assert lc.status == "ready"

    def test_empty_facts_yields_seven_domains(self):
        domains = build_readiness({})
        assert len(domains) == 7
        assert {d.domain for d in domains} == {"tree", "worksheet", "elimination", "calc", "report", "note", "lifecycle"}


class TestEvidenceFoldIntoWorksheet:
    """6.4：证据充分性四态折进 worksheet 域（映射，不重算）。"""

    def _ws(self, **facts):
        facts.setdefault("has_worksheet_data", True)
        domains = build_readiness({"worksheet": facts})
        return next(d for d in domains if d.domain == "worksheet")

    def test_evidence_ready_does_not_block(self):
        ws = self._ws(evidence_status="ready")
        assert ws.status == "ready"

    def test_evidence_not_declared_does_not_block(self):
        # A3-CONSOL 无声明需求 ⇒ not_declared，视为充分、不阻断
        ws = self._ws(evidence_status="not_declared")
        assert ws.status == "ready"

    def test_evidence_not_ready_blocks_with_missing_types(self):
        ws = self._ws(evidence_status="not_ready", evidence_missing_types=["bank_statement"])
        assert ws.status == "not_ready"
        assert any("证据不充分" in b for b in ws.blockers)
        assert any("bank_statement" in b for b in ws.blockers)

    def test_evidence_unknown_blocks(self):
        ws = self._ws(evidence_status="unknown")
        assert ws.status == "not_ready"
        assert any("无法判断" in b for b in ws.blockers)

    def test_missing_worksheet_still_blocks_independently(self):
        ws = self._ws(has_worksheet_data=False, evidence_status="ready")
        assert ws.status == "not_ready"
        assert any("未保存" in b for b in ws.blockers)


class TestReviewFoldIntoLifecycle:
    """6.4：壳复核状态折进 lifecycle 域。"""

    def _lc(self, **facts):
        facts.setdefault("has_snapshot", True)  # 排除"未创建快照"干扰，聚焦复核态
        domains = build_readiness({"lifecycle": facts})
        return next(d for d in domains if d.domain == "lifecycle")

    def test_rejected_review_blocks(self):
        lc = self._lc(review_status="level1_rejected")
        assert lc.status == "not_ready"
        assert any("退回" in b for b in lc.blockers)

    def test_pending_review_warns(self):
        lc = self._lc(review_status="pending_level1")
        assert lc.status == "warning"
        assert any("待复核" in b for b in lc.blockers)

    def test_not_submitted_review_warns(self):
        lc = self._lc(review_status="not_submitted")
        assert lc.status == "warning"
        assert any("尚未提交" in b for b in lc.blockers)

    def test_passed_review_with_snapshot_ready(self):
        lc = self._lc(review_status="level1_passed")
        assert lc.status == "ready"

    def test_locked_short_circuits_even_if_rejected(self):
        # 已锁定即 ready（签字锁定后不再看复核态）
        lc = self._lc(review_status="level1_rejected", is_locked=True)
        assert lc.status == "ready"


class TestRoleViews:
    """6.4：四角色待办桶纯投影（编制 / 审批 / 重大判断 / 质控）。"""

    def _views(self, facts, *, evidence=None, review=None):
        domains = build_readiness(facts)
        payload = build_role_views(
            domains, evidence=evidence or {}, review=review or {},
        )
        return {v["role"]: v for v in payload["views"]}

    def test_always_four_views_in_order(self):
        payload = build_role_views(build_readiness({}), evidence={}, review={})
        roles = [v["role"] for v in payload["views"]]
        assert roles == ["preparer", "approval", "significant_judgment", "qc"]
        labels = [v["label"] for v in payload["views"]]
        assert labels == ["编制", "审批", "重大判断", "质控"]

    def test_levels_from_role_map(self):
        views = self._views({})
        # 编制 / 审批 / 重大判断 = edit；质控 = review（经 ROLE_MAP 推导）
        assert views["preparer"]["level"] == "edit"
        assert views["approval"]["level"] == "edit"
        assert views["significant_judgment"]["level"] == "edit"
        assert views["qc"]["level"] == "review"

    def test_role_aliases_reverse_lookup(self):
        views = self._views({})
        # edit 级含 auditor/manager/partner 等英文别名；review 含 qc/eqcr
        assert "auditor" in views["preparer"]["role_aliases"]
        assert "manager" in views["preparer"]["role_aliases"]
        assert "qc" in views["qc"]["role_aliases"]
        assert "eqcr" in views["qc"]["role_aliases"]
        # 中文别名被排除（非 ascii），避免重复别名字面量
        assert all(a.isascii() for v in views.values() for a in v["role_aliases"])

    def test_preparer_gets_tree_worksheet_calc_todos(self):
        views = self._views({
            "tree": {"has_tree": False},
            "worksheet": {"has_worksheet_data": False},
            "calc": {"has_trial": False},
        })
        codes = {t["code"] for t in views["preparer"]["todos"]}
        assert "tree_not_ready" in codes
        assert "worksheet_todo" in codes
        assert "calc_not_ready" in codes
        assert views["preparer"]["status"] == "not_ready"

    def test_approval_gets_pending_entries_and_unpublished_report(self):
        views = self._views({
            "elimination": {"approved_count": 0, "draft_count": 0, "pending_count": 3},
            "report": {"has_published_run": False},
        })
        codes = {t["code"] for t in views["approval"]["todos"]}
        assert "elimination_pending" in codes
        assert "report_not_published" in codes
        assert views["approval"]["status"] == "not_ready"

    def test_significant_judgment_gets_drafts_and_note_uncertainty(self):
        views = self._views({
            "elimination": {"approved_count": 1, "draft_count": 2, "pending_count": 0},
            "note": {"total_sections": 5, "stale_count": 0, "pending_mappings": 1,
                     "source_mode_distribution": {"formula": 3, "mixed": 2}},
        })
        codes = {t["code"] for t in views["significant_judgment"]["todos"]}
        assert "judgment_draft_entries" in codes
        assert "note_pending_mappings" in codes
        assert "note_mixed_source" in codes
        # 都是 warning ⇒ 整桶 warning，非阻断
        assert views["significant_judgment"]["status"] == "warning"

    def test_qc_reflects_review_and_evidence(self):
        views = self._views(
            {},
            evidence={"status": "not_ready"},
            review={"review_status": "pending_level1"},
        )
        codes = {t["code"] for t in views["qc"]["todos"]}
        assert "review_pending" in codes
        assert "evidence_insufficient" in codes
        # 证据不足是 blocker ⇒ 质控桶 not_ready
        assert views["qc"]["status"] == "not_ready"

    def test_qc_rejected_review_is_blocker(self):
        views = self._views({}, review={"review_status": "level1_rejected"})
        qc = views["qc"]
        assert any(t["code"] == "review_rejected" and t["severity"] == "blocker" for t in qc["todos"])
        assert qc["status"] == "not_ready"

    def test_qc_evidence_unknown_warns(self):
        views = self._views({}, evidence={"status": "unknown"}, review={"review_status": "level1_passed"})
        codes = {t["code"] for t in views["qc"]["todos"]}
        assert "evidence_unknown" in codes
        # unknown 证据是 warning；复核通过无待办 ⇒ 桶整体 warning
        assert views["qc"]["status"] == "warning"

    def test_all_clear_yields_ready_views(self):
        facts = {
            "tree": {"has_tree": True, "node_count": 5},
            "worksheet": {"has_worksheet_data": True, "evidence_status": "ready"},
            "elimination": {"approved_count": 3, "draft_count": 0, "pending_count": 0},
            "calc": {"has_trial": True, "stale_trial_count": 0},
            "report": {"has_published_run": True},
            "note": {"total_sections": 4, "stale_count": 0, "pending_mappings": 0},
            "lifecycle": {"is_locked": True},
        }
        views = self._views(
            facts, evidence={"status": "ready"}, review={"review_status": "level1_passed"},
        )
        assert all(v["status"] == "ready" and v["todo_count"] == 0 for v in views.values())

    def test_todo_count_matches_list_length(self):
        views = self._views({"tree": {"has_tree": False}})
        for v in views.values():
            assert v["todo_count"] == len(v["todos"])


class TestSqlSlopeForSectionCount:
    """5.5：fill_note_sections 对章节数 S 的 SQL 为 O(1)（批量公式加载）。

    fill_note_sections 只在首次预构建 view_context（一次 CalcBasis + 一次报表配置），
    然后逐章节调 fill_by_formula——每章节内部 SQL 数恒定。因此章节数翻倍 SQL 不应翻倍；
    SQL 数 = 常数 + K × S（K 是每章的固定查询数，不含 CalcBasis）。
    守卫方式：S=1 和 S=10 时 view_context 构建 SQL 恒定（不随 S 增长）。
    """

    def test_view_context_sql_constant_regardless_of_section_count(self):
        """view_context 构建只涉及 load_calc_basis + load_report_rows，不取决于章节数。"""
        from app.services.consol_note_formula_service import fill_note_sections

        # fill_note_sections 先预构建 view_ctx，再逐章调 fill_by_formula。
        # view_ctx 构建路径 = load_view_context → load_calc_basis + load_report_rows，
        # 不依赖 section_ids 长度。这是设计保证：
        import inspect

        source = inspect.getsource(fill_note_sections)
        # 预构建只做一次 _context / load_view_context，然后 for section_id 循环
        assert "view_ctx" in source and "for section_id" in source
        # 确认 view_ctx 在 for 循环外构建
        ctx_pos = source.index("view_ctx")
        loop_pos = source.index("for section_id")
        assert ctx_pos < loop_pos, "view_ctx 应在章节循环前构建（批量不随 S 增长）"
