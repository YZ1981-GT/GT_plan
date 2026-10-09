"""V165 守卫：`authorization_reject` kind 让「零 application」场景可记 passed。
spec: workpaper-html-onlyoffice-bidirectional-writeback-closure
Requirements: 5.6, 12.10
Properties: P49（未真跑不得判绿）/ P70（证据不可跨场景复用）

═══ 这个文件锁什么 ═══

V165 之前 `quarantined_rejects_application_and_engine` 被 V151 的
`ck_wpees_standard_requires_entities` 与 AC 5.6 夹死（前者要求 passed 行
`application_ids>=1`，后者规定它永不创建 application）⇒ 该场景恒 UNVERIFIABLE、其 entry
永不 verified，登记在 `SCHEMA_UNREPRESENTABLE_SCENARIOS` 归因给任务 9。

V165 按该欠账自己开的方子修复：新增 `authorization_reject` kind。本文件锁三件事：

1. **三层一致**（铁律）：Python `ScenarioKind` 取值域 ↔ V165 迁移 SQL 的
   `ck_wpees_scenario_kind` 逐值对齐。第一版 `ScenarioKind` 写语义分类导致真库
   `CheckViolationError` 而离线全绿 —— 那次教训的机器形态就是本条。
2. **豁免必须配套零约束**：只把新 kind 加进 `ck_wpees_standard_requires_entities` 的豁免
   名单，等于允许「声明永不创建 application 的场景」带着伪造实体记 passed。因此 V165
   必须同时有 `ck_wpees_authorization_reject_zero_entities`，本文件逐条断言。
3. **反向锁**：`SCHEMA_UNREPRESENTABLE_SCENARIOS` 现在为空，但机制不得删 —— 谁将来新增
   「零 application 却落进 standard/recovery_claim/close_capture」的组合，必须在那张表里
   登记归因，而不是等真库插入时才炸。

🔴 本文件是**纯判据**测试（不连库）。「V165 的 CHECK 真的被真库接受、且真的拦住违规行」
由 `test_v165_authorization_reject_pg.py` 在真实 PostgreSQL 上另证 —— 两者缺一不可：
纯判据可能是死代码，真库测又不覆盖声明侧的推导。
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest

from app.services.workpaper_sync.evidence import (
    SCHEMA_UNREPRESENTABLE_SCENARIOS,
    ScenarioKind,
)
from app.services.workpaper_sync.pilot_harness import (
    HarnessRejected,
    ScenarioObservation,
    all_declared_scenarios,
    assert_entity_shape,
)

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "V165__wpees_authorization_reject_kind.sql"
)

#: V165 之前这 5 条声明了 `expects_application=False`。只有 quarantined 那条既无 recovery
#: case 也非三实体全零，因此只有它改 kind —— 其余 4 条是**回归锁**。
_ZERO_APPLICATION_EXPECTED_KINDS = {
    "quarantined_rejects_application_and_engine": ScenarioKind.authorization_reject,
    "browser_crash_no_userdata_recovery_case": ScenarioKind.recovery_reject,
    "wrong_prior_confirmation_bundle_fence_contributor_rejected": ScenarioKind.recovery_reject,
    "download_only_zero_three_entities": ScenarioKind.download_only,
    "single_html_no_blank_oo_artifact": ScenarioKind.download_only,
}


@pytest.fixture(scope="module")
def migration_sql() -> str:
    assert _MIGRATION.exists(), f"缺少 V165 迁移：{_MIGRATION}"
    return _MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def declared() -> dict[str, object]:
    return {s.scenario_id: s for s in all_declared_scenarios()}


class TestThreeLayerConsistency:
    """Python 枚举 ↔ 迁移 SQL 取值域，一个不多一个不少。"""

    def test_scenario_kind_domain_matches_v165_migration(self, migration_sql: str) -> None:
        block = re.search(
            r"ADD CONSTRAINT ck_wpees_scenario_kind CHECK \(scenario_kind IN \((.*?)\)\)",
            migration_sql,
            re.S,
        )
        assert block, "V165 里找不到 ck_wpees_scenario_kind 的 ADD CONSTRAINT —— 解析失效"
        sql_values = set(re.findall(r"'([a-z_]+)'", block.group(1)))
        python_values = {k.value for k in ScenarioKind}
        assert sql_values == python_values, (
            f"取值域漂移：SQL={sorted(sql_values)} vs Python={sorted(python_values)}。"
            "V151 首版就是这里漂移导致离线全绿、真库 CheckViolationError"
        )

    def test_authorization_reject_is_in_both_sides(self, migration_sql: str) -> None:
        assert ScenarioKind.authorization_reject.value == "authorization_reject"
        assert "'authorization_reject'" in migration_sql


class TestExemptionShipsWithZeroConstraint:
    """豁免与零约束必须同批 —— 只豁免就等于允许伪造实体记 passed。"""

    def test_standard_entities_constraint_exempts_the_new_kind(
        self, migration_sql: str
    ) -> None:
        block = re.search(
            r"ADD CONSTRAINT ck_wpees_standard_requires_entities CHECK \((.*?)\);",
            migration_sql,
            re.S,
        )
        assert block, "V165 里找不到 ck_wpees_standard_requires_entities —— 解析失效"
        body = block.group(1)
        assert "'authorization_reject'" in body, "新 kind 未被豁免 ⇒ 欠账没真解除"
        # 其余部分必须逐字保留 V151 语义，别顺手放松了通用规则
        assert "result <> 'passed'" in body
        assert "jsonb_array_length(operation_ids) >= 1" in body
        assert "jsonb_array_length(application_ids) >= 1" in body

    def test_zero_entities_constraint_exists_for_the_new_kind(
        self, migration_sql: str
    ) -> None:
        block = re.search(
            r"ADD CONSTRAINT ck_wpees_authorization_reject_zero_entities CHECK \((.*?)\);",
            migration_sql,
            re.S,
        )
        assert block, (
            "V165 缺 ck_wpees_authorization_reject_zero_entities —— 只豁免不加零约束，"
            "「永不创建 application 的场景」就能带伪造 operation/application 记 passed"
        )
        body = block.group(1)
        for column in ("operation_ids", "application_ids", "recovery_case_ids"):
            assert f"jsonb_array_length({column}) = 0" in body, (
                f"{column} 未被要求为 0 —— AC 5.6 的正面表达不完整"
            )

    def test_new_kind_is_not_folded_into_download_only_constraint(
        self, migration_sql: str
    ) -> None:
        """🔴 不得混进 `ck_wpees_download_only_zero_entities`。

        那条在三实体为零之外**还要求** `recovery_case_ids >= 1`（download-only 要终结一个
        case）。authorization_reject 的场景在 sealing 阶段就被拒、生产上连 case 都不建，
        混进去会把「必须有 case」错加到它头上，于是换一种方式继续写不进去。
        """
        block = re.search(
            r"ck_wpees_download_only_zero_entities(.*?);", migration_sql, re.S
        )
        if block is not None:
            assert "'authorization_reject'" not in block.group(1)


class TestKindDerivation:
    def test_quarantined_is_now_authorization_reject(self, declared: dict) -> None:
        scenario = declared["quarantined_rejects_application_and_engine"]
        assert scenario.expects_application is False
        assert scenario.expects_recovery_case is False
        assert scenario.expects_zero_entities is False
        assert scenario.kind is ScenarioKind.authorization_reject

    @pytest.mark.parametrize(
        ("scenario_id", "expected_kind"), sorted(_ZERO_APPLICATION_EXPECTED_KINDS.items())
    )
    def test_zero_application_scenarios_map_to_expected_kinds(
        self, declared: dict, scenario_id: str, expected_kind: ScenarioKind
    ) -> None:
        """回归锁：新分支只改 quarantined，其余 4 条仍走各自的前序分支。"""
        scenario = declared[scenario_id]
        assert scenario.expects_application is False
        assert scenario.kind is expected_kind

    def test_no_other_scenario_silently_became_the_new_kind(self, declared: dict) -> None:
        got = sorted(
            sid
            for sid, s in declared.items()
            if s.kind is ScenarioKind.authorization_reject
        )
        assert got == ["quarantined_rejects_application_and_engine"], (
            f"只应 quarantined 落 authorization_reject，实得 {got} —— "
            "kind 推导的分支顺序被动过"
        )


class TestRepresentabilityReverseLock:
    def test_every_declared_scenario_is_representable_or_registered(
        self, declared: dict
    ) -> None:
        offenders = sorted(
            sid
            for sid, s in declared.items()
            if not s.schema_representable_as_passed
            and sid not in SCHEMA_UNREPRESENTABLE_SCENARIOS
        )
        assert not offenders, (
            f"{offenders} 无法以 passed 存进 schema 却未登记归因 —— 这类场景会让它的 entry "
            "永不 verified，必须显式登记 owner，而不是等真库 CheckViolationError"
        )

    def test_registry_only_holds_genuinely_unrepresentable_scenarios(
        self, declared: dict
    ) -> None:
        """反向：登记表里不许放其实已经可表达的场景（否则是自造永久红）。"""
        bogus = sorted(
            sid
            for sid in SCHEMA_UNREPRESENTABLE_SCENARIOS
            if sid in declared and declared[sid].schema_representable_as_passed
        )
        assert not bogus, f"{bogus} 其实已可记 passed，应从登记表移除"

    def test_registry_is_empty_after_v165(self) -> None:
        """V165 的成果 tripwire：欠账已清零，谁再加回来必须连带补 schema。"""
        assert dict(SCHEMA_UNREPRESENTABLE_SCENARIOS) == {}, (
            "V165 已清空该表；若新增条目，请同时说明为何 schema 无法表达，"
            "并按 V165 的范式补一个 kind + 零约束，而不是让 entry 永久未验收"
        )

    def test_all_declared_scenarios_are_representable(self, declared: dict) -> None:
        bad = sorted(
            sid for sid, s in declared.items() if not s.schema_representable_as_passed
        )
        assert not bad, f"V165 之后不应再有不可表达场景，实得 {bad}"


class TestEntityShapeIsEnforcedBeforeInsert:
    """harness 侧比库层更早拦住违规形状（库层只在 passed 时才管）。"""

    @pytest.fixture()
    def scenario(self, declared: dict):
        return declared["quarantined_rejects_application_and_engine"]

    def test_zero_entity_observation_is_accepted(self, scenario) -> None:
        assert_entity_shape(
            scenario=scenario,
            observation=ScenarioObservation(scenario_id=scenario.scenario_id),
        )

    #: 🔴 一码一因：authorization_reject 的违规走 `application_forbidden_for_scenario`，
    #: **不**复用 download_only 的码 —— 两类 kind 的库层约束不同（download_only 要求
    #: case ≥ 1，本类要求 case = 0），合成一码会让 Task 39 的「每码各真触发一次且互不
    #: 重叠」判据当场打红（本轮实测踩过）。
    _CODE = "application_forbidden_for_scenario"

    @pytest.mark.parametrize(
        ("label", "ops", "apps", "cases"),
        [
            ("with_operation_and_application", 1, 1, 0),
            ("with_operation_only", 1, 0, 0),  # V165 把 operation 也收零
            ("with_application_only", 0, 1, 0),
            ("with_recovery_case_only", 0, 0, 1),  # 有 case 它就该是 recovery_reject
        ],
    )
    def test_any_entity_on_the_new_kind_is_refused(
        self, scenario, label: str, ops: int, apps: int, cases: int
    ) -> None:
        with pytest.raises(HarnessRejected) as err:
            assert_entity_shape(
                scenario=scenario,
                observation=ScenarioObservation(
                    scenario_id=scenario.scenario_id,
                    operation_ids=tuple(uuid.uuid4() for _ in range(ops)),
                    application_ids=tuple(uuid.uuid4() for _ in range(apps)),
                    recovery_case_ids=tuple(uuid.uuid4() for _ in range(cases)),
                ),
            )
        assert err.value.kind.value == self._CODE, (label, err.value.kind)

    def test_download_only_code_is_not_reused_for_the_new_kind(self, declared: dict) -> None:
        """反向锁：download_only 类的违规仍走它自己的码，两码互不串用。"""
        download_only = declared["download_only_zero_three_entities"]
        with pytest.raises(HarnessRejected) as err:
            assert_entity_shape(
                scenario=download_only,
                observation=ScenarioObservation(
                    scenario_id=download_only.scenario_id,
                    operation_ids=(uuid.uuid4(),),
                    recovery_case_ids=(uuid.uuid4(),),
                ),
            )
        assert err.value.kind.value == "download_only_has_entities"
