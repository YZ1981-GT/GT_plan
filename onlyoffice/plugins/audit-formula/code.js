/**
 * ONLYOFFICE 审计取数公式插件 — code.js
 *
 * 注册 5 个自定义函数到 ONLYOFFICE 电子表格编辑器：
 *   - TB(account_code, column_name)          — 试算平衡表取数
 *   - WP(wp_code, cell_ref)                  — 跨底稿引用
 *   - AUX(account_code, aux_dim, dim_val, column_name) — 辅助余额取数
 *   - PREV(formula_type, ...params)          — 上年同期数据（year-1 包装）
 *   - SUM_TB(account_code_range, column_name) — 科目区间汇总
 *
 * 后端 API: POST /api/formula/execute
 * 请求体: { project_id, year, formula_type, params }
 * 响应体: { value, cached, error }
 *
 * 需求: 2.9 / Task 16 + 16.2
 */
(function () {
  'use strict';

  // ================================================================
  // 配置
  // ================================================================
  var API_BASE = 'http://localhost:8000';

  // ================================================================
  // 审计上下文获取：优先 URL 参数，回退 window.AUDIT_CONTEXT
  // ================================================================
  function getCtx() {
    var s = window.location.search || '', p = {};
    s.replace(/[?&]+([^=&]+)=([^&]*)/gi, function (_, k, v) {
      p[decodeURIComponent(k)] = decodeURIComponent(v);
    });
    if (p.project_id && p.year) {
      return { project_id: p.project_id, year: parseInt(p.year, 10) };
    }
    var g = window.AUDIT_CONTEXT;
    if (g && g.project_id && g.year) {
      return { project_id: g.project_id, year: parseInt(g.year, 10) };
    }
    return null;
  }

  // ================================================================
  // 中文列名映射（TB / AUX / SUM_TB 共用）
  // ================================================================
  var COL_MAP = {
    '期末余额': 'audited_amount',
    '未审数':   'unadjusted_amount',
    'AJE调整':  'aje_adjustment',
    'RJE调整':  'rje_adjustment',
    '年初余额': 'opening_balance'
  };
  function resolveCol(c) {
    if (!c) return c;
    var s = String(c).trim();
    return COL_MAP[s] || s;
  }

  // ================================================================
  // 后端 API 调用（同步 XHR）— Task 16.2 错误处理
  //
  // 错误处理策略：
  //   - 缺少上下文 → 返回 error 描述
  //   - HTTP 非 200 → 解析响应体提取 message/detail
  //   - 网络异常   → 捕获 exception 返回 error
  //   - 后端业务错误 → 透传 FormulaResult.error
  // ================================================================
  function callAPI(formulaType, params) {
    var ctx = getCtx();
    if (!ctx) {
      return { value: null, error: '未配置审计上下文（缺少 project_id 或 year）' };
    }
    var payload = JSON.stringify({
      project_id: ctx.project_id, year: ctx.year,
      formula_type: formulaType, params: params || {}
    });
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('POST', API_BASE + '/api/formula/execute', false);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.send(payload);
    } catch (e) {
      return { value: null, error: '网络错误: ' + (e.message || '请求失败') };
    }
    if (xhr.status === 200) {
      var resp = JSON.parse(xhr.responseText);
      // 后端 ResponseWrapperMiddleware 包装: { code, message, data }
      var d = resp.data || resp;
      if (d.error) return { value: null, error: d.error };
      return { value: d.value, error: null };
    }
    var errMsg = 'HTTP ' + xhr.status;
    try {
      var er = JSON.parse(xhr.responseText);
      errMsg = er.detail || er.message || errMsg;
    } catch (_) {}
    return { value: null, error: errMsg };
  }

  /** 成功返回数值，失败返回 #REF! + 错误描述 */
  function fmt(r) { return r.error ? '#REF! ' + r.error : r.value; }

  // ================================================================
  // 五个自定义函数（外部闭包版，供独立调试）
  // ================================================================

  /**
   * TB(account_code, column_name) — 试算平衡表取数
   * 示例: =TB("1001", "期末余额")
   */
  function fnTB(acct, col) {
    if (!acct || !col) return '#REF! TB: 参数不能为空';
    return fmt(callAPI('TB', {
      account_code: String(acct).trim(), column_name: resolveCol(col)
    }));
  }

  /**
   * WP(wp_code, cell_ref) — 跨底稿引用
   * 示例: =WP("D1-1", "B5")
   */
  function fnWP(wp, ref) {
    if (!wp || !ref) return '#REF! WP: 参数不能为空';
    return fmt(callAPI('WP', {
      wp_code: String(wp).trim(), cell_ref: String(ref).trim()
    }));
  }

  /**
   * AUX(account_code, aux_dimension, dimension_value, column_name) — 辅助余额取数
   * 示例: =AUX("1122", "客户", "客户A", "期末余额")
   */
  function fnAUX(acct, dim, val, col) {
    if (!acct || !dim || !val || !col) return '#REF! AUX: 参数不能为空';
    return fmt(callAPI('AUX', {
      account_code: String(acct).trim(), aux_dimension: String(dim).trim(),
      dimension_value: String(val).trim(), column_name: resolveCol(col)
    }));
  }

  /**
   * PREV(formula_type, ...params) — 上年同期数据（year-1 包装）
   * 示例: =PREV("TB", "1001", "期末余额")
   */
  function fnPREV(fType) {
    if (!fType) return '#REF! PREV: 需要指定公式类型';
    var a = [];
    for (var i = 1; i < arguments.length; i++) a.push(arguments[i]);
    var t = String(fType).trim().toUpperCase();
    var p = { formula_type: t };
    switch (t) {
      case 'TB':
        p.account_code = a[0] ? String(a[0]).trim() : '';
        p.column_name = resolveCol(a[1]);
        break;
      case 'WP':
        p.wp_code = a[0] ? String(a[0]).trim() : '';
        p.cell_ref = a[1] ? String(a[1]).trim() : '';
        break;
      case 'AUX':
        p.account_code = a[0] ? String(a[0]).trim() : '';
        p.aux_dimension = a[1] ? String(a[1]).trim() : '';
        p.dimension_value = a[2] ? String(a[2]).trim() : '';
        p.column_name = resolveCol(a[3]);
        break;
      case 'SUM_TB':
        p.account_code_range = a[0] ? String(a[0]).trim() : '';
        p.column_name = resolveCol(a[1]);
        break;
      default:
        return '#REF! PREV: 不支持的公式类型 "' + fType + '"';
    }
    return fmt(callAPI('PREV', p));
  }

  /**
   * SUM_TB(account_code_range, column_name) — 科目区间汇总
   * 示例: =SUM_TB("6001:6999", "期末余额")
   */
  function fnSUM_TB(range, col) {
    if (!range || !col) return '#REF! SUM_TB: 参数不能为空';
    return fmt(callAPI('SUM_TB', {
      account_code_range: String(range).trim(), column_name: resolveCol(col)
    }));
  }

  // ================================================================
  // ONLYOFFICE 插件注册
  // ================================================================

  if (typeof Asc !== 'undefined' && Asc.plugin) {

    Asc.plugin.init = function () {

      // 注入审计上下文到 Document Builder 全局作用域
      var ctx = getCtx();
      if (ctx) {
        var ctxJson = JSON.stringify({
          project_id: ctx.project_id, year: ctx.year, apiBase: API_BASE
        });
        Asc.plugin.info.recalculate = false;
        Asc.plugin.executeCommand('command',
          '(function(){ window._AUDIT_CTX = ' + ctxJson + '; })()'
        );
      }

      // callCommand 回调运行在 Document Builder 沙箱中，无法访问外部闭包
      // 因此 colMap / xhrCall 必须在回调内部重新定义
      Asc.plugin.callCommand(function () {
        if (typeof Api === 'undefined' || typeof Api.AddCustomFunction !== 'function') {
          console.warn('[Audit Formula] Api.AddCustomFunction 不可用');
          return;
        }

        // 内联列名映射
        var cm = {
          '期末余额': 'audited_amount', '未审数': 'unadjusted_amount',
          'AJE调整': 'aje_adjustment', 'RJE调整': 'rje_adjustment',
          '年初余额': 'opening_balance'
        };
        function rc(c) { if (!c) return ''; var s = String(c).trim(); return cm[s] || s; }

        // 内联同步 XHR 调用
        function xc(ft, pm) {
          var ctx = window._AUDIT_CTX;
          if (!ctx) return '#REF! 未配置审计上下文';
          try {
            var x = new XMLHttpRequest();
            x.open('POST', ctx.apiBase + '/api/formula/execute', false);
            x.setRequestHeader('Content-Type', 'application/json');
            x.send(JSON.stringify({
              project_id: ctx.project_id, year: ctx.year,
              formula_type: ft, params: pm
            }));
            if (x.status === 200) {
              var r = JSON.parse(x.responseText), d = r.data || r;
              if (d.error) return '#REF! ' + d.error;
              return d.value;
            }
            var em = 'HTTP ' + x.status;
            try { var e = JSON.parse(x.responseText); em = e.detail || e.message || em; } catch(_){}
            return '#REF! ' + em;
          } catch (e) {
            return '#REF! 网络错误: ' + (e.message || '请求失败');
          }
        }

        // 1. TB(account_code, column_name)
        Api.AddCustomFunction('TB', function (acct, col) {
          if (!acct || !col) return '#REF! TB: 参数不能为空';
          return xc('TB', { account_code: String(acct).trim(), column_name: rc(col) });
        }, 'TB(account_code, column_name)');

        // 2. WP(wp_code, cell_ref)
        Api.AddCustomFunction('WP', function (wp, ref) {
          if (!wp || !ref) return '#REF! WP: 参数不能为空';
          return xc('WP', { wp_code: String(wp).trim(), cell_ref: String(ref).trim() });
        }, 'WP(wp_code, cell_ref)');

        // 3. AUX(account_code, aux_dimension, dimension_value, column_name)
        Api.AddCustomFunction('AUX', function (acct, dim, val, col) {
          if (!acct || !dim || !val || !col) return '#REF! AUX: 参数不能为空';
          return xc('AUX', {
            account_code: String(acct).trim(), aux_dimension: String(dim).trim(),
            dimension_value: String(val).trim(), column_name: rc(col)
          });
        }, 'AUX(account_code, aux_dimension, dimension_value, column_name)');

        // 4. PREV(formula_type, ...params)
        Api.AddCustomFunction('PREV', function (ft) {
          if (!ft) return '#REF! PREV: 需要指定公式类型';
          var a = []; for (var i = 1; i < arguments.length; i++) a.push(arguments[i]);
          var t = String(ft).trim().toUpperCase(), p = { formula_type: t };
          switch (t) {
            case 'TB':     p.account_code = a[0] ? String(a[0]).trim() : ''; p.column_name = rc(a[1]); break;
            case 'WP':     p.wp_code = a[0] ? String(a[0]).trim() : ''; p.cell_ref = a[1] ? String(a[1]).trim() : ''; break;
            case 'AUX':    p.account_code = a[0] ? String(a[0]).trim() : ''; p.aux_dimension = a[1] ? String(a[1]).trim() : '';
                           p.dimension_value = a[2] ? String(a[2]).trim() : ''; p.column_name = rc(a[3]); break;
            case 'SUM_TB': p.account_code_range = a[0] ? String(a[0]).trim() : ''; p.column_name = rc(a[1]); break;
            default: return '#REF! PREV: 不支持 "' + ft + '"';
          }
          return xc('PREV', p);
        }, 'PREV(formula_type, ...params)');

        // 5. SUM_TB(account_code_range, column_name)
        Api.AddCustomFunction('SUM_TB', function (range, col) {
          if (!range || !col) return '#REF! SUM_TB: 参数不能为空';
          return xc('SUM_TB', { account_code_range: String(range).trim(), column_name: rc(col) });
        }, 'SUM_TB(account_code_range, column_name)');

        console.log('[Audit Formula] 5 个自定义函数注册完成: TB, WP, AUX, PREV, SUM_TB');
      }, false); // callCommand: false = 不刷新单元格
    };

    /** 插件按钮事件（非可视插件，预留接口） */
    Asc.plugin.button = function () { this.executeCommand('close', ''); };

  } else {
    // 非 ONLYOFFICE 环境 — 导出函数供调试/测试
    console.log('[Audit Formula] 独立模式，函数通过 window.AuditFormulas 调用');
    window.AuditFormulas = { TB: fnTB, WP: fnWP, AUX: fnAUX, PREV: fnPREV, SUM_TB: fnSUM_TB };
  }

})();
