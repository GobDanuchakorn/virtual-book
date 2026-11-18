"""Generate a 4-page Thai Breast Biopsy Patient Guide using PyMuPDF (HarfBuzz Thai shaping) + Pastel Pink & Rose-Gold Premium Hospital graphics."""

import io
import json
import math
from pathlib import Path
import fitz  # PyMuPDF
from PIL import Image, ImageDraw


def _draw_rose_gold_frame(draw: ImageDraw.ImageDraw, w: int, h: int, margin: int = 42):
    ROSEGOLD = "#c48b71"
    SOFT_ROSE = "#f3d1dc"
    draw.rectangle([margin, margin, w - margin, h - margin], outline=ROSEGOLD, width=3)
    m2 = margin + 10
    draw.rectangle([m2, m2, w - m2, h - m2], outline=SOFT_ROSE, width=2)
    cs = 16
    for cx, cy in [
        (margin, margin),
        (w - margin - cs, margin),
        (margin, h - margin - cs),
        (w - margin - cs, h - margin - cs),
    ]:
        draw.rectangle([cx, cy, cx + cs, cy + cs], fill="#fdf2f6", outline=ROSEGOLD, width=2)


def _draw_breast_center_crest(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int):
    ROSEGOLD = "#b87a60"
    PINK_DEEP = "#be185d"
    PINK_PASTEL = "#fbcfe8"
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill="#fff5f8", outline=ROSEGOLD, width=3)
    r2 = int(radius * 0.82)
    draw.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], outline="#f4b8ce", width=2)
    for deg in range(0, 360, 30):
        rad = math.radians(deg)
        x1 = cx + int(math.cos(rad) * (radius * 0.35))
        y1 = cy + int(math.sin(rad) * (radius * 0.35))
        x2 = cx + int(math.cos(rad) * r2)
        y2 = cy + int(math.sin(rad) * r2)
        draw.line([x1, y1, x2, y2], fill=PINK_PASTEL, width=2)
    draw.arc([cx - 26, cy - 34, cx + 26, cy + 14], start=180, end=360, fill=PINK_DEEP, width=7)
    draw.line([cx - 22, cy - 10, cx + 18, cy + 32], fill=PINK_DEEP, width=7)
    draw.line([cx + 22, cy - 10, cx - 18, cy + 32], fill="#ec4899", width=7)


def _draw_hospital_hero_graphic(draw: ImageDraw.ImageDraw, x1: int, y1: int, x2: int, y2: int):
    draw.rounded_rectangle([x1, y1, x2, y2], radius=22, fill="#fceef4", outline="#e2a9be", width=2)
    cx = (x1 + x2) // 2
    draw.ellipse([cx - 180, y1 + 22, cx + 180, y1 + 382], fill="#fbdde9")
    draw.ellipse([cx - 128, y1 + 74, cx + 128, y1 + 330], fill="#fff7fa", outline="#c48b71", width=2)

    bx1, by1, bx2, by2 = cx - 108, y1 + 120, cx + 108, y1 + 275
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=12, fill="#ffffff", outline="#c48b71", width=3)
    draw.rounded_rectangle([cx - 62, by1 - 24, cx + 62, by1 + 10], radius=8, fill="#f9c6d9", outline="#c48b71", width=2)
    draw.rectangle([cx - 5, by1 - 18, cx + 5, by1 + 4], fill="#be185d")
    draw.rectangle([cx - 13, by1 - 11, cx + 13, by1 - 3], fill="#be185d")
    for wx in [bx1 + 22, cx - 18, bx2 - 58]:
        draw.rounded_rectangle([wx, by1 + 30, wx + 36, by2 - 18], radius=16, fill="#fce7f3", outline="#d49bae", width=2)


