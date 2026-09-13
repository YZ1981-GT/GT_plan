// -*- coding: utf-8 -*-
/**
 * D4-9 Task 8/12 守卫：legacy 单向入口已移除，在线编辑由宿主统一提供。
 *
 * spec: d4-9-customer-structure-bidirectional-writeback / Task 8, 12
 * Requirements: 7.1, 7.5, 8.4
 *
 * 判据落在**剥注释后的源码结构**上（防「注释里提到 GtOnlyOfficeSheet」造成假红/假绿）：
 * - `D4TabCustomerStructure.vue` 不再 import / 渲染 `GtOnlyOfficeSheet`（不得双入口）；
 * - 不再有本组件私有的 `editorMode` 双模式切换；
 * - 宿主 `GtD4OperatingRevenue.vue` 仍通过统一 `useD4EntryDualMode` + `GtOnlyOfficeSheet`
 *   提供 D4-9 的在线编辑（entry=xlsx/gt-d4-operating-revenue），且能力提示挂在该 entry。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { stripJsComments, stripHtmlComments } from '../../../../__tests__/_helpers/frontendSourceScan'

const COMPONENT = resolve(__dirname, './D4TabCustomerStructure.vue')
const HOST = resolve(__dirname, '../../GtD4OperatingRevenue.vue')

function codeOf(path: string): string {
  return stripJsComments(stripHtmlComments(readFileSync(path, 'utf-8')))
}

describe('D4-9 legacy 单向入口移除（Task 8/12）', () => {
  const component = codeOf(COMPONENT)
  const componentRaw = readFileSync(COMPONENT, 'utf-8')
  const host = codeOf(HOST)

  it('剥注释 helper 有效（否则正向/反向断言强度悄悄改变）', () => {
    // 原始源码里注释仍提到 GtOnlyOfficeSheet（留痕），剥掉后不在。
    expect(componentRaw).toContain('GtOnlyOfficeSheet')
    expect(component).not.toContain('GtOnlyOfficeSheet')
  })

  it('组件不再 import / 渲染 GtOnlyOfficeSheet（不得双入口）', () => {
    expect(component).not.toContain('GtOnlyOfficeSheet')
  })

  it('组件不再有私有 editorMode 双模式切换', () => {
    expect(component).not.toContain('editorMode')
    expect(component).not.toMatch(/el-segmented[^>]*modeOptions/)
  })

  it('宿主经统一 useD4EntryDualMode + GtOnlyOfficeSheet 提供在线编辑', () => {
    expect(host).toContain('useD4EntryDualMode')
    expect(host).toContain('GtOnlyOfficeSheet')
    // 能力提示挂在 D4 entry（D4-9 在线编辑复用该 entry 的裁决）。
    expect(host).toContain('xlsx/gt-d4-operating-revenue')
  })

  it('组件仍保留结构化视图核心（客户表 + 导入导出 + rowId 迁移未被误删）', () => {
    expect(component).toContain('migrateRowIds')
    expect(component).toContain('useD4ImportExport')
    expect(component).toContain('customer-table')
  })
})
