/**
 * useD4PolicyCheck — D4-5 营业收入会计政策检查逻辑
 *
 * 对齐源模板「D4-5 营业收入-会计政策（Leap-常规程序）」真实结构：
 * 一、审计目标（固定）
 * 二、审计过程
 *   （一）经营模式：产品应用场景/订单获取/产销模式/销售模式/定价方式/交货方式（6项）
 *   （二）会计政策：按业务类型（销售商品收入/贸易业务/…）分组，每组含 收入会计政策/同行业相关政策/合理性分析
 *   （三）信用政策
 * 三、审计说明
 * 四、审计结论
 * + 提示1/提示2（编制指导，只读折叠）
 *
 * 持久化：item_id 前缀 `D4-5-{fieldKey}`
 *
 * Requirements: 7.1-7.7, 21.3
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { UseD4BaseOptions } from './useD4Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 经营模式 6 项 */
export interface BizModelItem {
  key: string
  label: string
  content: string
}

/** 会计政策业务类型分组（可动态增删） */
export interface PolicyGroup {
  id: string
  bizName: string          // 业务类型名（如 销售商品收入 / 贸易业务）
  revenuePolicy: string    // 收入会计政策
  industryPolicy: string   // 同行业相关政策
  rationalityAnalysis: string  // 合理性分析
}

export interface PolicyCheckReturn {
  // 审计目标（只读固定文本）
  auditObjective: Ref<string>
  // 经营模式 6 项
  bizModelItems: Ref<BizModelItem[]>
  updateBizModel: (key: string, value: string) => void
  // 会计政策分组
  policyGroups: Ref<PolicyGroup[]>
  addPolicyGroup: () => void
  removePolicyGroup: (id: string) => void
  updatePolicyGroup: (id: string, field: keyof Omit<PolicyGroup, 'id'>, value: string) => void
  // 信用政策
  creditPolicy: Ref<string>
  updateCreditPolicy: (value: string) => void
  // 审计说明 / 审计结论
  auditNote: Ref<string>
  auditConclusion: Ref<string>
  updateAuditNote: (value: string) => void
  updateAuditConclusion: (value: string) => void
  // 进度
  completedCount: ComputedRef<number>
  totalCount: ComputedRef<number>
  progress: ComputedRef<number>
  // 编制提示（只读）
  guidanceTips: { title: string; content: string }[]
}

// ─── Constants ───────────────────────────────────────────────────────────────

const AUDIT_OBJECTIVE = '与营业收入有关的金额及其他数据已恰当记录，相关披露已得到恰当计量和描述。'

const AUDIT_CONCLUSION_DEFAULT =
  '被审计单位收入确认会计政策和会计估计与企业会计准则的规定一致，反映了被审计单位经济业务的实际情况，与同行业公司相比不存在显著差异，且得到一贯性地执行。'

const BIZ_MODEL_DEFS: Array<{ key: string; label: string }> = [
  { key: 'scene', label: '1. 产品应用场景' },
  { key: 'order', label: '2. 订单获取方式/渠道，合同签订及履行方式' },
  { key: 'produce', label: '3. 产销模式' },
  { key: 'sales', label: '4. 销售模式' },
  { key: 'pricing', label: '5. 定价方式' },
  { key: 'delivery', label: '6. 交货方式' },
]

