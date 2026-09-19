/**
 * useFormulaScopeCatalog.spec.ts — 公式作用域过滤 + 全局公式总览（Req 24 / Task 20.1）
 *
 * 消费后端 GET /api/formula-scope/{project_id}/formulas（Task 20.2）。覆盖：
 *  - Req 24.1/24.2：按 scope 加载只返回该域公式（不含他域）
 *  - Req 24.3：全局页跨全部 7 类作用域取并集
 *  - Req 24.5：作用域隔离 —— 一个作用域的编辑不改变另一作用域的列表
 *  - Req 24.6：来源地址经 ACNR full_resolve 取 canonical semantic_label（非拼坐标串）
 *
 * 不得假绿：http 与 useAcnr 用桩注入，断言真实过滤/并集/隔离/解析行为。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// ─── Mock http（axios 封装，自动带 Authorization；此处桩返回 { data: payload }） ──
const mockGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { get: (...args: unknown[]) => mockGet(...args) },
}))

// ─── Mock useAcnr（受控 resolveAddr，返回带 semantic_label） ──────────────────
const mockResolveAddr = vi.fn()
vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({ resolveAddr: mockResolveAddr }),
}))

// ─── Import after mocks ───────────────────────────────────────────────────────
import {
  useFormulaScopeCatalog,
  FORMULA_SCOPES,
  SCOPE_LABEL_MAP,
  type FormulaScope,
} from '@/composables/useFormulaScopeCatalog'

const PID = '11111111-1111-1111-1111-111111111111'

/** 构造一条后端 formula_to_dict 形态的公式 item。 */
function item(
  id: string,
  scope: FormulaScope,
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    id,
    project_id: PID,
    wp_id: `wp-${id}`,
    sheet_name: `${scope}-sheet`,
    target_cell: `B${id}`,
    expression: `=TB('100${id}','期末余额')`,
    formula_type: 'auto_calc',
    formula_source: 'preset',
    refs: [],
    issue_description: null,
    hint_text: null,
    last_computed_at: null,
    scope,
    scope_label: SCOPE_LABEL_MAP[scope],
    created_at: null,
    updated_at: null,
    ...overrides,
  }
}

/** 桩：scope 端点响应（{ data: { items } }）。 */
function scopeResponse(items: Record<string, unknown>[]) {
  return { data: { items } }
}

/** 桩：全局并集端点响应（{ data: { scopes: {..} } }）。 */
function globalResponse(byScope: Partial<Record<FormulaScope, Record<string, unknown>[]>>) {
  const scopes: Record<string, { items: Record<string, unknown>[] }> = {}
  for (const s of FORMULA_SCOPES) {
    scopes[s] = { items: byScope[s] ?? [] }
  }
  return { data: { scopes } }
}

beforeEach(() => {
  mockGet.mockReset()
  mockResolveAddr.mockReset()
  mockResolveAddr.mockResolvedValue({ found: true, semantic_label: '默认来源' })
})

