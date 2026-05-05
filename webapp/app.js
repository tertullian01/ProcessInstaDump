/**
 * Browser-only Instagram export → HTML.
 * Uses fflate (CDN) to read/write ZIP. No server upload.
 */
import { unzipSync, zipSync, strFromU8, strToU8 } from "https://esm.sh/fflate@0.8.2";

const $ = (id) => document.getElementById(id);

const state = {
  files: [],
  lastZipBytes: null,
  lastPosts: null,
};
const POST_SCHEMA_KEYS = ["caption", "date_label", "timestamp_raw", "items"];

function appError(code, message, hint = "") {
  const err = new Error(message);
  err.code = code;
  err.hint = hint;
  return err;
}

/** @type {Record<string, { id: string, pageTitle: string, bodyClass: string, mainClass: string, topClass: string, themeCss: string, extraHead: string, buildHeader: () => string }>} */
const OUTPUT_THEMES = {
  classic: {
    id: "classic",
    pageTitle: "Instagram archive",
    bodyClass: "output-theme-classic",
    mainClass: "container",
    topClass: "",
    themeCss: "assets/themes/classic.css",
    extraHead: "",
    buildHeader: () => "",
  },
  minimal: {
    id: "minimal",
    pageTitle: "Instagram archive",
    bodyClass: "output-theme-minimal",
    mainClass: "container",
    topClass: "",
    themeCss: "assets/themes/minimal.css",
    extraHead: "",
    buildHeader: () => "",
  },
  "memory-book": {
    id: "memory-book",
    pageTitle: "Memory book",
    bodyClass: "output-theme-memory-book",
    mainClass: "container",
    topClass: "pt-2",
    themeCss: "assets/themes/memory-book.css",
    extraHead:
      '<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400&family=Crimson+Pro:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">',
    buildHeader: () =>
      `<header class="memory-book-header text-center py-3 py-md-4 px-2">
        <h1 class="memory-book-title mb-2">Memory book</h1>
        <p class="memory-book-subtitle mb-0 text-muted">A printable keepsake from your Instagram archive — use your browser’s Print dialog for PDF or paper.</p>
      </header>`,
  },
};

/** @type {Record<string, { id: string }>} */
const OUTPUT_LAYOUTS = {
  stacked: { id: "stacked" },
  grid: { id: "grid" },
};

function getThemeAndLayout() {
  const themeEl = $("themeSelect");
  const layoutEl = $("layoutSelect");
  const rawTheme = (themeEl?.value ?? "classic").trim();
  const rawLayout = (layoutEl?.value ?? "stacked").trim();
  const themeKey = OUTPUT_THEMES[rawTheme] ? rawTheme : "classic";
  const layoutKey = OUTPUT_LAYOUTS[rawLayout] ? rawLayout : "stacked";
  return { theme: OUTPUT_THEMES[themeKey], layout: OUTPUT_LAYOUTS[layoutKey] };
}


function normalizePath(p) {
  return String(p || "")
    .replace(/\\/g, "/")
    .replace(/^\/+/, "")
    .replace(/\/+/g, "/");
}

function pathLeaf(filePath) {
  const n = normalizePath(filePath);
  const parts = n.split("/").filter(Boolean);
  if (parts.length < 2) return parts[0] || "";
  return parts[parts.length - 2];
}

function parseTime(timeString) {
  if (!timeString) return null;
  const d = new Date(timeString);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatHashMinute(d) {
  if (!d) return "unknown";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatDateLabel(d) {
  if (!d) return "";
  const months = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
  ];
  return `${months[d.getMonth()]} ${String(d.getDate()).padStart(2, "0")}, ${d.getFullYear()}`;
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => {
    const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
    return map[c] || c;
  });
}

function findInMap(fileMap, relPath) {
  const n = normalizePath(relPath);
  if (fileMap.has(n)) return fileMap.get(n);
  const lower = n.toLowerCase();
  for (const [k, v] of fileMap.entries()) {
    if (k.toLowerCase() === lower) return v;
  }
  const base = n.split("/").pop();
  const hits = [];
  for (const [k, v] of fileMap.entries()) {
    if (k === base || k.endsWith("/" + base)) hits.push(v);
  }
  if (hits.length === 1) return hits[0];
  return null;
}

