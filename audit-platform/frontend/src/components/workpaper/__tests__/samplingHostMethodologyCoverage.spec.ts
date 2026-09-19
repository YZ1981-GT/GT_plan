/**
 * 抽凭宿主方法学收口守卫（sampling-compliance-closure Wave 3 Task 22）
 *
 * 背景（2026-08-04 实证）：78 个底稿 Tab 挂载 `GtVoucherSamplingEngine`，其中相当一部分
 * **丢弃 `filled` 载荷里的 `methodology`**，最极端者只做 `addRow(v.summary || v.voucherNo)`
 * —— 凭证号 / 日期 / 金额 / 科目全丢。留痕在 `workpaper_extraction_log` 里没丢，但
 * **底稿正文（打印件 / 归档件）不体现抽样方法学与样本关键字段**，而复核与归档看的是底稿。
 *
 * 本守卫是「覆盖率单调收敛」型：宿主未满足的要求必须在 allowlist 里被逐条豁免且写明理由，
 * 豁免总数只许变短不许变长。它的产出即 Task 19/20/21 的**权威工作清单**。
 *
 * Validates: Requirements 6.3, 6.4, 6.5, 6.6, 6.7, 6.8
 * Properties: Property 15, Property 16
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync, existsSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// ─── REPO_ROOT：哨兵文件向上查找（禁写死回退级数） ──────────────────────────

function findRepoRoot(): string {
  // 哨兵必须是**具体文件**：目录名在多层同时存在时会提前停下（平台已有踩坑 ——
  // `audit-platform/backend/app/routers` 是历史遗留空目录，用目录当哨兵会停在那一层）
  const SENTINEL = join('backend', 'app', 'routers', 'voucher_sampling.py')
  let dir = dirname(fileURLToPath(import.meta.url))
  for (let i = 0; i < 12; i++) {
    try {
      readFileSync(join(dir, SENTINEL))
      return dir
    } catch {
      const parent = resolve(dir, '..')
      if (parent === dir) break
      dir = parent
    }
  }
  throw new Error('未找到仓库根（哨兵 backend/app/routers/voucher_sampling.py）')
}

const REPO_ROOT = findRepoRoot()
const WORKPAPER_DIR = join(
  REPO_ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper',
)
const ENGINE_FILE = 'GtVoucherSamplingEngine.vue'

// ─── 注释剥离（读源码前必做） ────────────────────────────────────────────────

/**
 * 剥 JS 注释，**带字符串状态的扫描器**，不用正则。
 *
 * 🔴 为什么不能用「非贪婪匹配块注释」的正则：本守卫第一版就是这么写的，结果模板里
 * `accept="image/*,.pdf"` 的斜杠星号被当成块注释起点，一直吞到几千字符之后的块注释
 * 结束符，把 `<GtVoucherSamplingEngine` 标签一起吃掉 → **G6TabVoucherCheck 与
 * K8TabSellingCheck 两个真实宿主静默逃出扫描面**（守卫少扫 2 个文件还是绿的）。
 * 同理 URL 里的双斜杠也不能靠「前一字符不是冒号」这种近似判据绕。
 */
function stripJsComments(src: string): string {
  let out = ''
  let quote: string | null = null
  let i = 0
  while (i < src.length) {
    const c = src[i]
    if (quote) {
      if (c === '\\') { out += '  '; i += 2; continue }
      out += c
      if (c === quote) quote = null
      i++
      continue
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; out += c; i++; continue }
    if (c === '/' && src[i + 1] === '*') {
      const end = src.indexOf('*/', i + 2)
      i = end < 0 ? src.length : end + 2
      out += ' '
      continue
    }
    if (c === '/' && src[i + 1] === '/') {
      const end = src.indexOf('\n', i)
      i = end < 0 ? src.length : end
      out += ' '
      continue
    }
    out += c
    i++
  }
  return out
}

/**
 * SFC 降噪：丢 `<style>`、剥 HTML 注释、只在 `<script>` 区内剥 JS 注释。
 *
 * 分区处理的理由：模板属性值里 `/*`（MIME 通配）与 `//`（URL）合法且常见，
 * 在模板区套 JS 注释规则必误伤；而 `<style>` 区与判据无关，整段丢掉最省心
 * （也顺带消掉 `.methodology-context` 这类样式名的干扰）。
 *
 * 不剥注释的后果：本守卫与被扫宿主里「为什么不能这么写 methodology」这类说明
 * 注释会被数成真实消费点 → 守卫恒绿（平台已多次踩中的假绿模式）。
 */
function stripComments(src: string): string {
  let s = src.replace(/<style[\s\S]*?<\/style>/gi, ' ')
  s = s.replace(/<!--[\s\S]*?-->/g, ' ')
  const hasScriptBlock = /<script[^>]*>/i.test(s)
  if (!hasScriptBlock) return stripJsComments(s)
  return s.replace(
    /(<script[^>]*>)([\s\S]*?)(<\/script>)/gi,
    (_m, open: string, body: string, close: string) =>
      `${open}${stripJsComments(body)}${close}`,
  )
}

// ─── 宿主收集 ────────────────────────────────────────────────────────────────

interface Host {
  /** 文件名（allowlist 的键） */
  file: string
  /** 仓库相对路径（报错信息里给出，便于直接打开） */
  rel: string
  /** 绝对路径（解析相对 import 用） */
  abs: string
  /** 已剥注释的源码 */
  src: string
}

function walkVueFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const st = statSync(p)
    if (st.isDirectory()) {
      if (name === '__tests__' || name === 'node_modules') continue
      walkVueFiles(p, out)
    } else if (name.endsWith('.vue')) {
      out.push(p)
    }
  }
  return out
}

function collectHosts(): Host[] {
  const hosts: Host[] = []
  for (const abs of walkVueFiles(WORKPAPER_DIR)) {
    const file = abs.split(/[\\/]/).pop() as string
    if (file === ENGINE_FILE) continue
    const src = stripComments(readFileSync(abs, 'utf-8'))
    // 判据 = 模板里真实挂载了引擎（仅在注释/文档里提到引擎名的不算宿主）
    if (!src.includes('<GtVoucherSamplingEngine')) continue
    hosts.push({
      file,
      rel: abs.slice(REPO_ROOT.length + 1).replace(/\\/g, '/'),
      abs,
      src,
    })
  }
  return hosts.sort((a, b) => a.file.localeCompare(b.file))
}

const HOSTS = collectHosts()

// ─── 要求判定（纯函数，便于反向自检拿替身源码复现） ──────────────────────────

type ReqKey = 'methodology' | 'persist' | 'bar' | 'fields'

const REQ_LABELS: Readonly<Record<ReqKey, string>> = Object.freeze({
  methodology: 'R6.3 消费 filled 载荷的 methodology',
  persist: 'R6.3 持久化到 samplingMethodologyItemKey',
  bar: 'R6.4 渲染 WpSamplingMethodologyBar',
  fields: 'R6.5 样本映射覆盖最小字段集',
})

/**
 * 薄壳委托：宿主用 `v-bind="$props"` 把全部 prop 转给下层组件承载抽凭区。
 * 按 R6.6 这类宿主视为已满足（真实实现在被委托组件里）。
 */
function isThinShellDelegate(src: string): boolean {
  return src.includes('v-bind="$props"')
}

