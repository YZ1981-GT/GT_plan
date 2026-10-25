# -*- coding: utf-8 -*-
"""Task 8.2 / 8.3 / 8.4 / 8.5 —— digest 门 · 注入形态自我约束 · 原子性 · 真库对账。

spec: workpaper-sync-adopt-overwrite-and-refresh-source
Requirements 3.4 / 3.8 / 6.6 / 6.7 / 6.8

═══ 与主体的分工 ═══

主体 `test_aos_adopt_endpoint_http.py` = harness（一次 `asyncio.run` 采集）+ §0 采集完整性
+ §1（8.1 状态码映射表现算 + 五个分支各一例）。本文件 = 计划**算出来之后**的四组判据：

| 节 | 判据 | Task |
| --- | --- | --- |
| §2 | `plan_digest` 过期即 409，且 store 未变；正确 digest 不被拒（正向对照） | 8.2 |
| §3 | 注入形态自我约束：override 的是**内层**稳定对象 + 被测链未被 mock | 8.3 |
| §4 | 原子性：三个注入点 + 多 item 部分写入，一律 HTTP 5xx 且库一字节未变 | 8.4 |
| §5 | 真库对账：dry_run 的三清单与实际落库逐元素相等 | 8.5 |

🔴 **共用同一次采集**：`collect_once()` 从主体 import（**顶层模块名**，该目录无
`__init__.py`、pytest 走 `prepend`；写成 `tests.workpaper_sync.…` 会拿到第二个模块实例，
于是两份各跑一次采集 = 两套 scratch schema + 两倍真库写入）。跑本文件时**不要漏掉主体**，
否则 §1 的映射表判据不参与判定。
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Any

import pytest

from aos8_endpoint_world import (
    ADD_ID,
    DROP_ID,
    KEEP_ID,
    error_code,
    identities_in_store,
    identities_of,
    unwrap,
)
from test_aos_adopt_endpoint_http import collect_once

_HARNESS_PY = Path(__file__).resolve().parent / "test_aos_adopt_endpoint_http.py"
_WORLD_PY = Path(__file__).resolve().parent / "aos8_endpoint_world.py"


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return collect_once()


# ═══════════════════════════════════════════════════════════════════════════════
# §2 Task 8.2 —— `plan_digest` 不符 ⇒ 409（含正向对照）
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlanDigestGateOverRealHttp:
    """**Validates: Requirements 3.4**"""

    def test_dry_run_is_where_the_digest_comes_from(self, snap: dict[str, Any]) -> None:
        obs = snap["scenarios"]["digest_flow"]
        assert obs["dry_status"] == 200, obs["dry_envelope"]
        wire = obs["plan_wire"]
        digest = obs["digest"]
        assert len(digest) == 64 and digest == digest.lower(), digest
        assert set("0123456789abcdef") >= set(digest), digest
        assert wire.get("plan_digest") == digest
        # dry_run 那一趟什么都不该写（它是去取摘要的）
        assert obs["store_before"] == obs["store_after_dry"]

    def test_the_response_envelope_is_the_platform_one(self, snap: dict[str, Any]) -> None:
        """2xx 被 `ResponseWrapperMiddleware` 包成 `{code,message,data}` —— 对外契约。"""
        obs = snap["scenarios"]["digest_flow"]
        envelope = obs["dry_envelope"]
        assert isinstance(envelope, dict) and {"code", "message", "data"} <= set(envelope), envelope
        assert envelope["code"] == 200
        assert unwrap(envelope) is not envelope and unwrap(envelope) == obs["plan_wire"]

    def test_stale_digest_is_refused_with_409(self, snap: dict[str, Any]) -> None:
        obs = snap["scenarios"]["digest_flow"]
        assert obs["stale_digest"] != obs["digest"], "变异用的过期 digest 与真值相同 ⇒ 判据空跑"
        assert obs["bad_status"] == 409, obs["bad_body"]
        assert error_code(obs["bad_body"]) == "adopt_plan_digest_mismatch", obs["bad_body"]

    def test_stale_digest_leaves_the_store_untouched(self, snap: dict[str, Any]) -> None:
        obs = snap["scenarios"]["digest_flow"]
        assert obs["store_before"] == obs["store_after_bad"], "被拒的那次动过库（含 updated_at）"
        assert identities_in_store(obs["store_after_bad"]) == (KEEP_ID, DROP_ID)

    def test_correct_digest_is_not_refused(self, snap: dict[str, Any]) -> None:
        """🔴 正向对照：否则「409」可能只是「带 digest 一律拒」。"""
        obs = snap["scenarios"]["digest_flow"]
        assert obs["good_status"] == 200, obs["good_body"]
        assert obs["good_status"] != 409
        body = unwrap(obs["good_body"])
        assert body["dry_run"] is False and body["changed_item_count"] == 1, body
        assert identities_in_store(obs["store_after_good"]) == (KEEP_ID, ADD_ID), (
            "带正确 digest 的那次没有真覆盖 ⇒ 正向对照本身是空的"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# §3 Task 8.3 —— 两条注入纪律写成可执行判据
#
# ① 依赖工厂**不能**直接作 `dependency_overrides` 键（每次调用返回新函数对象 ⇒ key 匹配
#    不上 ⇒ override 静默失效）。正解 = override **内层** `get_current_user` / `get_db`。
# ② 被测链**不许**被 mock：四个函数须真在跑。
# ═══════════════════════════════════════════════════════════════════════════════


async def _factory_override_demo() -> dict[str, Any]:
    """一个自足的最小 app：把「工厂对象作 override 键会静默失效」变成可执行事实。"""
    from fastapi import Depends, FastAPI
    from httpx import ASGITransport, AsyncClient

    async def inner_dep() -> str:
        return "real-inner"

    def factory(tag: str):
        async def _dep(value: str = Depends(inner_dep)) -> str:
            return f"{tag}:{value}"

        return _dep

    produced = factory("prod")
    app = FastAPI()

    @app.get("/probe")
    async def probe(value: str = Depends(produced)) -> dict[str, str]:  # noqa: ANN202
        return {"value": value}

    out: dict[str, Any] = {
        "factory_products_are_distinct": factory("prod") is not factory("prod"),
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://demo") as client:
        out["baseline"] = (await client.get("/probe")).json()["value"]

        async def _fake_dep() -> str:
            return "OVERRIDDEN-BY-FACTORY-KEY"

        # ① 用**另一次调用工厂**得到的对象作键（这正是那个坑）
        app.dependency_overrides[factory("prod")] = _fake_dep
        out["by_new_factory_product"] = (await client.get("/probe")).json()["value"]
        app.dependency_overrides.clear()

        # ② 用**内层稳定对象**作键
        async def _fake_inner() -> str:
            return "inner-overridden"

        app.dependency_overrides[inner_dep] = _fake_inner
        out["by_inner_dep"] = (await client.get("/probe")).json()["value"]
        app.dependency_overrides.clear()

        # ③ 对照：用**同一个**已产出的对象作键时 override 是生效的（证明坑在「重新调工厂」）
        app.dependency_overrides[produced] = _fake_dep
        out["by_same_product"] = (await client.get("/probe")).json()["value"]
        app.dependency_overrides.clear()
    return out


@pytest.fixture(scope="module")
def factory_demo() -> dict[str, Any]:
    return asyncio.run(_factory_override_demo())


class TestOverrideFormDiscipline:
    """**Validates: Requirements 6.6**"""

    def test_a_factory_product_as_override_key_silently_does_nothing(
        self, factory_demo: dict[str, Any]
    ) -> None:
        assert factory_demo["factory_products_are_distinct"] is True, (
            "本仓的依赖工厂若返回同一个对象，这条纪律就不成立 —— 先确认机制再谈判据"
        )
        assert factory_demo["baseline"] == "prod:real-inner"
        assert factory_demo["by_new_factory_product"] == "prod:real-inner", (
            "工厂产物作 key 居然生效了 ⇒ 纪律的前提变了，须重新裁定"
        )
        assert factory_demo["by_same_product"] == "OVERRIDDEN-BY-FACTORY-KEY", (
            "同一个已产出对象作 key 也不生效 ⇒ 说明失效原因不是「对象不同」，归因错了"
        )

    def test_overriding_the_inner_dependency_really_works(
        self, factory_demo: dict[str, Any]
    ) -> None:
        assert factory_demo["by_inner_dep"] == "prod:inner-overridden"

    def test_the_harness_overrides_exactly_the_three_inner_dependencies(
        self, snap: dict[str, Any]
    ) -> None:
        assert snap["override_keys"] == [
            "app.core.database.get_db",
            "app.deps.get_current_user",
            "app.routers.wp_sync_router._services",
        ], snap["override_keys"]

    def test_the_override_keys_are_module_level_stable_objects(self) -> None:
        """三个 key 都是模块级函数对象（多次取属性同一个）—— 不是工厂产物。"""
        from app.core.database import get_db
        from app.deps import get_current_user
        from app.routers import wp_sync_router as SR

        import app.core.database as DB
        import app.deps as DEPS

        assert DB.get_db is get_db and DEPS.get_current_user is get_current_user
        assert SR._services is SR._services
        for fn in (get_db, get_current_user, SR._services):
            assert callable(fn) and not isinstance(fn, type)

    def test_authorization_really_ran(self, snap: dict[str, Any]) -> None:
        """🔴「鉴权真的跑过」：不带身份 ⇒ 401；带身份 ⇒ 不是 401，且 guard 真被调过。"""
        assert snap["scenarios"]["unauthenticated"]["status"] == 401, (
            "不带身份也没得到 401 ⇒ 鉴权根本没跑（override 静默失效的典型症状是反过来的"
            "「全部 401」，这一条守的是另一侧）"
        )
        authed = [
            snap["scenarios"][name]["status"]
            for name in ("workflow_locked", "revision_conflict", "digest_flow")
            if snap["scenarios"][name].get("status") is not None
        ]
        assert authed and all(code != 401 for code in authed), authed
        assert snap["scenarios"]["digest_flow"]["dry_status"] == 200
        assert snap["authorize_calls"], "guard 的 action 授权回调一次都没被调 ⇒ 鉴权被绕过了"
        assert set(snap["authorize_calls"]) == {"adopt_substrate"}, snap["authorize_calls"]
        assert len(snap["probe_calls"]) >= len(snap["authorize_calls"]), (
            "visibility 探针调用次数少于 action 授权次数 ⇒ 阶段顺序被跳过了"
        )


#: 被测链的四个函数（任务书逐字点名）—— `(模块属性路径, 期望定义所在模块)`。
_CHAIN: tuple[tuple[str, str, str], ...] = (
    (
        "app.services.workpaper_sync.adopt_substrate_response",
        "compute_adopt_substrate",
        "app.services.workpaper_sync.adopt_substrate_response",
    ),
    (
        "app.services.workpaper_sync.adopt_substrate_response",
        "compute_plan_for_adopt",
        "app.services.workpaper_sync.adopt_substrate_response",
    ),
    (
        "app.services.workpaper_sync.adopt_substrate_response",
        "verify_plan_digest",
        "app.services.workpaper_sync.adopt_substrate_response",
    ),
    (
        "app.services.workpaper_sync.adopt_overwrite_apply",
        "apply_overwrite_deletions",
        "app.services.workpaper_sync.adopt_overwrite_apply",
    ),
)


class TestTheTestedChainIsNotMocked:
    """**Validates: Requirements 6.6**

    两路证明：**对象同一性**（谁都没被换掉）+ **只有它们能产生的可观测副作用**（它们真跑了）。
    """

    @pytest.mark.parametrize("module_name,attr,defined_in", _CHAIN)
    def test_each_chain_member_is_still_the_production_object(
        self, module_name: str, attr: str, defined_in: str
    ) -> None:
        import importlib
        import unittest.mock as M

        module = importlib.import_module(module_name)
        fn = getattr(module, attr)
        assert not isinstance(fn, (M.Mock, M.MagicMock, M.AsyncMock)), f"{attr} 被 mock 掉了"
        assert getattr(fn, "__module__", "") == defined_in, (attr, fn.__module__)
        assert not hasattr(fn, "mock"), f"{attr} 带 mock 属性 ⇒ 被 patch 过"
        # router 持有的引用与生产模块里的是同一个对象
        from app.routers import wp_sync_router as SR

        if attr == "compute_adopt_substrate":
            assert SR.compute_adopt_substrate is fn

    def test_verify_plan_digest_really_ran(self, snap: dict[str, Any]) -> None:
        """`adopt_plan_digest_mismatch` 这个 error_code 全仓只有它会抛。"""
        obs = snap["scenarios"]["digest_flow"]
        assert error_code(obs["bad_body"]) == "adopt_plan_digest_mismatch"

    def test_compute_plan_for_adopt_really_ran(self, snap: dict[str, Any]) -> None:
        """wire form 的那几个键只有 `_plan_wire_form(plan)` 会产出（前端不自行重算）。"""
        wire = snap["scenarios"]["digest_flow"]["plan_wire"]
        assert {
            "plan_digest",
            "store_row_count",
            "substrate_row_count",
            "store_rows_by_table",
            "substrate_rows_by_table",
            "deltas",
            "skipped_items",
        } <= set(wire), sorted(wire)
        delta = wire["deltas"][0]
        assert delta["rows_added_count"] == len(delta["rows_added"])
        assert delta["rows_deleted_count"] == len(delta["rows_deleted"])

    def test_apply_overwrite_deletions_really_ran(self, snap: dict[str, Any]) -> None:
        """🔴 删除是**只有它**会做的事：`mirror_projection_into_store` 从不删行。"""
        obs = snap["scenarios"]["digest_flow"]
        before = set(identities_in_store(obs["store_before"]))
        after = set(identities_in_store(obs["store_after_good"]))
        assert DROP_ID in before and DROP_ID not in after, (before, after)

    def test_compute_adopt_substrate_really_ran(self, snap: dict[str, Any]) -> None:
        body = unwrap(snap["scenarios"]["digest_flow"]["good_body"])
        assert set(body) == {
            "dry_run",
            "substrate_sha256",
            "expected_revision",
            "changed_item_count",
            "changed_items",
        }, sorted(body)
        audit = snap["scenarios"]["reconcile"]["audit_after"]
        actions = {row["action"] for row in audit}
        assert "workpaper_sync.adopt_substrate" in actions, actions


def _call_attrs(path: Path) -> list[str]:
    """AST 现扫一个文件里全部被调用的名字（铁律 ㉖：禁文本 `in` —— 注释/docstring 会骗人）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            out.append(str(getattr(node.func, "id", getattr(node.func, "attr", ""))))
    return out


