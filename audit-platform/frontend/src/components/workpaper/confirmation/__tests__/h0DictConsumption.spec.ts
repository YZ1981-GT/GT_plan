/**
 * h0DictConsumption.spec.ts — 函证枚举单一真源守卫（前后端交叉锁死）
 *
 * spec: h0-confirmation-source-fidelity-and-linkage
 *   Requirements 1.1 / 1.3 / 1.4 / 12.4；Property 1 / 30
 *
 * 🔴 本守卫存在的理由（改造前实证）：
 * `GtConfirmationSummary.vue` 与 `GtConfirmationDiffReconcile.vue` **各写一份**内置
 * 字面量数组，且**都与后端 system_dicts 不一致** ——
 *   - Summary 的 `confirmation_account_type` 只有 7 项（后端 22 项），H 循环品种
 *     （固定资产/工程物资/使用权资产/租赁负债…）一个都选不出来 → H0-1 下区矩阵按
 *     「账户/交易」列 SUMIF 分品种，品种名选不出即恒空；
 *   - DiffReconcile 的 `subjectOptions` 13 项同样无一个 H 类科目。
 * 两处都带 `// TODO: 从 useDictStore 获取`，但谁都没接，且各自漂移了两年。
 *
 * 守卫手法：直读后端 `system_dicts.py` 源码（跨前后端交叉锁死的唯一可靠手段），
 * 与前端 `CONFIRMATION_DICT_FALLBACK` 比对；并断言两个组件源码里不再出现字面量数组。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {
  CONFIRMATION_DICTS,
  CONFIRMATION_DICT_FALLBACK,
  FRONTEND_LEGACY_DICT_EXTRAS,
  fallbackOptions,
  fallbackSelectOptions,
} from '../coordination/confirmationDicts'
import { H0_MATRIX_DEFAULT_CATEGORIES } from '../h0SummaryMatrix'

// ─── 仓库根定位（向上找到含 backend/ 的目录，避免写死回退级数） ───────────────

function findRepoRoot(from: string): string {
  let dir = from
  for (let i = 0; i < 12; i++) {
    if (fs.existsSync(path.join(dir, 'backend', 'app', 'routers', 'system_dicts.py'))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未能定位仓库根（从 ${from} 向上找 backend/app/routers/system_dicts.py）`)
}

const REPO_ROOT = findRepoRoot(__dirname)
const SYSTEM_DICTS_PY = path.join(REPO_ROOT, 'backend', 'app', 'routers', 'system_dicts.py')
const CONFIRMATION_DIR = path.join(REPO_ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper', 'confirmation')

// ─── 后端字典解析 ────────────────────────────────────────────────────────────

/** 去掉 Python 行注释（`#` 开头，含行内），避免注释里的示例字面量被数进取值 */
function stripPyComments(src: string): string {
  return src
    .split('\n')
    .map((line) => {
      // 仅当 # 不在字符串内时才截断；本文件的取值均为 "..."，用简易状态机足够
      let inStr: string | null = null
      for (let i = 0; i < line.length; i++) {
        const ch = line[i]
        if (inStr) {
          if (ch === inStr) inStr = null
        } else if (ch === '"' || ch === "'") {
          inStr = ch
        } else if (ch === '#') {
          return line.slice(0, i)
        }
      }
      return line
    })
    .join('\n')
}

/** 从 system_dicts.py 抽某个字典 key 的 label 序列（保序） */
function backendLabels(dictKey: string): string[] {
  const src = stripPyComments(fs.readFileSync(SYSTEM_DICTS_PY, 'utf-8'))
  const start = src.indexOf(`"${dictKey}": [`)
  expect(start, `system_dicts.py 未找到字典 "${dictKey}"`).toBeGreaterThan(-1)
  // 从 '[' 起做括号配对，取整块（不能用 indexOf(']') —— 取值里可能含 ']'）
  const open = src.indexOf('[', start)
  let depth = 0
  let end = -1
  for (let i = open; i < src.length; i++) {
    if (src[i] === '[') depth++
    else if (src[i] === ']') {
      depth--
      if (depth === 0) {
        end = i
        break
      }
    }
  }
  expect(end, `字典 "${dictKey}" 括号未配对`).toBeGreaterThan(open)
  const block = src.slice(open, end + 1)
  return [...block.matchAll(/"label":\s*"([^"]*)"/g)].map((m) => m[1])
}

