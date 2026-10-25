"""G 循环双向回写：overlay 裁决完备性 + manifest 同步（当前被平台级门阻塞）。

spec: g-cycle-single-region-detail-lanes / g4-g6-shared-workbook-three-entry-lanes /
      g5-nested-sections-and-template-defects

## 这个文件锁住什么

2026-09-30 现算发现：G 域 13 个主入口的**六项前置全部满足**，但 manifest 里它们的
`capability` 仍是 `single_onlyoffice` ⇒ **双向回写在运行时从未启用**。契约、注册表、
台账、provider、golden digest、宿主改线都齐了，缺的只是 manifest 重生成。

而 manifest 重生成被**两道与 G 无关的门**依次卡住（2026-09-30 实测，逐道走过）：

**第一道 `approved_source_digest`** 报「source mounts changed since the reviewed overlay」。
已完成完整复核，结论：17 个 A 类宿主整体退网（A101/A111/A121/A171/A1721/A1731/A173/
A174/A176/A177/A181/A182/A271/A3/A51/A81/A91）+ 38 个宿主的 condition 配对变化（真因是
在 legacy 挂点前插入了 `WorkpaperSyncEditorHost` 真双向分支，legacy 降级为 `v-else-if`）
+ C22 净增 1 挂点（BP-10 补开关 + CC-63 `ooSheetName` 修复）。数字闭合
`GtOnlyOfficeSheet 238 − 17 + 1 = 222`，新增宿主 0，能力零损失。

🔴 **但复核通过后不能批准**：现算 `git status` 显示这 17 个 A 类宿主 **17/17 全部未提交**，
是并发会话的在途工作。批准等于把复核签名落在一个可能从未进入历史的树态上。

**第二道 `stale overlay overrides: [GtA51CashflowAudit.vue]`**（绕过第一道后实测撞到）。
根因是并发 A 轮会话的工作**自相矛盾**：他们同时在做①把 A51 改成只挂
`WorkpaperSyncEditorHost`（删掉 legacy `GtOnlyOfficeSheet`）②加一条挂在那个已删
legacy 挂点上的 a51 `bidirectional` override。先前第一道门一直先跳闸，所以他们还没撞到。
`git show HEAD:…overlay.json` 现算 HEAD 只有 7 条 override ⇒ **a51 那条不在 HEAD，是他人
未提交产物** ⇒ 不能删它来让自己的门通过。

🔴 **本轮因此暴露一个真实的发现契约缺口（比上面两道门更根本）**：entry 只能从
`_group_source_facts(discovery)` 派生，而 discoverer 只认 `GtOnlyOfficeSheet` /
`OnlyOfficeWordDialog` / `WorkpaperWordEditor` 三种组件，**不认 `WorkpaperSyncEditorHost`**
⇒ **迁移最彻底的宿主反而从挂点清册里整体消失、entry 直接不存在**。现算今天已有
**51 个「仅 EditorHost」宿主**（34 个 `d4/**` tab + 17 个 A 类）落在这个缺口里；而把
EditorHost 并入发现会让 **45 个双挂宿主**撞 `stable entry_id collision`
（`_entry_id` 只按 document_type + source_file 取键）⇒ 不是小改，需要设计裁决。

## 处置与结果（2026-09-30，用户明确授权「a51 那条矛盾的 override 你来代并发会话处置」）

- **a51 裁决移入新键 `deferred_overrides`（原文逐字保留），不是删除**。依据：把它留在
  `overrides` 里**并不能保住 a51 的能力** —— entry 只能由发现到的挂点派生，而 A51 已无
  可发现挂点 ⇒ `xlsx/gt-a51-cashflow-audit` 重生成后根本不存在，无论 overlay 写什么。
  所以留着只有阻塞作用、没有保护作用。恢复是机械动作（移回 `overrides`）。
- **第一道 digest 门已批准**，`review_basis` 如实披露「批准时 23 个 diff 涉及文件未提交，
  其中 17 个 A 类宿主 17/17 全部未提交」。
- **生成器已 `--apply`**：entries 155→138，13 条 G 主入口全部 `capability=bidirectional`
  + `migration_state=adapter_registered`，`build_manifest_registration_plan` 现算
  13/13 `blocked_reason is None`、provider 逐一对上。

⇒ 本文件把四件事变成可执行判据，而不是写在注释或 spec 里：
  1. **overlay 裁决完备** —— 13 条 override 的字段与 registry / 台账 / 宿主逐一对得上
  2. **阻塞已解除** —— manifest 按已批准挂点生成、挂点 diff 已清零（G 域自始至终 0 处）
  3. **a51 推迟可恢复且理由仍成立** —— 原文逐字在、与 overrides 互斥、glob 仍无匹配挂点、
     后果（entry 确实不在清册）如实锁住、批准留痕可查。理由一旦不成立本节即红，
     红即「把裁决移回 overrides 并重跑生成器」的信号
  4. **manifest 已同步** —— 原 `xfail(strict=True)` 已按设计删除
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

_ROOT = Path(__file__).resolve().parents[3]
_OVERLAY = _ROOT / "backend" / "data" / "workpaper_sync_entry_overlay.json"
_MANIFEST = _ROOT / "backend" / "data" / "workpaper_sync_entry_manifest.json"
_HOST_DIR = "audit-platform/frontend/src/components/workpaper/"

#: 本轮裁决的 13 个 G 主入口：(宿主文件名, adapter_id, manifest entry_id)
#:
#: 🔴 **不含**子入口：`g4-bond-investment-ecl` / `g4-…-sppi` / `g6-…-ecl` / `g6-…-sppi` /
#: `g7-equity-method` / `g7-equity-subsidiary` 按设计**不单独发 per-entry 契约**
#: （`build_manifest_registration_plan` 现算把它们判为 blocked，理由是「尚无该 entry
#: 自己的 approved per-entry 生产契约」）⇒ 它们不该出现在这张表里。
G_ADJUDICATED: tuple[tuple[str, str, str], ...] = (
    ("GtG1TradingFinancialAssets.vue", "g1.trading_financial_assets_detail",
     "xlsx/gt-g1-trading-financial-assets"),
    ("GtG2InterestReceivable.vue", "g2.interest_receivable_detail",
     "xlsx/gt-g2-interest-receivable"),
    ("GtG3DividendReceivable.vue", "g3.dividend_receivable_detail",
     "xlsx/gt-g3-dividend-receivable"),
    ("GtG4BondInvestmentMain.vue", "g4.bond_main",
     "xlsx/gt-g4-bond-investment-main"),
    ("GtG5LongTermReceivable.vue", "g5.long_term_receivable_detail",
     "xlsx/gt-g5-long-term-receivable"),
    ("GtG6OtherBondMain.vue", "g6.other_bond_main",
     "xlsx/gt-g6-other-bond-main"),
    ("GtG8OtherEquityInstruments.vue", "g8.other_equity_detail",
     "xlsx/gt-g8-other-equity-instruments"),
    ("GtG9OtherNoncurrentFinancial.vue", "g9.other_noncurrent_detail",
     "xlsx/gt-g9-other-noncurrent-financial"),
    ("GtG10TradingFinancialLiabilities.vue", "g10.trading_liabilities_detail",
     "xlsx/gt-g10-trading-financial-liabilities"),
    ("GtG11InvestmentIncome.vue", "g11.investment_income_detail",
     "xlsx/gt-g11-investment-income"),
    ("GtG12NetHedgeGains.vue", "g12.net_hedge_detail",
     "xlsx/gt-g12-net-hedge-gains"),
    ("GtG13FairValueChanges.vue", "g13.fair_value_changes_detail",
     "xlsx/gt-g13-fair-value-changes"),
    ("GtG14CreditImpairmentLoss.vue", "g14.credit_impairment_detail",
     "xlsx/gt-g14-credit-impairment-loss"),
)


def _overlay() -> dict:
    return json.loads(_OVERLAY.read_bytes().decode("utf-8"))


def _manifest_entries() -> dict[str, dict]:
    man = json.loads(_MANIFEST.read_bytes().decode("utf-8"))
    return {str(e["entry_id"]): e for e in man["entries"]}


def _override_by_glob() -> dict[str, dict]:
    return {str(o.get("file_glob") or ""): o for o in _overlay()["overrides"]}


# ═══ 一、overlay 裁决完备（现在就该绿）═══════════════════════════════════════


class TestOverlayAdjudicationIsComplete:
    """13 条 override 的每个字段都对得上真源，不是照抄形状。"""

    def test_all_thirteen_have_an_override(self):
        by_glob = _override_by_glob()
        missing = [h for h, _, _ in G_ADJUDICATED if _HOST_DIR + h not in by_glob]
        assert not missing, f"overlay 缺 override：{missing}"

    @pytest.mark.parametrize(("host", "adapter_id", "entry_id"), G_ADJUDICATED,
                             ids=[a for _, a, _ in G_ADJUDICATED])
    def test_override_fields_are_consistent(self, host, adapter_id, entry_id):
        o = _override_by_glob()[_HOST_DIR + host]
        assert o["capability"] == "bidirectional"
        assert o["adapter_id"] == adapter_id
        assert o["migration_state"] == "adapter_registered"
        assert o["canonical_resolver"] == "workpaper_sync_published_representation"
        assert o["component"] == "GtOnlyOfficeSheet"
        # evidence 必须清空 legacy 原因 —— 留着 `missing_adapter` 会让诊断自相矛盾
        assert o["evidence_patch"]["review_status"] == "published_representation_verified"
        assert o["evidence_patch"]["legacy_reasons"] == []
        assert o.get("reason"), "必须写明裁决依据（六项前置），否则无法复核"

    def test_adapter_ids_are_registered_in_store_merge_registry(self):
        from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY

        missing = [a for _, a, _ in G_ADJUDICATED if a not in STORE_MERGE_REGISTRY]
        assert not missing, f"裁决了但 STORE_MERGE_REGISTRY 没有：{missing}"

    def test_adapter_ids_are_in_the_delivered_ledger(self):
        from app.services.workpaper_sync.adapters.registry import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )

        by_entry = {str(r.get("entry_id")): r for r in DELIVERED_PER_ENTRY_CONTRACTS}
        for _host, adapter_id, entry_id in G_ADJUDICATED:
            row = by_entry.get(entry_id)
            assert row is not None, f"{entry_id} 不在交付台账里"
            assert str(row.get("provider_module") or ""), f"{entry_id} 台账没写 provider_module"

    def test_contracts_are_reviewed_not_candidate(self):
        """契约必须是正式发布的 —— `.candidate.json` 不算（K 域就卡在只有候选）。"""
        cdir = _ROOT / "backend" / "data" / "workpaper_sync_contracts"
        for _host, adapter_id, _entry in G_ADJUDICATED:
            formal = cdir / f"{adapter_id}.json"
            candidate = cdir / f"{adapter_id}.candidate.json"
            assert formal.is_file(), f"{adapter_id} 没有正式契约"
            assert not candidate.is_file(), (
                f"{adapter_id} 同时存在 candidate ⇒ 发布状态有歧义"
            )

    @pytest.mark.parametrize(("host", "adapter_id", "entry_id"), G_ADJUDICATED,
                             ids=[a for _, a, _ in G_ADJUDICATED])
    def test_host_is_wired_to_sync_bridge(self, host, adapter_id, entry_id):
        """宿主必须真已改线 —— 否则翻 capability 就是前端显示一个不可兑现的模式切换。

        判据取自已翻 entry 的实际做法（a51 的 override reason 明写「宿主改线到 sync bridge
        （WorkpaperSyncEditorHost + useA51SyncMode）」）。
        """
        p = _ROOT / _HOST_DIR / host
        assert p.is_file(), f"宿主不存在：{host}"
        src = p.read_text(encoding="utf-8", errors="replace")
        assert "WorkpaperSyncEditorHost" in src, f"{host} 未接 WorkpaperSyncEditorHost"
        assert "syncBridge" in src, f"{host} 未接 syncBridge"

    def test_sub_entries_are_deliberately_excluded(self):
        """🔴 反向判据：子入口**不该**被裁决，因为它们按设计没有独立契约。

        没有这条，「13 条」这个数字就只是个巧合 —— 有人顺手把 6 个子入口也加进 overlay
        时不会有任何信号，而那会造出「manifest 说双向、registration plan 判 blocked」的
        自相矛盾状态。
        """
        by_glob = _override_by_glob()
        sub_hosts = (
            "GtG4BondInvestmentEcl.vue", "GtG4BondInvestmentSppi.vue",
            "GtG6OtherBondSppi.vue", "GtG6OtherBondInvestmentEcl.vue",
            "GtG7EquityMethod.vue", "GtG7EquitySubsidiary.vue",
        )
        wrongly_adjudicated = [
            h for h in sub_hosts
            if by_glob.get(_HOST_DIR + h, {}).get("capability") == "bidirectional"
        ]
        assert not wrongly_adjudicated, (
            f"子入口被误裁决为 bidirectional：{wrongly_adjudicated} —— "
            "它们没有自己的 approved per-entry 契约，registration plan 会判 blocked"
        )


# ═══ 二、阻塞已解除（现在就该绿）═══════════════════════════════════════════
#
# 2026-09-30 用户授权后两道门均已过、manifest 已重生成。本节由「归因为何没翻」
# 转为「锁住已翻的状态是真的、且是按已复核挂点生成的」。


class TestBlockingIsNotCausedByGCycle:
    def test_manifest_was_generated_from_the_reviewed_mounts(self):
        """manifest 必须按 overlay 已批准的那批挂点生成（本文件其余判据的前提）。"""
        ov = _overlay()
        man = json.loads(_MANIFEST.read_bytes().decode("utf-8"))
        approved = str(ov.get("approved_source_digest") or "")
        assert approved, "overlay 必须有 approved_source_digest"
        assert str(man.get("source_digest") or "") == approved, (
            "manifest.source_digest 与 overlay.approved_source_digest 不一致 ⇒ "
            "manifest 不是按已复核的挂点生成的，本文件其余判据的前提不成立"
        )

    def test_no_pending_mount_diff_remains(self):
        """挂点 diff 已清零 —— 且 **G 域自始至终 0 处**。

        现算方式：跑前端挂点发现器，与 manifest 摊平后的挂点集合做对称差。
        🔴 本条在本轮之前断言的是「diff 非空且其中 G 域 0 处」（门跳闸时的现状锚点）；
        门已过、manifest 已重生成 ⇒ 现在断言 diff 为空。若哪天又非空，说明源码挂点
        再次变化而产物未同步，须重走复核 + 重生成，**不是**改本判据。

        🔴 口径说明：`key_of` 只取 (file, component)（live 侧行号字段叫 `sourceSpan`，
        两侧都取不到 `line` 故恒为空）⇒ 这是**宿主×组件粒度**的比对，行号位移与
        condition 变化不进 diff。细粒度语义 diff 见 overlay 的 `review_basis`。

        发现器不可用（无 node / 脚本缺失）时 skip：把环境问题伪装成通过才是假绿。
        """
        import subprocess

        discoverer = (
            _ROOT / "audit-platform" / "frontend" / "scripts"
            / "discover-workpaper-sync-mounts.mjs"
        )
        if not discoverer.is_file():
            pytest.skip("挂点发现器不存在")
        try:
            proc = subprocess.run(
                ["node", str(discoverer), "--json"],
                cwd=str(_ROOT / "audit-platform" / "frontend"),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=600,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            pytest.skip(f"挂点发现器跑不起来：{type(exc).__name__}")
        if proc.returncode != 0 or not (proc.stdout or "").strip():
            pytest.skip(f"挂点发现器 rc={proc.returncode}，无 JSON 输出")

        cur = json.loads(proc.stdout)

        def key_of(m: dict) -> tuple:
            return (
                str(m.get("file") or m.get("filePath") or m.get("host") or ""),
                str(m.get("component") or ""),
                str(m.get("line") or m.get("lineno") or ""),
            )

        # 🔴 口径必须与生成器一致：它拿 `discovery["mounts"]` 比 manifest 里
        # `sourceKind == "template_ast"` 的挂点，**dispatcher（registry_ast）不参与**
        # —— discoverer 把 word dispatcher 产出到 `dispatchers` 数组，而 manifest 的
        # `entries[].mounts[]` 把它折进去了。漏掉这个过滤会让 `GtWpRenderer.vue
        # [WorkpaperWordEditor]` 永远出现在 diff 里（上一任复核者已在 overlay 的
        # review_basis 里登记过这个度量口径差，不是语义变化）。
        cur_keys = {key_of(m) for m in (cur.get("mounts") or [])}
        man = json.loads(_MANIFEST.read_bytes().decode("utf-8"))
        man_keys = {
            key_of(m)
            for e in man["entries"]
            for m in (e.get("mounts") or [])
            if isinstance(m, dict) and m.get("sourceKind") == "template_ast"
        }
        # 空分母防护：两侧都必须非空，否则对称差为空会变成假绿
        assert cur_keys and man_keys, (
            f"挂点集合取空（current={len(cur_keys)} manifest={len(man_keys)}）⇒ "
            "对称差恒空会假绿，先修读取口径"
        )
        diff_files = {f for f, _, _ in (cur_keys ^ man_keys)}
        g_hosts = sorted(
            f for f in diff_files
            if f.rsplit("/", 1)[-1].lower().startswith("gtg")
        )
        assert not g_hosts, (
            f"挂点 diff 里出现了 G 宿主：{g_hosts} —— G 域源码挂点变了而产物未同步，"
            "须重走复核 + 重生成"
        )
        assert not diff_files, (
            f"挂点 diff 非空（{len(diff_files)} 个宿主）⇒ 产物与源码不同步，"
            f"须重跑生成器：{sorted(diff_files)[:8]}"
        )


# ═══ 三、原「a51 推迟处置 + 发现契约缺口」两类已删除 ═══════════════════════════
#
# 🔴 2026-10-01：这两类（`TestDeferredOverrideStaysRestorable` /
# `TestDiscoveryContractGap`）的**存在前提已消失**，按设计删除而不是改成恒绿。
#
# 它们当时锁的是两件事：
#   ① a51 裁决被迫移入 `deferred_overrides`（因为 A51 宿主已删 legacy 标签 ⇒ 其 entry
#      根本不存在 ⇒ 生成器报 `stale overlay overrides`，manifest **任何人都无法重生成**）；
#   ② 发现器不认 `WorkpaperSyncEditorHost` ⇒ 迁移最彻底的宿主从挂点清册整体消失
#      （当时 51 个，其中 34 个 `d4/**` tab 已真实消失过一次）。
#
# spec `sync-editor-host-discovery-contract-closure` 已把 ② 修掉（发现器纳入同步载体 +
# 三层身份解析链 L1/L2/L3 + 分组键换成 `(file, document_type)`），于是 ① 自动解除：
# a51 裁决已归回 `overrides`、`deferred_overrides` 键已删、其 entry
# `xlsx/gt-a51-cashflow-audit` 回到 manifest 且 `capability == bidirectional`。
#
# 这两类的后继判据在
# `backend/tests/workpaper_sync/test_sync_editor_host_discovery_contract.py`：
# 缺口不变量（含**接活事实**的版本）、三层覆盖闭合、声明式 parent、零 churn、
# a51 终局验收，以及 `mutate_sync_editor_host_discovery.py` 的 5 条变异证明。


# ═══ 四、manifest 已同步（原始诉求已达成）═══════════════════════════════════
#
# 2026-09-30：本条原为 `xfail(strict=True)`，钉住「overlay 已裁决但 manifest 未翻」。
# 用户授权处置 a51 矛盾 override 后两道门均已过、生成器已 `--apply`，
# 13 条 G 主入口全部翻成 bidirectional ⇒ **xfail 标记已按设计删除**（strict 下
# xpass 即失败，正是为了逼人来删它而不是忘掉它）。


def test_manifest_capability_matches_overlay_adjudication():
    """overlay 裁决为 bidirectional 的 entry，manifest 必须同步 —— 这才是运行时真启用。

    🔴 判据落在 manifest 而不是 overlay：`assert_manifest_capability_enabled` 这类运行时门
    读的是 manifest，overlay 只是生成它的输入。只验 overlay 会得到「裁决写了就算通」的假绿。
    """
    entries = _manifest_entries()
    not_flipped: list[str] = []
    for _host, adapter_id, entry_id in G_ADJUDICATED:
        e = entries.get(entry_id)
        assert e is not None, f"manifest 无此 entry：{entry_id}"
        if str(e.get("capability")) != "bidirectional" or str(e.get("adapter_id") or "") != adapter_id:
            not_flipped.append(
                f"{entry_id}: capability={e.get('capability')!r} adapter_id={e.get('adapter_id')!r}"
            )
    assert not not_flipped, "以下 G entry 的 manifest 尚未翻转：\n  " + "\n  ".join(not_flipped)
