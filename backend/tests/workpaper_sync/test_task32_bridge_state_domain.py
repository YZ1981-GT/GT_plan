# -*- coding: utf-8 -*-
"""Task 32 的**跨文档锚点**：桥状态域必须逐字等于 AC 11.2，键模板必须等于 design。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 32
Requirements: 4.1, 4.10, 5.8, 11.1, 11.2, 11.8
Properties: **P46 / P48**（前端判据的文档侧锚点）

═══ 为什么这些判据不能只放在 vitest 里 ═══

前端 spec 只能证明「代码按自己声明的那张表运行」。它无从知道那张表是否还等于
requirements.md 的 AC 11.2 与 design.md 的键模板 —— 而漂移的方向恰恰是**文档改了、
或者作者少抄了一个状态**：那时 vitest 全绿，UI 少一个状态、多一个自造状态，
没有任何判据打红。

更根本的一点：`WP_BRIDGE_AC_11_2_REQUIRED_STATES` 与 `WP_BRIDGE_STATES` 是**同一个人
在同一个文件里**写下的两个常量。在前端拿其中一个去校验另一个是自证（本 spec 反复点名的
第三类假绿）。真源只有 requirements.md，所以判据必须从那里解析。

═══ 本文件锁死的六件事 ═══

1. `WP_BRIDGE_AC_11_2_REQUIRED_STATES` 逐字（含顺序）等于 requirements.md 的 AC 11.2；
2. 追加状态必须在 design.md / requirements.md 里各有出处（禁自造状态）；
3. `WP_BRIDGE_STATE_MODE` / `WP_BRIDGE_STATE_TEXT` 的键集逐项等于状态域；
4. `bridgeStateForOperation` 的 `case` 标签逐项等于后端 `OperationState` 枚举；
5. 统一 localStorage 键模板逐字等于 design.md §legacy migration；
6. 旧键正则能匹配源码里**真实存在**的每一个 `*-dual-mode:` 前缀。

另有一条把**已登记的上游缺口**钉成事实：`claim_recovery_case` 只读四个字段，
design 规定的 `expected_generation / expected_write_fence /
expected_definition_bundle_sha256` 声明了但从不校验。桥不得假设它们被强制。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SPEC = (
    _REPO
    / ".kiro"
    / "specs"
    / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
)
_REQUIREMENTS = _SPEC / "requirements.md"
_DESIGN = _SPEC / "design.md"
_FRONTEND = _REPO / "audit-platform" / "frontend" / "src"
_SYNC_DIR = _FRONTEND / "components" / "workpaper" / "sync"
_MACHINE = _SYNC_DIR / "workpaperSyncBridgeMachine.ts"
_STORAGE = _SYNC_DIR / "workpaperSyncModeStorage.ts"
_BRIDGE = _SYNC_DIR / "useWorkpaperSyncBridge.ts"

if str(_REPO / "backend") not in sys.path:
    sys.path.insert(0, str(_REPO / "backend"))

from app.services.workpaper_sync import models as M  # noqa: E402

# ───────────────────────────────────────────────────────────── helpers


def _read(path: Path) -> str:
    assert path.is_file(), f"缺文件：{path.relative_to(_REPO)}"
    # 磁盘真相：并发会话可能刚改过，不经任何缓存层。
    return path.read_text(encoding="utf-8")


def _strip_ts_comments(text: str) -> str:
    """剥掉 TS 行/块注释，保留字符串与模板字面量。

    🔴 必需：本任务的源码注释里**必须**写清「为什么 `applied` 不是 terminal」「为什么
    `error` 没有 reload 边」这类论证，于是状态名会大量出现在注释里。裸 `in` 扫源码的
    反向判据会因此假红；而放宽判据就等于不判。
    """
    out: list[str] = []
    i = 0
    n = len(text)
    quote: str | None = None
    while i < n:
        ch = text[i]
        if quote is not None:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _ts_string_array(code: str, name: str) -> list[str]:
    """取 `export const NAME = [ 'a', 'b' ] as const` 里的字符串序列（保持顺序）。"""
    anchor = f"const {name} = ["
    start = code.find(anchor)
    assert start >= 0, f"{name} 未在源码里声明（或声明形态变了）"
    depth = 0
    i = start + len(anchor) - 1
    end = -1
    while i < len(code):
        if code[i] == "[":
            depth += 1
        elif code[i] == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1
    assert end > start, f"{name} 的数组字面量没有闭合"
    body = code[start + len(anchor) : end]
    return re.findall(r"'([a-z0-9_]+)'", body)


def _ts_record_keys(code: str, name: str) -> list[str]:
    """取 `export const NAME: ... = Object.freeze({ a: ..., b: ... })` 的顶层键。"""
    anchor = f"const {name}"
    start = code.find(anchor)
    assert start >= 0, f"{name} 未在源码里声明"
    brace = code.find("{", start)
    assert brace > 0, f"{name} 后面没有对象字面量"
    depth = 0
    i = brace
    end = -1
    while i < len(code):
        if code[i] == "{":
            depth += 1
        elif code[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1
    assert end > brace, f"{name} 的对象字面量没有闭合"
    body = code[brace + 1 : end]
    keys: list[str] = []
    depth = 0
    for line in body.splitlines():
        stripped = line.strip()
        if depth == 0:
            match = re.match(r"^([a-z][a-z0-9_]*)\s*:", stripped)
            if match:
                keys.append(match.group(1))
        depth += stripped.count("{") + stripped.count("[")
        depth -= stripped.count("}") + stripped.count("]")
        depth = max(depth, 0)
    return keys


@pytest.fixture(scope="module")
def machine_code() -> str:
    return _strip_ts_comments(_read(_MACHINE))


@pytest.fixture(scope="module")
def requirements_text() -> str:
    return _read(_REQUIREMENTS)


@pytest.fixture(scope="module")
def design_text() -> str:
    return _read(_DESIGN)


def _ac_11_2_states(requirements_text: str) -> list[str]:
    """从 requirements.md 的 AC 11.2 抠出 `a / b / c` 形态的状态清单。"""
    line = next(
        (ln for ln in requirements_text.splitlines() if ln.startswith("11.2.")),
        None,
    )
    assert line, "requirements.md 里找不到 AC 11.2"
    quoted = re.findall(r"`([^`]+)`", line)
    assert quoted, f"AC 11.2 没有反引号包裹的状态清单：{line[:120]}"
    states = [chunk.strip() for chunk in quoted[0].split("/")]
    assert all(re.fullmatch(r"[a-z][a-z0-9_]*", s) for s in states), states
    return states


# ═══════════════════════════════════════════════════════════════════════════
# 1. AC 11.2 逐字锚定
# ═══════════════════════════════════════════════════════════════════════════


def test_ac_11_2_state_list_is_parsable_and_non_trivial(requirements_text: str) -> None:
    """分母自证：AC 11.2 真的给出了一份足够长的状态清单。

    没有这一条，AC 解析出空列表时下面每条判据都会「恒成立」。
    """
    states = _ac_11_2_states(requirements_text)
    assert len(states) >= 19, f"AC 11.2 只解析出 {len(states)} 个状态：{states}"
    assert len(set(states)) == len(states), f"AC 11.2 状态清单有重复：{states}"


def test_required_state_constant_equals_ac_11_2_verbatim(
    machine_code: str, requirements_text: str
) -> None:
    """`WP_BRIDGE_AC_11_2_REQUIRED_STATES` 必须逐字（含顺序）等于 AC 11.2。"""
    declared = _ts_string_array(machine_code, "WP_BRIDGE_AC_11_2_REQUIRED_STATES")
    assert declared == _ac_11_2_states(requirements_text), (
        "前端登记的 AC 11.2 状态清单与 requirements.md 不一致：\n"
        f"  前端: {declared}\n"
        f"  文档: {_ac_11_2_states(requirements_text)}"
    )


def test_state_domain_covers_every_ac_11_2_state(
    machine_code: str, requirements_text: str
) -> None:
    domain = _ts_string_array(machine_code, "WP_BRIDGE_STATES")
    missing = [s for s in _ac_11_2_states(requirements_text) if s not in domain]
    assert not missing, f"桥状态域缺 AC 11.2 要求的状态：{missing}"


def test_extra_states_each_have_a_document_source(
    machine_code: str, requirements_text: str, design_text: str
) -> None:
    """状态域里超出 AC 11.2 的每一个状态都要在两份文档里找得到出处（禁自造）。"""
    domain = _ts_string_array(machine_code, "WP_BRIDGE_STATES")
    required = set(_ac_11_2_states(requirements_text))
    # 三份 spec 文档都算真源：`close_authorization_stale` / `close_recovery_required`
    # 是 tasks.md（Task 32/34 正文）逐字点名的两个状态，requirements 4.10 里写的是
    # 去掉 `close_` 前缀的协议术语 `authorization_stale/recovery_required`。
    documents = "\n".join([requirements_text, design_text, _read(_SPEC / "tasks.md")])
    # 追加状态的出处：或者文档里出现同名 snake_case 词，或者出现其对应的
    # 后端状态名/协议术语。逐条给出，缺任何一条都要显式裁决。
    known_sources = {
        # design §Frontend 与 AC 4.10 的 close 仲裁两个显式终态
        "close_authorization_stale": "close_authorization_stale",
        "close_recovery_required": "close_recovery_required",
        # AC 4.1 / 5.10 的 operation 形态
        "waiting_application": "waiting_application",
        "application_bound": "application_bound",
        "duplicate": "duplicate",
        # AC 4.1「创建供用户轮询的 operation shell」+ design 文案「已冻结保存请求」
        "forcesave_frozen": "已冻结保存请求",
        # AC 3.7 / Property 11：descriptor 挂载但 onDocumentReady 尚未触发
        "descriptor_mounted": "onDocumentReady",
    }
    for state in domain:
        if state in required:
            continue
        needle = known_sources.get(state)
        assert needle, (
            f"状态 {state} 既不在 AC 11.2 里，也没有登记文档出处 —— "
            "追加状态必须显式裁决，不得自造"
        )
        assert needle in documents, (
            f"状态 {state} 登记的文档出处 {needle!r} 在 requirements/design 里找不到"
        )


def test_mode_and_text_tables_cover_the_domain_exactly(machine_code: str) -> None:
    domain = _ts_string_array(machine_code, "WP_BRIDGE_STATES")
    modes = _ts_record_keys(machine_code, "WP_BRIDGE_STATE_MODE")
    texts = _ts_record_keys(machine_code, "WP_BRIDGE_STATE_TEXT")
    assert sorted(modes) == sorted(domain), (
        f"mode 表键集与状态域不一致：多 {sorted(set(modes) - set(domain))}，"
        f"少 {sorted(set(domain) - set(modes))}"
    )
    assert sorted(texts) == sorted(domain), (
        f"文案表键集与状态域不一致：多 {sorted(set(texts) - set(domain))}，"
        f"少 {sorted(set(domain) - set(texts))}"
    )


def test_recovery_terminals_named_by_design_are_declared(
    machine_code: str, design_text: str
) -> None:
    """design §Frontend 逐字点名的三个 recovery 状态必须都在域里。"""
    domain = set(_ts_string_array(machine_code, "WP_BRIDGE_STATES"))
    for state in ("recovery_pending", "recovery_claiming", "recovery_download_only"):
        assert state in design_text, f"design.md 里找不到 {state}（文档形态变了）"
        assert state in domain, f"桥状态域缺 design 点名的 {state}"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 快照投影 ↔ 后端枚举
# ═══════════════════════════════════════════════════════════════════════════


def test_operation_state_switch_covers_the_backend_enum(machine_code: str) -> None:
    """`bridgeStateForOperation` 的 case 标签逐项等于后端 `OperationState`。

    少一个 ⇒ 那个状态落到 `default` 分支被 fail visible（用户看到「未知状态」）；
    多一个 ⇒ 前端在替一个不存在的后端状态编含义。
    """
    start = machine_code.find("export function bridgeStateForOperation(")
    assert start >= 0, "bridgeStateForOperation 未导出（函数名变了）"
    # 函数体边界：从签名后的第一个 `{` 起做花括号配对（先跳过参数列表与返回类型）。
    paren = machine_code.index("(", start)
    depth = 0
    i = paren
    while i < len(machine_code):
        if machine_code[i] == "(":
            depth += 1
        elif machine_code[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    brace = machine_code.index("{", i)
    depth = 0
    j = brace
    while j < len(machine_code):
        if machine_code[j] == "{":
            depth += 1
        elif machine_code[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    body = machine_code[brace : j + 1]
    labels = set(re.findall(r"case '([a-z_]+)':", body))
    backend = {member.value for member in M.OperationState}
    assert labels == backend, (
        f"投影 case 标签与后端 OperationState 不一致：多 {sorted(labels - backend)}，"
        f"少 {sorted(backend - labels)}"
    )


def test_bridge_terminal_states_are_declared_and_minimal(machine_code: str) -> None:
    terminals = _ts_string_array(machine_code, "WP_BRIDGE_TERMINAL_STATES")
    assert terminals == ["duplicate", "recovery_download_only", "close_recovery_required"]
    # `applied` 不是桥终态：AC 4.5 要求 applied 之后必须按 result revision 重载。
    assert "applied" not in terminals
    # `error` 不是桥终态：AC 5.8 明文 error 可重试。
    assert "error" not in terminals


# ═══════════════════════════════════════════════════════════════════════════
# 3. localStorage 键模板 ↔ design
# ═══════════════════════════════════════════════════════════════════════════


def test_unified_mode_key_template_matches_design(design_text: str) -> None:
    """统一键模板逐字等于 design.md §legacy migration。"""
    assert "workpaper-sync-mode:{entry_id}:{wp_id}:{sheet_key}" in design_text, (
        "design.md 的键模板形态变了 —— 判据必须跟着重新裁决，不得放宽"
    )
    code = _strip_ts_comments(_read(_STORAGE))
    match = re.search(r"WP_SYNC_MODE_KEY_PREFIX = '([^']+)'", code)
    assert match, "workpaperSyncModeStorage.ts 未声明 WP_SYNC_MODE_KEY_PREFIX"
    assert match.group(1) == "workpaper-sync-mode:"
    # 三段必须都参与拼键。
    assert "${entryId}:${wpId}:${sheetKey}" in code, (
        "统一键没有把 entry/wp/sheet 三段都拼进去（AC 11.8）"
    )


def _discover_legacy_prefixes() -> list[str]:
    """扫前端源码，收集真实存在的 `*-dual-mode:` 前缀。"""
    pattern = re.compile(r"STORAGE_PREFIX\s*=\s*'([a-z0-9][a-z0-9-]*-dual-mode:)'")
    found: set[str] = set()
    for path in _FRONTEND.rglob("*"):
        if path.suffix not in (".ts", ".vue"):
            continue
        if "__tests__" in path.parts or "node_modules" in path.parts:
            continue
        for match in pattern.finditer(path.read_text(encoding="utf-8", errors="replace")):
            found.add(match.group(1))
    return sorted(found)


def test_legacy_key_regex_matches_every_real_prefix() -> None:
    """旧键正则必须覆盖源码里真实存在的每一个前缀（禁把扫描收窄成一张名单）。"""
    prefixes = _discover_legacy_prefixes()
    assert len(prefixes) >= 30, f"只发现 {len(prefixes)} 个旧前缀，分母不可信：{prefixes}"
    code = _strip_ts_comments(_read(_STORAGE))
    match = re.search(r"const LEGACY_KEY_RE = /([^/]+)/", code)
    assert match, "workpaperSyncModeStorage.ts 未声明 LEGACY_KEY_RE"
    compiled = re.compile(match.group(1))
    wp_id = "11111111-1111-1111-1111-111111111111"
    unmatched = [p for p in prefixes if not compiled.match(f"{p}{wp_id}")]
    assert not unmatched, f"旧键正则匹配不到这些真实前缀：{unmatched}"
    unmatched_sheet = [p for p in prefixes if not compiled.match(f"{p}{wp_id}:D4-1")]
    assert not unmatched_sheet, f"per-sheet 形态匹配不到：{unmatched_sheet}"


# ═══════════════════════════════════════════════════════════════════════════
# 4. 桥不得开第二个 HTTP 面
# ═══════════════════════════════════════════════════════════════════════════


def test_bridge_never_builds_a_url_or_calls_http_directly() -> None:
    """桥只能经 `workpaperSyncApi`；出现 `/api/` 字面量或 `http.` 调用即失败。

    AC 11.1 明文「业务组件不得自行拼 config/forcesave URL」，design §Frontend 另加
    「业务 composable 不拼 endpoint、localStorage key 或成功文案」。桥自己拼一条 URL
    与业务组件拼是同一个缺陷 —— 而「函数都在」的判据全绿。
    """
    code = _strip_ts_comments(_read(_BRIDGE))
    assert "/api/" not in code, "桥里出现了 /api/ 字面量 —— 路径只能来自生成的路由表"
    assert "onlyoffice-callback" not in code, "桥里出现了 callback 路径"
    for forbidden in ("http.get(", "http.post(", "axios"):
        assert forbidden not in code, f"桥里直接发请求：{forbidden}"
    assert "from './workpaperSyncApi'" in code, "桥没有走唯一 API 面"


def test_bridge_exposes_the_api_surface_design_names() -> None:
    """design §Frontend 列出的公开面必须真的在返回对象里（零消费方即死代码）。"""
    code = _strip_ts_comments(_read(_BRIDGE))
    start = code.rfind("  return {")
    assert start > 0, "桥的返回对象没找到"
    returned = code[start:]
    for name in (
        "switchToOnlyOffice",
        "switchToHtml",
        "retryOperation",
        "listRecoveryCases",
        "claimRecoveryCase",
        "downloadRecoveryArtifact",
        "resolveConflicts",
        "rollbackVersion",
        "canLeave",
        "mode",
        "state",
        "descriptor",
        "operation",
        "recoveryCases",
        "conflicts",
        "lastError",
    ):
        assert name in returned, f"design 点名的公开面 {name} 没有暴露"


# ═══════════════════════════════════════════════════════════════════════════
# 5. 已登记的上游缺口（钉成事实，不得假设被强制）
# ═══════════════════════════════════════════════════════════════════════════


def test_claim_route_still_ignores_the_three_design_declared_fences() -> None:
    """`claim_recovery_case` 只读四个字段 —— 这是**当前事实**，不是期望。

    design §API 规定 claim 可提交 `expected_generation / expected_write_fence /
    expected_definition_bundle_sha256`，但 handler 从不读它们。Task 31 照 design 白名单
    发送并锁死了请求体；Task 32 的状态机因此**不能**假设「错误 bundle/fence 会被拒 ⇒
    三实体保持为 0」——那条只有服务端补齐校验后才成立。

    本判据在服务端开始校验时会打红，那正是要的：缺口关闭时必须重新裁决前端判据，
    而不是让一条早已失效的注释继续留在代码里。
    """
    router_src = _read(_REPO / "backend" / "app" / "routers" / "wp_sync_router.py")
    start = router_src.index("async def claim_recovery_case(")
    end = router_src.index("\n@router", start)
    body = router_src[start:end]
    # 两种真实读法都要收：`payload.get("x")` / `payload["x"]`，以及
    # `_uuid_field(payload, "x")`（少收后者会让判据把两个已校验字段误报成「没读」）。
    read_fields = set(re.findall(r'payload(?:\.get)?[\(\[]"([a-z_]+)"', body)) | set(
        re.findall(r'payload,\s*"([a-z_]+)"', body)
    )
    assert read_fields == {
        "room_id",
        "prior_confirmation_id",
        "participant_id",
        "expected_current_revision",
    }, f"claim handler 读取的字段集变了：{sorted(read_fields)}"
    for never_read in (
        "expected_generation",
        "expected_write_fence",
        "expected_definition_bundle_sha256",
    ):
        assert never_read not in read_fields, (
            f"服务端开始校验 {never_read} 了 —— 上游缺口已关闭，"
            "请重新裁决 useWorkpaperSyncBridge 里对应的注释与判据"
        )


def test_claim_response_still_carries_no_shape_projection() -> None:
    """claim 的 202 响应体没有 shape ⇒ 桥必须读一次 operation 才能定 primary/duplicate。

    这条把「为什么桥在 claim 之后还要打一次 `getOperation`」钉成服务端事实。
    若服务端某天把 `shape` 投影出来，这条会红，那时前端应改成直接消费它。
    """
    router_src = _read(_REPO / "backend" / "app" / "routers" / "wp_sync_router.py")
    start = router_src.index("async def claim_recovery_case(")
    end = router_src.index("\n@router", start)
    body = router_src[start:end]
    ret = body[body.rindex("return {") :]
    keys = set(re.findall(r'"([a-z_]+)":', ret))
    assert keys == {
        "case_id",
        "forcesave_request_id",
        "operation_id",
        "application_id",
        "state",
    }, f"claim 响应键集变了：{sorted(keys)}"
    assert "shape" not in keys
    bridge = _strip_ts_comments(_read(_BRIDGE))
    assert "claimedShape: landed.shape" in bridge, (
        "桥必须用读回来的 operation 形态定终态，不得写死 'primary'"
    )
