<template>
  <div class="g1-sec-count" data-testid="g1-securities-count">
    <div class="section-head">
      <h3 class="sheet-title">G1-11 有价证券监盘表</h3>
      <div class="head-actions tab-toolbar">
        <G1ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G1-11"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="sc.addRow()">新增监盘行</el-button>
        <el-button size="small" :disabled="isReadonly" @click="sc.pullFromDetail()">从 G1-2 带入</el-button>
        <el-button size="small" :disabled="isReadonly" @click="onPushToG12">推送 G1-12</el-button>
        <el-button size="small" @click="headerDialogVisible = true">盘点信息</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-12" /></span>
        <el-tag size="small" type="info">共 {{ sc.rows.value.length }} 行</el-tag>
        <el-tag size="small" :type="sc.gateReady.value ? 'success' : 'warning'">
          差异闸门 {{ sc.gateReady.value ? '通过' : '待补' }}
        </el-tag>
        <el-button size="small" @click="openReviewDialog('G1-11-conclusion')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：确定资产负债表中记录的交易性金融资产是存在的，并记录于正确的账户。"
    />

    <el-alert
      v-if="sc.diffReasonGaps.value.length"
      type="warning"
      :closable="false"
      class="gate-alert"
      :title="`差异原因闸门：${sc.diffReasonGaps.value.length} 行 |差异|>0 未填原因（${sc.diffReasonGaps.value.map(r => r.securityName || '未命名').join('、')}）`"
    />

    <!-- 盘点信息摘要 -->
    <div class="header-summary" @click="headerDialogVisible = true">
      <div class="summary-main">
        <span class="summary-title">二、审计过程 · 盘点情况</span>
        <el-tag
          size="small"
          :type="sc.headerStatus.value.missing.length ? 'warning' : 'success'"
        >
          基础信息 {{ sc.headerStatus.value.filled }}/{{ sc.headerStatus.value.total }}
        </el-tag>
        <el-button link type="primary" size="small" @click.stop="headerDialogVisible = true">
          {{ isReadonly ? '查看' : '弹窗填写' }}
        </el-button>
      </div>
      <div class="summary-meta">
        <span>单位：{{ sc.header.value.company || '—' }}</span>
        <span>日期：{{ sc.header.value.countDate || '—' }}</span>
        <span>地点：{{ sc.header.value.location || '—' }}</span>
        <span>监盘人：{{ sc.header.value.observer || '—' }}</span>
        <span>盘点人：{{ sc.header.value.counter || '—' }}</span>
      </div>
      <p v-if="sc.header.value.narrative" class="narrative">{{ sc.header.value.narrative }}</p>
      <p v-else class="narrative placeholder">
        点击填写盘点单位、日期、地点与人员后，将自动生成监盘叙述（可再手改）。
      </p>
      <p v-if="sc.headerStatus.value.missing.length" class="missing-hint">
        待填：{{ sc.headerStatus.value.missing.join('、') }}
      </p>
    </div>

    <!-- 监盘扫描件（表级） -->
    <div v-if="projectId && wpId" class="attach-bar">
      <span class="attach-label">监盘表扫描件 / 现场照片</span>
      <ItemAttachment
        :project-id="projectId"
        :wp-id="wpId"
        sheet-key="G1-11"
        :item-index="0"
        accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls"
      />
    </div>

    <div class="stats-bar">
      <span>
        监盘证券 <b>{{ sc.rows.value.length }}</b> 项 ·
        盘点数量合计 {{ fmtNum(sc.grandTotal.value.countedQuantity) }} ·
        总计 {{ fmtNum(sc.grandTotal.value.total) }} ·
        差异项 <b :class="{ warn: sc.diffCount.value > 0 }">{{ sc.diffCount.value }}</b>
      </span>
      <div class="filter-bar">
        <el-select
          v-model="locationFilter"
          size="small"
          clearable
          placeholder="按地点筛选"
          style="width: 160px"
        >
          <el-option label="全部地点" value="" />
          <el-option
            v-for="loc in sc.locationOptions.value"
            :key="loc"
            :label="loc"
            :value="loc"
          />
          <el-option label="未指定地点" value="__empty__" />
        </el-select>
        <el-switch
          v-model="groupByLocation"
          size="small"
          inline-prompt
          active-text="分组"
          inactive-text="平铺"
        />
      </div>
    </div>

    <template v-if="groupByLocation">
      <div
        v-for="grp in displayGroups"
        :key="grp.location"
        class="loc-group"
      >
        <div class="loc-group-head">
          <strong>{{ grp.location }}</strong>
          <el-tag size="small" type="info">{{ grp.rows.length }} 项</el-tag>
        </div>
        <CountTable
          :rows="grp.rows"
          :is-readonly="isReadonly"
          :ocr-loading-row-id="ocrLoadingRowId"
          :wp-id="wpId"
          @update="(id, patch) => sc.updateRow(id, patch)"
          @remove="(id) => sc.removeRow(id)"
          @ocr="handleRowOcr"
        />
      </div>
    </template>
    <CountTable
      v-else
      :rows="filteredRows"
      :is-readonly="isReadonly"
      :ocr-loading-row-id="ocrLoadingRowId"
      :wp-id="wpId"
      @update="(id, patch) => sc.updateRow(id, patch)"
      @remove="(id) => sc.removeRow(id)"
      @ocr="handleRowOcr"
    />

    <p class="cross-ref">
      盘点日至报表日调节：见 <GtIndexChip value="wp:G1-12" />；
      可点击「推送 G1-12」写入监盘日实存。
    </p>

    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      :conclusion="sc.auditConclusion.value"
      @update:conclusion="(v: string) => { sc.auditConclusion.value = v }"
      note-ai-section="counting-note"
      conclusion-ai-section="counting-conclusion"
      note-placeholder="填写审计说明：（1）监盘或托管对账执行；（2）盘点差异及原因；（3）扫描件/OCR取证；（4）多地点同时盘点情况；（5）与 G1-12 倒轧衔接。"
      note-hint="覆盖监盘范围、差异闸门、取证及倒轧衔接。"
      :related-context="{
        行数: sc.rows.value.length,
        差异项: sc.diffCount.value,
        差异原因待补: sc.diffReasonGaps.value.length,
        盘点日期: sc.header.value.countDate,
        地点数: sc.locationOptions.value.length,
        监盘人: sc.header.value.observer,
      }"
    />

    <details class="prep-hint" open>
      <summary>📋 编制提示 / 监盘注意</summary>
      <ul>
        <li>总计 = 面值 × 数量；差异 = 盘点数量 − 账面数量；|差异|&gt;0 须填差异原因（闸门）。</li>
        <li>不同地点保管的证券应同时盘点：按行填写「盘点地点」，可用分组/筛选查看。</li>
        <li>盘点应与现金盘点同时进行；审计人员不宜亲自经手证券。</li>
        <li>盘点日 ≠ 报表日时推送至 G1-12 完成倒轧；行级 📎 可 OCR 识别托管对账单/盘点表。</li>
      </ul>
    </details>

    <!-- 盘点信息弹窗 -->
    <el-dialog
      v-model="headerDialogVisible"
      title="盘点情况 · 基础信息"
      width="640px"
      destroy-on-close
    >
      <el-form :model="draftHeader" label-width="96px" size="small" :disabled="isReadonly">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="盘点单位" required>
              <el-input v-model="draftHeader.company" placeholder="被审计单位" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="盘点日期" required>
              <el-date-picker
                v-model="draftHeader.countDate"
                type="date"
                value-format="YYYY-MM-DD"
                style="width:100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="盘点地点" required>
              <el-input v-model="draftHeader.location" placeholder="如：公司财务室 / 托管行；多地点在行上细分" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="参加人数">
              <el-input v-model="draftHeader.participantCount" placeholder="如：3" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="会计主管">
              <el-input v-model="draftHeader.accountingSupervisor" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="出纳人员">
              <el-input v-model="draftHeader.cashier" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="监盘人" required>
              <el-input v-model="draftHeader.observer" placeholder="项目组监盘人员" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="盘点人" required>
              <el-input v-model="draftHeader.counter" placeholder="被审计单位盘点人" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="复核人">
              <el-input v-model="draftHeader.reviewer" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="监盘叙述">
          <el-input
            v-model="draftHeader.narrative"
            type="textarea"
            :rows="3"
            placeholder="保存时可按上方信息自动生成，亦可手改"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="headerDialogVisible = false">取消</el-button>
        <el-button v-if="!isReadonly" @click="onRegenInDialog">按信息重写叙述</el-button>
        <el-button v-if="!isReadonly" type="primary" @click="saveHeaderDialog">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, inject, watch, computed, defineComponent, h } from 'vue'
