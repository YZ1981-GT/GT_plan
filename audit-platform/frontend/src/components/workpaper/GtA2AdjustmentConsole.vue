<!--
  GtA2AdjustmentConsole.vue — A2 调整分录程序表 · 卡片式中控台

  参照 GtA1Dashboard 卡片形态，但去掉 4 阶段里程碑/环形进度：
  A2 只有 5 条调整分录程序（AJE/RJE/合并/未更正/试算平衡），属完成阶段。
  突出 auto_data_source 自动汇总摘要（笔数/金额）。

  修复 A1 的 scope 硬编码 bug：persistField scope 按 wpCode 动态。
-->

<template>
  <div class="gt-a2-console">
    <!-- 顶部总览 -->
    <div class="gt-a2-console__overview">
      <div class="gt-a2-console__stats">
        <span class="stats-title">{{ title }}</span>
        <el-tag type="success" size="small" effect="plain">{{ completedCount }} 已完成</el-tag>
        <el-tag type="info" size="small" effect="plain">{{ trimmedCount }} 已裁剪</el-tag>
        <el-tag type="warning" size="small" effect="plain">{{ inProgressCount }} 执行中</el-tag>
        <el-tag size="small" effect="plain">{{ pendingCount }} 待执行</el-tag>
      </div>
      <div class="gt-a2-console__actions">
        <el-button v-if="!readonly" type="primary" size="small" @click="openAddDialog">+ 新增</el-button>
        <el-button size="small" @click="exportTable">📥 导出</el-button>
      </div>
    </div>

    <!-- 程序卡片列表 -->
    <div class="gt-a2-console__cards">
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
          <div v-if="row.linked_workpapers" class="program-card__refs">
            <GtIndexChip
              v-for="(ref, ri) in parseRefs(row.linked_workpapers)"
              :key="ri"
              :value="ref"
              :validate="true"
              @click="handleChipClick"
            />
          </div>
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

    <!-- 裁剪理由弹窗 -->
    <el-dialog v-model="trimVisible" title="裁剪理由" width="450px" :close-on-click-modal="false">
      <p style="margin-bottom:12px;color:#666">{{ trimTarget?.program_desc }}</p>
      <el-input v-model="trimReason" type="textarea" :rows="3" placeholder="请输入裁剪理由（必填）" maxlength="500" show-word-limit />
      <template #footer>
        <el-button @click="trimVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!trimReason.trim()" @click="confirmTrim">确认裁剪</el-button>
      </template>
    </el-dialog>

    <!-- 新增程序弹窗 -->
    <el-dialog v-model="addVisible" title="新增审计程序" width="500px" :close-on-click-modal="false">
      <el-form label-width="80px">
        <el-form-item label="描述" required>
          <el-input v-model="addDesc" type="textarea" :rows="3" placeholder="审计程序描述" maxlength="1000" show-word-limit />
        </el-form-item>
        <el-form-item label="索引号">
          <el-input v-model="addRef" placeholder="关联底稿索引，如 A2-2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!addDesc.trim()" @click="confirmAdd">新增</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
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
}>(), { readonly: false, wpCode: 'A2' })

const emit = defineEmits<{
  'save': [data: AProgramHtmlData]
  'jump-to-workpaper': [wpCode: string]
}>()

const route = useRoute()
const programs = ref<ProgramRow[]>([])
const projectId = computed(() => props.projectId || (route.params.projectId as string) || '')

const title = computed(() => {
  const code = props.wpCode || 'A2'
  return code === 'A2' ? '调整分录程序' : `${code} 审计程序`
})

// Trim dialog
const trimVisible = ref(false)
const trimTarget = ref<ProgramRow | null>(null)
const trimReason = ref('')

