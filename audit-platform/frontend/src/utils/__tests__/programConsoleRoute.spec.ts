/**
 * 程序裁剪页「进入程序表」直达程序表页签（spec procedure-chain-hardening-and-java-contracts R5）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { PROGRAM_SHEET_ALIAS } from '../normalizeSheetName'
import { programConsoleRoute } from '../programConsoleRoute'

describe('programConsoleRoute', () => {
  it('带程序表别名（原先不带 sheet ⇒ 多页底稿落到「底稿目录」）', () => {
    expect(programConsoleRoute('p1', 'w1')).toEqual({
      path: '/projects/p1/workpapers/w1/edit',
      query: { sheet: PROGRAM_SHEET_ALIAS },
    })
    expect(PROGRAM_SHEET_ALIAS).toBe('@program')
  })

  it('程序裁剪页的「进入程序表」用它跳转', () => {
    const src = readFileSync(resolve(__dirname, '../../views/ProcedureTrimming.vue'), 'utf-8')
    const body = src.slice(src.indexOf('function enterProgramConsole('), src.indexOf('function onSmartTrim('))
    expect(body).toMatch(/router\.push\(programConsoleRoute\(projectId\.value, row\.wp_id\)\)/)
  })
})
