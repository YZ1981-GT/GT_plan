<template>
  <div class="m2-detail-listed">
    <!-- ═══ 操作栏 ═══ -->
    <div class="detail-toolbar">
      <el-tag type="info" size="small">上市公司版·38×36·股份</el-tag>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="primary"
        @click="detail.addListedRow()"
      >
        <el-icon><Plus /></el-icon> 新增股东
      </el-button>
      <span class="row-count">共 {{ detail.computedListedRows.value.length }} 个股东</span>
    </div>

    <!-- ═══ 区段Tab切换器 ═══ -->
    <el-segmented v-model="activeSegment" :options="segmentOptions" size="default" class="segment-switcher" />

    <!-- ═══ 明细表主体 ═══ -->
    <el-table
      :data="detail.computedListedRows.value"
      border
      size="small"
      style="width: 100%"
      highlight-current-row
      max-height="520"
    >
      <el-table-column type="index" label="#" width="50" align="center" fixed />
      <el-table-column prop="shareholderName" label="股东名称" min-width="160" fixed>
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.shareholderName"
            size="small"
            @change="(val: string) => detail.updateListedRow($index, 'shareholderName', val)"
          />
          <span v-else>{{ row.shareholderName || '—' }}</span>
        </template>
      </el-table-column>

      <!-- ═══ 区段1: 股东信息 ═══ -->
      <template v-if="activeSegment === 'info'">
        <el-table-column label="股份性质" min-width="120" align="center">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.shareType"
              size="small"
              style="width:100%"
              placeholder="选择"
              @change="(val: string) => detail.updateListedRow($index, 'shareType', val)"
            >
              <el-option
                v-for="opt in SHARE_TYPE_OPTIONS"
                :key="opt.value"
                :value="opt.value"
                :label="opt.label"
              />
            </el-select>
            <span v-else>{{ shareTypeLabel(row.shareType) }}</span>
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
              @change="(val: string) => detail.updateListedRow($index, 'idType', val)"
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
              @change="(val: string) => detail.updateListedRow($index, 'idNumber', val)"
            />
            <span v-else>{{ row.idNumber || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="国籍/地区" min-width="110">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.nationality"
              size="small"
              placeholder="如：中国"
              @change="(val: string) => detail.updateListedRow($index, 'nationality', val)"
            />
            <span v-else>{{ row.nationality || '—' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段2: 股数增减变动 ═══ -->
      <template v-if="activeSegment === 'changes'">
        <el-table-column label="期初股数" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.beginShares"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => detail.updateListedRow($index, 'beginShares', val ?? 0)"
            />
            <span v-else>{{ fmtNumber(row.beginShares) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" min-width="130" align="right">
          <template #header>
            <el-tooltip content="贷方增资：增发/转增/配股/权证行权等" placement="top">
              <span class="formula-col-header">本期增加</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.increaseShares"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => detail.updateListedRow($index, 'increaseShares', val ?? 0)"
            />
            <span v-else>{{ fmtNumber(row.increaseShares) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" min-width="130" align="right">
          <template #header>
            <el-tooltip content="借方减资：回购/注销/转让等" placement="top">
              <span class="formula-col-header">本期减少</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.decreaseShares"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => detail.updateListedRow($index, 'decreaseShares', val ?? 0)"
            />
            <span v-else>{{ fmtNumber(row.decreaseShares) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末股数" min-width="130" align="right">
          <template #header>
            <el-tooltip content="公式: 期初 + 本期增加 − 本期减少（权益类贷方）" placement="top">
              <span class="formula-col-header">期末股数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value formula-value--primary">{{ fmtNumber(row.endShares) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="增加原因" min-width="130">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.increaseReason"
              size="small"
              style="width:100%"
              placeholder="选择"
              clearable
              @change="(val: string) => detail.updateListedRow($index, 'increaseReason', val)"
            >
              <el-option value="增发" label="增发" />
              <el-option value="转增" label="转增" />
              <el-option value="配股" label="配股" />
              <el-option value="权证行权" label="权证行权" />
              <el-option value="债转股" label="债转股" />
              <el-option value="其他" label="其他" />
            </el-select>
            <span v-else>{{ row.increaseReason || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减少原因" min-width="130">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.decreaseReason"
              size="small"
              style="width:100%"
              placeholder="选择"
              clearable
              @change="(val: string) => detail.updateListedRow($index, 'decreaseReason', val)"
            >
              <el-option value="回购" label="回购" />
              <el-option value="注销" label="注销" />
              <el-option value="转让" label="转让" />
              <el-option value="减资" label="减资" />
              <el-option value="其他" label="其他" />
            </el-select>
            <span v-else>{{ row.decreaseReason || '—' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段3: 比例与金额 ═══ -->
      <template v-if="activeSegment === 'ratio'">
        <el-table-column label="持股比例" min-width="110" align="right">
          <template #header>
            <el-tooltip content="公式: 个人期末股数 / 合计期末股数" placement="top">
              <span class="formula-col-header">持股比例</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtPercent(row.shareRatio) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="面值" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.parValue"
              :controls="false"
              :precision="2"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => detail.updateListedRow($index, 'parValue', val ?? 1)"
            />
            <span v-else>{{ fmtAmount(row.parValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初金额" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.beginAmount"
              :controls="false"
              :precision="2"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => detail.updateListedRow($index, 'beginAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.beginAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末金额" min-width="130" align="right">
          <template #header>
            <el-tooltip content="公式: 期末股数 × 面值" placement="top">
              <span class="formula-col-header">期末金额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value formula-value--primary">{{ fmtAmount(row.endAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="160">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              size="small"
              placeholder="备注"
              @change="(val: string) => detail.updateListedRow($index, 'remark', val)"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center" fixed="right">
        <template #default="{ $index }">
          <el-popconfirm title="确认删除该股东明细？" @confirm="detail.removeListedRow($index)">
            <template #reference>
              <el-button type="danger" text size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计汇总栏 ═══ -->
    <div class="summary-bar">
      <span>期初合计股数：<strong>{{ fmtNumber(detail.listedTotalBeginShares.value) }}</strong></span>
      <span>期末合计股数：<strong class="formula-value--primary">{{ fmtNumber(detail.listedTotalEndShares.value) }}</strong></span>
      <span>共 <strong>{{ detail.computedListedRows.value.length }}</strong> 个股东</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * M2TabDetailListed — M2-2 上市公司版明细表（38×36 股份）
 *
 * Requirements: 3.2, 3.4, 3.5, 3.6
 * - 36列拆3区段Tab：股东信息 / 股数增减变动 / 比例与金额
 * - 行跨区段同步（切换不丢数据）
 * - 动态行新增（ElMessageBox.prompt 输入股东名称）
 * - 公式列：endShares=begin+increase-decrease, shareRatio=individual/total
 * - min-width 自适应列宽
 *
 * 科目：4001 实收资本/股本（贷方/权益类！期末=期初+贷方-借方）
 */
import { computed } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import {
  useM2Detail,
  M2_LISTED_SEGMENTS,
  SHARE_TYPE_OPTIONS,
  type M2DetailSegment,
} from '../../../composables/useM2Detail'

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

const segmentOptions = M2_LISTED_SEGMENTS.map(s => ({ label: s.label, value: s.key }))

// ─── Label helpers ───────────────────────────────────────────────────────────

function shareTypeLabel(val: string): string {
  return SHARE_TYPE_OPTIONS.find(o => o.value === val)?.label || val || '—'
}

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtNumber(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

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
.m2-detail-listed { font-size: 13px; }
.detail-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.row-count { font-size: 12px; color: #909399; margin-left: auto; }
.segment-switcher { margin-bottom: 12px; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.formula-value--primary { color: #67c23a; font-weight: 600; }
:deep(.el-table) { font-size: 13px; }
.summary-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; background: #f5f7fa; border-radius: 6px; font-size: 13px; color: #606266; flex-wrap: wrap; }
</style>
