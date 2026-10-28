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
  results?: Array<{ entities?: PushEntityResult[] }>
}

/** 逐家列出失败原因（只看第一个章节：按钮一次只下推当前章节）。 */
export function pushFailureLines(result: PushTemplateResult | null | undefined): string {
  return (result?.results?.[0]?.entities ?? [])
    .filter(e => e.status === 'failed')
    .map(e => `${e.company_name || e.node_key}：${e.reason}`)
    .join('\n')
}

/** 确认 → 取本章节绑定的模板版本 → 下推；结果用消息 / 弹窗告知。busy 只在真正请求期间为 true。 */
export async function pushConsolNoteTemplate(
  projectId: string, year: number, sectionId: string | undefined, busy: Ref<boolean>,
): Promise<void> {
  if (!projectId) return
  if (!sectionId) { ElMessage.warning('请先选择附注章节'); return }
  try {
    await ElMessageBox.confirm(
      '将把当前章节的明细模板下推到全部子企业，在子企业附注中预生成行骨架。已有数据不会被覆盖。确认？',
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
      activate_lock: true,
    })) as PushTemplateResult | null
    if (!result) { ElMessage.error('下推失败：服务器没有返回结果'); return }
    if ((result.total_failure ?? 0) === 0) {
      ElMessage.success(`下推成功：${result.total_success ?? 0} 家子企业已生成行骨架`)
      return
    }
    // 弹窗关闭（点 × / Esc）会 reject，不算下推失败
    void ElMessageBox.alert(
      `成功 ${result.total_success ?? 0} 家，失败 ${result.total_failure} 家：\n${pushFailureLines(result)}`,
      '下推结果',
      { type: 'warning' },
    ).catch(() => undefined)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || err?.message || '下推失败')
  } finally {
    busy.value = false
  }
}
