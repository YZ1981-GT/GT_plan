"""Self-tests for the procedure delegation architecture debt guard."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

CHECK_DIR = Path(__file__).resolve().parents[2] / "scripts" / "check"
sys.path.insert(0, str(CHECK_DIR))

import check_procedure_delegation_architecture as guard  # noqa: E402


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def rules(findings):
    return {finding.rule for finding in findings}


def baseline_for(findings, ceiling=None):
    entries = [
        {**guard.asdict(finding), "reason": "Known historical debt with an explicit owner."}
        for finding in findings
        if finding.rule in guard.BASELINE_RULES
    ]
    return {
        "metadata": {"debt_ceiling": len(entries) if ceiling is None else ceiling},
        "entries": entries,
    }


class TestPythonAstRules:
    def test_instance_id_as_task_positive_and_read_negative(self, tmp_path):
        positive = write(tmp_path, "backend/app/services/tasks.py", """
from app.models.procedure_models import ProcedureInstance
async def get_my_tasks(db):
    rows = await db.execute(select(ProcedureInstance))
    return [{"task_id": str(p.id)} for p in rows]
""")
        negative = write(tmp_path, "backend/app/services/read.py", """
from app.models.procedure_models import ProcedureInstance
async def get_procedures(db):
    return await db.execute(select(ProcedureInstance))
""")
        assert guard.RULE_INSTANCE_ID_AS_ROW_TASK in rules(guard.scan_python_file(positive, tmp_path))
        assert guard.RULE_INSTANCE_ID_AS_ROW_TASK not in rules(guard.scan_python_file(negative, tmp_path))

    def test_get_render_domain_write_positive_and_read_negative(self, tmp_path):
        positive = write(tmp_path, "backend/app/routers/write.py", """
@router.get('/render')
async def render_page():
    from app.models.workpaper_models import WorkingPaper
    wp.parsed_data = {"程序": "已写"}
""")
        negative = write(tmp_path, "backend/app/routers/read.py", """
@router.get('/render')
async def render_page(db):
    from app.models.workpaper_models import WorkingPaper
    return await db.execute(select(WorkingPaper))
""")
        assert guard.RULE_GET_RENDER_DOMAIN_WRITE in rules(guard.scan_python_file(positive, tmp_path))
        assert guard.RULE_GET_RENDER_DOMAIN_WRITE not in rules(guard.scan_python_file(negative, tmp_path))

    def test_parsed_data_rmw_and_state_bypass(self, tmp_path):
        path = write(tmp_path, "backend/app/services/legacy.py", """
async def mutate(wp):
    parsed = dict(wp.parsed_data or {})
    parsed["procedure_status"] = {"R1": {"status": "submitted"}}
    wp.parsed_data = parsed
""")
        found = rules(guard.scan_python_file(path, tmp_path))
        assert guard.RULE_PARSED_DATA_RMW in found
        assert guard.RULE_STATE_BYPASS in found

    def test_exact_transition_service_allowlist(self, tmp_path):
        allowed = write(
            tmp_path,
            "backend/app/services/procedure_task_transition_service.py",
            """
class ProcedureTaskTransitionService:
    async def transition(self, wp):
        parsed = dict(wp.parsed_data or {})
        parsed["procedure_status"] = {"R1": {"status": "submitted"}}
        wp.parsed_data = parsed
""",
        )
        lookalike = write(tmp_path, "backend/app/services/lookalike.py", """
class ProcedureTaskTransitionService:
    async def transition(self, wp):
        parsed = dict(wp.parsed_data or {})
        parsed["procedure_status"] = {}
        wp.parsed_data = parsed
""")
        outside_class = write(
            tmp_path,
            "backend/app/services/procedure_task_transition_service.py",
            allowed.read_text(encoding="utf-8") + "\nasync def bypass(wp):\n"
            "    parsed = dict(wp.parsed_data or {})\n"
            "    parsed['procedure_status'] = {}\n"
            "    wp.parsed_data = parsed\n",
        )
        allowed_findings = guard.scan_python_file(allowed, tmp_path)
        assert not [f for f in allowed_findings if f.symbol == "ProcedureTaskTransitionService.transition"]
        assert guard.RULE_STATE_BYPASS in rules(guard.scan_python_file(lookalike, tmp_path))
        assert any(f.symbol == "bypass" for f in guard.scan_python_file(outside_class, tmp_path))

    def test_procedure_instance_state_update_positive_and_query_negative(self, tmp_path):
        positive = write(tmp_path, "backend/app/services/update.py", """
