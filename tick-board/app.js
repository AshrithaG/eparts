import * as gh from "./github-sync.js";

const COLUMN_LABELS = {
  backlog: "Backlog",
  "spec-ready": "Spec Ready",
  "in-build": "In Build",
  "in-review": "In Review",
  integrated: "Integrated",
  "demo-d": "Demo'd",
};

const BACKLOG_TICK_ID = "BACKLOG";

const state = {
  board: null,
  sha: null,
  ownerRepo: null,
  draggingId: null,
  editingCardId: null,
  panel: null,
  collisionBanner: false,
  searchQuery: "",
  archiveReadOnlyBoard: null,
  archiveSnapshotLabel: "",
  toast: "",
  polling: false,
};

const el = (id) => document.getElementById(id);

function showToast(message, ms = 4000) {
  state.toast = message;
  renderChrome();
  setTimeout(() => {
    state.toast = "";
    renderChrome();
  }, ms);
}

function nextArchiveNumber() {
  const archived = state.board.ticks.filter((t) => t.status === "archived");
  return String(archived.length + 1).padStart(2, "0");
}

/** Tick IDs considered archived */
function archivedTickIdSet() {
  return new Set(
    state.board.ticks.filter((t) => t.status === "archived").map((t) => t.tickId),
  );
}

/** Per spec Step 3.4: hide demo-d cards belonging to archived ticks */
function cardHiddenFromBoard(card) {
  const archivedIds = archivedTickIdSet();
  return archivedIds.has(card.tickId) && card.column === "demo-d";
}

function tickThroughputSeries() {
  const ticks = [...state.board.ticks];
  if (state.board.currentTick && state.board.currentTick.status === "active") {
    const exists = ticks.some((t) => t.tickId === state.board.currentTick.tickId);
    if (!exists) ticks.push({ ...state.board.currentTick, status: "active" });
  }
  ticks.sort((a, b) => a.tickId.localeCompare(b.tickId));
  const byTick = ticks.map((t) => ({
    tickId: t.tickId,
    label: t.tickLabel || t.tickId,
    count: state.board.cards.filter(
      (c) =>
        c.tickId === t.tickId &&
        (c.column === "integrated" || c.column === "demo-d"),
    ).length,
  }));
  const max = Math.max(1, ...byTick.map((x) => x.count));
  return { rows: byTick, max };
}

function ensureLogin() {
  const token = gh.getToken();
  const ownerRepo = gh.resolveOwnerRepo();
  state.ownerRepo = ownerRepo;
  if (!token || !ownerRepo)
    openPanel("pat");
}

async function reloadBoardQuiet() {
  const token = gh.getToken();
  if (!token || !state.ownerRepo) return;
  try {
    const { data, sha } = await gh.loadBoard(token, state.ownerRepo);
    state.board = data;
    state.sha = sha;
    state.collisionBanner = false;
    renderAll();
    showToast("Board reloaded — remote changes applied.");
  } catch (e) {
    showToast(String(e.message || e), 6000);
  }
}

async function saveBoard(commitMsg) {
  const token = gh.getToken();
  if (!token || !state.ownerRepo || !state.board || !state.sha) {
    ensureLogin();
    throw new Error("Not ready to save.");
  }
  try {
    const newSha = await gh.saveBoard(
      state.board,
      commitMsg || "chore(board): update",
      state.sha,
      token,
      state.ownerRepo,
    );
    state.sha = newSha;
    state.collisionBanner = false;
    renderAll();
  } catch (e) {
    if (
      e.code === 409 ||
      e.code === 422 ||
      String(e.message || "") === "SHA_CONFLICT"
    ) {
      state.collisionBanner = true;
      renderChrome();
      throw e;
    }
    throw e;
  }
}

function openPanel(which) {
  state.panel = which;
  renderChrome();
}

function closePanel() {
  state.panel = null;
  renderChrome();
}

/** Retro textarea template */
function retroTemplate(ct) {
  const tickId = ct.tickId || "T???";
  const tickLabel = ct.tickLabel || "";
  return `## Tick ${tickId} · ${tickLabel} Retro

### What went well
- 

### What didn't go well
- 

### AAS process check
- Validation Hours accuracy:
- Review Tier distribution:
- AI-rejection rate:

### Action items for next Tick
- 
`;
}

