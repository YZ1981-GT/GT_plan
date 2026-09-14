/**
 * dispatchRetirement.spec.ts — 契约守卫：防 dispatch_records 死脚手架复活
 *
 * Property 7: 退役后无死脚手架运行时引用
 * Validates: Requirements 3.1, 3.4, 6.3
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'

const CONFIRMATION_ROOT = path.resolve(__dirname, '../..')

function collectTsVueFiles(dir: string): string[] {
  const result: string[] = []
  if (!fs.existsSync(dir)) return result
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '__tests__') continue
      result.push(...collectTsVueFiles(fullPath))
    } else if (/\.(ts|vue)$/.test(entry.name)) {
      result.push(fullPath)
    }
  }
  return result
}

describe('dispatch_records retirement guard (P7)', () => {
  const sourceFiles = collectTsVueFiles(CONFIRMATION_ROOT)

  it('no runtime import of useConfirmationDispatch in confirmation tree', () => {
    const violations: string[] = []
    for (const file of sourceFiles) {
      const content = fs.readFileSync(file, 'utf-8')
      // Only flag actual import statements, not comments
      if (/^\s*import\b.*useConfirmationDispatch/m.test(content)) {
        violations.push(path.relative(CONFIRMATION_ROOT, file))
      }
    }
    expect(violations).toEqual([])
  })

  it('no runtime import of useDownstreamDispatch in confirmation tree', () => {
    const violations: string[] = []
    for (const file of sourceFiles) {
      const content = fs.readFileSync(file, 'utf-8')
      if (/^\s*import\b.*useDownstreamDispatch/m.test(content)) {
        violations.push(path.relative(CONFIRMATION_ROOT, file))
      }
    }
    expect(violations).toEqual([])
  })

  it('no runtime import of dispatchApi in confirmation tree', () => {
    const violations: string[] = []
    for (const file of sourceFiles) {
      const content = fs.readFileSync(file, 'utf-8')
      if (/^\s*import\b.*dispatchApi/m.test(content)) {
        violations.push(path.relative(CONFIRMATION_ROOT, file))
      }
    }
    expect(violations).toEqual([])
  })
})
