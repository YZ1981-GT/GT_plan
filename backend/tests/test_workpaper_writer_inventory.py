"""Wave 0 characterization for the workpaper writer / resolver / version-domain inventory.

Validates workpaper-html-onlyoffice-bidirectional-writeback-closure Property 4 and
Property 61.

Property 4 (business content version orthogonal to representation generation) and
Property 61 (every writer inside one revision domain) are both *red* during Wave 0:
`ContentMutationService` and `content_revision` do not exist yet. These tests pin the
violation shape so it cannot be quietly relabelled as compliant, and they exercise the
discovery predicate on synthetic sources so the guard is behavioural rather than textual.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

_REPO = Path(__file__).resolve().parents[2]
_GENERATOR_PATH = (
    _REPO / "backend" / "scripts" / "gen" / "generate_workpaper_writer_inventory.py"
)
_GATE_PATH = (
    _REPO / "backend" / "scripts" / "check" / "check_workpaper_writer_revision_gate.py"
)
_INVENTORY_PATH = _REPO / "backend" / "data" / "workpaper_writer_inventory.json"
_OVERLAY_PATH = _REPO / "backend" / "data" / "workpaper_writer_domain_overlay.json"

#: Fields Requirement 2.1 names as explicitly not business content and not a version.
_NON_CONTENT_FIELDS = ("prefill_stale", "updated_at", "updated_by")


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    return _load_module("wp_writer_inventory_generator", _GENERATOR_PATH)


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    return _load_module("wp_writer_revision_gate", _GATE_PATH)


@pytest.fixture(scope="module")
def inventory() -> dict:
    return json.loads(_INVENTORY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def source_scan(generator: ModuleType) -> tuple[list[dict], dict[str, dict]]:
    """One AST walk shared by every test that needs source-derived facts.

    ``collect_source_facts`` returns both the classified rows and the facts of *every*
    function, because verifying a retired writer needs the facts of a function that is
    deliberately absent from the rows.
    """
    return generator.collect_source_facts()


@pytest.fixture(scope="module")
def regenerated(generator: ModuleType, source_scan: tuple[list[dict], dict[str, dict]]) -> dict:
    rows, function_facts = source_scan
    overlay = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))
    return generator.build_inventory(rows, overlay, function_facts)


def _facts(generator: ModuleType, source: str, function_name: str):
    """Run the real AST fact extractor over a synthetic module and return one function."""
    tree = ast.parse(source)
    for qualname, node in generator._iter_functions(tree):
        if qualname.rsplit(".", 1)[-1] == function_name:
            return generator._collect_facts(node)
    raise AssertionError(f"synthetic source has no function named {function_name}")


def _writers(inventory: dict) -> list[dict]:
    return [entry for entry in inventory["entries"] if entry["kind"] in {"writer", "writer_resolver"}]


# ─── inventory is a live generated artifact, not a stored opinion ────────────


def test_inventory_on_disk_matches_the_ast(inventory: dict, regenerated: dict) -> None:
    """Source digest fail-closed: editing production source invalidates the inventory."""
    assert inventory["source_digest"] == regenerated["source_digest"]
    assert inventory["inventory_digest"] == regenerated["inventory_digest"]
    assert inventory["entries"] == regenerated["entries"]


def test_stale_inventory_is_rejected_rather_than_evaluated(
    gate: ModuleType, generator: ModuleType, inventory: dict
) -> None:
    """A self-consistent file whose source digest moved on is still refused."""
    stale = copy.deepcopy(inventory)
    stale["source_digest"] = "0" * 64
    stale["inventory_digest"] = generator.recompute_inventory_digest(stale)

    with pytest.raises(gate.WriterGateError, match="source digest is stale"):
        gate.assert_inventory_is_current(stale)


def test_hand_edited_inventory_is_rejected_by_self_consistency(
    gate: ModuleType, inventory: dict
) -> None:
    """Flipping a verdict without recomputing the digest must not be evaluated."""
    doctored = copy.deepcopy(inventory)
    doctored["entries"][0]["verdicts"]["bypasses_unified_commit"] = False

    with pytest.raises(gate.WriterGateError, match="internally inconsistent"):
        gate.assert_inventory_is_current(doctored)


def test_dropping_a_row_cannot_make_the_gate_greener(
    gate: ModuleType, generator: ModuleType, inventory: dict
) -> None:
    """Deleting a writer from the file must fail closed, not reduce debt.

    Covers the harder case too: an attacker-or-careless-editor who also recomputes
    ``inventory_digest`` after removing the row still fails, because the rows no longer
    match the ones re-derived from source.
    """
    before = gate.evaluate_gate(inventory)
    # Pick the victim by *fact*, not by name. The original test named
    # `wp_html_save::save_html_data`, which stopped carrying blocking facts the moment
    # Task 18 migrated it -- and then this test failed for a reason that has nothing to
    # do with what it is guarding. Deriving the victim keeps the guard about "removing a
    # blocking row fails closed" as the migration proceeds through Task 19/20.
    target = next(
        entry
        for entry in inventory["entries"]
        if entry["writer_id"] in before["bypasses_unified_commit"]
        and entry["writer_id"] in before["writes_legacy_version_field"]
    )
    # The row really was carrying blocking facts, so removing it is not a no-op.
    assert target["writer_id"] in before["bypasses_unified_commit"]
    assert target["writer_id"] in before["writes_legacy_version_field"]

    naive = copy.deepcopy(inventory)
    naive["entries"] = [
        entry for entry in naive["entries"] if entry["writer_id"] != target["writer_id"]
    ]
    with pytest.raises(gate.WriterGateError, match="internally inconsistent"):
        gate.assert_inventory_is_current(naive)

    rehashed = copy.deepcopy(naive)
    rehashed["inventory_digest"] = generator.recompute_inventory_digest(rehashed)
    with pytest.raises(gate.WriterGateError, match="do not match the rows re-derived"):
        gate.assert_inventory_is_current(rehashed)


def test_every_task3_domain_has_at_least_one_source_backed_row(
    gate: ModuleType, inventory: dict
) -> None:
    """HTML save, dedicated router, upload/import, WOPI, callback, custom, F2, rollback,
    history restore, export/storage resolver and the after-save handler are all present.

    A lane may be covered either by an open-debt row in ``entries`` or by a verified
    retirement in ``retired_writers``. Requiring it in ``entries`` alone would mean the
    first successfully migrated lane makes this guard permanently red, which would push
    the next person to delete the lane from ``_REQUIRED_DOMAINS`` -- i.e. to stop
    checking it exactly when it starts being satisfied.
    """
    issues = gate.evaluate_gate(inventory)
    assert issues["missing_required_domain"] == []
    by_domain = dict(inventory["stats"]["by_domain"])
    for domain, count in inventory["stats"]["retired_by_domain"].items():
        by_domain[domain] = by_domain.get(domain, 0) + count
    for domain in gate._REQUIRED_DOMAINS:
        assert by_domain.get(domain, 0) > 0, domain


def test_orchestrator_side_effect_lane_is_covered_by_a_verified_retirement(
    inventory: dict,
) -> None:
    """**Validates: Requirements 2.12, 13.4**

    Tasks 16/18 moved `after_save` out of the writer set. "Absent from `entries`" is what
    a *deleted* function produces too, so the lane's verdict lives in the retirement
    ledger and is positive: the function must still exist in source and the facts the
    retirement claims to have emptied must really be empty.
    """
    retired = {item["writer_id"]: item for item in inventory["retired_writers"]}
    handler = retired.get(
        "app.services.workpaper_save_orchestrator::WorkpaperSaveOrchestrator.after_save"
    )
    assert handler is not None, (
        "after_save has no retirement row -- the orchestrator lane would then be judged "
        "only by an absent entry, which a deletion satisfies just as well as a migration"
    )
    assert handler["domain"] == "orchestrator_side_effect"
    assert handler["source_state"] == "present_and_clean", (
        "the retirement claims the handler still exists; `absent` means it was deleted "
        "or renamed, not migrated"
    )
    facts = handler["facts"]
    assert facts["version_fields_written"] == []
    assert facts["version_fields_read"] == []
    assert facts["sql_update_columns"] == []
    assert facts["commit_receivers"] == [], "a shared side-effect handler owns no commit"
    assert facts["swallowed_exception_lines"] == [], (
        "Requirement 13.4: the audit log and the event enqueue must not degrade to warnings"
    )
    # It is still a real side-effect handler, not an emptied stub.
    assert facts["flush_receivers"], "after_save still flushes inside the caller's transaction"
    assert "<sets prefill_stale>" in facts["side_effects"]
    assert "<sets updated_at>" in facts["side_effects"]


def test_adjudications_are_domain_labels_not_bypass_exemptions(inventory: dict) -> None:
    """An adjudicated writer still reports its *source-derived* bypass verdict.

    The original form asserted `all(bypasses_unified_commit)` over adjudicated writers.
    That was only correct while **zero** writers had migrated: once Task 18 routed
    `wp_html_save` through `ContentMutationService`, a legitimately-migrated adjudicated
    writer made it fail -- for the opposite of the reason it guards.

    The invariant it actually protects is "the overlay cannot flip the verdict", so the
    judgement is now a re-derivation from the row's own facts:
    ``bypasses_unified_commit == (kind is writer) and not unified_commit_calls``.
    An overlay that tried to clear the verdict without the source really calling the
    unified boundary still fails, and the guard no longer rots as writers migrate.
    """
    adjudicated_writers = [
        entry
        for entry in _writers(inventory)
        if entry["adjudication"]["status"] == "adjudicated"
    ]
    assert adjudicated_writers
    for entry in adjudicated_writers:
        # 🔴 Task 20 给 derivation 加了第二项：`artifact_snapshot_only`。它**不是**豁免开关 ——
        # 它同样从源码派生（每一次 artifact 写的目标路径都在 `.versions`/`.upgrade-candidates`
        # 命名空间内，且函数不持久化任何业务内容），overlay 里没有任何字段能打开它。
        # 一个只把当前字节复制成快照的 writer 没有业务内容可提交，`bypasses_unified_commit`
        # 对它永远到不了零；类别把它换到自己的正面义务上（须裁决 + 须读统一计数器 + 不碰
        # legacy 字段），由门的 `artifact_snapshot_writer_not_verifiable` 判。
        # 见 `workpaper_sync/test_task20_writer_gate.py` 的 §2（含爆炸半径与两个扣分项的
        # 实测代表）。
        derived = (
            not entry["facts"]["unified_commit_calls"]
            and not entry["verdicts"]["artifact_snapshot_only"]
        )
        assert entry["verdicts"]["bypasses_unified_commit"] is derived, (
            f"{entry['writer_id']}: adjudication changed the derived bypass verdict "
            f"(verdict={entry['verdicts']['bypasses_unified_commit']}, "
            f"unified_commit_calls={entry['facts']['unified_commit_calls']}, "
            f"artifact_snapshot_only={entry['verdicts']['artifact_snapshot_only']})"
        )
        if entry["verdicts"]["artifact_snapshot_only"]:
            # 类别只能由源码事实成立，overlay 说了不算。
            targets = entry["facts"]["artifact_write_targets"]
            assert targets and all(item["target"] == "snapshot" for item in targets), (
                f"{entry['writer_id']}: 拿到快照类别却有非快照目标 {targets}"
            )
            assert not entry["verdicts"]["writes_business_content"], entry["writer_id"]
    # Both lanes must actually be represented, otherwise the re-derivation above is
    # vacuous: with every writer on one side, a hard-coded constant would satisfy it.
    verdicts = {
        entry["verdicts"]["bypasses_unified_commit"] for entry in adjudicated_writers
    }
    assert verdicts == {True, False}, (
        "the adjudicated set must contain both migrated and unmigrated writers for the "
        f"re-derivation to be a real judgement; got {verdicts}"
    )
    assert all(
        set(entry["adjudication"]) <= {"status", "domain", "version_domain_note"}
        for entry in adjudicated_writers
    ), "the overlay must not be able to introduce an exemption field"


# ─── Property 61: every writer inside one revision domain ───────────────────


def test_unified_revision_gate_is_red_and_names_every_reason(
    gate: ModuleType, inventory: dict
) -> None:
    """**Validates: Requirements 2.2**"""
    issues = gate.evaluate_gate(inventory)

    assert issues["bypasses_unified_commit"], "no writer routes through the unified commit yet"
    assert issues["writes_legacy_version_field"], "legacy _version/file_version writers exist"
    assert issues["owns_direct_commit"], "writers still own their own commit"
    # 🔴 Task 74 把 `unadjudicated_writer` 从 236 清到 0，所以原来那句
    # `assert issues["unadjudicated_writer"]` 必须改 —— 但**不是**删掉：它当初守的是「红要红得
    # 有名字」。裁决归零后这条判据变强而不是变弱：被点名的每一行现在都必须能在 overlay 里查到
    # lane + 理由，「本来就是未裁决行」这个逃生口关掉了。
    assert not issues["unadjudicated_writer"], (
        "Task 74 已把生产写路径的裁决清零；这里再出现未裁决 writer 说明有人加了新 writer 而没写"
        f"裁决：{issues['unadjudicated_writer'][:5]}"
    )
    adjudications = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))["adjudications"]
    named = {
        writer_id
        for name, values in issues.items()
        if name != "missing_required_domain"
        for writer_id in values
    }
    unexplained = sorted(
        writer_id
        for writer_id in named
        if not (adjudications.get(writer_id) or {}).get("version_domain_note")
    )
    assert not unexplained, (
        f"门点名了 {len(unexplained)} 行却在 overlay 里查不到理由：{unexplained[:5]} —— "
        "红必须有名字，且名字必须能查到 lane 与理由"
    )
    assert gate.main(["--skip-source-check"]) == 1
    assert gate.main(["--skip-source-check", "--expect-open-debt"]) == 0


def _cleared_to_task20_end_state(gate: ModuleType, inventory: dict) -> dict:
    """Simulate the Task 20 target state: every debt verdict cleared, all domains decided."""
    cleared = copy.deepcopy(inventory)
    required = list(gate._REQUIRED_DOMAINS)
    for index, entry in enumerate(cleared["entries"]):
        entry["verdicts"] = {name: False for name in entry["verdicts"]}
        entry["verdicts"]["has_characterization_test"] = True
        entry["adjudication"] = {
            "status": "adjudicated",
            "domain": entry["adjudication"].get("domain") or required[index % len(required)],
            "version_domain_note": "simulated Task 20 end state",
        }
    return cleared


def test_gate_can_reach_green_so_the_red_is_evidence_not_construction(
    gate: ModuleType, inventory: dict
) -> None:
    """A gate that can never go green proves nothing. This one can."""
    cleared = _cleared_to_task20_end_state(gate, inventory)
    issues = gate.evaluate_gate(cleared)

    assert not any(issues.values()), {k: v[:3] for k, v in issues.items() if v}


def test_a_single_unadjudicated_writer_keeps_the_gate_red(
    gate: ModuleType, inventory: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail-closed: after Wave 1 clears real debt, one undecided writer still blocks."""
    cleared = _cleared_to_task20_end_state(gate, inventory)
    target = next(
        entry for entry in cleared["entries"] if entry["kind"] in {"writer", "writer_resolver"}
    )
    target["adjudication"] = {"status": "unadjudicated", "domain": None}

    issues = gate.evaluate_gate(cleared)
    assert issues["unadjudicated_writer"] == [target["writer_id"]]
    assert not any(
        values for name, values in issues.items() if name != "unadjudicated_writer"
    ), "only the undecided writer should be blocking in this scenario"

    monkeypatch.setattr(gate, "load_inventory", lambda: cleared)
    assert gate.main(["--skip-source-check"]) == 1


