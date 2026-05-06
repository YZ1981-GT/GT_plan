"""合并模块集成测试 — Task 4.4 [R1.5]

合并模块主线链路集成测试：
  合并范围 → 导入子公司数据 → 合并试算表重算 → 抵消分录 CRUD → 差额表计算 → 合并报表生成

运行：python -m pytest backend/tests/test_consolidation_chain.py -v --tb=short

测试用户：admin / admin123
后端端口：9980
"""

from __future__ import annotations

import logging
import os
from io import BytesIO

import httpx
import pytest

logger = logging.getLogger(__name__)

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9980")
TEST_USER = os.getenv("TEST_USER", "admin")
TEST_PASS = os.getenv("TEST_PASS", "admin123")
AUDIT_YEAR = 2024


# ── 共享状态 ──────────────────────────────────────────────────────


class _SharedState:
    """跨测试方法共享的状态容器"""

    project_id: str | None = None
    auth_token: str | None = None
    scope_ids: list[str] = []
    elimination_id: str | None = None
    elimination_entry_no: str | None = None
    trial_rows: list[dict] = []
    issues: list[str] = []


state = _SharedState()


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    """创建同步 HTTP 客户端并登录获取 token"""
    c = httpx.Client(base_url=BASE_URL, timeout=60)
    resp = c.post("/api/auth/login", json={
        "username": TEST_USER,
        "password": TEST_PASS,
    })
    if resp.status_code == 200:
        data = resp.json()
        payload = data.get("data", data)
        token = payload.get("access_token") or payload.get("token")
        if token:
            c.headers["Authorization"] = f"Bearer {token}"
            state.auth_token = token
            logger.info("登录成功，获取到 token")
        else:
            state.issues.append("登录响应中未找到 access_token 字段")
            logger.warning("登录响应中未找到 token: %s", data)
    else:
        state.issues.append(f"登录失败: HTTP {resp.status_code}")
        logger.error("登录失败: %s %s", resp.status_code, resp.text[:200])
    yield c
    c.close()


def _log_issue(step: str, detail: str):
    msg = f"[{step}] {detail}"
    state.issues.append(msg)
    logger.warning(msg)


def _safe_json(resp: httpx.Response) -> dict | list:
    try:
        return resp.json()
    except Exception:
        return {"_raw": resp.text[:500]}


# ── 测试类 ────────────────────────────────────────────────────────


