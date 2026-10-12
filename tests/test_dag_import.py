"""
DAG import/parse test that runs without MWAA.
This test validates that all DAGs can be imported without errors,
catching syntax errors and import issues before spending environment time.
"""

import sys
import os
from pathlib import Path

# Add the orchestration/dags directory to the path
DAGS_DIR = Path(__file__).parent.parent / "orchestration" / "dags"


def test_dag_imports():
    """Test that all DAG files in orchestration/dags can be imported without errors."""
    dag_files = list(DAGS_DIR.glob("*.py"))
    assert dag_files, f"No DAG files found in {DAGS_DIR}"

    errors = []
    for dag_file in dag_files:
        if dag_file.name.startswith("__"):
            continue
        try:
            # Execute the DAG file to trigger imports and DAG instantiation
            # This mimics what Airflow's DagBag does during parsing
            namespace = {}
            with open(dag_file, "r") as f:
                code = compile(f.read(), str(dag_file), "exec")
                exec(code, namespace)

            # Verify at least one DAG object was created
            dag_objects = [v for v in namespace.values() if hasattr(v, "dag_id")]
            assert dag_objects, f"No DAG objects found in {dag_file.name}"

            for dag in dag_objects:
                assert hasattr(dag, "dag_id"), f"Invalid DAG object in {dag_file.name}"
                assert dag.dag_id, f"DAG missing dag_id in {dag_file.name}"

        except Exception as e:
            errors.append(f"{dag_file.name}: {type(e).__name__}: {e}")

    assert not errors, "DAG import errors:\n" + "\n".join(errors)


def test_hello_world_dag_structure():
    """Specific test for hello_world DAG structure."""
    hello_world_path = DAGS_DIR / "hello_world.py"
    assert hello_world_path.exists(), "hello_world.py not found"

    namespace = {}
    with open(hello_world_path, "r") as f:
        code = compile(f.read(), str(hello_world_path), "exec")
        exec(code, namespace)

    # Find the DAG object
    dag = None
    for v in namespace.values():
        if hasattr(v, "dag_id") and v.dag_id == "hello_world":
            dag = v
            break

    assert dag is not None, "hello_world DAG not found"

    # Verify basic structure
    assert dag.dag_id == "hello_world"
    assert dag.schedule == "@once"
    assert dag.catchup is False
    assert dag.is_paused_upon_creation is False

    # Verify tasks exist
    task_ids = {task.task_id for task in dag.tasks}
    assert "read_variable_and_write_s3" in task_ids, "Expected task not found"