/**
 * H5 油气资产披露载荷契约守卫（仅国企，§八、25）。
 *
 * 固化本 spec 修掉的 4 个静默 bug：
 * 1. 载荷行是自造 4 行（模板要 16 行四层）
 * 2. 列 3 vs 模板 5，且位置化 `values:[期末,期初]` 顺序与模板相反 → 期末落进期初列
 * 3. `_note_texts` 放载荷顶层被 pydantic 静默丢弃（必须在 `sub_table_data` 内）
 * 4. `syncToNote()` 内自调度 `scheduleAutoSync(syncToNote)` → 周期重复 POST 且骗过覆盖率守卫
 *
 * spec: h5-oil-gas-disclosure-alignment (Task 6)
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  H5_NOTE_SECTION,
  H5_SOE_COLUMNS,
  H5_SOE_ROW_LABELS,
  H5_SOE_SUBTABLE,
  buildH5SoeRows,
  buildH5SyncPayload,
} from '../h5NoteSectionMap'

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

function noteSoeSection() {
  const raw = JSON.parse(
    readFileSync(resolve(REPO_ROOT, 'backend/data/note_template_soe.json'), 'utf-8'),
  ) as { sections?: Array<Record<string, any>> }
  return (raw.sections ?? []).find((s) => String(s.section_number).trim() === '八、25')
}

/** 去注释后再做源码断言（守卫注释里会写反例，否则会被数成真实调用） */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

const CTX = { wpId: 'wp1', projectId: 'p1', year: 2025 }

describe('H5 §八、25 载荷 ↔ 模板契约', () => {
  it('P1 章节号与子表名逐字命中模板', () => {
    const sec = noteSoeSection()
    expect(sec, '模板缺 §八、25').toBeDefined()
    expect(H5_NOTE_SECTION.soe).toBe('八、25')
    expect((sec!.tables ?? []).map((t: any) => t.name)).toContain(H5_SOE_SUBTABLE.main)
  })

  it('P1 载荷 15 行且行标签/行序逐字等于模板', () => {
    const tbl = (noteSoeSection()!.tables as any[]).find((t) => t.name === H5_SOE_SUBTABLE.main)
    const tplLabels = (tbl.rows as any[]).map((r) => r.label)
    expect(H5_SOE_ROW_LABELS).toEqual(tplLabels)

    // 15 行 = 4 个层合计 + 11 个「其中：」类别行（累计折耗层源模板只列 2 类，非 3 类）
    const rows = buildH5SoeRows({ cost: 100, depletion: 30, impairment: 10 })
    expect(rows).toHaveLength(15)
    expect(rows.map((r) => r.label)).toEqual(tplLabels)
  })

  it('P2 行是业务键 dict，键 ⊆ columns.key，且无位置化 values', () => {
    const allowed = new Set([...H5_SOE_COLUMNS[H5_SOE_SUBTABLE.main].map((c) => c.key), 'is_total'])
    for (const r of buildH5SoeRows({ cost: 1, depletion: 1, impairment: 1 })) {
      expect(r).not.toHaveProperty('values')
      for (const k of Object.keys(r)) expect(allowed.has(k), `未知键 ${k}`).toBe(true)
    }
  })

  it('P3 列定义 5 列且 label 逐字等于模板 headers（首列 is_label + flat）', () => {
    const tbl = (noteSoeSection()!.tables as any[]).find((t) => t.name === H5_SOE_SUBTABLE.main)
    const cols = H5_SOE_COLUMNS[H5_SOE_SUBTABLE.main]
    expect(cols.map((c) => c.key)).toEqual(['label', 'begin', 'increase', 'decrease', 'end'])
    expect(cols.map((c) => c.label)).toEqual(tbl.headers)
    expect(cols[0].is_label).toBe(true)
    expect(cols[0].flat).toBe(true)
    // 金额列须标 format
    expect(cols.slice(1).every((c) => c.format === 'amount')).toBe(true)
  })

  it('P4 宁缺勿造：其中类别行与非期末列一律 null（不用 0 冒充未取数）', () => {
    const rows = buildH5SoeRows({ cost: 100, depletion: 30, impairment: 10 })
    for (const r of rows) {
      expect(r.begin).toBeNull()
      expect(r.increase).toBeNull()
      expect(r.decrease).toBeNull()
      if (!r.is_total) expect(r.end, `${r.label} 应为 null`).toBeNull()
    }
  })

  it('P5 账面价值层 = 原价 − 累计折耗 − 减值准备', () => {
    const rows = buildH5SoeRows({ cost: 100, depletion: 30, impairment: 10 })
    const pick = (label: string) => rows.find((r) => r.label === label)!
    expect(pick('一、原价合计').end).toBe(100)
    expect(pick('二、累计折耗合计').end).toBe(30)
    expect(pick('三、油气资产减值准备累计金额合计').end).toBe(10)
    expect(pick('四、油气资产账面价值合计').end).toBe(60)
  })

  it('P6 _note_texts 在 sub_table_data 内、不在顶层，且带中文 title；空文本不产生条目', () => {
    const withText = buildH5SyncPayload({
      ...CTX,
      layerTotals: { cost: 1 },
      soeDisclosureText: '本期取得矿区权益支出 XX 元。',
    })
    expect(withText).not.toHaveProperty('_note_texts')
    const texts = withText.sub_table_data._note_texts as Array<Record<string, string>>
    expect(texts).toHaveLength(1)
    expect(texts[0].title).toBe('补充披露（国资监管要求）')
    expect(/^[a-z-]+$/.test(texts[0].title)).toBe(false)

    const blank = buildH5SyncPayload({ ...CTX, layerTotals: { cost: 1 }, soeDisclosureText: '   ' })
    expect(blank.sub_table_data).not.toHaveProperty('_note_texts')
  })

  it('P6 载荷顶层字段集合符合 SyncFromWorkpaperRequest', () => {
    const p = buildH5SyncPayload({ ...CTX, layerTotals: { cost: 1 } })
    expect(Object.keys(p).sort()).toEqual(
      ['columns', 'current_standard', 'section_id', 'sheet_name', 'sub_table_data', 'wp_id', 'year'].sort(),
    )
    expect(p.current_standard).toBe('soe_standalone')
  })
})

