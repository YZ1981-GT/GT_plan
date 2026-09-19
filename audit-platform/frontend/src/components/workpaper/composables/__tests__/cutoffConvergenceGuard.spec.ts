/**
 * cutoffConvergenceGuard — 截止跨期判定「单一真源」契约守卫
 *
 * Spec: cutoff-test-architecture-convergence Wave 7 Task 12
 *
 * 目的：防止未来再度漂移回多轨状态。断言 I2/I6/K8/K9 截止的两套跨期判定核心【算术】
 * 只存在于 cutoffCanonical.ts（单一真源），其它 composable 一律薄封装委托。
 *
 * 允许列表（allowlist）：
 * - cutoffCanonical.ts：唯一持有 XOR（截止日两侧）与自然月比较算术
 *
 * F2 存货截止（f2CutoffJudgment.ts）已收敛为 canonical 第三模式消费者——
 * classifyCutoffTiming 委托 cutoffCanonical.classifyCutoffBoundary（XOR 算术单一真源），
 * F2 仅保留 early_book/late_book/cross_other 业务子类映射，不再持有裸算术，故不再豁免。
 *
 * 若新增文件出现裸 XOR / 自然月跨期算术而未走 canonical → 本守卫失败，提示走 cutoffCanonical。
 */
import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const COMPOSABLES_DIR = join(process.cwd(), 'src/components/workpaper/composables')

/** XOR 截止日两侧跨期算术：形如 `xOnOrBefore !== yOnOrBefore` 或 `=== `（classifyCutoffBoundary 用 ===） */
const XOR_BOUNDARY = /\w*[Oo]nOrBefore\s*(?:!==|===)\s*\w*[Oo]nOrBefore/
/** 自然月比较算术：year*12 序号或 year+month 双比较 */
const NATURAL_MONTH = /getFullYear\(\)\s*\*\s*12|Period\.year\s*!==\s*\w+Period\.year/

const CANONICAL = 'cutoffCanonical.ts'
// F2 已委托 canonical 第三模式，不再持有裸算术；仅 canonical 自身在允许列表
const ALLOWLIST = new Set([CANONICAL])

function listTsFiles(dir: string): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) continue
    if (name.endsWith('.ts') && !name.endsWith('.spec.ts')) out.push(name)
  }
  return out
}

describe('截止跨期判定单一真源契约守卫', () => {
  const files = listTsFiles(COMPOSABLES_DIR)

  it('canonical 模块存在且持有两套算术', () => {
    const src = readFileSync(join(COMPOSABLES_DIR, CANONICAL), 'utf-8')
    expect(XOR_BOUNDARY.test(src)).toBe(true)
    expect(NATURAL_MONTH.test(src)).toBe(true)
  })

  it('XOR（截止日两侧）跨期算术只存在于 cutoffCanonical.ts', () => {
    const offenders = files.filter((f) => {
      if (ALLOWLIST.has(f)) return false
      return XOR_BOUNDARY.test(readFileSync(join(COMPOSABLES_DIR, f), 'utf-8'))
    })
    expect(offenders, `以下文件出现裸 XOR 跨期算术，应改为委托 cutoffCanonical.crossesByCutoffBoundary: ${offenders.join(', ')}`).toEqual([])
  })

  it('自然月跨期比较算术只存在于 cutoffCanonical.ts', () => {
    const offenders = files.filter((f) => {
      if (ALLOWLIST.has(f)) return false
      return NATURAL_MONTH.test(readFileSync(join(COMPOSABLES_DIR, f), 'utf-8'))
    })
    expect(offenders, `以下文件出现裸自然月跨期算术，应改为委托 cutoffCanonical.crossesByNaturalMonth: ${offenders.join(', ')}`).toEqual([])
  })
})
