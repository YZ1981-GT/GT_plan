"""附件安全门接线 — 从配置装配 SecureAttachmentGateway 的三道内容门。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R1.2, R1.3, R2, R15
Design: §5.1 流式上传与内容验证门, §3.2 Facade, §9.3 可观测性

背景（生产接线缺口）：``SecureAttachmentGateway.__init__`` 的 ``malware_scanner`` /
``readability_checker`` / ``allowed_media_types`` 均默认 ``None``。为 None 时门以
``_run_hook_bool(..., default=True)`` 全放行，且无正向媒体类型允许清单——若生产 DI/router
不注入真实实现，这三道门会静默 **休眠**，绿测试注入的 fake 无法暴露。

本模块提供 **从 settings 装配真实门** 的工厂（不硬编码），供 router/DI 统一调用，并提供
启动 fail-closed 守卫：
  - ``build_allowed_media_types``：解析 ``settings.ATTACHMENT_ALLOWED_MEDIA_TYPES`` 正向白名单。
  - ``signature_scan_is_clean`` / ``build_malware_scanner``：最小签名式恶意内容检查（PE/ELF/
    Mach-O/shebang/EICAR）+ 可选 ClamAV（``CLAMAV_ENABLED``），二者组合成恶意内容门；**非
    ``lambda: True`` 桩**。
  - ``build_readability_checker``：非空 + 按识别类型的廉价可解析性检查。
  - ``resolve_attachment_security_gates``：一次装配三道门 + ``fully_wired`` 判定。
  - ``check_attachment_security_gates_startup``：启动守卫（production 缺门 → 报错或 loud
    WARNING + 治理指标 alert）。

门保持可注入——测试仍可在构造 gateway 时显式覆盖任一门（本模块只负责生产默认接线）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from collections.abc import Iterable

from app.core.config import settings as _global_settings
from app.services.evidence_governance.secure_attachment_gateway import (
    MalwareScanner,
    ReadabilityChecker,
    sniff_media_type,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 声明媒体类型允许清单
# ---------------------------------------------------------------------------


def build_allowed_media_types(cfg=None) -> frozenset[str] | None:
    """从 ``settings.ATTACHMENT_ALLOWED_MEDIA_TYPES`` 解析正向白名单（小写规范化）。

    - 逗号分隔，去空白，小写；空/纯空白字符串 → ``None``（禁用允许清单，不推荐）。
    - 返回 ``frozenset``（供 ``SecureAttachmentGateway`` 直接消费）或 ``None``。
    """
    cfg = cfg or _global_settings
    raw = getattr(cfg, "ATTACHMENT_ALLOWED_MEDIA_TYPES", "") or ""
    types = {t.strip().lower() for t in raw.split(",") if t.strip()}
    return frozenset(types) if types else None


# ---------------------------------------------------------------------------
# 最小签名式恶意内容检查（真实实现，非桩）
# ---------------------------------------------------------------------------

#: 危险文件 magic 前缀（可执行 / 脚本），命中即判定为不安全内容。
_DANGEROUS_MAGIC: tuple[bytes, ...] = (
    b"MZ",                       # Windows PE (EXE/DLL/SCR)
    b"\x7fELF",                  # Linux/Unix ELF 可执行
    b"\xfe\xed\xfa\xce",         # Mach-O 32-bit
    b"\xfe\xed\xfa\xcf",         # Mach-O 64-bit
    b"\xce\xfa\xed\xfe",         # Mach-O 32-bit (reverse)
    b"\xcf\xfa\xed\xfe",         # Mach-O 64-bit (reverse)
    b"\xca\xfe\xba\xbe",         # Mach-O fat / Java class
    b"#!",                       # 脚本 shebang (#!/bin/sh 等)
    b"\x4d\x53\x43\x46",         # MSCF (Windows cabinet)
)

#: EICAR 反病毒测试签名（标准无害测试串；用于验证恶意内容门确实生效）。
_EICAR_SIGNATURE = (
    rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
)

#: 首部嗅探字节数（只读首部，不解析全文）。
_HEAD_BYTES = 512


def signature_scan_is_clean(content: bytes) -> bool:
    """最小签名式检查：返回 True 表示未命中已知危险签名（clean）。

    检查（只读首部 + EICAR 全文子串）：
      - 首部命中可执行 / 脚本 magic（PE ``MZ`` / ELF / Mach-O / shebang / MSCF）→ 不安全。
      - 内容含 EICAR 标准反病毒测试签名 → 不安全（供门有效性验证）。

    纯函数，无 I/O；不替代完整 AV（ClamAV 由 ``CLAMAV_ENABLED`` 单独接入），但也 **绝非**
    ``lambda: True`` 桩——它会实打实拒绝上传的可执行/脚本内容。
    """
    if not content:
        # 空内容不是本门的职责（空由流式 empty 门拦截）；此处从宽放行。
        return True
    head = content[:_HEAD_BYTES]
    for magic in _DANGEROUS_MAGIC:
        if head.startswith(magic):
            return False
    if _EICAR_SIGNATURE in content:
        return False
    return True


async def _clamav_is_clean(content: bytes) -> bool:
    """委托既有 ``file_scan_service.scan_file``（ClamAV）；不可用时降级为 clean。"""
    from app.services.file_scan_service import scan_file

    result = await scan_file(content, "evidence-attachment")
    return bool(result.get("clean", True))


def build_malware_scanner(cfg=None) -> MalwareScanner | None:
    """装配恶意内容门：签名检查（可选）+ ClamAV（可选）。

    返回一个 async 钩子 ``(content) -> bool``（True=clean 放行），两道子检查任一判定不安全
    则整体不安全。两者都禁用时返回 ``None``（门以 default=True 放行——由启动守卫兜底告警）。
    """
    cfg = cfg or _global_settings
    sig_enabled = bool(getattr(cfg, "ATTACHMENT_SIGNATURE_SCAN_ENABLED", True))
    av_enabled = bool(getattr(cfg, "CLAMAV_ENABLED", False))
    if not sig_enabled and not av_enabled:
        return None

    async def _scan(content: bytes) -> bool:
        if sig_enabled and not signature_scan_is_clean(content):
            return False
        if av_enabled and not await _clamav_is_clean(content):
            return False
        return True

    return _scan


# ---------------------------------------------------------------------------
# 可读性检查
# ---------------------------------------------------------------------------

_ZERO_SNIFF_BYTES = 4096


def readability_is_ok(content: bytes, detected_media_type: str | None) -> bool:
    """最小可读性检查：非空 + 按识别类型的廉价可解析性（返回 True=可读）。

    - 空内容 → 不可读。
    - 全零/全空白首部（加密擦除残留 / 损坏）→ 不可读。
    - PDF：首部必须含 ``%PDF-`` 头。
    - PNG/JPEG/GIF/BMP/TIFF/ZIP：首部 magic 必须与识别类型一致（用 ``sniff_media_type``）。
    - text/csv/plain：首部必须能按 utf-8 或 gbk 解码（廉价截断解码）。
    - 未登记的识别类型：从宽放行（非空即可）。
    """
    if not content:
        return False
    head = content[:_ZERO_SNIFF_BYTES]
    # 全零首部 = 加密擦除残留 / 损坏内容 → 不可读。
    if not head.strip(b"\x00"):
        return False

    mt = (detected_media_type or "").lower()
    if mt == "application/pdf":
        return b"%PDF-" in content[:_HEAD_BYTES]
    if mt in {
        "image/png", "image/jpeg", "image/gif", "image/bmp",
        "image/tiff", "application/zip",
    }:
        return sniff_media_type(head) == mt
    if mt in {"text/csv", "text/plain"}:
        sample = content[:_ZERO_SNIFF_BYTES]
        for enc in ("utf-8", "gbk"):
            try:
                sample.decode(enc)
                return True
            except UnicodeDecodeError:
                continue
        return False
    # 未登记类型：非空即视为可读（从宽，不误伤合法未知类型）。
    return True


def build_readability_checker(cfg=None) -> ReadabilityChecker | None:
    """装配可读性门；禁用时返回 ``None``。"""
    cfg = cfg or _global_settings
    if not bool(getattr(cfg, "ATTACHMENT_READABILITY_CHECK_ENABLED", True)):
        return None

    def _check(content: bytes, media_type: str | None) -> bool:
        return readability_is_ok(content, media_type)

    return _check


# ---------------------------------------------------------------------------
# 一次装配 + fully_wired 判定
# ---------------------------------------------------------------------------


@dataclass
class AttachmentSecurityGates:
    """三道内容门的装配结果 + 接线诊断。"""

    allowed_media_types: frozenset[str] | None
    malware_scanner: MalwareScanner | None
    readability_checker: ReadabilityChecker | None

    @property
    def has_allow_list(self) -> bool:
        return self.allowed_media_types is not None and len(self.allowed_media_types) > 0

    @property
    def has_malware_scanner(self) -> bool:
        return self.malware_scanner is not None

    @property
    def has_readability_checker(self) -> bool:
        return self.readability_checker is not None

    @property
    def fully_wired(self) -> bool:
        """三道门全部真实接线（无 None、有正向允许清单）。"""
        return (
            self.has_allow_list
            and self.has_malware_scanner
            and self.has_readability_checker
        )

    def missing_gates(self) -> list[str]:
        missing: list[str] = []
        if not self.has_allow_list:
            missing.append("allowed_media_types")
        if not self.has_malware_scanner:
            missing.append("malware_scanner")
        if not self.has_readability_checker:
            missing.append("readability_checker")
        return missing

    def summary(self) -> dict:
        return {
            "allowed_media_type_count": len(self.allowed_media_types or ()),
            "has_allow_list": self.has_allow_list,
            "has_malware_scanner": self.has_malware_scanner,
            "has_readability_checker": self.has_readability_checker,
            "fully_wired": self.fully_wired,
            "missing": self.missing_gates(),
        }


def resolve_attachment_security_gates(cfg=None) -> AttachmentSecurityGates:
    """从 settings 一次装配三道门（供 router/DI 统一调用；门仍可被显式覆盖）。"""
    cfg = cfg or _global_settings
    return AttachmentSecurityGates(
        allowed_media_types=build_allowed_media_types(cfg),
        malware_scanner=build_malware_scanner(cfg),
        readability_checker=build_readability_checker(cfg),
    )


# ---------------------------------------------------------------------------
# fail-closed 启动守卫
# ---------------------------------------------------------------------------


def _is_production(cfg) -> bool:
    return str(getattr(cfg, "APP_ENV", "dev")).lower() in ("prod", "production")


class AttachmentSecurityGatesNotWiredError(RuntimeError):
    """production + ATTACHMENT_SECURITY_GATES_REQUIRED 时三道门未接线 → 启动失败。"""


def check_attachment_security_gates_startup(
    cfg=None,
    *,
    metrics=None,
    raise_on_missing: bool | None = None,
) -> dict:
    """启动守卫：确认三道门在 production 已真实接线（design §9.3 可观测性）。

    行为（不依赖 pytest 检测 hack，只看 APP_ENV / 配置开关）：
      - 三道门全接线 → 返回 ``{"ok": True, ...}``（无副作用）。
      - 未全接线 且（``ATTACHMENT_SECURITY_GATES_REQUIRED`` 为真 或 显式
        ``raise_on_missing=True``）→ 抛 ``AttachmentSecurityGatesNotWiredError``（fail-closed）。
      - 未全接线 且处于 production → 打 loud WARNING + 记录治理 alert（``gate_bypass``）。
      - 未全接线 且非 production（dev/test/staging，合法注入 fake 或关门运行）→ 仅 debug 日志。

    返回接线摘要 dict（供 health/metrics 暴露）。``metrics`` 未传时用全局治理指标单例。
    """
    cfg = cfg or _global_settings
    gates = resolve_attachment_security_gates(cfg)
    summary = gates.summary()
    prod = _is_production(cfg)
    summary["production"] = prod

    if gates.fully_wired:
        logger.info(
            "[attachment-security-gates] 三道门已接线: allow_list=%d malware=on readability=on",
            summary["allowed_media_type_count"],
        )
        return {"ok": True, **summary}

    required = (
        raise_on_missing
        if raise_on_missing is not None
        else bool(getattr(cfg, "ATTACHMENT_SECURITY_GATES_REQUIRED", False))
    )
    reason = (
        "SecureAttachmentGateway 内容门未真实接线（可能休眠放行）: missing="
        f"{gates.missing_gates()}"
    )

    if required:
        logger.error("[attachment-security-gates] FAIL-CLOSED: %s", reason)
        raise AttachmentSecurityGatesNotWiredError(reason)

    if prod:
        # production 但未强制 required：不阻断启动，打 loud WARNING + 治理 alert 暴露。
        logger.warning(
            "🔴 [attachment-security-gates] %s —— 生产环境上传安全门可能休眠！"
            "请注入真实实现或设置 ATTACHMENT_SECURITY_GATES_REQUIRED=true。",
            reason,
        )
        try:
            if metrics is None:
                from app.services.evidence_governance.observability import (
                    get_evidence_metrics,
                )

                metrics = get_evidence_metrics()
            metrics.record_alert(
                alert_type="gate_bypass",
                reason=reason,
                severity="error",
                metadata={"missing": gates.missing_gates()},
            )
        except Exception:  # pragma: no cover - 指标记录失败不阻断启动
            logger.debug("[attachment-security-gates] 记录治理告警失败", exc_info=True)
    else:
        logger.debug(
            "[attachment-security-gates] 非生产环境门未全接线（允许注入 fake / 关门运行）: %s",
            summary,
        )

    return {"ok": False, **summary}


__all__ = [
    "AttachmentSecurityGates",
    "AttachmentSecurityGatesNotWiredError",
    "build_allowed_media_types",
    "build_malware_scanner",
    "build_readability_checker",
    "check_attachment_security_gates_startup",
    "readability_is_ok",
    "resolve_attachment_security_gates",
    "signature_scan_is_clean",
]
