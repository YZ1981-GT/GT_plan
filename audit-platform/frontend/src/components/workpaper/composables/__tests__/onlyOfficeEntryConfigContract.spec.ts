/**
 * task 5.3：前端契约守卫 —— 唯一 URL / 唯一 resolver / pending 文案 / 模式集合封闭。
 *
 * spec: `onlyoffice-sheet-open-via-published-artifact` task 5.3
 * Requirements: 1, 4, 6, 10
 *
 * ═══ 为什么这些判据要读**源码**而不是只跑行为 ═══
 *
 * 行为测试能证明「当前实现按契约工作」，但证明不了「没有第二个实现」：
 * 有人新加一个 `probeSheetConfig()` 直接拼 `/sync/entry-identity` 时，所有行为测试仍绿，
 * 而「唯一 URL 拼接点」这条 Requirement 已经被破坏。所以本文件用**源码扫描 + AST 式判据**
 * 补齐这一层。
 *
 * ═══ 四条判据 ═══
 *
 * 1. **唯一 URL**：`/sync/entry-identity` 与 `onlyoffice-config` 的字面量只允许出现在
 *    被登记的位置（`onlyOfficeEntryConfig.ts` 是唯一入口，`onlyOfficeSheetConfig.ts` 是
 *    它的 URL 拼装）。其他地方出现即红。
 * 2. **唯一 binding resolver**：`onlyOfficeEntryConfig.ts` 必须是唯一读 `status` /
 *    `binding_status` 的地方 —— 别处自己解析 binding 状态就是第二套真源。
 * 3. **pending 文案**：`independent` 语义必须有明确文案来源，且不得出现「已同步」假状态。
 * 4. **模式集合封闭**：`SheetBindingStatus` 的成员必须与后端生成物逐值相等。
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

import { describe, expect, it } from 'vitest'

// ── 源码树扫描（不经 vite 的 glob，避免额外依赖）────────────────────────────

const SRC_ROOT = join(__dirname, '..', '..', '..', '..')

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    const st = statSync(full)
    if (st.isDirectory()) {
      if (name === 'node_modules' || name === '__tests__') continue
      walk(full, out)
    } else if (name.endsWith('.ts') || name.endsWith('.vue')) {
      out.push(full)
    }
  }
  return out
}

function sourceFiles(): string[] {
  return walk(SRC_ROOT)
}

function relOf(full: string): string {
  return relative(SRC_ROOT, full).replace(/\\/g, '/')
}

/** 去掉注释，只留代码行（判据不许被注释满足）。 */
function codeLines(text: string): string[] {
  return text
    .split('\n')
    .filter((line) => {
      const s = line.trim()
      return !(s.startsWith('//') || s.startsWith('*') || s.startsWith('/*'))
    })
}

/** 含某个字面量的**代码**文件（相对路径集合）。 */
function filesMentioning(needle: string): Set<string> {
  const out = new Set<string>()
  for (const full of sourceFiles()) {
    const text = readFileSync(full, 'utf-8')
    if (codeLines(text).some((line) => line.includes(needle))) {
      out.add(relOf(full))
    }
  }
  return out
}

// ── 登记：这两个字面量只允许出现在这些文件里 ─────────────────────────────────

const ENTRY_IDENTITY_URL = '/sync/entry-identity'
const LEGACY_CONFIG_URL = 'onlyoffice-config'

//: `/sync/entry-identity` 的**期望**出现次数是 0（见判据 1a）。这里刻意不设白名单：
//: 留一个白名单等于给「硬编码回来」留门。

const LEGACY_CONFIG_ALLOWED_BASE = new Set([
  // 唯一入口本身
  'components/workpaper/composables/onlyOfficeEntryConfig.ts',
  // 它的 URL 拼装
  'components/workpaper/sync/onlyOfficeSheetConfig.ts',
  // http 只判断该 URL 要不要带 client_instance 头（不发起调用）
  'utils/http.ts',
])

/**
 * 已登记的 legacy 调用方（真源是 task 3.7 的 ledger，**不在这里重抄白名单**）。
 *
 * 🔴 3.7 的语义是「未迁移的调用方**可以**存在，但必须逐条登记 owner + reason + next」；
 * 5.3 要判的是「**未登记**的不许有」。两份判据必须同源 —— 在测试里另抄一份白名单
 * 会让「ledger 加了一条、这里忘了加」变成假红，而「这里加了一条、ledger 没有」
 * 变成假绿（漏登记被测试放行）。
 */
