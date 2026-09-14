<template>
  <div class="timesheet">
    <!-- 顶部工具栏 -->
    <div class="ts-toolbar">
      <div class="ts-toolbar-left">
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button label="day">日视图</el-radio-button>
          <el-radio-button label="week">周视图</el-radio-button>
        </el-radio-group>

        <div class="ts-nav">
          <el-button size="small" :icon="ArrowLeft" circle @click="shift(-1)" />
          <span class="ts-nav-label">{{ navLabel }}</span>
          <el-button size="small" :icon="ArrowRight" circle @click="shift(1)" />
          <el-button v-if="!isCurrent" size="small" text type="primary" @click="gotoNow">
            {{ viewMode === 'day' ? '回到今天' : '回到本周' }}
          </el-button>
        </div>
      </div>
      <div class="ts-toolbar-right">
        <span v-if="hasUnsavedChanges" class="ts-unsaved-badge">● 未保存</span>
        <el-button size="small" type="warning" :loading="autoCollecting" @click="handleAutoCollect" title="从平台操作轨迹自动采集工时草稿">
          ⚡ 自动采集
        </el-button>
        <el-dropdown trigger="click" @command="handleToolCommand">
          <el-button size="small">更多工具 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="external">+ 平台外工作</el-dropdown-item>
              <el-dropdown-item command="editTime">📋 编辑记录</el-dropdown-item>
              <el-dropdown-item command="aiFill">🤖 LLM 预填</el-dropdown-item>
              <el-dropdown-item command="nlp">🗣️ 语音/文字</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button type="primary" size="small" :loading="saving" @click="saveAll">保存</el-button>
      </div>
    </div>

    <!-- ═══ 日视图 ═══ -->
    <div v-if="viewMode === 'day'" class="ts-day-view" v-loading="loading">
      <div class="ts-day-summary">
        <div class="ts-day-summary-icon"><el-icon :size="22"><Clock /></el-icon></div>
        <div>
          <div class="ts-day-summary-total">{{ selectedDayTotal }} <span>小时</span></div>
          <div class="ts-day-summary-sub">{{ dayFullLabel }}</div>
        </div>
        <div class="ts-day-summary-bar">
          <el-progress
            :percentage="Math.min(100, Math.round(selectedDayTotal / 8 * 100))"
            :color="selectedDayTotal > 8 ? '#f56c6c' : '#4b2d77'"
            :stroke-width="8"
            :show-text="false"
          />
          <span class="ts-day-summary-target">标准工时 8h</span>
        </div>
      </div>

      <!-- 时间轴 -->
      <WorkHourTimelineBar :date="selectedDate" ref="timelineRef" />

      <div v-if="projectRows.length === 0" class="ts-empty-card">
        <p>暂无参与项目</p>
        <el-button type="primary" size="small" @click="openAddProject">+ 添加项目填报</el-button>
      </div>

      <div v-else class="ts-project-cards">
        <div v-for="proj in projectRows" :key="proj.project_id" class="ts-project-card">
          <div class="ts-project-card-head">
            <div class="ts-project-card-name" :title="proj.project_name">{{ proj.project_name }}</div>
            <div class="ts-project-card-hours" :class="{ active: cellValue(proj.project_id, selectedDate) > 0 }">
              {{ cellValue(proj.project_id, selectedDate) || 0 }}h
              <el-icon v-if="isApproved(proj.project_id, selectedDate)" :size="12" title="已审批锁定" style="margin-left: 4px; color: var(--el-color-warning);"><Lock /></el-icon>
            </div>
          </div>
          <div class="ts-project-card-actions">
            <div class="ts-presets">
              <button
                v-for="preset in [2, 4, 6, 8]"
                :key="preset"
                class="ts-preset-btn"
                :class="{ active: cellValue(proj.project_id, selectedDate) === preset }"
                @click="setCell(proj.project_id, selectedDate, preset)"
              >{{ preset }}h</button>
            </div>
            <el-input-number
              :model-value="cellValue(proj.project_id, selectedDate)"
              :min="0" :max="24" :step="0.5" :precision="1"
              size="small"
              controls-position="right"
              style="width: 110px"
              @update:model-value="(v: number) => setCell(proj.project_id, selectedDate, v ?? 0)"
            />
          </div>
          <div class="ts-project-card-detail">
            <el-button type="primary" link size="small" @click="openDetailDialog(proj.project_id)">
              📋 详细
            </el-button>
          </div>
        </div>
        <div class="ts-add-project-card" @click="openAddProject">
          <el-icon :size="18"><Plus /></el-icon>
          <span>添加项目</span>
        </div>
      </div>
    </div>

    <!-- ═══ 周视图（网格） ═══ -->
    <div v-else class="ts-grid-wrap" v-loading="loading">
      <table class="ts-grid">
        <thead>
          <tr>
            <th class="ts-col-project">项目</th>
            <th
              v-for="(d, i) in weekDays"
              :key="i"
              class="ts-col-day"
              :class="{ 'is-today': d.isToday, 'is-weekend': d.isWeekend }"
            >
              <div class="ts-day-name">{{ d.dayName }}</div>
              <div class="ts-day-date">{{ d.dateLabel }}</div>
            </th>
            <th class="ts-col-total">合计</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="proj in projectRows" :key="proj.project_id">
            <td class="ts-col-project">
              <div class="ts-project-name" :title="proj.project_name">{{ proj.project_name }}</div>
            </td>
            <td
              v-for="(d, i) in weekDays"
              :key="i"
              class="ts-cell"
              :class="{ 'is-weekend': d.isWeekend, 'has-value': cellValue(proj.project_id, d.date) > 0 }"
            >
              <input
                class="ts-input"
                type="number" min="0" max="24" step="0.5"
                :value="cellValue(proj.project_id, d.date) || ''"
                placeholder="-"
                @input="onCellInput(proj.project_id, d.date, ($event.target as HTMLInputElement).value)"
              />
            </td>
            <td class="ts-col-total">{{ rowTotal(proj.project_id) || '-' }}</td>
          </tr>
          <tr v-if="projectRows.length === 0">
            <td :colspan="weekDays.length + 2" class="ts-empty">暂无参与项目，请联系项目经理分配</td>
          </tr>
        </tbody>
        <tfoot v-if="projectRows.length">
          <tr>
            <td class="ts-col-project ts-foot-label">每日合计</td>
            <td
              v-for="(d, i) in weekDays"
              :key="i"
              class="ts-foot-day"
              :class="{ 'is-over': dayTotal(d.date) > 8, 'is-weekend': d.isWeekend }"
            >{{ dayTotal(d.date) || '-' }}</td>
            <td class="ts-col-total ts-week-total">{{ weekTotal }}</td>
          </tr>
        </tfoot>
      </table>
    </div>

    <p class="ts-hint">
      {{ viewMode === 'day'
        ? '提示：点击 2h/4h/6h/8h 快捷按钮或微调小时数，修改后点"保存"提交。'
        : '提示：直接在格子中输入小时数，超过 8 小时的当日合计会标红。' }}
    </p>

    <!-- 添加项目弹窗 -->
    <el-dialog v-model="showAddProject" title="添加项目填报" width="420px" append-to-body>
      <el-select
        v-model="addProjectId"
        placeholder="选择要记工时的项目"
        filterable
        style="width: 100%"
      >
        <el-option
          v-for="p in availableProjects"
          :key="p.id"
          :label="p.client_name || p.name"
          :value="p.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="showAddProject = false">取消</el-button>
        <el-button type="primary" :disabled="!addProjectId" @click="confirmAddProject">添加</el-button>
      </template>
    </el-dialog>

    <!-- 细粒度工时填报弹窗 -->
    <WorkHourEntryDialog
      v-model="detailDialogVisible"
      :project-id="detailProjectId"
      :date="selectedDate"
      @saved="onDetailSaved"
    />

    <!-- 平台外工作快捷录入 -->
    <WorkHourExternalEntryDialog v-model="showExternalDialog" :projects="projectRows" @saved="loadRange" />

    <WorkHourNlpInput v-model="showNlpDialog" :projects="projectRows" @saved="loadRange" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import dayjs from 'dayjs'
