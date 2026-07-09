<template>
  <div class="s12-branch-fin-instrument">
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>S12-3-4 利用专家评价管理层的工作(金融工具公允价值）</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s12-3-4-fin-instrument', '金融工具公允价值评价')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <div class="methodology-context">
        <p>本表用于评价利用注册会计师的专家评价管理层在金融工具公允价值计量领域工作的适当性。重点关注估值技术的选用、公允价值层次划分、重大不可观察输入值等。</p>
      </div>

      <!-- 评价对象基本信息 -->
      <el-descriptions :column="2" border class="eval-info" size="small">
        <el-descriptions-item label="评价领域">
          <el-tag type="danger">金融工具公允价值</el-tag>
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
        <el-descriptions-item label="金融工具类型">
          <el-select
            v-if="!isReadonly"
            v-model="expertInfo.instrumentType"
            size="small"
            placeholder="请选择"
          >
            <el-option label="债务工具" value="debt" />
            <el-option label="权益工具" value="equity" />
            <el-option label="衍生工具" value="derivative" />
            <el-option label="结构化产品" value="structured" />
            <el-option label="其他" value="other" />
          </el-select>
          <span v-else>{{ expertInfo.instrumentType || '—' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="公允价值层次">
          <el-select
            v-if="!isReadonly"
            v-model="expertInfo.fvLevel"
            size="small"
            placeholder="请选择"
          >
            <el-option label="第一层次" value="Level1" />
            <el-option label="第二层次" value="Level2" />
            <el-option label="第三层次" value="Level3" />
          </el-select>
          <span v-else>{{ expertInfo.fvLevel || '—' }}</span>
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
      <p>1. 金融工具的分类是否正确（以公允价值计量/以摊余成本计量/FVOCI）。</p>
      <p>2. 估值技术的选择是否恰当（市场法/收益法/成本法）。</p>
      <p>3. 第三层次输入值的使用和披露是否充分。</p>
      <p>4. 公允价值层次间的转换是否正确识别和披露。</p>
      <p>5. 关注估值调整（如流动性折价、信用风险调整）的恰当性。</p>
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
  instrumentType: '',
  fvLevel: '',
})

const evalItems = ref([
  { category: '估值技术', question: '管理层使用的估值技术是否恰当（如DCF、可比交易法、期权定价法）？', answer: '', remark: '' },
  { category: '估值技术', question: '估值技术是否适用于该类金融工具的特征？', answer: '', remark: '' },
  { category: '估值技术', question: '估值技术是否与以前年度一致（如变更，变更理由是否充分）？', answer: '', remark: '' },
  { category: '输入值', question: '可观察输入值（第一/二层次）的来源和时点是否恰当？', answer: '', remark: '' },
  { category: '输入值', question: '不可观察输入值（第三层次）的确定方法是否合理？', answer: '', remark: '' },
  { category: '输入值', question: '折现率的确定（基准利率+信用利差+流动性溢价）是否合理？', answer: '', remark: '' },
  { category: '输入值', question: '预期现金流量的估计是否恰当？', answer: '', remark: '' },
  { category: '输入值', question: '波动率假设（如适用）是否合理？', answer: '', remark: '' },
  { category: '层次划分', question: '公允价值层次的划分是否正确？', answer: '', remark: '' },
  { category: '层次划分', question: '层次间的转换是否得到正确识别？', answer: '', remark: '' },
  { category: '调整', question: '估值调整（如信用风险调整/CVA/DVA）的计算是否恰当？', answer: '', remark: '' },
  { category: '调整', question: '流动性折价（如适用）的幅度是否合理？', answer: '', remark: '' },
  { category: '调整', question: '模型风险调整（如适用）是否恰当？', answer: '', remark: '' },
  { category: '数据', question: '估值使用的市场数据是否完整、准确、时效适当？', answer: '', remark: '' },
  { category: '数据', question: '数据来源（Bloomberg/Wind/交易所等）是否可靠？', answer: '', remark: '' },
  { category: '结论', question: '注册会计师专家的估值结果与管理层结果是否一致？', answer: '', remark: '' },
  { category: '结论', question: '如存在差异，差异金额是否重大？差异原因是否合理？', answer: '', remark: '' },
  { category: '披露', question: '公允价值的计量方法和关键假设是否在附注中恰当披露？', answer: '', remark: '' },
  { category: '披露', question: '第三层次公允价值计量的敏感性分析是否恰当披露？', answer: '', remark: '' },
])

const evalConclusion = ref('')

function handleAiAssist() { /* TODO */ }
function handleAiConclusion() { /* TODO */ }
</script>

<style scoped>
.s12-branch-fin-instrument { padding: 12px; }
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
.conclusion-text { white-space: pre-wrap; font-size: 13px; line-height: 1.6; color: #303133; }
.edit-hints { margin-top: 16px; font-size: 12px; color: #909399; }
.edit-hints summary { cursor: pointer; user-select: none; }
.edit-hints p { margin: 4px 0; line-height: 1.5; }
</style>
