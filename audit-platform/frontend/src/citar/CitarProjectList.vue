<template>
  <div class="list-screen">
    <header class="list-topbar">
      <img class="list-topbar__logo" src="/logo-citar-light.png" alt="致同 CITAR" />
      <div class="list-topbar__user">
        <span>{{ authStore.username }}</span>
        <button v-if="isAdmin" class="list-topbar__logout" type="button" @click="router.push('/settings/users')">账号权限</button>
        <button class="list-topbar__logout" type="button" @click="logout">退出登录</button>
      </div>
    </header>

    <main class="list-main">
      <div class="list-toolbar">
        <h1 class="list-toolbar__title">项目列表</h1>
        <span v-if="!loading && !loadError" class="list-toolbar__count">
          {{ picking ? `已勾选 ${selected.size} 个` : `共 ${projects.length} 个项目` }}
        </span>

        <div class="list-toolbar__actions">
          <template v-if="mode === 'delete'">
            <button class="list-button" type="button" @click="exitMode">取消</button>
            <button class="list-button list-button--danger" type="button" :disabled="selected.size === 0" @click="confirming = true">确认删除</button>
          </template>
          <template v-else-if="mode === 'edit'">
            <button class="list-button" type="button" @click="exitMode">取消</button>
            <button class="list-button list-button--primary" type="button" :disabled="selected.size !== 1" @click="confirmEdit">确认修改</button>
          </template>
          <template v-else>
            <button class="list-button" type="button" disabled title="本期暂未开放">项目导入</button>
            <button class="list-button" type="button" disabled title="本期暂未开放">项目导出</button>
            <button class="list-button" type="button" :disabled="projects.length === 0" @click="mode = 'delete'">删除项目</button>
            <button class="list-button" type="button" :disabled="projects.length === 0" @click="mode = 'edit'">修改项目</button>
            <button class="list-button list-button--primary" type="button" @click="router.push('/projects/new')">新建项目</button>
          </template>
        </div>
      </div>

      <p v-if="mode === 'delete'" class="list-notice">勾选要删除的项目，删除后进入回收站。</p>
      <p v-else-if="mode === 'edit'" class="list-notice list-notice--info">勾选要修改的项目，一次只能修改一个。</p>

      <p v-if="loadError" class="list-notice">{{ loadError }}</p>

      <div v-if="loading" class="list-empty">
        <p class="list-empty__title">正在载入项目列表…</p>
      </div>
      <div v-else-if="projects.length === 0 && !loadError" class="list-empty">
        <p class="list-empty__title">暂无项目</p>
        <p class="list-empty__hint">点击右上角「新建项目」创建第一个项目</p>
      </div>
      <div v-else class="list-cards">
        <button
          v-for="p in projects"
          :key="p.id"
          type="button"
          class="list-card"
          :class="cardClass(p.id)"
          @click="picking ? toggle(p.id) : openProject(p)"
        >
          <span
            v-if="picking"
            class="list-check"
            :class="{ 'list-check--on': selected.has(p.id), 'list-check--single': mode === 'edit' }"
            aria-hidden="true"
          >{{ selected.has(p.id) ? '✓' : '' }}</span>

          <div>
            <div class="list-card__head">
              <span class="list-card__name">{{ p.short_name || p.name }}</span>
              <span v-if="p.project_type" class="list-tag list-tag--type">{{ getStatusLabel('project_type', p.project_type) }}</span>
              <span v-for="tag in projectTags(p)" :key="tag.label" class="list-tag" :class="`list-tag--${tag.tone}`">{{ tag.label }}</span>
            </div>
            <div class="list-card__meta">
              <span>客户：{{ p.client_name || '—' }}</span>
              <span>审核年度：{{ p.audit_year || '—' }}</span>
            </div>
          </div>

          <div class="list-card__side">
            <span class="list-card__node">{{ statusLabel(p.status) }}</span>
            <span>{{ formatUpdatedAt(p.updated_at || p.created_at) }}</span>
          </div>
        </button>
      </div>
    </main>

    <!-- 删除确认：列出项目名称，看清自己要删什么 -->
    <div v-if="confirming" class="list-dialog__backdrop">
      <div class="list-dialog" role="dialog" aria-modal="true">
        <h2 class="list-dialog__title">确认删除以下项目？</h2>
        <ul class="list-dialog__items">
          <li v-for="p in selectedProjects" :key="p.id">
            {{ p.short_name || p.name }}
            <span class="list-dialog__sub">{{ p.client_name || '—' }} · {{ p.audit_year || '—' }}</span>
          </li>
        </ul>
        <p class="list-dialog__warning">删除后项目移入回收站，可由管理员在回收站恢复。</p>
        <div class="list-dialog__actions">
          <button class="list-button" type="button" :disabled="working" @click="confirming = false">取消</button>
          <button class="list-button list-button--danger" type="button" :disabled="working" @click="confirmDelete">
            {{ working ? '删除中…' : '确认删除' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 项目列表（移植自 CITAR src/screens/part1/ProjectListScreen.tsx）。
 * 数据接本平台：列表 GET /api/projects，删除 POST /api/projects/batch-delete（软删除进回收站），
 * 新建 / 修改进建项向导。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { listProjects } from '@/services/commonApi'
import { api } from '@/services/apiProxy'
import { getStatusLabel } from '@/constants/statusEnum'

defineOptions({ name: 'CitarProjectList' })

/** 浏览 / 删除（多选）/ 修改（单选）；用一个 mode 而不是两个布尔值，两者不会同时为真 */
type Mode = 'browse' | 'delete' | 'edit'

const router = useRouter()
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === 'admin')

const projects = ref<any[]>([])
const loading = ref(false)
const loadError = ref('')
const mode = ref<Mode>('browse')
const selected = ref<Set<string>>(new Set())
const confirming = ref(false)
const working = ref(false)

const picking = computed(() => mode.value !== 'browse')
const selectedProjects = computed(() => projects.value.filter(p => selected.value.has(p.id)))

async function loadProjects() {
  loading.value = true
  loadError.value = ''
  try {
    projects.value = await listProjects()
  } catch {
    loadError.value = '项目列表载入失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

onMounted(loadProjects)

function exitMode() {
  mode.value = 'browse'
  selected.value = new Set()
  confirming.value = false
}

function toggle(id: string) {
  // 修改模式单选：换选而非累加
  if (mode.value === 'edit') {
    selected.value = selected.value.has(id) ? new Set() : new Set([id])
    return
  }
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

function cardClass(id: string) {
  if (!picking.value || !selected.value.has(id)) return ''
  return mode.value === 'delete' ? 'list-card--selected' : 'list-card--picked'
}

function confirmEdit() {
  const [id] = [...selected.value]
  if (id) router.push({ path: '/projects/new', query: { projectId: id } })
}

async function confirmDelete() {
  working.value = true
  try {
    await api.post('/api/projects/batch-delete', { project_ids: [...selected.value] }, { _silent: true } as any)
    exitMode()
  } catch (e: any) {
    loadError.value = e?.response?.data?.message || e?.response?.data?.detail || '删除未能完成，请稍后重试'
    confirming.value = false
  } finally {
    working.value = false
  }
  // 无论成败都重新取：部分成功时列表才能反映真实状态
  await loadProjects()
}

/** 点项目先进项目空页，再由侧栏进入各环节（CITAR 流程） */
function openProject(p: any) {
  router.push({ path: `/projects/${p.id}/home`, query: p.audit_year ? { year: String(p.audit_year) } : {} })
}

/** 小微企业 / 税收优惠标签：字段有值即打标（CITAR projectTags 同判据；「无优惠」不算） */
function projectTags(p: any): { label: string; tone: 'small' | 'benefit' }[] {
  const tags: { label: string; tone: 'small' | 'benefit' }[] = []
  if (p.small_micro_enterprise_type) tags.push({ label: '小微企业', tone: 'small' })
  if (p.tax_incentive_type && p.tax_incentive_type !== 'none') tags.push({ label: '税收优惠', tone: 'benefit' })
  return tags
}

/** CITAR 这里显示「当前节点」；本平台没有节点概念，显示项目状态 */
const STATUS_LABELS: Record<string, string> = {
  created: '已创建', planning: '计划中', execution: '执行中', completion: '已完成', archived: '已归档',
}
function statusLabel(s: string | null | undefined) {
  return (s && STATUS_LABELS[s]) || s || '—'
}

/** 本地日期 + 时分（秒对使用者没有意义） */
function formatUpdatedAt(iso: string | null | undefined) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (v: number) => String(v).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function logout() {
  await authStore.logout()
  router.push('/login')
}
</script>

<style scoped src="./styles/project-list.css"></style>
