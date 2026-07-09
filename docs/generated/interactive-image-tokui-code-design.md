# Interactive Image TokUI Code Design

> Version: v0.1  
> Scope: ai-shifu only  
> Purpose: give later developers a code-oriented path for integrating the interactive image activity into the current ai-shifu TokUI course-design flow.  
> Hard boundary: do not use `interactive-process` JSON, frontend sample data, `ai-shifu-web`, or `aishifu-next` as product source of truth.

## 0. 中文阅读说明

这份文档是给后续开发用的代码级路线图。它不是产品宣传稿，也不是 UI 草图。

最重要的一句话：

```text
互动图片活动要写进 ai-shifu 现有 TokUI 课程设计链路，
不要继续长成 interactive-process 的独立 JSON 小岛。
```

后续开发可以按这个顺序读：

```text
第 2 节：先看当前代码里已经有什么。
第 3 节：再看为什么第一版放进 generation_options.interactive_blocks。
第 4 节：看互动图片的数据结构。
第 5 节：看后端要改哪些函数。
第 6 节：看为什么必须新增热点级学习记录。
第 7 节：看老师端和学生端组件怎么拆。
第 11 节：看实际开发顺序。
第 12 节：看必须做哪些测试。
```

费曼式理解：

```text
DraftTokuiTemplate 是老师桌上的教案。
PublishedTokuiTemplate 是盖章发给课堂的正式教案。
interactive_blocks[] 是教案里的一段互动图片活动。
学生的每个热点点击和答题，都要像作业纸一样留下记录。
```

## 1. Executive Decision

The interactive image activity is not a standalone product and not the first step of a new generic lesson `Content Blocks[]` system.

It is a structured course-design object inside the current TokUI lesson design:

```text
DraftTokuiTemplate.generation_options.interactive_blocks[]
  -> copied into PublishedTokuiTemplate.generation_options.interactive_blocks[]
  -> exposed to learner runtime as teacher_interactive_blocks
  -> rendered by a dedicated interactive-image learner component
  -> persisted as hotspot-level learning records
```

Feynman version:

```text
DraftTokuiTemplate is the teacher's lesson plan.
PublishedTokuiTemplate is the sealed classroom copy.
interactive_blocks[] is a special activity written into that lesson plan.
The student must see the sealed copy, not a loose JSON file from the prototype.
```

## 2. Current Code Facts

These are confirmed from the current `ai-shifu` code.

### 2.1 Teacher Course Design

Current main files:

```text
src/api/flaskr/service/shifu/models.py
src/api/flaskr/service/shifu/shifu_tokui_funcs.py
src/api/flaskr/service/shifu/route.py
src/cook-web/src/components/shifu-edit/TokuiTemplatePanel.tsx
src/cook-web/src/components/shifu-edit/ShifuEdit.tsx
```

Current teacher-side data path:

```text
Cook Web TokuiTemplatePanel
  -> POST /api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/tokui-template
  -> save_draft_tokui_template()
  -> DraftTokuiTemplate
```

Current `DraftTokuiTemplate` already has:

```text
teacher_intent
prompt_template
concept
audience
material_refs
media_refs
generation_options
context_policy
preview_dsl
preview_interaction_schema
template_hash
```

Current backend already normalizes:

```text
normalize_material_refs()
normalize_media_refs()
normalize_interaction_points()
```

Important existing behavior:

```text
_template_payload_from_request()
  reads material_refs / media_refs / generation_options / interaction_points
  normalizes interaction_points
  mirrors interaction_points into generation_options.interaction_points

template_hash()
  includes generation_options
```

This means if `interactive_blocks` is stored under `generation_options`, template hashing, publishing, and cache invalidation can work with fewer schema changes.

### 2.2 Publish Snapshot

Current main files:

```text
src/api/flaskr/service/shifu/shifu_publish_funcs.py
src/api/flaskr/service/shifu/shifu_tokui_funcs.py
```

Current publish path:

```text
publish_shifu_draft()
  -> copies DraftShifu to PublishedShifu
  -> copies DraftOutlineItem to PublishedOutlineItem
  -> calls publish_tokui_templates()
  -> copies DraftTokuiTemplate to PublishedTokuiTemplate
```

Current `publish_tokui_templates()` copies:

```text
teacher_intent
prompt_template
concept
audience
material_refs
media_refs
generation_options
context_policy
preview_dsl
preview_interaction_schema
template_hash
template_version
```

