/**
 * 披露 Tab 自动同步覆盖率守卫
 *
 * 背景：附注不跟随底稿内容的直接原因之一 —— 披露 Tab 改了数据不会自动同步到附注，
 * 用户必须记得手动点「同步到附注」。机制 `useDisclosureAutoSync` 早已存在
 * （spec `disclosure-note-linkage-completion` Req1），缺的是**接入覆盖**与**正确的触发条件**。
 *
 * 本守卫钉死三件事：
 * 1. 有同步能力（含 `syncToDisclosureNotes`）的 Tab 必须接入 `useDisclosureAutoSync`
 * 2. 接入了就必须真的调 `scheduleAutoSync`（不许只 import / 只建实例 —— E1 曾如此）
 * 3. 触发条件不得**只**监听提示横幅类状态（F2 曾只 watch `dataUpdatedVisible`，
 *    那是「上游数据已更新」的横幅可见性，用户自己改数据一律不触发）
 *
 * 未接入者进 `NOT_WIRED_ALLOWLIST` 且**必须写 reason**，随推广批次逐个移出
 * （对齐 `disclosure-columns-coverage` 的 allowlist 范式）。
 *
 * Spec: .kiro/specs/disclosure-note-follow-actual-content/ R1 / Task 4.3
 */
import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

const WP_ROOT = resolve(__dirname, '..')

/** 只监听这类状态不算接入：它们是「上游变化」提示，不代表用户编辑 */
const BANNER_ONLY_SOURCES = ['dataUpdatedVisible', 'upstreamUpdatedVisible', 'staleVisible']

/**
 * 🔴 **完全缺失同步链路**的披露 Tab（当前 **54 个**）。
 *
 * 📌 计数修正史：先按 emit 计入链路 → 低估为 27；改为不计 emit → 64；
 * 再加**委托解析**（`resolveDelegate`）→ 60（G10/G11 的 Listed/SOE 各是 15~21 行薄壳，
 * `v-bind="$props"` 委托给已带完整链路的 Base，属虚报）；
 * 批 1 补齐 G8/G9/G12 → 54；再补 G5 → **52**。
 *
 * 这批比「没接自动同步」严重得多：它们**没有 `syncToDisclosureNotes`、不打
 * `sync-from-workpaper` 端点、也不 emit 给父组件** —— 披露数据只停在
 * `checklist_responses`，附注模块永远拿不到。抽查 N2/L2 确认 `disclosure-notes`
 * 端点 0 命中。这是全库 569 个附注章节仍是 legacy 快照的根本原因之一。
 *
 * 补齐一个 Tab 需要：sheet→section 映射（`XNoteSectionMap.ts`）+ 载荷构建器
 * （`buildXSyncPayload`）+ `columns` 定义 + `syncToDisclosureNotes` + 自动同步接线，
 * 工作量对齐 F2/K1 的单循环量级 → 见 spec Task 12（按循环分批）。
 *
 * 本清单只允许**变短**：新增披露 Tab 必须自带同步链路。
 */
