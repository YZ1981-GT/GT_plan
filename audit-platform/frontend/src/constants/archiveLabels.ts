/**
 * 归档相关中文标签（spec attachment-archive-and-a-class-evidence 需求 5.3）：完整性检查类别、编排步骤。
 * 向导与完整性报告共用这一张表；改造前类别只有 4 个有中文，`sampling_records` 与失败步骤直接显示英文键名。
 */

export const ARCHIVE_CATEGORY_LABELS: Record<string, string> = {
  missing: '缺失底稿',
  unsigned: '未签字底稿',
  unresolved_reviews: '未解决复核意见',
  stale: '过期底稿',
  sampling_records: '抽样记录不完整',
  missing_files: '文件缺失',
  evidence_gaps: '证据缺口',
  unreplied_confirmations: '函证未回函',
  unconfirmed_ocr: '识别结果未确认',
  orphan_files: '孤儿文件',
}

/** 编排步骤（后端 ``ARCHIVE_SECTIONS``）；``wp_storage`` 是改造前的旧步骤名，历史作业仍可能显示 */
export const ARCHIVE_SECTION_LABELS: Record<string, string> = {
  gate: '门禁检查',
  package: '生成归档包',
  push_to_cloud: '推送云端',
  lock: '锁定项目',
  purge_local: '清理本地数据',
  wp_storage: '底稿打包（旧流程）',
}

export function archiveCategoryLabel(category: string): string {
  return ARCHIVE_CATEGORY_LABELS[category] || category
}

export function archiveSectionLabel(section: string | null | undefined): string {
  if (!section) return ''
  return ARCHIVE_SECTION_LABELS[section] || section
}
