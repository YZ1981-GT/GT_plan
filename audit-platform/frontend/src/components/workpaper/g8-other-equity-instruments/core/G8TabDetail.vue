<template>
  <div class="g8-detail" data-testid="g8-detail-table">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表按被投资单位分行列示其他权益工具投资（科目1503）的成本、公允价值及 OCI 累计变动明细。</p>
        <p>2. 灰底列（期初审定/期末余额/审定数）为自动计算列：期末余额 = 期初审定 + 增加 − 减少 + FV变动。</p>
        <p>3. 指定为以公允价值计量且变动计入 OCI 属不可撤销选择，须逐项填列指定原因；公允价值层次（Level 1/2/3）应与 G8-4 公允价值测试一致。</p>
        <p>4. 明细合计应与审定表 G8-1（科目1503）勾稽一致。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实其他权益工具投资各被投资单位期末成本、公允价值及 OCI 累计变动明细的准确与完整，验证公允价值层次划分与指定恰当，为审定表 G8-1（科目1503）提供明细支撑。"
      class="objective-alert"
    />

    <div class="toolbar">
      <h3>G8-2 明细表</h3>
      <div class="head-actions">
        <G8ImportExportDropdown :wp-id="wpId" sheet="G8-2" @imported="onImported" />
        <GtReviewTrigger section-id="G8-2-detail" />
        <el-button v-if="!isReadonly" size="small" data-testid="g8-detail-add" @click="detail.addRow()">+ 新增行</el-button>
      </div>
    </div>
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G8-2" /></span>
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-segmented v-model="detail.activeTab.value" :options="tabOptions" size="small" data-testid="g8-detail-tabs" />
    <el-table :data="detail.rows.value" border size="small" style="font-size:13px;margin-top:8px" max-height="520"
      highlight-current-row @current-change="onRowChange">
      <el-table-column prop="seq" label="#" width="44" align="center" fixed />
      <template v-if="detail.activeTab.value === 'basic'">
        <el-table-column label="被投资单位" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.investeeName" size="small" @update:model-value="(v: string) => detail.updateRow(row.rowId, { investeeName: v })" />
            <span v-else>{{ row.investeeName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="投资比例" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.investmentRatio" size="small" :controls="false" :step="0.01" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { investmentRatio: v ?? 0 })" />
            <span v-else>{{ (row.investmentRatio * 100).toFixed(2) }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.openingBalance" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingBalance: v ?? 0 })" />
            <span v-else>{{ fmt(row.openingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初调整" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.openingAdjustment" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingAdjustment: v ?? 0 })" />
            <span v-else>{{ fmt(row.openingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初审定" width="96" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.openingAdjusted) }}</span></template>
        </el-table-column>
        <el-table-column label="增加" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.increaseAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { increaseAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.increaseAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减少" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.decreaseAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { decreaseAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.decreaseAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="FV变动" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.fvChangeAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { fvChangeAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.fvChangeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="96" align="right">
          <template #default="{ row }"><span class="formula-cell" title="期初审定+增加-减少+FV变动">{{ fmt(row.closingBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="调整数" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.closingAdjustment" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { closingAdjustment: v ?? 0 })" />
            <span v-else>{{ fmt(row.closingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="96" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.closingAdjusted) }}</span></template>
        </el-table-column>
        <el-table-column label="指定OCI原因" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.designationReason" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { designationReason: v })" />
            <span v-else>{{ row.designationReason }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else>
        <el-table-column label="被投资单位" prop="investeeName" min-width="120" fixed />
        <el-table-column label="OCI累计" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.ociCumulativeChange" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { ociCumulativeChange: v ?? 0 })" />
            <span v-else>{{ fmt(row.ociCumulativeChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期OCI" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.ociCurrentChange" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { ociCurrentChange: v ?? 0 })" />
            <span v-else>{{ fmt(row.ociCurrentChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="OCI转留存" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.ociToRetainedEarnings" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { ociToRetainedEarnings: v ?? 0 })" />
            <span v-else>{{ fmt(row.ociToRetainedEarnings) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转入原因" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.transferReason" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { transferReason: v })" />
            <span v-else>{{ row.transferReason }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发函情况" width="96">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.confirmationStatus" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { confirmationStatus: v })" />
            <span v-else>{{ row.confirmationStatus }}</span>
          </template>
        </el-table-column>
        <el-table-column label="层次" width="96">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.fairValueLevel" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { fairValueLevel: v })">
              <el-option v-for="o in detail.fvLevelOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.fairValueLevel }}</span>
          </template>
        </el-table-column>
        <el-table-column label="估值方法" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.valuationMethod" size="small" allow-create filterable
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { valuationMethod: v })">
              <el-option v-for="o in detail.valuationMethodOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.valuationMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column label="持股数" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.shareCount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { shareCount: v ?? 0 })" />
            <span v-else>{{ row.shareCount }}</span>
          </template>
        </el-table-column>
        <el-table-column label="每股公允价值" width="108" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.pricePerShare" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { pricePerShare: v ?? 0 })" />
            <span v-else>{{ fmt(row.pricePerShare) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公允价值合计" width="108" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.fairValueTotal" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { fairValueTotal: v ?? 0 })" />
            <span v-else>{{ fmt(row.fairValueTotal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { remark: v })" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </template>
      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="detail.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-table v-if="detail.rows.value.length" :data="[detail.totals.value]" border size="small" class="totals-table" style="font-size:13px;margin-top:8px">
      <el-table-column label="合计" width="120" />
      <el-table-column label="期初审定" width="100" align="right">
        <template #default="{ row }">{{ fmt(row.openingAdjusted) }}</template>
      </el-table-column>
      <el-table-column label="增加" width="96" align="right">
        <template #default="{ row }">{{ fmt(row.increaseAmount) }}</template>
      </el-table-column>
      <el-table-column label="减少" width="96" align="right">
        <template #default="{ row }">{{ fmt(row.decreaseAmount) }}</template>
      </el-table-column>
      <el-table-column label="FV变动" width="96" align="right">
        <template #default="{ row }">{{ fmt(row.fvChangeAmount) }}</template>
      </el-table-column>
      <el-table-column label="期末余额" width="96" align="right">
        <template #default="{ row }">{{ fmt(row.closingBalance) }}</template>
      </el-table-column>
      <el-table-column label="审定数" width="96" align="right">
        <template #default="{ row }"><strong>{{ fmt(row.closingAdjusted) }}</strong></template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="audit-note-card">
      <template #header>审计说明</template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写审计说明：（1）明细核对程序及结果；（2）各被投资单位成本、公允价值、OCI 变动的核实情况及异常事项。" />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>审计结论</template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="填写审计结论：明细金额是否准确、完整，是否与审定表 G8-1（科目1503）勾稽一致。" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G8ImportExportDropdown from '../G8ImportExportDropdown.vue'
import { useG8Detail } from '../../composables/useG8Detail'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const detail = useG8Detail({
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

const AUDIT_NOTE_KEY = 'G8-2-audit-note'
const AUDIT_CONCLUSION_KEY = 'G8-2-audit-conclusion'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(AUDIT_CONCLUSION_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_CONCLUSION_KEY, { conclusion: null, remark: v })
})

const tabOptions = [
  { label: '基础信息', value: 'basic' },
  { label: '公允价值+OCI', value: 'fv_oci' },
]

function onRowChange(row: { seq?: number } | undefined) {
  if (row?.seq) detail.activeRowIndex.value = row.seq - 1
}

function onImported() { emit('imported') }

function fmt(n: number) {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g8-detail { font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; margin-bottom: 8px; align-items: center; }
.head-actions { display: flex; gap: 8px; }
.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
.guidance-details { margin-bottom: 10px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 10px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin: 8px 0; flex-wrap: wrap; gap: 8px; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 12px; }
</style>
