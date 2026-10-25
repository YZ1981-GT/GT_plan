# -*- coding: utf-8 -*-
r"""K 循环规划期登记的缺陷 / 空分母 —— **已修复或已晋级，且必须保持**。

spec: `k-cycle-sync-foundation-and-first-canary`（Task 22/23/27 晋级）
      `k1-k7-inlined-iife-hosts-and-orphan-cleanup`（BP-5 删 orphan / BP-7 notice / BP-8 lane 1）
      `k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub`（BP-8 lane 2 / Task 18 契约）

═══ 为什么从 Task 53 搬到这里（与 H/I/J `test_*_cycle_registered_defects_fixed.py` 同款）═══

`test_task53_k_cycle_migration.py` 是**规划期**快照，判据是「实测 == slice 登记」——
缺陷**还在**、契约**还没有**才绿。三份 K spec 交付后这些判据只会逼人把修复改回去。
判据于是**翻面**：

  ① slice / deletion_plan 登记保持原值（append-only，修复前的历史事实，改成新值同样打红）；
  ② 现算状态 == `k_foundation_facts` 里的**账本**（BP-5 删除账本 / BP-8 收敛账本 /
     BP-7 挂载账本 / 晋级账本），精确等值而非「≥」；
  ③ 行号类登记只比**文件 + 行内容**：`.vue` 行号会随任何编辑漂移（方法论铁律 ②），
     slice 冻结的 `#Lnn` 不再作为判据，但该行承载的形态必须仍在该文件里。

🔴 扫描口径共用 Task 53 的实现，不另抄一份（两个扫描器各自漂移正是要防的东西）。
"""
from __future__ import annotations

import pathlib
import re
from collections import Counter

import pytest

from tests.workpaper_sync.k_foundation_facts import (
    BP5_DELETED_ORPHAN_NAMES,
    BP5_DUALMODE_ENTRIES_REMAINING,
    BP5_HEALTH_AFTER_HOST_CONVERGENCE,
    BP7_NOTICE_MOUNTED_ENTRIES,
    K_BIDIRECTIONAL_ENTRIES,
    K_ENTRY_ID_BY_INDEX,
    K_PUBLISH_BLOCKED,
    K_REVIEWED_CONTRACTS,
    contract_dir_split,
    is_fixed_slot_exempt,
)
from tests.workpaper_sync.test_task53_k_cycle_migration import (
    DELETION_PLAN_PATH,
    FULL_MANIFEST_PATH,
    MANIFEST_SLICE_PATH,
    NOTICE_COMPONENT_NAME,
    OVERLAY_PATH,
    PILOT_CONTRACT_OWNERS,
    ROOT,
    SHARED_BASE,
    WP_COMPOSABLES,
    _ENTROPY,
    _HARDCODED_PATTERNS,
    _display_seq_sites,
    _family_of,
    _hardcoded_hits,
    _k_cycle_files,
    _load,
    _positional_identity_hits,
    _resolve_repo,
    _statement_edges_to,
    _strip_comments,
    _wp_code_of,
)

#: K10 / K1-9 / K2 草案原件归档处（晋级的 6 份草案已从契约目录移走）
ARCHIVED_DRAFT_DIR = (
    ROOT / ".kiro" / "specs"
    / "k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub"
    / "evidence" / "superseded-candidate-contracts"
)
#: K 循环仍是草案的契约（未晋级）
K_REMAINING_CANDIDATES = {
    "k2.adjudication_derived.candidate.json",
}


def _file(ref: str) -> str:
    return ref.split("#L")[0]


def _n_of(entry_id: str) -> int:
    m = re.match(r"^xlsx/gt-k(1[0-3]|[1-9])-", entry_id)
    assert m, entry_id
    return int(m.group(1))


@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return _load(MANIFEST_SLICE_PATH)


@pytest.fixture(scope="module")
def deletion_plan() -> dict:
    return _load(DELETION_PLAN_PATH)


@pytest.fixture(scope="module")
def full_manifest() -> dict:
    return _load(FULL_MANIFEST_PATH)


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return _k_cycle_files()


