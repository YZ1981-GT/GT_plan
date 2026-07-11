<template>
  <div class="m2-detail-unlisted">
    <!-- ═══ 操作栏 ═══ -->
    <div class="detail-toolbar">
      <el-tag type="info" size="small">非上市公司版·37×24·出资</el-tag>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="primary"
        @click="detail.addUnlistedRow()"
      >
        <el-icon><Plus /></el-icon> 新增出资人
      </el-button>
      <span class="row-count">共 {{ detail.computedUnlistedRows.value.length }} 个出资人</span>
    </div>

    <!-- ═══ 区段Tab切换器 ═══ -->
    <el-segmented v-model="activeSegment" :options="segmentOptions" size="default" class="segment-switcher" />

    <!-- ═══ 明细表主体 ═══ -->
    <el-table
      :data="detail.computedUnlistedRows.value"
      border
      size="small"
      style="width: 100%"
      highlight-current-row
      max-height="520"
    >
      <el-table-column type="index" label="#" width="50" align="center" fixed />
      <el-table-column prop="investorName" label="出资人名称" min-width="160" fixed>
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.investorName"
            size="small"
            @change="(val: string) => detail.updateUnlistedRow($index, 'investorName', val)"
          />
          <span v-else>{{ row.investorName || '—' }}</span>
        </template>
      </el-table-column>

      <!-- ═══ 区段1: 出资人信息 ═══ -->
      <template v-if="activeSegment === 'info'">
        <el-table-column label="出资方式" min-width="120" align="center">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.investType"
              size="small"
              style="width:100%"
              placeholder="选择"
              @change="(val: string) => detail.updateUnlistedRow($index, 'investType', val)"
            >
              <el-option
                v-for="opt in INVEST_TYPE_OPTIONS"
                :key="opt.value"
                :value="opt.value"
                :label="opt.label"
              />
            </el-select>
            <span v-else>{{ investTypeLabel(row.investType) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="证件类型" min-width="110" align="center">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.idType"
              size="small"
              style="width:100%"
              placeholder="选择"
              @change="(val: string) => detail.updateUnlistedRow($index, 'idType', val)"
            >
              <el-option value="unified_credit" label="统一社会信用代码" />
              <el-option value="id_card" label="身份证" />
              <el-option value="passport" label="护照" />
              <el-option value="other" label="其他" />
            </el-select>
            <span v-else>{{ row.idType || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="证件号码" min-width="160">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.idNumber"
              size="small"
              @change="(val: string) => detail.updateUnlistedRow($index, 'idNumber', val)"
            />
            <span v-else>{{ row.idNumber || '—' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段2: 出资增减 ═══ -->
      <template v-if="activeSegment === 'changes'">
        <el-table-column label="期初出资" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.beginAmount"
              :controls="false"
              :precision="2"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => detail.updateUnlistedRow($index, 'beginAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.beginAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增资" min-width="130" align="right">
          <template #header>
            <el-tooltip content="贷方增资：货币/实物/知识产权/土地使用权等" placement="top">
              <span class="formula-col-header">本期增资</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.increaseAmount"
              :controls="false"
              :precision="2"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => detail.updateUnlistedRow($index, 'increaseAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.increaseAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减资" min-width="130" align="right">
          <template #header>
            <el-tooltip content="借方减资：减资/转让/退出等" placement="top">
              <span class="formula-col-header">本期减资</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.decreaseAmount"
              :controls="false"
              :precision="2"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => detail.updateUnlistedRow($index, 'decreaseAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.decreaseAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末出资" min-width="130" align="right">
          <template #header>
            <el-tooltip content="公式: 期初 + 本期增资 − 本期减资（权益类贷方）" placement="top">
              <span class="formula-col-header">期末出资</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value formula-value--primary">{{ fmtAmount(row.endAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="增资原因" min-width="130">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.increaseReason"
              size="small"
              style="width:100%"
              placeholder="选择"
              clearable
              @change="(val: string) => detail.updateUnlistedRow($index, 'increaseReason', val)"
            >
              <el-option value="新增出资" label="新增出资" />
              <el-option value="资本公积转增" label="资本公积转增" />
              <el-option value="盈余公积转增" label="盈余公积转增" />
              <el-option value="未分配利润转增" label="未分配利润转增" />
              <el-option value="债转股" label="债转股" />
              <el-option value="其他" label="其他" />
            </el-select>
            <span v-else>{{ row.increaseReason || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减资原因" min-width="130">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.decreaseReason"
              size="small"
              style="width:100%"
              placeholder="选择"
              clearable
              @change="(val: string) => detail.updateUnlistedRow($index, 'decreaseReason', val)"
            >
              <el-option value="减资" label="减资" />
              <el-option value="股权转让" label="股权转让" />
              <el-option value="退出" label="退出" />
              <el-option value="其他" label="其他" />
            </el-select>
            <span v-else>{{ row.decreaseReason || '—' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段3: 比例 ═══ -->
      <template v-if="activeSegment === 'ratio'">
        <el-table-column label="出资比例" min-width="110" align="right">
          <template #header>
            <el-tooltip content="公式: 个人期末出资 / 合计期末出资" placement="top">
              <span class="formula-col-header">出资比例</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtPercent(row.investRatio) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="认缴出资额" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.subscribedAmount"
              :controls="false"
              :precision="2"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => detail.updateUnlistedRow($index, 'subscribedAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.subscribedAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="出资到位率" min-width="110" align="right">
          <template #header>
            <el-tooltip content="公式: 期末出资（实缴）/ 认缴出资额" placement="top">
              <span class="formula-col-header">出资到位率</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="['formula-value', { 'warn-value': paidInRate(row) < 1 && paidInRate(row) > 0 }]">
              {{ fmtPercent(paidInRate(row)) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="出资日期" min-width="130" align="center">
          <template #default="{ row, $index }">
            <el-date-picker
              v-if="!isReadonly"
              :model-value="row.investDate"
              type="date"
              size="small"
              style="width:100%"
              value-format="YYYY-MM-DD"
              @update:model-value="(val: string) => detail.updateUnlistedRow($index, 'investDate', val || '')"
            />
            <span v-else>{{ row.investDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="160">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              size="small"
              placeholder="备注"
              @change="(val: string) => detail.updateUnlistedRow($index, 'remark', val)"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center" fixed="right">
        <template #default="{ $index }">
          <el-popconfirm title="确认删除该出资人明细？" @confirm="detail.removeUnlistedRow($index)">
            <template #reference>
              <el-button type="danger" text size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计汇总栏 ═══ -->
    <div class="summary-bar">
      <span>期初合计：<strong>{{ fmtAmount(detail.unlistedTotalBeginAmount.value) }}</strong></span>
      <span>期末合计：<strong class="formula-value--primary">{{ fmtAmount(detail.unlistedTotalEndAmount.value) }}</strong></span>
      <span>共 <strong>{{ detail.computedUnlistedRows.value.length }}</strong> 个出资人</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * M2TabDetailUnlisted — M2-2 非上市公司版明细表（37×24 出资）
 *
 * Requirements: 3.3, 3.4, 3.5, 3.6
 * - 24列拆3区段Tab：出资人信息 / 出资增减 / 比例
 * - 行跨区段同步（切换不丢数据）
 * - 动态行新增（ElMessageBox.prompt 输入出资人名称）
 * - 公式列：endAmount=begin+increase-decrease, investRatio=individual/total
 * - min-width 自适应列宽
 * - 出资到位率<100%黄色警告
 *
 * 科目：4001 实收资本（贷方/权益类！期末=期初+贷方-借方）
 */
import { computed } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import {
  useM2Detail,
  M2_UNLISTED_SEGMENTS,
  INVEST_TYPE_OPTIONS,
  type M2DetailSegment,
  type M2DetailUnlistedRow,
} from '../../composables/useM2Detail'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  detail: ReturnType<typeof useM2Detail>
}>()

// ─── Segment (synced with detail) ────────────────────────────────────────────

const activeSegment = computed({
  get: () => props.detail.activeSegment.value,
  set: (val: M2DetailSegment) => props.detail.switchSegment(val),
})

const segmentOptions = M2_UNLISTED_SEGMENTS.map(s => ({ label: s.label, value: s.key }))

// ─── Helpers ─────────────────────────────────────────────────────────────────

function investTypeLabel(val: string): string {
  return INVEST_TYPE_OPTIONS.find(o => o.value === val)?.label || val || '—'
}

/** 计算出资到位率：期末出资(实缴) / 认缴出资额 */
function paidInRate(row: M2DetailUnlistedRow): number {
  if (!row.subscribedAmount || row.subscribedAmount === 0) return 0
  return row.endAmount / row.subscribedAmount
}

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return (val * 100).toFixed(2) + '%'
}
</script>

<style scoped>
.m2-detail-unlisted { font-size: 13px; }
.detail-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.row-count { font-size: 12px; color: #909399; margin-left: auto; }
.segment-switcher { margin-bottom: 12px; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.formula-value--primary { color: #67c23a; font-weight: 600; }
.warn-value { color: #e6a23c; font-weight: 600; }
:deep(.el-table) { font-size: 13px; }
.summary-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; background: #f5f7fa; border-radius: 6px; font-size: 13px; color: #606266; flex-wrap: wrap; }
</style>
