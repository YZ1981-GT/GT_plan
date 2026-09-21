/**
 * D4-33~36 其他业务收入组 A13 回写 + 双向回写 守卫（vitest）
 *
 * spec: d4-33-36-writeback-formula-and-io-closure · Requirement 5.3 / 5.4
 * 锁定行为（判行为 + 源码字面量，非纯字符串存在型）：
 *  - A13 推送用科目 6051（不得 6001）+ wpCode 字面量正确（Property 8）
 *  - 空项不 emit / 只读不 emit（Property 6/7）
 *  - 四组件源码：exportData/importData sheet 前缀正确、useD4InspectionWriteback wpCode 正确、
 *    D4-35 双向回写走 useWorkpaperSyncBridge + WorkpaperSyncEditorHost（人工触发，非 html 保存自动反写）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const emitted: Array<{ event: string; payload: any }> = []
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: (event: string, payload: any) => { emitted.push({ event, payload }) },
    on: vi.fn(),
    off: vi.fn(),
  },
}))
const msgInfo = vi.fn()
const msgSuccess = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: {
    info: (...a: any[]) => msgInfo(...a),
    success: (...a: any[]) => msgSuccess(...a),
    error: vi.fn(), warning: vi.fn(),
  },
}))

import { useD4InspectionWriteback } from '../composables/useD4InspectionWriteback'
import { D4_OTHER_ACCOUNT_CODE, D4_OTHER_ACCOUNT_NAME } from '../composables/d4OtherGroupPushPredicates'

function makeResponses() {
  return ref(new Map<string, any>())
}

describe('D4-33~36 A13 推送行为（6051 科目）', () => {
  beforeEach(() => { emitted.length = 0; msgInfo.mockClear(); msgSuccess.mockClear() })

  it('用 6051/其他业务收入 推送（不得 6001）—— Property 8', () => {
    const { pushToA13 } = useD4InspectionWriteback({ wpCode: 'D4-35', allResponses: makeResponses() })
    const fired = pushToA13(
      [{ voucherNo: 'PZ-1', amount: 12000, description: '抽凭异常', indexRef: 'wp:D4-35' }],
      D4_OTHER_ACCOUNT_CODE,
      D4_OTHER_ACCOUNT_NAME,
    )
    expect(fired).toBe(true)
    expect(emitted).toHaveLength(1)
    expect(emitted[0].payload.accountCode).toBe('6051')
    expect(emitted[0].payload.accountName).toBe('其他业务收入')
    expect(emitted[0].payload.accountCode).not.toBe('6001')
    expect(emitted[0].payload.wpCode).toBe('D4-35')
  })

  it('D4-34 差异保留符号（负差异不被 abs）', () => {
    const { pushToA13 } = useD4InspectionWriteback({ wpCode: 'D4-34', allResponses: makeResponses() })
    pushToA13(
      [{ voucherNo: '甲', amount: -2000, description: '合同测算差异（租赁）', indexRef: 'wp:D4-34' }],
      D4_OTHER_ACCOUNT_CODE, D4_OTHER_ACCOUNT_NAME,
    )
    expect(emitted[0].payload.items[0].amount).toBe(-2000) // 保留符号
  })

  it('空项不 emit（Property 6）', () => {
    const { pushToA13 } = useD4InspectionWriteback({ wpCode: 'D4-33', allResponses: makeResponses() })
    const fired = pushToA13([], D4_OTHER_ACCOUNT_CODE, D4_OTHER_ACCOUNT_NAME)
    expect(fired).toBe(false)
    expect(emitted).toHaveLength(0)
    expect(msgInfo).toHaveBeenCalled()
  })

  it('只读态不 emit（Property 7）', () => {
    const { pushToA13 } = useD4InspectionWriteback({
      wpCode: 'D4-36', allResponses: makeResponses(), isReadonly: ref(true),
    })
    const fired = pushToA13(
      [{ amount: 100, description: '跨期' }], D4_OTHER_ACCOUNT_CODE, D4_OTHER_ACCOUNT_NAME,
    )
    expect(fired).toBe(false)
    expect(emitted).toHaveLength(0)
  })
})

// ─── 连接性守卫：四组件源码字面量 ────────────────────────────────────────────
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const _dir = dirname(fileURLToPath(import.meta.url))
function readOther(rel: string): string {
  return readFileSync(resolve(_dir, '../d4/other', rel), 'utf-8')
}

describe('D4-33~36 组件连接性（字面量正确）', () => {
  const cases = [
    { file: 'D4TabOtherMargin.vue', wp: 'D4-33', sheet: 'D4-33' },
    { file: 'D4TabOtherCheck.vue', wp: 'D4-35', sheet: 'D4-35' },
  ]
  for (const c of cases) {
    it(`${c.file}: useD4InspectionWriteback wpCode = ${c.wp}`, () => {
      const src = readOther(c.file)
      expect(src).toMatch(new RegExp(`useD4InspectionWriteback\\([\\s\\S]*?wpCode:\\s*'${c.wp}'`))
    })
    it(`${c.file}: 推送用 6051 常量（D4_OTHER_ACCOUNT_CODE），不硬编码 6001`, () => {
      const src = readOther(c.file)
      expect(src).toContain('D4_OTHER_ACCOUNT_CODE')
      expect(src).not.toContain("'6001'")
    })
  }

  it('D4TabOtherContract.vue(D4-34): 两区 sheet 前缀 + wpCode D4-34', () => {
    const src = readOther('D4TabOtherContract.vue')
    expect(src).toContain("importData('D4-34-rental'")
    expect(src).toContain("importData('D4-34-consult'")
    expect(src).toMatch(/useD4InspectionWriteback\([\s\S]*?wpCode:\s*'D4-34'/)
    expect(src).not.toContain("'6001'")
  })

  it('D4TabOtherCutoff.vue(D4-36): 两区 sheet 前缀 + wpCode D4-36', () => {
    const src = readOther('D4TabOtherCutoff.vue')
    expect(src).toContain("importData('D4-36-forward'")
    expect(src).toContain("importData('D4-36-backward'")
    expect(src).toMatch(/useD4InspectionWriteback\([\s\S]*?wpCode:\s*'D4-36'/)
  })

  it('D4-35 双向回写走平台共享 composable useD4SyncMode（人工触发，非 html 保存自动反写）', () => {
    const src = readOther('D4TabOtherCheck.vue')
    // 消费平台共享 composable（entryId/capability/健康门禁/switchMode 已内聚，禁直连底层桥）
    expect(src).toContain('useD4SyncMode')
    expect(src).not.toContain('useWorkpaperSyncBridge(')
    expect(src).toContain('WorkpaperSyncEditorHost')
    // html→excel 为人工按钮触发（switchMode('在线编辑')），不存在 html 保存时自动反写 excel 的调用
    expect(src).toContain('同步到在线编辑')
    // persistAll（html 保存）里不得调用 switchMode/switchToOnlyOffice / forceSave（防自动反写）
    const persistIdx = src.indexOf('function persistAll')
    const persistBody = src.slice(persistIdx, persistIdx + 600)
    expect(persistBody).not.toContain('switchToOnlyOffice')
    expect(persistBody).not.toContain('switchD435Mode')
    expect(persistBody).not.toContain('forceSave')
  })

  it('D4-35 不再用单向只读 GtOnlyOfficeSheet（已升级为双向）', () => {
    const src = readOther('D4TabOtherCheck.vue')
    expect(src).not.toContain('GtOnlyOfficeSheet')
  })
})

// ─── 公式管理入口守卫：接入平台唯一公式体系（FormulaManagerDialog / wp_formula） ─────
// 四组件通过 open-formula-manager 事件打开平台全局公式管理中心（同 E1 范式），
// 定位到本底稿 nodeKey（wp_d4_33/34/35/36）。平台侧后端权威执行 + CAS + 审计 +
// 跨底稿 TB()/WP()/ROW() 取数联动，为"唯一一套公式"的落地入口。
describe('D4-33~36 公式管理入口（接入平台唯一公式体系）', () => {
  const cases = [
    { file: 'D4TabOtherMargin.vue', node: 'wp_d4_33' },
    { file: 'D4TabOtherContract.vue', node: 'wp_d4_34' },
    { file: 'D4TabOtherCheck.vue', node: 'wp_d4_35' },
    { file: 'D4TabOtherCutoff.vue', node: 'wp_d4_36' },
  ]
  for (const c of cases) {
    it(`${c.file}: import eventBus 且 openFormulaManager emit open-formula-manager`, () => {
      const src = readOther(c.file)
      expect(src).toContain("from '@/utils/eventBus'")
      // 判行为：openFormulaManager 函数体 emit 平台事件（非仅字符串出现）
      const fnIdx = src.indexOf('function openFormulaManager')
      expect(fnIdx, `${c.file} 缺 openFormulaManager 函数`).toBeGreaterThan(0)
      const fnBody = src.slice(fnIdx, fnIdx + 260)
      expect(fnBody).toContain("eventBus.emit('open-formula-manager'")
    })
    it(`${c.file}: nodeKey 字面量 = ${c.node}（定位本底稿，防串表）`, () => {
      const src = readOther(c.file)
      const fnIdx = src.indexOf('function openFormulaManager')
      const fnBody = src.slice(fnIdx, fnIdx + 260)
      expect(fnBody).toContain(`nodeKey: '${c.node}'`)
    })
    it(`${c.file}: 工具条有「ƒx 公式管理」按钮且 @click=openFormulaManager`, () => {
      const src = readOther(c.file)
      expect(src).toContain('ƒx 公式管理')
      expect(src).toContain('@click="openFormulaManager"')
    })
  }

  it('四组件 nodeKey 互不串表（每表唯一 wp_d4_3X）', () => {
    const nodes = cases.map(c => {
      const src = readOther(c.file)
      const m = src.match(/nodeKey:\s*'(wp_d4_3\d)'/)
      return m?.[1]
    })
    expect(new Set(nodes).size).toBe(4) // 四个各自唯一
    expect(nodes).toEqual(['wp_d4_33', 'wp_d4_34', 'wp_d4_35', 'wp_d4_36'])
  })
})
