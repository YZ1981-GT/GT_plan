import { readFileSync } from 'node:fs'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { parse } from '@vue/compiler-sfc'

const PATH = resolve(dirname(fileURLToPath(import.meta.url)), '../TrialBalance.vue')
const source = readFileSync(PATH, 'utf-8')
const fixedSource = readFileSync(resolve(dirname(PATH), 'composables/useTrialBalanceFixedColumns.ts'), 'utf-8')
const template = parse(source).descriptor.template?.content ?? ''
const KEYS = [
  'standard_account_code', 'account_name', 'direction', 'unadjusted_amount',
  'rje_adjustment', 'aje_adjustment', 'wp_adjustment', 'audited_amount', 'wp_status',
]

describe('TrialBalance 固定列接线', () => {
  it('设置入口只挂在 detail 主表，身份固定为 trial-balance', () => {
    expect(template.match(/<GtTableDisplaySettings\b/g)).toHaveLength(1)
    expect(template).toMatch(/<GtTableDisplaySettings[\s\S]*?page-key="trial-balance"/)
    expect(template).toMatch(/v-if="tbViewMode === 'detail' && !comparisonActive"/)
  })

  it('九个叶子列逐个带稳定 column-key 和 fixedFor；身份列 mandatory', () => {
    for (const key of KEYS) {
      const tags = [...template.matchAll(new RegExp(`<el-table-column[^>]*column-key="${key}"[^>]*>`, 'g'))]
      expect(tags.length, `${key} 必须恰有一个主表叶子列`).toBe(1)
      expect(tags[0][0]).toContain(`tbFixed.fixedFor('${key}')`)
    }
    expect(fixedSource).toContain("mandatoryColumns: ['standard_account_code', 'account_name']")
  })

  it('变异反证：去掉任一 fixedFor 后完整性判据会失败', () => {
    const mutated = template.replace(":fixed=\"tbFixed.fixedFor('audited_amount')\"", '')
    expect(mutated).not.toBe(template)
    expect(mutated).not.toMatch(/column-key="audited_amount"[^>]*tbFixed\.fixedFor\('audited_amount'\)/)
  })
})
