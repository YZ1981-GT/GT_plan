"""Task 21 离线守卫：doc_key/mtime 解耦、契约唯一消费方、冻结身份与双基线纯判据。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 21
Requirements: 2.5, 2.6, 2.7, 2.8, 2.9, 4.7, 4.11, 10.2, 10.3, 10.4, 10.9, 10.10
Properties: P6 / P15 / P43 / P44 / P62 / P63

═══ 这个文件为什么不连库 ═══

Task 21 的判据分两类：
* **纯判据**（doc_key 派生、契约解析、identity digest、真值表唯一消费方）—— 本文件；
* **并发/事务判据**（room lock 内的 fence 提升、outstanding request 取消、双基线原子
  推进）—— `test_task21_room_service_pg.py`，那些必须真库。

把纯判据也塞进 PG 文件会让「改一行 doc_key 格式」要跑一次完整迁移才知道红没红，
反过来把并发判据放这里则等于用 mock 抹掉唯一判据。

═══ 反向自检 ═══

每条「禁止出现」的守卫都配一条**正向断言**证明判据真的在看东西：
* `test_doc_key_probe_ast_check_follows_helper_calls` 真的构造一个「helper 读 mtime」
  的模块并断言 AST 检查打红 —— 否则 `_doc_key_source_is_mtime_free()` 可能只是恒真；
* `test_contract_numbers_have_single_source` 先断言 `oo_contract` 里**存在**这些数值，
  再断言别处没有 —— 否则「别处没有」在数值被全删时也成立。
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import rooms as rooms_mod  # noqa: E402
from app.services.workpaper_sync.entry_profile import (  # noqa: E402
    Editability,
    EntryProfile,
    EntryProfileDriftError,
    RoomFacts,
    RoomModel,
    ScenarioProfile,
    assert_profile_consistent_with_room,
)
from app.services.workpaper_sync.models import (  # noqa: E402
    AuthorityModel,
    BundleSlot,
    BundleSlotSpec,
    ContributorConfidence,
    ContributorSource,
    IdentityError,
    ParticipantState,
    RequestKind,
    RoomState,
    compute_bundle_slots_digest,
    compute_contributor_snapshot_digest,
)
from app.services.workpaper_sync.oo_contract import (  # noqa: E402
    CALLBACK_CONTRACT_PATH,
    CallbackContractError,
    Presence,
    UnknownCallbackStatusError,
    load_callback_contract,
)
from app.services.workpaper_sync.rooms import (  # noqa: E402
    DOC_KEY_PREFIX,
    DocKeyError,
    FrozenBundleIdentity,
    BundleIdentityDriftError,
    RoomBaselines,
    RouteCredential,
    RouteCredentialError,
    assert_route_credential,
    derive_doc_key,
    doc_key_matches,
    mint_route_credential,
    parse_doc_key,
    probe_room_facts,
)

_ROOMS_PATH = Path(rooms_mod.__file__)


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# 1. doc_key 与 mtime 解耦（Property 6 / AC 2.7）
# ═══════════════════════════════════════════════════════════════════════════


class TestDocKeyIsMtimeFree:
    def test_probe_reports_mtime_free_and_really_changed_mtime(self, tmp_path: Path) -> None:
        """探针必须**真的**改了 mtime 才算证明了「与 mtime 无关」。"""
        probe = probe_room_facts(tmp_path=tmp_path)
        assert probe.mtime_after != probe.mtime_before, (
            "探针没能真的改掉 mtime ⇒ 「doc_key 与 mtime 解耦」这条根本没被验证过，"
            "这是假绿：判据看起来通过，实际上两次派生的输入条件完全相同"
        )
        assert probe.doc_key_stable_across_mtime_change is True
        assert probe.doc_key_source_is_mtime_free is True
        assert probe.doc_key_rotates_with_generation is True
        assert probe.doc_key_includes_mtime is False

    def test_probe_facts_pass_registry_room_gate(self, tmp_path: Path) -> None:
        """RG-17：room service 的实测事实必须让 registry 的 room 门通过。

        这条门在 Task 13 就写好了，诊断文本明写「须先由 Task 21 的 room service 取代」。
        它是 Task 21 是否真的兑现的**唯一外部判据**。
        """
        probe = probe_room_facts(tmp_path=tmp_path)
        facts = RoomFacts(
            shared_doc_key=probe.doc_key_stable_across_users,
            doc_key_includes_mtime=probe.doc_key_includes_mtime,
            participant_lease=probe.lease_is_per_participant,
        )
        profile = EntryProfile(
            entry_id="xlsx/gt-d2-accounts-receivable",
            editability=Editability.editable,
            room_model=RoomModel.shared,
            scenario_profile=ScenarioProfile("excel_dynamic_table", {"profile_id": "x"}),
        )
        assert_profile_consistent_with_room(profile, facts)

    def test_registry_room_gate_still_rejects_mtime_doc_key(self) -> None:
        """反向自检：门本身没坏 —— 事实为真时仍必须打红。"""
        facts = RoomFacts(
            shared_doc_key=True, doc_key_includes_mtime=True, participant_lease=True
        )
        profile = EntryProfile(
            entry_id="e",
            editability=Editability.editable,
            room_model=RoomModel.shared,
            scenario_profile=ScenarioProfile("p", {"profile_id": "p"}),
        )
        with pytest.raises(EntryProfileDriftError):
            assert_profile_consistent_with_room(profile, facts)

    def test_doc_key_shape_and_roundtrip(self) -> None:
        wp = uuid.uuid4()
        key = derive_doc_key(wp_id=wp, entry_id="xlsx/gt-g7-equity-method", generation=7)
        assert key.startswith(f"{DOC_KEY_PREFIX}-")
        assert len(key) <= 150, "doc_key 必须能落进 working_paper_oo_room.doc_key(150)"
        digest, generation = parse_doc_key(key)  # type: ignore[misc]
        assert generation == 7
        assert digest == hashlib.sha256(
            f"{wp}|xlsx/gt-g7-equity-method".encode("utf-8")
        ).hexdigest()[:24]
        assert doc_key_matches(
            doc_key=key, wp_id=wp, entry_id="xlsx/gt-g7-equity-method"
        )

    def test_same_wp_entry_generation_is_shared_across_users(self) -> None:
        """AC 2.6：同 generation 的两个用户必须进同一 room（同 doc_key）。"""
        wp, entry = uuid.uuid4(), "xlsx/gt-h1-fixed-assets"
        assert derive_doc_key(wp_id=wp, entry_id=entry, generation=1) == derive_doc_key(
            wp_id=wp, entry_id=entry, generation=1
        )

    def test_generation_rotation_rotates_doc_key(self) -> None:
        """AC 2.8：发布新 generation 必须 supersede 旧 room ⇒ key 必须变。"""
        wp, entry = uuid.uuid4(), "xlsx/gt-h1-fixed-assets"
        keys = {derive_doc_key(wp_id=wp, entry_id=entry, generation=g) for g in (1, 2, 3)}
        assert len(keys) == 3

    def test_different_entries_of_same_wp_get_different_rooms(self) -> None:
        wp = uuid.uuid4()
        a = derive_doc_key(wp_id=wp, entry_id="entry/a", generation=1)
        b = derive_doc_key(wp_id=wp, entry_id="entry/b", generation=1)
        assert a != b, "同底稿的两个独立入口必须各自成 room，否则互相踢下线"

    @pytest.mark.parametrize("generation", [0, -1, True, "2", 1.0, None])
    def test_invalid_generation_fails_closed(self, generation: object) -> None:
        with pytest.raises(DocKeyError):
            derive_doc_key(wp_id=uuid.uuid4(), entry_id="e", generation=generation)  # type: ignore[arg-type]

    @pytest.mark.parametrize("entry", ["", "   ", None])
    def test_blank_entry_fails_closed(self, entry: object) -> None:
        with pytest.raises(DocKeyError):
            derive_doc_key(wp_id=uuid.uuid4(), entry_id=entry, generation=1)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "foreign",
        [
            "deliverable-3f0a5f7e-1c4f-4f36-9f0b-6f4d2c1a7b8e-2",  # 交付中心域
            "wpsync-XYZ-g1",  # 非 hex
            "wpsync-961326afaf83e4866c3895a2-g0",  # generation 0
            "wpsync-961326afaf83e4866c3895a2",  # 缺 generation
            "",
            None,
        ],
    )
    def test_parse_rejects_foreign_or_malformed_keys(self, foreign: object) -> None:
        assert parse_doc_key(foreign) is None  # type: ignore[arg-type]

    def test_ast_check_catches_mtime_read_via_helper(self, tmp_path: Path) -> None:
        """反向自检：AST 检查必须能跟到 helper 里（不是恒真）。

        直接构造一段「`derive_doc_key` 调用 `_bad_helper()`，helper 读 st_mtime_ns」的
        源码，用同一套遍历逻辑判定，必须判红。若这条断言过不去，说明
        `_doc_key_source_is_mtime_free()` 的传递闭包是装饰性的。
        """
        source = (
            "def _bad_helper(p):\n"
            "    return p.stat().st_mtime_ns\n"
            "def derive_doc_key(*, wp_id, entry_id, generation):\n"
            "    return f'{wp_id}-{_bad_helper(entry_id)}'\n"
            "def parse_doc_key(k):\n    return None\n"
            "def doc_key_matches(**kw):\n    return False\n"
        )
        assert _simulate_mtime_free_check(source) is False, (
            "AST 检查没能跟随 helper 调用 ⇒ 有人把 mtime 读取挪进 helper 就能绕过判据"
        )
        clean = (
            "import hashlib\n"
            "def derive_doc_key(*, wp_id, entry_id, generation):\n"
            "    return hashlib.sha256(f'{wp_id}|{entry_id}'.encode()).hexdigest()\n"
            "def parse_doc_key(k):\n    return None\n"
            "def doc_key_matches(**kw):\n    return False\n"
        )
        assert _simulate_mtime_free_check(clean) is True, "干净源码必须判绿（否则恒假）"

    def test_ast_check_fails_when_entry_functions_renamed(self) -> None:
        """入口函数被改名/删除时判据必须失效打红，而不是「找不到就算通过」。"""
        source = "def something_else():\n    return 1\n"
        assert _simulate_mtime_free_check(source) is False

    def test_entry_function_list_is_not_empty(self) -> None:
        """入口清单不得为空 —— 空清单会让 AST 检查变成 vacuous truth。

        `len(pending) != len(entries)` 在两边都是 0 时成立不了，循环一次都不进，
        于是恒返回 True。清空一个常量元组是最不起眼的一行改动，必须有独立判据。
        """
        assert rooms_mod._DOC_KEY_ENTRY_FUNCTIONS, "doc_key 入口清单不得为空"
        assert set(rooms_mod._DOC_KEY_ENTRY_FUNCTIONS) == {
            "derive_doc_key",
            "parse_doc_key",
            "doc_key_matches",
        }
        assert rooms_mod._doc_key_source_is_mtime_free() is True

    def test_empty_entry_list_makes_the_check_fail_not_pass(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """反向自检：把入口清单换空时，检查必须返回 False。

        这条与上一条是两件事：上一条断言「清单现在非空」，本条断言「清单为空时防线
        真的生效」。只有前者时，删掉那道 `if not _DOC_KEY_ENTRY_FUNCTIONS: return False`
        防线是**完全不可观测**的（清单仍非空，行为不变）—— 首轮变异实测判 GREEN。
        """
        monkeypatch.setattr(rooms_mod, "_DOC_KEY_ENTRY_FUNCTIONS", ())
        assert rooms_mod._doc_key_source_is_mtime_free() is False, (
            "入口清单为空时判据必须失效打红，而不是因为循环一次都不进而恒真"
        )

    def test_production_routers_no_longer_derive_doc_key_from_mtime(self) -> None:
        """生产 `onlyoffice-config` 路由不得再从文件 mtime 派生 doc_key（AC 2.7 / P6）。

        这条替代了原来的 characterization（「旧 `md5(wp_code + st_mtime_ns)` 还在」）：
        Task 21 已把两个 config 端点接到 room 身份上，design §wp_onlyoffice_router 要求
        `_generate_doc_key` **删除且不留 fallback**。

        判据落在 **doc_key 赋值表达式**上而不是整文件搜 `st_mtime`：路由里仍有正当的
        mtime 使用（sheet 可见性幂等短路的注释与判断），整文件搜会把它判红，接着人就会
        去放宽判据。表达式由 `entry_source_facts._doc_key_expression()` 提取 —— 复用生产
        提取器而不是在测试里抄一份正则，否则提取逻辑改了这里也不会红。
        """
        from app.services.workpaper_sync import entry_source_facts as facts

        facts.doc_key_providers.cache_clear()
        providers = facts.doc_key_providers()
        assert providers, "一条 onlyoffice-config 路由都没扫到 ⇒ 判据恒空（假绿）"
        for endpoint, provider in providers.items():
            assert provider.includes_mtime is False, (
                f"{endpoint} 的 doc_key 仍含 mtime（{provider.source_ref}）："
                f"{provider.doc_key_expression!r}"
            )
            assert provider.includes_user is False, (
                f"{endpoint} 的 doc_key 含用户成分 ⇒ 不是 shared room（AC 2.6）"
            )
        legacy = _BACKEND / "app" / "routers" / "wp_onlyoffice_router.py"
        if legacy.exists():
            tree = ast.parse(legacy.read_text(encoding="utf-8"))
            defined = {
                node.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            assert "_generate_doc_key" not in defined, (
                "`_generate_doc_key` 仍有定义 —— design 要求删除且不留 fallback；"
                "留着它意味着某个分支还能退回 mtime 语义"
            )

    def test_room_service_is_wired_into_production_outside_the_package(self) -> None:
        """room service 必须在 `workpaper_sync` 之外**真的被调用**（RG-17 的 lease 侧）。

        `entry_source_facts.room_service_wiring()` 是这件事的机器可读判据；它为空时
        `observe_room_facts().participant_lease` 恒 False，RG-17 全量必红。

        只断言「清单非空」是不够的 —— 一个 `import` 就能让它非空，而 import 不是接线
        （additive 死代码，假绿第①源）。所以再加一条：接线模块里的 doc_key 解析函数
        必须被 **router** 调用，且 router 侧的调用点在 AST 上可见。
        """
        from app.services.workpaper_sync import entry_source_facts as facts

        facts.room_service_wiring.cache_clear()
        wiring = facts.room_service_wiring()
        assert wiring, (
            "room service 在 workpaper_sync 之外零调用点 ⇒ 它是死代码，"
            "RG-17 的 participant lease 门必然全量打红"
        )
        seam = _BACKEND / "app" / "services" / "onlyoffice_room_identity.py"
        assert seam.exists(), "接线 seam 模块缺失"
        assert any("onlyoffice_room_identity" in hit for hit in wiring), (
            f"接线点不在 seam 模块里：{wiring}"
        )
        callers = []
        for name in ("wp_onlyoffice_router.py", "wp_editor_router.py"):
            path = _BACKEND / "app" / "routers" / name
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                attr = getattr(func, "attr", None)
                if attr == "resolve_room_doc_key":
                    callers.append(name)
        assert set(callers) == {"wp_onlyoffice_router.py", "wp_editor_router.py"}, (
            "两个 onlyoffice-config 路由必须都调 `resolve_room_doc_key`；"
            f"实测调用方 = {sorted(set(callers))}"
        )

    def test_seam_doc_key_is_behaviourally_immune_to_mtime(self, tmp_path: Path) -> None:
        """**真执行**：改一个真实文件的 mtime，seam 派生的 doc_key 必须逐字节不变。

        这是与 `probe_room_facts()` 互补的一条：那条探针跑的是 `derive_doc_key`，本条
        跑的是 **router 实际调用的那个函数**（`sheet_entry_id` + 派生），因此能抓到
        「seam 自己偷偷把文件状态混进 entry_id」这种接线层回归。

        不连库：`resolve_room_doc_key` 在无 room 时走基线代际分支，本条只验派生部分，
        room 复用分支由 PG 守卫覆盖。
        """
        from app.services import onlyoffice_room_identity as seam

        witness = tmp_path / "shared_workbook.xlsx"
        witness.write_bytes(b"workbook")
        wp_id = uuid.uuid4()
        entry_id = seam.sheet_entry_id(
            wp_code="D4-5", sheet_name="营业收入会计政策检查D4-5", whole_workbook=False
        )
        before_mtime = witness.stat().st_mtime_ns
        before = derive_doc_key(
            wp_id=wp_id, entry_id=entry_id, generation=seam.BASELINE_GENERATION
        )
        os.utime(witness, ns=(before_mtime + 1_000_000_000, before_mtime + 1_000_000_000))
        after_mtime = witness.stat().st_mtime_ns
        after = derive_doc_key(
            wp_id=wp_id, entry_id=entry_id, generation=seam.BASELINE_GENERATION
        )
        assert after_mtime != before_mtime, (
            "探针没能真的改掉 mtime ⇒ 本条根本没验证任何东西（假绿）"
        )
        assert after == before

    def test_seam_entry_id_separates_sheet_whole_workbook_and_word(self) -> None:
        """entry_id 必须区分「单 sheet / 整册 / Word 模板」三种视图。

        撞在一起的后果很具体：整册视图与单 sheet 视图共享 doc_key 时，OO 会把缓存的
        单 sheet 副本（其余 sheet 已被 openpyxl 隐藏）当成「完整 Excel」返回给用户。
        """
        from app.services import onlyoffice_room_identity as seam

        wp_id = uuid.uuid4()
        single = seam.sheet_entry_id(wp_code="G1", sheet_name="G1-1", whole_workbook=False)
        whole = seam.sheet_entry_id(wp_code="G1", sheet_name="G1-1", whole_workbook=True)
        other_sheet = seam.sheet_entry_id(
            wp_code="G1", sheet_name="G1-2", whole_workbook=False
        )
        word = seam.word_template_entry_id(wp_id=wp_id)
        assert len({single, whole, other_sheet, word}) == 4, (
            f"四个视图必须是四个 room 身份，实得 {[single, whole, other_sheet, word]}"
        )
        keys = {
            derive_doc_key(wp_id=wp_id, entry_id=entry, generation=1)
            for entry in (single, whole, other_sheet, word)
        }
        assert len(keys) == 4, "四个 entry_id 却派生出重复 doc_key"
        with pytest.raises(ValueError):
            seam.sheet_entry_id(wp_code="", sheet_name="x", whole_workbook=False)
        with pytest.raises(ValueError):
            seam.sheet_entry_id(wp_code="G1", sheet_name="  ", whole_workbook=False)

    def test_seam_does_not_use_file_version_or_prefill_state(self) -> None:
        """Word 端点的文档身份不得含 `file_version` 或「预填/未预填」。

        `file_version` 被 Requirement 2.1 明文禁止充当跨通道同步版本；`prefilled` 是展示
        态，进 doc_key 会让同一份文件在两个房间里被并行编辑。

        判据同样落在**赋值表达式**上，用生产提取器取，不整文件 grep（router 里别处
        正当使用 `wp.file_version` 签下载 token，整文件 grep 会误伤）。
        """
        from app.services.workpaper_sync import entry_source_facts as facts

        facts.doc_key_providers.cache_clear()
        providers = facts.doc_key_providers()
        target = "/api/projects/*/working-papers/*/onlyoffice-config"
        assert target in providers, f"Word 端点未被扫到：{sorted(providers)}"
        expression = providers[target].doc_key_expression
        for token in ("file_version", "prefilled", "'pf'", '"pf"'):
            assert token not in expression, (
                f"Word 端点 doc_key 表达式仍含 {token!r}：{expression!r}"
            )

    def test_rg17_is_clear_on_the_real_manifest(self) -> None:
        """RG-17 在**真实 manifest** 上必须零红（Task 73 留给 Task 21 的外部判据）。

        Task 73 的 tasks 正文写明「Task 21 room service 未接线，故 RG-17 全量必红 ——
        有意驻留」。本条是那笔欠账的收口：逐 entry 跑 `assert_profile_consistent_with_room`
        并要求 room 层零失败。

        刻意**只**统计 RG-17：同一份 manifest 上 RG-15/RG-16 仍有既存漂移（capability
        与 descriptor 的业务裁决欠账，分别属 Task 31/33 与 capability 复核），把它们一起
        断言成 0 会让本条永远红，接着人就会把整条判据删掉。
        """
        from app.services.workpaper_sync import entry_profile as ep
        from app.services.workpaper_sync import entry_source_facts as facts

        facts.doc_key_providers.cache_clear()
        facts.room_service_wiring.cache_clear()
        manifest = ep.load_entry_manifest()
        checked = 0
        failures: list[str] = []
        for entry in manifest["entries"]:
            if not entry.get("independent_entry"):
                continue
            capability = ep.capability_of(entry)
            if capability is ep.Capability.unreachable:
                continue
            profile = ep.extract_entry_profile(entry)
            room = facts.observe_room_facts(entry)
            checked += 1
            try:
                assert_profile_consistent_with_room(profile, room)
            except EntryProfileDriftError as exc:
                failures.append(f'{entry["entry_id"]}: {exc}')
        assert checked >= 100, f"只检查了 {checked} 条 entry ⇒ 判据被掏空（vacuous truth）"
        assert failures == [], (
            f"RG-17 仍有 {len(failures)} 条红：{failures[:3]}"
        )

    def test_rg17_still_reds_when_wiring_disappears(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """反向自检：把接线判据换空时，上一条必须变红。

        没有这条，`test_rg17_is_clear_on_the_real_manifest` 可能只是因为 `observe_room_facts`
        恒返回合规事实而通过 —— 那就是「守卫把声明当事实」。
        """
        from app.services.workpaper_sync import entry_profile as ep
        from app.services.workpaper_sync import entry_source_facts as facts

        monkeypatch.setattr(facts, "room_service_wiring", lambda: ())
        manifest = ep.load_entry_manifest()
        entry = next(
            item
            for item in manifest["entries"]
            if item.get("independent_entry")
            and ep.capability_of(item) is not ep.Capability.unreachable
            and str(item.get("room_model")) != "none"
        )
        profile = ep.extract_entry_profile(entry)
        room = facts.observe_room_facts(entry)
        assert room.participant_lease is False
        with pytest.raises(EntryProfileDriftError, match="participant lease"):
            assert_profile_consistent_with_room(profile, room)

    def test_room_service_does_not_import_legacy_doc_key_generator(self) -> None:
        """新 room service 不得复用旧 router 的 doc_key 生成（否则等于没换）。"""
        text = _ROOMS_PATH.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names]
                module = getattr(node, "module", "") or ""
                assert "wp_onlyoffice_router" not in module, module
                assert "_generate_doc_key" not in names, names


def _simulate_mtime_free_check(source: str) -> bool:
    """用与 `_doc_key_source_is_mtime_free` 相同的遍历逻辑判定任意源码。

    刻意**复用**被测模块的常量与入口清单，而不是在测试里抄一份规则：抄一份就变成
    「测试验证测试」，生产实现改了判据这里也不会红。
    """
    forbidden = rooms_mod._MTIME_FORBIDDEN_ATTRS
    entries = rooms_mod._DOC_KEY_ENTRY_FUNCTIONS
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if not entries:
        return False
    pending = [name for name in entries if name in functions]
    if len(pending) != len(entries):
        return False
    visited: set[str] = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        for node in ast.walk(functions[name]):
            if isinstance(node, ast.Attribute) and node.attr in forbidden:
                return False
            if isinstance(node, ast.Name) and node.id in forbidden:
                return False
            if isinstance(node, ast.Call):
                callee = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                if callee in {"stat", "lstat", "getmtime", "getctime", "utime"}:
                    return False
                if callee in functions and callee not in visited:
                    pending.append(callee)
    return True


# ═══════════════════════════════════════════════════════════════════════════
# 2. Task 4 真值表：生产侧唯一消费方（消灭 additive 死代码）
# ═══════════════════════════════════════════════════════════════════════════


class TestCallbackContractHasProductionConsumer:
    def test_contract_loads_and_is_versioned(self) -> None:
        contract = load_callback_contract()
        assert contract.schema_version == 1
        assert contract.known_statuses == (1, 2, 3, 4, 6, 7)
        assert contract.jwt.claim_schema_version == 1
        assert contract.jwt.claim_constants["cbv"] == 1

    @pytest.mark.parametrize("bad", [5, 0, -1, "6", True, None, 6.0, [6]])
    def test_unknown_status_fails_visible(self, bad: object) -> None:
        """Requirement 4.9：未知 status 抛专属异常，绝不「按最近似 status 猜」。"""
        with pytest.raises(UnknownCallbackStatusError):
            load_callback_contract().status_rule(bad)

    def test_status_2_carries_no_userdata_and_needs_close_capture(self) -> None:
        """实证：status 2 恒无 userdata ⇒ 必须靠 close-capture 仲裁定位 request。"""
        rule = load_callback_contract().status_rule(2)
        assert rule.userdata_present is Presence.never
        assert rule.may_carry_userdata is False
        assert rule.download_required is True
        assert rule.application_allowed is True
        assert "close_capture" in rule.request_correlation

    def test_status_6_userdata_is_optional_not_guaranteed(self) -> None:
        rule = load_callback_contract().status_rule(6)
        assert rule.userdata_present is Presence.optional
        assert rule.may_carry_userdata is True

    def test_status_1_and_4_never_download_and_never_apply(self) -> None:
        contract = load_callback_contract()
        for status in (1, 4):
            rule = contract.status_rule(status)
            assert rule.download_required is False
            assert rule.application_allowed is False

    def test_revocation_decision_forces_generation_rotation(self) -> None:
        """Property 63：drop 不证明内容已移除 ⇒ 必须 fence + 旋转 generation。"""
        rev = load_callback_contract().multi_user.revocation
        assert rev.requires_generation_rotation is True
        assert "已合入内容被移除" in "".join(rev.oo_drop_does_not_prove)

    def test_service_reads_the_revocation_decision_from_the_contract(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`revocation_policy()` 必须**真的**从契约读，而不是返回硬编码对象。

        判据形态：把 loader 换成返回「另一个裁决」的替身，`revocation_policy()` 必须
        跟着变。只断言「当前值是 rotation」的话，把这段换成硬编码同值对象是完全不可
        观测的（结构、调用点、日志全都不变）—— 而那正好让真值表退回「只有守卫在读」
        的死代码状态，契约被改回 participant-bound 时生产行为不再 fail closed。
        """
        from app.services.workpaper_sync import oo_contract as oc

        real = load_callback_contract()
        patched_rev = oc.RevocationPolicy(
            decision="participant_bound_selective_apply",
            oo_drop_proves=("patched",),
            oo_drop_does_not_prove=("patched",),
        )
        patched_mu = oc.MultiUserSemantics(
            callback_scope=real.multi_user.callback_scope,
            users_field_semantics=real.multi_user.users_field_semantics,
            contributor_snapshot_source=real.multi_user.contributor_snapshot_source,
            participant_bound_authorization_allowed=False,
            revocation=patched_rev,
        )
        patched = oc.CallbackContract(
            schema_version=real.schema_version,
            statuses=real.statuses,
            unknown_status_policy=real.unknown_status_policy,
            timers=real.timers,
            jwt=real.jwt,
            download=real.download,
            multi_user=patched_mu,
            correlation=real.correlation,
        )
        monkeypatch.setattr(rooms_mod, "load_callback_contract", lambda: patched)
        observed = rooms_mod.revocation_policy()
        assert observed.decision == "participant_bound_selective_apply", (
            "撤销裁决没有跟随契约变化 ⇒ 它是硬编码的，Task 4 的实证真值表在生产侧没有"
            "消费方"
        )
        assert observed.requires_generation_rotation is False

    def test_normalize_callback_status_never_coerces(self) -> None:
        """归一化只认严格 int —— `int("6")` / `int(6.0)` 这类猜测必须不存在。

        与 `test_unknown_status_fails_visible` 分工：那条测「未知会抛」，本条测
        「归一化本身不做隐式转换」。少了本条时，把归一化改成 `int(status)` 只会让
        `"6"` 变成合法 6（不抛异常），而「抛异常」那条测试用的是 5/0/-1 这类真未登记值，
        照样绿 —— 首轮变异实测正是这条空白。
        """
        from app.services.workpaper_sync.oo_contract import normalize_callback_status

        assert normalize_callback_status(6) == 6
        assert normalize_callback_status(0) == 0
        for raw in ("6", 6.0, True, False, None, [6], {"status": 6}, b"6"):
            assert normalize_callback_status(raw) is None, (
                f"{raw!r} 被归一化成了整数 ⇒ 契约 unknown_status_policy.forbidden[1]"
                "「按最近似 status 猜测处理」被违反"
            )

    def test_participant_bound_callback_authorization_is_refused(self) -> None:
        assert (
            load_callback_contract().multi_user.participant_bound_authorization_allowed
            is False
        )

    def test_application_key_excludes_status_delivery_key_includes_it(self) -> None:
        cor = load_callback_contract().correlation
        assert "callback_status" in cor.delivery_key_components
        assert "callback_status" not in cor.application_key_components
        assert "callback_status" in cor.application_key_forbidden_components

    def test_contract_numbers_have_single_source_in_oo_contract(self) -> None:
        """契约数值的唯一真源是契约 JSON，代码只许经 `oo_contract` **读**（timers.notes[0]）。

        三段断言合起来才有意义：先证明这些数值**真的**从契约读到了（否则「别处没有」在
        数值被全删时也成立），再分别否掉「另写常量」与「另写一份 JSON 解析」两种分叉。

        ## 🔴 判据形态为什么改了（Task 30 独立门实测）

        原判据是「剥注释/字符串后，模块正文里出现子串 `forcesave_callback_wait_timeout_seconds`
        即算自写」。`_strip_comments_and_strings` 会把**全部**字符串常量抹白，所以那个子串
        在剥完之后**只可能**以标识符形态存活 —— 也就是
        `timers.forcesave_callback_wait_timeout_seconds` 这种**从契约对象上读字段**的形态，
        而那恰恰是 notes[0] 要求的正确做法。反过来，真正的分叉
        （`FORCESAVE_CALLBACK_WAIT_TIMEOUT_SECONDS = 120` 这类自写常量）里没有那个子串，
        数值 `120` 也不在被扫的名单里 ⇒ **原判据只能打红正确行为、且必然漏掉真缺陷**。

        实测：`command_service.classify_editor_destroy(timers=…)` 把契约对象当入参、读
        `timers.forcesave_callback_wait_timeout_seconds` 判超时，被原判据点名；同一函数读
        `timers.in_flight_grace_seconds` 却不被点名（该键不在名单里）—— 名单本身即随手。

        改成两条 AST 判据（都对**语法结构**断言，不对字符出现断言）：

        * `H1 另写常量` —— 任一同步域模块把契约数值**绑定到契约同名标识符**
          （赋值 / 带注解赋值 / 形参默认值 / 关键字实参），或出现 `52428800` 这个
          不可能巧合的字节上限字面量。注意 H1 连 `oo_contract.py` 一起管：真源在 JSON，
          连 loader 也不该内联数值。
        * `H2 另写解析` —— 只有 loader（`oo_contract.py`）可以用**字符串下标/`getattr`
          字面量**去取契约键；别处那样写意味着自己又解析了一遍 JSON。
        """
        contract = load_callback_contract()
        numbers = {
            str(contract.timers.command_service_http_timeout_seconds),
            str(contract.timers.forcesave_callback_wait_timeout_seconds),
            str(contract.timers.in_flight_grace_seconds),
            str(contract.download.streaming_size_cap_bytes),
            str(contract.timers.recovery_case_claim_ttl_hours),
        }
        # `52428800` = 50 MiB：Task 22 把 `streaming_size_cap_bytes` 从首版的 209715200
        # （200 MiB）改回 Requirement 14.11 的压缩 OOXML 预算。理由是那 4 倍差值让下载门
        # 永远不会先触发（`stage_incoming` 在 50 MiB 就中止），超限错误码会指向 OOXML
        # 预算而不是「下载无界」。此处只是新鲜度 pin，语义判据仍是下面两段。
        assert numbers == {"10", "120", "30", "52428800", "72"}, numbers

        keys = _contract_quantity_keys()
        assert len(keys) >= 5, f"契约数量键集退化成 {sorted(keys)} ⇒ H1/H2 会在空集上评估"

        pkg = _BACKEND / "app" / "services" / "workpaper_sync"
        modules = sorted(pkg.glob("*.py"))
        assert len(modules) > 20, f"同步域只扫到 {len(modules)} 个模块 ⇒ 分母塌了"

        inlined: dict[str, list[str]] = {}
        reparsed: dict[str, list[str]] = {}
        for py in modules:
            tree = ast.parse(py.read_text(encoding="utf-8"))
            hits = _contract_number_inlined(tree, keys=keys, values=numbers)
            if hits:
                inlined[py.name] = hits
            if py.name == "oo_contract.py":
                continue  # loader 是唯一被允许按字符串键取 JSON 的地方
            reads = _contract_key_string_reads(tree, keys=keys)
            if reads:
                reparsed[py.name] = reads
        assert not inlined, (
            f"以下模块把契约数值内联成了自己的常量（真源是契约 JSON）: {inlined}"
        )
        assert not reparsed, (
            f"以下模块按字符串键自取契约值（应经 oo_contract 的 dataclass 字段读）: {reparsed}"
        )

    def test_loader_rejects_drifted_schema_version(self, tmp_path: Path) -> None:
        raw = json.loads(CALLBACK_CONTRACT_PATH.read_text(encoding="utf-8"))
        raw["schema_version"] = 99
        target = tmp_path / "drifted.json"
        target.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(CallbackContractError):
            load_callback_contract(target)

    def test_loader_rejects_redirect_following(self, tmp_path: Path) -> None:
        raw = json.loads(CALLBACK_CONTRACT_PATH.read_text(encoding="utf-8"))
        raw["download_security"]["required_controls"]["redirect_policy"][
            "follow_redirects"
        ] = True
        target = tmp_path / "redirect.json"
        target.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(CallbackContractError):
            load_callback_contract(target)

    def test_loader_rejects_participant_bound_authorization(self, tmp_path: Path) -> None:
        raw = json.loads(CALLBACK_CONTRACT_PATH.read_text(encoding="utf-8"))
        raw["multi_user_semantics"]["participant_bound_callback_authorization"][
            "allowed"
        ] = True
        target = tmp_path / "pba.json"
        target.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(CallbackContractError):
            load_callback_contract(target)

    def test_loader_rejects_grace_swallowing_timeout(self, tmp_path: Path) -> None:
        raw = json.loads(CALLBACK_CONTRACT_PATH.read_text(encoding="utf-8"))
        raw["timers"]["in_flight_grace_seconds"] = 999
        target = tmp_path / "grace.json"
        target.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(CallbackContractError):
            load_callback_contract(target)

    def test_loader_rejects_emptied_status_table(self, tmp_path: Path) -> None:
        raw = json.loads(CALLBACK_CONTRACT_PATH.read_text(encoding="utf-8"))
        raw["callback_statuses"] = []
        target = tmp_path / "empty.json"
        target.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(CallbackContractError):
            load_callback_contract(target)

    def test_loader_rejects_application_without_download(self, tmp_path: Path) -> None:
        """application 只能建在 durable incoming 上 ⇒ 「允许 application 但不下载」非法。"""
        raw = json.loads(CALLBACK_CONTRACT_PATH.read_text(encoding="utf-8"))
        for row in raw["callback_statuses"]:
            if row["status"] == 1:
                row["application_allowed"] = True
        target = tmp_path / "noapp.json"
        target.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(CallbackContractError):
            load_callback_contract(target)


