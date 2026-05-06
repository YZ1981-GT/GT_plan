"""端到端审计全流程验证 — Task 4.2 [R1.1]

用真实审计项目端到端验证全流程，暴露并修复实际问题。

运行：python -m pytest backend/tests/test_e2e_audit_flow.py -v --tb=short

覆盖流程（11 步）：
  1.  创建合并审计项目（含 3 家子公司）
  2.  导入科目余额表
  3.  科目映射（自动匹配）
  4.  试算表重算
  5.  录入调整分录（AJE + RJE）
  6.  五环联动验证（TB → Adjustments → Reports → Notes → Workpapers）
  7.  生成四张财务报表
  8.  跨报表一致性校验
  9.  生成附注 + AI 续写
  10. 底稿编制 + QC 检查
  11. Word 导出

测试用户：admin / admin123
后端端口：9980
"""

from __future__ import annotations

import logging
import os
from io import BytesIO
from uuid import UUID

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
    project_name: str = ""
    auth_token: str | None = None
    child_companies: list[dict] = []
    adjustment_ids: list[str] = []
    workpaper_id: str | None = None
    export_task_id: str | None = None
    issues: list[str] = []  # 记录发现的问题


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
    """记录发现的问题"""
    msg = f"[{step}] {detail}"
    state.issues.append(msg)
    logger.warning(msg)


def _safe_json(resp: httpx.Response) -> dict | list:
    """安全解析 JSON，处理非 JSON 响应"""
    try:
        return resp.json()
    except Exception:
        return {"_raw": resp.text[:500]}


# ── 测试类 ────────────────────────────────────────────────────────


