/**
 * ArtPipeline Studio · Web 前端
 */
import { API } from "./api.js";
import {
  initI18n,
  t,
  applyDomI18n,
  bindLangSwitcher,
  onLangChange,
} from "./i18n.js";
import {
  bindRipple,
  closeAllFloatingMenus,
  closeFloatingMenu,
  hideGlobalOverlay,
  hideSplash,
  openFloatingMenu,
  setBtnBusy,
  setPanelLoading,
  showGlobalOverlay,
  withBtnBusy,
} from "./effects.js";

const state = {
  categories: [],
  categoryId: null,
  assets: [],
  assetId: null,
  assetFull: null,
  previewSource: "inbox",
  statusMap: {},
  statusScanning: false,
  searchTimer: null,
  checkpoints: [],
  logFilter: "全部",
  logEs: null,
  jobTimer: null,
  jobRunId: null,
  jobTrack: { active: false, sawBusy: false, postOk: false },
  paths: null,
  previewReq: 0,
  previewBlobUrl: null,
  previewInfo: null,
  previewInfoReq: 0,
  aiMode: "free",
  aiBusy: false,
};

const previewView = {
  zoom: 1,
  panX: 0,
  panY: 0,
  imgW: 0,
  imgH: 0,
  minZoom: 0.08,
  maxZoom: 12,
  panning: null,
};

let appBooted = false;

const AI_MODE_KEYS = ["free", "prompt", "refine", "workflow", "basic"];

function aiModeText(mode, field) {
  return t(`ai.${field}.${mode}`);
}

function pathChipTips(kind, chipState) {
  const key = kind === "unity" ? "engine" : kind;
  return t(`path.chip.${key}.${chipState}`);
}

function previewSourceLabel() {
  const key = currentPreviewSourceKey();
  if (key === "unity") return t("path.engine");
  return key;
}

function currentPreviewSourceKey() {
  const active = document.querySelector(".preview-side .seg-btn.active");
  const fromUi = active?.dataset?.source;
  if (fromUi) {
    state.previewSource = fromUi;
    return fromUi;
  }
  return state.previewSource || "inbox";
}

function refreshI18nUi() {
  renderCategories();
  renderAssets();
  fillCheckpointSelects();
  updateAiModeUi();
  refreshAiMessages();
  refreshComfy();
  if (state.assetId) {
    loadPreview();
    loadPreviewInfo(state.assetId);
  } else clearPreview();
  const pill = $("#job-pill");
  if (pill && !pill.dataset.busy) pill.textContent = t("job.ready");
  if (jobProg.visible) renderJobFloat();
  if (state.previewInfo) renderPreviewInfo(state.previewInfo);
}

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function toast(msg, { variant = "info" } = {}) {
  const pill = $("#job-pill");
  if (pill) {
    const prev = pill.dataset.prev || pill.textContent;
    pill.dataset.prev = prev;
    pill.textContent = msg;
    pill.classList.toggle("is-error", variant === "error");
    clearTimeout(pill._toastTimer);
    pill._toastTimer = setTimeout(() => {
      if (pill.dataset.prev) pill.textContent = pill.dataset.prev;
      pill.classList.remove("is-error");
    }, 3500);
  }
}

function setFormError(form, msg) {
  if (!form) return;
  const el = form.querySelector(".form-error") || $("#new-asset-error");
  if (!el) return;
  if (msg) {
    el.textContent = msg;
    el.hidden = false;
  } else {
    el.textContent = "";
    el.hidden = true;
  }
}

function selectedIds() {
  return state.assetId ? [state.assetId] : [];
}

function categoryAssetIds() {
  return state.assets.filter((a) => a.enabled !== false).map((a) => a.id);
}

async function enabledAssetIdsForCategory(catId) {
  if (catId === state.categoryId) return categoryAssetIds();
  const data = await API.get(`/api/assets?category=${encodeURIComponent(catId)}`);
  return (data.assets || []).filter((a) => a.enabled !== false).map((a) => a.id);
}

async function runGenerate(assetIds, { exportAfter = false, emptyToastKey = "toast.noCategoryAssets" } = {}) {
  if (!assetIds?.length) {
    toast(t(emptyToastKey));
    return;
  }
  if (!(await ensureComfyOnline())) return;
  prepareJobUi("generate", assetIds);
  try {
    const res = await API.post("/api/generate", { asset_ids: assetIds, export_after: exportAfter });
    state.jobRunId = res.run_id ?? null;
    state.jobTrack.postOk = true;
    startJobPoll();
  } catch (err) {
    resetJobTracking();
    clearJobUi();
    toast(err.message);
  }
}

async function runExport(assetIds, { emptyToastKey = "toast.noCategoryAssets" } = {}) {
  if (!assetIds?.length) {
    toast(t(emptyToastKey));
    return;
  }
  prepareJobUi("export", assetIds);
  try {
    const res = await API.post("/api/export", { asset_ids: assetIds });
    state.jobRunId = res.run_id ?? null;
    state.jobTrack.postOk = true;
    startJobPoll();
  } catch (err) {
    resetJobTracking();
    clearJobUi();
    toast(err.message);
  }
}

// ── 渲染 ─────────────────────────────────────────────

function renderCategories() {
  const ul = $("#cat-list");
  if (!ul) return;
  ul.innerHTML = "";
  for (const cat of state.categories) {
    const li = document.createElement("li");
    li.className = "cat-item" + (cat.id === state.categoryId ? " active" : "");
    li.dataset.catId = cat.id;
    li.innerHTML = `
      <div class="label">${esc(cat.label)}</div>
      <div class="sub">${esc(cat.id)} · ${esc(cat.checkpoint_short)}</div>`;
    li.addEventListener("click", () => selectCategory(cat.id));
    ul.appendChild(li);
  }
}

const PATH_KINDS = [
  { key: "source", label: "S", title: "source" },
  { key: "inbox", label: "in", title: "inbox" },
  { key: "unity", label: "U", title: "engine" },
];

function pathChipClass(st) {
  if (st === "ok") return "ok";
  if (st === "none") return "none";
  if (st === "modified") return "warn";
  return "bad";
}

function pathChipHtml(assetId, kind, label, st, scanning) {
  let chipState = "pending";
  if (!scanning && st?.state) chipState = st.state;
  const tipKey = kind === "unity" ? "engine" : kind;
  const tip =
    (pathChipTips(tipKey, chipState) || pathChipTips(tipKey, "pending")) +
    (st?.file ? `\n${st.file}` : "");
  const cls = scanning ? "pending" : pathChipClass(chipState);
  return `<button type="button" class="path-chip ${cls}" data-path-kind="${kind}" data-asset-id="${esc(assetId)}" title="${esc(tip)}">${label}</button>`;
}

