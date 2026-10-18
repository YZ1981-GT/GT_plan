/**
 * sheetKeyNormalizationParity.spec.ts — 前端↔后端 sheet 名归一一致性断言（前端侧）
 * spec formula-manager-closure · Task 1.3 / ADR-FMC-01（稳定键单一真源 NIT-1）
 *
 * 验收判据（tasks.md Task 1.3）：
 *   前端本地归一 normalizeSheetKey 的结果，必须与后端 stable_key.normalize_sheet_key
 *   对同一组 sheet 名（含带排序前缀「五、1 审定表D2-1」、全角空格、大小写敏感 wp_code）
 *   产出一致。
 *
 * 承接方式：读后端真源产出的同一张 golden 对照表
 *   backend/tests/fixtures/sheet_key_normalization_parity.json
 * 断言 TS normalizeSheetKey(input) === golden.expected。后端侧另有
 *   backend/tests/test_sheet_key_normalization_parity.py 断言 golden 确由后端真源产出。
 * 两侧同对一张 golden ⇒ TS 归一 == Python 归一（传递闭包）。禁在前端另写一套归一（NIT-1）。
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { describe, it, expect } from 'vitest'
import { normalizeSheetKey } from '../sheetIdentityMatch'

// 从本测试文件定位仓库根下的后端 golden。
// __tests__ → formula → components → src → frontend → audit-platform → <repo root> = 向上 6 级。
const __here = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(__here, '../../../../../..')
const GOLDEN_PATH = path.join(
  REPO_ROOT,
  'backend',
  'tests',
  'fixtures',
  'sheet_key_normalization_parity.json',
)

interface ParityPair {
  input: string
  expected: string
}
interface ParityGolden {
  pairs: ParityPair[]
}

function loadGolden(): ParityGolden {
  const raw = readFileSync(GOLDEN_PATH, 'utf-8')
  const data = JSON.parse(raw) as ParityGolden
  if (!Array.isArray(data.pairs) || data.pairs.length === 0) {
    throw new Error('golden 对照表为空 —— 判据抽不到值（防空转）')
  }
  return data
}

describe('normalizeSheetKey 前端↔后端一致性（golden 对照）', () => {
  const golden = loadGolden()

  it('golden 覆盖任务点名的三类样本（防空转）', () => {
    const inputs = golden.pairs.map((p) => p.input)
    expect(inputs).toContain('五、1 审定表D2-1') // 带排序前缀
    expect(inputs.some((i) => i.includes('\u3000'))).toBe(true) // 全角空格
    expect(inputs).toContain('E1-1') // 大小写敏感
    expect(inputs).toContain('e1-1')
  })

  it.each(loadGolden().pairs)('TS 归一 %o 与后端真源一致', (pair) => {
    expect(normalizeSheetKey(pair.input)).toBe(pair.expected)
  })

  // ── 变异反证（铁律㉒）：若前端另写一套归一（偏离真源），一致性断言必打红 ──
  it('变异体（不剥排序前缀）会与后端真源不一致；生产 normalizeSheetKey 一致', () => {
    function tamperedNormalize(s: string): string {
      // 偏离真源：直接 trim，不剥「五、1 」这类排序前缀
      return (s || '').trim()
    }
    const sample = '五、1 审定表D2-1'
    const backendExpected = golden.pairs.find((p) => p.input === sample)!.expected
    // 变异体保留前缀 → 与后端真源不一致（坐实：前端一旦自写归一，本测试会红）
    expect(tamperedNormalize(sample)).not.toBe(backendExpected)
    expect(tamperedNormalize(sample)).toBe('五、1 审定表D2-1')
    // 反向断言：生产函数（复用单一真源口径）与后端一致（未注入不命中）
    expect(normalizeSheetKey(sample)).toBe(backendExpected)
    expect(backendExpected).toBe('审定表D2-1')
  })
})
