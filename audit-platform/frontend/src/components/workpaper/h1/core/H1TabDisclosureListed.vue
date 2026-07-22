<template>
  <div class="h1-disc-listed">
    <el-alert type="info" :closable="false" show-icon class="objective">
      审计目标：按上市公司附注格式编制固定资产披露——汇总表、原值/折旧/减值变动、闲置、经营租出、未办妥产权证书、政府补助冲减及固定资产清理，与 H1-1/H1-2/H1-4/H1-16~19/H6 勾稽，并同步至附注「{{ noteSectionId }}」。
    </el-alert>

    <div class="toolbar">
      <div class="toolbar-left">
        <strong>附注披露信息（上市公司）</strong>
        <el-tag size="small" type="info" effect="plain">源模板 93 行</el-tag>
        <el-tag size="small" type="success" effect="plain">15、固定资产</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" :disabled="isReadonly" @click="pullFromSources">从审定/检查表取数</el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          @click="syncToNotes"
        >同步到附注</el-button>
        <el-dropdown trigger="click" @command="handleImportExport">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-json">导出 JSON 数据包</el-dropdown-item>
              <el-dropdown-item command="import-json" :disabled="isReadonly">导入 JSON 数据包</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input ref="jsonInputRef" type="file" accept=".json,application/json" style="display:none" @change="onJsonSelected" />
        <span class="chip-wrap"><GtIndexChip value="wp:H1-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H1-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H1-4" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H1-19" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip :value="`Note:${noteSectionId}`" :context-project-id="projectId" /></span>
        <GtReviewTrigger section-id="H1-disclosure-listed" />
      </div>
    </div>

    <!-- ══════ 15、固定资产 汇总 ══════ -->
    <section class="block">
      <h3 class="block-title">15、固定资产</h3>
      <el-table :data="summaryDisplay" border size="small" class="wp-table" style="max-width: 560px">
        <el-table-column label="项  目" min-width="160">
          <template #default="{ row }">
            <span :class="{ 'is-total': row.key === '__total__' }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.key !== '__total__' && !isReadonly"
              :model-value="row.endBalance"
              :controls="false"
              size="small"
              style="width:100%"
              @update:model-value="(v: number) => updateSummary(row.key, 'endBalance', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': row.key === '__total__' }">{{ fmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上年年末余额" width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.key !== '__total__' && !isReadonly"
              :model-value="row.priorBalance"
              :controls="false"
              size="small"
              style="width:100%"
              @update:model-value="(v: number) => updateSummary(row.key, 'priorBalance', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': row.key === '__total__' }">{{ fmt(row.priorBalance) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <p class="hint">合计自动勾稽；期末固定资产宜与变动表「期末账面价值」合计一致。</p>
    </section>

    <!-- ══════ （1）固定资产 ══════ -->
    <section class="block">
      <h3 class="block-title">（1）固定资产</h3>
      <h4 class="sub-title">①固定资产情况</h4>

      <div class="cat-bar" v-if="!isReadonly">
        <el-button size="small" @click="addCategory">+ 增加资产类别列</el-button>
        <span class="hint inline">源模板 E 列「……」：按被审计单位实际类别扩展（如电子设备、办公设备）</span>
      </div>

      <div class="movement-wrap">
        <el-table :data="movementRowDefs" border size="small" class="wp-table movement-table" :row-class-name="movementRowClass">
          <el-table-column label="项  目" min-width="200" fixed>
            <template #default="{ row }">
              <span :style="{ paddingLeft: `${row.indent * 12}px` }" :class="`kind-${row.kind}`">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column
            v-for="cat in categories"
            :key="cat.key"
            :label="cat.label"
            min-width="120"
            align="right"
          >
            <template #header>
              <div class="cat-header">
                <span>{{ cat.label }}</span>
                <el-button
                  v-if="!isReadonly && !isDefaultCat(cat.key)"
                  link
                  size="small"
                  type="danger"
                  @click="removeCategory(cat.key)"
                >删</el-button>
              </div>
            </template>
            <template #default="{ row }">
              <template v-if="row.kind === 'section'">—</template>
              <el-input-number
                v-else-if="row.editable && !isReadonly"
                :model-value="rawCell(movement, row.key, cat.key)"
                :controls="false"
                size="small"
                style="width:100%"
                @update:model-value="(v: number) => updateMovement(row.key, cat.key, v ?? 0)"
              />
              <span v-else class="formula-cell">{{ fmt(cellValue(movement, row, cat.key)) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="合  计" min-width="120" align="right" fixed="right">
            <template #default="{ row }">
              <span v-if="row.kind === 'section'">—</span>
              <span v-else class="formula-cell">{{ fmt(totalCellValue(movement, row, categories)) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>

    <!-- ══════ 提示区（源 R52–R58）：指引放合理位置 + 可编辑披露文本 ══════ -->
    <section class="block guidance-block">
      <h4 class="sub-title">披露提示与说明（减值 / 抵押 / 高价出售）</h4>
      <el-alert type="info" :closable="false" class="guide-alert">{{ H1_LISTED_GUIDANCE.impairment }}</el-alert>
      <el-alert type="warning" :closable="false" class="guide-alert warn">{{ H1_LISTED_GUIDANCE.impairmentNote }}</el-alert>
      <div class="note-field">
        <label>减值测试披露说明</label>
        <el-input
          v-model="noteImpairment"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          :placeholder="H1_LISTED_GUIDANCE.impairment"
          @change="scheduleSave"
        />
      </div>

      <el-alert type="info" :closable="false" class="guide-alert">{{ H1_LISTED_GUIDANCE.mortgage }}</el-alert>
      <div class="note-field">
        <div class="note-field-head">
          <label>抵押、担保固定资产情况</label>
          <div class="mortgage-actions">
            <span class="xref-chips">
              交叉核对：
              <GtIndexChip value="wp:L1" :context-project-id="projectId" />
              <GtIndexChip value="wp:L3" :context-project-id="projectId" />
              <GtIndexChip value="wp:L4" :context-project-id="projectId" />
            </span>
            <el-button size="small" :disabled="isReadonly" @click="pullMortgage">从 H1-16/H1-17 同步抵押</el-button>
          </div>
        </div>
        <el-alert
          v-if="mortgageTotal > 0"
          type="warning"
          :closable="false"
          show-icon
          class="guide-alert warn"
          :title="`抵押/担保固定资产账面价值合计 ${fmt(mortgageTotal)}：须与借款质押披露（短期借款 L1 / 长期借款 L3 / 应付债券 L4）及或有事项（对外担保）一致核对，并在「所有权受限的固定资产」中列示。`"
        />
        <el-table v-if="mortgageRows.length" :data="mortgageRows" border size="small" class="wp-table" style="margin-bottom:8px">
          <el-table-column label="项目" min-width="160">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="scheduleSave" />
              <span v-else>{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="金额" width="130" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else>{{ fmt(row.amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="180">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.description" size="small" @change="scheduleSave" />
              <span v-else>{{ row.description }}</span>
            </template>
          </el-table-column>
        </el-table>
        <el-input
          v-model="noteMortgage"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          :placeholder="H1_LISTED_GUIDANCE.mortgage"
          @change="scheduleSave"
        />
      </div>

      <el-alert type="info" :closable="false" class="guide-alert">{{ H1_LISTED_GUIDANCE.sale }}</el-alert>
      <div class="note-field">
        <label>明显高于账面价值出售交易说明</label>
        <el-input
          v-model="noteSale"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          :placeholder="H1_LISTED_GUIDANCE.sale"
          @change="scheduleSave"
        />
      </div>

      <el-alert type="info" :closable="false" class="guide-alert">{{ H1_LISTED_GUIDANCE.govSubsidyOtherDec }}</el-alert>
      <el-alert type="info" :closable="false" class="guide-alert">{{ H1_LISTED_GUIDANCE.mergeNet }}</el-alert>
    </section>

    <!-- ══════ ② 暂时闲置 ══════ -->
    <section class="block">
      <h4 class="sub-title">②暂时闲置的固定资产情况</h4>
      <el-alert type="warning" :closable="false" class="guide-alert warn">{{ H1_LISTED_GUIDANCE.idleAlert }}</el-alert>
      <div class="row-actions" v-if="!isReadonly">
        <el-button size="small" @click="addIdleRow">+ 添加行</el-button>
        <el-button size="small" @click="pullIdle">从 H1-4 同步闲置</el-button>
      </div>
      <el-table :data="idleDisplay" border size="small" class="wp-table">
        <el-table-column label="项  目" min-width="140">
          <template #default="{ row }">
            <span v-if="row.rowId === '__total__'" class="is-total">合  计</span>
            <el-input v-else-if="!isReadonly" v-model="row.name" size="small" @change="onIdleChange(row)" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面原值" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.cost" :controls="false" size="small" style="width:100%" @change="onIdleChange(row)" />
            <span v-else :class="{ 'formula-cell': row.rowId === '__total__' }">{{ fmt(row.cost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计折旧" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.dep" :controls="false" size="small" style="width:100%" @change="onIdleChange(row)" />
            <span v-else :class="{ 'formula-cell': row.rowId === '__total__' }">{{ fmt(row.dep) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值准备" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.impairment" :controls="false" size="small" style="width:100%" @change="onIdleChange(row)" />
            <span v-else :class="{ 'formula-cell': row.rowId === '__total__' }">{{ fmt(row.impairment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面价值" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmt(row.rowId === '__total__' ? row.bookValue : idleBookValue(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.remark" size="small" @change="scheduleSave" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60">
          <template #default="{ row }">
            <el-button v-if="row.rowId !== '__total__' && !row.isPreset" link type="danger" size="small" @click="removeIdle(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ══════ ③ 经营租出 ══════ -->
    <section class="block">
      <h4 class="sub-title">③通过经营租赁租出的固定资产</h4>
      <div class="row-actions" v-if="!isReadonly">
        <el-button size="small" @click="addLeaseRow">+ 添加行</el-button>
        <el-button size="small" :disabled="!leaseHint.count" @click="pullLease">从 H1-19 同步（{{ leaseHint.count }}）</el-button>
      </div>
      <el-table :data="leaseDisplay" border size="small" class="wp-table" style="max-width: 480px">
        <el-table-column label="项  目" min-width="160">
          <template #default="{ row }">
            <span v-if="row.rowId === '__total__'" class="is-total">合  计</span>
            <el-input v-else-if="!isReadonly" v-model="row.name" size="small" @change="scheduleSave" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面价值" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.bookValue" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
            <span v-else class="formula-cell">{{ fmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60">
          <template #default="{ row }">
            <el-button v-if="row.rowId !== '__total__' && !row.isPreset" link type="danger" size="small" @click="removeLease(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ══════ ④ 未办妥产权证书 ══════ -->
    <section class="block">
      <h4 class="sub-title">④未办妥产权证书的固定资产情况</h4>
      <p class="guide-text">{{ H1_LISTED_GUIDANCE.titleCert }}</p>
      <div class="row-actions" v-if="!isReadonly">
        <el-button size="small" @click="addTitleRow">+ 添加行</el-button>
        <el-button size="small" @click="pullTitleCert">从 H1-16 同步无证房屋</el-button>
      </div>
      <el-table :data="titleCertRows" border size="small" class="wp-table">
        <el-table-column label="项  目" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="scheduleSave" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面价值" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookValue" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
            <span v-else>{{ fmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未办妥产权证书原因" min-width="200">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.reason" size="small" @change="scheduleSave" />
            <span v-else>{{ row.reason }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="titleCertRows.splice($index, 1); scheduleSave()">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ══════ ⑤ 政府补助 ══════ -->
    <section class="block">
      <h4 class="sub-title">⑤本期冲减固定资产账面价值的政府补助</h4>
      <div class="gov-row">
        <span>金额（元）</span>
        <el-input-number
          v-model="govSubsidy.amount"
          :controls="false"
          size="small"
          :disabled="isReadonly"
          @change="scheduleSave"
        />
      </div>
      <el-input
        v-model="govSubsidy.text"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 4 }"
        :disabled="isReadonly"
        :placeholder="formatGovSubsidyLine(govSubsidy.amount)"
        @change="scheduleSave"
      />
      <p class="guide-text">{{ H1_LISTED_GUIDANCE.govSubsidyHint }}</p>
    </section>

    <!-- ══════ ⑥ 已提足折旧仍在使用 ══════ -->
    <section class="block">
      <h4 class="sub-title">⑥已提足折旧仍继续使用的固定资产</h4>
      <p class="guide-text">{{ H1_LISTED_GUIDANCE.fullyDepreciated }}</p>
      <div class="row-actions" v-if="!isReadonly">
        <el-button size="small" @click="addFullyDepRow">+ 添加行</el-button>
        <el-button size="small" @click="pullFullyDepreciated">从 H1-2 带入候选（净值≈残值）</el-button>
      </div>
      <el-table :data="fullyDepDisplay" border size="small" class="wp-table" style="max-width: 620px">
        <el-table-column label="类别 / 项目" min-width="180">
          <template #default="{ row }">
            <span v-if="row.rowId === '__total__'" class="is-total">合  计</span>
            <el-input v-else-if="!isReadonly" v-model="row.name" size="small" @change="scheduleSave" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面原值" width="150" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.cost" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
            <span v-else class="formula-cell">{{ fmt(row.cost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="160">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.remark" size="small" @change="scheduleSave" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60">
          <template #default="{ row }">
            <el-button v-if="row.rowId !== '__total__'" link type="danger" size="small" @click="removeFullyDep(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ══════ （2）固定资产清理 ══════ -->
    <section class="block">
      <h3 class="block-title">（2）固定资产清理</h3>
      <div class="row-actions" v-if="!isReadonly">
        <el-button size="small" type="default" :loading="isPullingH6" data-testid="h1-listed-pull-h6" @click="pullClearingFromH6">
          从 H6 同步清理
        </el-button>
        <el-button size="small" @click="addClearingRow">+ 添加行</el-button>
      </div>
      <el-table :data="clearingDisplay" border size="small" class="wp-table">
        <el-table-column label="项  目" min-width="140">
          <template #default="{ row }">
            <span v-if="row.rowId === '__total__'" class="is-total">合  计</span>
            <el-input v-else-if="!isReadonly" v-model="row.name" size="small" @change="scheduleSave" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.endBalance" :controls="false" size="small" style="width:100%" @change="onClearingChange" />
            <span v-else class="formula-cell">{{ fmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上年年末余额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.priorBalance" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
            <span v-else class="formula-cell">{{ fmt(row.priorBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转入清理的原因" min-width="180">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.reason" size="small" @change="scheduleSave" />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60">
          <template #default="{ row }">
            <el-button v-if="row.rowId !== '__total__'" link type="danger" size="small" @click="removeClearing(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="note-field" style="margin-top:10px">
        <label>超 1 年清理进展说明</label>
        <el-input
          v-model="noteClearing"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          :placeholder="H1_LISTED_GUIDANCE.clearingProgress"
          @change="scheduleSave"
        />
      </div>
    </section>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>结构严格对齐源 xlsx「附注披露信息（上市公司）」：汇总 → 变动表 → 提示文本 → 闲置/租出/产权/补助 → 清理。</li>
        <li>蓝色提示保留在对应区块上方；可编辑说明用 placeholder 预填源模板指引，勿写入默认 value。</li>
        <li>变动表：期末=期初+本期增加−本期减少；账面价值=原值−累计折旧−减值；合计列=各类之和。</li>
        <li>「同步到附注」推送至「{{ noteSectionId }}」各子表；编制提示语不写入附注正文。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H1TabDisclosureListed — 附注披露信息（上市公司）
 * 读源模板 93 行精确重建；与附注模块五、22 联动。
 */
import { ref, reactive, computed, inject, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { H1_NOTE_SECTION } from '../../composables/h1NoteSectionMap'
import { buildH1ListedSyncPayloads, type H1ListedSyncSnapshot } from '../../composables/h1DisclosureSyncPayload'
import { pullH6ClearingForH1Listed } from '../../composables/h1SoeClearingH6Pull'
import {
  buildListedDisclosurePack,
  downloadJsonPack,
  parseListedDisclosurePack,
} from '../../composables/h1DisclosurePack'
import {
  H1_LISTED_DEFAULT_CATEGORIES,
  H1_LISTED_GUIDANCE,
  H1_LISTED_ITEM,
  H1_LISTED_MOVEMENT_ROWS,
  cellValue,
  createDefaultGovSubsidy,
  createDefaultIdleRows,
  createDefaultLeaseRows,
  createDefaultSummary,
  formatGovSubsidyLine,
  idleBookValue,
  isMovementEmpty,
  newRowId,
  num,
  rawCell,
  seedMovementFromAdjudication,
  setCell,
  sumClearing,
  sumIdle,
  sumLease,
  sumFullyDep,
  deriveFullyDepreciatedFromDetail,
  summaryTotal,
  totalCellValue,
  type ClearingRow,
  type FullyDepRow,
  type H1ListedCategory,
  type IdleRow,
  type LeaseOutRow,
  type MortgageRow,
  type MovementCellMap,
  type SummaryRow,
  type TitleCertRow,
} from '../../composables/h1ListedDisclosureModel'
import { mapOperatingToDisclosureRows, type OperatingLeaseRow } from '../../composables/useH1LeaseCheck'
import {
  mapMortgagedVehiclesToDisclosureRows,
  mapMortgagedBuildingsToDisclosureRows,
  mergeRestrictedDisclosureRows,
  type VehicleRow,
  type BuildingRow,
} from '../../composables/useH1TitleCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const isReadonly = computed(() => props.isReadonly)
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const noteSectionId = H1_NOTE_SECTION.listed
const isSyncing = ref(false)
const jsonInputRef = ref<HTMLInputElement | null>(null)

const summary = reactive<SummaryRow[]>(createDefaultSummary())
const categories = ref<H1ListedCategory[]>(H1_LISTED_DEFAULT_CATEGORIES.map((c) => ({ ...c })))
const movement = ref<MovementCellMap>({})
const idleRows = ref<IdleRow[]>(createDefaultIdleRows())
const leaseRows = ref<LeaseOutRow[]>(createDefaultLeaseRows())
const titleCertRows = ref<TitleCertRow[]>([
  { rowId: newRowId('title'), name: '', bookValue: 0, reason: '' },
  { rowId: newRowId('title'), name: '', bookValue: 0, reason: '' },
  { rowId: newRowId('title'), name: '', bookValue: 0, reason: '' },
])
const clearingRows = ref<ClearingRow[]>([
  { rowId: newRowId('clr'), name: '', endBalance: 0, priorBalance: 0, reason: '' },
])
const mortgageRows = ref<MortgageRow[]>([])
const fullyDepRows = ref<FullyDepRow[]>([])
const govSubsidy = reactive(createDefaultGovSubsidy())
const noteImpairment = ref('')
const noteMortgage = ref('')
const noteSale = ref('')
const noteClearing = ref('')

const movementRowDefs = H1_LISTED_MOVEMENT_ROWS

const summaryDisplay = computed(() => {
  const t = summaryTotal(summary)
  return [...summary, { key: '__total__' as const, label: '合  计', endBalance: t.endBalance, priorBalance: t.priorBalance }]
})

const idleDisplay = computed(() => {
  const t = sumIdle(idleRows.value)
  return [...idleRows.value, { rowId: '__total__', name: '合计', cost: t.cost, dep: t.dep, impairment: t.impairment, bookValue: t.bookValue, remark: '' }]
})

const leaseDisplay = computed(() => {
  return [...leaseRows.value, { rowId: '__total__', name: '合计', bookValue: sumLease(leaseRows.value) }]
})

const clearingDisplay = computed(() => {
  const t = sumClearing(clearingRows.value)
  return [...clearingRows.value, { rowId: '__total__', name: '合计', endBalance: t.endBalance, priorBalance: t.priorBalance, reason: '' }]
})

const fullyDepDisplay = computed(() => {
  return [...fullyDepRows.value, { rowId: '__total__', name: '合计', cost: sumFullyDep(fullyDepRows.value), remark: '' }]
})

/** 抵押、担保固定资产账面价值合计（供与借款质押/或有事项交叉核对） */
const mortgageTotal = computed(() => mortgageRows.value.reduce((s, r) => s + num(r.amount), 0))

const leaseHint = computed(() => {
  const item = props.allResponses.get('H1-19-rows')
  let rows: OperatingLeaseRow[] = []
  if (item?.remark) {
    try {
      const parsed = JSON.parse(item.remark)
      rows = Array.isArray(parsed) ? parsed : []
    } catch { rows = [] }
  }
  return { count: rows.length, rows }
})

function isDefaultCat(key: string) {
  return (H1_LISTED_DEFAULT_CATEGORIES as readonly { key: string }[]).some((c) => c.key === key)
}

function movementRowClass({ row }: { row: { kind: string } }) {
  if (row.kind === 'section') return 'row-section'
  if (row.kind === 'calc' || row.kind === 'book' || row.kind === 'subtotal') return 'row-calc'
  return ''
}

function fmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function parseJson<T>(id: string, fb: T): T {
  const raw = props.allResponses.get(id)?.remark
  if (!raw) return fb
  try {
    const p = JSON.parse(raw)
    return (p ?? fb) as T
  } catch { return fb }
}

function load() {
  const sumSaved = parseJson<SummaryRow[] | null>(H1_LISTED_ITEM.summary, null)
  if (Array.isArray(sumSaved) && sumSaved.length) {
    for (const s of sumSaved) {
      const row = summary.find((r) => r.key === s.key)
      if (row) Object.assign(row, s)
    }
  }

  const cats = parseJson<H1ListedCategory[] | null>(H1_LISTED_ITEM.categories, null)
  if (Array.isArray(cats) && cats.length) categories.value = cats

  const mov = parseJson<MovementCellMap | null>(H1_LISTED_ITEM.movement, null)
  if (mov && typeof mov === 'object') movement.value = mov

  const idle = parseJson<IdleRow[] | null>(H1_LISTED_ITEM.idle, null)
  if (Array.isArray(idle) && idle.length) idleRows.value = idle

  const lease = parseJson<LeaseOutRow[] | null>(H1_LISTED_ITEM.leaseOut, null)
    ?? parseJson<LeaseOutRow[] | null>(H1_LISTED_ITEM.leaseOutLegacy, null)
  if (Array.isArray(lease) && lease.length) {
    // 兼容旧动态行 {name, amount}
    leaseRows.value = lease.map((r: any, i) => ({
      rowId: r.rowId || `lease-${i}`,
      name: r.name || '',
      bookValue: num(r.bookValue ?? r.amount),
      isPreset: r.isPreset,
    }))
  }

  const title = parseJson<TitleCertRow[] | null>(H1_LISTED_ITEM.titleCert, null)
  if (Array.isArray(title) && title.length) titleCertRows.value = title

  const clearing = parseJson<ClearingRow[] | null>(H1_LISTED_ITEM.clearing, null)
  if (Array.isArray(clearing) && clearing.length) clearingRows.value = clearing

  const mort = parseJson<MortgageRow[] | null>(H1_LISTED_ITEM.mortgageRows, null)
    ?? parseJson<any[] | null>(H1_LISTED_ITEM.mortgageLegacy, null)
  if (Array.isArray(mort) && mort.length) {
    mortgageRows.value = mort.map((r: any, i) => ({
      rowId: r.rowId || `mort-${i}`,
      name: r.name || '',
      amount: num(r.amount),
      description: r.description || '',
      remark: r.remark || '',
    }))
  }

  const gov = parseJson<typeof govSubsidy | null>(H1_LISTED_ITEM.govSubsidy, null)
  if (gov) Object.assign(govSubsidy, gov)

  const fdep = parseJson<FullyDepRow[] | null>(H1_LISTED_ITEM.fullyDepreciated, null)
  if (Array.isArray(fdep) && fdep.length) {
    fullyDepRows.value = fdep.map((r: any, i) => ({
      rowId: r.rowId || `fdep-${i}`,
      name: r.name || '',
      cost: num(r.cost),
      remark: r.remark || '',
    }))
  }

  const ni = props.allResponses.get(H1_LISTED_ITEM.noteImpairment)?.remark
  if (ni) noteImpairment.value = ni
  const nm = props.allResponses.get(H1_LISTED_ITEM.noteMortgage)?.remark
  if (nm) noteMortgage.value = nm
  const ns = props.allResponses.get(H1_LISTED_ITEM.noteSale)?.remark
  if (ns) noteSale.value = ns
  const nc = props.allResponses.get(H1_LISTED_ITEM.noteClearing)?.remark
  if (nc) noteClearing.value = nc

  // 变动表全空时从 H1-1 seed
  if (isMovementEmpty(movement.value)) {
    seedFromAdjudication(false)
  }
  // 汇总表固定资产期末为空时，用变动表账面价值合计
  const fa = summary.find((r) => r.key === 'fixed_assets')!
  if (num(fa.endBalance) === 0) {
    const bookEnd = H1_LISTED_MOVEMENT_ROWS.find((d) => d.key === 'book_end')!
    fa.endBalance = totalCellValue(movement.value, bookEnd, categories.value)
    const bookBegin = H1_LISTED_MOVEMENT_ROWS.find((d) => d.key === 'book_begin')!
    fa.priorBalance = totalCellValue(movement.value, bookBegin, categories.value)
  }
}

let _saveTimer: ReturnType<typeof setTimeout> | null = null
function scheduleSave() {
  if (isReadonly.value) return
  if (_saveTimer) clearTimeout(_saveTimer)
  _saveTimer = setTimeout(() => {
    _saveTimer = null
    persistAll()
  }, 600)
}

function persistAll() {
  saveResponse(H1_LISTED_ITEM.summary, [...summary])
  saveResponse(H1_LISTED_ITEM.categories, categories.value)
  saveResponse(H1_LISTED_ITEM.movement, movement.value)
  saveResponse(H1_LISTED_ITEM.idle, idleRows.value)
  saveResponse(H1_LISTED_ITEM.leaseOut, leaseRows.value)
  saveResponse(H1_LISTED_ITEM.titleCert, titleCertRows.value)
  saveResponse(H1_LISTED_ITEM.clearing, clearingRows.value)
  saveResponse(H1_LISTED_ITEM.mortgageRows, mortgageRows.value)
  saveResponse(H1_LISTED_ITEM.fullyDepreciated, fullyDepRows.value)
  saveResponse(H1_LISTED_ITEM.govSubsidy, { ...govSubsidy })
  saveResponse(H1_LISTED_ITEM.noteImpairment, noteImpairment.value)
  saveResponse(H1_LISTED_ITEM.noteMortgage, noteMortgage.value)
  saveResponse(H1_LISTED_ITEM.noteSale, noteSale.value)
  saveResponse(H1_LISTED_ITEM.noteClearing, noteClearing.value)

  eventBus.emit('disclosure:note-text-updated' as any, {
    wp_code: 'H1',
    variant: 'listed',
    section: noteSectionId,
    text: noteImpairment.value || noteMortgage.value || '',
  })
}

function handleImportExport(cmd: string) {
  if (cmd === 'export-json') {
    const pack = buildListedDisclosurePack({
      summary: [...summary],
      categories: categories.value,
      movement: movement.value,
      idle: idleRows.value,
      leaseOut: leaseRows.value,
      titleCert: titleCertRows.value,
      clearing: clearingRows.value,
      mortgage: mortgageRows.value,
      govSubsidy: { ...govSubsidy },
      notes: {
        impairment: noteImpairment.value,
        mortgage: noteMortgage.value,
        sale: noteSale.value,
        clearing: noteClearing.value,
      },
    })
    downloadJsonPack(`H1_附注上市_${new Date().toISOString().slice(0, 10)}.json`, pack)
    ElMessage.success('已导出 JSON 数据包')
  } else if (cmd === 'import-json') {
    jsonInputRef.value?.click()
  }
}

async function onJsonSelected(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0]
  ;(ev.target as HTMLInputElement).value = ''
  if (!file) return
  try {
    await ElMessageBox.confirm(`即将导入「${file.name}」，将覆盖当前上市附注数据。确认？`, '导入确认', {
      type: 'warning',
    })
    const parsed = parseListedDisclosurePack(JSON.parse(await file.text()))
    if (!parsed.ok) {
      ElMessage.error(parsed.message)
      return
    }
    const pack = parsed.pack
    if (Array.isArray(pack.summary) && pack.summary.length) {
      for (const s of pack.summary as SummaryRow[]) {
        const row = summary.find((r) => r.key === s.key)
        if (row) Object.assign(row, s)
      }
    }
    if (Array.isArray(pack.categories) && pack.categories.length) {
      categories.value = pack.categories as H1ListedCategory[]
    }
    if (pack.movement && typeof pack.movement === 'object') {
      movement.value = pack.movement as MovementCellMap
    }
    if (Array.isArray(pack.idle)) idleRows.value = pack.idle as IdleRow[]
    if (Array.isArray(pack.leaseOut)) {
      leaseRows.value = (pack.leaseOut as any[]).map((r, i) => ({
        rowId: r.rowId || `lease-${i}`,
        name: r.name || '',
        bookValue: num(r.bookValue ?? r.amount),
        isPreset: r.isPreset,
      }))
    }
    if (Array.isArray(pack.titleCert)) titleCertRows.value = pack.titleCert as TitleCertRow[]
    if (Array.isArray(pack.clearing)) clearingRows.value = pack.clearing as ClearingRow[]
    if (Array.isArray(pack.mortgage)) {
      mortgageRows.value = (pack.mortgage as any[]).map((r, i) => ({
        rowId: r.rowId || `mort-${i}`,
        name: r.name || '',
        amount: num(r.amount),
        description: r.description || '',
        remark: r.remark || '',
      }))
    }
    if (pack.govSubsidy && typeof pack.govSubsidy === 'object') {
      Object.assign(govSubsidy, pack.govSubsidy)
    }
    noteImpairment.value = pack.notes?.impairment ?? ''
    noteMortgage.value = pack.notes?.mortgage ?? ''
    noteSale.value = pack.notes?.sale ?? ''
    noteClearing.value = pack.notes?.clearing ?? ''
    persistAll()
    ElMessage.success('已导入上市附注数据包')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e?.message || '导入失败')
  }
}

function updateSummary(key: string, field: 'endBalance' | 'priorBalance', v: number) {
  const row = summary.find((r) => r.key === key)
  if (!row) return
  row[field] = num(v)
  scheduleSave()
}

function updateMovement(rowKey: string, catKey: string, v: number) {
  movement.value = setCell(movement.value, rowKey, catKey, v)
  scheduleSave()
}

async function addCategory() {
  try {
    const { value } = await ElMessageBox.prompt('输入资产类别名称', '增加列', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    const label = String(value || '').trim()
    if (!label) return
    if (categories.value.some((c) => c.label === label)) {
      ElMessage.warning('类别已存在')
      return
    }
    const key = `cat_${Date.now().toString(36)}`
    categories.value.push({ key, label })
    scheduleSave()
  } catch { /* cancel */ }
}

function removeCategory(key: string) {
  categories.value = categories.value.filter((c) => c.key !== key)
  scheduleSave()
}

function onIdleChange(row: IdleRow) {
  row.bookValue = idleBookValue(row)
  scheduleSave()
}

function addIdleRow() {
  idleRows.value.push({
    rowId: newRowId('idle'), name: '', cost: 0, dep: 0, impairment: 0, bookValue: 0, remark: '',
  })
  scheduleSave()
}
function removeIdle(id: string) {
  idleRows.value = idleRows.value.filter((r) => r.rowId !== id)
  scheduleSave()
}

function addFullyDepRow() {
  fullyDepRows.value.push({ rowId: newRowId('fdep'), name: '', cost: 0, remark: '' })
  scheduleSave()
}

function removeFullyDep(id: string) {
  fullyDepRows.value = fullyDepRows.value.filter((r) => r.rowId !== id)
  scheduleSave()
}

function pullFullyDepreciated() {
  const raw = props.allResponses.get('H1-2-rows')?.remark
  if (!raw) { ElMessage.warning('H1-2 暂无明细数据'); return }
  try {
    const rows = JSON.parse(raw)
    if (!Array.isArray(rows) || !rows.length) { ElMessage.warning('H1-2 无行'); return }
    const candidates = deriveFullyDepreciatedFromDetail(rows)
    if (!candidates.length) { ElMessage.info('未识别到已提足折旧仍在使用的资产（净值均高于残值）'); return }
    fullyDepRows.value = candidates
    scheduleSave()
    ElMessage.success(`已带入 ${candidates.length} 类候选，请核实账面原值与仍在使用状态`)
  } catch { ElMessage.warning('解析 H1-2 失败') }
}

function addLeaseRow() {
  leaseRows.value.push({ rowId: newRowId('lease'), name: '', bookValue: 0 })
  scheduleSave()
}
function removeLease(id: string) {
  leaseRows.value = leaseRows.value.filter((r) => r.rowId !== id)
  scheduleSave()
}

function addTitleRow() {
  titleCertRows.value.push({ rowId: newRowId('title'), name: '', bookValue: 0, reason: '' })
  scheduleSave()
}

function addClearingRow() {
  clearingRows.value.push({ rowId: newRowId('clr'), name: '', endBalance: 0, priorBalance: 0, reason: '' })
  scheduleSave()
}

const isPullingH6 = ref(false)

async function pullClearingFromH6() {
  if (!props.projectId || isReadonly.value) return
  isPullingH6.value = true
  try {
    const result = await pullH6ClearingForH1Listed(props.projectId)
    if (result.status !== 'ok') {
      ElMessage.warning(result.message || '未能从 H6 取数')
      return
    }
    const clr = summary.find((r) => r.key === 'clearing')
    if (result.clearingRows.length) {
      clearingRows.value = result.clearingRows.map((r) => ({ ...r }))
      const t = sumClearing(clearingRows.value)
      if (clr) {
        clr.endBalance = t.endBalance
        clr.priorBalance = t.priorBalance
      }
    } else if (clr) {
      clr.endBalance = result.clearingEnd
      clr.priorBalance = result.clearingPrior
    }
    if (result.clearingNoteDraft && !noteClearing.value.trim()) {
      noteClearing.value = result.clearingNoteDraft
    }
    scheduleSave()
    ElMessage.success(result.message)
  } finally {
    isPullingH6.value = false
  }
}

function removeClearing(id: string) {
  clearingRows.value = clearingRows.value.filter((r) => r.rowId !== id)
  scheduleSave()
}
function onClearingChange() {
  const clr = summary.find((r) => r.key === 'clearing')!
  const t = sumClearing(clearingRows.value)
  clr.endBalance = t.endBalance
  clr.priorBalance = t.priorBalance
  scheduleSave()
}

function seedFromAdjudication(force: boolean) {
  if (!force && !isMovementEmpty(movement.value)) return
  const costRaw = props.allResponses.get('H1-1-cost-rows')?.remark
  const depRaw = props.allResponses.get('H1-1-dep-rows')?.remark
  if (!costRaw) return
  try {
    const costRows = JSON.parse(costRaw)
    const depRows = depRaw ? JSON.parse(depRaw) : []
    if (!Array.isArray(costRows)) return
    const seeded = seedMovementFromAdjudication(costRows, Array.isArray(depRows) ? depRows : [], categories.value)
    categories.value = seeded.categories
    movement.value = seeded.movement
    const bookEnd = H1_LISTED_MOVEMENT_ROWS.find((d) => d.key === 'book_end')!
    const bookBegin = H1_LISTED_MOVEMENT_ROWS.find((d) => d.key === 'book_begin')!
    const fa = summary.find((r) => r.key === 'fixed_assets')!
    fa.endBalance = totalCellValue(movement.value, bookEnd, categories.value)
    fa.priorBalance = totalCellValue(movement.value, bookBegin, categories.value)
  } catch { /* ignore */ }
}

function pullIdle() {
  const raw = props.allResponses.get('H1-4-rows')?.remark
  if (!raw) { ElMessage.warning('H1-4 暂无闲置数据'); return }
  try {
    const rows = JSON.parse(raw)
    if (!Array.isArray(rows) || !rows.length) { ElMessage.warning('H1-4 无行'); return }
    const mapped: IdleRow[] = rows.map((r: any, i: number) => ({
      rowId: newRowId(`idle-h14-${i}`),
      name: r.name || r.assetName || r.category || `闲置资产${i + 1}`,
      cost: num(r.originalCost ?? r.cost ?? r.bookCost),
      dep: num(r.accDep ?? r.dep ?? r.accumulatedDep),
      impairment: num(r.impairment ?? r.impairmentProvision),
      bookValue: 0,
      remark: r.remark || '来源:H1-4',
    }))
    mapped.forEach((r) => { r.bookValue = idleBookValue(r) })
    // 保留预设空行结构：替换为同步结果
    idleRows.value = mapped.length ? mapped : createDefaultIdleRows()
    scheduleSave()
    ElMessage.success(`已从 H1-4 同步 ${mapped.length} 项`)
  } catch { ElMessage.warning('解析 H1-4 失败') }
}

function pullLease() {
  const disc = mapOperatingToDisclosureRows(leaseHint.value.rows)
  if (!disc.length) { ElMessage.warning('H1-19 无经营租出行'); return }
  leaseRows.value = disc.map((r, i) => ({
    rowId: r.rowId || newRowId(`lease-${i}`),
    name: r.name,
    bookValue: num(r.amount),
  }))
  scheduleSave()
  ElMessage.success(`已从 H1-19 同步 ${disc.length} 项`)
}

function pullMortgage() {
  const vRaw = props.allResponses.get('H1-17-rows')?.remark
  const bRaw = props.allResponses.get('H1-16-rows')?.remark
  let vehicles: VehicleRow[] = []
  let buildings: BuildingRow[] = []
  try { if (vRaw) vehicles = JSON.parse(vRaw) } catch { /* */ }
  try { if (bRaw) buildings = JSON.parse(bRaw) } catch { /* */ }
  const fromV = mapMortgagedVehiclesToDisclosureRows(Array.isArray(vehicles) ? vehicles : [])
  const fromB = mapMortgagedBuildingsToDisclosureRows(Array.isArray(buildings) ? buildings : [])
  const merged = mergeRestrictedDisclosureRows(
    mergeRestrictedDisclosureRows([], fromV as any, '来源:H1-17'),
    fromB as any,
    '来源:H1-16',
  )
  mortgageRows.value = merged.map((r) => ({
    rowId: r.rowId,
    name: r.name,
    amount: num(r.amount),
    description: r.description || '',
    remark: r.remark || '',
  }))
  if (!noteMortgage.value.trim() && mortgageRows.value.length) {
    noteMortgage.value = mortgageRows.value
      .map((r) => `${r.name}：抵押/担保金额 ${fmt(r.amount)}${r.description ? `（${r.description}）` : ''}`)
      .join('\n')
  }
  scheduleSave()
  ElMessage.success(`已同步抵押 ${mortgageRows.value.length} 项`)
}

function pullTitleCert() {
  const bRaw = props.allResponses.get('H1-16-rows')?.remark
  if (!bRaw) { ElMessage.warning('H1-16 暂无数据'); return }
  try {
    const buildings: BuildingRow[] = JSON.parse(bRaw)
    const src = (Array.isArray(buildings) ? buildings : []).filter((r) => {
      const concl = String(r.checkConclusion || r.conclusion || '')
      return concl.includes('未取得权证') || concl.includes('无证') || concl === '未办证'
    })
    if (!src.length) {
      ElMessage.warning('H1-16 未识别到无产权证书房屋；请手工登记')
      return
    }
    titleCertRows.value = src.map((r, i) => ({
      rowId: newRowId(`title-${i}`),
      name: r.name || r.address || `房屋${i + 1}`,
      bookValue: num(r.netValue || r.bookValue),
      reason: r.cipNote || r.diffReason || r.remark || '',
    }))
    scheduleSave()
    ElMessage.success(`已从 H1-16 同步 ${src.length} 项无证房屋`)
  } catch { ElMessage.warning('解析 H1-16 失败') }
}

function pullFromSources() {
  seedFromAdjudication(true)
  scheduleSave()
  ElMessage.success('已从 H1-1 审定表刷新变动表（可再点各子节同步按钮）')
}

function getSnapshot(): H1ListedSyncSnapshot {
  return {
    summary: [...summary],
    categories: categories.value,
    movement: movement.value,
    idle: idleRows.value,
    leaseOut: leaseRows.value,
    titleCert: titleCertRows.value,
    clearing: clearingRows.value,
    govSubsidy: { ...govSubsidy },
    noteImpairment: noteImpairment.value,
    noteMortgage: noteMortgage.value,
    noteSale: noteSale.value,
    noteClearing: noteClearing.value,
  }
}

async function syncToNotes() {
  if (isSyncing.value || isReadonly.value || !props.projectId || !props.wpId) return
  persistAll()
  const payloads = buildH1ListedSyncPayloads(props.wpId, [], getSnapshot())
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
</script>

<style scoped>
.h1-disc-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
.cat-bar, .row-actions { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.movement-wrap { overflow-x: auto; }
.cat-header { display: flex; align-items: center; justify-content: center; gap: 4px; }
.formula-cell {
  border-bottom: 1px dashed #909399; font-variant-numeric: tabular-nums;
  background: #fafafa; display: inline-block; min-width: 100%; text-align: right;
}
.is-total { font-weight: 700; }
.kind-section { font-weight: 700; }
.guidance-block { background: #f8fafc; border-radius: 8px; padding: 12px; border: 1px solid #ebeef5; }
.guide-alert { margin-bottom: 8px; }
.guide-alert.warn :deep(.el-alert__content) { color: #856404; }
.guide-text { color: #409eff; font-size: 12px; margin: 0 0 8px; }
.note-field { margin: 8px 0 14px; }
.note-field label { display: block; font-size: 12px; color: #606266; margin-bottom: 4px; font-weight: 500; }
.note-field-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; gap: 8px; flex-wrap: wrap; }
.mortgage-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.xref-chips { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: var(--el-text-color-secondary); }
.gov-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.compile-hint {
  margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff;
  border-radius: 4px; padding: 8px 12px; font-size: 12px; color: #606266;
}
.compile-hint summary { cursor: pointer; color: #409eff; margin-bottom: 6px; }
:deep(.row-section) { background: #f5f7fa; font-weight: 600; }
:deep(.row-calc) { background: #fafafa; }
</style>
