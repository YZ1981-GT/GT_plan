<template>
  <div class="i6-tab-targeted-check">
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 费用归集完整性：研发费用是否全面归集到6602</div>
        <div class="guide-step"><span class="step-num">②</span> 人员费用分摊合理性：研发人员工时/工资分摊依据</div>
        <div class="guide-step"><span class="step-num">③</span> 与I2划分一致性：费用化(I6)+资本化(I2)划分合规</div>
      </div>
    </div>

    <!-- Section 1: 费用归集完整性 -->
    <el-card shadow="never" class="check-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">一、费用归集完整性</span>
          <div class="section-actions">
            <el-button size="small" type="primary" text @click="handleAiGenerate('completeness')"><el-icon><MagicStick /></el-icon> AI</el-button>
            <el-button size="small" type="default" text @click="handleReview">复核</el-button>
          </div>
        </div>
      </template>
      <div class="methodology-block">
        <p><strong>方法论：</strong>研发费用归集完整性检查要点：</p>
        <p>1. 核实是否所有符合条件的研发支出均已归集到6602科目</p>
        <p>2. 检查是否存在应归入研发费用但计入其他科目的支出</p>
        <p>3. 核查研发项目立项与费用归集的对应关系</p>
      </div>
      <div class="check-items">
        <div class="check-item">
          <span class="check-label">研发项目立项是否完整覆盖实际研发活动：</span>
          <el-radio-group v-model="checkItems.completeProject" :disabled="isReadonly" size="small" @change="onCheckChange('completeProject')">
            <el-radio-button value="正常">正常</el-radio-button><el-radio-button value="异常">异常</el-radio-button><el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
        <div class="check-item">
          <span class="check-label">是否存在应归入研发费用但计入管理费用等的支出：</span>
          <el-radio-group v-model="checkItems.completeMisclass" :disabled="isReadonly" size="small" @change="onCheckChange('completeMisclass')">
            <el-radio-button value="正常">正常</el-radio-button><el-radio-button value="异常">异常</el-radio-button><el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
      </div>
      <div class="section-conclusion">
        <span class="conclusion-label">本节结论：</span>
        <el-input v-model="conclusions.completeness" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="请填写费用归集完整性检查结论..." @blur="onConclusionBlur('completeness')" />
      </div>
    </el-card>

    <!-- Section 2: 人员费用分摊合理性 -->
    <el-card shadow="never" class="check-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">二、人员费用分摊合理性</span>
          <div class="section-actions">
            <el-button size="small" type="primary" text @click="handleAiGenerate('allocation')"><el-icon><MagicStick /></el-icon> AI</el-button>
            <el-button size="small" type="default" text @click="handleReview">复核</el-button>
          </div>
        </div>
      </template>
      <div class="methodology-block">
        <p><strong>方法论：</strong>人员费用分摊合理性检查：</p>
        <p>1. 核实研发人员名单与实际参与研发活动的人员是否一致</p>
        <p>2. 工时分摊比例是否有充分依据（工时记录/考勤/项目周报）</p>
        <p>3. 人工费用分摊方法是否合理且前后一致</p>
      </div>
      <div class="check-items">
        <div class="check-item">
          <span class="check-label">研发人员名单与实际参与研发的人员一致：</span>
          <el-radio-group v-model="checkItems.allocStaff" :disabled="isReadonly" size="small" @change="onCheckChange('allocStaff')">
            <el-radio-button value="正常">正常</el-radio-button><el-radio-button value="异常">异常</el-radio-button><el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
        <div class="check-item">
          <span class="check-label">工时分摊有充分支撑依据：</span>
          <el-radio-group v-model="checkItems.allocBasis" :disabled="isReadonly" size="small" @change="onCheckChange('allocBasis')">
            <el-radio-button value="正常">正常</el-radio-button><el-radio-button value="异常">异常</el-radio-button><el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
      </div>
      <div class="section-conclusion">
        <span class="conclusion-label">本节结论：</span>
        <el-input v-model="conclusions.allocation" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="请填写人员费用分摊合理性结论..." @blur="onConclusionBlur('allocation')" />
      </div>
    </el-card>

    <!-- Section 3: 与I2划分一致性 -->
    <el-card shadow="never" class="check-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">三、与I2划分一致性</span>
          <div class="section-actions">
            <el-button size="small" type="primary" text @click="handleAiGenerate('i2consistency')"><el-icon><MagicStick /></el-icon> AI</el-button>
            <el-button size="small" type="default" text @click="handleReview">复核</el-button>
          </div>
        </div>
      </template>
      <div class="methodology-block">
        <p><strong>方法论：</strong>费用化(I6)与资本化(I2)划分一致性：</p>
        <p>1. CAS 6号：研究阶段支出全部费用化，开发阶段满足5条件可资本化</p>
        <p>2. 验证费用化(I6)与资本化(I2)的划分时点、金额是否一致</p>
        <p>3. VR-I6-01：费用化+资本化=研发总额，确认无遗漏/重复</p>
      </div>
      <div class="check-items">
        <div class="check-item">
          <span class="check-label">研究/开发阶段划分时点合理：</span>
          <el-radio-group v-model="checkItems.i2PhaseDiv" :disabled="isReadonly" size="small" @change="onCheckChange('i2PhaseDiv')">
            <el-radio-button value="正常">正常</el-radio-button><el-radio-button value="异常">异常</el-radio-button><el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
        <div class="check-item">
          <span class="check-label">费用化+资本化=研发总额（VR-I6-01）：</span>
          <el-radio-group v-model="checkItems.i2VrBalance" :disabled="isReadonly" size="small" @change="onCheckChange('i2VrBalance')">
            <el-radio-button value="正常">正常</el-radio-button><el-radio-button value="异常">异常</el-radio-button><el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
      </div>
      <div class="section-conclusion">
        <span class="conclusion-label">本节结论：</span>
        <el-input v-model="conclusions.i2consistency" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="请填写与I2划分一致性结论..." @blur="onConclusionBlur('i2consistency')" />
      </div>
    </el-card>

    <!-- 总体结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header><div class="section-header"><span class="section-title">总体审计结论</span></div></template>
      <el-select v-model="overallConclusion" placeholder="请选择" :disabled="isReadonly" class="conclusion-select" @change="onOverallChange">
        <el-option value="针对性检查未发现异常，研发费用归集完整、分摊合理、与I2划分一致" label="针对性检查未发现异常，研发费用归集完整、分摊合理、与I2划分一致" />
        <el-option value="存在需关注事项，但不影响整体列报" label="存在需关注事项，但不影响整体列报" />
        <el-option value="发现需调整事项" label="发现需调整事项" />
      </el-select>
    </el-card>

    <details class="compile-hint"><summary>编制提示</summary><ul>
      <li>三维度检查：费用归集完整性/人员分摊合理性/I2划分一致性</li>
      <li>CAS 6号五条件是资本化判断依据</li>
      <li>VR-I6-01：费用化(I6)+资本化(I2)=研发总额</li>
    </ul></details>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import http from '@/utils/http'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const emit = defineEmits<{ 'save': [itemId: string, value: any] }>()
