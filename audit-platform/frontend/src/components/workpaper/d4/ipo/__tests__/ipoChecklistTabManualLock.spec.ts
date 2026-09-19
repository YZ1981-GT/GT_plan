/**
 * useIpoChecklistTab 派生列手填锁的生命周期判据。
 *
 * spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Task 8/10-13
 * Property 15（完整语义）：派生列手填 → 锁定不重算；**清空手填 → 解锁回落预设重算**。
 *
 * 🔴 抓的是真实缺陷：原 updateCell 只 `manualLocks.add` 从不 `delete`，用户把派生列
 *    手填后再清空，锁永久留着 → 该列即使依赖列变化也不再自动重算（Property 15 后半句
 *    「清空手填即解锁回落预设重算」/ design「派生列手填锁定」小节从未落地）。
 *    本判据在「清空后再改依赖列」时断言派生列恢复自动值——只 add 不 delete 必红。
 */
import { describe, it, expect } from 'vitest'
import { defineComponent, ref, nextTick, type Ref } from 'vue'
import { mount } from '@vue/test-utils'

import { useIpoChecklistTab } from '../useIpoChecklistTab'

/** 把 composable 挂进一个最小宿主，拿到其返回值（composable 用到 onBeforeUnmount/inject）。 */
function setupTab(sheetCode: 'D4-25' | 'D4-26' | 'D4-27' | 'D4-28') {
  const allResponses: Ref<Map<string, any>> = ref(new Map<string, any>())
  let api!: ReturnType<typeof useIpoChecklistTab>
  const Host = defineComponent({
    setup() {
      api = useIpoChecklistTab({
        sheetCode,
        wpId: ref('wp1'),
        projectId: ref('p1'),
        allResponses,
        isReadonly: ref(false),
      })
      return () => null
    },
  })
  const wrapper = mount(Host)
  return { api, wrapper, allResponses }
}

describe('useIpoChecklistTab — 派生列手填锁生命周期（Property 15 完整语义）', () => {
  it('D4-25 占比列：手填锁定 → 清空解锁 → 改依赖列后恢复自动重算', async () => {
    const { api, wrapper } = setupTab('D4-25')
    // 直接注入两行（绕过 addRow 的 prompt），rowId/seq 齐全。
    api.rows.value = [
      { rowId: 'r1', seq: 1, salesAmount: 300 } as any,
      { rowId: 'r2', seq: 2, salesAmount: 700 } as any,
    ]

    // 触发一次重算基线：r1 占比 = 300/1000 = 0.3
    api.updateCell('r1', 'salesAmount', 300)
    expect(api.rows.value[0].proportion).toBeCloseTo(0.3, 4)

    // ① 手填派生列 proportion → 锁定，不被重算覆盖
    api.updateCell('r1', 'proportion', 0.99)
    expect(api.rows.value[0].proportion).toBe(0.99)
    // 改依赖列，锁定项仍不动
    api.updateCell('r1', 'salesAmount', 100)
    expect(api.rows.value[0].proportion).toBe(0.99)

    // ② 清空手填 → 解锁；此刻应立即回落自动值（100 / (100+700) = 0.125）
    api.updateCell('r1', 'proportion', null)
    expect(api.rows.value[0].proportion).toBeCloseTo(0.125, 4)

    // ③ 解锁后再改依赖列 → 派生列继续自动重算（若锁没删，这里会停在旧值）
    api.updateCell('r1', 'salesAmount', 300)
    expect(api.rows.value[0].proportion).toBeCloseTo(0.3, 4)

    wrapper.unmount()
  })

  it('空字符串也算清空（解锁）', async () => {
    const { api, wrapper } = setupTab('D4-25')
    api.rows.value = [
      { rowId: 'r1', seq: 1, salesAmount: 400 } as any,
      { rowId: 'r2', seq: 2, salesAmount: 600 } as any,
    ]
    api.updateCell('r1', 'proportion', 0.5) // 锁定
    expect(api.rows.value[0].proportion).toBe(0.5)
    api.updateCell('r1', 'proportion', '   ') // 空白串 → 解锁
    // 解锁后回落自动值 400/1000 = 0.4
    expect(api.rows.value[0].proportion).toBeCloseTo(0.4, 4)
    wrapper.unmount()
  })

  it('删除行清掉其遗留手填锁（不残留僵尸键）', async () => {
    const { api, wrapper } = setupTab('D4-25')
    api.rows.value = [
      { rowId: 'r1', seq: 1, salesAmount: 300 } as any,
      { rowId: 'r2', seq: 2, salesAmount: 700 } as any,
    ]
    api.updateCell('r1', 'proportion', 0.99) // 锁定 r1:proportion
    api.removeRow('r1')
    // r2 变成唯一行，占比应为 1（700/700）；若 r1 锁残留不影响 r2，这里只验删行本身正常
    expect(api.rows.value).toHaveLength(1)
    expect(api.rows.value[0].rowId).toBe('r2')
    expect(api.rows.value[0].proportion).toBeCloseTo(1, 4)
    wrapper.unmount()
  })
})
