# AI-Shifu Project Research Assessment

## Purpose

This document records a first-pass research assessment of the current
AI-Shifu project. It summarizes what the project does, where its strongest
engineering and product ideas are, what limitations are visible from the
repository, and whether future work should continue inside this codebase or
start from a new project.

## Executive Summary

AI-Shifu is a full-stack AI teaching platform rather than a simple chatbot
demo. It attempts to turn creator-provided course structure and teaching intent
into interactive one-on-one learning experiences. The system covers course
authoring, AI-led learner chat, lesson execution, admin/operator tools,
payments, credit metering, promotions, referral flows, TTS, i18n, observability,
and a relatively mature development harness.

The project is valuable as a reference because it shows how an AI education
product can be engineered beyond the prompt layer. It contains practical
answers to questions such as how to publish AI courses, how to meter LLM usage,
how to connect learner flows with billing, how to trace runtime failures, and
how to keep a complex AI application maintainable with documentation and tests.

However, it also carries significant constraints. The frontend experience and
authoring model are not necessarily aligned with modern AI-to-UI or generative
course-building expectations. The MarkdownFlow-based content authoring path may
feel rigid compared with newer A2UI-style frameworks. The personalization model
appears to be more of a product and prompt orchestration layer than a deeply
validated learner modeling system. The codebase also contains substantial
legacy compatibility surfaces and architectural debt.

If the goal is to build a substantially different next-generation AI learning
product, especially one with a different UI philosophy and a different content
generation/runtime model, the recommended path is to start a new project and
reuse selected ideas or modules from this repository. If the goal is to operate
or incrementally improve AI-Shifu itself, continuing in this codebase is
reasonable, but it should be treated as a refactoring and product renovation
effort rather than a greenfield innovation path.

## What The Project Does

### AI Teaching Agent Platform

AI-Shifu is positioned as a scalable one-on-one teaching agent for creators,
teachers, instructors, training teams, and education organizations. The core
idea is that a teacher provides expertise, course structure, and teaching
intent once, and the system delivers personalized learning interactions to many
learners.

The learner experience is AI-led rather than purely user-led. Users can ask
questions and interact, but the system is designed to preserve the teaching
flow and narrative progression.

Important references:

- `README.md`
- `ARCHITECTURE.md`
- `docs/engineering-baseline.md`

### Course Creation And Publishing

The backend `shifu` service manages course-like teaching agents. It supports
drafts, published versions, outline trees, MarkdownFlow content, preview flows,
permissions, import/export, course history, and publishing behavior.

Important backend areas:

- `src/api/flaskr/service/shifu/route.py`
- `src/api/flaskr/service/shifu/shifu_draft_funcs.py`
- `src/api/flaskr/service/shifu/shifu_publish_funcs.py`
- `src/api/flaskr/service/shifu/shifu_mdflow_funcs.py`

Important frontend areas:

- `src/cook-web/src/app/shifu`
- `src/cook-web/src/app/admin`

### Learner Runtime

The `learn` service runs the learner-facing teaching experience. It loads course
information and outline trees, runs MarkdownFlow/lesson scripts, handles user
input, streams generated content, supports listen-mode elements, and records
lesson feedback.

Important backend areas:

- `src/api/flaskr/service/learn/routes.py`
- `src/api/flaskr/service/learn/runscript_v2.py`
- `src/api/flaskr/service/learn/context_v2.py`
- `src/api/flaskr/service/learn/handle_input_ask.py`

Important frontend area:

- `src/cook-web/src/app/c/[[...id]]`

### LLM Integration

Server-side LLM calls are routed through a central LiteLLM integration. The
system includes provider configuration, model aliases, allowed model handling,
usage extraction, Langfuse tracing, output excerpts for operator summaries, and
connections to metering and billing.

Important backend area:

- `src/api/flaskr/api/llm/__init__.py`

### Commercial And Operational Platform Features

The repository contains substantial non-learning product infrastructure:

- Creator billing and credit usage
- Legacy learner orders
- Payment integrations
- Promotions and coupons
- Referral campaigns
- Operator user management
- Course analytics
- Credit notifications
- Voice clone operations

Important backend areas:

- `src/api/flaskr/service/billing`
- `src/api/flaskr/service/order`
- `src/api/flaskr/service/metering`
- `src/api/flaskr/service/promo`
- `src/api/flaskr/service/referral`
- `src/api/flaskr/service/creator_analytics`

Important frontend areas:

- `src/cook-web/src/app/admin/dashboard`
- `src/cook-web/src/app/admin/operations`
- `src/cook-web/src/app/admin/orders`

