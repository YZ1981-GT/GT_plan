/**
 * l0ColumnAlignment — L0-1 上区列集与源模板对齐的守卫
 *
 * spec: l0-confirmation-source-alignment，Task 19（Property 18 ~ 24 / 36）
 *
 * 判据真源 = `backend/tests/test_l0_source_template_facts.py`（openpyxl 直读
 * `backend/wp_templates/L/L0 债务循环函证.xlsx`）。本守卫**读后端源码抽常量**与
 * 前端 `confirmationColumnSpec.ts` 双向比对 —— 各写一份期望值 = 双真源，
 * 两侧漂移时守卫仍全绿（memory 已记的假绿范式）。
 *
 * 🔴 `REPO_ROOT` 用**双哨兵具体文件**向上查找：单哨兵不够稳（将来子目录出现同名
 *    文件即误停）；目录做哨兵会被 `audit-platform/backend/app/routers`
 *    （历史遗留空目录）骗停。
 *
 * 🔴 读源码型断言一律先 `stripComments()` —— 本 spec 的注释里如实写着被撤销的
 *    反例（`send_memo` / `F0-4` / 「联系人」），不剥注释会把说明文字数成真实声明。
 */

import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import {
  resolveConfirmationColumns,
  CYCLE_VARIANT_COLUMNS,
  CYCLE_EXCLUDED_COLUMNS,
  CYCLE_COLUMN_LABEL_OVERRIDES,
  COLUMN_GROUP_LABELS,
  BASE_CONFIRMATION_COLUMNS,
  VARIANT_COLUMN_DEFS,
  type ConfirmCycle,
} from '../../confirmationColumnSpec'
import {
  CONFIRMATION_SOURCE_MANIFEST,
  CONFIRMATION_SOURCE_COLUMN_LABELS,
} from '../../confirmationColumnSourceManifest'

// ─── REPO_ROOT（双哨兵具体文件） ─────────────────────────────────────────────

const SENTINELS = [
  'backend/tests/test_l0_source_template_facts.py',
  'backend/wp_templates/L/L0 债务循环函证.xlsx',
]

function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    if (SENTINELS.every((s) => fs.existsSync(path.join(dir, s)))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`REPO_ROOT 定位失败：从 ${__dirname} 向上未找到 ${SENTINELS.join(' + ')}`)
}

const REPO_ROOT = findRepoRoot()
const FE_ROOT = path.join(REPO_ROOT, 'audit-platform/frontend/src/components/workpaper/confirmation')
const FACTS_PY = path.join(REPO_ROOT, 'backend/tests/test_l0_source_template_facts.py')

const SPEC_SRC = fs.readFileSync(path.join(FE_ROOT, 'confirmationColumnSpec.ts'), 'utf-8')
const DETAIL_SRC = fs.readFileSync(path.join(FE_ROOT, 'ConfirmationDetail.vue'), 'utf-8')
const TYPES_SRC = fs.readFileSync(path.join(FE_ROOT, 'confirmationTypes.ts'), 'utf-8')
const FACTS_SRC = fs.readFileSync(FACTS_PY, 'utf-8')

// ─── 注释剥离（TS/Vue 与 Python 各一份） ─────────────────────────────────────

function stripTsComments(src: string): string {
  // 先剥块注释，再剥行注释（避免 URL 的 `//` 被误判：行注释判据要求 `//` 前不是 `:`）
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .map((line) => {
      const i = line.indexOf('//')
      if (i < 0) return line
      if (i > 0 && line[i - 1] === ':') return line
      return line.slice(0, i)
    })
    .join('\n')
}

function stripPyComments(src: string): string {
  return src
    .split('\n')
    .map((line) => {
      const i = line.indexOf('#')
      return i >= 0 ? line.slice(0, i) : line
    })
    .join('\n')
}

const SPEC_NO_COMMENT = stripTsComments(SPEC_SRC)
const FACTS_NO_COMMENT = stripPyComments(FACTS_SRC)

