/**
 * customWpBatchParse.spec.ts — 批量创建清单解析与门控守卫
 *
 * spec: custom-workpaper-dual-mode-formula-and-batch Wave 6 Task 22
 *
 * 覆盖 Property：
 *   - Property 11（前端侧）：两种输入（粘贴文本 / Excel 行）解析出**同构**结果
 *   - 校验幂等 + 清单内重号检出 + 超限如实上报（PBT，numRuns=20）
 *   - R8.2 / R8.3 门控：有 invalid 行时「确认创建」按钮 disabled（源码级 + tooltip）
 *   - 前后端常量交叉锁死（`MAX_BATCH_ITEMS` / 编号正则）
 *
 * 🔴 判据设计（平台铁律，逐条都踩过）：
 *   - 标签/符号存在性断言带**边界**（`<Foo(?=[\s/>])`），否则被 `<FooREMOVED` 骗过
 *   - 读源码前先 stripComments，并配「剥注释确实生效」反向自检
 *   - 断言「门控存在」用**条件表达式形态**而非其中出现的标识符
 *     （`:disabled="false"` 会让「标识符仍在」的弱判据通过）
 *   - 交叉锁死直接读后端 .py 源码（防「改一侧另一侧不红」）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import fs from 'node:fs'
import path from 'node:path'

import {
  MAX_BATCH_ITEMS,
  WP_CODE_RE,
  canSubmitPreview,
  normalizeWpCode,
  parseExcelRows,
  parseTextList,
  submitBlockedReason,
  validateItems,
  type ParsedItem,
  type PreviewRow,
} from '../customWpBatchParse'

// ─── 仓库根：双哨兵具体文件向上查找（禁写死回退级数） ─────────────────────────
function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    const a = path.join(dir, 'backend', 'app', 'routers', 'wp_template.py')
    const b = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('repoRoot 未找到（双哨兵均需存在）')
}
const ROOT = repoRoot()

function readFileAt(rel: string): string {
  const p = path.join(ROOT, rel)
  if (!fs.existsSync(p)) throw new Error(`守卫判据文件缺失: ${rel}`)
  const txt = fs.readFileSync(p, 'utf-8')
  if (!txt.trim()) throw new Error(`守卫判据文件为空: ${rel}`)
  return txt
}

/** 剥 JS/TS 注释（字符串状态机，避免 URL `//` 与 `accept="image/*"` 误判） */
function stripComments(src: string): string {
  let out = ''
  let i = 0
  let mode: 'code' | 'line' | 'block' | 'sq' | 'dq' | 'tpl' = 'code'
  while (i < src.length) {
    const ch = src[i]
    const next = src[i + 1]
    if (mode === 'code') {
      if (ch === '/' && next === '/') { mode = 'line'; i += 2; continue }
      if (ch === '/' && next === '*') { mode = 'block'; i += 2; continue }
      if (ch === "'") { mode = 'sq'; out += ch; i++; continue }
      if (ch === '"') { mode = 'dq'; out += ch; i++; continue }
      if (ch === '`') { mode = 'tpl'; out += ch; i++; continue }
      out += ch; i++; continue
    }
    if (mode === 'line') { if (ch === '\n') { mode = 'code'; out += ch }; i++; continue }
    if (mode === 'block') { if (ch === '*' && next === '/') { mode = 'code'; i += 2 } else i++; continue }
    out += ch
    if (ch === '\\') { out += next ?? ''; i += 2; continue }
    if ((mode === 'sq' && ch === "'") || (mode === 'dq' && ch === '"') || (mode === 'tpl' && ch === '`')) mode = 'code'
    i++
  }
  return out
}

/**
 * 剥 Python 注释与 docstring。
 *
 * 行尾注释必须字符串感知 —— `s = "keep#me"` 里的 `#` 不是注释。
 * 平台已实证：裸 `#.*$` 会把字符串内容一起剥掉，让「剥注释生效」自检假红。
 */