def _draw_ultrasound_icon(draw: ImageDraw.ImageDraw, icx: int, icy: int):
    draw.ellipse([icx - 68, icy - 68, icx + 68, icy + 68], fill="#fce7f3", outline="#c48b71", width=2)
    draw.rounded_rectangle([icx - 26, icy - 58, icx + 26, icy - 40], radius=6, fill="#831843")
    for r_wave in [28, 46, 62]:
        draw.arc([icx - r_wave, icy - 44, icx + r_wave, icy + r_wave], start=45, end=135, fill="#ec4899", width=2)
    draw.ellipse([icx - 15, icy + 8, icx + 15, icy + 34], fill="#f472b6", outline="#9d174d", width=2)
    draw.line([icx + 54, icy - 12, icx + 4, icy + 18], fill="#b87a60", width=4)


DEFAULT_NOTES = [
    {
        "id": "note-hermes-01",
        "page": 2,
        "author": "Hermes",
        "text": "ข้อควรจำ: แจ้งรายการยาละลายลิ่มเลือด (เช่น Aspirin, Plavix, Warfarin) และวิตามินเสริมให้แพทย์ทราบล่วงหน้า 5–7 วันก่อนตรวจ",
        "color": "hermes",
        "x": 84.0,
        "y": 38.0,
        "replies": [],
        "created_at": "2026-11-18T20:35:00+07:00",
    },
    {
        "id": "note-hermes-02",
        "page": 3,
        "author": "Hermes",
        "text": "ระหว่างเก็บชิ้นเนื้อจะได้ยินเสียง 'คลิก' จากเข็มอัตโนมัติ ไม่ต้องตกใจ หลังฉีดยาชาจะรู้สึกเพียงแรงกดเบาๆ เท่านั้น",
        "color": "hermes",
        "x": 84.0,
        "y": 46.0,
        "replies": [],
        "created_at": "2026-11-18T20:35:00+07:00",
    },
    {
        "id": "note-hermes-03",
        "page": 4,
        "author": "Hermes",
        "text": "หลังตรวจแนะนำให้ใช้พาราเซตามอลหากมีอาการตึงแผล และหลีกเลี่ยงยากลุ่ม NSAIDs/Aspirin ใน 48 ชั่วโมงแรก",
        "color": "hermes",
        "x": 84.0,
        "y": 34.0,
        "replies": [],
        "created_at": "2026-11-18T20:35:00+07:00",
    },
]

BASE_CSS = """
body, div {
  font-family: 'Leelawadee UI', Tahoma, sans-serif;
}
.tag {
  font-size: 13.5pt;
  font-weight: bold;
  color: #be185d;
}
.folio-top {
  font-size: 13.5pt;
  font-weight: bold;
  color: #b87a60;
  text-align: right;
}
.h1 {
  font-size: 29pt;
  font-weight: bold;
  color: #4a1d34;
  line-height: 1.25;
  margin-bottom: 6pt;
}
.lead {
  font-size: 16.5pt;
  color: #6d3b53;
  line-height: 1.42;
}
.card-title {
  font-size: 18.5pt;
  font-weight: bold;
  color: #4a1d34;
  margin-bottom: 4pt;
}
.card-body {
  font-size: 16pt;
  color: #5c2c42;
  line-height: 1.42;
}
.callout, .callout b {
  font-size: 16pt;
  color: #fff5f8;
  line-height: 1.42;
}
"""


def _render_bg_with_html(bg_img: Image.Image, boxes: list[tuple[tuple[int, int, int, int], str]]) -> Image.Image:
    """Overlay HarfBuzz-shaped Thai HTML boxes onto a Pillow background image at 1:1 pixel resolution."""
    w, h = bg_img.size
    buf = io.BytesIO()
    bg_img.save(buf, format="PNG")

    doc = fitz.open()
    page = doc.new_page(width=w, height=h)
    page.insert_image(page.rect, stream=buf.getvalue())

    for rect_xy, html in boxes:
        page.insert_htmlbox(fitz.Rect(*rect_xy), html, css=BASE_CSS)

    pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
    out_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return out_img