### Engineering Governance

The project includes an unusually explicit engineering governance layer. It has
architecture maps, engineering baselines, design docs, product specs, ExecPlans,
generated knowledge indexes, architecture boundary checks, browser smoke tests,
request-id diagnostics, and a local observability stack.

Important references:

- `ARCHITECTURE.md`
- `docs/engineering-baseline.md`
- `docs/RELIABILITY.md`
- `docs/QUALITY_SCORE.md`
- `docs/references/architecture-boundaries.md`
- `docs/generated/harness-health.md`

## Strengths

### Complete Product Loop

The project connects authoring, publishing, learning, feedback, operations,
billing, and analytics. This makes it more useful as a real AI product reference
than a simple LLM demo.

### Structured AI Teaching Flow

The system does not rely only on open-ended chat. It uses course outlines,
MarkdownFlow content, lesson runtime state, and script execution to keep the AI
interaction attached to a planned learning path.

### Centralized LLM Infrastructure

LLM calls are not scattered randomly through the codebase. They are wrapped
through a shared integration layer with provider configuration, model aliases,
usage tracking, and observability.

### Operational Maturity

The repository has real operational concerns: payments, credits, admin tools,
custom domains, user roles, observability, migration management, and smoke
diagnostics.

### Agent-Friendly Development Model

The documentation and harness design make the project relatively friendly to AI
coding agents. The repository tries to make architectural knowledge explicit
instead of relying only on chat history or tribal knowledge.

## Limitations

### Authoring Experience May Be Outdated

MarkdownFlow provides a structured authoring mechanism, but it may not match
the quality or flexibility expected from newer AI-to-UI or A2UI frameworks. If
the desired product direction is dynamic, generative, component-rich learning
interfaces, then MarkdownFlow may become a constraint instead of an advantage.

Research questions:

- Can MarkdownFlow express modern interactive learning widgets cleanly?
- How hard is it to generate, inspect, edit, and version MarkdownFlow content?
- Does the authoring experience feel natural to teachers?
- Can it support rich adaptive UI without excessive custom block logic?

### Frontend Product Experience Needs Rethinking

The frontend has many routes and components, including maintained legacy
compatibility surfaces. If the current page design, learner experience, and
creator tools are not satisfying, incremental edits may be slower than designing
a new interaction model from scratch.

Visible concerns:

- Legacy `c-*` paths are still active.
- Learner and admin UI responsibilities are broad.
- Product flows have grown around historical compatibility.
- A new UI philosophy may fight the current structure.

### Personalization May Not Be Deep Enough

The product claims personalized teaching based on learner profiles and context.
However, a rigorous adaptive learning system usually needs more than profile
fields and prompt adaptation. It may need learner state modeling, mastery
estimation, misconception detection, targeted practice generation, learning
objective tracking, and measurable learning outcomes.

Research questions:

- What exactly is stored as the learner model?
- How does learner state change over time?
- How does the AI decide the next teaching strategy?
- Is there a measurable mastery model?
- Are learning gains evaluated independently from user satisfaction?

### Knowledge Base Capability Is Not Yet Mature

The public roadmap still lists knowledge base work. For an AI teaching platform,
retrieval, citation, source management, and knowledge update workflows are
central capabilities. Without a mature knowledge base, the system risks relying
too heavily on prompt context and model prior knowledge.

Research questions:

- Can courses ground answers in uploaded materials?
- Can answers cite sources?
- How are course documents chunked, indexed, and updated?
- How is hallucination reduced?
- Can teachers inspect and correct the knowledge base?

### Evaluation System Is Limited

The project includes feedback and analytics, but that is not the same as a
complete teaching quality evaluation system. A mature AI tutor should evaluate
answer correctness, pedagogical quality, alignment with learning objectives,
student mastery, and long-term learning outcomes.

Research questions:

- Are there automated rubrics for AI teaching quality?
- Are generated explanations checked against source materials?
- Are quizzes and assessments tied to explicit learning objectives?
- Can teachers audit AI behavior at scale?
- Is there an offline evaluation set for regression testing?

### Legacy And Architecture Debt

The repository explicitly tracks legacy compatibility and architecture boundary
debt. The generated harness report lists many baseline entries for backend
cross-service imports. The docs also note legacy route groups, legacy payment
flows, migration repair paths, and active compatibility surfaces.

Important references:

- `docs/exec-plans/tech-debt-tracker.md`
- `docs/references/architecture-boundaries.md`
- `docs/generated/harness-health.md`

This does not make the project bad. It means the project has lived through real
product evolution. But it increases the cost of using it as the foundation for a
new product direction.

