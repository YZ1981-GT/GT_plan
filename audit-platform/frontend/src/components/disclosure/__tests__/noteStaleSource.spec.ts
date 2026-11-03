/** 附注 stale 来源中文展示与后端 StaleSource 逐成员对拍。 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  NOTE_STALE_SOURCE_LABELS,
  noteStaleSourceLabel,
  noteStaleSourceTip,
} from '../noteStaleSource'

const REPO = resolve(__dirname, '../../../../../..')
const BACKEND = readFileSync(resolve(REPO, 'backend/app/services/stale_state.py'), 'utf-8')

function backendLabels(): Record<string, string> {
  const codes = new Map<string, string>()
  const labels = new Map<string, string>()
  for (const match of BACKEND.matchAll(/^    ([A-Z][A-Z0-9_]*) = "([^"]+)"$/gm)) {
    codes.set(match[1], match[2])
  }
  for (const match of BACKEND.matchAll(/^    StaleSource\.([A-Z][A-Z0-9_]*): "([^"]+)",?$/gm)) {
    labels.set(match[1], match[2])
  }
  const pairs = [...codes].map(([member, code]) => {
    const label = labels.get(member)
    if (!label) throw new Error(`后端 ${member} 缺中文标签`)
    return [code, label] as const
  })
  return Object.fromEntries(pairs)
}

describe('附注 stale 来源中文展示', () => {
  it('已知、未知、空值三态有不同且明确的中文文案', () => {
    expect(noteStaleSourceLabel('adjustment')).toBe('调整分录已变化')
    expect(noteStaleSourceLabel('future_source')).toBe('其他数据变化')
    expect(noteStaleSourceLabel(null)).toBe('来源未记录')
    expect(noteStaleSourceLabel('   ')).toBe('来源未记录')
    expect(noteStaleSourceTip(null)).toBe('过期（来源未记录）')
    expect(noteStaleSourceTip('future_source')).toContain('其他数据变化')
  })

  it('前端映射与后端 StaleSource / STALE_SOURCE_LABELS 逐成员一致', () => {
    const backend = backendLabels()
    expect(Object.keys(backend).length).toBeGreaterThanOrEqual(16)
    expect(backend).toEqual(NOTE_STALE_SOURCE_LABELS)
  })

  it('就绪面板展示来源标签，不退回笼统的“待刷新”', () => {
    const panel = readFileSync(resolve(__dirname, '../NoteReadinessPanel.vue'), 'utf-8')
    expect(panel).toContain('noteStaleSourceLabel(row.stale_source)')
    expect(panel).toContain('noteStaleSourceTip(row.stale_source)')
    expect(panel).not.toContain("row.stale_source === 'report' ? '关联变更' : '待刷新'")
  })
})
