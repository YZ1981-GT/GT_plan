<template>
  <div class="n5-high-tech-check">
    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <p><strong>高新技术企业认定条件检查（N5-6-2）</strong>：逐条核查《高新技术企业认定管理办法》规定的8项认定条件。全部满足方可适用15%优惠税率。任一条件不满足应警示，影响N5-6税收优惠中优惠税率的适用。</p>
    </div>

    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>高新技术企业认定条件检查表 N5-6-2</span>
        <el-tag :type="overallPassed ? 'success' : 'danger'" size="small">
          {{ overallPassed ? '✓ 全部满足' : '⚠ 存在不满足条件' }}
        </el-tag>
      </div>
      <div class="section-actions">
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon>AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon>复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 认定结论 ═══ -->
    <div class="conclusion-banner" :class="overallPassed ? 'pass' : 'fail'">
      <div class="cb-main">
        <span class="cb-icon">{{ overallPassed ? '✓' : '✗' }}</span>
        <span class="cb-text">
          {{ overallPassed ? '认定条件全部满足，企业可适用15%优惠税率' : '存在不满足条件，不得适用15%优惠税率（适用一般税率25%）' }}
        </span>
      </div>
      <div class="cb-stats">
        <span class="cb-stat pass">满足: {{ passedCount }}/{{ checkItems.length }}</span>
        <span class="cb-stat fail" v-if="failedCount > 0">不满足: {{ failedCount }}</span>
      </div>
    </div>

    <!-- ═══ 认定条件检查表 ═══ -->
    <el-table :data="checkItems" border size="small" class="check-table" :row-class-name="getCheckRowClass">
      <el-table-column prop="seq" label="序号" width="55" align="center" />
      <el-table-column prop="category" label="类别" width="110">
        <template #default="{ row }">
          <el-tag :type="getCategoryType(row.category)" size="small">{{ row.category }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="condition" label="认定条件" min-width="260">
        <template #default="{ row }">
          <span class="condition-text">{{ row.condition }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="standard" label="标准/要求" min-width="160">
        <template #default="{ row }">
          <span class="standard-text">{{ row.standard }}</span>
        </template>
      </el-table-column>
      <el-table-column label="实际情况" min-width="140">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model="row.actualValue" size="small" placeholder="填写实际值" @change="() => handleCheckUpdate($index)" />
          <span v-else class="cell-value">{{ row.actualValue || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="是否满足" width="100" align="center">
        <template #default="{ row, $index }">
          <el-select v-if="!isReadonly" v-model="row.result" size="small" style="width: 80px" @change="() => handleCheckUpdate($index)">
            <el-option value="满足" label="满足" />
            <el-option value="不满足" label="不满足" />
            <el-option value="待定" label="待定" />
          </el-select>
          <template v-else>
            <span :class="['result-badge', row.result === '满足' ? 'result-pass' : row.result === '不满足' ? 'result-fail' : 'result-pending']">
              {{ row.result || '待定' }}
            </span>
          </template>
        </template>
      </el-table-column>
      <el-table-column prop="evidence" label="审计证据/备注" min-width="160">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model="row.evidence" size="small" placeholder="证据说明" @change="() => handleCheckUpdate($index)" />
          <span v-else class="cell-value">{{ row.evidence || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 不满足条件警告 ═══ -->
    <div v-if="failedItems.length > 0" class="failed-warnings">
      <el-alert type="error" :closable="false" show-icon>
        <template #title>
          <span class="warning-title">以下认定条件不满足，影响15%优惠税率适用：</span>
        </template>
        <ul class="warning-list">
          <li v-for="item in failedItems" :key="item.seq">
            <strong>{{ item.category }}</strong> — {{ item.condition }}
            <span v-if="item.actualValue" class="warning-actual">（实际: {{ item.actualValue }}）</span>
          </li>
        </ul>
      </el-alert>
    </div>

    <!-- ═══ 联动N5-6 ═══ -->
    <div class="action-bar">
      <el-button type="primary" size="small" :disabled="isReadonly" :loading="syncLoading" @click="handleSyncConclusion">
        同步认定结论 → N5-6税收优惠
      </el-button>
      <span class="action-hint">{{ overallPassed ? '15%优惠税率适用' : '不适用优惠税率' }}</span>
    </div>

    <!-- ═══ 审计说明与结论 ═══ -->
    <el-card shadow="never" class="audit-notes-card">
      <template #header>
        <div class="notes-header">
          <span>审计说明与结论</span>
          <el-button size="small" @click="handleNotesAi"><el-icon><MagicStick /></el-icon>AI辅助</el-button>
        </div>
      </template>
      <div class="notes-field">
        <label class="field-label">审计说明</label>
        <el-input v-model="auditNotes" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请说明高新认定核查情况..." :disabled="isReadonly" @change="saveNotes" />
      </div>
      <div class="notes-field">
        <label class="field-label">审计结论</label>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="请输入审计结论..." :disabled="isReadonly" @change="saveConclusion" />
      </div>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>高新技术企业认定须同时满足全部8项条件</li>
        <li>核心指标：研发费用占比（5%/4%/3%）、科技人员占比（≥10%）、高新收入占比（≥60%）</li>
        <li>知识产权须在有效期内，且与核心技术/产品直接相关</li>
        <li>认定有效期3年，需注意到期年度</li>
        <li>认定结论影响N5-6优惠税率：通过→15%，不通过→25%</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N5TabHighTechCheck — 高新技术企业认定条件检查表N5-6-2
 *
 * 18×13 + 逐条认定条件检查 + 不满足红色警告
 * 认定结论联动N5-6优惠税率
 *
 * Spec: .kiro/specs/n5-income-tax-expense/ Task 4.11
 * Requirements: 6.4-6.6
 */
import { ref, reactive, computed, inject, onMounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import { useN5FormData } from '../../composables/useN5FormData'

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId?: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)

const wpIdRef = computed(() => props.wpId) as Ref<string>
const projectIdRef = computed(() => props.projectId || '') as Ref<string>

const formData = useN5FormData({ wpId: wpIdRef, projectId: projectIdRef })

// ─── 认定条件数据 ────────────────────────────────────────────────────────────

interface CheckItem {
  seq: number
  category: string
  condition: string
  standard: string
  actualValue: string
  result: string  // '满足' | '不满足' | '待定'
  evidence: string
}

const checkItems = reactive<CheckItem[]>([
  { seq: 1, category: '知识产权', condition: '拥有核心自主知识产权', standard: '≥1项发明专利或≥6项实用新型/软著', actualValue: '', result: '待定', evidence: '' },
  { seq: 2, category: '知识产权', condition: '知识产权在有效期内', standard: '认定时处于有效期', actualValue: '', result: '待定', evidence: '' },
  { seq: 3, category: '知识产权', condition: '知识产权与主要产品技术相关', standard: '直接支撑核心技术', actualValue: '', result: '待定', evidence: '' },
  { seq: 4, category: '科技人员', condition: '科技人员占比', standard: '≥10%（累计工作≥183天）', actualValue: '', result: '待定', evidence: '' },
  { seq: 5, category: '研发费用', condition: '最近一年销售收入<5000万元', standard: '研发费占比≥5%', actualValue: '', result: '待定', evidence: '' },
  { seq: 6, category: '研发费用', condition: '最近一年销售收入5000万-2亿元', standard: '研发费占比≥4%', actualValue: '', result: '待定', evidence: '' },
  { seq: 7, category: '研发费用', condition: '最近一年销售收入>2亿元', standard: '研发费占比≥3%', actualValue: '', result: '待定', evidence: '' },
  { seq: 8, category: '研发费用', condition: '境内研发费用占比', standard: '≥60%', actualValue: '', result: '待定', evidence: '' },
  { seq: 9, category: '高新收入', condition: '高新技术产品(服务)收入占比', standard: '≥60%', actualValue: '', result: '待定', evidence: '' },
  { seq: 10, category: '技术领域', condition: '核心技术属于国家重点支持技术领域', standard: '8大领域之一', actualValue: '', result: '待定', evidence: '' },
  { seq: 11, category: '企业资质', condition: '注册成立一年以上', standard: '≥365天', actualValue: '', result: '待定', evidence: '' },
  { seq: 12, category: '企业资质', condition: '认定前未发生重大安全/质量/环境事故', standard: '近三年无重大事故', actualValue: '', result: '待定', evidence: '' },
  { seq: 13, category: '企业资质', condition: '认定前未发生严重偷税漏税行为', standard: '近三年无处罚', actualValue: '', result: '待定', evidence: '' },
  { seq: 14, category: '创新能力', condition: '研发组织管理水平', standard: '有完善的研发管理制度', actualValue: '', result: '待定', evidence: '' },
  { seq: 15, category: '创新能力', condition: '科技成果转化能力', standard: '年均≥5项', actualValue: '', result: '待定', evidence: '' },
  { seq: 16, category: '创新能力', condition: '成长性指标', standard: '净资产增长率/收入增长率', actualValue: '', result: '待定', evidence: '' },
  { seq: 17, category: '有效期', condition: '高新技术企业证书在有效期内', standard: '有效期3年', actualValue: '', result: '待定', evidence: '' },
  { seq: 18, category: '有效期', condition: '年度备案/年报已按时提交', standard: '按时提交', actualValue: '', result: '待定', evidence: '' },
])

const syncLoading = ref(false)
const auditNotes = ref('')
const auditConclusion = ref('')

// ─── 计算 ────────────────────────────────────────────────────────────────────

const overallPassed = computed(() => {
  return checkItems.every(item => item.result === '满足')
})

const passedCount = computed(() => checkItems.filter(i => i.result === '满足').length)
const failedCount = computed(() => checkItems.filter(i => i.result === '不满足').length)

const failedItems = computed(() => checkItems.filter(i => i.result === '不满足'))

function getCheckRowClass({ row }: { row: CheckItem }): string {
  if (row.result === '不满足') return 'failed-row'
  if (row.result === '满足') return 'passed-row'
  return ''
}

function getCategoryType(category: string): string {
  const map: Record<string, string> = {
    '知识产权': 'primary',
    '科技人员': 'success',
    '研发费用': 'warning',
    '高新收入': 'danger',
    '技术领域': 'info',
    '企业资质': '',
    '创新能力': 'primary',
    '有效期': 'info',
  }
  return map[category] || ''
}

// ─── 初始化 ──────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  const saved = formData.getField('6-2', 'check-items')
  if (saved && Array.isArray(saved)) {
    saved.forEach((item: any, i: number) => {
      if (i < checkItems.length) {
        checkItems[i].actualValue = item.actualValue || ''
        checkItems[i].result = item.result || '待定'
        checkItems[i].evidence = item.evidence || ''
      }
    })
  }
  auditNotes.value = formData.getField('6-2', 'audit-notes') ?? ''
  auditConclusion.value = formData.getField('6-2', 'audit-conclusion') ?? ''
})

// ─── 事件处理 ────────────────────────────────────────────────────────────────

async function handleCheckUpdate(index: number) {
  await formData.setField('6-2', 'check-items', checkItems.map(item => ({
    actualValue: item.actualValue,
    result: item.result,
    evidence: item.evidence,
  })))
}

async function handleSyncConclusion() {
  syncLoading.value = true
  try {
    await formData.setField('6', 'high-tech-approved', overallPassed.value)
    ElMessage.success(`认定结论已同步N5-6：${overallPassed.value ? '适用15%优惠税率' : '不适用优惠税率'}`)
  } catch { ElMessage.error('同步失败') }
  finally { syncLoading.value = false }
}

async function saveNotes() { await formData.setField('6-2', 'audit-notes', auditNotes.value) }
async function saveConclusion() { await formData.setField('6-2', 'audit-conclusion', auditConclusion.value) }
function handleAiAssist() { ElMessage.info('AI辅助分析高新认定条件...') }
function handleNotesAi() { ElMessage.info('AI辅助生成审计说明...') }
function handleReview() { openReviewDialog ? openReviewDialog('N5-6-2-高新认定') : ElMessage.info('复核对话未配置') }
</script>

<style scoped>
.n5-high-tech-check { padding: 12px; font-size: var(--wp-font-size, 13px); }
.methodology-context { padding: 12px 16px; margin-bottom: 16px; background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #d97706; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #92400e; line-height: 1.7; }
.methodology-context p { margin: 0; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 8px; }

.conclusion-banner { padding: 14px 20px; margin-bottom: 16px; border-radius: 8px; }
.conclusion-banner.pass { background: #e8f5e9; border: 1px solid #a5d6a7; }
.conclusion-banner.fail { background: #fef0f0; border: 1px solid #fab6b6; }
.cb-main { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.cb-icon { font-size: 20px; }
.cb-text { font-size: 14px; font-weight: 600; color: #303133; }
.cb-stats { display: flex; gap: 16px; font-size: 12px; }
.cb-stat.pass { color: #43a047; }
.cb-stat.fail { color: #f56c6c; font-weight: 600; }

.check-table { margin-bottom: 16px; }
:deep(.check-table .el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.failed-row) { background: #fef0f0 !important; }
:deep(.passed-row) { background: #f0f9eb !important; }
.condition-text { font-weight: 500; color: #303133; }
.standard-text { font-size: 12px; color: #606266; }
.cell-value { font-size: var(--wp-font-size, 13px); color: #606266; }
.result-badge { padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
.result-pass { background: #e8f5e9; color: #43a047; }
.result-fail { background: #fef0f0; color: #f56c6c; }
.result-pending { background: #f5f7fa; color: #909399; }

.failed-warnings { margin-bottom: 16px; }
.warning-title { font-weight: 600; }
.warning-list { margin: 8px 0 0; padding-left: 20px; line-height: 2; }
.warning-actual { color: #f56c6c; font-size: 12px; }

.action-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; padding: 10px 16px; background: #f0f9eb; border: 1px solid #c2e7b0; border-radius: 6px; }
.action-hint { font-size: 12px; color: #67c23a; }

.audit-notes-card { margin-bottom: 16px; }
.notes-header { display: flex; align-items: center; justify-content: space-between; font-size: 14px; font-weight: 500; }
.notes-field { margin-bottom: 12px; }
.notes-field:last-child { margin-bottom: 0; }
.field-label { display: block; font-size: var(--wp-font-size, 13px); font-weight: 500; color: #606266; margin-bottom: 6px; }

.n5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.n5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.n5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
