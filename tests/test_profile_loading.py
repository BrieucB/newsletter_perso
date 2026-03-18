from __future__ import annotations

from app.settings import load_settings


def test_load_settings_includes_explicit_profile_and_local_repo_config() -> None:
    settings = load_settings()

    assert settings.explicit_profile.tone == "mentor_note_to_self"
    assert settings.explicit_profile.target_ratio.current_work == 0.5
    assert settings.repo_profiling.enabled is True
    assert [repo.name for repo in settings.local_repos] == ["Korali", "Mirheo", "UQ_DPD"]
