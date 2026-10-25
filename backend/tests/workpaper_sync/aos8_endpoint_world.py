# -*- coding: utf-8 -*-
"""Task 8 端点级判据的**世界构件**（harness world）—— 不含任何判据。

spec: workpaper-sync-adopt-overwrite-and-refresh-source · Task 8

═══ 为什么单独一个非 `test_` 模块 ═══

三份判据文件（`test_aos_adopt_endpoint_http.py` 主体 + 伴生件）共用同一套构件：scratch
schema 的 DDL、注入缝替身、会话代理、载体行集、信封解包。`.py` 行数门禁是 **800**，而
「harness + 判据」合起来实测 900+ ⇒ 必须切。切口选在 **harness / 判据** 之间而不是把判据
对半砍 —— 每组「判据 + 它的变异反证」都留在同一文件里（域内纪律）。

本模块**没有** `test_` 前缀 ⇒ pytest 不收集它；由判据文件用**顶层模块名** import
（该目录无 `__init__.py`，pytest 走 `prepend` 模式；写成 `tests.workpaper_sync.…` 会拿到
第二个模块实例，载体常量与替身类当场分家）。

🔴 本模块里的替身**都不是被测对象**：被测链（`compute_adopt_substrate` /
`compute_plan_for_adopt` / `apply_overwrite_deletions` / `verify_plan_digest` /
`mirror_projection_into_store` / `prune_undeclared_rows`）一个都没替，逐条理由见主体文件
docstring 的「注入边界」表。本模块也**一次都没用** `unittest.mock`。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))

#: 载体 provider —— 常量全部现读，本模块零字面量。
#:
#: 🔴 选 `f4.accounts_payable_detail` 是探针逐 adapter 实测的结论（51 条 store-backed）：
#:    需同时满足 ① `store_merge_plan_or_skip` 有 plan 且是**单 item rows** 形态
#:    ② 行枚举器**可枚举**（否则 plan 三清单恒空，8.5 的对账在空集上恒真）
#:    ③ merge 门面签名与 `store_mirror` 的调用形态兼容。f4 是最小的满足者。
from app.services.workpaper_sync import phase5_f4_accounts_payable as CARRIER  # noqa: E402

CARRIER_ADAPTER_ID: str = CARRIER.ADAPTER_ID
CARRIER_ENTRY_ID: str = CARRIER.ENTRY_ID
CARRIER_ITEM_ID: str = CARRIER.STORE_ITEM_ID
CARRIER_IDENTITY_KEY: str = CARRIER.ROW_IDENTITY_STORE_KEY

#: 载体行集：三类差异同时在场，否则 8.5 的对账会在空集上恒真。
#: `KEEP` 两侧都有（updated）· `DROP` 只 store 有（deleted）· `ADD` 只 substrate 有（added）。
KEEP_ID, DROP_ID, ADD_ID = "aos8-keep", "aos8-drop", "aos8-add"

#: scratch schema 里的最小平台表。
#:
#: 🔴 `working_paper_sync_entry_state` / `wp_index` / `projects.is_deleted` /
#:    `working_paper.created_at` 不是「为了让测试过」而加：`_registration` →
#:    `_attach_pilot_adapters` → 四条 pilot attach 会跑生产**唯一**可见性口径
#:    `projection_target_resolution.TARGET_VISIBILITY_SQL`，缺表即 `UndefinedTableError`
#:    逃出端点。列形态照抄真库 `information_schema`（现查），不是凭记忆写的。
STUB_DDL = """
CREATE TABLE projects (
    id UUID PRIMARY KEY,
    name VARCHAR(200) NOT NULL DEFAULT 'stub',
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE wp_index (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    wp_code VARCHAR(50) NOT NULL DEFAULT 'F4',
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE working_paper (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    wp_index_id UUID NOT NULL REFERENCES wp_index(id),
    file_version INTEGER NOT NULL DEFAULT 1,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    content_revision BIGINT NOT NULL DEFAULT 0
);
CREATE TABLE working_paper_sync_entry_state (
    wp_id UUID NOT NULL,
    entry_id VARCHAR(200) NOT NULL,
    current_representation_id UUID NOT NULL,
    representation_generation BIGINT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (wp_id, entry_id)
);
CREATE TABLE checklist_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    wp_id UUID NOT NULL,
    item_id VARCHAR(200) NOT NULL,
    conclusion TEXT,
    remark TEXT,
    wp_ref VARCHAR(200),
    updated_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    content_version INTEGER NOT NULL DEFAULT 1
);
"""


class HarnessError(RuntimeError):
    """harness 自身的前提不成立（不是判据失败）。"""


class InjectedFailure(RuntimeError):
    """8.4 的注入失败。**harness 侧**注入（包一层 session），生产文件一字不改。"""


def err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def carrier_spec() -> Any:
    """载体 store item 的受管行表 spec（现读，不写字面量）。"""
    for spec in CARRIER.managed_row_table_specs():
        if str(getattr(spec, "store_item_id", "")) == CARRIER_ITEM_ID:
            return spec
    raise HarnessError(f"{CARRIER_ITEM_ID} 不在 {CARRIER_ADAPTER_ID} 的受管 spec 清单里")


def carrier_anchor_path() -> str:
    """幽灵行门的锚点业务名字段在 store 行里的 json 路径（现读 spec，不写字面量）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import managed_field_specs

    spec = carrier_spec()
    field_specs = managed_field_specs(spec)
    return str(field_specs[spec.ghost_row_anchor_index][4])


def store_row(identity: str, name: str) -> dict[str, Any]:
    """一条合法 store 行：带身份 + 锚点业务名（业务名为空会被幽灵行门剔除）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import set_json_path

    row: dict[str, Any] = {CARRIER_IDENTITY_KEY: identity}
    spec = carrier_spec()
    if spec.row_section_field:
        row[spec.row_section_field] = spec.row_section_value
    set_json_path(row, carrier_anchor_path(), name)
    return row


def store_payload(*rows: dict[str, Any]) -> str:
    return json.dumps(list(rows), ensure_ascii=False)


def base_store_payload() -> str:
    return store_payload(store_row(KEEP_ID, "甲公司"), store_row(DROP_ID, "乙公司"))


def base_substrate_payload() -> str:
    return store_payload(store_row(KEEP_ID, "甲公司（在线编辑改过）"), store_row(ADD_ID, "丙公司"))


def identities_of(payload: str | None) -> tuple[str, ...]:
    """从 store 载荷取身份序列（保序）。判据侧的**独立**读法，不复用生产 reader。"""
    if not payload:
        return ()
    return tuple(str(row.get(CARRIER_IDENTITY_KEY) or "") for row in json.loads(payload))


def identities_in_store(rows: list[dict[str, Any]]) -> tuple[str, ...]:
    for row in rows:
        if row["item_id"] == CARRIER_ITEM_ID:
            return identities_of(row["remark"])
    return ()


# ═══════════════════════════════════════════════════════════════════════════════
# 信封解包（平台 `ResponseWrapperMiddleware` 是对外契约的一部分）
# ═══════════════════════════════════════════════════════════════════════════════


def unwrap(body: Any) -> Any:
    """2xx：`{code,message,data}` ⇒ 取 `data`；未包装时原样返回（同前端 `data?.data ?? data`）。"""
    if isinstance(body, dict) and "data" in body and "code" in body:
        return body["data"]
    return body


def error_detail(body: Any) -> dict[str, Any]:
    """4xx/5xx：`detail`（裸 FastAPI）或 `message`（被中间件包过）里的那个 dict。"""
    if not isinstance(body, dict):
        return {}
    for key in ("detail", "message"):
        value = body.get(key)
        if isinstance(value, dict):
            return value
    return {}


def error_code(body: Any) -> str:
    return str(error_detail(body).get("error_code") or "")


# ═══════════════════════════════════════════════════════════════════════════════
# 注入缝替身（逐个都是协议实现体 / 外部端口，不是被测对象）
# ═══════════════════════════════════════════════════════════════════════════════


class Switchboard:
    """visibility / workflow lock / action 的可翻开关（`ProjectVisibilityProbe` 协议实现）。

    刻意**不返回硬编码 True**：`workflow_locked` 有真实的否定侧（Requirement 6.2），
    `authorize` 复用生产词汇表 `_KNOWN_ACTIONS` 而不是恒 True —— 否则「未登记 action 一律
    403」这条 fail-closed 判据在本文件里就被绕过了。
    """

    def __init__(self) -> None:
        self.project_visible = True
        self.workflow_locked = False
        self.probe_calls: list[str] = []
        self.authorize_calls: list[str] = []

    async def observe(self, *, project_id: Any, wp_id: Any, entry_id: str) -> dict[str, Any]:
        self.probe_calls.append(f"{wp_id}/{entry_id}")
        return {
            "project_visible": self.project_visible,
            "workflow_locked": self.workflow_locked,
            "readonly": self.workflow_locked,
        }

    def authorize(self, scope: Any) -> bool:
        from app.routers.wp_sync_router import _KNOWN_ACTIONS

        self.authorize_calls.append(str(scope.action))
        return str(scope.action) in _KNOWN_ACTIONS


class StubRegistry:
    """registry 的**查询面**替身。`_attach_pilot_adapters` 照旧真跑（四条 pilot attach）。

    🔴 只替 `register_from_manifest` / `assert_bidirectional_ready` 两件：前者覆盖 186 条
    entry，实测 25~30s 且与本任务判据无关；后者返回本 harness 现算装配的 registration。
    `registrations()` 返回空元组 ⇒ 四条 pilot attach 会真的去查库（scratch schema 里
    `working_paper_sync_entry_state` 无行 ⇒ 各自 `return ()`），这一段没有被短路。
    """

    manifest_entries: tuple[Any, ...] = ()

    def __init__(self) -> None:
        self.registration: Any = None
        self.registry_error: BaseException | None = None
        self.ready_calls: list[str] = []

    def registrations(self) -> tuple[Any, ...]:
        return ()

    def register(self, registration: Any) -> None:
        return None

    async def register_from_manifest(self, *, session: Any) -> Any:
        return SimpleNamespace(registered_adapter_ids=(), reasons={})

    def assert_bidirectional_ready(self, entry_id: str) -> Any:
        self.ready_calls.append(str(entry_id))
        if self.registry_error is not None:
            raise self.registry_error
        return self.registration


class StubResolution:
    """`substrate` 解析端口。**真** `_resolve_published_substrate` 照旧跑在它上面。

    三态与生产一致：① 指针缺失 ⇒ `EntryPointerMissingError`（生产翻成 409）
    ② 指针在但文件缺失 ⇒ 返回一个不存在的路径（生产 `is_file()` 判定后 409）
    ③ 正常 ⇒ 返回真实存在的临时文件。
    """

    def __init__(self, artifact: Path) -> None:
        self.artifact = artifact
        self.mode = "ok"
        #: 🔴 `compute_adopt_substrate` 的 `adapter_id` 取自**解析结果**（已发布 representation
        #:    的 adapter），不是 registration ——  它决定 `mirror_projection_into_store` 分发到
        #:    哪个 provider。首版把它写死成 f4，于是多 item 场景的 merge 写进了 `F4-6-rows`
        #:    （真库实测：多 item wp 上凭空多出一行 f4 的 store）。这是 harness 缺陷不是生产缺陷，
        #:    但它坐实了「adapter_id 的真源在 resolution 侧」这条形态。
        self.adapter_id = CARRIER_ADAPTER_ID
        self.calls: list[str] = []

    async def resolve(
        self,
        *,
        intent: Any,
        project_id: Any,
        wp_id: Any,
        entry_id: str,
        expected_document_type: str,
    ) -> Any:
        from app.services.workpaper_sync.resolution import EntryPointerMissingError

        self.calls.append(f"{intent}/{entry_id}/{expected_document_type}")
        if self.mode == "pointer_missing":
            raise EntryPointerMissingError(f"entry {entry_id!r} 无 representation 指针（harness）")
        path = self.artifact if self.mode == "ok" else self.artifact.with_name("__absent__.xlsx")
        return SimpleNamespace(
            artifact_path=path,
            artifact_relative_path=f"storage/{path.name}",
            artifact_sha256="0" * 64,
            adapter_id=self.adapter_id,
        )


class StubAdapter:
    """artifact → Projection 的适配边界。返回的是**真** `Projection`（真引擎现算）。"""

    def __init__(self, contract: Any) -> None:
        self.contract = contract
        self.payload = store_payload()
        self.calls = 0

    def extract(self, *, artifact: Any, contract: Any) -> Any:
        self.calls += 1
        return CARRIER.build_store_projection(self.payload, contract=contract)


def is_store_write(sql: str) -> bool:
    head = " ".join(sql.split()).upper()
    return ("UPDATE CHECKLIST_RESPONSES" in head) or ("INSERT INTO CHECKLIST_RESPONSES" in head)


class InjectingSession:
    """会话薄代理：按「已观测到第 N 次 store 写」或「审计将写」注入失败（Task 8.4）。

    🔴 注入落在 **harness 侧**（我们自己 override 的 `get_db` 产出的对象），生产文件一字不改，
    也没有 `monkeypatch.setattr` —— 本域有并发会话，改共用模块的行为在窗口期内会影响别人。

    🔴 注入点由「真实发生过的写」定位，不是猜语句序号：`fail_after_store_writes=1` 就是
    「merge 的那条 UPDATE 已经执行完」（business 写后），`=2` 是「删除侧那条 UPDATE 已经执行完」
    （删除侧后）。`fail_before_audit=True` 在 `session.add(AuditLogEntry)` 处抛（审计前）。
    三者都在 `compute_adopt_substrate` 的统一 `commit()` **之前** —— `commits == 0` 是它的实测证据。
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.store_writes = 0
        self.commits = 0
        self.rollbacks = 0
        self.fail_after_store_writes: int | None = None
        self.fail_before_audit = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        result = await self._inner.execute(statement, *args, **kwargs)
        if is_store_write(str(statement)):
            self.store_writes += 1
            if self.store_writes == self.fail_after_store_writes:
                raise InjectedFailure(
                    f"注入：第 {self.store_writes} 次 store 写之后失败（commit 之前）"
                )
        return result

    def add(self, instance: Any, *args: Any, **kwargs: Any) -> Any:
        if self.fail_before_audit and type(instance).__name__ == "AuditLogEntry":
            raise InjectedFailure("注入：审计留痕之前失败（commit 之前）")
        return self._inner.add(instance, *args, **kwargs)

    async def commit(self) -> None:
        self.commits += 1
        await self._inner.commit()

    async def rollback(self) -> None:
        self.rollbacks += 1
        await self._inner.rollback()


# ═══════════════════════════════════════════════════════════════════════════════
# AST 取件（Task 8.1 的状态码映射表现算工具；铁律 ㉖：一律 AST，禁文本 `in`）
#
# 🔴 工具放在这里、判据与它的变异反证留在判据文件里 —— 与域内先例
#    （`test_aos_adopt_plan_wiring` 当共用工具箱）同一处置。
# ═══════════════════════════════════════════════════════════════════════════════

ROUTER_PY = _BACKEND / "app" / "routers" / "wp_sync_router.py"


def router_ast() -> Any:
    import ast

    return ast.parse(ROUTER_PY.read_text(encoding="utf-8"))


def func_ast(tree: Any, name: str) -> Any:
    import ast

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} 不在 {ROUTER_PY.name} 里")


