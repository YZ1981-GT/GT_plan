<template>
  <div class="l5-tab-adjudication">
    <!-- ═══ 标题 + DualMode + 导入导出 + 复核 + 保存 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L5-1 长期应付款审定表</h3>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" plain :loading="adjPullGross.loading.value" @click="openBringInGross">
          <el-icon><Download /></el-icon> 带入调整(原值)
        </el-button>
        <el-button size="small" type="primary" plain :loading="adjPullUnrec.loading.value" @click="openBringInUnrec">
          <el-icon><Download /></el-icon> 带入调整(未确认)
        </el-button>
        <el-segmented v-model="dualMode.mode.value" :options="dualMode.modeOptions.value" size="small" @change="(val: any) => dualMode.switchMode(val)" />
        <el-dropdown trigger="click" @command="handleImportExport">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleReview"><el-icon><Check /></el-icon> 复核</el-button>
        <el-button type="primary" size="small" :loading="isSaving" @click="handleSave">保存</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title>审计目标（认定）</template>
      <ol class="ao-list">
        <li><b>完整性：</b>所有长期应付款均已记录；</li>
        <li><b>存在与义务：</b>记录的长期应付款确实存在且为被审计单位义务；</li>
        <li><b>计价与分摊：</b>以摊余成本（原值 − 未确认融资费用）恰当列示，实际利率法摊销正确；</li>
        <li><b>列报与披露：</b>一年内到期部分重分类至流动负债，关联方交易公允披露。</li>
      </ol>
    </el-alert>

    <div class="methodology-context">
      <div class="methodology-text">
        <strong>双期审定 · 三区段（2701）：</strong>
        一、原值（长期应付款贷方）；二、未确认融资费用（借方备抵）；三、净值 = 原值 − 未确认融资费用（逐行）。
        期初/期末各按「未审 → 账项调整 → 重分类调整 → 审定数」列示，审定数 = 未审 + 账项调整 + 重分类调整；
        最终审定数 = 审定数 − 一年内到期（重分类至流动负债）。变动率超 30% 需在原因分析栏说明。
      </div>
    </div>

    <!-- ═══ 一、原值 ═══ -->
    <div class="block-section">
      <h4 class="block-title">一、原值（长期应付款 · 贷方/负债类）</h4>
      <el-table :data="computedGrossRows" border size="small" style="width:100%">
        <el-table-column prop="itemName" label="项目" min-width="170" fixed>
          <template #default="{ row }"><el-tag size="small" type="info" style="margin-right:4px">{{ row.category }}</el-tag>{{ row.itemName }}</template>
        </el-table-column>
        <el-table-column label="期初数" align="center">
          <el-table-column label="未审数" width="100" align="right"><template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.beginUnadjusted" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onGross(row.key,'beginUnadjusted',v??0)" /><span v-else>{{ fmt(row.beginUnadjusted) }}</span></template></el-table-column>
          <el-table-column label="账项调整" width="95" align="right"><template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.beginAje" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onGross(row.key,'beginAje',v??0)" /><span v-else>{{ fmt(row.beginAje) }}</span></template></el-table-column>
          <el-table-column label="重分类调整" width="95" align="right"><template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.beginRje" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onGross(row.key,'beginRje',v??0)" /><span v-else>{{ fmt(row.beginRje) }}</span></template></el-table-column>
          <el-table-column label="审定数" width="100" align="right"><template #default="{ row }"><span class="formula-value">{{ fmt(row.beginAudited) }}</span></template></el-table-column>
          <el-table-column label="减一年内到期" width="100" align="right"><template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.beginCurrent" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onGross(row.key,'beginCurrent',v??0)" /><span v-else>{{ fmt(row.beginCurrent) }}</span></template></el-table-column>
          <el-table-column label="最终审定数" width="100" align="right"><template #default="{ row }"><span class="formula-value">{{ fmt(row.beginDisclosed) }}</span></template></el-table-column>
        </el-table-column>
        <el-table-column label="期末数" align="center">
          <el-table-column label="未审数" width="100" align="right"><template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.endUnadjusted" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onGross(row.key,'endUnadjusted',v??0)" /><span v-else>{{ fmt(row.endUnadjusted) }}</span></template></el-table-column>
          <el-table-column label="账项调整" width="95" align="right"><template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.endAje" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onGross(row.key,'endAje',v??0)" /><span v-else>{{ fmt(row.endAje) }}</span></template></el-table-column>
          <el-table-column label="重分类调整" width="95" align="right"><template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.endRje" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onGross(row.key,'endRje',v??0)" /><span v-else>{{ fmt(row.endRje) }}</span></template></el-table-column>
          <el-table-column label="审定数" width="100" align="right"><template #default="{ row }"><span class="formula-value">{{ fmt(row.endAudited) }}</span></template></el-table-column>
          <el-table-column label="减一年内到期" width="100" align="right"><template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.endCurrent" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onGross(row.key,'endCurrent',v??0)" /><span v-else>{{ fmt(row.endCurrent) }}</span></template></el-table-column>
          <el-table-column label="最终审定数" width="100" align="right"><template #default="{ row }"><span class="formula-value">{{ fmt(row.endDisclosed) }}</span></template></el-table-column>
        </el-table-column>
        <el-table-column label="本期审定较期初" align="center">
          <el-table-column label="变动额" width="100" align="right"><template #default="{ row }"><span class="formula-value" :class="chg(row.auditedChange)">{{ fmt(row.auditedChange) }}</span></template></el-table-column>
          <el-table-column label="变动率" width="85" align="right"><template #default="{ row }"><span class="formula-value" :class="{ 'text-warning': Math.abs(row.auditedRate) > 0.3 }">{{ fmtRate(row.auditedRate) }}</span></template></el-table-column>
        </el-table-column>
        <el-table-column label="原因分析" min-width="150">
          <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.reason" size="small" placeholder="变动率超30%需说明" @input="(v:string)=>onGrossReason(row.key,v)" /><span v-else>{{ row.reason || '-' }}</span></template>
        </el-table-column>
      </el-table>
      <div class="l5-total-bar"><span class="l5-total-label">原值合计</span><span class="l5-total-figs">期末审定 {{ fmt(grossTotal.endAudited) }} ｜ 最终审定 {{ fmt(grossTotal.endDisclosed) }} ｜ 变动 {{ fmt(grossTotal.auditedChange) }} ({{ fmtRate(grossTotal.auditedRate) }})</span></div>
    </div>

    <!-- ═══ 二、未确认融资费用 ═══ -->
    <div class="block-section">
      <h4 class="block-title">二、未确认融资费用（借方/负债备抵类）</h4>
      <el-table :data="computedUnrecognizedRows" border size="small" style="width:100%">
        <el-table-column prop="itemName" label="项目" min-width="170" fixed>
          <template #default="{ row }"><el-tag size="small" type="warning" style="margin-right:4px">{{ row.category }}</el-tag>{{ row.itemName }}</template>
        </el-table-column>
        <el-table-column label="期初数" align="center">
          <el-table-column label="未审数" width="100" align="right"><template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.beginUnadjusted" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onUnrec(row.key,'beginUnadjusted',v??0)" /><span v-else>{{ fmt(row.beginUnadjusted) }}</span></template></el-table-column>
          <el-table-column label="账项调整" width="95" align="right"><template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.beginAje" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onUnrec(row.key,'beginAje',v??0)" /><span v-else>{{ fmt(row.beginAje) }}</span></template></el-table-column>
          <el-table-column label="重分类调整" width="95" align="right"><template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.beginRje" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onUnrec(row.key,'beginRje',v??0)" /><span v-else>{{ fmt(row.beginRje) }}</span></template></el-table-column>
          <el-table-column label="审定数" width="100" align="right"><template #default="{ row }"><span class="formula-value">{{ fmt(row.beginAudited) }}</span></template></el-table-column>
          <el-table-column label="减一年内到期" width="100" align="right"><template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.beginCurrent" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onUnrec(row.key,'beginCurrent',v??0)" /><span v-else>{{ fmt(row.beginCurrent) }}</span></template></el-table-column>
          <el-table-column label="最终审定数" width="100" align="right"><template #default="{ row }"><span class="formula-value">{{ fmt(row.beginDisclosed) }}</span></template></el-table-column>
        </el-table-column>
        <el-table-column label="期末数" align="center">
          <el-table-column label="未审数" width="100" align="right"><template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.endUnadjusted" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onUnrec(row.key,'endUnadjusted',v??0)" /><span v-else>{{ fmt(row.endUnadjusted) }}</span></template></el-table-column>
          <el-table-column label="账项调整" width="95" align="right"><template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.endAje" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onUnrec(row.key,'endAje',v??0)" /><span v-else>{{ fmt(row.endAje) }}</span></template></el-table-column>
          <el-table-column label="重分类调整" width="95" align="right"><template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.endRje" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onUnrec(row.key,'endRje',v??0)" /><span v-else>{{ fmt(row.endRje) }}</span></template></el-table-column>
          <el-table-column label="审定数" width="100" align="right"><template #default="{ row }"><span class="formula-value">{{ fmt(row.endAudited) }}</span></template></el-table-column>
          <el-table-column label="减一年内到期" width="100" align="right"><template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.endCurrent" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onUnrec(row.key,'endCurrent',v??0)" /><span v-else>{{ fmt(row.endCurrent) }}</span></template></el-table-column>
          <el-table-column label="最终审定数" width="100" align="right"><template #default="{ row }"><span class="formula-value">{{ fmt(row.endDisclosed) }}</span></template></el-table-column>
        </el-table-column>
        <el-table-column label="本期审定较期初" align="center">
          <el-table-column label="变动额" width="100" align="right"><template #default="{ row }"><span class="formula-value" :class="chg(row.auditedChange)">{{ fmt(row.auditedChange) }}</span></template></el-table-column>
          <el-table-column label="变动率" width="85" align="right"><template #default="{ row }"><span class="formula-value" :class="{ 'text-warning': Math.abs(row.auditedRate) > 0.3 }">{{ fmtRate(row.auditedRate) }}</span></template></el-table-column>
        </el-table-column>
        <el-table-column label="原因分析" min-width="150">
          <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.reason" size="small" placeholder="变动率超30%需说明" @input="(v:string)=>onUnrecReason(row.key,v)" /><span v-else>{{ row.reason || '-' }}</span></template>
        </el-table-column>
      </el-table>
      <div class="l5-total-bar"><span class="l5-total-label">未确认融资费用合计</span><span class="l5-total-figs">期末审定 {{ fmt(unrecognizedTotal.endAudited) }} ｜ 最终审定 {{ fmt(unrecognizedTotal.endDisclosed) }} ｜ 变动 {{ fmt(unrecognizedTotal.auditedChange) }} ({{ fmtRate(unrecognizedTotal.auditedRate) }})</span></div>
    </div>

    <!-- ═══ 三、净值（= 原值 − 未确认，逐行·只读） ═══ -->
    <div class="block-section">
      <h4 class="block-title">三、净值（= 原值 − 未确认融资费用）</h4>
      <el-table :data="computedNetRows" border size="small" style="width:100%">
        <el-table-column prop="label" label="项目" min-width="170" fixed />
        <el-table-column label="期初数" align="center">
          <el-table-column label="未审数" width="100" align="right"><template #default="{ row }">{{ fmt(row.beginUnadjusted) }}</template></el-table-column>
          <el-table-column label="审定数" width="100" align="right"><template #default="{ row }"><span class="formula-value">{{ fmt(row.beginAudited) }}</span></template></el-table-column>
          <el-table-column label="最终审定数" width="100" align="right"><template #default="{ row }"><span class="formula-value">{{ fmt(row.beginDisclosed) }}</span></template></el-table-column>
        </el-table-column>
        <el-table-column label="期末数" align="center">
          <el-table-column label="未审数" width="100" align="right"><template #default="{ row }">{{ fmt(row.endUnadjusted) }}</template></el-table-column>
          <el-table-column label="审定数" width="100" align="right"><template #default="{ row }"><span class="formula-value">{{ fmt(row.endAudited) }}</span></template></el-table-column>
          <el-table-column label="最终审定数" width="100" align="right"><template #default="{ row }"><span class="formula-value">{{ fmt(row.endDisclosed) }}</span></template></el-table-column>
        </el-table-column>
        <el-table-column label="变动额" width="110" align="right"><template #default="{ row }"><span class="formula-value" :class="chg(row.auditedChange)">{{ fmt(row.auditedChange) }}</span></template></el-table-column>
        <el-table-column label="变动率" width="90" align="right"><template #default="{ row }"><span class="formula-value">{{ fmtRate(row.auditedRate) }}</span></template></el-table-column>
      </el-table>
      <div class="l5-total-bar l5-total-bar--hl"><span class="l5-total-label">净值合计</span><span class="l5-total-figs">期末审定 {{ fmt(netTotal.endAudited) }} ｜ 最终审定 {{ fmt(netTotal.endDisclosed) }} ｜ 变动 {{ fmt(netTotal.auditedChange) }} ({{ fmtRate(netTotal.auditedRate) }})</span></div>
    </div>

    <!-- ═══ 与经审计财务报表核对 ═══ -->
    <el-card shadow="never" class="recon-card">
      <template #header><span class="card-title">与经审计财务报表核对</span></template>
      <el-table :data="reconRows" border size="small" style="width:100%">
        <el-table-column prop="label" label="项目" min-width="240" />
        <el-table-column label="期末数（最终审定）" width="220" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.editable && !isReadonly" :model-value="row.value" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>updateSpecialPayable(v??0)" />
            <span v-else class="formula-value">{{ fmt(row.value) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span class="card-title">审计说明</span>
          <el-button size="small" :loading="aiLoading" :disabled="isReadonly" @click="handleAiNote"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" :placeholder="NOTE_PLACEHOLDER" :disabled="isReadonly" @input="(v:string)=>updateText('note', v)" />
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="section-header"><span class="card-title">审计结论</span></div></template>
      <el-input :model-value="conclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="参考：A.未见异常。 B.除上述重大不符事项应作为调整事项予以调整外，其余未见异常。 C.由于存在重大未调整事项，不可确认。" :disabled="isReadonly" @input="(v:string)=>updateText('conclusion', v)" />
    </el-card>

    <details class="l5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>三区段：一、原值 / 二、未确认融资费用 / 三、净值（净值 = 原值 − 未确认，逐行）</li>
        <li>双期结构：期初/期末各含未审、账项调整、重分类调整、审定数、减一年内到期、最终审定数</li>
        <li>按款项类型：应付融资租赁款 / 分期付款方式购入固定资产 / 其他</li>
        <li>财报核对：长期应付款审定数（净值最终审定合计）+ 专项应付款审定数（手填）</li>
        <li>期末审定合计自动回写 TB（2701 原值 + 未确认融资费用）并通知附注组件</li>
        <li>「带入调整」：可从集中登记按科目 2701（原值）/2702（未确认融资费用）拉取调整分录，逐笔分配到各款项类型行的期末账项/重分类调整，带入后审定数自动更新并联动附注</li>
      </ul>
    </details>

    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />

    <AdjudicationBringInDialog
      v-model="bringInGrossVisible"
      :matches="adjPullGross.matches.value"
      :row-options="bringInGrossRowOptions"
      subject-label="2701 长期应付款原值"
      :loading="adjPullGross.loading.value"
      @apply="onBringInGrossApply"
    />
    <AdjudicationBringInDialog
      v-model="bringInUnrecVisible"
      :matches="adjPullUnrec.matches.value"
      :row-options="bringInUnrecRowOptions"
      subject-label="2702 未确认融资费用"
      :loading="adjPullUnrec.loading.value"
      @apply="onBringInUnrecApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * L5TabAdjudication — L5-1 长期应付款审定表（双期结构·三区段，2026-07 复盘重建）
 *
 * 对齐致同源模板：一、原值 / 二、未确认融资费用 / 三、净值（净值=原值−未确认，逐行）；
 * 每区段 期初/期末各(未审/账项调整/重分类/审定/减一年内到期/最终审定) + 本期审定较期初(变动额/率) + 原因分析。
 * 财报核对：长期应付款审定(净值最终审定合计) + 专项应付款审定(手填) + 合计。
 * 自 formData.allResponses hydrate（L5-L5-1-rows JSON，P0 数据丢失已修）+ 回写 TB 2701/未确认融资费用。
 */
import { computed, inject, onMounted, reactive, ref } from 'vue'
import { MagicStick, Check, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useL5FormData } from '../../composables/useL5FormData'
import { useL5DualMode } from '../../composables/useL5DualMode'
import { useL5ImportExport } from '../../composables/useL5ImportExport'
import { useL5Adjudication, type L5AdjudicationData, type L5AdjRow } from '../../composables/useL5Adjudication'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
defineEmits<{ (e: 'navigate', sheetName: string): void }>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

const formData = useL5FormData({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
const dualMode = useL5DualMode({ wpId: computed(() => props.wpId) })
const importExport = useL5ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })

function mkRow(key: string, category: L5AdjRow['category'], itemName: string): L5AdjRow {
  return { key, category, itemName, beginUnadjusted: 0, beginAje: 0, beginRje: 0, beginCurrent: 0, endUnadjusted: 0, endAje: 0, endRje: 0, endCurrent: 0, reason: '' }
}

const adjudicationData: L5AdjudicationData = reactive({
  grossRows: [
    mkRow('g-lease', '融资租赁', '应付融资租赁款'),
    mkRow('g-install', '分期付款', '分期付款方式购入固定资产'),
    mkRow('g-other', '其他', '其他'),
  ],
  unrecognizedRows: [
    mkRow('u-lease', '融资租赁', '应付融资租赁款'),
    mkRow('u-install', '分期付款', '分期付款方式购入固定资产'),
    mkRow('u-other', '其他', '其他'),
  ],
})

const {
  computedGrossRows, computedUnrecognizedRows, computedNetRows,
  grossTotal, unrecognizedTotal, netTotal, netFinalAudited,
  specialPayableAudited, updateSpecialPayable, reconTotal,
  auditNote, conclusion, updateText,
  updateGrossRow, updateUnrecognizedRow, updateGrossReason, updateUnrecognizedReason,
  saveAndWriteback,
} = useL5Adjudication(formData, adjudicationData)

// ─── 行编辑（按 key 定位 index） ─────────────────────────────────────────────

function onGross(key: string, field: string, v: number) {
  const i = adjudicationData.grossRows.findIndex(r => r.key === key)
  if (i >= 0) updateGrossRow(i, field as any, v)
}
function onUnrec(key: string, field: string, v: number) {
  const i = adjudicationData.unrecognizedRows.findIndex(r => r.key === key)
  if (i >= 0) updateUnrecognizedRow(i, field as any, v)
}
function onGrossReason(key: string, v: string) {
  const i = adjudicationData.grossRows.findIndex(r => r.key === key)
  if (i >= 0) updateGrossReason(i, v)
}
function onUnrecReason(key: string, v: string) {
  const i = adjudicationData.unrecognizedRows.findIndex(r => r.key === key)
  if (i >= 0) updateUnrecognizedReason(i, v)
}

// ─── 从集中登记带入调整（双 helper：原值 2701 负债贷方 / 未确认融资费用 2702 备抵借方；带入期末 AJE/RJE） ───
const bringInGrossRows = computed(() =>
  computedGrossRows.value.map((r) => ({ rowKey: r.key, name: r.itemName, aje: r.endAje, rje: r.endRje })),
)
const {
  adjPull: adjPullGross,
  visible: bringInGrossVisible,
  rowOptions: bringInGrossRowOptions,
  open: openBringInGross,
  apply: onBringInGrossApply,
} = useAdjudicationBringIn({
  projectId: computed(() => props.projectId) as any,
  year: useAuditContext().year as any,
  subjectPrefix: '2701',
  direction: 'credit',
  subjectCode: '2701',
  wpCode: 'L5',
  subjectLabel: '长期应付款原值(2701)',
  rows: bringInGrossRows,
  updateCell: (rowKey: string, field: any, value: number) =>
    onGross(rowKey, field === 'rje' ? 'endRje' : 'endAje', value),
  totalAudited: () => grossTotal.value.endAudited,
})

const bringInUnrecRows = computed(() =>
  computedUnrecognizedRows.value.map((r) => ({ rowKey: r.key, name: r.itemName, aje: r.endAje, rje: r.endRje })),
)
const {
  adjPull: adjPullUnrec,
  visible: bringInUnrecVisible,
  rowOptions: bringInUnrecRowOptions,
  open: openBringInUnrec,
  apply: onBringInUnrecApply,
} = useAdjudicationBringIn({
  projectId: computed(() => props.projectId) as any,
  year: useAuditContext().year as any,
  subjectPrefix: '2702',
  direction: 'debit',
  subjectCode: '2702',
  wpCode: 'L5',
  subjectLabel: '未确认融资费用(2702)',
  rows: bringInUnrecRows,
  updateCell: (rowKey: string, field: any, value: number) =>
    onUnrec(rowKey, field === 'rje' ? 'endRje' : 'endAje', value),
  totalAudited: () => unrecognizedTotal.value.endAudited,
})

const reconRows = computed(() => [
  { label: '长期应付款审定数（净值最终审定合计）', value: netFinalAudited.value, editable: false },
  { label: '专项应付款审定数', value: specialPayableAudited.value, editable: true },
  { label: '长期应付款与专项应付款合计数', value: reconTotal.value, editable: false },
])

const isSaving = ref(false)
const aiLoading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

async function handleSave() {
  isSaving.value = true
  try { await saveAndWriteback() } finally { isSaving.value = false }
}

function handleImportExport(command: string) {
  if (command === 'export-template') importExport.exportTemplate()
  else if (command === 'export-data') importExport.exportData()
  else if (command === 'import-data') fileInputRef.value?.click()
}
function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) importExport.importData(file)
  if (input) input.value = ''
}

