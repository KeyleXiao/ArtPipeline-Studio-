import {
  initI18n,
  getLang,
  t,
  applyDomI18n,
  bindLangSwitcher,
  onLangChange,
} from "./i18n.js";
import { renderMarkdown, escapeHtml } from "./markdown.js";

const content = document.getElementById("docs-content");
const toc = document.getElementById("docs-toc");
const progress = document.getElementById("docs-progress");

let scrollSpyObserver = null;

function setPageTitle() {
  document.title = `${t("docs.title")} · KEYLE Studio`;
}

function showLoading() {
  if (!content) return;
  content.innerHTML = `<div class="docs-loading">
    <span class="docs-loading-spinner" aria-hidden="true"></span>
    <span>${escapeHtml(t("docs.loading"))}</span>
  </div>`;
}

function buildToc(root) {
  if (!toc) return;
  const headings = root.querySelectorAll("h2, h3");
  toc.innerHTML = "";
  if (!headings.length) {
    toc.innerHTML = `<li><p class="docs-toc-empty">${escapeHtml(t("docs.tocEmpty"))}</p></li>`;
    return;
  }
  for (const h of headings) {
    if (!h.id) continue;
    const li = document.createElement("li");
    if (h.tagName === "H3") li.className = "toc-h3";
    const a = document.createElement("a");
    a.href = `#${h.id}`;
    a.textContent = h.textContent || "";
    a.dataset.target = h.id;
    a.addEventListener("click", (e) => {
      e.preventDefault();
      h.scrollIntoView({ behavior: "smooth", block: "start" });
      history.replaceState(null, "", `#${h.id}`);
    });
    li.appendChild(a);
    toc.appendChild(li);
  }
}

function setupScrollSpy(root) {
  if (scrollSpyObserver) scrollSpyObserver.disconnect();
  const links = toc?.querySelectorAll("a[data-target]");
  if (!links?.length) return;

  scrollSpyObserver = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((e) => e.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
      if (!visible.length) return;
      const id = visible[0].target.id;
      links.forEach((link) => {
        link.classList.toggle("is-active", link.dataset.target === id);
      });
    },
    { rootMargin: "-20% 0px -65% 0px", threshold: [0, 0.25, 0.5, 1] },
  );

  root.querySelectorAll("h2, h3").forEach((h) => scrollSpyObserver.observe(h));
}

function setupReadingProgress() {
  if (!progress) return;
  const onScroll = () => {
    const doc = document.documentElement;
    const scrollTop = doc.scrollTop || document.body.scrollTop;
    const height = doc.scrollHeight - doc.clientHeight;
    progress.style.width = height > 0 ? `${(scrollTop / height) * 100}%` : "0%";
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
}

function enhanceCodeBlocks(root) {
  root.querySelectorAll("pre").forEach((pre) => {
    if (pre.querySelector(".md-copy-btn")) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "md-copy-btn";
    btn.textContent = t("docs.copyCode");
    btn.addEventListener("click", async () => {
      const code = pre.querySelector("code")?.textContent || "";
      try {
        await navigator.clipboard.writeText(code);
        btn.textContent = t("docs.copied");
        btn.classList.add("is-copied");
        setTimeout(() => {
          btn.textContent = t("docs.copyCode");
          btn.classList.remove("is-copied");
        }, 1600);
      } catch {
        btn.textContent = "Error";
      }
    });
    pre.appendChild(btn);
  });
}

function scrollToHash(root) {
  const hash = decodeURIComponent(location.hash.slice(1));
  if (!hash) return;
  const el = root.querySelector(`#${CSS.escape(hash)}`);
  if (el) {
    requestAnimationFrame(() => el.scrollIntoView({ behavior: "smooth", block: "start" }));
  }
}

async function loadDoc(lang = getLang()) {
  if (!content) return;
  showLoading();
  try {
    const res = await fetch(`/docs/${lang}.md`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    content.innerHTML = renderMarkdown(await res.text());
    buildToc(content);
    enhanceCodeBlocks(content);
    setupScrollSpy(content);
    scrollToHash(content);
  } catch (err) {
    content.innerHTML = `<p class="docs-error">${escapeHtml(t("docs.error"))}: ${escapeHtml(err.message)}</p>`;
    if (toc) toc.innerHTML = "";
  }
}

async function main() {
  await initI18n();
  applyDomI18n();
  setPageTitle();
  bindLangSwitcher();
  setupReadingProgress();
  onLangChange((lang) => {
    applyDomI18n();
    setPageTitle();
    loadDoc(lang);
  });
  await loadDoc();
}

main();
