# Evaluation Pipeline with Repository Context

This is a modified version of the evaluation pipeline that integrates **repository context generation** to test if providing broader codebase context alongside diffs improves AI code review accuracy.

## Overview

The original pipeline (`evaluation_pipeline/pipeline_of_auto_testing.py`) reviews code diffs in isolation. This enhanced version:

1. **Generates repository context** using the `context_pipeline`
2. **Includes context in the architect review** prompt
3. **Compares test pass rates** to measure improvement

## Key Differences from Original Pipeline

| Aspect | Original Pipeline | Context-Enhanced Pipeline |
|--------|------------------|---------------------------|
| **Input to AI** | Only diffs + CTO instructions | **Diffs + CTO instructions + Repo context** |
| **Context Generation** | None | Analyzes repo structure, detects languages, extracts key files |
| **Prompt Size** | ~1-2K tokens | ~3-5K tokens (includes context) |
| **Hypothesis** | AI reviews in isolation | **AI has broader understanding** |

## How It Works

### Workflow Comparison

**Original:**
```
1. Setup repo & MR
2. Run pre-fix tests
3. Lead review (diff only)
4. Architect review (diff only) → Generate fixes
5. Apply fixes
6. Run post-fix tests
```

**With Context:**
```
1. Setup repo & MR
2. Generate repository context ← NEW STEP
3. Run pre-fix tests
4. Lead review (diff only)
5. Architect review (diff + context) ← ENHANCED
6. Apply fixes
7. Run post-fix tests
```

### Context Generation Details

The pipeline uses `context_pipeline` components:

```python
# Initialize context components
llm_client = create_llm_client(provider='gemini', ...)
self.context_generator = ContextGenerator(llm_client=llm_client)
self.repo_analyzer = RepoAnalyzer(max_file_size_kb=100, max_total_files=50)

# Generate context for each scenario
repo_context = self.generate_repo_context(scenario_name, tmp_dir)
```

Context includes:
- Repository overview
- Tech stack and languages
- Architecture and structure
- Code conventions
- Key files and their purposes

### Modified Architect Prompt

```python
architect_input = f"""
REPOSITORY CONTEXT:
{self.repo_context}

==========================================

CTO DIRECTIVES:
"{cto_instructions}"

CODE DIFF TO FIX:
{diff_context}
"""
```

## Usage

### Running the Context-Enhanced Pipeline

```bash
cd /Users/rakhat/Documents/Forte_Hackaton/the_cat_pyjamas/evaluation_pipeline_with_context

python pipeline_with_context.py
```

### Running the Original (for comparison)

```bash
cd /Users/rakhat/Documents/Forte_Hackaton/the_cat_pyjamas/evaluation_pipeline

python pipeline_of_auto_testing.py
```

## Expected Benefits

### Hypothesis
Adding repository context should help the AI:

1. **Understand project conventions** - Naming patterns, code style
2. **Recognize architecture** - How components interact
3. **Detect context-specific bugs** - Issues that only make sense with broader understanding
4. **Make better fix suggestions** - Aligned with existing patterns

### Metrics to Compare

- **Test Pass Rate**: % of scenarios that pass all tests after AI fixes
- **Fix Quality**: Do fixes align with project conventions?
- **Bug Detection**: Does AI find more critical bugs?

## Implementation Notes

### Performance Considerations

1. **Context Caching**: Context is generated once per scenario and cached
2. **File Limits**: Reduced to 50 files (vs 100) for faster generation
3. **Token Usage**: ~2-3K additional tokens per review

### Optimizations Made

- Context is generated **after** repo setup but **before** tests
- Context is **cached** in `self.repo_context_cache` to avoid regeneration
- Using Gemini Flash for context generation (faster, cheaper)

## Files in This Directory

```
evaluation_pipeline_with_context/
├── pipeline_with_context.py     # Modified pipeline with context
├── prompts_with_context.py      # Same prompts as original
├── benchmarks/                  # Copied test scenarios
│   ├── scenarios1.py
│   ├── scenarios2.py
│   └── ...
└── README.md                    # This file
```

## Dependencies

Same as original pipeline, plus:
- `context_pipeline/` components (automatically imported)

## Comparison Strategy

Run both pipelines on the same scenarios and compare:

```bash
# Run original
cd ../evaluation_pipeline
python pipeline_of_auto_testing.py > ../results_original.txt

# Run with context
cd ../evaluation_pipeline_with_context
python pipeline_with_context.py > ../results_with_context.txt

# Compare
diff ../results_original.txt ../results_with_context.txt
```

Look for:
- ✅ More PASSes in context version
- 🔍 Different bugs detected
- 💡 Better fix quality

## Example Output

```
🚀 STARTING SUITE WITH CONTEXT: 11 Scenarios Queued.

============================================================
▶️  RUNNING CASE 1/11: race-condition-deposit

📊 [Context Generation] Analyzing repository...
   ✅ Analyzed 8 files
   ✅ Generated 2847 character context

1️⃣  [Setup] Creating GitLab Repo & MR...
   ✅ Created: https://gitlab.com/...

    🧪 [PRE-FIX] Running Tests...
       ✅ Passed: 0
       ❌ Failed: 2

2️⃣  [Agent Lead] Executive Review...
    📝 Decision: CHANGES_REQUESTED

🧠 [Agent Architect] Analyzing Logic WITH CONTEXT...
    ℹ️  CTO Directives: Check for race conditions...
    📚 Context Length: 2847 chars
    🔍 Found 1 issues.
      ✅ Comment posted on bank.py:42

3️⃣  [Apply Fixes] Implementing suggestions...
    ✅ Fixed bank.py

    🧪 [POST-FIX] Running Tests...
       ✅ Passed: 2
       ❌ Failed: 0

    🏆 SCENARIO PASSED (WITH CONTEXT)
```

## Troubleshooting

**Problem: Context generation is slow**
- Reduce `max_total_files` in `pipeline_with_context.py` line 45

**Problem: Ge Gemini API rate limits**
- Add delays: `time.sleep(3)` after context generation

**Problem: Context is too large**
- Modify context prompt in `context_pipeline/context_generator.py` to be more concise

## Next Steps

1. Run both pipelines
2. Compare results statistically
3. Analyze specific scenarios where context helped/hurt
4. Document findings

## License

Part of the Kita AI Code Review Assistant project for Forte Hackathon.
