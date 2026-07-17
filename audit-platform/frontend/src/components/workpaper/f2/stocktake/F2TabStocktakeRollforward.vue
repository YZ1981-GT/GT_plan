<template>
  <div class="f2-roll">
    <header class="rf-hero">
      <div class="rf-hero-main">
        <div class="rf-kicker">F2-26 · 时点调节</div>
        <h2 class="rf-title">存货盘点倒轧表</h2>
        <p class="rf-objective">
          将监盘日实存数量调节至资产负债表日，与截止日账面比对；
          盘点日晚于截止日用「日后倒推」，早于截止日用「日前顺推」。
        </p>
      </div>
      <div class="rf-hero-actions">
        <GtIndexChip value="wp:F2-26" :context-project-id="projectId" />
        <F2SheetToolbar
          v-if="wpId"
          :wp-id="wpId"
          :project-id="projectId"
          api-prefix="f2-st"
          sheet="F2-26"
          :disabled="isReadonly"
          :show-import-export="true"
          ai-section="stocktake-rollforward"
          :existing-content="auditConclusion"
          :related-context="{
            afterVariance: afterVarianceCount,
            beforeVariance: beforeVarianceCount,
            suggestedMode,
            afterVarianceSummary: aiContext.afterVarianceSummary,
            beforeVarianceSummary: aiContext.beforeVarianceSummary,
          }"
          ai-title="AI 生成 · 审计结论"
          review-section="F2-26-conclusion"
          @ai-filled="(t: string) => saveAuditConclusion(t)"
        />
      </div>
    </header>

    <details class="rf-guide">
      <summary>编制提示</summary>
      <ol>
        <li>仅当监盘日 ≠ 资产负债表日时填本表；相同时可在说明中注明「不适用」。</li>
        <li>（一）日后盘点：D = A + 发出 − 入库（从盘点日倒推至截止日）。</li>
        <li>（二）日前盘点：D = A + 入库 − 发出（从盘点日顺推至截止日）。</li>
        <li>数量差异 F = D − E；金额差异 G ≈ F × 单价。有差异须填原因并判断是否调整。</li>
        <li>期间收发应抽查入库单/出库单，可作附件或 OCR 填入。</li>
      </ol>
    </details>

    <div v-if="suggestedMode" class="rf-mode-hint" :class="suggestedMode">
      <template v-if="suggestedMode === 'after'">
        根据日期：盘点日晚于截止日 → 建议填写<strong>第一节（日后倒推）</strong>
      </template>
      <template v-else>
        根据日期：盘点日早于截止日 → 建议填写<strong>第二节（日前顺推）</strong>
      </template>
    </div>
    <div v-else-if="datesEqual" class="rf-mode-hint same">
      盘点日与截止日相同，本表通常不适用；若仍有调节事项请在审计说明中说明。
    </div>

    <F2StocktakeSheetAttachments
      v-if="wpId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-code="F2-26"
    />

    <section v-for="group in F2_26_LAYOUT" :key="group.id" class="rf-card">
      <header class="rf-card-head">
        <div>
          <h3>{{ group.title }}</h3>
          <p v-if="group.subtitle">{{ group.subtitle }}</p>
        </div>
        <el-button
          v-if="group.id === 'meta' && wpId && !isReadonly"
          size="small"
          plain
          @click="seedFromPlan"
        >从计划/小结带入</el-button>
      </header>
      <div
        class="rf-card-grid"
        :style="{ gridTemplateColumns: `repeat(${group.cols}, minmax(0, 1fr))` }"
      >
        <div
          v-for="fid in group.fieldIds"
          :key="fid"
          class="rf-field"
          :class="{ span2: group.cols === 1 || fid === 'method' }"
        >
          <div class="rf-field-label">
            <span>{{ fieldMap[fid]?.label || fid }}</span>
            <button
              v-if="wpId && !isReadonly && !fieldMap[fid]?.date"
              type="button"
              class="ai-chip"
              :disabled="!aiAvailable || aiLoadingId === fid"
              :title="`AI 起草「${fieldMap[fid]?.label || fid}」`"
              :aria-label="`AI 起草${fieldMap[fid]?.label || fid}`"
              @click="aiFillField(fid, fieldMap[fid]?.label || fid)"
            >
              {{ aiLoadingId === fid ? '…' : 'AI' }}
            </button>
          </div>
          <el-date-picker
            v-if="fieldMap[fid]?.date"
            :model-value="toPickerDate(meta.fields.value[fid])"
            type="date"
            value-format="YYYY-MM-DD"
            format="YYYY年MM月DD日"
            :placeholder="fieldMap[fid]?.hint || '选择日期'"
            :disabled="isReadonly"
            style="width: 100%"
            @update:model-value="(v: string | null) => meta.updateField(fid, v || '')"
          />
          <el-input
            v-else-if="fieldMap[fid]?.multiline"
            :model-value="meta.fields.value[fid] || ''"
            type="textarea"
            :rows="fieldMap[fid]?.rows || 2"
            :placeholder="fieldMap[fid]?.hint || ''"
            :disabled="isReadonly"
            resize="vertical"
            @update:model-value="(v: string) => meta.updateField(fid, v)"
          />
          <el-input
            v-else
            :model-value="meta.fields.value[fid] || ''"
            :placeholder="fieldMap[fid]?.hint || ''"
            :disabled="isReadonly"
            @update:model-value="(v: string) => meta.updateField(fid, v)"
          />
        </div>
      </div>
    </section>

    <section class="rf-card" :class="{ recommended: suggestedMode === 'after' }">
      <header class="rf-card-head">
        <div>
          <h3>一、资产负债表日后盘点倒轧（倒推）</h3>
          <p>D = A + 发出 − 入库 · 盘点日晚于截止日时填写</p>
        </div>
        <div class="rf-card-actions">
          <el-tag v-if="afterVarianceCount > 0" size="small" type="danger">{{ afterVarianceCount }} 行差异</el-tag>
          <el-tag v-else-if="afterSheet.rows.value.length" size="small" type="success">核对一致</el-tag>
          <el-button size="small" :disabled="isReadonly" @click="pullBookRows('after', 'F2-24')">从 F2-24 带入</el-button>
          <el-button size="small" :disabled="isReadonly" @click="pullBookRows('after', 'F2-25')">从 F2-25 带入</el-button>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="afterSheet.addRow()">+ 明细行</el-button>
        </div>
      </header>
      <div class="rf-card-body">
        <el-empty
          v-if="!afterSheet.rows.value.length"
          description="暂无明细；可新增或从 F2-24/25 带入账面品名"
          :image-size="64"
        />
        <F2RollTable
          v-else
          mode="after"
          :rows="afterEnriched"
          :is-readonly="isReadonly"
          :wp-id="wpId"
          :ocr-loading-id="ocrLoadingId"
          @update="(id, patch) => afterSheet.updateRow(id, patch)"
          @remove="(id) => afterSheet.removeRow(id)"
          @ocr="(id, file) => onOcr(id, file, afterSheet)"
        />
      </div>
    </section>

    <section class="rf-card" :class="{ recommended: suggestedMode === 'before' }">
      <header class="rf-card-head">
        <div>
          <h3>二、资产负债表日前盘点倒轧（顺推）</h3>
          <p>D = A + 入库 − 发出 · 盘点日早于截止日时填写</p>
        </div>
        <div class="rf-card-actions">
          <el-tag v-if="beforeVarianceCount > 0" size="small" type="danger">{{ beforeVarianceCount }} 行差异</el-tag>
          <el-tag v-else-if="beforeSheet.rows.value.length" size="small" type="success">核对一致</el-tag>
          <el-button size="small" :disabled="isReadonly" @click="pullBookRows('before', 'F2-24')">从 F2-24 带入</el-button>
          <el-button size="small" :disabled="isReadonly" @click="pullBookRows('before', 'F2-25')">从 F2-25 带入</el-button>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="beforeSheet.addRow()">+ 明细行</el-button>
        </div>
      </header>
      <div class="rf-card-body">
        <el-empty
          v-if="!beforeSheet.rows.value.length"
          description="暂无明细；可新增或从 F2-24/25 带入账面品名"
          :image-size="64"
        />
        <F2RollTable
          v-else
          mode="before"
          :rows="beforeEnriched"
          :is-readonly="isReadonly"
          :wp-id="wpId"
          :ocr-loading-id="ocrLoadingId"
          @update="(id, patch) => beforeSheet.updateRow(id, patch)"
          @remove="(id) => beforeSheet.removeRow(id)"
          @ocr="(id, file) => onOcr(id, file, beforeSheet)"
        />
      </div>
    </section>

    <section class="rf-card rf-card-conclusion">
      <header class="rf-card-head">
        <div>
          <h3>三、审计说明</h3>
          <p>调节方向、收发核实、差异处理</p>
        </div>
        <button
          v-if="wpId && !isReadonly"
          type="button"
          class="ai-chip"
          :disabled="!aiAvailable || aiLoadingId === '__note__'"
          title="AI 起草审计说明"
          aria-label="AI 起草审计说明"
          @click="aiFillNote"
        >
          {{ aiLoadingId === '__note__' ? '…' : 'AI' }}
        </button>
      </header>
      <el-input
        v-model="beforeSheet.auditNote.value"
        type="textarea"
        :rows="4"
        :disabled="isReadonly"
        placeholder="填写审计说明…"
        resize="vertical"
      />
    </section>

    <section class="rf-card rf-card-conclusion">
      <header class="rf-card-head">
        <div>
          <h3>四、审计结论</h3>
          <p>A 未见异常 · B 除重大不符应调整外其余未见异常 · C 重大未调整或范围受限不可确认</p>
        </div>
        <button
          v-if="wpId && !isReadonly"
          type="button"
          class="ai-chip"
          :disabled="!aiAvailable || aiLoadingId === '__conclusion__'"
          title="AI 起草审计结论"
          aria-label="AI 起草审计结论"
          @click="aiFillConclusion"
        >
          {{ aiLoadingId === '__conclusion__' ? '…' : 'AI' }}
        </button>
      </header>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :rows="3"
        :disabled="isReadonly"
        placeholder="填写审计结论…"
        resize="vertical"
        @change="saveAuditConclusion"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useF2StocktakeFields, useF2StocktakeRows } from '../../composables/useF2StocktakeSheet'