function renderCollisionBanner() {
  const host = el("collisionBanner");
  if (!host) return;
  if (!state.collisionBanner) {
    host.innerHTML = "";
    return;
  }
  host.innerHTML = `
    <div class="rounded border border-amber-400 bg-amber-50 px-4 py-2 text-sm text-amber-900">
      Someone else just updated the board. Refresh to see their changes, then re-apply yours.
      <button type="button" id="btnReloadBoard" class="ml-3 rounded bg-amber-700 px-2 py-0.5 text-white hover:bg-amber-800">
        Reload board
      </button>
    </div>`;
  el("btnReloadBoard").onclick = reloadBoardQuiet;
}

function renderToast() {
  const host = el("toastHost");
  if (!host) return;
  if (!state.toast) {
    host.innerHTML = "";
    return;
  }
  host.innerHTML = `
    <div class="fixed bottom-4 right-4 z-50 rounded-lg bg-slate-900 px-4 py-3 text-sm text-white shadow-lg">
      ${escapeHtml(state.toast)}
    </div>`;
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function renderThroughputChart() {
  const host = el("throughputChart");
  if (!host || !state.board) return;
  const { rows, max } = tickThroughputSeries();
  const w = 220;
  const h = 56;
  const barW = w / Math.max(rows.length, 1) - 4;
  const bars = rows
    .map((r, i) => {
      const bh = (r.count / max) * (h - 16);
      const x = 4 + i * (barW + 4);
      const y = h - bh - 4;
      return `<rect x="${x}" y="${y}" width="${barW}" height="${bh}" rx="3" fill="#334155"/>
        <title>${escapeHtml(r.tickId)}: ${r.count} integrated</title>`;
    })
    .join("");
  const labels = rows
    .map((r, i) => {
      const x = 4 + i * (barW + 4) + barW / 2;
      return `<text x="${x}" y="${h}" text-anchor="middle" font-size="9" fill="#64748b">${escapeHtml(
        r.tickId,
      )}</text>`;
    })
    .join("");
  host.innerHTML = `
    <div class="flex items-center gap-2">
      <span class="text-xs text-slate-500">Throughput</span>
      <svg width="${w}" height="${h + 12}" xmlns="http://www.w3.org/2000/svg">${bars}${labels}</svg>
    </div>`;
}

function renderChrome() {
  renderCollisionBanner();
  renderToast();
  renderPatModal();
  renderTickPanel();
  renderArchiveOverlay();
}

function renderAll() {
  renderKanban();
  renderThroughputChart();
  renderChrome();
}

function tierBadgeClasses(tier) {
  if (tier === "T1") return "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-600/40";
  if (tier === "T2") return "bg-amber-100 text-amber-900 ring-1 ring-amber-600/30";
  if (tier === "T3") return "bg-red-100 text-red-800 ring-1 ring-red-600/30";
  return "bg-slate-100 text-slate-700";
}

function renderKanban() {
  const boardHost = el("kanbanBoard");
  if (!boardHost || !state.board) return;
  const archivedRO = !!state.archiveReadOnlyBoard;

  let cards = archivedRO ? state.archiveReadOnlyBoard.cards : state.board.cards;
  const fq = state.searchQuery.trim().toLowerCase();

  const columns = state.board.config.columns;

  boardHost.innerHTML = columns
    .map((col) => {
      const colCards = cards.filter((c) => {
        if (!archivedRO && cardHiddenFromBoard(c)) return false;
        if (c.column !== col) return false;
        if (!fq) return true;
        return (
          c.title.toLowerCase().includes(fq) ||
          (c.assignee || "").toLowerCase().includes(fq) ||
          (c.tickId || "").toLowerCase().includes(fq)
        );
      });
      const dropAttrs = archivedRO
        ? ""
        : `ondragover="event.preventDefault()" ondrop="window.__tickBoardDrop(event,'${col}')"`;
      return `
      <section class="flex min-w-[260px] max-w-[320px] flex-1 flex-col rounded-xl bg-slate-50 ring-1 ring-slate-200" ${dropAttrs}>
        <header class="border-b border-slate-200 px-3 py-2 font-semibold text-slate-800">
          ${COLUMN_LABELS[col] || col}
          <span class="ml-1 text-xs font-normal text-slate-500">${colCards.length}</span>
        </header>
        <div class="flex flex-1 flex-col gap-2 overflow-y-auto p-2 ${archivedRO ? "min-h-[200px]" : "min-h-[320px]"}" data-column="${col}">
          ${colCards.map((c) => cardMarkup(c, archivedRO)).join("")}
        </div>
      </section>`;
    })
    .join("");

  if (!archivedRO) wireDragHandlers();

  boardHost.onclick = (e) => {
    const card = e.target.closest("[data-card-id]");
    if (!card || archivedRO) return;
    const id = card.getAttribute("data-card-id");
    if (id) editCard(id);
  };
}

function cardMarkup(c, readOnly) {
  const draggable = readOnly ? "false" : "true";
  const cursor = readOnly ? "cursor-default" : "cursor-grab active:cursor-grabbing";
  return `
  <article
    draggable="${draggable}"
    data-card-id="${escapeHtml(c.id)}"
    class="rounded-lg border border-slate-200 bg-white p-3 shadow-sm hover:shadow ${cursor}">
    <div class="flex items-start justify-between gap-2">
      <h3 class="font-medium text-slate-900">${escapeHtml(c.title)}</h3>
      ${
        c.aiRejected
          ? '<span class="shrink-0 rounded bg-rose-600 px-1.5 py-0.5 text-[10px] font-bold uppercase text-white">AI-rejected</span>'
          : ""
      }
    </div>
    <div class="mt-2 flex flex-wrap items-center gap-1">
      <span class="rounded bg-violet-100 px-2 py-0.5 font-mono text-xs text-violet-800">${escapeHtml(
        c.tickId,
      )}</span>
      <span class="${tierBadgeClasses(c.reviewTier)} rounded px-2 py-0.5 text-xs">${escapeHtml(
        c.reviewTier,
      )}</span>
      <span class="text-xs text-slate-600">${escapeHtml(String(c.validationHours ?? 0))} VH</span>
    </div>
    <div class="mt-1 text-xs text-slate-500">${escapeHtml(c.assignee || "—")}</div>
    ${
      !readOnly && c.aiRejected && c.rejectReason
        ? `<div class="mt-1 text-xs italic text-rose-700">${escapeHtml(c.rejectReason)}</div>`
        : ""
    }
  </article>`;
}

window.__tickBoardDrop = async (ev, col) => {
  ev.preventDefault();
  const id = state.draggingId || ev.dataTransfer.getData("text/plain");
  if (!id || !state.board || state.archiveReadOnlyBoard) return;
  const card = state.board.cards.find((c) => c.id === id);
  if (!card) return;
  if (card.column === col) return;
  card.column = col;
  card.updatedAt = new Date().toISOString();
  try {
    await saveBoard(`chore(board): move ${card.id} → ${col}`);
  } catch {
    reloadBoardQuiet();
  }
  state.draggingId = null;
};

function wireDragHandlers() {
  document.querySelectorAll("[data-card-id]").forEach((node) => {
    node.addEventListener("dragstart", (ev) => {
      const id = node.getAttribute("data-card-id");
      state.draggingId = id;
      ev.dataTransfer.setData("text/plain", id);
      ev.dataTransfer.effectAllowed = "move";
    });
  });
}

function renderPatModal() {
  const modal = el("modalPat");
  if (!modal) return;
  if (state.panel !== "pat") {
    modal.innerHTML = "";
    modal.classList.add("hidden");
    return;
  }
  modal.classList.remove("hidden");
  modal.innerHTML = `
    <div class="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4">
      <div class="max-h-[90vh] overflow-y-auto rounded-2xl bg-white p-6 shadow-xl max-w-lg w-full ring-1 ring-slate-200">
        <h2 class="text-lg font-semibold text-slate-900">GitHub access</h2>
        <p class="mt-3 text-sm text-slate-600">
          Persistence uses your <strong class="font-medium">fine-grained personal access token</strong> (stored only in this browser).
        </p>
        <ol class="mt-3 list-decimal space-y-1 ps-5 text-xs text-slate-600">
          <li>GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate.</li>
          <li>Repository access → Only select repositories → pick this repo (<code class="rounded bg-slate-100 px-1">eparts</code> or team repo).</li>
          <li>Permissions: <strong>Contents</strong> → Read and write.</li>
          <li>Generate, copy token (often starts with <code class="rounded bg-slate-100 px-1">github_pat_</code>).</li>
          <li>Paste below.</li>
        </ol>
        ${
          !gh.inferGitHubRepo()
            ? `<label class="mt-4 block text-xs font-semibold uppercase text-slate-500">
                Repo owner<input id="fldOwner" class="mt-1 w-full rounded border border-slate-300 px-2 py-2 text-sm uppercase" placeholder="org-or-user" autocomplete="off" />
              </label>
              <label class="mt-2 block text-xs font-semibold uppercase text-slate-500">
                Repo name<input id="fldRepo" class="mt-1 w-full rounded border border-slate-300 px-2 py-2 text-sm" placeholder="eparts" autocomplete="off" />
              </label>`
            : ""
        }
        <label class="mt-4 block text-xs font-semibold uppercase text-slate-500">Token<input id="fldPat" type="password" autocomplete="current-password"
          class="mt-1 w-full rounded border border-slate-300 px-3 py-2 font-mono text-sm" placeholder="Paste token" /></label>
        <div class="mt-5 flex gap-2">
          <button type="button" id="btnPatSave" class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800">Save & load</button>
          <button type="button" id="btnPatCancel" class="rounded-lg border border-slate-300 px-4 py-2 text-sm hover:bg-slate-50">Cancel</button>
        </div>
      </div>
    </div>`;

  el("btnPatCancel").onclick = () => closePanel();
  el("btnPatSave").onclick = async () => {
    const pat = el("fldPat").value;
    gh.setToken(pat);
    let ownerRepo = gh.inferGitHubRepo();
    if (!ownerRepo) {
      ownerRepo = { owner: el("fldOwner").value.trim(), repo: el("fldRepo").value.trim() };
      gh.setSavedRepoOverrides(ownerRepo.owner, ownerRepo.repo);
    } else gh.setSavedRepoOverrides(null, null);
    try {
      const { data, sha } = await gh.loadBoard(pat.trim(), gh.resolveOwnerRepo());
      state.board = data;
      state.sha = sha;
      state.ownerRepo = gh.resolveOwnerRepo();
      closePanel();
      renderAll();
      startPolling();
    } catch (e) {
      alert(String(e.message || e));
    }
  };
}

function renderTickPanel() {
  const drawer = el("tickPanel");
  if (!drawer) return;
  if (state.panel === "completeTick") {
    drawer.classList.remove("hidden");
    return;
  }
  if (state.panel !== "tick") {
    drawer.classList.add("hidden");
    return;
  }
  drawer.classList.remove("hidden");
  const ct = state.board?.currentTick;
  if (!ct) {
    drawer.innerHTML =
      '<p class="text-sm text-slate-600">Load the board first.</p>';
    return;
  }

  let vhCommitted = 0;
  let vhIntegrated = 0;
  for (const c of state.board.cards) {
    if (c.tickId !== ct.tickId) continue;
    vhCommitted += Number(c.validationHours) || 0;
    if (c.column === "integrated" || c.column === "demo-d") {
      vhIntegrated += Number(c.validationHours) || 0;
    }
  }

  drawer.innerHTML = `
    <div class="mb-4 flex items-center justify-between">
      <h2 class="text-lg font-semibold text-slate-900">Active tick</h2>
      <button type="button" id="closeTickPanel" class="rounded p-1 text-slate-500 hover:bg-slate-100">✕</button>
    </div>
    <div class="rounded-lg border border-violet-200 bg-violet-50 p-4 text-sm">
      <div class="font-mono font-bold text-violet-900">${escapeHtml(ct.tickId)}</div>
      <div class="text-slate-800">${escapeHtml(ct.tickLabel || "")}</div>
      <div class="mt-2 text-xs text-violet-800">${escapeHtml(ct.startDate || "")} → ${escapeHtml(
        ct.endDate || "",
      )} · Stream ${escapeHtml(ct.stream || "")}</div>
      <dl class="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div><dt class="text-slate-500">VH committed</dt><dd class="font-semibold">${vhCommitted}</dd></div>
        <div><dt class="text-slate-500">VH integrated</dt><dd class="font-semibold">${vhIntegrated}</dd></div>
      </dl>
    </div>
    <button type="button" id="btnMarkTickDone" class="mt-6 w-full rounded-lg bg-emerald-600 py-3 text-center text-sm font-semibold text-white hover:bg-emerald-700">
      Mark tick complete…
    </button>`;

  el("closeTickPanel").onclick = () => closePanel();
  el("btnMarkTickDone").onclick = openCompleteTickWizard;
}

function openCompleteTickWizard() {
  const ct = state.board.currentTick;
  if (!ct) return;
  const ta = retroTemplate(ct);
  state.panel = "completeTick";
  const drawer = el("tickPanel");
  drawer.classList.remove("hidden");
  drawer.innerHTML = `
    <div class="mb-4 flex items-center justify-between">
      <h2 class="text-lg font-semibold text-slate-900">Complete ${escapeHtml(ct.tickId)}</h2>
      <button type="button" id="closeComplete" class="rounded p-1 text-slate-500 hover:bg-slate-100">✕</button>
    </div>
    <label class="text-xs font-semibold uppercase text-slate-500">Retro notes
      <textarea id="retroNotes" rows="14" class="mt-2 w-full rounded-lg border border-slate-300 p-3 font-mono text-xs">${escapeHtml(
        ta.trim(),
      )}</textarea></label>
    <p class="mt-2 text-xs text-slate-500">Snapshots cards for this tick, archives board state, hides demoʼd cards for this tick.</p>

    <h3 class="mt-6 text-xs font-semibold uppercase text-slate-500">Next tick</h3>
    <label class="mt-1 block text-xs text-slate-600">tickId<input id="nextTickId" class="mt-1 w-full rounded border px-2 py-1 font-mono text-sm" /></label>
    <label class="mt-2 block text-xs text-slate-600">Label<input id="nextTickLabel" class="mt-1 w-full rounded border px-2 py-1 text-sm" /></label>
    <label class="mt-2 block text-xs text-slate-600">Stream<select id="nextStream" class="mt-1 w-full rounded border px-2 py-1"><option>A</option><option>B</option></select></label>
    <label class="mt-2 block text-xs text-slate-600">Start<input type="date" id="nextStart" class="mt-1 w-full rounded border px-2 py-1"/></label>
    <label class="mt-2 block text-xs text-slate-600">End<input type="date" id="nextEnd" class="mt-1 w-full rounded border px-2 py-1"/></label>
    <div class="mt-6 flex gap-2">
      <button type="button" id="btnConfirmComplete" class="flex-1 rounded-lg bg-emerald-600 py-3 text-sm font-semibold text-white">Confirm</button>
      <button type="button" id="btnCancelComplete" class="rounded-lg border px-4 py-2 text-sm">Back</button>
    </div>`;

  const m = /\bT(\d+)/.exec(ct.tickId);
  const n = m ? parseInt(m[1], 10) + 1 : 2;
  el("nextTickId").value = `T${String(n).padStart(3, "0")}`;
  el("nextTickLabel").value = "";
  el("nextStream").value = ct.stream === "A" ? "B" : "A";

  el("closeComplete").onclick =
    el("btnCancelComplete").onclick = () =>
    openPanel("tick");

  const nextWeekStart = ct.endDate
    ? ct.endDate
    : ct.startDate || "";
  el("nextStart").value = nextWeekStart;
  el("nextEnd").value = nextWeekStart || "";

  el("btnConfirmComplete").onclick = async () => {
    const nid = el("nextTickId").value.trim();
    if (!nid) {
      alert("Enter next tick ID.");
      return;
    }
    if (!el("nextStart").value || !el("nextEnd").value) {
      alert("Set next tick start and end dates.");
      return;
    }
    await doCompleteTick();
  };
}

async function doCompleteTick() {
  const ct = state.board.currentTick;
  const retro = el("retroNotes").value;
  const archiveNum = nextArchiveNumber();
  const archiveRel = `${gh.ARCHIVE_PREFIX}tick-${archiveNum}.json`;
  const snap = {
    schemaVersion: 1,
    archivedAt: new Date().toISOString(),
    tick: { ...ct, status: "archived", retroNotes: retro, archivePath: archiveRel },
    cards: state.board.cards.filter((c) => c.tickId === ct.tickId),
  };

  try {
    const token = gh.getToken();
    await gh.archiveTickFile(
      archiveRel,
      snap,
      `chore(board): archive ${ct.tickId} snapshot`,
      token,
      state.ownerRepo,
    );

    state.board.ticks.push({
      tickId: ct.tickId,
      tickLabel: ct.tickLabel,
      stream: ct.stream,
      startDate: ct.startDate,
      endDate: ct.endDate,
      status: "archived",
      archivePath: archiveRel,
      retroNotes: retro,
    });

    const next = {
      tickId: el("nextTickId").value.trim(),
      tickLabel: el("nextTickLabel").value.trim() || `Tick · ${el("nextTickId").value.trim()}`,
      stream: el("nextStream").value,
      startDate: el("nextStart").value,
      endDate: el("nextEnd").value,
      status: "active",
    };
    state.board.currentTick = next;

    await saveBoard(`chore(board): complete ${ct.tickId}, archive ${archiveRel}`);
    closePanel();
    showToast(`Archived ${archiveRel}`, 5000);
    renderAll();
  } catch (e) {
    alert(String(e.message || e));
  }
}

function renderArchiveOverlay() {
  const overlay = el("modalArchive");
  if (!overlay) return;
  if (state.panel !== "archive") {
    overlay.innerHTML = "";
    overlay.classList.add("hidden");
    return;
  }
  overlay.classList.remove("hidden");
  const archived = state.board.ticks.filter((t) => t.status === "archived");

  overlay.innerHTML = `
    <div class="fixed inset-0 z-[90] overflow-y-auto bg-black/45 p-4">
      <div class="mx-auto max-w-3xl rounded-2xl bg-white p-6 shadow-xl ring-1 ring-slate-200">
        <div class="flex items-start justify-between">
          <h2 class="text-lg font-semibold text-slate-900">Archived ticks</h2>
          <button type="button" id="closeArchiveBtn" class="rounded px-3 py-1 text-sm hover:bg-slate-100">Close</button>
        </div>
        <table class="mt-4 w-full text-left text-sm">
          <thead><tr class="border-b border-slate-200 text-xs uppercase text-slate-500"><th class="pb-2">ID</th><th class="pb-2">Label</th><th class="pb-2">Dates</th><th class="pb-2">Retro</th><th></th></tr></thead>
          <tbody>
            ${archived
              .map(
                (t) => `
              <tr class="border-b border-slate-100">
                <td class="py-2 font-mono">${escapeHtml(t.tickId)}</td>
                <td>${escapeHtml(t.tickLabel)}</td>
                <td class="text-xs text-slate-600">${escapeHtml(t.startDate)} → ${escapeHtml(
                  t.endDate,
                )}</td>
                <td class="max-w-[200px] truncate text-xs text-slate-500">${escapeHtml(
                  (t.retroNotes || "").slice(0, 80),
                )}${(t.retroNotes || "").length > 80 ? "…" : ""}</td>
                <td><button type="button" class="viewArchived rounded bg-slate-100 px-2 py-1 text-xs" data-archive="${escapeHtml(
                  t.archivePath || "",
                )}">View</button></td>
              </tr>`,
              )
              .join("") || `<tr><td colspan="5" class="py-8 text-center text-slate-500">No archived ticks.</td></tr>`}
          </tbody>
        </table>
      </div>
    </div>`;

  el("closeArchiveBtn").onclick = () => {
    closePanel();
    resetReadonlyView();
  };

  overlay.querySelectorAll(".viewArchived").forEach((btn) => {
    btn.onclick = async () => {
      const ap = btn.getAttribute("data-archive");
      await openArchiveReadOnly(ap);
    };
  });
}