/**
 * 是否消费 `methodology`。
 *
 * 负向 lookahead `(?!-)` 排除 CSS 类名 `methodology-context`（多个宿主用它做
 * 方法论提示块的琥珀色边线样式）—— 那不是对载荷字段的消费。
 */
function consumesMethodology(src: string): boolean {
  return /\bmethodology\b(?!-)/.test(src)
}

/**
 * 是否把方法学落到**固定 item key**。
 *
 * 认两种形态：直接用 `samplingMethodologyItemKey` 构键，或走平台接线件
 * `useSamplingMethodologyPersist`（它内部就是那个键，且额外收口了只读门控与
 * 「无实质内容不写空壳」，是推荐形态）。不认「自己拼一个键名字符串」——
 * 那会让同一底稿在不同 Tab 下落到不同键，归档时读不出来。
 */
function persistsMethodology(src: string): boolean {
  return (
    src.includes('samplingMethodologyItemKey') ||
    src.includes('useSamplingMethodologyPersist')
  )
}

function rendersMethodologyBar(src: string): boolean {
  return src.includes('WpSamplingMethodologyBar')
}

/** 最小字段集的四类语义（R6.5）；金额借贷任一即可 */
const FIELD_CATEGORIES: ReadonlyArray<readonly [string, RegExp]> = [
  ['凭证号', /\b(?:voucherNo|voucher_no)\b/],
  ['凭证日期', /\b(?:voucherDate|voucher_date)\b/],
  ['金额（借或贷）', /\b(?:debitAmount|debit_amount|creditAmount|credit_amount)\b/],
  ['科目编码', /\b(?:accountCode|account_code)\b/],
]

const FIELD_RE: Readonly<Record<string, RegExp>> = Object.freeze(
  Object.fromEntries(FIELD_CATEGORIES.map(([label, re]) => [label, re])),
)

/**
 * ─── 判据分层（R6.5，2026-08-04 裁决）────────────────────────────────────────
 *
 * 一刀切「四要素」对部分行模型语义不成立，且源模板本身就没有那一列 —— 硬补等于
 * **自造底稿列**（违反「增强打磨禁止自造内容」铁律）。故按行模型语义分两层：
 *
 * - **层 1「样本可回溯」，全体宿主强制**：样本必须至少带凭证号进底稿。
 *   这一条是**收紧**：它直接拦住「只 `addRow(v.summary || v.voucherNo)` 之外什么都不留」
 *   与「弹一条 success 就把样本丢掉」（实测 `K5TabLitigationCheck` 正是后者）。
 * - **层 2「凭证明细四要素」，仅凭证明细型宿主强制**：日期 + 金额 + 科目来源。
 *
 * **科目来源**允许由已渲染的方法学 bar 满足 —— 41/41 宿主都把本科目码作为**常量**
 * 传给引擎（`account-code="1601"` / `:account-code="G9_ACCOUNT_CODE"`），它是**抽样
 * 参数**不是逐样本属性，已由 `methodology.accountCodes` 承载并经 bar 渲染到底稿正文
 * （R6.4）。逐行再存一遍是整批恒等的冗余常量，且会让守卫从此失去区分力
 * （真缺日期/金额的宿主与只缺冗余字段的宿主变成同一档）。
 */
type RowModelKind =
  | 'voucher-detail'
  | 'no-voucher-date'
  | 'compliance-checklist'
  | 'valuation-test'
  | 'account-detail'

/** 各 kind 在层 1 之上追加强制的字段类别 */
const KIND_TIER2: Readonly<Record<RowModelKind, readonly string[]>> = Object.freeze({
  'voucher-detail': ['凭证日期', '金额（借或贷）', '科目编码'],
  // 源模板「记账凭证」段下确实没有日期列（只有凭证编号）→ 不强制日期
  'no-voucher-date': ['金额（借或贷）', '科目编码'],
  'compliance-checklist': [],
  'valuation-test': [],
  'account-detail': [],
})

/**
 * 非「凭证明细型」宿主的**声明式**登记（默认 = `voucher-detail`）。
 *
 * 每条须写明**源模板依据**（不是"实现起来麻烦"）。**条目数只许变少**
 * （`NON_VOUCHER_DETAIL_BASELINE`）—— 防这张表被当成逃逸阀。
 */
const HOST_ROW_MODEL_KIND: Readonly<Record<string, { kind: RowModelKind; reason: string }>> =
  Object.freeze({
    'H10TabCheck.vue': {
      kind: 'compliance-checklist',
      reason:
        '行模型 H10CheckRow 是合规检查项行（CHECK_FIELDS 取值 non_compliant），' +
        '源模板只有 资产名/凭证索引/检查项 列，金额与科目码在该表里没有列位',
    },
    'F2ValuationTestSheet.vue': {
      kind: 'valuation-test',
      reason:
        '源模板 F2-38/39/40 行是「月份或日期 × 数量/单价/金额」的计价重算行' +
        '（B12 本期生产 / E12 本期销售 / H12 期末结存 / N12 差异），不是凭证明细行',
    },
    'D5TabDetail.vue': {
      kind: 'account-detail',
      reason:
        '行模型是「明细项目 × 期初/期末/本期增减」的科目明细表行，' +
        '源模板无记账凭证日期列；抽凭样本只作为明细项目来源带入',
    },
    'F2TabPurchaseInboundCheck.vue': {
      kind: 'no-voucher-date',
      reason:
        '源模板 F2-33 的「记账凭证」段（C15）下辖 C16 凭证编号/D16 业务内容/' +
        'H16 借方金额/I16 对方科目，**无日期列**（日期只在入库单/发票的「日期/编号」里）',
    },
    'F2TabMaterialUsageCheck.vue': {
      kind: 'no-voucher-date',
      reason:
        '源模板 F2-34 的「记账凭证」段（A14）下辖 A15 凭证编号/B15 业务内容/' +
        'F15 贷方金额/G15 对方科目，**无日期列**（日期只在出库单的「日期/编号」里）',
    },
    'H4TabDisposalCheck.vue': {
      kind: 'no-voucher-date',
      reason:
        '源模板 H4-5 减少检查表只有 D14 入账凭证号，**无记账凭证日期列**' +
        '（对比同册 H4-4 增加检查表 D15 明确有「日期」→ 差异是源模板有意为之）',
    },
    'H5TabAdditionCheck.vue': {
      kind: 'no-voucher-date',
      reason:
        '源模板 H5-7 只有 G12 入账凭证号，E12「增加日期」是业务事件日期' +
        '（与记账凭证日期不同维度），记账凭证段下无日期列',
    },
    'H5TabDisposalCheck.vue': {
      kind: 'no-voucher-date',
      reason:
        '源模板 H5-8 只有 G12 凭证号，F12「减少日期」是业务事件日期' +
        '（与记账凭证日期不同维度），记账凭证段下无日期列',
    },
  })

const NON_VOUCHER_DETAIL_BASELINE = 8

function rowModelKind(file: string): RowModelKind {
  return HOST_ROW_MODEL_KIND[file]?.kind ?? 'voucher-detail'
}

/** 走共享映射件即天然覆盖最小字段集（其字段集由 samplingFillTarget.spec.ts 锁死） */
function usesSharedRowMapper(src: string): boolean {
  return /\bmapSampledRows\b|\bmapSampledToGenericRow\b/.test(src)
}

