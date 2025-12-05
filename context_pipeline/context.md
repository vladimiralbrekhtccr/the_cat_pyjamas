# Repository Context for AI Code Review

**Source:** git@github.com:vladimiralbrekhtccr/the_cat_pyjamas.git
**Generated:** 2025-12-03 20:30:19
**Languages:** Python
**Files Analyzed:** 30 (of 30 total)

---
# Repository Overview  
This project is a hackathon submission for **Kita AI's "AI-Code Review Assistant" track**, demonstrating an automated AI-powered code review pipeline integrated with GitLab. It simulates a real-world banking use case by analyzing a merged MR from `confluentinc/confluent-kafka-go`, re-creating it in a test environment, and applying AI-driven review and suggestions to improve code quality.

# Tech Stack  
- **Languages**: Python  
- **Frameworks**: FastAPI, GitLab API client  
- **AI Model**: Google Gemini (via `google-genai`)  
- **Key Dependencies**: `python-gitlab`, `uvicorn`, `pyngrok`, `pytest`, `dotenv`  

# Architecture & Structure  
The system is structured around two main components:  
1. **Real-world case simulation** – scripts that mimic developer behavior (e.g., creating MRs, committing changes).  
2. **Evaluation pipeline** – automated benchmarking suite to test AI review quality across 11 scenarios (from simple to complex).  

Core agents include:  
- `Senior Agent` (Tech Lead): Provides high-level review with risk/decision labels.  
- `Suggestions Agent`: Generates inline code improvement suggestions.  
- `Friendly Commit Agent`: Monitors new commits post-review and updates feedback accordingly.  

All agents communicate via GitLab API and use structured prompts for consistent output.

# Code Conventions & Patterns  
- **Strict output formatting**: All agent responses use XML-like tags (`<summary>`, `<risk>`, `<decision>`, etc.) to enable parsing.  
- **Modular agent design**: Each agent has a single responsibility and is decoupled via clear interfaces.  
- **Environment-driven configuration**: Sensitive data (tokens, URLs) loaded from `.env`.  
- **Event-driven architecture**: Webhook servers listen for new MRs and commits, triggering automated workflows.  

# Key Files  
1. `1_webhook_for_new_mr.py` – Listens for new MRs and triggers initial AI review.  
2. `2_webhook_for_new_commits.py` – Monitors new commits and updates feedback.  
3. `1_1_generation_of_new_MR.py` – Simulates full MR creation and AI review workflow.  
4. `prompts.py` – Centralized prompt templates for all agents.  
5. `evaluation_pipeline/benchmarks/` – Test scenarios and unit tests for model evaluation.  
6. `commit_simulator_from_junior.py` – Simulates junior developer’s code changes and comments.  
7. `requirements.txt` – Project dependencies.  
8. `.env.example` – Template for environment variables.  

# Important Context for Reviewers  
1. **Security**: The project uses GitLab personal access tokens; ensure `.env` is never committed.  
2. **Pipeline Flow**: The full workflow is event-driven: MR → AI review → suggestions → commit → re-review → merge.  
3. **Evaluation Rigor**: The pipeline includes automated testing before/after fixes, enabling measurable validation of AI quality.