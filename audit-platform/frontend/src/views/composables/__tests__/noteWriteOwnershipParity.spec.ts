/**
 * 附注写入归属前后端对拍（spec formula-writer-ownership-and-stale design §13.6，D1 2026-11-04 拍板）。
 *
 * D1：已接「从底稿拉取 / 离屏同步」的章节由后端取数链路唯一写入。后端判定在 `note_write_ownership.WriteGate`，
 * 矩阵 `backend/data/note_write_ownership_matrix.json` 由 `gen_note_write_ownership_matrix.py` 生成；前端离屏同步的
 * 「从未由底稿同步、已有人工填写不覆盖」与后端 manual 策略必须是同一判据，否则 Tab 自动同步与离屏同步对同一章节结论不同。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { MANUAL_TAKEOVER_ADVICE, MANUAL_TAKEOVER_REASON } from '@/utils/noteWriteOwnership'
import { headlessDisclosureWpCodes, manualSkipMessage } from '../noteHeadlessDisclosure'

const BACKEND_DATA = resolve(__dirname, '../../../../../../backend/data')
const BACKEND_GATE = resolve(__dirname, '../../../../../../backend/app/services/note_write_ownership.py')

interface MatrixEntry { table_key: string; field_key: string; owner: string; scope: string }
interface Matrix {
  identity: Record<string, string>
  manual_policy: {
    writer: string
    rule: string
    cases: Array<{ synced_before: boolean; manual_values: number; blocked: boolean }>
  }
  chapters: Array<{ template_type: string; note_section: string; wp_codes: string[]; entries: MatrixEntry[] }>
}

type RegistryEntry = { wp_code: string } & Record<string, unknown>

function matrix(): Matrix {
  return JSON.parse(readFileSync(resolve(BACKEND_DATA, 'note_write_ownership_matrix.json'), 'utf-8')) as Matrix
}

function registry(): RegistryEntry[] {
  const doc = JSON.parse(readFileSync(resolve(BACKEND_DATA, 'note_workpaper_sync_registry.json'), 'utf-8'))
  return (doc.entries || []) as RegistryEntry[]
}

/** 与后端 `note_readiness_service.registry_sections` 同口径：主章节在前，`{准则}_sections` 的值随后，去重。 */
function registrySections(entry: RegistryEntry, variant: 'listed' | 'soe'): string[] {
  const out: string[] = []
  const primary = entry[variant]
  if (typeof primary === 'string' && primary.trim()) out.push(primary.trim())
  const nested = entry[`${variant}_sections`]
  if (nested && typeof nested === 'object') {
    for (const value of Object.values(nested as Record<string, unknown>)) {
      if (typeof value === 'string' && value.trim()) out.push(value.trim())
    }
  }
  return [...new Set(out)]
}

describe('附注写入归属前后端对拍', () => {
  it('manual 策略：前端离屏同步判据对后端算出的每条用例结论一致（同一组输入 synced_before / manual_values）', () => {
    const { manual_policy: policy } = matrix()
    expect(policy.writer).toBe('workpaper_sync')
    expect(policy.cases.some((c) => c.blocked)).toBe(true)
    expect(policy.cases.some((c) => !c.blocked)).toBe(true)
    for (const c of policy.cases) {
      const message = manualSkipMessage('八、5', { exists: true, synced_before: c.synced_before, manual_values: c.manual_values })
      expect(message !== null, JSON.stringify(c)).toBe(c.blocked)
    }
  })

  it('离屏 provider 的底稿编码集合 = 矩阵各章 wp_codes 的并集（前端接入的底稿都在交接域，交接域的底稿都已接入）', () => {
    const fromMatrix = [...new Set(matrix().chapters.flatMap((c) => c.wp_codes))].sort()
    expect(fromMatrix.length).toBe(78)
    expect([...new Set(headlessDisclosureWpCodes())].sort()).toEqual(fromMatrix)
  })

  it('矩阵治理域 = 登记表各准则章节；每章底稿披露容器归底稿披露同步、模板容器归模板绑定取数', () => {
    const expected = new Set<string>()
    for (const entry of registry()) {
      for (const variant of ['listed', 'soe'] as const) {
        for (const section of registrySections(entry, variant)) expected.add(`${variant}|${section}`)
      }
    }
    const chapters = matrix().chapters
    expect(new Set(chapters.map((c) => `${c.template_type}|${c.note_section}`))).toEqual(expected)
    for (const chapter of chapters) {
      const base = chapter.entries.filter((e) => e.table_key === '*')
      expect(base, `${chapter.template_type} ${chapter.note_section}`).toEqual([
        { table_key: '*', field_key: 'table.sub_table_data', owner: 'workpaper_sync', scope: 'cells' },
        { table_key: '*', field_key: 'table.rows.values', owner: 'binding_refill', scope: 'cells' },
      ])
      for (const e of chapter.entries.filter((x) => x.table_key !== '*')) {
        expect([e.owner, e.scope, e.field_key.startsWith('table.cell:')]).toEqual(['formula_push', 'pushed_cells', true])
      }
    }
  })

  it('HTML 入口与底稿披露同步是同一写方（身份登记）', () => {
    expect(matrix().identity.workpaper_html_sync).toBe('workpaper_sync')
  })

  it('manual 策略的原因代码与处理建议前后端同一句；离屏同步提示带上这句建议', () => {
    const source = readFileSync(BACKEND_GATE, 'utf-8')
    expect(source.match(/^MANUAL_TAKEOVER_ADVICE = "([^"]+)"$/m)?.[1]).toBe(MANUAL_TAKEOVER_ADVICE)
    expect(source).toContain(`if code == "${MANUAL_TAKEOVER_REASON}":`)
    expect(matrix().manual_policy.rule).toBe('never_synced_with_manual_values')
    const message = manualSkipMessage('八、5', { exists: true, synced_before: false, manual_values: 2 })
    expect(message).toContain(MANUAL_TAKEOVER_ADVICE)
    expect(message).not.toContain('底稿附注披露页同步')
  })
})
