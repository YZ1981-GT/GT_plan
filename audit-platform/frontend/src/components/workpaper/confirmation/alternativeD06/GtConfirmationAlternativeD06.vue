<template>
  <div class="gt-confirmation-alternative-d06">
    <!-- 旧格式降级 -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-alternative-d06__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <!-- 新格式：alternative-d06-v1 -->
    <template v-else>
      <!-- 顶部说明 -->
      <div class="gt-confirmation-alternative-d06__header-tip">
        <el-alert type="info" :closable="true" show-icon>
          提示③：对回函可能性不高的、余额重大的，发函同时执行替代程序。
        </el-alert>
      </div>

      <!-- 看板 -->
      <AlternativeD05Dashboard :metrics="data.metrics.value" />

      <!-- 主表 -->
      <AlternativeD05Master
        :companies="data.companies.value"
        :readonly="readonly"
        :is-dirty="data.isDirty.value"
        :get-completion-status="data.getCompletionStatus"
        :has-abnormal="data.hasAbnormal"
        :get-check-ratio="data.getCheckRatio"
        @select="handleSelectCompany"
        @add-company="handleAddCompany"
        @delete-company="handleDeleteCompany"
        @import-d01="handleImportD01"
        @import-excel="handleImportExcel"
        @export-excel="handleExportExcel"
        @save="handleSave"
      />

      <!-- Detail: 选中公司的详情 -->
      <template v-if="selectedCompany">
        <div class="gt-confirmation-alternative-d06__detail">
          <div class="detail-title">
            {{ selectedCompany.entity_name || '未命名公司' }} — 检查详情
          </div>

          <!-- 抽样配置 -->
          <div class="detail-section">
            <div class="detail-section__header">一、样本选取标准与规模</div>
            <el-form
              :model="selectedCompany.sampling || {}"
              label-width="100px"
              size="small"
              :disabled="readonly"
            >
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="测试范围">
                    <el-input
                      v-model="selectedCompany.sampling!.test_scope"
                      type="textarea"
                      :rows="2"
                      placeholder="如应收账款借方发生额所有凭证共XX笔金额XX、贷方发生额所有凭证共XX笔金额XX"
                      @change="markDirty"
                    />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="特定样本">
                    <el-input
                      v-model="selectedCompany.sampling!.specific_samples"
                      type="textarea"
                      :rows="2"
                      placeholder="XX金额以上（大额）、关联方/关联交易形成的款项、XX异常款项全部测试，共XX笔"
                      @change="markDirty"
                    />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="抽样总体">
                    <el-input
                      v-model="selectedCompany.sampling!.sampling_population"
                      placeholder="测试总体扣除特定样本以外的样本，共XX笔、金额XX"
                      @change="markDirty"
                    />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="样本量">
                    <el-input
                      v-model="selectedCompany.sampling!.sample_size"
                      placeholder="抽取XX笔"
                      @change="markDirty"
                    />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="抽样方法">
                    <el-select
                      v-model="selectedCompany.sampling!.sampling_method"
                      placeholder="选择抽样方法"
                      @change="markDirty"
                    >
                      <el-option value="随机选样" label="随机选样" />
                      <el-option value="系统选样" label="系统选样" />
                      <el-option value="货币单元抽样" label="货币单元抽样" />
                      <el-option value="随意选样" label="随意选样（非统计抽样适用）" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="抽样过程">
                    <el-input
                      v-model="selectedCompany.sampling!.sampling_process"
                      type="textarea"
                      :rows="2"
                      placeholder="使用IDEA（XX抽样工具）选择XX数量占比XX%的样本进行测试"
                      @change="markDirty"
                    />
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>
          </div>

          <!-- 余额汇总 -->
          <div class="detail-section">
            <div class="detail-section__header">二、余额汇总与检查比例</div>
            <el-form
              :model="selectedCompany.balance || {}"
              label-width="120px"
              size="small"
              :disabled="readonly"
              inline
            >
              <el-form-item label="函证项目">
                <el-input
                  v-model="selectedCompany.balance!.item_name"
                  placeholder="应收账款"
                  style="width: 120px"
                  @change="markDirty"
                />
              </el-form-item>
              <el-form-item label="年初余额">
                <el-input
                  v-model.number="selectedCompany.balance!.opening_balance"
                  type="number"
                  style="width: 120px"
                  @change="markDirty"
                />
              </el-form-item>
              <el-form-item label="借方发生额">
                <el-input
                  v-model.number="selectedCompany.balance!.debit_amount"
                  type="number"
                  style="width: 120px"
                  @change="markDirty"
                />
              </el-form-item>
              <el-form-item label="贷方发生额">
                <el-input
                  v-model.number="selectedCompany.balance!.credit_amount"
                  type="number"
                  style="width: 120px"
                  @change="markDirty"
                />
              </el-form-item>
              <el-form-item label="期末余额">
                <el-input
                  v-model.number="selectedCompany.balance!.closing_balance"
                  type="number"
                  style="width: 120px"
                  @change="markDirty"
                />
              </el-form-item>
              <el-form-item label="本期销售金额">
                <el-input
                  v-model.number="selectedCompany.balance!.sales_amount"
                  type="number"
                  style="width: 140px"
                  @change="markDirty"
                />
              </el-form-item>
              <el-form-item label="收款检查比例">
                <span class="ratio-display">{{ formatRatio(data.getCheckRatio(selectedCompany, 'receipt')) }}</span>
              </el-form-item>
              <el-form-item label="出库检查比例">
                <span class="ratio-display">{{ formatRatio(data.getCheckRatio(selectedCompany, 'shipment')) }}</span>
              </el-form-item>
            </el-form>
          </div>

          <!-- 4 区块检查表 -->
          <div class="detail-section">
            <div class="detail-section__header">三、检查过程记录</div>
            <CheckBlock
              v-for="bt in blockTypes"
              :key="bt"
              :config="blockConfigs[bt]"
              :rows="getBlockRows(selectedCompany, bt)"
              :totals="data.getBlockTotal(selectedCompany, bt)"
              :readonly="readonly"
              @add-row="data.addBlockRow(selectedCompany._company_id!, bt)"
              @delete-row="(rowId: string) => data.deleteBlockRow(selectedCompany!._company_id!, bt, rowId)"
              @update-field="(rowId: string, field: string, val: any) => data.updateBlockField(selectedCompany!._company_id!, bt, rowId, field, val)"
            />
          </div>

          <!-- 审计结论 -->
          <div class="detail-section">
            <div class="detail-section__header">四、审计说明与结论</div>
            <el-form
              :model="selectedCompany.conclusion || {}"
              label-width="80px"
              size="small"
              :disabled="readonly"
            >
              <el-form-item label="审计说明">
                <el-input
                  v-model="selectedCompany.conclusion!.audit_note"
                  type="textarea"
                  :rows="3"
                  placeholder="概述：（1）程序的测试情况、结果；（2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。"
                  @change="markDirty"
                />
              </el-form-item>
              <el-form-item label="审计结论">
                <el-radio-group v-model="selectedCompany.conclusion!.conclusion_type" @change="markDirty">
                  <el-radio value="A">A - 替代程序结果支持余额</el-radio>
                  <el-radio value="B">B - 部分事项待进一步确认</el-radio>
                  <el-radio value="C">C - 存在重大异常需扩大程序</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item v-if="selectedCompany.conclusion?.conclusion_type" label="结论文本">
                <el-input
                  v-model="selectedCompany.conclusion!.conclusion_text"
                  type="textarea"
                  :rows="2"
                  @change="markDirty"
                />
              </el-form-item>
              <!-- 异常未决提示 -->
              <el-alert
                v-if="data.hasAbnormal(selectedCompany)"
                type="warning"
                :closable="false"
                show-icon
                class="mt-8"
              >
                当前存在异常行，请确认是否需要调整或扩大替代程序范围。
              </el-alert>
            </el-form>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useAlternativeD06Data } from './composables/useAlternativeD06Data'