function mergeZipIntoMap(arrayBuffer, fileMap) {
  const u8 = new Uint8Array(arrayBuffer);
  const entries = unzipSync(u8);
  for (const [relPath, content] of Object.entries(entries)) {
    const key = normalizePath(relPath);
    if (!key || key.endsWith("/")) continue;
    fileMap.set(key, content);
  }
}

/** New export: e.g. your_instagram_activity/media/posts_1.json */
const POSTS_JSON_RE = /(^|\/)posts_\d+\.json$/i;

function dirnamePath(p) {
  const n = normalizePath(p);
  const i = n.lastIndexOf("/");
  return i <= 0 ? "" : n.slice(0, i);
}

/** Media paths in JSON are relative to the grandparent of posts_N.json (same folder as "media" segment). */
function resolvePostsExportPath(jsonKey, uri) {
  const base = dirnamePath(dirnamePath(jsonKey));
  const rel = normalizePath(String(uri || ""));
  return base ? `${base}/${rel}` : rel;
}

function makeDiagnostics() {
  return {
    format: "unknown",
    jsonFilesFound: 0,
    mediaFilesResolved: 0,
    mediaFilesMissing: 0,
    postsParsed: 0,
    postsSkipped: 0,
    invalidPosts: 0,
  };
}

function formatDiagnostics(diag) {
  return `Diagnostics: format=${diag.format}, json=${diag.jsonFilesFound}, posts_parsed=${diag.postsParsed}, posts_skipped=${diag.postsSkipped}, media_resolved=${diag.mediaFilesResolved}, media_missing=${diag.mediaFilesMissing}`;
}

function validatePostSchema(post) {
  if (!post || typeof post !== "object") throw appError("E_SCHEMA_POST", "Loader produced an invalid post object.");
  for (const key of POST_SCHEMA_KEYS) {
    if (!(key in post)) throw appError("E_SCHEMA_POST", `Post is missing required key "${key}".`);
  }
  if (!Array.isArray(post.items)) throw appError("E_SCHEMA_POST", 'Post key "items" must be an array.');
  for (const item of post.items) {
    if (!item || typeof item !== "object" || !item.media_url) {
      throw appError("E_SCHEMA_POST", "Post contains an invalid media item.");
    }
  }
}

function loadPostsFromLegacyMediaJson(fileMap, mediaJsonKeys, diagnostics) {
  diagnostics.format = "legacy-media-json";
  diagnostics.jsonFilesFound = mediaJsonKeys.length;
  const grouped = new Map();
  for (const key of mediaJsonKeys) {
    let fileData;
    try {
      fileData = JSON.parse(strFromU8(fileMap.get(key)));
    } catch {
      throw appError("E_INVALID_JSON", "Invalid JSON in " + key, "Re-export or re-unzip your archive.");
    }
    for (const postType of Object.keys(fileData)) {
      const list = fileData[postType];
      if (!Array.isArray(list)) continue;
      for (const post of list) {
        if (!post || typeof post !== "object" || Object.keys(post).length === 0) {
          diagnostics.postsSkipped += 1;
          continue;
        }
        const path = post.path;
        if (path) {
          post.path = `${pathLeaf(key)}/${path}`.replace(/\/+/g, "/");
        }
        const dt = parseTime(post.taken_at || "");
        const hash = dt ? formatHashMinute(dt) : "unknown";
        if (!grouped.has(hash)) grouped.set(hash, []);
        grouped.get(hash).push(post);
      }
    }
  }

  const posts = [];
  for (const [key, group] of grouped.entries()) {
    const first = group[0];
    const dtFirst = parseTime(first.taken_at || "");
    const dateLabel = dtFirst ? formatDateLabel(dtFirst) : "";
    const items = [];
    for (const media of group) {
      const relativePath = media.path || "";
      const bytes = findInMap(fileMap, relativePath);
      if (!relativePath || !bytes) {
        diagnostics.mediaFilesMissing += 1;
        continue;
      }
      diagnostics.mediaFilesResolved += 1;
      const lower = relativePath.toLowerCase();
      items.push({
        media_type: lower.endsWith(".mp4") ? "VIDEO" : "IMAGE",
        media_url: relativePath,
        _bytes: bytes,
      });
    }
    posts.push({
      caption: first.caption || "",
      date_label: dateLabel,
      timestamp_raw: key,
      items,
    });
  }
  diagnostics.postsParsed = posts.length;
  return posts;
}

