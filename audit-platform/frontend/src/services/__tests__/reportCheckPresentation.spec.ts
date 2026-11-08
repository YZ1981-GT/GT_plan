import { describe, expect, it, vi } from 'vitest'
vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
import { mapReportConsistencyCheck } from '@/services/auditPlatformApi'
import { getReportBalancePresentation, getReportCheckPresentation, reportCheckValueText, reportChecksToCsv } from '@/services/reportCheckPresentation'

// 全部使用合成响应，经真实 mapper 与展示实现，不访问接口。
describe('报表审核传输与五态展示', () => {
  it.each([
    ['passed', 'passed'], ['failed', 'failed'], ['not_executed', 'not_executed'],
    ['not_applicable', 'not_applicable'], ['error', 'error'],
    [undefined, 'error'], [null, 'error'], ['', 'error'], ['running', 'error'], ['future_state', 'error'],
  ])('自有状态 %s 优先于 passed=true，呈现为 %s', (status, expected) => {
    const result = mapReportConsistencyCheck({ checks: [{ status, passed: true }] })
    const check = result.checks[0]
    expect(Object.prototype.hasOwnProperty.call(check, 'status')).toBe(true)
    expect(check.status).toBe(status)
    expect(getReportCheckPresentation(check).status).toBe(expected)
  })

  it.each([true, false, 'true', 'false', 0, 1, null, undefined])('旧布尔字段只接受真 boolean：%s', passed => {
    const check = mapReportConsistencyCheck({ checks: [{ passed }] }).checks[0]
    expect(Object.prototype.hasOwnProperty.call(check, 'status')).toBe(false)
    expect(Object.prototype.hasOwnProperty.call(check, 'passed')).toBe(typeof passed === 'boolean')
    expect(getReportCheckPresentation(check).status).toBe(typeof passed === 'boolean' ? (passed ? 'passed' : 'failed') : 'error')
  })

  it('缺少 status 与 passed 时明确为错误，不制造失败或通过', () => {
    const check = mapReportConsistencyCheck({ checks: [{}] }).checks[0]
    expect(getReportCheckPresentation(check)).toMatchObject({ status: 'error', reason: '检查状态缺失或为空' })
  })

  it('原因去重，保留未知状态说明、后端原因与严重度', () => {
    const check = mapReportConsistencyCheck({ checks: [{ status: 'running', reason: ' 数据未就绪 ', message: '数据未就绪', severity: 'future' }] }).checks[0]
    expect(getReportCheckPresentation(check)).toEqual({
      status: 'error', label: '错误', reason: '未知检查状态：running；数据未就绪', severityLabel: '未识别：future', isHint: false,
    })
  })
})

describe('明细计数及数值保真', () => {
  it('五态按逐项事实统计，提示性失败不改 passed，也不混为阻断失败', () => {
    const result = mapReportConsistencyCheck({
      total: 999, consistent: true, failed_count: 1, hint_count: 2,
      checks: [
        { status: 'passed' }, { status: 'failed', severity: 'error' },
        { status: 'failed', severity: 'warning' }, { status: 'failed', severity: 'info' },
        { status: 'not_executed' }, { status: 'not_applicable' }, { status: 'error' },
      ],
    })
    const presentation = getReportBalancePresentation(result)
    expect(presentation.counts).toEqual({ passed: 1, failed: 3, not_executed: 1, not_applicable: 1, error: 1 })
    expect(presentation).toMatchObject({ status: 'error', blockingFailures: 1, hints: 2, failed_count: 1, hint_count: 2 })
    expect(presentation.message).toContain('审核明细 7 项')
    expect(presentation.message).not.toContain('999')
    const hints = getReportBalancePresentation(mapReportConsistencyCheck({ checks: [{ status: 'failed', severity: 'warning' }] }))
    expect(hints).toMatchObject({ status: 'hint', blockingFailures: 0, hints: 1, counts: { failed: 1, passed: 0 } })
  })

  it.each([
    [[], 'unverified'], [['passed'], 'passed'], [['not_executed'], 'unverified'],
    [['not_applicable'], 'not_applicable'], [['passed', 'not_applicable'], 'completed'],
  ])('只有全部真实通过才显示通过：%j', (statuses, status) => {
    const result = mapReportConsistencyCheck({ consistent: true, no_result: false, total: 7, checks: statuses.map(value => ({ status: value })) })
    expect(getReportBalancePresentation(result).status).toBe(status)
  })

  it('no_result 不隐藏已有未执行/不适用明细', () => {
    const result = mapReportConsistencyCheck({ no_result: true, checks: [{ status: 'not_executed' }, { status: 'not_applicable' }] })
    expect(getReportBalancePresentation(result).counts).toMatchObject({ not_executed: 1, not_applicable: 1 })
    expect(getReportBalancePresentation(result).checks).toHaveLength(2)
  })

  it('自有 null/undefined 不用别名填数；缺少字段才接收别名', () => {
    const checks = mapReportConsistencyCheck({ checks: [
      { expected: 0, expected_value: 9, actual: null, actual_value: 9, diff: undefined, difference: 9 },
      { expected_value: 0, actual_value: '0', difference: 0 }, {},
    ] }).checks
    expect([checks[0].expected, checks[0].actual, checks[0].diff]).toEqual([0, null, undefined])
    expect([checks[1].expected, checks[1].actual, checks[1].diff]).toEqual([0, '0', 0])
    expect([checks[2].expected, checks[2].actual, checks[2].diff]).toEqual([undefined, undefined, undefined])
    expect([0, '0', null, undefined, '', '  ', NaN, Infinity].map(reportCheckValueText)).toEqual(['0', '0', '—', '—', '—', '—', '—', '—'])
  })
})

describe('CSV 与界面使用同一五态及数值口径', () => {
  it('所有列转义逗号、双引号及换行，保留 0、缺数、原因与严重度', () => {
    const result = mapReportConsistencyCheck({ checks: [{
      status: 'failed', passed: true, name: '项,"甲"\n乙', expected: 0, actual: null,
      category_label: '类,"型"\r\n丙', formula: 'REPORT("甲",0)\n+1',
      reason: '原因,"缺数"\r\n下一行', severity: 'warning',
    }] })
    expect(reportChecksToCsv(result.checks)).toBe(
      '"结果","审核项目","期望值","实际值","差额","类型","公式/来源","原因","严重度"\r\n' +
      '"未通过","项,""甲""\n乙","0","—","—","类,""型""\r\n丙","REPORT(""甲"",0)\n+1","原因,""缺数""\r\n下一行","警告"',
    )
  })

  it('非法状态即使带 passed=true 也导出错误，不退回通过', () => {
    const result = mapReportConsistencyCheck({ checks: [{ status: undefined, passed: true, source: '来源,"甲"' }] })
    expect(reportChecksToCsv(result.checks)).toContain('"错误","","—","—","—","","来源,""甲""","检查状态缺失或为空","—"')
  })

  it('非数组及非法单项不抛错，非法单项成为有原因的错误', () => {
    expect(mapReportConsistencyCheck({ checks: {} }).checks).toEqual([])
    const result = mapReportConsistencyCheck({ checks: [null, 0, 'bad'] })
    expect(getReportBalancePresentation(result).counts.error).toBe(3)
  })
})
