/**
 * sendListSpec.spec.ts — 前后端交叉锁死守卫
 *
 * Property 1: 前端 SEND_LIST_SPECS 的 (cell, field, label, type, enum) 五元组
 *   == 后端 e0_send_list_source_manifest.json。
 * Property 11: hasConfirmFlag 四值正确。
 * Property 14: 金额列用 render:'amount'；利率/份额不用。
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'
import { SEND_LIST_SPECS, type SendListSheet } from '../sendListSpec'

/**
 * 🔴 REPO_ROOT：改造前写死回退 7 级，而 `confirmation/e0-send-list/__tests__/` 到仓库根
 * 实为 **8 级**（__tests__ → e0-send-list → confirmation → workpaper → components → src
 * → frontend → audit-platform → root）→ 解析到 `audit-platform`，
 * `audit-platform/backend/data/...` 不存在 → 整个文件 ENOENT，**本文件 12 条断言从未执行过**。
 * 改为按哨兵文件向上查找，不依赖层级数。
 */
function findRepoRoot(from: string): string {
  let dir = from
  for (let i = 0; i < 12; i++) {
    if (fs.existsSync(path.join(dir, 'backend', 'data', 'e0_send_list_source_manifest.json'))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未能定位仓库根（从 ${from} 向上找 backend/data/e0_send_list_source_manifest.json）`)
}
const REPO_ROOT = findRepoRoot(__dirname)
const MANIFEST_PATH = path.join(REPO_ROOT, 'backend', 'data', 'e0_send_list_source_manifest.json')

function loadManifest() {
  const text = fs.readFileSync(MANIFEST_PATH, 'utf-8')
  return JSON.parse(text)
}

describe('sendListSpec ↔ manifest 交叉锁死', () => {
  const manifest = loadManifest()
  const sheets: SendListSheet[] = ['e03', 'e04', 'e05', 'e06']

  it('manifest 文件存在且含 4 张表', () => {
    expect(Object.keys(manifest.sheets)).toHaveLength(4)
  })

  for (const key of sheets) {
    const spec = SEND_LIST_SPECS[key]
    const mSheet = manifest.sheets[spec.sheetName]

    describe(`${spec.sheetName}`, () => {
      it('列数一致', () => {
        const mCols = Object.keys(mSheet.cell_columns)
        expect(spec.columns).toHaveLength(mCols.length)
      })

      it('(cell, field, label, type) 五元组逐字一致', () => {
        const mCols = mSheet.cell_columns
        for (const col of spec.columns) {
          const mCol = mCols[col.cell]
          expect(mCol, `缺列 ${col.cell}`).toBeDefined()
          expect(col.field).toBe(mCol.field)
          expect(col.label).toBe(mCol.label)
          expect(col.type).toBe(mCol.type)
          if (mCol.enum) {
            expect(col.enum).toEqual(mCol.enum)
          }
          if (mCol.render) {
            expect(col.render).toBe(mCol.render)
          }
        }
      })
    })
  }
})

describe('Property 11: hasConfirmFlag', () => {
  it('e03 和 e04 有 is_confirm 列', () => {
    expect(SEND_LIST_SPECS.e03.hasConfirmFlag).toBe(true)
    expect(SEND_LIST_SPECS.e04.hasConfirmFlag).toBe(true)
  })

  it('e05 和 e06 无 is_confirm 列', () => {
    expect(SEND_LIST_SPECS.e05.hasConfirmFlag).toBe(false)
    expect(SEND_LIST_SPECS.e06.hasConfirmFlag).toBe(false)
  })

  it('e05/e06 columns 中不存在 field=is_confirm', () => {
    for (const key of ['e05', 'e06'] as const) {
      const fields = SEND_LIST_SPECS[key].columns.map(c => c.field)
      expect(fields).not.toContain('is_confirm')
    }
  })

  // 反向自检
  it('给 e05 加 is_confirm 必红', () => {
    // 验证当前确实没有
    const e05Fields = SEND_LIST_SPECS.e05.columns.map(c => c.field)
    expect(e05Fields.includes('is_confirm')).toBe(false)
  })
})

describe('Property 14: 金额控件语义', () => {
  it('balance_orig/balance/face_amount/net_value/accrued_interest 标 render:amount', () => {
    const amountFields = ['balance_orig', 'balance', 'face_amount', 'net_value', 'accrued_interest']
    for (const key of ['e03', 'e04', 'e05', 'e06'] as const) {
      for (const col of SEND_LIST_SPECS[key].columns) {
        if (amountFields.includes(col.field)) {
          expect(col.render, `${key}.${col.field} 应为 amount`).toBe('amount')
        }
      }
    }
  })

  it('interest_rate / holding_shares 不得标 render:amount', () => {
    const nonAmountFields = ['interest_rate', 'holding_shares']
    for (const key of ['e03', 'e04', 'e05', 'e06'] as const) {
      for (const col of SEND_LIST_SPECS[key].columns) {
        if (nonAmountFields.includes(col.field)) {
          expect(col.render, `${key}.${col.field} 不应为 amount`).not.toBe('amount')
        }
      }
    }
  })
})
