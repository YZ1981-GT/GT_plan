"""ACNR 目录加载期完整性：重复检测、禁止别名索引、内容哈希口径与报告 release 段互校。

design §5.5 / D4（T08）。从 `catalog.py` 拆出（段四审计 F4-07；`catalog.py` 已超 800 行门禁，
新逻辑一律放这里）。本模块只依赖标准库，返回「问题描述」而不直接抛异常，由 `catalog.py`
统一包成 `CatalogIntegrityError`（避免循环导入）。

内容哈希口径（`content_sha256`）：把 CRLF / CR 规范为 LF 后的 UTF-8 字节求 sha256，
即 git blob 内容的 sha256，与检出平台、core.autocrlf 无关。生成器（T07）写报告
`release.catalog_sha256` 与加载器互校都用这一口径；`.gitattributes` 对目录、报告、快照设
`text eol=lf`，Windows 检出后磁盘字节也是 LF。

报告 release 段互校（`check_release_report`，返回执行状态，供守卫断言「不是空转」）：
- 报告存在且有 release 段：release 必须同时带 `registry_version` 与 `catalog_sha256`，
  且与目录一致 → "checked"；缺字段或不一致 → 问题描述（不再「缺字段就跳过」）；
- 报告存在但无 release 段：仅当登记了过渡期旧报告（`LEGACY_REPORT_WITHOUT_RELEASE` 非 None）
  时跳过 → "legacy_skip"，运行时行为与 T07 之前一致；登记删除后一律是问题。
  登记是否仍成立由守卫按内容哈希钉住（生产报告一变、或出现 release 段，登记即失效须删除），
  所以过渡期不会无声延续；
- 报告缺失：默认生产路径 → 问题描述；`ACNR_CATALOG_PATH` 指向的其他目录 → "no_report"；
- 报告无法读取 / 解析 → 问题描述（fail-closed）。
"""
from __future__ import annotations

import contextvars
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

#: 报告里 release 段的键与必填字段（加载器与生成器共用，design §5.3 / §5.5）。
REPORT_RELEASE_KEY = "release"
REPORT_RELEASE_REQUIRED_FIELDS = ("registry_version", "catalog_sha256")

#: 过渡期登记：T07 首个合规发布批次之前的旧格式报告（无 release 段）。
#: design §18 发布顺序①要求加载器与带 release 段的新报告同提交上线，T08 先行入库，
#: 过渡期内对无 release 段的报告跳过互校（运行时行为不变）。守卫
#: test_catalog_index_fail_closed::test_production_report_release_or_registered_legacy 钉住：
#: 生产报告无 release 段时其内容哈希必须等于 report_sha256 且未过期；生产报告出现 release 段时
#: 本登记必须删除（改为 None）——删除后无 release 段的报告一律被加载器拒绝。
LEGACY_REPORT_WITHOUT_RELEASE: dict[str, str] | None = {
    "report_sha256": "71084363f411854a5ee99adcbe47482ecd03c84269d8fc12c6d35972d6ffd09b",
    "registry_version": "20260727115337",
    "owner": "acnr-foundation-defect-closure",
    "reason": "T07 首个合规发布批次之前的旧格式报告没有 release 段；加载器先于生成器重写入库，"
              "过渡期内只对这一份报告跳过 release 互校",
    "expires_on": "2027-01-31",
    "retire_when": "T07 用生成器重生成目录与带 release 段的报告并提交",
}


def content_sha256(raw: str | bytes) -> str:
    """LF 规范内容的 sha256（= git blob 内容哈希）。bytes 按 UTF-8 解码。"""
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ─── use_catalog 覆盖（只供发布门禁与测试） ─────────────────────────────────────
# 发布门禁的往返检查要用「待发布的新目录」解析，而不是磁盘上的已提交目录：
# `with use_catalog(index):` 作用域内 `catalog.get_catalog()` 返回传入的索引。
# 现状：只有 catalog_release 与测试调用；「生产代码不调用」的 AST 守卫随 T07 落地。
_catalog_override: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "_acnr_catalog_override", default=None
)


@contextmanager
def use_catalog(index: Any) -> Iterator[Any]:
    """在作用域内把 get_catalog() 指向 `index`（仅门禁 / 测试用）。"""
    token = _catalog_override.set(index)
    try:
        yield index
    finally:
        _catalog_override.reset(token)


def current_override() -> Any:
    """当前作用域的覆盖索引（无则 None）。"""
    return _catalog_override.get()


