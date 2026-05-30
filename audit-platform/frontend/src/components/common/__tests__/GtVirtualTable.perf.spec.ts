/**
 * GtVirtualTable 性能基准测试
 *
 * 验证：
 * - 冷启动渲染时间 < 50ms（500 行）
 * - 500 行表格首次渲染 < 200ms
 * - 滚动性能（模拟帧率 ≥ 60fps = 每帧 ≤ 16.67ms）
 *
 * Validates: Requirements 2.1, 2.2, 2.3
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { computed, ref } from 'vue'
import { useVirtualTable, VIRTUAL_THRESHOLD } from '@/composables/useVirtualTable'

/** 生成 N 行模拟数据 */
function generateRows(count: number): Record<string, any>[] {
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    name: `项目 ${i + 1}`,
    amount: Math.round(Math.random() * 1000000) / 100,
    date: '2025-01-01',
    status: i % 3 === 0 ? '已完成' : '进行中',
  }))
}

/** 生成列配置 */
function generateColumns() {
  return [
    { key: 'id', dataKey: 'id', title: '序号', width: 80, align: 'center' as const },
    { key: 'name', dataKey: 'name', title: '名称', width: 200 },
    { key: 'amount', dataKey: 'amount', title: '金额', width: 150, align: 'right' as const },
    { key: 'date', dataKey: 'date', title: '日期', width: 120 },
    { key: 'status', dataKey: 'status', title: '状态', width: 100 },
  ]
}

