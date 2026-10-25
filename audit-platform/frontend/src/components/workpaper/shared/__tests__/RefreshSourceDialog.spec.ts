/**
 * RefreshSourceDialog.spec.ts — Task 12.1 / 12.2 / 12.3 守卫
 *
 * spec: workpaper-sync-adopt-overwrite-and-refresh-source
 *
 * | 节 | 判据 | Task |
 * | --- | --- | --- |
 * | §1 | 交互路径：三项内容 / 说明项零请求 / 取消零写入 | 12.1 |
 * | §2 | Property 12：摘要数字与响应字段逐值相等（含变异反证） | 12.2 |
 * | §3 | 中文文案守卫 + 豁免白名单 + 白名单无失效条目 | 12.3 |
 * | §4 | 禁用态（无 entry_id / not_published / contract_required） | 10.3 |
 * | §5 | 覆盖路径：二次确认请求体 / 409 重取 / 成功用执行响应的数 | 10.2 / 10.4 |
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { mount, flushPromises, DOMWrapper } from '@vue/test-utils'

if (!(globalThis as any).ResizeObserver) {
  ;(globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

const { mockPost, mockMsgSuccess, mockMsgError, mockMsgWarning, mockConfirm } = vi.hoisted(() => ({
  mockPost: vi.fn(),
  mockMsgSuccess: vi.fn(),
  mockMsgError: vi.fn(),
  mockMsgWarning: vi.fn(),
  mockConfirm: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { post: mockPost } }))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return {
    ...actual,
    ElMessage: { success: mockMsgSuccess, error: mockMsgError, warning: mockMsgWarning, info: vi.fn() },
    ElMessageBox: { confirm: mockConfirm },
  }
})
import ElementPlus from 'element-plus'
import RefreshSourceDialog from '../RefreshSourceDialog.vue'

const ENTRY = 'xlsx/gt-d4-operating-revenue'
const WP = 'wp-uuid-1'
const PROJ = 'proj-uuid-1'

/** dry_run 响应：字段名与后端 `_plan_wire_form` 逐字一致。 */
function planWire(over: Record<string, any> = {}) {
  return {
    plan_digest: 'a'.repeat(64),
    store_row_count: 7,
    substrate_row_count: 5,
    expected_revision: 42,
    store_rows_by_table: { d4_rows: 7 },
    substrate_rows_by_table: { d4_rows: 5 },
    skipped_items: [],
    deltas: [
      { item_id: 'D4-2-rows', rows_added_count: 2, rows_deleted_count: 3, rows_updated_count: 4 },
      { item_id: 'D4-3-rows', rows_added_count: 1, rows_deleted_count: 1, rows_updated_count: 1 },
    ],
    ...over,
  }
}

