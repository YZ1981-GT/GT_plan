<template>
  <div class="g2-bad-debt" data-testid="g2-bad-debt">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 结构对齐模板：按单项评估计提 → 信用风险组合计提（按账龄段展开）→ 合计。</p>
        <p>2. 期初审定＝期初未审＋账项调整；期末未审＝期初审定＋计提＋其他增加−转回−转销−其他减少；期末审定＝期末未审＋账项调整。</p>
        <p>3. 组合行随账龄枚举（3年段／5年段／自定义）自动增减；可在 G2-2「同步账龄至各表」统一口径。</p>
        <p>4. ECL 三阶段测算请在 G2-7 完成；本表聚焦坏账准备滚动态与审定勾稽 G2-1。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：确认应收利息坏账准备计提充分、转回/转销恰当，验证期初期末滚动态及单项/组合划分，为 G2-1 审定提供依据。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="sheet-title">G2-3 坏账准备明细表</span>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="bd.addRow('individual')">
          新增单项行
        </el-button>
        <span class="muted">账龄口径</span>
        <el-select
          :model-value="bd.agingPreset.value"
          size="small"
          style="width: 120px"
          :disabled="isReadonly"
          @change="onAgingPresetChange"
        >
          <el-option label="3年段" value="THREE_YEAR" />
          <el-option label="5年段" value="FIVE_YEAR" />
          <el-option label="自定义" value="CUSTOM" />
        </el-select>
        <el-tag size="small" type="info">组合 {{ bd.segments.value.length }} 段</el-tag>
        <el-button size="small" :disabled="isReadonly" @click="bd.syncAgingAcrossSheets()">
          同步账龄至各表
        </el-button>
        <G2ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G2-3"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G2-1" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G2-7" /></span>
        <el-button size="small" @click="openReviewDialog('G2-3-bad-debt')">💬复核</el-button>
      </div>
    </div>

    <el-dialog v-model="showCustomDialog" title="自定义账龄段" width="420px" destroy-on-close>
      <p class="muted">每行一个段名，至少 2 段、最多 10 段。</p>
      <el-input v-model="customInput" type="textarea" :rows="8" placeholder="1年以内&#10;1-2年&#10;2-3年&#10;3年以上" />
      <template #footer>
        <el-button @click="cancelCustomAging">取消</el-button>
        <el-button type="primary" @click="confirmCustomAging">确定</el-button>
      </template>
    </el-dialog>

    <el-table
      :data="bd.dataRows.value"
      border
      size="small"
      max-height="520"
      :row-class-name="rowClassName"
    >
      <el-table-column label="项目" min-width="180" fixed>
        <template #default="{ row }">
          <span v-if="row.kind !== 'leaf'" class="label-strong">{{ row.item }}</span>
          <el-input
            v-else-if="row.category === 'individual'"
            :model-value="row.item"
            size="small"
            :disabled="isReadonly"
            placeholder="单项对象/标的"
            @change="(v: string) => bd.updateCell(row.id, 'item', v)"
          />
          <span v-else>{{ row.item }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期初数" align="center">
        <el-table-column label="未审数" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.openingUnadjusted"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => bd.updateCell(row.id, 'openingUnadjusted', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': row.kind !== 'leaf' }">{{ fmtNum(row.openingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="96" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.openingAdjustment"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => bd.updateCell(row.id, 'openingAdjustment', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': row.kind !== 'leaf' }">{{ fmtNum(row.openingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="期初审定 = 未审 + 账项调整">{{ fmtNum(row.openingAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="本期增加" align="center">
        <el-table-column label="计提" width="96" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.provisionIncrease"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => bd.updateCell(row.id, 'provisionIncrease', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.provisionIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="其他增加" width="96" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.otherIncrease"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => bd.updateCell(row.id, 'otherIncrease', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.otherIncrease) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="本期减少" align="center">
        <el-table-column label="转回" width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.reversal"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => bd.updateCell(row.id, 'reversal', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.reversal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转销" width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.writeOff"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => bd.updateCell(row.id, 'writeOff', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.writeOff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="其他减少" width="96" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.otherDecrease"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => bd.updateCell(row.id, 'otherDecrease', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.otherDecrease) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="期末数" align="center">
        <el-table-column label="未审数" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span
              class="formula-cell"
              title="期末未审 = 期初审定 + 计提 + 其他增加 − 转回 − 转销 − 其他减少"
            >{{ fmtNum(row.closingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="96" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.closingAdjustment"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => bd.updateCell(row.id, 'closingAdjustment', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.closingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="期末审定 = 未审 + 账项调整">{{ fmtNum(row.closingAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="单独计提减值、转回或转销原因" min-width="180">
        <template #default="{ row }">
          <el-input
            v-if="row.editable && !isReadonly"
            :model-value="row.reason"
            size="small"
            placeholder="说明原因"
            @update:model-value="(v: string) => bd.updateCell(row.id, 'reason', v)"
          />
          <span v-else-if="row.reason">{{ row.reason }}</span>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!isReadonly && row.kind === 'leaf' && row.category === 'individual'"
            size="small"
            type="danger"
            link
            @click="bd.removeRow(row.id)"
          >删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals">
      <div class="grand-total">
        <span class="subtotal-label">合计</span>
        期初审定 {{ fmtNum(bd.totals.value.openingAudited) }} ·
        本期净变动 {{ fmtNum(bd.totals.value.periodChange) }} ·
        期末审定 {{ fmtNum(bd.totals.value.closingAudited) }}
      </div>
    </div>

    <G2AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="bad-debt-note"
      conclusion-ai-section="bad-debt-conclusion"
      :related-context="{
        期初审定: bd.totals.value.openingAudited,
        本期计提: bd.totals.value.provisionIncrease,
        本期转回: bd.totals.value.reversal,
        本期转销: bd.totals.value.writeOff,
        期末审定: bd.totals.value.closingAudited,
        账龄口径: bd.agingPreset.value,
        组合段数: bd.segments.value.length,
      }"
      note-placeholder="填写审计说明：（1）单项计提依据；（2）组合账龄与损失率；（3）本期计提/转回/转销原因；（4）与 G2-1 / G2-7 勾稽。"
      note-hint="覆盖滚动态、单项/组合划分、账龄枚举及重大变动原因。"
      conclusion-hint="按 A/B/C 口径评价坏账准备计提充分性与转销恰当性。"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, watch, inject } from 'vue'
import { useG2BadDebtDetail } from '../composables/useG2BadDebtDetail'
import GtIndexChip from '../GtIndexChip.vue'
import G2ImportExportDropdown from './G2ImportExportDropdown.vue'
import G2AuditTextCards from './G2AuditTextCards.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

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

const bd = useG2BadDebtDetail({
  wpId: ref(props.wpId ?? ''),
  projectId: ref(props.projectId ?? ''),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const showCustomDialog = ref(false)
const customInput = ref('')
const lastNonCustomPreset = ref<'THREE_YEAR' | 'FIVE_YEAR'>(
  bd.agingPreset.value === 'CUSTOM' ? 'THREE_YEAR' : (bd.agingPreset.value as 'THREE_YEAR' | 'FIVE_YEAR'),
)

function onAgingPresetChange(val: 'THREE_YEAR' | 'FIVE_YEAR' | 'CUSTOM') {
  if (val === 'CUSTOM') {
    const labels = bd.customSegments.value.length
      ? bd.customSegments.value.map((s) => s.label)
      : bd.segments.value.map((s) => s.label)
    customInput.value = (labels.length ? labels : ['1年以内', '1-2年', '2-3年', '3年以上']).join('\n')
    showCustomDialog.value = true
    return
  }
  lastNonCustomPreset.value = val
  bd.setAgingPreset(val)
}

function confirmCustomAging() {
  const lines = customInput.value.split('\n').map((l) => l.trim()).filter(Boolean).slice(0, 10)
  if (!bd.setAgingPreset('CUSTOM', lines)) return
  showCustomDialog.value = false
}

function cancelCustomAging() {
  showCustomDialog.value = false
  if (!bd.customSegments.value.length && bd.agingPreset.value === 'CUSTOM') {
    bd.setAgingPreset(lastNonCustomPreset.value)
  }
}

function rowClassName({ row }: { row: { kind: string } }) {
  if (row.kind === 'section_header') return 'row-section'
  if (row.kind === 'footer') return 'row-footer'
  return ''
}

function fmtNum(v: unknown): string {
  return typeof v === 'number'
    ? v.toLocaleString(undefined, { maximumFractionDigits: 2 })
    : String(v ?? '')
}

const NOTE_KEY = 'G2-3-audit-note'
const CONCLUSION_KEY = 'G2-3-audit-conclusion'
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
.g2-bad-debt { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g2-bad-debt :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g2-bad-debt :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.muted { color: #909399; font-size: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.label-strong { font-weight: 600; }
:deep(.row-section) { background: #f0f5ff !important; font-weight: 600; }
:deep(.row-footer) { background: #fafafa !important; font-weight: 600; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
</style>
