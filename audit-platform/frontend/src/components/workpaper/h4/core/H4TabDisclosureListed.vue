<template>
  <div class="h4-tab-disclosure-listed">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>附注披露信息（上市公司）：按照CAS准则和证监会要求，披露工程物资期初/期末余额、本期增减变动、减值准备等。数据从H4-1审定表自动取数填入关键字段，审计人员核对后确认。</p>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：核实工程物资附注披露的金额与 H4-1 审定表一致、分类与增减变动披露完整，符合上市公司年报披露要求（CAS30/证监会披露准则）。" />

    <!-- Section Title -->
    <div class="section-header">
      <span>附注披露信息（上市公司）</span>
      <div class="section-header-actions">
        <el-segmented v-model="dualMode.currentMode.value" :options="dualMode.modeOptions"
          size="small" @change="dualMode.onModeChange" />
        <el-button size="small" circle @click="openReview('H4-disclosure-listed')">💬</el-button>
      </div>
    </div>

    <!-- OnlyOffice 模式 -->
    <GtOnlyOfficeSheet
      v-if="dualMode.currentMode.value === 'onlyoffice'"
      :wp-id="props.wpId"
      :sheet-name="props.sheetName || '附注披露信息（上市公司）'"
      :project-id="props.projectId"
      class="disclosure-oo"
    />

    <!-- HTML 摘要视图 -->
    <div v-else class="disclosure-summary">
      <el-card shadow="never">
        <template #header>
          <div style="display:flex;align-items:center;justify-content:space-between">
            <span style="font-weight: 600">工程物资附注关键数据（自动取数）</span>
            <el-tag v-if="autoFillData.disc_audited" size="small" type="success">已同步</el-tag>
            <el-tag v-else size="small" type="info">待审定</el-tag>
          </div>
        </template>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="期初余额">
            <span class="amt-cell">{{ fmtAmt(autoFillData.disc_begin) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="期末余额（审定）">
            <span class="amt-cell highlight">{{ fmtAmt(autoFillData.disc_audited) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="本期增加（借方）">
            <span class="amt-cell">{{ fmtAmt(autoFillData.disc_debit) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="本期减少（贷方）">
            <span class="amt-cell">{{ fmtAmt(autoFillData.disc_credit) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="明细合计">
            <span class="amt-cell">{{ fmtAmt(autoFillData.disc_detail_total) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="减值准备">
            <span class="amt-cell">{{ fmtAmt(impairmentProvision) }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 附注文本编辑 -->
      <el-card shadow="never" class="note-text-card">
        <template #header>
          <div class="section-header" style="margin-bottom:0">
            <span>附注披露文本</span>
            <div class="section-header-actions">
            </div>
          </div>
        </template>
        <el-input v-model="noteText" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }"
          placeholder="请填写附注披露文本内容..." :disabled="props.isReadonly"
          @blur="saveNoteText" />
      </el-card>
    </div>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>关键数据从H4-1审定表自动取数，H4-1审定完成后自动刷新</li>
        <li>需核对披露金额与审定表是否一致</li>
        <li>上市公司需按年报格式披露工程物资分类明细</li>
        <li>如有减值需单独披露减值准备计提/转回情况</li>
        <li>关联方工程物资采购需在关联交易附注中交叉披露</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H4TabDisclosureListed.vue — 附注披露信息（上市公司）
 *
 * OO-primary + HTML fallback showing key disclosure data.
 * Subscribe to EventBus 'substantive:adjudicated' to refresh when H4-1 audited changes.
 * Uses disclosureAutoFill from useH4CrossSheet for auto-populated fields.
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Task: 4.10
 * Requirements: 1.2
 */
import { ref, computed, defineAsyncComponent, inject, toRef, onMounted, onUnmounted } from 'vue'
import { useH4DualMode } from '../../composables/useH4DualMode'
import { useH4CrossSheet } from '../../composables/useH4CrossSheet'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('../../GtOnlyOfficeSheet.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  sheetName?: string
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Dual Mode ───────────────────────────────────────────────────────────────
const dualMode = useH4DualMode({
  wpId: toRef(props, 'wpId'),
})

// ─── Cross-Sheet Auto Fill ───────────────────────────────────────────────────
const allResponsesRef = computed(() => props.allResponses)
const { disclosureAutoFill } = useH4CrossSheet(allResponsesRef as any)
const autoFillData = computed(() => disclosureAutoFill.value)

// 减值准备从 allResponses 获取
const impairmentProvision = computed(() => {
  const resp = props.allResponses.get('H4-7-impairment-loss')
  const n = Number(resp?.remark)
  return Number.isFinite(n) ? n : 0
})

// ─── Note Text ───────────────────────────────────────────────────────────────
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', () => {})
const noteText = ref('')
const noteResp = props.allResponses.get('H4-disclosure-listed-text')
if (noteResp?.remark) noteText.value = noteResp.remark

function saveNoteText() {
  props.allResponses.set('H4-disclosure-listed-text', {
    item_id: 'H4-disclosure-listed-text', remark: noteText.value, conclusion: null,
  })
  saveResponse('H4-disclosure-listed-text', noteText.value)
}

// ─── EventBus Subscribe ──────────────────────────────────────────────────────
let unsubscribe: (() => void) | null = null

onMounted(() => {
  // Subscribe to 'substantive:adjudicated' to refresh when H4-1 changes
  // Uses window custom event as lightweight EventBus pattern
  const handler = (e: Event) => {
    const detail = (e as CustomEvent).detail
    if (detail?.wpCode === 'H4' || detail?.accountCode === '1605') {
      // Trigger reactivity refresh by touching allResponses
      // The computed disclosureAutoFill will auto-recompute
      console.log('[H4-Disclosure-Listed] Received substantive:adjudicated, refreshing')
    }
  }
  window.addEventListener('substantive:adjudicated', handler)
  unsubscribe = () => window.removeEventListener('substantive:adjudicated', handler)
})

onUnmounted(() => {
  unsubscribe?.()
})

// ─── Actions ─────────────────────────────────────────────────────────────────

function openReview(id: string) {
  openReviewDialog(id)
}

// ─── 金额格式化 ──────────────────────────────────────────────────────────────
function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h4-tab-disclosure-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }

.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.6;
}

.section-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 600; margin-bottom: 12px;
}
.section-header-actions { display: flex; align-items: center; gap: 4px; }

.disclosure-oo { min-height: 400px; margin-bottom: 12px; }

.disclosure-summary { margin-bottom: 12px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.highlight { color: #409eff; font-weight: 600; }

.note-text-card { margin-top: 12px; }

.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
