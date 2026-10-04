"""slopcore-factory: a headless lyrics-to-video factory.

The package turns a lyrics document (optionally plus a supplied audio track and a
background clip) into a complete, renderable HyperFrames project, then renders it
to MP4. It exists so the hand-authored motion design of ``please-continue-video``
can be reproduced for any song without touching the HyperFrames Studio UI.

Public entry point is the ``slopcore_factory`` console script (``slopcore_factory.cli:main``).
"""

from __future__ import annotations

__version__ = "0.1.0"
