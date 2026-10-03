"""Fourteen-stage synthetic native tool handoff tests; no agent or provider calls."""

import json

import pytest

from workbench.services.evaluation import Denied, digest, encoded
from workbench.services.evaluation_desktop_workflow import DIMENSIONS, STAGES, DesktopWorkflow
from workbench.services.evaluation_workflow import bibliography_markers, role_packet, role_result


@pytest.fixture
def run(tmp_path):
    inputs = {"inputs/manuscript.tex": b"ORIGINAL", "inputs/historical_verification_record.txt": b"RECORD"}
    return DesktopWorkflow.create(
        tmp_path / "pilot",
        inputs=inputs,
        expected={k: digest(v) for k, v in inputs.items()},
        brief="Neutral",
        authorization={
            "approved": True,
            "shared_access_accepted": True,
            "no_hard_credit_cap_accepted": True,
            "max_pilot_agents": 14,
            "model": "gpt-6-astra",
            "reasoning_effort": "high",
        },
        grading_reference={"marker": "HIDDEN_REFERENCE"},
    )


def result_for(packet, index):
    arm, role = STAGES[index]
    value = {"report": f"PRIVATE_{arm}_{role}"}
    if role in {"initial", "revision1", "revision2"}:
        value["candidate_tex"] = f"SOURCE_{arm}_{role}"
        if arm == "B1":
            value["records"] = (
                []
                if role == "initial"
                else [
                    {
                        "issue_id": packet["feedback"]["issues"][0]["id"],
                        "disposition": "unresolved",
                        "reason": "Synthetic",
                        "before_location": "1",
                        "after_location": "1",
                        "regression_check": "not run",
                    }
                ]
            )
    elif arm == "B1":
        if role == "final":
            value["verdicts"] = [
                {"issue_id": i, "status": "unresolved", "reason": "Synthetic", "regression_check": "not run"}
                for i in ("R1-1", "R2-1")
            ]
        else:
            value["issues"] = [
                {
                    "id": "R1-1" if role == "review1" else "R2-1",
                    "objection": "Synthetic",
                    "location": "1",
                    "evidence_sha256": [packet["candidate_sha256"]],
                }
            ]
    if arm == "grading":
        value.update(
            preference="tie", profiles={label: dict.fromkeys(DIMENSIONS, "U") for label in ("A", "B")}
        )
    return value


def begin(run):
    index = len(run.history()[0])
    prepared = run.prepare()
    agent = f"/root/{prepared['spawn']['task_name']}"
    identity = run.attach(agent, expected_dispatch_sha256=prepared["dispatch_sha256"])
    packet = json.loads((run._directory(index) / "packet.json").read_bytes())
    return (
        index,
        packet,
        {
            "observed_agent_id": agent,
            "completion_note": "Native completion observed",
            "expected_dispatch_sha256": prepared["dispatch_sha256"],
            "expected_identity_sha256": identity["identity_sha256"],
        },
    )


def test_full_native_sequence_and_order_swap(run):
    grading = []
    for _ in range(14):
        index, packet, evidence = begin(run)
        text = encoded(packet).decode()
        if index < 12:
            assert "HIDDEN_REFERENCE" not in text
            if index >= 6:
                assert "SOURCE_B0_" not in text and "PRIVATE_B0_" not in text
            if STAGES[index][1] in {"review1", "review2"}:
                arm = STAGES[index][0]
                assert f"PRIVATE_{arm}_initial" in text
                assert f"PRIVATE_{arm}_review1" not in text
                assert len(packet["author_reports"]) == (1 if STAGES[index][1] == "review1" else 2)
                for row in packet["evidence_artifacts"]:
                    assert row["sha256"] and row["path"].startswith("/")
            if STAGES[index][1] == "final":
                manifests = packet["earlier_packet_manifests"]
                revision1 = next(row for row in manifests if row["role"] == "revision1")
                assert any(
                    item["path"] == "/author_history/0/report"
                    for item in revision1["evidence_artifacts"]
                )
        else:
            assert "HIDDEN_REFERENCE" in text
            grading.append(packet["candidates"])
        (run._directory(index) / "submission.json").write_bytes(encoded(result_for(packet, index)))
        assert run.accept(**evidence)["accepted_stage"] == index
        run = DesktopWorkflow(
            run.root, expected_manifest_sha256=run._manifest_hash, expected_history_sha256=run._expected_tip
        )
    assert grading[0]["A"] == grading[1]["B"] and grading[0]["B"] == grading[1]["A"]
    with pytest.raises(Denied):
        run.prepare()
    assert len(run.history()[0]) == 14


