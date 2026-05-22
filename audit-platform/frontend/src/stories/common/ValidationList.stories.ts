import type { Meta, StoryObj } from '@storybook/vue3'
import ValidationList from '@/components/common/ValidationList.vue'

const meta = {
  title: 'Common/ValidationList',
  component: ValidationList,
  tags: ['autodocs'],
} satisfies Meta<typeof ValidationList>

export default meta
type Story = StoryObj<typeof meta>

const sampleFindings = [
  { id: '1', severity: 'high', check_type: '勾稽校验', message: '资产负债表借贷不平衡，差异 ¥12,500', fix_suggestion: '检查调整分录' },
  { id: '2', severity: 'medium', check_type: '完整性', message: '科目 6601 缺少辅助账明细', fix_suggestion: '补充辅助账数据' },
  { id: '3', severity: 'low', check_type: '格式校验', message: '日期格式不统一（混用 YYYY-MM-DD 和 YYYY/MM/DD）', fix_suggestion: null },
]

export const Default: Story = {
  args: {
    findings: sampleFindings,
  },
}

export const HighSeverityOnly: Story = {
  args: {
    findings: [
      { id: '1', severity: 'high', check_type: '三角勾稽', message: '期末余额 ≠ 期初 + 本期借方 - 本期贷方', fix_suggestion: '重新计算余额' },
      { id: '2', severity: 'high', check_type: '跨表校验', message: 'TB 合计与报表总资产不一致', fix_suggestion: '核对报表映射' },
    ],
  },
}

export const Empty: Story = {
  args: {
    findings: [],
  },
}
