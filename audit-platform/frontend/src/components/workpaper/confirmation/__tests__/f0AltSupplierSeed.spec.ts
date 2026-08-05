/**
 * f0AltSupplierSeed.spec.ts — 「从汇总表带入替代程序」的 aux 余额校准守卫
 *
 * 🔴 Task 25 返工说明：
 * 上一轮把 aux 匹配能力写在 `f0AltSupplierSeed.ts`（零消费方，F0-5/F0-6 实际用的是
 * 既有 `importUnrepliedAsCompanies`）→ 本轮删该模块，能力并入
 * `coordination/importFromSummary.ts`，使 D0/F0/G0/H0/K0/L0 六循环全部受益。
 *
 * 覆盖：
 * - Property 2.3: aux 命中时用精确账面余额，未命中回退汇总表发函金额
 * - 匹配优先级：精确 > 双向包含（≥4 字符）
 * - 科目前缀限定生效
 * - `_balance_source` 溯源标记正确
 * - 源码级：F0-5/F0-6 必须真的传了 auxAccountCode（防又变成零消费方能力）
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  matchAuxBalance,
  mapSummaryToAlternativeCompany,
  defaultUnrepliedFilter,
  pickAuxType,
  type AuxBalanceRow,
  type SummaryRow,
} from '../coordination/importFromSummary'

const __dirname_ = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname_, '../../../../../../..')

function readSource(rel: string): string {
  return readFileSync(resolve(REPO_ROOT, rel), 'utf-8')
}

/**
 * 剥掉注释后再做「不得出现 X」类断言。
 *
 * 🔴 本轮实测踩中（memory 已记的同款坑）：被守卫文件的**踩坑说明注释**里必然会写出
 * 被禁的字面量（如「原实现写 `const { data } = await api.get(...)`」「不得残留
 * 『从 D0-1 带入』」），不剥注释则守卫对自己的修复说明打红 —— 红的是注释、不是代码。
 *
 * 按区处理：先删块注释，再删行注释（行注释判据须排除 `://` 这类 URL 中的双斜杠）。
 */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const AUX_ROWS: AuxBalanceRow[] = [
  { auxName: '供应商A', accountCode: '1123.01', closingBalance: 12000 },
  { auxName: '供应商B有限公司', accountCode: '2202.01', closingBalance: 25000 },
  { auxName: '供应商E', accountCode: '1123.02', closingBalance: 7000 },
]

function makeSummaryRow(o: Partial<SummaryRow>): SummaryRow {
  return { _row_id: Math.random().toString(36).slice(2), ...o } as SummaryRow
}

// ─── Property 2.3: aux 优先、未命中回退 ──────────────────────────────────────

describe('Property 2.3: aux 精确余额优先于汇总表发函金额', () => {
  it('aux 命中 → closing_balance 用 aux 值，_balance_source=aux', () => {
    const row = makeSummaryRow({ entity_name: '供应商A', account_type: '预付账款', amount: 10000 })
    const c = mapSummaryToAlternativeCompany(row, '', AUX_ROWS, '1123')
    expect(c.balance.closing_balance).toBe(12000) // aux 精确值，非发函金额 10000
    expect(c._balance_source).toBe('aux')
  })

  it('aux 未命中 → 回退发函金额，_balance_source=summary', () => {
    const row = makeSummaryRow({ entity_name: '未知供应商XYZ', account_type: '预付账款', amount: 7777 })
    const c = mapSummaryToAlternativeCompany(row, '', AUX_ROWS, '1123')
    expect(c.balance.closing_balance).toBe(7777)
    expect(c._balance_source).toBe('summary')
  })

  it('不传 auxRows → 行为与改造前逐字一致（零回归）', () => {
    const row = makeSummaryRow({ entity_name: '供应商A', account_type: '预付账款', amount: 10000 })
    const c = mapSummaryToAlternativeCompany(row, '')
    expect(c.balance.closing_balance).toBe(10000)
    expect(c._balance_source).toBe('summary')
    expect(c.entity_name).toBe('供应商A')
    expect(c._source).toBe('auto')
  })

  it('空 auxRows 数组 → 回退发函金额', () => {
    const row = makeSummaryRow({ entity_name: '供应商A', amount: 500 })
    const c = mapSummaryToAlternativeCompany(row, '预付账款', [], '1123')
    expect(c.balance.closing_balance).toBe(500)
    expect(c._balance_source).toBe('summary')
  })

  it('item_name 缺省时用 defaultItemName', () => {
    const row = makeSummaryRow({ entity_name: 'X', amount: 1 })
    expect(mapSummaryToAlternativeCompany(row, '应付账款').balance.item_name).toBe('应付账款')
  })
})

