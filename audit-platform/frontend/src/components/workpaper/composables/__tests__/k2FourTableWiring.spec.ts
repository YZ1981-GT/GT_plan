/**
 * K2 科目口径 + 动态行 + 溯源接线守卫。
 *
 * 🔴 锁死一条实测缺陷：全循环把**应收款项坏账准备 `1231`** 当成其他流动资产。
 * `report_config` 实证 `BS-014 其他流动资产 = TB('1901','期末余额')`。
 * 错误科目不只让数字错，还让「从序时账导入」把坏账准备子科目导进 K2-2、
 * 抽凭引擎抽坏账准备的凭证、`writebackTB` 往 `1231` 写审定数（覆盖 D1/D2/K1）。
 *
 * spec: .kiro/specs/k2-four-table-extraction-and-dynamic-rows/ Task 3.4 / 4.2
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ref } from 'vue'
import {
  K2_ACCOUNT_NAME,
  K2_EXCLUDED_STANDARD_CODES,
  K2_GROSS_FALLBACK_STANDARD,
  K2_REPORT_ROW_CODE,
  K2_WRONG_LEGACY_ACCOUNT,
  k2AccountCode,
  k2GrossQueryCodes,
} from '../k2AccountScope'
import {
  K2_ADJ_PREFIX,
  K2_ADJ_ROWS_SPEC,
  K2_ADJ_VALUE_FIELDS,
  K2_LEGACY_ROWS,
  K2_TEMPLATE_ROW_EXAMPLES,
} from '../k2AdjudicationRows'
import { rowFieldItemId, rowsItemId, serializeRows } from '../shared/dynamicAdjudicationRows'
import { useK2Adjudication } from '../useK2Adjudication'
import { K2_DISCLOSURE_SHEET_NAME } from '../k2NoteSectionMap'

const ROOT = resolve(__dirname, '../..')

function read(rel: string): string {
  return readFileSync(resolve(ROOT, rel), 'utf-8')
}

/** 去掉注释后再做「源码不得出现 xxx」类断言（否则说明性注释会被数成真实调用） */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

function mapOf(entries: Record<string, string>) {
  const m = new Map<string, any>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, { item_id: k, conclusion: null, remark: v })
  }
  return m
}

// ─── 科目口径单一真源 ───────────────────────────────────────────────────────

describe('K2 科目口径单一真源（Requirements 1.1~1.3）', () => {
  it('报表行是 BS-014，兜底标准码是 1901', () => {
    expect(K2_REPORT_ROW_CODE).toBe('BS-014')
    expect(K2_GROSS_FALLBACK_STANDARD).toBe('1901')
    expect(K2_ACCOUNT_NAME).toBe('其他流动资产')
    expect(K2_GROSS_FALLBACK_STANDARD).not.toBe(K2_WRONG_LEGACY_ACCOUNT)
  })

  it('1131 应收股利声明为「不并入」（已属 BS-009/K1）', () => {
    expect(K2_EXCLUDED_STANDARD_CODES).toContain('1131')
    expect(K2_EXCLUDED_STANDARD_CODES).not.toContain(K2_GROSS_FALLBACK_STANDARD)
  })

  it('溯源存在时用溯源口径，缺失时回退 1901', () => {
    expect(k2GrossQueryCodes(null)).toEqual(['1901'])
    expect(k2GrossQueryCodes({ gross_standard: [] })).toEqual(['1901'])
    expect(k2GrossQueryCodes({ gross_standard: ['1901', '1901-01'] })).toEqual(['1901', '1901-01'])
    expect(k2AccountCode(undefined)).toBe('1901')
    expect(k2AccountCode({ gross_standard: ['1901-02'] })).toBe('1901-02')
  })

  it('🔴 任何回退路径都不得返回坏账准备族', () => {
    for (const src of [null, undefined, {}, { gross_standard: [] }, { gross_standard: [''] }]) {
      const codes = k2GrossQueryCodes(src as any)
      expect(codes.some((c) => c.startsWith(K2_WRONG_LEGACY_ACCOUNT))).toBe(false)
    }
  })
})

// ─── 源码不得残留硬编码 1231（反向自检） ────────────────────────────────────

