from __future__ import annotations

from pathlib import Path

from app.profile.repo_profile import aggregate_repo_profiles, build_repo_profile, scan_repo

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "repos"


def test_build_repo_profile_extracts_hpc_and_uq_markers() -> None:
    scan_result = scan_repo(
        FIXTURE_ROOT / "korali_like",
        repo_name="Korali",
        ignore_dirs=[".git", ".venv", "build", "dist"],
        ignore_file_globs=["*.png", "*.jpg", "*.pdf"],
    )

    profile = build_repo_profile(scan_result)

    assert "python" in profile.detected_languages
    assert "bayesian inference" in profile.inferred_scientific_domains
    assert "calibration" in profile.inferred_scientific_domains
    assert "gpu computing" in profile.inferred_engineering_themes
    assert "SLURM" in profile.workflow_markers


def test_aggregate_repo_profiles_merges_keywords_across_fixture_repos() -> None:
    profiles = []
    for repo_name in ("korali_like", "mirheo_like", "uq_dpd_like"):
        scan_result = scan_repo(
            FIXTURE_ROOT / repo_name,
            repo_name=repo_name,
            ignore_dirs=[".git", ".venv", "build", "dist"],
            ignore_file_globs=["*.png", "*.jpg", "*.pdf"],
        )
        profiles.append(build_repo_profile(scan_result))

    aggregated = aggregate_repo_profiles(profiles)

    assert aggregated.repo_count == 3
    assert "bayesian inference" in aggregated.scientific_domains
    assert "gpu computing" in aggregated.engineering_themes
    assert "SLURM" in aggregated.workflow_markers
    assert aggregated.summary