/** 旧口径（一刀切四要素）——仅供诊断落盘与反向自检对照，不参与判定 */
function missingFieldCategories(sources: readonly string[]): string[] {
  const joined = sources.join('\n')
  return FIELD_CATEGORIES.filter(([, re]) => !re.test(joined)).map(([label]) => label)
}

/**
 * 分层判据下的字段集缺口。
 *
 * @param kind 行模型语义（声明式登记，默认凭证明细型）
 * @param sources 宿主源码 ∪ 一级委托目标源码
 * @param hostSrc 宿主自身源码（判「科目来源是否已由 bar 承载」用）
 */
function missingFieldsLayered(
  kind: RowModelKind,
  sources: readonly string[],
  hostSrc: string,
): string[] {
  const joined = sources.join('\n')
  const missing: string[] = []

  // 层 1：样本可回溯（全体强制）
  if (!FIELD_RE['凭证号'].test(joined)) missing.push('凭证号')

  for (const cat of KIND_TIER2[kind]) {
    if (cat === '科目编码') {
      // 科目来源：逐行 accountCode 或 该宿主已渲染方法学 bar（承载 accountCodes）
      if (!FIELD_RE['科目编码'].test(joined) && !rendersMethodologyBar(hostSrc)) {
        missing.push('科目来源（逐行 accountCode 或已渲染方法学 bar）')
      }
      continue
    }
    if (!FIELD_RE[cat].test(joined)) missing.push(cat)
  }
  return missing
}

// ─── 一级委托解析（映射逻辑常落在 per-cycle composable 里） ──────────────────

/** 取 `@filled="xxx"` 的处理函数名；内联箭头函数返回 null（其体就在模板里） */
function filledHandlerName(src: string): string | null {
  const m = src.match(/@filled\s*=\s*"([A-Za-z_$][\w$]*)"/)
  return m ? m[1] : null
}

/**
 * 按花括号配对截取函数体（支持 `function X(...) {}` 与 `const X = (...) => {}`）。
 *
 * 🔴 必须**先用圆括号配对跳过整个参数列表**再找 `{`：抽凭宿主的处理函数普遍写成
 * `function onSampleFilled(payload: { samples: SampledVoucher[]; fillMode: FillMode })`，
 * 直接取「声明之后的第一个 `{`」会命中**参数的内联类型字面量** → 截出来的"函数体"
 * 是那段类型声明 → 委托解析恒为空 → 把「映射写在 composable 里」全判成「没映射」。
 * 这是本守卫字段集低报的主因（2026-08-04 实测）。
 */
function extractFunctionBody(src: string, name: string): string | null {
  const decl = new RegExp(
    `(?:function\\s+${name}\\s*\\(|(?:const|let|var)\\s+${name}\\s*=\\s*(?:async\\s*)?\\()`,
  )
  const m = decl.exec(src)
  if (!m) return null

  // m[0] 以参数列表的左括号结尾 → 从它开始做圆括号配对，找到参数列表的右括号
  let paren = 1
  let i = m.index + m[0].length
  for (; i < src.length && paren > 0; i++) {
    if (src[i] === '(') paren++
    else if (src[i] === ')') paren--
  }
  if (paren !== 0) return null

  const open = src.indexOf('{', i)
  if (open < 0) return null
  let depth = 0
  for (let k = open; k < src.length; k++) {
    if (src[k] === '{') depth++
    else if (src[k] === '}') {
      depth--
      if (depth === 0) return src.slice(open + 1, k)
    }
  }
  return null
}

/**
 * 字段集判定**不跟进**的模块：它们是最小字段集的**定义方**，不是某个宿主的映射实现。
 *
 * 🔴 不排除的后果（本守卫第二版实测）：宿主为类型断言写了
 * `import type { SamplingMethodologySnapshot } from '.../samplingFillTarget'`，
 * 而该符号出现在 `filled` 处理函数体里 → 一级委托把 `samplingFillTarget.ts` 拉进来当
 * 「字段来源」，于是**任何接过线的宿主都自动通过字段集判定** = 假绿。
 */
const FIELD_SCAN_EXCLUDED = [
  'composables/shared/samplingFillTarget.ts',
  'composables/shared/useSamplingMethodologyPersist.ts',
]

/**
 * 解析宿主 script 里的相对 import，返回 {本地符号 → 绝对文件路径}。
 * 只解析相对路径（`@/` 与三方包不跟进）；**类型 import 一律不计**
 * （类型不承载运行时字段读取）。
 */
/** `@/` 别名根（Vite 配置里 `@` → `audit-platform/frontend/src`） */
const ALIAS_ROOT = join(REPO_ROOT, 'audit-platform', 'frontend', 'src')

