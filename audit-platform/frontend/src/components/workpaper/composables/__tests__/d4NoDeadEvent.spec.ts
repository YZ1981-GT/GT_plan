/**
 * d4NoDeadEvent — D4 不留无接收端的 CustomEvent 守卫
 *
 * 断言：useD4CrossSheet.ts 不再含 d4:sync-row
 * Spec: d4-price-analysis-writeback-linkage Task 7
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

describe('D4 无死事件', () => {
  const crossSheetPath = path.resolve(__dirname, '../useD4CrossSheet.ts')

  it('useD4CrossSheet.ts 不含 d4:sync-row 发送', () => {
    const content = fs.readFileSync(crossSheetPath, 'utf-8')
    expect(content).not.toContain('d4:sync-row')
  })

  it('useD4CrossSheet.ts 不含 syncProductRowToAdjudication', () => {
    const content = fs.readFileSync(crossSheetPath, 'utf-8')
    expect(content).not.toContain('syncProductRowToAdjudication')
  })

  it('useD4CrossSheet.ts 不含 syncOtherItemRowToAdjudication', () => {
    const content = fs.readFileSync(crossSheetPath, 'utf-8')
    expect(content).not.toContain('syncOtherItemRowToAdjudication')
  })

  it('d4:price-abnormal 事件在 crossWpEventBridge 桥接列表中', () => {
    const bridgePath = path.resolve(__dirname, '../../../../utils/crossWpEventBridge.ts')
    const content = fs.readFileSync(bridgePath, 'utf-8')
    expect(content).toContain("'d4:price-abnormal'")
  })

  it('d4:price-abnormal 事件在 eventBus.ts Events 类型中注册', () => {
    const busPath = path.resolve(__dirname, '../../../../utils/eventBus.ts')
    const content = fs.readFileSync(busPath, 'utf-8')
    expect(content).toContain("'d4:price-abnormal'")
  })

  it('useD4PriceWriteback.ts 存在且消费 d4:price-abnormal', () => {
    const writebackPath = path.resolve(__dirname, '../useD4PriceWriteback.ts')
    const content = fs.readFileSync(writebackPath, 'utf-8')
    expect(content).toContain("eventBus.on('d4:price-abnormal'")
    expect(content).toContain("eventBus.off('d4:price-abnormal'")
  })
})
