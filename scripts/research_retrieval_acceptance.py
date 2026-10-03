"""Exercise retrieval and exclusive item allocation in a fresh synthetic local project."""

import argparse
import json
import os
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    output = args.output.resolve()
    os.environ.update(WB_LOAD_DOTENV="false", WB_DATABASE_URL="sqlite:///" +
                      (output / "synthetic.sqlite3").as_posix(), WB_DATA_DIR=str(output / "data"),
                      WB_PROVIDER_MODE="fake", WB_LLM_PROVIDER="openai", WB_AUTH_REQUIRED="false",
                      WB_DEPLOYMENT_MODE="local", WB_RESEARCH_EXECUTOR_ENABLED="false")
    from fastapi.testclient import TestClient

    from workbench import config, db

    config.get_settings.cache_clear()
    db.reset_engine_for_tests()
    from workbench.main import app

    with TestClient(app) as client:
        def post(path, **kwargs):
            response = client.post(path, **kwargs)
            response.raise_for_status()
            return response.json()

        def run(root, task):
            url = root + "/research-tasks/" + task["id"]
            post(url + "/start", json={})
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                result = client.get(url).json()
                if result["state"] == "completed":
                    return result
                if result["state"].endswith("partial"):
                    raise AssertionError(result["ledger"])
                time.sleep(0.1)
            raise AssertionError("Synthetic worker timed out")

        workspace = post("/workspaces", json={"name": "Synthetic retrieval acceptance"})
        project = post("/projects", json={"workspace_id": workspace["id"], "name": "Coverage demo"})
        root = "/projects/" + project["id"]
        task = post(root + "/research-tasks", json={"question": "Finite topology and asymmetric refinement",
                                                    "max_children": 2})
        for name, text in [("topology.txt", "Finite topology from ultrametric balls."),
                           ("asymmetric.txt", "Asymmetric refinement and directed counterexamples.")]:
            post(root + "/research-tasks/" + task["id"] + "/attachments",
                 files={"file": (name, text.encode())}, data={"version": "synthetic fixture v1"})
        run(root, task)
        query = "Finite topology asymmetric refinement counterexamples"
        topics = ["finite topology", "asymmetric refinement", "unseen astronomy"]
        preview = post(root + "/research-retrieval", json={"query": query, "topics": topics})
        next_task = post(root + "/research-tasks", json={"question": query,
            "coverage_topics": topics, "reuse_prior_research": True, "max_children": 2})
        result = run(root, next_task)
        allocation = result["ledger"]["retrieval_allocation"]
        owned = [item for lane in allocation.values() for item in lane]
        assert len(owned) == len(set(owned)) == len(preview["cards"])
        assert not preview["coverage"][-1]["matching_card_ids"]
        assert result["ledger"]["actual_tokens"] == 0
        for name, data in [("retrieval-preview.json", preview), ("allocation.json", allocation),
                           ("verification.json", {"project_id": project["id"], "task_id": result["id"],
                            "simulation": True, "unique_owned_items": len(owned),
                            "actual_model_tokens": 0, "state": result["state"],
                            "snapshot_hash": preview["snapshot_hash"], "owner_database_accessed": False})]:
            (output / name).write_text(json.dumps(data, indent=2), encoding="utf-8")
    db.reset_engine_for_tests()
    print(output)


if __name__ == "__main__":
    main()
