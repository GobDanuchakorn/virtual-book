(() => {
  "use strict";

  const state = {
    book: null,
    books: [],
    currentPage: 1,
    isFlipping: false,
    soundEnabled: false,
    zoom: 1,
    panX: 0,
    panY: 0,
    isDragging: false,
    dragStartX: 0,
    dragStartY: 0,
    uploadMode: "pdf",
    leftPanel: null,
    rightPanelOpen: false,
    audioCtx: null,
    pinMode: false,
    pendingPin: null, // { page, x, y }
    readerName: localStorage.getItem("vb_reader_name") || "Dan",
    followSync: false,
    readers: {},
    syncTimer: null,
  };

  const el = (id) => document.getElementById(id);

  let toastTimer = null;
  function showToast(msg, isError = false) {
    const box = el("app-toast");
    if (!box) return;
    box.textContent = msg;
    box.classList.toggle("is-error", Boolean(isError));
    box.classList.remove("hidden");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => box.classList.add("hidden"), 4500);
  }

  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function isSingleMode() {
    return window.innerWidth < 820;
  }

  function getSpreadForPage(pageNum, total) {
    if (total <= 0) return { left: null, right: null };
    const p = Math.max(1, Math.min(pageNum, total));
    if (isSingleMode()) {
      return { left: null, right: p, single: true };
    }
    if (p === 1) {
      return { left: null, right: 1, single: true };
    }
    if (p === total && total % 2 === 0) {
      return { left: total, right: null, single: true };
    }
    const left = p % 2 === 0 ? p : p - 1;
    const right = left + 1 <= total ? left + 1 : null;
    return { left, right, single: right === null };
  }

  function playFlipSound() {
    if (!state.soundEnabled) return;
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return;
      if (!state.audioCtx) state.audioCtx = new AudioContext();
      const ctx = state.audioCtx;
      if (ctx.state === "suspended") ctx.resume();

      const duration = 0.15;
      const sampleRate = ctx.sampleRate;
      const buffer = ctx.createBuffer(1, sampleRate * duration, sampleRate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < data.length; i++) {
        const env = Math.sin((i / data.length) * Math.PI);
        data[i] = (Math.random() * 2 - 1) * env * 0.2;
      }

      const noise = ctx.createBufferSource();
      noise.buffer = buffer;

      const filter = ctx.createBiquadFilter();
      filter.type = "bandpass";
      filter.frequency.setValueAtTime(1450, ctx.currentTime);
      filter.frequency.exponentialRampToValueAtTime(520, ctx.currentTime + duration);
      filter.Q.value = 1.1;

      noise.connect(filter);
      filter.connect(ctx.destination);
      noise.start();
    } catch {
      // Ignore audio restrictions
    }
  }

  function updateHash() {
    if (!state.book) return;
    const hash = `#book=${encodeURIComponent(state.book.id)}&page=${state.currentPage}`;
    if (window.location.hash !== hash) {
      history.replaceState(null, "", hash);
    }
  }

  function parseHash() {
    const raw = window.location.hash.replace(/^#/, "");
    const params = new URLSearchParams(raw);
    return {
      bookId: params.get("book"),
      page: parseInt(params.get("page") || "1", 10) || 1,
    };
  }

  function applyZoomTransform() {
    const layer = el("book-pan-layer");
    layer.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`;
    layer.classList.toggle("is-zoomed", state.zoom > 1);

    const zoomPill = el("zoom-pill");
    const zoomReset = el("btn-zoom-reset");
    if (state.zoom > 1) {
      zoomPill.classList.remove("hidden");
      zoomReset.textContent = `${Math.round(state.zoom * 100)}% (Reset)`;
    } else {
      zoomPill.classList.add("hidden");
    }

    el("icon-zoom-in").classList.toggle("hidden", state.zoom >= 2.2);
    el("icon-zoom-out").classList.toggle("hidden", state.zoom < 2.2);
    if (typeof showZoomHud === "function") showZoomHud(state.zoom);
  }

  function resetZoom() {
    state.zoom = 1;
    state.panX = 0;
    state.panY = 0;
    applyZoomTransform();
  }

  function cycleZoom() {
    if (state.zoom === 1) state.zoom = 1.65;
    else if (state.zoom < 2.2) state.zoom = 2.3;
    else {
      resetZoom();
      return;
    }
    applyZoomTransform();
  }

  function updatePaperStacks(spread, total) {
    const coverFrame = el("book-cover-frame");
    const stackLeft = el("stack-left");
    const stackRight = el("stack-right");

    const isCover = Boolean(spread.single);
    coverFrame.classList.toggle("is-cover", isCover);

    if (isSingleMode()) {
      stackLeft.classList.add("hidden");
      stackRight.classList.add("hidden");
      return;
    }

    const leftRatio = spread.left ? (spread.left - 1) / Math.max(1, total - 1) : 0;
    const rightRatio = spread.right ? (total - spread.right) / Math.max(1, total - 1) : 0;

    if (spread.left && leftRatio > 0.02) {
      stackLeft.classList.remove("hidden");
      stackLeft.style.width = `${Math.round(3 + leftRatio * 11)}px`;
    } else {
      stackLeft.classList.add("hidden");
    }

    if (spread.right && rightRatio > 0.02) {
      stackRight.classList.remove("hidden");
      stackRight.style.width = `${Math.round(3 + rightRatio * 11)}px`;
    } else {
      stackRight.classList.add("hidden");
    }
  }

  function renderPagePins(spread) {
    const leftLayer = el("pins-left");
    const rightLayer = el("pins-right");
    leftLayer.innerHTML = "";
    rightLayer.innerHTML = "";
    if (!state.book) return;

    const notes = state.book.notes || [];
    notes.forEach((note, idx) => {
      if (note.x == null || note.y == null) return;
      let targetLayer = null;
      if (spread.left === note.page) targetLayer = leftLayer;
      else if (spread.right === note.page) targetLayer = rightLayer;
      if (!targetLayer) return;

      const pin = document.createElement("button");
      pin.type = "button";
      const isHermes = (note.author || "").toLowerCase().startsWith("hermes") || (note.author || "").toLowerCase().includes("ai");
      pin.className = "page-pin" + (isHermes ? " hermes" : "");
      pin.style.left = `${note.x}%`;
      pin.style.top = `${note.y}%`;
      pin.title = `${note.author || "Reader"}: ${note.text}`;
      pin.setAttribute("aria-label", `Pin ${idx + 1} by ${note.author || "Reader"} on page ${note.page}`);
      pin.innerHTML = `<span>${idx + 1}</span>`;
      pin.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleNotesPanel(true);
      });
      targetLayer.appendChild(pin);
    });
  }

  const CANVAS_PAD = 80;

  function getCoverShiftPercent(spread) {
    if (isSingleMode()) return 0;
    if (!spread.left && spread.right) return -25;
    if (spread.left && !spread.right) return 25;
    return 0;
  }

  function renderBookSpread() {
    if (!state.book) return;
    const total = state.book.page_count;
    const spread = getSpreadForPage(state.currentPage, total);

    const coverFrame = el("book-cover-frame");
    const container = el("book-container");
    const leftSlot = el("page-left-slot");
    const rightSlot = el("page-right-slot");
    const spine = el("book-spine");
    const imgLeft = el("img-left");
    const imgRight = el("img-right");

    const singleMobile = isSingleMode();
    container.classList.toggle("single-cover", Boolean(spread.single) && singleMobile);
    container.classList.toggle("single-mode", singleMobile);

    const shiftPct = getCoverShiftPercent(spread);
    coverFrame.style.transform = shiftPct !== 0 ? `translateX(${shiftPct}%)` : "translateX(0%)";

    if (singleMobile) {
      leftSlot.classList.add("hidden");
      leftSlot.classList.remove("empty-slot");
      rightSlot.classList.remove("hidden", "empty-slot");
      const activePage = spread.right || spread.left || 1;
      imgRight.src = state.book.pages[activePage - 1].image_url;
    } else {
      // Desktop: always keep both slots in layout (2W width) so opening/closing cover never clips
      leftSlot.classList.remove("hidden");
      rightSlot.classList.remove("hidden");
      if (spread.left) {
        imgLeft.src = state.book.pages[spread.left - 1].image_url;
        leftSlot.classList.remove("empty-slot");
      } else {
        imgLeft.src = state.book.pages[0].image_url;
        leftSlot.classList.add("empty-slot");
      }

      if (spread.right) {
        imgRight.src = state.book.pages[spread.right - 1].image_url;
        rightSlot.classList.remove("empty-slot");
      } else {
        imgRight.src = state.book.pages[0].image_url;
        rightSlot.classList.add("empty-slot");
      }
    }

    spine.classList.toggle("hidden", !(spread.left && spread.right));
    updatePaperStacks(spread, total);
    renderPagePins(spread);

    el("page-input").value = String(state.currentPage);
    el("page-total").textContent = `/ ${total}`;
    el("btn-first").disabled = state.currentPage <= 1;
    el("btn-prev").disabled = state.currentPage <= 1;
    el("btn-next").disabled = state.currentPage >= total;
    el("btn-last").disabled = state.currentPage >= total;

    const activePages = new Set([spread.left, spread.right].filter(Boolean));
    document.querySelectorAll(".thumb-item").forEach((node) => {
      const p = Number(node.dataset.page);
      node.classList.toggle("active", activePages.has(p));
    });

    const noteSelect = el("note-page-select");
    if (noteSelect && noteSelect.options.length === total) {
      noteSelect.value = String(state.currentPage);
    }

    updateHash();
    pushSessionHeartbeat();
    el("book-cover-frame").style.setProperty("--flip", "0");
    if (typeof syncEditorialDock === "function") syncEditorialDock(state.currentPage, total);
    if (typeof renderAiContextChips === "function") renderAiContextChips(state.currentPage);
  }

  const imgCache = new Map();

  function getCachedImage(pageNum) {
    if (!state.book || !pageNum || pageNum < 1 || pageNum > state.book.page_count) return null;
    const url = state.book.pages[pageNum - 1].image_url;
    if (imgCache.has(url)) return imgCache.get(url);
    const img = new Image();
    img.src = url;
    imgCache.set(url, img);
    return img;
  }

  function preloadNearbyImages() {
    if (!state.book) return;
    for (let p = Math.max(1, state.currentPage - 3); p <= Math.min(state.book.page_count, state.currentPage + 4); p++) {
      getCachedImage(p);
    }
  }

  function constrainFoldPoint(px, py, spineX, cy, pageW, pageH) {
    let x = px;
    let y = py;
    // Constraint 1: distance from near spine corner (spineX, cy) <= pageW
    const dx1 = x - spineX;
    const dy1 = y - cy;
    const d1 = Math.hypot(dx1, dy1);
    if (d1 > pageW && d1 > 0.001) {
      x = spineX + (dx1 / d1) * pageW;
      y = cy + (dy1 / d1) * pageW;
    }
    // Constraint 2: distance from far spine corner (spineX, farY) <= hypot(pageW, pageH)
    const farY = cy === 0 ? pageH : 0;
    const maxDiag = Math.hypot(pageW, pageH);
    const dx2 = x - spineX;
    const dy2 = y - farY;
    const d2 = Math.hypot(dx2, dy2);
    if (d2 > maxDiag && d2 > 0.001) {
      x = spineX + (dx2 / d2) * maxDiag;
      y = farY + (dy2 / d2) * maxDiag;
    }
    return { x, y };
  }

  function setupRetinaCanvas(canvas, totalW, totalH) {
    const dpr = Math.min(2.5, window.devicePixelRatio || 1);
    const pad2 = CANVAS_PAD * 2;
    const targetW = Math.round((totalW + pad2) * dpr);
    const targetH = Math.round((totalH + pad2) * dpr);
    if (canvas.width !== targetW || canvas.height !== targetH) {
      canvas.width = targetW;
      canvas.height = targetH;
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, CANVAS_PAD * dpr, CANVAS_PAD * dpr);
    return { ctx, dpr };
  }

  function drawCurvedBackPage(ctx, img, localX, localY, w, h, dist) {
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(localX, localY, w, h);
    if (!img || !img.complete || img.naturalWidth === 0) return;

    const strips = 18;
    const natW = img.naturalWidth;
    const natH = img.naturalHeight;
    const stripW = w / strips;
    const srcStripW = natW / strips;
    const archAmp = Math.min(14, dist * 0.045);

    for (let i = 0; i < strips; i++) {
      const t = (i + 0.5) / strips;
      const curveOffsetY = -Math.sin(t * Math.PI) * archAmp;
      const sx = i * srcStripW;
      const dx = localX + i * stripW;
      ctx.drawImage(
        img,
        sx,
        0,
        srcStripW + 0.6,
        natH,
        dx,
        localY + curveOffsetY,
        stripW + 0.6,
        h
      );
    }
  }

  function drawPaperFoldFrame(ctx, cfg) {
    const {
      direction, // "next" | "prev"
      totalW,
      totalH,
      pageW,
      spineX,
      ox,
      cy,
      px,
      py,
      frontImg,
      backImg,
      underImg,
      staticImg,
      isSingle,
    } = cfg;
    const dpr = Math.min(2.5, window.devicePixelRatio || 1);
    const setWorldTransform = () => {
      ctx.setTransform(dpr, 0, 0, dpr, CANVAS_PAD * dpr, CANVAS_PAD * dpr);
    };

    setWorldTransform();
    ctx.clearRect(-CANVAS_PAD, -CANVAS_PAD, totalW + CANVAS_PAD * 2, totalH + CANVAS_PAD * 2);

    const drawPageOrPaper = (img, x, y, w, h, withShadow = false) => {
      if (withShadow) {
        ctx.save();
        ctx.shadowColor = "rgba(15, 23, 42, 0.22)";
        ctx.shadowBlur = 28;
        ctx.shadowOffsetY = 10;
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(x, y, w, h);
        ctx.restore();
      } else {
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(x, y, w, h);
      }
      if (img && img.complete && img.naturalWidth > 0) {
        ctx.drawImage(img, x, y, w, h);
      }
    };

    const pageStartX = isSingle ? 0 : direction === "next" ? spineX : 0;

    // 1. Draw static opposite page ONLY if it exists (leave empty cover half transparent!)
    if (!isSingle && staticImg) {
      const oppX = direction === "next" ? 0 : spineX;
      drawPageOrPaper(staticImg, oppX, 0, pageW, totalH, true);
    }

    // 2. Draw active turning page (frontImg) clipped to the unpeeled side (-n side of fold line)
    const vx = ox - px;
    const vy = cy - py;
    const dist = Math.hypot(vx, vy);
    const flipProgress = Math.min(1, Math.max(0, dist / Math.max(1, pageW * 2)));
    el("book-cover-frame").style.setProperty("--flip", Math.sin(flipProgress * Math.PI).toFixed(3));
    if (dist < 1.5) {
      drawPageOrPaper(frontImg, pageStartX, 0, pageW, totalH, true);
      return;
    }

    const mx = (ox + px) * 0.5;
    const my = (cy + py) * 0.5;
    const nx = vx / dist; // Unit normal pointing toward original corner O
    const ny = vy / dist;
    const tx = -ny;       // Unit tangent along fold line
    const ty = nx;
    const BIG = Math.max(totalW, totalH) * 3;

    const l1x = mx - tx * BIG;
    const l1y = my - ty * BIG;
    const l2x = mx + tx * BIG;
    const l2y = my + ty * BIG;

    // 2b. Unpeeled portion of frontImg (-n side of fold line)
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(l1x, l1y);
    ctx.lineTo(l2x, l2y);
    ctx.lineTo(l2x - nx * BIG, l2y - ny * BIG);
    ctx.lineTo(l1x - nx * BIG, l1y - ny * BIG);
    ctx.closePath();
    ctx.clip();
    drawPageOrPaper(frontImg, pageStartX, 0, pageW, totalH, true);
    ctx.restore();

    // 3. Peeled region (+n side of fold line): reveal underImg ONLY if it exists (transparent when closing cover!)
    if (underImg) {
      ctx.save();
      ctx.beginPath();
      ctx.rect(pageStartX, 0, pageW, totalH);
      ctx.clip();

      ctx.beginPath();
      ctx.moveTo(l1x, l1y);
      ctx.lineTo(l2x, l2y);
      ctx.lineTo(l2x + nx * BIG, l2y + ny * BIG);
      ctx.lineTo(l1x + nx * BIG, l1y + ny * BIG);
      ctx.closePath();
      ctx.clip();

      drawPageOrPaper(underImg, pageStartX, 0, pageW, totalH, false);

      const underShadowW = Math.min(95, dist * 0.45);
      if (underShadowW > 2) {
        const uGrad = ctx.createLinearGradient(mx, my, mx + nx * underShadowW, my + ny * underShadowW);
        uGrad.addColorStop(0, "rgba(15, 23, 42, 0.38)");
        uGrad.addColorStop(0.45, "rgba(15, 23, 42, 0.14)");
        uGrad.addColorStop(1, "rgba(15, 23, 42, 0)");
        ctx.fillStyle = uGrad;
        ctx.fillRect(pageStartX, 0, pageW, totalH);
      }
      ctx.restore();
    }

    // 4. Draw folded backside flap (-n side of fold line, including into the 80px bleed pad!)
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(l1x, l1y);
    ctx.lineTo(l2x, l2y);
    ctx.lineTo(l2x - nx * BIG, l2y - ny * BIG);
    ctx.lineTo(l1x - nx * BIG, l1y - ny * BIG);
    ctx.closePath();
    ctx.clip();

    const theta = direction === "next"
      ? Math.atan2(cy - py, ox - px)
      : Math.atan2(cy - py, px - ox);
    const rotAngle = direction === "next" ? 2 * theta : -2 * theta;
    const localX = direction === "next" ? 0 : -pageW;
    const localY = -cy;

    // 4a. Drop shadow cast by the lifted flap
    ctx.save();
    ctx.translate(px, py);
    ctx.rotate(rotAngle);
    ctx.shadowColor = "rgba(15, 23, 42, 0.34)";
    ctx.shadowBlur = Math.min(34, 8 + dist * 0.08);
    ctx.shadowOffsetX = -nx * 8;
    ctx.shadowOffsetY = -ny * 8;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(localX, localY, pageW, totalH);
    ctx.restore();

    // 4b. Clip to the reflected sheet boundary and draw curved strip-warped backImg
    ctx.save();
    ctx.translate(px, py);
    ctx.rotate(rotAngle);
    ctx.beginPath();
    ctx.rect(localX, localY, pageW, totalH);
    ctx.clip();

    drawCurvedBackPage(ctx, backImg, localX, localY, pageW, totalH, dist);
    ctx.restore();

    // 4c. Cylindrical paper-bend highlight & fold shadow across the flap
    const flapSpan = Math.max(24, dist * 0.52);
    const fGrad = ctx.createLinearGradient(mx, my, mx - nx * flapSpan, my - ny * flapSpan);
    fGrad.addColorStop(0, "rgba(15, 23, 42, 0.22)");
    fGrad.addColorStop(0.14, "rgba(255, 255, 255, 0.55)");
    fGrad.addColorStop(0.45, "rgba(255, 255, 255, 0.0)");
    fGrad.addColorStop(0.85, "rgba(15, 23, 42, 0.06)");
    fGrad.addColorStop(1, "rgba(15, 23, 42, 0.18)");

    ctx.save();
    ctx.translate(px, py);
    ctx.rotate(rotAngle);
    ctx.beginPath();
    ctx.rect(localX, localY, pageW, totalH);
    ctx.clip();
    setWorldTransform();
    ctx.fillStyle = fGrad;
    ctx.fillRect(-CANVAS_PAD, -CANVAS_PAD, totalW + CANVAS_PAD * 2, totalH + CANVAS_PAD * 2);
    ctx.restore();

    // 4d. Crisp fold-crease highlight line along the bend
    ctx.save();
    ctx.translate(px, py);
    ctx.rotate(rotAngle);
    ctx.beginPath();
    ctx.rect(localX, localY, pageW, totalH);
    ctx.clip();
    setWorldTransform();
    ctx.strokeStyle = "rgba(226, 232, 240, 0.85)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(l1x, l1y);
    ctx.lineTo(l2x, l2y);
    ctx.stroke();
    ctx.restore();

    ctx.restore();

    // 5. Spine crease shadow when both left and right pages are visible
    if (!isSingle && (staticImg || dist > pageW * 0.35)) {
      const sGrad = ctx.createLinearGradient(spineX - 22, 0, spineX + 22, 0);
      sGrad.addColorStop(0, "rgba(15, 23, 42, 0)");
      sGrad.addColorStop(0.48, "rgba(15, 23, 42, 0.18)");
      sGrad.addColorStop(0.5, "rgba(100, 116, 139, 0.35)");
      sGrad.addColorStop(0.52, "rgba(15, 23, 42, 0.18)");
      sGrad.addColorStop(1, "rgba(15, 23, 42, 0)");
      ctx.fillStyle = sGrad;
      ctx.fillRect(spineX - 22, 0, 44, totalH);
    }
  }

  function prepareFoldConfig(direction, targetPage, cornerV = "bottom") {
    const total = state.book.page_count;
    const prevSpread = getSpreadForPage(state.currentPage, total);
    const nextSpread = getSpreadForPage(targetPage, total);

    const container = el("book-container");
    const rect = container.getBoundingClientRect();
    const totalW = Math.max(300, Math.round(rect.width));
    const totalH = Math.max(360, Math.round(rect.height));
    const isSingle = isSingleMode();
    const pageW = isSingle ? totalW : Math.round(totalW / 2);
    const spineX = isSingle ? (direction === "next" ? 0 : totalW) : pageW;

    const ox = direction === "next" ? totalW : 0;
    const cy = cornerV === "top" ? 0 : totalH;

    const frontPageNum = direction === "next"
      ? (prevSpread.right || prevSpread.left)
      : (prevSpread.left || prevSpread.right);
    const backPageNum = direction === "next"
      ? (nextSpread.left || nextSpread.right)
      : (nextSpread.right || nextSpread.left);
    const underPageNum = isSingle
      ? (nextSpread.right || nextSpread.left)
      : (direction === "next" ? nextSpread.right : nextSpread.left);
    const staticPageNum = isSingle
      ? null
      : (direction === "next" ? prevSpread.left : prevSpread.right);

    return {
      direction,
      targetPage,
      totalW,
      totalH,
      pageW,
      spineX,
      ox,
      cy,
      isSingle,
      startShiftPct: getCoverShiftPercent(prevSpread),
      endShiftPct: getCoverShiftPercent(nextSpread),
      frontImg: getCachedImage(frontPageNum),
      backImg: getCachedImage(backPageNum),
      underImg: getCachedImage(underPageNum),
      staticImg: getCachedImage(staticPageNum),
    };
  }

  function animateFlip(direction, targetPage, startPos = null, cornerV = "bottom") {
    if (!state.book || state.isFlipping) return;
    const total = state.book.page_count;
    const clamped = Math.max(1, Math.min(targetPage, total));
    if (clamped === state.currentPage) return;

    preloadNearbyImages();
    const cfg = prepareFoldConfig(direction, clamped, cornerV);
    const canvas = el("fold-canvas");
    const coverFrame = el("book-cover-frame");
    const { ctx } = setupRetinaCanvas(canvas, cfg.totalW, cfg.totalH);
    coverFrame.classList.add("is-folding");
    canvas.classList.remove("hidden");

    state.isFlipping = true;
    playFlipSound();

    const startX = startPos ? startPos.x : (direction === "next" ? cfg.totalW - 22 : 22);
    const startY = startPos ? startPos.y : (cfg.cy === 0 ? 18 : cfg.totalH - 18);
    const endX = direction === "next" ? (cfg.isSingle ? -cfg.pageW : 0) : (cfg.isSingle ? cfg.totalW + cfg.pageW : cfg.totalW);
    const endY = cfg.cy;

    const duration = startPos ? 380 : 580;
    const t0 = performance.now();

    function stepFrame(now) {
      const raw = Math.min(1, (now - t0) / duration);
      const ease = raw < 0.5 ? 4 * raw * raw * raw : 1 - Math.pow(-2 * raw + 2, 3) / 2;

      const curX = startX + (endX - startX) * ease;
      const archLift = (cfg.cy === 0 ? 1 : -1) * Math.sin(raw * Math.PI) * (cfg.totalH * 0.14);
      const curY = startY + (endY - startY) * ease + archLift;

      // Smoothly glide cover centering (-25% <-> 0% <-> +25%) as cover opens/closes
      const curShift = cfg.startShiftPct + (cfg.endShiftPct - cfg.startShiftPct) * ease;
      coverFrame.style.transform = `translateX(${curShift}%)`;

      const clampedPt = constrainFoldPoint(curX, curY, cfg.spineX, cfg.cy, cfg.pageW, cfg.totalH);
      drawPaperFoldFrame(ctx, { ...cfg, px: clampedPt.x, py: clampedPt.y });

      if (raw < 1) {
        requestAnimationFrame(stepFrame);
      } else {
        state.currentPage = clamped;
        coverFrame.classList.remove("is-folding");
        canvas.classList.add("hidden");
        renderBookSpread();
        state.isFlipping = false;
        preloadNearbyImages();
      }
    }

    requestAnimationFrame(stepFrame);
  }

  function goNext() {
    if (!state.book) return;
    const total = state.book.page_count;
    if (state.currentPage >= total) return;
    const step = isSingleMode() || state.currentPage === 1 ? 1 : 2;
    animateFlip("next", Math.min(total, state.currentPage + step));
  }

  function goPrev() {
    if (!state.book) return;
    if (state.currentPage <= 1) return;
    const step = isSingleMode() || state.currentPage <= 2 ? 1 : 2;
    animateFlip("prev", Math.max(1, state.currentPage - step));
  }

  function jumpToPage(pageNum) {
    if (!state.book) return;
    const total = state.book.page_count;
    const target = Math.max(1, Math.min(pageNum, total));
    if (target === state.currentPage) return;
    const dir = target > state.currentPage ? "next" : "prev";
    animateFlip(dir, target);
  }

  // Interactive Corner Peel & Full Conical Drag-to-Fold
  function setupDragToFlip() {
    const rightZone = document.querySelector(".click-zone-right");
    const leftZone = document.querySelector(".click-zone-left");
    const canvas = el("fold-canvas");
    const coverFrame = el("book-cover-frame");

    function attachDrag(zone, direction) {
      zone.addEventListener("pointermove", (e) => {
        if (state.pinMode || state.zoom > 1 || state.isFlipping || !state.book || e.buttons !== 0) return;
        const total = state.book.page_count;
        if (direction === "next" && state.currentPage >= total) return;
        if (direction === "prev" && state.currentPage <= 1) return;

        const rect = el("book-container").getBoundingClientRect();
        const relY = e.clientY - rect.top;
        const isTopCorner = relY < 95;
        const isBottomCorner = rect.height - relY < 95;

        if (!isTopCorner && !isBottomCorner) {
          if (!state.isFlipping) {
            coverFrame.classList.remove("is-folding");
            canvas.classList.add("hidden");
          }
          return;
        }

        preloadNearbyImages();
        const step = direction === "next"
          ? (isSingleMode() || state.currentPage === 1 ? 1 : 2)
          : (isSingleMode() || state.currentPage <= 2 ? 1 : 2);
        const targetPage = direction === "next"
          ? Math.min(total, state.currentPage + step)
          : Math.max(1, state.currentPage - step);
        const cornerV = isTopCorner ? "top" : "bottom";
        const cfg = prepareFoldConfig(direction, targetPage, cornerV);

        const { ctx } = setupRetinaCanvas(canvas, cfg.totalW, cfg.totalH);
        coverFrame.classList.add("is-folding");
        canvas.classList.remove("hidden");

        const peelX = direction === "next" ? cfg.totalW - 44 : 44;
        const peelY = isTopCorner ? 38 : cfg.totalH - 38;
        const pt = constrainFoldPoint(peelX, peelY, cfg.spineX, cfg.cy, cfg.pageW, cfg.totalH);
        drawPaperFoldFrame(ctx, { ...cfg, px: pt.x, py: pt.y });
      });

      zone.addEventListener("pointerleave", () => {
        if (!state.isFlipping) {
          coverFrame.classList.remove("is-folding");
          canvas.classList.add("hidden");
        }
      });

      zone.addEventListener("pointerdown", (e) => {
        if (isSingleMode()) return; // Mobile single-page mode uses full-page touch handler below
        if (state.pinMode || state.zoom > 1 || state.isFlipping || !state.book) return;
        const total = state.book.page_count;
        if (direction === "next" && state.currentPage >= total) return;
        if (direction === "prev" && state.currentPage <= 1) return;

        try {
          if (e.pointerId != null) zone.setPointerCapture(e.pointerId);
        } catch {}

        preloadNearbyImages();
        const startClientX = e.clientX;
        const startClientY = e.clientY;
        let moved = false;

        const rect = el("book-container").getBoundingClientRect();
        const cornerV = (e.clientY - rect.top) < rect.height * 0.35 ? "top" : "bottom";
        const step = direction === "next"
          ? (isSingleMode() || state.currentPage === 1 ? 1 : 2)
          : (isSingleMode() || state.currentPage <= 2 ? 1 : 2);
        const targetPage = direction === "next"
          ? Math.min(total, state.currentPage + step)
          : Math.max(1, state.currentPage - step);

        const cfg = prepareFoldConfig(direction, targetPage, cornerV);
        const { ctx } = setupRetinaCanvas(canvas, cfg.totalW, cfg.totalH);

        let lastPt = {
          x: direction === "next" ? cfg.totalW - 30 : 30,
          y: cornerV === "top" ? 28 : cfg.totalH - 28,
        };

        const onMove = (ev) => {
          const dx = ev.clientX - startClientX;
          const dy = ev.clientY - startClientY;
          if (!moved && Math.hypot(dx, dy) < 6) return;
          moved = true;
          coverFrame.classList.add("is-folding");
          canvas.classList.remove("hidden");

          const localX = ev.clientX - rect.left;
          const localY = ev.clientY - rect.top;
          lastPt = constrainFoldPoint(localX, localY, cfg.spineX, cfg.cy, cfg.pageW, cfg.totalH);

          // Live cover shift during drag
          const dragProg = Math.max(0, Math.min(1, Math.abs(cfg.ox - lastPt.x) / Math.max(1, cfg.totalW)));
          const curShift = cfg.startShiftPct + (cfg.endShiftPct - cfg.startShiftPct) * dragProg;
          coverFrame.style.transform = `translateX(${curShift}%)`;

          drawPaperFoldFrame(ctx, { ...cfg, px: lastPt.x, py: lastPt.y });
        };

        const onUp = (ev) => {
          window.removeEventListener("pointermove", onMove);
          window.removeEventListener("pointerup", onUp);
          window.removeEventListener("pointercancel", onUp);
          try {
            if (ev.pointerId != null && zone.hasPointerCapture(ev.pointerId)) {
              zone.releasePointerCapture(ev.pointerId);
            }
          } catch {}

          if (!moved) {
            coverFrame.classList.remove("is-folding");
            canvas.classList.add("hidden");
            animateFlip(direction, targetPage, null, cornerV);
            return;
          }

          const dx = ev.clientX - startClientX;
          const threshold = cfg.pageW * 0.22;
          const shouldComplete = direction === "next" ? -dx > threshold : dx > threshold;

          if (shouldComplete) {
            animateFlip(direction, targetPage, lastPt, cornerV);
          } else {
            coverFrame.classList.remove("is-folding");
            canvas.classList.add("hidden");
            renderBookSpread();
          }
        };

        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
        window.addEventListener("pointercancel", onUp);
      });
    }

    attachDrag(rightZone, "next");
    attachDrag(leftZone, "prev");

    // Mobile Single-Page Mode: Full-Page Swipe & Left/Right Edge Tap
    const bookContainer = el("book-container");
    bookContainer.addEventListener("pointerdown", (e) => {
      if (!isSingleMode() || state.pinMode || state.zoom > 1 || state.isFlipping || !state.book) return;
      if (e.target.closest(".page-pin")) return;

      const total = state.book.page_count;
      const startX = e.clientX;
      const startY = e.clientY;
      const rect = bookContainer.getBoundingClientRect();
      const cornerV = (startY - rect.top) < rect.height * 0.35 ? "top" : "bottom";

      let direction = null;
      let cfg = null;
      let ctx = null;
      let lastPt = null;

      try {
        if (e.pointerId != null) bookContainer.setPointerCapture(e.pointerId);
      } catch {}

      preloadNearbyImages();

      const onMove = (ev) => {
        const dx = ev.clientX - startX;
        const dy = ev.clientY - startY;
        if (!direction) {
          if (Math.hypot(dx, dy) < 8) return;
          direction = dx < 0 ? "next" : "prev";
          if (direction === "next" && state.currentPage >= total) {
            direction = "blocked";
            return;
          }
          if (direction === "prev" && state.currentPage <= 1) {
            direction = "blocked";
            return;
          }
          const targetPage = direction === "next"
            ? Math.min(total, state.currentPage + 1)
            : Math.max(1, state.currentPage - 1);
          cfg = prepareFoldConfig(direction, targetPage, cornerV);
          ctx = setupRetinaCanvas(canvas, cfg.totalW, cfg.totalH).ctx;
          coverFrame.classList.add("is-folding");
          canvas.classList.remove("hidden");
        }
        if (direction === "blocked" || !cfg) return;

        // Map horizontal swipe distance across full page width
        const swipeSpan = Math.max(120, cfg.pageW);
        const prog = direction === "next"
          ? Math.max(0.04, Math.min(0.95, -dx / swipeSpan))
          : Math.max(0.04, Math.min(0.95, dx / swipeSpan));
        const synthX = direction === "next"
          ? cfg.totalW - prog * (cfg.totalW * 1.45)
          : prog * (cfg.totalW * 1.45);
        const localY = Math.max(12, Math.min(cfg.totalH - 12, ev.clientY - rect.top));
        lastPt = constrainFoldPoint(synthX, localY, cfg.spineX, cfg.cy, cfg.pageW, cfg.totalH);
        drawPaperFoldFrame(ctx, { ...cfg, px: lastPt.x, py: lastPt.y });
      };

      const onUp = (ev) => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);
        try {
          if (ev.pointerId != null && bookContainer.hasPointerCapture(ev.pointerId)) {
            bookContainer.releasePointerCapture(ev.pointerId);
          }
        } catch {}

        if (!direction) {
          // Simple tap on left 35% -> prev, right 65% -> next
          const tapRelX = (ev.clientX - rect.left) / Math.max(1, rect.width);
          if (tapRelX < 0.35) goPrev();
          else goNext();
          return;
        }

        if (direction === "blocked" || !cfg) {
          coverFrame.classList.remove("is-folding");
          canvas.classList.add("hidden");
          return;
        }

        const dx = ev.clientX - startX;
        const threshold = Math.min(55, cfg.pageW * 0.16);
        const shouldComplete = direction === "next" ? -dx > threshold : dx > threshold;

        if (shouldComplete) {
          animateFlip(direction, cfg.targetPage, lastPt, cornerV);
        } else {
          coverFrame.classList.remove("is-folding");
          canvas.classList.add("hidden");
          renderBookSpread();
        }
      };

      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
    });
  }

  function renderThumbnails() {
    const grid = el("thumbs-grid");
    grid.innerHTML = "";
    if (!state.book) return;

    state.book.pages.forEach((p) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "thumb-item";
      btn.dataset.page = String(p.page);
      btn.innerHTML = `
        <img src="${p.thumb_url}" alt="Page ${p.page}" loading="lazy" />
        <div class="thumb-label">Page ${p.page}</div>
      `;
      btn.addEventListener("click", () => jumpToPage(p.page));
      grid.appendChild(btn);
    });
  }

  function renderNotes() {
    const list = el("notes-list");
    const badge = el("notes-badge");
    const select = el("note-page-select");
    if (document.activeElement && list.contains(document.activeElement) && document.activeElement.tagName === "INPUT") {
      return;
    }
    list.innerHTML = "";

    if (!state.book) return;

    if (select.options.length !== state.book.page_count) {
      select.innerHTML = "";
      for (let i = 1; i <= state.book.page_count; i++) {
        const opt = document.createElement("option");
        opt.value = String(i);
        opt.textContent = `Page ${i}`;
        select.appendChild(opt);
      }
    }
    select.value = String(state.pendingPin?.page || state.currentPage);

    const notes = state.book.notes || [];
    if (notes.length > 0) {
      badge.textContent = String(notes.length);
      badge.classList.remove("hidden");
    } else {
      badge.classList.add("hidden");
    }

    renderPagePins(getSpreadForPage(state.currentPage, state.book.page_count));

    if (notes.length === 0) {
      list.innerHTML = '<div class="muted-note">No notes yet. Add one above or pin on a page!</div>';
      return;
    }

    notes.forEach((note, idx) => {
      const author = note.author || "Reader";
      const isHermes = author.toLowerCase().startsWith("hermes") || author.toLowerCase().includes("ai");
      const card = document.createElement("div");
      card.className = "note-card" + (isHermes ? " hermes" : "");
      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");
      card.setAttribute("aria-label", `Note ${idx + 1} by ${author} on page ${note.page}`);
      card.innerHTML = `
        <div class="note-card-head">
          <span><span class="note-author-tag"></span>#${idx + 1} • Page ${note.page}${note.x != null ? " (Pinned)" : ""}</span>
          <button type="button" class="note-delete" title="Delete note">&times;</button>
        </div>
        <div class="note-card-body"></div>
        <div class="note-replies"></div>
        <form class="note-reply-form">
          <input type="text" placeholder="Reply..." required />
          <button type="submit">Send</button>
        </form>
      `;
      card.querySelector(".note-author-tag").textContent = author;
      card.querySelector(".note-card-body").textContent = note.text;

      const repliesBox = card.querySelector(".note-replies");
      const replies = note.replies || [];
      if (replies.length === 0) {
        repliesBox.classList.add("hidden");
      } else {
        replies.forEach((r) => {
          const item = document.createElement("div");
          item.className = "note-reply-item";
          item.innerHTML = `<strong></strong>: <span></span>`;
          item.querySelector("strong").textContent = r.author || "Reader";
          item.querySelector("span").textContent = r.text;
          repliesBox.appendChild(item);
        });
      }

      card.addEventListener("click", (e) => {
        if (e.target.closest(".note-delete") || e.target.closest(".note-reply-form")) return;
        jumpToPage(note.page);
      });
      card.addEventListener("keydown", (e) => {
        if (e.target.tagName === "INPUT" || e.target.tagName === "BUTTON") return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          jumpToPage(note.page);
        }
      });

      card.querySelector(".note-delete").addEventListener("click", async () => {
        try {
          const res = await fetch(`/api/books/${state.book.id}/notes/${note.id}`, { method: "DELETE" });
          if (res.ok) {
            const data = await res.json();
            state.book.notes = data.notes;
            renderNotes();
          } else {
            const err = await res.json().catch(() => ({}));
            showToast(err.error || "Failed to delete note", true);
          }
        } catch {
          showToast("Network error deleting note", true);
        }
      });

      card.querySelector(".note-reply-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const input = e.target.querySelector("input");
        const replyText = input.value.trim();
        if (!replyText) return;
        try {
          const res = await fetch(`/api/books/${state.book.id}/notes/${note.id}/replies`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ author: state.readerName, text: replyText }),
          });
          if (res.ok) {
            const data = await res.json();
            state.book.notes = data.notes;
            renderNotes();
          } else {
            const err = await res.json().catch(() => ({}));
            showToast(err.error || "Failed to save reply", true);
          }
        } catch {
          showToast("Network error saving reply", true);
        }
      });

      list.appendChild(card);
    });
  }

  async function pushSessionHeartbeat() {
    if (!state.book) return;
    try {
      await fetch(`/api/books/${state.book.id}/session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reader: state.readerName, page: state.currentPage }),
      });
    } catch {
      // Ignore transient network errors
    }
  }

  async function pollSession() {
    if (!state.book || document.hidden) return;
    try {
      const res = await fetch(`/api/books/${state.book.id}/session`);
      if (!res.ok) return;
      const data = await res.json();
      state.readers = data.readers || {};

      const names = Object.keys(state.readers);
      el("collab-label").textContent = names.length > 1 ? `Co-Read (${names.length})` : "Co-Read";

      if (data.notes && JSON.stringify(data.notes) !== JSON.stringify(state.book.notes)) {
        state.book.notes = data.notes;
        renderNotes();
      }

      if (state.followSync) {
        const other = names.find((n) => n !== state.readerName);
        if (other && state.readers[other].page !== state.currentPage) {
          jumpToPage(state.readers[other].page);
        }
      }

      if (!el("modal-collab").classList.contains("hidden")) {
        renderActiveReaders();
      }
    } catch {
      // Ignore transient polling errors
    }
  }

  function renderActiveReaders() {
    const box = el("active-readers-list");
    box.innerHTML = "";
    const entries = Object.entries(state.readers);
    if (entries.length === 0) {
      box.innerHTML = '<div class="muted-note">Only you right now.</div>';
      return;
    }
    entries.forEach(([name, info]) => {
      const row = document.createElement("div");
      row.className = "library-item";
      row.innerHTML = `
        <div class="library-meta">
          <div class="library-title"></div>
          <div class="library-sub">Reading Page ${info.page}</div>
        </div>
        <button type="button" class="btn-ghost">Go to page</button>
      `;
      row.querySelector(".library-title").textContent = name === state.readerName ? `${name} (You)` : name;
      row.querySelector("button").addEventListener("click", () => {
        jumpToPage(info.page);
        el("modal-collab").classList.add("hidden");
      });
      box.appendChild(row);
    });
  }

  async function loadBook(bookId, initialPage = 1) {
    const res = await fetch(`/api/books/${encodeURIComponent(bookId)}`);
    if (!res.ok) return false;
    state.book = await res.json();
    state.currentPage = Math.max(1, Math.min(initialPage, state.book.page_count));
    resetZoom();

    el("book-title").textContent = state.book.title;
    el("book-title").title = state.book.title;
    document.title = `${state.book.title} — Virtual Book`;

    renderThumbnails();
    renderNotes();
    renderBookSpread();
    imgCache.clear();
    preloadNearbyImages();
    return true;
  }

  async function refreshBookList() {
    const res = await fetch("/api/books");
    if (!res.ok) return;
    const data = await res.json();
    state.books = data.books || [];
  }

  function openLeftPanel(panelName) {
    const sidebar = el("left-sidebar");
    const isSame = state.leftPanel === panelName && !sidebar.classList.contains("hidden");
    if (isSame) {
      sidebar.classList.add("hidden");
      state.leftPanel = null;
      el("btn-thumbs").classList.remove("active");
      el("btn-search").classList.remove("active");
      return;
    }

    state.leftPanel = panelName;
    sidebar.classList.remove("hidden");
    el("panel-thumbs").classList.toggle("hidden", panelName !== "thumbs");
    el("panel-search").classList.toggle("hidden", panelName !== "search");
    el("left-sidebar-title").textContent = panelName === "thumbs" ? "Thumbnails" : "Search Book";
    el("btn-thumbs").classList.toggle("active", panelName === "thumbs");
    el("btn-search").classList.toggle("active", panelName === "search");

    if (panelName === "search") {
      setTimeout(() => el("search-input").focus(), 50);
    }
  }

  function toggleNotesPanel(forceOpen) {
    const sidebar = el("right-sidebar");
    const shouldOpen = typeof forceOpen === "boolean" ? forceOpen : sidebar.classList.contains("hidden");
    sidebar.classList.toggle("hidden", !shouldOpen);
    el("btn-notes").classList.toggle("active", shouldOpen);
    state.rightPanelOpen = shouldOpen;
    if (shouldOpen) {
      el("note-page-select").value = String(state.pendingPin?.page || state.currentPage);
    }
  }

  function setPinMode(enabled) {
    state.pinMode = enabled;
    el("btn-pin-mode").classList.toggle("active", enabled);
    el("pin-mode-label").textContent = enabled ? "Click page to pin..." : "Pin on page";
    el("page-left-slot").classList.toggle("pin-placing", enabled);
    el("page-right-slot").classList.toggle("pin-placing", enabled);
  }

  function renderLibraryModal() {
    const list = el("library-list");
    list.innerHTML = "";
    state.books.forEach((b) => {
      const item = document.createElement("div");
      item.className = "library-item" + (state.book && state.book.id === b.id ? " active" : "");
      item.innerHTML = `
        <div class="library-meta">
          <div class="library-title"></div>
          <div class="library-sub">${b.page_count} pages • ${b.source_type.toUpperCase()}</div>
        </div>
        <div class="library-actions">
          <button type="button" class="btn-solid btn-open">Open</button>
          ${b.id !== "demo-wellness-guide" ? '<button type="button" class="btn-ghost btn-del">Delete</button>' : ""}
        </div>
      `;
      item.querySelector(".library-title").textContent = b.title;
      const openFn = async () => {
        await loadBook(b.id, 1);
        el("modal-library").classList.add("hidden");
      };
      item.querySelector(".library-meta").addEventListener("click", openFn);
      item.querySelector(".btn-open").addEventListener("click", openFn);

      const delBtn = item.querySelector(".btn-del");
      if (delBtn) {
        delBtn.addEventListener("click", async () => {
          if (!confirm(`Delete "${b.title}"?`)) return;
          const res = await fetch(`/api/books/${b.id}`, { method: "DELETE" });
          if (res.ok) {
            await refreshBookList();
            if (state.book && state.book.id === b.id && state.books.length > 0) {
              await loadBook(state.books[0].id, 1);
            }
            renderLibraryModal();
          }
        });
      }
      list.appendChild(item);
    });
  }

  function setUploadMode(mode) {
    state.uploadMode = mode;
    el("tab-pdf").classList.toggle("active", mode === "pdf");
    el("tab-images").classList.toggle("active", mode === "images");
    const input = el("upload-file-input");
    input.value = "";
    if (mode === "pdf") {
      input.accept = ".pdf";
      input.multiple = false;
      el("dropzone-label").innerHTML = "<strong>Click to choose a PDF</strong> or drag and drop here";
      el("dropzone-sub").textContent = "Pages are rendered at high DPI with full-text search";
    } else {
      input.accept = "image/*";
      input.multiple = true;
      el("dropzone-label").innerHTML = "<strong>Click to choose page images</strong> or drag and drop here";
      el("dropzone-sub").textContent = "Select multiple PNG, JPG, or WebP files (sorted by filename)";
    }
  }

  function bindEvents() {
    el("btn-first").addEventListener("click", () => jumpToPage(1));
    el("btn-prev").addEventListener("click", goPrev);
    el("btn-next").addEventListener("click", goNext);
    el("btn-last").addEventListener("click", () => state.book && jumpToPage(state.book.page_count));
    setupDragToFlip();

    // Page Pin Placement
    el("btn-pin-mode").addEventListener("click", () => setPinMode(!state.pinMode));
    [
      { slotId: "page-left-slot", side: "left" },
      { slotId: "page-right-slot", side: "right" },
    ].forEach(({ slotId, side }) => {
      el(slotId).addEventListener("click", (e) => {
        if (!state.pinMode || !state.book) return;
        const spread = getSpreadForPage(state.currentPage, state.book.page_count);
        const pageNum = side === "left" ? spread.left : spread.right;
        if (!pageNum) return;

        const rect = el(slotId).getBoundingClientRect();
        const x = Math.round(((e.clientX - rect.left) / rect.width) * 1000) / 10;
        const y = Math.round(((e.clientY - rect.top) / rect.height) * 1000) / 10;

        state.pendingPin = { page: pageNum, x, y };
        setPinMode(false);
        el("pin-coords-hint").classList.remove("hidden");
        el("pin-coords-hint").textContent = `Pinning on Page ${pageNum} (${x}%, ${y}%)`;
        toggleNotesPanel(true);
        setTimeout(() => el("note-text").focus(), 50);
      });
    });

    el("page-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const val = parseInt(e.target.value, 10);
        if (!Number.isNaN(val)) jumpToPage(val);
        e.target.blur();
      }
    });

    document.addEventListener("keydown", (e) => {
      if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
      if (e.key === "ArrowRight") goNext();
      else if (e.key === "ArrowLeft") goPrev();
      else if (e.key === "Home") jumpToPage(1);
      else if (e.key === "End" && state.book) jumpToPage(state.book.page_count);
      else if (e.key === "Escape") {
        setPinMode(false);
        document.querySelectorAll(".modal-backdrop").forEach((m) => m.classList.add("hidden"));
        if (state.zoom > 1) resetZoom();
      }
    });

    el("btn-thumbs").addEventListener("click", () => openLeftPanel("thumbs"));
    el("btn-search").addEventListener("click", () => openLeftPanel("search"));
    el("close-left-sidebar").addEventListener("click", () => {
      el("left-sidebar").classList.add("hidden");
      state.leftPanel = null;
      el("btn-thumbs").classList.remove("active");
      el("btn-search").classList.remove("active");
    });

    el("btn-notes").addEventListener("click", () => toggleNotesPanel());
    el("btn-add-note-pill").addEventListener("click", () => {
      state.pendingPin = null;
      el("pin-coords-hint").classList.add("hidden");
      toggleNotesPanel(true);
      setTimeout(() => el("note-text").focus(), 50);
    });
    el("close-right-sidebar").addEventListener("click", () => toggleNotesPanel(false));
    el("btn-export-annotated").addEventListener("click", () => {
      if (state.book) {
        window.location.href = `/api/books/${state.book.id}/export-annotated-pdf`;
      }
    });
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) pollSession();
    });

    window.__runAiPrompt = runAiCoReader;
    async function runAiCoReader(promptText) {
      if (!state.book) return;
      toggleNotesPanel(true);
      const chips = document.querySelectorAll(".btn-ai-chip");
      chips.forEach((c) => (c.disabled = true));
      try {
        const res = await fetch(`/api/books/${state.book.id}/ask-ai`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ page: state.currentPage, prompt: promptText }),
        });
        if (res.ok) {
          const data = await res.json();
          state.book.notes = data.notes;
          renderNotes();
        } else {
          const err = await res.json().catch(() => ({}));
          showToast(err.error || "AI summary could not be generated", true);
        }
      } catch {
        showToast("Network error contacting AI Co-Reader", true);
      } finally {
        chips.forEach((c) => (c.disabled = false));
      }
    }

    el("btn-ask-ai-pill").addEventListener("click", () => runAiCoReader("Key Clinical Takeaways"));
    document.querySelectorAll(".btn-ai-chip").forEach((chip) => {
      chip.addEventListener("click", () => runAiCoReader(chip.dataset.aiPrompt));
    });

    // Co-reading modal
    el("reader-name-input").value = state.readerName;
    el("btn-collab").addEventListener("click", () => {
      renderActiveReaders();
      el("modal-collab").classList.remove("hidden");
    });
    el("reader-name-input").addEventListener("change", (e) => {
      state.readerName = e.target.value.trim() || "Dan";
      localStorage.setItem("vb_reader_name", state.readerName);
      pushSessionHeartbeat();
    });
    el("follow-sync-checkbox").addEventListener("change", (e) => {
      state.followSync = e.target.checked;
    });

    el("search-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!state.book) return;
      const q = el("search-input").value.trim();
      const status = el("search-status");
      const resultsBox = el("search-results");
      resultsBox.innerHTML = "";
      if (!q) {
        status.textContent = "Type a keyword to search pages.";
        return;
      }
      status.textContent = "Searching...";
      const res = await fetch(`/api/books/${state.book.id}/search?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      const hits = data.results || [];
      status.textContent = hits.length ? `${hits.length} page(s) matched` : "No matches found.";
      hits.forEach((hit) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "search-hit";
        btn.innerHTML = `
          <div class="search-hit-page">Page ${hit.page}</div>
          <div class="search-hit-snippet"></div>
        `;
        btn.querySelector(".search-hit-snippet").textContent = hit.snippet;
        btn.addEventListener("click", () => jumpToPage(hit.page));
        resultsBox.appendChild(btn);
      });
    });

    el("note-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!state.book) return;
      const text = el("note-text").value.trim();
      const page = parseInt(el("note-page-select").value, 10) || state.currentPage;
      const author = el("note-author-select").value || state.readerName;
      if (!text) return;

      const payload = {
        page,
        author,
        text,
        x: state.pendingPin && state.pendingPin.page === page ? state.pendingPin.x : null,
        y: state.pendingPin && state.pendingPin.page === page ? state.pendingPin.y : null,
      };
      try {
        const res = await fetch(`/api/books/${state.book.id}/notes`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (res.ok) {
          const data = await res.json();
          state.book.notes = data.notes;
          state.pendingPin = null;
          el("pin-coords-hint").classList.add("hidden");
          el("note-text").value = "";
          renderNotes();
        } else {
          const err = await res.json().catch(() => ({}));
          showToast(err.error || "Failed to save note", true);
        }
      } catch {
        showToast("Network error saving note", true);
      }
    });

    el("btn-sound").addEventListener("click", () => {
      state.soundEnabled = !state.soundEnabled;
      el("icon-sound-on").classList.toggle("hidden", !state.soundEnabled);
      el("icon-sound-off").classList.toggle("hidden", state.soundEnabled);
      el("btn-sound").title = state.soundEnabled ? "Mute flip sound" : "Unmute flip sound";
    });

    el("btn-zoom").addEventListener("click", cycleZoom);
    el("btn-zoom-reset").addEventListener("click", resetZoom);
    el("book-container").addEventListener("dblclick", (e) => {
      if (e.target.closest(".click-zone") || state.pinMode) return;
      cycleZoom();
    });

    const panLayer = el("book-pan-layer");
    panLayer.addEventListener("mousedown", (e) => {
      if (state.zoom <= 1) return;
      state.isDragging = true;
      state.dragStartX = e.clientX - state.panX;
      state.dragStartY = e.clientY - state.panY;
      panLayer.classList.add("is-dragging");
    });
    window.addEventListener("mousemove", (e) => {
      if (!state.isDragging) return;
      state.panX = e.clientX - state.dragStartX;
      state.panY = e.clientY - state.dragStartY;
      panLayer.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`;
    });
    window.addEventListener("mouseup", () => {
      if (!state.isDragging) return;
      state.isDragging = false;
      panLayer.classList.remove("is-dragging");
    });

    // Touch pan when zoomed + 2-finger pinch-to-zoom for mobile/tablets
    let pinchStartDist = 0;
    let pinchStartZoom = 1;
    panLayer.addEventListener("touchstart", (e) => {
      if (e.touches.length === 2) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        pinchStartDist = Math.hypot(dx, dy);
        pinchStartZoom = state.zoom;
      } else if (e.touches.length === 1 && state.zoom > 1) {
        state.isDragging = true;
        state.dragStartX = e.touches[0].clientX - state.panX;
        state.dragStartY = e.touches[0].clientY - state.panY;
      }
    }, { passive: true });
    panLayer.addEventListener("touchmove", (e) => {
      if (e.touches.length === 2 && pinchStartDist > 0) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const scale = Math.hypot(dx, dy) / pinchStartDist;
        state.zoom = Math.max(1, Math.min(2.6, Number((pinchStartZoom * scale).toFixed(2))));
        panLayer.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`;
      } else if (e.touches.length === 1 && state.isDragging && state.zoom > 1) {
        state.panX = e.touches[0].clientX - state.dragStartX;
        state.panY = e.touches[0].clientY - state.dragStartY;
        panLayer.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`;
      }
    }, { passive: true });
    panLayer.addEventListener("touchend", () => {
      state.isDragging = false;
      pinchStartDist = 0;
    }, { passive: true });

    el("btn-fullscreen").addEventListener("click", () => {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
      } else {
        document.exitFullscreen().catch(() => {});
      }
    });
    el("btn-print").addEventListener("click", () => window.print());
    el("btn-download").addEventListener("click", () => {
      if (state.book) window.location.href = state.book.download_url;
    });
    el("btn-share").addEventListener("click", () => {
      updateHash();
      el("share-url-input").value = window.location.href;
      el("share-copied-msg").classList.add("hidden");
      el("modal-share").classList.remove("hidden");
    });
    el("btn-copy-share").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(el("share-url-input").value);
        el("share-copied-msg").classList.remove("hidden");
      } catch {
        el("share-url-input").select();
      }
    });

    el("btn-library").addEventListener("click", async () => {
      await refreshBookList();
      renderLibraryModal();
      el("modal-library").classList.remove("hidden");
    });

    el("btn-upload").addEventListener("click", () => {
      el("upload-status").classList.add("hidden");
      el("upload-title").value = "";
      setUploadMode("pdf");
      el("modal-upload").classList.remove("hidden");
    });
    el("tab-pdf").addEventListener("click", () => setUploadMode("pdf"));
    el("tab-images").addEventListener("click", () => setUploadMode("images"));

    const dropzone = el("dropzone");
    const fileInput = el("upload-file-input");
    fileInput.addEventListener("change", () => {
      const lbl = el("dropzone-label");
      if (fileInput.files.length === 1) {
        lbl.textContent = `Selected: ${fileInput.files[0].name}`;
      } else if (fileInput.files.length > 1) {
        lbl.textContent = `Selected: ${fileInput.files.length} image files`;
      }
    });
    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      if (e.dataTransfer.files.length > 0) {
        fileInput.files = e.dataTransfer.files;
        fileInput.dispatchEvent(new Event("change"));
      }
    });

    el("upload-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const files = fileInput.files;
      const status = el("upload-status");
      const btn = el("btn-submit-upload");

      if (!files || files.length === 0) {
        status.textContent = "Please choose file(s) first.";
        status.className = "upload-status error";
        return;
      }

      const formData = new FormData();
      formData.append("title", el("upload-title").value.trim());

      let endpoint = "/api/books/upload-pdf";
      if (state.uploadMode === "pdf") {
        formData.append("file", files[0]);
      } else {
        endpoint = "/api/books/upload-images";
        Array.from(files).forEach((f) => formData.append("files", f));
      }

      btn.disabled = true;
      status.textContent = "Converting pages... this may take a few seconds.";
      status.className = "upload-status";

      try {
        const res = await fetch(endpoint, { method: "POST", body: formData });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Upload failed");

        await refreshBookList();
        await loadBook(data.id, 1);
        el("modal-upload").classList.add("hidden");
      } catch (err) {
        status.textContent = err.message;
        status.className = "upload-status error";
      } finally {
        btn.disabled = false;
      }
    });

    document.querySelectorAll("[data-close-modal]").forEach((btn) => {
      btn.addEventListener("click", () => {
        el(btn.dataset.closeModal).classList.add("hidden");
      });
    });

    window.addEventListener("resize", renderBookSpread);
  }

  let zoomHudTimer = null;
  function showZoomHud(scale) {
    const hud = el("zoom-hud");
    const val = el("zoom-hud-val");
    if (!hud || !val) return;
    val.textContent = `${Math.round(scale * 100)}%`;
    hud.classList.add("is-on");
    clearTimeout(zoomHudTimer);
    zoomHudTimer = setTimeout(() => hud.classList.remove("is-on"), 1400);
  }

  function syncEditorialDock(page, total) {
    const range = el("page-range");
    const cur = el("dock-pg-cur");
    const tot = el("dock-pg-tot");
    const dPrev = el("dock-prev");
    const dNext = el("dock-next");
    if (!range) return;
    range.max = String(Math.max(1, total));
    range.value = String(page);
    const pct = total > 1 ? ((page - 1) / (total - 1)) * 100 : 100;
    range.style.setProperty("--p", `${pct}%`);
    if (cur) cur.textContent = String(page);
    if (tot) tot.textContent = String(total);
    if (dPrev) dPrev.disabled = page <= 1;
    if (dNext) dNext.disabled = page >= total;
  }

  const PAGE_AI_CHIPS = {
    1: [
      { label: "เจ็บไหม?", prompt: "เจาะชิ้นเนื้อเต้านมเจ็บไหม และฉีดยาชาช่วยอย่างไร" },
      { label: "ใช้เวลานานเท่าไร?", prompt: "ขั้นตอนทั้งหมดใช้เวลากี่นาที และกลับบ้านได้เลยไหม" },
      { label: "ส่วนใหญ่เป็นเนื้อร้ายไหม?", prompt: "โอกาสที่ก้อนจะไม่ใช่เนื้อร้ายมีมากน้อยแค่ไหน" },
    ],
    2: [
      { label: "ต้องงดน้ำ-อาหารไหม?", prompt: "ก่อนมาตรวจต้องงดน้ำและอาหารหรือไม่" },
      { label: "ยาละลายลิ่มเลือด", prompt: "ถ้าทานยาละลายลิ่มเลือดหรือวิตามินต้องทำอย่างไร" },
      { label: "วันตรวจแต่งตัวอย่างไร?", prompt: "วันมาตรวจควรเตรียมเสื้อผ้าหรือ Sports Bra อย่างไร" },
    ],
    3: [
      { label: "เสียงคลิกคืออะไร?", prompt: "เสียงคลิกเบาๆ ระหว่างเก็บชิ้นเนื้อคืออะไร น่ากลัวไหม" },
      { label: "วางคลิปไทเทเนียม?", prompt: "คลิปไทเทเนียมจิ๋ว 2 มม. ปลอดภัยไหม และใช้ทำอะไร" },
      { label: "ต้องเย็บแผลไหม?", prompt: "แผลขนาด 2-3 มม. ต้องเย็บแผลหรือไม่" },
    ],
    4: [
      { label: "อาบน้ำได้เมื่อไร?", prompt: "หลังเจาะชิ้นเนื้อกี่ชั่วโมงจึงจะอาบน้ำได้" },
      { label: "ปวดกินยาอะไรได้บ้าง?", prompt: "หลังตรวจทานยาแก้ปวดตัวไหนได้ และห้ามทานยาอะไร" },
      { label: "อาการที่ต้องรีบพบแพทย์", prompt: "อาการผิดปกติแบบไหนที่ต้องติดต่อโรงพยาบาลทันที" },
    ],
  };

  function renderAiContextChips(page) {
    const box = el("ai-context-chips");
    if (!box) return;
    box.innerHTML = "";
    const chips = PAGE_AI_CHIPS[page] || PAGE_AI_CHIPS[1];
    chips.forEach((c) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ai-context-chip";
      btn.textContent = c.label;
      btn.addEventListener("click", () => {
        const presetBtn = document.querySelector(`[data-ai-prompt]`);
        if (typeof window.__runAiPrompt === "function") {
          window.__runAiPrompt(c.prompt);
        } else if (presetBtn) {
          el("note-text").value = c.prompt;
        }
      });
      box.appendChild(btn);
    });
  }

  function initEditorialUX() {
    // 1. Reading-Lamp Mode
    const lampBtn = el("btn-lamp");
    const applyTheme = (theme) => {
      if (theme === "lamp") {
        document.documentElement.dataset.theme = "lamp";
        if (lampBtn) lampBtn.setAttribute("aria-pressed", "true");
      } else {
        delete document.documentElement.dataset.theme;
        if (lampBtn) lampBtn.setAttribute("aria-pressed", "false");
      }
    };
    try {
      applyTheme(localStorage.getItem("vb_theme") || "");
    } catch (_) {}
    if (lampBtn) {
      lampBtn.addEventListener("click", () => {
        const next = document.documentElement.dataset.theme === "lamp" ? "" : "lamp";
        applyTheme(next);
        try { localStorage.setItem("vb_theme", next); } catch (_) {}
      });
    }

    // 2. Floating Dock Scrubber
    const range = el("page-range");
    const peek = el("scrubber-peek");
    const dPrev = el("dock-prev");
    const dNext = el("dock-next");
    if (dPrev) dPrev.addEventListener("click", () => el("btn-prev").click());
    if (dNext) dNext.addEventListener("click", () => el("btn-next").click());
    if (range) {
      range.addEventListener("input", (e) => {
        const p = Number(e.target.value);
        const total = state.book ? state.book.page_count : 1;
        const pct = total > 1 ? ((p - 1) / (total - 1)) * 100 : 100;
        range.style.setProperty("--p", `${pct}%`);
        if (peek && state.book && state.book.pages[p - 1]) {
          peek.querySelector("img").src = state.book.pages[p - 1].thumb_url || state.book.pages[p - 1].image_url;
          peek.querySelector("span").textContent = `Page ${p}`;
          peek.classList.remove("hidden");
        }
      });
      range.addEventListener("change", (e) => {
        if (peek) peek.classList.add("hidden");
        goToPage(Number(e.target.value));
      });
    }

    // 3. Zoom HUD controls
    const zOut = el("zoom-hud-out");
    const zIn = el("zoom-hud-in");
    const zFit = el("zoom-hud-fit");
    if (zOut) zOut.addEventListener("click", () => {
      state.zoom = Math.max(1, Number((state.zoom - 0.25).toFixed(2)));
      if (state.zoom === 1) { state.panX = 0; state.panY = 0; }
      applyZoomTransform();
    });
    if (zIn) zIn.addEventListener("click", () => {
      state.zoom = Math.min(2.6, Number((state.zoom + 0.25).toFixed(2)));
      applyZoomTransform();
    });
    if (zFit) zFit.addEventListener("click", () => resetZoom());

    // 4. Auto-hide chrome after 3.5s idle reading
    let idleTimer = null;
    const topbar = el("top");
    const dock = el("reader-dock");
    const wakeChrome = () => {
      if (topbar) topbar.classList.remove("is-idle");
      if (dock) dock.classList.remove("is-idle");
      clearTimeout(idleTimer);
      idleTimer = setTimeout(() => {
        const anyOpen = document.querySelector(".sidebar:not(.hidden), .modal-backdrop:not(.hidden)");
        if (!anyOpen && state.zoom <= 1) {
          if (topbar) topbar.classList.add("is-idle");
          if (dock) dock.classList.add("is-idle");
        }
      }, 3500);
    };
    ["pointermove", "pointerdown", "keydown"].forEach((evt) => {
      window.addEventListener(evt, wakeChrome, { passive: true });
    });
    wakeChrome();
  }

  async function init() {
    initEditorialUX();
    bindEvents();
    await refreshBookList();
    const { bookId, page } = parseHash();
    const targetId =
      bookId && state.books.some((b) => b.id === bookId)
        ? bookId
        : state.books[0]?.id;
    if (targetId) {
      await loadBook(targetId, page);
    }
    state.syncTimer = setInterval(pollSession, 3000);
  }

  init();
})();
