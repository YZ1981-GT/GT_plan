<template>
<div class="d6-disclosure">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 合同资产（科目1402）附注依 CAS14 收入准则及 CAS22 减值准则披露，按上市公司版（5子节）/ 国企版（3子节）分别列报。</p>
      <p>2. 表内浅蓝背景单元格为跨sheet自动取数（来源 D6-1 审定表 / D6-3 减值明细 / D6-8 测算），不可手工编辑。</p>
      <p>3. 上市公司版需披露分类构成、减值计提情况、单项与组合明细及计提转回核销变动；国企版仅需披露分类及减值变动。</p>
      <p>4. 各子节说明文本将双向回写至附注模块，请与审定表、减值明细及测算保持勾稽一致。</p>
    </div>
  </details>

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-segmented v-if="showListed && showSoe" v-model="activeVariant" :options="variantOptions" size="small" />
      <el-button type="primary" plain size="small" :loading="isSyncing" :disabled="isReadonly"
        title="将披露表的表格与文本框内容同步到附注模块（五、10/八、11 合同资产）"
        @click="syncToDisclosureNotes">同步到附注</el-button>
      <el-dropdown split-button type="default" size="small" :disabled="!projectId"
        @click="jumpToNote(displayVariant)"
        @command="jumpToNote">
        ↩ 跳转回附注（{{ displayVariant === 'soe' ? '八、11' : '五、10' }}）
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="listed">上市版（五、10）</el-dropdown-item>
            <el-dropdown-item command="soe">国企版（八、11）</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
    <div class="toolbar-right">
      <span class="chip-wrap"><GtIndexChip value="wp:D6-1" :context-project-id="projectId" /></span>
      <span class="chip-wrap"><GtIndexChip value="wp:D6-3" :context-project-id="projectId" /></span>
    </div>
  </div>

  <!-- 上市公司版 -->
  <template v-if="displayVariant === 'listed'">
    <div v-for="section in listedSections" :key="section.sectionKey" class="disclosure-card">
      <h4 class="section-title">{{ section.label }}</h4>

      <!-- Section 1: 分类 -->
      <template v-if="section.sectionKey === 'listed-1'">
        <el-table :data="padRows(section.rows)" size="small" border>
          <el-table-column prop="label" label="项目" width="200" />
          <el-table-column label="期末账面余额" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endBookBalance) }}</span></template>
          </el-table-column>
          <el-table-column label="期末减值准备" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endImpairment) }}</span></template>
          </el-table-column>
          <el-table-column label="期末账面价值" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endBookValue) }}</span></template>
          </el-table-column>
          <el-table-column label="上年账面余额" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorBookBalance) }}</span></template>
          </el-table-column>
          <el-table-column label="上年减值准备" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorImpairment) }}</span></template>
          </el-table-column>
          <el-table-column label="上年账面价值" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorBookValue) }}</span></template>
          </el-table-column>
        </el-table>
      </template>

      <!-- (1) 本期合同资产账面价值的重大变动 -->
      <template v-else-if="section.sectionKey === 'listed-major-change'">
        <div class="sub-toolbar">
          <el-dropdown v-if="!isReadonly" size="small" trigger="click">
            <el-button size="small">导入导出 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="majorChangeIe.exportTemplate">导出模板</el-dropdown-item>
                <el-dropdown-item @click="majorChangeIe.exportData">导出数据</el-dropdown-item>
                <el-dropdown-item>
                  <el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="majorChangeIe.importing.value"
                    @change="(f: any) => onMajorChangeImport(f.raw || f)"><span>导入数据</span></el-upload>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <el-table :data="padRows(majorChangeRows)" size="small" border>
          <el-table-column label="项目" min-width="200">
            <template #default="{ row }">
              <el-input v-if="!isReadonly && !row._isPad" :model-value="row.label" size="small" placeholder="变动项目"
                @change="(v: string) => updateMajorChangeCell(row.rowId, 'label', v)" />
              <span v-else>{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动金额" width="160" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly && !row._isPad" :model-value="row.amount" :controls="false" size="small" style="width:100%"
                @change="(v: number) => updateMajorChangeCell(row.rowId, 'amount', v ?? 0)" />
              <span v-else>{{ row._isPad ? '' : fmtAmt(row.amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动原因" min-width="240">
            <template #default="{ row }">
              <el-input v-if="!isReadonly && !row._isPad" :model-value="row.reason" size="small" placeholder="变动原因"
                @change="(v: string) => updateMajorChangeCell(row.rowId, 'reason', v)" />
              <span v-else>{{ row.reason }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="50" align="center">
            <template #default="{ row }">
              <el-button v-if="!row._isPad" type="danger" text size="small" @click="removeMajorChangeRow(row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button v-if="!isReadonly" size="small" style="margin-top:8px" @click="addMajorChangeRow">添加行</el-button>
        <!-- 重大变动情形说明（准则指引） -->
        <details class="amber-context">
          <summary>📖 重大变动情形说明（CAS14）</summary>
          <div class="amber-content">
            <p>履行履约义务的时间与通常的付款时间之间的关系，以及此类因素对合同资产（如果对合同负债产生影响在合同负债科目下说明）账面价值的影响。本期内发生的重大变动的情形包括：</p>
            <p>① 企业合并导致的变动；</p>
            <p>② 对收入进行累积追溯调整导致的相关合同资产和合同负债的变动，此类调整可能源于估计履约进度的变化、估计交易价格的变化（包括对于可变对价是否受到限制的评估发生变化）或者合同变更；</p>
            <p>③ 对合同对价的权利成为无条件权利（即，合同资产重分类为应收款项）的时间安排发生变化。</p>
          </div>
        </details>
      </template>

      <!-- Section 2: 减值计提情况 -->
      <template v-else-if="section.sectionKey === 'listed-2'">
        <el-table :data="padRows(section.rows)" size="small" border>
          <el-table-column prop="label" label="类别" width="180" />
          <el-table-column label="期末余额" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endBalance) }}</span></template>
          </el-table-column>
          <el-table-column label="比例%" width="90" align="right">
            <template #default="{ row }">{{ fmtPct(row.endPercentage) }}</template>
          </el-table-column>
          <el-table-column label="减值金额" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endAmount) }}</span></template>
          </el-table-column>
          <el-table-column label="损失率%" width="90" align="right">
            <template #default="{ row }">{{ fmtPct100(row.endLossRate) }}</template>
          </el-table-column>
        </el-table>
      </template>

      <!-- Section 3: 单项明细 -->
      <template v-else-if="section.sectionKey === 'listed-3'">
        <el-table :data="padRows(section.rows)" size="small" border>
          <el-table-column prop="label" label="名称" min-width="160" />
          <el-table-column label="账面余额" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.balance) }}</span></template>
          </el-table-column>
          <el-table-column label="坏账准备" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.provision) }}</span></template>
          </el-table-column>
          <el-table-column label="损失率%" width="90" align="right">
            <template #default="{ row }">{{ fmtPct100(row.lossRate) }}</template>
          </el-table-column>
          <el-table-column prop="reason" label="计提理由" min-width="160" />
        </el-table>
      </template>

      <!-- Section 4: 按组合明细 -->
      <template v-else-if="section.sectionKey === 'listed-4'">
        <div class="sub-toolbar">
          <el-dropdown v-if="!isReadonly" size="small" trigger="click">
            <el-button size="small">导入导出 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="groupsIe.exportTemplate">导出模板</el-dropdown-item>
                <el-dropdown-item @click="groupsIe.exportData">导出数据</el-dropdown-item>
                <el-dropdown-item>
                  <el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="groupsIe.importing.value"
                    @change="(f: any) => onGroupsImport(f.raw || f)"><span>导入数据</span></el-upload>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <div v-for="(group, gIdx) in groupedDetails" :key="gIdx" class="group-block">
          <div class="group-header">
            <el-input
              v-if="!isReadonly"
              :model-value="group.groupName"
              size="small"
              placeholder="组合名称"
              style="width:200px"
              @change="(v: string) => updateGroupName(gIdx, v)"
            />
            <span v-else class="group-name">{{ group.groupName || `组合${gIdx + 1}` }}</span>
            <el-button v-if="!isReadonly" size="small" @click="addGroupedDetailRow(group.groupName)">添加行</el-button>
          </div>
          <el-table :data="padRows(group.rows)" size="small" border>
            <el-table-column label="账龄" width="120">
              <template #default="{ row }">
                <el-input v-if="!isReadonly && !row._isPad" :model-value="row.label" size="small" @change="(v: string) => updateGroupedCell(gIdx, row.rowId, 'label', v)" />
                <span v-else>{{ row.label }}</span>
              </template>
            </el-table-column>
            <el-table-column label="合同资产" width="120" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly && !row._isPad" :model-value="row.balance" :controls="false" size="small" style="width:100%" @change="(v: number) => updateGroupedCell(gIdx, row.rowId, 'balance', v ?? 0)" />
                <span v-else>{{ row._isPad ? '' : fmtAmt(row.balance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="坏账准备" width="120" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly && !row._isPad" :model-value="row.provision" :controls="false" size="small" style="width:100%" @change="(v: number) => updateGroupedCell(gIdx, row.rowId, 'provision', v ?? 0)" />
                <span v-else>{{ row._isPad ? '' : fmtAmt(row.provision) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="损失率%" width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly && !row._isPad" :model-value="row.lossRate" :controls="false" size="small" style="width:100%" @change="(v: number) => updateGroupedCell(gIdx, row.rowId, 'lossRate', v ?? 0)" />
                <span v-else>{{ row._isPad ? '' : fmtPct100(row.lossRate) }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="" width="50" align="center">
              <template #default="{ row }">
                <el-button v-if="!row._isPad" type="danger" text size="small" @click="removeGroupedRow(gIdx, row.rowId)">删</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <el-button v-if="!isReadonly" size="small" style="margin-top:8px" @click="addGroup">添加组合</el-button>
      </template>

      <!-- Section 5: 计提转回核销 -->
      <template v-else-if="section.sectionKey === 'listed-5'">
        <el-table :data="padRows(section.rows)" size="small" border>
          <el-table-column prop="label" label="项目" width="180" />
          <el-table-column label="本期计提" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.provision) }}</span></template>
          </el-table-column>
          <el-table-column label="本期转回" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.reversal) }}</span></template>
          </el-table-column>
          <el-table-column label="本期核销" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.writeOff) }}</span></template>
          </el-table-column>
          <el-table-column prop="reason" label="原因" min-width="160" />
        </el-table>
      </template>

      <div class="note-block">
        <div class="note-label">说明：</div>
        <el-input
          :model-value="noteTexts[getListedNoteKey(section.sectionKey)]"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="补充披露说明..."
          @change="(v: string) => updateNoteText(getListedNoteKey(section.sectionKey), v)"
        />
      </div>
    </div>
  </template>

  <!-- 国企版 -->
  <template v-if="displayVariant === 'soe'">
    <div v-for="section in soeSections" :key="section.sectionKey" class="disclosure-card">
      <h4 class="section-title">{{ section.label }}</h4>

      <!-- (1) 合同资产情况：期末/期初 各含 账面余额/减值准备/账面价值 -->
      <template v-if="section.sectionKey === 'soe-1'">
        <el-table :data="padRows(section.rows)" size="small" border>
          <el-table-column prop="label" label="项目" width="200" fixed />
          <el-table-column label="期末数" align="center">
            <el-table-column label="账面余额" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endBookBalance) }}</span></template>
            </el-table-column>
            <el-table-column label="减值准备" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endImpairment) }}</span></template>
            </el-table-column>
            <el-table-column label="账面价值" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endBookValue) }}</span></template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期初数" align="center">
            <el-table-column label="账面余额" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorBookBalance) }}</span></template>
            </el-table-column>
            <el-table-column label="减值准备" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorImpairment) }}</span></template>
            </el-table-column>
            <el-table-column label="账面价值" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorBookValue) }}</span></template>
            </el-table-column>
          </el-table-column>
        </el-table>
      </template>

      <!-- (2) 合同资产减值准备：项目/期初/本期变动(计提/转回/转销核销)/期末/原因 -->
      <template v-else-if="section.sectionKey === 'soe-2'">
        <el-table :data="padRows(section.rows)" size="small" border>
          <el-table-column prop="label" label="项目" width="150" fixed />
          <el-table-column label="期初数" width="110" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorBalance) }}</span></template>
          </el-table-column>
          <el-table-column label="本期变动金额" align="center">
            <el-table-column label="计提" width="110" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.provision) }}</span></template>
            </el-table-column>
            <el-table-column label="转回" width="110" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.reversal) }}</span></template>
            </el-table-column>
            <el-table-column label="转销/核销" width="110" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.writeOff) }}</span></template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期末数" width="110" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endBalance) }}</span></template>
          </el-table-column>
          <el-table-column label="原因" min-width="160">
            <template #default="{ row }">{{ row._isPad ? '' : row.reason }}</template>
          </el-table-column>
        </el-table>
      </template>

      <!-- (1) 本期合同资产账面价值的重大变动【国资委格式未要求披露】 -->
      <template v-else>
        <div class="sub-toolbar">
          <el-dropdown v-if="!isReadonly" size="small" trigger="click">
            <el-button size="small">导入导出 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="majorChangeIe.exportTemplate">导出模板</el-dropdown-item>
                <el-dropdown-item @click="majorChangeIe.exportData">导出数据</el-dropdown-item>
                <el-dropdown-item>
                  <el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="majorChangeIe.importing.value"
                    @change="(f: any) => onMajorChangeImport(f.raw || f)"><span>导入数据</span></el-upload>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <el-table :data="padRows(majorChangeRows)" size="small" border>
          <el-table-column label="项目" min-width="200">
            <template #default="{ row }">
              <el-input v-if="!isReadonly && !row._isPad" :model-value="row.label" size="small" placeholder="变动项目"
                @change="(v: string) => updateMajorChangeCell(row.rowId, 'label', v)" />
              <span v-else>{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动金额" width="160" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly && !row._isPad" :model-value="row.amount" :controls="false" size="small" style="width:100%"
                @change="(v: number) => updateMajorChangeCell(row.rowId, 'amount', v ?? 0)" />
              <span v-else>{{ row._isPad ? '' : fmtAmt(row.amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动原因" min-width="240">
            <template #default="{ row }">
              <el-input v-if="!isReadonly && !row._isPad" :model-value="row.reason" size="small" placeholder="变动原因"
                @change="(v: string) => updateMajorChangeCell(row.rowId, 'reason', v)" />
              <span v-else>{{ row.reason }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="50" align="center">
            <template #default="{ row }">
              <el-button v-if="!row._isPad" type="danger" text size="small" @click="removeMajorChangeRow(row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button v-if="!isReadonly" size="small" style="margin-top:8px" @click="addMajorChangeRow">添加行</el-button>
        <details class="amber-context">
          <summary>📖 重大变动情形说明（CAS14）</summary>
          <div class="amber-content">
            <p>履行履约义务的时间与通常的付款时间之间的关系，以及此类因素对合同资产（如果对合同负债产生影响在合同负债科目下说明）账面价值的影响。本期内发生的重大变动的情形包括：</p>
            <p>① 企业合并导致的变动；</p>
            <p>② 对收入进行累积追溯调整导致的相关合同资产和合同负债的变动，此类调整可能源于估计履约进度的变化、估计交易价格的变化（包括对于可变对价是否受到限制的评估发生变化）或者合同变更；</p>
            <p>③ 对合同对价的权利成为无条件权利（即，合同资产重分类为应收款项）的时间安排发生变化。</p>
          </div>
        </details>
      </template>

      <div v-if="section.sectionKey !== 'soe-3'" class="note-block">
        <div class="note-label">说明：</div>
        <el-input
          :model-value="noteTexts[getSoeNoteKey(section.sectionKey)]"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="补充披露说明..."
          @change="(v: string) => updateNoteText(getSoeNoteKey(section.sectionKey), v)"
        />
      </div>
    </div>
  </template>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabDisclosure.vue — 附注披露（上市5子节 / 国企3子节）
 */
import { computed, inject, ref, toRef, watch, onUnmounted, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useD6Disclosure } from '../composables/useD6Disclosure'
import { useD6ImportExport } from '../composables/useD6ImportExport'
import { useDisclosureAutoSync } from '../composables/useDisclosureAutoSync'
import {
  buildD6SyncPayload,
  D6_NOTE_SECTION,
  type D6DisclosureSnapshot,
} from '../composables/d6NoteSectionMap'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import type { ChecklistResponse } from '../composables/useD6FormData'
import type useD6CrossSheet from '../composables/useD6CrossSheet'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD6CrossSheet>
  variant: 'listed' | 'soe'
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const {
  listedSections, soeSections, showListed, showSoe, activeVariant,
  groupedDetails, addGroup, addGroupedDetailRow, updateGroupName, updateGroupedCell, removeGroupedRow,
  majorChangeRows, addMajorChangeRow, updateMajorChangeCell, removeMajorChangeRow,
  noteTexts,
} = useD6Disclosure({
  allResponses: allResponsesRef,
  crossSheet: props.crossSheet,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: async () => {},
  debouncedSave: props.debouncedSave,
})

if (props.variant) {
  activeVariant.value = props.variant
}

// ─── 导入导出（参照 D4-2）：重大变动表 + 组合明细表 ─────────────────────
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>

const majorChangeIe = useD6ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D6-note-major-change',
  sheetLabel: '重大变动',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})
const groupsIe = useD6ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D6-note-groups',
  sheetLabel: '组合明细',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onMajorChangeImport(file: File) { await majorChangeIe.importData(file) }
async function onGroupsImport(file: File) { await groupsIe.importData(file) }

const displayVariant = computed(() => {
  if (props.variant) return props.variant
  if (showListed.value && !showSoe.value) return 'listed'
  if (showSoe.value && !showListed.value) return 'soe'
  return activeVariant.value
})

const variantOptions = computed(() => {
  const opts = []
  if (showListed.value) opts.push({ label: '上市公司版', value: 'listed' })
  if (showSoe.value) opts.push({ label: '国企版', value: 'soe' })
  return opts
})

const LISTED_NOTE_MAP: Record<string, string> = {
  'listed-1': 'D6-note-listed-text-1',
  'listed-major-change': 'D6-note-listed-text-major-change',
  'listed-2': 'D6-note-listed-text-2',
  'listed-3': 'D6-note-listed-text-3',
  'listed-4': 'D6-note-listed-text-4',
  'listed-5': 'D6-note-listed-text-5',
}

const SOE_NOTE_MAP: Record<string, string> = {
  'soe-1': 'D6-note-soe-text-1',
  'soe-2': 'D6-note-soe-text-2',
  'soe-3': 'D6-note-soe-text-3',
}

function getListedNoteKey(sectionKey: string): string {
  return LISTED_NOTE_MAP[sectionKey] || ''
}

function getSoeNoteKey(sectionKey: string): string {
  return SOE_NOTE_MAP[sectionKey] || ''
}

function updateNoteText(key: string, value: string) {
  if (!key) return
  noteTexts.value = { ...noteTexts.value, [key]: value }
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 空表补足占位空行（至少2行），避免"No Data"太丑；占位行 _isPad=true 不渲染输入控件 */
function padRows<T extends { rowId?: string }>(rows: T[], min = 2): any[] {
  const out: any[] = [...(rows || [])]
  let i = 0
  while (out.length < min) {
    out.push({ rowId: `__pad-${i}__`, _isPad: true })
    i++
  }
  return out
}

function fmtPct(rate: number): string {
  if (!rate) return '-'
  return `${(rate * 100).toFixed(1)}%`
}

function fmtPct100(rate: number): string {
  if (!rate) return '-'
  return `${rate.toFixed(2)}%`
}

// ─── 同步到附注 / 跳转回附注 ─────────────────────────────────────────────────
const router = useRouter()
const isSyncing = ref(false)

function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'D6', target)
  if (route) router.push(route)
}

function findSection(sections: any[], key: string): any {
  return (sections || []).find((s) => s.sectionKey === key) || { rows: [] }
}

/** 底稿披露表 → 附注单向推送（当前 displayVariant 对应上市/国企）。 */
async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  isSyncing.value = true
  const variant = displayVariant.value as DisclosureVariant
  try {
    let snapshot: D6DisclosureSnapshot
    if (variant === 'soe') {
      const cls = findSection(soeSections.value, 'soe-1')
      const imp = findSection(soeSections.value, 'soe-2')
      snapshot = {
        classRows: (cls.rows ?? []).map((r: any) => ({
          label: r.label,
          endBookBalance: r.endBookBalance, endImpairment: r.endImpairment, endBookValue: r.endBookValue,
          priorBookBalance: r.priorBookBalance, priorImpairment: r.priorImpairment, priorBookValue: r.priorBookValue,
        })),
        soeImpairmentRows: (imp.rows ?? []).map((r: any) => ({
          label: r.label, priorBalance: r.priorBalance, provision: r.provision,
          reversal: r.reversal, writeOff: r.writeOff, endBalance: r.endBalance, reason: r.reason,
        })),
        majorChangeRows: majorChangeRows.value.map((r: any) => ({ label: r.label, amount: r.amount, reason: r.reason })),
        notes: { ...noteTexts.value },
      }
    } else {
      const cls = findSection(listedSections.value, 'listed-1')
      const prov = findSection(listedSections.value, 'listed-2')
      const single = findSection(listedSections.value, 'listed-3')
      const change = findSection(listedSections.value, 'listed-5')
      snapshot = {
        classRows: (cls.rows ?? []).map((r: any) => ({
          label: r.label,
          endBookBalance: r.endBookBalance, endImpairment: r.endImpairment, endBookValue: r.endBookValue,
          priorBookBalance: r.priorBookBalance, priorImpairment: r.priorImpairment, priorBookValue: r.priorBookValue,
        })),
        majorChangeRows: majorChangeRows.value.map((r: any) => ({ label: r.label, amount: r.amount, reason: r.reason })),
        impairmentProvisionRows: (prov.rows ?? []).map((r: any) => ({
          label: r.label, endBalance: r.endBalance, endPercentage: r.endPercentage,
          endAmount: r.endAmount, endLossRate: r.endLossRate,
        })),
        singleItems: (single.rows ?? []).map((r: any) => ({
          label: r.label, balance: r.balance, provision: r.provision, lossRate: r.lossRate, reason: r.reason,
        })),
        groups: groupedDetails.value.map((g: any) => ({
          groupName: g.groupName,
          rows: (g.rows ?? []).map((r: any) => ({ label: r.label, balance: r.balance, provision: r.provision, lossRate: r.lossRate })),
        })),
        changeRows: (change.rows ?? []).map((r: any) => ({
          label: r.label, provision: r.provision, reversal: r.reversal, writeOff: r.writeOff, reason: r.reason,
        })),
        notes: { ...noteTexts.value },
      }
    }
    const payload = buildD6SyncPayload(variant, props.wpId || '', null, snapshot)
    const result: any = await http.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = result?.data ?? result
    const rows = Number(data?.rows_synced ?? 0)
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: {
        wpCode: 'D6',
        accountCode: '1402',
        projectId: props.projectId,
        section: variant,
        sectionIds: [D6_NOTE_SECTION[variant]],
      },
    }))
    ElMessage.success(`已同步 ${rows} 行到附注模块「${D6_NOTE_SECTION[variant]} 合同资产」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

// 保存后自动同步（防抖/非阻塞/失败静默/只读 gate）
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onUnmounted(() => autoSync.cancelPending())
let autoSyncArmed = false
watch(
  [noteTexts, majorChangeRows, groupedDetails, listedSections, soeSections],
  () => {
    if (!autoSyncArmed) { autoSyncArmed = true; return }
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  },
  { deep: true },
)
</script>

<style scoped>
.d6-disclosure { padding: 16px; }
.d6-disclosure :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d6-disclosure :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
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
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }

/* 工具栏 */
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
.chip-wrap { display: inline-flex; align-items: center; }

.disclosure-card {
  margin-bottom: 24px;
  padding: 16px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}
.section-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: #303133; }

/* 重大变动情形说明（准则指引琥珀块） */
.amber-context {
  margin-top: 12px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 4px;
  padding: 8px 12px;
}
.amber-context summary { cursor: pointer; font-weight: 500; color: #e6a23c; }
.amber-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.7; }
.amber-content p { margin: 4px 0; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; cursor: help; }
.sub-toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.group-block { margin-bottom: 12px; }
.group-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.group-name { font-weight: 600; font-size: var(--wp-font-size, 13px); }
.note-block { margin-top: 12px; }
.note-label { font-size: var(--wp-font-size, 13px); color: #606266; margin-bottom: 6px; }
</style>
