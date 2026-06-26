/**
 * Property 12: 导出文件名格式
 *
 * Feature: a-cycle-docx-online
 * Validates: Requirements 6.5
 *
 * 验证导出文件名满足 {wp_code}_{entity_name}_{period_end}.docx 模式，
 * 且 entity_name 中的文件系统特殊字符已被清理。
 *
 * 实施方案：vitest + fast-check，fc.string() 生成随机 entity_name + wp_code，numRuns: 5。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

// ─── 从 WorkpaperWordEditor.vue 提取的纯逻辑（保持一致） ───

/** 清理文件名中不安全的字符 */
function sanitizeFilename(name: string): string {
  return name.replace(/[\\/:*?"<>|]/g, '_').trim()
}

/** 构建导出文件名 */
function buildExportFilename(wpCode: string, entityName: string, periodEnd: string): string {
  const code = wpCode || 'workpaper'
  const entity = sanitizeFilename(entityName)
  const period = periodEnd || ''
  if (entity && period) return `${code}_${entity}_${period}.docx`
  if (entity) return `${code}_${entity}.docx`
  return `${code}.docx`
}

// ─── 文件系统非法字符集 ───
const ILLEGAL_CHARS = /[\\/:*?"<>|]/

// ─── Property Tests ───

describe('Property 12: 导出文件名格式', () => {
  /**
   * **Validates: Requirements 6.5**
   *
   * 对任意 wp_code、entity_name、period_end 组合，生成的导出文件名应：
   * 1. 以 .docx 结尾
   * 2. 不包含文件系统非法字符（sanitized 部分）
   * 3. 当 entity_name 和 period_end 均非空时，匹配 {wp_code}_{entity_name}_{period_end}.docx 模式
   */
  it('P12: 文件名始终以 .docx 结尾且 entity 部分不含非法字符', () => {
    // wp_code 使用真实底稿编码集合（系统控制值，非用户输入）
    const wpCodeArb = fc.constantFrom(
      'A8-1', 'A9-1', 'A10-1', 'A16-1', 'A17-3', 'A26-1', 'A27-1',
    )
    fc.assert(
      fc.property(
        wpCodeArb,
        fc.string({ minLength: 0, maxLength: 50 }),  // entity_name (任意用户输入)
        fc.string({ minLength: 0, maxLength: 12 }),  // period_end
        (wpCode, entityName, periodEnd) => {
          const filename = buildExportFilename(wpCode, entityName, periodEnd)

          // 1. 文件扩展名始终为 .docx
          expect(filename.endsWith('.docx')).toBe(true)

          // 2. entity_name 部分经过 sanitize 后不含非法字符
          const sanitized = sanitizeFilename(entityName)
          expect(ILLEGAL_CHARS.test(sanitized)).toBe(false)

          // 3. 文件名以 wp_code 开头
          expect(filename.startsWith(wpCode)).toBe(true)
        },
      ),
      { numRuns: 5 },
    )
  })

  it('P12: 当 entity_name 和 period_end 均非空时匹配完整模式', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 20 }),  // wp_code (非空)
        fc.string({ minLength: 1, maxLength: 50 })   // entity_name (非空, 含可能的特殊字符)
          .filter(s => sanitizeFilename(s).length > 0), // sanitized 后非空
        fc.string({ minLength: 1, maxLength: 12 }),  // period_end (非空)
        (wpCode, entityName, periodEnd) => {
          const filename = buildExportFilename(wpCode, entityName, periodEnd)
          const sanitized = sanitizeFilename(entityName)

          // 匹配模式: {wp_code}_{entity_name}_{period_end}.docx
          const expected = `${wpCode}_${sanitized}_${periodEnd}.docx`
          expect(filename).toBe(expected)
        },
      ),
      { numRuns: 5 },
    )
  })

  it('P12: sanitizeFilename 清除所有文件系统非法字符', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 100 }),
        (input) => {
          const result = sanitizeFilename(input)

          // 结果不含任何非法字符
          expect(ILLEGAL_CHARS.test(result)).toBe(false)

          // 如果输入不含非法字符且 trim 后相同，则输出 === trim(输入)
          if (!ILLEGAL_CHARS.test(input) && input === input.trim()) {
            expect(result).toBe(input)
          }
        },
      ),
      { numRuns: 5 },
    )
  })
})
