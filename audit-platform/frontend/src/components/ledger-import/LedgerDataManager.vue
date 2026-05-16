<template>
  <el-dialog
    v-model="visible"
    title="账表数据管理"
    width="1100px"
    :close-on-click-modal="false"
    :before-close="onClose"
  >
    <div v-loading="loading">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      >
        <template #title>
          查看已导入数据、按年度/月份删除、或增量追加 12 月序时账等
        </template>
      </el-alert>

      <el-tabs v-model="activeTab">
        <!-- Tab 1: 数据概览 -->
        <el-tab-pane label="数据概览" name="summary">
          <div v-if="summary">
            <el-table
              :data="summaryRows"
              size="small"
              border
              style="width: 100%"
            >
              <el-table-column prop="table" label="表名" width="140" />
              <el-table-column prop="year" label="年度" width="80" />
              <el-table-column prop="total" label="总行数" width="100" align="right" />
              <el-table-column label="月份分布">
                <template #default="{ row }">
                  <div v-if="row.periods">
                    <el-tag
                      v-for="(cnt, period) in row.periods"
                      :key="period"
                      size="small"
                      style="margin: 2px"
                    >
                      {{ period }}月: {{ cnt }}
                    </el-tag>
                  </div>
                  <span v-else style="color: var(--gt-color-text-tertiary)">—</span>
                </template>
              </el-table-column>
              <el-table-column label="日期范围" width="200">
                <template #default="{ row }">
                  <span v-if="row.dateRange" style="font-size: var(--gt-font-size-xs)">
                    {{ row.dateRange }}
                  </span>
                </template>
              </el-table-column>
            </el-table>
            <div v-if="summaryRows.length === 0" style="text-align: center; padding: 40px; color: var(--gt-color-text-tertiary)">
              暂无已导入数据
            </div>
          </div>
        </el-tab-pane>

        <!-- Tab 2: 删除数据 -->
        <el-tab-pane label="删除数据" name="delete">
          <el-form label-width="100px" size="default">
            <el-form-item label="年度" required>
              <el-select v-model="deleteForm.year" placeholder="选择年度" style="width: 200px">
                <el-option
                  v-for="y in availableYears"
                  :key="y"
                  :label="`${y} 年`"
                  :value="y"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="目标表">
              <el-checkbox-group v-model="deleteForm.tables">
                <el-checkbox value="tb_balance">科目余额表</el-checkbox>
                <el-checkbox value="tb_aux_balance">辅助余额表</el-checkbox>
                <el-checkbox value="tb_ledger">序时账</el-checkbox>
                <el-checkbox value="tb_aux_ledger">辅助序时账</el-checkbox>
              </el-checkbox-group>
              <div style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: 4px">
                不选 = 删除全部四张表
              </div>
            </el-form-item>
            <el-form-item label="月份（可选）">
              <el-checkbox-group v-model="deleteForm.periods">
                <el-checkbox v-for="m in 12" :key="m" :value="m">{{ m }}月</el-checkbox>
              </el-checkbox-group>
              <div style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: 4px">
                仅对序时账/辅助序时账生效；不选 = 删整个年度
              </div>
            </el-form-item>
            <el-alert
              type="warning"
              :closable="false"
              show-icon
              style="margin-bottom: 16px"
              title="删除操作不可恢复，请谨慎确认"
            />
            <el-button
              type="danger"
              :disabled="!deleteForm.year"
              @click="onDelete"
            >
              确认删除
            </el-button>
          </el-form>
        </el-tab-pane>

        <!-- Tab 3: 增量追加（12月） -->
        <el-tab-pane label="增量追加" name="incremental">
          <el-form label-width="100px" size="default">
            <el-form-item label="年度" required>
              <el-select v-model="incrementalForm.year" placeholder="选择年度" style="width: 200px">
                <el-option
                  v-for="y in availableYears"
                  :key="y"
                  :label="`${y} 年`"
                  :value="y"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="已有月份">
              <div v-if="incrementalForm.year && summary">
                <el-tag
                  v-for="p in getExistingPeriods(incrementalForm.year)"
                  :key="p"
                  size="small"
                  type="success"
                  style="margin: 2px"
                >
                  {{ p }}月
                </el-tag>
                <span v-if="getExistingPeriods(incrementalForm.year).length === 0" style="color: var(--gt-color-text-tertiary)">
                  暂无序时账数据
                </span>
              </div>
            </el-form-item>

            <!-- 预检结果展示 -->
            <el-form-item v-if="incrementalDiff" label="检测结果">
              <div style="font-size: var(--gt-font-size-sm); line-height: 1.8">
                <div>
                  <span style="color: var(--gt-color-success); font-weight: 600">新增月份：</span>
                  <el-tag
                    v-for="p in incrementalDiff.diff.new"
                    :key="`new-${p}`"
                    size="small"
                    type="success"
                    style="margin: 2px"
                  >
                    {{ p }}月
                  </el-tag>
                  <span v-if="incrementalDiff.diff.new.length === 0" style="color: var(--gt-color-text-tertiary)">无</span>
                </div>
                <div>
                  <span style="color: var(--gt-color-wheat); font-weight: 600">重叠月份：</span>
                  <el-tag
                    v-for="p in incrementalDiff.diff.overlap"
                    :key="`ov-${p}`"
                    size="small"
                    type="warning"
                    style="margin: 2px"
                  >
                    {{ p }}月
                  </el-tag>
                  <span v-if="incrementalDiff.diff.overlap.length === 0" style="color: var(--gt-color-text-tertiary)">无</span>
                </div>
                <div v-if="incrementalDiff.diff.overlap.length > 0" style="margin-top: 8px">
                  <el-radio-group v-model="overlapStrategy">
                    <el-radio value="skip">跳过重叠月份（只追加新月份）</el-radio>
                    <el-radio value="overwrite">覆盖重叠月份（删除旧数据）</el-radio>
                  </el-radio-group>
                </div>
              </div>
            </el-form-item>

            <el-alert
              type="info"
              :closable="false"
              show-icon
              style="margin-bottom: 16px"
            >
              <template #title>操作步骤</template>
              <template #default>
                <ol style="margin: 4px 0 0 16px; padding: 0; font-size: var(--gt-font-size-sm); line-height: 1.8">
                  <li>选择年度（上方）</li>
                  <li>点击"检测"输入文件将要导入的月份</li>
                  <li>确认重叠策略（跳过/覆盖）</li>
                  <li>执行清理旧数据后上传文件继续导入</li>
                </ol>
              </template>
            </el-alert>
            <div style="display: flex; gap: 8px; align-items: center; padding: 12px; background: var(--gt-color-primary-bg); border-radius: 8px; border: 1px solid #e8e4f0">
              <el-input
                v-model="filePeriodsInput"
                placeholder="文件包含的月份，逗号分隔如: 11,12"
                style="width: 280px"
                size="small"
              />
              <el-button
                size="small"
                :disabled="!incrementalForm.year || !filePeriodsInput"
                @click="onDetectIncremental"
              >
                检测差异
              </el-button>
              <el-button
                v-if="incrementalDiff && (incrementalDiff.diff.overlap.length > 0 || incrementalDiff.diff.new.length > 0)"
                size="small"
                type="warning"
                :disabled="!incrementalForm.year"
                @click="onApplyIncremental"
              >
                执行清理
              </el-button>
              <el-button
                size="small"
                type="primary"
                :disabled="!incrementalForm.year"
                @click="onOpenIncrementalUpload"
              >
                上传文件
              </el-button>
            </div>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { ledger } from '@/services/apiPaths'
