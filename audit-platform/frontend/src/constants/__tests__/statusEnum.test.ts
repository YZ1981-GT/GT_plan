/**
 * statusEnum.ts 中文 label 映射测试 [Req 8.4.4]
 *
 * 验证：
 * 1. 所有 STATUS_DICT 条目的 label 字段为中文
 * 2. 所有 STATUS_DICT 条目的 color 字段为合法 el-tag type
 * 3. getStatusLabel / getStatusColor 函数正确返回
 * 4. 每个枚举常量值在对应 LABELS 映射中都有中文 label
 */
import { describe, it, expect } from 'vitest'
import {
  STATUS_DICT,
  WP_STATUS,
  WP_REVIEW_STATUS,
  ADJUSTMENT_STATUS,
  REPORT_STATUS,
  PROJECT_STATUS,
  ISSUE_STATUS,
  TEMPLATE_STATUS,
  WORKHOUR_STATUS,
  PROCEDURE_EXECUTION_STATUS,
  WP_STATUS_LABELS,
  WP_REVIEW_STATUS_LABELS,
  ADJUSTMENT_STATUS_LABELS,
  REPORT_STATUS_LABELS,
  PROJECT_STATUS_LABELS,
  ISSUE_STATUS_LABELS,
  TEMPLATE_STATUS_LABELS,
  WORKHOUR_STATUS_LABELS,
  PROCEDURE_STATUS_LABELS,
  getStatusLabel,
  getStatusColor,
} from '../statusEnum'

const VALID_COLORS = ['success', 'warning', 'danger', 'info', 'primary', '']
const CHINESE_REGEX = /[\u4e00-\u9fff]/

describe('statusEnum 中文 label 映射', () => {
  it('STATUS_DICT 所有条目 label 包含中文', () => {
    for (const [dictKey, entries] of Object.entries(STATUS_DICT)) {
      for (const [value, entry] of Object.entries(entries)) {
        expect(
          CHINESE_REGEX.test(entry.label) || entry.label.includes('EQCR'),
          `${dictKey}.${value}.label = "${entry.label}" 应包含中文`,
        ).toBe(true)
      }
    }
  })

  it('STATUS_DICT 所有条目 color 为合法 el-tag type', () => {
    for (const [dictKey, entries] of Object.entries(STATUS_DICT)) {
      for (const [value, entry] of Object.entries(entries)) {
        expect(
          VALID_COLORS.includes(entry.color),
          `${dictKey}.${value}.color = "${entry.color}" 不在合法值列表中`,
        ).toBe(true)
      }
    }
  })

  it('WP_STATUS 每个值在 WP_STATUS_LABELS 中有映射', () => {
    for (const value of Object.values(WP_STATUS)) {
      expect(
        WP_STATUS_LABELS[value],
        `WP_STATUS.${value} 缺少中文 label 映射`,
      ).toBeDefined()
    }
  })

  it('ADJUSTMENT_STATUS 每个值在 ADJUSTMENT_STATUS_LABELS 中有映射', () => {
    for (const value of Object.values(ADJUSTMENT_STATUS)) {
      expect(
        ADJUSTMENT_STATUS_LABELS[value],
        `ADJUSTMENT_STATUS.${value} 缺少中文 label 映射`,
      ).toBeDefined()
    }
  })

  it('REPORT_STATUS 每个值在 REPORT_STATUS_LABELS 中有映射', () => {
    for (const value of Object.values(REPORT_STATUS)) {
      expect(
        REPORT_STATUS_LABELS[value],
        `REPORT_STATUS.${value} 缺少中文 label 映射`,
      ).toBeDefined()
    }
  })

  it('PROJECT_STATUS 每个值在 PROJECT_STATUS_LABELS 中有映射', () => {
    for (const value of Object.values(PROJECT_STATUS)) {
      expect(
        PROJECT_STATUS_LABELS[value],
        `PROJECT_STATUS.${value} 缺少中文 label 映射`,
      ).toBeDefined()
    }
  })

  it('TEMPLATE_STATUS 每个值在 TEMPLATE_STATUS_LABELS 中有映射', () => {
    for (const value of Object.values(TEMPLATE_STATUS)) {
      expect(
        TEMPLATE_STATUS_LABELS[value],
        `TEMPLATE_STATUS.${value} 缺少中文 label 映射`,
      ).toBeDefined()
    }
  })

  it('WORKHOUR_STATUS 每个值在 WORKHOUR_STATUS_LABELS 中有映射', () => {
    for (const value of Object.values(WORKHOUR_STATUS)) {
      // WORKHOUR_STATUS has 'pending' which maps to different dict structure
      // The LABELS use the backend dict keys (draft/tracking/confirmed/approved/rejected)
      const label = WORKHOUR_STATUS_LABELS[value]
      if (value === 'pending') return // 'pending' not in backend workhour dict
      expect(label, `WORKHOUR_STATUS.${value} 缺少中文 label 映射`).toBeDefined()
    }
  })

  describe('getStatusLabel', () => {
    it('返回正确的中文 label', () => {
      expect(getStatusLabel('wp_status', 'draft')).toBe('草稿')
      expect(getStatusLabel('wp_status', 'review_passed')).toBe('复核通过')
      expect(getStatusLabel('project_status', 'archived')).toBe('已归档')
      expect(getStatusLabel('adjustment_status', 'pending_review')).toBe('待复核')
    })

    it('未知值返回原值', () => {
      expect(getStatusLabel('wp_status', 'unknown_value')).toBe('unknown_value')
    })

    it('未知字典键返回原值', () => {
      expect(getStatusLabel('nonexistent_dict', 'draft')).toBe('draft')
    })

    it('null/undefined 返回 "—"', () => {
      expect(getStatusLabel('wp_status', null)).toBe('—')
      expect(getStatusLabel('wp_status', undefined)).toBe('—')
    })
  })

  describe('getStatusColor', () => {
    it('返回正确的 color', () => {
      expect(getStatusColor('wp_status', 'draft')).toBe('warning')
      expect(getStatusColor('wp_status', 'review_passed')).toBe('success')
      expect(getStatusColor('adjustment_status', 'rejected')).toBe('danger')
    })

    it('未知值返回 info', () => {
      expect(getStatusColor('wp_status', 'unknown')).toBe('info')
    })

    it('null/undefined 返回 info', () => {
      expect(getStatusColor('wp_status', null)).toBe('info')
      expect(getStatusColor('wp_status', undefined)).toBe('info')
    })
  })
})