// ─── matchAuxBalance 匹配优先级 ──────────────────────────────────────────────

describe('matchAuxBalance', () => {
  it('精确匹配优先', () => {
    expect(matchAuxBalance('供应商A', AUX_ROWS, '1123')).toBe(12000)
  })

  it('双向包含匹配（aux 名含 summary 名）', () => {
    expect(matchAuxBalance('供应商B', AUX_ROWS, '2202')).toBe(25000)
  })

  // ─── P0-1：跨子科目 / 跨维度组合求和（真实数据驱动） ──────────────────────

  it('🔴 同一单位横跨多个子科目 → 全部求和（原 .find() 只取第一条 = 少算）', () => {
    // 真实形态（`2aa00f57` / 2025 / 2202）：某客户横跨 .01/.02/.03/.97/.98 五个子科目，
    // 只有 .98 带金额 → 若 .find() 命中 .01（0）就会把该单位期末余额显示成 0
    const aux: AuxBalanceRow[] = [
      { auxName: '甲公司', accountCode: '2202.01', closingBalance: 0 },
      { auxName: '甲公司', accountCode: '2202.02', closingBalance: 0 },
      { auxName: '甲公司', accountCode: '2202.03', closingBalance: 0 },
      { auxName: '甲公司', accountCode: '2202.97', closingBalance: 0 },
      { auxName: '甲公司', accountCode: '2202.98', closingBalance: -5143381.25 },
    ]
    expect(matchAuxBalance('甲公司', aux, '2202')).toBe(-5143381.25)
  })

  it('🔴 同一(科目码,单位名)的多行是不同维度组合，必须全加不得去重', () => {
    // 真实形态（active dataset 内 4 行，`aux_dimensions_raw` 各为不同成本中心）：
    //   客户+采购部 2,601,247.80 / 客户+渝北总店 268,355.69 / 长寿美丽泽京店 0 / 集团内外 0
    // 合计 2,869,603.49 —— 按 `科目码|单位名` 去重只会留一条 → 丢钱
    const aux: AuxBalanceRow[] = [
      { auxName: '乙公司', accountCode: '2202.02', closingBalance: 2601247.80 },
      { auxName: '乙公司', accountCode: '2202.02', closingBalance: 268355.69 },
      { auxName: '乙公司', accountCode: '2202.02', closingBalance: 0 },
      { auxName: '乙公司', accountCode: '2202.02', closingBalance: 0 },
    ]
    expect(matchAuxBalance('乙公司', aux, '2202')).toBe(2869603.49)
  })

  it('🔴 包含匹配命中多个不同单位时返回 undefined（不得把别人的钱加进来）', () => {
    // 真实形态：`重庆和平药房连锁有限责任公司医药保健品分公司` 与
    // `重庆市黔江区和平药房连锁有限责任公司` 都含「和平药房连锁有限责任公司」
    const aux: AuxBalanceRow[] = [
      { auxName: '重庆和平药房连锁有限责任公司医药保健品分公司', accountCode: '2202.98', closingBalance: -5143381.25 },
      { auxName: '重庆市黔江区和平药房连锁有限责任公司', accountCode: '2202.98', closingBalance: -999999 },
    ]
    expect(matchAuxBalance('和平药房连锁有限责任公司', aux, '2202')).toBeUndefined()
  })

  it('包含匹配唯一命中时仍求和（同一单位多行）', () => {
    const aux: AuxBalanceRow[] = [
      { auxName: '丙公司北京分公司', accountCode: '2202.01', closingBalance: 100 },
      { auxName: '丙公司北京分公司', accountCode: '2202.02', closingBalance: 200 },
    ]
    expect(matchAuxBalance('丙公司北京分公司XX', aux, '2202')).toBe(300)
  })

  it('反向自检：去重版实现会得到不同（更小）的结果', () => {
    const aux: AuxBalanceRow[] = [
      { auxName: '乙公司', accountCode: '2202.02', closingBalance: 2601247.80 },
      { auxName: '乙公司', accountCode: '2202.02', closingBalance: 268355.69 },
    ]
    // 复现「按 科目码|单位名 去重」的旧写法
    const seen = new Map<string, number>()
    for (const r of aux) {
      const k = `${r.accountCode}|${r.auxName}`
      if (!seen.has(k)) seen.set(k, r.closingBalance)
    }
    const deduped = [...seen.values()].reduce((s, v) => s + v, 0)
    expect(deduped).toBe(2601247.80)
    expect(matchAuxBalance('乙公司', aux, '2202')).toBe(2869603.49)
    expect(matchAuxBalance('乙公司', aux, '2202')).not.toBe(deduped)
  })

  it('科目前缀不符时不命中', () => {
    // 供应商A 在 1123 下，查 2202 应返回 undefined
    expect(matchAuxBalance('供应商A', AUX_ROWS, '2202')).toBeUndefined()
  })

  it('不传前缀时跨科目匹配', () => {
    expect(matchAuxBalance('供应商A', AUX_ROWS)).toBe(12000)
  })

  it('空名 / 空 aux → undefined', () => {
    expect(matchAuxBalance('', AUX_ROWS)).toBeUndefined()
    expect(matchAuxBalance('供应商A', [])).toBeUndefined()
  })

  it('名称 <4 字符不做包含匹配（防误命中）', () => {
    const aux: AuxBalanceRow[] = [{ auxName: 'AB公司', accountCode: '1123', closingBalance: 999 }]
    expect(matchAuxBalance('AB', aux)).toBeUndefined()
  })

  it('单字名不匹配', () => {
    expect(matchAuxBalance('A', AUX_ROWS)).toBeUndefined()
  })

  it('aux 行 auxName 为空时跳过不报错', () => {
    const aux: AuxBalanceRow[] = [{ auxName: '', accountCode: '1123', closingBalance: 1 }]
    expect(matchAuxBalance('供应商A', aux)).toBeUndefined()
  })
})