function relativeImportMap(host: Host): Record<string, string> {
  const out: Record<string, string> = {}
  // 相对路径与 `@/` 别名都要认：G6 的映射件在 `@/composables/useG6EclVoucherCheck`，
  // 只认相对路径会把它漏掉（本守卫第三处低报，2026-08-04 实测）。
  const re = /import\s+([\s\S]*?)\s+from\s+['"]((?:\.|@\/)[^'"]*)['"]/g
  let m: RegExpExecArray | null
  while ((m = re.exec(host.src))) {
    const clause = m[1]
    const spec = m[2]
    // `import type { X } from '...'` 整条跳过（类型不承载运行时字段读取）
    if (/^\s*type\b/.test(clause)) continue
    const isAlias = spec.startsWith('@/')
    const baseDir = isAlias ? ALIAS_ROOT : dirname(host.abs)
    const bare = isAlias ? spec.slice(2) : spec
    const candidates = [
      bare, `${bare}.ts`, `${bare}.vue`, join(bare, 'index.ts'),
    ].map((s) => resolve(baseDir, s))
    const target = candidates.find((p) => existsSync(p) && statSync(p).isFile())
    if (!target) continue
    const norm = target.replace(/\\/g, '/')
    if (FIELD_SCAN_EXCLUDED.some((s) => norm.endsWith(s))) continue
    for (const raw of clause.replace(/[{}]/g, ',').split(',')) {
      // 内联 `{ type X }` 形态也不计
      if (/^\s*type\s+/.test(raw)) continue
      const name = raw.trim().split(/\s+as\s+/).pop()?.trim()
      if (name && /^[A-Za-z_$][\w$]*$/.test(name)) out[name] = target
    }
  }
  // `defineAsyncComponent(() => import('./X.vue'))` 形态也纳入（宿主常这么挂子组件）
  const reAsync = /(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*defineAsyncComponent\(\s*\(\)\s*=>\s*import\(\s*['"](\.[^'"]*)['"]/g
  while ((m = reAsync.exec(host.src))) {
    const target = resolve(dirname(host.abs), m[2])
    if (existsSync(target) && statSync(target).isFile()) out[m[1]] = target
  }
  return out
}

/**
 * setup 层解构映射：`const { applySamplingResults, fillFromSampling } = useXVoucherCheck(...)`
 * → {applySamplingResults: <useXVoucherCheck 的绝对路径>, ...}
 *
 * 🔴 为什么必须解这一层（2026-08-04 实测的**低报**）：`filled` 处理函数体里出现的是
 * `applySamplingResults`（解构出来的成员名），而相对 import 的是 `useF3VoucherCheck`。
 * 只按 import 符号匹配 ⇒ 跟不进去 ⇒ 把「映射写在 composable 里」误判成「没映射」。
 * `useF3VoucherCheck.mapVoucherToEntries` 明明映射了 voucherDate / voucherNo /
 * debitAmount / creditAmount，却被判缺三类；F4/G1/G2/G5/G6 同族。
 */
function destructuredComposableMap(host: Host): Record<string, string> {
  const imports = relativeImportMap(host)
  const out: Record<string, string> = {}
  const re = /(?:const|let|var)\s*\{([\s\S]*?)\}\s*=\s*([A-Za-z_$][\w$]*)\s*\(/g
  let m: RegExpExecArray | null
  while ((m = re.exec(host.src))) {
    const target = imports[m[2]]
    if (!target) continue
    for (const raw of m[1].split(',')) {
      // 支持 `a`、`loading: aiLoading`、`b = 1` 三种形态，取**本地名**
      const local = raw.split(':').pop()?.split('=')[0]?.trim()
      if (local && /^[A-Za-z_$][\w$]*$/.test(local)) out[local] = target
    }
  }
  return out
}

/**
 * 对象式 composable：`const ic = useF2MaterialUsageCheck({...})` 后 `ic.fillFromSampling(...)`
 * → {ic: <useF2MaterialUsageCheck 的绝对路径>}
 *
 * 🔴 本守卫第四处低报（2026-08-04 实测）：F2 四个宿主、G6 都是这个形态，
 * 既不是直接 import 的符号也不是解构成员 → 一级委托跟不进去 → 明明
 * `useF2InspectionCheck.mapVoucherToRow` 映射了金额、`useG6EclVoucherCheck`
 * 映射了 `sample.voucherDate`，却被判成缺失。
 */
function objectFormComposableMap(host: Host): Record<string, string> {
  const imports = relativeImportMap(host)
  const out: Record<string, string> = {}
  const re = /(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*([A-Za-z_$][\w$]*)\s*\(/g
  let m: RegExpExecArray | null
  while ((m = re.exec(host.src))) {
    const target = imports[m[2]]
    if (target) out[m[1]] = target
  }
  return out
}

/**
 * 处理函数体里出现的、可解析到相对模块的符号 → 其源码（一级委托，不递归）。
 * 两条通道：直接 import 的符号；setup 层从 composable 解构出来的成员。
 */
function delegateSources(host: Host, body: string): string[] {
  const candidates = {
    ...relativeImportMap(host),
    ...destructuredComposableMap(host),
    ...objectFormComposableMap(host),
  }
  const paths = new Set<string>()
  for (const [name, path] of Object.entries(candidates)) {
    if (!new RegExp(`\\b${name}\\b`).test(body)) continue
    paths.add(path)
  }
  const srcs: string[] = []
  for (const path of paths) {
    const norm = path.replace(/\\/g, '/')
    if (FIELD_SCAN_EXCLUDED.some((s) => norm.endsWith(s))) continue
    try {
      srcs.push(stripComments(readFileSync(path, 'utf-8')))
    } catch {
      /* 解析不到的委托目标不计入，宁漏勿误杀 */
    }
  }
  return srcs
}

/**
 * 判定某宿主未满足哪些要求。
 *
 * 字段集判定的取值范围 = 宿主源码 ∪ 其 `filled` 处理函数委托到的一级相对 import
 * （D3 这类把映射交给 `useD3VoucherCheck.fillFromSampling` 的宿主必须跟进去看，
 * 否则会把「映射写在 composable 里」误判成「没映射」）。
 */
function unmetRequirements(
  host: Host,
  opts: { readDelegates?: boolean } = { readDelegates: true },
): ReqKey[] {
  if (isThinShellDelegate(host.src)) return []

  const unmet: ReqKey[] = []
  if (!consumesMethodology(host.src)) unmet.push('methodology')
  if (!persistsMethodology(host.src)) unmet.push('persist')
  if (!rendersMethodologyBar(host.src)) unmet.push('bar')

  if (usesSharedRowMapper(host.src)) return unmet

  const sources = fieldSources(host, opts)
  if (missingFieldsLayered(rowModelKind(host.file), sources, host.src).length > 0) {
    unmet.push('fields')
  }
  return unmet
}

/** 字段集判定的取值范围（宿主源码 ∪ 一级委托目标），抽出来供诊断与反向自检复用 */
function fieldSources(host: Host, opts: { readDelegates?: boolean } = {}): string[] {
  const sources = [host.src]
  if (opts.readDelegates !== false) {
    const handler = filledHandlerName(host.src)
    const body = handler ? extractFunctionBody(host.src, handler) : null
    if (body) sources.push(...delegateSources(host, body))
  }
  return sources
}

// ─── Allowlist：每条豁免须写明理由（≥10 字），总数只许变短 ───────────────────

type Allowlist = Readonly<Record<string, Partial<Record<ReqKey, string>>>>

/**
 * 已知未收口的宿主豁免清单。
 *
 * 规矩（R6.7）：
 * - 键 = 宿主文件名；值 = {未满足的要求 → 理由}
 * - 每条理由 ≥10 字，且必须指向具体归属（哪个 Task / 哪个后续 spec）
 * - **豁免总数只许变短**：修好一个就从这里删掉一条，`ALLOWED_EXCUSE_BASELINE` 同步下调
 */
const HOST_WIRING_ALLOWLIST: Allowlist = Object.freeze({
  'D1TabSamplingVouching.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 科目编码；未渲染方法学 bar 故层2「科目来源」不满足；接 bar 即自动满足，归 voucher-check-shared-layer 一并接',
  },
  'D2TabVoucherCheck.vue': {
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
  'D4TabOccurrence.vue': {
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 科目编码；未渲染方法学 bar 故层2「科目来源」不满足；接 bar 即自动满足，归 voucher-check-shared-layer 一并接',
  },
  'F2ValuationTestSheet.vue': {
    persist: '展示件无 allResponses 无法落库；methodology 已原样上抛，落库在父级 F2-38/39/40 宿主',
  },
  'G11TabVoucherCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
  'G12TabVoucherCheck.vue': {
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
  'H6TabCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 科目编码；未渲染方法学 bar 故层2「科目来源」不满足；接 bar 即自动满足，归 voucher-check-shared-layer 一并接',
  },
  'I1TabAdditionCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 凭证日期/金额（借或贷）/科目编码；行模型无金额位（合规检查项/计价测试型），补列须先回源模板核对，归 voucher-check-shared-layer',
  },
  'I1TabDisposalCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 金额（借或贷）/科目编码；行模型无金额位（合规检查项/计价测试型），补列须先回源模板核对，归 voucher-check-shared-layer',
  },
  'I2TabMaterialCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 科目编码；未渲染方法学 bar 故层2「科目来源」不满足；接 bar 即自动满足，归 voucher-check-shared-layer 一并接',
  },
  'I2TabOutsourceCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
  'I2TabStaffCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 金额（借或贷）/科目编码；行模型无金额位（合规检查项/计价测试型），补列须先回源模板核对，归 voucher-check-shared-layer',
  },
  'I2TabTargetedCheck.vue': {
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 科目编码；未渲染方法学 bar 故层2「科目来源」不满足；接 bar 即自动满足，归 voucher-check-shared-layer 一并接',
  },
  'I2TabWorkHourCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 凭证日期；行模型无记账凭证日期字段（只有业务事件日期/源单据日期号），补列须先回源模板核对，归 voucher-check-shared-layer',
  },
  'I3TabTargetedCheck.vue': {
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 科目编码；未渲染方法学 bar 故层2「科目来源」不满足；接 bar 即自动满足，归 voucher-check-shared-layer 一并接',
  },
  'I4TabTargetedCheck.vue': {
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 科目编码；未渲染方法学 bar 故层2「科目来源」不满足；接 bar 即自动满足，归 voucher-check-shared-layer 一并接',
  },
  'I5TabTargetedCheck.vue': {
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 科目编码；未渲染方法学 bar 故层2「科目来源」不满足；接 bar 即自动满足，归 voucher-check-shared-layer 一并接',
  },
  'I6TabTargetedCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 科目编码；未渲染方法学 bar 故层2「科目来源」不满足；接 bar 即自动满足，归 voucher-check-shared-layer 一并接',
  },
  'J1TabGeneralCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
  'K10TabOtherIncomeCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 凭证日期/科目编码；行模型无记账凭证日期字段（只有业务事件日期/源单据日期号），补列须先回源模板核对，归 voucher-check-shared-layer',
  },
  'K12TabNonOperatingCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 科目编码；未渲染方法学 bar 故层2「科目来源」不满足；接 bar 即自动满足，归 voucher-check-shared-layer 一并接',
  },
  'K13TabNonOperatingCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
  'K2TabCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
  'K3TabLongOutstanding.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 凭证日期/科目编码；行模型无记账凭证日期字段（只有业务事件日期/源单据日期号），补列须先回源模板核对，归 voucher-check-shared-layer',
  },
  'K3TabPayableCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
  'K3TabRelatedParty.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 凭证日期/科目编码；行模型无记账凭证日期字段（只有业务事件日期/源单据日期号），补列须先回源模板核对，归 voucher-check-shared-layer',
  },
  'K4TabCheck.vue': {
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
  'K5TabLitigationCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 凭证号/凭证日期/金额（借或贷）/科目编码；样本无凭证号也无 date/no 复合标签，层1「样本可回溯」未满足；归 voucher-check-shared-layer 统一行模型',
  },
  'K5TabProvisionCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
  'K7TabDeferredCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
  'K8TabContractCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
    fields: '分层判据缺 凭证日期/科目编码；行模型无记账凭证日期字段（只有业务事件日期/源单据日期号），补列须先回源模板核对，归 voucher-check-shared-layer',
  },
  'K8TabCutoffS2V.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
  'K8TabCutoffV2S.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
  'K8TabSellingCheck.vue': {
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
  'K9TabAdminCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
  'M1TabDividendCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
  'M2TabCapitalCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
  'N2TabTaxCheck.vue': {
    methodology: '本 spec Task 19~21 未列入该宿主；methodology 消费归 voucher-check-shared-layer',
    persist: '本 spec 范围外：固定 item key 持久化随 voucher-check-shared-layer 一并接',
    bar: '本 spec 范围外：方法学 bar 随 voucher-check-shared-layer 统一挂到抽凭区',
  },
})

