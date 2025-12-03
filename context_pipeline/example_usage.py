"""
Example integration showing how to use the context pipeline with different LLM providers
"""
import os
from dotenv import load_dotenv
from repo_context_pipeline import ContextPipeline
from llm_client import create_llm_client

load_dotenv()

def generate_with_openai_compatible():
    """Example: Generate context using OpenAI-compatible LLM (like Qwen)"""
    
    print("\n" + "="*60)
    print("Example 1: OpenAI-Compatible LLM (Qwen)")
    print("="*60)
    
    # Create OpenAI-compatible client
    llm_client = create_llm_client(
        provider='openai',
        base_url='http://10.201.24.88:6655/v1',
        api_key='EMPTY',
        model='qwen3_30b_deployed',
        temperature=0.1,
        max_tokens=4000
    )
    
    # Initialize pipeline with the client
    pipeline = ContextPipeline(llm_client=llm_client)
    
    # Generate context
    context_file = pipeline.generate_from_local(
        repo_path="/Users/rakhat/Documents/Forte_Hackaton/the_cat_pyjamas/evaluation_pipeline",
        output_path="./examples/openai_context.txt"
    )
    
    return context_file


def generate_with_gemini():
    """Example: Generate context using Gemini"""
    
    print("\n" + "="*60)
    print("Example 2: Google Gemini")
    print("="*60)
    
    # Create Gemini client
    llm_client = create_llm_client(
        provider='gemini',
        api_key=os.getenv("GEMINI_API_KEY"),
        model='gemini-flash-latest',
        temperature=0.1,
        max_output_tokens=4000
    )
    
    # Initialize pipeline
    pipeline = ContextPipeline(llm_client=llm_client)
    
    # Generate context from git URL
    context_file = pipeline.generate_from_url(
        repo_url="https://github.com/confluentinc/confluent-kafka-python",
        output_path="./examples/gemini_context.txt"
    )
    
    return context_file


def use_context_with_review():
    """Example: Use generated context with MR reviewer"""
    
    # Step 1: Generate context (or load existing)
    context_file = "./examples/kafka_context.txt"
    
    if not os.path.exists(context_file):
        print("Generating context first...")
        generate_repo_context_example()
    
    # Step 2: Load context
    with open(context_file, 'r', encoding='utf-8') as f:
        repo_context = f.read()
    
    print(f"\n✅ Loaded context ({len(repo_context)} characters)")
    
    # Step 3: Use with MR reviewer
    # This would be integrated into your existing code review flow:
    # 
    # from mr_reviewer import MRReviewer
    # import prompts_rakhat
    # 
    # reviewer = MRReviewer(
    #     gemini_api_key=os.getenv("GEMINI_API_KEY"),
    #     model="gemini-flash-latest"
    # )
    # 
    # results = reviewer.review_code(
    #     mr=mr_obj,
    #     diff_text=diff_string,
    #     diff_list=diff_list,
    #     system_prompt=prompts_rakhat.ARCHITECT_SYSTEM_PROMPT,
    #     code_context=repo_context  # <-- Add context here
    # )
    
    print("\n💡 Context is ready to use with your MR reviewer!")
    print("   Pass it as the 'code_context' parameter to reviewer.review_code()")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "openai":
        # Generate with OpenAI-compatible LLM
        generate_with_openai_compatible()
    elif len(sys.argv) > 1 and sys.argv[1] == "gemini":
        # Generate with Gemini
        generate_with_gemini()
    elif len(sys.argv) > 1 and sys.argv[1] == "integrate":
        # Show integration example
        use_context_with_review()
    else:
        print("Usage:")
        print("  python example_usage.py openai     - Generate with OpenAI-compatible LLM")
        print("  python example_usage.py gemini     - Generate with Gemini")
        print("  python example_usage.py integrate  - Show integration with MR reviewer")

