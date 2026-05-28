/**
 * editorDialogConfig 配置完整性 + 三个 helper 行为校验 [V3 Req 12.1.4]
 *
 * - getDialogByKey / getDialogsByCycle / getDialogByTrigger 行为
 * - TEMPLATE_DIALOGS 元数据完整性（key/title/cycle 非空 + 无重复 key + triggers 非空）
 */
import { describe, it, expect } from 'vitest'
import {
  TEMPLATE_DIALOGS,
  getDialogByKey,
  getDialogsByCycle,
  getDialogByTrigger,
} from '../editorDialogConfig'

describe('editorDialogConfig — config integrity', () => {
  it('每个条目都有非空 key/title/cycle', () => {
    for (const d of TEMPLATE_DIALOGS) {
      expect(d.key, `key empty in ${JSON.stringify(d)}`).toBeTruthy()
      expect(d.title, `title empty for ${d.key}`).toBeTruthy()
      expect(d.cycle, `cycle empty for ${d.key}`).toBeTruthy()
      expect(d.cycle.length).toBe(1)
    }
  })

  it('triggers 非空且每项均为非空字符串', () => {
    for (const d of TEMPLATE_DIALOGS) {
      expect(Array.isArray(d.triggers)).toBe(true)
      expect(d.triggers.length, `${d.key} triggers empty`).toBeGreaterThan(0)
      for (const t of d.triggers) {
        expect(typeof t).toBe('string')
        expect(t.length).toBeGreaterThan(0)
      }
    }
  })

  it('TEMPLATE_DIALOGS 内 key 唯一', () => {
    const keys = TEMPLATE_DIALOGS.map((d) => d.key)
    const unique = new Set(keys)
    expect(unique.size).toBe(keys.length)
  })

  it('componentPath 指向 components/workpaper/ 下的 .vue 文件', () => {
    for (const d of TEMPLATE_DIALOGS) {
      expect(d.componentPath).toMatch(/^@\/components\/workpaper\/[A-Za-z]+\.vue$/)
    }
  })

  it('dialogStateKey 必须非空（用于映射 useCycleDialogs）', () => {
    for (const d of TEMPLATE_DIALOGS) {
      expect(d.dialogStateKey, `${d.key} missing dialogStateKey`).toBeTruthy()
    }
  })
})

describe('getDialogByKey', () => {
  it('返回已知 key 对应的条目', () => {
    const dialog = getDialogByKey('depreciationCalc')
    expect(dialog).toBeDefined()
    expect(dialog?.cycle).toBe('H')
    expect(dialog?.title).toContain('折旧')
  })

  it('未知 key 返回 undefined', () => {
    expect(getDialogByKey('not-a-real-dialog-key')).toBeUndefined()
    expect(getDialogByKey('')).toBeUndefined()
  })
})

describe('getDialogsByCycle', () => {
  it('返回 F 循环至少 1 项且每项 cycle === "F"', () => {
    const fDialogs = getDialogsByCycle('F')
    expect(fDialogs.length).toBeGreaterThan(0)
    for (const d of fDialogs) {
      expect(d.cycle).toBe('F')
    }
  })

  it('小写 cycle 输入会归一化匹配（"f" -> "F"）', () => {
    const upper = getDialogsByCycle('F')
    const lower = getDialogsByCycle('f')
    expect(lower.length).toBe(upper.length)
  })

  it('不存在的循环返回空数组（cycle "Z"）', () => {
    expect(getDialogsByCycle('Z')).toEqual([])
  })

  it('空字符串返回空数组', () => {
    expect(getDialogsByCycle('')).toEqual([])
  })

  it('H 循环包含折旧测算 + 减值测算', () => {
    const hDialogs = getDialogsByCycle('H')
    const keys = hDialogs.map((d) => d.key)
    expect(keys).toContain('depreciationCalc')
    expect(keys).toContain('assetImpairment')
  })
})

describe('getDialogByTrigger', () => {
  it('按精确 trigger 查找条目（cycle:H -> 第一个 H 循环条目）', () => {
    const hit = getDialogByTrigger('cycle:H')
    expect(hit).toBeDefined()
    expect(hit?.cycle).toBe('H')
  })

  it('按 wp_code 触发器查找具体条目', () => {
    const hit = getDialogByTrigger('wp_code:H1-12')
    expect(hit?.key).toBe('depreciationCalc')
  })

  it('不存在的 trigger 返回 undefined', () => {
    expect(getDialogByTrigger('cycle:not-a-cycle')).toBeUndefined()
  })
})