import {
  useG1SecuritiesCount,
  buildCountNarrative,
  type G1SecuritiesCountHeader,
  type G1SecuritiesCountRow,
} from '../../composables/useG1SecuritiesCount'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'
import G1ImportExportDropdown from '../G1ImportExportDropdown.vue'
import ItemAttachment from '../../ItemAttachment.vue'
import { ElMessage, ElMessageBox, ElTable, ElTableColumn, ElInput, ElInputNumber, ElDatePicker, ElButton, ElUpload, ElTooltip } from 'element-plus'
import http from '@/utils/http'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
  projectId?: string
}>()

const wpId = computed(() => props.wpId ?? '')
const projectId = computed(() => props.projectId ?? '')

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const sc = useG1SecuritiesCount({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const AUDIT_NOTE_KEY = 'G1-11-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})

const headerDialogVisible = ref(false)
const draftHeader = ref<G1SecuritiesCountHeader>({ ...sc.header.value })
const locationFilter = ref('')
const groupByLocation = ref(false)
const ocrLoadingRowId = ref<string | null>(null)

watch(headerDialogVisible, (open) => {
  if (open) draftHeader.value = { ...sc.header.value }
})

const filteredRows = computed(() => {
  const f = locationFilter.value
  if (!f) return sc.rows.value
  if (f === '__empty__') return sc.rows.value.filter((r) => !String(r.location || '').trim())
  return sc.rows.value.filter((r) => String(r.location || '').trim() === f)
})

const displayGroups = computed(() => {
  const rows = filteredRows.value
  const map = new Map<string, G1SecuritiesCountRow[]>()
  for (const r of rows) {
    const loc = String(r.location || '').trim() || '未指定地点'
    if (!map.has(loc)) map.set(loc, [])
    map.get(loc)!.push(r)
  }
  return Array.from(map.entries()).map(([location, list]) => ({ location, rows: list }))
})

function onRegenInDialog() {
  draftHeader.value = {
    ...draftHeader.value,
    narrative: buildCountNarrative(draftHeader.value),
  }
}

function saveHeaderDialog() {
  const narrative =
    draftHeader.value.narrative?.trim()
      ? draftHeader.value.narrative
      : buildCountNarrative(draftHeader.value)
  sc.updateHeader({ ...draftHeader.value, narrative }, false)
  if (draftHeader.value.countDate || draftHeader.value.location) {
    for (const r of sc.rows.value) {
      if (!r.countDate && draftHeader.value.countDate) r.countDate = draftHeader.value.countDate
      if (!r.location && draftHeader.value.location) r.location = draftHeader.value.location
    }
    sc.persistRows()
  }
  headerDialogVisible.value = false
}

async function onPushToG12() {
  if (!sc.gateReady.value) {
    try {
      await ElMessageBox.confirm(
        `仍有 ${sc.diffReasonGaps.value.length} 行差异未填原因，是否仍推送至 G1-12？`,
        '差异闸门未通过',
        { confirmButtonText: '仍推送', cancelButtonText: '先补原因', type: 'warning' },
      )
    } catch {
      return
    }
  }
  sc.pushToReconciliation(false)
}

function onImported() {
  emit('imported')
  sc.loadAll()
}

function fmtNum(v: unknown): string {
  if (typeof v !== 'number' || Number.isNaN(v)) return String(v ?? '')
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

const OCR_FIELD_MAP: Record<string, string> = {
  security_name: 'securityName', 证券名称: 'securityName', name: 'securityName',
  security_code: 'securityCode', 代码: 'securityCode', code: 'securityCode',
  face_value: 'faceValue', 面值: 'faceValue',
  quantity: 'countedQuantity', 数量: 'countedQuantity', counted_quantity: 'countedQuantity',
  coupon_rate: 'couponRate', 票面利率: 'couponRate', rate: 'couponRate',
  maturity_date: 'maturityDate', 到期日: 'maturityDate',
  custodian: 'custodian', 保管机构: 'custodian', 托管: 'custodian',
  booked_quantity: 'bookedQuantity', 账面数量: 'bookedQuantity',
  location: 'location', 地点: 'location', 盘点地点: 'location',
}

async function handleRowOcr(rowId: string, file: File): Promise<boolean> {
  if (props.isReadonly || !props.wpId) return false
  ocrLoadingRowId.value = rowId
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const fields: Record<string, any> = (res.data?.data ?? res.data)?.extracted_fields || {}
    if (!Object.keys(fields).length) {
      ElMessage.info('OCR完成，未识别到可填充字段')
      return false
    }
    const patch: Record<string, any> = {}
    for (const [ocrKey, val] of Object.entries(fields)) {
      const target = OCR_FIELD_MAP[ocrKey] || OCR_FIELD_MAP[ocrKey.toLowerCase()]
      if (target && val != null && String(val).trim() !== '') {
        patch[target] = ['faceValue', 'countedQuantity', 'couponRate', 'bookedQuantity'].includes(target)
          ? Number(val) || 0
          : val
      }
    }
    if (!Object.keys(patch).length) {
      ElMessage.info('OCR完成，识别字段无法匹配监盘列')
      return false
    }
    const preview = Object.entries(patch).map(([k, v]) => `${k}: ${v}`).join('，')
    await ElMessageBox.confirm(`识别到监盘信息：\n${preview}\n是否填入当前行？`, 'OCR识别结果', {
      confirmButtonText: '填入',
      cancelButtonText: '取消',
    })
    sc.updateRow(rowId, patch)
    ElMessage.success('已填入识别结果')
  } catch (e) {
    if (e !== 'cancel') ElMessage.warning('OCR识别失败')
  } finally {
    ocrLoadingRowId.value = null
  }
  return false
}

/** 内联表格子组件，避免分组/平铺重复大段模板 */
const CountTable = defineComponent({
  name: 'G1CountTable',
  props: {
    rows: { type: Array as () => G1SecuritiesCountRow[], required: true },
    isReadonly: { type: Boolean, default: false },
    ocrLoadingRowId: { type: String as () => string | null, default: null },
    wpId: { type: String, default: '' },
  },
  emits: ['update', 'remove', 'ocr'],
  setup(p, { emit }) {
    function rowClass({ row }: { row: G1SecuritiesCountRow }) {
      const abs = Math.abs(Number(row.countDiff) || 0)
      if (abs > 0 && !String(row.diffReason || '').trim()) return 'diff-row gap-row'
      if (abs > 0) return 'diff-row'
      return ''
    }
    function fmt(v: unknown) {
      if (typeof v !== 'number' || Number.isNaN(v)) return String(v ?? '')
      return v.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
    }
    return () =>
      h(
        ElTable,
        {
          data: p.rows,
          border: true,
          size: 'small',
          maxHeight: 420,
          rowClassName: rowClass,
          class: 'count-inner-table',
        },
        {
          default: () => [
            h(ElTableColumn, { label: '地点', width: 100, fixed: true }, {
              default: ({ row }: { row: G1SecuritiesCountRow }) =>
                h(ElInput, {
                  modelValue: row.location,
                  size: 'small',
                  disabled: p.isReadonly,
                  placeholder: '地点',
                  'onUpdate:modelValue': (v: string) => { row.location = v },
                  onChange: () => emit('update', row.id, { location: row.location }),
                }),
            }),
            h(ElTableColumn, { label: '证券名称', minWidth: 120, fixed: true }, {
              default: ({ row }: { row: G1SecuritiesCountRow }) =>
                h(ElInput, {
                  modelValue: row.securityName,
                  size: 'small',
                  disabled: p.isReadonly,
                  'onUpdate:modelValue': (v: string) => { row.securityName = v },
                  onChange: () => emit('update', row.id, { securityName: row.securityName }),
                }),
            }),
            h(ElTableColumn, { label: '面值', width: 90, align: 'right' }, {
              default: ({ row }: { row: G1SecuritiesCountRow }) =>
                h(ElInputNumber, {
                  modelValue: row.faceValue,
                  size: 'small',
                  controls: false,
                  disabled: p.isReadonly,
                  style: 'width:100%',
                  'onUpdate:modelValue': (v: number | undefined) => { row.faceValue = v ?? 0 },
                  onChange: () => emit('update', row.id, { faceValue: row.faceValue }),
                }),
            }),
            h(ElTableColumn, { label: '数量', width: 88, align: 'right' }, {
              default: ({ row }: { row: G1SecuritiesCountRow }) =>
                h(ElInputNumber, {
                  modelValue: row.countedQuantity,
                  size: 'small',
                  controls: false,
                  disabled: p.isReadonly,
                  style: 'width:100%',
                  'onUpdate:modelValue': (v: number | undefined) => { row.countedQuantity = v ?? 0 },
                  onChange: () => emit('update', row.id, { countedQuantity: row.countedQuantity }),
                }),
            }),
            h(ElTableColumn, { label: '总计', width: 100, align: 'right' }, {
              default: ({ row }: { row: G1SecuritiesCountRow }) =>
                h('span', { class: 'formula-cell', title: '总计 = 面值 × 数量' }, fmt(row.total)),
            }),
            h(ElTableColumn, { label: '利率(%)', width: 88, align: 'right' }, {
              default: ({ row }: { row: G1SecuritiesCountRow }) =>
                h(ElInputNumber, {
                  modelValue: row.couponRate,
                  size: 'small',
                  controls: false,
                  precision: 4,
                  disabled: p.isReadonly,
                  style: 'width:100%',
                  'onUpdate:modelValue': (v: number | undefined) => { row.couponRate = v ?? 0 },
                  onChange: () => emit('update', row.id, { couponRate: row.couponRate }),
                }),
            }),
            h(ElTableColumn, { label: '到期日', width: 128 }, {
              default: ({ row }: { row: G1SecuritiesCountRow }) =>
                h(ElDatePicker, {
                  modelValue: row.maturityDate,
                  type: 'date',
                  valueFormat: 'YYYY-MM-DD',
                  size: 'small',
                  style: 'width:100%',
                  disabled: p.isReadonly,
                  'onUpdate:modelValue': (v: string) => { row.maturityDate = v || '' },
                  onChange: () => emit('update', row.id, { maturityDate: row.maturityDate }),
                }),
            }),
            h(ElTableColumn, { label: '账面数量', width: 96, align: 'right' }, {
              default: ({ row }: { row: G1SecuritiesCountRow }) =>
                h(ElInputNumber, {
                  modelValue: row.bookedQuantity,
                  size: 'small',
                  controls: false,
                  disabled: p.isReadonly,
                  style: 'width:100%',
                  'onUpdate:modelValue': (v: number | undefined) => { row.bookedQuantity = v ?? 0 },
                  onChange: () => emit('update', row.id, { bookedQuantity: row.bookedQuantity }),
                }),
            }),
            h(ElTableColumn, { label: '差异', width: 80, align: 'right' }, {
              default: ({ row }: { row: G1SecuritiesCountRow }) =>
                h('span', {
                  class: ['formula-cell', Math.abs(row.countDiff) > 0 ? 'diff-warn' : ''],
                  title: '差异 = 盘点数量 − 账面数量',
                }, fmt(row.countDiff)),
            }),
            h(ElTableColumn, { label: '差异原因', minWidth: 120 }, {
              default: ({ row }: { row: G1SecuritiesCountRow }) =>
                h(ElInput, {
                  modelValue: row.diffReason,
                  size: 'small',
                  disabled: p.isReadonly,
                  class: Math.abs(row.countDiff) > 0 && !row.diffReason?.trim() ? 'reason-required' : '',
                  placeholder: Math.abs(row.countDiff) > 0 ? '必填' : '',
                  'onUpdate:modelValue': (v: string) => { row.diffReason = v },
                  onChange: () => emit('update', row.id, { diffReason: row.diffReason }),
                }),
            }),
            h(ElTableColumn, { label: '保管机构', width: 110 }, {
              default: ({ row }: { row: G1SecuritiesCountRow }) =>
                h(ElInput, {
                  modelValue: row.custodian,
                  size: 'small',
                  disabled: p.isReadonly,
                  'onUpdate:modelValue': (v: string) => { row.custodian = v },
                  onChange: () => emit('update', row.id, { custodian: row.custodian }),
                }),
            }),
            h(ElTableColumn, { label: '📎', width: 72, fixed: 'right' }, {
              default: ({ row }: { row: G1SecuritiesCountRow }) => {
                if (p.isReadonly || !p.wpId) return h('span', '—')
                return h(ElTooltip, { content: '上传对账单/盘点表 OCR', placement: 'top' }, {
                  default: () =>
                    h(ElUpload, {
                      autoUpload: true,
                      showFileList: false,
                      accept: '.pdf,.png,.jpg,.jpeg',
                      disabled: p.ocrLoadingRowId === row.id,
                      httpRequest: () => Promise.resolve(),
                      beforeUpload: (file: File) => {
                        emit('ocr', row.id, file)
                        return false
                      },
                    }, {
                      default: () =>
                        h(ElButton, {
                          size: 'small',
                          link: true,
                          type: 'primary',
                          loading: p.ocrLoadingRowId === row.id,
                        }, () => 'OCR'),
                    }),
                })
              },
            }),
            !p.isReadonly
              ? h(ElTableColumn, { label: '操作', width: 52, fixed: 'right' }, {
                  default: ({ row }: { row: G1SecuritiesCountRow }) =>
                    h(ElButton, {
                      size: 'small',
                      type: 'danger',
                      link: true,
                      onClick: () => emit('remove', row.id),
                    }, () => '删'),
                })
              : null,
          ],
        },
      )
  },
})
</script>

<style scoped>
.g1-sec-count { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-sec-count :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g1-sec-count :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; color: #1f2a37; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 10px; }
.gate-alert { margin-bottom: 10px; }
.header-summary {
  margin-bottom: 12px;
  padding: 10px 12px;
  background: #f8f9fb;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  cursor: pointer;
}
.header-summary:hover { border-color: #c0c4cc; }
.summary-main { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
.summary-title { font-weight: 600; color: #303133; font-size: 13px; }
.summary-meta { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: #606266; }
.narrative { margin: 8px 0 0; font-size: 12px; color: #303133; line-height: 1.5; }
.narrative.placeholder { color: #909399; }
.missing-hint { margin: 6px 0 0; font-size: 12px; color: #e6a23c; }
.attach-bar {
  margin-bottom: 12px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
  padding: 8px 12px;
  border: 1px dashed #dcdfe6;
  border-radius: 6px;
  background: #fafafa;
}
.attach-label { font-size: 12px; color: #606266; padding-top: 6px; white-space: nowrap; }
.stats-bar {
  margin-bottom: 10px;
  padding: 8px 12px;
  background: #f8f9fb;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 12px;
  color: #606266;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.stats-bar .warn { color: #e6a23c; }
.filter-bar { display: flex; align-items: center; gap: 10px; }
.loc-group { margin-bottom: 14px; }
.loc-group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 13px;
  color: #303133;
}
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.diff-warn { color: #e6a23c; font-weight: 600; }
.cross-ref { margin: 10px 0; font-size: 12px; color: #606266; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #606266; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
:deep(.diff-row) { background: #fdf6ec; }
:deep(.gap-row) { background: #fef0f0; }
:deep(.reason-required .el-input__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }
</style>
