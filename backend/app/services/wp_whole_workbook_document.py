"""「完整Excel」整册模式的**源文档身份**解析。

从 `wp_onlyoffice_router` 抽出的伴生模块：这里的每一条都是**业务判定**（哪份文档才算这个
wp_code 的整本、两份候选选哪份、工作副本叫什么名字），不是路由参数搬运。router 只负责在
config / WOPI contents / OO 降级 grid / callback 四个点上消费本模块的结论。

═══ 为什么整册不能沿用主模板口径 ═══

`wp_template_finder.find_template_file_any(wp_code)` 是**主模板**口径，走「审定 > 常规程序」
优先级阶梯。D4 上它返回 ``D4-1至D4-4 …审定表明细表…xlsx`` —— 只有 10 张 sheet。于是标着
「完整Excel」的页签打开的根本不是整本：``境外销售收入检查D4-26`` 等 36 张 sheet 在那份文件里
**不存在**（真整册本 ``D4 收入底稿.xlsx`` 有 46 张）。

═══ 两份整册本选哪份（字节判据的由来）═══

D4 目录同时存在净化前后两份整册本，sheet 名序列完全相同、只差有无外部引用：

* ``D4 收入底稿.xlsx``（199176 B, sha ``b8fb92d4…``）= sync 契约 ``d4.revenue_detail``
  的 ``TemplateRef`` 钉住的那份，``xl/workbook.xml`` **无** ``<externalReference>``
  （``scripts/fix/sanitize_d4_template_external_links.py`` 净化的就是它）；
* ``D4收入底稿.xlsx``（352950 B）未净化，带 36 个 ``xl/externalLinks/`` 部件 —— 给 OO 打开
  就是刷新提示 + ``#REF!``。

候选**枚举**留在 `wp_template_finder.find_whole_workbook_templates`（那个模块是纯路径解析，
不读 xlsx 字节，`test_template_override_lossless` 的落盘路径白名单就是按这条登记它的）；
**挑哪份**需要字节事实，因此落在本模块。
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

#: 整册模式工作副本的文件名后缀。
#:
#: 🔴 为什么整册模式必须**独立一份**工作副本，而不是继续共用 `{wp_code}.xlsx`：
#:
#: `wp_onlyoffice_router._resolve_wp_file` 的缓存名只按 wp_code 取，隐含假设「一个 wp_code
#: 对应一份文档」。整册口径修正后这个假设不再成立 —— 整册本（D4 46 张）与主模板（审定包
#: 10 张）是**两份不同的文档**。共用一个文件名会有两个后果：
#:
#: 1. **修了不生效**：`_resolve_wp_file` 见到缓存已存在就直接复用。本次改动之前开过
#:    「完整Excel」的项目，缓存里那份 10 张 sheet 的审定包会被永久复用。
#: 2. **不敢自愈**：实测某项目的 `D4.xlsx` 有 30 个 zip 部件而模板有 49 个（丢
#:    `sharedStrings.xml` / `calcChain.xml` / `worksheets/_rels/*`）—— 那是**历史 openpyxl
#:    全量重写**留下的残骸（见 `_hide_non_target_sheets` 的实测记录）。它证不出「从未被
#:    编辑」，所以任何"旧缓存不对就删掉重播种"的自愈都不敢落地，否则可能删掉用户成果。
#:
#: 按文档身份分开命名同时解掉这两条：整册永远从整册本播种（老项目立即生效），旧
#: `{wp_code}.xlsx` 一个字节不动（零数据风险）。回写侧由 callback 的 `whole=1` 走同一
#: stem，读写仍然同码。
WHOLE_CACHE_SUFFIX = "__whole"


def whole_cache_stem(wp_code: str) -> str:
    """整册模式工作副本的文件名主干（不含扩展名）。读写两侧的唯一来源。"""
    return f"{wp_code}{WHOLE_CACHE_SUFFIX}"


def has_external_references(path: Path) -> bool:
    """`xl/workbook.xml` 里是否有 `<externalReference>`（= 带断链的跨簿引用）。

    读**不到**就当"不确定"返回 True（宁可落到下一个候选）。
    """
    try:
        with zipfile.ZipFile(path) as zf:
            return "<externalReference" in zf.read("xl/workbook.xml").decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("整册本外部引用探测失败 %s: %s", path.name, exc)
        return True


def resolve_whole_workbook_template(wp_code: str) -> Path | None:
    """该 wp_code 的**整册合并本**（净化过的那份优先）；没有则 None。

    无整册合并本的 wp_code（D2 等只有范围式拆分包）返回 None，调用方按原口径回落
    `find_template_file_any` —— 本函数是**纯加法**，不改那些底稿的行为。
    """
    from app.services.wp_template_finder import find_whole_workbook_templates

    candidates = find_whole_workbook_templates(wp_code)
    if not candidates:
        return None
    for path in candidates:
        if not has_external_references(path):
            return path
    # 全都未净化（如 F2 只有一份 F2存货.xlsx）：仍返回首个候选 —— 46/74 张的整本
    # 依然比 10 张的审定包更符合「完整Excel」语义，净化是另一条待办。
    logger.info(
        "整册本候选 %s 均含未净化外部引用，取首个：%s",
        [p.name for p in candidates], candidates[0].name,
    )
    return candidates[0]


def whole_workbook_template_or_primary(wp_code: str) -> Path | None:
    """整册模式的模板解析单一入口：整册合并本优先，否则回落主模板（现状口径）。"""
    from app.services.wp_template_finder import find_template_file_any

    return resolve_whole_workbook_template(wp_code) or find_template_file_any(wp_code)


__all__ = [
    "WHOLE_CACHE_SUFFIX",
    "has_external_references",
    "resolve_whole_workbook_template",
    "whole_cache_stem",
    "whole_workbook_template_or_primary",
]
