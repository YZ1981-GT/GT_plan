<!--
  GtA1Dashboard.vue — A1 财务报告程序表 · 项目总控仪表盘

  专用于 A1 底稿的仪表盘式渲染，替代通用 GtAProgramConsole 表格形态。
  A1 是审计项目全生命周期 checklist，以"项目仪表盘"形态呈现。

  功能：
  - 顶部：项目整体进度环形图 + 阶段里程碑时间线
  - 主体：4 阶段卡片式布局（计划/执行/完成/签发）
  - 每条程序：描述 + auto_data_source 实时摘要 + 索引 chip + 状态切换 + 执行说明
  - 操作：状态切换 / 裁剪(含理由) / 新增 / 导出
-->

<template>
  <div class="gt-a1-dashboard">
    <!-- ═══ 顶部总览 ═══ -->
    <div class="gt-a1-dashboard__overview">
      <!-- 环形进度 -->
      <div class="gt-a1-dashboard__ring-area">
        <el-progress
          type="circle"
          :percentage="progressPercentage"
          :width="96"
          :stroke-width="10"
          :color="progressColor"
        >
          <template #default>
            <div class="ring-inner">
              <span class="ring-num">{{ doneCount }}</span>
              <span class="ring-of">/{{ programs.length }}</span>
            </div>
          </template>
        </el-progress>
        <div class="ring-legend">
          <span class="legend-item legend--done">✓ {{ completedCount }}</span>
          <span class="legend-item legend--trim">— {{ trimmedCount }}</span>
          <span class="legend-item legend--wip">◐ {{ inProgressCount }}</span>
          <span class="legend-item legend--todo">◻ {{ pendingCount }}</span>
        </div>
      </div>

      <!-- 阶段里程碑 -->
      <div class="gt-a1-dashboard__milestones">
        <div
          v-for="(stage, idx) in phaseGroups"
          :key="stage.phase"
          class="milestone"
          :class="{ 'milestone--done': stage.progress === 100 }"
        >
          <div class="milestone__dot" :style="{ background: stageColors[idx] }">
            {{ stageIcons[idx] }}
          </div>
          <div class="milestone__body">
            <span class="milestone__label">{{ stage.label }}</span>
            <el-progress
              :percentage="stage.progress"
              :stroke-width="5"
              :show-text="false"
              :color="stage.progress === 100 ? '#67C23A' : stageColors[idx]"
              style="width: 80px"
            />
          </div>
          <span v-if="idx < phaseGroups.length - 1" class="milestone__connector" />
        </div>
      </div>

      <!-- 工具栏 -->
      <div class="gt-a1-dashboard__actions">
        <el-button v-if="!readonly" type="primary" size="small" @click="openAddDialog">+ 新增</el-button>
        <el-button size="small" @click="exportTable">📥 导出</el-button>
        <el-button text size="small" @click="flowGraphVisible = !flowGraphVisible">
          🗺️ {{ flowGraphVisible ? '收起' : '逻辑图' }}
        </el-button>
      </div>
    </div>

    <!-- ═══ 审计逻辑流程图（折叠） ═══ -->
    <GtAuditFlowGraph
      v-if="wpId && projectId"
      :wp-id="wpId"
      :project-id="projectId"
      :expanded="flowGraphVisible"
      :programs="programs"
      @scroll-to-program="scrollToCard"
    />

    <!-- ═══ 阶段卡片主体 ═══ -->
    <div class="gt-a1-dashboard__phases">
      <div
        v-for="(stage, sIdx) in phaseGroups"
        :key="stage.phase"
        class="phase-section"
      >
        <!-- 阶段标题 -->
        <div
          class="phase-section__header"
          :style="{ borderLeftColor: stageColors[sIdx] }"
          @click="togglePhase(stage.phase)"
        >
          <span class="phase-section__icon">{{ stageIcons[sIdx] }}</span>
          <span class="phase-section__title">{{ stage.label }}</span>
          <el-tag
            :type="stage.progress === 100 ? 'success' : 'info'"
            size="small"
            effect="plain"
          >
            {{ stage.doneCount }}/{{ stage.items.length }}
          </el-tag>
          <span class="phase-section__toggle">
            {{ expandedPhases[stage.phase] ? '−' : '+' }}
          </span>
        </div>

        <!-- 程序卡片列表（可折叠） -->
        <div v-show="expandedPhases[stage.phase]" class="phase-section__cards">
          <div
            v-for="row in stage.items"
            :key="row.id"
            :ref="(el) => { if (el) cardRefs[row.program_no] = el as HTMLElement }"
            class="program-card"
            :class="`program-card--${row.status || 'pending'}`"
          >
            <!-- 左侧：序号 + 状态指示 -->
            <div class="program-card__left">
              <span class="program-card__no">{{ row.program_no }}</span>
              <span class="program-card__status-dot" :style="{ background: statusColor(row.status) }" />
            </div>

            <!-- 中间：主内容 -->
            <div class="program-card__main">
              <div class="program-card__top">
                <span class="program-card__desc">{{ row.program_desc }}</span>
              </div>
              <!-- 自动汇总摘要（来自 auto_data_source） -->
              <div v-if="row.summary" class="program-card__summary">
                <el-icon size="12"><InfoFilled /></el-icon>
                <span>{{ row.summary }}</span>
              </div>
              <!-- 索引 chip -->
              <div v-if="row.linked_workpapers" class="program-card__refs">
                <GtIndexChip
                  v-for="(ref, ri) in parseRefs(row.linked_workpapers)"
                  :key="ri"
                  :value="ref"
                  :validate="true"
                  @click="handleChipClick"
                />
              </div>
              <!-- 执行说明（可编辑） -->
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

            <!-- 右侧：状态操作 -->
            <div class="program-card__right">
              <el-dropdown
                v-if="!readonly"
                trigger="click"
                @command="(cmd: string) => changeStatus(row, cmd)"
              >
                <el-tag
                  :type="statusTagType(row.status)"
                  size="small"
                  class="program-card__status-tag"
                >
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
              <el-tag v-else :type="statusTagType(row.status)" size="small">
                {{ statusLabel(row.status) }}
              </el-tag>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 裁剪理由弹窗 ═══ -->
    <el-dialog v-model="trimVisible" title="裁剪理由" width="450px" :close-on-click-modal="false">
      <p style="margin-bottom:12px;color:#666">{{ trimTarget?.program_desc }}</p>
      <el-input
        v-model="trimReason"
        type="textarea"
        :rows="3"
        placeholder="请输入裁剪理由（必填）"
        maxlength="500"
        show-word-limit
      />
      <template #footer>
        <el-button @click="trimVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!trimReason.trim()" @click="confirmTrim">确认裁剪</el-button>
      </template>
    </el-dialog>

    <!-- ═══ 新增程序弹窗 ═══ -->
    <el-dialog v-model="addVisible" title="新增审计程序" width="500px" :close-on-click-modal="false">
      <el-form label-width="80px">
        <el-form-item label="描述" required>
          <el-input v-model="addDesc" type="textarea" :rows="3" placeholder="审计程序描述" maxlength="1000" show-word-limit />
        </el-form-item>
        <el-form-item label="阶段">
          <el-select v-model="addPhase" style="width:100%">
            <el-option label="计划阶段" value="planning" />
            <el-option label="执行阶段" value="execution" />
            <el-option label="完成总结" value="completion" />
            <el-option label="复核签发" value="signoff" />
          </el-select>
        </el-form-item>
        <el-form-item label="索引号">
          <el-input v-model="addRef" placeholder="关联底稿索引，如 B10~B60" />
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
import { ref, computed, watch, reactive } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowDown, InfoFilled } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import GtAuditFlowGraph from '@/components/workpaper/GtAuditFlowGraph.vue'
import { api } from '@/services/apiProxy'
import type { ResolvedIndexRef } from '@/utils/parseIndexRef'