/**
 * 取 python `NAME = [...]` 的**常量体**（ASCII 方括号配对）。
 *
 * 🔴 必须按括号配对取体，**不能用固定字符窗口**（`slice(i, i + 1500)`）——
 * 窗口会越过常量末尾吃进下一个常量，判据就变成在无关文本上求值。
 * 本轮实测：`SOURCE_TEMPLATE_TYPOS` 的 1500 窗口吃进了紧随其后的
 * `CORRECT_INDEX_REFS = [("L0-1!S33", "L0-6")]`，使「S33 不得在笔误表里」恒红。
 * 同族坑 = memory 已记的「固定字符窗口截函数体」。
 */
function pyListBody(name: string): string {
  const decl = new RegExp(`^${name}\\s*=\\s*\\[`, 'm')
  const m = decl.exec(FACTS_NO_COMMENT)
  if (!m) throw new Error(`后端常量未找到：${name}（守卫会空转）`)
  const open = FACTS_NO_COMMENT.indexOf('[', m.index)
  let depth = 0
  let end = -1
  for (let i = open; i < FACTS_NO_COMMENT.length; i += 1) {
    const ch = FACTS_NO_COMMENT[i]
    if (ch === '[') depth += 1
    else if (ch === ']') {
      depth -= 1
      if (depth === 0) {
        end = i
        break
      }
    }
  }
  if (end < 0) throw new Error(`后端常量方括号未配对：${name}`)
  return FACTS_NO_COMMENT.slice(open + 1, end)
}

/** 抽 python `NAME = [...]` 的字符串字面量（行尾正则会被 CRLF 破坏，故走括号配对） */
function pyStrList(name: string): string[] {
  return Array.from(pyListBody(name).matchAll(/"([^"]*)"/g)).map((x) => x[1])
}

const L0_COLS = resolveConfirmationColumns('L0')
const L0_KEYS = L0_COLS.map((c) => c.key)
const OTHER_CYCLES: ConfirmCycle[] = ['D0', 'E0', 'F0', 'G0', 'H0', 'K0']

// ─── 自检（防断言空转） ─────────────────────────────────────────────────────

describe('l0ColumnAlignment 自检：源文件与剥注释器有效', () => {
  it('三份源码与后端 fixture 都读到了内容', () => {
    expect(SPEC_SRC.length).toBeGreaterThan(5000)
    expect(DETAIL_SRC.length).toBeGreaterThan(3000)
    expect(TYPES_SRC.length).toBeGreaterThan(500)
    expect(FACTS_SRC.length).toBeGreaterThan(10000)
  })

  it('stripTsComments 确实剥掉了注释（反向自检）', () => {
    expect(SPEC_SRC).toContain('伪列')
    expect(SPEC_NO_COMMENT).not.toContain('伪列')
  })

  it('剥注释未破坏 URL 里的双斜杠（同族坑对照）', () => {
    expect(stripTsComments('const u = "https://a.example/b" // tail')).toContain('https://a.example/b')
  })

  it('L0 解析出的列集非空（否则以下断言全部空转）', () => {
    expect(L0_COLS.length).toBeGreaterThan(20)
  })
})

// ─── Property 18: 伪列已撤且字段未删 ────────────────────────────────────────