import { useProjectStore } from '@/stores/project'

const props = defineProps<{
  modelValue: boolean
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'data-changed'): void
  (e: 'request-incremental-upload', year: number): void
}>()

const visible = ref(props.modelValue)
watch(() => props.modelValue, (v) => (visible.value = v))
watch(visible, (v) => emit('update:modelValue', v))

const loading = ref(false)
const activeTab = ref('summary')
const summary = ref<any>(null)

const deleteForm = ref<{ year: number | null; tables: string[]; periods: number[] }>({
  year: null,
  tables: [],
  periods: [],
})

const incrementalForm = ref<{ year: number | null }>({ year: null })
const filePeriodsInput = ref('')
const incrementalDiff = ref<any>(null)
const overlapStrategy = ref<'skip' | 'overwrite'>('skip')

const tableLabels: Record<string, string> = {
  tb_balance: '科目余额表',
  tb_aux_balance: '辅助余额表',
  tb_ledger: '序时账',
  tb_aux_ledger: '辅助序时账',
}

const availableYears = computed<number[]>(() => {
  const currentYear = new Date().getFullYear()
  if (!summary.value?.tables) {
    // summary 未加载时提供近 3 年选项
    return [currentYear, currentYear - 1, currentYear - 2]
  }
  const years = new Set<number>()
  for (const t of Object.values(summary.value.tables) as any[]) {
    if (t.years) Object.keys(t.years).forEach((y) => years.add(Number(y)))
  }
  // 确保当前年度和前一年始终可选（即使没有数据也能选择导入）
  years.add(currentYear)
  years.add(currentYear - 1)
  const arr = Array.from(years).sort((a, b) => b - a)
  return arr
})