def http_statuses(node: Any) -> tuple[int, ...]:
    """一段 AST 里 `HTTPException(status_code=<int>)` 的字面量（AST，不是文本匹配）。"""
    import ast

    out: list[int] = []
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        callee = getattr(inner.func, "id", getattr(inner.func, "attr", ""))
        if callee != "HTTPException":
            continue
        for kw in inner.keywords:
            if kw.arg == "status_code" and isinstance(kw.value, ast.Constant):
                out.append(int(kw.value.value))
    return tuple(out)


def handler_except_map(handler: Any) -> tuple[tuple[str, tuple[int, ...]], ...]:
    import ast

    rows: list[tuple[str, tuple[int, ...]]] = []
    for node in ast.walk(handler):
        if not isinstance(node, ast.Try):
            continue
        for clause in node.handlers:
            target = clause.type
            if isinstance(target, ast.Name):
                names = (target.id,)
            elif isinstance(target, ast.Tuple):
                names = tuple(getattr(e, "id", "?") for e in target.elts)
            else:
                names = ("<bare>",)
            rows.append((",".join(names), http_statuses(clause)))
    return tuple(rows)


def reachable_statuses(tree: Any) -> dict[int, tuple[str, ...]]:
    """本端点**可达**的状态码 → 产生点（全部现算，禁写死）。"""
    from app.services.workpaper_sync.endpoint_guard import _REFUSAL_STATUS

    out: dict[int, list[str]] = {}
    for exc, codes in handler_except_map(func_ast(tree, "adopt_substrate")):
        for code in codes:
            out.setdefault(code, []).append(f"handler:except {exc}")
    for family, status in _REFUSAL_STATUS.items():
        out.setdefault(status, []).append(f"guard:{family.__name__}")
    for helper in ("_registration", "_not_found", "_forbidden"):
        for code in set(http_statuses(func_ast(tree, helper))):
            out.setdefault(code, []).append(f"router:{helper}")
    return {code: tuple(sites) for code, sites in sorted(out.items())}


