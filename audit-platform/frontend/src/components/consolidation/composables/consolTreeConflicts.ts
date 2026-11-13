/**
 * 企业树重复项目 / 关系冲突的统一前端处理。
 *
 * 诊断仍是后端计算结果，前端只负责筛选、会话内去重和推送前确认。
 * 不能把其他企业树提示误当成冲突，也不能因为诊断接口失败而阻断本来可执行的推送。
 */
import { h } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getWorksheetTree, type ConsolTreeDiagnostic } from '@/services/consolidationApi'

export const CONFLICT_DIAGNOSTIC_CODES = ['duplicate_project', 'relation_conflict'] as const

const CONFLICT_CODE_SET = new Set<string>(CONFLICT_DIAGNOSTIC_CODES)

/** 只保留会改变企业树取值、需要用户确认的两类诊断。 */
export function treeConflicts(
  diagnostics: ConsolTreeDiagnostic[] | null | undefined,
): ConsolTreeDiagnostic[] {
  if (!Array.isArray(diagnostics)) return []
  return diagnostics.filter((diagnostic) => CONFLICT_CODE_SET.has(diagnostic.code))
}

/**
 * 生成与诊断顺序无关的签名。
 * 只使用诊断 code / message：项目 id 是「去修改」入口，不是诊断内容本身。
 */
export function conflictSignature(
  diagnostics: ConsolTreeDiagnostic[] | null | undefined,
): string {
  const entries = treeConflicts(diagnostics)
    .map((diagnostic) => [String(diagnostic.code), String(diagnostic.message)] as const)
    .sort(([codeA, messageA], [codeB, messageB]) => {
      const codeOrder = codeA.localeCompare(codeB)
      return codeOrder || messageA.localeCompare(messageB)
    })
  return JSON.stringify(entries)
}

export function conflictSessionKey(projectId: string, year: number | null | undefined): string {
  return `gt:consol-tree-conflicts:${projectId}:${year ?? 'unknown'}`
}

/**
 * 判断工作台在本次树加载后是否需要展示冲突弹窗。
 * 工作台与测试共用这条生产判定，避免只在视图源码里复制会话去重规则。
 */
export function shouldShowTreeConflicts(
  projectId: string | null | undefined,
  year: number | null | undefined,
  diagnostics: ConsolTreeDiagnostic[] | null | undefined,
): boolean {
  if (!projectId) return false
  const conflicts = treeConflicts(diagnostics)
  if (!conflicts.length) return false
  return acknowledgedConflictSignature(projectId, year) !== conflictSignature(conflicts)
}

export function acknowledgedConflictSignature(
  projectId: string,
  year: number | null | undefined,
): string | null {
  try {
    return sessionStorage.getItem(conflictSessionKey(projectId, year))
  } catch {
    // 浏览器禁用存储时不影响企业树或推送，只是无法做会话内去重。
    return null
  }
}

export function rememberConflictSignature(
  projectId: string,
  year: number | null | undefined,
  signature: string,
): void {
  try {
    sessionStorage.setItem(conflictSessionKey(projectId, year), signature)
  } catch {
    // 存储不可用时保持当前页面功能可用。
  }
}

function conflictMessage(diagnostics: ConsolTreeDiagnostic[]) {
  return h(
    'div',
    { style: 'line-height: 1.7;' },
    [
      h('p', { style: 'margin: 0 0 8px;' }, '企业树存在重复项目或集团关系冲突，系统会按提示的一方取值。'),
      h(
        'ul',
        { style: 'margin: 0; padding-left: 20px;' },
        diagnostics.map((diagnostic, index) => h('li', { key: `${diagnostic.code}-${index}` }, diagnostic.message)),
      ),
    ],
  )
}

/**
 * 手工推送前确认企业树冲突。
 * 诊断读取失败时按既有约定放行，但明确提示未检查成功；用户取消时返回 false。
 */
export async function confirmPushDespiteConflicts(projectId: string): Promise<boolean> {
  let response
  try {
    response = await getWorksheetTree(projectId)
  } catch {
    ElMessage.warning('未能检查企业树冲突，已继续推送')
    return true
  }

  const conflicts = treeConflicts(response?.diagnostics)
  if (!conflicts.length) return true

  try {
    await ElMessageBox.confirm(
      conflictMessage(conflicts),
      '企业树存在冲突',
      {
        type: 'warning',
        confirmButtonText: '仍要推送',
        cancelButtonText: '取消',
        closeOnClickModal: false,
      },
    )
    return true
  } catch {
    return false
  }
}
