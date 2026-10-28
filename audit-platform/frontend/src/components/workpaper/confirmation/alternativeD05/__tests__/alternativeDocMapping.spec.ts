/**
 * 替代程序单据映射（spec attachment-confirmation-evidence-loop 需求 3.2、3.3，ADR-ACE-03）
 *
 * 守卫两头：映射键都能在某页列配置里找到（无死条目，变异 M12）；映射值都在后端该类 schema 里（读 py 文件）。
 * 行为：只预选本行为空的列（变异 M4）、数值 / 日期按列类型转换、0 视为未识别。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { FRONTEND_SRC } from '@/__tests__/_helpers/frontendSourceScan'
import {
  ALT_DOC_COLUMN_MAP,
  ALT_DOC_TYPES,
  applicableDocTypes,
  buildFillPlan,
  columnKey,
  normalizeDate,
  type AltColumn,
  type AltDocType,
} from '../alternativeDocMapping'
import { BLOCK_COLUMN_CONFIGS } from '../blockColumnConfigs'
import { BLOCK_COLUMN_CONFIGS_D06 } from '../../alternativeD06/blockColumnConfigsD06'
import { BLOCK_COLUMN_CONFIGS_F05 } from '../../alternativeF05/blockColumnConfigsF05'
import { BLOCK_COLUMN_CONFIGS_F06 } from '../../alternativeF06/blockColumnConfigsF06'
import { BLOCK_COLUMN_CONFIGS_H05 } from '../../alternativeH05/blockColumnConfigsH05'
import { BLOCK_COLUMN_CONFIGS_K05 } from '../../alternativeK05/blockColumnConfigsK05'
import { BLOCK_COLUMN_CONFIGS_K06 } from '../../alternativeK06/blockColumnConfigsK06'
import { BLOCK_COLUMN_CONFIGS_G06 } from '../../../g0-confirmation/alternativeG06/blockColumnConfigsG06'

const REPO = resolve(FRONTEND_SRC, '../../..')
const read = (rel: string) => readFileSync(resolve(REPO, rel), 'utf-8').replace(/\r\n/g, '\n')

const PAGES: Record<string, Record<string, { columns: AltColumn[] }>> = {
  'D0-5': BLOCK_COLUMN_CONFIGS, 'D0-6': BLOCK_COLUMN_CONFIGS_D06, 'F0-5': BLOCK_COLUMN_CONFIGS_F05,
  'F0-6': BLOCK_COLUMN_CONFIGS_F06, 'H0-5': BLOCK_COLUMN_CONFIGS_H05, 'K0-5': BLOCK_COLUMN_CONFIGS_K05,
  'K0-6': BLOCK_COLUMN_CONFIGS_K06, 'G0-6': BLOCK_COLUMN_CONFIGS_G06,
}

/** L0-5 自有表格：证据列无分组（键 `|列名`），左侧 5 列记账凭证 */
function l05Keys(): string[] {
  const src = read('audit-platform/frontend/src/components/workpaper/confirmation/alternativeL05/GtConfirmationAlternativeL05.vue')
  const base = /const BLOCKS_L05_BASE[\s\S]*?\n\]\n/.exec(src)?.[0] ?? ''
  const evidence = [...base.matchAll(/\{ key: '[^']+', label: '([^']+)'/g)].map((m) => `|${m[1]}`)
  const voucher = [...(/const L05_VOUCHER_COLUMNS[\s\S]*?\n\]\n/.exec(src)?.[0] ?? '')
    .matchAll(/label: '([^']+)', group: '([^']+)'/g)].map((m) => `${m[2]}|${m[1]}`)
  return [...evidence, ...voucher]
}

function backendSchemas(): Record<string, string[]> {
  const src = read('backend/app/routers/wp_render_strategies/_confirmation_alt_doc_ocr.py')
  const body = /DOCUMENT_SCHEMAS: dict\[str, dict\[str, str\]\] = \{([\s\S]*?)\n\}\n/.exec(src)?.[1] ?? ''
  const out: Record<string, string[]> = {}
  for (const m of body.matchAll(/^    "(\w+)": \{([\s\S]*?)^    \},/gm)) {
    out[m[1]] = [...m[2].matchAll(/^        "(\w+)":/gm)].map((f) => f[1])
  }
  return out
}

