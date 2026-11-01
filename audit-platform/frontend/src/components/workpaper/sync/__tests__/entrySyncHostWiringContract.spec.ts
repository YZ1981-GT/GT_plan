/**
 * 宿主接线契约 —— 三条在 task 3.5 分批迁移中被实证**必要**的不变量。
 *
 * spec workpaper-html-onlyoffice-bidirectional-writeback-closure（AC 1.4 / 1.5 / 12.8）。
 *
 * ═══ 为什么这三条必须有守卫 ═══════════════════════════════════════════════
 *
 * ① **门控了就必须给原因**。接单源意味着 `capability` 非 bidirectional 的 entry 不再显示
 *    模式开关。若宿主没挂 `GtEntrySyncCapabilityNotice`，用户看到的只是「开关没了」且
 *    没有任何解释 —— 比改线前显示一个打不开的假开关**更糟**，也直接违反 AC 1.5。
 *    迁移中现算到的真实情况：94 个宿主已挂，**24 个没挂**（其中 19 个是 pending），
 *    还有 3 个宿主（B22B×2 / B22C）只 `import` 了它、模板里一次都没用。
 *
 * ② **门与原因必须指同一条 entry**。否则「原因讲的是 entry A、开关按的是 entry B」，
 *    用户看到的解释与实际行为对不上，而两边都「有」，静态扫描一律看不出。
 *
 * ③ **entry id 必须能在 generated manifest 里兑现**。宿主里的 entry id 是字面量，
 *    manifest 才是生成真源（`hostPath` 字段直接指向宿主文件）。两边会各自漂移 ——
 *    task 3.5 第七批一次性引入 23 个这样的字面量，没有这条守卫就等于 23 个待漂移点。
 *    允许的例外只有一种且可验证：本宿主的 entry 是**非独立 / inherited** 时，可以用它的
 *    `parentEntryId`（裁决本来就继承自父 entry；`D4TabMarginMonthly.vue` 即此情形，
 *    它的 notice 从一开始就用父 id，门与原因因此才一致）。
 *
 * 🔴 标签截取**必须引号感知**：`/<el-segmented[\s\S]{0,400}?>/` 会在属性值内部的 `>` 处
 *    提前截断（模板里常见 `@change="(v: any) => f(v)"`）。现算全仓 349 个 `el-segmented`
 *    里 26 个被这样截断，其中 3 个因此**改变判定**（`GtB60Bundle.vue` 两处 +
 *    `GtJ1EmployeeCompensation.vue` 一处的模式开关被残片判成「不是模式开关」）⇒ 会放过
 *    未门控的开关，还会把这两个宿主误列进「没有模式开关、可以豁免」。
 */
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { WORKPAPER_SYNC_MANIFEST } from '../workpaperSyncManifest.generated'

const SRC = resolve(__dirname, '../../../..')
const WP = resolve(SRC, 'components/workpaper')
/** 披露组件自己也用 readiness，但它是基础设施（entryId 由 prop 传入），不是宿主。 */
const NOTICE_COMPONENT = 'GtEntrySyncCapabilityNotice.vue'

/** 引号感知地截出 `<el-segmented ...>` 开标签全文。 */
function segmentedOpenTags(text: string): string[] {
  const out: string[] = []
  let i = 0
  for (;;) {
    i = text.indexOf('<el-segmented', i)
    if (i < 0) break
    let j = i + '<el-segmented'.length
    let quote: string | null = null
    while (j < text.length) {
      const ch = text[j]
      if (quote) {
        if (ch === quote) quote = null
      } else if (ch === '"' || ch === "'") {
        quote = ch
      } else if (ch === '>') {
        j += 1
        break
      }
      j += 1
    }
    out.push(text.slice(i, j))
    i = j
  }
  return out
}

function walkVue(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (name === '__tests__' || name === 'node_modules') continue
    if (statSync(full).isDirectory()) walkVue(full, out)
    else if (name.endsWith('.vue') && name !== NOTICE_COMPONENT) out.push(full)
  }
  return out
}

interface WiredHost {
  readonly rel: string
  readonly text: string
  /** gate 的 entryId 表达式求出的字面值（常量会被解引用）。 */
  readonly gateEntryIds: string[]
  /** 模板里 notice 用的 entry 字面值。 */
  readonly noticeEntryIds: string[]
  readonly noticeMounted: boolean
  readonly gatedTagCount: number
}

