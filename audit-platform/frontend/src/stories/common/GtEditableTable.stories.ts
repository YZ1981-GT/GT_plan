import type { Meta, StoryObj } from '@storybook/vue3'
import GtEditableTable from '@/components/common/GtEditableTable.vue'

const meta = {
  title: 'Common/GtEditableTable',
  component: GtEditableTable,
  tags: ['autodocs'],
} satisfies Meta<typeof GtEditableTable>

export default meta
type Story = StoryObj<typeof meta>

const sampleColumns = [
  { prop: 'code', label: '科目编号', width: 120 },
  { prop: 'name', label: '科目名称', width: 200 },
  { prop: 'balance', label: '期末余额', width: 150, align: 'right' as const },
]

const sampleData = [
  { code: '1001', name: '库存现金', balance: 50000 },
  { code: '1002', name: '银行存款', balance: 4950000 },
  { code: '1012', name: '其他货币资金', balance: 120000 },
]

export const Default: Story = {
  args: {
    columns: sampleColumns,
    modelValue: sampleData,
  },
}

export const WithSelection: Story = {
  args: {
    columns: sampleColumns,
    modelValue: sampleData,
    showSelection: true,
  },
}

export const EditMode: Story = {
  args: {
    columns: sampleColumns,
    modelValue: sampleData,
    editable: true,
  },
}