# ─── 重复 addr_id 与禁止别名 ───────────────────────────────────────────────────


def duplicate_addr_id_problems(sheets: list[dict], cells: list[dict]) -> list[str]:
    """三类 addr_id 重复（sheets 内 / cells 内 / sheet↔cell 互撞），已排序。"""
    sheet_seen: dict[str, int] = {}
    cell_seen: dict[str, int] = {}
    for s in sheets:
        aid = s.get("addr_id", "")
        sheet_seen[aid] = sheet_seen.get(aid, 0) + 1
    for c in cells:
        aid = c.get("addr_id", "")
        cell_seen[aid] = cell_seen.get(aid, 0) + 1
    problems = [f"sheets 内 addr_id 重复 {n} 次: {a}" for a, n in sheet_seen.items() if n > 1]
    problems += [f"cells 内 addr_id 重复 {n} 次: {a}" for a, n in cell_seen.items() if n > 1]
    problems += [f"addr_id 同时是 sheet 与 cell: {a}" for a in set(sheet_seen) & set(cell_seen)]
    return sorted(problems)


def format_duplicate_problems(problems: list[str]) -> str:
    head = "；".join(problems[:10])
    return f"目录 addr_id 重复 {len(problems)} 处（前 10）：{head}"


def forbidden_alias_index(sheets: list[dict]) -> dict[tuple[str, str], list[str]]:
    """同一父级内一个别名对应 ≥2 个 sheet_code ⇒ 禁止别名（exact_identity 第 3 步读它）。"""
    buckets: dict[tuple[str, str], list[str]] = {}
    for s in sheets:
        parent = s.get("parent_wp_code", "")
        code = s.get("sheet_code", "")
        for alias in s.get("sheet_name_aliases", []) or []:
            buckets.setdefault((parent, alias), []).append(code)
    return {k: sorted(v) for k, v in buckets.items() if len(v) >= 2}


# ─── 报告 release 段互校 ──────────────────────────────────────────────────────


def check_release_report(
    catalog_path: Path, raw: str | bytes, data: dict[str, Any], *, is_default_path: bool
) -> tuple[str, str | None]:
    """返回 (状态, 问题描述)。问题描述非空即应按 CatalogIntegrityError 处理。

    状态 ∈ checked / legacy_skip / no_report / rejected。
    """
    report_path = catalog_path.parent / "catalog_report.json"
    if not report_path.exists():
        if is_default_path:
            return "rejected", f"加载期互校失败：生产目录旁缺 catalog_report.json（{report_path}）"
        return "no_report", None
    try:
        report_text = report_path.read_text(encoding="utf-8")
        report = json.loads(report_text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return "rejected", f"加载期互校失败：catalog_report.json 无法读取或解析（{type(exc).__name__}）"
    if not isinstance(report, dict):
        return "rejected", "加载期互校失败：catalog_report.json 顶层不是对象"

    release = report.get(REPORT_RELEASE_KEY)
    if release is None:
        if LEGACY_REPORT_WITHOUT_RELEASE is not None:
            return "legacy_skip", None
        return "rejected", "加载期互校失败：catalog_report.json 缺 release 段（过渡期登记已删除）"
    if not isinstance(release, dict):
        return "rejected", "加载期互校失败：报告 release 段不是对象"
    missing = [f for f in REPORT_RELEASE_REQUIRED_FIELDS if not release.get(f)]
    if missing:
        return "rejected", f"加载期互校失败：报告 release 段缺字段 {missing}"

    rv_report = release["registry_version"]
    rv_catalog = data.get("registry_version")
    if rv_report != rv_catalog:
        return "rejected", (
            f"加载期互校失败：报告 release.registry_version={rv_report} 与目录 {rv_catalog} 不一致"
        )
    actual = content_sha256(raw)
    expected = str(release["catalog_sha256"])
    if actual != expected:
        return "rejected", (
            f"加载期互校失败：目录 sha256={actual[:16]}… 与报告 release.catalog_sha256={expected[:16]}… 不一致"
        )
    return "checked", None


__all__ = [
    "LEGACY_REPORT_WITHOUT_RELEASE",
    "REPORT_RELEASE_KEY",
    "REPORT_RELEASE_REQUIRED_FIELDS",
    "check_release_report",
    "content_sha256",
    "current_override",
    "duplicate_addr_id_problems",
    "forbidden_alias_index",
    "format_duplicate_problems",
    "use_catalog",
]
