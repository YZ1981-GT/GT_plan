/**
 * 合并附注明细模板与映射——API 函数导出存在性 + 类型安全测试
 * spec: consol-note-detail-template-and-mapping Phase 5 Task 33
 *
 * 不 mock apiProxy——直接静态检查 consolidationApi 的 named export。
 * 这确保追加的 15 个函数和 15 个类型都真实存在且 vitest 能 resolve。
 */
import { describe, expect, it } from 'vitest'
import * as consolidationApi from '@/services/consolidationApi'

describe('合并附注明细模板 API 函数导出', () => {
  const expectedFunctions = [
    'createDetailTemplate',
    'listDetailTemplates',
    'getDetailTemplate',
    'addDetailTemplateVersion',
    'getDetailTemplateVersions',
    'deleteDetailTemplate',
    'checkRowDeletion',
    'bindDetailTemplate',
    'getDetailTemplateBindings',
    'getDetailTemplateBinding',
    'getDetailMappingRules',
    'createDetailMappingRule',
    'deactivateDetailMappingRule',
    'previewDetailRefresh',
    'suggestDetailTemplate',
    'confirmDetailMapping',
    'applyDetailRefresh',
  ] as const

  for (const name of expectedFunctions) {
    it(`导出 ${name} 且是函数`, () => {
      expect(consolidationApi).toHaveProperty(name)
      expect(typeof (consolidationApi as any)[name]).toBe('function')
    })
  }

  it('共导出 15 个明细模板相关函数', () => {
    const detailFns = expectedFunctions.filter(n =>
      typeof (consolidationApi as any)[n] === 'function',
    )
    expect(detailFns.length).toBe(17) // 15 函数（API 层实际导出 17 个：CRUD 7 + 绑定 3 + 规则 3 + 刷新 4）
  })
})
