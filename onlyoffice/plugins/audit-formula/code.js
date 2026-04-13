/**
 * ONLYOFFICE Audit Formula Plugin - code.js
 *
 * Registers 5 custom functions: TB / WP / AUX / PREV / SUM_TB
 * Backend API: POST /api/formula/execute
 * Request: { project_id, year, formula_type, params }
 * Response: { value, cached, error }
 *
 * Requirements: 2.9 / Task 16 + 16.2
 */
(function () {
  'use strict';

  // ================================================================
  // Configuration
  // ================================================================
  var API_BASE = 'http://localhost:8000';

  // ================================================================
  // Audit Context - from URL params or window.AUDIT_CONTEXT
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
  // Chinese column name mapping (TB/AUX/SUM_TB shared)
  // ================================================================
  var COL_MAP = {};
  COL_MAP['\u671f\u672b\u4f59\u989d'] = 'audited_amount';     // 期末余额
  COL_MAP['\u672a\u5ba1\u6570']       = 'unadjusted_amount';  // 未审数
  COL_MAP['AJE\u8c03\u6574']          = 'aje_adjustment';     // AJE调整
  COL_MAP['RJE\u8c03\u6574']          = 'rje_adjustment';     // RJE调整
  COL_MAP['\u5e74\u521d\u4f59\u989d'] = 'opening_balance';    // 年初余额

  function resolveCol(c) {
    if (!c) return c;
    var s = String(c).trim();
    return COL_MAP[s] || s;
  }

  // ================================================================
  // Backend API call (sync XHR) - Task 16.2 error handling
  // ================================================================
  function callAPI(formulaType, params) {
    var ctx = getCtx();
    if (!ctx) {
      return { value: null, error: '\u672a\u914d\u7f6e\u5ba1\u8ba1\u4e0a\u4e0b\u6587' };
    }
    var payload = JSON.stringify({
      project_id: ctx.project_id,
      year: ctx.year,
      formula_type: formulaType,
      params: params || {}
    });
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('POST', API_BASE + '/api/formula/execute', false);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.send(payload);
    } catch (e) {
      return { value: null, error: '\u7f51\u7edc\u9519\u8bef: ' + (e.message || '\u8bf7\u6c42\u5931\u8d25') };
    }
    if (xhr.status === 200) {
      var resp = JSON.parse(xhr.responseText);
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

  function fmt(r) { return r.error ? '#REF! ' + r.error : r.value; }


  // ================================================================
  // 5 custom functions (outer closure - for standalone debugging)
  // ================================================================

  // TB(account_code, column_name) - Trial Balance lookup
  // Example: =TB("1001", "\u671f\u672b\u4f59\u989d")
  function fnTB(acct, col) {
    if (!acct || !col) return '#REF! TB: \u53c2\u6570\u4e0d\u80fd\u4e3a\u7a7a';
    return fmt(callAPI('TB', {
      account_code: String(acct).trim(), column_name: resolveCol(col)
    }));
  }

  // WP(wp_code, cell_ref) - Cross-workpaper reference
  // Example: =WP("D1-1", "B5")
  function fnWP(wp, ref) {
    if (!wp || !ref) return '#REF! WP: \u53c2\u6570\u4e0d\u80fd\u4e3a\u7a7a';
    return fmt(callAPI('WP', {
      wp_code: String(wp).trim(), cell_ref: String(ref).trim()
    }));
  }

  // AUX(account_code, aux_dimension, dimension_value, column_name)
  // Example: =AUX("1122", "\u5ba2\u6237", "\u5ba2\u6237A", "\u671f\u672b\u4f59\u989d")
  function fnAUX(acct, dim, val, col) {
    if (!acct || !dim || !val || !col) return '#REF! AUX: \u53c2\u6570\u4e0d\u80fd\u4e3a\u7a7a';
    return fmt(callAPI('AUX', {
      account_code: String(acct).trim(),
      aux_dimension: String(dim).trim(),
      dimension_value: String(val).trim(),
      column_name: resolveCol(col)
    }));
  }

  // PREV(formula_type, ...params) - Prior year data (year-1 wrapper)
  // Example: =PREV("TB", "1001", "\u671f\u672b\u4f59\u989d")
  function fnPREV(fType) {
    if (!fType) return '#REF! PREV: \u9700\u8981\u6307\u5b9a\u516c\u5f0f\u7c7b\u578b';
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
        return '#REF! PREV: \u4e0d\u652f\u6301 "' + fType + '"';
    }
    return fmt(callAPI('PREV', p));
  }

  // SUM_TB(account_code_range, column_name) - Sum over account range
  // Example: =SUM_TB("6001:6999", "\u671f\u672b\u4f59\u989d")
  function fnSUM_TB(range, col) {
    if (!range || !col) return '#REF! SUM_TB: \u53c2\u6570\u4e0d\u80fd\u4e3a\u7a7a';
    return fmt(callAPI('SUM_TB', {
      account_code_range: String(range).trim(), column_name: resolveCol(col)
    }));
  }


  // ================================================================
  // ONLYOFFICE Plugin Registration
  // ================================================================

  if (typeof Asc !== 'undefined' && Asc.plugin) {

    Asc.plugin.init = function () {

      // Inject audit context into Document Builder global scope
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

      // Register functions inside callCommand (Document Builder sandbox)
      // NOTE: Cannot access outer closure - all helpers must be inline
      Asc.plugin.callCommand(function () {
        if (typeof Api === 'undefined' || typeof Api.AddCustomFunction !== 'function') {
          return;
        }

        // Inline column map
        var cm = {};
        cm['\u671f\u672b\u4f59\u989d'] = 'audited_amount';
        cm['\u672a\u5ba1\u6570'] = 'unadjusted_amount';
        cm['AJE\u8c03\u6574'] = 'aje_adjustment';
        cm['RJE\u8c03\u6574'] = 'rje_adjustment';
        cm['\u5e74\u521d\u4f59\u989d'] = 'opening_balance';
        function rc(c) { if (!c) return ''; var s = String(c).trim(); return cm[s] || s; }

        // Inline sync XHR call
        function xc(ft, pm) {
          var ctx = window._AUDIT_CTX;
          if (!ctx) return '#REF! \u672a\u914d\u7f6e\u5ba1\u8ba1\u4e0a\u4e0b\u6587';
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
            return '#REF! \u7f51\u7edc\u9519\u8bef: ' + (e.message || '\u8bf7\u6c42\u5931\u8d25');
          }
        }


        // 1. TB
        Api.AddCustomFunction('TB', function (acct, col) {
          if (!acct || !col) return '#REF! TB: \u53c2\u6570\u4e0d\u80fd\u4e3a\u7a7a';
          return xc('TB', { account_code: String(acct).trim(), column_name: rc(col) });
        }, 'TB(account_code, column_name)');

        // 2. WP
        Api.AddCustomFunction('WP', function (wp, ref) {
          if (!wp || !ref) return '#REF! WP: \u53c2\u6570\u4e0d\u80fd\u4e3a\u7a7a';
          return xc('WP', { wp_code: String(wp).trim(), cell_ref: String(ref).trim() });
        }, 'WP(wp_code, cell_ref)');

        // 3. AUX
        Api.AddCustomFunction('AUX', function (acct, dim, val, col) {
          if (!acct || !dim || !val || !col) return '#REF! AUX: \u53c2\u6570\u4e0d\u80fd\u4e3a\u7a7a';
          return xc('AUX', {
            account_code: String(acct).trim(), aux_dimension: String(dim).trim(),
            dimension_value: String(val).trim(), column_name: rc(col)
          });
        }, 'AUX(account_code, aux_dimension, dimension_value, column_name)');

        // 4. PREV
        Api.AddCustomFunction('PREV', function (ft) {
          if (!ft) return '#REF! PREV: \u9700\u8981\u6307\u5b9a\u516c\u5f0f\u7c7b\u578b';
          var a = []; for (var i = 1; i < arguments.length; i++) a.push(arguments[i]);
          var t = String(ft).trim().toUpperCase(), p = { formula_type: t };
          switch (t) {
            case 'TB':     p.account_code = a[0] ? String(a[0]).trim() : ''; p.column_name = rc(a[1]); break;
            case 'WP':     p.wp_code = a[0] ? String(a[0]).trim() : ''; p.cell_ref = a[1] ? String(a[1]).trim() : ''; break;
            case 'AUX':    p.account_code = a[0] ? String(a[0]).trim() : ''; p.aux_dimension = a[1] ? String(a[1]).trim() : '';
                           p.dimension_value = a[2] ? String(a[2]).trim() : ''; p.column_name = rc(a[3]); break;
            case 'SUM_TB': p.account_code_range = a[0] ? String(a[0]).trim() : ''; p.column_name = rc(a[1]); break;
            default: return '#REF! PREV: \u4e0d\u652f\u6301 "' + ft + '"';
          }
          return xc('PREV', p);
        }, 'PREV(formula_type, ...params)');

        // 5. SUM_TB
        Api.AddCustomFunction('SUM_TB', function (range, col) {
          if (!range || !col) return '#REF! SUM_TB: \u53c2\u6570\u4e0d\u80fd\u4e3a\u7a7a';
          return xc('SUM_TB', { account_code_range: String(range).trim(), column_name: rc(col) });
        }, 'SUM_TB(account_code_range, column_name)');

        console.log('[Audit Formula] 5 functions registered: TB, WP, AUX, PREV, SUM_TB');
      }, false);
    };

    Asc.plugin.button = function () { this.executeCommand('close', ''); };

  } else {
    // Standalone mode - export for debugging
    console.log('[Audit Formula] Standalone mode - window.AuditFormulas');
    window.AuditFormulas = { TB: fnTB, WP: fnWP, AUX: fnAUX, PREV: fnPREV, SUM_TB: fnSUM_TB };
  }

})();