def test_f2_word_sync_endpoints_are_writers_through_their_delegation(
    inventory: dict,
) -> None:
    """The F2-22/F2-23 from-OO endpoints persist content one hop away, via `_save_fields`."""
    for module in (
        "app.routers.wp_render_strategies._f2_stocktake_plan_sync",
        "app.routers.wp_render_strategies._f2_stocktake_summary_sync",
    ):
        endpoint = next(
            entry
            for entry in inventory["entries"]
            if entry["writer_id"].startswith(f"{module}::")
            and entry["writer_id"].endswith("_sync_from_oo")
        )
        assert endpoint["kind"] == "writer_resolver", endpoint["writer_id"]
        assert endpoint["delegates_to_content_writer"] == [f"{module}::_save_fields"]
        assert endpoint["facts"]["version_fields_written"] == []
        assert endpoint["resolver_identities"] == ["_onlyoffice_dir"]


def _synthetic_function(generator: ModuleType, module: str, qualname: str, source: str, *, imports=None):
    return {
        "writer_id": f"{module}::{qualname}",
        "module": module,
        "qualname": qualname,
        "facts_obj": _facts(generator, source, qualname.rsplit(".", 1)[-1]),
        "import_bindings": imports or {},
    }


def test_single_hop_delegation_resolves_same_module_and_imported_callees(
    generator: ModuleType,
) -> None:
    """Predicate-level proof that delegation is followed, and only where resolvable.

    This is asserted against the propagation function itself rather than the generated
    file, so it stays a real judge even when a mutation makes regeneration refuse.
    """
    persist = _synthetic_function(
        generator,
        "app.routers.demo_sync",
        "_save_fields",
        """
async def _save_fields(db, wp):
    await db.execute(sa.text(
        "INSERT INTO checklist_responses (wp_id, item_id, remark) VALUES (:w, :i, :r)"
    ), {})
    await db.commit()
""",
    )
    same_module_caller = _synthetic_function(
        generator,
        "app.routers.demo_sync",
        "sync_from_oo",
        """
async def sync_from_oo(db, wp):
    await _save_fields(db, wp)
""",
    )
    imported_caller = _synthetic_function(
        generator,
        "app.routers.demo_router",
        "restore",
        """
async def restore(db, wp):
    await DemoService.rollback_to_snapshot(db, wp)
""",
        imports={"DemoService": "app.services.demo_service.DemoService"},
    )
    imported_target = _synthetic_function(
        generator,
        "app.services.demo_service",
        "DemoService.rollback_to_snapshot",
        """
async def rollback_to_snapshot(db, wp):
    wp.parsed_data = {"restored": True}
""",
    )
    unrelated_same_name = _synthetic_function(
        generator,
        "app.routers.other_module",
        "sync_from_oo",
        """
async def sync_from_oo(db, wp):
    await _save_fields(db, wp)
""",
    )

    delegated = generator._propagate_content_writers(
        [persist, same_module_caller, imported_caller, imported_target, unrelated_same_name]
    )

    assert delegated["app.routers.demo_sync::sync_from_oo"] == [
        "app.routers.demo_sync::_save_fields"
    ]
    assert delegated["app.routers.demo_router::restore"] == [
        "app.services.demo_service::DemoService.rollback_to_snapshot"
    ]
    assert "app.routers.other_module::sync_from_oo" not in delegated, (
        "a same-named callee in another module must not create a delegation edge"
    )
    assert "app.routers.demo_sync::_save_fields" not in delegated, "direct writers are not delegates"


