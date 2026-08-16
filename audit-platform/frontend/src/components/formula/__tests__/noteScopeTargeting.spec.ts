/**
 * noteScopeTargeting.spec.ts — 附注域「公式管理」定位/筛选守卫
 *
 * 锁三件事：
 *  1. note_section → 树节点 key 的规则（附注页打开弹窗时按此 key 定位章节）；
 *  2. 章节公式筛选按「标题精确」优先，避免「债权投资」把「其他债权投资」的公式带出来；
 *  3. FormulaManagerDialog 真的消费了本模块，且附注分支排在报表启发式之前
 *     （否则附注行 row_code 会被兜底判成 balance_sheet，回到默认「报表 > 资产负债表」）。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  noteSectionToNodeKey,
  isNoteDomainNodeKey,
  filterNotePresetsForSection,
  buildNoteFormulaRows,
  type NotePresetFormula,
} from '../noteScopeTargeting'

/**
 * 按花括号配对截取函数体（先跳过参数列表与返回类型注解）。
 * 不用固定字符窗口 / `\n}\n` 锚点：源文件是 CRLF，行锚点会恒不命中而把断言变成假绿/假红。
 */
function extractFunctionBody(src: string, declaration: string): string {
  const start = src.indexOf(declaration)
  if (start < 0) throw new Error(`未找到声明：${declaration}`)
  // 跳过参数列表 (...)
  const paren = src.indexOf('(', start)
  let depth = 0
  let i = paren
  for (; i < src.length; i++) {
    if (src[i] === '(') depth++
    else if (src[i] === ')') {
      depth--
      if (depth === 0) { i++; break }
    }
  }
  const bodyStart = src.indexOf('{', i)
  if (bodyStart < 0) throw new Error(`未找到函数体：${declaration}`)
  depth = 0
  for (let j = bodyStart; j < src.length; j++) {
    if (src[j] === '{') depth++
    else if (src[j] === '}') {
      depth--
      if (depth === 0) return src.slice(bodyStart, j + 1)
    }
  }
  throw new Error(`花括号未闭合：${declaration}`)
}

const PRESETS: NotePresetFormula[] = [
  { id: 'F1-1', note_section: '五、1', section_title: '货币资金', formula: 'A' },
  { id: 'F1-2', note_section: '五、1', section_title: '货币资金', formula: 'B' },
  { id: 'F14-1', note_section: '五、14', section_title: '债权投资', formula: 'C' },
  { id: 'F15-1', note_section: '五、15', section_title: '其他债权投资', formula: 'D' },
  { id: 'F17-1', note_section: '五、17', section_title: '其他综合收益', formula: 'E' },
]

