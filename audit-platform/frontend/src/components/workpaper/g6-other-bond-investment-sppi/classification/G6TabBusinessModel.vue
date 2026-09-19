<template>
  <div class="g6-tab-business-model">
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：评价管理层对其他债权投资业务模式的判断（既以收取合同现金流量又以出售为目标），支持其 FVOCI 分类结论的恰当性。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <span class="chip-wrap">
        <GtIndexChip value="wp:G6-7" :context-project-id="projectId" />
      </span>
      <el-tag size="small" type="info">共 {{ itemCount }} 项检查</el-tag>
      <el-tag v-if="bm.unansweredCount.value" size="small" type="warning">
        {{ bm.unansweredCount.value }} 项未回答
      </el-tag>
      <el-button
        size="small"
        :disabled="isReadonly"
        :loading="salePrefillLoading"
        @click="prefillSaleActivity"
      >
        从 G6-2 预填出售说明
      </el-button>
      <el-button size="small" @click="exportJson">JSON 导出</el-button>
      <el-button size="small" :disabled="isReadonly" @click="openImport">JSON 导入</el-button>
      <input
        ref="importInput"
        type="file"
        accept=".json"
        hidden
        @change="importJson"
      >
    </div>

    <div class="methodology-context">
      <p><strong>CAS22 业务模式三类定义：</strong></p>
      <p>① <strong>持有以收取合同现金流量</strong>：管理金融资产的目标是收取合同现金流量，而非持有并出售</p>
      <p>② <strong>既以收取合同现金流量又以出售为目标</strong>：通过收取合同现金流量和出售金融资产两者实现目标</p>
      <p>③ <strong>其他</strong>：不符合上述两类的业务模式（如以交易为目的持有）</p>
      <p class="methodology-basis">
        依据 CAS22《金融工具确认和计量》第十六条至第十九条，企业应在金融资产组合层次确定其业务模式，而非逐个金融资产确定。
      </p>
    </div>

    <el-card
      v-for="section in sectionDefs"
      :key="section.key"
      shadow="never"
      class="section-card"
    >
      <template #header>
        <div class="section-header">
          <span class="section-title">{{ section.title }}</span>
          <div class="section-actions">
            <el-tag size="small" type="info">完成度：{{ section.completion }}%</el-tag>
            <el-button
              size="small"
              :disabled="isReadonly"
              @click="addItem(section.key)"
            >
              新增检查项
            </el-button>
            <el-button
              size="small"
              :disabled="isReadonly || aiLoading"
              :loading="aiLoading"
              @click="handleAi(section.key)"
            >
              ✨ AI辅助
            </el-button>
            <el-button size="small" @click="openReview(section.reviewId)">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="section.items" border size="small" class="bm-table">
        <el-table-column label="序号" width="50" align="center">
          <template #default="{ row }">{{ row.seq }}</template>
        </el-table-column>

        <el-table-column label="检查项目" min-width="190">
          <template #default="{ row }">
            <div class="check-item-cell">
              <el-input
                v-if="!isReadonly"
                v-model="row.checkItem"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 4 }"
                @input="triggerSave"
              />
              <span v-else class="cell-text">{{ row.checkItem || '-' }}</span>
              <div class="critical-row">
                <el-tag v-if="row.critical" size="small" type="danger">关键</el-tag>
                <el-checkbox
                  v-if="!isReadonly"
                  :model-value="Boolean(row.critical)"
                  size="small"
                  @change="(value: boolean) => changeCritical(section.key, row.id, value)"
                >
                  关键项
                </el-checkbox>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="审计要求" min-width="190">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.auditRequirement"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              @input="triggerSave"
            />
            <span v-else class="cell-text">{{ row.auditRequirement || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="管理层说明" min-width="210">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.managementExplanation"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              placeholder="管理层对该事项的说明..."
              @update:model-value="(value: string) => updateText(section.key, row.id, 'managementExplanation', value)"
            />
            <span v-else class="cell-text">{{ row.managementExplanation || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="是否满足" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.isSatisfied"
              size="small"
              placeholder="选择"
              clearable
              @update:model-value="(value: boolean | null) => updateSatisfied(section.key, row.id, value)"
            >
              <el-option :value="true" label="是" />
              <el-option :value="false" label="否" />
            </el-select>
            <el-tag v-else-if="row.isSatisfied === true" type="success" size="small">是</el-tag>
            <el-tag v-else-if="row.isSatisfied === false" type="danger" size="small">否</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column label="审计结论" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.auditConclusion"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              placeholder="审计结论..."
              @update:model-value="(value: string) => updateText(section.key, row.id, 'auditConclusion', value)"
            />
            <span v-else class="cell-text">{{ row.auditConclusion || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="风险" width="90" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.riskLevel"
              size="small"
              placeholder="风险"
              clearable
              @update:model-value="(value: RiskLevel) => updateRisk(section.key, row.id, value)"
            >
              <el-option value="high" label="高" />
              <el-option value="medium" label="中" />
              <el-option value="low" label="低" />
            </el-select>
            <el-tag v-else-if="row.riskLevel === 'high'" type="danger" size="small">高</el-tag>
            <el-tag v-else-if="row.riskLevel === 'medium'" type="warning" size="small">中</el-tag>
            <el-tag v-else-if="row.riskLevel === 'low'" type="success" size="small">低</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column label="索引" min-width="135">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.indexRef"
              size="small"
              placeholder="索引"
              @update:model-value="(value: string) => updateText(section.key, row.id, 'indexRef', value)"
            />
            <span v-else-if="!row.indexRef">-</span>
            <div v-if="row.indexRef" class="row-index-chip">
              <GtIndexChip :value="row.indexRef" :context-project-id="projectId" />
            </div>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="操作" width="72" fixed="right" align="center">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeItem(section.key, row.id)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="section-conclusion">
        <label class="conclusion-label">分区小结</label>
        <el-input
          v-if="!isReadonly"
          :model-value="section.conclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 8 }"
          placeholder="填写本分区审计小结..."
          @update:model-value="(value: string) => updateSectionConclusion(section.key, value)"
        />
        <div v-else class="readonly-analysis">{{ section.conclusion || '（未填写）' }}</div>
      </div>
    </el-card>

    <el-card shadow="never" class="section-card conclusion-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">(三) 综合判断</span>
          <div class="section-actions">
            <el-tag
              v-if="bm.finalConclusion.value"
              :type="bm.conclusionLabel.value.type"
              size="small"
            >
              {{ bm.conclusionLabel.value.label }}
            </el-tag>
            <el-button
              size="small"
              :disabled="isReadonly || aiLoading"
              :loading="aiLoading"
              @click="handleAi('conclusion')"
            >
              ✨ AI辅助
            </el-button>
            <el-button size="small" @click="openReview('G6-7-business-model-conclusion')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>

      <div class="conclusion-grid">
        <el-alert
          v-if="!bm.isComplete.value"
          type="warning"
          :closable="false"
          :title="`尚有 ${bm.unansweredCount.value} 项未回答`"
          show-icon
        />

        <div class="conclusion-item">
          <label class="conclusion-label">最终结论</label>
          <el-select
            v-if="!isReadonly"
            :model-value="bm.finalConclusion.value"
            placeholder="请选择最终业务模式分类"
            clearable
            class="conclusion-select"
            @update:model-value="changeFinalConclusion"
          >
            <el-option value="hold_collect" label="持有以收取合同现金流量" />
            <el-option value="hold_and_sell" label="既以收取合同现金流量又以出售为目标" />
            <el-option value="other" label="其他（以交易为目的等）" />
          </el-select>
          <el-tag
            v-else-if="bm.finalConclusion.value"
            :type="bm.conclusionLabel.value.type"
          >
            {{ bm.conclusionLabel.value.label }}
          </el-tag>
          <span v-else class="no-data">未确定</span>
          <span v-if="!bm.isComplete.value" class="incomplete-hint">
            检查项尚未全部回答，仍可手工选择结论；完成后请复核自动推导结果。
          </span>
        </div>

        <div class="derived-hint">
          <span>
            自动推导：
            {{ bm.derivedConclusion.value ? conclusionText(bm.derivedConclusion.value) : '待检查项全部回答后生成' }}
          </span>
          <span v-if="bm.manualOverride.value" class="override-sep">｜已手工覆盖</span>
          <el-button
            v-if="bm.manualOverride.value && !isReadonly"
            link
            type="primary"
            size="small"
            @click="clearOverride"
          >
            恢复自动
          </el-button>
        </div>

        <el-alert
          v-if="bm.overrideDiffersFromDerived.value"
          type="warning"
          :closable="false"
          show-icon
          :title="`结论已偏离自动推导：自动推导「${conclusionText(bm.derivedConclusion.value)}」；手工选择「${conclusionText(bm.finalConclusion.value)}」`"
        />

        <div v-if="crossCheck.level" class="cross-check-alert">
          <el-alert
            :title="crossCheckTitle"
            :type="crossCheckAlertType"
            :closable="false"
            show-icon
          >
            <template #default>{{ crossCheck.message }}</template>
          </el-alert>
        </div>

        <div v-if="bm.highRiskCount.value" class="risk-alert">
          <el-alert
            type="warning"
            :closable="false"
            show-icon
            :title="`存在 ${bm.highRiskCount.value} 个高风险检查项，请重点关注`"
          />
        </div>

        <div class="conclusion-item full-width">
          <label class="conclusion-label">综合分析说明</label>
          <el-input
            v-if="!isReadonly"
            :model-value="bm.finalAnalysis.value"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 12 }"
            placeholder="结合业务模式确定和出售情况分析，说明最终分类判断的理由..."
            @update:model-value="updateFinalAnalysis"
          />
          <div v-else class="readonly-analysis">{{ bm.finalAnalysis.value || '（未填写）' }}</div>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="section-card audit-note-card">
      <template #header>
        <div class="section-header"><span class="section-title">审计说明</span></div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述业务模式确定与出售情况分析的测试情况及结果、对分类判断的支持性、拟调整与未调整事项及其影响。"
        @update:model-value="saveAuditNote"
      />
    </el-card>

    <details class="guide-details">
      <summary>📋 编制提示</summary>
      <div class="guide-content">
        <p>1. <b>编制目的</b>：在组合层次评价业务模式（既收合同现金流又以出售为目标），支持 FVOCI-Debt 分类。</p>
        <p>2. <b>建议顺序</b>：先维护 G6-2 明细 → 本表评估业务模式 → 再完成 G6-8 SPPI；两者共同决定 AC / FVOCI-Debt / FVTPL。</p>
        <p>3. 可用「从 G6-2 预填出售说明」带入出售相关线索，再补充管理层实际行动证据（出售频率/金额、业绩评价、薪酬与风控策略）。</p>
        <p>4. 评估基于实际行动而非仅声明意图；临近到期、信用恶化或偶发出售通常不单独构成业务模式变更。</p>
        <p>5. 选定最终结论后，关注与 G6-8 的交叉提示（预期分类）；不一致须在审计说明中解释。</p>
        <p>6. 分类摘要会提示至 G6-1 / 目录；后续利息（G6-6）、公允价值（G6-5）、ECL（G6-11~14）均以本结论为前提。</p>
        <p>7. 证据索引应指向业务模式政策、投资委员会纪要、出售台账等；结论变更时同步复核 G6-8 与附注披露表述。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  BM_CONCLUSION_LABELS,
  buildBusinessModelAiSummary,
  buildG6ClassificationSummary,
  evaluateG67G68Consistency,
  useG6SppiBusinessModel,
  type BusinessModelData,
  type SppiOverallConclusion,
} from '../../composables/useG6SppiBusinessModel'
import { useG6SppiFormData } from '../../composables/useG6SppiFormData'
import { useG6SppiAiGenerate } from '../../composables/useG6SppiAiGenerate'
import {
  fetchG62DetailRows,
  parseG6ChecklistPayload,
  summarizeG62SaleActivity,
  writeG6ClassificationSummary,
} from '../../composables/g6CrossHelpers'
import GtIndexChip from '../../GtIndexChip.vue'

type SectionKey = 'section1' | 'section2'
type RiskLevel = 'high' | 'medium' | 'low' | null
type BusinessModelConclusion = BusinessModelData['finalConclusion']

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ save: [] }>()

const DATA_KEY = 'G6-7-business-model-data'
const NOTE_KEY = 'G6-7-business-model-audit-note'
const SPPI_KEY = 'G6-8-sppi-test-data'

const bm = useG6SppiBusinessModel()
const formData = useG6SppiFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const { generateAndConfirm, loading: aiLoading } = useG6SppiAiGenerate(
  computed(() => props.wpId),
)

const auditNote = ref('')
const importInput = ref<HTMLInputElement | null>(null)
const salePrefillLoading = ref(false)
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const itemCount = computed(
  () => bm.section1.value.items.length + bm.section2.value.items.length,
)

const sectionDefs = computed(() => [
  {
    key: 'section1' as const,
    title: '(一) 业务模式确定',
    reviewId: 'G6-7-business-model-s1',
    items: bm.section1.value.items,
    completion: bm.section1CompletionRate.value,
    conclusion: bm.section1.value.sectionConclusion,
  },
  {
    key: 'section2' as const,
    title: '(二) 出售情况分析',
    reviewId: 'G6-7-business-model-s2',
    items: bm.section2.value.items,
    completion: bm.section2CompletionRate.value,
    conclusion: bm.section2.value.sectionConclusion,
  },
])

const sppiOverall = computed<SppiOverallConclusion>(() => {
  const payload = parseG6ChecklistPayload(formData.allResponses.value.get(SPPI_KEY))
  return payload?.overallConclusion === 'pass' || payload?.overallConclusion === 'fail'
    ? payload.overallConclusion
    : null
})

const crossCheck = computed(() =>
  evaluateG67G68Consistency(bm.finalConclusion.value, sppiOverall.value),
)
const crossCheckTitle = computed(() =>
  crossCheck.value.expectedClassification
    ? `与 G6-8 SPPI 交叉提示 · 预期分类：${crossCheck.value.expectedClassification}`
    : '与 G6-8 SPPI 交叉提示',
)
const crossCheckAlertType = computed<'success' | 'warning' | 'info'>(() => {
  if (crossCheck.value.level === 'ok') return 'success'
  if (crossCheck.value.level === 'warning') return 'warning'
  return 'info'
})

onMounted(async () => {
  await formData.loadAll()
  loadSavedData()
  const note = formData.allResponses.value.get(NOTE_KEY)
  auditNote.value = note?.remark || ''
})

onBeforeUnmount(() => {
  if (props.isReadonly) return
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  formData.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(bm.toJSON()) })
  formData.flushPending()
})

watch(
  () => props.htmlData,
  () => loadSavedData(),
)

function loadSavedData(): void {
  const primary = parseG6ChecklistPayload(formData.allResponses.value.get(DATA_KEY))
  if (primary?.section1?.items?.length || primary?.section2?.items?.length) {
    bm.loadData(primary as BusinessModelData)
    return
  }
  const fallback = formData.parseContent().businessModel
  if (fallback?.section1) bm.loadData(fallback as BusinessModelData)
}

let saveTimer: ReturnType<typeof setTimeout> | null = null

function triggerSave(): void {
  if (props.isReadonly) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    formData.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(bm.toJSON()) })
    void syncClassificationWriteback()
    emit('save')
  }, 800)
}

