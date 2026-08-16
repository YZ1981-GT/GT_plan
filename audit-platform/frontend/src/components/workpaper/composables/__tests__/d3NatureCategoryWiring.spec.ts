/**
 * d3NatureCategoryWiring — D3「款项性质 / 关联方类型」枚举单一真源接线守卫
 *
 * Spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/ Task 26
 * Validates: Requirements 10.1, 10.2, 10.3
 *
 * 【为什么需要】源模板 `审定表D3-1!B8 = SUMIF('预收账款明细表D3-2'!$C$12:$C$22, A8, ...)`
 * ⇒ D3-2 C 列取值是 D3-1 性质行的联动键，两侧标签必须逐字相同。改造前 SFC 内联硬编码
 * 四个 label，与 `useD3Adjudication.NATURE_ROWS` 构成双真源（改一处另一处不动即静默断链）。
 *
 * 本守卫锁死三件事：
 *   1. 枚举真源只有 `d3NatureCategories.ts` 一份（rowKey 是持久化键，禁改名）
 *   2. `NATURE_ROWS` / 标签→rowKey map 必须**派生**而非重写字面量
 *   3. D3-2 明细表 C/D 两列的下拉候选必须来自真源，禁内联 label
 * 并反向锁死：禁按 `2203` 子科目名建 D3-2 行（D3-2 行维度是**对方单位**，见源模板 `A10`）。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import {
  D3_NATURE_CATEGORIES,
  D3_NATURE_LABELS,
  D3_NATURE_LABEL_TO_KEY,
  D3_RELATION_TYPES,
  D3_RELATION_TYPE_SOURCE_REF,
  D3_SOURCE_TEMPLATE_DEFECTS,
  d3NatureOptions,
  d3RelationTypeOptions,
} from '../d3NatureCategories'
import { NATURE_ROWS } from '../useD3Adjudication'

// ─── 仓库根定位（双哨兵向上查找，禁写死回退级数）────────────────────────────
function findRepoRoot(): string {
  let dir = path.resolve(__dirname)
  for (let i = 0; i < 12; i += 1) {
    const s1 = path.join(dir, 'backend', 'app', 'main.py')
    const s2 = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    if (fs.existsSync(s1) && fs.existsSync(s2)) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`findRepoRoot failed from ${__dirname}`)
}

const REPO_ROOT = findRepoRoot()
const FE = path.join(REPO_ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper')

function readSrc(rel: string): string {
  const p = path.join(FE, rel)
  if (!fs.existsSync(p)) throw new Error(`source not found: ${p}`)
  return fs.readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

/** 剥 JS/TS 注释（带字符串状态，避免 URL 双斜杠与 `accept="image/*"` 误判） */
function stripComments(src: string): string {
  let out = ''
  let i = 0
  let inS: string | null = null
  while (i < src.length) {
    const ch = src[i]
    const nx = src[i + 1]
    if (inS) {
      out += ch
      if (ch === '\\') {
        out += nx ?? ''
        i += 2
        continue
      }
      if (ch === inS) inS = null
      i += 1
      continue
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      inS = ch
      out += ch
      i += 1
      continue
    }
    if (ch === '/' && nx === '/') {
      while (i < src.length && src[i] !== '\n') i += 1
      continue
    }
    if (ch === '/' && nx === '*') {
      i += 2
      while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) i += 1
      i += 2
      continue
    }
    out += ch
    i += 1
  }
  return out
}

/** 从 SFC 里切出 `<template>` 段 */
function templateOf(sfc: string): string {
  const m = /<template>([\s\S]*)<\/template>/.exec(sfc)
  if (!m) throw new Error('template block not found')
  return m[1]
}

/** 按花括号配对截出某个 `<el-table-column ...>` 块（按 label 定位） */
function tableColumnBlock(tpl: string, label: string): string {
  const marker = `label="${label}"`
  const at = tpl.indexOf(marker)
  if (at < 0) throw new Error(`el-table-column label="${label}" not found`)
  const open = tpl.lastIndexOf('<el-table-column', at)
  if (open < 0) throw new Error(`opening tag for label="${label}" not found`)
  const close = tpl.indexOf('</el-table-column>', at)
  if (close < 0) throw new Error(`closing tag for label="${label}" not found`)
  return tpl.slice(open, close)
}

const D3_TAB_DETAIL = readSrc('d3/D3TabDetail.vue')
const USE_D3_ADJ = readSrc('composables/useD3Adjudication.ts')
const D3_NATURE_TS = readSrc('composables/d3NatureCategories.ts')