const MISSING_SYNC_PATH: readonly string[] = [
  // D2（1）
  'D2TabDisclosure.vue',
  // F4（2）
  'F4TabDisclosureListed.vue',
  'F4TabDisclosureSOE.vue',
  // G10 / G11：Listed+SOE 是薄壳，链路在 Base 里 → 由 `resolveDelegate` 解析，不算缺口
  // G12 已补齐（spec disclosure-sync-path-buildout Task 2.8）
  // G4 已补齐（Task 2.1）；G5 已补齐（Task 2.2）
  // G6 已补齐（Task 2.3）：组件原是自造的 7 个虚构小节 + `generateRows()` 137 行
  //   `成本项目N`，已按权威模板 `backend/wp_templates/G/G6 其他债权投资.xlsx`
  //   重写为 6 小节 / 14 张表后接链路。
  // G8 已补齐（Task 2.4）；G9 已补齐（Task 2.5，Base + 2 个薄壳一并转绿）
  // H4（1）
  'H4TabDisclosureSoe.vue',
  // H5（1）
  'H5TabDisclosureListed.vue',
  // H6（2）
  'H6TabDisclosureListed.vue',
  'H6TabDisclosureSoe.vue',
  // H7（2）
  'H7TabDisclosureListed.vue',
  'H7TabDisclosureSoe.vue',
  // J2（2）
  'J2TabDisclosureListed.vue',
  'J2TabDisclosureSoe.vue',
  // L2（2）
  'L2TabDisclosureListed.vue',
  'L2TabDisclosureSoe.vue',
  // L4（2）
  'L4TabDisclosureListed.vue',
  'L4TabDisclosureSoe.vue',
  // L5（2）
  'L5TabDisclosureListed.vue',
  'L5TabDisclosureSoe.vue',
  // L6（2）
  'L6TabDisclosureListed.vue',
  'L6TabDisclosureSoe.vue',
  // L7（2）
  'L7TabDisclosureListed.vue',
  'L7TabDisclosureSoe.vue',
  // L8（2）
  'L8TabDisclosureListed.vue',
  'L8TabDisclosureSoe.vue',
  // M1（2）
  'M1TabDisclosureListed.vue',
  'M1TabDisclosureSoe.vue',
  // M10（2）
  'M10TabDisclosureListed.vue',
  'M10TabDisclosureSoe.vue',
  // M2（2）
  'M2TabDisclosureListed.vue',
  'M2TabDisclosureSoe.vue',
  // M3（1）
  'M3TabDisclosureListed.vue',
  // M4（2）
  'M4TabDisclosureListed.vue',
  'M4TabDisclosureSoe.vue',
  // M5（2）
  'M5TabDisclosureListed.vue',
  'M5TabDisclosureSoe.vue',
  // M6（2）
  'M6TabDisclosureListed.vue',
  'M6TabDisclosureSoe.vue',
  // M7（2）
  'M7TabDisclosureListed.vue',
  'M7TabDisclosureSoe.vue',
  // M8（2）
  'M8TabDisclosureListed.vue',
  'M8TabDisclosureSoe.vue',
  // M9（2）
  'M9TabDisclosureListed.vue',
  'M9TabDisclosureSoe.vue',
  // N2（2）
  'N2TabDisclosureListed.vue',
  'N2TabDisclosureSoe.vue',
  // N3（1）
  'N3TabDisclosure.vue',
  // N4（2）
  'N4TabDisclosureListed.vue',
  'N4TabDisclosureSoe.vue',
  // N5（2）
  'N5TabDisclosureListed.vue',
  'N5TabDisclosureSoe.vue',
]

/**
 * 尚未接入自动同步的 Tab —— 每条**必须**有 reason。
 *
 * ⚠️ 2026-07-30 重新统计后本表**应为空**：实测 `syncToDisclosureNotes && !scheduleAutoSync`
 * 的真实缺口为 **0**。此前 60 条「未接入」全是没有同步链路的 Tab（已移入
 * `MISSING_SYNC_PATH`）或用别的 syncFn 的 Tab（25 个，合规）。保留本表结构以便
 * 将来新增 Tab 时登记。
 */
const NOT_WIRED_ALLOWLIST: Record<string, string> = {
  // 实测为空：真实缺口（有同步能力却未接自动同步）= 0
}

interface TabInfo {
  name: string
  path: string
  src: string
  hasSyncFn: boolean
  hasImport: boolean
  hasCall: boolean
  /** 薄壳委托目标（`<Base variant="x" v-bind="$props" />`）的绝对路径，无则 null */
  delegatesTo: string | null
}

/**
 * 识别「变体薄壳」：整个 `<template>` 只有一个组件标签且带 `v-bind="$props"`。
 *
 * 🔴 这类文件（G9/G10/G11 的 Listed/SOE，15~21 行）本身没有任何同步代码，
 * 同步链路在被委托的 `XTabDisclosureBase.vue` 里 → 直接按文件判定会**虚报缺口**。
 * 返回委托目标的绝对路径（从 import 语句解析），非薄壳返回 null。
 */
