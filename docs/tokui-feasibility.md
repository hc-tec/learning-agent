# TokUI Feasibility Assessment

## Purpose

This document evaluates whether
[`jboltai/tokui`](https://github.com/jboltai/tokui) can replace MarkdownFlow as
the AI-generated UI layer for a future AI learning product. The preferred
product UI direction is shadcn/ui, but exact shadcn component equivalence is not
required. The practical target is: TokUI output should visually fit a
shadcn-style application and support fast LLM-generated interactive lessons.

## Repository Snapshot

Research clone:

- Local path: `D:\AIProject\learning-agent\_research\tokui`
- Upstream: `https://github.com/jboltai/tokui`
- Current checked commit during assessment:
  `e698133daab5a2a17ba963c71be0f6170956eea9`
- Commit time: `2026-07-01 07:42:32 +0800`
- Package version in `package.json`: `0.1.3`
- License: MIT
- Runtime model: zero runtime dependencies
- Node engine: `>=20`

Important TokUI files:

- `README_EN.md`
- `demo/TOKUI_DSL_REFERENCE.md`
- `src/core/parser.js`
- `src/core/renderer.js`
- `src/index.js`
- `src/server/tokui-builder.js`
- `packages/react/src/index.js`
- `src/styles/tokui.css`

## What TokUI Is

TokUI is a streaming UI description and rendering framework for AI output. It
uses a compact DSL:

```tokui
[card tt:Title][p Content][/card]
```

The intended data flow is:

```text
Backend or LLM emits TokUI DSL
→ streamed over SSE/WebSocket
→ frontend parser incrementally parses chunks
→ renderer paints real DOM as content arrives
```

This is conceptually better aligned with AI-generated UI than MarkdownFlow
because it treats UI as structured components rather than long markdown-like
content blocks.

## Why TokUI Is Interesting For The New Product

### Streaming-First Rendering

TokUI's parser is a state machine that supports `startStream()`, `feed()`, and
`endStream()`. It can render as chunks arrive, including partial containers and
some progressive table/chart behavior.

This matters for AI learning flows because the learner should see useful UI
appear early rather than waiting for a full lesson artifact to finish.

### Compact DSL

The DSL is significantly shorter than JSX or verbose JSON. This is useful for
LLM output cost and latency.

Example:

```tokui
[card tt:函数入门]
  [p 先观察这个例子：]
  [code lang:python]def add(a, b): return a + b[/code]
  [quiz tt:小测验]
[/card]
```

Compared with MarkdownFlow, TokUI has a more direct component vocabulary:
cards, forms, charts, tabs, callouts, tool calls, sources, artifacts, bubbles,
suggestions, timelines, steps, charts, and more.

### AI-Chat Component Vocabulary

TokUI includes AI-oriented components such as:

- `bubble`
- `think`
- `think-chain`
- `tool-call`
- `source`
- `plan`
- `agent`
- `terminal`
- `artifact`
- `suggestions`
- `chat-input`

This is a good fit for AI learning applications because lessons often need
explanations, questions, references, interactive widgets, and generated
artifacts.

### Theme System

TokUI uses CSS variables and supports themes such as `default`, `dark`,
`modern`, and `modern-dark`. This makes it realistic to create a `shadcn` theme
that maps TokUI visual tokens to shadcn CSS variables.

### Framework Integration

TokUI provides official adapters:

- React: `@jboltai/tokui-react`
- Vue: `@jboltai/tokui-vue`
- Svelte: `@jboltai/tokui-svelte`
- Web Component: `@jboltai/tokui-webc`

For a new Next.js/shadcn project, the React adapter is enough for initial
embedding.

## shadcn/ui Compatibility

### Summary

TokUI can fit visually into a shadcn-style application, but it is not a native
shadcn renderer.

The recommended approach is:

- Use shadcn/ui for the app shell, routes, layout, navigation, dialogs, fixed
  forms, and teacher/admin surfaces.
- Use TokUI for AI-generated lesson content and dynamic interaction blocks.
- Add a custom TokUI theme that maps TokUI variables to shadcn variables.
- Later, if needed, build a shadcn-native renderer for the core lesson
  components.

### What Works Well

TokUI and shadcn can coexist because:

- TokUI can be mounted inside a React component.
- TokUI import is SSR-friendly; rendering happens client-side.
- TokUI uses CSS variables, while shadcn also relies on CSS variables.
- TokUI's output can be scoped inside an AI lesson panel.
- The surrounding product can remain fully shadcn.

### What Does Not Work Natively

TokUI renders DOM directly through `document.createElement`. It does not emit
React elements and does not call local shadcn components.

For example:

```tokui
[btn tx:继续 v:primary]
```

renders as TokUI's own button DOM, not as:

```tsx
<Button>继续</Button>
```

So TokUI should not be treated as a drop-in shadcn component generator.

### Practical Theme Mapping

A custom theme can make TokUI visually close to shadcn:

```css
[data-tokui-theme="shadcn"] {
  --tokui-bg: hsl(var(--card));
  --tokui-text: hsl(var(--card-foreground));
  --tokui-text-muted: hsl(var(--muted-foreground));
  --tokui-border: hsl(var(--border));
  --tokui-stripe: hsl(var(--muted));
  --tokui-primary: hsl(var(--primary));
  --tokui-danger: hsl(var(--destructive));
  --tokui-success: hsl(var(--chart-2));
  --tokui-warning: hsl(var(--chart-4));
  --tokui-radius: var(--radius);
  --tokui-control-radius: calc(var(--radius) - 2px);
}
```

This is likely good enough for the first product version, especially if TokUI is
used inside a bounded lesson/chat surface.

### Recommended Integration Level

Use TokUI at "theme-compatible embedded surface" level first.

Do not immediately build a full shadcn-native renderer. First prove that:

1. LLMs can reliably generate useful TokUI DSL.
2. TokUI streaming improves perceived latency.
3. The generated UI can support learning interactions better than MarkdownFlow.
4. TokUI can be made visually acceptable inside a shadcn app.

After that, decide whether to:

- keep TokUI as the embedded generated-content renderer, or
- build a custom AST-to-shadcn renderer for the final product.

## UI Adaptation Assessment

### Strengths

- Good built-in component breadth.
- Built-in themes and CSS variable architecture.
- Responsive layout exists for row/col grids.
- AI-chat components are already aligned with agentic interfaces.
- Built-in chart support is useful for generated educational explanations.
- Error boundaries and unknown component fallback reduce rendering blast radius.
- Event handlers use named references instead of inline executable code.

### Concerns

- TokUI's visual language is its own. It will require CSS work to feel shadcn.
- Some components use fixed CSS assumptions and may not perfectly match shadcn
  density, radius, focus rings, or spacing.
- It is DOM-imperative, so deep React/shadcn integration requires extra work.
- It has a large component surface. LLM output should be constrained to a
  product-approved subset rather than exposing every tag.
- Some DSL parsing rules need careful prompting. For example, values with
  spaces or punctuation often need quotes, and colon syntax can be misread as
  attributes.
- Mobile UX must be verified with real screenshots, especially charts, tables,
  canvas/artifact panels, forms, and sidebars.

## Testing Result

The upstream `npm test` script uses POSIX shell syntax:

```bash
for f in tests/test-*.js; do node "$f" || exit 1; done
```

This fails under Windows PowerShell with:

```text
f was unexpected at this time.
```

Running the same test files with a PowerShell loop succeeds:

```powershell
Get-ChildItem tests -Filter test-*.js | ForEach-Object {
  node $_.FullName
  if ($LASTEXITCODE -ne 0) { throw "Failed $($_.Name)" }
}
```

Observed result:

- Test files: `34`
- Exit code: `0`
- Output shows all executed tests passing.

This suggests the library has meaningful test coverage, but the package script
is not Windows-friendly.

## Security Notes

TokUI's security model is better than rendering arbitrary HTML:

- Events are named references (`clk`, `sub`) that must be registered.
- `el()` filters dangerous attributes such as `on*` and `formaction`.
- Most content is rendered through `textContent`.
- Parser has `maxBuffer` and `maxDepth`.
- Renderer has depth limits and component error fallback.

Remaining cautions:

- Treat LLM-generated DSL as semi-trusted, not fully trusted.
- Register only safe event handlers.
- Do not let generated UI invoke sensitive actions without explicit user
  confirmation.
- Audit markdown/code/sandbox/artifact behavior before exposing untrusted user
  content.

## DeepSeek API Speed Benchmark Plan

### Prompting Status

TokUI currently does not ship an internal LLM system prompt or official skill.
The upstream issue discussion confirms the expected integration path: put the
TokUI DSL writing rules into a system prompt and send that prompt to the LLM
API.

A reusable local prompting guide has been added:

- `docs/tokui-prompting-guide.md`

This guide includes a base system prompt plus prompt cases for forms, reports,
ordinary tutor conversation, and lesson steps.

### Current Status

The `.env` file now provides `DEEPSEEK_API_KEY`, so real DeepSeek streaming
benchmarks have been executed. Secrets were not printed.

### Official API Notes

DeepSeek's official documentation states that the API is compatible with the
OpenAI API format. For OpenAI-compatible calls:

- Base URL: `https://api.deepseek.com`
- Auth: bearer API key
- Current model options listed by the docs include:
  - `deepseek-v4-flash`
  - `deepseek-v4-pro`
  - `deepseek-chat` and `deepseek-reasoner` are listed as being deprecated on
    `2026-07-24`

For TokUI generation speed tests, start with `deepseek-v4-flash` and disable
thinking mode when possible. For lesson-planning quality tests, compare with
`deepseek-v4-pro`.

Sources:

- https://api-docs.deepseek.com/
- https://api-docs.deepseek.com/api/create-chat-completion
- https://api-docs.deepseek.com/guides/thinking_mode

### What To Measure

For each prompt:

- Time to first byte.
- Time to first non-empty content delta.
- Time to first valid TokUI tag.
- Total generation time.
- Output character count.
- Approximate character throughput.
- Whether output is valid/usable TokUI DSL.
- Whether the UI renders without unknown/error components.

### Suggested Prompt Classes

Use at least these prompt classes:

1. Short explanation card.
2. Interactive quiz card.
3. Multi-step lesson with tabs/steps/callouts.
4. Data explanation with chart/table.
5. AI tutor conversation with quick replies and sources.

### Benchmark Script

A reproducible script has been added:

- `scripts/benchmark_tokui_deepseek.py`
- `scripts/validate_tokui_outputs.mjs`

Run from repository root:

```powershell
$env:DEEPSEEK_API_KEY="sk-..."
python scripts\benchmark_tokui_deepseek.py
```

Optional parameters:

```powershell
python scripts\benchmark_tokui_deepseek.py `
  --model deepseek-v4-flash `
  --runs 3 `
  --out docs\generated\tokui-deepseek-benchmark.json
```

Validate generated DSL with the upstream TokUI parser:

```powershell
node scripts\validate_tokui_outputs.mjs `
  docs\generated\tokui-deepseek-benchmark-prompt-v5.json
```

### Observed DeepSeek Result

The latest prompt v5 benchmark used `deepseek-v4-flash` against five learning
scenarios: short card, quiz card, lesson steps, data chart, and tutor bubble.

Result summary:

- Total runs: `5`
- Successful runs: `5`
- Average TTFB: about `209 ms`
- Average first content/tag: about `668 ms`
- Average total generation time: about `2108 ms`
- Average throughput: about `213 chars/sec`
- Markdown code fence runs: `0`
- Unbalanced bracket runs: `0`
- Equals attribute runs: `0`
- HTML table tag runs: `0`
- Invalid leaf closing runs: `0`
- Parser validation: `5/5` passed

Output file:

- `docs/generated/tokui-deepseek-benchmark-prompt-v5.json`

Earlier prompts were fast but exposed correctness problems: HTML-ish
attributes, invalid table tags, square brackets in normal text, and incorrect
`[/step]` closures. The current prompt fixed the observed cases by restricting
component usage and copying canonical shapes from TokUI's builder/docs.

## Recommendation

Proceed with TokUI as the first replacement candidate for MarkdownFlow.

The recommended product direction is:

1. Build the new app shell with shadcn/ui.
2. Embed TokUI as the generated lesson UI surface.
3. Add a shadcn-like TokUI theme.
4. Restrict the allowed TokUI component subset for learning scenarios.
5. Benchmark DeepSeek generation speed and output correctness.
6. Validate mobile and desktop rendering with screenshots.
7. Decide later whether to keep TokUI's DOM renderer or build a
   shadcn-native renderer.

TokUI is not perfect, but it is much closer to the desired "AI generates
interactive UI" direction than MarkdownFlow.