async function syncClassificationWriteback(): Promise<void> {
  const payload = parseG6ChecklistPayload(formData.allResponses.value.get(SPPI_KEY))
  const overall: SppiOverallConclusion =
    payload?.overallConclusion === 'pass' || payload?.overallConclusion === 'fail'
      ? payload.overallConclusion
      : null
  const businessModel = bm.finalConclusion.value
  const instrumentRows = Array.isArray(payload?.instruments)
    ? payload.instruments.map((i: any) => ({
        id: String(i?.id || ''),
        name: String(i?.name || '未命名'),
        overallConclusion:
          i?.overallConclusion === 'pass' || i?.overallConclusion === 'fail'
            ? i.overallConclusion
            : null,
      }))
    : undefined
  const summary = buildG6ClassificationSummary({
    businessModel,
    sppiOverall: overall,
    instruments: instrumentRows,
    source: 'G6-7',
  })
  const result = await writeG6ClassificationSummary({
    projectId: props.projectId,
    sppiWpId: props.wpId,
    summary,
  })
  if (!result.mainOk && result.resolveError) {
    ElMessage.warning(`分类摘要已存 SPPI；Main 未写入：${result.resolveError}`)
  }
}

function openReview(sectionId: string): void {
  openReviewDialog(sectionId)
}

