/**
 * reliabilityNotes.ts — D0-7 注1/注2/注3 提示完整文本
 *
 * 注1 → 身份确认列: 4种确认方式
 * 注2 → 邮箱验证列: 私人邮箱不可靠 + 工作邮箱验证 + 电子签名法 + 技术提示4号
 * 注3 → 信息可靠性列: 不列明余额 + 水印防篡改
 *
 * 精确就近 tooltip（列标题问号图标 hover 展示），完整原文同步到 guidance 侧栏。
 */

export interface FieldTooltipItem {
  /** 提示编号（注1/注2/注3） */
  id: string
  /** 对应列 field key */
  field: string
  /** tooltip 标题 */
  title: string
  /** 详细内容（数组每项为一条要点） */
  items: string[]
  /** 外部链接（可选） */
  link?: { url: string; label: string }
}

/**
 * D0-7 字段提示常量（注1/注2/注3）
 */
export const FIELD_TOOLTIPS_D07: FieldTooltipItem[] = [
  {
    id: '注1',
    field: 'identity_verified',
    title: '身份确认方式（注1）',
    items: [
      '1. 电话确认：致电对方单位（号码须取自工商/官网等独立来源），核实回函签字人身份及授权情况',
      '2. 邮件确认：向对方单位工作邮箱（非私人邮箱）发送确认邮件，要求确认回函签字人身份',
      '3. 见面确认：与对方单位经办人员面对面核实身份（适用于跟函现场确认的情形）',
      '4. 系统确认：通过对方单位内部系统（如供应商门户、客户系统）验证回函人员身份及权限',
    ],
  },
  {
    id: '注2',
    field: 'email_verified',
    title: '邮箱验证要点（注2）',
    items: [
      '1. 私人邮箱（如 163/qq/gmail 等）发出的回函不可靠——无法确认发件人身份与授权',
      '2. 工作邮箱验证：确认发件人邮箱域名与被询证单位官方域名一致，且该邮箱属于有权回复人员',
      '3. 电子签名法：根据《电子签名法》，可靠的电子签名应满足专属性、控制性、可检测性要求',
      '4. 参见致同技术提示4号《函证》相关指引',
    ],
    link: {
      url: 'https://www.gt-china.com/article_view.php?id=9691',
      label: '致同技术提示4号《函证》',
    },
  },
  {
    id: '注3',
    field: 'conclusion_status',
    title: '信息可靠性判断（注3）',
    items: [
      '1. 不列明余额：如回函未列明具体余额（仅盖章确认），应考虑该回函是否提供了充分审计证据',
      '2. 水印/防篡改：检查电子回函是否具有防篡改措施（如数字水印、PDF 签名、不可编辑格式等），缺乏防篡改措施的电子回函可靠性降低',
    ],
  },
]

/**
 * 顶部精简说明文本
 */
export const RELIABILITY_HEADER_NOTE =
  '本表用于验证通过电子邮件或传真收到的回函的可靠性。电子回函因无法直接确认发件人身份，存在被伪造或篡改的风险，需逐笔执行验证程序。'

/**
 * `G:M` 七列的父表头（源模板 X0-7 `G5:M5` 合并单元格字面）。
 *
 * 🔴 单一真源：六个可见的回函可靠性 sheet（`D0-7` / `F0-7` / `G0-7` / `H0-6` / `K0-7` / `L0-6`）
 * 的 `G5` 逐字相同，后端四份事实守卫各自以 openpyxl 直读断言过
 * （如 `test_k0_source_template_facts.py::TestReliability::test_14_columns_with_parent_header`）
 * ⇒ 平台侧只放一份常量、不按枢纽分叉；改字面必须先改源模板。
 *
 * spec: k0-confirmation-source-alignment R9.2 / Property 18
 */
export const RELIABILITY_PARENT_HEADER = '期末未收回原件函证可靠性验证'

/**
 * 列配置常量（14列定义）
 * 用于 Grid 组件动态渲染列 + 条件列标记 + tooltip 映射
 */
export interface ReliabilityColumnDef {
  field: string
  label: string
  width: number
  /** 是否为条件列（寄回原件=否时才展开） */
  conditional?: boolean
  /** 对应的 tooltip ID（注1/注2/注3） */
  tooltipId?: string
  /** 列分组（basic/verify/conclusion） */
  group: 'basic' | 'verify' | 'conclusion'
  /** 对齐方式 */
  align?: 'left' | 'center' | 'right'
}

export const RELIABILITY_COLUMN_CONFIG: ReliabilityColumnDef[] = [
  // ─── 基本信息组（6列） ──────────────────────────────────────────────────
  { field: 'seq', label: '序号', width: 55, group: 'basic', align: 'center' },
  { field: 'confirm_index', label: '函证索引号', width: 110, group: 'basic' },
  { field: 'entity_name', label: '被询证单位', width: 150, group: 'basic' },
  { field: 'reply_method', label: '回函方式', width: 100, group: 'basic', align: 'center' },
  { field: 'reply_date', label: '回函日期', width: 100, group: 'basic', align: 'center' },
  { field: 'original_returned', label: '寄回原件', width: 80, group: 'basic', align: 'center' },

  // ─── 验证组（7列，条件列） ──────────────────────────────────────────────
  { field: 'identity_verified', label: '身份已确认', width: 90, group: 'verify', align: 'center', conditional: true, tooltipId: '注1' },
  { field: 'identity_method', label: '确认方式', width: 110, group: 'verify', conditional: true },
  { field: 'email_verified', label: '邮箱已验证', width: 90, group: 'verify', align: 'center', conditional: true, tooltipId: '注2' },
  { field: 'email_domain', label: '邮箱域名', width: 120, group: 'verify', conditional: true },
  { field: 'phone_called', label: '已致电', width: 70, group: 'verify', align: 'center', conditional: true },
  { field: 'phone_source', label: '电话来源', width: 110, group: 'verify', conditional: true },
  { field: 'reliability_note', label: '验证备注', width: 150, group: 'verify', conditional: true },

  // ─── 结论组（1列） ──────────────────────────────────────────────────────
  { field: 'conclusion_status', label: '信息可靠性', width: 110, group: 'conclusion', align: 'center', tooltipId: '注3' },
]
