/**
 * 后处理编辑器 · Web（对标 postprocess_editor.py）
 * 服务端 PIL 渲染 + 浏览器交互（拖拽 / 裁切 / 图层管理）
 */
import { API } from "./api.js";
import { icon, layerTypeIcon } from "./icons.js";
import {
  initI18n,
  t,
  applyDomI18n,
  bindLangSwitcher,
  onLangChange,
} from "./i18n.js";
import { bindRipple, hideGlobalOverlay, showGlobalOverlay, withBtnBusy } from "./effects.js";

const params = new URLSearchParams(location.search);
const assetId = params.get("asset");

const $ = (s) => document.querySelector(s);

const view = {
  zoom: 1,
  panX: 0,
  panY: 0,
  minZoom: 0.25,
  maxZoom: 6,
};

let stack = null;
let assetInfo = null;
let assetPaths = null;
let selectedId = null;
let soloId = null;
let boundsData = { layers: [], canvas: { width: 512, height: 512 }, raw_sizes: {} };
let previewTimer = null;
let previewBusy = false;
let previewQueued = false;
let previewReq = 0;
let previewBlobUrl = null;

let drag = null;
let cropMode = false;
let matteMode = false;
let matteBusy = false;
let cropPreview = null;
let cropDrag = null;
let cropRawImg = null;
let cropRawSize = { w: 0, h: 0 };

const CROP_HANDLE = 9;
const HISTORY_MAX = 10;

const ppHistory = {
  past: [],
  future: [],
  recording: false,
  busy: false,
};
let propsHistoryArmed = true;

function cloneStackData(s) {
  return JSON.parse(JSON.stringify(s));
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error("read failed"));
        return;
      }
      resolve(result.includes(",") ? result.split(",")[1] : result);
    };
    reader.onerror = () => reject(reader.error || new Error("read failed"));
    reader.readAsDataURL(blob);
  });
}

async function fetchLayerRawBase64(layerId) {
  applyPropsFromForm();
  try {
    const res = await fetch(
      `/api/assets/${encodeURIComponent(assetId)}/postprocess/layer-raw`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ layer_id: layerId, stack }),
      },
    );
    if (!res.ok) return null;
    return blobToBase64(await res.blob());
  } catch {
    return null;
  }
}

async function createHistoryEntry({ includeImages = false } = {}) {
  applyPropsFromForm();
  const entry = {
    stack: cloneStackData(stack),
    selectedId,
    soloId,
    images: {},
  };
  if (!includeImages) return entry;
  for (const layer of stack.layers || []) {
    if (layer.type !== "image") continue;
    const b64 = await fetchLayerRawBase64(layer.id);
    if (b64) entry.images[layer.id] = b64;
  }
  return entry;
}

async function restoreHistoryEntry(entry) {
  ppHistory.recording = true;
  try {
    stack = cloneStackData(entry.stack);
    selectedId = entry.selectedId ?? selectedId;
    soloId = entry.soloId ?? null;
    const solo = $("#pp-solo");
    if (solo) solo.checked = !!soloId;
    for (const [layerId, b64] of Object.entries(entry.images || {})) {
      if (!b64) continue;
      await API.post(`/api/assets/${encodeURIComponent(assetId)}/postprocess/layer-restore-image`, {
        layer_id: layerId,
        image_b64: b64,
        stack,
      });
    }
    renderLayers();
    fillProps();
    await fetchBounds();
    await refreshPreview();
    drawOverlay();
  } finally {
    ppHistory.recording = false;
  }
}

function updateHistoryButtons() {
  const undoBtn = $("#pp-undo");
  const redoBtn = $("#pp-redo");
  const blocked = ppHistory.recording || ppHistory.busy;
  if (undoBtn) undoBtn.disabled = blocked || ppHistory.past.length === 0;
  if (redoBtn) redoBtn.disabled = blocked || ppHistory.future.length === 0;
}

function resetHistory() {
  ppHistory.past = [];
  ppHistory.future = [];
  propsHistoryArmed = true;
  updateHistoryButtons();
}

async function pushHistoryBefore({ includeImages = false } = {}) {
  if (ppHistory.recording || ppHistory.busy) return;
  ppHistory.busy = true;
  try {
    const entry = await createHistoryEntry({ includeImages });
    ppHistory.past.push(entry);
    if (ppHistory.past.length > HISTORY_MAX) ppHistory.past.shift();
    ppHistory.future = [];
    updateHistoryButtons();
  } finally {
    ppHistory.busy = false;
  }
}

function beginPropsHistoryBatch() {
  if (ppHistory.recording || !propsHistoryArmed) return;
  propsHistoryArmed = false;
  pushHistoryBefore({ includeImages: false }).finally(() => {
    window.setTimeout(() => {
      propsHistoryArmed = true;
    }, 1500);
  });
}

async function undoHistory() {
  if (ppHistory.recording || ppHistory.busy) return;
  if (!ppHistory.past.length) {
    setStatus(t("pp.historyNothing"));
    return;
  }
  ppHistory.busy = true;
  updateHistoryButtons();
  try {
    const current = await createHistoryEntry({ includeImages: true });
    ppHistory.future.push(current);
    const prev = ppHistory.past.pop();
    await restoreHistoryEntry(prev);
    setStatus(t("pp.historyRestored"));
  } catch (err) {
    setStatus(err.message);
  } finally {
    ppHistory.busy = false;
    updateHistoryButtons();
  }
}

async function redoHistory() {
  if (ppHistory.recording || ppHistory.busy || !ppHistory.future.length) return;
  ppHistory.busy = true;
  updateHistoryButtons();
  try {
    const current = await createHistoryEntry({ includeImages: true });
    ppHistory.past.push(current);
    if (ppHistory.past.length > HISTORY_MAX) ppHistory.past.shift();
    const next = ppHistory.future.pop();
    await restoreHistoryEntry(next);
    setStatus(t("pp.historyRestored"));
  } catch (err) {
    setStatus(err.message);
  } finally {
    ppHistory.busy = false;
    updateHistoryButtons();
  }
}

function bindHistoryControls() {
  $("#pp-undo")?.addEventListener("click", () => undoHistory());
  $("#pp-redo")?.addEventListener("click", () => redoHistory());
}

function setStatus(msg) {
  $("#pp-status").textContent = msg;
}

function selectedLayer() {
  return stack?.layers?.find((l) => l.id === selectedId) || null;
}

function subjectLayer() {
  return stack?.layers?.find((l) => l.is_subject || l.source === "$asset") || null;
}

function canvasSize() {
  return {
    w: stack?.canvas?.width || stack?.canvas_width || assetInfo?.width || 512,
    h: stack?.canvas?.height || stack?.canvas_height || assetInfo?.height || 512,
  };
}

function previewBody(extra = {}) {
  return { stack, solo_layer_id: soloId || undefined, ...extra };
}

function defaultTextStyle() {
  return {
    content: t("pp.defaultTextContent"),
    font_family: "PingFang SC",
    font_size: 40,
    color: "#FFFFFF",
    stroke_color: "#000000",
    stroke_width: 2,
    align: "center",
  };
}

function ensureFontOption(family) {
  const sel = $("#pp-fonts");
  if (!sel || !family) return;
  if ([...sel.options].some((o) => o.value === family)) return;
  const o = document.createElement("option");
  o.value = family;
  o.textContent = family;
  sel.appendChild(o);
}

function layerListSubtitle(layer) {
  if (layer.type === "text" && layer.text) {
    const snippet = (layer.text.content || "").trim().slice(0, 14) || t("pp.layerText");
    const font = (layer.text.font_family || "").trim();
    return font ? `${snippet} · ${font}` : snippet;
  }
  return `${layer.type}${layer.is_subject ? t("layer.subject") : ""}`;
}

function refreshActiveLayerRow() {
  const layer = selectedLayer();
  if (!layer) return;
  const row = document.querySelector(".layer-item.active");
  if (!row) {
    renderLayers();
    return;
  }
  const title = row.querySelector(".layer-title");
  const sub = row.querySelector(".layer-sub");
  if (title) title.textContent = layer.name || layer.id;
  if (sub) sub.textContent = layerListSubtitle(layer);
}

