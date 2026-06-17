<script setup lang="ts">
/**
 * GtContingentLiability — 或有事项审计底稿组件 (A5-3)
 *
 * 可能性三级判断 + 处理联动 + 附注披露链接
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { api } from '@/services/apiProxy'
import { ElMessage } from 'element-plus'

const props = defineProps<{ wpId: string; projectId?: string; htmlData?: any; readonly?: boolean }>()
const emit = defineEmits<{ (e: 'save'): void }>()

type Likelihood = 'probable' | 'possible' | 'remote' | ''
type Treatment = 'provision' | 'disclose' | 'none' | ''

interface ContingentItem {
  id: string
  description: string
  category: string
  likelihood: Likelihood
  treatment: Treatment
  amount: number
  note_section: string
  remark: string
}

const LIKELIHOOD_OPTIONS = [
  { value: 'probable', label: '很可能(>50%)', type: 'danger' },
  { value: 'possible', label: '可能(5%~50%)', type: 'warning' },
  { value: 'remote', label: '极小可能(<5%)', type: 'info' },
]

const TREATMENT_MAP: Record<string, Treatment> = {
  probable: 'provision',
  possible: 'disclose',
  remote: 'none',
}

const items = ref<ContingentItem[]>([])

function addItem() {
  items.value.push({
    id: `ci_${Date.now()}`,
    description: '',
    category: '诉讼',
    likelihood: '',
    treatment: '',
    amount: 0,
    note_section: '',
    remark: '',
  })
}

function removeItem(idx: number) {
  items.value.splice(idx, 1)
  scheduleSave()
}

function onLikelihoodChange(item: ContingentItem) {
  item.treatment = TREATMENT_MAP[item.likelihood] || ''
  scheduleSave()
}

// ─── 保存 ───
const saving = ref(false)
let saveTimer: ReturnType<typeof setTimeout> | null = null
function scheduleSave() {
  if (props.readonly) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(doSave, 2000)
}
async function doSave() {
  if (saving.value) return
  saving.value = true
  try {
    await api.put(`/api/workpapers/${props.wpId}/parsed-data`, { contingent_liability: { items: items.value } })
    emit('save')
  } catch { ElMessage.error('保存失败') }
  finally { saving.value = false }
}

async function loadData() {
  if (!props.wpId) return
  try {
    const data = await api.get(`/api/workpapers/${props.wpId}/render-config`)
    const parsed = data?.sheets?.[0]?.html_data?.contingent_liability || data?.fill_results?.contingent_liability
    if (parsed?.items) items.value = parsed.items
  } catch { /* 降级 */ }
}

onMounted(loadData)
onBeforeUnmount(() => { if (saveTimer) { clearTimeout(saveTimer); doSave() } })
</script>

<template>
  <div class="gt-contingent-liability">
    <div class="gt-cl-toolbar">
      <h4>或有事项清单</h4>
      <el-button v-if="!readonly" size="small" @click="addItem">+ 添加事项</el-button>
    </div>

    <el-table :data="items" border size="small" class="gt-compact-table">
      <el-table-column label="事项描述" min-width="200">
        <template #default="{ $index }">
          <el-input v-model="items[$index].description" :disabled="readonly" size="small" @change="scheduleSave" />
        </template>
      </el-table-column>
      <el-table-column label="类别" width="100">
        <template #default="{ $index }">
          <el-select v-model="items[$index].category" :disabled="readonly" size="small" @change="scheduleSave">
            <el-option label="诉讼" value="诉讼" />
            <el-option label="担保" value="担保" />
            <el-option label="质量保证" value="质量保证" />
            <el-option label="环境" value="环境" />
            <el-option label="其他" value="其他" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="可能性判断" width="150">
        <template #default="{ $index, row }">
          <el-select v-model="items[$index].likelihood" :disabled="readonly" size="small" @change="onLikelihoodChange(row)">
            <el-option v-for="opt in LIKELIHOOD_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="处理方式" width="130">
        <template #default="{ row }">
          <el-tag v-if="row.treatment === 'provision'" type="danger" size="small">确认预计负债</el-tag>
          <el-tag v-else-if="row.treatment === 'disclose'" type="warning" size="small">附注披露</el-tag>
          <el-tag v-else-if="row.treatment === 'none'" type="info" size="small">无需披露</el-tag>
          <span v-else class="gt-cl-pending">待判断</span>
        </template>
      </el-table-column>
      <el-table-column label="金额(万元)" width="120">
        <template #default="{ $index }">
          <el-input-number v-model="items[$index].amount" :disabled="readonly" size="small" :controls="false" @change="scheduleSave" />
        </template>
      </el-table-column>
      <el-table-column label="附注章节" width="100">
        <template #default="{ $index }">
          <el-input v-model="items[$index].note_section" :disabled="readonly" size="small" placeholder="五、xx" @change="scheduleSave" />
        </template>
      </el-table-column>
      <el-table-column v-if="!readonly" label="" width="60">
        <template #default="{ $index }">
          <el-button size="small" text type="danger" @click="removeItem($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 汇总 -->
    <div v-if="items.length" class="gt-cl-summary">
      <span>预计负债：{{ items.filter(i => i.treatment === 'provision').length }} 项，合计 {{ items.filter(i => i.treatment === 'provision').reduce((s, i) => s + i.amount, 0).toLocaleString() }} 万元</span>
      <span>附注披露：{{ items.filter(i => i.treatment === 'disclose').length }} 项</span>
    </div>
  </div>
</template>

<style scoped>
.gt-contingent-liability { padding: 12px; }
.gt-cl-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.gt-cl-toolbar h4 { margin: 0; font-size: 14px; color: var(--gt-primary, #4b2d77); }
.gt-cl-pending { color: #999; font-size: 12px; }
.gt-cl-summary { margin-top: 12px; display: flex; gap: 24px; font-size: 12px; color: #666; }
</style>