function resolveDelegate(src: string, path: string): string | null {
  const tpl = /<template>([\s\S]*?)<\/template>/.exec(src)?.[1] ?? ''
  const tags = tpl.replace(/<!--[\s\S]*?-->/g, '').match(/<([A-Z][\w.]*)\b/g) ?? []
  if (tags.length !== 1) return null
  const tag = tags[0].slice(1)
  if (!/v-bind="\$props"/.test(tpl)) return null
  const imp = new RegExp(`import\\s+${tag}\\s+from\\s+['"](.+?)['"]`).exec(src)
  if (!imp) return null
  const dir = path.replace(/[\\/][^\\/]+$/, '')
  return resolve(dir, imp[1])
}

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry)
    if (statSync(p).isDirectory()) {
      if (entry === '__tests__' || entry === 'node_modules') continue
      walk(p, out)
    } else if (/TabDisclosure.*\.vue$/.test(entry)) {
      out.push(p)
    }
  }
  return out
}

const TABS: TabInfo[] = walk(WP_ROOT).map((p) => {
  const src = readFileSync(p, 'utf8')
  return {
    name: p.split(/[\\/]/).pop() as string,
    path: p,
    src,
    hasSyncFn: src.includes('syncToDisclosureNotes'),
    hasImport: src.includes('useDisclosureAutoSync'),
    hasCall: src.includes('scheduleAutoSync('),
    delegatesTo: resolveDelegate(src, p),
  }
})