# ═══════════════════════════════════════════════════════════════════════════════
# 多 item 载体（Task 8.4 的「覆盖多 item 场景」）
#
# 🔴 为什么另取一个 adapter：`f4` 在 `store_mirror` 的单 item 分支下**只会写 1 个** item
#    （它只镜像 `bridge.STORE_ITEM_ID`），于是「多 item 之间的部分写入」这一事故形态在它上面
#    根本构不出来。`f3.notes_payable_detail` 现算 **5** 个 store item 且删除侧逐 item 各发
#    一条 UPDATE ⇒ 注入点落在第 k 条时，后面几条 item 的删除还没发生 = 真正的部分写入。
# ═══════════════════════════════════════════════════════════════════════════════

from app.services.workpaper_sync import phase5_f3_notes_payable as MULTI  # noqa: E402

MULTI_ADAPTER_ID: str = MULTI.ADAPTER_ID
MULTI_ENTRY_ID: str = MULTI.ENTRY_ID


def multi_specs() -> dict[str, Any]:
    """多 item 载体的 `item_id → spec`（现读，不写字面量）。"""
    return {
        str(getattr(spec, "store_item_id", "")): spec
        for spec in MULTI.managed_row_table_specs()
    }


def row_for_spec(spec: Any, identity: str, name: str) -> dict[str, Any]:
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        managed_field_specs,
        set_json_path,
    )

    row: dict[str, Any] = {spec.row_identity_key: identity}
    if spec.row_section_field:
        row[spec.row_section_field] = spec.row_section_value
    field_specs = managed_field_specs(spec)
    set_json_path(row, str(field_specs[spec.ghost_row_anchor_index][4]), name)
    return row


