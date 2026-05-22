import type { Meta, StoryObj } from '@storybook/vue3'
import ExcelImportPreviewDialog from '@/components/common/ExcelImportPreviewDialog.vue'

const meta = {
  title: 'Common/ExcelImportPreviewDialog',
  component: ExcelImportPreviewDialog,
  tags: ['autodocs'],
} satisfies Meta<typeof ExcelImportPreviewDialog>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    visible: true,
    title: '导入子企业信息',
    expectedColumns: ['子企业名称', '企业代码', '核算科目'],
    sheetName: '数据填写',
    skipRows: 3,
    alertText: '请确保文件格式与模板一致，前 3 行为说明行将自动跳过',
  },
}

export const WithErrorRows: Story = {
  args: {
    visible: true,
    title: '导入试算表数据',
    expectedColumns: ['科目编号', '科目名称', '期末余额'],
    allowErrorRows: true,
    alertText: '存在异常行时仍可选择导入',
  },
}
