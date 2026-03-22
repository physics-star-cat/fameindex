"""
Data pipeline package.

Provides data collection from external sources, normalisation, and
the orchestrator that ties it all together.
"""

from server.data.pipeline import run_pipeline

__all__ = ["run_pipeline"]
