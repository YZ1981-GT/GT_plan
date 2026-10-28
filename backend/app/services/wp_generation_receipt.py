"""建底稿入口的统一回执（spec procedure-chain-hardening-and-java-contracts R11）。

模板集生成 / 按编码生成 / 自定义底稿（单张、批量）/ 链路编排 / IPO 应对加载 / B60 附件 / 准则转换，
按同一组分类回报，失败不计入新建：

- ``created_codes``：新建；``existing_codes``：已有底稿（幂等跳过）
- ``skipped_trimmed_codes``：已在程序裁剪中标为不执行；``in_recycle_codes``：底稿在回收站（只能恢复）
- ``blank_codes``：找不到模板、建了空白底稿（已计入新建）
- ``failures``：``[{wp_code, error}]`` 建行 / 落文件失败（该码已回滚，不计入新建）
- ``header_failures``：``[{wp_code, reason}]`` 填了表头但没填上（底稿已建）
- ``header_unfilled``：请求内不填表头的入口（模板集 / 链路编排 / IPO / B60）新建的工作簿份数
- ``ignored_codes``：选中但不在所选模板集里（只有模板集生成有）

各入口原有字段（``created`` 计数、``skipped_codes``、``count``、``generated_wp_codes`` …）保留，回执只补缺项。
JSON 形状见 ``docs/contracts/procedure-chain/``（Java 版按同一 schema 实现）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence

from app.services.procedure_scope_retention import describe_skips

if TYPE_CHECKING:
    from app.services.procedure_scope_retention import GenerationPlan
    from app.services.wp_generate_file import GeneratedWorkpaperFile

#: 生成时没写表头就算「表头未填」的文件格式（docx 没有表头格）
WORKBOOK_SUFFIXES = (".xlsx", ".xlsm")
_MAX_LISTED = 10
_MAX_DETAILED = 5
_MAX_ERROR = 300


def _codes(items: Sequence[str]) -> str:
    shown = "、".join(items[:_MAX_LISTED])
    return shown + (" 等" if len(items) > _MAX_LISTED else "")


def failure_text(error: BaseException | str) -> str:
    """失败原因（进回执给用户看）：异常信息，信息为空时用异常类名；截断到 300 字。"""
    text = error if isinstance(error, str) else (str(error).strip() or type(error).__name__)
    return text[:_MAX_ERROR]


@dataclass
class GenerationReceipt:
    """一次建底稿的回执；各列表保持处理顺序。"""

    created_codes: list[str] = field(default_factory=list)
    existing_codes: list[str] = field(default_factory=list)
    skipped_trimmed_codes: list[str] = field(default_factory=list)
    in_recycle_codes: list[str] = field(default_factory=list)
    blank_codes: list[str] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    header_failures: list[dict[str, str]] = field(default_factory=list)
    header_unfilled: int = 0
    ignored_codes: list[str] = field(default_factory=list)

    @classmethod
    def from_plan(cls, plan: "GenerationPlan") -> "GenerationReceipt":
        receipt = cls()
        receipt.add_plan(plan)
        return receipt

    def add_plan(self, plan: "GenerationPlan") -> None:
        """并入一次保留范围判定的三类没新建的编码（链路编排的主底稿与子底稿各判一次）。"""
        self.existing_codes.extend(plan.existing_codes)
        self.skipped_trimmed_codes.extend(plan.skipped_trimmed_codes)
        self.in_recycle_codes.extend(plan.in_recycle_codes)

    def add_created(
        self,
        wp_code: str,
        generated: "GeneratedWorkpaperFile | None" = None,
        *,
        header_issue: str | None = None,
        header_filled: bool = True,
    ) -> None:
        """记一份新建：``generated`` 不是来自模板 ⇒ 空白册；``header_filled=False`` = 本入口请求内不填表头。"""
        self.created_codes.append(wp_code)
        if generated is not None and not generated.from_template:
            self.blank_codes.append(wp_code)
        if header_issue:
            self.header_failures.append({"wp_code": wp_code, "reason": header_issue})
        if not header_filled and generated is not None and generated.path.suffix.lower() in WORKBOOK_SUFFIXES:
            self.header_unfilled += 1

    def add_failure(self, wp_code: str, error: BaseException | str) -> None:
        self.failures.append({"wp_code": wp_code, "error": failure_text(error)})

    def describe(self) -> str:
        """给用户看的一句话（各入口同一措辞）。"""
        parts = [f"已生成 {len(self.created_codes)} 个底稿"]
        if self.existing_codes:
            parts.append(f"{len(self.existing_codes)} 个编码已有底稿，未重复生成：{_codes(self.existing_codes)}")
        if self.ignored_codes:
            parts.append(f"{len(self.ignored_codes)} 个选中的编码不在所选模板集里，未生成：{_codes(self.ignored_codes)}")
        skips = describe_skips({"skipped_trimmed_codes": self.skipped_trimmed_codes,
                                "in_recycle_codes": self.in_recycle_codes})
        if skips:
            parts.append(skips)
        if self.blank_codes:
            parts.append(f"{len(self.blank_codes)} 个编码没有找到底稿模板，已建空白底稿：{_codes(self.blank_codes)}")
        if self.failures:
            shown = "、".join(f"{f['wp_code']}（{f['error']}）" for f in self.failures[:_MAX_DETAILED])
            more = " 等" if len(self.failures) > _MAX_DETAILED else ""
            parts.append(f"{len(self.failures)} 个编码生成失败：{shown}{more}")
        if self.header_failures:
            from app.services.wp_header_service import describe_header_failures

            parts.append(describe_header_failures(self.header_failures))
        if self.header_unfilled:
            parts.append(f"{self.header_unfilled} 份底稿生成时未写入表头（编制单位、审计期间等），需在底稿文件中另行填写")
        return "；".join(parts)

    def to_payload(self) -> dict[str, Any]:
        """回执字段（``created`` = 新建数）+ ``message``。"""
        return {
            "created": len(self.created_codes),
            "created_codes": list(self.created_codes),
            "existing_codes": list(self.existing_codes),
            "skipped_trimmed_codes": list(self.skipped_trimmed_codes),
            "in_recycle_codes": list(self.in_recycle_codes),
            "blank_codes": list(self.blank_codes),
            "failures": [dict(f) for f in self.failures],
            "header_failures": [dict(h) for h in self.header_failures],
            "header_unfilled": self.header_unfilled,
            "ignored_codes": list(self.ignored_codes),
            "message": self.describe(),
        }
