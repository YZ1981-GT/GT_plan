/**
 * 日历日计算与时区无关：同一组输入在 UTC+8 / UTC / UTC-5 三个时区下结果相同。
 *
 * 子进程里设 TZ 才能真正换时区（Node 启动后改 process.env.TZ 不一定生效），
 * 所以把被测函数的源码拷进子进程执行。
 */
import { describe, expect, it } from 'vitest'
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { calendarDayIndex, calendarDaysBetween, localDateIso } from '../calendarDays'

const SRC = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../calendarDays.ts'), 'utf-8')

/** 去掉 TS 类型标注后在指定时区的子进程里求值（只用于这几个函数，标注形态固定）。 */
function runInTz(tz: string, body: string): unknown {
  const js = SRC
    .replace(/export /g, '')
    .replace(/: string \| Date \| null \| undefined/g, '')
    .replace(/\): number \| null \{/g, ') {')
    .replace(/\): string \{/g, ') {')
    .replace(/at: Date = new Date\(\)/g, 'at = new Date()')
    .replace(/let date: Date/g, 'let date')
  const script = `${js}\nconsole.log(JSON.stringify((() => { ${body} })()))`
  const out = execFileSync(process.execPath, ['-e', script], { env: { ...process.env, TZ: tz }, encoding: 'utf-8' })
  return JSON.parse(out.trim())
}

describe('calendarDays', () => {
  it('日期字符串按年月日取，不经时区换算', () => {
    expect(calendarDaysBetween('2025-07-01', '2025-10-15')).toBe(106)
    expect(calendarDaysBetween('2025-01-01', '2025-07-01')).toBe(181)
    expect(calendarDaysBetween('2025-03-01', '2025-03-01')).toBe(0)
    expect(calendarDaysBetween('2025-03-02', '2025-03-01')).toBe(-1)
    expect(calendarDayIndex('')).toBeNull()
    expect(calendarDayIndex('不是日期')).toBeNull()
  })

  it('new Date("YYYY-MM-DD")（UTC 零点）按 UTC 日期，与字符串同口径', () => {
    expect(calendarDayIndex(new Date('2025-07-01'))).toBe(calendarDayIndex('2025-07-01'))
  })

  it('当前时刻取本地日期（不是 UTC 日期）', () => {
    const at = new Date(2025, 9, 15, 7, 30) // 本地 10-15 07:30
    expect(calendarDayIndex(at)).toBe(calendarDayIndex('2025-10-15'))
    expect(localDateIso(at)).toBe('2025-10-15')
  })

  for (const tz of ['Asia/Shanghai', 'UTC', 'America/New_York']) {
    it(`${tz}：本地早上 7 点的「今天」与逾期天数都按本地日历`, () => {
      const got = runInTz(tz, `
        const at = new Date(2025, 9, 15, 7, 0)
        return {
          today: localDateIso(at),
          overdue: calendarDaysBetween('2025-07-01', at),
          fromDateObj: calendarDaysBetween(new Date('2025-07-01'), at),
        }`)
      expect(got).toEqual({ today: '2025-10-15', overdue: 106, fromDateObj: 106 })
    })
  }
})