// ─── Property 32: 枚举真源形态 ───────────────────────────────────────────────
describe('Property 32: D3 款项性质枚举真源', () => {
  it('恰四类，顺序即源模板 R8→R11', () => {
    expect(D3_NATURE_LABELS).toEqual([
      '预收销售固定资产款',
      '预收销售土地使用权款',
      '合同不成立时已收取的对价',
      '其他',
    ])
  })

  it('rowKey 集合与源模板坐标齐备（rowKey 是持久化键，禁改名）', () => {
    expect(D3_NATURE_CATEGORIES.map((c) => c.rowKey)).toEqual([
      'fixed-asset-sales',
      'land-use-right',
      'contract-invalid',
      'other',
    ])
    for (const c of D3_NATURE_CATEGORIES) {
      expect(c.sourceRef, `${c.rowKey} 缺 sourceRef`).toMatch(/^审定表D3-1!A\d+$/)
      expect(c.label.trim().length).toBeGreaterThan(0)
    }
  })

  it('label 与 rowKey 均无重复', () => {
    expect(new Set(D3_NATURE_LABELS).size).toBe(D3_NATURE_LABELS.length)
    expect(new Set(D3_NATURE_CATEGORIES.map((c) => c.rowKey)).size).toBe(D3_NATURE_CATEGORIES.length)
  })

  it('LABEL_TO_KEY 与真源双向一致', () => {
    expect(Object.keys(D3_NATURE_LABEL_TO_KEY).sort()).toEqual([...D3_NATURE_LABELS].sort())
    for (const c of D3_NATURE_CATEGORIES) {
      expect(D3_NATURE_LABEL_TO_KEY[c.label]).toBe(c.rowKey)
    }
  })

  it('常量已冻结（禁运行时篡改）', () => {
    expect(Object.isFrozen(D3_NATURE_CATEGORIES)).toBe(true)
    expect(Object.isFrozen(D3_NATURE_LABEL_TO_KEY)).toBe(true)
    expect(Object.isFrozen(D3_RELATION_TYPES)).toBe(true)
  })
})

// ─── Property 33: D3-1 审定表性质行必须派生自真源 ────────────────────────────
describe('Property 33: NATURE_ROWS 派生自单一真源', () => {
  it('NATURE_ROWS 与真源逐字相等', () => {
    expect(NATURE_ROWS.map((r) => ({ rowKey: r.rowKey, label: r.label }))).toEqual(
      D3_NATURE_CATEGORIES.map((c) => ({ rowKey: c.rowKey, label: c.label })),
    )
  })

  it('useD3Adjudication.ts 已 import 真源且不得重写字面量 label', () => {
    const src = stripComments(USE_D3_ADJ)
    expect(src).toMatch(/import\s*\{[^}]*D3_NATURE_CATEGORIES[^}]*\}\s*from\s*'\.\/d3NatureCategories'/)
    // 生产代码里不得再出现四个性质 label 字面量（注释已剥离）
    for (const label of D3_NATURE_LABELS) {
      if (label === '其他') continue // 「其他」是通用词，另由下条 map 断言覆盖
      expect(
        src.includes(`'${label}'`) || src.includes(`"${label}"`),
        `useD3Adjudication.ts 出现性质 label 字面量 ${label}（应派生自 d3NatureCategories）`,
      ).toBe(false)
    }
  })

  it('NATURE_LABEL_TO_KEY 是派生赋值而非字面量对象', () => {
    const src = stripComments(USE_D3_ADJ)
    expect(src).toMatch(/NATURE_LABEL_TO_KEY[^=]*=\s*D3_NATURE_LABEL_TO_KEY/)
    // 反向：不得出现 `'xxx': 'fixed-asset-sales'` 这类第二份映射
    expect(src).not.toMatch(/:\s*'fixed-asset-sales'/)
  })
})

// ─── Property 34: D3-2 明细表两列下拉候选来自真源 ────────────────────────────
describe('Property 34: D3-2 C/D 列下拉候选来自真源', () => {
  const tpl = templateOf(D3_TAB_DETAIL)

  it('C 列「款项性质」用 v-for 遍历 d3NatureOptions', () => {
    const block = tableColumnBlock(tpl, '款项性质')
    expect(block).toMatch(/v-for="opt in d3NatureOptions\(/)
    expect(block).toMatch(/:value="opt"/)
  })

  it('C 列不得内联硬编码性质 label', () => {
    const block = tableColumnBlock(tpl, '款项性质')
    for (const label of D3_NATURE_LABELS) {
      expect(
        block.includes(label),
        `C 列内联硬编码 label ${label}（应 v-for 真源）`,
      ).toBe(false)
    }
  })

  it('D 列「关联方类型」用 v-for 遍历 d3RelationTypeOptions', () => {
    const block = tableColumnBlock(tpl, '关联方类型')
    expect(block).toMatch(/v-for="opt in d3RelationTypeOptions\(/)
    expect(block).toMatch(/:value="opt"/)
  })

  it('D 列不得内联源模板之外的关联方枚举（改造前的 6 项）', () => {
    const block = tableColumnBlock(tpl, '关联方类型')
    for (const stale of ['母公司', '子公司', '联营企业', '合营企业', '其他关联方']) {
      expect(
        block.includes(stale),
        `D 列内联了源模板之外的关联方取值 ${stale}`,
      ).toBe(false)
    }
  })

  it('SFC 已 import 两个候选函数', () => {
    const src = stripComments(D3_TAB_DETAIL)
    expect(src).toMatch(
      /import\s*\{[^}]*d3NatureOptions[^}]*d3RelationTypeOptions[^}]*\}\s*from\s*'\.\.\/composables\/d3NatureCategories'/,
    )
  })
})

