/**
 * Property-Based Test — P23: TabIndex Code ⊆ ACNR Catalog（Task 25.4）
 *
 * Property 23（design Expansion 3）：
 *   *For any* migrated bundle `TabIndex`，其目录中每个 `sheet_code` 应存在于该循环
 *   ACNR catalog（subset 关系），使目录编码不会与 catalog 漂移；catalog 不可用时降级
 *   仍渲染完整硬编码行集（不出现空白目录）。
 *
 * 前端行为层验证（displayRows 合并逻辑，见 design §15）：
 *   - 名称从 catalog 取：命中 catalog 的 code → 显示名/ addr_id 来自 catalog（Req 18.1）
 *   - 未命中 catalog 的 code → 回退硬编码名（Req 18.7）
 *   - catalog 为空 → 全部行回退硬编码，且行数不变（无空白目录，Req 18.7）
 *   - code 集合恒为本地硬编码集（catalog 只覆盖名称，不改路由/编码/适用性，Req 18.2/18.5）
 *   - 采用 catalog 名称的 code 子集 ⊆ catalog keys（subset 不变式，Req 18.4 的运行时对应面）
 *
 * 通过 mock `useAcnrCatalogIndex` 控制 catalog map，挂载 D2TabIndex/D4TabIndex 试点组件，
 * 读取 `displayRows` 合并结果断言。
 *
 * Validates: Requirements 18.1, 18.4, 18.7
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import * as fc from 'fast-check'

// ─── 共享 catalog 持有器：mock 返回的 catalogIndex 从这里读 ───
// 用 vi.hoisted 保证在 vi.mock 工厂内可用；holder.value 为 Map，测试内按迭代替换。
const { holder } = vi.hoisted(() => ({
  holder: { value: new Map<string, { sheet_name: string; addr_id: string; order: number }>() },
}))

vi.mock('@/components/workpaper/composables/useAcnrCatalogIndex', () => ({
  useAcnrCatalogIndex: () => ({
    loading: { value: false },
    // 组件里以 catalogIndex.value.get(code) 读取；重挂载时读当前 holder.value 快照
    catalogIndex: holder,
    loadCatalogIndex: vi.fn(async () => holder.value),
  }),
}))

import D2TabIndex from '../../d2/D2TabIndex.vue'
import D4TabIndex from '../../d4/core/D4TabIndex.vue'

// 每个 TabIndex 只需给 catalog 命中的 code 生成一个「一定与硬编码不同」的名字前缀。
const CAT_PREFIX = '『CAT』'

// Element Plus 组件在测试环境未全局注册，shallowMount 无法自动 stub（会当原生元素渲染，
// 触发 el-table-column 的 #default="{ row }" 作用域插槽以 undefined 调用而崩）。
// 显式 stub 为不调用作用域插槽的空节点；本测试只读 vm.displayRows，不依赖 DOM 渲染。
const elStubs = {
  'el-table': { template: '<div class="el-table-stub"><slot /></div>' },
  'el-table-column': { template: '<div class="el-table-column-stub"></div>' },
  'el-progress': { template: '<div class="el-progress-stub"></div>' },
  'el-tag': { template: '<span class="el-tag-stub"><slot /></span>' },
}

const mountGlobal = { provide: { jumpToSection: () => {} }, stubs: elStubs }

function mountD2(catalog: Map<string, { sheet_name: string; addr_id: string; order: number }>) {
  holder.value = catalog
  return shallowMount(D2TabIndex, {
    props: {
      wpId: 'wp-d2',
      projectId: 'proj-1',
      allResponses: new Map<string, any>(),
      isReadonly: false,
    },
    global: mountGlobal,
  })
}

function mountD4(catalog: Map<string, { sheet_name: string; addr_id: string; order: number }>) {
  holder.value = catalog
  return shallowMount(D4TabIndex, {
    props: {
      wpId: 'wp-d4',
      projectId: 'proj-1',
      allResponses: new Map<string, any>(),
      isReadonly: false,
      ipoGroupVisible: true,
      hasExportBusiness: true,
    },
    global: mountGlobal,
  })
}

/** 读取组件当前硬编码行（挂载空 catalog 时 displayRows === 硬编码基线） */
function hardcodedRows(mountFn: typeof mountD2): Array<{ code: string; name: string }> {
  const wrapper = mountFn(new Map())
  const rows = (wrapper.vm as any).displayRows as Array<{ code: string; name: string }>
  const baseline = rows.map((r) => ({ code: r.code, name: r.name }))
  wrapper.unmount()
  return baseline
}

/** 为给定 code 子集构造 catalog map（名称带 CAT_PREFIX，保证与硬编码不同） */
function buildCatalog(
  codes: string[],
  parentWp: string,
): Map<string, { sheet_name: string; addr_id: string; order: number }> {
  const map = new Map<string, { sheet_name: string; addr_id: string; order: number }>()
  codes.forEach((code, i) => {
    map.set(code, {
      sheet_name: `${CAT_PREFIX}${code}`,
      addr_id: `${parentWp}/${code}/_sheet`,
      order: 100 + i,
    })
  })
  return map
}

