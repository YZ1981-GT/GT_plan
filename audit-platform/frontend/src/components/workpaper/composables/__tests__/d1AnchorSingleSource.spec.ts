/**
 * D1 锚点单一真源源码守卫
 *
 * Spec: .kiro/specs/d1-extraction-chain-completion/ (Property 4 / Requirement 8.1, 8.2)
 *
 * ## 为什么需要源码级守卫
 *
 * D1 曾有四处各自拼 `D1-adj-*` 字面量，其中三处拼错、**全平台无写入方**：
 *   * `useD1Disclosure` 读 `D1-adj-gross-bank-current-audited` / `D1-adj-baddebt-*`
 *   * `useD1InventoryCount` / `useD1RelatedPartyCheck` 读 `D1-adj-notes-receivable-current-audited`
 * 两类错因：① `-current-audited` 是 computed 列、从不持久化；② `baddebt` ≠ 写入方的 `bd`。
 * 三处都不报错、不崩、类型检查通不出，且它们的单测**镜像了同款错误字面量**播种 fixture
 * → 测试恒绿、生产恒死（披露①分类表 / D1-10 监盘 / D1-11 关联方的账面余额一直是 0）。
 *
 * 故：**除 `d1AdjudicationModel.ts` 外，任何 D1 生产源码都不得出现 `D1-adj-` 字面量**，
 * 一律经 `d1AdjAnchor` / `d1AdjAnchorByRowKey` / 导出常量构造。
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { resolve, join, basename } from 'node:path'
import { describe, expect, it } from 'vitest'

const WORKPAPER_DIR = resolve(__dirname, '../..')
const MODEL_FILE = 'd1AdjudicationModel.ts'

/** 去掉块注释、行注释与注释里的示例（守卫注释本身会写反例，不去掉必误报）。 */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

/** 递归收集 D1 相关生产源码（排除 __tests__）。 */
function collectD1Sources(): Array<{ path: string; name: string; src: string }> {
  const out: Array<{ path: string; name: string; src: string }> = []
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry)
      if (statSync(full).isDirectory()) {
        if (entry === '__tests__' || entry === 'node_modules') continue
        walk(full)
        continue
      }
      if (!/\.(ts|vue)$/.test(entry)) continue
      if (!/^(d1|useD1|D1)/.test(entry)) continue
      out.push({ path: full, name: entry, src: readFileSync(full, 'utf-8') })
    }
  }
  walk(WORKPAPER_DIR)
  return out
}

describe('D1 锚点单一真源（源码扫描）', () => {
  const sources = collectD1Sources()

  it('扫描到足量 D1 源文件（防 glob 失效导致断言空转）', () => {
    expect(sources.length).toBeGreaterThan(20)
    expect(sources.some((f) => f.name === MODEL_FILE)).toBe(true)
    expect(sources.some((f) => f.name === 'useD1Adjudication.ts')).toBe(true)
    expect(sources.some((f) => f.name === 'D1TabDisclosure.vue')).toBe(true)
  })

  it('🔴 除 d1AdjudicationModel.ts 外，代码里不得出现 D1-adj- 字面量', () => {
    const offenders: string[] = []
    for (const f of sources) {
      if (f.name === MODEL_FILE) continue
      const code = stripComments(f.src)
      if (code.includes('D1-adj-')) {
        const lines = code
          .split('\n')
          .map((l, i) => [i + 1, l] as const)
          .filter(([, l]) => l.includes('D1-adj-'))
          .map(([i, l]) => `${f.name}:${i}: ${l.trim().slice(0, 120)}`)
        offenders.push(...lines)
      }
    }
    expect(offenders, `发现模块外锚点字面量：\n${offenders.join('\n')}`).toEqual([])
  })

  it('🔴 反向自检：stripComments 未过度剥离（模型文件仍含锚点前缀）', () => {
    const model = sources.find((f) => f.name === MODEL_FILE)!
    expect(stripComments(model.src)).toContain('D1-adj-')
  })

  it('🔴 反向自检：stripComments 确实剥掉了注释里的反例', () => {
    const withComment = `const a = 1 // 旧写法 D1-adj-baddebt-bank-current-audited\nconst b = 2`
    expect(stripComments(withComment)).not.toContain('D1-adj-')
    const blockComment = `/* D1-adj-notes-receivable-current-audited */\nconst c = 3`
    expect(stripComments(blockComment)).not.toContain('D1-adj-')
  })

  it('🔴 已废弃锚点不得在任何 D1 源码（含注释外）重现', () => {
    const DEAD = [
      'D1-adj-baddebt-',
      'D1-adj-notes-receivable-',
      '-current-audited',
      '-prior-audited',
    ]
    const offenders: string[] = []
    for (const f of sources) {
      const code = stripComments(f.src)
      for (const dead of DEAD) {
        if (code.includes(dead)) offenders.push(`${f.name}: ${dead}`)
      }
    }
    expect(offenders, `废弃锚点重现：\n${offenders.join('\n')}`).toEqual([])
  })

  it('消费跨表金额的 D1 composable 必须 import 共享模型', () => {
    const MUST_IMPORT = [
      'useD1Adjudication.ts',
      'useD1Disclosure.ts',
      'useD1CrossSheet.ts',
      'useD1InventoryCount.ts',
      'useD1RelatedPartyCheck.ts',
    ]
    for (const name of MUST_IMPORT) {
      const f = sources.find((x) => basename(x.path) === name)
      expect(f, `未找到 ${name}`).toBeTruthy()
      expect(f!.src, `${name} 未接共享模型`).toMatch(/from '\.\/d1AdjudicationModel'/)
    }
  })
})
