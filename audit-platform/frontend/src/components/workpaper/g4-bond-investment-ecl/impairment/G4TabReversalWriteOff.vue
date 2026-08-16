<!--
  G4TabReversalWriteOff.vue — G4-12 减值准备转回（收回）、核销检查表（20列 → 2区段Tab）

  2区段Tab切换（el-segmented）：
  - Tab1: 转回（收回）检查(10列): 序号|单位名称|转回原因|收回方式|原确定坏账准备依据|收回或转回金额|收回前累计计提|合理性分析|是否合理|索引
  - Tab2: 核销检查(10列): 序号|单位名称|核销性质|核销金额|核销原因|核销程序|是否关联交易|合理性分析|是否合理|索引

  区段间行同步：切换Tab保持activeRowIndex
  Tab1: 转回金额 > 累计计提 → 红色高亮 + 校验错误
  Tab2: 关联交易 = true → 橙色底色高亮
  各Tab底部合计行（转回金额合计 / 核销金额合计）

  Spec: .kiro/specs/g4-bond-investment-ecl/ Task 8.2
  Requirements: 5.1~5.9, 11.2, 11.5, 11.8
-->
<template>
  <div class="g4-reversal-writeoff">
    <!-- 一、审计目标（对齐纸质底稿） -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="一、审计目标：债权投资已按适当的金额包括在财务报表中，与之相关的计价调整已恰当记录。"
      style="margin-bottom: 12px"
    />

    <el-alert
      v-if="!rw.gate.value.ready"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
      :title="gateAlertTitle"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <G4EclImportExportDropdown
          :wp-id="wpId"
          sheet="G4-12"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:G4-10" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G4-11" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G4-13" :context-project-id="projectId" /></span>
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="info">转回 {{ rw.reversals.value.length }} · 核销 {{ rw.writeOffs.value.length }}</el-tag>
        <el-tag size="small" :type="rw.gate.value.ready ? 'success' : 'warning'">
          闸门 {{ rw.gate.value.ready ? '通过' : '待补' }}
        </el-tag>
        <span class="chip-wrap"><GtIndexChip value="wp:G4-12" :context-project-id="projectId" /></span>
      </div>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">G4-12 减值准备转回（收回）、核销检查表</h3>
      <div class="head-actions">
        <el-segmented v-model="rw.activeTab.value" :options="segmentOptions" size="small" />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 新增行
        </el-button>
        <el-button size="small" type="warning" plain :disabled="isReadonly" @click="pushExceptionDrafts">
          推送例外至 G4-3
        </el-button>
        <el-button size="small" @click="openReviewDialog('G4-12-reversal-writeoff')">💬复核</el-button>
      </div>
    </div>

    <p class="section-label">
      二、审计过程 ·
      {{ rw.activeTab.value === 'tab1' ? '（一）本期重要的坏账准备转回或转销检查' : '（二）本期重要的核销检查' }}
    </p>

    <!-- 单表格 + v-if列组切换 -->
    <el-table
      :data="activeDisplayRows"
      border
      size="small"
      max-height="520"
      highlight-current-row
      row-key="id"
      :row-class-name="activeRowClassName"
      class="reversal-table"
      @current-change="onCurrentChange"
    >
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">
          <template v-if="row._isTotal">
            <span class="total-label">合计</span>
          </template>
          <template v-else>{{ row.seq }}</template>
        </template>
      </el-table-column>

      <el-table-column label="单位名称" min-width="120" fixed>
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <template v-else>
            <el-input v-if="!isReadonly" v-model="row.unitName" size="small" />
            <span v-else>{{ row.unitName }}</span>
          </template>
        </template>
      </el-table-column>

      <!-- ═══ Tab1: 转回（收回）检查列 ═══ -->
      <template v-if="rw.activeTab.value === 'tab1'">
        <el-table-column label="转回原因" min-width="130">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" v-model="row.reversalReason" size="small" placeholder="信用风险改善等" />
              <span v-else>{{ row.reversalReason }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="收回方式" min-width="110">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" v-model="row.recoveryMethod" size="small" placeholder="现金/抵债等" />
              <span v-else>{{ row.recoveryMethod }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="原确定坏账准备的依据" min-width="150">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" v-model="row.originalBasis" size="small" type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }" placeholder="原 Stage/ECL 依据" />
              <span v-else>{{ row.originalBasis }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="收回或转回金额" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(rw.reversalSummary.value.totalReversalAmount) }}</span>
            </template>
            <template v-else>
              <WpAmountInput v-if="!isReadonly" v-model="row.reversalAmount" size="small" class="compact-num" />
              <span v-else>{{ fmtNum(row.reversalAmount) }}</span>
              <div v-if="rw.getReversalError(row)" class="validation-error">
                {{ rw.getReversalError(row) }}
              </div>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="收回或转回前累计已计提" min-width="150" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(rw.reversalSummary.value.totalAccumulatedProvision) }}</span>
            </template>
            <template v-else>
              <WpAmountInput v-if="!isReadonly" v-model="row.accumulatedProvision" size="small" class="compact-num" />
              <span v-else>{{ fmtNum(row.accumulatedProvision) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="合理性分析" min-width="160">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" v-model="row.reasonAnalysis" size="small" type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }" />
              <span v-else>{{ row.reasonAnalysis }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="是否合理" width="100" align="center">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-select v-if="!isReadonly" v-model="row.isReasonable" size="small" style="width: 80px">
                <el-option label="合理" value="合理" />
                <el-option label="不合理" value="不合理" />
              </el-select>
              <span v-else>{{ row.isReasonable }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="索引号" width="100">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <GtIndexChip v-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" />
              <el-input v-else-if="!isReadonly" v-model="row.indexRef" size="small" placeholder="索引" />
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab2: 核销检查列 ═══ -->
      <template v-if="rw.activeTab.value === 'tab2'">
        <el-table-column label="债权投资的性质" min-width="130">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" v-model="row.writeOffType" size="small"
                placeholder="如：公司债/信托计划/贷款" />
              <span v-else>{{ row.writeOffType }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="核销金额" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal">
              <span class="total-num">{{ fmtNum(rw.writeOffSummary.value.totalWriteOffAmount) }}</span>
            </template>
            <template v-else>
              <WpAmountInput v-if="!isReadonly" v-model="row.writeOffAmount" size="small" class="compact-num" />
              <span v-else>{{ fmtNum(row.writeOffAmount) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="核销原因" min-width="140">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" v-model="row.writeOffReason" size="small" type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }" />
              <span v-else>{{ row.writeOffReason }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="履行的核销程序" min-width="140">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" v-model="row.writeOffProcedure" size="small" type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }" placeholder="审批/法务/董事会等" />
              <span v-else>{{ row.writeOffProcedure }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="是否由关联交易产生" width="130" align="center">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-switch v-if="!isReadonly" v-model="row.isRelatedParty" size="small"
                active-text="是" inactive-text="否" />
              <el-tag v-else :type="row.isRelatedParty ? 'warning' : 'info'" size="small">
                {{ row.isRelatedParty ? '是' : '否' }}
              </el-tag>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="合理性分析" min-width="160">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input
                v-if="!isReadonly"
                v-model="row.reasonAnalysis"
                size="small"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }"
                :placeholder="row.isRelatedParty ? '关联交易核销须说明合理性' : ''"
                :class="{ 'remark-required': row.isRelatedParty && !(row.reasonAnalysis || '').trim() }"
              />
              <span v-else>{{ row.reasonAnalysis }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="是否合理" width="100" align="center">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-select v-if="!isReadonly" v-model="row.isReasonable" size="small" style="width: 80px">
                <el-option label="合理" value="合理" />
                <el-option label="不合理" value="不合理" />
              </el-select>
              <span v-else>{{ row.isReasonable }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="索引号" width="100">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <GtIndexChip v-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" />
              <el-input v-else-if="!isReadonly" v-model="row.indexRef" size="small" placeholder="索引" />
            </template>
          </template>
        </el-table-column>
      </template>

      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm v-if="!row._isTotal" title="确认删除？"
            @confirm="handleDeleteRow(row.id)">
            <template #reference>
              <el-icon class="delete-icon"><Delete /></el-icon>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <G4AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      :show-conclusion="false"
      v-model:note="auditNote"
      note-title="三、审计说明"
      note-placeholder="填写：（1）重要转回/核销选取标准；（2）与 G4-10/G4-11 勾稽；（3）关联交易核销特别程序；（4）拟调整事项。"
      @update:note="saveAuditNote"
    />
    <div class="conclusion-toolbar no-print">
      <el-select
        v-if="!isReadonly"
        v-model="conclusionOption"
        size="small"
        clearable
        placeholder="参考结论"
        style="width: 220px"
        @change="applyConclusionTemplate"
      >
        <el-option label="A. 未见异常" value="A" />
        <el-option label="B. 个别例外已说明" value="B" />
        <el-option label="C. 重大例外/拟调整" value="C" />
      </el-select>
      <el-button
        size="small"
        type="primary"
        link
        :disabled="isReadonly || !aiAvailable"
        :loading="aiLoading"
        @click="handleAiConclusion"
      >
        🤖 AI生成
      </el-button>
    </div>
    <G4AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      :show-note="false"
      v-model:conclusion="conclusion"
      conclusion-title="四、审计结论"
      conclusion-placeholder="就转回/核销的计价调整是否恰当记录作出结论。"
    />

    <details class="prep-hint" open>
      <summary>编制提示</summary>
      <ul>
        <li>转回金额不得超过收回前累计已计提金额（超出红色高亮；CAS22 转回上限）。</li>
        <li>核销须记录审批程序；关联交易核销须填写合理性分析（闸门）。</li>
        <li>「债权投资的性质」描述标的类型（公司债/信托/贷款等），勿与核销原因混淆。</li>
        <li>转回/核销会计分录可交叉索引
          <span class="chip-wrap inline"><GtIndexChip value="wp:G4-13" :context-project-id="projectId" /></span>；
          金额可勾对
          <span class="chip-wrap inline"><GtIndexChip value="wp:G4-10" :context-project-id="projectId" /></span>。
        </li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * G4TabReversalWriteOff.vue — G4-12 减值准备转回核销检查表（2区段Tab）
 *
 * - el-segmented 切换 Tab1(转回检查) / Tab2(核销检查)
 * - Tab1: 转回金额 > 累计计提 → 红色高亮 + 校验错误信息
 * - Tab2: 关联交易行橙色底色高亮
 * - 各Tab底部合计行
 * - Tab切换行同步（activeRowIndex）
 * - 动态行增删（ElMessageBox.prompt输入单位名称）
 * - GtIndexChip索引列跳转
 */
import { ref, computed, inject, watch, onMounted } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useG4EclReversalWriteOff } from '../../composables/useG4EclReversalWriteOff'
import { useG4EclFormData } from '../../composables/useG4EclFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G4AuditTextCards from '../../g4-bond-investment-main/G4AuditTextCards.vue'
import G4EclImportExportDropdown from '../G4EclImportExportDropdown.vue'
import { useG4EclAiGenerate } from '../../composables/useG4EclAiGenerate'
import {
  buildG412ExceptionDrafts,
  dispatchG4ExceptionDrafts,
} from '../../composables/g4ExceptionRouting'
import {
  G4_ITEM_IDS,
  buildCanonicalPayload,
  parseCanonicalArray,
  parseCanonicalJson,
} from '../../composables/g4StorageContract'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG4EclAiGenerate(wpIdRef)

const rw = useG4EclReversalWriteOff()
const conclusion = ref('')
const conclusionOption = ref('')

const gateAlertTitle = computed(() => {
  const g = rw.gate.value
  const parts: string[] = []
  if (g.invalidReversals) parts.push(`转回超限 ${g.invalidReversals} 行`)
  if (g.relatedPartyWriteOffs) parts.push(`关联交易核销 ${g.relatedPartyWriteOffs} 行（须填合理性分析）`)
  if (g.unreasonableReversals || g.unreasonableWriteOffs) {
    parts.push(`判定不合理 ${(g.unreasonableReversals || 0) + (g.unreasonableWriteOffs || 0)} 行`)
  }
  return parts.length ? `质量闸门待补：${parts.join('；')}` : ''
})

const CONCLUSION_TEMPLATES: Record<string, string> = {
  A: '经检查，本期重要债权投资减值准备转回（收回）与核销事项依据充分、程序合规，转回金额未超过累计已计提金额，未发现需调整事项。债权投资相关计价调整已恰当记录。',
  B: '经检查，除下列事项外，本期重要转回/核销总体合理：【列示例外项目及处理】。其余转回未超累计计提，核销程序合规。请结合索引说明影响。',
  C: '经检查，发现重大例外或需调整事项：【性质、金额、对报表影响及建议调整分录】。在未完成调整前，不能仅依赖本表对计价认定形成无保留结论。',
}

function applyConclusionTemplate(opt: string): void {
  if (!opt || props.isReadonly) return
  const text = CONCLUSION_TEMPLATES[opt]
  if (text) conclusion.value = text
}

// ─── 审计说明（checklist_responses 持久化） ─────────────────────────────────
const formData = useG4EclFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const rowsLoaded = ref(false)
const NOTE_KEY = 'G4-12-reversal-writeoff-audit-note'
const auditNote = ref('')
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  formData.debouncedSave(NOTE_KEY, { remark: val })
}

const CONCLUSION_KEY = 'G4-12-reversal-writeoff-conclusion'
watch(conclusion, (val) => {
  if (props.isReadonly) return
  formData.debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: val })
})

watch(
  [rw.reversals, rw.writeOffs],
  ([reversals, writeOffs]) => {
    if (!rowsLoaded.value || props.isReadonly) return
    const rowsPayload = buildCanonicalPayload(G4_ITEM_IDS.G4_12_ROWS, { reversals, writeOffs })
    const reversalsPayload = buildCanonicalPayload(G4_ITEM_IDS.G4_12_REVERSALS, reversals)
    const writeOffsPayload = buildCanonicalPayload(G4_ITEM_IDS.G4_12_WRITEOFFS, writeOffs)
    formData.debouncedSave(rowsPayload.item_id, rowsPayload)
    // Keep the legacy import/export keys in sync during the migration window.
    formData.debouncedSave(reversalsPayload.item_id, reversalsPayload)
    formData.debouncedSave(writeOffsPayload.item_id, writeOffsPayload)
  },
  { deep: true },
)

// ─── 区段Tab选项 ─────────────────────────────────────────────────────────────

const segmentOptions = [
  { label: '（一）转回（收回）检查', value: 'tab1' },
  { label: '（二）核销检查', value: 'tab2' },
]

// ─── 统一显示行（单表格方案 — 避免Tab切换闪烁） ─────────────────────────────

interface DisplayRow {
  id: string
  seq: number
  unitName: string
  _isTotal?: boolean
  // Tab1 转回字段
  reversalReason?: string
  recoveryMethod?: string
  originalBasis?: string
  reversalAmount?: number
  accumulatedProvision?: number
  // Tab2 核销字段
  writeOffType?: string
  writeOffAmount?: number
  writeOffReason?: string
  writeOffProcedure?: string
  isRelatedParty?: boolean
  // 共用字段
  reasonAnalysis?: string
  isReasonable?: string
  indexRef?: string
}

const activeDisplayRows = computed<DisplayRow[]>(() => {
  if (rw.activeTab.value === 'tab1') {
    const result: DisplayRow[] = [...rw.reversals.value as DisplayRow[]]
    result.push({
      id: '__total__',
      seq: 0,
      unitName: '',
      reversalAmount: rw.reversalSummary.value.totalReversalAmount,
      accumulatedProvision: rw.reversalSummary.value.totalAccumulatedProvision,
      _isTotal: true,
    })
    return result
  } else {
    const result: DisplayRow[] = [...rw.writeOffs.value as DisplayRow[]]
    result.push({
      id: '__total__',
      seq: 0,
      unitName: '',
      writeOffAmount: rw.writeOffSummary.value.totalWriteOffAmount,
      _isTotal: true,
    })
    return result
  }
})

// ─── 行同步（activeRowIndex 跨Tab保持） ─────────────────────────────────────

function onCurrentChange(row: DisplayRow | null) {
  if (!row || row._isTotal) return
  if (rw.activeTab.value === 'tab1') {
    const idx = rw.reversals.value.findIndex(r => r.id === row.id)
    if (idx >= 0) rw.activeRowIndex.value = idx
  } else {
    const idx = rw.writeOffs.value.findIndex(r => r.id === row.id)
    if (idx >= 0) rw.activeRowIndex.value = idx
  }
}

// ─── 行样式（Tab1转回校验红色 / Tab2关联交易橙色） ──────────────────────────

function activeRowClassName({ row }: { row: DisplayRow }): string {
  if (row._isTotal) return 'row-total'
  if (rw.activeTab.value === 'tab1') {
    if (!rw.isRowValid(row as any)) return 'row-invalid'
  } else {
    if (rw.isRelatedPartyRow(row as any)) return 'row-related-party'
  }
  return ''
}

// ─── 统一删除行处理 ─────────────────────────────────────────────────────────

function handleDeleteRow(rowId: string): void {
  if (rw.activeTab.value === 'tab1') {
    rw.removeReversalRow(rowId)
  } else {
    rw.removeWriteOffRow(rowId)
  }
}

// ─── 动态行增删 ─────────────────────────────────────────────────────────────

async function handleAddRow() {
  if (rw.activeTab.value === 'tab1') {
    await rw.addReversalRow()
  } else {
    await rw.addWriteOffRow()
  }
}

function pushExceptionDrafts(): void {
  const drafts = buildG412ExceptionDrafts(
    rw.reversals.value,
    rw.writeOffs.value,
    formData.allResponses.value,
  )
  if (!drafts.length) {
    ElMessage.info('没有可推送的转回或核销例外')
    return
  }
  dispatchG4ExceptionDrafts(drafts, formData.allResponses.value)
  ElMessage.success(`已推送 ${drafts.length} 条 G4-3 草稿行`)
}

// ─── AI生成审计结论 ─────────────────────────────────────────────────────────

async function handleAiConclusion(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'reversal-writeoff-conclusion',
    conclusion.value || '',
    {
      转回行数: rw.reversals.value.length,
      核销行数: rw.writeOffs.value.length,
      转回金额合计: rw.reversalSummary.value.totalReversalAmount,
      核销金额合计: rw.writeOffSummary.value.totalWriteOffAmount,
      转回超限行: rw.gate.value.invalidReversals,
      关联交易核销: rw.gate.value.relatedPartyWriteOffs,
      闸门通过: rw.gate.value.ready,
    },
    'AI 审计结论',
  )
  if (text) conclusion.value = text
}

// ─── 数字格式化 ─────────────────────────────────────────────────────────────

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

// ─── 数据加载 ───────────────────────────────────────────────────────────────

function hydrateFromResponses(): void {
  const canonical = parseCanonicalJson<{
    reversals?: typeof rw.reversals.value
    writeOffs?: typeof rw.writeOffs.value
  }>(formData.allResponses.value.get(G4_ITEM_IDS.G4_12_ROWS))

  if (canonical && typeof canonical === 'object') {
    rw.loadData({
      reversals: Array.isArray(canonical.reversals) ? canonical.reversals : [],
      writeOffs: Array.isArray(canonical.writeOffs) ? canonical.writeOffs : [],
    })
  } else {
    const legacyReversalsResponse = formData.allResponses.value.get(G4_ITEM_IDS.G4_12_REVERSALS)
    const legacyWriteOffsResponse = formData.allResponses.value.get(G4_ITEM_IDS.G4_12_WRITEOFFS)
    const legacyReversals = parseCanonicalArray(legacyReversalsResponse)
    const legacyWriteOffs = parseCanonicalArray(legacyWriteOffsResponse)
    if (legacyReversalsResponse || legacyWriteOffsResponse) {
      rw.loadData({
        reversals: legacyReversals as typeof rw.reversals.value,
        writeOffs: legacyWriteOffs as typeof rw.writeOffs.value,
      })
    } else if (props.htmlData?.reversalWriteOff) {
      const data = props.htmlData.reversalWriteOff
      rw.loadData({
        reversals: data.reversals,
        writeOffs: data.writeOffs,
      })
    }
  }

  if (props.htmlData?.reversalWriteOff) {
    const data = props.htmlData.reversalWriteOff
    if (data.conclusion) conclusion.value = data.conclusion
  }
  const note = formData.allResponses.value.get(NOTE_KEY)
  if (note?.remark) auditNote.value = note.remark
  const conc = formData.allResponses.value.get(CONCLUSION_KEY)
  if (conc?.remark || conc?.conclusion) {
    conclusion.value = conc.remark || conc.conclusion || conclusion.value
  }
  rowsLoaded.value = true
}

async function onImported(): Promise<void> {
  try {
    await formData.loadAll()
  } catch { /* ignore */ }
  rowsLoaded.value = false
  hydrateFromResponses()
  emit('imported')
}

onMounted(async () => {
  await formData.loadAll()
  hydrateFromResponses()
})

// ─── 暴露序列化接口供父组件保存使用 ─────────────────────────────────────────

defineExpose({
  toJSON: () => ({
    ...rw.toJSON(),
    conclusion: conclusion.value,
  }),
})
</script>

<style scoped>
.g4-reversal-writeoff {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
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
  font-weight: 600;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 工具栏索引 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.tab-toolbar .toolbar-left { display: flex; gap: 8px; align-items: center; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }

.conclusion-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  flex-wrap: wrap;
}

/* 表格 */
.reversal-table {
  font-size: var(--wp-font-size, 13px);
}

.compact-num {
  width: 100%;
}

.compact-num :deep(.el-input__inner) {
  text-align: right;
}

/* 转回校验错误：红色高亮行 */
:deep(.row-invalid) {
  background-color: #fef0f0 !important;
}
:deep(.row-invalid td) {
  background-color: #fef0f0 !important;
}

.validation-error {
  color: #f56c6c;
  font-size: 11px;
  margin-top: 2px;
  line-height: 1.2;
}

/* 关联交易行：橙色高亮 */
:deep(.row-related-party) {
  background-color: #fdf6ec !important;
}
:deep(.row-related-party td) {
  background-color: #fdf6ec !important;
}

/* 合计行 */
:deep(.row-total) {
  background-color: #ecf5ff !important;
  font-weight: 700;
}
:deep(.row-total td) {
  background-color: #ecf5ff !important;
}

.total-label {
  color: #409eff;
  font-weight: 700;
}

.total-num {
  font-weight: 700;
  color: #303133;
}

/* 删除图标 */
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}

.conclusion-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.section-label {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.remark-required :deep(.el-textarea__inner) {
  box-shadow: 0 0 0 1px #e6a23c inset;
}

.chip-wrap.inline {
  display: inline-flex;
  vertical-align: middle;
}

/* 编制提示 */
.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
.prep-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.prep-hint ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
.prep-hint li {
  margin-bottom: 4px;
}
</style>