function runSubsetFallbackProperty(
  label: string,
  mountFn: typeof mountD2,
  parentWp: string,
) {
  describe(`Feature: acnr-consumer-wiring, Property 23 — ${label}`, () => {
    beforeEach(() => {
      holder.value = new Map()
    })

    const baseline = hardcodedRows(mountFn)
    const allCodes = baseline.map((r) => r.code)
    const hardName = new Map(baseline.map((r) => [r.code, r.name]))

    it('对任意 catalog 子集：名称按命中来源合并，行集与编码不漂移', () => {
      fc.assert(
        fc.property(
          // 随机挑选一部分 code 进入 catalog（可能空、可能全量）
          fc.subarray(allCodes),
          (catalogCodes) => {
            const catalog = buildCatalog(catalogCodes, parentWp)
            const catalogKeys = new Set(catalogCodes)

            const wrapper = mountFn(catalog)
            const rows = (wrapper.vm as any).displayRows as Array<{
              code: string
              name: string
              addrId?: string
            }>

            try {
              // (1) 行数不变，无行被丢弃（无空白目录，Req 18.7）
              expect(rows.length).toBe(baseline.length)

              // (2) code 集合与顺序恒为本地硬编码（catalog 只覆盖名称，Req 18.2/18.5）
              expect(rows.map((r) => r.code)).toEqual(allCodes)

              // (3) 逐行合并语义
              const catalogSourcedCodes: string[] = []
              for (const row of rows) {
                if (catalogKeys.has(row.code)) {
                  // 命中 catalog → 名称/addr_id 来自 catalog（Req 18.1）
                  expect(row.name).toBe(`${CAT_PREFIX}${row.code}`)
                  expect(row.addrId).toBe(`${parentWp}/${row.code}/_sheet`)
                  catalogSourcedCodes.push(row.code)
                } else {
                  // 未命中 → 回退硬编码名（Req 18.7），addr_id 未定义
                  expect(row.name).toBe(hardName.get(row.code))
                  expect(row.addrId).toBeUndefined()
                }
              }

              // (4) subset 不变式：采用 catalog 名称的 code 子集 ⊆ catalog keys（Req 18.4 运行时面）
              for (const c of catalogSourcedCodes) {
                expect(catalogKeys.has(c)).toBe(true)
              }
            } finally {
              wrapper.unmount()
            }
          },
        ),
        { numRuns: 40 },
      )
    })

    it('catalog 为空 → 全部行回退硬编码，行数不变（Req 18.7）', () => {
      const wrapper = mountFn(new Map())
      const rows = (wrapper.vm as any).displayRows as Array<{
        code: string
        name: string
        addrId?: string
      }>
      expect(rows.length).toBe(baseline.length)
      for (const row of rows) {
        expect(row.name).toBe(hardName.get(row.code))
        expect(row.addrId).toBeUndefined()
      }
      wrapper.unmount()
    })

    it('catalog 全量命中 → 全部行名称来自 catalog（Req 18.1）', () => {
      const catalog = buildCatalog(allCodes, parentWp)
      const wrapper = mountFn(catalog)
      const rows = (wrapper.vm as any).displayRows as Array<{
        code: string
        name: string
        addrId?: string
      }>
      for (const row of rows) {
        expect(row.name).toBe(`${CAT_PREFIX}${row.code}`)
        expect(row.addrId).toBe(`${parentWp}/${row.code}/_sheet`)
      }
      wrapper.unmount()
    })
  })
}

runSubsetFallbackProperty('D2TabIndex 目录', mountD2, 'D2')
runSubsetFallbackProperty('D4TabIndex 目录', mountD4 as unknown as typeof mountD2, 'D4')

// ─── 单测：tabName/applicable 等本地元数据不受 catalog 影响（Req 18.2/18.5） ───
describe('Feature: acnr-consumer-wiring, P23 — 本地路由/适用性元数据保留', () => {
  beforeEach(() => {
    holder.value = new Map()
  })

  it('D2：catalog 命中不改 applicable / sheetLabel（本地元数据）', () => {
    // 空 catalog 基线
    const base = mountD2(new Map())
    const baseRows = (base.vm as any).displayRows as Array<{
      code: string
      applicable: boolean
      sheetLabel: string
    }>
    const baseMeta = new Map(baseRows.map((r) => [r.code, { applicable: r.applicable, sheetLabel: r.sheetLabel }]))
    base.unmount()

    // 全量命中 catalog
    const codes = [...baseMeta.keys()]
    const wrapper = mountD2(buildCatalog(codes, 'D2'))
    const rows = (wrapper.vm as any).displayRows as Array<{
      code: string
      applicable: boolean
      sheetLabel: string
      name: string
    }>
    for (const row of rows) {
      const meta = baseMeta.get(row.code)!
      // 名称被 catalog 覆盖
      expect(row.name).toBe(`『CAT』${row.code}`)
      // 但本地路由/适用性不变（Req 18.2/18.5）
      expect(row.applicable).toBe(meta.applicable)
      expect(row.sheetLabel).toBe(meta.sheetLabel)
    }
    wrapper.unmount()
  })

  it('D4：catalog 命中不改 applicable / tabName（本地元数据）', () => {
    const base = mountD4(new Map())
    const baseRows = (base.vm as any).displayRows as Array<{
      code: string
      applicable: boolean
      tabName: string
    }>
    const baseMeta = new Map(baseRows.map((r) => [r.code, { applicable: r.applicable, tabName: r.tabName }]))
    base.unmount()

    const codes = [...baseMeta.keys()]
    const wrapper = mountD4(buildCatalog(codes, 'D4'))
    const rows = (wrapper.vm as any).displayRows as Array<{
      code: string
      applicable: boolean
      tabName: string
      name: string
    }>
    for (const row of rows) {
      const meta = baseMeta.get(row.code)!
      expect(row.name).toBe(`『CAT』${row.code}`)
      expect(row.applicable).toBe(meta.applicable)
      expect(row.tabName).toBe(meta.tabName)
    }
    wrapper.unmount()
  })
})