const allKeys = (): Set<string> => {
  const keys = new Set<string>(l05Keys())
  for (const page of Object.values(PAGES)) {
    for (const block of Object.values(page)) for (const col of block.columns) keys.add(columnKey(col))
  }
  return keys
}

describe('映射守卫', () => {
  it('每个「分组 | 列名」都在某页列配置里（无死条目）', () => {
    const keys = allKeys()
    expect(keys.size).toBeGreaterThan(150) // 扫描面没塌缩
    expect(l05Keys().length).toBeGreaterThanOrEqual(25)
    const dead = Object.entries(ALT_DOC_COLUMN_MAP).flatMap(([type, map]) =>
      Object.keys(map).filter((k) => !keys.has(k)).map((k) => `${type}: ${k}`))
    expect(dead, `映射表里有列配置中不存在的列：\n${dead.join('\n')}`).toEqual([])
  })

  it('单据类型与字段都在后端 schema 里（date_no 由 date + doc_no 派生）', () => {
    const schemas = backendSchemas()
    expect(Object.keys(schemas).sort()).toEqual(ALT_DOC_TYPES.map((t) => t.value).sort())
    const missing: string[] = []
    for (const [type, map] of Object.entries(ALT_DOC_COLUMN_MAP)) {
      for (const field of new Set(Object.values(map))) {
        const need = field === 'date_no' ? ['date', 'doc_no'] : [field]
        for (const f of need) if (!schemas[type]?.includes(f)) missing.push(`${type}.${f}`)
      }
    }
    expect(missing).toEqual([])
  })

  it('9 页每个区块都至少有一种可识别的单据类型', () => {
    const empty = Object.entries(PAGES).flatMap(([page, blocks]) =>
      Object.entries(blocks).filter(([, b]) => !applicableDocTypes(b.columns).length).map(([bt]) => `${page} ${bt}`))
    expect(empty).toEqual([])
    expect(applicableDocTypes(BLOCK_COLUMN_CONFIGS.block3.columns)).toEqual(['bank_receipt', 'invoice', 'voucher'])
  })
})

describe('填入计划', () => {
  const cols: AltColumn[] = [
    { field: 'voucher_date', label: '日期', group: '记账凭证', type: 'date' },
    { field: 'bank_payer', label: '付款方', group: '银行回单', type: 'text' },
    { field: 'bank_amount', label: '金额', group: '银行收款凭单', type: 'number' },
    { field: 'bank_slip_no', label: '日期/编号', group: '银行回单', type: 'text' },
    { field: 'is_abnormal', label: '是否异常', type: 'select' },
  ]
  const fields = { date: '2025年12月31日', doc_no: 'HD-001', payer: ' 甲公司 ', amount: '12,345.60', payee: '乙公司' }
  const plan = (type: AltDocType, row: Record<string, unknown>) => buildFillPlan(cols, row, type, fields)

  it('只预选本行为空的列；已有值的列列出但不可选', () => {
    const items = plan('bank_receipt', { bank_payer: '原有付款方', bank_amount: null })
    expect(items.map((i) => [i.field, i.value, i.fillable])).toEqual([
      ['bank_payer', '甲公司', false],
      ['bank_amount', 12345.6, true],
      ['bank_slip_no', '2025-12-31 HD-001', true],
    ])
    expect(items[0].label).toBe('银行回单 · 付款方')
  })

  it('数值 0 / 空串视为未识别不列出；日期按列类型归一', () => {
    const items = buildFillPlan(cols, {}, 'voucher', { date: '2025/1/5', amount: 0, doc_no: '' })
    expect(items).toEqual([{ field: 'voucher_date', label: '记账凭证 · 日期', value: '2025-01-05', current: undefined, fillable: true }])
    expect(normalizeDate('2025.12.3')).toBe('2025-12-03')
    expect(normalizeDate('十二月')).toBeNull()
  })

  it('下拉列不由识别结果填', () => {
    expect(plan('bank_receipt', {}).some((i) => i.field === 'is_abnormal')).toBe(false)
  })
})