from app.models.procedure_models import ProcedureInstance
async def update_status(db):
    await db.execute(sa.update(ProcedureInstance).values(execution_status="completed"))
""")
        negative = write(tmp_path, "backend/app/services/query.py", """
from app.models.procedure_models import ProcedureInstance
async def query_status(db):
    return await db.execute(sa.select(ProcedureInstance.execution_status))
""")
        assert guard.RULE_STATE_BYPASS in rules(guard.scan_python_file(positive, tmp_path))
        assert guard.RULE_STATE_BYPASS not in rules(guard.scan_python_file(negative, tmp_path))


class TestVueTsRules:
    def test_task_id_alias_positive_and_normal_id_negative(self, tmp_path):
        positive = write(tmp_path, "audit-platform/frontend/src/services/tasks.ts", """
export async function getRowTasks() {
  return rows.map((p) => ({ task_id: p.id, row_key: p.row_key }))
}
""")
        negative = write(tmp_path, "audit-platform/frontend/src/services/procedures.ts", """
export async function getProcedures() { return rows.map((p) => ({ id: p.id })) }
""")
        assert guard.RULE_INSTANCE_ID_AS_ROW_TASK in rules(guard.scan_frontend_file(positive, tmp_path))
        assert guard.RULE_INSTANCE_ID_AS_ROW_TASK not in rules(guard.scan_frontend_file(negative, tmp_path))

    def test_parallel_page_and_route_with_exact_canonical_allowlist(self, tmp_path):
        canonical_page = write(
            tmp_path,
            "audit-platform/frontend/src/views/MyProcedureTasks.vue",
            "<template><h1>我的审计程序</h1></template>",
        )
        parallel_page = write(
            tmp_path,
            "audit-platform/frontend/src/views/MyRowProcedureTasks.vue",
            "<template><h1>我的审计程序任务</h1></template>",
        )
        router = write(tmp_path, "audit-platform/frontend/src/router/index.ts", """
const routes = [
 { path: 'my-procedures', name: 'MyProcedureTasks', component: () => import('@/views/MyProcedureTasks.vue') },
 { path: 'my-row-procedures', name: 'MyRowProcedureTasks', component: () => import('@/views/MyRowProcedureTasks.vue') },
]
""")
        assert guard.RULE_PARALLEL_TASK_PAGE not in rules(guard.scan_frontend_file(canonical_page, tmp_path))
        assert guard.RULE_PARALLEL_TASK_PAGE in rules(guard.scan_frontend_file(parallel_page, tmp_path))
        route_findings = guard.scan_frontend_file(router, tmp_path)
        assert [f.symbol for f in route_findings if f.rule == guard.RULE_PARALLEL_TASK_PAGE] == [
            "route:MyRowProcedureTasks"
        ]

    def test_utf8_vue_is_scanned(self, tmp_path):
        path = write(
            tmp_path,
            "audit-platform/frontend/src/views/另一个ProcedureTasks.vue",
            "<template>我的审计程序任务</template>",
        )
        finding = guard.scan_frontend_file(path, tmp_path)[0]
        assert "另一个" in finding.path
        assert finding.fingerprint.startswith("sha256:")


class TestBaselineContract:
    def test_exact_baseline_passes(self, tmp_path):
        path = write(tmp_path, "backend/app/services/tasks.py", """
from app.models.procedure_models import ProcedureInstance
async def get_my_tasks(db):
    p = (await db.execute(select(ProcedureInstance))).scalar_one()
    return {"task_id": p.id}
""")
        findings = guard.scan_python_file(path, tmp_path)
        document = baseline_for(findings)
        entries, errors = guard._validate_baseline_document(document)
        assert errors == []
        assert guard.compare_with_baseline(findings, entries, document["metadata"]["debt_ceiling"]) == []

    def test_fingerprint_drift_fails(self, tmp_path):
        path = write(tmp_path, "backend/app/services/tasks.py", """
from app.models.procedure_models import ProcedureInstance
async def get_my_tasks(db):
    p = (await db.execute(select(ProcedureInstance))).scalar_one()
    return {"task_id": p.id}
