<template>
  <div class="alt-detail-panel">
    <!-- 抽样配置 -->
    <div class="detail-section">
      <div class="detail-section__header">一、样本选取标准与规模</div>
      <el-form :model="company.sampling || {}" label-width="100px" size="small" :disabled="readonly">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="测试范围">
              <el-input
                v-model="company.sampling!.test_scope"
                type="textarea"
                :rows="2"
                :placeholder="samplingScopePlaceholder"
                @change="emitDirty"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="特定样本">
              <el-input
                v-model="company.sampling!.specific_samples"
                type="textarea"
                :rows="2"
                placeholder="XX金额以上（大额）、关联方/关联交易形成的款项、XX异常款项全部测试，共XX笔"
                @change="emitDirty"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="抽样总体">
              <el-input
                v-model="company.sampling!.sampling_population"
                placeholder="测试总体扣除特定样本以外的样本，共XX笔、金额XX"
                @change="emitDirty"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="样本量">
              <el-input
                v-model="company.sampling!.sample_size"
                placeholder="抽取XX笔"
                @change="emitDirty"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="抽样方法">
              <el-select
                v-model="company.sampling!.sampling_method"
                placeholder="选择抽样方法"
                @change="emitDirty"
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
                v-model="company.sampling!.sampling_process"
                type="textarea"
                :rows="2"
                placeholder="使用IDEA（XX抽样工具）选择XX数量占比XX%的样本进行测试"
                @change="emitDirty"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </div>

    <!-- 余额汇总 -->
    <div class="detail-section">
      <div class="detail-section__header">二、余额汇总与检查比例</div>
      <div class="balance-cards">
        <!-- 左卡：余额数据 -->
        <div class="balance-card balance-card--data">
          <div class="balance-card__title">余额数据</div>
          <div class="balance-card__grid">
            <div class="balance-card__item">
              <span class="balance-card__label">函证项目</span>
              <el-input
                v-if="!readonly"
                v-model="company.balance!.item_name"
                size="small"
                :placeholder="itemNamePlaceholder"
                @change="emitDirty"
              />
              <span v-else class="balance-card__value">{{ company.balance?.item_name || '—' }}</span>
            </div>
            <div class="balance-card__item">
              <span class="balance-card__label">年初余额</span>
              <el-input
                v-if="!readonly"
                v-model.number="company.balance!.opening_balance"
                type="number"
                size="small"
                @change="emitDirty"
              />
              <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(company.balance?.opening_balance) }}</span>
            </div>
            <div class="balance-card__item">
              <span class="balance-card__label">借方发生额</span>
              <el-input
                v-if="!readonly"
                v-model.number="company.balance!.debit_amount"
                type="number"
                size="small"
                @change="emitDirty"
              />
              <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(company.balance?.debit_amount) }}</span>
            </div>
            <div class="balance-card__item">
              <span class="balance-card__label">贷方发生额</span>
              <el-input
                v-if="!readonly"
                v-model.number="company.balance!.credit_amount"
                type="number"
                size="small"
                @change="emitDirty"
              />
              <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(company.balance?.credit_amount) }}</span>
            </div>
            <div class="balance-card__item">
              <span class="balance-card__label">期末余额</span>
              <el-input
                v-if="!readonly"
                v-model.number="company.balance!.closing_balance"
                type="number"
                size="small"
                @change="emitDirty"
              />
              <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(company.balance?.closing_balance) }}</span>
            </div>
            <div class="balance-card__item">
              <span class="balance-card__label">{{ balanceFieldLabel }}</span>
              <el-input
                v-if="!readonly"
                v-model.number="company.balance![balanceField]"
                type="number"
                size="small"
                @change="emitDirty"
              />
              <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(company.balance?.[balanceField]) }}</span>
            </div>
          </div>
        </div>
        <!-- 右卡：检查比例指标 -->
        <div class="balance-card balance-card--ratio">
          <div class="balance-card__title">检查比例</div>
          <div class="ratio-indicators">
            <div v-for="r in ratios" :key="r.type" class="ratio-indicator">
              <div class="ratio-indicator__label">{{ r.label }}</div>
              <div class="ratio-indicator__value" :class="ratioClass(getCheckRatio(company, r.type))">
                {{ formatRatio(getCheckRatio(company, r.type)) }}
              </div>
              <div class="ratio-indicator__desc">{{ r.desc }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 4 区块检查表 -->
    <div class="detail-section">
      <div class="detail-section__header">三、检查过程记录</div>
      <CheckBlock
        v-for="bt in blockTypes"
        :key="bt"
        :config="blockConfigs[bt]"
        :rows="getBlockRows(company, bt)"
        :totals="getBlockTotal(company, bt)"
        :readonly="readonly"
        @add-row="addBlockRow(company._company_id!, bt)"
        @delete-row="(rowId: string) => deleteBlockRow(company._company_id!, bt, rowId)"
        @update-field="(rowId: string, field: string, val: any) => updateBlockField(company._company_id!, bt, rowId, field, val)"
      />
    </div>

    <!-- 审计结论 -->
    <div class="detail-section">
      <div class="detail-section__header">
        <span>四、审计说明与结论</span>
        <el-button
          v-if="!readonly"
          type="primary"
          size="small"
          plain
          :loading="aiLoading"
          style="margin-left: auto"
          @click="emit('ai-fill')"
        >
          AI 智能填充
        </el-button>
      </div>
      <el-form :model="company.conclusion || {}" label-width="80px" size="small" :disabled="readonly">
        <el-form-item label="审计说明">
          <el-input
            v-model="company.conclusion!.audit_note"
            type="textarea"
            :rows="3"
            :placeholder="auditNotePlaceholder"
            @change="emitDirty"
          />
        </el-form-item>
        <el-form-item label="审计结论">
          <el-radio-group v-model="company.conclusion!.conclusion_type" @change="emitDirty">
            <el-radio value="A">A - 替代程序结果支持余额</el-radio>
            <el-radio value="B">B - 部分事项待进一步确认</el-radio>
            <el-radio value="C">C - 存在重大异常需扩大程序</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="company.conclusion?.conclusion_type" label="结论文本">
          <el-input
            v-model="company.conclusion!.conclusion_text"
            type="textarea"
            :rows="2"
            @change="emitDirty"
          />
        </el-form-item>
        <!-- 异常未决提示 -->
        <el-alert
          v-if="hasAbnormal(company)"
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

<script setup lang="ts">
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import type { AlternativeCompany, BlockType, CheckRow, BalanceSummary } from './alternativeD05Types'
import type { BlockConfig } from './blockColumnConfigs'
import CheckBlock from './CheckBlock.vue'

/**
 * AlternativeDetailPanel — D0-5/F0-5/F0-6 替代程序「检查详情」共享面板。
 *
 * confirmation-alternative-structure-alignment 决策 5：F05/F06 拆子组件复用 D05，
 * 「不新造第二套」——此前 D05/F05/F06 各自内联同一份 Detail（抽样配置+余额卡片+4 区块+结论），
 * 抽出为单一共享组件，仅按 config prop 参数化差异（余额字段/比例/占位文案），
 * 数据仍由父组件的工厂 composable 驱动（company 为响应式对象引用，直接 mutate 透传）。
 *
 * 不含 K05/K06/L05/G06 的借贷拆表逻辑——那几套 block3/block2 splitByDirection 各自内联渲染，
 * 本面板仅服务不拆表的简单 4 区块套（D05/F05/F06）。
 */

interface RatioIndicator {
  /** getCheckRatio 的 type 入参（D05: receipt/shipment，F05/F06: payment/inbound） */
  type: string
  /** 指标标签（如「收款检查比例」/「付款检查比例」） */
  label: string
  /** 口径说明（如「区块③收款合计 / 本期销售额」） */
  desc: string
}

const props = defineProps<{
  company: AlternativeCompany
  readonly: boolean
  blockTypes: BlockType[]
  blockConfigs: Record<string, BlockConfig>
  /** 余额卡第 6 项字段（D05: sales_amount，F05/F06: purchase_amount） */
  balanceField: keyof BalanceSummary
  /** 第 6 项标签（三套均为「本期销售金额」，可覆盖） */
  balanceFieldLabel?: string
  /** 函证项目占位（合同负债/预付账款/应付账款） */
  itemNamePlaceholder?: string
  /** 抽样测试范围占位 */
  samplingScopePlaceholder?: string
  /** 审计说明占位 */
  auditNotePlaceholder?: string
  /** 检查比例指标（两项） */
  ratios: RatioIndicator[]
  aiLoading?: boolean
  // ─── 数据方法（父组件工厂 composable 透传） ───
  getBlockTotal: (company: AlternativeCompany, blockType: BlockType) => Record<string, number>
  getCheckRatio: (company: AlternativeCompany, type: string) => number | null
  addBlockRow: (companyId: string, blockType: BlockType) => void
  deleteBlockRow: (companyId: string, blockType: BlockType, rowId: string) => void
  updateBlockField: (companyId: string, blockType: BlockType, rowId: string, field: string, value: any) => void
  hasAbnormal: (company: AlternativeCompany) => boolean
}>()

const emit = defineEmits<{
  (e: 'mark-dirty'): void
  (e: 'ai-fill'): void
}>()

const prefs = useDisplayPrefsStore()

const balanceFieldLabel = props.balanceFieldLabel ?? '本期销售金额'
const itemNamePlaceholder = props.itemNamePlaceholder ?? ''
const samplingScopePlaceholder = props.samplingScopePlaceholder ?? ''
const auditNotePlaceholder =
  props.auditNotePlaceholder ??
  '概述：（1）程序的测试情况、结果；（2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。'

function emitDirty() {
  emit('mark-dirty')
}

function getBlockRows(company: AlternativeCompany, blockType: BlockType): CheckRow[] {
  const key = `${blockType}_rows` as keyof AlternativeCompany
  return (company[key] as CheckRow[]) || []
}

function formatRatio(val: number | null): string {
  if (val === null) return 'N/A'
  return `${val.toFixed(1)}%`
}

function formatAmount(val: number | undefined | null): string {
  if (val == null) return '—'
  return prefs.fmt(val)
}

function ratioClass(val: number | null): string {
  if (val === null) return 'ratio-indicator__value--na'
  if (val >= 80) return 'ratio-indicator__value--good'
  if (val >= 50) return 'ratio-indicator__value--warn'
  return 'ratio-indicator__value--danger'
}
</script>

<style scoped>
.detail-section {
  margin-bottom: 16px;
}

.detail-section__header {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  margin-bottom: 8px;
  padding: 4px 8px;
  background: var(--el-fill-color-light);
  border-radius: 3px;
  display: flex;
  align-items: center;
}

/* ─── 卡片式双栏：余额汇总与检查比例 ───────────────────────────────────── */

.balance-cards {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 12px;
}

.balance-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px 16px;
  background: #fafbfc;
}

