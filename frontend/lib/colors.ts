// Colors for common languages (matching the colors developers know from GitHub), with a
// deterministic fallback so every other language always gets the same color.
const KNOWN: Record<string, string> = {
  TypeScript: "#3178c6", JavaScript: "#f1e05a", Python: "#3572A5", Go: "#00ADD8",
  Rust: "#dea584", Java: "#b07219", Kotlin: "#A97BFF", "C#": "#178600", "C++": "#f34b7d",
  C: "#555555", Ruby: "#701516", PHP: "#4F5D95", Swift: "#F05138", Dart: "#00B4AB",
  Scala: "#c22d40", Shell: "#89e051", HTML: "#e34c26", CSS: "#563d7c", SCSS: "#c6538c",
  Vue: "#41b883", Svelte: "#ff3e00", Markdown: "#083fa1", MDX: "#fcb32c", JSON: "#8a8a8a",
  YAML: "#cb171e", TOML: "#9c4221", Dockerfile: "#384d54", Makefile: "#427819",
  "Jupyter Notebook": "#DA5B0B", Lua: "#000080", Elixir: "#6e4a7e", Haskell: "#5e5086",
  HCL: "#844FBA", SQL: "#e38c00", "Objective-C": "#438eff", R: "#198CE7", Julia: "#a270ba",
  Zig: "#ec915c", reStructuredText: "#141414", Perl: "#0298c3", Groovy: "#4298b8",
};
const FALLBACK = ["#6366f1", "#14b8a6", "#f59e0b", "#ec4899", "#84cc16", "#06b6d4", "#a855f7",
  "#ef4444", "#22c55e", "#eab308"];

export function languageColor(language: string): string {
  if (KNOWN[language]) return KNOWN[language];
  let hash = 0;
  for (const ch of language) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return FALLBACK[hash % FALLBACK.length];
}

export const CATEGORY_COLORS: Record<string, string> = {
  source: "#3b82f6", test: "#22c55e", documentation: "#a855f7", config: "#f59e0b",
  data: "#06b6d4", asset: "#ec4899", binary: "#71717a", lockfile: "#a1a1aa",
  generated: "#d4d4d8", other: "#94a3b8",
};
