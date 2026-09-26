"""判据：畸形 store 载荷必须抛 **domain 错误（4xx）**，不得冒泡成 opaque 500。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 16/17 回归修复 · Requirement 4.2

═══ 这条判据补的是什么洞 ═══

Task 16/17 把 D3/D5/D6/D7 的 `build_store_projection` 收敛成薄转发框架层，但**漏了
错误转译**：框架层抛 `RowTableStorePayloadError(Exception)`（有意设计成非 domain 错误，
见其 docstring「provider 侧薄转发时按需转译」），而收敛前各 provider 抛
`StorePayloadError(SyncDomainError)` 带 `error_code` ⇒ `wp_sync_router` 映射 **4xx**。

⇒ 收敛后畸形载荷从 **4xx 变成 opaque 500**（2026-09-26 实测确认四家全中）。
畸形 store 载荷是**用户侧数据问题**（OCR/导入/手改都能写出非数组），报 500 会让现场
以为是平台崩了，且错误体里没有 error_code 可供前端分流。

🔴 **golden digest 门禁抓不到这类回归**：它只对三段**成功路径**产物取 sha256
（contract payload / store projection / instrumentation），失败路径的错误分类不在其中。
这正是「零回归门绿 ≠ 无回归」的一个实证样本 —— 故另立本判据。
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")
warnings.filterwarnings("ignore")

from app.services.workpaper_sync.models import SyncDomainError  # noqa: E402

#: 四种用户侧真能写出的畸形载荷（覆盖引擎 fail-closed 的四个分支）。
BAD_PAYLOADS: dict[str, str] = {
    "non_array": '{"rows": []}',
    "invalid_json": "[{",
    "element_not_object": "[1, 2, 3]",
    "missing_row_identity": '[{"foo": 1}]',
}


def _provider(module_name: str) -> Any:
    import importlib

    return importlib.import_module(f"app.services.workpaper_sync.{module_name}")


#: 已收敛（或本就正确）且**必须**保持 domain 错误的 provider。
_DOMAIN_ERROR_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("d1", "phase5_d1_notes_receivable"),
    ("d5", "phase5_d5_receivables_financing"),
    ("d6", "phase5_d6_contract_assets"),
    ("d7", "phase5_d7_contract_liabilities"),
)


@pytest.mark.parametrize("label,module_name", _DOMAIN_ERROR_PROVIDERS)
@pytest.mark.parametrize("case", sorted(BAD_PAYLOADS))
def test_bad_store_payload_raises_domain_error_with_code(
    label: str, module_name: str, case: str
) -> None:
    """畸形载荷 ⇒ `SyncDomainError` 子类 + 非空 `error_code`（⇒ 路由映射 4xx）。"""
    prov = _provider(module_name)
    contract = prov.assert_contract_file_matches_source()
    with pytest.raises(SyncDomainError) as exc_info:
        prov.build_store_projection(BAD_PAYLOADS[case], contract=contract)
    code = getattr(exc_info.value, "error_code", None)
    assert isinstance(code, str) and code.strip(), (
        f"{label}/{case}: domain 错误缺 error_code（实得 {code!r}）—— "
        "前端无从按码分流"
    )


def test_each_provider_keeps_its_own_error_code() -> None:
    """各家 error_code 必须互不相同（合并成一个会让分流与告警失去粒度）。

    这也是**不把框架层错误类直接改成 SyncDomainError 子类**的原因：那样四家会共用
    同一个 error_code，与框架层 docstring 记录的设计（各 provider 自有子类）冲突。
    """
    codes: dict[str, str] = {}
    for label, module_name in _DOMAIN_ERROR_PROVIDERS:
        prov = _provider(module_name)
        contract = prov.assert_contract_file_matches_source()
        with pytest.raises(SyncDomainError) as exc_info:
            prov.build_store_projection(BAD_PAYLOADS["non_array"], contract=contract)
        codes[label] = str(getattr(exc_info.value, "error_code", ""))
    assert len(set(codes.values())) == len(codes), (
        f"error_code 出现重复，失去 per-provider 粒度: {codes}"
    )


def test_engine_error_is_deliberately_not_a_domain_error() -> None:
    """反面钉子：框架层错误类**应当**保持非 domain（设计如此，不是漏改）。

    若将来有人把它改成 `SyncDomainError` 子类以图省事，本条会红并提示：
    那会让四家共用一个 error_code，且把「provider 侧按需转译」这条设计约定废掉。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        RowTableStorePayloadError,
    )

    assert not issubclass(RowTableStorePayloadError, SyncDomainError), (
        "框架层 RowTableStorePayloadError 被改成了 SyncDomainError 子类 —— "
        "请改回并在各 provider 薄转发处转译（见其 docstring 的设计约定）"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "D3（phase5_d3_prepaid_receipts）同为 Task 16 收敛产物、同缺错误转译，"
        "但该文件正被 d3-sync-coverage-via-row-table-engine 并发会话改动中，"
        "本轮不介入以免冲突。修法与 D5/D6/D7 逐字相同（try/except 转译成本家 "
        "StorePayloadError）。🔴 strict=True：D3 lane 修好后本条会 XPASS 而红，"
        "届时请删掉这个 xfail 标记并把 d3 并入 _DOMAIN_ERROR_PROVIDERS。"
    ),
)
def test_d3_bad_store_payload_should_also_raise_domain_error() -> None:
    prov = _provider("phase5_d3_prepaid_receipts")
    contract = prov.assert_contract_file_matches_source()
    with pytest.raises(SyncDomainError):
        prov.build_store_projection(BAD_PAYLOADS["non_array"], contract=contract)
