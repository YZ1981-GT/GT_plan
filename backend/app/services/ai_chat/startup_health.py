"""AI Chat 启动自检 — local-only 验证与服务健康报告（Task 30）

Feature: dsh-agent-panel-integration
Requirements:
  - 12.1：model/embedding/OCR effective endpoint 启动验证为本地。
  - 12.2：cloud/bundled default/unknown provider → refuse + local_only_violation。
  - 12.4：embedding/OCR/model typed errors，不伪装"无结果"。
  - 10.5：DSH 失败 → engine_unavailable（启动时记录但不阻塞）。
  - 10.6：DSH 需 experimental flag 启用后才检查 SDK。
Design: "Components and Interfaces → 12. Engine Contract" + "→ 16. Rate Limits"
Properties: 24, 25, 26

## 启动行为

1. 验证 LLM_BASE_URL 在 loopback/内网 allowlist 内（Req 12.1）。
2. 验证 LLM_EMBEDDING_BASE_URL 在 loopback/内网 allowlist 内（Req 12.1）。
3. OCR 配置检查（已启用 ≠ 服务可达，但启动只做配置校验）。
4. 若 AI_DSH_ENABLED=True，额外检查 DSH SDK discovery 状态。
5. 任何 local-only violation 记录审计哈希链事件 + WARNING 日志。

⚠ 启动校验**不阻塞应用启动**（降级运行 > 拒绝启动），但会：
  - 对每个 violation 记录 ``local_only_violation`` 审计事件
  - 将 violation 状态缓存到模块级变量，``/capabilities`` 取用
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "StartupHealthReport",
    "run_ai_chat_startup_health_check",
    "get_cached_health_report",
]


# ---------------------------------------------------------------------------
# Report 数据结构
# ---------------------------------------------------------------------------


@dataclass
class ServiceCheckResult:
    """单个服务的启动检查结果。"""

    service: str
    ok: bool
    endpoint: str = ""
    error_code: str | None = None
    message: str = ""


@dataclass
class StartupHealthReport:
    """完整启动健康报告。"""

    checks: list[ServiceCheckResult] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    all_local: bool = True

    @property
    def has_violations(self) -> bool:
        return len(self.violations) > 0

    def summary(self) -> str:
        total = len(self.checks)
        ok_count = sum(1 for c in self.checks if c.ok)
        if self.all_local:
            return f"AI Chat 启动校验通过（{ok_count}/{total} 服务正常，全本地）"
        return (
            f"AI Chat 启动校验有 {len(self.violations)} 项 local-only 违规"
            f"（{ok_count}/{total} 服务正常）"
        )


# ---------------------------------------------------------------------------
# 模块缓存（lifespan 启动时写入一次，/capabilities 读取）
# ---------------------------------------------------------------------------

_cached_report: StartupHealthReport | None = None


def get_cached_health_report() -> StartupHealthReport | None:
    """获取启动时缓存的健康报告（未启动过返回 None）。"""
    return _cached_report


# ---------------------------------------------------------------------------
# 启动检查入口
# ---------------------------------------------------------------------------


async def run_ai_chat_startup_health_check() -> StartupHealthReport:
    """执行 AI Chat 模块的启动自检。

    🔴 不阻塞应用启动。任何异常被 catch 并记录，返回降级报告。

    在 ``app.main.lifespan`` 中调用（与 LibreOffice / GIN index 等同级）。
    """
    global _cached_report

    report = StartupHealthReport()

    try:
        from app.core.config import settings

        # 1. 模型 endpoint（Req 12.1 / 12.2）
        _check_model_local(settings, report)

        # 2. Embedding endpoint（Req 12.1）
        _check_embedding_local(settings, report)

        # 3. OCR 配置
        _check_ocr_config(settings, report)

        # 4. DSH SDK（仅 flag 启用时）
        if getattr(settings, "AI_DSH_ENABLED", False):
            _check_dsh_sdk(report)

        # 汇总
        report.all_local = not report.has_violations

        # 记录审计事件
        if report.has_violations:
            await _audit_violations(report)
            logger.warning(
                "[ai-chat] %s", report.summary()
            )
        else:
            logger.info("[ai-chat] %s", report.summary())

    except Exception as exc:
        logger.error(
            "[ai-chat] 启动健康检查异常（不阻塞启动）: %s", exc
        )
        report.checks.append(ServiceCheckResult(
            service="startup_check",
            ok=False,
            error_code="engine_unavailable",
            message=f"启动检查异常: {exc}",
        ))

    _cached_report = report
    return report


# ---------------------------------------------------------------------------
# 各服务检查
# ---------------------------------------------------------------------------


def _check_model_local(settings: Any, report: StartupHealthReport) -> None:
    """验证 LLM_BASE_URL 在 loopback/内网范围（Req 12.1）。"""
    from app.services.ai_chat.dsh_discovery import validate_model_route

    endpoint = getattr(settings, "LLM_BASE_URL", "") or ""
    if not endpoint:
        report.checks.append(ServiceCheckResult(
            service="model",
            ok=False,
            endpoint="(未配置)",
            error_code="engine_unavailable",
            message="LLM_BASE_URL 未配置",
        ))
        return

    errors = validate_model_route(endpoint)
    if errors:
        report.checks.append(ServiceCheckResult(
            service="model",
            ok=False,
            endpoint=endpoint,
            error_code="local_only_violation",
            message=errors[0],
        ))
        report.violations.append(f"model: {errors[0]}")
        logger.warning(
            "[ai-chat][local-only] 模型 endpoint 不合规: %s", errors[0]
        )
    else:
        report.checks.append(ServiceCheckResult(
            service="model",
            ok=True,
            endpoint=endpoint,
            message="本地模型 endpoint 校验通过",
        ))


def _check_embedding_local(settings: Any, report: StartupHealthReport) -> None:
    """验证 LLM_EMBEDDING_BASE_URL 在 loopback/内网范围（Req 12.1）。"""
    from app.services.ai_chat.dsh_discovery import validate_model_route

    endpoint = getattr(settings, "LLM_EMBEDDING_BASE_URL", "") or ""
    if not endpoint:
        report.checks.append(ServiceCheckResult(
            service="embedding",
            ok=False,
            endpoint="(未配置)",
            error_code="semantic_unavailable",
            message="LLM_EMBEDDING_BASE_URL 未配置",
        ))
        return

    errors = validate_model_route(endpoint)
    if errors:
        report.checks.append(ServiceCheckResult(
            service="embedding",
            ok=False,
            endpoint=endpoint,
            error_code="local_only_violation",
            message=errors[0],
        ))
        report.violations.append(f"embedding: {errors[0]}")
        logger.warning(
            "[ai-chat][local-only] embedding endpoint 不合规: %s", errors[0]
        )
    else:
        report.checks.append(ServiceCheckResult(
            service="embedding",
            ok=True,
            endpoint=endpoint,
            message="本地 embedding endpoint 校验通过",
        ))


def _check_ocr_config(settings: Any, report: StartupHealthReport) -> None:
    """检查 OCR 服务配置（Req 12.4：typed error，不伪装无结果）。"""
    paddle = getattr(settings, "OCR_PADDLE_ENABLED", False)
    tesseract = getattr(settings, "OCR_TESSERACT_ENABLED", False)

    if not paddle and not tesseract:
        report.checks.append(ServiceCheckResult(
            service="ocr",
            ok=False,
            endpoint="(全部关闭)",
            error_code="ocr_unavailable",
            message="Paddle 和 Tesseract OCR 均未启用",
        ))
    else:
        engines = []
        if paddle:
            engines.append("Paddle")
        if tesseract:
            engines.append("Tesseract")
        report.checks.append(ServiceCheckResult(
            service="ocr",
            ok=True,
            endpoint="localhost:8200",
            message=f"OCR 引擎已配置: {', '.join(engines)}",
        ))


def _check_dsh_sdk(report: StartupHealthReport) -> None:
    """检查 DSH SDK 安装与 discovery 状态（Req 10.6）。"""
    try:
        from app.services.ai_chat.dsh_discovery import discover_dsh_sdk

        result = discover_dsh_sdk()
        if result.is_available:
            report.checks.append(ServiceCheckResult(
                service="dsh_sdk",
                ok=True,
                endpoint="D:\\DeepHorness",
                message=f"DSH SDK 可用 (status={result.status.value})",
            ))
        else:
            report.checks.append(ServiceCheckResult(
                service="dsh_sdk",
                ok=False,
                endpoint="D:\\DeepHorness",
                error_code="engine_unavailable",
                message=(
                    f"DSH SDK 不可用: {result.status.value}"
                    + (f" — {result.errors[0]}" if result.errors else "")
                ),
            ))
    except Exception as exc:
        report.checks.append(ServiceCheckResult(
            service="dsh_sdk",
            ok=False,
            endpoint="D:\\DeepHorness",
            error_code="engine_unavailable",
            message=f"DSH SDK discovery 异常: {exc}",
        ))


# ---------------------------------------------------------------------------
# 审计记录
# ---------------------------------------------------------------------------


async def _audit_violations(report: StartupHealthReport) -> None:
    """将 local-only violations 写入审计哈希链（Req 12.2）。

    🔴 审计失败不阻塞启动（try/except 静默）。
    """
    try:
        from app.services.ai_chat.audit import audit_event

        for violation in report.violations:
            await audit_event(
                event_type="AI_CHAT_LOCAL_ONLY_VIOLATION",
                payload={
                    "source": "startup_health_check",
                    "violation": violation,
                    "action": "logged_warning",
                },
            )
    except Exception as exc:
        logger.debug(
            "[ai-chat] 审计记录 local-only violation 失败（不阻塞）: %s", exc
        )
