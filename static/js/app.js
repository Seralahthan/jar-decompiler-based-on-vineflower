(() => {
  "use strict";

  // ── Element refs — upload flow ─────────────────────────
  const dropZone        = document.getElementById("dropZone");
  const fileInput       = document.getElementById("fileInput");
  const fileInfo        = document.getElementById("fileInfo");
  const fileName        = document.getElementById("fileName");
  const fileSize        = document.getElementById("fileSize");
  const clearBtn        = document.getElementById("clearBtn");
  const decompileBtn    = document.getElementById("decompileBtn");
  const uploadCard      = document.getElementById("uploadCard");
  const progressCard    = document.getElementById("progressCard");
  const resultCard      = document.getElementById("resultCard");
  const errorCard       = document.getElementById("errorCard");
  const progressLabel   = document.getElementById("progressLabel");
  const progressPct     = document.getElementById("progressPct");
  const progressBarFill = document.getElementById("progressBarFill");
  const progressMsg     = document.getElementById("progressMsg");
  const newJobBtn       = document.getElementById("newJobBtn");
  const errorMsg        = document.getElementById("errorMsg");
  const retryBtn        = document.getElementById("retryBtn");

  // ── Element refs — workspace ───────────────────────────
  const mainEl              = document.querySelector(".main");
  const workspacePanel      = document.getElementById("workspacePanel");
  const zipBanner           = document.getElementById("zipBanner");
  const zipBannerMsg        = document.getElementById("zipBannerMsg");
  const zipDownloadBtn      = document.getElementById("zipDownloadBtn");
  const zipBannerClose      = document.getElementById("zipBannerClose");
  const treePanel           = document.getElementById("treePanel");
  const treeTitle           = document.getElementById("treeTitle");
  const treeCount           = document.getElementById("treeCount");
  const treeSearch          = document.getElementById("treeSearch");
  const treeBody            = document.getElementById("treeBody");
  const buildZipBtn         = document.getElementById("buildZipBtn");
  const zipFooterProgress   = document.getElementById("zipFooterProgress");
  const zipFooterBarFill    = document.getElementById("zipFooterBarFill");
  const zipFooterPct        = document.getElementById("zipFooterPct");
  const findMethodsBtn      = document.getElementById("findMethodsBtn");
  const indexingHint        = document.getElementById("indexingHint");
  const indexingPct         = document.getElementById("indexingPct");
  const newJobBtn2          = document.getElementById("newJobBtn2");
  const resizeHandle        = document.getElementById("resizeHandle");
  const sourceClassname     = document.getElementById("sourceClassname");
  const sourceCopyBtn       = document.getElementById("sourceCopyBtn");
  const sourceLoading       = document.getElementById("sourceLoading");
  const sourceEmpty         = document.getElementById("sourceEmpty");
  const sourcePre           = document.getElementById("sourcePre");
  const sourceCode          = document.getElementById("sourceCode");

  // ── State ──────────────────────────────────────────────
  let selectedFile      = null;
  let currentJobId      = null;
  let activeClassPath   = null;
  let classCache        = {};
  let zipPollInterval   = null;
  let indexPollInterval = null;
  let indexReady        = false;
  let currentTreeData   = null;
  let flatClassList     = [];

  // ── Helpers ────────────────────────────────────────────
  function formatBytes(bytes) {
    if (bytes < 1024)    return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1048576).toFixed(1) + " MB";
  }

  function show(el) { el.classList.remove("hidden"); }
  function hide(el) { el.classList.add("hidden"); }

  function setProgress(pct, label, msg) {
    progressBarFill.style.width = pct + "%";
    progressPct.textContent     = pct + "%";
    progressLabel.textContent   = label;
    progressMsg.textContent     = msg || "";
  }

  function stopZipPoll() {
    if (zipPollInterval) { clearInterval(zipPollInterval); zipPollInterval = null; }
  }

  function stopIndexPoll() {
    if (indexPollInterval) { clearInterval(indexPollInterval); indexPollInterval = null; }
  }

  // ── File selection ─────────────────────────────────────
  function onFileSelected(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".jar")) {
      alert("Please select a .jar file.");
      return;
    }
    if (file.size > 200 * 1024 * 1024) {
      alert("File exceeds the 200 MB limit.");
      return;
    }
    selectedFile = file;
    fileName.textContent = file.name;
    fileSize.textContent = formatBytes(file.size);
    show(fileInfo);
  }

  // ── Drag & drop ────────────────────────────────────────
  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  });
  ["dragleave", "dragend"].forEach((evt) => {
    dropZone.addEventListener(evt, () => dropZone.classList.remove("drag-over"));
  });
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    const file = e.dataTransfer?.files?.[0];
    if (file) onFileSelected(file);
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) onFileSelected(fileInput.files[0]);
    fileInput.value = "";
  });

  clearBtn.addEventListener("click", () => {
    selectedFile = null;
    hide(fileInfo);
  });

  // ── Reset to upload view ───────────────────────────────
  function resetUI() {
    stopZipPoll();
    stopIndexPoll();
    selectedFile    = null;
    currentJobId    = null;
    activeClassPath = null;
    classCache      = {};
    indexReady      = false;
    currentTreeData = null;
    flatClassList   = [];

    hide(fileInfo);
    hide(progressCard);
    hide(resultCard);
    hide(errorCard);
    hide(workspacePanel);
    hide(zipBanner);
    hide(zipFooterProgress);
    hide(indexingHint);
    show(buildZipBtn);
    show(findMethodsBtn);
    findMethodsBtn.disabled = false;

    treeSearch.value       = "";
    treeSearch.placeholder = "Filter classes…";
    treeBody.innerHTML     = "";
    sourceCode.textContent = "";
    sourceClassname.textContent = "Select a class to view its source";

    hide(sourceCopyBtn);
    hide(sourcePre);
    show(sourceEmpty);

    show(uploadCard);
    show(mainEl);
    document.body.classList.remove("workspace-active");
  }

  newJobBtn.addEventListener("click", resetUI);
  retryBtn .addEventListener("click", resetUI);
  newJobBtn2.addEventListener("click", resetUI);

  // ── Decompile ──────────────────────────────────────────
  decompileBtn.addEventListener("click", startDecompile);

  async function startDecompile() {
    if (!selectedFile) return;

    hide(uploadCard);
    show(progressCard);
    setProgress(0, "Uploading…", "Sending file to the server…");

    const formData = new FormData();
    formData.append("jar", selectedFile);

    let jobId;
    try {
      const res  = await fetch("/api/upload", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Upload failed.");
      jobId = data.job_id;
    } catch (err) {
      showError(err.message);
      return;
    }

    setProgress(10, "Scanning JAR…", "Reading class structure…");

    try {
      const res  = await fetch(`/api/tree/${jobId}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to read JAR structure.");

      currentJobId = jobId;
      classCache   = {};
      transitionToWorkspace(data);
    } catch (err) {
      showError(err.message);
    }
  }

  // ── Workspace transition ───────────────────────────────
  function transitionToWorkspace(data) {
    hide(mainEl);
    hide(progressCard);
    show(workspacePanel);
    document.body.classList.add("workspace-active");

    currentTreeData = data;
    flatClassList   = [];

    treeTitle.textContent = data.jar_name || "JAR";
    treeCount.textContent = `${data.class_count} classes`;

    if (data.class_count === 0) {
      treeBody.innerHTML = '<div style="padding:16px;color:var(--muted);font-size:0.83rem;">No .class files found in this JAR.</div>';
    } else {
      buildFlatList(data.tree);
      renderTree(data.tree, treeBody, 0);
    }

    show(buildZipBtn);
    show(findMethodsBtn);
    hide(zipFooterProgress);
    hide(indexingHint);
  }

  // ── Build ZIP button ───────────────────────────────────
  buildZipBtn.addEventListener("click", async () => {
    if (!currentJobId) return;
    try {
      const res = await fetch(`/api/start-decompile/${currentJobId}`, { method: "POST" });
      if (!res.ok) return;
    } catch (_) { return; }

    hide(buildZipBtn);
    zipFooterBarFill.style.width = "0%";
    zipFooterPct.textContent     = "0%";
    show(zipFooterProgress);

    zipPollInterval = setInterval(() => pollZipStatus(currentJobId), 3000);
  });

  // ── Find Methods button ────────────────────────────────
  findMethodsBtn.addEventListener("click", async () => {
    if (!currentJobId) return;

    try {
      const res = await fetch(`/api/build-index/${currentJobId}`, { method: "POST" });
      const data = await res.json();
      // Index already built — activate immediately
      if (res.status === 200 && data.ok) {
        onIndexReady();
        return;
      }
      // 202: indexing just started OR already running — fall through to show progress
    } catch (_) { return; }

    findMethodsBtn.disabled = true;
    indexingPct.textContent = "Indexing…";
    show(indexingHint);

    if (!indexPollInterval) {
      indexPollInterval = setInterval(() => pollIndexStatus(currentJobId), 3000);
    }
  });

  async function pollIndexStatus(jobId) {
    try {
      const res  = await fetch(`/api/index-status/${jobId}`);
      const data = await res.json();

      const pct = data.progress || 0;
      indexingPct.textContent = `Indexing… ${pct}%`;

      if (data.status === "done") {
        stopIndexPoll();
        hide(indexingHint);
        onIndexReady();
      } else if (data.status === "error") {
        stopIndexPoll();
        hide(indexingHint);
        findMethodsBtn.disabled = false; // allow retry
      }
    } catch (_) { /* keep polling */ }
  }

  function onIndexReady() {
    indexReady = true;
    findMethodsBtn.disabled = true;
    treeSearch.placeholder = "Filter classes and methods…";
    const q = treeSearch.value.trim();
    if (q) unifiedSearch(q);
  }

  // ── Tree rendering ─────────────────────────────────────
  function renderTree(nodes, parentEl, depth) {
    for (const node of nodes) {
      if (node.type === "package") {
        const details = document.createElement("details");
        details.className = "tree-pkg";
        if (depth === 0 && nodes.length === 1) details.open = true;
        details.style.setProperty("--tree-depth", depth);

        const summary = document.createElement("summary");
        summary.textContent = node.name;
        details.appendChild(summary);

        renderTree(node.children, details, depth + 1);
        parentEl.appendChild(details);
      } else {
        const item = document.createElement("div");
        item.className = "tree-item" +
          (node.isAnonymous ? " is-anon" : node.isInner ? " is-inner" : "");
        item.style.setProperty("--tree-depth", depth);
        item.dataset.path = node.path;
        item.dataset.name = node.name.toLowerCase();
        item.textContent  = node.name;
        item.title        = node.path;
        item.addEventListener("click", () => loadClass(node.path));
        parentEl.appendChild(item);
      }
    }
  }

  function buildFlatList(nodes) {
    for (const node of nodes) {
      if (node.type === "package") buildFlatList(node.children);
      else flatClassList.push(node);
    }
  }

  function restoreTree() {
    treeBody.innerHTML = "";
    if (currentTreeData) renderTree(currentTreeData.tree, treeBody, 0);
    if (activeClassPath) {
      const item = treeBody.querySelector(`[data-path="${CSS.escape(activeClassPath)}"]`);
      if (item) {
        item.classList.add("active");
        let p = item.parentElement;
        while (p && p !== treeBody) {
          if (p.tagName === "DETAILS") p.open = true;
          p = p.parentElement;
        }
      }
    }
  }

  // ── Unified search (classes + methods when index ready) ─
  let filterDebounce = null;
  treeSearch.addEventListener("input", () => {
    clearTimeout(filterDebounce);
    const query = treeSearch.value.trim();
    filterDebounce = setTimeout(() => unifiedSearch(query), 200);
  });

  async function unifiedSearch(query) {
    if (!query) { restoreTree(); return; }

    const q = query.toLowerCase();
    const classMatches = flatClassList
      .filter(c => c.name.toLowerCase().includes(q) || c.path.toLowerCase().includes(q))
      .slice(0, 60);

    let methodMatches = [];
    if (indexReady && currentJobId) {
      try {
        const res  = await fetch(`/api/search-methods/${currentJobId}?q=${encodeURIComponent(query)}`);
        const data = await res.json();
        methodMatches = (data.results || []).slice(0, 40);
      } catch (_) {}
    }

    // Discard stale result if the user has already typed something else
    if (treeSearch.value.trim() !== query) return;

    renderFlatResults(classMatches, methodMatches);
  }

  function renderFlatResults(classMatches, methodMatches) {
    treeBody.innerHTML = "";
    if (classMatches.length === 0 && methodMatches.length === 0) {
      treeBody.innerHTML = '<div class="search-empty">No results found.</div>';
      return;
    }

    const frag       = document.createDocumentFragment();
    const showLabels = classMatches.length > 0 && methodMatches.length > 0;

    if (classMatches.length > 0) {
      if (showLabels) {
        const lbl = document.createElement("div");
        lbl.className   = "search-section-label";
        lbl.textContent = "Classes";
        frag.appendChild(lbl);
      }
      for (const c of classMatches) {
        const item = document.createElement("div");
        item.className = "tree-item" + (c.path === activeClassPath ? " active" : "");
        item.style.setProperty("--tree-depth", 0);
        item.dataset.path = c.path;
        item.dataset.name = c.name.toLowerCase();
        item.textContent  = c.name.replace(/\.class$/, "");
        item.title        = c.path;
        item.addEventListener("click", () => loadClass(c.path));
        frag.appendChild(item);
      }
    }

    if (methodMatches.length > 0) {
      if (showLabels) {
        const lbl = document.createElement("div");
        lbl.className   = "search-section-label";
        lbl.textContent = "Methods";
        frag.appendChild(lbl);
      }
      for (const r of methodMatches) {
        const item = document.createElement("div");
        item.className = "tree-item search-result-method" + (r.class_path === activeClassPath ? " active" : "");
        item.style.setProperty("--tree-depth", 0);
        item.innerHTML = `<span class="srm-name">${escapeHtml(r.method)}</span><span class="srm-class">${escapeHtml(r.class_path.replace(/\//g, ".").replace(/\.class$/, ""))}</span>`;
        item.title = r.class_path;
        item.addEventListener("click", () => loadClass(r.class_path, r.line));
        frag.appendChild(item);
      }
    }

    treeBody.appendChild(frag);
  }

  function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // ── Load and display a class ───────────────────────────
  async function loadClass(classPath, targetLine) {
    if (classPath === activeClassPath) {
      if (targetLine) scrollToLine(targetLine);
      return;
    }

    treeBody.querySelectorAll(".tree-item.active")
      .forEach(el => el.classList.remove("active"));
    const clickedItem = treeBody.querySelector(`[data-path="${CSS.escape(classPath)}"]`);
    if (clickedItem) clickedItem.classList.add("active");

    activeClassPath = classPath;
    sourceClassname.textContent = classPath.replace(/\//g, ".").replace(/\.class$/, "");

    hide(sourceCopyBtn);
    hide(sourceEmpty);
    hide(sourcePre);
    show(sourceLoading);

    if (classCache[classPath] !== undefined) {
      displaySource(classCache[classPath], targetLine);
      return;
    }

    try {
      const res  = await fetch(`/api/decompile-class/${currentJobId}`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ class_path: classPath }),
      });
      const data = await res.json();

      if (!res.ok || data.error) {
        showSourceError(data.error || "Decompilation failed");
        return;
      }

      classCache[classPath] = data.source;
      displaySource(data.source, targetLine);
    } catch (err) {
      showSourceError(err.message);
    }
  }

  function displaySource(source, targetLine) {
    hide(sourceLoading);
    hide(sourceEmpty);
    sourceCode.textContent = source;
    sourceCode.removeAttribute("data-highlighted");
    show(sourcePre);
    show(sourceCopyBtn);
    if (typeof hljs !== "undefined") {
      hljs.highlightElement(sourceCode);
      if (typeof hljs.lineNumbersBlock === "function") {
        hljs.lineNumbersBlock(sourceCode);
      }
    }
    if (targetLine) {
      // The line-numbers plugin renders asynchronously via setTimeout(0),
      // so we wait a tick before querying the generated table rows.
      setTimeout(() => scrollToLine(targetLine), 50);
    }
  }

  function scrollToLine(line) {
    sourcePre.querySelectorAll("tr.method-target").forEach(r => r.classList.remove("method-target"));
    const targetRow = sourcePre.querySelector(`[data-line-number="${line}"]`)?.closest("tr");
    if (targetRow) {
      targetRow.classList.add("method-target");
      targetRow.scrollIntoView({ block: "center" });
    }
  }

  function showSourceError(msg) {
    hide(sourceLoading);
    sourceCode.textContent = "// Could not decompile this class:\n// " + msg;
    sourceCode.removeAttribute("data-highlighted");
    show(sourcePre);
    if (typeof hljs !== "undefined") {
      hljs.highlightElement(sourceCode);
    }
  }

  // ── Copy source ────────────────────────────────────────
  sourceCopyBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(sourceCode.textContent).then(() => {
      const orig = sourceCopyBtn.textContent;
      sourceCopyBtn.textContent = "Copied!";
      setTimeout(() => { sourceCopyBtn.textContent = orig; }, 1500);
    });
  });

  // ── ZIP status polling (drives footer progress bar) ────
  async function pollZipStatus(jobId) {
    try {
      const res  = await fetch(`/api/status/${jobId}`);
      const data = await res.json();

      const pct = data.progress || 0;
      zipFooterBarFill.style.width = pct + "%";
      zipFooterPct.textContent     = pct + "%";

      if (data.status === "done") {
        stopZipPoll();
        hide(zipFooterProgress);
        zipDownloadBtn.href = `/api/download/${jobId}`;
        zipBannerMsg.textContent = data.message || "Full decompilation complete!";
        show(zipBanner);
      } else if (data.status === "error") {
        stopZipPoll();
        hide(zipFooterProgress);
        show(buildZipBtn);
      }
    } catch (_) { /* network glitch — keep polling */ }
  }

  zipBannerClose.addEventListener("click", () => hide(zipBanner));

  // ── Resize handle ──────────────────────────────────────
  let isDragging     = false;
  let dragStartX     = 0;
  let dragStartWidth = 0;

  resizeHandle.addEventListener("mousedown", (e) => {
    isDragging     = true;
    dragStartX     = e.clientX;
    dragStartWidth = treePanel.getBoundingClientRect().width;
    resizeHandle.classList.add("dragging");
    document.body.style.cursor     = "col-resize";
    document.body.style.userSelect = "none";
    e.preventDefault();
  });

  document.addEventListener("mousemove", (e) => {
    if (!isDragging) return;
    const newWidth = Math.max(160, Math.min(500, dragStartWidth + (e.clientX - dragStartX)));
    treePanel.style.width = newWidth + "px";
  });

  document.addEventListener("mouseup", () => {
    if (!isDragging) return;
    isDragging = false;
    resizeHandle.classList.remove("dragging");
    document.body.style.cursor     = "";
    document.body.style.userSelect = "";
  });

  // ── Error card helper ──────────────────────────────────
  function showError(msg) {
    hide(progressCard);
    hide(uploadCard);
    errorMsg.textContent = msg;
    show(errorCard);
  }
})();
