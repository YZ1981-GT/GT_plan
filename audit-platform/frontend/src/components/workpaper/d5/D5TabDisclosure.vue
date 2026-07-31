<template>
<div class="d5-disclosure">
    <!-- 同步状态条 -->
    <GtWpDisclosureSyncBar :project-id="projectId" :year="auditYear" :wp-code="'D5'" :sheet-name="activeVariant === 'soe' ? '附注披露信息（国企）' : '附注披露信息（上市公司）'" />

    <!-- 工具栏：同步到附注 + 跳转回附注 -->
    <div class="d5-disclosure-toolbar">
      <el-button type="primary" plain size="small" :loading="isSyncing" :disabled="isReadonly"
        title="将披露表的表格与文本框内容同步到附注模块（五、6/八、6 应收款项融资）"
        @click="syncToDisclosureNotes">同步到附注</el-button>
      <el-dropdown split-button type="default" size="small" :disabled="!projectId"
        @click="jumpToNote(activeVariant)"
        @command="jumpToNote">
        ↩ 跳转回附注（{{ activeVariant === 'soe' ? '八、6' : '五、6' }}）
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="listed">上市版（五、6）</el-dropdown-item>
            <el-dropdown-item command="soe">国企版（八、6）</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 应收款项融资（科目1124）为以公允价值计量且其变动计入其他综合收益（FVOCI）的金融资产，附注按上市公司版/国企版分别披露。</p>
        <p>2. 分类表期末/期初数取自 D5-1 审定表（浅蓝背景为跨sheet自动取数），减值准备变动按公式：期末余额 = 上年末 + 本期计提 − 转回 − 核销。</p>
        <p>3. 上市公司版需披露分类构成、减值准备变动、已质押应收票据及已背书/贴现但尚未到期的应收票据（终止确认）；国企版仅需披露分类信息。</p>
        <p>4. 应收票据票面金额或应收账款余额 − 公允价值变动 = 期末公允价值；披露文本将双向回写至附注模块，请与审定表、减值测算保持一致。</p>
      </div>
    </details>

    <!-- 版本切换（上市公司版 / 国企版） -->
    <div class="variant-toolbar" v-if="showListed && showSoe">
      <el-segmented
        v-model="activeVariant"
        :options="variantOptions"
        size="small"
      />
    </div>

    <!-- ═══════════════ 上市公司版 ═══════════════ -->
    <template v-if="activeVariant === 'listed' && showListed">
      <div v-for="section in listedSections" :key="section.sectionKey" class="disclosure-card">
        <h4 v-if="section.label" class="section-title">{{ section.label }}</h4>

        <!-- Section 1: 分类表 -->
        <template v-if="section.sectionKey === 'listed-classification'">
          <el-table :data="section.rows" size="small" border>
            <!-- 列头取源模板 A8：项  目 / 期末余额 / 上年年末余额（与附注列头同口径） -->
            <el-table-column prop="label" label="项  目" width="240">
              <template #default="{ row }">
                <span :class="{ 'oci-label': row.rowId === 'listed-cls-oci' }">
                  {{ row.label }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="期末余额" width="140" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell" title="来源：D5-1审定表">
                  {{ fmtAmount(row.endAmount) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="上年年末余额" width="140" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell" title="来源：D5-1审定表">
                  {{ fmtAmount(row.priorAmount) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
          <!-- 说明 -->
          <div class="note-block">
            <div class="note-label">说明：</div>
            <el-input
              v-model="noteTexts['listed-1']"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 6 }"
              :disabled="isReadonly"
              placeholder="对应收款项融资分类的补充说明..."
            />
          <div class="note-actions">
            <el-button size="small" :loading="aiLoadingSection === 'listed-1'" :disabled="isReadonly"
              @click="runAi('listed-1')">🤖 AI</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReview('listed-1')">💬 复核</el-button>
          </div>
          </div>
          <!-- 编制提示 -->
          <details class="guidance-hint">
            <summary>📋 编制提示</summary>
            <div class="hint-content">
              按CAS22金融工具确认和计量，以公允价值计量且其变动计入其他综合收益的金融资产（FVOCI）
              应在附注中披露账面价值分类构成。
            </div>
          </details>
        </template>

        <!-- Section 2: 减值准备变动 -->
        <template v-if="section.sectionKey === 'listed-impairment'">
          <el-table :data="impairmentRows" size="small" border>
            <el-table-column label="项目" width="140">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  :model-value="row.itemName"
                  size="small"
                  placeholder="项目名称"
                  @change="(val: string) => onImpairmentCellChange(row.rowId, 'itemName', val)"
                />
                <span v-else>{{ row.itemName }}</span>
              </template>
            </el-table-column>
            <el-table-column label="上年末" width="110" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.priorEnd"
                  :controls="false"
                  size="small"
                  style="width:100%"
                  @change="(val: number) => onImpairmentCellChange(row.rowId, 'priorEnd', val ?? 0)"
                />
                <span v-else>{{ fmtAmount(row.priorEnd) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本期计提" width="110" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.provision"
                  :controls="false"
                  size="small"
                  style="width:100%"
                  @change="(val: number) => onImpairmentCellChange(row.rowId, 'provision', val ?? 0)"
                />
                <span v-else>{{ fmtAmount(row.provision) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="转回" width="110" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.reversal"
                  :controls="false"
                  size="small"
                  style="width:100%"
                  @change="(val: number) => onImpairmentCellChange(row.rowId, 'reversal', val ?? 0)"
                />
                <span v-else>{{ fmtAmount(row.reversal) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="核销" width="110" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.writeOff"
                  :controls="false"
                  size="small"
                  style="width:100%"
                  @change="(val: number) => onImpairmentCellChange(row.rowId, 'writeOff', val ?? 0)"
                />
                <span v-else>{{ fmtAmount(row.writeOff) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期末" width="110" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span class="auto-calc">{{ fmtAmount(row.endBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="60" align="center">
              <template #default="{ row }">
                <el-button
                  v-if="!isReadonly"
                  type="danger"
                  text
                  size="small"
                  @click="impairmentRemoveRow(row.rowId)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-button
            size="small"
            :disabled="isReadonly"
            style="margin-top: 8px"
            @click="impairmentAddRow"
          >
            添加行
          </el-button>
          <!-- 说明 -->
          <div class="note-block">
            <div class="note-label">说明：</div>
            <el-input
              v-model="noteTexts['listed-2']"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 6 }"
              :disabled="isReadonly"
              placeholder="对减值准备变动的补充说明..."
            />
          <div class="note-actions">
            <el-button size="small" :loading="aiLoadingSection === 'listed-2'" :disabled="isReadonly"
              @click="runAi('listed-2')">🤖 AI</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReview('listed-2')">💬 复核</el-button>
          </div>
          </div>
          <!-- 编制提示 -->
          <details class="guidance-hint">
            <summary>📋 编制提示</summary>
            <div class="hint-content">
              公式：期末余额 = 上年末 + 本期计提 - 收回转回 - 核销。
              按CAS22/ECL模型确认减值准备，披露变动明细。
            </div>
          </details>
        </template>

        <!-- Section 3: 已质押 + 已背书贴现 + 说明 -->
        <template v-if="section.sectionKey === 'listed-notes'">
          <!-- (2) 期末已质押的应收票据 -->
          <div class="sub-section-title">(2) 期末本公司已质押的应收票据</div>
          <el-table :data="pledgedDisplayRows" size="small" border style="margin-bottom: 16px">
            <el-table-column prop="label" label="种类" width="180">
              <template #default="{ row }">
                <span :class="{ 'subtotal-label': row.isTotal }">{{ row.label }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期末已质押金额" width="180" align="right">
              <template #default="{ row, $index }">
                <span v-if="row.isTotal" class="subtotal-label">{{ fmtAmount(row.pledgedAmount) }}</span>
                <el-input-number
                  v-else-if="!isReadonly"
                  :model-value="row.pledgedAmount"
                  :controls="false"
                  size="small"
                  style="width:100%"
                  @change="(val: number) => updatePledged($index, val ?? 0)"
                />
                <span v-else>{{ fmtAmount(row.pledgedAmount) }}</span>
              </template>
            </el-table-column>
          </el-table>

          <!-- (3) 期末已背书或贴现但尚未到期的应收票据 -->
          <div class="sub-section-title">(3) 期末本公司已背书或贴现但尚未到期的应收票据</div>
          <el-table :data="endorsedDisplayRows" size="small" border style="margin-bottom: 16px">
            <el-table-column prop="label" label="种类" width="180">
              <template #default="{ row }">
                <span :class="{ 'subtotal-label': row.isTotal }">{{ row.label }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期末终止确认金额" width="180" align="right">
              <template #default="{ row, $index }">
                <span v-if="row.isTotal" class="subtotal-label">{{ fmtAmount(row.derecognizedAmount) }}</span>
                <el-input-number
                  v-else-if="!isReadonly"
                  :model-value="row.derecognizedAmount"
                  :controls="false"
                  size="small"
                  style="width:100%"
                  @change="(val: number) => updateEndorsed($index, 'derecognizedAmount', val ?? 0)"
                />
                <span v-else>{{ fmtAmount(row.derecognizedAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期末未终止确认金额" width="180" align="right">
              <template #default="{ row, $index }">
                <span v-if="row.isTotal" class="subtotal-label">{{ fmtAmount(row.notDerecognizedAmount) }}</span>
                <el-input-number
                  v-else-if="!isReadonly"
                  :model-value="row.notDerecognizedAmount"
                  :controls="false"
                  size="small"
                  style="width:100%"
                  @change="(val: number) => updateEndorsed($index, 'notDerecognizedAmount', val ?? 0)"
                />
                <span v-else>{{ fmtAmount(row.notDerecognizedAmount) }}</span>
              </template>
            </el-table-column>
          </el-table>

          <!-- 说明 -->
          <div class="note-block">
            <div class="note-label">说明：</div>
            <el-input
              v-model="noteTexts['listed-3']"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 7 }"
              :disabled="isReadonly"
              placeholder="说明应收款项融资本期增减变动及公允价值变动情况；无单项计提减值准备的银行承兑汇票，评价其是否不存在重大信用风险..."
            />
          <div class="note-actions">
            <el-button size="small" :loading="aiLoadingSection === 'listed-3'" :disabled="isReadonly"
              @click="runAi('listed-3')">🤖 AI</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReview('listed-3')">💬 复核</el-button>
          </div>
          </div>
          <!-- 编制提示 -->
          <details class="guidance-hint">
            <summary>📋 编制提示</summary>
            <div class="hint-content">
              依《企业会计准则第23号——金融资产转移》，终止确认的应收票据列示其终止确认的金额及相关利得/损失。
              银行承兑汇票信用风险已随背书/贴现转移的（票据到期前主要风险和报酬已转移），可判断终止确认；
              商业承兑汇票信用风险未转移的，不终止确认（参考证监会《2014年上市公司年报会计监管报告》）。上表种类可自行添加项目。
            </div>
          </details>
        </template>
      </div>
    </template>

    <!-- ═══════════════ 国企版 ═══════════════ -->
    <template v-if="activeVariant === 'soe' && showSoe">
      <div v-for="section in soeSections" :key="section.sectionKey" class="disclosure-card">
        <h4 class="section-title">{{ section.label }}</h4>

        <!-- 列头取源模板国企 A7：项  目 / 期末余额 / 期初余额（与附注列头同口径） -->
        <el-table :data="section.rows" size="small" border>
          <el-table-column prop="label" label="项  目" width="200" />
          <el-table-column label="期末余额" width="140" align="right">
            <template #default="{ row }">
              <span class="cross-sheet-cell" title="来源：D5-1审定表">
                {{ fmtAmount(row.endAmount) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="期初余额" width="140" align="right">
            <template #default="{ row }">
              <span class="cross-sheet-cell" title="来源：D5-1审定表">
                {{ fmtAmount(row.priorAmount) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
        <!-- 合计行 -->
        <div v-if="section.totalRow" class="total-summary">
          合计 — 期末余额：{{ fmtAmount(section.totalRow.endAmount) }}，期初余额：{{ fmtAmount(section.totalRow.priorAmount) }}
        </div>
        <!-- 说明 -->
        <div class="note-block">
          <div class="note-label">说明：</div>
          <el-input
            v-model="noteTexts['soe-1']"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :disabled="isReadonly"
            placeholder="国企版分类披露补充说明..."
          />
          <div class="note-actions">
            <el-button size="small" :loading="aiLoadingSection === 'soe-1'" :disabled="isReadonly"
              @click="runAi('soe-1')">🤖 AI</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReview('soe-1')">💬 复核</el-button>
          </div>
        </div>
        <!-- 编制提示 -->
        <details class="guidance-hint">
          <summary>📋 编制提示</summary>
          <div class="hint-content">
            国企版按《国有企业财务决算报告附注》披露应收款项融资分类构成及期初期末余额；
            下列减值准备/质押/背书贴现披露表样参考应收账款、应收票据科目附注结构，数据取自 D5-2 应收款项融资明细表。
          </div>
        </details>
      </div>

      <!-- 参考披露表样（红框指引：表样参考D1/D2科目附注，数据取自D5-2明细表） -->
      <div class="disclosure-card">
        <details class="amber-context">
          <summary>📖 披露编制指引（参考其他科目附注表样）</summary>
          <div class="amber-content">
            <p><strong>1. 应收账款相关：</strong>本期计提、收回或转回的减值准备情况参考附注八、5、（3）披露；本期实际核销的应收款项融资情况参考附注八、5、（4）披露。</p>
            <p><strong>2. 应收票据相关：</strong>期末质押、背书或贴现且在资产负债表日尚未到期、出票人未履约、坏账准备计提情况参考附注八、4、（2）（3）（4）（5）（6）披露。</p>
            <p class="amber-note">下列表样借鉴应收账款/应收票据科目附注结构，数据取自 D5-2 应收款项融资明细表。</p>
          </div>
        </details>

        <!-- (1) 本期计提、收回或转回的减值准备情况 -->
        <div class="sub-section-title">(1) 本期计提、收回或转回的减值准备情况</div>
        <el-table :data="impairmentRows" size="small" border style="margin-bottom: 16px">
          <el-table-column label="项目" width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.itemName" size="small" placeholder="项目名称"
                @change="(val: string) => onImpairmentCellChange(row.rowId, 'itemName', val)" />
              <span v-else>{{ row.itemName }}</span>
            </template>
          </el-table-column>
          <el-table-column label="上年末" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.priorEnd" :controls="false" size="small" style="width:100%"
                @change="(val: number) => onImpairmentCellChange(row.rowId, 'priorEnd', val ?? 0)" />
              <span v-else>{{ fmtAmount(row.priorEnd) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期计提" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.provision" :controls="false" size="small" style="width:100%"
                @change="(val: number) => onImpairmentCellChange(row.rowId, 'provision', val ?? 0)" />
              <span v-else>{{ fmtAmount(row.provision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="收回或转回" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.reversal" :controls="false" size="small" style="width:100%"
                @change="(val: number) => onImpairmentCellChange(row.rowId, 'reversal', val ?? 0)" />
              <span v-else>{{ fmtAmount(row.reversal) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="核销" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.writeOff" :controls="false" size="small" style="width:100%"
                @change="(val: number) => onImpairmentCellChange(row.rowId, 'writeOff', val ?? 0)" />
              <span v-else>{{ fmtAmount(row.writeOff) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末" width="110" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="auto-calc">{{ fmtAmount(row.endBalance) }}</span></template>
          </el-table-column>
          <el-table-column label="操作" width="60" align="center">
            <template #default="{ row }">
              <el-button v-if="!isReadonly" type="danger" text size="small" @click="impairmentRemoveRow(row.rowId)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button size="small" :disabled="isReadonly" style="margin-bottom: 16px" @click="impairmentAddRow">添加行</el-button>

        <!-- (2) 期末已质押的应收票据 -->
        <div class="sub-section-title">(2) 期末本公司已质押的应收票据</div>
        <el-table :data="pledgedDisplayRows" size="small" border style="margin-bottom: 16px">
          <el-table-column prop="label" label="种类" width="180">
            <template #default="{ row }"><span :class="{ 'subtotal-label': row.isTotal }">{{ row.label }}</span></template>
          </el-table-column>
          <el-table-column label="期末已质押金额" width="180" align="right">
            <template #default="{ row, $index }">
              <span v-if="row.isTotal" class="subtotal-label">{{ fmtAmount(row.pledgedAmount) }}</span>
              <el-input-number v-else-if="!isReadonly" :model-value="row.pledgedAmount" :controls="false" size="small" style="width:100%"
                @change="(val: number) => updatePledged($index, val ?? 0)" />
              <span v-else>{{ fmtAmount(row.pledgedAmount) }}</span>
            </template>
          </el-table-column>
        </el-table>

        <!-- (3) 期末已背书或贴现但尚未到期的应收票据 -->
        <div class="sub-section-title">(3) 期末本公司已背书或贴现但尚未到期的应收票据</div>
        <el-table :data="endorsedDisplayRows" size="small" border style="margin-bottom: 16px">
          <el-table-column prop="label" label="种类" width="180">
            <template #default="{ row }"><span :class="{ 'subtotal-label': row.isTotal }">{{ row.label }}</span></template>
          </el-table-column>
          <el-table-column label="期末终止确认金额" width="180" align="right">
            <template #default="{ row, $index }">
              <span v-if="row.isTotal" class="subtotal-label">{{ fmtAmount(row.derecognizedAmount) }}</span>
              <el-input-number v-else-if="!isReadonly" :model-value="row.derecognizedAmount" :controls="false" size="small" style="width:100%"
                @change="(val: number) => updateEndorsed($index, 'derecognizedAmount', val ?? 0)" />
              <span v-else>{{ fmtAmount(row.derecognizedAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末未终止确认金额" width="180" align="right">
            <template #default="{ row, $index }">
              <span v-if="row.isTotal" class="subtotal-label">{{ fmtAmount(row.notDerecognizedAmount) }}</span>
              <el-input-number v-else-if="!isReadonly" :model-value="row.notDerecognizedAmount" :controls="false" size="small" style="width:100%"
                @change="(val: number) => updateEndorsed($index, 'notDerecognizedAmount', val ?? 0)" />
              <span v-else>{{ fmtAmount(row.notDerecognizedAmount) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </template>
</div>
</template>

<script setup lang="ts">
/**
 * D5TabDisclosure.vue — D5 附注披露
 *
 * el-segmented 切换（上市公司版 | 国企版）
 * 上市公司版：3子节卡片（分类/减值变动/说明）
 * 国企版：1子节卡片（分类）
 * 跨sheet浅蓝色取数 + tooltip来源
 * 减值准备变动：动态行 + 公式（期末=上年末+计提-转回-核销）
 * 按applicable_standards自动显示/隐藏版本
 *
 * Task: 17.1
 * Requirements: 8.1-8.8
 */
import { ref, computed, inject, watch, toRef, onBeforeUnmount, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useDisclosureAutoSync } from '../composables/useDisclosureAutoSync'
import { useDisclosureNoteAi } from '../composables/useDisclosureNoteAi'
import { useD5Disclosure } from '../composables/useD5Disclosure'
import {
  buildD5SyncPayload,
  D5_NOTE_SECTION,
  D5_NOTE_TEXT_SECTIONS,
  type D5DisclosureSnapshot,
} from '../composables/d5NoteSectionMap'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import type { useD5CrossSheet } from '../composables/useD5CrossSheet'
import type { ChecklistResponse } from '../composables/useD5FormData'
import { useAuditContext } from '@/composables/useAuditContext'
import { checkNoteConsistencyGeneric } from '../composables/noteConsistencyCheck'
import GtWpDisclosureSyncBar from '../GtWpDisclosureSyncBar.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD5CrossSheet>
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const { year: auditYear } = useAuditContext()

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  listedSections,
  soeSections,
  showListed,
  showSoe,
  activeVariant,
  impairmentRows,
  impairmentAddRow,
  impairmentRemoveRow,
  noteTexts,
} = useD5Disclosure({
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  crossSheet: props.crossSheet,
})

// ─── 说明文本域的 AI 辅助 + 复核入口（共享 composable）──────────────────────
// 🔴 `section_id` 与后端 `review_dialog._SECTION_PROMPTS` 的键逐字一致，
// 未登记会回退通用 prompt（过短 → 诱导模型自造披露内容）。
const openReviewDialog = inject<any>('openReviewDialog', null)
const noteAi = useDisclosureNoteAi({
  wpId: toRef(props, 'wpId') as Ref<string>,
  isReadonly: () => props.isReadonly,
  getText: (k) => noteTexts.value?.[k] ?? '',
  setText: (k, text) => { noteTexts.value = { ...noteTexts.value, [k]: text } },
  buildSectionId: (k) => `d5-disclosure-${k}-note`,
  labelOf: (k) => D5_NOTE_TEXT_SECTIONS.find((s) => s.key === k)?.title ?? k,
  openReviewDialog,
})
const { aiLoadingSection, runAi, openReview } = noteAi

// ─── 保存后自动同步到附注（防抖/非阻塞/失败静默）──────────────────────────────
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())
watch(
  [listedSections, soeSections, impairmentRows, noteTexts],
  () => {
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  },
  { deep: true },
)

// ─── (2) 期末已质押的应收票据 ────────────────────────────────────────────────

interface PledgedRow { key: string; label: string; pledgedAmount: number }

const pledgedRows = ref<PledgedRow[]>([
  { key: 'bank', label: '银行承兑票据', pledgedAmount: 0 },
  { key: 'commercial', label: '商业承兑票据', pledgedAmount: 0 },
])

watch(
  () => allResponsesRef.value.get('D5-note-listed-pledged')?.remark,
  (val) => {
    if (val) {
      try {
        const parsed = JSON.parse(val)
        if (Array.isArray(parsed) && parsed.length > 0) pledgedRows.value = parsed
      } catch { /* ignore */ }
    }
  },
  { immediate: true },
)

watch(
  pledgedRows,
  (val) => { props.debouncedSave('D5-note-listed-pledged', { remark: JSON.stringify(val) }) },
  { deep: true },
)

function updatePledged(idx: number, value: number) {
  const arr = [...pledgedRows.value]
  arr[idx] = { ...arr[idx], pledgedAmount: value }
  pledgedRows.value = arr
}

const pledgedDisplayRows = computed(() => [
  ...pledgedRows.value.map(r => ({ ...r, isTotal: false })),
  {
    key: '__total__',
    label: '合计',
    pledgedAmount: pledgedRows.value.reduce((s, r) => s + (r.pledgedAmount || 0), 0),
    isTotal: true,
  },
])

// ─── (3) 期末已背书或贴现但尚未到期的应收票据 ────────────────────────────────

interface EndorsedRow { key: string; label: string; derecognizedAmount: number; notDerecognizedAmount: number }

const endorsedRows = ref<EndorsedRow[]>([
  { key: 'bank', label: '银行承兑票据', derecognizedAmount: 0, notDerecognizedAmount: 0 },
  { key: 'commercial', label: '商业承兑票据', derecognizedAmount: 0, notDerecognizedAmount: 0 },
])

watch(
  () => allResponsesRef.value.get('D5-note-listed-endorsed')?.remark,
  (val) => {
    if (val) {
      try {
        const parsed = JSON.parse(val)
        if (Array.isArray(parsed) && parsed.length > 0) endorsedRows.value = parsed
      } catch { /* ignore */ }
    }
  },
  { immediate: true },
)

watch(
  endorsedRows,
  (val) => { props.debouncedSave('D5-note-listed-endorsed', { remark: JSON.stringify(val) }) },
  { deep: true },
)

function updateEndorsed(idx: number, field: 'derecognizedAmount' | 'notDerecognizedAmount', value: number) {
  const arr = [...endorsedRows.value]
  arr[idx] = { ...arr[idx], [field]: value }
  endorsedRows.value = arr
}

const endorsedDisplayRows = computed(() => [
  ...endorsedRows.value.map(r => ({ ...r, isTotal: false })),
  {
    key: '__total__',
    label: '合计',
    derecognizedAmount: endorsedRows.value.reduce((s, r) => s + (r.derecognizedAmount || 0), 0),
    notDerecognizedAmount: endorsedRows.value.reduce((s, r) => s + (r.notDerecognizedAmount || 0), 0),
    isTotal: true,
  },
])

// ─── Variant Options ─────────────────────────────────────────────────────────

const variantOptions = computed(() => {
  const opts = []
  if (showListed.value) opts.push({ label: '上市公司版', value: 'listed' })
  if (showSoe.value) opts.push({ label: '国企版', value: 'soe' })
  return opts
})

// ─── Impairment Cell Editing ─────────────────────────────────────────────────

function onImpairmentCellChange(rowId: string, field: string, value: any) {
  const idx = impairmentRows.value.findIndex(r => r.rowId === rowId)
  if (idx === -1) return
  const row = { ...impairmentRows.value[idx] }
  ;(row as any)[field] = value
  const newRows = [...impairmentRows.value]
  newRows[idx] = row
  impairmentRows.value = newRows
}

// ─── Formatting Helpers ──────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 同步到附注 / 跳转回附注 ─────────────────────────────────────────────────
const router = useRouter()
const isSyncing = ref(false)

function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'D5', target)
  if (route) router.push(route)
}

/** 底稿披露表 → 附注单向推送（当前 activeVariant 对应上市/国企）。 */
async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  isSyncing.value = true
  const variant = activeVariant.value as DisclosureVariant
  try {
    let snapshot: D5DisclosureSnapshot
    if (variant === 'soe') {
      const sec = soeSections.value[0]
      snapshot = {
        mainRows: (sec?.rows ?? []).map((r) => ({ label: r.label, endAmount: r.endAmount, priorAmount: r.priorAmount })),
        mainTotal: sec?.totalRow ? { label: '合计', endAmount: sec.totalRow.endAmount, priorAmount: sec.totalRow.priorAmount } : undefined,
        notes: { 'soe-1': noteTexts.value['soe-1'] || '' },
      }
    } else {
      const cls = listedSections.value.find((s) => s.sectionKey === 'listed-classification')
      const sum = <K extends 'priorEnd' | 'provision' | 'reversal' | 'writeOff' | 'endBalance'>(k: K) =>
        impairmentRows.value.reduce((s, r) => s + (Number(r[k]) || 0), 0)
      snapshot = {
        mainRows: (cls?.rows ?? []).map((r) => ({ label: r.label, endAmount: r.endAmount, priorAmount: r.priorAmount })),
        impairment: {
          priorBalance: sum('priorEnd'),
          provision: sum('provision'),
          reversal: sum('reversal'),
          writeOff: sum('writeOff'),
          endBalance: sum('endBalance'),
        },
        pledgedRows: pledgedRows.value.map((r) => ({ label: r.label, pledgedAmount: r.pledgedAmount })),
        endorsedRows: endorsedRows.value.map((r) => ({ label: r.label, derecognizedAmount: r.derecognizedAmount, notDerecognizedAmount: r.notDerecognizedAmount })),
        notes: {
          'listed-1': noteTexts.value['listed-1'] || '',
          'listed-2': noteTexts.value['listed-2'] || '',
          'listed-3': noteTexts.value['listed-3'] || '',
        },
      }
    }
    const payload = buildD5SyncPayload(variant, props.wpId || '', null, snapshot)
    const result: any = await http.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = result?.data ?? result
    const rows = Number(data?.rows_synced ?? 0)
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: {
        wpCode: 'D5',
        accountCode: '1124',
        projectId: props.projectId,
        section: variant,
        sectionIds: [D5_NOTE_SECTION[variant]],
      },
    }))
    ElMessage.success(`已同步 ${rows} 行到附注模块「${D5_NOTE_SECTION[variant]} 应收款项融资」`)
    // 静默校对附注合计一致性
    const pageTotal = snapshot.mainTotal?.endAmount ?? 0
    checkNoteConsistencyGeneric(props.projectId, auditYear.value, D5_NOTE_SECTION[variant], pageTotal, true)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}


</script>

<style scoped>
.d5-disclosure {
  padding: 12px;
}
.d5-disclosure :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d5-disclosure :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 顶部编制提示 */
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
.guidance-content p {
  margin: 2px 0;
}

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}

.variant-toolbar {
  margin-bottom: 16px;
}

.disclosure-card {
  margin-bottom: 24px;
  padding: 16px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  color: #303133;
}

.sub-section-title {
  font-size: 13px;
  font-weight: 600;
  margin: 4px 0 8px;
  color: #606266;
}

/* 方法论琥珀块（红框指引） */
.amber-context {
  margin-bottom: 16px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 4px;
  padding: 8px 12px;
}
.amber-context summary {
  cursor: pointer;
  font-weight: 500;
  color: #e6a23c;
}
.amber-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.7;
}
.amber-content p {
  margin: 4px 0;
}
.amber-note {
  color: #b88230;
  font-style: italic;
}

.subtotal-label {
  font-weight: 700;
}

.cross-sheet-cell {
  background: #ecf5ff;
  padding: 2px 6px;
  border-radius: 2px;
  cursor: help;
}

.oci-label {
  color: #409eff;
}

.auto-calc {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 2px;
  color: #909399;
}

.total-summary {
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 4px;
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

.note-block {
  margin-top: 12px;
}

.note-actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
  justify-content: flex-end;
}

.note-label {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  margin-bottom: 6px;
}

.guidance-hint {
  margin-top: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
}

.guidance-hint summary {
  padding: 8px 12px;
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #409eff;
}

.guidance-hint .hint-content {
  padding: 8px 12px 12px;
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}

</style>
