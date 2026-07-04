from flaskr.service.tokui.common import normalize_interaction_schema, normalize_media_refs
from flaskr.service.shifu.shifu_tokui_funcs import _build_guidance_prompt


def test_normalize_interaction_schema_preserves_blocking_checkpoint_fields():
    normalized = normalize_interaction_schema(
        [
            {
                "field_id": "first_understanding",
                "field_type": "text",
                "label": "Say it in your own words",
                "required": True,
                "semantic_role": "check_understanding",
                "value_shape": "string",
                "blocking": True,
                "continue_on_submit": True,
                "continuation_hint": "Use the answer to choose the next example.",
            }
        ]
    )

    assert normalized == [
        {
            "field_id": "first_understanding",
            "field_type": "text",
            "label": "Say it in your own words",
            "required": True,
            "semantic_role": "check_understanding",
            "value_shape": "string",
            "blocking": True,
            "continue_on_submit": True,
            "continuation_hint": "Use the answer to choose the next example.",
        }
    ]


def test_normalize_interaction_schema_defaults_continuation_to_blocking():
    normalized = normalize_interaction_schema(
        [{"field_id": "checkpoint", "blocking": True}]
    )

    assert normalized[0]["continue_on_submit"] is True
    assert normalized[0]["continuation_hint"] == ""


def test_normalize_media_refs_keeps_stable_resource_fields():
    normalized = normalize_media_refs(
        [
            {
                "resource_bid": "resource-1",
                "src": "https://example.test/train.png",
                "media_type": "image",
                "name": "Traction diagram",
                "description": "Teacher-selected diagram",
            },
            {
                "id": "video-1",
                "url": "https://example.test/intro.mp4",
                "type": "video",
            },
            {"url": ""},
        ]
    )

    assert normalized == [
        {
            "resource_id": "resource-1",
            "url": "https://example.test/train.png",
            "type": "image",
            "title": "Traction diagram",
            "description": "Teacher-selected diagram",
        },
        {
            "resource_id": "video-1",
            "url": "https://example.test/intro.mp4",
            "type": "video",
            "title": "",
            "description": "",
        },
    ]


def test_build_guidance_prompt_treats_prompt_template_as_teaching_guide():
    prompt = _build_guidance_prompt(
        template_payload={
            "teacher_intent": "学生能判断铁路制动压力传递的关键环节",
            "prompt_template": "先用真实场景解释，再提问检查理解",
            "concept": "制动压力传递",
            "audience": "铁路专业新生",
            "generation_options": {
                "interaction_mode": "checkpoint",
                "blocking_checkpoint": True,
            },
        },
        context_payload={"mode": "teacher_guidance_authoring"},
    )

    assert "instructions for the AI teacher" in prompt
    assert "blocking checkpoint question" in prompt
    assert "Do not introduce any third language" in prompt
    assert "学生能判断铁路制动压力传递的关键环节" in prompt