# ════════════════════════════════════════════════════════════════════════════
# 晋级：契约 / manifest（Property 3 & 20 的分母从空变实）
# ════════════════════════════════════════════════════════════════════════════
class TestPromotionLedger:
    def test_contract_ownership_with_k_production_contracts(
        self, manifest_slice: dict
    ) -> None:
        """原 `test_no_pilot_contract_belongs_to_the_k_cycle`。

        🔴 遍历只对**契约**（有 `review_status`）—— 目录里另有 L 循环的键映射表。
        """
        iso = manifest_slice["cross_entry_isolation"]
        k_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        contracts, _others = contract_dir_split()
        assert contracts, "契约目录为空 ⇒ 判据空跑"
        prod: list[str] = []
        cand: list[str] = []
        owners: set[str] = set()
        k_owned: dict[str, str] = {}
        for name, doc in contracts.items():
            owner = (doc.get("review") or {}).get("entry_id")
            if doc.get("review_status") == "candidate":
                cand.append(name)
                assert owner is None, f"{name} 是 candidate 却带 entry_id"
                continue
            prod.append(name)
            assert doc.get("review_status") == "reviewed", name
            assert owner, f"{name} 的 review.entry_id 缺失"
            owners.add(owner)
            if owner in k_ids:
                k_owned[name] = owner
        expected = {
            f"{cid}.json": K_ENTRY_ID_BY_INDEX[n] for n, cid in K_REVIEWED_CONTRACTS.items()
        }
        assert k_owned == expected, f"K 生产契约与晋级账本不符：{k_owned}"
        # slice 是修复前快照：它登记的 pilot 归属与生产清单仍全部在场（只增不减）
        assert PILOT_CONTRACT_OWNERS <= owners
        assert set(iso["production_contract_files"]) <= set(prod)
        # slice 登记的 candidate 若消失，只能是被晋级的 K 草案（归档在 evidence 下）
        vanished = set(iso["candidate_contract_files"]) - set(cand)
        assert all((ARCHIVED_DRAFT_DIR / v).exists() for v in vanished), vanished
        assert {c for c in cand if c.startswith("k")} == K_REMAINING_CANDIDATES

    def test_slice_entries_with_a_contract_equal_the_ledger(
        self, manifest_slice: dict
    ) -> None:
        """原 `test_no_slice_entry_has_a_contract`：分母从 0 变成账本 6 条。"""
        k_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        contracts, _ = contract_dir_split()
        hit = {
            (doc.get("review") or {}).get("entry_id")
            for doc in contracts.values()
        } & k_ids
        assert hit == {K_ENTRY_ID_BY_INDEX[n] for n in K_REVIEWED_CONTRACTS}

    def test_manifest_mirror_keeps_pre_promotion_values(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """原 `test_manifest_mirror_divergence_is_registered_not_silently_equal`。

        slice 镜像仍是 overlay 默认值（历史事实）；live manifest 只对晋级 5 条翻面。
        """
        by_id = {e["entry_id"]: e for e in full_manifest["entries"]}
        default = _load(OVERLAY_PATH)["defaults_by_component"]["GtOnlyOfficeSheet"]
        diverged = 0
        for e in manifest_slice["independent_entries"]:
            n = _n_of(e["entry_id"])
            mirror = e["manifest_mirror"]
            live = by_id[e["entry_id"]]
            assert mirror["capability"] == default["capability"]
            assert mirror["html_store"] == default["html_store"]
            assert "BP-9" in mirror["why_not_adopted"]
            if n in K_BIDIRECTIONAL_ENTRIES:
                assert live["capability"] == "bidirectional", e["entry_id"]
                assert live["adapter_id"] == K_REVIEWED_CONTRACTS[n]
            else:
                assert live["capability"] == mirror["capability"], e["entry_id"]
                assert live["html_store"] == mirror["html_store"]
                assert live["adapter_id"] is None
            if mirror["capability"] != e["capability"]:
                diverged += 1
        assert diverged == 13
        assert any(b["id"] == "BP-9" for b in manifest_slice["blocking_preconditions"])
        for n in K_PUBLISH_BLOCKED:
            assert by_id[K_ENTRY_ID_BY_INDEX[n]]["capability"] == "single_onlyoffice"

    def test_entry_profile_fields_mirror_the_manifest(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """原同名判据：晋级 5 条的 canonical_resolver 改由 representation 解析。"""
        by_id = {e["entry_id"]: e for e in full_manifest["entries"]}
        for e in manifest_slice["independent_entries"]:
            live = by_id[e["entry_id"]]
            n = _n_of(e["entry_id"])
            assert e["editability"] == live["editability"]
            assert e["room_model"] == live["room_model"]
            assert e["mount_count"] == len(live["mounts"])
            assert e["host_path"] == live["host_path"]
            assert e["wp_code_pattern"] in (live.get("wp_match") or {}).get(
                "wp_code_patterns", [])
            if n in K_BIDIRECTIONAL_ENTRIES:
                assert e["canonical_resolver"] == "legacy_sheet_onlyoffice_router"
                assert live["canonical_resolver"] == "workpaper_sync_published_representation"
            else:
                assert e["canonical_resolver"] == live["canonical_resolver"]


# ════════════════════════════════════════════════════════════════════════════
# BP-5：orphan 删除 + 宿主收敛（lane 1）
# ════════════════════════════════════════════════════════════════════════════
class TestBp5OrphanDeletionStaysDone:
    def test_declared_orphans_are_deleted(self, manifest_slice: dict) -> None:
        mods = manifest_slice["orphan_dual_mode_inventory"]["modules"]
        assert len(mods) == 7
        names = {pathlib.Path(m["file"]).name for m in mods}
        assert names == set(BP5_DELETED_ORPHAN_NAMES)
        for m in mods:
            assert not (ROOT / m["file"]).exists(), f"{m['id']}: orphan 又回来了 {m['file']}"

    def test_dual_mode_files_are_exactly_the_six_live_ones(
        self, manifest_slice: dict
    ) -> None:
        files = {
            p.name for p in WP_COMPOSABLES.iterdir()
            if re.fullmatch(r"useK(1[0-3]|[1-9])DualMode\.ts", p.name)
        }
        assert files == {f"useK{n}DualMode.ts" for n in BP5_DUALMODE_ENTRIES_REMAINING}
        live = {pathlib.Path(m["file"]).name for m in
                manifest_slice["orphan_dual_mode_inventory"]["live_modules"]}
        assert files == live

    def test_live_modules_keep_exactly_one_edge_to_the_declared_host(
        self, manifest_slice: dict
    ) -> None:
        for m in manifest_slice["orphan_dual_mode_inventory"]["live_modules"]:
            prod, test = _statement_edges_to(ROOT / m["file"])
            assert len(prod) == 1, (m["id"], prod)
            assert [_file(r) for r in prod] == [_file(r) for r in m["production_consumers"]]
            assert test == []

    def test_legacy_health_is_gone_and_config_is_deliberately_kept(
        self, manifest_slice: dict
    ) -> None:
        """health 13 → 0；config 6 处**有意保留**（K adapter 走 bridge 前不能删）。"""
        inv = manifest_slice["orphan_dual_mode_inventory"]
        assert inv["summary"]["modules_calling_legacy_health_endpoint"] == 13
        health = config = 0
        for m in inv["live_modules"]:
            src = _strip_comments((ROOT / m["file"]).read_text(encoding="utf-8"))
            health += int("/api/workpapers/onlyoffice/health" in src)
            config += int("onlyoffice-config" in src)
        assert health == 0
        assert config == inv["summary"]["modules_calling_legacy_config_endpoint"] == 6

    def test_no_host_calls_the_legacy_health_endpoint(self, manifest_slice: dict) -> None:
        assert manifest_slice["orphan_dual_mode_inventory"]["summary"][
            "hosts_calling_legacy_health_endpoint_directly"] == 7
        n = sum(
            "/api/workpapers/onlyoffice/health"
            in _strip_comments((ROOT / e["host_path"]).read_text(encoding="utf-8"))
            for e in manifest_slice["independent_entries"]
        )
        assert n == BP5_HEALTH_AFTER_HOST_CONVERGENCE == 0

    def test_k_still_contributes_zero_shared_base_edges(self, manifest_slice: dict) -> None:
        """KD-3 结论不变；总数随平台演进（29 → 现算），不再冻结。"""
        prod, test = _statement_edges_to(SHARED_BASE)
        k_edges = [r for r in prod + test if re.search(r"/(GtK\d|k\d+/|useK\d)", r)]
        assert k_edges == []
        assert manifest_slice["orphan_dual_mode_inventory"]["shared_base"][
            "k_cycle_contribution"] == 0

    def test_kd2_carrier_split_still_seven_plus_six(self, manifest_slice: dict) -> None:
        measured = next(
            d for d in manifest_slice["k_cycle_form_differences"]["differences"]
            if d["id"] == "KD-2"
        )["measured"]
        inline_n = dedicated_n = 0
        for code, rec in measured.items():
            host = ROOT / next(
                e["host_path"] for e in manifest_slice["independent_entries"]
                if _wp_code_of(e) == code
            )
            lines = _strip_comments(host.read_text(encoding="utf-8")).split("\n")
            iife = [l for l in lines if re.search(r"const dualMode = \(\(\) =>", l)]
            imp = [l for l in lines if re.search(r"import \{ use%sDualMode \}" % code, l)]
            assert not (iife and imp), code
            if rec["inline_iife_site"]:
                assert len(iife) == 1 and _file(rec["inline_iife_site"]) == host.relative_to(ROOT).as_posix()
                inline_n += 1
            else:
                assert len(imp) == 1, code
                dedicated_n += 1
        assert inline_n == 7 and dedicated_n == 6

    def test_kd7_one_toolbar_segmented_after_comment_strip(
        self, manifest_slice: dict
    ) -> None:
        fooled = 0
        for e in manifest_slice["independent_entries"]:
            raw = (ROOT / e["host_path"]).read_text(encoding="utf-8")
            before = [i for i, l in enumerate(raw.split("\n"), 1) if "el-segmented" in l]
            after = [
                i for i, l in enumerate(_strip_comments(raw).split("\n"), 1)
                if "el-segmented" in l
            ]
            assert len(after) == 1, (e["entry_id"], after)
            assert set(after) <= set(before)
            fooled += int(len(before) > len(after))
        assert fooled >= 10

    def test_plan_must_not_wire_to_targets_are_the_deleted_twins(
        self, deletion_plan: dict
    ) -> None:
        orphan = {m["file"] for m in deletion_plan["orphan_dual_mode_to_delete"]["modules"]}
        named = {t for e in deletion_plan["entries"] for t in e["must_not_wire_to"]}
        assert named == orphan
        assert {pathlib.Path(t).name for t in named} == set(BP5_DELETED_ORPHAN_NAMES)
        assert not any((ROOT / t).exists() for t in named)

    def test_plan_host_inlined_blocks_still_resolve_by_content(
        self, deletion_plan: dict
    ) -> None:
        n = 0
        for e in deletion_plan["entries"]:
            ref = e["host_inlined_block_to_remove"]
            if ref is None:
                continue
            n += 1
            src = _strip_comments(_resolve_repo(ref).read_text(encoding="utf-8"))
            assert len(re.findall(r"const dualMode = \(\(", src)) == 1, ref
        assert n == deletion_plan["counters"]["host_inlined_blocks_to_remove"] == 7


# ════════════════════════════════════════════════════════════════════════════
# BP-8：位置化行身份（lane 1 + lane 2 已全收敛）
# ════════════════════════════════════════════════════════════════════════════
class TestBp8PositionalIdentityStaysFixed:
    @staticmethod
    def _pii(manifest_slice: dict) -> dict:
        return manifest_slice["dynamic_row_identity"]["positional_identity_inventory"]

    def test_slice_keeps_pre_fix_inventory(self, manifest_slice: dict) -> None:
        pii = self._pii(manifest_slice)
        assert pii["total_hits"] == 48 and pii["defect_hits_total"] == 45
        assert pii["family_a_pure_ordinal"]["count"] == 32
        assert pii["family_b_index_as_fallback"]["count"] == 13
        assert pii["family_c_generated_opaque_must_not_be_flagged"]["count"] == 3

    def test_only_fixed_slot_exemptions_and_family_c_remain(
        self, manifest_slice: dict, k_files: list[pathlib.Path]
    ) -> None:
        by_name = {p.name: p for p in k_files}
        defects: list[tuple[str, str]] = []
        fam_c: list[str] = []
        exempt = 0
        for ref, _k, val in _positional_identity_hits(k_files):
            p = by_name[pathlib.Path(_file(ref)).name]
            if is_fixed_slot_exempt(p, val):
                exempt += 1
                continue
            if _family_of(val) == "c":
                fam_c.append(_file(ref))
            else:
                defects.append((ref, val))
        assert defects == [], f"K 又出现位置化行身份：{defects}"
        assert exempt == 3
        slice_c = [_file(r) for r in
                   self._pii(manifest_slice)["family_c_generated_opaque_must_not_be_flagged"]["hits"]]
        assert sorted(fam_c) == sorted(slice_c)

    def test_display_sequence_sites_unchanged_per_file(
        self, manifest_slice: dict, k_files: list[pathlib.Path]
    ) -> None:
        fam_d = self._pii(manifest_slice)["family_d_display_ordinal_must_not_be_flagged"]
        now = Counter(_file(r) for r in _display_seq_sites(k_files))
        assert now == Counter(_file(r) for r in fam_d["hits"])
        assert sum(now.values()) == fam_d["count"] == 38

    def test_hardcoded_template_only_keeps_family_c(
        self, manifest_slice: dict, k_files: list[pathlib.Path]
    ) -> None:
        hs = manifest_slice["dynamic_row_identity"]["hardcoded_scan_result"]
        assert hs["patterns"]["positional_row_id_template"] == 13
        for name in _HARDCODED_PATTERNS:
            if name != "positional_row_id_template":
                assert _hardcoded_hits(k_files, name) == [], name
        tmpl = _hardcoded_hits(k_files, "positional_row_id_template")
        pos = {ref for ref, _k, _v in _positional_identity_hits(k_files)}
        assert set(tmpl) <= pos
        slice_c = {_file(r) for r in
                   self._pii(manifest_slice)["family_c_generated_opaque_must_not_be_flagged"]["hits"]}
        assert {_file(r) for r in tmpl} <= slice_c and len(tmpl) == 2

    def test_declared_dynamic_tables_keep_an_entropy_identity_line(
        self, manifest_slice: dict
    ) -> None:
        dri = manifest_slice["dynamic_row_identity"]
        forbidden = set(dri["forbidden_identity_kinds"])
        for t in dri["tables"]:
            ident = t["row_identity"]
            assert ident["kind"] not in forbidden
            src = _strip_comments(_resolve_repo(ident["source_ref"]).read_text(encoding="utf-8"))
            ok = [
                l for l in src.split("\n")
                if re.search(rf"(?<![\w$]){ident['identity_field']}\s*:", l) and _ENTROPY.search(l)
            ]
            assert ok, f"{t['table_key']}: 文件里找不到带熵的 {ident['identity_field']} 身份行"


# ════════════════════════════════════════════════════════════════════════════
# BP-7：AC 1.4 notice（lane 1 + lane 2：13 宿主全挂）
# ════════════════════════════════════════════════════════════════════════════
class TestBp7NoticeMountedEverywhere:
    def test_slice_keeps_pre_fix_zero_and_all_hosts_mount_now(
        self, manifest_slice: dict
    ) -> None:
        assert manifest_slice["honest_adjudication_summary"][
            "entries_mounting_the_ac14_notice"] == 0
        assert any(b["id"] == "BP-7" for b in manifest_slice["blocking_preconditions"])
        mounted = []
        for e in manifest_slice["independent_entries"]:
            assert e["ui_toolbar_gate"]["mounts_ac14_notice"] is False
            src = _strip_comments((ROOT / e["host_path"]).read_text(encoding="utf-8"))
            if NOTICE_COMPONENT_NAME in src:
                mounted.append(_n_of(e["entry_id"]))
        assert sorted(mounted) == sorted(BP7_NOTICE_MOUNTED_ENTRIES)


# ════════════════════════════════════════════════════════════════════════════
# 静态属性里写模板插值（2026-10-01 复盘抓到：抽凭科目口径收敛时 `2241` 被换成
# `${samplingAccountCode}`，但 6 处 K 弹窗标题是**静态** `title="..."` ⇒ 界面原样显示
# `${samplingAccountCode}`）。K 域已全改成 `:title="`...`"`，此处防回退。
# ════════════════════════════════════════════════════════════════════════════
_STATIC_ATTR_INTERP = re.compile(r"\s(?:title|label|placeholder)=\"[^\"]*\$\{")


class TestNoTemplateInterpolationInStaticAttributes:
    def test_scanner_detects_static_and_ignores_bound(self) -> None:
        assert _STATIC_ATTR_INTERP.search(' title="⚡ 抽凭（科目 ${code}）"')
        assert not _STATIC_ATTR_INTERP.search(' :title="`⚡ 抽凭（科目 ${code}）`"')

    def test_k_domain_has_none(self) -> None:
        from tests.workpaper_sync.k_foundation_facts import k_domain_files

        bad = []
        for p in k_domain_files():
            if p.suffix != ".vue":
                continue
            for i, line in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
                if _STATIC_ATTR_INTERP.search(line):
                    bad.append(f"{p.name}#L{i}")
        assert bad == [], f"静态属性里写了 `${{...}}`（界面会原样显示）：{bad}"