describe('Property 18: send_memo 伪列已撤、字段未删、有只读呈现', () => {
  it('CYCLE_VARIANT_COLUMNS.L0 不含 send_memo', () => {
    expect(CYCLE_VARIANT_COLUMNS.L0).not.toContain('send_memo')
  })

  it('resolve 输出的 key 集合不含 send_memo（不再进列渲染）', () => {
    expect(L0_KEYS).not.toContain('send_memo')
  })

  it('ConfirmationRow 类型仍保留 send_memo 字段（数据零丢失红线）', () => {
    expect(stripTsComments(TYPES_SRC)).toMatch(/send_memo\??\s*:/)
  })

  it('行详情面板存在 send_memo 只读呈现分支（有值才显示）', () => {
    const noc = stripTsComments(DETAIL_SRC)
    expect(noc, '缺 v-if="row.send_memo" 的只读分支').toMatch(/v-if="row\.send_memo"/)
    expect(noc, '只读锚点 data-testid 缺失').toContain('send-memo-legacy-readonly')
    // readonly 必须真的加上（否则又变成一个录入口）
    const i = noc.indexOf('send-memo-legacy-readonly')
    expect(noc.slice(Math.max(0, i - 400), i)).toMatch(/\breadonly\b/)
  })

  it('只读分支不得带 @update/@change 之类写入口', () => {
    const noc = stripTsComments(DETAIL_SRC)
    const i = noc.indexOf('send-memo-legacy-readonly')
    const block = noc.slice(Math.max(0, i - 500), i + 200)
    expect(block).not.toMatch(/@update:model-value|@change|v-model="row\.send_memo"/)
  })

  /**
   * 🔴 改写记录（2026-08-07）：原断言「K0 仍保留 send_memo（本 spec 只撤 L0，
   * K0 归其自身 spec）」在 `k0-confirmation-source-alignment` R2.1 收口后失效 ——
   * 伪列 def 已从 `VARIANT_COLUMN_DEFS` **整条删除**，K0/L0 两侧统一撤下。
   * 本断言改为正向锁死「不得复活」，并保留字段与只读呈现（上面几条已断言）。
   */
  it('K0 也已撤下 send_memo，且伪列 def 已从注册表整条删除（不得复活）', () => {
    expect(CYCLE_VARIANT_COLUMNS.K0).not.toContain('send_memo')
    expect(Object.keys(VARIANT_COLUMN_DEFS)).not.toContain('send_memo')
    expect(resolveConfirmationColumns('K0').map((c) => c.key)).not.toContain('send_memo')
  })
})

// ─── Property 19: 行级审计结论归属独立段 ────────────────────────────────────

describe('Property 19: row_conclusion 归 row_summary 段且 source 指向 L0-1', () => {
  it('L0 用 l0_row_conclusion 这个注册 key', () => {
    expect(CYCLE_VARIANT_COLUMNS.L0).toContain('l0_row_conclusion')
  })

  it('resolve 输出中 row_conclusion 的 group 为 row_summary', () => {
    const col = L0_COLS.find((c) => c.key === 'row_conclusion')
    expect(col, 'L0 缺 row_conclusion 列').toBeDefined()
    expect(col!.group).toBe('row_summary')
  })

  it('source 指向 L0-1 而非 K0-1 / H0-1 / G0-1（溯源不得串枢纽）', () => {
    const col = L0_COLS.find((c) => c.key === 'row_conclusion')!
    expect(col.source).toContain('L0-1')
    for (const foreign of ['K0-1', 'H0-1', 'G0-1', 'E0-1', 'D0-1']) {
      expect(col.source, `source 串到 ${foreign}`).not.toContain(foreign)
    }
  })

  it('段标签为「行级审计结论」（源 AB5:AB7 在四段之外）', () => {
    expect(COLUMN_GROUP_LABELS.row_summary).toBe('行级审计结论')
  })

  it('L0 结果中不存在 group 为 send_memo 的列（该段整体不适用）', () => {
    expect(L0_COLS.filter((c) => c.group === 'send_memo')).toEqual([])
  })
})

// ─── Property 20: 空列噪声已剔除 ────────────────────────────────────────────

