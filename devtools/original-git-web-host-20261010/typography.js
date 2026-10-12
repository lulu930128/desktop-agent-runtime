JSON.stringify((() => {
  // Read-only page probes. Canvas is detached; original DOM/CSS/text never changes.
  const node = document.querySelector('.today-frame > header > .section-kicker');
  const input = document.querySelector('.schedule-toolbar input[type="date"]');
  const codepoints = text => Array.from(text).map(c => `U+${c.codePointAt(0).toString(16).toUpperCase().padStart(4,'0')}`);
  const formatter = new Intl.DateTimeFormat('zh-TW', {month:'long',day:'numeric',weekday:'long'});
  const date = new Date('2026-10-11T12:00:00+08:00');
  const formatted = formatter.format(date);
  let kicker = null;
  if (node) {
    const css = getComputedStyle(node), canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    const strings = [node.textContent, '10月11日星期日', '10月11日 星期日', ' ', '0123456789', '星期日'];
    const families = [css.fontFamily, '"Cascadia Mono"', 'Consolas', '"Microsoft JhengHei UI"', '"Segoe UI"', 'monospace'];
    const metrics = [];
    if (context) for (const family of families) for (const text of strings) {
      context.font = `${css.fontStyle} ${css.fontWeight} ${css.fontSize} ${family}`;
      const m = context.measureText(text);
      metrics.push({family, text, canvasFont:context.font, width:m.width,
        actualBoundingBoxAscent:m.actualBoundingBoxAscent, actualBoundingBoxDescent:m.actualBoundingBoxDescent,
        fontBoundingBoxAscent:m.fontBoundingBoxAscent, fontBoundingBoxDescent:m.fontBoundingBoxDescent});
    }
    const glyphRects = [];
    // The original kicker is plain text; preserve UTF-16 offsets for Range.
    for (const child of node.childNodes) if (child.nodeType === 3) {
      let offset = 0;
      for (const char of child.textContent) {
        const range = document.createRange(); range.setStart(child, offset); offset += char.length; range.setEnd(child, offset);
        glyphRects.push({char, codepoints:codepoints(char), rects:Array.from(range.getClientRects(), r => ({x:r.x,y:r.y,width:r.width,height:r.height}))});
      }
    }
    kicker = {text:node.textContent, codepoints:codepoints(node.textContent), font:css.font,
      fontFamily:css.fontFamily, lineHeight:css.lineHeight, fontSize:css.fontSize, metrics, glyphRects};
  }
  return {kicker, intl:{fixedInstant:date.toISOString(), formatted, codepoints:codepoints(formatted),
    parts:formatter.formatToParts(date), resolved:formatter.resolvedOptions()},
    nativeDate:input ? {type:input.type, value:input.value, width:input.getBoundingClientRect().width,
      lang:input.lang, documentLang:document.documentElement.lang, appearance:getComputedStyle(input).appearance} : null,
    limitations:['computed family and fonts.check do not identify actual fallback glyph fonts',
      'canvas metrics do not establish DOM line-box causality or ICU version',
      'native date shadow control internals and real picker interaction remain UNVERIFIED'],
    actualGlyphFonts:'UNVERIFIED', icuVersion:'UNVERIFIED'};
})())
