/**
 * D4 IPO 双模式回写：**前端侧**契约判据（列规格形态 + 组件接线）。
 *
 * spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Wave 1 · Task 2
 *
 * ═══ 2026-09-19 复盘重写 ═══
 *
 * 本文件原先测的是 `ipoChecklistSchema.rowsToSheet` / `sheetToRows` —— 那两个函数在
 * 生产代码里**零调用方**（四个组件走平台桥 `useWorkpaperSyncBridge` + `readStoreProjection`，
 * projection 由**服务端现算**），且其规则与后端 provider **已经分叉**（行定位按 seq vs 按
 * UUID 行身份、checkbox 做 true→1 转换 vs 原值照抄、显式跳全空行 vs 要求 rowId）。
 * 也就是说：**测了一个不参与运行的实现** —— 这是假绿，不是守卫。两个函数已删除。
 *
 * AC 2.3/2.4 与 Property 6/7/8 的判据已迁到生产路径（真跑
 * `build_store_projection` → `merge_projection_into_rows`）：
 *   `backend/tests/workpaper_sync/test_d4_ipo_checklist_store_roundtrip.py`
 * 后端 sheet_key / json_path 与前端列 key 的跨语言对齐：
 *   `backend/tests/workpaper_sync/test_d4_ipo_checklist_cross_lang_contract.py`
 *
 * 本文件保留**前端这一侧真正该管的事**：列规格形态（两级表头子列、checkbox/派生列声明），
 * 它们是后端 provider 与导入导出列头共同的对照基准。
 */
import { describe, it, expect } from 'vitest'

import * as schema from '../ipoChecklistSchema'

const SHEET_CODES = ['D4-25', 'D4-26', 'D4-27', 'D4-28'] as const

describe('ipoChecklistSchema 列规格真源形态', () => {
  it('四张表都有 spec，且列数为实测冻结值（13/19/18/15）', () => {
    expect(schema.SHEET_SPECS).toBeTruthy()
    const expected: Record<string, number> = {
      'D4-25': 13, 'D4-26': 19, 'D4-27': 18, 'D4-28': 15,
    }
    for (const code of SHEET_CODES) {
      expect(schema.SHEET_SPECS[code], `${code} 缺 spec`).toBeTruthy()
      expect(schema.SHEET_SPECS[code].columns.length, `${code} 列数漂移`).toBe(expected[code])
    }
  })

  it('不再导出 rows↔网格投影函数（删除后禁止回归 —— 投影真源在后端 provider）', () => {
    // 🔴 这条是「删旧代码」的防回归判据：谁把 rowsToSheet/sheetToRows 加回来就红，
    //    因为它们的规则与后端 phase5_d4_ipo_checklist_sheets 已分叉，接线即引入真 bug。
    expect((schema as Record<string, unknown>).rowsToSheet).toBeUndefined()
    expect((schema as Record<string, unknown>).sheetToRows).toBeUndefined()
  })

  it('每列 key 唯一（撞 key 会让投影互相覆盖且无人知情）', () => {
    for (const code of SHEET_CODES) {
      const keys = schema.SHEET_SPECS[code].columns.map((c: { key: string }) => c.key)
      expect(new Set(keys).size, `${code} 有重复列 key`).toBe(keys.length)
    }
  })
})

describe('两级表头父组形态（Property 2/3：各恰 5 个子列）', () => {
  it('D4-26「核查程序执行情况」5 子列，且全为 checkbox', () => {
    const spec = schema.SHEET_SPECS['D4-26']
    const sub = spec.columns.filter((c: { group: string | null }) => c.group)
    expect(sub.length).toBe(5)
    expect(new Set(sub.map((c: { group: string | null }) => c.group)).size).toBe(1)
    for (const c of sub) expect(c.type).toBe('checkbox')
  })

  it('D4-28「核查方式（√）」5 子列，且全为 checkbox', () => {
    const spec = schema.SHEET_SPECS['D4-28']
    const sub = spec.columns.filter((c: { group: string | null }) => c.group)
    expect(sub.length).toBe(5)
    expect(new Set(sub.map((c: { group: string | null }) => c.group)).size).toBe(1)
    for (const c of sub) expect(c.type).toBe('checkbox')
  })
})

describe('D4-27 身份属性列与派生总计列', () => {
  it('10 个身份属性 checkbox + total 为派生列（源模板内嵌 =SUM(C15:L15)）', () => {
    const spec = schema.SHEET_SPECS['D4-27']
    const cb = spec.columns.filter((c: { type: string }) => c.type === 'checkbox')
    expect(cb.length).toBe(10)
    const total = spec.columns.find((c: { key: string }) => c.key === 'total')
    expect(total).toBeTruthy()
    expect(total!.derived).toBe(true)
  })
})

describe('派生列声明与公式真源双向锁死（Property 15 同族）', () => {
  it('DERIVED_COLUMNS 与 intra_sheet 公式的 columnKey 集合相等', () => {
    for (const code of SHEET_CODES) {
      const declared = new Set(schema.DERIVED_COLUMNS[code])
      const fromFormula = new Set(
        schema.IPO_FORMULA_PRESETS
          .filter((p) => p.sheetCode === code && p.category === 'intra_sheet')
          .map((p) => p.columnKey),
      )
      expect(declared, `${code} 派生列声明与 intra_sheet 公式不一致`).toEqual(fromFormula)
    }
  })
})
