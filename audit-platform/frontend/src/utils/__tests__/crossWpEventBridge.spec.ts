// @vitest-environment jsdom
/**
 * 契约守卫：跨底稿事件传输桥（P0）
 *
 * 锁定行为，防止再次分裂为 window / eventBus 两套互不相通的通道：
 *  1. window 生产者 → eventBus 消费者收到，且 auditedAmount/adjudicatedAmount 双别名齐全。
 *  2. eventBus 生产者 → window 消费者收到，且双别名齐全。
 *  3. 双向不成环（每个消费者对单次发布恰好收到一次）。
 *  4. payload 归一：三金额别名互填 + wpCode/timestamp 兜底。
 *  5. 非桥接事件原样通过，不被 window 污染。
 */
import { describe, it, expect, beforeAll, afterEach } from 'vitest'
import { eventBus } from '../eventBus'
import {
  installCrossWpEventBridge,
  normalizeBridgedPayload,
  isCrossWpEventBridgeInstalled,
} from '../crossWpEventBridge'

beforeAll(() => {
  installCrossWpEventBridge()
})

describe('crossWpEventBridge — 传输通道统一', () => {
  afterEach(() => {
    eventBus.all.clear()
  })

  it('已安装（幂等）', () => {
    expect(isCrossWpEventBridgeInstalled()).toBe(true)
    // 再次安装不报错
    expect(() => installCrossWpEventBridge()).not.toThrow()
  })

  it('window 生产者 → eventBus 消费者收到，双金额别名齐全', () => {
    const received: any[] = []
    const handler = (p: any) => received.push(p)
    eventBus.on('substantive:adjudicated', handler)

    window.dispatchEvent(
      new CustomEvent('substantive:adjudicated', {
        detail: { accountCode: '1221', adjudicatedAmount: 500, wpCode: 'D2' },
      }),
    )

    eventBus.off('substantive:adjudicated', handler)
    expect(received).toHaveLength(1)
    expect(received[0].accountCode).toBe('1221')
    // 归一后 auditedAmount 由 adjudicatedAmount 补齐
    expect(received[0].auditedAmount).toBe(500)
    expect(received[0].adjudicatedAmount).toBe(500)
  })

  it('eventBus 生产者 → window 消费者收到，双金额别名齐全', () => {
    const received: any[] = []
    const handler = (e: Event) => received.push((e as CustomEvent).detail)
    window.addEventListener('substantive:adjudicated', handler)

    eventBus.emit('substantive:adjudicated', {
      accountCode: '2211',
      auditedAmount: 800,
      wpCode: 'K1',
      timestamp: 1,
    })

    window.removeEventListener('substantive:adjudicated', handler)
    expect(received).toHaveLength(1)
    expect(received[0].accountCode).toBe('2211')
    expect(received[0].auditedAmount).toBe(800)
    // 归一后 adjudicatedAmount 由 auditedAmount 补齐
    expect(received[0].adjudicatedAmount).toBe(800)
  })

  it('双向不成环：window 发布只被 eventBus 消费者收到一次', () => {
    let busCount = 0
    let winCount = 0
    const busHandler = () => (busCount += 1)
    const winHandler = () => (winCount += 1)
    eventBus.on('substantive:adjudicated', busHandler)
    window.addEventListener('substantive:adjudicated', winHandler)

    window.dispatchEvent(
      new CustomEvent('substantive:adjudicated', {
        detail: { accountCode: '1221', auditedAmount: 1 },
      }),
    )

    eventBus.off('substantive:adjudicated', busHandler)
    window.removeEventListener('substantive:adjudicated', winHandler)
    // window 生产 → 回灌 bus 一次；window 原生消费者亦一次；不再回环放大
    expect(busCount).toBe(1)
    expect(winCount).toBe(1)
  })

  it('双向不成环：eventBus 发布只被 window 消费者收到一次', () => {
    let busCount = 0
    let winCount = 0
    const busHandler = () => (busCount += 1)
    const winHandler = () => (winCount += 1)
    eventBus.on('substantive:adjudicated', busHandler)
    window.addEventListener('substantive:adjudicated', winHandler)

    eventBus.emit('substantive:adjudicated', {
      accountCode: '2211',
      auditedAmount: 2,
      wpCode: 'K1',
      timestamp: 1,
    })

    eventBus.off('substantive:adjudicated', busHandler)
    window.removeEventListener('substantive:adjudicated', winHandler)
    expect(busCount).toBe(1)
    expect(winCount).toBe(1)
  })

  it('normalizeBridgedPayload: auditedTotal 也作为金额别名', () => {
    const p = normalizeBridgedPayload('substantive:adjudicated', {
      accountCode: '6602',
      auditedTotal: 150000,
    })
    expect(p.auditedAmount).toBe(150000)
    expect(p.adjudicatedAmount).toBe(150000)
    expect(p.wpCode).toBe('')
    expect(typeof p.timestamp).toBe('number')
  })

  it('disclosure:note-text-updated 也桥接（双向）', () => {
    const busReceived: any[] = []
    eventBus.on('disclosure:note-text-updated', (p: any) => busReceived.push(p))
    window.dispatchEvent(
      new CustomEvent('disclosure:note-text-updated', {
        detail: { wpCode: 'H1', section: 'listed' },
      }),
    )
    eventBus.all.clear()
    expect(busReceived).toHaveLength(1)
    expect(busReceived[0].wpCode).toBe('H1')
    expect(typeof busReceived[0].timestamp).toBe('number')
  })

  it('confirmation:received 也桥接（eventBus → window）', () => {
    const winReceived: any[] = []
    const handler = (e: Event) => winReceived.push((e as CustomEvent).detail)
    window.addEventListener('confirmation:received', handler)
    eventBus.emit('confirmation:received', { projectId: 'p1', confirmationId: 'c1' } as any)
    window.removeEventListener('confirmation:received', handler)
    expect(winReceived).toHaveLength(1)
    expect(winReceived[0].confirmationId).toBe('c1')
  })

  it('非桥接事件不派发到 window', () => {
    let winCount = 0
    const winHandler = () => (winCount += 1)
    window.addEventListener('materiality:changed', winHandler)
    eventBus.emit('materiality:changed', { projectId: 'p1', year: 2025 })
    window.removeEventListener('materiality:changed', winHandler)
    expect(winCount).toBe(0)
  })
})