function loadPostsFromPostsJsonFiles(fileMap, postsJsonKeys, diagnostics) {
  diagnostics.format = "modern-posts-json";
  diagnostics.jsonFilesFound = postsJsonKeys.length;
  const posts = [];
  const sortedKeys = [...postsJsonKeys].sort();
  for (const jsonKey of sortedKeys) {
    let data;
    try {
      data = JSON.parse(strFromU8(fileMap.get(jsonKey)));
    } catch {
      throw appError("E_INVALID_JSON", "Invalid JSON in " + jsonKey, "Re-export or re-unzip your archive.");
    }
    if (!Array.isArray(data)) {
      diagnostics.postsSkipped += 1;
      continue;
    }
    for (const post of data) {
      if (!post || typeof post !== "object") {
        diagnostics.postsSkipped += 1;
        continue;
      }
      const caption = post.title != null ? String(post.title) : "";
      const ts = post.creation_timestamp;
      const dt = ts != null ? new Date(Number(ts) * 1000) : null;
      const valid = dt && !Number.isNaN(dt.getTime());
      const timestampRaw = valid ? formatHashMinute(dt) : "unknown";
      const dateLabel = valid ? formatDateLabel(dt) : "";
      const mediaList = Array.isArray(post.media) ? post.media : [];
      const items = [];
      for (const m of mediaList) {
        if (!m || typeof m !== "object") continue;
        const uri = m.uri;
        if (!uri) continue;
        const relativePath = resolvePostsExportPath(jsonKey, uri);
        const bytes = findInMap(fileMap, relativePath);
        if (!relativePath || !bytes) {
          diagnostics.mediaFilesMissing += 1;
          continue;
        }
        diagnostics.mediaFilesResolved += 1;
        const lower = relativePath.toLowerCase();
        items.push({
          media_type: lower.endsWith(".mp4") ? "VIDEO" : "IMAGE",
          media_url: relativePath,
          _bytes: bytes,
        });
      }
      if (items.length === 0) {
        diagnostics.postsSkipped += 1;
        continue;
      }
      posts.push({
        caption,
        date_label: dateLabel,
        timestamp_raw: timestampRaw,
        items,
      });
    }
  }
  diagnostics.postsParsed = posts.length;
  return posts;
}

function loadPostsFromFileMap(fileMap) {
  const keys = [...fileMap.keys()];
  const diagnostics = makeDiagnostics();
  const mediaJsonKeys = keys.filter((k) => k.endsWith("media.json"));
  let posts = [];
  if (mediaJsonKeys.length > 0) {
    posts = loadPostsFromLegacyMediaJson(fileMap, mediaJsonKeys, diagnostics);
  } else {
    const postsJsonKeys = keys.filter((k) => POSTS_JSON_RE.test(k));
    if (postsJsonKeys.length === 0) {
      throw appError(
        "E_NO_INPUT_JSON",
        "No Instagram export JSON found.",
        "Add legacy media.json or newer posts_<number>.json from your download ZIPs.",
      );
    }
    posts = loadPostsFromPostsJsonFiles(fileMap, postsJsonKeys, diagnostics);
  }
  for (const post of posts) {
    validatePostSchema(post);
  }
  return { posts, diagnostics };
}