function renderAssets() {
  const box = $("#asset-list");
  const countEl = $("#asset-count");
  if (!box) return;
  if (!state.categoryId) {
    box.innerHTML = `<p class="hint">${esc(t("asset.selectCategory"))}</p>`;
    if (countEl) countEl.textContent = "";
    return;
  }
  if (countEl) {
    countEl.textContent = state.statusScanning
      ? t("asset.countScanning", { n: state.assets.length })
      : t("asset.count", { n: state.assets.length });
  }
  const frag = document.createDocumentFragment();
  for (const asset of state.assets) {
    const row = document.createElement("div");
    row.className = "asset-row" + (asset.id === state.assetId ? " active" : "");
    row.dataset.id = asset.id;
    const st = state.statusMap[asset.id];
    const chips = PATH_KINDS.map(({ key, label }) =>
      pathChipHtml(asset.id, key, label, st?.[key], state.statusScanning),
    ).join("");
    row.innerHTML = `
      <span class="name" title="${esc(asset.filename)}">${esc(asset.filename)}</span>
      <span class="size">${esc(asset.size_label)}</span>
      <span class="path-chips" aria-label="${esc(t("asset.chipsAria"))}">${chips}</span>`;
    row.addEventListener("click", (ev) => {
      if (assetDrag.suppressClick) {
        assetDrag.suppressClick = false;
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
      selectAsset(asset.id);
    });
    frag.appendChild(row);
  }
  box.innerHTML = "";
  box.appendChild(frag);
}

function fillCheckpointSelects() {
  const fill = (sel, emptyLabel) => {
    if (!sel) return;
    const cur = sel.value;
    sel.innerHTML = `<option value="">${esc(emptyLabel)}</option>`;
    for (const ck of state.checkpoints) {
      const o = document.createElement("option");
      o.value = ck;
      o.textContent = ck.split("/").pop();
      sel.appendChild(o);
    }
    if (cur) sel.value = cur;
  };
  fill($("#asset-ckpt"), t("form.checkpointInherit"));
  fill($("#cat-ckpt"), t("form.checkpointUnset"));
}

async function fillNewCatCheckpointSelect() {
  await loadCheckpoints();
  const sel = $("#new-cat-ckpt");
  if (!sel) return;
  sel.innerHTML = "";
  sel.required = false;
  let preferred = "";
  try {
    const settings = await API.get("/api/settings");
    preferred = settings.checkpoint || "";
  } catch {
    /* ignore */
  }
  const defaultOpt = document.createElement("option");
  defaultOpt.value = "";
  defaultOpt.textContent = t("form.checkpointUnset");
  sel.appendChild(defaultOpt);
  if (!state.checkpoints.length) {
    if (preferred) {
      const hint = document.createElement("option");
      hint.value = preferred;
      hint.textContent = `${preferred.split("/").pop()} (${t("dlg.checkpointOfflineHint")})`;
      sel.appendChild(hint);
      sel.value = preferred;
    }
    return;
  }
  for (const ck of state.checkpoints) {
    const o = document.createElement("option");
    o.value = ck;
    o.textContent = ck.split("/").pop();
    sel.appendChild(o);
  }
  if (preferred && state.checkpoints.includes(preferred)) {
    sel.value = preferred;
  }
}

function categoryHasAssets() {
  return state.assets.length > 0;
}

function updateMainTabsVisibility() {
  const hasAssets = categoryHasAssets();
  $$("#main-tabs .tab").forEach((tab) => {
    const needsAsset = tab.hasAttribute("data-requires-asset");
    tab.hidden = needsAsset && !hasAssets;
  });
  const active = $("#main-tabs .tab.active");
  const activeId = active?.dataset.tab;
  if (activeId && !hasAssets && active?.hidden) {
    switchTab("category");
  }
}

function fillCategorySelect() {
  const sel = $("#asset-category-select");
  if (!sel) return;
  sel.innerHTML = "";
  for (const c of state.categories) {
    const o = document.createElement("option");
    o.value = c.id;
    o.textContent = c.label;
    sel.appendChild(o);
  }
}

async function loadBasicForm() {
  if (!state.assetId) return;
  const data = state.assetFull || (await API.get(`/api/assets/${state.assetId}`));
  state.assetFull = data;
  const form = $("#form-basic");
  if (!form) return;
  form.id.value = data.id;
  form.filename.value = data.filename;
  form.category.value = data.category;
  form.width.value = data.width;
  form.height.value = data.height;
  form.seed.value = data.seed || "";
  form.subject.value = data.subject || "";
  form.enabled.checked = data.enabled !== false;
  const mode = data.remove_bg_mode || "inherit";
  form.querySelectorAll('input[name="remove_bg_mode"]').forEach((r) => {
    r.checked = r.value === mode;
  });
  if ($("#asset-ckpt")) $("#asset-ckpt").value = data.checkpoint || "";
}

async function loadCategoryForm() {
  if (!state.categoryId) return;
  const data = await API.get(`/api/categories/${state.categoryId}`);
  const form = $("#form-category");
  if (!form) return;
  form.source.value = data.source || "";
  form.inbox.value = data.inbox || "";
  form.unity.value = data.unity || "";
  form.alpha_matte.checked = !!data.alpha_matte && data.alpha_matte !== "none";
  form.positive_common.value = data.positive_common || "";
  form.negative_common.value = data.negative_common || "";
  if ($("#cat-ckpt")) $("#cat-ckpt").value = data.checkpoint || "";
}

async function loadPromptTab() {
  if (!state.assetId) return;
  const data = state.assetFull || (await API.get(`/api/assets/${state.assetId}`));
  state.assetFull = data;
  const split = $("#sdxl-split");
  const useSplit = ["items", "skills"].includes(data.category);
  split?.classList.toggle("hidden", !useSplit);
  $("#positive-g-text").value = data.positive_g || "";
  $("#positive-l-text").value = data.positive_l || "";
  $("#negative-text").value = data.negative || "";
  if (useSplit && data.positive_g && data.positive_l) {
    $("#positive-text").value =
      `=== SDXL-G 边框构图 ===\n${data.positive_g}\n\n=== SDXL-L 物件主体 ===\n${data.positive_l}`;
  } else {
    $("#positive-text").value = data.positive || "";
  }
  let genMode = data.gen_mode || "txt2img";
  if (genMode === "img2img" && data.ref_image_use_source) genMode = "redraw";
  $$('input[name="gen_mode"]').forEach((r) => {
    r.checked = r.value === genMode;
  });
  $("#ref-image-path").value = data.ref_image || "";
  const denoise = data.img2img_denoise ?? 0.65;
  $("#img2img-denoise").value = denoise;
  $("#img2img-denoise-range").value = denoise;
  updateGenModeUi();
  try {
    const wf = await API.get(`/api/assets/${state.assetId}/workflow`);
    $("#workflow-text").value = wf.text || "";
  } catch {
    $("#workflow-text").value = "";
  }
}

function currentGenMode() {
  return document.querySelector('input[name="gen_mode"]:checked')?.value || "txt2img";
}

function isImg2imgFamily(mode = currentGenMode()) {
  return mode === "img2img" || mode === "redraw";
}

function refImageSourcePath() {
  return state.paths?.source || state.assetFull?.source_path || "";
}

function updateGenModeUi() {
  const mode = currentGenMode();
  const panel = $("#img2img-panel");
  const refSection = $("#ref-image-section");
  const redrawSection = $("#redraw-source-section");
  const hint = $("#gen-ref-hint");
  panel?.classList.toggle("hidden", !isImg2imgFamily(mode));
  refSection?.classList.toggle("hidden", mode !== "img2img");
  redrawSection?.classList.toggle("hidden", mode !== "redraw");
  if (mode === "redraw") {
    const pathEl = $("#redraw-source-path");
    const src = refImageSourcePath();
    if (pathEl) {
      pathEl.textContent = src || t("preview.infoFileMissing");
      pathEl.classList.toggle("is-missing", !src);
    }
  }
  if (hint) {
    const key = mode === "redraw" ? "form.redrawHint" : "form.img2imgHint";
    hint.dataset.i18n = key;
    hint.textContent = t(key);
  }
}

function syncDenoiseFromRange() {
  const range = $("#img2img-denoise-range");
  const num = $("#img2img-denoise");
  if (range && num) num.value = range.value;
}

function syncDenoiseFromNumber() {
  const range = $("#img2img-denoise-range");
  const num = $("#img2img-denoise");
  if (!range || !num) return;
  let v = parseFloat(num.value);
  if (Number.isNaN(v)) v = 0.65;
  v = Math.max(0.01, Math.min(1, v));
  num.value = v;
  range.value = v;
}

async function pickRefImageFile() {
  try {
    const r = await API.post("/api/pick-image-file", {});
    if (r.cancelled) return null;
    return r.path || r.absolute || null;
  } catch (err) {
    toast(err.message);
    return null;
  }
}

async function pickRefImage(btn) {
  await withBtnBusy(btn || document.querySelector('[data-action="pick-ref-image"]'), async () => {
    const path = await pickRefImageFile();
    if (!path) return;
    $$('input[name="gen_mode"]').forEach((r) => {
      if (r.value === "img2img") r.checked = true;
    });
    updateGenModeUi();
    $("#ref-image-path").value = path;
  }).catch((err) => {
    if (err) toast(err.message);
  });
}

async function loadSettingsForm() {
  const data = await API.get("/api/settings");
  const form = $("#form-settings");
  if (!form) return;
  for (const k of [
    "project_root",
    "art_pipeline_root",
    "log_dir",
    "comfyui_url",
    "steps",
    "cfg",
    "sampler",
    "scheduler",
    "seed",
    "deepseek_api_key",
    "deepseek_model",
  ]) {
    if (form[k] !== undefined) form[k].value = data[k] ?? "";
  }
  updateLogDirHint(data);
}

function updateLogDirHint(data) {
  const hint = $("#log-dir-hint");
  if (!hint) return;
  const effective = data?.log_dir_effective || data?.log_dir_default || "";
  hint.textContent = t("form.logDirHint", { path: effective, file: data?.log_file || "" });
}

function formSettingsLogDir() {
  const form = $("#form-settings");
  return form?.log_dir?.value?.trim() || "";
}

function aiHistoryUrl(mode = state.aiMode) {
  return `/api/ai/history/${encodeURIComponent(state.assetId)}?mode=${encodeURIComponent(mode)}`;
}

function updateAiModeUi() {
  const mode = state.aiMode;
  $$(".ai-mode-tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.aiMode === mode));
  const hint = $("#ai-mode-hint");
  if (hint) hint.textContent = aiModeText(mode, "hint");
  const input = $("#ai-input");
  if (input && !state.aiBusy) input.placeholder = aiModeText(mode, "placeholder");
}

function renderAiChat(history = []) {
  const box = $("#ai-history");
  if (!box) return;
  if (!state.assetId) {
    box.innerHTML = `<div class="ai-empty"><p>${esc(t("ai.selectAssetFirst"))}</p></div>`;
    return;
  }
  if (!history.length) {
    box.innerHTML = `<div class="ai-empty"><p>${esc(aiModeText(state.aiMode, "empty"))}</p></div>`;
    return;
  }
  box.innerHTML = history
    .map((item) => {
      const role = item.role === "user" ? "user" : "assistant";
      const label = role === "user" ? t("ai.roleUser") : t("ai.roleAssistant");
      return `<article class="ai-msg ${role}">
        <div class="ai-msg-head"><span class="ai-msg-role">${esc(label)}</span></div>
        <div class="ai-msg-body">${esc(item.content || "")}</div>
      </article>`;
    })
    .join("");
  box.scrollTop = box.scrollHeight;
}

function setAiBusy(busy) {
  state.aiBusy = busy;
  const btn = $("#ai-send-btn");
  const input = $("#ai-input");
  if (btn) {
    setBtnBusy(btn, busy);
    btn.textContent = busy ? t("ai.thinking") : t("ai.send");
  }
  if (input) input.disabled = busy;
  const box = $("#ai-history");
  if (busy && box && state.assetId) {
    const typing = box.querySelector(".ai-typing");
    if (!typing) {
      box.insertAdjacentHTML(
        "beforeend",
        `<div class="ai-typing muted sm"><span class="ai-typing-dots" aria-hidden="true"><span></span><span></span><span></span></span>${esc(t("ai.typing"))}</div>`,
      );
      box.scrollTop = box.scrollHeight;
    }
  } else {
    box?.querySelector(".ai-typing")?.remove();
  }
}

async function clearAiChat(mode = state.aiMode) {
  if (state.assetId) {
    try {
      await API.del(aiHistoryUrl(mode));
    } catch {
      /* ignore */
    }
  }
  if (mode === state.aiMode) renderAiChat([]);
}

async function refreshAiMessages() {
  if (!state.assetId) {
    renderAiChat([]);
    return;
  }
  try {
    const data = await API.get(aiHistoryUrl());
    renderAiChat(data.history || []);
  } catch {
    renderAiChat([]);
  }
}

async function openAiPanel() {
  updateAiModeUi();
  await clearAiChat(state.aiMode);
}

async function switchAiMode(mode) {
  if (!AI_MODE_KEYS.includes(mode) || state.aiMode === mode) return;
  state.aiMode = mode;
  updateAiModeUi();
  await clearAiChat(mode);
}

function switchTab(tabId) {
  const tabBtn = $(`#main-tabs .tab[data-tab="${tabId}"]`);
  if (tabBtn?.hidden) {
    tabId = categoryHasAssets() ? "ai" : "category";
  }
  $$("#main-tabs .tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tabId));
  $$(".tab-body").forEach((b) => b.classList.add("hidden"));
  const body = $(`#tab-${tabId}`);
  if (body) body.classList.remove("hidden");
  if (tabId === "category") loadCategoryForm();
  if (tabId === "prompt") loadPromptTab();
  if (tabId === "settings") loadSettingsForm();
  if (tabId === "ai") openAiPanel();
}

function revokePreviewBlob() {
  if (state.previewBlobUrl) {
    URL.revokeObjectURL(state.previewBlobUrl);
    state.previewBlobUrl = null;
  }
}

function previewMaxSize() {
  const stage = $("#preview-stage");
  if (!stage) return 480;
  const dpr = window.devicePixelRatio || 1;
  const base = Math.max(stage.clientWidth, stage.clientHeight, 160);
  return Math.min(512, Math.max(128, Math.ceil(base * dpr)));
}

function resetPreviewView() {
  previewView.zoom = 1;
  previewView.panX = 0;
  previewView.panY = 0;
  previewView.imgW = 0;
  previewView.imgH = 0;
  previewView.panning = null;
  $("#preview-viewport")?.classList.remove("is-grabbing");
}

function previewViewportSize() {
  const vp = $("#preview-viewport");
  const stage = $("#preview-stage");
  const rect = vp?.getBoundingClientRect();
  const w = rect?.width || stage?.clientWidth || 320;
  const h = rect?.height || stage?.clientHeight || 320;
  return { w: Math.max(w, 1), h: Math.max(h, 1) };
}

function previewViewportOffset() {
  const { w: vpW, h: vpH } = previewViewportSize();
  if (!previewView.imgW) return { ox: 0, oy: 0, docW: 0, docH: 0 };
  const docW = previewView.imgW * previewView.zoom;
  const docH = previewView.imgH * previewView.zoom;
  return {
    ox: (vpW - docW) / 2 + previewView.panX,
    oy: (vpH - docH) / 2 + previewView.panY,
    docW,
    docH,
  };
}

function layoutPreviewImage() {
  const img = $("#preview-img");
  if (!img || img.hidden || !previewView.imgW) return;
  const { ox, oy, docW, docH } = previewViewportOffset();
  img.style.width = `${docW}px`;
  img.style.height = `${docH}px`;
  img.style.left = `${ox}px`;
  img.style.top = `${oy}px`;
  const badge = $("#preview-zoom-label");
  if (badge) badge.textContent = `${Math.round(previewView.zoom * 100)}%`;
}

function previewZoom100() {
  previewView.zoom = 1;
  previewView.panX = 0;
  previewView.panY = 0;
  layoutPreviewImage();
}

function previewZoomFit() {
  const { w: vpW, h: vpH } = previewViewportSize();
  if (!previewView.imgW) return;
  const zx = vpW / previewView.imgW;
  const zy = vpH / previewView.imgH;
  previewView.zoom = Math.max(
    previewView.minZoom,
    Math.min(previewView.maxZoom, Math.min(zx, zy) * 0.94),
  );
  previewView.panX = 0;
  previewView.panY = 0;
  layoutPreviewImage();
}

function previewZoomBy(factor, clientX, clientY) {
  const vp = $("#preview-viewport");
  if (!vp || !previewView.imgW) return;
  const rect = vp.getBoundingClientRect();
  const cx = clientX != null ? clientX - rect.left : rect.width / 2;
  const cy = clientY != null ? clientY - rect.top : rect.height / 2;
  const { ox, oy } = previewViewportOffset();
  const imgX = (cx - ox) / previewView.zoom;
  const imgY = (cy - oy) / previewView.zoom;
  const nextZoom = Math.max(
    previewView.minZoom,
    Math.min(previewView.maxZoom, previewView.zoom * factor),
  );
  previewView.zoom = nextZoom;
  const { w: vpW, h: vpH } = previewViewportSize();
  previewView.panX = cx - imgX * nextZoom - (vpW - previewView.imgW * nextZoom) / 2;
  previewView.panY = cy - imgY * nextZoom - (vpH - previewView.imgH * nextZoom) / 2;
  layoutPreviewImage();
}

function hidePreviewLoadingUi() {
  const ph = $("#preview-ph");
  const loading = $("#preview-loading");
  const stage = $("#preview-stage");
  if (ph) ph.hidden = true;
  if (loading) {
    loading.hidden = true;
    loading.setAttribute("aria-hidden", "true");
  }
  stage?.classList.remove("is-loading");
}

async function applyPreviewBlob(reqId, asset, blob) {
  const img = $("#preview-img");
  const stage = $("#preview-stage");
  const badge = $("#preview-zoom-label");
  if (!img || reqId !== state.previewReq) return;

  revokePreviewBlob();
  resetPreviewView();
  state.previewBlobUrl = URL.createObjectURL(blob);
  img.src = state.previewBlobUrl;

  try {
    if (typeof img.decode === "function") {
      await img.decode();
    } else {
      await new Promise((resolve, reject) => {
        if (img.complete) resolve();
        else {
          img.onload = () => resolve();
          img.onerror = () => reject(new Error("image load failed"));
        }
      });
    }
  } catch {
    if (reqId !== state.previewReq) return;
    showPreviewEmpty(asset);
    return;
  }

  if (reqId !== state.previewReq) return;

  previewView.imgW = img.naturalWidth || 1;
  previewView.imgH = img.naturalHeight || 1;
  previewView.zoom = 1;
  previewView.panX = 0;
  previewView.panY = 0;

  img.hidden = false;
  hidePreviewLoadingUi();
  layoutPreviewImage();
  if (badge) badge.hidden = false;
  stage?.classList.add("has-image");
}

function bindPreviewViewport() {
  const vp = $("#preview-viewport");
  if (!vp || vp.dataset.bound) return;
  vp.dataset.bound = "1";

  vp.addEventListener(
    "wheel",
    (e) => {
      if ($("#preview-img")?.hidden) return;
      e.preventDefault();
      previewZoomBy(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX, e.clientY);
    },
    { passive: false },
  );

  vp.addEventListener("mousedown", (e) => {
    if ($("#preview-img")?.hidden || e.button !== 0) return;
    e.preventDefault();
    previewView.panning = {
      x: e.clientX,
      y: e.clientY,
      panX: previewView.panX,
      panY: previewView.panY,
    };
    vp.classList.add("is-grabbing");
  });

  window.addEventListener("mousemove", (e) => {
    if (!previewView.panning) return;
    previewView.panX = previewView.panning.panX + (e.clientX - previewView.panning.x);
    previewView.panY = previewView.panning.panY + (e.clientY - previewView.panning.y);
    layoutPreviewImage();
  });

  window.addEventListener("mouseup", () => {
    if (!previewView.panning) return;
    previewView.panning = null;
    vp.classList.remove("is-grabbing");
  });

  vp.addEventListener("dblclick", (e) => {
    if ($("#preview-img")?.hidden) return;
    e.preventDefault();
    previewZoomFit();
  });

  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(() => layoutPreviewImage()).observe(vp);
  }
}

function formatBytes(n) {
  if (!n || n <= 0) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDateTime(epochOrIso) {
  if (epochOrIso == null || epochOrIso === "") return "—";
  const d =
    typeof epochOrIso === "number"
      ? new Date(epochOrIso * 1000)
      : new Date(epochOrIso);
  if (Number.isNaN(d.getTime())) return "—";
  const lang = document.documentElement.lang || "zh-CN";
  return d.toLocaleString(lang, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatActivityTime(entry) {
  if (entry?.ts_epoch) return formatDateTime(entry.ts_epoch);
  return entry?.ts || "—";
}

function fileInfoLine(info) {
  if (!info?.exists) return t("preview.infoFileMissing");
  const date = formatDateTime(info.mtime);
  const size = formatBytes(info.size);
  return size
    ? t("preview.infoFileLine", { date, size })
    : t("preview.infoFileLineNoSize", { date });
}

function dlRow(label, value, { active = false, muted = false } = {}) {
  const cls = ["preview-dl-row", active && "is-active", muted && "is-muted"]
    .filter(Boolean)
    .join(" ");
  return `<div class="${cls}"><dt>${esc(label)}</dt><dd class="${muted ? "muted" : ""}">${esc(value)}</dd></div>`;
}

function clearPreviewInfo() {
  state.previewInfo = null;
  $("#preview-info-name").textContent = "—";
  $("#preview-info-sub").textContent = "—";
  $("#preview-dl-files").innerHTML = "";
  $("#preview-dl-config").innerHTML = "";
  $("#preview-activity").innerHTML = "";
}

function renderPreviewInfo(info) {
  if (!info) {
    clearPreviewInfo();
    return;
  }
  const sourceKey = currentPreviewSourceKey();
  const sourceLabel = previewSourceLabel();
  const nameEl = $("#preview-info-name");
  const subEl = $("#preview-info-sub");
  const filesEl = $("#preview-dl-files");
  const configEl = $("#preview-dl-config");
  const activityEl = $("#preview-activity");

  if (nameEl) nameEl.textContent = info.filename || "—";
  if (subEl) {
    const parts = [info.size_label, sourceLabel];
    if (info.subject) parts.push(info.subject);
    subEl.textContent = parts.filter(Boolean).join(" · ");
  }

  const fileLabels = {
    source: t("preview.infoFileSource"),
    inbox: t("preview.infoFileInbox"),
    unity: t("preview.infoFileEngine"),
  };
  if (filesEl) {
    filesEl.innerHTML = ["source", "inbox", "unity"]
      .map((key) => {
        const slot = info.files?.[key];
        return dlRow(fileLabels[key], fileInfoLine(slot), {
          active: sourceKey === key,
          muted: !slot?.exists,
        });
      })
      .join("");
  }

  if (configEl) {
    const rows = [
      dlRow(t("preview.infoWorkflow"), fileInfoLine(info.workflow), {
        muted: !info.workflow?.exists,
      }),
      dlRow(t("preview.infoPipelineConfig"), fileInfoLine(info.config_file), {
        muted: !info.config_file?.exists,
      }),
      dlRow(
        t("preview.infoPostprocess"),
        info.has_postprocess
          ? t("preview.infoPostprocessCustom")
          : t("preview.infoPostprocessDefault")
      ),
    ];
    if (info.seed) rows.push(dlRow(t("form.seed"), info.seed));
    configEl.innerHTML = rows.join("");
  }

  if (activityEl) {
    const items = info.activity || [];
    if (!items.length) {
      activityEl.innerHTML = `<li class="empty">${esc(t("preview.infoNoActivity"))}</li>`;
    } else {
      activityEl.innerHTML = items
        .map(
          (entry) =>
            `<li><time>${esc(formatActivityTime(entry))}</time><span>${esc(entry.msg || "")}</span></li>`
        )
        .join("");
    }
  }
}

async function loadPreviewInfo(assetId) {
  if (!assetId) {
    clearPreviewInfo();
    return;
  }
  const panel = $("#preview-info");
  const reqId = ++state.previewInfoReq;
  setPanelLoading(panel, true);
  try {
    const info = await API.get(`/api/assets/${encodeURIComponent(assetId)}/info`);
    if (reqId !== state.previewInfoReq || state.assetId !== assetId) return;
    state.previewInfo = info;
    renderPreviewInfo(info);
  } catch {
    if (reqId !== state.previewInfoReq || state.assetId !== assetId) return;
    const asset = state.assets.find((a) => a.id === assetId);
    if (asset) {
      renderPreviewInfo({
        filename: asset.filename,
        size_label: asset.size_label,
        subject: asset.subject || "",
        files: {},
        activity: [],
      });
    }
  } finally {
    if (reqId === state.previewInfoReq) setPanelLoading(panel, false);
  }
}

function showPreviewEmpty(asset, message = null) {
  const img = $("#preview-img");
  const ph = $("#preview-ph");
  const loading = $("#preview-loading");
  const badge = $("#preview-zoom-label");
  img.hidden = true;
  revokePreviewBlob();
  img.removeAttribute("src");
  img.style.width = "";
  img.style.height = "";
  img.style.left = "";
  img.style.top = "";
  resetPreviewView();
  if (badge) badge.hidden = true;
  $("#preview-stage")?.classList.remove("has-image");
  if (ph) {
    ph.hidden = false;
    ph.textContent = message ?? t("preview.noFile");
  }
  if (loading) loading.hidden = true;
  $("#preview-stage")?.classList.remove("is-loading");
  if (asset) loadPreviewInfo(asset.id);
}

function clearPreview() {
  clearPreviewInfo();
  revokePreviewBlob();
  const img = $("#preview-img");
  const badge = $("#preview-zoom-label");
  img.hidden = true;
  img.removeAttribute("src");
  img.style.width = "";
  img.style.height = "";
  img.style.left = "";
  img.style.top = "";
  resetPreviewView();
  if (badge) badge.hidden = true;
  $("#preview-stage")?.classList.remove("has-image", "is-loading");
  $("#preview-loading").hidden = true;
  const ph = $("#preview-ph");
  if (ph) {
    ph.hidden = false;
    ph.textContent = t("preview.selectAsset");
  }
}

async function loadPreview() {
  const asset = state.assets.find((a) => a.id === state.assetId);
  if (!asset) {
    clearPreview();
    return;
  }
  const stage = $("#preview-stage");
  const img = $("#preview-img");
  const ph = $("#preview-ph");
  const loading = $("#preview-loading");
  const hasCurrentImage = !!state.previewBlobUrl && !img.hidden;
  const reqId = ++state.previewReq;

  stage?.classList.add("is-loading");
  if (loading) {
    loading.hidden = false;
    loading.removeAttribute("aria-hidden");
  }
  if (hasCurrentImage) {
    if (ph) ph.hidden = true;
  } else {
    img.hidden = true;
    revokePreviewBlob();
    img.removeAttribute("src");
    if (ph) ph.hidden = true;
  }
  loadPreviewInfo(asset.id);

  const params = new URLSearchParams({
    source: currentPreviewSourceKey(),
    max: String(previewMaxSize()),
  });
  const url = `/api/assets/${encodeURIComponent(asset.id)}/preview.png?${params}&_=${Date.now()}`;

  try {
    const res = await fetch(url);
    if (reqId !== state.previewReq) return;

    if (!res.ok) {
      showPreviewEmpty(asset);
      return;
    }
    const blob = await res.blob();
    if (reqId !== state.previewReq) return;
    if (blob.size < 8) {
      showPreviewEmpty(asset);
      return;
    }
    const isImage =
      !blob.type || blob.type.startsWith("image/") || blob.type === "application/octet-stream";
    if (!isImage) {
      showPreviewEmpty(asset);
      return;
    }

    await applyPreviewBlob(reqId, asset, blob);
  } catch {
    if (reqId !== state.previewReq) return;
    showPreviewEmpty(asset);
  }
}

async function loadPaths() {
  if (!state.assetId) {
    state.paths = null;
    return;
  }
  state.paths = await API.get(`/api/assets/${state.assetId}/paths`);
  if (currentGenMode() === "redraw") updateGenModeUi();
}

// ── 数据加载 ─────────────────────────────────────────────

async function loadAssetList() {
  if (!state.categoryId) return;
  const panel = $("#panel-assets");
  setPanelLoading(panel, true);
  try {
    const q = $("#asset-search")?.value.trim() || "";
    const data = await API.get(
      `/api/assets?category=${encodeURIComponent(state.categoryId)}&q=${encodeURIComponent(q)}`,
    );
    state.assets = data.assets || [];
    renderAssets();
    updateMainTabsVisibility();
    scanStatus();
  } catch (err) {
    toast(t("toast.listFailed", { msg: err.message }));
  } finally {
    setPanelLoading(panel, false);
  }
}

async function selectCategory(catId) {
  const changed = state.categoryId !== catId;
  state.categoryId = catId;
  if (changed) {
    state.assetId = null;
    state.assetFull = null;
    state.statusMap = {};
    clearPreview();
  }
  renderCategories();
  await loadAssetList();
  await loadCategoryForm();
  updateMainTabsVisibility();
  if (state.assets.length > 0 && (changed || !state.assetId)) {
    await selectAsset(state.assets[0].id);
  } else if (state.assets.length === 0) {
    clearPreview();
    const active = $("#main-tabs .tab.active");
    if (active?.hasAttribute("data-requires-asset")) switchTab("category");
  }
}

async function selectAsset(assetId) {
  state.assetId = assetId;
  state.assetFull = null;
  renderAssets();
  await loadPaths();
  await loadBasicForm();
  await loadPreview();
  const activeTab = $("#main-tabs .tab.active")?.dataset.tab;
  if (activeTab === "prompt") await loadPromptTab();
  if (activeTab === "ai") await openAiPanel();
}

async function scanStatus() {
  if (!state.assets.length) {
    state.statusMap = {};
    state.statusScanning = false;
    renderAssets();
    return;
  }
  state.statusScanning = true;
  renderAssets();
  try {
    const data = await API.post("/api/assets/status", { ids: state.assets.map((a) => a.id) });
    state.statusMap = data.status || {};
  } catch (err) {
    toast(t("toast.scanFailed", { msg: err.message }));
  } finally {
    state.statusScanning = false;
    renderAssets();
  }
}

async function openAssetPathDir(assetId, kind) {
  const st = state.statusMap[assetId]?.[kind];
  if (st?.dir) {
    await openPath(st.dir);
    return;
  }
  try {
    const paths = await API.get(`/api/assets/${assetId}/paths`);
    const file = paths[kind];
    if (!file) {
      toast(t("toast.noPath"));
      return;
    }
    const dir = file.replace(/[/\\][^/\\]+$/, "");
    await openPath(dir || file);
  } catch (err) {
    toast(err.message);
  }
}

async function loadCheckpoints() {
  try {
    const data = await API.get("/api/comfyui/checkpoints");
    state.checkpoints = data.checkpoints || [];
    fillCheckpointSelects();
  } catch {
    state.checkpoints = [];
  }
}

// ── 任务 / ComfyUI ─────────────────────────────────────────────

const JOB_FLOAT_POS_KEY = "artApp.jobFloatPos";
const JOB_FLOAT_DRAG_THRESHOLD = 4;

const jobProg = {
  batchIdx: 0,
  batchTotal: 1,
  stepPct: 0,
  filename: "",
  message: "",
  lastApiKind: "",
  phase: "",
  cancelling: false,
  visible: false,
};

function resetJobProg(kind = "") {
  jobProg.batchIdx = 0;
  jobProg.batchTotal = 1;
  jobProg.stepPct = 0;
  jobProg.filename = "";
  jobProg.message = "";
  jobProg.phase = "";
  jobProg.lastApiKind = kind;
  jobProg.cancelling = false;
}

function resetJobTracking() {
  state.jobRunId = null;
  state.jobTrack = { active: false, sawBusy: false, postOk: false };
}

function stopJobPoll() {
  if (state.jobTimer) {
    clearInterval(state.jobTimer);
    state.jobTimer = null;
  }
}

function prepareJobUi(kind, assetIds) {
  stopJobPoll();
  resetJobTracking();
  state.jobTrack.active = true;
  resetJobProg(kind);
  jobProg.batchTotal = Math.max(assetIds.length, 1);
  jobProg.batchIdx = 1;
  jobProg.message = t("job.preparing");
  const first = state.assets.find((a) => a.id === assetIds[0]);
  jobProg.filename = first?.filename || "…";
  showJobFloat();
  const pill = $("#job-pill");
  if (pill) {
    pill.textContent = kind === "export" ? t("job.exporting") : t("job.busy");
    pill.classList.add("busy");
    pill.dataset.busy = "1";
  }
}

function clearJobUi() {
  stopJobPoll();
  resetJobTracking();
  hideJobFloat();
  const pill = $("#job-pill");
  if (pill) {
    pill.textContent = t("job.ready");
    pill.classList.remove("busy");
    delete pill.dataset.busy;
  }
  jobProg.cancelling = false;
}

function finishJobUi({ quickFail = false } = {}) {
  const wasGenerate = jobProg.lastApiKind === "generate";
  stopJobPoll();
  resetJobTracking();
  hideJobFloat();
  const pill = $("#job-pill");
  if (pill) {
    pill.textContent = t("job.ready");
    pill.classList.remove("busy");
    delete pill.dataset.busy;
  }
  jobProg.cancelling = false;
  void notifyJobFinish({ quickFail, wasGenerate });
}

async function notifyJobFinish({ quickFail, wasGenerate }) {
  if (!wasGenerate && !quickFail) return;
  try {
    const data = await API.get("/api/logs?tab=生成&limit=40");
    const entries = data.entries || [];
    const failLine = [...entries].reverse().find((e) => {
      const m = logEntryText(e);
      return (
        /^FAIL\b/i.test(m) ||
        m.includes("未配置") ||
        m.includes("没有可生成") ||
        m.includes("不存在") ||
        m.includes("ComfyUI")
      );
    });
    if (failLine) {
      toast(logEntryText(failLine), { variant: "error" });
      return;
    }
  } catch {
    /* ignore */
  }
  if (quickFail) {
    toast(t("toast.jobEndedCheckLogs"), { variant: "error" });
  }
}

function ingestJobProgress(p) {
  if (!p?.kind) return;
  const kind = p.kind;
  jobProg.phase = kind;
  if (p.index != null) {
    jobProg.batchIdx = parseInt(p.index, 10) || jobProg.batchIdx || 1;
  }
  if (p.total != null) {
    jobProg.batchTotal = Math.max(parseInt(p.total, 10) || 1, 1);
  }
  if (p.filename) jobProg.filename = p.filename;
  if (kind === "batch") {
    jobProg.stepPct = 0;
  } else if (kind === "progress") {
    const val = parseInt(p.value, 10) || 0;
    const mx = Math.max(parseInt(p.max, 10) || 1, 1);
    jobProg.stepPct = Math.min(100, Math.floor((val / mx) * 100));
    if (p.message) jobProg.message = p.message;
  } else if (kind === "queue") {
    if (p.message) jobProg.message = p.message;
    jobProg.stepPct = Math.max(jobProg.stepPct, 8);
  } else if (kind === "running") {
    if (p.message) jobProg.message = p.message;
    const elapsed = parseInt(p.elapsed, 10) || 0;
    if (elapsed > 0) {
      jobProg.stepPct = Math.max(
        jobProg.stepPct,
        Math.min(92, Math.floor((elapsed / 90) * 88) + 4),
      );
    } else {
      jobProg.stepPct = Math.max(jobProg.stepPct, 12);
    }
  } else if (["status", "executing"].includes(kind) && p.message) {
    jobProg.message = p.message;
    if (kind === "executing") {
      jobProg.stepPct = Math.max(jobProg.stepPct, 20);
    }
  }
}

function overallJobPct() {
  if (jobProg.lastApiKind === "export") return null;
  if (!jobProg.batchIdx) return null;
  const total = Math.max(jobProg.batchTotal, 1);
  const idx = Math.max(jobProg.batchIdx, 1);
  return Math.min(
    100,
    Math.max(0, Math.floor(((idx - 1) + jobProg.stepPct / 100) / total * 100))
  );
}

function renderJobFloat() {
  const root = $("#job-float");
  const title = $("#job-float-title");
  const file = $("#job-float-file");
  const pctEl = $("#job-float-pct");
  const fill = $("#job-float-fill");
  const batch = $("#job-float-batch");
  const status = $("#job-float-status");
  const cancel = $("#job-float-cancel");
  if (!root) return;

  const isExport = jobProg.lastApiKind === "export";
  if (title) title.textContent = isExport ? t("job.exporting") : t("job.generating");
  if (file) {
    file.textContent = jobProg.filename || (isExport ? "…" : t("job.preparing"));
  }

  const pct = overallJobPct();
  const waiting =
    jobProg.stepPct < 100 &&
    ["queue", "running", "status", "executing"].includes(jobProg.phase);
  const indeterminate = isExport || pct === null || (pct === 0 && waiting && !jobProg.message);
  root.classList.toggle("is-indeterminate", indeterminate);

  if (pctEl) {
    if (indeterminate) pctEl.textContent = "…";
    else if (waiting && pct === 0 && jobProg.message) pctEl.textContent = "…";
    else pctEl.textContent = `${pct}%`;
  }
  if (fill) {
    if (indeterminate) fill.style.width = "";
    else fill.style.width = `${pct}%`;
  }
  if (batch) {
    batch.textContent =
      jobProg.batchTotal > 1 && jobProg.batchIdx ? `${jobProg.batchIdx}/${jobProg.batchTotal}` : "";
  }
  if (status) {
    status.textContent = jobProg.message || (indeterminate ? t("job.preparing") : "");
  }
  if (cancel) {
    cancel.disabled = jobProg.cancelling;
    cancel.textContent = jobProg.cancelling ? t("job.cancelling") : t("job.cancel");
  }
}

function showJobFloat() {
  const root = $("#job-float");
  if (!root) return;
  root.classList.remove("hidden");
  void root.offsetWidth;
  requestAnimationFrame(() => root.classList.add("is-visible"));
  jobProg.visible = true;
  renderJobFloat();
}

function hideJobFloat() {
  const root = $("#job-float");
  if (!root || root.classList.contains("hidden")) return;
  root.classList.remove("is-visible");
  jobProg.visible = false;
  window.setTimeout(() => {
    if (!jobProg.visible) {
      root.classList.add("hidden");
      resetJobProg();
    }
  }, 280);
}

function updateJobFromApi(j) {
  const pill = $("#job-pill");

  if (state.jobTrack.active && !state.jobTrack.postOk && !j.busy) {
    return;
  }
  if (
    state.jobRunId != null &&
    j.run_id != null &&
    j.run_id !== state.jobRunId &&
    !j.busy
  ) {
    return;
  }

  if (j.busy) {
    if (!state.jobTrack.active) {
      state.jobTrack = { active: true, sawBusy: true, postOk: true };
      if (j.run_id != null) state.jobRunId = j.run_id;
    } else {
      state.jobTrack.sawBusy = true;
    }
    if (j.kind) jobProg.lastApiKind = j.kind;
    ingestJobProgress(j.progress || {});
    showJobFloat();
    renderJobFloat();
    if (pill) {
      pill.textContent = j.kind === "export" ? t("job.exporting") : t("job.busy");
      pill.classList.add("busy");
      pill.dataset.busy = "1";
    }
    return;
  }

  if (!state.jobTrack.active && !state.jobTrack.sawBusy) {
    return;
  }
  if (state.jobRunId != null && j.run_id != null && j.run_id !== state.jobRunId) {
    return;
  }

  const quickFail = state.jobTrack.active && state.jobTrack.postOk && !state.jobTrack.sawBusy;
  finishJobUi({ quickFail });
  if (state.assetId) {
    loadPreview();
    loadPreviewInfo(state.assetId);
  }
  scanStatus();
}

function clampFloatPosition(x, y, el) {
  if (!el) return { x, y };
  const pad = 8;
  const w = el.offsetWidth || 280;
  const h = el.offsetHeight || 100;
  return {
    x: Math.max(pad, Math.min(x, window.innerWidth - w - pad)),
    y: Math.max(pad, Math.min(y, window.innerHeight - h - pad)),
  };
}

function applyJobFloatPosition(x, y, el, persist = true) {
  const root = el || $("#job-float");
  if (!root) return;
  const p = clampFloatPosition(x, y, root);
  root.style.left = `${p.x}px`;
  root.style.top = `${p.y}px`;
  root.style.right = "auto";
  if (persist) {
    try {
      localStorage.setItem(JOB_FLOAT_POS_KEY, JSON.stringify(p));
    } catch {
      /* ignore */
    }
  }
  return p;
}

function initJobFloatPosition() {
  const root = $("#job-float");
  if (!root) return;
  try {
    const raw = localStorage.getItem(JOB_FLOAT_POS_KEY);
    if (raw) {
      const p = JSON.parse(raw);
      if (Number.isFinite(p.x) && Number.isFinite(p.y)) {
        applyJobFloatPosition(p.x, p.y, root);
        return;
      }
    }
  } catch {
    /* ignore */
  }
  root.style.top = "76px";
  root.style.right = "20px";
  root.style.left = "auto";
}

function bindJobFloat() {
  const root = $("#job-float");
  const handle = $("#job-float-handle");
  const cancel = $("#job-float-cancel");
  if (!root || !handle) return;
  initJobFloatPosition();

  let drag = null;

  handle.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    const rect = root.getBoundingClientRect();
    root.style.left = `${rect.left}px`;
    root.style.top = `${rect.top}px`;
    root.style.right = "auto";
    drag = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      origX: rect.left,
      origY: rect.top,
      moved: false,
    };
    handle.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  handle.addEventListener("pointermove", (e) => {
    if (!drag || e.pointerId !== drag.pointerId) return;
    const dx = e.clientX - drag.startX;
    const dy = e.clientY - drag.startY;
    if (!drag.moved && Math.abs(dx) + Math.abs(dy) < JOB_FLOAT_DRAG_THRESHOLD) return;
    drag.moved = true;
    root.classList.add("is-dragging");
    applyJobFloatPosition(drag.origX + dx, drag.origY + dy, root, false);
  });

  const endDrag = (e) => {
    if (!drag || e.pointerId !== drag.pointerId) return;
    const wasDrag = drag.moved;
    drag = null;
    root.classList.remove("is-dragging");
    try {
      handle.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    if (wasDrag) {
      const x = parseInt(root.style.left, 10);
      const y = parseInt(root.style.top, 10);
      if (Number.isFinite(x) && Number.isFinite(y)) applyJobFloatPosition(x, y, root, true);
    }
  };

  handle.addEventListener("pointerup", endDrag);
  handle.addEventListener("pointercancel", endDrag);

  cancel?.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (jobProg.cancelling) return;
    jobProg.cancelling = true;
    renderJobFloat();
    try {
      await API.post("/api/jobs/cancel");
      toast(t("toast.cancelRequested"));
    } catch (err) {
      toast(err.message);
      jobProg.cancelling = false;
      renderJobFloat();
    }
  });
}

async function refreshComfy() {
  const pill = $("#comfy-pill");
  if (!pill) return false;
  pill.classList.add("is-checking");
  try {
    const data = await API.get("/api/comfyui/status");
    pill.textContent = data.ok ? t("comfy.online") : t("comfy.offline");
    pill.classList.toggle("ok", data.ok);
    pill.title = data.message || "";
    return !!data.ok;
  } catch {
    pill.textContent = "ComfyUI ?";
    pill.classList.remove("ok");
    pill.title = "";
    return false;
  } finally {
    pill.classList.remove("is-checking");
  }
}

async function ensureComfyOnline() {
  const ok = await refreshComfy();
  if (ok) return true;
  const pill = $("#comfy-pill");
  toast(pill?.title || t("comfy.offline"), { variant: "error" });
  return false;
}

function startJobPoll() {
  stopJobPoll();
  const tick = async () => {
    try {
      const j = await API.get("/api/jobs/status");
      updateJobFromApi(j);
    } catch {
      /* ignore */
    }
  };
  tick();
  state.jobTimer = setInterval(tick, 500);
}

async function startGenerate(exportAfter = false, onlySelected = false) {
  const ids = onlySelected ? selectedIds() : categoryAssetIds();
  await runGenerate(ids, {
    exportAfter,
    emptyToastKey: onlySelected ? "toast.selectAsset" : "toast.noCategoryAssets",
  });
}

async function startExport(onlySelected = false) {
  const ids = onlySelected ? selectedIds() : categoryAssetIds();
  await runExport(ids, {
    emptyToastKey: onlySelected ? "toast.selectAsset" : "toast.noCategoryAssets",
  });
}

// ── 日志 SSE ─────────────────────────────────────────────

function openLogDrawer() {
  const drawer = $("#log-drawer");
  const fab = $("#log-fab");
  drawer?.classList.add("open");
  drawer?.setAttribute("aria-hidden", "false");
  fab?.classList.add("active");
  fab?.setAttribute("aria-expanded", "true");
  const pre = $("#log-body");
  if (pre) pre.scrollTop = pre.scrollHeight;
}

function closeLogDrawer() {
  const drawer = $("#log-drawer");
  const fab = $("#log-fab");
  drawer?.classList.remove("open");
  drawer?.setAttribute("aria-hidden", "true");
  fab?.classList.remove("active");
  fab?.setAttribute("aria-expanded", "false");
}

function toggleLogDrawer() {
  if ($("#log-drawer")?.classList.contains("open")) closeLogDrawer();
  else openLogDrawer();
}

const LOG_FAB_POS_KEY = "artApp.logFabPos";
const LOG_FAB_DRAG_THRESHOLD = 5;

function clampLogFabPosition(x, y, fab) {
  const el = fab || $("#log-fab");
  if (!el) return { x, y };
  const pad = 8;
  const w = el.offsetWidth || 48;
  const h = el.offsetHeight || 28;
  return {
    x: Math.max(pad, Math.min(x, window.innerWidth - w - pad)),
    y: Math.max(pad, Math.min(y, window.innerHeight - h - pad)),
  };
}

function applyLogFabPosition(x, y, fab, persist = true) {
  const el = fab || $("#log-fab");
  if (!el) return;
  const p = clampLogFabPosition(x, y, el);
  el.style.left = `${p.x}px`;
  el.style.top = `${p.y}px`;
  el.style.right = "auto";
  el.style.bottom = "auto";
  if (persist) {
    try {
      localStorage.setItem(LOG_FAB_POS_KEY, JSON.stringify(p));
    } catch {
      /* ignore */
    }
  }
  return p;
}

function initLogFabPosition() {
  const fab = $("#log-fab");
  if (!fab) return;
  try {
    const raw = localStorage.getItem(LOG_FAB_POS_KEY);
    if (raw) {
      const p = JSON.parse(raw);
      if (Number.isFinite(p.x) && Number.isFinite(p.y)) {
        applyLogFabPosition(p.x, p.y, fab);
        return;
      }
    }
  } catch {
    /* ignore */
  }
  fab.style.left = "12px";
  fab.style.bottom = "12px";
  fab.style.top = "auto";
  fab.style.right = "auto";
}

function bindLogFabDrag() {
  const fab = $("#log-fab");
  if (!fab) return;
  initLogFabPosition();

  let drag = null;

  fab.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    const rect = fab.getBoundingClientRect();
    fab.style.left = `${rect.left}px`;
    fab.style.top = `${rect.top}px`;
    fab.style.right = "auto";
    fab.style.bottom = "auto";
    drag = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      origX: rect.left,
      origY: rect.top,
      moved: false,
    };
    fab.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  fab.addEventListener("pointermove", (e) => {
    if (!drag || e.pointerId !== drag.pointerId) return;
    const dx = e.clientX - drag.startX;
    const dy = e.clientY - drag.startY;
    if (!drag.moved && Math.abs(dx) + Math.abs(dy) < LOG_FAB_DRAG_THRESHOLD) return;
    drag.moved = true;
    fab.classList.add("is-dragging");
    applyLogFabPosition(drag.origX + dx, drag.origY + dy, fab, false);
  });

  const endDrag = (e) => {
    if (!drag || e.pointerId !== drag.pointerId) return;
    const wasDrag = drag.moved;
    drag = null;
    fab.classList.remove("is-dragging");
    try {
      fab.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    if (wasDrag) {
      const x = parseInt(fab.style.left, 10);
      const y = parseInt(fab.style.top, 10);
      if (Number.isFinite(x) && Number.isFinite(y)) applyLogFabPosition(x, y, fab, true);
    } else {
      toggleLogDrawer();
    }
  };

  fab.addEventListener("pointerup", endDrag);
  fab.addEventListener("pointercancel", endDrag);

  fab.addEventListener(
    "click",
    (e) => {
      e.preventDefault();
    },
    true,
  );

  window.addEventListener("resize", () => {
    const x = parseInt(fab.style.left, 10);
    const y = parseInt(fab.style.top, 10);
    if (Number.isFinite(x) && Number.isFinite(y)) applyLogFabPosition(x, y, fab);
  });
}

function logEntryTime(entry) {
  return entry?.ts ?? entry?.time ?? "—";
}

function logEntryText(entry) {
  return entry?.msg ?? entry?.message ?? "";
}

function formatLogLine(entry) {
  return `[${logEntryTime(entry)}] [${entry?.kind ?? "?"}] ${logEntryText(entry)}`;
}

function appendLog(entry) {
  const tab = state.logFilter;
  if (tab !== "全部" && entry.kind !== tab) return;
  const pre = $("#log-body");
  if (!pre) return;
  pre.textContent += `${formatLogLine(entry)}\n`;
  if (pre.textContent.length > 120000) {
    pre.textContent = pre.textContent.slice(-80000);
  }
  pre.scrollTop = pre.scrollHeight;
}

function connectLogs() {
  if (state.logEs) state.logEs.close();
  const pre = $("#log-body");
  if (pre) pre.textContent = "";
  state.logEs = new EventSource("/api/logs/stream");
  state.logEs.onmessage = (ev) => {
    try {
      appendLog(JSON.parse(ev.data));
    } catch {
      /* ignore */
    }
  };
  state.logEs.onerror = () => {
    state.logEs?.close();
    setTimeout(connectLogs, 3000);
  };
}

async function reloadLogsHistory() {
  const data = await API.get(`/api/logs?tab=${encodeURIComponent(state.logFilter)}`);
  const pre = $("#log-body");
  if (!pre) return;
  pre.textContent = (data.entries || []).map(formatLogLine).join("\n");
  pre.scrollTop = pre.scrollHeight;
}

// ── 保存操作 ─────────────────────────────────────────────

async function saveBasic(e) {
  e?.preventDefault();
  if (!state.assetId) return;
  const submitBtn = e?.submitter || e?.target?.querySelector('[type="submit"]');
  await withBtnBusy(submitBtn, async () => {
    const form = $("#form-basic");
    const body = {
      filename: form.filename.value.trim(),
      category: form.category.value,
      width: parseInt(form.width.value, 10),
      height: parseInt(form.height.value, 10),
      seed: form.seed.value.trim(),
      subject: form.subject.value.trim(),
      enabled: form.enabled.checked,
      remove_bg_mode: form.querySelector('input[name="remove_bg_mode"]:checked')?.value || "inherit",
      checkpoint: $("#asset-ckpt")?.value || "",
    };
    state.assetFull = await API.put(`/api/assets/${state.assetId}`, body);
    toast(t("toast.saved"));
    if (body.category !== state.categoryId) {
      await bootstrap(false);
      await selectCategory(body.category);
      await selectAsset(state.assetId);
    } else {
      await loadAssetList();
    }
  }).catch((err) => {
    if (err) toast(err.message);
  });
}

async function saveCategory(e) {
  e?.preventDefault();
  if (!state.categoryId) return;
  const submitBtn = e?.submitter || e?.target?.querySelector('[type="submit"]');
  await withBtnBusy(submitBtn, async () => {
    const form = $("#form-category");
    const body = {
      source: form.source.value.trim(),
      inbox: form.inbox.value.trim(),
      unity: form.unity.value.trim(),
      checkpoint: $("#cat-ckpt")?.value || "",
      alpha_matte: form.alpha_matte.checked ? "default" : "none",
      positive_common: form.positive_common.value,
      negative_common: form.negative_common.value,
    };
    await API.put(`/api/categories/${state.categoryId}`, body);
    toast(t("toast.categorySaved"));
    const data = await API.get("/api/categories");
    state.categories = data.categories || [];
    renderCategories();
  }).catch((err) => {
    if (err) toast(err.message);
  });
}

async function savePrompts(btn) {
  if (!state.assetId) return;
  await withBtnBusy(btn || document.querySelector('[data-action="save-prompts"]'), async () => {
    const data = state.assetFull || {};
    const useSplit = ["items", "skills"].includes(data.category);
    const mode = currentGenMode();
    const body = {
      negative: $("#negative-text").value,
      gen_mode: mode,
      ref_image:
        mode === "img2img"
          ? ($("#ref-image-path")?.value.trim() || "")
          : (state.assetFull?.ref_image || "").trim(),
      ref_image_use_source: false,
      img2img_denoise: parseFloat($("#img2img-denoise")?.value) || 0.65,
    };
    if (useSplit) {
      const g = $("#positive-g-text").value.trim();
      const l = $("#positive-l-text").value.trim();
      body.positive_g = g;
      body.positive_l = l;
      body.positive = `${g} ${l}`.trim();
    } else {
      body.positive = $("#positive-text").value;
    }
    state.assetFull = await API.put(`/api/assets/${state.assetId}`, body);
    updateGenModeUi();
    toast(t("toast.promptsSaved"));
  }).catch((err) => {
    if (err) toast(err.message);
  });
}

async function saveWorkflow(btn) {
  if (!state.assetId) return;
  await withBtnBusy(btn || document.querySelector('[data-action="save-wf"]'), async () => {
    await API.put(`/api/assets/${state.assetId}/workflow`, { text: $("#workflow-text").value });
    toast(t("toast.workflowSaved"));
  }).catch((err) => {
    if (err) toast(err.message);
  });
}

async function validateWorkflow(btn) {
  if (!state.assetId) return;
  await withBtnBusy(btn || document.querySelector('[data-action="validate-wf"]'), async () => {
    await API.post(`/api/assets/${state.assetId}/workflow/validate`, {
      text: $("#workflow-text").value,
    });
    toast(t("toast.jsonValid"));
  }).catch((err) => {
    if (err) toast(err.message);
  });
}

async function loadDefaultWorkflow(btn) {
  if (!state.assetId) return;
  await withBtnBusy(btn || document.querySelector('[data-action="load-default-wf"]'), async () => {
    const data = await API.get(`/api/assets/${state.assetId}/workflow/default`);
    $("#workflow-text").value = data.text || "";
    toast(t("toast.defaultTemplateLoaded"));
  }).catch((err) => {
    if (err) toast(err.message);
  });
}

async function saveSettings(e) {
  e?.preventDefault();
  const submitBtn = e?.submitter || e?.target?.querySelector('[type="submit"]');
  await withBtnBusy(submitBtn, async () => {
    const form = $("#form-settings");
    const body = {};
    for (const el of form.elements) {
      if (el.name) body[el.name] = el.type === "number" ? Number(el.value) : el.value;
    }
    await API.put("/api/settings", body);
    toast(t("toast.settingsSaved"));
    await loadCheckpoints();
    await loadSettingsForm();
  }).catch((err) => {
    if (err) toast(err.message);
  });
}

async function refreshUiAfterAi(applied) {
  if (!applied?.length) return;
  state.assetFull = null;
  const categoryChanged = applied.includes("category");
  const catSettingsChanged = applied.some((k) => k.startsWith("cat."));
  const basicFields = new Set([
    "filename",
    "category",
    "width",
    "height",
    "seed",
    "subject",
    "enabled",
    "remove_bg_mode",
    "checkpoint",
  ]);
  const promptFields = new Set([
    "positive",
    "negative",
    "positive_g",
    "positive_l",
    "gen_mode",
    "ref_image",
    "img2img_denoise",
    "workflow",
  ]);

  if (categoryChanged) {
    const fresh = await API.get(`/api/assets/${state.assetId}`);
    await bootstrap(false);
    await selectCategory(fresh.category);
    await selectAsset(state.assetId);
  } else {
    if (applied.some((k) => basicFields.has(k))) await loadBasicForm();
    if (applied.some((k) => promptFields.has(k))) await loadPromptTab();
    if (catSettingsChanged) {
      const fresh = await API.get(`/api/assets/${state.assetId}`);
      if (state.categoryId === fresh.category) await loadCategoryForm();
    }
    if (applied.includes("filename")) await loadAssetList();
    else if (applied.some((k) => basicFields.has(k))) await loadAssetList();
  }
  await loadPreview();
  await scanStatus();
  toast(t("toast.aiAutoSaved", { fields: applied.join(", ") }));
}

async function sendAi() {
  if (!state.assetId) {
    toast(t("toast.selectAsset"));
    return;
  }
  if (state.aiBusy) return;
  const msg = $("#ai-input").value.trim();
  if (!msg) return;
  $("#ai-input").value = "";
  setAiBusy(true);
  try {
    const data = await API.post("/api/ai/chat", {
      asset_id: state.assetId,
      message: msg,
      mode: state.aiMode,
    });
    await refreshAiMessages();
    if (data.applied?.length) {
      await refreshUiAfterAi(data.applied);
    }
  } catch (err) {
    toast(err.message);
    await refreshAiMessages();
  } finally {
    setAiBusy(false);
    updateAiModeUi();
  }
}

async function openAssetFile(assetId, kind) {
  try {
    const paths = await API.get(`/api/assets/${assetId}/paths`);
    const file = paths[kind];
    if (!file) {
      toast(t("toast.noPath"));
      return;
    }
    await openPath(file);
  } catch (err) {
    toast(err.message);
  }
}

function openPostprocess(assetId) {
  window.open(`/postprocess.html?asset=${encodeURIComponent(assetId)}`, "_blank");
}

async function renameAssetDialog(assetId) {
  let filename = state.assets.find((a) => a.id === assetId)?.filename;
  if (!filename) {
    const data = await API.get(`/api/assets/${assetId}`);
    filename = data.filename;
  }
  const dlg = $("#dlg-rename-asset");
  const form = $("#form-rename-asset");
  if (!dlg || !form) return;
  form.reset();
  form.filename.value = filename || "";
  dlg.showModal();
  form.onsubmit = async (e) => {
    e.preventDefault();
    const submitBtn = e.submitter || form.querySelector('[type="submit"]');
    const newName = form.filename.value.trim();
    if (!newName || newName === filename) {
      dlg.close();
      return;
    }
    await withBtnBusy(submitBtn, async () => {
      const data = await API.post(`/api/assets/${assetId}/rename`, { filename: newName });
      dlg.close();
      const n = data.renamed?.length || 0;
      toast(n > 0 ? t("toast.renamed", { n, name: data.filename }) : t("toast.renamedConfig", { name: data.filename }));
      if (assetId === state.assetId) {
        state.assetFull = null;
        await loadBasicForm();
        await loadPaths();
        await loadPreview();
      }
      await loadAssetList();
      await scanStatus();
    }).catch((err) => {
      if (err) toast(err.message);
    });
  };
}

async function deleteAsset(assetId) {
  if (!assetId) return;
  const asset = state.assets.find((a) => a.id === assetId);
  const filename = asset?.filename || assetId;
  const ok = await showConfirmDialog({
    title: t("confirm.deleteAsset.title"),
    message: t("confirm.deleteAsset.message", { name: filename, id: assetId }),
    details: [t("confirm.deleteAsset.detailConfig"), t("confirm.deleteAsset.detailFiles")],
    confirmText: t("confirm.deleteAsset.confirm"),
    danger: true,
  });
  if (!ok) return;
  try {
    await API.del(`/api/assets/${assetId}`);
    if (state.assetId === assetId) {
      state.assetId = null;
      state.assetFull = null;
      clearPreview();
    }
    await loadAssetList();
    updateMainTabsVisibility();
    if (!categoryHasAssets()) switchTab("category");
  } catch (err) {
    toast(err.message);
  }
}

async function refreshAssetEntry(assetId) {
  await selectAsset(assetId);
  await scanStatus();
  await loadPreview();
}

let assetCtxId = null;

const assetDrag = {
  active: false,
  suppressClick: false,
  assetId: null,
  fromCategory: null,
  dropCatId: null,
  row: null,
  ghost: null,
  timer: null,
  pointerId: null,
  startX: 0,
  startY: 0,
};

const ASSET_DRAG_LONG_PRESS_MS = 450;
const ASSET_DRAG_MOVE_THRESHOLD = 10;

function clearCategoryDropTargets() {
  $$(".cat-item.drop-target").forEach((el) => el.classList.remove("drop-target"));
}

function positionAssetDragGhost(x, y) {
  const ghost = assetDrag.ghost;
  if (!ghost) return;
  ghost.style.left = `${x + 12}px`;
  ghost.style.top = `${y + 12}px`;
}

function cleanupAssetDrag() {
  clearTimeout(assetDrag.timer);
  assetDrag.timer = null;
  assetDrag.active = false;
  assetDrag.assetId = null;
  assetDrag.fromCategory = null;
  assetDrag.dropCatId = null;
  assetDrag.pointerId = null;
  assetDrag.row?.classList.remove("is-drag-source");
  assetDrag.row = null;
  if (assetDrag.ghost) {
    assetDrag.ghost.remove();
    assetDrag.ghost = null;
  }
  clearCategoryDropTargets();
}

function startAssetDrag(e, row, assetId) {
  const asset = state.assets.find((a) => a.id === assetId);
  assetDrag.active = true;
  assetDrag.suppressClick = true;
  assetDrag.assetId = assetId;
  assetDrag.fromCategory = state.categoryId;
  assetDrag.row = row;
  row.classList.add("is-drag-source");

  const ghost = document.createElement("div");
  ghost.className = "asset-drag-ghost";
  ghost.innerHTML = `<span class="asset-drag-ghost-label">${esc(asset?.filename || assetId)}</span>`;
  document.body.appendChild(ghost);
  assetDrag.ghost = ghost;
  positionAssetDragGhost(e.clientX, e.clientY);
  try {
    row.setPointerCapture(e.pointerId);
  } catch {
    /* ignore */
  }
  toast(t("toast.assetDragHint"));
}

function updateAssetDragTarget(clientX, clientY) {
  clearCategoryDropTargets();
  assetDrag.dropCatId = null;
  const el = document.elementFromPoint(clientX, clientY);
  const cat = el?.closest?.(".cat-item");
  if (!cat?.dataset.catId) return;
  if (cat.dataset.catId === assetDrag.fromCategory) return;
  cat.classList.add("drop-target");
  assetDrag.dropCatId = cat.dataset.catId;
}

function onAssetDragPointerMove(e) {
  if (assetDrag.timer && !assetDrag.active) {
    const dx = e.clientX - assetDrag.startX;
    const dy = e.clientY - assetDrag.startY;
    if (Math.hypot(dx, dy) > ASSET_DRAG_MOVE_THRESHOLD) {
      clearTimeout(assetDrag.timer);
      assetDrag.timer = null;
    }
    return;
  }
  if (!assetDrag.active) return;
  if (assetDrag.pointerId != null && e.pointerId !== assetDrag.pointerId) return;
  e.preventDefault();
  positionAssetDragGhost(e.clientX, e.clientY);
  updateAssetDragTarget(e.clientX, e.clientY);
}

async function confirmMoveAssetToCategory(assetId, targetCatId, fromCategoryId) {
  const asset = state.assets.find((a) => a.id === assetId);
  const fromCat = state.categories.find((c) => c.id === fromCategoryId);
  const toCat = state.categories.find((c) => c.id === targetCatId);
  if (!asset || !toCat) return;

  let preview;
  try {
    preview = await API.get(
      `/api/assets/${encodeURIComponent(assetId)}/move-preview?category=${encodeURIComponent(targetCatId)}`,
    );
  } catch (err) {
    toast(err.message, { variant: "error" });
    return;
  }
  if (preview.same_category) return;

  const fromLabel = preview.from_label || fromCat?.label || preview.from_category;
  const toLabel = preview.to_label || toCat.label;
  const details = [
    t("confirm.moveAsset.detailWarning"),
    t("confirm.moveAsset.detailCaution"),
  ];
  const kindLabels = {
    source: t("confirm.moveAsset.kindSource"),
    inbox: t("confirm.moveAsset.kindInbox"),
    unity: t("confirm.moveAsset.kindUnity"),
  };
  for (const file of preview.files || []) {
    const kind = kindLabels[file.kind] || file.kind;
    if (file.exists) {
      details.push(t("confirm.moveAsset.detailMove", { kind, from: file.from, to: file.to }));
    } else {
      details.push(t("confirm.moveAsset.detailSkip", { kind }));
    }
  }

  const ok = await showConfirmDialog({
    title: t("confirm.moveAsset.title"),
    message: t("confirm.moveAsset.message", {
      name: asset.filename,
      fromLabel,
      toLabel,
    }),
    details,
    confirmText: t("confirm.moveAsset.confirm"),
    danger: true,
  });
  if (!ok) return;

  try {
    const data = await API.post(`/api/assets/${encodeURIComponent(assetId)}/move-category`, {
      category: targetCatId,
    });
    const moved = data.moved?.length || 0;
    toast(t("toast.assetMoved", { label: toLabel, n: moved }));
    const wasSource = state.categoryId === preview.from_category;
    const wasTarget = state.categoryId === targetCatId;
    if (wasSource || wasTarget) {
      await loadAssetList();
      updateMainTabsVisibility();
    }
    if (wasTarget && data.asset?.id) {
      await selectAsset(data.asset.id);
    } else if (state.assetId === assetId && wasSource) {
      state.assetId = null;
      state.assetFull = null;
      clearPreview();
      if (!categoryHasAssets()) switchTab("category");
    }
    scanStatus();
  } catch (err) {
    toast(err.message, { variant: "error" });
  }
}

async function onAssetDragPointerEnd(e) {
  clearTimeout(assetDrag.timer);
  assetDrag.timer = null;
  if (!assetDrag.active) return;
  if (assetDrag.pointerId != null && e.pointerId !== assetDrag.pointerId) return;

  const targetCatId = assetDrag.dropCatId;
  const assetId = assetDrag.assetId;
  const fromCategoryId = assetDrag.fromCategory;
  cleanupAssetDrag();
  if (targetCatId && assetId) {
    await confirmMoveAssetToCategory(assetId, targetCatId, fromCategoryId);
  }
}

function bindAssetDragToCategory() {
  const list = $("#asset-list");
  if (!list) return;

  list.addEventListener(
    "pointerdown",
    (e) => {
      if (e.button !== 0 && e.pointerType === "mouse") return;
      const row = e.target.closest(".asset-row");
      if (!row || e.target.closest(".path-chip")) return;
      const assetId = row.dataset.id;
      if (!assetId || !state.categoryId) return;

      assetDrag.pointerId = e.pointerId;
      assetDrag.startX = e.clientX;
      assetDrag.startY = e.clientY;
      assetDrag.row = row;
      clearTimeout(assetDrag.timer);
      assetDrag.timer = setTimeout(() => {
        assetDrag.timer = null;
        startAssetDrag(e, row, assetId);
      }, ASSET_DRAG_LONG_PRESS_MS);
    },
    { passive: true },
  );

  window.addEventListener("pointermove", onAssetDragPointerMove, { passive: false });
  window.addEventListener("pointerup", onAssetDragPointerEnd);
  window.addEventListener("pointercancel", () => cleanupAssetDrag());
}

function closeNavMenus() {
  closeAllFloatingMenus(["#asset-ctx-menu", "#cat-ctx-menu"]);
}

/** 现代化确认对话框；返回 true 表示用户确认 */
function showConfirmDialog({
  title,
  message,
  details = [],
  confirmText,
  cancelText,
  danger = true,
}) {
  const dlg = $("#dlg-confirm");
  const icon = $("#confirm-icon");
  const titleEl = $("#confirm-title");
  const msgEl = $("#confirm-message");
  const listEl = $("#confirm-details");
  const okBtn = $("#confirm-ok");
  const cancelBtn = $("#confirm-cancel");
  if (!dlg || !titleEl || !msgEl || !okBtn || !cancelBtn) return Promise.resolve(false);

  titleEl.textContent = title || "";
  msgEl.textContent = message || "";
  icon?.classList.toggle("danger", danger);
  okBtn.textContent = confirmText || t("dlg.confirm");
  okBtn.className = danger ? "btn danger" : "btn primary";
  cancelBtn.textContent = cancelText || t("dlg.cancel");

  if (listEl) {
    const items = details.filter(Boolean);
    listEl.innerHTML = items.map((line) => `<li>${esc(line)}</li>`).join("");
    listEl.classList.toggle("hidden", items.length === 0);
  }

  dlg.showModal();
  return new Promise((resolve) => {
    const finish = (val) => {
      dlg.close();
      okBtn.removeEventListener("click", onOk);
      cancelBtn.removeEventListener("click", onCancel);
      dlg.removeEventListener("cancel", onCancel);
      resolve(val);
    };
    const onOk = () => finish(true);
    const onCancel = (e) => {
      e?.preventDefault?.();
      finish(false);
    };
    okBtn.addEventListener("click", onOk);
    cancelBtn.addEventListener("click", onCancel);
    dlg.addEventListener("cancel", onCancel);
  });
}

async function renameCategoryDialog(catId) {
  const cat = state.categories.find((c) => c.id === catId);
  if (!cat) return;
  const dlg = $("#dlg-rename-category");
  const form = $("#form-rename-category");
  const idHint = $("#rename-category-id");
  if (!dlg || !form) return;
  form.reset();
  form.label.value = cat.label;
  if (idHint) idHint.textContent = `ID: ${cat.id}`;
  dlg.showModal();
  form.onsubmit = async (e) => {
    e.preventDefault();
    const submitBtn = e.submitter || form.querySelector('[type="submit"]');
    const label = form.label.value.trim();
    if (!label || label === cat.label) {
      dlg.close();
      return;
    }
    await withBtnBusy(submitBtn, async () => {
      await API.put(`/api/categories/${catId}`, { label });
      dlg.close();
      toast(t("toast.categoryRenamed"));
      const data = await API.get("/api/categories");
      state.categories = data.categories || [];
      renderCategories();
      if (state.categoryId === catId) await loadCategoryForm();
    }).catch((err) => {
      if (err) toast(err.message);
    });
  };
}

async function deleteCategory(catId) {
  const cat = state.categories.find((c) => c.id === catId);
  if (!cat) return;
  let assetCount = 0;
  try {
    const data = await API.get(`/api/assets?category=${encodeURIComponent(catId)}`);
    assetCount = data.count ?? (data.assets?.length || 0);
  } catch {
    /* ignore */
  }
  const details = [t("confirm.deleteCategory.detailConfig")];
  if (assetCount > 0) {
    details.push(t("confirm.deleteCategory.detailAssets", { n: assetCount }));
  }
  details.push(t("confirm.deleteCategory.detailFiles"));
  const ok = await showConfirmDialog({
    title: t("confirm.deleteCategory.title"),
    message: t("confirm.deleteCategory.message", { name: cat.label, id: cat.id }),
    details,
    confirmText: t("confirm.deleteCategory.confirm"),
    danger: true,
  });
  if (!ok) return;
  try {
    await API.del(`/api/categories/${catId}`);
    toast(t("toast.categoryDeleted"));
    const wasCurrent = state.categoryId === catId;
    if (wasCurrent) {
      state.categoryId = null;
      state.assetId = null;
      state.assetFull = null;
      state.assets = [];
      state.statusMap = {};
      clearPreview();
    }
    const data = await API.get("/api/categories");
    state.categories = data.categories || [];
    renderCategories();
    if (state.categories.length) {
      await selectCategory(wasCurrent ? state.categories[0].id : state.categoryId || state.categories[0].id);
    } else {
      updateMainTabsVisibility();
      switchTab("settings");
    }
  } catch (err) {
    toast(err.message);
  }
}

let catCtxId = null;

function hideCatCtxMenu() {
  catCtxId = null;
  closeFloatingMenu($("#cat-ctx-menu"));
}

function showCatCtxMenu(x, y, catId) {
  closeNavMenus();
  hideAssetCtxMenu();
  const menu = $("#cat-ctx-menu");
  if (!menu) return;
  catCtxId = catId;
  openFloatingMenu(menu, () => {
    menu.style.left = "0px";
    menu.style.top = "0px";
    const pad = 8;
    const rect = menu.getBoundingClientRect();
    const maxX = window.innerWidth - rect.width - pad;
    const maxY = window.innerHeight - rect.height - pad;
    menu.style.left = `${Math.max(pad, Math.min(x, maxX))}px`;
    menu.style.top = `${Math.max(pad, Math.min(y, maxY))}px`;
  });
}

function bindCategoryContextMenu() {
  const list = $("#cat-list");
  const menu = $("#cat-ctx-menu");
  if (!list || !menu) return;

  list.addEventListener("contextmenu", (e) => {
    const item = e.target.closest(".cat-item");
    if (!item) return;
    const catId = item.dataset.catId;
    if (!catId) return;
    e.preventDefault();
    e.stopPropagation();
    showCatCtxMenu(e.clientX, e.clientY, catId);
  });

  menu.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-ctx]");
    if (!btn || !catCtxId) return;
    e.stopPropagation();
    const id = catCtxId;
    hideCatCtxMenu();
    const act = btn.dataset.ctx;
    if (act === "gen-category") {
      await runGenerate(await enabledAssetIdsForCategory(id));
    } else if (act === "gen-category-export") {
      await runGenerate(await enabledAssetIdsForCategory(id), { exportAfter: true });
    } else if (act === "export-category") {
      await runExport(await enabledAssetIdsForCategory(id));
    } else if (act === "rename") await renameCategoryDialog(id);
    else if (act === "delete") await deleteCategory(id);
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest("#cat-ctx-menu")) hideCatCtxMenu();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hideCatCtxMenu();
  });
  window.addEventListener(
    "scroll",
    () => {
      hideCatCtxMenu();
    },
    true,
  );
}