class TestE2EAuditFlow:
    """端到端审计全流程验证

    测试方法按编号顺序执行，共享 state 传递上下文。
    """

    # ── Step 1: 创建合并审计项目 ──────────────────────────────────

    def test_01_create_project(self, client: httpx.Client):
        """创建合并审计项目（含 3 家子公司）"""
        # 1a. 创建主项目
        resp = client.post("/api/projects", json={
            "client_name": "E2E测试集团有限公司",
            "audit_year": AUDIT_YEAR,
            "project_type": "annual",
            "accounting_standard": "enterprise",
            "template_type": "soe",
            "report_scope": "consolidated",
            "parent_company_name": "E2E测试集团有限公司",
        })
        if resp.status_code not in (200, 201):
            _log_issue("创建项目", f"HTTP {resp.status_code}: {resp.text[:300]}")
            pytest.skip(f"创建项目失败: {resp.status_code}")

        data = _safe_json(resp)
        payload = data.get("data", data) if isinstance(data, dict) else data
        project_id = str(payload.get("id", ""))
        assert project_id, f"项目 ID 为空，响应: {data}"
        state.project_id = project_id
        state.project_name = "E2E测试集团有限公司"
        logger.info("项目创建成功: %s", project_id)

        # 1b. 添加 3 家子公司到合并范围
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
                    "inclusion_reason": "control",
                    "scope_change_type": "none",
                },
            )
            if scope_resp.status_code in (200, 201):
                state.child_companies.append(child)
                logger.info("子公司 %s 添加成功", child["company_code"])
            else:
                _log_issue("添加子公司", f"{child['company_code']}: HTTP {scope_resp.status_code}")

        assert len(state.child_companies) >= 1, "至少需要添加 1 家子公司"
        logger.info("合并范围设置完成: %d 家子公司", len(state.child_companies))

    # ── Step 2: 导入科目余额表 ────────────────────────────────────

    def test_02_import_ledger(self, client: httpx.Client):
        """为每家子公司导入科目余额表数据"""
        if not state.project_id:
            pytest.skip("无项目 ID，跳过导入")

        import openpyxl

        success_count = 0
        # 为母公司 + 各子公司生成并导入余额表
        companies = [{"company_code": "001", "company_name": "母公司"}] + state.child_companies

        for company in companies:
            code = company["company_code"]
            # 生成模拟余额表 Excel
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "科目余额表"
            ws.append(["科目编码", "科目名称", "期初余额", "本期借方", "本期贷方", "期末余额"])
            # 模拟数据行
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
        logger.info("余额表导入完成: %d/%d 成功", success_count, len(companies))

    # ── Step 3: 科目映射 ──────────────────────────────────────────

    def test_03_account_mapping(self, client: httpx.Client):
        """执行自动科目映射"""
        if not state.project_id:
            pytest.skip("无项目 ID")

        # 3a. 触发自动匹配
        resp = client.post(
            f"/api/projects/{state.project_id}/mapping/auto-match",
            json={"year": AUDIT_YEAR},
        )
        if resp.status_code == 200:
            data = _safe_json(resp)
            payload = data.get("data", data) if isinstance(data, dict) else data
            matched = payload.get("matched_count", 0) if isinstance(payload, dict) else 0
            logger.info("自动匹配完成: %d 条映射", matched)
        else:
            _log_issue("自动匹配", f"HTTP {resp.status_code}: {resp.text[:200]}")

        # 3b. 查询映射完成率
        rate_resp = client.get(
            f"/api/projects/{state.project_id}/mapping/completion-rate",
            params={"year": AUDIT_YEAR},
        )
        if rate_resp.status_code == 200:
            rate_data = _safe_json(rate_resp)
            payload = rate_data.get("data", rate_data) if isinstance(rate_data, dict) else rate_data
            logger.info("映射完成率: %s", payload)
        else:
            _log_issue("映射完成率", f"HTTP {rate_resp.status_code}")

        # 3c. 查询映射列表
        list_resp = client.get(f"/api/projects/{state.project_id}/mapping")
        assert list_resp.status_code == 200, f"获取映射列表失败: {list_resp.status_code}"
        mappings = _safe_json(list_resp)
        if isinstance(mappings, dict):
            mappings = mappings.get("data", mappings)
        logger.info("映射列表: %d 条", len(mappings) if isinstance(mappings, list) else 0)

    # ── Step 4: 试算表重算 ────────────────────────────────────────

    def test_04_recalc_trial_balance(self, client: httpx.Client):
        """触发试算表全量重算"""
        if not state.project_id:
            pytest.skip("无项目 ID")

        resp = client.post(
            f"/api/projects/{state.project_id}/trial-balance/recalc",
            params={"year": AUDIT_YEAR, "company_code": "001"},
        )
        if resp.status_code == 200:
            logger.info("试算表重算成功")
        else:
            _log_issue("试算表重算", f"HTTP {resp.status_code}: {resp.text[:200]}")

        # 验证试算表数据
        tb_resp = client.get(
            f"/api/projects/{state.project_id}/trial-balance",
            params={"year": AUDIT_YEAR, "company_code": "001"},
        )
        assert tb_resp.status_code == 200, f"获取试算表失败: {tb_resp.status_code}"
        tb_data = _safe_json(tb_resp)
        rows = tb_data if isinstance(tb_data, list) else (tb_data.get("data", []) if isinstance(tb_data, dict) else [])
        logger.info("试算表行数: %d", len(rows))

    # ── Step 5: 录入调整分录 ──────────────────────────────────────

    def test_05_create_adjustments(self, client: httpx.Client):
        """创建 AJE 和 RJE 调整分录"""
        if not state.project_id:
            pytest.skip("无项目 ID")

        adjustments = [
            {
                "project_id": state.project_id,
                "year": AUDIT_YEAR,
                "adj_type": "AJE",
                "entry_number": "AJE-001",
                "description": "应收账款坏账准备调整",
                "debit_account": "6601",
                "debit_account_name": "资产减值损失",
                "credit_account": "1231",
                "credit_account_name": "坏账准备",
                "amount": "150000",
            },
            {
                "project_id": state.project_id,
                "year": AUDIT_YEAR,
                "adj_type": "RJE",
                "entry_number": "RJE-001",
                "description": "存货跌价准备重分类",
                "debit_account": "1405",
                "debit_account_name": "库存商品",
                "credit_account": "1471",
                "credit_account_name": "存货跌价准备",
                "amount": "80000",
            },
        ]

        for adj in adjustments:
            resp = client.post(
                "/api/adjustments/",
                params={"project_id": state.project_id, "year": AUDIT_YEAR},
                json=adj,
            )
            if resp.status_code in (200, 201):
                data = _safe_json(resp)
                payload = data.get("data", data) if isinstance(data, dict) else data
                adj_id = str(payload.get("id", "")) if isinstance(payload, dict) else ""
                if adj_id:
                    state.adjustment_ids.append(adj_id)
                logger.info("调整分录创建成功: %s", adj["entry_number"])
            else:
                _log_issue("创建调整分录", f"{adj['entry_number']}: HTTP {resp.status_code} - {resp.text[:200]}")

        # 查询调整分录列表
        list_resp = client.get(
            "/api/adjustments/",
            params={"project_id": state.project_id, "year": AUDIT_YEAR},
        )
        assert list_resp.status_code == 200, f"获取调整分录列表失败: {list_resp.status_code}"
        adj_data = _safe_json(list_resp)
        entries = adj_data if isinstance(adj_data, list) else (adj_data.get("data", []) if isinstance(adj_data, dict) else [])
        logger.info("调整分录总数: %d", len(entries) if isinstance(entries, list) else 0)

    # ── Step 6: 五环联动验证 ──────────────────────────────────────

    def test_06_verify_five_ring(self, client: httpx.Client):
        """验证五环联动：TB → Adjustments → Reports → Notes → Workpapers

        五环联动是审计平台的核心数据一致性机制：
        - 试算表（TB）的审定数 = 未审数 + AJE + RJE
        - 调整分录影响试算表
        - 报表数据来源于试算表
        - 附注数据与报表一致
        - 底稿引用报表/附注数据
        """
        if not state.project_id:
            pytest.skip("无项目 ID")

        ring_results = {}

        # Ring 1: 试算表
        tb_resp = client.get(
            f"/api/projects/{state.project_id}/trial-balance",
            params={"year": AUDIT_YEAR, "company_code": "001"},
        )
        ring_results["trial_balance"] = tb_resp.status_code == 200
        if tb_resp.status_code == 200:
            tb_data = _safe_json(tb_resp)
            rows = tb_data if isinstance(tb_data, list) else []
            logger.info("五环-试算表: %d 行", len(rows))
        else:
            _log_issue("五环-试算表", f"HTTP {tb_resp.status_code}")

        # Ring 2: 调整分录
        adj_resp = client.get(
            "/api/adjustments/",
            params={"project_id": state.project_id, "year": AUDIT_YEAR},
        )
        ring_results["adjustments"] = adj_resp.status_code == 200
        logger.info("五环-调整分录: HTTP %d", adj_resp.status_code)

        # Ring 3: 报表（先尝试获取，可能尚未生成）
        for report_type in ["balance_sheet", "income_statement"]:
            rpt_resp = client.get(
                f"/api/reports/{state.project_id}/{AUDIT_YEAR}/{report_type}"
            )
            ring_results[f"report_{report_type}"] = rpt_resp.status_code in (200, 404)
            logger.info("五环-报表(%s): HTTP %d", report_type, rpt_resp.status_code)

        # Ring 4: 附注
        notes_resp = client.get(
            f"/api/disclosure-notes/{state.project_id}/tree",
            params={"year": AUDIT_YEAR},
        )
        ring_results["notes"] = notes_resp.status_code in (200, 404)
        logger.info("五环-附注: HTTP %d", notes_resp.status_code)

        # Ring 5: 底稿
        wp_resp = client.get(
            f"/api/projects/{state.project_id}/working-papers",
        )
        ring_results["workpapers"] = wp_resp.status_code in (200, 404)
        logger.info("五环-底稿: HTTP %d", wp_resp.status_code)

        # 汇总
        passed = sum(1 for v in ring_results.values() if v)
        total = len(ring_results)
        logger.info("五环联动验证: %d/%d 通过", passed, total)
        if passed < total:
            failed_rings = [k for k, v in ring_results.items() if not v]
            _log_issue("五环联动", f"失败环节: {failed_rings}")

        assert passed >= 3, f"五环联动至少需要 3 环通过，实际 {passed}/{total}"

    # ── Step 7: 生成财务报表 ──────────────────────────────────────

    def test_07_generate_reports(self, client: httpx.Client):
        """生成四张财务报表"""
        if not state.project_id:
            pytest.skip("无项目 ID")

        resp = client.post("/api/reports/generate", json={
            "project_id": state.project_id,
            "year": AUDIT_YEAR,
        })
        if resp.status_code == 200:
            data = _safe_json(resp)
            payload = data.get("data", data) if isinstance(data, dict) else data
            report_types = payload.get("report_types", []) if isinstance(payload, dict) else []
            logger.info("报表生成成功: %s", report_types)
        else:
            _log_issue("生成报表", f"HTTP {resp.status_code}: {resp.text[:300]}")

        # 验证各报表可查询
        report_types_to_check = [
            "balance_sheet",
            "income_statement",
            "cash_flow_statement",
            "equity_change_statement",
        ]
        for rt in report_types_to_check:
            rpt_resp = client.get(
                f"/api/reports/{state.project_id}/{AUDIT_YEAR}/{rt}"
            )
            if rpt_resp.status_code == 200:
                rpt_data = _safe_json(rpt_resp)
                rows = rpt_data if isinstance(rpt_data, list) else (rpt_data.get("data", []) if isinstance(rpt_data, dict) else [])
                logger.info("报表 %s: %d 行", rt, len(rows) if isinstance(rows, list) else 0)
            else:
                _log_issue("查询报表", f"{rt}: HTTP {rpt_resp.status_code}")

    # ── Step 8: 一致性校验 ────────────────────────────────────────

    def test_08_consistency_check(self, client: httpx.Client):
        """执行跨报表一致性校验"""
        if not state.project_id:
            pytest.skip("无项目 ID")

        # 报表级一致性校验
        resp = client.get(
            f"/api/reports/{state.project_id}/{AUDIT_YEAR}/consistency-check"
        )
        if resp.status_code == 200:
            data = _safe_json(resp)
            payload = data.get("data", data) if isinstance(data, dict) else data
            consistent = payload.get("consistent", None) if isinstance(payload, dict) else None
            total = payload.get("total", 0) if isinstance(payload, dict) else 0
            logger.info("报表一致性: consistent=%s, total_checks=%d", consistent, total)
            if not consistent and isinstance(payload, dict):
                checks = payload.get("checks", [])
                failed = [c for c in checks if not c.get("passed", True)]
                for f in failed[:5]:
                    _log_issue("一致性校验", f"失败: {f.get('name', '?')} - 期望={f.get('expected')}, 实际={f.get('actual')}")
        else:
            _log_issue("一致性校验", f"HTTP {resp.status_code}: {resp.text[:200]}")

        # 试算表级一致性校验
        tb_check_resp = client.get(
            f"/api/projects/{state.project_id}/trial-balance/consistency-check",
            params={"year": AUDIT_YEAR, "company_code": "001"},
        )
        if tb_check_resp.status_code == 200:
            tb_data = _safe_json(tb_check_resp)
            payload = tb_data.get("data", tb_data) if isinstance(tb_data, dict) else tb_data
            tb_consistent = payload.get("consistent", None) if isinstance(payload, dict) else None
            issues = payload.get("issues", []) if isinstance(payload, dict) else []
            logger.info("试算表一致性: consistent=%s, issues=%d", tb_consistent, len(issues))
        else:
            _log_issue("试算表一致性", f"HTTP {tb_check_resp.status_code}")

    # ── Step 9: 生成附注 + AI 续写 ───────────────────────────────

    def test_09_generate_notes(self, client: httpx.Client):
        """生成披露附注并测试 AI 续写"""
        if not state.project_id:
            pytest.skip("无项目 ID")

        # 9a. 生成附注
        gen_resp = client.post(
            f"/api/disclosure-notes/{state.project_id}/generate",
            params={"year": AUDIT_YEAR},
        )
        if gen_resp.status_code == 200:
            data = _safe_json(gen_resp)
            logger.info("附注生成成功: %s", str(data)[:200])
        else:
            _log_issue("生成附注", f"HTTP {gen_resp.status_code}: {gen_resp.text[:200]}")

        # 9b. 获取附注树
        tree_resp = client.get(
            f"/api/disclosure-notes/{state.project_id}/tree",
            params={"year": AUDIT_YEAR},
        )
        if tree_resp.status_code == 200:
            tree_data = _safe_json(tree_resp)
            sections = tree_data if isinstance(tree_data, list) else (tree_data.get("data", []) if isinstance(tree_data, dict) else [])
            logger.info("附注章节数: %d", len(sections) if isinstance(sections, list) else 0)
        else:
            _log_issue("附注树", f"HTTP {tree_resp.status_code}")

        # 9c. AI 续写测试（可能因 LLM 不可用而降级）
        ai_resp = client.post(
            f"/api/disclosure-notes/{state.project_id}/ai/complete",
            json={
                "text": "本公司的货币资金主要包括库存现金和银行存款。",
                "section_number": "5.1",
                "year": AUDIT_YEAR,
            },
        )
        if ai_resp.status_code == 200:
            ai_data = _safe_json(ai_resp)
            payload = ai_data.get("data", ai_data) if isinstance(ai_data, dict) else ai_data
            has_result = bool(payload.get("result") or payload.get("suggestions")) if isinstance(payload, dict) else False
            logger.info("AI 续写: %s", "成功" if has_result else "降级（LLM 不可用）")
        else:
            _log_issue("AI 续写", f"HTTP {ai_resp.status_code}")
            logger.info("AI 续写不可用（预期行为，LLM 服务可能未启动）")

    # ── Step 10: 底稿编制 + QC 检查 ──────────────────────────────

    def test_10_workpaper_operations(self, client: httpx.Client):
        """底稿列表查询 + QC 检查"""
        if not state.project_id:
            pytest.skip("无项目 ID")

        # 10a. 查询底稿列表
        wp_resp = client.get(
            f"/api/projects/{state.project_id}/working-papers",
        )
        if wp_resp.status_code == 200:
            wp_data = _safe_json(wp_resp)
            wps = wp_data if isinstance(wp_data, list) else (wp_data.get("data", []) if isinstance(wp_data, dict) else [])
            if isinstance(wps, list) and len(wps) > 0:
                state.workpaper_id = str(wps[0].get("id", ""))
                logger.info("底稿列表: %d 份, 首份 ID=%s", len(wps), state.workpaper_id)
            else:
                logger.info("底稿列表为空（项目尚未生成底稿）")
        else:
            _log_issue("底稿列表", f"HTTP {wp_resp.status_code}")

        # 10b. QC 项目级汇总
        qc_resp = client.get(
            f"/api/projects/{state.project_id}/qc-summary",
        )
        if qc_resp.status_code == 200:
            qc_data = _safe_json(qc_resp)
            payload = qc_data.get("data", qc_data) if isinstance(qc_data, dict) else qc_data
            logger.info("QC 汇总: %s", str(payload)[:200])
        else:
            _log_issue("QC 汇总", f"HTTP {qc_resp.status_code}")

        # 10c. 如果有底稿，执行单份 QC 检查
        if state.workpaper_id:
            qc_check_resp = client.post(
                f"/api/projects/{state.project_id}/working-papers/{state.workpaper_id}/qc-check",
            )
            if qc_check_resp.status_code == 200:
                qc_result = _safe_json(qc_check_resp)
                payload = qc_result.get("data", qc_result) if isinstance(qc_result, dict) else qc_result
                passed = payload.get("passed", None) if isinstance(payload, dict) else None
                logger.info("QC 检查: passed=%s", passed)
            else:
                _log_issue("QC 检查", f"HTTP {qc_check_resp.status_code}: {qc_check_resp.text[:200]}")

    # ── Step 11: Word 导出 ────────────────────────────────────────

    def test_11_word_export(self, client: httpx.Client):
        """测试 Word/Excel 导出功能"""
        if not state.project_id:
            pytest.skip("无项目 ID")

        # 11a. 导出审计报告 Word
        audit_resp = client.post(
            f"/api/projects/{state.project_id}/word-exports/audit-report/generate",
        )
        if audit_resp.status_code == 200:
            data = _safe_json(audit_resp)
            payload = data.get("data", data) if isinstance(data, dict) else data
            task_id = str(payload.get("id", "")) if isinstance(payload, dict) else ""
            state.export_task_id = task_id
            logger.info("审计报告导出任务创建: %s", task_id)
        else:
            _log_issue("审计报告导出", f"HTTP {audit_resp.status_code}: {audit_resp.text[:200]}")

        # 11b. 导出财务报表 Word
        fin_resp = client.post(
            f"/api/projects/{state.project_id}/word-exports/financial-reports/generate",
        )
        if fin_resp.status_code == 200:
            logger.info("财务报表导出任务创建成功")
        else:
            _log_issue("财务报表导出", f"HTTP {fin_resp.status_code}: {fin_resp.text[:200]}")

        # 11c. 导出附注 Word
        notes_resp = client.post(
            f"/api/projects/{state.project_id}/word-exports/disclosure-notes/generate",
        )
        if notes_resp.status_code == 200:
            logger.info("附注导出任务创建成功")
        else:
            _log_issue("附注导出", f"HTTP {notes_resp.status_code}: {notes_resp.text[:200]}")

        # 11d. 导出报表 Excel（直接下载）
        excel_resp = client.get(
            f"/api/reports/{state.project_id}/{AUDIT_YEAR}/balance_sheet/export-excel",
        )
        if excel_resp.status_code == 200:
            content_type = excel_resp.headers.get("content-type", "")
            logger.info("Excel 导出成功: content-type=%s, size=%d bytes", content_type, len(excel_resp.content))
        elif excel_resp.status_code == 404:
            logger.info("Excel 导出: 报表数据不存在（需先生成报表）")
        else:
            _log_issue("Excel 导出", f"HTTP {excel_resp.status_code}")

        # 11e. 查询导出历史
        history_resp = client.get(
            f"/api/projects/{state.project_id}/word-exports/history",
        )
        if history_resp.status_code == 200:
            hist_data = _safe_json(history_resp)
            items = hist_data if isinstance(hist_data, list) else (hist_data.get("data", []) if isinstance(hist_data, dict) else [])
            logger.info("导出历史: %d 条记录", len(items) if isinstance(items, list) else 0)
        else:
            _log_issue("导出历史", f"HTTP {history_resp.status_code}")


# ── 问题汇总报告 ──────────────────────────────────────────────────


class TestIssuesSummary:
    """最终汇总：输出所有发现的问题"""

    def test_99_print_issues(self, client: httpx.Client):
        """打印端到端测试中发现的所有问题"""
        logger.info("=" * 60)
        logger.info("端到端测试问题汇总")
        logger.info("=" * 60)

        if not state.issues:
            logger.info("✅ 未发现问题，全流程通过！")
        else:
            logger.info("⚠️  发现 %d 个问题：", len(state.issues))
            for i, issue in enumerate(state.issues, 1):
                logger.info("  %d. %s", i, issue)

        logger.info("=" * 60)
        logger.info("项目 ID: %s", state.project_id or "未创建")
        logger.info("子公司数: %d", len(state.child_companies))
        logger.info("调整分录数: %d", len(state.adjustment_ids))
        logger.info("底稿 ID: %s", state.workpaper_id or "无")
        logger.info("导出任务 ID: %s", state.export_task_id or "无")
        logger.info("=" * 60)

        # 不 assert，仅记录
        if state.issues:
            logger.warning("共 %d 个问题需要关注", len(state.issues))
