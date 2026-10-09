<script setup lang="ts">
/**
 * B60-1 工时预算 HTML 面（G4-1 simple checklist canary）。
 * store item: B60-1-hour-budget-rows；行身份 rowUuid。
 *
 * ═══ 双向都已接通（2026-09-27）═══
 *
 * · HTML → OO：宿主 `GtB60Bundle` 的 `flushHtml` 先 await 本组件 `flushPendingSave()`
 *   再 `readStoreProjection` → materialize（防抖 600ms，不等它会丢最后一批编辑）。
 * · OO → HTML：forcesave 后 `oo_to_html._mirror_store_backed_if_needed` 按
 *   `store_item_registry` 的 plan 取 `pilot_simple_checklist.merge_projection_into_store_rows`
 *   （实现在伴生模块 `pilot_b60_store_merge`），把受管格合并回本 store item。
 *
 * 🔴 三方身份必须逐字一致，改任何一处都要同改其余两处（有判据守着）：
 *   · `STORE_ITEM_ID` ↔ `pilot_simple_checklist.STORE_ITEM_ID` ↔ 契约 `html_store.item_ids`
 *   · `ROW_ID_KEY` ↔ `pilot_simple_checklist.ROW_IDENTITY_STORE_KEY` ↔ 契约
 *     `row_identity.json_pointer`（`/rows` 下每行的 `rowUuid`）
 *     🔴 这里**不能**把 json_pointer 原样写成 `/rows/<星号>/rowUuid`：其中的 `*` 紧跟 `/`
 *     会构成 `*` + `/` 的块注释结束符，把本注释提前截断、整个文件语法破损
 *     （本文件曾因此让 `discover-workpaper-sync-mounts.mjs` 与前端构建双双失败）。
 *   · 字段名扁平 snake_case ↔ 契约 `json_pointer` ↔ `MANAGED_FIELD_SPECS` 的 column_key
 *
 * ⚠️ F 列 `budget_cost`（=(C+D)*E）**不会**回写到这里：它是 Excel 侧公式，
 * 固化进 HTML store 会造第二份事实（回方向按 mode 过滤掉）。本表也不显示该列。
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
          <!--
            🔴 这句文案有过两次反转，都是跟着后端真实能力走的：
            ① 最初写「打开在线编辑并 forcesave 后将镜像至此」—— 当时 b60 属
               NON_STORE_BACKED_ADAPTERS，镜像被跳过，是一句不成立的承诺；
            ② 随后改成「暂不会回写到这里」—— 如实，但那是缺口登记；
            ③ 2026-09-27 契约补了 html_store、注册表转真 store-backed、merge 门面落地
               （有 roundtrip 判据），承诺这才成立。
          -->
          <td colspan="8" class="b60-hour-budget__empty">
            暂无行。本表可直接录入；在「在线编辑」里保存后也会回写到这里
          </td>
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
