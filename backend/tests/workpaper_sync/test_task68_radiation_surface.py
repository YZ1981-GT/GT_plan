# -*- coding: utf-8 -*-
"""任务 68 门 —— 辐射面 / 既存红 判据。

拆分自 `backend/tests/workpaper_sync/test_task68_backend_chain_regression.py`（原 1809 行 > pre-commit 行数门禁 whitelist 基线 1581 + 5% = 1660）。
判据本体**原样搬移**，一条断言未改、未删；宿主的接线（GATE / fixtures）按路径加载复用，
不抄第二份 —— 抄第二份会让「宿主与本文件对同一个门的认知」可能分叉。

census 机制本身见 `backend/scripts/_census_lock.py`。
"""
from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from typing import Any, Mapping  # noqa: F401  搬移来的签名用得到

import pytest  # noqa: F401  搬移来的用例可能用到

_HOST_PATH = Path(__file__).with_name("test_task68_backend_chain_regression.py")
_spec = importlib.util.spec_from_file_location("_task68_census_host", _HOST_PATH)
assert _spec is not None and _spec.loader is not None
_host = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _host
_spec.loader.exec_module(_host)

GATE = _host.GATE
GATE_PATH = _host.GATE_PATH
REPO = _host.REPO
_THIS = _host._THIS
_clean_suite_record = _host._clean_suite_record
ast = _host.ast

report = _host.report  # noqa: F811  fixture 需在本模块命名空间
live = _host.live  # noqa: F811  同上

