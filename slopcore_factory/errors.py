"""Exception hierarchy for slopcore-factory.

All errors raised intentionally by the package derive from :class:`SlopcoreFactoryError`
so the CLI can render a clean message instead of a traceback, while tests can
assert on a single base type.
"""

from __future__ import annotations


class SlopcoreFactoryError(Exception):
    """Base class for every intentional error in slopcore-factory."""


class ConfigError(SlopcoreFactoryError):
    """The factory spec / config file is missing or malformed."""


class LyricsParseError(SlopcoreFactoryError):
    """The lyrics document could not be parsed into sections and lines."""


class AudioError(SlopcoreFactoryError):
    """No usable audio track was found and generation was not requested."""


class AlignmentError(SlopcoreFactoryError):
    """Lyric lines could not be aligned to the audio transcript."""


class SongGenerationError(SlopcoreFactoryError):
    """The optional Suno song generation step failed."""


class ClipGenerationError(SlopcoreFactoryError):
    """The optional Seedance clip generation step failed."""


class MediaError(SlopcoreFactoryError):
    """Background media could not be prepared."""


class ComposeError(SlopcoreFactoryError):
    """Composition HTML could not be generated."""


class RenderError(SlopcoreFactoryError):
    """A subprocess (hyperframes / ffmpeg) failed."""


class BudgetError(SlopcoreFactoryError):
    """A paid step would exceed the configured budget cap."""


class BlueprintError(SlopcoreFactoryError):
    """The blueprint is malformed or fails validation."""


class LLMError(SlopcoreFactoryError):
    """The storyboard LLM is unavailable or returned an unusable blueprint."""