function onPropsFormChange() {
  beginPropsHistoryBatch();
  applyPropsFromForm();
  refreshActiveLayerRow();
  schedulePreview(220);
}

function applyPropsFromForm() {
  const layer = selectedLayer();
  if (!layer) return;
  const form = $("#pp-props-form");
  layer.name = form.name.value.trim() || layer.name;
  if (form.opacity_slider) {
    const pct = Math.min(100, Math.max(0, parseInt(form.opacity_slider.value, 10) || 0));
    layer.opacity = pct / 100;
    form.opacity.value = pct === 100 ? 1 : pct / 100;
  } else {
    const o = parseFloat(form.opacity.value);
    layer.opacity = Number.isFinite(o) ? Math.min(1, Math.max(0, o)) : 1;
  }
  layer.transform = layer.transform || { anchor: "center" };
  layer.transform.offset_x = parseFloat(form.offset_x.value) || 0;
  layer.transform.offset_y = parseFloat(form.offset_y.value) || 0;
  if (form.scale_slider) {
    const pct = parseInt(form.scale_slider.value, 10) || 100;
    layer.transform.scale = pct / 100;
    form.scale_pct.value = pct;
    const tag = $("#scale-tag");
    if (tag) tag.textContent = `${pct}%`;
  } else {
    layer.transform.scale = (parseFloat(form.scale_pct.value) || 100) / 100;
  }
  if (layer.type === "image") {
    layer.source = form.source?.value?.trim() ?? layer.source;
    if (layer.is_subject) layer.source = "$asset";
    const cx = parseInt(form.crop_x?.value, 10);
    const cy = parseInt(form.crop_y?.value, 10);
    const cw = parseInt(form.crop_w?.value, 10);
    const ch = parseInt(form.crop_h?.value, 10);
    if (cw > 0 && ch > 0 && !Number.isNaN(cx) && !Number.isNaN(cy)) {
      layer.crop = { x: cx, y: cy, w: cw, h: ch };
    }
  }
  if (layer.type === "text") {
    layer.text = layer.text || defaultTextStyle();
    layer.text.content = form.text_content.value;
    layer.text.font_size = parseInt(form.font_size.value, 10) || 24;
    layer.text.color = form.text_color.value || "#FFFFFF";
    const family = form.font_family?.value?.trim();
    if (family) layer.text.font_family = family;
  }
}

function fillProps() {
  const layer = selectedLayer();
  const form = $("#pp-props-form");
  const imgFs = $("#pp-image-fields");
  const txtFs = $("#pp-text-fields");
  const cropFs = $("#pp-crop-fields");
  if (!layer) {
    form.querySelectorAll("input,textarea,select").forEach((el) => {
      if (el.name) el.disabled = true;
    });
    return;
  }
  form.querySelectorAll("input,textarea,select").forEach((el) => {
    el.disabled = false;
  });
  form.name.value = layer.name || "";
  const opPct = Math.min(100, Math.max(0, Math.round((layer.opacity ?? 1) * 100)));
  form.opacity.value = opPct === 100 ? 1 : opPct / 100;
  if (form.opacity_slider) form.opacity_slider.value = opPct;
  const xf = layer.transform || {};
  form.offset_x.value = xf.offset_x ?? 0;
  form.offset_y.value = xf.offset_y ?? 0;
  const scalePct = Math.round((xf.scale ?? 1) * 100);
  form.scale_pct.value = scalePct;
  if (form.scale_slider) form.scale_slider.value = Math.min(300, Math.max(5, scalePct));
  const tag = $("#scale-tag");
  if (tag) tag.textContent = `${scalePct}%`;

  const isImg = layer.type === "image";
  const isText = layer.type === "text";
  imgFs.hidden = !isImg;
  txtFs.hidden = !isText;
  cropFs.hidden = !isImg || !(layer.is_subject || layer.source === "$asset");
  if (isImg && form.source) {
    form.source.value = layer.is_subject ? "$asset" : layer.source || "";
    form.source.readOnly = layer.is_subject;
  }
  const browse = $("#pp-browse-source");
  if (browse) browse.disabled = !isImg || !!layer.is_subject;
  if (isImg && layer.crop) {
    form.crop_x.value = layer.crop.x ?? 0;
    form.crop_y.value = layer.crop.y ?? 0;
    form.crop_w.value = layer.crop.w ?? 0;
    form.crop_h.value = layer.crop.h ?? 0;
  } else if (form.crop_x) {
    form.crop_x.value = form.crop_y.value = form.crop_w.value = form.crop_h.value = "";
  }
  if (isText) {
    layer.text = layer.text || defaultTextStyle();
    ensureFontOption(layer.text.font_family);
    form.text_content.value = layer.text.content || "";
    form.font_size.value = layer.text.font_size || 40;
    form.text_color.value = layer.text.color || "#ffffff";
    form.font_family.value = layer.text.font_family || "PingFang SC";
  }
  $("#pp-crop-toggle").disabled = !(layer.is_subject || layer.source === "$asset") || layer.type !== "image";
  const matteToggle = $("#pp-matte-toggle");
  if (matteToggle) matteToggle.disabled = !isImg || !!layer.locked;
  const matteBorder = $("#pp-matte-border");
  const matteWand = $("#pp-matte-wand");
  if (matteBorder) matteBorder.disabled = !isImg || !!layer.locked;
  if (matteWand) matteWand.disabled = !isImg || !!layer.locked;
}

function layerActionBar(layer) {
  const isSubject = layer.is_subject;
  return `
    <div class="layer-actions">
      <button type="button" class="icon-btn" data-act="up" title="${escapeHtml(t("pp.moveUp"))}">${icon("chevronUp")}</button>
      <button type="button" class="icon-btn" data-act="down" title="${escapeHtml(t("pp.moveDown"))}">${icon("chevronDown")}</button>
      <button type="button" class="icon-btn" data-act="dup" title="${escapeHtml(t("pp.duplicate"))}" ${isSubject ? "disabled" : ""}>${icon("copy")}</button>
      <button type="button" class="icon-btn danger" data-act="del" title="${escapeHtml(t("pp.delete"))}" ${isSubject ? "disabled" : ""}>${icon("trash")}</button>
    </div>`;
}

function renderLayers() {
  const box = $("#pp-layer-list");
  box.innerHTML = "";
  for (const layer of [...(stack?.layers || [])].reverse()) {
    const isActive = layer.id === selectedId;
    const visible = layer.visible !== false;
    const locked = !!layer.locked;
    const row = document.createElement("div");
    row.className = "layer-item" + (isActive ? " active" : "") + (soloId === layer.id ? " solo" : "");
    if (!visible) row.classList.add("layer-hidden");
    if (locked) row.classList.add("layer-locked");

    row.innerHTML = `
      <div class="layer-row">
        <button type="button" class="layer-main" data-id="${layer.id}">
          <span class="layer-type-icon">${layerTypeIcon(layer)}</span>
          <span class="layer-name">
            <span class="layer-title">${escapeHtml(layer.name || layer.id)}</span>
            <span class="layer-sub">${escapeHtml(layerListSubtitle(layer))}</span>
          </span>
        </button>
        <div class="layer-quick">
          <button type="button" class="icon-btn ${visible ? "" : "off"}" data-act="vis" data-id="${layer.id}" title="${escapeHtml(visible ? t("pp.hide") : t("pp.show"))}">${icon(visible ? "eye" : "eyeOff")}</button>
          <button type="button" class="icon-btn ${locked ? "on" : ""}" data-act="lock" data-id="${layer.id}" title="${escapeHtml(locked ? t("pp.unlock") : t("pp.lock"))}">${icon(locked ? "lock" : "unlock")}</button>
        </div>
      </div>
      ${isActive ? layerActionBar(layer) : ""}`;

    row.querySelector(".layer-main")?.addEventListener("click", (e) => {
      if (e.altKey) {
        soloId = layer.id;
        $("#pp-solo").checked = true;
      }
      selectLayer(layer.id);
    });
    row.querySelector(".layer-main")?.addEventListener("dblclick", (e) => {
      e.preventDefault();
      selectLayer(layer.id);
      zoomFit();
    });

    row.querySelectorAll(".icon-btn[data-act]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        handleLayerAction(btn.dataset.act, layer.id);
      });
    });

    box.appendChild(row);
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function handleLayerAction(act, layerId) {
  const layer = stack.layers.find((l) => l.id === layerId);
  if (!layer) return;
  if (act === "vis") {
    pushHistoryBefore({ includeImages: false }).then(() => {
      layer.visible = !(layer.visible !== false);
      renderLayers();
      schedulePreview();
    });
    return;
  }
  if (act === "lock") {
    layer.locked = !layer.locked;
    renderLayers();
    fillProps();
    return;
  }
  if (layerId !== selectedId) selectLayer(layerId);
  if (act === "up") moveLayer(1);
  else if (act === "down") moveLayer(-1);
  else if (act === "dup") duplicateLayer();
  else if (act === "del") deleteLayer();
}

