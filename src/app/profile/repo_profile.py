from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

from app.profile.models import AggregatedRepoProfile, RepoProfile, RepoScanResult
from app.utils.hashing import stable_hash
from app.utils.text import clean_whitespace

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".cu": "cuda",
    ".cuh": "cuda",
    ".h": "cpp_headers",
    ".hpp": "cpp_headers",
    ".md": "markdown",
    ".ipynb": "notebook",
    ".sh": "shell",
    ".slurm": "slurm",
    ".sbatch": "slurm",
    ".cmake": "cmake",
}

PATTERN_GROUPS = {
    "scientific_domains": {
        "bayesian inference": ["bayesian", "mcmc", "tmcmc", "posterior", "inference"],
        "calibration": ["calibration", "inverse problem", "inverse", "calibrate"],
        "surrogate modeling": ["surrogate", "gaussian process", "emulator", "neural operator"],
        "particle simulation": ["particle", "dpd", "microbubble", "mirheo"],
        "multi-physics": ["multi-physics", "multiphysics", "multi physics"],
        "multi-scale": ["multi-scale", "multiscale", "coupling"],
    },
    "engineering_themes": {
        "gpu computing": ["gpu", "cuda", "nvidia"],
        "hpc scaling": ["hpc", "mpi", "parallel", "distributed"],
        "experiment pipelines": ["workflow", "pipeline", "reproducibility", "benchmark"],
        "simulation workflows": ["simulation", "solver", "physics-informed"],
    },
    "infra_themes": {
        "slurm orchestration": ["slurm", "sbatch", "srun"],
        "cmake builds": ["cmakelists", "cmake"],
        "python tooling": ["pyproject.toml", "requirements.txt", "environment.yml"],
        "containerization": ["docker", "container"],
    },
    "tools": {
        "mpi": ["mpi", "mpi4py"],
        "cuda": ["cuda", "cublas", "cudnn"],
        "cmake": ["cmake"],
        "slurm": ["slurm", "sbatch", "srun"],
        "pybind11": ["pybind11"],
        "numpy": ["numpy"],
        "scipy": ["scipy"],
        "torch": ["torch", "pytorch"],
    },
    "markers": {
        "MPI": ["mpi", "mpi4py"],
        "GPU/CUDA": ["gpu", "cuda"],
        "SLURM": ["slurm", "sbatch", "srun"],
        "Bayesian inference": ["bayesian", "mcmc", "tmcmc", "posterior"],
        "calibration": ["calibration", "calibrate"],
        "TMCMC / MCMC": ["tmcmc", "mcmc"],
        "surrogate modeling": ["surrogate", "gaussian process", "emulator"],
        "particle simulation": ["particle", "dpd", "mirheo"],
        "multi-physics": ["multi-physics", "multiphysics"],
        "HPC orchestration": ["slurm", "workflow", "pipeline"],
        "reproducibility / experiment pipelines": ["reproducibility", "experiment", "benchmark"],
    },
}

TEXT_FILE_NAMES = {
    "readme.md",
    "readme",
    "requirements.txt",
    "pyproject.toml",
    "environment.yml",
    "environment.yaml",
    "cmakelists.txt",
}


def _top(counter: dict[str, int], limit: int = 8) -> list[str]:
    return [key for key, _ in Counter(counter).most_common(limit)]


def ensure_local_clone(*, repo_path: Path, clone_url: str | None) -> Path:
    if repo_path.exists():
        return repo_path
    if not clone_url:
        raise FileNotFoundError(
            "Local repo path does not exist and no clone_url was provided: "
            f"{repo_path}"
        )
    repo_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", clone_url, str(repo_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return repo_path


def _should_skip(path: Path, *, ignore_dirs: set[str], ignore_suffixes: set[str]) -> bool:
    return any(part in ignore_dirs for part in path.parts) or path.suffix.lower() in ignore_suffixes


def _read_text_fragments(path: Path) -> list[str]:
    if path.suffix.lower() == ".ipynb":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        fragments: list[str] = []
        for cell in payload.get("cells", [])[:5]:
            source = cell.get("source", [])
            if isinstance(source, list):
                fragments.append(" ".join(source))
        return [clean_whitespace(fragment) for fragment in fragments if clean_whitespace(fragment)]

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    normalized = clean_whitespace(text)
    return [normalized[:4000]] if normalized else []


