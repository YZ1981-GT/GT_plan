/**
 * voucherAccountScopeConsistency.spec.ts — AccountScope 口径一致性守卫
 *
 * spec: voucher-attach-account-mapping-closure（Task 21）
 * Requirements: R2.1（accountPrefixes 来自 AccountScope）, R2.2（禁硬编码科目前缀）, R3.1
 * Design: §四.1 — 扫描 importFromAttached / pullSamplesForWorkpaper 的 accountPrefixes 参数来源
 *
 * 验证四件事：
 * 1. **pullSamplesForWorkpaper 消费端必须有 inject('tbSourceCodes')**
 * 2. **GtVoucherSamplingEngine 消费端必须有 inject('tbSourceCodes')**
 * 3. **pullSamplesForWorkpaper 第四参数禁止硬编码数字数组字面量**
 * 4. **F2_INVENTORY_ACCOUNT_CODES 不得在 :account-code 绑定中直接使用**
 *
 * 🔴 守卫设计原则：本守卫是**棘轮**（只许减少不许增加）。
 *    NOT_YET_MIGRATED 是冻结的例外清单——代表本 spec 之前的 voucher-sampling-account-scope-and-attach-closure
 *    spec 留下的、尚未走 inject 路径的组件。任何新增组件必须走 inject 路径。
 *    每完成一个的迁移就从清单删一条，清单只许缩短不许增长。
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

// ─── 基础设施 ────────────────────────────────────────────────────────────────

const WP_ROOT = path.resolve(__dirname, '../..')

/** 剔注释（与 dCycleVoucherMappedPrefixes.spec.ts / samplingAccountCodeSource.spec.ts 同口径） */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^[ \t]*\/\/.*$/gm, '')
    .replace(/([^:])\/\/[^\n'"`]*$/gm, '$1')
}

/** 递归收集 .vue 文件 */
function collectVue(dir: string): string[] {
  const out: string[] = []
  if (!fs.existsSync(dir)) return out
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) out.push(...collectVue(p))
    else if (e.name.endsWith('.vue')) out.push(p)
  }
  return out
}

interface VueFile {
  /** 相对于 WP_ROOT 的路径（正斜杠） */
  rel: string
  /** 绝对路径 */
  full: string
  /** 剔注释后的源码 */
  src: string
}

/** 全量 .vue 文件（剔注释） */
const ALL_VUE: VueFile[] = collectVue(WP_ROOT).map((f) => ({
  rel: path.relative(WP_ROOT, f).replace(/\\/g, '/'),
  full: f,
  src: stripComments(fs.readFileSync(f, 'utf-8')),
}))

// ─── 分类 ────────────────────────────────────────────────────────────────────

/** 含 pullSamplesForWorkpaper 的文件 */
const PULL_FILES = ALL_VUE.filter((v) => v.src.includes('pullSamplesForWorkpaper'))

/** 含 GtVoucherSamplingEngine（且不是引擎自身定义文件） 的文件 */
const ENGINE_FILES = ALL_VUE.filter(
  (v) =>
    v.src.includes('GtVoucherSamplingEngine') &&
    !v.rel.includes('voucher-sampling/GtVoucherSamplingEngine.vue'),
)

