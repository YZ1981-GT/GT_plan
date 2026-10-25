/**
 * 合并附注节点级刷新编排源码守卫（spec consol-note-node-refresh-and-formula-orchestration §六）。
 *
 * 不挂载 Vue 组件：直接读源码断言关键模式。
 * 刷新追踪逻辑已抽到 useConsolRefreshTracking composable，此处同时读两个文件。
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const ROOT = path.resolve(__dirname, '../../../')
const read = (rel: string) => fs.readFileSync(path.join(ROOT, rel), 'utf-8')

const index = read('views/ConsolidationIndex.vue')
const noteTab = read('components/consolidation/ConsolNoteTab.vue')
const tracking = read('components/consolidation/composables/useConsolRefreshTracking.ts')

// ─── 一键刷新上下文冻结与校验 ──────────────────────────────────────────────

describe('一键刷新上下文冻结与校验（需求 6.1 / 设计 §六）', () => {
  it('onRefreshAll 在 POST 前调用 captureRefreshContext', () => {
    const fn = index.slice(index.indexOf('async function onRefreshAll()'), index.indexOf('async function onRefreshAll()') + 2000)
    const capturePos = fn.indexOf('captureRefreshContext()')
    const postPos = fn.indexOf('api.post(P_consol.refreshAll(')
    expect(capturePos).toBeGreaterThan(-1)
    expect(postPos).toBeGreaterThan(-1)
    expect(capturePos).toBeLessThan(postPos)
  })

  it('onRefreshAll 使用 composable 的 start 方法', () => {
    expect(index).toContain('refreshTracking.start(jobId, context)')
  })

  it('composable start 初始化 tree 和 note 状态为 pending', () => {
    const fn = tracking.slice(tracking.indexOf('function start('), tracking.indexOf('function start(') + 500)
    expect(fn).toContain("state.tree = 'pending'")
    expect(fn).toContain("state.note = 'pending'")
  })

  it('onRefreshAll 校验后端返回的 project_id/year', () => {
    const fn = index.slice(index.indexOf('async function onRefreshAll()'), index.indexOf('async function onRefreshAll()') + 2500)
    expect(fn).toContain('resPid')
    expect(fn).toContain('resYear')
  })
})

// ─── SSE/轮询严格过滤 ──────────────────────────────────────────────────────

describe('SSE/轮询严格过滤（需求决策）', () => {
  it('SSE handler 严格匹配 job_id、project_id、year', () => {
    expect(tracking).toContain('!data.job_id || data.job_id !== jobId')
    expect(tracking).toContain('String(data.project_id) !== context.projectId')
    expect(tracking).toContain('Number(data.year) !== context.year')
  })

  it('轮询使用冻结上下文', () => {
    expect(tracking).toContain('P_consol.refreshStatus(context.projectId, context.year, jobId)')
  })

  it('SSE 完成事件提取 steps_completed', () => {
    expect(tracking).toContain('data.steps_completed')
  })
})

// ─── 附注完成以持久化 GET 为证据 ────────────────────────────────────────────

describe('附注完成以持久化 GET 为证据（ADR-CNFO-002）', () => {
  it('finish 内调用 reloadNoteForRefresh 而非只刷新目录', () => {
    expect(tracking).toContain('reloadNoteForRefresh(context)')
    expect(tracking).not.toContain('loadConsolNoteTree(true)')
  })

  it('notes 不在 steps_completed 时标记 note failed', () => {
    expect(tracking).toContain("!steps.includes('notes')")
    expect(tracking).toContain("state.note = 'failed'")
    expect(tracking).toContain("state.noteReason = '附注步骤未完成'")
  })

  it('附注重读 done 才标 note.done；failed 保留原因', () => {
    expect(tracking).toContain("noteResult?.status === 'done'")
    expect(tracking).toContain("state.note = 'done'")
    expect(tracking).toContain("state.note = 'failed'")
    expect(tracking).toContain('state.noteReason')
  })

  it('tree 完成独立于 note 完成', () => {
    expect(tracking).toContain("steps.includes('tree')")
  })
})

// ─── stale 快捷入口 ────────────────────────────────────────────────────────

describe('stale 快捷入口真正调用 API（需求 6.5）', () => {
  it('onReaggregateNow 是 async 并调用 onReaggregateNotes', () => {
    expect(index).toContain('async function onReaggregateNow()')
    const fn = index.slice(index.indexOf('async function onReaggregateNow()'), index.indexOf('async function onReaggregateNow()') + 500)
    expect(fn).toContain('await onReaggregateNotes()')
  })

  it('onReaggregateNotes 传完整 body 并等待附注重读', () => {
    const fn = index.slice(index.indexOf('async function onReaggregateNotes()'), index.indexOf('async function onReaggregateNotes()') + 3000)
    expect(fn).toContain('captureRefreshContext()')
    expect(fn).toContain('section_ids:')
    expect(fn).toContain('node_key: context.nodeKey')
    expect(fn).toContain('standard: consolNoteTemplateType.value')
    expect(fn).toContain('reloadNoteForRefresh(context)')
    expect(fn).toContain("noteResult?.status === 'done'")
    expect(fn).toContain('consolStale.value = false')
  })

  it('consolStale 只在 done 之后清', () => {
    const fn = index.slice(index.indexOf('async function onReaggregateNotes()'), index.indexOf('async function onReaggregateNotes()') + 3000)
    const stalePos = fn.indexOf('consolStale.value = false')
    const doneCheck = fn.indexOf("noteResult?.status === 'done'")
    expect(stalePos).toBeGreaterThan(doneCheck)
  })
})

// ─── 导航路径 ──────────────────────────────────────────────────────────────

describe('导航路径重读当前章节', () => {
  it('onTreeNodeClick 附注分支调用 onNoteNodeClick 带 section_id', () => {
    const fn = index.slice(index.indexOf('function onTreeNodeClick(data: ConsolTreeNode)'), index.indexOf('function onTreeNodeClick(data: ConsolTreeNode)') + 1000)
    expect(fn).toContain("consolNoteTabRef.value?.onNoteNodeClick({ section_id: section.section_id, title: section.title })")
  })

  it('onConsolRefreshEntity notes 类型重读当前章节', () => {
    const fn = index.slice(index.indexOf('function onConsolRefreshEntity('), index.indexOf('function onConsolRefreshEntity(') + 2000)
    expect(fn).toContain("types.includes('notes')")
    expect(fn).toContain('consolNoteTabRef.value?.onNoteNodeClick({ section_id: section.section_id')
  })

  it('onConsolCatalogSelect refresh-note 使用 sectionId 重读', () => {
    const fn = index.slice(index.indexOf("data.type === 'refresh-note'"), index.indexOf("data.type === 'refresh-note'") + 400)
    expect(fn).toContain('onNoteNodeClick({ section_id: data.sectionId')
  })

  it('refresh-all 刷新目录后也重读当前章节', () => {
    const fn = index.slice(index.indexOf("data.type === 'refresh-all'"), index.indexOf("data.type === 'refresh-all'") + 500)
    expect(fn).toContain('await loadConsolNoteTree()')
    expect(fn).toContain('consolNoteTabRef.value?.onNoteNodeClick({ section_id: section.section_id')
  })
})

// ─── ConsolNoteTab 持久化重读错误判定 ──────────────────────────────────────

describe('ConsolNoteTab 持久化重读错误判定（需求 6.4）', () => {
  it('reloadCurrentSectionAfterRefresh 检查 hasApiFailure', () => {
    const fn = noteTab.slice(noteTab.indexOf('async function reloadCurrentSectionAfterRefresh'), noteTab.indexOf('async function reloadCurrentSectionAfterRefresh') + 2000)
    expect(fn).toContain('hasApiFailure(saved)')
  })

  it('PersistedNotePayload 已删除', () => {
    expect(noteTab).not.toContain('interface PersistedNotePayload')
  })

  it('onNoteNodeClick 对持久化 GET 也检查 hasApiFailure', () => {
    const fn = noteTab.slice(noteTab.indexOf('async function onNoteNodeClick'), noteTab.indexOf('async function onNoteNodeClick') + 3000)
    const checks = fn.match(/hasApiFailure\(/g) || []
    expect(checks.length).toBeGreaterThanOrEqual(2)
  })
})

// ─── isRefreshBaseContextCurrent ────────────────────────────────────────────

describe('isRefreshBaseContextCurrent 比较完整上下文', () => {
  it('包含 sectionId 比较', () => {
    const fn = index.slice(index.indexOf('function isRefreshBaseContextCurrent('), index.indexOf('function isRefreshBaseContextCurrent(') + 500)
    expect(fn).toContain('context.sectionId')
    expect(fn).toContain('selectedNoteSection')
  })
})

// ─── SSE async handler 防 unhandled rejection ──────────────────────────────

describe('SSE async handler 防 unhandled rejection', () => {
  it('composable SSE completed/error 的 finish 调用带 .catch', () => {
    const startFn = tracking.slice(tracking.indexOf('function start('))
    expect(startFn).toContain('.catch(() => {})')
  })
})

// ─── loadGroupTree 返回 Promise<boolean> ─────────────────────────────────

describe('loadGroupTree 返回 Promise<boolean>', () => {
  it('成功返回 true、失败返回 false', () => {
    const fn = index.slice(index.indexOf('async function loadGroupTree()'), index.indexOf('async function loadGroupTree()') + 1500)
    expect(fn).toContain('Promise<boolean>')
    expect(fn).toContain('return true')
    expect(fn).toContain('return false')
  })

  it('composable finish 用 loadGroupTree 返回值判定树状态', () => {
    expect(tracking).toContain('treeOk = await deps.loadGroupTree()')
    expect(tracking).toContain("state.treeReason = '企业树加载失败'")
  })
})

// ─── 补重读当前章节 ────────────────────────────────────────────────────────

describe('冻结上下文过期时 best-effort 补重读', () => {
  it('finish 里冻结上下文 stale 时尝试用当前 sectionId 补重读', () => {
    expect(tracking).toContain('captureRefreshContext()')
    expect(tracking).toContain('currentCtx.sectionId !== context.sectionId')
    expect(tracking).toContain('reloadNoteForRefresh(currentCtx)')
  })

  it('补重读只在同项目同年度同节点时触发', () => {
    expect(tracking).toContain('currentCtx.projectId === context.projectId')
    expect(tracking).toContain('currentCtx.year === context.year')
    expect(tracking).toContain('currentCtx.nodeKey === context.nodeKey')
  })
})

// ─── steps_skipped 精确区分 ────────────────────────────────────────────────

describe('steps_skipped 精确区分跳过与成功', () => {
  it('finish 接收 stepsSkipped 参数', () => {
    expect(tracking).toContain('stepsSkipped: string[] | undefined')
  })

  it('notes 在 skipped 里时标 skipped', () => {
    expect(tracking).toContain("skipped.includes('notes')")
    expect(tracking).toContain('V2 未启用')
  })

  it('notes 既不在 completed 也不在 skipped 时标 failed', () => {
    expect(tracking).toContain("!steps.includes('notes')")
    expect(tracking).toContain("state.note = 'failed'")
    expect(tracking).toContain("state.noteReason = '附注步骤未完成'")
  })
})

// ─── SSE 总线 async handler 感知 ────────────────────────────────────────────

describe('SSE 总线 async handler 感知', () => {
  const sseSource = read('services/sse/projectEventStream.ts')

  it('_fanout 对 async handler 的 Promise 做 .catch', () => {
    const fanout = sseSource.slice(sseSource.indexOf('function _fanout('), sseSource.indexOf('function _fanout(') + 800)
    expect(fanout).toContain('.catch')
    expect(fanout).toContain('async handler error')
  })

  it('同步 handler 抛错仍被 try/catch 捕获', () => {
    const fanout = sseSource.slice(sseSource.indexOf('function _fanout('), sseSource.indexOf('function _fanout(') + 800)
    expect(fanout).toContain('try {')
    expect(fanout).toContain('} catch (e) {')
  })
})

// ─── composable 架构守卫 ────────────────────────────────────────────────────

describe('刷新追踪已抽成 composable', () => {
  it('ConsolidationIndex 导入 useConsolRefreshTracking', () => {
    expect(index).toContain('useConsolRefreshTracking')
    expect(index).toContain('refreshTracking.start(')
    expect(index).toContain('refreshTracking.stop')
  })

  it('composable 导出 start/stop/state/progress', () => {
    expect(tracking).toContain('return { state, progress, start, stop }')
  })

  it('ConsolidationIndex 不再内联 _startRefreshTracking', () => {
    expect(index).not.toContain('function _startRefreshTracking(')
    expect(index).not.toContain('function _stopRefreshTracking(')
  })
})
