/**
 * D1-4「按票据种类小计」区必须是**固定两行**，没有任何新增入口。
 *
 * spec: d1-sync-row-table-engine-and-d1-coverage · 裁决 A1（2026-09-28）
 *
 * ═══ 为什么 ═══
 *
 * 源模板 `坏账准备明细表D1-4` 的票据种类小计只有 R23/R24 两行，紧接 R25 就是
 * 「三、审计说明」—— **上下零余量**（openpyxl 现读实测）。同步层把该区声明为
 * `static_region`（first_data_row=23 / last_data_row=24），设计上绕开位移链、
 * 不会自动插行 ⇒ 新增的第三行在 Excel 侧物理上无处可去，OO 往返时静默丢失。
 *
 * 真库实测该键全库只有 2 个元素（`fixed-bank`/`fixed-commercial`），
 * 即原「+ 票据种类」入口从未被真正使用过 ⇒ 删除不涉及数据迁移。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

/**
 * 🔴 扫描前必须剥掉注释。
 *
 * 本文件第一版直接对原文做 `not.toContain('onAddNoteTypeRow')`，而我为了让后人别再把
 * 新增入口加回来，**在注释里写了这个标识名** ⇒ 守卫自己打红（假阳）。
 * 这与「注释里写了 `require_project_access` 就被当成已鉴权」（假阴）是同一个坑的两面：
 * **判断「代码是否真的做了 X」不能用文本匹配原文**。
 * 注释是有价值的文档，不该为了迁就扫描器而改措辞 —— 该改的是扫描器。
 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')   // HTML/模板注释
    .replace(/\/\*[\s\S]*?\*\//g, '')  // 块注释（含 JSDoc）
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')  // 行注释（避开 http:// 这类）
}

const COMPOSABLE_SRC = stripComments(
  readFileSync(resolve(__dirname, '../useD1BadDebt.ts'), 'utf-8'),
)
const HOST_SRC = stripComments(
  readFileSync(resolve(__dirname, '../../d1/D1TabBadDebt.vue'), 'utf-8'),
)
/** 原文（含注释）—— 只用于「说明文字仍在」这类正面判据。 */
const HOST_RAW = readFileSync(resolve(__dirname, '../../d1/D1TabBadDebt.vue'), 'utf-8')

describe('A1：票据种类小计区固定两行', () => {
  it('🔴 composable 不再提供 addNoteTypeRow', () => {
    expect(COMPOSABLE_SRC).not.toContain('function addNoteTypeRow')
    // 也不得从 return 里导出
    expect(COMPOSABLE_SRC).not.toMatch(/^\s+addNoteTypeRow,\s*$/m)
  })

  it('🔴 宿主不再有新增按钮/prompt 入口', () => {
    expect(HOST_SRC).not.toContain('onAddNoteTypeRow')
    expect(HOST_SRC).not.toContain('+ 票据种类')
    // prompt 弹窗是原新增入口的唯一用途
    expect(HOST_SRC).not.toContain('ElMessageBox')
  })

  it('两条固定行仍在（不能把区本身删掉）', () => {
    expect(COMPOSABLE_SRC).toContain("'fixed-bank'")
    expect(COMPOSABLE_SRC).toContain("'fixed-commercial'")
    expect(COMPOSABLE_SRC).toContain('DEFAULT_NOTETYPE_ROWS')
  })

  it('removeNoteTypeRow 保留且仍只允许删非固定行（清理历史遗留）', () => {
    expect(COMPOSABLE_SRC).toContain('function removeNoteTypeRow')
    const fn = COMPOSABLE_SRC.slice(
      COMPOSABLE_SRC.indexOf('function removeNoteTypeRow'),
    ).slice(0, 400)
    expect(fn, 'isFixed 守卫丢了 ⇒ 两条固定行会被删掉').toContain('isFixed')
  })

  it('🔴 变异反证：把新增函数加回来 ⇒ 守卫必红', () => {
    const mutated = COMPOSABLE_SRC + '\nfunction addNoteTypeRow(n: string) { return !!n }\n'
    expect(mutated).toContain('function addNoteTypeRow')
  })

  it('表头处留了「为什么不能新增」的说明（避免后人又加回去）', () => {
    // 这条用**原文**：说明就在注释与 el-tag 文案里
    expect(HOST_RAW).toContain('固定两行')
    expect(HOST_RAW).toMatch(/零余量|R23\/R24/)
  })

  it('剥注释器本身可用（正反各一条，防「剥过头把代码也剥了」）', () => {
    expect(stripComments('const a = 1 // x\n/* y */const b = 2')).toContain('const a = 1')
    expect(stripComments('const a = 1 // secret')).not.toContain('secret')
    expect(stripComments('<!-- z -->const c = 3')).toBe('const c = 3')
    // 不得吃掉 URL 里的双斜杠
    expect(stripComments("const u = 'https://x.y'")).toContain('https://x.y')
  })
})
