/**
 * H1 复盘改进 — 关键守卫测试
 */
import { describe, expect, it } from 'vitest'
import { BRIDGED_EVENTS } from '@/utils/crossWpEventBridge'
import {
  categoryKeyFromLabel,
  H1_LISTED_DEFAULT_CATEGORIES,
} from '../h1ListedDisclosureModel'
import {
  normalizeFaCategory,
  toListedDisclosureCategoryLabel,
  toSoeDisclosureCategoryLabel,
} from '../h1CategoryClassify'
import { H1_NOTE_SECTION } from '../h1NoteSectionMap'
import { extractCycleProcedureSheetCode, ALL_CYCLE_PROCEDURE_SHEETS } from '../cycleProcedureSheets'
import {
  readH12BranchRows,
  saveH12BranchRows,
  resolveH12Branch,
} from '../h1H12BranchKeys'

describe('H1 P0/P1 guards', () => {
  it('h1:disposal-completed 已纳入跨底稿桥接', () => {
    expect(BRIDGED_EVENTS.has('h1:disposal-completed')).toBe(true)
  })

  it('H1A 已注册为循环程序表', () => {
    expect(ALL_CYCLE_PROCEDURE_SHEETS.H1A?.sheetLabel).toContain('固定资产')
    expect(extractCycleProcedureSheetCode('H1A')).toBe('H1A')
    expect(extractCycleProcedureSheetCode('固定资产审计程序表H1A')).toBe('H1A')
  })

  it('上市默认分类与 H1-1 五类对齐', () => {
    expect(H1_LISTED_DEFAULT_CATEGORIES.map((c) => c.label)).toEqual([
      '房屋及建筑物',
      '机器设备',
      '运输设备',
      '办公设备',
      '其他设备',
    ])
  })

  it('分类 key / 上市国企标签映射', () => {
    expect(categoryKeyFromLabel('房屋、建筑物')).toBe('buildings')
    expect(categoryKeyFromLabel('运输工具')).toBe('transport')
    expect(normalizeFaCategory('电子设备')).toBe('办公设备')
    expect(toListedDisclosureCategoryLabel('电子设备')).toBe('办公设备')
    expect(toSoeDisclosureCategoryLabel('房屋及建筑物')).toBe('房屋、建筑物')
    expect(toSoeDisclosureCategoryLabel('运输设备')).toBe('运输工具')
  })

  it('附注章节：上市五、15 / 国企八、22', () => {
    expect(H1_NOTE_SECTION.listed).toBe('五、15')
    expect(H1_NOTE_SECTION.soe).toBe('八、22')
  })
})

describe('H1-12 分支键约定', () => {
  it('分支行键为 H1-12-A/B/C-rows', () => {
    for (const b of ['A', 'B', 'C'] as const) {
      expect(`H1-12-${b}-rows`).toMatch(/^H1-12-[ABC]-rows$/)
    }
  })

  it('readH12BranchRows 优先活动分支键，A 可回退旧键', () => {
    const map = new Map<string, { remark?: string | null }>([
      ['H1-12-branch', { remark: 'B' }],
      ['H1-12-B-rows', { remark: JSON.stringify([{ assetNo: 'B1' }]) }],
      ['H1-12-rows', { remark: JSON.stringify([{ assetNo: 'LEGACY' }]) }],
    ])
    const r = readH12BranchRows(map)
    expect(r.branch).toBe('B')
    expect(r.itemKey).toBe('H1-12-B-rows')
    expect(r.rows[0].assetNo).toBe('B1')

    const mapA = new Map<string, { remark?: string | null }>([
      ['H1-12-rows', { remark: JSON.stringify([{ assetNo: 'LEGACY' }]) }],
    ])
    expect(resolveH12Branch(mapA)).toBe('A')
    expect(readH12BranchRows(mapA).rows[0].assetNo).toBe('LEGACY')
  })

  it('saveH12BranchRows 同时写分支键与镜像键', () => {
    const saves: Array<{ id: string; val: any }> = []
    saveH12BranchRows((id, val) => saves.push({ id, val }), 'C', [{ assetNo: 'x' }])
    expect(saves.map((s) => s.id)).toEqual(['H1-12-C-rows', 'H1-12-rows'])
  })
})
