/**
 * `isTbSourceAbsent` / `tbAbsentCodesText` 守卫 —— 「本项目无此科目」三态的平台判据。
 *
 * ## 缺陷来源（浏览器实测）
 *
 * I5-1「其他非流动资产」审定表 / 项目「宜宾临港店」(soe)：**两个溯源面板都是空的**
 * —— `WpFourTableSourcePanel` 整块 `v-if` 隐藏（一片空白）、
 * `HiFourTableSourcePanel` 只剩 Element Plus 默认的英文「No Data」空表格
 * 加一个点了没意义的「🔄 刷新取数」按钮。
 *
 * 抓 `GET /api/workpapers/{I5-1}/render-config` 拿到的真实载荷：
 * ```json
 * { "wp_code": "I5", "row_code": "BS-037", "row_name": "其他非流动资产",
 *   "formula": "TB('1911','期末余额')",
 *   "resolved_from": "fallback",
 *   "signed_codes": [["1911", 1]],
 *   "segments": [{ "segment": "cost", "standard": [], "original": [] }],
 *   "diagnostics": [{ "kind": "unclaimed", "code": "1911", "chart_name": "" }],
 *   "gross": [], "gross_standard": [], "provision": [], "provision_standard": [] }
 * ```
 *
 * 🔴 **两个易错点**：
 * 1. `resolved_from` 是 **`'fallback'` 而不是 `'none'`** ⇒ 只判 `resolved_from === 'none'`
 *    的实现会漏掉这个真实形态（类型注释里 `'none'` 的存在很容易误导人只判它）。
 * 2. 「后端算过但本项目没这个科目」与「后端根本没下发」必须分开：
 *    前者要显式说明（审计师需知道本该从哪个报表行取数、为何没取到），
 *    后者才该整块隐藏（避免空洞卡片）。
 *
 * 三态表：
 * | 态 | 判据 | 界面 |
 * |---|---|---|
 * | 已取数 | `hasTbSourceCodes()` | 正常展示科目链路 |
 * | 本项目无此科目 | `isTbSourceAbsent()` | 显式说明 + 仍给报表行/公式 |
 * | 后端未下发 | `src == null` | 整块隐藏 |
 *
 * spec: .kiro/specs/i-cycle-extraction-formula-and-disclosure-closure/ Task 24（补测 5/5）
 */
import { describe, expect, it } from 'vitest'

import {
  hasTbSourceCodes,
  isTbSourceAbsent,
  tbAbsentCodesText,
  type TbSourceCodes,
} from '../tbSourceCodes'

/** I5-1 实测真实载荷（逐字取自 render-config，勿改） */
const I5_REAL: TbSourceCodes = {
  wp_code: 'I5',
  row_code: 'BS-037',
  row_name: '其他非流动资产',
  formula: "TB('1911','期末余额')",
  matched_standard: 'soe_standalone',
  resolved_from: 'fallback',
  signed_codes: [['1911', 1]],
  segments: [{
    segment: 'cost',
    label: '其他非流动资产',
    standard: [],
    original: [],
    exact: false,
    resolved_from: 'fallback',
    absolute: false,
    credit_is_increase: false,
    occurrence: false,
  }],
  diagnostics: [{ kind: 'unclaimed', code: '1911', chart_name: '', row_code: 'BS-037' }],
  gross: [],
  gross_standard: [],
  provision: [],
  provision_standard: [],
  parent_check_ok: true,
  unmapped: [],
}

/** I1-1 实测真实载荷（有码，必须**不**被判 absent） */
const I1_REAL: TbSourceCodes = {
  wp_code: 'I1',
  row_code: 'BS-032',
  row_name: '无形资产',
  formula: "TB('1701','期末余额') - TB('1702','期末余额')",
  matched_standard: 'soe_standalone',
  resolved_from: 'report_config',
  signed_codes: [['1701', 1], ['1702', -1]],
  segments: [
    { segment: 'cost', label: '账面原值', standard: ['1701'], original: ['1701'] },
    { segment: 'amortization', label: '累计摊销', standard: ['1702'], original: ['1702'] },
  ],
  gross: ['1701'],
  gross_standard: ['1701'],
  provision: ['1702'],
  provision_standard: ['1702'],
}

describe('三态区分：absent / 已取数 / 未下发', () => {
  it('🔴 I5-1 真实载荷（resolved_from=fallback 但码全空）判 absent', () => {
    expect(hasTbSourceCodes(I5_REAL)).toBe(false)
    expect(
      isTbSourceAbsent(I5_REAL),
      'resolved_from 是 fallback 不是 none ⇒ 只判 none 的实现会漏掉这个真实形态',
    ).toBe(true)
  })

  it('I1-1 真实载荷（有码）不判 absent', () => {
    expect(hasTbSourceCodes(I1_REAL)).toBe(true)
    expect(isTbSourceAbsent(I1_REAL), '有码的循环被误判 absent ⇒ 正常面板变提示').toBe(false)
  })

  it('后端未下发（null / undefined）不判 absent —— 该整块隐藏而非报「无此科目」', () => {
    expect(isTbSourceAbsent(null)).toBe(false)
    expect(isTbSourceAbsent(undefined)).toBe(false)
  })

  it('空对象不判 absent（没有任何元信息 ⇒ 后端没算过，不能替它下结论）', () => {
    expect(isTbSourceAbsent({})).toBe(false)
    expect(isTbSourceAbsent({ gross: [], provision: [] })).toBe(false)
  })
})

