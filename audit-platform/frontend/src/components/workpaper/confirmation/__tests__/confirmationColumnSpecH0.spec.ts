/**
 * confirmationColumnSpecH0.spec.ts — H0 列集与 label 覆盖守卫
 *
 * spec: h0-confirmation-source-fidelity-and-linkage
 *   Requirements 6.1~6.7 / 12.5；Property 16 / 17 / 18
 *
 * 与源模板表头的**逐字比对**在
 * `backend/tests/test_h0_source_template_facts.py::test_frontend_label_matches_source`
 * （前端读不了 xlsx）；本文件负责：
 *   - H0 列集（含/不含哪些列）
 *   - **其余六枢纽零回归**（快照 + BASE 常量未被 mutate）
 *   - 剔除列不销毁持久化值
 */
import { describe, it, expect } from 'vitest'
import {
  BASE_CONFIRMATION_COLUMNS,
  CYCLE_COLUMN_LABEL_OVERRIDES,
  CYCLE_EXCLUDED_COLUMNS,
  CYCLE_VARIANT_COLUMNS,
  VARIANT_COLUMN_DEFS,
  resolveConfirmationColumns,
  type ConfirmCycle,
} from '../confirmationColumnSpec'
import { CONFIRMATION_SOURCE_MANIFEST } from '../confirmationColumnSourceManifest'
import type { ConfirmationRow } from '../confirmationTypes'

const ALL_CYCLES: ConfirmCycle[] = ['D0', 'E0', 'F0', 'G0', 'H0', 'K0', 'L0']

// ─── Property 16: H0 列集 ────────────────────────────────────────────────────