const summaryRows = computed(() => {
  const rows: any[] = []
  if (!summary.value?.tables) return rows
  for (const [table, data] of Object.entries(summary.value.tables) as [string, any][]) {
    if (!data.years || Object.keys(data.years).length === 0) continue
    for (const [year, yearData] of Object.entries(data.years) as [string, any][]) {
      rows.push({
        table: tableLabels[table] || table,
        year,
        total: yearData.total,
        periods: yearData.periods,
        dateRange: yearData.voucher_date_min
          ? `${yearData.voucher_date_min} ~ ${yearData.voucher_date_max}`
          : '',
      })
    }
  }
  return rows
})

function getExistingPeriods(year: number): number[] {
  if (!summary.value?.tables?.tb_ledger?.years?.[year]?.periods) return []
  return Object.keys(summary.value.tables.tb_ledger.years[year].periods)
    .map(Number)
    .sort((a, b) => a - b)
}

async function refreshSummary() {
  loading.value = true
  try {
    summary.value = await api.get(ledger.data.summary(props.projectId))
    const years = Object.keys(summary.value?.tables?.tb_balance?.years || {})
      .map(Number)
      .sort((a, b) => b - a)
  } catch (exc: any) {
    ElMessage.error('查询失败: ' + (exc.message || exc))
  } finally {
    loading.value = false
  }
}

async function onDelete() {
  if (!deleteForm.value.year) return

  const tablesLabel = deleteForm.value.tables.length > 0
    ? deleteForm.value.tables.map((t) => tableLabels[t] || t).join('、')
    : '全部四张表'
  const periodsLabel = deleteForm.value.periods.length > 0
    ? `${deleteForm.value.periods.sort((a, b) => a - b).join(',')} 月`
    : '整年'

  // R10 Spec C / F5：清理账套必须输入项目名称二次确认
  const projectStore = useProjectStore()
  const projectName = projectStore.clientName || ''
  if (projectName) {
    try {
      const { value } = await ElMessageBox.prompt(
        `⚠ 即将删除 ${deleteForm.value.year} 年 ${periodsLabel} 的 ${tablesLabel} 数据。\n\n此操作不可恢复，将永久删除当前账套相关数据。\n\n请输入项目完整名称【${projectName}】确认：`,
        '清理账套数据 — 危险操作',
        {
          confirmButtonText: '确认清理',
          cancelButtonText: '取消',
          type: 'warning',
          confirmButtonClass: 'el-button--danger',
          inputPlaceholder: '请输入项目完整名称',
          inputValidator: (v: string) => v === projectName || '名称不匹配，请输入完整项目名称',
        },
      )
      if (value !== projectName) return
    } catch {
      return
    }
  } else {
    // fallback：无项目名时退化为简单二次确认
    try {
      await ElMessageBox.confirm(
        `即将删除 ${deleteForm.value.year} 年 ${periodsLabel} 的 ${tablesLabel} 数据，此操作不可恢复，是否继续？`,
        '清理账套数据',
        {
          confirmButtonText: '确认清理',
          cancelButtonText: '取消',
          type: 'warning',
          confirmButtonClass: 'el-button--danger',
        },
      )
    } catch {
      return
    }
  }

  loading.value = true
  try {
    const result: any = await api.delete(ledger.data.delete(props.projectId), {
      data: {
        year: deleteForm.value.year,
        tables: deleteForm.value.tables.length > 0 ? deleteForm.value.tables : null,
        periods: deleteForm.value.periods.length > 0 ? deleteForm.value.periods : null,
        confirmed: true,
      },
    })
    ElMessage.success(`已删除 ${result.total_deleted} 行数据`)
    emit('data-changed')
    await refreshSummary()
    // Reset form
    deleteForm.value = { year: null, tables: [], periods: [] }
  } catch (exc: any) {
    ElMessage.error('删除失败: ' + (exc.message || exc))
  } finally {
    loading.value = false
  }
}

