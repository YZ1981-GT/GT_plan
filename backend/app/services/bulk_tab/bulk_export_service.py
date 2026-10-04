"""BulkExportService — 项目级底稿批量导出编排（Req 1/3/6）

编排流程：
  build_manifest → for each exportable entry → export_tab → ZipAssembler.write
  → 写 manifest.json（含 sha256）+ README.txt → finalize

fail-soft：单 Tab 导出失败 → log warning, skip that tab, continue with rest。
mode=data + only_with_data：空表（无数据行）标 skipped("no_data")。
service 只 flush 不 commit。

Requirements: 1.1, 1.2, 1.7, 3.1, 3.2, 3.3, 6.3
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from typing import Any, Literal, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.bulk_tab.exceptions import (
    BulkExportEncryptionFailedError,
    BulkExportEncryptionUnavailableError,
    BulkExportNothingToExportError,
    BulkExportPasswordInvalidError,
)
from app.services.bulk_tab.manifest_builder import (
    BulkManifest,
    ManifestFileEntry,
    ManifestSkippedEntry,
    build_manifest,
)
from app.services.bulk_tab.single_tab_adapter import export_tab
from app.services.bulk_tab.zip_handler import ZipAssembler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Progress callback protocol
# ---------------------------------------------------------------------------


class ProgressCallback(Protocol):
    """SSE 进度回调协议。"""

    def tick(self, message: str = "") -> None: ...


# ---------------------------------------------------------------------------
# Helper: SHA-256
# ---------------------------------------------------------------------------


def _sha256(data: bytes) -> str:
    """计算 bytes 的 SHA-256 hex digest。"""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Helper: 检测空 xlsx（mode=data + only_with_data）
# ---------------------------------------------------------------------------


def _is_empty_xlsx(xlsx_bytes: bytes) -> bool:
    """检测 xlsx 文件是否为空数据文件（仅有表头、无数据行）。

    策略：用 openpyxl 只读模式打开，检查第一个 sheet 的数据行数。
    若仅有 0~1 行（可能是表头）则视为空。

    对于无法解析的文件（非 xlsx），保守返回 False（不跳过）。
    """
    try:
        import openpyxl

        wb = openpyxl.load_workbook(
            io.BytesIO(xlsx_bytes), read_only=True, data_only=True
        )
        ws = wb.active
        if ws is None:
            wb.close()
            return True

        # 统计非空行数（跳过表头行）
        row_count = 0
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                # 第一行通常是表头
                continue
            # 判断该行是否有任何非空值
            if any(cell is not None and str(cell).strip() != "" for cell in row):
                row_count += 1
                if row_count > 0:
                    # 有至少 1 行数据即非空
                    wb.close()
                    return False

        wb.close()
        return row_count == 0
    except Exception:
        # 解析失败保守不跳过
        logger.debug("_is_empty_xlsx: 无法解析 xlsx，保守返回 False")
        return False


# ---------------------------------------------------------------------------
# 跳过原因中文文案（Req 8.1 / 8.2）
#
# 单一真源：零 Tab 拦截的错误汇总、README 的「跳过原因」段、`_底稿目录.xlsx` 的状态列
# 三处共用。原实现三处各自输出英文代码（`resolve_instance_miss` 等），用户看不懂也不知道
# 下一步该做什么 —— 真栈实测就是在这里卡住的（导出 0 张底稿，界面只说「已导出」）。
#
# `manifest.json` 里仍写原始代码（供程序读取，导入侧与外部工具依赖它）。
# ---------------------------------------------------------------------------

#: `skip_reason` → 用户可读的中文短标签（用于 `_底稿目录.xlsx` 状态列、README 分类计数）
SKIP_REASON_LABELS: dict[str, str] = {
    "resolve_instance_miss": "未生成底稿",
    "no_data": "无数据",
    "unchanged": "与上次导出相同",
    "export_failed": "导出失败",
    "no_adapter": "该表格暂未接入导入导出",
    "unknown": "原因未知",
}

#: `skip_reason` → 一句「这是什么、你可以怎么办」。零 Tab 拦截时按类别汇总给用户。
SKIP_REASON_ADVICE: dict[str, str] = {
    "resolve_instance_miss": (
        "有 {n} 张表格找不到对应底稿（尚未生成，或同一编号存在多份无法确定用哪份），"
        "请先在「底稿列表」点「生成底稿」"
    ),
    "no_data": (
        "有 {n} 张表格没有数据，被「仅导出有数据的 Tab」过滤掉了，"
        "取消该选项可导出空白表格"
    ),
    "unchanged": (
        "有 {n} 张表格与上次导出内容相同，被「增量导出」跳过，"
        "取消该选项可导出全部"
    ),
    "export_failed": "有 {n} 张表格导出时出错，请稍后重试或联系技术支持",
    "no_adapter": "有 {n} 张表格所属类型暂未接入批量导入导出",
    "unknown": "有 {n} 张表格因未知原因未能导出",
}

#: 一张都没导出、且 `skipped` 也是空的（全部被可见集过滤掉）时的说明。
#: 🔴 刻意不提「有多少张被权限挡住」—— 那会泄露不可见底稿的存在性（Task 10 可见集设计）。
NOTHING_VISIBLE_MESSAGE = "所选循环中没有您可导出的底稿"

#: 零 Tab 拦截错误信息的开头。
NOTHING_TO_EXPORT_PREFIX = "没有可导出的底稿，已取消导出"


def _summarize_skip_reasons(manifest: BulkManifest) -> tuple[str, dict[str, int]]:
    """把 `manifest.skipped` 与 `unsupported_cycles` 汇总成一句中文原因（Req 8.1）。

    一类一句、用「；」连接 —— ElMessage 会吞掉换行，多行文案在界面上会糊成一团。

    Returns:
        ``(message, counts)``：``message`` 给用户；``counts`` 按类别计数，
        只用于日志与测试（``unsupported_cycles`` 记在键 ``unsupported_cycle`` 下）。
    """
    from collections import Counter

    counts: Counter[str] = Counter(s.skip_reason for s in manifest.skipped)

    parts: list[str] = []
    # 按 SKIP_REASON_ADVICE 的声明顺序输出，让「未生成底稿」这类最常见、最可行动的排在前面
    for reason, template in SKIP_REASON_ADVICE.items():
        n = counts.get(reason, 0)
        if n:
            parts.append(template.format(n=n))
    # 声明顺序之外的新类别不能静默消失
    for reason, n in sorted(counts.items()):
        if reason not in SKIP_REASON_ADVICE:
            parts.append(f"有 {n} 张表格未能导出（{reason}）")

    if manifest.unsupported_cycles:
        from app.services.bulk_tab.scenario_registry import UNSUPPORTED_CYCLE_REASON
        from app.services.dashboard_aggregator_service import CYCLE_NAMES

        counts["unsupported_cycle"] = len(manifest.unsupported_cycles)
        names = "、".join(
            f"{c} {CYCLE_NAMES.get(c, '')}".strip() for c in manifest.unsupported_cycles
        )
        parts.append(f"{names}：{UNSUPPORTED_CYCLE_REASON}")

    if not parts:
        parts.append(NOTHING_VISIBLE_MESSAGE)

    return f"{NOTHING_TO_EXPORT_PREFIX}：" + "；".join(parts) + "。", dict(counts)


# ---------------------------------------------------------------------------
# 导出密码字符集（Req 8.3）
# ---------------------------------------------------------------------------

#: 密码最大长度。前端 `WpBulkDialog.vue` 有同名常量，守卫逐值比对（后端是权威）。
PASSWORD_MAX_LENGTH = 128

#: **不允许**的字符：可打印 ASCII（0x21–0x7E）之外的一切，含空格、控制字符、中文、全角。
#:
#: 🔴 为什么不能允许中文：服务端按 UTF-8 编码密码去加密，而 Windows 上相当一部分解压软件
#: 按本地代码页（GBK）处理用户输入的密码 ⇒ 同一串中文算出的字节不同 ⇒ 密码输对了也打不开。
#: 真栈实测确认：UTF-8 可读、同一密码按 GBK 报 Bad password。只有 ASCII 在各编码下字节一致。
#: 不含空格则是因为首尾空格在输入框里看不见，是「密码明明对却打不开」的第二大来源。
#:
#: 🔴 为什么写成**否定字符类**而不是 `^[\x21-\x7E]+$`：Python 的 `$` 除了字符串末尾，
#: **还匹配末尾换行符之前** ⇒ `"pass55\n"` 会被 `^[\x21-\x7E]+$` 判为合法放行，
#: 而加密用的是含 `\n` 的字节，用户在解压软件里输 `pass55` 必然打不开
#: （本文件的参数化用例抓到过这一条）。否定字符类没有锚点，不受此影响；
#: 顺带让前端那份 JS 正则与本式**语义严格一致**（JS 的 `$` 行为与 Python 不同）。
_PASSWORD_FORBIDDEN_RE = re.compile(r"[^\x21-\x7E]")

_PASSWORD_RULE_TEXT = (
    f"导出密码只能使用英文字母、数字和英文符号（不含空格），长度 1–{PASSWORD_MAX_LENGTH} 位"
)


#: 不可见字符的可读名字 —— 直接把 `\n` / 空格塞进错误文案，用户只会看到「含不支持的字符「」」
_INVISIBLE_CHAR_NAMES: dict[str, str] = {
    " ": "空格",
    "\t": "制表符",
    "\n": "换行",
    "\r": "回车",
    "\x0b": "垂直制表符",
    "\x0c": "换页",
}


def _validate_password(password: str) -> None:
    """校验导出密码字符集与长度；不合规抛 422（在任何导出工作之前）。

    Raises:
        BulkExportPasswordInvalidError: 空、超长，或含 ASCII 可打印字符以外的字符。
    """
    if not password:
        # 「留空 = 不加密」由调用处的 `if password:` 承担；走到这里说明调用方逻辑有误
        raise BulkExportPasswordInvalidError(f"{_PASSWORD_RULE_TEXT}；当前密码为空。")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise BulkExportPasswordInvalidError(
            f"{_PASSWORD_RULE_TEXT}；当前密码 {len(password)} 位，过长。"
        )
    bad_chars = _PASSWORD_FORBIDDEN_RE.findall(password)
    if bad_chars:
        seen: list[str] = []
        for ch in bad_chars:
            name = _INVISIBLE_CHAR_NAMES.get(ch, ch)
            if name not in seen:
                seen.append(name)
        shown = "、".join(seen[:5])
        raise BulkExportPasswordInvalidError(
            f"{_PASSWORD_RULE_TEXT}；当前密码含不支持的字符「{shown}」。"
            "中文、全角字符与空格在不同解压软件下会被算成不同的密码，"
            "即使输入正确也可能打不开压缩包。"
        )


# ---------------------------------------------------------------------------
# Helper: README.txt 渲染
# ---------------------------------------------------------------------------


def _render_readme(manifest: BulkManifest, extra_files: list[str] | None = None) -> str:
    """生成 README.txt 内容（Req 1.7；跳过原因与附加文件按 Req 8.1 / 8.2 / 8.5 改写）。

    包含：
    - 导出摘要（**所选**循环逐个列状态，含 0 张的与整个不支持的）
    - 跳过原因（中文，先按类别给张数再列明细）
    - ZIP 使用说明
    - 导出信息（项目/模式/循环/导出时间）
    - 逐 Tab 文件列表（含编制提示链接引导）
    - 附加文件说明（**按实际写入**逐行生成）

    Args:
        manifest: 已完成导出的 manifest（``files`` 已剔除未导出条目）。
        extra_files: 实际写入的附加文件 zip 路径。``None`` / 空 ⇒ 该段写「本次未附带」。
            模板模式恒为空（Req 8.2）。
    """
    mode_label = "模板" if manifest.mode == "template" else "数据"
    lines: list[str] = [
        "=" * 60,
        "审计底稿批量导出",
        "=" * 60,
        "",
        f"导出时间: {manifest.exported_at}",
        f"导出人: {manifest.exported_by}",
        f"审计年度: {manifest.audit_year}",
        f"平台版本: {manifest.platform_version}",
        "",
        "─" * 40,
        "导出摘要",
        "─" * 40,
        "",
    ]

    # Per-cycle summary
    from collections import Counter
    cycle_counts: Counter[str] = Counter()
    for f in manifest.files:
        # Extract cycle from zip_path first segment
        parts = f.zip_path.split("/")
        cycle_counts[parts[0] if parts else "?"] += 1

    lines.append(f"已导出底稿: {len(manifest.files)} 张")
    lines.append(f"未导出: {len(manifest.skipped)} 张")
    lines.append("")
    lines.append("各循环状态:")
    # 🔴 逐个**所选**循环列出，不是只列有导出的：原实现用 cycle_counts（由已导出文件的
    # zip_path 首段得出）当键，于是「勾了但 0 张」的循环在 README 里整个消失 ——
    # 恰好是用户最需要解释的那些。
    _unsupported = set(manifest.unsupported_cycles)
    for cycle in manifest.cycles:
        if cycle in _unsupported:
            lines.append(f"  {cycle}: 未纳入（该循环暂未接入批量导入导出）")
            continue
        count = cycle_counts.get(cycle, 0)
        skip_count = sum(1 for s in manifest.skipped if s.parent_wp_code.startswith(cycle))
        detail = f"导出 {count} 张"
        if skip_count:
            detail += f", 未导出 {skip_count} 张"
        lines.append(f"  {cycle}: {detail}")
    # 所选循环之外的（理论上不该有，真出现说明 zip_path 首段与 cycles 不一致）也不隐藏
    for cycle in sorted(set(cycle_counts) - set(manifest.cycles)):
        lines.append(f"  {cycle}: 导出 {cycle_counts[cycle]} 张（不在所选循环内）")

    if manifest.unsupported_cycles:
        from app.services.bulk_tab.scenario_registry import UNSUPPORTED_CYCLE_REASON
        from app.services.dashboard_aggregator_service import CYCLE_NAMES

        lines.append("")
        lines.append("未纳入的循环:")
        for cycle in manifest.unsupported_cycles:
            _name = CYCLE_NAMES.get(cycle, "")
            lines.append(f"  {cycle} {_name}".rstrip() + f" — {UNSUPPORTED_CYCLE_REASON}")

    if manifest.skipped:
        from collections import Counter as _Counter

        lines.append("")
        lines.append("未导出原因:")
        # 先按类别给张数（用户先要知道「主要是什么问题」），再列明细定位具体表格
        _by_reason: _Counter[str] = _Counter(s.skip_reason for s in manifest.skipped)
        for reason, n in _by_reason.most_common():
            lines.append(f"  {SKIP_REASON_LABELS.get(reason, reason)}: {n} 张")
        lines.append("")
        lines.append("  明细:")
        for s in manifest.skipped[:20]:  # limit display
            _label = SKIP_REASON_LABELS.get(s.skip_reason, s.skip_reason)
            lines.append(f"    {s.sheet_code}: {_label}")
        if len(manifest.skipped) > 20:
            lines.append(f"    ...（共 {len(manifest.skipped)} 项，仅显示前 20 项）")

    lines.append("")
    lines.append("─" * 40)
    lines.append("附加文件")
    lines.append("─" * 40)
    # 🔴 按**实际写入**逐行生成。原实现固定列 5 个文件、再用「缺失即该项暂无数据」一句
    # 带过，模板包里也照列 —— 用户无法区分「这项没数据」与「这个包压根不该有这项」。
    _extra_notes: dict[str, str] = {
        "_报表/财务报表.xlsx": "四张财务报表（审定数）",
        "_报表/财务报表_未审数.xlsx": "四张财务报表（未审数）",
        "_附注/财务报表附注.docx": "附注正文",
        "_试算表/试算平衡表.xlsx": "科目余额试算表",
    }
    _written = list(extra_files or [])
    for path in _written:
        lines.append(f"  {path} — {_extra_notes.get(path, '')}".rstrip(" —"))
    lines.append("  _底稿目录.xlsx — 底稿清单索引")
    lines.append("  manifest.json — 完整导出清单与逐文件 sha256")
    if not _written:
        if manifest.mode == "template":
            lines.append("  （模板包不附带报表、附注、试算表 —— 它们属于项目数据）")
        else:
            lines.append("  （本次未附带报表 / 附注 / 试算表：相应数据暂不可用）")
    lines.append("")
    lines.append("─" * 40)
    lines.append("使用说明")
    lines.append("─" * 40)
    lines.append("")

    if manifest.mode == "template":
        lines.extend([
            "本模板包只含表格骨架与表头，不附带报表、附注、试算表。",
            "",
            "1. 解压本 ZIP 到本地文件夹。",
            "2. 按需打开各 Excel 文件，参照编制提示填写数据。",
            "3. 填写完毕后，将整个文件夹重新压缩为 ZIP（保持目录结构不变）。",
            "4. 在系统中选择「导入全部数据」上传 ZIP 即可批量导入。",
            "",
            "注意事项：",
            "- 请勿修改文件名或目录结构，否则导入时将无法识别。",
            "- 请勿修改表头行（第一行），仅在数据行填写。",
            "- 支持部分导入：未修改的文件可删除，系统会跳过缺失文件。",
        ])
    else:
        lines.extend([
            "1. 各 xlsx 文件可直接在 Excel 中打开编辑。",
            "2. 编辑后可通过「批量导入」功能回写平台。",
            "3. manifest.json 包含完整导出清单和文件哈希。",
        ])

    lines.extend([
        "",
        "─" * 40,
        "导出信息",
        "─" * 40,
        "",
        f"- 项目ID: {manifest.project_id}",
        f"- 审计年度: {manifest.audit_year}",
        f"- 导出模式: {mode_label}",
        f"- 审计循环: {', '.join(manifest.cycles)}",
        f"- 导出时间: {manifest.exported_at}",
        f"- 导出人: {manifest.exported_by}",
        f"- 平台版本: {manifest.platform_version}",
        "",
        "─" * 40,
        "文件清单",
        "─" * 40,
        "",
    ])

    for f in manifest.files:
        if f.sha256:
            lines.append(f"- [{f.sheet_code}] {f.sheet_name}")
            lines.append(f"  路径: {f.zip_path}")
            lines.append("")

    lines.append("")
    lines.append("---")
    lines.append("本文件由系统自动生成，请勿手动修改。")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------


async def export(
    db: AsyncSession,
    project_id: UUID,
    cycles: list[str] | None,
    mode: Literal["template", "data"],
    *,
    only_with_data: bool = False,
    incremental: bool = False,
    password: str | None = None,
    exported_by: str = "",
    platform_version: str = "",
    audit_year: int = 0,
    progress: Any | None = None,
    visible_filter: Any | None = None,
) -> io.BytesIO:
    """批量导出底稿为 ZIP。

    编排流程：
    1. build_manifest 获取 BulkManifest
    2. 遍历 manifest.exportable() 逐 Tab 调 export_tab
    3. mode=data + only_with_data 时检测空表跳过
    4. 计算 sha256 更新 entry
    5. 写 manifest.json + README.txt
    6. finalize 返回 BytesIO

    fail-soft: 单 Tab 失败 → log warning, skip, continue。
    service 只 flush 不 commit。

    Args:
        db: AsyncSession（只 flush 不 commit）。
        project_id: 项目 UUID。
        cycles: 审计循环列表（如 ["D"]）。None 导出全部。
        mode: "template" 或 "data"。
        only_with_data: mode=data 时是否仅导出有数据的 Tab（Req 3.3）。
        exported_by: 导出人用户名。
        platform_version: 平台版本号。
        audit_year: 审计年度。
        progress: SSE 进度回调（可选）。

    Returns:
        BytesIO 包含完整 ZIP；给了 ``password`` 时每个条目都已 AES 加密。

    Raises:
        AcnrCatalogUnavailableError: ACNR catalog 不可用。
        BulkExportPasswordInvalidError: 密码含可打印 ASCII 以外的字符或超长
            （HTTP 422，在任何导出工作之前）。
        BulkExportEncryptionUnavailableError: 要求密码但缺 pyzipper（HTTP 503，在任何导出工作之前）。
        BulkExportNothingToExportError: 所选范围一张 Tab 都没导出成功（HTTP 422，
            在写附加文件与增量清单之前）。
        BulkExportEncryptionFailedError: 加密失败或产物复核不通过（HTTP 500）。
    """
    # ─── Step 0: 密码先过字符集校验，再确认能加密 ──────────────────────
    # 两者都在建 manifest 之前：不做无用功、不先写增量清单。
    # 顺序是「用户可纠正的问题（422）先于服务端缺件（503）」—— 密码里打了中文时，
    # 先告诉用户改密码，而不是先报「服务器没装 pyzipper」。
    if password:
        _validate_password(password)
        _require_zip_encryption()

    # ─── Step 1: Build manifest ───────────────────────────────────────
    manifest = await build_manifest(
        db=db,
        project_id=project_id,
        cycles=cycles,
        mode=mode,
        exported_by=exported_by,
        platform_version=platform_version,
        audit_year=audit_year,
    )

    # ─── Step 2: Create ZipAssembler ──────────────────────────────────
    zip_assembler = ZipAssembler()

    # ─── Step 3: Export each tab ──────────────────────────────────────
    exportable_entries = manifest.exportable()

    # ─── Incremental: load previous hashes ────────────────────────────
    prev_hashes: dict[str, str] = {}
    if incremental:
        try:
            from app.models.core import Project
            proj = await db.get(Project, project_id)
            if proj and proj.wizard_state:
                prev_manifest = proj.wizard_state.get('_last_bulk_export_manifest', {})
                prev_hashes = prev_manifest.get('file_hashes', {})
        except Exception:
            pass  # fall back to full export

    # Task 10 · 可见集过滤（Req 8.6/8.14/9）：manifest 只由 gate 可见集构建。不可见底稿在 export_tab
    # （读正文）之前被剔除，其 sha256 保持空 → Step 4 从 manifest.files 移除，不泄露存在性。
    if visible_filter is not None:
        _visible: list[ManifestFileEntry] = []
        for _e in exportable_entries:
            try:
                _ok = await visible_filter(_e.wp_id, _e.sheet_code)
            except Exception:  # noqa: BLE001 — 过滤异常 fail-closed（不导出该条目）
                _ok = False
            if _ok:
                _visible.append(_e)
        exportable_entries = _visible

    # ─── Progress total tracking (Improvement #12) ────────────────────
    # +3 = 报表 / 附注 / 试算表，只有数据模式才写这三项（Req 8.3 模板包不附带项目数据）
    total_items = len(exportable_entries) + (3 if mode == "data" else 0)
    if progress and hasattr(progress, 'set_total'):
        progress.set_total(total_items)

    exported_count = 0
    skipped_count = 0

    for entry in exportable_entries:
        try:
            # 调用 SingleTabIeAdapter.export_tab
            xlsx_bytes = await export_tab(
                db=db,
                wp_id=entry.wp_id,
                api_prefix=entry.api_prefix,
                sheet_code=entry.sheet_code,
                mode=mode,
            )
        except KeyError:
            # api_prefix 未注册 → skip_reason=no_adapter（fail-soft）
            logger.warning(
                "bulk_export: skip %s — no_adapter (api_prefix=%s)",
                entry.sheet_code,
                entry.api_prefix,
            )
            manifest.skipped.append(
                ManifestSkippedEntry(
                    addr_id=entry.addr_id,
                    sheet_code=entry.sheet_code,
                    sheet_name=entry.sheet_name,
                    parent_wp_code=entry.parent_wp_code,
                    skip_reason="no_adapter",
                )
            )
            # 从 files 中移除此 entry（通过清空 sha256 标记，后续不写入）
            entry.sha256 = ""
            skipped_count += 1
            if progress:
                progress.tick(f"跳过 {entry.sheet_code}（无适配器）")
            continue
        except Exception as exc:
            # 其他异常 → fail-soft，记日志跳过
            logger.warning(
                "bulk_export: skip %s — export_tab failed: %s",
                entry.sheet_code,
                exc,
                exc_info=True,
            )
            manifest.skipped.append(
                ManifestSkippedEntry(
                    addr_id=entry.addr_id,
                    sheet_code=entry.sheet_code,
                    sheet_name=entry.sheet_name,
                    parent_wp_code=entry.parent_wp_code,
                    skip_reason="export_failed",
                )
            )
            entry.sha256 = ""
            skipped_count += 1
            if progress:
                progress.tick(f"跳过 {entry.sheet_code}（导出失败）")
            continue

        # ─── mode=data + only_with_data → 检测空表 ────────────────────
        if mode == "data" and only_with_data and _is_empty_xlsx(xlsx_bytes):
            logger.info(
                "bulk_export: skip %s — no_data (empty xlsx)",
                entry.sheet_code,
            )
            manifest.skipped.append(
                ManifestSkippedEntry(
                    addr_id=entry.addr_id,
                    sheet_code=entry.sheet_code,
                    sheet_name=entry.sheet_name,
                    parent_wp_code=entry.parent_wp_code,
                    skip_reason="no_data",
                )
            )
            entry.sha256 = ""
            skipped_count += 1
            if progress:
                progress.tick(f"跳过 {entry.sheet_code}（无数据）")
            continue

        # ─── 计算 sha256 并写入 ZIP ───────────────────────────────────
        file_hash = _sha256(xlsx_bytes)

        # ─── Incremental: skip if hash unchanged ──────────────────────
        if incremental and prev_hashes.get(entry.sheet_code) == file_hash:
            entry.sha256 = ""  # mark as skipped
            manifest.skipped.append(
                ManifestSkippedEntry(
                    addr_id=entry.addr_id,
                    sheet_code=entry.sheet_code,
                    sheet_name=entry.sheet_name,
                    parent_wp_code=entry.parent_wp_code,
                    skip_reason="unchanged",
                )
            )
            skipped_count += 1
            if progress:
                progress.tick(f"跳过 {entry.sheet_code}（未变更）")
            continue

        entry.sha256 = file_hash

        zip_assembler.write(entry.zip_path, xlsx_bytes)
        del xlsx_bytes  # Release memory immediately after writing to ZIP buffer
        exported_count += 1

        if progress:
            progress.tick(f"已导出 {entry.sheet_code} ({exported_count})")

    # ─── Step 4: 从 manifest.files 中移除未成功导出的 entries ─────────
    # 保留 sha256 非空的 entries 在 files 中（已成功导出）
    manifest.files = [f for f in manifest.files if f.sha256]

    # ─── Step 4b: 一张都没导出 ⇒ 拒绝导出（Req 8.1）────────────────────
    # 为什么判定点必须在这里：可见集过滤、缺适配器、导出失败、无数据、未变更这五种跳过
    # 分散在上面的逐 Tab 循环里，manifest 刚建完时一种都还没发生 —— 只有这个点能看到
    # 「最终一张都没有」。抛在附加文件与增量清单之前 ⇒ 不做无用功、不留痕迹。
    #
    # 只要有 1 张成功，其余跳过仍按原 fail-soft 规则只记进 manifest（归档 spec
    # `workpaper-bulk-tab-import-export` Req 1.6 / 1.8 不变）。
    if not manifest.files:
        message, counts = _summarize_skip_reasons(manifest)
        logger.warning(
            "bulk_export: 零 Tab 拒绝导出 project=%s mode=%s cycles=%s counts=%s",
            project_id,
            mode,
            cycles,
            counts,
        )
        raise BulkExportNothingToExportError(message, counts=counts)

    # ─── Step 3b: 附加文件（报表 / 附注 / 试算表）—— 只在数据模式（Req 8.2）─────
    extra_files: list[str] = []
    if mode == "data":
        extra_files = await _write_project_data_files(
            db=db,
            project_id=project_id,
            audit_year=audit_year,
            zip_assembler=zip_assembler,
        )
        exported_count += len(extra_files)

    # ─── Step 3c: Write index sheet (_底稿目录.xlsx) ────────────────────────
    try:
        import io as _io2
        from openpyxl import Workbook as _Wb2
        from openpyxl.styles import Font as _Font2
        from openpyxl.utils import get_column_letter as _gcl2

        wb_idx = _Wb2()
        ws_idx = wb_idx.active
        ws_idx.title = "底稿目录"
        idx_headers = ["序号", "循环", "底稿编码", "科目名称", "状态", "文件路径"]
        ws_idx.append(idx_headers)
        # Bold headers
        for col_i in range(1, len(idx_headers) + 1):
            ws_idx.cell(row=1, column=col_i).font = _Font2(bold=True)

        for seq, f in enumerate(manifest.files, start=1):
            ws_idx.append([
                seq,
                f.zip_path.split("/")[0] if "/" in f.zip_path else "",
                f.sheet_code,
                f.sheet_name,
                "已导出" if f.sha256 else "跳过",
                f.zip_path,
            ])

        # Also list skipped entries —— 状态列用中文标签（Req 8.2；原为英文 skip_reason 代码）
        seq = len(manifest.files)
        for s in manifest.skipped:
            seq += 1
            ws_idx.append([
                seq,
                s.parent_wp_code,
                s.sheet_code,
                s.sheet_name,
                f"未导出（{SKIP_REASON_LABELS.get(s.skip_reason, s.skip_reason)}）",
                "",
            ])

        # 逐循环登记的不支持循环也要出现在目录里，否则用户勾了却在目录中查无此项
        if manifest.unsupported_cycles:
            from app.services.bulk_tab.scenario_registry import UNSUPPORTED_CYCLE_REASON
            from app.services.dashboard_aggregator_service import CYCLE_NAMES

            for _cyc in manifest.unsupported_cycles:
                seq += 1
                ws_idx.append([
                    seq,
                    _cyc,
                    "",
                    CYCLE_NAMES.get(_cyc, ""),
                    f"整个循环未导出（{UNSUPPORTED_CYCLE_REASON}）",
                    "",
                ])

        # Auto-width
        for col_i in range(1, len(idx_headers) + 1):
            max_len = max(
                (len(str(ws_idx.cell(row=r, column=col_i).value or "")) for r in range(1, ws_idx.max_row + 1)),
                default=10,
            )
            ws_idx.column_dimensions[_gcl2(col_i)].width = min(max_len + 2, 50)

        buf_idx = _io2.BytesIO()
        wb_idx.save(buf_idx)
        zip_assembler.write("_底稿目录.xlsx", buf_idx.getvalue())
    except Exception as exc:
        logger.warning("bulk_export: skip index sheet — %s", exc)

    # ─── Step 5: Write manifest.json ──────────────────────────────────
    manifest_json = json.dumps(
        manifest.to_dict(),
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    zip_assembler.write("manifest.json", manifest_json)

    # ─── Step 6: Write README.txt ─────────────────────────────────────
    readme_text = _render_readme(manifest, extra_files).encode("utf-8")
    zip_assembler.write("README.txt", readme_text)

    # ─── Step 7: Finalize ─────────────────────────────────────────────
    logger.info(
        "bulk_export: project=%s mode=%s cycles=%s exported=%d skipped=%d",
        project_id,
        mode,
        cycles,
        exported_count,
        skipped_count,
    )

    # ─── Step 8: Persist manifest for incremental export ─────────────
    try:
        from app.models.core import Project
        from sqlalchemy.orm.attributes import flag_modified
        proj = await db.get(Project, project_id)
        if proj:
            ws = proj.wizard_state or {}
            ws['_last_bulk_export_manifest'] = {
                'exported_at': manifest.exported_at,
                'mode': manifest.mode,
                'file_hashes': {f.sheet_code: f.sha256 for f in manifest.files if f.sha256},
            }
            proj.wizard_state = {**ws}  # trigger ORM dirty
            flag_modified(proj, 'wizard_state')
            await db.flush()
    except Exception as exc:
        logger.warning("bulk_export: failed to persist manifest for incremental — %s", exc)

    # ─── Step 9: Optional password protection（fail-closed）───────────
    zip_result = zip_assembler.finalize()
    if password:
        return _encrypt_zip(zip_result, password)
    return zip_result


# ---------------------------------------------------------------------------
# 附加文件：报表 / 附注 / 试算表（Req 8.2 —— 只在数据模式写）
# ---------------------------------------------------------------------------


async def _write_project_data_files(
    db: AsyncSession,
    project_id: UUID,
    audit_year: int,
    zip_assembler: ZipAssembler,
) -> list[str]:
    """把项目级附加文件写进 ZIP，返回**实际写入**的 zip 路径列表。

    🔴 只在 ``mode == "data"`` 时调用。改造前它无条件执行，于是「导出空白模板」这个
    明确声称「不含任何项目数据」的场景，包里照样带着审定报表、未审报表、附注、试算表
    —— 模板包被发给被审计单位或现场人员时，等于把全套项目数据一起发了出去。

    返回实际写入清单而不是布尔：README 的「附加文件」段据此逐行生成。原实现固定列 5 个
    文件、再用「缺失即该项暂无数据」一句带过，用户无法区分「这项没数据」与「这个包压根
    不该有这项」。

    fail-soft 沿用原行为：四个导出器任一抛错只记 warning，不让整包失败。
    """
    written: list[str] = []
    try:
        from app.services.report_excel_exporter import ReportExcelExporter
        report_exporter = ReportExcelExporter(db)
        # Export audited version
        report_bytes_io = await report_exporter.export(
            project_id=project_id, year=audit_year, flatten_formulas=True
        )
        report_bytes = report_bytes_io.getvalue()
        zip_assembler.write("_报表/财务报表.xlsx", report_bytes)
        written.append("_报表/财务报表.xlsx")
        # Export unadjusted version if mode parameter is supported
        import inspect
        _export_sig = inspect.signature(report_exporter.export)
        if 'mode' in _export_sig.parameters:
            try:
                report_unadj_io = await report_exporter.export(
                    project_id=project_id, year=audit_year, flatten_formulas=True, mode="unadjusted"
                )
                zip_assembler.write("_报表/财务报表_未审数.xlsx", report_unadj_io.getvalue())
                written.append("_报表/财务报表_未审数.xlsx")
            except Exception as unadj_exc:
                logger.debug("bulk_export: unadjusted report failed: %s", unadj_exc)
    except Exception as exc:
        logger.warning("bulk_export: skip reports — %s", exc)

    try:
        from app.services.note_word_exporter import NoteWordExporter
        note_exporter = NoteWordExporter(db)
        # Determine template_type from project
        from app.models.core import Project
        project = await db.get(Project, project_id)
        template_type = getattr(project, 'template_type', 'soe') or 'soe'
        note_bytes_io = await note_exporter.export(
            project_id=project_id, year=audit_year, template_type=template_type
        )
        note_bytes = note_bytes_io.getvalue()
        zip_assembler.write("_附注/财务报表附注.docx", note_bytes)
        written.append("_附注/财务报表附注.docx")
    except Exception as exc:
        logger.warning("bulk_export: skip notes — %s", exc)

    try:
        # Trial balance export as xlsx
        from app.services.trial_balance_service import TrialBalanceService
        import io as _io
        from openpyxl import Workbook as _Wb
        tb_svc = TrialBalanceService(db)
        tb_rows = await tb_svc.get_trial_balance(project_id, audit_year)
        if tb_rows:
            wb = _Wb()
            ws = wb.active
            ws.title = "试算平衡表"
            ws.append(["科目编码", "科目名称", "期初余额", "未审数", "审计调整(AJE)", "重分类调整(RJE)", "审定数"])
            for r in tb_rows:
                ws.append([
                    getattr(r, 'standard_account_code', ''),
                    getattr(r, 'account_name', ''),
                    round(float(getattr(r, 'opening_balance', 0) or 0), 2),
                    round(float(getattr(r, 'unadjusted_amount', 0) or 0), 2),
                    round(float(getattr(r, 'aje_adjustment', 0) or 0), 2),
                    round(float(getattr(r, 'rje_adjustment', 0) or 0), 2),
                    round(float(getattr(r, 'audited_amount', 0) or 0), 2),
                ])
            buf = _io.BytesIO()
            wb.save(buf)
            zip_assembler.write("_试算表/试算平衡表.xlsx", buf.getvalue())
            written.append("_试算表/试算平衡表.xlsx")
    except Exception as exc:
        logger.warning("bulk_export: skip trial_balance — %s", exc)
    return written

# ---------------------------------------------------------------------------
# 密码保护（fail-closed）
#
# 旧实现在 pyzipper 缺失 / 加密抛错时只记 warning 然后返回**明文** ZIP：用户设了密码、
# 拿到的却是未加密压缩包，界面毫无提示。现在两种情况都中止导出并给出中文原因。
# ---------------------------------------------------------------------------

_ENCRYPTION_UNAVAILABLE_MESSAGE = (
    "服务器未安装 AES 加密组件（pyzipper），无法生成带密码的压缩包，已中止导出。"
    "请联系管理员安装依赖，或清空密码后重新导出（将得到未加密的压缩包）。"
)


def _require_zip_encryption() -> None:
    """确认可以生成 AES 加密 ZIP；否则抛 503（在任何导出工作之前调用）。"""
    try:
        import pyzipper  # noqa: F401
    except ImportError as exc:
        logger.error("bulk_export: 要求密码保护但 pyzipper 不可用 — %s", exc)
        raise BulkExportEncryptionUnavailableError(_ENCRYPTION_UNAVAILABLE_MESSAGE) from exc


def _encrypt_zip(zip_result: io.BytesIO, password: str) -> io.BytesIO:
    """把明文 ZIP 逐条目转写为 AES 加密 ZIP，并复核产物；任何失败都抛 500，不返回明文。

    复核只读中央目录（不解密）：条目名序列须与明文包一致，且每个条目的加密标志位
    （``flag_bits & 0x1``）都已置位 —— 防止「调用了加密库却静默产出明文条目」。
    """
    import zipfile

    try:
        import pyzipper

        plain_bytes = zip_result.getvalue()
        encrypted_buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(plain_bytes)) as src:
            names = src.namelist()
            with pyzipper.AESZipFile(
                encrypted_buf, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
            ) as zf:
                zf.setpassword(password.encode("utf-8"))
                for name in names:
                    zf.writestr(name, src.read(name))
        with zipfile.ZipFile(io.BytesIO(encrypted_buf.getvalue())) as check:
            infos = check.infolist()
        written = [info.filename for info in infos]
        unencrypted = [info.filename for info in infos if not info.flag_bits & 0x1]
        if written != names or unencrypted:
            raise RuntimeError(
                f"加密产物复核不通过：条目一致={written == names}，未加密条目 {len(unencrypted)} 个"
            )
    except Exception as exc:  # noqa: BLE001 - 任何失败都必须中止，不得退回明文
        logger.error("bulk_export: 密码保护失败，已中止导出 — %s: %s", type(exc).__name__, exc)
        raise BulkExportEncryptionFailedError(
            f"压缩包加密失败（{type(exc).__name__}），已中止导出，不会输出未加密的压缩包。请稍后重试或联系管理员。"
        ) from exc
    encrypted_buf.seek(0)
    return encrypted_buf