function registeredLegacyCallers(): Set<string> {
  const candidates = [
    join(process.cwd(), '..', 'backend', 'data', 'workpaper_sync_legacy_onlyoffice_callers.json'),
    join(process.cwd(), '..', '..', 'backend', 'data', 'workpaper_sync_legacy_onlyoffice_callers.json'),
  ]
  for (const p of candidates) {
    try {
      const payload = JSON.parse(readFileSync(p, 'utf-8')) as {
        callers: Record<string, unknown>
      }
      return new Set(Object.keys(payload.callers))
    } catch {
      continue
    }
  }
  // 无后端目录（纯前端环境）时只允许 3 个合法入口 —— 保守方向：
  // 宁可让本地跑出假红，也不让未登记调用方静默通过。
  return new Set()
}

describe('判据 1：唯一 URL 拼接点', () => {
  it(`${ENTRY_IDENTITY_URL} 字面量在前端必须为 0`, () => {
    // 🔴 期望是 **0** 而不是「至少一处」：task 3.1 起路径来自生成契约
    // （`WP_SYNC_SIBLING_PREFIX_TEMPLATE`），任何硬编码字面量都是倒退 ——
    // 前缀一改就是静默 404（`utils/http` 的 baseURL 是 `/`，少 `/api` 会拿到首页 HTML
    // 被调用方 catch 吞掉）。
    const found = filesMentioning(ENTRY_IDENTITY_URL)
    expect(
      [...found],
      `这些文件硬编码了 entry-identity URL（应改用 entryIdentityUrl / 生成契约）：${[...found]}`,
    ).toEqual([])
  })

  it('唯一入口的 entryIdentityUrl 函数体里**真的用了**生成模板', () => {
    // 🔴 只查「文件里含这个字符串」不够：把 import 换成 alias 之后字符串仍在
    // （别处用到）⇒ 判据绿而函数已经硬编码了（实测 M3 存活）。必须查**函数体**。
    const text = readFileSync(
      join(SRC_ROOT, 'components/workpaper/composables/onlyOfficeEntryConfig.ts'),
      'utf-8',
    )
    const match = text.match(
      /export function entryIdentityUrl\([^)]*\)[^{]*\{([\s\S]*?)\n\}/,
    )
    expect(match, '找不到 entryIdentityUrl 函数定义').not.toBeNull()
    const body = match![1]
    expect(
      body,
      `entryIdentityUrl 的函数体里没有引用 WP_SYNC_SIBLING_PREFIX_TEMPLATE（硬编码回来了？）：\n${body}`,
    ).toContain('WP_SYNC_SIBLING_PREFIX_TEMPLATE')
  })

  it(`${LEGACY_CONFIG_URL} 只允许出现在合法入口或 3.7 ledger 已登记的文件里`, () => {
    const found = filesMentioning(LEGACY_CONFIG_URL)
    const allowed = new Set([...LEGACY_CONFIG_ALLOWED_BASE, ...registeredLegacyCallers()])
    const extra = [...found].filter((f) => !allowed.has(f))
    expect(
      extra,
      `这些文件自己拼了 onlyoffice-config URL 且未在 3.7 ledger 登记：${extra}`,
    ).toEqual([])
    // 分母守卫：允许集不能因为 ledger 读不到而退化成空（那会让本条恒红或恒绿）。
    expect(allowed.size).toBeGreaterThanOrEqual(3)
  })

  it('URL 拼接函数本身只定义一次（不是多处各写一份模板）', () => {
    const found = [...filesMentioning('function entryIdentityUrl')].concat(
      [...filesMentioning('export function entryIdentityUrl')],
    )
    expect(new Set(found).size).toBe(1)
    expect(found[0]).toBe('components/workpaper/composables/onlyOfficeEntryConfig.ts')
  })
})

// ── 判据 2：唯一 binding resolver ────────────────────────────────────────────

describe('判据 2：唯一 binding 状态解析点', () => {
  it('只有唯一入口读 binding status 字段', () => {
    // `binding_status` / `bindingStatus` 的**读取**只允许在唯一入口里。
    // 别处自己解析就是第二套真源（两处口径分叉时前端会显示矛盾状态）。
    const readers = new Set<string>()
    for (const full of sourceFiles()) {
      const text = readFileSync(full, 'utf-8')
      const hit = codeLines(text).some(
        (line) =>
          line.includes('binding_status') ||
          line.includes('bindingStatus') ||
          line.includes('BINDING_STATUSES'),
      )
      if (hit) readers.add(relOf(full))
    }
    // 类型定义可以出现在 DTO 层（如果有），但当前只有唯一入口 —— 断言它就是唯一。
    expect([...readers]).toEqual([
      'components/workpaper/composables/onlyOfficeEntryConfig.ts',
    ])
  })

  it('唯一入口导出了封闭域常量（供别处引用而不是重抄）', () => {
    const text = readFileSync(
      join(SRC_ROOT, 'components/workpaper/composables/onlyOfficeEntryConfig.ts'),
      'utf-8',
    )
    expect(text).toContain('export type SheetBindingStatus')
    // 封闭域数组必须存在（运行期用它把未知值归 null）
    expect(text).toContain('BINDING_STATUSES')
  })
})