// ─── Types ───
interface ProgramRow {
  id: string
  program_no: number
  program_desc: string
  program_category: string
  assertions?: Record<string, boolean>
  linked_workpapers?: string
  execution_summary?: string
  status: string
  trim_reason?: string
  phase?: string
  summary?: string
  attachment_count?: number
}

interface AProgramHtmlData {
  programs: ProgramRow[]
  trim_decisions: Array<{ programId: string; reason: string }>
  signatures?: Array<{ role: string; name: string; date: string }>
}

// ─── Props / Emits ───
const props = withDefaults(defineProps<{
  wpId: string
  sheetName: string
  schema: any
  htmlData: AProgramHtmlData
  readonly?: boolean
  projectId?: string
  year?: number
  wpCode?: string
}>(), { readonly: false, wpCode: 'A1' })

const emit = defineEmits<{
  'save': [data: AProgramHtmlData]
  'jump-to-workpaper': [wpCode: string]
  'open-attachment': [payload: { wpId: string; sheetName: string; rowRef: string }]
  'program-trim': [payload: { programId: string; reason: string }]
  'program-status-change': [payload: { programId: string; status: string }]
  'program-add': [payload: { programId: string; description: string }]
}>()

// ─── Constants ───
const stageIcons = ['📋', '🔍', '✅', '🔒']
const stageColors = ['#4b2d77', '#0094B3', '#28A745', '#FFC23D']
const PHASE_ORDER = ['planning', 'execution', 'completion', 'signoff'] as const
const PHASE_LABELS: Record<string, string> = {
  planning: '计划与风险评估',
  execution: '执行审计程序',
  completion: '完成阶段',
  signoff: '复核与归档',
}

