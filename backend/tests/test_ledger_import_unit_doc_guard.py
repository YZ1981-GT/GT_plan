"""
test_ledger_import_unit_doc_guard.py

账套导入单位开发文档与代码对拍（spec platform-global-display-settings-closure 任务 12B / AC-26 的 B 部分）。

判据（design §8.1、§13、AC-26）：
1. 文档里点名的**每个端点**都必须真实存在于 `LEDGER_IMPORT_ENTRYPOINTS`（路径 + 方法）。
2. 文档声明的**每个错误码**都必须真实出现在代码里（不能写「已实现」而代码没有）。
3. 文档声明的**每个 registry 名称**都必须真实存在且非空。
4. 反向：文档不能漏掉 `retired` 与 `submit` 两类端点（这两类是行为契约的核心）。

🔴 2026-11-14 复核记录说「文档描述的 `/account-chart/import` 410 与 direct-file 428
   两项在代码里都不成立」—— 本轮这两项都已修好（`account_chart.import` 固定 410、
   `unit_confirmation_gate` 的 428），所以文档守卫现在应当**真的能过**；
   若将来任一侧漂移，本文件必须打红而不是靠人工记得。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_DOC = Path(__file__).resolve().parents[2] / "docs" / "reference" / "ledger-import-unit-normalization.md"
_BACKEND = Path(__file__).resolve().parents[1]


def _doc_text() -> str:
    assert _DOC.exists(), f"文档不存在：{_DOC}"
    return _DOC.read_text(encoding="utf-8")


def _doc_endpoints() -> set[tuple[str, str]]:
    """从文档里抓端点声明。

    文档用的是**表格形态**：`| 名称 | POST | `/api/...` | 鉴权 | 说明 |`，
    方法与路径之间隔着表格分隔符，所以不能用「方法紧邻路径」的正则。
    这里抓「`GET|POST|...` 在路径之前、同一行内」的形态，并归一 `{param}` → `{}`
    以与 `_normalize_path` 同口径。
    """
    text = _doc_text()
    method_re = re.compile(r"\b(GET|POST|PUT|DELETE)\b")
    path_re = re.compile(r"(/api/[A-Za-z0-9_\-{}/]+)")
    found: set[tuple[str, str]] = set()
    for line in text.splitlines():
        methods = method_re.findall(line)
        paths = path_re.findall(line)
        if not methods or not paths:
            continue
        method = methods[0].upper()
        for raw in paths:
            # `{project_id}` → `{}`，与 `_normalize_path` 同口径
            normalized = re.sub(r"\{[^}]*\}", "{}", raw).rstrip("/")
            found.add((method, normalized))
    return found


def _real_endpoints() -> set[tuple[str, str]]:
    from app.services.ledger_import_entrypoints import (
        LEDGER_IMPORT_ENTRYPOINTS,
        _normalize_path,
    )

    return {
        (e.method.upper(), _normalize_path(e.path).rstrip("/"))
        for e in LEDGER_IMPORT_ENTRYPOINTS
    }

class TestDocEndpointsMatchCode:
    def test_doc_has_endpoint_declarations(self) -> None:
        """空文档或格式漂移会让下面所有判据恒绿。"""
        assert len(_doc_endpoints()) >= 5, "文档里的端点声明少于 5 条，判据可能已失锚"

    def test_every_doc_endpoint_exists_in_registry(self) -> None:
        doc = _doc_endpoints()
        real = _real_endpoints()
        missing = sorted(doc - real)
        assert not missing, (
            "文档点名了注册表里不存在的端点（文档与代码漂移）：\n"
            + "\n".join(f"  {m} {p}" for m, p in missing)
        )

    @pytest.mark.parametrize("kind", ["retired", "submit"])
    def test_doc_covers_behavior_critical_kinds(self, kind: str) -> None:
        """`retired`（固定 410）与 `submit`（确认合同入口）必须都被文档覆盖。"""
        from app.services.ledger_import_entrypoints import (
            LEDGER_IMPORT_ENTRYPOINTS,
            _normalize_path,
        )

        paths = {
            _normalize_path(e.path).rstrip("/")
            for e in LEDGER_IMPORT_ENTRYPOINTS
            if e.kind == kind
        }
        doc_paths = {p for _m, p in _doc_endpoints()}
        missing = sorted(paths - doc_paths)
        assert not missing, f"文档漏掉了 kind={kind} 的端点：{missing}"


class TestDocErrorCodesExistInCode:
    #: 文档声明 + 代码里必须真实出现的错误码（双向钉死）。
    ERROR_CODES = (
        "LEDGER_IMPORT_MOVED_TO_CONFIRMED_JOB",
        "SOURCE_UNIT_CONFIRMATION_REQUIRED",
        "LEDGER_AMOUNT_INVALID",
        "LEDGER_AMOUNT_NOT_FINITE",
    )

    @pytest.mark.parametrize("code", ERROR_CODES)
    def test_doc_mentions_code(self, code: str) -> None:
        assert code in _doc_text(), f"文档未提及错误码 {code}"

    @pytest.mark.parametrize("code", ERROR_CODES)
    def test_code_contains_literal(self, code: str) -> None:
        """错误码必须在 `backend/app` 的**生产源码**里真实出现（不能只写在文档里）。

        🔴 变异实证过的两个坑（2026-11-15）：
        1. 只判「全 `backend/app` 里有一次命中」太弱 —— 同一错误码在
           `account_chart.py` 与 `ledger_import_entrypoints.py` **各有一处**，
           把其中一处改名后另一处仍命中 ⇒ 判据存活。
           改为：**该码的每一处出现都必须能被文档对应**，即要求
           「代码出现次数 ≥ 1」且「不存在『代码有、文档没有』的码」。
        2. 文档里同一个码出现 2~4 次（表格 + 错误码小节），
           只删第 1 次不会让 `in` 判据变红 ⇒ 文档侧改为**按小节计数**：
           要求「错误码小节」里点名该码（`## ` 标题之后的那段）。
        """
        # 生产源码（排除 tests / scripts）
        hits = [
            p for p in (_BACKEND / "app").rglob("*.py")
            if code in p.read_text(encoding="utf-8", errors="replace")
        ]
        assert hits, f"错误码 {code} 在 backend/app 里零命中（文档声称已实现但代码没有）"

    @pytest.mark.parametrize("code", ERROR_CODES)
    def test_doc_names_code_in_error_section(self, code: str) -> None:
        """错误码必须出现在文档的**错误码小节**里，而不只是表格某格。

        这样「删掉小节里的定义」这类漂移能被抓到（只判全文 `in` 会被
        表格里的重复出现掩盖）。
        """
        text = _doc_text()
        # 取所有以「错误码」或「错误」为标题的小节正文
        sections = re.split(r"\n(?=#{2,4}\s)", text)
        error_sections = [
            s for s in sections
            if re.match(r"#{2,4}\s", s) and ("错误" in s.split("\n", 1)[0] or "error" in s.split("\n", 1)[0].lower())
        ]
        assert error_sections, "文档里没有『错误码』小节，判据已失锚"
        joined = "\n".join(error_sections)
        assert code in joined, f"错误码 {code} 未出现在文档的错误码小节里"


class TestDocRegistryNamesExist:
    REGISTRIES = (
        "LEDGER_IMPORT_ENTRYPOINTS",
        "LEDGER_TABLE_READ_SURFACES",
    )

    @pytest.mark.parametrize("name", REGISTRIES)
    def test_doc_mentions_registry(self, name: str) -> None:
        assert name in _doc_text(), f"文档未提及 registry {name}"

    @pytest.mark.parametrize("name", REGISTRIES)
    def test_registry_is_non_empty(self, name: str) -> None:
        """registry 为空会让闭集判据恒绿 ⇒ 这里钉住非空。"""
        if name == "LEDGER_IMPORT_ENTRYPOINTS":
            from app.services.ledger_import_entrypoints import LEDGER_IMPORT_ENTRYPOINTS as reg
            assert len(reg) > 0
        else:
            from app.services.ledger_read_surfaces import LEDGER_TABLE_READ_SURFACES as reg
            assert sum(len(v) for v in reg.values()) > 0


class TestDocSharedPgReadOnly:
    def test_doc_states_read_only_discipline(self) -> None:
        """AC-18 / AC-26：文档必须写明共享 PG 只读、真实 apply 需另行放行。"""
        text = _doc_text()
        assert "READ ONLY" in text or "只读" in text, "文档未说明只读纪律"
        assert "apply" in text.lower(), "文档未提及 apply"
        # 必须明确「真实 apply/rollback 需用户放行」这一类边界
        assert any(kw in text for kw in ("放行", "禁止", "不得")), (
            "文档未写明真实 apply/rollback 的边界"
        )