/** 去掉 TS/Vue 注释（块注释 + 行注释），防注释里的反例字面量被判成真实代码 */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

function readSfc(rel: string): { raw: string; code: string } {
  const p = path.join(CONFIRMATION_DIR, rel)
  const raw = fs.readFileSync(p, 'utf-8')
  return { raw, code: stripComments(raw) }
}

// ─── Property 30: 后端字典 ↔ 前端回退常量交叉锁死 ───────────────────────────

const CROSS_LOCKED_KEYS = [
  CONFIRMATION_DICTS.ACCOUNT_TYPE,
  CONFIRMATION_DICTS.SUBJECT,
  CONFIRMATION_DICTS.METHOD,
  CONFIRMATION_DICTS.SEND_CHANNEL,
  CONFIRMATION_DICTS.SAMPLE_PURPOSE,
  CONFIRMATION_DICTS.ADDR_VERIFY,
  CONFIRMATION_DICTS.REPLY_METHOD,
  CONFIRMATION_DICTS.MATCH_STATUS,
  CONFIRMATION_DICTS.YES_NO,
  CONFIRMATION_DICTS.SEND_RESULT,
  CONFIRMATION_DICTS.SAMPLING_METHOD,
]

describe('Property 30: 后端 system_dicts ↔ 前端 CONFIRMATION_DICT_FALLBACK', () => {
  it.each(CROSS_LOCKED_KEYS)('%s — 后端全部标签都在前端回退常量里', (dictKey) => {
    const be = backendLabels(dictKey)
    expect(be.length, `后端 ${dictKey} 解析出 0 项（正则失效？）`).toBeGreaterThan(0)
    const fe = new Set(fallbackOptions(dictKey))
    const missing = be.filter((l) => !fe.has(l))
    expect(missing, `${dictKey} 前端回退常量缺后端标签`).toEqual([])
  })

  it.each(CROSS_LOCKED_KEYS)('%s — 前端多出的标签必须登记为历史遗留', (dictKey) => {
    const be = new Set(backendLabels(dictKey))
    const extras = fallbackOptions(dictKey).filter((l) => !be.has(l))
    const registered = new Set(
      FRONTEND_LEGACY_DICT_EXTRAS.filter((e) => e.dictKey === dictKey).map((e) => e.label),
    )
    const unregistered = extras.filter((l) => !registered.has(l))
    expect(unregistered, `${dictKey} 前端多出未登记的标签`).toEqual([])
  })

  it('后端权威部分保序（前端回退常量以后端序列开头）', () => {
    for (const dictKey of [CONFIRMATION_DICTS.SEND_CHANNEL, CONFIRMATION_DICTS.SAMPLE_PURPOSE, CONFIRMATION_DICTS.ADDR_VERIFY]) {
      expect(fallbackOptions(dictKey)).toEqual(backendLabels(dictKey))
    }
  })

  it('每条历史遗留登记都有理由且确实不在后端', () => {
    expect(FRONTEND_LEGACY_DICT_EXTRAS.length).toBeGreaterThan(0)
    for (const e of FRONTEND_LEGACY_DICT_EXTRAS) {
      expect(e.reason.trim().length, `${e.dictKey}/${e.label} 缺登记理由`).toBeGreaterThan(8)
      expect(backendLabels(e.dictKey)).not.toContain(e.label)
    }
  })
})

// ─── Property 1: H 类品种齐备（两个字典 + 前端回退三处一致） ─────────────────

const H_CYCLE_CONFIRM_CATEGORIES = [
  '固定资产', '在建工程', '投资性房地产', '工程物资', '油气资产',
  '固定资产清理', '生产性生物资产', '使用权资产', '租赁负债',
]