describe('noteSectionToNodeKey', () => {
  it('中文顿号/空白归一为下划线', () => {
    expect(noteSectionToNodeKey('五、1')).toBe('note_五_1')
    expect(noteSectionToNodeKey('十三、1')).toBe('note_十三_1')
    expect(noteSectionToNodeKey('七、本期不再纳入合并')).toBe('note_七_本期不再纳入合并')
    expect(noteSectionToNodeKey('九')).toBe('note_九')
  })

  it('与 FormulaManagerDialog 附注树 key 规则同源（树里正是用它生成 key）', () => {
    const src = readFileSync(
      resolve(__dirname, '../FormulaManagerDialog.vue'),
      'utf-8',
    )
    // 树构建处必须调用本函数，而不是各自 inline replace（否则定位 key 会漂）
    const inlineKeyRule = /key:\s*`note_\$\{[^}]*replace\(/g
    expect(src.match(inlineKeyRule)).toBeNull()
    expect((src.match(/key: noteSectionToNodeKey\(sectionId\)/g) || []).length).toBe(2)
  })
})

describe('isNoteDomainNodeKey', () => {
  it('域根节点 note 与章节 note_* 都算附注域', () => {
    expect(isNoteDomainNodeKey('note')).toBe(true)
    expect(isNoteDomainNodeKey('note_五_1')).toBe(true)
    expect(isNoteDomainNodeKey('note_chapter_五')).toBe(true)
  })
  it('其它域不误判', () => {
    expect(isNoteDomainNodeKey('report_balance_sheet')).toBe(false)
    expect(isNoteDomainNodeKey('notebook')).toBe(false)
    expect(isNoteDomainNodeKey('tb_detail')).toBe(false)
    expect(isNoteDomainNodeKey('')).toBe(false)
  })
})

describe('filterNotePresetsForSection', () => {
  it('标题精确命中本章节全部公式', () => {
    const rows = filterNotePresetsForSection(PRESETS, {
      sectionId: '五、1',
      sectionTitle: '货币资金',
    })
    expect(rows.map((r) => r.id)).toEqual(['F1-1', 'F1-2'])
  })

  it('标题互含不串扰：债权投资不得带出其他债权投资', () => {
    const rows = filterNotePresetsForSection(PRESETS, {
      sectionId: '五、14',
      sectionTitle: '债权投资',
    })
    expect(rows.map((r) => r.id)).toEqual(['F14-1'])
  })

  it('编号体系偏移时以标题为准（项目「五、17」标题不同则不取预设「五、17」）', () => {
    // 实测：上市版项目「五、17」是「设定受益计划净资产」，预设集「五、17」是「其他综合收益」
    const rows = filterNotePresetsForSection(PRESETS, {
      sectionId: '五、17',
      sectionTitle: '设定受益计划净资产',
    })
    expect(rows).toEqual([])
  })

  it('标题缺失时退到编号精确匹配', () => {
    const rows = filterNotePresetsForSection(PRESETS, { sectionId: '五、15' })
    expect(rows.map((r) => r.id)).toEqual(['F15-1'])
  })

  it('标题被裁剪时走双向 includes 兜底', () => {
    const rows = filterNotePresetsForSection(PRESETS, { sectionTitle: '1、货币资金' })
    expect(rows.map((r) => r.id)).toEqual(['F1-1', 'F1-2'])
  })

  it('无章节上下文返回空（由调用方决定是否展示全部）', () => {
    expect(filterNotePresetsForSection(PRESETS, {})).toEqual([])
    expect(filterNotePresetsForSection([], { sectionTitle: '货币资金' })).toEqual([])
  })
})

describe('buildNoteFormulaRows', () => {
  it('章节命中 → 只列本章节公式（映射为表格行）', () => {
    const rows = buildNoteFormulaRows(PRESETS, { sectionId: '五、1', sectionTitle: '货币资金' })
    expect(rows).toHaveLength(2)
    expect(rows.map((r) => r.row_name)).toEqual(['货币资金', '货币资金'])
    expect(rows[0]).toMatchObject({ id: 'note_preset_0', row_code: '五、1', formula: 'A' })
  })

  it('章级节点/无上下文 → 列全部（不给空表）', () => {
    expect(buildNoteFormulaRows(PRESETS, {})).toHaveLength(PRESETS.length)
  })

  it('筛不出（标题对不上）→ 退回全部而非空表', () => {
    const rows = buildNoteFormulaRows(PRESETS, { sectionTitle: '设定受益计划净资产' })
    expect(rows).toHaveLength(PRESETS.length)
  })

  it('空预设集 → 空行', () => {
    expect(buildNoteFormulaRows([], { sectionTitle: '货币资金' })).toEqual([])
  })
})

describe('FormulaManagerDialog 接线（防死代码 / 防回归到报表分支）', () => {
  const src = readFileSync(resolve(__dirname, '../FormulaManagerDialog.vue'), 'utf-8')

  it('导入并消费本模块三个导出', () => {
    expect(src).toContain("from './noteScopeTargeting'")
    expect(src).toContain('return buildNoteFormulaRows(notePresetFormulas.value, {')
    expect(src).toContain('isNoteDomainNodeKey(selectedNodeKey.value)')
  })

  it('附注行不再由组件内 inline 映射/过滤（逻辑单一真源在 noteScopeTargeting）', () => {
    expect(src).not.toContain("(f.section_title || '').includes(targetTitle)")
    expect(src).not.toContain('id: `note_preset_${i}`')
  })

  it('调用页章节上下文只用于本页章节/域根节点，章级节点不套用', () => {
    // 章级节点（note_chapter_*）沿用「显示全部」，否则点某一章会错列成本页章节的公式
    expect(src).toContain('const isPageSectionNode = nodeKey === \'note\'')
    expect(src).toContain('nodeKey === noteSectionToNodeKey(propSection)')
    expect(src).toContain('if (isPageSectionNode) {')
  })

  it('附注 scope 分支排在报表启发式（props.rows）之前', () => {
    const noteBranch = src.indexOf("props.scope === 'note'")
    const reportHeuristic = src.indexOf('props.rows?.length')
    expect(noteBranch).toBeGreaterThan(-1)
    expect(reportHeuristic).toBeGreaterThan(-1)
    expect(noteBranch).toBeLessThan(reportHeuristic)
  })

  it('附注 scope 分支调用定位函数，且定位函数会回退到附注域根节点', () => {
    expect(src).toContain('await applyNoteScopeTarget()')
    const body = extractFunctionBody(src, 'async function applyNoteScopeTarget')
    expect(body).toContain('noteSectionToNodeKey')
    expect(body).toContain("selectedNodeKey.value = 'note'")
    // 兜底不得落到报表域
    expect(body).not.toContain('report_')
  })

  it('模板版本跟随调用页（上市版页面不加载国企版预设）', () => {
    expect(src).toContain('normalizeTemplateType(props.templateType)')
    expect(src).toContain('fmTemplateType = ref<string>(normalizeTemplateType(props.templateType))')
  })
})

function dialogTag(viewFile: string): string {
  const src = readFileSync(resolve(__dirname, '../../../views/', viewFile), 'utf-8')
  const i = src.indexOf('<FormulaManagerDialog')
  if (i < 0) throw new Error(`${viewFile} 未挂载 FormulaManagerDialog`)
  return src.slice(i, src.indexOf('/>', i))
}

describe('调用页传参（缺一即回到默认报表节点 / 错版预设）', () => {
  it('DisclosureEditor 传 scope=note + 当前章节编号/标题 + 模板类型', () => {
    const tag = dialogTag('DisclosureEditor.vue')
    expect(tag).toContain('scope="note"')
    expect(tag).toContain(':note-section="currentNote?.note_section')
    expect(tag).toContain(':note-section-title="currentNote?.section_title')
    expect(tag).toContain(':template-type="templateType"')
  })

  it('ReportView 传模板类型（上市版项目不得加载国企版 report_config）', () => {
    const tag = dialogTag('ReportView.vue')
    expect(tag).toContain('scope="report"')
    expect(tag).toContain(':template-type="selectedTemplateType"')
  })
})
