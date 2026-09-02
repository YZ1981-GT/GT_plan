# -*- coding: utf-8 -*-
"""Task 29 离线守卫：append-only timeline、required scenario 推导、脱敏与告警。
spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 29
Requirements: 5.10, 5.11, 10.7, 12.10, 12.11, 12.12, 13.1, 13.2, 13.4, 13.5, 13.6,
              13.7, 13.8, 13.9, 13.10, 14.16
Properties: **P52 / P53 / P54 / P68 / P69 / P70 / P71**

═══ 本文件与 `_pg.py` 的分工 ═══

* 本文件 —— **纯行为**与**形态**判据：`RedactionPolicy` 的三层过滤与反向泄露、
  `AlertRuleRegistry` 与指标目录/Requirement 13.9 的三向双向锁、required scenario set
  推导（跑真实 186 条 manifest）、`check_projection` 的四条独立缺陷码、以及 router
  接线的 AST 形态。不连库。
* `test_task29_timeline_evidence_pg.py` —— 真库：event 表真的 append-only、current
  state 真的只是投影、recovery case claim 前真的零 operation、evidence recomputer 对
  真实行的逐项重算与 stale。

═══ 为什么这里的判据大量落在「值形态」而不是「函数被调用过」═══

Requirement 13.8 要禁的是**泄露**，而泄露是一个关于**输出字节**的性质。「`redact()`
被调用了」证明不了输出干净：allowlist 少一条、值形态规则拼错一个字符、URL 只去了
query 没去 userinfo —— 三种情况下调用都发生了。所以反向泄露测试给的是**合成事件**
（带真 JWS 形状、真 URL、真嵌套业务值），断言的是**输出里找不到**它们。

同理，「allowlist 两侧锁死」不是断言 `len(allowlist) == 150`（那是自证重言式：
把常量和判据写成同一个数），而是用**独立分母**：V151 四张 event 表的真实列名。
少登记一列 ⇒ 该列的值会被丢弃而没人知道；多登记一个不存在的键 ⇒ 名单腐化。
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_SYNC = _BACKEND / "app" / "services" / "workpaper_sync"
_REDACTION_PY = _SYNC / "redaction.py"
_METRICS_PY = _SYNC / "metrics.py"
_ALERTING_PY = _SYNC / "alerting.py"
_TIMELINE_PY = _SYNC / "timeline.py"
_EVIDENCE_PY = _SYNC / "evidence.py"
_ROUTER_PY = _BACKEND / "app" / "routers" / "wp_sync_router.py"

import app.routers.wp_sync_router as SR  # noqa: E402
import app.services.workpaper_sync.alerting as AL  # noqa: E402
import app.services.workpaper_sync.evidence as EV  # noqa: E402
import app.services.workpaper_sync.metrics as MX  # noqa: E402
import app.services.workpaper_sync.redaction as RD  # noqa: E402
import app.services.workpaper_sync.timeline as TL  # noqa: E402
from app.models.workpaper_sync_models import (  # noqa: E402
    WorkpaperCallbackRecoveryCaseEvent,
    WorkpaperContentApplicationEvent,
    WorkpaperOoCloseIntentEvent,
    WorkpaperSyncOperationEvent,
)
from app.services.workpaper_sync.entry_profile import (  # noqa: E402
    Capability,
    Editability,
    EntryProfile,
    EntryProfileError,
    RoomModel,
    ScenarioProfile,
    capability_of,
    extract_entry_profile,
    load_entry_manifest,
)
from app.services.workpaper_sync.models import AuthorityModel  # noqa: E402


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _func(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"找不到函数 {name!r}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


#: 真 JWS compact 形状（三段 base64url）。**不是**真凭证，但形状与 OO 发的一致。
_JWS = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhdWRpdG9yIn0.c2lnbmF0dXJlXzEyMzQ1"


# ═══════════════════════════════════════════════════════════════════════════
# 1. RedactionPolicy —— 三层过滤 + 反向泄露（Requirement 13.8 / 10.7）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def policy() -> RD.RedactionPolicy:
    return RD.load_redaction_policy()


class TestRedactionReverseLeak:
    """反向泄露：合成事件带凭证/URL/嵌套业务值，输出里必须找不到。"""

    def _leaky_event(self) -> dict[str, Any]:
        """一条**刻意脏**的 event detail：五类泄露各占一条。"""
        return {
            "operation_id": str(uuid.uuid4()),
            "from_state": "durable",
            "to_state": "applying",
            # ① 敏感键名
            "Authorization": f"Bearer {_JWS}",
            "X-Callback-Token": _JWS,
            # ② 键名合法但值是 URL（带 userinfo + query 凭证）
            "error_detail": (
                f"download failed: https://auditor:pw@docserver.internal:8080/cache/"
                f"files/data.xlsx?token={_JWS}#frag"
            ),
            # ③ 未登记键（业务值本体）
            "incoming_cell_values": {"D2!C7": 1234567.89, "D2!C8": -98765.43},
            "merged_projection": [{"stable_field_key": "ar_balance", "value": 8888.88}],
            # ④ **allowlist 内**键携带的嵌套结构里的敏感键。
            #    刻意挂在 `detail`（在 `scrubbed_keys` 里，故会被递归下降）而不是随便一个
            #    未登记键：挂在未登记键上时整棵子树在第一层就被丢掉，递归下降那段代码
            #    根本不会执行 —— 那样这条判据测的是「丢弃」而不是「嵌套投影」，
            #    对应的变异会永久 GREEN。
            "detail": {"jwt": _JWS, "stage": "extract", "session_key": "abcdef123456"},
            # ⑤ 长不透明串
            "payload_blob": "A" * 200,
        }

    def test_no_credential_shape_survives_projection(
        self, policy: RD.RedactionPolicy
    ) -> None:
        projected, report = policy.redact(self._leaky_event())
        blob = json.dumps(projected, ensure_ascii=False)
        assert _JWS not in blob, f"JWS 原文残留: {blob[:400]}"
        assert "Bearer " not in blob
        assert "auditor:pw@" not in blob, "URL userinfo 残留"
        assert "docserver.internal" not in blob, "未登记 host 残留"
        assert "token=" not in blob, "URL query 残留"
        assert "1234567.89" not in blob, "业务金额残留 —— allowlist 不是白名单了"
        assert "ar_balance" not in blob, "业务字段键残留"
        assert "A" * 100 not in blob, "长不透明串残留"
        # 报告必须如实说出发生了什么（否则「什么都没漏」与「什么都没查」不可区分）。
        assert "Authorization" in report.secret_keys
        assert "incoming_cell_values" in report.dropped_keys
        assert "jwt" in report.secret_keys, "嵌套里的敏感键未被识别"

    def test_self_check_accepts_its_own_output(self, policy: RD.RedactionPolicy) -> None:
        """`assert_no_leak` 必须接受本策略自己的输出（否则它恒抛，判据无意义）。"""
        projected, _ = policy.redact(self._leaky_event())
        policy.assert_no_leak(projected)

    @pytest.mark.parametrize(
        "leaky",
        [
            {"error_detail": f"see {_JWS}"},
            {"error_detail": "see https://evil.example.com/a"},
            {"error_detail": "see https://localhost/a?token=x"},
            {"error_detail": "see https://u:p@localhost/a"},
            {"error_detail": "see https://localhost/a#f"},
            {"Authorization": "Bearer plaintext-token-value"},
        ],
        ids=[
            "raw-jws",
            "unlisted-host",
            "url-query",
            "url-userinfo",
            "url-fragment",
            "secret-key-not-placeholder",
        ],
    )
    def test_self_check_rejects_each_leak_form(
        self, policy: RD.RedactionPolicy, leaky: dict[str, Any]
    ) -> None:
        """六种泄露形态各自被 `assert_no_leak` 抓住。

        逐条参数化而不是一条大用例：共用一条会让「五种里只抓住一种」照样绿。
        """
        with pytest.raises(RD.RedactionUsageError):
            policy.assert_no_leak(leaky)

    def test_exception_text_is_scrubbed_and_truncated(
        self, policy: RD.RedactionPolicy
    ) -> None:
        # 尾巴刻意用**带空格的短词**而不是 `"z" * 4000`：后者会先被 `long_opaque_blob`
        # 整段替换成占位符，结果反而变短 ⇒ 截断分支不会执行，这条判据就测不到截断。
        exc = RuntimeError(f"boom https://h.invalid/x?jwt={_JWS} " + "tail " * 800)
        text = policy.redact_exception(exc)
        assert text.startswith("RuntimeError: "), "异常类型是最稳定的分型，必须保留"
        assert _JWS not in text
        assert len(text) <= policy.limits.max_exception_chars + len(
            policy.truncated_placeholder
        )
        assert text.endswith(policy.truncated_placeholder)

    def test_bytes_never_reach_the_record(self, policy: RD.RedactionPolicy) -> None:
        """allowlist 内的键拿到 bytes 时只留长度（asyncpg 的 bytea 会给 memoryview）。"""
        projected, report = policy.redact({"detail_digest": memoryview(b"\x50\x4b\x03\x04")})
        assert projected["detail_digest"] == f"{policy.secret_placeholder}(4B)"
        assert "detail_digest" in report.secret_keys

    def test_depth_and_container_limits_bound_the_record(
        self, policy: RD.RedactionPolicy
    ) -> None:
        # 同上：嵌套必须挂在 allowlist 内的键（`detail`）上，否则第一层就被丢掉，
        # 深度门根本不会被触达。
        deep: dict[str, Any] = {"stage": "x"}
        for _ in range(policy.limits.max_depth + 4):
            deep = {"detail": deep, "stage": "y"}
        projected, report = policy.redact(deep)
        assert report.depth_exceeded, "超深嵌套没有被截断 —— 一条 event 能写进整份载荷"
        wide = {"stale_reasons": ["r"] * (policy.limits.max_container_items + 10)}
        _, wide_report = policy.redact(wide)
        assert "stale_reasons" in wide_report.truncated_keys


class TestRedactionAllowlistIsTwoWayLocked:
    """allowlist 与**独立分母**双向等值。加宽与清空都必须打红。"""

    #: 独立分母 = V151 四张 append-only event 表的真实列名。
    #:
    #: 🔴 刻意**不**从 `RedactionPolicy.allowlist` 推导：拿被验对象当分母就是自证重言式
    #: （本 spec 的假绿第三种形态）。这四张表是 timeline 的本体，它们的每一列要么在
    #: allowlist 里、要么在下面的排除表里带理由。
    EVENT_MODELS = (
        WorkpaperSyncOperationEvent,
        WorkpaperContentApplicationEvent,
        WorkpaperCallbackRecoveryCaseEvent,
        WorkpaperOoCloseIntentEvent,
    )

    #: 不进 allowlist 的列 + 理由。空理由不接受。
    EXCLUDED_COLUMNS = {
        "id": "bigint 代理键；业务身份是 (stream, parent_id, sequence_no)，投影时剔除",
    }

    def _event_columns(self) -> set[str]:
        names: set[str] = set()
        for model in self.EVENT_MODELS:
            names |= {column.name for column in model.__table__.columns}
        return names

    def test_every_event_column_is_either_allowlisted_or_excluded_with_a_reason(
        self, policy: RD.RedactionPolicy
    ) -> None:
        columns = self._event_columns()
        assert len(columns) >= 20, f"分母太小，四张表只解析出 {len(columns)} 列"
        unaccounted = sorted(
            name
            for name in columns
            if name not in policy.allowlist
            and name not in policy.scrubbed_keys
            and name not in self.EXCLUDED_COLUMNS
            and not policy.is_secret_key(name)
        )
        assert not unaccounted, (
            f"event 列 {unaccounted} 既不在 allowlist 也没登记排除理由 —— "
            "它们的值会被静默丢弃，timeline 少一段而无人知晓"
        )
        for name, reason in self.EXCLUDED_COLUMNS.items():
            assert name in columns, f"排除表里的 {name} 不是真实列 —— 名单腐化"
            assert len(reason) >= 8, f"{name} 的排除理由过短"

    def test_no_allowlisted_key_is_a_credential_name(
        self, policy: RD.RedactionPolicy
    ) -> None:
        """加宽方向：把凭证键登记进 allowlist 必须在**构造期**就被拒。"""
        config = dict(RD.load_redaction_config())
        allowlist = {k: dict(v) for k, v in config["allowlist"].items()}
        allowlist["identity"] = dict(allowlist["identity"])
        allowlist["identity"]["keys"] = list(allowlist["identity"]["keys"]) + [
            "authorization_header"
        ]
        config["allowlist"] = allowlist
        with pytest.raises(RD.RedactionConfigError, match="敏感键名"):
            RD.RedactionPolicy(config)

    def test_emptying_a_group_is_refused(self) -> None:
        """清空方向：把任一 allowlist 分组清空必须被拒（空组 = 悄悄放弃该组判据）。"""
        for group in RD.ALLOWLIST_GROUPS:
            config = dict(RD.load_redaction_config())
            allowlist = {k: dict(v) for k, v in config["allowlist"].items()}
            allowlist[group] = dict(allowlist[group])
            allowlist[group]["keys"] = []
            config["allowlist"] = allowlist
            with pytest.raises(RD.RedactionConfigError, match="非空数组"):
                RD.RedactionPolicy(config)

    def test_dropping_a_group_entirely_is_refused(self) -> None:
        for group in RD.ALLOWLIST_GROUPS:
            config = dict(RD.load_redaction_config())
            allowlist = {k: v for k, v in config["allowlist"].items() if k != group}
            config["allowlist"] = allowlist
            with pytest.raises(RD.RedactionConfigError, match="缺分组"):
                RD.RedactionPolicy(config)

    def test_role_suffix_list_is_closed_both_ways(
        self, policy: RD.RedactionPolicy
    ) -> None:
        """末段角色词名单：`authorization_result` 必须放行，`authorization_header` 必须屏蔽。

        这两条是同一条规则的正反两面。把 `header` 加进角色词名单 ⇒ 第二条断言红；
        把名单清空 ⇒ 构造期即拒（见 `test_emptying_role_suffixes_is_refused`）。

        ── 为什么还要锁「末段」而不只是「命中角色词」──

        角色词豁免**只**锚定 `segments[-1]`。改成「任一段命中就放行」时，
        `digest_token` / `state_authorization` / `sha256_secret` 三个键会因为**首段**
        是角色词而被判非凭证 —— 那是三条真实的长期凭证落库路径。原先本测试只有放行
        侧（`token_digest`）的断言，屏蔽侧一条都没有，于是这条不变量实际无守卫：针对
        它的变异会恒 GREEN。下面两组断言是同一条规则的正反面，缺任一侧都不算锁死。
        """
        assert policy.is_secret_key("Authorization") is True
        assert policy.is_secret_key("authorization_header") is True
        assert policy.is_secret_key("x-callback-token") is True
        assert policy.is_secret_key("authorization_result") is False, (
            "`authorization_result` 是 V151 的枚举结果列（allowed/denied/stale），"
            "AC 13.5 要求它可查询 —— 按裸子串屏蔽等于删掉一条 AC"
        )
        assert policy.is_secret_key("token_digest") is False, (
            "凭证的 SHA-256 不是凭证"
        )
        assert policy.is_secret_key("stale") is False

        # 末段锚定的屏蔽侧：首段是角色词但末段是凭证词 ⇒ 仍必须屏蔽。
        for key in ("digest_token", "state_authorization", "sha256_secret"):
            assert policy.is_secret_key(key) is True, (
                f"{key!r} 的末段是凭证词 ⇒ 必须屏蔽。若角色词豁免退化成「任一段命中」，"
                f"首段 {policy._segments(key)[0]!r} 会让长期凭证原样落库"
            )

    def test_emptying_role_suffixes_is_refused(self) -> None:
        config = dict(RD.load_redaction_config())
        group = dict(config["secret_key_patterns"])
        group["non_credential_role_suffixes"] = []
        config["secret_key_patterns"] = group
        with pytest.raises(RD.RedactionConfigError, match="non_credential_role_suffixes"):
            RD.RedactionPolicy(config)

    def test_role_suffix_may_not_overlap_a_credential_word(self) -> None:
        config = dict(RD.load_redaction_config())
        group = dict(config["secret_key_patterns"])
        group["non_credential_role_suffixes"] = list(
            group["non_credential_role_suffixes"]
        ) + ["token"]
        config["secret_key_patterns"] = group
        with pytest.raises(RD.RedactionConfigError, match="重叠"):
            RD.RedactionPolicy(config)

    def test_missing_policy_file_fails_closed(self, tmp_path: Path) -> None:
        """读不到策略时**不得** fallback 到内置默认值。"""
        with pytest.raises(RD.RedactionConfigError):
            RD.load_redaction_config(tmp_path / "nope.json")

    def test_zero_limits_are_refused(self) -> None:
        for field in (
            "max_depth",
            "max_container_items",
            "max_string_chars",
            "max_exception_chars",
        ):
            config = dict(RD.load_redaction_config())
            limits = dict(config["limits"])
            limits[field] = 0
            config["limits"] = limits
            with pytest.raises(RD.RedactionConfigError, match="必须为正数"):
                RD.RedactionPolicy(config)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 指标目录 —— 归因、封闭结果域、禁止压平（Requirement 13.7 / 5.1 / 10.9）
# ═══════════════════════════════════════════════════════════════════════════


class TestMetricCatalog:
    def test_catalog_self_check_is_clean(self) -> None:
        assert MX.validate_catalog() == ()

    def test_operation_scoped_metrics_require_all_six_dims(self) -> None:
        """`operation_scoped` 缺任一核心维度即拒 —— 逐维参数化。"""
        metrics = MX.SyncMetrics()
        full = {
            "room_id": uuid.uuid4(),
            "generation": 3,
            "requested_operation_id": uuid.uuid4(),
            "canonical_operation_id": uuid.uuid4(),
            "application_id": uuid.uuid4(),
            "participant_id": uuid.uuid4(),
        }
        metrics.record_outcome(
            "workpaper_sync_application_bind_total",
            result="primary_bound",
            landed=True,
            **full,
        )
        for dropped in sorted(full):
            partial = {k: v for k, v in full.items() if k != dropped}
            with pytest.raises(MX.MetricAttributionError, match="缺归因维度"):
                metrics.record_outcome(
                    "workpaper_sync_application_bind_total",
                    result="primary_bound",
                    landed=True,
                    **partial,
                )

    def test_route_scoped_metrics_forbid_participant(self) -> None:
        """AC 5.1 / 10.9：聚合 callback 事件不得带 participant 归因。"""
        metrics = MX.SyncMetrics()
        room, generation = uuid.uuid4(), 4
        metrics.record_outcome(
            "workpaper_sync_incoming_durable_total",
            result="durable",
            landed=True,
            room_id=room,
            generation=generation,
        )
        with pytest.raises(MX.MetricAttributionError, match="不得带维度"):
            metrics.record_outcome(
                "workpaper_sync_incoming_durable_total",
                result="durable",
                landed=True,
                room_id=room,
                generation=generation,
                participant_id=uuid.uuid4(),
            )

    def test_the_route_scoped_class_covers_the_callback_origin_metrics(self) -> None:
        """哪些指标必须是 route 级：**独立**推导，不读目录里的 attribution 字段。

        分母 = 「由 callback / 未归组 / 未 claim 路径 emit」的指标。这三条各有独立理由：
        callback 是聚合事件（AC 5.1）、建 recovery case 时恰恰归不出发起人、
        download-only 的 case 从未被 claim。
        """
        expected_route = {
            "workpaper_sync_incoming_durable_total",
            "workpaper_sync_recovery_case_total",
            "workpaper_sync_unmatched_status2_total",
            "workpaper_sync_recovery_download_only_total",
        }
        actual_route = {
            d.name
            for d in MX.METRIC_CATALOG
            if d.attribution is MX.AttributionClass.route_scoped
        }
        assert actual_route == expected_route, (
            f"route 级名单漂移：多 {sorted(actual_route - expected_route)}，"
            f"少 {sorted(expected_route - actual_route)}"
        )

    @pytest.mark.parametrize(
        "outcome",
        sorted(MX.FORBIDDEN_GENERIC_ERROR_OUTCOMES),
        ids=sorted(MX.FORBIDDEN_GENERIC_ERROR_OUTCOMES),
    )
    def test_each_forbidden_outcome_refuses_the_generic_error_metric(
        self, outcome: str
    ) -> None:
        metrics = MX.SyncMetrics()
        with pytest.raises(MX.MetricAttributionError) as caught:
            metrics.record_error(
                outcome=outcome,
                landed=True,
                result="unknown",
                room_id=uuid.uuid4(),
                generation=1,
                requested_operation_id=uuid.uuid4(),
                canonical_operation_id=uuid.uuid4(),
                application_id=uuid.uuid4(),
                participant_id=uuid.uuid4(),
            )
        # 异常必须**指出**该用哪个专用指标，否则调用方只能猜。
        assert MX.FORBIDDEN_GENERIC_ERROR_OUTCOMES[outcome] in str(caught.value)

    def test_a_non_forbidden_outcome_still_reaches_the_generic_error_metric(self) -> None:
        """对照侧：禁令不是「record_error 恒抛」。"""
        metrics = MX.SyncMetrics()
        sample = metrics.record_error(
            outcome="download_timeout",
            landed=False,
            result="pre_durable",
            room_id=uuid.uuid4(),
            generation=1,
            requested_operation_id=uuid.uuid4(),
            canonical_operation_id=uuid.uuid4(),
            application_id=uuid.uuid4(),
            participant_id=uuid.uuid4(),
        )
        assert sample.metric == "workpaper_sync_error_total"

    def test_the_three_task29_named_outcomes_are_in_the_forbidden_map(self) -> None:
        """Task 29 正文点名的三条必须在禁令表里（独立分母，不读实现）。"""
        for named in (
            "same_application_sequence_fold",
            "cross_participant_idempotency_conflict",
            "close_leader_no_successor_recovery_required",
        ):
            assert named in MX.FORBIDDEN_GENERIC_ERROR_OUTCOMES, (
                f"Task 29 明文禁止把 {named} 压成普通 error，禁令表里却没有它"
            )

    def test_result_is_mandatory_when_the_metric_has_a_closed_domain(self) -> None:
        metrics = MX.SyncMetrics()
        labels = {"room_id": uuid.uuid4(), "generation": 1, "participant_id": uuid.uuid4()}
        with pytest.raises(MX.MetricAttributionError, match="result 不得为空"):
            metrics.record_outcome(
                "workpaper_sync_forcesave_accepted_total",
                result=None,
                landed=False,
                **labels,
            )
        with pytest.raises(MX.MetricAttributionError, match="封闭域"):
            metrics.record_outcome(
                "workpaper_sync_forcesave_accepted_total",
                result="ok",
                landed=False,
                **labels,
            )

    def test_record_outcome_has_no_default_for_result_or_landed(self) -> None:
        """签名判据：`result` / `landed` 不得有默认值。

        有默认值 ⇒ 调用方可以省略 ⇒ 又回到「没抛异常就算成功」。这条走 `inspect`
        而不是 AST：它要证明的是**运行时签名**，而装饰器/重导出都可能让源码形态骗人。
        """
        signature = inspect.signature(MX.SyncMetrics.record_outcome)
        for name in ("result", "landed"):
            parameter = signature.parameters[name]
            assert parameter.default is inspect.Parameter.empty, (
                f"record_outcome 的 {name} 有默认值 {parameter.default!r} —— "
                "调用方就能省略它，失败会被记成成功"
            )
            assert parameter.kind is inspect.Parameter.KEYWORD_ONLY

    def test_unknown_metric_name_is_refused(self) -> None:
        metrics = MX.SyncMetrics()
        with pytest.raises(MX.UnknownMetricError):
            metrics.record_outcome("not_a_metric", result=None, landed=True)

    def test_unknown_label_name_is_refused(self) -> None:
        metrics = MX.SyncMetrics()
        with pytest.raises(MX.MetricAttributionError, match="未登记的维度"):
            metrics.record_outcome(
                "workpaper_sync_incoming_durable_total",
                result="durable",
                landed=True,
                room_id=uuid.uuid4(),
                generation=1,
                room="typo",
            )

    def test_sample_buffer_is_bounded(self) -> None:
        metrics = MX.SyncMetrics(buffer_size=8)
        for _ in range(40):
            metrics.record_outcome(
                "workpaper_sync_incoming_durable_total",
                result="durable",
                landed=True,
                room_id=uuid.uuid4(),
                generation=1,
            )
        assert len(metrics.samples) == 8, "样本缓冲无界 ⇒ 长跑进程会一直攒"


# ═══════════════════════════════════════════════════════════════════════════
# 3. AlertRuleRegistry —— 三向双向锁 + 合成事件（Requirement 13.9）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def registry() -> AL.AlertRuleRegistry:
    return AL.load_alert_registry()


def _registry_without_a_covered_condition() -> tuple[AL.AlertRuleRegistry, str, str]:
    """删掉一条「既属 13.9 点名、指标又 alert_required」的规则。

    返回 `(registry, 被摘掉的 metric, 被摘掉 condition 的 13.9 中文标签)`。

    ── 为什么必须用注入而不是「自检为空」──

    `validate_registry()` 的每一条分支在**合规数据上恒返回空**。因此
    `assert validate_registry(registry) == ()` 无论删掉哪条分支都仍然成立 —— 实测
    R31/R32 两条定向变异正是恒 GREEN。要证明某条分支真的在工作，只能构造一个它**应该**
    报错的输入，再断言它报出了**自己那条**消息。
    """
    labels_by_condition = {
        condition: label for label, condition in AL.REQUIREMENT_13_9_CONDITIONS.items()
    }
    config = dict(AL.load_alert_config())
    rules = [dict(r) for r in config["rules"]]
    victim = next(
        r
        for r in rules
        if MX.METRICS_BY_NAME[r["metric"]].alert_required
        and AL.AlertCondition(r["condition"]) in labels_by_condition
    )
    config["rules"] = [r for r in rules if r["rule_id"] != victim["rule_id"]]
    return (
        AL.AlertRuleRegistry(config),
        str(victim["metric"]),
        labels_by_condition[AL.AlertCondition(victim["condition"])],
    )


class TestAlertRegistry:
    def test_registry_self_check_is_clean(self, registry: AL.AlertRuleRegistry) -> None:
        assert AL.validate_registry(registry) == ()

    def test_an_alert_required_metric_without_a_rule_is_reported(self) -> None:
        """R31 分支的定向判据：摘掉规则后必须报出**这一条**消息。

        注意断言的是该分支**独有**的措辞 + 指标名。摘掉一条规则会同时触发三条分支
        （alert_required 未覆盖 / 13.9 标签缺失 / AlertCondition 缺失），若只断言
        `problems != ()`，删掉本分支仍会被另外两条满足而恒 GREEN —— 那正是「两条分支
        共用一个判据、靠后的把靠前的遮蔽掉」的形态。
        """
        broken, metric, _label = _registry_without_a_covered_condition()
        problems = AL.validate_registry(broken)
        hits = [
            p for p in problems if metric in p and "alert_required=True 但没有任何规则" in p
        ]
        assert len(hits) == 1, (
            f"应恰有一条针对 {metric} 的 alert_required 未覆盖告警，实得 {problems}"
        )

    def test_a_missing_requirement_13_9_condition_is_reported_by_its_label(self) -> None:
        """R32 分支的定向判据：报的必须是 **13.9 的中文标签**，不是 enum 名。

        `AlertCondition` 那条兜底分支报的是 `AlertCondition.X 没有规则`，与本分支的
        标签消息刻意不同措辞 —— 否则删掉 13.9 逐条核对后，兜底分支会替它「顶班」，
        使「13.9 是否被逐条覆盖」这条判据静默消失。
        """
        broken, _metric, label = _registry_without_a_covered_condition()
        problems = AL.validate_registry(broken)
        hits = [p for p in problems if f"「{label}」" in p]
        assert len(hits) == 1, (
            f"应恰有一条引用 13.9 标签「{label}」的缺口，实得 {problems}"
        )

    def test_a_rule_for_a_non_alert_required_metric_is_reported(
        self, registry: AL.AlertRuleRegistry, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """加宽方向：规则引用了 `alert_required=False` 的指标同样必须报。

        与上面两条合起来构成两侧锁死：少规则报、多规则也报。这里改的是**目录**一侧
        （把某个被规则引用的指标的 `alert_required` 翻成 False），因为改规则一侧会先被
        `_parse_rule` 的封闭域校验拦下，测不到 `validate_registry`。
        """
        target = registry.rules[0].metric
        original = MX.METRICS_BY_NAME[target]
        patched = dict(MX.METRICS_BY_NAME)
        patched[target] = dataclasses.replace(original, alert_required=False)
        monkeypatch.setattr(AL, "METRICS_BY_NAME", patched)

        problems = AL.validate_registry(registry)
        hits = [
            p
            for p in problems
            if target in p and "alert_required=False 的指标" in p
        ]
        assert len(hits) == 1, (
            f"应恰有一条针对 {target} 的「规则多于目录」告警，实得 {problems}"
        )

    def test_every_requirement_13_9_condition_has_a_rule(
        self, registry: AL.AlertRuleRegistry
    ) -> None:
        """独立分母 = requirements 13.9 逐条点名的十五个中文标签。"""
        assert len(AL.REQUIREMENT_13_9_CONDITIONS) >= 15
        for label, condition in sorted(AL.REQUIREMENT_13_9_CONDITIONS.items()):
            assert condition in registry.rules_by_condition, (
                f"Requirement 13.9 的「{label}」没有规则"
            )

    def test_every_alert_required_metric_has_exactly_one_rule(
        self, registry: AL.AlertRuleRegistry
    ) -> None:
        required = {
            name for name, d in MX.METRICS_BY_NAME.items() if d.alert_required
        }
        covered: dict[str, int] = {}
        for rule in registry.rules:
            covered[rule.metric] = covered.get(rule.metric, 0) + 1
        assert set(covered) == required, (
            f"多 {sorted(set(covered) - required)}，少 {sorted(required - set(covered))}"
        )
        assert all(count == 1 for count in covered.values()), covered

    def test_a_rule_referencing_an_unknown_metric_is_refused(self) -> None:
        config = dict(AL.load_alert_config())
        rules = [dict(r) for r in config["rules"]]
        rules[0]["metric"] = "workpaper_sync_nope_total"
        config["rules"] = rules
        with pytest.raises(AL.AlertConfigError, match="不在 METRIC_CATALOG"):
            AL.AlertRuleRegistry(config)

    def test_a_typo_in_result_filter_is_refused(self) -> None:
        """拼错的 result 过滤值会让规则**静默不触发** —— 必须在解析期就拒。"""
        config = dict(AL.load_alert_config())
        rules = [dict(r) for r in config["rules"]]
        target = next(r for r in rules if r["result_filter"])
        target["result_filter"] = list(target["result_filter"]) + ["typoo"]
        config["rules"] = rules
        with pytest.raises(AL.AlertConfigError, match="封闭域"):
            AL.AlertRuleRegistry(config)

    def test_an_ungroupable_dedupe_dim_is_refused(self) -> None:
        config = dict(AL.load_alert_config())
        rules = [dict(r) for r in config["rules"]]
        target = next(
            r
            for r in rules
            if MX.METRICS_BY_NAME[r["metric"]].attribution
            is MX.AttributionClass.platform_scoped
        )
        target["dedupe_key_fields"] = ["participant_id"]
        config["rules"] = rules
        with pytest.raises(AL.AlertConfigError, match="可归因的维度"):
            AL.AlertRuleRegistry(config)

    def test_zero_threshold_is_refused(self) -> None:
        config = dict(AL.load_alert_config())
        rules = [dict(r) for r in config["rules"]]
        rules[0]["threshold"] = 0
        config["rules"] = rules
        with pytest.raises(AL.AlertConfigError, match="threshold 必须为正"):
            AL.AlertRuleRegistry(config)

    def test_recovery_window_shorter_than_trigger_window_is_refused(self) -> None:
        config = dict(AL.load_alert_config())
        rules = [dict(r) for r in config["rules"]]
        rules[0] = dict(rules[0])
        rules[0]["recovery"] = {"kind": "below_threshold", "window_seconds": 1}
        config["rules"] = rules
        with pytest.raises(AL.AlertConfigError, match="恢复窗口"):
            AL.AlertRuleRegistry(config)

    def test_a_placeholder_runbook_is_refused(self) -> None:
        config = dict(AL.load_alert_config())
        rules = [dict(r) for r in config["rules"]]
        rules[0]["runbook"] = "TODO"
        config["rules"] = rules
        with pytest.raises(AL.AlertConfigError, match="runbook"):
            AL.AlertRuleRegistry(config)

    def test_an_empty_rule_table_is_refused(self) -> None:
        config = dict(AL.load_alert_config())
        config["rules"] = []
        with pytest.raises(AL.AlertConfigError, match="空"):
            AL.AlertRuleRegistry(config)

    def test_two_rules_on_one_condition_are_refused(self) -> None:
        config = dict(AL.load_alert_config())
        rules = [dict(r) for r in config["rules"]]
        rules[1]["condition"] = rules[0]["condition"]
        config["rules"] = rules
        with pytest.raises(AL.AlertConfigError, match="被两条规则占用"):
            AL.AlertRuleRegistry(config)

    def test_close_singleton_violation_fires_only_at_two_captures(
        self, registry: AL.AlertRuleRegistry
    ) -> None:
        """exactly-one 的观测面：一次 promoted 不告警，两次才告警。"""
        room, participant = uuid.uuid4(), uuid.uuid4()

        def promote(times: int) -> tuple[AL.AlertInstance, ...]:
            metrics = MX.SyncMetrics()
            for _ in range(times):
                metrics.record_outcome(
                    "workpaper_sync_close_capture_total",
                    result="promoted",
                    landed=False,
                    room_id=room,
                    generation=9,
                    participant_id=participant,
                )
            return registry.evaluate(metrics.samples)

        assert not [i for i in promote(1) if i.rule_id == "close_intent_singleton_violation"]
        fired = [i for i in promote(2) if i.rule_id == "close_intent_singleton_violation"]
        assert len(fired) == 1
        assert fired[0].severity is AL.AlertSeverity.critical
        assert fired[0].auto_recovers is False, (
            "两条 capture 意味着可能已产生两个 application —— 不得自动恢复"
        )

    def test_dedupe_key_collapses_one_room_but_not_two(
        self, registry: AL.AlertRuleRegistry
    ) -> None:
        metrics = MX.SyncMetrics()
        rooms = [uuid.uuid4(), uuid.uuid4()]
        for room in rooms:
            for _ in range(2):
                metrics.record_outcome(
                    "workpaper_sync_close_capture_total",
                    result="promoted",
                    landed=False,
                    room_id=room,
                    generation=1,
                    participant_id=uuid.uuid4(),
                )
        fired = [
            i
            for i in registry.evaluate(metrics.samples)
            if i.rule_id == "close_intent_singleton_violation"
        ]
        assert len(fired) == 2, "两个 room 的故障被去重键合成了一条"
        assert len({i.dedupe_key for i in fired}) == 2

    def test_result_filter_excludes_healthy_results(
        self, registry: AL.AlertRuleRegistry
    ) -> None:
        """`cache_hit` 是幂等重放，不是第二条 capture —— 不得触发 singleton 告警。"""
        metrics = MX.SyncMetrics()
        room, participant = uuid.uuid4(), uuid.uuid4()
        for _ in range(5):
            metrics.record_outcome(
                "workpaper_sync_close_capture_total",
                result="cache_hit",
                landed=False,
                room_id=room,
                generation=1,
                participant_id=participant,
            )
        assert not [
            i
            for i in registry.evaluate(metrics.samples)
            if i.rule_id == "close_intent_singleton_violation"
        ]

    def test_no_successor_fires_its_own_rule_not_a_generic_error(
        self, registry: AL.AlertRuleRegistry
    ) -> None:
        metrics = MX.SyncMetrics()
        metrics.record_outcome(
            "workpaper_sync_close_leader_recovery_required_total",
            result="no_successor",
            landed=False,
            room_id=uuid.uuid4(),
            generation=2,
            participant_id=uuid.uuid4(),
        )
        fired = registry.evaluate(metrics.samples)
        assert [i.rule_id for i in fired] == ["close_leader_no_successor"]
        assert fired[0].auto_recovers is False
        assert "重新授权" in fired[0].runbook

    def test_recovery_deadline_is_none_for_explicit_rules(
        self, registry: AL.AlertRuleRegistry
    ) -> None:
        assert registry.recovery_deadline(
            "close_intent_singleton_violation", fired_at=_now()
        ) is None
        deadline = registry.recovery_deadline("outbox_backlog", fired_at=_now())
        assert deadline is not None and deadline > _now()

    def test_naive_fired_at_is_refused(self, registry: AL.AlertRuleRegistry) -> None:
        with pytest.raises(AL.AlertUsageError, match="时区"):
            registry.recovery_deadline(
                "outbox_backlog", fired_at=datetime.now()  # noqa: DTZ005 - 判据本体
            )


# ═══════════════════════════════════════════════════════════════════════════
# 4. timeline —— 四条独立缺陷码 + 服务端时钟（Property 68 / AC 13.10）
# ═══════════════════════════════════════════════════════════════════════════


def _event(
    seq: int,
    frm: str | None,
    to: str | None,
    *,
    parent: uuid.UUID,
    offset: int = 0,
    stream: TL.TimelineStream = TL.TimelineStream.operation,
) -> TL.TimelineEvent:
    return TL.TimelineEvent(
        stream=stream,
        parent_id=parent,
        sequence_no=seq,
        occurred_at=_now() + timedelta(seconds=offset),
        from_state=frm,
        to_state=to,
        payload={},
    )


class TestProjectionOracle:
    """`check_projection` 的四条判据各有独立缺陷码，逐条参数化。"""

    def _service(self) -> TL.SyncTimelineService:
        return TL.SyncTimelineService.__new__(TL.SyncTimelineService)

    def _healthy(self, parent: uuid.UUID) -> list[TL.TimelineEvent]:
        return [
            _event(1, None, "created", parent=parent, offset=0),
            _event(2, "created", "accepted", parent=parent, offset=1),
            _event(3, "accepted", "applied", parent=parent, offset=2),
        ]

    def test_a_healthy_timeline_has_no_defect(self) -> None:
        parent = uuid.uuid4()
        check = self._service().check_projection(
            stream=TL.TimelineStream.operation,
            parent_id=parent,
            current_state="applied",
            events=self._healthy(parent),
        )
        assert check.consistent and check.defects == ()
        assert check.event_count == 3
        assert check.last_event_state == "applied"

    def test_current_state_diverging_from_the_last_event_is_caught(self) -> None:
        parent = uuid.uuid4()
        check = self._service().check_projection(
            stream=TL.TimelineStream.operation,
            parent_id=parent,
            current_state="error",
            events=self._healthy(parent),
        )
        assert check.defects == (TL.ProjectionDefect.state_diverged,)

    def test_a_deleted_middle_event_is_caught_as_a_sequence_gap(self) -> None:
        parent = uuid.uuid4()
        events = self._healthy(parent)
        del events[1]
        defects = self._service().check_projection(
            stream=TL.TimelineStream.operation,
            parent_id=parent,
            current_state="applied",
            events=events,
        ).defects
        assert TL.ProjectionDefect.sequence_gap in defects

    def test_a_forged_event_breaks_the_transition_chain(self) -> None:
        parent = uuid.uuid4()
        events = self._healthy(parent)
        events[2] = _event(3, "conflict", "applied", parent=parent, offset=2)
        defects = self._service().check_projection(
            stream=TL.TimelineStream.operation,
            parent_id=parent,
            current_state="applied",
            events=events,
        ).defects
        assert TL.ProjectionDefect.transition_chain_broken in defects

    def test_a_regressed_server_clock_is_caught(self) -> None:
        parent = uuid.uuid4()
        events = self._healthy(parent)
        events[2] = _event(3, "accepted", "applied", parent=parent, offset=-30)
        defects = self._service().check_projection(
            stream=TL.TimelineStream.operation,
            parent_id=parent,
            current_state="applied",
            events=events,
        ).defects
        assert TL.ProjectionDefect.clock_regressed in defects

    def test_an_empty_timeline_is_its_own_defect(self) -> None:
        check = self._service().check_projection(
            stream=TL.TimelineStream.operation,
            parent_id=uuid.uuid4(),
            current_state="created",
            events=[],
        )
        assert check.defects == (TL.ProjectionDefect.empty_timeline,)

    def test_a_stateless_sequence_fold_event_is_not_a_defect(self) -> None:
        """application 流的 `sequence_folded` 不带状态，不得被判成断链/分叉。

        这条是**真实缺陷**的回归：第一版把链式与投影判据建在「全部事件」上，于是每次
        合法的 same-application sequence fold 都会同时误报
        `transition_chain_broken` 与 `state_diverged` —— 而 fold 恰恰是协同下最常见的
        事件（Task 29 明文要求它「不 self-stale」）。
        """
        parent = uuid.uuid4()
        events = [
            _event(1, None, "queued", parent=parent, offset=0,
                   stream=TL.TimelineStream.application),
            _event(2, None, None, parent=parent, offset=1,
                   stream=TL.TimelineStream.application),
            _event(3, "queued", "applied", parent=parent, offset=2,
                   stream=TL.TimelineStream.application),
        ]
        check = self._service().check_projection(
            stream=TL.TimelineStream.application,
            parent_id=parent,
            current_state="applied",
            events=events,
        )
        assert check.defects == (), check.defects

    def test_assert_projection_raises_only_on_defects(self) -> None:
        service = self._service()
        parent = uuid.uuid4()
        good = service.check_projection(
            stream=TL.TimelineStream.operation,
            parent_id=parent,
            current_state="applied",
            events=self._healthy(parent),
        )
        service.assert_projection(good)
        bad = service.check_projection(
            stream=TL.TimelineStream.operation,
            parent_id=parent,
            current_state="error",
            events=self._healthy(parent),
        )
        with pytest.raises(TL.TimelineProjectionError):
            service.assert_projection(bad)


class TestTimelineQueryContract:
    def test_all_ac_13_6_locators_exist(self) -> None:
        """AC 13.6 点名的定位维度一个都不能少（独立分母写在这里）。"""
        required = {
            "wp_id",
            "room_id",
            "request_id",
            "participant_id",
            "operation_id",
            "recovery_case_id",
            "application_id",
            "correlation_id",
        }
        assert set(TL.TimelineQuery.LOCATORS) == required, (
            f"多 {sorted(set(TL.TimelineQuery.LOCATORS) - required)}，"
            f"少 {sorted(required - set(TL.TimelineQuery.LOCATORS))}"
        )

    def test_locators_is_a_classvar_not_a_field(self) -> None:
        """`LOCATORS` 必须是 `ClassVar`，不能变成可被调用方覆盖的实例字段。

        真实踩过：写成 `Final[tuple[...]]` 时 `@dataclass` 照样把它收成字段
        （PEP 591 只影响类型检查），于是 `TimelineQuery(LOCATORS=())` 能让
        `validate()` 恒通过 —— 「至少一个定位维度」这道门被静默绕开。
        """
        import dataclasses

        names = {f.name for f in dataclasses.fields(TL.TimelineQuery)}
        assert "LOCATORS" not in names, (
            "LOCATORS 变成了 dataclass 字段 —— 调用方可以传空清单绕过 validate()"
        )

    def test_a_query_without_any_locator_is_refused(self) -> None:
        with pytest.raises(TL.TimelineUsageError, match="至少需要一个定位维度"):
            TL.TimelineQuery().validate()

    @pytest.mark.parametrize(
        "locator", sorted(TL.TimelineQuery.LOCATORS), ids=sorted(TL.TimelineQuery.LOCATORS)
    )
    def test_each_locator_alone_is_enough(self, locator: str) -> None:
        TL.TimelineQuery(**{locator: uuid.uuid4()}).validate()

    def test_limit_bounds_are_enforced(self) -> None:
        for bad in (0, -1, TL.MAX_TIMELINE_ROWS + 1):
            with pytest.raises(TL.TimelineUsageError, match="limit"):
                TL.TimelineQuery(room_id=uuid.uuid4(), limit=bad).validate()

    def test_only_server_clock_columns_may_order_the_timeline(self) -> None:
        """AC 13.10：浏览器 trace 不得决定顺序。"""
        TL.assert_server_clock_only(TL.SERVER_ORDER_KEYS)
        for illegal in (["client_ts"], ["browser_time"], ["client_edit_epoch_ms"]):
            with pytest.raises(TL.TimelineUsageError, match="服务端时钟"):
                TL.assert_server_clock_only(illegal)

    def test_the_merged_query_asserts_server_clock_before_reading(self) -> None:
        """形态判据：`merged_timeline` 必须真的调用那道门。

        用 AST 而不是 `"assert_server_clock_only" in source`：后者在
        `if False: assert_server_clock_only(...)` 下照样满足（presence 式判据的经典缺陷）。
        这里断言它是函数体**顶层**的一个表达式语句，不在任何分支里。
        """
        fn = _func(_tree(_TIMELINE_PY), "merged_timeline")
        top_level_calls = [
            node.value.func.id
            for node in fn.body
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
        ]
        assert "assert_server_clock_only" in top_level_calls, (
            "merged_timeline 没有在函数体顶层无条件调用 assert_server_clock_only —— "
            "放在分支里等于可被绕过"
        )


class TestRecoveryTimelineHasNoOperation:
    """P68 / AC 13.5：recovery case 在 claim 前不得借 operation timeline 伪造 operation。"""

    def test_the_recovery_timeline_type_has_no_operation_events_field(self) -> None:
        """**结构性**判据：类型里根本没有 `operation_events`。

        行为判据（「claim 前 operation_events 为空」）会被一个「顺手挂上 operation
        事件」的实现绕过 —— 只要它在 claim 后才填。结构判据把这条路堵死：
        字段不存在，就不可能填。
        """
        import dataclasses

        names = {f.name for f in dataclasses.fields(TL.RecoveryTimeline)}
        assert "operation_events" not in names, (
            "RecoveryTimeline 出现了 operation_events —— recovery timeline 一旦能装 "
            "operation 事件，「claim 前零 operation」就只剩注释约定"
        )
        assert "events" in names and "claimed_operation_id" in names

    def test_three_entities_flag_requires_all_three(self) -> None:
        base = dict(
            case_id=uuid.uuid4(),
            state="unclaimed",
            reason="crash_close",
            claimed_operation_id=None,
            claimed_application_id=None,
            recovery_request_id=None,
        )
        assert TL.RecoveryTimeline(**base).has_three_entities is False
        for present in ("claimed_operation_id", "claimed_application_id", "recovery_request_id"):
            partial = dict(base)
            partial[present] = uuid.uuid4()
            assert TL.RecoveryTimeline(**partial).has_three_entities is False, (
                f"只有 {present} 就宣称三实体齐备 —— download-only 会被判成已 claim"
            )
        full = dict(base)
        full.update(
            claimed_operation_id=uuid.uuid4(),
            claimed_application_id=uuid.uuid4(),
            recovery_request_id=uuid.uuid4(),
        )
        assert TL.RecoveryTimeline(**full).has_three_entities is True


# ═══════════════════════════════════════════════════════════════════════════
# 5. required scenario set 推导（Property 69 / 70 / 71 · AC 12.12）
# ═══════════════════════════════════════════════════════════════════════════


def _profile(
    *,
    entry_id: str = "xlsx/test-entry",
    editability: Editability = Editability.editable,
    room_model: RoomModel = RoomModel.shared,
    payload: dict[str, Any] | None = None,
) -> EntryProfile:
    body = {"profile_id": "xlsx.editable.shared.single.v1", "document_type": "xlsx"}
    body.update(payload or {})
    return EntryProfile(
        entry_id=entry_id,
        editability=editability,
        room_model=room_model,
        scenario_profile=ScenarioProfile(profile_id=str(body["profile_id"]), payload=body),
    )


class TestClosePredicate:
    """AC 12.12 的机器谓词：`editable AND (bidirectional OR shared)`。"""

    @pytest.mark.parametrize(
        ("editability", "room_model", "capability", "expected"),
        [
            (Editability.editable, RoomModel.shared, Capability.single_onlyoffice, True),
            (Editability.editable, RoomModel.exclusive, Capability.bidirectional, True),
            (Editability.editable, RoomModel.exclusive, Capability.single_onlyoffice, False),
            (Editability.readonly, RoomModel.shared, Capability.single_onlyoffice, False),
            (Editability.readonly, RoomModel.exclusive, Capability.bidirectional, False),
        ],
        ids=[
            "editable+shared+single_oo",
            "editable+exclusive+bidirectional",
            "editable+exclusive+single_oo",
            "readonly+shared",
            "readonly+bidirectional",
        ],
    )
    def test_truth_table(
        self,
        editability: Editability,
        room_model: RoomModel,
        capability: Capability,
        expected: bool,
    ) -> None:
        assert (
            EV.close_scenarios_required(
                profile=_profile(editability=editability, room_model=room_model),
                capability=capability,
            )
            is expected
        )

    def test_shared_room_alone_is_enough_even_without_bidirectional(self) -> None:
        """本条是 179 个 entry 之所以必须跑 close 场景的**唯一**理由。

        把谓词的 `or` 写成 `and` 会让它们悄悄少八个场景，而「场景都跑过了」的计数仍满分。
        """
        required = EV.derive_required_scenarios(
            profile=_profile(room_model=RoomModel.shared),
            capability=Capability.single_onlyoffice,
            authority_model=AuthorityModel.opaque_single_onlyoffice,
        )
        assert required.close_required is True
        close_ids = {s.scenario_id for s in EV.CLOSE_SCENARIOS}
        assert close_ids <= set(required.scenario_ids)


class TestRequiredScenarioDerivation:
    def test_the_eight_close_scenarios_are_all_present(self) -> None:
        """独立分母 = Task 29 正文点名的八条 close 场景语义。"""
        expected = {
            "single_participant_close",
            "two_user_close_order_a_then_b",
            "two_user_close_order_b_then_a",
            "b_close_before_a_forcesave_terminal",
            "b_close_after_a_forcesave_terminal",
            "close_leader_revoked_successor_exactly_one",
            "close_leader_revoked_no_successor_recovery_required",
            "close_reconciler_reentrant_exactly_one_capture",
        }
        actual = {s.scenario_id for s in EV.CLOSE_SCENARIOS}
        assert actual == expected, (
            f"多 {sorted(actual - expected)}，少 {sorted(expected - actual)}"
        )

    def test_close_scenarios_declare_their_expected_capture_count(self) -> None:
        """七条要求 exactly-one，无 successor 那条要求恰零 —— 两侧都锁。"""
        by_id = {s.scenario_id: s for s in EV.CLOSE_SCENARIOS}
        assert (
            by_id["close_leader_revoked_no_successor_recovery_required"].expected_close_captures
            == 0
        )
        others = [
            s
            for sid, s in by_id.items()
            if sid != "close_leader_revoked_no_successor_recovery_required"
        ]
        assert all(s.expected_close_captures == 1 for s in others), (
            "除「无 successor」外每条 close 场景都必须要求恰一个 capture"
        )

    def test_download_only_scenario_expects_zero_entities(self) -> None:
        scenario = next(
            s
            for s in EV.PROJECTION_BASE_SCENARIOS
            if s.scenario_id == "download_only_zero_three_entities"
        )
        assert scenario.expects_zero_entities is True
        assert scenario.expects_application is False
        assert scenario.expects_recovery_case is True

    def test_the_sixteen_base_scenarios_cover_the_ac_12_12_list(self) -> None:
        """独立分母 = AC 12.12 第一句逐项列出的场景语义。"""
        expected = {
            "html_to_oo",
            "oo_to_html",
            "identity_retention",
            "different_field_merge",
            "same_field_conflict_resolve",
            "frozen_base_status_6_2_dedupe",
            "same_application_higher_sequence_fold",
            "cross_participant_idempotency_409",
            "quarantined_rejects_application_and_engine",
            "opaque_version_rollback_no_numeric_collision",
            "browser_crash_no_userdata_recovery_case",
            "authorization_first_recovery_claim",
            "wrong_prior_confirmation_bundle_fence_contributor_rejected",
            "download_only_zero_three_entities",
            "refresh_required_reopen",
            "rollback",
        }
        actual = {s.scenario_id for s in EV.PROJECTION_BASE_SCENARIOS}
        assert actual == expected, (
            f"多 {sorted(actual - expected)}，少 {sorted(expected - actual)}"
        )

    def test_only_the_two_field_level_scenarios_may_be_substituted(self) -> None:
        base = _profile(room_model=RoomModel.shared)
        projection = EV.derive_required_scenarios(
            profile=base,
            capability=Capability.bidirectional,
            authority_model=AuthorityModel.projection_contract,
        )
        for model in sorted(EV.SUBSTITUTING_AUTHORITY_MODELS, key=lambda m: m.value):
            substituted = EV.derive_required_scenarios(
                profile=base, capability=Capability.bidirectional, authority_model=model
            )
            removed = set(projection.scenario_ids) - set(substituted.scenario_ids)
            added = set(substituted.scenario_ids) - set(projection.scenario_ids)
            assert removed == set(EV.FIELD_LEVEL_SCENARIOS), (
                f"{model.value} 替换掉的不只是字段级两场景: {sorted(removed)}"
            )
            assert added == {s.scenario_id for s in EV.AUTHORITY_SUBSTITUTE_SCENARIOS}
            assert EV.NON_REPLACEABLE_SCENARIOS <= set(substituted.scenario_ids), (
                "close/recovery/authorization 场景被替换掉了 —— AC 12.12 明文禁止"
            )

    def test_projection_contract_may_not_substitute(self) -> None:
        """`projection_contract` 不在替换枚举里，强行替换必须抛。"""
        with pytest.raises(EV.ScenarioSubstitutionError, match="允许替换的枚举"):
            EV._apply_authority_substitution(
                EV.PROJECTION_BASE_SCENARIOS,
                authority_model=AuthorityModel.projection_contract,
            )

    def test_the_non_replaceable_set_is_exactly_the_close_recovery_authorization_ones(
        self,
    ) -> None:
        """独立分母：不可替换集 = close ∪ recovery ∪ authorization 的场景 id。"""
        expected = {
            s.scenario_id
            for s in EV.PROJECTION_BASE_SCENARIOS + EV.CLOSE_SCENARIOS
            if s.family
            in (
                EV.ScenarioFamily.close,
                EV.ScenarioFamily.recovery,
                EV.ScenarioFamily.authorization,
            )
        }
        assert EV.NON_REPLACEABLE_SCENARIOS == expected
        assert len(expected) == 14, f"不可替换集大小变了: {len(expected)}"
        assert not (set(EV.FIELD_LEVEL_SCENARIOS) & EV.NON_REPLACEABLE_SCENARIOS)

    def test_dynamic_and_word_additions_come_from_the_machine_profile(self) -> None:
        dynamic = EV.derive_required_scenarios(
            profile=_profile(payload={"mount_cardinality": "dynamic"}),
            capability=Capability.bidirectional,
            authority_model=AuthorityModel.projection_contract,
        )
        assert {s.scenario_id for s in EV.DYNAMIC_SCENARIOS} <= set(dynamic.scenario_ids)
        single = EV.derive_required_scenarios(
            profile=_profile(payload={"mount_cardinality": "single"}),
            capability=Capability.bidirectional,
            authority_model=AuthorityModel.projection_contract,
        )
        assert not ({s.scenario_id for s in EV.DYNAMIC_SCENARIOS} & set(single.scenario_ids))
        word = EV.derive_required_scenarios(
            profile=_profile(payload={"document_type": "docx"}),
            capability=Capability.bidirectional,
            authority_model=AuthorityModel.projection_contract,
        )
        assert {s.scenario_id for s in EV.WORD_SCENARIOS} <= set(word.scenario_ids)
        assert not (
            {s.scenario_id for s in EV.WORD_SCENARIOS} & set(single.scenario_ids)
        )

    def test_unreachable_entries_require_nothing(self) -> None:
        required = EV.derive_required_scenarios(
            profile=_profile(editability=Editability.unreachable, room_model=RoomModel.none),
            capability=Capability.unreachable,
            authority_model=AuthorityModel.opaque_single_onlyoffice,
        )
        assert required.scenarios == ()
        assert required.close_required is False

    def test_single_html_requires_only_the_no_blank_artifact_scenario(self) -> None:
        required = EV.derive_required_scenarios(
            profile=_profile(room_model=RoomModel.none),
            capability=Capability.single_html,
            authority_model=AuthorityModel.opaque_single_onlyoffice,
        )
        assert required.scenario_ids == ("single_html_no_blank_oo_artifact",)

    def test_a_contradictory_profile_is_refused_by_the_single_shared_rule(self) -> None:
        """交叉一致性必须委派给 Task 13 的唯一规则，不是本模块的第二份拷贝。"""
        with pytest.raises(EntryProfileError):
            EV.derive_required_scenarios(
                profile=_profile(room_model=RoomModel.exclusive),
                capability=Capability.single_html,
                authority_model=AuthorityModel.opaque_single_onlyoffice,
            )

    def test_derivation_delegates_the_cross_rule_instead_of_reimplementing_it(self) -> None:
        """形态判据：`derive_required_scenarios` 必须**调用**共享规则。

        断言它是函数体顶层的无条件调用；写成 `if False:` 或搬进某个分支都会红。
        """
        fn = _func(_tree(_EVIDENCE_PY), "derive_required_scenarios")
        top_level_calls = [
            node.value.func.id
            for node in fn.body
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
        ]
        assert "assert_profile_consistent_with_capability" in top_level_calls, (
            "推导没有在顶层调用 Task 13 的交叉规则 —— 要么漏了校验，要么抄了第二份"
        )


class TestScenarioKindIsLockedToV151:
    """`scenario_kind` 必须与 V151 的 CHECK 同域，且由 entity 期望单点推导。

    这一组是**真实缺陷**的回归：第一版 `ScenarioKind` 用的是语义分类
    （direction/identity/merge/… 12 个值），真库插入直接 `CheckViolationError`，
    而所有离线判据全绿 —— 因为没有一条把这个字段与 DDL 对上。
    """

    _MIGRATION = (
        _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"
    )

    def _ddl_domain(self) -> set[str]:
        """从迁移文本反向解析 `ck_wpees_scenario_kind` 的取值域（独立分母）。"""
        import re

        sql = self._MIGRATION.read_text(encoding="utf-8")
        anchor = sql.find("ck_wpees_scenario_kind")
        assert anchor > 0, "V151 里找不到 ck_wpees_scenario_kind"
        window = sql[anchor : anchor + 400]
        return set(re.findall(r"'([a-z_]+)'", window))

    def test_the_enum_matches_the_v151_check_exactly(self) -> None:
        ddl = self._ddl_domain()
        enum_values = {kind.value for kind in EV.ScenarioKind}
        assert enum_values == ddl, (
            f"ScenarioKind 与 V151 的 CHECK 不等值：多 {sorted(enum_values - ddl)}，"
            f"少 {sorted(ddl - enum_values)}"
        )

    def test_the_semantic_family_is_a_separate_enum(self) -> None:
        """语义分组不得混进入库取值域（混进去就会被 CHECK 拒）。"""
        ddl = self._ddl_domain()
        families = {family.value for family in EV.ScenarioFamily}
        assert not (families & ddl), (
            f"ScenarioFamily 与 DB 取值域重叠 {sorted(families & ddl)} —— "
            "两个概念混用时，写库的那个迟早被填成语义值"
        )

    @pytest.mark.parametrize(
        ("scenario_id", "expected_kind"),
        [
            ("html_to_oo", "standard"),
            ("download_only_zero_three_entities", "download_only"),
            ("browser_crash_no_userdata_recovery_case", "recovery_reject"),
            ("authorization_first_recovery_claim", "recovery_claim"),
            ("single_participant_close", "close_capture"),
        ],
        ids=["standard", "download-only", "recovery-reject", "recovery-claim", "close"],
    )
    def test_kind_is_derived_from_the_entity_shape(
        self, scenario_id: str, expected_kind: str
    ) -> None:
        by_id = {
            s.scenario_id: s
            for s in EV.PROJECTION_BASE_SCENARIOS + EV.CLOSE_SCENARIOS
        }
        assert by_id[scenario_id].kind.value == expected_kind

    def test_every_required_scenario_has_a_v151_representable_entity_shape(self) -> None:
        """V151 的三条 entity 约束 ↔ 场景声明的 entity 期望必须自洽。

        只有登记在 `SCHEMA_UNREPRESENTABLE_SCENARIOS` 里的那一条允许不自洽（并且它因此
        让 entry 保持未验收）。这条判据的价值在于：任何**新增**的零-application 场景都
        会立刻打红，而不是等到真库插入时才炸。
        """
        offenders = sorted(
            s.scenario_id
            for s in EV.PROJECTION_BASE_SCENARIOS + EV.CLOSE_SCENARIOS
            if not s.schema_representable_as_passed
        )
        assert offenders == sorted(EV.SCHEMA_UNREPRESENTABLE_SCENARIOS), (
            f"schema 不可表达的场景集合漂移：实得 {offenders}，"
            f"登记 {sorted(EV.SCHEMA_UNREPRESENTABLE_SCENARIOS)}"
        )

    def test_the_declared_gap_stays_in_the_required_set(self) -> None:
        """登记欠账**不等于**把场景移出必需集合。"""
        required_ids = {s.scenario_id for s in EV.PROJECTION_BASE_SCENARIOS}
        for sid in EV.SCHEMA_UNREPRESENTABLE_SCENARIOS:
            assert sid in required_ids, f"{sid} 被从 required set 里摘走了"


class TestRequiredSetDigest:
    """P71：任一输入变化都必须让 digest 变（否则旧 evidence 能保鲜）。"""

    def _base(self) -> EV.RequiredScenarioSet:
        return EV.derive_required_scenarios(
            profile=_profile(),
            capability=Capability.bidirectional,
            authority_model=AuthorityModel.projection_contract,
        )

    def test_digest_is_stable_for_identical_inputs(self) -> None:
        assert self._base().digest == self._base().digest

    def test_changing_room_model_changes_the_digest(self) -> None:
        other = EV.derive_required_scenarios(
            profile=_profile(room_model=RoomModel.exclusive),
            capability=Capability.bidirectional,
            authority_model=AuthorityModel.projection_contract,
        )
        assert other.digest != self._base().digest

    def test_changing_the_scenario_profile_payload_changes_the_digest(self) -> None:
        other = EV.derive_required_scenarios(
            profile=_profile(payload={"mount_cardinality": "dynamic"}),
            capability=Capability.bidirectional,
            authority_model=AuthorityModel.projection_contract,
        )
        assert other.digest != self._base().digest

    def test_changing_the_authority_model_changes_the_digest(self) -> None:
        other = EV.derive_required_scenarios(
            profile=_profile(),
            capability=Capability.bidirectional,
            authority_model=AuthorityModel.custom_authoritative_ooxml,
        )
        assert other.digest != self._base().digest

    def test_entry_id_is_in_the_digest_so_evidence_cannot_be_copied_across_entries(
        self,
    ) -> None:
        """P70 的第一道门：两个 entry 即使 profile 一样，required set digest 也不同。"""
        other = EV.derive_required_scenarios(
            profile=_profile(entry_id="xlsx/another-entry"),
            capability=Capability.bidirectional,
            authority_model=AuthorityModel.projection_contract,
        )
        assert other.digest != self._base().digest

    def test_the_scenario_list_itself_is_part_of_the_digest(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """P71 的核心：**增删 required scenario** 必须让 digest 变。

        上面几条都是改「输入」（room_model / payload / authority model / entry_id），
        而那些输入自己就在 digest 里 —— 所以即便把 `scenario_ids` 从 digest 里摘掉，
        它们照样会红。要证明场景清单本身进了 digest，唯一办法是**只**改场景清单、
        其余 digest 输入逐项保持不变。

        🔴 与 `test_the_derivation_version_is_part_of_the_digest` 同一个陷阱：`digest`
        是 property，必须先取成字符串再 monkeypatch，否则两侧都读到新目录、断言恒成立。
        """
        before_set = self._base()
        before_digest = before_set.digest
        before_ids = before_set.scenario_ids

        extra = EV.RequiredScenario(
            "probe_extra_scenario", EV.ScenarioFamily.direction, "13.5",
            "仅用于证明场景清单进了 digest 的探针场景",
        )
        monkeypatch.setattr(
            EV, "PROJECTION_BASE_SCENARIOS", EV.PROJECTION_BASE_SCENARIOS + (extra,)
        )
        after_set = self._base()

        # 独立分母：先证明「只有场景清单变了」，再断 digest 不等。缺这一步的话，
        # 断言不等可能是别的输入被顺带改动造成的（假红）。
        assert after_set.scenario_ids != before_ids
        assert set(after_set.scenario_ids) - set(before_ids) == {"probe_extra_scenario"}
        for field in (
            "entry_id", "capability", "authority_model", "editability", "room_model",
            "scenario_profile_digest",
        ):
            assert getattr(after_set, field) == getattr(before_set, field), (
                f"本测试只应改动场景清单，但 {field} 也变了 —— 判据被污染"
            )

        assert after_set.digest != before_digest, (
            "required scenario set 的场景清单没有进 digest —— 增删一条必需场景后 digest "
            "不变，旧 test run 永不 stale，P71 的核心承诺失效"
        )

    def test_the_derivation_version_is_part_of_the_digest(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """改推导规则必须 +1 版本号，否则旧 run 不会 stale。

        🔴 必须**先把 digest 取成字符串**再改常量：`digest` 是 property，改完再读两侧
        都会看到新版本号，断言就恒成立（自证重言式）。第一版正是这么写的，实测两边
        digest 完全相同。
        """
        before = self._base().digest
        monkeypatch.setattr(EV, "DERIVATION_VERSION", EV.DERIVATION_VERSION + 1)
        after = self._base().digest
        assert before != after, (
            "推导版本号没有进 required set digest —— 改了推导规则旧 evidence 仍算 verified"
        )


class TestDerivationOverTheRealManifest:
    """跑真实 186 条 manifest：推导必须对生产数据可用且确定。"""

    @pytest.fixture(scope="class")
    def entries(self) -> list[dict[str, Any]]:
        return list(load_entry_manifest()["entries"])

    def test_every_entry_either_derives_or_reports_profile_drift(
        self, entries: list[dict[str, Any]]
    ) -> None:
        derived = 0
        drifted: list[str] = []
        for entry in entries:
            try:
                EV.derive_for_manifest_entry(
                    entry, authority_model=AuthorityModel.opaque_single_onlyoffice
                )
                derived += 1
            except EntryProfileError:
                drifted.append(str(entry["entry_id"]))
        assert derived + len(drifted) == len(entries)
        assert derived >= 175, f"只有 {derived} 条能推导出 required set"
        # 🔴 不断言 drifted 的具体条数：那会把「manifest 当前的欠账」锁成基线。
        # 判据是「漂移的都能被指名」，欠账 owner 是 Task 1/67。
        assert all("/" in item for item in drifted), drifted

    def test_the_close_predicate_hits_every_shared_editable_entry(
        self, entries: list[dict[str, Any]]
    ) -> None:
        """独立分母：直接从 manifest 字段算谓词，与推导结果双向比对。"""
        expected = 0
        actual = 0
        for entry in entries:
            profile = extract_entry_profile(entry)
            capability = capability_of(entry)
            if profile.editability is Editability.editable and (
                capability is Capability.bidirectional
                or profile.room_model is RoomModel.shared
            ):
                expected += 1
            try:
                required = EV.derive_for_manifest_entry(
                    entry, authority_model=AuthorityModel.opaque_single_onlyoffice
                )
            except EntryProfileError:
                continue
            if required.close_required:
                actual += 1
        assert expected >= 100, f"谓词命中面太小: {expected}"
        assert actual == expected, (
            f"推导判定需要 close 场景的 entry 数 {actual} 与直接按 manifest 字段算出的 "
            f"{expected} 不等 —— 谓词被改动过"
        )

    def test_manifest_source_digest_is_available(self) -> None:
        digest = EV.manifest_source_digest()
        assert len(digest) == 64 and digest == digest.lower()

    def test_a_manifest_without_source_digest_fails_closed(self) -> None:
        with pytest.raises(EV.EvidenceError, match="source_digest"):
            EV.manifest_source_digest({"entries": []})


class TestStaleAndDefectCodesAreDistinct:
    """P71 / P69：每类失效与缺陷各有独立码（共用码会让靠后的检查被遮蔽）。"""

    def test_ac_14_16_change_classes_all_have_a_stale_reason(self) -> None:
        """独立分母 = AC 14.16 列出的变化类别。"""
        required = {
            "manifest_source_digest_changed",
            "editability_changed",
            "room_model_changed",
            "scenario_profile_changed",
            "required_scenario_set_changed",
            "authority_model_changed",
            "definition_bundle_changed",
            # AC 14.16 的原文把 bundle 与「**及其** template/instrumentation/contract
            # typed child identities」并列 ⇒ typed child 是**第三条**独立轴，不是 bundle
            # 那条的一部分。Task 39 补上它并在
            # `evidence_freshness.bundle_stale_reasons` 里 emit（recomputer 拿不到 bundle
            # 输入，只能比同一批写入的两个副本，所以三条轴由 freshness guard 承担）。
            # 合成一码会让「child 被换掉而 bundle digest 未变」（篡改）与「bundle 整体
            # 升级」（正常）分不出来。
            "definition_bundle_child_changed",
            "source_commit_changed",
            "runner_changed",
            "onlyoffice_build_changed",
            "browser_build_changed",
            "environment_digest_changed",
        }
        actual = {reason.value for reason in EV.StaleReason}
        assert actual == required, (
            f"多 {sorted(actual - required)}，少 {sorted(required - actual)}"
        )

    def test_all_defect_codes_are_unique(self) -> None:
        values = [d.value for d in EV.EvidenceDefect]
        assert len(values) == len(set(values))
        assert len(values) >= 20

    def test_verdict_result_is_derived_not_written(self) -> None:
        base = dict(
            entry_id="xlsx/x",
            run_id=uuid.uuid4(),
            required_scenario_ids=("a",),
            observed_scenario_ids=("a",),
        )
        assert EV.EvidenceVerdict(**base).result is EV.EvidenceResult.verified
        assert (
            EV.EvidenceVerdict(**base, stale_reasons=(EV.StaleReason.runner_changed,)).result
            is EV.EvidenceResult.stale
        )
        assert (
            EV.EvidenceVerdict(
                **base, defects=(EV.EvidenceDefect.missing_scenario,)
            ).result
            is EV.EvidenceResult.unverified
        )
        # 缺陷优先于 stale：一个「既 stale 又有缺陷」的 run 不得只报 stale。
        assert (
            EV.EvidenceVerdict(
                **base,
                defects=(EV.EvidenceDefect.missing_scenario,),
                stale_reasons=(EV.StaleReason.runner_changed,),
            ).result
            is EV.EvidenceResult.unverified
        )
        no_run = dict(base)
        no_run["run_id"] = None
        assert EV.EvidenceVerdict(**no_run).result is EV.EvidenceResult.unverified

    def test_environment_digest_changes_with_every_field(self) -> None:
        base = EV.EvidenceEnvironment(
            source_commit="abc123",
            runner_version="task39:v1",
            onlyoffice_build="9.4.0.42",
            browser_build="Chrome/140",
        )
        import dataclasses

        for field in dataclasses.fields(base):
            other = dataclasses.replace(base, **{field.name: "changed"})
            assert other.digest != base.digest, f"{field.name} 变了但环境 digest 没变"


# ═══════════════════════════════════════════════════════════════════════════
# 6. router 接线（避免「additive 注入即死代码」）
# ═══════════════════════════════════════════════════════════════════════════


class TestRouterWiring:
    def test_the_timeline_endpoint_goes_through_the_timeline_service(self) -> None:
        """AST：timeline 端点必须调用 `SyncTimelineService(...).operation_timeline`。"""
        fn = _func(_tree(_ROUTER_PY), "get_operation_timeline")
        calls = {
            node.func.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "operation_timeline" in calls, (
            "timeline 端点没有走 SyncTimelineService —— 手写投影会绕开 RedactionPolicy"
        )
        names = {
            node.func.id
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "SyncTimelineService" in names

    def test_the_recovery_case_timeline_endpoint_exists_and_is_separate(self) -> None:
        paths = {
            r.path
            for r in SR.router.routes
            if "GET" in r.methods and r.path.endswith("/timeline")
        }
        assert len(paths) == 2, f"timeline 端点应恰有两个（operation / recovery case）: {paths}"
        assert any("recovery-cases" in p for p in paths)
        fn = _func(_tree(_ROUTER_PY), "get_recovery_case_timeline")
        calls = {
            node.func.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "recovery_case_timeline" in calls
        assert "operation_timeline" not in calls, (
            "recovery case 端点调了 operation timeline —— 那会伪造 operation"
        )

    def test_every_metric_name_used_by_the_router_is_in_the_catalog(self) -> None:
        """接线判据：router 里出现的每个指标名必须在目录里（打错字 = 永不 emit）。"""
        tree = _tree(_ROUTER_PY)
        used: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            if not isinstance(target, ast.Attribute):
                continue
            if target.attr not in ("record_outcome", "observe", "set_gauge", "record_error"):
                continue
            if not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                used.add(first.value)
        assert used, "router 里没有任何指标 emit —— Task 29 的指标全是死代码"
        unknown = sorted(used - set(MX.METRICS_BY_NAME))
        assert not unknown, f"router 用了目录外的指标名 {unknown}"

    def test_the_router_emits_the_task29_named_metrics(self) -> None:
        """Task 29 点名必须能按 room/generation/participant 归因的那几条真的被 emit。"""
        source = _ROUTER_PY.read_text(encoding="utf-8")
        for metric in (
            "workpaper_sync_forcesave_fingerprint_conflict_total",
            "workpaper_sync_forcesave_accepted_total",
            "workpaper_sync_incoming_durable_total",
            "workpaper_sync_recovery_case_total",
            "workpaper_sync_recovery_claim_total",
            "workpaper_sync_recovery_download_only_total",
            "workpaper_sync_close_capture_total",
            "workpaper_sync_close_leader_recovery_required_total",
            "workpaper_sync_close_leader_authorization_stale_total",
            "workpaper_sync_refresh_required_total",
            "workpaper_sync_post_durable_failure_total",
        ):
            assert metric in source, f"router 从未 emit {metric}"

    def test_the_apply_path_reads_the_result_instead_of_assuming_success(self) -> None:
        """AC 5.7/5.8 的形态：apply 后的分型必须比对 `result.result`。

        `apply_durable_incoming` 在 durable 之后**刻意不抛**，所以「没抛异常就记成功」
        会把 refresh_required / conflict / error 全记成 applied。这里断言函数里存在对
        `OoToHtmlResult` 成员的比较，而不是只 grep 名字。
        """
        fn = _func(_tree(_ROUTER_PY), "_apply_durable_incoming")
        compared: set[str] = set()
        for node in ast.walk(fn):
            if not isinstance(node, ast.Compare):
                continue
            for operand in [node.left, *node.comparators]:
                if (
                    isinstance(operand, ast.Attribute)
                    and isinstance(operand.value, ast.Name)
                    and operand.value.id == "OoToHtmlResult"
                ):
                    compared.add(operand.attr)
        assert {"applied", "refresh_required", "conflict"} <= compared, (
            f"apply 路径只比较了 {sorted(compared)} —— 未分型的终态会被记成成功"
        )

    def test_the_callback_metric_reads_durable_at_not_a_state_name(self) -> None:
        """AC 5.4：归属/耐久判据只以 `durable_at` 判定，不得用泛化 terminal state。"""
        fn = _func(_tree(_ROUTER_PY), "_record_callback_metrics")
        attributes = {
            node.attr for node in ast.walk(fn) if isinstance(node, ast.Attribute)
        }
        assert "durable_at" in attributes, (
            "callback 指标没有读 durable_at —— 用 state 名单判耐久是 AC 5.4 明令禁止的"
        )

    def test_no_metric_emission_uses_a_defaulted_getattr(self) -> None:
        """`getattr(outcome, "x", default)` 会把字段名写错变成「永远记成某一类」。"""
        tree = _tree(_ROUTER_PY)
        for name in (
            "_record_callback_metrics",
            "_record_close_metrics",
            "claim_recovery_case",
            "terminate_recovery_download_only",
        ):
            fn = _func(tree, name)
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "getattr"
                    and len(node.args) >= 3
                ):
                    # `getattr(x, "value", None)` 对枚举取值是安全用法，唯一豁免：
                    # 第二个参数是字面量 "value"。
                    second = node.args[1]
                    if isinstance(second, ast.Constant) and second.value == "value":
                        continue
                    raise AssertionError(
                        f"{name}() 用了带默认值的 getattr —— 字段名写错会静默"
                        "落到默认分支，而四层静态检查全绿"
                    )


class TestPackageSurface:
    def test_the_new_modules_are_on_the_package_import_surface(self) -> None:
        import app.services.workpaper_sync as pkg

        for symbol in (
            "RedactionPolicy",
            "SyncMetrics",
            "sync_metrics",
            "AlertRuleRegistry",
            "SyncTimelineService",
            "EvidenceRecomputer",
            "derive_required_scenarios",
        ):
            assert symbol in pkg.__all__, f"{symbol} 不在包的对外形态里"
            assert hasattr(pkg, symbol)
