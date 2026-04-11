/**
 * ONLYOFFICE 审计复核批注插件 — 插件逻辑
 *
 * 功能：
 *   - 加载/展示复核意见列表（按创建时间排序）
 *   - 添加复核意见（支持单元格引用）
 *   - 回复复核意见（open → replied）
 *   - 解决复核意见（open/replied → resolved）
 *   - 状态筛选（全部/待处理/已回复/已解决）
 *   - 每 30 秒自动刷新
 *
 * 后端 API：
 *   GET    /api/working-papers/{wp_id}/reviews
 *   POST   /api/working-papers/{wp_id}/reviews
 *   PUT    /api/working-papers/{wp_id}/reviews/{id}/reply
 *   PUT    /api/working-papers/{wp_id}/reviews/{id}/resolve
 *
 * 需求: 5.2, 5.3, 5.4
 */

(function (window, undefined) {
  'use strict';

  // ========== 配置 ==========

  /** 后端 API 基础地址 */
  var API_BASE = 'http://localhost:8000';

  /** 当前底稿 ID（从 URL 参数或全局上下文获取） */
  var workingPaperId = null;

  /** 当前筛选状态（空字符串 = 全部） */
  var currentFilter = '';

  /** 自动刷新定时器 */
  var refreshTimer = null;

  /** 自动刷新间隔（毫秒） */
  var REFRESH_INTERVAL = 30000;

  // ========== 初始化 ==========

  /**
   * 获取 working_paper_id
   * 优先级：URL 参数 > window.AUDIT_CONTEXT > 空
   */
  function getWorkingPaperId() {
    // 1. 从 URL 参数获取
    try {
      var params = new URLSearchParams(window.location.search);
      var wpId = params.get('working_paper_id') || params.get('wp_id');
      if (wpId) return wpId;
    } catch (e) {
      // URLSearchParams 不可用时忽略
    }

    // 2. 从全局审计上下文获取
    if (window.AUDIT_CONTEXT && window.AUDIT_CONTEXT.working_paper_id) {
      return window.AUDIT_CONTEXT.working_paper_id;
    }

    return null;
  }

  /**
   * ONLYOFFICE 插件初始化
   */
  if (typeof Asc !== 'undefined' && Asc.plugin) {
    Asc.plugin.init = function () {
      console.log('[Audit Review] 插件初始化完成');
      workingPaperId = getWorkingPaperId();
      initUI();
      loadReviews();
      startAutoRefresh();
    };

    Asc.plugin.button = function (id) {
      if (id === -1) {
        stopAutoRefresh();
        this.executeCommand('close', '');
      }
    };
  } else {
    // 独立调试模式（非 ONLYOFFICE 环境）
    console.log('[Audit Review] 独立模式运行（非 ONLYOFFICE 环境）');
    document.addEventListener('DOMContentLoaded', function () {
      workingPaperId = getWorkingPaperId();
      initUI();
      loadReviews();
      startAutoRefresh();
    });
  }

  // ========== UI 事件绑定 ==========

  /**
   * 初始化 UI 事件监听
   */
  function initUI() {
    // 刷新按钮
    var btnRefresh = document.getElementById('btn-refresh');
    if (btnRefresh) {
      btnRefresh.addEventListener('click', function () {
        loadReviews();
      });
    }

    // 状态筛选按钮
    var filterBtns = document.querySelectorAll('.gt-filter-btn');
    filterBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        // 切换 active 样式
        filterBtns.forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        // 更新筛选条件并重新加载
        currentFilter = btn.getAttribute('data-status') || '';
        loadReviews();
      });
    });

    // 添加评论按钮
    var btnAdd = document.getElementById('btn-add-comment');
    if (btnAdd) {
      btnAdd.addEventListener('click', function () {
        addComment();
      });
    }
  }

  // ========== API 调用 ==========

  /**
   * 加载复核意见列表
   */
  function loadReviews() {
    if (!workingPaperId) {
      renderEmpty('未获取到底稿 ID，请通过正确入口打开');
      return;
    }

    var url = API_BASE + '/api/working-papers/' + workingPaperId + '/reviews';
    if (currentFilter) {
      url += '?status=' + encodeURIComponent(currentFilter);
    }

    apiGet(url, function (data) {
      if (Array.isArray(data)) {
        // 按创建时间排序（最新在前，后端已排序，此处做兜底）
        data.sort(function (a, b) {
          return (b.created_at || '').localeCompare(a.created_at || '');
        });
        renderReviewList(data);
      } else {
        renderEmpty('数据格式异常');
      }
    }, function (err) {
      console.error('[Audit Review] 加载失败:', err);
      renderEmpty('加载失败，请检查后端服务');
    });
  }

  /**
   * 添加复核意见
   */
  function addComment() {
    var textEl = document.getElementById('input-comment');
    var cellEl = document.getElementById('input-cell-ref');
    var btnEl = document.getElementById('btn-add-comment');

    var commentText = (textEl.value || '').trim();
    if (!commentText) {
      alert('请输入复核意见内容');
      return;
    }

    if (!workingPaperId) {
      alert('未获取到底稿 ID');
      return;
    }

    var payload = {
      comment_text: commentText,
      cell_reference: (cellEl.value || '').trim() || null,
      // POC 阶段使用固定 commenter_id，后续从登录态获取
      commenter_id: '00000000-0000-0000-0000-000000000001'
    };

    btnEl.disabled = true;
    btnEl.textContent = '提交中...';

    var url = API_BASE + '/api/working-papers/' + workingPaperId + '/reviews';
    apiPost(url, payload, function () {
      // 清空表单
      textEl.value = '';
      cellEl.value = '';
      btnEl.disabled = false;
      btnEl.textContent = '提交意见';
      // 刷新列表
      loadReviews();
    }, function (err) {
      console.error('[Audit Review] 添加失败:', err);
      alert('提交失败: ' + (err || '未知错误'));
      btnEl.disabled = false;
      btnEl.textContent = '提交意见';
    });
  }

  /**
   * 回复复核意见
   * @param {string} reviewId - 复核意见 ID
   * @param {string} replyText - 回复内容
   */
  function replyReview(reviewId, replyText) {
    if (!replyText || !replyText.trim()) {
      alert('请输入回复内容');
      return;
    }

    var payload = {
      reply_text: replyText.trim(),
      // POC 阶段使用固定 replier_id
      replier_id: '00000000-0000-0000-0000-000000000002'
    };

    var url = API_BASE + '/api/working-papers/' + workingPaperId
      + '/reviews/' + reviewId + '/reply';

    apiPut(url, payload, function () {
      loadReviews();
    }, function (err) {
      console.error('[Audit Review] 回复失败:', err);
      alert('回复失败: ' + (err || '未知错误'));
    });
  }

  /**
   * 解决复核意见
   * @param {string} reviewId - 复核意见 ID
   */
  function resolveReview(reviewId) {
    if (!confirm('确认标记为已解决？')) return;

    var payload = {
      // POC 阶段使用固定 resolved_by
      resolved_by: '00000000-0000-0000-0000-000000000003'
    };

    var url = API_BASE + '/api/working-papers/' + workingPaperId
      + '/reviews/' + reviewId + '/resolve';

    apiPut(url, payload, function () {
      loadReviews();
    }, function (err) {
      console.error('[Audit Review] 解决失败:', err);
      alert('操作失败: ' + (err || '未知错误'));
    });
  }

  // ========== 渲染 ==========

  /**
   * 渲染复核意见列表
   * @param {Array} reviews - 复核意见数组
   */
  function renderReviewList(reviews) {
    var container = document.getElementById('review-list');
    if (!container) return;

    if (!reviews || reviews.length === 0) {
      renderEmpty('暂无复核意见');
      return;
    }

    var html = '';
    reviews.forEach(function (item) {
      var status = item.status || 'open';
      var statusLabel = { open: '待处理', replied: '已回复', resolved: '已解决' };
      var badgeClass = 'badge-' + status;

      html += '<div class="gt-comment-card status-' + status + '">';

      // 卡片头部：评论人 + 状态徽章 + 时间
      html += '<div class="gt-comment-header">';
      html += '  <span class="gt-commenter">' + escapeHtml(item.commenter_id || '未知') + '</span>';
      html += '  <span class="gt-status-badge ' + badgeClass + '">' + (statusLabel[status] || status) + '</span>';
      html += '  <span class="gt-comment-time">' + formatTime(item.created_at) + '</span>';
      html += '</div>';

      // 单元格引用
      if (item.cell_reference) {
        html += '<span class="gt-cell-ref">📍 ' + escapeHtml(item.cell_reference) + '</span>';
      }

      // 评论正文
      html += '<div class="gt-comment-text">' + escapeHtml(item.comment_text) + '</div>';

      // 回复内容（如果有）
      if (item.reply_text) {
        html += '<div class="gt-reply-block">';
        html += '  <div class="gt-reply-label">💬 回复</div>';
        html += '  <div class="gt-reply-text">' + escapeHtml(item.reply_text) + '</div>';
        if (item.replied_at) {
          html += '  <div class="gt-reply-time">' + formatTime(item.replied_at) + '</div>';
        }
        html += '</div>';
      }

      // 操作按钮（仅未解决的显示）
      if (status !== 'resolved') {
        html += '<div class="gt-comment-actions">';

        // 回复按钮（仅 open 状态可回复）
        if (status === 'open') {
          html += '<button class="gt-action-btn" onclick="window.__auditReview.toggleReply(\'' + item.id + '\')">💬 回复</button>';
        }

        // 解决按钮（open 和 replied 都可解决）
        html += '<button class="gt-action-btn btn-resolve" onclick="window.__auditReview.resolve(\'' + item.id + '\')">✅ 解决</button>';

        html += '</div>';

        // 内联回复表单（open 状态）
        if (status === 'open') {
          html += '<div class="gt-reply-form" id="reply-form-' + item.id + '">';
          html += '  <textarea id="reply-text-' + item.id + '" placeholder="输入回复内容..."></textarea>';
          html += '  <button class="gt-reply-submit" onclick="window.__auditReview.submitReply(\'' + item.id + '\')">提交回复</button>';
          html += '</div>';
        }
      }

      html += '</div>';
    });

    container.innerHTML = html;
  }

  /**
   * 渲染空状态提示
   * @param {string} message - 提示文字
   */
  function renderEmpty(message) {
    var container = document.getElementById('review-list');
    if (container) {
      container.innerHTML = '<div class="gt-empty-tip">' + escapeHtml(message) + '</div>';
    }
  }

  // ========== 工具函数 ==========

  /**
   * HTML 转义，防止 XSS
   * @param {string} str - 原始字符串
   * @returns {string} 转义后的安全字符串
   */
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /**
   * 格式化时间显示
   * @param {string} isoStr - ISO 8601 时间字符串
   * @returns {string} 格式化后的时间（如 "03-15 14:30"）
   */
  function formatTime(isoStr) {
    if (!isoStr) return '';
    try {
      var d = new Date(isoStr);
      var mm = String(d.getMonth() + 1).padStart(2, '0');
      var dd = String(d.getDate()).padStart(2, '0');
      var hh = String(d.getHours()).padStart(2, '0');
      var mi = String(d.getMinutes()).padStart(2, '0');
      return mm + '-' + dd + ' ' + hh + ':' + mi;
    } catch (e) {
      return isoStr;
    }
  }

  // ========== 自动刷新 ==========

  /** 启动自动刷新（每 30 秒） */
  function startAutoRefresh() {
    stopAutoRefresh();
    refreshTimer = setInterval(function () {
      loadReviews();
    }, REFRESH_INTERVAL);
    console.log('[Audit Review] 自动刷新已启动（间隔 ' + (REFRESH_INTERVAL / 1000) + ' 秒）');
  }

  /** 停止自动刷新 */
  function stopAutoRefresh() {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  // ========== HTTP 封装 ==========

  /**
   * GET 请求
   * @param {string} url - 请求地址
   * @param {Function} onSuccess - 成功回调（参数为解析后的 JSON）
   * @param {Function} onError - 失败回调
   */
  function apiGet(url, onSuccess, onError) {
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('GET', url, true);
      xhr.timeout = 10000;
      xhr.setRequestHeader('Accept', 'application/json');

      xhr.onload = function () {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            var resp = JSON.parse(xhr.responseText);
            // 兼容 ResponseWrapperMiddleware 包装格式
            var data = resp.data !== undefined ? resp.data : resp;
            onSuccess(data);
          } catch (e) {
            onError('JSON 解析失败');
          }
        } else {
          onError('HTTP ' + xhr.status);
        }
      };

      xhr.onerror = function () { onError('网络错误'); };
      xhr.ontimeout = function () { onError('请求超时'); };
      xhr.send();
    } catch (e) {
      onError(e.message);
    }
  }

  /**
   * POST 请求
   * @param {string} url - 请求地址
   * @param {Object} payload - 请求体
   * @param {Function} onSuccess - 成功回调
   * @param {Function} onError - 失败回调
   */
  function apiPost(url, payload, onSuccess, onError) {
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('POST', url, true);
      xhr.timeout = 10000;
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.setRequestHeader('Accept', 'application/json');

      xhr.onload = function () {
        if (xhr.status >= 200 && xhr.status < 300) {
          onSuccess();
        } else {
          var detail = '';
          try {
            var resp = JSON.parse(xhr.responseText);
            detail = resp.detail || resp.message || '';
          } catch (e) { /* ignore */ }
          onError(detail || 'HTTP ' + xhr.status);
        }
      };

      xhr.onerror = function () { onError('网络错误'); };
      xhr.ontimeout = function () { onError('请求超时'); };
      xhr.send(JSON.stringify(payload));
    } catch (e) {
      onError(e.message);
    }
  }

  /**
   * PUT 请求
   * @param {string} url - 请求地址
   * @param {Object} payload - 请求体
   * @param {Function} onSuccess - 成功回调
   * @param {Function} onError - 失败回调
   */
  function apiPut(url, payload, onSuccess, onError) {
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('PUT', url, true);
      xhr.timeout = 10000;
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.setRequestHeader('Accept', 'application/json');

      xhr.onload = function () {
        if (xhr.status >= 200 && xhr.status < 300) {
          onSuccess();
        } else {
          var detail = '';
          try {
            var resp = JSON.parse(xhr.responseText);
            detail = resp.detail || resp.message || '';
          } catch (e) { /* ignore */ }
          onError(detail || 'HTTP ' + xhr.status);
        }
      };

      xhr.onerror = function () { onError('网络错误'); };
      xhr.ontimeout = function () { onError('请求超时'); };
      xhr.send(JSON.stringify(payload));
    } catch (e) {
      onError(e.message);
    }
  }

  // ========== 全局暴露（供 onclick 调用） ==========

  window.__auditReview = {
    /** 切换回复表单显示/隐藏 */
    toggleReply: function (reviewId) {
      var form = document.getElementById('reply-form-' + reviewId);
      if (form) {
        form.classList.toggle('visible');
        if (form.classList.contains('visible')) {
          var textarea = document.getElementById('reply-text-' + reviewId);
          if (textarea) textarea.focus();
        }
      }
    },

    /** 提交回复 */
    submitReply: function (reviewId) {
      var textarea = document.getElementById('reply-text-' + reviewId);
      if (textarea) {
        replyReview(reviewId, textarea.value);
      }
    },

    /** 解决复核意见 */
    resolve: function (reviewId) {
      resolveReview(reviewId);
    }
  };

})(window);