describe('Property 20: 三列空列噪声已剔除', () => {
  it('CYCLE_EXCLUDED_COLUMNS.L0 恰为三列', () => {
    expect(CYCLE_EXCLUDED_COLUMNS.L0).toEqual(['contact_person', 'contact_phone', 'currency'])
  })

  it('三列不在 resolve 输出中', () => {
    for (const k of ['contact_person', 'contact_phone', 'currency']) {
      expect(L0_KEYS, `${k} 未被剔除`).not.toContain(k)
    }
  })

  it('与后端 COLUMNS_ABSENT_IN_SOURCE 交叉锁死（源模板确实没这三列）', () => {
    // 🔴 后端该常量存的是**平台列 key**（英文），不是源模板中文 label ——
    //    实测 `['contact_person', 'contact_phone', 'currency']`。
    //    首版按中文 label 断言恒红，是判据缺陷不是代码缺陷。
    const absent = pyStrList('COLUMNS_ABSENT_IN_SOURCE')
    expect(absent.length, '后端常量抽取为空 → 本条断言空转').toBeGreaterThanOrEqual(3)
    for (const key of ['contact_person', 'contact_phone', 'currency']) {
      expect(absent, `后端未登记 ${key} 不存在于源模板`).toContain(key)
    }
    // 双向：后端登记的与前端剔除的必须是同一集合（防一侧漂移）
    expect([...absent].sort()).toEqual([...CYCLE_EXCLUDED_COLUMNS.L0].sort())
  })

  it('剔除的三列在 BASE 里确实存在（否则剔除是空操作）', () => {
    const baseKeys = BASE_CONFIRMATION_COLUMNS.map((c) => c.key)
    for (const k of ['contact_person', 'contact_phone', 'currency']) {
      expect(baseKeys).toContain(k)
    }
  })
})

// ─── Property 21: 渠道列与函证类型列显式区分 ────────────────────────────────

describe('Property 21: send_channel 与 confirmation_method 并存且不同名', () => {
  it('两列同时存在', () => {
    expect(L0_KEYS).toContain('send_channel')
    expect(L0_KEYS).toContain('confirmation_method')
  })

  it('两者 label 不相等（否则界面出现两个「函证方式」）', () => {
    const ch = L0_COLS.find((c) => c.key === 'send_channel')!
    const cm = L0_COLS.find((c) => c.key === 'confirmation_method')!
    expect(ch.label).not.toBe(cm.label)
  })

  it('confirmation_method 的 L0 label 含积极式/消极式（准则 1312 口径）', () => {
    const cm = L0_COLS.find((c) => c.key === 'confirmation_method')!
    expect(cm.label).toContain('积极式')
    expect(cm.label).toContain('消极式')
  })

  it('confirmation_method 未被改绑渠道枚举（可确认金额派生依赖它）', () => {
    const cm = L0_COLS.find((c) => c.key === 'confirmation_method')!
    for (const chan of ['邮寄', '跟函', '电子函证']) {
      expect(cm.label, `函证类型列被改绑渠道枚举：${chan}`).not.toContain(chan)
    }
  })

  it('send_channel 的 source 标明它是渠道且由 X0-2 带入', () => {
    const ch = L0_COLS.find((c) => c.key === 'send_channel')!
    expect(ch.source).toContain('渠道')
  })

  it('与后端 L02_REAL_DV 交叉锁死渠道四项', () => {
    // 后端把 L0-2 的真实 DV 固化为 dict，取值域里必有渠道四项
    const body = FACTS_NO_COMMENT.slice(FACTS_NO_COMMENT.indexOf('L02_REAL_DV'))
    for (const v of ['邮寄', '跟函', '电子函证', '其他']) {
      expect(body.slice(0, 1200), `后端 L02_REAL_DV 缺渠道项 ${v}`).toContain(v)
    }
  })
})

// ─── Property 22: label 覆盖逐条取自源模板 ──────────────────────────────────