#: Writers that have actually been migrated onto `ContentMutationService`.
#: Task 18 owns the plain HTML save; Tasks 19/20 add upload / WOPI / custom / F2 /
#: rollback / history-restore, and each addition must land here **with** its production
#: change -- that is the whole point of keeping the ledger explicit rather than counting.
_MIGRATED_TO_UNIFIED_COMMIT = {
    "app.routers.wp_html_save::save_html_data",
    # ── Task 19: 上传 / WOPI / custom lane ────────────────────────────────────
    #
    # 三条都经 `build_content_mutation_service_writer()` →
    # `AuthoritativeContentWriter.commit_bytes()` → `ContentMutationService.commit(...)`
    # 提交权威 OOXML 本体（`custom_authoritative_ooxml` / `opaque_single_onlyoffice`
    # authority model + 三个 registry typed null marker 的 approved bundle）。
    #
    # 🔴 `custom_workpaper_cells::update_custom_cells` **不在这里**：它迁移后
    # 版本/内容/commit facts 全空，整行离开了 writer 集合，正面判据改由
    # `retired_writers` 台账承担（与 Task 16/18 对 `after_save` 的处理同形）。
    "app.services.wopi_service::WOPIHostService.put_file",
    "app.services.wp_download_service::WpUploadService.upload_file",
    # ── Task 19 增量二: F2 半闭环（authoritative-bytes lane）──────────────────
    #
    # F2-22 / F2-23 的 `_save_fields` 现在把 fields upsert 与**产生它的 docx 本体**在
    # 一次业务事务里提交。lane 选择是 manifest 事实而不是偏好：
    # `workpaper_sync_entry_manifest.json` 里 F2 entry（`xlsx/gt-f2-stocktake-bundle`）
    # 的 `capability=single_onlyoffice` ⇒ 权威内容是 OOXML 本体（Requirement 2.11），
    # projection lane 会在 `HtmlOnlyCommitPlan.__post_init__` 直接拒绝。capability 与
    # 第二套 to/from-OO 流程都不动 —— 删除半闭环是 Task 60（Requirement 12.7 要求先有
    # 等价证据与 rollback 点）。
    "app.routers.wp_render_strategies._f2_stocktake_plan_sync::_save_fields",
    "app.routers.wp_render_strategies._f2_stocktake_summary_sync::_save_fields",
    # ── Task 19 增量二: rollback / 历史恢复（projection lane）─────────────────
    #
    # 两条恢复 writer 走的是**另一条** lane（`commit_projection` →
    # `stage_html_projection` + `commit_html_projection`）：它们恢复的是结构化 projection
    # 本体（`working_paper.parsed_data` / `checklist_responses` 行），手上没有 OOXML 字节
    # 可发布成 representation，凭空造一个空白 xlsx 正是 Requirement 3.9 禁止的。
    #
    # 本集合按「有没有经统一入口」判定，与 lane 无关，所以两条 lane 的成员并列在这里；
    # 「谁走哪条 lane」由 `test_task19_writer_migration.py` 的两张分表逐条断言。
    "app.services.wp_migration_service::WpMigrationService.rollback",
    "app.services.version_trail_service::VersionTrailService.rollback_to_snapshot",
}


