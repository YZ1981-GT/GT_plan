<template>
  <div class="g4-tab-stage-classification">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认债权投资信用风险自初始确认以来的变化评估恰当，三阶段（Stage1/2/3）划分合理，作为预期信用损失计提的基础。"
      style="margin-bottom: 12px"
    />
    <!-- 方法论上下文（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p><strong>ECL三阶段划分标准（对齐源底稿 G4-9 / CAS 22）：</strong></p>
      <ul>
        <li><strong>Stage1</strong>：信用风险自初始确认以来未显著增加，或资产负债表日适用较低信用风险豁免 → 12个月ECL</li>
        <li><strong>Stage2</strong>：信用风险显著增加且未适用低风险豁免、尚未发生信用减值 → 整个存续期ECL</li>
        <li><strong>Stage3</strong>：已发生信用减值（9项可观察信息之一）→ 整个存续期ECL，利息按净额确认</li>
      </ul>
      <p class="method-sub">判定优先级：已减值(Stage3) &gt; 显著增加且非低风险豁免(Stage2) &gt; 其余(Stage1)。逾期≥30日通常推定SICR；逾期≥90日通常推定违约（均可反驳）。</p>
      <p class="method-sub">
        外部评级及评级迁徙PD是阶段判断和ECL计量的输入之一，不能替代信用风险显著增加的综合判断；
        资本监管风险权重亦不等于会计PD或三阶段结论。完成本表后，在G4-11按阶段执行前瞻性及期限调整。
      </p>
    </div>

    <!-- 工具栏索引 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <G4EclImportExportDropdown
          :wp-id="wpId"
          sheet="G4-9"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G4-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G4-9" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G4-10" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G4-11" :context-project-id="projectId" /></span>
      </div>
    </div>

    <!-- Section标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G4-9 债权投资三阶段划分</h3>
      <div class="head-actions">
        <el-button size="small" :disabled="isReadonly" @click="handleAddProject">
          + 新增投资项目
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="importFromG42">
          从 G4-2 带入
        </el-button>
        <el-button
          size="small"
          type="primary"
          :disabled="isReadonly || stageLogic.rows.value.length === 0"
          @click="syncStagesToG410"
        >
          同步阶段至 G4-10
        </el-button>
        <el-button size="small" @click="guidanceDrawerVisible = true">中证协指引</el-button>
        <el-button size="small" @click="stageLogic.expandAll()">全部展开</el-button>
        <el-button size="small" @click="stageLogic.collapseAll()">全部折叠</el-button>
        <el-button size="small" @click="openReview">💬复核</el-button>
      </div>
    </div>

    <!-- 无数据占位 -->
    <el-empty
      v-if="stageLogic.rows.value.length === 0"
      description="暂无投资项目，点击「新增投资项目」或「从 G4-2 带入」开始"
    />

    <!-- 主表格：行式汇总视图 -->
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
      <!-- 展开行：逐项检查明细 -->
      <el-table-column type="expand">
        <template #default="scope">
          <div class="expand-detail">
            <!-- (一) 信用风险是否显著增加 -->
            <div class="check-section">
              <div class="check-section-title">(一) 信用风险是否显著增加（14项考虑因素，任一项为「是」即SICR）</div>
              <el-table :data="scope.row.sectionOneChecks" border size="small" class="check-detail-table">
                <el-table-column label="序号" width="50" align="center">
                  <template #default="{ $index }">{{ $index + 1 }}</template>
                </el-table-column>
                <el-table-column label="需要考虑的信息" prop="label" min-width="220" />
                <el-table-column label="说明" min-width="280">
                  <template #default="{ row: item }">
                    <span class="hint-text">{{ item.hint }}</span>
                  </template>
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
                    <span v-else>{{ item.value }}</span>
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
                  placeholder="就本投资对信用风险显著增加的综合判断..."
                  @input="(v: string) => stageLogic.updateSectionConclusion(scope.row.id, 'significantIncrease', v)"
                />
                <span v-else class="sc-text">{{ scope.row.sectionConclusions.significantIncrease || '—' }}</span>
              </div>
            </div>

            <!-- (二) 是否具有较低信用风险 -->
            <div class="check-section">
              <div class="check-section-title">(二) 是否具有较低信用风险（3项同时满足方可豁免）</div>
              <el-table :data="scope.row.sectionTwoChecks" border size="small" class="check-detail-table">
                <el-table-column label="序号" width="50" align="center">
                  <template #default="{ $index }">{{ $index + 1 }}</template>
                </el-table-column>
                <el-table-column label="条件（同时满足）" prop="label" min-width="220" />
                <el-table-column label="说明" min-width="280">
                  <template #default="{ row: item }">
                    <span class="hint-text">{{ item.hint }}</span>
                  </template>
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
                    <span v-else>{{ item.value }}</span>
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
                  placeholder="是否适用较低信用风险简化假定..."
                  @input="(v: string) => stageLogic.updateSectionConclusion(scope.row.id, 'lowCreditRisk', v)"
                />
                <span v-else class="sc-text">{{ scope.row.sectionConclusions.lowCreditRisk || '—' }}</span>
              </div>
            </div>

            <!-- (三) 已发生信用减值的评估 -->
            <div class="check-section">
              <div class="check-section-title">(三) 已发生信用减值的评估（9项可观察信息，任一项为「是」即Stage3）</div>
              <el-table :data="scope.row.sectionThreeChecks" border size="small" class="check-detail-table">
                <el-table-column label="序号" width="50" align="center">
                  <template #default="{ $index }">{{ $index + 1 }}</template>
                </el-table-column>
                <el-table-column label="可观察信息" prop="label" min-width="220" />
                <el-table-column label="说明" min-width="280">
                  <template #default="{ row: item }">
                    <span class="hint-text">{{ item.hint }}</span>
                  </template>
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
                    <span v-else>{{ item.value }}</span>
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
                  placeholder="是否存在客观减值证据；若逾期≥90日是否反驳违约推定..."
                  @input="(v: string) => stageLogic.updateSectionConclusion(scope.row.id, 'creditImpairment', v)"
                />
                <span v-else class="sc-text">{{ scope.row.sectionConclusions.creditImpairment || '—' }}</span>
              </div>
            </div>
          </div>
        </template>
      </el-table-column>

      <!-- 投资项目 -->
      <el-table-column label="投资项目" prop="investProject" min-width="140" fixed="left">
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

      <el-table-column label="账面余额" width="110" align="right">
        <template #default="{ row }">
          {{ fmtAmt(row.bookBalance) }}
        </template>
      </el-table-column>

      <!-- 信用风险显著增加判定(综合) -->
      <el-table-column label="显著增加" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.hasSignificantIncrease ? 'danger' : 'success'" size="small">
            {{ row.hasSignificantIncrease ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 较低信用风险(综合) -->
      <el-table-column label="低风险" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.hasLowCreditRisk ? 'success' : 'info'" size="small">
            {{ row.hasLowCreditRisk ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 已发生减值(综合) -->
      <el-table-column label="已减值" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.hasCreditImpairment ? 'danger' : 'success'" size="small">
            {{ row.hasCreditImpairment ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 企业划分阶段(下拉) -->
      <el-table-column label="企业阶段" width="120" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.companyStage"
            size="small"
            style="width: 100%"
            @change="(v: string) => stageLogic.updateCompanyStage(row.id, v as any)"
          >
            <el-option value="Stage1" label="Stage1" />
            <el-option value="Stage2" label="Stage2" />
            <el-option value="Stage3" label="Stage3" />
          </el-select>
          <span v-else>{{ row.companyStage }}</span>
        </template>
      </el-table-column>

      <!-- 审计阶段(下拉) -->
      <el-table-column label="审计阶段" width="120" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.auditStage"
            size="small"
            style="width: 100%"
            @change="(v: string) => stageLogic.updateAuditStage(row.id, v as any)"
          >
            <el-option value="Stage1" label="Stage1" />
            <el-option value="Stage2" label="Stage2" />
            <el-option value="Stage3" label="Stage3" />
          </el-select>
          <span v-else>{{ row.auditStage }}</span>
        </template>
      </el-table-column>

      <!-- 一致性(公式badge) -->
      <el-table-column label="一致性" width="100" align="center">
        <template #default="{ row }">
          <span v-if="row.isConsistent" class="badge-consistent">✓一致</span>
          <span v-else class="badge-inconsistent">✗不一致</span>
        </template>
      </el-table-column>

      <!-- 差异说明 -->
      <el-table-column label="差异说明" min-width="180">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.discrepancyNote"
            size="small"
            :placeholder="row.isConsistent ? '' : '请填写差异说明（必填）'"
            :class="{ 'required-field': !row.isConsistent && !row.discrepancyNote }"
            @input="(v: string) => stageLogic.updateDiscrepancyNote(row.id, v)"
          />
          <span v-else>{{ row.discrepancyNote || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 索引(GtIndexChip) -->
      <el-table-column label="索引" width="120" align="center">
        <template #default="{ row }">
          <GtIndexChip :value="row.indexRef" :context-project-id="projectId" />
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部：汇总区 + 审计结论 + 编制提示 -->
    <div v-if="stageLogic.rows.value.length > 0" class="bottom-section">
      <!-- 汇总统计 -->
      <div class="summary-stats">
        <span class="summary-label">阶段统计：</span>
        <el-tag type="success" size="small">Stage1: {{ stageLogic.summary.value.stage1Count }}</el-tag>
        <el-tag type="warning" size="small">Stage2: {{ stageLogic.summary.value.stage2Count }}</el-tag>
        <el-tag type="danger" size="small">Stage3: {{ stageLogic.summary.value.stage3Count }}</el-tag>
        <el-tag
          :type="stageLogic.summary.value.inconsistentCount > 0 ? 'danger' : 'info'"
          size="small"
        >
          不一致: {{ stageLogic.summary.value.inconsistentCount }}
        </el-tag>
        <span class="summary-total">合计: {{ stageLogic.summary.value.total }} 项</span>
      </div>

      <div v-if="!isReadonly" class="audit-ai-row">
        <el-button
          size="small"
          :disabled="!aiAvailable"
          :loading="aiLoading"
          @click="fillAiConclusion"
        >
          🤖 AI辅助
        </el-button>
      </div>
      <G4AuditTextCards
        :wp-id="wpId"
        :is-readonly="isReadonly"
        v-model:note="auditNote"
        :conclusion="stageLogic.conclusion.value"
        note-placeholder="填写审计说明：三阶段划分测试的执行情况、企业与审计判断差异、拟调整/未调整事项及其影响等。"
        conclusion-placeholder="对三阶段划分合理性的综合评价..."
        @update:note="saveAuditNote"
        @update:conclusion="(v: string) => { stageLogic.conclusion.value = v }"
      />

      <!-- 编制提示 details 折叠 -->
      <details class="g4-guide-details">
        <summary>📋 编制提示（源底稿逻辑 + 中证协指引要点）</summary>
        <div class="g4-guide-content">
          <p>1. 债务工具不适用简化方法，须按一般法三阶段追踪信用风险变化：Stage1→12个月ECL，Stage2/3→整个存续期ECL。</p>
          <p>2. {{ G4_9_GUIDANCE.priority }}</p>
          <p>3. 先「从 G4-2 带入」同步投资项目/余额/企业阶段；逾期≥30日自动预填 SICR 第14项（可反驳）。</p>
          <p>4. (一) 14项任一项为「是」→SICR；(二) 3项须全部为「是」才可低风险豁免；(三) 9项任一项为「是」→Stage3。</p>
          <p>5. {{ G4_9_GUIDANCE.overdue30 }}</p>
          <p>6. {{ G4_9_GUIDANCE.overdue90 }}</p>
          <p>7. {{ G4_9_GUIDANCE.lowRisk }}</p>
          <p>8. 确认后点「同步阶段至 G4-10」，保证减值测算分组与本表审计阶段一致。</p>
          <p>9. 企业阶段与审计阶段不一致时必须填写差异说明；各区块「分析结论」对应源表分析结论行。</p>
          <p class="guide-sub-title">中证协《证券公司金融工具减值指引》— SICR 实务参考情形：</p>
          <ol class="guide-list">
            <li v-for="(item, idx) in G4_9_GUIDANCE.sicrCsrc" :key="idx">{{ item }}</li>
          </ol>
        </div>
      </details>
    </div>

    <!-- 中证协指引侧栏 -->
    <el-drawer
      v-model="guidanceDrawerVisible"
      title="中证协《证券公司金融工具减值指引》要点"
      size="420px"
      append-to-body
    >
      <p class="drawer-lead">{{ G4_9_GUIDANCE.priority }}</p>
      <p class="drawer-tip">{{ G4_9_GUIDANCE.overdue30 }}</p>
      <p class="drawer-tip">{{ G4_9_GUIDANCE.overdue90 }}</p>
      <p class="drawer-tip">{{ G4_9_GUIDANCE.lowRisk }}</p>
      <h4 class="drawer-sub">SICR 实务参考情形</h4>
      <ol class="drawer-list">
        <li v-for="(item, idx) in G4_9_GUIDANCE.sicrCsrc" :key="idx">{{ item }}</li>
      </ol>
      <el-button type="primary" @click="openRefGuidanceSheet">
        打开完整参考 sheet
      </el-button>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabStageClassification.vue — G4-9 三阶段划分
 *
 * Spec: .kiro/specs/g4-bond-investment-ecl/ Task 5.1
 * Requirements: 2.1~2.13, 11.1, 11.5, 11.6, 11.10
 *
 * 功能：
 * - 列式转置结构：源模板投资项目为列，前端转换为行式交互视图
 * - 三区块检查：(一)SICR 14项 / (二)较低信用风险 3项 / (三)已减值 9项（对齐源模板）
 * - 展开明细含「说明」列 + 各区块分析结论
 * - 判定优先级：Stage3 > Stage2(SICR且非低风险豁免) > Stage1
 * - 底部汇总 + 审计说明/结论 + 中证协指引编制提示
 *
 * 使用 useG4EclStageClassification composable
 */
import { ref, computed, inject, watch, onMounted, onBeforeUnmount } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import {
  useG4EclStageClassification,
  G4_9_GUIDANCE,
} from '../../composables/useG4EclStageClassification'
import { useG4EclFormData } from '../../composables/useG4EclFormData'
import { applyStageUpdatesToRows } from '../../composables/useG4EclImpairmentCalc'
import {
  fetchG42DetailRows,
  parseChecklistRows,
  G4_9_ROWS_KEY,
  G4_10_ROWS_KEY,
  G4_STAGE_UPDATED_EVENT,
} from '../../composables/g4CrossHelpers'
import GtIndexChip from '../../GtIndexChip.vue'
import G4AuditTextCards from '../../g4-bond-investment-main/G4AuditTextCards.vue'
import G4EclImportExportDropdown from '../G4EclImportExportDropdown.vue'
import { useG4EclAiGenerate } from '../../composables/useG4EclAiGenerate'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ imported: []; 'navigate-sheet': [sheetName: string] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const navigateG4Sheet = inject<(code: string) => void>('navigateG4Sheet', (code) => {
  emit('navigate-sheet', code)
})

const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG4EclAiGenerate(wpIdRef)

const isReadonlyRef = computed(() => props.isReadonly)
const htmlDataRef = computed(() => props.htmlData)

const stageLogic = useG4EclStageClassification({
  htmlData: htmlDataRef,
  isReadonly: isReadonlyRef,
})

const formData = useG4EclFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const NOTE_KEY = 'G4-9-stage-classification-audit-note'
const CONCLUSION_KEY = 'G4-9-stage-classification-conclusion'
const auditNote = ref('')
const guidanceDrawerVisible = ref(false)
let persistTimer: ReturnType<typeof setTimeout> | null = null

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  formData.debouncedSave(NOTE_KEY, { remark: val })
}

function persistRows(): void {
  if (props.isReadonly) return
  const json = JSON.stringify(stageLogic.rows.value)
  formData.debouncedSave(G4_9_ROWS_KEY, { remark: json, conclusion: json })
}

function schedulePersistRows(): void {
  if (props.isReadonly) return
  if (persistTimer) clearTimeout(persistTimer)
  persistTimer = setTimeout(() => persistRows(), 800)
}

watch(() => stageLogic.conclusion.value, (val) => {
  if (props.isReadonly) return
  formData.debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: val })
})

watch(() => stageLogic.rows.value, () => schedulePersistRows(), { deep: true })

onMounted(async () => {
  stageLogic.init(props.htmlData)
  await formData.loadAll()
  const savedRows = formData.allResponses.value.get(G4_9_ROWS_KEY)
  const list = parseChecklistRows(savedRows)
  if (list.length && stageLogic.rows.value.length === 0) {
    stageLogic.loadRows(list as any)
  }
  const note = formData.allResponses.value.get(NOTE_KEY)
  if (note?.remark) auditNote.value = note.remark
  const conc = formData.allResponses.value.get(CONCLUSION_KEY)
  if (conc?.remark) stageLogic.conclusion.value = conc.remark
})

onBeforeUnmount(() => {
  if (persistTimer) clearTimeout(persistTimer)
})

watch(() => props.htmlData, (newData) => {
  if (newData && stageLogic.rows.value.length === 0) {
    stageLogic.init(newData)
  }
})

function fmtAmt(v: number): string {
  const n = Number(v) || 0
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function importFromG42(): Promise<void> {
  if (props.isReadonly) return
  const list = await fetchG42DetailRows(props.wpId)
  if (!list.length) {
    ElMessage.warning('未找到 G4-2 明细数据，请先在主底稿填写明细表')
    return
  }
  const result = stageLogic.importFromDetailRows(list)
  persistRows()
  ElMessage.success(
    `已带入：新增 ${result.added} 项，刷新 ${result.refreshed} 项`
      + (result.prefilledOverdue ? `；预填逾期SICR ${result.prefilledOverdue} 项` : ''),
  )
}

async function syncStagesToG410(): Promise<void> {
  if (props.isReadonly) return
  const missingNote = stageLogic.inconsistentRows.value.filter(r => !r.discrepancyNote?.trim())
  if (missingNote.length) {
    ElMessage.warning(`${missingNote.length} 项阶段不一致但未填差异说明，请先补全`)
    return
  }
  const updates = stageLogic.rows.value
    .filter(r => r.investProject?.trim())
    .map(r => ({
      investProject: r.investProject.trim(),
      auditStage: r.auditStage as 'Stage1' | 'Stage2' | 'Stage3',
      bookBalance: r.bookBalance,
    }))
  if (!updates.length) {
    ElMessage.warning('无可同步的投资项目')
    return
  }
  try {
    try { await formData.loadAll() } catch { /* ignore */ }
    const existing = parseChecklistRows(formData.allResponses.value.get(G4_10_ROWS_KEY))
    const applied = applyStageUpdatesToRows(existing, updates)
    const json = JSON.stringify(applied.rows)
    await formData.saveImmediate(G4_10_ROWS_KEY, { remark: json, conclusion: json })
    persistRows()
    try {
      window.dispatchEvent(new CustomEvent(G4_STAGE_UPDATED_EVENT, {
        detail: { updates, source: 'G4-9', written: true },
      }))
    } catch { /* silent */ }
    ElMessage.success(`已同步 ${applied.count} 条阶段至 G4-10`)
  } catch {
    ElMessage.error('阶段同步写入失败')
  }
}

function openRefGuidanceSheet(): void {
  guidanceDrawerVisible.value = false
  navigateG4Sheet('参考-中证协')
}

// ─── 展开行处理（el-table expand事件） ───
function handleExpandChange(row: any, expandedRows: any[]): void {
  // el-table expand-change 返回当前展开的行数组
  stageLogic.expandedRowIds.value.clear()
  for (const r of expandedRows) {
    stageLogic.expandedRowIds.value.add(r.id)
  }
}

// ─── 行样式：不一致行红色高亮 ───
function getRowClassName({ row }: { row: any }): string {
  if (!row.isConsistent) return 'row-inconsistent'
  return ''
}

// ─── 新增投资项目（ElMessageBox.prompt输入名称） ───
async function handleAddProject(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入投资项目名称',
      '新增投资项目',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '项目名称不能为空',
        inputPlaceholder: '例如：XX公司债券',
      },
    )
    if (value?.trim()) {
      stageLogic.addRow(value.trim())
      ElMessage.success(`已新增投资项目"${value.trim()}"`)
    }
  } catch {
    // 用户取消
  }
}

// ─── 删除投资项目确认 ───
async function handleRemoveRow(rowId: string, projectName: string): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认删除投资项目"${projectName}"及其所有检查数据？`,
      '删除确认',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
    stageLogic.removeRow(rowId)
    ElMessage.success(`已删除"${projectName}"`)
  } catch {
    // 用户取消
  }
}

// ─── 打开复核对话 ───
function openReview(): void {
  openReviewDialog('G4-9-stage-classification')
}

// ─── AI辅助生成审计结论 ───
async function fillAiConclusion(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'stage-classification-conclusion',
    stageLogic.conclusion.value || '',
    {},
    'AI 审计结论',
  )
  if (text) stageLogic.conclusion.value = text
}
</script>

<style scoped>
.g4-tab-stage-classification {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* 工具栏索引 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.tab-toolbar .toolbar-left { display: flex; gap: 8px; align-items: center; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }

.audit-ai-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景）─── */
.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.8;
}

.methodology-context p {
  margin: 0 0 4px;
}

.methodology-context ul {
  margin: 0;
  padding-left: 18px;
}

.methodology-context li {
  margin-bottom: 2px;
}

.methodology-context .method-sub {
  margin: 6px 0 0;
  color: #92400e;
  font-size: 12px;
}

.hint-text {
  color: #606266;
  font-size: 11px;
  line-height: 1.5;
}

.section-conclusion {
  margin-top: 8px;
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.section-conclusion .sc-label {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  color: #606266;
  padding-top: 6px;
  width: 64px;
}

.section-conclusion .sc-text {
  font-size: 12px;
  color: #303133;
  white-space: pre-wrap;
}

.g4-guide-content .guide-sub-title {
  margin-top: 8px;
  font-weight: 600;
  color: #1d4ed8;
}

.g4-guide-content .guide-list {
  margin: 4px 0 0;
  padding-left: 18px;
  color: #1e40af;
}

.g4-guide-content .guide-list li {
  margin-bottom: 2px;
}

.drawer-lead {
  font-weight: 600;
  margin: 0 0 12px;
  line-height: 1.6;
}

.drawer-tip {
  font-size: 12px;
  color: #606266;
  margin: 0 0 8px;
  line-height: 1.6;
}

.drawer-sub {
  margin: 16px 0 8px;
  font-size: 13px;
}

.drawer-list {
  margin: 0 0 16px;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.7;
  color: #1e40af;
}

/* ─── Section标题栏 ─── */
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* ─── 主表格 ─── */
.stage-main-table {
  width: 100%;
  font-size: var(--wp-font-size, 13px);
}

/* 不一致行红色高亮 */
:deep(.row-inconsistent) {
  background-color: #fef0f0 !important;
}

:deep(.row-inconsistent:hover > td) {
  background-color: #fde8e8 !important;
}

/* ─── 投资项目名称单元格 ─── */
.project-name-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.delete-btn {
  opacity: 0;
  transition: opacity 0.2s;
}

.project-name-cell:hover .delete-btn {
  opacity: 1;
}

/* ─── 一致性badge ─── */
.badge-consistent {
  color: #67c23a;
  font-weight: 600;
  font-size: 12px;
}

.badge-inconsistent {
  color: #f56c6c;
  font-weight: 700;
  font-size: 12px;
}

/* ─── 差异说明必填提示 ─── */
.required-field :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}

/* ─── 展开详情区 ─── */
.expand-detail {
  padding: 12px 24px;
  background: #fafafa;
}

.check-section {
  margin-bottom: 16px;
}

.check-section:last-child {
  margin-bottom: 0;
}

.check-section-title {
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
  margin-bottom: 8px;
  padding-left: 4px;
  border-left: 3px solid #409eff;
  padding-left: 8px;
}

.check-detail-table {
  width: 100%;
  font-size: 12px;
}

/* ─── 底部区域 ─── */
.bottom-section {
  margin-top: 16px;
}

/* 汇总统计 */
.summary-stats {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 12px;
}

.summary-label {
  font-weight: 700;
  color: #606266;
}

.summary-total {
  margin-left: 8px;
  font-weight: 600;
  color: #303133;
}

/* 编制提示 */
.g4-guide-details {
  margin-top: 16px;
}

.g4-guide-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  font-weight: 600;
}

.g4-guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}

.g4-guide-content p {
  margin: 0;
}
</style>
