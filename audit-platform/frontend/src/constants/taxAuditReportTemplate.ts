/**
 * 税审报告正文的内容定义（企业所得税年度纳税申报审核报告）。
 *
 * 移植自参考实现 CITAR `src/app/report-body-template.ts`（录自「报告正文.xlsx」Sheet1，60 行）。
 *
 * 做成数据而非写死在模板里：正文段落是法定文书措辞，将来要按业务类型切换模板，
 * 混在组件里改不动。
 *
 * 🔴 四段固定措辞照原文一字不改 —— 那是法定文书的表述，不是可以润色的说明文字。
 *
 * 25 行摘录的金额在原表里是跨工作簿公式（=[1]A100000!D20 等），真实来源是
 * 企业所得税年度纳税申报表主表 A100000。纳税申报表页面（TaxReturnPage）尚未实现，
 * 故此处只记来源地址、本期不取数 —— 填个零会让人以为已经取过数了。
 */

/** 正文里由用户手填的空档（离开页面即丢，本期不落库） */
export type BodyFieldVariable =
  /** 报告编号 */
  | 'reportNo'
  /** 公司名称（默认带入项目的客户名称，可改） */
  | 'companyName'
  /** 出具日期 */
  | 'reportDate'

/**
 * 正文的一个块。段落类型照原表的视觉层次：
 * 标题居中加大，正文段落首行缩进，签字与事务所信息左对齐。
 */
export type BodyBlock =
  | { kind: 'title'; text: string; excelRow: number }
  /** 带空档的字段行（报告编号靠右，其余靠左 —— 照原表的位置） */
  | { kind: 'field'; label: string; variable: BodyFieldVariable; excelRow: number }
  /** 固定段落。{year} 由审核年度替换 */
  | { kind: 'paragraph'; text: string; excelRow: number }
  /** 25 行数据摘录表 */
  | { kind: 'summary-table'; excelRow: number }
  /** 小字注释 */
  | { kind: 'note'; text: string; excelRow: number }
  /** 签字行 */
  | { kind: 'signature'; text: string; excelRow: number }
  /** 事务所信息等固定文字 */
  | { kind: 'footer'; text: string; excelRow: number }
  /** 附件清单 */
  | { kind: 'attachments'; title: string; items: string[]; excelRow: number }
  | { kind: 'spacer'; excelRow: number }

/**
 * 摘录表的一行。
 * source 记原表的跨工作簿公式地址（形如 A100000!D20）——
 * 申报表实现后按此地址取数，届时不必再回头翻原始 xlsx。
 */
export interface SummaryLine {
  seq: number
  label: string
  /** 申报表主表的来源单元格。税率一行是固定值，故为 null */
  source: string | null
  /** 固定值。仅税率一行有 */
  fixedText?: string
}

/** 25 行数据摘录（Excel 第 11-35 行） */
export const REPORT_SUMMARY_LINES: readonly SummaryLine[] = [
  { seq: 1, label: '一、利润总额', source: 'A100000!D20' },
  { seq: 2, label: '减：境外所得', source: 'A100000!D21' },
  { seq: 3, label: '加：纳税调整增加额', source: 'A100000!D22' },
  { seq: 4, label: '减：纳税调整减少额', source: 'A100000!D23' },
  { seq: 5, label: '减：免税、减计收入及加计扣除', source: 'A100000!D24' },
  { seq: 6, label: '加：境外应税所得抵减境内亏损', source: 'A100000!D55' },
  { seq: 7, label: '二、纳税调整后所得', source: 'A100000!D56' },
  { seq: 8, label: '减：所得减免', source: 'A100000!D57' },
  { seq: 9, label: '减：弥补以前年度亏损', source: 'A100000!D58' },
  { seq: 10, label: '减：抵扣应纳税所得额', source: 'A100000!D59' },
  { seq: 11, label: '三、应纳税所得额', source: 'A100000!D60' },
  // 原表此行为固定值 25%，不是公式。
  { seq: 12, label: '税率', source: null, fixedText: '25%' },
  { seq: 13, label: '四、应纳所得税额', source: 'A100000!D62' },
  { seq: 14, label: '减：减免所得税额', source: 'A100000!D63' },
  { seq: 15, label: '减：抵免所得税额', source: 'A100000!D103' },
  { seq: 16, label: '五、应纳税额', source: 'A100000!D104' },
  { seq: 17, label: '加：境外所得应纳所得税额', source: 'A100000!D105' },
  { seq: 18, label: '减：境外所得抵免所得税额', source: 'A100000!D106' },
  { seq: 19, label: '六、实际应纳所得税额', source: 'A100000!D107' },
  { seq: 20, label: '减：本年累计预缴所得税额', source: 'A100000!D108' },
  { seq: 21, label: '七、本年应补（退）的所得税额', source: 'A100000!D109' },
  { seq: 22, label: '减：民族自治地区企业所得税地方分享部分', source: 'A100000!D113' },
  { seq: 23, label: '减：稽查查补（退）所得税额', source: 'A100000!D114' },
  { seq: 24, label: '减：特别纳税调整补（退）所得税额', source: 'A100000!D115' },
  { seq: 25, label: '八、本年实际应补（退）所得税额', source: 'A100000!D116' },
]