// ─── 未回函筛选（替代程序带入的前置条件） ────────────────────────────────────

describe('defaultUnrepliedFilter（替代程序只带未回函项）', () => {
  it('match_status=未回函 → 通过', () => {
    expect(defaultUnrepliedFilter(makeSummaryRow({ match_status: '未回函' }))).toBe(true)
  })

  it('is_replied=false 且非相符 → 通过', () => {
    expect(defaultUnrepliedFilter(makeSummaryRow({ is_replied: false }))).toBe(true)
  })

  it('已回函且相符 → 不通过', () => {
    expect(defaultUnrepliedFilter(makeSummaryRow({ is_replied: true, match_status: '相符' }))).toBe(false)
  })
})

// ─── 源码级：防能力再次变成零消费方 ─────────────────────────────────────────

describe('Property: F0-5/F0-6 必须真的启用 aux 校准（防零消费方复发）', () => {
  const F05 = 'audit-platform/frontend/src/components/workpaper/confirmation/alternativeF05/GtConfirmationAlternativeF05.vue'
  const F06 = 'audit-platform/frontend/src/components/workpaper/confirmation/alternativeF06/GtConfirmationAlternativeF06.vue'

  it('反向自检：能读到两个组件源码', () => {
    expect(readSource(F05).length).toBeGreaterThan(1000)
    expect(readSource(F06).length).toBeGreaterThan(1000)
  })

  it('F0-5 传 auxAccountCode=1123（预付账款）', () => {
    const src = readSource(F05)
    expect(src).toMatch(/importUnrepliedAsCompanies\([\s\S]{0,300}auxAccountCode:\s*'1123'/)
  })

  it('F0-6 传 auxAccountCode=2202（应付账款）', () => {
    const src = readSource(F06)
    expect(src).toMatch(/importUnrepliedAsCompanies\([\s\S]{0,300}auxAccountCode:\s*'2202'/)
  })

  it('两个组件都回报 auxMatchedCount（用户可见校准结果）', () => {
    expect(readSource(F05)).toContain('auxMatchedCount')
    expect(readSource(F06)).toContain('auxMatchedCount')
  })

  it('已删除零消费方模块 f0AltSupplierSeed.ts', () => {
    let exists = true
    try {
      readSource('audit-platform/frontend/src/components/workpaper/confirmation/composables/f0AltSupplierSeed.ts')
    } catch {
      exists = false
    }
    expect(exists).toBe(false)
  })
})

// ─── P0-1: 跨子科目求和（端点改前缀匹配后暴露） ──────────────────────────────
//
// 🔴 2026-08-04 实测背景：`get_aux_balance` 原按精确等值匹配科目码，而辅助余额几乎
// 全落在子科目（全库 810,884 行子科目 vs 1,507 行精确四位码）→ 一级码查不到任何行。
// 端点改前缀匹配后，同一单位可能在 `1123.01`（预付货款）与 `1123.03` 各有余额，
// 替代程序的「期末余额」应为两者之和；原 `.find()` 只取第一条 → 少算。

describe('P0-1: 同一单位跨子科目余额求和', () => {
  const MULTI: AuxBalanceRow[] = [
    { auxName: '甲单位', accountCode: '1123.01', closingBalance: 1000 },
    { auxName: '甲单位', accountCode: '1123.03', closingBalance: 2500 },
  ]

  it('精确匹配跨两个子科目 → 求和 3500（旧 .find() 只会得到 1000）', () => {
    expect(matchAuxBalance('甲单位', MULTI, '1123')).toBe(3500)
  })

  it('反向自检：旧「取第一条」口径与新求和口径必须不同', () => {
    const first = MULTI[0].closingBalance
    expect(matchAuxBalance('甲单位', MULTI, '1123')).not.toBe(first)
  })

  it('前缀限定后只求和该科目族（2202 不混入 1123）', () => {
    const mixed: AuxBalanceRow[] = [
      ...MULTI,
      { auxName: '甲单位', accountCode: '2202.01', closingBalance: 90000 },
    ]
    expect(matchAuxBalance('甲单位', mixed, '1123')).toBe(3500)
    expect(matchAuxBalance('甲单位', mixed, '2202')).toBe(90000)
  })

  /**
   * 🔴 曾一度在前端按 `科目码|单位名` 去重，被真实数据证伪 —— 同一
   * `(科目码, 单位名)` 的多行**不是重复行**，而是不同**辅助维度组合**。
   *
   * 实测（项目 `2aa00f57` / 2025 / active dataset / `2202.02` / 客户 `014006`）：
   *   `客户+成本中心:采购部`            → 2,601,247.80
   *   `客户+成本中心:渝北总店`          →   268,355.69
   *   `客户+成本中心:长寿美丽泽京店`    →         0
   *   `客户+成本中心+集团内外`          →         0
   *   合计 2,869,603.49
   * 按 `科目码|单位名` 去重只会留下其中一条 → **丢钱**。
   *
   * 数据集版本冗余（同一行存在 `dataset_id` NULL 与 active 两份）**已由后端
   * `get_active_filter` 消除**：该客户 8 行 → 4 行、`1123` 364 行 → 182 行。
   */
  it('🔴 同名同码的多行是不同维度组合，必须全部求和（禁前端去重）', () => {
    const dims: AuxBalanceRow[] = [
      { auxName: '乙单位', accountCode: '2202.02', closingBalance: 2601247.80 },
      { auxName: '乙单位', accountCode: '2202.02', closingBalance: 268355.69 },
      { auxName: '乙单位', accountCode: '2202.02', closingBalance: 0 },
      { auxName: '乙单位', accountCode: '2202.02', closingBalance: 0 },
    ]
    expect(matchAuxBalance('乙单位', dims, '2202')).toBe(2869603.49)
  })

  it('反向自检：按「科目码|单位名」去重会少算（证明去重有害）', () => {
    const dims: AuxBalanceRow[] = [
      { auxName: '乙单位', accountCode: '2202.02', closingBalance: 2601247.80 },
      { auxName: '乙单位', accountCode: '2202.02', closingBalance: 268355.69 },
    ]
    const deduped = dims[0].closingBalance // 旧口径只会留第一条
    expect(matchAuxBalance('乙单位', dims, '2202')).not.toBe(deduped)
  })

  it('跨子科目 + 跨维度组合一并求和', () => {
    const rows: AuxBalanceRow[] = [
      { auxName: '丙单位', accountCode: '1123.01', closingBalance: 100 },
      { auxName: '丙单位', accountCode: '1123.01', closingBalance: 100 },
      { auxName: '丙单位', accountCode: '1123.03', closingBalance: 200 },
      { auxName: '丙单位', accountCode: '1123.03', closingBalance: 200 },
    ]
    expect(matchAuxBalance('丙单位', rows, '1123')).toBe(600)
  })

  /**
   * 🔴 包含匹配可能命中**多个不同单位** —— 实测同项目 `2202` 客户维度下
   * 「重庆和平药房连锁有限责任公司医药保健品分公司」与
   * 「重庆市黔江区和平药房连锁有限责任公司」都含「和平药房连锁有限责任公司」。
   * 求和会把两家的钱算进一家 → 多义时返 undefined 回退发函金额（宁缺勿造）。
   */
  it('🔴 包含匹配命中多个不同单位时返 undefined（不得跨单位求和）', () => {
    const ambiguous: AuxBalanceRow[] = [
      { auxName: '和平药房连锁有限责任公司医药保健品分公司', accountCode: '2202.01', closingBalance: 5143381.25 },
      { auxName: '黔江区和平药房连锁有限责任公司', accountCode: '2202.01', closingBalance: 1066821.21 },
    ]
    expect(matchAuxBalance('和平药房连锁有限责任公司', ambiguous, '2202')).toBeUndefined()
  })

  it('包含匹配只命中一个单位（含其多行）时正常求和', () => {
    const single: AuxBalanceRow[] = [
      { auxName: '和平药房连锁有限责任公司医药保健品分公司', accountCode: '2202.01', closingBalance: 100 },
      { auxName: '和平药房连锁有限责任公司医药保健品分公司', accountCode: '2202.98', closingBalance: 200 },
    ]
    expect(matchAuxBalance('和平药房连锁有限责任公司', single, '2202')).toBe(300)
  })

  it('包含匹配路径同样求和（不只精确路径）', () => {
    const rows: AuxBalanceRow[] = [
      { auxName: '丁单位有限公司', accountCode: '1123.01', closingBalance: 400 },
      { auxName: '丁单位有限公司', accountCode: '1123.03', closingBalance: 600 },
    ]
    expect(matchAuxBalance('丁单位有限公司分部', rows, '1123')).toBe(1000)
  })

  it('负余额（贷方性质）如实相加，不取绝对值', () => {
    const rows: AuxBalanceRow[] = [
      { auxName: '戊单位', accountCode: '2202.01', closingBalance: -5000 },
      { auxName: '戊单位', accountCode: '2202.02', closingBalance: -3000 },
    ]
    expect(matchAuxBalance('戊单位', rows, '2202')).toBe(-8000)
  })

  it('浮点求和保留 2 位（防 0.1+0.2 类误差）', () => {
    const rows: AuxBalanceRow[] = [
      { auxName: '己单位', accountCode: '1123.01', closingBalance: 0.1 },
      { auxName: '己单位', accountCode: '1123.03', closingBalance: 0.2 },
    ]
    expect(matchAuxBalance('己单位', rows, '1123')).toBe(0.3)
  })
})

// ─── P0-2: aux_type 选择规则与后端同源 ───────────────────────────────────────
//
// 🔴 原实现按「行数最多」选维度；后端 `four_table/aux_aggregation.pick_aux_type` 是
// 「关键词 > 余额 > 行数」。实测该项目 客户 265 行 / 成本中心 249 行 —— 行数规则
// **碰巧**选对了客户；一旦成本中心行数更多，替代程序期末余额就会静默按成本中心校准。

describe('P0-2: pickAuxType 与后端 pick_aux_type 同源', () => {
  it('空候选 → null', () => {
    expect(pickAuxType([])).toBeNull()
  })

  it('🔴 关键词优先于行数：客户(少行) 胜过 成本中心(多行)', () => {
    const picked = pickAuxType([
      { auxType: '成本中心', rowCount: 999, absAmount: 999999 },
      { auxType: '客户', rowCount: 3, absAmount: 100 },
    ])
    expect(picked).toBe('客户')
  })

  it('反向自检：纯「行数最多」口径会选成本中心（证明规则确实改了）', () => {
    const cands = [
      { auxType: '成本中心', rowCount: 999, absAmount: 999999 },
      { auxType: '客户', rowCount: 3, absAmount: 100 },
    ]
    const naive = [...cands].sort((a, b) => b.rowCount - a.rowCount)[0].auxType
    expect(naive).toBe('成本中心')
    expect(pickAuxType(cands)).not.toBe(naive)
  })

  it('多个关键词维度并存 → 比余额绝对值', () => {
    expect(pickAuxType([
      { auxType: '客户', rowCount: 500, absAmount: 100 },
      { auxType: '供应商', rowCount: 2, absAmount: 999 },
    ])).toBe('供应商')
  })

  it('关键词维度余额相等 → 比行数', () => {
    expect(pickAuxType([
      { auxType: '客户', rowCount: 2, absAmount: 500 },
      { auxType: '供应商', rowCount: 9, absAmount: 500 },
    ])).toBe('供应商')
  })

  it('无关键词维度 → 在全集里比余额', () => {
    expect(pickAuxType([
      { auxType: '成本中心', rowCount: 100, absAmount: 10 },
      { auxType: '保证金类别', rowCount: 1, absAmount: 9999 },
    ])).toBe('保证金类别')
  })

  it('余额取绝对值（负余额维度不因符号被排到最后）', () => {
    expect(pickAuxType([
      { auxType: '成本中心', rowCount: 1, absAmount: 10 },
      { auxType: '项目', rowCount: 1, absAmount: -9999 },
    ])).toBe('项目')
  })

  it('关键词覆盖 客户/供应商/往来/单位/个人/职员/员工', () => {
    for (const kw of ['客户', '供应商', '往来单位', '单位', '个人', '职员', '员工']) {
      expect(pickAuxType([
        { auxType: '成本中心', rowCount: 999, absAmount: 999999 },
        { auxType: kw, rowCount: 1, absAmount: 1 },
      ]), kw).toBe(kw)
    }
  })

  it('源码级：前端关键词表与后端 aux_aggregation 逐条一致', () => {
    const py = readSource('backend/app/services/four_table/aux_aggregation.py')
    const m = py.match(/AUX_TYPE_PREFERRED_KEYWORDS\s*=\s*\(([^)]*)\)/)
    expect(m, '后端未找到 AUX_TYPE_PREFERRED_KEYWORDS').toBeTruthy()
    const backend = [...m![1].matchAll(/"([^"]+)"/g)].map(x => x[1])
    expect(backend.length).toBeGreaterThan(4)

    const ts = readSource('audit-platform/frontend/src/components/workpaper/confirmation/coordination/importFromSummary.ts')
    const tm = ts.match(/AUX_TYPE_PREFERRED_KEYWORDS\s*=\s*\[([^\]]*)\]/)
    expect(tm, '前端未找到 AUX_TYPE_PREFERRED_KEYWORDS').toBeTruthy()
    const frontend = [...tm![1].matchAll(/'([^']+)'/g)].map(x => x[1])

    expect(frontend).toEqual(backend)
  })
})