/** inject('tbSourceCodes') 的正则 */
const RE_INJECT_TB = /inject\s*[<(][\s\S]{0,80}['"]tbSourceCodes['"]/

/**
 * 🎉 棘轮冻结清单：已清零。全部 33 个组件均已迁移至 inject('tbSourceCodes') 路径。
 *
 * 历史：来自 voucher-sampling-account-scope-and-attach-closure spec 的遗留组件，
 * 原先调用 xxxQueryCodes() 无参走兜底码。现已全部接入 inject 路径。
 *
 * 🔴 只许保持为空。新增凭证检查组件必须走 inject 路径，否则守卫 1/2 会打红。
 */
const NOT_YET_MIGRATED: ReadonlySet<string> = new Set([
  // 🎉 全部已迁移至 inject('tbSourceCodes') 路径。清单清零。
  // 新增凭证检查组件必须走 inject 路径，否则守卫 1/2 会打红。
])

/**
 * 完全排除的文件（不参与 inject 检查）——这些文件含 pullSamplesForWorkpaper 或
 * GtVoucherSamplingEngine 关键字但不是真正的消费端。
 */
const EXCLUDED_FILES: ReadonlySet<string> = new Set([
  // 引擎自身定义
  'voucher-sampling/GtVoucherSamplingEngine.vue',
  // L8 截止测试只在注释/说明中引用 GtVoucherSamplingEngine，不是实际消费端
  'l8/cutoff/L8TabCutoffTest.vue',
  // E1 银行流水核对：业务上只查银行存款 1002，不用 e1QueryCodes 全集（有意设计，非遗漏）
  'e1/E1TabBankFlowReconcile.vue',
  // G6 ECL：已有 inject('tbSourceCodes')，但 template 含 CSS `/*` 字面量导致 stripComments 误吞代码段。
  // 下方守卫 5 有专项直接断言绕开 strip 验证。
  'g6-other-bond-investment-ecl/voucher/G6TabVoucherCheck.vue',
])

// ─── 守卫一：pullSamplesForWorkpaper 消费端必须有 inject ─────────────────────

describe('守卫 1：pullSamplesForWorkpaper 消费端必须有 inject("tbSourceCodes")（R2.1/R3.1）', () => {
  it('扫描面非空（否则全部断言空转）', () => {
    expect(
      PULL_FILES.length,
      '扫不到任何 pullSamplesForWorkpaper 消费端',
    ).toBeGreaterThan(10)
  })

  it('已迁移的组件全部有 inject("tbSourceCodes")', () => {
    const migrated = PULL_FILES.filter(
      (v) => !NOT_YET_MIGRATED.has(v.rel) && !EXCLUDED_FILES.has(v.rel),
    )
    const missing: string[] = []
    for (const v of migrated) {
      if (!RE_INJECT_TB.test(v.src)) {
        missing.push(v.rel)
      }
    }
    expect(
      missing,
      '以下文件使用 pullSamplesForWorkpaper 但缺少 inject("tbSourceCodes")。\n' +
        '如果是新组件 → 必须走 inject 路径。\n' +
        '如果是遗漏 → 加入 NOT_YET_MIGRATED（只许临时，须尽快迁移）。\n\n  ' +
        missing.join('\n  '),
    ).toEqual([])
  })

  it('🔴 棘轮：NOT_YET_MIGRATED 清单只许减少不许增加', () => {
    // 冻结清单长度。每迁移一个就 -1，同时更新此数字。
    // 🔴 如果这个断言打红，说明有人往清单加了新条目 ⇒ 拒绝。
    expect(
      NOT_YET_MIGRATED.size,
      '棘轮上限 0。清单已清零，只许保持为空。\n' +
        '新增凭证检查组件必须走 inject 路径，不得往清单加条目。',
    ).toBeLessThanOrEqual(0)
  })

  it('NOT_YET_MIGRATED 中的文件确实存在且含 pullSamplesForWorkpaper 或 GtVoucherSamplingEngine', () => {
    const phantom: string[] = []
    for (const rel of NOT_YET_MIGRATED) {
      const found = ALL_VUE.find((v) => v.rel === rel)
      if (!found) {
        phantom.push(`${rel} — 文件不存在（路径陈旧？）`)
        continue
      }
      if (
        !found.src.includes('pullSamplesForWorkpaper') &&
        !found.src.includes('GtVoucherSamplingEngine')
      ) {
        phantom.push(`${rel} — 既无 pullSamplesForWorkpaper 也无 GtVoucherSamplingEngine`)
      }
    }
    expect(
      phantom,
      'NOT_YET_MIGRATED 中有无效条目（文件不存在或已不含抽凭调用）：\n  ' +
        phantom.join('\n  '),
    ).toEqual([])
  })

  it('NOT_YET_MIGRATED 中的文件如果已有 inject("tbSourceCodes") 则应移出清单', () => {
    const graduated: string[] = []
    for (const rel of NOT_YET_MIGRATED) {
      const found = ALL_VUE.find((v) => v.rel === rel)
      if (found && RE_INJECT_TB.test(found.src)) {
        graduated.push(rel)
      }
    }
    expect(
      graduated,
      '以下文件已有 inject("tbSourceCodes") 却仍在 NOT_YET_MIGRATED 中，应移出：\n  ' +
        graduated.join('\n  '),
    ).toEqual([])
  })
})

// ─── 守卫二：GtVoucherSamplingEngine 消费端必须有 inject ─────────────────────

describe('守卫 2：GtVoucherSamplingEngine 消费端必须有 inject("tbSourceCodes")（R2.1）', () => {
  it('扫描面非空', () => {
    expect(
      ENGINE_FILES.length,
      '扫不到任何 GtVoucherSamplingEngine 消费端',
    ).toBeGreaterThan(10)
  })

  it('已迁移的消费端全部有 inject("tbSourceCodes")', () => {
    const migrated = ENGINE_FILES.filter(
      (v) => !NOT_YET_MIGRATED.has(v.rel) && !EXCLUDED_FILES.has(v.rel),
    )
    const missing: string[] = []
    for (const v of migrated) {
      if (!RE_INJECT_TB.test(v.src)) {
        missing.push(v.rel)
      }
    }
    expect(
      missing,
      '以下 GtVoucherSamplingEngine 消费端缺少 inject("tbSourceCodes")。\n' +
        '新组件必须走 inject 路径；遗漏的旧组件应加入 NOT_YET_MIGRATED 并尽快迁移。\n\n  ' +
        missing.join('\n  '),
    ).toEqual([])
  })
})

// ─── 守卫三：pullSamplesForWorkpaper 第四参数禁止硬编码数字数组字面量 ────────

describe('守卫 3：pullSamplesForWorkpaper 的 accountPrefixes 参数不得为字面量数组（R2.2）', () => {
  /**
   * 匹配 pullSamplesForWorkpaper(..., ['1122', '2203']) 形态的硬编码。
   * 注意：[samplingAccountCode] 或 [k2CheckAccountCode.value] 是合法的（标识符而非数字字面量）。
   * 只匹配第四参数为 ['数字...'] 形态的调用。
   */
  const RE_LITERAL_ARRAY_ARG =
    /pullSamplesForWorkpaper\s*\([^)]*,\s*\[\s*['"][0-9][^'"]*['"]/

  it('扫描面非空', () => {
    expect(PULL_FILES.length).toBeGreaterThan(10)
  })

  it('没有文件使用硬编码数字数组作为 accountPrefixes', () => {
    const offenders: string[] = []
    for (const v of PULL_FILES) {
      if (RE_LITERAL_ARRAY_ARG.test(v.src)) {
        // 提取具体调用行供排查
        const lines = v.src.split('\n')
        const badLines = lines
          .filter((l) => RE_LITERAL_ARRAY_ARG.test(l))
          .map((l) => l.trim())
        offenders.push(`${v.rel}\n      ${badLines.join('\n      ')}`)
      }
    }
    expect(
      offenders,
      'pullSamplesForWorkpaper 的第四参数使用了硬编码数字数组。\n' +
        '应改用 AccountScope 函数的返回值（如 dSlotQueryCodes / k8QueryCodes 等）。\n\n  ' +
        offenders.join('\n  '),
    ).toEqual([])
  })

  it('🔴 反向自检：判据能抓到硬编码字面量', () => {
    const bad = "pullSamplesForWorkpaper(pid, year, wpId, ['1122', '2203'])"
    expect(RE_LITERAL_ARRAY_ARG.test(bad)).toBe(true)
  })

  it('🔴 反向自检：标识符数组不被误判', () => {
    // [samplingAccountCode] — 标识符而非数字字面量
    const good1 = 'pullSamplesForWorkpaper(pid, year, wpId, [samplingAccountCode])'
    expect(RE_LITERAL_ARRAY_ARG.test(good1)).toBe(false)

    // K1_ACCOUNT_PREFIXES — 变量引用
    const good2 = 'pullSamplesForWorkpaper(pid, year, wpId, K1_ACCOUNT_PREFIXES)'
    expect(RE_LITERAL_ARRAY_ARG.test(good2)).toBe(false)

    // [k2CheckAccountCode.value] — .value 访问
    const good3 =
      'pullSamplesForWorkpaper(pid, year, wpId, [k2CheckAccountCode.value])'
    expect(RE_LITERAL_ARRAY_ARG.test(good3)).toBe(false)
  })
})

// ─── 守卫四：F2_INVENTORY_ACCOUNT_CODES 不在 :account-code 绑定中使用 ───────

describe('守卫 4：F2_INVENTORY_ACCOUNT_CODES 不得作为 :account-code 绑定值（R2.3）', () => {
  it('没有 GtVoucherSamplingEngine 消费端在 :account-code 中引用 F2_INVENTORY_ACCOUNT_CODES', () => {
    const offenders: string[] = []
    const RE_BIND_F2 =
      /:account-code\s*=\s*"[^"]*F2_INVENTORY_ACCOUNT_CODES[^"]*"/
    for (const v of ENGINE_FILES) {
      if (RE_BIND_F2.test(v.src)) {
        offenders.push(v.rel)
      }
    }
    expect(
      offenders,
      'F2_INVENTORY_ACCOUNT_CODES 不得直接作为 :account-code 绑定值。\n' +
        '应改用 f2InventoryQueryCodes(injectedSrc) 走三层降级。\n\n  ' +
        offenders.join('\n  '),
    ).toEqual([])
  })

  it('🔴 反向自检：判据能抓到 F2_INVENTORY_ACCOUNT_CODES', () => {
    const bad =
      '<GtVoucherSamplingEngine :account-code="F2_INVENTORY_ACCOUNT_CODES.join(\',\')" />'
    expect(
      /:account-code\s*=\s*"[^"]*F2_INVENTORY_ACCOUNT_CODES[^"]*"/.test(bad),
    ).toBe(true)
  })
})

// ─── 守卫五：stripComments 误判的已排除文件直接验证（不经 strip） ────────────

describe('守卫 5：stripComments 误判的已排除文件直接验证（不经 strip）', () => {
  it('G6TabVoucherCheck.vue（ECL）raw 源码包含 inject("tbSourceCodes")', () => {
    const raw = fs.readFileSync(
      path.join(WP_ROOT, 'g6-other-bond-investment-ecl/voucher/G6TabVoucherCheck.vue'),
      'utf-8',
    )
    // 直接检查 raw 源码（不经 stripComments），绕开 template 里 /* 误判
    expect(raw).toMatch(/inject[\s\S]{0,120}['"]tbSourceCodes['"]/)
  })
})

// ─── 守卫六：剔注释器自检 ───────────────────────────────────────────────────

describe('剔注释器自检（防假绿/假红）', () => {
  it('HTML 注释被剔除', () => {
    const src = '<!-- inject("tbSourceCodes") -->\nconst x = 1'
    expect(stripComments(src)).not.toContain('tbSourceCodes')
    expect(stripComments(src)).toContain('const x = 1')
  })

  it('块注释被剔除', () => {
    const src = '/* inject("tbSourceCodes") */\nconst x = 1'
    expect(stripComments(src)).not.toContain('tbSourceCodes')
    expect(stripComments(src)).toContain('const x = 1')
  })

  it('行注释被剔除', () => {
    const src = '// inject("tbSourceCodes")\nconst x = 1'
    expect(stripComments(src)).not.toContain('tbSourceCodes')
    expect(stripComments(src)).toContain('const x = 1')
  })

  it('代码中的 inject 调用不被剔除', () => {
    const src =
      "const _injectedTbSrc = inject<Ref<any> | null>('tbSourceCodes', null)"
    expect(stripComments(src)).toContain("inject")
    expect(stripComments(src)).toContain("'tbSourceCodes'")
  })

  it('🔴 剔注释不剔代码后半段（URL 里的 // 不能按行注释处理）', () => {
    const src = "const url = 'https://example.com/api'"
    expect(stripComments(src)).toContain('https://example.com/api')
  })
})
