"""
test_pdf_validation_redaction.py

PDF 创建路由的 422 结构化脱敏（spec platform-global-display-settings-closure 任务 10 / AC-22）。

背景：Pydantic v2 的 `exc.errors()` 条目里 `input` / `context` 会带**原始请求值**。
PDF create 带 `password` 字段，校验失败时会把明文密码回显进 422 响应、应用日志
与审计日志。

判据：
1. PDF create 路径的 422 detail 里**不含** `input` / `context`；
2. 非 PDF 路径**保持原样**（不误伤其他路由的定位信息）；
3. `loc` / `msg` / `type` 必须保留（否则调用方无法定位问题）；
4. 空串 / 超长 / 错误类型 / 「合法密码+额外字段」四种形态都零泄漏；
5. 真实 `main.py` exception handler 生效（不是只测纯函数）。
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.middleware.error_handler import (
    _is_pdf_create_path,
    _redact_validation_detail,
    validation_exception_handler,
)

#: 唯一 marker：任何响应 / 日志里出现它即泄漏。
_SECRET_MARKER = "GT_PDF_SECRET_MARKER_9f3a"


# ── 1. 路径判定 ──────────────────────────────────────────

class TestPathDetection:
    @pytest.mark.parametrize("path", [
        "/api/projects/abc/pdf-export",
        "/api/export/pdf/export",
        "/api/projects/abc/pdf/create",
        "/api/projects/abc/pdf-export/",
    ])
    def test_pdf_create_paths_detected(self, path: str) -> None:
        assert _is_pdf_create_path(path) is True, f"未识别为 PDF 创建路由：{path}"

    @pytest.mark.parametrize("path", [
        "/api/projects/abc/archive/package",
        "/api/projects/abc/ledger-import/submit",
        "/api/projects/abc/trial-balance/export",
        "/api/health",
    ])
    def test_non_pdf_paths_excluded(self, path: str) -> None:
        assert _is_pdf_create_path(path) is False, f"误判为 PDF 创建路由：{path}"


# ── 2. 纯函数脱敏 ────────────────────────────────────────

class TestRedaction:
    def _err(self, marker: str = _SECRET_MARKER) -> list[dict]:
        return [{
            "loc": ["body", "password"],
            "msg": "密码长度必须为 1~127 bytes",
            "type": "value_error",
            "input": marker,
            "context": {"error": marker},
        }]

    def test_input_and_context_removed(self) -> None:
        out = _redact_validation_detail(self._err())
        assert "input" not in out[0]
        assert "context" not in out[0]

    def test_loc_msg_type_preserved(self) -> None:
        out = _redact_validation_detail(self._err())
        assert out[0]["loc"] == ["body", "password"]
        assert out[0]["msg"]
        assert out[0]["type"] == "value_error"

    def test_marker_absent_from_serialized_output(self) -> None:
        """序列化后不得出现 marker（这是 AC-22 的核心断言）。"""
        out = _redact_validation_detail(self._err())
        assert _SECRET_MARKER not in json.dumps(out, ensure_ascii=False)

    def test_nested_lists_redacted(self) -> None:
        nested = [{"loc": ["body"], "type": "x", "input": {"a": _SECRET_MARKER}}]
        out = _redact_validation_detail(nested)
        assert "input" not in out[0]

    def test_non_dict_items_pass_through(self) -> None:
        assert _redact_validation_detail(["plain", 1, None]) == ["plain", 1, None]

    def test_empty_detail(self) -> None:
        assert _redact_validation_detail([]) == []


# ── 3. 真实 exception handler（TestClient）────────────────

class _PdfCreateBody(BaseModel):
    """模拟 PDF create 的请求体（带 password 与 extra='forbid'）。"""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    year: int = Field(ge=2000, le=2100)
    password: str | None = None

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if v == "":
            raise ValueError("密码不能为空")
        if len(v.encode("utf-8")) >= 128:
            raise ValueError("密码长度不得超过 127 bytes")
        return v


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    @app.post("/api/projects/{project_id}/pdf-export")
    async def pdf_export(body: _PdfCreateBody):  # pragma: no cover - 只用于触发 422
        return {"ok": True}

    @app.post("/api/projects/{project_id}/ledger-import/submit")
    async def other_route(body: _PdfCreateBody):  # pragma: no cover
        return {"ok": True}

    return app


def _detail_items(text: str) -> list[dict]:
    """取 422 响应的 detail 条目（判 JSON 键，不用子串）。"""
    return json.loads(text)["detail"]


class TestRealHandler:
    @pytest.fixture()
    def client(self) -> TestClient:
        return TestClient(_make_app(), raise_server_exceptions=False)

    def _post(self, client: TestClient, path: str, payload: dict) -> tuple[int, str]:
        resp = client.post(path, json=payload)
        return resp.status_code, resp.text

    def test_password_empty_no_leak(self, client: TestClient) -> None:
        """空密码：422 且响应里无 input/context/marker。"""
        code, text = self._post(
            client, "/api/projects/p1/pdf-export",
            {"project_id": "p1", "year": 2025, "password": ""},
        )
        assert code == 422
        for item in _detail_items(text):
            assert "input" not in item, "空密码时 input 未脱敏"
            assert "context" not in item, "空密码时 context 未脱敏"
        assert _SECRET_MARKER not in text

    def test_password_too_long_no_leak(self, client: TestClient) -> None:
        """超长密码：mutation marker 不得出现在响应里。"""
        long_pwd = _SECRET_MARKER + "x" * 200
        code, text = self._post(
            client, "/api/projects/p1/pdf-export",
            {"project_id": "p1", "year": 2025, "password": long_pwd},
        )
        assert code == 422
        assert _SECRET_MARKER not in text, "超长密码泄漏进 422 响应"
        for item in _detail_items(text):
            assert "input" not in item

    def test_wrong_type_no_leak(self, client: TestClient) -> None:
        """错误类型（dict 而非 str）：同样不得回显原始值。"""
        code, text = self._post(
            client, "/api/projects/p1/pdf-export",
            {"project_id": "p1", "year": 2025, "password": {"secret": _SECRET_MARKER}},
        )
        assert code == 422
        assert _SECRET_MARKER not in text
        for item in _detail_items(text):
            assert "input" not in item

    def test_valid_password_plus_extra_field_no_leak(self, client: TestClient) -> None:
        """合法密码 + 额外字段：extra='forbid' 报错，但密码不得回显。"""
        code, text = self._post(
            client, "/api/projects/p1/pdf-export",
            {
                "project_id": "p1",
                "year": 2025,
                "password": _SECRET_MARKER,
                "bogus_extra": 1,
            },
        )
        assert code == 422
        assert _SECRET_MARKER not in text, "合法密码+额外字段时密码泄漏"
        # 🔴 判 JSON 键而非子串：`"input"` 是 Pydantic 消息
        # "Extra inputs are not permitted" 的子串（本轮实测 1 例假红）
        detail = json.loads(text)["detail"]
        for item in detail:
            assert "input" not in item
            assert "context" not in item

    def test_non_pdf_path_keeps_input(self, client: TestClient) -> None:
        """非 PDF 路径**保持原样**（不误伤其他路由的定位信息）。"""
        code, text = self._post(
            client, "/api/projects/p1/ledger-import/submit",
            {"project_id": "p1", "year": 1999},  # year 越界
        )
        assert code == 422
        # 非 PDF 路径不脱敏：input 应仍在
        assert "input" in text or "context" in text, (
            "非 PDF 路径也被脱敏了，会削弱其他路由的问题定位"
        )


# ── 4. 真实 main.py handler 已注册 ───────────────────────

class TestMainRegistration:
    def test_validation_handler_registered_in_main(self) -> None:
        """`main.py` 必须注册本 handler（否则真实应用走的还是 FastAPI 默认处理器）。"""
        from pathlib import Path

        p = Path(__file__).resolve().parents[1] / "app" / "main.py"
        src = p.read_text(encoding="utf-8")
        assert "validation_exception_handler" in src, (
            "main.py 未注册 validation_exception_handler"
        )

    def test_redaction_helpers_exist(self) -> None:
        from app.middleware import error_handler as mod

        assert hasattr(mod, "_is_pdf_create_path")
        assert hasattr(mod, "_redact_validation_detail")


class TestNoOverRedaction:
    """反向边界：脱敏**只删** `input`/`context`，`loc`/`msg`/`type` 必须保留。

    🔴 变异实证（2026-11-16）：把判据改成「只留 loc/msg/type 之外的全删」
    （即删掉 loc/msg/type 本身）时，此前的用例**全绿**存活 —— 因为那些用例
    只断言 `input`/`context` 不在，从不正向断言定位字段还在。
    过度脱敏会让调用方无法知道**哪个字段**错了，比泄漏更隐蔽地破坏可用性。
    """

    def _err_with_all_keys(self) -> list[dict]:
        return [{
            "loc": ["body", "year"],
            "msg": "Input should be greater than or equal to 2000",
            "type": "greater_than_equal",
            "input": _SECRET_MARKER,
            "context": {"ge": 2000},
        }]

    def test_loc_survives_redaction(self) -> None:
        out = _redact_validation_detail(self._err_with_all_keys())
        assert "loc" in out[0], "loc 被删了，调用方无法定位字段"
        assert out[0]["loc"] == ["body", "year"]

    def test_msg_survives_redaction(self) -> None:
        out = _redact_validation_detail(self._err_with_all_keys())
        assert "msg" in out[0] and out[0]["msg"], "msg 被删了，调用方看不到原因"

    def test_type_survives_redaction(self) -> None:
        out = _redact_validation_detail(self._err_with_all_keys())
        assert "type" in out[0], "type 被删了，前端无法做本地化"

    def test_real_handler_keeps_loc_and_msg(self) -> None:
        """真实 handler 的响应里必须能读到 loc 与 msg。"""
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.post(
            "/api/projects/p1/pdf-export",
            json={"project_id": "p1", "year": 1999},  # year 越界
        )
        assert resp.status_code == 422
        items = resp.json()["detail"]
        assert items, "422 没有 detail 条目"
        assert any(item.get("loc") for item in items), "所有条目的 loc 都没了"
        assert any(item.get("msg") for item in items), "所有条目的 msg 都没了"

    def test_only_two_keys_removed(self) -> None:
        """精确断言：只删 input/context，其余键一个不少。"""
        err = self._err_with_all_keys()
        out = _redact_validation_detail(err)
        expected_keys = set(err[0]) - {"input", "context"}
        assert set(out[0]) == expected_keys, (
            f"键集合不符：期望 {sorted(expected_keys)}，实得 {sorted(out[0])}"
        )
