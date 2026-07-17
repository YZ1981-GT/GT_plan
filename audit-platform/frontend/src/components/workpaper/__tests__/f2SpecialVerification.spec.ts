/**
 * F2 存货特殊组 — 性能优化验证 (Task 13.2) + UI规范验证 (Task 13.3)
 *
 * 通过静态源码分析验证关键实现模式：
 * - 13.2: 虚拟滚动/分组折叠/区段Tab/固定列滚动列/defineAsyncComponent/公式纯函数
 * - 13.3: 13px字体/AI+复核按钮右对齐/公式列虚线tooltip/min-width/el-card/details折叠
 *
 * Validates: Requirements 22.1~22.8
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

const COMP_BASE = path.resolve(__dirname, '..')

function readSource(relativePath: string): string {
  return fs.readFileSync(path.join(COMP_BASE, relativePath), 'utf-8')
}

describe('Task 13.2: 性能优化验证', () => {
  describe('F2-64 单耗分析(232行) 虚拟滚动 + 产品分组折叠', () => {
    const src = readSource('f2-special/ipo/F2TabUnitConsumption.vue')

    it('使用 el-table-v2 实现虚拟滚动', () => {
      expect(src).toContain('el-table-v2')
    })

    it('配置虚拟滚动行高和容器高度', () => {
      expect(src).toContain(':row-height=')
      expect(src).toContain(':height=')
    })

    it('实现产品分组折叠 (el-collapse)', () => {
      expect(src).toContain('el-collapse')
      expect(src).toContain('el-collapse-item')
    })

    it('提供全部展开/折叠操作', () => {
      expect(src).toContain('expandAllGroups')
      expect(src).toContain('collapseAllGroups')
    })

    it('支持分组/聚焦/速览三种视图模式', () => {
      expect(src).toContain("'focus'")
      expect(src).toContain("'group'")
      expect(src).toContain("'flat'")
    })
  })

  describe('F2-61 采购价格(118行) 虚拟滚动', () => {
    const src = readSource('f2-special/ipo/F2TabPurchasePrice.vue')

    it('使用 el-table-v2 实现虚拟滚动', () => {
      expect(src).toContain('el-table-v2')
    })

    it('虚拟滚动根据行数条件启用 (>=50行)', () => {
      expect(src).toContain('useVirtualScroll')
      expect(src).toContain('>= 50')
    })

    it('配置虚拟列定义', () => {
      expect(src).toContain('virtualColumns')
      expect(src).toContain('virtualRows')
    })
  })

  describe('F2-55(37列) 宽表横向滚动 + 固定列', () => {
    const src = readSource('f2-special/contract/F2TabContractCostDetail.vue')

    it('使用 matrix-table 宽表布局', () => {
      expect(src).toContain('matrix-table')
      expect(src).toContain('table-scroll')
    })

    it('包含期初/增加/减少/期末/审计调整/审定列组', () => {
      expect(src).toContain('账面期初余额')
      expect(src).toContain('账面本期增加')
      expect(src).toContain('账面本期减少')
      expect(src).toContain('账面期末余额')
      expect(src).toContain('审计调整')
      expect(src).toContain('期末审定余额')
    })

    it('项目信息列 sticky 固定', () => {
      expect(src).toContain('sticky')
      expect(src).toContain('col-name')
    })

    it('配置横向滚动最小宽度', () => {
      expect(src).toContain('min-width: 3400px')
      expect(src).toContain('overflow-x: auto')
    })
  })

  describe('F2-68(25列) 固定列 + 滚动列渲染', () => {
    const src = readSource('f2-special/ipo/F2TabSupplierStructure.vue')

    it('有固定列 (fixed 属性)', () => {
      const fixedCols = (src.match(/fixed(?:="right")?(?:\s|>|\/)/g) || []).length
      // 至少有序号+供应商名称+采购品类+合作年份+关联方 = 5个固定列 + 右侧操作列
      expect(fixedCols).toBeGreaterThanOrEqual(5)
    })

    it('滚动列区包含T期/T-1期/T-2期分组列', () => {
      expect(src).toContain('T期')
      expect(src).toContain('T-1期')
      expect(src).toContain('T-2期')
    })

    it('有横向滚动容器', () => {
      expect(src).toContain('table-scroll-wrap')
      expect(src).toContain('overflow-x: auto')
    })
  })

  describe('defineAsyncComponent lazy加载', () => {
    const src = readSource('GtF2InventorySpecial.vue')

    it('使用 defineAsyncComponent 延迟加载非首屏组件', () => {
      expect(src).toContain('defineAsyncComponent')
    })

    it('GtOnlyOfficeSheet 通过 defineAsyncComponent 懒加载', () => {
      expect(src).toMatch(/defineAsyncComponent\(\(\)\s*=>\s*import\(['"]\.\/GtOnlyOfficeSheet\.vue['"]\)\)/)
    })

    it('GtWpVersionTrail 通过 defineAsyncComponent 懒加载', () => {
      expect(src).toMatch(/defineAsyncComponent\(\(\)\s*=>\s*import\(/)
      expect(src).toContain('GtWpVersionTrail')
    })

    it('GtWpReviewDialogHost 通过 defineAsyncComponent 懒加载', () => {
      expect(src).toContain("defineAsyncComponent(() => import('./GtWpReviewDialogHost.vue'))")
    })
  })

  describe('公式引擎纯函数（无副作用/无recomputation）', () => {
    const src = readSource('composables/useF2SpecialFormulaEngine.ts')

    it('所有导出函数均为纯函数（export function）', () => {
      const exportFns = src.match(/^export function \w+/gm) || []
      expect(exportFns.length).toBeGreaterThanOrEqual(10)
    })

    it('不包含 ref/reactive/computed（无Vue响应式副作用）', () => {
      expect(src).not.toContain("from 'vue'")
      expect(src).not.toMatch(/\bref\s*\(/)
      expect(src).not.toMatch(/\breactive\s*\(/)
      expect(src).not.toMatch(/\bcomputed\s*\(/)
    })

    it('不包含异步操作（无fetch/axios/await）', () => {
      expect(src).not.toContain('async ')
      expect(src).not.toContain('await ')
      expect(src).not.toContain('fetch(')
      expect(src).not.toContain('axios')
    })

    it('不包含console/localStorage等副作用', () => {
      expect(src).not.toContain('console.')
      expect(src).not.toContain('localStorage')
      expect(src).not.toContain('sessionStorage')
    })
  })
})

describe('Task 13.3: UI规范验证', () => {
  // 收集所有特殊组组件源码
  const componentFiles = [
    'f2-special/contract/F2TabContractCostDetail.vue',
    'f2-special/ipo/F2TabPurchasePrice.vue',
    'f2-special/ipo/F2TabUnitConsumption.vue',
    'f2-special/ipo/F2TabSupplierStructure.vue',
  ]
  const sources = componentFiles.map(readSource)

  describe('13px 字体全局验证', () => {
    it.each(componentFiles)('%s 使用 font-size: 13px', (file) => {
      const src = readSource(file)
      expect(src).toContain('font-size: 13px')
    })
  })

  describe('AI + 复核按钮右对齐 (F2SheetToolbar)', () => {
    it.each(componentFiles)('%s 包含 F2SheetToolbar 组件', (file) => {
      const src = readSource(file)
      expect(src).toContain('F2SheetToolbar')
    })

    it.each(componentFiles)('%s toolbar 使用 flex 布局实现右对齐', (file) => {
      const src = readSource(file)
      expect(src).toContain('display: flex')
      expect(src).toContain('gap:')
    })
  })

  describe('公式列虚线下划线 + cursor:help + tooltip', () => {
    it.each(componentFiles)('%s 有 .formula 样式类定义', (file) => {
      const src = readSource(file)
      expect(src).toContain('.formula')
    })

    it('公式样式包含 underline dotted 虚线效果', () => {
      // 至少一个组件有完整的公式虚线样式定义
      const hasUnderlineDotted = sources.some(
        (s) => s.includes('underline dotted') || s.includes('text-decoration: underline dotted'),
      )
      expect(hasUnderlineDotted).toBe(true)
    })

    it('公式元素使用 span.formula 包裹计算值', () => {
      const hasFormulaSpan = sources.some((s) => s.includes('class="formula"'))
      expect(hasFormulaSpan).toBe(true)
    })
  })

  describe('min-width 自适应列宽', () => {
    it('F2TabContractCostDetail 使用 min-width 保证宽表列宽', () => {
      const src = readSource('f2-special/contract/F2TabContractCostDetail.vue')
      expect(src).toContain('min-width')
    })

    it('F2TabUnitConsumption 使用 min-width 自适应列', () => {
      const src = readSource('f2-special/ipo/F2TabUnitConsumption.vue')
      expect(src).toContain('min-width')
    })
  })

  describe('审计结论区域验证', () => {
    it.each(componentFiles)('%s 包含审计说明/结论textarea', (file) => {
      const src = readSource(file)
      // 每个组件都应有 textarea 用于审计说明
      expect(src).toContain('type="textarea"')
    })
  })

  describe('编制提示 / 引导区域', () => {
    it('F2TabUnitConsumption 有提示信息区域', () => {
      const src = readSource('f2-special/ipo/F2TabUnitConsumption.vue')
      // 有虚拟滚动速览的提示文案
      expect(src).toContain('flat-hint')
    })
  })
})