/** 豁免总数基线（= allowlist 里所有 {宿主 × 要求} 条目数），只许调小 */
const ALLOWED_EXCUSE_BASELINE = 122

function excuseCount(list: Allowlist): number {
  return Object.values(list).reduce((n, reqs) => n + Object.keys(reqs).length, 0)
}

// ─── 诊断出口：仅在显式设置环境变量时落盘，CI 不触发 ────────────────────────

/**
 * `SAMPLING_HOST_SCAN_OUT=<abs path>` 时把扫描结果写成 JSON。
 *
 * 用途：Task 19/20/21 接线时取**权威工作清单**（控制台中文在 GBK 终端会被腌坏，
 * 逐个 grep 又容易漏）。不设该变量时本函数是空操作，故 CI 与常规跑测零副作用。
 */
function dumpScanReportIfRequested(): void {
  const out = process.env.SAMPLING_HOST_SCAN_OUT
  if (!out) return
  const report = HOSTS.map((h) => {
    const handler = filledHandlerName(h.src)
    const body = handler ? extractFunctionBody(h.src, handler) : null
    const sources = [h.src, ...(body ? delegateSources(h, body) : [])]
    return {
      file: h.file,
      rel: h.rel,
      thinShell: isThinShellDelegate(h.src),
      unmet: unmetRequirements(h),
      // 诊断细节：字段集缺哪几类 + 是否走共享映射件 + 委托目标数（供后续收口取清单）
      rowModelKind: rowModelKind(h.file),
      missingFieldsLayered: usesSharedRowMapper(h.src)
        ? []
        : missingFieldsLayered(rowModelKind(h.file), sources, h.src),
      // 旧一刀切口径，仅供对照（分层判据取代它做判定）
      missingFieldCategories: usesSharedRowMapper(h.src) ? [] : missingFieldCategories(sources),
      usesSharedRowMapper: usesSharedRowMapper(h.src),
      filledHandler: handler,
      delegateCount: body ? delegateSources(h, body).length : 0,
    }
  })
  writeFileSync(out, JSON.stringify(report, null, 2), 'utf-8')
}

// ─── 扫描面自检（防「扫到 0 个文件」式静默空转） ─────────────────────────────

describe('扫描面自检', () => {
  it('（诊断）按需导出扫描结果', () => {
    dumpScanReportIfRequested()
    expect(HOSTS.length).toBeGreaterThan(0)
  })

  it('抽凭宿主数量在合理下限之上（防目录走错导致守卫空转）', () => {
    expect(HOSTS.length).toBeGreaterThanOrEqual(60)
  })

  it('引擎自身不计入宿主', () => {
    expect(HOSTS.map((h) => h.file)).not.toContain(ENGINE_FILE)
  })

  it('共享件与展示组件确实存在（判据依赖它们的符号名）', () => {
    expect(
      existsSync(join(
        WORKPAPER_DIR, 'composables', 'shared', 'samplingFillTarget.ts',
      )),
    ).toBe(true)
    expect(
      existsSync(join(WORKPAPER_DIR, 'shared', 'WpSamplingMethodologyBar.vue')),
    ).toBe(true)
  })
})

// ─── stripComments 反向自检 ──────────────────────────────────────────────────

