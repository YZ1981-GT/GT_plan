<!--
  G5TabStageClassification.vue — G5-9 长期应收款三阶段划分
  行式：债务人|余额|显著增加|低风险|已减值|企业阶段|建议阶段|审计阶段|一致|判断依据|差异说明|索引
-->
<template>
  <div class="g5-tab-stage-classification">
    <div class="methodology-context">
      <p><strong>ECL 三阶段划分（CAS 22 一般法）</strong></p>
      <ul>
        <li><strong>Stage1</strong>：信用风险自初始确认以来未显著增加（或适用较低信用风险豁免）→ 12 个月 ECL</li>
        <li><strong>Stage2</strong>：信用风险显著增加但未发生信用减值 → 整个存续期 ECL</li>
        <li><strong>Stage3</strong>：已发生信用减值 → 整个存续期 ECL，利息按摊余净额确认</li>
      </ul>
      <p class="method-sub">判定优先级：已减值(Stage3) &gt; 显著增加且非低风险豁免(Stage2) &gt; 其余(Stage1)。展开行可勾选 SICR/低风险/减值矩阵。</p>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">G5-9 长期应收款三阶段划分</h3>
      <div class="head-actions tab-toolbar">
        <GtIndexChip value="wp:G5-9" />
        <GtIndexChip value="wp:G5-2" />
        <GtIndexChip value="wp:G5-10" />
        <GtIndexChip value="wp:G5-4" />
        <el-tag size="small" type="info">共 {{ stageLogic.rows.value.length }} 户</el-tag>
        <el-tag
          v-if="stageLogic.summary.value.inconsistentCount"
          size="small"
          type="danger"
        >不一致 {{ stageLogic.summary.value.inconsistentCount }}</el-tag>
        <GtReviewTrigger section-id="g5-9-stage-classification" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：按债务人执行 ECL 三阶段划分，比对企业划分与审计判断；识别信用风险显著增加及已减值情形，并将审计阶段同步至 G5-10 减值测算。
    </el-alert>

    <div class="toolbar">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddDebtor">+ 新增债务人</el-button>
      <el-button size="small" :disabled="isReadonly" @click="importFromG52">从 G5-2 带入</el-button>
      <el-button
        size="small"
        type="primary"
        :disabled="isReadonly || stageLogic.rows.value.length === 0"
        @click="syncStagesToG510"
      >同步阶段至 G5-10</el-button>
      <el-button
        size="small"
        type="warning"
        plain
        :disabled="isReadonly || stageLogic.inconsistentRows.value.length === 0"
        @click="pushInconsistenciesToG54"
      >不一致推送 G5-4</el-button>
      <el-button size="small" @click="stageLogic.expandAll()">全部展开</el-button>
      <el-button size="small" @click="stageLogic.collapseAll()">全部折叠</el-button>
    </div>

    <el-empty v-if="stageLogic.rows.value.length === 0" description="暂无债务人，点击「新增债务人」或「从 G5-2 带入」" />

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
            <div v-if="triggersOf(scope.row).length" class="trigger-box">
              <strong>阶段触发因素：</strong>
              <ul>
                <li v-for="(t, i) in triggersOf(scope.row)" :key="i">{{ t }}</li>
              </ul>
              <el-button
                v-if="scope.row.auditStageOverridden"
                size="small"
                text
                type="primary"
                :disabled="isReadonly"
                @click="stageLogic.resetAuditStageToSuggested(scope.row.id)"
              >清除审计覆写（恢复建议阶段 {{ scope.row.suggestedStage }}）</el-button>
            </div>

            <div class="check-section">
              <div class="check-section-title">(一) 信用风险是否显著增加（13 项，任一项为「是」即显著增加）</div>
              <el-table :data="scope.row.sectionOneChecks" border size="small" class="check-detail-table">
                <el-table-column label="序号" width="50" align="center">
                  <template #default="{ $index }">{{ $index + 1 }}</template>
                </el-table-column>
                <el-table-column label="考虑因素" prop="label" min-width="300" />
                <el-table-column label="判断" width="140" align="center">
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
            </div>

            <div class="check-section">
              <div class="check-section-title">(二) 是否具有较低信用风险（3 项须同时为「是」方可豁免）</div>
              <el-table :data="scope.row.sectionTwoChecks" border size="small" class="check-detail-table">
                <el-table-column label="序号" width="50" align="center">
                  <template #default="{ $index }">{{ $index + 1 }}</template>
                </el-table-column>
                <el-table-column label="满足条件" prop="label" min-width="300" />
                <el-table-column label="判断" width="140" align="center">
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
            </div>

            <div class="check-section">
              <div class="check-section-title">(三) 已发生信用减值（8 项，任一项为「是」即 Stage3）</div>
              <el-table :data="scope.row.sectionThreeChecks" border size="small" class="check-detail-table">
                <el-table-column label="序号" width="50" align="center">
                  <template #default="{ $index }">{{ $index + 1 }}</template>
                </el-table-column>
                <el-table-column label="可观察信息" prop="label" min-width="300" />
                <el-table-column label="判断" width="140" align="center">
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
            </div>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="债务人" prop="debtor" min-width="130" fixed="left">
        <template #default="{ row }">
          <div class="debtor-name-cell">
            <span>{{ row.debtor }}</span>
            <el-button
              v-if="!isReadonly"
              size="small"
              type="danger"
              link
              class="delete-btn"
              @click.stop="handleRemoveRow(row.id, row.debtor)"
            >删</el-button>
          </div>
          <div v-if="row.businessType" class="sub-meta">{{ bizLabel(row.businessType) }}</div>
        </template>
      </el-table-column>

      <el-table-column label="期末余额" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.closingBalance"
            size="small"
            :controls="false"
            @change="(v: number | undefined) => stageLogic.updateClosingBalance(row.id, Number(v) || 0)"
          />
          <span v-else>{{ fmt(row.closingBalance) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="显著增加" width="88" align="center">
        <template #default="{ row }">
          <el-tag :type="row.hasSignificantIncrease ? 'danger' : 'success'" size="small">
            {{ row.hasSignificantIncrease ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="低风险" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.hasLowCreditRisk ? 'success' : 'info'" size="small">
            {{ row.hasLowCreditRisk ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="已减值" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.hasCreditImpairment ? 'danger' : 'success'" size="small">
            {{ row.hasCreditImpairment ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="企业阶段" width="100" align="center">
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

      <el-table-column label="建议阶段" width="90" align="center">
        <template #default="{ row }">
          <span class="formula-cell" title="由检查矩阵自动判定">{{ row.suggestedStage }}</span>
        </template>
      </el-table-column>

      <el-table-column label="审计阶段" width="110" align="center">
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
          <div v-if="row.auditStageOverridden" class="override-hint">已覆写</div>
        </template>
      </el-table-column>

      <el-table-column label="一致性" width="88" align="center">
        <template #default="{ row }">
          <span v-if="row.isConsistent" class="badge-consistent">✓一致</span>
          <span v-else class="badge-inconsistent">✗不一致</span>
        </template>
      </el-table-column>

      <el-table-column label="判断依据" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.judgmentBasis"
            size="small"
            placeholder="证据/合同要点"
            @input="(v: string) => stageLogic.updateJudgmentBasis(row.id, v)"
          />
          <span v-else>{{ row.judgmentBasis || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="差异说明" min-width="150">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.discrepancyNote"
            size="small"
            :placeholder="row.isConsistent ? '' : '不一致必填'"
            :class="{ 'required-field': !row.isConsistent && !row.discrepancyNote }"
            @input="(v: string) => stageLogic.updateDiscrepancyNote(row.id, v)"
          />
          <span v-else>{{ row.discrepancyNote || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="索引" width="90" align="center">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.indexRef"
            size="small"
            placeholder="索引"
            @input="(v: string) => stageLogic.updateIndexRef(row.id, v)"
          />
          <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" />
          <span v-else>—</span>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="stageLogic.rows.value.length > 0" class="bottom-section">
      <div class="summary-stats">
        <span class="summary-label">阶段户数：</span>
        <el-tag type="success" size="small">S1 {{ stageLogic.summary.value.stage1Count }}</el-tag>
        <el-tag type="warning" size="small">S2 {{ stageLogic.summary.value.stage2Count }}</el-tag>
        <el-tag type="danger" size="small">S3 {{ stageLogic.summary.value.stage3Count }}</el-tag>
        <el-tag :type="stageLogic.summary.value.inconsistentCount > 0 ? 'danger' : 'info'" size="small">
          不一致 {{ stageLogic.summary.value.inconsistentCount }}
        </el-tag>
        <span class="summary-sep">|</span>
        <span class="summary-label">阶段余额：</span>
        <span>S1 {{ fmt(stageLogic.summary.value.stage1Amount) }}</span>
        <span>S2 {{ fmt(stageLogic.summary.value.stage2Amount) }}</span>
        <span>S3 {{ fmt(stageLogic.summary.value.stage3Amount) }}</span>
        <span>合计 {{ fmt(stageLogic.summary.value.totalAmount) }}</span>
        <span
          v-if="stageLogic.summary.value.inconsistentAmount > 0"
          class="badge-inconsistent"
        >不一致余额 {{ fmt(stageLogic.summary.value.inconsistentAmount) }}</span>
      </div>

      <G5AuditTextCards
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :note="auditNote"
        :conclusion="stageLogic.conclusion.value"
        conclusion-ai-section="stage-classification-conclusion"
        note-placeholder="填写审计说明：SICR/已减值关键证据、企业与审计阶段差异原因、与 G5-8 政策及 G5-10 测算勾稽。"
        conclusion-placeholder="A、三阶段划分适当，与企业一致。B、除下述阶段差异应调整减值测算外，其余未见异常。C、由于存在重大未决阶段判断或范围受限，不可确认。"
        conclusion-hint="按 A/B/C 口径评价阶段划分结果。"
        :related-context="{
          Stage1: stageLogic.summary.value.stage1Count,
          Stage2: stageLogic.summary.value.stage2Count,
          Stage3: stageLogic.summary.value.stage3Count,
          不一致: stageLogic.summary.value.inconsistentCount,
          不一致余额: stageLogic.summary.value.inconsistentAmount,
        }"
        @update:note="saveAuditNote"
        @update:conclusion="(v: string) => { stageLogic.conclusion.value = v }"
      />

      <details class="g5-guide-details" open>
        <summary>📋 编制提示</summary>
        <div class="g5-guide-content">
          <ol>
            <li>从 G5-2 带入债务人及余额 → 展开逐户勾选（一）（二）（三）矩阵 → 核对建议阶段与企业阶段。</li>
            <li>（一）13 项任一为「是」→ SICR；（二）3 项全「是」才可低风险豁免；（三）8 项任一「是」→ Stage3。</li>
            <li>建议阶段由公式自动给出；审计阶段默认同建议，可人工覆写（展开区可「清除覆写」）。</li>
            <li>企业≠审计时须填差异说明；可推送备忘至 G5-4（金额待 G5-10 量化后补录）。</li>
            <li>确认后点「同步阶段至 G5-10」，保证减值测算分组与本表审计阶段一致。</li>
            <li>长期应收常见 Stage2 信号：逾期超 30 天、经营恶化、担保物贬值、合同展期让步。</li>
          </ol>
          <p class="cas-basis">CAS 依据：《企业会计准则第 22 号——金融工具确认和计量》预期信用损失三阶段模型。</p>
        </div>
      </details>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, watch, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import {
  useG5StageClassification,
  getStageTriggerLabels,
  type G5StageClassificationRow,
} from '../../composables/useG5StageClassification'
import { useInjectedG5FormData } from '../../composables/useG5LonRecFormData'
import {
  applyStageUpdatesToRows,
  parseG510Payload,
} from '../../composables/useG5ImpairmentCalc'
import { parseRowsRemark } from '../../composables/g5CrossHelpers'
import { G5_ITEM_IDS, readCanonicalRaw } from '../../composables/g5StorageContract'
import { createEmptyEntry } from '../../composables/useG5Adjustment'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import G5AuditTextCards from '../G5AuditTextCards.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const isReadonly = computed(() => props.isReadonly)
const isReadonlyRef = computed(() => props.isReadonly)
const htmlDataRef = computed(() => props.htmlData)

const g5Notes = useInjectedG5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const auditNote = ref('')
const G5_NOTE_KEY = 'G5-9-audit-note'
const G5_CONCLUSION_KEY = 'G5-9-audit-conclusion'
const G5_ROWS_KEY = 'G5-9-rows'
const G5_4_KEY = 'G5-4-rows'
const PUSH_MARK = '来自G5-9三阶段'

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  void g5Notes.saveImmediate(G5_NOTE_KEY, { conclusion: null, remark: val })
}

const stageLogic = useG5StageClassification({
  htmlData: htmlDataRef,
  isReadonly: isReadonlyRef,
})

watch(() => stageLogic.conclusion.value, (val) => {
  if (props.isReadonly) return
  void g5Notes.saveImmediate(G5_CONCLUSION_KEY, { conclusion: null, remark: val ?? '' })
})

let hydrating = false
onMounted(async () => {
  hydrating = true
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const n = g5Notes.allResponses.value.get(G5_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = g5Notes.allResponses.value.get(G5_CONCLUSION_KEY)
  if (c?.remark) stageLogic.conclusion.value = c.remark
  const saved = readCanonicalRaw(g5Notes.allResponses.value.get(G5_ROWS_KEY))
  if (saved) {
    try {
      const parsed = JSON.parse(saved)
      if (Array.isArray(parsed)) stageLogic.loadRows(parsed)
      else if (Array.isArray(parsed?.rows)) stageLogic.loadRows(parsed.rows)
      if (parsed?.conclusion) stageLogic.conclusion.value = parsed.conclusion
    } catch { /* ignore */ }
  } else {
    stageLogic.init(props.htmlData)
  }
  hydrating = false
})

watch(() => props.htmlData, (newData) => {
  if (newData && stageLogic.rows.value.length === 0) {
    stageLogic.init(newData)
  }
})

watch(
  () => stageLogic.rows.value,
  () => {
    if (props.isReadonly || hydrating) return
    const json = JSON.stringify(stageLogic.toSaveData())
    g5Notes.debouncedSave(G5_ROWS_KEY, { remark: json, conclusion: json })
  },
  { deep: true },
)

function handleExpandChange(_row: any, expandedRows: any[]): void {
  stageLogic.expandedRowIds.value.clear()
  for (const r of expandedRows) stageLogic.expandedRowIds.value.add(r.id)
}

function getRowClassName({ row }: { row: G5StageClassificationRow }): string {
  if (!row.isConsistent) return 'row-inconsistent'
  if (row.auditStage === 'Stage3') return 'row-stage3'
  if (row.auditStage === 'Stage2') return 'row-stage2'
  return ''
}

function triggersOf(row: G5StageClassificationRow): string[] {
  return getStageTriggerLabels(row)
}

function bizLabel(bt: string): string {
  const map: Record<string, string> = {
    lease: '融资租赁',
    installment: '分期销售',
    factoring: '保理',
    other: '其他',
  }
  return map[bt] || bt
}

async function handleAddDebtor(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入债务人名称', '新增债务人', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '债务人名称不能为空',
    })
    if (value?.trim()) {
      await stageLogic.addRow(value.trim())
      ElMessage.success(`已新增「${value.trim()}」`)
    }
  } catch { /* cancel */ }
}

async function importFromG52(): Promise<void> {
  if (props.isReadonly) return
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const list = parseRowsRemark(g5Notes.allResponses.value.get(G5_ITEM_IDS.G5_2_ROWS))
  if (!list.length) {
    ElMessage.warning('未找到 G5-2 明细数据')
    return
  }
  const added = stageLogic.importFromBalanceRows(list)
  ElMessage.success(added > 0 ? `已带入 ${added} 户（已有户仅刷新余额）` : '无新增户，已刷新同名余额')
}

async function syncStagesToG510(): Promise<void> {
  if (props.isReadonly) return
  const missingNote = stageLogic.inconsistentRows.value.filter(r => !r.discrepancyNote?.trim())
  if (missingNote.length) {
    ElMessage.warning(`${missingNote.length} 户阶段不一致但未填差异说明，请先补全`)
    return
  }
  const updates = stageLogic.rows.value
    .filter(r => r.debtor?.trim())
    .map(r => ({ debtor: r.debtor.trim(), auditStage: r.auditStage as 'Stage1' | 'Stage2' | 'Stage3' }))
  if (!updates.length) {
    ElMessage.warning('无可同步的债务人')
    return
  }
  try {
    try { await g5Notes.loadAll() } catch { /* ignore */ }
    const raw = readCanonicalRaw(g5Notes.allResponses.value.get(G5_ITEM_IDS.G5_10_ROWS))
    let existing: unknown = []
    if (raw) {
      try { existing = JSON.parse(raw) } catch { existing = [] }
    }
    const applied = applyStageUpdatesToRows(parseG510Payload(existing), updates)
    const json = JSON.stringify(applied.payload)
    await g5Notes.saveImmediate(G5_ITEM_IDS.G5_10_ROWS, { remark: json, conclusion: json })
    try {
      window.dispatchEvent(new CustomEvent('g5:stage-updated', {
        detail: { updates, source: 'G5-9', written: true },
      }))
    } catch { /* silent */ }
    ElMessage.success(`已同步 ${applied.count} 条阶段至 G5-10`)
  } catch {
    ElMessage.error('阶段同步写入失败')
  }
}

async function pushInconsistenciesToG54(): Promise<void> {
  if (props.isReadonly) return
  const drafts = stageLogic.buildInconsistencyAdjDrafts()
  if (!drafts.length) {
    ElMessage.info('无阶段不一致可推送')
    return
  }
  const missing = stageLogic.inconsistentRows.value.filter(r => !r.discrepancyNote?.trim())
  if (missing.length) {
    ElMessage.warning('请先为不一致行填写差异说明')
    return
  }
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const raw = readCanonicalRaw(g5Notes.allResponses.value.get(G5_4_KEY))
  let existing: any[] = []
  try {
    const parsed = raw ? JSON.parse(raw) : []
    existing = Array.isArray(parsed) ? parsed : []
  } catch {
    existing = []
  }
  const kept = existing.filter((e: any) => !String(e.remark || '').includes(PUSH_MARK))
  const added = drafts.map((d, i) => {
    const e = createEmptyEntry(kept.length + i + 1, d.description)
    e.accountCode = d.accountCode
    e.accountName = d.accountName
    e.reportItem = '坏账准备'
    e.debitAmount = d.debitAmount
    e.creditAmount = d.creditAmount
    e.indexRef = d.indexRef
    e.remark = d.remark
    e.category = '其他'
    e.entryType = 'AJE'
    return e
  })
  const next = [...kept, ...added]
  const json = JSON.stringify(next)
  await g5Notes.saveImmediate(G5_4_KEY, { remark: json, conclusion: json })
  try {
    window.dispatchEvent(new CustomEvent('g5:stage-diff-pushed', {
      detail: { count: added.length },
    }))
  } catch { /* silent */ }
  ElMessage.success(`已向 G5-4 推送 ${added.length} 条阶段不一致备忘（金额待 G5-10 补录）`)
}

async function handleRemoveRow(rowId: string, debtorName: string): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除「${debtorName}」及其检查数据？`, '删除确认', {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    stageLogic.removeRow(rowId)
    ElMessage.success(`已删除「${debtorName}」`)
  } catch { /* cancel */ }
}

function onImported(rows: unknown[]) {
  if (Array.isArray(rows)) stageLogic.loadRows(rows as any)
}

function fmt(v: number | null | undefined): string {
  const n = Number(v) || 0
  if (Math.abs(n) < 0.005) return '—'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

defineExpose({
  toJSON: () => stageLogic.toSaveData(),
})
</script>

<style scoped>
.g5-tab-stage-classification { padding: 4px 0; font-size: var(--wp-font-size, 13px); }
.methodology-context {
  margin-bottom: 12px; padding: 10px 14px; background: #fffbeb;
  border-left: 4px solid #f59e0b; border-radius: 4px; font-size: 12px; line-height: 1.75;
}
.methodology-context p { margin: 0 0 4px; }
.methodology-context ul { margin: 0; padding-left: 18px; }
.method-sub { margin-top: 6px !important; color: #865c0a; }
.section-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px; gap: 8px; flex-wrap: wrap;
}
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; color: #1f2a37; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.audit-objective { margin-bottom: 10px; }
.toolbar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.stage-main-table { width: 100%; font-size: var(--wp-font-size, 13px); }
:deep(.row-inconsistent) { background-color: #fef0f0 !important; }
:deep(.row-stage2) { background-color: #fdf6ec !important; }
:deep(.row-stage3) { background-color: #fef0f0 !important; }
.debtor-name-cell { display: flex; align-items: center; justify-content: space-between; gap: 4px; }
.delete-btn { opacity: 0.55; }
.sub-meta { font-size: 11px; color: #909399; }
.override-hint { font-size: 10px; color: #e6a23c; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; font-weight: 600; }
.badge-consistent { color: #67c23a; font-weight: 600; font-size: 12px; }
.badge-inconsistent { color: #f56c6c; font-weight: 700; font-size: 12px; }
.required-field :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }
.expand-detail { padding: 12px 20px; background: #fafafa; }
.trigger-box {
  margin-bottom: 12px; padding: 8px 12px; background: #fdf6ec;
  border-left: 3px solid #e6a23c; border-radius: 0 4px 4px 0; font-size: 12px;
}
.trigger-box ul { margin: 4px 0 0; padding-left: 18px; line-height: 1.6; }
.check-section { margin-bottom: 14px; }
.check-section-title {
  font-weight: 600; font-size: 13px; color: #303133; margin-bottom: 8px;
  padding-left: 8px; border-left: 3px solid #409eff;
}
.check-detail-table { width: 100%; font-size: 12px; }
.bottom-section { margin-top: 14px; }
.summary-stats {
  display: flex; flex-wrap: wrap; align-items: center; gap: 10px;
  padding: 10px 14px; background: #f5f7fa; border-radius: 4px; margin-bottom: 12px; font-size: 12px;
}
.summary-label { font-weight: 700; color: #606266; }
.summary-sep { color: #dcdfe6; }
.g5-guide-details { margin-top: 14px; font-size: 12px; color: #606266; }
.g5-guide-details summary { cursor: pointer; font-weight: 600; color: #409eff; }
.g5-guide-content {
  padding: 8px 12px; background: #fffbeb; border-left: 3px solid #f59e0b; margin-top: 6px; line-height: 1.8;
}
.g5-guide-content ol { margin: 0; padding-left: 18px; }
.cas-basis { margin: 8px 0 0; color: #909399; font-size: 11px; }
</style>
