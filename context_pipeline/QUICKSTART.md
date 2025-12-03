# Quick Start Guide - Context Pipeline

## Using Your Custom OpenAI-Compatible LLM (Qwen)

Based on your `test_llm_connection.py` setup:

```bash
cd /Users/rakhat/Documents/Forte_Hackaton/the_cat_pyjamas/context_pipeline

# Generate context using your Qwen model
python repo_context_pipeline.py \
  --repo-path /Users/rakhat/Documents/Forte_Hackaton/the_cat_pyjamas/evaluation_pipeline \
  --output ./context_output.txt \
  --provider openai \
  --base-url http://10.201.24.88:6655/v1 \
  --model qwen3_30b_deployed
```

## Using Gemini (Alternative)

If you want to use Gemini instead:

```bash
python repo_context_pipeline.py \
  --repo-path /Users/rakhat/Documents/Forte_Hackaton/the_cat_pyjamas/evaluation_pipeline \
  --output ./context_output.txt \
  --provider gemini \
  --api-key your-gemini-api-key
```

Or set the API key in your `.env` file:
```bash
echo "GEMINI_API_KEY=your-key-here" >> ../.env
```

## Programmatic Usage

### With Your Custom LLM

```python
from llm_client import create_llm_client
from repo_context_pipeline import ContextPipeline

# Create your custom OpenAI-compatible client
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

# Generate context
context_file = pipeline.generate_from_local(
    repo_path='/path/to/repo',
    output_path='./context.txt'
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

# Initialize and run pipeline
pipeline = ContextPipeline(llm_client=llm_client)
context_file = pipeline.generate_from_url(
    repo_url='https://github.com/user/repo',
    output_path='./context.txt'
)
```

## Switching Between LLMs

The architecture is now fully pluggable! You can:

1. **Use your custom LLM** (Qwen) for local/faster generation
2. **Use Gemini** for higher quality results
3. **Create your own LLM client** by extending `BaseLLMClient`

Example of creating a custom client:

```python
from llm_client import BaseLLMClient

class MyCustomLLM(BaseLLMClient):
    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        # Your custom implementation
        pass
    
    def get_client_info(self) -> Dict[str, str]:
        return {'type': 'My Custom LLM', 'model': 'custom-model'}

# Use it
pipeline = ContextPipeline(llm_client=MyCustomLLM())
```

## Next Steps

1. Test the pipeline with your Qwen model
2. Review the generated context quality
3. Adjust parameters (temperature, max_tokens) as needed
4. Integrate with your existing MR review workflow
