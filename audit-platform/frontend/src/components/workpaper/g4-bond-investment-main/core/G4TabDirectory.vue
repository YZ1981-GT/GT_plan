<template>
  <div class="g4-directory">
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
            <p>本底稿目录涵盖G4债权投资全部底稿。索引号G4A为程序表，G4-1至G4-4为实质性程序底稿，G4-5至G4-13为SPPI/ECL/盘点等专项底稿，G0-1至G0-8为投资循环函证底稿。各底稿通过索引号实现交叉引用与跳转。</p>
          </div>
        </div>
      </div>

      <!-- 右侧: 目录表 -->
      <div class="directory-table">
        <el-table :data="directoryRows" border stripe style="width: 100%; font-size: 13px">
          <el-table-column prop="seq" label="序号" width="55" align="center" />
          <el-table-column prop="content" label="内容" min-width="220" />
          <el-table-column label="索引号" width="100">
            <template #default="{ row }">
              <GtIndexChip v-if="row.indexCode" :value="row.indexCode" @click="emit('jump', row.indexCode)" />
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="pages" label="页数" width="60" align="center">
            <template #default="{ row }">{{ row.pages || '-' }}</template>
          </el-table-column>
          <el-table-column prop="preparer" label="编制人" width="80" />
          <el-table-column prop="reviewer" label="复核人" width="80" />
          <el-table-column prop="date" label="日期" width="100" />
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
 * G4TabDirectory.vue — 底稿目录
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Req 1.8, 1.9, 12.1~12.4
 * 27行×8列目录页渲染
 * 静态展示为主，支持GtIndexChip索引跳转
 * Left panel: entity info (被审计单位/截止日/编制人/复核人)
 * Right panel: directory table (序号/内容/索引号/备注)
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

// ═══ 27行目录数据 ═══
interface DirectoryRow {
  seq: number
  content: string
  indexCode: string
  pages: string
  preparer: string
  reviewer: string
  date: string
  remark: string
  status?: 'done' | 'pending' | ''
}

const directoryRows = ref<DirectoryRow[]>([
  // 顺序/文案对齐 Excel《底稿目录》
  { seq: 0, content: '债权投资实质性程序表', indexCode: 'G4A', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 1, content: '审定表', indexCode: 'G4-1', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 2, content: '附注披露信息（上市公司）', indexCode: '', pages: '', preparer: '', reviewer: '', date: '', remark: '无需打印', status: '' },
  { seq: 3, content: '附注披露信息（国企）', indexCode: '', pages: '', preparer: '', reviewer: '', date: '', remark: '无需打印', status: '' },
  { seq: 4, content: '明细表', indexCode: 'G4-2', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 5, content: '调整分录汇总', indexCode: 'G4-3', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 6, content: '利息测算表', indexCode: 'G4-4', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 7, content: '业务模式分析', indexCode: 'G4-5', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 8, content: '合同现金流量特征分析', indexCode: 'G4-6', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 9, content: '有价证券盘点表', indexCode: 'G4-7', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 10, content: '盘点倒轧表', indexCode: 'G4-8', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 11, content: '函证结果汇总表', indexCode: 'G0-1', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 12, content: '核实被函证单位信息', indexCode: 'G0-2', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 13, content: '跟函函证过程控制', indexCode: 'G0-3', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 14, content: '函证差异核对表（证券投资）', indexCode: 'G0-4', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 15, content: '函证差异核对表(非证券投资)', indexCode: 'G0-5', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 16, content: '替代程序检查表', indexCode: 'G0-6', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 17, content: '邮件传真回函可靠性验证', indexCode: 'G0-7', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 18, content: '函证程序舞弊风险评价表', indexCode: 'G0-8', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 19, content: '债权投资三阶段划分', indexCode: 'G4-9', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 20, content: '债权投资减值准备测算表', indexCode: 'G4-10', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 21, content: '预期信用损失的计量测试', indexCode: 'G4-11', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 22, content: '减值准备转回（收回）、核销检查表', indexCode: 'G4-12', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
  { seq: 23, content: '凭证检查表', indexCode: 'G4-13', pages: '', preparer: '', reviewer: '', date: '', remark: '', status: '' },
])
</script>

<style scoped>
.g4-directory { padding: 12px; font-size: var(--wp-font-size, 13px); }
.sheet-title { margin: 0 0 16px; font-size: 15px; font-weight: 600; }

.directory-layout { display: grid; grid-template-columns: 280px 1fr; gap: 16px; }
@media (max-width: 900px) { .directory-layout { grid-template-columns: 1fr; } }

.entity-info { display: flex; flex-direction: column; gap: 12px; }
.info-desc { width: 100%; }

.methodology-context { position: relative; padding: 12px 12px 12px 16px; background: #fffbe6; border-radius: 4px; }
.methodology-bar { position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: #d48806; border-radius: 4px 0 0 4px; }
.methodology-content { font-size: 12px; color: #614700; }
.methodology-content strong { display: block; margin-bottom: 4px; font-size: var(--wp-font-size, 13px); }
.methodology-content p { margin: 0; line-height: 1.6; }

.directory-table { overflow: auto; }
.status-done { color: #52c41a; font-size: 12px; }
.status-pending { color: #909399; font-size: 12px; }
</style>