So if `interactive_blocks` lives inside `generation_options`, publish snapshot copying already has the right basic shape.

### 2.3 Learner Runtime

Current main files:

```text
src/api/flaskr/service/learn/tokui_runtime.py
src/api/flaskr/service/learn/routes.py
src/api/flaskr/service/learn/models.py
src/cook-web/src/components/tokui/LearnerTokuiBlock.tsx
src/cook-web/src/components/tokui/TokuiRenderer.tsx
src/cook-web/src/components/tokui/learnerTokuiStream.ts
```

Current learner-side APIs:

```text
GET  /api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/tokui
POST /api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/tokui
POST /api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/tokui/retry
POST /api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/tokui/stream
POST /api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/tokui/responses
```

Current learner artifact path:

```text
PublishedTokuiTemplate
  -> _template_to_generation_payload()
  -> _build_learner_context()
  -> iter_tokui_llm_generation()
  -> LearnTokuiArtifact
  -> LearnerTokuiBlock
```

Current learner context already includes:

```text
teacher_material_refs
teacher_media_refs
teacher_interaction_points
tokui_responses
```

The new design should add:

```text
teacher_interactive_blocks
```

### 2.4 Current Test/E2E Assets

Existing relevant paths:

```text
src/api/tests/service/tokui/test_common.py
src/api/tests/service/tokui/test_validator.py
src/cook-web/src/components/tokui/LearnerTokuiBlock.test.tsx
src/cook-web/src/components/tokui/TokuiRenderer.test.tsx
e2e/run_tokui_complex_course_e2e.py
e2e/run_tokui_real_railway_course_e2e.py
```

The new work should extend this family of tests. Do not add a shallow smoke test and call it done.

## 3. MVP Architecture

### 3.1 Data Ownership

The backend owns official interactive image data.

Official data lives in:

```text
DraftTokuiTemplate.generation_options.interactive_blocks[]
PublishedTokuiTemplate.generation_options.interactive_blocks[]
```

Teacher UI may expose `interactive_blocks` as a top-level API convenience field, but persistence should mirror it into `generation_options`.

Correct:

```json
{
  "generation_options": {
    "interaction_points": [],
    "interactive_blocks": []
  },
  "interactive_blocks": []
}
```

Wrong:

```text
src/samples/*.ts
interactive-process localStorage
standalone exported JSON
frontend-only fixtures
```

### 3.2 Why Use generation_options First

MVP recommendation:

```text
Store interactive_blocks inside generation_options for the first implementation slice.
```

Reasons:

```text
1. DraftTokuiTemplate and PublishedTokuiTemplate already have generation_options.
2. publish_tokui_templates() already copies generation_options.
3. template_hash() already includes generation_options.
4. learner runtime already loads generation_options.
5. This avoids a premature schema migration before the data shape is battle-tested.
```

This does not mean `interactive_blocks` is vague config forever. It means the first slice can prove the product loop before promoting the structure into dedicated course-design tables.

Promotion trigger:

```text
If operators need search, analytics, review queues, or separate permissions per hotspot,
promote interactive_blocks into dedicated draft/published tables.
```

### 3.3 Rendering Ownership

Do not ask the LLM to rebuild the full interaction as ordinary DSL.

Correct:

```text
TokUI runtime introduces the activity into the lesson flow.
Dedicated InteractiveImageActivity component renders the actual activity.
```

Wrong:

```text
LLM generates plain [img] + [video] + [input] and pretends it is an interactive image.
```

Reason:

```text
The activity has internal state:
which hotspot was clicked,
which video segment was viewed,
which explanation was viewed,
which quiz was answered,
whether the whole activity is complete.

Plain DSL should not own that state.
```

## 4. Proposed Data Contract

### 4.1 Template Payload Shape

Add this shape to teacher save/load/preview payloads.

