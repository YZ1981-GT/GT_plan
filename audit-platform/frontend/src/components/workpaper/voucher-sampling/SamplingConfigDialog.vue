<script setup lang="ts">
/**
 * SamplingConfigDialog — 5种抽样方法配置弹窗
 *
 * Spec: .kiro/specs/voucher-sampling-engine/
 * Task: 7.1
 *
 * 功能：
 * - el-dialog（width=700px）
 * - 抽样方法选择：el-radio-group 5种方法
 * - 条件渲染参数区（v-if method）：
 *   - random：样本量 el-input-number（min=1, max=500）
 *   - stratified：动态行列表（下限/上限/样本量）+ 增删行按钮
 *   - specific_item：重要性水平金额 + 可选自定义条件
 *   - systematic：起始点 + 间隔K
 *   - mus：样本量 + 总体金额（只读 computed）
 * - 随机种子设置：el-input-number（可选）
 * - 通用过滤条件区（el-collapse 默认展开）
 * - 底部："执行抽样"按钮（校验后 emit execute）
 * - 校验失败红色提示
 *
 * Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.1, 2.2, 2.4
 */
import { computed, ref } from 'vue'
import type { SamplingConfig, SamplingMethod, StratumConfig } from '../composables/useSamplingAlgorithms'

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  visible: boolean
  config: SamplingConfig
  configErrors: Record<string, string>
  loading: boolean
}

const props = defineProps<Props>()

// ─── Emits ────────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'execute'): void
}>()

// ─── Dialog visibility ────────────────────────────────────────────────────────

const dialogVisible = computed({
  get: () => props.visible,
  set: (v: boolean) => emit('update:visible', v),
})

// ─── 5种抽样方法中文名 ───────────────────────────────────────────────────────

const methodOptions: { value: SamplingMethod; label: string }[] = [
  { value: 'random', label: '随机抽样' },
  { value: 'stratified', label: '金额分层抽样' },
  { value: 'specific_item', label: '特定项目选取' },
  { value: 'systematic', label: '系统抽样（等距）' },
  { value: 'mus', label: 'MUS货币单元抽样' },
]

// ─── 期间范围：12个月份 ──────────────────────────────────────────────────────

const allMonths = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

const isAllMonthsSelected = computed(() => {
  return props.config.periodRange.length === 12
})

function handleToggleAllMonths() {
  if (isAllMonthsSelected.value) {
    props.config.periodRange = []
  } else {
    props.config.periodRange = [...allMonths]
  }
}

// ─── 凭证类型选项 ────────────────────────────────────────────────────────────

const voucherTypeOptions = [
  { value: '记', label: '记' },
  { value: '收', label: '收' },
  { value: '付', label: '付' },
  { value: '转', label: '转' },
]

// ─── 方向选项 ─────────────────────────────────────────────────────────────────

const directionOptions: { value: 'debit' | 'credit' | 'all'; label: string }[] = [
  { value: 'all', label: '不限' },
  { value: 'debit', label: '借方' },
  { value: 'credit', label: '贷方' },
]

// ─── Collapse 默认展开 ───────────────────────────────────────────────────────

const activeCollapse = ref<string[]>(['filters'])

// ─── 分层抽样：动态行操作 ────────────────────────────────────────────────────

function handleAddStratum() {
  if (!props.config.strata) {
    props.config.strata = []
  }
  props.config.strata.push({
    lowerBound: '',
    upperBound: '',
    sampleSize: 10,
  })
}

function handleRemoveStratum(index: number) {
  if (props.config.strata) {
    props.config.strata.splice(index, 1)
  }
}

// ─── 执行抽样 ─────────────────────────────────────────────────────────────────

function handleExecute() {
  emit('execute')
}

// ─── 辅助：获取字段错误 ──────────────────────────────────────────────────────

function getError(key: string): string | undefined {
  return props.configErrors[key]
}