function bindRangeSync() {
  const form = $("#pp-props-form");
  form.scale_slider?.addEventListener("input", () => {
    form.scale_pct.value = form.scale_slider.value;
    const tag = $("#scale-tag");
    if (tag) tag.textContent = `${form.scale_slider.value}%`;
    schedulePreview(120);
  });
  form.scale_pct?.addEventListener("input", () => {
    let v = parseInt(form.scale_pct.value, 10) || 100;
    v = Math.min(800, Math.max(1, v));
    form.scale_slider.value = Math.min(300, v);
    const tag = $("#scale-tag");
    if (tag) tag.textContent = `${v}%`;
    schedulePreview(120);
  });
  form.opacity_slider?.addEventListener("input", () => {
    const pct = Math.min(100, Math.max(0, parseInt(form.opacity_slider.value, 10) || 0));
    form.opacity.value = pct === 100 ? 1 : pct / 100;
    schedulePreview(120);
  });
  form.opacity?.addEventListener("input", () => {
    const o = parseFloat(form.opacity.value);
    const pct = Number.isFinite(o) ? Math.round(Math.min(1, Math.max(0, o)) * 100) : 100;
    if (form.opacity_slider) form.opacity_slider.value = pct;
    schedulePreview(120);
  });
}

function initToolbarIcons() {
  const imgBtn = $("#pp-add-image")?.querySelector(".btn-icon");
  const txtBtn = $("#pp-add-text")?.querySelector(".btn-icon");
  if (imgBtn) imgBtn.innerHTML = icon("image", 14);
  if (txtBtn) txtBtn.innerHTML = icon("type", 14);
}

function selectLayer(id) {
  selectedId = id;
  renderLayers();
  fillProps();
  schedulePreview();
  drawOverlay();
}

let ppFileInput = null;

function ensureFileInput() {
  if (ppFileInput) return ppFileInput;
  ppFileInput = document.createElement("input");
  ppFileInput.type = "file";
  ppFileInput.accept = "image/png,image/jpeg,image/webp,image/gif,image/*";
  ppFileInput.hidden = true;
  document.body.appendChild(ppFileInput);
  return ppFileInput;
}

function pickImageViaInput() {
  return new Promise((resolve) => {
    const input = ensureFileInput();
    const onChange = async () => {
      input.removeEventListener("change", onChange);
      const file = input.files?.[0];
      input.value = "";
      if (!file) {
        resolve(null);
        return;
      }
      try {
        const fd = new FormData();
        fd.append("file", file);
        const res = await fetch("/api/postprocess/upload-image", {
          method: "POST",
          body: fd,
          headers: { Accept: "application/json" },
        });
        if (!res.ok) {
          const msg = (await res.text()).slice(0, 200) || res.statusText;
          throw new Error(msg);
        }
        const data = await res.json();
        resolve(data.path || null);
      } catch (err) {
        setStatus(err.message || t("pp.pickImageFailed"));
        resolve(null);
      }
    };
    input.addEventListener("change", onChange);
    input.click();
  });
}

function pickImageInitialDir() {
  const inbox = assetPaths?.inbox;
  if (!inbox) return undefined;
  const i = inbox.lastIndexOf("/");
  return i > 0 ? inbox.slice(0, i) : undefined;
}

async function pickImageFile() {
  try {
    const r = await API.post("/api/pick-image-file", {
      initial_dir: pickImageInitialDir(),
    });
    if (r.cancelled) return null;
    return r.path || null;
  } catch {
    return pickImageViaInput();
  }
}

function layerNameFromPath(path) {
  const base = path.split("/").pop() || "";
  const dot = base.lastIndexOf(".");
  return dot > 0 ? base.slice(0, dot) : base || t("pp.layerImage");
}

async function browseImageSource() {
  const layer = selectedLayer();
  if (!layer || layer.type !== "image" || layer.is_subject) return;
  const path = await pickImageFile();
  if (!path) return;
  await pushHistoryBefore({ includeImages: true });
  layer.source = path;
  if (!layer.name || layer.name === t("pp.layerImage")) {
    layer.name = layerNameFromPath(path);
  }
  renderLayers();
  fillProps();
  schedulePreview();
}

function schedulePreview(delay = 180) {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(refreshPreview, delay);
}

function revokePreviewBlob() {
  if (previewBlobUrl) {
    URL.revokeObjectURL(previewBlobUrl);
    previewBlobUrl = null;
  }
}

function showPreviewEmpty(message = null) {
  const msg = message ?? t("pp.noPreview");
  const img = $("#pp-preview");
  const ph = $("#pp-preview-ph");
  revokePreviewBlob();
  img.hidden = true;
  img.removeAttribute("src");
  if (ph) {
    ph.hidden = false;
    ph.textContent = msg;
  }
}

function showPreviewLoading(message = null) {
  const msg = message ?? t("pp.loadingPreview");
  const img = $("#pp-preview");
  const ph = $("#pp-preview-ph");
  const hasImage = previewBlobUrl && !img.hidden;
  if (!hasImage) {
    revokePreviewBlob();
    img.hidden = true;
    img.removeAttribute("src");
    if (ph) {
      ph.hidden = false;
      ph.textContent = msg;
    }
  } else if (ph) {
    ph.hidden = true;
  }
}

async function setPreviewBlob(blob) {
  const img = $("#pp-preview");
  const ph = $("#pp-preview-ph");
  if (!blob.type.startsWith("image/")) {
    showPreviewEmpty(t("pp.noPreview"));
    return false;
  }
  try {
    if (typeof createImageBitmap === "function") {
      const bmp = await createImageBitmap(blob);
      bmp.close();
    } else {
      await new Promise((resolve, reject) => {
        const probe = new Image();
        const url = URL.createObjectURL(blob);
        probe.onload = () => {
          URL.revokeObjectURL(url);
          resolve();
        };
        probe.onerror = () => {
          URL.revokeObjectURL(url);
          reject(new Error("decode"));
        };
        probe.src = url;
      });
    }
  } catch {
    showPreviewEmpty(t("pp.noPreview"));
    return false;
  }
  revokePreviewBlob();
  previewBlobUrl = URL.createObjectURL(blob);
  img.src = previewBlobUrl;
  img.hidden = false;
  if (ph) ph.hidden = true;
  return true;
}

async function fetchBounds() {
  try {
    boundsData = await API.post(`/api/assets/${assetId}/postprocess/bounds`, previewBody());
  } catch {
    boundsData = { layers: [], canvas: canvasSize(), raw_sizes: {} };
  }
}

