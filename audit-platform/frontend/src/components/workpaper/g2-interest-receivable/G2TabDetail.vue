<template>
  <div class="g2-detail">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表按投资种类/项目逐笔列示应收利息，完成期初→发生→期末滚动核对，并填列结息日与期后收款情况。</p>
        <p>2. 灰色底纹列为自动计算列：期初审定 = 期初余额 + 期初调整；期末余额 = 期初审定 + 借方 − 贷方；期末审定 = 期末余额 + 账项调整。</p>
        <p>3. 账龄段支持「3年段 / 5年段 / 自定义」枚举切换（对齐 F1-1）；行内「账龄分配」可将审定余额整笔填入指定段。账龄各段之和应等于对应审定数。</p>
        <p>4. 计息核对列（面值/利率/起止日）可选填，便于与 G2-5 利息测算交叉核对；长期挂账衔接 G2-6。</p>
        <p>5. 依据：CAS 22《金融工具确认和计量》；合计与 G2-1 审定表勾稽。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实资产负债表日应收利息的存在、完整与准确，确认计息基础与账龄划分恰当，并关注期后收款及长期挂账。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="sheet-title">G2-2 应收利息明细表</span>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="detail.addRow()">新增行</el-button>
        <span class="muted">账龄口径</span>
        <el-select
          :model-value="agingPresetModel"
          size="small"
          style="width: 110px"
          :disabled="isReadonly"
          @change="onAgingPresetChange"
        >
          <el-option label="3年段" value="THREE_YEAR" />
          <el-option label="5年段" value="FIVE_YEAR" />
          <el-option label="自定义" value="CUSTOM" />
        </el-select>
        <el-button size="small" :disabled="isReadonly" @click="detail.syncAgingAcrossSheets()">
          同步账龄至各表
        </el-button>
        <G2ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G2-2"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G2-1" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G2-5" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G2-6" /></span>
        <el-tag size="small" type="info">共 {{ detail.dataRows.value.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G2-2-detail')">💬复核</el-button>
      </div>
    </div>

    <el-table :data="detail.dataRows.value" border size="small" max-height="520" style="width: 100%">
      <el-table-column label="序号" prop="seq" width="55" align="center" fixed />
      <el-table-column label="投资种类" width="110" fixed>
        <template #default="{ row }">
          <el-input :model-value="row.investType" size="small" :disabled="isReadonly"
            @change="(v: string) => detail.updateCell(row.id, 'investType', v)" />
        </template>
      </el-table-column>
      <el-table-column label="投资项目" width="140" fixed>
        <template #default="{ row }">
          <el-input :model-value="row.investTarget" size="small" :disabled="isReadonly"
            @change="(v: string) => detail.updateCell(row.id, 'investTarget', v)" />
        </template>
      </el-table-column>

      <el-table-column label="期初余额" width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput :model-value="row.openingUnadjusted" size="small" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => detail.updateCell(row.id, 'openingUnadjusted', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="期初调整数" width="110" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.openingAdjustment" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => detail.updateCell(row.id, 'openingAdjustment', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="期初余额审定数" width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="期初审定 = 期初余额 + 期初调整数">{{ fmtNum(row.openingAudited) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期初审定账龄" align="center">
        <el-table-column
          v-for="band in detail.bands.value"
          :key="`prior-${band.key}`"
          :label="band.label"
          width="95"
          align="right"
        >
          <template #default="{ row }">
            <el-input-number
              :model-value="row.agingPrior?.[band.key] ?? 0"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => detail.updateCell(row.id, `agingPrior.${band.key}`, v ?? 0)"
            />
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="借方发生" width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput :model-value="row.debit" size="small" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => detail.updateCell(row.id, 'debit', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="贷方发生" width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput :model-value="row.credit" size="small" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => detail.updateCell(row.id, 'credit', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="期末余额 = 期初审定 + 借方 − 贷方">{{ fmtNum(row.closingUnadjusted) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="账项调整" width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput :model-value="row.closingAdjustment" size="small" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => detail.updateCell(row.id, 'closingAdjustment', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="应收利息余额审定数" width="140" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="期末审定 = 期末余额 + 账项调整">{{ fmtNum(row.closingAudited) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期末审定账龄" align="center">
        <el-table-column
          v-for="band in detail.bands.value"
          :key="`audited-${band.key}`"
          :label="band.label"
          width="95"
          align="right"
        >
          <template #default="{ row }">
            <el-input-number
              :model-value="row.agingAudited?.[band.key] ?? 0"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => detail.updateCell(row.id, `agingAudited.${band.key}`, v ?? 0)"
            />
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="结息日" width="130">
        <template #default="{ row }">
          <el-date-picker :model-value="row.interestDueDate" type="date" size="small" value-format="YYYY-MM-DD"
            :disabled="isReadonly" style="width:100%"
            @update:model-value="(v: string) => detail.updateCell(row.id, 'interestDueDate', v ?? '')" />
        </template>
      </el-table-column>
      <el-table-column label="原计收项目期" width="120">
        <template #default="{ row }">
          <el-input :model-value="row.accrualPeriod" size="small" :disabled="isReadonly"
            @change="(v: string) => detail.updateCell(row.id, 'accrualPeriod', v)" />
        </template>
      </el-table-column>
      <el-table-column label="流通或期后收款情况" width="150">
        <template #default="{ row }">
          <el-input :model-value="row.collectionStatus" size="small" :disabled="isReadonly"
            @change="(v: string) => detail.updateCell(row.id, 'collectionStatus', v)" />
        </template>
      </el-table-column>

      <el-table-column label="账龄分配" width="100" fixed="right">
        <template #default="{ row }">
          <el-dropdown v-if="!isReadonly" size="small" trigger="click">
            <el-button link type="primary" size="small">分配▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>期初→期初审定</el-dropdown-item>
                <el-dropdown-item
                  v-for="band in detail.bands.value"
                  :key="`ap-${band.key}`"
                  @click="detail.allocateAging(row.id, 'prior', band.key)"
                >
                  期初·{{ band.label }}
                </el-dropdown-item>
                <el-dropdown-item divided disabled>期末→期末审定</el-dropdown-item>
                <el-dropdown-item
                  v-for="band in detail.bands.value"
                  :key="`aa-${band.key}`"
                  @click="detail.allocateAging(row.id, 'audited', band.key)"
                >
                  期末·{{ band.label }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <span
            v-if="!detail.isAgingBalanced(row, 'audited')"
            class="aging-warn"
            title="期末账龄合计 ≠ 期末审定"
          >≠</span>
        </template>
      </el-table-column>

      <el-table-column label="减值阶段" width="100">
        <template #default="{ row }">
          <el-select :model-value="row.eclStage" size="small" :disabled="isReadonly"
            @change="(v: string) => detail.updateCell(row.id, 'eclStage', v)">
            <el-option value="Stage1" label="Stage1" />
            <el-option value="Stage2" label="Stage2" />
            <el-option value="Stage3" label="Stage3" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="备注" width="120">
        <template #default="{ row }">
          <el-input :model-value="row.remark" size="small" :disabled="isReadonly"
            @change="(v: string) => detail.updateCell(row.id, 'remark', v)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="detail.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <details class="accrual-details">
      <summary>计息核对列（可选，对接 G2-5）</summary>
      <el-table :data="detail.dataRows.value" border size="small" max-height="280" class="accrual-table">
        <el-table-column label="序号" prop="seq" width="55" align="center" />
        <el-table-column label="投资项目" width="140">
          <template #default="{ row }">{{ row.investTarget || '—' }}</template>
        </el-table-column>
        <el-table-column label="面值/本金" width="120" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.faceValue" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => detail.updateCell(row.id, 'faceValue', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="票面利率(%)" width="110" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.couponRate" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%" :precision="4"
              @update:model-value="(v: number) => detail.updateCell(row.id, 'couponRate', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="计息起始日" width="130">
          <template #default="{ row }">
            <el-date-picker :model-value="row.accrualStart" type="date" size="small" value-format="YYYY-MM-DD"
              :disabled="isReadonly" style="width:100%"
              @update:model-value="(v: string) => detail.updateCell(row.id, 'accrualStart', v ?? '')" />
          </template>
        </el-table-column>
        <el-table-column label="计息截止日" width="130">
          <template #default="{ row }">
            <el-date-picker :model-value="row.accrualEnd" type="date" size="small" value-format="YYYY-MM-DD"
              :disabled="isReadonly" style="width:100%"
              @update:model-value="(v: string) => detail.updateCell(row.id, 'accrualEnd', v ?? '')" />
          </template>
        </el-table-column>
        <el-table-column label="计息天数" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ row.accruedDays }}</span>
          </template>
        </el-table-column>
        <el-table-column label="应计利息" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtNum(row.accruedInterest) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="已收利息" width="110" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.receivedInterest" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => detail.updateCell(row.id, 'receivedInterest', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="测算期末应收" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtNum(row.netReceivable) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </details>

    <div class="totals">
      <div class="grand-total">
        <span class="subtotal-label">合计</span>
        期初审定 {{ fmtNum(detail.totals.value.openingAudited) }} ·
        借方 {{ fmtNum(detail.totals.value.debit) }} ·
        贷方 {{ fmtNum(detail.totals.value.credit) }} ·
        期末审定 {{ fmtNum(detail.totals.value.closingAudited) }}
      </div>
      <div v-if="detail.bands.value.length" class="aging-total">
        期末账龄合计：
        <span v-for="band in detail.bands.value" :key="`t-${band.key}`" class="aging-chip">
          {{ band.label }} {{ fmtNum(detail.totals.value.agingAudited[band.key] ?? 0) }}
        </span>
      </div>
    </div>

    <G2AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="detail-note"
      conclusion-ai-section="detail-conclusion"
      :related-context="{
        明细行数: detail.dataRows.value.length,
        期初审定合计: detail.totals.value.openingAudited,
        期末审定合计: detail.totals.value.closingAudited,
        账龄口径: detail.agingPreset.value,
      }"
      note-placeholder="填写审计说明：（1）明细加计与总账/G2-1勾稽；（2）期初调整与发生额核对；（3）账龄划分及一年以上挂账；（4）结息日与期后收款核查。"
      note-hint="覆盖滚动核对、账龄枚举、结息日/期后收款及与 G2-1 勾稽。"
      conclusion-hint="按 A/B/C 口径表述明细完整性、余额准确性与账龄划分。"
    />

    <el-dialog v-model="showCustomDialog" title="自定义账龄段" width="420px" @close="cancelCustomAging">
      <p class="muted">每行一个账龄段名称（至少 2 段，最多 10 段），与 F1-1 自定义口径一致。</p>
      <el-input v-model="customInput" type="textarea" :rows="6" placeholder="例如：&#10;1年以内&#10;1-2年&#10;2-3年&#10;3年以上" />
      <template #footer>
        <el-button @click="cancelCustomAging">取消</el-button>
        <el-button type="primary" @click="confirmCustomAging">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
import { ref, toRef, computed, watch, inject } from 'vue'
import { useG2Detail } from '../composables/useG2Detail'
import GtIndexChip from '../GtIndexChip.vue'
import G2ImportExportDropdown from './G2ImportExportDropdown.vue'
import G2AuditTextCards from './G2AuditTextCards.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'
import type { AgingPreset } from '@/composables/useAgingConfig'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
  projectId?: string
}>()

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const wpId = computed(() => props.wpId ?? '')
const projectIdRef = computed(() => props.projectId ?? '')

const detail = useG2Detail({
  wpId,
  projectId: projectIdRef,
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const agingPresetModel = computed(() => detail.agingPreset.value)
const showCustomDialog = ref(false)
const customInput = ref('')
const lastNonCustomPreset = ref<AgingPreset>(
  detail.agingPreset.value === 'CUSTOM' ? 'THREE_YEAR' : detail.agingPreset.value,
)

function onAgingPresetChange(val: AgingPreset) {
  if (val === 'CUSTOM') {
    const labels = detail.customSegments.value.length
      ? detail.customSegments.value.map((s) => s.label)
      : detail.bands.value.map((b) => b.label)
    customInput.value = (labels.length ? labels : ['1年以内', '1-2年', '2-3年', '3年以上']).join('\n')
    showCustomDialog.value = true
    return
  }
  lastNonCustomPreset.value = val
  detail.setAgingPreset(val)
}

function confirmCustomAging() {
  const lines = customInput.value.split('\n').map((l) => l.trim()).filter(Boolean)
  if (lines.length > 10) {
    customInput.value = lines.slice(0, 10).join('\n')
  }
  if (!detail.setAgingPreset('CUSTOM', lines.slice(0, 10))) return
  showCustomDialog.value = false
}

function cancelCustomAging() {
  showCustomDialog.value = false
  if (!detail.customSegments.value.length && detail.agingPreset.value !== 'CUSTOM') {
    /* keep current */
  } else if (!detail.customSegments.value.length) {
    detail.setAgingPreset(lastNonCustomPreset.value)
  }
}

function fmtNum(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(v ?? '')
}

const NOTE_KEY = 'G2-2-audit-note'
const CONCLUSION_KEY = 'G2-2-audit-conclusion'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(CONCLUSION_KEY)?.remark ?? '')

watch(() => props.allResponses.get(NOTE_KEY)?.remark, (v) => { if (v != null) auditNote.value = v })
watch(() => props.allResponses.get(CONCLUSION_KEY)?.remark, (v) => { if (v != null) auditConclusion.value = v })
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: v })
})
</script>

<style scoped>
.g2-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g2-detail :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g2-detail :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.muted { color: #909399; font-size: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.aging-warn { color: #f56c6c; margin-left: 4px; font-weight: 700; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
.aging-total { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.aging-chip { background: #f4f4f5; padding: 2px 8px; border-radius: 4px; }
.accrual-details { margin-top: 12px; border: 1px solid #ebeef5; border-radius: 4px; padding: 8px 12px; }
.accrual-details summary { cursor: pointer; color: #606266; font-size: 13px; font-weight: 500; }
.accrual-table { margin-top: 8px; }
</style>