function mk(props: Record<string, any> = {}) {
  const upstreamRefresh = vi.fn()
  const reload = vi.fn()
  const wrapper = mount(RefreshSourceDialog, {
    props: {
      modelValue: true,
      wpId: WP,
      projectId: PROJ,
      entryId: ENTRY,
      upstreamRefresh,
      reload,
      ...props,
    },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  /**
   * 🔴 `el-dialog` 带 `append-to-body` ⇒ 内容被 teleport 到 document.body，
   *    `wrapper.find()` 看不到它（首版就是这么错的：19 failed / "empty DOMWrapper"）。
   *    故一律经 document.body 查询，并包成 DOMWrapper 以便 .trigger()。
   */
  function q(testid: string): DOMWrapper<Element> {
    const el = document.body.querySelector(`[data-testid="${testid}"]`)
    if (!el) throw new Error(`未找到 [data-testid="${testid}"] —— 查询口径或渲染条件变了`)
    return new DOMWrapper(el)
  }
  function has(testid: string): boolean {
    return !!document.body.querySelector(`[data-testid="${testid}"]`)
  }
  mounted.push(wrapper)
  return { wrapper, upstreamRefresh, reload, q, has }
}

function httpErr(code: string) {
  return { response: { data: { detail: { error_code: code, message: '后端文案' } } } }
}

/** 本轮挂载过的 wrapper，afterEach 统一卸载。 */
const mounted: any[] = []

beforeEach(() => {
  vi.clearAllMocks()
  mockPost.mockReset()
  mockConfirm.mockReset()
})

/**
 * 🔴 必须逐例卸载并清空 document.body：`append-to-body` 把内容 teleport 到 body，
 *    不卸载则上一例的弹窗**留在 body 里**，`querySelector` 会取到**上一例**的节点
 *    （首版就是这么错的：禁用态断言拿到了另一例的文案）。
 */
afterEach(() => {
  while (mounted.length) {
    try { mounted.pop().unmount() } catch { /* 忽略卸载异常 */ }
  }
  document.body.innerHTML = ''
})

// ═══════════════════════════════════════════════════════════════════
// §1 交互路径（Task 12.1）
// ═══════════════════════════════════════════════════════════════════
describe('§1 交互路径', () => {
  it('打开即请求 dry_run，且恰好一次、body 为 {dry_run:true}', async () => {
    mockPost.mockResolvedValue({ data: planWire() })
    mk()
    await flushPromises()
    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body] = mockPost.mock.calls[0]
    expect(url).toContain('/adopt-substrate')
    expect(body).toEqual({ dry_run: true })
  })

  it('URL 含未转义的 entry_id（Starlette :path 接收，禁 percent-encode）', async () => {
    mockPost.mockResolvedValue({ data: planWire() })
    mk()
    await flushPromises()
    const url = mockPost.mock.calls[0][0] as string
    expect(url).toContain(ENTRY)
    expect(url).not.toContain('%2F')
  })

  it('恰 2 个可执行来源 + 恰 1 个说明项', async () => {
    mockPost.mockResolvedValue({ data: planWire() })
    const { q, has } = mk()
    await flushPromises()
    expect(has('rsd-opt-upstream')).toBe(true)
    expect(has('rsd-opt-overwrite')).toBe(true)
    const note = q('rsd-opt-note')
    expect(note.exists()).toBe(true)
    // 说明项必须**不是** button（不可选）
    expect(note.element.tagName.toLowerCase()).not.toBe('button')
  })

  it('🔴 点说明项零请求（不触发 materialize）', async () => {
    mockPost.mockResolvedValue({ data: planWire() })
    const { q, has } = mk()
    await flushPromises()
    mockPost.mockClear()
    await q('rsd-opt-note').trigger('click')
    await flushPromises()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('选第一项 ⇒ 走既有取数（upstreamRefresh），且不发 adopt 请求', async () => {
    mockPost.mockResolvedValue({ data: planWire() })
    const { q, upstreamRefresh } = mk()
    await flushPromises()
    mockPost.mockClear()
    await q('rsd-opt-upstream').trigger('click')
    await flushPromises()
    expect(upstreamRefresh).toHaveBeenCalledTimes(1)
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('🔴 二次确认取消 ⇒ 零写入（不发 dry_run:false）', async () => {
    mockPost.mockResolvedValue({ data: planWire() })
    mockConfirm.mockRejectedValue(new Error('cancel'))
    const { q, reload } = mk()
    await flushPromises()
    mockPost.mockClear()
    await q('rsd-opt-overwrite').trigger('click')
    await flushPromises()
    expect(mockConfirm).toHaveBeenCalledTimes(1)
    expect(mockPost).not.toHaveBeenCalled()
    expect(reload).not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════
// §2 Property 12：摘要数字与响应字段逐值相等（Task 12.2）
//
// 🔴 要害：前端**不得自行重算**。判据形态 = 让响应里的 rows_*_count 与清单长度
//    **故意不一致**，然后断言 UI 显示的是 count 字段而不是 length。
//    若实现改成 rows_added.length，本节必打红（这就是变异反证）。
// ═══════════════════════════════════════════════════════════════════
describe('§2 Property 12 摘要逐值相等', () => {
  it('两侧行数取自 store_row_count / substrate_row_count', async () => {
    mockPost.mockResolvedValue({ data: planWire({ store_row_count: 11, substrate_row_count: 3 }) })
    const { q, has } = mk()
    await flushPromises()
    const txt = q('rsd-summary').text()
    expect(txt).toContain('表单 11 行')
    expect(txt).toContain('在线编辑侧 3 行')
  })

  it('增删改条数 = 各 delta 的 rows_*_count 之和（逐值）', async () => {
    mockPost.mockResolvedValue({ data: planWire() })
    const { q, has } = mk()
    await flushPromises()
    const txt = q('rsd-summary').text()
    // 2+1=3 新增 / 3+1=4 删除 / 4+1=5 更新
    expect(txt).toContain('新增 3')
    expect(txt).toContain('删除 4')
    expect(txt).toContain('更新 5')
  })

  it('🔴 变异反证：count 字段与清单长度不一致时，UI 必须跟 count 而不是 length', async () => {
    // rows_added 清单长度 0，但后端给的 count 是 9 ⇒ 前端若自己 length 就会显示 0
    mockPost.mockResolvedValue({
      data: planWire({
        deltas: [
          {
            item_id: 'X',
            rows_added: [],
            rows_deleted: [],
            rows_updated: [],
            rows_added_count: 9,
            rows_deleted_count: 8,
            rows_updated_count: 7,
          },
        ],
      }),
    })
    const { q, has } = mk()
    await flushPromises()
    const txt = q('rsd-summary').text()
    expect(txt).toContain('新增 9')
    expect(txt).toContain('删除 8')
    expect(txt).toContain('更新 7')
    expect(txt).not.toContain('新增 0')
  })

  it('二次确认文案里的删除行数也取自 count（与摘要同源）', async () => {
    mockPost.mockResolvedValue({ data: planWire() })
    mockConfirm.mockRejectedValue(new Error('cancel'))
    const { q, has } = mk()
    await flushPromises()
    await q('rsd-opt-overwrite').trigger('click')
    await flushPromises()
    const msg = String(mockConfirm.mock.calls[0][0])
    expect(msg).toContain('4 行将被删除')
    expect(msg).toContain('3 行将被新增')
  })
})

// ═══════════════════════════════════════════════════════════════════
// §3 中文文案守卫（Task 12.3）
//
// 🔴 豁免白名单必须**可伪证**：不只存名字，还配「白名单无失效条目」检查 ——
//    名单里的每个词必须**真的出现在**被扫文本里，否则它是个失效条目（词改了/删了
//    而名单没跟着改），那样名单就成了「加一行就变绿」的后门。
// ═══════════════════════════════════════════════════════════════════
const SFC_PATH = resolve(__dirname, '../RefreshSourceDialog.vue')

/** 用户可见文本里允许出现的英文（技术术语）。每条都必须真的在文本里出现。 */
const ENGLISH_ALLOWLIST = ['OnlyOffice'] as const

/** 取 SFC 的 <template> 段里的**用户可见文本**：剥标签、属性、注释、插值。 */
function visibleTemplateText(): string {
  const sfc = readFileSync(SFC_PATH, 'utf-8')
  const m = /<template>([\s\S]*)<\/template>/.exec(sfc)
  if (!m) throw new Error('未取到 <template> 段 —— 扫描器失效')
  return m[1]
    .replace(/<!--[\s\S]*?-->/g, ' ')   // 注释不是用户可见文本
    .replace(/\{\{[\s\S]*?\}\}/g, ' ') // 插值是运行时值
    .replace(/<[^>]+>/g, ' ')           // 标签与属性（含 data-testid / class）
}

describe('§3 中文文案守卫', () => {
  it('扫描器真的取到了非空文本（反空转）', () => {
    const txt = visibleTemplateText()
    expect(txt.length).toBeGreaterThan(80)
    expect(txt).toContain('刷新本表')
  })

  it('用户可见文本无未豁免英文单词', () => {
    let txt = visibleTemplateText()
    for (const w of ENGLISH_ALLOWLIST) txt = txt.split(w).join(' ')
    const leftovers = txt.match(/[A-Za-z]{2,}/g) ?? []
    expect(leftovers).toEqual([])
  })

  it('🔴 白名单无失效条目：每个豁免词都必须真的出现在被扫文本里', () => {
    const txt = visibleTemplateText()
    const stale = ENGLISH_ALLOWLIST.filter((w) => !txt.includes(w))
    expect(stale).toEqual([])
  })

  it('🔴 变异反证：往白名单塞一个不存在的词 ⇒ 失效条目检查必须抓到', () => {
    const txt = visibleTemplateText()
    const polluted = [...ENGLISH_ALLOWLIST, 'ThisWordIsNotInTheTemplate']
    const stale = polluted.filter((w) => !txt.includes(w))
    expect(stale).toEqual(['ThisWordIsNotInTheTemplate'])
  })

  it('🔴 变异反证：扫描器对含未豁免英文的样本必须打红（否则它什么都没在扫）', () => {
    const sample = '这里有一个 Untranslated 词'
    let t2 = sample
    for (const w of ENGLISH_ALLOWLIST) t2 = t2.split(w).join(' ')
    expect((t2.match(/[A-Za-z]{2,}/g) ?? []).length).toBeGreaterThan(0)
  })

  it('三项标题均为中文且带序号', () => {
    const txt = visibleTemplateText()
    for (const s of ['① 以上游业务数据为准', '② 以在线编辑侧为准', '③ 以表单为准']) {
      expect(txt).toContain(s)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════
// §4 禁用态（Task 10.3 / Requirement 5.7）
// ═══════════════════════════════════════════════════════════════════
describe('§4 禁用态', () => {
  it('🔴 无 entry_id（未接双模式）⇒ 不发 dry_run、②禁用并就地说明', async () => {
    const { q, has } = mk({ entryId: null })
    await flushPromises()
    expect(mockPost).not.toHaveBeenCalled()
    const btn = q('rsd-opt-overwrite')
    expect(btn.attributes('disabled')).toBeDefined()
    expect(q('rsd-overwrite-blocked').text()).toContain('未接入在线编辑双模式')
  })

  it('dry_run 返回 adopt_substrate_not_published ⇒ ②禁用 + 原因就地显示', async () => {
    mockPost.mockRejectedValue(httpErr('adopt_substrate_not_published'))
    const { q, has } = mk()
    await flushPromises()
    expect(q('rsd-opt-overwrite').attributes('disabled')).toBeDefined()
    expect(q('rsd-overwrite-blocked').text()).toContain('尚无已发布底稿')
  })

  it('dry_run 返回 adopt_contract_required ⇒ ②禁用 + 原因就地显示', async () => {
    mockPost.mockRejectedValue(httpErr('adopt_contract_required'))
    const { q, has } = mk()
    await flushPromises()
    expect(q('rsd-opt-overwrite').attributes('disabled')).toBeDefined()
    expect(q('rsd-overwrite-blocked').text()).toContain('契约未就绪')
  })

  it('🔴 禁用态下点②不发任何请求（禁用不是只做样式）', async () => {
    mockPost.mockRejectedValue(httpErr('adopt_contract_required'))
    const { q, has } = mk()
    await flushPromises()
    mockPost.mockClear()
    await q('rsd-opt-overwrite').trigger('click')
    await flushPromises()
    expect(mockPost).not.toHaveBeenCalled()
    expect(mockConfirm).not.toHaveBeenCalled()
  })

  it('①在禁用②的场景下仍然可用（两项互不牵连）', async () => {
    mockPost.mockRejectedValue(httpErr('adopt_contract_required'))
    const { q, upstreamRefresh } = mk()
    await flushPromises()
    await q('rsd-opt-upstream').trigger('click')
    await flushPromises()
    expect(upstreamRefresh).toHaveBeenCalledTimes(1)
  })
})

// ═══════════════════════════════════════════════════════════════════
// §5 覆盖路径（Task 10.2 / 10.4）
// ═══════════════════════════════════════════════════════════════════
describe('§5 覆盖路径', () => {
  it('确认后请求体带 dry_run:false + plan_digest + expected_revision', async () => {
    mockPost.mockResolvedValueOnce({ data: planWire() })
    mockConfirm.mockResolvedValue(true)
    mockPost.mockResolvedValueOnce({ data: { changed_item_count: 2 } })
    const { q, has } = mk()
    await flushPromises()
    await q('rsd-opt-overwrite').trigger('click')
    await flushPromises()
    const body = mockPost.mock.calls[1][1] as any
    expect(body.dry_run).toBe(false)
    expect(body.plan_digest).toBe('a'.repeat(64))
    expect(body.expected_revision).toBe(42)
  })

  it('🔴 成功提示用执行响应的 changed_item_count，不复用 dry_run 的数', async () => {
    mockPost.mockResolvedValueOnce({ data: planWire() })
    mockConfirm.mockResolvedValue(true)
    // dry_run 摘要是 3/4/5；执行响应说只变了 1 个 item ⇒ 提示必须是 1
    mockPost.mockResolvedValueOnce({ data: { changed_item_count: 1 } })
    const { q, reload } = mk()
    await flushPromises()
    await q('rsd-opt-overwrite').trigger('click')
    await flushPromises()
    const msg = String(mockMsgSuccess.mock.calls[0][0])
    expect(msg).toContain('共变更 1 个数据项')
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('🔴 409 adopt_plan_digest_mismatch ⇒ 提示两侧已变化并**重取 dry_run**', async () => {
    mockPost.mockResolvedValueOnce({ data: planWire() })
    mockConfirm.mockResolvedValue(true)
    mockPost.mockRejectedValueOnce(httpErr('adopt_plan_digest_mismatch'))
    mockPost.mockResolvedValueOnce({ data: planWire({ store_row_count: 99 }) })
    const { q, reload } = mk()
    await flushPromises()
    await q('rsd-opt-overwrite').trigger('click')
    await flushPromises()
    expect(String(mockMsgWarning.mock.calls[0][0])).toContain('已变化')
    // 第 3 次调用 = 重取的 dry_run
    expect(mockPost).toHaveBeenCalledTimes(3)
    expect(mockPost.mock.calls[2][1]).toEqual({ dry_run: true })
    expect(reload).not.toHaveBeenCalled()
    expect(q('rsd-summary').text()).toContain('表单 99 行')
  })

  it('其它错误 ⇒ 报错且不 reload', async () => {
    mockPost.mockResolvedValueOnce({ data: planWire() })
    mockConfirm.mockResolvedValue(true)
    mockPost.mockRejectedValueOnce(httpErr('adopt_store_payload_unreadable'))
    const { q, reload } = mk()
    await flushPromises()
    await q('rsd-opt-overwrite').trigger('click')
    await flushPromises()
    expect(mockMsgError).toHaveBeenCalled()
    expect(reload).not.toHaveBeenCalled()
  })
})