class TestTheHarnessReallySendsHttpOverAsgi:
    """源码锁：本组判据的观测面**真的**来自 ASGI 请求，不是直接调 service。

    **Validates: Requirements 6.6**
    """

    def test_the_harness_builds_an_asgi_transport_and_posts(self) -> None:
        calls = _call_attrs(_HARNESS_PY)
        assert calls.count("ASGITransport") >= 2, calls.count("ASGITransport")
        assert calls.count("AsyncClient") >= 2
        assert calls.count("post") >= 4, calls.count("post")
        assert "add_middleware" in calls and "include_router" in calls

    def test_the_scanner_is_not_matching_comments(self) -> None:
        """变异反证：同一扫描器对**没有** ASGI 的域内测试文件必须现算为 0。"""
        other = _HARNESS_PY.parent / "test_aos_declared_table_binary.py"
        assert other.exists(), other
        calls = _call_attrs(other)
        assert calls.count("ASGITransport") == 0 and calls.count("AsyncClient") == 0, calls[:20]
        # 而该文件确实有大量别的调用 ⇒ 扫描器不是整体失灵
        assert len(calls) > 50, len(calls)

    def test_the_chain_is_reached_through_the_router_not_called_directly(self) -> None:
        """本两份判据文件都**不**直接调 `compute_adopt_substrate`（只经 HTTP 抵达）。"""
        for path in (_HARNESS_PY, _WORLD_PY, Path(__file__).resolve()):
            calls = _call_attrs(path)
            assert "compute_adopt_substrate" not in calls, path.name
            assert "apply_overwrite_deletions" not in calls, path.name


