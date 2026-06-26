/**
 * 子文档导航可用性映射逻辑
 *
 * 纯函数，可用于属性测试。
 * Requirements: 6.3, 6.4, 6.5
 */

export interface SubDocItem {
  wp_code: string
  label: string
  exists: boolean
  wp_id: string | null
}

/** A17 子文档定义（A17-2 ~ A17-7） */
export const SUB_DOC_DEFINITIONS: Array<{ wp_code: string; label: string }> = [
  { wp_code: 'A17-2', label: 'KAM' },
  { wp_code: 'A17-3', label: '业务咨询' },
  { wp_code: 'A17-4', label: '分歧记录' },
  { wp_code: 'A17-5', label: '完成核对表' },
  { wp_code: 'A17-6', label: '总结会' },
  { wp_code: 'A17-7', label: '独立性声明' },
]

/**
 * 根据 wp_index 数据映射子文档可用性。
 *
 * @param wpIndex - 项目 wp_index 条目（至少含 wp_code 和 wp_id）
 * @returns SubDocItem[] 固定 6 条（A17-2~A17-7），exists 由 wp_index 决定
 */
export function mapSubDocAvailability(
  wpIndex: Array<{ wp_code: string; wp_id?: string | null }>,
): SubDocItem[] {
  const existingMap = new Map<string, string | null>()
  for (const item of wpIndex) {
    if (item.wp_code.startsWith('A17-') && item.wp_code !== 'A17-1') {
      existingMap.set(item.wp_code, item.wp_id || null)
    }
  }

  return SUB_DOC_DEFINITIONS.map((def) => ({
    wp_code: def.wp_code,
    label: def.label,
    exists: existingMap.has(def.wp_code),
    wp_id: existingMap.get(def.wp_code) || null,
  }))
}
