/** 循环底稿右侧复核入口默认 sectionId */
export function resolveCycleReviewSection(
  cyclePrefix: string,
  sheetCode: string,
  label?: string,
): { id: string; label: string } {
  const code = sheetCode || cyclePrefix
  const normalized = code.replace(/\s+/g, '-')
  return {
    id: `${cyclePrefix}-${normalized}-header`,
    label: label ?? `${cyclePrefix} ${code}`,
  }
}