/** 编制提示（源模板底部提示1/提示2，只读展示） */
const GUIDANCE_TIPS: { title: string; content: string }[] = [
  {
    title: '提示1：会计政策描述要求',
    content:
      '会计政策应描述收入确认和计量所采用的会计政策、对于确定收入确认的时点和金额具有重大影响的判断以及这些判断的变更，包括确定履约进度的方法及采用该方法的原因、评估客户取得所转让商品控制权时点的相关判断，在确定交易价格、估计计入交易价格的可变对价、分摊交易价格以及计量预期将退还给客户的款项等类似义务时所采用的方法、输入值和假设等。',
  },
  {
    title: '提示2：了解和记录经营模式时注意以下方面',
    content:
      '(1)产品应用场景，包括产品种类、行业协会（如有）、监管部门网站（如有）、用途、市场空间、行业前景等；\n' +
      '(2)订单获取方式/渠道，合同签订及履行方式应来源于销售部门，若有多条业务线，应全面了解；了解该内容，可以整体评估收入的可持续性、销售费用的完整性，并与同行业对比。实质性核查程序，应考虑该因素，如招投标、关联关系等；\n' +
      '(3)以销定产（加合理库存）模式：①要分析合理库存的制定方法、合理性、一惯性，存货是否积压，是否有减值迹象；②剔除合理库存后，存货是否有在手订单覆盖，业务是否可持续，存货是否会积压？③是否与产能匹配？以产定销，是否与产品的竞争力匹配，是否与同行业一致？\n' +
      '(4)如果被审计单位采用代理模式、经销商模式，了解其原因及合理性，并通过访谈获取被审计单位选择经销商的原则。部分形式上的直接销售，可能包含转销，要结合产品与客户的业务类型、规模、合同条款，分析识别。经销、代销、转销模式是否符合行业惯例，应穿透至最终客户检查；如何规定控制权转移，可能影响收入政策。\n' +
      '(5)了解并记录被审计单位定价方式时应分析主动权，并结合其他描述、同行业分析合理性。是否存在可变对价，可能影响收入政策。\n' +
      '(6)了解并记录被审计单位送货还是取货、运输工具、途中耗时等；交货周期（合同签订至交付日），分析大额订单存货、生产周期是否匹配；被审计单位在货物流转前是否取得控制权；验收方式；退换货政策，质保政策。',
  },
]

