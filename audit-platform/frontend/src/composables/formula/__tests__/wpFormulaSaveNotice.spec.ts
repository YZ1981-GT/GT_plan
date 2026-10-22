/**
 * 底稿公式保存回执提示（spec formula-governance-coverage-closure R6.3 / R5 走查）：
 * 算不出值（后端只回 eval_warnings、格子留空）时提示必须写明原因，不能只说「公式已保存」或只报条数。
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { savedDefinitionVersion, wpFormulaBatchNotice, wpFormulaSaveNotice } from '../wpFormulaSaveNotice'

const SRC = path.resolve(__dirname, '../../..')
/** 保存底稿公式的写法：`api.put(wpFormula.upsert(…)` / `api.put(apiPaths.workpapers.formulas(…)` */
const SAVE_CALL = /api\.put\(\s*(?:wpFormula\.upsert|apiPaths\.workpapers\.formulas)\(/

/** 从 `api.put(` 起按括号配平截出整段调用（请求体在里面） */
function callBlocks(text: string): string[] {
  const out: string[] = []
  for (const m of text.matchAll(new RegExp(SAVE_CALL.source, 'g'))) {
    const start = m.index ?? 0
    let depth = 0
    for (let i = start + 'api.put'.length; i < text.length; i++) {
      if (text[i] === '(') depth++
      else if (text[i] === ')' && --depth === 0) { out.push(text.slice(start, i + 1)); break }
    }
  }
  return out
}

function sourceFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const full = path.join(dir, e.name)
    if (e.isDirectory()) return e.name === '__tests__' || e.name === 'node_modules' ? [] : sourceFiles(full)
    return /\.(vue|ts)$/.test(e.name) && !/\.spec\.ts$/.test(e.name) ? [full] : []
  })
}

describe('wpFormulaSaveNotice', () => {
  it('算不出值：警告级，带单元格与原因原文', () => {
    const n = wpFormulaSaveNotice({ eval_warnings: ["REPORT('BS-002','期初')：报表行 BS-002 上期金额为空"] }, 'B6')
    expect(n.level).toBe('warning')
    expect(n.text).toContain('B6')
    expect(n.text).toContain('没有算出值（已留空）')
    expect(n.text).toContain('上期金额为空')
    expect(n.warnings).toHaveLength(1)
  })

  it('原因最多列 2 条，其余给条数；有原因时不显示数值', () => {
    const n = wpFormulaSaveNotice({ evaluated_value: '0', eval_warnings: ['甲', '乙', '丙', '丁'] }, 'B7')
    expect(n.text).toContain('甲；乙')
    expect(n.text).not.toContain('丙')
    expect(n.text).toContain('另有 2 条')
    expect(n.text).not.toContain('= 0')
  })

  it('算出值：成功级并报值；0 也是值', () => {
    expect(wpFormulaSaveNotice({ evaluated_value: '300.00' }, 'B5')).toMatchObject({ level: 'success', text: '公式已保存，B5 = 300.00' })
    expect(wpFormulaSaveNotice({ evaluated_value: 0 }, 'B8').text).toBe('公式已保存，B8 = 0')
  })

  it('没有求值结果也没有原因（非自动运算、F2 锚点等）：只说已保存', () => {
    expect(wpFormulaSaveNotice({}, 'B5')).toMatchObject({ level: 'success', text: '公式已保存' })
    expect(wpFormulaSaveNotice(null).text).toBe('公式已保存')
    expect(wpFormulaSaveNotice({ eval_warnings: ['', '  '] }).level).toBe('success')
  })
})

describe('savedDefinitionVersion', () => {
  it('版本在回执的 saved 下；顶层同名字段不算（后端从不放顶层）', () => {
    expect(savedDefinitionVersion({ saved: { definition_version: 2 } })).toBe(2)
    expect(savedDefinitionVersion({ definition_version: 5 } as any)).toBeNull()
    expect(savedDefinitionVersion({ saved: null })).toBeNull()
    expect(savedDefinitionVersion(undefined)).toBeNull()
  })
})

describe('wpFormulaBatchNotice', () => {
  it('全部算出：成功级，保留跳过说明', () => {
    expect(wpFormulaBatchNotice(5, [], '（跳过 1 条只读投影）')).toMatchObject({
      level: 'success', text: '已保存 5 个公式（跳过 1 条只读投影）',
    })
  })

  it('有算不出的：警告级，列单元格与第一条原因，超过 2 个给个数', () => {
    const n = wpFormulaBatchNotice(4, [
      { cell: 'B6', warnings: ['上期金额为空', '另一条'] },
      { cell: 'B7', warnings: ['上年（2024）试算表无数据'] },
      { cell: 'B9', warnings: ['附注没有章节'] },
    ])
    expect(n.level).toBe('warning')
    expect(n.text).toContain('其中 3 个没有算出值（已留空）')
    expect(n.text).toContain('B6：上期金额为空')
    expect(n.text).toContain('B7：上年（2024）试算表无数据')
    expect(n.text).not.toContain('B9')
    expect(n.text).toContain('另有 1 个')
    expect(n.warnings).toHaveLength(4)
  })
})

describe('保存底稿公式的调用方都经提示函数', () => {
  it('每个 PUT 底稿公式的文件都用 wpFormulaSaveNotice（不许只提示「公式已保存」吞掉求值原因）', () => {
    const callers = sourceFiles(SRC).filter((f) => SAVE_CALL.test(fs.readFileSync(f, 'utf-8')))
    // 防空转：现有调用方 = 公式管理中心 / 自定义底稿编辑器 / 公式状态面板
    expect(callers.map((f) => path.basename(f)).sort()).toEqual(
      expect.arrayContaining(['FormulaManagerDialog.vue', 'FormulaStatusPanel.vue', 'GtCustomWpEditor.vue']),
    )
    // 逐处计数：一个文件里有几处保存，就要有几处经提示函数（公式管理中心有单条保存与「保存全部」两处）
    const count = (text: string, re: RegExp) => (text.match(new RegExp(re.source, 'g')) || []).length
    const short = callers.map((f) => {
      const text = fs.readFileSync(f, 'utf-8')
      return { file: path.relative(SRC, f), saves: count(text, SAVE_CALL), notices: count(text, /wpFormulaSaveNotice\(/) }
    }).filter((c) => c.notices < c.saves)
    expect(short).toEqual([])
  })

  it('每处保存都带 expected_version；保存后不从回执顶层读版本（R5 走查：自定义编辑器 428、公式管理中心第二次保存 409）', () => {
    const callers = sourceFiles(SRC).filter((f) => SAVE_CALL.test(fs.readFileSync(f, 'utf-8')))
    const noVersion = callers.flatMap((f) => callBlocks(fs.readFileSync(f, 'utf-8'))
      .filter((b) => !/\bexpected_version\s*:/.test(b)).map(() => path.relative(SRC, f)))
    expect(noVersion).toEqual([])
    const topLevel = callers.filter((f) => /\b(?:saved|savedRow|res|receipt)\?\.definition_version\b/
      .test(fs.readFileSync(f, 'utf-8'))).map((f) => path.relative(SRC, f))
    expect(topLevel).toEqual([])
    const fmd = fs.readFileSync(path.join(SRC, 'components', 'formula', 'FormulaManagerDialog.vue'), 'utf-8')
    expect((fmd.match(/savedDefinitionVersion\(/g) || []).length).toBe(callBlocks(fmd).length)
  })
})
