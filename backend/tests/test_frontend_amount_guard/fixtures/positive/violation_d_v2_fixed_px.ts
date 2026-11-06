// Violation d: fixed px fontSize in el-table-v2 cellRenderer
const columns = [
  {
    key: 'amount',
    cellRenderer: ({ cellData }: any) => {
      return h('span', { style: { fontSize: '12px' } }, cellData)
    },
  },
]