import { useF2StocktakeOcr } from '../../composables/useF2StocktakeOcr'
import { useF2StocktakeAiGenerate } from '../../composables/useF2StocktakeAiGenerate'
import {
  applyMetaSeedToFields,
  formatVarianceSummary,
  parseJsonRows,
  readStocktakeMetaSeed,
} from '../../composables/useF2StocktakeCrossSheet'
import type { ChecklistResponse } from '../../composables/useF2StocktakeFormData'
import {
  F2_26_FIELDS,
  F2_26_LAYOUT,
  type StocktakeReconcileRow,
  type StocktakeRollMode,
  type StocktakeRollforwardRow,
  type StocktakeSampleRow,
  type StocktakeSectionField,
} from './f2StocktakeConfigs'
import F2RollTable, { type F2RollEnrichedRow } from './F2RollTable.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'
import F2StocktakeSheetAttachments from './F2StocktakeSheetAttachments.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const fieldIds = F2_26_FIELDS.filter((f) => !f.isSection).map((f) => f.id)
const fieldMap = Object.fromEntries(
  F2_26_FIELDS.filter((f) => !f.isSection).map((f) => [f.id, f]),
) as Record<string, StocktakeSectionField>

const meta = useF2StocktakeFields({
  fieldsKey: 'F2-26-fields',
  noteKey: 'F2-26-fields-note',
  fieldIds,
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

function emptyRow(): StocktakeRollforwardRow {
  return {
    id: `st-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    category: '',
    itemCode: '',
    itemName: '',
    spec: '',
    unit: '',
    unitPrice: 0,
    warehouse: '',
    countDayQty: 0,
    inboundQty: 0,
    outboundQty: 0,
    bookQty: 0,
    varianceReason: '',
    needAdjust: '',
    remark: '',
  }
}

/** 日前顺推（与旧版 F2-26-rows 公式一致，保留兼容） */
const beforeSheet = useF2StocktakeRows<StocktakeRollforwardRow>({
  rowsKey: 'F2-26-rows',
  noteKey: 'F2-26-note',
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  emptyRow,
})

/** 日后倒推 */
const afterSheet = useF2StocktakeRows<StocktakeRollforwardRow>({
  rowsKey: 'F2-26-after-rows',
  noteKey: 'F2-26-after-note',
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  emptyRow,
})

function enrich(rows: StocktakeRollforwardRow[], mode: StocktakeRollMode): F2RollEnrichedRow[] {
  return rows.map((r) => {
    const calcBsQty =
      mode === 'after'
        ? r.countDayQty + r.outboundQty - r.inboundQty
        : r.countDayQty + r.inboundQty - r.outboundQty
    const qtyDiff = calcBsQty - r.bookQty
    const amtDiff = qtyDiff * (r.unitPrice || 0)
    return {
      ...r,
      category: r.category || '',
      itemCode: r.itemCode || '',
      spec: r.spec || '',
      unit: r.unit || '',
      unitPrice: r.unitPrice || 0,
      warehouse: r.warehouse || '',
      varianceReason: r.varianceReason || '',
      needAdjust: r.needAdjust || '',
      calcBsQty,
      qtyDiff,
      amtDiff,
      hasVariance: Math.abs(qtyDiff) > 0.001,
    }
  })
}

const afterEnriched = computed(() => enrich(afterSheet.rows.value, 'after'))
const beforeEnriched = computed(() => enrich(beforeSheet.rows.value, 'before'))
const afterVarianceCount = computed(() => afterEnriched.value.filter((r) => r.hasVariance).length)
const beforeVarianceCount = computed(() => beforeEnriched.value.filter((r) => r.hasVariance).length)

function toPickerDate(raw: string | undefined): string {
  const s = (raw || '').trim()
  if (!s) return ''
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s
  const m = s.match(/(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?/)
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`
  return ''
}

const suggestedMode = computed<StocktakeRollMode | ''>(() => {
  const bs = toPickerDate(meta.fields.value.bsDate)
  const ct = toPickerDate(meta.fields.value.countDate)
  if (!bs || !ct || bs === ct) return ''
  return ct > bs ? 'after' : 'before'
})

const datesEqual = computed(() => {
  const bs = toPickerDate(meta.fields.value.bsDate)
  const ct = toPickerDate(meta.fields.value.countDate)
  return !!(bs && ct && bs === ct)
})

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const projectIdRef = toRef(() => props.projectId || '') as Ref<string>
const { ocrLoadingId, uploadAndMerge } = useF2StocktakeOcr(wpIdRef)
const { aiAvailable, generateAndConfirm } = useF2StocktakeAiGenerate({
  wpId: wpIdRef,
  projectId: projectIdRef,
})
const aiLoadingId = ref('')

function onOcr(
  rowId: string,
  file: File | undefined,
  sheet: ReturnType<typeof useF2StocktakeRows<StocktakeRollforwardRow>>,
) {
  if (!file) return
  void uploadAndMerge('F2-26', rowId, file, (id, patch) => sheet.updateRow(id, patch as Partial<StocktakeRollforwardRow>))
}

const CONCLUSION_KEY = 'F2-26-audit-conclusion'
const auditConclusion = ref('')
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item: ChecklistResponse = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-stocktake:save-items', { detail: { items: [item] } }))
}

onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
  const legacy = props.allResponses.get('F2-26-fields')
  if (legacy?.remark) {
    try {
      const parsed = JSON.parse(legacy.remark) as Record<string, string>
      const patch: Record<string, string> = {}
      if (parsed.countDate && !meta.fields.value.countDate) patch.countDate = parsed.countDate
      if (parsed.bsDate && !meta.fields.value.bsDate) patch.bsDate = parsed.bsDate
      if (parsed.method && !meta.fields.value.method) patch.method = parsed.method
      if (Object.keys(patch).length) meta.applyFields(patch, { overwriteEmptyOnly: true })
    } catch { /* ignore */ }
  }
  seedFromPlan({ silent: true })
})

