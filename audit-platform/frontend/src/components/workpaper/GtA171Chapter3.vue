<!--
  GtA171Chapter3.vue — A17-1 第3章「对审计计划的更新和修改」结构化组件
  独立持久化：item_id 前缀 a171-ch3-s{1|2|3}-*，不经过 chapters['3'].content
-->
<template>
  <div class="gt-ch3">
    <!-- 适用性总开关 -->
    <div class="gt-ch3__toggle">
      <span class="gt-ch3__toggle-label">本期是否对审计计划做了重大修改？</span>
      <el-switch v-model="hasModification" active-text="是" inactive-text="否" @change="onToggle" />
    </div>

    <!-- 无修改 -->
    <el-alert v-if="!hasModification" type="success" :closable="false" show-icon class="gt-ch3__no-mod">
      <template #title>审计工作按总体审计策略进行，本期未对审计计划做重大修改。</template>
    </el-alert>

    <!-- 有修改：3个区块 -->
    <template v-else>
      <!-- 区块1: 修改轮次 -->
      <el-card shadow="never" class="gt-ch3__card">
        <template #header>
          <div class="gt-ch3__card-hd">
            <span class="gt-ch3__card-title">1、对审计计划的修改及理由</span>
            <div class="gt-ch3__card-actions">
              <el-switch v-model="s1Applicable" size="small" active-text="适用" inactive-text="不适用" @change="save" />
              <el-button size="small" :loading="aiLoading === 1" @click="aiGenerate(1)">🤖 AI</el-button>
            </div>
          </div>
        </template>
        <template v-if="s1Applicable">
          <el-table :data="modRows" border size="small" class="gt-ch3__table">
            <el-table-column label="修改轮次" width="90">
              <template #default="{ $index }">第{{ $index + 1 }}次</template>
            </el-table-column>
            <el-table-column label="修改时间" width="120">
              <template #default="{ row }">
                <el-date-picker v-model="row.time" type="date" size="small" value-format="YYYY-MM-DD" placeholder="日期" @change="save" />
              </template>
            </el-table-column>
            <el-table-column label="原计划或安排" min-width="150">
              <template #default="{ row }">
                <el-input v-model="row.original" type="textarea" :autosize="{minRows:1,maxRows:4}" size="small" @change="save" />
              </template>
            </el-table-column>
            <el-table-column label="更新和修改情况" min-width="150">
              <template #default="{ row }">
                <el-input v-model="row.updated" type="textarea" :autosize="{minRows:1,maxRows:4}" size="small" @change="save" />
              </template>
            </el-table-column>
            <el-table-column label="修改理由" min-width="150">
              <template #default="{ row }">
                <el-input v-model="row.reason" type="textarea" :autosize="{minRows:1,maxRows:4}" size="small" @change="save" />
              </template>
            </el-table-column>
            <el-table-column label="修改后程序" min-width="150">
              <template #default="{ row }">
                <el-input v-model="row.procedure" type="textarea" :autosize="{minRows:1,maxRows:4}" size="small" @change="save" />
              </template>
            </el-table-column>
            <el-table-column width="45" align="center">
              <template #default="{ $index }">
                <el-button type="danger" link size="small" @click="removeRow($index)">×</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-button size="small" type="primary" plain @click="addRow" style="margin-top:6px">+ 添加轮次</el-button>
        </template>
        <el-alert v-else type="info" :closable="false" show-icon title="本节不适用" />
      </el-card>

      <!-- 区块2: 重要性水平 -->
      <el-card shadow="never" class="gt-ch3__card">
        <template #header>
          <div class="gt-ch3__card-hd">
            <span class="gt-ch3__card-title">2、重要性水平的再评估</span>
            <div class="gt-ch3__card-actions">
              <el-switch v-model="s2Applicable" size="small" active-text="适用" inactive-text="不适用" @change="save" />
              <el-button size="small" :loading="aiLoading === 2" @click="aiGenerate(2)">🤖 AI</el-button>
            </div>
          </div>
        </template>
        <template v-if="s2Applicable">
          <p class="gt-ch3__hint">根据审定的财务数据，重新确定重要性水平，与计划阶段对比分析。</p>
          <el-table :data="matRows" border size="small" class="gt-ch3__table">
            <el-table-column label="确定的重要性水平" min-width="280">
              <template #default="{ row, $index }">
                <span v-if="$index === 0">确定基准：{{ row.desc }}</span>
                <span v-else>{{ row.desc }}（{{ row.label }} = <el-input v-model="row.ratio" size="small" style="width:50px;display:inline-block" placeholder="X%" @change="save" /> × {{ $index === 1 ? '基准' : 'PM' }}）</span>
              </template>
            </el-table-column>
            <el-table-column label="计划审计阶段" min-width="120">
              <template #default="{ row }"><el-input v-model="row.plan" size="small" placeholder="计划值" @change="save" /></template>
            </el-table-column>
            <el-table-column label="审计完成阶段" min-width="120">
              <template #default="{ row }"><el-input v-model="row.actual" size="small" placeholder="完成值" @change="save" /></template>
            </el-table-column>
          </el-table>
          <el-input v-model="matConclusion" type="textarea" :autosize="{minRows:2}" placeholder="对比分析结论" style="margin-top:6px" @change="save" />
        </template>
        <el-alert v-else type="info" :closable="false" show-icon title="本节不适用" />
      </el-card>

      <!-- 区块3: 工时 -->
      <el-card shadow="never" class="gt-ch3__card">
        <template #header>
          <div class="gt-ch3__card-hd">
            <span class="gt-ch3__card-title">3、项目完成工时情况</span>
            <div class="gt-ch3__card-actions">
              <el-switch v-model="s3Applicable" size="small" active-text="适用" inactive-text="不适用" @change="save" />
              <el-button size="small" :loading="aiLoading === 3" @click="aiGenerate(3)">🤖 AI</el-button>
            </div>
          </div>
        </template>
        <template v-if="s3Applicable">
          <el-input v-model="workHours" type="textarea" :autosize="{minRows:2}" placeholder="计划X天结束现场审计……如增减工时达10%以上应说明原因。" @change="save" />
        </template>
        <el-alert v-else type="info" :closable="false" show-icon title="本节不适用" />
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