import { ArrowLeft, ArrowRight, Clock, Lock, MagicStick, Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { listEntries, getMyAssignments, type WorkHourEntryRecord } from '@/services/staffApi'
import WorkHourEntryDialog from './WorkHourEntryDialog.vue'
import WorkHourExternalEntryDialog from './WorkHourExternalEntryDialog.vue'
import WorkHourNlpInput from './WorkHourNlpInput.vue'
import WorkHourTimelineBar from './WorkHourTimelineBar.vue'
import { listProjects } from '@/services/commonApi'
import http from '@/utils/http'
import { workHourEntries as P_whe, workHours as P_wh_paths } from '@/services/apiPaths'

const props = defineProps<{ staffId: string; aiSuggestions?: any[] }>()
const emit = defineEmits<{ (e: 'ai-fill'): void }>()
const timelineRef = ref<InstanceType<typeof WorkHourTimelineBar> | null>(null)
// AI 建议回填
watch(() => props.aiSuggestions, (suggestions) => {
  if (!suggestions || suggestions.length === 0) return
  for (const s of suggestions) {
    const dateKey = s.work_date || s.date
    if (s.project_id && dateKey && s.hours > 0) {
      setCell(s.project_id, dateKey, s.hours)
      if (!projects.value.some(p => p.project_id === s.project_id)) {
        projects.value.push({ project_id: s.project_id, project_name: s.project_name || s.project_id })
      }
    }
  }
}, { deep: true })

const viewMode = ref<'day' | 'week'>('day')
const loading = ref(false)
const saving = ref(false)
const autoCollecting = ref(false)
const anchor = ref(dayjs())
const projects = ref<any[]>([])
const records = ref<WorkHourEntryRecord[]>([])
const edits = ref<Record<string, number>>({})

// 细粒度工时弹窗状态
const detailDialogVisible = ref(false)
const detailProjectId = ref('')

// 平台外工作快捷录入弹窗
const showExternalDialog = ref(false)
const showNlpDialog = ref(false)

function openDetailDialog(projectId: string) {
  detailProjectId.value = projectId
  detailDialogVisible.value = true
}

function onDetailSaved() {
  ElMessage.success('细粒度工时已保存')
}

async function fillFromEditTime() {
  const targetDate = selectedDate.value
  try {
    const { data } = await http.get(P_wh_paths.editTimeSuggest, {
      params: { staff_id: props.staffId, target_date: targetDate }
    })
    const suggestions = data?.suggestions || (data as any)?.suggestions || []
    if (suggestions.length === 0) {
      ElMessage.info('当天无底稿编辑记录')
      return
    }
    // 按底稿编辑时长合计→填入第一个项目（简化策略）
    const totalHours = (data?.total_hours || (data as any)?.total_hours || 0) as number
    if (totalHours > 0 && projects.value.length > 0) {
      // 均分到有记录的项目
      const perProject = +(totalHours / projects.value.length).toFixed(1)
      for (const proj of projects.value) {
        setCell(proj.project_id, targetDate, Math.min(perProject, 8))
      }
      ElMessage.success(`已从编辑记录填充 ${totalHours.toFixed(1)}h（${suggestions.length} 个底稿）`)
    }
  } catch {
    ElMessage.warning('获取编辑记录失败')
  }
}

async function handleAutoCollect() {
  autoCollecting.value = true
  try {
    const { api } = await import('@/services/apiProxy')
    const today = new Date().toISOString().slice(0, 10)
    const result = await api.post('/api/workhours/auto-collect', null, {
      params: { date_from: today, date_to: today }
    }) as any
    const created = result?.created || 0
    if (created > 0) {
      ElMessage.success(`已采集 ${created} 条工时草稿`)
      await loadRange()
    } else {
      ElMessage.info('暂无新的可采集工时')
    }
  } catch (e: any) {
    ElMessage.warning('自动采集失败，请手动填报')
  } finally {
    autoCollecting.value = false
  }
}

function handleToolCommand(cmd: string) {
  switch (cmd) {
    case 'external': showExternalDialog.value = true; break
    case 'editTime': fillFromEditTime(); break
    case 'aiFill': emit('ai-fill'); break
    case 'nlp': showNlpDialog.value = true; break
  }
}

const hasUnsavedChanges = computed(() => Object.keys(edits.value).length > 0)

async function confirmDiscardIfDirty(): Promise<boolean> {
  if (!hasUnsavedChanges.value) return true
  try {
    const { ElMessageBox } = await import('element-plus')
    await ElMessageBox.confirm('当前有未保存的工时修改，切换将丢失。是否继续？', '提示', {
      confirmButtonText: '放弃修改',
      cancelButtonText: '取消',
      type: 'warning',
    })
    return true
  } catch {
    return false
  }
}

// 添加项目
const showAddProject = ref(false)
const addProjectId = ref('')
const allProjects = ref<any[]>([])
const manualProjects = ref<any[]>(loadManualProjects())  // 用户手动添加的项目（localStorage 持久化）

function manualStorageKey() {
  return `ts_manual_projects_${props.staffId || 'anon'}`
}
function loadManualProjects(): any[] {
  try {
    const raw = localStorage.getItem(`ts_manual_projects_${props.staffId || 'anon'}`)
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}
function saveManualProjects() {
  try {
    localStorage.setItem(manualStorageKey(), JSON.stringify(manualProjects.value))
  } catch { /* ignore quota */ }
}

const availableProjects = computed(() =>
  allProjects.value.filter(p => !projects.value.some(pr => pr.project_id === p.id))
)

async function openAddProject() {
  showAddProject.value = true
  addProjectId.value = ''
  if (allProjects.value.length === 0) {
    try { allProjects.value = await listProjects() } catch { /* ignore */ }
  }
}

function confirmAddProject() {
  const proj = allProjects.value.find(p => p.id === addProjectId.value)
  if (proj && !projects.value.some(pr => pr.project_id === proj.id)) {
    const entry = { project_id: proj.id, project_name: proj.client_name || proj.name }
    manualProjects.value.push(entry)
    projects.value.push(entry)
    saveManualProjects()
  }
  showAddProject.value = false
}

const recordMap = computed(() => {
  const m: Record<string, WorkHourEntryRecord> = {}
  for (const r of records.value) m[`${r.project_id}|${r.date}`] = r
  return m
})

const DAY_NAMES = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

const weekStart = computed(() => anchor.value.startOf('week'))
const selectedDate = computed(() => anchor.value.format('YYYY-MM-DD'))

const weekDays = computed(() => {
  const today = dayjs().format('YYYY-MM-DD')
  return Array.from({ length: 7 }, (_, i) => {
    const d = weekStart.value.add(i, 'day')
    const dateStr = d.format('YYYY-MM-DD')
    return {
      date: dateStr,
      dayName: DAY_NAMES[d.day()],
      dateLabel: d.format('MM/DD'),
      isToday: dateStr === today,
      isWeekend: d.day() === 0 || d.day() === 6,
    }
  })
})

const navLabel = computed(() => {
  if (viewMode.value === 'day') {
    return anchor.value.format('YYYY年MM月DD日') + ` ${DAY_NAMES[anchor.value.day()]}`
  }
  const end = weekStart.value.add(6, 'day')
  return `${weekStart.value.format('MM月DD日')} - ${end.format('MM月DD日')}`
})

const dayFullLabel = computed(() => {
  const d = anchor.value
  const today = dayjs().format('YYYY-MM-DD')
  const prefix = d.format('YYYY-MM-DD') === today ? '今天 · ' : ''
  return prefix + d.format('MM月DD日 ') + DAY_NAMES[d.day()]
})

const isCurrent = computed(() => {
  if (viewMode.value === 'day') return anchor.value.isSame(dayjs(), 'day')
  return weekStart.value.isSame(dayjs().startOf('week'), 'day')
})

const projectRows = computed(() => projects.value)

function cellKey(p: string, d: string) { return `${p}|${d}` }

function cellValue(projectId: string, date: string): number {
  const k = cellKey(projectId, date)
  if (k in edits.value) return edits.value[k]
  return recordMap.value[k]?.hours ?? 0
}

function isApproved(projectId: string, dateStr: string): boolean {
  return records.value.some(r => r.project_id === projectId && r.date === dateStr && r.status === 'approved')
}

function setCell(projectId: string, date: string, value: number) {
  // 审批锁定守卫
  if (isApproved(projectId, date)) {
    ElMessage.warning('该条目已审批通过，不可修改')
    return
  }
  edits.value[cellKey(projectId, date)] = Math.max(0, Math.min(24, value))
}

function onCellInput(projectId: string, date: string, value: string) {
  const num = parseFloat(value)
  setCell(projectId, date, isNaN(num) ? 0 : num)
}

function rowTotal(projectId: string): number {
  return weekDays.value.reduce((s, d) => s + cellValue(projectId, d.date), 0)
}
function dayTotal(date: string): number {
  return projectRows.value.reduce((s, p) => s + cellValue(p.project_id, date), 0)
}
const weekTotal = computed(() => projectRows.value.reduce((s, p) => s + rowTotal(p.project_id), 0))
const selectedDayTotal = computed(() => dayTotal(selectedDate.value))

async function shift(delta: number) {
  if (!await confirmDiscardIfDirty()) return
  anchor.value = viewMode.value === 'day'
    ? anchor.value.add(delta, 'day')
    : anchor.value.add(delta * 7, 'day')
  loadRange()
}
async function gotoNow() {
  if (!await confirmDiscardIfDirty()) return
  anchor.value = dayjs(); loadRange()
}

async function loadRange() {
  if (!props.staffId) return
  loading.value = true
  edits.value = {}
  try {
    const start = weekStart.value.format('YYYY-MM-DD')
    const end = weekStart.value.add(6, 'day').format('YYYY-MM-DD')
    // 跨项目单次请求加载所有工时条目
    const { data } = await http.get(P_wh_paths.myEntries, { params: { start_date: start, end_date: end } })
    const allEntries = (Array.isArray(data) ? data : data?.items || []) as WorkHourEntryRecord[]
    records.value = allEntries
    // 合并：已有工时记录的项目（确保显示为行）
    for (const r of records.value) {
      if (!projects.value.some(p => p.project_id === r.project_id)) {
        projects.value.push({ project_id: r.project_id, project_name: (r as any).project_name || r.project_id })
      }
    }
    for (const m of manualProjects.value) {
      if (!projects.value.some(p => p.project_id === m.project_id)) {
        projects.value.push(m)
      }
    }
  } finally {
    loading.value = false
  }
}

async function saveAll() {
  const changes = Object.entries(edits.value)
  if (changes.length === 0) { ElMessage.info('没有需要保存的修改'); return }
  saving.value = true
  try {
    // 按 projectId 分组
    const byProject: Record<string, Array<{ date: string; hours: number; description?: string }>> = {}
    for (const [key, hours] of changes) {
      const [projectId, date] = key.split('|')
      if (!byProject[projectId]) byProject[projectId] = []
      byProject[projectId].push({ date, hours, description: '' })
    }
    // 逐项目调 batch-quick 端点
    for (const [projectId, items] of Object.entries(byProject)) {
      await http.post(P_whe.list(projectId) + '/batch-quick', { items })
    }
    ElMessage.success(`已保存 ${changes.length} 项工时`)
    await loadRange()
  } catch {
    ElMessage.error('保存失败，请重试')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    const assigned = await getMyAssignments()
    projects.value = [...assigned]
  } catch { /* ignore */ }
  await loadRange()
})

defineExpose({ reload: loadRange })
</script>

<style scoped>
.timesheet { display: flex; flex-direction: column; gap: 16px; }

/* 工具栏 */
.ts-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.ts-toolbar-left { display: flex; align-items: center; gap: 20px; }
.ts-nav { display: flex; align-items: center; gap: 8px; }
.ts-nav-label {
  font-size: 14px; font-weight: 600;
  color: var(--gt-color-text-primary, #1a1a1a);
  min-width: 180px; text-align: center;
}
.ts-toolbar-right { display: flex; gap: 8px; align-items: center; }
.ts-unsaved-badge { font-size: 12px; color: var(--el-color-warning, #e6a23c); font-weight: 600; }

/* ═══ 日视图 ═══ */
.ts-day-view { display: flex; flex-direction: column; gap: 16px; }

.ts-day-summary {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px 20px;
  background: linear-gradient(135deg, #f4f0fa 0%, #faf8fd 100%);
  border: 1px solid var(--gt-purple-border, #e5d5f5);
  border-radius: 12px;
}
.ts-day-summary-icon {
  width: 48px; height: 48px; border-radius: 12px;
  background: var(--gt-purple, #4b2d77); color: #fff;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.ts-day-summary-total {
  font-size: 26px; font-weight: 700; color: var(--gt-purple, #4b2d77); line-height: 1;
}
.ts-day-summary-total span { font-size: 14px; font-weight: 500; }
.ts-day-summary-sub { font-size: 13px; color: var(--gt-color-text-secondary, #666); margin-top: 4px; }
.ts-day-summary-bar { flex: 1; margin-left: 12px; min-width: 120px; }
.ts-day-summary-target { font-size: 11px; color: var(--gt-color-text-tertiary, #999); margin-top: 4px; display: block; }

.ts-project-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}
.ts-project-card {
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: 10px;
  padding: 14px 16px;
  transition: all 0.2s;
}
.ts-project-card:hover {
  border-color: var(--gt-purple-border, #d8b8ee);
  box-shadow: 0 2px 10px rgba(75,45,119,0.08);
}
.ts-project-card-head {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;
}
.ts-project-card-name {
  font-size: 14px; font-weight: 600; color: var(--gt-color-text-primary, #1a1a1a);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 200px;
}
.ts-project-card-hours {
  font-size: 16px; font-weight: 700; color: var(--gt-color-text-tertiary, #ccc);
}
.ts-project-card-hours.active { color: var(--gt-purple, #4b2d77); }
.ts-project-card-actions {
  display: flex; justify-content: space-between; align-items: center; gap: 12px;
}
.ts-presets { display: flex; gap: 6px; }
.ts-preset-btn {
  border: 1px solid var(--gt-color-border, #dcdfe6);
  background: #fff;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
  color: var(--gt-color-text-secondary, #666);
  transition: all 0.15s;
}
.ts-preset-btn:hover { border-color: var(--gt-purple, #4b2d77); color: var(--gt-purple, #4b2d77); }
.ts-preset-btn.active {
  background: var(--gt-purple, #4b2d77); border-color: var(--gt-purple, #4b2d77); color: #fff;
}

.ts-project-card-detail {
  margin-top: 8px;
  text-align: right;
}

.ts-empty-card {
  padding: 48px; text-align: center;
  color: var(--gt-color-text-tertiary, #999);
  border: 1px dashed var(--gt-color-border, #dcdfe6);
  border-radius: 10px;
}
.ts-empty-card p { margin: 0 0 12px; }

.ts-add-project-card {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px dashed var(--gt-color-border, #dcdfe6);
  border-radius: 10px;
  padding: 14px;
  color: var(--gt-color-text-tertiary, #999);
  cursor: pointer;
  transition: all 0.2s;
  font-size: 13px;
}
.ts-add-project-card:hover {
  border-color: var(--gt-purple, #4b2d77);
  color: var(--gt-purple, #4b2d77);
  background: var(--gt-purple-light, #f4f0fa);
}

/* ═══ 周视图网格 ═══ */
.ts-grid-wrap {
  overflow-x: auto;
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: 8px;
}
.ts-grid { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 720px; }
.ts-grid th, .ts-grid td { border: 1px solid var(--gt-color-border-lighter, #f0f0f0); padding: 0; text-align: center; }
.ts-grid thead th { background: var(--gt-purple-light, #f4f0fa); padding: 8px 4px; font-weight: 600; color: var(--gt-color-text-secondary, #555); }
.ts-col-project {
  width: 200px; text-align: left !important; padding: 8px 12px !important;
  position: sticky; left: 0; background: #fff; z-index: 1;
}
.ts-grid thead .ts-col-project { background: var(--gt-purple-light, #f4f0fa); }
.ts-project-name { font-weight: 500; color: var(--gt-color-text-primary, #1a1a1a); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ts-col-day { min-width: 72px; }
.ts-day-name { font-weight: 600; }
.ts-day-date { font-size: 11px; color: var(--gt-color-text-tertiary, #999); margin-top: 2px; }
.ts-col-day.is-today {
  background: var(--gt-purple-light, #f0e9f9);
  color: var(--gt-purple, #4b2d77);
  box-shadow: inset 0 -3px 0 var(--gt-purple, #4b2d77);
}
.ts-col-day.is-today .ts-day-name { color: var(--gt-purple, #4b2d77); font-weight: 700; }
.ts-col-day.is-today .ts-day-date { color: var(--gt-purple, #4b2d77); }
.ts-col-day.is-weekend { background: #faf9fc; }
.ts-col-total { width: 64px; font-weight: 600; background: #fafafa; color: var(--gt-purple, #4b2d77); }
.ts-cell { padding: 0; height: 40px; }
.ts-cell.is-weekend { background: #fcfbfd; }
.ts-cell.has-value { background: var(--gt-purple-light, #f4f0fa); }
.ts-input {
  width: 100%; height: 40px; border: none; background: transparent; text-align: center;
  font-size: 13px; color: var(--gt-color-text-primary, #1a1a1a); outline: none; -moz-appearance: textfield;
}
.ts-input::-webkit-outer-spin-button, .ts-input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.ts-input:focus { background: #fff; box-shadow: inset 0 0 0 2px var(--gt-purple, #4b2d77); }
.ts-empty { padding: 40px !important; color: var(--gt-color-text-tertiary, #999); text-align: center !important; }
.ts-grid tfoot td { background: #fafafa; font-weight: 600; padding: 8px 4px; }
.ts-foot-label { text-align: right !important; color: var(--gt-color-text-secondary, #666); }
.ts-foot-day.is-over { color: var(--el-color-danger, #f56c6c); }
.ts-foot-day.is-weekend { background: #f5f3f8; }
.ts-week-total { color: var(--gt-purple, #4b2d77); font-size: 14px; }

.ts-hint { font-size: 12px; color: var(--gt-color-text-tertiary, #999); margin: 0; }
</style>