function hideAssetCtxMenu() {
  assetCtxId = null;
  closeFloatingMenu($("#asset-ctx-menu"));
}

function showAssetCtxMenu(x, y, assetId) {
  closeNavMenus();
  hideCatCtxMenu();
  const menu = $("#asset-ctx-menu");
  if (!menu) return;
  assetCtxId = assetId;
  openFloatingMenu(menu, () => {
    menu.style.left = "0px";
    menu.style.top = "0px";
    const pad = 8;
    const rect = menu.getBoundingClientRect();
    const maxX = window.innerWidth - rect.width - pad;
    const maxY = window.innerHeight - rect.height - pad;
    menu.style.left = `${Math.max(pad, Math.min(x, maxX))}px`;
    menu.style.top = `${Math.max(pad, Math.min(y, maxY))}px`;
  });
}

function bindAssetContextMenu() {
  const list = $("#asset-list");
  const menu = $("#asset-ctx-menu");
  if (!list || !menu) return;

  list.addEventListener("contextmenu", (e) => {
    const row = e.target.closest(".asset-row");
    if (!row) return;
    const assetId = row.dataset.id;
    if (!assetId) return;
    e.preventDefault();
    e.stopPropagation();
    showAssetCtxMenu(e.clientX, e.clientY, assetId);
  });

  menu.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-ctx]");
    if (!btn || !assetCtxId) return;
    e.stopPropagation();
    const id = assetCtxId;
    hideAssetCtxMenu();
    const act = btn.dataset.ctx;
    if (act === "gen-one") {
      if (id !== state.assetId) await selectAsset(id);
      await runGenerate([id], { emptyToastKey: "toast.selectAsset" });
    } else if (act === "gen-one-export") {
      if (id !== state.assetId) await selectAsset(id);
      await runGenerate([id], { exportAfter: true, emptyToastKey: "toast.selectAsset" });
    } else if (act === "export-one") {
      if (id !== state.assetId) await selectAsset(id);
      await runExport([id], { emptyToastKey: "toast.selectAsset" });
    } else if (act === "rename") await renameAssetDialog(id);
    else if (act === "postprocess") openPostprocess(id);
    else if (act === "open-source") await openAssetFile(id, "source");
    else if (act === "open-inbox") await openAssetFile(id, "inbox");
    else if (act === "open-unity") await openAssetFile(id, "unity");
    else if (act === "refresh") await refreshAssetEntry(id);
    else if (act === "delete") await deleteAsset(id);
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest("#asset-ctx-menu")) hideAssetCtxMenu();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hideAssetCtxMenu();
  });
  window.addEventListener(
    "scroll",
    () => {
      hideAssetCtxMenu();
    },
    true,
  );
}

