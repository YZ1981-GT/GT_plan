/**
 * F3/F4/F5 科目码单一真源守卫（Property 8 前端侧）。
 *
 * 断言 F3/F4/F5 组件源码不得出现裸科目码作为科目码/请求参数/事件载荷。
 * 合法使用：注释中引用后端键名（如 `tb_values['2201']`）、scope 文件本身。
 *
 * spec: f-cycle-four-table-extraction-and-disclosure-completion Task 7.4
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'

const WORKPAPER_DIR = path.resolve(__dirname, '../..')

/**
 * 递归收集目录下所有 .vue/.ts 文件（排除 __tests__ 和 node_modules）
 */
function collectFiles(dir: string, ext: string[]): string[] {
  const results: string[] = []
  if (!fs.existsSync(dir)) return results
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === '__tests__' || entry.name === 'node_modules') continue
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      results.push(...collectFiles(full, ext))
    } else if (ext.some((e) => entry.name.endsWith(e))) {
      results.push(full)
    }
  }
  return results
}

function stripComments(src: string): string {
  // Strip single-line comments
  let result = src.replace(/\/\/[^\n]*/g, '')
  // Strip multi-line comments
  result = result.replace(/\/\*[\s\S]*?\*\//g, '')
  // Strip HTML comments
  result = result.replace(/<!--[\s\S]*?-->/g, '')
  return result
}

interface ScopeCheck {
  cycleDir: string
  scopeFile: string
  code: string
  codeLabel: string
}

const CHECKS: ScopeCheck[] = [
  {
    cycleDir: 'f3-notes-payable',
    scopeFile: 'f3AccountScope.ts',
    code: '2201',
    codeLabel: 'F3 应付票据 2201',
  },
  {
    cycleDir: 'f4-accounts-payable',
    scopeFile: 'f4AccountScope.ts',
    code: '2202',
    codeLabel: 'F4 应付账款 2202',
  },
  {
    cycleDir: 'f5-cost-of-sales',
    scopeFile: 'f5AccountScope.ts',
    code: '6401',
    codeLabel: 'F5 营业成本 6401',
  },
]

describe('F3/F4/F5 科目码字面量清零守卫', () => {
  for (const check of CHECKS) {
    describe(check.codeLabel, () => {
      const cycleFullDir = path.join(WORKPAPER_DIR, check.cycleDir)
      const files = collectFiles(cycleFullDir, ['.vue', '.ts'])

      it(`${check.cycleDir} 目录下至少有组件文件`, () => {
        expect(files.length).toBeGreaterThan(0)
      })

      it(`组件源码（去注释后）不得含裸 '${check.code}' 作为科目码`, () => {
        const violations: string[] = []
        // 匹配 accountCode: 'XXXX' / subjectPrefix: 'XXXX' / subjectCode: 'XXXX'
        // 以及请求参数中的 accountCode: 'XXXX'
        const pattern = new RegExp(
          `(?:accountCode|subjectPrefix|subjectCode|account_code)\\s*[:=]\\s*['"\`]${check.code}['"\`]`,
        )

        for (const file of files) {
          const rel = path.relative(WORKPAPER_DIR, file)
          // 跳过 scope 文件本身（它声明常量是合法的）
          if (rel.includes(check.scopeFile)) continue

          const raw = fs.readFileSync(file, 'utf-8')
          const stripped = stripComments(raw)

          if (pattern.test(stripped)) {
            violations.push(rel)
          }
        }

        expect(violations).toEqual([])
      })

      it(`scope 文件 ${check.scopeFile} 存在且导出常量`, () => {
        const scopePath = path.join(WORKPAPER_DIR, 'composables', check.scopeFile)
        expect(fs.existsSync(scopePath)).toBe(true)
        const content = fs.readFileSync(scopePath, 'utf-8')
        expect(content).toContain('REPORT_ROW_CODE')
        expect(content).toContain('GROSS_FALLBACK_STANDARD')
      })
    })
  }

  // 反向自检：确保守卫不是空转（scope 文件里确实含被检字面量）
  describe('反向自检', () => {
    for (const check of CHECKS) {
      it(`${check.scopeFile} 确实含 '${check.code}' 字面量（证明守卫非空转）`, () => {
        const scopePath = path.join(WORKPAPER_DIR, 'composables', check.scopeFile)
        const content = fs.readFileSync(scopePath, 'utf-8')
        expect(content).toContain(`'${check.code}`)
      })
    }
  })
})
