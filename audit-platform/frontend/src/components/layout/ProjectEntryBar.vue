<!--
  ProjectEntryBar — 进入项目后顶栏下方的项目信息条。

  展示：项目名称（加粗紫色） + 审核年度 + 签字合伙人 + 项目经理 + 现场负责人。

  数据来源两处，互相补位：
  - `GET /api/projects/{id}`：项目名称、审核年度（`audit_year`）
  - `GET /api/projects/{id}/assignments`：按 role 取姓名

  🔴 项目表只有 partner_id / manager_id 两个人员列、且存的是账号 id 不是姓名，
     接口不下发姓名 ⇒ 三个角色的姓名一律从 assignments（含 staff_name）取。
     未委派该角色时显示「—」，不猜、不用 id 顶替姓名。
-->
<template>
  <div v-if="projectId" class="gt-pe-bar">
    <span class="gt-pe-bar__name" :title="projectName">{{ projectName || '—' }}</span>
    <span class="gt-pe-bar__field">
      <span class="gt-pe-bar__label">审核年度</span>
      <span class="gt-pe-bar__value">{{ auditYear || '—' }}</span>
    </span>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { projects as P_proj } from '@/services/apiPaths'

const props = defineProps<{
  /** 当前项目 id；空串表示不在项目上下文内（整条不渲染） */
  projectId: string
}>()

/**
 * 信息条上的三个人员字段 → 委派角色别名。
 *
 * 别名取自后端 `assignment_service.ROLE_MAP` 的键（同时收录英文与中文写法，
 * 历史数据两种都有）。「现场负责人」在 ROLE_MAP 里没有独立角色，
 * 业务上由审计员/助理担任 ⇒ 匹配 auditor / assistant 族。
 */
interface RoleField {
  key: string
  label: string
  /** 命中任一别名即认为是该角色 */
  aliases: readonly string[]
}

const ROLE_FIELDS: readonly RoleField[] = [
  { key: 'partner', label: '签字合伙人', aliases: ['signing_partner', 'partner', '合伙人', '签字合伙人'] },
  { key: 'manager', label: '项目经理', aliases: ['manager', '项目经理'] },
  { key: 'site', label: '现场负责人', aliases: ['auditor', '审计员', 'assistant', '助理'] },
]

const projectName = ref('')
const auditYear = ref<number | null>(null)
const roleNames = reactive<Record<string, string>>({})

async function load(pid: string) {
  projectName.value = ''
  auditYear.value = null
  for (const r of ROLE_FIELDS) roleNames[r.key] = ''
  if (!pid) return

  // 两个请求互不依赖，任一失败不拖垮另一个（信息条是展示件，失败就显示「—」）。
  //
  // 🔴 必须带 `_dedupe: false`：`utils/http` 对同 URL + 同 params 的并发 GET 去重时
  //    **取消先发的那一个**，而 projectStore.syncFromRoute / DetailProjectPanel 同时
  //    在取 `/api/projects/{id}`。本条实测被 net::ERR_ABORTED 掐掉、allSettled 把
  //    rejected 静默吃掉 ⇒ 整条信息条恒显示「—」。
  const [detail, assignments] = await Promise.allSettled([
    api.get(P_proj.detail(pid), { _dedupe: false } as any),
    api.get(P_proj.assignments(pid), { _dedupe: false } as any),
  ])

  if (detail.status === 'fulfilled') {
    const d = detail.value as any
    projectName.value = d?.name || d?.client_name || ''
    auditYear.value = d?.audit_year ?? null
  }

  if (assignments.status === 'fulfilled') {
    const raw = assignments.value as any
    const items: any[] = Array.isArray(raw) ? raw : raw?.items || []
    for (const field of ROLE_FIELDS) {
      const hit = items.find(a => field.aliases.includes(String(a?.role || '')))
      roleNames[field.key] = hit?.staff_name || ''
    }
  }
}

watch(() => props.projectId, pid => load(pid), { immediate: true })
</script>

<style scoped>
.gt-pe-bar {
  display: flex;
  align-items: center;
  gap: 22px;
  height: 32px;
  padding: 0 var(--gt-space-4);
  background: var(--gt-color-primary-bg, #f4f0fa);
  border-bottom: 1px solid var(--gt-color-border-light, #ebeef5);
  font-size: var(--gt-font-size-xs);
  flex-shrink: 0;
  overflow-x: auto;
  white-space: nowrap;
}
.gt-pe-bar__name {
  font-size: var(--gt-font-size-sm);
  font-weight: 700;
  color: var(--gt-color-primary, #4b2d77);
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 0;
}
.gt-pe-bar__field {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.gt-pe-bar__label { color: var(--gt-color-text-tertiary, #909399); }
.gt-pe-bar__value {
  color: var(--gt-color-text, #303133);
  font-weight: 500;
}
</style>
