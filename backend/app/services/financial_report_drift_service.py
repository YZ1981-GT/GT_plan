"""财务报表 xlsx 手工改动差异检测（**只告警、不回写**）。

Spec: deliverable-lineage-wiring-and-writeback-closure — Wave 4 Task 21 / 需求 10

**审计底线（需求 10.1）**：财务报表数字的唯一合法来源是试算表 + 调整分录（AJE/RJE）。
允许把 xlsx 里手工改的数字回写上游 = 绕过调整分录，违反审计逻辑。故报表侧**不提供
单元格级回写**，而是把「有人手工改了数字」检测出来、告警并**阻断该版本进入 confirmed**，
把人引回调整分录路径。这与附注/报告正文的「文字可回填」是有意区分的两种处理。

## 三态返回（需求 10.5 / 10.6 / 10.8）

| 情形 | 返回 | `confirm_deliverable` |
|------|------|----------------------|
| Cell_Mapping 文件不存在（该报表类型确实未配映射） | ``None`` | 放行（fail-open） |
| 映射存在但**解析失败**（配置损坏） | ``{"unavailable": "<原因>"}`` | **拒绝**（fail-closed） |
| 比对完成 | ``{"diffs": [...], "checked": N, ...}`` | ``diffs`` 非空则拒绝，空则放行 |

🔴 **第二态必须 fail-closed**：若解析失败也放行，只要弄坏一个映射配置文件就能绕过
需求 10.4 的阻断 —— 等于给「绕过调整分录改数字」开后门。

🔴 **判据不是「drift_report 非空即拒绝」**：``{"diffs": []}`` 是非空 dict 但表示
「已比对且一致」，必须放行；否则每个配了映射的报表都永远确认不了。
判定逻辑收敛在 :func:`should_block_confirm`，禁止调用方自己写 `if drift_report:`。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: 金额比对容差（元）。报表以元为单位、保留 2 位小数，
#: xlsx 浮点往返可能带 1e-9 级噪声，故用 0.005 元（半分）作阈值 ——
#: 比它小的差异不可能是人工改动（人改数字至少改到分）。
AMOUNT_TOLERANCE = Decimal("0.005")

#: 只比对这两个期间列（Cell_Mapping 的 `current` / `prior`）。
#: 需求 10.7：只覆盖映射显式声明的单元格，文字性单元格不参与数字比对。
PERIODS = ("current", "prior")


class DriftUnavailable(Exception):
    """映射存在但不可用（解析失败 / 结构不符）—— 必须 fail-closed。"""


def _to_decimal(raw: Any) -> Decimal | None:
    """把单元格值/重算值转 Decimal；非数值返回 ``None``（不参与比对）。

    公式字符串（``=SUM(...)``）、文字、空值都返回 None —— 需求 10.7。
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, (int, float)):
        return Decimal(str(raw))
    if isinstance(raw, str):
        text = raw.strip().replace(",", "").replace("，", "")
        if not text or text.startswith("="):
            return None
        try:
            return Decimal(text)
        except (InvalidOperation, ValueError):
            return None
    return None


def _load_variant_mapping(variant_key: str) -> dict[str, Any] | None:
    """加载某变体的 Cell_Mapping；文件不存在返回 ``None``（放行态）。

    Raises:
        DriftUnavailable: 文件存在但解析失败 / 结构不符（阻断态）。
    """
    from app.services import financial_cell_mapping as fcm

    path: Path = fcm.MAPPING_PATH
    if not path.is_file():
        logger.info("drift: Cell_Mapping 文件不存在（未配映射），放行 %s", path)
        return None

    try:
        root = fcm.load_cell_mapping_root()
    except Exception as exc:  # noqa: BLE001 — 解析失败必须 fail-closed
        raise DriftUnavailable(f"Cell_Mapping 解析失败: {exc}") from exc

    if not isinstance(root, dict) or not isinstance(root.get("variants"), dict):
        raise DriftUnavailable("Cell_Mapping 结构不符（缺 variants 对象）")

    variant = root["variants"].get(variant_key)
    if variant is None:
        # 该变体未配映射 —— 属「未配」而非「坏了」，放行
        logger.info("drift: 变体 %s 未配 Cell_Mapping，放行", variant_key)
        return None
    if not isinstance(variant, dict) or not isinstance(variant.get("rows"), dict):
        raise DriftUnavailable(f"变体 {variant_key} 的 Cell_Mapping 结构不符（缺 rows）")
    return variant


