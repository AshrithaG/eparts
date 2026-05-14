## What this is

The Tick Board is a single-page Kanban web app for **Agentic-Augmented Scrum (AAS)**. It tracks **Spec Cards** across six columns (Backlog → Spec Ready → In Build → In Review → Integrated → Demo’d), Validation Hours (VH), Review Tier (T1/T2/T3), tick assignment, and AI-rejection flags. State is stored in **`tick-board/data/board.json`** in this repo so changes are **auditable in git** when synced via the GitHub API.

---

## Live URL

**GitHub’s “Deploy from a branch” only allows `/` or `/docs`**, not arbitrary folders like `/tick-board`. This repo publishes the SPA with **GitHub Actions** instead:

1. In the repo go to **Settings → Pages**.
2. Under **Build and deployment**, set **Source** to **GitHub Actions** (not “Deploy from a branch”).
3. Push or merge commits that touch `tick-board/` or `.github/workflows/tick-board-pages.yml`, or open **Actions** and rerun **Deploy tick board (GitHub Pages)**.

Typical URL (board is served at your project site root):

`https://<your-username>.github.io/eparts/`

(Replace with your GitHub username and repo name.)

**Alternative (no Actions):** copy the static assets (`index.html`, `app.js`, `github-sync.js`, `styles.css`) into `docs/tick-board/` in the repo and set Pages source to **`/docs`**. Keep `tick-board/data/board.json` at repo root for API paths; the UI still talks to GitHub via the API, not that file over HTTP.

---

## How to access (PAT setup)

Persistence uses the GitHub Contents API from the browser. Each teammate needs their own token (stored only in that browser):

1. GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → Generate.
2. **Repository access**: only select this repo (**eparts**, or whatever the team repo is named).
3. **Repository permissions**: **Contents** → **Read and write**.
4. Generate, copy the token (often prefixed `github_pat_`).
5. Open the board URL, click **GitHub sign-in**, paste token, **Save & load**.

**Local/offline preview** (`file://`) does not expose your GitHub Pages domain, so enter **repo owner** and **repo name** in the modal as well.

**Log out** clears the PAT and saved owner/repo override from localStorage.

Never commit a PAT to git. If one is leaked, revoke it immediately on GitHub.

---

## Workflow

- **Board updates** are commits to **`tick-board/data/board.json`** (and **`tick-board/archive/tick-XX.json`** when a tick is archived). Refresh (or polling about every 30s) to pick up teammates’ changes.
- Plan AAS loosely as: Day 0 (Spec Session): create/move cards · Days 1–2: drag across columns · Day 3: **Mark tick complete** (snapshot → archive + retro notes + next tick).
- **Archived ticks**: open **Archive** → **View** for a frozen read-only Kanban (gray header banner).
- **Throughput** header chart: approximate count per tick of cards in Integrated or Demo’d.

---

## Data model

JSON schema (`schemaVersion`, `updatedAt`, `currentTick`, `cards[]`, `ticks[]`, `config`) matches **`TICK_BOARD.md`** in the repo root. Key card fields: `id`, `title`, `intent`, `acceptanceCriteria[]`, `detailedSpec`, `validationHours`, `reviewTier`, `tickId`, `column`, `assignee`, `aiRejected`, timestamps, `definitionOfDone`.

---

## Troubleshooting

| Symptom | Likely cause |
|--------|----------------|
| **401** after save | Bad or expired token; generate a new fine-grained token. |
| **404** on load | Wrong owner/repo, or `tick-board/data/board.json` not on the default branch. |
| **409 / 422** or “SHA conflict” banner | Someone else committed `board.json` first. Use **Reload board** and re-apply your change. |
| Blank board / no cards | Not signed in, or failed fetch; check browser devtools **Network** for `api.github.com`. |
| CORS errors | You should not see CORS on `api.github.com` from a normal browser; ensure you are not blocking requests. |

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `n` | New Spec Card |
| `/` | Focus search |
| `t` | Open/close Tick panel |
| `a` | Open Archive overlay |
| `Esc` | Close modals/panels |

---

## Files

- `index.html` — shell + Tailwind CDN
- `app.js` — UI and workflow
- `github-sync.js` — GitHub REST helpers
- `styles.css` — small layout tweaks
- `data/board.json` — live board JSON (committed)
- `archive/` — tick snapshot JSON files (committed as they’re created)
