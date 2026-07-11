<script setup lang="ts">
/**
 * D4TabInterviewTemplate — 访谈记录与核对示例（走访模板）
 *
 * QA卡片结构：
 * - 走访公司基本信息区（工商信息 + 经营场所 + 人员规模）
 * - 交易核实区（交易金额/品种/定价/回款确认）
 * - 现场观察区（经营场地/库存/生产能力）
 * - 结论区
 * - "新建走访记录"按钮
 * - AI预填 disabled按钮
 *
 * Requirements: 30.1-30.4
 */
import { ref, computed, toRef, inject, type Ref } from 'vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── Types ────────────────────────────────────────────────────────────
interface InterviewRecord {
  id: string
  companyName: string
  visitDate: string
  // 基本信息区
  bizLicense: string
  registeredAddress: string
  operatingAddress: string
  legalPerson: string
  registeredCapital: string
  staffCount: string
  mainBusiness: string
  // 交易核实区
  transactionAmount: string
  productCategory: string
  pricingMethod: string
  paymentConfirm: string
  settlementMethod: string
  transactionHistory: string
  // 现场观察区
  venueDescription: string
  inventoryObservation: string
  productionCapacity: string
  equipmentCondition: string
  operatingStatus: string
  // 结论区
  conclusion: string
  abnormalItems: string
  followUpActions: string
  interviewer: string
}

// ─── State ────────────────────────────────────────────────────────────

const ITEM_ID = 'D4-interview-template-records'

