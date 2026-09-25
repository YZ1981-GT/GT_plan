/**
 * d567 spec Task 1 — D6/D7 底稿目录聚合键缺陷修复判据
 *
 * 缺陷：`D6TabIndex.vue` / `D7TabIndex.vue` 的完成度判定读了四个**无写入方**的聚合键
 * （`D6-6-rows` / `D6-8-rows` / `D7-4-rows` / `D7-7-rows`），真实写入方用的是
 * block/single/credit/debit/period/post 分区键 ⇒ 这四张底稿完成度恒显示「未填」。
 *
 * 🔴 判据纪律（裁决 G4 + design Property 10）：
 *   1. 以**真实写入方的键**播种 payload ⇒ 断言判为已填；
 *   2. **不镜像错误键名** —— 判据直接 import 并跑生产纯函数 `isD6SheetComplete` /
 *      `isD7SheetComplete`（组件从同一处 import），而非在测试里复刻一份键映射
 *      （D1 那次「单测镜像同款错误锚点、恒绿而生产恒死」是同源事故）；
 *   3. 变异（改回聚合键播种）⇒ 判为未填，即 Property 10/11 的红侧。
 *
 * @spec d567-sync-coverage-via-row-table-engine — Task 1 / Requirements 5.1 5.2 5.3
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { isD6SheetComplete } from '../composables/d6SheetLabels'
import { isD7SheetComplete } from '../composables/d7SheetLabels'

type RemarkEntry = { remark?: string } | undefined

/** 一条 checklist 载荷：remark 存 JSON 行数组（与生产 hasJsonRows 一致） */
function rows(n = 1): { remark: string } {
  return { remark: JSON.stringify(Array.from({ length: n }, (_, i) => ({ id: i + 1 }))) }
}

function m(entries: [string, RemarkEntry][]): Map<string, RemarkEntry> {
  return new Map(entries)
}

describe('d567 Task 1: isD6SheetComplete 聚合键缺陷修复', () => {
  it('D6-6 双区 block1 有行 ⇒ 已填（Requirement 5.1）', () => {
    expect(isD6SheetComplete('D6-6', m([['D6-6-block1-rows', rows()]]))).toBe(true)
  })

  it('D6-6 双区仅 block2 有行也 ⇒ 已填（任一有行，Requirement 5.1）', () => {
    expect(isD6SheetComplete('D6-6', m([['D6-6-block2-rows', rows()]]))).toBe(true)
  })

  it('D6-8 真实写入方键 single ⇒ 已填（Requirement 5.1）', () => {
    expect(isD6SheetComplete('D6-8', m([['D6-8-single-rows', rows()]]))).toBe(true)
  })

  it('🔴 变异：改回旧聚合键 D6-6-rows 播种 ⇒ 未填（Property 10 红侧）', () => {
    expect(isD6SheetComplete('D6-6', m([['D6-6-rows', rows()]]))).toBe(false)
  })

  it('🔴 变异：改回旧聚合键 D6-8-rows 播种 ⇒ 未填（Property 10 红侧）', () => {
    expect(isD6SheetComplete('D6-8', m([['D6-8-rows', rows()]]))).toBe(false)
  })

  it('空 Map ⇒ 全部未填（下限）', () => {
    expect(isD6SheetComplete('D6-6', m([]))).toBe(false)
    expect(isD6SheetComplete('D6-8', m([]))).toBe(false)
  })
})

