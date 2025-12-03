# Repository Context Pipeline

Generate comprehensive repository context files using LLM analysis for better understanding of codebases.

## Overview

This pipeline analyzes git repositories (local or remote) and generates structured context files that summarize:
- Project purpose and architecture
- Tech stack and dependencies
- Code organization and conventions
- Key files and their roles

The context is generated using your choice of LLM (OpenAI-compatible API or Google Gemini).

## Features

- **Flexible LLM Support**: Use OpenAI-compatible endpoints (like Qwen) or Google Gemini
- **Git Repository Analysis**: Clone from URLs or analyze local paths
- **SSH Support**: Works with SSH URLs for private repositories
- **Smart File Filtering**: Automatically identifies and prioritizes important files
- **Configurable Limits**: Control file size and count to manage LLM token usage
- **CLI Interface**: Easy-to-use command-line interface

## Installation

```bash
# From the_cat_pyjamas root directory
pip install -r requirements.txt
```

Dependencies already in `requirements.txt`:
- `google-genai` - For Gemini support
- `openai` - For OpenAI-compatible APIs
- `python-gitlab` - Already installed
- `dotenv` - Already installed

## Quick Start

### Using OpenAI-Compatible LLM (e.g., Qwen)

```bash
cd context_pipeline

python repo_context_pipeline.py \
  --repo-url https://github.com/user/repo \
  --output context.txt \
  --provider openai \
  --base-url http://10.201.24.88:6655/v1 \
  --model qwen3_30b_deployed
```

### Using Google Gemini

```bash
# Set API key in environment
export GEMINI_API_KEY="your-api-key"

python repo_context_pipeline.py \
  --repo-url https://github.com/user/repo \
  --output context.txt \
  --provider gemini
```

### Using SSH for Private Repos

For private repositories, use SSH URLs directly:

```bash
python repo_context_pipeline.py \
  --repo-url git@github.com:user/private-repo.git \
  --output context.txt \
  --provider openai \
  --base-url http://10.201.24.88:6655/v1 \
  --model qwen3_30b_deployed
```

**Note:** Make sure your SSH keys are configured with GitHub:
```bash
ssh -T git@github.com
```

### Analyzing Local Repositories

```bash
python repo_context_pipeline.py \
  --repo-path /path/to/your/repo \
  --output context.txt \
  --provider openai \
  --base-url http://10.201.24.88:6655/v1 \
  --model qwen3_30b_deployed
```

## CLI Options

### Required Arguments

- `--repo-url URL` - Git repository URL to analyze (HTTPS or SSH)
- `--repo-path PATH` - Local repository path to analyze
- `--output FILE` - Output file path for generated context

**Note:** Use either `--repo-url` OR `--repo-path`, not both.

### LLM Provider Options

- `--provider {openai,gemini}` - LLM provider (default: gemini)
- `--base-url URL` - Base URL for OpenAI-compatible API (required for `--provider openai`)
- `--model NAME` - Model name to use
  - Default for OpenAI: `qwen3_30b_deployed`
  - Default for Gemini: `gemini-flash-latest`
- `--api-key KEY` - API key (or set `GEMINI_API_KEY` env var for Gemini)

### Generation Parameters

- `--temperature FLOAT` - Sampling temperature 0.0-1.0 (default: 0.1)
- `--max-tokens INT` - Maximum tokens to generate (default: 4000)

## Programmatic Usage

### With OpenAI-Compatible LLM

```python
from llm_client import create_llm_client
from repo_context_pipeline import ContextPipeline

# Create client for your LLM endpoint
llm_client = create_llm_client(
    provider='openai',
    base_url='http://10.201.24.88:6655/v1',
    api_key='EMPTY',
    model='qwen3_30b_deployed',
    temperature=0.1,
    max_tokens=4000
)

# Initialize pipeline
pipeline = ContextPipeline(llm_client=llm_client)

# Generate from URL
context_file = pipeline.generate_from_url(
    repo_url='https://github.com/user/repo',
    output_path='context.txt'
)

# Or from local path
context_file = pipeline.generate_from_local(
    repo_path='/path/to/repo',
    output_path='context.txt'
)
```

### With Gemini

```python
from llm_client import create_llm_client
from repo_context_pipeline import ContextPipeline

# Create Gemini client
llm_client = create_llm_client(
    provider='gemini',
    api_key='your-api-key',
    model='gemini-flash-latest'
)

# Initialize and run
pipeline = ContextPipeline(llm_client=llm_client)
context_file = pipeline.generate_from_url(
    repo_url='https://github.com/user/repo',
    output_path='context.txt'
)
```

## Output Format

The generated context file includes:

```
# Repository Context for AI Code Review

**Source:** https://github.com/user/repo
**Generated:** 2025-12-03 20:30:00
**Languages:** Python, JavaScript
**Files Analyzed:** 45 (of 234 total)

---

# Repository Overview
[LLM-generated description of what the project does]

# Tech Stack
- Languages: [detected languages]
- Frameworks: [detected frameworks]
- Key Dependencies: [from config files]

# Architecture & Structure
[LLM-generated explanation of code organization]

# Code Conventions & Patterns
[LLM-generated patterns and conventions]

# Key Files
[List of important files with descriptions]

# Important Context for Reviewers
[Critical information for code reviewers]
```