/** 正文结构（Excel 第 1-60 行） */
export const REPORT_BODY_BLOCKS: readonly BodyBlock[] = [
  { kind: 'title', text: '企业所得税年度纳税申报审核报告', excelRow: 1 },
  { kind: 'field', label: '报告编号', variable: 'reportNo', excelRow: 2 },
  { kind: 'field', label: '公司名称', variable: 'companyName', excelRow: 3 },
  {
    kind: 'paragraph',
    text: '我们接受委托，对被审核单位{year}年度的企业所得税年度纳税申报事项进行审核，并出具审核报告。',
    excelRow: 4,
  },
  {
    kind: 'paragraph',
    text: '被审核单位的责任是，及时提供与企业所得税年度纳税申报事项有关的会计资料和纳税资料，并保证其真实、准确、完整和合法，确保被审核单位按照《中华人民共和国企业所得税法》及其实施条例、《中华人民共和国税收征收管理法》及其实施细则以及其他税收法律、法规、规范性文件，如实纳税申报企业所得税年度纳税申报表。',
    excelRow: 5,
  },
  {
    kind: 'paragraph',
    text: '我们的责任是，本着独立、客观、公正的原则，依据《中华人民共和国企业所得税法》及其实施条例、《中华人民共和国税收征收管理法》及其实施细则和有关规定，按照国家税务总局《涉税专业服务监管办法（试行）》、《涉税专业服务管理办法（试行）》、中国注册税务师协会《税务师行业涉税专业服务规范基本指引（试行）》等执业规范要求，对被审核单位企业所得税年度纳税申报的真实性、准确性、完整性和合法性实施审核，并发表审核意见。',
    excelRow: 6,
  },
  {
    kind: 'paragraph',
    text: '在审核过程中，我们考虑了与企业所得税相关的审核材料的证据资格和证明能力，对被审核单位提供的会计资料及纳税资料等实施了审核、验证、计算和职业判断等必要的审核程序。我们相信，我们获取的审核证据是充分的、适当的，为发表审核意见提供了基础。现将审核结果报告如下：',
    excelRow: 7,
  },
  {
    kind: 'paragraph',
    text: '经对被审核单位{year}年度企业所得税年度纳税申报事项进行审核，我们认为，本报告后附的《企业所得税年度纳税申报表》已经按照《中华人民共和国企业所得税法》及其实施条例、《中华人民共和国税收征收管理法》及其实施细则以及其他税收法律法规的相关规定填报，在所有重大方面真实、准确、完整地反映了被审核单位本纳税年度的所得税纳税申报情况。部分数据摘录如下：',
    excelRow: 8,
  },
  { kind: 'summary-table', excelRow: 10 },
  {
    kind: 'note',
    text: '注：具体纳税调整项目及说明详见附件《企业所得税年度纳税申报审核报告说明》。',
    excelRow: 36,
  },
  { kind: 'spacer', excelRow: 37 },
  {
    kind: 'paragraph',
    text: '本报告仅供被审核单位向主管税务机关办理企业所得税年度纳税申报时使用，不作其他用途。因使用不当造成的后果，与执行本审核业务的税务师事务所及其税务师无关。',
    excelRow: 41,
  },
  { kind: 'spacer', excelRow: 42 },
  { kind: 'signature', text: '所  长：（签名、盖章）', excelRow: 45 },
  { kind: 'signature', text: '税务师：（签名、盖章）', excelRow: 47 },
  { kind: 'footer', text: '致同（北京）税务师事务所有限责任公司', excelRow: 49 },
  { kind: 'footer', text: '电话：010-85665588', excelRow: 51 },
  { kind: 'footer', text: '地址：北京市朝阳区建国门外大街22号赛特广场5层', excelRow: 52 },
  { kind: 'field', label: '日期', variable: 'reportDate', excelRow: 53 },
  {
    kind: 'attachments',
    title: '附件：',
    items: [
      '1. 企业所得税年度纳税申报审核报告说明',
      '2. 企业所得税年度纳税申报表',
      '3. 企业年度财务报表',
      '4. 税务师事务所行政登记证（副本）复印件',
      '5. 营业执照（副本）复印件',
    ],
    excelRow: 55,
  },
]

/**
 * 把段落里的 {year} 替换成审核年度。
 * 取不到年度时留全角空格占位（像纸质文书上的空档），绝不显示 undefined / null。
 */
export function fillYear(text: string, year: string | number | null | undefined): string {
  const y = year == null ? '' : String(year).trim()
  return text.replace(/\{year\}/g, y || '　　　')
}
