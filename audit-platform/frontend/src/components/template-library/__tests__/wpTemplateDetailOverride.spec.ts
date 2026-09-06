/**
 * WpTemplateDetail 的模板覆盖层 UI 判据。
 *
 * spec: .kiro/specs/excel-template-override-layer-and-onlyoffice-template-editor/
 * Requirements: 5.1, 5.2, 5.3, 5.5
 * Properties: 20, 21
 *
 * ═══ 判据形态 ═══
 *
 * 两层：
 *
 * 1. **渲染形态**（真 mount）—— 门控按后端字段生效、置灰处**说明原因**而不是只不可点、
 *    上传替换对置灰的 127 份仍然可用。
 * 2. **源码结构**（读 .vue 源码）—— Property 21 的「前端不含据文件名/路径推断来源的逻辑」
 *    只能这么验：mount 测不出「有没有第二份优先级规则」。
 *
 * element-plus 未在测试里全局注册，`el-button` 会渲染成同名自定义元素。这**不影响判据**
 * ——`data-testid` 与 `disabled` 属性照样落在 DOM 上，而且测的是本组件的门控逻辑本身，
 * 不掺 el-button 的实现细节。
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const _dir = dirname(fileURLToPath(import.meta.url))
const COMPONENT_PATH = resolve(_dir, '../WpTemplateDetail.vue')
const COMPONENT_SOURCE = readFileSync(COMPONENT_PATH, 'utf-8')

/**
 * 🔴 template 块必须切到 `<script` 为止，**不能**用 `indexOf('</template>')`。
 *
 * 组件里有嵌套的 `<template #default="{ row }">`（el-table-column 的作用域插槽），
 * 第一个 `</template>` 出现在文件中段 —— 用它切会把后半个 template 全丢掉，
 * 于是「file input 存在」这类判据在一个被截断的字符串上恒假。初版就是这么红的。
 */
const TEMPLATE_BLOCK = COMPONENT_SOURCE.slice(0, COMPONENT_SOURCE.indexOf('<script'))
const SCRIPT_BLOCK = COMPONENT_SOURCE.slice(COMPONENT_SOURCE.indexOf('<script'))

// ─── mock 依赖 ──────────────────────────────────────────────────────────────

const apiGet = vi.fn()
const apiPost = vi.fn()
const apiDelete = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: unknown[]) => apiGet(...args),
    post: (...args: unknown[]) => apiPost(...args),
    delete: (...args: unknown[]) => apiDelete(...args),
    put: vi.fn(),
    patch: vi.fn(),
    download: vi.fn(),
  },
  apiProxy: { get: (...args: unknown[]) => apiGet(...args) },
}))

vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

// 🔴 只替换 ElMessage / ElMessageBox，其余保留真实实现（`importOriginal`）。
//    整体 mock 掉 element-plus 会让 `el-table-column` 的作用域插槽拿不到组件定义，
//    渲染时报 `Cannot destructure property 'row'` —— mount 全挂。
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
    ElMessageBox: { confirm: vi.fn(async () => 'confirm') },
  }
})

import ElementPlus from 'element-plus'

import WpTemplateDetail from '../WpTemplateDetail.vue'

/** 后端 `GET /{wp_code}/resolution` 的形态。 */
function resolutionFixture(over: Record<string, unknown> = {}) {
  return {
    wp_code: 'K11',
    origin: 'override:firm_default',
    // 🔴 刻意用一个前端不可能自己拼出来的标签 —— 若断言能命中它，
    //    就证明来源展示确实来自后端（Property 21），不是前端据扩展名/路径推断的。
    origin_label: '事务所覆盖·后端下发标记#7',
    path_name: 'current.xlsx',
    extension: '.xlsx',
    sha256: 'a'.repeat(64),
    version_id: 'deadbeefcafe1234',
    editable_in_browser: true,
    not_editable_reason: null,
    ...over,
  }
}