def test_pending_spawn_cannot_repeat(run):
    run.prepare()
    with pytest.raises(FileExistsError):
        run.prepare()


@pytest.mark.parametrize("which", ["dispatch.json", "identity.json"])
def test_pending_identity_tampering_cannot_promote(run, which):
    index, packet, evidence = begin(run)
    (run._directory(index) / which).write_bytes(b"{}")
    (run._directory(index) / "submission.json").write_bytes(encoded(result_for(packet, index)))
    with pytest.raises(Denied):
        run.accept(**evidence)
    assert not (run._directory(index) / "receipt.json").exists()


def test_latest_receipt_cannot_drop_accepted_artifact(run):
    index, packet, evidence = begin(run)
    stage = run._directory(index)
    (stage / "submission.json").write_bytes(encoded(result_for(packet, index)))
    run.accept(**evidence)
    receipt = json.loads((stage / "receipt.json").read_bytes())
    del receipt["files"]["accepted.json"]
    (stage / "receipt.json").write_bytes(encoded(receipt))
    with pytest.raises(Denied):
        run.history()


def test_invalid_submission_stops_and_preserves_raw(run):
    index, _, evidence = begin(run)
    (run._directory(index) / "submission.json").write_bytes(b'{"report":"no candidate"}')
    with pytest.raises(Denied):
        run.accept(**evidence)
    assert (run.root / "stopped.json").is_file()
    assert (run._directory(index) / "raw-submission.json").is_file()
    with pytest.raises(Denied):
        run.prepare()


def test_final_verifier_can_cover_both_maximum_review_lists():
    prior = [{"issues": [{"id": f"R{round_}-{i}"} for i in range(1, 51)]} for round_ in (1, 2)]
    value = {
        "report": "Synthetic",
        "verdicts": [
            {
                "issue_id": item["id"],
                "status": "unresolved",
                "reason": "Synthetic",
                "regression_check": "None",
            }
            for review in prior
            for item in review["issues"]
        ],
    }
    output = role_result(
        json.dumps(value), expected={"inputs/manuscript.tex": "0" * 64}, prior=prior, arm="B1", role="final"
    )
    assert len(output["verdicts"]) == 100


def test_duplicate_candidate_key_denied(run):
    index, _, evidence = begin(run)
    (run._directory(index) / "submission.json").write_text(
        '{"report":"S","candidate_tex":"FIRST","candidate_tex":"SECOND"}'
    )
    with pytest.raises(ValueError):
        run.accept(**evidence)
    assert not (run._directory(index) / "receipt.json").exists()



