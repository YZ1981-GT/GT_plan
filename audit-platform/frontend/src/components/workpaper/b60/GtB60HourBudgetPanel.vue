<script setup lang="ts">
/**
 * B60-1 工时预算 HTML 面（G4-1 simple checklist canary）。
 * store item: B60-1-hour-budget-rows；行身份 rowUuid。
 */
import { ref, watch, onMounted } from 'vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const STORE_ITEM_ID = 'B60-1-hour-budget-rows'
const ROW_ID_KEY = 'rowUuid'

type HourRow = Record<string, unknown> & { rowUuid?: string }

const rows = ref<HourRow[]>([])
const loading = ref(false)
const dirty = ref(false)
let saveTimer: ReturnType<typeof setTimeout> | null = null

async function load(): Promise<void> {
  if (!props.wpId) {
    rows.value = []
    return
  }
  loading.value = true
  try {
    // 权威 checklist 路径是 /api/workpapers/{wpId}/…（项目前缀路径 404）
    const { data } = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const list = (data?.data ?? data ?? []) as Array<{ item_id?: string; remark?: string }>
    const hit = list.find((r) => r.item_id === STORE_ITEM_ID)
    if (!hit?.remark) {
      rows.value = []
      return
    }
    try {
      const parsed = JSON.parse(hit.remark)
      rows.value = Array.isArray(parsed) ? (parsed as HourRow[]) : []
    } catch {
      rows.value = []
    }
  } finally {
    loading.value = false
    dirty.value = false
  }
}

async function flushPendingSave(): Promise<void> {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  if (!props.wpId || props.readonly || !dirty.value) return
  await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
    responses: [
      {
        item_id: STORE_ITEM_ID,
        remark: JSON.stringify(rows.value),
      },
    ],
  })
  dirty.value = false
}

function scheduleSave(): void {
  dirty.value = true
  if (props.readonly) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    void flushPendingSave()
  }, 600)
}

function onCellInput(row: HourRow, key: string, ev: Event): void {
  const el = ev.target as HTMLInputElement
  row[key] = el.value
  scheduleSave()
}

watch(
  () => props.wpId,
  () => {
    void load()
  },
)

onMounted(() => {
  void load()
})

defineExpose({ flushPendingSave, reload: load })
</script>

<template>
  <div class="g7-soe b60-hour-budget" v-loading="loading" data-testid="b60-hour-budget">
    <p v-if="!wpId" class="b60-hour-budget__empty">B60-1 底稿尚未生成</p>
    <table v-else class="b60-hour-budget__table">
      <thead>
        <tr>
          <th>级别</th>
          <th>姓名</th>
          <th>预算执行</th>
          <th>预算复核</th>
          <th>小时费用</th>
          <th>实际执行</th>
          <th>实际复核</th>
          <th>差异说明</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, idx) in rows" :key="String(row[ROW_ID_KEY] ?? idx)">
          <td>{{ row.grade ?? '' }}</td>
          <td>
            <input
              :value="String(row.member_name ?? '')"
              :readonly="readonly"
              @input="onCellInput(row, 'member_name', $event)"
            />
          </td>
          <td>
            <input
              :value="String(row.budget_execution_hours ?? '')"
              :readonly="readonly"
              @input="onCellInput(row, 'budget_execution_hours', $event)"
            />
          </td>
          <td>
            <input
              :value="String(row.budget_review_hours ?? '')"
              :readonly="readonly"
              @input="onCellInput(row, 'budget_review_hours', $event)"
            />
          </td>
          <td>
            <input
              :value="String(row.hourly_rate ?? '')"
              :readonly="readonly"
              @input="onCellInput(row, 'hourly_rate', $event)"
            />
          </td>
          <td>
            <input
              class="b60-hour-budget__actual-exec"
              :value="String(row.actual_execution_hours ?? '')"
              :readonly="readonly"
              @input="onCellInput(row, 'actual_execution_hours', $event)"
            />
          </td>
          <td>
            <input
              :value="String(row.actual_review_hours ?? '')"
              :readonly="readonly"
              @input="onCellInput(row, 'actual_review_hours', $event)"
            />
          </td>
          <td>
            <input
              :value="String(row.variance_note ?? '')"
              :readonly="readonly"
              @input="onCellInput(row, 'variance_note', $event)"
            />
          </td>
        </tr>
        <tr v-if="rows.length === 0">
          <td colspan="8" class="b60-hour-budget__empty">暂无行（打开在线编辑并 forcesave 后将镜像至此）</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.b60-hour-budget__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.b60-hour-budget__table th,
.b60-hour-budget__table td {
  border: 1px solid #dcdfe6;
  padding: 4px 6px;
}
.b60-hour-budget__table input {
  width: 100%;
  border: none;
  background: transparent;
  font: inherit;
}
.b60-hour-budget__empty {
  color: #909399;
  padding: 12px;
}
</style>
