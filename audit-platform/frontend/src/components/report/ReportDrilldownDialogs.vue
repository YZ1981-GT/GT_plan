<template>
  <!--
    ReportDrilldownDialogs — 穿透 + 构成科目 + 附注引用 Drawer
    从 ReportDialogs.vue 拆分（report-view-slimdown tech debt #3）
  -->

  <!-- Sprint 4 Task 4.3：附注引用我（侧栏 drawer） -->
  <el-drawer
    :model-value="noteRefsVisible"
    :title="`附注引用我 — ${noteRefsRowName || ''}`"
    direction="rtl"
    size="380px"
    append-to-body
    :destroy-on-close="false"
    @update:model-value="$emit('update:noteRefsVisible', $event)"
  >
    <div v-loading="noteRefsLoading" class="gt-rv-note-refs">
      <div class="gt-rv-note-refs__header">
        <span class="gt-rv-note-refs__label">报表行</span>
        <code class="gt-rv-note-refs__code">{{ noteRefsRowCode || '—' }}</code>
      </div>
      <el-empty
        v-if="!noteRefsLoading && noteRefsList.length === 0"
        :image-size="80"
        description="暂无附注引用此报表项"
      />
      <ul v-else class="gt-rv-note-refs__list">
        <li
          v-for="(ref, i) in noteRefsList"
          :key="`${ref.note_section}-${ref.table_index}-${i}`"
          class="gt-rv-note-refs__item"
          @click="$emit('note-ref-jump', ref)"
        >
          <span class="gt-rv-note-refs__sec">{{ ref.note_section }}</span>
          <span v-if="ref.section_title" class="gt-rv-note-refs__title">{{ ref.section_title }}</span>
          <span v-if="ref.table_index > 0" class="gt-rv-note-refs__tbl">表 #{{ ref.table_index + 1 }}</span>
          <span class="gt-rv-note-refs__arrow">→</span>
        </li>
      </ul>
      <div v-if="noteRefsList.length > 0" class="gt-rv-note-refs__footer">
        共 {{ noteRefsList.length }} 处引用 · 点击跳转到附注编辑器
      </div>
    </div>
  </el-drawer>

  <!-- 穿透弹窗 -->
  <el-dialog append-to-body :model-value="drilldownVisible" :title="`穿透查询 — ${drilldownData?.row_name || ''}`" width="700px" @update:model-value="$emit('update:drilldownVisible', $event)">
    <div v-if="drilldownData" class="gt-rv-drilldown-content">
      <div class="gt-rv-dd-section">
        <span class="gt-rv-dd-label">公式：</span>
        <code>{{ drilldownData.formula }}</code>
      </div>
      <el-table :data="drilldownData.accounts" border size="small" style="margin-top: 12px">
        <el-table-column prop="code" label="科目编码" width="120" />
        <el-table-column prop="name" label="科目名称" min-width="200" />
        <el-table-column label="金额" width="150" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.amount" /></template>
        </el-table-column>
        <el-table-column label="底稿" width="100" align="center">
          <template #default="{ row }">
            <el-button v-if="row.wp_id" link type="primary" size="small"
              @click="$emit('open-workpaper', row.wp_id)">打开底稿</el-button>
            <span v-else style="color: var(--gt-color-text-placeholder)">—</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <div v-else v-loading="drilldownLoading" style="min-height: 100px" />
  </el-dialog>

  <!-- Phase 3 F1.2: 报表行构成科目弹窗 -->
  <el-dialog
    append-to-body
    :model-value="lineCompVisible"
    :title="`构成科目 — ${lineCompData?.item_name || ''}`"
    width="650px"
    @update:model-value="$emit('update:lineCompVisible', $event)"
  >
    <div v-if="lineCompData" class="gt-rv-line-comp-content">
      <!-- 报表行汇总 -->
      <div class="gt-rv-line-comp-header">
        <span class="gt-rv-line-comp-label">报表行次</span>
        <div class="gt-rv-line-comp-summary">
          <span class="gt-rv-line-comp-name">{{ lineCompData.item_name }}</span>
          <GtAmountCell :value="lineCompData.total_amount" />
        </div>
      </div>

      <!-- 构成科目列表 -->
      <div class="gt-rv-line-comp-accounts">
        <span class="gt-rv-line-comp-label">构成科目（点击跳转试算表）</span>
        <el-table
          :data="lineCompData.accounts"
          border
          size="small"
          style="margin-top: 8px"
          :row-style="{ cursor: 'pointer' }"
          @row-click="(row: any) => $emit('line-comp-jump', row.code)"
        >
          <el-table-column prop="code" label="科目编码" width="120">
            <template #default="{ row }">
              <span class="gt-amt" style="color: var(--gt-color-primary)">{{ row.code }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="科目名称" min-width="180" />
          <el-table-column label="期末余额" width="150" align="right">
            <template #header>
              <span>期末余额</span>
              <span style="font-size: 10px; color: var(--gt-color-text-placeholder); margin-left: 4px">(元)</span>
            </template>
            <template #default="{ row }">
              <GtAmountCell :value="row.closing_balance" />
            </template>
          </el-table-column>
          <el-table-column label="占比" width="90" align="right">
            <template #default="{ row }">
              <span style="color: var(--gt-color-text-secondary); font-size: 12px">{{ row.pct?.toFixed(1) }}%</span>
            </template>
          </el-table-column>
          <el-table-column label="" width="60" align="center">
            <template #default>
              <span style="color: var(--gt-color-primary); font-size: 12px">→</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 底部提示 -->
      <div class="gt-rv-line-comp-footer">
        <span style="color: var(--gt-color-text-tertiary); font-size: 12px">
          点击任意科目行可跳转到试算表定位（支持 Backspace 返回）
        </span>
      </div>
    </div>
    <div v-else v-loading="lineCompLoading" style="min-height: 100px" />
  </el-dialog>
</template>

<script setup lang="ts">
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import type { ReportDrilldownData } from '@/services/auditPlatformApi'
import type { LineCompositionData } from '@/views/composables/useReportCellActions'

// ─── Props ──────────────────────────────────────────────────────────────────
defineProps<{
  // Drilldown
  drilldownVisible: boolean
  drilldownLoading: boolean
  drilldownData: ReportDrilldownData | null

  // Line composition
  lineCompVisible: boolean
  lineCompLoading: boolean
  lineCompData: LineCompositionData | null

  // Note refs
  noteRefsVisible: boolean
  noteRefsLoading: boolean
  noteRefsList: any[]
  noteRefsRowCode: string
  noteRefsRowName: string
}>()

// ─── Emits ──────────────────────────────────────────────────────────────────
defineEmits<{
  (e: 'update:drilldownVisible', val: boolean): void
  (e: 'update:lineCompVisible', val: boolean): void
  (e: 'update:noteRefsVisible', val: boolean): void
  (e: 'line-comp-jump', accountCode: string): void
  (e: 'note-ref-jump', ref: { note_section: string; table_index: number }): void
  (e: 'open-workpaper', wpId: string): void
}>()
</script>
