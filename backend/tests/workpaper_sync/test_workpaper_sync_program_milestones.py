"""G0-1 跨 spec HTML/OnlyOffice 双向回写 program milestone 守卫。"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_GENERATOR_PATH = (
    _REPO / "backend" / "scripts" / "gen" / "generate_workpaper_sync_program_milestones.py"
)
_DEFINITIONS_PATH = (
    _REPO / "backend" / "data" / "workpaper_sync_program_milestone_definitions.json"
)
_REGISTRY_PATH = _REPO / "backend" / "data" / "workpaper_sync_program_milestones.json"
_WRITER_GATE_PATH = (
    _REPO / "backend" / "scripts" / "check" / "check_workpaper_writer_revision_gate.py"
)


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def source() -> dict[str, Any]:
    generator = _load_module("workpaper_sync_program_milestone_generator_test", _GENERATOR_PATH)
    definitions = generator.load_definitions()
    registry = generator.build_program_registry()
    on_disk = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    spec_inputs: dict[str, str] = {}
    spec_facts = generator.collect_spec_facts(definitions, spec_inputs)
    return {
        "generator": generator,
        "definitions": definitions,
        "registry": registry,
        "on_disk": on_disk,
        "spec_facts": spec_facts,
    }


def test_generated_projection_is_current_and_self_digest_bound(source: dict[str, Any]) -> None:
    generator = source["generator"]
    registry = source["registry"]
    on_disk = source["on_disk"]

    assert on_disk == registry
    assert _REGISTRY_PATH.read_text(encoding="utf-8") == generator.render_registry(registry)
    assert registry["program_digest"] == generator.recompute_program_digest(registry)
    assert registry["database_probe_digest"] == generator.recompute_database_probe_digest(
        registry["database_probe_facts"]
    )
    assert registry["generated_at"] is None
    assert registry["source_commit"] is None
    assert registry["schema_version"] == "workpaper-sync-program-milestones/v1"


def test_g0_1_work_package_declares_every_required_execution_field(
    source: dict[str, Any],
) -> None:
    package = source["definitions"]["work_package"]
    required = {
        "owner",
        "modified_files",
        "input_gates",
        "output_artifact",
        "targeted_tests",
        "real_scenarios",
        "rollback",
        "evidence_path",
    }
    assert required <= package.keys()
    assert package["id"] == "G0-1"
    assert package["owner"]
    assert package["input_gates"]
    assert package["targeted_tests"]
    assert package["real_scenarios"]
    assert package["rollback"]["reversible"] is True
    assert package["rollback"]["data_migration"] is False
    assert {
        "backend/data/workpaper_sync_program_milestones.json",
        "backend/scripts/gen/generate_workpaper_sync_program_milestones.py",
        "backend/tests/workpaper_sync/test_workpaper_sync_program_milestones.py",
    } <= set(package["modified_files"])


def test_g0_2_work_package_declares_every_required_execution_field() -> None:
    path = (
        _REPO
        / ".kiro"
        / "specs"
        / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
        / "evidence"
        / "g0-2-denominator-discovery-state"
        / "README.md"
    )
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"<!-- G0-2-WORK-PACKAGE-JSON:START -->\s*```json\s*(\{.*?\})\s*```\s*"
        r"<!-- G0-2-WORK-PACKAGE-JSON:END -->",
        text,
        flags=re.DOTALL,
    )
    assert match, "G0-2 evidence 缺机器可读执行卡"
    package = json.loads(match.group(1))
    required = {
        "owner",
        "modified_files",
        "input_gates",
        "output_milestone",
        "targeted_tests",
        "real_scenarios",
        "rollback",
        "evidence_path",
    }
    assert required <= package.keys()
    assert package["id"] == "G0-2"
    assert package["owner"]
    assert package["input_gates"]
    assert package["targeted_tests"]
    assert package["real_scenarios"]
    assert package["rollback"]["reversible"] is True
    assert package["rollback"]["data_migration"] is False
    assert {
        "docs/operations/workpaper-html-onlyoffice-bidirectional-writeback-master-control.md",
        ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/tasks.md",
        "backend/data/workpaper_sync_program_milestones.json",
        "backend/tests/workpaper_sync/test_workpaper_sync_program_milestones.py",
    } <= set(package["modified_files"])


def test_g0_3_work_package_declares_every_required_execution_field() -> None:
    path = (
        _REPO
        / ".kiro"
        / "specs"
        / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
        / "evidence"
        / "g0-3-archive-writer-debt-dependency"
        / "README.md"
    )
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"<!-- G0-3-WORK-PACKAGE-JSON:START -->\s*```json\s*(\{.*?\})\s*```\s*"
        r"<!-- G0-3-WORK-PACKAGE-JSON:END -->",
        text,
        flags=re.DOTALL,
    )
    assert match, "G0-3 evidence 缺机器可读执行卡"
    package = json.loads(match.group(1))
    required = {
        "owner",
        "modified_files",
        "input_gates",
        "output_milestone",
        "targeted_tests",
        "real_scenarios",
        "rollback",
        "evidence_path",
    }
    assert required <= package.keys()
    assert package["id"] == "G0-3"
    assert package["status"] in {"IN_PROGRESS", "CLOSED"}
    assert package["output_milestone"] == "G0-3-ARCHIVE-DEPENDS-ON-WRITER-DEBT"
    assert package["owner"]
    assert package["input_gates"]
    assert package["targeted_tests"]
    assert package["real_scenarios"]
    assert package["rollback"]["reversible"] is True
    assert package["rollback"]["data_migration"] is False
    assert {
        ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/tasks.md",
        "backend/scripts/gen/generate_workpaper_sync_program_milestones.py",
        "backend/tests/workpaper_sync/test_workpaper_sync_program_milestones.py",
        "backend/data/workpaper_sync_program_milestones.json",
        ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/g0-3-archive-writer-debt-dependency/README.md",
    } <= set(package["modified_files"])


def test_eight_spec_task_and_dependency_denominators_are_exact(source: dict[str, Any]) -> None:
    registry = source["registry"]
    definitions = source["definitions"]
    expected_full = {
        "workpaper-html-onlyoffice-bidirectional-writeback-closure": 77,
        "published-representation-production-path-and-lane-adjudication": 43,
        "excel-structural-row-insertion-and-shift-aware-verification": 27,
        "excel-workbook-wide-row-change-propagation": 30,
        "custom-workpaper-template-ingestion-and-sync-closure": 19,
        "excel-template-override-layer-and-onlyoffice-template-editor": 27,
        "workpaper-guidance-content-closure": 23,
        "workpaper-page-formula-toolbar-closure": 17,
    }
    expected_main = {
        **expected_full,
        "published-representation-production-path-and-lane-adjudication": 28,
        "excel-structural-row-insertion-and-shift-aware-verification": 22,
    }
    expected_optional = {
        "published-representation-production-path-and-lane-adjudication": 15,
        "excel-structural-row-insertion-and-shift-aware-verification": 5,
    }

    assert set(registry["specs"]) == set(definitions["specs"]) == set(expected_full)
    assert registry["stats"]["spec_count"] == 8
    assert {name: spec["task_count"] for name, spec in registry["specs"].items()} == expected_full
    assert registry["stats"]["task_count"] == sum(expected_full.values()) == 263

    optional_ids_by_spec: dict[str, set[str]] = {}
    optional_re = re.compile(
        r"^\s*-\s*\[[ xX~\-]\]\*\s+([0-9]+(?:\.[0-9]+)*)(?:\.\s+|\s+)",
        flags=re.MULTILINE,
    )
    for spec_name, spec in registry["specs"].items():
        assert spec["task_states"], f"{spec_name} 的任务分母为空"
        assert set(spec["task_states"]) == set(spec["dependencies"])
        assert sum(spec["state_counts"].values()) == spec["task_count"]
        tasks_text = (_REPO / spec["path"]).read_text(encoding="utf-8")
        optional_ids = set(optional_re.findall(tasks_text))
        optional_ids_by_spec[spec_name] = optional_ids
        assert len(optional_ids) == expected_optional.get(spec_name, 0)
        assert optional_ids <= set(spec["task_states"])
        assert spec["task_count"] - len(optional_ids) == expected_main[spec_name]

    published_name = "published-representation-production-path-and-lane-adjudication"
    expected_published_optional = {
        "1.2", "1.4", "2.2", "2.3", "4.2", "4.4", "4.6", "6.2",
        "6.4", "7.2", "7.3", "9.2", "9.4", "9.6", "10.2",
    }
    assert optional_ids_by_spec[published_name] == expected_published_optional
    assert all(
        registry["specs"][published_name]["task_states"][task] == "x"
        for task in expected_published_optional
    )

    core = registry["specs"]["workpaper-html-onlyoffice-bidirectional-writeback-closure"]
    assert {task: core["task_states"][task] for task in ("1", "2", "20", "60", "62", "64")} == {
        "1": "~", "2": "~", "20": "~", "60": "~", "62": "~", "64": "~",
    }
    assert core["state_counts"] == {
        "completed": 66,
        "partial": 6,
        "blocked": 5,
        "pending": 0,
    }
    assert registry["stats"]["task_state_counts"] == {
        "completed": 240,
        "partial": 15,
        "blocked": 7,
        "pending": 1,
    }

    overview_expectations = {
        "workpaper-html-onlyoffice-bidirectional-writeback-closure": ("77 个主/全任务", "74 个任务"),
        published_name: (None, "共 28 个任务"),
        "excel-structural-row-insertion-and-shift-aware-verification": (
            "22 个主任务 / 27 个全任务", "共 22 个任务"
        ),
        "excel-workbook-wide-row-change-propagation": (
            "30 个任务 / 7 个 Wave", "26 个任务 / 7 个 Wave"
        ),
        "excel-template-override-layer-and-onlyoffice-template-editor": (
            "27 个任务 / 7 个 Wave", "25 个任务 / 7 个 Wave"
        ),
    }
    for spec_name, (current_text, stale_text) in overview_expectations.items():
        overview = (_REPO / registry["specs"][spec_name]["path"]).read_text(
            encoding="utf-8"
        ).split("## Task Dependency Graph", maxsplit=1)[0]
        if current_text is not None:
            assert current_text in overview
        if stale_text is not None:
            assert stale_text not in overview


def test_optional_star_checkbox_syntax_is_parsed_without_matching_prose(
    source: dict[str, Any],
) -> None:
    generator = source["generator"]
    tasks = generator.parse_tasks(
        "\n".join(
            (
                "- [x] 1. 主任务",
                "  - [x]* 1.2 属性测试（optional）",
                "  - 普通说明引用 1.3，不是任务",
            )
        ),
        source="synthetic.md",
    )
    assert set(tasks) == {"1", "1.2"}
    assert tasks["1.2"]["state"] == "x"
    assert tasks["1.2"]["title"] == "属性测试（optional）"


def test_g0_3_archive_dependency_is_closed_and_mutation_reopens_debt(
    source: dict[str, Any],
) -> None:
    generator = source["generator"]
    registry = source["registry"]
    dag = registry["dag"]
    nodes = {
        f"{spec_name}:{task_id}"
        for spec_name, spec in registry["specs"].items()
        for task_id in spec["task_states"]
    }

    assert dag["acyclic"] is True
    assert dag["node_count"] == 263
    assert dag["internal_edge_count"] == 448
    assert dag["cross_spec_edge_count"] == 120
    assert dag["node_count"] == len(nodes) == registry["stats"]["task_count"]
    assert all(edge["producer"] in nodes and edge["consumer"] in nodes for edge in dag["cross_spec_edges"])

    core_name = "workpaper-html-onlyoffice-bidirectional-writeback-closure"
    core = registry["specs"][core_name]
    assert core["dependencies"]["72"] == ["67", "68", "69", "70", "71", "74"]
    assert not any(
        item["code"] == "archive_bypasses_writer_debt" for item in registry["diagnostics"]
    )

    mutated_facts = copy.deepcopy(source["spec_facts"])
    mutated_facts[core_name]["graph"]["dependencies"]["72"].remove("74")
    mutated_dag, mutated_diagnostics = generator.validate_program_dag(
        source["definitions"], mutated_facts
    )
    assert mutated_dag["internal_edge_count"] == 447
    assert mutated_dag["cross_spec_edge_count"] == 120
    assert {
        "code": "archive_bypasses_writer_debt",
        "severity": "blocker",
        "spec": core_name,
        "task": "72",
        "missing_dependency": "74",
    } in mutated_diagnostics


def test_g0_3_wave_order_is_valid_and_same_wave_forward_dependency_is_rejected(
    source: dict[str, Any],
) -> None:
    generator = source["generator"]
    core_name = "workpaper-html-onlyoffice-bidirectional-writeback-closure"
    core_facts = source["spec_facts"][core_name]
    waves = {item["wave"]: item for item in core_facts["graph"]["waves"]}

    assert sorted(waves) == list(range(9))
    assert waves[7]["tasks"] == ["68", "69", "70", "71", "74"]
    assert waves[8]["tasks"] == ["72"]
    assert waves[8]["depends_on"] == [7]
    core_overview = (
        _REPO / core_facts["path"]
    ).read_text(encoding="utf-8").split("## Task Dependency Graph", maxsplit=1)[0]
    assert "77 个主/全任务、9 个 Wave" in core_overview
    assert "77 个主/全任务、8 个 Wave" not in core_overview

    def task_order(value: str) -> tuple[int, ...]:
        return tuple(int(part) for part in value.split("."))

    for spec_name, facts in source["spec_facts"].items():
        wave_of = {
            task: wave["wave"]
            for wave in facts["graph"]["waves"]
            for task in wave["tasks"]
        }
        for task, dependencies in facts["graph"]["dependencies"].items():
            assert all(
                wave_of[dependency] < wave_of[task]
                or (
                    wave_of[dependency] == wave_of[task]
                    and task_order(dependency) < task_order(task)
                )
                for dependency in dependencies
            ), f"{spec_name}:{task} 存在同 Wave 非前序依赖"

    mutated_graph = copy.deepcopy(core_facts["graph"])
    mutated_waves = {item["wave"]: item for item in mutated_graph["waves"]}
    mutated_waves[8]["tasks"].remove("72")
    mutated_waves[7]["tasks"].append("72")
    synthetic_tasks = {task: {} for task in core_facts["task_states"]}
    with pytest.raises(generator.ProgramMilestoneError, match="same-wave non-earlier tasks"):
        generator.normalize_dependency_graph(
            mutated_graph,
            synthetic_tasks,
            source="g0-3-same-wave-forward-mutation",
        )


def test_g0_3_does_not_promote_tasks_milestones_or_g0_4(
    source: dict[str, Any],
) -> None:
    registry = source["registry"]
    core_name = "workpaper-html-onlyoffice-bidirectional-writeback-closure"
    core = registry["specs"][core_name]
    assert core["task_states"]["72"] == core["task_states"]["74"] == "-"
    assert registry["stats"]["task_state_counts"] == {
        "completed": 240,
        "partial": 15,
        "blocked": 7,
        "pending": 1,
    }
    # 🔴 2026-09-11 · G4-2 后判据改成**方向感知**（原先是把整个分布锁成字面量）。
    #
    # 本测试名字说的是「不得**推进**」。而 G4-2 物理删除 `/d2-sync/*` 之后，
    # `HOST-CONSUMES-UNIFIED-PATH` 由 `ONLYOFFICE_VERIFIED` 退为 `STALE`
    # （删除前采的浏览器观测不再覆盖当前源码，属总控 §2.3 与 Task 45 的预定行为）——
    # 那是**降级**，恰恰是本守卫要防的反方向。锁死字面量会让一次合法降级把本守卫打红，
    # 从而逼人去改基线；而改基线的动作又同时放开了「推进」那一侧，守卫就废了。
    #
    # 故拆成两条：①终态桶只准降不准升（这才是「不得推进」）；②总数守恒（防有人凭空
    # 加/删 milestone 来凑分布）。
    counts = registry["stats"]["milestone_state_counts"]
    #: G0-3/G0-4 收口时的观测基线。终态桶只能 <= 它。
    _TERMINAL_CEILING = {"ONLYOFFICE_VERIFIED": 1, "CLOSED": 0, "REQUEST_PATH_VERIFIED": 0}
    for bucket, ceiling in _TERMINAL_CEILING.items():
        assert counts[bucket] <= ceiling, (
            f"{bucket} 由 {ceiling} 升到 {counts[bucket]} —— 本守卫禁止悄悄推进终态；"
            "要提升必须先有 producer task + 重算 evidence，并在此显式抬高上限"
        )
    assert counts["BLOCKED"] <= 3, f"BLOCKED 由 3 升到 {counts['BLOCKED']}"
    assert sum(counts.values()) == 16, f"milestone 总数应为 16，实为 {sum(counts.values())}"
    assert set(counts) == {
        "BLOCKED",
        "CLOSED",
        "IMPLEMENTED",
        "ONLYOFFICE_VERIFIED",
        "REQUEST_PATH_VERIFIED",
        "STALE",
    }, f"状态词表漂移：{sorted(counts)}"
    assert registry["stats"]["diagnostic_count"] == 5
    assert registry["stats"]["blocking_diagnostic_count"] == 5

    host = next(
        item for item in registry["milestones"] if item["id"] == "HOST-CONSUMES-UNIFIED-PATH"
    )
    # 🔴 2026-09-11 · G4-2 后：`HOST-CONSUMES-UNIFIED-PATH` 由 `ONLYOFFICE_VERIFIED`
    # 退为 `STALE` —— 物理删除 `/d2-sync/*` 使删除前采的浏览器观测不再覆盖当前源码
    # （`network:required_literal_missing` + `network:source_digest_mismatch` 落在
    # `GtOnlyOfficeSheet.vue`；`source_check_missing_file:capability` 绑在已删 router 上）。
    # 属总控 §2.3 与核心 Task 45 的**预定行为**，不是回退。
    #
    # 本测试的义务是「不得**推进**」，故判据从「== ONLYOFFICE_VERIFIED」改成
    # 「∈ 允许集且未越过终态上限」；同时新增一条**反向**判据：不得出现
    # `REQUEST_PATH_LEGACY`（那才是真回退 —— 宿主又走回旁路）。
    # 解除 STALE 的唯一途径是按 §9.6 在 post-delete 源码上重跑四个 pilot 并重采
    # G0-4 evidence，届时把下面的允许集收回 `{"ONLYOFFICE_VERIFIED"}`。
    assert host["state"] in {"ONLYOFFICE_VERIFIED", "STALE"}, host["state"]
    assert host["producers"] == [{"spec": core_name, "tasks": ["33"]}]
    entry_counts = host["entry_state_counts"]
    assert entry_counts["REQUEST_PATH_LEGACY"] == 0, (
        "有 entry 退回 REQUEST_PATH_LEGACY —— 宿主又走回 legacy 旁路，这是真回退"
    )
    assert entry_counts["BLOCKED"] == 0
    assert entry_counts["ONLYOFFICE_VERIFIED"] <= 4, "终态 entry 数不得超过 G0-4 分母"
    assert sum(entry_counts.values()) == 4, f"分母必须恒为 4，实为 {entry_counts}"
    entry_ids = [row["entry_id"] for row in host["entry_projection"]["entries"]]
    assert entry_ids == [
        "xlsx/gt-d2-accounts-receivable",
        "xlsx/gt-h1-fixed-assets",
        "xlsx/gt-g7-long-term-equity-main",
        "xlsx/b60/gt-b60-bundle",
    ]
    assert all(
        row["state"] in {"ONLYOFFICE_VERIFIED", "STALE"}
        for row in host["entry_projection"]["entries"]
    )
    entry = host["entry_projection"]["entries"][0]
    assert entry["entry_id"] == "xlsx/gt-d2-accounts-receivable"
    assert entry["state"] == host["state"], "顶层与首个 entry 的态必须同源推导，不得各说各话"
    assert len(entry["facts"]) == 8
    facts = {item["fact"]: item for item in entry["facts"]}
    #: STALE 时每条 fact 都必须带 stale 判读与原因，不得静默变 pass 或消失。
    if host["state"] == "STALE":
        assert all(item["result"] == "stale" for item in entry["facts"]), entry["facts"]
        assert all(
            (item.get("details") or {}).get("stale_reasons") for item in entry["facts"]
        ), "stale 必须逐条给出原因"
    else:
        assert all(item["result"] == "pass" for item in entry["facts"])
    #: 八条 fact 的**词表与齐备性**在两个态下都必须成立（少一条即分母被偷走）；
    #: 逐条的 pass/stale 由上面按 `host["state"]` 分支断言，不在此重复。
    assert set(facts) == {
        "user_sync_prefix_request",
        "no_legacy_bypass",
        "callback_url_bound",
        "application_applied",
        "operation_terminal_bound",
        "onlyoffice_content_version",
        "no_secondary_revision_domain",
        "server_computed_capability",
    }, f"八项谓词词表漂移：{sorted(facts)}"
    assert all(
        item["result"] in {"pass", "stale"} for item in entry["facts"]
    ), f"出现 pass/stale 之外的判读：{[i['result'] for i in entry['facts']]}"
    assert not any(
        item.get("code") == "producer_tasks_missing"
        and item.get("milestone") == "HOST-CONSUMES-UNIFIED-PATH"
        for item in registry["diagnostics"]
    )


def test_unknown_producer_task_is_rejected(source: dict[str, Any]) -> None:
    generator = source["generator"]
    definitions = copy.deepcopy(source["definitions"])
    definitions["milestones"][0]["producers"][0]["tasks"].append("999999")

    with pytest.raises(generator.ProgramMilestoneError, match="producer task does not exist"):
        generator.validate_program_dag(definitions, source["spec_facts"])


def test_combined_dependency_cycle_is_rejected(source: dict[str, Any]) -> None:
    generator = source["generator"]
    facts = copy.deepcopy(source["spec_facts"])
    spec_name = source["definitions"]["specs"][0]
    task_id = next(iter(facts[spec_name]["graph"]["dependencies"]))
    facts[spec_name]["graph"]["dependencies"][task_id] = [task_id]

    with pytest.raises(generator.ProgramMilestoneError, match="combined program dependency cycle"):
        generator.validate_program_dag(source["definitions"], facts)


def test_checkbox_and_manifest_capability_cannot_close_a_milestone(
    source: dict[str, Any],
) -> None:
    generator = source["generator"]
    task_and_manifest_only = [
        {"id": "producer-tasks", "result": "pass"},
        {"id": "manifest", "result": "pass"},
    ]
    assert generator.derive_milestone_state(task_and_manifest_only) == "IMPLEMENTED"
    assert (
        generator.derive_milestone_state(
            task_and_manifest_only
            + [{"id": "runtime", "result": "unverifiable", "grants_state": "CLOSED"}]
        )
        == "IMPLEMENTED"
    )

    granting_predicates = [
        predicate
        for milestone in source["definitions"]["milestones"]
        for predicate in milestone["predicates"]
        if predicate.get("grants_state")
    ]
    assert granting_predicates
    assert all(predicate["type"] == "evidence_bundle" for predicate in granting_predicates)
    assert all(predicate["grants_state"] == "CLOSED" for predicate in granting_predicates)


def test_any_advanced_state_has_a_passing_explicit_grant(source: dict[str, Any]) -> None:
    advanced = {"REQUEST_PATH_VERIFIED", "ONLYOFFICE_VERIFIED", "CLOSED"}
    for milestone in source["registry"]["milestones"]:
        if milestone["state"] not in advanced:
            continue
        assert any(
            predicate["result"] == "pass"
            and predicate.get("grants_state") == milestone["state"]
            for predicate in milestone["machine_predicates"]
        ), f"{milestone['id']} 在没有机器 grant 时越级到 {milestone['state']}"


def test_evidence_artifact_digest_drift_projects_stale(
    source: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generator = source["generator"]
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"current artifact")
    evidence = {
        "milestone": "SYNTHETIC",
        "verdict": "PASS",
        "producerSpec": "producer-spec",
        "producerTask": "1",
        "consumers": ["consumer-spec:Task2"],
        "artifacts": [{"path": "artifact.bin", "sha256": "0" * 64}],
    }
    (tmp_path / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(generator, "_REPO", tmp_path)

    result = generator.evaluate_evidence_bundle(
        {
            "id": "SYNTHETIC",
            "producers": [{"spec": "producer-spec", "tasks": ["1"]}],
            "consumers": [{"spec": "consumer-spec", "tasks": ["2"]}],
        },
        {
            "id": "synthetic.evidence",
            "type": "evidence_bundle",
            "paths": ["evidence.json"],
            "grants_state": "CLOSED",
            "require_producer_binding": True,
            "require_consumer_binding": True,
            "require_artifact_digests": True,
        },
        {},
    )
    assert result["result"] == "stale"
    assert "grants_state" not in result
    assert "artifact_digest_mismatch:artifact.bin" in result["details"]["stale_reasons"]
    assert "artifact_digest_coverage_incomplete" in result["details"]["stale_reasons"]


def test_database_probe_is_live_read_only_and_complete(source: dict[str, Any]) -> None:
    generator = source["generator"]
    facts = source["registry"]["database_probe_facts"]

    assert facts["status"] == "ok"
    assert facts["read_only_requested"] is True
    assert facts["read_only_verified"] is True
    assert facts["failure"] is None
    assert facts["probe_digest"] == generator.recompute_database_probe_digest(facts)
    assert facts["relation_denominator"] == facts["observed_relation_count"] > 0
    assert facts["column_denominator"] == facts["observed_column_count"] > 0
    assert facts["constraint_denominator"] == facts["observed_constraint_count"] > 0
    assert set(facts["probes"]) == {
        "durable-application-schema",
        "unified-room-schema",
    }
    assert all(probe["result"] == "pass" for probe in facts["probes"].values())


def test_database_unavailable_query_failure_and_empty_catalog_fail_closed(
    source: dict[str, Any],
) -> None:
    generator = source["generator"]
    definitions = source["definitions"]
    milestone = {"id": "SYNTHETIC"}
    predicate = {
        "id": "synthetic.database",
        "type": "database_readonly_schema",
        "probe_id": "durable-application-schema",
    }

    unavailable = generator.database_probe_failure_facts(
        definitions,
        status="database_unavailable",
        failure_phase="connect",
        failure_code="ConnectionRefusedError",
    )
    query_failed = generator.database_probe_failure_facts(
        definitions,
        status="query_failed",
        failure_phase="query:relations",
        failure_code="ProgrammingError",
    )
    empty_catalog = generator.build_database_probe_facts(
        definitions,
        observed_relations=(),
        observed_columns={},
        observed_constraints={},
        read_only_verified=True,
    )

    def evaluate(database_facts: dict[str, Any]) -> dict[str, Any]:
        return generator.evaluate_predicate(
            milestone,
            predicate,
            inputs={},
            manifest_facts={},
            writer_facts={},
            database_facts=database_facts,
            symbol_cache={},
        )

    assert evaluate(unavailable)["result"] == "blocked"
    assert evaluate(query_failed)["result"] == "fail"
    empty_result = evaluate(empty_catalog)
    assert empty_result["result"] == "fail"
    assert empty_result["reason_code"] == "database_schema_requirements_missing"
    assert empty_catalog["relation_denominator"] > 0
    assert empty_catalog["observed_relation_count"] == 0


def test_database_query_set_is_closed_and_read_only(source: dict[str, Any]) -> None:
    generator = source["generator"]
    assert generator._DATABASE_CONTROL_SQL == {
        "set_read_only": "SET TRANSACTION READ ONLY",
        "verify_read_only": "SHOW transaction_read_only",
    }
    forbidden = re.compile(
        r"\b(insert|update|delete|truncate|drop|alter|create|grant|copy)\b", re.I
    )
    for sql in generator._DATABASE_FACT_SQL.values():
        assert sql.lstrip().split(None, 1)[0].upper() in {"SELECT", "WITH"}
        assert not forbidden.search(sql)

    tree = ast.parse(_GENERATOR_PATH.read_text(encoding="utf-8"))
    text_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "sa"
        and node.func.attr == "text"
    ]
    assert len(text_calls) == 5
    for call in text_calls:
        assert len(call.args) == 1
        argument = call.args[0]
        assert isinstance(argument, ast.Subscript)
        assert isinstance(argument.value, ast.Name)
        assert argument.value.id in {"_DATABASE_CONTROL_SQL", "_DATABASE_FACT_SQL"}

    dotted_calls = {
        f"{node.func.value.id}.{node.func.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
    }
    assert not ({"session.add", "session.commit", "session.flush"} & dotted_calls)
    assert "session.rollback" in dotted_calls


def test_database_query_digest_tracks_reviewed_requirements(source: dict[str, Any]) -> None:
    generator = source["generator"]
    definitions = source["definitions"]
    changed = copy.deepcopy(definitions)
    changed["database_probes"][0]["relations"][
        "working_paper_content_application"
    ]["columns"].append("future_required_column")

    assert generator._database_query_set_digest(changed) != generator._database_query_set_digest(
        definitions
    )


def test_writer_gate_projection_is_recomputed_from_current_inventory(
    source: dict[str, Any],
) -> None:
    gate = _load_module("workpaper_writer_revision_gate_program_guard", _WRITER_GATE_PATH)
    inventory = gate.load_inventory()
    try:
        gate.assert_inventory_is_current(inventory)
        source_current = True
    except Exception:
        source_current = False
    issues = gate.evaluate_gate(inventory)
    projected = source["registry"]["writer_gate_facts"]

    assert projected["source_current"] is source_current
    assert projected["inventory_digest"] == inventory.get("inventory_digest")
    assert projected["source_digest"] == inventory.get("source_digest")
    assert projected["issue_counts"] == {
        name: len(values) for name, values in sorted(issues.items())
    }


def test_definition_digest_is_the_reviewed_single_source(source: dict[str, Any]) -> None:
    generator = source["generator"]
    definitions = source["definitions"]
    expected = hashlib.sha256(generator._stable_json(definitions).encode("utf-8")).hexdigest()
    assert source["registry"]["definition_digest"] == expected
    assert json.loads(_DEFINITIONS_PATH.read_text(encoding="utf-8")) == definitions


def test_g0_4_static_positive_flags_cannot_verify_host_fact(source: dict[str, Any]) -> None:
    generator = source["generator"]
    entry = {
        "entry_id": "xlsx/test",
        "network": {"requests": [], "complete_for_negative_assertion": True,
                    "execution_status": "COMPLETED", "positive_state_eligible": True,
                    "complete_for_positive_assertion": True},
        "editor_config": {"observed_query_keys": [], "execution_status": "COMPLETED",
                          "positive_state_eligible": True, "complete_for_positive_assertion": True},
        "database": {"execution_status": "NOT_RUN"},
        "required_callback_query_keys": [],
        "source_refs": [],
        "stale_reasons": [],
        "capability_literal_true": False,
        "server_computed_call_present": True,
    }
    assert generator.evaluate_host_path_entry_fact(entry, "user_sync_prefix_request")["result"] == "fail"
    assert generator.evaluate_host_path_entry_fact(entry, "callback_url_bound")["result"] == "unverifiable"
    assert generator.evaluate_host_path_entry_fact(entry, "application_applied")["result"] == "unverifiable"


def test_g0_4_database_facts_require_exact_entry_and_operation_binding(source: dict[str, Any]) -> None:
    generator = source["generator"]
    entry = {"entry_id": "xlsx/exact", "network": {}, "editor_config": {},
             "database": {"execution_status": "COMPLETED", "scenario_executed": True,
                          "read_only_capture": True, "applications": [{"id": "app-decoy", "entry_id": "xlsx/other", "state": "applied"}],
                          "operations": [{"id": "op-decoy", "entry_id": "xlsx/exact", "application_id": "app-decoy", "state": "completed"}],
                          "content_versions": [{"source": "onlyoffice", "operation_id": "op-decoy"}]},
             "required_callback_query_keys": [], "source_refs": [], "stale_reasons": [],
             "operation_terminal_states": ["completed"]}
    assert generator.evaluate_host_path_entry_fact(entry, "application_applied")["result"] == "fail"
    assert generator.evaluate_host_path_entry_fact(entry, "operation_terminal_bound")["result"] == "fail"
    assert generator.evaluate_host_path_entry_fact(entry, "onlyoffice_content_version")["result"] == "fail"
