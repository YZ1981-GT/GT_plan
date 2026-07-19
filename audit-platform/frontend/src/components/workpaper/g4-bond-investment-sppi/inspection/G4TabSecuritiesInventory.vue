<template>
  <div class="g4-tab-securities-inventory">
    <!-- 一、审计目标（对齐纸质底稿） -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="一、审计目标：资产负债表中所记录的债权投资是否存在，且已经记录在适当账户中。"
      style="margin-bottom: 12px"
    />

    <!-- 日差倒轧提示 -->
    <el-alert
      v-if="needsRollForward"
      type="warning"
      :closable="false"
      show-icon
      class="roll-alert"
      :title="`盘点日（${header.countDate}）≠ 资产负债表日（${effectiveBalanceSheetDate}）：须编制 G4-8 倒轧表，可将本表结果一键推送。`"
      style="margin-bottom: 12px"
    />
    <el-alert
      v-else-if="header.countDate && !effectiveBalanceSheetDate"
      type="info"
      :closable="false"
      show-icon
      title="已填盘点日，尚无资产负债表日：请在「盘点信息」中填写报表日，以便判断是否需要倒轧。"
      style="margin-bottom: 12px"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:G4-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G4-8" :context-project-id="projectId" /></span>
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="info">共 {{ items.length }} 行</el-tag>
        <el-tag size="small" :type="headerStatus.missing.length ? 'warning' : 'success'">
          盘点信息 {{ headerStatus.filled }}/{{ headerStatus.total }}
        </el-tag>
        <el-tag v-if="needsRollForward" size="small" type="warning">需倒轧</el-tag>
        <el-button size="small" @click="headerDialogVisible = true">盘点信息</el-button>
        <el-button
          size="small"
          type="success"
          plain
          :disabled="isReadonly || validItemCount === 0"
          @click="onPushToG48"
        >
          推送 G4-8
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="isReadonly || !aiAvailable"
          :loading="aiLoading"
          @click="fillAiConclusion"
        >
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" :icon="ChatDotRound" @click="handleReview('G4-7有价证券盘点表')">复核</el-button>
      </div>
    </div>

    <div class="section-header">
      <h3 class="section-title">G4-7 有价证券盘点表</h3>
    </div>

    <!-- 二、审计过程 · 1. 盘点情况 -->
    <div class="header-summary" @click="headerDialogVisible = true">
      <div class="summary-main">
        <span class="summary-title">二、审计过程 · 1. 盘点情况</span>
        <el-tag size="small" :type="headerStatus.missing.length ? 'warning' : 'success'">
          基础信息 {{ headerStatus.filled }}/{{ headerStatus.total }}
        </el-tag>
        <el-button link type="primary" size="small" @click.stop="headerDialogVisible = true">
          {{ isReadonly ? '查看' : '弹窗填写' }}
        </el-button>
      </div>
      <div class="summary-meta">
        <span>单位：{{ header.company || '—' }}</span>
        <span>盘点日：{{ header.countDate || '—' }}</span>
        <span>报表日：{{ effectiveBalanceSheetDate || '—' }}</span>
        <span>地点：{{ header.location || '—' }}</span>
        <span>监盘人：{{ header.observer || '—' }}</span>
        <span>盘点人：{{ header.counter || '—' }}</span>
        <span>复核人：{{ header.reviewer || '—' }}</span>
      </div>
      <p v-if="header.narrative" class="narrative">{{ header.narrative }}</p>
      <p v-else class="narrative placeholder">
        点击填写盘点单位、日期、地点与人员后，将自动生成监盘叙述（可再手改）。
      </p>
      <p v-if="headerStatus.missing.length" class="missing-hint">
        待填：{{ headerStatus.missing.join('、') }}
      </p>
    </div>

    <!-- 盘点明细表 -->
    <el-table
      :data="items"
      border
      stripe
      size="small"
      show-summary
      :summary-method="getSummary"
      class="inventory-detail-table"
    >
      <el-table-column label="序号" prop="seq" width="60" align="center" />
      <el-table-column label="证券名称" min-width="140">
        <template #default="{ row }">
          <el-input
            v-model="row.securitiesName"
            size="small"
            :disabled="isReadonly"
            @change="inventoryLogic.updateItem(row.id, { securitiesName: row.securitiesName })"
          />
        </template>
      </el-table-column>
      <el-table-column label="面值" min-width="110">
        <template #default="{ row }">
          <el-input-number
            v-model="row.faceValue"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @change="inventoryLogic.updateItem(row.id, { faceValue: row.faceValue })"
          />
        </template>
      </el-table-column>
      <el-table-column label="数量" min-width="90">
        <template #default="{ row }">
          <el-input-number
            v-model="row.quantity"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @change="inventoryLogic.updateItem(row.id, { quantity: row.quantity })"
          />
        </template>
      </el-table-column>
      <el-table-column label="总计" min-width="120">
        <template #default="{ row }">
          <el-tooltip content="总计 = 面值 × 数量" placement="top">
            <span class="formula-cell">{{ row.total.toFixed(2) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="票面利率(%)" min-width="110">
        <template #default="{ row }">
          <el-input-number
            v-model="row.couponRate"
            size="small"
            :controls="false"
            :precision="4"
            :disabled="isReadonly"
            @change="inventoryLogic.updateItem(row.id, { couponRate: row.couponRate })"
          />
        </template>
      </el-table-column>
      <el-table-column label="到期日" min-width="130">
        <template #default="{ row }">
          <el-date-picker
            v-model="row.maturityDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            style="width: 100%;"
            :disabled="isReadonly"
            @change="inventoryLogic.updateItem(row.id, { maturityDate: row.maturityDate })"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" align="center">
        <template #default="{ row }">
          <el-button
            type="danger"
            link
            size="small"
            :disabled="isReadonly || items.length <= 1"
            @click="inventoryLogic.removeItem(row.id)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="inventoryLogic.addItem()">
        + 新增盘点明细
      </el-button>
      <slot name="importExport">
        <G4SppiImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G4-7"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
      </slot>
    </div>

    <!-- 二、审计过程 · 2. 倒轧衔接 -->
    <p class="cross-ref">
      2. 有价证券盘点倒轧：见
      <span class="chip-wrap"><GtIndexChip value="wp:G4-8" :context-project-id="projectId" /></span>。
      可点击「推送 G4-8」写入盘点日实存；盘点日 ≠ 资产负债表日时须继续登记增减并完成倒轧。
    </p>

    <G4AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditDescription"
      v-model:conclusion="auditConclusion"
      note-title="三、审计说明"
      conclusion-title="四、审计结论"
      note-placeholder="可记录：监盘范围与地点、与现金同时盘点情况、多地点同时盘点控制、权属/质押限制、异常及跟进等。"
      conclusion-placeholder="就债权投资存在性及账户归属作出结论；盘点日≠报表日须说明已衔接 G4-8。"
      @update:note="inventoryLogic.setAuditDescription"
      @update:conclusion="inventoryLogic.setAuditConclusion"
    />

    <!-- 编制提示（对齐纸质底稿蓝色注意事项） -->
    <details class="guidance-details" open>
      <summary>编制提示 / 监盘注意</summary>
      <div class="guidance-content">
        <p>1. 盘点应与现金盘点同时进行；审计人员不宜亲自经手有价证券。</p>
        <p>2. 存放在不同地点的有价证券应同时盘点，以防转移后重复盘点或漏盘。</p>
        <p>3. 若盘点日不是资产负债表日，应将盘点日数量调节至资产负债表日，编制
          <span class="chip-wrap inline"><GtIndexChip value="wp:G4-8" :context-project-id="projectId" /></span>
          倒轧表。
        </p>
        <p>4. 明细表：总计 = 面值 × 数量（自动）；合计行自动汇总面值、数量与总计。</p>
        <p>5. 盘点信息头需填写单位、日期、地点、监盘人、盘点人；叙述句可一键按信息重写后手改。</p>
      </div>
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
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="资产负债表日">
              <el-date-picker
                v-model="draftHeader.balanceSheetDate"
                type="date"
                value-format="YYYY-MM-DD"
                style="width: 100%"
                placeholder="截止日 / 报表日"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="盘点地点" required>
              <el-input v-model="draftHeader.location" placeholder="如：公司财务室 / 托管行" />
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
/**
 * G4TabSecuritiesInventory.vue — G4-7 有价证券盘点表
 *
 * 对齐致同纸质「有价证券盘点表G4-7」：
 * 一审计目标 → 二审计过程(盘点情况+倒轧交叉索引) → 三审计说明 → 四审计结论
 * + 纸质底稿蓝色监盘注意事项
 */
import { inject, toRef, computed, ref, watch } from 'vue'
import { ChatDotRound, MagicStick } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import G4AuditTextCards from '../../g4-bond-investment-main/G4AuditTextCards.vue'
import G4SppiImportExportDropdown from '../G4SppiImportExportDropdown.vue'
import {
  useG4SppiInventory,
  buildInventoryNarrative,
  type InventoryHeader,
} from '@/composables/useG4SppiInventory'
import { useG4SppiFormData } from '@/composables/useG4SppiFormData'
import { useG4SppiAiGenerate } from '../../composables/useG4SppiAiGenerate'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'imported'): void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog')
function handleReview(sectionId: string): void {
  openReviewDialog?.(sectionId)
}

const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG4SppiAiGenerate(wpIdRef)

const formData = useG4SppiFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
formData.loadAll()

const projectBalanceSheetDate = computed(() => {
  const d = props.htmlData?.balanceSheetDate
    ?? props.htmlData?.cutoffDate
    ?? props.htmlData?.cutoff_date
    ?? ''
  return String(d).slice(0, 10)
})

const inventoryLogic = useG4SppiInventory({
  allResponses: formData.allResponses,
  debouncedSave: formData.debouncedSave,
  saveImmediate: formData.saveImmediate,
  isReadonly: toRef(props, 'isReadonly'),
  projectBalanceSheetDate,
})

const {
  header,
  items,
  summary,
  headerStatus,
  effectiveBalanceSheetDate,
  needsRollForward,
  validItemCount,
  auditDescription,
  auditConclusion,
} = inventoryLogic

const headerDialogVisible = ref(false)
const draftHeader = ref<InventoryHeader>({ ...header.value })

watch(headerDialogVisible, (open) => {
  if (open) {
    draftHeader.value = {
      ...header.value,
      balanceSheetDate: header.value.balanceSheetDate || effectiveBalanceSheetDate.value,
    }
  }
})

function onRegenInDialog(): void {
  draftHeader.value = {
    ...draftHeader.value,
    narrative: buildInventoryNarrative(draftHeader.value),
  }
}

function saveHeaderDialog(): void {
  const narrative = draftHeader.value.narrative?.trim()
    ? draftHeader.value.narrative
    : buildInventoryNarrative(draftHeader.value)
  inventoryLogic.updateHeader({ ...draftHeader.value, narrative }, false)
  headerDialogVisible.value = false
}

async function onPushToG48(): Promise<void> {
  if (props.isReadonly) return
  if (needsRollForward.value) {
    try {
      await ElMessageBox.confirm(
        `盘点日（${header.value.countDate}）与资产负债表日（${effectiveBalanceSheetDate.value}）不一致。推送后请打开 G4-8 登记增减并完成倒轧。是否继续推送？`,
        '需要倒轧',
        { confirmButtonText: '推送', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return
    }
  }
  inventoryLogic.pushToReconciliation()
}

async function fillAiConclusion(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'inventory-conclusion',
    auditConclusion.value || '',
    {
      行数: items.value.length,
      有效证券行: validItemCount.value,
      盘点日期: header.value.countDate,
      资产负债表日: effectiveBalanceSheetDate.value,
      需倒轧: needsRollForward.value,
      盘点地点: header.value.location,
      监盘人: header.value.observer,
      盘点人: header.value.counter,
      证券总计: summary.value.totalTotal,
      信息完备: headerStatus.value.missing.length === 0,
      待填字段: headerStatus.value.missing.join('、') || '无',
    },
    'AI 审计结论',
  )
  if (text) inventoryLogic.setAuditConclusion(text)
}

function getSummary({ columns }: { columns: any[]; data: any[] }) {
  const sums: string[] = []
  columns.forEach((col: any, idx: number) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    if (col.property === 'seq' || idx === 0) { sums[idx] = ''; return }
    switch (idx) {
      case 2:
        sums[idx] = summary.value.faceValueTotal.toFixed(2)
        break
      case 3:
        sums[idx] = String(summary.value.quantityTotal)
        break
      case 4:
        sums[idx] = summary.value.totalTotal.toFixed(2)
        break
      default:
        sums[idx] = ''
    }
  })
  return sums
}
</script>

<style scoped>
.g4-tab-securities-inventory { font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; }

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.chip-wrap.inline { display: inline-flex; vertical-align: middle; }

.header-summary {
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  background: #fafafa;
  cursor: pointer;
}
.summary-main {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.summary-title { font-weight: 600; color: #303133; }
.summary-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: #606266;
  margin-bottom: 6px;
}
.narrative {
  margin: 0;
  font-size: 12px;
  color: #303133;
  line-height: 1.6;
}
.narrative.placeholder { color: #909399; }
.missing-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: #e6a23c;
}

.inventory-detail-table { margin-bottom: 8px; }

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

.table-actions {
  display: flex;
  gap: 8px;
  margin: 8px 0 12px;
  flex-wrap: wrap;
}

.cross-ref {
  margin: 0 0 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}

.guidance-details {
  margin-top: 16px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #606266;
}
.guidance-content {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  line-height: 1.8;
}
.guidance-content p { margin: 0; }
</style>
