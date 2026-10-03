import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const ROOT = path.resolve(__dirname, '../../../')
const read = (rel: string) => fs.readFileSync(path.join(ROOT, rel), 'utf-8')
const manager = read('components/formula/FormulaManagerDialog.vue')
const layout = read('layouts/ThreeColumnLayout.vue')
const index = read('views/ConsolidationIndex.vue')
const note = read('components/consolidation/ConsolNoteTab.vue')
const worksheets = read('components/consolidation/worksheets/ConsolWorksheetTabs.vue')
const sseTypes = read('types/sse.ts')

describe('公式管理合并域跨层接线', () => {
  it('公式中心用合并专用 CRUD 面板，通用 report/note 工具不在合并节点误显示', () => {
    expect(manager).toContain('<ConsolFormulaManagementPanel')
    expect(manager).toContain('v-if="isConsolFormulaNode && projectId && year"')
    expect(manager).toContain('v-if="!isConsolFormulaNode" class="gt-fm-health-bar"')
    expect(manager).toContain('!isConsolFormulaNode && !isCrossCheckMode')
    expect(manager).toContain('CONSOL_REPORT_TREE_ITEMS.map')
    expect(manager).toContain("key: 'consol_note', label: '合并附注'")
  })

  it('无 wpId 的项目级合并 payload 仍完整保留并透传模板/章节/报表类型', () => {
    expect(layout).toContain('formulaContext.value = payload ? { ...payload } : undefined')
    expect(layout).not.toContain('payload?.wpId ? { ...payload } : undefined')
    for (const binding of [
      ':template-type="formulaContext?.templateType"', ':note-section="formulaContext?.noteSection"',
      ':note-section-title="formulaContext?.noteSectionTitle"', ':initial-report-type="formulaContext?.initialReportType"',
    ]) expect(layout).toContain(binding)
  })

  it('合并页与附注/工作底稿入口都发送 project/year/scope，不再只发 nodeKey', () => {
    expect(index).toContain("scope: 'consol_report', projectId: projectId.value, year: effectiveYear")
    expect(index).toContain("scope: 'consol_note', projectId: projectId.value, year: effectiveYear")
    expect(index).toContain("scope: 'consol_worksheet', projectId: projectId.value, year: effectiveYear")
    expect(note).toContain("scope: 'consol_note'")
    expect(note).toContain('noteSection: sec.section_id')
    expect(worksheets).toContain("scope: 'consol_worksheet'")
    expect(worksheets).toContain('defineExpose({ reload, activeSheet })')
  })
})

describe('合并推送 raw SSE 接线', () => {
  it('三种事件进入 SSE 类型联合，并通过 projectEventStream 精确订阅事件名', () => {
    for (const eventName of ['consol.pushed', 'consol.push_stale', 'consol.push_failed']) {
      expect(sseTypes).toContain(`| '${eventName}'`)
    }
    expect(index).toContain('for (const eventName of Object.values(CONSOL_PUSH_EVENTS))')
    expect(index).toContain('subscribeProjectEvent(projectId.value, eventName, onConsolPushEvent)')
    expect(index).toContain('if (!isCurrentConsolPushEvent(payload, projectId.value, effectiveConsolYear())) return')
  })

  it('推送成功按当前视图强制刷新；失败只提示不伪装成功；过期只重查状态', () => {
    const refresh = index.slice(index.indexOf('async function refreshCurrentAfterConsolPush'), index.indexOf('function stopConsolPushEvents'))
    expect(refresh).toContain("activeTab.value === 'worksheets'")
    expect(refresh).toContain('consolWorksheetTabsRef.value?.reload()')
    expect(refresh).toContain("activeTab.value === 'structure'")
    expect(refresh).toContain("activeTab.value === 'consol_tb'")
    expect(refresh).toContain("activeTab.value === 'consol_report'")
    expect(refresh).toContain('reloadConsolReportView(true)')
    expect(refresh).toContain("activeTab.value === 'consol_note'")
    const failedAt = refresh.indexOf('eventName === CONSOL_PUSH_EVENTS.failed')
    const pushedAt = refresh.indexOf('eventName !== CONSOL_PUSH_EVENTS.pushed')
    expect(failedAt).toBeGreaterThan(0)
    expect(pushedAt).toBeGreaterThan(failedAt)
    expect(refresh.slice(failedAt, pushedAt)).not.toContain('refreshCurrentAfterConsolPush()')
  })

  it('页面过期横幅直接 manual 推送，排队回执后不提前清除权威 stale', () => {
    expect(index).toContain('data-testid="consol-push-stale-banner"')
    expect(index).toContain("pushConsolidation(projectId.value, effectiveConsolYear(), 'manual')")
    const queue = index.slice(index.indexOf('async function queueConsolPush'), index.indexOf('async function refreshCurrentAfterConsolPush'))
    expect(queue).not.toContain('consolPushStatus.value = null')
    expect(index).toContain('stopConsolPushEvents()')
  })
})