describe('H5 组件：自动同步真接入（无自调度）', () => {
  const compPath = resolve(
    REPO_ROOT,
    'audit-platform/frontend/src/components/workpaper/h5/core/H5TabDisclosureSoe.vue',
  )
  const raw = readFileSync(compPath, 'utf-8')
  const src = stripComments(raw)

  it('反向自检：原始源码含被禁字样（确保 stripComments 未把断言变空转）', () => {
    expect(raw).toContain('scheduleAutoSync')
  })

  /** 按花括号配对精确截取函数体（不依赖后续代码布局） */
  function functionBody(source: string, signature: string): string {
    const at = source.indexOf(signature)
    if (at === -1) return ''
    const open = source.indexOf('{', at)
    let depth = 0
    for (let i = open; i < source.length; i++) {
      if (source[i] === '{') depth++
      else if (source[i] === '}') {
        depth--
        if (depth === 0) return source.slice(open, i + 1)
      }
    }
    return source.slice(open)
  }

  it('P7 syncToNote 函数体内不得调 scheduleAutoSync（自调度）', () => {
    const body = functionBody(src, 'async function syncToNote')
    expect(body, '未定位到 syncToNote 函数体').not.toBe('')
    expect(body).not.toContain('scheduleAutoSync')
  })

  it('反向自检：花括号配对截取有效（能在含该调用的函数体里检出）', () => {
    const fake = 'async function syncToNote(): Promise<void> { a(); scheduleAutoSync(x); }\nfunction z(){}'
    expect(functionBody(fake, 'async function syncToNote')).toContain('scheduleAutoSync')
  })

  it('P7 组件存在 watch 型 scheduleAutoSync（真接入实际数据）', () => {
    expect(/watch\(\s*\[[\s\S]*?\][\s\S]*?scheduleAutoSync/.test(src)).toBe(true)
    // 不得使用一次性挂载防护（会吞掉切走再切回后的第一次编辑）
    expect(/_[A-Za-z0-9]*[Mm]ounted\s*=/.test(src)).toBe(false)
  })
})