""")
        before = guard.scan_python_file(path, tmp_path)
        entries = baseline_for(before)["entries"]
        path.write_text(path.read_text(encoding="utf-8") + "\n# no AST drift\n", encoding="utf-8")
        assert guard.compare_with_baseline(guard.scan_python_file(path, tmp_path), entries, 1) == []
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "    p = (await db.execute", "    changed = True\n    p = (await db.execute"
            ),
            encoding="utf-8",
        )
        errors = guard.compare_with_baseline(guard.scan_python_file(path, tmp_path), entries, 1)
        assert any("fingerprint drift" in error for error in errors)

    def test_stale_debt_and_debt_ceiling_fail(self, tmp_path):
        finding = guard.Finding("backend/app/x.py", "f", guard.RULE_STATE_BYPASS, "sha256:abc")
        entry = {**guard.asdict(finding), "reason": "Historical entry."}
        assert any("stale baseline" in e for e in guard.compare_with_baseline([], [entry], 1))
        assert any("exceeds debt_ceiling" in e for e in guard.compare_with_baseline([finding], [entry], 0))

    @pytest.mark.parametrize(
        ("mutate", "needle"),
        [
            (lambda d: d.update({"extra": True}), "unknown top-level"),
            (lambda d: d["metadata"].update({"extra": True}), "metadata unknown"),
            (lambda d: d["entries"][0].update({"extra": True}), "unknown fields"),
            (lambda d: d["entries"][0].update({"rule": "invented-rule"}), "unknown or non-baselineable rule"),
            (lambda d: d["entries"].append(dict(d["entries"][0])), "duplicate entry"),
        ],
    )
    def test_unknown_fields_rules_and_duplicates_fail(self, mutate, needle):
        finding = guard.Finding("backend/app/x.py", "f", guard.RULE_STATE_BYPASS, "sha256:abc")
        document = baseline_for([finding], ceiling=2)
        mutate(document)
        _, errors = guard._validate_baseline_document(document)
        assert any(needle in error for error in errors)

    def test_load_baseline_accepts_windows_style_paths(self, tmp_path):
        finding = guard.Finding(
            "backend/app/x.py", "f", guard.RULE_STATE_BYPASS, "sha256:" + "a" * 64
        )
        document = baseline_for([finding])
        document["entries"][0]["path"] = r"backend\app\x.py"
        path = tmp_path / "债务基线.json"
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        entries, ceiling, errors = guard.load_baseline(path)
        assert errors == []
        assert ceiling == 1
        assert entries[0]["path"] == "backend/app/x.py"


class TestRepositoryAndCli:
    def test_canonical_v105_is_allowed(self, tmp_path):
        # Task 2 landed the canonical feature migration → guard must NOT flag it.
        write(tmp_path, f"backend/migrations/{guard.CANONICAL_V105_FILENAME}", "-- V105 feature\n")
        findings = guard.scan_repository(tmp_path)
        assert guard.RULE_FORBIDDEN_V105 not in rules(findings)

    def test_non_canonical_v105_is_rejected(self, tmp_path):
        # A duplicate/misnamed V105 would be silently skipped by the runner's version dedup.
        write(tmp_path, "backend/migrations/V105__duplicate_variant.sql", "-- rogue\n")
        findings = guard.scan_repository(tmp_path)
        assert guard.RULE_FORBIDDEN_V105 in rules(findings)
        assert any("non-canonical V105" in e for e in guard.compare_with_baseline(findings, [], 0))

    def test_injected_root_and_baseline_strict(self, tmp_path):
        write(tmp_path, "backend/app/services/read.py", "async def read_only():\n    return 1\n")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"metadata": {"debt_ceiling": 0}, "entries": []}), encoding="utf-8")
        assert guard.main(["--strict", "--root", str(tmp_path), "--baseline", str(baseline)]) == 0

    def test_constants_track_landed_v105(self):
        """常量必须**跟随磁盘上真实落地的迁移**，不手抄版本号。

        🔴 2026-09-28 修：原断言写死 `NEXT_MIGRATION_FILENAME == "V105__..."` /
        `CURRENT_MIGRATION_VERSION == 105`。迁移头已推进到 V112（守卫源码注释自己
        写着「Current head advances to 112」），于是这条恒红 —— 是**判据手抄数字后
        过期**，不是常量错。改成从磁盘现算：常量指向的文件必须真存在、版本号必须由
        文件名解析得出、且不得回退到 V105 之前。这样再推进到 V113 也不会误红，
        但「常量与磁盘脱钩」会立刻打红。
        """
        migrations = Path(__file__).resolve().parents[2] / "migrations"

        # V105 是已落地的 canonical feature migration，必须一直在盘上
        assert guard.CANONICAL_V105_FILENAME == "V105__procedure_row_tasks.sql"
        assert (migrations / guard.CANONICAL_V105_FILENAME).is_file(), (
            f"canonical V105 迁移不在盘上: {guard.CANONICAL_V105_FILENAME}"
        )

        # 当前头部迁移：常量指向的文件必须存在，版本号必须与文件名一致
        head = guard.NEXT_MIGRATION_FILENAME
        assert (migrations / head).is_file(), f"头部迁移不在盘上: {head}"
        parsed = re.fullmatch(r"V(\d+)__.+\.sql", head)
        assert parsed, f"头部迁移文件名不合 V<num>__*.sql 形态: {head}"
        assert guard.CURRENT_MIGRATION_VERSION == int(parsed.group(1)), (
            f"CURRENT_MIGRATION_VERSION={guard.CURRENT_MIGRATION_VERSION} 与 "
            f"NEXT_MIGRATION_FILENAME={head} 解析出的版本不符"
        )
        # 已落地的 V105 不可回退
        assert guard.CURRENT_MIGRATION_VERSION >= 105

    def test_current_repository_baseline_is_exact(self):
        root = Path(__file__).resolve().parents[3]
        findings = guard.scan_repository(root)
        entries, ceiling, errors = guard.load_baseline(
            root / "backend/scripts/check/baselines/procedure_delegation_debt.json"
        )
        assert errors == []
        assert guard.compare_with_baseline(findings, entries, ceiling) == []


class TestCanonicalRouteLocation:
    """canonical「我的程序任务」路由的落点判据（2026-09-28 路由域拆分回归守卫）."""

    _CANONICAL_ROUTE = (
        "export const dashboardRoutes = [\n"
        "  {\n"
        "    path: 'my-procedures',\n"
        "    name: 'MyProcedureTasks',\n"
        "    component: () => import('@/views/MyProcedureTasks.vue'),\n"
        "  },\n"
        "]\n"
    )

    def test_router_source_predicate_covers_index_and_domains(self):
        base = "audit-platform/frontend/src/router"
        assert guard._is_router_source(f"{base}/index.ts")
        assert guard._is_router_source(f"{base}/domains/dashboard.ts")
        assert guard._is_router_source(f"{base}/domains/projects.ts")
        # 非路由真源：不得被当成 canonical 落点
        assert not guard._is_router_source(f"{base}/domains/nested/deep.ts")
        assert not guard._is_router_source(f"{base}/guards/authGuard.ts")
        assert not guard._is_router_source("audit-platform/frontend/src/views/Foo.ts")

    def test_canonical_route_in_domain_file_is_not_debt(self, tmp_path):
        """变异证明（正面）：canonical 路由落在 domains/*.ts 不得被报成并行页面。

        这正是长期红的形态 —— 路由本体从 index.ts 搬到 domains/dashboard.ts。
        """
        write(
            tmp_path,
            "audit-platform/frontend/src/router/domains/dashboard.ts",
            self._CANONICAL_ROUTE,
        )
        findings = guard.scan_repository(tmp_path)
        assert guard.RULE_PARALLEL_TASK_PAGE not in rules(findings), findings

    def test_canonical_route_outside_router_source_is_debt(self, tmp_path):
        """变异证明（反面）：同一条路由放在非路由真源文件里仍必须报债务。"""
        write(
            tmp_path,
            "audit-platform/frontend/src/views/rogueRoutes.ts",
            self._CANONICAL_ROUTE,
        )
        findings = guard.scan_repository(tmp_path)
        assert guard.RULE_PARALLEL_TASK_PAGE in rules(findings)

    def test_canonical_route_registered_twice_across_domains_is_debt(self, tmp_path):
        """变异证明：双注册（两个分域文件各一份）必须报出第二处。

        原 `canonical_seen > 1` 是文件内计数，拆分后两文件各只见 1 次 ⇒ 会静默放行。
        """
        write(
            tmp_path,
            "audit-platform/frontend/src/router/domains/dashboard.ts",
            self._CANONICAL_ROUTE,
        )
        write(
            tmp_path,
            "audit-platform/frontend/src/router/domains/projects.ts",
            self._CANONICAL_ROUTE.replace("dashboardRoutes", "projectsRoutes"),
        )
        findings = guard.scan_repository(tmp_path)
        dupes = [
            f for f in findings
            if f.rule == guard.RULE_PARALLEL_TASK_PAGE
            and "duplicate-canonical" in f.symbol
        ]
        assert len(dupes) == 1, findings
        assert dupes[0].path.endswith("domains/projects.ts")

    def test_real_repository_has_exactly_one_canonical_route(self):
        """真源回归：全仓 canonical 路由恰好一处（现算，禁写死文件名）。"""
        root = Path(__file__).resolve().parents[3]
        dupes = [
            f for f in guard._scan_duplicate_canonical_routes(root)
            if "duplicate-canonical" in f.symbol
        ]
        assert dupes == [], f"canonical 路由被重复注册: {dupes}"
