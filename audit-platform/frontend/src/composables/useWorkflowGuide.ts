/**
 * 工作流引导提示 composable
 * 
 * 在关键操作入口弹出友好提示，告诉用户：
 * 1. 即将执行什么操作
 * 2. 需要提前准备什么
 * 3. 操作完成后的效果
 * 
 * 用户可勾选"不再提示"，存储在 localStorage
 */
import { ElMessageBox } from 'element-plus'
import { h } from 'vue'

const STORAGE_KEY = 'gt_workflow_guide_dismissed'

function getDismissed(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? new Set(JSON.parse(raw)) : new Set()
  } catch { return new Set() }
}

function setDismissed(key: string) {
  const s = getDismissed()
  s.add(key)
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...s]))
}

interface GuideConfig {
  key: string           // 唯一标识，用于"不再提示"
  title: string         // 弹窗标题
  action: string        // 操作描述
  prerequisites: string[] // 前置条件列表
  effects?: string[]    // 操作效果
  tips?: string[]       // 额外提示
  confirmText?: string  // 确认按钮文字
  cancelText?: string   // 取消按钮文字
}

/**
 * 显示工作流引导弹窗
 * @returns true = 用户确认继续, false = 用户取消
 */
export async function showWorkflowGuide(config: GuideConfig): Promise<boolean> {
  // 已勾选"不再提示"则直接通过
  if (getDismissed().has(config.key)) return true

  const items = [
    ...config.prerequisites.map(t => h('li', { style: 'margin-bottom: 4px' }, [
      h('span', { style: 'color: #e6a23c; margin-right: 4px' }, '⚠'),
      t,
    ])),
  ]

  const effectItems = (config.effects || []).map(t => h('li', { style: 'margin-bottom: 4px' }, [
    h('span', { style: 'color: #67c23a; margin-right: 4px' }, '✓'),
    t,
  ]))

  const tipItems = (config.tips || []).map(t => h('li', { style: 'margin-bottom: 4px; color: #909399; font-size: 12px' }, [
    h('span', { style: 'margin-right: 4px' }, '💡'),
    t,
  ]))

  const content = h('div', { style: 'line-height: 1.8' }, [
    h('p', { style: 'margin-bottom: 8px; font-size: 13px; color: #606266' }, config.action),
    items.length > 0 ? h('div', { style: 'margin-bottom: 8px' }, [
      h('div', { style: 'font-size: 12px; color: #909399; margin-bottom: 4px' }, '请确认以下准备工作已完成：'),
      h('ul', { style: 'margin: 0; padding-left: 16px; font-size: 13px' }, items),
    ]) : null,
    effectItems.length > 0 ? h('div', { style: 'margin-bottom: 8px' }, [
      h('div', { style: 'font-size: 12px; color: #909399; margin-bottom: 4px' }, '操作完成后：'),
      h('ul', { style: 'margin: 0; padding-left: 16px; font-size: 13px' }, effectItems),
    ]) : null,
    tipItems.length > 0 ? h('ul', { style: 'margin: 8px 0 0; padding-left: 16px; border-top: 1px solid #f0f0f0; padding-top: 8px' }, tipItems) : null,
  ])

  try {
    await ElMessageBox({
      title: config.title,
      message: content,
      confirmButtonText: config.confirmText || '继续',
      cancelButtonText: config.cancelText || '取消',
      showCancelButton: true,
      showInput: true,
      inputPlaceholder: '',
      inputType: 'checkbox',
      // Use custom footer with checkbox
      distinguishCancelAndClose: true,
      customClass: 'gt-workflow-guide-dialog',
      beforeClose: (action, instance, done) => {
        if (action === 'confirm') {
          // Check if "don't show again" checkbox is checked via input value
          const inputVal = instance.inputValue
          if (inputVal) {
            setDismissed(config.key)
          }
        }
        done()
      },
    })
    return true
  } catch {
    return false // 用户取消
  }
}

/**
 * 简化版：直接用 ElMessageBox.confirm
 */
export async function showGuide(
  key: string,
  title: string,
  message: string,
  confirmText = '继续',
): Promise<boolean> {
  if (getDismissed().has(key)) return true
  try {
    await ElMessageBox.confirm(message, title, {
      confirmButtonText: confirmText,
      cancelButtonText: '取消',
      type: 'info',
      customClass: 'gt-workflow-guide-dialog',
      dangerouslyUseHTMLString: true,
    })
    return true
  } catch {
    return false
  }
}

// ═══════════════════════════════════════════
// 预定义的引导配置
// ═══════════════════════════════════════════

