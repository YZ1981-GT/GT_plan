/**
 * 打开独立查账窗口的统一入口
 *
 * 窗口名按 projectId 固定，重复调用聚焦已有窗口而非重复创建。
 * 参考 DshPanel.vue:377-391 的 window.open 模式。
 *
 * spec: multi-window-ledger-workbench Phase 1 Task 3
 */
import router from '@/router'

export function openLedgerWindow(projectId: string, year?: number): void {
  if (!projectId) return

  const resolved = router.resolve({
    name: 'LedgerWorkbench',
    params: { projectId },
    query: year ? { year: String(year) } : {},
  })

  // 窗口名固定：同一项目只开一个查账窗口，再次调用聚焦已有窗口
  const windowName = `gt-ledger-${projectId}`

  window.open(
    resolved.href,
    windowName,
    'width=1400,height=900,menubar=no,toolbar=no,status=no',
  )
}