## Configuration

### File Limits

Edit `repo_analyzer.py` to adjust:

```python
RepoAnalyzer(
    max_file_size_kb=100,  # Max individual file size
    max_total_files=100     # Max files to include
)
```

### File Filtering

The analyzer automatically:
- **Ignored directories**: `node_modules`, `.git`, `venv`, `__pycache__`, `dist`, `build`, etc.
- **Code files**: `.py`, `.js`, `.ts`, `.go`, `.java`, `.rs`, `.cpp`, `.c`, etc. (30+ languages)
- **Documentation**: `.md`, `.rst`, `.txt`
- **Configuration**: `.json`, `.yaml`, `.toml`, `.xml`

### Priority Files

Always included if present:
- `README.md`, `CONTRIBUTING.md`, `ARCHITECTURE.md`
- `package.json`, `requirements.txt`, `go.mod`, `Cargo.toml`, `pyproject.toml`
- `Dockerfile`, `Makefile`, `docker-compose.yml`

## Architecture

### Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER INPUT                                   │
│  (Git URL or Local Path) + (LLM Provider Config)              │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│              repo_context_pipeline.py                           │
│                  (Main Orchestrator)                            │
│                                                                 │
│  1. Accepts LLM client instance (provider-agnostic)            │
│  2. Coordinates the entire workflow                            │
│  3. Manages output file creation                               │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ├─────────────────┐
                       ▼                 ▼
         ┌─────────────────────┐  ┌──────────────────┐
         │  repo_analyzer.py   │  │  llm_client.py   │
         │                     │  │                  │
         │  STEP 1: ANALYZE    │  │  LLM PROVIDERS:  │
         │  • Clone repo       │  │  • OpenAI API    │
         │  • Scan files       │  │  • Gemini API    │
         │  • Filter by type   │  │  • Custom LLMs   │
         │  • Extract content  │  └──────────────────┘
         │  • Detect metadata  │            │
         └─────────┬───────────┘            │
                   │                        │
                   ▼                        │
         ┌─────────────────────────────────┴─┐
         │    context_generator.py           │
         │                                   │
         │    STEP 2: GENERATE CONTEXT       │
         │    • Build structured prompt      │
         │    • Call LLM via client         │
         │    • Parse response              │
         │    • Fallback on errors          │
         └─────────────────┬─────────────────┘
                           │
                           ▼
         ┌─────────────────────────────────────┐
         │     STEP 3: OUTPUT CONTEXT FILE     │
         │                                     │
         │  • Add metadata header              │
         │  • Format content                   │
         │  • Write to file                    │
         └─────────────────────────────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │  context.txt    │
                  │  (Final Output) │
                  └─────────────────┘
```

### Component Details

#### 1. **`repo_analyzer.py`** - Repository Scanner

**Purpose:** Extract and organize repository information

**Key Responsibilities:**
- **Git Operations:** Clone remote repos or read local directories
- **File Discovery:** Recursively scan directory structure
- **Smart Filtering:** 
  - Ignore irrelevant dirs (`node_modules`, `.git`, `venv`, etc.)
  - Prioritize important files (README, configs, entry points)
  - Filter by extension (30+ programming languages supported)
  - Limit file size (100KB max per file by default)
- **Content Extraction:** Read file contents with encoding handling
- **Metadata Detection:** Identify languages, frameworks, project type

**Output:** Structured dictionary with:
```python
{
    'repo_path': '/path/to/repo',
    'metadata': {...},      # Languages, frameworks, etc.
    'file_tree': '...',     # Directory structure
    'files': [...],         # List of file objects with content
    'stats': {...}          # Analysis statistics
}
```

#### 2. **`llm_client.py`** - Pluggable LLM Abstraction

**Purpose:** Provide unified interface for different LLM providers

**Architecture Pattern:** Strategy Pattern
- Abstract base class: `BaseLLMClient`
- Concrete implementations: `OpenAICompatibleClient`, `GeminiClient`
- Factory function: `create_llm_client(provider, ...)`

**Key Benefits:**
- **Provider-agnostic:** Core pipeline doesn't know which LLM it's using
- **Easily extensible:** Add new providers by implementing `BaseLLMClient`
- **Type-safe:** Enforces consistent interface across all implementations
- **Configuration isolated:** Each client handles its own auth/config

**Interface:**
```python
class BaseLLMClient(ABC):
    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str
    def get_client_info(self) -> Dict[str, str]
```

**Implementations:**

**`OpenAICompatibleClient`:**
- Works with any OpenAI-compatible API (vLLM, Ollama, custom endpoints)
- Supports streaming responses
- Configurable endpoint, model, temperature, max_tokens

**`GeminiClient`:**
- Uses Google's Gemini API
- Supports flash and pro models
- Configurable temperature, max_output_tokens

#### 3. **`context_generator.py`** - LLM Context Builder

**Purpose:** Transform repository analysis into LLM-generated context

**Key Responsibilities:**
- **Prompt Engineering:** Build structured prompts from repo analysis
  - Includes: README, file tree, config files, code samples
  - Optimized for context generation (not exhaustive docs)
- **LLM Interaction:** Call LLM client with system + user prompts
- **Response Processing:** Parse and format LLM output
- **Error Handling:** Fallback to basic context if LLM fails

**Prompt Structure:**
```
SYSTEM PROMPT:
"You are an expert code analyst creating concise repository context..."
[Structured format instructions]

