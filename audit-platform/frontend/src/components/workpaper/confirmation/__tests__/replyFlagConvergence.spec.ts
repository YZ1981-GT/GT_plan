/**
 * 「是否收到回函」三态收敛（spec attachment-confirmation-evidence-loop 需求 1.6，浏览器走查实测）
 *
 * 明细面板写 '是' / '否'（完整表格视图写布尔）。'否' 是真值：裸判 `row.is_replied` 把「明确未回函」当成已回函 ——
 * 同步到函证中心推成「已回函」（函证证据声明随之误判已回函）、列表「回函」列显示「是」、看板 / 覆盖率 / 舞弊信号
 * 多算回函、差异调节表把它带进来；H0 / G0 的「从 X0-1 带入替代程序」只认布尔 false，填「否」的行永远带不进来。
 */
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import ElementPlus from 'element-plus'
import ConfirmationMaster from '../ConfirmationMaster.vue'
import { rowToHubStatus } from '../coordination/syncHubFromSummary'
import { emitConfirmationCompletedFromSummary, isConfirmationInFlight } from '../coordination/emitConfirmationCompleted'
import { useD01DiffImport } from '../diffReconcile/composables/useD01DiffImport'
import { FRONTEND_SRC, readSource, stripJsComments, toSrcRelative, walkSourceFiles } from '@/__tests__/_helpers/frontendSourceScan'
import { eventBus } from '@/utils/eventBus'

vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))

describe('回函三态', () => {
  it('同步到函证中心：「否」不推成已回函，「是」才推', () => {
    expect(rowToHubStatus({ entity_name: '乙', is_replied: '否', send_date: '2026-01-05' } as any)).toBe('sent')
    expect(rowToHubStatus({ entity_name: '乙', is_replied: '否' } as any)).toBe('pending')
    expect(rowToHubStatus({ entity_name: '乙', is_replied: '是' } as any)).toBe('returned')
    expect(rowToHubStatus({ entity_name: '乙', is_replied: true } as any)).toBe('returned')
  })

  it('已进入函证程序：填了是 / 否都算（含布尔 false），未填不算', () => {
    expect(isConfirmationInFlight({ is_replied: '否' })).toBe(true)
    expect(isConfirmationInFlight({ is_replied: false })).toBe(true)
    expect(isConfirmationInFlight({})).toBe(false)
  })

  it('函证完成事件的已回函笔数不把「否」算进去', () => {
    const seen: any[] = []
    const off = (e: any) => seen.push(e)
    eventBus.on('confirmation:completed', off)
    emitConfirmationCompletedFromSummary({
      rows: [
        { entity_name: '甲', is_replied: '是' }, { entity_name: '乙', is_replied: '否' }, { entity_name: '丙', send_date: '2026-01-05' },
      ],
    })
    eventBus.off('confirmation:completed', off)
    const summary = seen.find((e) => e.customerName === '__summary__')
    expect([summary.sentCount, summary.receivedCount]).toEqual([3, 1])
  })

  it('差异调节表「从 D0-1 带入」不带「否」的行', () => {
    const { mapD01Row } = useD01DiffImport({ existingIndexes: () => new Set(), onImport: vi.fn() })
    expect(mapD01Row({ confirm_index: 'C1', amount: 100, reply_amount: 80, is_replied: '否' } as any)).toBeNull()
    expect(mapD01Row({ confirm_index: 'C1', amount: 100, reply_amount: 80, is_replied: '是' } as any)).not.toBeNull()
  })

  it('列表「回函」列：是 / 否 / 未填三态', async () => {
    const rows = [{ _row_id: 'a', is_replied: '否' }, { _row_id: 'b', is_replied: '是' }, { _row_id: 'c', is_replied: true }, { _row_id: 'd' }]
    const w = mount(ConfirmationMaster, { props: { rows, readonly: true, selectedIds: [] }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(w.findAll('[data-testid=reply-flag]').map((n) => n.text())).toEqual(['否', '是', '是', '—'])
  })
})

/** 读 is_replied 的地方都要走 replyStatus 归一谓词：只许写（`x.is_replied = …`），不许直接读 */
const BARE_READ = /\.is_replied\b(?!\s*=[^=])/

describe('全仓不再裸读 is_replied', () => {
  it('扫描器认得出裸读（自检）', () => {
    expect(BARE_READ.test('rows.filter(r => r.is_replied)')).toBe(true)
    expect(BARE_READ.test("r.is_replied === false")).toBe(true)
    expect(BARE_READ.test('patch.is_replied = true')).toBe(false)
  })

  it('除 replyStatus 自身外，前端源码没有裸读 is_replied', () => {
    const hits: string[] = []
    let scanned = 0
    for (const abs of walkSourceFiles(FRONTEND_SRC)) {
      if (!/\.(vue|ts)$/.test(abs) || /\.(spec|test)\.ts$/.test(abs) || abs.endsWith('replyStatus.ts')) continue
      scanned++
      const text = stripJsComments(readSource(abs)).replace(/<!--[\s\S]*?-->/g, '')
      text.split('\n').forEach((line, i) => { if (BARE_READ.test(line)) hits.push(`${toSrcRelative(abs)}:${i + 1}`) })
    }
    expect(scanned).toBeGreaterThan(1000)
    expect(hits, `请改用 confirmation/replyStatus 的归一谓词：\n${hits.join('\n')}`).toEqual([])
  })

  it('后端三份「从 X0-1 带入」与前端用同一词表', () => {
    const ts = readFileSync(resolve(__dirname, '../replyStatus.ts'), 'utf-8')
    const py = readFileSync(resolve(__dirname, '../../../../../../../backend/app/services/confirmation_reply_flag.py'), 'utf-8')
    const tokens = (src: string, name: string) => {
      const m = new RegExp(`${name}\\s*=\\s*(?:new Set\\(\\[|frozenset\\(\\{)([^\\]}]*)`).exec(src)
      return [...(m?.[1] ?? '').matchAll(/['"]([^'"]+)['"]/g)].map((x) => x[1]).sort()
    }
    expect(tokens(py, 'TRUE_TOKENS')).toEqual(tokens(ts, 'TRUE_TOKENS'))
    expect(tokens(py, 'FALSE_TOKENS')).toEqual(tokens(ts, 'FALSE_TOKENS'))
    expect(tokens(ts, 'TRUE_TOKENS').length).toBeGreaterThan(5)
  })
})
