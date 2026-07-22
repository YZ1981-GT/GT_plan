/**
 * B60 适用性矩阵 — flags / SCOT / B60D 存档 / 计划版本
 */
import { computed, ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'

export type B60FlagKey =
  | 'integrated_audit'
  | 'listed_or_ipo'
  | 'soe_annual'
  | 'needs_regulatory_filing'
  | 'needs_it_audit'
  | 'it_team_executes'
  | 'uses_expert'

export interface B60FlagDef {
  label: string
  wp_codes: string[]
}

export interface B60MissingAttachment {
  flag: string
  flag_label: string
  wp_code: string
  present: boolean
}

export interface B60QcFinding {
  code: string
  severity: string
  message: string
  suggested_action?: string
  location?: Record<string, unknown>
}

export interface B60ScotRow {
  scot_id: string
  name: string
  cycle_code: string
  risk_id: string
  procedure_wp_index: string
  rely_on_controls: string
}

export interface B60Simplification {
  is_pie: boolean
  collapse_sections: Array<{ id: string; title: string; default: string }>
  must_keep_sections: string[]
  note: string
}

export interface B60AttachmentFlagsState {
  flags: Record<string, boolean>
  flag_defs: Record<string, B60FlagDef>
  missing_attachments: B60MissingAttachment[]
  always_required_missing: string[]
  materiality_reference: string | null
  plan_version: number | null
  generated_wp_codes?: string[]
  simplification?: B60Simplification | null
  scot_rows?: B60ScotRow[]
  b60d_archive?: {
    filed_plan_version?: number
    delivery_date?: string
    recipient?: string
    delivery_method?: string
    consistent_with_b60?: boolean
  } | null
}

function emptyScotRow(): B60ScotRow {
  return {
    scot_id: '',
    name: '',
    cycle_code: '',
    risk_id: '',
    procedure_wp_index: '',
    rely_on_controls: '',
  }
}

export function useB60AttachmentMatrix(projectId: Ref<string | undefined> | (() => string | undefined)) {
  const loading = ref(false)
  const saving = ref(false)
  const state = ref<B60AttachmentFlagsState | null>(null)
  const qcFindings = ref<B60QcFinding[]>([])
  const materialityRef = ref('')
  const scotRows = ref<B60ScotRow[]>([])
  const b60dFiledVersion = ref<number | null>(null)
  const b60dDeliveryDate = ref('')
  const b60dRecipient = ref('')
  const autoGenerate = ref(true)

  const pid = () => (typeof projectId === 'function' ? projectId() : projectId.value)

  const missingCount = computed(
    () =>
      (state.value?.missing_attachments.filter((m) => !m.present).length || 0) +
      (state.value?.always_required_missing.length || 0),
  )

  function applyState(res: B60AttachmentFlagsState) {
    state.value = res
    materialityRef.value = res.materiality_reference || ''
    scotRows.value = (res.scot_rows || []).map((r) => ({ ...emptyScotRow(), ...r }))
    const arch = res.b60d_archive
    b60dFiledVersion.value = arch?.filed_plan_version ?? res.plan_version ?? null
    b60dDeliveryDate.value = arch?.delivery_date || ''
    b60dRecipient.value = arch?.recipient || ''
  }

  async function load() {
    const id = pid()
    if (!id) return
    loading.value = true
    try {
      const res = (await api.get(`/api/projects/${id}/b60/attachment-flags`)) as B60AttachmentFlagsState
      applyState(res)
      await loadQc()
    } catch (e: any) {
      ElMessage.error(e?.message || '加载 B60 适用性矩阵失败')
    } finally {
      loading.value = false
    }
  }

  async function loadQc() {
    const id = pid()
    if (!id) return
    try {
      const res = (await api.get(`/api/projects/${id}/b60/qc-status`)) as { findings: B60QcFinding[] }
      qcFindings.value = res.findings || []
    } catch {
      qcFindings.value = []
    }
  }

  async function save() {
    const id = pid()
    if (!id || !state.value) return
    saving.value = true
    try {
      const res = (await api.put(`/api/projects/${id}/b60/attachment-flags`, {
        flags: state.value.flags,
        materiality_reference: materialityRef.value || null,
        auto_generate_missing: autoGenerate.value,
      })) as B60AttachmentFlagsState
      applyState(res)
      await loadQc()
      const gen = res.generated_wp_codes || []
      if (gen.length) {
        ElMessage.success(`矩阵已保存，已自动生成：${gen.join(', ')}`)
      } else {
        ElMessage.success('适用性矩阵已保存')
      }
    } catch (e: any) {
      ElMessage.error(e?.message || '保存失败')
    } finally {
      saving.value = false
    }
  }

  async function saveScotRows() {
    const id = pid()
    if (!id) return
    saving.value = true
    try {
      await api.put(`/api/projects/${id}/b60/scot-rows`, { rows: scotRows.value })
      ElMessage.success('SCOT+ 行已保存')
      await loadQc()
    } catch (e: any) {
      ElMessage.error(e?.message || 'SCOT+ 保存失败')
    } finally {
      saving.value = false
    }
  }

  async function saveB60dArchive() {
    const id = pid()
    if (!id) return
    if (b60dFiledVersion.value == null) {
      ElMessage.warning('请填写报送对应的计划版本号')
      return
    }
    saving.value = true
    try {
      const res = (await api.put(`/api/projects/${id}/b60/b60d-archive`, {
        filed_plan_version: b60dFiledVersion.value,
        delivery_date: b60dDeliveryDate.value || null,
        recipient: b60dRecipient.value || null,
        consistent_with_b60: true,
      })) as { version_match?: boolean; plan_version?: number }
      if (res.version_match === false) {
        ElMessage.warning(`已保存，但报送版本 ≠ 当前计划 v${res.plan_version}`)
      } else {
        ElMessage.success('B60D 存档信息已保存')
      }
      await load()
    } catch (e: any) {
      ElMessage.error(e?.message || 'B60D 存档保存失败')
    } finally {
      saving.value = false
    }
  }

  async function bumpPlanVersion() {
    const id = pid()
    if (!id) return
    try {
      const { value: reason } = await ElMessageBox.prompt(
        '确认第十五章存在重大更新？将递增计划版本号。请填写更新理由：',
        '第十五章重大更新',
        {
          confirmButtonText: '确认并升版',
          cancelButtonText: '取消',
          inputPlaceholder: '如：重要性修订 / 范围变更 / 风险结论变更',
          inputValidator: (v) => (!!v && !!String(v).trim()) || '必须填写理由',
        },
      )
      saving.value = true
      const res = (await api.post(`/api/projects/${id}/b60/plan-update`, {
        bump_version: true,
        confirm_major_change: true,
        reason: String(reason).trim(),
        materiality_reference: materialityRef.value || null,
        flags: state.value?.flags,
      })) as { plan_version: number }
      ElMessage.success(`计划版本已更新为 v${res.plan_version}`)
      await load()
    } catch (e: any) {
      if (e === 'cancel' || e?.action === 'cancel') return
      ElMessage.error(e?.message || e?.detail?.detail || '更新计划版本失败')
    } finally {
      saving.value = false
    }
  }

  function setFlag(key: string, value: boolean) {
    if (!state.value) return
    state.value.flags = { ...state.value.flags, [key]: value }
    if (key === 'it_team_executes' && value) {
      state.value.flags.needs_it_audit = true
    }
  }

  function addScotRow() {
    scotRows.value = [...scotRows.value, emptyScotRow()]
  }

  function removeScotRow(idx: number) {
    scotRows.value = scotRows.value.filter((_, i) => i !== idx)
  }

  return {
    loading,
    saving,
    state,
    qcFindings,
    materialityRef,
    scotRows,
    b60dFiledVersion,
    b60dDeliveryDate,
    b60dRecipient,
    autoGenerate,
    missingCount,
    load,
    save,
    saveScotRows,
    saveB60dArchive,
    bumpPlanVersion,
    setFlag,
    addScotRow,
    removeScotRow,
    loadQc,
  }
}