def _contract_quantity_keys() -> frozenset[str]:
    """契约数量键集 —— 从 `oo_contract` 的 dataclass 字段**派生**，不在本文件抄。

    分母取 :class:`Timers` 的全部字段（8 个，命名都带 `_seconds`/`_hours`，无同名碰撞）
    加上下载字节上限。刻意**不**收 `policy_version` / `max_redirects` 这类通用名：
    同步域里 redaction / retention / ooxml 各有自己的 `policy_version`（且是 str），
    把它们算进来会让判据在无关模块上假红，进而逼下一个人整体降标。
    """
    import dataclasses

    from app.services.workpaper_sync.oo_contract import Timers

    return frozenset(
        [field.name for field in dataclasses.fields(Timers)] + ["streaming_size_cap_bytes"]
    )


def _contract_number_inlined(
    tree: ast.AST, *, keys: frozenset[str], values: set[str]
) -> list[str]:
    """H1：模块是否把契约数值**内联成自己的常量**。

    三种绑定形态都算（它们是「另写常量」的全部语法出口）：赋值目标名、带注解赋值、
    形参默认值、关键字实参名。外加 `52428800` 这个不可能巧合的字面量 —— 它出现在任何
    位置都是自写（真源在契约 JSON 里，连 loader 也不内联它）。
    """
    hits: list[str] = []
    numeric = {int(v) for v in values}

    def _is_num(node: ast.AST | None) -> int | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(
            node.value, bool
        ):
            return int(node.value)
        return None

    def _record(name: str, value: int) -> None:
        if name in keys and value in numeric:
            hits.append(f"{name}={value}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = _is_num(node.value)
            if value is not None:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        _record(target.id.lower(), value)
                    elif isinstance(target, ast.Attribute):
                        _record(target.attr.lower(), value)
        elif isinstance(node, ast.AnnAssign):
            value = _is_num(node.value)
            if value is not None and isinstance(node.target, ast.Name):
                _record(node.target.id.lower(), value)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            positional = [*args.posonlyargs, *args.args]
            for arg, default in zip(positional[len(positional) - len(args.defaults):],
                                    args.defaults):
                value = _is_num(default)
                if value is not None:
                    _record(arg.arg.lower(), value)
            for arg, default in zip(args.kwonlyargs, args.kw_defaults):
                value = _is_num(default)
                if value is not None:
                    _record(arg.arg.lower(), value)
        elif isinstance(node, ast.keyword) and node.arg:
            value = _is_num(node.value)
            if value is not None:
                _record(node.arg.lower(), value)
        elif isinstance(node, ast.Constant) and _is_num(node) == 52428800:
            hits.append("streaming_size_cap_bytes=52428800(inline literal)")
    return sorted(set(hits))


def _contract_key_string_reads(tree: ast.AST, *, keys: frozenset[str]) -> list[str]:
    """H2：模块是否按**字符串键**自取契约值（= 又解析了一遍契约 JSON）。

    只认两种真正的取值语法：`x["key"]` 下标与 `getattr(x, "key")`。docstring / 日志文案
    里出现同一个名字不算 —— 那正是原判据（子串扫描）分不清的地方。
    """
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            index = node.slice
            if (
                isinstance(index, ast.Constant)
                and isinstance(index.value, str)
                and index.value in keys
            ):
                hits.append(f'["{index.value}"]')
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
            and node.args[1].value in keys
        ):
            hits.append(f'getattr(..., "{node.args[1].value}")')
    return sorted(set(hits))


