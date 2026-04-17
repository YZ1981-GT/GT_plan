/**
 * ONLYOFFICE 审计取数函数插件 — 调整分录创建扩展
 * Phase 9 Task 9.11
 *
 * 用户在底稿中选中单元格 → 点击"创建调整分录"按钮
 * → 插件读取科目编码和金额 → 调用 POST /api/adjustments
 * → 创建成功后触发 ADJUSTMENT_CREATED 事件 → 级联更新试算表和报表
 */

(function () {
  'use strict';

  // 获取当前选中单元格的值
  function getSelectedCellValue(callback) {
    Asc.scope.callback = callback;
    var oWorksheet = Api.GetActiveSheet();
    var oRange = oWorksheet.GetSelection();
    if (oRange) {
      var value = oRange.GetValue();
      var address = oRange.GetAddress();
      callback({ value: value, address: address });
    } else {
      callback(null);
    }
  }

  // 创建调整分录
  function createAdjustmentEntry(projectId, accountCode, amount, description) {
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/projects/' + projectId + '/adjustments', false);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.setRequestHeader('Authorization', 'Bearer ' + getAccessToken());

    var payload = JSON.stringify({
      adjustment_type: 'AJE',
      description: description || '从底稿创建的调整分录',
      lines: [
        {
          account_code: accountCode,
          debit_amount: amount > 0 ? amount : 0,
          credit_amount: amount < 0 ? Math.abs(amount) : 0,
        }
      ]
    });

    xhr.send(payload);

    if (xhr.status === 200 || xhr.status === 201) {
      var result = JSON.parse(xhr.responseText);
      return { success: true, data: result.data || result };
    } else {
      return { success: false, error: xhr.statusText };
    }
  }

  // 获取访问令牌（从 URL 参数或 localStorage）
  function getAccessToken() {
    var params = new URLSearchParams(window.location.search);
    return params.get('access_token') || localStorage.getItem('access_token') || '';
  }

  // 注册按钮事件（在插件 UI 中调用）
  window.AuditAdjustmentPlugin = {
    createFromSelection: function (projectId, accountCode) {
      getSelectedCellValue(function (cellInfo) {
        if (!cellInfo || !cellInfo.value) {
          alert('请先选中包含金额的单元格');
          return;
        }

        var amount = parseFloat(cellInfo.value);
        if (isNaN(amount) || amount === 0) {
          alert('选中单元格的值不是有效金额');
          return;
        }

        var desc = prompt('请输入调整分录摘要：', '底稿调整 - ' + accountCode);
        if (!desc) return;

        var result = createAdjustmentEntry(projectId, accountCode, amount, desc);
        if (result.success) {
          alert('调整分录创建成功！编号：' + (result.data.entry_no || ''));
        } else {
          alert('创建失败：' + result.error);
        }
      });
    }
  };

})();