def _collect_git_messages(repo_path: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "log", "--oneline", "-n", "12"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return []
    return [clean_whitespace(line) for line in result.stdout.splitlines() if clean_whitespace(line)]


def scan_repo(
    repo_path: Path,
    *,
    repo_name: str,
    ignore_dirs: list[str],
    ignore_file_globs: list[str],
) -> RepoScanResult:
    ignore_dir_set = set(ignore_dirs)
    ignore_suffixes = {
        Path(pattern).suffix.lower()
        for pattern in ignore_file_globs
        if pattern.startswith("*.")
    }
    result = RepoScanResult(repo_name=repo_name, repo_path=repo_path)

    for path in repo_path.rglob("*"):
        if not path.is_file() or _should_skip(
            path,
            ignore_dirs=ignore_dir_set,
            ignore_suffixes=ignore_suffixes,
        ):
            continue

        result.file_names.append(path.name.lower())
        language = LANGUAGE_BY_SUFFIX.get(path.suffix.lower())
        if language:
            result.languages[language] = result.languages.get(language, 0) + 1

        should_read = (
            path.name.lower() in TEXT_FILE_NAMES
            or path.suffix.lower()
            in {".md", ".py", ".cpp", ".cu", ".ipynb", ".txt", ".slurm", ".sbatch"}
            or any(part in {"docs", "scripts"} for part in path.parts)
        )
        if should_read:
            result.text_fragments.extend(_read_text_fragments(path))

    result.commit_messages = _collect_git_messages(repo_path)
    haystack = " ".join(result.file_names + result.text_fragments + result.commit_messages).lower()

    for bucket_name, patterns in PATTERN_GROUPS.items():
        target = getattr(result, bucket_name)
        for label, keywords in patterns.items():
            matches = sum(haystack.count(keyword) for keyword in keywords)
            if matches > 0:
                target[label] = matches

    return result


def build_repo_profile(scan_result: RepoScanResult) -> RepoProfile:
    keywords = (
        _top(scan_result.scientific_domains, limit=4)
        + _top(scan_result.engineering_themes, limit=4)
        + _top(scan_result.infra_themes, limit=4)
        + _top(scan_result.markers, limit=6)
    )
    summary_parts = [
        f"{scan_result.repo_name} looks like a "
        f"{', '.join(_top(scan_result.languages, limit=3)) or 'mixed-language'} project.",
    ]
    if scan_result.scientific_domains:
        summary_parts.append(
            "Scientific focus: " + ", ".join(_top(scan_result.scientific_domains, limit=3)) + "."
        )
    if scan_result.engineering_themes:
        summary_parts.append(
            "Engineering themes: " + ", ".join(_top(scan_result.engineering_themes, limit=3)) + "."
        )
    if scan_result.infra_themes:
        summary_parts.append(
            "Infrastructure markers: " + ", ".join(_top(scan_result.infra_themes, limit=3)) + "."
        )

    fingerprint_hash = stable_hash(
        [
            scan_result.repo_name,
            str(scan_result.repo_path),
            *scan_result.file_names[:100],
            *scan_result.commit_messages[:12],
            *scan_result.text_fragments[:20],
        ]
    )
    confidence_by_theme = {
        theme: min(score / 5.0, 1.0)
        for theme, score in {
            **scan_result.scientific_domains,
            **scan_result.engineering_themes,
            **scan_result.infra_themes,
        }.items()
    }
    return RepoProfile(
        repo_name=scan_result.repo_name,
        repo_path=str(scan_result.repo_path),
        detected_languages=_top(scan_result.languages, limit=5),
        detected_libraries_tools=_top(scan_result.tools, limit=8),
        inferred_scientific_domains=_top(scan_result.scientific_domains, limit=6),
        inferred_engineering_themes=_top(scan_result.engineering_themes, limit=6),
        inferred_infra_themes=_top(scan_result.infra_themes, limit=6),
        workflow_markers=_top(scan_result.markers, limit=8),
        summary=" ".join(summary_parts),
        keywords=list(dict.fromkeys(keywords)),
        confidence_by_theme=confidence_by_theme,
        fingerprint_hash=fingerprint_hash,
    )


def aggregate_repo_profiles(repo_profiles: list[RepoProfile]) -> AggregatedRepoProfile:
    if not repo_profiles:
        return AggregatedRepoProfile()

    scientific: Counter[str] = Counter()
    engineering: Counter[str] = Counter()
    infra: Counter[str] = Counter()
    markers: Counter[str] = Counter()
    tools: Counter[str] = Counter()
    languages: Counter[str] = Counter()
    keywords: Counter[str] = Counter()

    for profile in repo_profiles:
        scientific.update(profile.inferred_scientific_domains)
        engineering.update(profile.inferred_engineering_themes)
        infra.update(profile.inferred_infra_themes)
        markers.update(profile.workflow_markers)
        tools.update(profile.detected_libraries_tools)
        languages.update(profile.detected_languages)
        keywords.update(profile.keywords)

    top_scientific = [name for name, _ in scientific.most_common(3)] or ["computational science"]
    top_engineering = [name for name, _ in engineering.most_common(3)] or ["tooling"]
    top_markers = [name for name, _ in markers.most_common(3)] or ["repeatable workflows"]
    summary = (
        "Your repo fingerprint centers on "
        f"{', '.join(top_scientific)}, "
        f"with engineering emphasis on "
        f"{', '.join(top_engineering)} "
        f"and infrastructure markers around "
        f"{', '.join(top_markers)}."
    )
    return AggregatedRepoProfile(
        repo_count=len(repo_profiles),
        scientific_domains=[name for name, _ in scientific.most_common(8)],
        engineering_themes=[name for name, _ in engineering.most_common(8)],
        infra_themes=[name for name, _ in infra.most_common(8)],
        workflow_markers=[name for name, _ in markers.most_common(10)],
        libraries_tools=[name for name, _ in tools.most_common(10)],
        dominant_languages=[name for name, _ in languages.most_common(5)],
        summary=summary,
        keyword_weights={name: float(score) for name, score in keywords.most_common(20)},
    )