const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

const PREFIX = 'I6-4'
const checkItems = reactive({
  completeProject: '', completeMisclass: '',
  allocStaff: '', allocBasis: '',
  i2PhaseDiv: '', i2VrBalance: '',
})
const conclusions = reactive({ completeness: '', allocation: '', i2consistency: '' })
const overallConclusion = ref('')

function _load(): void {
  checkItems.completeProject = _str(`${PREFIX}-complete-project`)
  checkItems.completeMisclass = _str(`${PREFIX}-complete-misclass`)
  checkItems.allocStaff = _str(`${PREFIX}-alloc-staff`)
  checkItems.allocBasis = _str(`${PREFIX}-alloc-basis`)
  checkItems.i2PhaseDiv = _str(`${PREFIX}-i2-phase-div`)
  checkItems.i2VrBalance = _str(`${PREFIX}-i2-vr-balance`)
  conclusions.completeness = _str(`${PREFIX}-completeness-conclusion`)
  conclusions.allocation = _str(`${PREFIX}-allocation-conclusion`)
  conclusions.i2consistency = _str(`${PREFIX}-i2consistency-conclusion`)
  overallConclusion.value = _str(`${PREFIX}-conclusion`)
}
function _str(id: string): string { const item = props.allResponses.get(id); return (item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : '')) as string }
watch(() => props.allResponses, () => _load(), { immediate: true })

const CHECK_MAP: Record<string, string> = {
  completeProject: `${PREFIX}-complete-project`, completeMisclass: `${PREFIX}-complete-misclass`,
  allocStaff: `${PREFIX}-alloc-staff`, allocBasis: `${PREFIX}-alloc-basis`,
  i2PhaseDiv: `${PREFIX}-i2-phase-div`, i2VrBalance: `${PREFIX}-i2-vr-balance`,
}
function onCheckChange(field: keyof typeof checkItems): void { emit('save', CHECK_MAP[field], checkItems[field]) }
function onConclusionBlur(field: keyof typeof conclusions): void { emit('save', `${PREFIX}-${field}-conclusion`, conclusions[field]) }
function onOverallChange(val: string): void { emit('save', `${PREFIX}-conclusion`, val) }

async function handleAiGenerate(section: string): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, { section, prompt: `I6针对性检查-${section}`, context: { wpCode: 'I6-4', topic: section } })
    if (res.data?.data?.content) { const k = section as keyof typeof conclusions; conclusions[k] = res.data.data.content; onConclusionBlur(k) }
  } catch { /* */ }
}
function handleReview(): void { openReviewDialog('I6-4 针对性检查') }
</script>

<style scoped>
.i6-tab-targeted-check { padding: 16px; font-size: 13px; }
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: flex-start; gap: 6px; font-size: 13px; }
.step-num { font-weight: 700; color: var(--el-color-primary); min-width: 20px; }
.check-section { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-size: 14px; font-weight: 600; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.methodology-block { border-left: 4px solid #d97706; background: #fffbeb; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.7; }
.methodology-block p { margin: 0 0 2px; }
.methodology-block strong { color: #78350f; }
.check-items { margin-bottom: 12px; }
.check-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-bottom: 1px dashed var(--el-border-color-lighter); }
.check-item:last-child { border-bottom: none; }
.check-label { font-size: 13px; color: var(--el-text-color-regular); flex: 1; }
.section-conclusion { margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--el-border-color-lighter); }
.conclusion-label { font-size: 12px; color: var(--el-text-color-regular); display: block; margin-bottom: 6px; }
.conclusion-card { margin-bottom: 16px; }
.conclusion-select { width: 100%; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
