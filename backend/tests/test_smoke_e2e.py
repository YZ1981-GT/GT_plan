"""端到端冒烟测试 — 验证核心 API 链路可用

运行：python -m pytest backend/tests/test_smoke_e2e.py -v --tb=short

覆盖流程：
  1. 健康检查
  2. 报表配置查询
  3. 公式解析+执行
  4. 自定义查询
  5. 合并工作底稿数据存取
  6. 批注/复核 CRUD
  7. 科目映射
  8. 公式审计日志
"""

import pytest
import httpx
import os

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9980")
# 测试用户凭证
TEST_USER = os.getenv("TEST_USER", "admin")
TEST_PASS = os.getenv("TEST_PASS", "admin123")


@pytest.fixture(scope="module")
def client():
    """创建带认证的 HTTP 客户端"""
    c = httpx.Client(base_url=BASE_URL, timeout=30)
    # 登录获取 token
    resp = c.post("/api/auth/login", json={"username": TEST_USER, "password": TEST_PASS})
    if resp.status_code == 200:
        token = resp.json().get("access_token") or resp.json().get("token")
        if token:
            c.headers["Authorization"] = f"Bearer {token}"
    yield c
    c.close()


class TestHealthCheck:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200


class TestReportConfig:
    def test_list_report_configs(self, client):
        resp = client.get("/api/report-config", params={
            "report_type": "balance_sheet",
            "applicable_standard": "soe_standalone",
        })
        assert resp.status_code == 200
        data = resp.json()
        # 可能返回列表或包装对象
        rows = data if isinstance(data, list) else (data.get("data") or [])
        assert isinstance(rows, list)


class TestFormulaEngine:
    def test_parse_arithmetic(self, client):
        """测试纯算术公式执行"""
        resp = client.post("/api/report-config/execute-formula", json={
            "project_id": "",
            "year": 2024,
            "formula": "100 + 200 * 3",
        })
        assert resp.status_code == 200
        result = resp.json()
        data = result.get("data") or result
        assert data.get("value") == 700.0
        assert data.get("error") is None

    def test_parse_row_ref(self, client):
        """测试行引用公式"""
        resp = client.post("/api/report-config/execute-formula", json={
            "project_id": "",
            "year": 2024,
            "formula": "BS-002 + BS-003",
            "row_values": {"BS-002": 50000, "BS-003": 30000},
        })
        assert resp.status_code == 200
        data = (resp.json().get("data") or resp.json())
        assert data.get("value") == 80000.0

    def test_parse_range_sum(self, client):
        """测试范围求和"""
        resp = client.post("/api/report-config/execute-formula", json={
            "project_id": "",
            "year": 2024,
            "formula": "SUM(CN-001:CN-003)",
            "row_values": {"CN-001": 100, "CN-002": 200, "CN-003": 300, "CN-004": 999},
        })
        assert resp.status_code == 200
        data = (resp.json().get("data") or resp.json())
        assert data.get("value") == 600.0

    def test_batch_execution(self, client):
        """测试批量执行+拓扑排序"""
        resp = client.post("/api/report-config/execute-formulas-batch", json={
            "project_id": "",
            "year": 2024,
            "formulas": [
                {"row_code": "A", "formula": "100 + 200"},
                {"row_code": "B", "formula": "A + 50"},
            ],
        })
        assert resp.status_code == 200
        data = (resp.json().get("data") or resp.json())
        results = data.get("results", [])
        row_values = data.get("row_values", {})
        assert row_values.get("A") == 300.0
        assert row_values.get("B") == 350.0

    def test_parse_error(self, client):
        """测试无效公式"""
        resp = client.post("/api/report-config/execute-formula", json={
            "project_id": "",
            "year": 2024,
            "formula": "",
        })
        assert resp.status_code == 200
        data = (resp.json().get("data") or resp.json())
        assert data.get("error") is not None


class TestCustomQuery:
    def test_indicators(self, client):
        resp = client.get("/api/custom-query/indicators")
        assert resp.status_code == 200
        data = resp.json()
        tree = data if isinstance(data, list) else (data.get("data") or [])
        assert len(tree) >= 4  # 至少 4 个大类


class TestConsolWorksheetData:
    def test_save_and_load(self, client):
        """测试工作底稿数据存取"""
        # 用一个不存在的项目 ID 测试（不影响真实数据）
        test_pid = "00000000-0000-0000-0000-000000000001"
        test_year = 9999
        test_key = "test_smoke"

        # 保存
        resp = client.put(f"/api/consol-worksheet-data/{test_pid}/{test_year}/{test_key}", json={
            "sheet_key": test_key,
            "data": {"rows": [{"a": 1, "b": 2}], "test": True},
        })
        assert resp.status_code == 200

        # 加载
        resp = client.get(f"/api/consol-worksheet-data/{test_pid}/{test_year}/{test_key}")
        assert resp.status_code == 200
        data = (resp.json().get("data") or resp.json())
        saved = data.get("data") or data
        assert saved.get("test") is True or (isinstance(saved, dict) and "rows" in saved)


class TestCellComments:
    def test_save_comment(self, client):
        test_pid = "00000000-0000-0000-0000-000000000001"
        resp = client.put(f"/api/cell-comments/{test_pid}/9999", json={
            "module": "test",
            "sheet_key": "smoke",
            "row_idx": 0,
            "col_idx": 0,
            "comment_type": "comment",
            "comment": "冒烟测试批注",
            "status": "",
            "row_name": "测试行",
            "col_name": "测试列",
        })
        assert resp.status_code == 200

    def test_load_comments(self, client):
        test_pid = "00000000-0000-0000-0000-000000000001"
        resp = client.get(f"/api/cell-comments/{test_pid}/9999/test")
        assert resp.status_code == 200
        data = resp.json()
        comments = data if isinstance(data, list) else (data.get("data") or [])
        assert isinstance(comments, list)


class TestAccountNoteMapping:
    def test_get_mappings(self, client):
        test_pid = "00000000-0000-0000-0000-000000000001"
        resp = client.get(f"/api/account-note-mapping/{test_pid}")
        assert resp.status_code == 200


class TestFormulaAuditLog:
    def test_get_log(self, client):
        test_pid = "00000000-0000-0000-0000-000000000001"
        resp = client.get(f"/api/formula-audit-log/{test_pid}/9999")
        assert resp.status_code == 200


class TestConsolNoteSections:
    def test_get_sections(self, client):
        resp = client.get("/api/consol-note-sections/soe")
        assert resp.status_code == 200
        data = resp.json()
        tree = data if isinstance(data, list) else (data.get("data") or [])
        assert len(tree) > 0  # 至少有章节数据
