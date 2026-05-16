<template>
  <div class="gt-confirmation-ai-panel">
    <el-card class="panel-card">
      <template #header>
        <div class="panel-header">
          <span class="panel-title">📮 函证AI辅助</span>
          <el-radio-group v-model="currentTab" size="default">
            <el-radio-button value="address">地址核查</el-radio-button>
            <el-radio-button value="reply">回函OCR</el-radio-button>
            <el-radio-button value="discrepancy">差异分析</el-radio-button>
          </el-radio-group>
        </div>
      </template>

      <!-- 地址核查 -->
      <div v-if="currentTab === 'address'" class="tab-content">
        <div class="section-header">
          <h4>🏠 地址核查结果</h4>
          <el-button size="small" :loading="loading" @click="runAddressVerify" :icon="Refresh">
            {{ loading ? '核查中...' : '重新核查' }}
          </el-button>
        </div>

        <el-empty v-if="addressResults.length === 0" description="暂无地址核查数据" :image-size="80" />
        <el-table v-else :data="addressResults" stripe border size="small" max-height="400">
          <el-table-column prop="address" label="地址" min-width="200" show-overflow-tooltip />
          <el-table-column label="核查结果" width="100">
            <template #default="{ row }">
              <el-tag :type="resultTagType(row.result)" size="small">
                {{ resultLabel(row.result) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="风险等级" width="100">
            <template #default="{ row }">
              <el-tag :type="riskTagType(row.riskLevel)" size="small">
                {{ riskLabel(row.riskLevel) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="确认状态" width="140">
            <template #default>
              <el-tag type="info" effect="plain">AI辅助-待人工确认</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <el-button type="success" size="small" plain @click="confirmItem(row)" :icon="Check">
                确认
              </el-button>
              <el-button type="danger" size="small" plain @click="rejectItem(row)" :icon="Close">
                拒绝
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 回函OCR -->
      <div v-if="currentTab === 'reply'" class="tab-content">
        <div class="section-header">
          <h4>📄 回函OCR识别结果</h4>
          <el-button size="small" type="primary" @click="triggerUpload" :icon="Upload">
            上传回函扫描件
          </el-button>
          <input ref="fileInputRef" type="file" accept="image/*,.pdf" @change="handleUpload" style="display:none" />
        </div>

        <el-empty
          v-if="replyResults.length === 0"
          description="暂无回函识别数据，请上传回函扫描件"
          :image-size="80"
        />

        <div v-else class="reply-results">
          <el-card v-for="(reply, idx) in replyResults" :key="idx" class="reply-card" shadow="hover">
            <template #header>
              <div class="reply-header">
                <span class="reply-unit">{{ reply.unitName || reply.extractedUnit || '未知单位' }}</span>
                <el-tag type="info" effect="plain">AI辅助-待人工确认</el-tag>
              </div>
            </template>

            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="回函单位名称">
                <span>{{ reply.extractedUnit || '-' }}</span>
                <el-tag v-if="reply.unitMismatch" type="danger" size="small" style="margin-left: 8px">
                  ⚠️ 不一致
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="确认金额">
                <span class="amount-value">{{ formatCurrency(reply.confirmedAmount) }}</span>
                <el-tag v-if="reply.amountMismatch" type="warning" size="small" style="margin-left: 8px">
                  ⚠️ 与账面 {{ formatCurrency(reply.bookAmount) }} 不匹配
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="签章检测">
                <el-tag :type="reply.hasSeal ? 'success' : 'warning'" size="small">
                  {{ reply.hasSeal ? '✅ 检测到印章' : '⚠️ 未检测到印章' }}
                </el-tag>
                <el-tag v-if="reply.sealMismatch" type="danger" size="small" style="margin-left: 8px">
                  ⚠️ 印章名称不一致
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="回函日期">
                <span>{{ reply.replyDate || '-' }}</span>
              </el-descriptions-item>
            </el-descriptions>

            <div class="reply-actions">
              <el-button type="success" size="small" plain @click="confirmReply(reply)" :icon="Check">
                确认
              </el-button>
              <el-button type="danger" size="small" plain @click="rejectReply(reply)" :icon="Close">
                拒绝
              </el-button>
            </div>
          </el-card>
        </div>
      </div>

      <!-- 差异分析 -->
      <div v-if="currentTab === 'discrepancy'" class="tab-content">
        <div class="section-header">
          <h4>📊 不符差异分析</h4>
          <el-button size="small" :loading="loading" @click="runMismatchAnalysis" :icon="Refresh">
            {{ loading ? '分析中...' : '重新分析' }}
          </el-button>
        </div>

        <el-empty v-if="discrepancies.length === 0" description="暂无不符差异数据" :image-size="80" />
        <el-table v-else :data="discrepancies" stripe border size="small" max-height="400">
          <el-table-column prop="item" label="函证项目" min-width="150" show-overflow-tooltip />
          <el-table-column label="账面金额" width="130" align="right">
            <template #default="{ row }">
              {{ formatCurrency(row.bookAmount) }}
            </template>
          </el-table-column>
          <el-table-column label="确认金额" width="130" align="right">
            <template #default="{ row }">
              {{ formatCurrency(row.confirmedAmount) }}
            </template>
          </el-table-column>
          <el-table-column label="差异" width="130" align="right">
            <template #default="{ row }">
              <span :class="row.difference < 0 ? 'negative' : ''">
                {{ formatCurrency(row.difference) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="suggestedReason" label="可能原因" min-width="200" show-overflow-tooltip />
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button type="success" size="small" plain @click="acceptReason(row)" :icon="Check">
                采纳
              </el-button>
              <el-button size="small" plain @click="editReason(row)" :icon="Edit">
                编辑
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  Refresh, Upload, Check, Close, Edit
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { confirmationAI } from '@/services/aiApi'
import type { ConfirmationAIResult } from '@/services/aiApi'

interface AddressResult extends ConfirmationAIResult {
  address: string
  result: 'verified' | 'mismatch' | 'suspicious'
  riskLevel: 'high' | 'medium' | 'low' | 'pass'
}

interface ReplyResult {
  unitName?: string
  confirmationId?: string
  extractedUnit?: string
  confirmedAmount?: number
  bookAmount?: number
  unitMismatch?: boolean
  amountMismatch?: boolean
  hasSeal?: boolean
  sealMismatch?: boolean
  replyDate?: string
  status?: string
}

interface Discrepancy {
  item: string
  bookAmount: number
  confirmedAmount: number
  difference: number
  suggestedReason: string
  accepted?: boolean
}

const props = defineProps<{
  projectId: string
  confirmationId?: string
}>()

const currentTab = ref<'address' | 'reply' | 'discrepancy'>('address')
const loading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

// 地址核查结果
const addressResults = ref<AddressResult[]>([])

// 回函OCR结果
const replyResults = ref<ReplyResult[]>([])

// 差异分析
const discrepancies = ref<Discrepancy[]>([])

function resultLabel(result: string): string {
  const map: Record<string, string> = {
    verified: '已核实',
    mismatch: '不一致',
    suspicious: '可疑',
  }
  return map[result] || result
}

function riskLabel(level: string): string {
  const map: Record<string, string> = {
    high: '高风险',
    medium: '中风险',
    low: '低风险',
    pass: '通过',
  }
  return map[level] || level
}

function resultTagType(result: string): 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    verified: 'success',
    mismatch: 'warning',
    suspicious: 'danger',
  }
  return map[result] || 'info'
}

function riskTagType(level: string): 'danger' | 'warning' | 'success' | 'info' {
  const map: Record<string, 'danger' | 'warning' | 'success' | 'info'> = {
    high: 'danger',
    medium: 'warning',
    low: 'success',
    pass: 'success',
  }
  return map[level] || 'info'
}

function formatCurrency(val: number | undefined | null): string {
  if (val == null) return '-'
  return Number(val).toLocaleString('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2,
  })
}

async function runAddressVerify() {
  loading.value = true
  try {
    // 调用 API: POST /api/projects/{id}/confirmations/ai/address-verify
    const result = await confirmationAI.verifyAddresses(props.projectId)
    addressResults.value = (result.data || []) as any
    ElMessage.success('地址核查完成')
  } catch (e) {
    console.error('Address verification failed:', e)
    // 模拟数据
    addressResults.value = [
      {
        id: '1',
        check_type: 'address_verify',
        check_result: { address: '北京市朝阳区建国路88号SOHO现代城A座1201' },
        risk_level: 'low',
        human_confirmed: false,
        confirmed_by: null,
        confirmed_at: null,
        address: '北京市朝阳区建国路88号SOHO现代城A座1201',
        result: 'verified',
        riskLevel: 'low',
      },
      {
        id: '2',
        check_type: 'address_verify',
        check_result: { address: '上海市浦东新区世纪大道100号' },
        risk_level: 'high',
        human_confirmed: false,
        confirmed_by: null,
        confirmed_at: null,
        address: '上海市浦东新区世纪大道100号',
        result: 'mismatch',
        riskLevel: 'high',
      },
      {
        id: '3',
        check_type: 'address_verify',
        check_result: { address: '深圳市南山区科技园南区高新南七道R2-B栋5楼' },
        risk_level: 'medium',
        human_confirmed: false,
        confirmed_by: null,
        confirmed_at: null,
        address: '深圳市南山区科技园南区高新南七道R2-B栋5楼',
        result: 'suspicious',
        riskLevel: 'medium',
      },
    ]
    ElMessage.warning('API 不可用，使用模拟数据')
  } finally {
    loading.value = false
  }
}

async function confirmItem(item: AddressResult) {
  try {
    // 调用 API: PUT /api/projects/{id}/confirmations/ai/checks/{chk}/confirm
    await confirmationAI.confirmCheck(props.projectId, item.id, 'accept')
    item.human_confirmed = true
    item.confirmed_by = 'current_user'
    item.confirmed_at = new Date().toISOString()
    ElMessage.success('已确认')
  } catch (e) {
    console.error(e)
    ElMessage.warning('API 不可用，仅本地标记')
    item.human_confirmed = true
  }
}

async function rejectItem(item: AddressResult) {
  try {
    await confirmationAI.confirmCheck(props.projectId, item.id, 'reject')
    ElMessage.info('已拒绝')
  } catch (e) {
    console.error(e)
    ElMessage.warning('API 不可用，仅本地标记')
  }
}

function triggerUpload() {
  fileInputRef.value?.click()
}

async function handleUpload(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  if (files.length === 0) return

  const file = files[0]
  loading.value = true
  try {
    // 如果有 confirmationId，使用该 ID，否则使用项目 ID
    const confId = props.confirmationId || 'new'
    // 调用 API: POST /api/projects/{id}/confirmations/{cid}/ai/ocr-reply
    const result = await confirmationAI.ocrReply(props.projectId, confId, file)
    if (result.data) {
      replyResults.value.push(result.data)
    }
    ElMessage.success('回函识别完成')
  } catch (e) {
    console.error(e)
    // 模拟数据
    replyResults.value.push({
      unitName: '供应商A公司',
      extractedUnit: 'A公司',
      confirmedAmount: 1000000,
      bookAmount: 980000,
      amountMismatch: true,
      hasSeal: true,
      sealMismatch: false,
      replyDate: '2024-03-15',
    })
    ElMessage.warning('API 不可用，使用模拟数据')
  } finally {
    loading.value = false
    input.value = ''
  }
}

function confirmReply(reply: ReplyResult) {
  reply.status = 'confirmed'
  ElMessage.success('已确认')
}

function rejectReply(reply: ReplyResult) {
  reply.status = 'rejected'
  ElMessage.info('已拒绝')
}

async function runMismatchAnalysis() {
  loading.value = true
  try {
    // 调用 API: POST /api/projects/{id}/confirmations/ai/mismatch-analysis
    const result = await confirmationAI.analyzeMismatch(props.projectId, props.confirmationId)
    discrepancies.value = result.data || []
    ElMessage.success('差异分析完成')
  } catch (e) {
    console.error(e)
    // 模拟数据
    discrepancies.value = [
      {
        item: '应收账款 - 客户A',
        bookAmount: 1000000,
        confirmedAmount: 980000,
        difference: -20000,
        suggestedReason: '可能存在在途款项，需核对期后银行水单',
      },
      {
        item: '应付账款 - 供应商B',
        bookAmount: 500000,
        confirmedAmount: 500000,
        difference: 0,
        suggestedReason: '金额一致，无差异',
      },
    ]
    ElMessage.warning('API 不可用，使用模拟数据')
  } finally {
    loading.value = false
  }
}

function acceptReason(d: Discrepancy) {
  d.accepted = true
  ElMessage.success('已采纳该原因')
}

async function editReason(d: Discrepancy) {
  try {
    const { value: newReason } = await ElMessageBox.prompt(
      '请输入差异原因',
      '编辑原因',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputValue: d.suggestedReason,
      }
    )
    if (newReason) {
      d.suggestedReason = newReason
      ElMessage.success('原因已更新')
    }
  } catch {
    // 用户取消
  }
}

// 初始化加载
onMounted(async () => {
  try {
    // 调用 API: GET /api/projects/{id}/confirmations/ai/checks
    const result = await confirmationAI.getChecks(props.projectId)
    addressResults.value = (result.data || []) as any
  } catch (e) {
    console.error('Failed to load checks:', e)
    // 不显示错误，让用户手动点击加载
  }
})
</script>

<style scoped>
.gt-confirmation-ai-panel {
  padding: 16px;
}

.panel-card {
  border-radius: 8px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.panel-title {
  font-size: var(--gt-font-size-md);
  font-weight: 600;
}

.tab-content {
  margin-top: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  gap: 12px;
}

.section-header h4 {
  margin: 0;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-regular);
}

.reply-results {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.reply-card {
  border-radius: 8px;
}

.reply-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.reply-unit {
  font-weight: 600;
  font-size: var(--gt-font-size-sm);
}

.reply-actions {
  margin-top: 16px;
  display: flex;
  gap: 12px;
}

.amount-value {
  font-weight: 600;
  color: var(--gt-color-text-primary);
}

.negative {
  color: var(--gt-color-coral);
  font-weight: 600;
}
</style>
</script>

<style scoped>
.gt-confirmation-ai-panel {
  padding: 16px;
}

.panel-card {
  border-radius: 8px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.panel-title {
  font-size: var(--gt-font-size-md);
  font-weight: 600;
}

.tab-content {
  margin-top: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  gap: 12px;
}

.section-header h4 {
  margin: 0;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-regular);
}

.reply-results {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.reply-card {
  border-radius: 8px;
}

.reply-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.reply-unit {
  font-weight: 600;
  font-size: var(--gt-font-size-sm);
}

.reply-actions {
  margin-top: 16px;
  display: flex;
  gap: 12px;
}

.amount-value {
  font-weight: 600;
  color: var(--gt-color-text-primary);
}

.negative {
  color: var(--gt-color-coral);
  font-weight: 600;
}
</style>
