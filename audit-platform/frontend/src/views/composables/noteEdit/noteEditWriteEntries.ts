/**
 * noteEditWriteEntries — 写入口清单
 *
 * 每个入口声明：id（与 DOM 上 data-note-write 一致）、中文名、触发方式、
 * 是否受多窗口锁约束、是否按 EQCR 隐藏、对应的清册调用点 key。
 *
 * vitest 守卫断言每个 callPoints 都在清册中、入口 id 唯一、
 * 清册中范围内调用点都至少归属一个入口。
 *
 * Feature: partner-manager-edit-permission
 * Requirements: 10.3, 10.8
 */

// ── 类型 ─────────────────────────────────────────────────────────────────────

export interface NoteWriteEntry {
  /** 与 DOM 上 data-note-write 一致 */
  id: string
  /** 中文名，如「💾 保存」 */
  label: string
  /** 触发方式 */
  trigger: 'button' | 'menu' | 'switch' | 'tree' | 'context-menu' | 'shortcut' | 'auto' | 'input'
  /** true = 目标属覆盖集合或章节拖拽排序 */
  coverage: boolean
  /** 受多窗口锁约束（10.3 默认四类） */
  lockConstrained: boolean
  /** 按 EQCR 隐藏 */
  eqcrHidden: boolean
  /** 清册 editor_call_points[].key；拖拽排序记死链路径 */
  callPoints: string[]
}

// ── 写入口清单 ───────────────────────────────────────────────────────────────

/**
 * 附注编辑器全部写入口。实施阶段后续任务（17.5、17.6）会逐个给入口元素
 * 加上 `data-note-write="<id>"`，这里先声明清单。
 *
 * callPoints 在后端清册完成后填充；目前先声明入口结构，
 * callPoints 暂为空数组——vitest 守卫会在清册产物可用时补齐断言。
 */
export const WRITE_ENTRIES: readonly NoteWriteEntry[] = [
  // ── 编辑与保存 ──────────────────────────────────────────────────────────
  {
    id: 'enter-edit',
    label: '编辑',
    trigger: 'button',
    coverage: true,
    lockConstrained: true,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'save',
    label: '💾 保存',
    trigger: 'button',
    coverage: true,
    lockConstrained: true,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'save-shortcut',
    label: '保存（快捷键）',
    trigger: 'shortcut',
    coverage: true,
    lockConstrained: true,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'auto-save',
    label: '定时自动保存',
    trigger: 'auto',
    coverage: true,
    lockConstrained: true,
    eqcrHidden: false,
    callPoints: [],
  },

  // ── 章节结构 ──────────────────────────────────────────────────────────
  {
    id: 'add-section',
    label: '新增章节',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: true,
    callPoints: [],
  },
  {
    id: 'delete-section',
    label: '删除章节',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'restore-section',
    label: '恢复章节',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'drag-sort',
    label: '章节拖拽排序',
    trigger: 'tree',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: ['PUT /api/disclosure-notes/{}/{}/sections/{}/move'],
  },

  // ── 公式 ──────────────────────────────────────────────────────────────
  {
    id: 'clear-formulas',
    label: '一键清除公式',
    trigger: 'button',
    coverage: true,
    lockConstrained: true,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'apply-formulas',
    label: '应用公式',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'restore-auto',
    label: '恢复自动提数',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'edit-formula',
    label: '编辑单元格公式',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },

  // ── 刷新 ──────────────────────────────────────────────────────────────
  {
    id: 'refresh-section',
    label: '当前章节刷新',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'refresh-all',
    label: '全部刷新',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'workpaper-event-refresh',
    label: '底稿保存事件刷新',
    trigger: 'auto',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },

  // ── 批量操作 ──────────────────────────────────────────────────────────
  {
    id: 'offline-import',
    label: '离线导入',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'validate',
    label: '校验',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'toggle-mode',
    label: '切换输入模式',
    trigger: 'switch',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'pull-workpapers',
    label: '从底稿取数',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },

  // ── 正文批量写入（受多窗口锁约束的三入口） ───────────────────────────
  {
    id: 'batch-import-upload',
    label: '批量写入（上传）',
    trigger: 'button',
    coverage: true,
    lockConstrained: true,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'batch-import-knowledge',
    label: '批量写入（知识库）',
    trigger: 'button',
    coverage: true,
    lockConstrained: true,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'batch-apply',
    label: '批量应用',
    trigger: 'button',
    coverage: true,
    lockConstrained: true,
    eqcrHidden: false,
    callPoints: [],
  },

  // ── 内容模板 ──────────────────────────────────────────────────────────
  {
    id: 'template-save',
    label: '保存内容模板',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'template-delete',
    label: '删除内容模板',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'template-preview',
    label: '预览内容模板',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },

  // ── 上年继承 ──────────────────────────────────────────────────────────
  {
    id: 'import-prior-year',
    label: '导入上年附注',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'inherit-prior-year',
    label: '继承上年附注',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },

  // ── 其他编辑器操作 ────────────────────────────────────────────────────
  {
    id: 'cross-ref-update',
    label: '交叉引用更新',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'confirm-validation',
    label: '确认校验结果',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'auto-trim',
    label: '自动裁剪',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'trim-sections',
    label: '裁剪保存',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'wp-mapping',
    label: '取数映射保存',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'refresh-all-bindings',
    label: '全量取数刷新',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'apply-group-baseline',
    label: '集团基线应用',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'generate-notes',
    label: '自动生成附注（无章节时）',
    trigger: 'auto',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'regenerate-template',
    label: '切模板重新生成',
    trigger: 'auto',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'note-template-save',
    label: '附注模板保存（新增/删除自定义章节）',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'note-template-restore',
    label: '结构版本回滚',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'custom-section-create',
    label: '新建自定义章节',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: true,
    callPoints: [],
  },
  {
    id: 'custom-section-apply-template',
    label: '应用章节模板',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'custom-section-save-as-template',
    label: '另存为章节模板',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'lock-acquire',
    label: '获取章节锁',
    trigger: 'auto',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'lock-heartbeat',
    label: '章节锁心跳',
    trigger: 'auto',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'data-lock-snapshot',
    label: '数据锁定快照',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'group-template-save',
    label: '集团模板保存',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'group-template-detach',
    label: '脱离集团模板',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },

  // ── 输入区（coverage 但不对应特定端点调用） ────────────────────────────
  {
    id: 'rich-text-input',
    label: '正文富文本编辑区',
    trigger: 'input',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'table-cell-input',
    label: '表格单元格',
    trigger: 'input',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },
  {
    id: 'table-structure-toolbar',
    label: '表格结构工具栏',
    trigger: 'button',
    coverage: true,
    lockConstrained: false,
    eqcrHidden: false,
    callPoints: [],
  },

  // ── 仅按 EQCR 显隐的非覆盖入口 ─────────────────────────────────────
  {
    id: 'ai-fill',
    label: 'AI 填充',
    trigger: 'button',
    coverage: false,
    lockConstrained: false,
    eqcrHidden: true,
    callPoints: [],
  },
  {
    id: 'ref-doc-fill',
    label: '参照文档填充',
    trigger: 'button',
    coverage: false,
    lockConstrained: false,
    eqcrHidden: true,
    callPoints: [],
  },
  {
    id: 'batch-prefill',
    label: '批量预填充',
    trigger: 'button',
    coverage: false,
    lockConstrained: false,
    eqcrHidden: true,
    callPoints: [],
  },
] as const
