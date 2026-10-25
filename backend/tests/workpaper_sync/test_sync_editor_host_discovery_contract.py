"""同步编辑器宿主纳入挂点发现契约 —— 缺口不变量与三层解析链。

spec: sync-editor-host-discovery-contract-closure · Task 0 / 1

## 这个文件锁住什么

**缺陷本体**：entry 只能由前端挂点发现器发现到的挂点派生，而发现器的组件白名单不含
`WorkpaperSyncEditorHost`（真双向载体）⇒ **宿主一旦完成迁移、删掉 legacy 标签，
它在 manifest 里的 entry 就直接不存在**。迁移越彻底，越早从清册消失。

本文件第一条判据（`TestTheGapItself`）在 spec 落地前**应当是红的**，且红的内容要
点名那些「挂了同步载体却没有 entry」的宿主 —— 这是把缺陷写成可执行判据，而不是
写在复盘文档里。Task 15 之后它转绿。

🔴 **分母一律现算，禁写死**：迁移在推进，96 / 51 / 45 这些数每天都在变，写死即假红。
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

_ROOT = Path(__file__).resolve().parents[3]
_WP_REL = "audit-platform/frontend/src/components/workpaper/"
_WP = _ROOT / _WP_REL
_MANIFEST = _ROOT / "backend" / "data" / "workpaper_sync_entry_manifest.json"
_OVERLAY = _ROOT / "backend" / "data" / "workpaper_sync_entry_overlay.json"
_DISCOVERER = (
    _ROOT / "audit-platform" / "frontend" / "scripts" / "discover-workpaper-sync-mounts.mjs"
)

#: 发现器当前认的 legacy 组件 → 其固定 document_type（与 mjs 的 TARGETS 同源，
#: 由 `test_legacy_component_table_matches_the_discoverer` 钉死两边一致）。
_LEGACY_COMPONENTS: dict[str, str] = {
    "GtOnlyOfficeSheet": "xlsx",
    "OnlyOfficeWordDialog": "docx",
    "WorkpaperWordEditor": "docx",
}
_SYNC_HOST = "WorkpaperSyncEditorHost"

#: `GtEntrySyncCapabilityNotice entry-id="…"` 的静态字面量（L2 信号）。
_ENTRY_ID_ATTR = re.compile(
    r"""entry-id\s*=\s*["']((?:xlsx|docx)/[A-Za-z0-9][A-Za-z0-9/_-]*)["']"""
)


def _manifest() -> dict:
    return json.loads(_MANIFEST.read_bytes().decode("utf-8"))


def _overlay() -> dict:
    return json.loads(_OVERLAY.read_bytes().decode("utf-8"))


def _strip_vue_comments(text: str) -> str:
    """剔除 `<!-- -->` 与 `/* */`、`//` 注释。

    🔴 存在的理由：宿主文件头注释里会出现 `entry-id` 这类词与 entry_id 字面量
    （本文件自己的 docstring 就是例子）。不剔注释的扫描会把**说明文字**当成声明。
    """
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", line) for line in text.split("\n"))