function stripPy(src: string): string {
  const noDoc = src
    .replace(/"""[\s\S]*?"""/g, '""')
    .replace(/'''[\s\S]*?'''/g, "''")
  return noDoc
    .split('\n')
    .map((line) => {
      let q: string | null = null
      for (let i = 0; i < line.length; i++) {
        const c = line[i]
        if (q) {
          if (c === '\\') { i++; continue }
          if (c === q) q = null
          continue
        }
        if (c === '\'' || c === '"') { q = c; continue }
        if (c === '#') return line.slice(0, i)
      }
      return line
    })
    .join('\n')
}

/**
 * 按**花括号配对**截函数体（正则匹配到开括号，再配对到闭括号）。
 *
 * 🔴 禁用固定字符窗口 `[\\s\\S]{0,N}` —— N 短于真实函数体时断言假红、
 * N 长于函数体时会越界命中下一个函数。平台已实证多次。
 */
function braceBody(src: string, header: RegExp): string {
  const m = src.match(header)
  if (!m || m.index == null) throw new Error(`braceBody: 未匹配到 ${header}`)
  let i = src.indexOf('{', m.index)
  if (i < 0) throw new Error('braceBody: 未找到开括号')
  let depth = 0
  const start = i
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++
    else if (src[i] === '}') {
      depth--
      if (depth === 0) return src.slice(start, i + 1)
    }
  }
  throw new Error('braceBody: 花括号不配对')
}

const DIALOG_REL = 'audit-platform/frontend/src/components/workpaper/custom/GtCustomWpBatchDialog.vue'
const LIST_REL = 'audit-platform/frontend/src/views/WorkpaperList.vue'
const TPL_REL = 'backend/app/routers/wp_template.py'
const PARSE_REL = 'audit-platform/frontend/src/components/workpaper/custom/customWpBatchParse.ts'