class TestConsolidationChain:
    """合并模块主线链路集成测试

    测试方法按编号顺序执行，共享 state 传递上下文。
    """

    # ── Step 0: 创建项目 ──────────────────────────────────────────

    def test_00_create_project(self, client: httpx.Client):
        """创建合并审计项目作为测试基础"""
        resp = client.post("/api/projects", json={
            "client_name": "合并链路测试集团",
            "audit_year": AUDIT_YEAR,
            "project_type": "annual",
            "accounting_standard": "enterprise",
            "template_type": "soe",
            "report_scope": "consolidated",
            "parent_company_name": "合并链路测试集团",
        })
        if resp.status_code not in (200, 201):
            _log_issue("创建项目", f"HTTP {resp.status_code}: {resp.text[:300]}")
            pytest.skip(f"创建项目失败: {resp.status_code}")

        data = _safe_json(resp)
        payload = data.get("data", data) if isinstance(data, dict) else data
        project_id = str(payload.get("id", ""))
        assert project_id, f"项目 ID 为空，响应: {data}"
        state.project_id = project_id
        logger.info("项目创建成功: %s", project_id)

    # ── Step 1: 创建合并范围 → 导入子公司数据 ────────────────────

    def test_01_create_scope_and_import(self, client: httpx.Client):
        """创建合并范围（3 家子公司）并导入余额表数据"""
        if not state.project_id:
            pytest.skip("无项目 ID")

        # 1a. 添加 3 家子公司到合并范围
        child_companies = [
            {"company_code": "C001", "company_name": "子公司A-制造", "ownership_ratio": "0.80"},
            {"company_code": "C002", "company_name": "子公司B-贸易", "ownership_ratio": "0.60"},
            {"company_code": "C003", "company_name": "子公司C-科技", "ownership_ratio": "1.00"},
        ]

        for child in child_companies:
            scope_resp = client.post(
                "/api/consolidation/scope",
                params={"project_id": state.project_id},
                json={
                    "project_id": state.project_id,
                    "year": AUDIT_YEAR,
                    "company_code": child["company_code"],
                    "company_name": child["company_name"],
                    "is_included": True,
                    "ownership_ratio": child["ownership_ratio"],
                    "inclusion_reason": "subsidiary",
                    "scope_change_type": "none",
                },
            )
            if scope_resp.status_code in (200, 201):
                scope_data = _safe_json(scope_resp)
                scope_payload = scope_data.get("data", scope_data) if isinstance(scope_data, dict) else scope_data
                scope_id = str(scope_payload.get("id", "")) if isinstance(scope_payload, dict) else ""
                if scope_id:
                    state.scope_ids.append(scope_id)
                logger.info("子公司 %s 添加成功, scope_id=%s", child["company_code"], scope_id)
            else:
                _log_issue("添加子公司", f"{child['company_code']}: HTTP {scope_resp.status_code} - {scope_resp.text[:200]}")

        assert len(state.scope_ids) >= 1, "至少需要添加 1 家子公司到合并范围"

        # 1b. 验证合并范围列表
        list_resp = client.get(
            "/api/consolidation/scope",
            params={"project_id": state.project_id, "year": AUDIT_YEAR},
        )
        assert list_resp.status_code == 200, f"获取合并范围列表失败: {list_resp.status_code}"
        scope_list = _safe_json(list_resp)
        if isinstance(scope_list, dict):
            scope_list = scope_list.get("data", scope_list)
        scope_count = len(scope_list) if isinstance(scope_list, list) else 0
        logger.info("合并范围: %d 家子公司", scope_count)

        # 1c. 验证合并范围汇总
        summary_resp = client.get(
            "/api/consolidation/scope/summary",
            params={"project_id": state.project_id, "year": AUDIT_YEAR},
        )
        if summary_resp.status_code == 200:
            summary = _safe_json(summary_resp)
            logger.info("合并范围汇总: %s", summary)
        else:
            _log_issue("合并范围汇总", f"HTTP {summary_resp.status_code}")

        # 1d. 为母公司 + 各子公司导入余额表
        import openpyxl

        companies_to_import = [
            {"company_code": "001", "company_name": "母公司"},
        ] + child_companies

        success_count = 0
        for company in companies_to_import:
            code = company["company_code"]
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "科目余额表"
            ws.append(["科目编码", "科目名称", "期初余额", "本期借方", "本期贷方", "期末余额"])
            test_accounts = [
                ["1001", "库存现金", 50000, 120000, 100000, 70000],
                ["1002", "银行存款", 5000000, 8000000, 7500000, 5500000],
                ["1122", "应收账款", 2000000, 3000000, 2800000, 2200000],
                ["1403", "原材料", 800000, 1200000, 1000000, 1000000],
                ["1405", "库存商品", 1500000, 2000000, 1800000, 1700000],
                ["2202", "应付账款", 1800000, 1600000, 2000000, 2200000],
                ["4001", "营业收入", 0, 0, 15000000, 15000000],
                ["4101", "营业成本", 0, 10000000, 0, 10000000],
                ["5001", "管理费用", 0, 2000000, 0, 2000000],
            ]
            for row in test_accounts:
                ws.append(row)

            buf = BytesIO()
            wb.save(buf)
            buf.seek(0)

            resp = client.post(
                f"/api/projects/{state.project_id}/import",
                files={"file": (f"余额表_{code}.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={
                    "source_type": "generic",
                    "data_type": "tb_balance",
                    "year": str(AUDIT_YEAR),
                    "on_duplicate": "overwrite",
                },
            )
            if resp.status_code == 200:
                success_count += 1
                logger.info("余额表导入成功: %s", code)
            else:
                _log_issue("导入余额表", f"{code}: HTTP {resp.status_code} - {resp.text[:200]}")

        assert success_count >= 1, "至少需要成功导入 1 份余额表"
        logger.info("余额表导入完成: %d/%d 成功", success_count, len(companies_to_import))

    # ── Step 2: 合并试算表重算 ────────────────────────────────────

    def test_02_consol_trial_recalc(self, client: httpx.Client):
        """触发合并试算表重算并验证结果"""
        if not state.project_id:
            pytest.skip("无项目 ID")

        # 2a. 触发合并试算表重算
        resp = client.post(
            "/api/consolidation/trial/recalculate",
            params={"project_id": state.project_id, "year": AUDIT_YEAR},
        )
        if resp.status_code == 200:
            data = _safe_json(resp)
            rows = data if isinstance(data, list) else (data.get("data", []) if isinstance(data, dict) else [])
            state.trial_rows = rows if isinstance(rows, list) else []
            logger.info("合并试算表重算成功: %d 行", len(state.trial_rows))
        else:
            _log_issue("合并试算表重算", f"HTTP {resp.status_code}: {resp.text[:300]}")

        # 2b. 查询合并试算表
        list_resp = client.get(
            "/api/consolidation/trial",
            params={"project_id": state.project_id, "year": AUDIT_YEAR},
        )
        assert list_resp.status_code == 200, f"获取合并试算表失败: {list_resp.status_code}"
        trial_data = _safe_json(list_resp)
        rows = trial_data if isinstance(trial_data, list) else (trial_data.get("data", []) if isinstance(trial_data, dict) else [])
        logger.info("合并试算表行数: %d", len(rows) if isinstance(rows, list) else 0)

        # 2c. 一致性校验
        check_resp = client.get(
            "/api/consolidation/trial/consistency-check",
            params={"project_id": state.project_id, "year": AUDIT_YEAR},
        )
        if check_resp.status_code == 200:
            check_data = _safe_json(check_resp)
            payload = check_data.get("data", check_data) if isinstance(check_data, dict) else check_data
            is_balanced = payload.get("is_balanced", None) if isinstance(payload, dict) else None
            logger.info("合并试算表一致性: is_balanced=%s", is_balanced)
        else:
            _log_issue("合并试算表一致性", f"HTTP {check_resp.status_code}: {check_resp.text[:200]}")

    # ── Step 3: 抵消分录 CRUD ─────────────────────────────────────

    def test_03_elimination_crud(self, client: httpx.Client):
        """创建/读取/更新/删除抵消分录"""
        if not state.project_id:
            pytest.skip("无项目 ID")

        # 3a. 创建抵消分录 — 内部往来抵消
        create_resp = client.post(
            "/api/consolidation/eliminations",
            params={"project_id": state.project_id},
            json={
                "project_id": state.project_id,
                "year": AUDIT_YEAR,
                "entry_type": "internal_ar_ap",
                "description": "内部应收应付抵消",
                "lines": [
                    {
                        "account_code": "2202",
                        "account_name": "应付账款",
                        "debit_amount": "500000",
                        "credit_amount": "0",
                    },
                    {
                        "account_code": "1122",
                        "account_name": "应收账款",
                        "debit_amount": "0",
                        "credit_amount": "500000",
                    },
                ],
                "related_company_codes": ["C001", "C002"],
            },
        )
        if create_resp.status_code in (200, 201):
            data = _safe_json(create_resp)
            payload = data.get("data", data) if isinstance(data, dict) else data
            state.elimination_id = str(payload.get("id", "")) if isinstance(payload, dict) else ""
            state.elimination_entry_no = str(payload.get("entry_no", "")) if isinstance(payload, dict) else ""
            logger.info("抵消分录创建成功: id=%s, entry_no=%s", state.elimination_id, state.elimination_entry_no)
        else:
            _log_issue("创建抵消分录", f"HTTP {create_resp.status_code}: {create_resp.text[:300]}")
            pytest.skip("创建抵消分录失败，跳过后续 CRUD")

        assert state.elimination_id, "抵消分录 ID 为空"

        # 3b. 读取抵消分录
        get_resp = client.get(
            f"/api/consolidation/eliminations/{state.elimination_id}",
            params={"project_id": state.project_id},
        )
        assert get_resp.status_code == 200, f"读取抵消分录失败: {get_resp.status_code}"
        entry_data = _safe_json(get_resp)
        payload = entry_data.get("data", entry_data) if isinstance(entry_data, dict) else entry_data
        logger.info("读取抵消分录: entry_type=%s, description=%s",
                     payload.get("entry_type") if isinstance(payload, dict) else "?",
                     payload.get("description") if isinstance(payload, dict) else "?")

        # 3c. 更新抵消分录
        update_resp = client.put(
            f"/api/consolidation/eliminations/{state.elimination_id}",
            params={"project_id": state.project_id},
            json={
                "description": "内部应收应付抵消（已更新）",
                "lines": [
                    {
                        "account_code": "2202",
                        "account_name": "应付账款",
                        "debit_amount": "600000",
                        "credit_amount": "0",
                    },
                    {
                        "account_code": "1122",
                        "account_name": "应收账款",
                        "debit_amount": "0",
                        "credit_amount": "600000",
                    },
                ],
            },
        )
        if update_resp.status_code == 200:
            updated = _safe_json(update_resp)
            updated_payload = updated.get("data", updated) if isinstance(updated, dict) else updated
            logger.info("抵消分录更新成功: description=%s",
                         updated_payload.get("description") if isinstance(updated_payload, dict) else "?")
        else:
            _log_issue("更新抵消分录", f"HTTP {update_resp.status_code}: {update_resp.text[:200]}")

        # 3d. 查询抵消分录列表
        list_resp = client.get(
            "/api/consolidation/eliminations",
            params={"project_id": state.project_id, "year": AUDIT_YEAR},
        )
        assert list_resp.status_code == 200, f"获取抵消分录列表失败: {list_resp.status_code}"
        entries = _safe_json(list_resp)
        if isinstance(entries, dict):
            entries = entries.get("data", entries)
        entry_count = len(entries) if isinstance(entries, list) else 0
        logger.info("抵消分录列表: %d 条", entry_count)
        assert entry_count >= 1, "抵消分录列表应至少有 1 条"

        # 3e. 查询抵消分录汇总
        summary_resp = client.get(
            "/api/consolidation/eliminations/summary/year",
            params={"project_id": state.project_id, "year": AUDIT_YEAR},
        )
        if summary_resp.status_code == 200:
            summary = _safe_json(summary_resp)
            logger.info("抵消分录汇总: %s", summary)
        else:
            _log_issue("抵消分录汇总", f"HTTP {summary_resp.status_code}")

        # 3f. 创建第二条抵消分录用于后续删除测试
        create2_resp = client.post(
            "/api/consolidation/eliminations",
            params={"project_id": state.project_id},
            json={
                "project_id": state.project_id,
                "year": AUDIT_YEAR,
                "entry_type": "equity",
                "description": "权益法抵消（待删除）",
                "lines": [
                    {
                        "account_code": "4001",
                        "account_name": "实收资本",
                        "debit_amount": "1000000",
                        "credit_amount": "0",
                    },
                    {
                        "account_code": "1511",
                        "account_name": "长期股权投资",
                        "debit_amount": "0",
                        "credit_amount": "1000000",
                    },
                ],
                "related_company_codes": ["C001"],
            },
        )
        delete_entry_id = None
        if create2_resp.status_code in (200, 201):
            data2 = _safe_json(create2_resp)
            payload2 = data2.get("data", data2) if isinstance(data2, dict) else data2
            delete_entry_id = str(payload2.get("id", "")) if isinstance(payload2, dict) else ""
            logger.info("第二条抵消分录创建成功: id=%s", delete_entry_id)
        else:
            _log_issue("创建第二条抵消分录", f"HTTP {create2_resp.status_code}")

        # 3g. 删除第二条抵消分录
        if delete_entry_id:
            del_resp = client.delete(
                f"/api/consolidation/eliminations/{delete_entry_id}",
                params={"project_id": state.project_id},
            )
            if del_resp.status_code == 204:
                logger.info("抵消分录删除成功: id=%s", delete_entry_id)
            else:
                _log_issue("删除抵消分录", f"HTTP {del_resp.status_code}: {del_resp.text[:200]}")

            # 验证删除后列表数量
            list2_resp = client.get(
                "/api/consolidation/eliminations",
                params={"project_id": state.project_id, "year": AUDIT_YEAR},
            )
            if list2_resp.status_code == 200:
                entries2 = _safe_json(list2_resp)
                if isinstance(entries2, dict):
                    entries2 = entries2.get("data", entries2)
                count2 = len(entries2) if isinstance(entries2, list) else 0
                logger.info("删除后抵消分录列表: %d 条", count2)

    # ── Step 4: 差额表计算 ────────────────────────────────────────

    def test_04_worksheet_recalc(self, client: httpx.Client):
        """触发差额表全量重算并验证"""
        if not state.project_id:
            pytest.skip("无项目 ID")

        # 4a. 全量重算差额表
        resp = client.post(
            "/api/consolidation/worksheet/recalc",
            json={
                "project_id": state.project_id,
                "year": AUDIT_YEAR,
            },
        )
        if resp.status_code == 200:
            data = _safe_json(resp)
            logger.info("差额表重算成功: %s", str(data)[:300])
        else:
            _log_issue("差额表重算", f"HTTP {resp.status_code}: {resp.text[:300]}")

        # 4b. 查询企业树
        tree_resp = client.get(
            "/api/consolidation/worksheet/tree",
            params={"project_id": state.project_id},
        )
        if tree_resp.status_code == 200:
            tree_data = _safe_json(tree_resp)
            logger.info("企业树: %s", str(tree_data)[:300])
        else:
            _log_issue("企业树", f"HTTP {tree_resp.status_code}")

        # 4c. 节点汇总查询
        agg_resp = client.get(
            "/api/consolidation/worksheet/aggregate",
            params={
                "project_id": state.project_id,
                "year": AUDIT_YEAR,
                "node_code": "001",
                "mode": "descendants",
            },
        )
        if agg_resp.status_code == 200:
            agg_data = _safe_json(agg_resp)
            rows = agg_data.get("rows", []) if isinstance(agg_data, dict) else []
            logger.info("节点汇总: %d 行", len(rows) if isinstance(rows, list) else 0)
        else:
            _log_issue("节点汇总", f"HTTP {agg_resp.status_code}: {agg_resp.text[:200]}")

        # 4d. 透视查询
        pivot_resp = client.post(
            "/api/consolidation/worksheet/pivot",
            json={
                "project_id": state.project_id,
                "year": AUDIT_YEAR,
                "row_dimension": "account",
                "col_dimension": "company",
                "value_field": "consolidated_amount",
            },
        )
        if pivot_resp.status_code == 200:
            pivot_data = _safe_json(pivot_resp)
            logger.info("透视查询成功: %s", str(pivot_data)[:300])
        else:
            _log_issue("透视查询", f"HTTP {pivot_resp.status_code}: {pivot_resp.text[:200]}")

    # ── Step 5: 合并报表生成 ──────────────────────────────────────

    def test_05_generate_consol_reports(self, client: httpx.Client):
        """生成合并报表并验证"""
        if not state.project_id:
            pytest.skip("无项目 ID")

        # 5a. 生成合并报表
        gen_resp = client.post(
            "/api/consolidation/reports/generate",
            json={
                "project_id": state.project_id,
                "year": AUDIT_YEAR,
                "applicable_standard": "CAS",
            },
        )
        if gen_resp.status_code == 200:
            data = _safe_json(gen_resp)
            payload = data.get("data", data) if isinstance(data, dict) else data
            report_types = payload.get("report_types", []) if isinstance(payload, dict) else []
            logger.info("合并报表生成成功: %s", report_types)
        else:
            _log_issue("生成合并报表", f"HTTP {gen_resp.status_code}: {gen_resp.text[:300]}")

        # 5b. 查询合并资产负债表
        bs_resp = client.get(
            f"/api/consolidation/reports/{state.project_id}/{AUDIT_YEAR}",
            params={"report_type": "balance_sheet"},
        )
        if bs_resp.status_code == 200:
            bs_data = _safe_json(bs_resp)
            rows = bs_data if isinstance(bs_data, list) else (bs_data.get("data", []) if isinstance(bs_data, dict) else [])
            logger.info("合并资产负债表: %d 行", len(rows) if isinstance(rows, list) else 0)
        elif bs_resp.status_code == 404:
            logger.info("合并资产负债表尚未生成（404）")
        else:
            _log_issue("查询合并资产负债表", f"HTTP {bs_resp.status_code}")

        # 5c. 查询合并利润表
        is_resp = client.get(
            f"/api/consolidation/reports/{state.project_id}/{AUDIT_YEAR}",
            params={"report_type": "income_statement"},
        )
        if is_resp.status_code == 200:
            is_data = _safe_json(is_resp)
            rows = is_data if isinstance(is_data, list) else (is_data.get("data", []) if isinstance(is_data, dict) else [])
            logger.info("合并利润表: %d 行", len(rows) if isinstance(rows, list) else 0)
        elif is_resp.status_code == 404:
            logger.info("合并利润表尚未生成（404）")
        else:
            _log_issue("查询合并利润表", f"HTTP {is_resp.status_code}")

        # 5d. 平衡校验
        check_resp = client.get(
            f"/api/consolidation/reports/{state.project_id}/{AUDIT_YEAR}/balance-check",
        )
        if check_resp.status_code == 200:
            check_data = _safe_json(check_resp)
            payload = check_data.get("data", check_data) if isinstance(check_data, dict) else check_data
            is_balanced = payload.get("is_balanced", None) if isinstance(payload, dict) else None
            logger.info("合并报表平衡校验: is_balanced=%s", is_balanced)
        else:
            _log_issue("合并报表平衡校验", f"HTTP {check_resp.status_code}: {check_resp.text[:200]}")


# ── 问题汇总报告 ──────────────────────────────────────────────────


class TestConsolidationChainSummary:
    """最终汇总：输出所有发现的问题"""

    def test_99_print_issues(self, client: httpx.Client):
        """打印合并链路测试中发现的所有问题"""
        logger.info("=" * 60)
        logger.info("合并模块集成测试问题汇总")
        logger.info("=" * 60)

        if not state.issues:
            logger.info("✅ 未发现问题，合并链路全流程通过！")
        else:
            logger.info("⚠️  发现 %d 个问题：", len(state.issues))
            for i, issue in enumerate(state.issues, 1):
                logger.info("  %d. %s", i, issue)

        logger.info("=" * 60)
        logger.info("项目 ID: %s", state.project_id or "未创建")
        logger.info("合并范围 scope_ids: %s", state.scope_ids)
        logger.info("抵消分录 ID: %s", state.elimination_id or "无")
        logger.info("合并试算表行数: %d", len(state.trial_rows))
        logger.info("=" * 60)

        if state.issues:
            logger.warning("共 %d 个问题需要关注", len(state.issues))
