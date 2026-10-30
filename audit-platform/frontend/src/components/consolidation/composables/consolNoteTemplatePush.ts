/**
 * 合并附注「📤 下推模板」：把当前章节绑定的集团明细模板下推到全部子企业，在子企业附注里预生成行骨架
 * （spec consol-note-template-push-to-subsidiaries；后端 POST /api/consolidation/notes/{pid}/{year}/push-template）。
 *
 * 从 ConsolNoteTab.vue 抽出：那个文件在行数白名单里，只许变小。
 */
import type { Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { consolidation as P_consol } from '@/services/apiPaths'
import { getDetailTemplateBindings } from '@/services/consolidationApi'

interface PushEntityResult { status?: string; company_name?: string; node_key?: string; reason?: string | null }
export interface PushTemplateResult {
  total_success?: number
  total_failure?: number
  total_skipped?: number
  results?: Array<{ entities?: PushEntityResult[] }>
}

/** 逐家列出某一状态的原因（只看第一个章节：按钮一次只下推当前章节）。 */
function entityLines(result: PushTemplateResult | null | undefined, status: string): string[] {
  return (result?.results?.[0]?.entities ?? [])
    .filter(e => e.status === status)
    .map(e => `${e.company_name || e.node_key}：${e.reason}`)
}

/** 逐家列出失败原因。 */
export function pushFailureLines(result: PushTemplateResult | null | undefined): string {
  return entityLines(result, 'failed').join('\n')
}

/** 失败在前、跳过在后（没有附注 / 由底稿同步 / 无权限 / 合并锁定等，后端写明原因）。 */
export function pushIssueLines(result: PushTemplateResult | null | undefined): string {
  return [...entityLines(result, 'failed'), ...entityLines(result, 'skipped')].join('\n')
}

/** 确认 → 取本章节绑定的模板版本 → 下推；结果用消息 / 弹窗告知。busy 只在真正请求期间为 true。 */
export async function pushConsolNoteTemplate(
  projectId: string, year: number, sectionId: string | undefined, busy: Ref<boolean>,
): Promise<void> {
  if (!projectId) return
  if (!sectionId) { ElMessage.warning('请先选择附注章节'); return }
  try {
    await ElMessageBox.confirm(
      '将把当前章节的明细模板下推到全部子企业：子企业附注里对应的行打上集团行标识，缺的行补成空行。已有行名与数据不会被改动。确认？',
      '下推集团模板',
      { type: 'info', confirmButtonText: '确认下推', cancelButtonText: '取消' },
    )
  } catch { return }

  busy.value = true
  try {
    const bindings = await getDetailTemplateBindings(projectId)
    const binding = bindings?.find(b => b.section_id === sectionId)
    if (!binding?.template_version_id) {
      ElMessage.warning('当前章节未绑定明细模板，请先在「📝 模板管理」中绑定')
      return
    }
    const result = (await api.post(P_consol.notes.pushTemplate(projectId, year), {
      template_version_id: binding.template_version_id,
      section_ids: [sectionId],
    }, { _silent: true } as any)) as PushTemplateResult | null
    if (!result) { ElMessage.error('下推失败：服务器没有返回结果'); return }
    const failed = result.total_failure ?? 0
    const skipped = result.total_skipped ?? 0
    if (failed === 0 && skipped === 0) {
      ElMessage.success(`下推成功：${result.total_success ?? 0} 家子企业已按集团模板对齐行`)
      return
    }
    const counts = [`成功 ${result.total_success ?? 0} 家`]
    if (skipped) counts.push(`跳过 ${skipped} 家`)
    if (failed) counts.push(`失败 ${failed} 家`)
    // 弹窗关闭（点 × / Esc）会 reject，不算下推失败
    void ElMessageBox.alert(
      `${counts.join('，')}：\n${pushIssueLines(result)}`,
      '下推结果',
      { type: 'warning' },
    ).catch(() => undefined)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || err?.message || '下推失败')
  } finally {
    busy.value = false
  }
}