const NOTE_PLACEHOLDER =
  '（1）长期应付款期末净值较期初净值增减及主要原因（比例超30%需说明）。\n' +
  '（2）融资租赁/分期付款购入固定资产的未确认融资费用实际利率法摊销情况。\n' +
  '（3）一年内到期的长期应付款重分类至流动负债的情况。\n' +
  '（4）关联方长期应付款交易的公允性及披露。'

async function handleAiNote() {
  if (props.isReadonly) return
  aiLoading.value = true
  try {
    const context: Record<string, string> = {
      净值最终审定合计: String(netFinalAudited.value),
      原值期末审定: String(grossTotal.value.endAudited),
      未确认融资费用期末审定: String(unrecognizedTotal.value.endAudited),
      净值变动额: String(netTotal.value.auditedChange),
      净值变动率百分比: (netTotal.value.auditedRate * 100).toFixed(2),
    }
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'L5-1-note',
      prompt: '请基于长期应付款审定表数据撰写审计说明，覆盖：①净值较期初增减及原因②未确认融资费用摊销③一年内到期重分类④关联方交易公允披露。',
      existingContent: auditNote.value,
      context,
    })
    const content = (res.data?.data ?? res.data)?.content
    if (content) updateText('note', content)
    else ElMessage.info('AI 未返回内容，请手动撰写')
  } catch {
    ElMessage.info('AI 辅助暂不可用，请手动撰写')
  } finally {
    aiLoading.value = false
  }
}

