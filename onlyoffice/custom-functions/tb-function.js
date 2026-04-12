/**
 * ONLYOFFICE 自定义函数 — TB(account_code, column_name)
 *
 * 用途：在 Excel 单元格中通过 =TB("1001", "closing_balance") 调用后端 API，
 *       获取试算平衡表（Trial Balance）中指定科目的指定列值。
 *
 * 实现方式：使用 ONLYOFFICE Document Builder / Macro API 注册自定义函数。
 *           函数内部发起异步 HTTP 请求到后端 API 获取数据。
 *
 * 后端 API 端点（POC）：
 *   GET /api/trial-balance?account_code=xxx&column=yyy
 *   返回 JSON: { "code": 200, "data": { "value": 12345.67 } }
 *
 * 注意事项：
 *   - ONLYOFFICE Document Builder 的自定义函数运行在沙箱环境中
 *   - 实际部署时需要根据 ONLYOFFICE 版本调整 API 调用方式
 *   - 当前为 POC 验证，展示自定义函数 + 异步取数的可行性
 *
 * 需求: 6.5
 */

(function () {
  'use strict';

  /**
   * 后端 API 基础地址
   * 部署时应替换为实际的后端服务地址
   */
  var API_BASE_URL = 'http://localhost:8000';

  /**
   * TB 自定义函数 — 从后端获取试算平衡表数据
   *
   * @param {string} accountCode - 科目代码，如 "1001"（库存现金）、"1002"（银行存款）
   * @param {string} columnName  - 列名，如 "closing_balance"（期末余额）、"opening_balance"（期初余额）
   * @returns {number|string} 返回数值或错误信息
   *
   * 用法示例：
   *   =TB("1001", "closing_balance")    → 返回科目 1001 的期末余额
   *   =TB("6001", "debit_amount")       → 返回科目 6001 的借方发生额
   */
  function TB(accountCode, columnName) {
    // 参数校验
    if (!accountCode || !columnName) {
      return '#VALUE! 参数不能为空';
    }

    // 将参数转为字符串（单元格引用可能传入数字）
    accountCode = String(accountCode).trim();
    columnName = String(columnName).trim();

    try {
      // 构造请求 URL
      var url = API_BASE_URL + '/api/trial-balance'
        + '?account_code=' + encodeURIComponent(accountCode)
        + '&column=' + encodeURIComponent(columnName);

      // 发起同步 XMLHttpRequest（ONLYOFFICE 宏环境中的标准做法）
      // 注意：ONLYOFFICE Document Builder 宏环境支持同步 XHR
      var xhr = new XMLHttpRequest();
      xhr.open('GET', url, false); // 同步请求
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.send();

      if (xhr.status === 200) {
        var response = JSON.parse(xhr.responseText);
        if (response && response.data && response.data.value !== undefined) {
          return response.data.value;
        }
        return '#N/A 未找到数据';
      } else if (xhr.status === 404) {
        return '#N/A 科目不存在: ' + accountCode;
      } else {
        return '#ERROR! HTTP ' + xhr.status;
      }
    } catch (e) {
      // 网络错误或 JSON 解析错误
      return '#ERROR! ' + (e.message || '请求失败');
    }
  }

  /**
   * 注册自定义函数到 ONLYOFFICE
   *
   * 使用 ONLYOFFICE 的 AddCustomFunction API 将 TB 函数注册为可在单元格中使用的公式。
   *
   * 参考文档：
   *   https://api.onlyoffice.com/docs/plugin-and-macros/macros/
   *   https://api.onlyoffice.com/docs/office-api/usage-api/spreadsheet-api/
   *
   * 注册后，用户可以在任意单元格中输入 =TB("1001", "closing_balance") 来调用此函数。
   */
  if (typeof Asc !== 'undefined' && Asc.plugin) {
    // ONLYOFFICE 插件环境中注册
    Asc.plugin.init = function () {
      // 通过插件 API 注册自定义函数
      Asc.plugin.callCommand(function () {
        // 在 Document Builder 上下文中定义函数
        var oWorksheet = Api.GetActiveSheet();

        // 注册 TB 函数（通过 AddCustomFunction 如果可用）
        if (typeof Api.AddCustomFunction === 'function') {
          Api.AddCustomFunction(
            'TB',                          // 函数名
            TB,                            // 函数实现
            'TB(account_code, column_name)' // 函数签名描述
          );
        }
      });
    };

    // 插件事件处理
    Asc.plugin.button = function (id) {
      // 关闭插件窗口
      this.executeCommand('close', '');
    };
  }

  /**
   * 备选方案：通过 Document Builder 脚本直接使用
   *
   * 如果不通过插件注册，也可以在 Document Builder 脚本中直接调用：
   *
   *   builder.OpenFile("path/to/file.xlsx");
   *   var oWorksheet = Api.GetActiveSheet();
   *   var value = TB("1001", "closing_balance");
   *   oWorksheet.GetRange("A1").SetValue(value);
   *   builder.SaveFile("xlsx", "path/to/output.xlsx");
   *   builder.CloseFile();
   *
   * 这种方式适用于批量数据填充场景。
   */

  // 导出函数供外部使用
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { TB: TB };
  }

})();