// ─── State ───
const route = useRoute()
const programs = ref<ProgramRow[]>([])
const flowGraphVisible = ref(false)
const cardRefs = reactive<Record<number, HTMLElement>>({})

const projectId = computed(() => props.projectId || (route.params.projectId as string) || '')

// Trim dialog
const trimVisible = ref(false)
const trimTarget = ref<ProgramRow | null>(null)
const trimReason = ref('')

// Phase collapse state (default: expand phases that have items)
const expandedPhases = reactive<Record<string, boolean>>({
  planning: true,
  execution: true,
  completion: true,
  signoff: true,
})

function togglePhase(phase: string) {
  expandedPhases[phase] = !expandedPhases[phase]
}

// Add dialog
const addVisible = ref(false)
const addDesc = ref('')
const addPhase = ref('completion')
const addRef = ref('')

// ─── Init ───
function initData() {
  programs.value = props.htmlData?.programs
    ? JSON.parse(JSON.stringify(props.htmlData.programs))
    : []
}
initData()
watch(() => props.htmlData, initData, { deep: true })

// ─── Computed ───
const completedCount = computed(() => programs.value.filter(p => p.status === 'completed').length)
const trimmedCount = computed(() => programs.value.filter(p => p.status === 'not_applicable').length)
const inProgressCount = computed(() => programs.value.filter(p => p.status === 'in_progress').length)
const pendingCount = computed(() => programs.value.filter(p => !p.status || p.status === 'pending').length)
const doneCount = computed(() => completedCount.value + trimmedCount.value)
const progressPercentage = computed(() => {
  const total = programs.value.length
  return total ? Math.round((doneCount.value / total) * 100) : 0
})
const progressColor = computed(() => {
  const pct = progressPercentage.value
  if (pct === 100) return '#67C23A'
  if (pct >= 60) return '#4b2d77'
  return '#E6A23C'
})

/** 按 phase 分组 */
const phaseGroups = computed(() => {
  const grouped = new Map<string, ProgramRow[]>()
  for (const phase of PHASE_ORDER) grouped.set(phase, [])
  for (const p of programs.value) {
    const phase = p.phase || 'completion'
    const list = grouped.get(phase)
    if (list) list.push(p)
    else grouped.set(phase, [p])
  }
  return PHASE_ORDER
    .filter(phase => (grouped.get(phase)?.length ?? 0) > 0)
    .map(phase => {
      const items = grouped.get(phase)!
      const doneInPhase = items.filter(i => i.status === 'completed' || i.status === 'not_applicable').length
      return {
        phase,
        label: PHASE_LABELS[phase] || phase,
        items,
        doneCount: doneInPhase,
        progress: items.length > 0 ? Math.round((doneInPhase / items.length) * 100) : 0,
      }
    })
})

// ─── Methods ───
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

function scrollToCard(programNo: number) {
  const el = cardRefs[programNo]
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

// ─── Status change ───
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
    emit('program-status-change', { programId: row.id, status: newStatus })
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
  emit('program-trim', { programId: row.id, reason: trimReason.value.trim() })
  trimVisible.value = false
  debounceSave()
}

// ─── Add ───
function openAddDialog() {
  addDesc.value = ''
  addPhase.value = 'completion'
  addRef.value = ''
  addVisible.value = true
}

function confirmAdd() {
  if (!addDesc.value.trim()) return
  const maxNo = programs.value.reduce((m, p) => Math.max(m, p.program_no || 0), 0)
  const newId = `custom-${Date.now()}`
  programs.value.push({
    id: newId,
    program_no: maxNo + 1,
    program_desc: addDesc.value.trim(),
    program_category: '',
    linked_workpapers: addRef.value.trim(),
    status: 'pending',
    phase: addPhase.value,
  })
  emit('program-add', { programId: newId, description: addDesc.value.trim() })
  addVisible.value = false
  debounceSave()
}