def _strip_comments_and_strings(code: str) -> str:
    """去掉注释与字符串字面量后的代码（避免 docstring 里的数值造成误判）。"""
    tree = ast.parse(code)
    spans: list[tuple[int, int]] = []
    lines = code.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    def _pos(lineno: int, col: int) -> int:
        return offsets[lineno - 1] + col

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.end_lineno is None or node.end_col_offset is None:
                continue
            spans.append(
                (_pos(node.lineno, node.col_offset), _pos(node.end_lineno, node.end_col_offset))
            )
    out = list(code)
    for start, end in spans:
        for i in range(start, min(end, len(out))):
            out[i] = " "
    text = "".join(out)
    return re.sub(r"#[^\n]*", "", text)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 冻结身份 digest（AC 2.5 / 3.7 / 4.1）
# ═══════════════════════════════════════════════════════════════════════════


def _slots(
    *, template: str = "tpl", instrumentation: str = "instr", contract: str = "contract"
) -> dict[BundleSlot, BundleSlotSpec]:
    return {
        BundleSlot.template: BundleSlotSpec(
            BundleSlot.template, "definition", f"definition:{uuid.UUID(int=1)}", _d(template)
        ),
        BundleSlot.instrumentation: BundleSlotSpec(
            BundleSlot.instrumentation,
            "definition",
            f"definition:{uuid.UUID(int=2)}",
            _d(instrumentation),
        ),
        BundleSlot.contract: BundleSlotSpec(
            BundleSlot.contract, "definition", f"definition:{uuid.UUID(int=3)}", _d(contract)
        ),
    }


