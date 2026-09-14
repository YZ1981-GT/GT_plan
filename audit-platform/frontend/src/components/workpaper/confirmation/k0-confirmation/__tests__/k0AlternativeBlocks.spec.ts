/**
 * k0AlternativeBlocks.spec — K0-5 / K0-6 段① 源模板对齐
 *
 * spec: k0-confirmation-source-alignment
 *   Task 13（Requirements 7.1 / 7.2 / 7.5）
 *   Task 16 Property 14/15/16 的段① 部分
 *
 * 判据真源：后端 `backend/tests/test_k0_source_template_facts.py` 的
 * `ALT_BLOCK1_EVIDENCE` / `ALT_RED_HINT` / `ALT_PREPARATION_ITEMS`
 * （openpyxl 直读源 xlsx，是唯一裁决者）。前端 `k0AlternativeSourceFidelity.ts`
 * 与它双向锁死；两个 `blockColumnConfigsK0*.ts` 再与前端真源锁死。
 *
 * 🔴 段②/③/④ 的「具体化证据列」**不在本守卫的对齐范围** —— 源模板红字
 *    `O15`/`O26`/`O38`「检查的关键证据和要素根据被审计单位具体情况修改」明确授权具体化
 *    （R7.3）。本文件只断言它们**没被误改**（字段名与合计列不变）。
 */

import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import {
  K05_BLOCK1_SOURCE,
  K06_BLOCK1_SOURCE,
  K0_ALT_COUNTERPARTY,
  K0_ALT_PREPARATION_ITEMS,
  K0_ALT_RED_HINT,
  K0_ALT_RED_HINT_BLOCKS,
  K0_ALT_SOURCE_TYPOS,
} from '../../alternativeK05/k0AlternativeSourceFidelity'
import { BLOCK_COLUMN_CONFIGS_K05, getGroupsK05, getSumFieldsK05 } from '../../alternativeK05/blockColumnConfigsK05'
import { BLOCK_COLUMN_CONFIGS_K06, getGroupsK06, getSumFieldsK06 } from '../../alternativeK06/blockColumnConfigsK06'

// ─── 仓库根：双哨兵具体文件向上查找 ─────────────────────────────────────────

function repoRoot(): string {
  let dir = path.resolve(__dirname)
  for (let i = 0; i < 12; i++) {
    const a = path.join(dir, 'backend', 'tests', 'test_k0_source_template_facts.py')
    const b = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    const up = path.dirname(dir)
    if (up === dir) break
    dir = up
  }
  throw new Error('[k0AlternativeBlocks.spec] 找不到仓库根（双哨兵均未命中）')
}

const ROOT = repoRoot()
const factsSrc = fs.readFileSync(
  path.join(ROOT, 'backend', 'tests', 'test_k0_source_template_facts.py'),
  'utf-8',
)

/** 抽 python 里某个常量声明块的原文（按 ASCII 括号配对，不用固定字符窗口） */
function pyBlock(src: string, name: string, open: '{' | '[' ): string {
  const close = open === '{' ? '}' : ']'
  const decl = new RegExp(`${name}\\s*(?::[^=\\n]*)?=\\s*\\${open}`).exec(src)
  if (!decl) throw new Error(`[k0AlternativeBlocks.spec] 后端未找到常量 ${name}（正则失效即空转）`)
  let i = decl.index + decl[0].length - 1
  const start = i
  let depth = 0
  for (; i < src.length; i++) {
    if (src[i] === open) depth++
    else if (src[i] === close) { depth--; if (depth === 0) break }
  }
  return src.slice(start, i + 1)
}

const BLOCK1_EVIDENCE_SRC = pyBlock(factsSrc, 'ALT_BLOCK1_EVIDENCE', '{')
const PREP_ITEMS_SRC = pyBlock(factsSrc, 'ALT_PREPARATION_ITEMS', '[')

// ─── Property 14: 段① 与源模板双向锁死 ──────────────────────────────────────

