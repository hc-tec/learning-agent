from flaskr.service.tokui.common import normalize_interaction_schema, normalize_media_refs


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