.balance-card__title {
  font-size: 12px;
  font-weight: 600;
  color: #909399;
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.balance-card__grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 10px 16px;
}

.balance-card__item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.balance-card__label {
  font-size: 11px;
  color: #909399;
}

.balance-card__value {
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}

.balance-card__value--num {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}

.balance-card--ratio {
  display: flex;
  flex-direction: column;
  justify-content: center;
  background: linear-gradient(135deg, #f5f0ff 0%, #eef2ff 100%);
  border-color: #d9d0f0;
}

.ratio-indicators {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ratio-indicator {
  text-align: center;
}

.ratio-indicator__label {
  font-size: 11px;
  color: #606266;
  margin-bottom: 4px;
}

.ratio-indicator__value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
}

.ratio-indicator__value--good { color: #67c23a; }
.ratio-indicator__value--warn { color: #e6a23c; }
.ratio-indicator__value--danger { color: #f56c6c; }
.ratio-indicator__value--na { color: #c0c4cc; }

.ratio-indicator__desc {
  font-size: 10px;
  color: #c0c4cc;
  margin-top: 2px;
}

@media (max-width: 900px) {
  .balance-cards {
    grid-template-columns: 1fr;
  }
  .balance-card__grid {
    grid-template-columns: 1fr 1fr;
  }
}

.mt-8 { margin-top: 8px; }
</style>
