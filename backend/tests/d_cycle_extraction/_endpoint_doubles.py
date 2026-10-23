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


class AuthGateSessionMixin:
    """替身会话混入：补 ``get`` / ``get_bind``，并记录门禁触达。

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
            return SimpleNamespace(id=ident, status=self.project_status)
        return None

    def get_bind(self, *_a, **_kw):
        self.auth_gate_calls.append(("get_bind",))
        return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))


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