async function openPath(path) {
  if (!path) return;
  try {
    await API.post("/api/open-path", { path });
  } catch (err) {
    toast(err.message);
  }
}

async function openPreviewFile() {
  if (!state.assetId) {
    toast(t("toast.selectAsset"));
    return;
  }
  const key = currentPreviewSourceKey();
  try {
    const paths = await API.get(`/api/assets/${state.assetId}/paths`);
    state.paths = paths;
    const file = paths[key];
    if (!file) {
      toast(t("toast.noPath"));
      return;
    }
    await openPath(file);
  } catch (err) {
    toast(err.message);
  }
}

// ── 对话框 ─────────────────────────────────────────────

function bindDialogDismiss(dlg) {
  const form = dlg.querySelector("form");
  form?.querySelector("[data-dismiss]")?.addEventListener("click", () => dlg.close());
  dlg.addEventListener("cancel", (e) => {
    e.preventDefault();
    dlg.close();
  });
}

async function newCategoryDialog() {
  const dlg = $("#dlg-new-cat");
  const form = $("#form-new-cat");
  form.reset();
  await fillNewCatCheckpointSelect();
  dlg.showModal();
  form.onsubmit = async (e) => {
    e.preventDefault();
    const label = form.label.value.trim();
    if (!label) {
      toast(t("toast.categoryNameRequired"));
      return;
    }
    const submitBtn = e.submitter || form.querySelector('button[type="submit"]');
    const checkpoint = form.checkpoint?.value?.trim() || "";
    await withBtnBusy(submitBtn, async () => {
      try {
        const cat = await API.post("/api/categories", {
          label,
          id: form.id.value.trim() || undefined,
          checkpoint,
        });
        dlg.close();
        await bootstrap(false);
        await selectCategory(cat.id);
        toast(t("toast.categoryCreated"));
      } catch (err) {
        toast(err.message);
        throw err;
      }
    });
  };
}

