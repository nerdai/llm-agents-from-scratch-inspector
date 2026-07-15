import { createHighlighterCore, type HighlighterCore } from 'shiki/core'
import { createJavaScriptRegexEngine } from 'shiki/engine/javascript'
import githubLight from 'shiki/themes/github-light.mjs'

/**
 * Prompt templates and rollout dumps aren't any specific programming
 * language (they're `{placeholder}`-style text), so this deliberately
 * doesn't attempt language detection -- Shiki's plaintext lexer needs
 * no grammar at all, just a theme for consistent, legible monospace
 * rendering inside the templates/rollout drawers (#23).
 *
 * Built on Shiki's fine-grained core bundle (rather than the
 * top-level `shiki` package) with zero `langs` and the pure-JS regex
 * engine (no WASM): the top-level package's `codeToHtml` dynamically
 * imports from its full `bundledLanguages`/`bundledThemes` maps, which
 * pulls every language's grammar (100+ chunks) into the Vite build
 * even though only `text` is ever requested here.
 */
const THEME = 'github-light'
const LANG = 'text'

let highlighterPromise: Promise<HighlighterCore> | null = null

function highlighter() {
  highlighterPromise ??= createHighlighterCore({
    themes: [githubLight],
    langs: [],
    engine: createJavaScriptRegexEngine(),
  })
  return highlighterPromise
}

/** Renders `code` to a self-contained, pre-styled HTML string. */
export async function highlightText(code: string): Promise<string> {
  const hl = await highlighter()
  return hl.codeToHtml(code, { lang: LANG, theme: THEME })
}
