from pathlib import Path


def test_required_sample_directories_exist() -> None:
    assert Path("data/resumes").is_dir()
    assert Path("data/job_descriptions").is_dir()


def test_sample_dataset_is_available() -> None:
    resumes = [path for path in Path("data/resumes").iterdir() if path.is_file()]
    job_descriptions = [
        path for path in Path("data/job_descriptions").iterdir() if path.is_file()
    ]

    assert len(resumes) >= 30
    assert len(job_descriptions) >= 6


def test_required_documentation_deliverables_exist() -> None:
    assert Path("README.md").is_file()
    assert Path("docs/state_machine.md").is_file()
    assert Path("docs/test_scenarios.md").is_file()
    assert Path("docs/demo_script.md").is_file()
    assert Path("scripts/ingest_resumes.py").is_file()