@pytest.mark.parametrize("arm", ["B0", "B1"])
def test_paraphrased_false_absence_is_review_flag_not_blanket_rejection(arm):
    inputs = {"inputs/manuscript.tex": b"ORIGINAL"}
    expected = {key: digest(value) for key, value in inputs.items()}
    initial = {
        "role": "initial", "report": "An accompanying report with a finite check.",
        "candidate_tex": "BEFORE", "candidate_sha256": digest(b"BEFORE"),
    }
    review = {"role": "review1", "report": "Check provenance.", "issues": []}
    packet = role_packet(
        inputs=inputs, expected=expected, brief="Neutral", prior=[initial, review],
        arm=arm, role="revision1",
    )
    assert any(
        row["path"] == "/author_history/0/report"
        and row["sha256"] == digest(initial["report"].encode())
        for row in packet["evidence_artifacts"]
    )
    value = {
        "report": "No accompanying author report was provided with this packet.",
        "candidate_tex": (
            "The preceding candidate's referenced accompanying report is unavailable "
            "from the admitted evidence."
        ),
    }
    if arm == "B1":
        value["records"] = []
    output = role_result(
        json.dumps(value), expected=expected, prior=[initial, review],
        arm=arm, role="revision1", packet=packet,
    )
    assert output["diagnostic_status"] == "accepted"
    assert not output["release_eligibility"]["eligible"]
    assert any(not row["resolved"] for row in output["review_flags"])


def test_structured_availability_assertion_is_artifact_specific():
    initial = {
        "role": "initial", "report": "Supplied report.",
        "candidate_tex": "BEFORE", "candidate_sha256": digest(b"BEFORE"),
    }
    review = {"role": "review1", "report": "Review.", "issues": []}
    expected = {"inputs/manuscript.tex": "0" * 64}
    packet = role_packet(
        inputs={}, expected=expected, brief="Neutral", prior=[initial, review],
        arm="B0", role="revision1",
    )
    report_hash = next(
        row["sha256"] for row in packet["evidence_artifacts"]
        if row["path"] == "/author_history/0/report"
    )
    base = {
        "report": "Structured inventory assessment.",
        "candidate_tex": "AFTER",
        "historical_corrections": [],
    }
    output = role_result(
        json.dumps({
            **base,
            "evidence_assertions": [
                {
                    "packet_scope": "current",
                    "artifact_path": "/author_history/1/report",
                    "availability": "unavailable",
                    "artifact_sha256": None,
                },
                {
                    "packet_scope": "current",
                    "artifact_path": "/author_history/0/report",
                    "availability": "available",
                    "artifact_sha256": report_hash,
                },
            ],
        }),
        expected=expected, prior=[initial, review], arm="B0", role="revision1", packet=packet,
    )
    assert output["release_eligibility"]["eligible"]
    with pytest.raises(Denied, match="contradicted by packet"):
        role_result(
            json.dumps({
                **base,
                "evidence_assertions": [{
                    "packet_scope": "current",
                    "artifact_path": "/author_history/0/report",
                    "availability": "unavailable",
                    "artifact_sha256": None,
                }],
            }),
            expected=expected, prior=[initial, review], arm="B0", role="revision1", packet=packet,
        )


def test_bibliography_completion_marker_is_retained_without_invented_metadata():
    source = r"\begin{thebibliography}{99}" + "\n" + (
        r"\bibitem{ZhaoSTP} Bibliographic details to be checked before submission."
    ) + "\n" + r"\end{thebibliography}"
    markers = bibliography_markers(source)
    assert markers == [{"line": 2, "marker": "Bibliographic details to be checked"}]
    output = role_result(
        json.dumps({"report": "Source not verified.", "candidate_tex": source}),
        expected={"inputs/manuscript.tex": "0" * 64}, prior=[], arm="B0", role="initial",
    )
    assert output["bibliography_completion_markers"] == markers
    packet = role_packet(
        inputs={}, expected={"inputs/manuscript.tex": "0" * 64}, brief="Neutral",
        prior=[output], arm="B0", role="final",
    )
    final = role_result(
        json.dumps({"report": "Bibliography remains incomplete."}),
        expected={"inputs/manuscript.tex": "0" * 64}, prior=[output],
        arm="B0", role="final", packet=packet,
    )
    assert final["bibliography_completion_markers"] == markers
    assert final["diagnostic_status"] == "accepted"
    assert final["release_eligibility"] == {
        "eligible": False,
        "blockers": [{"code": "unresolved_bibliography_placeholders", "count": 1}],
    }



