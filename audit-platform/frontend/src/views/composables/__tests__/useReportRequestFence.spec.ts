import { afterEach, describe, expect, it } from 'vitest'
import { effectScope, ref, type EffectScope } from 'vue'
import { useReportRequestFence } from '../useReportRequestFence'

const scopes: EffectScope[] = []
afterEach(() => { scopes.splice(0).forEach(scope => { scope.stop() }) })
function createFence() {
  const context = ref('A')
  let invalidations = 0
  const scope = effectScope()
  scopes.push(scope)
  const fence = scope.run(() => useReportRequestFence(() => [context.value], () => { invalidations++ }))!
  return { ...fence, context, scope, invalidations: () => invalidations }
}

describe('报表请求围栏', () => {
  it('同步观察 A→B→A，即使未过 nextTick 也拒绝旧票据', () => {
    const fence = createFence()
    const old = fence.begin('rows')
    fence.context.value = 'B'
    fence.context.value = 'A'
    expect(old.isCurrent()).toBe(false)
    expect(fence.invalidations()).toBe(2)
    expect(fence.begin('rows').isCurrent()).toBe(true)
  })
  it('同 lane 只保留最后一次，其他 lane 不互相作废', () => {
    const fence = createFence()
    const first = fence.begin('rows')
    const manual = fence.begin('manual')
    const second = fence.begin('rows')
    expect(first.isCurrent()).toBe(false)
    expect(second.isCurrent()).toBe(true)
    expect(manual.isCurrent()).toBe(true)
  })
  it('scope 销毁后全部请求失效，不能重新取得有效票据', () => {
    const fence = createFence()
    const request = fence.begin()
    fence.scope.stop()
    expect(request.isCurrent()).toBe(false)
    expect(fence.begin().isCurrent()).toBe(false)
    expect(fence.invalidations()).toBe(1)
  })
})
