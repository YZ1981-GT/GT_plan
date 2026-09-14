<template>
  <div class="g4-sppi-extra">
    <!-- (三) -->
    <div class="section-header mt24">
      <h3 class="section-title">（三）优先股、永续债</h3>
      <el-button size="small" @click="emit('review', 'G4-6-优先股永续债')">复核</el-button>
    </div>
    <div v-for="tip in SECTION_TIPS.preferred_perpetual" :key="tip.id" class="tip-banner" :class="`tip-${tip.accent}`">
      <strong>{{ tip.title }}</strong>
      <p v-for="(para, i) in tip.paragraphs" :key="i">{{ para }}</p>
    </div>
    <el-table :data="preferredItems" border stripe size="small" empty-text="暂无数据，点击下方新增">
      <el-table-column label="投资项目" min-width="130">
        <template #default="{ row }">
          <el-input v-model="row.investProject" size="small" :disabled="isReadonly" @change="logic.updatePreferredItem(row.id, { investProject: row.investProject })" />
        </template>
      </el-table-column>
      <el-table-column label="投资总额" min-width="100">
        <template #default="{ row }">
          <WpAmountInput v-model="row.totalAmount" size="small" :disabled="isReadonly" @change="logic.updatePreferredItem(row.id, { totalAmount: row.totalAmount })" />
        </template>
      </el-table-column>
      <el-table-column label="期限" min-width="90">
        <template #default="{ row }">
          <el-input v-model="row.term" size="small" :disabled="isReadonly" placeholder="如3+N年" @change="logic.updatePreferredItem(row.id, { term: row.term })" />
        </template>
      </el-table-column>
      <el-table-column label="票面利率/重置" min-width="130">
        <template #default="{ row }">
          <el-input v-model="row.couponRate" size="small" :disabled="isReadonly" @change="logic.updatePreferredItem(row.id, { couponRate: row.couponRate })" />
        </template>
      </el-table-column>
      <el-table-column label="递延付息" width="80" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.deferredInterest" size="small" :disabled="isReadonly" @change="logic.updatePreferredItem(row.id, { deferredInterest: row.deferredInterest })" />
        </template>
      </el-table-column>
      <el-table-column label="利息累积" width="80" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.interestCumulative" size="small" :disabled="isReadonly" @change="logic.updatePreferredItem(row.id, { interestCumulative: row.interestCumulative })" />
        </template>
      </el-table-column>
      <el-table-column label="利率跳升" min-width="110">
        <template #default="{ row }">
          <el-input v-model="row.rateStepUp" size="small" :disabled="isReadonly" @change="logic.updatePreferredItem(row.id, { rateStepUp: row.rateStepUp })" />
        </template>
      </el-table-column>
      <el-table-column label="可转股" width="80" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.convertibleToEquity" size="small" :disabled="isReadonly" @change="logic.updatePreferredItem(row.id, { convertibleToEquity: row.convertibleToEquity })" />
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="120">
        <template #default="{ row }">
          <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" @change="logic.updatePreferredItem(row.id, { conclusion: row.conclusion })">
            <el-option v-for="opt in SPPI_CONCLUSION_OPTIONS" :key="String(opt.value)" :label="opt.label" :value="opt.value" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="判断说明" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.judgmentNote" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" :disabled="isReadonly" @change="logic.updatePreferredItem(row.id, { judgmentNote: row.judgmentNote })" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" align="center">
        <template #default="{ row }">
          <el-button type="danger" link size="small" :disabled="isReadonly" @click="logic.removePreferredItem(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="logic.addPreferredItem()">+ 新增优先股/永续债</el-button>
    </div>

    <!-- (四) -->
    <div class="section-header mt24">
      <h3 class="section-title">（四）可转换债券</h3>
      <el-button size="small" @click="emit('review', 'G4-6-可转换债券')">复核</el-button>
    </div>
    <div v-for="tip in SECTION_TIPS.convertible" :key="tip.id" class="tip-banner" :class="`tip-${tip.accent}`">
      <strong>{{ tip.title }}</strong>
      <p v-for="(para, i) in tip.paragraphs" :key="i">{{ para }}</p>
    </div>
    <el-table :data="convertibleItems" border stripe size="small" empty-text="暂无数据，点击下方新增">
      <el-table-column label="投资项目" min-width="130">
        <template #default="{ row }">
          <el-input v-model="row.investProject" size="small" :disabled="isReadonly" @change="logic.updateConvertibleItem(row.id, { investProject: row.investProject })" />
        </template>
      </el-table-column>
      <el-table-column label="投资总额" min-width="100">
        <template #default="{ row }">
          <WpAmountInput v-model="row.totalAmount" size="small" :disabled="isReadonly" @change="logic.updateConvertibleItem(row.id, { totalAmount: row.totalAmount })" />
        </template>
      </el-table-column>
      <el-table-column label="期限" min-width="80">
        <template #default="{ row }">
          <el-input v-model="row.term" size="small" :disabled="isReadonly" @change="logic.updateConvertibleItem(row.id, { term: row.term })" />
        </template>
      </el-table-column>
      <el-table-column label="票面利率" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.couponRate" size="small" :disabled="isReadonly" @change="logic.updateConvertibleItem(row.id, { couponRate: row.couponRate })" />
        </template>
      </el-table-column>
      <el-table-column label="初始转股价" min-width="100">
        <template #default="{ row }">
          <el-input v-model="row.conversionPrice" size="small" :disabled="isReadonly" @change="logic.updateConvertibleItem(row.id, { conversionPrice: row.conversionPrice })" />
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="120">
        <template #default="{ row }">
          <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" @change="logic.updateConvertibleItem(row.id, { conclusion: row.conclusion })">
            <el-option v-for="opt in SPPI_CONCLUSION_OPTIONS" :key="String(opt.value)" :label="opt.label" :value="opt.value" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="判断说明" min-width="200">
        <template #default="{ row }">
          <el-input v-model="row.judgmentNote" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" :disabled="isReadonly" @change="logic.updateConvertibleItem(row.id, { judgmentNote: row.judgmentNote })" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" align="center">
        <template #default="{ row }">
          <el-button type="danger" link size="small" :disabled="isReadonly" @click="logic.removeConvertibleItem(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="logic.addConvertibleItem()">+ 新增可转换债券</el-button>
    </div>

    <!-- (五) -->
    <div class="section-header mt24">
      <h3 class="section-title">（五）项目收益债、信托计划</h3>
      <el-button size="small" @click="emit('review', 'G4-6-项目收益债信托')">复核</el-button>
    </div>
    <div v-for="tip in SECTION_TIPS.project_trust" :key="tip.id" class="tip-banner" :class="`tip-${tip.accent}`">
      <strong>{{ tip.title }}</strong>
      <p v-for="(para, i) in tip.paragraphs" :key="i">{{ para }}</p>
    </div>
    <el-table :data="projectTrustItems" border stripe size="small" empty-text="暂无数据，点击下方新增">
      <el-table-column label="投资项目" min-width="140">
        <template #default="{ row }">
          <el-input v-model="row.investProject" size="small" :disabled="isReadonly" @change="logic.updateProjectTrustItem(row.id, { investProject: row.investProject })" />
        </template>
      </el-table-column>
      <el-table-column label="投资总额" min-width="100">
        <template #default="{ row }">
          <WpAmountInput v-model="row.totalAmount" size="small" :disabled="isReadonly" @change="logic.updateProjectTrustItem(row.id, { totalAmount: row.totalAmount })" />
        </template>
      </el-table-column>
      <el-table-column label="期限" min-width="80">
        <template #default="{ row }">
          <el-input v-model="row.term" size="small" :disabled="isReadonly" @change="logic.updateProjectTrustItem(row.id, { term: row.term })" />
        </template>
      </el-table-column>
      <el-table-column label="票面利率" min-width="90">
        <template #default="{ row }">
          <el-input v-model="row.couponRate" size="small" :disabled="isReadonly" @change="logic.updateProjectTrustItem(row.id, { couponRate: row.couponRate })" />
        </template>
      </el-table-column>
      <el-table-column label="基础资产现金流" min-width="150">
        <template #default="{ row }">
          <el-input v-model="row.underlyingCashFlow" size="small" :disabled="isReadonly" @change="logic.updateProjectTrustItem(row.id, { underlyingCashFlow: row.underlyingCashFlow })" />
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="120">
        <template #default="{ row }">
          <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" @change="logic.updateProjectTrustItem(row.id, { conclusion: row.conclusion })">
            <el-option v-for="opt in SPPI_CONCLUSION_OPTIONS" :key="String(opt.value)" :label="opt.label" :value="opt.value" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="判断说明" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.judgmentNote" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" :disabled="isReadonly" @change="logic.updateProjectTrustItem(row.id, { judgmentNote: row.judgmentNote })" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" align="center">
        <template #default="{ row }">
          <el-button type="danger" link size="small" :disabled="isReadonly" @click="logic.removeProjectTrustItem(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="logic.addProjectTrustItem()">+ 新增项目收益债/信托</el-button>
    </div>

    <!-- (六) -->
    <div class="section-header mt24">
      <h3 class="section-title">（六）资产支持证券</h3>
      <el-button size="small" @click="emit('review', 'G4-6-资产支持证券')">复核</el-button>
    </div>
    <div v-for="tip in SECTION_TIPS.abs" :key="tip.id" class="tip-banner" :class="`tip-${tip.accent}`">
      <strong>{{ tip.title }}</strong>
      <p v-for="(para, i) in tip.paragraphs" :key="i">{{ para }}</p>
    </div>
    <el-table :data="absItems" border stripe size="small" empty-text="暂无数据，点击下方新增">
      <el-table-column label="投资项目" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.investProject" size="small" :disabled="isReadonly" @change="logic.updateAbsItem(row.id, { investProject: row.investProject })" />
        </template>
      </el-table-column>
      <el-table-column label="投资份额" min-width="100">
        <template #default="{ row }">
          <el-input-number v-model="row.shareAmount" size="small" :controls="false" :disabled="isReadonly" @change="logic.updateAbsItem(row.id, { shareAmount: row.shareAmount })" />
        </template>
      </el-table-column>
      <el-table-column label="期限" min-width="80">
        <template #default="{ row }">
          <el-input v-model="row.term" size="small" :disabled="isReadonly" @change="logic.updateAbsItem(row.id, { term: row.term })" />
        </template>
      </el-table-column>
      <el-table-column label="票面利率" min-width="90">
        <template #default="{ row }">
          <el-input v-model="row.couponRate" size="small" :disabled="isReadonly" @change="logic.updateAbsItem(row.id, { couponRate: row.couponRate })" />
        </template>
      </el-table-column>
      <el-table-column label="级次" min-width="90">
        <template #default="{ row }">
          <el-select v-model="row.tranche" size="small" :disabled="isReadonly" clearable allow-create filterable @change="logic.updateAbsItem(row.id, { tranche: row.tranche })">
            <el-option label="优先级" value="优先级" />
            <el-option label="中间级" value="中间级" />
            <el-option label="次级" value="次级" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="基础资产现金流" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.underlyingCashFlow" size="small" :disabled="isReadonly" @change="logic.updateAbsItem(row.id, { underlyingCashFlow: row.underlyingCashFlow })" />
        </template>
      </el-table-column>
      <el-table-column label="信用风险分担" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.creditRiskSharing" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" :disabled="isReadonly" @change="logic.updateAbsItem(row.id, { creditRiskSharing: row.creditRiskSharing })" />
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="120">
        <template #default="{ row }">
          <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" @change="logic.updateAbsItem(row.id, { conclusion: row.conclusion })">
            <el-option v-for="opt in SPPI_CONCLUSION_OPTIONS" :key="String(opt.value)" :label="opt.label" :value="opt.value" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="判断说明" min-width="150">
        <template #default="{ row }">
          <el-input v-model="row.judgmentNote" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" :disabled="isReadonly" @change="logic.updateAbsItem(row.id, { judgmentNote: row.judgmentNote })" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" align="center">
        <template #default="{ row }">
          <el-button type="danger" link size="small" :disabled="isReadonly" @click="logic.removeAbsItem(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="logic.addAbsItem()">+ 新增资产支持证券</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * G4-6 部分(三)～(六)：优先股永续债 / 可转债 / 项目信托 / ABS
 */
