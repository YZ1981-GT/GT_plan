# -*- coding: utf-8 -*-
"""Task 73 守卫：manifest 的 source-backed profile 三字段与 RG-15/16/17 的真实可达性。

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 73（Task 1 欠账收口）
Requirements 1.2（owner）/ 1.3 / 1.4 / 1.5 / 1.7 / 1.8 / 12.12 / 12.14
Properties 3 / 6

## 这个文件要证明什么

Task 1 要求「逐 entry 机器字段至少包含 editable / room_model / scenario_profile，并由
宿主、descriptor 与 room 事实生成」。实测欠账是：三个字段一个都不在 manifest 里，于是
`entry_profile` 的 RG-15/16/17 只能在手搓 fixture 上跑 —— 对真实数据结构性不可达
（假绿第①源）。本文件的判据分四层：

1. **字段真的在**：186 条 entry 全带三字段 + provenance，取值在封闭域内，且与 V151
   `working_paper_sync_test_run` 的 CHECK 同域。
2. **字段真的进 digest**：改任一 profile 字段，`manifest_digest` 与
   `profile_source_digest` 必须变；`source_digest` 必须不变（fail-closed 门不被削弱）。
3. **RG-15/16/17 真的跑在真实 manifest 上**，并且**能红也能绿** —— 换一份合规的实测
   事实，红的条数必须下降到只剩 RG-15 那一层（否则「全红」就成了不可证伪的常量）。
4. **反重言式**：把 overlay 的 capability 全部翻掉重跑生成器，三字段必须逐字节不变。
   这是本任务最重要的一条 —— 若 profile 从 capability 派生，RG-15/16/17 会恒真。

## 命名裁决（Task 1 散文 vs V151 列名）

Task 1 写 `editable`，`entry_profile.PROFILE_KEYS` 与 V151 列名写 `editability`。
**取 `editability`（三值封闭域）**：它同时是 DB 列名与 Python 枚举名，且比布尔多带
`readonly` / `unreachable` 两个真实状态；AC 12.12 用到的布尔 `editable` 由
`EntryProfile.editable` 单点派生。本文件断言磁盘上**只有一种拼写**。
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import entry_profile as EP  # noqa: E402
from app.services.workpaper_sync import entry_source_facts as F  # noqa: E402
from app.services.workpaper_sync.adapters import registry as RG  # noqa: E402

_MANIFEST_PATH = _BACKEND / "data" / "workpaper_sync_entry_manifest.json"
_OVERLAY_PATH = _BACKEND / "data" / "workpaper_sync_entry_overlay.json"
_GENERATOR_PATH = _BACKEND / "scripts" / "gen" / "generate_workpaper_sync_manifest.py"
_CLOSURE_PATH = _BACKEND / "scripts" / "check" / "check_workpaper_sync_closure.py"
_V151 = _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"
_FRONTEND_PROJECTION = (
    _REPO
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "sync"
    / "workpaperSyncManifest.generated.ts"
)


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def overlay() -> dict[str, Any]:
    return json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    return _load(_GENERATOR_PATH, "task73_manifest_generator")


@pytest.fixture(scope="module")
def discovery(generator: ModuleType) -> dict[str, Any]:
    """Node AST 发现只跑一次（每次调用都会 spawn node）。"""
    return generator.discover_source()


@pytest.fixture(scope="module")
def closure_gate() -> ModuleType:
    return _load(_CLOSURE_PATH, "task73_closure_gate")


def _observer(entry: dict[str, Any]) -> RG.ObservedEntryFacts:
    return RG.ObservedEntryFacts(
        descriptor=F.observe_descriptor_facts(entry), room=F.observe_room_facts(entry)
    )


def _independent_reachable(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        entry
        for entry in manifest["entries"]
        if entry.get("independent_entry") and entry.get("capability") != "unreachable"
    ]


def _mtime_coupled_observer(entry: dict[str, Any]) -> RG.ObservedEntryFacts:
    """descriptor 合规 + room 事实带 mtime 耦合的**合成**观察器。

    用途只有一个：单独证明 RG-17 还在 `build_report` 里被调用。RG-15/16 今天在真实数据上
    各有反例，所以「它们从报告里消失」会被漂移集合等式抓到；RG-17 已被 Task 21 清零
    （真实反例 0 条），等式判据对它失效 —— 摘掉 RG-17 也不会改变报告。喂一份非合规的
    合成 room 事实就能把这条覆盖补回来，而且**不需要生产存在缺陷**。
    """
    capability = EP.capability_of(entry)
    room_model = EP.RoomModel(entry["room_model"])
    return RG.ObservedEntryFacts(
        descriptor=EP.DescriptorFacts(
            mode=EP.DescriptorMode(capability.value), exposes_mode_switch=False
        ),
        room=EP.RoomFacts(
            shared_doc_key=room_model is EP.RoomModel.shared,
            doc_key_includes_mtime=True,
            participant_lease=room_model is not EP.RoomModel.none,
        ),
    )


def _layered_drift(
    manifest: dict[str, Any],
) -> tuple[dict[str, str], dict[str, set[str]], int]:
    """独立重算「`build_report` 应当报出的 profile 漂移」，按 RG-15 → RG-16 → RG-17 分层。

    刻意**不读** `report.profile_drift`：本函数是那个值的独立期望来源。逐 entry 取**首个**
    失败层（与 `build_report` 的短路顺序一致），所以三个分桶互斥、`reasons` 里的消息可与
    报告逐字比对 —— 某一层被摘掉、多出一层、或规则先后顺序变了都会打红。

    返回 `(reasons, layers, evaluated)`；`evaluated` 供非空性判据用（判据的非空性必须
    落在「评估了多少条」，不能落在「有多少条红」）。
    """
    reasons: dict[str, str] = {}
    layers: dict[str, set[str]] = {"rg15": set(), "rg16": set(), "rg17": set()}
    evaluated = 0
    for entry in _independent_reachable(manifest):
        entry_id = entry["entry_id"]
        evaluated += 1
        profile = EP.extract_entry_profile(entry)
        capability = EP.capability_of(entry)
        try:
            EP.assert_profile_consistent_with_capability(profile, capability)
        except EP.EntryProfileDriftError as exc:
            layers["rg15"].add(entry_id)
            reasons[entry_id] = str(exc)
            continue
        descriptor = F.observe_descriptor_facts(entry)
        assert descriptor is not None, (
            f"{entry_id}: 可达 entry 观察不出 descriptor —— `build_report` 会走它自己那条"
            "「产不出 descriptor 事实」的 raise，本推导的分层就与报告对不上了"
        )
        try:
            EP.assert_profile_consistent_with_descriptor(profile, capability, descriptor)
        except EP.EntryProfileDriftError as exc:
            layers["rg16"].add(entry_id)
            reasons[entry_id] = str(exc)
            continue
        try:
            EP.assert_profile_consistent_with_room(profile, F.observe_room_facts(entry))
        except EP.EntryProfileDriftError as exc:
            layers["rg17"].add(entry_id)
            reasons[entry_id] = str(exc)
    return reasons, layers, evaluated


def _synthetic_profile(room_model: EP.RoomModel) -> EP.EntryProfile:
    """构造一条**合成** profile。RG-17 的分支只看 `room_model`，其余字段给稳定占位。

    刻意不从真实 manifest 取：分支存活性判据不得依赖真实数据当下的取值 —— 那正是
    「守卫要求生产保持破损」的来源。
    """
    profile_id = f"synthetic.rg17.{room_model.value}.v1"
    return EP.EntryProfile(
        entry_id=f"synthetic/rg17-{room_model.value}",
        editability=EP.Editability.editable,
        room_model=room_model,
        scenario_profile=EP.ScenarioProfile(
            profile_id=profile_id, payload={"profile_id": profile_id}
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. 字段真的在，且与封闭域 / V151 双向锁死
# ═══════════════════════════════════════════════════════════════════════════


class TestProfileFieldsExistOnEveryEntry:
    def test_every_entry_carries_all_three_source_backed_fields(
        self, manifest: dict[str, Any]
    ) -> None:
        entries = manifest["entries"]
        assert entries, "manifest 为空 ⇒ 下面的全量断言会被 vacuous truth 掏空"
        for entry in entries:
            missing = [key for key in EP.PROFILE_KEYS if entry.get(key) is None]
            assert not missing, f"entry {entry['entry_id']} 缺 {missing}"
            assert entry.get("profile_source"), f"entry {entry['entry_id']} 缺 profile_source"

    def test_values_stay_inside_the_closed_domains(self, manifest: dict[str, Any]) -> None:
        for entry in manifest["entries"]:
            profile = EP.extract_entry_profile(entry)  # 任一非法值都会在这里抛
            assert profile.editability in set(EP.Editability)
            assert profile.room_model in set(EP.RoomModel)
            assert profile.editable is (profile.editability is EP.Editability.editable)

    def test_domains_match_the_v151_check_constraints(self, manifest: dict[str, Any]) -> None:
        """manifest 取值 ↔ DB CHECK 双向锁死（Task 39 要把它们写进 test_run 行）。"""
        sql = _V151.read_text(encoding="utf-8")
        for column, enum in (("editability", EP.Editability), ("room_model", EP.RoomModel)):
            match = re.search(
                rf"CHECK \(\s*{column} IN \(([^)]*)\)\s*\)", sql, re.I
            )
            assert match, f"V151 未找到 {column} 的 CHECK —— 无法反向核对封闭域"
            declared = {item.strip().strip("'") for item in match.group(1).split(",")}
            assert declared == {item.value for item in enum}, (
                f"{column} 的 Python 枚举与 V151 CHECK 不同域: {declared}"
            )
            used = {entry[column] for entry in manifest["entries"]}
            assert used <= declared, f"manifest 的 {column} 越出 V151 CHECK: {used - declared}"

    def test_scenario_profile_is_a_machine_payload_not_free_text(
        self, manifest: dict[str, Any]
    ) -> None:
        by_payload: dict[str, str] = {}
        by_profile_id: dict[str, set[str]] = {}
        for entry in manifest["entries"]:
            profile = EP.extract_entry_profile(entry)
            payload = entry["scenario_profile"]
            assert isinstance(payload, dict), "scenario_profile 必须是机器对象"
            assert payload["schema_version"] == F.SCENARIO_PROFILE_SCHEMA_VERSION
            assert payload["editability"] == entry["editability"]
            assert payload["room_model"] == entry["room_model"]
            assert " " not in profile.scenario_profile.profile_id
            assert re.fullmatch(r"[a-z0-9_.\-]+", profile.scenario_profile.profile_id), (
                "profile_id 必须是稳定 key —— required scenarios 不得由自由文本决定"
            )
            digest = profile.scenario_profile.digest
            assert re.fullmatch(r"[0-9a-f]{64}", digest)
            # digest 必须是 payload 的纯函数：同 payload 同 digest、不同 payload 不同 digest。
            # 它比 profile_id 更细（还含 mount_count / readonly_binding 等宿主事实），
            # 所以一个 profile_id 可以对应多个 digest —— 宿主事实变了 evidence 就该 stale。
            canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            previous = by_payload.setdefault(canonical, digest)
            assert previous == digest, "同一 payload 得到两个 digest ⇒ digest 不是纯函数"
            by_profile_id.setdefault(profile.scenario_profile.profile_id, set()).add(digest)
        inverse: dict[str, set[str]] = {}
        for profile_id, digests in by_profile_id.items():
            for digest in digests:
                inverse.setdefault(digest, set()).add(profile_id)
        collisions = {digest: ids for digest, ids in inverse.items() if len(ids) > 1}
        assert not collisions, f"不同 profile_id 撞到同一 digest: {collisions}"

    def test_only_one_spelling_is_persisted(self, manifest: dict[str, Any]) -> None:
        """命名裁决：磁盘上只留 `editability`，布尔 `editable` 只作派生属性。"""
        for entry in manifest["entries"]:
            assert "editable" not in entry, (
                f"entry {entry['entry_id']} 同时存了 `editable` —— 两种拼写会各自漂移"
            )
            assert "editable" not in entry["scenario_profile"]
        projection = _FRONTEND_PROJECTION.read_text(encoding="utf-8")
        assert "editability:" in projection and "roomModel:" in projection
        assert not re.search(r"^\s*editable:", projection, re.M)
        assert "editability VARCHAR" in _V151.read_text(encoding="utf-8")

    def test_provenance_points_at_real_source_lines(self, manifest: dict[str, Any]) -> None:
        """每条 fact 都要能追到文件+行，且文件真的存在（否则 provenance 是装饰）。"""
        fact_codes = {
            value
            for name, value in vars(F).items()
            if name.startswith("FACT_") and isinstance(value, str)
        }
        for entry in manifest["entries"]:
            source = entry["profile_source"]
            assert source["editability_fact"] in fact_codes
            assert source["room_model_fact"] in fact_codes
            assert source["source_refs"], f"entry {entry['entry_id']} 无 source_refs"
            for ref in source["source_refs"]:
                relative, _, line = ref.rpartition("#L")
                path = _REPO / relative
                assert path.is_file(), f"provenance 指向不存在的文件: {ref}"
                assert line.isdigit() and int(line) >= 1
                # 🔴 行号必须真的指向那行事实，不能只是「文件存在」：剥注释时丢行会让
                # 全部 `#Lnn` 整体偏移，而「文件存在」判据照样绿（实测踩过：
                # `^\s*//` 的 `\s` 吃空行 ⇒ WorkpaperWordEditor.vue 少 33 行）。
                lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
                assert int(line) <= len(lines), f"provenance 行号越界: {ref}"
                target = lines[int(line) - 1]
                assert re.search(
                    r"readonly|onlyoffice-config|doc_key|document_key|props\.mode|GtOnlyOfficeSheet|"
                    r"OnlyOfficeWordDialog|WorkpaperWordEditor|documentKey",
                    target,
                ), f"provenance {ref} 指向的行与该事实无关: {target.strip()[:90]!r}"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 字段与来源摘要真的进 manifest digest（Requirement 1.2）
# ═══════════════════════════════════════════════════════════════════════════


class TestProfileParticipatesInTheManifestDigest:
    def test_flipping_a_profile_field_changes_both_digests(
        self, generator: ModuleType, manifest: dict[str, Any]
    ) -> None:
        entries = copy.deepcopy(manifest["entries"])
        before_profile = generator._profile_source_digest(entries)
        entries[0]["editability"] = "readonly"
        assert generator._profile_source_digest(entries) != before_profile, (
            "profile 变化不改 profile_source_digest ⇒ 来源摘要没有跟着字段走"
        )

        original = copy.deepcopy(manifest)
        original.pop("manifest_digest")
        before_manifest = generator._sha256_bytes(
            generator._stable_json(original).encode("utf-8")
        )
        assert before_manifest == manifest["manifest_digest"], (
            "manifest_digest 不是对整份 manifest 现算的 ⇒ 下面的判据无意义"
        )
        for key, value in (("room_model", "none"), ("editability", "readonly")):
            mutated = copy.deepcopy(original)
            mutated["entries"][0][key] = value
            assert generator._sha256_bytes(
                generator._stable_json(mutated).encode("utf-8")
            ) != before_manifest, (
                f"{key} 不进 manifest_digest ⇒ evidence 不会因 profile 变化 stale"
            )

    def test_manifest_records_the_provenance_digest(self, manifest: dict[str, Any]) -> None:
        assert re.fullmatch(r"[0-9a-f]{64}", manifest["profile_source_digest"])

    def test_source_digest_gate_is_untouched(
        self, manifest: dict[str, Any], overlay: dict[str, Any], discovery: dict[str, Any]
    ) -> None:
        """加字段只改 overlay_digest，不动 source digest 的 fail-closed 门。"""
        assert manifest["source_digest"] == discovery["sourceDigest"]
        assert manifest["source_digest"] == overlay["approved_source_digest"]
        assert manifest["overlay_digest"] == generator_overlay_digest(overlay)


def generator_overlay_digest(overlay: dict[str, Any]) -> str:
    module = _load(_GENERATOR_PATH, "task73_overlay_digest")
    return module._sha256_bytes(module._stable_json(overlay).encode("utf-8"))


# ═══════════════════════════════════════════════════════════════════════════
# 3. 反重言式：profile 不得从 capability 派生
# ═══════════════════════════════════════════════════════════════════════════


class TestDerivationIsIndependentOfBusinessAdjudication:
    def test_flipping_every_capability_leaves_the_profile_byte_identical(
        self, generator: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """🔴 本任务最重要的一条判据。

        若有人把 `room_model` 写成 `'none' if capability == 'single_html' else 'shared'`，
        RG-15 就永远为真、永远发现不了漂移（假绿第③源）。这里把 overlay 里每个
        capability 都换成另一个合法值重跑生成器：三字段必须逐字节不变。
        """
        flip = {
            "single_onlyoffice": "single_html",
            "single_html": "single_onlyoffice",
            "bidirectional": "single_onlyoffice",
        }
        baseline = generator.build_manifest(discovery, overlay)
        twisted_overlay = copy.deepcopy(overlay)
        flipped = 0
        for default in twisted_overlay["defaults_by_component"].values():
            if default.get("capability") in flip:
                default["capability"] = flip[default["capability"]]
                flipped += 1
        for override in twisted_overlay.get("overrides") or []:
            if override.get("capability") in flip:
                override["capability"] = flip[override["capability"]]
                flipped += 1
        assert flipped >= 3, "没翻到 capability ⇒ 本判据是空操作"

        twisted = generator.build_manifest(discovery, twisted_overlay)
        changed_entries = [
            left["entry_id"]
            for left, right in zip(baseline["entries"], twisted["entries"])
            if left["capability"] != right["capability"]
        ]
        assert len(changed_entries) >= 100, (
            f"只有 {len(changed_entries)} 条 entry 的 capability 真的变了 ⇒ 判据近乎空操作"
            "（翻转必须落在实际生效的 defaults/overrides 上）"
        )
        for left, right in zip(baseline["entries"], twisted["entries"]):
            assert left["entry_id"] == right["entry_id"]
            for key in (*EP.PROFILE_KEYS, "profile_source"):
                assert left[key] == right[key], (
                    f"entry {left['entry_id']} 的 {key} 随 capability 变化 ⇒ profile 从业务"
                    "裁决派生，RG-15/16/17 已退化成重言式"
                )
        assert twisted["profile_source_digest"] == baseline["profile_source_digest"]

    def test_ast_guard_passes_on_the_real_derivation(self) -> None:
        F.assert_derivation_ignores_business_adjudication()

    @pytest.mark.parametrize(
        "collapse",
        [
            pytest.param('    return entry["capability"]', id="dict_key"),
            pytest.param("    return host.capability", id="attribute"),
            pytest.param("    return _sneak(host)", id="indirect_helper"),
        ],
    )
    def test_ast_guard_rejects_a_derivation_that_reads_capability(self, collapse: str) -> None:
        """判据本身必须双向有效：读了 capability 就得抛，否则它只是在盖章。"""
        synthetic = (
            "def _sneak(host):\n"
            '    return host.capability\n'
            "def derive_editability(host, component):\n"
            "    return 1\n"
            "def derive_room_model(host):\n"
            "    return 2\n"
            "def derive_entry_profile(host, component=None):\n"
            f"{collapse}\n"
        )
        with pytest.raises(F.EntrySourceFactError, match="重言式"):
            F.assert_derivation_ignores_business_adjudication(synthetic)

    def test_ast_guard_accepts_a_clean_synthetic_derivation(self) -> None:
        """反向锚：上一条若把守卫改成恒抛也会通过，所以必须有一条「合规必不抛」。"""
        clean = (
            "def derive_editability(host, component):\n"
            "    return host.readonly_binding\n"
            "def derive_room_model(host):\n"
            "    return host.endpoints\n"
            "def derive_entry_profile(host, component=None):\n"
            "    return derive_editability(host, component), derive_room_model(host)\n"
        )
        F.assert_derivation_ignores_business_adjudication(clean)

    def test_descriptor_observation_never_reads_capability_tainted_baseline_flags(self) -> None:
        """`flags.single_mode_switch_visible` 已经把 capability 揉进去了，读它即重言式。"""
        import ast as _ast
        import inspect

        body = inspect.getsource(F.observe_descriptor_facts)
        tree = _ast.parse(body.lstrip())
        constants = {
            node.value
            for node in _ast.walk(tree)
            if isinstance(node, _ast.Constant) and isinstance(node.value, str)
        }
        assert "ui_characterization" in constants, "descriptor 事实必须来自纯源码 UI 事实"
        assert "flags" not in constants and "single_mode_switch_visible" not in constants, (
            "observe_descriptor_facts 读了红基线的 capability-tainted flags ⇒ RG-16 退化"
        )

    def test_ast_guard_fails_closed_when_its_own_entry_list_is_emptied(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """入口清单被清空时必须判红，不能退化成 vacuous truth。"""
        monkeypatch.setattr(F, "_DERIVATION_ENTRY_FUNCTIONS", ())
        with pytest.raises(F.EntrySourceFactError, match="入口清单为空"):
            F.assert_derivation_ignores_business_adjudication()

    def test_ast_guard_fails_closed_when_a_derivation_function_is_renamed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            F, "_DERIVATION_ENTRY_FUNCTIONS", ("derive_entry_profile", "derive_gone")
        )
        with pytest.raises(F.EntrySourceFactError, match="改名或删除"):
            F.assert_derivation_ignores_business_adjudication()

    def test_generator_calls_the_guard_before_deriving(self, generator: ModuleType) -> None:
        """接线判据：守卫必须有生产消费方，不能只有测试在调。"""
        body = _GENERATOR_PATH.read_text(encoding="utf-8")
        without_comments = re.sub(r"(?m)^\s*#.*$", "", body)
        assert "assert_derivation_ignores_business_adjudication()" in without_comments

    def test_room_observation_ignores_the_manifest_room_model(
        self, manifest: dict[str, Any]
    ) -> None:
        """RG-17 的另一侧必须是实测，不能把 manifest 读回来自比。

        🔴 判据被加宽过，原因是一次实测到的守卫缺陷。原写法只探
        `_independent_reachable(manifest)[0]` **一条** entry、只把 `room_model` 翻成
        `none`。而那一条是 `docx/gt-a10-bundle`（可达序列前 5 条全是 docx bundle，
        `room_model=exclusive`）—— 对「把 manifest 裁决读回来当运行时事实」这个变异
        （M06：`shared_doc_key = (room_model == "shared")`）**行为不可见**：`exclusive` 与被
        翻成的 `none` 都推出 `shared_doc_key=False`，观察结果逐字不变，判据照样绿。

        M06 当时之所以还是 RED，是被同类的另一条判据兜着 ——
        `test_rg17_exercises_two_distinct_branches_on_real_data`，它断言真实数据**仍然**
        违反 RG-17，即要求生产保持破损。那条改写成合成事实之后，本条必须自己站住：
        逐条扫全部独立可达 entry，每条都把裁决翻遍三种取值，并断言三种 room_model 里
        真实存在的那几种都被覆盖到（否则又会退化成单点探针）。
        """
        reachable = _independent_reachable(manifest)
        assert len(reachable) >= 100, f"只探了 {len(reachable)} 条 ⇒ 判据被空集掏空"
        covered: set[str] = set()
        for original in reachable:
            entry = copy.deepcopy(original)
            observed = F.observe_room_facts(entry)
            covered.add(str(original["room_model"]))
            # 逐一翻成**每一种**合法裁决：只翻一种时，恰好与原值同推导结果的那条会漏。
            for verdict in sorted(item.value for item in EP.RoomModel):
                entry["room_model"] = verdict
                entry["scenario_profile"]["room_model"] = verdict
                entry["scenario_profile"]["doc_key_identity"] = (
                    "server_doc_key_scoped_to_wp_without_user_component"
                )
                assert F.observe_room_facts(entry) == observed, (
                    f"{original['entry_id']}: 把 manifest 裁决改成 {verdict!r} 后观察结果变了"
                    " ⇒ observe_room_facts 读了 manifest 里的裁决，RG-17 退化成自我比对"
                )
        assert covered == {
            str(entry["room_model"]) for entry in reachable
        } and len(covered) >= 2, (
            f"真实数据只覆盖到 {sorted(covered)} 一种 room_model ⇒ 翻裁决的判据可能对当下"
            "数据整体不敏感，需要补合成 entry"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 源码事实层本身可证伪
# ═══════════════════════════════════════════════════════════════════════════


class TestSourceFactsAreObservedNotAssumed:
    def test_doc_key_provider_probe_finds_both_real_routes(self) -> None:
        """两条真实路由都要被实扫到，且 `probe_kind` 必须如实反映「有没有真执行过」。

        🔴 判据方向被 Task 21 反转了。接线前 xlsx 路由的 doc_key 是
        `_generate_doc_key(file_path, wp_code)` —— 模块级双参纯函数，
        `_behavioral_mtime_probe` 能把它单独提取出来真跑一遍（改 mtime 再比 key），
        所以当时要求 `probe_kind == "behavioral"` 且 `includes_mtime is True`。
        接线后两条路由都改成 `await _room_identity.resolve_room_doc_key(...)`：
        跨模块 async seam，探针**按设计**提取不出来，只能如实降级标注
        `static_expression`（`includes_mtime` 由静态表达式判定接管）。

        保留下来的是那条两个方向都能红的判据 —— **标注 ↔ 证据**：
        把 `probe_kind` 写死成 `behavioral`（静态结论冒充实测）在这里红；
        doc_key 退回路由本地的 mtime 算法，seam / `includes_mtime` 断言红；
        真执行探针整段被掏空，下面的合成往返判据红。
        """
        import ast

        providers = F.doc_key_providers()
        for endpoint in (
            "/api/workpapers/*/sheets/*/onlyoffice-config",
            "/api/projects/*/working-papers/*/onlyoffice-config",
        ):
            assert endpoint in providers, (
                f"实扫丢了真实路由 {endpoint} —— 前端端点会全部判成「无后端路由」，"
                "room_model 集体退化成 exclusive（假事实）"
            )
        for endpoint, provider in providers.items():
            assert provider.probe_kind in {"behavioral", "static_expression"}
            assert "resolve_room_doc_key" in provider.doc_key_expression, (
                f"{endpoint} 的 doc_key 不再由 room seam 派生（实测表达式 "
                f"{provider.doc_key_expression!r}）—— 复核源码 diff，别放宽本判据"
            )
            assert provider.probe_kind == "static_expression", (
                f"{endpoint} 的 doc_key 由跨模块 async seam 派生，真执行探针提取不出来，"
                "标注只能是 static_expression。它若变回 behavioral，要么 doc_key 落回了"
                "路由本地的可提取 helper，要么标注在冒充实测 —— 两种都要先看源码 diff"
            )
            assert provider.includes_mtime is False, (
                f"{endpoint} 的 doc_key 又与 mtime 耦合 —— Property 6 回归"
            )
            assert provider.includes_user is False, (
                f"{endpoint} 的 doc_key 含用户成分 ⇒ 同 wp 的两个用户进不了同一间房"
            )

        # 只断言「现在是 static_expression」会让真执行探针整段退化成死代码
        # （假绿第①源）：下次真有人写回 mtime helper 时没有任何判据会红。
        # 用合成模块双向验证探针能力，不依赖生产源码此刻恰好是什么形态。
        coupled = (
            "def _generate_doc_key(file_path, wp_code):\n"
            "    return f'{wp_code}-{file_path.stat().st_mtime_ns}'\n"
        )
        free = (
            "def _generate_doc_key(file_path, wp_code):\n"
            "    return f'{wp_code}-{file_path.name}'\n"
        )
        extractable = "doc_key = _generate_doc_key(file_path, wp_code)"
        assert F._behavioral_mtime_probe(ast.parse(coupled), coupled, extractable) is True, (
            "真执行探针对 mtime 耦合的 helper 判不出 True ⇒ Property 6 的实测能力已失效"
        )
        assert F._behavioral_mtime_probe(ast.parse(free), free, extractable) is False, (
            "探针对与 mtime 无关的 helper 也判 True ⇒ 它不是在实测，而是恒真"
        )
        seam_call = "doc_key = await _room_identity.resolve_room_doc_key(db, wp_id=wp_id)"
        assert F._behavioral_mtime_probe(ast.parse(free), free, seam_call) is None, (
            "表达式不是可独立提取的 helper 时，探针必须返回 None 交回静态判定 —— "
            "吞成 False 就等于把「没测过」冒充成「测过且不含 mtime」"
        )

    def test_room_service_is_still_unwired_and_reported_as_such(
        self, manifest: dict[str, Any]
    ) -> None:
        """「尚不可观测」必须是机器可读状态，而不是手填一个看起来合理的布尔。"""
        wiring = F.room_service_wiring()
        states = {entry["scenario_profile"]["room_service_state"] for entry in manifest["entries"]}
        expected = F.ROOM_SERVICE_WIRED if wiring else F.ROOM_SERVICE_PENDING
        assert states == {expected}
        assert manifest["stats"]["room_service_state"] == expected
        for entry in _independent_reachable(manifest)[:5]:
            assert F.observe_room_facts(entry).participant_lease is bool(wiring)

    def test_unreachable_host_is_derived_from_zero_inbound_references(
        self, manifest: dict[str, Any]
    ) -> None:
        index = F.frontend_reference_index()
        assert index.scanned_files > 1000, "入边索引扫描面过小 ⇒ 可达性判据不可信"
        unreachable = [
            entry for entry in manifest["entries"] if entry["editability"] == "unreachable"
        ]
        assert unreachable, "至少还有一个不可达旧桩（Requirement 1.7 未清理）"
        for entry in unreachable:
            assert index.inbound(entry["host_path"]) == ()
            assert entry["profile_source"]["editability_fact"] == F.FACT_HOST_UNREACHABLE
        reachable_hosts = {
            entry["host_path"]
            for entry in manifest["entries"]
            if entry["editability"] != "unreachable"
        }
        for host in sorted(reachable_hosts):
            assert index.inbound(host), f"{host} 无入边却被判可达"

    def test_declaration_files_are_not_reachability_evidence(self) -> None:
        """`components.d.ts` 提到每个组件，若算入边则可达性判据恒真。"""
        index = F.frontend_reference_index()
        for referrers in index.imports.values():
            assert not any(item.endswith(".d.ts") for item in referrers)
        for referrers in index.tags.values():
            assert not any(item.endswith(".d.ts") for item in referrers)

    def test_comment_only_endpoints_are_not_counted(self) -> None:
        """注释里的端点不得被当成真实请求（room_model 的假事实来源之一）。"""
        F._assert_comment_stripping.cache_clear()
        assert F._assert_comment_stripping() is True
        # 真实反例：b60 宿主的文件头注释里写着「切到在线编辑前先 GET onlyoffice-config」。
        b60 = F._endpoint_facts(
            "audit-platform/frontend/src/components/workpaper/b60/GtB60DocxPane.vue"
        )
        assert b60 == (), f"注释里的端点被当成真实请求: {b60}"
        for endpoint, ref in F._endpoint_facts(
            "audit-platform/frontend/src/components/workpaper/WorkpaperWordEditor.vue"
        ):
            assert endpoint.startswith("/api/") and "\n" not in endpoint, endpoint
            assert "#L" in ref

    def test_endpoint_regex_never_spans_lines(self) -> None:
        """跨行引号会把整段注释吞成一个「端点」（首版实测踩过）。"""
        swallowed = "'>\n * - 切到在线编辑前先 GET onlyoffice-config 才显示\n */\nimport * from'"
        assert F._ENDPOINT_RE.findall(swallowed) == [], (
            "端点正则允许跨行 ⇒ 注释块被吞成端点，该 entry 的 room_model 会被判成 "
            "frontend_endpoint_without_backend_route（假事实）"
        )
        assert F._ENDPOINT_RE.findall("const u = '/api/x/onlyoffice-config'") == [
            "/api/x/onlyoffice-config"
        ]

    def test_template_tag_edge_counts_even_without_an_import(self) -> None:
        """unplugin 全局自动注册的宿主可以不写 import，模板标签用法也算入边。

        ⚠️ 实测：当前 185 个宿主里 **tag-only 为 0**（57 both / 127 import-only），
        所以对真实数据把这条边删掉是**行为不变**的无效变异 —— 这条判据因此用合成索引
        证明该能力真的接着，而不是靠现网数据碰巧覆盖。
        """
        index = F.FrontendReferenceIndex(
            scanned_files=2,
            imports={},
            tags={"GtGhostHost": ("audit-platform/frontend/src/views/Page.vue",)},
        )
        host = "audit-platform/frontend/src/components/workpaper/GtGhostHost.vue"
        assert index.inbound(host) == ("audit-platform/frontend/src/views/Page.vue",)
        real = F.frontend_reference_index()
        tag_only = [
            entry_host
            for entry_host in {
                item["source_host"]
                for item in [
                    entry["wp_match"]
                    for entry in json.loads(
                        _MANIFEST_PATH.read_text(encoding="utf-8")
                    )["entries"]
                ]
            }
            if not real.imports.get(entry_host) and real.tags.get(Path(entry_host).stem)
        ]
        assert tag_only == [], (
            "出现 tag-only 可达宿主 ⇒ 请把 mutate_task73 的 M09 改回模板标签边"
            f"（当前: {tag_only[:3]}）"
        )

    def test_editability_falls_back_to_the_component_prop_default(self) -> None:
        """组件默认值是真判据：把它翻成 true，同一宿主事实必须推出 readonly。"""
        sheet = F.component_source_facts(
            "GtOnlyOfficeSheet",
            "audit-platform/frontend/src/components/workpaper/GtOnlyOfficeSheet.vue",
        )
        assert sheet.readonly_default == "false" and sheet.editable_by_default is True
        host = F.HostSourceFacts(
            entry_id="probe", host_path="x.vue", document_type="xlsx",
            component="GtOnlyOfficeSheet", canonical_file=sheet.canonical_file,
            mount_count=1, dynamic_mount=False, readonly_binding="absent",
            readonly_refs=(), inbound_references=("host.vue",), endpoints=sheet.endpoints,
            client_local_doc_key=None,
        )
        assert F.derive_editability(host, sheet)[0] is EP.Editability.editable
        pinned = F.ComponentSourceFacts(
            component=sheet.component, canonical_file=sheet.canonical_file,
            readonly_default="true", editable_by_default=False,
            endpoints=sheet.endpoints, client_local_doc_key=None, source_refs=sheet.source_refs,
        )
        assert F.derive_editability(host, pinned)[0] is EP.Editability.readonly

    def test_missing_endpoint_facts_fail_closed(self) -> None:
        host = F.HostSourceFacts(
            entry_id="probe", host_path="x.vue", document_type="xlsx",
            component="GtOnlyOfficeSheet",
            canonical_file="audit-platform/frontend/src/components/workpaper/GtOnlyOfficeSheet.vue",
            mount_count=1, dynamic_mount=False, readonly_binding="absent", readonly_refs=(),
            inbound_references=("host.vue",), endpoints=(), client_local_doc_key=None,
        )
        with pytest.raises(F.EntrySourceFactError, match="端点字面量"):
            F.derive_room_model(host)


# ═══════════════════════════════════════════════════════════════════════════
# 5. RG-15/16/17 真的跑在真实 manifest 上，且能红能绿
# ═══════════════════════════════════════════════════════════════════════════


class TestCrossRulesRunAgainstTheRealManifest:
    def test_report_has_no_missing_profile_and_real_drift(
        self, manifest: dict[str, Any]
    ) -> None:
        """`report.profile_drift` 必须逐条等于**独立重算**的 RG-15/16/17 分层并集。

        🔴 本判据换过形状。原写法是
        `len(report.profile_drift) == len(_independent_reachable(manifest))`（142 条全红）
        —— 那个等式只在「RG-17 对每条 entry 都红」时成立，等于**把一个生产缺陷钉成了期望
        值**：Task 21 接线（doc_key 去 mtime + 逐用户 participant lease）之后它立刻变红，
        而变红的原因是缺陷被修好了。判据不能要求生产保持破损。

        现在期望值是**推导**出来的：`_layered_drift` 逐 entry 按 RG-15 → RG-16 → RG-17 的
        短路顺序取首个失败层，再与报告逐条（含原因消息逐字）比对。于是

        * 某一层从 `build_report` 里消失 / 多出一层 / 规则先后顺序变了 ⇒ 打红；
        * 某一层在真实数据上被修到清零（RG-17 今天就是 0 条）⇒ **不**打红。

        非空性不靠「有多少条红」，靠「评估了多少条 entry」—— 否则下游把 RG-15/16 也修完
        之后，这条判据又会变成「要求缺陷继续存在」。
        """
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest)
        report = registry.build_report(facts_observer=_observer)
        assert report.missing_profile == (), "Task 73 之后不应再有缺 profile 的 entry"

        reasons, layers, evaluated = _layered_drift(manifest)
        assert evaluated == len(_independent_reachable(manifest))
        assert evaluated >= 100, (
            f"只评估了 {evaluated} 条 entry ⇒ 判据被空集掏空（vacuous truth）"
        )

        assert len(set(report.profile_drift)) == len(report.profile_drift), (
            f"报告里有重复 entry_id（{len(report.profile_drift)} 条 / "
            f"{len(set(report.profile_drift))} 个唯一值）⇒ 下面的集合等式会把重复吞掉"
        )
        # 集合等式而非列表等式：本判据要锁的是「哪几条 entry 漂移」，不是 manifest 里
        # entry 的排列顺序。写成 `list(...) == sorted(...)` 会顺带把生成器的排序也钉住，
        # 换个排序就红 —— 那不是这条判据要防的缺陷。重复由上一条单独兜。
        assert set(report.profile_drift) == set(reasons), (
            "报告的漂移集合与独立重算的分层并集不符 —— 逐 entry 循环漏了 entry、某一层"
            f"没跑、或多跑了一层。报告 {len(report.profile_drift)} 条，重算 "
            f"{len(reasons)} 条（分层 "
            f"{ {name: len(bucket) for name, bucket in layers.items()} }）"
        )
        for entry_id, message in reasons.items():
            assert report.profile_drift_reasons[entry_id] == message, (
                f"{entry_id} 的首个漂移原因与重算不符 ⇒ 规则短路顺序变了"
            )
            assert entry_id in message, f"{entry_id} 的漂移原因没写出它自己是哪条 entry"
        assert set(report.profile_drift_reasons) == set(reasons)
        assert report.blocking_counts["profile_drift"] == len(report.profile_drift)

        # 上面的等式对 RG-15/16 有效（两层今天各有真实反例），但对 RG-17 失效：它已被
        # Task 21 清零，摘掉它报告也不会变。用合成的 mtime 耦合事实把这条覆盖补回来 ——
        # 判据因此不要求 RG-17 在真实数据上仍然红。
        reachable_ids = {entry["entry_id"] for entry in _independent_reachable(manifest)}
        mtime_report = registry.build_report(facts_observer=_mtime_coupled_observer)
        assert set(mtime_report.profile_drift) == reachable_ids, (
            "喂进 mtime 耦合的合成 room 事实后仍有 entry 不漂移 ⇒ RG-17 没被 build_report "
            "消费（它在真实数据上是 0 条，等式判据抓不到它消失）"
        )
        assert {
            entry_id
            for entry_id, message in mtime_report.profile_drift_reasons.items()
            if "mtime" in message
        } == reachable_ids - layers["rg15"], (
            "RG-17 的 mtime 分支没有恰好落在「先过了 RG-15」的那批 entry 上 ⇒ 分层短路"
            "顺序变了"
        )

    def test_rg15_fires_on_real_entries_whose_capability_contradicts_the_room_facts(
        self, manifest: dict[str, Any]
    ) -> None:
        """capability=single_html 却真的开着 OO room ⇒ 真实漂移（Requirement 1.5）。"""
        offenders = sorted(
            entry["entry_id"]
            for entry in _independent_reachable(manifest)
            if entry["capability"] == "single_html" and entry["room_model"] != "none"
        )
        assert offenders, "没有可用于验证 RG-15 的真实反例 ⇒ 本判据退化"
        for entry in manifest["entries"]:
            if entry["entry_id"] not in offenders:
                continue
            profile = EP.extract_entry_profile(entry)
            with pytest.raises(EP.EntryProfileDriftError, match="room_model"):
                EP.assert_profile_consistent_with_capability(
                    profile, EP.capability_of(entry)
                )

    def test_rg16_fires_where_a_single_capability_host_still_offers_both_modes(
        self, manifest: dict[str, Any]
    ) -> None:
        hit = 0
        for entry in _independent_reachable(manifest):
            descriptor = F.observe_descriptor_facts(entry)
            assert descriptor is not None
            if not descriptor.exposes_mode_switch:
                continue
            hit += 1
            with pytest.raises(EP.EntryProfileDriftError):
                EP.assert_profile_consistent_with_descriptor(
                    EP.extract_entry_profile(entry), EP.capability_of(entry), descriptor
                )
        assert hit, "没有 single capability + 仍显示切换 UI 的真实 entry ⇒ RG-16 无真实反例"

    def test_rg17_branches_are_alive_under_synthetic_non_conformant_facts(self) -> None:
        """RG-17 的每条分支都用**合成**的非合规 room 事实单独打一遍，消息必须可区分。

        🔴 本判据换过立论方向。原名 `test_rg17_exercises_two_distinct_branches_on_real_data`，
        断言真实 manifest **仍然**同时命中 mtime 耦合与缺 lease 两条分支 —— 那是在**要求
        生产保持破损**：Task 21 把两条都修好之后它必然红，而且除了把缺陷放回去，没有任何
        合法改法能让它绿。凡是形如「真实数据必须仍然表现出缺陷 X」的判据，都等价于
        「禁止修 X」。

        分支存活性改由合成事实证明：自己造 room 事实喂进
        `assert_profile_consistent_with_room`，每条分支必须抛出**只属于它自己**的判别串。
        这条判据与生产当前是否违规无关 —— 分支被删掉或被短路它才红。

        真实数据那一侧**不在这里重复实现**：`test_task21_room_service.py` 已有配对判据
        `test_rg17_is_clear_on_the_real_manifest`（逐 entry 跑 RG-17，`checked >= 100` 防
        vacuous truth）与 `test_rg17_still_reds_when_wiring_disappears`（把接线判据换空后
        必须红）。再抄第三份只会让「哪一份是真源」变模糊。本文件里 RG-17 与真实 manifest
        的接线由 `test_report_has_no_missing_profile_and_real_drift` 的合成 mtime 探针覆盖。
        """
        import ast

        # 控制组：合规事实必须**不**抛。没有它，下面几条 `raises` 在「函数无条件抛异常」
        # 时也会全绿。
        for room_model, room in (
            (
                EP.RoomModel.shared,
                EP.RoomFacts(
                    shared_doc_key=True, doc_key_includes_mtime=False, participant_lease=True
                ),
            ),
            (
                EP.RoomModel.exclusive,
                EP.RoomFacts(
                    shared_doc_key=False, doc_key_includes_mtime=False, participant_lease=True
                ),
            ),
            (
                EP.RoomModel.none,
                EP.RoomFacts(
                    shared_doc_key=False, doc_key_includes_mtime=False, participant_lease=False
                ),
            ),
        ):
            EP.assert_profile_consistent_with_room(_synthetic_profile(room_model), room)

        cases: tuple[tuple[str, EP.RoomModel, EP.RoomFacts, str], ...] = (
            (
                "mtime_coupled",
                EP.RoomModel.shared,
                EP.RoomFacts(
                    shared_doc_key=True, doc_key_includes_mtime=True, participant_lease=True
                ),
                "doc_key 仍包含文件 mtime",
            ),
            (
                "missing_lease",
                EP.RoomModel.shared,
                EP.RoomFacts(
                    shared_doc_key=True, doc_key_includes_mtime=False, participant_lease=False
                ),
                "要求逐用户 participant lease",
            ),
            (
                "none_but_room_exists",
                EP.RoomModel.none,
                EP.RoomFacts(
                    shared_doc_key=True, doc_key_includes_mtime=False, participant_lease=False
                ),
                "room_model=none 却存在",
            ),
            (
                "shared_without_shared_doc_key",
                EP.RoomModel.shared,
                EP.RoomFacts(
                    shared_doc_key=False, doc_key_includes_mtime=False, participant_lease=True
                ),
                "room_model=shared 要求 doc_key 与用户无关",
            ),
            (
                "exclusive_with_shared_doc_key",
                EP.RoomModel.exclusive,
                EP.RoomFacts(
                    shared_doc_key=True, doc_key_includes_mtime=False, participant_lease=True
                ),
                "room_model=exclusive 却使用共享 doc_key",
            ),
        )

        # 非空性：`cases` 被清空时下面每一条断言都会退化成 vacuous truth（空循环 +
        # `0 == 0`），本判据就成了永绿常量。下面还有一条 raise 站点数等式兜第二层。
        assert len(cases) >= 2, (
            f"只喂了 {len(cases)} 条合成事实 ⇒ 分支存活性判据被空集掏空"
        )

        messages: dict[str, str] = {}
        for name, room_model, room, marker in cases:
            profile = _synthetic_profile(room_model)
            with pytest.raises(
                EP.EntryProfileDriftError, match=re.escape(marker)
            ) as caught:
                EP.assert_profile_consistent_with_room(profile, room)
            messages[name] = str(caught.value)
            assert profile.entry_id in messages[name], (
                f"{name} 分支的消息没写出是哪条 entry ⇒ 报告里无法归因到具体入口"
            )

        # 判别串必须**独占**：`room_model=none 却存在 shared doc_key / participant lease`
        # 与「缺 lease」两条消息都含 `participant lease`，用裸子串会把两条分支混成一条，
        # 「哪条分支红了」的归因就串了（M18 那类踩坑）。
        for name, _room_model, _room, marker in cases:
            intruders = sorted(
                other for other, message in messages.items()
                if other != name and marker in message
            )
            assert not intruders, (
                f"{name} 的判别串 {marker!r} 也出现在 {intruders} 的消息里 ⇒ 分支不可区分"
            )
        assert len(set(messages.values())) == len(cases), "RG-17 分支消息不是两两不同"

        # 结构判据：新增分支必须同步补进 `cases`，否则新分支从第一天起就是没有判据的死代码。
        target = next(
            node
            for node in ast.walk(ast.parse(Path(EP.__file__).read_text(encoding="utf-8")))
            if isinstance(node, ast.FunctionDef)
            and node.name == "assert_profile_consistent_with_room"
        )
        raise_sites = [node for node in ast.walk(target) if isinstance(node, ast.Raise)]
        assert len(raise_sites) == len(cases), (
            f"`assert_profile_consistent_with_room` 有 {len(raise_sites)} 条 raise，本判据"
            f"只喂了 {len(cases)} 条合成事实 —— 逐条补齐，别放宽这个等式"
        )

    def test_drift_shrinks_to_the_rg15_layer_under_conformant_facts(
        self, manifest: dict[str, Any]
    ) -> None:
        """能红也要能绿：换一份合规实测事实，只应剩下 RG-15 那一层。

        没有这条，「142 条全红」就是个不可证伪的常量 —— 把三个 assert 换成 `raise` 也
        一样红。
        """
        def conformant(entry: dict[str, Any]) -> RG.ObservedEntryFacts:
            capability = EP.capability_of(entry)
            room_model = EP.RoomModel(entry["room_model"])
            return RG.ObservedEntryFacts(
                descriptor=EP.DescriptorFacts(
                    mode=EP.DescriptorMode(capability.value), exposes_mode_switch=False
                ),
                room=EP.RoomFacts(
                    shared_doc_key=room_model is EP.RoomModel.shared,
                    doc_key_includes_mtime=False,
                    participant_lease=room_model is not EP.RoomModel.none,
                ),
            )

        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest)
        observed = registry.build_report(facts_observer=_observer).profile_drift
        conformant_drift = registry.build_report(facts_observer=conformant).profile_drift
        capability_only = registry.build_report().profile_drift

        # RG-15 层必须真的被 build_report 消费（不是只有测试自己在调 EP.assert_*）：
        # 两侧独立现算，逐条比对。
        expected_rg15 = set()
        for entry in _independent_reachable(manifest):
            try:
                EP.assert_profile_consistent_with_capability(
                    EP.extract_entry_profile(entry), EP.capability_of(entry)
                )
            except EP.EntryProfileDriftError:
                expected_rg15.add(entry["entry_id"])
        assert expected_rg15, "没有 RG-15 真实反例 ⇒ 本判据退化"
        assert set(capability_only) == expected_rg15, (
            "build_report 没有把 RG-15 跑在真实 manifest 上"
        )
        assert set(conformant_drift) == expected_rg15
        assert set(conformant_drift) < set(observed), (
            "换成合规实测事实后漂移集合没有变小 ⇒ RG-16/17 的判据与实测事实无关"
        )

    def test_descriptor_is_absent_exactly_for_unreachable_hosts(
        self, manifest: dict[str, Any]
    ) -> None:
        for entry in manifest["entries"]:
            descriptor = F.observe_descriptor_facts(entry)
            reachable = entry["editability"] != "unreachable"
            assert (descriptor is not None) is reachable, entry["entry_id"]


# ═══════════════════════════════════════════════════════════════════════════
# 6. 闭合门接线（Requirement 1.8：可见且阻断）
# ═══════════════════════════════════════════════════════════════════════════


class TestClosureGateConsumesProfileDrift:
    def test_profile_drift_is_a_registered_blocking_fact(
        self, closure_gate: ModuleType, manifest: dict[str, Any]
    ) -> None:
        assert "registry_profile_drift" in closure_gate.REGISTRY_ISSUE_KEYS
        facts = closure_gate.build_registry_facts(manifest)
        assert set(facts) == set(closure_gate.REGISTRY_ISSUE_KEYS)
        assert facts["registry_missing_entry_profile"] == []
        assert facts["registry_profile_drift"], "闭合门看不到 profile 漂移 ⇒ 不阻断"
        # 行为判据：门必须拿到**实测**事实（RG-16/17 都跑），而不是只跑 manifest 自比的
        # RG-15。少传观察器时这里会从 142 掉到 5 条。
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=manifest)
        assert facts["registry_profile_drift"] == list(
            registry.build_report(facts_observer=_observer).profile_drift
        )

    def test_profile_drift_participates_in_the_blocking_total(
        self, closure_gate: ModuleType, manifest: dict[str, Any]
    ) -> None:
        baseline = json.loads(
            (_BACKEND / "data" / "workpaper_sync_legacy_baseline.json").read_text(
                encoding="utf-8"
            )
        )
        without = closure_gate.evaluate_closure(manifest, baseline)
        with_fact = closure_gate.evaluate_closure(
            manifest, baseline, {"registry_profile_drift": ["x/y"]}
        )
        assert without["registry_profile_drift"] == []
        assert with_fact["registry_profile_drift"] == ["x/y"]
        assert sum(len(v) for v in with_fact.values()) == (
            sum(len(v) for v in without.values()) + 1
        )

    def test_gate_passes_the_live_observer_not_a_stub(self) -> None:
        source = _CLOSURE_PATH.read_text(encoding="utf-8")
        body = re.sub(r"(?m)^\s*#.*$", "", source)
        assert "observe_descriptor_facts" in body and "observe_room_facts" in body
        assert "facts_observer=observer" in body, (
            "闭合门没把实测观察器传进 build_report ⇒ RG-16/17 仍是死代码"
        )

    def test_fact_collection_failure_fails_closed(self) -> None:
        body = _CLOSURE_PATH.read_text(encoding="utf-8")
        assert "cannot observe source-backed entry facts" in body
        assert "return {}" not in body


# ═══════════════════════════════════════════════════════════════════════════
# 7. 生成器侧 fail-closed（缺字段 / 复核期望 / 可达性裁决）
# ═══════════════════════════════════════════════════════════════════════════


class TestGeneratorFailsClosed:
    def test_required_entry_fields_cover_the_three_profile_fields(
        self, generator: ModuleType
    ) -> None:
        assert set(EP.PROFILE_KEYS) | {"profile_source"} <= generator._REQUIRED_ENTRY_FIELDS

    def test_a_dropped_profile_field_is_rejected(
        self,
        generator: ModuleType,
        discovery: dict[str, Any],
        overlay: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`_REQUIRED_ENTRY_FIELDS` 必须真的拦住缺字段，而不只是一个好看的集合。"""
        original = generator._facts.derive_entry_profile

        def lossy(host: Any, component: Any = None) -> Any:
            derived = original(host, component)
            fields = derived.as_entry_fields()
            fields.pop("room_model")
            return _StubDerived(fields, derived)

        monkeypatch.setattr(generator._facts, "derive_entry_profile", lossy)
        with pytest.raises(generator.ManifestGenerationError, match="misses fields"):
            generator.build_manifest(discovery, overlay)

    def test_reviewed_expectation_mismatch_is_rejected(
        self, generator: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        twisted = copy.deepcopy(overlay)
        twisted["defaults_by_component"]["GtOnlyOfficeSheet"]["expected_profile"]["editability"] = [
            "readonly"
        ]
        # 🔴 必须匹配**不符**这条判据自己的措辞，不能只 match "editability"：任何写错的
        # 复核值同时也是「过期值」，`stale reviewed expected_profile.editability` 会顶上来
        # 让判据看起来通过（变异检验实测判 GREEN 才发现）。
        with pytest.raises(generator.ManifestGenerationError, match="source facts derive"):
            generator.build_manifest(discovery, twisted)

    def test_stale_reviewed_expectation_is_rejected(
        self, generator: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        twisted = copy.deepcopy(overlay)
        twisted["defaults_by_component"]["GtOnlyOfficeSheet"]["expected_profile"][
            "scenario_profile_ids"
        ].append("xlsx.editable.shared.dynamic.pending_room_service.v1")
        with pytest.raises(generator.ManifestGenerationError, match="stale reviewed"):
            generator.build_manifest(discovery, twisted)

    def test_missing_expected_profile_is_rejected(
        self, generator: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        twisted = copy.deepcopy(overlay)
        twisted["defaults_by_component"]["GtOnlyOfficeSheet"].pop("expected_profile")
        with pytest.raises(generator.ManifestGenerationError, match="expected_profile"):
            generator.build_manifest(discovery, twisted)

    def test_reachability_and_reviewed_unreachable_rule_must_agree(
        self, generator: ModuleType, discovery: dict[str, Any], overlay: dict[str, Any]
    ) -> None:
        """删掉 reviewed 不可达规则 ⇒ 源码入边事实与裁决冲突，必须 fail closed。"""
        twisted = copy.deepcopy(overlay)
        twisted["unreachable_rules"] = []
        with pytest.raises(generator.ManifestGenerationError, match="inbound references"):
            generator.build_manifest(discovery, twisted)

    def test_generated_frontend_projection_carries_the_profile(
        self, manifest: dict[str, Any]
    ) -> None:
        text = _FRONTEND_PROJECTION.read_text(encoding="utf-8")
        match = re.search(
            r"export const WORKPAPER_SYNC_MANIFEST = (\[[\s\S]*?\]) as const", text
        )
        assert match, "未能从生成的 TS 里取出投影数组"
        projected = json.loads(match.group(1))
        assert len(projected) == len(manifest["entries"])
        by_id = {entry["entry_id"]: entry for entry in manifest["entries"]}
        for row in projected:
            entry = by_id[row["entryId"]]
            assert row["editability"] == entry["editability"]
            assert row["roomModel"] == entry["room_model"]
            assert row["scenarioProfileId"] == entry["scenario_profile"]["profile_id"]
            assert row["roomServiceState"] == entry["scenario_profile"]["room_service_state"]
            assert "editable" not in row


class _StubDerived:
    """只用于「缺字段必须 fail closed」判据：故意少给一个 entry 字段。"""

    def __init__(self, fields: dict[str, Any], real: Any) -> None:
        self._fields = fields
        self.editability = real.editability
        self.room_model = real.room_model
        self.scenario_profile = real.scenario_profile
        self.profile_source = real.profile_source
        self.scenario_profile_id = real.scenario_profile_id
        self.scenario_profile_digest = real.scenario_profile_digest

    def as_entry_fields(self) -> dict[str, Any]:
        return dict(self._fields)