@dataclass(frozen=True)
class CellSpec:
    """一个待比对的单元格：`(交付件真实 sheet 名, row_code, 期间, 坐标)`。

    🔴 `sheet` 存的是**交付件里的真实 sheet 名**（如 `1,2-资产负债表(企财01表）续`），
    **不是** `cell_mapping.json` 的 `sheet` 键（`balance_sheet`）。这个区别是本模块
    最重要的修正点，原因见 :func:`resolve_expected_cell_specs`。
    """

    sheet: str
    row_code: str
    row_name: str
    period: str
    coord: str


def resolve_expected_cell_specs(template_key: str) -> list[CellSpec] | None:
    """解析「哪个 sheet 的哪个格该放哪个 row_code」——**必须与 exporter 同源**。

    🔴🔴 这里曾有一个让整个差异检测产出**成片假差异**的缺陷（2026-08-05 修）：

    `ReportExcelExporter._fill_template` 的填充口径是「**逐 sheet** 扫内联
    ``{{row:CODE:current|prior}}`` 占位符，该 sheet 没有内联占位符才回退
    ``cell_mapping.json`` 坐标」。而资产负债表在四个变体里**都拆成「主表 + 续表」两个
    sheet**（`_resolve_sheets` 对 alias 为列表时返回全部匹配），偏偏
    ``cell_mapping.json`` 里主表与续表的 row_code **共用同一个 `sheet` 键
    `balance_sheet`、坐标还重叠**：

    - 主表 `C6` = `BS-002 货币资金`；续表 `C6` = `BS-055 短期借款`
    - 主表 `C11` = `BS-007 应收票据`；续表 `C11` = `BS-060 应付票据`

    exporter 靠逐 sheet 扫占位符区分，填的是对的；而旧实现按 ``sheet_aliases`` 只取
    **第一个**匹配 sheet 取值 ⇒ 续表 49 个 row_code 全去主表取值 ⇒ 报出「应付票据
    拿到应收票据余额」这类**系统性错位**。真实库项目 `0ec33ac9` 报表 v8 实测的 22 处
    差异**全部**由此而来（该项目只有部分行有重算值，故 49 → 22）。

    → 正解 = 从**同一份模板**逐 sheet 解析，并把结果按**真实 sheet 名**落到 CellSpec。

    Returns:
        ``None`` 表示无法解析（JSON 未配该变体 / 模板缺失 / 解析不出任何映射格）
        ⇒ 调用方放行。模板缺失时 exporter 走 programmatic 生成，那种交付件没有
        稳定坐标，本就不该判差异。

    Raises:
        DriftUnavailable: JSON 存在但解析失败，或模板存在但打不开（配置损坏）
            ⇒ fail-closed（需求 10.6）。
    """
    from app.services.report_excel_exporter import (
        REPORT_TYPE_SHEET_NAMES,
        ReportExcelExporter,
    )

    # 先过 JSON 三态闸（需求 10.5 / 10.6）：文件不存在 / 该变体未配 ⇒ 放行；
    # **存在但解析失败 ⇒ 由 _load_variant_mapping 抛 DriftUnavailable 上传，fail-closed**。
    # 🔴 不要改成「JSON 坏了就只用内联占位符」—— 那样只需弄坏配置文件，就能让
    # 「无内联占位符的 sheet」静默退出比对面 = 需求 10.6 想堵的后门。
    json_variant = _load_variant_mapping(template_key)
    if json_variant is None:
        return None
    json_rows = json_variant.get("rows") or {}

    # 复用 exporter 自己的模板加载与 sheet 解析（两者都不用 db）——
    # 抄一份等于给「改一处另一处不红」留口子。
    exporter = ReportExcelExporter(None)  # type: ignore[arg-type]
    try:
        wb = exporter._load_template(template_key)  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        raise DriftUnavailable(f"报表模板无法加载: {exc}") from exc
    if wb is None:
        logger.info("drift: 变体 %s 无 xlsx 模板（programmatic 生成），放行", template_key)
        return None

    try:
        specs: list[CellSpec] = []
        seen: set[tuple[str, str, str]] = set()
        for report_type in REPORT_TYPE_SHEET_NAMES:
            sheets = exporter._resolve_sheets(wb, report_type, template_key)  # noqa: SLF001
            for ws in sheets:
                specs.extend(
                    _specs_for_sheet(ws, report_type, json_rows, seen)
                )
    finally:
        wb.close()

    if not specs:
        logger.info("drift: 变体 %s 未解析出任何映射格，放行", template_key)
        return None
    return specs


