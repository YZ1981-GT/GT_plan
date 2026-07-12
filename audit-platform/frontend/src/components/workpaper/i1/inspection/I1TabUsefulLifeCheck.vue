<template>
  <div class="i1-tab-useful-life-check">
    <!-- 琥珀色方法论上下文（CAS6 §11-15 使用寿命规则） -->
    <div class="methodology-context">
      <p><b>CAS6 §11-15 使用寿命规则</b>：无形资产使用寿命有限的，自可供使用时起在预计使用寿命内系统合理摊销；
      使用寿命不确定的无形资产不应摊销，但应当在每个会计期间进行减值测试（CAS8）。
      企业至少应于每年年度终了对使用寿命有限的无形资产的使用寿命及摊销方法进行复核，
      寿命估计发生变更的，应当作为会计估计变更处理（CAS28）。使用寿命的确定应考虑：
      ①法律规定的有效年限 ②合同约定的受益年限 ③技术更新换代周期 ④行业惯例及同类资产情况。</p>
    </div>

    <!-- 蓝色引导区 -->
    <div class="guidance-area">
      <div class="guidance-grid">
        <div class="guidance-step"><span class="step-num">①</span> 逐项核查使用寿命估计：对照合同/法律有效期、技术更新周期、行业惯例，评估寿命估计的合理性</div>
        <div class="guidance-step"><span class="step-num">②</span> 关注使用寿命不确定项：标注"不摊销"的资产须每期进行减值测试，跳转I1-12核实减值结论</div>
      </div>
    </div>

    <!-- 主检查表 -->
    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>I1-7 使用寿命检查表（{{ rows.length }} 项）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" type="primary" link @click="handleAiGenerate('usefullife-review')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('I1-7')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="rows" border stripe size="small" max-height="500" class="check-table">
        <!-- 1. 序号 -->
        <el-table-column type="index" label="序号" width="50" align="center" fixed />
        <!-- 2. 名称 -->
        <el-table-column prop="name" label="名称" min-width="130" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" placeholder="无形资产名称" @change="handleChange" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <!-- 3. 原始寿命（月） -->
        <el-table-column prop="usefulLifeMonths" label="原始寿命(月)" width="110" align="right">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input-number v-model="row.usefulLifeMonths" :controls="false" size="small" :min="0" :precision="0" placeholder="0=不确定" @change="handleChange" />
            </template>
            <template v-else>
              <span v-if="row.usefulLifeMonths === 0" class="indefinite-tag">不摊销</span>
              <span v-else>{{ row.usefulLifeMonths }}</span>
            </template>
          </template>
        </el-table-column>
        <!-- 4. 已用年限 -->
        <el-table-column prop="usedYears" label="已用年限" width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.usedYears" :controls="false" size="small" :min="0" :precision="1" @change="handleChange" />
            <span v-else>{{ row.usedYears ?? '-' }}</span>
          </template>
        </el-table-column>
        <!-- 5. 剩余年限（公式） -->
        <el-table-column label="剩余年限" width="90" align="right">
          <template #default="{ row }">
            <template v-if="row.usefulLifeMonths === 0">
              <span class="indefinite-tag">不确定</span>
            </template>
            <template v-else>
              <el-tooltip content="剩余年限 = 原始寿命(月)/12 - 已用年限" placement="top">
                <span class="formula-cell">{{ fmtYears(calcRemainingYears(row)) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>
        <!-- 6. 寿命依据 -->
        <el-table-column prop="lifeBasis" label="寿命依据" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.lifeBasis" size="small" placeholder="如：合同约定/法律年限/技术周期" @change="handleChange" />
            <span v-else>{{ row.lifeBasis || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 7. 本期是否变更 -->
        <el-table-column prop="isChanged" label="本期是否变更" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isChanged" size="small" placeholder="-" @change="onChangeToggle(row)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <el-tag v-else :type="row.isChanged === '是' ? 'warning' : 'info'" size="small">
              {{ row.isChanged || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <!-- 8. 变更原因（仅当变更=是时显示） -->
        <el-table-column prop="changeReason" label="变更原因" min-width="150">
          <template #default="{ row }">
            <template v-if="row.isChanged === '是'">
              <el-input
                v-if="!isReadonly"
                v-model="row.changeReason"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }"
                size="small"
                placeholder="说明使用寿命变更原因..."
                @change="handleChange"
              />
              <span v-else>{{ row.changeReason || '-' }}</span>
            </template>
            <span v-else class="na-cell">—</span>
          </template>
        </el-table-column>
        <!-- 9. 结论 -->
        <el-table-column prop="conclusion" label="结论" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.conclusion" size="small" placeholder="-" @change="handleChange">
              <el-option label="合理" value="合理" />
              <el-option label="需关注" value="需关注" />
              <el-option label="不合理" value="不合理" />
            </el-select>
            <el-tag v-else :type="conclusionTagType(row.conclusion)" size="small">
              {{ row.conclusion || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <!-- 10. 联动跳转 -->
        <el-table-column label="联动" width="80" align="center">
          <template #default="{ row }">
            <el-tooltip v-if="row.usefulLifeMonths === 0" content="跳转减值测试 I1-12" placement="top">
              <GtIndexChip value="I1-12" @click="emit('navigate-sheet', '减值准备测试表I1-12')" />
            </el-tooltip>
            <el-tooltip v-else content="跳转摊销测算" placement="top">
              <GtIndexChip value="I1-10" @click="emit('navigate-sheet', '摊销测算表（不含减值）I1-10')" />
            </el-tooltip>
          </template>
        </el-table-column>
        <!-- 操作列 -->
        <el-table-column label="操作" width="50" v-if="!isReadonly" fixed="right">
          <template #default="{ $index }">
            <el-button size="small" type="danger" link @click="handleRemoveRow($index)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计行 -->
      <div class="summary-bar">
        <span>资产总数: <b>{{ rows.length }}</b></span>
        <span>不摊销项: <b :class="{ 'warn-count': indefiniteCount > 0 }">{{ indefiniteCount }}</b></span>
        <span>本期变更: <b :class="{ 'warn-count': changedCount > 0 }">{{ changedCount }}</b></span>
        <span>合理: <b class="ok-count">{{ conclusionStats.reasonable }}</b></span>
        <span>需关注: <b class="warn-count">{{ conclusionStats.attention }}</b></span>
        <span>不合理: <b class="error-count">{{ conclusionStats.unreasonable }}</b></span>
        <GtIndexChip value="审定表I1" @click="emit('navigate-sheet', '审定表I1')" />
        <GtIndexChip value="I1-10" @click="emit('navigate-sheet', '摊销测算表（不含减值）I1-10')" />
        <GtIndexChip value="I1-11" @click="emit('navigate-sheet', '摊销测算表（含减值）I1-11')" />
      </div>
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('usefullife-conclusion')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="对各项无形资产使用寿命估计合理性的审计结论..."
        @change="saveConclusion"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>原始寿命填0表示使用寿命不确定（不摊销），需每期进行减值测试（CAS8）</li>
        <li>剩余年限 = 原始寿命(月) ÷ 12 - 已用年限，剩余≤0表示已摊销完毕</li>
        <li>寿命依据可填写：合同约定年限 / 法律保护期限 / 技术更新周期 / 行业惯例</li>
        <li>本期变更=是时，需说明变更原因并按CAS28会计估计变更处理</li>
        <li>使用寿命不确定的资产不摊销，但须链接减值测试表I1-12</li>
        <li>摊销参数变更将影响I1-10/I1-11摊销测算结果</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, watch, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

// ─── Props & Emits ────────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

// ─── Inject ───────────────────────────────────────────────────────────────────
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── State ────────────────────────────────────────────────────────────────────
interface UsefulLifeRow {
  rowId: string
  name: string
  usefulLifeMonths: number
  usedYears: number
  lifeBasis: string
  isChanged: string
  changeReason: string
  conclusion: string
}

const rows = ref<UsefulLifeRow[]>([])
const auditConclusion = ref('')

const STORAGE_KEY = 'I1-7-rows'
const CONCLUSION_KEY = 'I1-7-conclusion'

// ─── Computed Stats ───────────────────────────────────────────────────────────
const indefiniteCount = computed(() => rows.value.filter(r => r.usefulLifeMonths === 0).length)
const changedCount = computed(() => rows.value.filter(r => r.isChanged === '是').length)

const conclusionStats = computed(() => {
  const stats = { reasonable: 0, attention: 0, unreasonable: 0 }
  for (const r of rows.value) {
    if (r.conclusion === '合理') stats.reasonable++
    else if (r.conclusion === '需关注') stats.attention++
    else if (r.conclusion === '不合理') stats.unreasonable++
  }
  return stats
})

// ─── Formula Helpers ──────────────────────────────────────────────────────────
function calcRemainingYears(row: UsefulLifeRow): number {
  if (row.usefulLifeMonths === 0) return 0
  const totalYears = row.usefulLifeMonths / 12
  return totalYears - (row.usedYears || 0)
}

function fmtYears(val: number): string {
  if (val <= 0) return '已到期'
  return val.toFixed(1)
}

// ─── UI Helpers ───────────────────────────────────────────────────────────────
function conclusionTagType(conclusion: string): 'success' | 'warning' | 'danger' | 'info' {
  if (conclusion === '合理') return 'success'
  if (conclusion === '需关注') return 'warning'
  if (conclusion === '不合理') return 'danger'
  return 'info'
}

// ─── Row Operations ───────────────────────────────────────────────────────────
function createRow(name: string): UsefulLifeRow {
  return {
    rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name,
    usefulLifeMonths: 120,
    usedYears: 0,
    lifeBasis: '',
    isChanged: '否',
    changeReason: '',
    conclusion: '',
  }
}

async function handleAddRow() {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入无形资产名称', '新增使用寿命检查项', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：XX专利/商标/软件著作权',
    })
    if (name?.trim()) {
      rows.value.push(createRow(name.trim()))
      handleChange()
    }
  } catch { /* cancelled */ }
}

function handleRemoveRow(index: number) {
  rows.value.splice(index, 1)
  handleChange()
}

function onChangeToggle(row: UsefulLifeRow) {
  if (row.isChanged !== '是') {
    row.changeReason = ''
  }
  handleChange()
}

// ─── Persistence ──────────────────────────────────────────────────────────────
function handleChange() {
  emit('save', STORAGE_KEY, JSON.stringify(rows.value))
}

function saveConclusion() {
  emit('save', CONCLUSION_KEY, auditConclusion.value)
}

function loadFromResponses() {
  if (!props.allResponses) return
  const raw = props.allResponses.get(STORAGE_KEY)
  if (raw) {
    try {
      rows.value = JSON.parse(typeof raw === 'string' ? raw : raw.value || '[]')
    } catch { rows.value = [] }
  }
  const concRaw = props.allResponses.get(CONCLUSION_KEY)
  if (concRaw) {
    auditConclusion.value = typeof concRaw === 'string' ? concRaw : concRaw.value || ''
  }
}

// ─── AI Generate ──────────────────────────────────────────────────────────────
async function handleAiGenerate(section: string) {
  try {
    const context = `使用寿命检查表共${rows.length}项资产，其中不摊销（使用寿命不确定）${indefiniteCount.value}项，本期变更${changedCount.value}项，结论分布：合理${conclusionStats.value.reasonable}/需关注${conclusionStats.value.attention}/不合理${conclusionStats.value.unreasonable}`
    const resp = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section,
      prompt: '请根据使用寿命检查结果，评估各资产寿命估计的合理性，关注不摊销项及本期变更项',
      context,
      existingContent: auditConclusion.value,
    })
    if (resp.data?.data?.content) {
      auditConclusion.value = resp.data.data.content
      saveConclusion()
    }
  } catch { /* silent */ }
}

// ─── Review ───────────────────────────────────────────────────────────────────
function handleReview(id: string) {
  openReviewDialog(id)
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(() => {
  loadFromResponses()
})

watch(() => props.allResponses, () => {
  loadFromResponses()
}, { deep: true })
</script>

<style scoped>
.i1-tab-useful-life-check { padding: 16px; font-size: var(--wp-font-size, 13px); }

.methodology-context {
  border-left: 3px solid var(--el-color-warning);
  background: #fffbe6;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #6b5900;
}

.guidance-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border-radius: 6px;
  padding: 12px 16px;
  margin-bottom: 12px;
}
.guidance-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.guidance-step {
  font-size: 12px;
  color: #1a5276;
  display: flex;
  align-items: flex-start;
  gap: 6px;
}
.step-num {
  font-weight: 700;
  color: #2980b9;
  flex-shrink: 0;
}

.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; align-items: center; }

.check-table { font-size: var(--wp-font-size, 13px); }

.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

.indefinite-tag {
  color: var(--el-color-warning-dark-2);
  font-weight: 600;
  font-size: 12px;
}

.na-cell {
  color: var(--el-text-color-placeholder);
}

.summary-bar {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  align-items: center;
  padding: 10px 12px;
  margin-top: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 12px;
}
.ok-count { color: var(--el-color-success); }
.warn-count { color: var(--el-color-warning-dark-2); }
.error-count { color: var(--el-color-danger); }

.note-card { margin-top: 12px; }

.compile-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
