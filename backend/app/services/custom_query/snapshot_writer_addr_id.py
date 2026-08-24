"""ACNR addr_id 解析（回写身份升级：裸坐标 → canonical addr_id）。

从 ``snapshot_writer.py`` 抽出（该文件已达 800 行门禁上限）。本函数只查 ACNR catalog、
不触碰 writer 实例，是纯粹的「(wp_code, sheet_name, cell_ref) → addr_id」映射。

``SnapshotWriter._resolve_addr_id`` 保留为薄委托：既有测试直接调它并做实例赋值替身。

**本函数不接受 project_id，这是有意的**：ACNR catalog 是与项目无关的**模板级**索引
（``get_catalog()`` 全局单例，addr_id 形如 ``{wp_code}/{sheet_code}/{cell}``），解析结果
不因项目而异。原签名收了一个 ``project_id`` 却从不使用，docstring 还声称「携带 project
context 进行解析（R15.4）」—— 而且有一条测试专门断言「调用时传了 project_id」，那条断言
对被调方忽略该参数的事实一无所知，属典型假绿判据。

R15.4 的项目上下文真正生效的地方是**身份解析**那条链：
``SnapshotWriter._resolve_writeback_identity`` → ``AddressingService.resolve``
（它确实吃 ``project_id`` + ``db``）。本函数只在身份确定之后做**语义标签增强**
（display_label / drilldown），不参与身份判定。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def resolve_addr_id(
    wp_code: str,
    sheet_name: str,
    cell_ref: str,
) -> dict | None:
    """通过 ACNR catalog 解析 (wp_code, sheet_name, cell_ref) 为 canonical addr_id。

    供**语义标签增强**使用（display_label / drilldown，R15.2）；回写**身份**由
    ``AddressingService`` 那条链确定，见模块 docstring。catalog 是模板级索引、与项目无关，
    故不收 project_id。

    Args:
        wp_code: 底稿编码（如 D2）
        sheet_name: sheet 名称（如 明细表D2-2）
        cell_ref: cell 引用（如 E100）

    Returns:
        dict with {addr_id, uri, formula_ref, entry_type, jump_route} or None on miss
    """
    try:
        from app.services.acnr.catalog import get_catalog

        # 尝试通过 catalog lookup 获取 sheet → addr_id
        # 1. 先确定 sheet_code：从 sheet_name 反查（别名机制）
        cat = get_catalog()

        # 构建 sheet-level addr_id：通过 wp_code + sheet_name 反查
        sheet_entry = None

        # 尝试通过 sheet_name 在别名索引中查找
        alias_matches = cat.sheets_by_alias.get(sheet_name, [])
        if wp_code and alias_matches:
            filtered = [m for m in alias_matches if m.get("parent_wp_code") == wp_code]
            if len(filtered) == 1:
                sheet_entry = filtered[0]
            elif not filtered and len(alias_matches) == 1:
                sheet_entry = alias_matches[0]

        # 如果别名反查未命中，尝试 sheet_code 索引
        if not sheet_entry:
            code_matches = cat.sheets_by_code.get(sheet_name, [])
            if wp_code and code_matches:
                code_matches = [m for m in code_matches if m.get("parent_wp_code") == wp_code]
            if len(code_matches) == 1:
                sheet_entry = code_matches[0]

        if not sheet_entry:
            # catalog miss — 降级返回 None（不阻塞写回主流程）
            logger.debug(
                "ACNR addr_id resolve miss: wp_code=%s sheet_name=%s",
                wp_code, sheet_name,
            )
            return None

        sheet_addr_id = sheet_entry.get("addr_id", "")

        # 2. 如果有 cell_ref，构造 cell-level addr_id
        if cell_ref:
            # canonical addr_id = {parent}/{sheet_code}/{cell_address}
            cell_addr_id = f"{sheet_addr_id}/{cell_ref}"

            # 尝试精确 cell 命中
            cell_entry = cat.cells_by_addr_id.get(cell_addr_id)
            if cell_entry:
                return {
                    "addr_id": cell_entry.get("addr_id"),
                    "uri": cell_entry.get("uri"),
                    "formula_ref": cell_entry.get("formula_ref"),
                    "entry_type": "cell",
                    "semantic_label": cell_entry.get("semantic_label"),
                    "parent_addr_id": cell_entry.get("parent_addr_id"),
                    "jump_route": sheet_entry.get("jump_route_template"),
                    "column_metadata": {
                        "addr_id": cell_entry.get("addr_id"),
                        "display_label": (
                            cell_entry.get("semantic_label")
                            or cell_entry.get("addr_id")
                        ),
                        "cell_address": cell_ref,
                        "sheet_addr_id": sheet_addr_id,
                        "drilldown_enabled": True,
                    },
                }

            # Cell 未在 L1 种子中注册：构造 runtime addr_id
            # 仍返回可用的 addr_id（格式正确但非 L1 注册）
            return {
                "addr_id": cell_addr_id,
                "uri": None,
                "formula_ref": None,
                "entry_type": "cell",
                "semantic_label": None,
                "parent_addr_id": sheet_addr_id,
                "jump_route": sheet_entry.get("jump_route_template"),
                "column_metadata": {
                    "addr_id": cell_addr_id,
                    "display_label": cell_addr_id,
                    "cell_address": cell_ref,
                    "sheet_addr_id": sheet_addr_id,
                    "drilldown_enabled": True,
                },
            }

        # 3. 仅 sheet 级
        return {
            "addr_id": sheet_addr_id,
            "uri": None,
            "formula_ref": None,
            "entry_type": "sheet",
            "semantic_label": None,
            "parent_addr_id": None,
            "jump_route": sheet_entry.get("jump_route_template"),
            "column_metadata": {
                "addr_id": sheet_addr_id,
                "display_label": sheet_entry.get("display_label") or sheet_addr_id,
                "cell_address": None,
                "sheet_addr_id": sheet_addr_id,
                "drilldown_enabled": False,
            },
        }

    except Exception as e:
        # ACNR 解析失败不阻塞写回主流程（降级策略）
        logger.warning("ACNR addr_id resolve error (non-fatal): %s", e)
        return None
