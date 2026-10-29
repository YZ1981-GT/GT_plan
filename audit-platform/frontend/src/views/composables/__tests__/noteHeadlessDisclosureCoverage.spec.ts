/**
 * 离屏同步覆盖清单（spec note-pull-header-formula-closure R2.3 / note-pull-followup-closure R1.4）：只许变短，逐码写明原因。
 *
 * 附注刷新时，已接入离屏同步的底稿按披露 Tab 同一套代码现算披露表同步到附注；未接入的底稿只能在底稿附注披露页
 * 保存一次才进附注（刷新提示会点名）。每接入一张底稿：在 `components/workpaper/headless/providers/` 本组登记文件里登记、
 * 从下面清单删掉这一项。底稿 → 附注章节映射真源 = `backend/data/note_workpaper_sync_registry.json`。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { headlessDisclosureWpCodes } from '../noteHeadlessDisclosure'


/** 未接入的底稿 → 原因（只许删条目） */
const NOT_YET_HEADLESS: Readonly<Record<string, string>> = {
}

function registryCodes(): string[] {
  const path = resolve(__dirname, '../../../../../../backend/data/note_workpaper_sync_registry.json')
  const doc = JSON.parse(readFileSync(path, 'utf-8')) as { entries: Array<{ wp_code: string }> }
  return [...new Set(doc.entries.map((e) => e.wp_code))]
}

describe('附注离屏同步覆盖清单', () => {
  it('注册表里每张底稿要么已接入离屏同步，要么在待接入清单（清单只许变短）', () => {
    const covered = new Set(headlessDisclosureWpCodes())
    const missing = registryCodes().filter((c) => !covered.has(c)).sort()
    expect(missing).toEqual(Object.keys(NOT_YET_HEADLESS).sort())
  })

  it('已接入的底稿都在注册表里（不接入没有附注映射的底稿）', () => {
    const registry = new Set(registryCodes())
    expect(headlessDisclosureWpCodes().filter((c) => !registry.has(c))).toEqual([])
    expect(registry.size).toBe(78)
  })

  it('仍未接入的底稿逐码写明具体原因（不许用「待接入」类笼统标签占位）', () => {
    expect(Object.entries(NOT_YET_HEADLESS).filter(([, why]) => !why.trim() || /^待接入/.test(why) || why.length < 40))
      .toEqual([])
  })

  it('78/78 已接入：待接清单必须为空', () => {
    expect(Object.keys(NOT_YET_HEADLESS)).toEqual([])
  })
})
