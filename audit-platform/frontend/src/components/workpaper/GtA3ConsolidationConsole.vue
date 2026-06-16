<!--
  GtA3ConsolidationConsole.vue — A3 合并流程程序表 · 合并专用卡片中控台

  仅在合并项目(consolidated)中生成。
  5 条程序关联合并模块已有页面（范围/抵销/内部往来/试算/附注），
  chip 点击跳转到对应模块 Tab，不创建独立子底稿。
-->

<template>
  <div class="gt-a3-console">
    <!-- 顶部总览 -->
    <div class="gt-a3-console__overview">
      <div class="gt-a3-console__stats">
        <span class="stats-title">🔗 合并流程程序</span>
        <el-tag type="success" size="small" effect="plain">{{ completedCount }} 已完成</el-tag>
        <el-tag type="info" size="small" effect="plain">{{ trimmedCount }} 已裁剪</el-tag>
        <el-tag type="warning" size="small" effect="plain">{{ inProgressCount }} 执行中</el-tag>
        <el-tag size="small" effect="plain">{{ pendingCount }} 待执行</el-tag>
      </div>
      <div class="gt-a3-console__actions">
        <el-button size="small" @click="exportTable">📥 导出</el-button>
      </div>
    </div>

    <!-- 程序卡片列表 -->
    <div class="gt-a3-console__cards">
      <div
        v-for="row in programs"
        :key="row.id"
        class="program-card"
        :class="`program-card--${row.status || 'pending'}`"
      >
        <div class="program-card__left">
          <span class="program-card__no">{{ row.program_no }}</span>
          <span class="program-card__status-dot" :style="{ background: statusColor(row.status) }" />
        </div>
        <div class="program-card__main">
          <div class="program-card__desc">{{ row.program_desc }}</div>
          <div v-if="row.summary" class="program-card__summary">
            <el-icon size="12"><InfoFilled /></el-icon>
            <span>{{ row.summary }}</span>
          </div>
          <!-- 关联跳转 -->
          <div v-if="row.linked_workpapers" class="program-card__refs">
            <template v-for="(ref, ri) in parseRefs(row.linked_workpapers)" :key="ri">
              <el-tag
                v-if="ref.startsWith('route:')"
                size="small"
                class="program-card__route-chip"
                @click="navigateToRoute(ref)"
              >📂 {{ routeLabel(ref) }}</el-tag>
              <GtIndexChip v-else :value="ref" :validate="true" @click="handleChipClick" />
            </template>
          </div>
          <!-- 执行说明 -->
          <div class="program-card__exec">
            <el-input
              v-if="!readonly"
              v-model="row.execution_summary"
              size="small"
              placeholder="执行情况说明..."
              @blur="saveExecution(row)"
              class="program-card__exec-input"
            />
            <span v-else class="program-card__exec-text">{{ row.execution_summary || '' }}</span>
          </div>
        </div>
        <!-- 右侧状态 -->
        <div class="program-card__right">
          <el-dropdown v-if="!readonly" trigger="click" @command="(cmd: string) => changeStatus(row, cmd)">
            <el-tag :type="statusTagType(row.status)" size="small" class="program-card__status-tag">
              {{ statusLabel(row.status) }}
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </el-tag>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="in_progress">执行中</el-dropdown-item>
                <el-dropdown-item command="completed">已完成</el-dropdown-item>
                <el-dropdown-item command="not_applicable" divided>裁剪</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-tag v-else :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </div>
      </div>
    </div>

    <!-- 裁剪弹窗 -->
    <el-dialog v-model="trimVisible" title="裁剪理由" width="450px" :close-on-click-modal="false">
      <p style="margin-bottom:12px;color:#666">{{ trimTarget?.program_desc }}</p>
      <el-input v-model="trimReason" type="textarea" :rows="3" placeholder="请输入裁剪理由（必填）" maxlength="500" show-word-limit />
      <template #footer>
        <el-button @click="trimVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!trimReason.trim()" @click="confirmTrim">确认裁剪</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, InfoFilled } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { api } from '@/services/apiProxy'
import type { ResolvedIndexRef } from '@/utils/parseIndexRef'

interface ProgramRow {
  id: string
  program_no: number
  program_desc: string
  program_category: string
  linked_workpapers?: string
  execution_summary?: string
  status: string
  trim_reason?: string
  summary?: string
}