let newAssetDlgTab = "manual";
/** @type {{ id: string, file: File, url: string, width?: number, height?: number }[]} */
let importDraftFiles = [];
let importDraftSeq = 0;
let newAssetImportBound = false;

function importAssetTargetName(file) {
  const stem = (file.name || "import").replace(/\.[^.]+$/, "").trim() || "import";
  return `${stem}.png`;
}

function resetImportDraft() {
  for (const item of importDraftFiles) {
    if (item.url) URL.revokeObjectURL(item.url);
  }
  importDraftFiles = [];
  const input = $("#import-asset-files");
  if (input) input.value = "";
  renderImportAssetList();
}

function updateNewAssetSubmitLabel() {
  const btn = $("#new-asset-submit");
  if (!btn) return;
  if (newAssetDlgTab === "import") {
    const n = importDraftFiles.length;
    btn.textContent = n > 0 ? t("dlg.importCreate", { n }) : t("dlg.create");
  } else {
    btn.textContent = t("dlg.create");
  }
}

function switchNewAssetDlgTab(tab) {
  newAssetDlgTab = tab;
  const dlg = $("#dlg-new-asset");
  if (!dlg) return;
  dlg.querySelectorAll(".dlg-tab").forEach((btn) => {
    const active = btn.dataset.dlgTab === tab;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  dlg.querySelectorAll("[data-dlg-panel]").forEach((panel) => {
    const show = panel.dataset.dlgPanel === tab;
    panel.classList.toggle("hidden", !show);
    panel.hidden = !show;
  });
  updateNewAssetSubmitLabel();
}

function probeImportImageSize(item) {
  const img = new Image();
  img.onload = () => {
    item.width = img.naturalWidth;
    item.height = img.naturalHeight;
    renderImportAssetList();
  };
  img.onerror = () => {};
  img.src = item.url;
}

function addImportDraftFiles(fileList) {
  const existing = new Set(importDraftFiles.map((x) => x.file.name));
  for (const file of fileList) {
    if (!file || !file.type.startsWith("image/")) continue;
    if (existing.has(file.name)) continue;
    existing.add(file.name);
    const item = {
      id: `imp-${++importDraftSeq}`,
      file,
      url: URL.createObjectURL(file),
    };
    importDraftFiles.push(item);
    probeImportImageSize(item);
  }
  renderImportAssetList();
}

function removeImportDraftFile(id) {
  const idx = importDraftFiles.findIndex((x) => x.id === id);
  if (idx < 0) return;
  const [removed] = importDraftFiles.splice(idx, 1);
  if (removed?.url) URL.revokeObjectURL(removed.url);
  renderImportAssetList();
}

function renderImportAssetList() {
  const list = $("#import-asset-list");
  const countEl = $("#import-asset-count");
  const emptyEl = $("#import-asset-empty");
  if (!list) return;

  list.replaceChildren();
  for (const item of importDraftFiles) {
    const li = document.createElement("li");
    li.className = "import-asset-item";
    li.dataset.importId = item.id;

    const thumb = document.createElement("img");
    thumb.className = "import-asset-thumb";
    thumb.src = item.url;
    thumb.alt = "";
    thumb.loading = "lazy";

    const meta = document.createElement("div");
    meta.className = "import-asset-meta";

    const name = document.createElement("div");
    name.className = "import-asset-name";
    name.textContent = importAssetTargetName(item.file);
    name.title = item.file.name;

    const sub = document.createElement("div");
    sub.className = "import-asset-sub";
    const parts = [formatBytes(item.file.size)];
    if (item.width && item.height) parts.push(`${item.width}×${item.height}`);
    sub.textContent = parts.filter(Boolean).join(" · ");

    meta.append(name, sub);

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "import-asset-remove";
    removeBtn.textContent = "×";
    removeBtn.setAttribute("aria-label", t("asset.delete"));
    removeBtn.dataset.importRemove = item.id;

    li.append(thumb, meta, removeBtn);
    list.appendChild(li);
  }

  if (countEl) {
    countEl.textContent =
      importDraftFiles.length > 0
        ? t("dlg.importCount", { n: importDraftFiles.length })
        : "";
  }
  if (emptyEl) {
    emptyEl.hidden = importDraftFiles.length > 0;
  }
  updateNewAssetSubmitLabel();
}

function bindNewAssetImportUi() {
  if (newAssetImportBound) return;
  newAssetImportBound = true;

  const dlg = $("#dlg-new-asset");
  const form = $("#form-new-asset");
  const fileInput = $("#import-asset-files");
  const pickBtn = $("#import-asset-pick");
  const list = $("#import-asset-list");

  form?.querySelectorAll(".dlg-tab").forEach((tab) => {
    tab.addEventListener("click", () => switchNewAssetDlgTab(tab.dataset.dlgTab || "manual"));
  });

  pickBtn?.addEventListener("click", () => fileInput?.click());

  fileInput?.addEventListener("change", () => {
    if (fileInput.files?.length) addImportDraftFiles(fileInput.files);
    fileInput.value = "";
  });

  list?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-import-remove]");
    if (!btn) return;
    removeImportDraftFile(btn.dataset.importRemove);
  });

  dlg?.addEventListener("close", () => {
    resetImportDraft();
    switchNewAssetDlgTab("manual");
    setFormError(form, "");
  });
}

