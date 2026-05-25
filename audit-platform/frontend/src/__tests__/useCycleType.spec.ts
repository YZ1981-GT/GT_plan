/**
 * useCycleType — 单元测试
 *
 * 锚定 spec workpaper-editor-refactor Phase 2 拆分前置工具
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useCycleType } from '@/composables/useCycleType'

function makeRef(wpCode: string | null) {
  return ref({ wp_code: wpCode })
}

describe('useCycleType', () => {
  it('① null wpDetail → 所有 cycle flag = false', () => {
    const { isDCycle, isFCycle, isGCycle, code } = useCycleType(ref(null))
    expect(code.value).toBe('')
    expect(isDCycle.value).toBe(false)
    expect(isFCycle.value).toBe(false)
    expect(isGCycle.value).toBe(false)
  })

  it('② D2 应收账款 → isDCycle=true, 其他 false', () => {
    const r = makeRef('D2')
    const flags = useCycleType(r)
    expect(flags.isDCycle.value).toBe(true)
    expect(flags.isFCycle.value).toBe(false)
    expect(flags.isGCycle.value).toBe(false)
  })

  it('③ D2-1 子表 → isDCycle=true', () => {
    const flags = useCycleType(makeRef('D2-1'))
    expect(flags.isDCycle.value).toBe(true)
  })

  it('④ F2 存货 → isFCycle=true', () => {
    const flags = useCycleType(makeRef('F2'))
    expect(flags.isFCycle.value).toBe(true)
    expect(flags.isDCycle.value).toBe(false)
  })

  it('⑤ H1 固定资产 → isHCycle=true', () => {
    const flags = useCycleType(makeRef('H1'))
    expect(flags.isHCycle.value).toBe(true)
  })

  it('⑥ G14 衍生工具 → isGCycle=true', () => {
    const flags = useCycleType(makeRef('G14'))
    expect(flags.isGCycle.value).toBe(true)
  })

  it('⑦ 小写 d2 → 自动大写归一 → isDCycle=true', () => {
    const flags = useCycleType(makeRef('d2'))
    expect(flags.code.value).toBe('D2')
    expect(flags.isDCycle.value).toBe(true)
  })

  it('⑧ B23-2 控制了解 → isBCycle=true', () => {
    const flags = useCycleType(makeRef('B23-2'))
    expect(flags.isBCycle.value).toBe(true)
    expect(flags.isCCycle.value).toBe(false)
  })

  it('⑨ C3 控制测试 → isCCycle=true', () => {
    const flags = useCycleType(makeRef('C3'))
    expect(flags.isCCycle.value).toBe(true)
    expect(flags.isBCycle.value).toBe(false)
  })

  it('⑩ I1-10 无形摊销 → isICycle=true', () => {
    const flags = useCycleType(makeRef('I1-10'))
    expect(flags.isICycle.value).toBe(true)
  })

  it('⑪ K8 管理费用 → isKCycle=true', () => {
    const flags = useCycleType(makeRef('K8'))
    expect(flags.isKCycle.value).toBe(true)
  })

  it('⑫ L3 短期借款 → isLCycle=true', () => {
    const flags = useCycleType(makeRef('L3'))
    expect(flags.isLCycle.value).toBe(true)
  })

  it('⑬ M6 权益变动 → isMCycle=true', () => {
    const flags = useCycleType(makeRef('M6'))
    expect(flags.isMCycle.value).toBe(true)
  })

  it('⑭ N5 所得税 → isNCycle=true', () => {
    const flags = useCycleType(makeRef('N5'))
    expect(flags.isNCycle.value).toBe(true)
  })

  it('⑮ E1 货币资金 → 所有 isXCycle 都 false（E 不属于本表识别范围）', () => {
    const flags = useCycleType(makeRef('E1'))
    expect(flags.isDCycle.value).toBe(false)
    expect(flags.isFCycle.value).toBe(false)
    expect(flags.isGCycle.value).toBe(false)
    expect(flags.isHCycle.value).toBe(false)
    expect(flags.isICycle.value).toBe(false)
  })

  it('⑯ wp_code 变化时 reactivity 工作', () => {
    const r = makeRef('D2')
    const flags = useCycleType(r)
    expect(flags.isDCycle.value).toBe(true)
    r.value = { wp_code: 'F2' }
    expect(flags.isDCycle.value).toBe(false)
    expect(flags.isFCycle.value).toBe(true)
  })
})
