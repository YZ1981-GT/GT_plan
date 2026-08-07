<template>
  <div class="reliability-grid">
    <!-- 顶部精简说明 -->
    <div class="reliability-grid__header-note">
      <el-icon :size="14"><InfoFilled /></el-icon>
      <span>{{ RELIABILITY_HEADER_NOTE }}</span>
    </div>

    <!-- 工具栏 -->
    <div class="reliability-grid__toolbar">
      <el-button-group>
        <el-button size="small" type="primary" :icon="Plus" :disabled="readonly" @click="$emit('add')">
          新增
        </el-button>
        <el-button size="small" type="danger" :icon="Delete" :disabled="readonly || !selectedIds.length" @click="$emit('delete', selectedIds)">
          删除
        </el-button>
        <el-button size="small" :icon="Download" :disabled="readonly" @click="$emit('import-d01')">
          从 D0-1 带入电子回函
        </el-button>
      </el-button-group>
      <el-button-group>
        <el-button size="small" :disabled="readonly" @click="$emit('import-excel')">
          导入
        </el-button>
        <el-button size="small" @click="$emit('export-template')">
          导出模板
        </el-button>
        <el-button size="small" @click="$emit('export-data')">
          导出数据
        </el-button>
      </el-button-group>
      <div class="reliability-grid__toolbar-right">
        <el-button size="small" type="success" :disabled="readonly || !isDirty" @click="$emit('save')">
          保存
        </el-button>
      </div>
    </div>

    <!-- 网格表 -->
    <el-table
      ref="tableRef"
      :data="rows"
      border
      stripe
      size="small"
      highlight-current-row
      max-height="560"
      :row-class-name="getRowClassName"
      @selection-change="handleSelectionChange"
    >
      <el-table-column v-if="!readonly" type="selection" width="35" fixed="left" />

      <!-- ═══ 基本信息组 ═══ -->
      <el-table-column label="序号" prop="seq" width="55" align="center" fixed="left" />
      <el-table-column label="函证索引号" prop="confirm_index" width="110" fixed="left">
        <template #default="{ row }">
          <template v-if="!readonly">
            <el-input
              :model-value="row.confirm_index"
              size="small"
              placeholder="D0-"
              @change="(val: string) => $emit('update', row._row_id, 'confirm_index', val)"
            />
          </template>
          <span v-else class="reliability-grid__link" @click="$emit('jump-d01', row.confirm_index)">
            {{ row.confirm_index || '—' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column :label="RELIABILITY_COLUMN_LABELS.entity_name" prop="entity_name" width="150" show-overflow-tooltip>
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.entity_name"
            size="small"
            @change="(val: string) => $emit('update', row._row_id, 'entity_name', val)"
          />
          <span v-else>{{ row.entity_name || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="回函方式" prop="reply_method" width="100" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!readonly"
            :model-value="row.reply_method"
            size="small"
            placeholder="选择"
            @change="(val: string) => $emit('update', row._row_id, 'reply_method', val)"
          >
            <el-option value="传真" label="传真" />
            <el-option value="电子邮件" label="电子邮件" />
          </el-select>
          <template v-else>
            <el-tag v-if="row.reply_method" size="small" type="info">{{ row.reply_method }}</el-tag>
            <span v-else>—</span>
          </template>
        </template>
      </el-table-column>
      <!--
        🔴 源外增强列：六个可靠性 sheet 的源模板**都没有**「回函日期」列
           （`test_k0_source_template_facts.py::test_no_reply_date_column` 已钉死）。
           平台保留它是有意的（回函日期与「报告日前寄回原件」的时限判断相关），
           故按「显式登记 + 表头标注」处置，而非按循环隐藏 —— 隐藏会让 K0 与
           其余六枢纽的可靠性表列集分叉，且该列在任何枢纽都同样属源外。
        spec: k0-confirmation-source-alignment R9.3 / Property 24
      -->
      <el-table-column prop="reply_date" width="100" align="center">
        <template #header>
          <span>{{ SOURCE_EXTRA_RELIABILITY_COLUMNS[0].label }}</span>
          <el-tooltip placement="top" :content="SOURCE_EXTRA_RELIABILITY_COLUMNS[0].reason">
            <el-icon class="reliability-grid__src-extra-icon" :size="12"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-date-picker
            v-if="!readonly"
            :model-value="row.reply_date"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            style="width: 100%"
            @change="(val: string) => $emit('update', row._row_id, 'reply_date', val)"
          />
          <span v-else>{{ row.reply_date || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="RELIABILITY_COLUMN_LABELS.original_returned" prop="original_returned" width="80" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!readonly"
            :model-value="row.original_returned"
            size="small"
            @change="(val: string) => $emit('update', row._row_id, 'original_returned', val)"
          >
            <el-option value="是" label="是" />
            <el-option value="否" label="否" />
          </el-select>
          <el-tag v-else :type="row.original_returned === '是' ? 'success' : 'info'" size="small">
            {{ row.original_returned || '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="RELIABILITY_COLUMN_LABELS.direct_received" prop="direct_received" width="80" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!readonly"
            :model-value="row.direct_received"
            size="small"
            clearable
            placeholder="选择"
            @change="(val: string) => $emit('update', row._row_id, 'direct_received', val)"
          >
            <el-option value="是" label="是" />
            <el-option value="否" label="否" />
            <el-option value="不适用" label="不适用" />
          </el-select>
          <el-tag v-else :type="row.direct_received === '是' ? 'success' : 'info'" size="small">
            {{ row.direct_received || '—' }}
          </el-tag>
        </template>
      </el-table-column>

      <!--
        ═══ 期末未收回原件函证可靠性验证（源模板 X0-7 `G5:M5` 合并父表头） ═══

        🔴 R9.2：源模板把 `G:M` 七列合并在一个父表头「期末未收回原件函证可靠性验证」之下
        （后端 `test_k0_source_template_facts.py::TestReliability::test_14_columns_with_parent_header`
         已 openpyxl 直读断言 `G5:M5` 在 `merged_cells.ranges` 内）。改造前平台把这七列平铺，
        父表头缺失 ⇒ 审计师看不出「这组列只在未收回原件时才需要填」这一源模板语义。

        七列与源模板列字母的对应（`g0SharedComponentCoverage.spec.ts` Property 26 已逐列锁死）：
          G 被函证者身份确认（注1）      → identity_verified / identity_method
          H 发函及回函传真信息及验证      → fax_info_verify
          I 发函邮箱                    → send_email
          J 回函邮箱                    → reply_email
          K 邮箱可靠性验证（注2）        → email_verified / email_domain
          L 是否致电被函证者确认          → phone_called / phone_source
          M 对函证信息可靠性的考虑（注3） → reliability_consideration
        平台把 G/K/L 各拆成「勾选 + 明细」两列（录入更细），故子列数多于 7。
      -->
      <el-table-column :label="RELIABILITY_PARENT_HEADER" align="center">
      <!-- ═══ 验证组（条件列：寄回原件=否 展开，=是 灰掉） ═══ -->
      <el-table-column :label="RELIABILITY_COLUMN_LABELS.identity_verified" width="90" align="center">
        <template #header>
          <span>{{ RELIABILITY_COLUMN_LABELS.identity_verified }}</span>
          <el-tooltip placement="top">
            <template #content>
              <div class="reliability-grid__tooltip-content">
                <strong>{{ tooltipMap['注1']?.title }}</strong>
                <ul>
                  <li v-for="(item, idx) in tooltipMap['注1']?.items" :key="idx">{{ item }}</li>
                </ul>
              </div>
            </template>
            <el-icon :size="12" class="reliability-grid__tooltip-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <template v-if="!isVerificationDisabled(row)">
            <el-checkbox
              v-if="!readonly"
              :model-value="row.identity_verified"
              @change="(val: boolean) => $emit('update', row._row_id, 'identity_verified', val)"
            />
            <el-icon v-else-if="row.identity_verified" color="var(--el-color-success)"><Select /></el-icon>
            <span v-else class="reliability-grid__empty">—</span>
          </template>
          <span v-else class="reliability-grid__disabled">免验证</span>
        </template>
      </el-table-column>

      <el-table-column  prop="identity_method" width="110">
        <template #header>
          <span>{{ SOURCE_EXTRA_RELIABILITY_COLUMNS[1].label }}</span>
          <el-tooltip placement="top" :content="SOURCE_EXTRA_RELIABILITY_COLUMNS[1].reason">
            <el-icon class="reliability-grid__src-extra-icon" :size="12"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <template v-if="!isVerificationDisabled(row)">
            <el-select
              v-if="!readonly"
              :model-value="row.identity_method"
              size="small"
              clearable
              placeholder="选择方式"
              @change="(val: string) => $emit('update', row._row_id, 'identity_method', val)"
            >
              <el-option value="电话确认" label="电话确认" />
              <el-option value="邮件确认" label="邮件确认" />
              <el-option value="见面确认" label="见面确认" />
              <el-option value="系统确认" label="系统确认" />
            </el-select>
            <span v-else>{{ row.identity_method || '—' }}</span>
          </template>
          <span v-else class="reliability-grid__disabled">—</span>
        </template>
      </el-table-column>

      <el-table-column :label="RELIABILITY_COLUMN_LABELS.email_verified" width="90" align="center">
        <template #header>
          <span>{{ RELIABILITY_COLUMN_LABELS.email_verified }}</span>
          <el-tooltip placement="top" :width="360">
            <template #content>
              <div class="reliability-grid__tooltip-content">
                <strong>{{ tooltipMap['注2']?.title }}</strong>
                <ul>
                  <li v-for="(item, idx) in tooltipMap['注2']?.items" :key="idx">{{ item }}</li>
                </ul>
                <a
                  v-if="tooltipMap['注2']?.link"
                  :href="tooltipMap['注2'].link.url"
                  target="_blank"
                  class="reliability-grid__tooltip-link"
                >
                  {{ tooltipMap['注2'].link.label }} ↗
                </a>
              </div>
            </template>
            <el-icon :size="12" class="reliability-grid__tooltip-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <template v-if="!isVerificationDisabled(row)">
            <el-checkbox
              v-if="!readonly"
              :model-value="row.email_verified"
              @change="(val: boolean) => $emit('update', row._row_id, 'email_verified', val)"
            />
            <el-icon v-else-if="row.email_verified" color="var(--el-color-success)"><Select /></el-icon>
            <span v-else class="reliability-grid__empty">—</span>
          </template>
          <span v-else class="reliability-grid__disabled">免验证</span>
        </template>
      </el-table-column>

      <el-table-column label="邮箱域名" prop="email_domain" width="180">
        <template #default="{ row }">
          <template v-if="!isVerificationDisabled(row)">
            <div class="reliability-grid__email-cell">
              <el-input
                v-if="!readonly"
                :model-value="row.email_domain"
                size="small"
                placeholder="如 @company.com"
                @change="(val: string) => $emit('update', row._row_id, 'email_domain', val)"
              />
              <span v-else>{{ row.email_domain || '—' }}</span>
              <el-tooltip
                v-if="row.email_domain"
                :content="emailReliabilityTag(row.email_domain).tooltip"
                placement="top"
              >
                <el-tag :type="emailReliabilityTag(row.email_domain).type" size="small" disable-transitions>
                  {{ emailReliabilityTag(row.email_domain).label }}
                </el-tag>
              </el-tooltip>
            </div>
          </template>
          <span v-else class="reliability-grid__disabled">—</span>
        </template>
      </el-table-column>

      <el-table-column :label="RELIABILITY_COLUMN_LABELS.phone_called" prop="phone_called" width="70" align="center">
        <template #default="{ row }">
          <template v-if="!isVerificationDisabled(row)">
            <el-checkbox
              v-if="!readonly"
              :model-value="row.phone_called"
              @change="(val: boolean) => $emit('update', row._row_id, 'phone_called', val)"
            />
            <el-icon v-else-if="row.phone_called" color="var(--el-color-success)"><Select /></el-icon>
            <span v-else class="reliability-grid__empty">—</span>
          </template>
          <span v-else class="reliability-grid__disabled">—</span>
        </template>
      </el-table-column>

      <el-table-column  prop="phone_source" width="110">
        <template #header>
          <span>{{ SOURCE_EXTRA_RELIABILITY_COLUMNS[2].label }}</span>
          <el-tooltip placement="top" :content="SOURCE_EXTRA_RELIABILITY_COLUMNS[2].reason">
            <el-icon class="reliability-grid__src-extra-icon" :size="12"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <template v-if="!isVerificationDisabled(row)">
            <el-input
              v-if="!readonly"
              :model-value="row.phone_source"
              size="small"
              placeholder="工商/官网/独立来源"
              @change="(val: string) => $emit('update', row._row_id, 'phone_source', val)"
            />
            <span v-else>{{ row.phone_source || '—' }}</span>
          </template>
          <span v-else class="reliability-grid__disabled">—</span>
        </template>
      </el-table-column>

      <el-table-column  prop="reliability_note" min-width="150" show-overflow-tooltip>
        <template #header>
          <span>{{ SOURCE_EXTRA_RELIABILITY_COLUMNS[3].label }}</span>
          <el-tooltip placement="top" :content="SOURCE_EXTRA_RELIABILITY_COLUMNS[3].reason">
            <el-icon class="reliability-grid__src-extra-icon" :size="12"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <template v-if="!isVerificationDisabled(row)">
            <el-input
              v-if="!readonly"
              :model-value="row.reliability_note"
              size="small"
              placeholder="验证说明"
              @change="(val: string) => $emit('update', row._row_id, 'reliability_note', val)"
            />
            <span v-else>{{ row.reliability_note || '—' }}</span>
          </template>
          <span v-else class="reliability-grid__disabled">—</span>
        </template>
      </el-table-column>

      <!-- ═══ 回函核实补充（X0-7 源模板列） ═══ -->
      <el-table-column label="发函邮箱" prop="send_email" width="140" show-overflow-tooltip>
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.send_email"
            size="small"
            placeholder="发函邮箱"
            @change="(val: string) => $emit('update', row._row_id, 'send_email', val)"
          />
          <span v-else>{{ row.send_email || '—' }}</span>
        </template>
      </el-table-column>
      <!--
        回函邮箱：带域名可靠性实时判定（源模板 F0-7 注2「从私人电子信箱发送的回函不可靠」）
        私人域名（qq/163/gmail 等 30+）标红、公司域名标绿、无法识别标灰
      -->
      <el-table-column label="回函邮箱" prop="reply_email" width="200" show-overflow-tooltip>
        <template #header>
          <span>回函邮箱</span>
          <el-tooltip placement="top" :width="320">
            <template #content>
              <div style="line-height:1.6">
                <strong>回函邮箱可靠性（注2）</strong><br />
                1. 从私人电子信箱（如 163/qq/gmail）发送的回函<strong>不可靠</strong>——无法确认发件人身份与授权<br />
                2. 工作邮箱验证：确认域名与被询证单位官方域名一致，且该邮箱属于有权回复人员<br />
                3. 系统按域名自动初判，最终判断仍需审计师复核
              </div>
            </template>
            <span style="cursor:help;color:var(--el-color-primary);margin-left:2px">ⓘ</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <div class="reliability-grid__email-cell">
            <el-input
              v-if="!readonly"
              :model-value="row.reply_email"
              size="small"
              placeholder="回函邮箱"
              @change="(val: string) => $emit('update', row._row_id, 'reply_email', val)"
            />
            <span v-else>{{ row.reply_email || '—' }}</span>
            <el-tooltip
              v-if="row.reply_email"
              :content="emailReliabilityTag(row.reply_email).tooltip"
              placement="top"
            >
              <el-tag :type="emailReliabilityTag(row.reply_email).type" size="small" disable-transitions>
                {{ emailReliabilityTag(row.reply_email).label }}
              </el-tag>
            </el-tooltip>
          </div>
        </template>
      </el-table-column>
      <el-table-column :label="RELIABILITY_COLUMN_LABELS.fax_info_verify" prop="fax_info_verify" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.fax_info_verify"
            size="small"
            placeholder="传真号及验证过程"
            @change="(val: string) => $emit('update', row._row_id, 'fax_info_verify', val)"
          />
          <span v-else>{{ row.fax_info_verify || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="RELIABILITY_COLUMN_LABELS.reliability_consideration" prop="reliability_consideration" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.reliability_consideration"
            size="small"
            placeholder="对回函信息可靠性的考虑"
            @change="(val: string) => $emit('update', row._row_id, 'reliability_consideration', val)"
          />
          <span v-else>{{ row.reliability_consideration || '—' }}</span>
        </template>
      </el-table-column>
      </el-table-column>
      <!-- ═══ 「期末未收回原件函证可靠性验证」父表头结束（源 G5:M5） ═══ -->

      <!-- ═══ 结论组 ═══ -->
      <el-table-column :label="RELIABILITY_COLUMN_LABELS.conclusion_status" width="120" align="center">
        <template #header>
          <span>{{ RELIABILITY_COLUMN_LABELS.conclusion_status }}</span>
          <el-tooltip placement="top">
            <template #content>
              <div class="reliability-grid__tooltip-content">
                <strong>{{ tooltipMap['注3']?.title }}</strong>
                <ul>
                  <li v-for="(item, idx) in tooltipMap['注3']?.items" :key="idx">{{ item }}</li>
                </ul>
              </div>
            </template>
            <el-icon :size="12" class="reliability-grid__tooltip-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-select
            v-if="!readonly"
            :model-value="row.conclusion_status"
            size="small"
            clearable
            placeholder="选择结论"
            :disabled="isVerificationDisabled(row)"
            @change="(val: string) => $emit('update', row._row_id, 'conclusion_status', val)"
          >
            <el-option value="可靠" label="可靠" />
            <el-option value="部分可靠需补充" label="部分可靠需补充" />
            <el-option value="不可靠" label="不可靠" />
          </el-select>
          <!--
            系统初判建议（R6.4）：仅在**尚未填结论**时出现，点击采纳。
            🔴 不自动写入、已填值不覆盖 —— 源模板注2 第 3 条明确
            「系统按域名自动初判，最终判断仍需审计师复核」。
          -->
          <div v-if="!readonly && shouldOfferSuggestion(row)" class="reliability-grid__suggest">
            <el-tooltip placement="top">
              <template #content>
                <div class="reliability-grid__tooltip-content">
                  <strong>系统初判：{{ suggestionOf(row)?.status }}</strong>
                  <div>{{ suggestionOf(row)?.reason }}</div>
                  <ul v-if="suggestionOf(row)?.blockers?.length">
                    <li v-for="(b, i) in suggestionOf(row)!.blockers" :key="i">{{ b }}</li>
                  </ul>
                  <div>点击采纳后可再手工调整。</div>
                </div>
              </template>
              <el-tag
                size="small"
                effect="plain"
                :type="suggestionTagType(suggestionOf(row)!.status)"
                class="reliability-grid__suggest-tag"
                @click="applySuggestion(row)"
              >初判：{{ suggestionOf(row)?.status }}</el-tag>
            </el-tooltip>
          </div>
          <template v-else-if="readonly">
            <el-tag
              v-if="row.conclusion_status"
              size="small"
              :type="conclusionTagType(row.conclusion_status)"
            >
              {{ row.conclusion_status }}
            </el-tag>
            <span v-else-if="isVerificationDisabled(row)" class="reliability-grid__disabled">免验证</span>
            <span v-else class="reliability-grid__empty">未评定</span>
          </template>
        </template>
      </el-table-column>

      <!-- 来源标识 -->
      <el-table-column label="来源" width="60" align="center">
        <template #default="{ row }">
          <el-tag v-if="row._source === 'auto'" size="small" type="primary" effect="plain">
            自动
          </el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Plus, Delete, Download, InfoFilled, QuestionFilled, Select } from '@element-plus/icons-vue'
import type { ReliabilityRow } from './reliabilityTypes'
import {
  FIELD_TOOLTIPS_D07,
  RELIABILITY_HEADER_NOTE,
  RELIABILITY_PARENT_HEADER,
} from './reliabilityNotes'
/**
 * 列标签源模板用词 + 源外增强列登记（R9.3 / R9.4）。
 *
 * 🔴 六个可见的可靠性 sheet 表头逐字相同 ⇒ 一份映射七枢纽通用，**不按循环分叉**
 *    （立项写的「按循环控制 `reply_date` 可见性」经实证不成立，理由见
 *    `reliabilityColumnLabels.ts` 文件头）。
 */
import {
  RELIABILITY_COLUMN_LABELS,
  RELIABILITY_COLUMN_SOURCE_LABELS,
  SOURCE_EXTRA_RELIABILITY_COLUMNS,
  reliabilitySourceLabel,
} from './reliabilityColumnLabels'
// 邮箱域名可靠性判定（源模板 X0-7 注2：私人电子信箱回函不可靠）
import { emailReliabilityTag } from '@/utils/emailDomainCheck'
// 结论自动推导（R6.4）：只给建议，采纳与否由审计师决定
import {
  deriveReliabilityConclusion,
  shouldOfferSuggestion,
  suggestionTagType,
  type ReliabilityConclusionSuggestion,
} from './reliabilityConclusionDerive'

/** 建议缓存（模板里多处引用同一行的建议，避免重复计算） */
function suggestionOf(row: ReliabilityRow): ReliabilityConclusionSuggestion | null {
  return deriveReliabilityConclusion(row)
}

/** 采纳系统初判（写入 conclusion_status，之后仍可手工改） */
function applySuggestion(row: ReliabilityRow) {
  const s = deriveReliabilityConclusion(row)
  if (!s || !row._row_id) return
  emit('update', row._row_id, 'conclusion_status', s.status)
}

const props = defineProps<{
  rows: ReliabilityRow[]
  readonly: boolean
  isDirty: boolean
  isVerificationDisabled: (row: ReliabilityRow) => boolean
  getRowQualityStatus: (row: ReliabilityRow) => 'ok' | 'warning' | 'danger'
}>()

const emit = defineEmits<{
  (e: 'add'): void
  (e: 'delete', ids: string[]): void
  (e: 'save'): void
  (e: 'update', rowId: string, field: string, value: any): void
  (e: 'import-d01'): void
  (e: 'import-excel'): void
  (e: 'export-template'): void
  (e: 'export-data'): void
  (e: 'jump-d01', confirmIndex: string): void
}>()

const tableRef = ref()
const selectedIds = ref<string[]>([])

// ─── Tooltip 映射 ────────────────────────────────────────────────────────────

const tooltipMap = computed(() => {
  const map: Record<string, typeof FIELD_TOOLTIPS_D07[0]> = {}
  for (const t of FIELD_TOOLTIPS_D07) {
    map[t.id] = t
  }
  return map
})

// ─── Selection ───────────────────────────────────────────────────────────────

function handleSelectionChange(selection: ReliabilityRow[]) {
  selectedIds.value = selection.map((r) => r._row_id!).filter(Boolean)
}

// ─── 行样式（质量红线） ──────────────────────────────────────────────────────

function getRowClassName({ row }: { row: ReliabilityRow }) {
  const status = props.getRowQualityStatus(row)
  if (status === 'danger') return 'reliability-grid__row--danger'
  if (status === 'warning') return 'reliability-grid__row--warning'
  return ''
}

// ─── 结论标签颜色 ────────────────────────────────────────────────────────────

function conclusionTagType(status: string): string {
  if (status === '可靠') return 'success'
  if (status === '部分可靠需补充') return 'warning'
  if (status === '不可靠') return 'danger'
  return 'info'
}
</script>

<style scoped>
/* 源外保留列表头标记（源模板无该列，见 SOURCE_EXTRA_RELIABILITY_COLUMNS） */
.reliability-grid__src-extra-icon {
  margin-left: 3px;
  color: #e6a23c;
  cursor: help;
  vertical-align: middle;
}
.reliability-grid__header-note {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: var(--el-color-info-light-9);
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  color: var(--el-text-color-regular);
}

.reliability-grid__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.reliability-grid__toolbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}

.reliability-grid__link {
  color: var(--el-color-primary);
  cursor: pointer;
  text-decoration: underline;
}

/* 邮箱列：输入框 + 域名可靠性 tag 横向紧凑排列 */
.reliability-grid__email-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.reliability-grid__email-cell :deep(.el-input) {
  flex: 1;
  min-width: 0;
}

.reliability-grid__disabled {
  color: var(--el-text-color-disabled);
  font-size: 12px;
  font-style: italic;
}

.reliability-grid__empty {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}

.reliability-grid__tooltip-icon {
  margin-left: 2px;
  cursor: help;
  color: var(--el-color-info);
}

.reliability-grid__tooltip-content {
  max-width: 340px;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
}

.reliability-grid__tooltip-content ul {
  margin: 6px 0;
  padding-left: 16px;
}

.reliability-grid__tooltip-content li {
  margin-bottom: 4px;
}

.reliability-grid__tooltip-link {
  display: block;
  margin-top: 8px;
  color: var(--el-color-primary);
  text-decoration: none;
}

:deep(.reliability-grid__row--danger) {
  background-color: var(--el-color-danger-light-9) !important;
}

:deep(.reliability-grid__row--warning) {
  background-color: var(--el-color-warning-light-9) !important;
}

/* 表头折行显示（列名过长时换行而非截断） */
:deep(.el-table__header th .cell) {
  white-space: normal;
  word-break: break-all;
  line-height: 1.3;
  font-size: 12px;
  padding: 4px 2px;
}

:deep(.el-table__body td .cell) {
  font-size: 12px;
}
</style>
