"""Run one synthetic, no-network container compute check against a cached image.

This never touches the configured workbench database or research artifacts: it creates a
temporary data directory, database, project, script, and output, then removes them on exit.
The image must already exist locally and must be supplied by registry digest.
"""

import argparse
import json
import os
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="paper-workbench-container-check-") as temporary:
        root = Path(temporary)
        os.environ["WB_PROVIDER_MODE"] = "fake"
        os.environ["WB_DATA_DIR"] = str(root / "data")
        os.environ["WB_DATABASE_URL"] = f"sqlite:///{root / 'check.sqlite3'}"

        from workbench import config, db
        from workbench.ingest.files import ingest_file
        from workbench.services import compute, research

        config.get_settings.cache_clear()
        db.reset_engine_for_tests()
        db.create_all()
        session = db.session_factory()()
        try:
            workspace = research.create_workspace(session, "Container verification")
            project = research.create_project(session, workspace.id, "Synthetic check")
            script_path = root / "check.py"
            script_path.write_text(
                """import json
import os
import socket
from pathlib import Path

try:
    import numpy
    numpy_version = numpy.__version__
except ImportError:
    numpy_version = None

result = {
    "seed": os.environ["WB_COMPUTE_SEED"],
    "network_policy": os.environ["WB_COMPUTE_NETWORK_POLICY"],
    "numpy_version": numpy_version,
    "hostname": socket.gethostname(),
}
Path(os.environ["WB_COMPUTE_OUTPUT_DIR"], "verification.json").write_text(
    json.dumps(result, sort_keys=True), encoding="utf-8"
)
print(json.dumps(result, sort_keys=True))
""",
                encoding="utf-8",
            )
            script = ingest_file(session, project.id, script_path)
            run = compute.create_run(
                session,
                project.id,
                script_source_id=script.id,
                executor="docker",
                container_image=args.image,
                timeout_seconds=30,
                memory_mb=512,
                cpus=1.0,
                pids_limit=32,
                seed=23,
            )
            compute.approve_run(
                session,
                run.id,
                plan_hash=run.plan_hash,
                review_note="synthetic container verification",
                acknowledge_unenforced_isolation=True,
            )
            compute.execute_run(
                session,
                run.id,
                plan_hash=run.plan_hash,
                confirm_local_execution=True,
            )
            if str(run.state) != "succeeded":
                raise RuntimeError(json.dumps(run.execution, indent=2))
            if not all(
                run.execution[name]
                for name in (
                    "network_isolation_enforced",
                    "filesystem_isolation_enforced",
                    "descendant_process_containment_enforced",
                    "resource_limits_enforced",
                )
            ):
                raise RuntimeError("container execution did not record every enforced boundary")
            payload = json.loads(Path(run.outputs[0]["artifact_path"]).read_text(encoding="utf-8"))
            if payload["seed"] != "23" or payload["network_policy"] != "enforced_offline_container":
                raise RuntimeError(f"unexpected container output: {payload}")
            print(
                json.dumps(
                    {
                        "status": "passed",
                        "image": args.image,
                        "plan_hash": run.plan_hash,
                        "manifest_hash": run.execution["manifest_hash"],
                        "output_sha256": run.outputs[0]["sha256"],
                        "numpy_version": payload["numpy_version"],
                        "network_policy": payload["network_policy"],
                    },
                    indent=2,
                )
            )
        finally:
            session.close()
            db.reset_engine_for_tests()
            config.get_settings.cache_clear()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