function buildPost(post, urlResolver) {
  const caption = post.caption ?? "";
  const dateLabel = post.date_label ?? "";
  const mediaItems = post.items ?? [];
  let html = `<div class='blog-post'><p class='blog-post-meta'>${escapeHtml(dateLabel)}</p>`;
  for (const item of mediaItems) {
    const mediaType = String(item.media_type || "").toUpperCase();
    const url = urlResolver(item);
    if (!url) continue;
    if (mediaType === "VIDEO") {
      html += `<div class='embed-responsive embed-responsive-16by9'><video width='320' height='240' controls><source src='${escapeHtml(url)}' type='video/mp4'></video></div>`;
    } else {
      html += `<img src='${escapeHtml(url)}' class='img-fluid' alt='${escapeHtml(caption)}'>`;
    }
  }
  html += `<blockquote><p>${escapeHtml(caption)}</p></blockquote>`;
  html += `</div>`;
  return html;
}

function sortPosts(posts, descending = true) {
  if (!Array.isArray(posts)) return [];
  return [...posts].sort((a, b) => {
    const cmp = String(a.timestamp_raw).localeCompare(String(b.timestamp_raw));
    return descending ? -cmp : cmp;
  });
}

function renderPostsHtml(posts, urlResolver, descending = true, layoutId = "stacked", presorted = false) {
  const sorted = posts;
  if (!Array.isArray(posts)) {
    throw appError("E_SCHEMA_POST", "renderPostsHtml expected an array of posts.");
  }
  const ordered = presorted ? sorted : sortPosts(sorted, descending);
  const layout =
    layoutId === "grid" ? "grid" : "stacked";
  let inner = "";
  for (const p of ordered) {
    inner += buildPost(p, urlResolver);
  }
  return `<div class="posts-layout posts-layout--${layout}">${inner}</div>`;
}

function applyOutputTemplate(
  template,
  {
    title,
    bodyClass,
    mainClass,
    topClass,
    headerHtml,
    extraHead,
    postsHtml,
  },
) {
  return template
    .replace("%%TITLE%%", escapeHtml(title))
    .replace("%%BODY_CLASS%%", bodyClass)
    .replace("%%MAIN_CLASS%%", mainClass)
    .replace("%%TOP_CLASS%%", topClass)
    .replace("%%EXTRA_HEAD%%", extraHead)
    .replace("%%HEADER%%", headerHtml)
    .replace("%%POSTS%%", postsHtml)
    .replace("%%FOOTER%%", "");
}

function decodeUtf8(u8) {
  let s = new TextDecoder("utf-8", { fatal: false }).decode(u8);
  if (s.charCodeAt(0) === 0xfeff) {
    s = s.slice(1);
  }
  return s;
}

/** Avoid stale theme/blog CSS when preview is regenerated (HTTP cache, SW, disk cache). */
const FETCH_ASSETS = { cache: "no-store" };

/** Avoid `</style` inside CSS from terminating the HTML style element early. */
function sanitizeCssForInlineStyle(css) {
  return css.replace(/<\/style/gi, "<\\/style");
}

/**
 * Blob: URLs cannot resolve relative css/bootstrap.css, blog.css, theme.css (or JS).
 * Strip those tags and inject one merged &lt;style&gt; (Bootstrap → blog → theme) before &lt;/head&gt;.
 */
