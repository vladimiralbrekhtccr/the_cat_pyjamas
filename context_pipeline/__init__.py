"""
Repository Context Pipeline

Generate comprehensive repository context for AI-powered code review.
"""

from .repo_analyzer import RepoAnalyzer
from .context_generator import ContextGenerator
from .repo_context_pipeline import ContextPipeline
from .llm_client import (
    BaseLLMClient,
    OpenAICompatibleClient,
    GeminiClient,
    create_llm_client
)
from .config import PipelineConfig, DEFAULT_CONFIG

__version__ = "1.0.0"
__all__ = [
    "RepoAnalyzer",
    "ContextGenerator",
    "ContextPipeline",
    "BaseLLMClient",
    "OpenAICompatibleClient",
    "GeminiClient",
    "create_llm_client",
    "PipelineConfig",
    "DEFAULT_CONFIG",
]