describe('Property 14: K0-5/K0-6 段① 证据结构与源模板双向锁死', () => {
  it('后端常量块确实被抽到（防解析失效导致断言空转）', () => {
    expect(BLOCK1_EVIDENCE_SRC.length).toBeGreaterThan(200)
    expect(BLOCK1_EVIDENCE_SRC).toContain('"K0-5"')
    expect(BLOCK1_EVIDENCE_SRC).toContain('"K0-6"')
  })

  it.each([
    ['K0-5', K05_BLOCK1_SOURCE],
    ['K0-6', K06_BLOCK1_SOURCE],
  ] as const)('%s 的段头与叶子逐字出现在后端常量里', (_code, groups) => {
    for (const g of groups) {
      expect(BLOCK1_EVIDENCE_SRC, `段头 ${g.group} 未在后端登记`).toContain(`"${g.group}"`)
      expect(BLOCK1_EVIDENCE_SRC, `锚点 ${g.anchor} 未在后端登记`).toContain(`"${g.anchor}"`)
      for (const [anchor, label] of g.leaves) {
        expect(BLOCK1_EVIDENCE_SRC, `叶子锚点 ${anchor} 未登记`).toContain(`"${anchor}"`)
        expect(BLOCK1_EVIDENCE_SRC, `叶子 label ${label} 未登记`).toContain(`"${label}"`)
      }
    }
  })

  it('K0-5 段① 平台列 label/group 与前端真源逐字一致（含新补的支持性文件三列）', () => {
    const cols = BLOCK_COLUMN_CONFIGS_K05.block1.columns
    const byLabel = new Map(cols.map((c) => [`${c.group ?? ''}|${c.label}`, c]))
    for (const g of K05_BLOCK1_SOURCE) {
      for (const [, label] of g.leaves) {
        expect(byLabel.has(`${g.group}|${label}`), `K0-5 缺列 ${g.group}/${label}`).toBe(true)
      }
    }
    // 三列是新补的，逐个钉字段名（持久化契约）
    const fields = cols.map((c) => c.field)
    expect(fields).toContain('support1_feature')
    expect(fields).toContain('support1_info1')
    expect(fields).toContain('support1_info2')
    expect(getGroupsK05('block1')).toContain('支持性文件1')
  })

  it('K0-6 段① 平台列 label/group 与前端真源逐字一致', () => {
    const cols = BLOCK_COLUMN_CONFIGS_K06.block1.columns
    const byLabel = new Map(cols.map((c) => [`${c.group ?? ''}|${c.label}`, c]))
    for (const g of K06_BLOCK1_SOURCE) {
      for (const [, label] of g.leaves) {
        expect(byLabel.has(`${g.group}|${label}`), `K0-6 缺列 ${g.group}/${label}`).toBe(true)
      }
    }
    expect(getGroupsK06('block1')).toContain('付款审批单')
    expect(getGroupsK06('block1')).toContain('银行回单')
  })

  it('两侧段① 的记账凭证段仍在（左固定列未被误删）', () => {
    for (const cols of [BLOCK_COLUMN_CONFIGS_K05.block1.columns, BLOCK_COLUMN_CONFIGS_K06.block1.columns]) {
      const voucher = cols.filter((c) => c.group === '记账凭证')
      expect(voucher.length).toBe(5)
      expect(voucher.map((c) => c.label)).toEqual(['日期', '凭证编号', '业务内容', '对方科目', '金额'])
    }
  })
})

// ─── Property 15: 对方当事人必须不同（业务方向） ─────────────────────────────

describe('Property 15: 两侧段① 对方当事人 label 必须不同', () => {
  it('K0-5 = 付款方 / K0-6 = 收款方，且两者不相等', () => {
    const k5 = BLOCK_COLUMN_CONFIGS_K05.block1.columns.find((c) => c.field === 'receipt_payer')!
    const k6 = BLOCK_COLUMN_CONFIGS_K06.block1.columns.find((c) => c.field === 'payee')!
    expect(k5.label).toBe('付款方')
    expect(k6.label).toBe('收款方')
    // 🔴 反向自检：两侧统一成同一个词即打红 —— 其他应收款是收回款项（对方是付款方）、
    //    其他应付款是对外付款（对方是收款方），统一用词等于把业务方向搞反。
    expect(k5.label, '两侧对方当事人用词相同 = 业务方向被搞反').not.toBe(k6.label)
  })

  it('前端真源常量与实现一致（否则改常量不打红 = 断言空转）', () => {
    expect(K0_ALT_COUNTERPARTY['K0-5'].label).toBe('付款方')
    expect(K0_ALT_COUNTERPARTY['K0-6'].label).toBe('收款方')
    expect(K0_ALT_COUNTERPARTY['K0-5'].label).not.toBe(K0_ALT_COUNTERPARTY['K0-6'].label)
    // 与后端锚点交叉锁死
    expect(BLOCK1_EVIDENCE_SRC).toContain(`"${K0_ALT_COUNTERPARTY['K0-5'].anchor}", "付款方"`)
    expect(BLOCK1_EVIDENCE_SRC).toContain(`"${K0_ALT_COUNTERPARTY['K0-6'].anchor}", "收款方"`)
  })
})

