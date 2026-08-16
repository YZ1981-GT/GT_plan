<template>
  <div class="h2-disc-listed">
    <el-alert type="info" :closable="false" show-icon class="objective">
      审计目标：按上市公司附注格式编制在建工程披露——汇总、明细、重要项目变动（含续表）、减值、工程物资，与 H2-1/H2-2 勾稽，并同步至附注「{{ noteSectionId }}」。
    </el-alert>

    <div class="toolbar">
      <div class="toolbar-left">
        <strong>附注披露信息（上市公司）</strong>
        <el-tag size="small" type="success" effect="plain">23、在建工程</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" :disabled="isReadonly" @click="pullFromSources">从审定/明细取数</el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          data-testid="h2-disclosure-listed-sync"
          @click="syncToNotes"
        >同步到附注</el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('listed')">↩ 跳转回附注</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:H2-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H2-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip :value="`Note:${noteSectionId}`" :context-project-id="projectId" /></span>
        <GtReviewTrigger section-id="H2-disclosure-listed" />
      </div>
    </div>

    <!-- ══════ 23、在建工程 汇总 ══════ -->
    <section class="block">
      <h3 class="block-title">23、在建工程</h3>
      <el-table :data="summaryDisplay" border size="small" class="wp-table" style="max-width: 520px">
        <el-table-column label="项  目" min-width="140">
          <template #default="{ row }">
            <span :class="{ 'is-total': row.key === '__total__' }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="150" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.key !== '__total__' && !isReadonly"
              :model-value="row.endBalance"
              size="small"
              style="width:100%"
              @update:model-value="(v: number) => updateSummary(row.key, 'endBalance', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': row.key === '__total__' }">{{ fmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上年年末余额" width="150" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.key !== '__total__' && !isReadonly"
              :model-value="row.priorBalance"
              size="small"
              style="width:100%"
              @update:model-value="(v: number) => updateSummary(row.key, 'priorBalance', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': row.key === '__total__' }">{{ fmt(row.priorBalance) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <p class="hint">合计自动勾稽；在建工程期末宜与明细「账面净值」合计、重要项目期末合计一致。</p>
    </section>

    <!-- ══════ （1）在建工程 → ①明细 ══════ -->
    <section class="block">
      <h3 class="block-title">（1）在建工程</h3>
      <h4 class="sub-title">①在建工程明细</h4>
      <div class="row-actions" v-if="!isReadonly">
        <el-button size="small" @click="addDetailRow">+ 新增项目行</el-button>
      </div>
      <el-table :data="detailDisplay" border size="small" class="wp-table">
        <el-table-column label="项  目" min-width="140" fixed>
          <template #default="{ row }">
            <span v-if="row.rowId === '__total__'" class="is-total">合  计</span>
            <el-input v-else-if="!isReadonly" v-model="row.name" size="small" @change="scheduleSave" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" align="center">
          <el-table-column label="账面余额" width="120" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.endBook" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else :class="{ 'formula-cell': row.rowId === '__total__' }">{{ fmt(row.endBook) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="减值准备" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.endImpairment" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else :class="{ 'formula-cell': row.rowId === '__total__' }">{{ fmt(row.endImpairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面净值" width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmt(row.rowId === '__total__' ? row.endNet : listedDetailNet(row.endBook, row.endImpairment)) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="上年年末余额" align="center">
          <el-table-column label="账面余额" width="120" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.priorBook" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else :class="{ 'formula-cell': row.rowId === '__total__' }">{{ fmt(row.priorBook) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="减值准备" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.priorImpairment" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else :class="{ 'formula-cell': row.rowId === '__total__' }">{{ fmt(row.priorImpairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面净值" width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmt(row.rowId === '__total__' ? row.priorNet : listedDetailNet(row.priorBook, row.priorImpairment)) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="48">
          <template #default="{ row }">
            <el-button v-if="row.rowId !== '__total__'" link type="danger" size="small" @click="removeDetail(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ══════ ②重要项目变动 ══════ -->
    <section class="block">
      <h4 class="sub-title">②重要在建工程项目变动情况</h4>
      <div class="row-actions" v-if="!isReadonly">
        <el-button size="small" @click="addProjectRow">+ 新增工程行</el-button>
        <span class="hint inline">期末余额 E = A + B − C − D（自动计算）</span>
      </div>
      <div class="scroll-x">
        <el-table :data="projectMoveDisplay" border size="small" class="wp-table">
          <el-table-column label="工程名称" min-width="140" fixed>
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="is-total">合  计</span>
              <el-input v-else-if="!isReadonly" v-model="row.name" size="small" @change="scheduleSave" />
              <span v-else>{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期初余额" width="110" align="right">
            <template #header>期初余额<br /><span class="col-hint">A</span></template>
            <template #default="{ row }">
              <WpAmountInput v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.beginBalance" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.beginBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期增加" width="110" align="right">
            <template #header>本期增加<br /><span class="col-hint">B</span></template>
            <template #default="{ row }">
              <WpAmountInput v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.increase" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.increase) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="转入固定资产" width="120" align="right">
            <template #header>转入固定资产<br /><span class="col-hint">C</span></template>
            <template #default="{ row }">
              <WpAmountInput v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.transferToFA" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.transferToFA) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="其他减少" width="110" align="right">
            <template #header>其他减少<br /><span class="col-hint">D</span></template>
            <template #default="{ row }">
              <WpAmountInput v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.otherDecrease" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.otherDecrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="利息资本化累计金额" width="130" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.interestCapAccum" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.interestCapAccum) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="其中：本期利息资本化金额" width="140" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.interestCapCurrent" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.interestCapCurrent) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期利息资本化率%" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.interestCapRate" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else>{{ row.rowId === '__total__' ? '—' : fmt(row.interestCapRate) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="120" align="right" fixed="right">
            <template #header>期末余额<br /><span class="col-hint">E=A+B−C−D</span></template>
            <template #default="{ row }">
              <span class="formula-cell">{{ fmt(row.rowId === '__total__' ? row.endBalance : listedProjectEnd(row)) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="48" fixed="right">
            <template #default="{ row }">
              <el-button v-if="row.rowId !== '__total__'" link type="danger" size="small" @click="removeProject(row.rowId)">✕</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>

    <!-- ══════ 续表 ══════ -->
    <section class="block">
      <h4 class="sub-title">重要在建工程项目变动情况（续）</h4>
      <el-alert type="info" :closable="false" class="guide-alert">{{ H2_LISTED_GUIDANCE.progress }}</el-alert>
      <el-alert type="info" :closable="false" class="guide-alert">{{ H2_LISTED_GUIDANCE.fundSource }}</el-alert>
      <el-table :data="projectContDisplay" border size="small" class="wp-table">
        <el-table-column label="工程名称" min-width="140">
          <template #default="{ row }">
            <span v-if="row.rowId === '__total__'" class="is-total">合  计</span>
            <span v-else>{{ row.name || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预算数" width="130" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.budget" size="small" style="width:100%" @change="scheduleSave" />
            <span v-else class="formula-cell">{{ fmt(row.budget) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="工程累计投入占预算比例%" width="160" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.cumInputPct" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
            <span v-else class="formula-cell">{{ fmt(row.cumInputPct) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="工程进度" min-width="120">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.progress" size="small" @change="scheduleSave" />
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="资金来源" min-width="140">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.fundSource" size="small" @change="scheduleSave" />
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
      <WpNoteTextArea
        v-model="noteFundSource"
        label="资金来源补充说明"
        testid-prefix="h2-listed-fundSource"
        :min-rows="2"
        :max-rows="4"
        :disabled="isReadonly"
        :placeholder="H2_LISTED_GUIDANCE.fundSource"
        :ai-loading="aiLoadingSection === 'fundSource'"
        @change="scheduleSave"
        @ai="runAi('fundSource')"
        @review="openReview('fundSource')"
      />
    </section>

    <!-- ══════ ③减值 ══════ -->
    <section class="block">
      <h4 class="sub-title">③在建工程减值准备情况</h4>
      <el-alert type="info" :closable="false" class="guide-alert">{{ H2_LISTED_GUIDANCE.impairment }}</el-alert>
      <el-alert type="warning" :closable="false" class="guide-alert warn">{{ H2_LISTED_GUIDANCE.impairmentNote }}</el-alert>
      <div class="row-actions" v-if="!isReadonly">
        <el-button size="small" @click="addImpairmentRow">+ 新增行</el-button>
      </div>
      <el-table :data="impairmentDisplay" border size="small" class="wp-table" style="max-width: 720px">
        <el-table-column label="项  目" min-width="140">
          <template #default="{ row }">
            <span v-if="row.rowId === '__total__'" class="is-total">合  计</span>
            <el-input v-else-if="!isReadonly" v-model="row.name" size="small" @change="scheduleSave" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.beginBalance" size="small" style="width:100%" @change="scheduleSave" />
            <span v-else class="formula-cell">{{ fmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期计提" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.provision" size="small" style="width:100%" @change="scheduleSave" />
            <span v-else class="formula-cell">{{ fmt(row.provision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.decrease" size="small" style="width:100%" @change="scheduleSave" />
            <span v-else class="formula-cell">{{ fmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmt(row.rowId === '__total__' ? row.endBalance : listedImpairmentEnd(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="48">
          <template #default="{ row }">
            <el-button v-if="row.rowId !== '__total__'" link type="danger" size="small" @click="removeImpairment(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <WpNoteTextArea
        v-model="noteImpairment"
        label="减值测试披露说明"
        testid-prefix="h2-listed-impairment"
        :min-rows="3"
        :max-rows="8"
        :disabled="isReadonly"
        :placeholder="H2_LISTED_GUIDANCE.impairment"
        :ai-loading="aiLoadingSection === 'impairment'"
        @change="scheduleSave"
        @ai="runAi('impairment')"
        @review="openReview('impairment')"
      />
    </section>

    <WpDisclosureConsistencyPanel :results="consistencyChecks" :project-id="projectId" />

    <!-- ══════ （2）工程物资 ══════ -->
    <section class="block">
      <h3 class="block-title">（2）工程物资</h3>
      <el-table :data="materialsDisplay" border size="small" class="wp-table" style="max-width: 520px">
        <el-table-column label="项  目" min-width="160">
          <template #default="{ row }">
            <span :class="{ 'is-total': row.key === '__total__' || row.key === '__gross__' }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="150" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.editable && !isReadonly"
              :model-value="row.endBalance"
              size="small"
              style="width:100%"
              @update:model-value="(v: number) => updateMaterial(row.key, 'endBalance', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': !row.editable }">{{ row.isDeduction ? `(${fmt(row.endBalance)})` : fmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上年年末余额" width="150" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.editable && !isReadonly"
              :model-value="row.priorBalance"
              size="small"
              style="width:100%"
              @update:model-value="(v: number) => updateMaterial(row.key, 'priorBalance', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': !row.editable }">{{ row.isDeduction ? `(${fmt(row.priorBalance)})` : fmt(row.priorBalance) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ══════ 抵押 / 所有权受限 ══════ -->
    <section class="block">
      <h4 class="sub-title">所有权或使用权受限的在建工程（抵押/担保）</h4>
      <el-alert type="info" :closable="false" class="guide-alert">{{ H2_LISTED_GUIDANCE.mortgage }}</el-alert>
      <div class="row-actions" v-if="!isReadonly">
        <el-button size="small" type="primary" plain @click="pullMortgage">从 H2-2 同步抵押</el-button>
        <el-button size="small" @click="addMortgageRow">+ 新增行</el-button>
      </div>
      <el-table v-if="mortgageRows.length" :data="mortgageRows" border size="small" class="wp-table" style="max-width: 780px">
        <el-table-column label="工程名称" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="scheduleSave" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="抵押/担保金额" width="140" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.amount" size="small" style="width:100%" @change="scheduleSave" />
            <span v-else class="formula-cell">{{ fmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.description" size="small" @change="scheduleSave" />
            <span v-else>{{ row.description || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="scheduleSave" />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="48">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeMortgage(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p v-else class="hint">暂无抵押项目；请在 H2-2 勾选「是否抵押=是」后点「从 H2-2 同步抵押」。</p>
      <WpNoteTextArea
        v-model="noteMortgage"
        label="抵押、担保在建工程情况说明"
        testid-prefix="h2-listed-mortgage"
        :min-rows="2"
        :max-rows="6"
        :disabled="isReadonly"
        :placeholder="H2_LISTED_GUIDANCE.mortgage"
        :ai-loading="aiLoadingSection === 'mortgage'"
        @change="scheduleSave"
        @ai="runAi('mortgage')"
        @review="openReview('mortgage')"
      />
    </section>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>列结构严格对齐源 xlsx「附注披露信息（上市公司）」；明细/重要项目/减值按实际工程动态插行。</li>
        <li>账面净值、项目期末余额、减值期末余额为公式列，不可手工改列结构。</li>
        <li>抵押行自 H2-2「是否抵押=是」同步；「同步到附注」一并推送受限资产子表。</li>
        <li>「同步到附注」推送至「{{ noteSectionId }}」各子表；空名称行不推送。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabDisclosureListed — 附注披露信息（上市公司）
 * 对齐源 xlsx 列结构；动态插行；同步附注五、23
 */
import { ref, reactive, computed, inject, watch, onMounted, onBeforeUnmount } from 'vue'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import WpNoteTextArea from '../../shared/disclosure/WpNoteTextArea.vue'
import { useHCycleDisclosureAi } from '../../composables/useHCycleDisclosureAi'
import { H_CYCLE_NOTE_AI_SECTIONS } from '../../composables/hCycleNoteAiSections'
import WpDisclosureConsistencyPanel from '../../shared/disclosure/WpDisclosureConsistencyPanel.vue'
import { buildH2ListedChecks } from '../../composables/h2DisclosureConsistency'
import { H2_NOTE_SECTION } from '../../composables/h2NoteSectionMap'
import { buildH2ListedSyncPayloads, type H2ListedSyncSnapshot } from '../../composables/h2DisclosureSyncPayload'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import {
  H2_LISTED_GUIDANCE,
  H2_LISTED_ITEM,
  buildMortgageNoteText,
  createDefaultListedMaterials,
  createDefaultListedSummary,
  createEmptyListedProject,
  listedDetailNet,
  listedDetailSubtotal,
  listedImpairmentEnd,
  listedImpairmentSubtotal,
  listedMaterialsGross,
  listedMaterialsNet,
  listedProjectEnd,
  listedProjectSubtotal,
  listedSummaryTotal,
  mapDetailToListedDetail,
  mapDetailToListedProjects,
  mapMortgagedDetailToRows,
  newRowId,
  num,
  type ListedDetailRow,
  type ListedImpairmentRow,
  type ListedMaterialRow,
  type ListedMortgageRow,
  type ListedProjectRow,
  type ListedSummaryRow,
} from '../../composables/h2ListedDisclosureModel'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const isReadonly = computed(() => props.isReadonly)
const autoSync = useDisclosureAutoSync({ isReadonly: () => isReadonly.value })
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'H2', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}
const noteSectionId = H2_NOTE_SECTION.listed
const isSyncing = ref(false)
let saveTimer: ReturnType<typeof setTimeout> | null = null

const summary = reactive<ListedSummaryRow[]>(createDefaultListedSummary())
const detailRows = ref<ListedDetailRow[]>([])
const projectRows = ref<ListedProjectRow[]>([])
const impairmentRows = ref<ListedImpairmentRow[]>([])
const materials = reactive<ListedMaterialRow[]>(createDefaultListedMaterials())
const mortgageRows = ref<ListedMortgageRow[]>([])
const noteImpairment = ref('')
const noteFundSource = ref('')
const noteMortgage = ref('')

// ─── 披露说明 AI 辅助 + 复核（原本 3 个文本域全无 AI 按钮） ──────────────────
const { aiLoadingSection: aiLoadingRef, runAi, openReview } = useHCycleDisclosureAi({
  wpCode: 'H2',
  variant: 'listed',
  wpId: () => props.wpId,
  isReadonly: () => isReadonly.value,
  noteSectionId: H2_NOTE_SECTION.listed,
  labels: H_CYCLE_NOTE_AI_SECTIONS.H2.listed,
  fields: {
    fundSource: { get: () => noteFundSource.value || '', set: (v) => { noteFundSource.value = v; scheduleSave() } },
    impairment: { get: () => noteImpairment.value || '', set: (v) => { noteImpairment.value = v; scheduleSave() } },
    mortgage: { get: () => noteMortgage.value || '', set: (v) => { noteMortgage.value = v; scheduleSave() } },
  },
})
const aiLoadingSection = computed(() => aiLoadingRef.value)

const consistencyChecks = computed(() =>
  buildH2ListedChecks({
    summary: [...summary],
    detailRows: detailRows.value,
    projectRows: projectRows.value,
    impairmentRows: impairmentRows.value,
  }),
)

const summaryDisplay = computed(() => {
  const tot = listedSummaryTotal(summary)
  return [...summary, { key: '__total__' as any, label: '合  计', endBalance: tot.endBalance, priorBalance: tot.priorBalance }]
})

const detailDisplay = computed(() => {
  const tot = listedDetailSubtotal(detailRows.value)
  return [
    ...detailRows.value,
    {
      rowId: '__total__',
      name: '合计',
      endBook: tot.endBook,
      endImpairment: tot.endImpairment,
      endNet: tot.endNet,
      priorBook: tot.priorBook,
      priorImpairment: tot.priorImpairment,
      priorNet: tot.priorNet,
    } as any,
  ]
})

const projectMoveDisplay = computed(() => {
  const tot = listedProjectSubtotal(projectRows.value)
  return [
    ...projectRows.value,
    {
      rowId: '__total__',
      name: '合计',
      beginBalance: tot.beginBalance,
      increase: tot.increase,
      transferToFA: tot.transferToFA,
      otherDecrease: tot.otherDecrease,
      interestCapAccum: tot.interestCapAccum,
      interestCapCurrent: tot.interestCapCurrent,
      interestCapRate: 0,
      endBalance: tot.endBalance,
    } as any,
  ]
})

const projectContDisplay = computed(() => {
  const tot = listedProjectSubtotal(projectRows.value)
  return [
    ...projectRows.value,
    {
      rowId: '__total__',
      name: '合计',
      budget: tot.budget,
      cumInputPct: tot.cumInputPct,
      progress: '',
      fundSource: '',
    } as any,
  ]
})

const impairmentDisplay = computed(() => {
  const tot = listedImpairmentSubtotal(impairmentRows.value)
  return [
    ...impairmentRows.value,
    {
      rowId: '__total__',
      name: '合计',
      beginBalance: tot.beginBalance,
      provision: tot.provision,
      decrease: tot.decrease,
      endBalance: tot.endBalance,
    } as any,
  ]
})

const materialsDisplay = computed(() => {
  const gross = listedMaterialsGross(materials)
  const net = listedMaterialsNet(materials)
  const rows: any[] = []
  for (const r of materials) {
    if (r.isDeduction) {
      rows.push({ key: '__gross__', label: '小计', endBalance: gross.endBalance, priorBalance: gross.priorBalance, editable: false })
    }
    rows.push({ ...r, editable: true })
  }
  rows.push({ key: '__total__', label: '合  计', endBalance: net.endBalance, priorBalance: net.priorBalance, editable: false })
  return rows
})

function fmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function parseJson(itemId: string): any {
  const raw = props.allResponses.get(itemId)?.remark
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

function load() {
  const s = parseJson(H2_LISTED_ITEM.summary)
  if (Array.isArray(s) && s.length) {
    for (const row of s) {
      const t = summary.find((x) => x.key === row.key)
      if (t) {
        t.endBalance = num(row.endBalance)
        t.priorBalance = num(row.priorBalance)
      }
    }
  }
  const d = parseJson(H2_LISTED_ITEM.detail)
  detailRows.value = Array.isArray(d) ? d.map((r: any) => ({
    rowId: r.rowId || newRowId('det'),
    name: r.name || '',
    endBook: num(r.endBook),
    endImpairment: num(r.endImpairment),
    priorBook: num(r.priorBook),
    priorImpairment: num(r.priorImpairment),
  })) : []
  const p = parseJson(H2_LISTED_ITEM.projects)
  projectRows.value = Array.isArray(p) ? p.map((r: any) => ({
    ...createEmptyListedProject(),
    ...r,
    rowId: r.rowId || newRowId('proj'),
    beginBalance: num(r.beginBalance),
    increase: num(r.increase),
    transferToFA: num(r.transferToFA),
    otherDecrease: num(r.otherDecrease),
    interestCapAccum: num(r.interestCapAccum),
    interestCapCurrent: num(r.interestCapCurrent),
    interestCapRate: num(r.interestCapRate),
    budget: num(r.budget),
    cumInputPct: num(r.cumInputPct),
    accumulatedInput: num(r.accumulatedInput),
  })) : []
  const i = parseJson(H2_LISTED_ITEM.impairment)
  impairmentRows.value = Array.isArray(i) ? i.map((r: any) => ({
    rowId: r.rowId || newRowId('imp'),
    name: r.name || '',
    beginBalance: num(r.beginBalance),
    provision: num(r.provision),
    decrease: num(r.decrease),
  })) : []
  const m = parseJson(H2_LISTED_ITEM.materials)
  if (Array.isArray(m) && m.length) {
    for (const row of m) {
      const t = materials.find((x) => x.key === row.key)
      if (t) {
        t.endBalance = num(row.endBalance)
        t.priorBalance = num(row.priorBalance)
      }
    }
  }
  noteImpairment.value = String(props.allResponses.get(H2_LISTED_ITEM.noteImpairment)?.remark ?? '')
  noteFundSource.value = String(props.allResponses.get(H2_LISTED_ITEM.noteFundSource)?.remark ?? '')
  noteMortgage.value = String(props.allResponses.get(H2_LISTED_ITEM.noteMortgage)?.remark ?? '')
  const mort = parseJson(H2_LISTED_ITEM.mortgageRows)
  mortgageRows.value = Array.isArray(mort) ? mort.map((r: any, i: number) => ({
    rowId: r.rowId || newRowId(`mort-${i}`),
    name: r.name || '',
    amount: num(r.amount),
    description: r.description || '',
    remark: r.remark || '',
  })) : []

  const hasData = detailRows.value.length || projectRows.value.length
    || summary.some((r) => r.endBalance || r.priorBalance)
  if (!hasData) pullFromSources(false)
}

function scheduleSave() {
  if (isReadonly.value) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => persistAll(), 300)
}

function persistAll() {
  saveResponse(H2_LISTED_ITEM.summary, summary.map((r) => ({ ...r })))
  saveResponse(H2_LISTED_ITEM.detail, detailRows.value)
  saveResponse(H2_LISTED_ITEM.projects, projectRows.value)
  saveResponse(H2_LISTED_ITEM.impairment, impairmentRows.value)
  saveResponse(H2_LISTED_ITEM.materials, materials.map((r) => ({ key: r.key, label: r.label, endBalance: r.endBalance, priorBalance: r.priorBalance, isDeduction: r.isDeduction })))
  saveResponse(H2_LISTED_ITEM.mortgageRows, mortgageRows.value)
  saveResponse(H2_LISTED_ITEM.noteImpairment, noteImpairment.value)
  saveResponse(H2_LISTED_ITEM.noteFundSource, noteFundSource.value)
  saveResponse(H2_LISTED_ITEM.noteMortgage, noteMortgage.value)
  eventBus.emit('disclosure:note-text-updated' as any, {
    wpCode: 'H2',
    accountCode: '1604',
    projectId: props.projectId,
    section: noteSectionId,
    sectionIds: [noteSectionId],
    text: noteImpairment.value || noteFundSource.value || noteMortgage.value || '',
  })
  autoSync.scheduleAutoSync(syncToNotes)
}

function updateSummary(key: string, field: 'endBalance' | 'priorBalance', v: number) {
  const row = summary.find((r) => r.key === key)
  if (!row) return
  row[field] = num(v)
  scheduleSave()
}

function updateMaterial(key: string, field: 'endBalance' | 'priorBalance', v: number) {
  const row = materials.find((r) => r.key === key)
  if (!row) return
  row[field] = num(v)
  // 汇总工程物资行联动净值
  const mat = summary.find((r) => r.key === 'materials')
  if (mat) {
    const net = listedMaterialsNet(materials)
    mat.endBalance = net.endBalance
    mat.priorBalance = net.priorBalance
  }
  scheduleSave()
}

function addDetailRow() {
  detailRows.value.push({
    rowId: newRowId('det'),
    name: '',
    endBook: 0,
    endImpairment: 0,
    priorBook: 0,
    priorImpairment: 0,
  })
  scheduleSave()
}
function removeDetail(rowId: string) {
  detailRows.value = detailRows.value.filter((r) => r.rowId !== rowId)
  scheduleSave()
}
function addProjectRow() {
  projectRows.value.push(createEmptyListedProject())
  scheduleSave()
}
function removeProject(rowId: string) {
  projectRows.value = projectRows.value.filter((r) => r.rowId !== rowId)
  scheduleSave()
}
function addImpairmentRow() {
  impairmentRows.value.push({
    rowId: newRowId('imp'),
    name: '',
    beginBalance: 0,
    provision: 0,
    decrease: 0,
  })
  scheduleSave()
}
function removeImpairment(rowId: string) {
  impairmentRows.value = impairmentRows.value.filter((r) => r.rowId !== rowId)
  scheduleSave()
}

function pullFromSources(showMsg = true) {
  const adjRaw = props.allResponses.get('H2-1-rows')?.remark
  const detRaw = props.allResponses.get('H2-2-rows')?.remark
  let adj: any[] = []
  let det: any[] = []
  try { if (adjRaw) adj = JSON.parse(adjRaw) } catch { /* ignore */ }
  try { if (detRaw) det = JSON.parse(detRaw) } catch { /* ignore */ }

  if (Array.isArray(det) && det.length) {
    detailRows.value = mapDetailToListedDetail(det)
    projectRows.value = mapDetailToListedProjects(det)
    // 自动带入抵押（不覆盖已有手工编辑行时若为空则填充）
    if (!mortgageRows.value.length) {
      const morts = mapMortgagedDetailToRows(det)
      if (morts.length) {
        mortgageRows.value = morts
        if (!noteMortgage.value.trim()) noteMortgage.value = buildMortgageNoteText(morts)
      }
    }
  }

  if (Array.isArray(adj) && adj.length) {
    const cipBegin = adj.reduce((s, r) => s + num(r.cipBegin), 0)
    const cipEnd = adj.reduce((s, r) => s + num(r.cipEnd ?? r.audited), 0)
    const impair = adj.reduce((s, r) => s + num(r.impairment), 0)
    const cip = summary.find((r) => r.key === 'cip')
    if (cip) {
      cip.endBalance = cipEnd - impair
      cip.priorBalance = cipBegin
    }
  } else if (detailRows.value.length) {
    const tot = listedDetailSubtotal(detailRows.value)
    const cip = summary.find((r) => r.key === 'cip')
    if (cip) {
      cip.endBalance = tot.endNet
      cip.priorBalance = tot.priorNet
    }
  }

  scheduleSave()
  if (showMsg) ElMessage.success('已从 H2-1/H2-2 取数填充披露表')
}

function pullMortgage() {
  const detRaw = props.allResponses.get('H2-2-rows')?.remark
  let det: any[] = []
  try { if (detRaw) det = JSON.parse(detRaw) } catch { /* ignore */ }
  const morts = mapMortgagedDetailToRows(Array.isArray(det) ? det : [])
  if (!morts.length) {
    ElMessage.warning('H2-2 无「是否抵押=是」的工程')
    return
  }
  mortgageRows.value = morts
  if (!noteMortgage.value.trim()) noteMortgage.value = buildMortgageNoteText(morts)
  scheduleSave()
  ElMessage.success(`已同步抵押 ${morts.length} 项`)
}

function addMortgageRow() {
  mortgageRows.value.push({
    rowId: newRowId('mort'),
    name: '',
    amount: 0,
    description: '',
    remark: '',
  })
  scheduleSave()
}

function removeMortgage(rowId: string) {
  mortgageRows.value = mortgageRows.value.filter((r) => r.rowId !== rowId)
  scheduleSave()
}

function getSnapshot(): H2ListedSyncSnapshot {
  return {
    summary: summary.map((r) => ({ ...r })),
    detail: detailRows.value,
    projects: projectRows.value,
    impairment: impairmentRows.value,
    materials: materials.map((r) => ({ ...r })),
    mortgage: mortgageRows.value,
    noteImpairment: noteImpairment.value,
    noteFundSource: noteFundSource.value,
    noteMortgage: noteMortgage.value,
  }
}

async function syncToNotes() {
  if (isSyncing.value || isReadonly.value || !props.projectId || !props.wpId) return
  persistAll()
  const payloads = buildH2ListedSyncPayloads(props.wpId, [], getSnapshot())
  if (!payloads.length) {
    ElMessage.warning('当前不适用上市附注同步')
    return
  }
  isSyncing.value = true
  try {
    let rows = 0
    for (const payload of payloads) {
      const result: any = await api.post(
        `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
        payload,
      )
      const data = result?.data ?? result
      rows += Number(data?.rows_synced ?? 0)
    }
    ElMessage.success(`已同步 ${rows} 行到附注「${noteSectionId}」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

onMounted(load)
watch(() => props.allResponses, load, { deep: false })

// A3: 订阅 substantive:adjudicated 刷新披露数据
const _onAdjudicated = (payload: any) => {
  if (payload?.wpCode === 'H2' || payload?.accountCode === '1604') load()
}
eventBus.on('substantive:adjudicated', _onAdjudicated)
onBeforeUnmount(() => { autoSync.cancelPending(); eventBus.off('substantive:adjudicated', _onAdjudicated) })
</script>

<style scoped>
.h2-disc-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective { margin-bottom: 12px; }
.toolbar {
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;
  margin-bottom: 14px;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.block { margin-bottom: 20px; }
.block-title { margin: 0 0 8px; font-size: 15px; }
.sub-title { margin: 0 0 8px; font-size: 14px; color: #303133; }
.hint { font-size: 12px; color: #909399; margin: 6px 0 0; }
.hint.inline { margin: 0; }
.row-actions { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.scroll-x { overflow-x: auto; }
.formula-cell {
  border-bottom: 1px dashed #909399; font-variant-numeric: tabular-nums;
}
.is-total { font-weight: 600; }
.col-hint { font-size: 11px; color: #909399; font-weight: 400; }
.guide-alert { margin-bottom: 8px; }
.guide-alert.warn { --el-alert-bg-color: #fdf6ec; }
.note-field { margin-top: 10px; }
.note-field label {
  display: block; font-size: 12px; color: #606266; margin-bottom: 4px;
}
.compile-hint { margin-top: 16px; font-size: 12px; color: #909399; }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
