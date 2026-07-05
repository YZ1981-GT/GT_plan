<template>
  <div class="gt-confirmation-diff-securities">
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-diff-securities__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <template v-else>
      <div class="gt-confirmation-diff-securities__metrics">
        <el-row :gutter="12">
          <el-col :span="6">
            <el-statistic title="核对笔数" :value="data.metrics.value.total_count" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="有差异笔数" :value="data.metrics.value.diff_count" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="无差异笔数" :value="data.metrics.value.no_diff_count" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="最大单笔差异" :value="data.metrics.value.max_abs_diff" :precision="2" />
          </el-col>
        </el-row>
      </div>

      <div class="gt-confirmation-diff-securities__toolbar">
        <span class="gt-confirmation-diff-securities__section-title">证券投资函证差异核对</span>
        <div class="gt-confirmation-diff-securities__toolbar-right">
          <el-button v-if="!readonly" type="primary" size="small" @click="handleAdd">新增行</el-button>
          <el-button v-if="!readonly" type="success" size="small" :disabled="!data.isDirty.value" @click="handleSave">
            保存
          </el-button>
          <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
          <GtReviewTrigger section-id="G0-3S-securities-diff" label="复核" />
        </div>
      </div>

      <el-table
        :data="data.rows.value"
        border
        size="small"
        style="width: 100%; font-size: 13px"
        :row-class-name="rowClassName"
        max-height="520"
      >
        <el-table-column prop="seq" label="序号" width="55" align="center" />
        <el-table-column label="证券名称" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!readonly" v-model="row.security_name" size="small" @change="updateField(row, 'security_name', row.security_name)" />
            <span v-else>{{ row.security_name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="证券代码" width="100">
          <template #default="{ row }">
            <el-input v-if="!readonly" v-model="row.security_code" size="small" @change="updateField(row, 'security_code', row.security_code)" />
            <span v-else>{{ row.security_code }}</span>
          </template>
        </el-table-column>
        <el-table-column label="证券类型" width="90">
          <template #default="{ row }">
            <el-select v-if="!readonly" v-model="row.security_type" size="small" @change="updateField(row, 'security_type', row.security_type)">
              <el-option label="股票" value="股票" />
              <el-option label="基金" value="基金" />
              <el-option label="债券" value="债券" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.security_type }}</span>
          </template>
        </el-table-column>
        <el-table-column label="回函持仓" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!readonly" v-model="row.confirmed_qty" size="small" :controls="false" @change="updateField(row, 'confirmed_qty', row.confirmed_qty)" />
            <span v-else>{{ row.confirmed_qty }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面持仓" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!readonly" v-model="row.booked_qty" size="small" :controls="false" @change="updateField(row, 'booked_qty', row.booked_qty)" />
            <span v-else>{{ row.booked_qty }}</span>
          </template>
        </el-table-column>
        <el-table-column label="数量差异" width="95" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ row.qty_diff }}</span>
          </template>
        </el-table-column>
        <el-table-column label="回函单位公允值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!readonly" v-model="row.confirmed_unit_fv" size="small" :controls="false" :precision="2" @change="updateField(row, 'confirmed_unit_fv', row.confirmed_unit_fv)" />
            <span v-else>{{ row.confirmed_unit_fv }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面单位公允值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!readonly" v-model="row.booked_unit_fv" size="small" :controls="false" :precision="2" @change="updateField(row, 'booked_unit_fv', row.booked_unit_fv)" />
            <span v-else>{{ row.booked_unit_fv }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公允价值差异" width="105" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ row.fv_diff }}</span>
          </template>
        </el-table-column>
        <el-table-column label="回函总市值" width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!readonly" v-model="row.confirmed_market_value" size="small" :controls="false" :precision="2" @change="updateField(row, 'confirmed_market_value', row.confirmed_market_value)" />
            <span v-else>{{ row.confirmed_market_value }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面总市值" width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!readonly" v-model="row.booked_market_value" size="small" :controls="false" :precision="2" @change="updateField(row, 'booked_market_value', row.booked_market_value)" />
            <span v-else>{{ row.booked_market_value }}</span>
          </template>
        </el-table-column>
        <el-table-column label="市值差异" width="95" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ row.market_value_diff }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异原因" min-width="130">
          <template #default="{ row }">
            <el-select v-if="!readonly" v-model="row.diff_reason" size="small" @change="updateField(row, 'diff_reason', row.diff_reason)">
              <el-option label="估值时点差异" value="估值时点差异" />
              <el-option label="交易日与结算日差异" value="交易日与结算日差异" />
              <el-option label="计量方法差异" value="计量方法差异" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.diff_reason }}</span>
          </template>
        </el-table-column>
        <el-table-column label="调节事项" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!readonly" v-model="row.adjustment_note" size="small" @change="updateField(row, 'adjustment_note', row.adjustment_note)" />
            <span v-else>{{ row.adjustment_note }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核实结论" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!readonly" v-model="row.verify_conclusion" size="small" @change="updateField(row, 'verify_conclusion', row.verify_conclusion)" />
            <span v-else>{{ row.verify_conclusion }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!readonly" v-model="row.remark" size="small" @change="updateField(row, 'remark', row.remark)" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!readonly" label="操作" width="70" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="data.deleteRow(row._row_id!)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="gt-confirmation-diff-securities__conclusion">
        <div class="gt-confirmation-diff-securities__conclusion-header">
          <span>审计说明与结论</span>
          <GtReviewTrigger section-id="G0-3S-conclusion" label="复核" />
        </div>
        <el-form label-width="80px" size="small" :disabled="readonly">
          <el-form-item label="审计说明">
            <el-input v-model="data.auditNote.value" type="textarea" :rows="2" @change="markDirty" />
          </el-form-item>
          <el-form-item label="审计结论">
            <el-input v-model="data.conclusion.value" type="textarea" :rows="3" @change="markDirty" />
          </el-form-item>
        </el-form>
      </div>
    </template>

    <!-- 版本链抽屉 -->
    <GtWpVersionTrail
      v-if="wpId"
      ref="versionTrailRef"
      :workpaper-id="wpId"
      :project-id="projectId || ''"
    />

    <!-- 复核对话 -->
    <GtReviewDialog
      v-if="reviewDialog.isOpen.value && reviewDialog.activationParams.value"
      :key="reviewDialog.activationParams.value.sectionId"
      v-bind="reviewDialog.activationParams.value"
      @closed="reviewDialog.closeReviewDialog"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { useDiffSecuritiesData } from './composables/useDiffSecuritiesData'
import type { SecuritiesDiffRow } from './diffSecuritiesTypes'
import { useWorkpaperVersionToolbar } from '../../composables/useWorkpaperVersionToolbar'
import { useG0ReviewDialogProvide } from '../composables/useG0ReviewDialogProvide'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const GtGridSheet = defineAsyncComponent(() => import('../../../GtGridSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('../../version-trail/GtWpVersionTrail.vue'))
const GtReviewDialog = defineAsyncComponent(() => import('@/components/collaboration/GtReviewDialog.vue'))

const props = defineProps<{
  htmlData: any
  readonly: boolean
  wpId?: string
  projectId?: string
}>()

const emit = defineEmits<{ (e: 'save', payload: any): void }>()

const htmlDataRef = computed(() => props.htmlData)
const isNewFormat = computed(() => props.htmlData?._format === 'diff-securities-v1')

const wpIdRef = computed(() => props.wpId ?? '')
const projectIdRef = computed(() => props.projectId ?? '')

// ─── 版本链集成（autoSnapshot on save + 版本历史抽屉）───────────────────────
const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: projectIdRef })
const { versionTrailRef } = versionToolbar

// ─── 复核对话 provide（供 section 标题栏 GtReviewTrigger inject）─────────────
const reviewDialog = useG0ReviewDialogProvide({ wpId: wpIdRef, projectId: projectIdRef })

const data = useDiffSecuritiesData({
  htmlData: () => props.htmlData,
  readonly: props.readonly,
})

function markDirty() {
  data.isDirty.value = true
}

function handleAdd() {
  data.addRow()
}

function handleSave() {
  emit('save', data.buildPayload())
  data.isDirty.value = false
  versionToolbar.scheduleAutoSnapshot()
  ElMessage.success('已保存')
}

function updateField(row: SecuritiesDiffRow, field: string, value: unknown) {
  if (!row._row_id) return
  data.updateRow(row._row_id, field, value)
}

function rowClassName({ row }: { row: SecuritiesDiffRow }) {
  return data.rowHasDiff(row) ? 'row-has-diff' : ''
}
</script>

<style scoped>
.gt-confirmation-diff-securities {
  padding: 12px;
  font-size: 13px;
}
.gt-confirmation-diff-securities__metrics {
  margin-bottom: 12px;
}
.gt-confirmation-diff-securities__toolbar {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.gt-confirmation-diff-securities__section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.gt-confirmation-diff-securities__toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-confirmation-diff-securities__conclusion {
  margin-top: 16px;
}
.gt-confirmation-diff-securities__conclusion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--el-text-color-primary);
}
.formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  display: inline-block;
  min-width: 48px;
}
:deep(.row-has-diff) {
  background-color: #fdf6ec !important;
}
</style>