function hasError(key: string): boolean {
  return !!props.configErrors[key]
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="抽凭参数配置"
    width="700px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <div class="sampling-config-dialog">
      <!-- ═══ 1. 抽样方法选择 ═══ -->
      <div class="config-section">
        <div class="section-title">抽样方法</div>
        <el-radio-group v-model="config.samplingMethod" class="method-radio-group">
          <el-radio
            v-for="opt in methodOptions"
            :key="opt.value"
            :value="opt.value"
          >
            {{ opt.label }}
          </el-radio>
        </el-radio-group>
      </div>

      <!-- ═══ 2. 条件渲染参数区 ═══ -->
      <div class="config-section">
        <div class="section-title">方法参数</div>

        <!-- ── random：样本量 ── -->
        <div v-if="config.samplingMethod === 'random'" class="param-block">
          <el-form-item label="样本量" :error="getError('sampleSize')">
            <el-input-number
              v-model="config.sampleSize"
              :min="1"
              :max="500"
              placeholder="请输入样本量"
              controls-position="right"
              style="width: 200px"
            />
          </el-form-item>
        </div>

        <!-- ── stratified：动态行列表 ── -->
        <div v-if="config.samplingMethod === 'stratified'" class="param-block">
          <div v-if="hasError('strata')" class="field-error">{{ getError('strata') }}</div>
          <div
            v-for="(stratum, idx) in config.strata"
            :key="idx"
            class="stratum-row"
          >
            <span class="stratum-label">第{{ idx + 1 }}层</span>
            <el-input-number
              v-model="stratum.lowerBound"
              :controls="false"
              placeholder="下限金额"
              style="width: 130px"
              :class="{ 'is-error': hasError(`strata_${idx}_bounds`) }"
            />
            <span class="stratum-sep">~</span>
            <el-input-number
              v-model="stratum.upperBound"
              :controls="false"
              placeholder="上限金额"
              style="width: 130px"
              :class="{ 'is-error': hasError(`strata_${idx}_bounds`) }"
            />
            <el-input-number
              v-model="stratum.sampleSize"
              :min="1"
              :max="500"
              controls-position="right"
              placeholder="样本量"
              style="width: 120px"
              :class="{ 'is-error': hasError(`strata_${idx}_sampleSize`) }"
            />
            <el-button
              type="danger"
              :icon="'Delete'"
              circle
              size="small"
              @click="handleRemoveStratum(idx)"
            />
            <div v-if="hasError(`strata_${idx}_bounds`)" class="field-error">
              {{ getError(`strata_${idx}_bounds`) }}
            </div>
            <div v-if="hasError(`strata_${idx}_sampleSize`)" class="field-error">
              {{ getError(`strata_${idx}_sampleSize`) }}
            </div>
          </div>
          <el-button type="primary" size="small" plain @click="handleAddStratum">
            + 添加层级
          </el-button>
        </div>

        <!-- ── specific_item：重要性水平金额 ── -->
        <div v-if="config.samplingMethod === 'specific_item'" class="param-block">
          <el-form-item label="重要性水平金额" :error="getError('materialityThreshold')">
            <el-input-number
              v-model="config.materialityThreshold"
              :min="0"
              :controls="false"
              placeholder="请输入重要性水平金额"
              style="width: 240px"
            />
          </el-form-item>
        </div>

        <!-- ── systematic：起始点 + 间隔K ── -->
        <div v-if="config.samplingMethod === 'systematic'" class="param-block">
          <el-form-item label="起始点" :error="getError('startPoint')">
            <el-input-number
              v-model="config.startPoint"
              :min="1"
              controls-position="right"
              placeholder="起始序号"
              style="width: 200px"
            />
          </el-form-item>
          <el-form-item label="间隔K" :error="getError('interval')">
            <el-input-number
              v-model="config.interval"
              :min="2"
              controls-position="right"
              placeholder="等距间隔"
              style="width: 200px"
            />
          </el-form-item>
        </div>

        <!-- ── mus：样本量 + 总体金额（只读） ── -->
        <div v-if="config.samplingMethod === 'mus'" class="param-block">
          <el-form-item label="MUS样本量" :error="getError('musSampleSize')">
            <el-input-number
              v-model="config.musSampleSize"
              :min="1"
              :max="500"
              controls-position="right"
              placeholder="请输入样本量"
              style="width: 200px"
            />
          </el-form-item>
          <el-form-item label="总体金额">
            <el-input
              model-value="执行后自动计算"
              disabled
              style="width: 200px"
            />
          </el-form-item>
        </div>
      </div>

      <!-- ═══ 3. 随机种子设置 ═══ -->
      <div class="config-section">
        <div class="section-title">随机种子（可选）</div>
        <el-form-item>
          <el-input-number
            v-model="config.randomSeed"
            :min="0"
            :controls="false"
            placeholder="留空则系统自动生成"
            style="width: 240px"
          />
          <span class="hint-text">留空则系统自动生成，填入可复现相同结果</span>
        </el-form-item>
      </div>

      <!-- ═══ 4. 通用过滤条件区 ═══ -->
      <el-collapse v-model="activeCollapse" class="filter-collapse">
        <el-collapse-item title="通用过滤条件" name="filters">
          <div class="filter-grid">
            <!-- 科目范围 -->
            <div class="filter-item">
              <label class="filter-label">科目范围</label>
              <el-select
                v-model="config.accountCodes"
                multiple
                filterable
                allow-create
                default-first-option
                placeholder="输入科目编码（支持前缀匹配）"
                style="width: 100%"
                :class="{ 'is-error': hasError('accountCodes') }"
              >
                <el-option
                  v-for="code in config.accountCodes"
                  :key="code"
                  :label="code"
                  :value="code"
                />
              </el-select>
              <div v-if="hasError('accountCodes')" class="field-error">
                {{ getError('accountCodes') }}
              </div>
            </div>

            <!-- 期间范围 -->
            <div class="filter-item">
              <label class="filter-label">
                期间范围
                <el-checkbox
                  :model-value="isAllMonthsSelected"
                  :indeterminate="config.periodRange.length > 0 && config.periodRange.length < 12"
                  @change="handleToggleAllMonths"
                  style="margin-left: 8px"
                >
                  全选
                </el-checkbox>
              </label>
              <el-checkbox-group v-model="config.periodRange" class="month-checkbox-group">
                <el-checkbox
                  v-for="m in allMonths"
                  :key="m"
                  :label="m"
                  :value="m"
                >
                  {{ m }}月
                </el-checkbox>
              </el-checkbox-group>
            </div>

            <!-- 金额范围 -->
            <div class="filter-item">
              <label class="filter-label">金额范围</label>
              <div class="amount-range">
                <el-input-number
                  v-model="config.amountMin"
                  :controls="false"
                  placeholder="下限"
                  style="width: 140px"
                />
                <span class="range-sep">~</span>
                <el-input-number
                  v-model="config.amountMax"
                  :controls="false"
                  placeholder="上限"
                  style="width: 140px"
                />
              </div>
            </div>

            <!-- 方向 -->
            <div class="filter-item">
              <label class="filter-label">方向</label>
              <el-radio-group v-model="config.directionFilter" size="small">
                <el-radio
                  v-for="opt in directionOptions"
                  :key="opt.value"
                  :value="opt.value"
                >
                  {{ opt.label }}
                </el-radio>
              </el-radio-group>
            </div>

            <!-- 凭证类型 -->
            <div class="filter-item">
              <label class="filter-label">凭证类型</label>
              <el-checkbox-group v-model="config.voucherTypeFilter" size="small">
                <el-checkbox
                  v-for="opt in voucherTypeOptions"
                  :key="opt.value"
                  :label="opt.value"
                  :value="opt.value"
                >
                  {{ opt.label }}
                </el-checkbox>
              </el-checkbox-group>
              <span class="hint-text">不选则不限制</span>
            </div>

            <!-- 摘要关键词 -->
            <div class="filter-item">
              <label class="filter-label">摘要关键词</label>
              <el-input
                v-model="config.summaryKeyword"
                placeholder="输入摘要关键词（模糊匹配）"
                clearable
                style="width: 100%"
              />
            </div>

            <!-- 排除已抽过 -->
            <div class="filter-item">
              <label class="filter-label">排除已抽过的凭证</label>
              <el-switch
                v-model="config.excludeExtracted"
                active-text="开启"
                inactive-text="关闭"
              />
              <span class="hint-text">开启后自动排除历史已抽凭证号</span>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- ═══ 底部按钮 ═══ -->
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="loading"
          @click="handleExecute"
        >
          执行抽样
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.sampling-config-dialog {
  max-height: 60vh;
  overflow-y: auto;
  padding: 0 4px;
}

/* ── 配置区块 ── */
.config-section {
  margin-bottom: 20px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

/* ── 方法 radio 组 ── */
.method-radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}

/* ── 参数区块 ── */
.param-block {
  padding: 12px 0;
}

.param-block .el-form-item {
  margin-bottom: 12px;
}

/* ── 分层抽样行 ── */
.stratum-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.stratum-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  min-width: 48px;
}

.stratum-sep {
  color: var(--el-text-color-secondary);
}

/* ── 过滤条件区 ── */
.filter-collapse {
  margin-top: 8px;
}

.filter-grid {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filter-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-regular);
  display: flex;
  align-items: center;
}

/* ── 月份 checkbox 组 ── */
.month-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
}

/* ── 金额范围 ── */
.amount-range {
  display: flex;
  align-items: center;
  gap: 8px;
}

.range-sep {
  color: var(--el-text-color-secondary);
}

/* ── 提示文本 ── */
.hint-text {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  margin-left: 8px;
}

/* ── 字段错误提示 ── */
.field-error {
  font-size: 12px;
  color: var(--el-color-danger);
  margin-top: 4px;
  line-height: 1.4;
}

/* ── el-input-number 错误边框 ── */
.is-error :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px var(--el-color-danger) inset;
}

/* ── 底部按钮 ── */
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
