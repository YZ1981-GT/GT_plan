/**
 * 地址树 / 选址列表是否列出某 cell（spec acnr-foundation-defect-closure T30 / RV7-02，design §3.3）。
 *
 * 停用（deprecated）cell 不列；`/api/acnr/anchors` 仍返回它们并带标记，供已有引用定位。
 * `useAcnr.loadCellNodes`、公式选址器 `FormulaRefPicker`、地址库搜索 `stores/addressRegistry`、
 * 公式管理当前页锚点 `leftPanelAnchors` 共用这一个谓词，不各写一份判断。
 * 单独成文件（不依赖 http / SSE），纯函数模块也能直接引用。
 */
export function isListedCell(cell: { deprecated?: boolean | null } | null | undefined): boolean {
  return !!cell && !cell.deprecated
}
