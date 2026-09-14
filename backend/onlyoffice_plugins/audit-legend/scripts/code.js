(function (window, undefined) {
  "use strict";

  window.Asc.plugin.init = function () {
    // 插件初始化：无需自动动作，等待用户点击按钮
  };

  window.Asc.plugin.button = function (id) {
    // id=0 确定，id=-1 取消/关闭
    this.executeCommand("close", "");
  };

  /**
   * 在选中单元格前缀叠加审计符号
   * @param {string} symbol - 审计符号（√/ⓒ/➜）
   */
  window.applyLegend = function (symbol) {
    window.Asc.plugin.callCommand(function () {
      var oWorksheet = Api.GetActiveSheet();
      var oRange = oWorksheet.GetSelection();
      var currentValue = oRange.GetValue();
      // 避免重复叠加：检查是否已有该符号前缀
      if (currentValue && currentValue.indexOf(symbol) === 0) {
        return;
      }
      oRange.SetValue(symbol + " " + (currentValue || ""));
    }, true, true);
  };

  window.Asc.plugin.onTranslate = function () {};
})(window, undefined);
