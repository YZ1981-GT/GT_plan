<template>
  <div class="g2-ecl-calc" data-testid="g2-ecl-calc">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表对齐 Excel「应收利息坏账准备测算表 G2-7」：分（一）单项计提、（二）账龄组合、（三）其他组合。</p>
        <p>2. 灰色底纹列为自动计算：应计提③ = 审定余额① × 损失率②；差异⑤ = 应计提③ − 账面坏账准备④。</p>
        <p>3. 账龄段支持「3年段 / 5年段 / 自定义」枚举（默认 5 年段，对齐模板）；切换后各组合账龄行自动同步。</p>
        <p>4. 差异可推送至 G2-4；可回填 G2-3 本期计提（默认差异，可选应计提全额）。</p>
        <p>5. 依据：CAS 22 预期信用损失模型；账龄以记账凭证日期起算，逾期则考虑信用期。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：独立测算应收利息坏账准备（单项/账龄组合/其他组合），验证企业计提充分性，确认与 G2-3、G2-4、G2-1 勾稽一致。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="sheet-title">G2-7 坏账准备测算</span>
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
        <el-tag size="small" type="info">{{ ecl.segments.value.length }} 段</el-tag>
        <el-button size="small" :disabled="isReadonly" @click="ecl.syncAgingAcrossSheets()">
          同步账龄至各表
        </el-button>
        <el-button
          size="small"
          type="warning"
          :disabled="isReadonly || Math.abs(ecl.grandTotal.value.totalDiff) < 0.01"
          @click="onPushDiffs"
        >
          推送差异至 G2-4
        </el-button>
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="onPushProvision"
        >
          回填 G2-3（差异/应计提）
        </el-button>
      </div>
      <div class="toolbar-right">
        <G2ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G2-7"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:G2-3" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G2-4" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G2-1" /></span>
        <el-button size="small" @click="openReviewDialog('G2-7-ecl-calc')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      v-if="ecl.diffAlert.value"
      type="warning"
      :closable="false"
      show-icon
      :title="ecl.diffAlert.value"
      style="margin-bottom: 10px"
    />

    <!-- (一) 单项计提 -->
    <div class="ecl-block">
      <div class="block-header">
        <h4 class="block-title">（一）单项计提坏账准备</h4>
        <el-button v-if="!isReadonly" size="small" type="primary" @click="ecl.addSingleRow()">添加标的</el-button>
      </div>
      <el-table :data="ecl.singleRows.value" size="small" border stripe>
        <el-table-column label="投资标的/债务人" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.investTarget" size="small"
              @change="(v: string) => ecl.updateSingleCell(row.rowId, 'investTarget', v)" />
            <span v-else>{{ row.investTarget || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定余额①" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.auditedBalance" :controls="false" size="small" style="width:100%"
              @update:model-value="(v: number) => ecl.updateSingleCell(row.rowId, 'auditedBalance', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.auditedBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="损失率②" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.lossRate" :controls="false" :step="0.01" :max="1" size="small" style="width:100%"
              @update:model-value="(v: number) => ecl.updateSingleCell(row.rowId, 'lossRate', v ?? 0)" />
            <span v-else>{{ fmtPct(row.lossRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="应计提③" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.expectedProvision) }}</span></template>
        </el-table-column>
        <el-table-column label="账面准备④" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.bookBalance" :controls="false" size="small" style="width:100%"
              @update:model-value="(v: number) => ecl.updateSingleCell(row.rowId, 'bookBalance', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.bookBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异⑤" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'diff-warn': Math.abs(row.difference) >= 0.01 }]">{{ fmtAmt(row.difference) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计提依据" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.basis" size="small"
              @change="(v: string) => ecl.updateSingleCell(row.rowId, 'basis', v)" />
            <span v-else>{{ row.basis || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small"
              @change="(v: string) => ecl.updateSingleCell(row.rowId, 'indexRef', v)" />
            <span v-else>{{ row.indexRef || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }">
            <el-button type="danger" text size="small" @click="ecl.removeSingleRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="subtotal-line">
        单项小计 — 应计提 {{ fmtAmt(ecl.singleTotal.value.provision) }}，账面 {{ fmtAmt(ecl.singleTotal.value.book) }}，差异 {{ fmtAmt(ecl.singleTotal.value.diff) }}
      </div>
    </div>

    <!-- (二) 账龄组合 -->
    <div class="ecl-block">
      <div class="block-header">
        <h4 class="block-title">（二）账龄组合计提坏账准备</h4>
        <el-button v-if="!isReadonly" size="small" type="primary" @click="ecl.addAgingGroup()">添加组合</el-button>
      </div>
      <p class="aging-hint">账龄【以记账凭证日期起计算，逾期则考虑信用期】</p>

      <div v-for="(group, gIdx) in ecl.agingGroups.value" :key="group.groupId" class="aging-group">
        <div class="group-header">
          <el-input
            v-if="!isReadonly"
            :model-value="group.groupName"
            size="small"
            placeholder="组合名称"
            style="width:180px"
            @change="(v: string) => ecl.updateGroupName(group.groupId, v)"
          />
          <span v-else class="group-name">{{ group.groupName || `组合${gIdx + 1}` }}</span>
          <el-button v-if="!isReadonly" type="danger" text size="small" @click="ecl.removeAgingGroup(group.groupId)">删除组合</el-button>
        </div>
        <el-table :data="group.rows.filter((r: any) => !r.archived)" size="small" border stripe>
          <el-table-column prop="agingBand" label="账龄" width="160" />
          <el-table-column label="审定余额①" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.auditedBalance" :controls="false" size="small" style="width:100%"
                @update:model-value="(v: number) => ecl.updateAgingCell(group.groupId, row.rowId, 'auditedBalance', v ?? 0)" />
              <span v-else>{{ fmtAmt(row.auditedBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="损失率②" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.lossRate" :controls="false" :step="0.01" :max="1" size="small" style="width:100%"
                @update:model-value="(v: number) => ecl.updateAgingCell(group.groupId, row.rowId, 'lossRate', v ?? 0)" />
              <span v-else>{{ fmtPct(row.lossRate) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="应计提③" width="120" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.expectedProvision) }}</span></template>
          </el-table-column>
          <el-table-column label="账面准备④" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.bookBalance" :controls="false" size="small" style="width:100%"
                @update:model-value="(v: number) => ecl.updateAgingCell(group.groupId, row.rowId, 'bookBalance', v ?? 0)" />
              <span v-else>{{ fmtAmt(row.bookBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异⑤" width="110" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span :class="['formula-cell', { 'diff-warn': Math.abs(row.difference) >= 0.01 }]">{{ fmtAmt(row.difference) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计提依据" min-width="120">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.basis" size="small"
                @change="(v: string) => ecl.updateAgingCell(group.groupId, row.rowId, 'basis', v)" />
              <span v-else>{{ row.basis || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="索引" width="80">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small"
                @change="(v: string) => ecl.updateAgingCell(group.groupId, row.rowId, 'indexRef', v)" />
              <span v-else>{{ row.indexRef || '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div class="subtotal-line">
          组合小计 — 应计提 {{ fmtAmt(ecl.agingGroupTotals.value[gIdx]?.provision) }}，
          账面 {{ fmtAmt(ecl.agingGroupTotals.value[gIdx]?.book) }}，
          差异 {{ fmtAmt(ecl.agingGroupTotals.value[gIdx]?.diff) }}
        </div>
      </div>
    </div>

    <!-- (三) 其他组合 -->
    <div class="ecl-block">
      <div class="block-header">
        <h4 class="block-title">（三）其他组合计提坏账准备</h4>
        <el-button v-if="!isReadonly" size="small" type="primary" @click="ecl.addOtherRow()">添加行</el-button>
      </div>
      <el-table :data="ecl.otherRows.value" size="small" border stripe>
        <el-table-column label="组合名称" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.groupName" size="small"
              @change="(v: string) => ecl.updateOtherCell(row.rowId, 'groupName', v)" />
            <span v-else>{{ row.groupName || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定余额①" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.auditedBalance" :controls="false" size="small" style="width:100%"
              @update:model-value="(v: number) => ecl.updateOtherCell(row.rowId, 'auditedBalance', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.auditedBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="损失率②" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.lossRate" :controls="false" :step="0.01" :max="1" size="small" style="width:100%"
              @update:model-value="(v: number) => ecl.updateOtherCell(row.rowId, 'lossRate', v ?? 0)" />
            <span v-else>{{ fmtPct(row.lossRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="应计提③" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.expectedProvision) }}</span></template>
        </el-table-column>
        <el-table-column label="账面准备④" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.bookBalance" :controls="false" size="small" style="width:100%"
              @update:model-value="(v: number) => ecl.updateOtherCell(row.rowId, 'bookBalance', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.bookBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异⑤" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'diff-warn': Math.abs(row.difference) >= 0.01 }]">{{ fmtAmt(row.difference) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计提依据" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.basis" size="small"
              @change="(v: string) => ecl.updateOtherCell(row.rowId, 'basis', v)" />
            <span v-else>{{ row.basis || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }">
            <el-button type="danger" text size="small" @click="ecl.removeOtherRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="subtotal-line">
        其他组合小计 — 应计提 {{ fmtAmt(ecl.otherTotal.value.provision) }}，账面 {{ fmtAmt(ecl.otherTotal.value.book) }}，差异 {{ fmtAmt(ecl.otherTotal.value.diff) }}
      </div>
    </div>

    <div class="grand-total">
      <span>合计应计提 <strong>{{ fmtAmt(ecl.grandTotal.value.expectedProvision) }}</strong></span>
      <span>合计账面 <strong>{{ fmtAmt(ecl.grandTotal.value.bookBalance) }}</strong></span>
      <span>总差异 <strong :class="{ 'diff-warn': Math.abs(ecl.grandTotal.value.totalDiff) >= 0.01 }">{{ fmtAmt(ecl.grandTotal.value.totalDiff) }}</strong></span>
    </div>

    <div class="method-note">
      <p><strong>编制说明（非打印）：</strong>预期信用损失应基于概率加权、货币时间价值及合理前瞻信息计量；
      可按金融工具类型、信用风险评级、担保物类型、行业、地域等信用风险特征划分组合。
      已发生信用减值的金融资产应单项评估。</p>
    </div>

    <G2AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="ecl-note"
      conclusion-ai-section="ecl-conclusion"
      :related-context="{
        账龄口径: ecl.agingPreset.value,
        账龄段数: ecl.segments.value.length,
        应计提合计: ecl.grandTotal.value.expectedProvision,
        账面合计: ecl.grandTotal.value.bookBalance,
        总差异: ecl.grandTotal.value.totalDiff,
      }"
      note-placeholder="填写审计说明：（1）单项计提判断；（2）账龄组合与损失率依据；（3）测算与账面差异及拟调整；（4）与 G2-3/G2-4 勾稽。"
      note-hint="覆盖 ECL 模型参数、账龄枚举与差异处理。"
      conclusion-hint="按 A/B/C 口径评价坏账准备计提充分性。"
    />

    <el-dialog v-model="showCustomDialog" title="自定义账龄段" width="420px" @close="cancelCustomAging">
      <p class="muted">每行一个账龄段名称（至少 2 段，最多 10 段），与 F1-1 / G2-2 自定义口径一致。</p>
      <el-input v-model="customInput" type="textarea" :rows="6" placeholder="例如：&#10;1年以内/未逾期&#10;1-2年/逾期30天以内&#10;…" />
      <template #footer>
        <el-button @click="cancelCustomAging">取消</el-button>
        <el-button type="primary" @click="confirmCustomAging">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useG2ECLCalc } from '../composables/useG2ECLCalc'
import type { ChecklistResponse } from '../composables/useF1FormData'
import type { AgingPreset } from '@/composables/useAgingConfig'
import GtIndexChip from '../GtIndexChip.vue'
import G2ImportExportDropdown from './G2ImportExportDropdown.vue'
import G2AuditTextCards from './G2AuditTextCards.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
  projectId?: string
}>()

const emit = defineEmits<{ imported: [] }>()

const wpId = computed(() => props.wpId ?? '')
const projectIdRef = computed(() => props.projectId ?? '')
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const ecl = useG2ECLCalc({
  wpId,
  projectId: projectIdRef,
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const agingPresetModel = computed(() => ecl.agingPreset.value)
const showCustomDialog = ref(false)
const customInput = ref('')
const lastNonCustomPreset = ref<AgingPreset>(
  ecl.agingPreset.value === 'CUSTOM' ? 'FIVE_YEAR' : ecl.agingPreset.value,
)

function onAgingPresetChange(val: AgingPreset) {
  if (val === 'CUSTOM') {
    const labels = ecl.customSegments.value.length
      ? ecl.customSegments.value.map((s) => s.label)
      : ecl.segments.value.map((s) => s.label)
    customInput.value = (labels.length ? labels : ['1年以内', '1-2年', '2-3年', '3年以上']).join('\n')
    showCustomDialog.value = true
    return
  }
  lastNonCustomPreset.value = val
  ecl.setAgingPreset(val)
}

function confirmCustomAging() {
  const lines = customInput.value.split('\n').map((l) => l.trim()).filter(Boolean).slice(0, 10)
  if (!ecl.setAgingPreset('CUSTOM', lines)) return
  showCustomDialog.value = false
}

function cancelCustomAging() {
  showCustomDialog.value = false
  if (!ecl.customSegments.value.length && ecl.agingPreset.value === 'CUSTOM') {
    ecl.setAgingPreset(lastNonCustomPreset.value)
  }
}

function onPushDiffs() {
  const n = ecl.pushDiffsToG24()
  if (n > 0) ElMessage.success(`已推送 ${n} 笔差异至 G2-4`)
}

async function onPushProvision() {
  try {
    await ElMessageBox.confirm(
      '默认回填「差异」（应计提−账面）至 G2-3 本期计提，避免覆盖滚动态期初。亦可改为回填应计提全额。',
      '回填 G2-3',
      {
        distinguishCancelAndClose: true,
        confirmButtonText: '回填差异（推荐）',
        cancelButtonText: '回填应计提全额',
        type: 'info',
      },
    )
    const r = ecl.pushProvisionToG23('difference')
    if (r.individual + r.portfolio === 0) return
    ElMessage.success(`已回填差异至 G2-3：单项 ${r.individual} 行、组合 ${r.portfolio} 段`)
  } catch (action) {
    if (action === 'cancel') {
      const r = ecl.pushProvisionToG23('expected')
      if (r.individual + r.portfolio === 0) return
      ElMessage.success(`已回填应计提至 G2-3：单项 ${r.individual} 行、组合 ${r.portfolio} 段`)
    }
  }
}

async function onImported() {
  emit('imported')
  // 等待父级 loadAll 完成后再从扁平表还原三区段
  await new Promise((r) => setTimeout(r, 400))
  ecl.hydrateFromFlat(props.allResponses.get('G2-7-flat-export')?.remark)
}

function fmtAmt(n: number | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—'
  if (!n) return '—'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPct(n: number): string {
  if (!n) return '—'
  return `${(n * 100).toFixed(2)}%`
}

const NOTE_KEY = 'G2-7-audit-note'
const CONCLUSION_KEY = 'G2-7-audit-conclusion'
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
.g2-ecl-calc { padding: 12px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 10px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 10px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.sheet-title { font-size: 15px; font-weight: 600; }
.muted { color: #909399; font-size: 12px; }
.chip-wrap { display: inline-flex; }
.ecl-block { margin-bottom: 16px; }
.block-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.block-title { margin: 0; font-size: 14px; font-weight: 600; color: #303133; }
.aging-hint { font-size: 12px; color: #909399; margin: 0 0 8px; }
.aging-group { margin-bottom: 12px; padding: 8px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; }
.group-header { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.group-name { font-weight: 600; }
.subtotal-line { margin-top: 6px; font-size: 12px; color: #606266; }
.grand-total {
  display: flex; gap: 20px; flex-wrap: wrap; padding: 10px 12px; margin: 12px 0;
  background: #f8f9fb; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px;
}
.formula-cell { border-bottom: 1px dashed #909399; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.diff-warn { color: #e6a23c; font-weight: 600; }
.method-note { margin: 12px 0; padding: 10px; background: #fdf6ec; border-radius: 4px; font-size: 12px; color: #a67c00; line-height: 1.6; }
.method-note p { margin: 0; }
</style>