describe('Property 22: L0 label 覆盖与源模板表头一致，且不动别的枢纽', () => {
  const ovr = CYCLE_COLUMN_LABEL_OVERRIDES.L0 as Readonly<Record<string, string>>

  it('L0 覆盖表存在且规模符合预期（13 处偏差）', () => {
    expect(ovr).toBeDefined()
    expect(Object.keys(ovr).length).toBeGreaterThanOrEqual(13)
  })

  it('「与 BASE 同 label」的登记项恰为已备案的三条（精确集合，不许悄悄变多）', () => {
    // 🔴 这三列源模板用词与 BASE 恰好相同，登记进覆盖表**只为证明已逐列核对**，
    //    不是冗余。用精确集合而非「数量上限」断言 —— 上限式断言能被「再塞一条」绕过，
    //    而多出来的那条恰恰是要拦的动作（同族：Object.freeze 登记表要双向锁死）。
    //    reply_from_addr 源 Q「回函发出地址」/ use_alternative 源 X「是否采取替代程序」
    //    / alt_unconfirmed 源 Z「替代后不可确认金额」—— 三者 BASE 用词一致。
    const baseByKey = new Map(BASE_CONFIRMATION_COLUMNS.map((c) => [c.key, c.label]))
    const sameAsBase = Object.entries(ovr)
      .filter(([k, v]) => baseByKey.get(k) === v)
      .map(([k]) => k)
      .sort()
    expect(sameAsBase).toEqual(['alt_unconfirmed', 'reply_from_addr', 'use_alternative'])
  })

  it('其余覆盖条目都真的改变了 BASE 的 label（不是整表冗余）', () => {
    const baseByKey = new Map(BASE_CONFIRMATION_COLUMNS.map((c) => [c.key, c.label]))
    const changed = Object.entries(ovr).filter(([k, v]) => baseByKey.get(k) !== v)
    // 13 处偏差 - 3 处「与 BASE 同」= 至少 10 处真实改写
    expect(changed.length, '覆盖表几乎没有真实改写 → 可能是空操作').toBeGreaterThanOrEqual(10)
  })

  it('关键几列的 label 逐字为源模板用词', () => {
    expect(ovr.account_type).toBe('账户/交易')
    expect(ovr.amount).toBe('金额')
    expect(ovr.confirm_index).toBe('询证函索引号')
    expect(ovr.difference).toBe('差异')
    expect(ovr.remark).toBe('其他说明/备注')
  })

  it('覆盖后 resolve 输出真的用了新 label（不是只改了常量）', () => {
    expect(L0_COLS.find((c) => c.key === 'account_type')!.label).toBe('账户/交易')
    expect(L0_COLS.find((c) => c.key === 'amount')!.label).toBe('金额')
  })

  it('五段表头与后端 SUMMARY_GROUP_HEADERS 交叉锁死', () => {
    const body = FACTS_NO_COMMENT.slice(FACTS_NO_COMMENT.indexOf('SUMMARY_GROUP_HEADERS'))
    const head = body.slice(0, 900)
    for (const seg of ['发函询证纪要', '发函信息', '收到回函', '回函金额确认', '审计结论']) {
      expect(head, `后端五段表头缺 ${seg}`).toContain(seg)
    }
  })

  it('override 表恰四键 G0/H0/K0/L0，且 L0 条目未被别的 spec 改动', () => {
    // 🔴 K0 于 2026-08-07 按其 spec R2.5 加入（名单式锁死的设计意图：新增须显式登记）。
    const keys = Object.keys(CYCLE_COLUMN_LABEL_OVERRIDES)
    expect(keys.sort()).toEqual(['G0', 'H0', 'K0', 'L0'])
    // L0 侧关键用词不得被 K0 的加入波及（各自 Object.freeze，浅拷贝套用）
    const l0 = CYCLE_COLUMN_LABEL_OVERRIDES.L0 as Readonly<Record<string, string>>
    expect(l0.amount).toBe('金额')
    expect(l0.diff_ref_index).toBe('调节索引（L0-4）')
  })
})

// ─── Property 23: 调节索引笔误已更正 ────────────────────────────────────────