# ═══════════════════════════════════════════════════════════════════════════════
# §4 Task 8.4 —— 原子性：merge 之后 / 统一 commit 之前注入失败 ⇒ 5xx 且库一字节未变
# ═══════════════════════════════════════════════════════════════════════════════

_INJECTED = (
    ("inject_after_business_write", 1),
    ("inject_after_deletion_side", 2),
    ("inject_before_audit", 2),
)


class TestAtomicityUnderInjection:
    """**Validates: Requirements 6.7, 6.8**"""

    @pytest.mark.parametrize("name,expected_writes", _INJECTED)
    def test_injection_yields_5xx(
        self, snap: dict[str, Any], name: str, expected_writes: int
    ) -> None:
        obs = snap["scenarios"][name]
        assert obs["raised"] is None, obs["raised"]
        assert obs["status"] is not None and 500 <= obs["status"] < 600, obs["status"]

    @pytest.mark.parametrize("name,expected_writes", _INJECTED)
    def test_injection_point_is_after_merge_and_before_commit(
        self, snap: dict[str, Any], name: str, expected_writes: int
    ) -> None:
        """注入点由**真实发生过的写**定位：写次数 ≥1（merge 已发生）且 `commits == 0`。"""
        obs = snap["scenarios"][name]
        assert obs["store_writes"] == expected_writes, obs["store_writes"]
        assert obs["store_writes"] >= 1, "一次写都没发生 ⇒ 注入点其实在 merge 之前"
        assert obs["commits"] == 0, "已经 commit 过了 ⇒ 注入点在统一 commit 之后"
        assert obs["rollbacks"] == 1, obs["rollbacks"]

    @pytest.mark.parametrize("name,expected_writes", _INJECTED)
    def test_database_is_byte_identical_after_injection(
        self, snap: dict[str, Any], name: str, expected_writes: int
    ) -> None:
        """逐行逐列比（含 `id` / `content_version` / `created_at` / `updated_at`）+ 审计零新增。"""
        obs = snap["scenarios"][name]
        assert obs["store_before"] == obs["store_after"], (
            f"{name}: 库变了 —— before={obs['store_before']} after={obs['store_after']}"
        )
        assert obs["audit_before"] == obs["audit_after"], "审计链多/少了条目"
        assert identities_in_store(obs["store_after"]) == (KEEP_ID, DROP_ID)
        assert len(obs["store_before"]) == 1, "分母为 0 ⇒「未变」在空集上恒真"

    def test_positive_control_really_wrote(self, snap: dict[str, Any]) -> None:
        """🔴 不注入时**确实**落库了 —— 否则上面三条「库未变」在空操作上恒真。"""
        obs = snap["scenarios"]["atomicity_positive_control"]
        assert obs["status"] == 200, obs["body"]
        assert obs["store_before"] != obs["store_after"], (
            "不注入时库也没变 ⇒ 三条「库未变」判据是在空操作上恒真"
        )
        assert identities_in_store(obs["store_before"]) == (KEEP_ID, DROP_ID)
        assert identities_in_store(obs["store_after"]) == (KEEP_ID, ADD_ID)
        assert obs["commits"] == 1 and obs["rollbacks"] == 0
        assert len(obs["audit_after"]) == len(obs["audit_before"]) + 1, (
            "业务写成功但审计没留痕 ⇒ 三者同事务这条不成立"
        )


