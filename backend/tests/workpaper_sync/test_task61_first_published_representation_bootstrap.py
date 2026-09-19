# -*- coding: utf-8 -*-
"""Task 61 首版 published representation 引导器的守卫。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 5 Task 61
**Validates: Requirements 2.2, 2.3, 2.11, 3.1, 6.19, 12.6**

三类判据，刻意分开：

1. **夹具门是真门** —— `fixture_violations` 是纯函数，喂**合成的真实客户项目行**逐条
   证明拒绝分支会走到。只在真夹具数据上断言等于等价变异（本 spec 的 M15 教训）。
2. **写入面没有旁路** —— AST 断言脚本自己不写业务行（无 `UPDATE working_paper`）、
   没有任何 `--force` 类绕过开关、且 `assert_fixture_only` 真的被目标解析调用
   （删掉那行调用必须打红，不能只查符号存在）。
3. **实证台账不是空壳** —— apply 报告里 14 条判据全 True、越权行清单为空、
   三张 sync 域表各 +1、receipt 单事务单 commit。
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = (
    _REPO
    / "backend/scripts/fix/fix_task61_bootstrap_first_published_representation.py"
)
_EVIDENCE = (
    _REPO
    / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure"
    / "evidence/task61-oo94-word-pilot-gate"
    / "first_published_representation_bootstrap.json"
)

def _module():
    import importlib.util
    import sys

    backend = _REPO / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    spec = importlib.util.spec_from_file_location("_task61_bootstrap", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # dataclasses._is_type 会去 sys.modules 查 cls.__module__ —— 动态加载不先登记
    # 就会在 @dataclass 那行抛 AttributeError: NoneType has no attribute __dict__。
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _module()


@pytest.fixture(scope="module")
def source() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tree(source: str) -> ast.Module:
    return ast.parse(source)


@pytest.fixture(scope="module")
def evidence() -> dict:
    assert _EVIDENCE.is_file(), f"apply 台账缺失: {_EVIDENCE}"
    return json.loads(_EVIDENCE.read_text(encoding="utf-8"))


def _fixture_row(**overrides) -> dict:
    row = {
        "client_name": "测试客户",
        "project_status": "created",
        "project_workpaper_count": 1,
        "content_revision": 0,
    }
    row.update(overrides)
    return row

class TestFixtureGateIsARealGate:
    """夹具门必须对**合成的**非夹具行逐条拒绝。"""

    def test_a_real_fixture_row_passes(self, mod):
        assert mod.fixture_violations(_fixture_row()) == ()
        mod.assert_fixture_only(_fixture_row())

    @pytest.mark.parametrize(
        "overrides,expected",
        [
            ({"client_name": "重庆和平药房连锁有限责任公司"}, "client_name_is_fixture"),
            ({"client_name": ""}, "client_name_is_fixture"),
            ({"project_status": "execution"}, "project_status_is_created"),
            ({"project_status": "planning"}, "project_status_is_created"),
            ({"project_workpaper_count": 1025}, "project_workpaper_count_within_cap"),
            ({"project_workpaper_count": 0}, "project_workpaper_count_within_cap"),
            ({"project_workpaper_count": None}, "project_workpaper_count_within_cap"),
            ({"content_revision": 1}, "target_revision_is_zero"),
            ({"content_revision": 7}, "target_revision_is_zero"),
        ],
    )
    def test_each_criterion_rejects_its_counterexample(self, mod, overrides, expected):
        violations = mod.fixture_violations(_fixture_row(**overrides))
        assert expected in violations, (overrides, violations)
        with pytest.raises(mod.FixtureGuardError):
            mod.assert_fixture_only(_fixture_row(**overrides))
    def test_a_real_client_project_row_is_rejected_on_three_counts(self, mod):
        row = _fixture_row(
            client_name="重庆医药集团宜宾医药有限公司新健康大药房临港店",
            project_status="execution",
            project_workpaper_count=1025,
        )
        assert set(mod.fixture_violations(row)) == {
            "client_name_is_fixture",
            "project_status_is_created",
            "project_workpaper_count_within_cap",
        }

    def test_criteria_vocabulary_matches_what_the_function_can_emit(self, mod):
        emitted = set()
        for overrides in (
            {"client_name": "x"},
            {"project_status": "x"},
            {"project_workpaper_count": 999},
            {"content_revision": 3},
        ):
            emitted |= set(mod.fixture_violations(_fixture_row(**overrides)))
        assert emitted == set(mod.FIXTURE_CRITERIA)

class TestNoBypassAndNoBusinessRowWrites:
    """写入面判据：门被真调用、无绕过开关、脚本自己不写业务行。"""

    def test_target_resolution_actually_calls_the_gate(self, tree):
        target = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "resolve_fixture_target"
        )
        called = {
            n.func.id
            for n in ast.walk(target)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "assert_fixture_only" in called, (
            "resolve_fixture_target 必须真调 assert_fixture_only —— "
            "只 import 不调用等于门不存在"
        )

    def test_no_force_style_bypass_flag_exists(self, source, tree):
        added = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "add_argument"
        ]
        flags = [
            a.value
            for call in added
            for a in call.args
            if isinstance(a, ast.Constant) and isinstance(a.value, str)
        ]
        bad = [f for f in flags if "force" in f.lower() or "skip" in f.lower()]
        assert bad == [], f"夹具门不得有绕过开关，实得 {bad}"
        # 刻意不写 assert '--force' not in source：那是子串判据，会被脚本文档里
        # 「没有 --force 开关」这句说明文字打成假红。上面的 AST 判据才是本体。
        assert flags, "argparse 至少要注册 --check/--apply 两个开关"
    def test_script_never_writes_business_rows_itself(self, source):
        lowered = source.lower()
        for forbidden in ("update working_paper", "insert into working_paper", "delete from"):
            assert forbidden not in lowered, (
                f"脚本自己出现 {forbidden!r} —— 业务行只能由 "
                "ContentMutationService.commit 的 CAS 推进"
            )

    def test_it_goes_through_the_production_writer_not_a_hand_rolled_plan(self, source):
        assert "build_content_mutation_service_writer" in source
        assert "commit_bytes" in source
        assert "ContentCommitPlan(" not in source, (
            "不得自己装配 ContentCommitPlan —— 那会绕开 lane 登记决定 authority model 这条约束"
        )

    def test_lane_id_is_a_registered_lane_with_an_opaque_authority_model(self, mod):
        from app.services.workpaper_sync.models import AuthorityModel
        from app.services.workpaper_sync.opaque_entry_gate import lane_ids

        assert mod.LANE_ID in lane_ids()
        facts = mod.lane_facts()
        assert facts["authority_model"] != AuthorityModel.projection_contract.value
        assert facts["entry_id_source"] == "wp_id"

class TestVerdictFunctionCanFail:
    """结算函数必须能对合成的越界快照打红（注入口，不只在真数据上跑）。"""

    @staticmethod
    def _snap(counts: dict, touched: list) -> dict:
        return {"counts": counts, "business_rows_touched": touched}

    def _base(self, mod):
        before = {t: 0 for t in mod.SYNC_DOMAIN_TABLES + mod.UNTOUCHED_TABLES}
        after = dict(before)
        for t in ("working_paper_sync_entry_state", "working_paper_content_version",
                  "working_paper_content_representation", "working_paper_artifact"):
            after[t] = 1
        return before, after

    def _target(self, mod):
        import uuid as _u

        return mod.FixtureTarget(
            project_id=_u.UUID(int=1),
            wp_id=_u.UUID(int=2),
            wp_code="D2",
            project_name="proj_fixture",
            client_name=mod.FIXTURE_CLIENT_NAME,
            project_status=mod.FIXTURE_PROJECT_STATUS,
            project_workpaper_count=1,
            content_revision=0,
        )

    def _receipt(self):
        return {
            "revision": 1,
            "representation_generation": 1,
            "commit_count": 1,
            "transaction_ids": ["1"],
        }
    def _row(self, mod, target, **over):
        row = {
            "wp_id": str(target.wp_id),
            "client_name": mod.FIXTURE_CLIENT_NAME,
            "content_revision": 1,
            "has_current_content_version": True,
            "is_fixture_client": True,
        }
        row.update(over)
        return row

    def test_a_clean_run_passes_every_check(self, mod):
        before, after = self._base(mod)
        target = self._target(mod)
        v = mod.extend_verdict(
            mod.verdict_of(
                self._snap(before, []),
                self._snap(after, [self._row(mod, target)]),
                target,
                self._receipt(),
            ),
            self._receipt(),
        )
        assert v["failed"] == [], v

    def test_a_real_client_row_being_touched_fails_the_run(self, mod):
        before, after = self._base(mod)
        target = self._target(mod)
        intruder = self._row(
            mod, target, wp_id="deadbeef", client_name="重庆和平药房连锁有限责任公司",
            is_fixture_client=False,
        )
        v = mod.extend_verdict(
            mod.verdict_of(
                self._snap(before, []),
                self._snap(after, [self._row(mod, target), intruder]),
                target,
                self._receipt(),
            ),
            self._receipt(),
        )
        assert "only_fixture_business_row_touched" in v["failed"]
        assert v["non_fixture_business_rows"] == [intruder]
    def test_touching_an_untouched_table_fails_the_run(self, mod):
        before, after = self._base(mod)
        target = self._target(mod)
        after = dict(after)
        after["working_paper_oo_room"] = 1
        v = mod.extend_verdict(
            mod.verdict_of(
                self._snap(before, []),
                self._snap(after, [self._row(mod, target)]),
                target,
                self._receipt(),
            ),
            self._receipt(),
        )
        assert "no_untouched_table_moved" in v["failed"]
    def test_two_transactions_or_two_commits_fail_the_run(self, mod):
        before, after = self._base(mod)
        target = self._target(mod)
        bad = {
            "revision": 1,
            "representation_generation": 1,
            "commit_count": 2,
            "transaction_ids": ["1", "2"],
        }
        v = mod.extend_verdict(
            mod.verdict_of(
                self._snap(before, []),
                self._snap(after, [self._row(mod, target)]),
                target,
                bad,
            ),
            bad,
        )
        assert "receipt_commit_count_is_one" in v["failed"]
        assert "receipt_single_transaction" in v["failed"]
    def test_no_representation_created_fails_the_run(self, mod):
        before, _ = self._base(mod)
        target = self._target(mod)
        v = mod.extend_verdict(
            mod.verdict_of(
                self._snap(before, []),
                self._snap(dict(before), []),
                target,
                self._receipt(),
            ),
            self._receipt(),
        )
        assert "representation_supply_now_nonzero" in v["failed"]
        assert "representation_created" in v["failed"]

class TestEvidenceLedgerIsRealAndComplete:
    """apply 台账不是空壳：14 条判据全 True，写入面恰好是登记的那些。"""

    def test_every_check_passed_and_nothing_failed(self, evidence):
        checks = evidence["verification"]["checks"]
        assert evidence["verification"]["failed"] == []
        assert evidence["errors"] == []
        assert len(checks) == 14, sorted(checks)
        assert all(checks.values()), [k for k, v in checks.items() if not v]

    def test_no_real_client_row_was_touched(self, evidence):
        assert evidence["verification"]["non_fixture_business_rows"] == []
        touched = evidence["after"]["business_rows_touched"]
        assert len(touched) == 1
        assert touched[0]["is_fixture_client"] is True
        assert touched[0]["content_revision"] == 1
    def test_the_three_supply_tables_went_from_zero_to_one(self, evidence):
        before = evidence["before"]["counts"]
        after = evidence["after"]["counts"]
        for table in (
            "working_paper_sync_entry_state",
            "working_paper_content_version",
            "working_paper_content_representation",
        ):
            assert before[table] == 0, table
            assert after[table] == 1, table

    def test_the_receipt_is_a_first_generation_opaque_commit(self, evidence):
        receipt = evidence["receipt"]
        assert receipt["revision"] == 1
        assert receipt["representation_generation"] == 1
        assert receipt["commit_count"] == 1
        assert len(set(receipt["transaction_ids"])) == 1
        assert receipt["projection_sha256"] is None
        assert receipt["authority_model"] == "opaque_single_onlyoffice"
        assert receipt["replayed"] is False
    def test_the_bytes_came_from_the_frozen_authoritative_template(self, evidence):
        template = evidence["template"]
        assert template["authority_root"] == "backend/wp_templates"
        assert template["payload_bytes"] > 0
        assert evidence["receipt"]["artifact_sha256"] == template["template_sha256"], (
            "published representation 的 digest 必须等于契约冻结的模板 digest —— "
            "不等即字节在途被改写（custom/opaque 不得被 JSON writer 改写）"
        )

    def test_the_lane_recorded_matches_the_registry_today(self, evidence, mod):
        assert evidence["lane"]["lane_id"] == mod.LANE_ID
        assert evidence["lane"] == mod.lane_facts()

    def test_the_entry_id_is_the_opaque_scope_form(self, evidence):
        from app.services.workpaper_sync.writer_migration import OPAQUE_ENTRY_PREFIX

        assert evidence["entry_id"].startswith(OPAQUE_ENTRY_PREFIX)
        assert evidence["entry_id"].endswith(evidence["target"]["wp_id"])
    def test_a_lane_with_a_different_entry_id_scheme_is_rejected(self, mod):
        """M11 补洞：断言「值等于 wp_id」测不出校验被删 —— 这条喂一条真实登记的
        **另一种口径** lane，只有那道校验真在才会抛。"""
        from app.services.workpaper_sync.opaque_entry_gate import (
            EntryIdSource,
            lane_for,
        )

        other = next(
            lane_id
            for lane_id in ("custom_cells", "f2_stocktake_plan", "f2_stocktake_summary")
            if lane_for(lane_id).entry_id_source is not EntryIdSource.wp_id
        )
        with pytest.raises(mod.BootstrapScriptError):
            mod.lane_facts(other)

    def test_a_projection_lane_is_rejected(self, mod, monkeypatch):
        """projection_contract 必须走 adapter 全量协议，不得用 opaque 装配跳过。"""
        from app.services.workpaper_sync import opaque_entry_gate as gate
        from app.services.workpaper_sync.models import AuthorityModel

        monkeypatch.setattr(
            gate, "authority_model_for_lane",
            lambda lane_id: AuthorityModel.projection_contract,
        )
        with pytest.raises(mod.BootstrapScriptError):
            mod.lane_facts(mod.LANE_ID)