def test_only_the_migrated_writers_reach_the_unified_commit_boundary(
    inventory: dict,
) -> None:
    """**Validates: Requirements 2.2**

    The Wave 0 form of this test asserted *zero* adopters (`ContentMutationService` did
    not exist yet). Task 18 moves it to an explicit ledger: the set of rows that call the
    unified boundary must equal :data:`_MIGRATED_TO_UNIFIED_COMMIT`, and the bypass count
    must be exactly `writer_count` minus that set.

    Both directions matter. Dropping the equality for a `>= 1` count would let a writer
    silently *leave* the boundary again (Property 61's regression shape), and dropping the
    count arithmetic would let the gate report a debt number that does not add up.
    """
    reaching = {
        entry["writer_id"]
        for entry in inventory["entries"]
        if entry["facts"]["unified_commit_calls"]
    }
    assert reaching == _MIGRATED_TO_UNIFIED_COMMIT, (
        f"unified-commit adopters drifted: extra={reaching - _MIGRATED_TO_UNIFIED_COMMIT} "
        f"missing={_MIGRATED_TO_UNIFIED_COMMIT - reaching}"
    )
    stats = inventory["stats"]
    # 🔴 Task 20：算式多了一项 `artifact_snapshot_only`。这一项**不是**"允许绕过"的名单，
    # 而是「没有业务内容可提交」的源码派生类别（目标路径全在快照命名空间 + 零业务内容事实），
    # 所以它既不在统一入口里、也不该记在绕过里。这里把它**显式列名**而不是让算式自己少一个：
    # 名单漂移（比如某个真的写权威 artifact 的 writer 拿到了类别）会直接打红。
    snapshot_only = {
        entry["writer_id"]
        for entry in inventory["entries"]
        if entry["verdicts"]["artifact_snapshot_only"]
    }
    assert snapshot_only == {
        # 只把**当前**文件复制进 `.versions/`，内容零变化；快照名跟随 `content_revision`。
        "app.services.wp_storage_service::WpStorageService.save_version",
    }, f"artifact-snapshot 类别漂移：{sorted(snapshot_only)}"
    assert stats["artifact_snapshot_only_count"] == len(snapshot_only)
    assert snapshot_only.isdisjoint(_MIGRATED_TO_UNIFIED_COMMIT)
    assert stats["bypasses_unified_commit_count"] == stats["writer_count"] - len(
        _MIGRATED_TO_UNIFIED_COMMIT
    ) - len(snapshot_only)


def test_legacy_version_writers_are_the_enumerated_ones(inventory: dict) -> None:
    """Every remaining `_version`/`file_version` writer is a known Task 3 lane."""
    legacy = {
        entry["writer_id"]
        for entry in _writers(inventory)
        if entry["verdicts"]["writes_legacy_version_field"]
    }
    expected = {
        # ── Task 19 lane (still unmigrated) ──────────────────────────────────
        #
        # Task 19 已迁走三条，故它们**不再**出现在本集合里：
        #   * `custom_workpaper_cells::update_custom_cells` —— 整行离开 writer 集合
        #     （版本/内容/commit facts 全空），正面判据在 `retired_writers` 台账；
        #   * `wopi_service::WOPIHostService.put_file` —— 零 `file_version` 写，快照名
        #     改用本次保存前的 content revision；
        #   * `wp_download_service::WpUploadService.upload_file` —— 零 `file_version`
        #     写，冲突早检查比 `content_revision`。
        #
        # 🔴 期望值随生产一起搬是合法的，**因为所有者同时搬走了**：三条的零 version 写
        # 由 `test_task19_writer_migration.py::
        # test_migrated_writer_owns_no_private_version_counter` 逐条断言，且
        # `_MIGRATED_TO_UNIFIED_COMMIT` 同批加了正面接线判据。单独改这里会被那两条打红。
        #
        # 增量二又搬走一条：
        #   * `wp_storage_service::WpStorageService.save_version` —— 它只把**当前**文件
        #     复制进 `.versions/`（内容一个字节没变），却曾 `file_version += 1`，既造出
        #     与前一版逐字节相同的「新版本」，又成为第四个争抢同一列的写入方。现在快照
        #     名跟随真正在动的 `content_revision`，本方法只读不写。它仍留在 writer 集合
        #     里（生成器把 `shutil.copy2` 算作 writer 事实），但 `content_stores_written`
        #     已为空 —— 「它不再是 content writer」这件事由 overlay 的
        #     `version_domain_note` 与 `test_task19_writer_migration.py::
        #     test_the_storage_snapshot_no_longer_invents_a_version` 逐条说明与断言。
        "app.routers.wp_structure::save_structure",
        "app.services.working_paper_service::WorkingPaperService.upload_offline_edit",
        # ── Task 18: the three new `file_version` owners ─────────────────────
        # `WorkpaperSaveOrchestrator.after_save` used to carry the eighth entry here.
        # Tasks 16/18 removed its `file_version += 1`, so it left the writer set
        # entirely; its positive verdict now lives in `retired_writers` and is asserted
        # by `test_orchestrator_side_effect_lane_is_covered_by_a_verified_retirement`.
        #
        # But the file lifecycle version still has to advance when a file is actually
        # replaced, so Task 18 handed ownership to the three paths that write files.
        # They appear here because `file_version` is still a *legacy* domain from this
        # spec's point of view: their **business** content revision migration is Task 19.
        "app.routers.wp_editor_router::save_univer_data",
        "app.routers.wp_onlyoffice_router::post_sheet_onlyoffice_callback",
        "app.services.custom_query.snapshot_writer::SnapshotWriter._write_workpaper_cell",
        # `wp_html_save::save_html_data` left this set in Task 18: it writes no file and
        # no longer touches `parsed_data._version`; its business version is
        # `working_paper.content_revision`, advanced by `ContentMutationService`.
    }
    assert legacy == expected