function addItem(section: SectionKey): void {
  bm.addItem(section)
  triggerSave()
}

function removeItem(section: SectionKey, itemId: string): void {
  if (!bm.removeItem(section, itemId)) {
    ElMessage.warning('每个分区至少保留一项检查项')
    return
  }
  triggerSave()
}

function changeCritical(section: SectionKey, itemId: string, value: boolean): void {
  bm.toggleCritical(section, itemId, value)
  triggerSave()
}

function updateText(
  section: SectionKey,
  itemId: string,
  field: 'managementExplanation' | 'auditConclusion' | 'indexRef',
  value: string,
): void {
  if (field === 'managementExplanation') bm.updateManagementExplanation(section, itemId, value)
  if (field === 'auditConclusion') bm.updateAuditConclusion(section, itemId, value)
  if (field === 'indexRef') bm.updateIndexRef(section, itemId, value)
  triggerSave()
}

function updateSatisfied(section: SectionKey, itemId: string, value: boolean | null): void {
  bm.updateIsSatisfied(section, itemId, value)
  triggerSave()
}

function updateRisk(section: SectionKey, itemId: string, value: RiskLevel): void {
  bm.updateRiskLevel(section, itemId, value)
  triggerSave()
}

function updateSectionConclusion(section: SectionKey, value: string): void {
  bm.updateSectionConclusion(section, value)
  triggerSave()
}

