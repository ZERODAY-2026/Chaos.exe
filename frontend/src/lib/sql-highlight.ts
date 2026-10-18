/** Tiny dependency-free SQL tokenizer for syntax highlighting. Display only, never parses for execution. */

export type SqlToken = { type: "keyword" | "function" | "string" | "number" | "comment" | "identifier" | "operator" | "space"; text: string };

const KEYWORDS = new Set(
  (
    "select from where group by order having limit offset join inner left right full outer cross on as and or not in is null " +
    "like ilike between case when then else end distinct union all intersect except with asc desc nulls first last over partition " +
    "rows range qualify true false interval cast try_cast exists any some using natural lateral top fetch next only window filter"
  ).split(" "),
);

const FUNCTIONS = new Set(
  (
    "count sum avg min max round floor ceil abs coalesce nullif date_trunc date_part extract year month day quarter week " +
    "to_date to_char to_varchar lower upper trim length substr substring concat iff ifnull row_number rank dense_rank lag lead " +
    "median stddev variance listagg string_agg any_value approx_count_distinct datediff dateadd current_date current_timestamp"
  ).split(" "),
);

const TOKEN_RE =
  /(--[^\n]*|\/\*[\s\S]*?\*\/)|('(?:[^']|'')*')|("(?:[^"]|"")*")|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_$]*)|(\s+)|([<>=!]=?|<>|\|\||::|[-+*/%,.;()])|(.)/g;

export function tokenizeSql(sql: string): SqlToken[] {
  const tokens: SqlToken[] = [];
  for (const m of sql.matchAll(TOKEN_RE)) {
    const [text, comment, str, quotedIdent, num, word, space, op] = m;
    if (comment) tokens.push({ type: "comment", text });
    else if (str) tokens.push({ type: "string", text });
    else if (quotedIdent) tokens.push({ type: "identifier", text });
    else if (num) tokens.push({ type: "number", text });
    else if (word) {
      const lower = word.toLowerCase();
      const next = sql.slice((m.index ?? 0) + word.length).match(/^\s*\(/);
      if (FUNCTIONS.has(lower) && next) tokens.push({ type: "function", text });
      else if (KEYWORDS.has(lower)) tokens.push({ type: "keyword", text });
      else tokens.push({ type: "identifier", text });
    } else if (space) tokens.push({ type: "space", text });
    else if (op) tokens.push({ type: "operator", text });
    else tokens.push({ type: "identifier", text });
  }
  return tokens;
}
