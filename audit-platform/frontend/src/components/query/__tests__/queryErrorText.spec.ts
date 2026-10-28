/**
 * queryErrorText.spec.ts — 请求失败 → 中文原因 + 追踪号（advanced-query-linkage-closure 任务 27；R11.1、R11.2，AQ-29）
 *
 * 错误对象按生产形状构造：后端 http_exception_handler 把 detail 放进信封 message，拦截器 `normaliseErrorEnvelope`
 * 补出 detail（与 CustomQueryTabRejection.spec 同口径）；422 请求模型校验保持 FastAPI 的 detail 数组。
 */
import { describe, it, expect } from 'vitest'
import { normaliseErrorEnvelope } from '@/utils/http'
import { NETWORK_ERROR_TEXT, describeQueryError, queryErrorToast } from '../queryErrorText'

function axiosError(status: number, body: unknown, headers: Record<string, string> = {}) {
  const response = { status, data: body, headers }
  normaliseErrorEnvelope(response)
  return Object.assign(new Error(`Request failed with status code ${status}`), { isAxiosError: true, response })
}

describe('describeQueryError — 422 请求模型校验译成中文（R11.2）', () => {
  it('pydantic 英文明细 → 「字段中文名 + 规则」，不出现英文', () => {
    const d = describeQueryError(axiosError(422, { detail: [
      { type: 'less_than_equal', loc: ['body', 'limit'], msg: 'Input should be less than or equal to 1000', ctx: { le: 1000 } },
      { type: 'greater_than_equal', loc: ['body', 'year'], msg: 'Input should be greater than or equal to 2000', ctx: { ge: 2000 } },
      { type: 'literal_error', loc: ['body', 'filter_logic'], msg: "Input should be 'and' or 'or'", ctx: { expected: "'and' or 'or'" } },
      { type: 'missing', loc: ['body', 'filters', 0, 'op'], msg: 'Field required' },
    ] }))
    expect(d.message).toBe("参数校验失败：每页行数不能大于 1000；审计年度不能小于 2000；条件逻辑取值无效，可选：'and'、'or'；筛选 · 第 1 项 · 操作符为必填项")
    expect(d.message).not.toMatch(/Input should|Field required/)
    expect(d.status).toBe(422)
  })

  it('结果列字段名用列标签中文；未知类型给「取值无效」', () => {
    const d = describeQueryError(axiosError(422, { detail: [
      { type: 'string_too_long', loc: ['body', 'conditions', 2, 'value'], msg: 'String should have at most 200 characters', ctx: { max_length: 200 } },
      { type: 'something_new', loc: ['body', 'voucher_date'], msg: 'Value error, bad' },
    ] }))
    expect(d.message).toBe('参数校验失败：条件 · 第 3 项 · 值长度不能超过 200 个字符；凭证日期取值无效')
  })

  it('acnr 的自定义中文类型原样显示，与翻译项并列', () => {
    const d = describeQueryError(axiosError(422, { detail: [
      { type: 'unknown_field', loc: ['body', 'foo'], msg: '请求包含未声明的字段：foo' },
      { type: 'too_long', loc: ['body', 'columns'], msg: 'List should have at most 60 items', ctx: { max_length: 60 } },
    ] }))
    expect(d.message).toBe('请求包含未声明的字段：foo；参数校验失败：显示列最多 60 项')
  })
})

