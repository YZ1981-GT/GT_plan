<template>
  <el-dialog
    v-model="visible"
    title="账表数据管理"
    width="720px"
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
                  <span v-else style="color: #999">—</span>
                </template>
              </el-table-column>
              <el-table-column label="日期范围" width="200">
                <template #default="{ row }">
                  <span v-if="row.dateRange" style="font-size: 12px">
                    {{ row.dateRange }}
                  </span>
                </template>
              </el-table-column>
            </el-table>
            <div v-if="summaryRows.length === 0" style="text-align: center; padding: 40px; color: #999">
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
              <div style="font-size: 12px; color: #999; margin-top: 4px">
                不选 = 删除全部四张表
              </div>
            </el-form-item>
            <el-form-item label="月份（可选）">
              <el-checkbox-group v-model="deleteForm.periods">
                <el-checkbox v-for="m in 12" :key="m" :value="m">{{ m }}月</el-checkbox>
              </el-checkbox-group>
              <div style="font-size: 12px; color: #999; margin-top: 4px">
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
                <span v-if="getExistingPeriods(incrementalForm.year).length === 0" style="color: #999">
                  暂无序时账数据
                </span>
              </div>
            </el-form-item>
            <el-alert
              type="success"
              :closable="false"
              show-icon
              title="操作步骤"
              style="margin-bottom: 16px"
            >
              <template #default>
                <ol style="margin: 8px 0 0 16px; padding: 0">
                  <li>选择年度（上方）</li>
                  <li>点击下方"上传文件"选择 12 月序时账</li>
                  <li>系统自动检测新增月份 vs 重叠月份</li>
                  <li>确认后只追加新月份，重叠月份需二次确认</li>
                </ol>
              </template>
            </el-alert>
            <el-button
              type="primary"
              :disabled="!incrementalForm.year"
              @click="onOpenIncrementalUpload"
            >
              上传文件 (增量追加)
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </div>

    <template #footer>
      <el-button @click="onClose">关闭</el-button>
      <el-button @click="refreshSummary">刷新数据</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { ledger } from '@/services/apiPaths'

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

const tableLabels: Record<string, string> = {
  tb_balance: '科目余额表',
  tb_aux_balance: '辅助余额表',
  tb_ledger: '序时账',
  tb_aux_ledger: '辅助序时账',
}

const availableYears = computed<number[]>(() => {
  if (!summary.value?.tables) return [new Date().getFullYear()]
  const years = new Set<number>()
  for (const t of Object.values(summary.value.tables) as any[]) {
    if (t.years) Object.keys(t.years).forEach((y) => years.add(Number(y)))
  }
  const arr = Array.from(years).sort((a, b) => b - a)
  return arr.length ? arr : [new Date().getFullYear()]
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
    summary.value = await api.get(ledger.import.data.summary(props.projectId))
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

  try {
    await ElMessageBox.confirm(
      `即将删除 ${deleteForm.value.year} 年 ${periodsLabel} 的 ${tablesLabel} 数据，此操作不可恢复，是否继续？`,
      '删除确认',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  loading.value = true
  try {
    const result: any = await api.delete(ledger.import.data.delete(props.projectId), {
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

function onClose() {
  visible.value = false
}

// Initial load
watch(visible, (v) => {
  if (v) refreshSummary()
})
</script>
