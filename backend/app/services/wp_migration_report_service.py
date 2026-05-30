"""迁移报告生成服务

生成 markdown 格式的迁移报告：成功/跳过/需人工处理分类。

Spec: wp-template-migration
Requirements: 3.1, 3.2
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MigrationResult:
    """单个底稿的迁移结果"""
    wp_id: str
    wp_code: str = ""
    wp_name: str = ""
    status: str = "success"  # success / skipped / manual_required / error
    message: str = ""
    snapshot_id: str = ""


@dataclass
class MigrationReport:
    """迁移报告"""
    template_old_version: str = ""
    template_new_version: str = ""
    started_at: str = ""
    finished_at: str = ""
    results: list[MigrationResult] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.status == "success")

    @property
    def skipped_count(self) -> int:
        return sum(1 for r in self.results if r.status == "skipped")

    @property
    def manual_required_count(self) -> int:
        return sum(1 for r in self.results if r.status == "manual_required")

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if r.status == "error")

    @property
    def total_count(self) -> int:
        return len(self.results)

    def add_result(self, result: MigrationResult) -> None:
        self.results.append(result)


def classify_migration_result(
    wp_id: str,
    wp_code: str,
    wp_name: str,
    migrate_result: dict[str, Any],
) -> MigrationResult:
    """将迁移引擎返回的 dict 转为 MigrationResult

    "需人工处理"标记机制：
    - status == "error" 且 message 包含结构冲突关键词 → manual_required
    - 其他 error → error
    """
    status = migrate_result.get("status", "error")
    message = migrate_result.get("message", "")

    # 结构冲突检测：如果错误信息包含特定关键词，标记为需人工处理
    manual_keywords = ["结构冲突", "conflict", "无法自动", "数据类型不匹配"]
    if status == "error" and any(kw in message for kw in manual_keywords):
        status = "manual_required"

    return MigrationResult(
        wp_id=wp_id,
        wp_code=wp_code,
        wp_name=wp_name,
        status=status,
        message=message,
        snapshot_id=migrate_result.get("snapshot_id", ""),
    )


def generate_migration_report_markdown(report: MigrationReport) -> str:
    """生成 markdown 格式的迁移报告

    Args:
        report: MigrationReport 对象

    Returns:
        markdown 字符串
    """
    lines: list[str] = []

    # 标题
    lines.append("# 模板版本升级迁移报告")
    lines.append("")
    lines.append(f"- **旧版本**: {report.template_old_version}")
    lines.append(f"- **新版本**: {report.template_new_version}")
    lines.append(f"- **开始时间**: {report.started_at}")
    lines.append(f"- **完成时间**: {report.finished_at}")
    lines.append("")

    # 汇总
    lines.append("## 汇总")
    lines.append("")
    lines.append(f"| 类别 | 数量 |")
    lines.append(f"|------|------|")
    lines.append(f"| 总计 | {report.total_count} |")
    lines.append(f"| ✅ 成功 | {report.success_count} |")
    lines.append(f"| ⏭️ 跳过 | {report.skipped_count} |")
    lines.append(f"| ⚠️ 需人工处理 | {report.manual_required_count} |")
    lines.append(f"| ❌ 错误 | {report.error_count} |")
    lines.append("")

    # 成功列表
    success_results = [r for r in report.results if r.status == "success"]
    if success_results:
        lines.append("## ✅ 成功迁移")
        lines.append("")
        lines.append("| 底稿编码 | 底稿名称 | 快照 ID |")
        lines.append("|----------|----------|---------|")
        for r in success_results:
            lines.append(f"| {r.wp_code} | {r.wp_name} | {r.snapshot_id[:8]}... |")
        lines.append("")

    # 跳过列表
    skipped_results = [r for r in report.results if r.status == "skipped"]
    if skipped_results:
        lines.append("## ⏭️ 跳过")
        lines.append("")
        lines.append("| 底稿编码 | 底稿名称 | 原因 |")
        lines.append("|----------|----------|------|")
        for r in skipped_results:
            lines.append(f"| {r.wp_code} | {r.wp_name} | {r.message} |")
        lines.append("")

    # 需人工处理
    manual_results = [r for r in report.results if r.status == "manual_required"]
    if manual_results:
        lines.append("## ⚠️ 需人工处理")
        lines.append("")
        lines.append("| 底稿编码 | 底稿名称 | 问题描述 |")
        lines.append("|----------|----------|----------|")
        for r in manual_results:
            lines.append(f"| {r.wp_code} | {r.wp_name} | {r.message} |")
        lines.append("")

    # 错误列表
    error_results = [r for r in report.results if r.status == "error"]
    if error_results:
        lines.append("## ❌ 错误")
        lines.append("")
        lines.append("| 底稿编码 | 底稿名称 | 错误信息 |")
        lines.append("|----------|----------|----------|")
        for r in error_results:
            lines.append(f"| {r.wp_code} | {r.wp_name} | {r.message} |")
        lines.append("")

    return "\n".join(lines)


def save_migration_report(
    report: MigrationReport,
    output_dir: str | Path = "docs/uat",
) -> Path:
    """保存迁移报告到文件

    Args:
        report: 迁移报告
        output_dir: 输出目录

    Returns:
        报告文件路径
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"migration_report_{timestamp}.md"
    filepath = output_dir / filename

    content = generate_migration_report_markdown(report)
    filepath.write_text(content, encoding="utf-8")

    logger.info("迁移报告已保存: %s", filepath)
    return filepath
