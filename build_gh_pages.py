"""Build a self-contained static GitHub Pages site in ./docs from the Virtual Book app."""

import json
import shutil
from pathlib import Path
import fitz
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "docs"
DEMO_SRC = BASE_DIR / "data" / "books" / "demo-wellness-guide"
DEMO_DST = DOCS_DIR / "books" / "demo-wellness-guide"


def build_static_site() -> None:
    if DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")

    # 1. Copy static CSS & JS
    static_dst = DOCS_DIR / "static"
    static_dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BASE_DIR / "static" / "style.css", static_dst / "style.css")

    # 2. Copy demo book assets
    shutil.copytree(DEMO_SRC, DEMO_DST)

    # 3. Generate a downloadable PDF of the demo book inside docs/books/demo-wellness-guide/book.pdf
    doc = fitz.open()
    for page_file in sorted((DEMO_DST / "pages").glob("*.webp")):
        with Image.open(page_file) as im:
            import io
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            w_pt, h_pt = im.width * 0.5, im.height * 0.5
        page = doc.new_page(width=w_pt, height=h_pt)
        page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(DEMO_DST / "Executive-Longevity-Compendium.pdf", deflate=True)
    doc.close()

    # 4. Write index.html with relative asset paths (./static/...) + PDF.js CDN for client-side PDF uploads
    html = (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="/static/style.css"', 'href="./static/style.css?v=13"')
    html = html.replace(
        '<script src="/static/app.js"></script>',
        '<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>\n  <script src="./static/static-shim.js?v=13"></script>\n  <script src="./static/app.js?v=13"></script>',
    )
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")

    # 5. Copy app.js and write static-shim.js that intercepts /api/books/* in the browser when hosted on GitHub Pages!
    shutil.copy2(BASE_DIR / "static" / "app.js", static_dst / "app.js")

    shim_js = r"""/**
 * Client-side API interceptor for static hosting (GitHub Pages).
 * Emulates /api/books/* in browser memory + localStorage + PDF.js so the exact same app.js runs 100% serverless!
 */
(() => {
  "use strict";
  const origFetch = window.fetch.bind(window);
  const memBooks = new Map();
  let initialized = false;

  async function ensureInit() {
    if (initialized) return;
    initialized = true;
    const [meta, text, seedNotes] = await Promise.all([
      origFetch("./books/demo-wellness-guide/meta.json").then((r) => r.json()),
      origFetch("./books/demo-wellness-guide/text.json").then((r) => r.json()),
      origFetch("./books/demo-wellness-guide/notes.json").then((r) => r.json()),
    ]);
    const savedNotes = localStorage.getItem("vb_notes_demo-wellness-guide");
    const notes = savedNotes ? JSON.parse(savedNotes) : seedNotes;
    const v = encodeURIComponent(meta.edition || "1");
    const pages = [];
    for (let i = 1; i <= meta.page_count; i++) {
      const num = String(i).padStart(3, "0");
      pages.push({
        page: i,
        image_url: `./books/demo-wellness-guide/pages/page_${num}.webp?v=${v}`,
        thumb_url: `./books/demo-wellness-guide/thumbs/thumb_${num}.webp?v=${v}`,
      });
    }
    memBooks.set("demo-wellness-guide", {
      ...meta,
      pages,
      text_records: text,
      notes,
      download_url: "./books/demo-wellness-guide/Executive-Longevity-Compendium.pdf",
    });
  }

  function saveBookNotes(bookId, notes) {
    try {
      localStorage.setItem(`vb_notes_${bookId}`, JSON.stringify(notes));
    } catch {}
  }

  function jsonResp(obj, status = 200) {
    return new Response(JSON.stringify(obj), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }

  function naturalSortKey(name) {
    return name.split(/(\d+)/).map((p) => (/^\d+$/.test(p) ? Number(p) : p.toLowerCase()));
  }

  async function handlePdfUpload(formData) {
    const file = formData.get("file");
    if (!file) return jsonResp({ error: "No PDF file selected" }, 400);
    const title = (formData.get("title") || "").trim() || file.name.replace(/\.pdf$/i, "");
    const pdfjsLib = window["pdfjs-dist/build/pdf"];
    if (!pdfjsLib) return jsonResp({ error: "PDF.js library not loaded" }, 500);
    pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";

    const buf = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: buf }).promise;
    const bookId = "book-" + Math.random().toString(36).slice(2, 10);
    const pages = [];
    const text_records = [];

    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i);
      const vp = page.getViewport({ scale: 1.8 });
      const c = document.createElement("canvas");
      c.width = vp.width;
      c.height = vp.height;
      await page.render({ canvasContext: c.getContext("2d"), viewport: vp }).promise;
      const imgUrl = c.toDataURL("image/webp", 0.88);

      const tc = document.createElement("canvas");
      const tvp = page.getViewport({ scale: 0.35 });
      tc.width = tvp.width;
      tc.height = tvp.height;
      await page.render({ canvasContext: tc.getContext("2d"), viewport: tvp }).promise;
      const thumbUrl = tc.toDataURL("image/webp", 0.8);

      const tcText = await page.getTextContent();
      const extracted = tcText.items.map((it) => it.str).join(" ");
      pages.push({ page: i, image_url: imgUrl, thumb_url: thumbUrl });
      text_records.push({ page: i, text: extracted });
    }

    const blobUrl = URL.createObjectURL(file);
    const book = {
      id: bookId,
      title,
      page_count: pdf.numPages,
      source_type: "pdf",
      created_at: new Date().toISOString(),
      pages,
      text_records,
      notes: [],
      download_url: blobUrl,
    };
    memBooks.set(bookId, book);
    return jsonResp(book, 201);
  }

  async function handleImagesUpload(formData) {
    const files = Array.from(formData.getAll("files")).filter((f) => f && f.name);
    if (!files.length) return jsonResp({ error: "No image files selected" }, 400);
    files.sort((a, b) => {
      const ka = naturalSortKey(a.name);
      const kb = naturalSortKey(b.name);
      for (let i = 0; i < Math.min(ka.length, kb.length); i++) {
        if (ka[i] !== kb[i]) return ka[i] < kb[i] ? -1 : 1;
      }
      return 0;
    });
    const title = (formData.get("title") || "").trim() || "Uploaded Image Book";
    const bookId = "book-" + Math.random().toString(36).slice(2, 10);
    const pages = files.map((f, idx) => {
      const url = URL.createObjectURL(f);
      return { page: idx + 1, image_url: url, thumb_url: url };
    });
    const text_records = files.map((f, idx) => ({ page: idx + 1, text: f.name }));
    const book = {
      id: bookId,
      title,
      page_count: files.length,
      source_type: "images",
      created_at: new Date().toISOString(),
      pages,
      text_records,
      notes: [],
      download_url: pages[0].image_url,
    };
    memBooks.set(bookId, book);
    return jsonResp(book, 201);
  }

  window.fetch = async function (input, init = {}) {
    const urlStr = typeof input === "string" ? input : input.url;
    const u = new URL(urlStr, window.location.origin);
    if (!u.pathname.startsWith("/api/books")) {
      return origFetch(input, init);
    }

    await ensureInit();
    const method = (init.method || "GET").toUpperCase();
    const path = u.pathname;

    if (path === "/api/books" && method === "GET") {
      const books = Array.from(memBooks.values()).map((b) => ({
        id: b.id,
        title: b.title,
        page_count: b.page_count,
        source_type: b.source_type,
        created_at: b.created_at,
      }));
      return jsonResp({ books });
    }

    if (path === "/api/books/upload-pdf" && method === "POST") {
      return handlePdfUpload(init.body);
    }
    if (path === "/api/books/upload-images" && method === "POST") {
      return handleImagesUpload(init.body);
    }

    const mBook = path.match(/^\/api\/books\/([^/]+)$/);
    if (mBook) {
      const id = decodeURIComponent(mBook[1]);
      if (method === "GET") {
        const b = memBooks.get(id);
        return b ? jsonResp(b) : jsonResp({ error: "Not found" }, 404);
      }
      if (method === "DELETE") {
        memBooks.delete(id);
        return jsonResp({ deleted: id });
      }
    }

    const mSearch = path.match(/^\/api\/books\/([^/]+)\/search$/);
    if (mSearch && method === "GET") {
      const b = memBooks.get(decodeURIComponent(mSearch[1]));
      const q = (u.searchParams.get("q") || "").trim().toLowerCase();
      if (!b || !q) return jsonResp({ query: q, results: [] });
      const results = [];
      for (const rec of b.text_records || []) {
        const pos = (rec.text || "").toLowerCase().indexOf(q);
        if (pos !== -1) {
          const start = Math.max(0, pos - 40);
          const end = Math.min(rec.text.length, pos + q.length + 60);
          results.push({ page: rec.page, snippet: "..." + rec.text.slice(start, end) + "..." });
        }
      }
      return jsonResp({ query: q, results });
    }

    const mNotes = path.match(/^\/api\/books\/([^/]+)\/notes$/);
    if (mNotes && method === "POST") {
      const b = memBooks.get(decodeURIComponent(mNotes[1]));
      const body = JSON.parse(init.body || "{}");
      const note = {
        id: "note-" + Math.random().toString(36).slice(2, 9),
        page: Number(body.page || 1),
        author: body.author || "Dan",
        text: body.text || "",
        x: body.x,
        y: body.y,
        replies: [],
        created_at: new Date().toISOString(),
      };
      b.notes.push(note);
      saveBookNotes(b.id, b.notes);
      return jsonResp({ note, notes: b.notes }, 201);
    }

    const mDelNote = path.match(/^\/api\/books\/([^/]+)\/notes\/([^/]+)$/);
    if (mDelNote && method === "DELETE") {
      const b = memBooks.get(decodeURIComponent(mDelNote[1]));
      b.notes = b.notes.filter((n) => n.id !== mDelNote[2]);
      saveBookNotes(b.id, b.notes);
      return jsonResp({ notes: b.notes });
    }

    const mReply = path.match(/^\/api\/books\/([^/]+)\/notes\/([^/]+)\/replies$/);
    if (mReply && method === "POST") {
      const b = memBooks.get(decodeURIComponent(mReply[1]));
      const body = JSON.parse(init.body || "{}");
      const target = b.notes.find((n) => n.id === mReply[2]);
      if (target) {
        target.replies = target.replies || [];
        target.replies.push({
          id: "rep-" + Math.random().toString(36).slice(2, 9),
          author: body.author || "Dan",
          text: body.text || "",
          created_at: new Date().toISOString(),
        });
        saveBookNotes(b.id, b.notes);
      }
      return jsonResp({ notes: b.notes }, 201);
    }

    const mAi = path.match(/^\/api\/books\/([^/]+)\/ask-ai$/);
    if (mAi && method === "POST") {
      const b = memBooks.get(decodeURIComponent(mAi[1]));
      const body = JSON.parse(init.body || "{}");
      const page = Number(body.page || 1);
      const prompt = body.prompt || "Key Takeaways";
      const rec = (b.text_records || []).find((r) => r.page === page);
      const words = (rec?.text || "Visual folio page").split(/\s+/);
      const summary = `${prompt} (p.${page}): ${words.slice(0, 26).join(" ")}...`;
      const existing = b.notes.filter((n) => n.page === page && n.x != null);
      const note = {
        id: "note-" + Math.random().toString(36).slice(2, 9),
        page,
        author: "Gobg AI",
        text: summary,
        color: "hermes",
        x: 82.0,
        y: Math.min(85, 24 + existing.length * 14),
        replies: [],
        created_at: new Date().toISOString(),
      };
      b.notes.push(note);
      saveBookNotes(b.id, b.notes);
      return jsonResp({ note, notes: b.notes }, 201);
    }

    const mSession = path.match(/^\/api\/books\/([^/]+)\/session$/);
    if (mSession) {
      const b = memBooks.get(decodeURIComponent(mSession[1]));
      const reader = localStorage.getItem("vb_reader_name") || "Dan";
      return jsonResp({
        readers: { [reader]: { page: 1, updated_at: new Date().toISOString() } },
        notes: b ? b.notes : [],
      });
    }

    return jsonResp({ ok: true });
  };
})();
"""
    (static_dst / "static-shim.js").write_text(shim_js, encoding="utf-8")
    print(f"Static GitHub Pages site built in {DOCS_DIR}")


if __name__ == "__main__":
    build_static_site()
