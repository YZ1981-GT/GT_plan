<template>
  <div class="g6-tab-ecl-measurement">
    <!-- 方法论上下文（琥珀色左边线+浅黄背景）: ECL三要素定义 -->
    <div class="methodology-context">
      <p><strong>预期信用损失(ECL)三要素定义：</strong></p>
      <ul>
        <li><strong>ECL = PD × LGD × EAD × 折现因子</strong></li>
        <li><strong>PD（违约概率）</strong>：债务人在未来特定期间内违约的可能性</li>
        <li><strong>LGD（违约损失率）</strong>：违约发生后的损失比例（1 - 回收率）</li>
        <li><strong>EAD（违约风险暴露）</strong>：违约时点的预期风险敞口余额</li>
        <li><strong>折现因子</strong>：以原始实际利率或近似利率折现至报告日</li>
      </ul>
      <p style="margin-top:4px;color:#92400e">
        检查要点：验证企业ECL模型中各参数的数据来源、估计方法及前瞻性调整是否合理。
      </p>
    </div>

    <!-- ═══ Section(一) PD（违约概率） ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">(一) PD（违约概率）</span>
          <div class="section-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleAi('pd')">
              🤖 AI辅助
            </el-button>
            <el-button size="small" @click="openReview('G6-13-pd')">💬复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="pdSection" border size="small" class="ecl-table">
        <el-table-column label="序号" width="50" align="center" prop="seq" />
        <el-table-column label="检查区域" min-width="80" prop="checkArea" />
        <el-table-column label="检查项目" min-width="120" prop="checkItem" />
        <el-table-column label="审计要求" min-width="160">
          <template #default="{ row }">
            <span class="audit-req-text">{{ row.auditRequirement }}</span>
          </template>
        </el-table-column>
        <el-table-column label="企业参数" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.companyParam" type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }" placeholder="企业参数..."
              @update:model-value="(v: string) => updateRow(row.id, 'companyParam', v)" />
            <span v-else>{{ row.companyParam || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否合理" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.isReasonable" size="small"
              style="width:100%" placeholder="请选择"
              @change="(v: string) => updateRow(row.id, 'isReasonable', v)">
              <el-option value="合理" label="合理" />
              <el-option value="基本合理" label="基本合理" />
              <el-option value="不合理" label="不合理" />
            </el-select>
            <span v-else>{{ row.isReasonable || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计结论" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.auditConclusion" type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }" placeholder="审计结论..."
              @update:model-value="(v: string) => updateRow(row.id, 'auditConclusion', v)" />
            <span v-else>{{ row.auditConclusion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险等级" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.riskLevel" size="small"
              style="width:100%" placeholder="等级"
              @change="(v: string) => updateRow(row.id, 'riskLevel', v)">
              <el-option value="高" label="高" />
              <el-option value="中" label="中" />
              <el-option value="低" label="低" />
            </el-select>
            <span v-else>{{ row.riskLevel || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
            <el-input v-else-if="!isReadonly" v-model="row.indexRef" size="small"
              placeholder="索引" @change="() => updateRow(row.id, 'indexRef', row.indexRef)" />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              placeholder="备注..."
              @update:model-value="(v: string) => updateRow(row.id, 'remark', v)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section(二) LGD（违约损失率） ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">(二) LGD（违约损失率）</span>
          <div class="section-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleAi('lgd')">
              🤖 AI辅助
            </el-button>
            <el-button size="small" @click="openReview('G6-13-lgd')">💬复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="lgdSection" border size="small" class="ecl-table">
        <el-table-column label="序号" width="50" align="center" prop="seq" />
        <el-table-column label="检查区域" min-width="80" prop="checkArea" />
        <el-table-column label="检查项目" min-width="120" prop="checkItem" />
        <el-table-column label="审计要求" min-width="160">
          <template #default="{ row }">
            <span class="audit-req-text">{{ row.auditRequirement }}</span>
          </template>
        </el-table-column>
        <el-table-column label="企业参数" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.companyParam" type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }" placeholder="企业参数..."
              @update:model-value="(v: string) => updateRow(row.id, 'companyParam', v)" />
            <span v-else>{{ row.companyParam || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否合理" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.isReasonable" size="small"
              style="width:100%" placeholder="请选择"
              @change="(v: string) => updateRow(row.id, 'isReasonable', v)">
              <el-option value="合理" label="合理" />
              <el-option value="基本合理" label="基本合理" />
              <el-option value="不合理" label="不合理" />
            </el-select>
            <span v-else>{{ row.isReasonable || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计结论" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.auditConclusion" type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }" placeholder="审计结论..."
              @update:model-value="(v: string) => updateRow(row.id, 'auditConclusion', v)" />
            <span v-else>{{ row.auditConclusion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险等级" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.riskLevel" size="small"
              style="width:100%" placeholder="等级"
              @change="(v: string) => updateRow(row.id, 'riskLevel', v)">
              <el-option value="高" label="高" />
              <el-option value="中" label="中" />
              <el-option value="低" label="低" />
            </el-select>
            <span v-else>{{ row.riskLevel || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
            <el-input v-else-if="!isReadonly" v-model="row.indexRef" size="small"
              placeholder="索引" @change="() => updateRow(row.id, 'indexRef', row.indexRef)" />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              placeholder="备注..."
              @update:model-value="(v: string) => updateRow(row.id, 'remark', v)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section(三) EAD（违约风险暴露） ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">(三) EAD（违约风险暴露）</span>
          <div class="section-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleAi('ead')">
              🤖 AI辅助
            </el-button>
            <el-button size="small" @click="openReview('G6-13-ead')">💬复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="eadSection" border size="small" class="ecl-table">
        <el-table-column label="序号" width="50" align="center" prop="seq" />
        <el-table-column label="检查区域" min-width="80" prop="checkArea" />
        <el-table-column label="检查项目" min-width="120" prop="checkItem" />
        <el-table-column label="审计要求" min-width="160">
          <template #default="{ row }">
            <span class="audit-req-text">{{ row.auditRequirement }}</span>
          </template>
        </el-table-column>
        <el-table-column label="企业参数" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.companyParam" type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }" placeholder="企业参数..."
              @update:model-value="(v: string) => updateRow(row.id, 'companyParam', v)" />
            <span v-else>{{ row.companyParam || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否合理" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.isReasonable" size="small"
              style="width:100%" placeholder="请选择"
              @change="(v: string) => updateRow(row.id, 'isReasonable', v)">
              <el-option value="合理" label="合理" />
              <el-option value="基本合理" label="基本合理" />
              <el-option value="不合理" label="不合理" />
            </el-select>
            <span v-else>{{ row.isReasonable || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计结论" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.auditConclusion" type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }" placeholder="审计结论..."
              @update:model-value="(v: string) => updateRow(row.id, 'auditConclusion', v)" />
            <span v-else>{{ row.auditConclusion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险等级" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.riskLevel" size="small"
              style="width:100%" placeholder="等级"
              @change="(v: string) => updateRow(row.id, 'riskLevel', v)">
              <el-option value="高" label="高" />
              <el-option value="中" label="中" />
              <el-option value="低" label="低" />
            </el-select>
            <span v-else>{{ row.riskLevel || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
            <el-input v-else-if="!isReadonly" v-model="row.indexRef" size="small"
              placeholder="索引" @change="() => updateRow(row.id, 'indexRef', row.indexRef)" />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              placeholder="备注..."
              @update:model-value="(v: string) => updateRow(row.id, 'remark', v)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section(四) 折现率 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">(四) 折现率</span>
          <div class="section-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleAi('discount-rate')">
              🤖 AI辅助
            </el-button>
            <el-button size="small" @click="openReview('G6-13-discount-rate')">💬复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="discountRateSection" border size="small" class="ecl-table">
        <el-table-column label="序号" width="50" align="center" prop="seq" />
        <el-table-column label="检查区域" min-width="80" prop="checkArea" />
        <el-table-column label="检查项目" min-width="120" prop="checkItem" />
        <el-table-column label="审计要求" min-width="160">
          <template #default="{ row }">
            <span class="audit-req-text">{{ row.auditRequirement }}</span>
          </template>
        </el-table-column>
        <el-table-column label="企业参数" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.companyParam" type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }" placeholder="企业参数..."
              @update:model-value="(v: string) => updateRow(row.id, 'companyParam', v)" />
            <span v-else>{{ row.companyParam || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否合理" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.isReasonable" size="small"
              style="width:100%" placeholder="请选择"
              @change="(v: string) => updateRow(row.id, 'isReasonable', v)">
              <el-option value="合理" label="合理" />
              <el-option value="基本合理" label="基本合理" />
              <el-option value="不合理" label="不合理" />
            </el-select>
            <span v-else>{{ row.isReasonable || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计结论" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.auditConclusion" type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }" placeholder="审计结论..."
              @update:model-value="(v: string) => updateRow(row.id, 'auditConclusion', v)" />
            <span v-else>{{ row.auditConclusion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险等级" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.riskLevel" size="small"
              style="width:100%" placeholder="等级"
              @change="(v: string) => updateRow(row.id, 'riskLevel', v)">
              <el-option value="高" label="高" />
              <el-option value="中" label="中" />
              <el-option value="低" label="低" />
            </el-select>
            <span v-else>{{ row.riskLevel || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
            <el-input v-else-if="!isReadonly" v-model="row.indexRef" size="small"
              placeholder="索引" @change="() => updateRow(row.id, 'indexRef', row.indexRef)" />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              placeholder="备注..."
              @update:model-value="(v: string) => updateRow(row.id, 'remark', v)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section(五) 前瞻性信息 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">(五) 前瞻性信息</span>
          <div class="section-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleAi('forward-looking')">
              🤖 AI辅助
            </el-button>
            <el-button size="small" @click="openReview('G6-13-forward-looking')">💬复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="forwardLookingSection" border size="small" class="ecl-table">
        <el-table-column label="序号" width="50" align="center" prop="seq" />
        <el-table-column label="检查区域" min-width="80" prop="checkArea" />
        <el-table-column label="检查项目" min-width="120" prop="checkItem" />
        <el-table-column label="审计要求" min-width="160">
          <template #default="{ row }">
            <span class="audit-req-text">{{ row.auditRequirement }}</span>
          </template>
        </el-table-column>
        <el-table-column label="企业参数" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.companyParam" type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }" placeholder="企业参数..."
              @update:model-value="(v: string) => updateRow(row.id, 'companyParam', v)" />
            <span v-else>{{ row.companyParam || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否合理" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.isReasonable" size="small"
              style="width:100%" placeholder="请选择"
              @change="(v: string) => updateRow(row.id, 'isReasonable', v)">
              <el-option value="合理" label="合理" />
              <el-option value="基本合理" label="基本合理" />
              <el-option value="不合理" label="不合理" />
            </el-select>
            <span v-else>{{ row.isReasonable || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计结论" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.auditConclusion" type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }" placeholder="审计结论..."
              @update:model-value="(v: string) => updateRow(row.id, 'auditConclusion', v)" />
            <span v-else>{{ row.auditConclusion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险等级" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.riskLevel" size="small"
              style="width:100%" placeholder="等级"
              @change="(v: string) => updateRow(row.id, 'riskLevel', v)">
              <el-option value="高" label="高" />
              <el-option value="中" label="中" />
              <el-option value="低" label="低" />
            </el-select>
            <span v-else>{{ row.riskLevel || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
            <el-input v-else-if="!isReadonly" v-model="row.indexRef" size="small"
              placeholder="索引" @change="() => updateRow(row.id, 'indexRef', row.indexRef)" />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              placeholder="备注..."
              @update:model-value="(v: string) => updateRow(row.id, 'remark', v)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 编制提示 details 折叠 -->
    <details class="g6-guide-details">
      <summary>📋 编制提示</summary>
      <div class="g6-guide-content">
        <p>1. PD(违约概率)：验证数据来源(外部评级/内部模型/迁移矩阵)、估计方法(历史法/TTC→PIT转换)、前瞻性调整(宏观经济变量)</p>
        <p>2. LGD(违约损失率)：检查抵押品覆盖率、回收率假设、清偿时间折现、优先/次级债结构差异</p>
        <p>3. EAD(违约风险暴露)：确认余额口径(表内+表外×CCF)、利息应计、提前还款假设</p>
        <p>4. 折现率：原则上使用原始实际利率；浮动利率可用当前实际利率近似；如使用替代利率需说明合理性</p>
        <p>5. 前瞻性信息：检查宏观经济情景设置(至少基准/乐观/悲观)、概率权重分配合理性、经济变量选择与模型敏感度</p>
        <p>6. 参考材料：CAS22/IFRS9减值要求、中证协金融工具减值指引、企业ECL模型文档</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabEclMeasurement.vue — G6-13 预期信用损失计量测试
 *
 * Spec: .kiro/specs/g6-other-bond-investment-ecl/ Task 8.1
 * Requirements: 4.1, 4.2, 4.3
 *
 * 49行×10列问卷式表格，5个section:
 * (一) PD（违约概率） — 数据来源/估计方法/前瞻性调整
 * (二) LGD（违约损失率） — 抵押品/回收率/优先级
 * (三) EAD（违约风险暴露） — 余额口径/表外承诺
 * (四) 折现率 — 原始实际利率/近似利率
 * (五) 前瞻性信息 — 宏观经济情景/权重
 *
 * 顶部方法论上下文（琥珀色：ECL三要素定义）
 * 每section标题右侧AI按钮(ecl-measurement-conclusion)
 * inject('openReviewDialog') for 复核按钮
 * GtIndexChip索引列
 * 底部编制提示details折叠
 */
import { ref, inject, watch, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useG6EclFormData } from '../../composables/useG6EclFormData'
import type { EclCheckRow } from '../../composables/useG6EclFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── 复核对话 inject ───
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

function openReview(sectionId: string): void {
  openReviewDialog(sectionId)
}

// ─── 数据层 ───
const formData = useG6EclFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── 预定义检查行（49行 across 5 sections） ───

/** (一) PD（违约概率）— 12行 */
const DEFAULT_PD_ROWS: EclCheckRow[] = [
  { id: 'pd-1', seq: 1, checkArea: '数据来源', checkItem: 'PD数据来源', auditRequirement: '检查企业PD值来源是否可靠（外部评级机构/内部信用模型/迁移矩阵）', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'pd-2', seq: 2, checkArea: '数据来源', checkItem: '历史违约数据', auditRequirement: '验证历史违约数据的完整性、时间跨度（≥1个完整经济周期）及样本代表性', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'pd-3', seq: 3, checkArea: '数据来源', checkItem: '外部评级映射', auditRequirement: '如使用外部评级机构PD，检查评级映射表的合理性及更新频率', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'pd-4', seq: 4, checkArea: '估计方法', checkItem: 'PD估计模型', auditRequirement: '评估PD模型（如Logistic回归/Markov链/CreditMetrics）是否适用于债券投资', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'pd-5', seq: 5, checkArea: '估计方法', checkItem: 'TTC→PIT转换', auditRequirement: '如将跨周期PD(TTC)转换为时点PD(PIT)，验证转换方法及宏观经济调整因子', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'pd-6', seq: 6, checkArea: '估计方法', checkItem: '期限结构', auditRequirement: '检查PD期限结构（1年期→整个存续期）的推导方法是否合理', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'pd-7', seq: 7, checkArea: '估计方法', checkItem: '违约定义', auditRequirement: '确认企业采用的违约定义是否符合CAS22要求（逾期90天可推翻假设）', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'pd-8', seq: 8, checkArea: '前瞻性调整', checkItem: '宏观经济变量', auditRequirement: '检查前瞻性调整所选宏观经济变量（GDP/CPI/失业率等）与PD的相关性', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'pd-9', seq: 9, checkArea: '前瞻性调整', checkItem: '多情景设置', auditRequirement: '验证多情景设置（至少基准/乐观/悲观三种）及概率权重分配的合理性', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'pd-10', seq: 10, checkArea: '前瞻性调整', checkItem: '模型回测', auditRequirement: '检查企业是否定期对PD模型进行回测验证，偏差是否在可接受范围内', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'pd-11', seq: 11, checkArea: '前瞻性调整', checkItem: '行业/区域差异', auditRequirement: '评估PD是否区分行业、区域等维度，避免组合内信用风险异质性', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'pd-12', seq: 12, checkArea: '前瞻性调整', checkItem: '管理层覆盖', auditRequirement: '如存在管理层对模型PD的人工覆盖(overlay)，评估覆盖理由及金额合理性', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
]

/** (二) LGD（违约损失率）— 10行 */
const DEFAULT_LGD_ROWS: EclCheckRow[] = [
  { id: 'lgd-1', seq: 1, checkArea: '抵押品', checkItem: '抵押品识别', auditRequirement: '确认企业是否完整识别了所有有效抵押品及其类型（房产/股权/票据等）', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'lgd-2', seq: 2, checkArea: '抵押品', checkItem: '抵押品估值', auditRequirement: '检查抵押品估值方法（市场法/收益法）及估值日期的时效性', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'lgd-3', seq: 3, checkArea: '抵押品', checkItem: '折扣率(Haircut)', auditRequirement: '评估抵押品折扣率是否反映了变现难度、市场波动及处置成本', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'lgd-4', seq: 4, checkArea: '回收率', checkItem: '历史回收数据', auditRequirement: '验证历史回收率数据的样本量、时间跨度及代表性', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'lgd-5', seq: 5, checkArea: '回收率', checkItem: '回收时间假设', auditRequirement: '检查从违约到最终回收的时间假设是否合理，折现处理是否正确', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'lgd-6', seq: 6, checkArea: '回收率', checkItem: '处置费用', auditRequirement: '确认LGD计算中是否扣除了合理的处置费用（法律/评估/拍卖等）', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'lgd-7', seq: 7, checkArea: '优先级', checkItem: '债权优先级', auditRequirement: '核实债券的清偿优先级（优先级/次级/劣后）对LGD的影响', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'lgd-8', seq: 8, checkArea: '优先级', checkItem: '交叉违约条款', auditRequirement: '检查是否考虑了交叉违约条款对LGD的影响', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'lgd-9', seq: 9, checkArea: '优先级', checkItem: '经济下行调整', auditRequirement: '评估LGD是否进行了经济下行情景调整（Downturn LGD）', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'lgd-10', seq: 10, checkArea: '优先级', checkItem: 'LGD上下限', auditRequirement: '验证LGD取值是否在合理范围内（0%~100%），极端值是否有充分依据', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
]

/** (三) EAD（违约风险暴露）— 9行 */
const DEFAULT_EAD_ROWS: EclCheckRow[] = [
  { id: 'ead-1', seq: 1, checkArea: '余额口径', checkItem: '表内敞口确认', auditRequirement: '确认EAD的表内敞口口径（摊余成本/公允价值/账面余额）与会计政策一致', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'ead-2', seq: 2, checkArea: '余额口径', checkItem: '利息应计', auditRequirement: '检查EAD是否包含应计利息（已计入摊余成本部分）', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'ead-3', seq: 3, checkArea: '余额口径', checkItem: '减值准备扣除', auditRequirement: '确认EAD计算是否在扣除减值准备前的总额基础上进行', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'ead-4', seq: 4, checkArea: '表外承诺', checkItem: '信用转换因子(CCF)', auditRequirement: '如有表外承诺（如未使用授信额度），检查CCF取值依据', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'ead-5', seq: 5, checkArea: '表外承诺', checkItem: '提前还款假设', auditRequirement: '评估是否考虑了债务人提前还款行为对EAD的影响', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'ead-6', seq: 6, checkArea: '表外承诺', checkItem: '到期日确定', auditRequirement: '确认存续期的确定方法（合同到期日/行为到期日/提前终止条款）', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'ead-7', seq: 7, checkArea: '表外承诺', checkItem: 'EAD时点一致性', auditRequirement: '核实EAD与PD的时点口径一致（均为违约时点预期值）', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'ead-8', seq: 8, checkArea: '表外承诺', checkItem: '分期偿还考虑', auditRequirement: '对于分期偿还型债券，检查EAD是否反映了本金递减结构', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'ead-9', seq: 9, checkArea: '表外承诺', checkItem: '币种风险', auditRequirement: '如涉及外币计价债券，确认EAD是否考虑了汇率变动风险', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
]

/** (四) 折现率 — 8行 */
const DEFAULT_DISCOUNT_RATE_ROWS: EclCheckRow[] = [
  { id: 'dr-1', seq: 1, checkArea: '折现率选择', checkItem: '原始实际利率', auditRequirement: '确认ECL折现使用的是初始确认时确定的原始实际利率（EIR）', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'dr-2', seq: 2, checkArea: '折现率选择', checkItem: '浮动利率处理', auditRequirement: '对浮动利率债券，检查是否使用当前实际利率进行折现', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'dr-3', seq: 3, checkArea: '折现率选择', checkItem: '近似利率使用', auditRequirement: '如使用替代/近似利率，评估其与原始EIR的差异及合理性说明', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'dr-4', seq: 4, checkArea: '折现率选择', checkItem: '信用调整忽略', auditRequirement: '确认折现率不包含信用风险溢价（避免双重计算）', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'dr-5', seq: 5, checkArea: '折现计算', checkItem: '折现期限', auditRequirement: '检查折现期限是否与现金流短缺发生的预期时点一致', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'dr-6', seq: 6, checkArea: '折现计算', checkItem: '折现频率', auditRequirement: '确认折现频率（年/半年/季度）与付息频率和PD期限结构匹配', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'dr-7', seq: 7, checkArea: '折现计算', checkItem: '多笔汇总折现', auditRequirement: '对于组合评估，检查加权平均折现率的计算方法是否合理', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'dr-8', seq: 8, checkArea: '折现计算', checkItem: '折现影响测试', auditRequirement: '评估折现对ECL金额的影响程度，短期限债券可豁免折现', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
]

/** (五) 前瞻性信息 — 10行 */
const DEFAULT_FORWARD_LOOKING_ROWS: EclCheckRow[] = [
  { id: 'fl-1', seq: 1, checkArea: '情景设置', checkItem: '情景数量', auditRequirement: '确认企业设置了至少3种宏观经济情景（基准/乐观/悲观）', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'fl-2', seq: 2, checkArea: '情景设置', checkItem: '情景定义', auditRequirement: '评估各情景的经济假设是否具有内在一致性和区分度', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'fl-3', seq: 3, checkArea: '情景设置', checkItem: '概率权重', auditRequirement: '检查各情景概率权重的确定依据（专家判断/历史频率/市场隐含）', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'fl-4', seq: 4, checkArea: '情景设置', checkItem: '权重合理性', auditRequirement: '验证概率权重之和=100%，各情景权重与当前经济环境匹配', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'fl-5', seq: 5, checkArea: '宏观变量', checkItem: '变量选择', auditRequirement: '评估所选宏观经济变量（GDP/CPI/利率/失业率等）与信用风险的相关性', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'fl-6', seq: 6, checkArea: '宏观变量', checkItem: '变量预测值', auditRequirement: '验证宏观变量预测值来源（央行/IMF/市场共识）的权威性和时效性', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'fl-7', seq: 7, checkArea: '宏观变量', checkItem: '预测期限', auditRequirement: '确认前瞻性信息的预测期限覆盖了金融资产的预期存续期', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'fl-8', seq: 8, checkArea: '模型敏感度', checkItem: '敏感性分析', auditRequirement: '检查企业是否进行了ECL对关键宏观变量的敏感性分析', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'fl-9', seq: 9, checkArea: '模型敏感度', checkItem: '非线性效应', auditRequirement: '评估模型是否捕捉了经济下行时ECL的非线性加速增长效应', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
  { id: 'fl-10', seq: 10, checkArea: '模型敏感度', checkItem: '年度更新', auditRequirement: '确认前瞻性信息及情景权重是否在报告期末进行了重新评估和更新', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' },
]

// ─── 响应式数据（5 section） ───
const pdSection = ref<EclCheckRow[]>([...DEFAULT_PD_ROWS])
const lgdSection = ref<EclCheckRow[]>([...DEFAULT_LGD_ROWS])
const eadSection = ref<EclCheckRow[]>([...DEFAULT_EAD_ROWS])
const discountRateSection = ref<EclCheckRow[]>([...DEFAULT_DISCOUNT_RATE_ROWS])
const forwardLookingSection = ref<EclCheckRow[]>([...DEFAULT_FORWARD_LOOKING_ROWS])

// ─── 数据加载 ───
onMounted(async () => {
  await formData.loadAll()
  initFromData()
})

watch(() => props.htmlData, (newData) => {
  if (newData) initFromData()
})

function initFromData(): void {
  const content = formData.parseContent()
  const ecl = content.eclMeasurement
  if (!ecl) return

  if (ecl.pdSection?.length) pdSection.value = ecl.pdSection
  if (ecl.lgdSection?.length) lgdSection.value = ecl.lgdSection
  if (ecl.eadSection?.length) eadSection.value = ecl.eadSection
  if (ecl.discountRateSection?.length) discountRateSection.value = ecl.discountRateSection
  if (ecl.forwardLookingSection?.length) forwardLookingSection.value = ecl.forwardLookingSection
}

// ─── 保存逻辑 ───
function saveAll(): void {
  formData.debouncedSave('G6-13-ecl-measurement', {
    conclusion: JSON.stringify({
      pdSection: pdSection.value,
      lgdSection: lgdSection.value,
      eadSection: eadSection.value,
      discountRateSection: discountRateSection.value,
      forwardLookingSection: forwardLookingSection.value,
    }),
  })
}

// ─── 行更新（统一入口） ───
function updateRow(rowId: string, field: keyof EclCheckRow, value: any): void {
  // 查找所有section中的目标行
  const allSections = [pdSection, lgdSection, eadSection, discountRateSection, forwardLookingSection]
  for (const section of allSections) {
    const row = section.value.find((r) => r.id === rowId)
    if (row) {
      ;(row as any)[field] = value
      break
    }
  }
  saveAll()
}

// ─── AI辅助 ───
async function handleAi(section: string): Promise<void> {
  try {
    const { data } = await http.post(
      `/api/workpapers/${props.wpId}/g6-ecl/ai/ecl-measurement-conclusion`,
      { section, projectId: props.projectId },
      { _silent: true } as any,
    )
    const result = data?.data?.conclusion || data?.conclusion
    if (result) {
      ElMessage.success('AI结论已生成')
      // 将AI结论填入对应section最后一行的auditConclusion
      const sectionMap: Record<string, typeof pdSection> = {
        pd: pdSection, lgd: lgdSection, ead: eadSection,
        'discount-rate': discountRateSection, 'forward-looking': forwardLookingSection,
      }
      const target = sectionMap[section]
      if (target && target.value.length > 0) {
        const lastRow = target.value[target.value.length - 1]
        lastRow.auditConclusion = result
        saveAll()
      }
    }
  } catch {
    ElMessage.info(`AI辅助(${section})功能将在AI模块完成后启用`)
  }
}

// ─── 暴露序列化接口供父组件保存使用 ─────────────────────────
defineExpose({
  toJSON: () => ({
    pdSection: pdSection.value,
    lgdSection: lgdSection.value,
    eadSection: eadSection.value,
    discountRateSection: discountRateSection.value,
    forwardLookingSection: forwardLookingSection.value,
  }),
})
</script>

<style scoped>
.g6-tab-ecl-measurement {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景）─── */
.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.8;
}

.methodology-context p {
  margin: 0 0 4px;
}

.methodology-context ul {
  margin: 0;
  padding-left: 18px;
}

.methodology-context li {
  margin-bottom: 2px;
}

/* ─── Section卡片 ─── */
.section-card {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-title {
  font-weight: 600;
  font-size: 14px;
}

.section-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* ─── 表格 ─── */
.ecl-table {
  font-size: var(--wp-font-size, 13px);
}

.audit-req-text {
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
}

/* ─── 编制提示 ─── */
.g6-guide-details {
  margin-top: 16px;
}

.g6-guide-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  font-weight: 600;
}

.g6-guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}

.g6-guide-content p {
  margin: 0;
}
</style>