function parseNewAssetForm(form) {
  const filename = form.filename.value.trim();
  const size = parseInt(form.size.value, 10);
  if (!filename) return { error: t("toast.filenameRequired") };
  if (!Number.isFinite(size) || size < 32 || size > 4096) {
    return { error: t("toast.invalidSize") };
  }
  return {
    filename,
    width: size,
    height: size,
    subject: form.subject.value.trim(),
  };
}

async function newAssetDialog() {
  if (!state.categoryId) {
    toast(t("toast.selectCategory"), { variant: "error" });
    return;
  }
  bindNewAssetImportUi();
  const dlg = $("#dlg-new-asset");
  const form = $("#form-new-asset");
  if (!dlg || !form) return;
  form.reset();
  resetImportDraft();
  switchNewAssetDlgTab("manual");
  setFormError(form, "");
  dlg.showModal();
  form.onsubmit = async (e) => {
    e.preventDefault();
    setFormError(form, "");
    const submitBtn = e.submitter || form.querySelector('button[type="submit"]');

    if (newAssetDlgTab === "import") {
      if (importDraftFiles.length === 0) {
        const msg = t("toast.importEmpty");
        setFormError(form, msg);
        toast(msg, { variant: "error" });
        return;
      }
      await withBtnBusy(submitBtn, async () => {
        try {
          const fd = new FormData();
          fd.append("category", state.categoryId);
          for (const item of importDraftFiles) {
            fd.append("files", item.file, item.file.name);
          }
          const result = await API.postForm("/api/assets/import", fd);
          dlg.close();
          resetImportDraft();
          await loadAssetList();
          updateMainTabsVisibility();
          const created = result?.created || [];
          const failed = result?.failed || [];
          if (failed.length) {
            toast(
              t("toast.assetsImportedPartial", {
                ok: result.count ?? created.length,
                fail: failed.length,
              }),
              { variant: failed.length && !created.length ? "error" : "warning" },
            );
          } else {
            toast(t("toast.assetsImported", { n: result.count ?? created.length }));
          }
          if (created[0]?.id) {
            await selectAsset(created[0].id);
            switchTab("basic");
          }
        } catch (err) {
          setFormError(form, err.message);
          toast(err.message, { variant: "error" });
          throw err;
        }
      });
      return;
    }

    const parsed = parseNewAssetForm(form);
    if (parsed.error) {
      setFormError(form, parsed.error);
      toast(parsed.error, { variant: "error" });
      return;
    }
    await withBtnBusy(submitBtn, async () => {
      try {
        const asset = await API.post("/api/assets", {
          filename: parsed.filename,
          category: state.categoryId,
          width: parsed.width,
          height: parsed.height,
          subject: parsed.subject,
          enabled: false,
        });
        dlg.close();
        await loadAssetList();
        updateMainTabsVisibility();
        if (asset?.id) {
          await selectAsset(asset.id);
          switchTab("basic");
        }
        toast(t("toast.assetCreated"));
      } catch (err) {
        setFormError(form, err.message);
        toast(err.message, { variant: "error" });
        throw err;
      }
    });
  };
}

