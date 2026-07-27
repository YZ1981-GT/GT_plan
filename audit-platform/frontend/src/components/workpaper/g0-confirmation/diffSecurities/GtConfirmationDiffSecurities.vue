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
      <!-- 审计目标 -->
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="gt-confirmation-diff-securities__objective"
      >
        <template #title>
          审计目标：核对证券投资函证回函的持仓数量、单位公允价值及总市值与账面记录是否一致，对存在差异的项目查明原因（估值时点／交易结算日／计量方法差异），确认账面金额的准确性与计价认定。
        </template>
      </el-alert>

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
        <div class="gt-confirmation-diff-securities__toolbar-left">
          <span class="gt-confirmation-diff-securities__section-title">证券投资函证差异核对</span>
          <GtIndexChip value="wp:G0-3S" />
          <el-tag size="small" type="info" effect="plain">共 {{ data.rows.value.length }} 行</el-tag>
        </div>
        <div class="gt-confirmation-diff-securities__toolbar-right">
          <el-button v-if="!readonly" type="primary" size="small" @click="handleAdd">新增行</el-button>
          <el-button v-if="!readonly" size="small" @click="handleImportFromG01">从 G0-1 带入</el-button>
          <el-button v-if="!readonly" type="success" size="small" :disabled="!data.isDirty.value" @click="handleSave">
            保存
          </el-button>
          <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
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
        <el-table-column prop="seq" label="序号" width="52" align="center" fixed="left" />
        <!-- A 询证函索引号（关联 G0-1，可手工填/带入） -->
        <el-table-column label="询证函索引号" width="120" fixed="left">
          <template #default="{ row }">
            <el-input v-if="!readonly" v-model="row.confirm_index" size="small" placeholder="关联G0-1" @change="updateField(row, 'confirm_index', row.confirm_index)" />
            <span v-else>{{ row.confirm_index }}</span>
          </template>
        </el-table-column>
        <!-- B 证券名称 -->
        <el-table-column label="证券名称" min-width="110" fixed="left">
          <template #default="{ row }">
            <el-input v-if="!readonly" v-model="row.security_name" size="small" @change="updateField(row, 'security_name', row.security_name)" />
            <span v-else>{{ row.security_name }}</span>
          </template>
        </el-table-column>
        <!-- 源外增强：证券代码 / 证券类型（源模板无，保留不删） -->
        <el-table-column label="证券代码" width="96">
          <template #default="{ row }">
            <el-input v-if="!readonly" v-model="row.security_code" size="small" @change="updateField(row, 'security_code', row.security_code)" />
            <span v-else>{{ row.security_code }}</span>
          </template>
        </el-table-column>
        <el-table-column label="证券类型" width="86">
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
        <!-- C 资金账号 / D 开户名称 -->
        <el-table-column label="资金账号" width="110">
          <template #default="{ row }">
            <el-input v-if="!readonly" v-model="row.fund_account" size="small" @change="updateField(row, 'fund_account', row.fund_account)" />
            <span v-else>{{ row.fund_account }}</span>
          </template>
        </el-table-column>
        <el-table-column label="开户名称" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!readonly" v-model="row.account_holder" size="small" @change="updateField(row, 'account_holder', row.account_holder)" />
            <span v-else>{{ row.account_holder }}</span>
          </template>
        </el-table-column>
        <!-- 账面（E 数量 / F 市价单价 / G 账面余额） -->
        <el-table-column label="账面数（①）" align="center">
          <el-table-column label="账面数量" width="92" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!readonly" v-model="row.booked_qty" size="small" :controls="false" @change="updateField(row, 'booked_qty', row.booked_qty)" />
              <span v-else>{{ row.booked_qty }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面市价(单价)" width="108" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!readonly" v-model="row.booked_unit_fv" size="small" :controls="false" :precision="2" @change="updateField(row, 'booked_unit_fv', row.booked_unit_fv)" />
              <span v-else>{{ row.booked_unit_fv }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面余额" width="104" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!readonly" v-model="row.booked_market_value" size="small" :controls="false" :precision="2" @change="updateField(row, 'booked_market_value', row.booked_market_value)" />
              <span v-else>{{ row.booked_market_value }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <!-- 回函（H 数量 / I 市价单价 / J 回函公允价值） -->
        <el-table-column label="回函数（②）" align="center">
          <el-table-column label="回函数量" width="92" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!readonly" v-model="row.confirmed_qty" size="small" :controls="false" @change="updateField(row, 'confirmed_qty', row.confirmed_qty)" />
              <span v-else>{{ row.confirmed_qty }}</span>
            </template>
          </el-table-column>
          <el-table-column label="回函市价(单价)" width="108" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!readonly" v-model="row.confirmed_unit_fv" size="small" :controls="false" :precision="2" @change="updateField(row, 'confirmed_unit_fv', row.confirmed_unit_fv)" />
              <span v-else>{{ row.confirmed_unit_fv }}</span>
            </template>
          </el-table-column>
          <el-table-column label="回函公允价值" width="104" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!readonly" v-model="row.confirmed_market_value" size="small" :controls="false" :precision="2" @change="updateField(row, 'confirmed_market_value', row.confirmed_market_value)" />
              <span v-else>{{ row.confirmed_market_value }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <!-- 差异（K 数量 / L 市价 / M 公允价值，②−①，只读派生） -->
        <el-table-column label="差异（②−①）" align="center">
          <el-table-column label="差异数量" width="88" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="回函数量 − 账面数量">{{ row.qty_diff }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异市价(单价)" width="104" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="回函市价 − 账面市价">{{ row.fv_diff }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异公允价值" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="回函公允价值 − 账面余额">{{ row.market_value_diff }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <!-- N 差异原因 -->
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
        <!-- O 相关支持性证据 -->
        <el-table-column label="相关支持性证据" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!readonly" v-model="row.support_evidence" size="small" @change="updateField(row, 'support_evidence', row.support_evidence)" />
            <span v-else>{{ row.support_evidence }}</span>
          </template>
        </el-table-column>
        <!-- P 是否需要调账（判断列，源模板 P） -->
        <el-table-column label="是否需要调账" width="104" align="center">
          <template #default="{ row }">
            <el-select v-if="!readonly" v-model="row.need_adjust" size="small" placeholder="判断" @change="updateField(row, 'need_adjust', row.need_adjust)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="待定" value="待定" />
            </el-select>
            <span v-else>{{ row.need_adjust }}</span>
          </template>
        </el-table-column>
        <!-- 源外增强：调账说明（原自由文本，need_adjust 的说明保留） -->
        <el-table-column label="调账说明" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!readonly" v-model="row.adjustment_note" size="small" @change="updateField(row, 'adjustment_note', row.adjustment_note)" />
            <span v-else>{{ row.adjustment_note }}</span>
          </template>
        </el-table-column>
        <!-- 源外增强：核实结论 -->
        <el-table-column label="核实结论" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!readonly" v-model="row.verify_conclusion" size="small" @change="updateField(row, 'verify_conclusion', row.verify_conclusion)" />
            <span v-else>{{ row.verify_conclusion }}</span>
          </template>
        </el-table-column>
        <!-- Q 备注 -->
        <el-table-column label="备注" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!readonly" v-model="row.remark" size="small" @change="updateField(row, 'remark', row.remark)" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!readonly" label="操作" width="64" fixed="right">
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

      <!-- 编制提示 -->
      <details class="gt-confirmation-diff-securities__tips">
        <summary>编制提示</summary>
        <p>
          依据 CAS 1312《函证》：证券投资一般通过中国结算（中登）或托管券商函证持仓与市值。回函与账面存在差异时，
          应区分数量差异（持仓不符，追查交割单／对账单确认权属）与计价差异（单位公允值／总市值不符，多因估值时点或计量方法不同）。
          有差异行以底色高亮，须在"差异原因／调节事项／核实结论"中记录处理，并评估是否需要调整分录。
        </p>
      </details>
    </template>

  </div>
</template>

<script setup lang="ts">
import { computed, inject, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { useDiffSecuritiesData } from './composables/useDiffSecuritiesData'
import type { SecuritiesDiffRow } from './diffSecuritiesTypes'
import {
  WorkpaperRuntimeContextKey,
  type WorkpaperRuntimeContext,
} from '../../composables/useWorkpaperScaffold'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const GtGridSheet = defineAsyncComponent(() => import('../../GtGridSheet.vue'))

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

// ─── Runtime Boundary 统一提供版本链 + 复核（GtWpRenderer scaffold），本组件不再本地接线 ───
// version/review/displayPrefs/ai 由 GtWpRenderer 一次性 provide + GtWorkpaperRuntimeHosts 挂载。
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
const openVersionHistory = () => runtime?.version.openVersionHistory()

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

/**
 * 从 G0-1 带入询证函索引号（Req 1.5 / 3.1 / 3.4）。
 * 跨底稿 G0-1 汇总数据未在本组件 props 内提供（平台跨 sheet 引用尚未统一接线，
 * 共享 diffReconcile 的「从 X0-1 带入」亦为同款待接线状态）。
 * 故此处不静默断链：提示以「询证函索引号」列手工填写关联 G0-1（Req 3.4 手工填索引）。
 * 去重与映射逻辑已由 useG01ConfirmIndexImport 纯函数实现并单测（Property 8）。
 */
function handleImportFromG01() {
  ElMessage.info('请在「询证函索引号」列手工填写以关联 G0-1（跨底稿自动带入待平台统一接线后启用）')
}

function handleSave() {
  emit('save', data.buildPayload())
  data.isDirty.value = false
  runtime?.version.scheduleAutoSnapshot()
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
  font-size: var(--wp-font-size, 13px);
}
.gt-confirmation-diff-securities__objective {
  margin-bottom: 12px;
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
.gt-confirmation-diff-securities__toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-confirmation-diff-securities__section-title {
  font-size: var(--wp-font-size, 13px);
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
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--el-text-color-primary);
}
.formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  display: inline-block;
  min-width: 48px;
  padding: 0 4px;
  border-radius: 2px;
  background: var(--el-fill-color-light);
  cursor: help;
}
.gt-confirmation-diff-securities__tips {
  margin-top: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  padding: 6px 10px;
}
.gt-confirmation-diff-securities__tips summary {
  cursor: pointer;
  font-weight: 600;
  color: var(--el-text-color-regular);
}
.gt-confirmation-diff-securities__tips p {
  margin: 8px 0 0;
  line-height: 1.6;
}
:deep(.row-has-diff) {
  background-color: #fdf6ec !important;
}
</style>
