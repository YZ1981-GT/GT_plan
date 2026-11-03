/**
 * spec excel-style-table-editing：适配层在模块求值时不读 element-plus 的组件导出。
 * 大量既有单测用 `vi.mock('element-plus', () => ({ ElMessage: … }))` 只 mock 了消息组件；
 * 适配层从 `element-plus/es` 取原组件，与 `'element-plus'` 是同一个文件、同受这份 mock 约束 ——
 * 若模块顶层就读 ElInput 等，导入链上有适配层的组件（如 GtEditableTable）在这些测试里一 import 就报
 * 「No "ElInput" export is defined on the mock」（实测合并工作表 3 个测试文件因此整文件失败）。
 */
import { describe, expect, it, vi } from 'vitest'

vi.mock('element-plus', () => ({ ElMessage: Object.assign(vi.fn(), { success: vi.fn(), warning: vi.fn(), info: vi.fn(), error: vi.fn() }) }))

describe('适配层导入不依赖 element-plus 组件导出', () => {
  it('只 mock 了 ElMessage 时，适配层与 GtEditableTable 都能导入', async () => {
    const adapters = await import('../adapters')
    expect(adapters.ElInput).toBeTruthy()
    expect(adapters.ElSelect).toBeTruthy()
    const table = await import('@/components/common/GtEditableTable.vue')
    expect(table.default).toBeTruthy()
  })
})