function changeFinalConclusion(value: BusinessModelConclusion): void {
  bm.setFinalConclusion(value)
  triggerSave()
}

function clearOverride(): void {
  bm.clearManualOverride()
  triggerSave()
}

function updateFinalAnalysis(value: string): void {
  bm.setFinalAnalysis(value)
  triggerSave()
}

function saveAuditNote(value: string): void {
  if (props.isReadonly) return
  auditNote.value = value
  formData.debouncedSave(NOTE_KEY, { remark: value })
}

async function handleAi(section: SectionKey | 'conclusion'): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'business-model-conclusion',
    bm.finalAnalysis.value,
    {
      section,
      businessModel: buildBusinessModelAiSummary(bm.toJSON()),
    },
    'AI 业务模式综合判断',
  )
  if (text) {
    bm.setFinalAnalysis(text)
    triggerSave()
  }
}

async function prefillSaleActivity(): Promise<void> {
  if (props.isReadonly || salePrefillLoading.value) return
  salePrefillLoading.value = true
  try {
    const rows = await fetchG62DetailRows(props.projectId, props.wpId)
    const summary = summarizeG62SaleActivity(rows)
    const applied = bm.applySaleDraft(summary.draftText)
    if (applied) triggerSave()
    ElMessage.success(`读取 G6-2 共 ${rows.length} 条明细，已预填 ${applied} 个检查项`)
  } catch {
    ElMessage.error('从 G6-2 预填出售说明失败')
  } finally {
    salePrefillLoading.value = false
  }
}