def test_html_save_no_longer_writes_two_version_domains(inventory: dict) -> None:
    """**Validates: Requirements 2.1, 2.2**

    The Task 3 headline finding was: *one* HTML save moved *two* independent counters --
    it bumped `parsed_data._version` as its own optimistic lock, delegated a separate
    `working_paper.file_version` bump to `after_save`, and committed itself.

    Task 18 closes all three halves, and each one is asserted separately so that a
    partial regression cannot hide behind the others:

    1. `parsed_data._version` is no longer written (the second true source is gone);
    2. the router owns no commit (the unified boundary owns it);
    3. the shared side-effect handler is not back in the writer set.

    Plus the positive counterpart -- it really does reach `ContentMutationService` --
    because 1-3 are all negative and could be satisfied by deleting the endpoint.
    """
    entry = next(
        item
        for item in inventory["entries"]
        if item["writer_id"] == "app.routers.wp_html_save::save_html_data"
    )
    written = entry["facts"]["version_fields_written"]
    assert "parsed_data._version" not in written, (
        f"parsed_data._version is being written again: {written} -- it is a second true "
        "source and drifts against working_paper.content_revision (Requirement 2.1)"
    )
    assert "file_version" not in written, "HTML save writes no file, so no file_version"
    assert entry["facts"]["commit_receivers"] == [], (
        "the router must not own a commit: the only exit is "
        "ContentMutationService.commit_html_projection (Requirement 2.2)"
    )
    assert entry["facts"]["unified_commit_calls"], (
        "and it must actually reach the unified boundary -- the three assertions above "
        "are negative and would also hold for a deleted endpoint"
    )
    assert entry["verdicts"]["bypasses_unified_commit"] is False
    assert entry["verdicts"]["writes_legacy_version_field"] is False
    # It still delegates the replayable side effects, which is the shape Requirement 2.12
    # wants (`after_save` does the side effects, nobody's version moves there).
    assert entry["facts"]["after_save_calls"], "side effects still go through after_save"

    # The *second* counter stays closed: Tasks 16/18 removed `file_version += 1` from the
    # shared side-effect handler, so `after_save` is no longer a version owner and no
    # longer appears in `entries` at all. Its end state is asserted positively against the
    # retirement ledger instead of by looking for a row that is supposed to be gone.
    assert all(
        item["writer_id"]
        != "app.services.workpaper_save_orchestrator::WorkpaperSaveOrchestrator.after_save"
        for item in inventory["entries"]
    ), "after_save is back in the writer set -- the second version domain reopened"


def test_routing_through_the_unified_commit_clears_only_the_bypass_verdict(
    generator: ModuleType,
) -> None:
    """Behavioural, not textual: the predicate follows the call, not the file text."""
    bypassing = _facts(
        generator,
        """
async def save(db, wp):
    wp.parsed_data = {"a": 1}
    wp.file_version += 1
    await db.commit()
""",
        "save",
    )
    unified = _facts(
        generator,
        """
async def save(db, wp, content_mutation_service):
    await content_mutation_service.commit(wp_id=wp.id, projection={"a": 1})
""",
        "save",
    )

    assert bypassing.unified_commit_calls == set()
    assert generator._writes_content_directly(bypassing) is True
    assert unified.unified_commit_calls
    assert generator._classify(bypassing, delegates_to=[]) == "writer"
    assert generator._classify(unified, delegates_to=[]) is None


def test_commented_out_or_renamed_writes_are_not_discovered(generator: ModuleType) -> None:
    """A grep-shaped guard would still see these; the AST predicate must not."""
    commented = _facts(
        generator,
        """
async def save(db, wp):
    # wp.parsed_data = {"a": 1}
    # wp.file_version += 1
    return None
""",
        "save",
    )
    renamed = _facts(
        generator,
        '''
async def save(db, wp):
    """wp.parsed_data and wp.file_version are only mentioned in this docstring."""
    wp.some_unrelated_attribute = 1
    return None
''',
        "save",
    )

    assert generator._writes_content_directly(commented) is False
    assert generator._classify(commented, delegates_to=[]) is None
    assert generator._writes_content_directly(renamed) is False
    assert generator._classify(renamed, delegates_to=[]) is None


def test_raw_sql_content_writes_are_discovered(generator: ModuleType) -> None:
    """`wp_migration_service` and the F2/version-trail paths write through `text()`."""
    working_paper = _facts(
        generator,
        """
async def rollback(db, wid):
    await db.execute(sa.text(
        "UPDATE working_paper SET parsed_data = :data, updated_at = :ts WHERE id = :wid"
    ), {"wid": wid})
""",
        "rollback",
    )
    checklist = _facts(
        generator,
        """
async def restore(db, wid):
    await db.execute(sa.text("DELETE FROM checklist_responses WHERE wp_id = :wid"), {})
    await db.execute(sa.text(
        "INSERT INTO checklist_responses (project_id, wp_id, item_id, conclusion, remark) "
        "VALUES (:pid, :wid, :iid, NULL, :remark)"
    ), {})
""",
        "restore",
    )

    assert "working_paper.parsed_data" in working_paper.sql_update_columns
    assert "<sets working_paper.updated_at>" in working_paper.side_effects
    assert "working_paper.updated_at" not in working_paper.sql_update_columns
    assert "checklist_responses.<delete>" in checklist.sql_update_columns
    assert "checklist_responses.remark" in checklist.sql_update_columns


# ─── Property 4: business content version vs representation generation ──────


#: 允许写 `working_paper.content_revision` 的**唯一**归属：Wave 1 Task 10 的统一仓储层。
#:
#: 🔴 2026-08-25：Task 10 交付 `WorkpaperSyncRepository.bump_content_revision()` 后，
#: 「零 writer 触碰 content_revision」这句话不再成立。但判据不能就此删掉 —— 它要防的是
#: **业务 writer 各自 bump revision**（Property 4 / Requirement 2.1）。故改成允许清单：
#: 只有统一仓储层可写，任何 router/service 自己写 content_revision 仍立即打红。
#: Task 20 关门时再把「业务 writer 全部经由它」这条正向判据补上。
_UNIFIED_REVISION_WRITER_ALLOWLIST = {
    "app.services.workpaper_sync.repository::WorkpaperSyncRepository.bump_content_revision",
}


def test_orthogonal_business_content_revision_does_not_exist_yet(inventory: dict) -> None:
    """**Validates: Requirements 2.1**

    Property 4 needs a `content_revision` that only business content moves；而它只能由
    统一仓储层推进。除允许清单里的那一个入口外，任何 writer 写 `content_revision`
    都说明业务 writer 又开了第二个 revision 域。
    """
    offenders = sorted(
        entry["writer_id"]
        for entry in inventory["entries"]
        if entry["verdicts"]["writes_unified_content_revision"]
        and entry["writer_id"] not in _UNIFIED_REVISION_WRITER_ALLOWLIST
    )
    assert not offenders, (
        f"以下 writer 自己写 content_revision（必须经统一仓储层）: {offenders}"
    )
    assert "content_revision" not in inventory["stats"]["version_field_write_histogram"], (
        "content_revision 不得进入 legacy version 字段直方图"
    )
    # 反向：允许清单里的入口必须**真的存在**，否则清单是过期豁免
    known = {entry["writer_id"] for entry in inventory["entries"]}
    stale = sorted(_UNIFIED_REVISION_WRITER_ALLOWLIST - known)
    assert not stale, f"允许清单里的入口已不存在（过期豁免）: {stale}"


def test_status_and_staleness_fields_are_never_counted_as_business_content(
    inventory: dict,
) -> None:
    """Requirement 2.1: `prefill_stale`/`updated_at` must not enter the content domain."""
    for entry in inventory["entries"]:
        facts = entry["facts"]
        domain_fields = (
            facts["version_fields_written"]
            + facts["content_fields_written"]
            + facts["sql_update_columns"]
        )
        for field in _NON_CONTENT_FIELDS:
            assert not any(
                field in written for written in domain_fields
            ), f"{entry['writer_id']} counts {field} as business content"


