import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = resolve(__dirname, '../../..')
const read = (relative: string) => readFileSync(resolve(root, relative), 'utf8')

describe('集团合并工作台动作真实语义', () => {
  const index = read('views/ConsolidationIndex.vue')
  const middle = read('components/consolidation/ConsolMiddleNav.vue')
  const note = read('components/consolidation/ConsolNoteTab.vue')
  const worksheets = read('components/consolidation/worksheets/ConsolWorksheetTabs.vue')

  it('不再展示无后端写入的转换规则或范围模板成功入口', () => {
    expect(index).not.toContain('应用转换')
    expect(index).not.toContain('showConsolConversion')
    expect(index).not.toContain('SharedTemplatePicker')
    expect(index).not.toContain('@year-change=')
    expect(index).not.toContain('@template-change=')
    expect(index).toContain('修改项目口径')
  })

  it('节点动作明确为重新读取，不再谎称计算或消费无效 worksheet 选项', () => {
    expect(middle).toContain('重新读取已生成内容')
    expect(middle).toContain('需要重新计算时，请使用主工具栏“更新合并结果”')
    expect(middle).not.toContain('refreshOptions.worksheet')
    expect(middle).not.toContain('已发起刷新')
    expect(middle).not.toContain('setTimeout(r, 500)')
  })

  it('所有危险上下文切换共用三选一协调器', () => {
    expect(index).toContain('provideConsolWorkspaceGuard()')
    expect(index).toContain('onBeforeRouteLeave(() => workspaceGuard.confirmTransition')
    expect(index).toContain(':before-leave="beforeConsolTabLeave"')
    expect(index).toContain('更新合并结果前，请先处理未保存修改')
    expect(worksheets).toContain("id: 'consol-worksheets'")
    expect(note).toContain("id: 'consol-note'")
    expect(note.match(/@click="leaveNoteEdit"/g)?.length).toBe(2)
    expect(note).not.toContain('@click="exitNoteEdit(true)"')
  })

  it('正式报表与实时预览分栏，正式导出固定到 report run 的 immutable artifact', () => {
    expect(index).toContain('value="published"')
    expect(index).toContain('value="preview"')
    expect(index).toContain("mode: requestedMode")
    expect(index).toContain('envelope?.report_run_id')
    expect(index).toContain("`${base}|${consolReportMode.value}|${consolReportRunId.value || 'latest'}`")
    expect(index).toContain('createConsolArtifact(')
    expect(index).toContain('consolArtifactDownloadUrl(')
    expect(index).toContain(':disabled="!consolReportIsPublished"')
    expect(index).not.toContain('reportPaths.exportAllExcel')
    expect(index).not.toContain('reportPaths.exportExcel')
  })

  it('工作表首次加载不可编辑，错误不清除上次成功数据，汇总表完整读回', () => {
    expect(worksheets).toContain('cw-loading-skeleton')
    expect(worksheets).toContain(':inert="contentBlocked || undefined"')
    expect(worksheets).toContain('已保留上次成功加载的数据')
    for (const key of ['saved.post_invest', 'saved.post_income', 'saved.minority', 'saved.internal_cashflow']) {
      expect(worksheets).toContain(key)
    }
    expect(worksheets).toContain('saved.capital')
    expect(worksheets).toContain('adjustment_items')
    expect(worksheets).toContain('consol_report_amount')
  })
})
