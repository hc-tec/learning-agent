from types import SimpleNamespace
from unittest.mock import patch

from flaskr.service.tokui.common import (
    normalize_interaction_points,
    normalize_interaction_schema,
    normalize_material_refs,
    normalize_media_refs,
)
from flaskr.service.shifu.shifu_tokui_funcs import (
    _build_generation_prompt,
    _build_guidance_prompt,
    _template_payload_from_request,
)
from flaskr.service.learn.tokui_runtime import _continuation_contract_errors
from flaskr.service.learn.tokui_runtime import (
    _build_learner_context,
    _filter_artifacts_for_chain,
    _has_continue_response_values,
    _JsonStringFieldStreamExtractor,
)


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


def test_normalize_material_refs_keeps_course_design_placement_fields():
    normalized = normalize_material_refs(
        [
            {
                "placement_id": "material-a",
                "position": 2,
                "insertion_point": "讲完四类铁路后立即插入",
                "media_type": "video",
                "title": "四类铁路实景对比短片",
                "prompt": "高铁、城际、客货共线、重载分屏对比",
                "purpose": "建立直观体感",
                "resource_bid": "resource-video",
                "src": "https://example.test/railway.mp4",
            },
            {},
        ]
    )

    assert normalized == [
        {
            "placement_id": "material-a",
            "position": "2",
            "insertion_point": "讲完四类铁路后立即插入",
            "media_type": "video",
            "title": "四类铁路实景对比短片",
            "description": "高铁、城际、客货共线、重载分屏对比",
            "purpose": "建立直观体感",
            "resource_id": "resource-video",
            "url": "https://example.test/railway.mp4",
        }
    ]


def test_normalize_interaction_points_preserves_blocking_dependency_design():
    normalized = normalize_interaction_points(
        [
            {
                "field_id": "railway_type_check",
                "position": 3,
                "insertion_point": "讲完重载铁路定义后立即插入",
                "kind": "feynman_check",
                "question": "万吨列车制动健康预测属于哪类铁路？",
                "response_schema": {"field_type": "text"},
                "blocking": True,
                "continuation_hint": "根据答案补讲重载铁路和高铁的业务差异",
            }
        ]
    )

    assert normalized == [
        {
            "interaction_id": "railway_type_check",
            "position": "3",
            "insertion_point": "讲完重载铁路定义后立即插入",
            "kind": "feynman_check",
            "prompt": "万吨列车制动健康预测属于哪类铁路？",
            "response_schema": {"field_type": "text"},
            "blocking": True,
            "continue_on_submit": True,
            "downstream_context_policy": "",
            "continuation_hint": "根据答案补讲重载铁路和高铁的业务差异",
        }
    ]


def test_template_payload_stores_interaction_points_in_generation_options():
    payload = _template_payload_from_request(
        {
            "teacher_intent": "学生能区分四类铁路",
            "prompt_template": "按速度和功能逐类精讲",
            "material_refs": [{"title": "对比图"}],
            "media_refs": [],
            "interaction_points": [
                {
                    "question": "为什么高铁一般不跑货运列车？",
                    "blocking": True,
                }
            ],
            "generation_options": {"model": "tokui-e2e-controlled"},
            "context_policy": {},
        }
    )

    assert payload["material_refs"][0]["title"] == "对比图"
    assert payload["generation_options"]["interaction_points"][0]["prompt"] == (
        "为什么高铁一般不跑货运列车？"
    )


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


def test_generation_prompt_includes_material_and_interaction_design_contracts():
    prompt = _build_generation_prompt(
        template_payload={
            "teacher_intent": "学生能区分四类铁路",
            "prompt_template": "用铁路行业基本格局课程脚本授课",
            "material_refs": [
                {
                    "insertion_point": "讲完四类铁路后立即插入",
                    "media_type": "image",
                    "title": "中国四类铁路核心参数对比图",
                    "purpose": "结构化对比",
                }
            ],
            "media_refs": [],
            "generation_options": {
                "interaction_mode": "checkpoint",
                "blocking_checkpoint": True,
                "interaction_points": [
                    {
                        "insertion_point": "讲完重载铁路场景后插入",
                        "prompt": "客户说万吨列车制动健康预测属于哪类铁路？",
                        "blocking": True,
                    }
                ],
            },
        },
        context_payload={"mode": "learner_runtime", "tokui_responses": []},
    )

    assert "structured material placements" in prompt
    assert "explicit interaction/check points" in prompt
    assert "flow insertion point by default" in prompt
    assert "Do not dump all interaction points together" in prompt
    assert "student-facing teaching rewrite" in prompt
    assert "do not merely copy the teacher script verbatim" in prompt
    assert "learner-facing classroom flow" in prompt
    assert "中国四类铁路核心参数对比图" in prompt
    assert "万吨列车制动健康预测" in prompt
    assert '[input n:"field_id" l:"field label" t:text req]' in prompt
    assert '[btn tx:"提交" v:primary' in prompt
    assert "Do not generate `[submit]`" in prompt
    assert '[img s:"provided_url" tt:"title"' in prompt
    assert '[video s:"provided_url"]' in prompt
    assert "Do not generate `[media]` tags" in prompt
    assert "素材待提供" in prompt


