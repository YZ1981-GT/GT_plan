/**
 * 项目默认金额单位的项目上下文时序。
 *
 * Validates: Requirements R4, AC-05, AC-06
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import ts from 'typescript'

/*
 * 使用 vi.spyOn 而非 vi.mock factory 劫持 getProject / api.get：
 * project.ts 在首次求值时从 @/services/auditPlatformApi 和 @/services/apiProxy
 * 捕获 ESM live binding；vi.mock factory 会替换整个模块对象，但如果 vitest 的
 * transform 管线让 project.ts 先于 mock 注册而被求值，闭包内的绑定就指向原模块。
 * vi.spyOn 直接修改现有模块命名空间对象的属性，所有持有该对象引用的消费者
 *（包括已经求值的 project.ts）都能看到替换。
 */
import * as auditPlatformApi from '@/services/auditPlatformApi'
import * as apiProxyModule from '@/services/apiProxy'

// eventBus 只需静默 emit，vi.mock 可行（project.ts 只调 eventBus.emit，对象引用不影响流程）
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: vi.fn() } }))

import { useProjectStore } from '@/stores/project'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

function deferred<T>() {
  let resolvePromise!: (value: T) => void
  let rejectPromise!: (reason: unknown) => void
  const promise = new Promise<T>((resolve, reject) => {
    resolvePromise = resolve
    rejectPromise = reject
  })
  return { promise, resolve: resolvePromise, reject: rejectPromise }
}

const route = (projectId?: string) => ({
  params: projectId ? { projectId } : {},
  query: {},
}) as any

let getProjectSpy: ReturnType<typeof vi.spyOn>
let apiGetSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  vi.restoreAllMocks()
  setActivePinia(createPinia())
  getProjectSpy = vi.spyOn(auditPlatformApi, 'getProject')
  apiGetSpy = vi.spyOn(apiProxyModule.api, 'get')
  apiGetSpy.mockResolvedValue({ years: [] })
  localStorage.clear()
  vi.spyOn(console, 'warn').mockImplementation(() => undefined)
})