describe('d567 Task 1: isD7SheetComplete 聚合键缺陷修复', () => {
  it('D7-4 双区 credit 有行 ⇒ 已填（Requirement 5.2）', () => {
    expect(isD7SheetComplete('D7-4', m([['D7-4-credit-rows', rows()]]))).toBe(true)
  })

  it('D7-4 双区仅 debit 有行也 ⇒ 已填（任一有行，Requirement 5.2）', () => {
    expect(isD7SheetComplete('D7-4', m([['D7-4-debit-rows', rows()]]))).toBe(true)
  })

  it('D7-7 双区 period 有行 ⇒ 已填（Requirement 5.2）', () => {
    expect(isD7SheetComplete('D7-7', m([['D7-7-period-rows', rows()]]))).toBe(true)
  })

  it('D7-7 双区仅 post 有行也 ⇒ 已填（任一有行，Requirement 5.2）', () => {
    expect(isD7SheetComplete('D7-7', m([['D7-7-post-rows', rows()]]))).toBe(true)
  })

  it('🔴 变异：改回旧聚合键 D7-4-rows 播种 ⇒ 未填（Property 10 红侧）', () => {
    expect(isD7SheetComplete('D7-4', m([['D7-4-rows', rows()]]))).toBe(false)
  })

  it('🔴 变异：改回旧聚合键 D7-7-rows 播种 ⇒ 未填（Property 10 红侧）', () => {
    expect(isD7SheetComplete('D7-7', m([['D7-7-rows', rows()]]))).toBe(false)
  })

  it('空 Map ⇒ 全部未填（下限）', () => {
    expect(isD7SheetComplete('D7-4', m([]))).toBe(false)
    expect(isD7SheetComplete('D7-7', m([]))).toBe(false)
  })
})

/**
 * Property 11：四个聚合键在前端生产源码零残留引用（除注释外）。
 * 这里做静态断言 —— isD*SheetComplete 的行为已由上面覆盖，本用例守护
 * 「未来有人把某个 case 又改回聚合键」会立刻红。
 */
describe('d567 Task 1: Property 11 聚合键零残留（行为守卫）', () => {
  it('四个聚合键单独播种都不能让对应底稿判为已填', () => {
    expect(isD6SheetComplete('D6-6', m([['D6-6-rows', rows()]]))).toBe(false)
    expect(isD6SheetComplete('D6-8', m([['D6-8-rows', rows()]]))).toBe(false)
    expect(isD7SheetComplete('D7-4', m([['D7-4-rows', rows()]]))).toBe(false)
    expect(isD7SheetComplete('D7-7', m([['D7-7-rows', rows()]]))).toBe(false)
  })
})

/**
 * Property 11 静态侧（需求 5.4）：四个聚合键在 D6/D7 完成度判定源码里零 hasJsonRows 调用。
 * 扫真实源码文件而非镜像 —— 未来有人把某 case 又改回 `hasJsonRows(m, 'D6-6-rows')` 会立刻红。
 * 注释里提及旧键名（说明用途）不算残留，故只匹配 `hasJsonRows(...'KEY'...)` 调用形态。
 */
describe('d567 Task 1: Property 11 聚合键源码零残留（静态守卫，需求 5.4）', () => {
  const COMPOSABLES = path.resolve(__dirname, '../composables')
  const AGGREGATE_KEYS = ['D6-6-rows', 'D6-8-rows', 'D7-4-rows', 'D7-7-rows'] as const
  const SRC_FILES = [
    path.join(COMPOSABLES, 'd6SheetLabels.ts'),
    path.join(COMPOSABLES, 'd7SheetLabels.ts'),
  ]

  for (const file of SRC_FILES) {
    for (const key of AGGREGATE_KEYS) {
      it(`${path.basename(file)} 不含 hasJsonRows(..., '${key}') 调用`, () => {
        const src = fs.readFileSync(file, 'utf-8')
        // 匹配 hasJsonRows(<任意>, 'KEY') 或 "KEY"，允许中间空白
        const callRe = new RegExp(
          `hasJsonRows\\s*\\([^)]*['"]${key.replace(/-/g, '\\-')}['"]`,
        )
        expect(callRe.test(src), `${path.basename(file)} 残留了聚合键 ${key} 的调用`).toBe(false)
      })
    }
  }

  it('反向自检：正则能匹配到聚合键调用形态（防空转）', () => {
    const callRe = /hasJsonRows\s*\([^)]*['"]D6-6-rows['"]/
    expect(callRe.test(`return hasJsonRows(m, 'D6-6-rows')`)).toBe(true)
  })
})
