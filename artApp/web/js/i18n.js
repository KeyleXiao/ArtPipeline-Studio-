/**
 * 轻量 i18n：locales/*.json + data-i18n DOM 绑定
 */
const STORAGE_KEY = "artApp.lang";
const DEFAULT_LANG = "zh-CN";
const SUPPORTED = ["zh-CN", "en-US"];

let currentLang = DEFAULT_LANG;
/** @type {Record<string, string>} */
let messages = {};
const listeners = new Set();

async function loadLocale(lang) {
  const res = await fetch(`/locales/${lang}.json`);
  if (!res.ok) throw new Error(`locale ${lang}`);
  messages = await res.json();
}

export function getLang() {
  return currentLang;
}

export function t(key, params = {}) {
  let s = messages[key] ?? key;
  for (const [k, v] of Object.entries(params)) {
    s = s.replaceAll(`{${k}}`, String(v));
  }
  return s;
}

export function applyDomI18n(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  root.querySelectorAll("[data-i18n-title]").forEach((el) => {
    el.title = t(el.dataset.i18nTitle);
  });
  root.querySelectorAll("[data-i18n-aria]").forEach((el) => {
    el.setAttribute("aria-label", t(el.dataset.i18nAria));
  });
  document.title = t("app.title");
}

export async function initI18n() {
  const saved = localStorage.getItem(STORAGE_KEY);
  currentLang = SUPPORTED.includes(saved) ? saved : DEFAULT_LANG;
  await loadLocale(currentLang);
  document.documentElement.lang = currentLang;
}

export async function setLang(lang) {
  if (!SUPPORTED.includes(lang) || lang === currentLang) return;
  currentLang = lang;
  localStorage.setItem(STORAGE_KEY, lang);
  document.documentElement.lang = lang;
  await loadLocale(lang);
  applyDomI18n();
  updateLangSwitcher();
  listeners.forEach((fn) => fn(lang));
}

export function onLangChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function updateLangSwitcher() {
  document.querySelectorAll("[data-lang]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.lang === currentLang);
  });
}

export function bindLangSwitcher() {
  document.querySelectorAll("[data-lang]").forEach((btn) => {
    btn.addEventListener("click", () => setLang(btn.dataset.lang));
  });
  updateLangSwitcher();
}