def test_staleness_writers_are_recorded_as_side_effects_instead(
    generator: ModuleType,
) -> None:
    """Behavioural counterpart: a stale-marking function is a side effect, not a writer."""
    stale_only = _facts(
        generator,
        """
async def mark_stale(db, wp):
    wp.prefill_stale = True
    wp.updated_at = now()
""",
        "mark_stale",
    )

    assert generator._writes_content_directly(stale_only) is False
    assert generator._classify(stale_only, delegates_to=[]) is None
    assert "<sets prefill_stale>" in stale_only.side_effects
    assert "<sets updated_at>" in stale_only.side_effects


def test_after_save_side_effect_handler_no_longer_moves_a_version(
    gate: ModuleType, generator: ModuleType, inventory: dict
) -> None:
    """**Validates: Requirements 2.12, 13.4**

    Property 4 requires representation/side-effect work to leave the business version
    alone. Tasks 16/18 closed this one, so the gate lane is green -- and the falsifiability
    of that green is checked here, not assumed: putting the increment back into the
    retirement's measured facts must turn the lane red again.
    """
    issues = gate.evaluate_gate(inventory)
    assert issues["after_save_still_increments_revision"] == []
    assert issues["retired_writer_not_verifiable"] == []

    # Reverse check 1: a regressed handler (version write back in its body) is red.
    regressed = copy.deepcopy(inventory)
    handler = next(
        item
        for item in regressed["retired_writers"]
        if item["domain"] == "orchestrator_side_effect"
    )
    handler["facts"]["version_fields_written"] = ["file_version"]
    assert gate.evaluate_gate(regressed)["after_save_still_increments_revision"] == [
        handler["writer_id"]
    ]

    # Reverse check 2: a *deleted* handler must not inherit the migration's green verdict.
    deleted = copy.deepcopy(inventory)
    for item in deleted["retired_writers"]:
        if item["domain"] == "orchestrator_side_effect":
            item["source_state"] = "absent"
            item["facts"] = None
    assert gate.evaluate_gate(deleted)["retired_writer_not_verifiable"] == [
        handler["writer_id"]
    ]

    # Reverse check 3: dropping the ledger entirely must fail closed, not read as zero debt.
    #
    # 🔴 Task 74 改了这一段的**前提**，不是它的判据。原来 `orchestrator_side_effect` 只存在于退役
    # 台账里，所以「清空台账 ⇒ 该 domain 缺失」在**活体清册**上直接成立。Task 74 把两条真实的事件/
    # 保存后副作用行（`ConsistencyCheckService.update_workpaper_consistency`、
    # `register_event_handlers._on_b514_high_risk`）裁决进了这条 lane，于是 `entries` 侧也有了它 ——
    # 这正是 Task 20 证据 §九 预告的「等有第二个副作用 handler 进 entries 时复核」。
    #
    # 判据本身（台账是某个必需 domain 的唯一来源时，清空台账必须被报成缺失）没有变弱：改成在**构造
    # 的**清册上做 —— 先把 `entries` 侧的该 domain 摘掉，让台账重新成为唯一来源，再清空台账。
    ledger_only = copy.deepcopy(inventory)
    for entry in ledger_only["entries"]:
        if entry["adjudication"].get("domain") == "orchestrator_side_effect":
            entry["adjudication"] = {"status": "adjudicated", "domain": "html_save"}
    assert gate.evaluate_gate(ledger_only)["missing_required_domain"] == [], (
        "构造出的『台账是唯一来源』清册本身必须仍然绿 —— 否则下一步的断言证明不了任何东西"
    )
    ledger_only["retired_writers"] = []
    assert gate.evaluate_gate(ledger_only)["missing_required_domain"] == [
        "orchestrator_side_effect"
    ]

    without = copy.deepcopy(inventory)
    without["retired_writers"] = []
    del without["retired_writers"]
    with pytest.raises(gate.WriterGateError, match="no retired_writers ledger"):
        gate.evaluate_gate(without)


def test_generator_refuses_an_unverifiable_retirement(
    generator: ModuleType, source_scan: tuple[list[dict], dict[str, dict]]
) -> None:
    """**Validates: Requirements 2.12**

    The retirement ledger is the only positive verdict a migrated writer has, so the
    generator must refuse every way of writing one that cannot be falsified.
    """
    rows, function_facts = source_scan
    overlay = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))
    handler_id = (
        "app.services.workpaper_save_orchestrator::WorkpaperSaveOrchestrator.after_save"
    )

    # Facts withheld -> a retirement would be accepted without reading source.
    with pytest.raises(generator.WriterInventoryError, match="no per-function facts"):
        generator.build_inventory(rows, overlay)

    # Retired *and* still discovered as a writer -> the source regressed.
    regressed = copy.deepcopy(overlay)
    regressed["retired_adjudications"]["app.routers.wp_html_save::save_html_data"] = (
        copy.deepcopy(regressed["retired_adjudications"][handler_id])
    )
    del regressed["retired_adjudications"]["app.routers.wp_html_save::save_html_data"][
        "expected_empty_facts"
    ]
    regressed["retired_adjudications"]["app.routers.wp_html_save::save_html_data"][
        "expected_empty_facts"
    ] = ["commit_receivers"]
    with pytest.raises(generator.WriterInventoryError, match="both active and retired"):
        generator.build_inventory(rows, regressed, function_facts)

    # Same writer retired while still classified, without an active adjudication.
    both = copy.deepcopy(overlay)
    del both["adjudications"]["app.routers.wp_html_save::save_html_data"]
    both["retired_adjudications"]["app.routers.wp_html_save::save_html_data"] = {
        "domain": "html_save",
        "retired_by_task": "18",
        "retired_reason": "premature",
        "version_domain_note": "premature",
        "must_still_exist": True,
        "expected_empty_facts": ["commit_receivers"],
    }
    with pytest.raises(generator.WriterInventoryError, match="discovered as a writer"):
        generator.build_inventory(rows, both, function_facts)

    # Claimed-empty fact that is not actually empty.
    lying = copy.deepcopy(overlay)
    lying["retired_adjudications"][handler_id]["expected_empty_facts"] = ["flush_receivers"]
    with pytest.raises(generator.WriterInventoryError, match="claims these facts are empty"):
        generator.build_inventory(rows, lying, function_facts)

    # Nothing to assert -> not falsifiable.
    empty = copy.deepcopy(overlay)
    empty["retired_adjudications"][handler_id]["expected_empty_facts"] = []
    with pytest.raises(generator.WriterInventoryError, match="non-empty"):
        generator.build_inventory(rows, empty, function_facts)

    # A retirement pointing at a function that does not exist any more.
    vanished = copy.deepcopy(overlay)
    vanished["retired_adjudications"]["app.services.nope::gone"] = copy.deepcopy(
        vanished["retired_adjudications"][handler_id]
    )
    with pytest.raises(generator.WriterInventoryError, match="must_still_exist"):
        generator.build_inventory(rows, vanished, function_facts)


def test_representation_only_writers_are_distinguishable_from_content_writers(
    inventory: dict,
) -> None:
    """Property 4 needs the two lanes separable; today some artifact writers move no
    version at all while others move `file_version`, which is the divergence to fix."""
    artifact_only = [
        entry
        for entry in _writers(inventory)
        if entry["facts"]["artifact_writes"]
        and not entry["content_stores_written"]
        and not entry["facts"]["version_fields_written"]
    ]
    versioned_artifact = [
        entry
        for entry in _writers(inventory)
        if entry["facts"]["artifact_writes"] and entry["facts"]["version_fields_written"]
    ]

    assert artifact_only, "representation-only writers exist"
    assert versioned_artifact, "and other artifact writers do move a version field"
    assert {entry["writer_id"] for entry in artifact_only}.isdisjoint(
        {entry["writer_id"] for entry in versioned_artifact}
    )


