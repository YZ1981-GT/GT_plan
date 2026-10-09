# -*- coding: utf-8 -*-
"""G 地基判据 GF-P1 / GF-P2 / GF-P3：FC 适用性重裁 · 两条「缺陷不存在」· 逐 entry 阻塞。

spec: `g-cycle-sync-foundation-and-first-canary` · Task 2
　　　Requirements 1.1 / 1.2 / 1.3 / 1.4

═══ 为什么另起文件（GF-P21 要求显式说明）═══

既有 G 产物 `test_task49_g_cycle_migration.py` 属 **umbrella Task 49**（冻结 slice 的交付物），
3,147 行。本 spec 是它的**下游实施 spec**，Property 编号自成一套（`GF-P{N}`）。
把 20 条下游判据塞进上游守卫会让「slice 冻结事实」与「下游实施判据」混在一个文件里，
改一处分不清动了谁的基线。F 循环已确立的做法就是每 spec 独立判据文件
（`test_f1_property1_5_entry_selectable.py` / `test_f2_p3_p4_p6_p9_p10_red_baselines.py` …），
本文件照它。上游 `test_task49_g_cycle_migration.py` **未被替换、未被改动**。

═══ GF-P1：FC-1~FC-13 在 G 的适用性重裁 ═══
三条「不适用/不成立」必须有**正向证据**，不是「没查到所以不适用」：
* FC-3（一 entry 恰一 template_ref）→ `belongs_to_entries` 复数字段实证 13 册覆盖 17 entry
* FC-8（OCR 第二写入方）→ G 全仓 OCR 零命中
* FC-11（prefill `items` 型死配置）→ 47 个 G 块全 `cells`、零 `items`

═══ GF-P2：两条「缺陷不存在」现算成立 ═══
虚报与漏报同罪：不得为「对齐 F 的 BP 清单」而登记不存在的缺陷，
但**必须有判据锁住它们确实不存在**，且将来一旦出现要打红。

═══ GF-P3：逐 entry 阻塞取 slice 字段，覆盖 17 条全集 ═══
🔴 本轮现算发现 slice **内部不一致**（详见
`evidence/task1-slice-review-and-adjudication.md` §三）：BP-7 正文只覆盖 G6-sppi，
但 9 条 entry 的 `blocked_by` 都列了 BP-7。判据按**两条并存**处置 ——
①按 slice 逐元素断言（锁冻结事实）②另立子判据锁「实际缺陷面 == {G6-sppi}」（锁正文事实）。
既不抹平 slice，也不伪造 8 处不存在的缺陷。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

SLICE_PATH = _BACKEND / "data" / "workpaper_sync_g_cycle_manifest_slice.json"
PREFILL_PATH = _BACKEND / "data" / "prefill_formula_mapping.json"
TPL_G = _BACKEND / "wp_templates" / "G"
FRONTEND = _REPO / "audit-platform" / "frontend" / "src"

#: 本 spec 的 17 条 entry 全集（slice `independent_entries`，按 entry_id 排序无关）。
EXPECTED_ENTRY_IDS: frozenset[str] = frozenset(
    {
        "xlsx/gt-g1-trading-financial-assets",
        "xlsx/gt-g2-interest-receivable",
        "xlsx/gt-g3-dividend-receivable",
        "xlsx/gt-g4-bond-investment-main",
        "xlsx/gt-g4-bond-investment-sppi",
        "xlsx/gt-g4-bond-investment-ecl",
        "xlsx/gt-g5-long-term-receivable",
        "xlsx/gt-g6-other-bond-main",
        "xlsx/gt-g6-other-bond-sppi",
        "xlsx/gt-g6-other-bond-investment-ecl",
        "xlsx/gt-g8-other-equity-instruments",
        "xlsx/gt-g9-other-noncurrent-financial",
        "xlsx/gt-g10-trading-financial-liabilities",
        "xlsx/gt-g11-investment-income",
        "xlsx/gt-g12-net-hedge-gains",
        "xlsx/gt-g13-fair-value-changes",
        "xlsx/gt-g14-credit-impairment-loss",
    }
)


@pytest.fixture(scope="module")
def slice_doc() -> dict:
    return json.loads(SLICE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def entries(slice_doc: dict) -> dict[str, dict]:
    return {e["entry_id"]: e for e in slice_doc["independent_entries"]}


# ═══════════════════════════════════════════════════════════════════════════
# GF-P1：FC 适用性重裁 —— 三条「不适用/不成立」各有正向证据
# ═══════════════════════════════════════════════════════════════════════════


class TestGfP1FcReinterpretation:
    """Validates: 1.1, 1.2"""

    def test_entry_set_is_exactly_17(self, entries: dict[str, dict]) -> None:
        """17 条全集锁死 —— 少一条则后续所有「覆盖全集」判据都失去分母。"""
        assert set(entries) == EXPECTED_ENTRY_IDS, (
            f"多出: {sorted(set(entries) - EXPECTED_ENTRY_IDS)}\n"
            f"缺失: {sorted(EXPECTED_ENTRY_IDS - set(entries))}"
        )

    # ── FC-3 不成立：belongs_to_entries 复数字段实证 ─────────────────────
    def test_fc3_injective_template_mapping_does_not_hold(self, slice_doc: dict) -> None:
        """FC-3「一 entry 恰一 template_ref」的**单射**在 G 不成立（⇒ GC-1）。

        正向证据：`authoritative_templates.files[]` 里存在 `belongs_to_entry=null` 且
        `belongs_to_entries` 为多元素列表的条目（G4 / G6 各一），
        它们各覆盖 3 条 entry ⇒ 13 张 owner 模板覆盖 17 条 entry。
        """
        files = slice_doc["authoritative_templates"]["files"]
        plural = {
            f["name"]: f["belongs_to_entries"]
            for f in files
            if f.get("belongs_to_entries")
        }
        assert plural, (
            "未找到任何 belongs_to_entries 复数字段 —— FC-3 不成立的正向证据缺失。"
            "若 slice 真的改回单射，本 spec 的 GC-1 裁决须重审，不得静默通过。"
        )
        # 逐条：复数字段必须真的是多元素，且 belongs_to_entry 必须为 null（不硬塞给某一方）
        for name, ids in plural.items():
            assert len(ids) >= 2, f"{name} 的 belongs_to_entries 只有 {len(ids)} 条，不构成 1:N"
            single = next(f for f in files if f["name"] == name).get("belongs_to_entry")
            assert single is None, (
                f"{name} 同时有 belongs_to_entry={single!r} 与 belongs_to_entries —— "
                "两个字段并存会让「归属」有两个真源"
            )
        # 满射 + 唯一认领：owner 模板认领的 entry 并集 == 17 条全集，且每条恰被一张认领
        claimed: dict[str, list[str]] = {}
        for f in files:
            names = f.get("belongs_to_entries") or (
                [f["belongs_to_entry"]] if f.get("belongs_to_entry") else []
            )
            for eid in names:
                claimed.setdefault(eid, []).append(f["name"])
        assert set(claimed) == EXPECTED_ENTRY_IDS, (
            f"owner 模板并集 != entry 全集\n"
            f"未被认领: {sorted(EXPECTED_ENTRY_IDS - set(claimed))}\n"
            f"认领了非本 spec entry: {sorted(set(claimed) - EXPECTED_ENTRY_IDS)}"
        )
        multi_claim = {k: v for k, v in claimed.items() if len(v) != 1}
        assert not multi_claim, f"以下 entry 未被**恰一张**模板认领: {multi_claim}"

    def test_fc3_mutation_injective_assertion_would_fail(self, slice_doc: dict) -> None:
        """自省变异：若把 FC-3 改回「成立」（断言单射），与实测矛盾 ⇒ 必红。

        这里**正向执行**那个错误断言并要求它失败 —— 证明判据不空转。
        """
        files = slice_doc["authoritative_templates"]["files"]
        owners = [f for f in files if f.get("belongs_to_entry") or f.get("belongs_to_entries")]
        # 错误断言 = 「每张 owner 模板恰服务 1 条 entry」
        injective = all(
            len(f.get("belongs_to_entries") or [f.get("belongs_to_entry")]) == 1
            for f in owners
        )
        assert not injective, (
            "单射断言居然成立 —— 说明 G4/G6 的 1:N 事实已从 slice 消失，"
            "GC-1 的裁决基础不存在了"
        )

    # ── 🔴 FC-8 **适用**（spec 原判「不适用」经现算不成立）─────────────────
    #
    # spec requirements.md 写「OCR ✅ 全仓 **零命中** ⇒ FC-8 在 G 不适用」，
    # design.md §FC 适用性重裁写「FC-8 🔴 **不适用** | G 循环全仓零 OCR 命中」。
    # 本轮按**真实端点字面量** `d4/contract-ocr`（workpaper 域唯一 OCR 写入端点）现算，
    # G 循环实测 **10 个 entry** 的凭证检查 / 盘点 tab 都有 OCR 写入路径（见下方基线）。
    # 原判为何会错：那次只扫了顶层 `GtG*.vue` / `useG*.ts`，而 OCR 站点在
    # 子目录 tab 组件（`g1-trading-financial-assets/inspection/G1TabVoucherCheck.vue` 等）
    # 与 `src/composables/useG6EclVoucherCheck.ts`（不在 `components/workpaper/composables/` 下）。
    #
    # 重裁：**FC-8 适用，但对本批受管区无第二写入方** —— OCR 写入方全部落在
    # **非受管 sheet** 的 store 键上（凭证检查 / 监盘表）。这不是「不适用」，
    # 是「适用且当前不冲突」，两者的判据形态完全不同：后者必须逐 entry 证明
    # 「OCR 目标键 ∩ 受管键 == ∅」，并在将来某 lane 把凭证检查表纳入受管时**打红**。

    #: workpaper 域**唯一**的 OCR 写入端点字面量（`services/apiPaths` 里的
    #: `/api/ai/ocr/*` 与 `evidence/ocr/*` 属证据治理中心，不写底稿 store）。
    _OCR_ENDPOINT = "d4/contract-ocr"

    #: G 循环（除 G0/G7）带 OCR 写入路径的文件 → 所属 entry 的 wp_code。
    #: 2026-09-27 按 `_OCR_ENDPOINT` 字面量现算。
    OCR_WRITE_SITES: dict[str, str] = {
        "components/workpaper/g1-trading-financial-assets/inspection/G1TabSecuritiesCount.vue": "G1",
        "components/workpaper/g1-trading-financial-assets/inspection/G1TabVoucherCheck.vue": "G1",
        "components/workpaper/g2-interest-receivable/G2TabVoucherCheck.vue": "G2",
        "components/workpaper/g4-bond-investment-ecl/voucher/G4TabVoucherCheck.vue": "G4",
        "composables/useG6EclVoucherCheck.ts": "G6",
        "components/workpaper/composables/useG8VoucherCheck.ts": "G8",
        "components/workpaper/g8-other-equity-instruments/voucher/G8TabVoucherCheck.vue": "G8",
        "components/workpaper/g9-other-noncurrent-financial/voucher/G9TabVoucherCheck.vue": "G9",
        "components/workpaper/g10-trading-financial-liabilities/voucher/G10TabVoucherCheck.vue": "G10",
        "components/workpaper/g12-net-hedge-gains/voucher/G12TabVoucherCheck.vue": "G12",
    }

    def test_fc8_is_applicable_in_g_cycle_contrary_to_spec(self) -> None:
        """🔴 FC-8 在 G **适用**：OCR 写入站点现算非空，且与登记基线逐项一致。"""
        hits: dict[str, str] = {}
        for p in FRONTEND.rglob("*"):
            if p.suffix not in (".ts", ".vue") or not p.is_file():
                continue
            rel = p.relative_to(FRONTEND).as_posix()
            # 只看 G 循环资产：路径含 g{n}- 目录 或 文件名带 G{n}
            if not re.search(r"(^|/)g(?:[1-9]|1[0-4])-|G(?:[1-9]|1[0-4])(?![0-9])", rel):
                continue
            if re.search(r"(^|/)g[07]-|G[07](?![0-9])", rel):  # G0 / G7 已排除
                continue
            if "__tests__" in rel:
                continue
            try:
                txt = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if self._OCR_ENDPOINT in txt:
                hits[rel] = ""
        assert hits, (
            f"按 {self._OCR_ENDPOINT!r} 现算 G 循环 OCR 写入站点为空 —— "
            "若 OCR 真的全被移除，则 spec 的「FC-8 不适用」重新成立，本判据须改写；"
            "若只是探针失效，修探针不要改结论"
        )
        assert set(hits) == set(self.OCR_WRITE_SITES), (
            "OCR 写入站点集合漂移（FC-8 的覆盖面变了）\n"
            f"新增: {sorted(set(hits) - set(self.OCR_WRITE_SITES))}\n"
            f"消失: {sorted(set(self.OCR_WRITE_SITES) - set(hits))}"
        )

    def test_fc8_ocr_targets_disjoint_from_managed_store_keys(
        self, entries: dict[str, dict]
    ) -> None:
        """重裁的实质判据：OCR 写入方的 store 键与**受管**主表键不相交。

        canary G2 逐值实证：受管键 `G2-2-detail-rows`（`useG2Detail.ts` 的 `STORAGE_KEY`），
        而 `G2TabVoucherCheck.vue` 写 `G2-8-rows` / `G2-8-audit-note` / `G2-8-audit-conclusion`
        ⇒ 交集为空。将来某 lane 把凭证检查表纳入受管，本判据立刻打红。
        """
        managed_keys = {
            e["html_counterpart"]["transport_key_shape"] for e in entries.values()
        }
        assert len(managed_keys) == 17, f"受管键去重后不是 17 个: {sorted(managed_keys)}"
        key_literal = re.compile(r"['\"](G(?:[1-9]|1[0-4])-[A-Za-z0-9\-]+)['\"]")
        collisions: list[str] = []
        for rel in self.OCR_WRITE_SITES:
            p = FRONTEND / rel
            if not p.exists():
                collisions.append(f"{rel}: 文件不存在（基线过期）")
                continue
            txt = p.read_text(encoding="utf-8")
            for k in set(key_literal.findall(txt)) & managed_keys:
                collisions.append(f"{rel} 写受管键 {k!r}")
        assert not collisions, (
            "🔴 OCR 第二写入方命中受管键 ⇒ FC-8 的风险在 G 实现了，"
            "该 entry 的受管必须先处置 OCR 路径：\n" + "\n".join(collisions)
        )

    def test_fc8_probe_is_not_vacuous(self) -> None:
        """反向自检：`d4/contract-ocr` 探针在**已知有 OCR 的非 G 循环**必须命中。

        对照取 J1（`useJ1VoucherOcr.ts`）与 B1（`useB1RiskAssessment.ts`）——
        两处都是按值确认过的真实 OCR 写入方。
        """
        for rel in (
            "composables/workpaper/j1/useJ1VoucherOcr.ts",
            "components/workpaper/composables/useB1RiskAssessment.ts",
        ):
            p = FRONTEND / rel
            assert p.exists(), f"对照文件不存在，反向自检无基础: {rel}"
            assert self._OCR_ENDPOINT in p.read_text(encoding="utf-8"), (
                f"探针在已知 OCR 写入方 {rel} 零命中 ⇒ 探针失效，G 的结论不可信"
            )

    # ── FC-11 不命中：47 个 G 块全 cells、零 items ──────────────────────
    def test_fc11_all_g_prefill_blocks_use_cells_not_items(self) -> None:
        """FC-11（prefill `items` 型运行时死配置）在 G **不命中**。

        正向证据：G 循环（除 G0 / G7）prefill 块全部用 `cells`，`items` 键一个都没有。
        🔴 `G7` 必须显式排除 —— `r"G(?:[1-9]|1[0-4])"` 里 `[1-9]` 含 7，
        漏排会把 G7 的 4 块算进来（47 → 51），基线对不上。
        """
        raw = json.loads(PREFILL_PATH.read_text(encoding="utf-8"))
        indexed = [
            (i, b)
            for i, b in enumerate(raw["mappings"])
            if re.fullmatch(r"G(?:[1-9]|1[0-4])", b.get("wp_code", ""))
            and b.get("wp_code") != "G7"
        ]
        assert len(indexed) == 47, (
            f"G 块数变了（现 {len(indexed)}，基线 47）⇒ 分母变动须复核后再改基线"
        )
        with_items = [
            f"[{i}] {b['wp_code']}/{b.get('sheet')}" for i, b in indexed if b.get("items")
        ]
        without_cells = [
            f"[{i}] {b['wp_code']}/{b.get('sheet')}" for i, b in indexed if not b.get("cells")
        ]
        assert not with_items, f"出现 items 型块 ⇒ FC-11 在 G 变为命中: {with_items}"
        assert not without_cells, f"以下 G 块没有 cells: {without_cells}"


# ═══════════════════════════════════════════════════════════════════════════
# GF-P2：两条「缺陷不存在」现算成立
# ═══════════════════════════════════════════════════════════════════════════


class TestGfP2DefectsAbsentInGCycle:
    """Validates: 1.4

    两条候选缺陷（D4/F2 同型）在 G 裁定 `not_present_in_g_cycle`。
    🔴 判据必须**现算**而非读 slice 快照，且变异「往 G 目录塞未索引册子」必红。
    """

    def test_every_g_wp_code_resolves_to_its_own_workbook(self) -> None:
        """候选①「整册码回落打开错工作簿」在 G 不存在。

        13 整册码 + 8 子码 × **三个解析入口**（`find_template_file` /
        `find_template_file_any` / `find_all_template_files`）逐一现算 ——
        spec 要求三个入口都核，因为 D4/F2 的同型缺陷是「某一个入口走了关键词竞争路径」。
        """
        from app.services.wp_template_finder import (  # type: ignore
            find_all_template_files,
            find_template_file,
            find_template_file_any,
        )

        whole = [f"G{n}" for n in (1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14)]
        subs = ["G1-2", "G2-2", "G4-2", "G4-7", "G5-2", "G6-2", "G11-2", "G14-2"]
        bad: list[str] = []
        for code in whole + subs:
            head = code.split("-")[0]
            for label, fn in (
                ("find_template_file", find_template_file),
                ("find_template_file_any", find_template_file_any),
            ):
                got = fn(code)
                if got is None:
                    bad.append(f"{code} via {label}: 解析不到模板")
                    continue
                stem = Path(str(got)).name
                # 册名形如 "G4 债权投资.xlsx" ⇒ 首段必须逐字等于整册码
                if not re.match(rf"^{re.escape(head)}\s", stem):
                    bad.append(f"{code} via {label}: 解析到 {stem!r}（首段不是 {head}）")
            for got in find_all_template_files(code):
                stem = Path(str(got)).name
                if not re.match(rf"^{re.escape(head)}\s", stem):
                    bad.append(
                        f"{code} via find_all_template_files: 含 {stem!r}（首段不是 {head}）"
                    )
        assert not bad, "整册码/子码解析回落到错工作簿:\n" + "\n".join(bad)

    def test_disk_files_equal_runtime_index_entries(self) -> None:
        """候选②「磁盘有、索引无的不可达冗余合册」在 G 不存在 —— 差集必须为空。

        变异「往 G 目录塞一本未索引的册子」⇒ 差集非空 ⇒ 本判据打红。
        """
        index_path = _BACKEND / "wp_templates" / "_index.json"
        idx = json.loads(index_path.read_text(encoding="utf-8"))
        indexed = {
            Path(str(v)).name
            for v in _iter_index_paths(idx)
            if "/G/" in str(v).replace("\\", "/") or str(v).replace("\\", "/").startswith("G/")
        }
        on_disk = {p.name for p in TPL_G.glob("*.xlsx") if not p.name.startswith("~$")}
        assert on_disk, "G 目录一个 xlsx 都没扫到 —— 路径写错，判据会假绿"
        only_disk = sorted(on_disk - indexed)
        only_index = sorted(indexed - on_disk)
        assert not only_disk, (
            "🔴 磁盘有而索引无（不可达冗余合册，D4/F2 同型缺陷在 G 出现了）: "
            f"{only_disk}"
        )
        assert not only_index, f"索引有而磁盘无（断链）: {only_index}"

    def test_mutation_unindexed_workbook_would_be_caught(self) -> None:
        """自省变异：合成一个「磁盘有、索引无」的名字，证明上一条判据真能抓到。"""
        index_path = _BACKEND / "wp_templates" / "_index.json"
        idx = json.loads(index_path.read_text(encoding="utf-8"))
        indexed = {Path(str(v)).name for v in _iter_index_paths(idx)}
        on_disk = {p.name for p in TPL_G.glob("*.xlsx")} | {"G99 合成冗余合册.xlsx"}
        assert sorted(on_disk - indexed) == ["G99 合成冗余合册.xlsx"], (
            "差集算法抓不到合成的未索引册子 ⇒ 上一条判据空转"
        )


def _iter_index_paths(node: object):
    """递归取 `_index.json` 里所有形如 `X/xxx.xlsx` 的路径值（结构未知时也不漏）。"""
    if isinstance(node, str):
        if node.lower().endswith(".xlsx"):
            yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _iter_index_paths(v)
    elif isinstance(node, (list, tuple)):
        for v in node:
            yield from _iter_index_paths(v)


# ═══════════════════════════════════════════════════════════════════════════
# GF-P3：逐 entry 阻塞取 slice 字段且覆盖 17 条全集
# ═══════════════════════════════════════════════════════════════════════════

#: 🔴 逐 entry `capability_target_blocked_by` 现算基线（2026-09-27 实测，
#: 见 `evidence/task1-slice-review-and-adjudication.md` §四）。
#: **不是**从 BP 正文推演出来的，是逐元素抄 slice。
BLOCKED_BY_BASELINE: dict[str, tuple[str, ...]] = {
    "xlsx/gt-g1-trading-financial-assets": ("BP-1", "BP-2", "BP-3", "BP-4", "BP-5", "BP-7"),
    "xlsx/gt-g2-interest-receivable": ("BP-1", "BP-2", "BP-3", "BP-4", "BP-7"),
    "xlsx/gt-g3-dividend-receivable": ("BP-1", "BP-2", "BP-3", "BP-4", "BP-7"),
    "xlsx/gt-g4-bond-investment-main": ("BP-1", "BP-2", "BP-3", "BP-4", "BP-7", "BP-8"),
    "xlsx/gt-g4-bond-investment-sppi": ("BP-1", "BP-2", "BP-3", "BP-4", "BP-8"),
    "xlsx/gt-g4-bond-investment-ecl": ("BP-1", "BP-2", "BP-3", "BP-4", "BP-6", "BP-8"),
    "xlsx/gt-g5-long-term-receivable": ("BP-1", "BP-2", "BP-3", "BP-4", "BP-6"),
    "xlsx/gt-g6-other-bond-main": ("BP-1", "BP-2", "BP-3", "BP-4", "BP-6", "BP-8"),
    "xlsx/gt-g6-other-bond-sppi": ("BP-1", "BP-2", "BP-3", "BP-4", "BP-6", "BP-7", "BP-8"),
    "xlsx/gt-g6-other-bond-investment-ecl": ("BP-1", "BP-2", "BP-3", "BP-4", "BP-6", "BP-8"),
    "xlsx/gt-g8-other-equity-instruments": ("BP-1", "BP-2", "BP-3", "BP-4"),
    "xlsx/gt-g9-other-noncurrent-financial": ("BP-1", "BP-2", "BP-3", "BP-4"),
    "xlsx/gt-g10-trading-financial-liabilities": ("BP-1", "BP-2", "BP-3", "BP-4", "BP-7"),
    "xlsx/gt-g11-investment-income": ("BP-1", "BP-2", "BP-3", "BP-4", "BP-7"),
    "xlsx/gt-g12-net-hedge-gains": ("BP-1", "BP-2", "BP-3", "BP-4", "BP-7"),
    "xlsx/gt-g13-fair-value-changes": ("BP-1", "BP-2", "BP-3", "BP-4", "BP-7"),
    "xlsx/gt-g14-credit-impairment-loss": ("BP-1", "BP-2", "BP-3", "BP-4"),
}


class TestGfP3PerEntryBlockedBy:
    """Validates: 1.3"""

    def test_baseline_covers_all_17_entries(self) -> None:
        assert set(BLOCKED_BY_BASELINE) == EXPECTED_ENTRY_IDS

    @pytest.mark.parametrize("entry_id", sorted(BLOCKED_BY_BASELINE))
    def test_blocked_by_matches_slice_element_wise(
        self, entry_id: str, entries: dict[str, dict]
    ) -> None:
        """逐元素比对，**不得**跨 entry 套用（FC-13）。"""
        got = tuple(entries[entry_id]["capability_target_blocked_by"])
        assert got == BLOCKED_BY_BASELINE[entry_id], (
            f"{entry_id} 的 blocked_by 漂移\nslice={got}\n基线={BLOCKED_BY_BASELINE[entry_id]}"
        )

    def test_bp1_to_bp4_are_universal(self, entries: dict[str, dict]) -> None:
        """BP-1~BP-4 是 17 条共有（平台级供给缺位）。"""
        for eid, e in entries.items():
            bs = set(e["capability_target_blocked_by"])
            assert {"BP-1", "BP-2", "BP-3", "BP-4"} <= bs, f"{eid} 缺平台级前置: {sorted(bs)}"

    def test_bp5_hits_only_g1(self, entries: dict[str, dict]) -> None:
        hits = sorted(e for e, v in entries.items() if "BP-5" in v["capability_target_blocked_by"])
        assert hits == ["xlsx/gt-g1-trading-financial-assets"], hits

    def test_bp8_hits_exactly_g4_and_g6_triples(self, entries: dict[str, dict]) -> None:
        hits = sorted(e for e, v in entries.items() if "BP-8" in v["capability_target_blocked_by"])
        assert hits == sorted(
            [
                "xlsx/gt-g4-bond-investment-main",
                "xlsx/gt-g4-bond-investment-sppi",
                "xlsx/gt-g4-bond-investment-ecl",
                "xlsx/gt-g6-other-bond-main",
                "xlsx/gt-g6-other-bond-sppi",
                "xlsx/gt-g6-other-bond-investment-ecl",
            ]
        ), hits

    def test_mutation_applying_bp5_to_g2_is_caught(self, entries: dict[str, dict]) -> None:
        """变异：把 BP-5（G1 专属）套到 G2 ⇒ 必红。"""
        g2 = set(entries["xlsx/gt-g2-interest-receivable"]["capability_target_blocked_by"])
        assert "BP-5" not in g2, (
            "BP-5 是 G1 的 sheet 标签表缺陷，套到 G2 上等于跨 entry 复制阻塞项（FC-13 禁止）"
        )

    # ── 🔴 slice 内部不一致：BP-7 的两条并存判据 ───────────────────────
    def test_bp7_blocked_by_covers_nine_entries(self, entries: dict[str, dict]) -> None:
        """①锁冻结事实：`blocked_by` 里 BP-7 实测覆盖 9 条（不是 spec 写的 1 条）。"""
        hits = sorted(e for e, v in entries.items() if "BP-7" in v["capability_target_blocked_by"])
        assert len(hits) == 9, f"BP-7 的 blocked_by 覆盖面变了（现 {len(hits)}，实测基线 9）: {hits}"

    def test_bp7_actual_defect_surface_is_only_g6_sppi(
        self, slice_doc: dict, entries: dict[str, dict]
    ) -> None:
        """②锁正文事实：真正有「行身份退化成数组下标」的**只有** G6-sppi。

        判据从 `dynamic_row_identity.tables[].row_identity.kind` 现算，
        不从 BP-7 正文抄 —— 正文是散文，kind 是结构化事实。
        """
        forbidden_kind = "generated_opaque_string_with_array_index_fallback"
        tables = slice_doc["dynamic_row_identity"]["tables"]
        degraded = sorted(
            {t["entry_id"] for t in tables if t["row_identity"]["kind"] == forbidden_kind}
        )
        assert degraded == ["xlsx/gt-g6-other-bond-sppi"], (
            f"实际下标回退面 != {{G6-sppi}}：{degraded}\n"
            "若多出 entry ⇒ g4-g6 spec 的 BP-7 修复范围须扩；"
            "若变空 ⇒ BP-7 已修，本判据须改写"
        )
        # 双向锁：BP-7 的 blocked_by 面 ⊋ 实际缺陷面，这个差**就是**已登记的不一致
        bp7_marked = {e for e, v in entries.items() if "BP-7" in v["capability_target_blocked_by"]}
        assert set(degraded) < bp7_marked, (
            "BP-7 标记面不再严格包含实际缺陷面 ⇒ slice 的内部不一致已变形，"
            "evidence/task1-slice-review-and-adjudication.md §三① 须重写"
        )

    def test_bp9_is_not_in_any_blocked_by(self, entries: dict[str, dict]) -> None:
        """🔴 BP-9 不在任何 entry 的 `blocked_by` 里（spec GF-P3 原写「仅 G1」，实测不成立）。

        性质上也合理：BP-9 的 `must_fix_before` 是 Task 72 Stage B 删除，
        不是「标 bidirectional 之前」⇒ 它本就不该是受管前置。
        """
        hits = sorted(e for e, v in entries.items() if "BP-9" in v["capability_target_blocked_by"])
        assert hits == [], (
            f"BP-9 出现在 blocked_by 里: {hits}\n"
            "若确实加了，说明「跨循环共用件」被提升为受管前置，"
            "本 spec 需求 2.4 的「登记不动」裁决须改"
        )

    def test_bp6_marked_on_five_but_text_covers_all_17(
        self, entries: dict[str, dict], slice_doc: dict
    ) -> None:
        """🔴 BP-6：正文覆盖 17 条、`blocked_by` 只标 5 条 —— 两面都锁住。"""
        marked = sorted(e for e, v in entries.items() if "BP-6" in v["capability_target_blocked_by"])
        assert marked == sorted(
            [
                "xlsx/gt-g4-bond-investment-ecl",
                "xlsx/gt-g5-long-term-receivable",
                "xlsx/gt-g6-other-bond-main",
                "xlsx/gt-g6-other-bond-sppi",
                "xlsx/gt-g6-other-bond-investment-ecl",
            ]
        ), f"BP-6 标记面变了: {marked}"
        # 正文侧：17 条在 source manifest 里 capability 全是组件级默认值
        bp6 = next(b for b in slice_doc["blocking_preconditions"] if b.get("id") == "BP-6")
        assert "17" in json.dumps(bp6, ensure_ascii=False), (
            "BP-6 正文不再声明 17 条 ⇒ 本 spec 登记的「正文与标记面不一致」须重核"
        )
