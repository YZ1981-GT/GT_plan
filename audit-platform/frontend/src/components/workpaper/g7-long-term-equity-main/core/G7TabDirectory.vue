<template>
  <div class="g7-directory">
    <h3 class="sheet-title">底稿目录</h3>

    <div class="directory-layout">
      <!-- 左侧: 编制信息区 -->
      <div class="entity-info">
        <el-descriptions :column="1" border size="small" class="info-desc">
          <el-descriptions-item label="被审计单位">{{ entityName || '——' }}</el-descriptions-item>
          <el-descriptions-item label="截止日">{{ balanceSheetDate || '——' }}</el-descriptions-item>
          <el-descriptions-item label="编制人">{{ preparer || '——' }}</el-descriptions-item>
          <el-descriptions-item label="复核人">{{ reviewer || '——' }}</el-descriptions-item>
        </el-descriptions>

        <!-- 方法论上下文 -->
        <div class="methodology-context">
          <div class="methodology-bar" />
          <div class="methodology-content">
            <strong>关于工作底稿与审计程序索引号对应的说明</strong>
            <p>本底稿目录涵盖G7长期股权投资全部底稿。索引号G7A为实质性程序表，G7-1为审定表（按控制类型分层：子公司/合营/联营），G7-2为明细表（54列5区段），G7-3为调整分录汇总，G7-4至G7-6/G7-13至G7-17为权益法组底稿，G7-7至G7-12/G7-18为子公司组底稿，G0为投资循环共享函证。各底稿通过索引号实现交叉引用与跳转。</p>
          </div>
        </div>
      </div>

      <!-- 右侧: 目录表（24行×8列 只读） -->
      <div class="directory-table">
        <el-table :data="directoryRows" border stripe style="width: 100%; font-size: 13px">
          <el-table-column prop="seq" label="序号" width="55" align="center" />
          <el-table-column label="底稿编码" width="120">
            <template #default="{ row }">
              <GtIndexChip v-if="row.indexCode" :value="row.indexCode" @click="emit('jump', row.indexCode)" />
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="content" label="底稿名称" min-width="220" />
          <el-table-column prop="pages" label="页数" width="55" align="center">
            <template #default="{ row }">{{ row.pages || '-' }}</template>
          </el-table-column>
          <el-table-column prop="preparer" label="编制人" width="80" />
          <el-table-column prop="date" label="日期" width="100" />
          <el-table-column prop="reviewer" label="复核人" width="80" />
          <el-table-column label="备注" min-width="80">
            <template #default="{ row }">
              <span v-if="row.status === 'done'" class="status-done">✓ 已完成</span>
              <span v-else-if="row.status === 'pending'" class="status-pending">○ 待完成</span>
              <span v-else>{{ row.remark || '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabDirectory.vue — 底稿目录（24行×8列 只读）
 *
 * Spec: .kiro/specs/g7-long-term-equity-main/ Task 6.3
 * Requirements: 1.2
 *
 * 静态目录页渲染，支持 GtIndexChip 索引跳转
 * 无虚拟滚动（行数<50）
 * 列：序号|底稿编码|底稿名称|页数|编制人|日期|复核人|备注
 */
import { ref } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ jump: [code: string] }>()

// ═══ 编制信息（从htmlData加载） ═══
const entityName = ref(props.htmlData?.entityName || '')
const balanceSheetDate = ref(props.htmlData?.balanceSheetDate || '')
const preparer = ref(props.htmlData?.preparer || '')
const reviewer = ref(props.htmlData?.reviewer || '')

// ═══ 24行目录数据 ═══
interface DirectoryRow {
  seq: number
  content: string
  indexCode: string
  pages: string
  preparer: string
  date: string
  reviewer: string
  remark: string
  status?: 'done' | 'pending' | ''
}

const directoryRows = ref<DirectoryRow[]>([
  // ═══ main组（本spec：7 sheet） ═══
  { seq: 1, content: '长期股权投资实质性程序表', indexCode: 'G7A', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 2, content: '长期股权投资审定表', indexCode: 'G7-1', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 3, content: '长期股权投资明细表', indexCode: 'G7-2', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 4, content: '调整分录汇总', indexCode: 'G7-3', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 5, content: '附注披露信息（上市公司）', indexCode: 'G7-附注(上市)', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 6, content: '附注披露信息（国企）', indexCode: 'G7-附注(国企)', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 7, content: '底稿目录', indexCode: 'G7-目录', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  // ═══ equity-method组（8 sheet） ═══
  { seq: 8, content: '被投资单位基本信息', indexCode: 'G7-4', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 9, content: '被投资单位财务信息', indexCode: 'G7-5', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 10, content: '会计政策一致性检查', indexCode: 'G7-6', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 11, content: '成本法后续计量测试', indexCode: 'G7-13', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 12, content: '权益法核算测算', indexCode: 'G7-14', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 13, content: '内部交易未实现损益', indexCode: 'G7-15', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 14, content: '未确认投资损失', indexCode: 'G7-16', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 15, content: '长期股权投资减值', indexCode: 'G7-17', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  // ═══ subsidiary组（7 sheet） ═══
  { seq: 16, content: '投资初始确认判断', indexCode: 'G7-7', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 17, content: '同一控制下企业合并', indexCode: 'G7-8', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 18, content: '非同一控制下企业合并', indexCode: 'G7-9', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 19, content: '后续计量检查', indexCode: 'G7-10', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 20, content: '处置检查（非一揽子交易）', indexCode: 'G7-11', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 21, content: '处置检查（一揽子交易）', indexCode: 'G7-12', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  { seq: 22, content: '凭证检查表', indexCode: 'G7-18', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  // ═══ 函证组（G0共享） ═══
  { seq: 23, content: '投资循环函证', indexCode: 'G0', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
  // ═══ 其他 ═══
  { seq: 24, content: '审计说明与结论', indexCode: '', pages: '', preparer: '', date: '', reviewer: '', remark: '', status: '' },
])
</script>

<style scoped>
.g7-directory { padding: 12px; font-size: 13px; }
.sheet-title { margin: 0 0 16px; font-size: 15px; font-weight: 600; }

.directory-layout { display: grid; grid-template-columns: 280px 1fr; gap: 16px; }
@media (max-width: 900px) { .directory-layout { grid-template-columns: 1fr; } }

.entity-info { display: flex; flex-direction: column; gap: 12px; }
.info-desc { width: 100%; }

.methodology-context { position: relative; padding: 12px 12px 12px 16px; background: #fffbe6; border-radius: 4px; }
.methodology-bar { position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: #d48806; border-radius: 4px 0 0 4px; }
.methodology-content { font-size: 12px; color: #614700; }
.methodology-content strong { display: block; margin-bottom: 4px; font-size: 13px; }
.methodology-content p { margin: 0; line-height: 1.6; }

.directory-table { overflow: auto; }
.status-done { color: #52c41a; font-size: 12px; }
.status-pending { color: #909399; font-size: 12px; }
</style>