def test_generation_prompt_requires_differentiated_feedback_after_response():
    prompt = _build_generation_prompt(
        template_payload={
            "teacher_intent": "学生能区分四类铁路",
            "prompt_template": "先讲四类铁路，再根据学生答案继续讲解",
            "generation_options": {},
        },
        context_payload={
            "mode": "learner_runtime",
            "tokui_responses": [
                {
                    "field_id": "heavy_haul_answer",
                    "field_type": "text",
                    "value": "重载铁路",
                }
            ],
        },
    )

    assert "generate only the next appropriate continuation block" in prompt
    assert "first DSL block" in prompt
    assert "do not restart the same explanation" in prompt
    assert "append this new block after the prior" in prompt
    assert "diagnose the answer quality" in prompt
    assert "correct" in prompt
    assert "incorrect" in prompt
    assert "vague/incomplete" in prompt
    assert "off-topic" in prompt
    assert "Choose the continuation strategy from that diagnosis" in prompt
    assert "incorrect, vague, incomplete, or off-topic answers must get" in prompt
    assert "回答正确" in prompt
    assert "存在误区" in prompt
    assert "回答不够具体" in prompt
    assert "答非所问" in prompt
    assert "Do not mechanically continue" in prompt
    assert "_retry" in prompt
    assert "_clarification" in prompt
    assert "do not reuse an already answered field_id" in prompt


def test_continuation_contract_rejects_repeated_answered_fields():
    errors = _continuation_contract_errors(
        {
            "dsl": "[card tt:\"回答正确\"]答得对，我们继续。[/card]",
            "interaction_schema": [
                {"field_id": "heavy_haul_answer", "field_type": "text"},
                {"field_id": "next_question", "field_type": "text"},
            ]
        },
        {
            "tokui_responses": [
                {"field_id": "heavy_haul_answer", "value": "重载铁路"}
            ]
        },
    )

    assert errors
    assert errors[0]["code"] == "TokuiContinuationRepeatedAnsweredFields"
    assert errors[0]["field_ids"] == ["heavy_haul_answer"]


def test_continuation_contract_requires_answer_quality_feedback():
    errors = _continuation_contract_errors(
        {
            "dsl": "[card tt:\"继续学习\"]现在继续讲城际铁路。[/card]",
            "interaction_schema": [
                {"field_id": "next_question", "field_type": "text"},
            ],
        },
        {
            "tokui_responses": [
                {"field_id": "heavy_haul_answer", "value": "重载铁路"}
            ]
        },
    )

    assert errors
    assert errors[0]["code"] == "TokuiContinuationMissingAnswerFeedback"


def test_continue_response_detection_ignores_non_blocking_answers():
    interaction_schema = [
        {
            "field_id": "background_answer",
            "field_type": "text",
            "blocking": False,
            "continue_on_submit": False,
        },
        {
            "field_id": "heavy_haul_answer",
            "field_type": "text",
            "blocking": True,
            "continue_on_submit": True,
        },
    ]

    assert (
        _has_continue_response_values(
            interaction_schema,
            [{"field_id": "background_answer", "value": "铁路经验"}],
        )
        is False
    )
    assert (
        _has_continue_response_values(
            interaction_schema,
            [{"field_id": "heavy_haul_answer", "value": "重载铁路"}],
        )
        is True
    )


def test_learner_context_loads_tokui_responses_from_current_progress_only():
    with patch(
        "flaskr.service.learn.tokui_runtime._load_existing_responses",
        return_value=[{"field_id": "current_answer", "value": "ok"}],
    ) as load_existing_responses:
        context = _build_learner_context(
            user_bid="user-1",
            shifu_bid="shifu-1",
            outline=SimpleNamespace(
                outline_item_bid="outline-1",
                title="Lesson",
                position=1,
            ),
            progress_record=SimpleNamespace(
                progress_record_bid="progress-current",
                status=602,
                block_position=0,
            ),
            template=SimpleNamespace(
                material_refs="[]",
                media_refs="[]",
                generation_options="{}",
            ),
        )

    load_existing_responses.assert_called_once_with(
        "user-1",
        "shifu-1",
        "outline-1",
        "progress-current",
    )
    assert context["tokui_responses"] == [
        {"field_id": "current_answer", "value": "ok"}
    ]


