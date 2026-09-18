// Client-side mirror of backend/app/services/repository_parser.py. The backend remains the
// authority; this gives instant feedback and builds shareable /analyze/{owner}/{repo} URLs.

export type RepoParseResult =
  | { ok: true; owner: string; name: string }
  | { ok: false; error: string };

const MAX_INPUT_LENGTH = 512;
const OWNER_RE = /^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$/;
const REPO_RE = /^[A-Za-z0-9._-]{1,100}$/;
const SSH_RE = /^git@github\.com:(.+)$/i;
const ALLOWED_HOSTS = new Set(["github.com", "www.github.com"]);
const RESERVED_OWNERS = new Set([
  "about", "apps", "collections", "contact", "customer-stories", "enterprise", "explore",
  "features", "issues", "login", "marketplace", "new", "notifications", "orgs", "pricing",
  "pulls", "search", "settings", "sponsors", "topics", "trending", "join", "site",
]);

export function parseRepoInput(raw: string): RepoParseResult {
  const value = raw.trim();
  if (!value) return { ok: false, error: "Enter a GitHub repository URL." };
  if (value.length > MAX_INPUT_LENGTH) return { ok: false, error: "Repository URL is too long." };
  if (/[\s\x00-\x1f]/.test(value)) {
    return { ok: false, error: "Repository URL must not contain whitespace." };
  }

  let path: string;
  const ssh = SSH_RE.exec(value);
  if (ssh) {
    path = ssh[1];
  } else if (value.includes("://") || /^(www\.)?github\.com\//i.test(value)) {
    let url: URL;
    try {
      url = new URL(value.includes("://") ? value : `https://${value}`);
    } catch {
      return { ok: false, error: "That doesn't look like a valid URL." };
    }
    if (url.protocol !== "https:" && url.protocol !== "http:") {
      return { ok: false, error: "Only http(s) GitHub URLs are supported." };
    }
    if (!ALLOWED_HOSTS.has(url.hostname.toLowerCase())) {
      return { ok: false, error: "Only github.com repositories are supported." };
    }
    if (url.username || url.password || url.port) {
      return { ok: false, error: "Repository URL must not contain credentials or a port." };
    }
    path = url.pathname;
  } else {
    path = value; // shorthand owner/repo
  }

  const segments = path.split("/").filter(Boolean);
  if (segments.length < 2) {
    return { ok: false, error: "Use a repository URL such as https://github.com/owner/repository." };
  }
  const owner = segments[0];
  let name = segments[1];
  if (name.toLowerCase().endsWith(".git")) name = name.slice(0, -4);

  if (RESERVED_OWNERS.has(owner.toLowerCase()) || !OWNER_RE.test(owner)) {
    return { ok: false, error: `"${owner.slice(0, 50)}" is not a valid GitHub owner name.` };
  }
  if (!REPO_RE.test(name) || name === "." || name === "..") {
    return { ok: false, error: `"${name.slice(0, 100)}" is not a valid repository name.` };
  }
  return { ok: true, owner, name };
}

export function analyzePath(owner: string, name: string): string {
  return `/analyze/${encodeURIComponent(owner)}/${encodeURIComponent(name)}`;
}