describe('Property 1: H 循环品种在三处齐备', () => {
  it.each([CONFIRMATION_DICTS.ACCOUNT_TYPE, CONFIRMATION_DICTS.SUBJECT])(
    '%s — 前端回退常量含 9 个 H 类品种',
    (dictKey) => {
      const fe = new Set(fallbackOptions(dictKey))
      const missing = H_CYCLE_CONFIRM_CATEGORIES.filter((c) => !fe.has(c))
      expect(missing, `${dictKey} 缺 H 类品种`).toEqual([])
    },
  )

  it('两个字典中的 H 类品种标签顺序逐字一致（防漂移）', () => {
    const pick = (k: string) => fallbackOptions(k).filter((l) => H_CYCLE_CONFIRM_CATEGORIES.includes(l))
    expect(pick(CONFIRMATION_DICTS.ACCOUNT_TYPE)).toEqual(H_CYCLE_CONFIRM_CATEGORIES)
    expect(pick(CONFIRMATION_DICTS.SUBJECT)).toEqual(H_CYCLE_CONFIRM_CATEGORIES)
  })
})

// ─── Property 1: 两个组件不得再写内置字面量数组 ─────────────────────────────

describe('Property 1: 组件不得内联枚举字面量', () => {
  it('GtConfirmationSummary.vue 的 dictData 引用单一真源', () => {
    const { raw, code } = readSfc('GtConfirmationSummary.vue')

    // 反向自检：改造前那份 7 项数组的特征取值「长期应收款」曾出现在本文件
    // （若下面断言变成恒真，说明特征取值已不存在，需重写本自检）
    expect(raw.includes('CONFIRMATION_DICT_FALLBACK') || raw.includes('fallbackOptions')).toBe(true)

    expect(code).toContain('fallbackOptions(')
    // 改造前的字面量特征：dictData 里直接写中文品种数组
    expect(code).not.toMatch(/confirmation_account_type\s*:\s*\[\s*'/)
    expect(code).not.toContain("'长期应收款'")
    expect(code).not.toContain("'第三方平台'")
    expect(code).not.toContain("'当面递交'")
  })

  it('GtConfirmationDiffReconcile.vue 的 subjectOptions 引用单一真源', () => {
    const { code } = readSfc('diffReconcile/GtConfirmationDiffReconcile.vue')
    expect(code).toContain('fallbackSelectOptions(')
    // 改造前的 13 项字面量特征
    expect(code).not.toMatch(/value:\s*'应收账款'\s*,\s*label:\s*'应收账款'/)
  })

  it('stripComments 自检：注释中的反例不被计入', () => {
    const src = `
      // const x = [{ value: '应收账款', label: '应收账款' }]
      /* value: '长期应收款' */
      const y = fallbackSelectOptions(K)
    `
    const cleaned = stripComments(src)
    expect(cleaned).not.toContain('长期应收款')
    expect(cleaned).not.toMatch(/value:\s*'应收账款'/)
    expect(cleaned).toContain('fallbackSelectOptions')
    // 原文确实含被禁字样 → 证明 strip 不是对空输入生效
    expect(src).toContain('长期应收款')
  })
})

// ─── Property 2 / 11: 矩阵品种 ⊆ 枚举 + 注入字段有真实消费方 ─────────────────

describe('Property 2: 矩阵默认品种 ⊆ 账户/交易枚举', () => {
  it('H0_MATRIX_DEFAULT_CATEGORIES 每项都在枚举里（否则按品种 SUMIF 恒空）', () => {
    const fe = new Set(fallbackOptions(CONFIRMATION_DICTS.ACCOUNT_TYPE))
    for (const c of H0_MATRIX_DEFAULT_CATEGORIES) {
      expect(fe.has(c), `矩阵默认品种「${c}」不在 confirmation_account_type 枚举里`).toBe(true)
    }
  })

  it('后端 h0_book_amounts 的品种映射也在枚举里（三方一致）', () => {
    const src = fs.readFileSync(
      path.join(REPO_ROOT, 'backend', 'app', 'services', 'four_table', 'h0_book_amounts.py'),
      'utf-8',
    )
    const cats = [...src.matchAll(/category="([^"]+)"/g)].map((m) => m[1])
    expect(cats.length, '未解析出后端品种（正则失效？）').toBeGreaterThan(0)
    const fe = new Set(fallbackOptions(CONFIRMATION_DICTS.ACCOUNT_TYPE))
    for (const c of cats) {
      expect(fe.has(c), `后端品种「${c}」不在前端枚举里`).toBe(true)
    }
    // 矩阵默认品种必须是后端有取数能力的子集（否则账面金额永远取不到）
    for (const c of H0_MATRIX_DEFAULT_CATEGORIES) {
      expect(cats).toContain(c)
    }
  })
})

describe('Property 11: 注入字段有真实消费方且在矩阵入参链上', () => {
  const summary = readSfc('GtConfirmationSummary.vue').code
  const lower = readSfc('H0SummaryLowerZone.vue').code

  it('h0_book_amounts / h0_book_source_codes 各有消费点', () => {
    expect(summary).toContain('h0_book_amounts')
    expect(summary).toContain('h0_book_source_codes')
  })

  it('消费点在 buildH0SummaryMatrix 入参链上（不是赋值即弃）', () => {
    // 宿主把注入值传给下区组件的 book-amounts prop
    expect(summary).toMatch(/:book-amounts="h0BookAmounts"/)
    expect(summary).toMatch(/:book-source-codes="h0BookSourceCodes"/)
    // 下区组件把 props.bookAmounts 传进 buildH0SummaryMatrix
    const idx = lower.indexOf('buildH0SummaryMatrix({')
    expect(idx, 'H0SummaryLowerZone 未调用 buildH0SummaryMatrix').toBeGreaterThan(-1)
    const call = lower.slice(idx, idx + 400)
    expect(call).toContain('bookAmounts: props.bookAmounts')
    // 反向自检：入参不得写死 undefined（f0 曾因此让矩阵 4 个比例行恒「-」）
    expect(call).not.toMatch(/bookAmounts:\s*undefined/)
    expect(call).not.toMatch(/manualOverrides:\s*undefined/)
  })

  it('两态可区分：不得把 undefined 兜底成空对象', () => {
    // 「键不存在=未取数」与「值为 null=本项目无此科目」是两种状态，
    // 写 `?? {}` 会把前者变成后者（全部品种显示「本项目无此科目」）。
    expect(summary).not.toMatch(/h0_book_amounts\s*\?\?\s*\{\}/)
  })

  it('溯源面板真实消费 source_codes 的字段', () => {
    for (const f of ['resolved_from', 'row_code', 'formula_hint', 'gross']) {
      expect(lower, `溯源面板未消费 ${f}`).toContain(f)
    }
  })
})

// ─── 辅助函数行为 ────────────────────────────────────────────────────────────

describe('fallbackOptions / fallbackSelectOptions', () => {
  it('未登记的 key 返回空数组而非抛错', () => {
    expect(fallbackOptions('confirmation_not_exist')).toEqual([])
    expect(fallbackSelectOptions('confirmation_not_exist')).toEqual([])
  })

  it('fallbackSelectOptions 的 value 与 label 相同（既有持久化值即中文标签）', () => {
    for (const o of fallbackSelectOptions(CONFIRMATION_DICTS.SUBJECT)) {
      expect(o.value).toBe(o.label)
    }
  })

  it('回退常量为冻结对象（防运行期被组件改写成第二真源）', () => {
    expect(Object.isFrozen(CONFIRMATION_DICT_FALLBACK)).toBe(true)
    for (const key of CROSS_LOCKED_KEYS) {
      expect(Object.isFrozen(CONFIRMATION_DICT_FALLBACK[key]), `${key} 未冻结`).toBe(true)
    }
  })
})


// ─── 下区录入持久化路径（2026-08-04 浏览器实测暴露的两个缺陷） ────────────────

describe('H0 下区录入必须走 checklist-responses，不得 emit save 覆盖 sheet 载荷', () => {
  const SUMMARY = fs.readFileSync(
    path.join(__dirname, '..', 'GtConfirmationSummary.vue'),
    'utf-8',
  )
  const CODE = SUMMARY
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:"'`\\])\/\/.*$/gm, '$1')

  /** 花括号配对截取具名函数体（固定字符窗口会溢出到下一个函数）。 */
  function fnBody(src: string, name: string): string {
    const decl = src.search(new RegExp(`(async\\s+)?function ${name}\\(`))
    expect(decl, `未找到 function ${name}(`).toBeGreaterThan(-1)
    const open = src.indexOf('{', decl)
    let depth = 0
    for (let i = open; i < src.length; i++) {
      if (src[i] === '{') depth++
      else if (src[i] === '}') {
        depth--
        if (depth === 0) return src.slice(open, i + 1)
      }
    }
    throw new Error(`${name} 花括号未配对`)
  }

  it('🔴 handleH0LowerSave 直接 PUT checklist-responses，不得 emit(save)', () => {
    const body = fnBody(CODE, 'handleH0LowerSave')
    expect(body).toContain('/checklist-responses')
    expect(body).toMatch(/http\.put\(/)
    // 实测：emit('save', {itemId,value}) 会被宿主写成整个 sheet 的 html_data
    // → `html_data['函证结果汇总表H0-1']` 被覆盖成 {"itemId":...,"value":"4"}，
    //   连带清掉函证行，该 sheet 下次打开退化成「旧格式只读」。
    expect(body).not.toMatch(/emit\(\s*['"]save['"]/)
  })

  it('两处 checklist-responses 调用都带 /api 前缀（漏了会拿回 index.html 静默变空）', () => {
    const calls = CODE.match(/['"`]\/[^'"`]*checklist-responses[^'"`]*['"`]/g) || []
    expect(calls.length).toBeGreaterThanOrEqual(2)
    for (const c of calls) {
      expect(c, c).toMatch(/^['"`]\/api\//)
    }
  })

  it('反向自检：源码里确实出现过 checklist-responses（否则上条断言空转）', () => {
    expect(SUMMARY).toContain('checklist-responses')
  })

  it('冲突三元组必须翻成中文句子，不得裸 String() 渲染', () => {
    // h0BookConflicts 是 computed 不是 function → 按声明起点切到下一个顶层 const
    const start = CODE.indexOf('const h0BookConflicts')
    expect(start).toBeGreaterThan(0)
    const seg = CODE.slice(start, CODE.indexOf('\nconst ', start + 10))
    expect(seg).toContain('H0_SLOT_LABELS')
    expect(seg).toContain('报表行公式引用')
    // 旧实现 `v.map(String)` 会渲染成 `impairment,1601,1602,1606,1603`
    expect(seg).not.toMatch(/\.map\(String\)/)
  })

  it('H0_SLOT_LABELS 键集与后端 h_cycle_specs 的槽键一致（交叉锁死）', async () => {
    const { H0_SLOT_LABELS } = await import('../h0SummaryMatrix')
    const specDir = path.join(REPO_ROOT, 'backend', 'app', 'services', 'four_table')
    const keys = new Set<string>()
    for (const n of fs.readdirSync(specDir)) {
      if (!/^h\d+_account_scope\.py$/.test(n)) continue
      const src = fs.readFileSync(path.join(specDir, n), 'utf-8')
      for (const m of src.matchAll(/\bkey="([a-z_]+)"/g)) keys.add(m[1])
    }
    expect(keys.size).toBeGreaterThan(4) // 正则失效自检
    for (const k of keys) {
      expect(Object.keys(H0_SLOT_LABELS), `槽 ${k} 未登记中文标签`).toContain(k)
    }
  })
})
