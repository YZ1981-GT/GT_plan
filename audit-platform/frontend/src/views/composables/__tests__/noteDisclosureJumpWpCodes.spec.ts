/**
 * 附注↔底稿跳转的 `wpCode` 联合类型必须覆盖本文件里所有 `wpCode:` 字面量。
 * 原先漏了 D2 / H5 / K2~K10 / L3 / L5 / L7 / M2~M7 / M9 / M10 共 22 个实际在用的族码，
 * 类型报错只是表征 —— 真正的风险是新增族码时没人发现漏登记。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const SRC = readFileSync('src/views/composables/noteDisclosureJump.ts', 'utf-8')

describe('noteDisclosureJump wpCode 联合类型', () => {
  it('本文件所有 wpCode: 字面量都在联合里', () => {
    const unionLine = SRC.match(/wpCode\?: (.+)/)?.[1] ?? ''
    const union = new Set(Array.from(unionLine.matchAll(/'([\w-]+)'/g), (m) => m[1]))
    const used = new Set(Array.from(SRC.matchAll(/wpCode: '([\w-]+)'/g), (m) => m[1]))
    expect(used.size).toBeGreaterThan(20)
    expect([...used].filter((c) => !union.has(c))).toEqual([])
  })
})
