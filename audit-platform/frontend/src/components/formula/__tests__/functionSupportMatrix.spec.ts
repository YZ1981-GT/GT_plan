/**
 * functionSupportMatrix.spec.ts — 函数支持矩阵前端↔后端一致性（前端侧）
 * spec formula-manager-closure · Task 4.2 / 需求 8（禁静默 0）
 *
 * 承接方式：读后端真源产出的同一张 golden
 *   backend/tests/fixtures/function_support_matrix.json
 * 断言 TS buildMatrixPayload() === golden，且 isFunctionSupported/unsupportedReason 与 golden 逐格一致。
 * 后端侧另有 backend/tests/formula_management/test_function_support_matrix.py 断言 golden 确由后端真源产出。
 * 两侧同对一张 golden ⇒ 前端矩阵 == 后端真相（传递闭包）。
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { describe, it, expect } from 'vitest'
import {
  buildMatrixPayload,
  isFunctionSupported,
  unsupportedReason,
  FUNCTIONS,
  EXECUTORS,
  type Executor,
} from '../functionSupportMatrix'

// __tests__ → formula → components → src → frontend → audit-platform → <repo root> = 向上 6 级。
const __here = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(__here, '../../../../../..')
const GOLDEN_PATH = path.join(
  REPO_ROOT,
  'backend',
  'tests',
  'fixtures',
  'function_support_matrix.json',
)

interface Cell {
  supported: boolean
  reason: string | null
}
interface Golden {
  schema_version: number
  functions: string[]
  executors: string[]
  matrix: Record<string, Record<string, Cell>>
}

function loadGolden(): Golden {
  const data = JSON.parse(readFileSync(GOLDEN_PATH, 'utf-8')) as Golden
  if (!data.matrix || Object.keys(data.matrix).length === 0) {
    throw new Error('golden 矩阵为空 —— 判据抽不到值（防空转）')
  }
  return data
}

describe('functionSupportMatrix 前端↔后端一致性（golden 对拍）', () => {
  const golden = loadGolden()

  it('前端 buildMatrixPayload 与后端 golden 逐字节一致', () => {
    expect(buildMatrixPayload()).toEqual(golden)
  })

  it('golden 覆盖四执行器 + 报告点名函数（防空转）', () => {
    expect(new Set(golden.executors)).toEqual(
      new Set(['wp_evaluator', 'report_path', 'note_executor', 'central_batch']),
    )
    for (const fn of ['TB', 'SUM_TB', 'WP', 'PREV', 'AUX', 'ADJ']) {
      expect(golden.functions).toContain(fn)
    }
  })

  it('isFunctionSupported/unsupportedReason 与 golden 每一格一致', () => {
    for (const fn of FUNCTIONS) {
      for (const exe of EXECUTORS) {
        const cell = golden.matrix[fn][exe]
        expect(isFunctionSupported(fn, exe)).toBe(cell.supported)
        expect(unsupportedReason(fn, exe)).toBe(cell.supported ? null : cell.reason)
      }
    }
  })

  it('不支持者必有显式原因（UI 据此标注「此处不支持」，禁静默 0）', () => {
    let foundUnsupported = false
    for (const fn of FUNCTIONS) {
      for (const exe of EXECUTORS) {
        if (!isFunctionSupported(fn, exe)) {
          foundUnsupported = true
          expect(unsupportedReason(fn, exe)).toBeTruthy()
        }
      }
    }
    expect(foundUnsupported).toBe(true)
  })

  it('report 路径对 PREV/AUX 不支持（静默 0 现状）', () => {
    expect(isFunctionSupported('PREV', 'report_path')).toBe(false)
    expect(isFunctionSupported('AUX', 'report_path')).toBe(false)
  })

  it('未知函数 fail-closed 判不支持', () => {
    expect(isFunctionSupported('NOPE', 'wp_evaluator' as Executor)).toBe(false)
  })

  // ── 变异反证（铁律㉒）──
  it('变异：把不支持格（PREV×report_path）当成「静默支持」应与真源冲突被打红', () => {
    // 变异态（错误）= UI 仍把 PREV 当可点、点了返 0
    const mutatedSupported = true
    const realSupported = isFunctionSupported('PREV', 'report_path')
    expect(realSupported).toBe(false) // 真源不被污染
    expect(realSupported).not.toBe(mutatedSupported) // 生产若按变异态渲染，本断言红
    // golden 也反映真源（不支持 + 有原因）
    expect(golden.matrix.PREV.report_path.supported).toBe(false)
    expect(golden.matrix.PREV.report_path.reason).toBeTruthy()
  })

  it('反向断言：支持函数（TB×wp_evaluator）不被误判为禁用', () => {
    expect(isFunctionSupported('TB', 'wp_evaluator')).toBe(true)
    expect(unsupportedReason('TB', 'wp_evaluator')).toBeNull()
  })
})