// ─── Property 16: 索引号列不参与求和（源模板 M46 笔误不实现） ─────────────────

describe('Property 16: 索引号列不得带 sumField（源模板 M46 笔误不实现）', () => {
  it.each(['block1', 'block2', 'block3', 'block4'])('K0-5 %s 的索引号列无 sumField', (blk) => {
    const col = BLOCK_COLUMN_CONFIGS_K05[blk].columns.find((c) => c.field === 'ref_index')!
    expect(col).toBeTruthy()
    expect(col.sumField, `${blk} 的索引号列被误标为合计列（源模板 M46 笔误）`).toBeFalsy()
    expect(getSumFieldsK05(blk)).not.toContain('ref_index')
  })

  it.each(['block1', 'block2', 'block3', 'block4'])('K0-6 %s 的索引号列无 sumField', (blk) => {
    const col = BLOCK_COLUMN_CONFIGS_K06[blk].columns.find((c) => c.field === 'ref_index')!
    expect(col).toBeTruthy()
    expect(col.sumField).toBeFalsy()
    expect(getSumFieldsK06(blk)).not.toContain('ref_index')
  })

  it('笔误已在前端真源登记且与后端说明呼应', () => {
    expect(K0_ALT_SOURCE_TYPOS).toHaveLength(1)
    const t = K0_ALT_SOURCE_TYPOS[0]
    expect(t.sourceRef).toContain('M46')
    expect(t.note.length).toBeGreaterThanOrEqual(15)
    expect(factsSrc, '后端未登记 M46 笔误').toContain('M46')
  })
})

// ─── Property 17: 红字与编制说明真源（Task 13 步骤 B 的判据前置） ─────────────

describe('源模板红字与编制说明真源与后端逐字一致', () => {
  it('红字原文逐字一致，且恰三处区块登记（O48 不得凭空补第 4 处）', () => {
    expect(factsSrc, '红字原文与后端漂移').toContain(K0_ALT_RED_HINT)
    expect(Object.keys(K0_ALT_RED_HINT_BLOCKS).sort()).toEqual(['block1', 'block2', 'block3'])
    expect(Object.values(K0_ALT_RED_HINT_BLOCKS)).toEqual(['O15', 'O26', 'O38'])
    // block4 是源外增强区块（SOURCE_EXTRA_MANIFEST 已登记），源模板无红字
    expect(K0_ALT_RED_HINT_BLOCKS).not.toHaveProperty('block4')
  })

  it('编制说明 3 条逐字与后端一致（含锚点）', () => {
    expect(K0_ALT_PREPARATION_ITEMS).toHaveLength(3)
    expect(PREP_ITEMS_SRC.length).toBeGreaterThan(80)
    for (const item of K0_ALT_PREPARATION_ITEMS) {
      expect(PREP_ITEMS_SRC, `锚点 ${item.anchor} 未登记`).toContain(`"${item.anchor}"`)
      expect(PREP_ITEMS_SRC, `文案未登记: ${item.text}`).toContain(item.text)
    }
    expect(K0_ALT_PREPARATION_ITEMS.map((i) => i.anchor)).toEqual(['B68', 'B69', 'B70'])
  })
})

// ─── Property 18: 真源已接线（防「写好从未渲染」） ────────────────────────────

