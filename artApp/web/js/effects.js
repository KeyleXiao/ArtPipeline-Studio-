/**
 * 全局 UI 动效与 loading 工具
 */

const FX_MENU_MS = 220;

/** 按钮 busy：禁用 + 旋转环 */
export function setBtnBusy(btn, busy) {
  if (!btn) return;
  btn.classList.toggle("is-busy", busy);
  if (busy) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
  } else {
    btn.disabled = false;
    btn.removeAttribute("aria-busy");
  }
}

export async function withBtnBusy(btn, fn, { label } = {}) {
  if (btn?.classList.contains("is-busy")) return;
  const prevHtml = btn.innerHTML;
  const prevLabel = btn.textContent;
  setBtnBusy(btn, true);
  if (label) btn.textContent = label;
  try {
    return await fn();
  } finally {
    setBtnBusy(btn, false);
    if (label) {
      if (btn.dataset.keepHtml === "1") btn.innerHTML = prevHtml;
      else btn.textContent = prevLabel;
    }
  }
}

export function actionBtn(fromEvent) {
  if (!fromEvent) return null;
  return fromEvent.target?.closest?.(".btn") || fromEvent.target?.closest?.("[data-action]");
}

/** 点击涟漪 */
export function bindRipple(root = document) {
  root.addEventListener(
    "pointerdown",
    (e) => {
      const el = e.target.closest(".btn, .nav-item, .ctx-item, .cat-item, .asset-row, .tab, .seg-btn, .lang-btn, .radio-seg-item");
      if (!el || el.disabled || el.classList.contains("is-busy")) return;
      const rect = el.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height) * 1.6;
      const ripple = document.createElement("span");
      ripple.className = "fx-ripple";
      ripple.style.width = ripple.style.height = `${size}px`;
      ripple.style.left = `${e.clientX - rect.left - size / 2}px`;
      ripple.style.top = `${e.clientY - rect.top - size / 2}px`;
      el.classList.add("fx-ripple-host");
      el.appendChild(ripple);
      ripple.addEventListener("animationend", () => ripple.remove(), { once: true });
    },
    { passive: true },
  );
}

/** 启动页 */
export function showSplash() {
  const splash = document.getElementById("app-splash");
  if (!splash) return null;
  splash.classList.remove("is-hiding", "is-done");
  splash.setAttribute("aria-hidden", "false");
  document.body.classList.add("is-booting");
  return splash;
}

export function hideSplash(splash, { minMs = 800 } = {}) {
  const el = splash || document.getElementById("app-splash");
  if (!el) {
    document.body.classList.remove("is-booting");
    document.getElementById("app")?.classList.add("is-ready");
    return Promise.resolve();
  }
  const started = Date.now();
  return new Promise((resolve) => {
    const finish = () => {
      el.classList.add("is-done");
      el.setAttribute("aria-hidden", "true");
      document.body.classList.remove("is-booting");
      document.getElementById("app")?.classList.add("is-ready");
      resolve();
    };
    const run = () => {
      el.classList.add("is-hiding");
      el.addEventListener("transitionend", finish, { once: true });
      setTimeout(finish, 650);
    };
    const wait = Math.max(0, minMs - (Date.now() - started));
    setTimeout(run, wait);
  });
}

/** 全屏 overlay（重载配置等） */
export function showGlobalOverlay(message) {
  const ov = document.getElementById("fx-global-overlay");
  if (!ov) return;
  const msg = ov.querySelector(".fx-overlay-msg");
  if (msg && message) msg.textContent = message;
  ov.classList.remove("hidden");
  requestAnimationFrame(() => ov.classList.add("is-visible"));
}

export function hideGlobalOverlay() {
  const ov = document.getElementById("fx-global-overlay");
  if (!ov) return;
  ov.classList.remove("is-visible");
  const done = () => ov.classList.add("hidden");
  ov.addEventListener("transitionend", done, { once: true });
  setTimeout(done, 320);
}

export function setPanelLoading(el, loading) {
  el?.classList.toggle("is-loading", loading);
}

/** 浮动菜单开/关动画 */
export function openFloatingMenu(menu, positionFn) {
  if (!menu) return;
  menu.classList.remove("hidden", "fx-closing");
  if (positionFn) positionFn();
  requestAnimationFrame(() => {
    requestAnimationFrame(() => menu.classList.add("fx-open"));
  });
}

export function closeFloatingMenu(menu, { resetPosition = false } = {}) {
  if (!menu || menu.classList.contains("hidden")) return;
  if (!menu.classList.contains("fx-open")) {
    menu.classList.add("hidden");
    return;
  }
  menu.classList.remove("fx-open");
  menu.classList.add("fx-closing");
  const done = () => {
    menu.classList.add("hidden");
    menu.classList.remove("fx-closing");
    if (resetPosition) {
      menu.style.left = "";
      menu.style.top = "";
    }
  };
  menu.addEventListener("transitionend", done, { once: true });
  setTimeout(done, FX_MENU_MS + 40);
}

export function closeAllFloatingMenus(selectors = [".nav-dropdown", "#asset-ctx-menu"]) {
  selectors.forEach((sel) => {
    document.querySelectorAll(sel).forEach((m) => closeFloatingMenu(m, { resetPosition: sel.includes("nav") }));
  });
  document.querySelectorAll(".nav-trigger").forEach((t) => t.setAttribute("aria-expanded", "false"));
}