function handleReview() { openReviewDialog?.() }

function fmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtRate(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return `${(val * 100).toFixed(2)}%`
}
function chg(val: number): Record<string, boolean> {
  return { 'text-danger': val < 0, 'text-success': val > 0 }
}

onMounted(async () => { await formData.loadData() })
</script>

<style scoped>
.l5-tab-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context { border-left: 4px solid #f59e0b; background: #fffbeb; padding: 10px 14px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.methodology-text strong { color: #b45309; }

.block-section { margin-bottom: 20px; }
.block-title { margin: 0 0 8px; font-size: 14px; font-weight: 600; color: #303133; }

.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.text-danger { color: #f56c6c; }
.text-success { color: #67c23a; }
.text-warning { color: #e6a23c; font-weight: 600; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table th .cell) { font-size: var(--wp-font-size, 13px); font-weight: 600; }

.l5-total-bar { display: flex; justify-content: space-between; align-items: center; padding: 6px 12px; background: #f5f7fa; border: 1px solid #ebeef5; border-top: none; font-size: var(--wp-font-size, 13px); }
.l5-total-bar--hl { background: #ecf5ff; border-color: #b3d8ff; }
.l5-total-label { font-weight: 600; color: #303133; }
.l5-total-figs { color: #409eff; font-weight: 600; }

.recon-card, .audit-note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.audit-note-card :deep(.el-textarea__inner) { font-size: var(--wp-font-size, 13px); }

.l5-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.l5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }

.audit-objective { margin-bottom: 12px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
</style>