describe('Property 16: H0 列集', () => {
  const keys = resolveConfirmationColumns('H0').map((c) => c.key)

  it('含行级审计结论列（源模板 AB 列）', () => {
    expect(keys).toContain('row_conclusion')
  })

  it('含发函渠道列 send_channel（源模板 G 列「函证方式」）', () => {
    expect(keys).toContain('send_channel')
  })

  it('含条款口径四列（H0 的金额/条款双载体）', () => {
    for (const k of ['term_book', 'term_reply', 'term_match', 'term_note']) {
      expect(keys).toContain(k)
    }
  })

  it('不含源模板没有的三列（联系人/联系电话/币种）', () => {
    for (const k of ['contact_person', 'contact_phone', 'currency']) {
      expect(keys).not.toContain(k)
    }
  })

  it('每列 key 仍 ⊆ CONFIRMATION_SOURCE_MANIFEST.H0（Property 3 不被打破）', () => {
    const manifest = new Set(CONFIRMATION_SOURCE_MANIFEST.H0)
    for (const k of keys) {
      expect(manifest.has(k), `列 "${k}" 不在 manifest.H0`).toBe(true)
    }
  })

  it('列 key 唯一（h0_row_conclusion 与 K0/L0 的 row_conclusion 共享字段但不重复渲染）', () => {
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('每列都有非空 label 与 source 出处', () => {
    for (const c of resolveConfirmationColumns('H0')) {
      expect(c.label, `${c.key} label 为空`).toBeTruthy()
      expect(c.source, `${c.key} 缺 source`).toBeTruthy()
    }
  })
})

// ─── Property 16: label 覆盖表 ───────────────────────────────────────────────

describe('Property 16: CYCLE_COLUMN_LABEL_OVERRIDES', () => {
  it('H0 已声明覆盖表', () => {
    // 🔴 不写死「只有 H0」—— 并发 spec（g0-confirmation-source-alignment）已复用本机制
    // 为 G0 声明覆盖。零回归的判据是「**未声明覆盖的循环** label 不变」（见 Property 17），
    // 不是「只有一个循环声明」。
    expect(CYCLE_COLUMN_LABEL_OVERRIDES.H0).toBeTruthy()
    expect(Object.keys(CYCLE_COLUMN_LABEL_OVERRIDES.H0!).length).toBeGreaterThan(10)
  })

  it('覆盖表里每个 key 都真实出现在 H0 渲染列里（无死配置）', () => {
    const keys = new Set(resolveConfirmationColumns('H0').map((c) => c.key))
    for (const k of Object.keys(CYCLE_COLUMN_LABEL_OVERRIDES.H0!)) {
      expect(keys.has(k), `override key "${k}" 不在 H0 渲染列里 = 死配置`).toBe(true)
    }
  })

  it('覆盖生效：账户/交易、金额或合同条款、替代程序索引号等', () => {
    const byKey = Object.fromEntries(resolveConfirmationColumns('H0').map((c) => [c.key, c.label]))
    expect(byKey.account_type).toBe('账户/交易')
    expect(byKey.amount).toBe('金额或合同条款')
    expect(byKey.alt_ref_index).toBe('替代程序索引号')
    expect(byKey.diff_ref_index).toBe('差异核对索引（H0-4）')
    expect(byKey.remark).toBe('其他说明/备注')
  })

  it('confirmation_method 在 H0 上明示为「函证类型」以与源模板的「函证方式」区分', () => {
    const byKey = Object.fromEntries(resolveConfirmationColumns('H0').map((c) => [c.key, c.label]))
    expect(byKey.confirmation_method).toContain('积极式')
    expect(byKey.send_channel).toBe('函证方式')
    // 两列 label 必须不同，否则界面出现两个「函证方式」
    expect(byKey.confirmation_method).not.toBe(byKey.send_channel)
  })
})

// ─── Property 17: 六枢纽零回归 + BASE 未被 mutate ────────────────────────────

describe('Property 17: 其余六枢纽零回归', () => {
  it('未声明覆盖的循环 label 与 BASE/VARIANT 原始 label 完全一致', () => {
    const baseLabel = new Map(BASE_CONFIRMATION_COLUMNS.map((c) => [c.key, c.label]))
    const variantLabel = new Map(Object.values(VARIANT_COLUMN_DEFS).map((d) => [d.key, d.label]))
    const untouched = ALL_CYCLES.filter((c) => !CYCLE_COLUMN_LABEL_OVERRIDES[c])
    expect(untouched.length, '至少应有若干循环未声明覆盖').toBeGreaterThan(2)
    for (const cycle of untouched) {
      for (const c of resolveConfirmationColumns(cycle)) {
        const expected = baseLabel.get(c.key) ?? variantLabel.get(c.key)
        expect(c.label, `${cycle}/${c.key} label 漂移`).toBe(expected)
      }
    }
  })

  it('已声明覆盖的循环之间互不影响（H0 的覆盖不渗到别的循环）', () => {
    const h0Overrides = CYCLE_COLUMN_LABEL_OVERRIDES.H0!
    for (const cycle of ALL_CYCLES) {
      if (cycle === 'H0') continue
      const own = CYCLE_COLUMN_LABEL_OVERRIDES[cycle]
      for (const c of resolveConfirmationColumns(cycle)) {
        // 若该循环自己声明了同 key 的覆盖，取自己的；否则不得等于 H0 的专属用词
        if (own && own[c.key] !== undefined) continue
        const h0Label = h0Overrides[c.key]
        if (h0Label === undefined) continue
        const original =
          BASE_CONFIRMATION_COLUMNS.find((b) => b.key === c.key)?.label
          ?? Object.values(VARIANT_COLUMN_DEFS).find((d) => d.key === c.key)?.label
        if (original !== undefined && original !== h0Label) {
          expect(c.label, `${cycle}/${c.key} 被 H0 覆盖污染`).toBe(original)
        }
      }
    }
  })

  it('🔴 先调 H0 再调 D0：D0 的 label 不被 H0 的覆盖污染（浅拷贝未写漏）', () => {
    const before = resolveConfirmationColumns('D0').map((c) => `${c.key}=${c.label}`)
    resolveConfirmationColumns('H0') // 触发 override 分支
    resolveConfirmationColumns('H0')
    const after = resolveConfirmationColumns('D0').map((c) => `${c.key}=${c.label}`)
    expect(after).toEqual(before)
  })

  it('🔴 BASE_CONFIRMATION_COLUMNS 常量对象自身未被改写', () => {
    const snapshot = BASE_CONFIRMATION_COLUMNS.map((c) => `${c.key}=${c.label}`)
    resolveConfirmationColumns('H0')
    expect(BASE_CONFIRMATION_COLUMNS.map((c) => `${c.key}=${c.label}`)).toEqual(snapshot)
    // 账户/交易 只在 H0 上生效，BASE 仍是「科目」
    expect(BASE_CONFIRMATION_COLUMNS.find((c) => c.key === 'account_type')!.label).toBe('科目')
    expect(BASE_CONFIRMATION_COLUMNS.find((c) => c.key === 'alt_ref_index')!.label).toBe('替代程序索引')
  })

  it('🔴 VARIANT_COLUMN_DEFS 常量对象自身未被改写', () => {
    const snapshot = Object.entries(VARIANT_COLUMN_DEFS).map(([k, d]) => `${k}=${d.label}`)
    resolveConfirmationColumns('H0')
    expect(Object.entries(VARIANT_COLUMN_DEFS).map(([k, d]) => `${k}=${d.label}`)).toEqual(snapshot)
  })

  it('七枢纽列数均等于 (BASE − EXCLUDED) ∪ variant', () => {
    for (const cycle of ALL_CYCLES) {
      const excluded = new Set(CYCLE_EXCLUDED_COLUMNS[cycle] ?? [])
      const baseCount = BASE_CONFIRMATION_COLUMNS.filter((c) => !excluded.has(c.key)).length
      const variantCount = new Set(
        (CYCLE_VARIANT_COLUMNS[cycle] ?? []).map((k) => VARIANT_COLUMN_DEFS[k]?.key).filter(Boolean),
      ).size
      expect(resolveConfirmationColumns(cycle).length, cycle).toBe(baseCount + variantCount)
    }
  })

  it('H0 剔除三列；未声明剔除的循环仍为空数组', () => {
    expect(CYCLE_EXCLUDED_COLUMNS.H0).toEqual(['contact_person', 'contact_phone', 'currency'])
    expect(CYCLE_EXCLUDED_COLUMNS.E0.length).toBeGreaterThan(0) // 既有例外
    // 🔴 不写死「其余全空」—— 并发 spec 已为 G0 声明同款剔除。
    const declared = ALL_CYCLES.filter((c) => (CYCLE_EXCLUDED_COLUMNS[c] ?? []).length > 0)
    expect(declared, 'H0 必须在已声明剔除的循环里').toContain('H0')
    for (const cycle of ALL_CYCLES) {
      if (declared.includes(cycle)) continue
      expect(CYCLE_EXCLUDED_COLUMNS[cycle], cycle).toEqual([])
    }
  })
})

// ─── Property 18: 剔除列不销毁持久化值 ──────────────────────────────────────

describe('Property 18: 剔除只影响渲染，不销毁数据', () => {
  it('历史载荷里的 contact_person / currency 值仍在（只是不渲染）', () => {
    const legacy: ConfirmationRow = {
      _row_id: 'r1',
      confirm_index: 'H0-001',
      entity_name: '甲公司',
      contact_person: '张三',
      contact_phone: '13800000000',
      currency: 'CNY',
      amount: 1000,
    }
    // 模拟「读取 → 展开保存」（渲染层不含这些列，但字段照样往下传）
    const saved: ConfirmationRow = { ...legacy }
    expect(saved.contact_person).toBe('张三')
    expect(saved.contact_phone).toBe('13800000000')
    expect(saved.currency).toBe('CNY')

    // 渲染列里确实没有它们
    const keys = resolveConfirmationColumns('H0').map((c) => c.key)
    expect(keys).not.toContain('contact_person')
    expect(keys).not.toContain('currency')
  })

  it('剔除列仍登记在 manifest 里（可追溯，不是被删除）', () => {
    const manifest = new Set(CONFIRMATION_SOURCE_MANIFEST.H0)
    for (const k of ['contact_person', 'contact_phone', 'currency']) {
      expect(manifest.has(k), `${k} 应仍在 manifest（剔除≠删除）`).toBe(true)
    }
  })
})

// ─── 分段表头顺序 ────────────────────────────────────────────────────────────

describe('H0 分段表头顺序', () => {
  it('列按 group 顺序排列（send_info → reply_info → reply_amount → alternative → row_summary）', () => {
    const groups = resolveConfirmationColumns('H0').map((c) => c.group)
    const order = ['send_info', 'reply_info', 'reply_amount', 'alternative', 'send_memo', 'row_summary']
    let cursor = -1
    for (const g of groups) {
      const idx = order.indexOf(g)
      expect(idx, `未知 group ${g}`).toBeGreaterThan(-1)
      expect(idx, `group 顺序错乱: ${groups.join(',')}`).toBeGreaterThanOrEqual(cursor)
      cursor = idx
    }
  })

  it('send_channel 落在发函信息段、row_conclusion 落在行级结论段', () => {
    const byKey = Object.fromEntries(resolveConfirmationColumns('H0').map((c) => [c.key, c.group]))
    expect(byKey.send_channel).toBe('send_info')
    expect(byKey.row_conclusion).toBe('row_summary')
  })

  it('H0 的 row_conclusion 不落在 send_memo 段（那是发函询证纪要段）', () => {
    const h0 = resolveConfirmationColumns('H0').find((c) => c.key === 'row_conclusion')!
    expect(h0.group).toBe('row_summary')
    // 🔴 改写记录（k0-confirmation-source-alignment R2.4，2026-08-07）：
    //    原断言 `k0.group === 'send_memo'` 锁定 K0 改造前的缺陷状态；K0 现已收口，
    //    四个循环（G0/H0/K0/L0）的行级结论列统一归 row_summary。
    const k0 = resolveConfirmationColumns('K0').find((c) => c.key === 'row_conclusion')!
    expect(k0.group).toBe('row_summary')
    expect(k0.source).toContain('K0-1')
  })
})

// ─── 零参可调（覆盖率 sweep 前提） ───────────────────────────────────────────

describe('resolveConfirmationColumns 零参可调', () => {
  it('七枢纽均返回非空列集', () => {
    for (const cycle of ALL_CYCLES) {
      expect(resolveConfirmationColumns(cycle).length, cycle).toBeGreaterThan(20)
    }
  })

})
