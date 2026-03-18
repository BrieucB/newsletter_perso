from __future__ import annotations

import json
from typing import Any, cast

from app.profile.learning import learn_from_feedback
from app.profile.models import AggregatedRepoProfile, RuntimeProfileContext
from app.profile.repo_profile import (
    aggregate_repo_profiles,
    build_repo_profile,
    ensure_local_clone,
    scan_repo,
)
from app.repositories.feedback import FeedbackRepository
from app.repositories.profiles import ProfilesRepository
from app.settings import AppSettings, ExplicitProfileConfig


class ProfileService:
    def __init__(
        self,
        settings: AppSettings,
        *,
        profiles_repo: ProfilesRepository,
        feedback_repo: FeedbackRepository,
    ) -> None:
        self.settings = settings
        self.profiles_repo = profiles_repo
        self.feedback_repo = feedback_repo

    def ensure_explicit_profile(self) -> None:
        active = self.profiles_repo.get_active_user_profile()
        current_json = self.settings.explicit_profile.model_dump()
        if active is not None and json.loads(active["profile_json"]) == current_json:
            return
        self.profiles_repo.replace_active_user_profile(current_json)

    def load_runtime_context(self) -> RuntimeProfileContext:
        explicit = self.profiles_repo.get_active_user_profile()
        explicit_profile = (
            self.settings.explicit_profile
            if explicit is None
            else ExplicitProfileConfig.model_validate_json(explicit["profile_json"])
        )
        repo_profiles = self.profiles_repo.list_active_repo_profiles()
        aggregated_repo_profile = (
            AggregatedRepoProfile()
            if not repo_profiles
            else aggregate_repo_profiles(
                [self.profiles_repo.row_to_repo_profile(row) for row in repo_profiles]
            )
        )
        snapshot = self.profiles_repo.get_latest_profile_snapshot()
        if snapshot is None:
            feedback_rows = self.feedback_repo.list_feedback_contexts()
            learned_preferences = learn_from_feedback(
                feedback_rows,
                adaptation_strength=explicit_profile.feedback_adaptation_strength,
            )
        else:
            learned_preferences = self.profiles_repo.snapshot_learned_preferences(snapshot)
        return RuntimeProfileContext(
            explicit_profile=explicit_profile,
            aggregated_repo_profile=aggregated_repo_profile,
            learned_preferences=learned_preferences,
        )

    def refresh_profiles(self) -> RuntimeProfileContext:
        self.ensure_explicit_profile()
        repo_profiles = []

        if self.settings.repo_profiling.enabled:
            for repo in self.settings.local_repos:
                if not repo.enabled:
                    continue
                resolved_path = ensure_local_clone(
                    repo_path=self.settings.resolve_repo_path(repo),
                    clone_url=repo.clone_url,
                )
                scan_result = scan_repo(
                    resolved_path,
                    repo_name=repo.name,
                    ignore_dirs=self.settings.local_repo_ignore_dirs,
                    ignore_file_globs=self.settings.local_repo_ignore_file_globs,
                )
                repo_profiles.append(build_repo_profile(scan_result))

        self.profiles_repo.replace_active_repo_profiles(repo_profiles)
        aggregated = aggregate_repo_profiles(repo_profiles)
        feedback_rows = self.feedback_repo.list_feedback_contexts()
        learned = learn_from_feedback(
            feedback_rows,
            adaptation_strength=self.settings.explicit_profile.feedback_adaptation_strength,
        )
        self.profiles_repo.create_profile_snapshot(
            explicit_profile_json=self.settings.explicit_profile.model_dump(),
            aggregated_repo_profile_json=aggregated.model_dump(),
            learned_preferences_json=learned.model_dump(),
        )
        return RuntimeProfileContext(
            explicit_profile=self.settings.explicit_profile,
            aggregated_repo_profile=aggregated,
            learned_preferences=learned,
        )

    def describe_context(self) -> dict[str, Any]:
        context = self.load_runtime_context()
        return cast(dict[str, Any], json.loads(context.model_dump_json()))

    def rebuild_snapshot_from_feedback(self) -> None:
        self.ensure_explicit_profile()
        repo_profiles = [
            self.profiles_repo.row_to_repo_profile(row)
            for row in self.profiles_repo.list_active_repo_profiles()
        ]
        aggregated = aggregate_repo_profiles(repo_profiles)
        feedback_rows = self.feedback_repo.list_feedback_contexts()
        learned = learn_from_feedback(
            feedback_rows,
            adaptation_strength=self.settings.explicit_profile.feedback_adaptation_strength,
        )
        self.profiles_repo.create_profile_snapshot(
            explicit_profile_json=self.settings.explicit_profile.model_dump(),
            aggregated_repo_profile_json=aggregated.model_dump(),
            learned_preferences_json=learned.model_dump(),
        )
