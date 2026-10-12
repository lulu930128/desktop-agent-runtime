JSON.stringify((() => {
  const selectors = [".work-panel", ".rail", ".chrome", ".stage", ".chat-header", ".message-list", ".composer", ".conversation-controls", ".settings-shell", ".settings-nav", ".settings-content", ".history-drawer", ".local-schedule"];
  const geometry = Object.fromEntries(selectors.map(selector => {
    const node = document.querySelector(selector);
    if (!node) return [selector, null];
    const rect = node.getBoundingClientRect();
    const css = getComputedStyle(node);
    return [selector, {x: rect.x, y: rect.y, width: rect.width, height: rect.height,
      font: css.font, color: css.color, background: css.backgroundColor, display: css.display}];
  }));
  const css = getComputedStyle(document.documentElement);
  // Qt WebEngine may resolve custom properties without enumerating them.
  // Names mirror the original styles.css :root; values must come from the page.
  const tokenNames = ["--ink", "--deep", "--paper", "--muted", "--line", "--moon", "--iris", "--good", "--warn", "--bad", "--quiet", "--rail-width", "--detail-width", "--chrome-height", "--ui-font", "--data-font"];
  const tokens = Object.fromEntries(tokenNames.map(key => [key, css.getPropertyValue(key).trim()]));
  // Read-only deep layout evidence. Never normalize fonts, dates, margins or pixels.
  const properties = ["fontFamily", "fontSize", "fontWeight", "fontStyle", "lineHeight", "letterSpacing", "whiteSpace", "width", "minWidth", "maxWidth", "height", "boxSizing", "marginTop", "marginBottom", "paddingTop", "paddingBottom", "borderTopWidth", "borderBottomWidth", "display", "alignItems", "gap", "appearance"];
  const deepSelectors = [".today-frame", ".today-frame > header", ".today-frame > header > .section-kicker", ".today-frame > header > .today-question", ".today-frame > header > .today-summary", ".today-primary > section > .block-heading", ".today-primary", ".priority-list", ".priority-item", ".empty-state", ".block-heading", ".local-schedule", ".schedule-toolbar", '.schedule-toolbar input[type="date"]'];
  const deepGeometry = Object.fromEntries(deepSelectors.map(selector => [selector,
    Array.from(document.querySelectorAll(selector)).map(node => {
      const rect = node.getBoundingClientRect(), computed = getComputedStyle(node);
      const range = document.createRange(); range.selectNodeContents(node);
      const textRects = Array.from(range.getClientRects()).map(r => ({x:r.x,y:r.y,width:r.width,height:r.height}));
      return {tag: node.tagName, text: node.textContent, value: node.value ?? null,
        rect: {x:rect.x,y:rect.y,width:rect.width,height:rect.height,bottom:rect.bottom},
        css: Object.fromEntries(properties.map(p => [p, computed[p]])), textRects,
        clientWidth:node.clientWidth, scrollWidth:node.scrollWidth, offsetWidth:node.offsetWidth,
        parent:node.parentElement?.className ?? null};
    })]));
  const fontChecks = typeof document.fonts.check === "function"
    ? Object.fromEntries(["Segoe UI", "Microsoft JhengHei", "Noto Sans TC", "Arial", "monospace"].map(f => [f, document.fonts.check(`14px "${f}"`, "今天星期六 0123456789")])) : {};
  const stage = document.querySelector('.stage'), drawer = document.querySelector('.history-drawer');
  const stageRect = geometry['.stage'], drawerRect = geometry['.history-drawer'];
  let visibleIntersection = null;
  if (stageRect && drawerRect) {
    const x = Math.max(0, stageRect.x, drawerRect.x), y = Math.max(0, stageRect.y, drawerRect.y);
    const right = Math.min(innerWidth, stageRect.x + stageRect.width, drawerRect.x + drawerRect.width);
    const bottom = Math.min(innerHeight, stageRect.y + stageRect.height, drawerRect.y + drawerRect.height);
    visibleIntersection = {x, y, width:Math.max(0, right-x), height:Math.max(0, bottom-y)};
  }
  const relevantAnimations = typeof document.getAnimations === 'function'
    ? document.getAnimations().filter(a => a.effect?.target === stage || a.effect?.target === drawer || drawer?.contains?.(a.effect?.target)) : null;
  const animations = relevantAnimations?.map(a => ({playState:a.playState, pending:a.pending === true})) ?? null;
  const animationsSettled = animations !== null && animations.every(a => !a.pending && a.playState !== 'running');
  const drawerCss = drawer ? getComputedStyle(drawer) : null;
  return {ready: !!document.querySelector(".work-panel") && document.body.innerText.includes("SYNTHETIC"),
    viewport: {width: innerWidth, height: innerHeight, devicePixelRatio},
    screen: {width: screen.width, height: screen.height, colorDepth: screen.colorDepth},
    userAgent: navigator.userAgent, language: navigator.language,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    fontStatus: document.fonts.status, tokens, geometry, deepGeometry, fontChecks,
    deepCoverage: {today: deepGeometry[".today-frame"].length > 0,
      required: Object.fromEntries([".today-frame > header", ".today-frame > header > .section-kicker", ".today-frame > header > .today-question", ".today-frame > header > .today-summary", ".today-primary > section > .block-heading", ".priority-list", ".local-schedule", '.schedule-toolbar input[type="date"]'].map(s => [s, deepGeometry[s].length]))},
    intl: {date: new Intl.DateTimeFormat("zh-TW", {month:"long",day:"numeric",weekday:"long",timeZone:"UTC"}).format(new Date("2026-10-10T12:00:00Z")), resolved: Intl.DateTimeFormat().resolvedOptions()},
    categories: Array.from(document.querySelectorAll(".settings-nav-item strong")).map(node => node.textContent),
    history: {opened: stage?.classList?.contains('has-history') === true
      && (visibleIntersection?.width ?? 0) > 0 && (visibleIntersection?.height ?? 0) > 0
      && drawerRect?.display !== 'none' && drawerCss?.visibility !== 'hidden' && drawerCss?.opacity !== '0',
      visibleIntersection, animations, animationsSettled},
    overflow: {width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight}};
})())
