/**
 * 披露 sheet 判定 / 变体解析（附注联动复盘 P0-2）单测。
 *
 * 各循环披露 sheet 真实命名（取自 workpaper_sheet_classification 与
 * note_workpaper_sync_registry.json 实测值）必须全部被识别，
 * 且非披露 sheet 不得误命中（否则每张底稿都会挂状态条）。
 */
import { describe, expect, it } from 'vitest'

import {
  isDisclosureSheetName,
  resolveDisclosureVariantFromSheet,
} from '../composables/disclosureSyncBar'

describe('isDisclosureSheetName', () => {
  it.each([
    '附注披露信息（上市公司）',
    '附注披露信息(上市公司)',
    '附注披露信息（国有企业）',
    '附注披露信息(国企)',
    '附注披露（上市公司）',
    '附注上市',
    '附注国企',
    'F1-note-listed',
    'G2-note-soe',
  ])('识别披露 sheet：%s', (name) => {
    expect(isDisclosureSheetName(name)).toBe(true)
  })

  it.each([
    '审定表D1-1',
    '明细表D2-2',
    '底稿目录',
    '实质性程序表K9A',
    '检查表J1-8',
    '完整Excel',
    '',
    null,
    undefined,
  ])('非披露 sheet 不误命中：%s', (name) => {
    expect(isDisclosureSheetName(name as any)).toBe(false)
  })
})

describe('resolveDisclosureVariantFromSheet', () => {
  it.each([
    ['附注披露信息（上市公司）', 'listed'],
    ['附注上市', 'listed'],
    ['F1-note-listed', 'listed'],
    ['附注披露信息（国有企业）', 'soe'],
    ['附注披露信息(国企)', 'soe'],
    ['G2-note-soe', 'soe'],
  ])('%s → %s', (name, expected) => {
    expect(resolveDisclosureVariantFromSheet(name)).toBe(expected)
  })

  it('无变体标识（单变体科目）返回 null，由调用方兜底取唯一项', () => {
    expect(resolveDisclosureVariantFromSheet('附注披露信息')).toBeNull()
    expect(resolveDisclosureVariantFromSheet('')).toBeNull()
    expect(resolveDisclosureVariantFromSheet(undefined)).toBeNull()
  })
})