describe('Property 23: diff_ref_index 展示 L0-4（源字面 F0-4 是笔误）', () => {
  const ovr = CYCLE_COLUMN_LABEL_OVERRIDES.L0 as Readonly<Record<string, string>>

  it('label 指向 L0-4', () => {
    expect(ovr.diff_ref_index).toBe('调节索引（L0-4）')
  })

  it('label 中不残留 F0-4（源模板笔误不得渗进展示层）', () => {
    expect(ovr.diff_ref_index).not.toContain('F0-4')
    expect(L0_COLS.find((c) => c.key === 'diff_ref_index')!.label).not.toContain('F0-4')
  })

  it('后端笔误登记表含该处，且正确值为 L0-4', () => {
    const body = FACTS_NO_COMMENT.slice(FACTS_NO_COMMENT.indexOf('SOURCE_TEMPLATE_TYPOS'))
    const head = body.slice(0, 1500)
    expect(head, '后端未登记 F0-4 笔误').toContain('F0-4')
    expect(head).toContain('L0-4')
  })

  it('L0-1!S33 的（L0-6）是正确索引号，不得被顺手改掉', () => {
    // 🔴 判据不能是「TYPOS 后 1500 字符里不出现 S33」——`CORRECT_INDEX_REFS`
    //    紧跟在 `SOURCE_TEMPLATE_TYPOS` 之后声明，其内容就含 `L0-1!S33`，
    //    裸窗口判定必然假红（memory 已记的「固定字符窗口截块」同族坑）。
    //    正解 = 按方括号配对精确取两个常量各自的 body 再分别判定。
    const typos = pyListBody('SOURCE_TEMPLATE_TYPOS')
    const correct = pyListBody('CORRECT_INDEX_REFS')

    expect(typos, '笔误表为空 → 本组断言空转').not.toBe('')
    expect(correct, '正确索引登记表为空 → 本组断言空转').not.toBe('')

    // S33 只许出现在「正确索引号」登记里，不得进笔误表
    expect(typos, 'S33 的（L0-6）被误登记成笔误').not.toContain('S33')
    expect(correct, 'S33 的（L0-6）未登记为正确索引号').toContain('S33')
    expect(correct).toContain('L0-6')

    // 反向自检：笔误表里确实有另外三处（证明上面那条 not.toContain 不是因为表空）
    for (const anchor of ['函证程序表F0A', 'L0-1!V6', 'L0-2!AA6', 'L0-1!S28']) {
      expect(typos, `笔误表缺登记项 ${anchor}`).toContain(anchor)
    }
  })
})

// ─── Property 24: manifest 覆盖 resolve 输出 ────────────────────────────────

describe('Property 24: resolve ⊆ manifest，且 NO_EXCLUSION 白名单已移出 L0', () => {
  it('L0 的 manifest 条目存在且非空', () => {
    const keys = CONFIRMATION_SOURCE_MANIFEST.L0
    expect(Array.isArray(keys)).toBe(true)
    expect(keys.length).toBeGreaterThan(20)
  })

  it('源模板列名清单恰 28 条（与 L0-1 的 A..AB 逐列对应）', () => {
    // 🔴 两个常量语义不同，别搞混（本守卫写错过一次）：
    //    `CONFIRMATION_SOURCE_COLUMN_LABELS.L0` = 源模板**中文列名**清单（28 条，= A..AB）
    //    `CONFIRMATION_SOURCE_MANIFEST.L0`      = 允许出现的**字段 key** 集合（33 条，含
    //                                             共性列 ∪ 该枢纽特有列，供 resolve ⊆ manifest 判定）
    expect(CONFIRMATION_SOURCE_COLUMN_LABELS.L0.length).toBe(28)
  })

  it('resolve 输出的每列 label 都能在 manifest 找到出处（宽判：允许平台改写用词）', () => {
    // 真正的 resolve ⊆ manifest：按**字段 key** 判子集（label 经 override 后会改写，
    // 如 F0-4→L0-4、函证方式→函证类型，故不能拿 label 判子集）。
    const allowed = new Set(CONFIRMATION_SOURCE_MANIFEST.L0)
    const leaked = L0_KEYS.filter((k) => !allowed.has(k))
    expect(leaked, `resolve 输出了 manifest 未登记的列 key：${leaked.join(',')}`).toEqual([])
  })

  it('源模板列名清单含关键中文列（防 label 常量整表被换掉）', () => {
    for (const label of ['账户/交易', '金额', '询证函索引号', '审计结论']) {
      expect(CONFIRMATION_SOURCE_COLUMN_LABELS.L0, `源列名清单缺「${label}」`).toContain(label)
    }
  })

  it('confirmationColumnSpec.spec.ts 的 NO_EXCLUSION_CYCLES 不含 L0', () => {
    const src = fs.readFileSync(
      path.join(FE_ROOT, '__tests__/confirmationColumnSpec.spec.ts'),
      'utf-8',
    )
    const noc = stripTsComments(src)
    const m = noc.match(/NO_EXCLUSION_CYCLES\s*:\s*ConfirmCycle\[\]\s*=\s*\[([^\]]*)\]/)
    expect(m, '未找到 NO_EXCLUSION_CYCLES 声明（守卫会空转）').not.toBeNull()
    const listed = Array.from(m![1].matchAll(/'([^']+)'/g)).map((x) => x[1])
    expect(listed, `L0 已声明剔除却仍在白名单：${listed}`).not.toContain('L0')
    // 白名单只许变短
    expect(listed.length).toBeLessThanOrEqual(3)
  })
})

