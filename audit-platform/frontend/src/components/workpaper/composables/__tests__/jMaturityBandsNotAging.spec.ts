/**
 * Property 13：到期分析不是账龄。
 *
 * J1/J2 **无账龄披露**。J2「未折现的离职后福利预计到期分析」是**到期分析**（未来 4 档），
 * CAS 9 固定档位，语义与账龄（过去）相反 → 禁止套用项目账龄枚举（3年段/5年段/自定义）。
 *
 * 本守卫反向锁死：J 类组件源码不得引用 `disclosureAgingLabels` / `useAgingConfig`。
 *
 * spec: .kiro/specs/j-cycle-four-table-extraction-and-disclosure-alignment/ R10.5
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'
import { glob } from 'glob'

function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\/\/.*/g, '')
}

const J_DIRS = [
  path.resolve(__dirname, '../../j1'),
  path.resolve(__dirname, '../../j2'),
  path.resolve(__dirname, '../'),  // composables/ 下的 j 文件
]

const AGING_IMPORTS = [
  'disclosureAgingLabels',
  'useAgingConfig',
  'AgingSegment',
  'agingSegments',
  'DISCLOSURE_AGING_',
]

function getJFiles(): string[] {
  const files: string[] = []
  for (const dir of J_DIRS) {
    if (!fs.existsSync(dir)) continue
    const matches = glob.sync('**/*.{ts,vue}', { cwd: dir, absolute: true })
    for (const f of matches) {
      const base = path.basename(f).toLowerCase()
      // 排除测试文件自身（含 `Aging` 关键字作为禁止词声明）
      if (base.includes('.spec.') || base.includes('.test.')) continue
      if (base.startsWith('j1') || base.startsWith('j2') || base.startsWith('j') && !base.startsWith('j3')) {
        files.push(f)
      }
    }
  }
  return files
}

describe('J 类组件不引用账龄枚举模块（Property 13）', () => {
  const files = getJFiles()

  it('至少找到 J 类文件（反向自检防空转）', () => {
    expect(files.length).toBeGreaterThan(3)
  })

  it.each(files.map(f => [path.basename(f), f]))('%s 不含账龄引用', (_name, filePath) => {
    const src = stripComments(fs.readFileSync(filePath as string, 'utf-8'))
    for (const kw of AGING_IMPORTS) {
      expect(src).not.toContain(kw)
    }
  })

  it('J_MATURITY_BANDS 恒为 CAS 9 固定 4 档', async () => {
    const { J_MATURITY_BANDS } = await import('../jAccountScope')
    expect(J_MATURITY_BANDS).toEqual(['一年以内', '一到两年', '二到五年', '五年以上'])
    expect(J_MATURITY_BANDS).toHaveLength(4)
  })
})