class TestBundleSlotsDigest:
    def test_digest_is_deterministic_and_order_independent(self) -> None:
        """dict 插入序不得影响 digest（否则同 bundle 在两条路径算出两个值）。"""
        slots = _slots()
        reordered = {
            BundleSlot.contract: slots[BundleSlot.contract],
            BundleSlot.template: slots[BundleSlot.template],
            BundleSlot.instrumentation: slots[BundleSlot.instrumentation],
        }
        a = compute_bundle_slots_digest(
            authority_model=AuthorityModel.projection_contract,
            authority_model_definition_sha256=_d("authority"),
            slots=slots,
        )
        b = compute_bundle_slots_digest(
            authority_model=AuthorityModel.projection_contract,
            authority_model_definition_sha256=_d("authority"),
            slots=reordered,
        )
        assert a == b

    @pytest.mark.parametrize("changed", ["template", "instrumentation", "contract"])
    def test_any_slot_change_changes_digest(self, changed: str) -> None:
        base = compute_bundle_slots_digest(
            authority_model=AuthorityModel.projection_contract,
            authority_model_definition_sha256=_d("authority"),
            slots=_slots(),
        )
        drifted = compute_bundle_slots_digest(
            authority_model=AuthorityModel.projection_contract,
            authority_model_definition_sha256=_d("authority"),
            slots=_slots(**{changed: "drifted"}),
        )
        assert base != drifted, f"{changed} slot 变化必须改变 typed-slot inventory digest"

    def test_authority_model_change_changes_digest(self) -> None:
        slots = _slots()
        a = compute_bundle_slots_digest(
            authority_model=AuthorityModel.projection_contract,
            authority_model_definition_sha256=_d("authority"),
            slots=slots,
        )
        b = compute_bundle_slots_digest(
            authority_model=AuthorityModel.custom_authoritative_ooxml,
            authority_model_definition_sha256=_d("authority"),
            slots=slots,
        )
        assert a != b

    def test_slot_omission_fails_closed(self) -> None:
        slots = _slots()
        del slots[BundleSlot.instrumentation]
        with pytest.raises(IdentityError):
            compute_bundle_slots_digest(
                authority_model=AuthorityModel.projection_contract,
                authority_model_definition_sha256=_d("authority"),
                slots=slots,
            )

    @pytest.mark.parametrize("bad", ["", "   ", "0" * 64, "zz" * 32, "abc"])
    def test_zero_or_blank_digest_rejected(self, bad: str) -> None:
        slots = _slots()
        slots[BundleSlot.contract] = BundleSlotSpec(
            BundleSlot.contract, "definition", f"definition:{uuid.UUID(int=3)}", bad
        )
        with pytest.raises(IdentityError):
            compute_bundle_slots_digest(
                authority_model=AuthorityModel.projection_contract,
                authority_model_definition_sha256=_d("authority"),
                slots=slots,
            )

    def test_unknown_authority_model_rejected(self) -> None:
        with pytest.raises(IdentityError):
            compute_bundle_slots_digest(
                authority_model="freeform_whatever",
                authority_model_definition_sha256=_d("authority"),
                slots=_slots(),
            )


