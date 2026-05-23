"""K-2 审计复核提示词路由测试

spec proposal-remaining-18 task 2.5

覆盖：
- happy path：cycle_name = 字母代号 / 中文名分别返回正确文件内容
- 404：cycle_name 不匹配任何文件
- 404：TSJ 目录缺失
- 大小写不敏感：'e' 和 'E' 同样匹配货币资金
- list 端点：返回文件清单
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.routers.knowledge_tsj import router as tsj_router


class _FakeUser:
    def __init__(self, uid: str = "u-1"):
        self.id = uid
        self.username = "tester"
        self.email = "t@test.com"
        self.is_active = True


def _make_app(tsj_dir: Path | None, monkeypatch=None) -> FastAPI:
    """创建带 TSJ 路由的测试应用。

    若提供 tsj_dir，则通过环境变量重定向 TSJ 目录；否则使用默认仓库 TSJ/。
    """
    app = FastAPI()
    app.include_router(tsj_router)

    async def _override_user():
        return _FakeUser()

    app.dependency_overrides[get_current_user] = _override_user
    return app


def _seed_tsj_dir(tmp_path: Path) -> Path:
    """创建一个临时 TSJ 目录并放入若干 .md 文件用于测试。"""
    tsj = tmp_path / "TSJ"
    tsj.mkdir()
    (tsj / "货币资金提示词.md").write_text(
        "# 货币资金审计复核提示词\n\n本提示词覆盖银行存款、库存现金等账户。",
        encoding="utf-8",
    )
    (tsj / "应收账款审计复核提示词.md").write_text(
        "# 应收账款审计复核提示词\n\n关注坏账准备的合理性。",
        encoding="utf-8",
    )
    (tsj / "存货审计复核提示词.md").write_text(
        "# 存货审计复核提示词\n\n关注监盘和跌价准备。",
        encoding="utf-8",
    )
    (tsj / "管理费用审计复核提示词.md").write_text(
        "# 管理费用审计复核提示词\n\n关注期间费用归集是否合理。",
        encoding="utf-8",
    )
    (tsj / "审计方案提示词.md").write_text(
        "# 审计方案提示词",
        encoding="utf-8",
    )
    return tsj


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_tsj_by_letter_code_E_returns_currency_prompt(tmp_path, monkeypatch):
    """字母代号 E → 货币资金提示词。"""
    seed = _seed_tsj_dir(tmp_path)
    monkeypatch.setenv("TSJ_KNOWLEDGE_DIR", str(seed))

    app = _make_app(seed)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/knowledge/tsj/E")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["cycle_name"] == "E"
    assert data["source_file"] == "货币资金提示词.md"
    assert "货币资金" in data["markdown"]


@pytest.mark.asyncio
async def test_get_tsj_letter_code_case_insensitive(tmp_path, monkeypatch):
    """字母代号大小写不敏感：'e' 和 'E' 等价。"""
    seed = _seed_tsj_dir(tmp_path)
    monkeypatch.setenv("TSJ_KNOWLEDGE_DIR", str(seed))

    app = _make_app(seed)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp_lower = await ac.get("/api/knowledge/tsj/e")
        resp_upper = await ac.get("/api/knowledge/tsj/E")

    assert resp_lower.status_code == 200
    assert resp_upper.status_code == 200
    assert resp_lower.json()["source_file"] == resp_upper.json()["source_file"]


@pytest.mark.asyncio
async def test_get_tsj_by_chinese_name_inventory(tmp_path, monkeypatch):
    """中文 cycle_name='存货' → 存货审计复核提示词。"""
    seed = _seed_tsj_dir(tmp_path)
    monkeypatch.setenv("TSJ_KNOWLEDGE_DIR", str(seed))

    app = _make_app(seed)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/knowledge/tsj/存货")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["source_file"] == "存货审计复核提示词.md"
    assert "存货" in data["markdown"]


@pytest.mark.asyncio
async def test_get_tsj_letter_code_K_returns_admin_expense(tmp_path, monkeypatch):
    """字母代号 K → 管理费用提示词（按 _LETTER_KEYWORDS 'K' 第一个命中）。"""
    seed = _seed_tsj_dir(tmp_path)
    monkeypatch.setenv("TSJ_KNOWLEDGE_DIR", str(seed))

    app = _make_app(seed)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/knowledge/tsj/K")

    assert resp.status_code == 200, resp.text
    assert resp.json()["source_file"] == "管理费用审计复核提示词.md"


@pytest.mark.asyncio
async def test_get_tsj_letter_code_S_returns_audit_plan(tmp_path, monkeypatch):
    """字母代号 S → 审计方案提示词（专项程序）。"""
    seed = _seed_tsj_dir(tmp_path)
    monkeypatch.setenv("TSJ_KNOWLEDGE_DIR", str(seed))

    app = _make_app(seed)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/knowledge/tsj/S")

    assert resp.status_code == 200, resp.text
    assert resp.json()["source_file"] == "审计方案提示词.md"


# ---------------------------------------------------------------------------
# 404 错误路径
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_tsj_unknown_cycle_returns_404(tmp_path, monkeypatch):
    """未知 cycle_name → 404。"""
    seed = _seed_tsj_dir(tmp_path)
    monkeypatch.setenv("TSJ_KNOWLEDGE_DIR", str(seed))

    app = _make_app(seed)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/knowledge/tsj/不存在的循环XYZ")

    assert resp.status_code == 404
    assert "未找到" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_tsj_unmatched_letter_returns_404(tmp_path, monkeypatch):
    """字母代号 'Z' 不在 _LETTER_KEYWORDS 字典 → 404。"""
    seed = _seed_tsj_dir(tmp_path)
    monkeypatch.setenv("TSJ_KNOWLEDGE_DIR", str(seed))

    app = _make_app(seed)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/knowledge/tsj/Z")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_tsj_letter_with_no_match_files_returns_404(tmp_path, monkeypatch):
    """字母代号 H（关键字含'固定资产'）但 TSJ 目录中无匹配文件 → 404。"""
    # 仅放一个货币资金文件，没有固定资产相关
    tsj = tmp_path / "TSJ_minimal"
    tsj.mkdir()
    (tsj / "货币资金提示词.md").write_text("# 货币资金", encoding="utf-8")
    monkeypatch.setenv("TSJ_KNOWLEDGE_DIR", str(tsj))

    app = _make_app(tsj)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/knowledge/tsj/H")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_tsj_when_directory_missing_returns_404(tmp_path, monkeypatch):
    """TSJ 目录不存在 → 404（任何 cycle_name 都失败）。"""
    nonexistent = tmp_path / "no-such-dir"
    monkeypatch.setenv("TSJ_KNOWLEDGE_DIR", str(nonexistent))

    app = _make_app(nonexistent)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/knowledge/tsj/E")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# list 端点
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tsj_returns_all_files(tmp_path, monkeypatch):
    """GET /api/knowledge/tsj 返回 TSJ 目录下全部 .md 文件。"""
    seed = _seed_tsj_dir(tmp_path)
    monkeypatch.setenv("TSJ_KNOWLEDGE_DIR", str(seed))

    app = _make_app(seed)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/knowledge/tsj")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    # seed 中放了 5 个文件
    assert data["count"] == 5
    assert "货币资金提示词.md" in data["files"]
    assert "存货审计复核提示词.md" in data["files"]


@pytest.mark.asyncio
async def test_list_tsj_when_directory_missing(tmp_path, monkeypatch):
    """目录缺失 → count=0, files=[]。"""
    nonexistent = tmp_path / "no-tsj"
    monkeypatch.setenv("TSJ_KNOWLEDGE_DIR", str(nonexistent))

    app = _make_app(nonexistent)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/knowledge/tsj")

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["files"] == []


# ---------------------------------------------------------------------------
# 真实仓库 TSJ/ 目录烟雾测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_tsj_dir_E_returns_currency_prompt():
    """烟雾测试：默认 TSJ/ 目录中 cycle_name=E 应能命中货币资金提示词.md。

    依赖仓库根 TSJ/ 目录中的真实文件（70 份 + B60 总体审计策略）。
    """
    app = _make_app(None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/knowledge/tsj/E")

    if resp.status_code == 404:
        pytest.skip("仓库 TSJ/ 目录不存在，跳过真实文件烟雾测试")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "货币资金" in data["source_file"]
    assert "货币资金" in data["markdown"]
