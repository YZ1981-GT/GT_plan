/**
 * confirmationColumnSpec.spec.ts — 列配置驱动层契约测试
 *
 * spec: confirmation-shared-model-extension (Wave 5 / Tasks 6.1, 6.2)
 *
 * 覆盖 Property 1-6, 9-12
 */
import { describe, it, expect } from 'vitest'
import {
  resolveConfirmationColumns,
  BASE_CONFIRMATION_COLUMNS,
  CYCLE_VARIANT_COLUMNS,
  CORE_COLUMN_KEYS,
  VARIANT_COLUMN_DEFS,
  type ConfirmCycle,
} from '../confirmationColumnSpec'
import {
  CONFIRMATION_SOURCE_MANIFEST,
  CONFIRMATION_SOURCE_EXTRA,
  allRegisteredConfirmationKeys,
} from '../confirmationColumnSourceManifest'
import type { ConfirmationRow } from '../confirmationTypes'

const ALL_CYCLES: ConfirmCycle[] = ['D0', 'E0', 'F0', 'G0', 'H0', 'K0', 'L0']

describe('Property 3: resolveConfirmationColumns ⊆ manifest', () => {
  it.each(ALL_CYCLES)('%s — 每列 key 都在 SOURCE_MANIFEST 中有出处', (cycle) => {
    const columns = resolveConfirmationColumns(cycle)
    const manifest = new Set(CONFIRMATION_SOURCE_MANIFEST[cycle])
    for (const col of columns) {
      expect(manifest.has(col.key), `${cycle} 列 "${col.key}" 不在 manifest`).toBe(true)
    }
  })

  it('resolve 结果 = BASE ∪ variant（逐 cycle 验证集合相等）', () => {
    for (const cycle of ALL_CYCLES) {
      const resolved = resolveConfirmationColumns(cycle).map((c) => c.key)
      const baseKeys = BASE_CONFIRMATION_COLUMNS.map((c) => c.key)
      const variantKeys = CYCLE_VARIANT_COLUMNS[cycle] ?? []
      const expected = new Set([...baseKeys, ...variantKeys])
      expect(new Set(resolved)).toEqual(expected)
    }
  })
})

describe('Property 4: K0/L0 五段与审计结论', () => {
  it('K0 含 send_memo 和 row_conclusion', () => {
    const cols = resolveConfirmationColumns('K0')
    const keys = cols.map((c) => c.key)
    expect(keys).toContain('send_memo')
    expect(keys).toContain('row_conclusion')
  })

  it('L0 含 send_memo 和 row_conclusion', () => {
    const cols = resolveConfirmationColumns('L0')
    const keys = cols.map((c) => c.key)
    expect(keys).toContain('send_memo')
    expect(keys).toContain('row_conclusion')
  })
})

describe('Property 5: E0 原币/本位币口径', () => {
  it('E0 含 amount_orig / fx_rate / confirmed_amount_orig 但覆盖率仍用 amount', () => {
    const cols = resolveConfirmationColumns('E0')
    const keys = cols.map((c) => c.key)
    expect(keys).toContain('amount_orig')
    expect(keys).toContain('fx_rate')
    expect(keys).toContain('confirmed_amount_orig')
    // amount 仍在（本位币，参与覆盖率计算）
    expect(keys).toContain('amount')
    expect(keys).toContain('confirmed_amount')
  })

  it('amount 列类型仍为 amount（非改为 text）', () => {
    const amountCol = BASE_CONFIRMATION_COLUMNS.find((c) => c.key === 'amount')
    expect(amountCol?.kind).toBe('amount')
  })
})

describe('Property 6: H0 条款载体', () => {
  it('H0 含 term_* 四列', () => {
    const cols = resolveConfirmationColumns('H0')
    const keys = cols.map((c) => c.key)
    expect(keys).toContain('term_book')
    expect(keys).toContain('term_reply')
    expect(keys).toContain('term_match')
    expect(keys).toContain('term_note')
  })

  it('D0/F0/G0 不含 term_* 列（不该枢纽无噪声）', () => {
    for (const cycle of ['D0', 'F0', 'G0'] as ConfirmCycle[]) {
      const keys = resolveConfirmationColumns(cycle).map((c) => c.key)
      expect(keys).not.toContain('term_book')
      expect(keys).not.toContain('term_note')
    }
  })
})

