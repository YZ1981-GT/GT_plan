/**
 * ONLYOFFICE 审计侧边栏插件 — 插件逻辑
 *
 * 功能：
 *   - 初始化插件并连接 ONLYOFFICE Plugin API
 *   - 显示当前底稿的审计信息（静态 POC 数据）
 *   - 后续可扩展为从后端 API 动态获取数据
 *
 * ONLYOFFICE Plugin API 参考：
 *   https://api.onlyoffice.com/docs/plugin-and-macros/plugins/
 *
 * 需求: 6.6
 */

(function (window, undefined) {
  'use strict';

  /**
   * 后端 API 基础地址（POC 阶段使用静态数据，后续替换为实际 API 调用）
   */
  var API_BASE_URL = 'http://localhost:8000';

  /**
   * 插件初始化
   *
   * 当 ONLYOFFICE 加载插件时，调用 Asc.plugin.init 进行初始化。
   * POC 阶段使用静态数据展示，后续可替换为 API 调用。
   */
  if (typeof Asc !== 'undefined' && Asc.plugin) {

    Asc.plugin.init = function (data) {
      // 插件已加载，可以在此处进行初始化操作
      console.log('[Audit Sidebar] 插件初始化完成');

      // POC: 尝试从后端获取底稿信息（如果后端可用）
      loadWorkpaperInfo();
    };

    /**
     * 插件按钮点击事件
     * config.json 中未定义按钮，此处为预留接口
     */
    Asc.plugin.button = function (id) {
      if (id === -1) {
        // 关闭按钮
        this.executeCommand('close', '');
      }
    };

    /**
     * 监听编辑器事件（预留）
     * 后续可监听单元格选择变化，动态更新侧边栏内容
     */
    Asc.plugin.onExternalMouseUp = function () {
      // 鼠标释放事件，可用于检测用户交互
    };

    Asc.plugin.onMethodReturn = function (returnValue) {
      // 方法返回值回调
    };

  } else {
    // 非 ONLYOFFICE 环境（独立调试模式）
    console.log('[Audit Sidebar] 独立模式运行（非 ONLYOFFICE 环境）');
    loadWorkpaperInfo();
  }

  /**
   * 从后端加载底稿信息
   *
   * POC 阶段：先尝试调用后端 API，失败则使用静态数据。
   * 后续阶段：从后端 API 获取实际底稿元数据、复核状态和操作日志。
   */
  function loadWorkpaperInfo() {
    // POC: 尝试从后端获取数据
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('GET', API_BASE_URL + '/api/health', true);
      xhr.timeout = 3000;

      xhr.onload = function () {
        if (xhr.status === 200) {
          console.log('[Audit Sidebar] 后端连接正常，后续可加载实际数据');
          // TODO: 替换为实际的底稿信息 API 调用
          // fetchWorkpaperDetail(fileId);
        }
      };

      xhr.onerror = function () {
        console.log('[Audit Sidebar] 后端不可用，使用静态展示数据');
      };

      xhr.ontimeout = function () {
        console.log('[Audit Sidebar] 后端连接超时，使用静态展示数据');
      };

      xhr.send();
    } catch (e) {
      console.log('[Audit Sidebar] 网络请求异常:', e.message);
    }
  }

  /**
   * 更新侧边栏 UI（预留接口）
   *
   * 当从后端获取到实际数据后，调用此函数更新页面内容。
   *
   * @param {Object} data - 底稿信息对象
   * @param {string} data.code       - 底稿编号
   * @param {string} data.name       - 底稿名称
   * @param {string} data.cycle      - 所属循环
   * @param {string} data.author     - 编制人
   * @param {string} data.date       - 编制日期
   * @param {string} data.status     - 复核状态
   * @param {string} data.reviewer   - 复核人
   * @param {number} data.comments   - 复核意见数
   * @param {number} data.issues     - 未解决问题数
   * @param {Array}  data.logs       - 操作日志列表
   */
  function updateUI(data) {
    if (!data) return;

    var setTextById = function (id, text) {
      var el = document.getElementById(id);
      if (el) el.textContent = text;
    };

    setTextById('wp-code', data.code || '-');
    setTextById('wp-name', data.name || '-');
    setTextById('wp-cycle', data.cycle || '-');
    setTextById('wp-author', data.author || '-');
    setTextById('wp-date', data.date || '-');
    setTextById('wp-reviewer', data.reviewer || '-');
    setTextById('wp-comments', (data.comments || 0) + ' 条');
    setTextById('wp-issues', (data.issues || 0) + ' 条');

    // 更新状态徽章
    var statusEl = document.getElementById('wp-status');
    if (statusEl && data.status) {
      statusEl.textContent = data.status;
      statusEl.className = 'gt-status-badge '
        + (data.status === '已复核' ? 'gt-status-done' : 'gt-status-review');
    }

    // 更新操作日志
    if (data.logs && data.logs.length > 0) {
      var logList = document.getElementById('log-list');
      if (logList) {
        logList.innerHTML = '';
        data.logs.forEach(function (log) {
          var item = document.createElement('div');
          item.className = 'gt-log-item';
          item.innerHTML =
            '<div class="gt-log-time">' + escapeHtml(log.time) + '</div>' +
            '<div class="gt-log-action">' + escapeHtml(log.action) + '</div>';
          logList.appendChild(item);
        });
      }
    }
  }

  /**
   * HTML 转义，防止 XSS
   */
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

})(window);