describe('describeQueryError — 业务拒绝显示后端原因（AQ-29）', () => {
  it('403 人员表：显示后端中文原因与错误码（不是笼统的「无权」）', () => {
    const d = describeQueryError(axiosError(403, { code: 403, message: {
      error_code: 'TABLE_ROLE_FORBIDDEN', message: '表「人员」仅对管理员、合伙人开放', table: 'staff_members',
    } }, { 'x-request-id': 'rid-403' }))
    expect(d).toEqual({ message: '表「人员」仅对管理员、合伙人开放', status: 403, errorCode: 'TABLE_ROLE_FORBIDDEN', correlationId: 'rid-403' })
  })

  it('422 单元格取值被拒：「message：引用：原因；…」（与 acnr 同口径）', () => {
    const d = describeQueryError(axiosError(422, { code: 422, message: {
      error_code: 'ACNR_TARGETS_REJECTED', message: '所选单元格中有 2 项无法取值，未执行查询',
      issues: [{ ref: 'E1/E1-14', message: '所选为整张表' }, { ref: 'tb:1001', message: '不支持取值' }],
    } }))
    expect(d.message).toBe('所选单元格中有 2 项无法取值，未执行查询：E1/E1-14：所选为整张表；tb:1001：不支持取值')
  })

  it('429 导出闸原样显示后端文案', () => {
    const d = describeQueryError(axiosError(429, { code: 429, message: { error_code: 'EXPORT_BUSY', message: '已有导出在进行，请稍后再试' } }))
    expect(d.message).toBe('已有导出在进行，请稍后再试')
    expect(d.errorCode).toBe('EXPORT_BUSY')
  })

  it('未经拦截器的错误对象：信封 message 为对象时取其 message / error_code', () => {
    const raw = Object.assign(new Error('x'), { response: { status: 400, data: { code: 400, message: {
      error_code: 'UNKNOWN_FILTER_KEY', message: '未登记的筛选键：foo',
    } } } })
    expect(describeQueryError(raw)).toMatchObject({ message: '未登记的筛选键：foo', errorCode: 'UNKNOWN_FILTER_KEY' })
  })

  it('starlette 英文缺省文案译成中文', () => {
    expect(describeQueryError(axiosError(404, { detail: 'Not Found' })).message).toBe('请求的数据不存在')
  })
})

describe('describeQueryError — 追踪号与兜底（R11.1）', () => {
  it('500：detail.correlation_id 优先，其次响应头 X-Correlation-ID / X-Request-ID', () => {
    const body = { code: 500, message: { error_code: 'INTERNAL_ERROR', message: '查询执行失败，请稍后重试；如持续失败请提供追踪号联系管理员', correlation_id: 'c-1' } }
    expect(describeQueryError(axiosError(500, body, { 'x-correlation-id': 'c-2', 'x-request-id': 'r-1' })).correlationId).toBe('c-1')
    expect(describeQueryError(axiosError(500, {}, { 'x-correlation-id': 'c-2', 'x-request-id': 'r-1' })).correlationId).toBe('c-2')
    const viaGetter = describeQueryError({ response: { status: 502, data: {}, headers: { get: (n: string) => (n.toLowerCase() === 'x-request-id' ? 'r-9' : undefined) } } })
    expect(viaGetter).toEqual({ message: '服务暂时不可用，请稍后重试', status: 502, correlationId: 'r-9' })
  })

  it('没有可读原因时按状态码给中文，绝不出现 axios 英文 message', () => {
    const d = describeQueryError(axiosError(500, {}))
    expect(d.message).toBe('服务器内部错误，请稍后重试')
    expect(d.message).not.toContain('Request failed')
    expect(describeQueryError(axiosError(418, {})).message).toBe('请求失败，请稍后重试')
  })

  it('没有响应：网络提示；被取消：取消提示', () => {
    expect(describeQueryError(new Error('Network Error'))).toEqual({ message: NETWORK_ERROR_TEXT, status: 0 })
    expect(describeQueryError(Object.assign(new Error('canceled'), { name: 'CanceledError', code: 'ERR_CANCELED' })).message).toBe('请求已取消')
    expect(describeQueryError(undefined).message).toBe(NETWORK_ERROR_TEXT)
  })

  it('blob 错误体（未先读成 JSON）按状态码兜底，不抛错', () => {
    const e = Object.assign(new Error('x'), { response: { status: 400, data: new Blob(['{}']), headers: {} } })
    expect(describeQueryError(e).message).toBe('请求参数有误')
  })
})

describe('queryErrorToast — 一次性提示文案', () => {
  it('参数类（4xx）不附追踪号；服务器错误（5xx）附追踪号', () => {
    expect(queryErrorToast('查询执行', { message: '表「人员」仅对管理员、合伙人开放', status: 403, correlationId: 'r-1' }))
      .toBe('查询执行：表「人员」仅对管理员、合伙人开放')
    expect(queryErrorToast('导出 Excel', { message: '导出失败，请稍后重试', status: 500, correlationId: 'c-1' }))
      .toBe('导出 Excel：导出失败，请稍后重试（追踪号 c-1）')
  })
})