// ─── P0-2b / P1-2: 端点契约与溯源字段接线 ────────────────────────────────────

describe('fetchAuxBalances 的两条契约（源码级）', () => {
  const SRC = 'audit-platform/frontend/src/components/workpaper/confirmation/coordination/importFromSummary.ts'

  it('🔴 用 apiProxy 的 `api` 就不得解构 `{ data }`（形态错配，恒 undefined）', () => {
    const raw = readSource(SRC)
    expect(raw).toContain("import { api } from '@/services/apiProxy'")
    // 实测：该端点返回数组，数组无 data 属性 → 解构必得 undefined → 恒返回 []
    // 🔴 必须剥注释：本文件的踩坑说明注释里原样引用了这个错误写法
    expect(stripComments(raw)).not.toMatch(/const\s*\{\s*data\s*\}\s*=\s*await\s+api\.get/)
  })

  it('反向自检：stripComments 确实在起作用（注释里有该写法、代码里没有）', () => {
    const raw = readSource(SRC)
    // 注释里保留了错误写法作为踩坑留证 → 不剥注释时必然命中
    expect(raw).toMatch(/const\s*\{\s*data\s*\}\s*=\s*await\s+api\.get/)
    // 剥掉后不命中 ⇒ 证明命中的那处在注释里，且剥离逻辑非空操作
    expect(stripComments(raw)).not.toMatch(/const\s*\{\s*data\s*\}\s*=\s*await\s+api\.get/)
  })

  it('按 pickAuxType 锁定维度（不再是「行数最多」）', () => {
    const src = readSource(SRC)
    const i = src.indexOf('export async function fetchAuxBalances')
    expect(i).toBeGreaterThan(0)
    const body = src.slice(i, i + 3000)
    expect(body).toContain('pickAuxType')
  })
})