### E2E Coverage Is Narrow

The Playwright smoke suite currently focuses on a small number of baseline
paths: login/admin loading and learner chat shell rendering. This is useful but
not full regression coverage for payments, publishing, long-running lesson
flows, TTS, permissions, or complex admin operations.

Important reference:

- `src/cook-web/e2e/smoke.spec.ts`

### Local Development Stack Is Heavy

The Docker development stack includes API, web, MySQL, Redis, Celery, Nginx,
Grafana, Loki, Tempo, Prometheus, Promtail, and OTEL Collector. This is powerful
for debugging but heavy for fast product exploration.

Important reference:

- `docker/docker-compose.dev.yml`

## Build On This Project Or Start A New One?

### Recommendation

For a substantially redesigned AI learning product, start a new project.

Keep AI-Shifu as a reference implementation and selectively reuse ideas,
schemas, tests, prompts, provider abstractions, or operational patterns. Do not
make it the main codebase unless the intended product remains close to
AI-Shifu's current assumptions: MarkdownFlow-centered authoring, existing
learner chat flow, existing admin model, and existing billing/operator
architecture.

### Why A New Project Is Likely Better

Start a new project if the new direction requires:

- A different learner experience and visual design.
- A modern A2UI or component-generation framework instead of MarkdownFlow.
- A new course authoring model.
- A different personalization architecture.
- A simpler backend domain model.
- A cleaner data model without legacy payment/order compatibility.
- Faster iteration on product experience.
- Research flexibility before production hardening.

The current project already has strong assumptions embedded across backend
services, frontend routes, tests, docs, billing, and compatibility paths. If the
core product philosophy changes, refactoring this repository may require
fighting many existing decisions.

### Why Not Discard It Completely

Starting a new project does not mean ignoring AI-Shifu. The current repository
contains valuable lessons:

- How to structure an AI teaching runtime.
- How to publish and preview AI courses.
- How to wrap LLM providers.
- How to meter LLM usage.
- How to connect AI usage with billing.
- How to trace request failures.
- How to organize tests and engineering docs.
- Which legacy decisions become costly over time.

A good strategy is to treat AI-Shifu as a reference and extraction source, not
as the new product's foundation.

### When Continuing In This Codebase Makes Sense

Continue inside AI-Shifu if the goal is:

- To operate or improve the existing AI-Shifu product.
- To add one or two features while preserving the current product model.
- To study production-grade AI education platform engineering.
- To improve reliability, observability, tests, or documentation.
- To incrementally modernize the existing UI without changing the core runtime.

In this case, the work should be framed as renovation. The main roadmap would
be: reduce legacy boundary debt, modernize authoring UI, expand E2E coverage,
improve knowledge base support, and strengthen personalization/evaluation.

## Suggested New Project Strategy

### Keep The New Project Small At First

The new project should begin as a focused research and product prototype, not a
full clone of AI-Shifu. Start with only the core loop:

1. Teacher creates or imports teaching material.
2. System generates an interactive lesson UI.
3. Learner studies through AI-guided interaction.
4. System records learner state and evidence.
5. Teacher can inspect, edit, and improve the result.

Avoid adding payments, large operator tools, promotions, referrals, and complex
admin systems until the core learning experience is clearly better.

### Rebuild The Authoring Model

Instead of treating MarkdownFlow as the central source of truth, evaluate a
newer content/runtime model:

- Structured lesson graph.
- Typed learning blocks.
- A2UI-generated components.
- Teacher-editable generated UI.
- Source-grounded knowledge objects.
- Versioned lesson plans.
- Explicit learning objectives and assessments.

Markdown can still be supported as an import/export format, but it should not
necessarily be the internal runtime model.

### Design Personalization From First Principles

The new system should define personalization explicitly:

- Learner profile: stable background and goals.
- Learner state: changing mastery, confusion, interests, pace.
- Evidence: answers, attempts, time, hints, reflections.
- Strategy: explain, quiz, remediate, analogize, summarize, challenge.
- Outcome: measurable progress against objectives.

This makes personalization inspectable instead of hidden inside prompts.

### Build A Modern Evaluation Loop

The new project should include evaluation early:

- Offline test courses.
- Golden learner scenarios.
- Rubrics for explanation quality.
- Source-grounding checks.
- Hallucination checks.
- Learning objective coverage.
- Teacher review workflow.

This is especially important if the research goal is to prove that the AI tutor
is better than a generic chatbot.

### Reuse Selectively From AI-Shifu

Potentially reusable ideas:

- Central LLM provider abstraction.
- Request tracing and harness ideas.
- Metering concepts.
- Course publish/preview distinction.
- i18n organization.
- Docker deployment lessons.
- Admin analytics concepts.
- Test and documentation governance.

Areas to avoid copying directly unless needed:

- Legacy frontend route structure.
- MarkdownFlow as the only core authoring model.
- Legacy payment/order compatibility.
- Large operator admin scope.
- Existing personalization assumptions.

## Decision Matrix

| Question | If Yes | Suggested Path |
| --- | --- | --- |
| Do we want mostly the same product with better implementation? | Yes | Continue in AI-Shifu |
| Do we want a different UI and authoring experience? | Yes | Start a new project |
| Do we need existing payment/admin/operation features immediately? | Yes | Continue or fork AI-Shifu |
| Is the research focus AI teaching interaction itself? | Yes | Start a focused new prototype |
| Is the research focus production AI platform engineering? | Yes | Study and extend AI-Shifu |
| Are MarkdownFlow and current pages already unacceptable? | Yes | Start a new project |
| Do we need fast experiments with A2UI frameworks? | Yes | Start a new project |

## Practical Recommendation

Use a two-track strategy:

1. Keep `ai-shifu` as the reference codebase for research, comparison, and
   selective extraction.
2. Create a new lean project for the next-generation product direction.

The new project should initially prove three things:

1. A better authoring and generated-UI model than MarkdownFlow.
2. A better learner experience than the current chat/course shell.
3. A clearer personalization and evaluation architecture.

Only after those three are validated should the new project absorb heavier
platform capabilities such as billing, promotion, operator tools, and full
observability.

## TokUI And shadcn/ui Fit Assessment

### Context

TokUI is being considered as a replacement for MarkdownFlow. The desired UI
direction prefers shadcn/ui, so the key question is not only whether TokUI can
render UI, but whether it can participate cleanly in a shadcn-based product.

### Summary

TokUI is compatible with a shadcn-style product at the surface and theme level,
but it is not a native shadcn renderer.

Out of the box, TokUI renders its own DOM and CSS classes. The React adapter
mounts an imperative TokUI renderer inside a React component; it does not map
TokUI DSL tags to shadcn React components. Therefore, TokUI can coexist with a
shadcn app, but it will not automatically produce real shadcn components such
as the project's `Button`, `Card`, `Dialog`, `Tabs`, or `Form` components.

For a new product whose visual and interaction system should be shadcn-first,
the best use of TokUI is either:

1. Use TokUI as an embedded AI-output surface with custom theme CSS mapped to
   shadcn tokens.
2. Reuse TokUI's DSL and streaming parser ideas, but build a new React renderer
   that maps the parsed AST to local shadcn components.

The second option is more work, but it fits the desired architecture better.

### What Fits Well

TokUI has several qualities that fit a shadcn-based application:

- It has a React adapter, so it can be mounted inside a Next.js/React app.
- It is SSR-friendly at import time, which matters for Next.js.
- It uses CSS variables for theming, while shadcn/ui also recommends CSS
  variables and semantic tokens.
- It has a concise DSL that is likely easier for LLMs to generate than raw JSX.
- It supports streaming incremental rendering, which is valuable for AI UI.
- It includes AI-chat-oriented components such as bubbles, reasoning blocks,
  tool calls, sources, artifacts, plans, terminals, and suggestions.
- It allows custom component registration through its renderer.

### What Does Not Fit Natively

TokUI and shadcn/ui have different rendering models:

- shadcn/ui components are React source components styled with Tailwind and CSS
  variables.
- TokUI's renderer creates DOM nodes directly with `document.createElement`.
- TokUI applies its own classes such as `tokui-card`, `tokui-btn`, and
  `tokui-row`.
- The official TokUI React adapter is a wrapper around the imperative renderer,
  not a React component mapper.

This means a DSL such as:

```tokui
[card tt:登录][input l:手机号][btn tx:继续 v:primary][/card]
```

renders as TokUI's own DOM, not as the project's local shadcn `Card`, `Input`,
and `Button` components.

### UI Adaptation Levels

#### Level 1: Coexistence

Mount TokUI inside a shadcn page as a dynamic AI-output panel.

This is easy and useful for prototypes. The surrounding shell, navigation,
layout, dialogs, forms, and dashboards remain shadcn. TokUI is used only for
generated lesson content, AI chat output, artifacts, small forms, charts, and
interactive blocks.

Pros:

- Fastest path.
- Preserves TokUI streaming.
- Low engineering cost.
- Good for validating whether TokUI DSL is better than MarkdownFlow.

Cons:

- TokUI output will not perfectly look or behave like shadcn.
- Two UI systems exist in one product.
- Component behavior, spacing, accessibility, and form patterns may diverge.

#### Level 2: Token And Theme Mapping

Create a TokUI theme that maps TokUI variables to shadcn CSS variables.

Example direction:

```css
[data-tokui-theme="shadcn"] {
  --tokui-bg: hsl(var(--card));
  --tokui-text: hsl(var(--card-foreground));
  --tokui-border: hsl(var(--border));
  --tokui-primary: hsl(var(--primary));
  --tokui-danger: hsl(var(--destructive));
  --tokui-radius: var(--radius);
}
```

This is the best near-term compromise. TokUI still renders its own DOM, but the
visual language can be made much closer to the surrounding shadcn interface.

Pros:

- Keeps TokUI streaming and components.
- Better visual consistency.
- Reasonable engineering effort.

Cons:

- Still not actual shadcn components.
- Some TokUI component CSS may need overrides for density, radius, shadows, and
  interaction states.
- shadcn styles are Tailwind utility driven, while TokUI is class/CSS driven.

#### Level 3: React Bridge Components

Register TokUI components that mount React/shadcn components into DOM islands
using `ReactDOM.createRoot`.

This can make selected tags render as actual shadcn components, for example
`btn`, `card`, or `dialog`.

Pros:

- Can reuse real shadcn components for high-value tags.
- Lets TokUI DSL drive parts of a shadcn UI.

Cons:

- Adds lifecycle complexity.
- Streaming updates become harder.
- Form submission, event handling, teardown, hydration, and nested slots need
  careful design.
- It risks creating many tiny React roots, which can be awkward and costly.

This is feasible for a few components but not recommended as the main rendering
architecture.

#### Level 4: shadcn-native TokUI Renderer

Use TokUI's DSL/parser idea, but render the parsed AST through React components
that map directly to the local shadcn component set.

Example conceptual mapping:

```tsx
const componentMap = {
  card: ShadcnCardBlock,
  btn: ShadcnButtonBlock,
  input: ShadcnInputBlock,
  tabs: ShadcnTabsBlock,
  callout: ShadcnAlertBlock,
}
```

This is the cleanest long-term architecture if the new product is meant to be
shadcn-first.

Pros:

- One UI system.
- Full control over spacing, accessibility, responsive behavior, and variants.
- Better fit for Next.js and React state.
- Easier to align with local design decisions.

Cons:

- Requires building and maintaining a renderer.
- May not reuse TokUI's existing DOM renderer.
- Streaming has to be reimplemented or adapted at the AST/event level.

### Recommendation For A shadcn-first Product

Do not treat TokUI as a drop-in shadcn replacement.

Use TokUI first as a research prototype for replacing MarkdownFlow. Evaluate
whether its DSL, component vocabulary, and streaming behavior are good enough
for AI-generated lessons. In parallel, design the new product around a
shadcn-native rendering architecture.

Recommended sequence:

1. Build a small shadcn app shell.
2. Embed TokUI as an AI lesson output panel.
3. Add a shadcn-token-compatible TokUI theme.
4. Test LLM generation quality and streaming speed.
5. If the DSL proves useful, build a thin AST-to-shadcn renderer for the core
   learning components.
6. Keep TokUI's existing renderer only for low-risk auxiliary blocks or
   prototyping.

### Decision

TokUI is a good candidate to replace MarkdownFlow as an experimental AI UI DSL,
but it should not own the final UI layer if shadcn/ui is the preferred product
design system.

For the new project, the recommended architecture is:

- shadcn/ui owns the app shell, navigation, cards, dialogs, forms, and core
  product interactions.
- A TokUI-like DSL or AST represents AI-generated lesson content.
- A custom React renderer maps that DSL/AST to shadcn components.
- TokUI's native renderer can be used initially for rapid validation, then
  gradually replaced or narrowed.

## Possible Research Thesis

AI-Shifu demonstrates a production-oriented approach to AI-assisted teaching by
combining structured lesson authoring, LLM-driven interaction, learner-facing
chat, creator/admin tools, billing, metering, and observability. Its main value
is not any single model call but the platform architecture around AI course
delivery.

At the same time, the project shows the limitations of an evolved AI education
codebase. The MarkdownFlow-centered authoring model, legacy compatibility
surfaces, limited end-to-end coverage, incomplete knowledge base direction, and
unclear depth of learner modeling suggest that a next-generation AI tutor may be
better explored in a new project. The existing repository should serve as a
reference implementation and engineering case study rather than the default
foundation for a redesigned product.