def test_two_content_stores_hold_workpaper_business_content(inventory: dict) -> None:
    """Requirement 9.11 second-authority fact: F2 and the version trail keep workpaper
    content in `checklist_responses`, which has no version column at all."""
    stores = inventory["stats"]["by_content_store"]
    assert stores["working_paper"] > 0
    assert stores["checklist_responses"] > 0

    version_trail = next(
        entry
        for entry in inventory["entries"]
        if entry["writer_id"]
        == "app.services.version_trail_service::VersionTrailService.rollback_to_snapshot"
    )
    assert version_trail["content_stores_written"] == ["checklist_responses"]
    assert version_trail["facts"]["version_fields_written"] == []
    # The restore is a delete-then-reinsert of the workpaper's whole answer set, and it
    # advances no version field, so no reader can tell a restore from no change.
    columns = version_trail["facts"]["sql_update_columns"]
    assert "checklist_responses.<delete>" in columns
    assert "checklist_responses.remark" in columns


# ─── Requirement 9.11: resolver divergence ──────────────────────────────────


def test_canonical_resolver_is_the_minority_and_divergence_is_named(
    inventory: dict,
) -> None:
    """**Validates: Requirements 9.11**"""
    resolvers = [
        entry for entry in inventory["entries"] if entry["kind"] in {"resolver", "writer_resolver"}
    ]
    canonical = [entry for entry in resolvers if entry["canonical_resolver"]]

    assert canonical, "the designated canonical resolver does have callers"
    assert inventory["canonical_resolver"] == "resolve_wp_file"
    assert inventory["stats"]["non_canonical_resolver_only_count"] > len(canonical)
    assert inventory["stats"]["multi_resolver_count"] > 0


def test_onlyoffice_config_and_download_fan_out_to_several_resolvers(
    inventory: dict,
) -> None:
    """The config/download divergence design.md flags, as a structural assertion."""
    for writer_id in (
        "app.routers.wp_onlyoffice_router::get_sheet_onlyoffice_config",
        "app.routers.wp_onlyoffice_router::get_sheet_wopi_contents",
    ):
        entry = next(
            item for item in inventory["entries"] if item["writer_id"] == writer_id
        )
        assert len(entry["resolver_identities"]) > 1, writer_id
        assert entry["canonical_resolver"] is None, writer_id


def test_generator_refuses_an_unreviewed_or_stale_overlay(
    generator: ModuleType, source_scan: tuple[list[dict], dict[str, dict]]
) -> None:
    rows, function_facts = source_scan
    overlay = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))

    unreviewed = copy.deepcopy(overlay)
    unreviewed["review_status"] = "draft"
    with pytest.raises(generator.WriterInventoryError, match="review_status"):
        generator.build_inventory(rows, unreviewed, function_facts)

    bad_domain = copy.deepcopy(overlay)
    bad_domain["adjudications"]["app.routers.wp_html_save::save_html_data"]["domain"] = "nope"
    with pytest.raises(generator.WriterInventoryError, match="unknown domain"):
        generator.build_inventory(rows, bad_domain)

    stale_row = copy.deepcopy(overlay)
    stale_row["adjudications"]["app.routers.gone::vanished"] = {
        "domain": "html_save",
        "version_domain_note": "no longer exists",
    }
    with pytest.raises(generator.WriterInventoryError, match="no longer exist"):
        generator.build_inventory(rows, stale_row)


# ─── Task 20: injection guards for old _version/file_version/direct commit ───
#
# Property 4 & Property 61 require that once a writer has been migrated to the
# unified commit boundary, re-introducing legacy paths makes the gate go red.
# Each test below simulates a specific regression on the stored inventory and
# asserts that the gate produces the exact issue key that would block it.
#
# Task description: "注入旧 `_version/file_version/direct commit` 路径时守卫打红。"


def _inject_legacy_into_migrated_writer(
    inventory: dict, writer_id: str, *, version_field: str | None = None,
    direct_commit: bool = False,
) -> dict:
    """Deep-copy the inventory and inject a legacy regression into a migrated writer."""
    mutated = copy.deepcopy(inventory)
    entry = next(
        item for item in mutated["entries"] if item["writer_id"] == writer_id
    )
    if version_field:
        if version_field not in entry["facts"]["version_fields_written"]:
            entry["facts"]["version_fields_written"].append(version_field)
        entry["verdicts"]["writes_legacy_version_field"] = True
        entry["verdicts"]["keeps_legacy_write_path_beside_unified_commit"] = True
    if direct_commit:
        if "db.commit" not in entry["facts"]["commit_receivers"]:
            entry["facts"]["commit_receivers"].append("db.commit")
        entry["verdicts"]["owns_direct_commit"] = True
        entry["verdicts"]["keeps_legacy_write_path_beside_unified_commit"] = True
    return mutated


def test_injecting_parsed_data_version_into_migrated_writer_turns_gate_red(
    gate: ModuleType, inventory: dict,
) -> None:
    """**Validates: Property 4, Property 61 — Requirements 2.1, 2.2**

    Task 20 injection guard: a migrated writer that re-introduces `parsed_data._version`
    must be caught by `keeps_legacy_write_path_beside_unified_commit` AND
    `writes_legacy_version_field`, because it creates the double-revision shape Task 15
    forbids (one business application, two version movements).
    """
    target = "app.routers.wp_html_save::save_html_data"
    mutated = _inject_legacy_into_migrated_writer(
        inventory, target, version_field="parsed_data._version",
    )
    issues = gate.evaluate_gate(mutated)
    assert target in issues["keeps_legacy_write_path_beside_unified_commit"], (
        "injecting parsed_data._version into a unified-commit writer must fire "
        "keeps_legacy_write_path_beside_unified_commit"
    )
    assert target in issues["writes_legacy_version_field"], (
        "the legacy version field injection must also be independently visible"
    )


def test_injecting_file_version_into_migrated_writer_turns_gate_red(
    gate: ModuleType, inventory: dict,
) -> None:
    """**Validates: Property 4, Property 61 — Requirements 2.1, 2.2**

    Task 20 injection guard: a migrated writer that re-introduces `file_version`
    increments must be caught.
    """
    target = "app.services.wopi_service::WOPIHostService.put_file"
    mutated = _inject_legacy_into_migrated_writer(
        inventory, target, version_field="file_version",
    )
    issues = gate.evaluate_gate(mutated)
    assert target in issues["keeps_legacy_write_path_beside_unified_commit"]
    assert target in issues["writes_legacy_version_field"]


def test_injecting_direct_commit_into_migrated_writer_turns_gate_red(
    gate: ModuleType, inventory: dict,
) -> None:
    """**Validates: Property 61 — Requirements 2.2**

    Task 20 injection guard: a migrated writer that re-introduces a direct `db.commit()`
    beside the unified commit boundary creates a second transaction for the same business
    content, violating the single-commit invariant.
    """
    target = "app.routers.wp_html_save::save_html_data"
    mutated = _inject_legacy_into_migrated_writer(
        inventory, target, direct_commit=True,
    )
    issues = gate.evaluate_gate(mutated)
    assert target in issues["keeps_legacy_write_path_beside_unified_commit"], (
        "a direct commit beside the unified boundary must fire "
        "keeps_legacy_write_path_beside_unified_commit"
    )