def multi_store_payloads() -> dict[str, str]:
    """多 item 载体的 store 侧载荷：每个 item 都有 KEEP（将被更新）+ DROP（将被删）。"""
    return {
        item: store_payload(
            row_for_spec(spec, KEEP_ID, "甲公司"), row_for_spec(spec, DROP_ID, "乙公司")
        )
        for item, spec in multi_specs().items()
    }


class MultiStubAdapter:
    """多 item 载体的 extract：逐 item 建**真** Projection 后按真类合并成一份。

    合并形态照抄 dual-store provider 的 combined projection（`values` 并集 + `row_keys` 并集），
    用的是真 `Projection` 类，不是同形替身。
    """

    def __init__(self, contract: Any) -> None:
        self.contract = contract
        self.calls = 0

    def extract(self, *, artifact: Any, contract: Any) -> Any:
        from app.services.workpaper_sync.adapters.base import Projection

        self.calls += 1
        values: dict[str, Any] = {}
        row_keys: dict[str, tuple[str, ...]] = {}
        for item, spec in multi_specs().items():
            payload = store_payload(
                row_for_spec(spec, KEEP_ID, "甲公司（在线编辑改过）"),
                row_for_spec(spec, ADD_ID, "丙公司"),
            )
            projection = MULTI.build_store_projection(
                payload, contract=contract, store_item_id=item
            )
            values.update(projection.values)
            row_keys.update(projection.row_keys)
        return Projection(
            contract_id=contract.contract_id,
            semantic_version=contract.semantic_version,
            document_type=contract.document_type,
            values=values,
            row_keys=row_keys,
        )