describe('项目上下文的正式金额单位', () => {
  it.each(['yuan', 'qian', 'wan'] as const)(
    '项目详情返回 %s 时保留该三值',
    async (amountUnit) => {
      getProjectSpy.mockResolvedValue({ id: 'p1', audit_year: 2025, amount_unit: amountUnit } as any)
      const store = useProjectStore()

      await store.loadProjectContext('p1')

      expect(store.projectAmountUnit).toBe(amountUnit)
      expect(store.currentProjectContext.projectAmountUnit).toBe(amountUnit)
    },
  )

  it('缺失或非法单位按元降级，详情请求失败保持 null', async () => {
    const store = useProjectStore()
    getProjectSpy.mockResolvedValueOnce({ id: 'p1', amount_unit: 'hundred' } as any)
    await store.loadProjectContext('p1')
    expect(store.projectAmountUnit).toBe('yuan')

    getProjectSpy.mockRejectedValue(new Error('network down'))
    await store.loadProjectContext('p2')
    expect(store.projectId).toBe('p2')
    expect(store.projectAmountUnit).toBeNull()
  })

  it('A(wan) → B(慢/失败) → A：切换立刻清空且不沿用旧值', async () => {
    const store = useProjectStore()
    getProjectSpy.mockResolvedValueOnce({ id: 'A', audit_year: 2025, amount_unit: 'wan' } as any)
    await store.loadProjectContext('A')
    expect(store.projectAmountUnit).toBe('wan')

    const slowB = deferred<any>()
    getProjectSpy.mockReturnValueOnce(slowB.promise).mockRejectedValueOnce(new Error('B failed'))
    const loadingB = store.loadProjectContext('B')
    expect(store.projectAmountUnit).toBeNull()
    slowB.reject(new Error('B failed'))
    await loadingB
    expect(store.projectId).toBe('B')
    expect(store.projectAmountUnit).toBeNull()

    getProjectSpy.mockResolvedValueOnce({ id: 'A', audit_year: 2026, amount_unit: 'qian' } as any)
    await store.loadProjectContext('A')
    expect(store.projectAmountUnit).toBe('qian')
  })

  it('迟到的 A 响应不会覆盖当前 B 的项目金额单位', async () => {
    const first = deferred<any>()
    const second = deferred<any>()
    getProjectSpy.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const store = useProjectStore()

    const loadingA = store.loadProjectContext('A')
    const loadingB = store.loadProjectContext('B')
    expect(store.projectAmountUnit).toBeNull()

    second.resolve({ id: 'B', audit_year: 2025, amount_unit: 'qian' })
    await loadingB
    first.resolve({ id: 'A', audit_year: 2025, amount_unit: 'wan' })
    await loadingA

    expect(store.projectId).toBe('B')
    expect(store.projectAmountUnit).toBe('qian')
  })

  it('离开项目、过期的保存响应和显式 qian 个人选择互不污染', async () => {
    const store = useProjectStore()
    const displayPrefs = useDisplayPrefsStore()
    displayPrefs.setUnit('qian')
    getProjectSpy.mockResolvedValue({ id: 'p1', audit_year: 2025, amount_unit: 'wan' } as any)
    await store.loadProjectContext('p1')

    expect(store.projectAmountUnit).toBe('wan')
    expect(displayPrefs.amountUnit).toBe('qian')
    expect(store.applyProjectAmountUnit('p2', 'yuan')).toBe(false)
    expect(store.projectAmountUnit).toBe('wan')

    await store.syncFromRoute(route())
    expect(store.projectAmountUnit).toBeNull()
  })

  it('另一账号仅在下一次 loadProjectContext 后看到项目单位更新', async () => {
    const piniaA = createPinia()
    setActivePinia(piniaA)
    const storeA = useProjectStore()
    getProjectSpy.mockResolvedValueOnce({ id: 'p1', audit_year: 2025, amount_unit: 'yuan' } as any)
    await storeA.loadProjectContext('p1')

    const piniaB = createPinia()
    setActivePinia(piniaB)
    const storeB = useProjectStore()
    getProjectSpy.mockResolvedValueOnce({ id: 'p1', audit_year: 2025, amount_unit: 'yuan' } as any)
    await storeB.loadProjectContext('p1')

    // A 的成功 PUT 只改自己的当前 store；没有 SSE 推送给 B。
    expect(storeA.applyProjectAmountUnit('p1', 'wan')).toBe(true)
    expect(storeB.projectAmountUnit).toBe('yuan')

    getProjectSpy.mockResolvedValueOnce({ id: 'p1', audit_year: 2025, amount_unit: 'wan' } as any)
    await storeB.loadProjectContext('p1')
    expect(storeB.projectAmountUnit).toBe('wan')
  })
})

function hasProjectAmountUnitReset(source: string): boolean {
  const file = ts.createSourceFile('project.ts', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  let hasNullableState = false
  let hasResetAssignment = false

  const visit = (node: ts.Node, inReset = false) => {
    const isReset = ts.isFunctionDeclaration(node) && node.name?.text === 'resetProjectScopedState'
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.name.text === 'projectAmountUnit') {
      const text = node.initializer?.getText(file) || ''
      hasNullableState ||= text.includes('ref<ProjectAmountUnit | null>(null)')
    }
    if (inReset && ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
      const left = node.left.getText(file)
      const right = node.right.getText(file)
      hasResetAssignment ||= left === 'projectAmountUnit.value' && right === 'null'
    }
    node.forEachChild((child) => visit(child, inReset || isReset))
  }
  visit(file)
  return hasNullableState && hasResetAssignment
}

describe('项目金额单位 store 清空的变异守卫', () => {
  const sourcePath = resolve(__dirname, '../project.ts')
  const source = readFileSync(sourcePath, 'utf-8')

  it('当前实现有 nullable 状态和切项目清空动作', () => {
    expect(hasProjectAmountUnitReset(source)).toBe(true)
  })

  it('变异：删除 resetProjectScopedState 的单位清空后守卫必须红', () => {
    const original = source.replace(/\r\n/g, '\n')
    const mutated = original.replace(
      '    projectAmountUnit.value = null\n    projectStatus.value = \'\'\n',
      '    projectStatus.value = \'\'\n',
    )
    expect(mutated).not.toBe(original)
    expect(hasProjectAmountUnitReset(mutated)).toBe(false)
  })
})