def _specs_for_sheet(
    ws,
    report_type: str,
    json_rows: dict[str, Any],
    seen: set[tuple[str, str, str]],
) -> list[CellSpec]:
    """单个 sheet 的映射：内联占位符优先，无内联才回退该 sheet 的 JSON 条目。

    与 `financial_cell_mapping.row_mappings_for_sheet` 同口径（内联覆盖 JSON），
    但这里额外把 ``ws.title`` 记进 spec，使主表/续表不再混淆。

    ``seen`` 按 ``(sheet, code, period)`` 去重 —— 同一 sheet 可能既被
    `sheet_aliases` 命中又被中文子串回退命中（`_resolve_sheets` 两条路径）。
    """
    from app.services.financial_cell_mapping import scan_worksheet_row_placeholders

    inline = scan_worksheet_row_placeholders(ws)
    out: list[CellSpec] = []

    def _add(code: str, period: str, coord: str) -> None:
        key = (ws.title, code, period)
        if key in seen:
            return
        seen.add(key)
        entry = json_rows.get(code)
        row_name = (
            entry.get("row_name") if isinstance(entry, dict) else None
        ) or code
        out.append(
            CellSpec(
                sheet=ws.title,
                row_code=code,
                row_name=row_name,
                period=period,
                coord=coord,
            )
        )

    if inline:
        for code, coords in inline.items():
            for period in PERIODS:
                coord = coords.get(period)
                if coord:
                    _add(code, period, coord)
        return out

    # 该 sheet 无内联占位符 ⇒ exporter 走 JSON 回退，检测也必须走 JSON 回退
    for code, entry in json_rows.items():
        if not isinstance(entry, dict) or entry.get("sheet") != report_type:
            continue
        for period in PERIODS:
            coord = entry.get(period)
            if coord:
                _add(code, period, coord)
    return out


