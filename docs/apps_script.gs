/**
 * Penerima webhook Google Sheets untuk bot RMF.
 *
 * Menerima {kind: "<nama tab>", row: {...}} dari GitHub Actions dan menambahkan
 * satu baris ke tab dengan nama itu (equity, orders, flush_trades, flush_signals).
 * Header dibuat dari baris pertama; kolom baru ditambah di kanan tanpa menggeser
 * data lama.
 */
var ALLOWED = ['equity', 'orders', 'flush_trades', 'flush_signals'];

function doPost(e) {
  try {
    var body = JSON.parse(e.postData.contents);
    if (ALLOWED.indexOf(body.kind) < 0) return _json({ ok: false, error: 'kind tidak dikenal: ' + body.kind });
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sh = ss.getSheetByName(body.kind) || ss.insertSheet(body.kind);
    var row = body.row || {};
    var header = sh.getLastRow() > 0
      ? sh.getRange(1, 1, 1, Math.max(sh.getLastColumn(), 1)).getValues()[0]
      : [];
    if (header.length === 0 || (header.length === 1 && header[0] === '')) {
      header = Object.keys(row);
      sh.getRange(1, 1, 1, header.length).setValues([header]);
      sh.setFrozenRows(1);
      sh.getRange(1, 1, 1, header.length).setFontWeight('bold');
    } else {
      var missing = Object.keys(row).filter(function (k) { return header.indexOf(k) < 0; });
      if (missing.length) {
        sh.getRange(1, header.length + 1, 1, missing.length).setValues([missing]);
        header = header.concat(missing);
      }
    }
    sh.appendRow(header.map(function (k) {
      var v = row[k];
      return (v === undefined || v === null) ? '' : v;
    }));
    return _json({ ok: true, sheet: body.kind, row: sh.getLastRow() });
  } catch (err) {
    return _json({ ok: false, error: String(err) });
  }
}

function doGet() {
  return _json({ ok: true, service: 'rmf logger' });
}

function _json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
