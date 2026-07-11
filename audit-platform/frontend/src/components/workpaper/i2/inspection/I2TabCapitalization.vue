<template>
  <div class="i2-capitalization">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-6 研发项目资本化时点判断（CAS6五条件核心）</span>
      <div class="section-actions">
        <el-button size="small" type="primary" text @click="handleAiSuggest">
          <el-icon><MagicStick /></el-icon> AI建议
        </el-button>
        <el-button size="small" type="default" text @click="handleReview">
          复核
        </el-button>
      </div>
    </div>

    <!-- 蓝色引导面板：CAS6第9条原文 + 五条件解读 -->
    <div class="cas6-guide-panel">
      <div class="guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>CAS6第9条 — 企业内部研究开发项目开发阶段支出资本化条件</span>
      </div>
      <div class="guide-body">
        <p class="guide-quote">
          企业内部研究开发项目开发阶段的支出，同时满足下列条件的，才能确认为无形资产：
        </p>
        <div class="conditions-grid">
          <div class="condition-item">
            <span class="condition-num">①</span>
            <span class="condition-text"><strong>技术可行性</strong> — 完成该无形资产使其能够使用或出售在技术上具有可行性</span>
          </div>
          <div class="condition-item">
            <span class="condition-num">②</span>
            <span class="condition-text"><strong>完成意图</strong> — 具有完成该无形资产并使用或出售的意图</span>
          </div>
          <div class="condition-item">
            <span class="condition-num">③</span>
            <span class="condition-text"><strong>使用或出售能力</strong> — 能够证明运用该无形资产生产的产品存在市场或无形资产自身存在市场</span>
          </div>
          <div class="condition-item">
            <span class="condition-num">④</span>
            <span class="condition-text"><strong>未来经济利益</strong> — 有足够的技术、财务资源和其他资源支持完成开发</span>
          </div>
          <div class="condition-item">
            <span class="condition-num">⑤</span>
            <span class="condition-text"><strong>资源充足</strong> — 归属于该无形资产开发阶段的支出能够可靠地计量</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 项目选择器 -->
    <div class="project-selector">
      <span class="selector-label">研发项目：</span>
      <el-select
        v-model="selectedProject"
        placeholder="选择研发项目"
        size="default"
        style="width: 320px"
        @change="onProjectChange"
      >
        <el-option
          v-for="proj in projectOptions"
          :key="proj"
          :label="proj"
          :value="proj"
        />
      </el-select>
      <el-button
        v-if="!selectedProject"
        size="small"
        type="primary"
        plain
        style="margin-left: 12px"
        @click="handleAddProject"
      >
        + 新增项目
      </el-button>
    </div>

    <!-- 五条件矩阵（当选中项目时显示） -->
    <div v-if="selectedProject" class="conditions-matrix">
      <div
        v-for="(cond, idx) in currentConditions"
        :key="cond.id"
        class="condition-card"
      >
        <div class="condition-card-header">
          <span class="condition-card-num">{{ conditionIcons[idx] }}</span>
          <span class="condition-card-title">{{ cond.name }}</span>
        </div>

        <div class="condition-card-body">
          <!-- 是/否/NA 单选 -->
          <div class="condition-radio-group">
            <el-radio-group
              :model-value="cond.result"
              @change="(v: string) => onConditionResultChange(idx, v as 'yes' | 'no' | 'na')"
            >
              <el-radio-button value="yes">是</el-radio-button>
              <el-radio-button value="no">否</el-radio-button>
              <el-radio-button value="na">不适用</el-radio-button>
            </el-radio-group>
          </div>

          <!-- 证据描述 -->
          <div class="condition-evidence">
            <el-input
              :model-value="cond.evidence"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              placeholder="请描述支撑证据..."
              @change="(v: string) => onEvidenceChange(idx, v)"
            />
          </div>

          <!-- 附件上传 -->
          <div class="condition-attachment">
            <el-button size="small" type="default" plain @click="handleAttachUpload(idx)">
              📎 上传附件
            </el-button>
            <span v-if="attachments[idx]" class="attachment-name">{{ attachments[idx] }}</span>
          </div>
        </div>
      </div>

      <!-- 结论自动计算 -->
      <div :class="['conclusion-panel', conclusionClass]">
        <div class="conclusion-icon">
          {{ capitalizationResult.isMet ? '✅' : '❌' }}
        </div>
        <div class="conclusion-text">
          <strong>{{ capitalizationResult.conclusion }}</strong>
          <div v-if="!capitalizationResult.isMet && capitalizationResult.missingConditions.length > 0" class="missing-list">
            缺失条件：
            <el-tag
              v-for="id in capitalizationResult.missingConditions"
              :key="id"
              type="danger"
              size="small"
              style="margin-left: 4px"
            >
              {{ CAS6_CONDITION_NAMES[id as 1|2|3|4|5] }}
            </el-tag>
          </div>
        </div>
      </div>

      <!-- 资本化时点日期 -->
      <div class="capitalization-date-row">
        <span class="date-label">资本化时点日期（联动I2-2"资本化起点"列）：</span>
        <el-date-picker
          v-model="capitalizationDate"
          type="date"
          size="default"
          value-format="YYYY-MM-DD"
          placeholder="选择资本化时点日期"
          :disabled="!capitalizationResult.isMet"
          @change="onCapDateChange"
        />
        <el-tag v-if="!capitalizationResult.isMet" type="info" size="small" style="margin-left: 8px">
          未满足资本化条件，无法设置时点
        </el-tag>
      </div>

      <!-- 保存按钮 -->
      <div class="table-actions">
        <el-button size="small" type="success" @click="handleSave">
          保存
        </el-button>
      </div>
    </div>

    <!-- 无项目时提示 -->
    <div v-else class="no-project-hint">
      <el-empty description="请选择或新增研发项目以开始CAS6五条件检查" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { MagicStick, InfoFilled } from '@element-plus/icons-vue'