interface AProgramHtmlData {
  programs: ProgramRow[]
  trim_decisions: Array<{ programId: string; reason: string }>
  signatures?: Array<{ role: string; name: string; date: string }>
}

const props = withDefaults(defineProps<{
  wpId: string
  sheetName: string
  schema: any
  htmlData: AProgramHtmlData
  readonly?: boolean
  projectId?: string
  year?: number
  wpCode?: string
}>(), { readonly: false, wpCode: 'A3' })

const emit = defineEmits<{
  'save': [data: AProgramHtmlData]
  'jump-to-workpaper': [wpCode: string]
}>()

const route = useRoute()
const router = useRouter()
const programs = ref<ProgramRow[]>([])
const projectId = computed(() => props.projectId || (route.params.projectId as string) || '')

// Trim dialog
const trimVisible = ref(false)
const trimTarget = ref<ProgramRow | null>(null)
const trimReason = ref('')

function initData() {
  programs.value = props.htmlData?.programs
    ? JSON.parse(JSON.stringify(props.htmlData.programs))
    : []
}
initData()
watch(() => props.htmlData, initData, { deep: true })

// Computed
const completedCount = computed(() => programs.value.filter(p => p.status === 'completed').length)
const trimmedCount = computed(() => programs.value.filter(p => p.status === 'not_applicable').length)
const inProgressCount = computed(() => programs.value.filter(p => p.status === 'in_progress').length)
const pendingCount = computed(() => programs.value.filter(p => !p.status || p.status === 'pending').length)

// Helpers
function statusColor(status: string): string {
  switch (status) {
    case 'completed': return '#67C23A'
    case 'in_progress': return '#E6A23C'
    case 'not_applicable': return '#909399'
    default: return '#dcdfe6'
  }
}
function statusTagType(status: string): 'success' | 'warning' | 'info' | 'primary' {
  switch (status) {
    case 'completed': return 'success'
    case 'in_progress': return 'warning'
    case 'not_applicable': return 'info'
    default: return 'primary'
  }
}
function statusLabel(status: string): string {
  switch (status) {
    case 'completed': return '已完成'
    case 'in_progress': return '执行中'
    case 'not_applicable': return '已裁剪'
    default: return '待执行'
  }
}
function parseRefs(value: string): string[] {
  if (!value) return []
  return value.split(/[,;\n]/).map(s => s.trim()).filter(Boolean)
}
function handleChipClick(resolved: ResolvedIndexRef) {
  if (resolved.ns === 'wp' && resolved.target) {
    emit('jump-to-workpaper', resolved.target)
  }
}

// route: 前缀跳转到合并模块页面
const ROUTE_LABELS: Record<string, string> = {
  scope: '合并范围',
  eliminations: '抵销分录',
  'internal-trade': '内部往来',
  trial: '合并试算',
  notes: '合并附注',
}
function routeLabel(ref: string): string {
  const path = ref.replace('route:', '')
  const tabMatch = path.match(/[?&]tab=([^&]+)/)
  const tab = tabMatch?.[1] || ''
  return ROUTE_LABELS[tab] || tab || '合并模块'
}
function navigateToRoute(ref: string) {
  const path = ref.replace('route:', '')
  // 拼接项目级路由
  const pid = projectId.value
  if (pid) {
    router.push(`/projects/${pid}${path}`)
  }
}

// Status change
function changeStatus(row: ProgramRow, newStatus: string) {
  if (newStatus === 'not_applicable') {
    trimTarget.value = row
    trimReason.value = ''
    trimVisible.value = true
    return
  }
  const idx = programs.value.findIndex(p => p.id === row.id)
  if (idx >= 0) {
    programs.value[idx].status = newStatus
    persistField(row.program_no, 'status', newStatus)
    debounceSave()
  }
}
function confirmTrim() {
  if (!trimTarget.value || !trimReason.value.trim()) return
  const row = trimTarget.value
  const idx = programs.value.findIndex(p => p.id === row.id)
  if (idx >= 0) {
    programs.value[idx].status = 'not_applicable'
    programs.value[idx].trim_reason = trimReason.value.trim()
  }
  trimVisible.value = false
  debounceSave()
}