def ensure_demo_book(books_dir: Path, force: bool = False) -> None:
    """Create the 4-page Pastel Pink Premium Hospital Thai Breast Biopsy Guide with HarfBuzz Thai shaping."""
    book_dir = books_dir / "demo-wellness-guide"
    meta_path = book_dir / "meta.json"
    if meta_path.exists() and not force:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("edition") == "pastel-pink-harfbuzz-v6":
            return

    pages_dir = book_dir / "pages"
    thumbs_dir = book_dir / "thumbs"
    if pages_dir.exists():
        for old_f in pages_dir.glob("*.webp"):
            old_f.unlink()
    if thumbs_dir.exists():
        for old_f in thumbs_dir.glob("*.webp"):
            old_f.unlink()
    pages_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    w, h = 1120, 1500
    PAPER = "#fffafb"
    ROSEGOLD = "#b87a60"
    PINK_DEEP = "#be185d"
    PINK_CARD = "#fdf2f7"
    PINK_BORDER = "#f3c6d8"

    # --- PAGE 1: COVER ---
    bg1 = Image.new("RGB", (w, h), "#fdf2f6")
    d1 = ImageDraw.Draw(bg1)
    d1.rectangle([28, 28, w - 28, h - 28], fill="#fff9fb")
    _draw_rose_gold_frame(d1, w, h, margin=46)
    _draw_breast_center_crest(d1, w // 2, 195, 72)
    d1.rounded_rectangle([w // 2 - 270, 290, w // 2 + 270, 338], radius=24, fill="#fce7f3", outline=ROSEGOLD, width=2)
    _draw_hospital_hero_graphic(d1, 110, 650, w - 110, 995)
    d1.rounded_rectangle([110, 1030, w - 110, 1320], radius=18, fill="#fff0f6", outline=PINK_BORDER, width=2)
    for cy_dot in [1076, 1158, 1240]:
        d1.ellipse([148, cy_dot, 174, cy_dot + 26], fill=PINK_DEEP)

    boxes1 = [
        ((w // 2 - 260, 298, w // 2 + 260, 336), '<div style="text-align:center;font-size:14pt;font-weight:bold;color:#be185d;">BREAST CARE SANCTUARY  •  คู่มือสำหรับผู้ป่วย</div>'),
        ((90, 360, w - 90, 640), '''
          <div style="text-align:center;">
            <div style="font-size:40pt;font-weight:bold;color:#4a1d34;line-height:1.22;">การเจาะชิ้นเนื้อเต้านม<br>เพื่อส่งตรวจทางพยาธิวิทยา</div>
            <div style="font-size:19pt;font-weight:bold;color:#b87a60;margin-top:8pt;">Core Needle Breast Biopsy • Patient Care Guide</div>
            <div style="font-size:18pt;color:#6d3b53;margin-top:8pt;">คู่มือแนะนำขั้นตอนการตรวจ การเตรียมตัว และการดูแลตนเองอย่างอบอุ่นและปลอดภัย</div>
          </div>
        '''),
        ((195, 1064, w - 130, 1120), '<div style="font-size:19pt;font-weight:bold;color:#4a1d34;">แผลเล็กเพียง 2–3 มม. ไม่ต้องเย็บแผล ฟื้นตัวไว</div>'),
        ((195, 1146, w - 130, 1202), '<div style="font-size:19pt;font-weight:bold;color:#4a1d34;">ทำภายใต้ยาชาเฉพาะที่ ใช้เวลาเพียง 30–45 นาที</div>'),
        ((195, 1228, w - 130, 1284), '<div style="font-size:19pt;font-weight:bold;color:#4a1d34;">กลับบ้านได้ทันทีหลังตรวจ ไม่ต้องนอนโรงพยาบาล</div>'),
        ((90, h - 105, w - 90, h - 60), '<div style="text-align:center;font-size:13.5pt;font-weight:bold;color:#b87a60;">EXECUTIVE BREAST CENTER   •   PASTEL PINK EDITION   •   หน้า 01 / 04</div>'),
    ]
    img1 = _render_bg_with_html(bg1, boxes1)

    # --- PAGE 2: OVERVIEW & PREPARATION ---
    bg2 = Image.new("RGB", (w, h), PAPER)
    d2 = ImageDraw.Draw(bg2)
    _draw_rose_gold_frame(d2, w, h, margin=42)
    d2.line([92, 112, w - 92, 112], fill=PINK_BORDER, width=2)
    # Ultrasound biopsy graphic box
    d2.rounded_rectangle([92, 330, w - 92, 520], radius=18, fill="#fff5f9", outline="#e5b2c6", width=2)
    _draw_ultrasound_icon(d2, 215, 425)
    for y_card in [550, 742, 934]:
        d2.rounded_rectangle([92, y_card, w - 92, y_card + 170], radius=14, fill=PINK_CARD, outline=PINK_BORDER, width=2)
        d2.rectangle([92, y_card, 102, y_card + 170], fill=ROSEGOLD)
    d2.rounded_rectangle([92, h - 220, w - 92, h - 95], radius=14, fill="#831843", outline=ROSEGOLD, width=2)

    boxes2 = [
        ((92, 74, w - 250, 108), '<div class="tag">01  •  ความรู้เบื้องต้นและการเตรียมตัว (OVERVIEW & PREPARATION)</div>'),
        ((w - 260, 74, w - 92, 108), '<div class="folio-top">หน้า 02 / 04</div>'),
        ((92, 130, w - 92, 320), '''
          <div class="h1">ทำไมต้องเจาะชิ้นเนื้อเต้านม และเตรียมตัวอย่างไร?</div>
          <div class="lead">การเจาะชิ้นเนื้อเต้านม (Core Needle Biopsy) คือวิธีมาตรฐานที่แม่นยำและปลอดภัยในการวินิจฉัยก้อนหรือจุดหินปูนที่พบจากแมมโมแกรมหรืออัลตราซาวด์ โดยไม่ต้องผ่าตัดใหญ่</div>
        '''),
        ((315, 348, w - 110, 510), '''
          <div style="font-size:14pt;font-weight:bold;color:#9d174d;margin-bottom:4pt;">IMAGE-GUIDED CORE NEEDLE BIOPSY</div>
          <div class="card-body">• แผลขนาดเล็กเพียง 2–3 มม. (เท่าปลายหลอดกาแฟ)<br>• นำทางด้วยอัลตราซาวด์หรือแมมโมแกรม 3 มิติ แม่นยำสูง<br>• <b style="color:#be185d;">มากกว่า 80% ของก้อนที่ตรวจพบมักเป็นเนื้องอกธรรมดา</b></div>
        '''),
        ((126, 566, w - 115, 710), '''
          <div class="card-title">1. แจ้งประวัติยาละลายลิ่มเลือดและโรคประจำตัว</div>
          <div class="card-body">หากท่านรับประทานยาละลายลิ่มเลือดหรือยาต้านเกล็ดเลือด (เช่น Aspirin, Plavix, Warfarin) หรือวิตามินน้ำมันปลา กรุณาแจ้งแพทย์ล่วงหน้า เพราะอาจต้องงดยาก่อนตรวจ 5–7 วัน</div>
        '''),
        ((126, 758, w - 115, 902), '''
          <div class="card-title">2. ไม่ต้องงดน้ำและอาหารก่อนตรวจ</div>
          <div class="card-body">ท่านสามารถรับประทานอาหารและยาประจำตัวอื่นๆ ได้ตามปกติ เนื่องจากการตรวจใช้เพียงการฉีดยาชาเฉพาะที่บริเวณเต้านม</div>
        '''),
        ((126, 950, w - 115, 1096), '''
          <div class="card-title">3. การแต่งกายในวันเข้ารับการตรวจ</div>
          <div class="card-body">งดทาแป้ง โลชั่น น้ำหอม หรือโรลออนบริเวณทรวงอกและรักแร้ในวันตรวจ และแนะนำให้สวมเสื้อผ้าแยกชิ้นบน-ล่าง พร้อมพกเสื้อชั้นในที่กระชับ (Sports Bra) มาสวมหลังตรวจ</div>
        '''),
        ((122, h - 202, w - 122, h - 105), '<div class="callout"><b>ความอุ่นใจของผู้ป่วย:</b> กว่า 80% ของก้อนหรือจุดที่ส่งเจาะชิ้นเนื้อตรวจ พบว่าเป็นเพียงเนื้องอกธรรมดาหรือถุงน้ำที่ไม่ใช่เนื้อร้าย</div>'),
    ]
    img2 = _render_bg_with_html(bg2, boxes2)

    # --- PAGE 3: 4 STEPS OF THE PROCEDURE ---
    bg3 = Image.new("RGB", (w, h), PAPER)
    d3 = ImageDraw.Draw(bg3)
    _draw_rose_gold_frame(d3, w, h, margin=42)
    d3.line([92, 112, w - 92, 112], fill=PINK_BORDER, width=2)
    step_ys = [320, 530, 740, 950]
    for sy in step_ys:
        d3.rounded_rectangle([92, sy, w - 92, sy + 190], radius=16, fill=PINK_CARD, outline=PINK_BORDER, width=2)
        bcx, bcy = 162, sy + 95
        d3.ellipse([bcx - 44, bcy - 44, bcx + 44, bcy + 44], fill="#fce7f3", outline=ROSEGOLD, width=3)
    d3.rounded_rectangle([92, h - 220, w - 92, h - 95], radius=14, fill="#831843", outline=ROSEGOLD, width=2)

    steps_data = [
        ("ขั้นที่ 1", "จัดท่าและระบุพิกัดก้อนด้วยภาพถ่ายรังสี (Imaging Guidance)", "นอนหงายหรือตะแคงบนเตียงตรวจ แพทย์ใช้อัลตราซาวด์หรือเครื่องแมมโมแกรม 3 มิติ ระบุตำแหน่งก้อนอย่างแม่นยำ"),
        ("ขั้นที่ 2", "ทำความสะอาดและฉีดยาชาเฉพาะที่ (Local Anesthesia)", "ทำความสะอาดผิวหนังและฉีดยาชาด้วยเข็มขนาดเล็ก อาจรู้สึกแสบตึงเล็กน้อยช่วงแรก หลังจากนั้นบริเวณที่ตรวจจะชาและไม่เจ็บ"),
        ("ขั้นที่ 3", "เก็บตัวอย่างชิ้นเนื้อด้วยเข็มอัตโนมัติ (Tissue Sampling)", "สอดเข็มผ่านรอยเปิดผิวหนัง 2–3 มม. จะได้ยินเสียง 'คลิก' เบาๆ ประมาณ 3–6 ครั้งขณะเก็บชิ้นเนื้อ อาจรู้สึกตึงหรือมีแรงกดแต่ไม่ปวด"),
        ("ขั้นที่ 4", "กดห้ามเลือดและปิดพลาสเตอร์กันน้ำ (Dressing & Rest)", "กดห้ามเลือด 5–10 นาทีจนเลือดหยุดสนิท ปิดแผลด้วยพลาสเตอร์ยึดแผล (Steri-Strips) และพลาสเตอร์กันน้ำโดยไม่ต้องเย็บแผล"),
    ]
    boxes3 = [
        ((92, 74, w - 250, 108), '<div class="tag">02  •  ขั้นตอนในห้องตรวจ (STEP-BY-STEP PROCEDURE)</div>'),
        ((w - 260, 74, w - 92, 108), '<div class="folio-top">หน้า 03 / 04</div>'),
        ((92, 130, w - 92, 310), '''
          <div class="h1">4 ขั้นตอนการเจาะชิ้นเนื้อเต้านม</div>
          <div class="lead">ดูแลโดยรังสีแพทย์เฉพาะทางเต้านมและทีมพยาบาลวิชาชีพ พร้อมเครื่องมือภาพนำทางความละเอียดสูงตลอดการตรวจ (ใช้เวลาประมาณ 30–45 นาที)</div>
        '''),
    ]
    for sy, (b_num, s_title, s_body) in zip(step_ys, steps_data):
        boxes3.append(((118, sy + 78, 206, sy + 120), f'<div style="text-align:center;font-size:14pt;font-weight:bold;color:#be185d;">{b_num}</div>'))
        boxes3.append(((226, sy + 24, w - 115, sy + 178), f'<div class="card-title">{s_title}</div><div class="card-body">{s_body}</div>'))
    boxes3.append(((122, h - 202, w - 122, h - 105), '<div class="callout"><b>หลังทำหัตถการ:</b> นั่งพักประคบเย็นในห้องรับรอง 15–30 นาที เมื่อแผลเรียบร้อยดีสามารถเดินทางกลับบ้านได้ทันที</div>'))
    img3 = _render_bg_with_html(bg3, boxes3)

    # --- PAGE 4: AFTERCARE & WARNING SIGNS ---
    bg4 = Image.new("RGB", (w, h), PAPER)
    d4 = ImageDraw.Draw(bg4)
    _draw_rose_gold_frame(d4, w, h, margin=42)
    d4.line([92, 112, w - 92, 112], fill=PINK_BORDER, width=2)
    after_ys = [310, 474, 638, 802, 966]
    for ay in after_ys:
        d4.rounded_rectangle([92, ay, w - 92, ay + 146], radius=14, fill=PINK_CARD, outline=PINK_BORDER, width=2)
        d4.ellipse([122, ay + 46, 176, ay + 100], fill=PINK_DEEP, outline=ROSEGOLD, width=2)
    d4.rounded_rectangle([92, h - 245, w - 92, h - 95], radius=14, fill="#fff1f2", outline="#f43f5e", width=2)
    d4.rectangle([92, h - 245, 104, h - 95], fill="#e11d48")

    after_items = [
        ("01", "<b>ประคบเย็นใน 24 ชั่วโมงแรก :</b> ใช้เจลเย็นห่อผ้าสะอาดประคบทับบริเวณแผลครั้งละ 15 นาที ทุก 2–3 ชั่วโมง เพื่อลดอาการบวมและรอยช้ำ"),
        ("02", "<b>ระวังแผลโดนน้ำ 24–48 ชั่วโมง :</b> อาบน้ำได้หากปิดพลาสเตอร์กันน้ำแน่นดี หากพลาสเตอร์หลุดให้ซับแห้งและปิดใหม่ งดแช่น้ำหรือว่ายน้ำ 7 วัน"),
        ("03", "<b>การรับประทานยาแก้ปวด :</b> หากปวดตึงแผลให้รับประทานยาพาราเซตามอล (Paracetamol) งดยากลุ่ม Aspirin หรือ Ibuprofen ใน 48 ชม. แรก"),
        ("04", "<b>สวมเสื้อชั้นในที่กระชับและงดยกของหนัก 2–3 วัน :</b> ช่วยพยุงเต้านม ลดการดึงรั้งแผล และป้องกันเลือดออกซ้ำ"),
        ("05", "<b>การนัดฟังผลตรวจชิ้นเนื้อ :</b> ผลตรวจทางพยาธิวิทยาใช้เวลาประมาณ 3–7 วันทำการ แพทย์จะนัดฟังผลและให้คำแนะนำอย่างละเอียด"),
    ]
    boxes4 = [
        ((92, 74, w - 250, 108), '<div class="tag">03  •  การดูแลตนเองหลังตรวจ (AFTERCARE & RECOVERY)</div>'),
        ((w - 260, 74, w - 92, 108), '<div class="folio-top">หน้า 04 / 04</div>'),
        ((92, 130, w - 92, 300), '''
          <div class="h1">การดูแลแผลและอาการที่ควรสังเกต</div>
          <div class="lead">การดูแลตนเองอย่างถูกวิธีในช่วง 48 ชั่วโมงแรก ช่วยให้แผลสมานตัวเร็ว ลดอาการบวมช้ำ และเคลื่อนไหวได้อย่างมั่นใจ</div>
        '''),
    ]
    for ay, (num_str, item_html) in zip(after_ys, after_items):
        boxes4.append(((122, ay + 58, 176, ay + 95), f'<div style="text-align:center;font-size:14pt;font-weight:bold;color:#ffffff;">{num_str}</div>'))
        boxes4.append(((196, ay + 24, w - 115, ay + 136), f'<div class="card-body">{item_html}</div>'))
    boxes4.append(((128, h - 230, w - 115, h - 102), '''
      <div style="font-size:18.5pt;font-weight:bold;color:#9f1239;margin-bottom:4pt;">อาการผิดปกติที่ควรติดต่อศูนย์เต้านมหรือโรงพยาบาลทันที</div>
      <div style="font-size:15.5pt;color:#881337;line-height:1.4;">• เลือดซึมชุ่มพลาสเตอร์ไม่หยุดหลังกดห้ามเลือดนาน 15 นาที &nbsp; • เต้านมบวมตึงเร็วผิดปกติ &nbsp; • แผลบวมแดงร้อน มีหนอง หรือมีไข้</div>
    '''))
    img4 = _render_bg_with_html(bg4, boxes4)

    all_imgs = [img1, img2, img3, img4]
    search_texts = [
        "การเจาะชิ้นเนื้อเต้านม เพื่อส่งตรวจทางพยาธิวิทยา Breast Biopsy Core Needle คู่มือผู้ป่วย แผลเล็ก ยาชาเฉพาะที่ อัลตราซาวด์ แมมโมแกรม",
        "ทำไมต้องเจาะชิ้นเนื้อเต้านม การเตรียมตัวก่อนตรวจ ยาละลายลิ่มเลือด Aspirin ไม่ต้องงดน้ำและอาหาร งดทาแป้ง โลชั่น Sports Bra เนื้องอกธรรมดา",
        "ขั้นตอนการเจาะชิ้นเนื้อเต้านม จัดท่า อัลตราซาวด์ แมมโมแกรม ฉีดยาชาเฉพาะที่ เข็มอัตโนมัติ เสียงคลิก กดห้ามเลือด พลาสเตอร์กันน้ำ Steri-Strips",
        "การดูแลตนเองหลังเจาะชิ้นเนื้อ ประคบเย็น พาราเซตามอล Paracetamol งดยกของหนัก อาการผิดปกติ เลือดซึม บวมแดง มีไข้ ผลตรวจทางพยาธิวิทยา",
    ]

    text_records = []
    for idx, (im, stext) in enumerate(zip(all_imgs, search_texts), start=1):
        im.save(pages_dir / f"page_{idx:03d}.webp", "WEBP", quality=92)
        thumb = im.copy()
        thumb.thumbnail((260, 360), Image.Resampling.LANCZOS)
        thumb.save(thumbs_dir / f"thumb_{idx:03d}.webp", "WEBP", quality=85)
        text_records.append({"page": idx, "text": stext})

    meta = {
        "id": "demo-wellness-guide",
        "title": "คู่มือผู้ป่วย: การเจาะชิ้นเนื้อเต้านม (Breast Biopsy)",
        "edition": "pastel-pink-harfbuzz-v6",
        "page_count": 4,
        "source_type": "demo",
        "original_filename": None,
        "created_at": "2026-11-18T20:36:00+07:00",
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    (book_dir / "text.json").write_text(json.dumps(text_records, indent=2, ensure_ascii=False), encoding="utf-8")
    (book_dir / "notes.json").write_text(json.dumps(DEFAULT_NOTES, indent=2, ensure_ascii=False), encoding="utf-8")
