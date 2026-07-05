import itertools
from decimal import Decimal

from flaskr.dao import db
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftTokuiTemplate,
    TokuiImageGenerationCandidate,
    TokuiImageGenerationJob,
)
from flaskr.service.tokui import image_jobs
from flaskr.service.tokui.common import json_dumps
from flaskr.service.tokui.image_generation import GeneratedImage


def _seed_outline(shifu_bid: str, outline_bid: str) -> None:
    db.session.add(
        DraftOutlineItem(
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            title="TokUI image job test outline",
            type=402,
            created_user_bid="teacher-1",
            updated_user_bid="teacher-1",
        )
    )
    db.session.commit()


def _seed_template(shifu_bid: str, outline_bid: str) -> DraftTokuiTemplate:
    template = DraftTokuiTemplate(
        tokui_template_bid=f"template-{outline_bid}",
        shifu_bid=shifu_bid,
        outline_item_bid=outline_bid,
        teacher_intent="Help learners understand braking pressure transfer",
        prompt_template="Use a concrete railway braking scenario.",
        concept="Brake pressure",
        audience="Beginners",
        material_refs="[]",
        media_refs=json_dumps(
            [
                {
                    "resource_id": "existing-resource",
                    "url": "/existing.png",
                    "type": "image",
                    "title": "Existing",
                    "description": "",
                }
            ],
            [],
        ),
        generation_options="{}",
        context_policy="{}",
        template_hash="template-hash",
        created_user_bid="teacher-1",
        updated_user_bid="teacher-1",
    )
    db.session.add(template)
    db.session.commit()
    return template


def _seed_job(
    app,
    *,
    shifu_bid: str = "shifu-image-job",
    outline_bid: str = "outline-image-job",
    job_bid: str = "job-image-job",
    candidate_count: int = 3,
    optimizer_enabled: bool = False,
    optimizer_model: str = "",
) -> TokuiImageGenerationJob:
    job = TokuiImageGenerationJob(
        job_bid=job_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_bid,
        tokui_template_bid=f"template-{outline_bid}",
        created_user_bid="teacher-1",
        status=image_jobs.JOB_STATUS_QUEUED,
        teacher_prompt="Draw a clear teaching diagram",
        prompt_optimization_status=image_jobs.PROMPT_STATUS_PENDING,
        prompt_optimizer_enabled=1 if optimizer_enabled else 0,
        prompt_optimizer_model=optimizer_model,
        prompt_optimizer_temperature=Decimal("0.2"),
        prompt_optimizer_template_snapshot="Optimize the prompt",
        provider_base_url="https://image-provider.test/v1",
        provider_model="gpt-image-2",
        provider_size="1024x1024",
        provider_timeout_seconds=10,
        candidate_count=candidate_count,
    )
    db.session.add(job)
    db.session.commit()
    return job


def test_operator_tokui_image_config_masks_api_key(monkeypatch):
    values = {
        "TOKUI_IMAGE_API_BASE_URL": "https://image-provider.test/v1",
        "TOKUI_IMAGE_API_KEY": "secret-key",
        "TOKUI_IMAGE_MODEL": "gpt-image-2",
        "TOKUI_IMAGE_TIMEOUT_SECONDS": "30",
        "TOKUI_IMAGE_SIZE": "1024x1024",
        "TOKUI_IMAGE_DEFAULT_CANDIDATE_COUNT": "3",
        "TOKUI_IMAGE_PROMPT_OPTIMIZER_ENABLED": "true",
        "TOKUI_IMAGE_PROMPT_OPTIMIZER_MODEL": "deepseek-v4-flash",
        "TOKUI_IMAGE_PROMPT_OPTIMIZER_TEMPERATURE": "0.2",
        "TOKUI_IMAGE_PROMPT_OPTIMIZER_SYSTEM_PROMPT": "Optimize",
    }
    monkeypatch.setattr(image_jobs, "get_config", lambda key, default=None: values.get(key, default))

    result = image_jobs.get_operator_tokui_image_config()

    assert result["api_key_configured"] is True
    assert "api_key" not in result
    assert result["default_candidate_count"] == 3
    assert result["prompt_optimizer_enabled"] is True


def test_update_operator_tokui_image_config_keeps_blank_api_key(app, monkeypatch):
    calls = []
    monkeypatch.setattr(
        image_jobs,
        "add_config",
        lambda app, key, value, is_secret=False, updated_by="system": calls.append(
            (key, value, is_secret, updated_by)
        ),
    )
    monkeypatch.setattr(
        image_jobs,
        "get_operator_tokui_image_config",
        lambda: {"api_key_configured": True},
    )

    result = image_jobs.update_operator_tokui_image_config(
        app,
        "operator-1",
        {
            "api_key": "",
            "model": "gpt-image-2",
            "prompt_optimizer_enabled": True,
        },
    )

    assert result == {"api_key_configured": True}
    assert ("TOKUI_IMAGE_API_KEY", "", True, "operator-1") not in calls
    assert ("TOKUI_IMAGE_MODEL", "gpt-image-2", False, "operator-1") in calls
    assert (
        "TOKUI_IMAGE_PROMPT_OPTIMIZER_ENABLED",
        "true",
        False,
        "operator-1",
    ) in calls


