# Repository Context Pipeline

Generate comprehensive repository context files for AI-powered code review using LLM analysis.

## Overview

This pipeline analyzes git repositories and generates structured context files that provide essential information about the codebase. These context files can be fed to AI code reviewers alongside merge request diffs to enable more informed and contextually aware code reviews.

## Features

- **Git Repository Analysis**: Clone and analyze repositories from URLs or local paths
- **Smart File Filtering**: Automatically identifies and prioritizes important files (README, configs, code)
- **LLM-Powered Summarization**: Uses Gemini to generate concise, structured context
- **Size Management**: Handles large repositories with configurable limits
- **CLI Interface**: Easy-to-use command-line interface

## Installation

1. **Install dependencies:**
```bash
# From the_cat_pyjamas root directory
pip install -r requirements.txt
```

2. **Set up environment variables:**
```bash
# Copy example env file
cp .env_example .env

# Edit .env and add your Gemini API key
GEMINI_API_KEY=your_api_key_here
```

## Usage

### Basic Usage

**Generate context from a git URL:**
```bash
cd context_pipeline
python repo_context_pipeline.py --repo-url https://github.com/user/repo --output context.txt
```

**Generate context from a local repository:**
```bash
python repo_context_pipeline.py --repo-path /path/to/repo --output context.txt
```

### Advanced Options

**Specify a different Gemini model:**
```bash
python repo_context_pipeline.py \
  --repo-url https://github.com/user/repo \
  --output context.txt \
  --model gemini-2.0-flash
```

**Pass API key directly (instead of .env):**
```bash
python repo_context_pipeline.py \
  --repo-url https://github.com/user/repo \
  --output context.txt \
  --api-key your_api_key_here
```

## Integration with Code Review

### Example: Using with MR Reviewer

```python
from repo_context_pipeline import ContextPipeline

# Generate context
pipeline = ContextPipeline(gemini_api_key="your_key")
context_file = pipeline.generate_from_url(
    repo_url="https://github.com/user/repo",
    output_path="repo_context.txt"
)

# Load context
with open(context_file, 'r') as f:
    repo_context = f.read()

# Use with your MR reviewer
reviewer = MRReviewer(gemini_api_key="your_key")
results = reviewer.review_code(
    mr=mr_obj,
    diff_text=diff_string,
    diff_list=diff_list,
    system_prompt=ARCHITECT_SYSTEM_PROMPT,
    code_context=repo_context  # Add repo context here
)
```

## Output Format

The generated context file includes:

1. **Metadata Header**
   - Source repository
   - Generation timestamp
   - Languages detected
   - Files analyzed

2. **Repository Overview**
   - Project description and purpose
   - Tech stack and dependencies

3. **Architecture & Structure**
   - Code organization
   - Key directories

4. **Code Conventions**
   - Patterns and naming conventions
   - Architectural decisions

5. **Key Files**
   - Most important files with descriptions

6. **Reviewer Context**
   - Critical information for code reviewers

## Configuration

### File Limits

Edit `repo_analyzer.py` to adjust:
- `max_file_size_kb`: Maximum individual file size (default: 100 KB)
- `max_total_files`: Maximum files to include (default: 100)

### File Filtering

The analyzer automatically filters:
- **Ignored directories**: `node_modules`, `.git`, `venv`, `__pycache__`, etc.
- **Code extensions**: `.py`, `.js`, `.go`, `.java`, `.rs`, etc.
- **Doc extensions**: `.md`, `.rst`, `.txt`
- **Config extensions**: `.json`, `.yaml`, `.toml`, etc.

### Priority Files

These files are always included if present:
- README.md, CONTRIBUTING.md
- package.json, requirements.txt, go.mod
- Dockerfile, Makefile

## Architecture

### Components

1. **`repo_analyzer.py`**
   - Clones git repositories
   - Scans and categorizes files
   - Extracts file contents
   - Detects project metadata

2. **`context_generator.py`**
   - Uses Gemini API for analysis
   - Generates structured summaries
   - Provides fallback for errors

3. **`repo_context_pipeline.py`**
   - Main orchestrator
   - CLI interface
   - Coordinates analyzer and generator

## Examples

### Example 1: Analyze Kafka Repository
```bash
python repo_context_pipeline.py \
  --repo-url https://github.com/confluentinc/confluent-kafka-python \
  --output kafka_context.txt
```

### Example 2: Analyze Local Project
```bash
python repo_context_pipeline.py \
  --repo-path /Users/rakhat/Documents/Forte_Hackaton/the_cat_pyjamas \
  --output local_context.txt
```

## Troubleshooting

**Problem: "GEMINI_API_KEY not found"**
- Solution: Ensure `.env` file exists and contains `GEMINI_API_KEY=your_key`

**Problem: "Clone failed"**
- Solution: Check git is installed and URL is correct
- Private repos: May need authentication credentials

**Problem: Context file is too small**
- Solution: Increase `max_total_files` in RepoAnalyzer initialization
- Check if important files are being filtered out

**Problem: LLM generation fails**
- Solution: Pipeline will fallback to basic context generation
- Check API key is valid and has quota remaining

## License

Part of the Kita AI Code Review Assistant project for Forte Hackathon.
