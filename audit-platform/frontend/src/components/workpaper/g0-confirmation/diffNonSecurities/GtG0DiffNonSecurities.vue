<template>
  <div class="gt-g0-diff-nonsec">
    <template v-if="!isNewFormat && !isLegacyReconcile">
      <div class="gt-g0-diff-nonsec__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <template v-else>
      <el-alert type="info" :closable="false" show-icon class="gt-g0-diff-nonsec__objective">
        <template #title>
          审计目标：核对非证券投资（长期股权投资等）函证回函的持股比例、投资金额及投资条款与账面记录是否一致，对差异查明原因（权益变动未同步／计量方法／协议条款理解差异），确认投资的存在、权利义务与计价认定。
        </template>
      </el-alert>

      <el-alert
        v-if="isLegacyReconcile"
        type="warning"
        :closable="false"
        show-icon
        class="gt-g0-diff-nonsec__legacy-hint"
      >
        <template #title>
          检测到本表既有数据录于共享差异调节表（单维金额）。已按投资金额维回显；持股比例／投资条款维需补录。
        </template>
      </el-alert>

      <div class="gt-g0-diff-nonsec__metrics">
        <el-row :gutter="12">
          <el-col :span="6"><el-statistic title="核对笔数" :value="data.metrics.value.total_count" /></el-col>
          <el-col :span="6"><el-statistic title="有差异笔数" :value="data.metrics.value.diff_count" /></el-col>
          <el-col :span="6"><el-statistic title="无差异笔数" :value="data.metrics.value.no_diff_count" /></el-col>
          <el-col :span="6"><el-statistic title="金额差异合计" :value="data.metrics.value.amount_diff_abs_total" :precision="2" /></el-col>
        </el-row>
      </div>

      <div class="gt-g0-diff-nonsec__toolbar">
        <div class="gt-g0-diff-nonsec__toolbar-left">
          <span class="gt-g0-diff-nonsec__section-title">非证券投资函证差异核对</span>
          <GtIndexChip value="wp:G0-4" />
          <el-tag size="small" type="info" effect="plain">共 {{ data.rows.value.length }} 行</el-tag>
          <el-tag size="small" type="warning" effect="plain">仅限非证券投资（证券投资填 G0-3）</el-tag>
        </div>
        <div class="gt-g0-diff-nonsec__toolbar-right">
          <el-button v-if="!readonly" type="primary" size="small" @click="handleAdd">新增行</el-button>
          <el-button v-if="!readonly" size="small" @click="handleImportFromG01">从 G0-1 带入</el-button>
          <el-button v-if="!readonly" type="success" size="small" :disabled="!data.isDirty.value" @click="handleSave">保存</el-button>
          <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
          <GtReviewTrigger section-id="G0-4-nonsec-diff" label="复核" />
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
        <el-table-column label="询证函索引号" width="120" fixed="left">
          <template #default="{ row }">
            <el-input v-if="!readonly" v-model="row.confirm_index" size="small" placeholder="关联G0-1" @change="updateField(row, 'confirm_index', row.confirm_index)" />
            <span v-else>{{ row.confirm_index }}</span>
          </template>
        </el-table-column>
        <el-table-column label="被投资单位名称" min-width="140" fixed="left">
          <template #default="{ row }">
            <el-input v-if="!readonly" v-model="row.entity_name" size="small" @change="updateField(row, 'entity_name', row.entity_name)" />
            <span v-else>{{ row.entity_name }}</span>
          </template>
        </el-table-column>
        <!-- 账面（①） -->
        <el-table-column label="账面数（①）" align="center">
          <el-table-column label="持股比例(%)" width="96" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!readonly" v-model="row.booked_ratio" size="small" :controls="false" :precision="2" @change="updateField(row, 'booked_ratio', row.booked_ratio)" />
              <span v-else>{{ row.booked_ratio }}</span>
            </template>
          </el-table-column>
          <el-table-column label="投资金额" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!readonly" v-model="row.booked_amount" size="small" :controls="false" :precision="2" @change="updateField(row, 'booked_amount', row.booked_amount)" />
              <span v-else>{{ row.booked_amount }}</span>
            </template>
          </el-table-column>
          <el-table-column label="投资条款" min-width="130">
            <template #default="{ row }">
              <el-input v-if="!readonly" v-model="row.booked_term" size="small" type="textarea" :autosize="{ minRows: 1 }" @change="updateField(row, 'booked_term', row.booked_term)" />
              <span v-else>{{ row.booked_term }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <!-- 回函（②） -->
        <el-table-column label="回函数（②）" align="center">
          <el-table-column label="持股比例(%)" width="96" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!readonly" v-model="row.reply_ratio" size="small" :controls="false" :precision="2" @change="updateField(row, 'reply_ratio', row.reply_ratio)" />
              <span v-else>{{ row.reply_ratio }}</span>
            </template>
          </el-table-column>
          <el-table-column label="投资金额" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!readonly" v-model="row.reply_amount" size="small" :controls="false" :precision="2" @change="updateField(row, 'reply_amount', row.reply_amount)" />
              <span v-else>{{ row.reply_amount }}</span>
            </template>
          </el-table-column>
          <el-table-column label="投资条款" min-width="130">
            <template #default="{ row }">
              <el-input v-if="!readonly" v-model="row.reply_term" size="small" type="textarea" :autosize="{ minRows: 1 }" @change="updateField(row, 'reply_term', row.reply_term)" />
              <span v-else>{{ row.reply_term }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <!-- 差异（③：比例=百分点差、金额=账面−回函、条款=一致/不一致不相减） -->
        <el-table-column label="差异（③）" align="center">
          <el-table-column label="差异比例(百分点)" width="112" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="账面持股比例 − 回函持股比例（百分点）">{{ diffCellText('ratio_diff', row.ratio_diff) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异金额" width="104" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="账面投资金额 − 回函投资金额">{{ diffCellText('amount_diff', row.amount_diff) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="投资条款差异" min-width="150">
            <template #default="{ row }">
              <template v-if="!readonly">
                <el-select v-model="row.term_match" size="small" placeholder="判断" style="width: 92px" @change="updateField(row, 'term_match', row.term_match)">
                  <el-option label="一致" value="一致" />
                  <el-option label="不一致" value="不一致" />
                </el-select>
                <el-input
                  v-if="row.term_match === '不一致'"
                  v-model="row.term_diff_note"
                  size="small"
                  placeholder="差异说明"
                  style="margin-top: 2px"
                  @change="updateField(row, 'term_diff_note', row.term_diff_note)"
                />
              </template>
              <span v-else>{{ row.term_match }}{{ row.term_diff_note ? '：' + row.term_diff_note : '' }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <!-- L 差异原因 -->
        <el-table-column label="差异原因" min-width="130">
          <template #default="{ row }">
            <el-select v-if="!readonly" v-model="row.diff_reason" size="small" allow-create filterable @change="updateField(row, 'diff_reason', row.diff_reason)">
              <el-option label="权益变动未同步" value="权益变动未同步" />
              <el-option label="计量方法差异" value="计量方法差异" />
              <el-option label="协议条款理解差异" value="协议条款理解差异" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.diff_reason }}</span>
          </template>
        </el-table-column>
        <!-- M 相关支持性证据 -->
        <el-table-column label="相关支持性证据" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!readonly" v-model="row.support_evidence" size="small" @change="updateField(row, 'support_evidence', row.support_evidence)" />
            <span v-else>{{ row.support_evidence }}</span>
          </template>
        </el-table-column>
        <!-- N 是否需要调账 -->
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
        <!-- O 备注 -->
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

      <div class="gt-g0-diff-nonsec__conclusion">
        <div class="gt-g0-diff-nonsec__conclusion-header">
          <span>审计说明与结论</span>
          <GtReviewTrigger section-id="G0-4-conclusion" label="复核" />
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

      <details class="gt-g0-diff-nonsec__tips">
        <summary>编制提示</summary>
        <p>
          依据 CAS 1312《函证》：非证券投资（长期股权投资等）通过被投资单位函证持股比例、投资金额及投资协议条款。
          差异按三维核对——持股比例差异以<strong>百分点</strong>计、投资金额差异 = 账面 − 回函、投资条款仅判断<strong>是否一致</strong>不做数值相减。
          本表仅填<strong>非证券投资</strong>；证券投资（数量/市价/公允价值）填 G0-3，同一被投资单位不在两表重复录入。
          有差异行以底色高亮，须记录差异原因并评估是否需要调整分录。
        </p>
      </details>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { useG0DiffNonSecurities } from './composables/useG0DiffNonSecurities'
import type { NonSecuritiesDiffRow } from './nonSecuritiesDiffTypes'
import {
  WorkpaperRuntimeContextKey,
  type WorkpaperRuntimeContext,
} from '../../composables/useWorkpaperScaffold'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { DisplayPrefs_Key } from '../../composables/displayPrefsKey'
import { isDiffAmountColumn } from '../g0DiffSourceManifest'

const GtGridSheet = defineAsyncComponent(() => import('../../GtGridSheet.vue'))

/**
 * 金额格式单一真源（store 成员，非模块级导出）。
 * 🔴 平台铁律写法 = setup 顶层 `inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()`：
 *    优先用底稿主入口注入的**同一个** store 实例，无宿主 provide 时才回退自取。
 * 🔴 必须在 setup 顶层取 —— `useDisplayPrefsStore()` 是 setup 作用域 composable，
 *    写进函数体会静默失效。
 */
const prefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

/**
 * 派生格显示值（Task 3 / Requirement 3）。
 *
 * 🔴 本表两个派生列语义**相反**：`amount_diff` 是金额（要千分符 + 2 位小数），
 *    `ratio_diff` 是**百分点**（套金额格式会把 3.5 个百分点显示成「3.50 元」，
 *    在「报表/附注金额默认元」的平台语境下直接误导审计判断）。
 *    故逐列语义只由 `g0DiffSourceManifest` 的 `kind` 决定，组件不写第二份判定。
 */
function diffCellText(field: string, val: unknown): string {
  if (val == null || val === '') return ''
  if (isDiffAmountColumn('nonSecurities', field)) return prefs.fmt(val)
  return String(val)
}

const props = defineProps<{
  htmlData: any
  readonly: boolean
  wpId?: string
  projectId?: string
}>()

const emit = defineEmits<{ (e: 'save', payload: any): void }>()

const htmlDataRef = computed(() => props.htmlData)
const isNewFormat = computed(() => props.htmlData?._format === 'diff-nonsecurities-v1')
const isLegacyReconcile = computed(() => props.htmlData?._format === 'diff-reconcile-v1')

const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
const openVersionHistory = () => runtime?.version.openVersionHistory()

const data = useG0DiffNonSecurities({
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
 * 从 G0-1 带入询证函索引号（Req 1.5 / 3.1 / 3.4）——跨底稿自动带入待平台统一接线，
 * 不静默断链：提示以「询证函索引号」列手工填写关联 G0-1。
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

function updateField(row: NonSecuritiesDiffRow, field: string, value: unknown) {
  if (!row._row_id) return
  data.updateRow(row._row_id, field, value)
}

function rowClassName({ row }: { row: NonSecuritiesDiffRow }) {
  return data.rowHasDiff(row) ? 'row-has-diff' : ''
}
</script>

<style scoped>
.gt-g0-diff-nonsec {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.gt-g0-diff-nonsec__objective,
.gt-g0-diff-nonsec__legacy-hint,
.gt-g0-diff-nonsec__metrics {
  margin-bottom: 12px;
}
.gt-g0-diff-nonsec__toolbar {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.gt-g0-diff-nonsec__toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-g0-diff-nonsec__section-title {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.gt-g0-diff-nonsec__toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-g0-diff-nonsec__conclusion {
  margin-top: 16px;
}
.gt-g0-diff-nonsec__conclusion-header {
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
.gt-g0-diff-nonsec__tips {
  margin-top: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  padding: 6px 10px;
}
.gt-g0-diff-nonsec__tips summary {
  cursor: pointer;
  font-weight: 600;
  color: var(--el-text-color-regular);
}
.gt-g0-diff-nonsec__tips p {
  margin: 8px 0 0;
  line-height: 1.6;
}
:deep(.row-has-diff) {
  background-color: #fdf6ec !important;
}
</style>