import { SECTION_TIPS } from '@/composables/g4SppiGuidance'
import { SPPI_CONCLUSION_OPTIONS } from '@/composables/useG4SppiTest'
import type {
  PreferredPerpetualItem,
  ConvertibleBondItem,
  ProjectTrustItem,
  AbsItem,
} from '@/composables/useG4SppiTest'

defineProps<{
  preferredItems: PreferredPerpetualItem[]
  convertibleItems: ConvertibleBondItem[]
  projectTrustItems: ProjectTrustItem[]
  absItems: AbsItem[]
  isReadonly: boolean
  logic: {
    updatePreferredItem: (id: string, patch: Partial<PreferredPerpetualItem>) => void
    addPreferredItem: () => Promise<void>
    removePreferredItem: (id: string) => void
    updateConvertibleItem: (id: string, patch: Partial<ConvertibleBondItem>) => void
    addConvertibleItem: () => Promise<void>
    removeConvertibleItem: (id: string) => void
    updateProjectTrustItem: (id: string, patch: Partial<ProjectTrustItem>) => void
    addProjectTrustItem: () => Promise<void>
    removeProjectTrustItem: (id: string) => void
    updateAbsItem: (id: string, patch: Partial<AbsItem>) => void
    addAbsItem: () => Promise<void>
    removeAbsItem: (id: string) => void
  }
}>()

const emit = defineEmits<{ (e: 'review', id: string): void }>()
</script>

<style scoped>
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; }
.mt24 { margin-top: 24px; }
.table-actions { display: flex; gap: 8px; margin: 8px 0 16px; }
.tip-banner { border-radius: 4px; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; line-height: 1.6; }
.tip-banner p { margin: 4px 0 0; }
.tip-blue { background: #ecf5ff; border-left: 3px solid #409eff; color: #1d39c4; }
.tip-red { background: #fef0f0; border-left: 3px solid #f56c6c; color: #c45656; }
.tip-amber { background: #fdf6ec; border-left: 3px solid #e6a23c; color: #8b6914; }
</style>
