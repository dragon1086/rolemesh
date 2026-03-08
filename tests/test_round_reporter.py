from __future__ import annotations

from rolemesh.routing.round_reporter import (
    _extract_done_report_v1,
    _record_quality_scores,
)


class _TrackerStub:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def record(self, **kwargs) -> None:
        self.calls.append(kwargs)


def test_extract_done_report_v1_accepts_multiline_json_block():
    summary = """
    작업 완료
    DONE_REPORT_V1:
    ```json
    {
      "status": "verified",
      "score": 91,
      "provider": "amp"
    }
    ```
    trailing text
    """

    report = _extract_done_report_v1(summary)

    assert report == {"status": "verified", "score": 91, "provider": "amp"}


def test_record_quality_scores_uses_alternative_score_keys():
    tracker = _TrackerStub()
    summaries = [
        'DONE_REPORT_V1: {"quality_score": "88.5", "batch_id": "b1", "provider": "amp"}',
        'DONE_REPORT_V1: {"metrics": {"score": 77}, "task_id": "t2", "assignee": "openai"}',
    ]

    _record_quality_scores(tracker, round_no=6, summaries=summaries)

    assert len(tracker.calls) == 2
    assert tracker.calls[0]["batch_id"] == "b1"
    assert tracker.calls[0]["score"] == 88.5
    assert tracker.calls[1]["batch_id"] == "t2"
    assert tracker.calls[1]["score"] == 77.0


def test_record_quality_scores_skips_missing_score():
    tracker = _TrackerStub()

    _record_quality_scores(
        tracker,
        round_no=6,
        summaries=['DONE_REPORT_V1: {"batch_id": "b1", "provider": "amp"}'],
    )

    assert tracker.calls == []