// ─── Property 36: 共享件改动为加法式最小 hunk ───────────────────────────────

describe('Property 36: 三个 record 中 L0 之外的键未被改动', () => {
  it('其余六枢纽 resolve 输出的 key 序列不含 L0 专属注册 key 的痕迹', () => {
    for (const cycle of OTHER_CYCLES) {
      const cols = resolveConfirmationColumns(cycle)
      const rc = cols.find((c) => c.key === 'row_conclusion')
      if (rc) {
        expect(rc.source, `${cycle} 的 row_conclusion 溯源被改成 L0`).not.toContain('L0-1')
      }
    }
  })

  it('CYCLE_EXCLUDED_COLUMNS 只有 E0 / G0 / H0 / K0 / L0 非空', () => {
    // 🔴 改写记录：K0 于 2026-08-07 收口（k0 spec R2.6，同款剔三列），故加入清单。
    //    D0 / F0 源模板确有那三列 ⇒ 必须保持空数组（零回归支点）。
    const nonEmpty = Object.entries(CYCLE_EXCLUDED_COLUMNS)
      .filter(([, v]) => (v ?? []).length > 0)
      .map(([k]) => k)
      .sort()
    expect(nonEmpty).toEqual(['E0', 'G0', 'H0', 'K0', 'L0'])
  })

  it('CYCLE_VARIANT_COLUMNS.L0 恰为两个 variant key（加法式最小 hunk）', () => {
    expect(CYCLE_VARIANT_COLUMNS.L0).toEqual(['send_channel', 'l0_row_conclusion'])
  })

  it('label 覆盖走浅拷贝，不污染 BASE 常量（跨枢纽调用顺序无关）', () => {
    // 先解析 L0（带 override），再解析 D0，D0 必须仍是 BASE 用词
    resolveConfirmationColumns('L0')
    const d0 = resolveConfirmationColumns('D0')
    expect(d0.find((c) => c.key === 'account_type')!.label).toBe('科目')
    expect(d0.find((c) => c.key === 'amount')!.label).toBe('函证金额')
    // BASE 常量本身也没被写坏
    expect(BASE_CONFIRMATION_COLUMNS.find((c) => c.key === 'amount')!.label).toBe('函证金额')
  })

  it('源码级：override 应用处用了展开拷贝而非就地赋值', () => {
    expect(SPEC_NO_COMMENT, 'override 就地写 col.label 会污染常量').not.toMatch(
      /\bcol\.label\s*=/,
    )
    expect(SPEC_NO_COMMENT).toMatch(/\{\s*\.\.\.c\s*,\s*label:/)
  })
})

// ─── 注册表键唯一性（本轮变异检验挖出的真实缺陷：l0_row_conclusion 曾定义两次） ──

describe('VARIANT_COLUMN_DEFS 顶层键唯一（重复键会被 JS 静默取后者）', () => {
  /**
   * 🔴 2026-08-05 实测缺陷：`l0_row_conclusion` 在同一对象字面量里定义了两次
   * （内容相同），JS 静默取后者 ⇒ `get_diagnostics` / vitest / Vite transform
   * 四层全绿，只有变异脚本报「锚点命中 2 处」才暴露。
   *
   * 本组按**源码**扫顶层键（运行时对象已被去重，看不出问题）。
   */
  const SPEC_PATH = path.join(
    REPO_ROOT,
    'audit-platform/frontend/src/components/workpaper/confirmation/confirmationColumnSpec.ts',
  )

  /** 取 `VARIANT_COLUMN_DEFS` 对象体内的顶层键（按花括号深度=1 判定） */
  function variantTopLevelKeys(): string[] {
    const src = stripTsComments(fs.readFileSync(SPEC_PATH, 'utf-8'))
    const m = /VARIANT_COLUMN_DEFS[^=]*=\s*\{/.exec(src)
    if (!m) throw new Error('未找到 VARIANT_COLUMN_DEFS 声明（守卫会空转）')
    const open = src.indexOf('{', m.index)
    let depth = 0
    let end = -1
    for (let i = open; i < src.length; i += 1) {
      const ch = src[i]
      if (ch === '{') depth += 1
      else if (ch === '}') {
        depth -= 1
        if (depth === 0) {
          end = i
          break
        }
      }
    }
    if (end < 0) throw new Error('VARIANT_COLUMN_DEFS 花括号未配对')
    const body = src.slice(open + 1, end)

    // 逐字符走一遍，只收 depth===0 处的 `key:`
    const keys: string[] = []
    let d = 0
    let lineStart = 0
    for (let i = 0; i < body.length; i += 1) {
      const ch = body[i]
      if (ch === '{' || ch === '[' || ch === '(') d += 1
      else if (ch === '}' || ch === ']' || ch === ')') d -= 1
      else if (ch === '\n') {
        if (d === 0) {
          const line = body.slice(lineStart, i)
          const km = /^\s*([A-Za-z_$][\w$]*)\s*:/.exec(line)
          if (km) keys.push(km[1])
        }
        lineStart = i + 1
      }
    }
    // 末行
    const tail = body.slice(lineStart)
    const tm = /^\s*([A-Za-z_$][\w$]*)\s*:/.exec(tail)
    if (d === 0 && tm) keys.push(tm[1])
    return keys
  }

  it('抽取结果非空（否则本组断言空转）', () => {
    const keys = variantTopLevelKeys()
    expect(keys.length).toBeGreaterThan(10)
    // 锚：几个已知键必须在册
    // 🔴 锚点原含 `send_memo`，K0 spec 收口后该 def 已整条删除 → 换成稳定键
    //    （伪列不得作为解析器锚点，否则「撤掉伪列」这个正确动作会打红本守卫）。
    for (const k of ['k0_row_conclusion', 'l0_row_conclusion', 'send_channel', 'h0_row_conclusion']) {
      expect(keys, `顶层键抽取遗漏 ${k}`).toContain(k)
    }
  })

  it('无重复键', () => {
    const keys = variantTopLevelKeys()
    const seen = new Map<string, number>()
    for (const k of keys) seen.set(k, (seen.get(k) ?? 0) + 1)
    const dups = [...seen.entries()].filter(([, n]) => n > 1).map(([k, n]) => `${k}×${n}`)
    expect(dups, `VARIANT_COLUMN_DEFS 存在重复键（JS 会静默取后者）：${dups.join(', ')}`).toEqual([])
  })

  it('运行时键数与源码顶层键数一致（重复键会让两者不等）', () => {
    const srcKeys = variantTopLevelKeys()
    const runtimeKeys = Object.keys(VARIANT_COLUMN_DEFS)
    expect(srcKeys.length, '源码键数 ≠ 运行时键数 ⇒ 有重复键被静默去重').toBe(runtimeKeys.length)
  })
})