interface ModRow { time: string; original: string; updated: string; reason: string; procedure: string }

const props = defineProps<{ wpId: string; projectId: string; clientName?: string }>()

// ─── State ───
const hasModification = ref(false)
const s1Applicable = ref(true)
const s2Applicable = ref(true)
const s3Applicable = ref(true)
const aiLoading = ref<number | null>(null)
const modRows = ref<ModRow[]>([{ time: '', original: '', updated: '', reason: '', procedure: '' }])
const matRows = ref([
  { label: '确定基准', desc: `${props.clientName || '被审计单位'}经常性税前利润总额`, ratio: '', plan: '', actual: '' },
  { label: 'PM', desc: '财务报表层次的重要性水平', ratio: '', plan: '', actual: '' },
  { label: 'TE', desc: '认定层次的重要性水平', ratio: '', plan: '', actual: '' },
  { label: 'SAD', desc: '审计差异归集界限', ratio: '', plan: '', actual: '' },
])
const matConclusion = ref('')
const workHours = ref('')

// ─── Persistence (独立 item_id，不走 content) ───
let _saveTimer: ReturnType<typeof setTimeout> | null = null

function save() {
  if (_saveTimer) clearTimeout(_saveTimer)
  _saveTimer = setTimeout(doSave, 2000)
}

async function doSave() {
  if (!props.wpId) return
  const items: { item_id: string; conclusion: string | null; remark: string | null }[] = [
    { item_id: 'a171-ch3-toggle', conclusion: hasModification.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch3-s1-applicable', conclusion: s1Applicable.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch3-s2-applicable', conclusion: s2Applicable.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch3-s3-applicable', conclusion: s3Applicable.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch3-s1-rows', conclusion: null, remark: JSON.stringify(modRows.value) },
    { item_id: 'a171-ch3-s2-materiality', conclusion: null, remark: JSON.stringify(matRows.value.map(r => ({ ratio: r.ratio, plan: r.plan, actual: r.actual }))) },
    { item_id: 'a171-ch3-s2-conclusion', conclusion: null, remark: matConclusion.value || null },
    { item_id: 'a171-ch3-s3-hours', conclusion: null, remark: workHours.value || null },
  ]
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined, items,
    })
  } catch { /* retry handled by parent composable pattern */ }
}

