import pytest

from codex_auto.config import GitHubConfig
from codex_auto.github import GitHubAdapterError, LocalGitHubAdapter


def make_adapter(*, allow_deletions=False):
    adapter = object.__new__(LocalGitHubAdapter)
    adapter.config = GitHubConfig(
        repository="owner/repo",
        allowed_paths=["src/**"],
        forbidden_paths=["src/secrets/**"],
        allow_deletions=allow_deletions,
    )
    return adapter


def test_patch_policy_accepts_declared_allowed_text_path():
    patch = (
        "diff --git a/src/app.py b/src/app.py\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1 +1 @@\n-old\n+new\n"
    )

    assert make_adapter()._paths_from_patch(patch) == ["src/app.py"]


def test_patch_policy_rejects_forbidden_path():
    patch = (
        "diff --git a/src/secrets/key.py b/src/secrets/key.py\n"
        "--- a/src/secrets/key.py\n"
        "+++ b/src/secrets/key.py\n"
    )

    with pytest.raises(GitHubAdapterError, match="not allowed"):
        make_adapter()._paths_from_patch(patch)


def test_default_policy_rejects_root_secret_key():
    adapter = object.__new__(LocalGitHubAdapter)
    adapter.config = GitHubConfig(repository="owner/repo")

    assert adapter._is_allowed("production.key") is False
    assert adapter._is_allowed(".agents/skills/codex-auto/SKILL.md") is False
    assert adapter._is_allowed(".codex/config.toml") is False
    assert adapter._is_allowed(".github/workflows/ci.yml") is False
    assert adapter._is_allowed(".codex-auto/project.yml") is False


def test_patch_policy_rejects_deletion_by_default():
    patch = "diff --git a/src/app.py b/src/app.py\n--- a/src/app.py\n+++ /dev/null\n"

    with pytest.raises(GitHubAdapterError, match="deletion is disabled"):
        make_adapter()._paths_from_patch(patch)


def test_patch_policy_rejects_deletion_header_with_timestamp():
    patch = (
        "diff --git a/src/app.py b/src/app.py\n"
        "--- a/src/app.py\t2026-08-24 10:00:00\n"
        "+++ /dev/null\t2026-08-24 10:00:00\n"
    )

    with pytest.raises(GitHubAdapterError, match="deletion is disabled"):
        make_adapter()._paths_from_patch(patch)


def test_patch_policy_validates_every_unified_diff_header_before_apply():
    patch = (
        "diff --git a/src/app.py b/src/app.py\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1 +1 @@\n-old\n+new\n"
        "--- a/src/secrets/key.py\n"
        "+++ b/src/secrets/key.py\n"
        "@@ -1 +1 @@\n-old\n+new\n"
    )

    with pytest.raises(GitHubAdapterError, match="not allowed"):
        make_adapter()._paths_from_patch(patch)


def test_patch_policy_rejects_symlinks_and_binary_patches():
    with pytest.raises(GitHubAdapterError, match="symbolic-link"):
        make_adapter()._paths_from_patch("diff --git a/src/link b/src/link\nnew file mode 120000\n")
    with pytest.raises(GitHubAdapterError, match="binary"):
        make_adapter()._paths_from_patch("diff --git a/src/a.bin b/src/a.bin\nGIT binary patch\n")
