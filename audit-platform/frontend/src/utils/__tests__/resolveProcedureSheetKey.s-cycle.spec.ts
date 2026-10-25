/**
 * resolveProcedureSheetKey — S 循环路由测试
 *
 * spec s-cycle-linkage-trimming-and-component-wiring §1.6（Task 17/18）
 *
 * 测试覆盖：
 * 1. S 循环专属路由（S20/S17/S15/S14/S13/S12/S10/S8/S1）
 * 2. S16/S11 显式 fallback → e1a（不被 startsWith('S1') 误捕获）
 * 3. 无专属路由的 S 码 fallback → e1a（S2/S9/S21/S32/S34 等）
 * 4. 小写 wp_code 标准化
 */
import { describe, it, expect } from 'vitest'
import { resolveProcedureSheetKey } from '../resolveProcedureSheetKey'

describe('resolveProcedureSheetKey - S 循环路由（§1.6 Task 17/18）', () => {
  // ─── 专属路由 ──────────────────────────────────────────────────────────────
  it('S20 系列底稿（S20 / S20-1）→ s20a（营业收入扣除）', () => {
    expect(resolveProcedureSheetKey('S20')).toBe('s20a')
    expect(resolveProcedureSheetKey('S20-1')).toBe('s20a')
  })

  it('S17 系列底稿（S17 / S17-1 / S17-2）→ s17a（非经常性损益）', () => {
    expect(resolveProcedureSheetKey('S17')).toBe('s17a')
    expect(resolveProcedureSheetKey('S17-1')).toBe('s17a')
    expect(resolveProcedureSheetKey('S17-2')).toBe('s17a')
  })

  it('S15 系列底稿（S15 / S15-1）→ s15a（每股收益/ROE）', () => {
    expect(resolveProcedureSheetKey('S15')).toBe('s15a')
    expect(resolveProcedureSheetKey('S15-1')).toBe('s15a')
  })

  it('S14 系列底稿（S14 / S14-1）→ s14a（会计估计）', () => {
    expect(resolveProcedureSheetKey('S14')).toBe('s14a')
    expect(resolveProcedureSheetKey('S14-1')).toBe('s14a')
  })

  it('S13 系列底稿（S13 / S13-1）→ s13a（利用管理层专家）', () => {
    expect(resolveProcedureSheetKey('S13')).toBe('s13a')
    expect(resolveProcedureSheetKey('S13-1')).toBe('s13a')
  })

  it('S12 系列底稿（S12 / S12-1）→ s12a（利用专家）', () => {
    expect(resolveProcedureSheetKey('S12')).toBe('s12a')
    expect(resolveProcedureSheetKey('S12-1')).toBe('s12a')
  })

  it('S10 系列底稿（S10 / S10-1）→ s10a（环境事项）', () => {
    expect(resolveProcedureSheetKey('S10')).toBe('s10a')
    expect(resolveProcedureSheetKey('S10-1')).toBe('s10a')
  })

  it('S8 系列底稿（S8 / S8-1）→ s8a（租赁）', () => {
    expect(resolveProcedureSheetKey('S8')).toBe('s8a')
    expect(resolveProcedureSheetKey('S8-1')).toBe('s8a')
  })

  it('S1 系列底稿（S1 / S1-1）→ s1a（违反法规行为）', () => {
    expect(resolveProcedureSheetKey('S1')).toBe('s1a')
    expect(resolveProcedureSheetKey('S1-1')).toBe('s1a')
  })

  // ─── 显式 fallback（CRITICAL：不被 startsWith('S1') 误捕获）────────────────
  it('S16 → e1a（套期活动，显式 fallback，不被 S1 前缀误匹配）', () => {
    expect(resolveProcedureSheetKey('S16')).toBe('e1a')
  })

  it('S11 系列底稿（S11 / S11-1）→ e1a（利用服务机构，显式 fallback，不被 S1 前缀误匹配）', () => {
    expect(resolveProcedureSheetKey('S11')).toBe('e1a')
    expect(resolveProcedureSheetKey('S11-1')).toBe('e1a')
  })

  // ─── 无专属路由的 S 码 → 默认 e1a ─────────────────────────────────────────
  it('S2 → e1a（无专属程序表数据源，默认 fallback）', () => {
    expect(resolveProcedureSheetKey('S2')).toBe('e1a')
  })

  it('S9 → e1a（无专属程序表数据源，默认 fallback）', () => {
    expect(resolveProcedureSheetKey('S9')).toBe('e1a')
  })

  it('S21 → e1a（无专属程序表数据源，默认 fallback）', () => {
    expect(resolveProcedureSheetKey('S21')).toBe('e1a')
  })

  it('S32/S34 → e1a（bundle 码走默认 fallback）', () => {
    expect(resolveProcedureSheetKey('S32')).toBe('e1a')
    expect(resolveProcedureSheetKey('S34')).toBe('e1a')
  })

  // ─── 小写 wp_code 标准化 ──────────────────────────────────────────────────
  it('小写 wp_code 也能正确路由（uppercase 标准化）', () => {
    expect(resolveProcedureSheetKey('s1')).toBe('s1a')
    expect(resolveProcedureSheetKey('s10')).toBe('s10a')
    expect(resolveProcedureSheetKey('s17')).toBe('s17a')
    expect(resolveProcedureSheetKey('s20')).toBe('s20a')
    expect(resolveProcedureSheetKey('s11')).toBe('e1a')
    expect(resolveProcedureSheetKey('s16')).toBe('e1a')
  })
})