import {
  evaluateCapitalization,
  CAS6_CONDITION_NAMES,
  type CAS6Condition,
  type CapitalizationResult,
} from '../../composables/useI2CapitalizationEngine'

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
}>()

const emit = defineEmits<{
  'save': []
  'navigate-sheet': [sheetName: string]
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

// ─── Constants ───────────────────────────────────────────────────────────────

const conditionIcons = ['①', '②', '③', '④', '⑤']

const STORAGE_KEY = 'I2-6-capitalization'

// ─── State ───────────────────────────────────────────────────────────────────

const selectedProject = ref('')
const capitalizationDate = ref('')
const attachments = ref<string[]>(['', '', '', '', ''])

/** All project data: Map<projectName, { conditions, date }> */
const projectDataMap = ref<Map<string, { conditions: CAS6Condition[]; date: string }>>(new Map())

// ─── Load from allResponses ──────────────────────────────────────────────────

function loadData() {
  const raw = props.allResponses.get(STORAGE_KEY)
  if (raw) {
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : (raw.remark ? JSON.parse(raw.remark) : raw)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        const map = new Map<string, { conditions: CAS6Condition[]; date: string }>()
        for (const [projName, projData] of Object.entries(parsed as Record<string, any>)) {
          map.set(projName, {
            conditions: Array.isArray(projData.conditions)
              ? projData.conditions.map((c: any) => ({
                  id: c.id,
                  name: c.name || CAS6_CONDITION_NAMES[c.id as 1|2|3|4|5] || '',
                  result: c.result || 'na',
                  evidence: c.evidence || '',
                }))
              : createEmptyConditions(),
            date: projData.date || '',
          })
        }
        projectDataMap.value = map
      }
    } catch { /* ignore */ }
  }
}

watch(() => props.allResponses, () => loadData(), { immediate: true })

// ─── Project Options (from I2-2 detail rows or existing data) ────────────────

const projectOptions = computed(() => {
  const fromDetail = getDetailProjectNames()
  const fromMap = Array.from(projectDataMap.value.keys())
  const all = new Set([...fromDetail, ...fromMap])
  return Array.from(all).filter(Boolean)
})

function getDetailProjectNames(): string[] {
  const raw = props.allResponses.get('I2-2-rows')
  if (!raw) return []
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : (raw.remark ? JSON.parse(raw.remark) : raw)
    if (Array.isArray(parsed)) {
      return parsed.map((r: any) => r.projectName).filter(Boolean)
    }
  } catch { /* ignore */ }
  return []
}

// ─── Current Project Conditions ──────────────────────────────────────────────

const currentConditions = computed<CAS6Condition[]>(() => {
  if (!selectedProject.value) return createEmptyConditions()
  const data = projectDataMap.value.get(selectedProject.value)
  return data?.conditions ?? createEmptyConditions()
})

const capitalizationResult = computed<CapitalizationResult>(() => {
  return evaluateCapitalization(currentConditions.value)
})

