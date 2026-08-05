<template>
  <div class="confirmation-sampling">
    <!-- 自动统计卡片（从发函数据联动） -->
    <div class="confirmation-sampling__stats">
      <el-tooltip content="已录入的函证对象总数" placement="top">
        <div class="confirmation-sampling__stat-item">
          <span class="confirmation-sampling__stat-label">总体笔数</span>
          <span class="confirmation-sampling__stat-value">{{ stats.totalCount }} 笔</span>
        </div>
      </el-tooltip>
      <el-tooltip content="所有函证对象的账面金额合计" placement="top">
        <div class="confirmation-sampling__stat-item">
          <span class="confirmation-sampling__stat-label">总体金额</span>
          <span class="confirmation-sampling__stat-value">{{ stats.totalAmount.toLocaleString() }} 元</span>
        </div>
      </el-tooltip>
      <el-tooltip content="实际纳入函证程序的样本数量（当前=总体）" placement="top">
        <div class="confirmation-sampling__stat-item">
          <span class="confirmation-sampling__stat-label">已选样本</span>
          <span class="confirmation-sampling__stat-value">{{ stats.sampleCount }} 笔</span>
        </div>
      </el-tooltip>
      <el-tooltip content="样本覆盖的金额合计" placement="top">
        <div class="confirmation-sampling__stat-item">
          <span class="confirmation-sampling__stat-label">样本金额</span>
          <span class="confirmation-sampling__stat-value">{{ stats.sampleAmount.toLocaleString() }} 元</span>
        </div>
      </el-tooltip>
      <el-tooltip content="覆盖率 = 样本金额 / 总体金额 × 100%（建议 ≥ 70%）" placement="top">
        <div class="confirmation-sampling__stat-item">
          <span class="confirmation-sampling__stat-label">覆盖率</span>
          <span class="confirmation-sampling__stat-value" :class="{ 'confirmation-sampling__stat-value--warn': stats.coverage < 70 }">
            {{ stats.coverage.toFixed(1) }}%
          </span>
        </div>
      </el-tooltip>
    </div>

    <!--
      源模板 6 项（G0-1!J19「二、样本选择」）——🔴 `isG0` 门控（裁决门 E）。
      其余六枢纽走下方既有 4 项分支，渲染结果逐字节不变。
      文字真源全部 import 自 `g0-confirmation/g0SummaryLowerZone`，本组件不抄第二份。
      spec: g0-confirmation-source-alignment R3.6 / R3.6.1 / R3.6.2 / R3.6.3
    -->
    <el-form v-if="isG0" label-width="132px" size="small" class="confirmation-sampling__form">
      <el-form-item
        v-for="def in G0_SAMPLE_DEFS"
        :key="def.field"
        :label="def.label"
      >
        <!-- 抽样方法：源模板 K25 本就是斜杠分隔的备选项 → 点选优先（可自定义） -->
        <el-select
          v-if="def.options"
          :model-value="valueOf(def.field)"
          :disabled="readonly"
          :placeholder="def.placeholder"
          filterable
          allow-create
          default-first-option
          style="width: 100%"
          @update:model-value="(v: string) => $emit('update', def.field, v)"
        >
          <el-option v-for="opt in def.options" :key="opt" :value="opt" :label="opt" />
        </el-select>
        <el-input
          v-else
          :model-value="valueOf(def.field)"
          :disabled="readonly"
          type="textarea"
          :autosize="{ minRows: 2 }"
          :placeholder="def.placeholder"
          @update:model-value="(v: string) => $emit('update', def.field, v)"
        />
        <!-- 源模板补充说明段（K24 / K27），只读提示不是录入项 -->
        <div v-if="hintOf(def.field)" class="confirmation-sampling__hint">
          {{ hintOf(def.field) }}
          <span class="confirmation-sampling__anchor">源模板 {{ hintAnchorOf(def.field) }}</span>
        </div>
      </el-form-item>

      <!-- 源外增强字段：源模板无此项，保留既有数据不丢失（R3.6 数据零丢失） -->
      <el-form-item label="抽样结论">
        <el-input
          :model-value="data.sampling_conclusion"
          :disabled="readonly"
          type="textarea"
          :autosize="{ minRows: 2 }"
          placeholder="抽样结果是否支持审计结论（源模板无此项，平台源外增强）"
          @update:model-value="(v) => $emit('update', 'sampling_conclusion', v)"
        />
      </el-form-item>
    </el-form>

    <!-- 表单区 -->
    <el-form v-else label-width="80px" size="small" class="confirmation-sampling__form">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="抽样方式">
            <el-select
              :model-value="data.sampling_method"
              :disabled="readonly"
              placeholder="请选择"
              filterable
              allow-create
              @update:model-value="(v) => $emit('update', 'sampling_method', v)"
            >
              <el-option value="随机选样" label="随机选样" />
              <el-option value="金额前N大" label="金额前N大" />
              <el-option value="全部函证" label="全部函证" />
              <el-option value="系统抽样" label="系统抽样" />
              <el-option value="分层抽样" label="分层抽样" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="样本量">
            <el-input
              :model-value="data.sampling_size"
              :disabled="readonly"
              placeholder="如：15 笔 / 金额前 10 大"
              @update:model-value="(v) => $emit('update', 'sampling_size', v)"
            />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="选样标准">
        <el-input
          :model-value="data.sampling_criteria"
          :disabled="readonly"
          type="textarea"
          :rows="2"
          :placeholder="criteriaSuggestion"
          @update:model-value="(v) => $emit('update', 'sampling_criteria', v)"
        />
      </el-form-item>
      <el-form-item label="抽样结论">
        <el-input
          :model-value="data.sampling_conclusion"
          :disabled="readonly"
          type="textarea"
          :rows="2"
          placeholder="抽样结果是否支持审计结论（如：函证覆盖率达到 XX%，满足审计要求）"
          @update:model-value="(v) => $emit('update', 'sampling_conclusion', v)"
        />
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
/**
 * ConfirmationSampling.vue — 函证「二、样本选择」区块
 *
 * 🔴 `isG0` 门控（裁决门 E，spec g0-confirmation-source-alignment R3.6.2）：
 * 本组件唯一消费方是 `GtConfirmationSummary.vue`，而后者服务**全部七枢纽** →
 * 无门控地改成 6 项会同时改掉 D0/E0/F0/H0/K0/L0 的样本选择区（与 R11.1 冲突）。
 * 故 G0 渲染源模板 6 项、其余六枢纽继续渲染既有 4 项。
 *
 * 🔴 **门控只在渲染层** —— `SamplingData` 的 6 个字段对全部枢纽都可读写，
 * `emit('update', field, value)` 不按枢纽分叉，故其余枢纽若已存 6 项数据不会因门控丢失（R3.6.3）。
 *
 * 🔴 旧 4 字段**每个都有落点**（数据零丢失）：
 *   `sampling_size` → `sample_size` · `sampling_criteria` → `specific_samples`
 *   `sampling_method` 同名沿用 · `sampling_conclusion` 作源外增强字段独立保留并渲染
 * 读回时新字段为空则回落旧字段值；写入一律写新字段（不双写，避免双真源）。
 *
 * 平台级统一为 6 项已登记为待收敛项（见 spec tasks.md §Notes「收敛 spec 登记」）。
 */
