/**
 * I2-9 研发人员认定 — 规则引擎单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  emptyI2StaffRow,
  normalizeI2StaffRow,
  suggestStaffConclusion,
  summarizeI2StaffRows,
  hitNonRdKeyword,
} from '../i2StaffCheckModel'

describe('i2StaffCheckModel', () => {
  it('劳务派遣 → 建议不予认定', () => {
    const row = emptyI2StaffRow({
      staffName: '张三',
      employmentForm: '劳务派遣',
      position: '研发工程师',
      personnelCategory: '直接研发人员',
      fullTimeRd: '是',
      rdHourRatio: 100,
    })
    expect(row.suggestedConclusion).toBe('不予认定')
  })

  it('后勤辅助 / 非研发关键词 → 建议不予认定', () => {
    expect(suggestStaffConclusion({
      staffName: '李四',
      employmentForm: '劳动合同',
      personnelCategory: '后勤辅助',
      department: '行政部',
      position: '司机',
      fullTimeRd: '是',
      rdHourRatio: 80,
    })).toBe('不予认定')

    expect(hitNonRdKeyword('销售部', '客户经理')).toBe(true)
  })

  it('兼职且工时占比&lt;50% → 建议不予认定', () => {
    expect(suggestStaffConclusion({
      staffName: '王五',
      employmentForm: '劳动合同',
      personnelCategory: '直接研发人员',
      department: '研发中心',
      position: '工程师',
      fullTimeRd: '否',
      rdHourRatio: 30,
    })).toBe('不予认定')
  })

  it('全时+劳动合同+占比≥50% → 建议认定为研发人员', () => {
    expect(suggestStaffConclusion({
      staffName: '赵六',
      employmentForm: '劳动合同',
      personnelCategory: '直接研发人员',
      department: '研发中心',
      position: '算法工程师',
      fullTimeRd: '是',
      rdHourRatio: 90,
    })).toBe('认定为研发人员')
  })

  it('兼容旧 5 字段结构', () => {
    const row = normalizeI2StaffRow({
      staffName: '旧数据',
      position: '研发',
      qualification: '硕士/工程师',
      projects: '项目A',
      conclusion: '待核实',
    })
    expect(row.education).toBe('硕士')
    expect(row.title).toBe('工程师')
    expect(row.projects).toBe('项目A')
    expect(row.conclusion).toBe('待核实')
  })

  it('汇总统计覆盖风险', () => {
    const rows = [
      emptyI2StaffRow({
        staffName: 'A',
        employmentForm: '劳务派遣',
        conclusion: '认定为研发人员',
      }),
      emptyI2StaffRow({
        staffName: 'B',
        employmentForm: '劳动合同',
        personnelCategory: '直接研发人员',
        position: '工程师',
        department: '研发部',
        fullTimeRd: '是',
        rdHourRatio: 80,
        conclusion: '认定为研发人员',
      }),
    ]
    // 强制建议：第一人是派遣，建议不予认定
    rows[0].suggestedConclusion = '不予认定'
    const s = summarizeI2StaffRows(rows)
    expect(s.totalCount).toBe(2)
    expect(s.overrideRiskCount).toBe(1)
    expect(s.dispatchCount).toBe(1)
    expect(s.acceptedCount).toBe(2)
  })
})
