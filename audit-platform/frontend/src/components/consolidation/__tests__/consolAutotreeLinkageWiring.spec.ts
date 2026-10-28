/**
 * 合并页左树 ↔ 右侧联动接线源码守卫（spec consol-autotree-linkage-closure R6 / R7 / R9.4）。
 *
 * 合并页（ConsolidationIndex.vue，2000+ 行、依赖布局与十余个子组件）不挂载：直接读源码断言关键接线，
 * 行为本身由各子组件的单测覆盖（ConsolMiddleNav.linkage / ConsolTrialBalanceTab / ConsolReportBreakdownView /
 * ConsolEntityStandalonePanel / EntrySummarySheet / ConsolWorksheetTabs.autotree）。
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const ROOT = path.resolve(__dirname, '../../../')
const read = (rel: string) => fs.readFileSync(path.join(ROOT, rel), 'utf-8')
const index = read('views/ConsolidationIndex.vue')
const layout = read('layouts/ThreeColumnLayout.vue')
const nav = read('components/consolidation/ConsolMiddleNav.vue')

/** 取函数体：从声明到下一个顶格的「}」 */
function body(src: string, decl: string): string {
  const start = src.indexOf(decl)
  expect(start, `找不到 ${decl}`).toBeGreaterThan(-1)
  return src.slice(start, src.indexOf('\n}', start) + 2)
}

describe('单棵树：中栏是唯一的企业树（R7.1）', () => {
  it('页内常驻企业树侧栏已删除', () => {
    for (const s of ['gt-consol-sidebar', 'consolSidebarCollapsed', 'onSidebarNodeClick', 'sidebarTreeRef', 'sidebarSearch']) {
      expect(index, `残留侧栏：${s}`).not.toContain(s)
    }
  })

  it('当前节点只经 setCurrentNode 切换：中栏选择 / 组织图 / 结构卡片 / 上下文条都走它', () => {
    const set = body(index, 'function setCurrentNode(node: ConsolTreeNode')
    expect(set).toContain('currentConsolEntity.value = currentConsolEntityForNode(node)')
    expect(set).toContain('if (opts.reload !== false && (changed || opts.force)) reloadCurrentNodeContent()')
    expect(body(index, 'function onTreeNodeClick(data: ConsolTreeNode)')).toContain('setCurrentNode(data)')
    expect(body(index, 'function onConsolTreeSelect(data: ConsolTreeSelectPayload)')).toContain('setCurrentNode(node')
    expect(index).toContain('@go-root="groupTree[0] && setCurrentNode(groupTree[0])"')
  })

  it('页面广播当前节点，中栏据此高亮；中栏晚挂载时请求回发', () => {
    expect(body(index, 'function broadcastCurrentNode()')).toContain("eventBus.emit('consol-current-node', {")
    expect(index).toContain('watch(currentEntityNodeKey, broadcastCurrentNode)')
    expect(index).toContain("eventBus.on('consol-current-node-request', broadcastCurrentNode)")
    expect(index).toContain("eventBus.off('consol-current-node-request', broadcastCurrentNode)")
    expect(nav).toContain("eventBus.on('consol-current-node'")
    expect(nav).toContain("eventBus.off('consol-current-node'")
  })

  it('试算页 / 差额表自己切换节点 ⇒ 回写当前节点，不重复取数', () => {
    expect(body(index, 'function onChildNodeChange(key: string)')).toContain('setCurrentNode(node, { reload: false })')
    expect((index.match(/@node-change="onChildNodeChange"/g) || []).length).toBe(2)
  })
})

describe('差额户呈现（R7.2）', () => {
  it('点差额户不自动弹分录抽屉；「📝 差额分录」与中栏右键事件打开', () => {
    expect(body(index, 'function onTreeNodeClick(data: ConsolTreeNode)')).not.toContain('openElimPanel(')
    const open = body(index, 'function onOpenElimPanelEvent(payload: { nodeKey: string })')
    expect(open).toContain('if (!node || !isElimNode(node)) return')
    expect(open).toContain('openElimPanel(node)')
    expect(index).toContain("eventBus.on('consol-open-elim-panel', onOpenElimPanelEvent)")
    expect(index).toContain("eventBus.off('consol-open-elim-panel', onOpenElimPanelEvent)")
    expect(index).toContain('@open-elim="openElimPanel"')
  })

  it('分录变化后重读企业树、通知中栏、重读分录汇总表', () => {
    const changed = body(index, 'function onElimChanged()')
    expect(changed).toContain('loadGroupTree()')
    expect(changed).toContain('notifyTreeChanged()')
    expect(changed).toContain('consolWorksheetTabsRef.value?.reloadEntrySummary()')
    expect(body(index, 'function notifyTreeChanged()')).toContain("eventBus.emit('consol-refresh-done'")
  })
})