import { computed } from 'vue'
import type { SamplingData } from './confirmationTypes'
import type { ConfirmCycle } from './confirmationColumnSpec'
// 文字真源单一化：6 项的 label / placeholder / 只读提示全部来自 G0 下区声明模块，
// 本组件不抄第二份（改源模板文案只需改那一处）。
import {
  G0_SAMPLE_SELECTION_DEFS as G0_SAMPLE_DEFS,
  G0_SAMPLE_SELECTION_HINTS as G0_SAMPLE_HINTS,
} from '../g0-confirmation/g0SummaryLowerZone'

const props = defineProps<{
  data: SamplingData
  readonly: boolean
  dictData: Record<string, any[]>
  /**
   * 函证枢纽（`GtConfirmationSummary.vue` 由 wpCode 派生传入）。
   * 缺省按**非 G0** 处理 —— 绝不默认 G0，否则其余枢纽会被误改成 6 项。
   */
  cycle?: ConfirmCycle
  /** 从父组件传入的发函统计数据 */
  totalCount?: number
  totalAmount?: number
  sampleCount?: number
  sampleAmount?: number
}>()

defineEmits<{
  (e: 'update', field: string, value: any): void
}>()

/** 🔴 渲染层门控：只有 G0 渲染源模板 6 项 */
const isG0 = computed(() => props.cycle === 'G0')

/** 新字段为空时的旧字段落点（读回映射；写入只写新字段） */
const LEGACY_FALLBACK: Readonly<Record<string, keyof SamplingData>> = {
  sample_size: 'sampling_size',
  specific_samples: 'sampling_criteria',
  sampling_method: 'sampling_method',
}

function valueOf(field: string): string {
  const d = (props.data ?? {}) as Record<string, unknown>
  const own = d[field]
  if (own !== undefined && own !== null && own !== '') return String(own)
  const legacy = LEGACY_FALLBACK[field]
  if (legacy) {
    const v = d[legacy]
    if (v !== undefined && v !== null && v !== '') return String(v)
  }
  return ''
}

function hintOf(field: string): string {
  return G0_SAMPLE_HINTS.find((h) => h.field === field)?.text ?? ''
}

function hintAnchorOf(field: string): string {
  return G0_SAMPLE_HINTS.find((h) => h.field === field)?.anchor ?? ''
}

const stats = computed(() => ({
  totalCount: props.totalCount ?? 0,
  totalAmount: props.totalAmount ?? 0,
  sampleCount: props.sampleCount ?? props.totalCount ?? 0,
  sampleAmount: props.sampleAmount ?? props.totalAmount ?? 0,
  coverage: props.totalAmount && props.totalAmount > 0
    ? ((props.sampleAmount ?? props.totalAmount) / props.totalAmount) * 100
    : 0,
}))

const criteriaSuggestion = computed(() => {
  const method = props.data?.sampling_method
  if (method === '金额前N大') return '选取余额前 N 大的客户/供应商进行函证（覆盖科目余额 XX% 以上）'
  if (method === '全部函证') return '科目余额全部函证（期末有余额的所有客户/供应商）'
  if (method === '分层抽样') return '按金额分层：大额全选 + 中额随机 + 小额判断性选取'
  return '根据重要性水平和审计风险确定选样标准（如：余额超过重要性水平 50% 的全选，其余随机）'
})
</script>

<style scoped>
.confirmation-sampling__stats {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  margin-bottom: 12px;
}
.confirmation-sampling__stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 80px;
}
.confirmation-sampling__stat-label {
  font-size: 11px;
  color: #909399;
}
.confirmation-sampling__stat-value {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.confirmation-sampling__stat-value--warn {
  color: #f56c6c;
}
.confirmation-sampling__form {
  padding: 0 4px;
}
.confirmation-sampling__hint {
  border-left: 3px solid var(--el-color-warning-light-3);
  background: var(--el-color-warning-light-9);
  padding: 4px 8px;
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
}
.confirmation-sampling__anchor {
  margin-left: 6px;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}
</style>