// Add dialog
const addVisible = ref(false)
const addDesc = ref('')
const addRef = ref('')

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
  return value.split(/[/,;\n]/).map(s => s.trim()).filter(Boolean)
}
function handleChipClick(resolved: ResolvedIndexRef) {
  if (resolved.ns === 'wp' && resolved.target) {
    emit('jump-to-workpaper', resolved.target)
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

// Add
function openAddDialog() { addDesc.value = ''; addRef.value = ''; addVisible.value = true }
function confirmAdd() {
  if (!addDesc.value.trim()) return
  const maxNo = programs.value.reduce((m, p) => Math.max(m, p.program_no || 0), 0)
  const newId = `custom-${Date.now()}`
  const newProgram: ProgramRow = {
    id: newId,
    program_no: maxNo + 1,
    program_desc: addDesc.value.trim(),
    program_category: '',
    linked_workpapers: addRef.value.trim(),
    status: 'pending',
  }
  programs.value.push(newProgram)
  addVisible.value = false
  debounceSave()
  // P0: 持久化到后端
  persistCustomItem(newProgram)
}

async function persistCustomItem(item: ProgramRow) {
  const year = props.year || parseInt(route.query.year as string) || new Date().getFullYear()
  try {
    await api.post(`/api/projects/${projectId.value}/procedure-tables/custom-items`, {
      table_code: props.wpCode || 'A2',
      year,
      description: item.program_desc,
      phase: 'completion',
      ref_index: item.linked_workpapers || '',
    })
  } catch {
    // 已有 persistField 的错误提示，这里不重复
  }
}

// Persist — scope 动态按 wpCode（修复 A1 硬编码 bug）
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
      scope: `procedure_table:${props.wpCode || 'A2'}`,
      item_key: String(programNo),
      field,
      value,
    })
  } catch (e: any) {
    const { ElMessage } = await import('element-plus')
    ElMessage.error(`保存失败：${e?.message || '网络异常'}`)
  }
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
      '索引号': p.linked_workpapers || '',
      '执行说明': p.execution_summary || '',
      '状态': statusLabel(p.status),
    })),
    columns: [
      { key: '序号', header: '序号' },
      { key: '审计程序', header: '审计程序' },
      { key: '自动摘要', header: '自动状态' },
      { key: '索引号', header: '索引号' },
      { key: '执行说明', header: '执行情况说明' },
      { key: '状态', header: '状态' },
    ],
    sheetName: `${props.wpCode || 'A2'} 程序表`,
    fileName: `${props.wpCode || 'A2'} 调整分录程序表.xlsx`,
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
.gt-a2-console {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1000px;
  margin: 0 auto;
}

.gt-a2-console__overview {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: linear-gradient(135deg, #f9f7fc 0%, #f0ebf7 100%);
  border: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
  border-radius: 10px;
  flex-wrap: wrap;
  gap: 10px;
}

.gt-a2-console__stats {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.stats-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--gt-purple, #4b2d77);
  margin-right: 8px;
}

.gt-a2-console__actions { display: flex; gap: 6px; }

.gt-a2-console__cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 卡片样式（与 A1 一致） */
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
  border-color: var(--gt-color-border-purple-light, #d8b8ee);
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.06);
}
.program-card--completed { border-left: 3px solid #67C23A; }
.program-card--in_progress { border-left: 3px solid #E6A23C; }
.program-card--not_applicable { border-left: 3px solid #c0c4cc; opacity: 0.7; }
.program-card--pending { border-left: 3px solid #dcdfe6; }

.program-card__left {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding-top: 2px;
}
.program-card__no {
  font-size: 14px;
  font-weight: 700;
  color: var(--gt-purple, #4b2d77);
  min-width: 22px;
  text-align: center;
}
.program-card__status-dot { width: 8px; height: 8px; border-radius: 50%; }

.program-card__main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.program-card__desc { font-size: var(--wp-font-size, 13px); color: #303133; line-height: 1.5; }

.program-card__summary {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--gt-purple, #4b2d77);
  background: var(--gt-color-primary-bg, #f4f0fa);
  padding: 3px 8px;
  border-radius: 4px;
  width: fit-content;
}

.program-card__refs { display: flex; flex-wrap: wrap; gap: 4px; }

.program-card__exec { margin-top: 2px; }
.program-card__exec-input { max-width: 400px; }
.program-card__exec-text { font-size: 12px; color: #909399; }

.program-card__right { flex-shrink: 0; padding-top: 2px; }
.program-card__status-tag { cursor: pointer; }
</style>