// ─── Load ───
async function loadData() {
  if (!props.wpId) return
  try {
    const res = await api.get<any[]>(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
    const items = Array.isArray(res) ? res : (res as any)?.data || []
    const map = new Map<string, { conclusion?: string; remark?: string }>()
    for (const r of items) { if (r.item_id?.startsWith('a171-ch3-')) map.set(r.item_id, r) }

    hasModification.value = map.get('a171-ch3-toggle')?.conclusion === 'Y'
    s1Applicable.value = map.get('a171-ch3-s1-applicable')?.conclusion !== 'N'
    s2Applicable.value = map.get('a171-ch3-s2-applicable')?.conclusion !== 'N'
    s3Applicable.value = map.get('a171-ch3-s3-applicable')?.conclusion !== 'N'

    const rowsJson = map.get('a171-ch3-s1-rows')?.remark
    if (rowsJson) { try { modRows.value = JSON.parse(rowsJson) } catch {} }

    const matJson = map.get('a171-ch3-s2-materiality')?.remark
    if (matJson) {
      try {
        const parsed = JSON.parse(matJson)
        for (let i = 0; i < matRows.value.length && i < parsed.length; i++) {
          matRows.value[i].ratio = parsed[i].ratio || ''
          matRows.value[i].plan = parsed[i].plan || ''
          matRows.value[i].actual = parsed[i].actual || ''
        }
      } catch {}
    }
    matConclusion.value = map.get('a171-ch3-s2-conclusion')?.remark || ''
    workHours.value = map.get('a171-ch3-s3-hours')?.remark || ''
  } catch { /* silent */ }
}

// ─── Actions ───
function onToggle() { save() }
function addRow() { modRows.value.push({ time: '', original: '', updated: '', reason: '', procedure: '' }); save() }
function removeRow(i: number) { modRows.value.splice(i, 1); save() }

async function aiGenerate(section: number) {
  const titles: Record<number, string> = { 1: '对审计计划的修改及理由', 2: '重要性水平的再评估', 3: '项目完成工时情况' }
  const guidances: Record<number, string> = {
    1: '根据本项目审计计划变更情况，生成修改轮次内容。',
    2: '根据B15重要性水平数据，对比计划与完成阶段PM/TE/SAD，生成分析结论。',
    3: '根据项目实际工时与计划工时，生成工时对比说明。',
  }
  aiLoading.value = section
  try {
    const res = await api.post<any>(`/api/workpapers/${props.wpId}/a171/ai-generate`, {
      chapter: 3, chapter_title: titles[section] || '', guidance: guidances[section] || '',
      existing_content: '', knowledge_doc_ids: [],
    }, { _silent: true } as any)
    const content = res?.content || ''
    if (!content) { ElMessage.info('AI 未生成有效内容'); return }
    if (section === 1) { modRows.value = [{ time: '', original: '', updated: content, reason: '', procedure: '' }] }
    else if (section === 2) { matConclusion.value = content }
    else if (section === 3) { workHours.value = content }
    save()
    ElMessage.success('AI 已生成，可编辑后自动保存')
  } catch { ElMessage.warning('AI 生成失败') }
  finally { aiLoading.value = null }
}

onMounted(loadData)
</script>

<style scoped>
.gt-ch3 { font-size: var(--wp-font-size, 13px); display: flex; flex-direction: column; gap: 12px; }
.gt-ch3__toggle { display: flex; align-items: center; gap: 12px; padding: 8px 12px; background: #f4f0fa; border-radius: 6px; }
.gt-ch3__toggle-label { font-size: var(--wp-font-size, 13px); font-weight: 500; }
.gt-ch3__toggle :deep(.el-switch__label) { font-size: var(--wp-font-size, 13px); }
.gt-ch3__no-mod { margin-top: 4px; }
.gt-ch3__no-mod :deep(.el-alert__title) { font-size: var(--wp-font-size, 13px); }
.gt-ch3__card { margin-top: 4px; }
.gt-ch3__card-hd { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.gt-ch3__card-actions { display: flex; align-items: center; gap: 8px; }
.gt-ch3__card-actions :deep(.el-switch__label) { font-size: var(--wp-font-size, 13px); }
.gt-ch3__card-title { font-size: var(--wp-font-size, 13px); font-weight: 600; color: #6b21a8; }
.gt-ch3__hint { font-size: var(--wp-font-size, 13px); color: #909399; margin: 0 0 8px; }
.gt-ch3__table { font-size: var(--wp-font-size, 13px); }
.gt-ch3__table :deep(.el-table__cell) { font-size: var(--wp-font-size, 13px); vertical-align: top; }
.gt-ch3__table :deep(.el-textarea__inner) { font-size: var(--wp-font-size, 13px); line-height: 1.5; }
.gt-ch3__table :deep(.el-input__inner) { font-size: var(--wp-font-size, 13px); text-align: right; }
</style>