function seedFromPlan(opts?: { silent?: boolean }): void {
  if (props.isReadonly) return
  const seed = readStocktakeMetaSeed(props.allResponses)
  const patch = applyMetaSeedToFields(seed, meta.fields.value, {
    entityName: 'entityName',
    bsDate: 'bsDate',
    countDate: 'countDate',
  })
  if (!Object.keys(patch).length) {
    if (!opts?.silent) {
      ElMessage.info(seed.source ? '文首字段已有内容，未覆盖' : '计划/小结中暂无可带入的文首信息')
    }
    return
  }
  meta.applyFields(patch, { overwriteEmptyOnly: true })
  if (!opts?.silent) ElMessage.success(`已从 ${seed.source || '上游'} 带入文首信息`)
}

function pullBookRows(target: StocktakeRollMode, source: 'F2-24' | 'F2-25'): void {
  if (props.isReadonly) return
  const sheet = target === 'after' ? afterSheet : beforeSheet
  let mapped: StocktakeRollforwardRow[] = []

  if (source === 'F2-24') {
    const primary = parseJsonRows<StocktakeReconcileRow>(props.allResponses, 'F2-24-rows')
    const countRows = parseJsonRows<StocktakeReconcileRow>(props.allResponses, 'F2-24-count-rows')
    const src = target === 'after' && countRows.length ? countRows : (primary.length ? primary : countRows)
    mapped = src
      .filter((r) => (r.itemName || '').trim())
      .map((r, i) => {
        const bookQty = Number(r.bookQty) || 0
        const bookAmount = Number(r.bookAmount) || 0
        return {
          ...emptyRow(),
          id: `st-${Date.now().toString(36)}-${i}-${Math.random().toString(36).slice(2, 6)}`,
          itemName: r.itemName || '',
          spec: r.spec || '',
          bookQty,
          unitPrice: bookQty ? bookAmount / bookQty : 0,
          remark: r.remark || '',
        }
      })
  } else {
    const exist = parseJsonRows<StocktakeSampleRow>(props.allResponses, 'F2-25-rows')
    const floor = parseJsonRows<StocktakeSampleRow>(props.allResponses, 'F2-25-floor-rows')
    const src = exist.length ? exist : floor
    mapped = src
      .filter((r) => (r.itemName || '').trim())
      .map((r, i) => ({
        ...emptyRow(),
        id: `st-${Date.now().toString(36)}-${i}-${Math.random().toString(36).slice(2, 6)}`,
        itemCode: r.itemCode || '',
        itemName: r.itemName || '',
        spec: r.spec || '',
        unit: r.unit || '',
        unitPrice: Number(r.unitPrice) || 0,
        bookQty: Number(r.bookQty) || 0,
        countDayQty: Number(r.sampleQty) || Number(r.clientCountQty) || 0,
        remark: r.remark || '',
      }))
  }

  if (!mapped.length) {
    ElMessage.warning(`${source} 暂无可带入的明细行`)
    return
  }

  const existingNames = new Set(
    sheet.rows.value.map((r) => (r.itemName || '').trim()).filter(Boolean),
  )
  const toAdd = mapped.filter((r) => !existingNames.has((r.itemName || '').trim()))
  if (!toAdd.length) {
    ElMessage.info('品名已存在，未重复带入')
    return
  }
  sheet.rows.value = [...sheet.rows.value, ...toAdd]
  void sheet.flushNow()
  ElMessage.success(`已从 ${source} 带入 ${toAdd.length} 行（请补全期间收发数量）`)
}