function installApi(resolution: Record<string, unknown> | null) {
  apiGet.mockReset()
  apiGet.mockImplementation(async (url: string) => {
    if (url.includes('/resolution')) {
      if (resolution === null) throw new Error('404')
      return resolution
    }
    if (url.includes('/wp-template-overrides/') && url.endsWith('/versions')) {
      return [
        {
          version_id: 'ver-current-0001', wp_code: 'K11',
          authoritative_stem: 'K11 资产减值损失', scope: 'firm_default',
          scope_label: '事务所', sha256: 'b'.repeat(64), is_current: true,
          parent_version_id: 'ver-old-0001', created_by: null, created_at: null,
        },
        {
          version_id: 'ver-old-0001', wp_code: 'K11',
          authoritative_stem: 'K11 资产减值损失', scope: 'firm_default',
          scope_label: '事务所', sha256: 'c'.repeat(64), is_current: false,
          parent_version_id: null, created_by: null, created_at: null,
        },
      ]
    }
    if (url.includes('prefill-formulas')) return { cells: [] }
    if (url.includes('cross-wp-references')) return { references: [] }
    return {}
  })
}

async function mountDetail() {
  const wrapper = mount(WpTemplateDetail, {
    props: { wpCode: 'K11', projectId: 'p-1' },
    global: {
      plugins: [ElementPlus],
      stubs: {
        TemplateLibraryButton: true,
        GtFormulaPresetDialog: true,
      },
    },
    attachTo: document.body,
  })
  await vi.waitFor(() => {
    expect(wrapper.find('[data-testid="wpd-override-card"]').exists()).toBe(true)
  })
  // 让 loadAll 的 await 链跑完
  await Promise.resolve()
  await wrapper.vm.$nextTick()
  await Promise.resolve()
  await wrapper.vm.$nextTick()
  return wrapper
}

/**
 * 🔴 读**真实 DOM 属性**而不是 `attributes('disabled')`。
 *
 * element-plus 的 `el-button` 在禁用时渲染成 `disabled=""` —— 空字符串是 **falsy**，
 * 于是 `expect(attributes('disabled')).toBeTruthy()` 在按钮确实被禁用时也失败。
 * 初版四条置灰判据全红在这个坑上。
 */
function isDisabled(el: Element): boolean {
  return (el as HTMLButtonElement).disabled === true
}