const conclusionClass = computed(() => {
  if (!selectedProject.value) return 'conclusion-neutral'
  return capitalizationResult.value.isMet ? 'conclusion-met' : 'conclusion-not-met'
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

function createEmptyConditions(): CAS6Condition[] {
  return [
    { id: 1, name: '技术可行性', result: 'na', evidence: '' },
    { id: 2, name: '完成意图', result: 'na', evidence: '' },
    { id: 3, name: '使用或出售能力', result: 'na', evidence: '' },
    { id: 4, name: '未来经济利益', result: 'na', evidence: '' },
    { id: 5, name: '资源充足', result: 'na', evidence: '' },
  ]
}

function ensureProjectData(projName: string) {
  if (!projectDataMap.value.has(projName)) {
    projectDataMap.value.set(projName, {
      conditions: createEmptyConditions(),
      date: '',
    })
  }
}

// ─── Events ──────────────────────────────────────────────────────────────────

function onProjectChange(projName: string) {
  ensureProjectData(projName)
  const data = projectDataMap.value.get(projName)!
  capitalizationDate.value = data.date
  attachments.value = ['', '', '', '', '']
}

function onConditionResultChange(condIdx: number, result: 'yes' | 'no' | 'na') {
  if (!selectedProject.value) return
  ensureProjectData(selectedProject.value)
  const data = projectDataMap.value.get(selectedProject.value)!
  data.conditions[condIdx] = { ...data.conditions[condIdx], result }
  // Force reactivity
  projectDataMap.value = new Map(projectDataMap.value)
}

function onEvidenceChange(condIdx: number, evidence: string) {
  if (!selectedProject.value) return
  ensureProjectData(selectedProject.value)
  const data = projectDataMap.value.get(selectedProject.value)!
  data.conditions[condIdx] = { ...data.conditions[condIdx], evidence }
  projectDataMap.value = new Map(projectDataMap.value)
}

function onCapDateChange(date: string) {
  if (!selectedProject.value) return
  ensureProjectData(selectedProject.value)
  const data = projectDataMap.value.get(selectedProject.value)!
  data.date = date || ''
  projectDataMap.value = new Map(projectDataMap.value)
}

// ─── Add Project ─────────────────────────────────────────────────────────────

async function handleAddProject() {
  try {
    const { value } = await ElMessageBox.prompt('请输入研发项目名称', '新增项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：XX智能平台研发项目',
    })
    if (value?.trim()) {
      const name = value.trim()
      ensureProjectData(name)
      selectedProject.value = name
      capitalizationDate.value = ''
      ElMessage.success(`已添加项目：${name}`)
    }
  } catch {
    // cancelled
  }
}

// ─── Save ────────────────────────────────────────────────────────────────────

async function handleSave() {
  // Serialize Map to JSON object
  const obj: Record<string, any> = {}
  for (const [projName, data] of projectDataMap.value.entries()) {
    obj[projName] = {
      conditions: data.conditions,
      date: data.date,
    }
  }
  await props.saveResponse('I2-6', { [STORAGE_KEY]: JSON.stringify(obj) })
  emit('save')
  ElMessage.success('资本化时点判断已保存')
}

// ─── AI Suggest ──────────────────────────────────────────────────────────────

function handleAiSuggest() {
  if (!selectedProject.value) {
    ElMessage.warning('请先选择研发项目')
    return
  }
  ElMessage.info(`AI正在为"${selectedProject.value}"生成五条件建议...`)
  console.log('[I2-Capitalization] AI suggest for:', selectedProject.value)
}

// ─── Attachment ──────────────────────────────────────────────────────────────

function handleAttachUpload(condIdx: number) {
  ElMessage.info('附件上传功能开发中')
}

// ─── Review ──────────────────────────────────────────────────────────────────

function handleReview() {
  openReviewDialog('I2-6-资本化时点判断')
}
</script>

<style scoped>
.i2-capitalization {
  font-size: 13px;
  padding: 16px;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
}
.section-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 蓝色引导面板 */
.cas6-guide-panel {
  background: linear-gradient(135deg, #eff6ff, #dbeafe);
  border: 1px solid #93c5fd;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 20px;
}
.guide-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #1e40af;
  margin-bottom: 12px;
}
.guide-body {
  font-size: 12px;
  color: #1e3a5f;
  line-height: 1.6;
}
.guide-quote {
  margin: 0 0 10px 0;
  font-style: italic;
  color: #1e40af;
}
.conditions-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.condition-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
}
.condition-num {
  color: #2563eb;
  font-weight: 700;
  font-size: 14px;
  flex-shrink: 0;
}
.condition-text {
  font-size: 12px;
  color: #334155;
}

/* 项目选择器 */
.project-selector {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
  padding: 12px 16px;
  background: #f9fafb;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
}
.selector-label {
  font-weight: 600;
  color: #374151;
  margin-right: 12px;
  white-space: nowrap;
}

/* 五条件矩阵 */
.conditions-matrix {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.condition-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}
.condition-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
  font-weight: 600;
  color: #374151;
}
.condition-card-num {
  color: #2563eb;
  font-size: 16px;
}
.condition-card-title {
  font-size: 14px;
}
.condition-card-body {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.condition-radio-group {
  display: flex;
  align-items: center;
}
.condition-evidence {
  flex: 1;
}
.condition-attachment {
  display: flex;
  align-items: center;
  gap: 8px;
}
.attachment-name {
  font-size: 12px;
  color: #6b7280;
}

/* 结论面板 */
.conclusion-panel {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border-radius: 8px;
  margin-top: 8px;
}
.conclusion-met {
  background: #ecfdf5;
  border: 1px solid #6ee7b7;
}
.conclusion-not-met {
  background: #fef2f2;
  border: 1px solid #fca5a5;
}
.conclusion-neutral {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
}
.conclusion-icon {
  font-size: 24px;
}
.conclusion-text {
  font-size: 14px;
  color: #1f2937;
}
.missing-list {
  margin-top: 6px;
  font-size: 12px;
  color: #dc2626;
}

/* 资本化时点日期 */
.capitalization-date-row {
  display: flex;
  align-items: center;
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafbfc;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
}
.date-label {
  font-size: 13px;
  font-weight: 500;
  color: #374151;
  margin-right: 12px;
  white-space: nowrap;
}

/* 操作按钮 */
.table-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}

/* 无项目提示 */
.no-project-hint {
  margin-top: 40px;
}
</style>
