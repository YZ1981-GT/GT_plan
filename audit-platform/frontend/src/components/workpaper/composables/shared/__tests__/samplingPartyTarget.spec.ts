/**
 * samplingPartyTarget 守卫 —— 抽凭样本「往来单位名称」落列裁决
 *
 * 判据的数据基础（真实库实证 2026-08-04，8 个项目 `tb_aux_ledger`）：
 * - 往来单位类维度只有 **「客户」与「职员」**，没有「供应商」「往来单位」
 * - `aux_type='客户'` 同时挂在应收侧（1122/1123/1221/2203）与**应付侧**
 *   （2202 48 万行 / 5878 个名字、2241、2201）以及损益侧（6001/6401/6601~6603）
 *   ⇒ 该维度实际承载「往来单位」，应付科目下那批就是供应商
 *   ⇒ **不能按 aux_type 反推目标列语义**，只能按宿主那一列是什么判定
 * - 「职员」是备用金/报销领用人，填进「客户名称」列是错的 ⇒ 必须挡掉
 *
 * 四道不填门控（每道都有反向自检）：
 * 1. 宿主没声明该列（这张底稿压根没有往来单位名称列）
 * 2. 未命中（该凭证行在辅助明细账里没有往来单位）
 * 3. 歧义（一键多名 ⇒ 交审计师判断，与「重复抽凭必须弹窗」同一原则）
 * 4. 维度不适格（如「职员」）
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { readFileSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'

import {
  PARTY_SEMANTIC_LABELS,
  PARTY_ELIGIBLE_AUX_TYPES,
  readSampledParty,
  resolvePartyFill,
  partyNameForColumn,
  buildPartyAmbiguousHint,
  buildPartySourceHint,
  type PartyColumnSemantic,
  type PartyFillTarget,
} from '../samplingPartyTarget'

// ─── REPO_ROOT：哨兵文件向上查找（禁写死回退级数） ───────────────────────────

function findRepoRoot(): string {
  const SENTINEL = join('backend', 'app', 'services', 'ledger_sampling_service.py')
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    if (existsSync(join(dir, SENTINEL))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error('找不到仓库根（哨兵 backend/app/services/ledger_sampling_service.py 未命中）')
}

const REPO_ROOT = findRepoRoot()

const ALL_SEMANTICS: PartyColumnSemantic[] = [
  'customer', 'supplier', 'debtor', 'creditor', 'investee', 'counterpart',
]

function target(semantic: PartyColumnSemantic, rowField = 'partyCol'): PartyFillTarget {
  return { rowField, semantic }
}

// ─── 门控 1：宿主没声明该列 ─────────────────────────────────────────────────

describe('门控 1：宿主未声明该列 ⇒ 不填', () => {
  const good = { partyName: '重庆医药股份有限公司', partyAuxType: '客户' }

  it('target 为 null / undefined ⇒ 返回 null', () => {
    expect(resolvePartyFill(null, good)).toBeNull()
    expect(resolvePartyFill(undefined, good)).toBeNull()
  })

  it('rowField 为空串 ⇒ 返回 null（防声明了个空字段名）', () => {
    expect(resolvePartyFill({ rowField: '', semantic: 'customer' }, good)).toBeNull()
  })

  it('🔴 反向自检：声明齐备时必须能填出来（否则上面三条是空转）', () => {
    const fill = resolvePartyFill(target('customer'), good)
    expect(fill).not.toBeNull()
    expect(fill!.rowField).toBe('partyCol')
    expect(fill!.value).toBe('重庆医药股份有限公司')
  })
})

// ─── 门控 2：未命中 ─────────────────────────────────────────────────────────

describe('门控 2：未命中 ⇒ 不填（不写空串覆盖手工输入）', () => {
  it('partyName 缺失 / null / 空串 / 纯空白 ⇒ 返回 null', () => {
    for (const bad of [undefined, null, '', '   ', '\t']) {
      expect(resolvePartyFill(target('customer'), { partyName: bad, partyAuxType: '客户' }))
        .toBeNull()
    }
  })

  it('partyNameForColumn 未命中时返回空串（宿主可安全赋值，不产 undefined）', () => {
    expect(partyNameForColumn({ partyName: null }, 'customer')).toBe('')
    expect(partyNameForColumn({}, 'customer')).toBe('')
  })
})

// ─── 门控 3：歧义 ───────────────────────────────────────────────────────────

describe('门控 3：一键多名（歧义）⇒ 不填，交审计师判断', () => {
  it('party_ambiguous 为 true 时即便有名字也不填', () => {
    const fill = resolvePartyFill(target('customer'), {
      partyName: '某某公司', partyAuxType: '客户', partyAmbiguous: true,
    })
    expect(fill).toBeNull()
  })

  it('snake_case 的 party_ambiguous 同样生效（后端 items 直接消费路径）', () => {
    const fill = resolvePartyFill(target('customer'), {
      party_name: '某某公司', party_aux_type: '客户', party_ambiguous: true,
    })
    expect(fill).toBeNull()
  })

  it('🔴 反向自检：同一样本去掉 ambiguous 标记后必须能填（证明是它挡住的）', () => {
    const base = { partyName: '某某公司', partyAuxType: '客户' }
    expect(resolvePartyFill(target('customer'), { ...base, partyAmbiguous: true })).toBeNull()
    expect(resolvePartyFill(target('customer'), base)).not.toBeNull()
  })

  it('歧义提示文案必须与「留空」可区分：说明是系统查到多个候选故意没填', () => {
    const hint = buildPartyAmbiguousHint('customer', '客户')
    expect(hint).toContain('多个往来单位')
    expect(hint).toContain('客户名称')
    expect(hint).toContain('手工填写')
    // 必须点明风险取向，否则审计师会以为是系统故障
    expect(hint).toContain('填错')
  })
})

// ─── 门控 4：维度不适格（这一道是「职员」引起的） ────────────────────────────

describe('门控 4：辅助维度不适格 ⇒ 不填', () => {
  it('适格维度白名单只含往来单位类，不含分摊/分类维度', () => {
    const eligible = new Set(PARTY_ELIGIBLE_AUX_TYPES)
    // 真实库实证存在且属往来单位
    expect(eligible.has('客户')).toBe(true)
    // 真实库该账套没有，但其它账套可能有 ⇒ 预留
    expect(eligible.has('供应商')).toBe(true)
    expect(eligible.has('往来单位')).toBe(true)
    // 🔴 这些是分摊/分类维度，进来会把「重庆区域」「13%」填进往来单位列
    for (const bad of ['成本中心', '业态', '税率', '银行账户', '医保类型', '区域2', '车牌号']) {
      expect(eligible.has(bad as never)).toBe(false)
    }
  })

  it('🔴「职员」维度必须被挡掉（备用金/报销领用人不是客户）', () => {
    const fill = resolvePartyFill(target('customer'), {
      partyName: '张三', partyAuxType: '职员',
    })
    expect(fill).toBeNull()
    expect(partyNameForColumn({ partyName: '张三', partyAuxType: '职员' }, 'customer')).toBe('')
  })

  it('🔴 反向自检：同一个名字换成「客户」维度后必须能填（证明是维度挡的，不是名字）', () => {
    expect(resolvePartyFill(target('customer'), { partyName: '张三', partyAuxType: '职员' }))
      .toBeNull()
    const ok = resolvePartyFill(target('customer'), { partyName: '张三', partyAuxType: '客户' })
    expect(ok).not.toBeNull()
    expect(ok!.value).toBe('张三')
  })

  it('维度缺失（后端未给 aux_type）时按未知处理 ⇒ 不填', () => {
    expect(resolvePartyFill(target('customer'), { partyName: '某公司' })).toBeNull()
  })

  it('每种目标列语义都受同一套维度白名单约束（不给某个语义开后门）', () => {
    for (const s of ALL_SEMANTICS) {
      expect(resolvePartyFill(target(s), { partyName: '张三', partyAuxType: '职员' }))
        .toBeNull()
      expect(resolvePartyFill(target(s), { partyName: '甲公司', partyAuxType: '客户' }))
        .not.toBeNull()
    }
  })
})

// ─── aux_type 不得用于反推列语义（真实库实证支撑的关键设计约束） ──────────────

describe('🔴 aux_type 不得反推目标列语义', () => {
  it('同一个「客户」维度的名字，既能落客户列也能落供应商列', () => {
    // 真实库：aux_type='客户' 同时挂在 1122（应收）与 2202（应付，48 万行）
    // ⇒ 应付科目下那批就是供应商，若按 aux_type 反推会拒填供应商列
    const sample = { partyName: '重庆某供应链公司', partyAuxType: '客户' }
    expect(resolvePartyFill(target('customer', 'customerName'), sample)!.value)
      .toBe('重庆某供应链公司')
    expect(resolvePartyFill(target('supplier', 'supplier'), sample)!.value)
      .toBe('重庆某供应链公司')
    expect(resolvePartyFill(target('debtor', 'debtorName'), sample)!.value)
      .toBe('重庆某供应链公司')
  })

  it('落列由宿主声明的 rowField 决定，与 aux_type 无关', () => {
    const sample = { partyName: '甲公司', partyAuxType: '客户' }
    expect(resolvePartyFill(target('supplier', 'supplierName'), sample)!.rowField)
      .toBe('supplierName')
    expect(resolvePartyFill(target('investee', 'investeeName'), sample)!.rowField)
      .toBe('investeeName')
  })
})

// ─── readSampledParty：双形态兼容与健壮性 ───────────────────────────────────

describe('readSampledParty', () => {
  it('camelCase（抽凭引擎 SampledVoucher）', () => {
    expect(readSampledParty({
      partyName: '甲公司', partyAuxType: '客户', partyAmbiguous: false,
    })).toEqual({ partyName: '甲公司', partyAuxType: '客户', partyAmbiguous: false })
  })

  it('snake_case（后端 items 直接消费）', () => {
    expect(readSampledParty({
      party_name: '乙公司', party_aux_type: '客户', party_ambiguous: true,
    })).toEqual({ partyName: '乙公司', partyAuxType: '客户', partyAmbiguous: true })
  })

  it('空白名归一为 null（区分「有值」与「有个空字符串」）', () => {
    expect(readSampledParty({ partyName: '   ' }).partyName).toBeNull()
  })

  it('非对象输入返回全空且不抛错（一条脏样本不打掉整批回填）', () => {
    for (const bad of [null, undefined, 'x', 5, [], true]) {
      const info = readSampledParty(bad)
      expect(info.partyName).toBeNull()
      expect(info.partyAmbiguous).toBe(false)
    }
  })

  it('PBT：任意输入都不抛错，且 partyName 恒为 null 或非空串', () => {
    fc.assert(
      fc.property(fc.anything(), (v) => {
        const info = readSampledParty(v)
        expect(info.partyName === null || info.partyName.length > 0).toBe(true)
        expect(typeof info.partyAmbiguous).toBe('boolean')
      }),
      { numRuns: 20 },
    )
  })
})

// ─── 文案与标签 ─────────────────────────────────────────────────────────────

describe('语义标签与溯源文案', () => {
  it('每种语义都有中文标签（禁在组件里另写一份）', () => {
    for (const s of ALL_SEMANTICS) {
      expect(PARTY_SEMANTIC_LABELS[s]).toBeTruthy()
      expect(PARTY_SEMANTIC_LABELS[s]).not.toMatch(/[a-z]/)  // 全中文
    }
  })

  it('溯源文案说明来源维度且提示可手工改（审计追溯要求）', () => {
    const hint = buildPartySourceHint('customer', '客户')
    expect(hint).toContain('辅助明细账')
    expect(hint).toContain('客户')
    expect(hint).toContain('可手工修改')
  })

  it('无维度信息时文案不出现「维度：undefined」', () => {
    const hint = buildPartySourceHint('supplier', null)
    expect(hint).not.toContain('undefined')
    expect(hint).not.toContain('维度：')
  })
})

// ─── 与后端字段契约交叉锁死（防改一侧漏一侧） ────────────────────────────────

describe('🔴 与后端 enrich 字段契约交叉锁死', () => {
  const BE = join(REPO_ROOT, 'backend', 'app', 'services', 'ledger_sampling_service.py')

  it('后端确实产出这三个字段（否则本模块整体空转）', () => {
    const src = readFileSync(BE, 'utf-8')
    for (const f of ['party_name', 'party_aux_type', 'party_ambiguous']) {
      expect(src).toContain(f)
    }
  })

  it('后端的适格维度常量与前端白名单同源（一处改了另一处必红）', () => {
    const src = readFileSync(BE, 'utf-8')
    const m = src.match(/AUX_PARTY_TYPES[^=]*=\s*\(([^)]*)\)/)
    expect(m, '后端未找到 AUX_PARTY_TYPES 常量').toBeTruthy()
    const beTypes = [...m![1].matchAll(/"([^"]+)"/g)].map((x) => x[1])
    expect(beTypes.length).toBeGreaterThan(0)
    // 后端查询侧的维度集合必须 ⊇ 前端落列白名单：后端多查一些无害
    // （多出来的由前端第 4 道门控挡掉，如「职员」），反之会让白名单永远取不到值
    for (const t of PARTY_ELIGIBLE_AUX_TYPES) {
      expect(beTypes, `后端未查询维度「${t}」，前端白名单里的它永远取不到值`).toContain(t)
    }
  })

  it('🔴 后端必须查「职员」而前端必须挡它（证明两层分工真实存在）', () => {
    const src = readFileSync(BE, 'utf-8')
    const m = src.match(/AUX_PARTY_TYPES[^=]*=\s*\(([^)]*)\)/)
    const beTypes = [...m![1].matchAll(/"([^"]+)"/g)].map((x) => x[1])
    expect(beTypes).toContain('职员')
    expect([...PARTY_ELIGIBLE_AUX_TYPES]).not.toContain('职员')
  })
})
