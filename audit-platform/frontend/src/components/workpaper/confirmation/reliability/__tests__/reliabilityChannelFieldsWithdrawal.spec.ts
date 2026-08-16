/**
 * reliabilityChannelFieldsWithdrawal.spec.ts — 12 个「按渠道核对」死字段已撤回的守卫
 *
 * spec: k0-confirmation-source-alignment，Task 14 / Property 18 / R9.1 / R9.2 / R9.4
 *
 * ─── 🔴 为什么是「撤回」而不是「接线」（tasks.md 的前提已被源模板实证推翻） ──────────
 *
 * requirements R9.1 与 tasks.md Task 14 都写「12 个渠道字段应在 UI 上提供录入位置」，
 * 落手前逐个源模板核实后**该前提不成立**：
 *
 * 1. **六个可见回函可靠性 sheet 的列集完全同构，且都只有 14 列**
 *    （openpyxl 直读 `backend/wp_templates/**`：`邮件传真回函可靠性验证D0-7` /
 *      `F0-7` / `G0-7` / `H0-6` / `K0-7` / `L0-6`）——
 *    r5 基本段 6 列 + `G5:M5` 父表头下 7 个叶子列 + `N5 回函可靠性结论`。
 *    这 14 列**没有一列**是 `是否分别由经办人和复核人签名` / `邮戳显示发出城市` /
 *    `电子签名信息是否一致` / `回函的 IP 地址` 这类按渠道细分项。
 *
 * 2. **这 12 个字段的出处是 E0 的 `邮件传真回函核对记录F1-12`，而它是 `hidden` sheet**
 *    （字段注释逐条写着「源 F1-12 X 列」）。用户 2026-08-02 已就 E0 三张隐藏 sheet
 *    明确裁决 **A-否：不实现**（`e0-confirmation-completion` 因此删掉了整个 Wave 6）。
 *    ⇒ 给它们补 UI 等于把已被裁决不做的隐藏表能力从侧门实现回来。
 *
 * 3. **零存量数据**：全库 498 份底稿的 `parsed_data` 里，12 个字段名命中数均为 **0**
 *    （postgres 只读实测）⇒ 删除类型声明**不丢任何已录入值**。
 *
 * ⇒ 处置 = 从 `ReliabilityRow` **删除**这 12 个字段声明（真正消除「类型加了、UI 从未
 *   渲染」的死字段形态，R9.1 的两个出口「提供录入位置 **或** 明确撤回」取后者），
 *   并由本守卫把该裁决钉死，防下个会话又照 tasks.md 旧描述补一次。
 *
 * 🔴 本守卫**不读 xlsx**（前端不解析 xlsx）—— 源侧 14 列事实经后端事实守卫
 *   `test_k0_source_template_facts.py::RELIABILITY_LEAF_COLUMNS` 交叉取得，
 *   源模板一旦真的加了渠道列，后端先红。
 */
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

// ─── REPO_ROOT：哨兵**文件**向上查找（禁写死回退级数） ───────────────────────
const SENTINELS = [
  join('backend', 'tests', 'test_k0_source_template_facts.py'),
  join('backend', 'app', 'data', 'wp_code_overrides.json'),
] as const