import type { AlternativeCompany, BlockType, CheckRow } from '../alternativeD05/alternativeD05Types'
import { BLOCK_COLUMN_CONFIGS_D06 } from './blockColumnConfigsD06'

// 复用 D0-5 的 Dashboard 和 Master 组件
import AlternativeD05Dashboard from '../alternativeD05/AlternativeD05Dashboard.vue'
import AlternativeD05Master from '../alternativeD05/AlternativeD05Master.vue'
// 复用 D0-5 的 CheckBlock 组件
import CheckBlock from '../alternativeD05/CheckBlock.vue'

const GtGridSheet = defineAsyncComponent(() => import('../../GtGridSheet.vue'))

const props = defineProps<{
  htmlData: any
  readonly: boolean
  wpId?: string
  projectId?: string
  wpCode?: string
  year?: string
}>()

const emit = defineEmits<{
  (e: 'save', payload: any): void
}>()

// ─── 格式检测 ────────────────────────────────────────────────────────────────

const htmlDataRef = computed(() => props.htmlData)
const isNewFormat = computed(() => props.htmlData?._format === 'alternative-d06-v1')

// ─── 数据核心（D06 专属 composable） ─────────────────────────────────────────

const data = useAlternativeD06Data({
  htmlData: () => props.htmlData,
  readonly: props.readonly,
})

