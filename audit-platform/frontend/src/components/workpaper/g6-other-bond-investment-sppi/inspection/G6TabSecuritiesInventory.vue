<template>
  <div class="g6-tab-securities-inventory">
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实其他债权投资对应有价证券期末的存在性与数量准确性，通过账实核对确认账面数量与实际持仓相符。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:G6-9" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ inventory.totalCount.value }} 行</el-tag>
      <el-tag v-if="inventory.restrictedCount.value > 0" size="small" type="warning">
        {{ inventory.restrictedCount.value }}项受限
      </el-tag>
      <el-button
        v-if="!props.isReadonly"
        size="small"
        type="primary"
        plain
        :loading="syncing"
        @click="syncFromG62"
      >从 G6-2 同步清单</el-button>
      <el-button
        v-if="!props.isReadonly"
        size="small"
        type="warning"
        plain
        :loading="pushingAdj"
        :disabled="inventory.varianceCount.value === 0"
        @click="pushVarianceToG64"
      >差异 → G6-4 调整草稿</el-button>
    </div>

    <!-- 盘点元数据 -->
    <el-card shadow="never" class="meta-card">
      <template #header>
        <div class="section-header"><span class="section-title">盘点程序信息</span></div>
      </template>
      <div class="meta-grid">
        <div class="meta-field">
          <label>盘点日</label>
          <el-date-picker
            :model-value="inventory.meta.value.inventoryDate || undefined"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择盘点日"
            size="small"
            :disabled="props.isReadonly"
            style="width: 100%"
            @update:model-value="(v: string | null) => onInventoryDateChange(v || '')"
          />
        </div>
        <div class="meta-field">
          <label>是否资产负债表日</label>
          <el-radio-group
            :model-value="bsDateRadio"
            size="small"
            :disabled="props.isReadonly"
            @update:model-value="onBsDateChange"
          >
            <el-radio-button :value="'yes'">是</el-radio-button>
            <el-radio-button :value="'no'">否</el-radio-button>
            <el-radio-button :value="'unset'">未定</el-radio-button>
          </el-radio-group>
        </div>
        <div class="meta-field">
          <label>参加人员</label>
          <el-input
            :model-value="inventory.meta.value.participants"
            size="small"
            :disabled="props.isReadonly"
            placeholder="盘点人员、监盘人员..."
            @update:model-value="(v: string) => updateMetaAndSave('participants', v)"
          />
        </div>
        <div class="meta-field">
          <label>第三方托管机构</label>
          <el-input
            :model-value="inventory.meta.value.custodyInstitution"
            size="small"
            :disabled="props.isReadonly"
            placeholder="中债登/上清所/券商等"
            @update:model-value="(v: string) => updateMetaAndSave('custodyInstitution', v)"
          />
        </div>
        <div class="meta-field meta-field-wide">
          <label>覆盖范围</label>
          <el-input
            :model-value="inventory.meta.value.coverageNote"
            size="small"
            :disabled="props.isReadonly"
            placeholder="盘点范围、抽样比例或全覆盖说明..."
            @update:model-value="(v: string) => updateMetaAndSave('coverageNote', v)"
          />
        </div>
      </div>
      <el-alert
        v-if="inventory.needsRollForward.value"
        type="warning"
        :closable="false"
        show-icon
        class="rollforward-alert"
        title="盘点日非资产负债表日：请编制 G6-10 盘点倒轧表，将盘点数量推算至基准日。"
      />
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">有价证券盘点表（G6-9）</span>
          <div class="section-actions">
            <el-tag v-if="inventory.varianceCount.value > 0" type="danger" size="small">
              {{ inventory.varianceCount.value }}项差异
            </el-tag>
            <el-button size="small" @click="openReview('G6-9-securities-inventory')">💬复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="inventory.items.value"
        border
        size="small"
        class="inventory-table"
        highlight-current-row
        row-key="id"
      >
        <el-table-column label="序号" width="50" align="center">
          <template #default="{ row }">{{ row.seq }}</template>
        </el-table-column>

        <el-table-column label="证券名称" min-width="160">
          <template #default="{ row }">
            <div class="name-cell">
              <el-input
                v-if="!props.isReadonly"
                :model-value="row.securitiesName"
                size="small"
                placeholder="证券名称..."
                @update:model-value="(v: string) => inventory.updateItem(row.id, 'securitiesName', v)"
              />
              <span v-else>{{ row.securitiesName || '-' }}</span>
              <el-button
                v-if="!props.isReadonly"
                size="small"
                type="danger"
                link
                class="delete-btn"
                @click="inventory.removeItem(row.id)"
              >🗑️</el-button>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="证券代码" width="100">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              :model-value="row.securitiesCode"
              size="small"
              placeholder="代码..."
              @update:model-value="(v: string) => inventory.updateItem(row.id, 'securitiesCode', v)"
            />
            <span v-else>{{ row.securitiesCode || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="面值" width="95" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly"
              :model-value="row.faceValue"
              size="small"
              :controls="false"
              :precision="2"
              style="width: 85px"
              @update:model-value="(v: number | undefined) => inventory.updateItem(row.id, 'faceValue', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.faceValue) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="数量(盘点)" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly"
              :model-value="row.countQuantity"
              size="small"
              :controls="false"
              :precision="0"
              style="width: 90px"
              @update:model-value="(v: number | undefined) => inventory.updateItem(row.id, 'countQuantity', v ?? 0)"
            />
            <span v-else>{{ row.countQuantity }}</span>
          </template>
        </el-table-column>

        <el-table-column label="数量(账面)" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!props.isReadonly"
              :model-value="row.bookQuantity"
              size="small"
              :controls="false"
              :precision="0"
              style="width: 90px"
              @update:model-value="(v: number | undefined) => inventory.updateItem(row.id, 'bookQuantity', v ?? 0)"
            />
            <span v-else>{{ row.bookQuantity }}</span>
          </template>
        </el-table-column>

        <el-table-column label="差异" width="80" align="right">
          <template #default="{ row }">
            <el-tooltip content="盘点数量 - 账面数量" placement="top">
              <span class="formula-cell" :style="inventory.getVarianceCellStyle(row)">{{ row.variance }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="差异原因" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              :model-value="row.varianceReason"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="差异原因..."
              :class="{ 'variance-reason-required': inventory.isVarianceReasonMissing(row) }"
              @update:model-value="(v: string) => inventory.updateItem(row.id, 'varianceReason', v)"
            />
            <span v-else>{{ row.varianceReason || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="差异结论" width="110">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              :model-value="row.varianceConclusion"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="结论..."
              @update:model-value="(v: string) => inventory.updateItem(row.id, 'varianceConclusion', v)"
            />
            <span v-else>{{ row.varianceConclusion || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="权属主体" width="110">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              :model-value="row.ownershipEntity"
              size="small"
              placeholder="账户/主体"
              @update:model-value="(v: string) => inventory.updateItem(row.id, 'ownershipEntity', v)"
            />
            <span v-else>{{ row.ownershipEntity || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="受限" width="110">
          <template #default="{ row }">
            <el-select
              v-if="!props.isReadonly"
              :model-value="row.restrictionType || ''"
              size="small"
              clearable
              placeholder="类型"
              style="width: 100%"
              @update:model-value="(v: string) => inventory.updateItem(row.id, 'restrictionType', v || '')"
            >
              <el-option
                v-for="opt in INVENTORY_RESTRICTION_OPTIONS"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
            <span v-else>{{ restrictionLabel(row.restrictionType) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="受限说明" min-width="110">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              :model-value="row.restrictionNote"
              size="small"
              placeholder="说明..."
              @update:model-value="(v: string) => inventory.updateItem(row.id, 'restrictionNote', v)"
            />
            <span v-else>{{ row.restrictionNote || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="证据索引" min-width="110">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              :model-value="row.evidenceIndex"
              size="small"
              placeholder="对账单"
              @update:model-value="(v: string) => inventory.updateItem(row.id, 'evidenceIndex', v)"
            />
            <span v-else-if="!row.evidenceIndex">-</span>
            <div v-if="row.evidenceIndex" class="row-index-chip">
              <GtIndexChip :value="row.evidenceIndex" :context-project-id="projectId" />
            </div>
          </template>
        </el-table-column>

        <el-table-column label="索引" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              :model-value="row.indexRef"
              size="small"
              placeholder="索引"
              @update:model-value="(v: string) => inventory.updateItem(row.id, 'indexRef', v)"
            />
            <span v-else-if="!row.indexRef">-</span>
            <div v-if="row.indexRef" class="row-index-chip">
              <GtIndexChip :value="row.indexRef" :context-project-id="projectId" />
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-alert
        v-if="inventory.varianceValidationErrors.value.length > 0"
        type="warning"
        :closable="false"
        class="variance-alert"
      >
        <template #title>差异原因必填提示：以下项目存在差异但未填写原因</template>
        <ul class="variance-error-list">
          <li v-for="item in inventory.varianceValidationErrors.value" :key="item.row.id">
            {{ item.row.securitiesName }}（差异: {{ item.row.variance }}）
          </li>
        </ul>
      </el-alert>

      <div class="bottom-actions">
        <el-button
          v-if="!props.isReadonly"
          type="primary"
          size="small"
          @click="inventory.addItem()"
        >+ 新增行</el-button>
        <G6SppiImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G6-9"
          :disabled="props.isReadonly"
          @imported="onImported"
        />
        <span class="row-count">共 {{ inventory.totalCount.value }} 行</span>
      </div>
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header"><span class="section-title">审计说明</span></div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="props.isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述盘点程序的执行情况及结果、与第三方托管对账单的核对情况、差异追查与处理、拟调整与未调整事项及其影响。"
        @update:model-value="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">审计结论</span>
          <div class="section-actions">
            <el-button
              size="small"
              :disabled="props.isReadonly || aiLoading"
              :loading="aiLoading"
              @click="handleAi"
            >✨ AI辅助</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="inventory.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="props.isReadonly"
        placeholder="对有价证券盘点结果的审计结论..."
        @input="handleConclusionInput"
      />
    </el-card>

    <details class="guide-details">
      <summary>📋 编制提示</summary>
      <div class="guide-content">
        <p>1. <b>建议顺序</b>：先在 G6-2 维护证券清单与账面持仓 → 本表同步并完成账实核对 → 盘点日非报表日时编 G6-10 → 拟调整差异写入 G6-4。</p>
        <p>2. 优先用「从 G6-2 同步清单」带入证券名称、代码、面值与账面数量（请先在 G6-2 维护持仓数量），再填盘点数量。</p>
        <p>3. 盘点日应与被审计单位确认；若非资产负债表日，须编制倒轧表（G6-10）。</p>
        <p>4. 差异不为零时须填写差异原因/结论；未填将阻断审计结论保存。</p>
        <p>5. 逐项核对证券名称、代码与登记结算机构持仓；标注权属主体与质押/冻结/限售。</p>
        <p>6. 获取第三方托管机构对账单，并在「证据索引」列引用。</p>
        <p>7. 拟调整差异可用「差异 → G6-4 调整草稿」按 |数量差|×单位面值估算金额写入 Main 底稿，须人工复核。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabSecuritiesInventory.vue — G6-9 有价证券盘点表
 * 持久化：G6-9-securities-inventory-data + G6-9-rows 双写
 */
import { computed, inject, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useG6SppiInventory,
  INVENTORY_RESTRICTION_OPTIONS,
  type InventoryMeta,
  type SecuritiesInventoryData,
} from '../../composables/useG6SppiInventory'
import { useG6SppiFormData } from '../../composables/useG6SppiFormData'
import {
  parseG6ChecklistPayload,
  fetchG62DetailRows,
  fetchG62BalanceSheetDate,
  mapG62RowsToInventorySeeds,
  buildG69VarianceAdjustmentDrafts,
  fetchG64AdjustmentEntries,
  mergeG64EntriesWithG69Drafts,
  saveG64AdjustmentEntries,
} from '../../composables/g6CrossHelpers'
import { useG6SppiAiGenerate } from '../../composables/useG6SppiAiGenerate'
import GtIndexChip from '../../GtIndexChip.vue'
import G6SppiImportExportDropdown from '../G6SppiImportExportDropdown.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'imported'): void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
function openReview(sectionId: string): void {
  openReviewDialog(sectionId)
}

type G6SppiFormDataApi = ReturnType<typeof useG6SppiFormData>
const injectedFormData = inject<G6SppiFormDataApi | null>('g6SppiFormData', null)
const formData = injectedFormData ?? useG6SppiFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const inventory = useG6SppiInventory()
const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, loading: aiLoading } = useG6SppiAiGenerate(wpIdRef)

const DATA_KEY = 'G6-9-securities-inventory-data'
const ROWS_KEY = 'G6-9-rows'
const NOTE_KEY = 'G6-9-securities-inventory-audit-note'
const auditNote = ref('')
const syncing = ref(false)
const pushingAdj = ref(false)

const bsDateRadio = computed(() => {
  if (inventory.meta.value.isBalanceSheetDate === true) return 'yes'
  if (inventory.meta.value.isBalanceSheetDate === false) return 'no'
  return 'unset'
})

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  formData.debouncedSave(NOTE_KEY, { remark: val })
}

function updateMetaAndSave<K extends keyof InventoryMeta>(field: K, value: InventoryMeta[K]): void {
  if (props.isReadonly) return
  inventory.updateMeta(field, value)
  handleSave()
}

function onInventoryDateChange(date: string): void {
  updateMetaAndSave('inventoryDate', date)
}

function onBsDateChange(val: string | number | boolean | undefined): void {
  const v = String(val || 'unset')
  const mapped = v === 'yes' ? true : v === 'no' ? false : null
  updateMetaAndSave('isBalanceSheetDate', mapped)
}

function initFromData(): void {
  const primary = parseG6ChecklistPayload(formData.allResponses.value.get(DATA_KEY))
  if (primary && Array.isArray(primary.items)) {
    inventory.loadData(primary as SecuritiesInventoryData)
    return
  }
  const flat = parseG6ChecklistPayload(formData.allResponses.value.get(ROWS_KEY))
  if (Array.isArray(flat) && flat.length) {
    inventory.loadData({
      items: flat,
      auditConclusion: typeof primary?.auditConclusion === 'string' ? primary.auditConclusion : '',
      meta: primary?.meta,
    } as SecuritiesInventoryData)
    return
  }
  const content = formData.parseContent()
  if (content.inventory) {
    inventory.loadData(content.inventory as SecuritiesInventoryData)
  }
}

onMounted(async () => {
  await formData.loadAll()
  initFromData()
  const noteResp = formData.allResponses.value.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
})

onBeforeUnmount(() => {
  handleSave()
  formData.flushPending()
})

watch(() => props.htmlData, (newData) => {
  if (!newData) return
  // 已有 checklist 时勿被 render 壳覆盖
  if (formData.allResponses.value.get(DATA_KEY) || formData.allResponses.value.get(ROWS_KEY)) return
  initFromData()
})

function handleSave(): void {
  if (props.isReadonly) return
  const nested = inventory.toJSON()
  formData.debouncedSaveBatch([
    { itemId: DATA_KEY, data: { conclusion: JSON.stringify(nested) } },
    { itemId: ROWS_KEY, data: { conclusion: JSON.stringify(inventory.flattenRows()) } },
  ])
  emit('save')
}

watch(() => inventory.items.value, () => { handleSave() }, { deep: true })

watch(() => inventory.auditConclusion.value, () => {
  if (!inventory.isVarianceValid.value) return
  handleSave()
})

function handleConclusionInput(): void {
  if (!inventory.assertVarianceValidForSave('保存审计结论')) return
  handleSave()
}

async function onImported(): Promise<void> {
  await formData.loadAll()
  initFromData()
  const noteResp = formData.allResponses.value.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
  emit('imported')
}

async function syncFromG62(): Promise<void> {
  if (props.isReadonly) return
  syncing.value = true
  try {
    const [rows, bsDate] = await Promise.all([
      fetchG62DetailRows(props.projectId, props.wpId),
      fetchG62BalanceSheetDate(props.projectId, props.wpId),
    ])
    const seeds = mapG62RowsToInventorySeeds(rows)
    if (!seeds.length) {
      ElMessage.warning('未从 G6-2 取到投资项目，请先维护明细表')
      return
    }
    const { added, updated } = inventory.mergeSeedsFromDetail(seeds)
    if (bsDate && !inventory.meta.value.inventoryDate) {
      inventory.updateMeta('inventoryDate', bsDate)
      if (inventory.meta.value.isBalanceSheetDate == null) {
        inventory.updateMeta('isBalanceSheetDate', true)
      }
    }
    handleSave()
    ElMessage.success(
      `已从 G6-2 同步：新增 ${added} 项，更新 ${updated} 项` +
        (bsDate ? `；已带入资产负债表日 ${bsDate}` : ''),
    )
  } catch {
    ElMessage.warning('同步 G6-2 失败，请稍后重试')
  } finally {
    syncing.value = false
  }
}

async function pushVarianceToG64(): Promise<void> {
  if (props.isReadonly) return
  if (!inventory.assertVarianceValidForSave('生成调整草稿')) return
  const varianceItems = inventory.items.value.filter((r) => inventory.hasVariance(r))
  if (!varianceItems.length) {
    ElMessage.warning('当前无账实数量差异')
    return
  }

  let { pairs, skipped } = buildG69VarianceAdjustmentDrafts(varianceItems, {
    onlyProposedAdjust: true,
  })
  if (!pairs.length) {
    try {
      await ElMessageBox.confirm(
        `未找到标注「拟调整」的差异行（跳过 ${skipped.length} 项）。是否对全部可估算金额的差异生成草稿？`,
        '生成 G6-4 调整草稿',
        { type: 'warning', confirmButtonText: '全部生成', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
    ;({ pairs, skipped } = buildG69VarianceAdjustmentDrafts(varianceItems, {
      onlyProposedAdjust: false,
    }))
  }
  if (!pairs.length) {
    ElMessage.warning(skipped[0]?.reason || '无法生成调整草稿（缺少面值等）')
    return
  }

  const preview = pairs
    .map((p) =>
      `• ${p.securitiesName}：${p.direction === 'surplus' ? '盘盈' : '盘亏'} 数量差 ${p.variance}，估算 ${p.amount}（${p.amountBasis}）`,
    )
    .join('\n')
  try {
    await ElMessageBox.confirm(
      `将向 Main 底稿 G6-4 写入 ${pairs.length} 组借贷草稿（估算金额，须人工复核）：\n\n${preview}` +
        (skipped.length ? `\n\n另跳过 ${skipped.length} 项` : '') +
        '\n\n同来源旧草稿会被替换。确认继续？',
      '确认写入 G6-4',
      { type: 'warning', confirmButtonText: '确认写入', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  pushingAdj.value = true
  try {
    const { mainWpId, entries } = await fetchG64AdjustmentEntries(props.projectId, props.wpId)
    if (!mainWpId) {
      ElMessage.warning('未找到 Main 底稿实例，无法写入 G6-4')
      return
    }
    const merged = mergeG64EntriesWithG69Drafts(entries, pairs)
    const saved = await saveG64AdjustmentEntries(props.projectId, merged)
    if (saved) {
      ElMessage.success(`已写入 G6-4 调整草稿 ${pairs.length} 组（${pairs.length * 2} 行）`)
    } else {
      ElMessage.warning('未解析到 Main 底稿实例，写入 G6-4 已取消（避免写入当前 SPPI 实例）')
    }
  } catch {
    ElMessage.warning('写入 G6-4 失败，请稍后重试')
  } finally {
    pushingAdj.value = false
  }
}

async function handleAi(): Promise<void> {
  if (props.isReadonly) return
  if (!inventory.assertVarianceValidForSave('生成审计结论')) return
  const varianceItems = inventory.items.value
    .filter((r) => inventory.hasVariance(r))
    .map((r) => ({
      securitiesName: r.securitiesName,
      securitiesCode: r.securitiesCode,
      countQuantity: r.countQuantity,
      bookQuantity: r.bookQuantity,
      variance: r.variance,
      varianceReason: r.varianceReason,
      varianceConclusion: r.varianceConclusion,
      restrictionType: r.restrictionType,
      ownershipEntity: r.ownershipEntity,
    }))
  const restrictedItems = inventory.items.value
    .filter((r) => r.restrictionType && r.restrictionType !== 'none')
    .map((r) => ({
      securitiesName: r.securitiesName,
      restrictionType: r.restrictionType,
      restrictionNote: r.restrictionNote,
      evidenceIndex: r.evidenceIndex,
    }))
  const text = await generateAndConfirm(
    'inventory-conclusion',
    inventory.auditConclusion.value || '',
    {
      totalCount: inventory.totalCount.value,
      varianceCount: inventory.varianceCount.value,
      restrictedCount: inventory.restrictedCount.value,
      missingReasonCount: inventory.varianceValidationErrors.value.length,
      needsRollForward: inventory.needsRollForward.value,
      meta: inventory.meta.value,
      varianceItems,
      restrictedItems,
      auditNote: auditNote.value,
      sampleItems: inventory.items.value.slice(0, 20).map((r) => ({
        securitiesName: r.securitiesName,
        securitiesCode: r.securitiesCode,
        countQuantity: r.countQuantity,
        bookQuantity: r.bookQuantity,
        variance: r.variance,
        ownershipEntity: r.ownershipEntity,
        restrictionType: r.restrictionType,
      })),
    },
    'AI 盘点审计结论',
  )
  if (text) {
    inventory.auditConclusion.value = text
    handleSave()
  }
}

function restrictionLabel(v: string): string {
  return INVENTORY_RESTRICTION_OPTIONS.find((o) => o.value === v)?.label || v || '-'
}

function fmtNum(v: number | undefined, decimals = 2): string {
  if (v === undefined || v === null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

defineExpose({
  toJSON: () => inventory.toJSON(),
})
</script>

<style scoped>
.g6-tab-securities-inventory {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.chip-wrap { display: inline-flex; align-items: center; }
.row-index-chip { margin-top: 4px; }
.meta-card, .section-card, .conclusion-card { margin-bottom: 16px; }
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.section-title { font-weight: 600; font-size: 14px; }
.section-actions { display: flex; gap: 8px; align-items: center; }
.meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 16px;
}
.meta-field label {
  display: block;
  font-size: 12px;
  color: #606266;
  margin-bottom: 4px;
}
.meta-field-wide { grid-column: 1 / -1; }
.rollforward-alert { margin-top: 12px; }
.inventory-table { font-size: var(--wp-font-size, 13px); }
.name-cell { display: flex; align-items: center; gap: 4px; }
.name-cell .el-input { flex: 1; }
.delete-btn { flex-shrink: 0; }
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding: 2px 4px;
  display: inline-block;
}
.variance-reason-required :deep(.el-textarea__inner) {
  border-color: #f59e0b;
  background: #fffbeb;
}
.variance-alert { margin-top: 10px; }
.variance-error-list { margin: 4px 0 0; padding-left: 18px; }
.bottom-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin: 12px 0;
}
.row-count { color: #909399; font-size: 12px; }
.guide-details { margin-top: 16px; }
.guide-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  font-weight: 600;
}
.guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}
.guide-content p { margin: 0; }
@media (max-width: 900px) {
  .meta-grid { grid-template-columns: 1fr; }
}
</style>