function findRepoRoot(start: string): string {
  let dir = resolve(start)
  for (let i = 0; i < 20; i += 1) {
    if (SENTINELS.every((s) => existsSync(join(dir, s)))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未能从 ${start} 向上找到含哨兵文件的仓库根：${SENTINELS.join(' + ')}`)
}

const REPO_ROOT = findRepoRoot(__dirname)

function readRepo(...rel: string[]): string {
  const p = join(REPO_ROOT, ...rel)
  if (!existsSync(p)) throw new Error(`文件不存在：${rel.join('/')}`)
  return readFileSync(p, 'utf-8')
}

const FE = ['audit-platform', 'frontend', 'src', 'components', 'workpaper', 'confirmation'] as const

const TYPES_SRC = readRepo(...FE, 'reliability', 'reliabilityTypes.ts')
const GRID_SRC = readRepo(...FE, 'reliability', 'ReliabilityGrid.vue')
const BACKEND_K0_FACTS = readRepo('backend', 'tests', 'test_k0_source_template_facts.py')

/** 去注释（块 + 行 + HTML）—— 撤回说明里逐条写着被撤字段名，不剥必假红 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

/**
 * 取「以 `:label="RELIABILITY_PARENT_HEADER"` 开头的 `<el-table-column>`」整块。
 *
 * 🔴 用**标签配对**而非固定字符窗口 —— memory 已记「固定字符窗口截块」多次越界到邻居
 *   （`slice(i, i+N)` 会把紧随其后的无关列一起吞进来，使「不该在块内」的断言假绿）。
 *   自闭合 `<el-table-column ... />` 不计入深度。
 */
function parentBlockOf(src: string): string | null {
  const anchor = src.indexOf(':label="RELIABILITY_PARENT_HEADER"')
  if (anchor < 0) return null
  const start = src.lastIndexOf('<el-table-column', anchor)
  if (start < 0) return null

  const OPEN = '<el-table-column'
  const CLOSE = '</el-table-column>'
  let depth = 0
  let i = start
  while (i < src.length) {
    const nextOpen = src.indexOf(OPEN, i + 1)
    const nextClose = src.indexOf(CLOSE, i + 1)
    if (nextClose < 0) return null
    if (nextOpen >= 0 && nextOpen < nextClose) {
      const tagEnd = src.indexOf('>', nextOpen)
      if (tagEnd < 0) return null
      const selfClosing = src[tagEnd - 1] === '/'
      if (!selfClosing) depth += 1
      i = tagEnd
      continue
    }
    if (depth === 0) return src.slice(start, nextClose + CLOSE.length)
    depth -= 1
    i = nextClose
  }
  return null
}

function parentBlock(): string | null {
  return parentBlockOf(GRID_SRC)
}

/**
 * 被撤回的 12 个字段（e0-confirmation-completion R7 曾按 E0 隐藏 sheet `F1-12` 加进类型）。
 * 🔴 本清单**只许变短不许变长** —— 变长意味着又有人往共享类型里塞隐藏表字段。
 */
const WITHDRAWN_CHANNEL_FIELDS = Object.freeze([
  // 通用 2 项
  'signed_by_both',
  'signer_in_public_list',
  // 邮寄 3 项
  'envelope_addr_match',
  'postmark_city_match',
  'reply_info_complete',
  // 跟函 3 项
  'followup_flow_known',
  'followup_identity_verified',
  'followup_normal_process',
  // 电子平台 4 项
  'esign_match',
  'ip_match',
  'platform_op_time',
  'platform_feedback',
] as const)

/** 源模板真有的 14 列所对应的字段（撤回后必须一个不少地留着） */
const SOURCE_BACKED_FIELDS = Object.freeze([
  'seq',
  'confirm_index',
  'entity_name',
  'reply_method',
  'direct_received',
  'original_returned',
  'identity_verified',
  'fax_info_verify',
  'send_email',
  'reply_email',
  'email_verified',
  'phone_called',
  'reliability_consideration',
  'conclusion_status',
] as const)

// ════════════════════════════════════════════════════════════════════════════
describe('Property 18 — 12 个按渠道核对字段已从共享类型撤回（死字段清零）', () => {
  it('清单非空且恰 12 项（防清单被清空导致断言空转）', () => {
    expect(WITHDRAWN_CHANNEL_FIELDS.length).toBe(12)
    expect(new Set(WITHDRAWN_CHANNEL_FIELDS).size).toBe(12)
  })

  it.each(WITHDRAWN_CHANNEL_FIELDS)('`%s` 不再声明于 ReliabilityRow', (field) => {
    const code = stripComments(TYPES_SRC)
    expect(
      new RegExp(`\\b${field}\\s*\\??\\s*:`).test(code),
      `${field} 仍作为字段声明存在 —— 它源自 E0 隐藏 sheet F1-12（用户裁决 A-否 不实现），` +
        `六个可见回函可靠性 sheet 均无此列，且全库零存量数据`,
    ).toBe(false)
  })

  it.each(WITHDRAWN_CHANNEL_FIELDS)('`%s` 也不在 ReliabilityGrid 里被渲染', (field) => {
    const code = stripComments(GRID_SRC)
    expect(code.includes(field), `${field} 出现在网格里 = 又把隐藏表能力接了回来`).toBe(false)
  })

  it('撤回理由已在类型文件里留证（含隐藏 sheet 与裁决出处）', () => {
    // 🔴 只断言注释里留了依据，不断言具体措辞（改文案不是回归）
    expect(TYPES_SRC).toContain('F1-12')
    expect(TYPES_SRC).toMatch(/hidden|隐藏/)
    expect(TYPES_SRC).toMatch(/撤回|不实现/)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('撤回不得伤及源模板真有的 14 列', () => {
  it.each(SOURCE_BACKED_FIELDS)('`%s` 仍声明于 ReliabilityRow', (field) => {
    const code = stripComments(TYPES_SRC)
    expect(new RegExp(`\\b${field}\\s*\\??\\s*:`).test(code), `${field} 被误删`).toBe(true)
  })

  it('14 列全部仍在网格里有渲染出口（prop= 或 field 绑定）', () => {
    const code = stripComments(GRID_SRC)
    for (const field of SOURCE_BACKED_FIELDS) {
      expect(code.includes(field), `${field} 在网格里没有渲染出口`).toBe(true)
    }
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('R9.2 — `G:M` 七列在源模板父表头「期末未收回原件函证可靠性验证」下分组', () => {
  /** 源 `G5:M5` 父表头下的 7 个叶子列（顺序 = 源模板 G→M） */
  const GROUP_LEAF_FIELDS = Object.freeze([
    'identity_verified',      // G 被函证者身份确认（注1）
    'fax_info_verify',        // H 发函及回函传真信息及验证
    'send_email',             // I 发函邮箱
    'reply_email',            // J 回函邮箱
    'email_verified',         // K 邮箱可靠性验证（注2）
    'phone_called',           // L 是否致电被函证者确认
    'reliability_consideration', // M 对函证信息可靠性的考虑（注3）
  ] as const)

  /** 父表头字面的**单一真源**（组件里以 `:label="RELIABILITY_PARENT_HEADER"` 绑定） */
  const PARENT_HEADER_CONST = 'RELIABILITY_PARENT_HEADER'
  const PARENT_HEADER_TEXT = '期末未收回原件函证可靠性验证'

  it('父表头字面与源模板逐字一致（跨前后端交叉锁死）', () => {
    // 源侧真源在后端事实守卫里；平台侧字面在 reliabilityNotes 常量里
    expect(BACKEND_K0_FACTS).toContain(PARENT_HEADER_TEXT)
    const notes = readRepo(...FE, 'reliability', 'reliabilityNotes.ts')
    expect(notes).toContain(PARENT_HEADER_TEXT)
  })

  /**
   * 🔴 **模板绑定的常量必须真的被定义并 import** —— 这条是本轮落手时自己踩出来的：
   * 先写了 `:label="RELIABILITY_PARENT_HEADER"` 却没定义该常量，
   * **Vite transform 返回 200 / vitest 全绿 / `get_diagnostics` 零诊断**，
   * 只有浏览器里表头会渲染成空白（`<script setup>` 未声明标识符不阻断编译）。
   * 故断言「绑定 + 定义 + import」三者齐备，缺一即红。
   */
  it('父表头常量已定义、已 import、且在模板中被绑定（防绑定未定义标识符）', () => {
    const notes = readRepo(...FE, 'reliability', 'reliabilityNotes.ts')
    expect(
      new RegExp(`export\\s+const\\s+${PARENT_HEADER_CONST}\\b`).test(notes),
      `${PARENT_HEADER_CONST} 未在 reliabilityNotes.ts 里 export`,
    ).toBe(true)

    const importLine = GRID_SRC.match(/import\s*\{[^}]*\}\s*from\s*'\.\/reliabilityNotes'/)
    expect(importLine, '网格未从 reliabilityNotes 引入常量').toBeTruthy()
    expect(
      importLine![0].includes(PARENT_HEADER_CONST),
      `${PARENT_HEADER_CONST} 未被 import ⇒ 模板绑定会静默取到 undefined（表头空白）`,
    ).toBe(true)

    expect(GRID_SRC).toContain(`:label="${PARENT_HEADER_CONST}"`)
  })

  it('父表头是一个真实的嵌套 el-table-column（不是只写了个文字）', () => {
    const block = parentBlock()
    expect(block, '未找到带闭合标记的父列区块（父表头必须真的包住 7 个子列）').toBeTruthy()
    // 子列必须都在父列区块内部
    for (const field of GROUP_LEAF_FIELDS) {
      expect(block!.includes(field), `${field} 不在父表头区块内`).toBe(true)
    }
  })

  it('基本段 6 列与结论列**不得**被卷进父表头（父列只管 G:M）', () => {
    const block = parentBlock()!
    for (const outside of ['confirm_index', 'entity_name', 'reply_method', 'original_returned', 'direct_received', 'conclusion_status']) {
      expect(block.includes(outside), `${outside} 属基本段/结论段，不应在父表头下`).toBe(false)
    }
  })

  it('反向自检：把父列绑定改掉即无法命中（证明断言不是空转）', () => {
    const mutated = GRID_SRC.replace(`:label="${PARENT_HEADER_CONST}"`, ':label="XX"')
    expect(mutated.includes(`:label="${PARENT_HEADER_CONST}"`), '变异未生效').toBe(false)
    // 用同一份取块逻辑作用于变异源码 → 必须取不到
    expect(parentBlockOf(mutated), '变异后仍能取到父列区块 = 正则写得太宽').toBeNull()
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('R9.5 — `RELIABILITY_COLUMN_CONFIG` 零消费方登记（平台级，本 spec 不清理）', () => {
  it('该常量仍只被自身文件声明、无生产消费方（现状登记，变了要来改这条）', () => {
    const notes = readRepo(...FE, 'reliability', 'reliabilityNotes.ts')
    expect(notes).toContain('RELIABILITY_COLUMN_CONFIG')
    // 网格自行渲染列，不消费该常量
    expect(stripComments(GRID_SRC)).not.toContain('RELIABILITY_COLUMN_CONFIG')
  })
})