function bundlePreviewForBlobDocument(html, bootstrapU8, blogU8, themeU8) {
  const boot = sanitizeCssForInlineStyle(decodeUtf8(bootstrapU8));
  const blog = sanitizeCssForInlineStyle(decodeUtf8(blogU8));
  const theme = sanitizeCssForInlineStyle(decodeUtf8(themeU8));
  const merged = [
    "/*! archive-preview: bootstrap */",
    boot,
    "/*! archive-preview: blog */",
    blog,
    "/*! archive-preview: theme */",
    theme,
  ].join("\n\n");
  const block = `\n<style type="text/css" id="archive-preview-styles">\n${merged}\n</style>\n`;

  let out = html.replace(/\r\n/g, "\n");
  out = out.replace(/<link[^>]*\bhref\s*=\s*["']css\/bootstrap\.css["'][^>]*>\s*/gi, "");
  out = out.replace(/<link[^>]*\bhref\s*=\s*["']blog\.css["'][^>]*>\s*/gi, "");
  out = out.replace(/<link[^>]*\bhref\s*=\s*["']theme\.css["'][^>]*>\s*/gi, "");
  out = out.replace(/<script[^>]*\bsrc\s*=\s*["']js\/bootstrap\.bundle\.js["'][^>]*>\s*<\/script>\s*/gi, "");

  const headClose = /<\/head>/i;
  const m = headClose.exec(out);
  if (m) {
    const i = m.index;
    return out.slice(0, i) + block + out.slice(i);
  }
  if (/<body\b[^>]*>/i.test(out)) {
    return out.replace(/<body\b[^>]*>/i, (open) => `${block}${open}`);
  }
  return `${block}${out}`;
}

function revokeObjectUrls(posts) {
  for (const p of posts) {
    for (const it of p.items) {
      if (it._blobUrl) {
        URL.revokeObjectURL(it._blobUrl);
        delete it._blobUrl;
      }
    }
  }
}

function attachPreviewUrls(posts) {
  revokeObjectUrls(posts);
  for (const p of posts) {
    for (const it of p.items) {
      const blob = new Blob([it._bytes], { type: it.media_type === "VIDEO" ? "video/mp4" : "image/jpeg" });
      it._blobUrl = URL.createObjectURL(blob);
    }
  }
  return (item) => item._blobUrl || "";
}

async function loadTemplate() {
  const base = new URL(".", import.meta.url);
  const r = await fetch(new URL("template.html", base), FETCH_ASSETS);
  if (!r.ok) throw new Error("Could not load template.html");
  return await r.text();
}

async function fetchBinaryAsset(relativePath) {
  const base = new URL(".", import.meta.url);
  const r = await fetch(new URL(relativePath, base), FETCH_ASSETS);
  if (!r.ok) throw new Error("Missing local asset: " + relativePath);
  return new Uint8Array(await r.arrayBuffer());
}

function safeZipPath(p) {
  return normalizePath(p)
    .split("/")
    .filter((x) => x && x !== "." && x !== "..")
    .join("/");
}

function setStatus(msg, isError = false) {
  $("status").classList.toggle("d-none", !!isError || !msg);
  $("error").classList.toggle("d-none", !isError);
  if (isError) $("error").textContent = msg;
  else $("status").textContent = msg;
}

async function tickUi() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

function updateFileUi() {
  const names = state.files.map((f) => f.name).join(", ");
  $("fileList").textContent = state.files.length ? `Selected: ${names}` : "";
  $("btnGenerate").disabled = state.files.length === 0;
}

function readAllZips() {
  const fileMap = new Map();
  return (async () => {
    for (const f of state.files) {
      const buf = await f.arrayBuffer();
      mergeZipIntoMap(buf, fileMap);
    }
    return fileMap;
  })();
}

async function generate() {
  $("btnDownload").disabled = true;
  state.lastZipBytes = null;
  setStatus("Reading ZIPs…");
  revokeObjectUrls(state.lastPosts || []);
  state.lastPosts = null;

  try {
    setStatus("Reading ZIP files…");
    await tickUi();
    const fileMap = await readAllZips();
    setStatus("Parsing export JSON…");
    await tickUi();
    const { posts, diagnostics } = loadPostsFromFileMap(fileMap);
    if (posts.length === 0) {
      throw appError(
        "E_NO_POSTS",
        "No posts could be built from your files.",
        "Ensure all ZIP parts are selected and extracted media paths are included in the archives.",
      );
    }
    state.lastPosts = posts;
    setStatus(formatDiagnostics(diagnostics));
    await tickUi();

    setStatus("Loading HTML/CSS assets…");
    await tickUi();
    const template = await loadTemplate();
    const { theme, layout } = getThemeAndLayout();
    const layoutId = layout.id;

    const css = await fetchBinaryAsset("assets/css/bootstrap.css");
    const js = await fetchBinaryAsset("assets/js/bootstrap.bundle.js");
    const blog = await fetchBinaryAsset("assets/blog.css");
    const themeCss = await fetchBinaryAsset(theme.themeCss);

    setStatus("Building preview…");
    await tickUi();
    const sortedPosts = sortPosts(posts, true);
    const previewResolver = attachPreviewUrls(sortedPosts);
    const previewPostsHtml = renderPostsHtml(sortedPosts, previewResolver, true, layoutId, true);
    let previewHtml = applyOutputTemplate(template, {
      title: theme.pageTitle,
      bodyClass: theme.bodyClass,
      mainClass: theme.mainClass,
      topClass: theme.topClass,
      headerHtml: theme.buildHeader(),
      extraHead: theme.extraHead,
      postsHtml: previewPostsHtml,
    });
    previewHtml = bundlePreviewForBlobDocument(previewHtml, css, blog, themeCss);

    setStatus("Packing download ZIP…");
    await tickUi();
    const zipPathResolver = (item) => safeZipPath(item.media_url);
    const zipPostsHtml = renderPostsHtml(sortedPosts, zipPathResolver, true, layoutId, true);
    const zipHtml = applyOutputTemplate(template, {
      title: theme.pageTitle,
      bodyClass: theme.bodyClass,
      mainClass: theme.mainClass,
      topClass: theme.topClass,
      headerHtml: theme.buildHeader(),
      extraHead: theme.extraHead,
      postsHtml: zipPostsHtml,
    });

    const exportFiles = {
      "index.html": strToU8(zipHtml),
      "blog.css": blog,
      "theme.css": themeCss,
      "css/bootstrap.css": css,
      "js/bootstrap.bundle.js": js,
    };
    for (const p of sortedPosts) {
      for (const it of p.items) {
        const zp = safeZipPath(it.media_url);
        if (zp && !exportFiles[zp]) exportFiles[zp] = it._bytes;
      }
    }
    state.lastZipBytes = zipSync(exportFiles, { level: 6 });

    $("btnDownload").disabled = false;
    setStatus(
      `Ready: ${posts.length} post(s) — theme "${theme.id}", ${layout.id} layout. Preview opened; download the ZIP when you are satisfied.`,
    );
    const previewBlob = new Blob([previewHtml], { type: "text/html;charset=utf-8" });
    const previewUrl = URL.createObjectURL(previewBlob);
    const a = document.createElement("a");
    a.href = previewUrl;
    a.target = "_blank";
    a.rel = "noopener";
    a.click();
    setTimeout(() => URL.revokeObjectURL(previewUrl), 60_000);
  } catch (e) {
    console.error(e);
    const code = e?.code ? ` [${e.code}]` : "";
    const hint = e?.hint ? ` Hint: ${e.hint}` : "";
    setStatus(`${String(e?.message || e)}${code}${hint}`, true);
  }
}

function downloadZip() {
  if (!state.lastZipBytes) return;
  const blob = new Blob([state.lastZipBytes], { type: "application/zip" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "instagram-archive.zip";
  a.click();
  URL.revokeObjectURL(url);
}

function wireUi() {
  const drop = $("dropZone");
  const input = $("fileInput");

  drop.addEventListener("click", () => input.click());
  drop.addEventListener("dragover", (e) => {
    e.preventDefault();
    drop.classList.add("drag");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("drag");
    const zips = [...e.dataTransfer.files].filter((f) => f.name.toLowerCase().endsWith(".zip"));
    if (zips.length) {
      state.files = zips;
      updateFileUi();
    }
  });

  input.addEventListener("change", () => {
    state.files = [...input.files].filter((f) => f.name.toLowerCase().endsWith(".zip"));
    updateFileUi();
  });

  $("btnGenerate").addEventListener("click", () => generate());
  $("btnDownload").addEventListener("click", () => downloadZip());
}

wireUi();