/** 提取包含 scheduleAutoSync 的 watch 的监听源片段 */
function watchSourcesFor(src: string): string[] {
  const out: string[] = []
  const re = /watch\(\s*([\s\S]{0,400}?)\s*,\s*\(/g
  let m: RegExpExecArray | null
  while ((m = re.exec(src))) {
    const after = src.slice(m.index, m.index + 900)
    if (after.includes('scheduleAutoSync')) out.push(m[1])
  }
  return out
}

describe('披露 Tab 自动同步覆盖率', () => {
  it('扫描到足量披露 Tab（防止 glob 失效导致守卫空转）', () => {
    expect(TABS.length).toBeGreaterThan(140)
  })

  it('接入了 useDisclosureAutoSync 就必须真的调 scheduleAutoSync（不许只 import 或只建实例）', () => {
    const halfWired = TABS.filter((t) => t.hasImport && !t.hasCall).map((t) => t.name)
    expect(
      halfWired,
      `以下 Tab import 了 useDisclosureAutoSync 却从不调 scheduleAutoSync（等于没接，E1 曾如此）：${halfWired.join(', ')}`,
    ).toEqual([])
  })

  it('有 syncToDisclosureNotes 的 Tab 必须接入自动同步（未接入需登记 allowlist + reason）', () => {
    const unwired = TABS.filter((t) => t.hasSyncFn && !t.hasCall).map((t) => t.name)
    const undeclared = unwired.filter((n) => !(n in NOT_WIRED_ALLOWLIST))
    expect(
      undeclared,
      `以下 Tab 有同步能力但未接自动同步且未登记 allowlist：${undeclared.join(', ')}`,
    ).toEqual([])
  })

  it('allowlist 每条都必须有非空 reason', () => {
    const blank = Object.entries(NOT_WIRED_ALLOWLIST)
      .filter(([, r]) => !r || !r.trim())
      .map(([k]) => k)
    expect(blank, `allowlist 缺 reason：${blank.join(', ')}`).toEqual([])
  })

  it('allowlist 不得残留已接入的 Tab（推广完成后必须移出）', () => {
    const stale = Object.keys(NOT_WIRED_ALLOWLIST).filter((n) => {
      const t = TABS.find((x) => x.name === n)
      return t?.hasCall
    })
    expect(stale, `以下 Tab 已接入但仍在 allowlist 中，请移出：${stale.join(', ')}`).toEqual([])
  })

  it('真实缺口（有同步能力却未接自动同步）应为 0', () => {
    const gap = TABS.filter((t) => t.hasSyncFn && !t.hasCall).map((t) => t.name)
    expect(gap, `出现新的自动同步缺口：${gap.join(', ')}`).toEqual([])
  })
})

describe('披露 Tab 同步链路完整性', () => {
  /** 有任何同步痕迹：自有 syncFn / 别的 syncFn 走 autoSync / 打端点 / emit 给父组件 */
  /**
   * 真正的同步链路：自有 syncFn / 别的 syncFn 走 autoSync / 直打同步端点。
   *
   * 🔴 **emit 不算**（2026-07-30 实证）：37 个 emit 型披露 Tab 的事件只有
   * `navigate`(27) / `imported`(7) / `disclosure:note-text-updated`(5)。前两者与同步无关；
   * 后者的消费方 `useNoteRefresh.onDisclosureNoteTextUpdated` 仅调 `fetchDetail`
   * 刷新界面，且首行 `if (!currentNote.value) return`（附注页未打开直接返回）——
   * **完全不推数据落库**。此前把 emit 计入链路，导致缺口被低估为 27。
   */
  function hasOwnSyncPath(t: TabInfo): boolean {
    return (
      t.hasSyncFn ||
      t.hasCall ||
      t.src.includes('sync-from-workpaper') ||
      t.src.includes('syncFromWorkpaper')
    )
  }

  /**
   * 含**委托解析**：薄壳（`v-bind="$props"` 单标签）继承被委托 Base 的链路判定。
   * 深度上限 3 防环。
   */
  function hasAnySyncPath(t: TabInfo, depth = 0): boolean {
    if (hasOwnSyncPath(t)) return true
    if (depth >= 3 || !t.delegatesTo) return false
    const target = TABS.find((x) => x.path === t.delegatesTo)
    if (!target) {
      // 委托目标不在披露 Tab 集合内（命名不含 TabDisclosure）→ 直接读文件判定
      try {
        const src = readFileSync(t.delegatesTo, 'utf8')
        return (
          src.includes('syncToDisclosureNotes') ||
          src.includes('scheduleAutoSync(') ||
          src.includes('sync-from-workpaper')
        )
      } catch {
        return false
      }
    }
    return hasAnySyncPath(target, depth + 1)
  }

  it('MISSING_SYNC_PATH 清单只允许变短（新增披露 Tab 必须自带同步链路）', () => {
    const actual = TABS.filter((t) => !hasAnySyncPath(t)).map((t) => t.name).sort()
    const declared = [...MISSING_SYNC_PATH].sort()
    const unexpected = actual.filter((n) => !declared.includes(n))
    expect(
      unexpected,
      `以下披露 Tab 完全没有同步到附注的链路且未登记：${unexpected.join(', ')}。` +
        `披露数据会停在 checklist_responses，附注模块永远拿不到。`,
    ).toEqual([])
  })

  it('MISSING_SYNC_PATH 中已补齐链路的条目必须移出', () => {
    const fixed = MISSING_SYNC_PATH.filter((n) => {
      const t = TABS.find((x) => x.name === n)
      return t && hasAnySyncPath(t)
    })
    expect(fixed, `以下 Tab 已有同步链路，请从 MISSING_SYNC_PATH 移出：${fixed.join(', ')}`).toEqual(
      [],
    )
  })

  it('MISSING_SYNC_PATH 每条都能在代码库中找到对应文件（防清单腐烂）', () => {
    const missing = MISSING_SYNC_PATH.filter((n) => !TABS.some((t) => t.name === n))
    expect(missing, `清单中的文件已不存在，请更新：${missing.join(', ')}`).toEqual([])
  })

  it('缺链路数量记录在案（49 个；批1 G 循环 11 条全部补齐：G4/G5/G6/G8/G9/G12）', () => {
    expect(MISSING_SYNC_PATH.length).toBe(49)
  })

  it('委托解析生效：薄壳继承 Base 的链路判定（G10/G11 不得被虚报）', () => {
    for (const name of [
      'G10TabDisclosureListed.vue',
      'G10TabDisclosureSOE.vue',
      'G11TabDisclosureListed.vue',
      'G11TabDisclosureSOE.vue',
    ]) {
      const t = TABS.find((x) => x.name === name)!
      expect(t.delegatesTo, `${name} 应被识别为薄壳`).toBeTruthy()
      expect(hasOwnSyncPath(t), `${name} 自身不应有同步代码`).toBe(false)
      expect(hasAnySyncPath(t), `${name} 应通过委托继承 Base 的链路`).toBe(true)
    }
  })

  // 反向自检用替身：不依赖某个真实循环的当前状态（G9 曾用于此，补齐后会假红）
  it('委托解析不得误判：委托目标无链路时仍算缺口', () => {
    const stub: TabInfo = {
      name: 'StubTabDisclosureListed.vue',
      path: join(WP_ROOT, 'stub', 'StubTabDisclosureListed.vue'),
      src: '<template><Base variant="listed" v-bind="$props" /></template>',
      hasSyncFn: false,
      hasImport: false,
      hasCall: false,
      delegatesTo: join(WP_ROOT, 'stub', 'BaseWithoutSync.vue'), // 不存在 → 读不到 → false
    }
    expect(hasOwnSyncPath(stub)).toBe(false)
    expect(hasAnySyncPath(stub)).toBe(false)
  })

  it('委托识别只认单标签 + v-bind="$props"（多标签模板不算薄壳）', () => {
    expect(
      resolveDelegate(
        '<template><A v-bind="$props" /><B /></template>\nimport A from "./A.vue"',
        join(WP_ROOT, 'x.vue'),
      ),
    ).toBeNull()
    expect(
      resolveDelegate(
        '<template><A variant="listed" /></template>\nimport A from "./A.vue"',
        join(WP_ROOT, 'x.vue'),
      ),
    ).toBeNull()
  })

  /**
   * 🔴 平台级：禁止 `_xxxMounted` 一次性防护（2026-07-30 浏览器实测确认是 bug）。
   *
   * ```ts
   * let _xxxMounted = false
   * watch([...], () => { if (!_xxxMounted) { _xxxMounted = true; return }
   *                     autoSync.scheduleAutoSync(syncToDisclosureNotes) })
   * ```
   *
   * 防护的消耗时机取决于「数据是否已加载」：首次挂载时 `allResponses` 异步填充让
   * computed 变化、watch 触发一次 → 防护被消耗（符合设计意图）；但**切走再切回**时
   * 数据已在内存、computed 不变、watch 不触发 → 防护未被消耗 → 吞掉用户回到本页后的
   * **第一次真实编辑**（实测：`checklist_responses` 已写入但 `_last_sync_at` 不变）。
   * Vue `watch` 默认 `immediate:false`，挂载本身不触发，故该防护从一开始就不必要。
   *
   * 清除脚本：`backend/scripts/fix/fix_disclosure_mounted_guard.py`（带 `--check`）。
   */
  const MOUNTED_GUARD_RE = /if \(!(_\w*Mounted)\)\s*\{\s*\1\s*=\s*true;?\s*return\s*\}/
  const MOUNTED_DECL_RE = /\blet _\w*Mounted\s*=\s*false/

  it('禁止 `_xxxMounted` 一次性防护（会吞掉「切走再切回后的第一次编辑」）', () => {
    const offenders = TABS.filter((t) => MOUNTED_GUARD_RE.test(t.src)).map((t) => t.name)
    expect(
      offenders,
      `以下 Tab 仍有一次性防护：${offenders.join(', ')}；` +
        `请跑 python backend/scripts/fix/fix_disclosure_mounted_guard.py`,
    ).toEqual([])
  })

  it('一次性防护的声明也不得残留（死变量）', () => {
    const offenders = TABS.filter((t) => MOUNTED_DECL_RE.test(t.src)).map((t) => t.name)
    expect(offenders).toEqual([])
  })

  it('自检替身：守卫正则能命中真实写法（防正则失效导致空转）', () => {
    const sample = `let _l1SoeMounted = false
watch([a], () => {
  if (!_l1SoeMounted) { _l1SoeMounted = true; return }
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
})`
    expect(MOUNTED_GUARD_RE.test(sample)).toBe(true)
    expect(MOUNTED_DECL_RE.test(sample)).toBe(true)
    // 不误伤：正常的 onMounted 钩子与普通布尔变量
    expect(MOUNTED_GUARD_RE.test('onMounted(() => { load() })')).toBe(false)
    expect(MOUNTED_DECL_RE.test('let isMountedRef = false')).toBe(false)
  })

  it('自动同步的触发条件不得只监听提示横幅类状态', () => {
    const offenders: string[] = []
    for (const t of TABS) {
      if (!t.hasCall) continue
      const sources = watchSourcesFor(t.src)
      if (sources.length === 0) continue // 非 watch 触发（如 persistXxx 内直接调）→ 合规
      // 若**全部** watch 源都只是横幅类状态 → 视为未真正接入
      const allBannerOnly = sources.every((s) => {
        const hasBanner = BANNER_ONLY_SOURCES.some((b) => s.includes(b))
        const hasOther = /[A-Za-z_$][\w$]*/.test(s.replace(new RegExp(BANNER_ONLY_SOURCES.join('|'), 'g'), ''))
        return hasBanner && !hasOther
      })
      if (allBannerOnly) offenders.push(t.name)
    }
    expect(
      offenders,
      `以下 Tab 的自动同步只监听「上游已更新」横幅，用户自己改数据不会触发（F2 曾如此）：${offenders.join(', ')}`,
    ).toEqual([])
  })
})

describe('F2 披露 Tab 自动同步触发条件（定点回归）', () => {
  const listed = TABS.find((t) => t.name === 'F2TabDisclosureListed.vue')!
  const soe = TABS.find((t) => t.name === 'F2TabDisclosureSoe.vue')!

  it('两个 Tab 都已接入', () => {
    expect(listed.hasCall).toBe(true)
    expect(soe.hasCall).toBe(true)
  })

  it.each([
    ['上市', 'listed'],
    ['国企', 'soe'],
  ])('%s Tab 不再只监听 dataUpdatedVisible', (_label, key) => {
    const t = key === 'listed' ? listed : soe
    expect(t.src).not.toMatch(/watch\(dataUpdatedVisible,\s*\(v\)\s*=>\s*\{\s*if \(v\) autoSync\.scheduleAutoSync/)
  })

  it('上市 Tab 监听全部 8 个表格数据源 + 6 个文本域', () => {
    const sources = watchSourcesFor(listed.src).join(' ')
    for (const s of [
      'section1Rows', 'section2Rows', 'section2QualRows',
      's3EndRows', 's3PriorRows', 's5Rows', 's6Rows', 's7Rows', 'drRows',
      'noteCategory', 'noteNrv', 'noteProvision', 's4BorrowText', 's4AmortText', 'noteRe',
    ]) {
      expect(sources, `上市 Tab 自动同步未监听 ${s}`).toContain(s)
    }
  })

  it('国企 Tab 监听全部表格数据源 + 5 个文本域', () => {
    const sources = watchSourcesFor(soe.src).join(' ')
    for (const s of [
      'section1Rows', 'section2Rows', 'drRows',
      'noteCategory', 's3BorrowText', 's4AmortText', 'noteText', 'landNote',
    ]) {
      expect(sources, `国企 Tab 自动同步未监听 ${s}`).toContain(s)
    }
  })

  it.each([
    ['上市', 'listed'],
    ['国企', 'soe'],
  ])('%s Tab 不得用 mounted 一次性防护（会吞掉「切走再切回后的第一次编辑」）', (_label, key) => {
    // 🔴 浏览器实测（2026-07-30）：防护的消耗时机取决于「数据是否已加载」。
    // 首次挂载时 allResponses 异步填充 → computed 变化 → 消耗掉防护（符合设计意图）；
    // 但切走再切回时 allResponses 已有值 → computed 不变 → watch 不触发 → 防护未消耗
    // → 吞掉用户回到本页后的第一次真实编辑（实测：checklist_responses 已存但附注
    // `_last_sync_at` 不变；同一挂载内再改一次才同步）。
    // Vue watch 默认 immediate:false，挂载本身不触发，故无需防护。
    const t = key === 'listed' ? listed : soe
    expect(t.src).not.toMatch(/_f2\w*SyncMounted/)
    expect(t.src).not.toMatch(/if \(![_a-zA-Z]*Mounted\)\s*\{[^}]*return[^}]*\}\s*\n?\s*autoSync\.scheduleAutoSync/)
  })
})
