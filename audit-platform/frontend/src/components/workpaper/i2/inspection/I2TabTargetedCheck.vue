<template>
  <div class="i2-targeted-check">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-12 针对性检查表</span>
      <div class="section-actions">
        <el-button size="small" type="primary" text @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" type="default" text @click="handleReview">
          复核
        </el-button>
      </div>
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>针对开发支出底稿的特定风险领域进行专项检查，关注：研发费用加计扣除合规性、资本化比例合理性、项目进度与里程碑。</p>
    </div>

    <!-- 检查项卡片：研发费用加计扣除合规性 -->
    <el-card class="check-section" shadow="never">
      <template #header>
        <div class="check-section-header">
          <span class="check-section-title">一、研发费用加计扣除合规性</span>
          <el-button size="small" type="primary" text @click="handleAiSection('加计扣除')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <div class="check-section-body">
        <el-input
          v-model="sections.deductionCompliance"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 10 }"
          placeholder="请检查：&#10;1. 研发费用归集范围是否符合财税[2015]119号文规定&#10;2. 加计扣除比例适用是否正确（制造业100%/其他75%）&#10;3. 委外研发按80%加计扣除是否正确计算&#10;4. 负面清单行业排除是否执行"
        />
        <div class="conclusion-row">
          <span class="conclusion-label">检查结论：</span>
          <el-select v-model="conclusions.deductionCompliance" size="small" placeholder="选择结论" style="width:200px">
            <el-option label="合规" value="合规" />
            <el-option label="存在偏差" value="存在偏差" />
            <el-option label="不合规" value="不合规" />
            <el-option label="不适用" value="不适用" />
          </el-select>
        </div>
      </div>
    </el-card>

    <!-- 检查项卡片：资本化比例合理性 -->
    <el-card class="check-section" shadow="never">
      <template #header>
        <div class="check-section-header">
          <span class="check-section-title">二、资本化比例合理性</span>
          <el-button size="small" type="primary" text @click="handleAiSection('资本化比例')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <div class="check-section-body">
        <el-input
          v-model="sections.capitalizationRatio"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 10 }"
          placeholder="请检查：&#10;1. 资本化支出占研发总投入比例是否合理（同行业对比）&#10;2. 各项目资本化时点判断是否一致（参照I2-6五条件结论）&#10;3. 资本化金额是否与开发阶段实际进度匹配&#10;4. 研究阶段与开发阶段的划分标准是否清晰"
        />
        <div class="conclusion-row">
          <span class="conclusion-label">检查结论：</span>
          <el-select v-model="conclusions.capitalizationRatio" size="small" placeholder="选择结论" style="width:200px">
            <el-option label="合理" value="合理" />
            <el-option label="偏高" value="偏高" />
            <el-option label="偏低" value="偏低" />
            <el-option label="不合理" value="不合理" />
          </el-select>
        </div>
      </div>
    </el-card>

    <!-- 检查项卡片：项目进度与里程碑 -->
    <el-card class="check-section" shadow="never">
      <template #header>
        <div class="check-section-header">
          <span class="check-section-title">三、项目进度与里程碑</span>
          <el-button size="small" type="primary" text @click="handleAiSection('项目进度')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <div class="check-section-body">
        <el-input
          v-model="sections.projectProgress"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 10 }"
          placeholder="请检查：&#10;1. 各研发项目是否按立项计划推进&#10;2. 关键里程碑是否有对应验收文档支撑&#10;3. 长期未结项的项目是否存在减值迹象&#10;4. 项目终止/暂停的费用化处理是否正确"
        />
        <div class="conclusion-row">
          <span class="conclusion-label">检查结论：</span>
          <el-select v-model="conclusions.projectProgress" size="small" placeholder="选择结论" style="width:200px">
            <el-option label="正常" value="正常" />
            <el-option label="存在延期" value="存在延期" />
            <el-option label="存在减值迹象" value="存在减值迹象" />
            <el-option label="需进一步关注" value="需进一步关注" />
          </el-select>
        </div>
      </div>
    </el-card>

    <!-- 综合结论 -->
    <el-card class="overall-conclusion" shadow="never">
      <template #header>
        <span style="font-weight:600">综合检查结论</span>
      </template>
      <el-input
        v-model="overallConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 6 }"
        placeholder="综合以上针对性检查结果，说明审计意见和后续跟进事项..."
      />
    </el-card>

    <!-- 保存 -->
    <div class="table-actions">
      <el-button size="small" type="success" @click="handleSave">保存</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, inject, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
}>()

const emit = defineEmits<{ 'save': []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const STORAGE_KEY = 'I2-12-targeted'

const sections = reactive({
  deductionCompliance: '',
  capitalizationRatio: '',
  projectProgress: '',
})

const conclusions = reactive({
  deductionCompliance: '',
  capitalizationRatio: '',
  projectProgress: '',
})

const overallConclusion = ref('')

function loadData() {
  const raw = props.allResponses.get(STORAGE_KEY)
  if (!raw) return
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : (raw.remark ? JSON.parse(raw.remark) : raw)
    if (parsed) {
      sections.deductionCompliance = parsed.sections?.deductionCompliance || ''
      sections.capitalizationRatio = parsed.sections?.capitalizationRatio || ''
      sections.projectProgress = parsed.sections?.projectProgress || ''
      conclusions.deductionCompliance = parsed.conclusions?.deductionCompliance || ''
      conclusions.capitalizationRatio = parsed.conclusions?.capitalizationRatio || ''
      conclusions.projectProgress = parsed.conclusions?.projectProgress || ''
      overallConclusion.value = parsed.overallConclusion || ''
    }
  } catch { /* ignore */ }
}

watch(() => props.allResponses, () => loadData(), { immediate: true })

async function handleSave() {
  const data = { sections: { ...sections }, conclusions: { ...conclusions }, overallConclusion: overallConclusion.value }
  await props.saveResponse('I2-12', { [STORAGE_KEY]: JSON.stringify(data) })
  emit('save'); ElMessage.success('针对性检查表已保存')
}

function handleAiAssist() { ElMessage.info('AI辅助全部检查项分析...') }
function handleAiSection(section: string) { ElMessage.info(`AI辅助"${section}"检查分析...`) }
function handleReview() { openReviewDialog('I2-12-针对性检查') }
</script>

<style scoped>
.i2-targeted-check { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6; }
.check-section { margin-bottom: 16px; }
.check-section-header { display: flex; align-items: center; justify-content: space-between; }
.check-section-title { font-size: 14px; font-weight: 600; color: #374151; }
.check-section-body { display: flex; flex-direction: column; gap: 12px; }
.conclusion-row { display: flex; align-items: center; gap: 12px; margin-top: 8px; }
.conclusion-label { font-weight: 500; color: #374151; white-space: nowrap; }
.overall-conclusion { margin-top: 8px; }
.table-actions { display: flex; gap: 8px; margin-top: 16px; }
</style>
