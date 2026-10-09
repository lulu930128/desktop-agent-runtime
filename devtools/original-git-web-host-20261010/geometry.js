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
  const tokens = Object.fromEntries(Array.from(css).filter(key => key.startsWith("--")).map(key => [key, css.getPropertyValue(key).trim()]));
  return {ready: !!document.querySelector(".work-panel") && document.body.innerText.includes("SYNTHETIC"),
    viewport: {width: innerWidth, height: innerHeight, devicePixelRatio},
    screen: {width: screen.width, height: screen.height, colorDepth: screen.colorDepth},
    userAgent: navigator.userAgent, language: navigator.language,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    fontStatus: document.fonts.status, tokens, geometry,
    categories: Array.from(document.querySelectorAll(".settings-nav-item strong")).map(node => node.textContent),
    overflow: {width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight}};
})())
