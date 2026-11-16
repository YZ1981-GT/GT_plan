"""d-cycle 端点 / render 测试替身：跟上现行契约，且不替换被测的门禁与归集逻辑。

spec: .kiro/specs/_archive/71-formula-fetch-and-wp-generation-defect-closure/（R7）

本目录 75 条用例长期红（守卫形同不存在），根因是替身落后于生产代码，不是被测行为错了：

1. **项目鉴权门**：``GET / PUT /api/workpapers/{wp_id}/formulas`` 自 formula-manager-closure
   Task 5.2（ADR-FMC-06）起在函数体内调 ``assert_project_permission``（经 ``wp.project_id``
   反查项目）。edit 级先过归档守卫 ``db.get(Project, project_id)``；管理员分支设 RLS 上下文
   ``session.get_bind()``（SQLite 方言跳过 ``set_config``）。替身补这两个方法，身份用管理员
   —— 门禁代码原样执行，``auth_gate_calls`` 记录它实际触达的会话方法。
2. **直调端点协程的默认值**：``list_formulas`` 的 ``project_id`` / ``sheet_uid`` 默认值是
   ``Query(None)`` 对象（FastAPI 依赖注入才会换成 ``None``）。直调不传 ⇒ ``project_id`` 是
   非 ``None`` 的 ``Query`` 对象 ⇒ 「与反查出的项目不一致」403。直调须显式传 ``None``
   （= 真实请求不带这两个查询参数）。
3. **公式行**：``_formula_to_dict`` 直接读 ORM 全部列（V163 稳定键等）。用 ``SimpleNamespace``
   造行会在每次加列后 AttributeError ⇒ 改用真 ``WpFormula`` 瞬态实例（未入库，缺省列为 None）。
4. **D6 明细归集**：four-table-extraction-entry-completion Task 4 把裸 SQL 换成共享件
   ``aggregate_d_cycle_aux``（ORM 查询 + active dataset + 单一 aux_type）。按 SQL 文本路由的
   替身认不出新查询 ⇒ 归集恒空、``detail_prefill`` 恒缺。render 层用例改为替换**统一入口**
   ``aggregate_d_cycle_aux`` 并记录入参（项目 / 年度 / 循环）；共享件本身由真 SQLite 行的
   用例覆盖（``test_d6_detail_aggregation``）。
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.models.base import ProjectStatus, UserRole
from app.models.core import Project
from app.models.workpaper_models import WpFormula


class _NullSavepoint:
    """``AsyncSession.begin_nested()`` 的替身：enter/exit 均无操作。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeExecuteResult:
    """``AsyncSession.execute`` 结果替身（共享）。

    审计链（``audit_chain.head.read_head`` / ``append_audit_log``）、年度解析、
    成员级别查询各自用不同的取值入口（``.all()`` / ``.scalars()`` / ``.scalar_one_or_none()``
    / ``.mappings()``）—— 少一个就会以 AttributeError 的形式，把「替身不全」伪装成
    「生产回归」。本替身把常用的都覆盖，未知查询一律返回空集合（= 空结果，而非崩溃）。

    用法：``FakeExecuteResult(scalar=..., rows=[...])``。
    """

    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = list(rows or [])

    # 单值入口
    def scalar_one_or_none(self):
        return self._scalar

    def scalar(self):
        return self._scalar

    # 行集合入口
    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return SimpleNamespace(
            all=lambda: list(self._rows),
            first=lambda: (self._rows[0] if self._rows else None),
            unique=lambda: SimpleNamespace(all=lambda: list(self._rows)),
        )

    def mappings(self):
        return SimpleNamespace(
            all=lambda: list(self._rows),
            first=lambda: (self._rows[0] if self._rows else None),
        )


class FakeSessionWriteMixin:
    """替身会话的 **ORM 写侧** 方法（与 ``AuthGateSessionMixin`` 的读侧配对）。

    自 spec ``audit-log-chain-integrity`` 批 B，公式保存是 mandatory 审计调用点：
    ``write_wp_formula_audit`` → ``append_audit_log`` → ``append_entry`` 会
    ``db.add(AuditLogEntry(...))`` 并要求 SAVEPOINT 隔离。这是**审计留痕**，
    不是业务表写回 —— 与 Property 13「锚点保存不写 checklist_responses / parsed_data」
    不冲突。替身把写入登记到 ``added``，不真正落库。

    使用方法：``class _FakeSession(FakeSessionWriteMixin, AuthGateSessionMixin)``，
    并在 ``__init__`` 里调用 ``self._init_write_side()``。
    """

    def _init_write_side(self):
        self.added: list[object] = []

    def add(self, obj):
        self.added.append(obj)

    def add_all(self, objs):
        self.added.extend(objs)

    async def flush(self, *a, **_kw):
        return None

    async def refresh(self, obj, *a, **_kw):
        return None

    async def delete(self, obj):
        return None


