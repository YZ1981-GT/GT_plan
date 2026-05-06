<template>
  <div class="qc-inspection-workbench">
    <!-- 顶部横幅 -->
    <div class="gt-page-banner">
      <div class="gt-banner-content">
        <h2>🔍 质控抽查工作台</h2>
        <span class="gt-banner-sub">
          共 {{ inspections.length }} 个抽查批次
        </span>
      </div>
    </div>

    <!-- Tab 切换 -->
    <el-tabs v-model="activeTab" class="workbench-tabs">
      <el-tab-pane label="底稿抽查" name="workpaper">
        <!-- 三栏布局（原有内容） -->
        <div class="workbench-body">
          <!-- 左栏：抽查批次列表 -->
          <div class="batch-panel">
            <div class="panel-header">
              <span>抽查批次</span>
              <el-badge :value="inspections.length" type="primary" />
            </div>
            <div class="batch-list" v-loading="loadingBatches">
              <div
                v-for="batch in inspections"
                :key="batch.id"
                class="batch-item"
                :class="{ active: selectedBatchId === batch.id }"
                @click="selectBatch(batch)"
              >
                <div class="batch-item-header">
                  <el-tag size="small" :type="strategyTagType(batch.strategy)">
                    {{ strategyLabel(batch.strategy) }}
                  </el-tag>
                  <el-tag size="small" :type="statusTagType(batch.status)">
                    {{ statusLabel(batch.status) }}
                  </el-tag>
                </div>
                <div class="batch-item-project">{{ batch.project_name || '未知项目' }}</div>
                <div class="batch-item-meta">
                  <span>{{ formatDate(batch.created_at) }}</span>
                  <span v-if="batch.item_count != null">{{ batch.item_count }} 项</span>
                </div>
              </div>
              <el-empty v-if="!loadingBatches && !inspections.length" description="暂无抽查批次" />
            </div>
          </div>

          <!-- 中栏：底稿队列 -->
          <div class="queue-panel">
            <div class="panel-header">
              <span>底稿队列</span>
              <el-badge v-if="currentItems.length" :value="currentItems.length" type="warning" />
            </div>
            <div class="queue-list" v-loading="loadingItems">
              <template v-if="selectedBatchId">
                <div
                  v-for="item in currentItems"
                  :key="item.id"
                  class="queue-item"
                  :class="{ active: selectedItemId === item.id }"
                  @click="selectItem(item)"
                >
                  <div class="queue-item-header">
                    <span class="wp-code">{{ item.wp_code }}</span>
                    <el-tag size="small" :type="itemStatusTagType(item.status)">
                      {{ itemStatusLabel(item.status) }}
                    </el-tag>
                  </div>
                  <div class="queue-item-verdict" v-if="item.qc_verdict">
                    <el-tag size="small" :type="verdictTagType(item.qc_verdict)">
                      {{ verdictLabel(item.qc_verdict) }}
                    </el-tag>
                  </div>
                  <div class="wp-name" v-if="item.wp_name">{{ item.wp_name }}</div>
                  <div class="wp-meta" v-if="item.audit_cycle">
                    <span>{{ item.audit_cycle }}</span>
                  </div>
                </div>
                <el-empty v-if="!loadingItems && !currentItems.length" description="该批次无底稿" />
              </template>
              <el-empty v-else description="请从左侧选择批次" />
            </div>

            <!-- 生成报告按钮 -->
            <div class="report-action" v-if="allItemsCompleted && selectedBatchId">
              <el-button
                type="primary"
                :loading="generatingReport"
                @click="handleGenerateReport"
              >
                📄 生成质控报告
              </el-button>
            </div>
          </div>

          <!-- 右栏：复核表单 -->
          <div class="review-panel">
            <template v-if="selectedItem">
              <div class="panel-header">
                <span>复核表单</span>
                <span class="wp-code-label">{{ selectedItem.wp_code }}</span>
              </div>

              <!-- 底稿信息 -->
              <div class="review-meta">
                <div class="meta-row">
                  <label>底稿编号：</label>
                  <span>{{ selectedItem.wp_code }}</span>
                </div>
                <div class="meta-row" v-if="selectedItem.wp_name">
                  <label>底稿名称：</label>
                  <span>{{ selectedItem.wp_name }}</span>
                </div>
                <div class="meta-row" v-if="selectedItem.audit_cycle">
                  <label>审计循环：</label>
                  <span>{{ selectedItem.audit_cycle }}</span>
                </div>
                <div class="meta-row">
                  <label>当前状态：</label>
                  <el-tag size="small" :type="itemStatusTagType(selectedItem.status)">
                    {{ itemStatusLabel(selectedItem.status) }}
                  </el-tag>
                </div>
              </div>

              <el-divider />

              <!-- 结论选择 -->
              <div class="verdict-section">
                <label class="form-label">质控结论</label>
                <el-radio-group v-model="verdictForm.verdict" :disabled="selectedItem.status === 'completed'">
                  <el-radio value="pass">通过</el-radio>
                  <el-radio value="conditional_pass">有条件通过</el-radio>
                  <el-radio value="fail">不通过</el-radio>
                </el-radio-group>
              </div>

              <!-- 发现问题 -->
              <div class="findings-section">
                <label class="form-label">发现问题与意见</label>
                <el-input
                  v-model="verdictForm.findings"
                  type="textarea"
                  :rows="6"
                  placeholder="请输入质控发现的问题、意见或建议..."
                  :disabled="selectedItem.status === 'completed'"
                />
              </div>

              <!-- 提交按钮 -->
              <div class="submit-section">
                <el-button
                  type="primary"
                  :disabled="!verdictForm.verdict || selectedItem.status === 'completed'"
                  :loading="submitting"
                  @click="handleSubmitVerdict"
                >
                  提交结论
                </el-button>
                <span v-if="selectedItem.status === 'completed'" class="completed-hint">
                  ✅ 已完成
                </span>
              </div>

              <!-- 发布为案例入口 -->
              <div class="publish-case-section" v-if="selectedItem.status === 'completed' && selectedItem.qc_verdict === 'fail'">
                <el-divider />
                <el-button type="warning" plain @click="openPublishCaseDialog">
                  📚 发布为案例
                </el-button>
              </div>
            </template>
            <el-empty v-else description="请从中栏选择底稿" />
          </div>
        </div>
      </el-tab-pane>

      <!-- 日志合规抽查 Tab -->
      <el-tab-pane label="日志合规抽查" name="audit_log">
        <div class="audit-log-tab">
          <!-- 操作栏 -->
          <div class="audit-log-toolbar">
            <el-button
              type="primary"
              :loading="runningCompliance"
              @click="handleRunCompliance"
            >
              🔄 执行日志合规检查
            </el-button>
            <el-select
              v-model="logFilterStatus"
              placeholder="筛选状态"
              clearable
              style="width: 140px; margin-left: 12px"
              @change="loadAuditLogFindings"
            >
              <el-option label="全部" value="" />
              <el-option label="待审查" value="pending" />
              <el-option label="已审查" value="reviewed" />
              <el-option label="需上报" value="escalated" />
            </el-select>
            <span class="toolbar-summary" v-if="auditLogFindings.length">
              共 {{ auditLogTotal }} 条命中
            </span>
          </div>

          <!-- 命中条目表格 -->
          <el-table
            :data="auditLogFindings"
            v-loading="loadingAuditLog"
            stripe
            border
            style="width: 100%"
            class="audit-log-table"
          >
            <el-table-column prop="ts" label="时间" width="170">
              <template #default="{ row }">
                {{ formatDateTime(row.ts) }}
              </template>
            </el-table-column>
            <el-table-column prop="action_type" label="操作类型" width="180" />
            <el-table-column prop="user_name" label="用户" width="120">
              <template #default="{ row }">
                {{ row.user_name || row.user_id || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="ip" label="IP 地址" width="140">
              <template #default="{ row }">
                {{ row.ip || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="rule_code" label="触发规则" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="severityTagType(row.severity)">
                  {{ row.rule_code }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="severity" label="严重程度" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="severityTagType(row.severity)">
                  {{ severityLabel(row.severity) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="message" label="说明" min-width="200" show-overflow-tooltip />
            <el-table-column label="审查状态" width="140" fixed="right">
              <template #default="{ row }">
                <el-dropdown
                  trigger="click"
                  @command="(cmd) => handleStatusChange(row, cmd)"
                  :disabled="row.review_status !== 'pending'"
                >
                  <el-tag
                    :type="reviewStatusTagType(row.review_status)"
                    class="status-tag-clickable"
                    :class="{ 'is-clickable': row.review_status === 'pending' }"
                  >
                    {{ reviewStatusLabel(row.review_status) }}
                    <el-icon v-if="row.review_status === 'pending'" class="el-icon--right">
                      <arrow-down />
                    </el-icon>
                  </el-tag>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="reviewed">✅ 已审查</el-dropdown-item>
                      <el-dropdown-item command="escalated">🚨 需上报</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </el-table-column>
          </el-table>

          <el-empty
            v-if="!loadingAuditLog && !auditLogFindings.length"
            description="暂无日志合规命中条目，请点击「执行日志合规检查」按钮"
          />
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 发布为案例对话框 -->
    <el-dialog
      v-model="publishCaseVisible"
      title="发布为案例"
      width="520px"
      destroy-on-close
    >
      <el-form :model="publishCaseForm" label-width="80px">
        <el-form-item label="标题" required>
          <el-input v-model="publishCaseForm.title" placeholder="请输入案例标题" />
        </el-form-item>
        <el-form-item label="分类" required>
          <el-select v-model="publishCaseForm.category" placeholder="选择分类" style="width: 100%">
            <el-option label="底稿质量" value="workpaper_quality" />
            <el-option label="程序执行" value="procedure_execution" />
            <el-option label="判断偏差" value="judgment_bias" />
            <el-option label="披露遗漏" value="disclosure_omission" />
            <el-option label="合规问题" value="compliance" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="严重程度" required>
          <el-select v-model="publishCaseForm.severity" placeholder="选择严重程度" style="width: 100%">
            <el-option label="阻断" value="blocking" />
            <el-option label="警告" value="warning" />
            <el-option label="提示" value="info" />
          </el-select>
        </el-form-item>
        <el-form-item label="经验教训">
          <el-input
            v-model="publishCaseForm.lessons_learned"
            type="textarea"
            :rows="4"
            placeholder="请输入经验教训与改进建议..."
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="publishCaseVisible = false">取消</el-button>
        <el-button type="primary" :loading="publishingCase" @click="handlePublishCase">
          确认发布
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import {
  getInspections,
  getInspectionDetail,
  submitVerdict,
  generateReport,
  type QcInspection,
  type QcInspectionItem,
  type VerdictPayload,
} from '@/services/qcInspectionApi'
import { publishAsCase, type PublishAsCasePayload } from '@/services/qcCaseApi'
import {
  getAuditLogFindings,
  runAuditLogCompliance,
  updateFindingStatus,
  type AuditLogFinding,
} from '@/services/qcAuditLogComplianceApi'

// ── Tab 状态 ──

const activeTab = ref('workpaper')

// ── 底稿抽查状态 ──

const loadingBatches = ref(false)
const loadingItems = ref(false)
const submitting = ref(false)
const generatingReport = ref(false)

const inspections = ref<QcInspection[]>([])
const selectedBatchId = ref<string>('')
const currentItems = ref<QcInspectionItem[]>([])
const selectedItemId = ref<string>('')

const verdictForm = ref<VerdictPayload>({
  verdict: '' as any,
  findings: '',
})

// ── 日志合规抽查状态 ──

const loadingAuditLog = ref(false)
const runningCompliance = ref(false)
const auditLogFindings = ref<AuditLogFinding[]>([])
const auditLogTotal = ref(0)
const logFilterStatus = ref('')

// ── 计算属性 ──

const selectedItem = computed<QcInspectionItem | null>(
  () => currentItems.value.find((i) => i.id === selectedItemId.value) ?? null,
)

const allItemsCompleted = computed(() => {
  if (!currentItems.value.length) return false
  return currentItems.value.every((i) => i.status === 'completed')
})

// ── 底稿抽查数据加载 ──

async function loadBatches() {
  loadingBatches.value = true
  try {
    const res = await getInspections()
    inspections.value = res.items
  } catch (e: any) {
    ElMessage.error('加载抽查批次失败: ' + (e.message || '未知错误'))
  } finally {
    loadingBatches.value = false
  }
}

async function selectBatch(batch: QcInspection) {
  selectedBatchId.value = batch.id
  selectedItemId.value = ''
  verdictForm.value = { verdict: '' as any, findings: '' }
  loadingItems.value = true
  try {
    const detail = await getInspectionDetail(batch.id)
    currentItems.value = detail.items || []
  } catch (e: any) {
    ElMessage.error('加载批次详情失败: ' + (e.message || '未知错误'))
    currentItems.value = []
  } finally {
    loadingItems.value = false
  }
}

function selectItem(item: QcInspectionItem) {
  selectedItemId.value = item.id
  if (item.qc_verdict) {
    verdictForm.value = {
      verdict: item.qc_verdict,
      findings: (item.findings as any)?.text || '',
    }
  } else {
    verdictForm.value = { verdict: '' as any, findings: '' }
  }
}

// ── 提交结论 ──

async function handleSubmitVerdict() {
  if (!selectedBatchId.value || !selectedItemId.value) return
  if (!verdictForm.value.verdict) {
    ElMessage.warning('请选择质控结论')
    return
  }
  submitting.value = true
  try {
    const updated = await submitVerdict(
      selectedBatchId.value,
      selectedItemId.value,
      verdictForm.value,
    )
    const idx = currentItems.value.findIndex((i) => i.id === selectedItemId.value)
    if (idx >= 0) {
      currentItems.value[idx] = { ...currentItems.value[idx], ...updated }
    }
    ElMessage.success('结论已提交')
    selectNextPending()
  } catch (e: any) {
    ElMessage.error('提交失败: ' + (e.message || '未知错误'))
  } finally {
    submitting.value = false
  }
}

function selectNextPending() {
  const pending = currentItems.value.find(
    (i) => i.status !== 'completed' && i.id !== selectedItemId.value,
  )
  if (pending) {
    selectItem(pending)
  }
}

// ── 生成报告 ──

async function handleGenerateReport() {
  if (!selectedBatchId.value) return
  generatingReport.value = true
  try {
    const result = await generateReport(selectedBatchId.value)
    if (result.status === 'completed' && result.report_url) {
      ElMessage.success('质控报告已生成')
      const batch = inspections.value.find((b) => b.id === selectedBatchId.value)
      if (batch) batch.report_url = result.report_url
    } else {
      ElMessage.info('报告生成任务已提交，请稍后刷新查看')
    }
  } catch (e: any) {
    ElMessage.error('生成报告失败: ' + (e.message || '未知错误'))
  } finally {
    generatingReport.value = false
  }
}

// ── 发布为案例 ──

const publishCaseVisible = ref(false)
const publishingCase = ref(false)
const publishCaseForm = ref<PublishAsCasePayload>({
  title: '',
  category: '',
  severity: '',
  lessons_learned: '',
})

function openPublishCaseDialog() {
  publishCaseForm.value = {
    title: selectedItem.value?.wp_code ? `案例：${selectedItem.value.wp_code}` : '',
    category: '',
    severity: 'warning',
    lessons_learned: '',
  }
  publishCaseVisible.value = true
}

async function handlePublishCase() {
  if (!publishCaseForm.value.title || !publishCaseForm.value.category || !publishCaseForm.value.severity) {
    ElMessage.warning('请填写标题、分类和严重程度')
    return
  }
  if (!selectedBatchId.value || !selectedItemId.value) return
  publishingCase.value = true
  try {
    await publishAsCase(selectedBatchId.value, selectedItemId.value, publishCaseForm.value)
    ElMessage.success('案例已发布到案例库')
    publishCaseVisible.value = false
  } catch (e: any) {
    ElMessage.error('发布案例失败: ' + (e.message || '未知错误'))
  } finally {
    publishingCase.value = false
  }
}

// ── 日志合规抽查 ──

async function loadAuditLogFindings() {
  loadingAuditLog.value = true
  try {
    const res = await getAuditLogFindings({
      status: logFilterStatus.value || undefined,
    })
    auditLogFindings.value = res.items
    auditLogTotal.value = res.total
  } catch (e: any) {
    ElMessage.error('加载日志合规数据失败: ' + (e.message || '未知错误'))
  } finally {
    loadingAuditLog.value = false
  }
}

async function handleRunCompliance() {
  runningCompliance.value = true
  try {
    const result = await runAuditLogCompliance({
      time_window_hours: 720, // 30 天
    })
    ElMessage.success(`${result.message}，新增 ${result.findings_count} 条命中`)
    await loadAuditLogFindings()
  } catch (e: any) {
    ElMessage.error('执行日志合规检查失败: ' + (e.message || '未知错误'))
  } finally {
    runningCompliance.value = false
  }
}

async function handleStatusChange(row: AuditLogFinding, status: string) {
  try {
    const updated = await updateFindingStatus(row.id, status as 'reviewed' | 'escalated')
    // 更新本地状态
    const idx = auditLogFindings.value.findIndex((f) => f.id === row.id)
    if (idx >= 0) {
      auditLogFindings.value[idx] = { ...auditLogFindings.value[idx], ...updated }
    }
    const label = status === 'reviewed' ? '已审查' : '需上报'
    ElMessage.success(`已标记为"${label}"`)
  } catch (e: any) {
    ElMessage.error('更新状态失败: ' + (e.message || '未知错误'))
  }
}

// ── 辅助函数（底稿抽查） ──

function strategyLabel(s: string): string {
  const map: Record<string, string> = {
    random: '随机抽样',
    risk_based: '风险导向',
    full_cycle: '全循环',
    mixed: '混合策略',
  }
  return map[s] || s
}

function strategyTagType(s: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'primary'> = {
    random: 'info',
    risk_based: 'warning',
    full_cycle: 'danger',
    mixed: 'primary',
  }
  return map[s] || 'info'
}

function statusLabel(s: string): string {
  const map: Record<string, string> = {
    pending: '待开始',
    in_progress: '进行中',
    completed: '已完成',
  }
  return map[s] || s
}

function statusTagType(s: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'primary'> = {
    pending: 'info',
    in_progress: 'warning',
    completed: 'success',
  }
  return map[s] || 'info'
}

function itemStatusLabel(s: string): string {
  const map: Record<string, string> = {
    pending: '待复核',
    in_progress: '复核中',
    completed: '已完成',
  }
  return map[s] || s
}

function itemStatusTagType(s: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'primary'> = {
    pending: 'warning',
    in_progress: 'primary',
    completed: 'success',
  }
  return map[s] || 'info'
}

function verdictLabel(v: string): string {
  const map: Record<string, string> = {
    pass: '通过',
    conditional_pass: '有条件通过',
    fail: '不通过',
  }
  return map[v] || v
}

function verdictTagType(v: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'primary'> = {
    pass: 'success',
    conditional_pass: 'warning',
    fail: 'danger',
  }
  return map[v] || 'info'
}

// ── 辅助函数（日志合规） ──

function severityLabel(s: string): string {
  const map: Record<string, string> = {
    blocking: '阻断',
    warning: '警告',
    info: '提示',
  }
  return map[s] || s
}

function severityTagType(s: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'primary'> = {
    blocking: 'danger',
    warning: 'warning',
    info: 'info',
  }
  return map[s] || 'info'
}

function reviewStatusLabel(s: string): string {
  const map: Record<string, string> = {
    pending: '待审查',
    reviewed: '已审查',
    escalated: '需上报',
  }
  return map[s] || s
}

function reviewStatusTagType(s: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'primary'> = {
    pending: 'warning',
    reviewed: 'success',
    escalated: 'danger',
  }
  return map[s] || 'info'
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleDateString('zh-CN')
}

function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

// ── 生命周期 ──

onMounted(() => {
  loadBatches()
  // 预加载日志合规数据
  loadAuditLogFindings()
})
</script>

<style scoped>
.qc-inspection-workbench {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0;
}

.workbench-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0 12px;
  min-height: 0;
}

.workbench-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.workbench-tabs :deep(.el-tab-pane) {
  height: 100%;
  overflow: hidden;
}

.workbench-body {
  display: flex;
  flex: 1;
  min-height: 0;
  padding: 12px 0;
  gap: 12px;
  height: 100%;
}

/* 左栏：批次列表 */
.batch-panel {
  width: 280px;
  flex-shrink: 0;
  border-right: 1px solid var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
  padding-right: 12px;
  min-height: 0;
}

.batch-list {
  flex: 1;
  overflow-y: auto;
}

.batch-item {
  padding: 10px;
  cursor: pointer;
  border-radius: 6px;
  margin-bottom: 6px;
  border: 1px solid transparent;
  transition: all 0.15s ease;
}
.batch-item:hover {
  background: var(--el-fill-color-light);
}
.batch-item.active {
  background: var(--gt-primary-lighter, #f0ebf8);
  border-color: var(--gt-color-primary, #6e3fd4);
}
.batch-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.batch-item-project {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.batch-item-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

/* 中栏：底稿队列 */
.queue-panel {
  width: 300px;
  flex-shrink: 0;
  border-right: 1px solid var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
  padding: 0 12px;
  min-height: 0;
}

.queue-list {
  flex: 1;
  overflow-y: auto;
}

.queue-item {
  padding: 10px;
  cursor: pointer;
  border-radius: 6px;
  margin-bottom: 6px;
  border: 1px solid transparent;
  transition: all 0.15s ease;
}
.queue-item:hover {
  background: var(--el-fill-color-light);
}
.queue-item.active {
  background: var(--gt-primary-lighter, #f0ebf8);
  border-color: var(--gt-color-primary, #6e3fd4);
}
.queue-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.queue-item-verdict {
  margin-bottom: 4px;
}
.wp-code {
  font-weight: 600;
  font-size: 13px;
}
.wp-name {
  font-size: 12px;
  color: var(--el-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 4px;
}
.wp-meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.report-action {
  padding: 12px 0;
  border-top: 1px solid var(--el-border-color-lighter);
  text-align: center;
}

/* 右栏：复核表单 */
.review-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding-left: 12px;
  overflow-y: auto;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.wp-code-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: normal;
}

.review-meta {
  margin: 8px 0 12px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
}
.meta-row {
  display: flex;
  gap: 8px;
  font-size: 13px;
  margin-bottom: 6px;
  align-items: center;
}
.meta-row:last-child {
  margin-bottom: 0;
}
.meta-row label {
  min-width: 80px;
  color: var(--el-text-color-secondary);
}

.verdict-section {
  margin-bottom: 16px;
}

.findings-section {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 8px;
  color: var(--el-text-color-primary);
}

.submit-section {
  display: flex;
  align-items: center;
  gap: 12px;
}

.completed-hint {
  font-size: 13px;
  color: var(--el-color-success);
}

.publish-case-section {
  margin-top: 4px;
}

/* 日志合规抽查 Tab */
.audit-log-tab {
  padding: 12px 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.audit-log-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.toolbar-summary {
  margin-left: 16px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.audit-log-table {
  flex: 1;
  min-height: 0;
}

.status-tag-clickable {
  cursor: default;
}
.status-tag-clickable.is-clickable {
  cursor: pointer;
}
</style>