def compare_cell_specs(
    specs: Iterable[CellSpec],
    sheet_values: dict[str, dict[str, Any]],
    expected_by_code: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """纯函数：按 CellSpec 逐格比对 xlsx 值 vs 重算值，返回差异清单。

    Args:
        specs: 待比对格清单（`sheet` 为交付件真实 sheet 名）。
        sheet_values: ``{sheet 名: {坐标: 单元格值}}``（从交付 xlsx 读出，data_only）。
        expected_by_code: ``{row_code: {"current_period_amount", "prior_period_amount"}}``。

    Returns:
        差异清单，每项 ``{row_code, row_name, sheet, period, coord, file_value,
        expected_value, diff}``。**只包含两侧都能转成数值且差额超容差的格**：
        - 单元格是公式 / 文字 / 空 → 跳过（需求 10.7）
        - 重算值缺失（该行未参与报表） → 跳过（不是「手工改动」）
    """
    diffs: list[dict[str, Any]] = []
    for spec in specs:
        values = sheet_values.get(spec.sheet) or {}
        file_val = _to_decimal(values.get(spec.coord))
        if file_val is None:
            continue
        field = (
            "current_period_amount"
            if spec.period == "current"
            else "prior_period_amount"
        )
        exp_val = _to_decimal(
            (expected_by_code.get(spec.row_code) or {}).get(field)
        )
        if exp_val is None:
            continue
        delta = file_val - exp_val
        if abs(delta) <= AMOUNT_TOLERANCE:
            continue
        diffs.append(
            {
                "row_code": spec.row_code,
                "row_name": spec.row_name,
                "sheet": spec.sheet,
                "period": spec.period,
                "coord": spec.coord,
                "file_value": str(file_val),
                "expected_value": str(exp_val),
                "diff": str(delta),
            }
        )
    return diffs


def compare_cells(
    variant: dict[str, Any],
    sheet_values: dict[str, dict[str, Any]],
    expected_by_code: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """按 ``cell_mapping.json`` 单变体块比对（**JSON 口径薄壳**）。

    保留此函数是为了 ①既有守卫用它做纯比对逻辑的单元测试 ②某些调用方只有 JSON。
    它把 JSON 条目转成 CellSpec 后委托 :func:`compare_cell_specs`，
    **比对逻辑只有一份**。

    🔴 注意它的 `sheet` 语义是 JSON 的 `sheet` 键（`balance_sheet`），
    因此**无法区分主表与续表** —— 生产检测路径必须走
    :func:`resolve_expected_cell_specs`，不要用这个。
    """
    specs = [
        CellSpec(
            sheet=entry.get("sheet") or "",
            row_code=code,
            row_name=entry.get("row_name") or code,
            period=period,
            coord=entry[period],
        )
        for code, entry in ((variant.get("rows") or {}).items())
        if isinstance(entry, dict)
        for period in PERIODS
        if entry.get(period)
    ]
    return compare_cell_specs(specs, sheet_values, expected_by_code)


def read_values_for_sheets(
    xlsx_path: Path, sheet_titles: Iterable[str]
) -> dict[str, dict[str, Any]]:
    """读交付 xlsx 中指定 sheet → ``{sheet 名: {坐标: 值}}``。

    用 ``data_only=True`` 取缓存值（我们要的是「文件里显示的数」）。
    **按真实 sheet 名取**，不再经 ``sheet_aliases`` 猜 —— 猜的那版会让
    主表/续表混淆（见 :func:`resolve_expected_cell_specs`）。

    交付件里不存在的 sheet 直接跳过（如未导出的表），属「不参与比对」而非「不可用」。

    Raises:
        DriftUnavailable: xlsx 打不开（文件损坏）——检测不可用。
    """
    from openpyxl import load_workbook

    try:
        wb = load_workbook(str(xlsx_path), data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001
        raise DriftUnavailable(f"交付 xlsx 无法打开: {exc}") from exc

    out: dict[str, dict[str, Any]] = {}
    try:
        available = set(wb.sheetnames)
        for title in {t for t in sheet_titles if t}:
            if title not in available:
                continue
            cells: dict[str, Any] = {}
            for row in wb[title].iter_rows():
                for cell in row:
                    if cell.value is not None:
                        cells[cell.coordinate] = cell.value
            out[title] = cells
    finally:
        wb.close()
    return out


def _as_utc(dt):
    """把 naive datetime 视作 UTC 后返回 aware datetime；None 原样返回。

    🔴 平台的时间戳**混用 naive 与 aware**：PG `func.now()` / `utcnow()` 落库后
    读回是 naive（memory 已记「后端 created_at 是 naive UTC」），而
    `datetime.now(timezone.utc)` 写入的是 aware。二者直接比较抛
    ``TypeError: can't compare offset-naive and offset-aware datetimes``。
    """
    if dt is None:
        return None
    from datetime import timezone

    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _is_later(candidate, baseline) -> bool:
    """``candidate`` 是否晚于 ``baseline``（任一为 None 返 False = 未知不算晚）。

    统一归一为 aware 再比 —— 这个函数存在的唯一理由就是上面那条时区混用陷阱。
    真实库跑 detect 时它曾让 `_attribute` 抛 TypeError 冒泡，被
    `detect_and_store_report_drift` 的 `except Exception` 吞成 warning ⇒
    `drift_report` 恒 None、整个检测又变成死的（fail-open 把 bug 伪装成"无数据"）。
    """
    a, b = _as_utc(candidate), _as_utc(baseline)
    if a is None or b is None:
        return False
    return a > b


def annotate_pre_existing(
    diffs: list[dict[str, Any]], baseline_keys: set[tuple[str, str]] | None
) -> list[dict[str, Any]]:
    """给差异标注是否**在基线版本就已存在**（纯函数）。

    ``baseline_keys is None`` 表示基线未知（读不到上一版文件等）—— 此时
    **一个标记都不打**，避免把「基线读不到」误报成「本次编辑引入」。
    """
    if baseline_keys is None:
        return diffs
    return [
        {**d, "pre_existing": (d.get("row_code"), d.get("period")) in baseline_keys}
        for d in diffs
    ]


def should_block_confirm(drift_report: dict | None) -> tuple[bool, str | None]:
    """由 ``drift_report`` 判定是否阻断 confirmed（需求 10.4 / 10.6 / 10.8）。

    **判定唯一入口** —— 调用方禁止自己写 `if drift_report:`，那会把
    ``{"diffs": []}``（已比对且一致）误判成有差异，使配了映射的报表永远确认不了。

    Returns:
        ``(是否阻断, 中文原因)``。
    """
    if drift_report is None:
        return False, None
    if not isinstance(drift_report, dict):
        # 结构异常按「检测不可用」处理（fail-closed）
        return True, "差异检测结果结构异常，无法判定报表是否被手工改动，请重新生成报表"

    if "unavailable" in drift_report:
        reason = drift_report.get("unavailable") or "原因未记录"
        return True, (
            f"报表差异检测不可用（{reason}），为避免手工改动的数字被确认，"
            "已阻断本版本；请修复单元格映射配置后重新生成报表"
        )

    diffs = drift_report.get("diffs")
    if isinstance(diffs, list) and diffs:
        head = diffs[:3]
        detail = "；".join(
            f"{d.get('row_name')}（{d.get('sheet')}!{d.get('coord')}）"
            f"文件值 {d.get('file_value')} 与重算值 {d.get('expected_value')} "
            f"差 {d.get('diff')}"
            for d in head
        )
        more = f"，另有 {len(diffs) - len(head)} 处" if len(diffs) > len(head) else ""
        # 🔴 文案必须**中性归因**，不得直接断言「有人手工改了数字」。
        #
        # 真实库实测（项目 0ec33ac9 / 报表交付件 v8，非 stale）报出 22 处差异，
        # 逐个看是**系统性错位**（`应付票据 C9` 取到了应收票据的余额）——
        # 属「Cell_Mapping 坐标与该模板变体实际布局不一致」，而不是手工改动。
        # 在审计平台里把这种情况说成「有人改了报表数字」是误指控，比不告警更坏。
        #
        # 故这里只陈述「文件值与按试算表重算值不一致」这一事实，并列出三种
        # 可能原因让审计师判断；stale 态由 `stale` 标记单独提示。
        stale_hint = (
            "该版本绑定的试算表快照已过期（上游数据在生成后发生变更），"
            "很可能只需重新生成报表；"
            if drift_report.get("stale")
            else ""
        )
        # 基线归因提示（有基线可比时才出）：这些格在被编辑的上一版就已不一致 ⇒
        # 本次编辑没碰过它们，指向配置问题而非手工改动。
        pre_existing_hint = ""
        if drift_report.get("attribution") == "pre_existing":
            n = drift_report.get("pre_existing_count")
            pre_existing_hint = (
                f"其中 {n} 处在被编辑的上一版就已存在（本次编辑并未改动这些单元格），"
                "更可能是单元格映射与模板布局不一致；"
            )
        return True, (
            f"报表有 {len(diffs)} 处数字与按试算表重算的结果不一致：{detail}{more}。"
            f"{stale_hint}{pre_existing_hint}"
            "请先确认原因：①上游数据已变更 → 重新生成报表；"
            "②确有手工改动 → 财务报表数字只能由试算表与调整分录派生，"
            "请通过调整分录（AJE/RJE）修正后重新生成，不要直接改 xlsx；"
            "③单元格映射与模板布局不一致 → 属配置问题，请联系系统管理员核对映射"
        )
    return False, None


class FinancialReportDriftService:
    """按 Cell_Mapping 比对交付 xlsx 与按试算表重算值。"""

    def __init__(self, db):
        self.db = db

    async def detect(
        self,
        word_export_task_id,
        version_no: int,
        *,
        baseline_version_no: int | None = None,
    ) -> dict | None:
        """检测某个报表版本是否被手工改过数字。

        Args:
            baseline_version_no: 可选的**基线版本**（通常是被编辑的上一版）。给了它就
                对基线文件跑同一套比对，把两侧都存在的差异标 ``pre_existing=True``。

                为什么需要：即便映射解析已修正（见 `resolve_expected_cell_specs`），
                「文件值与重算值不一致」仍可能来自**上游变更**或**模板/映射的其它
                残留问题**，与「本次编辑改了数字」在单版本视角下无法区分。有基线后
                ``introduced_count`` 才是真正指向「这次编辑改了数字」的信号。

                🔴 历史教训（勿据旧注释推断）：真实库项目 `0ec33ac9` 报表 v8 曾报
                22 处「系统性错位」（`应付票据` 取到应收票据余额），当时被归因为
                「Cell_Mapping 配置与模板布局不一致」并推给别的 spec ——
                **实为本服务自身的映射解析缺陷**（按 `sheet_aliases` 只取第一个匹配
                sheet，使资产负债表续表的 49 个 row_code 全去主表取值），已于
                2026-08-05 修正。

        Returns:
            三态见模块 docstring。**不落库**（落库由调用方决定，便于测试与重试）。
        """
        import sqlalchemy as sa

        from app.models.phase13_models import WordExportTask, WordExportTaskVersion

        row = (
            await self.db.execute(
                sa.select(
                    WordExportTaskVersion.file_path,
                    WordExportTask.project_id,
                    WordExportTask.doc_type,
                )
                .join(
                    WordExportTask,
                    WordExportTask.id == WordExportTaskVersion.word_export_task_id,
                )
                .where(
                    WordExportTaskVersion.word_export_task_id == word_export_task_id,
                    WordExportTaskVersion.version_no == version_no,
                )
            )
        ).first()
        if row is None or not row.file_path:
            logger.info(
                "drift: 版本不存在或无文件 task=%s v%s，跳过检测",
                word_export_task_id,
                version_no,
            )
            return None
        if not (row.doc_type or "").startswith("financial_report"):
            # 只对财务报表做数字比对；附注/报告正文走文字回填路径
            return None

        xlsx = _resolve_deliverable_file(row.file_path)
        if xlsx is None:
            logger.info("drift: 交付文件缺失 %s，跳过检测", row.file_path)
            return None

        variant_key = await self._resolve_variant_key(row.project_id)
        try:
            # 🔴 映射解析必须与 exporter 同源（逐 sheet 内联占位符优先），
            # 不能按 cell_mapping.json 的 `sheet` 键 + sheet_aliases 猜 ——
            # 资产负债表主表/续表共用同一个键且坐标重叠，猜法会产出成片假差异。
            specs = resolve_expected_cell_specs(variant_key)
            if specs is None:
                return None
            year = await self._resolve_year(row.project_id)
            if year is None:
                # 拿不到年度 ⇒ 无法重算权威值 ⇒ 检测不可用（不得静默放行）。
                # 真实库实测该分支会命中「交付件文件在、但项目里一条
                # financial_report 都没有」的情形（如报表数据被删）——
                # 这种报表的数字来源不可追溯，阻断它进入 confirmed 是审计上正确的，
                # 故文案要指向处置（重新生成）而不是笼统说"不可用"。
                raise DriftUnavailable(
                    "本项目未查到财务报表数据（financial_report 无记录），"
                    "无法按试算表重算校验该报表，请先重新生成报表"
                )
            sheet_values = read_values_for_sheets(
                xlsx, {s.sheet for s in specs}
            )
            expected = await self._recompute_expected(
                row.project_id, year, row.doc_type, variant_key
            )
        except DriftUnavailable as exc:
            logger.warning("drift: 检测不可用 task=%s: %s", word_export_task_id, exc)
            return {"unavailable": str(exc)}

        diffs = compare_cell_specs(specs, sheet_values, expected)
        checked = len(specs)
        stale = await self._is_version_stale(word_export_task_id, version_no)

        baseline_keys = None
        if baseline_version_no is not None:
            baseline_keys = await self._baseline_diff_keys(
                word_export_task_id, baseline_version_no, specs, expected
            )
        diffs = annotate_pre_existing(diffs, baseline_keys)
        introduced = (
            sum(1 for d in diffs if d.get("pre_existing") is False)
            if baseline_keys is not None
            else None
        )

        attribution = await self._attribute(
            word_export_task_id,
            version_no,
            row.project_id,
            year,
            stale,
            diff_count=len(diffs),
            introduced_count=introduced,
        )
        logger.info(
            "drift: task=%s v%s 比对 %d 个映射格，发现 %d 处差异"
            "（stale=%s attribution=%s baseline=%s introduced=%s）",
            word_export_task_id,
            version_no,
            checked,
            len(diffs),
            stale,
            attribution,
            baseline_version_no,
            introduced,
        )
        report: dict[str, Any] = {
            "diffs": diffs,
            "checked": checked,
            "variant": variant_key,
            # 归因线索（**不是**阻断判据）：该版本绑定的 tb_hash 是否已与 task 级不同。
            "stale": stale,
            # 归因结论（见 _attribute 的判据说明）：
            #   upstream_changed / pre_existing / manual_edit / unknown
            "attribution": attribution,
        }
        if baseline_keys is not None:
            report["baseline_version_no"] = baseline_version_no
            report["pre_existing_count"] = len(diffs) - (introduced or 0)
            report["introduced_count"] = introduced
        return report

    async def _baseline_diff_keys(
        self,
        word_export_task_id,
        baseline_version_no: int,
        specs: list[CellSpec],
        expected: dict[str, dict[str, Any]],
    ) -> set[tuple[str, str]] | None:
        """对**基线版本文件**跑同一套比对，返回其差异键集合。

        任何一步拿不到（版本不存在 / 文件缺失 / xlsx 打不开）都返回 ``None``
        = 「基线未知」，此时不给任何差异打 ``pre_existing`` 标记。
        """
        import sqlalchemy as sa

        from app.models.phase13_models import WordExportTaskVersion

        try:
            path = (
                await self.db.execute(
                    sa.select(WordExportTaskVersion.file_path).where(
                        WordExportTaskVersion.word_export_task_id
                        == word_export_task_id,
                        WordExportTaskVersion.version_no == baseline_version_no,
                    )
                )
            ).scalar_one_or_none()
            if not path:
                return None
            xlsx = _resolve_deliverable_file(path)
            if xlsx is None:
                return None
            base_values = read_values_for_sheets(xlsx, {s.sheet for s in specs})
        except Exception as exc:  # noqa: BLE001 — 基线读不到只降级为「未知」
            logger.info(
                "drift: 基线版本 v%s 不可比对（%s），本次不做差异归因",
                baseline_version_no,
                exc,
            )
            return None
        return {
            (d["row_code"], d["period"])
            for d in compare_cell_specs(specs, base_values, expected)
        }

    async def _attribute(
        self,
        word_export_task_id,
        version_no: int,
        project_id,
        year: int,
        stale: bool,
        *,
        diff_count: int = 0,
        introduced_count: int | None = None,
    ) -> str:
        """判别差异的**成因**（需求 10.3：告警要指向正确的处置路径）。

        平台上「报表数字与重算值不一致」只有两条可达成因，且**方向相反**：

        1. **直接改 xlsx 单元格** —— 交付中心对 `financial_report*` 同样开放 OO
           在线编辑（``_document_type`` 对 ``.xlsx`` 返回 ``cell``、``_editor_mode``
           对非终态返回 ``edit``、`DeliverableCenter` 的 `@edit` 不按 doc_type 拦），
           forcesave → callback 落成新版本。此时**文件变了、DB 没变**。
           ⇒ 真·手工改动，处置 = 走调整分录（AJE/RJE）重新生成。
        2. **改取数公式/重算** —— `financial_report` 由 `report_engine` /
           `reports.py` / `report_config.py` / `consol_report_service` 写入；
           改 `report_config.formula` 或公式管理预设后重算，**DB 变了、xlsx 没变**。
           ⇒ 上游变更，处置 = 重新生成报表（**不是**指控有人改数字）。

        **只比对「文件值 vs DB 值」无法区分二者**（都表现为不一致）。判别证据 = 谁更新在后：

        - DB 的 ``financial_report.updated_at`` 晚于版本 ``created_at``（或版本 stale）
          ⇒ ``upstream_changed``
        - **有差异但 ``introduced_count == 0``**（这些格在被编辑的上一版就已不一致）
          ⇒ ``pre_existing`` —— 本次编辑没碰过它们，最可能是「映射坐标与模板布局
          不一致」的配置问题。**这条必须优先于 `manual_edit`**，否则「配置错位 +
          恰好有人做过在线编辑」会被判成手工改数字 = 误指控。
        - 该版本 ``created_via == 'onlyoffice_edit'`` 且上述都不成立
          ⇒ ``manual_edit``（差异只可能来自那次编辑）
        - 其余（含两者都动过、时间戳缺失、无基线可比）⇒ ``unknown``，
          文案列出全部可能原因不做断言

        🔴 判据刻意**偏向 upstream_changed** —— 误报「上游变了，重新生成一下」的代价
        远小于误指控「有人改了报表数字」，后者在审计场景里是对人的指控。
        """
        import sqlalchemy as sa

        from app.models.phase13_models import WordExportTaskVersion
        from app.models.report_models import FinancialReport

        try:
            ver = (
                await self.db.execute(
                    sa.select(
                        WordExportTaskVersion.created_at,
                        WordExportTaskVersion.created_via,
                    ).where(
                        WordExportTaskVersion.word_export_task_id
                        == word_export_task_id,
                        WordExportTaskVersion.version_no == version_no,
                    )
                )
            ).first()
            db_updated = (
                await self.db.execute(
                    sa.select(sa.func.max(FinancialReport.updated_at)).where(
                        FinancialReport.project_id == project_id,
                        FinancialReport.year == year,
                        FinancialReport.is_deleted == sa.false(),
                    )
                )
            ).scalar_one_or_none()
        except Exception:  # noqa: BLE001 — 归因失败不影响阻断结论
            logger.warning("drift: 归因查询失败，记 unknown", exc_info=True)
            return "unknown"

        if ver is None or ver.created_at is None:
            return "unknown"

        upstream_newer = _is_later(db_updated, ver.created_at)
        if stale or upstream_newer:
            return "upstream_changed"
        # 🔴 基线证据优先于「谁在编辑」：若这些格在**被编辑的上一版**里就已经不一致，
        # 本次编辑没碰过它们 ⇒ 不得归因为 manual_edit（那正是误指控的来源）。
        if diff_count > 0 and introduced_count == 0:
            return "pre_existing"
        if (ver.created_via or "") == "onlyoffice_edit":
            return "manual_edit"
        return "unknown"

    async def _is_version_stale(self, word_export_task_id, version_no: int) -> bool:
        """该版本绑定的 ``tb_hash`` 是否已与交付件当前绑定不同。

        用于**归因**而非阻断：差异 + stale ⇒ 更可能是上游变更后未重新生成。
        读不到绑定时返回 False（未知不当作 stale）。
        """
        import sqlalchemy as sa

        from app.models.phase13_models import WordExportTask, WordExportTaskVersion

        row = (
            await self.db.execute(
                sa.select(
                    WordExportTaskVersion.source_snapshot_refs,
                    WordExportTask.source_snapshot_refs.label("task_refs"),
                )
                .join(
                    WordExportTask,
                    WordExportTask.id == WordExportTaskVersion.word_export_task_id,
                )
                .where(
                    WordExportTaskVersion.word_export_task_id == word_export_task_id,
                    WordExportTaskVersion.version_no == version_no,
                )
            )
        ).first()
        if row is None:
            return False
        ver_refs = row.source_snapshot_refs if isinstance(row.source_snapshot_refs, dict) else {}
        task_refs = row.task_refs if isinstance(row.task_refs, dict) else {}
        ver_hash = ver_refs.get("tb_hash")
        task_hash = task_refs.get("tb_hash")
        if not ver_hash or not task_hash:
            return False
        return ver_hash != task_hash

    async def _resolve_year(self, project_id) -> int | None:
        """确定报表年度。

        ``word_export_task`` **没有 year 列**（年度在请求参数里传），
        故从该项目已有的 ``financial_report`` 行取最大年度 —— 那正是
        exporter 写入报表时用的年度。查不到返回 ``None``（交由调用方判不可用）。
        """
        import sqlalchemy as sa

        from app.models.report_models import FinancialReport

        return (
            await self.db.execute(
                sa.select(sa.func.max(FinancialReport.year)).where(
                    FinancialReport.project_id == project_id,
                    FinancialReport.is_deleted == sa.false(),
                )
            )
        ).scalar_one_or_none()

    async def _resolve_variant_key(self, project_id) -> str:
        """解析 Cell_Mapping 变体键，**与 `ReportExcelExporter.export` 同口径**。

        🔴 真源是**项目**的 ``template_type`` + ``report_scope``
        （``f"{template_type}_{report_scope}"``，缺省 ``soe`` / ``standalone``），
        **不是** ``word_export_task.template_type``。

        实测（真实库 14 个财务报表交付件版本）：**`word_export_task.template_type`
        全部为 NULL** ⇒ 若按它取变体键会恒得空串 ⇒ `_load_variant_mapping("")`
        返回 None ⇒ `detect()` 恒返回 None ⇒ **整个差异检测从不真正运行**
        （典型的「additive 注入即死代码」）。首版实现即踩此坑，靠真实库探针才暴露。

        `cell_mapping.json` 的合法变体键实测为四个：
        ``listed_consolidated`` / ``listed_standalone`` / ``soe_consolidated`` / ``soe_standalone``。
        """
        import sqlalchemy as sa

        from app.models.core import Project

        row = (
            await self.db.execute(
                sa.select(Project.template_type, Project.report_scope).where(
                    Project.id == project_id
                )
            )
        ).first()
        template_type = (getattr(row, "template_type", None) or "soe") if row else "soe"
        report_scope = (
            (getattr(row, "report_scope", None) or "standalone") if row else "standalone"
        )
        # 枚举字段可能是 Enum 实例，取 value
        template_type = getattr(template_type, "value", template_type)
        report_scope = getattr(report_scope, "value", report_scope)
        return f"{template_type}_{report_scope}"

    async def _recompute_expected(
        self, project_id, year: int, doc_type: str, variant_key: str
    ) -> dict[str, dict[str, Any]]:
        """按试算表重算权威值 → ``{row_code: {current_period_amount, prior_period_amount}}``。

        复用 ``ReportExcelExporter._load_report_data``（同一真源，避免两套算法漂移）；
        ``mode`` 按 doc_type 后缀选审定/未审 —— 与 exporter 的口径一致。

        🔴 签名必须实证：``_load_report_data(project_id, year, report_types, *, mode)``
        三个位置参数缺一不可（首版按 ``(project_id, mode=…)`` 调用直接抛
        `missing 2 required positional arguments`，被 fail-closed 包成
        「检测不可用」→ 会把所有报表版本都误判成阻断）。

        取数失败按 ``DriftUnavailable`` 上抛 —— 拿不到权威值时**不能**判「无差异」，
        否则等于静默放行（fail-open 的错误方向）。
        """
        try:
            from app.services.financial_cell_mapping import build_amount_lookup
            from app.services.report_excel_exporter import (
                REPORT_TYPE_SHEET_NAMES,
                ReportExcelExporter,
            )

            mode = "unadjusted" if doc_type.endswith("_unadjusted") else "audited"
            exporter = ReportExcelExporter(self.db)
            report_data = await exporter._load_report_data(  # noqa: SLF001
                project_id,
                year,
                list(REPORT_TYPE_SHEET_NAMES.keys()),
                mode=mode,
            )
            return build_amount_lookup(report_data)
        except Exception as exc:  # noqa: BLE001
            raise DriftUnavailable(f"按试算表重算权威值失败: {exc}") from exc


def _resolve_deliverable_file(file_path: str) -> Path | None:
    """解析交付文件真实路径。

    🔴 ``word_export_task_versions.file_path`` 存的是**相对 `backend/` 的相对路径**
    （``storage\\deliverables\\...``，Windows 反斜杠）。按 CWD 直接判存在性会落空
    （Task 20 的验收脚本已踩过一次）。
    """
    backend_root = Path(__file__).resolve().parents[2]
    raw = (file_path or "").replace("\\", "/")
    for cand in (Path(raw), backend_root / raw, backend_root.parent / raw):
        if cand.exists():
            return cand
    return None