async function refreshPreview() {
  if (previewBusy) {
    previewQueued = true;
    return;
  }
  previewBusy = true;
  applyPropsFromForm();
  const reqId = ++previewReq;
  showPreviewLoading(t("pp.rendering"));
  setStatus(t("pp.rendering"));
  try {
    const res = await fetch(`/api/assets/${encodeURIComponent(assetId)}/postprocess/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(previewBody()),
    });
    if (reqId !== previewReq) return;

    if (!res.ok) {
      showPreviewEmpty(t("pp.noPreviewFile"));
      setStatus(t("pp.noPreviewFile"));
      return;
    }
    const blob = await res.blob();
    if (reqId !== previewReq) return;

    const ok = await setPreviewBlob(blob);
    if (reqId !== previewReq) return;
    if (!ok) {
      setStatus(t("pp.noPreview"));
      return;
    }
    await fetchBounds();
    layoutPreview();
    drawOverlay();
    setStatus(t("pp.ready"));
  } catch (err) {
    if (reqId !== previewReq) return;
    showPreviewEmpty(t("pp.noPreview"));
    setStatus(t("pp.previewFailed", { msg: err.message }));
  } finally {
    previewBusy = false;
    if (previewQueued) {
      previewQueued = false;
      schedulePreview(50);
    }
  }
}

function viewportOffset() {
  const vp = $("#pp-viewport");
  const { w, h } = canvasSize();
  const docW = w * view.zoom;
  const docH = h * view.zoom;
  return {
    ox: (vp.clientWidth - docW) / 2 + view.panX,
    oy: (vp.clientHeight - docH) / 2 + view.panY,
    docW,
    docH,
  };
}

function canvasToDoc(cx, cy) {
  const vp = $("#pp-viewport");
  const rect = vp.getBoundingClientRect();
  const { ox, oy } = viewportOffset();
  return { x: (cx - rect.left - ox) / view.zoom, y: (cy - rect.top - oy) / view.zoom };
}

function layoutPreview() {
  const img = $("#pp-preview");
  if (img.hidden || !previewBlobUrl) return;
  const { w, h } = canvasSize();
  const { ox, oy, docW, docH } = viewportOffset();
  img.style.width = `${docW}px`;
  img.style.height = `${docH}px`;
  img.style.left = `${ox}px`;
  img.style.top = `${oy}px`;
  const canvas = $("#pp-overlay");
  canvas.width = $("#pp-viewport").clientWidth;
  canvas.height = $("#pp-viewport").clientHeight;
  $("#pp-zoom-label").textContent = `${Math.round(view.zoom * 100)}%`;
}

function drawOverlay() {
  const canvas = $("#pp-overlay");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const { ox, oy } = viewportOffset();
  const z = view.zoom;
  for (const b of boundsData.layers || []) {
    if (soloId && b.id !== soloId) continue;
    const x0 = ox + b.x * z;
    const y0 = oy + b.y * z;
    const x1 = ox + (b.x + b.w) * z;
    const y1 = oy + (b.y + b.h) * z;
    ctx.strokeStyle = b.id === selectedId ? "#00aaff" : "#666";
    ctx.setLineDash([4, 3]);
    ctx.lineWidth = 1.5;
    ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
  }
  ctx.setLineDash([]);
}

function hitTestLayer(docX, docY) {
  const layers = [...(boundsData.layers || [])].reverse();
  for (const b of layers) {
    if (!b.visible || b.locked) continue;
    if (docX >= b.x && docX < b.x + b.w && docY >= b.y && docY < b.y + b.h) {
      return stack.layers.find((l) => l.id === b.id);
    }
  }
  return null;
}

function zoomBy(factor) {
  view.zoom = Math.max(view.minZoom, Math.min(view.maxZoom, view.zoom * factor));
  layoutPreview();
  drawOverlay();
}

function zoomFit() {
  const vp = $("#pp-viewport");
  const { w, h } = canvasSize();
  const zx = vp.clientWidth / Math.max(w, 1);
  const zy = vp.clientHeight / Math.max(h, 1);
  view.zoom = Math.max(view.minZoom, Math.min(view.maxZoom, Math.min(zx, zy) * 0.92));
  view.panX = view.panY = 0;
  layoutPreview();
  drawOverlay();
}

function readMatteSettings() {
  const tol = parseInt($("#pp-matte-tol-num")?.value || $("#pp-matte-tol")?.value || "34", 10);
  return {
    color_tol: Math.max(8, Math.min(80, tol || 34)),
    step_tol: 16,
    feather: 0,
  };
}

function syncMatteToleranceFromRange() {
  const range = $("#pp-matte-tol");
  const num = $("#pp-matte-tol-num");
  if (range && num) num.value = range.value;
}

function syncMatteToleranceFromNumber() {
  const range = $("#pp-matte-tol");
  const num = $("#pp-matte-tol-num");
  if (!range || !num) return;
  let v = parseInt(num.value, 10);
  if (Number.isNaN(v)) v = 34;
  v = Math.max(8, Math.min(80, v));
  num.value = v;
  range.value = v;
}

function docToRawPixel(layer, docX, docY) {
  const b = (boundsData.layers || []).find((x) => x.id === layer.id);
  const raw = boundsData.raw_sizes?.[layer.id];
  if (!b || !raw?.w || !raw?.h) return null;
  if (docX < b.x || docX >= b.x + b.w || docY < b.y || docY >= b.y + b.h) return null;
  const relX = (docX - b.x) / b.w;
  const relY = (docY - b.y) / b.h;
  const crop = layer.crop;
  let rawX;
  let rawY;
  if (crop?.w > 0 && crop?.h > 0) {
    rawX = crop.x + relX * crop.w;
    rawY = crop.y + relY * crop.h;
  } else {
    rawX = relX * raw.w;
    rawY = relY * raw.h;
  }
  return {
    x: Math.max(0, Math.min(raw.w - 1, Math.round(rawX))),
    y: Math.max(0, Math.min(raw.h - 1, Math.round(rawY))),
  };
}

async function callLayerMatte(payload) {
  applyPropsFromForm();
  return API.post(`/api/assets/${encodeURIComponent(assetId)}/postprocess/layer-matte`, {
    ...payload,
    stack,
  });
}

async function applyBorderMatte(btn) {
  const layer = selectedLayer();
  if (!layer || layer.type !== "image") {
    setStatus(t("pp.matteNeedImage"));
    return;
  }
  if (layer.locked) return;
  const settings = readMatteSettings();
  await withBtnBusy(btn || $("#pp-matte-border"), async () => {
    await pushHistoryBefore({ includeImages: true });
    await callLayerMatte({
      layer_id: layer.id,
      mode: "border",
      ...settings,
    });
    setStatus(t("pp.matteBorderDone"));
    await fetchBounds();
    await refreshPreview();
  }).catch((err) => {
    if (err) setStatus(err.message);
  });
}

async function applySeedMatte(docX, docY, layer) {
  if (!layer || layer.type !== "image" || layer.locked || matteBusy) return;
  const px = docToRawPixel(layer, docX, docY);
  if (!px) return;
  matteBusy = true;
  setStatus(t("pp.matteSeedWorking"));
  try {
    await pushHistoryBefore({ includeImages: true });
    await callLayerMatte({
      layer_id: layer.id,
      mode: "seed",
      seed_x: px.x,
      seed_y: px.y,
      ...readMatteSettings(),
    });
    setStatus(t("pp.matteSeedDone"));
    await fetchBounds();
    await refreshPreview();
  } catch (err) {
    setStatus(err.message);
  } finally {
    matteBusy = false;
  }
}

function updateMatteModeUi() {
  const vp = $("#pp-viewport");
  const banner = $("#pp-matte-banner");
  const toggle = $("#pp-matte-toggle");
  const wandBtn = $("#pp-matte-wand");
  vp?.classList.toggle("pp-matte-mode", matteMode);
  banner?.classList.toggle("hidden", !matteMode);
  toggle?.classList.toggle("active", matteMode);
  if (toggle) toggle.textContent = matteMode ? t("pp.matteDone") : t("pp.matteWandShort");
  if (wandBtn) wandBtn.textContent = matteMode ? t("pp.matteDone") : t("pp.matteWand");
}

function enterMatteMode() {
  if (cropMode) exitCropMode();
  const layer = selectedLayer();
  if (!layer || layer.type !== "image") {
    setStatus(t("pp.matteNeedImage"));
    return;
  }
  matteMode = true;
  updateMatteModeUi();
  setStatus(t("pp.matteModeHint"));
}

function exitMatteMode() {
  if (!matteMode) return;
  matteMode = false;
  updateMatteModeUi();
  setStatus(t("pp.ready"));
}

function toggleMatteMode() {
  if (matteMode) exitMatteMode();
  else enterMatteMode();
}

function bindMatteControls() {
  $("#pp-matte-tol")?.addEventListener("input", syncMatteToleranceFromRange);
  $("#pp-matte-tol-num")?.addEventListener("change", syncMatteToleranceFromNumber);
  $("#pp-matte-border")?.addEventListener("click", (e) => applyBorderMatte(e.currentTarget));
  $("#pp-matte-wand")?.addEventListener("click", () => toggleMatteMode());
  $("#pp-matte-toggle")?.addEventListener("click", () => toggleMatteMode());
}

// ── 裁切（1:1 原图面板） ─────────────────────────────

async function enterCropMode() {
  exitMatteMode();
  const layer = selectedLayer();
  if (!layer || layer.type !== "image" || !(layer.is_subject || layer.source === "$asset")) return;
  try {
    const res = await fetch(`/api/assets/${encodeURIComponent(assetId)}/postprocess/subject-raw.png`);
    if (!res.ok) throw new Error("无主体原图");
    const blob = await res.blob();
    cropRawImg = await createImageBitmap(blob);
    cropRawSize = { w: cropRawImg.width, h: cropRawImg.height };
  } catch (err) {
    setStatus(err.message);
    return;
  }
  cropMode = true;
  if (layer.crop?.w > 0 && layer.crop?.h > 0) {
    cropPreview = { ...layer.crop };
  } else {
    const side = Math.min(cropRawSize.w, cropRawSize.h);
    cropPreview = {
      x: Math.floor((cropRawSize.w - side) / 2),
      y: Math.floor((cropRawSize.h - side) / 2),
      w: side,
      h: side,
    };
  }
  $("#pp-crop-panel").classList.remove("hidden");
  $("#pp-viewport").classList.add("hidden");
  $("#pp-crop-toggle").textContent = t("pp.cropDone");
  drawCropCanvas();
  updateCropInfo();
}

function exitCropMode() {
  cropMode = false;
  cropPreview = null;
  cropDrag = null;
  $("#pp-crop-panel").classList.add("hidden");
  $("#pp-viewport").classList.remove("hidden");
  $("#pp-crop-toggle").textContent = t("pp.crop");
  if (cropRawImg) {
    cropRawImg.close?.();
    cropRawImg = null;
  }
}

function getCropCanvasScale() {
  const canvas = $("#pp-crop-canvas");
  return canvas.width / cropRawSize.w;
}

function cropEventPos(e) {
  const canvas = $("#pp-crop-canvas");
  const rect = canvas.getBoundingClientRect();
  const cx = e.clientX - rect.left;
  const cy = e.clientY - rect.top;
  const scale = getCropCanvasScale();
  return { cx, cy, rx: cx / scale, ry: cy / scale, scale };
}

function clampCrop(c) {
  const rw = cropRawSize.w;
  const rh = cropRawSize.h;
  let x = Math.round(c.x);
  let y = Math.round(c.y);
  let w = Math.round(c.w);
  let h = Math.round(c.h);
  if (w < 1) w = 1;
  if (h < 1) h = 1;
  if (x < 0) {
    w += x;
    x = 0;
  }
  if (y < 0) {
    h += y;
    y = 0;
  }
  if (x + w > rw) w = rw - x;
  if (y + h > rh) h = rh - y;
  if (w < 1) w = 1;
  if (h < 1) h = 1;
  return { x, y, w, h };
}

function cropRectCanvas() {
  if (!cropPreview) return null;
  const s = getCropCanvasScale();
  return {
    x: cropPreview.x * s,
    y: cropPreview.y * s,
    w: cropPreview.w * s,
    h: cropPreview.h * s,
    x2: (cropPreview.x + cropPreview.w) * s,
    y2: (cropPreview.y + cropPreview.h) * s,
  };
}

function hitTestCrop(cx, cy) {
  const r = cropRectCanvas();
  if (!r || r.w < 2 || r.h < 2) return { type: "create" };
  const H = CROP_HANDLE;
  const near = (a, b) => Math.abs(a - b) <= H;
  const onCorner = (hx, hy) => near(cx, hx) && near(cy, hy);

  if (onCorner(r.x, r.y)) return { type: "resize", handle: "nw" };
  if (onCorner(r.x2, r.y)) return { type: "resize", handle: "ne" };
  if (onCorner(r.x, r.y2)) return { type: "resize", handle: "sw" };
  if (onCorner(r.x2, r.y2)) return { type: "resize", handle: "se" };

  if (near(cx, r.x) && cy >= r.y && cy <= r.y2) return { type: "resize", handle: "w" };
  if (near(cx, r.x2) && cy >= r.y && cy <= r.y2) return { type: "resize", handle: "e" };
  if (near(cy, r.y) && cx >= r.x && cx <= r.x2) return { type: "resize", handle: "n" };
  if (near(cy, r.y2) && cx >= r.x && cx <= r.x2) return { type: "resize", handle: "s" };

  if (cx >= r.x && cx <= r.x2 && cy >= r.y && cy <= r.y2) return { type: "move" };
  return { type: "create" };
}

function cropCursorForHit(hit) {
  if (hit.type === "move") return "move";
  if (hit.type === "resize") {
    const map = {
      nw: "nwse-resize",
      se: "nwse-resize",
      ne: "nesw-resize",
      sw: "nesw-resize",
      n: "ns-resize",
      s: "ns-resize",
      e: "ew-resize",
      w: "ew-resize",
    };
    return map[hit.handle] || "crosshair";
  }
  return "crosshair";
}

function applyCropResize(orig, handle, rx, ry, square) {
  let x = orig.x;
  let y = orig.y;
  let x2 = orig.x + orig.w;
  let y2 = orig.y + orig.h;

  if (handle.includes("w")) x = rx;
  if (handle.includes("e")) x2 = rx;
  if (handle.includes("n")) y = ry;
  if (handle.includes("s")) y2 = ry;

  if (square) {
    const w = x2 - x;
    const h = y2 - y;
    const side = Math.max(Math.abs(w), Math.abs(h));
    const sx = w < 0 ? -1 : 1;
    const sy = h < 0 ? -1 : 1;
    if (handle.includes("w")) x = x2 - sx * side;
    else x2 = x + sx * side;
    if (handle.includes("n")) y = y2 - sy * side;
    else y2 = y + sy * side;
  }

  let nx = Math.min(x, x2);
  let ny = Math.min(y, y2);
  let nw = Math.max(1, Math.abs(x2 - x));
  let nh = Math.max(1, Math.abs(y2 - y));
  return clampCrop({ x: nx, y: ny, w: nw, h: nh });
}

function applyCropCreate(anchor, rx, ry, square) {
  let x = Math.min(anchor.x, rx);
  let y = Math.min(anchor.y, ry);
  let w = Math.max(1, Math.abs(rx - anchor.x));
  let h = Math.max(1, Math.abs(ry - anchor.y));
  if (square) {
    const side = Math.max(w, h);
    w = h = side;
    if (rx < anchor.x) x = anchor.x - side;
    if (ry < anchor.y) y = anchor.y - side;
  }
  return clampCrop({ x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) });
}

function drawCropCanvas() {
  const canvas = $("#pp-crop-canvas");
  if (!cropRawImg || !cropPreview) return;
  const maxW = canvas.parentElement.clientWidth - 24;
  const scale = Math.min(1, maxW / cropRawSize.w);
  canvas.width = Math.round(cropRawSize.w * scale);
  canvas.height = Math.round(cropRawSize.h * scale);
  const ctx = canvas.getContext("2d");
  ctx.drawImage(cropRawImg, 0, 0, canvas.width, canvas.height);
  const c = cropPreview;
  const sx = c.x * scale;
  const sy = c.y * scale;
  const sw = c.w * scale;
  const sh = c.h * scale;
  ctx.fillStyle = "rgba(0,0,0,0.48)";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.clearRect(sx, sy, sw, sh);
  ctx.drawImage(cropRawImg, c.x, c.y, c.w, c.h, sx, sy, sw, sh);
  ctx.strokeStyle = "#00c8ff";
  ctx.lineWidth = 2;
  ctx.setLineDash([6, 3]);
  ctx.strokeRect(sx + 0.5, sy + 0.5, sw - 1, sh - 1);
  ctx.setLineDash([]);

  const hs = 7;
  ctx.fillStyle = "#fff";
  ctx.strokeStyle = "#00c8ff";
  ctx.lineWidth = 1.5;
  const handles = [
    [sx, sy],
    [sx + sw, sy],
    [sx, sy + sh],
    [sx + sw, sy + sh],
    [sx + sw / 2, sy],
    [sx + sw / 2, sy + sh],
    [sx, sy + sh / 2],
    [sx + sw, sy + sh / 2],
  ];
  for (const [hx, hy] of handles) {
    ctx.fillRect(hx - hs / 2, hy - hs / 2, hs, hs);
    ctx.strokeRect(hx - hs / 2 + 0.5, hy - hs / 2 + 0.5, hs - 1, hs - 1);
  }

  const label = `${c.w} × ${c.h}`;
  ctx.font = "600 12px Inter, system-ui, sans-serif";
  const tw = ctx.measureText(label).width + 16;
  const lx = sx + sw / 2 - tw / 2;
  const ly = Math.max(4, sy - 26);
  ctx.fillStyle = "rgba(15, 17, 24, 0.9)";
  ctx.fillRect(lx, ly, tw, 20);
  ctx.fillStyle = "#e8eaef";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, sx + sw / 2, ly + 10);
}

function syncCropToForm() {
  if (!cropPreview) return;
  const form = $("#pp-props-form");
  if (!form.crop_x) return;
  form.crop_x.value = cropPreview.x;
  form.crop_y.value = cropPreview.y;
  form.crop_w.value = cropPreview.w;
  form.crop_h.value = cropPreview.h;
}

function updateCropInfo() {
  if (!cropPreview) return;
  const c = cropPreview;
  const text = `${c.w} × ${c.h} px · 位置 (${c.x}, ${c.y})`;
  $("#pp-crop-info").textContent = text;
  const badge = $("#pp-crop-size");
  if (badge) badge.textContent = `${c.w} × ${c.h} px`;
  syncCropToForm();
}

async function commitCrop() {
  const layer = selectedLayer();
  if (layer && cropPreview) {
    await pushHistoryBefore({ includeImages: false });
    layer.crop = clampCrop(cropPreview);
    fillProps();
    schedulePreview();
  }
  exitCropMode();
}

function cancelCropMode() {
  exitCropMode();
  setStatus(t("pp.cropCancelled"));
}

function bindCropCanvas() {
  const cropCanvas = $("#pp-crop-canvas");

  cropCanvas.addEventListener("contextmenu", (e) => {
    if (!cropMode) return;
    e.preventDefault();
    cancelCropMode();
  });

  cropCanvas.addEventListener("mousedown", (e) => {
    if (!cropMode || e.button !== 0) return;
    e.preventDefault();
    const { cx, cy, rx, ry } = cropEventPos(e);
    const hit = hitTestCrop(cx, cy);
    if (hit.type === "create") {
      cropDrag = { mode: "create", anchor: { x: rx, y: ry }, square: e.shiftKey };
      cropPreview = clampCrop({ x: Math.round(rx), y: Math.round(ry), w: 1, h: 1 });
    } else if (hit.type === "move") {
      cropDrag = { mode: "move", start: { x: rx, y: ry }, orig: { ...cropPreview } };
    } else {
      cropDrag = { mode: "resize", handle: hit.handle, orig: { ...cropPreview }, square: e.shiftKey };
    }
    drawCropCanvas();
    updateCropInfo();
  });

  cropCanvas.addEventListener("mousemove", (e) => {
    if (!cropMode) return;
    const { cx, cy, rx, ry } = cropEventPos(e);
    if (cropDrag) {
      if (cropDrag.mode === "create") {
        cropPreview = applyCropCreate(cropDrag.anchor, rx, ry, e.shiftKey || cropDrag.square);
      } else if (cropDrag.mode === "move") {
        const dx = rx - cropDrag.start.x;
        const dy = ry - cropDrag.start.y;
        cropPreview = clampCrop({
          x: cropDrag.orig.x + dx,
          y: cropDrag.orig.y + dy,
          w: cropDrag.orig.w,
          h: cropDrag.orig.h,
        });
      } else if (cropDrag.mode === "resize") {
        cropPreview = applyCropResize(
          cropDrag.orig,
          cropDrag.handle,
          rx,
          ry,
          e.shiftKey || cropDrag.square,
        );
      }
      drawCropCanvas();
      updateCropInfo();
    } else {
      cropCanvas.style.cursor = cropCursorForHit(hitTestCrop(cx, cy));
    }
  });

  cropCanvas.addEventListener("mouseup", (e) => {
    if (!cropMode || e.button !== 0) return;
    cropDrag = null;
  });

  cropCanvas.addEventListener("mouseleave", () => {
    if (!cropDrag) cropCanvas.style.cursor = "crosshair";
  });

  window.addEventListener("mouseup", (e) => {
    if (cropMode && cropDrag && e.button === 0) cropDrag = null;
  });
}

// ── 图层操作 ─────────────────────────────────────────────

async function addTextLayer() {
  await pushHistoryBefore({ includeImages: true });
  const id = "t_" + Math.random().toString(36).slice(2, 8);
  const textStyle = defaultTextStyle();
  ensureFontOption(textStyle.font_family);
  stack.layers.push({
    id,
    name: t("pp.layerText"),
    type: "text",
    visible: true,
    opacity: 1,
    transform: { offset_x: 0, offset_y: 0, scale: 1, anchor: "center" },
    text: textStyle,
  });
  selectLayer(id);
}

function addImageLayer() {
  pickImageFile().then(async (path) => {
    if (!path) return;
    await pushHistoryBefore({ includeImages: true });
    const id = "i_" + Math.random().toString(36).slice(2, 8);
    stack.layers.push({
      id,
      name: layerNameFromPath(path),
      type: "image",
      visible: true,
      opacity: 1,
      source: path,
      transform: { offset_x: 0, offset_y: 0, scale: 1, anchor: "center" },
    });
    selectLayer(id);
  });
}

async function moveLayer(delta) {
  const layer = selectedLayer();
  if (!layer) return;
  const idx = stack.layers.indexOf(layer);
  const ni = idx + delta;
  if (ni < 0 || ni >= stack.layers.length) return;
  await pushHistoryBefore({ includeImages: true });
  [stack.layers[idx], stack.layers[ni]] = [stack.layers[ni], stack.layers[idx]];
  renderLayers();
  schedulePreview();
}

async function duplicateLayer() {
  const layer = selectedLayer();
  if (!layer || layer.is_subject) return;
  await pushHistoryBefore({ includeImages: true });
  const clone = JSON.parse(JSON.stringify(layer));
  clone.id = (layer.type === "text" ? "t_" : "i_") + Math.random().toString(36).slice(2, 8);
  clone.name = `${layer.name}${t("pp.layerCopy")}`;
  clone.is_subject = false;
  stack.layers.push(clone);
  selectLayer(clone.id);
}

function adjustTextFontSize(delta) {
  const layer = selectedLayer();
  if (!layer || layer.type !== "text" || layer.locked) return false;
  beginPropsHistoryBatch();
  layer.text = layer.text || {};
  layer.text.font_size = Math.min(256, Math.max(8, (layer.text.font_size || 24) + delta));
  fillProps();
  schedulePreview(80);
  return true;
}

function focusTextContent() {
  const layer = selectedLayer();
  if (layer?.type !== "text") return false;
  const ta = $("#pp-props-form")?.elements?.text_content;
  if (!ta) return false;
  ta.focus();
  ta.select?.();
  return true;
}

function isPlusKey(e) {
  return e.key === "+" || e.key === "=" || e.code === "NumpAdd" || e.code === "Equal";
}

function isMinusKey(e) {
  return e.key === "-" || e.key === "_" || e.code === "NumpSubtract" || e.code === "Minus";
}

async function deleteLayer(opts = {}) {
  const { silent = false } = opts;
  const layer = selectedLayer();
  if (!layer || layer.is_subject || layer.locked) return;
  if (!silent && !confirm(t("pp.confirmDeleteLayer", { name: layer.name }))) return;
  await pushHistoryBefore({ includeImages: true });
  stack.layers = stack.layers.filter((l) => l.id !== layer.id);
  selectedId = stack.layers[stack.layers.length - 1]?.id || subjectLayer()?.id;
  renderLayers();
  fillProps();
  schedulePreview();
}

async function saveStack(btn) {
  await withBtnBusy(btn || $("#pp-save"), async () => {
    applyPropsFromForm();
    await API.put(`/api/assets/${assetId}/postprocess`, { stack });
    setStatus(t("pp.saved"));
  }).catch((err) => {
    if (err) setStatus(err.message);
  });
}

async function applyInbox(btn) {
  await withBtnBusy(btn || $("#pp-apply"), async () => {
    applyPropsFromForm();
    await API.put(`/api/assets/${assetId}/postprocess`, { stack });
    const r = await API.post(`/api/assets/${assetId}/postprocess/apply`, { stack });
    setStatus(t("pp.writtenInbox", { file: r.path?.split("/").pop() || "inbox" }));
  }).catch((err) => {
    if (err) setStatus(err.message);
  });
}

async function restoreFromSource(btn) {
  if (!confirm(t("pp.confirmRestore"))) return;
  await withBtnBusy(btn || $("#pp-restore-source"), async () => {
    setStatus(t("pp.restoring"));
    const r = await API.post(`/api/assets/${encodeURIComponent(assetId)}/postprocess/restore-from-source`);
    stack = r.stack;
    const subj = subjectLayer();
    selectedId = subj?.id || stack.layers?.[0]?.id;
    soloId = null;
    if ($("#pp-solo")) $("#pp-solo").checked = false;
    exitCropMode?.();
    renderLayers();
    fillProps();
    schedulePreview();
    resetHistory();
    setStatus(t("pp.restored", { file: r.path?.split("/").pop() || "inbox" }));
  }).catch((err) => {
    if (err) setStatus(err.message);
  });
}

async function loadTemplate(btn) {
  const tid = $("#pp-template").value;
  if (!tid) return;
  await withBtnBusy(btn || $("#pp-load-template"), async () => {
    await pushHistoryBefore({ includeImages: true });
    const { w, h } = canvasSize();
    const data = await API.get(`/api/postprocess/templates/${tid}?width=${w}&height=${h}`);
    stack = data.stack;
    soloId = null;
    $("#pp-solo").checked = false;
    const subj = stack.layers?.find((l) => l.is_subject);
    selectLayer(subj?.id || stack.layers?.[0]?.id);
    setStatus(t("pp.templateLoaded", { name: tid }));
  }).catch((err) => {
    if (err) setStatus(err.message);
  });
}

async function exportUnityAndReturn() {
  const btn = $("#pp-export-unity");
  await withBtnBusy(btn, async () => {
    applyPropsFromForm();
    setStatus(t("pp.exportSaving"));
    await API.put(`/api/assets/${assetId}/postprocess`, { stack });
    await API.post(`/api/assets/${assetId}/postprocess/apply`, { stack, export_unity: true });
    location.href = `/?asset=${encodeURIComponent(assetId)}`;
  }).catch((err) => {
    if (err) setStatus(t("pp.exportFailed", { msg: err.message }));
  });
}

async function resetTransform(full = false, partial = {}) {
  const l = selectedLayer();
  if (!l) return;
  await pushHistoryBefore({ includeImages: false });
  l.transform = l.transform || { anchor: "center" };
  if (full) {
    l.transform.offset_x = 0;
    l.transform.offset_y = 0;
    l.transform.scale = 1;
    l.opacity = 1;
  } else if (partial.xy) {
    l.transform.offset_x = 0;
    l.transform.offset_y = 0;
  } else if (partial.x) {
    l.transform.offset_x = 0;
  } else if (partial.y) {
    l.transform.offset_y = 0;
  } else if (partial.scale) {
    l.transform.scale = 1;
  } else {
    l.transform.offset_x = 0;
    l.transform.offset_y = 0;
    l.transform.scale = 1;
  }
  fillProps();
  schedulePreview();
}

async function clearLayerCrop() {
  const l = selectedLayer();
  if (!l?.crop) return;
  await pushHistoryBefore({ includeImages: false });
  delete l.crop;
  fillProps();
  schedulePreview();
}

// ── 指针事件 ─────────────────────────────────────────────

function bindViewport() {
  const vp = $("#pp-viewport");

  vp.addEventListener("wheel", (e) => {
    e.preventDefault();
    zoomBy(e.deltaY < 0 ? 1.1 : 0.9);
  }, { passive: false });

  vp.addEventListener("mousedown", (e) => {
    if (cropMode) return;
    const doc = canvasToDoc(e.clientX, e.clientY);
    const layer = hitTestLayer(doc.x, doc.y);

    if (matteMode && e.button === 0) {
      e.preventDefault();
      if (layer?.type === "image" && !layer.locked) {
        selectedId = layer.id;
        renderLayers();
        fillProps();
        drawOverlay();
        applySeedMatte(doc.x, doc.y, layer);
      }
      return;
    }

    if (layer) {
      selectedId = layer.id;
      renderLayers();
      fillProps();
      if (!layer.locked && layer.visible !== false) {
        pushHistoryBefore({ includeImages: false });
        drag = { id: layer.id, lastX: doc.x, lastY: doc.y };
      }
      drawOverlay();
    }
  });

  vp.addEventListener("dblclick", (e) => {
    if (cropMode) return;
    const doc = canvasToDoc(e.clientX, e.clientY);
    const layer = hitTestLayer(doc.x, doc.y);
    if (layer?.type === "text") {
      selectLayer(layer.id);
      focusTextContent();
      e.preventDefault();
    }
  });

  window.addEventListener("mousemove", (e) => {
    if (cropMode) return;
    if (!drag) return;
    const doc = canvasToDoc(e.clientX, e.clientY);
    const layer = stack.layers.find((l) => l.id === drag.id);
    if (!layer?.transform) return;
    const dx = doc.x - drag.lastX;
    const dy = doc.y - drag.lastY;
    if (dx === 0 && dy === 0) return;
    layer.transform.offset_x += dx;
    layer.transform.offset_y += dy;
    drag.lastX = doc.x;
    drag.lastY = doc.y;
    fillProps();
    fetchBounds().then(() => {
      layoutPreview();
      drawOverlay();
    });
    schedulePreview(120);
  });

  window.addEventListener("mouseup", () => {
    if (drag) {
      drag = null;
      refreshPreview();
    }
  });

  bindCropCanvas();

  window.addEventListener("resize", () => {
    layoutPreview();
    drawOverlay();
    if (cropMode) drawCropCanvas();
  });
}

function bindKeys() {
  document.addEventListener("keydown", (e) => {
    const inField = e.target.matches("input,textarea,select");
    const mod = e.ctrlKey || e.metaKey;

    if (cropMode) {
      if (e.key === "Escape") {
        cancelCropMode();
        e.preventDefault();
      } else if (e.key === "Enter") {
        commitCrop();
        e.preventDefault();
      }
      return;
    }

    if (matteMode) {
      if (e.key === "Escape") {
        exitMatteMode();
        e.preventDefault();
      }
      return;
    }

    if (mod && (e.key === "s" || e.key === "S")) {
      e.preventDefault();
      saveStack().catch((err) => setStatus(err.message));
      return;
    }

    if (mod && e.key === "z" && !e.shiftKey) {
      e.preventDefault();
      undoHistory();
      return;
    }
    if (mod && ((e.key === "z" && e.shiftKey) || e.key === "y" || e.key === "Y")) {
      e.preventDefault();
      redoHistory();
      return;
    }

    if (!inField && mod && isPlusKey(e)) {
      e.preventDefault();
      zoomBy(1.18);
      return;
    }
    if (!inField && mod && isMinusKey(e)) {
      e.preventDefault();
      zoomBy(0.85);
      return;
    }
    if (!inField && mod && e.key === "1") {
      e.preventDefault();
      zoomFit();
      return;
    }

    if (!inField && (e.key === "Delete" || e.key === "Backspace")) {
      const layer = selectedLayer();
      if (layer && !layer.is_subject && !layer.locked) {
        e.preventDefault();
        deleteLayer({ silent: true });
      }
      return;
    }

    if (!inField && e.key === "Escape") {
      e.preventDefault();
      if (matteMode) {
        exitMatteMode();
        return;
      }
      soloId = null;
      const solo = $("#pp-solo");
      if (solo) solo.checked = false;
      const subj = subjectLayer();
      if (subj) selectLayer(subj.id);
      else {
        selectedId = null;
        renderLayers();
        fillProps();
        drawOverlay();
      }
      return;
    }

    if (!inField && mod && (e.key === "d" || e.key === "D")) {
      e.preventDefault();
      duplicateLayer();
      return;
    }

    if (!inField && isPlusKey(e)) {
      e.preventDefault();
      const layer = selectedLayer();
      if (layer?.type === "text" && !layer.locked) {
        adjustTextFontSize(e.shiftKey ? 10 : 2);
      } else {
        zoomBy(1.18);
      }
      return;
    }
    if (!inField && isMinusKey(e)) {
      e.preventDefault();
      const layer = selectedLayer();
      if (layer?.type === "text" && !layer.locked) {
        adjustTextFontSize(e.shiftKey ? -10 : -2);
      } else {
        zoomBy(0.85);
      }
      return;
    }

    if (!inField && e.key === "Enter") {
      const layer = selectedLayer();
      if (layer?.type === "text") {
        e.preventDefault();
        focusTextContent();
        return;
      }
    }

    if (inField) return;

    const l = selectedLayer();
    if (!l?.transform || l.locked) return;
    const step = e.shiftKey ? 10 : 1;
    if (e.key === "ArrowLeft") {
      beginPropsHistoryBatch();
      l.transform.offset_x -= step;
      fillProps();
      schedulePreview(80);
      e.preventDefault();
    } else if (e.key === "ArrowRight") {
      l.transform.offset_x += step;
      fillProps();
      schedulePreview(80);
      e.preventDefault();
    } else if (e.key === "ArrowUp") {
      l.transform.offset_y -= step;
      fillProps();
      schedulePreview(80);
      e.preventDefault();
    } else if (e.key === "ArrowDown") {
      l.transform.offset_y += step;
      fillProps();
      schedulePreview(80);
      e.preventDefault();
    } else if (e.key === "Home") {
      l.transform.offset_x = 0;
      l.transform.offset_y = 0;
      fillProps();
      schedulePreview(80);
      e.preventDefault();
    } else if (e.key === "c" || e.key === "C") {
      enterCropMode();
      e.preventDefault();
    } else if (e.key === "m" || e.key === "M") {
      toggleMatteMode();
      e.preventDefault();
    } else if (e.key === "0" && mod) {
      l.transform.scale = 1;
      fillProps();
      schedulePreview(80);
      e.preventDefault();
    } else if ((e.key === "[" || e.key === "【") && l.type === "text") {
      adjustTextFontSize(e.shiftKey ? -10 : -2);
      e.preventDefault();
    } else if ((e.key === "]" || e.key === "】") && l.type === "text") {
      adjustTextFontSize(e.shiftKey ? 10 : 2);
      e.preventDefault();
    }
  });
}

function updatePostprocessMeta() {
  if (!assetInfo) return;
  const inboxName = assetPaths?.inbox?.split("/").pop() || "inbox";
  $("#pp-title").textContent = t("pp.titleAsset", { name: assetInfo.filename });
  $("#pp-meta").textContent = t("pp.meta", {
    w: assetInfo.width,
    h: assetInfo.height,
    inbox: inboxName,
  });
}

async function bootstrap() {
  assetInfo = await API.get(`/api/assets/${assetId}`);
  assetPaths = await API.get(`/api/assets/${assetId}/paths`);
  updatePostprocessMeta();

  const pp = await API.get(`/api/assets/${assetId}/postprocess`);
  stack = pp.stack;
  const subj = stack.layers?.find((l) => l.is_subject);
  selectedId = subj?.id || stack.layers?.[0]?.id;

  const tpl = await API.get("/api/postprocess/templates");
  for (const tplName of tpl.templates || []) {
    const o = document.createElement("option");
    o.value = tplName;
    o.textContent = tplName;
    $("#pp-template").appendChild(o);
  }

  try {
    const fonts = await API.get("/api/postprocess/fonts");
    for (const f of fonts.fonts || []) {
      const o = document.createElement("option");
      o.value = f;
      o.textContent = f;
      $("#pp-fonts").appendChild(o);
    }
  } catch {
    /* ignore */
  }

  renderLayers();
  fillProps();
  bindViewport();
  bindKeys();
  bindRangeSync();
  bindMatteControls();
  bindHistoryControls();
  resetHistory();
  initToolbarIcons();

  $("#pp-preview")?.addEventListener("error", () => {
    showPreviewEmpty(t("pp.noPreviewFile"));
    setStatus(t("pp.previewFailed", { msg: "load" }));
  });

  $("#pp-props-form").addEventListener("input", onPropsFormChange);
  $("#pp-props-form").addEventListener("change", onPropsFormChange);
  bindRipple(document.getElementById("pp-app"));

  $("#pp-save").addEventListener("click", (e) => saveStack(e.currentTarget));
  $("#pp-export-unity").addEventListener("click", (e) => exportUnityAndReturn());
  $("#pp-apply").addEventListener("click", (e) => applyInbox(e.currentTarget));
  $("#pp-restore-source").addEventListener("click", (e) => restoreFromSource(e.currentTarget));
  $("#pp-add-text").addEventListener("click", addTextLayer);
  $("#pp-add-image").addEventListener("click", () => addImageLayer());
  $("#pp-browse-source").addEventListener("click", (e) =>
    withBtnBusy(e.currentTarget, browseImageSource).catch((err) => {
      if (err) setStatus(err.message);
    }),
  );
  $("#pp-load-template").addEventListener("click", (e) => loadTemplate(e.currentTarget));
  $("#pp-center").addEventListener("click", () => resetTransform(false, { xy: true }));
  $("#pp-x0").addEventListener("click", () => resetTransform(false, { x: true }));
  $("#pp-y0").addEventListener("click", () => resetTransform(false, { y: true }));
  $("#pp-scale100").addEventListener("click", () => resetTransform(false, { scale: true }));
  $("#pp-reset-xform").addEventListener("click", () => resetTransform(true));
  $("#pp-clear-crop").addEventListener("click", () => clearLayerCrop());
  $("#pp-zoom-in").addEventListener("click", () => zoomBy(1.18));
  $("#pp-zoom-out").addEventListener("click", () => zoomBy(0.85));
  $("#pp-zoom-fit").addEventListener("click", zoomFit);
  $("#pp-solo").addEventListener("change", (e) => {
    soloId = e.target.checked ? selectedId : null;
    schedulePreview();
  });
  $("#pp-crop-toggle").addEventListener("click", () => {
    if (cropMode) commitCrop();
    else enterCropMode();
  });
  $("#pp-crop-commit").addEventListener("click", commitCrop);
  $("#pp-crop-cancel").addEventListener("click", cancelCropMode);

  await refreshPreview();
  zoomFit();
}

async function start() {
  showGlobalOverlay(t("splash.reloading"));
  try {
    await initI18n();
    applyDomI18n();
    bindLangSwitcher();
    onLangChange(() => {
      applyDomI18n();
      updatePostprocessMeta();
      renderLayers();
      if ($("#pp-crop-toggle")) {
        $("#pp-crop-toggle").textContent = cropMode ? t("pp.cropDone") : t("pp.crop");
      }
      updateMatteModeUi();
    });
    if (!assetId) {
      document.body.innerHTML = `<p class="hint">${t("pp.missingAsset")}</p>`;
      return;
    }
    await bootstrap();
    $("#pp-app")?.classList.add("is-ready");
  } finally {
    hideGlobalOverlay();
    document.body.classList.remove("is-booting");
  }
}

start().catch((e) => setStatus(e.message));