describe('任一层级有码即不算 absent（防误判正常面板）', () => {
  it.each<[string, TbSourceCodes]>([
    ['gross', { row_code: 'BS-001', gross: ['1122'] }],
    ['gross_standard', { row_code: 'BS-001', gross_standard: ['1122'] }],
    ['provision', { row_code: 'BS-001', provision: ['1231'] }],
    ['provision_standard', { row_code: 'BS-001', provision_standard: ['1231'] }],
    ['segments[].standard', { row_code: 'BS-001', segments: [{ segment: 'cost', standard: ['1701'] }] }],
    ['segments[].original', { row_code: 'BS-001', segments: [{ segment: 'cost', original: ['1701'] }] }],
    ['slots[].codes', { row_code: 'BS-001', slots: { g: { key: 'g', label: '原值', codes: ['1122'] } } }],
    ['slots[].standard_codes', { row_code: 'BS-001', slots: { g: { key: 'g', label: '原值', standard_codes: ['1122'] } } }],
  ])('%s 有值 → 不判 absent', (_label, src) => {
    expect(isTbSourceAbsent(src)).toBe(false)
  })

  it('段/槽存在但码全空 → 仍判 absent（段化解析的 absent 形态）', () => {
    expect(isTbSourceAbsent({
      row_code: 'BS-037',
      segments: [{ segment: 'cost', standard: [], original: [] }],
    })).toBe(true)
    expect(isTbSourceAbsent({
      row_code: 'BS-037',
      slots: { g: { key: 'g', label: '原值', codes: [], standard_codes: [] } },
    })).toBe(true)
  })
})

describe('「后端算过」的三种元信息任一存在即可判 absent', () => {
  it.each<[string, TbSourceCodes]>([
    ['row_code', { row_code: 'BS-037' }],
    ['formula', { formula: "TB('1911','期末余额')" }],
    ['signed_codes', { signed_codes: [['1911', 1]] }],
  ])('只有 %s 也判 absent', (_label, src) => {
    expect(isTbSourceAbsent(src)).toBe(true)
  })

  it('resolved_from=none 且码全空 → 判 absent（另一条真实路径）', () => {
    expect(isTbSourceAbsent({ row_code: 'BS-009', resolved_from: 'none', gross: [] })).toBe(true)
  })
})

describe('tbAbsentCodesText：报表公式引用但科目表缺失的码', () => {
  it('I5-1 真实载荷取出 1911（signed_codes 与 diagnostics 去重）', () => {
    expect(tbAbsentCodesText(I5_REAL)).toBe('1911')
  })

  it('多个码按出现顺序以「、」连接', () => {
    expect(tbAbsentCodesText({
      signed_codes: [['1701', 1], ['1702', -1]],
    })).toBe('1701、1702')
  })

  it('只有 diagnostics.unclaimed 时也能取出', () => {
    expect(tbAbsentCodesText({
      diagnostics: [{ kind: 'unclaimed', code: '1911' }],
    })).toBe('1911')
  })

  it('非 unclaimed 的 diagnostics 不计入（chart_conflict / row_name_mismatch）', () => {
    expect(tbAbsentCodesText({
      diagnostics: [
        { kind: 'chart_conflict', code: '1234' },
        { kind: 'row_name_mismatch', code: '5678' },
      ],
    })).toBe('')
  })

  it('空载荷返回空串（调用方据此走「没有可定位科目」文案）', () => {
    expect(tbAbsentCodesText(null)).toBe('')
    expect(tbAbsentCodesText({})).toBe('')
  })
})

describe('面板可见性判据（三态合成）', () => {
  /** 与 `WpFourTableSourcePanel.visible` 同构（不含 extra 槽那一项） */
  const visible = (src: TbSourceCodes | null) =>
    hasTbSourceCodes(src) || isTbSourceAbsent(src)

  it('absent 态必须可见（旧行为在此隐藏 ⇒ 审计师看到一片空白）', () => {
    expect(visible(I5_REAL)).toBe(true)
  })

  it('已取数态可见', () => {
    expect(visible(I1_REAL)).toBe(true)
  })

  it('未下发态不可见（保留「禁空洞卡片」口径）', () => {
    expect(visible(null)).toBe(false)
    expect(visible({})).toBe(false)
  })
})