describe('stripComments 反向自检', () => {
  it('真剥掉三类注释（否则守卫会把说明文字数成真实消费点）', () => {
    const src = [
      '<!-- 这里提到 methodology 只是说明 -->',
      '<script setup lang="ts">',
      '/* 块注释里也提到 samplingMethodologyItemKey */',
      'const a = 1 // 行注释里提到 WpSamplingMethodologyBar',
      "const url = 'https://example.com/x'",
      '</script>',
    ].join('\n')
    const out = stripComments(src)
    expect(out).not.toContain('methodology')
    expect(out).not.toContain('samplingMethodologyItemKey')
    expect(out).not.toContain('WpSamplingMethodologyBar')
    // 不得把 URL 的 `//` 当行注释吃掉（它在字符串里）
    expect(out).toContain('https://example.com/x')
  })

  it('剥离前的替身源码确实含被禁字样（证明上一条不是空转）', () => {
    const src = '<!-- methodology -->'
    expect(src).toContain('methodology')
    expect(stripComments(src)).not.toContain('methodology')
  })

  it('🔴 回归：模板里的 accept="image/*" 不得把后面的引擎标签吞掉', () => {
    // 守卫第一版用正则剥块注释，`image/*` 的 `/*` 一直吞到几千字符后的 `*/`，
    // 使 G6TabVoucherCheck 与 K8TabSellingCheck 两个真实宿主逃出扫描面。
    const src = [
      '<template>',
      '  <input type="file" accept="image/*,.pdf" />',
      '  <GtVoucherSamplingEngine @filled="onFilled" />',
      '</template>',
      '<script setup lang="ts">',
      'const x = 1 /* 真注释 */',
      '</script>',
    ].join('\n')
    const out = stripComments(src)
    expect(out).toContain('<GtVoucherSamplingEngine')
    expect(out).not.toContain('真注释')
  })

  it('🔴 回归：两个曾逃出扫描面的真实宿主现在必须被识别为宿主', () => {
    const files = HOSTS.map((h) => h.file)
    expect(files).toContain('G6TabVoucherCheck.vue')
    expect(files).toContain('K8TabSellingCheck.vue')
  })

  it('<style> 区整段丢弃（样式名不参与任何判据）', () => {
    const out = stripComments(
      '<template><div class="a"/></template><style>.methodology-context{color:red}</style>',
    )
    expect(out).not.toContain('methodology-context')
  })
})

// ─── Property 15：覆盖率单调收敛 ─────────────────────────────────────────────

describe('Property 15：宿主 methodology 覆盖率单调收敛', () => {
  it('未满足要求的宿主必须在 allowlist 里被逐条豁免', () => {
    const violations: string[] = []
    for (const host of HOSTS) {
      const unmet = unmetRequirements(host)
      const excused = HOST_WIRING_ALLOWLIST[host.file] ?? {}
      const notExcused = unmet.filter((k) => !excused[k])
      if (notExcused.length > 0) {
        violations.push(
          `${host.file}  缺 [${notExcused.map((k) => REQ_LABELS[k]).join(' / ')}]  ${host.rel}`,
        )
      }
    }
    expect(
      violations,
      `以下宿主未满足抽样方法学收口要求且未登记豁免（共 ${violations.length} 个）：\n` +
        violations.join('\n'),
    ).toEqual([])
  })

  it('allowlist 每条豁免都写明理由且不少于 10 字', () => {
    const bad: string[] = []
    for (const [file, reqs] of Object.entries(HOST_WIRING_ALLOWLIST)) {
      for (const [key, reason] of Object.entries(reqs)) {
        if (typeof reason !== 'string' || reason.trim().length < 10) {
          bad.push(`${file}.${key} → ${JSON.stringify(reason)}`)
        }
      }
    }
    expect(bad, `豁免理由缺失或过短：\n${bad.join('\n')}`).toEqual([])
  })

  it('allowlist 不得残留已修好的豁免（强制只减不增）', () => {
    const stale: string[] = []
    for (const [file, reqs] of Object.entries(HOST_WIRING_ALLOWLIST)) {
      const host = HOSTS.find((h) => h.file === file)
      if (!host) {
        stale.push(`${file}（已不是抽凭宿主，请从 allowlist 删除）`)
        continue
      }
      const unmet = new Set(unmetRequirements(host))
      for (const key of Object.keys(reqs) as ReqKey[]) {
        if (!unmet.has(key)) stale.push(`${file}.${key}（已满足，请从 allowlist 删除）`)
      }
    }
    expect(stale, `allowlist 残留：\n${stale.join('\n')}`).toEqual([])
  })

  it('豁免总数不超过基线（只许变短）', () => {
    expect(excuseCount(HOST_WIRING_ALLOWLIST)).toBeLessThanOrEqual(
      ALLOWED_EXCUSE_BASELINE,
    )
  })
})

// ─── Property 15 反向自检 ────────────────────────────────────────────────────

const STUB_DIR = join(WORKPAPER_DIR, '__stub__')

function stubHost(src: string, file = 'StubTabVoucherCheck.vue'): Host {
  return {
    file,
    rel: `stub/${file}`,
    abs: join(STUB_DIR, file),
    src: stripComments(src),
  }
}

describe('Property 15 反向自检：替身宿主必须被判违规', () => {
  it('丢弃 methodology 的替身宿主 → 判 methodology / persist / bar 三项未满足', () => {
    const stub = stubHost(`
      <template>
        <el-dialog v-model="v">
          <GtVoucherSamplingEngine @filled="onFilled" />
        </el-dialog>
      </template>
      <script setup lang="ts">
      function onFilled(payload: { samples: any[] }) {
        payload.samples.forEach((s) => addRow({
          voucherNo: s.voucherNo, voucherDate: s.voucherDate,
          debitAmount: s.debitAmount, accountCode: s.accountCode,
        }))
      }
      </script>
    `)
    const unmet = unmetRequirements(stub, { readDelegates: false })
    expect(unmet).toContain('methodology')
    expect(unmet).toContain('persist')
    expect(unmet).toContain('bar')
    // 字段齐备 ⇒ 不该报 fields（证明四项判定彼此独立、不是一锅红）
    expect(unmet).not.toContain('fields')
  })

  it('只读 summary 的替身宿主 → 判 fields 未满足', () => {
    const stub = stubHost(`
      <template><GtVoucherSamplingEngine @filled="onFilled" /></template>
      <script setup lang="ts">
      function onFilled(payload: { samples: any[]; methodology?: any }) {
        payload.samples.forEach((v) => addRow(v.summary || v.voucherNo))
        persist(samplingMethodologyItemKey('K8'), payload.methodology)
      }
      </script>
      <template><WpSamplingMethodologyBar :methodology="m" /></template>
    `)
    const unmet = unmetRequirements(stub, { readDelegates: false })
    expect(unmet).toEqual(['fields'])
  })

  it('methodology-context 这类 CSS 类名不算消费（防判据被样式名蒙过去）', () => {
    const stub = stubHost(`
      <template>
        <div class="methodology-context">方法论提示</div>
        <GtVoucherSamplingEngine @filled="onFilled" />
      </template>
      <style scoped>.methodology-context { border-left: 4px solid #f59e0b; }</style>
    `)
    expect(unmetRequirements(stub, { readDelegates: false })).toContain('methodology')
  })

  it('薄壳 v-bind="$props" 委托视为已满足（R6.6）', () => {
    const stub = stubHost(`
      <template>
        <GtVoucherSamplingEngine v-if="false" />
        <BaseVoucherCheck v-bind="$props" />
      </template>
    `)
    expect(unmetRequirements(stub, { readDelegates: false })).toEqual([])
  })

  it('走共享映射件的宿主字段集天然满足', () => {
    const stub = stubHost(`
      <template>
        <GtVoucherSamplingEngine @filled="onFilled" />
        <WpSamplingMethodologyBar :methodology="m" />
      </template>
      <script setup lang="ts">
      import { mapSampledRows, samplingMethodologyItemKey } from '../composables/shared/samplingFillTarget'
      function onFilled(payload: { samples: any[]; methodology?: any }) {
        rows.value = mapSampledRows(payload.samples)
        persist(samplingMethodologyItemKey('D3'), payload.methodology)
      }
      </script>
    `)
    expect(unmetRequirements(stub, { readDelegates: false })).toEqual([])
  })
})