```json
{
  "interactive_blocks": [
    {
      "interactive_block_id": "turnout_parts_activity",
      "kind": "interactive_image",
      "title": "认识道岔关键部件",
      "description": "点击底图上的热点，学习尖轨、基本轨、转辙机",
      "display_order": "3",
      "base_image": {
        "resource_id": "resource-base-image",
        "url": "/api/storage/courses/turnout/base.png",
        "title": "道岔俯视底图",
        "width": 1920,
        "height": 1080
      },
      "hotspots": [
        {
          "hotspot_id": "switch_rail",
          "label": "尖轨",
          "shape": "circle",
          "position": {
            "x": 42.5,
            "y": 58.0
          },
          "radius": 3.2,
          "video": {
            "resource_id": "resource-video-1",
            "url": "/api/storage/courses/turnout/demo.mp4",
            "clip_start": 35.0,
            "clip_end": 55.0,
            "title": "尖轨动作片段"
          },
          "learning_objective": "学生能说出尖轨如何引导车轮进入不同线路",
          "approved_explanation": "看这里，尖轨像一扇会移动的小门。它贴住哪一边，车轮就会被带向哪一条线路。",
          "evidence_cards": [
            {
              "evidence_card_id": "switch_rail_standard_1",
              "source_title": "铁路轨道培训资料",
              "source_type": "internal_training",
              "section_or_page": "第 12 页",
              "summary": "尖轨与基本轨配合，引导车轮进入不同线路。",
              "detail_reference": "老师端可展开的详细依据或摘录。",
              "review_status": "approved"
            }
          ],
          "quiz": {
            "quiz_id": "switch_rail_quiz_1",
            "question_type": "single_choice",
            "question": "尖轨主要改变的是哪件事？",
            "options": [
              { "id": "A", "text": "车轮走向" },
              { "id": "B", "text": "轨枕高度" },
              { "id": "C", "text": "列车颜色" }
            ],
            "correct_answer": "A",
            "explanation": "尖轨贴靠不同方向后，会引导车轮进入不同线路。"
          },
          "status": "approved"
        }
      ],
      "status": "approved"
    }
  ]
}
```

### 4.2 Coordinate Rules

Use percentage coordinates, not pixels:

```text
position.x: 0-100
position.y: 0-100
radius: percentage of the shorter image side
```

Reason:

```text
The same course must render on desktop, tablets, and mobile.
Pixel positions break when the image scales.
```

MVP hotspot shape:

```text
shape = circle
```

Schema should keep `shape` so a later `rect` extension does not require a data migration:

```json
{
  "shape": "circle"
}
```

Do not enable `rect` in the formal ai-shifu MVP unless the product decision is reopened.

### 4.3 Completion Rules

Hotspot completion requires:

```text
hotspot opened
video segment viewed or explicitly skipped only if no video exists
approved explanation viewed
quiz answered
```

Interactive block completion requires:

```text
all active hotspots completed
```

Quiz correctness is separate from completion:

```text
completed = student submitted required activity
is_correct = whether quiz answer is correct
```

This lets the system say:

```text
The student completed the activity but got "尖轨" wrong.
```

## 5. Backend Implementation Plan

### 5.1 Normalizer

Add to:

```text
src/api/flaskr/service/tokui/common.py
```

New function:

```python
def normalize_interactive_blocks(value: Any) -> list[dict[str, Any]]:
    ...
```

Responsibilities:

```text
1. Accept only list input; otherwise return [] or raise at request boundary.
2. Keep only dict entries.
3. Synthesize stable IDs when absent:
   interactive_block_id = interactive_block_<n>
   hotspot_id = hotspot_<n>
   evidence_card_id = evidence_<n>
4. Coerce kind to interactive_image.
5. Normalize display_order to string.
6. Normalize base_image resource_id/url/title/width/height.
7. Normalize hotspot x/y/radius as bounded numbers.
8. Normalize video clip_start/clip_end as numbers; clip_end must be greater than clip_start when both are present.
9. Keep quiz only when it is single_choice or true_false.
10. Drop empty hotspots and empty blocks.
```

Request boundary behavior:

```text
interactive_blocks is not a list -> raise_param_error("interactive_blocks")
```

Internal context behavior:

```text
missing interactive_blocks -> []
malformed entries -> dropped by normalizer
```

### 5.2 Template Save/Load

Modify:

```text
src/api/flaskr/service/shifu/shifu_tokui_funcs.py
```

Functions:

```text
_serialize_template()
_template_payload_from_request()
save_draft_tokui_template()
_build_generation_prompt()
_build_guidance_prompt()
generate_teacher_tokui_guidance()
generate_teacher_tokui_preview()
```

Expected behavior:

```text
_template_payload_from_request()
  -> reads payload.interactive_blocks
  -> falls back to generation_options.interactive_blocks
  -> validates list
  -> normalized_interactive_blocks = normalize_interactive_blocks(...)
  -> writes generation_options.interactive_blocks = normalized_interactive_blocks
  -> returns top-level interactive_blocks too
```