// Persist
async function saveExecution(row: ProgramRow) {
  if (props.readonly) return
  persistField(row.program_no, 'execution_summary', row.execution_summary || '')
}
async function persistField(programNo: number, field: string, value: any) {
  const year = props.year || parseInt(route.query.year as string) || new Date().getFullYear()
  try {
    await api.post('/api/workpapers/field-overrides', {
      project_id: projectId.value,
      year,
      scope: `procedure_table:${props.wpCode || 'A3'}`,
      item_key: String(programNo),
      field,
      value,
    })
  } catch { /* 静默 */ }
}

// Export
async function exportTable() {
  const { useExcelIO } = await import('@/composables/useExcelIO')
  const { exportData } = useExcelIO()
  await exportData({
    data: programs.value.map(p => ({
      '序号': p.program_no,
      '审计程序': p.program_desc,
      '自动摘要': p.summary || '',
      '关联模块': p.linked_workpapers || '',
      '执行说明': p.execution_summary || '',
      '状态': statusLabel(p.status),
    })),
    columns: [
      { key: '序号', header: '序号' },
      { key: '审计程序', header: '审计程序' },
      { key: '自动摘要', header: '合并状态' },
      { key: '关联模块', header: '关联模块' },
      { key: '执行说明', header: '执行情况说明' },
      { key: '状态', header: '状态' },
    ],
    sheetName: 'A3 合并流程程序表',
    fileName: 'A3 合并流程程序表.xlsx',
  })
}

let saveTimer: ReturnType<typeof setTimeout> | null = null
function debounceSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    emit('save', {
      programs: programs.value,
      trim_decisions: programs.value
        .filter(p => p.status === 'not_applicable' && p.trim_reason)
        .map(p => ({ programId: p.id, reason: p.trim_reason! })),
      signatures: props.htmlData?.signatures,
    })
  }, 1500)
}
</script>

<style scoped>
.gt-a3-console {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1000px;
  margin: 0 auto;
}
.gt-a3-console__overview {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: linear-gradient(135deg, #f7f9fc 0%, #edf2f7 100%);
  border: 1px solid #c6d4e1;
  border-radius: 10px;
  flex-wrap: wrap;
  gap: 10px;
}
.gt-a3-console__stats { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.stats-title { font-size: 15px; font-weight: 600; color: #2c5282; margin-right: 8px; }
.gt-a3-console__actions { display: flex; gap: 6px; }
.gt-a3-console__cards { display: flex; flex-direction: column; gap: 8px; }

.program-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid #e8e8ec;
  background: #fff;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.program-card:hover {
  border-color: #a0c4e8;
  box-shadow: 0 2px 8px rgba(44, 82, 130, 0.08);
}
.program-card--completed { border-left: 3px solid #67C23A; }
.program-card--in_progress { border-left: 3px solid #E6A23C; }
.program-card--not_applicable { border-left: 3px solid #c0c4cc; opacity: 0.7; }
.program-card--pending { border-left: 3px solid #dcdfe6; }

.program-card__left { display: flex; flex-direction: column; align-items: center; gap: 4px; padding-top: 2px; }
.program-card__no { font-size: 14px; font-weight: 700; color: #2c5282; min-width: 22px; text-align: center; }
.program-card__status-dot { width: 8px; height: 8px; border-radius: 50%; }

.program-card__main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.program-card__desc { font-size: 13px; color: #303133; line-height: 1.5; }
.program-card__summary {
  display: flex; align-items: center; gap: 4px;
  font-size: 12px; color: #2c5282;
  background: #edf2f7; padding: 3px 8px; border-radius: 4px; width: fit-content;
}
.program-card__refs { display: flex; flex-wrap: wrap; gap: 4px; }
.program-card__route-chip {
  cursor: pointer;
  background: #ebf5ff !important;
  border-color: #a0c4e8 !important;
  color: #2c5282 !important;
  transition: all 0.15s;
}
.program-card__route-chip:hover {
  background: #bee3f8 !important;
  border-color: #63b3ed !important;
}
.program-card__exec { margin-top: 2px; }
.program-card__exec-input { max-width: 400px; }
.program-card__exec-text { font-size: 12px; color: #909399; }
.program-card__right { flex-shrink: 0; padding-top: 2px; }
.program-card__status-tag { cursor: pointer; }
</style>