def _entry_id_of(document_type: str, host_rel: str) -> str:
    """复用**生成器真实实现**，不自己复刻 kebab。

    🔴 教训来由：本 spec 的调查阶段自己写了个近似 kebab，把
    `GtB22AControlMatrix` 推成 `gt-b22-acontrol-matrix`（真值 `gt-b22-a-control-matrix`），
    于是误判两个宿主「声明不含自身派生值」。接口能 import 就一律 import。
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_gen_for_entry_id",
        _ROOT / "backend" / "scripts" / "gen" / "generate_workpaper_sync_manifest.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._entry_id(document_type, host_rel)


class _Host:
    """一个挂了 `WorkpaperSyncEditorHost` 的宿主及其三层解析信号（全部现算）。"""

    __slots__ = ("rel", "legacy_doc_types", "declarations", "layer", "relation")

    def __init__(self, path: Path) -> None:
        code = _strip_vue_comments(path.read_bytes().decode("utf-8", errors="replace"))
        self.rel = _WP_REL + path.relative_to(_WP).as_posix()
        self.legacy_doc_types = sorted(
            {doc for comp, doc in _LEGACY_COMPONENTS.items() if f"<{comp}" in code}
        )
        self.declarations = sorted(set(_ENTRY_ID_ATTR.findall(code)))
        if self.legacy_doc_types:
            self.layer = "L1"
        elif len(self.declarations) == 1:
            self.layer = "L2"
        else:
            self.layer = "L3"
        self.relation = ""
        if len(self.declarations) == 1:
            own = {_entry_id_of(d, self.rel) for d in ("xlsx", "docx")}
            self.relation = "self" if self.declarations[0] in own else "parent"


def _sync_hosts() -> list[_Host]:
    out: list[_Host] = []
    for path in sorted(_WP.rglob("*.vue")):
        code = _strip_vue_comments(path.read_bytes().decode("utf-8", errors="replace"))
        if f"<{_SYNC_HOST}" in code:
            out.append(_Host(path))
    return out


# ═══ 一、缺口本体（spec 落地前应为红）═══════════════════════════════════════


class TestTheGapItself:
    """挂了真双向载体的宿主，在 manifest 里必须有一条 entry。"""

    def test_every_sync_editor_host_has_a_manifest_entry(self) -> None:
        """🔴 缺陷本体：无 entry 的 EditorHost 宿主数必须为 0。

        独立 entry 或 `parent_duplicate` 都算「有」—— 判据问的是「它在清册里可见吗」，
        不是「它是不是独立底稿」。
        """
        hosts = _sync_hosts()
        assert hosts, (
            "一个挂 WorkpaperSyncEditorHost 的宿主都没扫到 ⇒ 分母为空，判据恒绿，"
            "先查扫描口径（组件名是否改过）"
        )
        host_paths = {str(e.get("host_path") or "") for e in _manifest().get("entries") or []}
        missing = sorted(h.rel for h in hosts if h.rel not in host_paths)
        assert not missing, (
            f"{len(missing)}/{len(hosts)} 个挂了同步编辑器载体的宿主在 manifest 里没有 entry "
            "⇒ 发现契约缺口（spec sync-editor-host-discovery-contract-closure）。"
            "它们完成双向迁移、删掉 legacy 标签之后就从挂点清册消失了。\n  "
            + "\n  ".join(missing[:40])
            + (f"\n  …另 {len(missing) - 40} 个" if len(missing) > 40 else "")
        )

    def test_the_discoverer_recognises_the_sync_editor_host(self) -> None:
        """发现器的组件白名单必须含 `WorkpaperSyncEditorHost`。

        🔴 这条是上一条的**机理**判据：上一条说「结果不对」，这条说「原因在白名单」。
        两条分开，变异报告才能分辨是发现器没认、还是认了但分组/派生出错。
        """
        src = _DISCOVERER.read_bytes().decode("utf-8", errors="replace")
        assert "const TARGETS" in src, "发现器的 TARGETS 表不见了 ⇒ 本判据的锚点失效"
        for comp in _LEGACY_COMPONENTS:
            assert comp in src, f"发现器白名单里连既有的 {comp} 都没有 ⇒ 口径坏了"
        assert _SYNC_HOST in src, (
            f"发现器白名单不含 {_SYNC_HOST} ⇒ 挂了它的宿主不进挂点清册，"
            "其 entry 无从派生（缺陷本体）"
        )

    def test_no_entry_carries_a_null_document_type(self) -> None:
        """document_type 不得为 null —— 它是 entry_id 的组成部分。

        EditorHost 的 document_type 必须由三层链解析出来；留 null 等于让一个
        `None/gt-…` 的 entry_id 流进持久化面。
        """
        bad = [
            str(e.get("entry_id"))
            for e in _manifest().get("entries") or []
            if not str(e.get("document_type") or "")
        ]
        assert not bad, f"以下 entry 的 document_type 为空：{bad[:10]}"


# ═══ 二、三层解析链的闭合性（纯扫描，不依赖生成器）═══════════════════════════


class TestResolutionLayersClose:
    """L1 / L2 / L3 三层必须把 EditorHost 宿主**不重不漏**地分完。"""

    def test_layers_partition_all_hosts_and_none_is_empty(self) -> None:
        """三层之和 == 宿主总数，且每层非空。

        🔴 「每层非空」不是洁癖：某层归零时它的判据会变成恒真式（空分母），
        而那恰恰发生在「口径写错」而不是「该层真没对象」的时候。
        """
        hosts = _sync_hosts()
        assert hosts, "分母为空，先查扫描口径"
        counts = Counter(h.layer for h in hosts)
        assert sum(counts.values()) == len(hosts)
        for layer in ("L1", "L2", "L3"):
            assert counts[layer] > 0, (
                f"{layer} 覆盖为 0 ⇒ 该层判据成了空分母恒真式。"
                f"现算分布 {dict(counts)}；若确实是迁移推进所致，请在 spec 里更新分层设计"
            )

    def test_l1_siblings_agree_on_one_document_type(self) -> None:
        """L1：同文件的 legacy 兄弟挂点必须给出**唯一**的 document_type。"""
        multi = [h.rel for h in _sync_hosts() if len(h.legacy_doc_types) > 1]
        assert not multi, (
            f"以下宿主同时挂 xlsx 与 docx 的 legacy 组件 ⇒ L1 无法给出唯一 document_type，"
            f"须人工裁决：{multi}"
        )

    def test_l2_declaration_is_unambiguous_when_used(self) -> None:
        """L2：走 L2 的宿主必须恰好有一个 `entry-id` 声明；多个即不可判定。"""
        hosts = _sync_hosts()
        l2 = [h for h in hosts if h.layer == "L2"]
        assert l2, "L2 为空 ⇒ 空分母"
        for h in l2:
            assert len(h.declarations) == 1, (h.rel, h.declarations)
            assert h.relation in {"self", "parent"}, (h.rel, h.relation)
        # 分母再分两类，各自非空（否则「self/parent 两分」这条设计无实测对象）
        kinds = Counter(h.relation for h in l2)
        assert kinds["self"] > 0 and kinds["parent"] > 0, (
            f"L2 的 self/parent 两类未同时非空：{dict(kinds)} ⇒ 其中一类的判定逻辑无实测对象"
        )

    def test_l1_and_l2_signals_never_contradict(self) -> None:
        """交叉校验：同时有 L1、L2 信号的宿主，两者 document_type 必须一致。

        这是「规则写错」的独立检测口 —— L1 读兄弟挂点、L2 读宿主声明，两个来源互不依赖。
        """
        both = [h for h in _sync_hosts() if h.legacy_doc_types and len(h.declarations) == 1]
        assert both, "没有同时具备两种信号的宿主 ⇒ 交叉校验无对象，先查扫描口径"
        bad = [
            (h.rel, h.legacy_doc_types, h.declarations[0])
            for h in both
            if h.declarations[0].split("/", 1)[0] not in h.legacy_doc_types
        ]
        assert not bad, f"L1 与 L2 给出的 document_type 冲突：{bad}"

    def test_l3_hosts_are_covered_by_a_reviewed_overlay_rule(self) -> None:
        """L3：无源码信号的宿主必须被 overlay 的 reviewed 规则覆盖，否则 fail closed。

        spec 落地前 overlay 还没有 `sync_host_entry_rules` 键 ⇒ 本条此时应红，
        红的内容点名那些**没有任何身份来源**的宿主。
        """
        import fnmatch

        l3 = [h for h in _sync_hosts() if h.layer == "L3"]
        assert l3, "L3 为空 ⇒ 空分母"
        rules = _overlay().get("sync_host_entry_rules") or []
        uncovered = [
            h.rel
            for h in l3
            if not any(
                isinstance(r.get("file_glob"), str)
                and fnmatch.fnmatchcase(h.rel, r["file_glob"])
                and r.get("component") in (None, _SYNC_HOST)
                for r in rules
            )
        ]
        assert not uncovered, (
            f"{len(uncovered)}/{len(l3)} 个 L3 宿主既无 legacy 兄弟、又无 entry-id 声明、"
            "且 overlay 的 `sync_host_entry_rules` 没有覆盖它们 ⇒ 身份无从解析。\n  "
            + "\n  ".join(uncovered[:35])
        )


# ═══ 三、manifest.stats 自洽（Task 1：另一类「没人守住」的缺陷）══════════════


class TestManifestStatsAreSelfConsistent:
    """`stats` 必须与 `entries` 现算逐值相等。

    🔴 **实证来由**：2026-09-30 发现 HEAD 的 committed manifest 里 `entries` 有 **5** 条
    `bidirectional` 而 `stats.capability_counts` 声明 **4**（`single_onlyoffice` 144 vs 声明 145）。
    生成器在同一个函数里由 entries 算 stats，**不可能产出这种偏差** ⇒ 该 manifest 被手改过
    （`git log` 定位到 `1ec6a1050 feat(sync): D1 adapter 注册 —— manifest bidirectional …`，
    它改了 entries 里 D1 的 capability 却没重跑生成器）。
    **而当时没有任何判据守住这件事** —— 这条就是那个缺口。
    """

    @staticmethod
    def _recount(manifest: dict) -> dict[str, object]:
        entries = manifest.get("entries") or []
        return {
            "entry_count": len(entries),
            "capability_counts": dict(sorted(Counter(e.get("capability") for e in entries).items())),
            "independent_entry_count": sum(1 for e in entries if e.get("independent_entry")),
            "parent_duplicate_count": sum(1 for e in entries if e.get("parent_entry_id") is not None),
        }

    def test_declared_stats_equal_the_recomputed_stats(self) -> None:
        man = _manifest()
        stats = man.get("stats") or {}
        actual = self._recount(man)
        assert actual["entry_count"] > 0, "entries 为空 ⇒ 本判据成了空分母"
        mismatches = {
            key: (stats.get(key), value)
            for key, value in actual.items()
            if stats.get(key) != value
        }
        assert not mismatches, (
            "manifest.stats 与 entries 现算不一致 ⇒ 产物很可能被**手改**过而未重跑生成器"
            "（生成器在同一函数里由 entries 算 stats，不可能产出偏差）。"
            f"\n  字段: (声明值, 现算值) = {mismatches}"
            "\n  处置：跑 `python backend/scripts/gen/generate_workpaper_sync_manifest.py --apply`，"
            "并查 `git log -- backend/data/workpaper_sync_entry_manifest.json` 定位手改来源"
        )

    def test_the_check_detects_a_hand_edited_stats_block(self) -> None:
        """🔴 变异自证：手改一份内存副本的 stats 后，上一条的口径必须判出来。

        没有这条，`test_declared_stats_equal_the_recomputed_stats` 可能只是在
        「两边都读同一个地方」而根本没有区分力。
        """
        import copy

        man = copy.deepcopy(_manifest())
        before = self._recount(man)
        assert man["stats"]["entry_count"] == before["entry_count"], "前提不成立"

        man["stats"]["entry_count"] = int(before["entry_count"]) - 1
        after = self._recount(man)
        assert man["stats"]["entry_count"] != after["entry_count"], (
            "改了 stats.entry_count 之后现算仍与声明相等 ⇒ 口径失效（可能两边读的是同一个值）"
        )

        caps = dict(before["capability_counts"])  # type: ignore[arg-type]
        assert caps, "capability_counts 为空 ⇒ 变异无对象"
        first = sorted(caps)[0]
        man2 = copy.deepcopy(_manifest())
        man2["stats"]["capability_counts"][first] = caps[first] + 1
        assert self._recount(man2)["capability_counts"] != man2["stats"]["capability_counts"], (
            "改了 capability_counts 之后现算仍相等 ⇒ 口径失效"
        )


# ═══ 四、与发现器白名单的双向锁 ═════════════════════════════════════════════


def test_legacy_component_table_matches_the_discoverer() -> None:
    """本文件的 `_LEGACY_COMPONENTS` 必须与发现器的 TARGETS 同步。

    🔴 这张表是本文件多条判据的输入（L1 靠它找兄弟挂点）。发现器加减组件而这里没跟，
    会让 L1 的覆盖面悄悄变化而判据仍然绿 —— 那是最难发现的一类假绿。
    """
    src = _DISCOVERER.read_bytes().decode("utf-8", errors="replace")
    declared = set(re.findall(r"component:\s*'([A-Za-z0-9_]+)'", src))
    assert declared, "从发现器里解析不出 component 声明 ⇒ 口径坏了"
    missing_here = sorted(declared - set(_LEGACY_COMPONENTS) - {_SYNC_HOST})
    assert not missing_here, (
        f"发现器声明了本文件未登记的组件：{missing_here} ⇒ 请同步 `_LEGACY_COMPONENTS`"
        "（并确认它的 document_type 是否固定）"
    )
    stale_here = sorted(set(_LEGACY_COMPONENTS) - declared)
    assert not stale_here, f"本文件登记了发现器已不认的组件：{stale_here}"


# ═══ 五、entry 侧验收：声明式 parent、新字段、零 churn ═══════════════════════


class TestEntryDerivationIsCorrect:
    """缺口闭合之后，新派生出来的 entry 必须**语义正确**，不只是「数量对上了」。"""

    def test_hosts_forwarding_a_parent_identity_become_parent_duplicates(self) -> None:
        """声明值 != 自身路径派生值的宿主 ⇒ parent_duplicate，且父级真实存在。

        现算对象：`d4/**` 下那批 tab（它们经 useD4SyncMode 转发 D4 根 entry 身份）。
        """
        man = _manifest()
        by_host = {str(e.get("host_path") or ""): e for e in man.get("entries") or []}
        ids = {str(e.get("entry_id")) for e in man.get("entries") or []}
        forwarding = [h for h in _sync_hosts() if h.relation == "parent"]
        assert forwarding, "没有转发父级的宿主 ⇒ 空分母（L2 的 parent 分支无实测对象）"
        for host in forwarding:
            entry = by_host.get(host.rel)
            assert entry is not None, f"{host.rel} 没有 entry"
            assert entry.get("parent_entry_id") == host.declarations[0], (
                f"{host.rel}: parent_entry_id={entry.get('parent_entry_id')!r} "
                f"≠ 源码声明 {host.declarations[0]!r}"
            )
            assert entry.get("independent_entry") is False, host.rel
            assert entry.get("adapter_id") is None, host.rel
            assert entry.get("migration_state") == "parent_duplicate", host.rel
            assert host.declarations[0] in ids, (
                f"{host.rel} 转发到一个不存在的父级 {host.declarations[0]}"
            )

    def test_hosts_declaring_their_own_identity_stay_independent(self) -> None:
        """声明值 == 自身派生值的宿主 ⇒ 独立 entry（现算对象：17 个 A 类）。"""
        man = _manifest()
        by_host = {str(e.get("host_path") or ""): e for e in man.get("entries") or []}
        own = [h for h in _sync_hosts() if h.relation == "self" and not h.legacy_doc_types]
        assert own, "没有「仅同步载体且声明自身」的宿主 ⇒ 空分母"
        for host in own:
            entry = by_host.get(host.rel)
            assert entry is not None, f"{host.rel} 没有 entry"
            assert entry.get("entry_id") == host.declarations[0], (
                f"{host.rel}: entry_id={entry.get('entry_id')!r} ≠ 声明 {host.declarations[0]!r}"
            )
            assert entry.get("independent_entry") is True, host.rel
            assert entry.get("parent_entry_id") is None, host.rel

    def test_mount_components_and_flag_agree_with_the_source(self) -> None:
        """`mount_components` / `sync_editor_host_mounted` 必须与源码扫描逐一吻合。"""
        man = _manifest()
        hosts = {h.rel for h in _sync_hosts()}
        flagged = {
            str(e.get("host_path"))
            for e in man.get("entries") or []
            if e.get("sync_editor_host_mounted")
        }
        assert flagged == hosts, (
            "`sync_editor_host_mounted` 与源码扫描不一致：\n"
            f"  只在 manifest 里: {sorted(flagged - hosts)[:8]}\n"
            f"  只在源码里      : {sorted(hosts - flagged)[:8]}"
        )
        for entry in man.get("entries") or []:
            components = entry.get("mount_components")
            assert isinstance(components, list) and components, entry.get("entry_id")
            assert components == sorted(components), f"{entry.get('entry_id')} 未排序"
            actual = sorted({str(m.get("component")) for m in entry.get("mounts") or []})
            assert components == actual, (entry.get("entry_id"), components, actual)
            assert entry.get("sync_editor_host_mounted") is (_SYNC_HOST in components)

    def test_dual_mount_entries_took_no_capability_churn(
        self, live_manifest_pair: tuple[dict, dict]
    ) -> None:
        """🔴 零 churn：同一活源码/同一 overlay 下，加入同步载体前后逐 entry 值不变。

        **旧判据是假绿**：它只断言双挂 entry 的 ``canonical_resolver`` 不等于
        ``sync_bridge_editor_host``，却在 docstring 声称锁住 capability / html_store /
        migration_state。13 条 G override 同时翻转四字段时它照样绿 —— 「不是某个默认值」
        不能证明「与修复前逐字相同」。

        本判据真正构造两个可比状态：

        * before：从当前 discovery **仅过滤** WorkpaperSyncEditorHost 挂点（模拟旧 TARGETS
          不认同步载体），并从 overlay 的内存副本移除只服务该组件的 default / L3 rule /
          a51 override；其余 override（包括 13 条 G）逐字保留。
        * after：同一次 discovery + 同一份 overlay 的正常现算结果。

        因此唯一自变量是「发现器是否纳入同步载体」。对 after 中每条双挂 entry，before
        必须有同 entry_id，且五个业务裁决字段逐值相同。这样既不会把并发 G lane 已复核的
        override 错算成本 spec 的 churn，也能真的打红组件优先级反转或默认值越权。
        """
        before, after = live_manifest_pair
        before_by_id = {str(e["entry_id"]): e for e in before["entries"]}
        after_ids = {str(e["entry_id"]) for e in after["entries"]}
        removed_or_renamed = sorted(set(before_by_id) - after_ids)
        assert not removed_or_renamed, (
            "旧发现器可见的 entry 在纳入同步载体后消失或改了 entry_id："
            f"{removed_or_renamed[:8]}"
        )
        dual = [
            e for e in after["entries"]
            if _SYNC_HOST in (e.get("mount_components") or [])
            and set(e.get("mount_components") or []) - {_SYNC_HOST}
        ]
        assert dual, "没有双挂 entry ⇒ 空分母，零 churn 判据无对象"

        missing = sorted(str(e["entry_id"]) for e in dual if e["entry_id"] not in before_by_id)
        assert not missing, f"双挂 entry 在修复前不存在，无法证明零 churn：{missing[:8]}"

        fields = (
            "capability",
            "html_store",
            "canonical_resolver",
            "migration_state",
            "adapter_id",
        )
        changed: dict[str, dict[str, tuple[object, object]]] = {}
        for current in dual:
            entry_id = str(current["entry_id"])
            previous = before_by_id[entry_id]
            diff = {
                field: (previous.get(field), current.get(field))
                for field in fields
                if previous.get(field) != current.get(field)
            }
            if diff:
                changed[entry_id] = diff
        assert not changed, (
            f"{len(changed)} 条双挂 entry 因发现同步载体而改变业务裁决；"
            f"前 5 条={list(changed.items())[:5]}"
        )

    def test_only_sync_host_entries_use_the_sync_resolver(self) -> None:
        """反向半边：**仅**挂同步载体且**无 override** 的 entry 用同步载体的 resolver。

        与上一条成对 —— 只有上一条时，「所有 entry 都不用同步 resolver」也能通过
        （那说明新默认值根本没生效）。

        🔴 「无 override」这个限定是实测加上的：`xlsx/gt-a51-cashflow-audit` 是仅挂同步
        载体的 entry，但它有一条 reviewed override 把 resolver 显式设成
        `workpaper_sync_published_representation`（因为它已裁决为 bidirectional）。
        首版漏了这个限定 ⇒ 判据把**正确的 override 生效**误判成缺陷。
        override 覆盖默认值是 overlay 的本职，不是异常。
        """
        import fnmatch

        overridden = [
            str(o.get("file_glob"))
            for o in _overlay().get("overrides") or []
            if o.get("canonical_resolver")
        ]
        solo = [
            e for e in _manifest().get("entries") or []
            if (e.get("mount_components") or []) == [_SYNC_HOST]
        ]
        assert solo, "没有「仅同步载体」的 entry ⇒ 新组件默认值无实测对象"
        from_default = [
            e for e in solo
            if not any(fnmatch.fnmatchcase(str(e.get("host_path")), g) for g in overridden)
        ]
        assert from_default, (
            "所有「仅同步载体」entry 都被 override 覆盖了 resolver ⇒ 新组件默认值无实测对象，"
            "本判据退化为恒真式"
        )
        resolvers = {str(e.get("canonical_resolver") or "") for e in from_default}
        assert resolvers == {"sync_bridge_editor_host"}, (
            f"取默认值的「仅同步载体」entry 其 canonical_resolver 现算为 {sorted(resolvers)} "
            "—— 新组件默认值未生效"
        )


def test_the_a51_adjudication_is_redeemable_again() -> None:
    """🔴 本 spec 的终局验收：a51 裁决重新可兑现，不再需要 `deferred_overrides`。

    2026-09-30 该裁决曾因发现契约缺口而不可兑现（宿主已删 legacy 标签 ⇒ entry 不存在
    ⇒ 生成器报 `stale overlay overrides`，manifest **任何人都无法重生成**），被迫移入
    `deferred_overrides`。缺口修好后它必须回到 `overrides` 并真正落到 manifest。
    """
    overlay = _overlay()
    assert not (overlay.get("deferred_overrides") or []), (
        "`deferred_overrides` 非空 ⇒ 仍有裁决因发现契约缺口而不可兑现"
    )
    globs = {str(o.get("file_glob")) for o in overlay.get("overrides") or []}
    a51_host = _WP_REL + "GtA51CashflowAudit.vue"
    assert a51_host in globs, "a51 裁决不在 overrides 里"

    entries = {str(e.get("entry_id")): e for e in _manifest().get("entries") or []}
    entry = entries.get("xlsx/gt-a51-cashflow-audit")
    assert entry is not None, "a51 的 entry 仍不在 manifest 里 ⇒ 缺口未真正闭合"
    assert entry.get("capability") == "bidirectional", entry.get("capability")
    assert entry.get("adapter_id") == "a51.cashflow_audit", entry.get("adapter_id")
    assert entry.get("mount_components") == [_SYNC_HOST], entry.get("mount_components")


# ═══ 六、把不变量接到**活事实**上（变异实测暴露的判据缺口）═════════════════
#
# 🔴 来由：Task 15 的变异检验里，M01（把同步载体从发现器白名单摘掉）与 M05（改新组件的
# 默认 canonical_resolver）两条**该红却绿**。根因同一个：上面那些判据读的是**磁盘
# manifest**，而改发现器 / overlay 在产物重生成之前**不改变磁盘产物** ⇒ 判据还在看旧事实。
#
# 只把变异目标改成「生成器 --check 会报 stale」能让变异变红，但那只证明「产物过期会被发现」，
# **不证明**不变量本身还成立。所以这里再加一层：现跑发现器 + 在内存里重算 manifest，
# 把缺口不变量接到活事实上 —— 这样发现器或 overlay 一变，判据立刻看得见。


@pytest.fixture(scope="module")
def live_manifest_pair() -> tuple[dict, dict]:
    """同一次活 discovery 现算 ``(旧发现器语义, 当前语义)``，全程只改内存副本。

    ``before`` 只过滤同步载体，并删掉 overlay 里仅服务该组件、在旧发现器下必然 stale 的
    default / L3 rule / a51 override；G 等其它 lane 的 override 原样保留。故两态唯一自变量
    是「发现器是否认 WorkpaperSyncEditorHost」，可用于真正的零 churn 差分。
    """
    import copy
    import importlib.util
    import subprocess

    discoverer = _DISCOVERER
    if not discoverer.is_file():
        pytest.skip("挂点发现器不存在")
    try:
        proc = subprocess.run(
            ["node", str(discoverer), "--json"],
            cwd=str(_ROOT / "audit-platform" / "frontend"),
            capture_output=True, shell=False, timeout=900,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"挂点发现器跑不起来：{type(exc).__name__}")
    if proc.returncode != 0 or not (proc.stdout or b"").strip():
        pytest.skip(f"挂点发现器 rc={proc.returncode}，无 JSON 输出")
    discovery = json.loads(proc.stdout.decode("utf-8"))

    spec = importlib.util.spec_from_file_location(
        "_gen_for_recompute",
        _ROOT / "backend" / "scripts" / "gen" / "generate_workpaper_sync_manifest.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    overlay = _overlay()
    # 复核门在重算场景下不适用（我们要的是「按当前源码会算出什么」）。
    overlay = {**overlay, "approved_source_digest": discovery["sourceDigest"]}
    after = module.build_manifest(copy.deepcopy(discovery), copy.deepcopy(overlay))

    before_discovery = copy.deepcopy(discovery)
    before_discovery["mounts"] = [
        fact for fact in before_discovery["mounts"]
        if fact.get("component") != _SYNC_HOST
    ]
    before_discovery["stats"]["byComponent"].pop(_SYNC_HOST, None)
    # 这是内存反事实，不冒充当前全量 discovery 的真实 digest。复核门只要求两侧身份一致；
    # 用显式 sentinel 比沿用 after 的 digest 更诚实，也防止后续有人误拿 before.manifest 的
    # source_digest 当可提交产物。
    before_discovery["sourceDigest"] = "in-memory-pre-fix-editor-host-filtered"

    before_overlay = copy.deepcopy(overlay)
    before_overlay["approved_source_digest"] = before_discovery["sourceDigest"]
    before_overlay["sync_host_entry_rules"] = []
    before_overlay["defaults_by_component"].pop(_SYNC_HOST, None)
    before_overlay["overrides"] = [
        rule for rule in before_overlay.get("overrides") or []
        if rule.get("component") != _SYNC_HOST
    ]
    before = module.build_manifest(before_discovery, before_overlay)
    return before, after


@pytest.fixture(scope="module")
def recomputed_manifest(live_manifest_pair: tuple[dict, dict]) -> dict:
    """当前活源码现算的 manifest（不读、不写磁盘产物）。"""
    return live_manifest_pair[1]


class TestTheInvariantHoldsOnLiveFacts:
    """不变量在**现算**的 manifest 上同样成立 —— 不依赖磁盘产物是否新鲜。"""

    def test_every_sync_editor_host_has_an_entry_in_the_recomputed_manifest(
        self, recomputed_manifest: dict
    ) -> None:
        hosts = {h.rel for h in _sync_hosts()}
        assert hosts, "分母为空，先查扫描口径"
        host_paths = {str(e.get("host_path") or "") for e in recomputed_manifest["entries"]}
        missing = sorted(hosts - host_paths)
        assert not missing, (
            f"{len(missing)}/{len(hosts)} 个挂了同步载体的宿主在**现算** manifest 里没有 entry "
            "⇒ 发现契约缺口（而不是产物过期）。\n  " + "\n  ".join(missing[:30])
        )

    def test_the_recomputed_manifest_matches_the_artifact_on_disk(
        self, recomputed_manifest: dict
    ) -> None:
        """现算结果必须与磁盘产物一致 —— 否则产物过期，上面所有读磁盘的判据都在看旧事实。

        🔴 这条是「读磁盘」那批判据的**前提**。没有它，磁盘判据全部可能基于过期产物而假绿。
        """
        disk = _manifest()
        for key in ("entry_count", "capability_counts"):
            assert recomputed_manifest["stats"][key] == disk["stats"][key], (
                f"现算 stats.{key} 与磁盘不一致 ⇒ 产物过期，请跑 "
                "`generate_workpaper_sync_manifest.py --apply`\n"
                f"  现算={recomputed_manifest['stats'][key]}\n  磁盘={disk['stats'][key]}"
            )
        assert recomputed_manifest["manifest_digest"] == disk["manifest_digest"], (
            "现算 manifest_digest 与磁盘不一致 ⇒ 产物过期"
        )

    def test_only_sync_host_entries_use_the_sync_resolver_on_live_facts(
        self, recomputed_manifest: dict
    ) -> None:
        """组件默认值的生效性接到活事实上（M05 变异据此可见）。

        与磁盘版同口径：排除被 reviewed override 显式指定 resolver 的 entry
        （override 覆盖默认值是 overlay 的本职，不是缺陷）。
        """
        import fnmatch

        overridden = [
            str(o.get("file_glob"))
            for o in _overlay().get("overrides") or []
            if o.get("canonical_resolver")
        ]
        solo = [
            e for e in recomputed_manifest["entries"]
            if (e.get("mount_components") or []) == [_SYNC_HOST]
            and not any(fnmatch.fnmatchcase(str(e.get("host_path")), g) for g in overridden)
        ]
        assert solo, "没有「仅同步载体且取默认值」的 entry ⇒ 新组件默认值无实测对象"
        resolvers = {str(e.get("canonical_resolver") or "") for e in solo}
        assert resolvers == {"sync_bridge_editor_host"}, (
            f"取默认值的「仅同步载体」entry 其 canonical_resolver 现算为 {sorted(resolvers)} "
            "—— 新组件默认值未生效"
        )
