/**
 * J2 附注同步请求体 = 端点契约 `SyncFromWorkpaperRequest`（wp_disclosure_sync.py）
 *
 * 缺陷（2026-09-30 现算）：J2 两个披露 Tab 把构建器产物（`note_section` / `_sub_table_columns` /
 * 顶层 `_removed_table_keys`）直接展开进请求体，再用 axios 默认实例发出 ⇒ 先 401；即便带鉴权也 422
 * （必填 `wp_id` / `section_id` / `current_standard` 缺失），`columns` 与待删表名还会被 pydantic 静默丢弃。
 * 真库五、49 / 八、54 / 五、17 共 8 个章节 `_last_sync_wp_id` 全 0 —— 从未同步成功过。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  buildJ2ListedSyncPayload,
  buildJ2NetAssetPayload,
  buildJ2SoeSyncPayload,
  J2_SOE_LEGACY_OBSOLETE_TABLES,
  toJ2SyncRequest,
} from '../j2DisclosureSyncPayload'
import { J2_DISCLOSURE_SHEET_NAME, J2_NET_ASSET_NOTE_SECTION, J2_NOTE_SECTION } from '../j2NoteSectionMap'

/** 端点必填字段（与后端 pydantic 模型逐项对应） */
const REQUIRED = ['wp_id', 'sheet_name', 'section_id', 'current_standard'] as const
/** 端点认识的全部字段；其余字段会被静默丢弃 */
const KNOWN = new Set([...REQUIRED, 'sub_table_data', 'columns', 'year'])

const row = (label: string) => ({ key: label, label, end: 1, begin: 2, cur: 3, prior: 4, amount: 5, delta: 6, up: 7, down: 8 })
const listed = () => buildJ2ListedSyncPayload({
  summaryRows: [row('设定受益计划净负债')], dboRows: [row('期初余额')], assetRows: [row('期初余额')],
  netRows: [row('期初余额')], maturityRows: [row('1年以内')], assetCompRows: [row('现金')],
  assumeRows: [row('折现率')], sensRows: [row('折现率')], noteTerm: '', noteDbp: '说明', noteSens: '',
})
const soe = () => buildJ2SoeSyncPayload({
  summaryRows: [{ key: 's', label: '设定受益计划净负债', begin: 1, increase: 2, decrease: 3 }],
  changeRows: [{ key: 'c', label: '期初余额', dboCur: 1, dboPrior: 2, assetCur: 3, assetPrior: 4, netCur: 5, netPrior: 6 }],
  maturityRows: [row('1年以内')], assetCompRows: [row('现金')], assumeRows: [row('折现率')], sensRows: [row('折现率')],
  noteTerm: '', noteDbp: '', noteSens: '', summaryEndFn: (r) => r.begin + r.increase - r.decrease,
})

describe('toJ2SyncRequest：构建器产物 → 端点契约', () => {
  it('上市：必填字段齐全、只含端点认识的字段，数据与列头原样透传', () => {
    const built = listed()
    const req = toJ2SyncRequest(built, { wpId: 'wp-1', currentStandard: 'listed_standalone', year: 2025 })
    for (const k of REQUIRED) expect(req[k], k).toBeTruthy()
    expect(Object.keys(req).filter((k) => !KNOWN.has(k))).toEqual([])
    expect(req).toMatchObject({
      wp_id: 'wp-1', sheet_name: J2_DISCLOSURE_SHEET_NAME.listed, section_id: J2_NOTE_SECTION.listed,
      current_standard: 'listed_standalone', year: 2025,
    })
    expect(req.sub_table_data).toEqual(built.sub_table_data)
    expect(req.columns).toBe(built._sub_table_columns)
    expect(Object.keys(req.columns).length).toBeGreaterThan(0)
  })

  it('国企：待删旧表名进 sub_table_data._removed_table_keys（后端只在那里读取）', () => {
    const built = soe()
    const req = toJ2SyncRequest(built, { wpId: 'wp-2', currentStandard: 'soe_standalone', year: 2025 })
    expect(req.section_id).toBe(J2_NOTE_SECTION.soe)
    expect(req.sub_table_data._removed_table_keys).toEqual([...J2_SOE_LEGACY_OBSOLETE_TABLES])
    expect(Object.keys(req).filter((k) => !KNOWN.has(k))).toEqual([])
    // 不改构建器产物（纯映射）
    expect('_removed_table_keys' in built.sub_table_data).toBe(false)
  })

  it('净资产分支：章节五、17，年度缺失时不发 year 键', () => {
    const built = buildJ2NetAssetPayload({ dbpNetRow: { begin: -1, increase: 2, decrease: 0, end: -3 } })
    const req = toJ2SyncRequest(built, { wpId: 'wp-3', currentStandard: 'listed_standalone', year: null })
    expect(req.section_id).toBe(J2_NET_ASSET_NOTE_SECTION.listed)
    expect('year' in req).toBe(false)
  })
})

describe('J2 两个披露 Tab 的接线（源码级）', () => {
  const read = (f: string) => readFileSync(resolve(__dirname, '../../j2', f), 'utf-8')
  it.each(['J2TabDisclosureListed.vue', 'J2TabDisclosureSoe.vue'])('%s 经 apiProxy + toJ2SyncRequest 发请求', (f) => {
    const src = read(f)
    expect(src).toContain("import { api } from '@/services/apiProxy'")
    expect(src).toMatch(/api\.post\(\s*`\/api\/projects\/\$\{props\.projectId\}\/disclosure-notes\/sync-from-workpaper`,\s*toJ2SyncRequest\(/)
    expect(src).not.toMatch(/import\(\s*['"]axios['"]\s*\)/)
    expect(src).not.toMatch(/\.\.\.payload\b/)
  })
})
