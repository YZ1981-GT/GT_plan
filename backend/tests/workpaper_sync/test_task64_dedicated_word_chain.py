# -*- coding: utf-8 -*-
r"""Task 64 守卫 —— A16/A17 专用 Word 链与 Word editor 宿主的裁决记录。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 6 Task 64
Requirements: 7.1 · 7.3 · 11.4 · 11.5 · 11.12 · 12.1 · 12.5 · 12.10 · 12.11 · 12.12
Properties: 30 · 31 · 47 · 69 · 70

从仓库根运行::

    .\.venv\Scripts\python.exe -m pytest backend/tests/workpaper_sync/test_task64_dedicated_word_chain.py -q

═══ 判据口径 ═══

每条判据都**现算**再与产物比对，不查「字符串是否存在」：
* HTML 字段面 → 守卫自己调生产解析器 `parse_template`，与产物逐 wp_code 对数；
* mount 门控链 → 守卫自己扫 `.vue`，与产物逐挂载点对齐；
* 不可达 → 三要素（挂载点存在 + 外层门控引用某 kind + 该 kind 从未出现在静态 TABS）；
* 未越 Task 61 门 → 断言 `adapters/word.py` 真不存在、登记表与 provider 白名单条数未变。

于是「把产物改对/改错」「把生产解析器短路」「偷偷加一行契约登记」三类都会打红，而不是
只在有人删掉某个字面量时才打红。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_THIS = Path(__file__).resolve()
_REPO = _THIS.parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))

RECORD_PATH = _BACKEND / "data" / "workpaper_sync_a16_a17_word_chain_adjudication.json"
GENERATOR = _BACKEND / "scripts" / "gen" / "generate_task64_dedicated_word_chain.py"
TEMPLATE_ROOT = _BACKEND / "wp_templates"
WP_COMPONENTS = _REPO / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
A16_BUNDLE_VUE = WP_COMPONENTS / "GtA16Bundle.vue"
A17_BUNDLE_VUE = WP_COMPONENTS / "GtA17Bundle.vue"
WORD_EDITOR_VUE = WP_COMPONENTS / "WorkpaperWordEditor.vue"
OO_WORD_DIALOG_VUE = WP_COMPONENTS / "OnlyOfficeWordDialog.vue"
FORBIDDEN_WORD_ADAPTER = _BACKEND / "app" / "services" / "workpaper_sync" / "adapters" / "word.py"

A16_SUBCODES = tuple(f"A16-{i}" for i in range(1, 8))
EXPECTED_ENTRY_IDS = (
    "docx/gt-a16-bundle",
    "docx/gt-a17-bundle",
    "docx/workpaper-word-editor",
    "docx/wp-popup-docx-editor",
)
EXPECTED_BP_IDS = tuple(f"BP-{n}" for n in range(16, 23))


@pytest.fixture(scope="module")
def record() -> dict:
    assert RECORD_PATH.is_file(), (
        f"缺产物 {RECORD_PATH} —— 先跑 "
        f"`.\\.venv\\Scripts\\python.exe {GENERATOR.relative_to(_REPO).as_posix()} --write`"
    )
    return json.loads(RECORD_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def entries(record: dict) -> dict[str, dict]:
    return {e["entry_id"]: e for e in record["entries"]}


# ═══════════════════════════════════════════════════════════════════════════
# 1. 守卫自身的反向自检（防「分母为空所以全绿」）
# ═══════════════════════════════════════════════════════════════════════════
class TestGuardSelfChecks:
    def test_the_denominators_are_not_empty(self, record: dict) -> None:
        """分母为空时本文件的多数断言会退化成重言式 —— 先把分母钉死。"""
        assert len(record["entries"]) == 4, "docx entry 分母必须是 4 条"
        assert len(record["authoritative_templates"]) == 15, (
            "权威 DOCX 分母必须是 15 份（Task 58 清册 owner_task=64 里 "
            "unified_verdict=resolved_docx 的行）"
        )
        assert len(record["html_projection_surface"]) == 15
        assert record["property_denominators"]["oo_host_components"] == 2
        assert len(record["blocking_preconditions"]) == len(EXPECTED_BP_IDS)

    def test_the_four_verdicts_are_actually_different(self, record: dict) -> None:
        """四条 entry 若裁决全同，说明推导没有区分 —— 那是「一刀切」不是逐 entry 裁决。"""
        verdicts = [e["verdict"] for e in record["entries"]]
        assert len(set(verdicts)) == 4, f"四条 entry 应有四种不同裁决，实得 {verdicts}"

    def test_impl_probes_really_ran(self, record: dict) -> None:
        """impl 反证必须真跑过并被拒 —— 没有一条允许 UNEXPECTED_SUCCESS。"""
        probes = record["impl_probes"]
        rejected = [k for k, v in probes.items() if v.get("outcome") == "rejected"]
        assert len(rejected) >= 4, f"至少四条 impl 反证应为 rejected，实得 {rejected}"
        unexpected = [k for k, v in probes.items() if v.get("outcome") == "UNEXPECTED_SUCCESS"]
        assert not unexpected, (
            f"这些 impl 反证意外成功了 {unexpected} —— 裁决前提已变，必须重新裁决而不是"
            "留着记录不动"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. HTML 投影字段面：委派生产解析器现算
# ═══════════════════════════════════════════════════════════════════════════
class TestHtmlProjectionSurfaceIsRecomputed:
    def test_a16_chain_has_zero_html_field_surface(self, record: dict) -> None:
        """A16 七码的 HTML 侧字段面必须由**生产解析器**现算为 0。

        这是「裁 opaque 而非 projection_contract」的唯一实质依据。守卫在这里重新跑一次
        `parse_template`，因此产物被改成非 0、或解析器被短路成返回空，两种都打红。
        """
        from app.services.wp_docx_template_parser import parse_template

        surface = record["html_projection_surface"]
        for code in A16_SUBCODES:
            rel = record["authoritative_templates"][code]["relative_path"]
            live = parse_template(str(TEMPLATE_ROOT / rel))
            assert len(live.placeholders) == surface[code]["placeholder_count"], (
                f"{code}: 产物记 {surface[code]['placeholder_count']} 个 placeholder，"
                f"生产解析器现算 {len(live.placeholders)} 个"
            )
            assert len(live.placeholders) == 0, (
                f"{code}: HTML 侧字段面现算为 {len(live.placeholders)} ≠ 0 —— "
                "投影出现了对端，opaque 裁决的前提失效，必须重新裁决（BP-16）"
            )
            # 反向自检：模板本身不是空文档，否则「0 个 placeholder」毫无信息量。
            assert len(live.paragraphs) > 0, f"{code}: 模板解析出 0 个段落，判据空转"

    def test_no_declarative_dollar_token_exists_anywhere(self, record: dict) -> None:
        """15 份模板的 `${}` 声明式 token 总数为 0（zip 级现算，与产物对齐）。"""
        assert record["counters"]["templates_with_dollar_tokens"] == 0
        assert record["counters"]["html_placeholder_dollar_total"] == 0
        for code, facts in record["authoritative_templates"].items():
            assert facts["dollar_tokens"] == [], f"{code} 出现了 `${{}}` token: {facts}"

    def test_every_template_has_tables(self, record: dict) -> None:
        """15/15 有 `w:tbl` —— 这条钉死「WORD_ONLY_COVERAGE_REQUIRED 不能照抄 F2」。

        F2-22/F2-23 的 `w:tbl` 实测为 0，故 Task 77 的必需覆盖项刻意不含 `table_shape`
        / `managed_row_identity`。本 lane 反过来，将来若要发契约必须按自己的实测重算。
        """
        assert record["counters"]["templates_with_tables"] == 15
        for code, facts in record["authoritative_templates"].items():
            assert facts["w_tbl_count"] > 0, f"{code} 没有 w:tbl，与本 lane 的实测相反"


# ═══════════════════════════════════════════════════════════════════════════
# 3. 不可达桩：三要素结构判据
# ═══════════════════════════════════════════════════════════════════════════
class TestUnreachableStubFinding:
    def test_a17_word_mount_is_gated_by_a_kind_never_used(self, record: dict) -> None:
        """A17 bundle 的 Word 挂载点不可达 —— 三要素缺一即不成立。

        ① 挂载点确实存在；② 它的外层门控引用某个 `tab.kind === '<k>'`；
        ③ 该 `<k>` 从未出现在静态 TABS 的 `kind:` 字面量里。
        只断言 ①② 会把「kind 后来被启用」也判成不可达；只断言 ③ 会把「压根没有这个门控」
        也判成不可达。
        """
        text = A17_BUNDLE_VUE.read_text(encoding="utf-8")
        lines = text.splitlines()

        # ① 挂载点存在
        mount_lines = [i + 1 for i, ln in enumerate(lines) if "<WorkpaperWordEditor" in ln]
        assert mount_lines, "GtA17Bundle.vue 里没有 WorkpaperWordEditor 挂载点，判据前提消失"

        # ② 外层门控引用的 kind
        gated_kinds: set[str] = set()
        for mount_line in mount_lines:
            for back in range(mount_line - 2, max(-1, mount_line - 60), -1):
                m = re.search(r"tab\.kind\s*===\s*'([^']+)'", lines[back])
                if m:
                    gated_kinds.add(m.group(1))
                    break
        assert gated_kinds, (
            "Word 挂载点外层没有 `tab.kind === '...'` 门控 —— 若门控被改成别的形态，"
            "本判据必须重写而不是继续绿"
        )

        # ③ 这些 kind 从未出现在静态 TABS
        used = set(re.findall(r"kind:\s*'([^']+)'", text))
        never_used = gated_kinds - used
        assert never_used == gated_kinds, (
            f"外层门控引用的 kind {sorted(gated_kinds)} 里有已被 TABS 使用的 "
            f"{sorted(gated_kinds & used)} ⇒ 挂载点可达，unreachable 裁决失效"
        )

        # 与产物对齐
        vocab = record["a17_tab_vocabulary"]
        assert set(vocab["kinds_declared_but_never_used"]) >= never_used
        assert "word" in never_used, f"实测未使用的 kind 是 {sorted(never_used)}"
        finding = record["unreachable_findings"][0]
        assert finding["entry_id"] == "docx/gt-a17-bundle"
        assert finding["verdict"] == "unreachable_stub"
        assert finding["mount_line"] in mount_lines

    def test_manifest_condition_alone_cannot_see_this(self, record: dict) -> None:
        """钉死 BP-18 的根因：manifest 的 mount condition 里没有外层 kind 门控。

        这条不是「manifest 有 bug 所以我们记一笔」，而是「本任务的判据必须比 manifest
        的口径更深一层」的可执行证明 —— 若哪天 manifest 开始记外层门控，本条会打红，
        提醒把判据来源切回 manifest 并撤掉 BP-18。
        """
        entry = next(
            e for e in record["entries"] if e["entry_id"] == "docx/gt-a17-bundle"
        )
        conditions = entry["manifest_facts"]["mount_conditions"]
        joined = " ".join(c for c in conditions if c)
        assert "tab.kind" not in joined, (
            "manifest 的 mount condition 现在包含了外层 kind 门控 ⇒ 扫描器口径已修，"
            "BP-18 应当解除，本判据与该 BP 都要更新"
        )
        chain = entry["mount_gate_chain"]
        assert chain and any(
            c.get("outer_gate") and "tab.kind" in c["outer_gate"] for c in chain
        ), "本任务的 mount_gate_chain 必须记下外层 kind 门控，否则与 manifest 无差别"


# ═══════════════════════════════════════════════════════════════════════════
# 4. 逐 entry 裁决与跨 entry 隔离
# ═══════════════════════════════════════════════════════════════════════════
class TestVerdictDerivations:
    def test_all_four_entries_are_present_and_manifest_backed(
        self, entries: dict[str, dict]
    ) -> None:
        assert tuple(sorted(entries)) == tuple(sorted(EXPECTED_ENTRY_IDS))
        for entry_id, entry in entries.items():
            assert entry["manifest_facts"], f"{entry_id} 缺 manifest 事实"
            assert entry["manifest_facts"]["host_path"], f"{entry_id} 缺 host_path"

    def test_a16_bundle_mount_has_no_static_kind_gate(self, entries: dict[str, dict]) -> None:
        """A16 裁 opaque 的前提之一：它的 mount **真实可达**（不像 A17 那条）。"""
        chain = entries["docx/gt-a16-bundle"]["mount_gate_chain"]
        assert chain, "A16 bundle 的挂载点消失了"
        for item in chain:
            gate = item.get("outer_gate") or ""
            assert "tab.kind" not in gate, (
                f"A16 挂载点出现了 kind 门控 {gate!r} —— 可达性前提要重新验"
            )

    def test_parent_duplicate_follows_manifest_not_our_opinion(
        self, entries: dict[str, dict]
    ) -> None:
        entry = entries["docx/workpaper-word-editor"]
        assert entry["manifest_facts"]["independent_entry"] is False
        assert entry["manifest_facts"]["parent_entry_id"] == "docx/gt-a16-bundle"
        assert entry["verdict"] == "parent_duplicate_follows_parent"

    def test_shared_room_entry_is_the_only_shared_one(
        self, record: dict, entries: dict[str, dict]
    ) -> None:
        shared = [
            e["entry_id"]
            for e in record["entries"]
            if e["manifest_facts"]["room_model"] == "shared"
        ]
        assert shared == ["docx/wp-popup-docx-editor"], (
            f"shared room 的 docx entry 应恰有一条，实得 {shared}"
        )


class TestCrossEntryIsolation:
    def test_scenarios_are_not_deduped_by_profile_id(self, record: dict) -> None:
        """三条 entry 的 profile_id 逐字相同 ⇒ 禁止按 profile 去重，必须按 entry_id。"""
        profiles: dict[str, list[str]] = {}
        for e in record["entries"]:
            pid = e["manifest_facts"].get("scenario_profile_id")
            if pid:
                profiles.setdefault(pid, []).append(e["entry_id"])
        collided = {p: ids for p, ids in profiles.items() if len(ids) > 1}
        assert collided, (
            "本 lane 实测有多条 entry 共享同一 profile_id；若不再共享，"
            "「禁止按 profile 去重」这条判据要重写"
        )
        # 每条共享 profile 的 entry 仍各自成条目
        for ids in collided.values():
            assert len(set(ids)) == len(ids)
            for entry_id in ids:
                assert any(e["entry_id"] == entry_id for e in record["entries"])

    def test_no_reusable_artifact_was_produced(self, record: dict) -> None:
        iso = record["cross_entry_isolation"]
        assert iso["production_contract_dir_untouched"] is True
        assert iso["delivered_contract_rows_added"] == 0
        assert iso["provider_modules_added"] == 0
        for e in record["entries"]:
            assert e["per_entry_contract"] is None
            assert e["definition_bundle"] is None
            assert e["published_representation"] is None
            assert e["adapter_id"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 5. 未越 Task 61 的 word_bulk 门
# ═══════════════════════════════════════════════════════════════════════════
class TestTask61GateNotCrossed:
    def test_word_adapter_module_still_absent(self, record: dict) -> None:
        """`adapters/word.py` 必须不存在 —— 门是 Task 61（`[-]` UNVERIFIABLE）。"""
        from app.services.workpaper_sync.adapters import registry as R

        assert not FORBIDDEN_WORD_ADAPTER.exists(), (
            f"{FORBIDDEN_WORD_ADAPTER} 出现了 —— PENDING_ENGINE_ADAPTERS 明禁，"
            "Word adapter 的门是 Task 61"
        )
        forbidden = [
            p for row in R.PENDING_ENGINE_ADAPTERS
            if row.get("document_type") == "docx"
            for p in row.get("forbidden_paths", ())
        ]
        assert forbidden, "docx 的 pending adapter 登记消失了 —— 门被拆掉了"
        # 🔴 必须断言清单**包含那个真实路径**，不能只断言「清单非空且逐条不存在」：
        #    把 `word.py` 改名成 `word_DISABLED.py` 时后两条仍满足（改名后的路径当然也
        #    不存在）⇒ 门被悄悄挪开而守卫全绿。这条缺陷由变异 M13 实测抓出（判定
        #    WRONG-TEST：只有生成器幂等那条红了，本条没红）。
        assert "app/services/workpaper_sync/adapters/word.py" in forbidden, (
            f"docx pending adapter 的被禁路径清单 {forbidden} 里没有真实的 "
            "`app/services/workpaper_sync/adapters/word.py` —— 被禁路径被改名等于"
            "把 Task 61 的门挪开，Word adapter 就能以另一个文件名落地"
        )
        for rel in forbidden:
            assert not (_BACKEND / rel).exists(), f"被禁路径已存在: {rel}"
        assert record["task64_gate_compliance" if False else "task61_gate_compliance"][
            "forbidden_paths_still_absent"
        ] is True

    def test_contract_registry_row_count_unchanged_by_this_task(self, record: dict) -> None:
        """本任务不得往交付登记表 / provider 白名单加行。

        用「本任务名下 0 行」而不是「总数恰好等于 4」：Task 62/63 也在往里加行，
        锁死总数会把并发方的正常推进判成本任务打红（假红）。
        """
        from app.services.workpaper_sync import contracts as C
        from app.services.workpaper_sync.adapters import registry as R

        rf = record["registry_facts"]
        assert rf["task64_added_contract_rows"] == 0
        assert rf["task64_added_provider_modules"] == 0

        live_by_task = [
            r for r in R.DELIVERED_PER_ENTRY_CONTRACTS
            if str(r.get("delivered_by_task")) == "64"
        ]
        assert live_by_task == [], (
            f"交付登记表里出现了 delivered_by_task=64 的行 {live_by_task} —— "
            "本任务裁决为不发契约，加行即与裁决矛盾"
        )
        # 本任务裁决的四条 entry 都不该出现在登记表里
        registered = {str(r.get("entry_id")) for r in R.DELIVERED_PER_ENTRY_CONTRACTS}
        for entry_id in EXPECTED_ENTRY_IDS:
            assert entry_id not in registered, (
                f"{entry_id} 出现在 DELIVERED_PER_ENTRY_CONTRACTS —— 与 opaque/unreachable "
                "裁决矛盾"
            )
        # 契约目录里不该出现本 lane 的契约
        for contract_id in C.available_contract_ids():
            assert not contract_id.lower().startswith(("a16", "a17")), (
                f"契约目录出现了本 lane 的契约 {contract_id!r}"
            )

    def test_authority_model_and_contract_are_not_paired_illegally(
        self, entries: dict[str, dict]
    ) -> None:
        """裁 opaque 的 entry 绝不能同时带 contract —— RG-8/RG-9 在 impl 层就拒。

        这条不是复述文档：它把「裁决」与「产物」的一致性做成结构判据。
        """
        from app.services.workpaper_sync.models import AuthorityModel

        for entry_id, entry in entries.items():
            am = entry["authority_model"]
            if am is None:
                continue
            assert am != AuthorityModel.projection_contract.value, (
                f"{entry_id} 裁成了 projection_contract，但本任务未发布任何 per-entry "
                "contract ⇒ assert_authority_model_contract_pairing 会抛 "
                "AuthorityModelMismatchError"
            )
            assert entry["per_entry_contract"] is None, (
                f"{entry_id} 是 {am} 却带了 contract —— custom/opaque 只能在 contract slot "
                "用版本化 typed null marker（Requirement 6.19）"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 6. Property 不得过度宣称
# ═══════════════════════════════════════════════════════════════════════════
class TestPropertiesAreNotOverclaimed:
    @pytest.mark.parametrize("prop", ["Property 30", "Property 31", "Property 69"])
    def test_zero_denominator_properties_are_not_claimed(
        self, record: dict, prop: str
    ) -> None:
        node = record["properties_verified"][prop]
        assert node["claim"].startswith("NOT_CLAIMED"), (
            f"{prop} 分母为 0 却宣称通过 —— 空集恒真是假绿"
        )
        assert node["denominator"] == 0

    def test_property_47_denominator_is_not_zero(self, record: dict) -> None:
        """BP-15 的教训：承载者存在且形态相反时，分母不是 0，是反例。"""
        node = record["properties_verified"]["Property 47"]
        assert node["claim"].startswith("NOT_CLAIMED")
        assert node["denominator"] == 2, (
            "Property 47 的分母必须是现算的宿主数（2 个 OO 宿主），"
            "写成 0 会把「没有承载者所以通过」这种假绿锁死"
        )
        # 现算复核：两个宿主都不是 descriptor consumer
        for vue in (WORD_EDITOR_VUE, OO_WORD_DIALOG_VUE):
            text = vue.read_text(encoding="utf-8")
            assert "defineExpose" not in text, (
                f"{vue.name} 出现了 defineExpose ⇒ 可能已成为 descriptor consumer，"
                "Property 47 的反例判据要重验"
            )
            assert not re.search(r"\bdescriptor\b", text), (
                f"{vue.name} 出现了 descriptor ⇒ 同上"
            )

    def test_property_70_is_the_only_pass_and_has_real_denominator(
        self, record: dict
    ) -> None:
        props = record["properties_verified"]
        passed = [k for k, v in props.items() if v["claim"] == "PASS"]
        assert passed == ["Property 70"], f"本任务只应宣称 Property 70 通过，实得 {passed}"
        assert props["Property 70"]["denominator"] == 4


# ═══════════════════════════════════════════════════════════════════════════
# 7. 阻断项登记完整性
# ═══════════════════════════════════════════════════════════════════════════
class TestBlockingPreconditions:
    def test_all_bps_are_registered_and_open(self, record: dict) -> None:
        bps = {bp["id"]: bp for bp in record["blocking_preconditions"]}
        assert tuple(sorted(bps)) == tuple(sorted(EXPECTED_BP_IDS))
        for bp_id, bp in bps.items():
            assert bp["status"] == "open", f"{bp_id} 状态不是 open"
            assert bp["blocks"], f"{bp_id} 没写它阻断了什么"
            assert bp["what"].strip(), f"{bp_id} 的 what 为空"
            assert bp["observable_consequences"], f"{bp_id} 没写可观察后果"
            assert bp["source_refs"], f"{bp_id} 没写 source_refs"
            for ref in bp["source_refs"]:
                assert (_REPO / ref).exists(), f"{bp_id} 的 source_ref 不存在: {ref}"

    def test_every_entry_blocked_by_points_at_a_registered_bp(self, record: dict) -> None:
        known = {bp["id"] for bp in record["blocking_preconditions"]}
        for entry in record["entries"]:
            assert entry["blocked_by"], f"{entry['entry_id']} 没写 blocked_by"
            for bp_id in entry["blocked_by"]:
                assert bp_id in known, (
                    f"{entry['entry_id']} 指向未登记的 {bp_id}"
                )

    def test_bp_numbering_continues_task60(self, record: dict) -> None:
        """编号必须续接 Task 60 的 BP-15，不得与它撞号。"""
        f2 = _BACKEND / "data" / "workpaper_sync_f2_word_lane_publication.json"
        if not f2.is_file():  # pragma: no cover - Task 60 产物缺失时跳过
            pytest.skip("Task 60 发布记录不存在")
        prior = {
            bp["id"] for bp in json.loads(f2.read_text(encoding="utf-8"))["blocking_preconditions"]
        }
        mine = {bp["id"] for bp in record["blocking_preconditions"]}
        assert not (prior & mine), f"BP 编号与 Task 60 撞号: {sorted(prior & mine)}"


# ═══════════════════════════════════════════════════════════════════════════
# 8. 每条 BP 的解除探测（xfail strict —— 真解除时 XPASS 必红）
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.xfail(strict=True, reason="BP-16 未解除：A16 链 HTML 字段面仍为 0")
def test_bp16_a16_chain_gains_html_field_surface() -> None:
    from app.services.wp_docx_template_parser import parse_template

    record = json.loads(RECORD_PATH.read_text(encoding="utf-8"))
    totals = 0
    for code in A16_SUBCODES:
        rel = record["authoritative_templates"][code]["relative_path"]
        totals += len(parse_template(str(TEMPLATE_ROOT / rel)).placeholders)
    assert totals > 0


@pytest.mark.xfail(strict=True, reason="BP-17 未解除：生产字段定位仍靠 legacy 中文正则")
def test_bp17_production_locator_no_longer_uses_cjk_regex() -> None:
    from app.services.wp_docx_template_parser import _LEGACY_PATTERNS

    assert not _LEGACY_PATTERNS


@pytest.mark.xfail(strict=True, reason="BP-18 未解除：A17 word 分支仍不可达")
def test_bp18_a17_word_kind_is_now_used() -> None:
    text = A17_BUNDLE_VUE.read_text(encoding="utf-8")
    assert "word" in set(re.findall(r"kind:\s*'([^']+)'", text))


@pytest.mark.xfail(strict=True, reason="BP-19 未解除：Word 宿主仍非 descriptor consumer")
def test_bp19_word_hosts_become_descriptor_consumers() -> None:
    for vue in (WORD_EDITOR_VUE, OO_WORD_DIALOG_VUE):
        text = vue.read_text(encoding="utf-8")
        assert "defineExpose" in text and re.search(r"\bdescriptor\b", text)


@pytest.mark.xfail(strict=True, reason="BP-20 未解除：opaque authority 通道未落库")
def test_bp20_authority_model_published_to_db() -> None:
    record = json.loads(RECORD_PATH.read_text(encoding="utf-8"))
    assert any(e["definition_bundle"] is not None for e in record["entries"])


@pytest.mark.xfail(strict=True, reason="BP-21 未解除：SyncContract.template 仍是单 TemplateRef")
def test_bp21_contract_can_express_multiple_templates() -> None:
    from app.services.workpaper_sync.contracts import SyncContract

    ann = getattr(SyncContract, "__annotations__", {})
    assert any("list" in str(v).lower() or "tuple" in str(v).lower()
               for k, v in ann.items() if "template" in k.lower())


@pytest.mark.xfail(strict=True, reason="BP-22 未解除：A17 子码 entry 仍是 document_type=xlsx")
def test_bp22_a17_subcode_entries_become_docx() -> None:
    manifest = json.loads(
        (_BACKEND / "data" / "workpaper_sync_entry_manifest.json").read_text(encoding="utf-8")
    )
    a17 = [
        e for e in manifest["entries"]
        if e["entry_id"].endswith(
            ("gt-a171-audit-summary", "gt-a173-consultation-record",
             "gt-a174-disagreement-record", "gt-a176-closing-meeting")
        )
    ]
    assert a17 and all(e["document_type"] == "docx" for e in a17)


# ═══════════════════════════════════════════════════════════════════════════
# 9. 生成器幂等与观测值口径
# ═══════════════════════════════════════════════════════════════════════════
class TestGeneratorContract:
    def test_generator_check_is_idempotent(self) -> None:
        proc = subprocess.run(  # noqa: S603 - 固定参数，无 shell
            [sys.executable, str(GENERATOR), "--check"],
            cwd=str(_REPO),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        assert proc.returncode == 0, (
            f"生成器 --check 未通过（可能上游 popup 配置被并发改动，重跑 --write）:\n"
            f"{proc.stdout}\n{proc.stderr}"
        )

    def test_popup_total_is_recorded_as_observation_with_digests(self, record: dict) -> None:
        """popup 总数是带 digest 的观测值，不是被锁死的基线。"""
        denom = record["denominator"]
        assert "popup_config_total_observed" in denom
        assert denom["popup_source_digests"], "缺 popup 源文件 digest"
        assert len(denom["popup_source_digests"]) == 3
        for name, digest in denom["popup_source_digests"].items():
            live = (WP_COMPONENTS / name).read_bytes()
            import hashlib

            assert hashlib.sha256(live).hexdigest() == digest, (
                f"{name} 的 digest 与磁盘不符 —— 上游被改动，需重跑 --write"
            )
        assert denom["popup_total_is_an_observation_not_a_baseline"].strip()

    def test_task64_popup_subset_is_stable_a16_a17_only(self, record: dict) -> None:
        """Task 64 的稳定 popup 子集只含 A16/A17 —— 不随 B/S 文件漂移。"""
        subset = record["denominator"]["popup_owned_by_task_64"]
        assert subset, "Task 64 名下的 popup 子集为空，判据空转"
        for code in subset:
            assert code.startswith(("A16", "A17")), (
                f"Task 64 的 popup 子集出现了非 A16/A17 的 {code}"
            )