def test_final_verifier_scopes_and_corrects_historical_availability_claim():
    initial = {
        "role": "initial", "report": "Supplied author report.",
        "candidate_tex": "INITIAL", "candidate_sha256": digest(b"INITIAL"),
    }
    revision = {
        "role": "revision1", "report": "Revision narrative.",
        "candidate_tex": "The referenced accompanying report is absent.",
        "candidate_sha256": digest(b"The referenced accompanying report is absent."),
    }
    historical_sha = "1" * 64
    packet = role_packet(
        inputs={}, expected={"inputs/manuscript.tex": "0" * 64}, brief="Neutral",
        prior=[initial, revision], arm="B0", role="final",
        packet_history=[{
            "role": "revision1", "packet_sha256": historical_sha,
            "evidence_artifacts": [{
                "path": "/author_history/0/report", "kind": "author_report",
                "sha256": digest(initial["report"].encode()),
                "utf8_bytes": len(initial["report"].encode()),
            }],
        }],
    )
    uncorrected = role_result(
        json.dumps({"report": "Final check."}),
        expected={"inputs/manuscript.tex": "0" * 64},
        prior=[initial, revision], arm="B0", role="final", packet=packet,
    )
    assert uncorrected["diagnostic_status"] == "accepted"
    assert not uncorrected["release_eligibility"]["eligible"]
    historical_flag = next(
        row for row in uncorrected["review_flags"] if row["source_role"] == "revision1"
    )
    assert historical_flag["packet_scope"] == historical_sha
    assert not historical_flag["resolved"]

    corrected = role_result(
        json.dumps({
            "report": (
                'Revision1 said "the referenced report is absent"; that statement was incorrect. '
                "The report is present in its frozen packet."
            ),
            "evidence_assertions": [{
                "packet_scope": historical_sha,
                "artifact_path": "/author_history/0/report",
                "availability": "available",
                "artifact_sha256": digest(initial["report"].encode()),
            }],
            "historical_corrections": [{
                "source_role": "revision1",
                "packet_sha256": historical_sha,
                "artifact_path": "/author_history/0/report",
                "corrected_availability": "available",
                "reason": "The historical packet inventory contains the report bytes.",
            }],
        }),
        expected={"inputs/manuscript.tex": "0" * 64},
        prior=[initial, revision], arm="B0", role="final", packet=packet,
    )
    assert corrected["diagnostic_status"] == "accepted"
    assert corrected["release_eligibility"]["eligible"]
    assert corrected["review_flags"]
    assert all(row["resolved"] for row in corrected["review_flags"])


def test_historical_packet_scope_does_not_use_current_inventory():
    initial = {
        "role": "initial", "report": "Initial report.",
        "candidate_tex": "INITIAL", "candidate_sha256": digest(b"INITIAL"),
    }
    revision = {
        "role": "revision1", "report": "Revision.",
        "candidate_tex": "REVISION", "candidate_sha256": digest(b"REVISION"),
    }
    historical_sha = "2" * 64
    expected = {"inputs/manuscript.tex": "0" * 64}
    packet = role_packet(
        inputs={}, expected=expected, brief="Neutral", prior=[initial, revision],
        arm="B0", role="final",
        packet_history=[{
            "role": "revision1",
            "packet_sha256": historical_sha,
            "evidence_artifacts": [],
        }],
    )
    assert any(row["path"] == "/before_after_candidates/0/report"
               for row in packet["evidence_artifacts"])
    output = role_result(
        json.dumps({
            "report": "Scoped structured assessment.",
            "evidence_assertions": [{
                "packet_scope": historical_sha,
                "artifact_path": "/author_history/0/report",
                "availability": "unavailable",
                "artifact_sha256": None,
            }],
            "historical_corrections": [],
        }),
        expected=expected, prior=[initial, revision], arm="B0", role="final", packet=packet,
    )
    assert output["release_eligibility"]["eligible"]