// ══════════════════════════════════════════════════════════════════════════════
describe('Req 24.1/24.2 — 按 scope 加载只返回该域公式', () => {
  it('loadScope(note) 命中 scope 端点，返回行全部属 note，且不加载他域', async () => {
    mockGet.mockResolvedValueOnce(
      scopeResponse([item('1', 'note'), item('2', 'note')]),
    )
    const cat = useFormulaScopeCatalog()
    const rows = await cat.loadScope(PID, 'note')

    // 端点与参数正确
    expect(mockGet).toHaveBeenCalledWith(
      `/api/formula-scope/${PID}/formulas`,
      { params: { scope: 'note' } },
    )
    // 返回仅 note 域
    expect(rows).toHaveLength(2)
    expect(rows.every((r) => r.scope === 'note')).toBe(true)
    // 其他作用域为空（无泄漏，Req 24.2）
    expect(cat.getScopeRows('report')).toHaveLength(0)
    expect(cat.getScopeRows('workpaper')).toHaveLength(0)
  })

  it('非法 scope / 缺 projectId → 返回空且不发请求', async () => {
    const cat = useFormulaScopeCatalog()
    expect(await cat.loadScope(PID, 'bogus' as FormulaScope)).toEqual([])
    expect(await cat.loadScope('', 'note')).toEqual([])
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('addrKey 派生：有引用 addr_id 用之，无引用回退 wp/sheet/cell 复合键', async () => {
    mockGet.mockResolvedValueOnce(
      scopeResponse([
        item('1', 'note', { refs: [{ addr_id: 'D2/D2-2/E100' }] }),
        item('2', 'note', { refs: [], wp_id: 'wpX', sheet_name: 'shY', target_cell: 'C9' }),
      ]),
    )
    const cat = useFormulaScopeCatalog()
    const rows = await cat.loadScope(PID, 'note')
    expect(rows[0].addrKey).toBe('D2/D2-2/E100')
    expect(rows[0].sourceAddrId).toBe('D2/D2-2/E100')
    expect(rows[1].addrKey).toBe('wpX::shY::C9')
    expect(rows[1].sourceAddrId).toBeNull()
  })
})

// ══════════════════════════════════════════════════════════════════════════════
describe('Req 24.3 — 全局页跨全部 7 类作用域取并集', () => {
  it('loadGlobal 返回各域并集，totalCount == 各域之和', async () => {
    mockGet.mockResolvedValueOnce(
      globalResponse({
        note: [item('1', 'note'), item('2', 'note')],
        report: [item('3', 'report')],
        workpaper: [item('4', 'workpaper')],
      }),
    )
    const cat = useFormulaScopeCatalog()
    const grouped = await cat.loadGlobal(PID)

    // 端点无 scope 参数
    expect(mockGet).toHaveBeenCalledWith(`/api/formula-scope/${PID}/formulas`)
    // 分组并集
    expect(grouped.note).toHaveLength(2)
    expect(grouped.report).toHaveLength(1)
    expect(grouped.workpaper).toHaveLength(1)
    expect(grouped.tb).toHaveLength(0)
    // 全局总数 == 并集
    expect(cat.totalCount.value).toBe(4)
    expect(cat.allRows.value).toHaveLength(4)
    // 全部 7 类键齐全
    expect(Object.keys(cat.globalGrouped.value).sort()).toEqual([...FORMULA_SCOPES].sort())
  })
})

// ══════════════════════════════════════════════════════════════════════════════
describe('Req 24.5 — 作用域隔离：一个作用域的编辑不改另一作用域列表', () => {
  it('upsert 到 note 后 report 列表逐一不变', async () => {
    mockGet.mockResolvedValueOnce(
      globalResponse({
        note: [item('1', 'note')],
        report: [item('2', 'report'), item('3', 'report')],
      }),
    )
    const cat = useFormulaScopeCatalog()
    await cat.loadGlobal(PID)

    const reportBefore = cat.getScopeRows('report').map((r) => r.id)
    expect(reportBefore).toEqual(['2', '3'])

    // 在 note 域新增一条
    const newNote = cat.getScopeRows('note')[0]
    cat.upsertFormula('note', { ...newNote, id: '99', addrKey: 'note::new::A1' })

    // note 变化
    expect(cat.getScopeRows('note')).toHaveLength(2)
    // report 逐一不变（Req 24.5）
    expect(cat.getScopeRows('report').map((r) => r.id)).toEqual(reportBefore)
  })

  it('从 report 删除后 note 列表不变', async () => {
    mockGet.mockResolvedValueOnce(
      globalResponse({
        note: [item('1', 'note'), item('2', 'note')],
        report: [item('3', 'report', { refs: [{ addr_id: 'A/A-1/B1' }] })],
      }),
    )
    const cat = useFormulaScopeCatalog()
    await cat.loadGlobal(PID)

    const noteBefore = cat.getScopeRows('note').map((r) => r.id)
    cat.removeFormula('report', 'A/A-1/B1')

    expect(cat.getScopeRows('report')).toHaveLength(0)
    expect(cat.getScopeRows('note').map((r) => r.id)).toEqual(noteBefore)
  })

  it('loadScope 只替换目标域缓存，不清空其他已加载域', async () => {
    // 先加载 note
    mockGet.mockResolvedValueOnce(scopeResponse([item('1', 'note')]))
    const cat = useFormulaScopeCatalog()
    await cat.loadScope(PID, 'note')
    expect(cat.getScopeRows('note')).toHaveLength(1)

    // 再加载 report → note 不受影响
    mockGet.mockResolvedValueOnce(scopeResponse([item('2', 'report')]))
    await cat.loadScope(PID, 'report')
    expect(cat.getScopeRows('report')).toHaveLength(1)
    expect(cat.getScopeRows('note')).toHaveLength(1)
  })
})

// ══════════════════════════════════════════════════════════════════════════════
describe('Req 24.6 — 来源地址经 ACNR full_resolve 取 semantic_label（非拼坐标串）', () => {
  it('resolveSources 用 sourceAddrId 调 resolveAddr，写 canonical semantic_label', async () => {
    mockGet.mockResolvedValueOnce(
      scopeResponse([item('1', 'note', { refs: [{ addr_id: 'D2/D2-2/E100' }] })]),
    )
    mockResolveAddr.mockResolvedValue({
      found: true,
      addr_id: 'D2/D2-2/E100',
      semantic_label: 'D2 应收账款明细表 · 期末余额',
    })
    const cat = useFormulaScopeCatalog()
    const rows = await cat.loadScope(PID, 'note')
    await cat.resolveSources(rows)

    expect(mockResolveAddr).toHaveBeenCalledWith('D2/D2-2/E100')
    expect(rows[0].sourceLabel).toBe('D2 应收账款明细表 · 期末余额')
    // 反面：来源标签不是坐标串原文
    expect(rows[0].sourceLabel).not.toBe('D2/D2-2/E100')
  })

  it('full_resolve 未命中（found=false）→ sourceLabel 保持 null，不拼坐标', async () => {
    mockGet.mockResolvedValueOnce(
      scopeResponse([item('1', 'note', { refs: [{ addr_id: 'X/Y/Z1' }] })]),
    )
    mockResolveAddr.mockResolvedValue({ found: false, error: 'miss' })
    const cat = useFormulaScopeCatalog()
    const rows = await cat.loadScope(PID, 'note')
    await cat.resolveSources(rows)

    expect(rows[0].sourceLabel).toBeNull()
  })

  it('无引用 addr_id 的公式不触发 resolveAddr', async () => {
    mockGet.mockResolvedValueOnce(scopeResponse([item('1', 'note', { refs: [] })]))
    const cat = useFormulaScopeCatalog()
    const rows = await cat.loadScope(PID, 'note')
    await cat.resolveSources(rows)
    expect(mockResolveAddr).not.toHaveBeenCalled()
    expect(rows[0].sourceLabel).toBeNull()
  })
})
