/**
 * 公式引用校验问题 → 提示文案（spec formula-fetch-followup-defect-closure 7.2 浏览器实测发现）。
 *
 * 原状（逐条可打红）：后端逐引用问题是 `{ref, uri, status, reason?, message, target?}`，原因在 `message`；
 * * 全局拦截器 / handleApiError / formulaErrorText 只取 `detail.message` ⇒ 只剩「公式含悬空引用，拒绝保存」，
 *   底稿公式的 422 没有 message ⇒ 全局提示是整段 JSON、handleApiError 是「请求参数有误」；
 * * 附注公式弹窗只列引用；底稿公式面板把问题对象拼成「[object Object]」（既有用例用字符串问题，与真实契约不符）。
 * 夹具按后端真实形状写死；契约用例直接读后端源码，确认「原因在 message」仍成立。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const { elError, elWarning, elNotification } = vi.hoisted(() => ({
  elError: vi.fn(), elWarning: vi.fn(), elNotification: vi.fn(),
}))
vi.mock('element-plus', () => ({
  ElMessage: { error: elError, warning: elWarning, success: vi.fn(), info: vi.fn() },
  ElNotification: elNotification,
}))

import http from '@/utils/http'
import { handleApiError } from '@/utils/errorHandler'
import { formulaErrorText } from '@/composables/formula/useFormulaSettings'
import { formatRefIssue, formatRefIssues, refIssueDetailText } from '@/utils/formulaRefIssues'

/** `acnr/formula_validation._make_wp_issue` 的真实形状 */
const WP_ISSUE = {
  ref: "WP('X9','X9-1','Z1')", uri: 'wp://X9/X9-1#Z1', status: 'not_found', reason: 'not_found',
  message: '引用地址 wp://X9/X9-1#Z1 在当前项目中不存在',
}
/** `address_registry.validate_formula_refs` + 附注公式保存补的 `target` */
const NOTE_ISSUE = {
  ref: "NOTE('货币资金','合计','期末')", uri: 'note://货币资金/合计#期末', status: 'not_found',
  message: '本年度（2025）附注没有章节 货币资金（第一参须是章节编号，如「五、1」，不是标题）', target: '合计.期末',
}
const NOTE_LINE = "【合计.期末】NOTE('货币资金','合计','期末')：本年度（2025）附注没有章节 货币资金（第一参须是章节编号，如「五、1」，不是标题）"
const WP_LINE = "WP('X9','X9-1','Z1')：引用地址 wp://X9/X9-1#Z1 在当前项目中不存在"

const dangling = { error_code: 'FORMULA_DANGLING_REFS', message: '公式含悬空引用，拒绝保存', issues: [NOTE_ISSUE, WP_ISSUE] }
/** 底稿公式保存（`wp_formula._formula_issue_error_code`）：没有 message */
const refNotFound = { error_code: 'FORMULA_REF_NOT_FOUND', issues: [WP_ISSUE] }
const err = (status: number, detail: unknown) => ({ response: { status, headers: {}, data: { detail } } })

function shown(): string {
  return [...elError.mock.calls, ...elWarning.mock.calls].map((c) => String(c[0])).join(' | ')
}

