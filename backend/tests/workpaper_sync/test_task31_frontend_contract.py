# -*- coding: utf-8 -*-
"""Task 31 的**后端侧**判据：前端 contract 生成物必须与真实 router / 枚举逐项一致。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 31
Requirements: 3.1, 3.6, 3.7, 5.8, 11.2, 11.4, 11.5, 11.6, 11.11
Properties: **P10 / P11 / P47**（前端侧的服务端锚点）

═══ 为什么判据要落在**后端** ═══

前端的 vitest 只能证明「客户端按 contract 里写的那样调用」；它无从知道 contract 本身
是否还等于后端。漂移方向恰恰是后端改了而生成物没跟上 —— 于是 vitest 全绿、生产恒 404。
本文件把生成物钉回三个真源：

* `wp_sync_router.router.routes` —— 路由模板与方法（含 `entry_id:path` 转换器）；
* FastAPI 解出的 dependant —— `Idempotency-Key` 是否**服务端强制**；
* `workpaper_sync.models` 的 Enum / `TERMINAL_STATES` —— 状态封闭域。

外加 `EditorLaunchDescriptor.confirm_payload()` 的**真实调用结果**（不是 AST 扫源码）。

═══ 反向自检 ═══

每条判据都必须能被「把生成器改错一处」打红。`test_generated_file_is_fresh` 是总闸
（任何字节漂移都红），其余各条按维度分开，这样变异报告能分辨「是路由漂了还是枚举漂了」。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO / "backend" / "scripts" / "gen") not in sys.path:
    sys.path.insert(0, str(_REPO / "backend" / "scripts" / "gen"))

import generate_workpaper_sync_frontend_contract as gen  # noqa: E402

from app.routers import wp_sync_router as SR  # noqa: E402
from app.services.workpaper_sync import models as M  # noqa: E402
from app.services.workpaper_sync.definitions import AuthorityModel  # noqa: E402

_TARGET = gen._TARGET
_FRONTEND_SYNC_DIR = _TARGET.parent


@pytest.fixture(scope="module")
def facts() -> dict[str, Any]:
    return gen.collect_facts()


@pytest.fixture(scope="module")
def generated_text() -> str:
    assert _TARGET.is_file(), (
        f"生成物不存在：{_TARGET.relative_to(_REPO)} —— 跑 "
        "`py -3 backend/scripts/gen/generate_workpaper_sync_frontend_contract.py --apply`"
    )
    return _TARGET.read_text(encoding="utf-8")


def _strip_ts_comments(text: str) -> str:
    """去掉 TS 的行注释与块注释，保留字符串/模板字面量内容。

    🔴 存在的理由：`workpaperSyncApi.ts` 的模块 docstring 里**必须**写清「为什么没有
    callback 调用面」，于是 `onlyoffice-callback` 这个词组会出现在注释里。用裸
    `in` 扫源码的反向判据会因此假红，而放宽成「不扫 .ts 只扫生成物」又会漏掉真正的
    风险面（客户端拼了这个路径）。所以先剥注释，再扫代码。

    字符串状态机是必需的：`'https://x'` 里的 `//` 不是注释起点。
    """
    out: list[str] = []
    index = 0
    length = len(text)
    quote: str | None = None
    while index < length:
        char = text[index]
        if quote is not None:
            out.append(char)
            if char == "\\" and index + 1 < length:
                out.append(text[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in ("'", '"', "`"):
            quote = char
            out.append(char)
            index += 1
            continue
        if char == "/" and index + 1 < length and text[index + 1] == "/":
            while index < length and text[index] != "\n":
                index += 1
            continue
        if char == "/" and index + 1 < length and text[index + 1] == "*":
            index += 2
            while index + 1 < length and not (text[index] == "*" and text[index + 1] == "/"):
                index += 1
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _ts_array(text: str, const_name: str) -> Any:
    """从生成的 TS 里取一个 `export const NAME[: Type] = [...] as const` 的字面量。

    只认**行首**的 `export const NAME`，并按括号配对取到闭合处 —— 不用固定字符窗口，
    也不用 `index()` 算边界（本 spec 已为字符窗口付过代价）。类型注解可选：
    `WP_SYNC_REJECTION_STATUS` 带 `: Readonly<Record<string, number>>`，写死
    `NAME = ` 的正则会零命中并把判据变成「找不到就红」的假红。
    """
    match = re.search(
        rf"^export const {re.escape(const_name)}(?::[^=\n]+)? = ", text, re.M
    )
    assert match, f"生成物里找不到 `export const {const_name}`"
    start = match.end()
    assert text[start] in "[{", (
        f"{const_name} 的右值以 {text[start]!r} 开头 —— 期望数组或对象字面量"
    )
    opener = text[start]
    closer = "]" if opener == "[" else "}"
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return json.loads(text[start : index + 1])
    raise AssertionError(f"{const_name} 的字面量没有闭合")


def _ts_string(text: str, const_name: str) -> str:
    match = re.search(rf'^export const {re.escape(const_name)} = "([^"]*)"', text, re.M)
    assert match, f"生成物里找不到字符串常量 `{const_name}`"
    return match.group(1)


def _ts_union(text: str, type_name: str) -> list[str]:
    """取一个 `export type NAME = "a" | "b"` 的字面量联合成员（保持声明顺序）。

    只作类型约束的域用联合发射（运行时无人读数组 ⇒ 发数组就是死代码）。
    """
    match = re.search(rf"^export type {re.escape(type_name)} = (.+)$", text, re.M)
    assert match, f"生成物里找不到字面量联合类型 `{type_name}`"
    members = [chunk.strip() for chunk in match.group(1).split("|")]
    return [json.loads(chunk) for chunk in members]


# ═══════════════════════════════════════════════════════════════════════════
# 1. 总闸：生成物新鲜
# ═══════════════════════════════════════════════════════════════════════════


def test_generated_file_is_fresh(facts: dict[str, Any], generated_text: str) -> None:
    """磁盘上的生成物必须逐字节等于重新渲染的结果（source digest fail-closed）。"""
    assert generated_text == gen.render(facts), (
        "前端 contract 生成物与真实 router / 枚举不一致；跑 "
        "`py -3 backend/scripts/gen/generate_workpaper_sync_frontend_contract.py --apply`"
    )


def test_check_mode_agrees_with_the_stored_artifact() -> None:
    """`--check` 必须对当前磁盘状态返回 0（CI 用的正是这条路径）。"""
    assert gen.main(["--check"]) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 2. 路由维度
# ═══════════════════════════════════════════════════════════════════════════


def test_route_table_covers_every_real_user_route(generated_text: str) -> None:
    """生成的路由表 = router 的**全部**用户路由，一条不多一条不少。

    少一条 ⇒ 该端点前端永远打不到；多一条 ⇒ 前端会打出一个统一 404，
    而调用点分辨不出「没这个端点」与「无权限」。
    """
    routes = _ts_array(generated_text, "WP_SYNC_ROUTES")
    generated = {(r["method"], r["suffix"]) for r in routes}
    real = set()
    for route in SR.router.routes:
        methods = sorted(m for m in route.methods if m not in ("HEAD", "OPTIONS"))
        assert len(methods) == 1, f"{route.path} 声明了 {methods}"
        real.add((methods[0], route.path[len(SR.USER_SYNC_PREFIX) :]))
    assert generated == real, (
        f"生成物少了 {sorted(real - generated)}，多了 {sorted(generated - real)}"
    )
    assert len(routes) == len(SR.router.routes)


def test_prefix_template_drops_the_path_converter_but_keeps_all_three_scope_segments(
    generated_text: str,
) -> None:
    """前缀模板去掉 `:path` 语法，但 project/wp/entry 三段必须都在。

    🔴 `:path` 是 Starlette 的转换器语法，不是 URL 的一部分；把它留在模板里，前端会拼出
    `.../entries/{entry_id:path}` 的字面量。反之若前端把 entry 段 percent-encode，
    Starlette 解出的 `entry_id` 就不等于原值 —— Task 28 的变异 B01 已证明默认转换器下
    每一个端点恒 404。
    """
    template = _ts_string(generated_text, "WP_SYNC_USER_PREFIX_TEMPLATE")
    assert ":path" not in template, template
    for segment in ("{project_id}", "{wp_id}", "{entry_id}"):
        assert segment in template, f"前缀模板缺 {segment}：{template}"
    assert template + "" == SR.USER_SYNC_PREFIX.replace("{entry_id:path}", "{entry_id}")


def test_the_real_router_still_uses_the_path_converter() -> None:
    """反向自检：生成器去掉 `:path` 的前提是 router 真的用了它。"""
    assert "{entry_id:path}" in SR.USER_SYNC_PREFIX


def test_a_real_slashed_entry_id_still_routes_through_the_generated_template() -> None:
    """把生成的模板按前端规则填成 URL，必须唯一命中路由且解出原值。

    这是**行为侧**判据：模板字符串「长得对」在两种转换器下都成立，只有真跑一次路由匹配
    才能证明多段 entry_id 不会被吞掉后缀。
    """
    import uuid

    template = _ts_string(_TARGET.read_text(encoding="utf-8"), "WP_SYNC_USER_PREFIX_TEMPLATE")
    project, wp = uuid.uuid4(), uuid.uuid4()
    room, op, case, version = (uuid.uuid4() for _ in range(4))
    for entry in (
        "xlsx/gt-d2-accounts-receivable",
        "xlsx/d4/analysis/d4-tab-customer-price",
        "docx/gt-a10-bundle",
    ):
        base = (
            template.replace("{project_id}", str(project))
            .replace("{wp_id}", str(wp))
            .replace("{entry_id}", entry)
        )
        for spec in _ts_array(_TARGET.read_text(encoding="utf-8"), "WP_SYNC_ROUTES"):
            suffix = (
                spec["suffix"]
                .replace("{room_id}", str(room))
                .replace("{operation_id}", str(op))
                .replace("{case_id}", str(case))
                .replace("{version_id}", str(version))
            )
            assert "{" not in suffix, suffix
            scope = {
                "type": "http",
                "method": spec["method"],
                "path": base + suffix,
                "headers": [],
            }
            hits = []
            for route in SR.router.routes:
                match, child = route.matches(scope)
                if match.name == "FULL":
                    hits.append((route.endpoint.__name__, child.get("path_params", {})))
            assert len(hits) == 1, (
                f"{spec['endpoint']} 用 entry={entry!r} 命中 {[h[0] for h in hits]} —— 应恰好 1 条"
            )
            assert hits[0][1].get("entry_id") == entry, (
                f"{spec['endpoint']} 解出的 entry_id={hits[0][1].get('entry_id')!r} ≠ {entry!r}"
            )


def test_idempotency_key_projection_equals_the_dependant_truth(
    generated_text: str,
) -> None:
    """`required` 标记必须来自 FastAPI 解出的 dependant，而不是一张手抄名单。

    Task 28 已证明把 `Header(...)` 改成 `Header(default="")` 时零功能测试失败，而后果是
    复合幂等键 `(room, generation, participant, kind, key)` 的最后一项恒为空串。前端若照
    一张手抄名单发 header，同一个漂移在前端侧同样静默。
    """
    from fastapi.dependencies.utils import get_dependant

    real_required: set[str] = set()
    for route in SR.router.routes:
        dependant = get_dependant(path=route.path, call=route.endpoint)
        for param in dependant.header_params:
            if str(getattr(param.field_info, "alias", "")) == "Idempotency-Key":
                if bool(param.field_info.is_required()):
                    real_required.add(route.endpoint.__name__)

    projected = set(_ts_array(generated_text, "WP_SYNC_IDEMPOTENT_ENDPOINTS"))
    assert projected == real_required, (
        f"生成的必填集 {sorted(projected)} ≠ router 实际 {sorted(real_required)}"
    )
    routes = {r["endpoint"]: r for r in _ts_array(generated_text, "WP_SYNC_ROUTES")}
    for endpoint in real_required:
        assert routes[endpoint]["idempotencyKey"] == "required", endpoint
    for endpoint, spec in routes.items():
        if endpoint not in real_required:
            assert spec["idempotencyKey"] in ("optional", "absent"), (endpoint, spec)


def test_the_callback_route_is_never_projected_to_the_frontend(
    generated_text: str,
) -> None:
    """callback 是 DocServer 的服务凭证面，且被排除 envelope 包装。

    前端一旦拿到这个路径，就可能去拼一个「自己造 callback」的调用，而它的响应体是顶层
    `{"error": N}`（不是平台 envelope）—— 解包层套上去必然错一层。
    """
    assert SR.public_router.routes, "反向自检：callback 路由本身必须存在"
    callback_path = SR.public_router.routes[0].path
    assert "onlyoffice-callback" in callback_path
    assert "onlyoffice-callback" not in generated_text

    # 反向自检：剥注释器真的在剥（否则下面的循环退化成恒真）。
    probe = "// onlyoffice-callback\nconst kept = '/api/x'\n/* onlyoffice-callback */"
    stripped_probe = _strip_ts_comments(probe)
    assert "onlyoffice-callback" not in stripped_probe, stripped_probe
    assert "'/api/x'" in stripped_probe, stripped_probe

    scanned = 0
    for source in sorted(_FRONTEND_SYNC_DIR.glob("*.ts")):
        code = _strip_ts_comments(source.read_text(encoding="utf-8"))
        assert "onlyoffice-callback" not in code, (
            f"{source.name} 的**代码**里出现了 callback 路径 —— 前端不得拼它"
        )
        scanned += 1
    assert scanned >= 3, f"只扫到 {scanned} 个 .ts —— 判据的分母不对"


# ═══════════════════════════════════════════════════════════════════════════
# 3. 状态封闭域
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("const_name", "enum_name"),
    [
        ("WP_SYNC_OPERATION_STATES", "OperationState"),
        ("WP_SYNC_ROOM_STATES", "RoomState"),
        ("WP_SYNC_RECOVERY_CASE_STATES", "RecoveryCaseState"),
        ("WP_SYNC_RECOVERY_REASONS", "RecoveryReason"),
    ],
    ids=["operation_state", "room_state", "recovery_case_state", "recovery_reason"],
)
def test_closed_domain_equals_the_backend_enum(
    const_name: str, enum_name: str, generated_text: str
) -> None:
    """封闭域必须逐项等于后端 Enum（顺序也一致 —— 顺序是 Enum 的声明顺序）。

    少一个值 ⇒ 前端把它当未知状态 fail visible（或更糟：被兜底）；多一个值 ⇒ 前端为
    一个后端永不返回的状态留了分支，那是死代码。
    """
    projected = _ts_array(generated_text, const_name)
    real = [member.value for member in getattr(M, enum_name)]
    assert projected == real, f"{const_name} 投影 {projected} ≠ {enum_name} 的 {real}"


def test_type_only_domain_equals_the_backend_enum(generated_text: str) -> None:
    """只发类型的域同样要逐项等于后端 Enum。

    `OperationShape` 由 `classifyOperationShape()` 从两个 link 派生、服务端从不下发它，
    所以运行时没有「校验收到的 shape」这回事 ⇒ 发数组常量就是死代码。但类型仍必须与
    后端三态一致，否则前端会给一个后端不存在的 shape 留分支。
    """
    assert _ts_union(generated_text, "WorkpaperSyncOperationShape") == [
        member.value for member in M.OperationShape
    ]


@pytest.mark.parametrize(
    ("const_name", "machine"),
    [("WP_SYNC_OPERATION_TERMINAL_STATES", "operation")],
    ids=["operation"],
)
def test_terminal_set_equals_the_state_machine(
    const_name: str, machine: str, generated_text: str
) -> None:
    """terminal 集来自 `TERMINAL_STATES`（出边为空的状态），不是手挑。

    多挑一个 ⇒ 前端会在非终态上停止等待（显示「完成」）；少挑一个 ⇒ 永远转圈。
    """
    projected = sorted(_ts_array(generated_text, const_name))
    real = sorted(s.value for s in M.TERMINAL_STATES[machine])
    assert projected == real, f"{const_name} 投影 {projected} ≠ {machine} 的 {real}"


def test_operation_terminal_set_is_a_strict_subset_of_the_state_domain(
    generated_text: str,
) -> None:
    """反向自检：terminal 集必须是状态域的真子集且非空。"""
    states = set(_ts_array(generated_text, "WP_SYNC_OPERATION_STATES"))
    terminals = set(_ts_array(generated_text, "WP_SYNC_OPERATION_TERMINAL_STATES"))
    assert terminals and terminals < states, (terminals, states)
    # `error` 不是 terminal —— 它可重试（AC 5.8）。这条是「terminal 集被整体误抄成
    # 状态域」时唯一还能打红的判据。
    assert "error" not in terminals


def test_authority_models_equal_the_backend_enum(generated_text: str) -> None:
    projected = _ts_array(generated_text, "WP_SYNC_AUTHORITY_MODELS")
    assert projected == [m.value for m in AuthorityModel]


def test_no_domain_is_projected_without_a_frontend_consumer(generated_text: str) -> None:
    """每个投影出去的封闭域都必须在前端有**真实**消费方。

    🔴 这条是本 spec「第一类假绿（additive 注入即死代码）」的正面判据：投影一个没人读的
    常量，静态检查全绿、测试全绿，而它永远不会被发现是死的。participant state/mode 与
    request kind 不在响应里出现，故刻意不投影 —— 哪天有人把它们加回来，这条会打红并
    要求先给出消费方。
    """
    dto = (_FRONTEND_SYNC_DIR / "workpaperSyncDto.ts").read_text(encoding="utf-8")
    api = (_FRONTEND_SYNC_DIR / "workpaperSyncApi.ts").read_text(encoding="utf-8")
    tracker = (_FRONTEND_SYNC_DIR / "workpaperSyncOperationTracker.ts").read_text(
        encoding="utf-8"
    )
    consumers = _strip_ts_comments(dto + api + tracker)

    exported = set(re.findall(r"^export const (WP_SYNC_[A-Z0-9_]+)", generated_text, re.M))
    # 只有 digest 是纯新鲜度标记（无运行时消费方，与既有 manifest 生成物同例）。
    marker_only = {"WP_SYNC_CONTRACT_DIGEST"}
    # 判据的分母来自测试侧：它驱动参数化，是「真实消费方」的另一种形态。
    test_only = {"WP_SYNC_IDEMPOTENT_ENDPOINTS"}
    orphans = sorted(
        name
        for name in exported - marker_only - test_only
        if name not in consumers
    )
    assert not orphans, (
        f"这些常量被投影到前端但生产代码零消费：{orphans} —— 先给出消费方再投影"
    )
    assert len(exported) >= 8, f"只解析出 {len(exported)} 个导出常量 —— 判据分母不对"
    for name in sorted(test_only):
        specs = "".join(
            p.read_text(encoding="utf-8")
            for p in sorted((_FRONTEND_SYNC_DIR / "__tests__").glob("workpaperSync*.spec.ts"))
        )
        assert name in specs, f"{name} 连测试侧也没消费方"


# ═══════════════════════════════════════════════════════════════════════════
# 4. descriptor identity
# ═══════════════════════════════════════════════════════════════════════════


def test_descriptor_fields_equal_the_backend_required_list(generated_text: str) -> None:
    from app.services.workpaper_sync.materialize_coordinator import (
        DESCRIPTOR_REQUIRED_FIELDS,
    )

    assert _ts_array(generated_text, "WP_SYNC_DESCRIPTOR_FIELDS") == list(
        DESCRIPTOR_REQUIRED_FIELDS
    )


def test_confirm_keys_come_from_a_real_confirm_payload_call(generated_text: str) -> None:
    """confirm 回传清单来自**真实调用** `confirm_payload()`，不是扫源码字面量。

    AST 只能证明「源码里写了这些键」；真构造一个合法 descriptor 再调一次，顺手证明了
    `assert_descriptor_mountable` 的判据与本清单自洽 —— 构造不出来就 fail closed，
    而不是投影出一份没人能满足的 identity 清单。
    """
    descriptor = gen._synthetic_descriptor()
    real = sorted(descriptor.confirm_payload())
    assert _ts_array(generated_text, "WP_SYNC_DESCRIPTOR_CONFIRM_KEYS") == real
    assert len(real) == 10, f"design §API 的 confirm 回传是十项，实得 {len(real)}：{real}"


def test_confirm_keys_are_a_subset_of_the_descriptor_response(
    facts: dict[str, Any], generated_text: str
) -> None:
    """反向自检：confirm 回传的每一项都必须能从 descriptor 响应里取到。

    🔴 `content_revision` 是唯一改名项（descriptor 里叫 `server_applied_revision`）——
    显式登记它，否则「回传了一个 descriptor 里根本没有的字段」会被这条判据放过。

    descriptor 响应键集**不投影到前端**（前端无消费方），故这一侧从 `facts` 取 ——
    它由 `EditorLaunchDescriptor.as_dict()` 真调一次得到，与前端投影同源同 digest。
    """
    confirm = set(_ts_array(generated_text, "WP_SYNC_DESCRIPTOR_CONFIRM_KEYS"))
    response = set(facts["descriptor_response_keys"])
    renamed = {"content_revision": "server_applied_revision"}
    for key in confirm:
        source = renamed.get(key, key)
        assert source in response, (
            f"confirm 要回传 {key}，但 descriptor 响应里没有 {source} —— "
            "前端无从取值，只能编一个"
        )
    assert set(renamed) <= confirm


def test_descriptor_response_never_carries_a_signed_document_url(
    facts: dict[str, Any],
) -> None:
    """descriptor 刻意不含签名下载 URL（Task 25/28 的 signature-TTL 论证）。

    把 URL 签进 descriptor 会让签名 TTL 与 descriptor 生命周期绑死：要么签名长到不安全，
    要么 descriptor 提前失效导致 confirm 永远 409。
    """
    response = set(facts["descriptor_response_keys"])
    for forbidden in ("document_url", "url", "download_url", "signed_url"):
        assert forbidden not in response, forbidden
    assert "onlyoffice_config" in response, (
        "反向自检：config 必须在 descriptor 里，否则前端只能再请求一份"
    )


def test_pending_mutation_receipt_never_leaks_a_revision_result(
    facts: dict[str, Any],
) -> None:
    """flush 按定义不产生业务版本（AC 3.1），回执多一个字段就会诱使前端把它当提交。"""
    keys = set(facts["pending_mutation_receipt_keys"])
    assert keys == {
        "pending_mutation_token",
        "expected_revision",
        "payload_sha256",
        "expires_at",
    }, keys
    for forbidden in ("revision", "content_version_id", "representation_id", "operation_id"):
        assert forbidden not in keys, forbidden


def test_descriptor_confirmation_exposes_the_forcesave_gate(facts: dict[str, Any]) -> None:
    """confirm 响应必须带 `forcesave_unlocked` —— 确认成功前不得 forcesave（P11 后半）。"""
    keys = set(facts["descriptor_confirmation_keys"])
    assert "forcesave_unlocked" in keys
    assert "room_state" in keys


# ═══════════════════════════════════════════════════════════════════════════
# 5. 拒绝映射
# ═══════════════════════════════════════════════════════════════════════════


def test_rejection_status_equals_the_single_mapping_point(generated_text: str) -> None:
    """`error_code → status` 必须逐项等于 `MATERIALIZE_REJECTION_STATUS`。

    它是 router 的**唯一**映射点；前端照抄第二份的后果是「422 被显示成 500」之类的
    误导，而两者的处理完全不同（前者是内容/契约不适配，后者是平台内部失败）。
    """
    from app.services.workpaper_sync.materialize_coordinator import (
        MATERIALIZE_REJECTION_STATUS,
    )

    projected = _ts_array(generated_text, "WP_SYNC_REJECTION_STATUS")
    real = {
        str(exc.error_code): int(status)
        for exc, status in MATERIALIZE_REJECTION_STATUS.items()
    }
    assert projected == real, (
        f"投影 {len(projected)} 条、真源 {len(real)} 条；差集 "
        f"{sorted(set(projected) ^ set(real))}"
    )


def test_every_registered_error_code_is_unique_per_exception_type() -> None:
    """反向自检：两个异常类共用一个 `error_code` 会让先到的那条永远不可达。

    这正是本 spec 变异运行三次抓到的守卫缺陷形态；映射表按 `error_code` 建字典，
    重名时后者会静默覆盖前者的状态码。
    """
    from app.services.workpaper_sync.materialize_coordinator import (
        MATERIALIZE_REJECTION_STATUS,
    )

    seen: dict[str, str] = {}
    collisions: list[tuple[str, str, str]] = []
    for exc in MATERIALIZE_REJECTION_STATUS:
        code = str(exc.error_code)
        if code in seen:
            collisions.append((code, seen[code], exc.__name__))
        seen[code] = exc.__name__
    assert not collisions, f"error_code 撞名：{collisions}"


def test_stale_identity_codes_are_both_409(generated_text: str) -> None:
    """陈旧 descriptor / substrate 两个码都必须是 409。

    前端的三门（editing / retryable / forcesave）全关就建立在这个事实上；哪天有一个
    变成 422，「409 不得转成 editing」那条前端判据仍绿，但真实响应已经走另一条分支。
    """
    projected = _ts_array(generated_text, "WP_SYNC_REJECTION_STATUS")
    for code in ("launch_descriptor_stale_identity", "launch_descriptor_substrate_stale"):
        assert projected[code] == 409, (code, projected.get(code))


def test_preflight_family_is_uniformly_422(generated_text: str) -> None:
    """`MaterializePreflightError` 家族是可捕获的 422 族（router 依赖这条分组）。"""
    from app.services.workpaper_sync.materialize_coordinator import (
        MaterializePreflightError,
    )

    projected = _ts_array(generated_text, "WP_SYNC_REJECTION_STATUS")
    subclasses = MaterializePreflightError.__subclasses__()
    assert subclasses, "反向自检：422 族必须有子类"
    for subclass in subclasses:
        assert projected[str(subclass.error_code)] == 422, subclass.__name__


def test_scope_not_visible_maps_to_the_platform_unified_404(generated_text: str) -> None:
    """跨 scope / 不存在都走统一 404（Property 45 的存在性 oracle）。"""
    projected = _ts_array(generated_text, "WP_SYNC_REJECTION_STATUS")
    assert projected["materialize_scope_not_visible"] == 404
    assert projected["materialize_authorization_denied"] == 403