// ─── Persistence ───
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
      scope: `procedure_table:${props.wpCode || 'A1'}`,
      item_key: String(programNo),
      field,
      value,
    })
  } catch { /* 静默 */ }
}

async function exportTable() {
  const { useExcelIO } = await import('@/composables/useExcelIO')
  const { exportData } = useExcelIO()
  await exportData({
    data: programs.value.map(p => ({
      '序号': p.program_no,
      '审计程序': p.program_desc,
      '阶段': PHASE_LABELS[p.phase || 'completion'] || '',
      '自动摘要': p.summary || '',
      '索引号': p.linked_workpapers || '',
      '执行说明': p.execution_summary || '',
      '状态': statusLabel(p.status),
    })),
    columns: [
      { key: '序号', header: '序号' },
      { key: '审计程序', header: '审计程序' },
      { key: '阶段', header: '阶段' },
      { key: '自动摘要', header: '自动状态' },
      { key: '索引号', header: '索引号' },
      { key: '执行说明', header: '执行情况说明' },
      { key: '状态', header: '状态' },
    ],
    sheetName: `${props.wpCode || 'A1'} 总控程序表`,
    fileName: `${props.wpCode || 'A1'} 财务报告程序表.xlsx`,
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
.gt-a1-dashboard {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

/* ═══ 顶部总览 ═══ */
.gt-a1-dashboard__overview {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 16px 20px;
  background: linear-gradient(135deg, #f9f7fc 0%, #f0ebf7 100%);
  border: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
  border-radius: 12px;
  flex-wrap: wrap;
}

.gt-a1-dashboard__ring-area {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.ring-inner {
  display: flex;
  align-items: baseline;
  gap: 2px;
}
.ring-num { font-size: 24px; font-weight: 700; color: var(--gt-purple, #4b2d77); }
.ring-of { font-size: 14px; color: #909399; }

.ring-legend {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 12px;
}
.legend-item { white-space: nowrap; }
.legend--done { color: #67C23A; }
.legend--trim { color: #909399; }
.legend--wip { color: #E6A23C; }
.legend--todo { color: #c0c4cc; }

/* 里程碑 */
.gt-a1-dashboard__milestones {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.milestone {
  display: flex;
  align-items: center;
  gap: 6px;
  position: relative;
}
.milestone--done .milestone__dot { box-shadow: 0 0 0 3px rgba(103, 194, 58, 0.2); }

.milestone__dot {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
  color: #fff;
  text-shadow: 0 1px 2px rgba(0,0,0,0.2);
}

.milestone__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.milestone__label { font-size: 11px; color: #606266; white-space: nowrap; }

.milestone__connector {
  display: block;
  width: 20px;
  height: 2px;
  background: #dcdfe6;
  margin: 0 2px;
  flex-shrink: 0;
}

/* 工具栏 */
.gt-a1-dashboard__actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
  margin-left: auto;
}

/* ═══ 阶段卡片区域 ═══ */
.gt-a1-dashboard__phases {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.phase-section__header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-left: 4px solid;
  background: #fafafa;
  border-radius: 0 8px 8px 0;
  margin-bottom: 10px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}
.phase-section__header:hover { background: #f0ebf7; }
.phase-section__icon { font-size: 16px; }
.phase-section__title { font-size: 14px; font-weight: 600; color: #303133; flex: 1; }
.phase-section__toggle {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  background: #e8e8ec;
  font-size: 14px;
  font-weight: 700;
  color: #606266;
  transition: background 0.15s;
}
.phase-section__header:hover .phase-section__toggle { background: #d8b8ee; color: #4b2d77; }

.phase-section__cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-left: 16px;
}

/* ═══ 程序卡片 ═══ */
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
.program-card__status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.program-card__main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.program-card__top { display: flex; align-items: flex-start; gap: 8px; }
.program-card__desc {
  font-size: 13px;
  color: #303133;
  line-height: 1.5;
}

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

.program-card__refs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.program-card__exec { margin-top: 2px; }
.program-card__exec-input { max-width: 400px; }
.program-card__exec-text { font-size: 12px; color: #909399; }

.program-card__right {
  flex-shrink: 0;
  padding-top: 2px;
}
.program-card__status-tag { cursor: pointer; }

/* ═══ 响应式 ═══ */
@media (max-width: 768px) {
  .gt-a1-dashboard__overview { flex-direction: column; align-items: flex-start; }
  .gt-a1-dashboard__milestones { flex-wrap: wrap; }
  .gt-a1-dashboard__actions { margin-left: 0; }
  .program-card { flex-wrap: wrap; }
}
</style>