class TestRadiationSurfaceAndPreexistingReds:
    def test_surface_is_recomputed_from_references_not_hand_written(
        self, report: dict[str, Any]
    ) -> None:
        """辐射面的**选取契约**逐字节锁死；计数/成员清单/digest 走 census 现算断言。

        🔴 这条判据原来比 `fresh["digest"] == recorded["digest"]` —— 那是把「本仓库今天有多少
        文件引用了被验模块」冻进了锁：任意新增一个引用被验模块的测试文件都让它打红（BP-74-1
        实测）。改成两段：①**现算**辐射面并断言语义性质（非空 / 不是全量 / 每条 pattern 都有
        命中者 / 目录外差集非空）；②选取契约（patterns / pattern_coverage / 两条差集存在性）
        逐字节与记录相等 —— scanner 被改坏时它立刻变红，而仓库长大不再打红。
        """
        fresh = GATE.radiation_surface()
        recorded = report["radiation_surface"]

        # ① 现算侧：语义性质（不随仓库演进 ⇒ 可以断言、可以进锁）
        semantics = GATE.census_semantics(fresh)
        assert semantics["all_hold"] is True, (
            f"辐射面普查语义断言不成立: {semantics['failing_checks']}"
            f"（无命中者的 pattern: {semantics['patterns_without_a_match']}）"
        )
        assert int(fresh["scanned_test_files"]) > 1000, (
            "扫描分母过小 ⇒ 没有真的遍历 `backend/tests/**`"
        )
        assert 20 <= int(fresh["surface_size"]) < int(fresh["scanned_test_files"]), (
            "辐射面等于全量或几乎为空 —— 正文逐字「不跑无边界全量」，也不能空集恒真"
        )
        assert fresh["outside_files"], (
            "辐射面里没有 `workpaper_sync/` 目录外的文件 ⇒ 引用关系反查大概率退化成了目录枚举"
        )

        # ② 记录侧：选取契约逐字节相等（scanner 或 pattern 名单被改立刻打红）
        assert fresh["patterns"] == recorded["patterns"], "辐射面 pattern 名单漂移"
        assert fresh["pattern_coverage"] == recorded["pattern_coverage"], (
            "逐 pattern 覆盖布尔漂移 ⇒ 某条选取规则今天选不到东西了"
        )
        assert (
            fresh["has_files_outside_the_sync_dir"]
            == recorded["has_files_outside_the_sync_dir"]
        )
        assert (
            fresh["has_in_dir_files_out_of_surface"]
            == recorded["has_in_dir_files_out_of_surface"]
        )
        assert recorded["census_derived_keys"] == sorted(
            key.split(".", 1)[1]
            for key in GATE.CENSUS_KEYS
            if key.startswith("radiation_surface.")
        ), "报告里登记的 census 键与门的常量不符 ⇒ 剔了什么无从核对"

    def test_in_dir_but_out_of_surface_files_are_listed_not_hidden(
        self, report: dict[str, Any]
    ) -> None:
        recorded = report["radiation_surface"]
        assert "in_dir_but_out_of_surface" in recorded
        assert recorded["in_dir_but_out_of_surface_note"]
        for path in recorded["in_dir_but_out_of_surface"]:
            assert (REPO / path).exists(), f"清单里的文件不存在: {path}"
            assert path not in recorded["files"], f"{path} 同时出现在两侧"

    def test_census_derived_quantities_are_excluded_from_the_byte_lock(
        self, report: dict[str, Any]
    ) -> None:
        """普查派生量必须被 `strip_census` 剔掉，选取契约必须留下。

        🔴 BP-74-1：辐射面按引用关系派生，其规模/成员清单/digest 进了逐字节锁 ⇒ 新增一个引用
        了被验模块的测试文件就打红三条守卫。正反两面各一条：
        * 正面 —— 塞一个合成的新辐射面成员，投影必须**不变**；
        * 反面 —— 动选取契约（`patterns` / `pattern_coverage`），投影必须**变**。
        """
        assert GATE.CENSUS_KEYS, "CENSUS_KEYS 为空 ⇒ 普查免疫没有落点"
        assert "radiation_surface.surface_size" in GATE.CENSUS_KEYS
        assert "radiation_surface.scanned_test_files" in GATE.CENSUS_KEYS
        assert "properties.rows[].annotated_in_surface_files" in GATE.CENSUS_KEYS, (
            "Property 落点里的「被辐射面几个文件点名」也是普查派生量 —— 漏了它仍会被顶红"
        )

        base = GATE.strip_census(dict(report))
        grown = copy.deepcopy(dict(report))
        node = grown["radiation_surface"]
        node["surface_size"] = int(node["surface_size"]) + 1
        node["inside_workpaper_sync_dir"] = int(node["inside_workpaper_sync_dir"]) + 1
        node["scanned_test_files"] = int(node["scanned_test_files"]) + 9
        node["files"]["backend/tests/synthetic/test_brand_new.py"] = ["sync_services_module"]
        node["digest"] = "0" * 64
        grown["properties"]["rows"][0]["annotated_in_surface_files"] = 9_999
        assert GATE.strip_census(grown) == base, (
            "辐射面长大让投影变了 ⇒ 普查量又被冻进锁了（BP-74-1 复发）"
        )

        for field in ("patterns", "pattern_coverage", "has_files_outside_the_sync_dir"):
            tampered = copy.deepcopy(dict(report))
            value = tampered["radiation_surface"][field]
            tampered["radiation_surface"][field] = {} if isinstance(value, dict) else False
            assert GATE.strip_census(tampered) != base, (
                f"把辐射面选取契约字段 {field} 清空后投影没变 ⇒ strip_census 剔多了"
            )
        tiered = copy.deepcopy(dict(report))
        tiered["properties"]["rows"][0]["tier"] = "synthetic"
        assert GATE.strip_census(tiered) != base, (
            "改掉 Property 档位后投影没变 ⇒ 档位被误当成普查量剔掉了"
        )

    def test_census_semantics_are_asserted_not_merely_skipped(self) -> None:
        """剔除 ≠ 不管：喂植入的退化辐射面，语义断言必须逐条打红且**正是**预期那条。"""
        live = GATE.radiation_surface()
        assert GATE.census_semantics(live)["all_hold"] is True, (
            f"真实辐射面的语义断言就不成立: {GATE.census_semantics(live)['failing_checks']}"
        )
        for label, mutated, expect in (
            ("空集", dict(live, surface_size=0, files={}), "surface_is_not_empty"),
            ("不遍历", dict(live, scanned_test_files=0), "walk_really_traversed_the_tree"),
            (
                "退化成全量",
                dict(live, surface_size=int(live["scanned_test_files"])),
                "surface_is_not_the_whole_tree",
            ),
            (
                "某条 pattern 零命中",
                dict(
                    live,
                    pattern_coverage={**live["pattern_coverage"], "sync_router_module": False},
                ),
                "every_pattern_has_a_match",
            ),
            (
                "退化成目录枚举",
                dict(live, has_files_outside_the_sync_dir=False),
                "surface_reaches_outside_the_sync_dir",
            ),
            (
                "差集如实报告被短路",
                dict(live, has_in_dir_files_out_of_surface=False),
                "in_dir_difference_is_still_reported",
            ),
        ):
            result = GATE.census_semantics(mutated)
            assert result["all_hold"] is False, f"{label}：语义断言没打红 ⇒ 剔除退化成了不看"
            assert expect in result["failing_checks"], (
                f"{label}：打红的不是预期那条（实得 {result['failing_checks']}）"
            )

    def test_census_contract_declares_what_is_still_locked(self, report: dict[str, Any]) -> None:
        """普查契约必须写明「剔了什么」「为什么」「什么仍然锁死」，三者缺一即无从复核。"""
        contract = report["census_contract"]
        assert sorted(contract["census_keys"]) == sorted(GATE.CENSUS_KEYS)
        assert str(contract["why"]).strip()
        assert str(contract["excluded_is_not_unchecked"]).strip()
        locked = "\n".join(contract["still_locked"])
        assert "source_commit" in locked, "没写明 source_commit 仍然锁死 ⇒ 真 stale 轴可能被削弱"
        assert "pattern_coverage" in locked
        assert contract["semantics"]["all_hold"] is True

    def test_this_guard_file_ran_in_the_same_execution(self, report: dict[str, Any]) -> None:
        """本守卫**不在**辐射面（它验的是门，不引用被验生产单元），但必须同批跑掉。

        否则「门自己绿不绿」在报告里就没有实证 —— 只剩一句自称。
        """
        me = _THIS.relative_to(REPO).as_posix()
        suite = report["suite_verdict"]
        assert suite["own_guard_included"] is True, "那次执行没有带上本守卫"
        assert suite["own_guard_path"] == me, (
            f"记录里的守卫路径 {suite['own_guard_path']} 与本文件 {me} 不一致"
        )
        assert int(suite["executed_file_count"]) >= int(suite["file_count"]), (
            "执行文件数小于辐射面文件数 ⇒ 有文件被漏掉"
        )
        # 本守卫可能**恰好**也在辐射面里（它现读 V151/V152 核对 scratch DDL 集合 ⇒ 命中
        # `scratch_migrations` 模式）。那不是自证：命中理由必须是真实的引用模式，且无论
        # 在不在辐射面里，`own_guard_included` 都独立保证它跑掉了。
        surface_files = report["radiation_surface"]["files"]
        if me in surface_files:
            assert surface_files[me], "在辐射面里却没记命中了哪条引用模式"
            for reason in surface_files[me]:
                assert reason in dict(GATE._SURFACE_PATTERNS), f"未知命中理由: {reason}"

    def test_every_preexisting_red_is_registered_with_attribution_and_owner(self) -> None:
        for entry in GATE.PREEXISTING_FAILURES:
            assert entry["attribution"], f"{entry['file']} 没有归因"
            assert entry["owner_task"], f"{entry['file']} 没有 owner"
            assert entry["why_not_fixed_here"], f"{entry['file']} 没说明为何不在本任务修"
            assert (REPO / str(entry["file"])).exists(), f"登记的文件不存在: {entry['file']}"

    def test_the_registered_baseline_matches_the_real_run(self, report: dict[str, Any]) -> None:
        suite = report["suite_verdict"]
        bad = [row["file"] for row in suite["preexisting"] if not row["agrees"]]
        assert not bad, (
            f"既存红逐项核对不上: {bad} —— 声明与实测必须一致（多了要归因，少了说明基线过期）"
        )
        assert suite["unexpected_failed_nodeids"] == [], (
            f"出现未登记的失败: {suite['unexpected_failed_nodeids']}"
        )
        assert suite["unexpected_error_nodeids"] == [], (
            f"出现未登记的 error: {suite['unexpected_error_nodeids']}"
        )
        own = suite["own_guard_result"]
        # 🔴 这里**刻意不**断言 `own["clean"]`：pytest 先跑、报告后写，本守卫读到的永远是
        #    上一份报告 —— 自我断言会变成不动点迭代（4→1→0），每轮 16 分钟。
        #    「本门守卫必须全绿」这条由**门的判定**承担（`verdict.suite_passed` 现算自记录），
        #    它不在循环里，一轮即收敛。这里只断言**分桶完整**：任何失败都必须归入
        #    「已登记既存红」或「本门守卫」二者之一，不得有第三类被静默。
        assert int(suite["observed_errors"]) == int(suite["declared_preexisting_errors"])
        assert (
            int(suite["observed_failed"])
            == int(suite["declared_preexisting_failed"]) + len(own["failed"])
        ), (
            "观测失败数 ≠ 已登记既存红 + 本门守卫失败数 ⇒ 有失败既不属既存红也不属本门守卫，"
            "而 `unexpected_failed_nodeids` 却是空的（分桶漏了一类）"
        )

    def test_error_nodeids_are_actually_captured(self, report: dict[str, Any]) -> None:
        """`-rf` 只列 FAILED；ERROR 必须靠 `-rfE` 才进短摘要，否则 6 个 error 永远对不上。"""
        suite = report["suite_run"]
        assert "-rfE" in str(suite["command"]), "pytest 调用里缺 `-rfE` ⇒ ERROR 不会被记 nodeid"
        assert suite["error_nodeids"], "记录里没有任何 error nodeid，但计数非零"
        assert len(suite["error_nodeids"]) == int(suite["counts"].get("errors", 0))

    def test_surface_extras_are_recomputed_live_not_only_read(
        self, report: dict[str, Any]
    ) -> None:
        """辐射面的每个字段都要**现算**并有判据 —— 只读磁盘对 scanner 侧改动天生不敏感。

        🔴 原判据把六个字段逐个 `fresh[key] == recorded[key]`，其中五个是普查派生量
        （计数与成员清单）⇒ 仓库长大即打红（BP-74-1）。现在：普查派生量断言**语义性质**
        （非空 / 关系 / 差集仍在），非普查字段继续等值比对。
        """
        fresh = GATE.radiation_surface()
        recorded = report["radiation_surface"]

        # 普查派生量：现算并断言语义关系，不与冻结基线等值比
        assert int(fresh["surface_size"]) == int(fresh["inside_workpaper_sync_dir"]) + int(
            fresh["outside_workpaper_sync_dir"]
        ), "辐射面规模 ≠ 目录内 + 目录外 ⇒ 分桶漏了一类"
        assert len(fresh["files"]) == int(fresh["surface_size"])
        assert len(fresh["outside_files"]) == int(fresh["outside_workpaper_sync_dir"])
        assert fresh["digest"] == GATE.digest_of(sorted(fresh["files"])), (
            "辐射面 digest 与文件清单脱钩 ⇒ 改 scanner 不会让 digest 变"
        )
        # 逐 pattern 覆盖布尔必须**真的由成员清单派生**：写成恒真时它照样与记录相等
        # （记录里今天也全是 True），只有从同一份 `files` 重算才能抓到。
        assert fresh["pattern_coverage"] == {
            name: any(name in why for why in fresh["files"].values())
            for name, _ in GATE._SURFACE_PATTERNS
        }, "逐 pattern 覆盖布尔与成员清单脱钩 ⇒ 恒真的选取契约"
        assert fresh["in_dir_but_out_of_surface"], (
            "现算的「在目录里但不引用被验单元」差集为空 —— 本轮实测该目录确实有这类文件，"
            "空集意味着这条如实报告被短路了"
        )
        for path in fresh["in_dir_but_out_of_surface"]:
            assert path not in fresh["files"], f"{path} 同时出现在两侧"

        # 非普查字段：继续与记录逐字节相等
        for key in (
            "statement",
            "patterns",
            "pattern_coverage",
            "has_files_outside_the_sync_dir",
            "has_in_dir_files_out_of_surface",
            "in_dir_but_out_of_surface_note",
            "census_derived_keys",
        ):
            assert fresh[key] == recorded[key], f"辐射面选取契约字段 {key} 漂移"

        # 每个被剔的键都必须**真的**在 CENSUS_KEYS 里登记（剔了什么必须可核对）
        for key in (
            "surface_size",
            "inside_workpaper_sync_dir",
            "outside_workpaper_sync_dir",
            "in_dir_but_out_of_surface",
            "outside_files",
            "files",
            "digest",
            "scanned_test_files",
        ):
            assert f"radiation_surface.{key}" in GATE.CENSUS_KEYS, (
                f"{key} 既不与记录等值比对、也没登记成 census ⇒ 它变成了没有判据的字段"
            )

    def test_the_suite_command_keeps_error_reporting_on(self) -> None:
        """`-rfE` 必须写在**门的源码**里，不能只在磁盘记录里看着对。"""
        source = ast.unparse(GATE.function_def(GATE.module_ast(GATE_PATH), "run_radiation_suites"))
        assert "-rfE" in source, (
            "pytest 调用里缺 `-rfE` ⇒ ERROR 不进短摘要，6 个 collection/setup ERROR 会全部"
            "变成「无 nodeid」，既存红逐项核对永远对不上而总计数看起来还是对的"
        )
        assert "'-rf'" not in source and '"-rf"' not in source

    def test_suite_reconciliation_is_a_pure_function_of_the_record(
        self, report: dict[str, Any]
    ) -> None:
        """用合成 suite 记录直接喂回 `evaluate_suite_run`，逐条结论必须跟着变。

        🔴 只断言磁盘记录的判据对「核对逻辑本身被短路」完全不敏感（教训 17）。
        """
        surface = report["radiation_surface"]
        # 🔴 baseline 必须取**随 suite 记录前滚**的那个 digest，而不是现算/当前的辐射面：
        #    suite 记录覆盖的辐射面是过去的事实，拿它和现在的辐射面等值比对就是 BP-74-1。
        carried = {"digest": report["suite_verdict"]["recorded_surface_digest"]}
        recomputed = GATE.evaluate_suite_run(report["suite_run"], surface, carried)
        assert recomputed["passed"] == report["suite_verdict"]["passed"], "suite 结论不可复算"
        assert recomputed["preexisting_all_agree"] == report["suite_verdict"][
            "preexisting_all_agree"
        ]

        base = _clean_suite_record(report)
        clean = GATE.evaluate_suite_run(base, surface)
        assert clean["passed"] is True, (
            "合成的「一切干净」记录必须先判通过（对照组）—— 不过则后面每条否定臂都无信息量"
        )
        # ① 声明与实测不符 ⇒ agrees 必须变假
        entry = GATE.PREEXISTING_FAILURES[0]
        stem = Path(str(entry["file"])).name
        shrunk = dict(
            base,
            failed_nodeids=[n for n in base["failed_nodeids"] if stem not in n],
            counts=dict(base["counts"], failed=int(base["counts"]["failed"]) - 1),
        )
        verdict = GATE.evaluate_suite_run(shrunk, surface)
        row = next(r for r in verdict["preexisting"] if Path(str(r["file"])).name == stem)
        assert row["agrees"] is False, (
            "已登记既存红在实测里消失后 `agrees` 仍为真 ⇒ 逐项核对被短路（基线过期不会被发现）"
        )
        assert verdict["passed"] is False

        # ② 本门守卫自身的红必须单列且让 suite 判定失败
        own = f"{GATE.OWN_GUARD_PATH}::TestSynthetic::test_synthetic"
        with_own = dict(
            base,
            failed_nodeids=[*base["failed_nodeids"], own],
            counts=dict(base["counts"], failed=int(base["counts"]["failed"]) + 1),
        )
        verdict2 = GATE.evaluate_suite_run(with_own, surface)
        bucketed = verdict2["own_guard_result"]["failed"]
        # 不比整个集合（记录里本来可能已有若干本门守卫的红，那与本判据无关）——
        # 只要求「合成的那条被正确分桶」且「这一桶里只有本门守卫的 nodeid」。
        assert own in bucketed, (
            "本门守卫的失败没有被单列 ⇒ 会与「未登记的第三类失败」混在一起无法区分"
        )
        assert all(GATE.OWN_GUARD_PATH.split("/")[-1] in n for n in bucketed), (
            f"本门守卫桶里混进了别的文件: {bucketed}"
        )
        assert verdict2["own_guard_result"]["clean"] is False
        assert own not in verdict2["unexpected_failed_nodeids"], (
            "本门守卫的失败被误算成「未登记的既存红」⇒ 自指，永不收敛"
        )
        assert verdict2["passed"] is False, (
            "本门守卫全红时 suite 仍判通过 ⇒ 「跑了自己的守卫」被当成「守卫真的绿」"
        )

        # ③ 真正未登记的第三类失败必须进 unexpected
        stranger = "backend/tests/workpaper_sync/test_task00_not_registered.py::test_x"
        with_stranger = dict(
            base,
            failed_nodeids=[*base["failed_nodeids"], stranger],
            counts=dict(base["counts"], failed=int(base["counts"]["failed"]) + 1),
        )
        verdict3 = GATE.evaluate_suite_run(with_stranger, surface)
        assert verdict3["unexpected_failed_nodeids"] == [stranger]
        assert verdict3["passed"] is False

        # ④ suite 记录的 digest 与**同源**辐射面 digest 不一致必须失败（报告被手改/拼接）
        drifted = GATE.evaluate_suite_run(dict(base, files_digest="synthetic"), surface)
        assert drifted["suite_digest_matches_recorded_surface"] is False
        assert drifted["passed"] is False

        # ⑤ 辐射面**长大**不得打红（仓库在演进 —— BP-74-1 的根因就是把这件事当成 stale）
        grown = GATE.evaluate_suite_run(
            base,
            dict(surface, surface_size=int(surface["surface_size"]) + 7),
            surface,
        )
        assert grown["suite_digest_matches_recorded_surface"] is True
        assert grown["live_surface_covers_run"] is True
        assert int(grown["surface_growth_since_run"]) > 0
        assert grown["passed"] is True, (
            "辐射面长大就把 suite 判成不通过 ⇒ 判据要求仓库停止演进（BP-74-1 的形态）"
        )

        # ⑥ 辐射面**缩到已执行集合以下**必须打红（scanner 被改窄）
        narrowed = GATE.evaluate_suite_run(
            base,
            dict(surface, surface_size=int(base["file_count"]) - 1),
            surface,
        )
        assert narrowed["live_surface_covers_run"] is False
        assert narrowed["passed"] is False, (
            "scanner 被改窄到已执行集合以下仍判通过 ⇒ 「改 scanner 蒙过去」有了落脚点"
        )

    def test_this_task_did_not_introduce_new_reds(self, report: dict[str, Any]) -> None:
        introduced = [
            row
            for row in report["suite_verdict"]["preexisting"]
            if row.get("discovered_by_this_task") and str(row.get("owner_task")) == "68"
            and (int(row["observed_failed"]) or int(row["observed_errors"]))
        ]
        assert not introduced, (
            f"本任务自己引入的红没有清零: {[r['file'] for r in introduced]}"
        )
