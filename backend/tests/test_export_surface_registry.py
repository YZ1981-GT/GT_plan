"""
test_export_surface_registry.py

验证 EXPORT_SURFACE_REGISTRY 结构与 validate_registry(app) 闭合性。
design §9, R9, AC-20, AC-23.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.export_surface_registry import (
    EXPORT_SURFACE_REGISTRY,
    ExportSurfaceEntry,
    RegistryValidationError,
    validate_registry,
)


# ── helpers ───────────────────────────────────────────────

def _mock_app(routes: list[dict]) -> SimpleNamespace:
    mock_routes = []
    for r in routes:
        mock_routes.append(SimpleNamespace(path=r["path"], methods=r.get("methods", {"GET"})))
    return SimpleNamespace(routes=mock_routes)


# ── 1. 注册表结构 ────────────────────────────────────────

class TestRegistryStructure:

    def test_non_empty(self) -> None:
        assert len(EXPORT_SURFACE_REGISTRY) > 0

    def test_all_entries_have_required_fields(self) -> None:
        for key, entry in EXPORT_SURFACE_REGISTRY.items():
            assert isinstance(entry, ExportSurfaceEntry), f"{key} 不是 ExportSurfaceEntry"
            assert entry.path, f"{key} 缺少 path"
            assert entry.method in ("GET", "POST", "PUT", "DELETE"), f"{key} 非法 method"
            assert entry.classification in ("formal", "data_exchange", "template", "non_amount")
            assert entry.description

    def test_formal_entries_exist(self) -> None:
        formal = [k for k, v in EXPORT_SURFACE_REGISTRY.items() if v.classification == "formal"]
        assert len(formal) >= 5, "formal 分类条目应至少含试算表、报表、附注、底稿、PDF"

    def test_data_exchange_entries_exist(self) -> None:
        de = [k for k, v in EXPORT_SURFACE_REGISTRY.items() if v.classification == "data_exchange"]
        assert len(de) >= 1

    def test_no_duplicate_paths(self) -> None:
        paths = [v.path for v in EXPORT_SURFACE_REGISTRY.values()]
        assert len(paths) == len(set(paths)), "存在重复的 path"


# ── 2. validate_registry 闭合性 ──────────────────────────

class TestValidateRegistry:

    def test_all_registered_present_passes(self) -> None:
        """app.routes 包含全部注册路径时不抛异常。"""
        # 🔴 只造**非退役**条目的路由：`retired=True` 的条目现算确认无真实路由，
        # 把它们造进 mock 会让 validate_registry 判成「未注册」（口径反转）。
        routes = [
            {"path": e.path}
            for e in EXPORT_SURFACE_REGISTRY.values()
            if not e.retired
        ]
        app = _mock_app(routes)
        validate_registry(app)

    def test_missing_registered_path_raises(self) -> None:
        """已注册路径不在 app.routes 中时抛异常。"""
        app = _mock_app([])
        with pytest.raises(RegistryValidationError) as exc_info:
            validate_registry(app)
        assert exc_info.value.missing

    def test_unregistered_export_path_raises(self) -> None:
        """app.routes 包含未注册的导出路由时抛异常。"""
        routes = [
            {"path": e.path}
            for e in EXPORT_SURFACE_REGISTRY.values()
            if not e.retired
        ]
        routes.append({"path": "/api/projects/{project_id}/export-secret"})
        app = _mock_app(routes)
        with pytest.raises(RegistryValidationError) as exc_info:
            validate_registry(app)
        assert exc_info.value.unregistered

    def test_non_export_extra_route_ignored(self) -> None:
        """非导出相关的额外路由不触发异常。"""
        routes = [
            {"path": e.path}
            for e in EXPORT_SURFACE_REGISTRY.values()
            if not e.retired
        ]
        routes.append({"path": "/api/health"})
        routes.append({"path": "/api/projects/{project_id}/config"})
        routes.append({"path": "/api/users/me/display-preferences"})
        app = _mock_app(routes)
        validate_registry(app)

    def test_classification_coverage(self) -> None:
        """四种分类至少各出现一次。"""
        classes = {v.classification for v in EXPORT_SURFACE_REGISTRY.values()}
        assert "formal" in classes
        assert "data_exchange" in classes
        assert "template" in classes
        assert "non_amount" in classes

    def test_duplicate_normalized_path_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """同一路由被登记两次（即使参数名不同）必须打红。"""
        key, entry = next(iter(EXPORT_SURFACE_REGISTRY.items()))
        duplicate_path = entry.path.replace("{project_id}", "{another_project_id}")
        monkeypatch.setitem(
            EXPORT_SURFACE_REGISTRY,
            f"{key}_duplicate",
            ExportSurfaceEntry(
                path=duplicate_path,
                method=entry.method,
                classification=(
                    "data_exchange"
                    if entry.classification != "data_exchange"
                    else "formal"
                ),
                description="故障注入：重复登记同一归一化路径",
            ),
        )
        app = _mock_app(
            [
                {"path": item.path}
                for item in EXPORT_SURFACE_REGISTRY.values()
                if not item.retired
            ]
        )

        with pytest.raises(RegistryValidationError) as exc_info:
            validate_registry(app)

        assert exc_info.value.duplicate_classification
        assert "keys:" in exc_info.value.duplicate_classification[0]


# ── 闭合性棘轮（spec platform-global-display-settings-closure 任务 10 / AC-20）──
#
# 🔴 背景：`EXPORT_SURFACE_REGISTRY` 里曾挂 12 条**从未存在过**的路径
# （`missing=12`），而其中第一条就是**活的用户缺陷** —— 前端
# `views/TrialBalance.vue` 的「导出」按钮一直在调 `/trial-balance/export`，
# 后端从来没实现 ⇒ 点一次 404。其余 11 条同样「注册表登记 ≠ 路由存在」。
#
# 这组守卫把「登记了就必须真的存在」变成自动可检出的判据：
# 1. 每条**非 retired** 条目必须能在 `app.routes` 里找到（方法也要对）；
# 2. `missing` 必须为 **0**（不允许回升）；
# 3. `retired=True` 的条目**必须真的没有路由** —— 否则「退役」被当成
#    「删不掉就标退役」的后门，真实路由反而脱管。


class TestRegistryClosureRatchet:
    """注册表与实际路由的闭合性棘轮（只许变好）。"""

    def test_every_non_retired_entry_has_real_route(self) -> None:
        """每条非退役条目必须真的挂在 `app.routes` 上，且方法一致。

        只断言「注册表非空」会漏掉整类缺陷：登记齐全但路由从未实现。

        🔴 2026-11-16 口径统一：本条原用 `(entry.path, entry.method)` 逐字符
        比对 `app.routes`，而 `validate_registry` 用 `_normalize_path` 归一化
        比对 ⇒ **两套口径会给出相反答案**（首版按归一化清单登记时，
        `validate_registry` PASS 而本条红 295 条）。

        现在两条判据都走 `_normalize_path`，且该函数**保留转换器**
        （`{id:uuid}` → `{:uuid}`）⇒ 参数名不同仍算同一路由（Starlette 的参数名
        是实现细节），但 `:uuid` 与无转换器**不可混同**（那是真实的路由差异，
        注册表里 `attachment_download` 就带 `:uuid`）。
        """
        from app.main import app
        from app.services.export_surface_registry import _normalize_path

        actual: set[tuple[str, str]] = set()
        for r in app.routes:
            p = getattr(r, "path", None)
            if not p:
                continue
            norm = _normalize_path(p)
            for m in getattr(r, "methods", None) or set():
                actual.add((norm, m))

        missing: list[str] = []
        for key, entry in EXPORT_SURFACE_REGISTRY.items():
            if entry.retired:
                continue
            if (_normalize_path(entry.path), entry.method) not in actual:
                missing.append(f"{key}: {entry.method} {entry.path}")

        assert not missing, f"注册表登记但无真实路由: {missing}"

    def test_normalize_path_preserves_converter(self) -> None:
        """`_normalize_path` 必须保留转换器，只忽略参数名。

        🔴 反向自检：这是「两套口径」收口的核心。原实现
        `re.sub(r"\\{[^}]+\\}", "{}", path)` 把 `{attachment_id:uuid}` 与
        `{attachment_id}` 归一成同一个 `{}` ⇒ 注册表把带 `:uuid` 的路由
        登记成不带转换器时，`validate_registry` 会**静默放行**，
        而真实请求永远 404（Starlette 的 `:uuid` 转换器会拒绝非 UUID 值）。

        判据要求：
        - 参数名不同 ⇒ 归一化结果相同（参数名是实现细节）
        - 转换器不同 ⇒ 归一化结果不同（那是真实的路由差异）
        """
        from app.services.export_surface_registry import _normalize_path

        # 参数名被忽略
        assert _normalize_path("/api/projects/{project_id}/x") == _normalize_path(
            "/api/projects/{pid}/x"
        )
        assert _normalize_path("/api/projects/{project_id}/x") == "/api/projects/{}/x"

        # 转换器被保留
        assert _normalize_path("/api/attachments/{a:uuid}/download") == (
            "/api/attachments/{:uuid}/download"
        )
        assert _normalize_path("/api/attachments/{a:uuid}/download") != (
            _normalize_path("/api/attachments/{a}/download")
        )

        # 混合路径：一个带转换器一个不带
        assert _normalize_path("/api/a/{x:uuid}/b/{y}/c") == "/api/a/{:uuid}/b/{}/c"

        # 非参数路径原样
        assert _normalize_path("/api/a17/export-word") == "/api/a17/export-word"

    def test_converter_mismatch_is_detected(self) -> None:
        """登记时漏写转换器必须被打红（这是 `:uuid` 差异的实战形态）。

        注入一条「真实路由带 `:uuid`，但登记写成不带转换器」的条目，
        闭合判定必须失败 —— 变更前 `validate_registry` 会放行。
        """
        from app.main import app
        from app.services.export_surface_registry import (
            EXPORT_SURFACE_REGISTRY,
            ExportSurfaceEntry,
            RegistryValidationError,
            validate_registry,
        )

        # 先确认基线闭合
        validate_registry(app)

        key = "_probe_converter_mismatch"
        try:
            EXPORT_SURFACE_REGISTRY[key] = ExportSurfaceEntry(
                # 真实路由是 /api/attachments/{attachment_id:uuid}/download
                path="/api/attachments/{attachment_id}/download",
                method="GET",
                classification="non_amount",
                description="probe: 漏写 :uuid 转换器",
            )
            with pytest.raises(RegistryValidationError) as exc_info:
                validate_registry(app)
            # 这条登记的路径在 app.routes 里「找不到」（因为真实路径带 :uuid）
            assert exc_info.value.missing, (
                "漏写转换器必须被判成 missing（登记的路由不存在）"
            )
        finally:
            EXPORT_SURFACE_REGISTRY.pop(key, None)

        validate_registry(app)  # 还原后必须重新闭合

    def test_classification_gaps_do_not_grow(self) -> None:
        """分类一致性缺口是棘轮：只许减少，不许增加。

        背景见 `export_surface_registry.CLASSIFICATION_GAP_FILE` 的注释：
        `_AUTO_SURFACES` 的分类是按路径关键字自动打的，没经过实现验证。
        现算 180 条「声明了某分类但实现缺少该分类要求的行为」：
          - formal 无 `ExportUnitPolicy` 折算（52 条）
          - data_exchange 无 `_GT_EXPORT_META`（128 条）

        本判据要求：
        1. 登记表与现算**双向一致**（`resolved` / `new` 都为空）；
        2. 总数不超过当前基线（新增缺口必须补登记，且总数只许减少）。

        🔴 反向自检：把某条登记删掉 ⇒ `new` 非空必红；
        给某条补上 `ExportUnitPolicy` 但忘了删登记 ⇒ `resolved` 非空必红。
        """
        from app.main import app
        from app.services.export_surface_registry import (
            load_classification_gaps,
            verify_classification_conformance,
        )

        registered = load_classification_gaps()
        assert registered, "缺口登记为空 —— 判据分母为 0，无法验证"

        resolved, new = verify_classification_conformance(app)
        assert not new, (
            f"{len(new)} 条新缺口未登记（声明分类与实现不符，须补进 "
            f"export_surface_classification_gaps.json）: {new[:8]}"
        )
        assert not resolved, (
            f"{len(resolved)} 条缺口已修好但仍在登记表里（须从 JSON 删除）: "
            f"{resolved[:8]}"
        )

        # 棘轮上限：只许减少
        BASELINE = 180
        assert len(registered) <= BASELINE, (
            f"缺口总数 {len(registered)} > 基线 {BASELINE} —— 新增缺口必须"
            "先修好再登记，或按业务语义调整分类（不能靠加登记蒙过去）"
        )

        # 🔴 分母非空自检：`verify` 必须真的扫到东西。
        # 实测：把 verify 改成恒返回 ([], []) 时，上面两个 `assert not ...`
        # 全部恒真（空转）⇒ 判据全绿而什么都没验证。这里要求它真的算出
        # 「登记数 == 现算数」这一等式，而不只是「两个差集为空」。
        from app.services.export_surface_registry import classify_conformance

        by_pm = {}
        for r in app.routes:
            p = getattr(r, "path", None)
            if not p:
                continue
            for m in getattr(r, "methods", None) or ():
                by_pm[(p, m)] = r

        from app.services.export_surface_registry import EXPORT_SURFACE_REGISTRY

        actual_gap_count = 0
        for entry in EXPORT_SURFACE_REGISTRY.values():
            if entry.retired or entry.classification not in ("formal", "data_exchange"):
                continue
            route = by_pm.get((entry.path, entry.method))
            if route is None:
                continue
            if classify_conformance(route, entry.classification) not in (
                "ok",
                "unverifiable",
            ):
                actual_gap_count += 1

        assert actual_gap_count > 0, (
            "现算缺口数为 0 —— 判据分母为 0（要么扫描逻辑坏了，要么"
            "classify_conformance 恒返 ok）"
        )
        assert actual_gap_count == len(registered), (
            f"现算缺口 {actual_gap_count} != 登记 {len(registered)} —— "
            "两边必须逐条对应（这也防 verify 恒返回空集）"
        )

        # 🔴 关键：上面的重算绕过了 `verify`，所以 `verify` 自己坏掉时它照样过。
        # 这里直接验证 `verify` 的**输出内容**：往登记表临时注入一条已知缺口，
        # `verify` 必须把它算进 `resolved`（因为它现算不出该缺口）。
        # 这钉住「verify 真的在算」，而不只是「它没报错」。
        import app.services.export_surface_registry as reg_mod

        probe = "/api/_probe/conformance/export"
        original_loader = reg_mod.load_classification_gaps
        try:
            reg_mod.load_classification_gaps = lambda: frozenset(
                set(original_loader()) | {probe}
            )
            resolved2, _new2 = verify_classification_conformance(app)
            assert probe in resolved2, (
                "verify 未把注入的假缺口算进 resolved —— 说明它没有真的做"
                f"双向比对（resolved={resolved2[:5]}）"
            )
        finally:
            reg_mod.load_classification_gaps = original_loader

        # 还原后必须重新干净
        resolved3, new3 = verify_classification_conformance(app)
        assert resolved3 == [] and new3 == []

    def test_classification_gap_file_schema(self) -> None:
        """缺口登记文件的 schema 必须完整（防止手改出半截文件）。"""
        import json
        from pathlib import Path

        from app.services.export_surface_registry import (
            CLASSIFICATION_GAP_FILE,
            load_classification_gaps,
        )

        path = Path(__file__).resolve().parents[1] / CLASSIFICATION_GAP_FILE
        assert path.is_file(), f"缺口登记文件不存在: {path}"

        raw = json.loads(path.read_text(encoding="utf-8"))
        for field in ("_doc", "_counts", "gaps", "detail"):
            assert field in raw, f"缺口登记文件缺字段 {field}"

        gaps = raw["gaps"]
        detail = raw["detail"]
        assert len(gaps) == len(set(gaps)), "gaps 有重复项"
        assert len(gaps) == len(detail), (
            f"gaps({len(gaps)}) 与 detail({len(detail)}) 数量不一致"
        )

        # 每条 detail 必须含可追溯字段
        for d in detail:
            for f in ("path", "key", "declared", "gap", "auto"):
                assert f in d, f"detail 项缺字段 {f}: {d}"
            assert d["declared"] in ("formal", "data_exchange"), d
            assert d["gap"] in (
                "formal_missing_unit_policy",
                "data_exchange_missing_marker",
            ), d

        # load_classification_gaps 必须与文件一致
        assert set(load_classification_gaps()) == set(gaps)

        # 计数必须与 detail 实际分布一致（防止手改 counts 掩盖漂移）
        actual: dict[str, int] = {}
        for d in detail:
            actual[d["gap"]] = actual.get(d["gap"], 0) + 1
        assert raw["_counts"] == actual, (
            f"_counts 与实际分布不符: 文件 {raw['_counts']} vs 实际 {actual}"
        )

    def test_retired_entries_really_have_no_route(self) -> None:
        """退役条目必须真的没有路由 —— 防止「删不掉就标退役」掩盖真实出口。"""
        from app.main import app

        actual_paths = {getattr(r, "path", None) for r in app.routes}
        offenders = [
            f"{key}: {entry.path}"
            for key, entry in EXPORT_SURFACE_REGISTRY.items()
            if entry.retired and entry.path in actual_paths
        ]
        assert not offenders, (
            f"标了 retired 但路由真实存在（应从 retired 撤下并参与闭合）: {offenders}"
        )

    def test_missing_is_zero(self) -> None:
        """`missing` 必须为 0（原 12，2026-11-16 已逐条治理完毕）。

        🔴 这是一条**棘轮**：任何新增「登记了但没实现」的路径都会打红。
        """
        from app.main import app

        try:
            validate_registry(app)
        except RegistryValidationError as exc:
            assert not exc.missing, f"注册表 missing 不为 0: {exc.missing}"

    def test_unregistered_is_zero(self) -> None:
        """`unregistered` 必须为 0（原 303，2026-11-16 已全部补登记）。

        🔴 这条棘轮此前**刻意缺位**：注释写着「unregistered 是既有历史漂移
        （303 条，属独立工作量），本判据只管 missing」。后果是**元数据口径改动
        完全没有判据守护** —— 实测把 `is_metadata_only_export_path` 整个删掉
        （让 status/history/manifest 都算导出出口）时，全部用例仍然全绿。

        现在漂移已清零，闭合性必须双向：
        - `missing` = 登记了没实现；
        - `unregistered` = 实现了没登记（新加导出端点不登记会打红）。
        """
        from app.main import app

        try:
            validate_registry(app)
        except RegistryValidationError as exc:
            assert not exc.unregistered, (
                "注册表 unregistered 不为 0（新增导出端点必须补登记）: "
                f"{exc.unregistered}"
            )

    def test_registry_is_fully_closed(self) -> None:
        """三向闭合：missing / unregistered / duplicates 全为 0。

        与前两条的区别：那两条各自只看一个方向，本判据要求 `validate_registry`
        **完全不抛**。这样「只修好 missing 就以为闭合」不再可能。
        """
        from app.main import app

        validate_registry(app)  # 不抛即闭合

    def test_auto_entries_description_matches_classification(self) -> None:
        """自动段的 description 必须按分类取自 `_AUTO_DESCRIPTIONS`。

        🔴 反向自检：实测把 `description=_AUTO_DESCRIPTIONS[_cls]` 改成固定取
        某一类（如 `["non_amount"]`）时，全部用例仍然全绿 —— 描述看起来「只是
        文档」，但它直接决定用户在导出面板看到的说明文案，写错等于把
        「导入模板」标成「元数据查询」。本判据钉住这个映射。
        """
        from app.services.export_surface_registry import (
            EXPORT_SURFACE_REGISTRY,
            _AUTO_DESCRIPTIONS,
        )

        auto = {k: v for k, v in EXPORT_SURFACE_REGISTRY.items() if k.startswith("auto_")}
        assert auto, "自动段为空 —— 判据分母为 0，无法验证"

        wrong = [
            f"{k}: classification={v.classification} description={v.description!r}"
            for k, v in auto.items()
            if v.description != _AUTO_DESCRIPTIONS[v.classification]
        ]
        assert not wrong, (
            f"{len(wrong)} 条自动条目的 description 与分类不符（应取 _AUTO_DESCRIPTIONS[分类]）: "
            f"{wrong[:5]}"
        )

    def test_auto_surfaces_cover_all_three_file_classes(self) -> None:
        """自动段必须覆盖 formal / data_exchange / template 三类文件出口。

        🔴 反向自检：把展开循环里的 `_cls` 写死成 `'formal'` 时，
        `test_metadata_only_paths_are_not_export_sinks` 与闭合判据都不会红
        （路径仍真实存在），但 124 条模板出口会被误标成「正式出具」——
        那正是导出面板分类统计错误的来源。本判据钉住分类列真的被使用。
        """
        import collections

        from app.services.export_surface_registry import EXPORT_SURFACE_REGISTRY

        auto = {k: v for k, v in EXPORT_SURFACE_REGISTRY.items() if k.startswith("auto_")}
        counts = collections.Counter(v.classification for v in auto.values())

        # 三个文件出口分类都必须在自动段出现（否则说明分类列被压平）
        for cls in ("formal", "data_exchange", "template"):
            assert counts[cls] > 0, (
                f"自动段没有任何 {cls} 条目（分类列可能被写死）: {dict(counts)}"
            )
        # 数量下限（防止只留 1~2 条就过）
        assert counts["template"] >= 100, (
            f"template 条目只有 {counts['template']} 条，应 >= 100"
        )
        assert counts["data_exchange"] >= 100, (
            f"data_exchange 条目只有 {counts['data_exchange']} 条，应 >= 100"
        )
        assert sum(counts.values()) == len(auto)

    def test_metadata_only_paths_are_not_export_sinks(self) -> None:
        """导出任务的元数据查询不算文件 sink。

        🔴 反向自检：`is_metadata_only_export_path` 若被弱化（只认 /status、
        或整个删掉），本判据必打红 —— 这是上一条棘轮抓不到的口径回归。
        """
        from app.services.export_surface_registry import is_metadata_only_export_path

        # 这些是**任务元数据**，不产文件字节
        metadata_paths = [
            "/api/export/{}/status",
            "/api/export/{}/history",
            "/api/exports/{}",
            "/api/exports/{}/manifest",
            "/api/exports/{}/integrity",
            "/api/exports/{}/download-token",
            "/api/projects/{project_id}/workpapers/{wp_id}/export-history",
        ]
        for p in metadata_paths:
            assert is_metadata_only_export_path(p), (
                f"{p} 应判为元数据型（不产文件），口径被弱化"
            )

        # 这些是**真实文件 sink**，不得被误判为元数据
        sink_paths = [
            "/api/exports/{}/download",
            "/api/export/{}/download",
            "/api/workpapers/{wp_id}/d1/export-data",
            "/api/workpapers/{wp_id}/d1/export-template",
            "/api/projects/{project_id}/notes/export-word",
            "/api/projects/{project_id}/deliverables/package/{package_id}/download",
        ]
        for p in sink_paths:
            assert not is_metadata_only_export_path(p), (
                f"{p} 是真实文件 sink，不得被当元数据排除"
            )

    def test_retired_flag_defaults_false(self) -> None:
        """`retired` 默认 False —— 否则新加条目会静默不参与闭合判定。"""
        entry = ExportSurfaceEntry(
            path="/api/x/export",
            method="GET",
            classification="formal",
            description="probe",
        )
        assert entry.retired is False
