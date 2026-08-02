/**
 * E1 披露内部勾稽守卫 —— Property 14
 *
 * 「勾稽引擎覆盖校验预设全集」：`computeE1Consistency` 返回的规则集合必须覆盖
 * `note_check_preset_formulas.json` 里 E1 两版各 6 条（F1-1~F1-6），且
 * listed / soe 两版都要覆盖（源 JSON 实证两版预设**完全相同**）。
 *
 * 反向自检：断言从真源 JSON 抽出的 id 集合确实是 6 条 F1-*，
 * 防「正则失效 → 期望集合为空 → 断言空转」。
 *
 * spec: e1-four-table-extraction-and-disclosure-alignment / Property 14, Req 9.1 9.2
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  E1_ACCOUNT_CODE,
  E1_ACCOUNT_NAME,
  E1_COVERED_PRESET_IDS,
  buildE1MisstatementPayload,
  computeE1Consistency,
  summarizeE1Consistency,
  type E1ConsistencyInput,
} from '../e1DisclosureConsistency'
import { normalizeMisstatementPushPayload } from '@/composables/useA13MisstatementBridge'

// ─── 真源：校验预设 JSON ────────────────────────────────────────────────
const PRESET_PATH = resolve(
  __dirname,
  '../../../../../../../backend/data/note_check_preset_formulas.json',
)

interface PresetItem {
  id?: string
  note_section?: string
  section_title?: string
  table_name?: string
  formula?: string
}

/** 真源结构实证：`{ soe: PresetItem[], listed: PresetItem[] }`，E1 侧各 6 条 F1-*。 */
function loadE1Presets(variant: 'listed' | 'soe'): PresetItem[] {
  const raw = JSON.parse(readFileSync(PRESET_PATH, 'utf-8')) as Record<string, PresetItem[]>
  const arr = raw[variant] ?? []
  // E1 = 「货币资金」章节的 F1-* 预设（同一 JSON 里 F1-* 前缀也被其他章节复用过，
  // 故必须同时按 section_title 过滤 —— memory 已实证 五、7 下混入过 F65-*/F82-*）
  return arr.filter((it) => /^F1-\d+$/.test(String(it.id ?? '')) && String(it.section_title ?? '') === '货币资金')
}

function loadE1PresetIds(variant: 'listed' | 'soe'): string[] {
  return [...new Set(loadE1Presets(variant).map((it) => String(it.id)))].sort()
}