describe('数据节点显示单体报表 / 附注（R6）', () => {
  it('报表页与附注页按 currentStandalone 切单体面板；合并附注组件保持挂载（v-show）', () => {
    expect(index).toContain('const currentStandalone = computed(() => standaloneEntityOf(currentNode.value))')
    expect((index.match(/<ConsolEntityStandalonePanel/g) || []).length).toBe(2)
    expect(index).toContain('mode="report"')
    expect(index).toContain('mode="note"')
    expect(index).toContain('v-show="!currentStandalone"')
  })

  it('合并附注组件有多个根节点（弹窗等）⇒ v-show 放在包裹元素上（写在组件上不生效，浏览器实测两块同时显示）', () => {
    const noteTab = read('components/consolidation/ConsolNoteTab.vue')
    const tpl = noteTab.slice(noteTab.indexOf('<template>') + 10, noteTab.indexOf('<script'))
    expect((tpl.match(/^ {2}<[A-Za-z]/gm) || []).length, '前提：ConsolNoteTab 是多根组件').toBeGreaterThan(1)
    expect(index).toContain('<div v-show="!currentStandalone" class="gt-consol-note-host">')
    expect(index).not.toMatch(/<ConsolNoteTab\s+v-show=/)
  })

  it('合并附注组件的主体只取合并口径节点（数据节点不改它的保存目标）', () => {
    expect(index).toContain(':current-entity="noteEntity"')
    expect(index).toContain('if (!currentStandalone.value) noteEntity.value = { ...currentConsolEntity.value }')
  })

  it('当前节点变化后：报表重读；附注等下一次渲染拿到新节点再重读当前章节；数据节点不读合并附注', () => {
    const fn = body(index, 'async function reloadCurrentNodeContent()')
    expect(fn).toContain('loadConsolReport()')
    expect(fn).toContain("if (activeTab.value !== 'consol_note' || currentStandalone.value) return")
    expect(fn.indexOf('await nextTick()')).toBeLessThan(fn.indexOf('onNoteNodeClick('))
  })
})

describe('就绪门与四栏切换（R7.4 / R7.5）', () => {
  it('企业树与年度就绪前不取数；挂载时树加载完再加载当前页', () => {
    expect(index).toContain('const consolContentReady = computed(() => groupTreeLoaded.value && Boolean(projectId.value && effectiveConsolYear()))')
    expect(body(index, 'function loadActiveTabContent(tab = activeTab.value)')).toContain('if (!consolContentReady.value) return')
    const mounted = index.slice(index.indexOf('onMounted(async () => {'))
    expect(mounted.indexOf('await loadGroupTree()')).toBeGreaterThan(-1)
    expect(mounted.indexOf('loadActiveTabContent()')).toBeGreaterThan(mounted.indexOf('await loadGroupTree()'))
  })

  it('进入合并附注页切四栏显示附注目录', () => {
    const w = index.slice(index.indexOf('watch(activeTab, (tab) => {'), index.indexOf('watch(activeTab, (tab) => {') + 400)
    expect(w).toContain("if (tab === 'consol_note') eventBus.emit('four-col-switch', { tab: 'notes' })")
    expect(w).toContain('loadActiveTabContent(tab)')
  })

  it('布局只转发一次 four-col-switch（转发件带 _relayed，收到转发件不再处理）', () => {
    const fn = body(layout, 'function onSwitchFourCol(payload: FourColSwitchPayload)')
    expect(fn).toContain('if (payload?._relayed) return')
    expect(fn).toContain("eventBus.emit('four-col-switch', { ...payload, _relayed: true })")
    expect(fn.indexOf('if (payload?._relayed) return')).toBeLessThan(fn.indexOf('eventBus.emit('))
  })
})
