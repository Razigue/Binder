// Binder phone scanner. The page only films and frames: Binder, on the computer, detects the
// outline, straightens and cleans up the pages, then builds the PDF.
"use strict"
;(() => {
  // --- Texts ------------------------------------------------------------------------------
  const TEXTS = {
    fr: {
      document: "Document {n}",
      pages_one: "{n} page",
      pages_other: "{n} pages",
      docs_one: "{n} document",
      docs_other: "{n} documents",
      auto: "Auto",
      next: "Nouveau doc",
      finish: "Envoyer",
      shutter: "Prendre la page",
      torch: "Lampe",
      hintFrame: "Cadrez la page en entier",
      hintContrast: "Posez la page sur un fond plus sombre, bien éclairé",
      hintHold: "Ne bougez plus…",
      hintTap: "Appuyez sur le bouton pour prendre la page",
      hintTurn: "Page {n} prise · passez à la suivante",
      hintNewDoc: "Document {n} : commencez par sa première page",
      connecting: "Connexion à Binder…",
      expiredTitle: "Session terminée",
      expiredText: "Dans Binder, rouvrez « Scanner avec mon téléphone » puis scannez le nouveau QR code.",
      doneTitle: "C'est envoyé",
      doneText: "{docs} transmis à Binder, qui les analyse. Vous pouvez fermer cette page.",
      offlineTitle: "Binder est injoignable",
      offlineText: "Vérifiez que le téléphone et l'ordinateur sont sur le même Wi-Fi et que Binder est ouvert.",
      retry: "Réessayer",
      fallbackTitle: "Prenez vos pages en photo",
      fallbackInsecure: "Ce navigateur ne permet pas le viseur en direct. Prenez chaque page en photo : Binder la recadre et la redresse.",
      fallbackDenied: "L'accès à la caméra a été refusé. Autorisez-le dans les réglages du navigateur et rechargez la page, ou prenez chaque page en photo :",
      fallbackBtn: "Photographier une page",
      confirmTitle: "Envoyer à Binder ?",
      confirmText: "{docs}, {pages} au total. Binder les classe et en extrait les informations.",
      send: "Envoyer",
      keepScanning: "Continuer",
      pageTitle: "Page {n}",
      pageNoOutline: "Bords non détectés : la photo est gardée entière.",
      pageFailed: "Cette page n'a pas pu être envoyée.",
      delete: "Supprimer",
      keep: "Garder",
      sending: "Envoi…",
      uploadError: "Envoi impossible. Vérifiez le Wi-Fi.",
      tooMany: "Nombre maximal de pages atteint.",
    },
    en: {
      document: "Document {n}",
      pages_one: "{n} page",
      pages_other: "{n} pages",
      docs_one: "{n} document",
      docs_other: "{n} documents",
      auto: "Auto",
      next: "New doc",
      finish: "Send",
      shutter: "Take the page",
      torch: "Torch",
      hintFrame: "Fit the whole page in the frame",
      hintContrast: "Place the page on a darker, well-lit surface",
      hintHold: "Hold still…",
      hintTap: "Press the button to take the page",
      hintTurn: "Page {n} taken · move on to the next one",
      hintNewDoc: "Document {n}: start with its first page",
      connecting: "Connecting to Binder…",
      expiredTitle: "Session ended",
      expiredText: "In Binder, open “Scan with my phone” again and scan the new QR code.",
      doneTitle: "Sent",
      doneText: "{docs} sent to Binder, which is analysing them. You can close this page.",
      offlineTitle: "Binder cannot be reached",
      offlineText: "Check that the phone and the computer are on the same Wi-Fi and that Binder is open.",
      retry: "Try again",
      fallbackTitle: "Take photos of your pages",
      fallbackInsecure: "This browser does not allow a live viewfinder. Take a photo of each page: Binder crops and straightens it.",
      fallbackDenied: "Camera access was denied. Allow it in the browser settings and reload the page, or take a photo of each page:",
      fallbackBtn: "Photograph a page",
      confirmTitle: "Send to Binder?",
      confirmText: "{docs}, {pages} in total. Binder files them and extracts their details.",
      send: "Send",
      keepScanning: "Keep scanning",
      pageTitle: "Page {n}",
      pageNoOutline: "No outline found: the whole photo is kept.",
      pageFailed: "This page could not be sent.",
      delete: "Delete",
      keep: "Keep",
      sending: "Sending…",
      uploadError: "Could not send. Check the Wi-Fi.",
      tooMany: "Maximum number of pages reached.",
    },
  }
  const LANG = (navigator.language || "en").toLowerCase().startsWith("fr") ? "fr" : "en"
  document.documentElement.lang = LANG

  function t(key, params = {}) {
    let text = TEXTS[LANG][key] ?? key
    for (const [k, v] of Object.entries(params)) text = text.replaceAll(`{${k}}`, String(v))
    return text
  }
  function plural(key, n) {
    const one = LANG === "fr" ? n <= 1 : n === 1
    return t(`${key}_${one ? "one" : "other"}`, { n })
  }

  // --- Tuning ------------------------------------------------------------------------------
  const FRAME_SIZE = 400 // long side of the frames sent for live detection
  const HOLD_MS = 1000 // how long the outline must stay still before an automatic capture
  const STILL = 0.025 // corner movement tolerated while holding still (share of the frame)
  const LOST_MS = 500 // outline missing for this long: hidden, and auto capture re-armed
  const CONTRAST_HINT_MS = 3000
  const CHANGED = 0.06 // share of the sheet that changed: "another page is in front of the camera"
  const RING = 226.2 // circumference of the progress ring

  // --- Elements and state ------------------------------------------------------------------
  const $ = (id) => document.getElementById(id)
  const video = $("video")
  const quadEl = $("quad")
  const token = new URLSearchParams(location.search).get("t") || ""

  const state = {
    pages: [], // { key, doc, id, thumb, status: "busy" | "ok" | "failed", detected, blob, quad }
    doc: 1,
    auto: true,
    track: null,
    running: false,
    target: null, // last outline from Binder
    shown: null, // outline drawn (eased towards target)
    seenAt: 0,
    searchingSince: performance.now(),
    anchor: null,
    stillSince: 0,
    armed: true,
    capturing: false,
    signature: null,
    capturedSignature: null,
    lastCount: 0,
    finished: false,
    wakeLock: null,
  }
  let queue = Promise.resolve()

  // --- Server ------------------------------------------------------------------------------
  class Expired extends Error {}

  async function api(path, options = {}) {
    let response
    try {
      response = await fetch(path, {
        ...options,
        headers: { "X-Scan-Token": token, ...(options.headers || {}) },
        cache: "no-store",
      })
    } catch {
      throw new Error("network")
    }
    if (response.status === 403) throw new Expired()
    if (!response.ok) throw new Error(response.status === 409 ? "full" : `http ${response.status}`)
    return response.status === 204 ? null : response.json()
  }

  function onError(error) {
    if (error instanceof Expired) return showExpired()
    toast(error.message === "full" ? t("tooMany") : t("uploadError"))
  }

  // --- Screens -----------------------------------------------------------------------------
  const ICONS = {
    wait: '<svg viewBox="0 0 24 24"><path d="M12 6v6l4 2"/><circle cx="12" cy="12" r="9"/></svg>',
    ok: '<svg viewBox="0 0 24 24"><path d="m5 12 5 5 9-10"/></svg>',
    bad: '<svg viewBox="0 0 24 24"><path d="M12 8v5M12 16.5v.01"/><circle cx="12" cy="12" r="9"/></svg>',
    wifi: '<svg viewBox="0 0 24 24"><path d="M2 8.5a15 15 0 0 1 20 0M5 12a10 10 0 0 1 14 0M8.5 15.5a5 5 0 0 1 7 0M12 19h.01"/></svg>',
  }

  function showOnly(id) {
    for (const screen of ["camera", "fallback", "message"]) $(screen).hidden = screen !== id
  }

  function showMessage(icon, title, text, button) {
    stopCamera()
    showOnly("message")
    const badge = $("messageIcon")
    badge.className = `badge ${icon === "ok" ? "ok" : icon === "bad" ? "bad" : ""}`
    badge.innerHTML = ICONS[icon]
    $("messageTitle").textContent = title
    $("messageText").textContent = text
    const btn = $("messageBtn")
    btn.hidden = !button
    if (button) {
      btn.textContent = button.label
      btn.onclick = button.action
    }
  }

  function showExpired() {
    state.finished = true
    showMessage("bad", t("expiredTitle"), t("expiredText"))
  }

  function showDone(count) {
    state.finished = true
    showMessage("ok", t("doneTitle"), t("doneText", { docs: plural("docs", count) }))
  }

  let toastTimer = 0
  function toast(text) {
    const el = $("toast")
    el.textContent = text
    el.hidden = false
    clearTimeout(toastTimer)
    toastTimer = setTimeout(() => (el.hidden = true), 3500)
  }

  function sheet({ title, text, image, confirm, cancel, onConfirm }) {
    $("sheetTitle").textContent = title
    $("sheetText").textContent = text || ""
    $("sheetText").hidden = !text
    const img = $("sheetImage")
    img.hidden = !image
    if (image) img.src = image
    $("sheetConfirm").textContent = confirm
    $("sheetCancel").textContent = cancel
    $("sheet").hidden = false
    const close = () => ($("sheet").hidden = true)
    $("sheetCancel").onclick = close
    $("sheet").onclick = (e) => e.target === $("sheet") && close()
    $("sheetConfirm").onclick = () => {
      close()
      onConfirm()
    }
  }

  // --- Pages -------------------------------------------------------------------------------
  const docPages = (doc) => state.pages.filter((p) => p.doc === doc)
  const documents = () => [...new Set(state.pages.map((p) => p.doc))]

  function render() {
    const current = docPages(state.doc)
    const docLabel = `${t("document", { n: state.doc })} · ${plural("pages", current.length)}`
    $("docLabel").textContent = docLabel
    const total = state.pages.length
    const docs = documents().length
    $("finishLabel").textContent = docs > 1 ? `${t("finish")} (${docs})` : t("finish")
    $("finishBtn").disabled = total === 0
    $("fallbackFinish").disabled = total === 0
    $("fallbackFinish").textContent = $("finishLabel").textContent
    $("nextBtn").disabled = current.length === 0
    $("fallbackNext").disabled = current.length === 0
    for (const tray of [$("tray"), $("fallbackTray")]) {
      tray.replaceChildren(...current.map((page, i) => thumb(page, i + 1)))
      if (current.length > state.lastCount) tray.scrollLeft = tray.scrollWidth
    }
    state.lastCount = current.length
  }

  function thumb(page, n) {
    const el = document.createElement("button")
    el.type = "button"
    el.className = `thumb${page.status === "busy" ? " busy" : ""}${page.status === "failed" ? " failed" : ""}${
      page.status === "ok" && !page.detected ? " warn" : ""
    }`
    el.setAttribute("aria-label", t("pageTitle", { n }))
    const img = document.createElement("img")
    img.src = page.thumb
    img.alt = ""
    const num = document.createElement("span")
    num.className = "num"
    num.textContent = String(n)
    el.append(img, num)
    el.onclick = () => openPage(page, n)
    return el
  }

  function openPage(page, n) {
    if (page.status === "busy") return
    const failed = page.status === "failed"
    sheet({
      title: t("pageTitle", { n }),
      text: failed ? t("pageFailed") : page.detected ? "" : t("pageNoOutline"),
      image: page.thumb,
      confirm: failed ? t("retry") : t("delete"),
      cancel: failed ? t("delete") : t("keep"),
      onConfirm: () => (failed ? retry(page) : removePage(page)),
    })
    if (failed) {
      $("sheetCancel").onclick = () => {
        $("sheet").hidden = true
        removePage(page)
      }
    }
  }

  async function removePage(page) {
    state.pages = state.pages.filter((p) => p !== page)
    render()
    if (page.id) await api(`/api/pages/${page.id}`, { method: "DELETE" }).catch(onError)
  }

  function retry(page) {
    page.status = "busy"
    render()
    enqueue(page)
  }

  function enqueue(page) {
    queue = queue.then(() => upload(page))
  }

  async function upload(page) {
    const quad = page.quad ? `&quad=${page.quad.flat().map((v) => v.toFixed(4)).join(",")}` : ""
    try {
      const result = await api(`/api/pages?document=${page.doc}${quad}`, {
        method: "POST",
        headers: { "Content-Type": "image/jpeg" },
        body: page.blob,
      })
      page.id = result.id
      page.detected = result.detected
      page.status = "ok"
      page.blob = null
      // The cleaned-up page as Binder will keep it.
      page.thumb = `/api/pages/${result.id}/thumb?t=${encodeURIComponent(token)}`
    } catch (error) {
      page.status = "failed"
      onError(error)
    }
    if (state.pages.includes(page)) render()
  }

  function addPage(blob, preview, quad) {
    const page = {
      key: crypto.randomUUID ? crypto.randomUUID() : String(Math.random()),
      doc: state.doc,
      id: null,
      thumb: preview,
      status: "busy",
      detected: true,
      blob,
      quad,
    }
    state.pages.push(page)
    render()
    enqueue(page)
  }

  function nextDocument() {
    if (!docPages(state.doc).length) return
    state.doc = Math.max(state.doc, ...documents()) + 1
    // The page still under the camera belongs to the previous document: wait for the next one.
    render()
    setHint(t("hintNewDoc", { n: state.doc }), 2500)
  }

  function finish() {
    const pages = state.pages.length
    if (!pages) return
    sheet({
      title: t("confirmTitle"),
      text: t("confirmText", { docs: plural("docs", documents().length), pages: plural("pages", pages) }),
      confirm: t("send"),
      cancel: t("keepScanning"),
      onConfirm: async () => {
        showMessage("wait", t("sending"), "")
        await queue
        try {
          const result = await api("/api/finish", { method: "POST" })
          showDone(result.imported)
        } catch (error) {
          if (error instanceof Expired) return showExpired()
          showMessage("bad", t("offlineTitle"), t("offlineText"), {
            label: t("retry"),
            action: () => location.reload(),
          })
        }
      },
    })
  }

  // --- Images ------------------------------------------------------------------------------
  const toBlob = (canvas, quality) =>
    new Promise((resolve, reject) =>
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("encode"))), "image/jpeg", quality),
    )

  function draw(source, width, height, long) {
    const scale = Math.min(1, long / Math.max(width, height))
    const canvas = document.createElement("canvas")
    canvas.width = Math.round(width * scale)
    canvas.height = Math.round(height * scale)
    canvas.getContext("2d").drawImage(source, 0, 0, canvas.width, canvas.height)
    return canvas
  }

  // Small grey picture of the sheet, to notice that another page has been put down.
  const SIG_W = 24
  const SIG_H = 32
  const sigCanvas = document.createElement("canvas")
  sigCanvas.width = SIG_W
  sigCanvas.height = SIG_H
  const sigContext = sigCanvas.getContext("2d", { willReadFrequently: true })
  function signature(source, quad) {
    const xs = quad.map((p) => p[0] * source.width)
    const ys = quad.map((p) => p[1] * source.height)
    const x = Math.max(0, Math.min(...xs))
    const y = Math.max(0, Math.min(...ys))
    const w = Math.min(source.width, Math.max(...xs)) - x
    const h = Math.min(source.height, Math.max(...ys)) - y
    if (w < 8 || h < 8) return null
    sigContext.drawImage(source, x, y, w, h, 0, 0, SIG_W, SIG_H)
    const data = sigContext.getImageData(0, 0, SIG_W, SIG_H).data
    const grey = new Uint8Array(SIG_W * SIG_H)
    for (let i = 0; i < grey.length; i++) grey[i] = (data[i * 4] + data[i * 4 + 1] + data[i * 4 + 2]) / 3
    return grey
  }
  /** Share of the cells whose brightness clearly changed. */
  function difference(a, b) {
    if (!a || !b) return 0
    let changed = 0
    for (let i = 0; i < a.length; i++) if (Math.abs(a[i] - b[i]) > 40) changed++
    return changed / a.length
  }

  // --- Camera ------------------------------------------------------------------------------
  async function startCamera() {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) return showFallback("insecure")
    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" }, width: { ideal: 3840 }, height: { ideal: 2160 } },
      })
    } catch (error) {
      return showFallback(error && error.name === "NotAllowedError" ? "denied" : "insecure")
    }
    video.srcObject = stream
    state.track = stream.getVideoTracks()[0]
    try {
      await video.play()
    } catch {
      // Autoplay of a muted inline video is allowed everywhere; nothing else to try.
    }
    const caps = state.track.getCapabilities ? state.track.getCapabilities() : {}
    if (caps.torch) $("torchBtn").hidden = false
    if (caps.focusMode && caps.focusMode.includes("continuous")) {
      state.track.applyConstraints({ advanced: [{ focusMode: "continuous" }] }).catch(() => {})
    }
    showOnly("camera")
    keepAwake()
    state.running = true
    state.searchingSince = performance.now()
    detectLoop()
    requestAnimationFrame(animate)
  }

  function stopCamera() {
    state.running = false
    if (state.track) state.track.stop()
    state.track = null
  }

  function showFallback(reason) {
    stopCamera()
    showOnly("fallback")
    $("fallbackTitle").textContent = t("fallbackTitle")
    $("fallbackText").textContent = t(reason === "denied" ? "fallbackDenied" : "fallbackInsecure")
    $("fallbackBtn").textContent = t("fallbackBtn")
    $("fallbackNext").textContent = t("next")
    render()
  }

  async function keepAwake() {
    try {
      if ("wakeLock" in navigator && !document.hidden) state.wakeLock = await navigator.wakeLock.request("screen")
    } catch {
      // Optional: the screen may simply dim.
    }
  }

  // --- Live detection ----------------------------------------------------------------------
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

  async function detectLoop() {
    while (state.running) {
      if (document.hidden || !video.videoWidth || state.capturing || state.finished) {
        await sleep(200)
        continue
      }
      const frame = draw(video, video.videoWidth, video.videoHeight, FRAME_SIZE)
      try {
        const blob = await toBlob(frame, 0.6)
        const result = await api("/api/detect", { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: blob })
        onOutline(result.quad, result.quad ? signature(frame, result.quad) : null)
      } catch (error) {
        if (error instanceof Expired) return showExpired()
        await sleep(1000)
      }
      await sleep(30)
    }
  }

  const maxShift = (a, b) => Math.max(...a.map((p, i) => Math.max(Math.abs(p[0] - b[i][0]), Math.abs(p[1] - b[i][1]))))

  function onOutline(quad, sig) {
    const now = performance.now()
    state.signature = sig
    if (quad) {
      state.target = quad
      state.seenAt = now
      if (!state.anchor || maxShift(quad, state.anchor) > STILL) {
        state.anchor = quad
        state.stillSince = now
      }
      // A different page in front of the camera: ready for another automatic capture.
      if (!state.armed && difference(sig, state.capturedSignature) > CHANGED) state.armed = true
    } else if (now - state.seenAt > LOST_MS) {
      if (state.target) state.searchingSince = now
      state.target = null
      state.anchor = null
      state.armed = true
    }
    update(now)
  }

  let hintUntil = 0
  function setHint(text, hold = 0) {
    $("hint").textContent = text
    hintUntil = hold ? performance.now() + hold : 0
  }

  function update(now) {
    const seen = !!state.target
    const held = seen ? Math.min(1, (now - state.stillSince) / HOLD_MS) : 0
    const counting = seen && state.auto && state.armed
    quadEl.classList.toggle("seen", seen)
    quadEl.classList.toggle("locked", counting && held >= 0.5)
    $("ring").style.strokeDashoffset = String(RING * (1 - (counting ? held : 0)))

    if (now >= hintUntil) {
      if (!seen) {
        setHint(now - state.searchingSince > CONTRAST_HINT_MS ? t("hintContrast") : t("hintFrame"))
      } else if (!state.armed) {
        setHint(t("hintTurn", { n: docPages(state.doc).length }))
      } else {
        setHint(state.auto ? t("hintHold") : t("hintTap"))
      }
    }
    if (counting && held >= 1) capture()
  }

  // Maps a corner of the frame to the screen, given that the video covers the screen.
  function toScreen([x, y]) {
    const vw = video.videoWidth
    const vh = video.videoHeight
    const w = video.clientWidth
    const h = video.clientHeight
    const scale = Math.max(w / vw, h / vh)
    return [x * vw * scale + (w - vw * scale) / 2, y * vh * scale + (h - vh * scale) / 2]
  }

  function animate() {
    if (!state.running) return
    const target = state.target
    if (target && video.videoWidth) {
      state.shown = state.shown
        ? state.shown.map((p, i) => [p[0] + (target[i][0] - p[0]) * 0.35, p[1] + (target[i][1] - p[1]) * 0.35])
        : target
      quadEl.setAttribute("points", state.shown.map((p) => toScreen(p).join(",")).join(" "))
    } else {
      state.shown = null
    }
    requestAnimationFrame(animate)
  }

  async function capture() {
    if (state.capturing || !video.videoWidth) return
    state.capturing = true
    const flash = $("flash")
    flash.classList.remove("go")
    void flash.offsetWidth
    flash.classList.add("go")
    $("shutter").classList.add("shot")
    if (navigator.vibrate) navigator.vibrate(25)
    try {
      const full = draw(video, video.videoWidth, video.videoHeight, 4096)
      const preview = draw(full, full.width, full.height, 160).toDataURL("image/jpeg", 0.7)
      const blob = await toBlob(full, 0.92)
      addPage(blob, preview, state.target)
      state.capturedSignature = state.signature
      state.armed = false
      state.stillSince = performance.now()
    } finally {
      state.capturing = false
      setTimeout(() => $("shutter").classList.remove("shot"), 150)
      update(performance.now())
    }
  }

  // --- Photos taken outside the page (no live camera) --------------------------------------
  async function addPhotos(files) {
    for (const file of files) {
      try {
        const bitmap = await createImageBitmap(file)
        const full = draw(bitmap, bitmap.width, bitmap.height, 4096)
        const preview = draw(full, full.width, full.height, 160).toDataURL("image/jpeg", 0.7)
        addPage(await toBlob(full, 0.92), preview, null)
      } catch {
        toast(t("uploadError"))
      }
    }
  }

  // --- Sync with Binder --------------------------------------------------------------------
  async function poll() {
    while (!state.finished) {
      await sleep(3000)
      if (document.hidden || state.finished) continue
      try {
        const remote = await api("/api/state")
        if (remote.imported !== null) return showDone(remote.imported)
        // Pages deleted from the computer disappear here too.
        const ids = new Set(remote.pages.map((p) => p.id))
        const before = state.pages.length
        state.pages = state.pages.filter((p) => p.status !== "ok" || ids.has(p.id))
        if (state.pages.length !== before) render()
      } catch (error) {
        if (error instanceof Expired) return showExpired()
      }
    }
  }

  async function boot() {
    if (!token) return showExpired()
    showMessage("wait", t("connecting"), "")
    let remote
    try {
      remote = await api("/api/state")
    } catch (error) {
      if (error instanceof Expired) return showExpired()
      return showMessage("wifi", t("offlineTitle"), t("offlineText"), {
        label: t("retry"),
        action: () => location.reload(),
      })
    }
    if (remote.imported !== null) return showDone(remote.imported)
    // Reloaded page: the pages already received are shown again.
    for (const p of remote.pages) {
      state.pages.push({
        key: p.id,
        doc: p.document,
        id: p.id,
        thumb: `/api/pages/${p.id}/thumb?t=${encodeURIComponent(token)}`,
        status: "ok",
        detected: p.detected,
        blob: null,
        quad: null,
      })
    }
    state.doc = Math.max(1, ...documents())
    poll()
    await startCamera()
    render()
  }

  // --- Wiring ------------------------------------------------------------------------------
  $("shutter").setAttribute("aria-label", t("shutter"))
  $("torchBtn").setAttribute("aria-label", t("torch"))
  $("autoBtn").textContent = t("auto")
  $("nextLabel").textContent = t("next")
  $("shutter").onclick = () => capture()
  $("nextBtn").onclick = nextDocument
  $("fallbackNext").onclick = nextDocument
  $("finishBtn").onclick = finish
  $("fallbackFinish").onclick = finish
  $("fileInput").onchange = (e) => {
    addPhotos([...e.target.files])
    e.target.value = ""
  }
  $("autoBtn").onclick = () => {
    state.auto = !state.auto
    $("autoBtn").setAttribute("aria-pressed", String(state.auto))
    update(performance.now())
  }
  $("torchBtn").onclick = () => {
    const on = $("torchBtn").getAttribute("aria-pressed") !== "true"
    state.track
      ?.applyConstraints({ advanced: [{ torch: on }] })
      .then(() => $("torchBtn").setAttribute("aria-pressed", String(on)))
      .catch(() => {})
  }
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && state.running) keepAwake()
  })
  window.addEventListener("resize", () => (state.shown = null))

  boot()
})()