function onOpenIncrementalUpload() {
  if (!incrementalForm.value.year) return
  emit('request-incremental-upload', incrementalForm.value.year)
}

function _parseFilePeriods(): number[] {
  return filePeriodsInput.value
    .split(/[,，]/)
    .map((s) => Number(s.trim()))
    .filter((n) => n >= 1 && n <= 12)
}

async function onDetectIncremental() {
  if (!incrementalForm.value.year) return
  const file_periods = _parseFilePeriods()
  if (file_periods.length === 0) {
    ElMessage.warning('请输入有效的月份，如 11,12')
    return
  }
  loading.value = true
  try {
    incrementalDiff.value = await api.post(
      ledger.data.incrementalDetect(props.projectId),
      { year: incrementalForm.value.year, file_periods },
    )
    // 默认策略：有 overlap 则提示用户选择，否则 skip
    if (incrementalDiff.value.diff.overlap.length === 0) {
      overlapStrategy.value = 'skip'
    }
  } catch (exc: any) {
    ElMessage.error('检测失败: ' + (exc.message || exc))
  } finally {
    loading.value = false
  }
}

async function onApplyIncremental() {
  if (!incrementalForm.value.year || !incrementalDiff.value) return
  const file_periods = _parseFilePeriods()
  const strategy = overlapStrategy.value

  if (strategy === 'overwrite') {
    const ovMonths = incrementalDiff.value.diff.overlap.join(', ')
    try {
      await ElMessageBox.confirm(
        `即将覆盖 ${incrementalForm.value.year} 年 ${ovMonths} 月数据，此操作不可恢复，是否继续？`,
        '覆盖确认',
        { confirmButtonText: '确认覆盖', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return
    }
  }

  loading.value = true
  try {
    const result: any = await api.post(
      ledger.data.incrementalApply(props.projectId),
      {
        year: incrementalForm.value.year,
        file_periods,
        overlap_strategy: strategy,
        confirmed: strategy === 'overwrite',
      },
    )
    if (result.executed) {
      const rows = result.action?.rows_deleted
      const total = rows
        ? Object.values(rows).reduce((a: number, b: any) => a + (Number(b) || 0), 0)
        : 0
      ElMessage.success(`已清理 ${total} 行旧数据，请上传文件继续`)
    } else {
      ElMessage.info('跳过策略下无需清理，可直接上传新月份文件')
    }
    emit('data-changed')
    await refreshSummary()
    // 清空检测结果，鼓励用户上传新文件
    incrementalDiff.value = null
  } catch (exc: any) {
    ElMessage.error('清理失败: ' + (exc.message || exc))
  } finally {
    loading.value = false
  }
}

function onClose() {
  visible.value = false
}

// Initial load
watch(visible, (v) => {
  if (v) refreshSummary()
})
</script>