// ════════════════════════════════════════════════════════════════════════════
describe('守卫自检', () => {
  it('stripComments 剥注释而保留字符串内容', () => {
    const sample = `const a = 1 // hasBlocking\nconst u = 'https://x/y' /* hasBlocking */\nconst k = "keep//me"`
    const cleaned = stripComments(sample)
    expect(cleaned).not.toContain('hasBlocking')
    expect(cleaned).toContain('https://x/y')
    expect(cleaned).toContain('keep//me')
  })

  it('stripPy 剥 Python 注释而保留字符串', () => {
    const sample = 'def f():\n    """doc begin_nested"""\n    x = 1  # begin_nested\n    s = "keep#me"'
    const cleaned = stripPy(sample)
    expect(cleaned).not.toContain('begin_nested')
    expect(cleaned).toContain('keep#me')
  })

  it('标签断言必须带边界（弱判据对照）', () => {
    const mutated = '<GtCustomWpBatchDialogREMOVED v-model="x" />'
    expect(mutated).toContain('<GtCustomWpBatchDialog') // 弱判据被骗过
    expect(new RegExp('<GtCustomWpBatchDialog(?=[\\s/>])').test(mutated)).toBe(false)
  })

  it('readFileAt 对缺失文件抛错（防守卫空转）', () => {
    expect(() => readFileAt('backend/__no_such_file__.py')).toThrow(/判据文件缺失/)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 11: 两种输入解析同构', () => {
  it('粘贴文本按 Tab / 逗号 / 多空格切列', () => {
    const items = parseTextList('X1\t自定义底稿一\tX\nX2,自定义底稿二\nX3   自定义底稿三')
    expect(items.map((i) => i.wp_code)).toEqual(['X1', 'X2', 'X3'])
    expect(items.map((i) => i.wp_name)).toEqual(['自定义底稿一', '自定义底稿二', '自定义底稿三'])
    expect(items[0].audit_cycle).toBe('X')
    expect(items[1].audit_cycle).toBeUndefined()
  })

  it('Excel 表头行被识别并按列名映射（不当数据行）', () => {
    const rows: unknown[][] = [
      ['编号', '名称', '循环'],
      ['X1', '自定义底稿一', 'X'],
    ]
    const items = parseExcelRows(rows)
    expect(items).toHaveLength(1)
    expect(items[0].wp_code).toBe('X1')
    expect(items[0].wp_name).toBe('自定义底稿一')
    expect(items[0].audit_cycle).toBe('X')
  })

  it('表头列序颠倒时仍按列名映射（不按位置）', () => {
    const rows: unknown[][] = [
      ['名称', '编号'],
      ['自定义底稿一', 'X1'],
    ]
    const items = parseExcelRows(rows)
    expect(items).toHaveLength(1)
    // 🔴 按位置读会把名称当编号 —— 这条正是「按列名映射」的存在理由
    expect(items[0].wp_code).toBe('X1')
    expect(items[0].wp_name).toBe('自定义底稿一')
  })

  it('无表头时按位置解析', () => {
    const rows: unknown[][] = [['X1', '自定义底稿一']]
    const items = parseExcelRows(rows)
    expect(items).toHaveLength(1)
    expect(items[0].wp_code).toBe('X1')
    expect(items[0].wp_name).toBe('自定义底稿一')
  })

  it('空行/全空白行跳过，行号仍指向原始行（便于报错定位）', () => {
    const items = parseTextList('X1\t一\n\n   \nX2\t二')
    expect(items).toHaveLength(2)
    expect(items[0].line).toBe(1)
    expect(items[1].line).toBe(4) // 原始第 4 行
  })

  it('两种输入对同一逻辑清单产出同构结果（忽略 line）', () => {
    const fromText = parseTextList('X1\t一\tX\nX2\t二\tX')
    const fromExcel = parseExcelRows([
      ['编号', '名称', '循环'],
      ['X1', '一', 'X'],
      ['X2', '二', 'X'],
    ])
    const norm = (a: ParsedItem[]) =>
      a.map(({ wp_code, wp_name, audit_cycle }) => ({ wp_code, wp_name, audit_cycle }))
    expect(norm(fromText)).toEqual(norm(fromExcel))
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('validateItems: 格式 / 清单内重号 / 库内重号 / 超限', () => {
  it('合法项进 valid，errors 为空', () => {
    const r = validateItems(parseTextList('X1\t一\nX2\t二'))
    expect(r.valid.map((v) => v.wp_code)).toEqual(['X1', 'X2'])
    expect(r.errors).toEqual([])
    expect(r.overflow).toBe(false)
  })

  it('清单内重复被检出（带原始行号）', () => {
    const r = validateItems(parseTextList('X1\t一\nX1\t二'))
    expect(r.valid).toHaveLength(1)
    expect(r.errors).toHaveLength(1)
    expect(r.errors[0].line).toBe(2)
    expect(r.errors[0].reason).toContain('清单内编号重复')
  })

  it('大小写不同视为清单内同一编号（normalizeWpCode 归一）', () => {
    expect(normalizeWpCode(' x1 ')).toBe('X1')
    const r = validateItems(parseTextList('x1\t一\nX1\t二'))
    expect(r.valid).toHaveLength(1)
    expect(r.errors[0].reason).toContain('清单内编号重复')
  })

  it('库内已存在编号按后端口径（精确匹配）检出，大小写不同不误拦', () => {
    const items = parseTextList('X1\t一\nx1b\t二')
    const r = validateItems(items, ['X1'])
    expect(r.errors.some((e) => e.wp_code === 'X1' && e.reason.includes('已存在'))).toBe(true)
    // 🔴 `x1b` 与库内 `X1` 精确不等 ⇒ 必须放行（归一后比会假阻断）
    expect(r.valid.map((v) => v.wp_code)).toEqual(['x1b'])
  })

  it('编号为空 / 名称为空 / 非法字符 均落 errors', () => {
    const r = validateItems([
      { wp_code: '', wp_name: '一', line: 1 },
      { wp_code: 'X2', wp_name: '', line: 2 },
      { wp_code: '中文码', wp_name: '三', line: 3 },
      { wp_code: '-X4', wp_name: '四', line: 4 },
    ])
    expect(r.valid).toEqual([])
    expect(r.errors.map((e) => e.line)).toEqual([1, 2, 3, 4])
    expect(r.errors[0].reason).toContain('编号不能为空')
    expect(r.errors[1].reason).toContain('名称不能为空')
    expect(r.errors[2].reason).toContain('字母')
  })

  it('超过上限时置 overflow 且**不截断** valid', () => {
    const items: ParsedItem[] = Array.from({ length: MAX_BATCH_ITEMS + 3 }, (_, i) => ({
      wp_code: `X${i + 1}`,
      wp_name: `名称${i + 1}`,
      line: i + 1,
    }))
    const r = validateItems(items)
    expect(r.overflow).toBe(true)
    // 🔴 不截断：截断会让用户以为整份清单都提交了
    expect(r.valid).toHaveLength(MAX_BATCH_ITEMS + 3)
  })

  it('PBT: 校验幂等（同输入两次结论一致）', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            wp_code: fc.string({ minLength: 0, maxLength: 6 }),
            wp_name: fc.string({ minLength: 0, maxLength: 6 }),
            line: fc.integer({ min: 1, max: 50 }),
          }),
          { maxLength: 12 },
        ),
        (items) => {
          const a = validateItems(items as ParsedItem[])
          const b = validateItems(items as ParsedItem[])
          expect(a).toEqual(b)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('PBT: valid ∪ errors 覆盖全部输入行且互不重叠', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            wp_code: fc.constantFrom('X1', 'x1', 'X2', '', '中文', 'A-1'),
            wp_name: fc.constantFrom('一', ''),
            line: fc.integer({ min: 1, max: 50 }),
          }),
          { maxLength: 12 },
        ),
        (items) => {
          const r = validateItems(items as ParsedItem[])
          expect(r.valid.length + r.errors.length).toBe(items.length)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('PBT: valid 里的编号两两归一后不重复', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            wp_code: fc.constantFrom('X1', 'x1', 'X2', 'x2', 'X3'),
            wp_name: fc.constant('名'),
            line: fc.integer({ min: 1, max: 50 }),
          }),
          { maxLength: 10 },
        ),
        (items) => {
          const r = validateItems(items as ParsedItem[])
          const keys = r.valid.map((v) => normalizeWpCode(v.wp_code))
          expect(new Set(keys).size).toBe(keys.length)
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('canSubmitPreview / submitBlockedReason: 提交门控', () => {
  const row = (status: PreviewRow['status'], code = 'X1'): PreviewRow => ({
    wp_code: code,
    wp_name: '名',
    status,
  })

  it('空清单不可提交且给出原因', () => {
    expect(canSubmitPreview([])).toBe(false)
    expect(submitBlockedReason([])).toContain('请先粘贴或上传清单')
  })

  it('有 invalid 行时禁止提交（R8.3）', () => {
    const rows = [row('ok'), row('invalid', 'X2')]
    expect(canSubmitPreview(rows)).toBe(false)
    expect(submitBlockedReason(rows)).toContain('1 行存在错误')
  })

  it('duplicate_db / duplicate_input 不阻断（创建时跳过属正常幂等）', () => {
    const rows = [row('ok'), row('duplicate_db', 'X2'), row('duplicate_input', 'X3')]
    expect(canSubmitPreview(rows)).toBe(true)
    expect(submitBlockedReason(rows)).toBe('')
  })

  it('全部已存在/重复（无 ok）时不可提交并说明原因', () => {
    const rows = [row('duplicate_db'), row('duplicate_input', 'X2')]
    expect(canSubmitPreview(rows)).toBe(false)
    expect(submitBlockedReason(rows)).toContain('没有可创建的新编号')
  })

  it('可提交时 blockedReason 必为空串（禁只 disable 不说明的反面）', () => {
    fc.assert(
      fc.property(
        fc.array(fc.constantFrom<PreviewRow['status']>('ok', 'duplicate_db', 'duplicate_input', 'invalid'), {
          minLength: 1,
          maxLength: 8,
        }),
        (statuses) => {
          const rows = statuses.map((s, i) => row(s, `X${i + 1}`))
          const can = canSubmitPreview(rows)
          const reason = submitBlockedReason(rows)
          // 不可提交 ⇔ 有原因；可提交 ⇔ 无原因
          expect(can).toBe(reason === '')
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('R8.2 / R8.3: 门控前置为 disabled（不是点了才提示）', () => {
  const dialog = stripComments(readFileAt(DIALOG_REL))

  it('确认创建按钮 disabled 受 canSubmit 驱动（非仅 loading）', () => {
    // 🔴 条件形态判据：`:disabled="false"` 或只绑 loading 都必须打红
    // 词边界：`canSubmitX` 不得命中（弱判据被改名骗过是同族第 N 次踩）
    expect(/:disabled="[^"]*!\s*canSubmit(?![A-Za-z0-9_])[^"]*"/.test(dialog)).toBe(true)
    // 且该 computed 必须真的存在（改名即红）
    expect(/const\s+canSubmit(?![A-Za-z0-9_])\s*=\s*computed/.test(dialog)).toBe(true)
  })

  it('禁用时有 tooltip 说明原因（blockedReason）', () => {
    expect(/const\s+blockedReason(?![A-Za-z0-9_])\s*=\s*computed/.test(dialog)).toBe(true)
    expect(/blockedReason(?![A-Za-z0-9_])/.test(dialog)).toBe(true)
    // tooltip / title 任一承载
    expect(/(el-tooltip|:title=)/.test(dialog)).toBe(true)
  })

  it('创建前必须先预览（doCreate 依赖 previewRows）', () => {
    // 🔴 花括号配对截函数体，禁固定字符窗口（平台已多次踩：窗口短于函数体即假红）
    const body = braceBody(dialog, /async function doCreate\s*\([^)]*\)\s*\{/)
    expect(body.length).toBeGreaterThan(200)
    expect(body).toMatch(/previewRows/)
  })

  it('预览端点与创建端点都走 apiPaths 或显式路径且成对存在', () => {
    expect(dialog).toMatch(/create-custom-batch\/preview|customWpBatchPreview|batchPreview/)
    expect(dialog).toMatch(/create-custom-batch|customWpBatch/)
  })

  it('dialog 已挂载到底稿列表（否则用户不可达）', () => {
    const list = stripComments(readFileAt(LIST_REL))
    expect(new RegExp('<GtCustomWpBatchDialog(?=[\\s/>])').test(list)).toBe(true)
    expect(list).toMatch(/GtCustomWpBatchDialog/)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('前后端常量交叉锁死', () => {
  const py = stripPy(readFileAt(TPL_REL))

  it('MAX_BATCH_ITEMS 两侧相等', () => {
    const m = py.match(/^MAX_BATCH_ITEMS\s*=\s*(\d+)/m)
    expect(m).toBeTruthy()
    expect(Number(m![1])).toBe(MAX_BATCH_ITEMS)
  })

  it('编号正则两侧字符集一致', () => {
    const m = py.match(/WP_CODE_PATTERN\s*=\s*r?"([^"]+)"/)
    expect(m).toBeTruthy()
    const feSrc = WP_CODE_RE.source
    // 后端是 python 正则字符串，前端是 RegExp.source；比对核心字符集片段
    expect(m![1]).toContain('[A-Za-z0-9][A-Za-z0-9\\-_.]{0,31}')
    expect(feSrc).toContain('[A-Za-z0-9][A-Za-z0-9\\-_.]{0,31}')
  })

  it('后端确实使用了该正则做校验（非死常量）', () => {
    expect(py).toMatch(/re\.fullmatch\(\s*WP_CODE_PATTERN\s*,/)
  })

  it('前端解析层零 Vue 依赖（便于 PBT）', () => {
    const parse = readFileAt(PARSE_REL)
    expect(parse).not.toMatch(/from\s+['"]vue['"]/)
    expect(parse).not.toMatch(/from\s+['"]element-plus['"]/)
  })
})
