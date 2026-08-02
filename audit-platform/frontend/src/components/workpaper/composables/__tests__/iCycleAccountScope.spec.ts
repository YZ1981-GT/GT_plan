/**
 * I 循环科目口径单一真源测试（I1~I6）。
 *
 * 覆盖：
 * 1. 参数化 iNGrossQueryCodes（6 循环 × 3 情形 = 18 用例）
 * 2. I1 三段函数（i1AmortQueryCodes / i1ImpairQueryCodes）各 2 用例
 * 3. Property 2 反向自检（源码禁止硬编码科目码逻辑）
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'

import {
  i1GrossQueryCodes,
  i1AmortQueryCodes,
  i1ImpairQueryCodes,
  I1_GROSS_FALLBACK_STANDARD,
  I1_AMORT_FALLBACK,
  I1_IMPAIR_FALLBACK,
} from '../i1AccountScope'
import { i2GrossQueryCodes, I2_GROSS_FALLBACK_STANDARD } from '../i2AccountScope'
import { i3GrossQueryCodes, I3_GROSS_FALLBACK_STANDARD } from '../i3AccountScope'
import { i4GrossQueryCodes, I4_GROSS_FALLBACK_STANDARD } from '../i4AccountScope'
import { i5GrossQueryCodes, I5_GROSS_FALLBACK_STANDARD } from '../i5AccountScope'
import { i6GrossQueryCodes, I6_GROSS_FALLBACK_STANDARD } from '../i6AccountScope'

// ---------- 1. 参数化 iNGrossQueryCodes ----------

interface GrossCase {
  label: string
  fn: (src?: any) => string[]
  fallback: string
  /** I5 无兜底码，空对象/null 时返回 [] */
  emptyReturnsEmpty?: boolean
}

const grossCases: GrossCase[] = [
  { label: 'I1', fn: i1GrossQueryCodes, fallback: I1_GROSS_FALLBACK_STANDARD },
  { label: 'I2', fn: i2GrossQueryCodes, fallback: I2_GROSS_FALLBACK_STANDARD },
  { label: 'I3', fn: i3GrossQueryCodes, fallback: I3_GROSS_FALLBACK_STANDARD },
  { label: 'I4', fn: i4GrossQueryCodes, fallback: I4_GROSS_FALLBACK_STANDARD },
  { label: 'I5', fn: i5GrossQueryCodes, fallback: I5_GROSS_FALLBACK_STANDARD, emptyReturnsEmpty: true },
  { label: 'I6', fn: i6GrossQueryCodes, fallback: I6_GROSS_FALLBACK_STANDARD },
]

describe('iNGrossQueryCodes 参数化（6循环×3情形）', () => {
  for (const c of grossCases) {
    describe(c.label, () => {
      it('有溯源 {gross_standard: ["xxx"]} → 返回 ["xxx"]', () => {
        const result = c.fn({ gross_standard: ['xxx'] })
        expect(result).toEqual(['xxx'])
      })

      it('空对象 {} → 返回兜底码', () => {
        const result = c.fn({})
        if (c.emptyReturnsEmpty) {
          expect(result).toEqual([])
        } else {
          expect(result).toEqual([c.fallback])
        }
      })

      it('null → 返回兜底码', () => {
        const result = c.fn(null)
        if (c.emptyReturnsEmpty) {
          expect(result).toEqual([])
        } else {
          expect(result).toEqual([c.fallback])
        }
      })
    })
  }
})

// ---------- 2. I1 三段函数 ----------

describe('i1AmortQueryCodes', () => {
  it('有 segments amortization → 取对应段', () => {
    const src = { segments: [{ segment: 'amortization', standard: ['1702A'] }] }
    expect(i1AmortQueryCodes(src)).toEqual(['1702A'])
  })

  it('无 segments → 返回兜底码', () => {
    expect(i1AmortQueryCodes(null)).toEqual([I1_AMORT_FALLBACK])
  })
})

describe('i1ImpairQueryCodes', () => {
  it('有 segments impairment → 取对应段', () => {
    const src = { segments: [{ segment: 'impairment', standard: ['1703B'] }] }
    expect(i1ImpairQueryCodes(src)).toEqual(['1703B'])
  })

  it('无 segments → 返回兜底码', () => {
    expect(i1ImpairQueryCodes({})).toEqual([I1_IMPAIR_FALLBACK])
  })
})

// ---------- 3. Property 2 反向自检 ----------

describe('Property 2: I 类审定表/披露 Tab 源码禁止硬编码科目码逻辑', () => {
  /**
   * 扫 6 个审定表（I{N}TabAdjudication.vue）+ 12 个披露 Tab（I{N}TabDisclosure{Listed,Soe}.vue）
   * 去掉注释后不得出现 startsWith('1717') / startsWith('1911') / .startsWith('6602') / '1712'
   */
  const composablesDir = path.resolve(__dirname, '..', '..')
  const targetFiles: string[] = []

  for (let n = 1; n <= 6; n++) {
    targetFiles.push(`I${n}TabAdjudication.vue`)
    targetFiles.push(`I${n}TabDisclosureListed.vue`)
    targetFiles.push(`I${n}TabDisclosureSoe.vue`)
  }

  /** 递归查找文件（在 composablesDir 的父目录即 workpaper 目录下搜索） */
  function findFiles(dir: string, name: string): string[] {
    const results: string[] = []
    let entries: fs.Dirent[]
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true })
    } catch {
      return results
    }
    for (const entry of entries) {
      const full = path.join(dir, entry.name)
      if (entry.isDirectory() && !entry.name.startsWith('.') && entry.name !== 'node_modules') {
        results.push(...findFiles(full, name))
      } else if (entry.isFile() && entry.name === name) {
        results.push(full)
      }
    }
    return results
  }

  function stripComments(src: string): string {
    // 去掉单行注释和多行注释
    return src
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/\/\/[^\n]*/g, '')
  }

  const forbiddenPatterns = [
    /startsWith\(['"]1717['"]\)/,
    /startsWith\(['"]1911['"]\)/,
    /\.startsWith\(['"]6602['"]\)/,
    /['"]1712['"]/,
  ]

  const foundFiles: string[] = []

  for (const fileName of targetFiles) {
    const matches = findFiles(composablesDir, fileName)
    foundFiles.push(...matches)
  }

  // 反向自检：至少 12 个文件存在
  it('反向自检：至少 12 个 I 类审定表/披露 Tab 文件存在', () => {
    expect(foundFiles.length).toBeGreaterThanOrEqual(12)
  })

  it('所有 I 类审定表/披露 Tab 去掉注释后不得含硬编码科目码逻辑', () => {
    const violations: string[] = []

    for (const filePath of foundFiles) {
      const raw = fs.readFileSync(filePath, 'utf-8')
      const cleaned = stripComments(raw)
      for (const pat of forbiddenPatterns) {
        if (pat.test(cleaned)) {
          violations.push(`${path.basename(filePath)}: ${pat.source}`)
        }
      }
    }

    expect(violations).toEqual([])
  })
})