async def collect_multi_item_scenarios(ctx: Any) -> None:
    """跑多 item 载体的两个场景（正向对照 + 删除侧中途注入）。

    落在世界模块只因**行数门禁**（主体 harness 装不下）；它仍是采集的一部分，判据在
    `test_aos_adopt_endpoint_injection_and_atomicity.py` 的 §4。`ctx` 是主体 `_collect`
    的闭包门面（session 读写 / 两个 client / 替身 / 场景表），本函数不自己建任何连接。
    """
    from app.services.workpaper_sync.contracts import load_contract

    multi_contract = load_contract(MULTI_ADAPTER_ID)
    multi_adapter = MultiStubAdapter(multi_contract)
    for name, fail_writes in (
        ("multi_item_positive_control", None),
        ("multi_item_inject_mid_deletion", 3),
    ):
        try:
            wp = ctx.wps[name]
            payloads = multi_store_payloads()
            await ctx.seed_many(wp, payloads)
            before = await ctx.read_store(wp)
            audit_before = await ctx.audit_rows()
            ctx.registry.registration = SimpleNamespace(
                adapter_id=MULTI_ADAPTER_ID, contract=multi_contract, adapter=multi_adapter
            )
            # 🔴 `adapter_id` 的真源在 resolution 侧（见 StubResolution.adapter_id 的注释）。
            ctx.resolution.adapter_id = MULTI_ADAPTER_ID
            ctx.injector["fail_writes"] = fail_writes
            picked = ctx.client_5xx if fail_writes is not None else ctx.client
            resp = await picked.post(ctx.url(wp, MULTI_ENTRY_ID), json={"dry_run": False})
            try:
                body: Any = resp.json()
            except ValueError:
                body = {"_text": resp.text[:200]}
            session = ctx.injector["session"]
            ctx.scen[name] = {
                "wp": str(wp),
                "status": resp.status_code,
                "body": body,
                "raised": None,
                "seeded_items": sorted(payloads),
                "store_before": before,
                "store_after": await ctx.read_store(wp),
                "audit_before": audit_before,
                "audit_after": await ctx.audit_rows(),
                "store_writes": getattr(session, "store_writes", None),
                "commits": getattr(session, "commits", None),
                "rollbacks": getattr(session, "rollbacks", None),
            }
        except Exception as exc:  # noqa: BLE001 - 记录不穿透
            ctx.phase_failed(name, exc)
        finally:
            ctx.injector["fail_writes"] = None
            ctx.resolution.adapter_id = CARRIER_ADAPTER_ID
            ctx.registry.registration = SimpleNamespace(
                adapter_id=CARRIER_ADAPTER_ID,
                contract=ctx.carrier_contract,
                adapter=ctx.carrier_adapter,
            )