// ─── Property 16：最小字段集 ─────────────────────────────────────────────────

describe('Property 16：宿主样本映射最小字段集', () => {
  it('四类语义的判据互不重叠且金额借贷任一即可', () => {
    expect(missingFieldCategories(['voucherNo voucherDate creditAmount accountCode']))
      .toEqual([])
    expect(missingFieldCategories(['voucher_no voucher_date debit_amount account_code']))
      .toEqual([])
    expect(missingFieldCategories(['summary'])).toEqual([
      '凭证号', '凭证日期', '金额（借或贷）', '科目编码',
    ])
  })

  it('只读 voucherNo 与 summary 二者之一即判违规', () => {
    expect(missingFieldCategories(['v.summary'])).toContain('凭证号')
    expect(missingFieldCategories(['v.voucherNo']).length).toBeGreaterThan(0)
  })

  it('宿主字段覆盖度必须在 allowlist 约束内（与 Property 15 同一判定）', () => {
    const violations: string[] = []
    for (const host of HOSTS) {
      if (isThinShellDelegate(host.src)) continue
      const unmet = unmetRequirements(host)
      if (!unmet.includes('fields')) continue
      if (!(HOST_WIRING_ALLOWLIST[host.file] ?? {}).fields) {
        violations.push(`${host.file}  ${host.rel}`)
      }
    }
    expect(
      violations,
      `以下宿主样本映射未覆盖最小字段集且未登记豁免：\n${violations.join('\n')}`,
    ).toEqual([])
  })
})

// ─── Property 16 分层判据（2026-08-04 裁决）──────────────────────────────────

describe('Property 16 分层判据：层 1 全体强制 + 层 2 按行模型语义', () => {
  it('层 1「样本可回溯」对每一个 kind 都强制要求凭证号', () => {
    const kinds = Object.keys(KIND_TIER2) as RowModelKind[]
    expect(kinds.length).toBeGreaterThanOrEqual(5)
    for (const kind of kinds) {
      // 只带摘要不带凭证号 ⇒ 无论什么行模型都必须打红
      expect(
        missingFieldsLayered(kind, ['addRow(v.summary)'], ''),
        `kind=${kind} 未强制层 1`,
      ).toContain('凭证号')
    }
  })

  it('层 1 是收紧：仅带凭证号即可满足非凭证明细型宿主', () => {
    for (const kind of ['compliance-checklist', 'valuation-test', 'account-detail'] as const) {
      expect(missingFieldsLayered(kind, ['row.voucherNo = v.voucherNo'], '')).toEqual([])
    }
  })

  it('凭证明细型仍强制日期与金额（分层不是放宽）', () => {
    const src = ['row.voucherNo = v.voucherNo']
    const missing = missingFieldsLayered('voucher-detail', src, 'WpSamplingMethodologyBar')
    expect(missing).toContain('凭证日期')
    expect(missing).toContain('金额（借或贷）')
  })

  it('no-voucher-date 免日期但不免金额（源模板无日期列 ≠ 无金额列）', () => {
    const missing = missingFieldsLayered(
      'no-voucher-date', ['row.voucherNo = v.voucherNo'], 'WpSamplingMethodologyBar',
    )
    expect(missing).not.toContain('凭证日期')
    expect(missing).toContain('金额（借或贷）')
  })

  it('科目来源可由已渲染的方法学 bar 满足（accountCodes 已在底稿正文可见）', () => {
    const sources = ['row.voucherNo = v.voucherNo; row.date = v.voucherDate; row.amt = v.debitAmount']
    expect(missingFieldsLayered('voucher-detail', sources, '<WpSamplingMethodologyBar />')).toEqual([])
    // 既无逐行 accountCode 又没渲染 bar ⇒ 科目来源无处可查，必须打红
    expect(missingFieldsLayered('voucher-detail', sources, '')).toEqual([
      '科目来源（逐行 accountCode 或已渲染方法学 bar）',
    ])
  })

  it('kind 登记表每条都写明源模板依据（≥20 字）且指向真实宿主', () => {
    const hostFiles = new Set(HOSTS.map((h) => h.file))
    for (const [file, spec] of Object.entries(HOST_ROW_MODEL_KIND)) {
      expect(hostFiles.has(file), `${file} 不在扫描面内，登记无意义`).toBe(true)
      expect(spec.kind, `${file} 登记为默认 kind 属冗余`).not.toBe('voucher-detail')
      expect(spec.reason.trim().length, `${file} 的理由过短`).toBeGreaterThanOrEqual(20)
    }
  })

  it('非凭证明细型登记数只许变少（防 kind 表被当逃逸阀）', () => {
    const n = Object.keys(HOST_ROW_MODEL_KIND).length
    expect(
      n,
      `非凭证明细型登记数 ${n} 超过基线 ${NON_VOUCHER_DETAIL_BASELINE}；` +
        '新增登记须先在 spec 里给出源模板依据并由用户裁决',
    ).toBeLessThanOrEqual(NON_VOUCHER_DETAIL_BASELINE)
  })

  it('🔴 反向自检：把 H10 强标 voucher-detail 时必须打红', () => {
    const h10 = HOSTS.find((h) => h.file === 'H10TabCheck.vue')
    expect(h10, 'H10TabCheck.vue 必须在扫描面内（登记项依赖它）').toBeTruthy()
    const sources = fieldSources(h10!)
    // 实际登记为 compliance-checklist ⇒ 满足
    expect(missingFieldsLayered('compliance-checklist', sources, h10!.src)).toEqual([])
    // 强标凭证明细型 ⇒ 金额缺口暴露（证明分层判据没有把它一律放行）
    expect(missingFieldsLayered('voucher-detail', sources, h10!.src)).toContain('金额（借或贷）')
  })

  it('🔴 反向自检：F2 两张检查表强标 voucher-detail 时必须因缺日期打红', () => {
    for (const file of ['F2TabPurchaseInboundCheck.vue', 'F2TabMaterialUsageCheck.vue']) {
      const host = HOSTS.find((h) => h.file === file)
      expect(host, `${file} 必须在扫描面内`).toBeTruthy()
      const sources = fieldSources(host!)
      expect(missingFieldsLayered('no-voucher-date', sources, host!.src)).toEqual([])
      expect(
        missingFieldsLayered('voucher-detail', sources, host!.src),
        `${file} 强标凭证明细型未打红 ⇒ 分层判据失去区分力`,
      ).toContain('凭证日期')
    }
  })

  it('🔴 层 1 确实抓到真实缺陷：存在样本一条都不进底稿的宿主', () => {
    const tier1Violations = HOSTS.filter((h) => {
      if (isThinShellDelegate(h.src) || usesSharedRowMapper(h.src)) return false
      return missingFieldsLayered(rowModelKind(h.file), fieldSources(h), h.src)
        .includes('凭证号')
    }).map((h) => h.file)
    // 实测 K5TabLitigationCheck 的 onSampleFilled 只弹一条 success，样本整批丢弃。
    // 这条断言的意义 = 证明层 1 不是空转；修好后应把它从下面的期望里删掉。
    expect(tier1Violations).toContain('K5TabLitigationCheck.vue')
  })
})

// ─── 委托解析自检 ────────────────────────────────────────────────────────────

