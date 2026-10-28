/**
 * useQueryBuilderAccess.spec.ts — 构建器入口判据只取 access 接口（advanced-query-linkage-closure 任务 30；ADR-AQL-08，R3.6、R11.3）
 *
 * - 结论由 `GET /api/query/access` 给出：可用 = 准入通过且作用域非空；原因取接口 reason；
 * - 模块级缓存：同一身份多个入口只取一次；换人登录 / 登出即失效；上次失败的下次使用重取；
 * - 取不到结论时不可用，不回落到前端角色清单（变异 B9-c）；
 * - 源码（TS 语法树）里不再有任何系统角色字面量，也不导出角色清单。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const apiMocks = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ default: apiMocks, api: apiMocks }))
const roleHolder = vi.hoisted(() => ({ value: 'admin' }))
vi.mock('@/composables/usePermissionMatrix', () => ({
  usePermissionMatrix: () => ({ currentRole: { get value() { return roleHolder.value } } }),
}))

import {
  ACCESS_NOT_LOGGED_IN_REASON,
  ACCESS_UNAVAILABLE_REASON,
  resetQueryBuilderAccessCache,
  useQueryBuilderAccess,
} from '../useQueryBuilderAccess'
import { useAuthStore } from '@/stores/auth'

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'useQueryBuilderAccess.ts')
const FORBIDDEN = '高级构建器仅限管理员、合伙人、经理（含任一项目的项目经理）使用'

function accessCalls() {
  return apiMocks.get.mock.calls.filter((c) => c[0] === '/api/query/access')
}

/** 挂一个只调用本 composable 的组件，返回它暴露的状态 */
function useInComponent() {
  let state: ReturnType<typeof useQueryBuilderAccess> | null = null
  const Comp = defineComponent({ setup() { state = useQueryBuilderAccess(); return () => h('div') } })
  const wrapper = mount(Comp)
  return { wrapper, get: () => state! }
}

beforeEach(() => {
  resetQueryBuilderAccessCache()
  apiMocks.get.mockReset()
  roleHolder.value = 'admin'
  useAuthStore().token = 'tok'
})

describe('useQueryBuilderAccess — 结论只取 access 接口', () => {
  it('系统角色 / 项目经理可用：canUseBuilder、计数与不限项目按接口', async () => {
    apiMocks.get.mockResolvedValue({ allowed: true, basis: 'project_manager', reason: null, all_projects: false, accessible_project_count: 2 })
    const { get } = useInComponent()
    await flushPromises()
    expect(get().canUseBuilder.value).toBe(true)
    expect(get().accessibleProjectCount.value).toBe(2)
    expect(get().allProjects.value).toBe(false)
    expect(get().builderDisabledReason.value).toBe('')
    expect(accessCalls()[0][1]).toMatchObject({ _silent: true })
  })

  it('无权与作用域为空都不可用，原因取接口 reason', async () => {
    apiMocks.get.mockResolvedValueOnce({ allowed: false, basis: null, reason: FORBIDDEN, all_projects: false, accessible_project_count: 0 })
    const a = useInComponent()
    await flushPromises()
    expect(a.get().canUseBuilder.value).toBe(false)
    expect(a.get().builderDisabledReason.value).toBe(FORBIDDEN)
    resetQueryBuilderAccessCache()
    apiMocks.get.mockResolvedValueOnce({ allowed: true, basis: 'system_role', reason: '您可访问的项目均设有审计循环范围，请在业务视图中查询', all_projects: false, accessible_project_count: 0 })
    const b = useInComponent()
    await flushPromises()
    expect(b.get().canUseBuilder.value).toBe(false)
    expect(b.get().builderDisabledReason.value).toBe('您可访问的项目均设有审计循环范围，请在业务视图中查询')
  })

  it('接口失败或返回形状不对：不可用并提示，不回落到前端角色（admin 也一样）；下次使用重取', async () => {
    roleHolder.value = 'admin'
    apiMocks.get.mockRejectedValueOnce(new Error('Network Error'))
    const a = useInComponent()
    await flushPromises()
    expect(a.get().canUseBuilder.value).toBe(false)
    expect(a.get().builderDisabledReason.value).toBe(ACCESS_UNAVAILABLE_REASON)
    apiMocks.get.mockResolvedValueOnce({ tables: [] })
    useInComponent()
    await flushPromises()
    expect(accessCalls()).toHaveLength(2)
    expect(a.get().canUseBuilder.value).toBe(false)
    expect(a.get().builderDisabledReason.value).toBe(ACCESS_UNAVAILABLE_REASON)
  })

  it('模块级缓存：同一身份两个入口只取一次；换人登录重取；登出清空且不发请求', async () => {
    apiMocks.get.mockResolvedValue({ allowed: true, basis: 'system_role', reason: null, all_projects: true, accessible_project_count: null })
    const a = useInComponent()
    const b = useInComponent()
    await flushPromises()
    expect(accessCalls()).toHaveLength(1)
    expect(a.get().canUseBuilder.value && b.get().canUseBuilder.value).toBe(true)

    const auth = useAuthStore()
    auth.user = { id: 'u-2', username: 'u2', email: '', role: 'auditor' } as any
    await nextTick()
    await flushPromises()
    expect(accessCalls()).toHaveLength(2)

    auth.user = null
    auth.token = null
    await nextTick()
    await flushPromises()
    expect(accessCalls()).toHaveLength(2)
    expect(a.get().canUseBuilder.value).toBe(false)
    expect(a.get().builderDisabledReason.value).toBe(ACCESS_NOT_LOGGED_IN_REASON)
  })

  it('换人登录时上一身份迟到的回包不写入', async () => {
    let release: (v: unknown) => void = () => {}
    apiMocks.get.mockImplementationOnce(() => new Promise((r) => { release = r }))
    const a = useInComponent()
    await flushPromises()
    apiMocks.get.mockResolvedValueOnce({ allowed: false, basis: null, reason: FORBIDDEN, all_projects: false, accessible_project_count: 0 })
    useAuthStore().user = { id: 'u-3', username: 'u3', email: '', role: 'auditor' } as any
    await nextTick()
    await flushPromises()
    release({ allowed: true, basis: 'system_role', reason: null, all_projects: true, accessible_project_count: null })
    await flushPromises()
    expect(a.get().canUseBuilder.value).toBe(false)
    expect(a.get().builderDisabledReason.value).toBe(FORBIDDEN)
  })
})

describe('源码：前端不再持有角色清单（TS 语法树）', () => {
  it('没有任何系统角色字面量，也不导出角色清单', () => {
    const sf = ts.createSourceFile('useQueryBuilderAccess.ts', readFileSync(SRC, 'utf-8'), ts.ScriptTarget.Latest, true)
    const literals: string[] = []
    const exportsList: string[] = []
    const visit = (node: ts.Node) => {
      if (ts.isStringLiteralLike(node)) literals.push(node.text)
      if (ts.isVariableStatement(node) && node.modifiers?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword)) {
        for (const d of node.declarationList.declarations) if (ts.isIdentifier(d.name)) exportsList.push(d.name.text)
      }
      ts.forEachChild(node, visit)
    }
    visit(sf)
    expect(literals.length).toBeGreaterThan(5) // 扫描器确实读到了字面量（不是空转）
    expect(literals.filter((s) => ['admin', 'manager', 'partner'].includes(s))).toEqual([])
    expect(exportsList).not.toContain('QUERY_BUILDER_ROLES')
  })
})