describe('K2 源码不得把 1231 当科目码（反向自检）', () => {
  const FILES = [
    'GtK2OtherCurrentAssets.vue',
    'k2/core/K2TabAdjudication.vue',
    'k2/core/K2TabDetail.vue',
    'k2/core/K2TabAdjustment.vue',
    'k2/core/K2TabDisclosureListed.vue',
    'k2/core/K2TabDisclosureSoe.vue',
    'k2/inspection/K2TabCheck.vue',
    'k2/amortization/K2TabAmortization.vue',
    'k2/amortization/K2TabContractCost.vue',
    'composables/useK2FormData.ts',
  ]

  it.each(FILES)('%s 不含 1231 字面量作科目码 / 请求参数 / 事件载荷', (rel) => {
    const body = stripComments(read(rel))
    // 反向自检：文件确实读到了（防路径写错导致断言空转）
    expect(body.length).toBeGreaterThan(200)
    expect(body).not.toMatch(/account_prefix:\s*'1231'/)
    expect(body).not.toMatch(/accountCode:\s*'1231'/)
    expect(body).not.toMatch(/account_code:\s*'1231'/)
    expect(body).not.toMatch(/account-code="1231"/)
    expect(body).not.toMatch(/=\s*'1231'/)
    expect(body).not.toMatch(/startsWith\('1231'\)/)
  })

  it('宿主读 render 下发溯源并透传给四个 Tab', () => {
    const host = read('GtK2OtherCurrentAssets.vue')
    expect(host).toMatch(/htmlData\?\.tb_source_codes/)
    // K2-1 / K2-2 / K2-3 / K2-6 都需要科目口径
    expect(host.match(/:tb-source-codes="tbSourceCodes"/g)?.length).toBeGreaterThanOrEqual(4)
  })

  it('审定表 Tab 渲染溯源面板（tb_source_codes 不是 dead output）', () => {
    const tab = read('k2/core/K2TabAdjudication.vue')
    expect(tab).toMatch(/<K2FourTableSourcePanel/)
    expect(tab).toMatch(/tbSourceCodes\?:\s*TbSourceCodes/)
  })

  it('溯源面板是共用件薄壳（不复制第二份面板实现）', () => {
    const panel = read('k2/core/K2FourTableSourcePanel.vue')
    expect(panel).toMatch(/WpFourTableSourcePanel/)
    // 其他流动资产无备抵科目 → 不得声明 provisionLabel
    expect(panel).not.toMatch(/provision-label/)
    const k1 = read('k1/core/K1FourTableSourcePanel.vue')
    expect(k1).toMatch(/WpFourTableSourcePanel/)
    expect(k1).toMatch(/provision-label="坏账准备"/)
  })

  it('披露两版 AI 的 context 必须是对象（传字符串必 422 且被静默吞）', () => {
    for (const rel of ['k2/core/K2TabDisclosureListed.vue', 'k2/core/K2TabDisclosureSoe.vue']) {
      const body = stripComments(read(rel))
      expect(body).toMatch(/context:\s*\{/)
      // 反向自检：不得再出现 `context: \`...\`` / `context: '...'` 形态
      expect(body).not.toMatch(/context:\s*[`'"]/)
    }
  })
})

// ─── K2-1 动态行 spec 声明 ──────────────────────────────────────────────────

describe('K2-1 动态行规格声明', () => {
  it('前缀与字段集正确，清单键为 K2-1-rows', () => {
    expect(K2_ADJ_PREFIX).toBe('K2-1')
    expect(rowsItemId(K2_ADJ_ROWS_SPEC)).toBe('K2-1-rows')
    expect(rowFieldItemId(K2_ADJ_ROWS_SPEC, 'contract-cost', 'unadj')).toBe(
      'K2-1-contract-cost-unadj',
    )
    expect([...K2_ADJ_VALUE_FIELDS]).toEqual(K2_ADJ_ROWS_SPEC.valueFields)
  })

  it('历史固定行 8 条，rowKey 与旧实现逐字一致（迁移零丢数的前提）', () => {
    expect(K2_LEGACY_ROWS.map((r) => r.key)).toEqual([
      'contract-cost', 'prepayment', 'deferred-expense', 'tax-deductible',
      'contract-asset', 'deposit', 'receivable-transfer', 'other',
    ])
    expect(K2_LEGACY_ROWS.map((r) => r.label)).toEqual([
      '合同取得成本', '预付款项', '待摊费用', '待抵扣税额',
      '合同资产', '押金保证金', '应收款项转让', '其他',
    ])
  })

  it('历史行是 K2 自己的二级子明细 —— 不得被标成「别的循环科目」', () => {
    // 共享件已移除 foreignWarning 机制；此处正向锁死：spec 只声明 key/label 两字段
    for (const r of K2_LEGACY_ROWS) {
      expect(Object.keys(r).sort()).toEqual(['key', 'label'])
    }
    const src = read('composables/k2AdjudicationRows.ts')
    expect(src).not.toMatch(/foreignWarning/)
    expect(src).not.toMatch(/口径存疑/)
    // 反向自检：文件确实声明了这 8 行（防断言空转）
    expect(src).toContain('receivable-transfer')
  })

  it('源模板示例项目仅作输入提示，不得成为固定行', () => {
    expect(K2_TEMPLATE_ROW_EXAMPLES).toEqual([
      '待摊费用', '待抵扣进项税', '房租物业费', '预缴企业所得税',
      '委托贷款', '预缴其他税费', '应收退货成本',
    ])
    // 示例是源模板举的例子，与历史 8 行不重合（两者都只是二级子明细的举例）
    expect(K2_TEMPLATE_ROW_EXAMPLES.length).toBe(7)
  })

  it('🔴 useK2Adjudication 不得再有硬编码 8 行枚举', () => {
    const body = stripComments(read('composables/useK2Adjudication.ts'))
    expect(body.length).toBeGreaterThan(500)
    expect(body).not.toMatch(/K2_ADJ_ITEMS/)
    // 旧实现的「未命中一律塞 other」兜底必须消失
    expect(body).not.toMatch(/matchKey\s*=\s*'other'/)
    expect(body).not.toMatch(/label\.includes\(pName\)/)
  })
})

// ─── 动态行运行时行为 ───────────────────────────────────────────────────────

describe('useK2Adjudication 动态行行为', () => {
  function setup(entries: Record<string, string> = {}, prefill?: any[]) {
    const saved: Record<string, string> = {}
    const removed: string[] = []
    const map = ref(mapOf(entries))
    const api = useK2Adjudication(map as any, {
      prefill: ref(prefill) as any,
      onSave: (id, v) => { saved[id] = String(v) },
      onRemove: (ids) => { removed.push(...ids) },
    })
    return { api, map, saved, removed }
  }

  it('无持久化清单 + 无历史数据 → 空表（宁缺勿造，不预置 8 行）', () => {
    const { api } = setup()
    expect(api.rows.value).toHaveLength(0)
    expect(api.subtotalRow.value.audited).toBe(0)
  })

  it('历史固定行有数据 → 自动迁移并落库清单，金额零丢失', () => {
    const { api, saved } = setup({
      'K2-1-contract-cost-begin': '100000',
      'K2-1-contract-cost-unadj': '115000',
      'K2-1-contract-cost-aje': '2000',
      'K2-1-deposit-unadj': '50000',
    })
    expect(api.rows.value.map((r) => r.rowKey)).toEqual(['contract-cost', 'deposit'])
    expect(api.rows.value[0].begin).toBe(100000)
    expect(api.rows.value[0].audited).toBe(117000)
    expect(api.rows.value.every((r) => r.source === 'legacy')).toBe(true)
    expect(saved['K2-1-rows']).toBeTruthy()
    // 迁移来的二级子明细行同样可改名 / 可删除（与手工行无差别）
    expect(api.renameRow('deposit', '押金及保证金').ok).toBe(true)
    expect(api.removeRow('contract-cost').ok).toBe(true)
  })

  it('合计覆盖全部动态行（Property 9）', () => {
    const { api } = setup({
      'K2-1-rows': serializeRows([
        { rowId: 'r-1', label: '待摊费用', source: 'manual' },
        { rowId: 'r-2', label: '待抵扣进项税', source: 'manual' },
        { rowId: 'r-3', label: '委托贷款', source: 'manual' },
      ]),
      'K2-1-r-1-begin': '100', 'K2-1-r-1-debit': '20', 'K2-1-r-1-credit': '5',
      'K2-1-r-1-unadj': '115', 'K2-1-r-1-aje': '2', 'K2-1-r-1-rje': '-1',
      'K2-1-r-2-begin': '50', 'K2-1-r-2-unadj': '52',
      'K2-1-r-3-begin': '30', 'K2-1-r-3-credit': '10', 'K2-1-r-3-unadj': '20',
    })
    const st = api.subtotalRow.value
    expect(api.rows.value).toHaveLength(3)
    expect(st.begin).toBe(180)
    expect(st.debit).toBe(20)
    expect(st.credit).toBe(15)
    expect(st.end).toBe(185)          // 180 + 20 − 15
    expect(st.unadjusted).toBe(187)
    expect(st.aje).toBe(2)
    expect(st.rje).toBe(-1)
    expect(st.audited).toBe(188)
    expect(st.label).toBe('合计')
  })

  it('新增行：撞名拒绝，成功后清单落库', () => {
    const { api, saved } = setup()
    expect(api.addRow('待摊费用').ok).toBe(true)
    expect(api.addRow(' 待  摊 费用 ').ok).toBe(false)
    expect(api.addRow('').ok).toBe(false)
    expect(api.rows.value).toHaveLength(1)
    expect(saved['K2-1-rows']).toContain('待摊费用')
  })

  it('改名：撞名拒绝；同名 no-op；成功后行名更新', () => {
    const { api } = setup()
    const a = api.addRow('甲').rowId!
    api.addRow('乙')
    expect(api.renameRow(a, '乙').ok).toBe(false)
    expect(api.renameRow(a, '甲').ok).toBe(true)
    expect(api.renameRow(a, '丙').ok).toBe(true)
    expect(api.rows.value.find((r) => r.rowKey === a)?.label).toBe('丙')
  })

  it('删除行：清理该行全部字段键，其它行不受影响（Property 7）', () => {
    const { api, map, removed } = setup({
      'K2-1-rows': serializeRows([
        { rowId: 'r-1', label: '甲', source: 'manual' },
        { rowId: 'r-2', label: '乙', source: 'manual' },
      ]),
      'K2-1-r-1-unadj': '100', 'K2-1-r-1-remark': 'x',
      'K2-1-r-2-unadj': '200',
    })
    expect(api.rowItemIds('r-1')).toHaveLength(2)
    expect(api.removeRow('r-1').ok).toBe(true)
    expect(api.rows.value.map((r) => r.rowKey)).toEqual(['r-2'])
    expect(map.value.has('K2-1-r-1-unadj')).toBe(false)
    expect(map.value.has('K2-1-r-2-unadj')).toBe(true)
    expect(removed.sort()).toEqual(['K2-1-r-1-remark', 'K2-1-r-1-unadj'])
    expect(api.removeRow('r-1').ok).toBe(false)   // 幂等
  })

  it('四表 seed：按叶子科目名建行，手工优先不覆盖（Property 8）', () => {
    const { api } = setup(
      {},
      [
        { name: '待摊费用', code: '1901.01', opening_balance: 100, closing_balance: 250 },
        { name: '待抵扣进项税', code: '1901.02', opening_balance: 0, closing_balance: 80 },
      ],
    )
    expect(api.rows.value.map((r) => r.label)).toEqual(['待摊费用', '待抵扣进项税'])
    expect(api.rows.value[0].begin).toBe(100)
    expect(api.rows.value[0].unadjusted).toBe(250)
    expect(api.rows.value.every((r) => r.source === 'tb')).toBe(true)
  })

  it('🔴 四表 seed 不再把无法匹配的科目塞进「其他」行', () => {
    const { api } = setup(
      {},
      [{ name: '坏账准备_应收账款', code: '1231.02', closing_balance: 26401719.77 }],
    )
    // 宁缺勿造：按科目名建**自己的**行，不堆到「其他」
    expect(api.rows.value.map((r) => r.label)).toEqual(['坏账准备_应收账款'])
    expect(api.rows.value.some((r) => r.label === '其他')).toBe(false)
  })

  it('四表 seed 为空 → 不建任何行', () => {
    expect(setup({}, []).api.rows.value).toHaveLength(0)
    expect(setup({}, undefined).api.rows.value).toHaveLength(0)
  })

  it('刷新取数：默认只补空值（手工优先），overwrite 才覆盖「四表」来源行', () => {
    const { api } = setup(
      {},
      [{ name: '待摊费用', code: '1901.01', opening_balance: 100, closing_balance: 250 }],
    )
    // 审计师手工改了未审数
    const rowId = api.rows.value[0].rowKey
    api.updateField(rowId, 'unadj', 999)
    expect(api.rows.value[0].unadjusted).toBe(999)

    // 默认路径（自动 watch / 「仅补空值」）不覆盖
    api.seedFromPrefill()
    expect(api.rows.value[0].unadjusted).toBe(999)

    // 预演能报出「1 行有变化」
    expect(api.previewSeedFromPrefill()).toMatchObject({ createdCount: 0, changedCount: 1 })

    // 显式刷新 → 该行是 source='tb'，覆盖回四表值
    api.seedFromPrefill({ overwrite: true })
    expect(api.rows.value[0].unadjusted).toBe(250)
  })

  it('刷新取数：手工新增行的录入永不被覆盖', () => {
    const { api } = setup(
      {},
      [{ name: '待摊费用', code: '1901.01', closing_balance: 250 }],
    )
    // 手工行与四表某科目同名之外的独立项目
    const manualId = api.addRow('应收退货成本').rowId!
    api.updateField(manualId, 'unadj', 777)
    api.seedFromPrefill({ overwrite: true })
    expect(api.rows.value.find((r) => r.rowKey === manualId)?.unadjusted).toBe(777)
  })

  it('刷新取数：四表新增子科目 → 动态插行', () => {
    const map = ref(mapOf({}))
    const prefill = ref<any[]>([{ name: '待摊费用', code: '1901.01', closing_balance: 100 }])
    const api = useK2Adjudication(map as any, { prefill: prefill as any })
    expect(api.rows.value).toHaveLength(1)
    // 四表重新入库后多了一个明细子科目
    prefill.value = [
      { name: '待摊费用', code: '1901.01', closing_balance: 100 },
      { name: '预缴企业所得税', code: '1901.02', closing_balance: 55 },
    ]
    api.seedFromPrefill()
    expect(api.rows.value.map((r) => r.label)).toEqual(['待摊费用', '预缴企业所得税'])
    expect(api.rows.value[1].unadjusted).toBe(55)
  })

  it('从 K2-2 明细按行名聚合带入；审定表无该项目时自动建行', () => {
    const { api } = setup({
      'K2-1-rows': serializeRows([{ rowId: 'r-1', label: '待摊费用', source: 'manual' }]),
      'K2-2-rows': JSON.stringify([
        { rowId: 'd1', name: '待摊费用', endBalance: 300 },
        { rowId: 'd2', name: '待 摊 费用', endBalance: 200 },   // 同名合并
        { rowId: 'd3', name: '委托贷款', endBalance: 500 },
        { rowId: 'd4', name: '零余额项目', endBalance: 0 },
      ]),
    })
    const res = api.pullFromDetail()
    expect(res.filled).toBe(2)
    expect(res.created).toBe(1)
    expect(res.unmatched).toEqual(['零余额项目'])
    expect(api.rows.value.find((r) => r.label === '待摊费用')?.unadjusted).toBe(500)
    expect(api.rows.value.find((r) => r.label === '委托贷款')?.unadjusted).toBe(500)
  })

  it('K2-2 无数据 / 载荷损坏 → 返回全 0，不抛', () => {
    expect(setup({}).api.pullFromDetail()).toEqual({ filled: 0, created: 0, unmatched: [] })
    expect(setup({ 'K2-2-rows': 'not json' }).api.pullFromDetail().filled).toBe(0)
    expect(setup({ 'K2-2-rows': '[]' }).api.pullFromDetail().filled).toBe(0)
  })

  it('🔴 「从 K2-2 带入」读的键是 K2-2-rows（旧实现读 K2-2-detail-rows，恒空）', () => {
    const body = stripComments(read('composables/useK2Adjudication.ts'))
    expect(body).toMatch(/'K2-2-rows'/)
    expect(body).not.toMatch(/K2-2-detail-rows/)
    const tab = stripComments(read('k2/core/K2TabAdjudication.vue'))
    expect(tab).not.toMatch(/K2-2-detail-rows/)
  })

  it('三角勾稽在动态行下成立', () => {
    const { api } = setup({
      'K2-1-rows': serializeRows([{ rowId: 'r-1', label: '甲', source: 'manual' }]),
      'K2-1-r-1-begin': '100', 'K2-1-r-1-debit': '30', 'K2-1-r-1-credit': '10',
    })
    expect(api.subtotalRow.value.end).toBe(120)
    expect(api.reconciliation.value.isBalanced).toBe(true)
  })
})

// ─── sheet 名（Property 11） ────────────────────────────────────────────────

describe('披露 sheet 名与源 xlsx tab 名一致（Property 11）', () => {
  it('国企侧是「国企」且括号全角', () => {
    expect(K2_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企）')
    expect(K2_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(K2_DISCLOSURE_SHEET_NAME.soe).not.toContain('国有企业')
    for (const name of Object.values(K2_DISCLOSURE_SHEET_NAME)) {
      expect(name).not.toMatch(/[()]/)
    }
  })
})