describe('GtVirtualTable 性能基准', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('冷启动渲染性能', () => {
    it('500 行数据 useVirtualTable 初始化 < 50ms', () => {
      const rows = ref(generateRows(500))
      const columns = ref(generateColumns())

      const start = performance.now()

      const result = useVirtualTable({
        rows,
        columns,
        width: 1200,
        height: 600,
      })

      // 触发 computed 求值
      const _ = result.useVirtual.value
      const __ = result.tableProps.value
      const ___ = result.rowEventHandlers.value

      const elapsed = performance.now() - start

      expect(elapsed).toBeLessThan(50)
      expect(result.useVirtual.value).toBe(false) // 500 行 = 阈值，不启用
    })

    it('501 行数据启用虚拟滚动，初始化 < 50ms', () => {
      const rows = ref(generateRows(501))
      const columns = ref(generateColumns())

      const start = performance.now()

      const result = useVirtualTable({
        rows,
        columns,
        width: 1200,
        height: 600,
      })

      const isVirtual = result.useVirtual.value
      const props = result.tableProps.value

      const elapsed = performance.now() - start

      expect(elapsed).toBeLessThan(50)
      expect(isVirtual).toBe(true) // > 500 行启用
      expect(props.data.length).toBe(501)
    })

    it('1000 行数据初始化 < 50ms', () => {
      const rows = ref(generateRows(1000))
      const columns = ref(generateColumns())

      const start = performance.now()

      const result = useVirtualTable({
        rows,
        columns,
        width: 1200,
        height: 600,
      })

      result.useVirtual.value
      result.tableProps.value
      result.rowEventHandlers.value

      const elapsed = performance.now() - start

      expect(elapsed).toBeLessThan(50)
      expect(result.useVirtual.value).toBe(true)
    })

    it('5000 行数据初始化 < 50ms', () => {
      const rows = ref(generateRows(5000))
      const columns = ref(generateColumns())

      const start = performance.now()

      const result = useVirtualTable({
        rows,
        columns,
        width: 1200,
        height: 600,
      })

      result.useVirtual.value
      result.tableProps.value

      const elapsed = performance.now() - start

      expect(elapsed).toBeLessThan(50)
    })
  })

  describe('500 行表格首次渲染性能', () => {
    it('500 行 computed 列转换 < 200ms', () => {
      const rows = ref(generateRows(500))
      const columns = ref(generateColumns())

      const start = performance.now()

      const result = useVirtualTable({
        rows,
        columns,
        width: 1200,
        height: 600,
      })

      // 模拟完整渲染流程：所有 computed 求值
      const tableProps = result.tableProps.value
      const handlers = result.rowEventHandlers.value
      const virtual = result.useVirtual.value

      // 模拟 headerCellRenderer 调用（每列一次）
      for (const col of columns.value) {
        result.headerCellRenderer({ column: col })
      }

      // 模拟 cellRenderer 调用（每行每列）
      for (let i = 0; i < Math.min(rows.value.length, 20); i++) {
        for (const col of columns.value) {
          result.cellRenderer({ cellData: rows.value[i][col.dataKey] })
        }
      }

      const elapsed = performance.now() - start

      expect(elapsed).toBeLessThan(200)
    })
  })

  describe('滚动性能（模拟）', () => {
    it('单帧滚动处理 < 16.67ms（60fps 阈值）', () => {
      const rows = ref(generateRows(2000))
      const columns = ref(generateColumns())

      const result = useVirtualTable({
        rows,
        columns,
        width: 1200,
        height: 600,
      })

      // 模拟滚动：重新计算 tableProps（虚拟滚动核心操作）
      const frameTimes: number[] = []

      for (let frame = 0; frame < 30; frame++) {
        const frameStart = performance.now()

        // 模拟滚动时的重新计算
        const props = result.tableProps.value
        const handlers = result.rowEventHandlers.value

        // 模拟可见行渲染（虚拟滚动只渲染可见区域 ~17 行）
        const visibleCount = Math.ceil(600 / 36)
        const startIdx = frame * 5 // 模拟滚动偏移
        for (let i = startIdx; i < startIdx + visibleCount && i < rows.value.length; i++) {
          for (const col of columns.value) {
            result.cellRenderer({ cellData: rows.value[i][col.dataKey] })
          }
        }

        const frameTime = performance.now() - frameStart
        frameTimes.push(frameTime)
      }

      // 每帧应 < 16.67ms（60fps）
      const maxFrameTime = Math.max(...frameTimes)
      const avgFrameTime = frameTimes.reduce((a, b) => a + b, 0) / frameTimes.length

      expect(maxFrameTime).toBeLessThan(16.67)
      expect(avgFrameTime).toBeLessThan(10) // 平均应更快
    })

    it('大数据集（10000 行）滚动帧时间 < 16.67ms', () => {
      const rows = ref(generateRows(10000))
      const columns = ref(generateColumns())

      const result = useVirtualTable({
        rows,
        columns,
        width: 1200,
        height: 600,
      })

      const frameTimes: number[] = []

      for (let frame = 0; frame < 20; frame++) {
        const frameStart = performance.now()

        result.tableProps.value
        const visibleCount = Math.ceil(600 / 36)
        const startIdx = frame * 50
        for (let i = startIdx; i < startIdx + visibleCount && i < rows.value.length; i++) {
          for (const col of columns.value) {
            result.cellRenderer({ cellData: rows.value[i][col.dataKey] })
          }
        }

        frameTimes.push(performance.now() - frameStart)
      }

      const maxFrameTime = Math.max(...frameTimes)
      expect(maxFrameTime).toBeLessThan(16.67)
    })
  })

  describe('阈值切换逻辑', () => {
    it('VIRTUAL_THRESHOLD 为 500', () => {
      expect(VIRTUAL_THRESHOLD).toBe(500)
    })

    it('≤500 行不启用虚拟滚动', () => {
      const rows = ref(generateRows(500))
      const columns = ref(generateColumns())

      const { useVirtual } = useVirtualTable({ rows, columns })
      expect(useVirtual.value).toBe(false)
    })

    it('>500 行启用虚拟滚动', () => {
      const rows = ref(generateRows(501))
      const columns = ref(generateColumns())

      const { useVirtual } = useVirtualTable({ rows, columns })
      expect(useVirtual.value).toBe(true)
    })

    it('数据动态变化时自动切换', () => {
      const rows = ref(generateRows(100))
      const columns = ref(generateColumns())

      const { useVirtual } = useVirtualTable({ rows, columns })
      expect(useVirtual.value).toBe(false)

      // 增加到 > 500
      rows.value = generateRows(600)
      expect(useVirtual.value).toBe(true)

      // 减少到 ≤ 500
      rows.value = generateRows(200)
      expect(useVirtual.value).toBe(false)
    })
  })
})