describe('一级委托解析自检', () => {
  it('能取到 @filled 的处理函数名', () => {
    expect(filledHandlerName('<GtVoucherSamplingEngine @filled="onSampleFilled" />'))
      .toBe('onSampleFilled')
    expect(filledHandlerName('<GtVoucherSamplingEngine @filled="(p) => f(p)" />'))
      .toBeNull()
  })

  it('按花括号配对截函数体，不溢出到下一个函数', () => {
    const src = [
      'function onFilled(p: any) {',
      '  if (p) { fill(p.samples) }',
      '}',
      'function other() { const voucherDate = 1 }',
    ].join('\n')
    const body = extractFunctionBody(src, 'onFilled') ?? ''
    expect(body).toContain('fill(p.samples)')
    expect(body).not.toContain('voucherDate')
  })

  it('取不到函数体时返回 null（调用方据此退化为只看宿主源码）', () => {
    expect(extractFunctionBody('const x = 1', 'onFilled')).toBeNull()
  })

  it('🔴 回归：参数含内联类型字面量时不得把类型当函数体', () => {
    const src = [
      'function onSampleFilled(payload: { samples: SampledVoucher[]; fillMode: FillMode }) {',
      '  applySamplingResults(payload.samples, payload.fillMode)',
      '}',
    ].join('\n')
    const body = extractFunctionBody(src, 'onSampleFilled') ?? ''
    expect(body).toContain('applySamplingResults')
    // 旧实现会截到 ` samples: SampledVoucher[]; fillMode: FillMode ` 这段类型
    expect(body).not.toContain('SampledVoucher[]')
  })

  it('箭头函数与多层括号参数也能截对', () => {
    const src = [
      'const onFilled = (p: { a: (x: number) => void }) => {',
      '  doWork(p)',
      '}',
    ].join('\n')
    expect(extractFunctionBody(src, 'onFilled') ?? '').toContain('doWork(p)')
  })

  it('🔴 回归：跟进 setup 层解构的 composable（否则「映射写在 composable 里」被误判成没映射）', () => {
    const stub = stubHost(`
      <template>
        <GtVoucherSamplingEngine @filled="handleSamplingFilled" />
        <WpSamplingMethodologyBar :methodology="methodology" />
      </template>
      <script setup lang="ts">
      import { useF3VoucherCheck } from '../composables/useF3VoucherCheck'
      const { applySamplingResults } = useF3VoucherCheck({} as never)
      function handleSamplingFilled(payload: { samples: any[] }) {
        applySamplingResults(payload.samples, 'append')
      }
      </script>
    `)
    // useF3VoucherCheck 里映射了 voucherNo/voucherDate/debitAmount/creditAmount，
    // 故不得再报「凭证号 / 日期 / 金额」缺失（只可能剩科目编码）
    const unmet = unmetRequirements(stub)
    const missing = missingFieldCategories([
      stub.src,
      ...delegateSources(stub, extractFunctionBody(stub.src, 'handleSamplingFilled') ?? ''),
    ])
    expect(missing).not.toContain('凭证号')
    expect(missing).not.toContain('凭证日期')
    expect(missing).not.toContain('金额（借或贷）')
    // 旧判据下这里断言 `unmet` 仍含 'fields'（因只剩「科目编码」未映射）。
    // 分层判据落地后该断言已过时：本替身渲染了 bar ⇒ 层 2 的「科目来源」由
    // methodology.accountCodes 满足 ⇒ fields 合格。这条用例要验的是**委托解析
    // 生效**（不是"仍有缺口"），故改为正向断言：跟进 composable 后 fields 通过。
    expect(unmet).not.toContain('fields')
    // 并保留「不跟委托就会误判」的对照，证明委托解析确实是必要的
    const withoutDelegate = unmetRequirements(stub, { readDelegates: false })
    expect(withoutDelegate).toContain('fields')
  })

  it('🔴 回归：对象式 composable（const ic = useX() 后 ic.method()）也要跟进', () => {
    const stub = stubHost(`
      <script setup lang="ts">
      import { useF2MaterialUsageCheck } from '../composables/useF2InspectionCheck'
      const ic = useF2MaterialUsageCheck({} as never)
      function handleSamplingFilled(payload: { samples: any[] }) {
        ic.fillFromSampling(payload.samples, 'append')
      }
      </script>
    `)
    const map = objectFormComposableMap(stub)
    expect(map.ic).toBeTruthy()
    const srcs = delegateSources(
      stub, extractFunctionBody(stub.src, 'handleSamplingFilled') ?? '',
    )
    expect(srcs.length).toBeGreaterThan(0)
    // useF2InspectionCheck.mapVoucherToRow 映射了借贷金额 ⇒ 不得再报「金额」缺失
    expect(missingFieldCategories([stub.src, ...srcs])).not.toContain('金额（借或贷）')
  })

  it('🔴 回归：`@/` 别名 import 也要跟进（G6 的映射件在 @/composables 下）', () => {
    const stub = stubHost(`
      <script setup lang="ts">
      import { useG6EclVoucherCheck } from '@/composables/useG6EclVoucherCheck'
      const vc = useG6EclVoucherCheck({} as never)
      function onSamplesFilled(payload: { samples: any[] }) {
        vc.applySampling({ samples: payload.samples })
      }
      </script>
    `)
    const srcs = delegateSources(stub, extractFunctionBody(stub.src, 'onSamplesFilled') ?? '')
    expect(srcs.length).toBeGreaterThan(0)
    // 该件里写着 `sample.voucherDate ?? sample.date` ⇒ 不得再报「凭证日期」缺失
    expect(missingFieldCategories([stub.src, ...srcs])).not.toContain('凭证日期')
  })

  it('解构解析支持 `a` / `loading: x` / `b = 1` 三种形态', () => {
    const stub = stubHost(`
      <script setup lang="ts">
      import { useX } from '../composables/useF3VoucherCheck'
      const { applySamplingResults, loading: aiLoading, seq = 1 } = useX({} as never)
      </script>
    `)
    const map = destructuredComposableMap(stub)
    expect(Object.keys(map).sort()).toEqual(['aiLoading', 'applySamplingResults', 'seq'])
  })

  it('🔴 回归：类型 import 与共享定义件不得成为「字段来源」', () => {
    // 守卫第二版的假绿：宿主为类型断言 import 了 SamplingMethodologySnapshot，
    // 一级委托把 samplingFillTarget.ts（最小字段集的**定义方**）拉进来当字段来源，
    // 于是任何接过线的宿主都自动通过字段集判定。
    expect(FIELD_SCAN_EXCLUDED).toContain('composables/shared/samplingFillTarget.ts')
    const stub = stubHost(`
      <template>
        <GtVoucherSamplingEngine @filled="onFilled" />
        <WpSamplingMethodologyBar :methodology="methodology" />
      </template>
      <script setup lang="ts">
      import { useSamplingMethodologyPersist } from '../composables/shared/useSamplingMethodologyPersist'
      import type { SamplingMethodologySnapshot } from '../composables/shared/samplingFillTarget'
      const { methodology, persistMethodology } = useSamplingMethodologyPersist({} as never)
      function onFilled(payload: { samples: any[] }) {
        void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)
        payload.samples.forEach((v) => addRow(v.summary))
      }
      </script>
    `)
    // 只读 summary ⇒ 必须仍判 fields 未满足（不得被共享件的字段名蒙过去）
    expect(unmetRequirements(stub)).toContain('fields')
  })
})
