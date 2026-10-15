/* Export Excel (.xlsx) sans dépendance : un classeur d'une feuille, écrit en XML SpreadsheetML et zippé
 * (entrées non compressées). Nombres, pourcentages et dates restent des valeurs Excel (pas du texte) ;
 * en-tête en gras, figé, avec filtres automatiques ; largeurs de colonnes ajustées au contenu. */
'use strict';
const Xlsx = (() => {
  const enc = new TextEncoder();
  const CRC = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
    return t;
  })();
  function crc32(b) { let c = 0xffffffff; for (let i = 0; i < b.length; i++) c = CRC[(c ^ b[i]) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; }

  /** Archive ZIP « stockée » (sans compression) : suffisant pour Excel, très rapide à produire. */
  function zip(files) {
    const parts = [], central = [];
    let offset = 0;
    for (const [name, text] of files) {
      const data = enc.encode(text), nm = enc.encode(name), crc = crc32(data);
      const local = new DataView(new ArrayBuffer(30));
      local.setUint32(0, 0x04034b50, true); local.setUint16(4, 20, true); local.setUint16(6, 0x0800, true);
      local.setUint32(14, crc, true); local.setUint32(18, data.length, true); local.setUint32(22, data.length, true); local.setUint16(26, nm.length, true);
      const cen = new DataView(new ArrayBuffer(46));
      cen.setUint32(0, 0x02014b50, true); cen.setUint16(4, 20, true); cen.setUint16(6, 20, true); cen.setUint16(8, 0x0800, true);
      cen.setUint32(16, crc, true); cen.setUint32(20, data.length, true); cen.setUint32(24, data.length, true); cen.setUint16(28, nm.length, true);
      cen.setUint32(42, offset, true);
      parts.push(local, nm, data);
      central.push(cen, nm);
      offset += 30 + nm.length + data.length;
    }
    const size = central.reduce((s, x) => s + (x.byteLength ?? x.length), 0);
    const end = new DataView(new ArrayBuffer(22));
    end.setUint32(0, 0x06054b50, true); end.setUint16(8, files.length, true); end.setUint16(10, files.length, true);
    end.setUint32(12, size, true); end.setUint32(16, offset, true);
    return new Blob([...parts, ...central, end], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  }

  const x = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, '');
  const colName = (i) => { let s = ''; for (i++; i; i = Math.floor((i - 1) / 26)) s = String.fromCharCode(65 + ((i - 1) % 26)) + s; return s; };
  const serial = (iso) => (Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) - Date.UTC(1899, 11, 30)) / 864e5;
  // Styles : 0 défaut · 1 en-tête · 2 entier · 3 pourcentage · 4 date · 5 décimal
  const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="1"><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF0A2357"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="6"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" applyFont="1" applyFill="1"/>
<xf numFmtId="3" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/><xf numFmtId="10" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/><xf numFmtId="4" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`;

  /**
   * Écrit et télécharge `name.xlsx`. columns = [{ label, kind: 'pct'|'int'|'num'|'date'|'text' (facultatif) }], rows = tableaux de valeurs.
   * Sans `kind`, le type est déduit de la valeur : nombre entier, nombre décimal, date ISO (AAAA-MM-JJ) ou texte.
   */
  function download(name, sheet, columns, rows) {
    const widths = columns.map((c) => Math.min(60, Math.max(8, String(c.label).length + 2)));
    const cell = (v, ci, ri) => {
      const ref = colName(ci) + (ri + 1), kind = columns[ci].kind;
      if (v == null || v === '' || (typeof v === 'number' && !isFinite(v))) return '';
      if (typeof v === 'number') {
        const s = kind === 'pct' ? 3 : kind === 'int' || (kind !== 'num' && Number.isInteger(v)) ? 2 : 5;
        widths[ci] = Math.max(widths[ci], Math.min(20, String(Math.round(v)).length + 5));
        return `<c r="${ref}" s="${s}"><v>${v}</v></c>`;
      }
      const t = String(v);
      if (kind !== 'text' && /^\d{4}-\d{2}-\d{2}$/.test(t)) { widths[ci] = Math.max(widths[ci], 12); return `<c r="${ref}" s="4"><v>${serial(t)}</v></c>`; }
      widths[ci] = Math.max(widths[ci], Math.min(60, t.length + 2));
      return `<c r="${ref}" t="inlineStr"><is><t xml:space="preserve">${x(t)}</t></is></c>`;
    };
    const head = `<row r="1">${columns.map((c, ci) => `<c r="${colName(ci)}1" s="1" t="inlineStr"><is><t xml:space="preserve">${x(c.label)}</t></is></c>`).join('')}</row>`;
    const body = rows.map((r, ri) => `<row r="${ri + 2}">${r.map((v, ci) => cell(v, ci, ri + 1)).join('')}</row>`).join('');
    const last = colName(columns.length - 1) + (rows.length + 1);
    const ws = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
<cols>${widths.map((w, i) => `<col min="${i + 1}" max="${i + 1}" width="${w}" customWidth="1"/>`).join('')}</cols><sheetData>${head}${body}</sheetData><autoFilter ref="A1:${last}"/></worksheet>`;
    const sheetName = x(String(sheet || 'Export').replace(/[[\]:*?/\\]/g, ' ').slice(0, 31));
    const blob = zip([
      ['[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'],
      ['_rels/.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'],
      ['xl/workbook.xml', `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="${sheetName}" sheetId="1" r:id="rId1"/></sheets><definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'${sheetName.replace(/'/g, "''")}'!$A$1:$${colName(columns.length - 1)}$${rows.length + 1}</definedName></definedNames></workbook>`],
      ['xl/_rels/workbook.xml.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'],
      ['xl/styles.xml', STYLES],
      ['xl/worksheets/sheet1.xml', ws],
    ]);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${name}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    return blob;
  }
  return { download, zip, crc32 };
})();
if (typeof module !== 'undefined') module.exports = Xlsx;