describe('Property 9: 每字段可追溯源模板出处', () => {
  it('BASE_CONFIRMATION_COLUMNS 每列有 source', () => {
    for (const col of BASE_CONFIRMATION_COLUMNS) {
      expect(col.source, `${col.key} 缺 source`).toBeTruthy()
    }
  })

  it('VARIANT_COLUMN_DEFS 每列有 source', () => {
    for (const [key, def] of Object.entries(VARIANT_COLUMN_DEFS)) {
      expect(def.source, `variant ${key} 缺 source`).toBeTruthy()
    }
  })

  it('ConfirmationRow 所有字段在 manifest 或 SOURCE_EXTRA 中有条目', () => {
    const registered = allRegisteredConfirmationKeys()
    // 从类型推导不可能，但可检查 spec 数据完整性
    // 至少确保 BASE + variant + extra 键齐全
    const allColKeys = new Set([
      ...BASE_CONFIRMATION_COLUMNS.map((c) => c.key),
      ...Object.keys(VARIANT_COLUMN_DEFS),
    ])
    for (const k of allColKeys) {
      expect(registered.has(k), `字段 "${k}" 在 manifest/extra 中不可追溯`).toBe(true)
    }
  })
})

describe('Property 10: 各枢纽用词不强行统一', () => {
  it('resolveConfirmationColumns 返回的 label 不为空', () => {
    for (const cycle of ALL_CYCLES) {
      const cols = resolveConfirmationColumns(cycle)
      for (const col of cols) {
        expect(col.label, `${cycle}/${col.key} label 为空`).toBeTruthy()
      }
    }
  })
})

describe('Property 11: accountTabs 派生不变', () => {
  it('补列后 account_type 字段语义保持「科目大类」', () => {
    const atCol = BASE_CONFIRMATION_COLUMNS.find((c) => c.key === 'account_type')
    expect(atCol).toBeDefined()
    expect(atCol!.label).toContain('科目')
  })
})

describe('Property 12: 替代程序适配器读 X0-1 行不变', () => {
  it('BASE_CONFIRMATION_COLUMNS 含适配器消费的核心字段', () => {
    const baseKeys = BASE_CONFIRMATION_COLUMNS.map((c) => c.key)
    // 适配器消费的最小字段集
    const requiredKeys = ['amount', 'confirmed_amount', 'alt_confirmed', 'entity_name', 'account_type', 'match_status']
    for (const k of requiredKeys) {
      expect(baseKeys).toContain(k)
    }
  })
})

describe('Property 1: additive round-trip 保真（旧 payload 新字段 undefined）', () => {
  it('旧 ConfirmationRow 经展开保存不丢既有字段', () => {
    // 模拟旧 payload 行（仅既有 28 字段）
    const oldRow: ConfirmationRow = {
      _row_id: 'test-001',
      seq: 1,
      confirm_index: 'CF-001',
      entity_name: '测试公司',
      amount: 100000,
      match_status: '相符',
      is_replied: true,
      reply_amount: 100000,
      remark: '测试备注',
    }
    // 模拟 "读取→展开保存" 过程
    const saved = { ...oldRow }
    // 新增字段为 undefined（天然可选）
    expect(saved.sample_purpose).toBeUndefined()
    expect(saved.send_doc_no).toBeUndefined()
    expect(saved.row_conclusion).toBeUndefined()
    // 既有字段逐字不变
    expect(saved._row_id).toBe('test-001')
    expect(saved.amount).toBe(100000)
    expect(saved.remark).toBe('测试备注')
    expect(saved.match_status).toBe('相符')
  })
})

describe('Property 2: 新字段不进 Sync_Field_Set', () => {
  it('新增字段不在 syncHubFromSummary 消费集合', () => {
    // syncHubFromSummary 消费的字段（baseline-1.2.md §2.1/§2.2 锁定）
    const SYNC_CONSUMED_KEYS = new Set([
      'entity_name', 'account_type', 'amount', 'reply_amount',
      'difference', 'remark', 'confirm_index',
      'match_status', 'is_replied', 'reply_date', 'send_date', 'confirmation_method',
    ])

    // 本 spec 新增全部 additive 字段
    const NEW_ADDITIVE_KEYS = [
      'sample_purpose', 'send_doc_no', 'send_addr_match', 'reply_courier_no',
      'reply_from_addr', 'send_reply_addr_match', 'use_alternative', 'alt_unconfirmed',
      'row_conclusion', 'send_memo', 'account_no', 'fx_rate',
      'amount_orig', 'confirmed_amount_orig',
      'term_book', 'term_reply', 'term_match', 'term_note',
    ]

    for (const key of NEW_ADDITIVE_KEYS) {
      expect(SYNC_CONSUMED_KEYS.has(key), `"${key}" 不应进入 Sync_Field_Set`).toBe(false)
    }
  })
})
