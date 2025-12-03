"""
Configuration options for the context pipeline
"""
import os
from dataclasses import dataclass
from typing import Set


@dataclass
class PipelineConfig:
    """Configuration for repository context pipeline"""
    
    # LLM Settings
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"
    
    # File Analysis Limits
    max_file_size_kb: int = 100
    max_total_files: int = 100
    
    # Temperature for LLM generation (0.0 - 1.0, lower = more focused)
    llm_temperature: float = 0.1
    
    # Maximum output tokens for LLM
    max_output_tokens: int = 4000
    
    # Custom file extensions to include (beyond defaults)
    custom_code_extensions: Set[str] = None
    custom_doc_extensions: Set[str] = None
    
    # Additional directories to ignore
    custom_ignore_dirs: Set[str] = None
    
    # Whether to include test files in analysis
    include_tests: bool = True
    
    @classmethod
    def from_env(cls):
        """Load configuration from environment variables"""
        return cls(
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
            max_file_size_kb=int(os.getenv("MAX_FILE_SIZE_KB", "100")),
            max_total_files=int(os.getenv("MAX_TOTAL_FILES", "100")),
        )


# Default configuration
DEFAULT_CONFIG = PipelineConfig()