describe('P1-2: _balance_source 溯源标记必须落库（防孤儿字段）', () => {
  const FACTORY = 'audit-platform/frontend/src/components/workpaper/confirmation/coordination/createAlternativeConfirmationData.ts'
  const TYPES = 'audit-platform/frontend/src/components/workpaper/confirmation/alternativeD05/alternativeD05Types.ts'

  it('AlternativeCompany 已声明 _balance_source（不靠 as any）', () => {
    expect(readSource(TYPES)).toMatch(/_balance_source\?:\s*'aux'\s*\|\s*'summary'/)
  })

  it('🔴 共享工厂 importCompanies 必须透传该字段（原按字段白名单构造 → 静默丢弃）', () => {
    const src = readSource(FACTORY)
    const i = src.indexOf('function importCompanies')
    expect(i).toBeGreaterThan(0)
    const body = src.slice(i, i + 2000)
    expect(body).toContain('_balance_source')
  })

  it('反向自检：工厂确实是「白名单构造」而非整体 spread（说明透传是必要的）', () => {
    const src = readSource(FACTORY)
    const i = src.indexOf('function importCompanies')
    const body = src.slice(i, i + 2000)
    // 若改成 `...item` 整体展开，本断言会打红提醒重新评估透传逻辑
    expect(body).not.toMatch(/\.\.\.item\b/)
  })
})