async function openArchiveReadOnly(archivePath) {
  closePanel();
  const token = gh.getToken();
  try {
    const res = await gh.fetchRepoFile(token, state.ownerRepo, archivePath);
    if (!res || !res.data.cards) throw new Error("Invalid snapshot.");
    state.archiveReadOnlyBoard = res.data;
    state.archiveSnapshotLabel = archivePath;
    const lbl = el("snapshotLabelHint");
    if (lbl) lbl.textContent = archivePath;
    el("readonlyBanner").classList.remove("hidden");
    renderAll();
  } catch (e) {
    alert(String(e.message || e));
  }
}

function resetReadonlyView() {
  state.archiveReadOnlyBoard = null;
  state.archiveSnapshotLabel = "";
  const lbl = el("snapshotLabelHint");
  if (lbl) lbl.textContent = "";
  el("readonlyBanner")?.classList.add("hidden");
  renderKanban();
}

function newCard() {
  state.editingCardId = "__new__";
  openModalEditor(null);
}

function editCard(id) {
  state.editingCardId = id;
  const c = state.board.cards.find((x) => x.id === id);
  openModalEditor(c);
}

function openModalEditor(card) {
  const isNew = !card;
  const columns = [...state.board.config.columns];
  const team = state.board.config.team;
  const tiers = state.board.config.tiers;
  const activeTickId =
    state.board.currentTick?.status === "active"
      ? state.board.currentTick.tickId
      : BACKLOG_TICK_ID;

  document.getElementById("modalEditor").innerHTML = `
    <div class="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4" id="editorBackdrop">
      <div class="max-h-[90vh] overflow-y-auto w-full max-w-xl rounded-2xl bg-white p-6 shadow-xl ring-1 ring-slate-200">
        <h2 class="text-lg font-semibold">${isNew ? "New Spec Card" : "Edit Spec Card"}</h2>

        <label class="mt-4 block text-xs font-semibold uppercase text-slate-500">Title
          <input id="ecfTitle" class="mt-1 w-full rounded border px-3 py-2 text-sm" /></label>
        <label class="mt-2 block text-xs font-semibold uppercase text-slate-500">Intent
          <textarea id="ecfIntent" rows="2" class="mt-1 w-full rounded border px-3 py-2 text-sm"></textarea></label>
        <label class="mt-2 block text-xs font-semibold uppercase text-slate-500">Acceptance criteria (one per line)
          <textarea id="ecfAC" rows="4" class="mt-1 w-full rounded border px-3 py-2 font-mono text-xs"></textarea></label>
        <label class="mt-2 block text-xs font-semibold uppercase text-slate-500">Detailed spec
          <textarea id="ecfDetailed" rows="3" class="mt-1 w-full rounded border px-3 py-2 text-xs"></textarea></label>

        <div class="mt-4 grid grid-cols-2 gap-3">
          <label class="text-xs font-semibold uppercase text-slate-500">VH
            <input id="ecfVh" type="number" step="0.5" min="0" class="mt-1 w-full rounded border px-3 py-2 text-sm"/></label>
          <label class="text-xs font-semibold uppercase text-slate-500">Review tier
            <select id="ecfTier" class="mt-1 w-full rounded border px-3 py-2">
              ${tiers.map((t) => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join("")}
            </select></label>
        </div>

        <div class="mt-4 grid grid-cols-2 gap-3">
          <label class="text-xs font-semibold uppercase text-slate-500">Tick
            <select id="ecfTick" class="mt-1 w-full rounded border px-3 py-2 font-mono text-sm"></select></label>
          <label class="text-xs font-semibold uppercase text-slate-500">Assignee
            <select id="ecfAssignee" class="mt-1 w-full rounded border px-3 py-2">${team.map(
              (n) =>
                `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`,
            )}</select></label>
        </div>

        <label class="mt-4 block text-xs font-semibold uppercase text-slate-500">Column
          <select id="ecfCol" class="mt-1 w-full rounded border px-3 py-2">${columns.map(
            (col) =>
              `<option value="${escapeHtml(col)}">${escapeHtml(
                COLUMN_LABELS[col] || col,
              )}</option>`,
          )}</select></label>

        <label class="mt-3 flex cursor-pointer items-center gap-2 text-sm">
          <input type="checkbox" id="ecfAI"/> AI rejection</label>

        <div class="mt-8 flex gap-3">
          <button type="button" id="ecfSave" class="flex-1 rounded-lg bg-slate-900 py-3 text-center text-sm font-semibold text-white">Save</button>
          ${isNew ? "" : '<button type="button" id="ecfDel" class="rounded-lg border border-rose-200 px-4 py-2 text-sm text-rose-700">Delete</button>'}
          <button type="button" id="ecfCancel" class="rounded-lg border px-4 py-2 text-sm">Cancel</button>
        </div>
      </div>
    </div>`;

  const tickSel = el("ecfTick");
  tickSel.innerHTML =
    `<option value="${BACKLOG_TICK_ID}">Backlog</option>` +
    (state.board.currentTick && state.board.currentTick.status === "active"
      ? `<option value="${escapeHtml(activeTickId)}">${escapeHtml(
          activeTickId,
        )} (active)</option>`
      : "");

  const fillTick = card?.tickId || activeTickId;
  if (tickSel.querySelector(`option[value="${fillTick}"`))
    tickSel.value = fillTick;
  else tickSel.value = BACKLOG_TICK_ID;

  if (!isNew) {
    el("ecfTitle").value = card.title;
    el("ecfIntent").value = card.intent || "";
    el("ecfAC").value = (card.acceptanceCriteria || []).join("\n");
    el("ecfDetailed").value = card.detailedSpec || "";
    el("ecfVh").value = card.validationHours ?? 1;
    el("ecfTier").value = card.reviewTier || "T2";
    el("ecfAssignee").value = card.assignee || team[0];
    el("ecfCol").value = card.column;
    el("ecfAI").checked = !!card.aiRejected;
  } else {
    el("ecfTitle").value = "";
    el("ecfIntent").value = "";
    el("ecfAC").value = "";
    el("ecfDetailed").value = "";
    el("ecfVh").value = 2;
    el("ecfTier").value = "T2";
    el("ecfAssignee").value = team[0];
    el("ecfCol").value = columns[0];
    el("ecfAI").checked = false;
  }

  el("editorBackdrop").onclick = (ev) => {
    if (ev.target.id === "editorBackdrop") closeModalEditor();
  };
  el("ecfCancel").onclick = () => closeModalEditor();
  if (!isNew) {
    el("ecfDel").onclick = async () => {
      if (!confirm("Delete card?")) return;
      state.board.cards = state.board.cards.filter((c) => c.id !== card.id);
      closeModalEditor();
      await saveBoard(`chore(board): delete ${card.id}`);
    };
  }

  el("ecfSave").onclick = async () => {
    const acText = el("ecfAC").value
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    const tickVal = tickSel.value;
    const draft = {
      title: el("ecfTitle").value.trim(),
      intent: el("ecfIntent").value.trim(),
      acceptanceCriteria: acText,
      detailedSpec: el("ecfDetailed").value.trim(),
      validationHours: parseFloat(el("ecfVh").value) || 0,
      reviewTier: el("ecfTier").value,
      tickId: tickVal,
      stream:
        tickVal === BACKLOG_TICK_ID ? null : state.board.currentTick?.stream || "A",
      column: el("ecfCol").value,
      assignee: el("ecfAssignee").value,
      aiRejected: el("ecfAI").checked,
      updatedAt: new Date().toISOString(),
      definitionOfDone: ["Tested", "Reviewed", "Integrated"],
    };
    if (!draft.title) {
      alert("Title required.");
      return;
    }
    if (isNew) {
      draft.id =
        `SC-${Date.now().toString(36).toUpperCase()}`;
      draft.createdAt = draft.updatedAt;
      state.board.cards.push(draft);
      await saveBoard(`chore(board): add ${draft.id}`);
    } else {
      Object.assign(card, draft);
      await saveBoard(`chore(board): update ${card.id}`);
    }
    closeModalEditor();
  };
}

