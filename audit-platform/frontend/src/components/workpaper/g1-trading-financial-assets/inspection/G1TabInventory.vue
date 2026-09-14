<template>
  <div class="g1-inventory" data-testid="g1-inventory">
    <div class="section-head">
      <h3 class="sheet-title">G1-4 交易性金融资产期末结存表</h3>
      <div class="head-actions tab-toolbar">
        <G1ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G1-4"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
        <el-button size="small" :disabled="isReadonly" @click="onSyncDetail">从 G1-2 带入账面</el-button>
        <el-button size="small" :disabled="isReadonly" @click="onSyncCount">从 G1-11 回填监盘</el-button>
        <el-button
          size="small"
          :disabled="isReadonly || !projectId"
          :loading="confirmSyncing"
          @click="onSyncConfirm"
        >
          从函证模块回填④
        </el-button>
        <el-button
          size="small"
          type="warning"
          :disabled="isReadonly || inv.diffCount.value === 0"
          @click="onPushAdj"
        >
          差异推送 G1-3
        </el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="inv.addRow()">新增证券</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-3" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-11" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-12" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G0-3S" /></span>
        <el-button size="small" @click="openReviewDialog('G1-4-conclusion')">💬复核</el-button>
      </div>
    </div>

    <details class="guidance-details" open>
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表对齐 Excel「结存表 G1-4」：以①账面结存为起点，对照②库存、③对账单、④函证，计算⑤差异。</p>
        <p>2. 差异公式：⑤ = ① − ② − (③ 或 ④)。证据源选「自动」时优先函证，否则对账单；可选「仅监盘」则只扣减②。</p>
        <p>3. 可从 G1-2 带入账面、从 G1-11 回填监盘、从函证模块（G0-3S/G0-1）回填④；差异非零应说明原因，并可推送至 G1-3 调整分录。</p>
        <p>4. <strong>与 G1-12 分工：</strong>本表 = 报表日多源存在性核对；G1-12 = 监盘日→报表日时间轴倒轧。二者差异原因应互相印证，勿重复录入同一差异。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实交易性金融资产存在、完整、权利义务及计价；通过账面与库存/对账单/函证交叉核对，识别并说明结存差异。"
    />

    <el-alert
      v-if="inv.reconCrossMismatches.value.length > 0"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      :title="`与 G1-12 账面交叉校验：${inv.reconCrossMismatches.value.length} 项证券数量/金额不一致（请核对 G1-4 ①账面与 G1-12 账面列）`"
    >
      <ul class="cross-list">
        <li v-for="m in inv.reconCrossMismatches.value.slice(0, 8)" :key="m.securityName">
          {{ m.securityName }}：G1-4 数量 {{ fmt(m.inventoryBookQty) }} / 金额 {{ fmt(m.inventoryBookTotal) }}
          ≠ G1-12 数量 {{ fmt(m.reconBookQty) }} / 金额 {{ fmt(m.reconBookTotal) }}
          <span v-if="m.reconReportQty">（倒轧报表日数量 {{ fmt(m.reconReportQty) }}）</span>
        </li>
      </ul>
    </el-alert>

    <el-alert
      v-if="inv.lastConfirmSync.value && inv.lastConfirmSync.value.unmatchedConfirm.length > 0"
      type="warning"
      :closable="true"
      show-icon
      class="cross-alert"
      :title="`函证回填：已匹配 ${inv.lastConfirmSync.value.matched} 行${inv.lastConfirmSync.value.fuzzyMatched ? `（含模糊 ${inv.lastConfirmSync.value.fuzzyMatched}）` : ''}；未匹配 ${inv.lastConfirmSync.value.unmatchedConfirm.length} 行`"
    >
      <ul class="cross-list">
        <li
          v-for="(u, i) in inv.lastConfirmSync.value.unmatchedConfirm.slice(0, 12)"
          :key="i"
        >
          {{ u.label }}
        </li>
      </ul>
      <p v-if="inv.lastConfirmSync.value.unmatchedConfirm.length > 12" class="cross-more">
        …其余 {{ inv.lastConfirmSync.value.unmatchedConfirm.length - 12 }} 行略
      </p>
    </el-alert>

    <div class="stats-bar">
      <span>证券 <b>{{ inv.rows.value.length }}</b> 项</span>
      <span>账面总计 <b>{{ fmt(inv.bookGrandTotal.value) }}</b></span>
      <span>
        差异项
        <b :class="{ warn: inv.diffCount.value > 0 }">{{ inv.diffCount.value }}</b>
      </span>
      <span>
        差异合计
        <b :class="{ warn: Math.abs(inv.diffGrandTotal.value) > 0.005 }">
          {{ fmt(inv.diffGrandTotal.value) }}
        </b>
      </span>
    </div>

    <el-table
      :data="inv.rows.value"
      border
      size="small"
      max-height="560"
      style="width: 100%"
      :row-class-name="rowClass"
      empty-text="暂无结存行。可「新增证券」或「从 G1-2 带入账面」。"
    >
      <el-table-column label="证券信息" align="center">
        <el-table-column label="证券名称" min-width="140" fixed="left">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.securityName"
              size="small"
              @change="(v: string) => inv.updateRow(row.id, { securityName: v })"
            />
            <span v-else>{{ row.securityName || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资金账号" width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.cashAccountNo"
              size="small"
              @change="(v: string) => inv.updateRow(row.id, { cashAccountNo: v })"
            />
            <span v-else>{{ row.cashAccountNo || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账户名称" width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.accountName"
              size="small"
              @change="(v: string) => inv.updateRow(row.id, { accountName: v })"
            />
            <span v-else>{{ row.accountName || '—' }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="①账面结存证券投资" align="center">
        <el-table-column label="数量" width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.bookQuantity"
              size="small"
              :controls="false"
              style="width: 100%"
              @update:model-value="(v: number) => inv.updateRow(row.id, { bookQuantity: v ?? 0 })"
            />
            <span v-else>{{ fmt(row.bookQuantity) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="面值/单价" width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.bookFaceValue"
              size="small"
              :controls="false"
              style="width: 100%"
              @update:model-value="(v: number) => inv.updateRow(row.id, { bookFaceValue: v ?? 0 })"
            />
            <span v-else>{{ fmt(row.bookFaceValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="票面利率" width="80">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.couponRate"
              size="small"
              placeholder="%"
              @change="(v: string) => inv.updateRow(row.id, { couponRate: v })"
            />
            <span v-else>{{ row.couponRate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="到期日" width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.maturityDate"
              size="small"
              placeholder="YYYY-MM-DD"
              @change="(v: string) => inv.updateRow(row.id, { maturityDate: v })"
            />
            <span v-else>{{ row.maturityDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="总计" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="总计 = 数量 × 面值/单价">{{ fmt(row.bookTotal) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="②报表日库存有价证券" align="center">
        <el-table-column label="数量" width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.stockQuantity"
              size="small"
              :controls="false"
              style="width: 100%"
              @update:model-value="(v: number) => inv.updateRow(row.id, { stockQuantity: v ?? 0 })"
            />
            <span v-else>{{ fmt(row.stockQuantity) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="面值/单价" width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.stockFaceValue"
              size="small"
              :controls="false"
              style="width: 100%"
              @update:model-value="(v: number) => inv.updateRow(row.id, { stockFaceValue: v ?? 0 })"
            />
            <span v-else>{{ fmt(row.stockFaceValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="总计" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmt(row.stockTotal) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="③对账单" align="center">
        <el-table-column label="数量" width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.stmtQuantity"
              size="small"
              :controls="false"
              style="width: 100%"
              @update:model-value="(v: number) => inv.updateRow(row.id, { stmtQuantity: v ?? 0 })"
            />
            <span v-else>{{ fmt(row.stmtQuantity) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="面值/单价" width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.stmtFaceValue"
              size="small"
              :controls="false"
              style="width: 100%"
              @update:model-value="(v: number) => inv.updateRow(row.id, { stmtFaceValue: v ?? 0 })"
            />
            <span v-else>{{ fmt(row.stmtFaceValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="总计" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmt(row.stmtTotal) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="④函证证券投资" align="center">
        <el-table-column label="数量" width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.confQuantity"
              size="small"
              :controls="false"
              style="width: 100%"
              @update:model-value="(v: number) => inv.updateRow(row.id, { confQuantity: v ?? 0 })"
            />
            <span v-else>{{ fmt(row.confQuantity) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="面值/单价" width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.confFaceValue"
              size="small"
              :controls="false"
              style="width: 100%"
              @update:model-value="(v: number) => inv.updateRow(row.id, { confFaceValue: v ?? 0 })"
            />
            <span v-else>{{ fmt(row.confFaceValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="总计" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmt(row.confTotal) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="⑤差异＝①−②−(③或④)" align="center">
        <el-table-column label="证据源" width="100">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.evidenceSource"
              size="small"
              @change="(v: string) => inv.updateRow(row.id, { evidenceSource: v as any })"
            >
              <el-option label="自动" value="auto" />
              <el-option label="对账单" value="statement" />
              <el-option label="函证" value="confirmation" />
              <el-option label="仅监盘" value="stocktake" />
            </el-select>
            <span v-else>{{ evidenceLabel(row.evidenceSource) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="数量" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'diff-warn': inv.isDiffAbnormal(row) }">
              {{ fmt(row.diffQuantity) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="总计" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'diff-warn': inv.isDiffAbnormal(row) }">
              {{ fmt(row.diffTotal) }}
            </span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            placeholder="差异原因"
            @change="(v: string) => inv.updateRow(row.id, { remark: v })"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!isReadonly"
            size="small"
            type="danger"
            link
            @click="inv.removeRow(row.id)"
          >删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals">
      <span>合计 · 账面 {{ fmt(inv.grandTotal.value.bookTotal) }}</span>
      <span>库存 {{ fmt(inv.grandTotal.value.stockTotal) }}</span>
      <span>对账单 {{ fmt(inv.grandTotal.value.stmtTotal) }}</span>
      <span>函证 {{ fmt(inv.grandTotal.value.confTotal) }}</span>
      <span :class="{ warn: Math.abs(inv.grandTotal.value.diffTotal) > 0.005 }">
        差异 {{ fmt(inv.grandTotal.value.diffTotal) }}
      </span>
    </div>

    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      :conclusion="inv.auditConclusion.value"
      @update:conclusion="(v: string) => { inv.auditConclusion.value = v }"
      note-ai-section="inventory-note"
      conclusion-ai-section="inventory-conclusion"
      note-placeholder="填写审计说明：获取开户/清单、对账单与函证情况；差异查明与处理；是否影响存在性/完整性认定。"
      note-hint="覆盖多源核对程序、差异原因与结论依据。"
      conclusion-hint="按 A/B/C 口径评价结存是否公允反映。"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, inject, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useG1Inventory, type G1InventoryRow } from '../../composables/useG1Inventory'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'
import G1ImportExportDropdown from '../G1ImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
  projectId?: string
}>()

const emit = defineEmits<{ imported: [] }>()

const wpId = computed(() => props.wpId ?? '')
const projectId = computed(() => props.projectId ?? '')
const confirmSyncing = ref(false)
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const inv = useG1Inventory({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const AUDIT_NOTE_KEY = 'G1-4-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})

function fmt(n: number): string {
  if (n == null || Number.isNaN(n)) return '—'
  if (n === 0) return '—'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function evidenceLabel(src: string): string {
  const map: Record<string, string> = {
    auto: '自动',
    statement: '对账单',
    confirmation: '函证',
    stocktake: '仅监盘',
  }
  return map[src] || src
}

function rowClass({ row }: { row: G1InventoryRow }) {
  return inv.isDiffAbnormal(row) ? 'row-diff' : ''
}

function onSyncDetail() {
  const n = inv.syncFromDetail()
  if (n > 0) ElMessage.success(`已从 G1-2 带入 ${n} 行账面结存`)
  else ElMessage.info('G1-2 暂无明细可带入')
}

function onSyncCount() {
  const n = inv.syncFromSecuritiesCount()
  if (n > 0) ElMessage.success(`已从 G1-11 回填 ${n} 行监盘数量`)
  else ElMessage.info('未匹配到 G1-11 监盘行')
}

async function onSyncConfirm() {
  if (!projectId.value) {
    ElMessage.warning('缺少项目上下文，无法从函证模块回填')
    return
  }
  confirmSyncing.value = true
  try {
    const n = await inv.syncFromConfirmationModule(projectId.value)
    const sync = inv.lastConfirmSync.value
    if (n > 0) {
      const fuzzy = sync?.fuzzyMatched ? `，其中模糊匹配 ${sync.fuzzyMatched}` : ''
      const miss = sync?.unmatchedConfirm?.length
        ? `；未匹配 ${sync.unmatchedConfirm.length} 行见下方清单`
        : ''
      ElMessage.success(`已从函证模块回填 ${n} 行④函证${fuzzy}${miss}`)
    } else if (sync?.unmatchedConfirm?.length) {
      ElMessage.warning(`函证有 ${sync.unmatchedConfirm.length} 行但未能匹配到结存表，请核对证券名称/代码`)
    } else {
      ElMessage.info('函证模块暂无可匹配的证券行（请先编制 G0-3S 或 G0-1）')
    }  } catch (e: any) {
    ElMessage.warning('函证回填失败：' + (e?.message || '未知错误'))
  } finally {
    confirmSyncing.value = false
  }
}

function onPushAdj() {
  const n = inv.pushDiffToAdjustment()
  if (n > 0) ElMessage.success(`已将 ${n} 行差异推送至 G1-3 调整分录`)
  else ElMessage.info('无差异行可推送')
}
</script>

<style scoped>
.g1-inventory { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-inventory :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.g1-inventory :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }
.section-head {
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 12px; margin-bottom: 12px; flex-wrap: wrap;
}
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; color: #1f2a37; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.guidance-details { margin-bottom: 10px; font-size: 12px; color: #606266; }
.guidance-details summary { cursor: pointer; color: #4b2d77; font-weight: 500; }
.guidance-content { margin-top: 8px; }
.guidance-content p { margin: 4px 0; }
.objective-alert { margin-bottom: 10px; }
.cross-alert { margin-bottom: 10px; }
.cross-list { margin: 6px 0 0; padding-left: 1.2em; font-size: 12px; line-height: 1.5; }
.cross-more { margin: 4px 0 0; font-size: 12px; color: #909399; }
.stats-bar {
  display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 10px;
  padding: 8px 12px; background: #f8f9fb; border: 1px solid #ebeef5;
  border-radius: 6px; font-size: 12px; color: #606266;
}
.stats-bar .warn, .totals .warn, .diff-warn { color: #e6a23c; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; }
:deep(.auto-calc-col) { background-color: #f5f7fa; }
:deep(.row-diff) { background-color: #fdf6ec; }
.totals {
  display: flex; gap: 16px; flex-wrap: wrap; margin: 10px 0 12px;
  font-size: 12px; color: #606266; font-weight: 600;
}
</style>