/** 报表刷新数据 */
export const GUIDE_REPORT_GENERATE = {
  key: 'report_generate',
  title: '📊 刷新报表数据',
  action: '将根据试算表审定数重新计算生成六张财务报表。',
  prerequisites: [
    '已完成账套数据导入（科目余额表、序时账）',
    '已完成科目映射（客户科目 → 标准科目）',
    '调整分录已录入并审批（如有）',
  ],
  effects: [
    '资产负债表、利润表、现金流量表等六张报表将重新生成',
    '已有报表数据将被覆盖',
  ],
  tips: [
    '如果试算表数据为空，报表金额将全部为零',
    '可在"公式管理"中查看和修改报表取数公式',
  ],
}

/** 报表审核 */
export const GUIDE_REPORT_AUDIT = {
  key: 'report_audit',
  title: '✅ 报表审核校验',
  action: '将对报表执行逻辑审核和合理性检查。',
  prerequisites: [
    '报表数据已生成（点击"刷新数据"）',
  ],
  effects: [
    '按公式分类（逻辑审核/提示性审核）逐条执行校验',
    '校验结果将在弹窗中展示，可点击溯源跳转',
  ],
}

/** 附注生成 */
export const GUIDE_NOTE_GENERATE = {
  key: 'note_generate',
  title: '📝 生成附注',
  action: '将根据选定的模板（国企版/上市版）生成全部附注章节。',
  prerequisites: [
    '已选择正确的模板类型（国企版或上市版）',
    '建议先完成报表生成，附注表格将自动从试算表取数',
    '如有上年附注，建议先上传到知识库供 AI 参照',
  ],
  effects: [
    '将生成 170+ 个附注章节（含表格和正文）',
    '已有附注数据将被重新生成',
    '表格数据自动从试算表/底稿提取',
  ],
  tips: [
    '生成后可在编辑模式下修改表格数据和正文内容',
    '使用 AI 续写/改写功能可辅助编写会计政策等文字内容',
  ],
}

/** 账套导入 */
export const GUIDE_LEDGER_IMPORT = {
  key: 'ledger_import',
  title: '📥 账套数据导入',
  action: '将导入企业财务数据（科目余额表、序时账等）。',
  prerequisites: [
    '已准备好企业导出的 Excel 或 CSV 文件',
    '文件应包含：科目余额表（必需）、序时账（建议）',
    '确认文件中的年度与当前项目年度一致',
  ],
  effects: [
    '数据将写入四表（余额表/序时账/辅助余额/辅助明细）',
    '导入完成后试算表将自动重算',
  ],
  tips: [
    '支持多 Sheet 的 Excel 文件，系统会自动识别各表类型',
    '大文件（>50MB）导入可能需要几分钟，请耐心等待',
    '导入后可在"查账"页面查看和校验数据',
  ],
}

/** 底稿生成 */
export const GUIDE_WORKPAPER_GENERATE = {
  key: 'workpaper_generate',
  title: '📋 生成项目底稿',
  action: '将根据致同标准模板为当前项目生成底稿文件。',
  prerequisites: [
    '已完成项目基本信息配置（客户名称、审计期间等）',
    '建议先完成审计程序裁剪（跳过不适用的底稿）',
  ],
  effects: [
    '底稿文件将从模板库复制到项目目录',
    '表头信息（编制单位、审计期间等）将自动填充',
    '已存在的底稿不会被覆盖',
  ],
  tips: [
    '生成后可在底稿列表中查看和编辑',
    '支持 Univer 在线编辑或下载后本地编辑',
  ],
}

/** 提交复核 */
export const GUIDE_SUBMIT_REVIEW = {
  key: 'submit_review',
  title: '📤 提交复核',
  action: '将底稿提交给复核人进行审阅。',
  prerequisites: [
    '底稿内容已编制完成',
    '已分配复核人（在底稿详情中设置）',
    '质量自检（QC）无阻断级问题',
    '所有未解决的复核意见已回复',
  ],
  effects: [
    '底稿状态将变更为"待复核"',
    '复核人将收到通知',
  ],
}

/** AI 模型配置提示 */
export const GUIDE_AI_CONFIG = {
  key: 'ai_config',
  title: '🤖 AI 功能说明',
  action: 'AI 辅助功能需要配置大语言模型服务。',
  prerequisites: [
    '已部署 vLLM 或其他 OpenAI 兼容的 LLM 服务',
    '在"系统设置 → AI 模型"中配置了模型地址和密钥',
  ],
  tips: [
    'AI 功能不可用时会自动降级，不影响手动操作',
    '本地部署推荐使用 Qwen3.5-27B 模型',
  ],
}

/** 重置导入 */
export const GUIDE_RESET_IMPORT = {
  key: 'reset_import_always', // 不存储dismissed，每次都提示
  title: '⚠️ 重置导入',
  action: '将清除当前卡住的导入任务并释放导入锁。',
  prerequisites: [
    '确认当前没有正在进行的导入任务',
    '此操作不会删除已导入的数据',
  ],
}

export function resetAllGuides() {
  localStorage.removeItem(STORAGE_KEY)
}
