<template>
  <div class="s12-branch-share-payment">
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>S12-3-3 利用专家评价管理层的工作(股份支付)</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s12-3-3-share-payment', '股份支付评价')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <div class="methodology-context">
        <p>本表用于评价利用注册会计师的专家评价管理层在股份支付领域工作的适当性。重点关注期权定价模型（如Black-Scholes模型）的假设、行权条件、公允价值计量等。</p>
      </div>

      <!-- 评价对象基本信息 -->
      <el-descriptions :column="2" border class="eval-info" size="small">
        <el-descriptions-item label="评价领域">
          <el-tag type="warning">股份支付</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="管理层专家">
          <el-input
            v-if="!isReadonly"
            v-model="expertInfo.name"
            size="small"
            placeholder="管理层专家姓名/机构"
          />
          <span v-else>{{ expertInfo.name || '—' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="股份支付类型">
          <el-select
            v-if="!isReadonly"
            v-model="expertInfo.paymentType"
            size="small"
            placeholder="请选择"
          >
            <el-option label="以权益结算的股份支付" value="equity" />
            <el-option label="以现金结算的股份支付" value="cash" />
            <el-option label="混合" value="mixed" />
          </el-select>
          <span v-else>{{ expertInfo.paymentType || '—' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="评价日期">
          <el-date-picker
            v-if="!isReadonly"
            v-model="expertInfo.date"
            type="date"
            size="small"
            placeholder="选择日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
          />
          <span v-else>{{ expertInfo.date || '—' }}</span>
        </el-descriptions-item>
      </el-descriptions>

      <!-- 评价检查表 -->
      <el-table
        :data="evalItems"
        border
        style="width: 100%; font-size: 13px; margin-top: 16px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="category" label="评价类别" width="130">
          <template #default="{ row }">
            <span>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="question" label="评价项目" min-width="360">
          <template #default="{ row }">
            <span>{{ row.question }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="answer" label="评价结论" width="140" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.answer"
              size="small"
              placeholder="—"
              style="width: 110px"
            >
              <el-option label="恰当" value="恰当" />
              <el-option label="基本恰当" value="基本恰当" />
              <el-option label="不恰当" value="不恰当" />
              <el-option label="不适用" value="不适用" />
            </el-select>
            <span v-else>{{ row.answer || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="说明/证据" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="说明"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 总体评价结论 -->
    <el-card shadow="never" class="audit-section conclusion-card">
      <template #header>
        <div class="section-header">
          <span>总体评价结论</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiConclusion"
            >AI辅助</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-if="!isReadonly"
        v-model="evalConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="填写总体评价结论"
      />
      <div v-else class="conclusion-text">{{ evalConclusion || '—' }}</div>
    </el-card>

    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 股份支付中定价模型的选择是否恰当（如 Black-Scholes、二叉树）。</p>
      <p>2. 关键输入参数：标的股价、行权价、预期波动率、无风险利率、预期存续期。</p>
      <p>3. 行权条件（服务期限条件/市场条件/非市场条件）的会计处理是否正确。</p>
      <p>4. 等待期内每个资产负债表日的费用确认方法是否恰当。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  domain?: string
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog')

function handleOpenReview(sectionId: string, label: string) {
  openReviewDialog?.(sectionId, label)
}

const expertInfo = ref({
  name: '',
  paymentType: '',
  date: '',
})

const evalItems = ref([
  { category: '定价模型', question: '管理层使用的期权定价模型是否恰当（如Black-Scholes、二叉树模型）？', answer: '', remark: '' },
  { category: '定价模型', question: '所选模型是否适用于授予条款的具体特征？', answer: '', remark: '' },
  { category: '输入参数', question: '标的股票价格的确定是否恰当？', answer: '', remark: '' },
  { category: '输入参数', question: '行权价格的确定是否与授予条款一致？', answer: '', remark: '' },
  { category: '输入参数', question: '预期波动率的估计方法和数据来源是否合理？', answer: '', remark: '' },
  { category: '输入参数', question: '无风险利率的选取是否恰当（期限、来源）？', answer: '', remark: '' },
  { category: '输入参数', question: '预期存续期（行权期）的估计是否合理（考虑提前行权行为）？', answer: '', remark: '' },
  { category: '输入参数', question: '预期股利率的假设是否合理？', answer: '', remark: '' },
  { category: '行权条件', question: '服务期限条件的确定是否恰当？', answer: '', remark: '' },
  { category: '行权条件', question: '业绩条件（非市场条件）是否影响了授予日公允价值的确定？', answer: '', remark: '' },
  { category: '行权条件', question: '市场条件是否在定价模型中正确反映？', answer: '', remark: '' },
  { category: '费用确认', question: '等待期内费用的分配方式（直线法）是否恰当？', answer: '', remark: '' },
  { category: '费用确认', question: '对预计可行权数量的最佳估计是否合理？', answer: '', remark: '' },
  { category: '数据', question: '定价模型使用的历史数据是否完整、准确？', answer: '', remark: '' },
  { category: '结论', question: '注册会计师专家的估值结果与管理层结果是否一致？', answer: '', remark: '' },
  { category: '结论', question: '如存在差异，差异金额是否重大？', answer: '', remark: '' },
])

const evalConclusion = ref('')

function handleAiAssist() { /* TODO */ }
function handleAiConclusion() { /* TODO */ }
</script>

<style scoped>
.s12-branch-share-payment { padding: 12px; }
.audit-section { margin-bottom: 16px; }
.section-header { display: flex; justify-content: space-between; align-items: center; }
.header-actions { display: flex; gap: 8px; }
.methodology-context {
  margin-bottom: 12px; padding: 8px 12px;
  border-left: 3px solid #e6a23c; background: #fdf6ec;
  font-size: 12px; color: #8a6914; line-height: 1.5;
}
.eval-info { margin-top: 12px; }
.conclusion-card { margin-top: 16px; }
.conclusion-text { white-space: pre-wrap; font-size: var(--wp-font-size, 13px); line-height: 1.6; color: #303133; }
.edit-hints { margin-top: 16px; font-size: 12px; color: #909399; }
.edit-hints summary { cursor: pointer; user-select: none; }
.edit-hints p { margin: 4px 0; line-height: 1.5; }
</style>
