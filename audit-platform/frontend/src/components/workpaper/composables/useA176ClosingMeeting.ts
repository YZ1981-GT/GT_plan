/**
 * useA176ClosingMeeting - A17-6 总结会会议纪要 数据管理 + 持久化
 * 升级版：10项会议议题 + 元信息 + 双模式 + AI + 双向回写
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

export interface A176MetaInfo {
  client_name: string
  period: string
  preparer: string
  preparer_date: string
  reviewer: string
  reviewer_date: string
  index_no: string
  meeting_place: string
  meeting_time: string
  organizer: string
  convener: string
  recorder: string
  attendees: string
}

export interface A176Agenda { [key: number]: string }

export const AGENDA_ITEMS: { index: number; title: string }[] = [
  { index: 1, title: '总体审计意见' },
  { index: 2, title: '审计计划是否充分执行的评估' },
  { index: 3, title: '特别风险及其应对措施及审计结论' },
  { index: 4, title: '内部控制测试和审计风险' },
  { index: 5, title: '已发现的错报和重要情况汇总' },
  { index: 6, title: '其他重要的会计和审计事项' },
  { index: 7, title: '会计师事务所资源与独立性' },
  { index: 8, title: '确定拟发表的审计意见' },
  { index: 9, title: '拟发表的审计意见' },
  { index: 10, title: '其他' },
]

export const AGENDA_GUIDANCE: Record<number, string> = {
  1: '【联动A17-5第5项+A17-1】确认审计过程中发现的所有错报均已恰当评价与处理；已获取充分适当的审计证据支持拟发表的审计意见。系统自动核对：A17-5-1核对表第5项(审计报告意见类型恰当)是否已勾选"是"。',
  2: '【联动A17-5第3/9/13/14/15项+B50】评估审计计划执行充分性：①总体审计策略和具体审计计划是否全部执行(A17-5#9)；②各项审计程序是否全部完成(A17-5#13)；③审计范围是否未受到限制(A17-5#14)；④计划阶段确定的风险是否仍旧恰当(A17-5#15)。如有未执行程序需说明替代方案。',
  3: '【联动B50+A17-5第4/15/16项】①列示B50风险评估矩阵中标注为"特别风险"的项目；②逐项评估应对措施是否足够；③是否恰当应对审计过程中识别的舞弊迹象(A17-5#16)。系统可自动拉取B50中severity=high的风险项。',
  4: '【联动B22A/B22B+A17-5第6项】①汇总B22A内控五要素测试结果(element_score)；②列示B22B内控缺陷评价表中的重大/重要缺陷；③讨论是否出现新的情况需调整审计方案；④已识别缺陷是否已与管理层/治理层沟通(A17-5#8)。',
  5: '【联动A13+A17-5第31/33/34/35项】①从A13错报汇总自动拉取：已更正错报合计、未更正错报合计、推断误差；②评估未更正错报是否超过重要性水平(对比B15)；③是否已将所有错报与管理层沟通(A17-5#34)；④未更正错报汇总表是否已由治理层签章确认(A17-5#35)。',
  6: '【联动A17-5第17-25项】逐项讨论：①政府补助核算方法适当性(#17)；②终止经营列报(#18)；③期后事项(#19→A11)；④或有事项(#20)；⑤承诺事项(#21)；⑥关联方交易(#22)；⑦持续经营(#23→A15)；⑧其他信息(#24)；⑨会计估计(#25)。如无相关事项可标注"不适用"。',
  7: '【联动A17-7+A17-5第12/39-41项】①确认项目组全体成员独立性声明书(A17-7)已签署；②如涉及组成部分注册会计师是否满意其工作(A17-5#12)；③项目质量复核合伙人复核是否完成(A17-5#39)；④质量控制复核人复核是否完成(A17-5#40)；⑤事务所资源是否充分、是否需利用专家。',
  8: '【联动A17-5第5/36项+A17-1第8章】根据议题1-7的讨论结论，综合确定审计意见类型：①无保留意见；②保留意见(说明范围限制/会计分歧)；③否定意见(说明重大错报)；④无法表示意见(说明范围限制)。董事会/管理层是否接受已审计财务报表(A17-5#36)。',
  9: '【联动A17-2-1(KAM)+A17-5第29项】①明确审计报告最终措辞；②如涉及关键审计事项(KAM)，确认已确定并适当表述(A17-5#29)；③如为非无保留意见，完整描述审计报告中的保留/否定段落措辞；④确认审计报告日期。',
  10: '【联动A17-5第44-46项】①上年度审计结转事项是否全部处理(A17-5#44)；②下年度审计需考虑的重要事项备忘录是否整理完毕(A17-5#45)；③所有追查事项是否已满意解决(A17-5#46)；④其他需在总结会中讨论的事项。',
}

export interface A176ProjectContext {
  client_name: string
  period: string
  current_user: string
}

export interface UseA176Return {
  loading: Ref<boolean>
  metaInfo: Ref<A176MetaInfo>
  agenda: Ref<A176Agenda>
  projectContext: Ref<A176ProjectContext>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  lastSavedAt: Ref<Date | null>
  saveError: Ref<boolean>
  loadData: (wpId?: string) => Promise<void>
  updateMeta: (field: keyof A176MetaInfo, value: string) => void
  updateAgenda: (index: number, value: string) => void
  flushPendingSaves: () => Promise<void>
}

export function useA176ClosingMeeting(wpId: Ref<string>): UseA176Return {
  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const lastSavedAt = ref<Date | null>(null)
  const saveError = ref(false)

  const metaInfo = ref<A176MetaInfo>({
    client_name: '', period: '', preparer: '', preparer_date: '',
    reviewer: '', reviewer_date: '', index_no: 'A17-6',
    meeting_place: '', meeting_time: '', organizer: '', convener: '', recorder: '',
    attendees: '',
  })

  const agenda = ref<A176Agenda>({ 1: '', 2: '', 3: '', 4: '', 5: '', 6: '', 7: '', 8: '', 9: '', 10: '' })

  const projectContext = ref<A176ProjectContext>({ client_name: '', period: '', current_user: '' })

  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  async function loadData(id?: string) {
    const targetId = id || wpId.value
    if (!targetId) return
    loading.value = true
    try {
      const res = await api.get<any>(
        `/api/workpapers/${targetId}/render-config?force_component_type=a17-6-closing-meeting`,
        { _silent: true } as any,
      )
      const htmlData = res?.sheets?.[0]?.html_data ?? res
      if (htmlData?.meta_info) Object.assign(metaInfo.value, htmlData.meta_info)
      if (htmlData?.agenda) {
        for (const [k, v] of Object.entries(htmlData.agenda)) {
          const idx = parseInt(k)
          if (idx >= 1 && idx <= 10) agenda.value[idx] = (v as string) || ''
        }
      }
      if (htmlData?.project_context) Object.assign(projectContext.value, htmlData.project_context)
    } catch { /* silent */ }
    finally { loading.value = false }
  }

  function updateMeta(field: keyof A176MetaInfo, value: string) {
    metaInfo.value[field] = value
    const itemId = `a176-meta-${field}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: value, remark: null })
    scheduleSave()
  }

  function updateAgenda(index: number, value: string) {
    agenda.value[index] = value
    const itemId = `a176-agenda-${index}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value })
    scheduleSave()
  }

  function scheduleSave() {
    saveStatus.value = 'unsaved'
    saveError.value = false
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => { saveTimer = null; doSave() }, 2000)
  }

  async function doSave(retryCount = 0) {
    if (pendingItems.size === 0) return
    const items = [...pendingItems.values()]
    pendingItems.clear()
    saveStatus.value = 'saving'
    try {
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, { items })
      saveStatus.value = 'saved'
      lastSavedAt.value = new Date()
      saveError.value = false
    } catch {
      if (retryCount < 3) {
        for (const item of items) pendingItems.set(item.item_id, item)
        setTimeout(() => doSave(retryCount + 1), 1000 * (retryCount + 1))
        return
      }
      saveStatus.value = 'unsaved'
      saveError.value = true
      ElMessage.warning('保存失败，请检查网络后重试')
    }
  }

  async function flushPendingSaves(): Promise<void> {
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null }
    await doSave()
  }

  return {
    loading, metaInfo, agenda, projectContext,
    saveStatus, lastSavedAt, saveError,
    loadData, updateMeta, updateAgenda, flushPendingSaves,
  }
}