def test_stream_extractor_emits_dsl_value_across_json_chunks():
    extractor = _JsonStringFieldStreamExtractor("dsl")
    chunks = [
        '{"dsl":"[card tt:\\"',
        '标题\\"]第一行\\n第二',
        '行[/card]","interaction_schema":[]}',
    ]

    assert "".join(extractor.feed(chunk) for chunk in chunks) == (
        '[card tt:"标题"]第一行\n第二行[/card]'
    )


def test_artifact_chain_keeps_latest_failed_fallback_without_old_failures():
    artifacts = [
        SimpleNamespace(
            tokui_artifact_bid="artifact-1",
            validation_status="validated",
        ),
        SimpleNamespace(
            tokui_artifact_bid="artifact-failed-old",
            validation_status="failed",
        ),
        SimpleNamespace(
            tokui_artifact_bid="artifact-failed-latest",
            validation_status="failed",
        ),
    ]

    filtered = _filter_artifacts_for_chain(artifacts)

    assert [item.tokui_artifact_bid for item in filtered] == [
        "artifact-1",
        "artifact-failed-latest",
    ]


def test_artifact_chain_keeps_submitted_history_after_successful_continuation():
    artifacts = [
        SimpleNamespace(
            tokui_artifact_bid="artifact-1",
            validation_status="validated",
        ),
        SimpleNamespace(
            tokui_artifact_bid="artifact-failed-old",
            validation_status="failed",
        ),
        SimpleNamespace(
            tokui_artifact_bid="artifact-2",
            validation_status="validated",
        ),
    ]

    filtered = _filter_artifacts_for_chain(
        artifacts,
        responses_by_artifact={
            "artifact-1": [{"field_id": "checkpoint", "value": "answer"}],
        },
    )

    assert [item.tokui_artifact_bid for item in filtered] == [
        "artifact-1",
        "artifact-2",
    ]


def test_artifact_chain_keeps_unsubmitted_prelude_before_submitted_checkpoint():
    artifacts = [
        SimpleNamespace(
            tokui_artifact_bid="artifact-prelude",
            validation_status="validated",
        ),
        SimpleNamespace(
            tokui_artifact_bid="artifact-checkpoint",
            validation_status="validated",
        ),
        SimpleNamespace(
            tokui_artifact_bid="artifact-continuation",
            validation_status="validated",
        ),
    ]

    filtered = _filter_artifacts_for_chain(
        artifacts,
        responses_by_artifact={
            "artifact-checkpoint": [{"field_id": "checkpoint", "value": "answer"}],
        },
    )

    assert [item.tokui_artifact_bid for item in filtered] == [
        "artifact-prelude",
        "artifact-checkpoint",
        "artifact-continuation",
    ]


def test_artifact_chain_drops_stale_unsubmitted_retry_before_submitted_checkpoint():
    artifacts = [
        SimpleNamespace(
            tokui_artifact_bid="artifact-stale-retry",
            validation_status="validated",
        ),
        SimpleNamespace(
            tokui_artifact_bid="artifact-prelude",
            validation_status="validated",
        ),
        SimpleNamespace(
            tokui_artifact_bid="artifact-checkpoint",
            validation_status="validated",
        ),
        SimpleNamespace(
            tokui_artifact_bid="artifact-continuation",
            validation_status="validated",
        ),
    ]

    filtered = _filter_artifacts_for_chain(
        artifacts,
        responses_by_artifact={
            "artifact-checkpoint": [{"field_id": "checkpoint", "value": "answer"}],
        },
    )

    assert [item.tokui_artifact_bid for item in filtered] == [
        "artifact-prelude",
        "artifact-checkpoint",
        "artifact-continuation",
    ]


def test_artifact_chain_drops_old_unsubmitted_validated_retries():
    artifacts = [
        SimpleNamespace(
            tokui_artifact_bid="artifact-old",
            validation_status="validated",
        ),
        SimpleNamespace(
            tokui_artifact_bid="artifact-latest",
            validation_status="validated",
        ),
    ]

    filtered = _filter_artifacts_for_chain(artifacts)

    assert [item.tokui_artifact_bid for item in filtered] == ["artifact-latest"]