const aiContext = computed(() => {
  const filled = Object.fromEntries(
    Object.entries(meta.fields.value).filter(([, v]) => v),
  )
  const afterVar = afterEnriched.value.filter((r) => r.hasVariance)
  const beforeVar = beforeEnriched.value.filter((r) => r.hasVariance)
  return {
    sheet: 'F2-26',
    suggestedMode: suggestedMode.value,
    afterVariance: afterVarianceCount.value,
    beforeVariance: beforeVarianceCount.value,
    afterRows: afterEnriched.value.length,
    beforeRows: beforeEnriched.value.length,
    afterVarianceSummary: formatVarianceSummary(
      afterVar.map((r) => ({
        itemName: r.itemName,
        qtyDiff: r.qtyDiff,
        amtDiff: r.amtDiff,
        calcBsQty: r.calcBsQty,
        bookQty: r.bookQty,
        varianceReason: r.varianceReason,
        hasVariance: true,
      })),
      { label: '日后倒推差异' },
    ),
    beforeVarianceSummary: formatVarianceSummary(
      beforeVar.map((r) => ({
        itemName: r.itemName,
        qtyDiff: r.qtyDiff,
        amtDiff: r.amtDiff,
        calcBsQty: r.calcBsQty,
        bookQty: r.bookQty,
        varianceReason: r.varianceReason,
        hasVariance: true,
      })),
      { label: '日前顺推差异' },
    ),
    ...filled,
  }
})

