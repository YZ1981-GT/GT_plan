<!--
  G7TabImpairmentTest.vue — G7-17 减值测试表

  核心特色：CAS8 减值判断标准
  - 可收回金额(公式) = MAX(公允价值-处置费用, 使用价值)；可勾选手工覆盖
  - 减值金额(公式) = MAX(0, 账面价值 - 可收回金额)
  - 减值迹象=是 → 公允-处置/使用价值 两列高亮；可收回取高
  - 减值迹象=否 → 可收回/公允-处置/使用价值 三列禁用
  - 行结论随减值金额自动对齐；双零告警；G7-14 账面 stale；跨表勾稽

  Spec: .kiro/specs/g7-long-term-equity-method/
  Task: 8.2
  Requirements: 6.5, 6.6, 6.7, 7.4
-->
<template>
  <div class="g7-tab-impairment-test">
    <div class="methodology-context">
      <p><strong>减值判断标准（CAS8）：</strong></p>
      <ul>
        <li>可收回金额 = MAX(公允价值 - 处置费用, 使用价值)</li>
        <li>减值金额 = MAX(0, 账面价值 - 可收回金额)</li>
        <li>减值迹象包括：被投资方持续亏损、净资产大幅下降、市场环境显著恶化、技术/法律变化等</li>
        <li>长期股权投资减值损失一经确认，不得转回</li>
      </ul>
    </div>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：评价长期股权投资减值迹象识别及可收回金额估计的合理性，验证减值准备计提是否充分（CAS8）。"
      class="objective-alert"
    />

    <el-alert
      v-if="missingRecoverableCount > 0"
      type="warning"
      :closable="false"
      :title="`有 ${missingRecoverableCount} 行标记减值迹象=是，但公允净额与使用价值均为 0，可收回金额将为 0，可能误提全额减值。请补填估值输入或改用手工覆盖。`"
      class="warn-alert"
    />

    <el-alert
      v-if="staleBookCount > 0"
      type="warning"
      :closable="false"
      class="warn-alert"
    >
      <template #title>
        <span>
          有 {{ staleBookCount }} 行账面价值相对 G7-14 已过期。
          <el-button
            link
            type="primary"
            size="small"
            :disabled="isReadonly || syncingCross"
            @click="refreshStaleBooks"
          >
            一键刷新账面
          </el-button>
        </span>
      </template>
    </el-alert>

    <!-- 减值勾稽面板 -->
    <div class="recon-panel" :class="{ 'recon-mismatch': !recon.matched714 || !recon.matched72 }">
      <span class="recon-title">减值勾稽</span>
      <span>G7-17 ∑减值 {{ fmtNum(recon.g717Total) }}</span>
      <span :class="{ 'recon-bad': !recon.matched714 }">
        ↔ G7-14 减值准备 {{ fmtNum(recon.g714Total) }}
        <template v-if="!recon.matched714">（差 {{ fmtNum(recon.diff714) }}）</template>
      </span>
      <span :class="{ 'recon-bad': !recon.matched72 }">
        ↔ G7-2 减值期末 {{ fmtNum(recon.g72Total) }}
        <template v-if="!recon.matched72">（差 {{ fmtNum(recon.diff72) }}）</template>
      </span>
      <el-button link size="small" :loading="syncingCross" @click="refreshReconSources">刷新勾稽</el-button>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">G7-17 减值测试表</h3>
      <div class="head-actions">
        <el-button size="small" :disabled="isReadonly" @click="openAddRowDialog">＋ 新增</el-button>
        <el-button
          size="small"
          :disabled="isReadonly || syncingCross"
          :loading="syncingCross"
          @click="syncFromRelated"
        >
          从关联表带入
        </el-button>
        <el-button
          size="small"
          :disabled="isReadonly || syncingToG714"
          :loading="syncingToG714"
          @click="syncImpairmentToG714"
        >
          同步至 G7-14
        </el-button>
        <el-dropdown
          trigger="click"
          size="small"
          :disabled="importExport.importing.value"
          @command="handleDropdownCommand"
        >
          <el-button size="small" :loading="importExport.importing.value">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item v-if="!isReadonly" command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAiConclusion">🤖AI辅助</el-button>
        <el-button size="small" @click="openReviewDialog('G7-17-impairment-test')">💬复核</el-button>
      </div>
    </div>
    <input
      ref="fileInput"
      type="file"
      accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      style="display:none"
      @change="onFileSelected"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G7-17" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <el-table
      :data="rows"
      border
      size="small"
      max-height="580"
      class="impairment-test-table"
      row-key="id"
    >
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>

      <el-table-column label="被投资单位" min-width="130" fixed>
        <template #default="{ row }">
          <el-input
            :model-value="row.investeeName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => updateField(row.id, 'investeeName', v)"
          />
        </template>
      </el-table-column>

      <el-table-column label="账面价值" min-width="140" align="right">
        <template #default="{ row }">
          <div class="book-cell">
            <el-input-number
              :model-value="row.bookValue"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @change="(v: number | undefined) => handleBookValueChange(row.id, v ?? 0)"
            />
            <el-tag
              v-if="isRowBookStale(row)"
              size="small"
              type="warning"
              class="stale-tag"
              title="G7-14 账面已变化"
            >
              源已变
            </el-tag>
            <el-button
              v-if="isRowBookStale(row) && !isReadonly"
              link
              type="primary"
              size="small"
              @click="refreshRowBook(row.id)"
            >
              刷新
            </el-button>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="期初已提" min-width="110" align="right">
        <template #header>
          <span class="formula-header" title="期初已计提减值准备 → consol open_impairment">期初已提</span>
        </template>
        <template #default="{ row }">
          <el-input-number
            :model-value="row.openingImpairment ?? 0"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => updateField(row.id, 'openingImpairment', v ?? 0)"
          />
        </template>
      </el-table-column>

      <el-table-column label="可收回金额" min-width="160" align="right">
        <template #header>
          <span class="formula-header" title="= MAX(公允价值-处置费用, 使用价值)；可勾选手工覆盖">
            可收回金额
          </span>
        </template>
        <template #default="{ row }">
          <div v-if="row.hasImpairmentSign" class="recoverable-cell">
            <el-checkbox
              :model-value="!!row.recoverableManual"
              :disabled="isReadonly"
              size="small"
              @change="(v: boolean | string | number) => toggleRecoverableManual(row.id, !!v)"
            >
              手工
            </el-checkbox>
            <el-input-number
              v-if="row.recoverableManual"
              :model-value="row.recoverableAmount"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @change="(v: number | undefined) => handleManualRecoverable(row.id, v ?? 0)"
            />
            <span
              v-else
              class="formula-cell"
              :title="`MAX(${fmtNum(row.fvLessDisposalCost)}, ${fmtNum(row.valueInUse)}) = ${fmtNum(row.recoverableAmount)}`"
            >
              {{ fmtNum(row.recoverableAmount) }}
            </span>
            <el-input
              v-if="row.recoverableManual"
              :model-value="row.recoverableOverrideReason || ''"
              size="small"
              placeholder="覆盖原因"
              :disabled="isReadonly"
              @change="(v: string) => updateField(row.id, 'recoverableOverrideReason', v)"
            />
          </div>
          <span
            v-else
            class="formula-cell disabled-cell"
            title="无减值迹象时不测算可收回金额"
          >
            {{ fmtNum(0) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="减值迹象" width="100" align="center">
        <template #default="{ row }">
          <el-select
            :model-value="row.hasImpairmentSign ? '是' : '否'"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => handleSignChange(row.id, v === '是')"
          >
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="减值金额" min-width="120" align="right">
        <template #header>
          <span class="formula-header" title="= MAX(0, 账面价值 - 可收回金额)">
            减值金额
          </span>
        </template>
        <template #default="{ row }">
          <span
            class="formula-cell"
            :class="{ 'impairment-positive': row.impairmentAmount > 0 }"
            :title="`MAX(0, ${fmtNum(row.bookValue)} - ${fmtNum(row.recoverableAmount)}) = ${fmtNum(row.impairmentAmount)}`"
          >
            {{ fmtNum(row.impairmentAmount) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="公允-处置费用" min-width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.fvLessDisposalCost"
            size="small"
            :controls="false"
            :disabled="isReadonly || !row.hasImpairmentSign"
            :class="{
              'highlight-required': row.hasImpairmentSign && !row.recoverableManual,
              'disabled-cell': !row.hasImpairmentSign,
              'warn-zero': hasMissingRecoverableInputs(row),
            }"
            style="width:100%"
            @change="(v: number | undefined) => handleFvOrViuChange(row.id, 'fvLessDisposalCost', v ?? 0)"
          />
        </template>
      </el-table-column>

      <el-table-column label="使用价值" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.valueInUse"
            size="small"
            :controls="false"
            :disabled="isReadonly || !row.hasImpairmentSign"
            :class="{
              'highlight-required': row.hasImpairmentSign && !row.recoverableManual,
              'disabled-cell': !row.hasImpairmentSign,
              'warn-zero': hasMissingRecoverableInputs(row),
            }"
            style="width:100%"
            @change="(v: number | undefined) => handleFvOrViuChange(row.id, 'valueInUse', v ?? 0)"
          />
        </template>
      </el-table-column>

      <el-table-column label="审计结论" width="120" align="center">
        <template #default="{ row }">
          <el-select
            :model-value="row.auditConclusion"
            size="small"
            placeholder="请选择"
            clearable
            :disabled="isReadonly"
            @change="(v: string) => updateField(row.id, 'auditConclusion', v || '')"
          >
            <el-option label="无需计提" value="无需计提" />
            <el-option label="需计提" value="需计提" />
            <el-option label="已充分计提" value="已充分计提" />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="索引" width="90">
        <template #default="{ row }">
          <el-input
            :model-value="row.indexRef"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => updateField(row.id, 'indexRef', v)"
          />
        </template>
      </el-table-column>

      <el-table-column label="依据" width="100" align="center">
        <template #default="{ row }">
          <div class="attach-cell">
            <el-button
              v-if="!isReadonly"
              link
              size="small"
              title="上传估值依据 / OCR"
              @click="handleAttachment(row)"
            >
              📎
            </el-button>
            <span v-if="row.attachmentName" class="attach-name" :title="row.attachmentName">
              {{ row.attachmentName }}
            </span>
          </div>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-icon class="delete-icon" @click="handleRemoveRow(row.id)">
            <Delete />
          </el-icon>
        </template>
      </el-table-column>
    </el-table>

    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计说明</span>
          <el-button size="small" :disabled="isReadonly" @click="handleAiNote">🤖AI辅助</el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述所执行程序、测试情况及结果，拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计结论</span>
          <el-button size="small" :disabled="isReadonly" @click="handleAiConclusion">🤖AI辅助</el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对长期股权投资减值测试的审计结论..."
        @change="persistConclusion"
      />
    </el-card>

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>减值迹象判断：被投资方持续亏损、经营恶化、净资产大幅下降、市价持续低于账面</li>
        <li>减值迹象=否时，可收回金额/公允-处置费用/使用价值三列自动禁用</li>
        <li>减值迹象=是时，公允-处置费用与使用价值高亮必填；可收回金额 = MAX(二者) 自动取高；可勾选「手工」覆盖并填写原因</li>
        <li>行结论自动对齐：减值&gt;0→需计提；=0→无需计提（「已充分计提」不覆盖）</li>
        <li>可用「从关联表带入」自 G7-4 / G7-14 预填；账面相对 G7-14 变化时显示「源已变」</li>
        <li>「同步至 G7-14」将各行减值金额写入 G7-14 减值准备列；G7-14 亦可从关联表带入 G7-17</li>
        <li>期初已提减值 → consol open_impairment；本期减值金额 → add_impairment</li>
        <li>顶部勾稽：∑G7-17 减值 ↔ G7-14 减值准备 ↔ G7-2 减值期末</li>
        <li>长期股权投资减值损失一经确认，不得转回（CAS8）</li>
        <li>保存后写入 G7-17-rows；合并工作底稿可通过 linkage 将本期增加减值带入 equity_inv</li>
      </ul>
    </details>

    <!-- 新增行：从 G7-4 下拉选择 -->
    <el-dialog
      v-model="addDialogVisible"
      title="新增减值测试行"
      width="420px"
      destroy-on-close
    >
      <el-form label-width="100px">
        <el-form-item label="被投资单位">
          <el-select
            v-model="addDialogInvestee"
            filterable
            allow-create
            default-first-option
            placeholder="从 G7-4 选择或输入名称"
            style="width:100%"
          >
            <el-option
              v-for="opt in investeeOptions"
              :key="opt.investeeId || opt.name"
              :label="opt.name"
              :value="opt.name"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAddRow">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { extractG7AiText } from '../../composables/g7AiText'
/**
 * G7TabImpairmentTest — G7-17 减值测试表
 */
import { ref, computed, inject, onMounted } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { parseNum } from '../../composables/useG7EquityMethodFormulaEngine'
import { useG7EquityMethodFormData } from '../../composables/useG7EquityMethodFormData'
import type { ImpairmentTestRow } from '../../composables/useG7EquityMethodFormData'
import { useG7EquityMethodImportExport } from '../../composables/useG7EquityMethodImportExport'
import {
  G7_2_ROWS_KEY,
  G7_4_ROWS_KEY,
  G7_17_ROWS_KEY,
  G7_17_SECTION_KEY,
  applyG717ImpairmentToG714Payload,
  buildG714DualWriteItems,
  flattenG714Rows,
  loadEquityInvestees,
  makeG714ConclusionGetter,
  parseChecklistJson,
  resolveG714PayloadFromChecklist,
  type G7EquityInvesteeOption,
} from '../../composables/g7EquityMethodCrossSheet'
import { normalizeG7DetailRows } from '../../composables/g7DetailModel'
import { emitG7SourceRowsSaved } from '../../composables/g7DisclosureCrossSheet'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'
import {
  G7_IMPAIRMENT_UPDATED_EVENT,
  applyAutoAuditConclusion,
  calcImpairmentRecon,
  extractG714Book,
  hasMissingRecoverableInputs,
  isBookValueStale,
  recalcImpairmentAmounts,
  sumG714Impairment,
  sumG72ImpairmentClosing,
  sumImpairmentAmounts,
} from './g7ImpairmentTestModel'

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const isReadonly = computed(() => props.readonly ?? false)
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const formData = useG7EquityMethodFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const importExport = useG7EquityMethodImportExport({
  wpId: computed(() => props.wpId),
})

const SECTION_KEY = G7_17_SECTION_KEY
const ROWS_KEY = G7_17_ROWS_KEY
const CONCLUSION_KEY = 'G7-17-conclusion'
const AUDIT_NOTE_KEY = 'G7-17-audit-note'

const rows = ref<ImpairmentTestRow[]>([])
const conclusion = ref('')
const auditNote = ref('')
const syncingCross = ref(false)
const syncingToG714 = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const investeeOptions = ref<G7EquityInvesteeOption[]>([])
const g714BookByName = ref<Record<string, number>>({})
const g714ImpairmentTotal = ref(0)
const g72ImpairmentTotal = ref(0)

const addDialogVisible = ref(false)
const addDialogInvestee = ref('')

const missingRecoverableCount = computed(() =>
  rows.value.filter((r) => hasMissingRecoverableInputs(r)).length,
)

const staleBookCount = computed(() =>
  rows.value.filter((r) => isRowBookStale(r)).length,
)

const recon = computed(() =>
  calcImpairmentRecon(
    sumImpairmentAmounts(rows.value),
    g714ImpairmentTotal.value,
    g72ImpairmentTotal.value,
  ),
)

function saveAuditNote(val: string): void {
  if (isReadonly.value) return
  auditNote.value = val
  formData.debouncedSave(AUDIT_NOTE_KEY, { remark: val, conclusion: null })
}

function normalizeYesNo(v: unknown): boolean {
  if (typeof v === 'boolean') return v
  if (typeof v === 'number') return v !== 0
  const s = String(v ?? '').trim().toLowerCase()
  return s === '是' || s === 'true' || s === '1' || s === 'y' || s === 'yes'
}

function parseSaved(raw: unknown): unknown {
  if (raw == null || raw === '') return null
  if (typeof raw === 'object') return raw
  try { return JSON.parse(String(raw)) } catch { return null }
}

function hydrateRows(payload: unknown): boolean {
  if (payload == null) return false
  let list: any[] | null = null
  if (Array.isArray(payload)) list = payload
  else if (typeof payload === 'object' && Array.isArray((payload as any).rows)) {
    list = (payload as any).rows
  }
  if (!list?.length) return false
  rows.value = list.map((r: any, idx: number) => {
    const row: ImpairmentTestRow = {
      ...createEmptyRow(idx + 1),
      ...r,
      seq: idx + 1,
      id: r.id || `g17-${Date.now()}-${idx}`,
      hasImpairmentSign: normalizeYesNo(r.hasImpairmentSign),
      bookValue: parseNum(r.bookValue),
      sourceBookValue: r.sourceBookValue != null ? parseNum(r.sourceBookValue) : null,
      openingImpairment: parseNum(r.openingImpairment),
      fvLessDisposalCost: parseNum(r.fvLessDisposalCost),
      valueInUse: parseNum(r.valueInUse),
      recoverableAmount: parseNum(r.recoverableAmount),
      impairmentAmount: parseNum(r.impairmentAmount),
      recoverableManual: !!r.recoverableManual,
      recoverableOverrideReason: String(r.recoverableOverrideReason ?? ''),
      attachmentName: String(r.attachmentName ?? ''),
      investeeId: r.investeeId || undefined,
    }
    return row
  })
  recalcAll()
  return true
}

function loadRowsFromChecklist(): boolean {
  const rowsSaved = parseSaved(
    formData.data.value.get(ROWS_KEY)?.conclusion
    ?? formData.data.value.get(ROWS_KEY)?.remark,
  )
  const sectionSaved = parseSaved(formData.data.value.get(SECTION_KEY)?.conclusion)
  return hydrateRows(rowsSaved) || hydrateRows(sectionSaved)
}

onMounted(async () => {
  await formData.load()

  const snapshotRows = parseSaved(
    props.htmlData?.responses_snapshot?.[ROWS_KEY]?.conclusion
    ?? props.htmlData?.responses_snapshot?.[ROWS_KEY]?.remark,
  )
  const snapshotSection = parseSaved(
    props.htmlData?.responses_snapshot?.[SECTION_KEY]?.conclusion,
  )

  if (
    !loadRowsFromChecklist()
    && !hydrateRows(snapshotRows)
    && !hydrateRows(snapshotSection)
    && !hydrateRows((props.htmlData as any)?.impairmentTest)
    && !hydrateRows((props.htmlData as any)?.rows)
  ) {
    rows.value = Array.from({ length: 5 }, (_, i) => createEmptyRow(i + 1))
  }

  const savedConclusion = formData.data.value.get(CONCLUSION_KEY)
  if (savedConclusion?.conclusion) {
    conclusion.value = savedConclusion.conclusion
  }

  const savedNote = formData.data.value.get(AUDIT_NOTE_KEY)
  if (savedNote?.remark) {
    auditNote.value = savedNote.remark
  }

  await refreshCrossSheetCaches()
})

function createEmptyRow(seq: number, investeeName = '', investeeId = ''): ImpairmentTestRow {
  return {
    id: `g17-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    seq,
    investeeName,
    investeeId: investeeId || undefined,
    bookValue: 0,
    sourceBookValue: null,
    openingImpairment: 0,
    recoverableAmount: 0,
    recoverableManual: false,
    recoverableOverrideReason: '',
    hasImpairmentSign: false,
    impairmentAmount: 0,
    fvLessDisposalCost: 0,
    valueInUse: 0,
    auditConclusion: '' as any,
    indexRef: '',
    attachmentName: '',
  }
}

function recalcRow(row: ImpairmentTestRow): void {
  recalcImpairmentAmounts(row)
  applyAutoAuditConclusion(row)
}

function recalcAll(): void {
  for (const row of rows.value) {
    recalcRow(row)
  }
}

function updateField(rowId: string, field: keyof ImpairmentTestRow, value: any): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  ;(row as any)[field] = value
  if (field !== 'auditConclusion' && field !== 'indexRef' && field !== 'attachmentName'
    && field !== 'recoverableOverrideReason' && field !== 'investeeName') {
    recalcRow(row)
  }
  persistRows()
}

function handleBookValueChange(rowId: string, value: number): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.bookValue = value
  recalcRow(row)
  persistRows()
}

function handleFvOrViuChange(
  rowId: string,
  field: 'fvLessDisposalCost' | 'valueInUse',
  value: number,
): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row[field] = value
  recalcRow(row)
  persistRows()
}

function handleSignChange(rowId: string, hasSign: boolean): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.hasImpairmentSign = hasSign

  if (!hasSign) {
    row.recoverableAmount = 0
    row.fvLessDisposalCost = 0
    row.valueInUse = 0
    row.recoverableManual = false
    row.recoverableOverrideReason = ''
  }

  recalcRow(row)
  persistRows()
}

function toggleRecoverableManual(rowId: string, manual: boolean): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.recoverableManual = manual
  if (!manual) {
    row.recoverableOverrideReason = ''
  }
  recalcRow(row)
  persistRows()
}

function handleManualRecoverable(rowId: string, value: number): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.recoverableAmount = value
  row.recoverableManual = true
  recalcRow(row)
  persistRows()
}

function isRowBookStale(row: ImpairmentTestRow): boolean {
  const name = String(row.investeeName ?? '').trim()
  if (!name) return false
  const current = g714BookByName.value[name]
  if (current == null) return false
  return isBookValueStale(row.bookValue, row.sourceBookValue, current)
}

function refreshRowBook(rowId: string): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  const name = String(row.investeeName ?? '').trim()
  const book = g714BookByName.value[name]
  if (book == null) {
    ElMessage.warning('未找到对应 G7-14 账面')
    return
  }
  row.bookValue = book
  row.sourceBookValue = book
  recalcRow(row)
  persistRows()
  ElMessage.success(`已刷新 ${name} 账面`)
}

function refreshStaleBooks(): void {
  let n = 0
  for (const row of rows.value) {
    if (!isRowBookStale(row)) continue
    const name = String(row.investeeName ?? '').trim()
    const book = g714BookByName.value[name]
    if (book == null) continue
    row.bookValue = book
    row.sourceBookValue = book
    recalcRow(row)
    n++
  }
  if (n) {
    persistRows()
    ElMessage.success(`已刷新 ${n} 行账面`)
  } else {
    ElMessage.info('无需刷新')
  }
}

async function refreshCrossSheetCaches(): Promise<void> {
  investeeOptions.value = loadEquityInvestees(
    formData.data.value.get(G7_4_ROWS_KEY)?.conclusion
    ?? props.htmlData?.responses_snapshot?.[G7_4_ROWS_KEY]?.conclusion,
  )

  const g714Payload = resolveG714PayloadFromChecklist(
    makeG714ConclusionGetter(formData.data.value, props.htmlData?.responses_snapshot),
  )
  const g714Rows = flattenG714Rows(g714Payload)
  const bookMap: Record<string, number> = {}
  for (const r of g714Rows) {
    const name = String(r.investeeName ?? '').trim()
    if (!name) continue
    bookMap[name] = extractG714Book(r)
  }
  g714BookByName.value = bookMap
  g714ImpairmentTotal.value = sumG714Impairment(g714Rows)

  const g72Raw = parseChecklistJson(
    formData.data.value.get(G7_2_ROWS_KEY)?.conclusion
    ?? props.htmlData?.responses_snapshot?.[G7_2_ROWS_KEY]?.conclusion,
  )
  const detail = normalizeG7DetailRows(g72Raw)
  g72ImpairmentTotal.value = sumG72ImpairmentClosing(detail.impairmentRows)
}

async function refreshReconSources(): Promise<void> {
  syncingCross.value = true
  try {
    await formData.loadResponses()
    await refreshCrossSheetCaches()
    ElMessage.success('勾稽源已刷新')
  } catch {
    ElMessage.error('勾稽源刷新失败')
  } finally {
    syncingCross.value = false
  }
}

function openAddRowDialog(): void {
  addDialogInvestee.value = ''
  void refreshCrossSheetCaches()
  addDialogVisible.value = true
}

function confirmAddRow(): void {
  const name = String(addDialogInvestee.value ?? '').trim()
  if (!name) {
    ElMessage.warning('被投资单位名称不能为空')
    return
  }
  const matched = investeeOptions.value.find((o) => o.name === name || o.investeeId === name)
  const newRow = createEmptyRow(
    rows.value.length + 1,
    matched?.name || name,
    matched?.investeeId || '',
  )
  const book = g714BookByName.value[newRow.investeeName]
  if (book) {
    newRow.bookValue = book
    newRow.sourceBookValue = book
  }
  recalcRow(newRow)
  rows.value.push(newRow)
  persistRows()
  addDialogVisible.value = false
  ElMessage.success(`已新增: ${newRow.investeeName}`)
}

function handleRemoveRow(rowId: string): void {
  const idx = rows.value.findIndex((r) => r.id === rowId)
  if (idx < 0) return
  rows.value.splice(idx, 1)
  rows.value.forEach((r, i) => { r.seq = i + 1 })
  persistRows()
}

async function handleAttachment(row: ImpairmentTestRow): Promise<void> {
  if (isReadonly.value) return
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    row.attachmentName = file.name
    if (!row.indexRef) row.indexRef = `附:${file.name}`
    persistRows()
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await api.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, fd)
      const data = res?.data?.data ?? res?.data ?? {}
      const preview = [
        data.businessContent || data.summary || data.content || '',
        data.amount != null ? `金额:${data.amount}` : '',
      ].filter(Boolean).join(' / ') || '（未识别到结构化字段）'
      await ElMessageBox.confirm(
        `OCR 识别：${preview}\n是否将摘要追加到审计说明？`,
        '估值依据 OCR',
        { confirmButtonText: '追加', cancelButtonText: '仅保留附件名' },
      )
      const line = `[${row.investeeName || '未命名'}] ${file.name}: ${preview}`
      auditNote.value = auditNote.value ? `${auditNote.value}\n${line}` : line
      saveAuditNote(auditNote.value)
      ElMessage.success('附件已登记，OCR 摘要已追加')
    } catch (e: any) {
      if (e !== 'cancel' && e?.toString?.() !== 'cancel') {
        ElMessage.success('附件名已登记（OCR 暂不可用）')
      } else {
        ElMessage.success('附件名已登记')
      }
    }
  }
  input.click()
}

function persistRows(): void {
  if (isReadonly.value) return
  const payload = JSON.stringify({ rows: rows.value })
  const flatRows = JSON.stringify(rows.value)
  formData.debouncedSaveBatch([
    {
      itemId: SECTION_KEY,
      data: { conclusion: payload, remark: null },
    },
    {
      itemId: ROWS_KEY,
      data: { conclusion: flatRows, remark: flatRows },
    },
  ])
  try {
    window.dispatchEvent(new CustomEvent(G7_IMPAIRMENT_UPDATED_EVENT, {
      detail: {
        projectId: props.projectId,
        wpId: props.wpId,
        itemIds: [ROWS_KEY, SECTION_KEY],
        rowCount: rows.value.length,
        totalImpairment: sumImpairmentAmounts(rows.value),
        timestamp: Date.now(),
      },
    }))
    emitG7SourceRowsSaved({
      projectId: props.projectId,
      wpId: props.wpId,
      itemIds: [ROWS_KEY, SECTION_KEY],
    })
  } catch { /* ignore */ }
}

function persistConclusion(): void {
  formData.debouncedSave(CONCLUSION_KEY, { conclusion: conclusion.value })
}

async function handleAiConclusion(): Promise<void> {
  if (isReadonly.value) return
  try {
    const res = await api.post(
      `/api/workpapers/${props.wpId}/g7-equity-method/ai/impairment-conclusion`,
      {
        project_id: props.projectId,
        existingContent: conclusion.value,
        relatedContext: { rows: rows.value, recon: recon.value },
      },
    )
    const aiText = extractG7AiText(res?.data)
    if (aiText) {
      conclusion.value = conclusion.value ? `${conclusion.value}\n${aiText}` : aiText
      persistConclusion()
      ElMessage.success('AI结论已生成')
    } else {
      generateLocalConclusion()
    }
  } catch {
    generateLocalConclusion()
  }
}

async function handleAiNote(): Promise<void> {
  if (isReadonly.value) return
  try {
    const res = await api.post(
      `/api/workpapers/${props.wpId}/g7-equity-method/ai/impairment-note`,
      {
        project_id: props.projectId,
        existingContent: auditNote.value,
        relatedContext: { rows: rows.value, recon: recon.value },
      },
    )
    const aiText = extractG7AiText(res?.data)
    if (aiText) {
      auditNote.value = auditNote.value ? `${auditNote.value}\n${aiText}` : aiText
      saveAuditNote(auditNote.value)
      ElMessage.success('AI说明已生成')
    } else {
      generateLocalNote()
    }
  } catch {
    generateLocalNote()
  }
}

function generateLocalConclusion(): void {
  const total = rows.value.length
  const withSign = rows.value.filter((r) => r.hasImpairmentSign).length
  const withImpairment = rows.value.filter((r) => r.impairmentAmount > 0).length
  const totalImpairment = sumImpairmentAmounts(rows.value)

  const draft =
    `经检查，本期共有 ${total} 项长期股权投资纳入减值测试，` +
    `其中 ${withSign} 项存在减值迹象。` +
    (withImpairment > 0
      ? `经测算，${withImpairment} 项需计提减值准备，减值金额合计 ${fmtNum(totalImpairment)} 元。`
      : `经测算，各项投资可收回金额均不低于账面价值，无需计提减值准备。`) +
    ` 减值测试方法及结论恰当。`

  conclusion.value = conclusion.value ? `${conclusion.value}\n${draft}` : draft
  persistConclusion()
  ElMessage.success('已生成本地结论')
}

function generateLocalNote(): void {
  const withSign = rows.value.filter((r) => r.hasImpairmentSign)
  const missing = withSign.filter((r) => hasMissingRecoverableInputs(r))
  const draft =
    `已执行减值迹象识别，共 ${withSign.length} 项标记存在迹象；` +
    (missing.length
      ? `其中 ${missing.length} 项尚未填列公允净额/使用价值，待补估值依据。`
      : `已复核可收回金额估计依据。`) +
    ` 勾稽：G7-17 ∑减值 ${fmtNum(recon.value.g717Total)}，` +
    `G7-14 ${fmtNum(recon.value.g714Total)}，G7-2 ${fmtNum(recon.value.g72Total)}。`

  auditNote.value = auditNote.value ? `${auditNote.value}\n${draft}` : draft
  saveAuditNote(auditNote.value)
  ElMessage.success('已生成本地说明')
}

async function handleDropdownCommand(command: string): Promise<void> {
  if (command === 'template') await importExport.exportTemplate('G7-17')
  else if (command === 'export') await importExport.exportData('G7-17')
  else if (command === 'import') fileInput.value?.click()
}

async function onFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const result = await importExport.importData('G7-17', file)
  if (!result) return
  await formData.load()
  if (loadRowsFromChecklist()) {
    await refreshCrossSheetCaches()
    ElMessage.success(`导入完成，已刷新 ${rows.value.length} 行`)
  } else {
    ElMessage.warning('导入完成，但未解析到行数据')
  }
}

async function syncImpairmentToG714(): Promise<void> {
  if (isReadonly.value || syncingToG714.value) return
  const named = rows.value.filter(r => String(r.investeeName ?? '').trim())
  if (!named.length) {
    ElMessage.warning('无有效被投资单位行可同步')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将把 ${named.length} 行的减值金额写入 G7-14「减值准备」列（按被投资单位匹配，覆盖原值）。是否继续？`,
      '同步至 G7-14',
      { confirmButtonText: '确认覆盖', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  syncingToG714.value = true
  try {
    await formData.loadResponses()
    const g714Payload = resolveG714PayloadFromChecklist(
      makeG714ConclusionGetter(formData.data.value, props.htmlData?.responses_snapshot),
    )
    const result = applyG717ImpairmentToG714Payload(g714Payload, { rows: rows.value })
    if (!result.ok || !result.payload) {
      ElMessage.warning(result.message)
      return
    }
    await formData.saveBatch(buildG714DualWriteItems(result.payload))
    await refreshCrossSheetCaches()
    ElMessage.success(result.message)
  } catch {
    ElMessage.error('同步至 G7-14 失败')
  } finally {
    syncingToG714.value = false
  }
}

async function syncFromRelated(): Promise<void> {
  if (isReadonly.value || syncingCross.value) return
  syncingCross.value = true
  try {
    await formData.loadResponses()
    await refreshCrossSheetCaches()
    const g74 = investeeOptions.value
    const g714Payload = resolveG714PayloadFromChecklist(
      makeG714ConclusionGetter(formData.data.value, props.htmlData?.responses_snapshot),
    )
    const g714Rows = flattenG714Rows(g714Payload)

    const names = g74.length
      ? g74.map(x => ({ name: x.name, id: x.investeeId }))
      : g714Rows
        .map((r: any) => ({
          name: String(r.investeeName ?? '').trim(),
          id: String(r.investeeId ?? '').trim() || undefined,
        }))
        .filter(x => x.name)

    if (!names.length) {
      ElMessage.warning('未找到 G7-4 / G7-14 被投资单位，请先维护关联表')
      return
    }

    let added = 0
    let filled = 0
    for (const inv of names) {
      let row = rows.value.find(r => r.investeeName === inv.name)
      if (!row) {
        row = createEmptyRow(rows.value.length + 1, inv.name, inv.id || '')
        rows.value.push(row)
        added++
      } else if (inv.id && !row.investeeId) {
        row.investeeId = inv.id
      }
      const match714 = g714Rows.find((r: any) => String(r.investeeName ?? '').trim() === inv.name)
      if (match714) {
        const book = extractG714Book(match714)
        if (book && !parseNum(row.bookValue)) {
          row.bookValue = book
          row.sourceBookValue = book
          filled++
        } else if (book && row.sourceBookValue == null) {
          row.sourceBookValue = book
        }
      }
      recalcRow(row)
    }
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    persistRows()
    ElMessage.success(`已带入：新增 ${added} 家，回填账面 ${filled} 项`)
  } catch {
    ElMessage.error('关联表带入失败')
  } finally {
    syncingCross.value = false
  }
}

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}
</script>

<style scoped>
.g7-tab-impairment-test {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.objective-alert,
.warn-alert {
  margin-bottom: 12px;
}
.recon-panel {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: #f4f4f5;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
}
.recon-panel.recon-mismatch {
  background: #fef0f0;
  border: 1px solid #fbc4c4;
}
.recon-title {
  font-weight: 600;
  color: #303133;
}
.recon-bad {
  color: #f56c6c;
  font-weight: 600;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.tab-toolbar .toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.tab-toolbar .chip-wrap {
  display: inline-flex;
  align-items: center;
}
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  margin-bottom: 14px;
  border-radius: 0 4px 4px 0;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.7;
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
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.sheet-title {
  margin: 0;
  font-size: 15px;
}
.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.impairment-test-table {
  font-size: var(--wp-font-size, 13px);
}
.formula-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  display: inline-block;
  min-width: 40px;
  text-align: right;
}
.formula-cell.disabled-cell {
  color: #c0c4cc;
  border-bottom-color: #e4e7ed;
  cursor: default;
}
.impairment-positive {
  color: #f56c6c;
  font-weight: 600;
}
.book-cell,
.recoverable-cell,
.attach-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: stretch;
}
.stale-tag {
  align-self: flex-start;
}
.attach-name {
  font-size: 11px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 90px;
}
:deep(.highlight-required .el-input__wrapper),
:deep(.highlight-required .el-input-number__wrapper) {
  background-color: #fef0f0;
  border-color: #fab6b6;
}
:deep(.warn-zero .el-input__wrapper),
:deep(.warn-zero .el-input-number__wrapper) {
  background-color: #fdf6ec;
  border-color: #e6a23c;
}
:deep(.disabled-cell .el-input__wrapper),
:deep(.disabled-cell .el-input-number__wrapper) {
  background-color: #f5f7fa;
}
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}
.conclusion-card {
  margin-top: 14px;
}
.conclusion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
.prep-hint summary {
  cursor: pointer;
}
.prep-hint ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
</style>