describe('formatRefIssue / formatRefIssues', () => {
  it('原因取 message，不取状态码；带目标单元格时加前缀', () => {
    expect(formatRefIssue(WP_ISSUE)).toBe(WP_LINE)
    expect(formatRefIssue(NOTE_ISSUE)).toBe(NOTE_LINE)
    expect(formatRefIssue(WP_ISSUE)).not.toContain('not_found')
  })

  it('字符串问题原样；只有引用或只有原因也能出字；无内容为空串', () => {
    expect(formatRefIssue(" TB('9999','期末余额') 引用不存在 ")).toBe("TB('9999','期末余额') 引用不存在")
    expect(formatRefIssue({ ref: "TB('9999')" })).toBe("TB('9999')")
    expect(formatRefIssue({ message: '校验请求失败' })).toBe('校验请求失败')
    expect(formatRefIssue({ status: 'not_found' })).toBe('')
    expect(formatRefIssue(null)).toBe('')
  })

  it('清单去重、「；」连接；不是数组为空串', () => {
    expect(formatRefIssues([WP_ISSUE, WP_ISSUE, NOTE_ISSUE, {}])).toBe(`${WP_LINE}；${NOTE_LINE}`)
    expect(formatRefIssues(undefined)).toBe('')
  })

  it('只认引用校验的错误码：其他 422 不改写', () => {
    expect(refIssueDetailText(dangling)).toBe(`公式含悬空引用，拒绝保存：${NOTE_LINE}；${WP_LINE}`)
    expect(refIssueDetailText(refNotFound)).toBe(`公式引用无法解析，未保存：${WP_LINE}`)
    expect(refIssueDetailText({ error_code: 'FORMULA_SOURCE_SCOPE_INVALID', issues: [WP_ISSUE] })).toBe('')
    expect(refIssueDetailText('字符串')).toBe('')
  })
})

describe('三条错误文案通路都列出「引用：原因」', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
  })

  it('handleApiError：422 悬空引用列原因；底稿公式 422（无 message）不再是「请求参数有误」', () => {
    handleApiError(err(422, dangling), '保存失败')
    expect(shown()).toContain(NOTE_LINE)
    expect(shown()).toContain(WP_LINE)
    vi.clearAllMocks()
    handleApiError(err(422, refNotFound), '保存失败')
    expect(shown()).toContain(WP_LINE)
    expect(shown()).not.toContain('请求参数有误')
  })

  it('formulaErrorText：422 悬空引用列原因', () => {
    const text = formulaErrorText(err(422, dangling), '保存失败')
    expect(text).toContain(NOTE_LINE)
    expect(text).toContain(WP_LINE)
  })

  it('全局拦截器提示：列原因，不再把整段 JSON 甩给用户', async () => {
    const rejected = (http.interceptors.response as any).handlers?.[0]?.rejected
    expect(typeof rejected, '拦截器 rejected handler 必须存在，否则这条判据是空转').toBe('function')
    const error: any = {
      isAxiosError: true, message: 'Request failed with status code 422',
      config: { url: '/api/workpapers/w1/formulas', method: 'put' },
      response: { status: 422, headers: {}, data: { code: 422, message: refNotFound } },
    }
    await expect(rejected(error)).rejects.toBe(error)
    expect(elWarning).toHaveBeenCalledTimes(1)
    expect(String(elWarning.mock.calls[0][0])).toContain(WP_LINE)
    expect(String(elWarning.mock.calls[0][0])).not.toContain('"error_code"')
  })
})

/** 含 `'status': 'not_found'` 的字典字面量（向上到以 `{` 结尾的行、向下到以 `}` 开头的行；f-string 里的花括号不影响） */
function notFoundIssueBlocks(src: string): string[] {
  const lines = src.split('\n')
  const blocks: string[] = []
  lines.forEach((line, i) => {
    if (!/['"]status['"]\s*:\s*['"]not_found['"]/.test(line)) return
    let s = i
    while (s > 0 && !/\{\s*$/.test(lines[s])) s--
    let e = i
    while (e < lines.length - 1 && !/^\s*\}/.test(lines[e])) e++
    blocks.push(lines.slice(s, e + 1).join('\n'))
  })
  return blocks
}

describe('契约：后端逐引用问题的原因在 message', () => {
  const BACKEND = resolve(__dirname, '../../../../../backend/app/services')
  it.each(['acnr/formula_validation.py', 'address_registry.py'])('%s 里每个 not_found 问题都带 ref / message 键', (rel) => {
    const blocks = notFoundIssueBlocks(readFileSync(resolve(BACKEND, rel), 'utf-8'))
    expect(blocks.length, `${rel} 没找到 not_found 问题字面量：判据空转`).toBeGreaterThan(0)
    for (const b of blocks) {
      expect(b, b).toMatch(/['"]ref['"]\s*:/)
      expect(b, b).toMatch(/['"]message['"]\s*:/)
    }
  })
})