function exportJson(): void {
  const blob = new Blob([JSON.stringify(bm.toJSON(), null, 2)], {
    type: 'application/json;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'G6-7-business-model-data.json'
  link.click()
  URL.revokeObjectURL(url)
}

function openImport(): void {
  importInput.value?.click()
}

async function importJson(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const parsed = JSON.parse(await file.text()) as BusinessModelData
    bm.loadData(parsed)
    triggerSave()
    ElMessage.success('业务模式 JSON 导入成功')
  } catch {
    ElMessage.error('JSON 文件格式无效，导入失败')
  } finally {
    input.value = ''
  }
}

function conclusionText(value: BusinessModelConclusion): string {
  return value ? BM_CONCLUSION_LABELS[value] || '未知' : '未确定'
}

defineExpose({ toJSON: () => bm.toJSON() })
</script>

<style scoped>
.g6-tab-business-model {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.objective-alert {
  margin-bottom: 12px;
}

.tab-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.chip-wrap {
  display: inline-flex;
  align-items: center;
}

.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: var(--gt-color-warning-light, #fffbeb);
  border-left: 4px solid var(--gt-color-warning, #f59e0b);
  border-radius: 4px;
  font-size: var(--gt-font-size-sm, 12px);
  line-height: 1.8;
}

.methodology-context p {
  margin: 0 0 2px;
}

.methodology-basis {
  margin-top: 4px !important;
  color: var(--gt-color-warning-dark, #92400e);
  font-size: var(--gt-font-size-xs, 11px);
}

.section-card {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.section-title {
  font-size: var(--gt-font-size-md, 14px);
  font-weight: 600;
}

.section-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.bm-table {
  font-size: var(--wp-font-size, 13px);
}

.bm-table :deep(.el-table__cell) {
  padding: 6px 0;
  vertical-align: top;
}

.cell-text {
  white-space: pre-wrap;
  overflow-wrap: break-word;
  font-size: var(--gt-font-size-sm, 12px);
  line-height: 1.5;
}

.check-item-cell,
.critical-row {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.critical-row {
  flex-direction: row;
  align-items: center;
}

.row-index-chip {
  margin-top: 5px;
}

.section-conclusion {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 12px;
}

.conclusion-section {
  border-top: 2px solid var(--gt-color-warning, #f59e0b);
}

.conclusion-grid {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.conclusion-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}

.conclusion-item.full-width {
  width: 100%;
}

.conclusion-label {
  color: var(--gt-color-text-primary, #303133);
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

.conclusion-select {
  width: 320px;
  max-width: 100%;
}

.incomplete-hint,
.no-data {
  color: var(--gt-color-text-tertiary, #909399);
  font-size: var(--gt-font-size-sm, 12px);
}

.derived-hint {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  padding: 6px 10px;
  color: var(--gt-color-warning-dark, #92400e);
  background: var(--gt-color-warning-light, #fffbeb);
  border-radius: 4px;
  font-size: var(--gt-font-size-sm, 12px);
}

.override-sep {
  color: var(--gt-color-warning, #d97706);
}

.cross-check-alert,
.risk-alert {
  margin-top: 4px;
}

.readonly-analysis {
  min-height: 60px;
  padding: 8px 12px;
  color: var(--gt-color-text-primary, #303133);
  background: var(--gt-color-bg-fill, #f5f7fa);
  border-radius: 4px;
  white-space: pre-wrap;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
}

.audit-note-card {
  margin-top: 16px;
}

.guide-details {
  margin-top: 16px;
}

.guide-details summary {
  color: var(--gt-color-text-secondary, #606266);
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

.guide-content {
  margin-top: 6px;
  padding: 8px 12px;
  background: var(--gt-color-warning-light, #fffbeb);
  border-left: 3px solid var(--gt-color-warning, #f59e0b);
  font-size: var(--gt-font-size-sm, 12px);
  line-height: 1.8;
}

.guide-content p {
  margin: 0;
}
</style>