class TestMultiItemPartialWriteIsRolledBack:
    """多 item 场景（上游实测过的「部分写入」事故形态）。

    **Validates: Requirements 6.7, 6.8**

    🔴 载体换成 5 个 store item 的 `f3.notes_payable_detail`：删除侧**逐 item 各发一条**
    UPDATE ⇒ 注入点落在中途时，后面几个 item 的删除还没发生 = 真正的跨 item 部分写入。
    `f4`（§1~§4 前半用的那个）在 `store_mirror` 的单 item 分支下只写 1 个 item，构不出这形态。
    """

    def test_all_five_items_were_seeded(self, snap: dict[str, Any]) -> None:
        obs = snap["scenarios"]["multi_item_positive_control"]
        assert len(obs["seeded_items"]) == 5, obs["seeded_items"]
        assert len(obs["store_before"]) == 5
        for row in obs["store_before"]:
            assert identities_of(row["remark"]) == (KEEP_ID, DROP_ID), row["item_id"]

    def test_positive_control_pruned_every_item(self, snap: dict[str, Any]) -> None:
        obs = snap["scenarios"]["multi_item_positive_control"]
        assert obs["status"] == 200, obs["body"]
        body = unwrap(obs["body"])
        assert body["changed_item_count"] == 5, body
        assert len(obs["store_after"]) == 5, [r["item_id"] for r in obs["store_after"]]
        for row in obs["store_after"]:
            ids = identities_of(row["remark"])
            assert DROP_ID not in ids and KEEP_ID in ids, (row["item_id"], ids)
        assert obs["store_writes"] >= 5, (
            f"跨 item 的写少于 5 条 ⇒ 部分写入形态构不出来：{obs['store_writes']}"
        )
        assert obs["commits"] == 1 and obs["rollbacks"] == 0

    def test_mid_deletion_injection_rolls_back_every_item(self, snap: dict[str, Any]) -> None:
        obs = snap["scenarios"]["multi_item_inject_mid_deletion"]
        assert obs["status"] is not None and 500 <= obs["status"] < 600, obs["status"]
        positive = snap["scenarios"]["multi_item_positive_control"]
        assert 1 <= obs["store_writes"] < positive["store_writes"], (
            "注入点不在「中途」：写次数要么为 0（merge 前）要么与不注入时相同（写完了）"
            f"—— 注入 {obs['store_writes']} vs 不注入 {positive['store_writes']}"
        )
        assert obs["commits"] == 0 and obs["rollbacks"] == 1
        assert obs["store_before"] == obs["store_after"], "跨 item 的部分写入没被回滚干净"
        assert obs["audit_before"] == obs["audit_after"]
        for row in obs["store_after"]:
            assert identities_of(row["remark"]) == (KEEP_ID, DROP_ID), row["item_id"]

    def test_registered_why_the_added_row_lands_nowhere_here(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 **现状登记（两个成因，都已探针实证，都不在本 spec 修复面）**：

        ① **4 / 5 个 item 的追加方向恒空** —— `f3` 声明 5 个 store item，而
        `store_mirror` 单 item 分支只镜像 `bridge.STORE_ITEM_ID` 那 1 个（`dual_store_fn` 为空）。
        形态与注册表注释里记的 D4-35 / D1 同族（域外，属 `store_item_registry` 的接线面）。
        ② **被镜像的那 1 个 item 也没长出新增行** —— 是 **harness 数据**造成的：`F3-5-rows` 的幽灵行
        锚点字段是 `note_type`，把本 harness 的中文业务名喂进去后经值类型归一变成 `null`
        （真库实测 remark 为 `[{"rowId": "...", "noteType": null}]`）⇒ 新增行业务名为空 ⇒
        被幽灵行门正确剔除。这不是缺陷，是「该字段不吃自由文本」。

        本条把两件事都钉住：哪天追加方向开始覆盖多 item，或归一口径变了，它会打红并逼迫复读。
        """
        obs = snap["scenarios"]["multi_item_positive_control"]
        with_add = [
            row["item_id"] for row in obs["store_after"] if ADD_ID in identities_of(row["remark"])
        ]
        assert with_add == [], (
            "追加方向开始覆盖多 item 了（或幽灵行门 / 值归一口径变了）—— 请复读本条 docstring "
            f"的两条登记并重裁：{with_add}"
        )
        # 成因 ② 的直接证据：被镜像的那个 item 的锚点字段在库里就是 null
        mirrored = [row for row in obs["store_after"] if row["item_id"].endswith("F3-5-rows")]
        assert mirrored, [row["item_id"] for row in obs["store_after"]]
        assert '"noteType": null' in (mirrored[0]["remark"] or ""), mirrored[0]["remark"]


# ═══════════════════════════════════════════════════════════════════════════════
# §5 Task 8.5 —— 真库对账：dry_run 的三清单 == 真实执行后实际落库的三清单
#
# 🔴 口径已裁定（tasks.md 4.2 / Requirement 3.8）：追加侧按
#    **`rows_added − rows_ghost_dropped`** 对账 —— 裸 `rows_added` 含被幽灵行门剔除的身份，
#    拿它比会假红。
# ═══════════════════════════════════════════════════════════════════════════════


def _single_delta(snap: dict[str, Any]) -> dict[str, Any]:
    wire = snap["scenarios"]["reconcile"]["plan_wire"]
    deltas = wire["deltas"]
    assert len(deltas) == 1, [d["item_id"] for d in deltas]
    return deltas[0]


class TestDryRunReconcilesWithWhatLanded:
    """**Validates: Requirements 3.8**"""

    def test_the_two_requests_saw_the_same_store_version(self, snap: dict[str, Any]) -> None:
        """同一 substrate 与同一 store 版本：dry_run 不写库，所以两趟看到的是同一份。"""
        obs = snap["scenarios"]["reconcile"]
        assert obs["dry_status"] == 200 and obs["real_status"] == 200, obs["real_body"]
        assert identities_in_store(obs["store_before"]) == (KEEP_ID, DROP_ID)
        assert obs["plan_wire"]["store_row_count"] == 2, obs["plan_wire"]

    def test_the_three_lists_are_non_empty(self, snap: dict[str, Any]) -> None:
        """反空转：三清单全空时下面的逐元素相等在空集上恒真。"""
        delta = _single_delta(snap)
        assert delta["rows_added"] and delta["rows_deleted"] and delta["rows_updated"], delta
        assert delta["rows_ghost_dropped"] == [], (
            "本场景不该有幽灵行（业务名都填了）—— 若非空，说明载荷或锚点口径变了"
        )

    def test_added_minus_ghost_landed(self, snap: dict[str, Any]) -> None:
        obs = snap["scenarios"]["reconcile"]
        delta = _single_delta(snap)
        effective_added = tuple(
            i for i in delta["rows_added"] if i not in set(delta["rows_ghost_dropped"])
        )
        before = set(identities_in_store(obs["store_before"]))
        after = identities_in_store(obs["store_after"])
        assert effective_added == (ADD_ID,), effective_added
        for identity in effective_added:
            assert identity not in before, identity
            assert identity in after, identity

    def test_deleted_really_left(self, snap: dict[str, Any]) -> None:
        obs = snap["scenarios"]["reconcile"]
        delta = _single_delta(snap)
        before = set(identities_in_store(obs["store_before"]))
        after = set(identities_in_store(obs["store_after"]))
        assert tuple(delta["rows_deleted"]) == (DROP_ID,), delta["rows_deleted"]
        for identity in delta["rows_deleted"]:
            assert identity in before and identity not in after, identity

    def test_updated_stayed(self, snap: dict[str, Any]) -> None:
        obs = snap["scenarios"]["reconcile"]
        delta = _single_delta(snap)
        before = set(identities_in_store(obs["store_before"]))
        after = set(identities_in_store(obs["store_after"]))
        assert tuple(delta["rows_updated"]) == (KEEP_ID,), delta["rows_updated"]
        for identity in delta["rows_updated"]:
            assert identity in before and identity in after, identity

    def test_the_final_row_set_equals_the_plan_element_wise(self, snap: dict[str, Any]) -> None:
        """整体等式：落库身份序列 == （覆盖前 − 删除）∪（追加 − 幽灵），**逐元素**比。"""
        obs = snap["scenarios"]["reconcile"]
        delta = _single_delta(snap)
        deleted = set(delta["rows_deleted"])
        ghost = set(delta["rows_ghost_dropped"])
        expected = [i for i in identities_in_store(obs["store_before"]) if i not in deleted]
        expected += [i for i in delta["rows_added"] if i not in ghost]
        assert list(identities_in_store(obs["store_after"])) == expected, (
            f"落库 {identities_in_store(obs['store_after'])} ≠ 计划推出的 {expected}"
        )

    def test_changed_items_comes_from_the_same_plan(self, snap: dict[str, Any]) -> None:
        obs = snap["scenarios"]["reconcile"]
        body = unwrap(obs["real_body"])
        delta = _single_delta(snap)
        assert body["changed_items"] == [delta["item_id"]], (body, delta["item_id"])
        assert body["changed_item_count"] == 1


class TestDigestGoesStaleWhenTheStoreMoves:
    """tasks.md 8.2 逐字那一种过期：**改动 store** 使 digest 过期，再带旧 digest 执行。

    **Validates: Requirements 3.4**

    与 `TestPlanDigestGateOverRealHttp`（直接送一个错 digest）互补：那组证「门在」，
    本组证「门为什么存在」—— 服务端重算值是被**真实数据变化**推动的。
    """

    def test_the_store_really_moved_between_the_two_calls(self, snap: dict[str, Any]) -> None:
        obs = snap["scenarios"]["digest_stale_by_store_change"]
        assert identities_in_store(obs["store_after_drift"]) == (KEEP_ID, DROP_ID, "aos8-late"), (
            "第三方改动没生效 ⇒ 下面的「过期」其实不是过期"
        )

    def test_the_recomputed_digest_differs(self, snap: dict[str, Any]) -> None:
        obs = snap["scenarios"]["digest_stale_by_store_change"]
        assert len(obs["old_digest"]) == 64 and len(obs["new_digest"]) == 64
        assert obs["old_digest"] != obs["new_digest"], (
            "store 多了一行而计划摘要没变 ⇒ digest 对 store 侧行集不敏感（这才是真缺陷）"
        )

    def test_the_old_digest_is_refused_with_409(self, snap: dict[str, Any]) -> None:
        obs = snap["scenarios"]["digest_stale_by_store_change"]
        assert obs["refused_status"] == 409, obs["refused_body"]
        assert error_code(obs["refused_body"]) == "adopt_plan_digest_mismatch", obs["refused_body"]
        assert obs["store_after_drift"] == obs["store_after_refused"], "被拒的那次动过库"

    def test_the_freshly_taken_digest_is_accepted(self, snap: dict[str, Any]) -> None:
        """正向对照：重取一次摘要后带新 digest ⇒ 200 且真覆盖（`aos8-late` 被删掉）。"""
        obs = snap["scenarios"]["digest_stale_by_store_change"]
        assert obs["accepted_status"] == 200, obs["accepted_body"]
        after = identities_in_store(obs["store_after_accepted"])
        assert after == (KEEP_ID, ADD_ID), after
        assert "aos8-late" not in after