describe('E1 披露勾稽 — Property 14 覆盖校验预设全集', () => {
  const variants: Array<'listed' | 'soe'> = ['listed', 'soe']

  it('反向自检：真源 JSON 能抽出 6 条 F1-* 货币资金预设（两版相同）', () => {
    for (const v of variants) {
      const ids = loadE1PresetIds(v)
      expect(ids.length, `${v} 侧应抽出 6 条 F1-* 预设，实际 ${ids.join(',')}`).toBe(6)
      expect(ids).toEqual(['F1-1', 'F1-2', 'F1-3', 'F1-4', 'F1-5', 'F1-6'])
    }
    // 两版逐字相同（memory 已实证）
    expect(loadE1PresetIds('listed')).toEqual(loadE1PresetIds('soe'))
  })

  it('反向自检：F1-1~F1-3 挂①分类表、F1-4~F1-6 挂②受限表', () => {
    for (const v of variants) {
      const byId = new Map(loadE1Presets(v).map((it) => [String(it.id), String(it.table_name ?? '')]))
      for (const id of ['F1-1', 'F1-2', 'F1-3']) {
        expect(byId.get(id), `${v}/${id}`).toContain('货币资金分类表')
      }
      for (const id of ['F1-4', 'F1-5', 'F1-6']) {
        expect(byId.get(id), `${v}/${id}`).toContain('受限制的货币资金明细表')
      }
    }
  })

  it('E1_COVERED_PRESET_IDS ⊇ 真源预设 id 全集', () => {
    const covered = new Set(E1_COVERED_PRESET_IDS)
    for (const v of variants) {
      for (const id of loadE1PresetIds(v)) {
        expect(covered.has(id), `${v} 侧预设 ${id} 未被勾稽引擎覆盖`).toBe(true)
      }
    }
  })

  function baseInput(variant: 'listed' | 'soe'): E1ConsistencyInput {
    return {
      variant,
      mainRows: [
        { key: 'cash', label: '现金', endingAmount: 100, openingAmount: 80 },
        { key: 'bank', label: '银行存款', endingAmount: 900, openingAmount: 720 },
        {
          key: 'overseas',
          label: '其中：存放在境外的款项总额',
          endingAmount: 50,
          openingAmount: 40,
          isMemo: true,
        },
        { key: 'total', label: '合计', endingAmount: 1000, openingAmount: 800, isTotal: true },
      ],
      restrictedRows: [
        { label: '保证金', endingAmount: 60, openingAmount: 50 },
        { label: '冻结存款', endingAmount: 40, openingAmount: 30 },
      ],
      reportEnding: 1000,
      reportOpening: 800,
    }
  }

  it.each(variants)('%s：每条 F1-* 规则都产出至少一个条目', (variant) => {
    const results = computeE1Consistency(baseInput(variant))
    for (const id of E1_COVERED_PRESET_IDS) {
      expect(
        results.some((r) => r.label.startsWith(id)),
        `${variant} 侧缺 ${id} 条目`,
      ).toBe(true)
    }
  })

  it.each(variants)('%s：每条规则说明都写明预设出处或源模板公式', (variant) => {
    const results = computeE1Consistency(baseInput(variant))
    expect(results.length).toBeGreaterThan(0)
    for (const r of results) {
      expect(r.rule.length, `规则说明过短：${r.label}`).toBeGreaterThan(15)
      expect(
        /校验预设|源 xlsx|源模板/.test(r.rule),
        `规则 ${r.label} 未标注真源出处`,
      ).toBe(true)
    }
  })

  it.each(variants)('%s：refs 只允许平台索引形态（wp:/tb:/report:）', (variant) => {
    const results = computeE1Consistency(baseInput(variant))
    let refCount = 0
    for (const r of results) {
      for (const ref of r.refs ?? []) {
        refCount += 1
        expect(/^(wp|tb|report|note|aux):/.test(ref), `非法追溯索引 ${ref}`).toBe(true)
      }
    }
    expect(refCount, '应至少有一条追溯索引（否则断言空转）').toBeGreaterThan(0)
  })

  // ─── 数值语义 ───────────────────────────────────────────────────────
  it('F1-1 / F1-2：报表金额 == 主表合计行 → ok；不等 → error', () => {
    const ok = computeE1Consistency(baseInput('soe'))
    expect(ok.find((r) => r.label.startsWith('F1-1'))?.level).toBe('ok')
    expect(ok.find((r) => r.label.startsWith('F1-2'))?.level).toBe('ok')

    const bad = computeE1Consistency({ ...baseInput('soe'), reportEnding: 1234 })
    const f1 = bad.find((r) => r.label.startsWith('F1-1'))
    expect(f1?.level).toBe('error')
    expect(f1?.diff).toBe(234)
  })

  it('报表金额取不到（null）→ F1-1/F1-2 skip 而非误报 0', () => {
    const res = computeE1Consistency({
      ...baseInput('soe'),
      reportEnding: null,
      reportOpening: null,
    })
    expect(res.find((r) => r.label.startsWith('F1-1'))?.level).toBe('skip')
    expect(res.find((r) => r.label.startsWith('F1-2'))?.level).toBe('skip')
  })

  it('F1-3：「其中：」备注行不参与加总（否则 100+900+50 ≠ 1000）', () => {
    const res = computeE1Consistency(baseInput('listed'))
    const f3 = res.filter((r) => r.label.startsWith('F1-3'))
    expect(f3.length).toBe(2)
    for (const r of f3) expect(r.level).toBe('ok')
  })

  it('F1-3：备注行若被误当明细行则会 error（反向自检）', () => {
    const input = baseInput('listed')
    const rows = input.mainRows.map((r) =>
      r.key === 'overseas' ? { ...r, isMemo: false } : r,
    )
    const res = computeE1Consistency({ ...input, mainRows: rows })
    expect(res.find((r) => r.label.startsWith('F1-3'))?.level).toBe('error')
  })

  it('F1-4：②表合计由引擎按明细求和 → 恒成立；明细为空则不产出该条', () => {
    const withRows = computeE1Consistency(baseInput('soe'))
    for (const r of withRows.filter((x) => x.label.startsWith('F1-4'))) {
      expect(r.level).toBe('ok')
    }
    const noRows = computeE1Consistency({ ...baseInput('soe'), restrictedRows: [] })
    expect(noRows.some((r) => r.label.startsWith('F1-4'))).toBe(false)
  })

  it('F1-5 / F1-6：拿不到补充资料③表数据 → skip 且规则里给出推算值', () => {
    const res = computeE1Consistency(baseInput('soe'))
    const f5 = res.find((r) => r.label.startsWith('F1-5'))
    expect(f5?.level).toBe('skip')
    // 推算值 = 报表货币资金 1000 − 受限合计 100 = 900
    expect(f5?.rule).toContain('900')
    expect(f5?.rule).toContain('人工核对')
  })

  it('F1-5：提供补充资料③表数据 → 真实比对（1000 − 900 = 100 == 受限合计）', () => {
    const res = computeE1Consistency({
      ...baseInput('soe'),
      cashEquivalentsEnding: 900,
      cashEquivalentsOpening: 720,
    })
    const f5 = res.find((r) => r.label.startsWith('F1-5'))
    expect(f5?.level).toBe('ok')
    const f6 = res.find((r) => r.label.startsWith('F1-6'))
    // 800 − 720 = 80 == 受限期初合计 80
    expect(f6?.level).toBe('ok')
  })

  it('外币原币表未启用（fxRows 为空）→ 不产出源模板 B16 / 分组小计条目', () => {
    const res = computeE1Consistency(baseInput('listed'))
    expect(res.some((r) => r.label.includes('B16'))).toBe(false)
    expect(res.some((r) => r.label.startsWith('原币表分组小计'))).toBe(false)
  })

  it('🔴 外币区两变体都渲染 + 两变体都传 fxRows（原「上市专属」判断已推翻）', () => {
    // 原断言锁的是「国企侧不得传 fxRows」，理由写成「源 xlsx 的外币原币表只在
    // 附注披露信息(上市公司)，国企版没有这两张表」。
    //
    // 🔴 2026-08-02 openpyxl 逐格实证**推翻**该理由：两张披露 sheet 的 R25~R62
    // （「外币性货币项目」+「货币资金（原币）」）**逐字相同** —— 表名 / 两级表头 /
    // 四个分组（库存现金·银行存款·银行存款中：财务公司存款·其他货币资金）/
    // 五个币种 / 合计公式全同，只有 R17 汇率中间价提示块是上市侧独有。
    // 而国企 sheet 的勾稽单元格 R12 列 E 正是
    // `=B12-'附注披露信息(上市公司)'!D62`（主表合计 − 原币表人民币合计），
    // 反证国企版同样要求填这两张表。
    //
    // 假「不一致」的真因是**组件把外币区 `v-if` 到了上市变体** → 国企 Tab 拿到
    // 未渲染的默认骨架（金额全 0）。根因已修：外币区两变体都渲染。
    const src = readFileSync(
      resolve(__dirname, '../../e1/E1TabDisclosure.vue'),
      'utf-8',
    ).replace(/<!--[\s\S]*?-->/g, '').replace(/\/\*[\s\S]*?\*\//g, '')
    expect(src, 'fxRows 不得再按变体门控').not.toMatch(
      /fxRows:\s*\n?\s*variant\.value === 'listed'/,
    )
    // 外币表本体（`foreignCurrencyRows` 驱动的 el-table）不得被 variant 包住
    expect(src).toMatch(/:data="foreignCurrencyRows"/)
    const fxTableIdx = src.indexOf(':data="foreignCurrencyRows"')
    const gateIdx = src.lastIndexOf("variant === 'listed'", fxTableIdx)
    if (gateIdx >= 0) {
      // 上市专属的只能是汇率提示块 → 门控与表体之间必须已闭合
      const between = src.slice(gateIdx, fxTableIdx)
      expect(between, '外币表体仍被上市门控包着').toMatch(/<\/template>/)
    }

    // 引擎侧：给了真实原币表数据就产出 B16，soe 同样适用（引擎本就变体无关）
    const rows = [
      { groupSlot: 'cash', currencyKey: '', currencyLabel: '库存现金：', isGroup: true, endRmb: 1000, endForeign: null },
      { groupSlot: 'cash', currencyKey: 'CNY', currencyLabel: '人民币', isGroup: false, endRmb: 1000, endForeign: 1000 },
    ]
    for (const variant of ['listed', 'soe'] as const) {
      const res = computeE1Consistency({ ...baseInput(variant), fxRows: rows })
      expect(res.some((r) => r.label.includes('B16')), `${variant} 应产出 B16`).toBe(true)
    }
  })

  it('外币原币表启用 → B16 主表合计 vs 原币表人民币合计 + 分组小计', () => {
    const res = computeE1Consistency({
      ...baseInput('listed'),
      fxRows: [
        {
          groupSlot: 'cash',
          currencyKey: '',
          currencyLabel: '库存现金',
          isGroup: true,
          endRmb: 100,
          endForeign: null,
        },
        {
          groupSlot: 'cash',
          currencyKey: 'USD',
          currencyLabel: '美元',
          isGroup: false,
          endRmb: 100,
          endForeign: 14,
        },
        {
          groupSlot: 'bank',
          currencyKey: '',
          currencyLabel: '银行存款',
          isGroup: true,
          endRmb: 900,
          endForeign: null,
        },
        {
          groupSlot: 'bank',
          currencyKey: 'EUR',
          currencyLabel: '欧元',
          isGroup: false,
          endRmb: 900,
          endForeign: 115,
        },
      ],
    })
    const b16 = res.find((r) => r.label.includes('B16'))
    expect(b16?.level).toBe('ok')
    const groups = res.filter((r) => r.label.startsWith('原币表分组小计'))
    expect(groups.length).toBe(2)
    for (const g of groups) expect(g.level).toBe('ok')
  })

  it('汇总：全 ok 且有条目 → allPassed；有 error → 不通过', () => {
    const ok = summarizeE1Consistency(
      computeE1Consistency({
        ...baseInput('soe'),
        cashEquivalentsEnding: 900,
        cashEquivalentsOpening: 720,
      }),
    )
    expect(ok.error).toBe(0)
    expect(ok.allPassed).toBe(true)

    const bad = summarizeE1Consistency(
      computeE1Consistency({ ...baseInput('soe'), reportEnding: 1 }),
    )
    expect(bad.error).toBeGreaterThan(0)
    expect(bad.allPassed).toBe(false)
  })

  // ─── 勾稽差异 → A13 错报 ────────────────────────────────────────────────
  describe('buildE1MisstatementPayload', () => {
    /** 造一份含 error 的结果（报表期末 1234 vs 主表合计 1000 → 差 234） */
    function withError() {
      return computeE1Consistency({ ...baseInput('soe'), reportEnding: 1234 })
    }

    it('全通过时返回 null（不发空事件）', () => {
      const clean = computeE1Consistency({
        ...baseInput('soe'),
        cashEquivalentsEnding: 900,
        cashEquivalentsOpening: 720,
      })
      expect(summarizeE1Consistency(clean).error).toBe(0)
      expect(buildE1MisstatementPayload(clean)).toBeNull()
    })

    it('只推 error 级；skip（跨底稿取数未就绪）绝不推', () => {
      const res = withError()
      expect(res.some((r) => r.level === 'skip')).toBe(true)
      const p = buildE1MisstatementPayload(res)!
      expect(p).not.toBeNull()
      for (const it of p.items) {
        const src = res.find((r) => it.description.includes(r.label))!
        expect(src.level).toBe('error')
      }
    })

    it('金额取 |diff| 且 ≤0.01 不推（桥也会丢弃 amount≤0）', () => {
      const p = buildE1MisstatementPayload(withError())!
      expect(p.items.some((it) => it.amount === 234)).toBe(true)
      for (const it of p.items) expect(it.amount).toBeGreaterThan(0.01)
    })

    it('labels 指定时只推那条，且仍只推真差异（不把 ok/skip 当错报）', () => {
      const res = withError()
      const errLabel = res.find((r) => r.level === 'error')!.label
      const okLabel = res.find((r) => r.level === 'ok')!.label
      const one = buildE1MisstatementPayload(res, { labels: [errLabel] })!
      expect(one.items).toHaveLength(1)
      expect(one.items[0].description).toContain(errLabel)
      // 指定一个 ok 条目 → 不产出（防单行推送把非差异也推进错报汇总）
      expect(buildE1MisstatementPayload(res, { labels: [okLabel] })).toBeNull()
    })

    it('描述内联规则 label / 两侧金额 / 规则原文，便于错报汇总溯源', () => {
      const p = buildE1MisstatementPayload(withError())!
      const d = p.items[0].description
      expect(d).toContain('货币资金披露勾稽差异')
      expect(d).toContain('F1-1')
      expect(d).toContain('校验预设')
      expect(d).toContain('1234')
      expect(d).toContain('1000')
    })

    it('科目 / wpCode / indexRef 齐备（写入 source_wp_code 溯源）', () => {
      const p = buildE1MisstatementPayload(withError())!
      expect(p.wpCode).toBe('E1')
      expect(p.accountCode).toBe(E1_ACCOUNT_CODE)
      expect(p.accountName).toBe(E1_ACCOUNT_NAME)
      for (const it of p.items) {
        expect(it.wpCode).toBe('E1')
        expect(it.wpCode.slice(0, 20)).toBe('E1')
        expect(it.indexRef).toContain('wp:E1-1')
      }
    })

    it('🔴 载荷能被平台桥 normalizeMisstatementPushPayload 正确归一（形态 A）', () => {
      const p = buildE1MisstatementPayload(withError())!
      const drafts = normalizeMisstatementPushPayload(p)
      expect(drafts.length).toBe(p.items.length)
      for (const d of drafts) {
        expect(d.amount).toBeGreaterThan(0)
        expect(d.description.length).toBeGreaterThan(0)
      }
    })

    it('纯函数：同输入同输出', () => {
      const res = withError()
      expect(buildE1MisstatementPayload(res)).toEqual(buildE1MisstatementPayload(res))
    })
  })
})