const records = computed<InterviewRecord[]>({
  get() {
    const resp = props.allResponses.get(ITEM_ID)
    if (!resp?.remark) return []
    try {
      const parsed = JSON.parse(resp.remark)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  },
  set(val) {
    const map = props.allResponses as Map<string, any>
    map.set(ITEM_ID, { item_id: ITEM_ID, conclusion: null, remark: JSON.stringify(val) })
  },
})

const activeRecordIndex = ref(0)

const currentRecord = computed(() => {
  if (records.value.length === 0) return null
  return records.value[activeRecordIndex.value] || records.value[0]
})

// ─── Actions ──────────────────────────────────────────────────────────

function createNewRecord() {
  const newRecord: InterviewRecord = {
    id: `visit-${Date.now()}`,
    companyName: '',
    visitDate: new Date().toISOString().slice(0, 10),
    bizLicense: '',
    registeredAddress: '',
    operatingAddress: '',
    legalPerson: '',
    registeredCapital: '',
    staffCount: '',
    mainBusiness: '',
    transactionAmount: '',
    productCategory: '',
    pricingMethod: '',
    paymentConfirm: '',
    settlementMethod: '',
    transactionHistory: '',
    venueDescription: '',
    inventoryObservation: '',
    productionCapacity: '',
    equipmentCondition: '',
    operatingStatus: '',
    conclusion: '',
    abnormalItems: '',
    followUpActions: '',
    interviewer: '',
  }
  const newList = [...records.value, newRecord]
  records.value = newList
  activeRecordIndex.value = newList.length - 1
}

function updateField(field: keyof InterviewRecord, value: string) {
  if (!currentRecord.value) return
  const list = [...records.value]
  const idx = activeRecordIndex.value
  list[idx] = { ...list[idx], [field]: value }
  records.value = list
}

function removeRecord(index: number) {
  const list = [...records.value]
  list.splice(index, 1)
  records.value = list
  if (activeRecordIndex.value >= list.length) {
    activeRecordIndex.value = Math.max(0, list.length - 1)
  }
}
</script>

<template>
  <div class="d4-tab-interview-template">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表为IPO项目客户走访记录模板，适用于对重要客户的实地走访核查。</p>
        <p>2. 每次走访单独建一条记录，记录公司基本信息、交易核实情况和现场观察结果。</p>
        <p>3. 走访应重点关注：经营真实性、交易合理性、回款确认、现场一致性。</p>
        <p>4. 异常事项须在"结论区"详细说明并制定后续跟进措施。</p>
      </div>
    </details>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button type="primary" size="small" :disabled="isReadonly" @click="createNewRecord">
          + 新建走访记录
        </el-button>
        <el-button size="small" disabled title="AI预填功能开发中">🤖 AI预填</el-button>
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="info">共 {{ records.length }} 条走访记录</el-tag>
      </div>
    </div>

    <!-- 记录选择 -->
    <div v-if="records.length > 0" class="record-tabs">
      <el-tabs v-model="activeRecordIndex" type="card">
        <el-tab-pane
          v-for="(rec, idx) in records"
          :key="rec.id"
          :name="idx"
          :label="rec.companyName || `走访记录 ${idx + 1}`"
        >
          <template #label>
            <span>{{ rec.companyName || `走访记录 ${idx + 1}` }}</span>
            <el-button
              v-if="!isReadonly"
              type="danger"
              size="small"
              link
              style="margin-left: 8px"
              @click.stop="removeRecord(idx)"
            >×</el-button>
          </template>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 空状态 -->
    <div v-if="records.length === 0" class="empty-state">
      <el-empty description="暂无走访记录，请点击“新建走访记录”开始" />
    </div>

    <!-- 当前记录编辑区 -->
    <template v-if="currentRecord">
      <!-- 基本信息区 -->
      <el-card class="section-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="section-title">一、走访公司基本信息</span>
            <el-button size="small" circle @click="openReviewDialog?.('D4-interview-basic')">💬</el-button>
          </div>
        </template>
        <el-form label-width="100px" size="small">
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="公司名称">
                <el-input :model-value="currentRecord.companyName" :disabled="isReadonly" placeholder="走访对象公司全称" @input="(v: string) => updateField('companyName', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="走访日期">
                <el-input :model-value="currentRecord.visitDate" :disabled="isReadonly" type="date" @input="(v: string) => updateField('visitDate', v)" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="法定代表人">
                <el-input :model-value="currentRecord.legalPerson" :disabled="isReadonly" @input="(v: string) => updateField('legalPerson', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="注册资本">
                <el-input :model-value="currentRecord.registeredCapital" :disabled="isReadonly" @input="(v: string) => updateField('registeredCapital', v)" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="工商信息">
            <el-input :model-value="currentRecord.bizLicense" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 2 }" placeholder="统一社会信用代码、经营范围等" @input="(v: string) => updateField('bizLicense', v)" />
          </el-form-item>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="注册地址">
                <el-input :model-value="currentRecord.registeredAddress" :disabled="isReadonly" @input="(v: string) => updateField('registeredAddress', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="经营地址">
                <el-input :model-value="currentRecord.operatingAddress" :disabled="isReadonly" @input="(v: string) => updateField('operatingAddress', v)" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="人员规模">
                <el-input :model-value="currentRecord.staffCount" :disabled="isReadonly" placeholder="人数/部门结构" @input="(v: string) => updateField('staffCount', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="主营业务">
                <el-input :model-value="currentRecord.mainBusiness" :disabled="isReadonly" @input="(v: string) => updateField('mainBusiness', v)" />
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>
      </el-card>

      <!-- 交易核实区 -->
      <el-card class="section-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="section-title">二、交易核实</span>
            <el-button size="small" circle @click="openReviewDialog?.('D4-interview-transaction')">💬</el-button>
          </div>
        </template>
        <el-form label-width="100px" size="small">
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="交易金额">
                <el-input :model-value="currentRecord.transactionAmount" :disabled="isReadonly" placeholder="审计期间交易总额" @input="(v: string) => updateField('transactionAmount', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="产品/品种">
                <el-input :model-value="currentRecord.productCategory" :disabled="isReadonly" placeholder="交易产品类别" @input="(v: string) => updateField('productCategory', v)" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="定价方式">
                <el-input :model-value="currentRecord.pricingMethod" :disabled="isReadonly" placeholder="合同定价/市场定价/协议定价" @input="(v: string) => updateField('pricingMethod', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="结算方式">
                <el-input :model-value="currentRecord.settlementMethod" :disabled="isReadonly" placeholder="预付/货到付款/赊销" @input="(v: string) => updateField('settlementMethod', v)" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="回款确认">
            <el-input :model-value="currentRecord.paymentConfirm" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 2 }" placeholder="确认交易回款情况，核对银行流水" @input="(v: string) => updateField('paymentConfirm', v)" />
          </el-form-item>
          <el-form-item label="交易历史">
            <el-input :model-value="currentRecord.transactionHistory" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 2 }" placeholder="合作年限、交易规模变化趋势" @input="(v: string) => updateField('transactionHistory', v)" />
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 现场观察区 -->
      <el-card class="section-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="section-title">三、现场观察</span>
            <el-button size="small" circle @click="openReviewDialog?.('D4-interview-observation')">💬</el-button>
          </div>
        </template>
        <el-form label-width="100px" size="small">
          <el-form-item label="经营场地">
            <el-input :model-value="currentRecord.venueDescription" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 2 }" placeholder="办公场所面积、装修情况、人员在岗情况" @input="(v: string) => updateField('venueDescription', v)" />
          </el-form-item>
          <el-form-item label="库存观察">
            <el-input :model-value="currentRecord.inventoryObservation" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 2 }" placeholder="仓库面积、库存规模、出入库管理" @input="(v: string) => updateField('inventoryObservation', v)" />
          </el-form-item>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="生产能力">
                <el-input :model-value="currentRecord.productionCapacity" :disabled="isReadonly" placeholder="产线数量/日产能" @input="(v: string) => updateField('productionCapacity', v)" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="设备状况">
                <el-input :model-value="currentRecord.equipmentCondition" :disabled="isReadonly" placeholder="设备新旧/运转状态" @input="(v: string) => updateField('equipmentCondition', v)" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="经营状态">
            <el-input :model-value="currentRecord.operatingStatus" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 2 }" placeholder="与注册信息一致性、实际经营规模评估" @input="(v: string) => updateField('operatingStatus', v)" />
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 结论区 -->
      <el-card class="section-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="section-title">四、走访结论</span>
            <el-button size="small" circle @click="openReviewDialog?.('D4-interview-conclusion')">💬</el-button>
          </div>
        </template>
        <el-form label-width="100px" size="small">
          <el-form-item label="总体结论">
            <el-input :model-value="currentRecord.conclusion" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 3 }" placeholder="走访总体结论（经营真实性/交易合理性判断）" @input="(v: string) => updateField('conclusion', v)" />
          </el-form-item>
          <el-form-item label="异常事项">
            <el-input :model-value="currentRecord.abnormalItems" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 2 }" placeholder="如有异常请详细列示" @input="(v: string) => updateField('abnormalItems', v)" />
          </el-form-item>
          <el-form-item label="后续措施">
            <el-input :model-value="currentRecord.followUpActions" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 2 }" placeholder="需进一步跟进的事项" @input="(v: string) => updateField('followUpActions', v)" />
          </el-form-item>
          <el-form-item label="走访人员">
            <el-input :model-value="currentRecord.interviewer" :disabled="isReadonly" placeholder="审计团队走访人员姓名" @input="(v: string) => updateField('interviewer', v)" />
          </el-form-item>
        </el-form>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.d4-tab-interview-template {
  padding: 12px;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.record-tabs {
  margin-bottom: 12px;
}
.empty-state {
  padding: 40px;
}
.section-card {
  margin-bottom: 16px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}
</style>