class TestContributorSnapshotDigest:
    def test_order_and_case_insensitive_but_membership_sensitive(self) -> None:
        room, gen = uuid.uuid4(), 3
        a, b = uuid.uuid4(), uuid.uuid4()
        d1 = compute_contributor_snapshot_digest(
            room_id=room, generation=gen, contributor_user_ids=[a, b]
        )
        d2 = compute_contributor_snapshot_digest(
            room_id=room, generation=gen, contributor_user_ids=[str(b).upper(), str(a)]
        )
        assert d1 == d2, (
            "OO 的 history.changes 顺序随编辑时序变化；按到达序入 digest 会让同一批贡献者"
            "算出不同值，合法重放被误判 409"
        )
        d3 = compute_contributor_snapshot_digest(
            room_id=room, generation=gen, contributor_user_ids=[a]
        )
        assert d1 != d3, "贡献者集合变化必须改变 digest"

    def test_generation_scoped(self) -> None:
        room, u = uuid.uuid4(), uuid.uuid4()
        assert compute_contributor_snapshot_digest(
            room_id=room, generation=1, contributor_user_ids=[u]
        ) != compute_contributor_snapshot_digest(
            room_id=room, generation=2, contributor_user_ids=[u]
        )

    def test_empty_contributor_set_is_stable_not_error(self) -> None:
        """单人 room 首次 forcesave 时 contributors 可能为空，必须有稳定 digest。"""
        room = uuid.uuid4()
        assert compute_contributor_snapshot_digest(
            room_id=room, generation=1, contributor_user_ids=[]
        ) == compute_contributor_snapshot_digest(
            room_id=room, generation=1, contributor_user_ids=["", "  "]
        )