describe('Property 18: 红字与编制说明已在两个组件真实渲染（真源零消费方即打红）', () => {
  const FE_SRC = path.join(ROOT, 'audit-platform', 'frontend', 'src')
  const K05_VUE = path.join(
    FE_SRC, 'components/workpaper/confirmation/alternativeK05/GtConfirmationAlternativeK05.vue',
  )
  const K06_VUE = path.join(
    FE_SRC, 'components/workpaper/confirmation/alternativeK06/GtConfirmationAlternativeK06.vue',
  )

  it.each([
    ['K0-5', K05_VUE, 'k05'],
    ['K0-6', K06_VUE, 'k06'],
  ] as const)('%s 组件 import 真源并渲染红字琥珀块与编制说明', (_code, file, prefix) => {
    const src = fs.readFileSync(file, 'utf-8')
    // import 了真源（不是抄第二份中文）
    expect(src, '未 import 红字真源').toMatch(/K0_ALT_RED_HINT\b/)
    expect(src, '未 import 编制说明真源').toMatch(/K0_ALT_PREPARATION_ITEMS\b/)
    expect(src, '未 import 红字区块映射').toMatch(/K0_ALT_RED_HINT_BLOCKS\b/)
    // 段①② 走 v-for 动态 testid（源码里是模板字符串，不是展开后的 block1/block2）
    expect(src, '缺 v-for 区块的动态红字锚点').toContain(`${prefix}-red-hint-\${bt}`)
    // 该动态块必须由 redHintAnchorOf 门控（段④ 无红字 ⇒ 不渲染）
    expect(src, '红字琥珀块未由 redHintAnchorOf 门控').toMatch(
      /v-if="redHintAnchorOf\(bt\)"/,
    )
    expect(src, '缺 redHintAnchorOf 实现').toMatch(
      /function redHintAnchorOf\([\s\S]{0,200}K0_ALT_RED_HINT_BLOCKS\[/,
    )
    // 段③（借贷拆表）是单独渲染的，锚点为静态字面
    expect(src, '缺 block3 的红字锚点').toContain(`${prefix}-red-hint-block3`)
    // 段④ 不得有第 4 处红字（源模板 O48 为空）——静态锚点与显式传参两种写法都禁
    expect(src, '段④ 凭空补了第 4 处红字').not.toContain(`${prefix}-red-hint-block4`)
    expect(src, '段④ 被显式传进 redHintAnchorOf').not.toMatch(
      /redHintAnchorOf\(\s*['"]block4['"]\s*\)/,
    )
    // 编制说明区存在且用 v-for 遍历真源
    expect(src).toContain(`${prefix}-preparation-notes`)
    expect(src).toMatch(/v-for="item in K0_ALT_PREPARATION_ITEMS"/)
  })

  it('两个组件都不得硬编码红字原文（只许经真源引入）', () => {
    for (const file of [K05_VUE, K06_VUE]) {
      const src = fs.readFileSync(file, 'utf-8')
      // 出现在插值 `{{ K0_ALT_RED_HINT }}` 里是对的；出现为字面字符串就是双真源
      const literalHits = src.split(K0_ALT_RED_HINT).length - 1
      expect(literalHits, `${path.basename(file)} 硬编码了红字原文 = 双真源`).toBe(0)
    }
  })

  it('两个组件都不得硬编码编制说明文案', () => {
    for (const file of [K05_VUE, K06_VUE]) {
      const src = fs.readFileSync(file, 'utf-8')
      for (const item of K0_ALT_PREPARATION_ITEMS) {
        expect(src, `${path.basename(file)} 硬编码了「${item.text}」= 双真源`).not.toContain(item.text)
      }
    }
  })
})

// ─── 段②③④ 未被误改（具体化列受源模板红字授权） ────────────────────────────

describe('段②③④ 的具体化证据列未被误改（红字授权具体化，不是缺陷）', () => {
  it('K0-5 段② 的审批单/借据协议列仍在', () => {
    const fields = BLOCK_COLUMN_CONFIGS_K05.block2.columns.map((c) => c.field)
    for (const f of ['approval_date_no', 'approval_proper', 'agreement_no', 'agreement_party', 'agreement_amount']) {
      expect(fields, `段② 丢了 ${f}`).toContain(f)
    }
  })

  it('K0-5/K0-6 段④ 往来对账列仍在（源外增强区块）', () => {
    expect(BLOCK_COLUMN_CONFIGS_K05.block4.columns.map((c) => c.field)).toContain('reconcile_diff')
    expect(BLOCK_COLUMN_CONFIGS_K06.block4.columns.map((c) => c.field)).toContain('reconcileDiff')
  })

  it('四区块 blockType 与键一致（结构未被打乱）', () => {
    for (const key of ['block1', 'block2', 'block3', 'block4']) {
      expect(BLOCK_COLUMN_CONFIGS_K05[key].blockType).toBe(key)
      expect(BLOCK_COLUMN_CONFIGS_K06[key].blockType).toBe(key)
    }
  })
})
