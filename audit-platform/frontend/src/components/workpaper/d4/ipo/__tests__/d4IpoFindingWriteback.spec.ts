/**
 * D4IpoFindingWriteback — 风险发现人工认定 → A13 人工门守卫（vitest + @vue/test-utils）
 *
 * spec: d4-ipo-fraud-writeback-formula-io · Task 4/5（Requirement 3.1-3.4）
 * 锁定行为：
 *  - 发现存在但未人工认定 → 不 emit a13:push-misstatement（不自动造错报）
 *  - 金额=0 / 描述空 / 证据空 → 未认定 → 不可推送
 *  - 金额>0 + 描述 + 证据齐全 且勾选 → emit，payload wpCode/accountCode 正确
 *  - 「仅保存发现留痕」→ 派发 d4:save-items 写 {wpCode}-findings，不 emit A13
 *  - 只读态 → 不 emit、不落库
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

// ─── Mock eventBus（a13 推送落点）───────────────────────────────────────────
const emitted: Array<{ event: string; payload: any }> = []
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: (event: string, payload: any) => { emitted.push({ event, payload }) },
    on: vi.fn(), off: vi.fn(),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

import D4IpoFindingWriteback from '../D4IpoFindingWriteback.vue'

// 轻量 stub：透传 slot，v-model 支持
const STUBS = {
  'el-badge': { template: '<span><slot /></span>' },
  'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
  'el-dialog': { props: ['modelValue'], template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>' },
  'el-alert': { template: '<div><slot /></div>' },
  'el-table': { props: ['data'], template: '<div><slot /></div>' },
  'el-table-column': { template: '<div><slot :row="{}" /></div>' },
  'el-checkbox': { props: ['modelValue', 'disabled'], template: '<input type="checkbox" />' },
  'el-input': { props: ['modelValue', 'disabled'], template: '<input />' },
  'el-tag': { template: '<span><slot /></span>' },
}

function mkWrapper(props: any) {
  return mount(D4IpoFindingWriteback, {
    props: {
      wpCode: 'D4-32', accountCode: '6001', accountName: '营业收入',
      allResponses: new Map<string, any>(), isReadonly: false, findings: [],
      ...props,
    },
    global: { stubs: STUBS },
  })
}

const FINDING = { key: 'd4-32-r1', label: '主要供应商·甲：异常资金往来', indexRef: 'D4-32' }

describe('D4IpoFindingWriteback 人工门', () => {
  beforeEach(() => { emitted.length = 0 })

  it('发现存在但未人工认定 → 不可推送、不 emit（不自动造错报）', () => {
    const w = mkWrapper({ findings: [FINDING] })
    const vm: any = w.vm
    vm.openDialog()
    // 未填任何认定
    expect(vm.isConfirmed(FINDING.key)).toBe(false)
    expect(vm.pushableCount).toBe(0)
    vm.handlePush()
    expect(emitted.length).toBe(0)
  })

  it('金额=0 / 描述空 / 证据空 → 未认定', async () => {
    const w = mkWrapper({ findings: [FINDING] })
    const vm: any = w.vm
    vm.openDialog(); await nextTick()
    const c = vm.confirmations[FINDING.key]
    c.amount = 0; c.description = '虚增收入'; c.evidence = '流水X'
    expect(vm.isConfirmed(FINDING.key)).toBe(false)  // 金额=0
    c.amount = 1000; c.description = ''; c.evidence = '流水X'
    expect(vm.isConfirmed(FINDING.key)).toBe(false)  // 描述空
    c.amount = 1000; c.description = '虚增收入'; c.evidence = ''
    expect(vm.isConfirmed(FINDING.key)).toBe(false)  // 证据空
    c.amount = 1000; c.description = '虚增收入'; c.evidence = '流水X'
    expect(vm.isConfirmed(FINDING.key)).toBe(true)   // 齐全
  })

  it('金额>0+描述+证据齐全且勾选 → emit a13，payload 正确', async () => {
    const w = mkWrapper({ findings: [FINDING] })
    const vm: any = w.vm
    vm.openDialog(); await nextTick()
    const c = vm.confirmations[FINDING.key]
    c.amount = 5000; c.description = '虚增收入'; c.evidence = '银行流水D4-32-1'; c.selected = true
    expect(vm.pushableCount).toBe(1)
    vm.handlePush()
    const a13 = emitted.filter(e => e.event === 'a13:push-misstatement')
    expect(a13.length).toBe(1)
    expect(a13[0].payload.wpCode).toBe('D4-32')
    expect(a13[0].payload.accountCode).toBe('6001')
    expect(a13[0].payload.items[0].amount).toBe(5000)
    expect(a13[0].payload.items[0].description).toContain('证据：银行流水D4-32-1')
  })

  it('仅保存发现留痕 → 派发 d4:save-items 写 {wpCode}-findings，不 emit A13', () => {
    const events: any[] = []
    const handler = (e: any) => events.push(e)
    window.addEventListener('d4:save-items', handler)
    const responses = new Map<string, any>()
    const w = mkWrapper({ findings: [FINDING], allResponses: responses })
    const vm: any = w.vm
    vm.handleSaveFindings()
    window.removeEventListener('d4:save-items', handler)

    expect(emitted.filter(e => e.event === 'a13:push-misstatement').length).toBe(0)
    expect(responses.has('D4-32-findings')).toBe(true)
    const saved = JSON.parse(responses.get('D4-32-findings').remark)
    expect(saved.findings[0].key).toBe('d4-32-r1')
    expect(events.length).toBeGreaterThanOrEqual(1)
  })

  it('只读态 → 不 emit、不落库', () => {
    const responses = new Map<string, any>()
    const w = mkWrapper({ findings: [FINDING], isReadonly: true, allResponses: responses })
    const vm: any = w.vm
    // 强行构造已认定态再推
    vm.openDialog()
    vm.confirmations[FINDING.key] = { selected: true, amount: 9999, description: 'x', evidence: 'y' }
    vm.handlePush()
    expect(emitted.length).toBe(0)
    expect(responses.has('D4-32-findings')).toBe(false)
  })
})