async function aiFillField(fieldId: string, fieldLabel: string): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  aiLoadingId.value = fieldId
  try {
    const text = await generateAndConfirm(
      'stocktake-rollforward-field',
      meta.fields.value[fieldId] || '',
      { ...aiContext.value, fieldId, fieldLabel },
      `AI · ${fieldLabel}`,
    )
    if (text) {
      meta.updateField(fieldId, text)
      ElMessage.success('已填入，可继续编辑')
    }
  } finally {
    aiLoadingId.value = ''
  }
}

async function aiFillNote(): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  aiLoadingId.value = '__note__'
  try {
    const text = await generateAndConfirm(
      'stocktake-rollforward-field',
      beforeSheet.auditNote.value || '',
      { ...aiContext.value, fieldId: 'auditNote', fieldLabel: '审计说明' },
      'AI · 审计说明',
    )
    if (text) {
      beforeSheet.auditNote.value = text
      ElMessage.success('已填入，可继续编辑')
    }
  } finally {
    aiLoadingId.value = ''
  }
}

async function aiFillConclusion(): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  aiLoadingId.value = '__conclusion__'
  try {
    const text = await generateAndConfirm(
      'stocktake-rollforward',
      auditConclusion.value || '',
      { ...aiContext.value, fieldId: 'conclusion', fieldLabel: '审计结论' },
      'AI · 审计结论',
    )
    if (text) {
      saveAuditConclusion(text)
      ElMessage.success('已填入，可继续编辑')
    }
  } finally {
    aiLoadingId.value = ''
  }
}
</script>