def test_injecting_both_legacy_version_and_direct_commit_is_caught(
    gate: ModuleType, inventory: dict,
) -> None:
    """**Validates: Property 4, Property 61 — Requirements 2.1, 2.2**

    Task 20: the worst regression — both a legacy version write and a direct commit
    re-appear in the same migrated writer. The gate must catch both.
    """
    target = "app.services.wp_download_service::WpUploadService.upload_file"
    mutated = _inject_legacy_into_migrated_writer(
        inventory, target, version_field="file_version", direct_commit=True,
    )
    issues = gate.evaluate_gate(mutated)
    assert target in issues["keeps_legacy_write_path_beside_unified_commit"]
    assert target in issues["writes_legacy_version_field"]
    assert target in issues["owns_direct_commit"]


def test_removing_unified_commit_from_migrated_writer_turns_gate_red(
    gate: ModuleType, inventory: dict,
) -> None:
    """**Validates: Property 61 — Requirements 2.2**

    Task 20 injection guard: a migrated writer that silently leaves the unified boundary
    (e.g. someone deletes the `content_mutation_service.commit()` call) must immediately
    re-enter the `bypasses_unified_commit` debt set.
    """
    target = "app.routers.wp_html_save::save_html_data"
    mutated = copy.deepcopy(inventory)
    entry = next(
        item for item in mutated["entries"] if item["writer_id"] == target
    )
    # Remove the unified commit call and set the bypass verdict
    entry["facts"]["unified_commit_calls"] = []
    entry["verdicts"]["bypasses_unified_commit"] = True
    issues = gate.evaluate_gate(mutated)
    assert target in issues["bypasses_unified_commit"], (
        "removing the unified commit call must make the writer a bypass offender again"
    )


def test_multi_resolver_stays_in_has_debt_even_when_other_criteria_cleared(
    gate: ModuleType, inventory: dict,
) -> None:
    """**Task 20 → Task 30 → Task 71 handoff guard.**

    The `multi_resolver` criterion is deferred to Task 30/71, but it must continue to
    be counted in `has_debt` so that Task 30/71 can use the same gate to verify it
    reaches zero. Removing it from the report would be fail-open (indistinguishable
    from the criterion actually reaching zero).
    """
    cleared = _cleared_to_task20_end_state(gate, inventory)
    issues_cleared = gate.evaluate_gate(cleared)
    # After clearing everything, multi_resolver should still be 0 (it was cleared too)
    # But the REAL inventory must show multi_resolver > 0 because it's not yet resolved
    issues_real = gate.evaluate_gate(inventory)
    assert len(issues_real["multi_resolver"]) == 4, (
        f"multi_resolver must have exactly 4 rows (all in wp_onlyoffice_router), "
        f"got {len(issues_real['multi_resolver'])}"
    )
    # And they must all be in wp_onlyoffice_router
    assert all(
        "wp_onlyoffice_router" in writer_id
        for writer_id in issues_real["multi_resolver"]
    ), "all multi_resolver rows must be in wp_onlyoffice_router"
    # has_debt includes multi_resolver
    assert any(issues_real.values()), "gate must be RED when multi_resolver > 0"


def test_every_injection_on_every_migrated_writer_is_caught(
    gate: ModuleType, inventory: dict,
) -> None:
    """**Validates: Property 61 — Requirements 2.2**

    Comprehensive injection: for *every* migrated writer, injecting `parsed_data._version`
    must fire `keeps_legacy_write_path_beside_unified_commit`. This prevents a new
    migrated writer from being added to the ledger without the gate actually watching it.
    """
    for writer_id in _MIGRATED_TO_UNIFIED_COMMIT:
        # Find the writer in the inventory
        matches = [
            item for item in inventory["entries"] if item["writer_id"] == writer_id
        ]
        if not matches:
            continue  # may be in retired_writers
        mutated = _inject_legacy_into_migrated_writer(
            inventory, writer_id, version_field="parsed_data._version",
        )
        issues = gate.evaluate_gate(mutated)
        assert writer_id in issues["keeps_legacy_write_path_beside_unified_commit"], (
            f"injecting parsed_data._version into migrated writer {writer_id} "
            f"must fire keeps_legacy_write_path_beside_unified_commit"
        )


def test_representation_upgrade_lane_does_not_increment_business_revision(
    gate: ModuleType, inventory: dict,
) -> None:
    """**Validates: Property 4 — Requirements 2.1**

    The representation upgrade lane must not move the business content revision.
    This test verifies the gate criterion is green AND that injecting a revision bump
    turns it red.
    """
    issues = gate.evaluate_gate(inventory)
    assert issues["representation_upgrade_increments_business_revision"] == [], (
        "representation upgrade lane must not increment business revision"
    )
    # Injection: add a version write to the upgrade lane
    mutated = copy.deepcopy(inventory)
    lane_item = mutated["representation_upgrade_lane"][0]
    lane_item["version_fields_written"] = ["content_revision"]
    regressed = gate.evaluate_gate(mutated)
    assert regressed["representation_upgrade_increments_business_revision"], (
        "injecting a version write into the upgrade lane must turn the criterion red"
    )


def test_after_save_injection_into_retired_handler_turns_gate_red(
    gate: ModuleType, inventory: dict,
) -> None:
    """**Validates: Property 4 — Requirements 2.12**

    The after-save side-effect handler was retired by Task 18. Injecting a version
    write back into its measured facts must turn the gate red, proving the retirement
    is truly verifiable (not just unchecked).
    """
    issues = gate.evaluate_gate(inventory)
    assert issues["after_save_still_increments_revision"] == []
    # Inject version write into the retired handler
    mutated = copy.deepcopy(inventory)
    handler = next(
        item for item in mutated["retired_writers"]
        if item["domain"] == "orchestrator_side_effect"
    )
    handler["facts"]["version_fields_written"] = ["file_version"]
    regressed = gate.evaluate_gate(mutated)
    assert handler["writer_id"] in regressed["after_save_still_increments_revision"]


def test_gate_counts_are_internally_consistent(
    gate: ModuleType, inventory: dict,
) -> None:
    """**Validates: Property 61 — Requirements 2.2**

    Task 20 gate closure: the gate's issue counts must be self-consistent. Every writer
    that reaches the unified commit boundary must NOT be in bypasses_unified_commit,
    and vice versa; the sum must equal the writer count minus artifact-snapshot-only.
    """
    issues = gate.evaluate_gate(inventory)
    stats = inventory["stats"]
    unified_count = len(_MIGRATED_TO_UNIFIED_COMMIT)
    snapshot_count = stats["artifact_snapshot_only_count"]
    bypass_count = len(issues["bypasses_unified_commit"])
    writer_count = stats["writer_count"]
    assert bypass_count == writer_count - unified_count - snapshot_count, (
        f"bypass count arithmetic: {bypass_count} != {writer_count} - "
        f"{unified_count} - {snapshot_count}"
    )
    # No migrated writer should appear in bypasses_unified_commit
    migrated_in_bypass = _MIGRATED_TO_UNIFIED_COMMIT & set(issues["bypasses_unified_commit"])
    assert not migrated_in_bypass, (
        f"migrated writers in bypass list: {migrated_in_bypass}"
    )