USER PROMPT:
Repository: [name]
Languages: [detected]
File Tree: [structure]
README: [content]
Config Files: [package.json, requirements.txt, etc.]
Code Samples: [key files]
```

**Output Format:** Structured markdown with sections:
- Repository Overview
- Tech Stack
- Architecture & Structure
- Code Conventions & Patterns
- Key Files
- Important Context for Reviewers

#### 4. **`repo_context_pipeline.py`** - Orchestrator & CLI

**Purpose:** Main entry point that coordinates the entire workflow

**Key Responsibilities:**
- **Initialization:** Accept LLM client instance (dependency injection)
- **Workflow Coordination:**
  1. Call `RepoAnalyzer` to analyze repository
  2. Call `ContextGenerator` to generate context via LLM
  3. Build final output with metadata header
  4. Write to output file
- **CLI Interface:** Parse arguments and route to appropriate methods
- **Error Handling:** Catch and display errors gracefully
- **Cleanup:** Remove temporary cloned repositories

**Two Main Methods:**
- `generate_from_url(repo_url, output_path)` - Clone and analyze
- `generate_from_local(repo_path, output_path)` - Analyze existing repo

### Data Flow Example

```
INPUT: --repo-url https://github.com/user/repo --provider openai

┌─────────────────────────────────────────────────────┐
│ 1. ContextPipeline receives OpenAICompatibleClient │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│ 2. RepoAnalyzer.clone_repo()                         │
│    → Creates /tmp/repo_context_xyz/                  │
│    → git clone --depth 1 https://...                 │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│ 3. RepoAnalyzer.analyze_local_repo()                 │
│    → Scans 234 files, filters to 45 relevant files   │
│    → Reads READMEs, configs, code samples            │
│    → Returns structured dict                         │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│ 4. ContextGenerator.generate_context()               │
│    → Builds prompt from analysis                     │
│    → OpenAICompatibleClient.generate()               │
│      → POST http://10.201.24.88:6655/v1/completions │
│      → Returns LLM summary                           │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│ 5. ContextPipeline._build_final_context()            │
│    → Adds metadata header                            │
│    → Combines with LLM output                        │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│ 6. ContextPipeline._save_context()                   │
│    → Writes to context.txt                           │
│    → Cleanup: rm -rf /tmp/repo_context_xyz           │
└──────────────────────────────────────────────────────┘

OUTPUT: context.txt (3,456 chars)
```

### Design Principles

1. **Separation of Concerns:** Each component has a single, well-defined responsibility
2. **Dependency Injection:** Pipeline accepts LLM client, staying provider-agnostic
3. **Strategy Pattern:** LLM clients are interchangeable implementations
4. **Fail-Safe:** Fallback mechanisms when LLM or network fails
5. **Configurability:** File limits, extensions, and LLM params are adjustable

### Extending: Custom LLM Providers

Create your own LLM client:

```python
from llm_client import BaseLLMClient

class MyCustomLLM(BaseLLMClient):
    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        # Your implementation
        response = my_api_call(system_prompt, user_prompt)
        return response
    
    def get_client_info(self) -> dict:
        return {
            'type': 'My Custom LLM',
            'model': 'my-model-v1'
        }

# Use it
pipeline = ContextPipeline(llm_client=MyCustomLLM())
```

## Examples

See [`example_usage.py`](file:///Users/rakhat/Documents/Forte_Hackaton/the_cat_pyjamas/context_pipeline/example_usage.py) for working examples with both OpenAI-compatible and Gemini LLMs.

## Troubleshooting

**Problem: "GEMINI_API_KEY not found"**
- Solution: Set environment variable or use `--api-key` argument

**Problem: "Clone failed - Authentication failed"**
- Solution: Use SSH URL format directly: `git@github.com:user/repo.git`
- Ensure SSH keys are configured: `ssh -T git@github.com`

**Problem: "base-url is required when using --provider openai"**
- Solution: Add `--base-url http://your-endpoint/v1` when using OpenAI provider

**Problem: Context file is too small/empty**
- Solution: Increase `max_total_files` in `RepoAnalyzer` initialization
- Check repository actually contains supported file types

**Problem: LLM generation fails**
- Solution: Pipeline will fallback to basic context generation
- Check API endpoint is accessible and credentials are valid

## Use Cases

- **Code Review**: Generate context to help AI understand repositories before reviewing PRs
- **Onboarding**: Create summaries for new developers joining a project
- **Documentation**: Auto-generate high-level architecture documentation
- **Analysis**: Quickly understand unfamiliar codebases
- **Archival**: Document repository structure at specific points in time

## License

Part of the Kita AI Code Review Assistant project for Forte Hackathon.