def test_prompt_optimizer_failure_stops_before_provider(app, monkeypatch):
    with app.app_context():
        _seed_outline("shifu-opt-fail", "outline-opt-fail")
        _seed_job(
            app,
            shifu_bid="shifu-opt-fail",
            outline_bid="outline-opt-fail",
            job_bid="job-opt-fail",
            optimizer_enabled=True,
            optimizer_model="",
        )

    provider_calls = []
    monkeypatch.setattr(
        image_jobs,
        "request_generated_image",
        lambda *args, **kwargs: provider_calls.append(kwargs),
    )

    image_jobs._process_job(app, "job-opt-fail")

    with app.app_context():
        job = TokuiImageGenerationJob.query.filter_by(job_bid="job-opt-fail").first()
        assert job.status == image_jobs.JOB_STATUS_FAILED
        assert job.prompt_optimization_status == image_jobs.PROMPT_STATUS_FAILED
        assert "tokuiImagePromptOptimizerNotConfigured" in job.error_message
        assert provider_calls == []
        assert TokuiImageGenerationCandidate.query.filter_by(job_bid="job-opt-fail").count() == 0


def test_partial_candidate_success_moves_job_to_awaiting_selection(app, monkeypatch):
    with app.app_context():
        _seed_outline("shifu-partial", "outline-partial")
        _seed_job(
            app,
            shifu_bid="shifu-partial",
            outline_bid="outline-partial",
            job_bid="job-partial",
            candidate_count=3,
            optimizer_enabled=False,
        )

    counter = itertools.count()

    def fake_request_generated_image(*args, **kwargs):
        if next(counter) == 0:
            return (
                GeneratedImage(
                    content=b"png",
                    content_type="image/png",
                    provider_payload={"b64_json": "hidden"},
                ),
                {"data": [{"b64_json": "hidden"}]},
            )
        raise RuntimeError("provider timeout")

    def fake_store_generated_image(*args, **kwargs):
        return {
            "resource_id": "resource-success",
            "url": "/api/storage/courses/tokui/generated-images/resource-success.png",
            "type": "image",
            "title": "TokUI generated image",
            "description": "Draw a clear teaching diagram",
        }

    monkeypatch.setattr(image_jobs, "request_generated_image", fake_request_generated_image)
    monkeypatch.setattr(image_jobs, "_store_generated_image", fake_store_generated_image)

    image_jobs._process_job(app, "job-partial")

    with app.app_context():
        job = TokuiImageGenerationJob.query.filter_by(job_bid="job-partial").first()
        candidates = TokuiImageGenerationCandidate.query.filter_by(
            job_bid="job-partial"
        ).all()
        assert job.status == image_jobs.JOB_STATUS_AWAITING_SELECTION
        assert job.final_provider_prompt == "Draw a clear teaching diagram"
        assert len(candidates) == 3
        assert sum(
            candidate.status == image_jobs.CANDIDATE_STATUS_SUCCEEDED
            for candidate in candidates
        ) == 1
        assert sum(
            candidate.status == image_jobs.CANDIDATE_STATUS_FAILED
            for candidate in candidates
        ) == 2


def test_all_candidate_failures_mark_job_failed(app, monkeypatch):
    with app.app_context():
        _seed_outline("shifu-all-fail", "outline-all-fail")
        _seed_job(
            app,
            shifu_bid="shifu-all-fail",
            outline_bid="outline-all-fail",
            job_bid="job-all-fail",
            candidate_count=2,
            optimizer_enabled=False,
        )

    monkeypatch.setattr(
        image_jobs,
        "request_generated_image",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider down")),
    )

    image_jobs._process_job(app, "job-all-fail")

    with app.app_context():
        job = TokuiImageGenerationJob.query.filter_by(job_bid="job-all-fail").first()
        assert job.status == image_jobs.JOB_STATUS_FAILED
        assert job.error_message == "All image candidates failed"


def test_select_candidate_appends_media_ref_to_draft_template(app, monkeypatch):
    with app.app_context():
        _seed_outline("shifu-select", "outline-select")
        _seed_template("shifu-select", "outline-select")
        _seed_job(
            app,
            shifu_bid="shifu-select",
            outline_bid="outline-select",
            job_bid="job-select",
            candidate_count=1,
            optimizer_enabled=False,
        )
        db.session.add(
            TokuiImageGenerationCandidate(
                candidate_bid="candidate-select",
                job_bid="job-select",
                candidate_index=0,
                status=image_jobs.CANDIDATE_STATUS_SUCCEEDED,
                resource_id="resource-selected",
                resource_url="/api/storage/courses/tokui/generated-images/resource-selected.png",
                title="Selected diagram",
                description="Optimized teaching prompt",
            )
        )
        db.session.commit()

    from flaskr.service.shifu import shifu_tokui_funcs

    monkeypatch.setattr(
        shifu_tokui_funcs,
        "check_text_with_risk_control",
        lambda *args, **kwargs: None,
    )

    result = image_jobs.select_tokui_image_candidate(
        app,
        user_bid="teacher-1",
        shifu_bid="shifu-select",
        outline_bid="outline-select",
        job_bid="job-select",
        candidate_bid="candidate-select",
    )

    assert result["job"]["status"] == image_jobs.JOB_STATUS_SELECTED
    assert result["media_ref"]["resource_id"] == "resource-selected"
    assert len(result["template"]["media_refs"]) == 2
    assert result["template"]["media_refs"][-1]["resource_id"] == "resource-selected"
