"""Automated tests for the Virtual Book Flask application."""

import io
from pathlib import Path
import sys

import fitz
from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import create_app


@pytest.fixture()
def client(tmp_path: Path):
    app = create_app(books_dir=tmp_path / "books")
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def _make_sample_pdf_bytes() -> bytes:
    doc = fitz.open()
    for idx, text in enumerate(["Welcome Cover Page", "Cardiology Screening Guide", "Summary Checklist"], start=1):
        page = doc.new_page(width=400, height=560)
        page.insert_text((40, 80), f"Page {idx}: {text}", fontsize=16)
    buf = doc.tobytes()
    doc.close()
    return buf


def _make_png_bytes(color: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (300, 400), color).save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def test_demo_book_created_and_listed(client):
    res = client.get("/api/books")
    assert res.status_code == 200
    books = res.get_json()["books"]
    assert any(b["id"] == "demo-wellness-guide" and b["page_count"] == 4 for b in books)

    detail = client.get("/api/books/demo-wellness-guide")
    assert detail.status_code == 200
    assert len(detail.get_json()["pages"]) == 4


def test_pdf_upload_search_and_download(client):
    pdf_bytes = _make_sample_pdf_bytes()
    res = client.post(
        "/api/books/upload-pdf",
        data={"title": "Test PDF Book", "file": (io.BytesIO(pdf_bytes), "sample.pdf")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 201
    book = res.get_json()
    assert book["title"] == "Test PDF Book"
    assert book["page_count"] == 3

    # Search for text on page 2
    search_res = client.get(f"/api/books/{book['id']}/search?q=Cardiology")
    assert search_res.status_code == 200
    hits = search_res.get_json()["results"]
    assert len(hits) == 1
    assert hits[0]["page"] == 2

    # Built-in Gobg AI Co-Reader summary pin on page 2
    ai_res = client.post(
        f"/api/books/{book['id']}/ask-ai",
        json={"page": 2, "prompt": "Key Clinical Takeaways"},
    )
    assert ai_res.status_code == 201
    ai_note = ai_res.get_json()["note"]
    assert ai_note["author"] == "Gobg AI"
    assert ai_note["page"] == 2
    assert "Cardiology" in ai_note["text"]

    # Export Annotated PDF with embedded pins
    ann_res = client.get(f"/api/books/{book['id']}/export-annotated-pdf")
    assert ann_res.status_code == 200
    assert ann_res.mimetype == "application/pdf"
    exported_doc = fitz.open(stream=ann_res.data, filetype="pdf")
    annots_p2 = list(exported_doc[1].annots() or [])
    assert len(annots_p2) >= 1
    exported_doc.close()

    # Page image & download
    assert client.get(f"/api/books/{book['id']}/pages/1").status_code == 200
    dl_res = client.get(f"/api/books/{book['id']}/download")
    assert dl_res.status_code == 200


def test_image_batch_upload_and_notes(client):
    res = client.post(
        "/api/books/upload-images",
        data={
            "title": "Photo Album",
            "files": [
                (io.BytesIO(_make_png_bytes((255, 0, 0))), "page10.png"),
                (io.BytesIO(_make_png_bytes((0, 255, 0))), "page2.png"),
            ],
        },
        content_type="multipart/form-data",
    )
    assert res.status_code == 201
    book = res.get_json()
    assert book["page_count"] == 2

    # Add & delete note
    add_res = client.post(
        f"/api/books/{book['id']}/notes",
        json={"page": 2, "author": "Hermes", "text": "Important diagram", "x": 42.5, "y": 31.0},
    )
    assert add_res.status_code == 201
    notes = add_res.get_json()["notes"]
    assert len(notes) == 1
    assert notes[0]["author"] == "Hermes"
    assert notes[0]["x"] == 42.5
    note_id = notes[0]["id"]

    # Add reply to note
    rep_res = client.post(
        f"/api/books/{book['id']}/notes/{note_id}/replies",
        json={"author": "Dan", "text": "Agreed, let's highlight this."},
    )
    assert rep_res.status_code == 201
    assert len(rep_res.get_json()["notes"][0]["replies"]) == 1

    # Co-reading session sync
    sess_post = client.post(
        f"/api/books/{book['id']}/session",
        json={"reader": "Dan", "page": 2},
    )
    assert sess_post.status_code == 200
    sess_get = client.get(f"/api/books/{book['id']}/session")
    assert sess_get.status_code == 200
    assert sess_get.get_json()["readers"]["Dan"]["page"] == 2

    del_res = client.delete(f"/api/books/{book['id']}/notes/{note_id}")
    assert del_res.status_code == 200
    assert del_res.get_json()["notes"] == []


def test_enterprise_security_and_room_isolation(client):
    # Security headers present on HTML response
    home = client.get("/")
    assert home.status_code == 200
    assert home.headers.get("X-Content-Type-Options") == "nosniff"
    assert home.headers.get("Referrer-Policy") == "no-referrer"
    assert "Content-Security-Policy" in home.headers

    # Thai 13-digit ID PHI blocked on note creation
    phi_note = client.post(
        "/api/books/demo-wellness-guide/notes",
        json={"page": 1, "author": "Nurse", "text": "Patient ID 1-1004-00123-45-6"},
    )
    assert phi_note.status_code == 422

    # Co-reading rooms are isolated
    client.post("/api/books/demo-wellness-guide/session", json={"reader": "PatientA", "page": 1, "room": "room-a"})
    client.post("/api/books/demo-wellness-guide/session", json={"reader": "PatientB", "page": 3, "room": "room-b"})
    room_a = client.get("/api/books/demo-wellness-guide/session?room=room-a").get_json()["readers"]
    room_b = client.get("/api/books/demo-wellness-guide/session?room=room-b").get_json()["readers"]
    assert "PatientA" in room_a and "PatientB" not in room_a
    assert "PatientB" in room_b and "PatientA" not in room_b