Pseudo-code:

```python
interactive_blocks = _as_json_value(
    payload.get("interactive_blocks"),
    generation_options.get("interactive_blocks", []),
)
if not isinstance(interactive_blocks, list):
    raise_param_error("interactive_blocks")

normalized_interactive_blocks = normalize_interactive_blocks(interactive_blocks)
generation_options = {
    **generation_options,
    "interaction_points": normalized_interaction_points,
    "interactive_blocks": normalized_interactive_blocks,
}
return {
    ...,
    "interactive_blocks": normalized_interactive_blocks,
    "generation_options": generation_options,
}
```

`_serialize_template()` should expose:

```json
{
  "interactive_blocks": [],
  "generation_options": {
    "interactive_blocks": []
  }
}
```

Reason:

```text
Frontend developers should not need to dig into generation_options just to render the editor.
Backend still stores one stable source inside generation_options.
```

### 5.3 Template Hashing

Because `template_hash()` already includes `generation_options`, the hash changes when `interactive_blocks` changes.

Still add a test proving:

```text
changing hotspot position changes template_hash
changing quiz correct answer changes template_hash
changing evidence summary changes template_hash
```

This matters because learner artifact reuse depends on:

```text
template_hash + context_hash
```

### 5.4 Publish

If `interactive_blocks` stays inside `generation_options`, no special copy code is needed in `publish_tokui_templates()` beyond preserving existing generation_options copy.

Still add tests for:

```text
DraftTokuiTemplate.generation_options.interactive_blocks
  -> PublishedTokuiTemplate.generation_options.interactive_blocks
```

Do not rely on "it should copy because generation_options copies" without a test.

### 5.5 Learner Runtime Context

Modify:

```text
src/api/flaskr/service/learn/tokui_runtime.py
```

Functions:

```text
_template_to_generation_payload()
_build_learner_context()
_artifact_to_dict()
_attach_artifact_chain()
```

Add:

```python
interactive_blocks = normalize_interactive_blocks(
    generation_options.get("interactive_blocks")
)
```

Generation payload should include:

```json
{
  "interactive_blocks": [],
  "generation_options": {
    "interactive_blocks": []
  }
}
```

Learner context should include:

```json
{
  "teacher_interactive_blocks": []
}
```

Artifact response should include the published interactive blocks as sidecar data:

```json
{
  "tokui_artifact_bid": "...",
  "dsl": "...",
  "interactive_blocks": []
}
```

Reason:

```text
The learner component needs exact teacher-approved activity data.
It should not scrape it from generated DSL text.
```

### 5.6 Prompt Contract

Update `_build_generation_prompt()`:

```text
If interactive_blocks exist:
  - Tell the LLM that interactive image activity data is teacher-owned sidecar data.
  - The LLM may introduce or transition into the activity.
  - The LLM must not rewrite hotspot coordinates, quiz answers, evidence cards, or approved explanations.
  - The LLM must not invent interactive block IDs.
```

Recommended prompt idea:

```text
The teacher provided interactive image activities in teacher_interactive_blocks.
Treat them as fixed approved activity data. You may introduce the activity in
learner-facing text, but do not rewrite hotspot content, quiz answers, evidence
cards, media URLs, or coordinates. The frontend renders these activities with a
dedicated component.
```

This avoids the "AI realtime lecture" mistake:

```text
AI can introduce the activity.
AI cannot generate unreviewed hotspot teaching content at learner click time.
```

## 6. Hotspot-Level Learning Records

### 6.1 Why LearnTokuiResponse Is Not Enough

Current `LearnTokuiResponse` records:

```text
field_id
field_type
field_label
value_json
tokui_artifact_bid
published_template_bid
template_hash
progress_record_bid
```

This is good for ordinary TokUI form fields.

It is not enough for interactive image hotspot analytics because we also need:

```text
interactive_block_id
hotspot_id
quiz_id
video viewed
explanation viewed
evidence expanded
answer correctness
per-hotspot completion
block-level completion
```

### 6.2 Recommended Tables

Add two learner tables.

#### learn_interactive_image_hotspot_records

One row per learner + published template + interactive block + hotspot.

Fields:

```text
id
hotspot_record_bid
user_bid
shifu_bid
outline_item_bid
progress_record_bid
tokui_artifact_bid
published_template_bid
template_hash
interactive_block_id
hotspot_id
hotspot_label
base_image_resource_id
video_resource_id
clip_start
clip_end
opened_at
video_viewed_at
explanation_viewed_at
quiz_answered_at
completed_at
is_completed
deleted
created_at
updated_at
```

Indexes:

```text
ix_learn_interactive_hotspot_progress
  user_bid, progress_record_bid, template_hash, deleted

ix_learn_interactive_hotspot_unique_latest
  user_bid, published_template_bid, interactive_block_id, hotspot_id, deleted

ix_learn_interactive_hotspot_artifact
  tokui_artifact_bid, interactive_block_id, hotspot_id, deleted
```

#### learn_interactive_image_quiz_records

One row per learner answer to a hotspot quiz.

Fields:

```text
id
quiz_record_bid
hotspot_record_bid
user_bid
shifu_bid
outline_item_bid
progress_record_bid
tokui_artifact_bid
published_template_bid
template_hash
interactive_block_id
hotspot_id
quiz_id
question_type
answer_json
correct_answer_json
is_correct
answered_at
deleted
created_at
updated_at
```

Indexes:

```text
ix_learn_interactive_quiz_hotspot_record
  hotspot_record_bid, deleted

ix_learn_interactive_quiz_progress
  user_bid, progress_record_bid, template_hash, deleted
```

### 6.3 Backend APIs

Add learner APIs under existing learn route family:

```text
GET  /api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/interactive-image/progress
POST /api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/interactive-image/hotspots/{hotspot_id}/events
POST /api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/interactive-image/hotspots/{hotspot_id}/quiz
```

MVP can combine event and quiz into one endpoint if implementation speed matters, but the payload must stay structured.

Progress response:

```json
{
  "interactive_blocks": [
    {
      "interactive_block_id": "turnout_parts_activity",
      "completed": false,
      "hotspots": [
        {
          "hotspot_id": "switch_rail",
          "opened": true,
          "video_viewed": true,
          "explanation_viewed": true,
          "quiz_answered": true,
          "is_correct": false,
          "completed": true
        }
      ]
    }
  ]
}
```

Event payload:

```json
{
  "tokui_artifact_bid": "artifact-1",
  "published_template_bid": "published-template-1",
  "template_hash": "hash",
  "interactive_block_id": "turnout_parts_activity",
  "hotspot_id": "switch_rail",
  "event_type": "video_viewed"
}
```

Allowed event types:

```text
hotspot_opened
video_viewed
explanation_viewed
evidence_expanded
hotspot_completed
```

Quiz payload:

```json
{
  "tokui_artifact_bid": "artifact-1",
  "published_template_bid": "published-template-1",
  "template_hash": "hash",
  "interactive_block_id": "turnout_parts_activity",
  "hotspot_id": "switch_rail",
  "quiz_id": "switch_rail_quiz_1",
  "answer": "A"
}
```

Server computes:

```text
is_correct
correct_answer_json
completed_at
block completion
```

Do not trust frontend-provided correctness.

### 6.4 Version Binding

Every hotspot/quiz record must bind to:

```text
published_template_bid
template_hash
tokui_artifact_bid
interactive_block_id
hotspot_id
quiz_id
```

Reason:

```text
Published edits create new versions.
A student's old answer must still point to the exact version of the activity they saw.
```

## 7. Frontend Implementation Plan

### 7.1 Teacher Editor

Current file:

```text
src/cook-web/src/components/shifu-edit/TokuiTemplatePanel.tsx
```

Add new local types:

```ts
type TokuiInteractiveBlock = {
  interactive_block_id: string;
  kind: 'interactive_image';
  title: string;
  description: string;
  display_order: string;
  base_image: TokuiInteractiveImageResource;
  hotspots: TokuiInteractiveHotspot[];
  status: 'draft' | 'pending' | 'approved' | 'needs_work' | 'published' | 'archived';
};
```

Add normalizer:

```ts
const normalizeInteractiveBlocks = (value: unknown): TokuiInteractiveBlock[] => { ... };
```

Update:

```text
TokuiTemplate type
normalizeTemplate()
buildPayload()
```

So:

```text
template.interactive_blocks
generationOptions.interactive_blocks
```

are always in sync.

### 7.2 Teacher UI Placement

Current `TokuiTemplatePanel` already contains:

```text
guidance editor
material placements
interaction points
media refs
preview
save button
```

Add a new section:

```text
Interactive Image Activities
```

Suggested component split:

```text
src/cook-web/src/components/shifu-edit/interactive-image/
  InteractiveImageDesigner.tsx
  InteractiveImageCanvas.tsx
  InteractiveHotspotEditor.tsx
  InteractiveHotspotList.tsx
  interactiveImageTypes.ts
  interactiveImageNormalize.ts
```

Do not put all designer logic directly into `TokuiTemplatePanel.tsx`; it is already large.

MVP teacher interactions:

```text
1. Add interactive image activity.
2. Select or paste base image resource/url.
3. Add circular hotspot.
4. Drag hotspot on image.
5. Edit hotspot label.
6. Bind video resource/url.
7. Set clip_start and clip_end.
8. Write approved explanation.
9. Add evidence card.
10. Add single-choice or true/false quiz.
11. Mark hotspot approved.
12. Save template.
```

### 7.3 Media Selection

Current `TokuiTemplatePanel` supports manual URL/resource refs and image generation jobs.

For interactive image MVP:

```text
Base image and hotspot videos should use the same normalized resource shape as media_refs.
```

Do not create a second incompatible resource object.

Recommended resource shape:

```ts
type TokuiInteractiveImageResource = {
  resource_id: string;
  url: string;
  type?: 'image' | 'video';
  title: string;
  description?: string;
  width?: number;
  height?: number;
};
```

### 7.4 Learner Component

Add:

```text
src/cook-web/src/components/tokui/interactive-image/
  InteractiveImageActivity.tsx
  InteractiveImageHotspotLayer.tsx
  InteractiveImageLearningPanel.tsx
  interactiveImageProgressApi.ts
  interactiveImageTypes.ts
```

Props:

```ts
type InteractiveImageActivityProps = {
  shifuBid: string;
  outlineBid: string;
  artifactBid: string;
  publishedTemplateBid: string;
  templateHash: string;
  block: TokuiInteractiveBlock;
  readOnly?: boolean;
  onCompleted?: (interactiveBlockId: string) => void;
};
```

Learner flow:

```text
1. Render base image.
2. Render hotspot buttons by percentage coordinates.
3. On hotspot click, POST hotspot_opened.
4. Open learning panel.
5. Show video segment.
6. When video reaches clip_end or user completes segment, POST video_viewed.
7. Show approved_explanation.
8. When explanation is visible/read, POST explanation_viewed.
9. Show evidence cards.
10. Show quiz.
11. Submit quiz to backend.
12. Backend returns correctness and hotspot completion.
13. Update hotspot state.
14. If all hotspots complete, mark block complete.
```

Important:

```text
Frontend may update optimistic UI for responsiveness.
Backend remains the source of truth for completion and correctness.
```

### 7.5 Integrating With LearnerTokuiBlock

Current `LearnerTokuiBlock` renders a chain of `LearnerTokuiArtifact`.

Extend `LearnerTokuiArtifact` type:

```ts
type LearnerTokuiArtifact = {
  ...
  published_template_bid?: string;
  template_hash?: string;
  interactive_blocks?: TokuiInteractiveBlock[];
};
```

Rendering option for MVP:

```text
Render TokuiRenderer for artifact.dsl.
Then render artifact.interactive_blocks sorted by display_order.
```

This is the lowest-risk first implementation.

Better later:

```text
Support explicit inline markers so interactive image activities can appear at exact positions inside generated DSL.
```

Do not attempt exact inline placement until tests prove the sidecar component loop works.

## 8. Optional Inline Marker Design

The ideal future DSL marker could look like:

```text
[interactive-image id:"turnout_parts_activity"]
```

But this requires validator/parser/renderer support.

Touched files would likely include:

```text
src/cook-web/scripts/validate-tokui.mjs
src/api/scripts/validate-tokui.mjs
src/cook-web/src/components/tokui/TokuiRenderer.tsx
possibly upstream @jboltai/tokui support
```

Risk:

```text
If the validator rejects the new tag, learner generation fails.
If the renderer ignores the tag, the activity disappears.
If the LLM invents IDs, the frontend cannot bind data.
```

Therefore:

```text
MVP should use sidecar interactive_blocks rendered by LearnerTokuiBlock.
Inline markers can be v2 after parser support is proven.
```

## 9. Backend Validation Rules

### 9.1 Save-Time Validation