// ─── 区块配置（D06 专属列定义） ──────────────────────────────────────────────

const blockTypes: BlockType[] = ['block1', 'block2', 'block3', 'block4']
const blockConfigs = BLOCK_COLUMN_CONFIGS_D06

// ─── 选中公司 ────────────────────────────────────────────────────────────────

const selectedCompany = computed<AlternativeCompany | undefined>(() => {
  if (!data.selectedCompanyId.value) return data.companies.value[0]
  return data.companies.value.find((c) => c._company_id === data.selectedCompanyId.value)
})

function getBlockRows(company: AlternativeCompany, blockType: BlockType): CheckRow[] {
  const key = `${blockType}_rows` as keyof AlternativeCompany
  return (company[key] as CheckRow[]) || []
}

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function handleSelectCompany(companyId: string) {
  data.selectedCompanyId.value = companyId
}

function handleAddCompany() {
  const company = data.addCompany()
  data.selectedCompanyId.value = company._company_id!
}

function handleDeleteCompany(companyId: string) {
  data.deleteCompany(companyId)
}

function handleImportD01() {
  // TODO: 跨底稿引用获取 D0-1 未回函应收账款公司
  console.log('[GtConfirmationAlternativeD06] 从 D0-1 带入未回函应收账款公司（待接入）')
}

function handleImportExcel() {
  // TODO: 复用 useExcelIO
  console.log('[GtConfirmationAlternativeD06] Excel 导入')
}

function handleExportExcel() {
  // TODO: 复用 useExcelIO 导出模板
  console.log('[GtConfirmationAlternativeD06] 导出模板')
}

function handleSave() {
  const payload = data.buildPayload()
  emit('save', payload)
}

function markDirty() {
  data.isDirty.value = true
}

function formatRatio(val: number | null): string {
  if (val === null) return 'N/A'
  return `${val.toFixed(1)}%`
}
</script>

<style scoped>
.gt-confirmation-alternative-d06 {
  padding: 8px 0;
}

.gt-confirmation-alternative-d06__legacy-notice {
  margin-bottom: 12px;
}

.gt-confirmation-alternative-d06__header-tip {
  margin-bottom: 12px;
}

.gt-confirmation-alternative-d06__detail {
  margin-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 12px;
}

.detail-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--el-text-color-primary);
}

.detail-section {
  margin-bottom: 16px;
}

.detail-section__header {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  padding: 4px 8px;
  background: var(--el-fill-color-light);
  border-radius: 3px;
}

.ratio-display {
  font-weight: 700;
  color: var(--el-color-primary);
  font-size: 14px;
}

.mt-8 { margin-top: 8px; }
</style>
