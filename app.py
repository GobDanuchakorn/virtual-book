"""FlippingBook-style Virtual Book Web Application (Flask + PyMuPDF + Pillow)."""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import fitz  # PyMuPDF
from flask import Flask, jsonify, render_template, request, send_file, send_from_directory
from PIL import Image, ImageOps

from demo_generator import ensure_demo_book

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
BOOKS_DIR = DATA_DIR / "books"

ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
MAX_UPLOAD_MB = 100


def _natural_sort_key(name: str) -> list[int | str]:
    """Sort filenames naturally (e.g. page2.png before page10.png)."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def _safe_book_id(raw_id: str) -> str | None:
    """Validate book_id to prevent directory traversal."""
    if not raw_id or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", raw_id):
        return None
    return raw_id


def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data) -> None:
    tmp_path = path.with_suffix(f".{uuid.uuid4().hex[:8]}.tmp")
    tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_path, path)


PHI_PATTERN = re.compile(r"\b(HN\s*[:#-]?\s*\d{5,10}|DOB\s*[:#-]?\s*\d{1,4}[/-]\d{1,2}[/-]\d{1,4}|MRN\s*[:#-]?\s*\d{5,10})\b", re.IGNORECASE)


def _book_payload(book_dir: Path) -> dict | None:
    meta_path = book_dir / "meta.json"
    if not meta_path.exists():
        return None
    meta = _load_json(meta_path, {})
    book_id = meta.get("id", book_dir.name)
    page_count = int(meta.get("page_count", 0))
    pages = [
        {
            "page": i,
            "image_url": f"/api/books/{book_id}/pages/{i}",
            "thumb_url": f"/api/books/{book_id}/thumbs/{i}",
        }
        for i in range(1, page_count + 1)
    ]
    notes = _load_json(book_dir / "notes.json", [])
    return {
        **meta,
        "pages": pages,
        "notes": notes,
        "download_url": f"/api/books/{book_id}/download",
    }


def create_app(books_dir: Path | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

    target_books_dir = books_dir or BOOKS_DIR
    target_books_dir.mkdir(parents=True, exist_ok=True)
    ensure_demo_book(target_books_dir)

    # In-memory co-reading presence per book_id: { book_id: { reader_name: { page, updated_at } } }
    co_reading_sessions: dict[str, dict[str, dict]] = {}
    notes_lock = threading.Lock()

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/books")
    def list_books():
        items = []
        for entry in sorted(target_books_dir.iterdir()):
            if not entry.is_dir():
                continue
            meta_path = entry / "meta.json"
            if meta_path.exists():
                items.append(_load_json(meta_path, {}))
        items.sort(key=lambda b: b.get("created_at", ""), reverse=True)
        return jsonify({"books": items})

    @app.get("/api/books/<raw_id>")
    def get_book(raw_id: str):
        book_id = _safe_book_id(raw_id)
        if not book_id:
            return jsonify({"error": "Invalid book ID"}), 400
        payload = _book_payload(target_books_dir / book_id)
        if not payload:
            return jsonify({"error": "Book not found"}), 404
        return jsonify(payload)

    @app.get("/api/books/<raw_id>/pages/<int:page_num>")
    def get_page_image(raw_id: str, page_num: int):
        book_id = _safe_book_id(raw_id)
        if not book_id or page_num < 1:
            return jsonify({"error": "Invalid request"}), 400
        pages_dir = target_books_dir / book_id / "pages"
        filename = f"page_{page_num:03d}.webp"
        if not (pages_dir / filename).exists():
            return jsonify({"error": "Page not found"}), 404
        return send_from_directory(pages_dir, filename)

    @app.get("/api/books/<raw_id>/thumbs/<int:page_num>")
    def get_thumb_image(raw_id: str, page_num: int):
        book_id = _safe_book_id(raw_id)
        if not book_id or page_num < 1:
            return jsonify({"error": "Invalid request"}), 400
        thumbs_dir = target_books_dir / book_id / "thumbs"
        filename = f"thumb_{page_num:03d}.webp"
        if not (thumbs_dir / filename).exists():
            return jsonify({"error": "Thumbnail not found"}), 404
        return send_from_directory(thumbs_dir, filename)

    @app.post("/api/books/upload-pdf")
    def upload_pdf():
        if "file" not in request.files:
            return jsonify({"error": "No PDF file provided"}), 400
        file = request.files["file"]
        if not file or not file.filename:
            return jsonify({"error": "Empty filename"}), 400
        if not file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "Only .pdf files are supported here"}), 400

        title = (request.form.get("title") or "").strip() or Path(file.filename).stem
        book_id = f"book-{uuid.uuid4().hex[:10]}"
        book_dir = target_books_dir / book_id
        pages_dir = book_dir / "pages"
        thumbs_dir = book_dir / "thumbs"
        pages_dir.mkdir(parents=True, exist_ok=True)
        thumbs_dir.mkdir(parents=True, exist_ok=True)

        pdf_path = book_dir / "source.pdf"
        file.save(pdf_path)

        try:
            doc = fitz.open(pdf_path)
        except Exception as exc:
            shutil.rmtree(book_dir, ignore_errors=True)
            return jsonify({"error": f"Failed to read PDF: {exc}"}), 400

        if doc.page_count == 0:
            doc.close()
            shutil.rmtree(book_dir, ignore_errors=True)
            return jsonify({"error": "PDF has no pages"}), 400

        text_records = []
        try:
            for idx, page in enumerate(doc, start=1):
                # Render at ~2x resolution for crisp zoom without huge files
                zoom = min(2.2, 1800.0 / max(page.rect.width, 1.0))
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                img.save(pages_dir / f"page_{idx:03d}.webp", "WEBP", quality=88)

                thumb = img.copy()
                thumb.thumbnail((260, 360), Image.Resampling.LANCZOS)
                thumb.save(thumbs_dir / f"thumb_{idx:03d}.webp", "WEBP", quality=80)

                extracted = " ".join((page.get_text("text") or "").split())
                text_records.append({"page": idx, "text": extracted})
        finally:
            page_count = doc.page_count
            doc.close()

        meta = {
            "id": book_id,
            "title": title,
            "page_count": page_count,
            "source_type": "pdf",
            "original_filename": Path(file.filename).name,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_json(book_dir / "meta.json", meta)
        _save_json(book_dir / "text.json", text_records)
        _save_json(book_dir / "notes.json", [])

        return jsonify(_book_payload(book_dir)), 201

    @app.post("/api/books/upload-images")
    def upload_images():
        files = request.files.getlist("files")
        valid_files = [
            f for f in files if f and f.filename and Path(f.filename).suffix.lower() in ALLOWED_IMAGE_EXTS
        ]
        if not valid_files:
            return jsonify({"error": "No valid image files provided (PNG, JPG, WebP)"}), 400

        valid_files.sort(key=lambda f: _natural_sort_key(Path(f.filename).name))
        title = (request.form.get("title") or "").strip() or "Uploaded Image Book"
        book_id = f"book-{uuid.uuid4().hex[:10]}"
        book_dir = target_books_dir / book_id
        pages_dir = book_dir / "pages"
        thumbs_dir = book_dir / "thumbs"
        pages_dir.mkdir(parents=True, exist_ok=True)
        thumbs_dir.mkdir(parents=True, exist_ok=True)

        text_records = []
        try:
            for idx, f in enumerate(valid_files, start=1):
                img = Image.open(f.stream)
                img = ImageOps.exif_transpose(img).convert("RGB")
                if img.width > 2000:
                    ratio = 2000.0 / img.width
                    img = img.resize((2000, int(img.height * ratio)), Image.Resampling.LANCZOS)

                img.save(pages_dir / f"page_{idx:03d}.webp", "WEBP", quality=88)

                thumb = img.copy()
                thumb.thumbnail((260, 360), Image.Resampling.LANCZOS)
                thumb.save(thumbs_dir / f"thumb_{idx:03d}.webp", "WEBP", quality=80)

                text_records.append({"page": idx, "text": Path(f.filename).stem})
        except Exception as exc:
            shutil.rmtree(book_dir, ignore_errors=True)
            return jsonify({"error": f"Failed to process images: {exc}"}), 400

        meta = {
            "id": book_id,
            "title": title,
            "page_count": len(valid_files),
            "source_type": "images",
            "original_filename": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_json(book_dir / "meta.json", meta)
        _save_json(book_dir / "text.json", text_records)
        _save_json(book_dir / "notes.json", [])

        return jsonify(_book_payload(book_dir)), 201

    @app.delete("/api/books/<raw_id>")
    def delete_book(raw_id: str):
        book_id = _safe_book_id(raw_id)
        if not book_id:
            return jsonify({"error": "Invalid book ID"}), 400
        if book_id == "demo-wellness-guide":
            return jsonify({"error": "Built-in demo book cannot be deleted"}), 400
        book_dir = target_books_dir / book_id
        if not book_dir.exists():
            return jsonify({"error": "Book not found"}), 404
        shutil.rmtree(book_dir)
        return jsonify({"deleted": book_id})

    @app.get("/api/books/<raw_id>/search")
    def search_book(raw_id: str):
        book_id = _safe_book_id(raw_id)
        if not book_id:
            return jsonify({"error": "Invalid book ID"}), 400
        book_dir = target_books_dir / book_id
        if not book_dir.exists():
            return jsonify({"error": "Book not found"}), 404

        query = (request.args.get("q") or "").strip()
        if not query:
            return jsonify({"query": "", "results": []})

        text_records = _load_json(book_dir / "text.json", [])
        q_lower = query.lower()
        results = []
        for rec in text_records:
            text = rec.get("text", "")
            pos = text.lower().find(q_lower)
            if pos != -1:
                start = max(0, pos - 45)
                end = min(len(text), pos + len(query) + 65)
                snippet = ("..." if start > 0 else "") + text[start:end] + ("..." if end < len(text) else "")
                results.append({"page": rec["page"], "snippet": snippet})
        return jsonify({"query": query, "results": results})

    @app.post("/api/books/<raw_id>/notes")
    def add_note(raw_id: str):
        book_id = _safe_book_id(raw_id)
        if not book_id:
            return jsonify({"error": "Invalid book ID"}), 400
        book_dir = target_books_dir / book_id
        if not book_dir.exists():
            return jsonify({"error": "Book not found"}), 404

        body = request.get_json(silent=True) or {}
        text = (body.get("text") or "").strip()
        page = int(body.get("page") or 1)
        author = (body.get("author") or "Reader").strip()[:40] or "Reader"
        color = (body.get("color") or ("hermes" if author.lower().startswith("hermes") else "amber")).strip()
        x = body.get("x")
        y = body.get("y")
        if not text:
            return jsonify({"error": "Note text is required"}), 400

        notes_path = book_dir / "notes.json"
        with notes_lock:
            notes = _load_json(notes_path, [])
            note = {
                "id": f"note-{uuid.uuid4().hex[:8]}",
                "page": page,
                "author": author,
                "text": text,
                "color": color,
                "x": float(x) if x is not None else None,
                "y": float(y) if y is not None else None,
                "replies": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            notes.append(note)
            _save_json(notes_path, notes)
        return jsonify({"note": note, "notes": notes}), 201

    @app.post("/api/books/<raw_id>/notes/<note_id>/replies")
    def add_note_reply(raw_id: str, note_id: str):
        book_id = _safe_book_id(raw_id)
        if not book_id:
            return jsonify({"error": "Invalid book ID"}), 400
        book_dir = target_books_dir / book_id
        notes_path = book_dir / "notes.json"
        if not notes_path.exists():
            return jsonify({"error": "Notes not found"}), 404

        body = request.get_json(silent=True) or {}
        text = (body.get("text") or "").strip()
        author = (body.get("author") or "Reader").strip()[:40] or "Reader"
        if not text:
            return jsonify({"error": "Reply text is required"}), 400

        with notes_lock:
            notes = _load_json(notes_path, [])
            target_note = next((n for n in notes if n.get("id") == note_id), None)
            if not target_note:
                return jsonify({"error": "Note not found"}), 404

            reply = {
                "id": f"rep-{uuid.uuid4().hex[:8]}",
                "author": author,
                "text": text,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            target_note.setdefault("replies", []).append(reply)
            _save_json(notes_path, notes)
        return jsonify({"reply": reply, "notes": notes}), 201

    @app.get("/api/books/<raw_id>/session")
    def get_session(raw_id: str):
        book_id = _safe_book_id(raw_id)
        if not book_id:
            return jsonify({"error": "Invalid book ID"}), 400
        book_dir = target_books_dir / book_id
        if not book_dir.exists():
            return jsonify({"error": "Book not found"}), 404

        now_ts = datetime.now(timezone.utc).timestamp()
        readers = co_reading_sessions.get(book_id, {})
        # Prune stale readers (> 90s inactive)
        active = {
            name: info
            for name, info in readers.items()
            if now_ts - info.get("ts", 0) <= 90
        }
        co_reading_sessions[book_id] = active
        notes = _load_json(book_dir / "notes.json", [])
        return jsonify({"readers": active, "notes": notes})

    @app.post("/api/books/<raw_id>/session")
    def update_session(raw_id: str):
        book_id = _safe_book_id(raw_id)
        if not book_id:
            return jsonify({"error": "Invalid book ID"}), 400
        book_dir = target_books_dir / book_id
        if not book_dir.exists():
            return jsonify({"error": "Book not found"}), 404

        body = request.get_json(silent=True) or {}
        reader = (body.get("reader") or "Reader").strip()[:32] or "Reader"
        page = max(1, int(body.get("page") or 1))
        now = datetime.now(timezone.utc)
        co_reading_sessions.setdefault(book_id, {})[reader] = {
            "page": page,
            "updated_at": now.isoformat(),
            "ts": now.timestamp(),
        }
        return jsonify({"ok": True, "readers": co_reading_sessions[book_id]})

    @app.post("/api/books/<raw_id>/ask-ai")
    def ask_ai_coreader(raw_id: str):
        book_id = _safe_book_id(raw_id)
        if not book_id:
            return jsonify({"error": "Invalid book ID"}), 400
        book_dir = target_books_dir / book_id
        if not book_dir.exists():
            return jsonify({"error": "Book not found"}), 404

        body = request.get_json(silent=True) or {}
        page = max(1, int(body.get("page") or 1))
        prompt = (body.get("prompt") or "Summarize key takeaways").strip()

        text_records = _load_json(book_dir / "text.json", [])
        page_text = next((r.get("text", "") for r in text_records if r.get("page") == page), "").strip()

        if PHI_PATTERN.search(page_text) and not body.get("confirm_phi"):
            return jsonify({
                "error": "Patient identifier (HN/MRN/DOB) detected on this page. AI summary paused for PDPA/PHI safety."
            }), 422

        if not page_text:
            summary = f"[{prompt}] Visual page {page} (no embedded text layer). Add a manual pin to annotate key visual details."
        else:
            words = page_text.split()
            p_lower = prompt.lower()
            if "check" in p_lower or "action" in p_lower:
                chunk1 = " ".join(words[:14])
                chunk2 = " ".join(words[14:28]) if len(words) > 14 else "Review page metrics"
                summary = f"Action Checklist (p.{page}):\n• Verify: {chunk1}\n• Follow-up: {chunk2}"
            elif "clinical" in p_lower or "takeaway" in p_lower:
                excerpt = " ".join(words[:26]) + ("..." if len(words) > 26 else "")
                summary = f"Key Takeaway (p.{page}): {excerpt}"
            else:
                excerpt = " ".join(words[:28]) + ("..." if len(words) > 28 else "")
                summary = f"Co-Reader Summary ({prompt}): {excerpt}"

        notes_path = book_dir / "notes.json"
        with notes_lock:
            notes = _load_json(notes_path, [])
            existing_on_page = [n for n in notes if n.get("page") == page and n.get("x") is not None]
            pin_y = min(85.0, 24.0 + len(existing_on_page) * 14.0)

            note = {
                "id": f"note-{uuid.uuid4().hex[:8]}",
                "page": page,
                "author": "Gobg AI",
                "text": summary,
                "color": "hermes",
                "x": 82.0,
                "y": pin_y,
                "replies": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            notes.append(note)
            _save_json(notes_path, notes)
        return jsonify({"note": note, "notes": notes}), 201

    @app.delete("/api/books/<raw_id>/notes/<note_id>")
    def delete_note(raw_id: str, note_id: str):
        book_id = _safe_book_id(raw_id)
        if not book_id:
            return jsonify({"error": "Invalid book ID"}), 400
        book_dir = target_books_dir / book_id
        notes_path = book_dir / "notes.json"
        if not notes_path.exists():
            return jsonify({"error": "Notes not found"}), 404

        with notes_lock:
            notes = _load_json(notes_path, [])
            updated = [n for n in notes if n.get("id") != note_id]
            _save_json(notes_path, updated)
        return jsonify({"notes": updated})

    @app.get("/api/books/<raw_id>/export-annotated-pdf")
    def export_annotated_pdf(raw_id: str):
        book_id = _safe_book_id(raw_id)
        if not book_id:
            return jsonify({"error": "Invalid book ID"}), 400
        book_dir = target_books_dir / book_id
        if not book_dir.exists():
            return jsonify({"error": "Book not found"}), 404

        meta = _load_json(book_dir / "meta.json", {})
        notes = _load_json(book_dir / "notes.json", [])
        safe_title = re.sub(r"[^a-zA-Z0-9._ -]", "_", meta.get("title", book_id)).strip() or book_id

        pdf_path = book_dir / "source.pdf"
        if pdf_path.exists():
            doc = fitz.open(pdf_path)
        else:
            doc = fitz.open()
            for page_file in sorted((book_dir / "pages").glob("*.webp")):
                with Image.open(page_file) as im:
                    png_buf = io.BytesIO()
                    im.save(png_buf, format="PNG")
                    w_pt, h_pt = im.width * 0.5, im.height * 0.5
                page = doc.new_page(width=w_pt, height=h_pt)
                page.insert_image(page.rect, stream=png_buf.getvalue())

        for idx, note in enumerate(notes, start=1):
            p_num = int(note.get("page") or 1)
            if p_num < 1 or p_num > doc.page_count:
                continue
            page = doc[p_num - 1]
            rect = page.rect
            x_pct = float(note["x"]) if note.get("x") is not None else 86.0
            y_pct = float(note["y"]) if note.get("y") is not None else min(88.0, 14.0 + idx * 8.0)
            px = rect.width * (x_pct / 100.0)
            py = rect.height * (y_pct / 100.0)

            author = note.get("author") or "Reader"
            is_hermes = author.lower().startswith("hermes") or "ai" in author.lower()
            fill_rgb = (0.48, 0.23, 0.93) if is_hermes else (0.77, 0.61, 0.15)

            # Draw visible numbered pin badge on the PDF page
            page.draw_circle(fitz.Point(px, py), 11, color=(1, 1, 1), fill=fill_rgb, width=1.5)
            page.insert_text(fitz.Point(px - (4 if idx < 10 else 7), py + 4), str(idx), fontsize=10, color=(1, 1, 1))

            # Embed interactive PDF sticky note annotation with threaded replies
            lines = [f"#{idx} [{author}]: {note.get('text', '')}"]
            for rep in note.get("replies", []):
                lines.append(f"  ↳ {rep.get('author', 'Reader')}: {rep.get('text', '')}")
            annot = page.add_text_annot(fitz.Point(px + 12, py - 12), "\n".join(lines), icon="Note")
            annot.set_info(title=author)
            annot.update()

        out_buf = io.BytesIO(doc.tobytes(deflate=True))
        doc.close()
        out_buf.seek(0)
        return send_file(
            out_buf,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{safe_title}-Annotated.pdf",
        )

    @app.get("/api/books/<raw_id>/download")
    def download_book(raw_id: str):
        book_id = _safe_book_id(raw_id)
        if not book_id:
            return jsonify({"error": "Invalid book ID"}), 400
        book_dir = target_books_dir / book_id
        if not book_dir.exists():
            return jsonify({"error": "Book not found"}), 404

        meta = _load_json(book_dir / "meta.json", {})
        pdf_path = book_dir / "source.pdf"
        safe_title = re.sub(r"[^a-zA-Z0-9._ -]", "_", meta.get("title", book_id)).strip() or book_id

        if pdf_path.exists():
            return send_file(
                pdf_path,
                as_attachment=True,
                download_name=meta.get("original_filename") or f"{safe_title}.pdf",
            )

        # Package pages into an in-memory ZIP for image/demo books
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for page_file in sorted((book_dir / "pages").glob("*.webp")):
                zf.write(page_file, arcname=page_file.name)
        buf.seek(0)
        return send_file(
            buf,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"{safe_title}.zip",
        )

    return app


if __name__ == "__main__":
    from waitress import serve

    application = create_app()
    print("Virtual Book running at http://127.0.0.1:5055 (Waitress WSGI)")
    serve(application, host="127.0.0.1", port=5055, threads=6)