At teacher draft save:

```text
interactive_blocks must be a list.
Each block must have kind interactive_image.
Each block must have base_image.resource_id or base_image.url.
Each active hotspot must have label and valid coordinates.
clip_end must be greater than clip_start when both exist.
quiz.question_type must be single_choice or true_false.
```

Do not require every hotspot to be fully approved at draft save. Drafts need to be incomplete while teachers work.

### 9.2 Publish-Time Validation

Before publish:

```text
Every active interactive block must have:
  base image
  at least one hotspot
  status approved

Every active hotspot must have:
  label
  coordinates
  video resource or explicit no-video allowance
  clip_start and clip_end when video exists
  learning_objective
  approved_explanation
  at least one approved evidence card
  one valid quiz
  status approved
```

Integration point:

```text
publish_shifu_draft()
  -> after assert_outline_tree_publishable()
  -> before publish_tokui_templates()
  -> assert_tokui_interactive_blocks_publishable(shifu_id)
```

If invalid:

```text
raise_error("server.shifu.interactiveImageNotPublishable")
```

Add i18n keys only when implementing.

## 10. API Contract Summary

### 10.1 Existing API To Extend

Extend request/response:

```text
GET  /api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/tokui-template
POST /api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/tokui-template
POST /api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/tokui-template/preview
POST /api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/tokui-template/guidance
```

New field:

```json
{
  "interactive_blocks": []
}
```

### 10.2 Existing Learner API To Extend

Extend response:

```text
GET/POST /api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/tokui
POST     /api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/tokui/retry
POST     /api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/tokui/stream
```

Final artifact shape should include:

```json
{
  "enabled": true,
  "tokui_artifact_bid": "...",
  "published_template_bid": "...",
  "template_hash": "...",
  "dsl": "...",
  "interactive_blocks": []
}
```

For streamed final events:

```json
{
  "type": "final",
  "artifact": {
    "interactive_blocks": []
  }
}
```

### 10.3 New Learner Progress API

Add:

```text
GET  /api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/interactive-image/progress
POST /api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/interactive-image/events
POST /api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/interactive-image/quiz
```

Keep all three behind the same learner auth/context behavior as existing learn routes.

## 11. Suggested Implementation Order

### Step 1: Backend Contract Without UI

Implement:

```text
normalize_interactive_blocks()
_template_payload_from_request()
_serialize_template()
_template_to_generation_payload()
_build_learner_context()
_artifact_to_dict()
```

Add tests proving:

```text
save accepts interactive_blocks
save mirrors interactive_blocks into generation_options
load returns top-level interactive_blocks
publish copies interactive_blocks
learner artifact response includes interactive_blocks
template_hash changes when hotspot data changes
```

### Step 2: Teacher Editor Minimal UI

Implement:

```text
InteractiveImageDesigner
base image selector/url field
add circle hotspot
drag hotspot
edit hotspot detail form
save through existing saveTokuiTemplate
```

No student-side feature is complete until this saves to backend and reloads correctly.

### Step 3: Learner Component

Implement:

```text
InteractiveImageActivity
progress API
event API
quiz API
hotspot completion
block completion
```

Integrate under `LearnerTokuiBlock`.

### Step 4: Publish Validation

Add publish-time checks:

```text
complete approved block
complete approved hotspots
valid quiz
valid evidence
valid video segment
```

Tests must prove invalid drafts cannot publish.

### Step 5: Full E2E

Use the existing `e2e/` style, not a smoke test.

Required E2E story:

```text
1. Create or load railway course.
2. Save TokUI template with one interactive image block and at least three hotspots.
3. Publish course.
4. Open learner page.
5. Confirm interactive image renders.
6. Click each hotspot.
7. Confirm correct video/explanation/evidence/quiz appears.
8. Submit at least one correct and one incorrect quiz.
9. Refresh page.
10. Confirm hotspot-level progress persists.
11. Confirm backend records bind to published_template_bid, template_hash, interactive_block_id, hotspot_id, quiz_id.
```

## 12. Tests Required

### 12.1 Backend Unit Tests

Add/extend:

```text
src/api/tests/service/tokui/test_common.py
src/api/tests/service/tokui/test_interactive_image.py
```

Cases:

```text
normalize_interactive_blocks keeps valid block
normalize_interactive_blocks drops empty block
normalize_interactive_blocks bounds coordinates
normalize_interactive_blocks rejects invalid request type at boundary
template payload mirrors top-level interactive_blocks into generation_options
template hash changes on hotspot coordinate/quiz/evidence changes
publish copies interactive_blocks snapshot
publish rejects incomplete approved interactive block
```

### 12.2 Backend Learner Tests

Add tests for:

```text
learner context includes teacher_interactive_blocks
artifact response includes interactive_blocks sidecar
hotspot event creates/updates hotspot record
quiz submission computes is_correct server-side
block completion only true after all hotspots completed
records bind to published_template_bid and template_hash
```

### 12.3 Frontend Unit Tests

Add/extend:

```text
src/cook-web/src/components/shifu-edit/TokuiTemplatePanel.test.tsx
src/cook-web/src/components/tokui/LearnerTokuiBlock.test.tsx
src/cook-web/src/components/tokui/interactive-image/*.test.tsx
```

Cases:

```text
teacher can add a block and hotspot
dragging hotspot updates percentage coordinates
save payload includes interactive_blocks and generation_options.interactive_blocks
learner renders sidecar interactive_blocks
hotspot click opens learning panel
quiz submit calls backend and marks hotspot complete
refresh uses persisted progress
```

### 12.4 E2E

Add or extend:

```text
e2e/run_tokui_complex_course_e2e.py
```

Do not create a fake "page loads" smoke test.

Minimum acceptance:

```text
real persisted teacher design
publish snapshot
learner rendering
three hotspots
hotspot-level records
refresh persistence
at least one incorrect answer path
```

## 13. Migration Strategy

### 13.1 MVP Tables

If only storing course design in `generation_options`, no migration is needed for the teacher/publish data.

Hotspot learning records do need migrations:

```text
add learn_interactive_image_hotspot_records
add learn_interactive_image_quiz_records
```

### 13.2 Future Promotion

If course design needs dedicated tables later:

```text
shifu_draft_interactive_image_blocks
shifu_draft_interactive_image_hotspots
shifu_published_interactive_image_blocks
shifu_published_interactive_image_hotspots
```

Migration approach:

```text
1. Keep generation_options.interactive_blocks as compatibility source.
2. Backfill dedicated draft/published rows from generation_options.
3. Read dedicated rows first; fall back to generation_options during transition.
4. Once stable, stop writing new generation_options interactive_blocks if desired.
```

Do not start with this unless the first implementation slice genuinely needs queryable teacher-side blocks.

## 14. Failure Modes To Avoid

### 14.1 AI Realtime Lecture Drift

Wrong:

```text
Student clicks hotspot -> AI writes new explanation live.
```

Correct:

```text
Student clicks hotspot -> show teacher-approved explanation from published template.
```

### 14.2 Frontend Sample Drift

Wrong:

```text
E2E passes because src/samples/railway.ts contains the activity.
```

Correct:

```text
E2E fails unless backend persisted teacher design exists and publishes.
```

### 14.3 Total-Only Completion

Wrong:

```text
Record only "interactive activity completed".
```

Correct:

```text
Record every hotspot and quiz result.
```

### 14.4 LLM-Owned Coordinates

Wrong:

```text
LLM decides hotspot coordinates.
```

Correct:

```text
Teacher editor owns coordinates; LLM may only introduce the activity.
```

### 14.5 Direct Prototype JSON

Wrong:

```text
Learner page imports interactive-process export JSON.
```

Correct:

```text
Learner page receives interactive_blocks from PublishedTokuiTemplate through backend APIs.
```

## 15. First Development Checklist

Before coding:

```text
1. Re-read this doc and docs/generated/interactive-content-block-integration.md.
2. Confirm no implementation touches ai-shifu-web or aishifu-next.
3. Confirm whether MVP stores course design only in generation_options.
4. Confirm exact learner record table names.
5. Confirm whether formal MVP allows only circle hotspots.
```

During coding:

```text
1. Add backend normalizer first.
2. Add backend tests before frontend UI grows.
3. Keep interactive_blocks mirrored top-level <-> generation_options.
4. Keep published snapshot immutable.
5. Keep learner correctness server-side.
```

Before claiming done:

```text
1. Backend tests pass.
2. Frontend type check passes.
3. Full E2E proves persisted teacher design -> publish -> learner -> hotspot records.
4. No frontend sample/fixture is the source of truth.
5. No standalone interactive-process JSON is used by the learner page.
```