// ── 事件 ─────────────────────────────────────────────

const ASSET_PANEL_STORAGE_KEY = "artApp.assetPanelW";
const ASSET_PANEL_MIN = 176;
const ASSET_PANEL_MAX = 440;
const ASSET_PANEL_DEFAULT = 228;

function applyAssetPanelWidth(width) {
  const w = Math.min(ASSET_PANEL_MAX, Math.max(ASSET_PANEL_MIN, Math.round(width)));
  document.documentElement.style.setProperty("--asset-panel-w", `${w}px`);
  const panel = $("#panel-assets");
  if (panel) panel.style.width = `${w}px`;
  try {
    localStorage.setItem(ASSET_PANEL_STORAGE_KEY, String(w));
  } catch {
    /* ignore */
  }
  return w;
}

function readAssetPanelWidth() {
  const panel = $("#panel-assets");
  const inline = panel ? parseInt(panel.style.width, 10) : NaN;
  if (Number.isFinite(inline)) return inline;
  const raw = parseInt(localStorage.getItem(ASSET_PANEL_STORAGE_KEY) || "", 10);
  return Number.isFinite(raw) ? raw : ASSET_PANEL_DEFAULT;
}

function bindAssetPanelResize() {
  const resizer = $("#asset-panel-resizer");
  if (!resizer) return;

  applyAssetPanelWidth(readAssetPanelWidth());

  let startX = 0;
  let startW = ASSET_PANEL_DEFAULT;
  let dragging = false;

  const stopDrag = (e) => {
    if (!dragging) return;
    dragging = false;
    resizer.classList.remove("is-dragging");
    document.body.classList.remove("is-col-resizing");
    try {
      resizer.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  };

  const onMove = (e) => {
    if (!dragging) return;
    e.preventDefault();
    applyAssetPanelWidth(startW + (e.clientX - startX));
  };

  resizer.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    dragging = true;
    startX = e.clientX;
    startW = readAssetPanelWidth();
    resizer.classList.add("is-dragging");
    document.body.classList.add("is-col-resizing");
    resizer.setPointerCapture(e.pointerId);
  });

  resizer.addEventListener("pointermove", onMove);
  resizer.addEventListener("pointerup", stopDrag);
  resizer.addEventListener("pointercancel", stopDrag);

  resizer.addEventListener("keydown", (e) => {
    const step = e.shiftKey ? 24 : 8;
    let w = readAssetPanelWidth();
    if (e.key === "ArrowLeft") w -= step;
    else if (e.key === "ArrowRight") w += step;
    else return;
    e.preventDefault();
    applyAssetPanelWidth(w);
  });
}

