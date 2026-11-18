"""Generate a clean, modern, premium executive health monograph (Monocle / Apple Books / Bumrungrad VIP style)."""

import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def _get_font(size: int, kind: str = "sans"):
    font_map = {
        "sans": [
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ],
        "sans_light": [
            "C:/Windows/Fonts/segoeuil.ttf",
            "C:/Windows/Fonts/calibril.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ],
        "sans_semibold": [
            "C:/Windows/Fonts/seguisb.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
        ],
        "sans_bold": [
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ],
        "serif": [
            "C:/Windows/Fonts/georgia.ttf",
            "C:/Windows/Fonts/pala.ttf",
        ],
        "serif_italic": [
            "C:/Windows/Fonts/georgiai.ttf",
            "C:/Windows/Fonts/palai.ttf",
        ],
    }
    for path in font_map.get(kind, font_map["sans"]):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font,
    fill: str,
    max_width: int,
    line_spacing: int = 14,
) -> int:
    x, y = xy
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y += (bbox[3] - bbox[1]) + line_spacing
    return y


def ensure_demo_book(books_dir: Path, force: bool = False) -> None:
    """Create the 8-page clean, modern, premium executive book."""
    book_dir = books_dir / "demo-wellness-guide"
    meta_path = book_dir / "meta.json"
    if meta_path.exists() and not force:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("edition") == "modern-premium-v3":
            return

    pages_dir = book_dir / "pages"
    thumbs_dir = book_dir / "thumbs"
    pages_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    w, h = 1120, 1500
    f_cover_title = _get_font(68, "sans_bold")
    f_cover_sub = _get_font(28, "sans_light")
    f_h1 = _get_font(50, "sans_bold")
    f_h2 = _get_font(28, "sans_semibold")
    f_italic = _get_font(26, "serif_italic")
    f_body = _get_font(25, "sans")
    f_small = _get_font(19, "sans_semibold")
    f_num_lg = _get_font(76, "sans_light")

    PAPER = "#ffffff"
    INK = "#0f172a"
    SLATE = "#475569"
    MUTED = "#94a3b8"
    LINE = "#e2e8f0"
    ACCENT = "#0d9488"  # Modern clinical teal-emerald
    GOLD = "#b48a3e"    # Warm minimalist champagne accent

    pages_spec = [
        {
            "kind": "cover",
            "title": "Executive\nLongevity &\nPreventive Care",
            "subtitle": "Annual Clinical Guide & Health Architecture",
            "footer": "2026 EDITION  •  EXECUTIVE HEALTH CENTER",
            "search_text": (
                "Executive Longevity Preventive Care Annual Clinical Guide "
                "Health Architecture Modern Digital Health Wellness"
            ),
        },
        {
            "kind": "toc",
            "title": "Contents",
            "subtitle": "Five Clinical Pillars for Long-Term Vitality",
            "items": [
                ("01", "Precision Diagnostics & Early Care", "Baseline biomarkers & imaging", "03"),
                ("02", "Metabolic Nutrition & Hydration", "Glycemic stability & cellular fuel", "04"),
                ("03", "Sleep Architecture & Recovery", "Circadian alignment & deep stages", "05"),
                ("04", "Cardiorespiratory Reserve", "Zone 2 conditioning & strength", "06"),
                ("05", "Autonomic Balance & Focus", "Stress resilience & HRV recovery", "07"),
                ("06", "Annual Executive Checklist", "Summary targets & clinical review", "08"),
            ],
            "search_text": (
                "Table of Contents Precision Diagnostics Early Care Metabolic Nutrition "
                "Hydration Sleep Architecture Recovery Cardiorespiratory Reserve "
                "Autonomic Balance Annual Executive Checklist"
            ),
        },
        {
            "kind": "article",
            "num": "01",
            "tag": "PREVENTIVE MEDICINE",
            "title": "Precision Diagnostics & Early Care",
            "lead": "True preventive medicine establishes a longitudinal baseline years before clinical symptoms appear.",
            "metric_label": "EARLY DETECTION IMPACT",
            "metric_val": "3.4×",
            "metric_sub": "Higher intervention success when tracked via annual longitudinal trends",
            "p1": "Comprehensive baseline screening combines advanced lipid sub-fractionation, high-sensitivity metabolic markers, and age-appropriate low-dose imaging to map your personal health trajectory.",
            "p2": "Rather than evaluating isolated single-visit numbers against broad population averages, tracking your personal year-over-year inflection points gives clinicians early, actionable clarity.",
            "callout": "Clinical Key: Maintain a single digital dossier of your annual blood panels, blood pressure trends, and imaging reports.",
            "search_text": (
                "Chapter 01 Preventive Screening Early Care Precision Diagnostics "
                "baseline labs lipid panels imaging coronary calcium longitudinal biomarkers"
            ),
        },
        {
            "kind": "article",
            "num": "02",
            "tag": "METABOLIC HEALTH",
            "title": "Daily Nutrition & Cellular Hydration",
            "lead": "Stable post-meal glucose and steady electrolyte hydration are the foundation of daily cognitive energy.",
            "metric_label": "DAILY FIBER & FLUID TARGET",
            "metric_val": "30g / 2L",
            "metric_sub": "Prebiotic dietary fiber paired with consistent daytime hydration",
            "p1": "A modern preventive plate centers on colorful polyphenol-rich vegetables, clean marine and plant proteins, and extra-virgin unsaturated lipids while minimizing refined glycemic spikes.",
            "p2": "Sequencing fiber and protein before complex carbohydrates flattens post-prandial glucose excursions, protecting vascular endothelium and preventing afternoon fatigue.",
            "callout": "Daily Protocol: Finish evening meals 3 hours before sleep to support overnight metabolic and digestive recovery.",
            "search_text": (
                "Chapter 02 Daily Nutrition Hydration Metabolic Health balanced plate "
                "fiber vegetables lean protein unsaturated fats glucose water intake"
            ),
        },
        {
            "kind": "article",
            "num": "03",
            "tag": "CIRCADIAN MEDICINE",
            "title": "Sleep Architecture & Restoration",
            "lead": "Deep slow-wave and REM sleep drive glymphatic brain clearance, hormonal repair, and memory consolidation.",
            "metric_label": "OPTIMAL SANCTUARY TEMP",
            "metric_val": "18.5°C",
            "metric_sub": "Cool thermal environment with 10–15 min morning outdoor sunlight anchor",
            "p1": "Circadian alignment begins in the morning: natural outdoor daylight within 30 minutes of waking triggers a timed cortisol pulse and sets an automatic 14-hour countdown to evening melatonin release.",
            "p2": "Dimming overhead blue-white lighting 60 minutes before bed and keeping wake times consistent within 30 minutes—even on weekends—preserves deep sleep efficiency.",
            "callout": "Sleep Hygiene: Treat your final hour before bed as a screen-free wind-down ritual in warm, low-lux lighting.",
            "search_text": (
                "Chapter 03 Sleep Architecture Recovery slow-wave REM memory immune "
                "consistent wake time circadian rhythm morning sunlight melatonin"
            ),
        },
        {
            "kind": "article",
            "num": "04",
            "tag": "CARDIORESPIRATORY FITNESS",
            "title": "Movement & Cardiovascular Reserve",
            "lead": "VO2 peak and skeletal muscle mass are two of the strongest independent predictors of healthspan.",
            "metric_label": "WEEKLY CONDITIONING",
            "metric_val": "150m + 2×",
            "metric_sub": "150+ min Zone 2 aerobic training plus 2 resistance sessions per week",
            "p1": "Zone 2 aerobic conditioning—sustained movement at a conversational pace—builds mitochondrial density and metabolic flexibility, training cells to oxidize fat efficiently.",
            "p2": "Pairing aerobic base work with two weekly progressive resistance sessions preserves bone mineral density, insulin sensitivity, and postural stability across decades.",
            "callout": "Micro-Habit: A 5-minute brisk walk after meals reduces post-meal glucose peaks by up to 25%.",
            "search_text": (
                "Chapter 04 Movement Cardiovascular Health Zone 2 aerobic walking cycling "
                "resistance strength training glucose regulation longevity VO2"
            ),
        },
        {
            "kind": "article",
            "num": "05",
            "tag": "AUTONOMIC RESILIENCE",
            "title": "Stress Resilience & Vagal Tone",
            "lead": "Composure under high cognitive load is a measurable, trainable physiological skill.",
            "metric_label": "RAPID DOWNSHIFT CADENCE",
            "metric_val": "4s / 6s",
            "metric_sub": "4-second nasal inhale followed by a 6-second slow exhale activates vagal tone",
            "p1": "Chronic sympathetic activation elevates resting heart rate and fragments sleep architecture. Brief deliberate breathing resets—such as physiological sighs or extended exhalations—shift autonomic balance within 90 seconds.",
            "p2": "Protecting short daily blocks of unplugged stillness or outdoor walking restores executive attention and prevents cumulative decision fatigue.",
            "callout": "2-Minute Reset: Use three slow 4s-in / 6s-out breath cycles before high-stakes clinical or leadership decisions.",
            "search_text": (
                "Chapter 05 Stress Resilience Mindfulness cortisol physiological sighs "
                "breathing mindfulness heart-rate variability vagal tone"
            ),
        },
        {
            "kind": "back",
            "title": "Annual Executive Checklist",
            "subtitle": "Six Core Targets for Long-Term Healthspan",
            "items": [
                ("01", "Annual Preventive Panel & Longitudinal Imaging Review"),
                ("02", "30g+ Daily Prebiotic Fiber & 2L Balanced Hydration"),
                ("03", "7.5–8.5 Hours Consistent Sleep Window + Morning Sunlight"),
                ("04", "150+ Min/Week Zone 2 Cardio + 2× Strength Training"),
                ("05", "Daily 3-Minute Autonomic Breathing or Unplugged Walk"),
                ("06", "Shared Annotations & Follow-Up in Your Virtual Book"),
            ],
            "footer": "Upload any PDF or image set using '+ Upload Book' in the top bar.",
            "search_text": (
                "Quick Reference Checklist Annual Executive Checklist preventive checkup "
                "sleep window aerobic strength fiber stress reset Upload your own PDF"
            ),
        },
    ]

    text_records = []
    for idx, spec in enumerate(pages_spec, start=1):
        if spec["kind"] == "cover":
            img = Image.new("RGB", (w, h), "#0f172a")
            draw = ImageDraw.Draw(img)

            # Modern architectural geometry on right/bottom
            draw.rectangle([0, 0, 24, h], fill=GOLD)
            draw.rectangle([24, 0, 30, h], fill=ACCENT)

            # Subtle modern grid lines
            draw.line([110, 140, w - 110, 140], fill="#1e293b", width=2)
            draw.line([110, h - 160, w - 110, h - 160], fill="#1e293b", width=2)

            # Top badge
            draw.rounded_rectangle([110, 185, 420, 232], radius=23, fill="#1e293b", outline=GOLD, width=1)
            draw.text((265, 208), "EXECUTIVE HEALTH MONOGRAPH", font=f_small, fill="#f8fafc", anchor="mm")

            # Clean modern title
            y_t = 340
            for line in spec["title"].split("\n"):
                draw.text((110, y_t), line, font=f_cover_title, fill="#ffffff")
                y_t += 86

            draw.rectangle([110, y_t + 24, 240, y_t + 30], fill=ACCENT)
            draw.text((110, y_t + 62), spec["subtitle"], font=f_cover_sub, fill="#cbd5e1")

            # Minimalist modern graphic card on lower half
            card_y = 870
            draw.rounded_rectangle([110, card_y, w - 110, card_y + 380], radius=20, fill="#162033", outline="#334155", width=2)
            # Abstract modern rings
            draw.ellipse([w - 430, card_y + 50, w - 150, card_y + 330], outline=GOLD, width=3)
            draw.ellipse([w - 380, card_y + 100, w - 200, card_y + 280], outline=ACCENT, width=3)
            draw.text((160, card_y + 85), "FIVE CLINICAL PILLARS", font=f_small, fill=GOLD)
            draw.text((160, card_y + 130), "Diagnostics • Nutrition\nSleep • Conditioning\nAutonomic Balance", font=f_h2, fill="#f1f5f9", spacing=14)

            draw.text((110, h - 115), spec["footer"], font=f_small, fill="#94a3b8")

        elif spec["kind"] == "toc":
            img = Image.new("RGB", (w, h), PAPER)
            draw = ImageDraw.Draw(img)

            draw.line([96, 105, w - 96, 105], fill=LINE, width=2)
            draw.text((96, 72), "EXECUTIVE LONGEVITY COMPENDIUM", font=f_small, fill=MUTED)
            draw.text((w - 96, 72), "CONTENTS", font=f_small, fill=ACCENT, anchor="ra")

            draw.text((96, 165), spec["title"], font=f_h1, fill=INK)
            draw.text((96, 235), spec["subtitle"], font=f_italic, fill=SLATE)

            y = 335
            for num, label, desc, pg in spec["items"]:
                draw.rounded_rectangle([96, y, w - 96, y + 136], radius=14, fill="#f8fafc", outline=LINE, width=2)
                draw.text((132, y + 28), num, font=f_h1, fill=ACCENT)
                draw.text((230, y + 30), label, font=f_h2, fill=INK)
                draw.text((230, y + 74), desc, font=f_body, fill=SLATE)
                draw.text((w - 135, y + 50), f"p. {pg}", font=f_h2, fill=GOLD, anchor="ra")
                y += 162

            draw.line([96, h - 96, w - 96, h - 96], fill=LINE, width=2)
            draw.text((w // 2, h - 62), f"0{idx}", font=f_small, fill=MUTED, anchor="mm")

        elif spec["kind"] == "article":
            img = Image.new("RGB", (w, h), PAPER)
            draw = ImageDraw.Draw(img)

            # Clean modern top header bar
            draw.line([96, 105, w - 96, 105], fill=LINE, width=2)
            draw.text((96, 72), spec["tag"], font=f_small, fill=ACCENT)
            draw.text((w - 96, 72), f"SECTION {spec['num']}", font=f_small, fill=MUTED, anchor="ra")

            # Large modern number + Title
            draw.text((96, 145), spec["num"], font=f_num_lg, fill=GOLD)
            y = _draw_wrapped_text(draw, spec["title"], (96, 250), f_h1, INK, w - 192, 10)
            y = _draw_wrapped_text(draw, spec["lead"], (96, y + 18), f_italic, SLATE, w - 192, 12)

            # Modern KPI Metric Highlight Card
            card_y = y + 34
            draw.rounded_rectangle([96, card_y, w - 96, card_y + 185], radius=16, fill="#f8fafc", outline=LINE, width=2)
            draw.rounded_rectangle([96, card_y, 106, card_y + 185], radius=4, fill=ACCENT)
            draw.text((140, card_y + 28), spec["metric_label"], font=f_small, fill=ACCENT)
            draw.text((140, card_y + 62), spec["metric_val"], font=f_h1, fill=INK)
            _draw_wrapped_text(draw, spec["metric_sub"], (390, card_y + 68), f_body, SLATE, w - 520, 10)
            y = card_y + 235

            # Body paragraphs
            y = _draw_wrapped_text(draw, spec["p1"], (96, y), f_body, "#1e293b", w - 192, 16)
            y += 30
            y = _draw_wrapped_text(draw, spec["p2"], (96, y), f_body, "#1e293b", w - 192, 16)

            # Bottom Executive Takeaway Box
            box_y = max(y + 36, h - 295)
            draw.rounded_rectangle([96, box_y, w - 96, box_y + 150], radius=14, fill="#0f172a")
            draw.text((132, box_y + 24), "EXECUTIVE TAKEAWAY", font=f_small, fill=GOLD)
            _draw_wrapped_text(draw, spec["callout"], (132, box_y + 58), f_body, "#f8fafc", w - 264, 12)

            draw.line([96, h - 96, w - 96, h - 96], fill=LINE, width=2)
            draw.text((96, h - 62), "Executive Longevity & Preventive Care", font=f_small, fill=MUTED)
            draw.text((w - 96, h - 62), f"0{idx}", font=f_small, fill=INK, anchor="ra")

        elif spec["kind"] == "back":
            img = Image.new("RGB", (w, h), PAPER)
            draw = ImageDraw.Draw(img)

            draw.line([96, 105, w - 96, 105], fill=LINE, width=2)
            draw.text((96, 72), "SUMMARY CHARTER", font=f_small, fill=ACCENT)
            draw.text((96, 160), spec["title"], font=f_h1, fill=INK)
            draw.text((96, 228), spec["subtitle"], font=f_italic, fill=SLATE)

            y = 320
            for num, item in spec["items"]:
                draw.rounded_rectangle([96, y, w - 96, y + 118], radius=14, fill="#f8fafc", outline=LINE, width=2)
                draw.ellipse([128, y + 35, 176, y + 83], fill=ACCENT)
                draw.text((152, y + 59), num, font=f_small, fill="#ffffff", anchor="mm")
                draw.text((206, y + 43), item, font=f_h2, fill=INK)
                y += 144

            draw.text((w // 2, h - 140), spec["footer"], font=f_body, fill=SLATE, anchor="mm")
            draw.line([96, h - 96, w - 96, h - 96], fill=LINE, width=2)
            draw.text((w // 2, h - 62), f"0{idx}", font=f_small, fill=MUTED, anchor="mm")

        page_file = pages_dir / f"page_{idx:03d}.webp"
        thumb_file = thumbs_dir / f"thumb_{idx:03d}.webp"
        img.save(page_file, "WEBP", quality=92)

        thumb = img.copy()
        thumb.thumbnail((260, 360), Image.Resampling.LANCZOS)
        thumb.save(thumb_file, "WEBP", quality=85)

        text_records.append({"page": idx, "text": spec["search_text"]})

    meta = {
        "id": "demo-wellness-guide",
        "title": "Executive Longevity & Preventive Care",
        "edition": "modern-premium-v3",
        "page_count": len(pages_spec),
        "source_type": "demo",
        "original_filename": None,
        "created_at": "2026-11-18T19:41:00+07:00",
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (book_dir / "text.json").write_text(json.dumps(text_records, indent=2), encoding="utf-8")
    if not (book_dir / "notes.json").exists():
        (book_dir / "notes.json").write_text("[]", encoding="utf-8")
