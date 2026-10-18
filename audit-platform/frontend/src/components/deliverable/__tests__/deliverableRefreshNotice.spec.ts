/**
 * 交付件章节增量刷新：确认文案与结果提示（spec deliverable-trio-generation-accuracy Task 16b）
 *
 * 钉住：结果提示按后端返回如实说（原前端不看返回值，跳过 / 未执行也提示「已刷新」）。
 */
import { describe, expect, it } from 'vitest'

import {
  headCodes,
  overwritePrompt,
  sectionRefreshPrompt,
  staleRefreshPrompt,
  summarizeRefresh,
} from '../deliverableRefreshNotice'

const base = {
  version_no: null,
  refreshed: [] as string[],
  skipped: [] as string[],
  requires_confirm: false,
  pending_confirm_sections: [] as string[],
  messages: [] as string[],
}

describe('summarizeRefresh', () => {
  it('落了新版本、无提醒 ⇒ success，写明节数与版本号', () => {
    expect(summarizeRefresh({ ...base, version_no: 15, refreshed: ['八、1', '八、2'] })).toEqual({
      kind: 'success', title: '刷新完成', lines: ['已刷新 2 节（八、1、八、2），已另存为第 15 版'],
    })
  })

  it('落了新版本、有跳过 ⇒ warning，先列已刷新再列原因', () => {
    const n = summarizeRefresh({ ...base, version_no: 3, refreshed: ['八、1'], skipped: ['八、2'], messages: ['八、2：原因'] })
    expect(n.kind).toBe('warning')
    expect(n.title).toBe('刷新完成，部分章节未刷新')
    expect(n.lines).toEqual(['已刷新 1 节（八、1），已另存为第 3 版', '八、2：原因'])
  })

  it('没有落版本 ⇒ 不说「已刷新」，列后端原因；后端没给原因时按跳过节数说明', () => {
    expect(summarizeRefresh({ ...base, skipped: ['八、1'], messages: ['八、1：原因'] })).toEqual({
      kind: 'warning', title: '未刷新', lines: ['八、1：原因'],
    })
    expect(summarizeRefresh({ ...base, skipped: ['八、1'] }).lines).toEqual(['1 节未刷新（八、1）'])
  })

  it('refreshed 非空但 version_no 为空（异常形态）⇒ 不当成成功', () => {
    expect(summarizeRefresh({ ...base, refreshed: ['八、1'], messages: ['x'] }).kind).toBe('warning')
  })

  it('什么都没有（没有过期章节）⇒ info；缺字段 / null 不抛', () => {
    expect(summarizeRefresh(base)).toEqual({ kind: 'info', title: '无需刷新', lines: ['没有需要刷新的过期章节'] })
    expect(summarizeRefresh(null).kind).toBe('info')
    expect(summarizeRefresh({}).kind).toBe('info')
  })
})

describe('确认文案', () => {
  it('章节号缩写最多 6 个（与后端 _head 同口径）', () => {
    expect(headCodes(['a', 'b'])).toBe('a、b')
    expect(headCodes(['1', '2', '3', '4', '5', '6', '7'])).toBe('1、2、3、4、5、6 等 7 节')
  })

  it('刷新确认写明：整节替换、另存新版本、以已保存版本为底、未保存的在线编辑不含', () => {
    for (const text of [sectionRefreshPrompt('八、1'), staleRefreshPrompt(3), staleRefreshPrompt(null)]) {
      expect(text).toContain('标题、表格与正文')
      expect(text).toContain('另存为')
      expect(text).toContain('以已保存的最新版本为底')
      expect(text).toContain('尚未保存的修改不包含在内')
    }
    expect(staleRefreshPrompt(3)).toContain('（共 3 节）')
    expect(staleRefreshPrompt(null)).not.toContain('共')
  })

  it('覆盖手动修改的二次确认：单节点名、多节列数', () => {
    expect(overwritePrompt(['八、1'])).toContain('「八、1」在交付件中有手动修改')
    expect(overwritePrompt(['八、1', '八、2'])).toContain('以下 2 节在交付件中（八、1、八、2）有手动修改')
  })
})