/** 把 entryId 表达式解成字面值：直接字面量，或本文件内 `const X = '…'`。 */
function literalOf(expr: string, text: string): string | null {
  const trimmed = expr.trim().replace(/,$/, '')
  if (/^['"]/.test(trimmed)) return trimmed.slice(1, -1)
  const m = new RegExp(`const\\s+${trimmed.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*=\\s*['"]([^'"]+)['"]`)
    .exec(text)
  return m ? m[1] : null
}

const wiredHosts: WiredHost[] = walkVue(WP)
  .map((file) => ({ rel: relative(SRC, file).split('\\').join('/'), text: readFileSync(file, 'utf-8') }))
  .filter(({ text }) => text.includes('useEntrySyncReadiness'))
  .map(({ rel, text }) => {
    const gateEntryIds = [...text.matchAll(/entryId:\s*\(\)\s*=>\s*([^,\n]+)/g)]
      .map((m) => literalOf(m[1], text))
      .filter((v): v is string => v !== null)
    const noticeEntryIds = [
      ...[...text.matchAll(/<GtEntrySyncCapabilityNotice[\s\S]{0,300}?entry-id="(xlsx\/[^"]+)"/g)]
        .map((m) => m[1]),
      ...[...text.matchAll(/<GtEntrySyncCapabilityNotice[\s\S]{0,300}?:entry-id="([A-Za-z0-9_.]+)"/g)]
        .map((m) => literalOf(m[1], text))
        .filter((v): v is string => v !== null),
    ]
    return {
      rel,
      text,
      gateEntryIds,
      noticeEntryIds,
      // 🔴 必须看模板里有没有**真的用**，只看文件里出现过这个字符串会把「只 import 不挂」
      //    判成已挂（B22B×2 / B22C 三个宿主正是这种形态）。
      noticeMounted: /<GtEntrySyncCapabilityNotice[\s/>]/.test(text),
      gatedTagCount: segmentedOpenTags(text)
        .filter((tag) => /v-if="[^"]*showModeSwitch[^"]*"/.test(tag)).length,
    }
  })

const manifestByHost = new Map<string, typeof WORKPAPER_SYNC_MANIFEST[number][]>()
for (const entry of WORKPAPER_SYNC_MANIFEST) {
  const list = manifestByHost.get(entry.hostPath) ?? []
  list.push(entry)
  manifestByHost.set(entry.hostPath, list)
}
const manifestIds = new Set(WORKPAPER_SYNC_MANIFEST.map((e) => e.entryId))

describe('宿主接线契约', () => {
  it('分母非空，且标签截取器没退化（否则下面三条恒绿）', () => {
    expect(wiredHosts.length, '一个已接单源的宿主都算不出 ⇒ 扫描器失锚').toBeGreaterThan(50)
    expect(
      wiredHosts.some((h) => h.gatedTagCount > 0),
      '没有任何宿主的 segmented 带 showModeSwitch 门 ⇒ 判据看不到对象',
    ).toBe(true)
    // 截取器退化成只匹配标签名时，长度会全部等于 '<el-segmented'.length
    const tags = wiredHosts.flatMap((h) => segmentedOpenTags(h.text))
    expect(tags.length).toBeGreaterThan(50)
    expect(
      Math.max(...tags.map((t) => t.length)),
      '截出的标签全都极短 ⇒ 截取器只匹配到标签名，属性读不到',
    ).toBeGreaterThan(40)
  })

  it('截取器引号感知：内联箭头函数里的 `>` 不得当成标签结束', () => {
    const tricky =
      '<el-segmented :model-value="m" @change="(v: any) => f(v)" :options="opts" />\n<p>x</p>'
    const tags = segmentedOpenTags(tricky)
    expect(tags.length).toBe(1)
    expect(tags[0].endsWith('/>')).toBe(true)
    expect(tags[0]).toContain(':options')
    expect(tags[0]).not.toContain('<p>')
    // 朴素正则在同一输入上必须确实截断（否则本用例失锚）
    expect(tricky.match(/<el-segmented[\s\S]{0,400}?>/)?.[0]).not.toContain(':options')
  })

  const gatedHosts = wiredHosts.filter((h) => h.gatedTagCount > 0)

  it('① 门控了模式开关的宿主，必须挂能力披露（只隐藏不给原因 = 更糟）', () => {
    expect(gatedHosts.length, '一个门控宿主都没有 ⇒ 判据看不到对象').toBeGreaterThan(50)
    const missing = gatedHosts.filter((h) => !h.noticeMounted).map((h) => h.rel)
    expect(missing, `这些宿主会隐藏模式开关却不给任何原因：\n${missing.join('\n')}`).toEqual([])
  })

  it('② 门与原因必须指同一条 entry', () => {
    const mismatched = gatedHosts
      .filter((h) => h.noticeEntryIds.length > 0)
      .filter((h) => !h.gateEntryIds.every((id) => h.noticeEntryIds.includes(id)))
      .map((h) => `${h.rel}  gate=${h.gateEntryIds.join(',')}  notice=${h.noticeEntryIds.join(',')}`)
    expect(mismatched, `门与原因指向不同 entry：\n${mismatched.join('\n')}`).toEqual([])
  })

  it('③ entry id 必须能在 generated manifest 里兑现（宿主自己的，或 inherited 的父 entry）', () => {
    const offenders: string[] = []
    let inheritedExceptions = 0
    let siblingHostExceptions = 0
    for (const host of wiredHosts) {
      const hostPath = `audit-platform/frontend/src/${host.rel}`
      const own = manifestByHost.get(hostPath) ?? []
      const hostDir = host.rel.slice(0, host.rel.lastIndexOf('/'))
      for (const id of host.gateEntryIds) {
        if (!manifestIds.has(id)) {
          offenders.push(`${host.rel}: ${id} 不在 manifest 里`)
          continue
        }
        if (own.some((e) => e.entryId === id)) continue
        // 例外一：本宿主的 entry 是非独立 / inherited，用它的 parentEntryId
        //（裁决本来就继承自父 entry；`D4TabMarginMonthly.vue` 即此情形，它的 notice
        // 从一开始就用父 id，门与原因因此才一致）。
        const inherited = own.find((e) => !e.independentEntry && e.parentEntryId === id)
        if (inherited) {
          inheritedExceptions += 1
          continue
        }
        // 例外二：manifest 里**没有**以本文件为 hostPath 的 entry（Tab 子组件未被生成器
        // 单独登记），此时用**同目录父宿主**的 entry。两个条件都可验证：
        //   ① 本文件确实没有自己的 entry；② 该 id 的 hostPath 与本文件同目录。
        // 这不是「写个理由就豁免」—— 条件不成立时下面照样记违规。
        if (own.length === 0) {
          const owner = WORKPAPER_SYNC_MANIFEST.find((e) => e.entryId === id)
          const ownerDir = owner
            ? owner.hostPath
              .replace('audit-platform/frontend/src/', '')
              .slice(0, owner.hostPath.replace('audit-platform/frontend/src/', '').lastIndexOf('/'))
            : null
          if (ownerDir !== null && ownerDir === hostDir) {
            siblingHostExceptions += 1
            continue
          }
        }
        offenders.push(
          `${host.rel}: 用 ${id}，但 manifest 给本文件的是 ` +
            `${own.map((e) => e.entryId).join(',') || '（无）'}`,
        )
      }
    }
    expect(offenders, `entry id 与 manifest 不符：\n${offenders.join('\n')}`).toEqual([])
    // 两个例外分支都必须**真的被走到过**，否则它们只是两段永不执行的死代码，
    // 下一次有人改坏时也不会有人发现它们其实没在守什么。
    expect(inheritedExceptions, 'inherited 例外分支从未命中 ⇒ 它在守什么？').toBeGreaterThan(0)
    expect(siblingHostExceptions, '同目录父宿主例外分支从未命中 ⇒ 它在守什么？').toBeGreaterThan(0)
  })

  /**
   * ④ 宿主注释里点名的守卫文件必须真实存在。
   *
   * 🔴 这条是被真实缺陷逼出来的：批 7 的迁移脚本在 **33 个**宿主里写下
   * 「由 `sync/__tests__/entryIdLiteralsMatchManifest.spec.ts` 钉住两边一致」，
   * 而那个文件从头到尾**不存在** —— 真正守这条不变量的是本文件的判据 ③。
   *
   * 指向不存在的守卫比不写更糟：读代码的人会以为该不变量已有人守，于是不再去建
   * 真正的判据。这与本 spec 反复抓到的「注释骗过扫描器」是同一形态，只是方向相反
   * （那次是注释让扫描器**以为有**鉴权，这次是注释让人**以为有**守卫）。
   */
  it('④ 宿主注释点名的 sync 守卫文件必须存在（不得指向不存在的判据）', () => {
    const REF = /sync\/__tests__\/([A-Za-z0-9_.-]+\.spec\.ts)/g
    const offenders: string[] = []
    let referenced = 0
    for (const host of wiredHosts) {
      for (const match of host.text.matchAll(REF)) {
        referenced += 1
        const target = join(__dirname, match[1])
        if (!existsSync(target)) offenders.push(`${host.rel} → ${match[1]}`)
      }
    }
    // 分母非空：一条引用都没有时本判据恒绿，那就不是「没问题」而是「没看到对象」。
    expect(referenced, '没有任何宿主点名 sync 守卫 ⇒ 判据失锚').toBeGreaterThan(0)
    expect(
      offenders,
      `这些宿主的注释点名了不存在的守卫文件：\n${offenders.join('\n')}`,
    ).toEqual([])
  })
})