<style scoped>
.f2-roll {
  --rf-border: #e8eaef;
  --rf-muted: #6b7280;
  --rf-ink: #1f2937;
  --rf-accent: var(--gt-color-primary, #4b2d77);
  --rf-accent-light: var(--gt-color-primary-light, #A06DFF);
  --rf-surface: var(--gt-color-primary-bg, #f4f0fa);
  padding: 8px 12px 20px;
  font-size: var(--wp-font-size, 13px);
  color: var(--rf-ink);
  max-width: 1280px;
}
.f2-roll :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f2-roll :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

.rf-hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 14px 16px;
  margin-bottom: 12px;
  border: 1px solid var(--rf-border);
  border-radius: 10px;
  background: linear-gradient(135deg, #faf9ff 0%, #fff 55%);
}
.rf-kicker {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--rf-accent);
  font-weight: 600;
  margin-bottom: 4px;
}
.rf-title {
  margin: 0;
  font-size: 18px;
  font-weight: 650;
  line-height: 1.3;
  color: var(--rf-ink);
}
.rf-objective {
  margin: 6px 0 0;
  color: var(--rf-muted);
  line-height: 1.5;
  max-width: 56em;
}
.rf-hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  flex-shrink: 0;
}

.rf-guide {
  margin-bottom: 12px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid var(--gt-color-primary-lighter, #c4a8e8);
  background: var(--rf-surface);
}
.rf-guide summary {
  cursor: pointer;
  font-weight: 600;
  color: #374151;
  list-style: none;
}
.rf-guide summary::-webkit-details-marker { display: none; }
.rf-guide ol {
  margin: 8px 0 4px;
  padding-left: 1.2em;
  color: var(--rf-muted);
  line-height: 1.55;
}

.rf-mode-hint {
  margin-bottom: 12px;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.45;
  border: 1px solid var(--gt-color-primary-lighter, #c4a8e8);
  background: var(--rf-surface);
  color: var(--rf-accent);
}
.rf-mode-hint.after {
  border-color: var(--gt-color-wheat, #FFC23D);
  background: var(--gt-color-wheat-light, #fff8e6);
  color: #8a6a12;
}
.rf-mode-hint.before {
  border-color: var(--gt-color-primary-lighter, #c4a8e8);
  background: var(--rf-surface);
  color: var(--rf-accent);
}
.rf-mode-hint.same {
  border-color: #e5e7eb;
  background: #f9fafb;
  color: #6b7280;
}

.rf-card {
  margin-bottom: 12px;
  border: 1px solid var(--rf-border);
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}
.rf-card.recommended {
  border-color: var(--gt-color-primary-lighter, #c4a8e8);
  box-shadow: 0 0 0 1px rgba(75, 45, 119, 0.12);
}
.rf-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--rf-border);
  background: var(--rf-surface);
}
.rf-card-head h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 650;
  color: var(--rf-accent);
}
.rf-card-head p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--rf-muted);
}
.rf-card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.rf-card-grid {
  display: grid;
  gap: 12px 14px;
  padding: 12px 14px 14px;
}
.rf-card-body {
  padding: 12px 14px 14px;
}
.rf-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.rf-field.span2 { grid-column: 1 / -1; }
.rf-field-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  font-weight: 550;
  color: #374151;
}
.rf-field :deep(.el-textarea__inner),
.rf-field :deep(.el-input__wrapper),
.rf-field :deep(.el-date-editor.el-input__wrapper) {
  box-shadow: 0 0 0 1px #e5e7eb inset;
}
.rf-field :deep(.el-textarea__inner:focus),
.rf-field :deep(.el-input__wrapper.is-focus),
.rf-field :deep(.el-date-editor.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--rf-accent) inset !important;
}
.rf-field :deep(.el-date-editor) { width: 100%; }

.ai-chip {
  border: 1px solid var(--gt-color-primary-lighter, #c4a8e8);
  background: var(--rf-surface);
  color: var(--rf-accent);
  border-radius: 999px;
  padding: 0 8px;
  height: 22px;
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.02em;
  cursor: pointer;
  line-height: 20px;
  flex-shrink: 0;
}
.ai-chip:hover:not(:disabled) {
  background: #ebe4f5;
  border-color: var(--rf-accent-light);
}
.ai-chip:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

:deep(.auto-calc-col) { background-color: #f8f7fc !important; }
:deep(.warn-row) { background: var(--gt-color-coral-light, #fff0ef); }

.rf-card-conclusion .rf-card-head { background: var(--rf-surface); }
.rf-card-conclusion :deep(.el-textarea) {
  padding: 0 14px 14px;
  display: block;
}
</style>