let _gid = 0
function nextGroupId(): string {
  _gid += 1
  return `pg-${Date.now()}-${_gid}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD4PolicyCheck(options: UseD4BaseOptions): PolicyCheckReturn {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── State ───────────────────────────────────────────────────────────
  const auditObjective = ref(AUDIT_OBJECTIVE)
  const bizModelItems = ref<BizModelItem[]>(
    BIZ_MODEL_DEFS.map(d => ({ key: d.key, label: d.label, content: '' })),
  )
  const policyGroups = ref<PolicyGroup[]>([])
  const creditPolicy = ref('')
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load from allResponses ──────────────────────────────────────────
  function loadFromResponses(): void {
    // 经营模式
    for (const item of bizModelItems.value) {
      const r = allResponses.value.get(`D4-5-biz-${item.key}`)
      item.content = r?.remark || ''
    }
    // 信用政策 / 审计说明 / 审计结论
    creditPolicy.value = allResponses.value.get('D4-5-credit-policy')?.remark || ''
    auditNote.value = allResponses.value.get('D4-5-audit-note')?.remark || ''
    const concl = allResponses.value.get('D4-5-audit-conclusion')?.remark
    auditConclusion.value = concl != null ? concl : AUDIT_CONCLUSION_DEFAULT
    // 会计政策分组（存 JSON）
    const groupsRaw = allResponses.value.get('D4-5-policy-groups')?.remark
    if (groupsRaw) {
      try {
        const parsed = JSON.parse(groupsRaw)
        if (Array.isArray(parsed) && parsed.length) {
          policyGroups.value = parsed.map((g: any) => ({
            id: g.id || nextGroupId(),
            bizName: g.bizName || '',
            revenuePolicy: g.revenuePolicy || '',
            industryPolicy: g.industryPolicy || '',
            rationalityAnalysis: g.rationalityAnalysis || '',
          }))
        }
      } catch { /* ignore */ }
    }
    // 无分组时给默认两组（销售商品收入 / 贸易业务）
    if (policyGroups.value.length === 0) {
      policyGroups.value = [
        { id: nextGroupId(), bizName: '销售商品收入', revenuePolicy: '', industryPolicy: '', rationalityAnalysis: '' },
        { id: nextGroupId(), bizName: '贸易业务', revenuePolicy: '', industryPolicy: '', rationalityAnalysis: '' },
      ]
    }
  }

  watch(
    () => allResponses.value.get('D4-5-biz-scene')?.remark,
    () => loadFromResponses(),
    { immediate: true },
  )

  // ─── Progress（统计已填写字段占比） ──────────────────────────────────
  const totalCount = computed(() => {
    // 6经营模式 + 信用政策 + 审计说明 + 每组3字段
    return 6 + 1 + 1 + policyGroups.value.length * 3
  })
  const completedCount = computed(() => {
    let n = 0
    for (const item of bizModelItems.value) if (item.content.trim()) n++
    if (creditPolicy.value.trim()) n++
    if (auditNote.value.trim()) n++
    for (const g of policyGroups.value) {
      if (g.revenuePolicy.trim()) n++
      if (g.industryPolicy.trim()) n++
      if (g.rationalityAnalysis.trim()) n++
    }
    return n
  })
  const progress = computed(() => {
    if (totalCount.value === 0) return 0
    return Math.round((completedCount.value / totalCount.value) * 100)
  })

  // ─── Mutations ───────────────────────────────────────────────────────
  function updateBizModel(key: string, value: string): void {
    if (readonly.value) return
    const item = bizModelItems.value.find(i => i.key === key)
    if (!item) return
    item.content = value
    persist(`D4-5-biz-${key}`, value)
  }

  function updateCreditPolicy(value: string): void {
    if (readonly.value) return
    creditPolicy.value = value
    persist('D4-5-credit-policy', value)
  }

  function updateAuditNote(value: string): void {
    if (readonly.value) return
    auditNote.value = value
    persist('D4-5-audit-note', value)
  }

  function updateAuditConclusion(value: string): void {
    if (readonly.value) return
    auditConclusion.value = value
    persist('D4-5-audit-conclusion', value)
  }

  function addPolicyGroup(): void {
    if (readonly.value) return
    policyGroups.value.push({
      id: nextGroupId(), bizName: '', revenuePolicy: '', industryPolicy: '', rationalityAnalysis: '',
    })
    persistGroups()
  }

  function removePolicyGroup(id: string): void {
    if (readonly.value) return
    policyGroups.value = policyGroups.value.filter(g => g.id !== id)
    persistGroups()
  }

  function updatePolicyGroup(id: string, field: keyof Omit<PolicyGroup, 'id'>, value: string): void {
    if (readonly.value) return
    const g = policyGroups.value.find(x => x.id === id)
    if (!g) return
    ;(g as any)[field] = value
    persistGroups()
  }

  // ─── Persistence ────────────────────────────────────────────────────
  function persist(itemId: string, value: string): void {
    allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: value })
    debounceSave()
  }

  function persistGroups(): void {
    const json = JSON.stringify(policyGroups.value)
    allResponses.value.set('D4-5-policy-groups', { item_id: 'D4-5-policy-groups', conclusion: null, remark: json })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    try {
      const keys = [
        ...bizModelItems.value.map(i => `D4-5-biz-${i.key}`),
        'D4-5-credit-policy', 'D4-5-audit-note', 'D4-5-audit-conclusion', 'D4-5-policy-groups',
      ]
      const items = keys.map(k => allResponses.value.get(k)).filter(Boolean)
      window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } }))
    } catch { /* silent */ }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    auditObjective,
    bizModelItems,
    updateBizModel,
    policyGroups,
    addPolicyGroup,
    removePolicyGroup,
    updatePolicyGroup,
    creditPolicy,
    updateCreditPolicy,
    auditNote,
    auditConclusion,
    updateAuditNote,
    updateAuditConclusion,
    completedCount,
    totalCount,
    progress,
    guidanceTips: GUIDANCE_TIPS,
  }
}

export default useD4PolicyCheck
