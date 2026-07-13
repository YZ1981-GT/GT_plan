<template>
  <div class="h3-tab-fair-value-review">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表用于复核公允价值模式下投资性房地产公允价值的确定，仅公允价值模式适用。</p>
        <p>2. 评价评估师胜任能力与独立性，复核评估方法（市场法/收益法/成本法）与关键假设（折现率、租金、资本化率）。</p>
        <p>3. 独立测算值 = 年租金 /(资本化率 − 增长率)；差异率 &gt;20% 或超出合理区间需重点关注并挑战假设。</p>
        <p>4. 公允价值变动通过 EventBus 联动 H3-1 审定表与附注披露。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：复核公允价值模式下投资性房地产公允价值计量的恰当性，评价评估师独立性与方法假设的合理性，确认公允价值变动损益准确。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H3-8" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ reviewCalcRows.length }} 行</el-tag>
    </div>

    <!-- 区域1：评估师信息 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(1) 评估师信息</span>
          <el-button size="small" @click="generateAI('H3-8-appraiser')">AI</el-button>
        </div>
      </template>
      <div class="info-grid">
        <div class="info-item">
          <label>评估机构</label>
          <el-input v-model="appraiserInfo.firm" size="small" :disabled="isReadonly" @change="onInfoChange" />
        </div>
        <div class="info-item">
          <label>资质等级</label>
          <el-input v-model="appraiserInfo.qualification" size="small" :disabled="isReadonly" @change="onInfoChange" />
        </div>
        <div class="info-item">
          <label>独立性声明</label>
          <el-select v-model="appraiserInfo.independence" size="small" :disabled="isReadonly" @change="onInfoChange">
            <el-option label="独立" value="独立" />
            <el-option label="存在关联" value="存在关联" />
          </el-select>
        </div>
      </div>
    </el-card>

    <!-- 区域2：评估方法与假设 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(2) 评估方法与关键假设</span>
          <el-button size="small" @click="generateAI('H3-8-method')">AI</el-button>
        </div>
      </template>
      <el-input v-model="methodText" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="描述评估方法(市场法/收益法/成本法)及关键参数假设..." :disabled="isReadonly" @change="onMethodChange" />
    </el-card>

    <!-- 区域3：复核计算（15公式） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(3) 复核计算（15公式验证）</span>
          <el-button size="small" @click="generateAI('H3-8-calc')">AI</el-button>
        </div>
      </template>
      <el-table :data="reviewCalcRows" border size="small" class="audit-table" :row-class-name="getCalcRowClass">
        <el-table-column prop="assetName" label="资产名称" min-width="120" />
        <el-table-column prop="appraisalValue" label="评估值" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.appraisalValue" size="small" :disabled="isReadonly" @change="onCalcRowChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="bookValue" label="账面值" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.bookValue" size="small" :disabled="isReadonly" @change="onCalcRowChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column label="差异" min-width="90" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="评估-账面">{{ fmtNum(row.appraisalValue - row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异率" width="80" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" :class="{ 'text-danger': Math.abs(calcDiffRate(row)) > 20 }">
              {{ row.bookValue ? calcDiffRate(row).toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="discountRate" label="收益法折现率" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.discountRate" size="small" :disabled="isReadonly" @change="onCalcRowChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="rentAssumption" label="租金假设" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.rentAssumption" size="small" :disabled="isReadonly" @change="onCalcRowChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="capRate" label="资本化率" width="80" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.capRate" size="small" :disabled="isReadonly" @change="onCalcRowChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column label="独立测算值" min-width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="年租金/(资本化率-增长率)">{{ fmtNum(row.independentCalc) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="独立vs评估差异" min-width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtNum(row.independentCalc - row.appraisalValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="在范围内" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.withinRange ? 'success' : 'danger'" size="small">
              {{ row.withinRange ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="结论" min-width="90">
          <template #default="{ row, $index }">
            <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" @change="onCalcRowChange($index, row)">
              <el-option label="合理" value="合理" />
              <el-option label="偏高" value="偏高" />
              <el-option label="偏低" value="偏低" />
            </el-select>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 区域4：假设挑战 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(4) 假设挑战清单</span>
          <span class="action-btns">
            <el-button size="small" :disabled="isReadonly" @click="addChallengeRow">+ 新增</el-button>
            <el-button size="small" @click="generateAI('H3-8-challenge')">AI</el-button>
          </span>
        </div>
      </template>
      <el-table :data="challengeRows" border size="small" class="audit-table">
        <el-table-column prop="assumption" label="关键假设" min-width="140">
          <template #default="{ row, $index }">
            <el-input v-model="row.assumption" size="small" :disabled="isReadonly" @change="onChallengeChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="appraiserValue" label="评估师假设值" min-width="110">
          <template #default="{ row, $index }">
            <el-input v-model="row.appraiserValue" size="small" :disabled="isReadonly" @change="onChallengeChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="auditorJudgment" label="审计师独立判断" min-width="120">
          <template #default="{ row, $index }">
            <el-input v-model="row.auditorJudgment" size="small" :disabled="isReadonly" @change="onChallengeChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="difference" label="差异" min-width="90">
          <template #default="{ row, $index }">
            <el-input v-model="row.difference" size="small" :disabled="isReadonly" @change="onChallengeChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="reasonableness" label="合理性结论" min-width="100">
          <template #default="{ row, $index }">
            <el-select v-model="row.reasonableness" size="small" :disabled="isReadonly" @change="onChallengeChange($index, row)">
              <el-option label="合理" value="合理" />
              <el-option label="偏乐观" value="偏乐观" />
              <el-option label="偏悲观" value="偏悲观" />
              <el-option label="不合理" value="不合理" />
            </el-select>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-8')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-8')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" placeholder="填写审计说明：评估师独立性与胜任能力评价、方法与假设复核、独立测算与评估值差异及处理。" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写审计结论：A、公允价值计量恰当、假设合理。B、除下列事项外未见异常。C、公允价值计量存在重大问题，不可确认。" :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabFairValueReview.vue — H3-8 公允价值复核
 * 四区域(评估师/方法/复核15公式/假设挑战)+AI+💬复核
 */
import { ref, reactive, computed, inject, toRef, onMounted } from 'vue'
import { useH3FairValueReview } from '../../composables/useH3FairValueReview'
import { useH3FormData } from '../../composables/useH3FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  measurementModel?: 'cost' | 'fair_value'
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('fair_value') as any,
})

const {
  appraiserInfo, methodText, reviewCalcRows, challengeRows,
  updateAppraiserInfo, updateMethod, updateCalcRow, updateChallengeRow, addChallengeRow,
} = useH3FairValueReview({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
})

// ─── 审计说明 / 审计结论（标准 checklist_responses 持久化） ───────────────────
const NOTE_KEY = 'H3-8-audit-note'
const CONCLUSION_KEY = 'H3-8-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void saveImmediate(NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void saveImmediate(CONCLUSION_KEY, val)
}

function onInfoChange() { updateAppraiserInfo(appraiserInfo) }
function onMethodChange() { updateMethod(methodText.value) }
function onCalcRowChange(index: number, row: any) {
  updateCalcRow(index, row)
  // 公允价值变动联动：publish 'h3:fair-value-changed' 事件
  publishFairValueChanged()
}
function onChallengeChange(index: number, row: any) { updateChallengeRow(index, row) }

/** EventBus: publish 'h3:fair-value-changed' */
function publishFairValueChanged() {
  const totalChange = reviewCalcRows.value.reduce((sum: number, r: any) => sum + (r.appraisalValue - r.bookValue || 0), 0)
  http.post(`/api/projects/${props.projectId}/events/publish`, {
    event_type: 'h3:fair-value-changed',
    payload: { wp_id: props.wpId, totalFairValueChange: totalChange },
  }).catch(() => { /* best effort */ })
}

function calcDiffRate(row: any): number {
  if (!row.bookValue || row.bookValue === 0) return 0
  return ((row.appraisalValue - row.bookValue) / row.bookValue) * 100
}

function getCalcRowClass({ row }: { row: any }): string {
  if (row.withinRange === false) return 'row-danger'
  if (Math.abs(calcDiffRate(row)) > 20) return 'row-warn'
  return ''
}

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-fair-value-review { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.section-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.action-btns { display: flex; gap: 4px; }
.info-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.info-item label { display: block; font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.audit-table :deep(.row-danger) { background-color: #fef0f0 !important; }
.audit-table :deep(.row-warn) { background-color: #fef9e7 !important; }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.text-danger { color: var(--el-color-danger); }
.conclusion-card { margin-top: 16px; }
</style>