// ── 判据 3：pending 文案与「已同步」假状态 ───────────────────────────────────

describe('判据 3：pending / independent 文案', () => {
  it('唯一入口暴露 syncMode，且两个值都出现在类型里', () => {
    const text = readFileSync(
      join(SRC_ROOT, 'components/workpaper/composables/onlyOfficeEntryConfig.ts'),
      'utf-8',
    )
    expect(text).toMatch(/'bound'\s*\|\s*'independent'/)
  })

  it('不允许在唯一入口之外声称「已同步」（Requirement 4.2 / 6.2）', () => {
    // 🔴 判据范围刻意收窄到**本 spec 相关文件**：全仓搜「已同步」会命中大量与
    // 在线编辑无关的业务文案（附注同步、公式推送等），那是误报。
    //
    // 🔴 **必须同时扫注释**：首版只扫 `codeLines()`（剥掉注释），而「已同步」写进
    // JSDoc 里同样会误导读者 —— Requirement 4.3 明写「不得通过注释长期隐藏」。
    // 实测把 `/** 已同步 */` 加进去时判据存活（M7）。
    const scoped = [
      'components/workpaper/composables/onlyOfficeEntryConfig.ts',
      'components/workpaper/sync/onlyOfficeSheetConfig.ts',
    ]
    const offenders: string[] = []
    for (const rel of scoped) {
      const full = join(SRC_ROOT, rel)
      try {
        const text = readFileSync(full, 'utf-8')
        for (const line of text.split('\n')) {
          // 允许「不同步」「未同步」这类否定表述；禁止肯定式「已同步」「双向回写」。
          if (/已同步|双向回写/.test(line) && !/不同步|未同步|不得|禁止|而不是/.test(line)) {
            offenders.push(`${rel}: ${line.trim().slice(0, 100)}`)
          }
        }
      } catch {
        // 文件不存在时跳过（同步 shell 已删掉它的情况）
      }
    }
    expect(offenders, `这些地方声称了「已同步」：\n${offenders.join('\n')}`).toEqual([])
  })
})

// ── 判据 4：模式集合封闭（与后端生成物逐值相等）──────────────────────────────

describe('判据 4：binding 模式集合封闭', () => {
  it('前端封闭域与后端 ledger / bindings 里出现的状态值一致', () => {
    const ledgerPath = join(
      __dirname, '..', '..', '..', '..', '..', '..', '..',
      'backend', 'data', 'workpaper_sync_sheet_open_bindings.json',
    )
    // 路径在不同布局下可能不同，逐个候选尝试。
    const candidates = [
      ledgerPath,
      join(process.cwd(), '..', 'backend', 'data', 'workpaper_sync_sheet_open_bindings.json'),
      join(process.cwd(), '..', '..', 'backend', 'data', 'workpaper_sync_sheet_open_bindings.json'),
    ]
    let raw: string | null = null
    for (const p of candidates) {
      try {
        raw = readFileSync(p, 'utf-8')
        break
      } catch {
        continue
      }
    }
    if (raw === null) {
      // 前端单测在无后端目录的环境里跑时跳过（CI 的后端守卫覆盖同一件事）。
      return
    }
    const payload = JSON.parse(raw) as { bindings: Array<{ status: string }> }
    const backendStates = new Set(payload.bindings.map((r) => r.status))
    const frontendText = readFileSync(
      join(SRC_ROOT, 'components/workpaper/composables/onlyOfficeEntryConfig.ts'),
      'utf-8',
    )
    // 前端封闭域声明（type 里逐个字面量）
    const declared = new Set(
      [...frontendText.matchAll(/^\s*\|\s*'([a-z_]+)'\s*$/gm)].map((m) => m[1]),
    )
    const missing = [...backendStates].filter((s) => !declared.has(s))
    expect(
      missing,
      `后端出现但前端封闭域没声明的状态：${missing}（前端会把它静默归 null）`,
    ).toEqual([])
  })

  it('封闭域恰好 6 个成员（加成员必须同时改判据）', () => {
    const text = readFileSync(
      join(SRC_ROOT, 'components/workpaper/composables/onlyOfficeEntryConfig.ts'),
      'utf-8',
    )
    const members = [...text.matchAll(/^\s*\|\s*'([a-z_]+)'\s*$/gm)].map((m) => m[1])
    expect(members.sort()).toEqual([
      'draining',
      'migrated',
      'out_of_scope',
      'pending',
      'ready',
      'retired',
    ])
  })
})