class TestFrozenBundleIdentityComparison:
    def _identity(self, **overrides: object) -> FrozenBundleIdentity:
        base = dict(
            definition_bundle_id=uuid.UUID(int=10),
            definition_bundle_sha256=_d("bundle"),
            authority_model=AuthorityModel.projection_contract,
            authority_model_definition_id=uuid.UUID(int=11),
            authority_model_definition_sha256=_d("authority"),
            slots=_slots(),
            slots_digest=_d("slots"),
        )
        base.update(overrides)
        return FrozenBundleIdentity(**base)  # type: ignore[arg-type]

    def test_same_identity_passes(self) -> None:
        self._identity().assert_same_as(self._identity(), where="test")

    @pytest.mark.parametrize(
        "field,value",
        [
            ("definition_bundle_id", uuid.UUID(int=99)),
            ("definition_bundle_sha256", _d("other")),
            ("authority_model", AuthorityModel.opaque_single_onlyoffice),
            ("authority_model_definition_id", uuid.UUID(int=98)),
            ("authority_model_definition_sha256", _d("other-authority")),
            ("slots_digest", _d("other-slots")),
        ],
    )
    def test_each_field_drift_is_detected_and_named(self, field: str, value: object) -> None:
        with pytest.raises(BundleIdentityDriftError) as exc:
            self._identity().assert_same_as(
                self._identity(**{field: value}), where="unit"
            )
        assert field in str(exc.value), (
            "漂移诊断必须指出**首个**漂移字段，否则运维只知道「bundle 不一致」"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3.5 route credential 与 contributor 三分（AC 2.6 末句 / Property 63）
# ═══════════════════════════════════════════════════════════════════════════


class TestRouteCredentialIsRoomScoped:
    def test_deterministic_and_bound_to_all_three_components(self) -> None:
        """凭证必须由 `(room, generation, doc_key)` 三者共同决定，且可重算。

        可重算是硬要求：callback 可能在进程重启之后到达，Task 22 只有能重算才能校验；
        随机值要么落表、要么塞进 URL 让客户端回传（后者等于让攻击者自选凭证）。
        """
        room = uuid.uuid4()
        key = derive_doc_key(wp_id=uuid.uuid4(), entry_id="xlsx-sheet/D2/D2-1", generation=1)
        base = mint_route_credential(room_id=room, generation=1, doc_key=key)
        assert base == mint_route_credential(room_id=room, generation=1, doc_key=key)
        other_generation = mint_route_credential(room_id=room, generation=2, doc_key=key)
        other_room = mint_route_credential(room_id=uuid.uuid4(), generation=1, doc_key=key)
        other_key = mint_route_credential(
            room_id=room, generation=1, doc_key=key.replace("-g1", "-g9")
        )
        ids = {
            base.credential_id,
            other_generation.credential_id,
            other_room.credential_id,
            other_key.credential_id,
        }
        assert len(ids) == 4, (
            "三个成分任一变化都必须换凭证：只绑 room 时 generation 旋转后旧 callback 仍"
            "合法（AC 2.8 的 supersede 形同虚设）"
        )

    def test_assert_route_credential_rejects_foreign_credential(self) -> None:
        room = uuid.uuid4()
        key = derive_doc_key(wp_id=uuid.uuid4(), entry_id="e", generation=1)
        good = mint_route_credential(room_id=room, generation=1, doc_key=key)
        assert (
            assert_route_credential(
                good.credential_id, room_id=room, generation=1, doc_key=key
            )
            == good
        )
        with pytest.raises(RouteCredentialError):
            assert_route_credential(
                good.credential_id, room_id=room, generation=2, doc_key=key
            )
        with pytest.raises(RouteCredentialError):
            assert_route_credential(
                uuid.uuid4(), room_id=room, generation=1, doc_key=key
            )

    def test_mint_signature_has_no_user_or_participant_parameter(self) -> None:
        """结构判据：签名里不能有 user/participant —— 「route 不是作者」得是结构性的。

        Task 4 §3 实证：Command Service 的 forcesave 请求体没有发起人字段，status 6 的
        `users` 只有最后编辑者一人，`history.changes` 才是全体贡献者且**含已被 drop 的
        用户**。所以把 callback 里任一 participant 当聚合 artifact 的唯一作者/唯一授权
        依据在 OO 9.4 上是事实错误。

        只写注释是不够的：注释挡不住有人加一个 `user_id=` 参数。这里断言签名与
        dataclass 字段里都没有这类名字。
        """
        import inspect

        forbidden = {"user_id", "participant_id", "participant", "current_user", "actor_id"}
        params = set(inspect.signature(mint_route_credential).parameters)
        assert not (params & forbidden), f"mint 签名混入用户成分：{sorted(params & forbidden)}"
        fields = set(RouteCredential.__dataclass_fields__)
        assert not (fields & forbidden), f"RouteCredential 混入用户成分：{sorted(fields)}"

    def test_credential_id_is_not_derivable_from_doc_key_alone(self) -> None:
        """凭证不得等于 doc_key 的可预测变形（否则知道 doc_key 就等于持有凭证）。"""
        room = uuid.uuid4()
        key = derive_doc_key(wp_id=uuid.uuid4(), entry_id="e", generation=1)
        credential = mint_route_credential(room_id=room, generation=1, doc_key=key)
        assert str(credential.credential_id) not in key
        assert key not in str(credential.credential_id)
        assert credential.credential_id != room


class TestContributorDomainMatchesSchemaAndContract:
    def test_source_and_confidence_enums_equal_the_v151_check_domains(self) -> None:
        """两个封闭域必须与 V151 的 CHECK **逐值**一致（真源双向锁死）。

        写在两处（Python enum 与 SQL CHECK）时，只在 Python 侧加一个值会让写库在生产
        才炸；只在 SQL 侧加会让 Python 永远产不出那个值。所以从迁移文本里把 CHECK 的
        值集抽出来正面比对。
        """
        migration = (
            _BACKEND
            / "migrations"
            / "V151__workpaper_sync_content_application_bundle_scope.sql"
        )
        text = migration.read_text(encoding="utf-8")
        source_match = re.search(
            r"ck_wpsoc_source CHECK \(source IN \(([^)]*)\)\)", text
        )
        confidence_match = re.search(
            r"ck_wpsoc_confidence CHECK \(confidence IN \(([^)]*)\)\)", text
        )
        assert source_match and confidence_match, (
            "V151 里找不到 contributor 的两条 CHECK ⇒ 判据恒空（假绿）"
        )
        sql_sources = set(re.findall(r"'([a-z_]+)'", source_match.group(1)))
        sql_confidences = set(re.findall(r"'([a-z_]+)'", confidence_match.group(1)))
        assert sql_sources == {item.value for item in ContributorSource}
        assert sql_confidences == {item.value for item in ContributorConfidence}

    def test_contract_pins_history_changes_as_the_only_contributor_source(self) -> None:
        """契约必须仍把 `history.changes[].user` 当唯一 contributor 来源。

        Task 4 §2 实测：`users` 在 status 6 只含「最后编辑者」一人。拿它当 contributor
        set 会让审计快照丢掉全部并发贡献者，而这恰恰是「A 发起的 forcesave 里含 B 的
        修改」这条实证要防的。
        """
        contract = load_callback_contract().multi_user
        assert contract.contributor_snapshot_source == "history.changes[].user"
        assert contract.users_field_semantics == "last_editor_only_not_contributors"
        assert contract.participant_bound_authorization_allowed is False

    def test_room_service_reads_contributor_source_from_the_contract(self) -> None:
        """结构判据：contributor 来源必须**从契约读**，不得在代码里写死字面量。

        判法是两段：先断言 `record_contributor_snapshot` 的源码里真的引用了契约字段，
        再断言它把不合规的契约值拒掉（后者由 PG 守卫的行为用例覆盖）。只做第二段时，
        把契约读取换成硬编码同值对象是完全不可观测的。
        """
        source = _ROOMS_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        target = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "record_contributor_snapshot"
        )
        body = ast.dump(target)
        assert "contributor_snapshot_source" in body, (
            "contributor 来源没有从契约读 ⇒ 真值表退回「只有守卫在读」的死代码状态"
        )
        assert "load_callback_contract" in body, (
            "没有调用契约 loader ⇒ 契约被改回 participant-bound 时生产行为不变"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 双基线纯判据（Property 62）
# ═══════════════════════════════════════════════════════════════════════════


class TestRoomBaselinesProjection:
    def _baselines(self, **overrides: object) -> RoomBaselines:
        base = dict(
            opened_base_version_id=uuid.UUID(int=1),
            server_last_applied_version_id=uuid.UUID(int=2),
            client_confirmed_base_version_id=uuid.UUID(int=3),
            client_confirmed_representation_id=uuid.UUID(int=4),
            client_confirmed_projection_sha256=_d("projection"),
            client_confirmed_definition_bundle_id=uuid.UUID(int=5),
            client_confirmed_definition_bundle_sha256=_d("bundle"),
        )
        base.update(overrides)
        return RoomBaselines(**base)  # type: ignore[arg-type]

    def test_complete_snapshot_is_established(self) -> None:
        assert self._baselines().client_baseline_established is True

    @pytest.mark.parametrize(
        "field",
        [
            "client_confirmed_base_version_id",
            "client_confirmed_representation_id",
            "client_confirmed_projection_sha256",
            "client_confirmed_definition_bundle_id",
        ],
    )
    def test_half_missing_snapshot_is_not_established(self, field: str) -> None:
        """四项缺一即视为未建立 —— 半缺快照会让 forcesave 冻结出不完整 base。"""
        assert self._baselines(**{field: None}).client_baseline_established is False

    def test_server_last_applied_is_independent_of_client_confirmed(self) -> None:
        """Property 62：服务端已应用 ≠ 编辑器已持有。二者必须是两个字段。"""
        snapshot = self._baselines(
            server_last_applied_version_id=uuid.UUID(int=42),
            client_confirmed_base_version_id=uuid.UUID(int=3),
        )
        assert snapshot.server_last_applied_version_id != (
            snapshot.client_confirmed_base_version_id
        )
        assert snapshot.client_baseline_established is True


# ═══════════════════════════════════════════════════════════════════════════
# 5. 结构判据：服务层不得重写 repository 已有的原子写
# ═══════════════════════════════════════════════════════════════════════════


class TestServiceDoesNotDuplicateRepository:
    def test_room_service_never_commits(self) -> None:
        """事务边界由 coordinator 持有（与 repository 同一约定）。"""
        code = _strip_comments_and_strings(_ROOMS_PATH.read_text(encoding="utf-8"))
        assert ".commit()" not in code, (
            "room service 不得 commit —— 一次业务应用要同时落 room 双基线/application/"
            "operation event/outbox，服务层自己提交会留下半成功态"
        )

    def test_room_service_does_not_compute_request_sequence(self) -> None:
        """request_sequence 只由 repository 在 room lock 内算一次。"""
        code = _strip_comments_and_strings(_ROOMS_PATH.read_text(encoding="utf-8"))
        assert "latest_request_sequence" not in code, (
            "服务层碰 latest_request_sequence 就出现了第二处序号推进 —— "
            "room fence 只认 repository 那一份"
        )

    def test_close_capture_cannot_be_requested_by_client(self) -> None:
        """契约 clean_close.forbidden[0]：客户端不得直接创建 kind=close_capture。"""
        code = _ROOMS_PATH.read_text(encoding="utf-8")
        assert "RequestKind.close_capture" in code, (
            "资格门必须显式拒绝 close_capture，而不是靠「没人会传」"
        )
        assert RequestKind.close_capture.value == "close_capture"

    def test_allowed_states_include_barrier_and_closing(self) -> None:
        """AC 4.10：barrier 期间 closing participant 仍要能做 predecessor forcesave。

        把 `close_barrier`/`closing` 排除掉的后果很具体：两人关闭场景永远等不到
        predecessor terminal ⇒ close-capture 永不生成 ⇒ 最后一份编辑丢失。
        """
        assert RoomState.close_barrier in rooms_mod._REQUEST_ALLOWED_ROOM_STATES
        assert RoomState.active in rooms_mod._REQUEST_ALLOWED_ROOM_STATES
        assert RoomState.refresh_required not in rooms_mod._REQUEST_ALLOWED_ROOM_STATES
        assert RoomState.superseded not in rooms_mod._REQUEST_ALLOWED_ROOM_STATES
        assert RoomState.closed not in rooms_mod._REQUEST_ALLOWED_ROOM_STATES
        assert (
            ParticipantState.closing in rooms_mod._REQUEST_ALLOWED_PARTICIPANT_STATES
        )
        assert (
            ParticipantState.revoked
            not in rooms_mod._REQUEST_ALLOWED_PARTICIPANT_STATES
        )
        assert (
            ParticipantState.expired
            not in rooms_mod._REQUEST_ALLOWED_PARTICIPANT_STATES
        )
        assert ParticipantState.left not in rooms_mod._REQUEST_ALLOWED_PARTICIPANT_STATES
