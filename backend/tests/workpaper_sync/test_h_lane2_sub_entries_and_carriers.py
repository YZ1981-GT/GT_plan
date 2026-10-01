# -*- coding: utf-8 -*-
r"""lane2（H4/H8）子入口改线 + 载体处置 + 族 C 身份的收口判据。

spec: `h4-h8-sub-entry-lanes-and-seed-identity-defects`

═══ 与既有守卫的分工 ═══════════════════════════════════════════════════════════

`test_h_lane2_seed_and_disclosure_defects.py`（12 例）已覆盖 **BP-5 / BP-6 / BP-7**
三条专属缺陷。本文件补它**零覆盖**的那几块（现算该文件里
`useH4DualMode` / `useH8DualMode` / `parent_duplicate` / `h8-tab-recoverable` /
`tb_publish_gate` 关键字命中均为 **0**）：
链式复用图、5 条子入口、载体处置、族 C 两处、以及 H8 的 TB 发布门缺口登记。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.workpaper_sync import h_cycle_facts as F

FE = F.FRONTEND_SRC
COMP = F.COMPOSABLES
UNIQ_RE = re.compile(r"Math\.random|Date\.now|randomUUID")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _production_files() -> list[Path]:
    res = []
    for p in list(FE.rglob("*.ts")) + list(FE.rglob("*.vue")):
        rel = p.relative_to(FE).as_posix()
        if "__tests__" in rel or rel.endswith(".spec.ts"):
            continue
        res.append(p)
    return res


def _import_edges(module_stem: str) -> list[str]:
    """现算某 composable 的**生产** import 边（文件:行）。"""
    pat = re.compile(rf"from ['\"][^'\"]*{re.escape(module_stem)}['\"]")
    out: list[str] = []
    for p in _production_files():
        text = _read(p)
        for m in pat.finditer(text):
            out.append(f"{p.relative_to(FE).as_posix()}:{text[: m.start()].count(chr(10)) + 1}")
    return sorted(out)


# ════════════════════════════════════════════════════════════════════════════
# HS-P1　链式复用图：接桥后宿主不再 import legacy dual-mode，只剩子 Tab
# ════════════════════════════════════════════════════════════════════════════


class TestChainedDualModeReuse:
    """🔴 spec 原文写的是**迁移前**的期望（H4 5 / H8 2）。

    接桥后宿主换成 `useHSyncMode`，声明消费方按三态模型「减掉宿主那一条」——
    所以现算值比原文**小**不代表漏接。本类断言的是**迁移后**应有的形态：
    ①legacy dual-mode 只被子 Tab 引用；②宿主一条都不引；③子 Tab 一条都不许少。
    """

    def test_h4_dual_mode_is_only_consumed_by_its_two_sub_tabs(self) -> None:
        edges = _import_edges("useH4DualMode")
        files = sorted({e.rsplit(":", 1)[0] for e in edges})
        assert files == [
            "components/workpaper/h4/impairment/H4TabImpairment.vue",
            "components/workpaper/h4/impairment/H4TabRecoverable.vue",
        ], f"useH4DualMode 的消费方变了：{files}"

    def test_h8_dual_mode_is_only_consumed_by_the_recoverable_sub_tab(self) -> None:
        """🔴 这条是本 spec 点名「最易漏的一条」：H8 宿主**内联自己的实现**，
        只有 `h8/impairment/H8TabRecoverable.vue` 用 `useH8DualMode`。

        按「删 composable + 改宿主」的常规套路走会完全漏掉它 —— 故单独立一条判据。
        """
        edges = _import_edges("useH8DualMode")
        files = sorted({e.rsplit(":", 1)[0] for e in edges})
        assert files == [
            "components/workpaper/h8/impairment/H8TabRecoverable.vue"
        ], f"useH8DualMode 的消费方变了：{files}"

    def test_hosts_no_longer_import_the_legacy_dual_modes(self) -> None:
        """②宿主侧必须零引用 —— 否则两套切换实现并存（D4-35 踩过「切错桥 + 工具条叠加」）。"""
        for stem, host in (
            ("useH4DualMode", "GtH4EngineeringMaterials.vue"),
            ("useH8DualMode", "GtH8RightOfUseAssets.vue"),
        ):
            files = {e.rsplit(":", 1)[0] for e in _import_edges(stem)}
            assert not any(f.endswith(host) for f in files), f"{host} 仍 import {stem}"

    def test_h6_and_h9_dual_modes_are_now_zero_consumer(self) -> None:
        """🔴 spec Task 6 原文「`useH9DualMode` 实测消费 1，**不得删**」**已过期**。

        现算 `useH6DualMode` / `useH9DualMode` 的生产 import 边都是 **0** ——
        两个宿主都已换 `useHSyncMode`。本判据只**登记事实**，不在本 spec 删文件：
        删除归属分别是 lane3 与 foundation（且删旧代码铁律要求独立 commit）。
        """
        for stem in ("useH6DualMode", "useH9DualMode"):
            assert _import_edges(stem) == [], f"{stem} 又有消费方了：{_import_edges(stem)}"


# ════════════════════════════════════════════════════════════════════════════
# HS-P3　5 条 parent_duplicate 子入口
# ════════════════════════════════════════════════════════════════════════════

#: manifest 里 5 条子入口的 entry_id 全名 → 对应 Tab 文件（相对 FRONTEND_SRC）。
SUB_ENTRIES: dict[str, str] = {
    "xlsx/h4/impairment/h4-tab-impairment": "components/workpaper/h4/impairment/H4TabImpairment.vue",
    "xlsx/h4/impairment/h4-tab-recoverable": "components/workpaper/h4/impairment/H4TabRecoverable.vue",
    "xlsx/h8/impairment/h8-tab-recoverable": "components/workpaper/h8/impairment/H8TabRecoverable.vue",
    "xlsx/h8/measurement/h8-tab-measurement-annual": "components/workpaper/h8/measurement/H8TabMeasurementAnnual.vue",
    "xlsx/h8/measurement/h8-tab-measurement-monthly": "components/workpaper/h8/measurement/H8TabMeasurementMonthly.vue",
}


#: manifest 路径现读（`h_cycle_facts` 里没有 `FULL_MANIFEST_PATH` —— 那是
#: `test_task50_h_cycle_migration` 的常量；按名字推会直接 AttributeError）。
MANIFEST_PATH = F.BACKEND / "data/workpaper_sync_entry_manifest.json"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_five_sub_entries_exist_with_full_entry_ids(manifest: dict) -> None:
    """HS-P3：子入口的 pointer 必须用 **entry_id 全名**（GC-1）。

    🔴 反向理由写进判据：5 条共用父级 `wp_code_pattern`（`H4T` / `H8T`），
    用 wp_code 当 pointer **必撞** —— 所以这里断言 entry_id 这一维是齐的、且互不相同。
    """
    entries = manifest["entries"] if isinstance(manifest, dict) else manifest
    by_id = {str(e.get("entry_id")): e for e in entries}
    missing = [eid for eid in SUB_ENTRIES if eid not in by_id]
    assert missing == [], f"manifest 缺子入口：{missing}"
    assert len(set(SUB_ENTRIES)) == 5


@pytest.mark.parametrize("eid", sorted(SUB_ENTRIES))
def test_sub_entry_is_parent_duplicate_and_gate_is_still_closed(manifest: dict, eid: str) -> None:
    entries = manifest["entries"] if isinstance(manifest, dict) else manifest
    e = next(x for x in entries if str(x.get("entry_id")) == eid)
    assert e.get("migration_state") == "parent_duplicate", (eid, e.get("migration_state"))
    assert e.get("capability") == "single_onlyoffice", (eid, e.get("capability"))
    assert e.get("adapter_id") is None, (eid, e.get("adapter_id"))


@pytest.mark.parametrize("eid", sorted(SUB_ENTRIES))
def test_sub_entry_tab_file_really_exists(eid: str) -> None:
    """声明了子入口却没有对应 Tab 文件 = 清册与磁盘脱钩。"""
    p = FE / SUB_ENTRIES[eid]
    assert p.exists(), f"{eid} 的 Tab 文件不存在：{SUB_ENTRIES[eid]}"


# ════════════════════════════════════════════════════════════════════════════
# HS-P15 / HS-P16　载体处置 + H8 的 TB 发布门缺口
# ════════════════════════════════════════════════════════════════════════════


class TestLane2Carriers:
    def test_h8_formdata_stays_deleted(self) -> None:
        assert not (COMP / "useH8FormData.ts").exists(), "useH8FormData.ts 又回来了（生产消费 0）"

    def test_do_not_delete_list_is_respected(self) -> None:
        """🔴 `useH8DualMode`（子 Tab 唯一切换实现）与 `useH4DualMode`（两个子 Tab）禁删。"""
        for name in ("useH8DualMode.ts", "useH4DualMode.ts"):
            assert (COMP / name).exists(), f"{name} 被删了 —— 子入口切换随之失效"

    def test_h8_host_is_host_inline_write_path(self) -> None:
        """HS-P16：H8 走 `host_inline`（宿主自己 import http 并 PUT）。"""
        host = next(FE.rglob("GtH8RightOfUseAssets.vue"))
        text = _read(host)
        assert re.search(r"import http from ['\"]@/utils/http['\"]", text), "宿主未内联 http"
        assert text.count("http.put") >= 1, "宿主没有 PUT 写路径"
        assert "force_component_type" in text, "宿主未走 render-config?force_component_type"

    def test_h8_has_no_tb_publish_gate_and_that_gap_is_registered(self) -> None:
        """HS-P15：H8 **无** TB 发布门 —— 这是如实登记的缺口，不是本 spec 补。

        🔴 判据写成「H8 作业面内 `publish-to-tb` 命中 0」而不是「某个文件里没有」：
        后者只要换个文件写就绕过去了。补门归 `h2-h6-h10-pilot-cross-reference-lanes`。
        """
        hits: list[str] = []
        for p in _production_files():
            rel = p.relative_to(FE).as_posix()
            if not re.search(r"[Hh]8", rel):
                continue
            if "audit-determination/publish-to-tb" in _read(p):
                hits.append(rel)
        assert hits == [], f"H8 侧出现了 TB 发布门 {hits} —— 缺口登记已过期，需同步改 spec"


# ════════════════════════════════════════════════════════════════════════════
# HS-P17　族 C 两处 + 族 A 样板不得被动
# ════════════════════════════════════════════════════════════════════════════

LANE2_FAMILY_C_SITES: tuple[tuple[str, str], ...] = (
    ("useH4Adjudication.ts", r"`net-\$\{name\}[^`]*`"),
    ("useH8Adjudication.ts", r"`h81-net-\$\{cat\}[^`]*`"),
)


@pytest.mark.parametrize(("fname", "pattern"), LANE2_FAMILY_C_SITES)
def test_lane2_family_c_sites_carry_a_uniqueness_suffix(fname: str, pattern: str) -> None:
    text = _read(COMP / fname)
    hits = re.findall(pattern, text)
    assert hits, f"{fname}: 找不到该族 C 身份模板（{pattern}）"
    for frag in hits:
        assert UNIQ_RE.search(frag), f"{fname}: {frag!r} 无唯一化后缀"


def test_h8_family_a_reference_site_is_untouched() -> None:
    """🔴 `useH8Adjudication.ts` 的族 A 样板是**全 H 的参照形态**（真库 3656 B 实证安全），
    spec 明文「不得改」。这里断言它还在、且仍带后缀。
    """
    text = _read(COMP / "useH8Adjudication.ts")
    m = re.search(r"`h81-\$\{block\}-\$\{\w+\}[^`]*`", text)
    assert m, "族 A 样板不见了"
    assert UNIQ_RE.search(m.group(0)), f"族 A 样板失去唯一化后缀：{m.group(0)!r}"


#: 每个文件里**允许**只生成不沿用的站点（= 新建行 builder）。按身份模板前缀登记。
#: 其余任何带生成器的 `rowId:` 站点都必须写成 `X.rowId ?? <生成>`。
GENERATOR_ONLY_BUILDERS: dict[str, tuple[str, ...]] = {
    "useH4Adjudication.ts": ("`h41-${section}-${Date.now()", "`net-${name}-${Math.random()"),
    "useH8Adjudication.ts": ("`h81-${block}-${category}-", "`h81-net-${cat}-"),
}
_GEN_RE = re.compile(r"Math\.random|Date\.now|randomUUID")
_PRESERVE_RE = re.compile(r"\w+\.rowId\s*\?\?")


@pytest.mark.parametrize("fname", sorted(GENERATOR_ONLY_BUILDERS))
def test_lane2_legacy_identities_survive_via_preserve_on_read(fname: str) -> None:
    """真库 `H8-1-rows` 3656 B 已落库 `h81-cost-房屋及建筑物-ya2jc` 这类族 A 身份 ⇒
    读路径必须沿用，否则历史行全部变新行。

    🔴 按**函数体**取而不是整文件搜：同文件里另有「新建行 builder」直接生成身份，
    整文件搜会被 builder 那一行满足 ⇒ 恒绿（lane1 同类判据实测连踩两次）。

    🔴 **口径换过两版**，lane1 那套「按 `_normalize*` 函数名取函数体」在 H4/H8 上不成立：
    H8 的唯一 `_normalize*` 是 `_normalizeCategory`（把中文科目名归一到枚举，压根不碰
    rowId），而真正的 preserve 站点在 L339、不在任何 `_normalize*` 里 ⇒ 那套口径会
    「一个函数体都取不到」而误红。**按函数名猜职责和按缩进猜边界是同一类错**。

    本版改成**站点级棘轮**，不依赖函数名：扫全文件每个 `rowId:` 右值，
    凡带身份生成器（`Math.random` / `Date.now` / `randomUUID`）的站点二分为
      · preserve 站点（`X.rowId ?? <生成>`）—— 读库路径，必须这样写；
      · 生成器站点（直接生成）—— 只允许是登记在册的**新建行 builder**。
    删掉某个 preserve 站点的 `??` 会把它变成未登记的生成器站点 ⇒ 当场打红并点名行号。
    """
    text = _read(COMP / fname)
    preserve: list[int] = []
    gen_only: list[tuple[int, str]] = []
    for m in re.finditer(r"rowId:\s*([^,\n]+)", text):
        rhs = m.group(1).strip()
        if not _GEN_RE.search(rhs):
            continue  # 稳定串 / 透传，不在本判据范围
        line = text[: m.start()].count("\n") + 1
        if _PRESERVE_RE.search(rhs):
            preserve.append(line)
        else:
            gen_only.append((line, rhs))

    assert preserve, (
        f"{fname}: 没有任何 `X.rowId ?? <生成>` 站点 ⇒ 读库时不沿用已有身份，"
        "真库族 A 历史行（如 `h81-cost-房屋及建筑物-ya2jc`）会全部被当成新行"
    )
    allowed = GENERATOR_ONLY_BUILDERS[fname]
    unregistered = [
        (ln, rhs) for ln, rhs in gen_only if not any(rhs.startswith(a) for a in allowed)
    ]
    assert unregistered == [], (
        f"{fname}: 出现未登记的「只生成不沿用」身份站点 {unregistered} —— "
        "要么它是读库路径（必须补 `X.rowId ??`），要么它是新建行 builder（须登记进 "
        "GENERATOR_ONLY_BUILDERS 并说明理由）"
    )