function bindUi() {
  bindRipple(document.getElementById("app"));
  bindAssetPanelResize();
  bindAssetContextMenu();
  bindCategoryContextMenu();
  bindAssetDragToCategory();
  bindJobFloat();
  bindLogFabDrag();
  bindPreviewViewport();
  bindDialogDismiss($("#dlg-new-cat"));
  bindDialogDismiss($("#dlg-new-asset"));
  bindDialogDismiss($("#dlg-rename-asset"));
  bindDialogDismiss($("#dlg-rename-category"));
  bindDialogDismiss($("#dlg-confirm"));

  $("#preview-img")?.addEventListener("error", () => {
    const asset = state.assets.find((a) => a.id === state.assetId);
    showPreviewEmpty(asset || null);
  });

  $("#asset-search")?.addEventListener("input", () => {
    clearTimeout(state.searchTimer);
    state.searchTimer = setTimeout(loadAssetList, 150);
  });

  $("#asset-list")?.addEventListener("click", (e) => {
    const chip = e.target.closest(".path-chip");
    if (!chip) return;
    e.preventDefault();
    e.stopPropagation();
    const assetId = chip.dataset.assetId;
    const kind = chip.dataset.pathKind;
    if (assetId && kind) openAssetPathDir(assetId, kind);
  });

  $$(".seg-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".seg-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.previewSource = btn.dataset.source || "inbox";
      if (state.assetId) {
        loadPreview();
        if (state.previewInfo) renderPreviewInfo(state.previewInfo);
      }
    });
  });

  $$("#main-tabs .tab").forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  $$(".ai-mode-tab").forEach((tab) => {
    tab.addEventListener("click", () => switchAiMode(tab.dataset.aiMode));
  });

  updateAiModeUi();
  renderAiChat([]);

  $("#form-basic")?.addEventListener("submit", saveBasic);
  $("#form-category")?.addEventListener("submit", saveCategory);
  $("#form-settings")?.addEventListener("submit", saveSettings);

  $$('input[name="gen_mode"]').forEach((r) => {
    r.addEventListener("change", updateGenModeUi);
  });
  $("#img2img-denoise-range")?.addEventListener("input", syncDenoiseFromRange);
  $("#img2img-denoise")?.addEventListener("change", syncDenoiseFromNumber);

  $("#log-filter")?.addEventListener("change", (e) => {
    state.logFilter = e.target.value;
    reloadLogsHistory();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && $("#log-drawer")?.classList.contains("open")) {
      closeLogDrawer();
    }
    if (e.key === "Escape") closeNavMenus();
  });

  $("#ai-input")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      sendAi();
    }
  });

  document.addEventListener("click", () => {
    closeNavMenus();
  });

  document.getElementById("app")?.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    closeNavMenus();
    const act = btn.dataset.action;
    switch (act) {
      case "scan-status":
        await withBtnBusy(btn, scanStatus);
        break;
      case "dup-asset":
        if (!state.assetId) break;
        await withBtnBusy(btn, async () => {
          const a = await API.post(`/api/assets/${state.assetId}/duplicate`);
          await loadAssetList();
          await selectAsset(a.id);
        }).catch((err) => {
          if (err) toast(err.message);
        });
        break;
      case "refresh-preview":
        if (state.assetId) {
          loadPreview();
          loadPreviewInfo(state.assetId);
        }
        break;
      case "open-file":
        await openPreviewFile();
        break;
      case "open-inbox-dir":
        if (state.categoryId) {
          const d = await API.get(`/api/categories/${state.categoryId}/dir/inbox`);
          openPath(d.path);
        }
        break;
      case "open-source-dir":
        if (state.categoryId) {
          const d = await API.get(`/api/categories/${state.categoryId}/dir/source`);
          openPath(d.path);
        }
        break;
      case "postprocess":
        if (state.assetId) openPostprocess(state.assetId);
        break;
      case "new-category":
        newCategoryDialog();
        break;
      case "new-asset":
        newAssetDialog();
        break;
      case "save-prompts":
        await savePrompts(btn);
        break;
      case "pick-ref-image":
        await pickRefImage(btn);
        break;
      case "save-wf":
        await saveWorkflow(btn);
        break;
      case "validate-wf":
        await validateWorkflow(btn);
        break;
      case "load-default-wf":
        await loadDefaultWorkflow(btn);
        break;
      case "ai-send":
        sendAi();
        break;
      case "ai-clear":
        await clearAiChat();
        break;
      case "clear-logs":
        await API.del("/api/logs");
        $("#log-body").textContent = "";
        break;
      case "close-logs":
        closeLogDrawer();
        break;
      case "init-workflows":
        await withBtnBusy(btn, async () => {
          const r = await API.post("/api/workflows/init");
          toast(t("toast.workflowsInit", { n: r.created }));
        }).catch((err) => {
          if (err) toast(err.message);
        });
        break;
      case "autodetect-paths":
        await withBtnBusy(btn, async () => {
          const p = await API.get("/api/settings/paths/default");
          const form = $("#form-settings");
          form.project_root.value = p.project_root;
          form.art_pipeline_root.value = p.art_pipeline_root;
          if (p.log_dir && form.log_dir) form.log_dir.value = p.log_dir;
        }).catch((err) => {
          if (err) toast(err.message);
        });
        break;
      case "open-log-dir":
        await withBtnBusy(btn, async () => {
          const data = await API.get("/api/settings");
          const dir = (formSettingsLogDir() || data.log_dir_effective || "").trim();
          if (!dir) {
            toast(t("toast.logDirMissing"), { variant: "error" });
            return;
          }
          await openPath(dir);
        }).catch((err) => {
          if (err) toast(err.message);
        });
        break;
      default:
        break;
    }
  });
}

async function trySelectAssetFromUrl() {
  const id = new URLSearchParams(location.search).get("asset");
  if (!id) return false;
  try {
    const asset = await API.get(`/api/assets/${id}`);
    await selectCategory(asset.category);
    await selectAsset(id);
    return true;
  } catch {
    return false;
  }
}

async function bootstrap(pickFirst = true) {
  const useSplash = !appBooted;
  if (!useSplash) showGlobalOverlay(t("splash.reloading"));
  try {
    await initI18n();
    applyDomI18n();
    bindLangSwitcher();
    onLangChange(() => refreshI18nUi());
    await API.get("/api/health");
    const data = await API.get("/api/categories");
    state.categories = data.categories || [];
    fillCategorySelect();
    renderCategories();
    await loadCheckpoints();
    const fromUrl = await trySelectAssetFromUrl();
    if (!fromUrl && pickFirst && state.categories.length && !state.categoryId) {
      await selectCategory(state.categories[0].id);
    } else if (state.categoryId) {
      await loadAssetList();
    }
    refreshComfy();
    if (!appBooted) setInterval(refreshComfy, 30000);
    try {
      const j = await API.get("/api/jobs/status");
      if (j.busy) {
        state.jobRunId = j.run_id ?? null;
        state.jobTrack = { active: true, sawBusy: true, postOk: true };
        resetJobProg(j.kind || "");
        updateJobFromApi(j);
        startJobPoll();
      }
    } catch {
      /* ignore */
    }
    const activeTab = $("#main-tabs .tab.active")?.dataset.tab;
    updateMainTabsVisibility();
    const visibleTab = $(`#main-tabs .tab[data-tab="${activeTab}"]:not([hidden])`);
    switchTab(visibleTab?.dataset.tab || (categoryHasAssets() ? "ai" : "category"));
  } catch (err) {
    toast(t("toast.backendFailed", { msg: err.message }));
  } finally {
    if (useSplash) await hideSplash(document.getElementById("app-splash"));
    else hideGlobalOverlay();
    appBooted = true;
  }
}

document.body.classList.add("is-booting");
bindUi();
connectLogs();
bootstrap();