// ─── Property 35: 历史枚举外值不丢（数据零丢失红线）────────────────────────
describe('Property 35: 历史枚举外值兼容', () => {
  it('关联方类型：源模板 3 项且与源坐标登记一致', () => {
    expect(D3_RELATION_TYPES).toEqual(['合并范围内关联方', '合并范围外关联方', '非关联方'])
    expect(D3_RELATION_TYPE_SOURCE_REF).toBe('预收账款明细表D3-2!D12:D23')
  })

  it('当前值在枚举内时候选不变', () => {
    expect(d3RelationTypeOptions('非关联方')).toEqual([...D3_RELATION_TYPES])
    expect(d3NatureOptions('其他')).toEqual([...D3_NATURE_LABELS])
  })

  it('历史枚举外值被追加为候选（否则 el-select 无法保住旧值）', () => {
    expect(d3RelationTypeOptions('母公司')).toEqual([...D3_RELATION_TYPES, '母公司'])
    expect(d3NatureOptions('货款')).toEqual([...D3_NATURE_LABELS, '货款'])
  })

  it('空/空白/undefined 不追加空选项', () => {
    for (const v of [undefined, null, '', '   ']) {
      expect(d3RelationTypeOptions(v as any)).toEqual([...D3_RELATION_TYPES])
      expect(d3NatureOptions(v as any)).toEqual([...D3_NATURE_LABELS])
    }
  })

  it('返回的是副本，调用方修改不污染真源', () => {
    const a = d3NatureOptions()
    a.push('污染')
    expect(D3_NATURE_LABELS).toHaveLength(4)
    expect(d3NatureOptions()).toHaveLength(4)
  })
})

// ─── Property 36: 反向锁死 —— 禁按 2203 子科目名建 D3-2 行 ───────────────────
describe('Property 36: 禁按 2203 子科目名建 D3-2 明细行', () => {
  /**
   * 立项 requirements 10.1 曾写「D3-2 按 2203 叶子子科目建行」，按源模板不成立：
   * `预收账款明细表D3-2!A10='对方单位名称'` ⇒ 行维度是**对方单位（客户）**。
   * 客户子科目实证只有 `2203.01 预收账款_预收货款` / `2203.02 预收账款_预收项目款`
   * （后者全部项目为 0），与 D3-1 四类性质不同构、SUMIF 匹配不上。
   * 数据来源已定为 `tb_aux_balance` 2203 **客户维度**归集（render 已记宁缺勿造决策）。
   */
  const FORBIDDEN_ROW_LABELS = ['预收货款', '预收项目款']

  it('D3-2 明细相关生产代码不得出现 2203 子科目名作行标签', () => {
    for (const rel of ['composables/useD3Detail.ts', 'd3/D3TabDetail.vue', 'composables/useD3CrossSheet.ts']) {
      const src = stripComments(readSrc(rel))
      for (const bad of FORBIDDEN_ROW_LABELS) {
        expect(src.includes(bad), `${rel} 出现 2203 子科目名 ${bad}（D3-2 行维度是对方单位）`).toBe(false)
      }
    }
  })

  it('反向自检：扫描面非空（源码确实被读到且含已知锚点）', () => {
    const src = readSrc('composables/useD3Detail.ts')
    expect(src.length).toBeGreaterThan(1000)
    expect(src).toContain('nature')
    // 证明 stripComments 未把整份源码吃空
    expect(stripComments(src).length).toBeGreaterThan(src.length * 0.4)
  })
})

// ─── Property 37: 源模板缺陷登记 ─────────────────────────────────────────────
describe('Property 37: 源模板自身缺陷已登记', () => {
  it('两处缺陷各带坐标与说明', () => {
    expect(D3_SOURCE_TEMPLATE_DEFECTS.length).toBeGreaterThanOrEqual(2)
    const refs = D3_SOURCE_TEMPLATE_DEFECTS.map((d) => d.ref).join('\n')
    expect(refs).toContain('C23')
    expect(refs).toContain('SUMIF')
    for (const d of D3_SOURCE_TEMPLATE_DEFECTS) {
      expect(d.note.length, `${d.ref} 说明过短`).toBeGreaterThan(30)
    }
  })

  it('缺陷① 的错误枚举不得被当成候选实现', () => {
    for (const wrong of ['货款', '工程款', '设备款', '服务费', '建造合同形成的已结算尚未完工款']) {
      expect(D3_NATURE_LABELS.includes(wrong), `源模板 C23 的错误枚举 ${wrong} 被实现成候选`).toBe(false)
    }
  })

  it('真源文件本身留有源模板依据（防后来者按常识改动）', () => {
    expect(D3_NATURE_TS).toContain('审定表D3-1')
    expect(D3_NATURE_TS).toContain('SUMIF')
    expect(D3_NATURE_TS).toContain('预收账款明细表D3-2')
  })
})
