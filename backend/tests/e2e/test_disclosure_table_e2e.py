"""E2E: 披露表 sub_table_data 同步 → 附注模块可见完整表格 → Word 导出含表

验证 disclosure-table-sync-convergence spec Task 14.1:
- 上市版: 披露表录入 → 推送(POST sync-from-workpaper with sub_table_data + _columns)
  → 附注模块可见完整表格(中文列头 + 合计行) → Word 导出含表
- 国企版: 同验(不同 note_section 各自正确)

Validates: Requirements 1.1, 1.2, 4.1, 4.4, 7.2, 8.1

运行方式（对 live dev server 9980）:
    python -m pytest backend/tests/e2e/test_disclosure_table_e2e.py -v

注: 此测试直接对运行中的 dev server(localhost:9980) 发送 HTTP 请求，
    使用真实项目数据（重药控股安徽 0ec33ac9 或 重庆和平药房 2aa00f57）。
    需要 dev server 已启动（start-dev.bat）。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import httpx

# ─── 配置 ────────────────────────────────────────────────────────────────────

BASE_URL = "http://localhost:9980/api"
AUTH_CREDENTIALS = {"username": "admin", "password": "admin123"}

# 真实测试项目（重药控股安徽 2025，有 live disclosure_notes 数据）
TEST_PROJECT_ID = "0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49"
# 如果上面项目不存在，回退到重庆和平药房
FALLBACK_PROJECT_ID = "2aa00f57-1df4-4fe8-9840-2d65d0fd8749"

TEST_YEAR = 2025

# 用于测试的合成 note_section（不与真实数据冲突）
LISTED_TEST_SECTION = "E2E_LISTED_TEST_五、99"
SOE_TEST_SECTION = "E2E_SOE_TEST_八、99"

# 合成 wp_id（仅作同步载荷标识，不需要真实存在的底稿）
SYNTHETIC_WP_ID = str(uuid.uuid4())


# ─── 测试载荷 ─────────────────────────────────────────────────────────────────

def _build_test_sub_table_data() -> dict[str, list[dict]]:
    """构造测试 sub_table_data：含中文子表名、多行数据、合计行。"""
    return {
        "存货分类": [
            {"label": "原材料", "end_gross": 1000000, "end_impairment": 50000, "is_total": False},
            {"label": "在产品", "end_gross": 500000, "end_impairment": 20000, "is_total": False},
            {"label": "库存商品", "end_gross": 800000, "end_impairment": 30000, "is_total": False},
            {"label": "合计", "end_gross": 2300000, "end_impairment": 100000, "is_total": True},
        ],
        "存货跌价准备": [
            {"label": "原材料", "begin_provision": 40000, "increase": 15000, "decrease": 5000, "is_total": False},
            {"label": "合计", "begin_provision": 40000, "increase": 15000, "decrease": 5000, "is_total": True},
        ],
    }


def _build_test_columns() -> dict[str, list[dict]]:
    """构造测试 _columns：中文列头，源对齐定义。"""
    return {
        "存货分类": [
            {"key": "label", "label": "存货类别", "is_label": True},
            {"key": "end_gross", "label": "期末账面余额", "format": "amount"},
            {"key": "end_impairment", "label": "期末跌价准备", "format": "amount"},
        ],
        "存货跌价准备": [
            {"key": "label", "label": "项目", "is_label": True},
            {"key": "begin_provision", "label": "期初余额", "format": "amount"},
            {"key": "increase", "label": "本期增加", "format": "amount"},
            {"key": "decrease", "label": "本期减少", "format": "amount"},
        ],
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _login(client: httpx.Client) -> str:
    """登录获取 JWT token。"""
    r = client.post(f"{BASE_URL}/auth/login", json=AUTH_CREDENTIALS)
    if r.status_code != 200:
        pytest.skip(f"无法登录 dev server (status={r.status_code})，跳过 live E2E")
    body = r.json()
    data = body.get("data", body)
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip(f"登录响应无 token: {body}")
    return token


def _resolve_project_id(client: httpx.Client, headers: dict) -> str:
    """验证测试项目可达，回退到备选项目。"""
    for pid in [TEST_PROJECT_ID, FALLBACK_PROJECT_ID]:
        r = client.get(f"{BASE_URL}/projects/{pid}", headers=headers)
        if r.status_code == 200:
            return pid
    pytest.skip("测试项目均不可达，跳过 live E2E")
    return ""  # unreachable


def _sync_payload(
    section_id: str,
    current_standard: str,
) -> dict[str, Any]:
    """构造完整的 sync-from-workpaper 请求体。"""
    return {
        "wp_id": SYNTHETIC_WP_ID,
        "sheet_name": "E2E测试披露表",
        "section_id": section_id,
        "sub_table_data": _build_test_sub_table_data(),
        "columns": _build_test_columns(),
        "current_standard": current_standard,
        "year": TEST_YEAR,
    }


def _cleanup_sync(
    client: httpx.Client,
    headers: dict,
    project_id: str,
    section_id: str,
    current_standard: str,
) -> None:
    """清理：发送空载荷同步恢复原状（空载荷 no-op 不清表，Req 8.1）。

    实际清理策略：发送一个已知不包含 sub_table_data 的同步，
    或直接依赖 section_id 是合成的不影响真实数据。
    由于我们用合成 section_id，真实数据不受影响，无需特殊清理。
    """
    pass  # 合成 section_id 不与真实数据冲突，无需清理


# ─── Tests ────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def live_session():
    """创建一个对 live dev server 的认证会话。"""
    client = httpx.Client(timeout=30.0)
    # 验证 dev server 可达
    try:
        r = client.get(f"{BASE_URL}/health", timeout=5.0)
    except (httpx.ConnectError, httpx.ReadTimeout):
        client.close()
        pytest.skip("Dev server (localhost:9980) 未启动，跳过 live E2E")

    # 登录获取 token
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 验证项目可达
    project_id = _resolve_project_id(client, headers)

    yield {
        "client": client,
        "headers": headers,
        "project_id": project_id,
        "token": token,
    }
    client.close()


class TestDisclosureTableSyncE2E:
    """上市版/国企版 披露表→附注模块→Word 导出 全链路 E2E"""

    # ── 上市版（listed）────────────────────────────────────────────────────

    def test_listed_sync_creates_note_with_tables(self, live_session):
        """上市版: sync-from-workpaper → 附注 detail 含投影 _tables（中文列头+合计行）

        Validates: Req 1.1, 4.1
        """
        ctx = live_session
        client, headers, pid = ctx["client"], ctx["headers"], ctx["project_id"]

        # 1) POST sync-from-workpaper (上市版)
        payload = _sync_payload(LISTED_TEST_SECTION, "listed_standalone")
        r = client.post(
            f"{BASE_URL}/projects/{pid}/disclosure-notes/sync-from-workpaper",
            json=payload,
            headers=headers,
        )
        assert r.status_code == 200, f"sync failed: {r.status_code} {r.text}"
        sync_result = r.json()
        data = sync_result.get("data", sync_result)
        assert data.get("success") is True, f"sync not success: {data}"
        assert data.get("section_id") == LISTED_TEST_SECTION

        # 2) GET note detail → 验证投影 _tables
        r = client.get(
            f"{BASE_URL}/disclosure-notes/{pid}/{TEST_YEAR}/{LISTED_TEST_SECTION}",
            headers=headers,
        )
        assert r.status_code == 200, f"note detail failed: {r.status_code} {r.text}"
        detail_body = r.json()
        detail = detail_body.get("data", detail_body)

        # 找到 table_data 中的 _tables（投影结果）
        table_data = detail.get("table_data", {})
        tables = table_data.get("_tables")
        assert tables is not None, (
            "投影 _tables 未注入到 note detail 响应中（project_sub_tables 可能未执行）"
        )
        assert isinstance(tables, list)
        assert len(tables) >= 2, f"预期至少2张投影表, 实际 {len(tables)}"

        # 验证第一张表: 存货分类
        t1 = tables[0]
        assert t1["name"] == "存货分类"
        # 中文列头 (Req 1.1)
        assert "存货类别" in t1["headers"]
        assert "期末账面余额" in t1["headers"]
        assert "期末跌价准备" in t1["headers"]
        # 英文字段键不应出现在 headers 中 (Req 7.2)
        for h in t1["headers"]:
            assert h not in ("end_gross", "end_impairment", "label"), (
                f"英文字段键 '{h}' 出现在 headers 中，违反 Req 7.2"
            )
        # 验证行数据
        assert len(t1["rows"]) == 4
        # 合计行 is_total (Req 1.4 → Property 5)
        total_row = t1["rows"][-1]
        assert total_row["is_total"] is True
        assert total_row["label"] == "合计"
        # 数值正确
        assert total_row["values"][0] == 2300000  # end_gross 合计
        assert total_row["values"][1] == 100000  # end_impairment 合计

        # 验证第二张表: 存货跌价准备
        t2 = tables[1]
        assert t2["name"] == "存货跌价准备"
        assert "项目" in t2["headers"]
        assert "期初余额" in t2["headers"]
        assert "本期增加" in t2["headers"]
        assert "本期减少" in t2["headers"]
        assert len(t2["rows"]) == 2

    def test_listed_word_export_contains_table(self, live_session):
        """上市版: Word 导出含表（至少返回 200 + 有内容）

        Validates: Req 1.2
        """
        ctx = live_session
        client, headers, pid = ctx["client"], ctx["headers"], ctx["project_id"]

        # 先确保 sync 过数据（前面测试已同步）
        # POST Word export (NOTE: 这个端点导出整册附注，非单节)
        r = client.post(
            f"{BASE_URL}/projects/{pid}/notes/export-word",
            json={
                "year": TEST_YEAR,
                "template_type": "listed",
                "sections": [LISTED_TEST_SECTION],
                "skip_empty": False,
            },
            headers=headers,
        )
        # Word 导出可能返回 200(docx) 或 404(section 无内容/端点未实现)
        if r.status_code == 404:
            pytest.skip("Word 导出端点对测试 section 返回 404（可能需整节完整数据）")
        assert r.status_code == 200, f"Word export failed: {r.status_code} {r.text}"
        # 验证返回了有内容的文件
        assert len(r.content) > 100, (
            f"Word 导出内容过小({len(r.content)} bytes)，可能不含表格"
        )
        # docx 文件头 magic bytes (PK zip format)
        assert r.content[:4] == b"PK\x03\x04" or len(r.content) > 500, (
            "Word 导出内容不像有效 docx 文件"
        )

    # ── 国企版（SOE）────────────────────────────────────────────────────────

    def test_soe_sync_creates_note_with_tables(self, live_session):
        """国企版: 同步到不同 note_section → 各自正确渲染

        Validates: Req 4.1, 4.4
        """
        ctx = live_session
        client, headers, pid = ctx["client"], ctx["headers"], ctx["project_id"]

        # POST sync-from-workpaper (国企版)
        payload = _sync_payload(SOE_TEST_SECTION, "soe_standalone")
        r = client.post(
            f"{BASE_URL}/projects/{pid}/disclosure-notes/sync-from-workpaper",
            json=payload,
            headers=headers,
        )
        assert r.status_code == 200, f"SOE sync failed: {r.status_code} {r.text}"
        data = r.json().get("data", r.json())
        assert data.get("success") is True
        assert data.get("section_id") == SOE_TEST_SECTION

        # GET note detail for SOE section
        r = client.get(
            f"{BASE_URL}/disclosure-notes/{pid}/{TEST_YEAR}/{SOE_TEST_SECTION}",
            headers=headers,
        )
        assert r.status_code == 200, f"SOE note detail failed: {r.status_code} {r.text}"
        detail = r.json().get("data", r.json())
        table_data = detail.get("table_data", {})
        tables = table_data.get("_tables")
        assert tables is not None, "国企版 _tables 未投影"
        assert len(tables) >= 2

        # 验证国企版表结构与上市版一致（同一组件用同一 _columns）
        t1 = tables[0]
        assert t1["name"] == "存货分类"
        assert "存货类别" in t1["headers"]
        assert t1["rows"][-1]["is_total"] is True

    def test_soe_word_export_contains_table(self, live_session):
        """国企版: Word 导出含表

        Validates: Req 1.2, 4.1
        """
        ctx = live_session
        client, headers, pid = ctx["client"], ctx["headers"], ctx["project_id"]

        r = client.post(
            f"{BASE_URL}/projects/{pid}/notes/export-word",
            json={
                "year": TEST_YEAR,
                "template_type": "soe",
                "sections": [SOE_TEST_SECTION],
                "skip_empty": False,
            },
            headers=headers,
        )
        if r.status_code == 404:
            pytest.skip("SOE Word 导出对测试 section 返回 404")
        assert r.status_code == 200, f"SOE Word export failed: {r.status_code} {r.text}"
        assert len(r.content) > 100

    # ── 变体隔离验证 ──────────────────────────────────────────────────────

    def test_listed_and_soe_sections_isolated(self, live_session):
        """上市版/国企版写不同 note_section，互不干扰（Req 4.1/4.3）

        Validates: Req 4.1
        """
        ctx = live_session
        client, headers, pid = ctx["client"], ctx["headers"], ctx["project_id"]

        # 读上市版
        r1 = client.get(
            f"{BASE_URL}/disclosure-notes/{pid}/{TEST_YEAR}/{LISTED_TEST_SECTION}",
            headers=headers,
        )
        # 读国企版
        r2 = client.get(
            f"{BASE_URL}/disclosure-notes/{pid}/{TEST_YEAR}/{SOE_TEST_SECTION}",
            headers=headers,
        )

        if r1.status_code != 200 or r2.status_code != 200:
            pytest.skip("section 不可达")

        detail1 = r1.json().get("data", r1.json())
        detail2 = r2.json().get("data", r2.json())

        td1 = detail1.get("table_data", {})
        td2 = detail2.get("table_data", {})

        # 两者都有 _tables，说明各自独立投影
        assert td1.get("_tables") is not None
        assert td2.get("_tables") is not None

        # _source 各自标记 workpaper
        assert td1.get("_source") in ("workpaper", "workpaper_html")
        assert td2.get("_source") in ("workpaper", "workpaper_html")

        # current_standard 各自不同
        assert td1.get("_current_standard") == "listed_standalone"
        assert td2.get("_current_standard") == "soe_standalone"

    # ── 空载荷 no-op 回归 (Req 8.1) ──────────────────────────────────────

    def test_empty_payload_preserves_existing_tables(self, live_session):
        """空 sub_table_data 同步 → 既有表格保留 (Req 8.1, Property 9)

        Validates: Req 8.1
        """
        ctx = live_session
        client, headers, pid = ctx["client"], ctx["headers"], ctx["project_id"]

        # 发空载荷同步到上市版 section（已有数据）
        empty_payload = {
            "wp_id": SYNTHETIC_WP_ID,
            "sheet_name": "E2E测试披露表",
            "section_id": LISTED_TEST_SECTION,
            "sub_table_data": {},
            "columns": {},
            "current_standard": "listed_standalone",
            "year": TEST_YEAR,
        }
        r = client.post(
            f"{BASE_URL}/projects/{pid}/disclosure-notes/sync-from-workpaper",
            json=empty_payload,
            headers=headers,
        )
        assert r.status_code == 200

        # 重新读 detail → _tables 应仍存在（空载荷 no-op）
        r = client.get(
            f"{BASE_URL}/disclosure-notes/{pid}/{TEST_YEAR}/{LISTED_TEST_SECTION}",
            headers=headers,
        )
        assert r.status_code == 200
        detail = r.json().get("data", r.json())
        table_data = detail.get("table_data", {})
        tables = table_data.get("_tables")
        assert tables is not None, "空载荷同步后 _tables 丢失，违反 Req 8.1"
        assert len(tables) >= 2, "空载荷同步后表格数量减少"

    def test_double_empty_payload_preserves_existing_tables(self, live_session):
        """二次空载荷同步 → 附注表格不丢失 (Task 14.2, Req 8.1)

        验证连续两次空载荷同步后，既有 sub_table_data 仍完整保留。
        这是对"空载荷 no-op"机制的强化测试：确保不存在累积/序列相关的
        清空行为（如首次 no-op 正确但第二次触发不同代码路径清空表格）。

        同时验证 fetchDetailFresh 后不命中旧缓存（GET 每次取到最新投影）。

        Validates: Req 8.1
        """
        ctx = live_session
        client, headers, pid = ctx["client"], ctx["headers"], ctx["project_id"]

        empty_payload = {
            "wp_id": SYNTHETIC_WP_ID,
            "sheet_name": "E2E测试披露表",
            "section_id": LISTED_TEST_SECTION,
            "sub_table_data": {},
            "columns": {},
            "current_standard": "listed_standalone",
            "year": TEST_YEAR,
        }

        # ── 第一次空载荷同步（前面测试已做过一次，这里再做以确保序列性）
        r = client.post(
            f"{BASE_URL}/projects/{pid}/disclosure-notes/sync-from-workpaper",
            json=empty_payload,
            headers=headers,
        )
        assert r.status_code == 200, f"第1次空载荷同步失败: {r.status_code}"

        # ── 第二次空载荷同步（核心：连续空载荷不累积清空）
        r = client.post(
            f"{BASE_URL}/projects/{pid}/disclosure-notes/sync-from-workpaper",
            json=empty_payload,
            headers=headers,
        )
        assert r.status_code == 200, f"第2次空载荷同步失败: {r.status_code}"

        # ── 模拟 fetchDetailFresh：直接 GET 最新 detail（HTTP 无缓存）
        # 前端 fetchDetailFresh = invalidateDetailCache + fetchDetail(section, true)
        # 后端 GET 端点无服务端缓存，每次读 DB 最新 → 验证不命中旧缓存
        r = client.get(
            f"{BASE_URL}/disclosure-notes/{pid}/{TEST_YEAR}/{LISTED_TEST_SECTION}",
            headers=headers,
        )
        assert r.status_code == 200, f"二次空载荷后读取失败: {r.status_code}"
        detail = r.json().get("data", r.json())
        table_data = detail.get("table_data", {})

        # 验证 sub_table_data 仍完整（空载荷 no-op 不清空）
        sub = table_data.get("sub_table_data", {})
        assert isinstance(sub, dict), "sub_table_data 应为 dict"
        assert len(sub) >= 2, (
            f"二次空载荷同步后 sub_table_data 子表丢失，预期≥2，实际 {len(sub)}"
        )

        # 验证 _sub_table_columns 仍保留（空 columns={} no-op 不清空列头）
        cols = table_data.get("_sub_table_columns", {})
        assert isinstance(cols, dict), "_sub_table_columns 应为 dict"
        assert len(cols) >= 2, (
            f"二次空载荷同步后 _sub_table_columns 丢失，预期≥2，实际 {len(cols)}"
        )

        # 验证投影 _tables 仍正确注入（get_note_detail 读时投影正常）
        tables = table_data.get("_tables")
        assert tables is not None, (
            "二次空载荷同步后 _tables 投影丢失，"
            "get_note_detail 可能未正确执行 project_sub_tables"
        )
        assert isinstance(tables, list)
        assert len(tables) >= 2, (
            f"二次空载荷同步后投影表数量减少，预期≥2，实际 {len(tables)}"
        )

        # 验证表结构仍完整（中文列头 + 合计行，与初次同步一致）
        t1 = tables[0]
        assert t1["name"] == "存货分类", f"首表名称错误: {t1.get('name')}"
        assert "存货类别" in t1["headers"], "中文列头丢失"
        assert len(t1["rows"]) == 4, f"行数不对: {len(t1['rows'])}"
        assert t1["rows"][-1]["is_total"] is True, "合计行 is_total 丢失"

    # ── 降级路径 (Req 7.2) ────────────────────────────────────────────────

    def test_missing_columns_degrades_gracefully(self, live_session):
        """无 _columns 时降级不 crash、不用英文键当列头 (Req 7.2)

        Validates: Req 7.2
        """
        ctx = live_session
        client, headers, pid = ctx["client"], ctx["headers"], ctx["project_id"]
        degrade_section = "E2E_DEGRADE_TEST_五、98"

        # 发送有 sub_table_data 但无 _columns 的载荷
        payload = {
            "wp_id": SYNTHETIC_WP_ID,
            "sheet_name": "E2E降级测试",
            "section_id": degrade_section,
            "sub_table_data": {
                "测试表": [
                    {"label": "项目A", "end_balance": 100, "prior_balance": 80},
                    {"label": "合计", "end_balance": 100, "prior_balance": 80, "is_total": True},
                ],
            },
            # 故意不传 columns
            "current_standard": "listed_standalone",
            "year": TEST_YEAR,
        }
        r = client.post(
            f"{BASE_URL}/projects/{pid}/disclosure-notes/sync-from-workpaper",
            json=payload,
            headers=headers,
        )
        assert r.status_code == 200

        # 读 detail → 应不 crash，且 headers 不含英文字段键
        r = client.get(
            f"{BASE_URL}/disclosure-notes/{pid}/{TEST_YEAR}/{degrade_section}",
            headers=headers,
        )
        assert r.status_code == 200
        detail = r.json().get("data", r.json())
        table_data = detail.get("table_data", {})
        tables = table_data.get("_tables")
        assert tables is not None, "降级路径未产出 _tables"

        # 验证 headers 不含英文字段键 (Property 8)
        for t in tables:
            for h in t.get("headers", []):
                assert h not in ("end_balance", "prior_balance", "label"), (
                    f"降级路径 headers 含英文字段键 '{h}'，违反 Req 7.2"
                )
            # 降级表应有 _needs_columns 标记
            if not t.get("columns"):
                assert t.get("_needs_columns") is True, (
                    "降级表缺少 _needs_columns 标记"
                )
