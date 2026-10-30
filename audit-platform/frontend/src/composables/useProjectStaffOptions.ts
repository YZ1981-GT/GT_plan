import { computed, ref } from 'vue'
import { api } from '@/services/apiProxy'
import type { BasicInfo } from '@/stores/wizard'

/**
 * 建项向导的签字合伙人 / 项目经理下拉数据源。
 *
 * 🔴 数据源 = users 表（登录账号），不是 staff_members（人员档案）。
 * 用户 2026-10-30 明确要求：「新建项目时合伙人和项目经理数据应该取得是 users 表」。
 *
 * 由此带来的取舍（已向用户说明并确认）：
 * - 两个下拉按 users.role 过滤（partner / manager），彼此**不联动** ——
 *   users 表没有「某经理归属哪个合伙人」的字段，无法做级联过滤。
 *   原先取人员档案时可按 staff.partner_id / partner_name 级联，改回 users 后该能力不存在。
 * - 只列启用账号（is_active）：停用账号不应再被指派为签字人。
 */
interface TeamUserOption {
  id: string
  username: string
  email?: string
  role: string
  is_active?: boolean
}

export function useProjectStaffOptions(form: BasicInfo, publishNames: (names: Record<string, string>) => void) {
  const users = ref<TeamUserOption[]>([])
  const teamLoading = ref(false)
  const teamFailed = ref(false)
  const loaded = ref(false)
  let pending: Promise<void> | null = null

  /** 仅启用账号可被指派（停用账号登录即 401，指派上去也用不了） */
  const activeUsers = computed(() => users.value.filter(u => u.is_active !== false))

  const partnerOptions = computed(() => activeUsers.value.filter(u => u.role === 'partner'))
  /** 不按合伙人过滤：users 表无归属关系（见文件头说明） */
  const managerOptions = computed(() => activeUsers.value.filter(u => u.role === 'manager'))

  const selectedPartner = computed(() => partnerOptions.value.find(u => u.id === form.signing_partner_id))

  function restoreSelection() {
    // 账号编号即下拉值，无需按姓名或职级反查（这是取 users 相对取档案的简化）
  }

  function onPartnerChange() {
    form.signing_partner_id = form.signing_partner_id || null
    // 兼容字段：后端 STAFF_FIELDS 协议按「字段是否提交」区分未提交与显式清空，
    // 这里显式置空，表示本次保存走账号协议、不使用人员档案选择。
    form.signing_partner_staff_id = null
  }

  function onManagerChange() {
    form.manager_id = form.manager_id || null
    form.manager_staff_id = null
  }

  const selectionError = computed(() => {
    const hasSelection = form.signing_partner_id || form.manager_id
    if (!hasSelection) return ''
    if (teamLoading.value) return '账号列表正在加载，请稍后保存'
    if (!loaded.value || teamFailed.value) return '账号列表加载失败，请重试后保存'
    if (form.signing_partner_id && !selectedPartner.value) {
      return '原签字合伙人账号不可用（已停用或角色变更），请重新选择'
    }
    if (form.manager_id && !managerOptions.value.some(u => u.id === form.manager_id)) {
      return '原项目经理账号不可用（已停用或角色变更），请重新选择'
    }
    return ''
  })

  function loadTeamStaff(): Promise<void> {
    if (pending) return pending
    teamLoading.value = true
    teamFailed.value = false
    pending = (async () => {
      try {
        // GET /api/users/ 返回全量账号（无分页），含 is_active
        const data = await api.get('/api/users/')
        const list = (Array.isArray(data) ? data : []) as TeamUserOption[]
        users.value = list
        loaded.value = true
        const names: Record<string, string> = {}
        for (const u of list) names[u.id] = u.username
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
