/**
 * 后端时间串解析（spec attachment-confirmation-evidence-loop 浏览器走查发现）
 *
 * 函证附件抽屉的上传时间显示「NaN-NaN-NaN」：接口返回 `…+00:00`，前端手写
 * `ts.includes('Z') ? ts : ts + 'Z'` 拼成 `…+00:00Z` ⇒ Invalid Date。同一写法另有 4 处，统一改走 `parseServerTime`。
 */
import { describe, expect, it } from 'vitest'
import { parseServerTime } from '../formatters'
import { FRONTEND_SRC, readSource, stripJsComments, toSrcRelative, walkSourceFiles } from '@/__tests__/_helpers/frontendSourceScan'

describe('parseServerTime', () => {
  it.each([
    ['2026-10-28T03:05:05.073276+00:00', '2026-10-28T03:05:05.073Z'],
    ['2026-10-28T03:05:05Z', '2026-10-28T03:05:05.000Z'],
    ['2026-10-28T11:05:05+08:00', '2026-10-28T03:05:05.000Z'],
    ['2026-10-28T03:05:05', '2026-10-28T03:05:05.000Z'], // 裸时间按 UTC
  ])('%s', (input, iso) => {
    expect(parseServerTime(input).toISOString()).toBe(iso)
  })

  it('解析不了的串给 Invalid Date（调用方据此显示原文 / 占位）', () => {
    expect(Number.isNaN(parseServerTime('不是时间').getTime())).toBe(true)
  })
})

/** 只看末尾有没有 Z 就补 Z 的写法：遇到 `±hh:mm` 必拼坏 */
const BAD_IDIOM = /\.(?:endsWith|includes)\(\s*['"]Z['"]\s*\)\s*\?\s*(\w+)\s*:\s*\1\s*\+\s*['"]Z['"]/

describe('全仓不再手拼时区后缀', () => {
  it('扫描器认得出这种写法（自检）', () => {
    expect(BAD_IDIOM.test("new Date(ts.includes('Z') ? ts : ts + 'Z')")).toBe(true)
    expect(BAD_IDIOM.test("new Date(iso.endsWith('Z') ? iso : iso + 'Z')")).toBe(true)
    expect(BAD_IDIOM.test('parseServerTime(ts)')).toBe(false)
  })

  it('没有文件再用「只认 Z 就补 Z」解析后端时间', () => {
    const hits: string[] = []
    let scanned = 0
    for (const abs of walkSourceFiles(FRONTEND_SRC)) {
      if (!/\.(vue|ts)$/.test(abs) || /\.(spec|test)\.ts$/.test(abs)) continue
      scanned++
      if (BAD_IDIOM.test(stripJsComments(readSource(abs)))) hits.push(toSrcRelative(abs))
    }
    expect(scanned).toBeGreaterThan(1000) // 扫描面没塌缩
    expect(hits, `请改用 utils/formatters 的 parseServerTime：${hits.join('、')}`).toEqual([])
  })
})