async def collect_stale_by_store_change_scenario(ctx: Any) -> None:
    """tasks.md 8.2 逐字要求的那一种过期：**改动 store 使 digest 过期**，再带旧 digest 执行。

    与「直接送一个错 digest」不是同一件事：这里服务端重算值是被**真实数据变化**推动的
    （用户看摘要与按确认之间别人动了几行），而那才是 Requirement 3.4 要防的场景。
    两种都留：错 digest 证「门在」，本场景证「门为什么存在」。
    """
    name = "digest_stale_by_store_change"
    try:
        wp = ctx.wps[name]
        await ctx.seed_store(wp, base_store_payload())
        first = await ctx.client.post(ctx.url(wp), json={"dry_run": True})
        old_digest = str(unwrap(first.json()).get("plan_digest") or "")
        # 🔴 第三方在「看摘要」与「按确认」之间动了 store：多出一行 ⇒ 服务端重算的计划变了
        drifted = store_payload(
            store_row(KEEP_ID, "甲公司"),
            store_row(DROP_ID, "乙公司"),
            store_row("aos8-late", "丁公司（别人刚加的）"),
        )
        await ctx.seed_store(wp, drifted)
        after_drift = await ctx.read_store(wp)
        refused = await ctx.client.post(
            ctx.url(wp), json={"dry_run": False, "plan_digest": old_digest}
        )
        after_refused = await ctx.read_store(wp)
        second = await ctx.client.post(ctx.url(wp), json={"dry_run": True})
        new_digest = str(unwrap(second.json()).get("plan_digest") or "")
        accepted = await ctx.client.post(
            ctx.url(wp), json={"dry_run": False, "plan_digest": new_digest}
        )
        ctx.scen[name] = {
            "wp": str(wp),
            "old_digest": old_digest,
            "new_digest": new_digest,
            "refused_status": refused.status_code,
            "refused_body": refused.json(),
            "accepted_status": accepted.status_code,
            "accepted_body": accepted.json(),
            "store_after_drift": after_drift,
            "store_after_refused": after_refused,
            "store_after_accepted": await ctx.read_store(wp),
        }
    except Exception as exc:  # noqa: BLE001 - 记录不穿透
        ctx.phase_failed(name, exc)