class AuthGateSessionMixin:
    """替身会话混入：补 ``get`` / ``get_bind`` / ``begin_nested``，并记录门禁触达。

    ``project_status``：归档守卫读到的项目状态（默认进行中；设为 ``archived`` 可验证 423）。
    """

    project_status: ProjectStatus = ProjectStatus.execution

    @property
    def auth_gate_calls(self) -> list[tuple]:
        calls = self.__dict__.get("_auth_gate_calls")
        if calls is None:
            calls = []
            self.__dict__["_auth_gate_calls"] = calls
        return calls

    async def get(self, model, ident, **_kw):
        self.auth_gate_calls.append(("get", getattr(model, "__name__", str(model)), ident))
        if model is Project:
            # 另给审计年度五级解析读的字段（spec formula-hub-integrity-closure 需求 11.1：底稿公式审计按项目年度补齐）；
            # 全为 None = 项目没有审计年度，载荷不带 year
            # is_deleted：``formula_settings.outbox._fetch_project_year`` 会判项目是否已删
            # （spec formula-global-settings-sync：公式变更 outbox 事件需要年度）
            return SimpleNamespace(id=ident, status=self.project_status, audit_year=None, audit_period_end=None,
                                   audit_period_start=None, wizard_state=None, name=None,
                                   is_deleted=False)
        return None

    def get_bind(self, *_a, **_kw):
        self.auth_gate_calls.append(("get_bind",))
        return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    def begin_nested(self):
        """SAVEPOINT 替身（async context manager，不做任何事）。

        生产侧自 spec ``audit-log-chain-integrity`` 批 B 起，公式审计
        ``write_wp_formula_audit`` 是 mandatory 调用点：审计失败即业务失败，
        故写审计时 ``async with db.begin_nested():`` 包一层 SAVEPOINT 隔离。
        替身必须跟上，否则 AttributeError 会把「被测行为是否正确」变成
        「替身是否够新」——这类红会掩盖真实回归。
        """
        self.auth_gate_calls.append(("begin_nested",))
        return _NullSavepoint()


def admin_user():
    """管理员身份（``current_user.role.value == 'admin'``，走鉴权门的管理员分支）。"""
    return SimpleNamespace(id=uuid4(), username="tester", role=UserRole.admin)


def member_user():
    """普通用户（非管理员）：替身会话不返回成员行 ⇒ 鉴权门应 403。"""
    return SimpleNamespace(id=uuid4(), username="outsider", role=UserRole.auditor)


def formula_row(**columns) -> WpFormula:
    """真 ``WpFormula`` 瞬态实例（不入库）；未给的列为 None，跟随 ORM 列集自动对齐。"""
    return WpFormula(**columns)


def patch_d_cycle_aux_aggregation(monkeypatch, entries, *, raise_exc=None):
    """把 D 循环明细 aux 归集统一入口换成记录入参的替身，返回调用记录列表。

    ``entries``：``(aux_name, opening, debit, credit, closing)`` 元组或 ``AuxEntry``。
    ``raise_exc``：给定则替身抛该异常（验证调用方 fail-open）。
    被替换的是 ``d_aux_import.aggregate_d_cycle_aux`` —— ``aggregate_d6_detail_rows`` 在函数体内
    按名取它，故 render → seed → ``aggregate_d6_detail_rows`` → 行构建 全程仍是生产代码。
    """
    from app.services.d_cycle_extraction import d_aux_import as dai
    from app.services.four_table.aux_aggregation import AuxEntry

    calls: list[dict] = []
    built = [e if isinstance(e, AuxEntry) else AuxEntry(*e) for e in entries]

    async def _fake(db, project_id, year, wp_code):
        calls.append({"project_id": project_id, "year": year, "wp_code": wp_code})
        if raise_exc is not None:
            raise raise_exc
        return dai.DAuxImportResult(
            entries=list(built),
            aux_type="客户" if built else None,
            reason="ok" if built else "no_rows",
            prefixes=["1141"],
            row_code="BS-011",
            resolved_from="fallback",
        )

    monkeypatch.setattr(dai, "aggregate_d_cycle_aux", _fake, raising=True)
    return calls
