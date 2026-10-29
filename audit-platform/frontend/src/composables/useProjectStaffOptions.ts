import { computed, ref } from 'vue'
import { listStaff, type StaffMember } from '@/services/staffApi'
import type { BasicInfo } from '@/stores/wizard'

export function useProjectStaffOptions(form: BasicInfo, publishNames: (names: Record<string, string>) => void) {
  const staff = ref<StaffMember[]>([])
  const teamLoading = ref(false)
  const teamFailed = ref(false)
  const loaded = ref(false)
  let pending: Promise<void> | null = null

  const partnerOptions = computed(() => staff.value.filter(person => person.title === '合伙人'))
  const selectedPartner = computed(() => partnerOptions.value.find(person => person.id === form.signing_partner_staff_id))
  const managerOptions = computed(() => {
    const partner = selectedPartner.value
    if (!partner) return []
    const uniqueName = partnerOptions.value.filter(person => person.name === partner.name).length === 1
    return staff.value.filter(person => person.partner_id
      ? person.partner_id === partner.id
      : uniqueName && person.partner_name === partner.name)
  })

  function restoreSelection() {
    if (!loaded.value) return
    // 旧项目只存用户编号，必须唯一匹配档案，不能按姓名或角色猜测。
    if (!form.signing_partner_staff_id && form.signing_partner_id) {
      const matches = partnerOptions.value.filter(person => person.user_id === form.signing_partner_id)
      if (matches.length === 1) form.signing_partner_staff_id = matches[0].id
    }
    if (!form.manager_staff_id && form.manager_id) {
      const matches = managerOptions.value.filter(person => person.user_id === form.manager_id)
      if (matches.length === 1) form.manager_staff_id = matches[0].id
    }
  }

  function onPartnerChange() {
    form.signing_partner_staff_id = form.signing_partner_staff_id || null
    form.signing_partner_id = selectedPartner.value?.user_id || null
    form.manager_staff_id = null
    form.manager_id = null
  }

  function onManagerChange() {
    form.manager_staff_id = form.manager_staff_id || null
    form.manager_id = managerOptions.value.find(person => person.id === form.manager_staff_id)?.user_id || null
  }

  const selectionError = computed(() => {
    const hasSelection = form.signing_partner_staff_id || form.manager_staff_id || form.signing_partner_id || form.manager_id
    if (!hasSelection) return ''
    if (teamLoading.value) return '人员档案正在加载，请稍后保存'
    if (!loaded.value || teamFailed.value) return '人员档案加载失败，请重试后保存'
    if (!selectedPartner.value) return '原签字合伙人无法对应人员档案，请重新选择'
    if ((form.manager_staff_id || form.manager_id) && !managerOptions.value.some(person => person.id === form.manager_staff_id)) {
      return '原项目经理不在所选合伙人名下，请重新选择'
    }
    return ''
  })

  function loadTeamStaff(): Promise<void> {
    if (pending) return pending
    teamLoading.value = true
    teamFailed.value = false
    pending = (async () => {
      try {
        const all: StaffMember[] = []
        let total = 0
        do {
          const page = await listStaff({ offset: all.length, limit: 200 })
          total = page.total
          if (!page.items.length && all.length < total) throw new Error('人员档案名单加载不完整')
          all.push(...page.items)
        } while (all.length < total)
        staff.value = all
        loaded.value = true
        const names: Record<string, string> = {}
        for (const person of all) {
          names[person.id] = person.name
          if (person.user_id) names[person.user_id] = person.name
        }
        publishNames(names)
        restoreSelection()
      } catch {
        teamFailed.value = true
      } finally {
        teamLoading.value = false
        pending = null
      }
    })()
    return pending
  }

  return {
    partnerOptions, managerOptions, selectedPartner, teamLoading, teamFailed, selectionError,
    loadTeamStaff, restoreSelection, onPartnerChange, onManagerChange,
  }
}