// ─── P2: 主表文案按循环（不再显示 D0-5 销售循环术语） ───────────────────────

describe('P2: F0-5/F0-6 主表文案接 alternativeMasterLabels', () => {
  const LABELS = 'audit-platform/frontend/src/components/workpaper/confirmation/composables/f0MasterLabels.ts'
  const F05H = 'audit-platform/frontend/src/components/workpaper/confirmation/alternativeF05/GtConfirmationAlternativeF05.vue'
  const F06H = 'audit-platform/frontend/src/components/workpaper/confirmation/alternativeF06/GtConfirmationAlternativeF06.vue'

  /**
   * 🔴 2026-08-04 浏览器实测教训：本 describe 首版只 grep「宿主是否提到某常量名」，
   * 而模块实际导出的是 `F0_ALTERNATIVE_MASTER_LABELS`（两表共用一份），宿主却 import
   * `F05_MASTER_LABELS` / `F06_MASTER_LABELS` → 运行时
   * `does not provide an export named 'F05_MASTER_LABELS'`，**整个 F0-5 页面白屏**
   * （「页面渲染出错」）。`get_diagnostics` 零诊断、vitest 全绿、Vite transform 200 ——
   * 四层验证全过，只有浏览器打开才暴露。
   *
   * → 守卫改为**从模块源码抽真实导出名**，再断言宿主 import 的名字在其中。
   *   这条判据对「模块改名 / 拆分 / 合并」都有效，不会再出现「名字写错但守卫全绿」。
   */
  function exportedNames(rel: string): string[] {
    const src = stripComments(readSource(rel))
    return [...src.matchAll(/export\s+(?:const|function|class)\s+([A-Za-z_$][\w$]*)/g)].map(m => m[1])
  }

  function importedFrom(hostRel: string, moduleHint: string): string[] {
    const src = stripComments(readSource(hostRel))
    const re = new RegExp(`import\\s*\\{([^}]*)\\}\\s*from\\s*['"][^'"]*${moduleHint}['"]`, 'g')
    const names: string[] = []
    for (const m of src.matchAll(re)) {
      for (const part of m[1].split(',')) {
        const n = part.replace(/\btype\b/, '').trim()
        if (n) names.push(n)
      }
    }
    return names
  }

  it('反向自检：能从 f0MasterLabels.ts 抽到导出名', () => {
    expect(exportedNames(LABELS).length).toBeGreaterThan(0)
  })

  it('🔴 宿主 import 的常量名必须真的被 f0MasterLabels.ts 导出（防运行时白屏）', () => {
    const exported = exportedNames(LABELS)
    for (const host of [F05H, F06H]) {
      const imported = importedFrom(host, 'f0MasterLabels')
      expect(imported.length, `${host} 未从 f0MasterLabels 导入任何常量`).toBeGreaterThan(0)
      for (const name of imported) {
        expect(exported, `${host} 导入了未导出的 ${name}`).toContain(name)
      }
    }
  })

  it('两个宿主都把该常量传给了 :labels（否则回落 D0-5 默认值 = 改了也看不到）', () => {
    for (const host of [F05H, F06H]) {
      const imported = importedFrom(host, 'f0MasterLabels')
      const src = stripComments(readSource(host))
      const wired = imported.some(n => src.includes(`:labels="${n}"`))
      expect(wired, `${host} import 了常量但没传给 :labels`).toBe(true)
    }
  })

  it('🔴 带入按钮指向 F0-1，不得残留「从 D0-1 带入」', () => {
    const raw = readSource(LABELS)
    expect(raw).toContain('从 F0-1 带入')
    // 🔴 必须剥注释：文件头的「改造前显示什么」说明里原样引用了 D0-5 旧文案
    expect(stripComments(raw)).not.toContain('从 D0-1 带入')
  })

  it('反向自检：stripComments 有效（旧文案只存在于注释）', () => {
    const raw = readSource(LABELS)
    expect(raw).toContain('从 D0-1 带入')
    expect(stripComments(raw)).not.toContain('从 D0-1 带入')
  })

  it('比例列文案逐字取自源模板 K11（F0-5 付款 / F0-6 入库）', () => {
    const src = readSource(LABELS)
    // 源 `预付及采购替代程序F0-5!K11` = 本期付款检查比例
    expect(src).toContain('本期付款检查比例')
    // 源 `应付及采购替代程序F0-6!K11` = 本期入库检查比例
    expect(src).toContain('本期入库检查比例')
  })

  it('主体名称列取源模板 A5「供应商名称：」（去冒号）', () => {
    expect(readSource(LABELS)).toContain('供应商名称')
  })

  it('索引号占位符是 F0-（不是 D0-）', () => {
    const src = readSource(LABELS)
    expect(src).toMatch(/confirmIndexPlaceholder:\s*'F0-'/)
  })

  it('反向自检：共享默认值仍是 D0-5 字面（证明按循环覆盖是必要的）', () => {
    const shared = readSource('audit-platform/frontend/src/components/workpaper/confirmation/alternativeD05/alternativeMasterLabels.ts')
    expect(shared).toContain('从 D0-1 带入')
    expect(shared).toContain('供应商/客户名称')
  })
})