function closeModalEditor() {
  document.getElementById("modalEditor").innerHTML = "";
  state.editingCardId = null;
}

function exportCsv() {
  if (!state.board) return;
  const cols = [
    "id",
    "title",
    "intent",
    "acceptanceCriteria",
    "detailedSpec",
    "validationHours",
    "reviewTier",
    "tickId",
    "column",
    "assignee",
    "aiRejected",
    "createdAt",
    "updatedAt",
  ];
  const rows = [
    cols.join(","),
    ...state.board.cards.map((c) =>
      cols
        .map((k) => {
          let v = c[k];
          if (k === "acceptanceCriteria" && Array.isArray(v))
            v = JSON.stringify(v);
          if (
            typeof v === "string" &&
            (v.includes(",") || v.includes('"') || v.includes("\n"))
          ) {
            v = `"${v.replace(/"/g, '""')}"`;
          }
          return v == null ? "" : v;
        })
        .join(","),
    ),
  ];
  const blob = new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `board-export-${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function bootstrap() {
  el("btnOpenPat").onclick = () => openPanel("pat");
  el("btnLogout").onclick = () => {
    gh.setToken("");
    gh.setSavedRepoOverrides(null, null);
    state.board = null;
    state.sha = null;
    openPanel("pat");
  };
  el("btnAddCard").onclick = () => newCard();
  el("btnExport").onclick = () => exportCsv();
  el("btnTickPanel").onclick = () =>
    openPanel(
      state.panel === "tick" || state.panel === "completeTick"
        ? null
        : "tick",
    );
  el("btnArchive").onclick = () =>
    openPanel(state.panel === "archive" ? null : "archive");
  el("searchInput").oninput = (e) => {
    state.searchQuery = e.target.value;
    renderKanban();
  };
  el("btnExitRo").onclick = resetReadonlyView;

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (document.getElementById("modalEditor")?.firstElementChild) {
        closeModalEditor();
        return;
      }
      if (state.panel === "completeTick") openPanel("tick");
      else closePanel();
      resetReadonlyView();
      return;
    }

    const tag = document.activeElement?.tagName || "";
    const inTyping = ["INPUT", "TEXTAREA"].includes(tag);
    const editorOpen = !!document.getElementById("modalEditor")?.firstElementChild;
    if (inTyping || editorOpen || state.panel === "pat") return;

    switch (e.key) {
      case "n":
        newCard();
        break;
      case "/":
        e.preventDefault();
        el("searchInput").focus();
        break;
      case "t":
        openPanel(
          state.panel === "tick" || state.panel === "completeTick"
            ? null
            : "tick",
        );
        break;
      case "a":
        openPanel(state.panel === "archive" ? null : "archive");
        break;
      default:
    }
  });

  ensureLogin();

  const token = gh.getToken();
  state.ownerRepo = gh.resolveOwnerRepo();
  if (token && state.ownerRepo) {
    try {
      const { data, sha } = await gh.loadBoard(token, state.ownerRepo);
      state.board = data;
      state.sha = sha;
      closePanel();
      renderAll();
      startPolling();
    } catch(e) {
      openPanel("pat");
    }
  }
}

function startPolling() {
  if (state.polling || !state.ownerRepo) return;
  state.polling = true;

  async function poll() {
    try {
      const token = gh.getToken();
      if (!token || !state.sha || !state.ownerRepo) return;
      const r = await gh.pollBoardSha(token, state.ownerRepo, state.sha);
      if (!r) return;
      if (r.changed && r.sha && r.sha !== state.sha)
        reloadBoardQuiet();
    } catch {
      /* noop */
    } finally {
      setTimeout(poll, 30000);
    }
  }

  poll();
}

document.addEventListener("DOMContentLoaded", bootstrap);
