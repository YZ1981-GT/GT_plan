import type { Meta, StoryObj } from '@storybook/vue3'
import GtPrintPreview from '@/components/common/GtPrintPreview.vue'

const meta = {
  title: 'Common/GtPrintPreview',
  component: GtPrintPreview,
  tags: ['autodocs'],
} satisfies Meta<typeof GtPrintPreview>

export default meta
type Story = StoryObj<typeof meta>

const sampleColumns = [
  { prop: 'code', label: '科目编号', width: 100 },
  { prop: 'name', label: '科目名称', width: 200 },
  { prop: 'debit', label: '借方', width: 120, align: 'right' },
  { prop: 'credit', label: '贷方', width: 120, align: 'right' },
]

const sampleData = [
  { code: '1001', name: '库存现金', debit: 50000, credit: 0 },
  { code: '1002', name: '银行存款', debit: 4950000, credit: 100000 },
  { code: '1012', name: '其他货币资金', debit: 120000, credit: 0 },
]

export const Default: Story = {
  args: {
    modelValue: true,
    data: sampleData,
    columns: sampleColumns,
    title: '试算平衡表',
    subtitle: '2025年度',
  },
}

export const WithFooter: Story = {
  args: {
    modelValue: true,
    data: sampleData,
    columns: sampleColumns,
    title: '科目余额表',
    footerLeft: '致同会计师事务所',
    footerRight: '2025-01-15',
  },
}

export const EmptyData: Story = {
  args: {
    modelValue: true,
    data: [],
    columns: sampleColumns,
    title: '空表格预览',
  },
}
