(function (window, undefined) {
  "use strict";

  var PLUGIN_GUID = "asc.{B2C3D4E5-2222-3333-4444-TBFETCHPLU01}";

  window.Asc.plugin.init = function () {
    // 注册右键菜单项
    this.executeMethod("AddContextMenuItem", [{
      guid: PLUGIN_GUID,
      items: [
        { id: "tb_fetch", text: "从 TB 取数" }
      ]
    }]);
  };

  window.Asc.plugin.event_onContextMenuClick = function (options) {
    if (!options || options.id !== "tb_fetch") return;

    // 获取选中单元格信息，然后调后端取数
    this.callCommand(function () {
      var oSheet = Api.GetActiveSheet();
      var oRange = oSheet.GetSelection();
      var cellAddress = oRange.GetAddress();
      return cellAddress;  // 返回给 plugin 外部处理
    }, false, true, function (result) {
      if (result) {
        fetchTBData(result);
      }
    });
  };

  /**
   * 调用后端 auto_data_resolvers API 取数并回填
   * 复用平台既有鉴权（携带 session/cookie），不硬编码任何密钥
   */
  function fetchTBData(cellAddress) {
    // 从页面 URL 提取项目/底稿上下文（实际实现需根据 editorConfig.customization 传参）
    var baseUrl = window.location.origin;
    var apiUrl = baseUrl + "/api/workpapers/auto-data-resolve";

    // 使用 XMLHttpRequest 复用浏览器 cookie/session（不硬编码 token）
    var xhr = new XMLHttpRequest();
    xhr.open("POST", apiUrl, true);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.withCredentials = true;  // 携带 cookie（平台鉴权）

    xhr.onload = function () {
      if (xhr.status === 200) {
        try {
          var data = JSON.parse(xhr.responseText);
          if (data && data.value !== undefined) {
            fillCellValue(data.value);
          }
        } catch (e) {
          console.warn("[tb-fetch] 解析响应失败:", e);
        }
      } else {
        console.warn("[tb-fetch] API 请求失败, status:", xhr.status);
      }
    };

    xhr.onerror = function () {
      console.warn("[tb-fetch] 网络错误");
    };

    xhr.send(JSON.stringify({
      cell_address: cellAddress,
      source: "tb_balance"
    }));
  }

  /**
   * 将取数结果回填到选中单元格
   */
  function fillCellValue(value) {
    window.Asc.plugin.callCommand(function () {
      var oSheet = Api.GetActiveSheet();
      var oRange = oSheet.GetSelection();
      oRange.SetValue(String(value));
    }, true, true);
  }

  window.Asc.plugin.button = function (id) {
    this.executeCommand("close", "");
  };

  window.Asc.plugin.onTranslate = function () {};
})(window, undefined);
