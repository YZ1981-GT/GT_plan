/**
 * 合并附注「⚡ 自动映射」（spec note-pull-header-formula-closure R6.3；后端 POST
 * /api/projects/{pid}/consol-note-detail-refresh/auto-map）：未绑定明细模板的章节按子企业单体附注建议建模板并绑定，
 * 行名精确 / 别名 / 集团下推行 / 已确认过的对应整组能确定的企业直接确认映射，其余企业留在「📋 明细映射」确认。
 * 不写合并附注数据（之后点「🔄 重新汇总」写入）。
 *
 * 从 ConsolNoteTab.vue 抽出：那个文件在行数白名单里，只许变小。
 */
import { h, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { autoMapDetail, type AutoMapResult } from '@/services/consolidationApi'

const LIST_LIMIT = 8

function limited(lines: string[]): string[] {
  return lines.length > LIST_LIMIT ? [...lines.slice(0, LIST_LIMIT), `……共 ${lines.length} 条`] : lines
}

/** 结果文字：确认了几家；哪些企业的哪些行要去「📋 明细映射」确认；失败 / 跳过的章节与原因。`ok` = 没有要用户处理的。 */
export function autoMapReport(result: AutoMapResult): { ok: boolean; text: string } {
  const s = result.summary
  const lines = [`已确认 ${s.confirmed_entities} 家企业的映射，${s.mapped} 个章节全部确认`
    + (s.templates_created ? `，新建 / 更新明细模板 ${s.templates_created} 个` : '')]
  const pending = result.sections.flatMap(sec => sec.pending.map(
    p => `${sec.section_id} ${p.company_name || p.node_key}：${p.labels.join('、')}`))
  if (pending.length) lines.push(`以下企业有行对不上，请在「📋 明细映射」确认：`, ...limited(pending))
  const failed = result.sections.filter(sec => sec.status === 'failed').map(sec => `${sec.section_id}：${sec.reason}`)
  if (failed.length) lines.push(`失败 ${failed.length} 个章节：`, ...limited(failed))
  const skipped = result.sections.filter(sec => sec.status === 'skipped')
  const onlySkipped = skipped.length > 0 && skipped.length === result.sections.length
  if (onlySkipped && skipped.length === 1) lines.push(`未映射：${skipped[0].reason}`)
  else if (skipped.length) lines.push(`${skipped.length} 个章节没有读到子企业单体附注，已跳过`)
  if (s.confirmed_entities) lines.push('点「🔄 重新汇总」把子企业数据写入合并附注')
  return { ok: !pending.length && !failed.length && !onlySkipped, text: lines.join('\n') }
}

/** 选范围（全部章节 / 仅当前章节）→ 自动映射 → 提示结果。返回结果（取消或失败返回 null）。 */
export async function runConsolNoteAutoMap(
  projectId: string, year: number, sectionId: string | undefined, busy: Ref<boolean>,
): Promise<AutoMapResult | null> {
  if (!projectId) return null
  let sectionIds: string[] | null = null
  try {
    await ElMessageBox.confirm(
      '按子企业单体附注自动建明细模板并确认映射：行名精确 / 别名 / 集团下推行 / 已确认过的对应直接确认，'
      + '其余企业留在「📋 明细映射」确认。不写合并附注数据。',
      '⚡ 自动映射',
      { type: 'info', distinguishCancelAndClose: true, confirmButtonText: '全部章节', cancelButtonText: '仅当前章节' },
    )
  } catch (action) {
    if (action !== 'cancel') return null  // 点 × / Esc：不做
    if (!sectionId) { ElMessage.warning('请先选择附注章节'); return null }
    sectionIds = [sectionId]
  }
  busy.value = true
  try {
    const result = await autoMapDetail(projectId, { year, section_ids: sectionIds })
    const report = autoMapReport(result)
    if (report.ok) ElMessage.success(report.text.split('\n').join('；'))
    else {
      // 渲染上下文外的 VNode 不带 scopeId ⇒ 只用内联样式
      void ElMessageBox.alert(h('div', { style: 'white-space: pre-line; max-height: 50vh; overflow: auto' }, report.text),
        '⚡ 自动映射结果', { type: 'warning' }).catch(() => undefined)
    }
    return result
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || err?.message || '自动映射失败')
    return null
  } finally {
    busy.value = false
  }
}
