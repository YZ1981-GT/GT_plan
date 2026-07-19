<template>
  <div class="g6-tab-stage-classification">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：核实其他债权投资信用风险三阶段划分的合理性，验证企业阶段与审计阶段的一致性，为 G6-12 减值准备测算提供阶段依据。"
      class="objective-alert"
    />

    <div class="methodology-context">
      <p><strong>其他债权投资（FVOCI）ECL 三阶段划分标准（CAS 22）：</strong></p>
      <ul>
        <li><strong>Stage1</strong>：信用风险自初始确认以来未显著增加，或报告日适用较低信用风险豁免 → 12个月ECL</li>
        <li><strong>Stage2</strong>：信用风险显著增加（SICR）、未适用低风险豁免且尚未发生信用减值 → 整个存续期ECL</li>
        <li><strong>Stage3</strong>：已发生信用减值（8项可观察信息之一）→ 整个存续期ECL，利息按净额确认</li>
      </ul>
      <p class="method-sub">
        判定优先级：已减值（Stage3） &gt; SICR 且非低风险豁免（Stage2） &gt; 其余（Stage1）。
        低风险豁免的三项条件必须同时满足；仅有投资级评级或高质量担保并不足以单独适用豁免。
      </p>
      <p class="method-sub">
        FVOCI 减值损失计入损益、累计减值计入其他综合收益，不冲减资产负债表中的公允价值账面金额；阶段划分仍按一般法执行。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <G6EclImportExportDropdown
          :wp-id="wpId"
          sheet="G6-11"
          :disabled="isReadonly"
          @imported="onImported"
        />
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G6-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G6-11" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G6-12" :context-project-id="projectId" /></span>
      </div>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">G6-11 其他债权投资三阶段划分</h3>
      <div class="head-actions">
        <el-button size="small" :disabled="isReadonly" @click="handleAddProject">+ 新增投资项目</el-button>
        <el-button size="small" :disabled="isReadonly" @click="importFromG62">从 G6-2 带入</el-button>
        <el-button
          size="small"
          type="primary"
          :disabled="isReadonly || stageLogic.rows.value.length === 0"
          @click="syncStagesToG612"
        >
          同步阶段至 G6-12
        </el-button>
        <el-button size="small" @click="stageLogic.expandAll()">全部展开</el-button>
        <el-button size="small" @click="stageLogic.collapseAll()">全部折叠</el-button>
        <el-button
          size="small"
          :disabled="isReadonly || !aiAvailable"
          :loading="aiLoading"
          @click="fillAiConclusion"
        >
          🤖 AI辅助
        </el-button>
        <el-button size="small" @click="openReview">💬复核</el-button>
      </div>
    </div>

    <el-empty
      v-if="stageLogic.rows.value.length === 0"
      description="暂无投资项目，点击「新增投资项目」或「从 G6-2 带入」开始"
    />

    <el-table
      v-else
      :data="stageLogic.rows.value"
      border
      size="small"
      class="stage-main-table"
      :row-class-name="getRowClassName"
      row-key="id"
      :expand-row-keys="Array.from(stageLogic.expandedRowIds.value)"
      @expand-change="handleExpandChange"
    >
      <el-table-column type="expand">
        <template #default="scope">
          <div class="expand-detail">
            <div class="check-section">
              <div class="check-section-title">(一) 信用风险是否显著增加（13项考虑因素，任一项为「是」即SICR）</div>
              <el-table :data="scope.row.sectionOneChecks" border size="small" class="check-detail-table">
                <el-table-column label="序号" width="50" align="center">
                  <template #default="{ $index }">{{ $index + 1 }}</template>
                </el-table-column>
                <el-table-column label="需要考虑的信息" prop="label" min-width="220" />
                <el-table-column label="说明" min-width="280">
                  <template #default="{ row: item }"><span class="hint-text">{{ item.hint }}</span></template>
                </el-table-column>
                <el-table-column label="判断" width="120" align="center">
                  <template #default="{ $index, row: item }">
                    <el-select
                      v-if="!isReadonly"
                      :model-value="item.value"
                      size="small"
                      style="width: 100%"
                      @change="(v: string) => stageLogic.updateCheckValue(scope.row.id, 'significantIncrease', $index, v as any)"
                    >
                      <el-option value="是" label="是" />
                      <el-option value="否" label="否" />
                      <el-option value="不适用" label="不适用" />
                    </el-select>
                    <span v-else>{{ item.value || '—' }}</span>
                  </template>
                </el-table-column>
              </el-table>
              <div class="section-conclusion">
                <span class="sc-label">分析结论</span>
                <el-input
                  v-if="!isReadonly"
                  :model-value="scope.row.sectionConclusions.significantIncrease"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 3 }"
                  placeholder="就该投资项目信用风险是否显著增加作出综合判断..."
                  @input="(v: string) => stageLogic.updateSectionConclusion(scope.row.id, 'significantIncrease', v)"
                />
                <span v-else class="sc-text">{{ scope.row.sectionConclusions.significantIncrease || '—' }}</span>
              </div>
            </div>

            <div class="check-section">
              <div class="check-section-title">(二) 是否具有较低信用风险（3项同时满足方可豁免）</div>
              <el-table :data="scope.row.sectionTwoChecks" border size="small" class="check-detail-table">
                <el-table-column label="序号" width="50" align="center">
                  <template #default="{ $index }">{{ $index + 1 }}</template>
                </el-table-column>
                <el-table-column label="条件（同时满足）" prop="label" min-width="220" />
                <el-table-column label="说明" min-width="280">
                  <template #default="{ row: item }"><span class="hint-text">{{ item.hint }}</span></template>
                </el-table-column>
                <el-table-column label="判断" width="120" align="center">
                  <template #default="{ $index, row: item }">
                    <el-select
                      v-if="!isReadonly"
                      :model-value="item.value"
                      size="small"
                      style="width: 100%"
                      @change="(v: string) => stageLogic.updateCheckValue(scope.row.id, 'lowCreditRisk', $index, v as any)"
                    >
                      <el-option value="是" label="是" />
                      <el-option value="否" label="否" />
                    </el-select>
                    <span v-else>{{ item.value || '—' }}</span>
                  </template>
                </el-table-column>
              </el-table>
              <div class="section-conclusion">
                <span class="sc-label">分析结论</span>
                <el-input
                  v-if="!isReadonly"
                  :model-value="scope.row.sectionConclusions.lowCreditRisk"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 3 }"
                  placeholder="说明三项条件是否同时满足及低风险豁免是否适用..."
                  @input="(v: string) => stageLogic.updateSectionConclusion(scope.row.id, 'lowCreditRisk', v)"
                />
                <span v-else class="sc-text">{{ scope.row.sectionConclusions.lowCreditRisk || '—' }}</span>
              </div>
            </div>

            <div class="check-section">
              <div class="check-section-title">(三) 已发生信用减值的评估（8项可观察信息，任一项为「是」即Stage3）</div>
              <el-table :data="scope.row.sectionThreeChecks" border size="small" class="check-detail-table">
                <el-table-column label="序号" width="50" align="center">
                  <template #default="{ $index }">{{ $index + 1 }}</template>
                </el-table-column>
                <el-table-column label="可观察信息" prop="label" min-width="220" />
                <el-table-column label="说明" min-width="280">
                  <template #default="{ row: item }"><span class="hint-text">{{ item.hint }}</span></template>
                </el-table-column>
                <el-table-column label="判断" width="120" align="center">
                  <template #default="{ $index, row: item }">
                    <el-select
                      v-if="!isReadonly"
                      :model-value="item.value"
                      size="small"
                      style="width: 100%"
                      @change="(v: string) => stageLogic.updateCheckValue(scope.row.id, 'creditImpairment', $index, v as any)"
                    >
                      <el-option value="是" label="是" />
                      <el-option value="否" label="否" />
                    </el-select>
                    <span v-else>{{ item.value || '—' }}</span>
                  </template>
                </el-table-column>
              </el-table>
              <div class="section-conclusion">
                <span class="sc-label">分析结论</span>
                <el-input
                  v-if="!isReadonly"
                  :model-value="scope.row.sectionConclusions.creditImpairment"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 3 }"
                  placeholder="说明是否存在已发生信用减值的客观证据..."
                  @input="(v: string) => stageLogic.updateSectionConclusion(scope.row.id, 'creditImpairment', v)"
                />
                <span v-else class="sc-text">{{ scope.row.sectionConclusions.creditImpairment || '—' }}</span>
              </div>
            </div>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="投资项目" prop="investProject" min-width="150" fixed="left">
        <template #default="{ row }">
          <div class="project-name-cell">
            <span>{{ row.investProject }}</span>
            <el-button
              v-if="!isReadonly"
              size="small"
              type="danger"
              link
              class="delete-btn"
              @click.stop="handleRemoveRow(row.id, row.investProject)"
            >
              🗑️
            </el-button>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="账面余额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmt(row.bookBalance) }}</template>
      </el-table-column>
      <el-table-column label="显著增加" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.hasSignificantIncrease ? 'danger' : 'success'" size="small">
            {{ row.hasSignificantIncrease ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="低风险" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.hasLowCreditRisk ? 'success' : 'info'" size="small">
            {{ row.hasLowCreditRisk ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="已减值" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.hasCreditImpairment ? 'danger' : 'success'" size="small">
            {{ row.hasCreditImpairment ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="企业阶段" width="120" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.companyStage"
            size="small"
            @change="(v: string) => stageLogic.updateCompanyStage(row.id, v as any)"
          >
            <el-option value="Stage1" label="Stage1" />
            <el-option value="Stage2" label="Stage2" />
            <el-option value="Stage3" label="Stage3" />
          </el-select>
          <span v-else>{{ row.companyStage }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审计阶段" width="150" align="center">
        <template #default="{ row }">
          <div class="audit-stage-cell">
            <el-select
              v-if="!isReadonly"
              :model-value="row.auditStage"
              size="small"
              @change="(v: string) => stageLogic.updateAuditStage(row.id, v as any)"
            >
              <el-option value="Stage1" label="Stage1" />
              <el-option value="Stage2" label="Stage2" />
              <el-option value="Stage3" label="Stage3" />
            </el-select>
            <span v-else>{{ row.auditStage }}</span>
            <div v-if="row.auditStageManualOverride" class="override-tools">
              <el-tag size="small" type="warning">手动</el-tag>
              <el-button
                v-if="!isReadonly"
                size="small"
                link
                type="primary"
                @click="stageLogic.clearAuditStageOverride(row.id)"
              >
                恢复公式
              </el-button>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="一致性" width="100" align="center">
        <template #default="{ row }">
          <span v-if="row.isConsistent" class="badge-consistent">✓一致</span>
          <span v-else class="badge-inconsistent">✗不一致</span>
        </template>
      </el-table-column>
      <el-table-column label="差异说明" min-width="190">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.discrepancyNote"
            size="small"
            :placeholder="row.isConsistent ? '' : '请填写差异说明（必填）'"
            :class="{ 'required-field': !row.isConsistent && !row.discrepancyNote?.trim() }"
            @input="(v: string) => stageLogic.updateDiscrepancyNote(row.id, v)"
          />
          <span v-else>{{ row.discrepancyNote || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="150" align="center">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.indexRef"
            size="small"
            placeholder="如 wp:G6-2"
            @input="(v: string) => stageLogic.updateIndexRef(row.id, v)"
          />
          <GtIndexChip v-else :value="row.indexRef" :context-project-id="projectId" />
        </template>
      </el-table-column>
    </el-table>

    <div v-if="stageLogic.rows.value.length > 0" class="bottom-section">
      <div class="summary-stats">
        <span class="summary-label">阶段统计：</span>
        <el-tag type="success" size="small">Stage1: {{ stageLogic.summary.value.stage1Count }}</el-tag>
        <el-tag type="warning" size="small">Stage2: {{ stageLogic.summary.value.stage2Count }}</el-tag>
        <el-tag type="danger" size="small">Stage3: {{ stageLogic.summary.value.stage3Count }}</el-tag>
        <el-tag :type="stageLogic.summary.value.inconsistentCount ? 'danger' : 'info'" size="small">
          不一致: {{ stageLogic.summary.value.inconsistentCount }}
        </el-tag>
        <el-tag v-if="stageLogic.incompleteRows.value.length" type="warning" size="small">
          未检查完成: {{ stageLogic.incompleteRows.value.length }}
        </el-tag>
        <span class="summary-total">合计: {{ stageLogic.summary.value.total }} 项</span>
      </div>

      <el-card class="conclusion-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span>审计结论</span>
            <el-button
              size="small"
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="fillAiConclusion"
            >
              🤖 AI辅助
            </el-button>
          </div>
        </template>
        <el-input
          v-model="stageLogic.conclusion.value"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="对其他债权投资三阶段划分合理性的综合评价..."
        />
      </el-card>

      <details class="guide-details">
        <summary>📋 编制提示</summary>
        <div class="guide-content">
          <p>1. 其他债权投资适用一般法：Stage1按12个月ECL，Stage2/3按整个存续期ECL计量。</p>
          <p>2. 判定必须依次考虑：已减值（Stage3）＞SICR且不适用低风险豁免（Stage2）＞其余（Stage1）。</p>
          <p>3. SICR的13项因素任一项为「是」即表明信用风险显著增加，但仍需单独评估低风险豁免。</p>
          <p>4. 低风险豁免仅在三项条件全部为「是」时成立；不得仅凭投资级评级、担保物价值或历史未违约单独认定。</p>
          <p>5. 已发生信用减值的8项可观察信息任一项为「是」，应优先划入Stage3。</p>
          <p>6. 企业阶段与审计阶段不一致时必须填写差异说明；手动覆盖审计阶段后可点击「恢复公式」。</p>
          <p>7. 从G6-2带入项目、账面余额和企业阶段，完成复核后同步至G6-12减值准备测算。</p>
          <p>8. FVOCI减值不冲减公允价值账面金额，减值损益与OCI累计金额按准则要求列报。</p>
        </div>
      </details>
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述执行的审计程序、三阶段划分测试情况与结果、拟调整/未调整事项及其影响。"
        @input="saveAuditNote"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useG6EclStageClassification } from '@/composables/useG6EclStageClassification'
import { useG6EclFormData } from '../../composables/useG6EclFormData'
import { useG6EclAiGenerate } from '../../composables/useG6EclAiGenerate'
import { applyStageUpdatesToRows } from '../../composables/useG6EclImpairmentCalc'
import {
  fetchG62DetailRows,
  parseG6ChecklistRows,
  parseG6ChecklistPayload,
  G6_11_ROWS_KEY,
  G6_12_DATA_KEY,
  G6_STAGE_UPDATED_EVENT,
} from '../../composables/g6CrossHelpers'
import GtIndexChip from '../../GtIndexChip.vue'
import G6EclImportExportDropdown from '../G6EclImportExportDropdown.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ imported: []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const wpIdRef = computed(() => props.wpId)
const stageLogic = useG6EclStageClassification({
  htmlData: computed(() => props.htmlData),
  isReadonly: computed(() => props.isReadonly),
})
const formData = useG6EclFormData({
  wpId: wpIdRef,
  projectId: computed(() => props.projectId),
})
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG6EclAiGenerate(wpIdRef)

const ROWS_KEY = G6_11_ROWS_KEY
const CONCLUSION_KEY = 'G6-11-stage-classification-conclusion'
const NOTE_KEY = 'G6-11-stage-classification-audit-note'
const auditNote = ref('')
let persistTimer: ReturnType<typeof setTimeout> | null = null

function fmtAmt(value: number): string {
  return (Number(value) || 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function persistRows(): void {
  if (props.isReadonly) return
  const json = JSON.stringify(stageLogic.rows.value)
  formData.debouncedSave(ROWS_KEY, { remark: json, conclusion: json })
}

function schedulePersistRows(): void {
  if (props.isReadonly) return
  if (persistTimer) clearTimeout(persistTimer)
  persistTimer = setTimeout(persistRows, 800)
}

/** 切 Tab / 卸载前：取消本地延时并立刻入队 + flush */
function flushPersist(): void {
  if (persistTimer) {
    clearTimeout(persistTimer)
    persistTimer = null
  }
  persistRows()
  formData.flushPending()
}

function saveAuditNote(value: string): void {
  if (props.isReadonly) return
  auditNote.value = value
  formData.debouncedSave(NOTE_KEY, { remark: value })
}

watch(() => stageLogic.rows.value, schedulePersistRows, { deep: true })
watch(() => stageLogic.conclusion.value, (value) => {
  if (!props.isReadonly) formData.debouncedSave(CONCLUSION_KEY, { remark: value })
})

onMounted(async () => {
  await formData.loadAll()
  const savedRows = parseG6ChecklistRows(formData.allResponses.value.get(ROWS_KEY))
  if (savedRows.length) {
    stageLogic.loadRows(savedRows as any)
  } else {
    stageLogic.init(props.htmlData)
  }
  const note = formData.allResponses.value.get(NOTE_KEY)
  if (note?.remark) auditNote.value = note.remark
  const conclusion = formData.allResponses.value.get(CONCLUSION_KEY)
  if (conclusion?.remark) stageLogic.conclusion.value = conclusion.remark
})

onBeforeUnmount(() => {
  flushPersist()
})

watch(() => props.htmlData, (value) => {
  if (!value) return
  const savedRows = parseG6ChecklistRows(formData.allResponses.value.get(ROWS_KEY))
  if (savedRows.length) return
  if (stageLogic.rows.value.length === 0) stageLogic.init(value)
})

async function importFromG62(): Promise<void> {
  if (props.isReadonly) return
  const list = await fetchG62DetailRows(props.projectId, props.wpId)
  if (!list.length) {
    ElMessage.warning('未找到 G6-2 明细数据，请先在主底稿填写明细表')
    return
  }
  const result = stageLogic.importFromDetailRows(list)
  persistRows()
  ElMessage.success(
    `已带入：新增 ${result.added} 项，刷新 ${result.refreshed} 项`
      + (result.prefilledOverdue ? `；预填逾期SICR ${result.prefilledOverdue} 项` : '')
      + (result.prefilledDefault ? `；预填逾期≥90日违约 ${result.prefilledDefault} 项` : ''),
  )
}

async function onImported(): Promise<void> {
  try {
    await formData.loadAll()
    const savedRows = parseG6ChecklistRows(formData.allResponses.value.get(ROWS_KEY))
    if (savedRows.length) stageLogic.loadRows(savedRows as any)
  } catch { /* ignore */ }
  emit('imported')
}

async function syncStagesToG612(): Promise<void> {
  if (props.isReadonly) return
  const incomplete = stageLogic.incompleteRows.value
  if (incomplete.length) {
    ElMessage.warning(`${incomplete.length} 项检查未完成，请先填完检查项再同步（避免未复核项目写入 G6-12）`)
    return
  }
  const missingNote = stageLogic.inconsistentRows.value.filter(row => !row.discrepancyNote?.trim())
  if (missingNote.length) {
    ElMessage.warning(`${missingNote.length} 项阶段不一致但未填差异说明，请先补全`)
    return
  }
  const updates = stageLogic.rows.value
    .filter(row => row.investProject?.trim())
    .map(row => ({
      investProject: row.investProject.trim(),
      auditStage: row.auditStage,
      bookBalance: row.bookBalance,
      crossSheetInvestmentId: row.crossSheetInvestmentId || row.id,
    }))
  if (!updates.length) {
    ElMessage.warning('无可同步的投资项目')
    return
  }
  try {
    await formData.loadAll()
    const payload = parseG6ChecklistPayload(formData.allResponses.value.get(G6_12_DATA_KEY))
    const existing = Array.isArray(payload) ? payload : (Array.isArray(payload?.rows) ? payload.rows : [])
    const priorConclusion = typeof payload?.conclusion === 'string' ? payload.conclusion : ''
    const applied = applyStageUpdatesToRows(existing, updates)
    await formData.saveImmediate(G6_12_DATA_KEY, {
      conclusion: JSON.stringify({ rows: applied.rows, conclusion: priorConclusion }),
    })
    const json = JSON.stringify(applied.rows)
    await formData.saveImmediate('G6-12-rows', { remark: json, conclusion: json })
    persistRows()
    window.dispatchEvent(new CustomEvent(G6_STAGE_UPDATED_EVENT, {
      detail: { updates, source: 'G6-11', written: true },
    }))
    ElMessage.success(`已同步 ${applied.count} 条阶段至 G6-12`)
  } catch {
    ElMessage.error('阶段同步写入失败')
  }
}

function handleExpandChange(_row: any, expandedRows: any[]): void {
  stageLogic.expandedRowIds.value = new Set(expandedRows.map(row => row.id))
}

function getRowClassName({ row }: { row: any }): string {
  const classes: string[] = []
  if (!row.isConsistent) classes.push('row-inconsistent')
  if (stageLogic.hasIncompleteChecks(row)) classes.push('row-incomplete')
  return classes.join(' ')
}

async function handleAddProject(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入投资项目名称', '新增投资项目', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '项目名称不能为空',
      inputPlaceholder: '例如：XX公司债券',
    })
    if (value?.trim()) {
      await stageLogic.addRow(value.trim())
      ElMessage.success(`已新增投资项目“${value.trim()}”`)
    }
  } catch {
    // 用户取消
  }
}

async function handleRemoveRow(rowId: string, projectName: string): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除投资项目“${projectName}”及其所有检查数据？`, '删除确认', {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    stageLogic.removeRow(rowId)
    ElMessage.success(`已删除“${projectName}”`)
  } catch {
    // 用户取消
  }
}

function openReview(): void {
  openReviewDialog('G6-11-stage-classification')
}

async function fillAiConclusion(): Promise<void> {
  if (props.isReadonly) return
  const rows = stageLogic.rows.value
  const summary = stageLogic.summary.value
  const stageBalance = rows.reduce((result, row) => {
    result[row.auditStage] += Number(row.bookBalance) || 0
    return result
  }, { Stage1: 0, Stage2: 0, Stage3: 0 })
  const text = await generateAndConfirm(
    'stage-conclusion',
    stageLogic.conclusion.value || '',
    {
      total: summary.total,
      stage1Count: summary.stage1Count,
      stage2Count: summary.stage2Count,
      stage3Count: summary.stage3Count,
      inconsistentCount: summary.inconsistentCount,
      incompleteCount: stageLogic.incompleteRows.value.length,
      inconsistentProjects: stageLogic.inconsistentRows.value.map(row => ({
        name: row.investProject,
        company: row.companyStage,
        audit: row.auditStage,
        note: row.discrepancyNote,
      })),
      sicrAndLowRiskConflicts: rows
        .filter(row => row.hasSignificantIncrease && row.hasLowCreditRisk)
        .map(row => ({
          name: row.investProject,
          company: row.companyStage,
          audit: row.auditStage,
        })),
      manualOverrides: rows.filter(row => row.auditStageManualOverride).length,
      stageBalance,
    },
    'AI 审计结论',
  )
  if (text) stageLogic.conclusion.value = text
}
</script>

<style scoped>
.g6-tab-stage-classification {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.objective-alert { margin-bottom: 12px; }

.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: var(--gt-color-warning-light, #fffbeb);
  border-left: 4px solid var(--gt-color-warning, #f59e0b);
  border-radius: 4px;
  font-size: var(--gt-font-size-sm, 12px);
  line-height: 1.8;
}
.methodology-context p { margin: 0 0 4px; }
.methodology-context ul { margin: 0; padding-left: 18px; }
.methodology-context li { margin-bottom: 2px; }
.methodology-context .method-sub {
  margin: 6px 0 0;
  color: var(--gt-color-warning-dark, #92400e);
}

.tab-toolbar,
.section-head,
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.tab-toolbar { margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.toolbar-left, .toolbar-right, .head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.chip-wrap { display: inline-flex; align-items: center; }
.section-head { margin-bottom: 12px; gap: 12px; }
.sheet-title {
  margin: 0;
  font-size: var(--gt-font-size-lg, 15px);
  font-weight: 600;
  flex-shrink: 0;
}

.stage-main-table { width: 100%; font-size: var(--wp-font-size, 13px); }
:deep(.row-inconsistent) { background-color: var(--gt-color-danger-light, #fef0f0) !important; }
:deep(.row-inconsistent:hover > td) { background-color: var(--gt-color-danger-lighter, #fde8e8) !important; }
:deep(.row-incomplete:not(.row-inconsistent)) { background-color: var(--gt-color-warning-light, #fffbeb) !important; }
:deep(.row-incomplete:not(.row-inconsistent):hover > td) { background-color: var(--gt-color-warning-lighter, #fef3c7) !important; }

.project-name-cell { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.delete-btn { opacity: 0; transition: opacity 0.2s; }
.project-name-cell:hover .delete-btn { opacity: 1; }
.audit-stage-cell { display: flex; flex-direction: column; gap: 4px; align-items: center; }
.override-tools { display: flex; align-items: center; justify-content: center; gap: 2px; }
.badge-consistent {
  color: var(--gt-color-success, #67c23a);
  font-weight: 600;
  font-size: var(--gt-font-size-sm, 12px);
}
.badge-inconsistent {
  color: var(--gt-color-danger, #f56c6c);
  font-weight: 700;
  font-size: var(--gt-font-size-sm, 12px);
}
.required-field :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px var(--gt-color-danger, #f56c6c) inset;
}

.expand-detail { padding: 12px 24px; background: var(--gt-color-bg-page, #fafafa); }
.check-section { margin-bottom: 16px; }
.check-section:last-child { margin-bottom: 0; }
.check-section-title {
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 3px solid var(--gt-color-primary, #409eff);
  color: var(--gt-color-text-primary, #303133);
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}
.check-detail-table { width: 100%; font-size: var(--gt-font-size-sm, 12px); }
.hint-text {
  color: var(--gt-color-text-secondary, #606266);
  font-size: var(--gt-font-size-xs, 11px);
  line-height: 1.5;
}
.section-conclusion { display: flex; gap: 8px; align-items: flex-start; margin-top: 8px; }
.section-conclusion .sc-label {
  width: 64px;
  flex-shrink: 0;
  padding-top: 6px;
  color: var(--gt-color-text-secondary, #606266);
  font-size: var(--gt-font-size-sm, 12px);
  font-weight: 600;
}
.section-conclusion .sc-text {
  color: var(--gt-color-text-primary, #303133);
  font-size: var(--gt-font-size-sm, 12px);
  white-space: pre-wrap;
}

.bottom-section { margin-top: 16px; }
.summary-stats {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  margin-bottom: 12px;
  background: var(--gt-color-bg-fill, #f5f7fa);
  border-radius: 4px;
}
.summary-label { color: var(--gt-color-text-secondary, #606266); font-weight: 700; }
.summary-total {
  margin-left: 8px;
  color: var(--gt-color-text-primary, #303133);
  font-weight: 600;
}
.conclusion-card, .audit-note-card { margin-top: 16px; }
.card-header { font-weight: 600; }

.guide-details { margin-top: 16px; }
.guide-details summary {
  cursor: pointer;
  color: var(--gt-color-text-secondary, #606266);
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}
.guide-content {
  padding: 8px 12px;
  margin-top: 6px;
  background: var(--gt-color-warning-light, #fffbeb);
  border-left: 3px solid var(--gt-color-warning, #f59e0b);
  font-size: var(--gt-font-size-sm, 12px);
  line-height: 1.8;
}
.guide-content p { margin: 0; }
</style>
