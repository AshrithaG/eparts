/**
 * GitHub Contents API persistence for Tick Board.
 * Paths are relative to repo root (tick-board/data/board.json).
 */

export const STORAGE_KEY_PAT = "gh_pat";
export const STORAGE_KEY_OWNER = "gh_repo_owner";
export const STORAGE_KEY_REPO = "gh_repo_name";

export const BOARD_PATH = "tick-board/data/board.json";
export const ARCHIVE_PREFIX = "tick-board/archive/";

const API_ROOT = "https://api.github.com";

/** Encode repo-relative path segments for Contents API URLs */
export function encodeRepoPath(repoRelativePath) {
  return repoRelativePath
    .split("/")
    .filter(Boolean)
    .map((p) => encodeURIComponent(p))
    .join("/");
}

function headers(token) {
  return {
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    Authorization: `Bearer ${token}`,
  };
}

function utf8ToBase64(str) {
  return btoa(unescape(encodeURIComponent(str)));
}

function base64ToUtf8(b64) {
  return decodeURIComponent(escape(atob(b64)));
}

/** Infer owner/repo when served from PROJECT.github.io/REPO/... */
export function inferGitHubRepo() {
  const { hostname, pathname } = window.location;
  if (!hostname.endsWith(".github.io")) return null;
  const owner = hostname.replace(".github.io", "");
  const segments = pathname.split("/").filter(Boolean);
  const repo = segments[0];
  if (repo && !["assets", "static"].includes(repo)) return { owner, repo };
  return null;
}

export function getSavedRepoOverrides() {
  const owner = localStorage.getItem(STORAGE_KEY_OWNER);
  const repo = localStorage.getItem(STORAGE_KEY_REPO);
  if (owner && repo) return { owner, repo };
  return null;
}

export function setSavedRepoOverrides(owner, repo) {
  if (owner) localStorage.setItem(STORAGE_KEY_OWNER, owner.trim());
  else localStorage.removeItem(STORAGE_KEY_OWNER);
  if (repo) localStorage.setItem(STORAGE_KEY_REPO, repo.trim());
  else localStorage.removeItem(STORAGE_KEY_REPO);
}

export function resolveOwnerRepo() {
  return inferGitHubRepo() || getSavedRepoOverrides();
}

export function getToken() {
  return localStorage.getItem(STORAGE_KEY_PAT);
}

export function setToken(token) {
  if (token && token.trim()) localStorage.setItem(STORAGE_KEY_PAT, token.trim());
  else localStorage.removeItem(STORAGE_KEY_PAT);
}

async function ghFetch(path, token, opts = {}) {
  const res = await fetch(`${API_ROOT}${path}`, {
    ...opts,
    headers: { ...headers(token), ...(opts.headers || {}) },
  });
  return res;
}

/**
 * GET file contents + SHA
 * @returns {{ data: object, sha: string, raw: object } | null}
 */
export async function loadBoard(token, ownerRepo) {
  const { owner, repo } = ownerRepo;
  const path = `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(
    repo,
  )}/contents/${encodeRepoPath(BOARD_PATH)}`;
  const res = await ghFetch(path, token, { method: "GET" });
  if (res.status === 404) {
    throw new Error(
      "board.json not found. Ensure path tick-board/data/board.json exists on the default branch.",
    );
  }
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`GitHub GET failed (${res.status}): ${err}`);
  }
  const raw = await res.json();
  if (!raw.content) throw new Error("Unexpected response: missing content");
  const text = base64ToUtf8(raw.content.replace(/\n/g, ""));
  const data = JSON.parse(text);
  return { data, sha: raw.sha, raw };
}

/**
 * PUT board.json update
 */
export async function saveBoard(boardData, message, sha, token, ownerRepo) {
  const { owner, repo } = ownerRepo;
  boardData.updatedAt = new Date().toISOString();
  const body = JSON.stringify(boardData);
  const path = `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(
    repo,
  )}/contents/${encodeRepoPath(BOARD_PATH)}`;
  const payload = {
    message: message || "chore(board): update",
    content: utf8ToBase64(body),
    sha,
  };
  const res = await ghFetch(path, token, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  if (res.status === 409 || res.status === 422) {
    const err = new Error("SHA_CONFLICT");
    err.code = res.status;
    throw err;
  }
  if (!res.ok) {
    const txt = await res.text();
    const err = new Error(`GitHub PUT failed (${res.status}): ${txt}`);
    err.status = res.status;
    throw err;
  }
  const out = await res.json();
  return out?.content?.sha || out?.commit?.sha || sha;
}

/**
 * Create or update arbitrary path (new file omit sha).
 */
export async function putFile(
  pathInRepo,
  contentStr,
  message,
  token,
  ownerRepo,
  shaOptional,
) {
  const { owner, repo } = ownerRepo;
  const path = `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(
    repo,
  )}/contents/${encodeRepoPath(pathInRepo)}`;
  const payload = {
    message,
    content: utf8ToBase64(contentStr),
  };
  if (shaOptional) payload.sha = shaOptional;

  const res = await ghFetch(path, token, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`GitHub PUT ${pathInRepo} failed (${res.status}): ${txt}`);
  }
  return res.json();
}

/** Fetch raw file SHA + content without parsing as board */
export async function fetchRepoFile(token, ownerRepo, pathInRepo) {
  const { owner, repo } = ownerRepo;
  const path = `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(
    repo,
  )}/contents/${encodeRepoPath(pathInRepo)}`;
  const res = await ghFetch(path, token, { method: "GET" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`GET ${pathInRepo} ${res.status}`);
  const raw = await res.json();
  const text = base64ToUtf8(raw.content.replace(/\n/g, ""));
  let data = null;
  try {
    data = JSON.parse(text);
  } catch {
    data = text;
  }
  return { data, sha: raw.sha };
}

/**
 * Create archive snapshot (new file — no SHA)
 */
export async function archiveTickFile(
  archiveRelativePath,
  snapshotData,
  message,
  token,
  ownerRepo,
) {
  const json = JSON.stringify(snapshotData, null, 2);
  return putFile(
    archiveRelativePath,
    json,
    message,
    token,
    ownerRepo,
    null,
  );
}

/** Poll SHA for BOARD_PATH — pass current SHA string */
export async function pollBoardSha(token, ownerRepo, knownSha) {
  const { owner, repo } = ownerRepo;
  const path = `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(
    repo,
  )}/contents/${encodeRepoPath(BOARD_PATH)}`;
  const res = await ghFetch(path, token, {
    method: "GET",
  });
  if (!res.ok) return null;
  const raw = await res.json();
  if (knownSha && raw.sha !== knownSha) return { changed: true, sha: raw.sha };
  return { changed: false, sha: raw.sha };
}