beforeEach(() => {
  apiPost.mockReset()
  apiDelete.mockReset()
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 20 —— 编辑入口按格式门控
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 20：编辑入口按格式门控', () => {
  it('卡片、编辑入口、上传替换、版本历史四者都在（入口挂在既有界面，不新造孤岛）', async () => {
    installApi(resolutionFixture())
    const wrapper = await mountDetail()
    expect(wrapper.find('[data-testid="wpd-override-card"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="wpd-override-edit"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="wpd-override-upload"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="wpd-override-history"]').exists()).toBe(true)
  })

  it('xlsx：在线编辑可用', async () => {
    installApi(resolutionFixture({ extension: '.xlsx', editable_in_browser: true }))
    const wrapper = await mountDetail()
    const btn = wrapper.find('[data-testid="wpd-override-edit"]')
    expect(isDisabled(btn.element)).toBe(false)
    // 可编辑时不显示置灰原因
    expect(wrapper.find('[data-testid="wpd-override-reason"]').exists()).toBe(false)
  })

  it.each([
    ['.docx', 'Word 模板的在线编辑是另一条路（结构化 SDT），本功能只做 Excel'],
    ['.doc', 'Word 97-2003 二进制格式，非 OOXML'],
    ['.xls', 'Excel 97-2003 二进制格式，非 OOXML'],
    ['.xlsm', '含 VBA 宏（vbaProject.bin），OnlyOffice 往返是否保留宏未取证，暂不开放在线编辑'],
  ])('%s：在线编辑置灰，且**说明原因**（不是只不可点）', async (ext, reason) => {
    installApi(resolutionFixture({
      extension: ext, editable_in_browser: false, not_editable_reason: reason,
    }))
    const wrapper = await mountDetail()

    const btn = wrapper.find('[data-testid="wpd-override-edit"]')
    expect(isDisabled(btn.element)).toBe(true)

    const reasonEl = wrapper.find('[data-testid="wpd-override-reason"]')
    expect(reasonEl.exists()).toBe(true)
    expect(reasonEl.text()).toContain(reason)
  })

  it('置灰的格式仍可「上传替换」—— 476/476 都能产生覆盖版本（Requirement 7.2）', async () => {
    installApi(resolutionFixture({
      extension: '.docx', editable_in_browser: false, not_editable_reason: '仅 Excel 可在线编辑',
    }))
    const wrapper = await mountDetail()
    const upload = wrapper.find('[data-testid="wpd-override-upload"]')
    expect(upload.exists()).toBe(true)
    expect(isDisabled(upload.element)).toBe(false)
  })

  it('模板库里没有该 wp_code（后端 404）时不崩，来源显示为空占位', async () => {
    installApi(null)
    const wrapper = await mountDetail()
    expect(wrapper.find('[data-testid="wpd-override-card"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="wpd-override-origin"]').exists()).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 21 —— 来源与版本号取自后端，前端不推断
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 21：来源与版本号取自后端', () => {
  it('来源标签逐字等于后端 origin_label', async () => {
    const fixture = resolutionFixture()
    installApi(fixture)
    const wrapper = await mountDetail()
    const tag = wrapper.find('[data-testid="wpd-override-origin"]')
    expect(tag.exists()).toBe(true)
    expect(tag.text()).toBe(fixture.origin_label as string)
  })

  it('权威模板时显示「未覆盖」而不是编造一个版本号', async () => {
    installApi(resolutionFixture({
      origin: 'authoritative', origin_label: '权威模板', version_id: null,
      path_name: 'K11 资产减值损失.xlsx',
    }))
    const wrapper = await mountDetail()
    const card = wrapper.find('[data-testid="wpd-override-card"]')
    expect(card.text()).toContain('未覆盖')
  })

  it('🔴 源码里不含前端自己的格式白名单 —— 门控只能来自后端字段', () => {
    const script = SCRIPT_BLOCK

    // 门控的唯一来源
    expect(script).toContain('editable_in_browser')

    // 不得出现前端侧的可编辑格式白名单。注意本组件里已有的 `OFFICE_EXTS`
    // 是**预览**用的（与覆盖层无关），故按覆盖层相关的命名来判。
    const forbidden = [
      /EDITABLE_FORMATS/,
      /overrideEditable\s*=\s*computed\([^)]*extension/s,
      /overrideEditable[\s\S]{0,200}?\.endsWith\(/,
      /overrideEditable[\s\S]{0,200}?\bincludes\(\s*['"]xlsx/,
    ]
    for (const pattern of forbidden) {
      expect(script).not.toMatch(pattern)
    }
  })

  it('🔴 覆盖层的门控计算里不出现路径/文件名推断', () => {
    const script = SCRIPT_BLOCK
    const start = script.indexOf('const overrideEditable')
    expect(start).toBeGreaterThan(-1)
    const block = script.slice(start, start + 300)
    expect(block).toContain('editable_in_browser')
    expect(block).not.toContain('path_name')
    expect(block).not.toContain('extension')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 渲染形态三要素（遍历 + 门控 + 嵌套）—— 平台 UI 判据铁律
// ═══════════════════════════════════════════════════════════════════════════

describe('渲染形态三要素', () => {
  it('版本历史是**遍历**渲染的，且行数等于后端返回条数', async () => {
    installApi(resolutionFixture())
    const wrapper = await mountDetail()
    await wrapper.find('[data-testid="wpd-override-history"]').trigger('click')
    await vi.waitFor(() => {
      expect(apiGet).toHaveBeenCalledWith(
        expect.stringContaining('/wp-template-overrides/K11/versions'),
      )
    })
    const table = wrapper.find('el-table, .el-table')
    expect(table.exists()).toBe(true)
  })

  it('门控与置灰原因是**同一个**条件的两面（不会出现可编辑却显示原因）', () => {
    const template = TEMPLATE_BLOCK
    // 门控
    expect(template).toContain(':disabled="!overrideEditable"')
    // 置灰原因块由 `!overrideEditable` 门控，且要求 resolution 已加载
    expect(template).toMatch(
      /v-if="overrideResolution\s*&&\s*!overrideEditable"/,
    )
  })

  it('上传替换的 file input 存在且不带 accept 白名单（扩展名校验按后端字段做）', () => {
    const template = TEMPLATE_BLOCK
    expect(template).toContain('data-testid="wpd-override-file-input"')
    // accept 写死格式表就是第二份白名单；扩展名一致性由 overrideResolution.extension 判
    const inputBlock = template.slice(
      template.indexOf('wpd-override-file-input') - 200,
      template.indexOf('wpd-override-file-input') + 200,
    )
    expect(inputBlock).not.toMatch(/accept="[^"]*xlsx/)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 20 续 —— 打印设置变化提示（上传替换路径）
//
// 后端 `SaveResultOut.page_setup_changes` 若无人消费就是 additive 死代码。
// 这几条锁住"真被读了、真提示了、属性名是中文"。
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 20：打印设置变化提示', () => {
  /** 触发一次上传替换，返回 ElMessage mock。 */
  async function uploadWith(pageSetupChanges: unknown) {
    installApi(resolutionFixture())
    apiPost.mockReset()
    apiPost.mockResolvedValue({ data: { page_setup_changes: pageSetupChanges } })
    // 🔴 mock 的调用记录跨用例累积（vi.mock 工厂只跑一次）⇒ 必须逐例清零，
    //    否则「无差异时不提示」会读到上一例留下的调用而假红。
    const { ElMessage: _msg } = await import('element-plus')
    ;(_msg.warning as unknown as ReturnType<typeof vi.fn>).mockClear()

    const wrapper = await mountDetail()
    const input = wrapper.find('[data-testid="wpd-override-file-input"]')
    const file = new File([new Uint8Array([1, 2, 3])], 'K11 资产减值损失.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    Object.defineProperty(input.element, 'files', { value: [file], writable: false })
    await input.trigger('change')
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalled())
    const { ElMessage } = await import('element-plus')
    return ElMessage as unknown as { warning: ReturnType<typeof vi.fn> }
  }

  it('🔴 后端报出差异时**真的**提示（响应体被消费，不是丢掉）', async () => {
    const msg = await uploadWith([
      { sheet_part: 'xl/worksheets/sheet1.xml', attribute: 'orientation',
        before: 'portrait', after: 'landscape' },
    ])
    await vi.waitFor(() => expect(msg.warning).toHaveBeenCalled())
    const text = String(msg.warning.mock.calls.at(-1)?.[0] ?? '')
    expect(text).toContain('打印设置')
    expect(text).toContain('portrait')
    expect(text).toContain('landscape')
  })

  it('属性名显示中文而不是英文字段名（UI 全中文化）', async () => {
    const msg = await uploadWith([
      { sheet_part: 'xl/worksheets/sheet1.xml', attribute: 'paperSize',
        before: '9', after: '8' },
    ])
    await vi.waitFor(() => expect(msg.warning).toHaveBeenCalled())
    const text = String(msg.warning.mock.calls.at(-1)?.[0] ?? '')
    expect(text).toContain('纸张')
    expect(text).not.toContain('paperSize')
  })

  it('无差异（空数组）时不打扰用户', async () => {
    const msg = await uploadWith([])
    // 成功提示走 success，warning 不该被调
    expect(msg.warning).not.toHaveBeenCalled()
  })

  it('比对失败时提示"请自行核对"，不谎报等价', async () => {
    const msg = await uploadWith([
      { sheet_part: '<比对失败>', attribute: 'BadZipFile', before: 'boom', after: '' },
    ])
    await vi.waitFor(() => expect(msg.warning).toHaveBeenCalled())
    const text = String(msg.warning.mock.calls.at(-1)?.[0] ?? '')
    expect(text).toContain('核对')
    expect(text).not.toContain('BadZipFile')
  })

  it('差异过多时截断显示并给出总数（不刷屏）', async () => {
    const many = Array.from({ length: 7 }, (_, i) => ({
      sheet_part: `xl/worksheets/sheet${i + 1}.xml`,
      attribute: 'scale', before: '100', after: String(50 + i),
    }))
    const msg = await uploadWith(many)
    await vi.waitFor(() => expect(msg.warning).toHaveBeenCalled())
    const text = String(msg.warning.mock.calls.at(-1)?.[0] ?? '')
    expect(text).toContain('7')
    // 只展开前 3 条
    expect(text.match(/缩放/g)?.length).toBe(3)
  })
})
