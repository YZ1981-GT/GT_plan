/**
 * useD4InspectionWriteback — D4-13/14/15/16 双向回写守卫（vitest）
 *
 * spec: d4-inspection-writeback-formula-io · Task 7
 * 锁定行为（Requirement 4/6.3）：
 *  - 无差异项 → 不 emit，给 info 提示（AC 4.5）
 *  - 有差异项 → emit 'a13:push-misstatement'，payload wpCode/accountCode 字面量正确（防接错底稿）
 *  - appendToD41Note 追加到 item_id 'D4-1-adj-note' 并派发 d4:save-items（AC 4.6）
 *  - 只读态不 emit（AC 4.7）
 *  - 公式：D4-16 差异 = 账面 − 系统（calcChangeAmount）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// ─── Mock eventBus ───────────────────────────────────────────────────────────
const emitted: Array<{ event: string; payload: any }> = []
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: (event: string, payload: any) => { emitted.push({ event, payload }) },
    on: vi.fn(),
    off: vi.fn(),
  },
}))

// ─── Mock ElMessage ──────────────────────────────────────────────────────────
const msgInfo = vi.fn()
const msgSuccess = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: {
    info: (...a: any[]) => msgInfo(...a),
    success: (...a: any[]) => msgSuccess(...a),
    error: vi.fn(),
    warning: vi.fn(),
  },
}))

import { useD4InspectionWriteback } from '../composables/useD4InspectionWriteback'
import { calcChangeAmount } from '../composables/useD4FormulaEngine'

function makeResponses() {
  return ref(new Map<string, any>())
}

describe('useD4InspectionWriteback', () => {
  beforeEach(() => {
    emitted.length = 0
    msgInfo.mockClear()
    msgSuccess.mockClear()
  })

  it('无差异项：不 emit，给 info 提示（AC 4.5）', () => {
    const { pushToA13 } = useD4InspectionWriteback({ wpCode: 'D4-16', allResponses: makeResponses() })
    const fired = pushToA13([])
    expect(fired).toBe(false)
    expect(emitted.length).toBe(0)
    expect(msgInfo).toHaveBeenCalled()
  })

  it('有差异项：emit a13:push-misstatement，payload wpCode/accountCode 字面量正确', () => {
    const responses = makeResponses()
    const { pushToA13 } = useD4InspectionWriteback({ wpCode: 'D4-16', allResponses: responses })
    const fired = pushToA13(
      [{ amount: 2000, description: '2024-Q1：口岸差异2000', indexRef: 'IDX-1' }],
      '6001',
      '营业收入',
    )
    expect(fired).toBe(true)
    expect(emitted.length).toBe(1)
    expect(emitted[0].event).toBe('a13:push-misstatement')
    expect(emitted[0].payload.wpCode).toBe('D4-16')      // 防接错底稿
    expect(emitted[0].payload.accountCode).toBe('6001')
    expect(emitted[0].payload.source).toBe('D4-16')
    expect(emitted[0].payload.items).toHaveLength(1)
    expect(emitted[0].payload.items[0].amount).toBe(2000)
    expect(msgSuccess).toHaveBeenCalled()
  })

  it('appendToD41Note：追加到 D4-1-adj-note 并派发 d4:save-items（AC 4.6）', () => {
    const responses = makeResponses()
    const saveEvents: any[] = []
    const handler = (e: Event) => saveEvents.push((e as CustomEvent).detail)
    window.addEventListener('d4:save-items', handler)

    const { pushToA13 } = useD4InspectionWriteback({ wpCode: 'D4-15', allResponses: responses })
    pushToA13([{ amount: 500, description: '事项A 三维不一致', indexRef: 'D4-15-1' }])

    const note = responses.value.get('D4-1-adj-note')
    expect(note).toBeTruthy()
    expect(note.item_id).toBe('D4-1-adj-note')
    expect(note.remark).toContain('D4-15')          // 来源标注
    expect(note.remark).toContain('三维不一致')
    expect(saveEvents.length).toBeGreaterThanOrEqual(1)
    window.removeEventListener('d4:save-items', handler)
  })

  it('append 是累加不是覆盖（已有说明保留）', () => {
    const responses = makeResponses()
    responses.value.set('D4-1-adj-note', { item_id: 'D4-1-adj-note', conclusion: null, remark: '原有说明' })
    const { pushToA13 } = useD4InspectionWriteback({ wpCode: 'D4-14', allResponses: responses })
    pushToA13([{ amount: 999, description: '异常事项X' }])
    const note = responses.value.get('D4-1-adj-note')
    expect(note.remark).toContain('原有说明')
    expect(note.remark).toContain('D4-14')
    expect(note.remark).toContain('异常事项X')
  })

  it('只读态：不 emit（AC 4.7）', () => {
    const { pushToA13 } = useD4InspectionWriteback({
      wpCode: 'D4-13',
      allResponses: makeResponses(),
      isReadonly: ref(true),
    })
    const fired = pushToA13([{ amount: 100, description: '差异' }])
    expect(fired).toBe(false)
    expect(emitted.length).toBe(0)
  })

  it('公式：D4-16 差异 = 账面 − 系统（calcChangeAmount）', () => {
    expect(calcChangeAmount(100000, 98000)).toBe(2000)
    expect(calcChangeAmount(50000, 50000)).toBe(0)
    expect(calcChangeAmount(48000, 50000)).toBe(-2000)
  })
})

// ─── 连接性守卫：组件源码字面量（防调错 sheet / 接错底稿，AC 6.5）─────────────
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const _dir = dirname(fileURLToPath(import.meta.url))
function readComp(rel: string): string {
  return readFileSync(resolve(_dir, '../d4/inspection', rel), 'utf-8')
}

describe('D4 检查表导入导出/回写 连接性（字面量正确）', () => {
  const cases = [
    { file: 'D4TabErpCheck.vue', sheet: 'D4-13' },
    { file: 'D4TabCompleteness.vue', sheet: 'D4-15' },
    { file: 'D4TabExport.vue', sheet: 'D4-16' },
  ]
  for (const c of cases) {
    it(`${c.file}: exportData/importData 指向 ${c.sheet}（防调错 sheet 前缀）`, () => {
      const src = readComp(c.file)
      expect(src).toContain(`exportData('${c.sheet}')`)
      expect(src).toContain(`importData('${c.sheet}'`)
    })
    it(`${c.file}: useD4InspectionWriteback wpCode = ${c.sheet}（防接错底稿）`, () => {
      const src = readComp(c.file)
      expect(src).toMatch(new RegExp(`useD4InspectionWriteback\\([\\s\\S]*?wpCode:\\s*'${c.sheet}'`))
    })
  }

  it('D4TabOccurrence.vue(D4-14): 回写 wpCode = D4-14', () => {
    const src = readComp('D4TabOccurrence.vue')
    expect(src).toMatch(/useD4InspectionWriteback\([\s\S]*?wpCode:\s*'D4-14'/)
  })
})
