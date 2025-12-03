"""
Repository Context Pipeline - Main orchestrator
Generates comprehensive context files from git repositories for LLM-based code review
"""
import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

from repo_analyzer import RepoAnalyzer
from context_generator import ContextGenerator
from llm_client import BaseLLMClient, create_llm_client


class ContextPipeline:
    """Main pipeline for generating repository context"""
    
    def __init__(self, llm_client: BaseLLMClient):
        """
        Initialize pipeline
        
        Args:
            llm_client: LLM client instance (GeminiClient, OpenAICompatibleClient, etc.)
        """
        self.analyzer = RepoAnalyzer(max_file_size_kb=100, max_total_files=100)
        self.generator = ContextGenerator(llm_client=llm_client)
    
    def generate_from_url(self, repo_url: str, output_path: str) -> str:
        """
        Generate context from a git repository URL
        
        Args:
            repo_url: Git repository URL
            output_path: Path to save context file
            
        Returns:
            Path to generated context file
        """
        print(f"\n{'='*60}")
        print(f"🚀 Repository Context Pipeline")
        print(f"{'='*60}\n")
        
        try:
            # Step 1: Clone repository
            repo_path = self.analyzer.clone_repo(repo_url)
            
            # Step 2: Analyze repository
            analysis = self.analyzer.analyze_local_repo(repo_path)
            
            # Step 3: Generate context with LLM
            context = self.generator.generate_context(analysis)
            
            # Step 4: Add metadata header
            full_context = self._build_final_context(repo_url, analysis, context)
            
            # Step 5: Save to file
            output_file = self._save_context(full_context, output_path)
            
            print(f"\n{'='*60}")
            print(f"✅ Context generated successfully!")
            print(f"📄 Output: {output_file}")
            print(f"{'='*60}\n")
            
            return output_file
            
        finally:
            # Cleanup
            self.analyzer.cleanup()
    
    def generate_from_local(self, repo_path: str, output_path: str) -> str:
        """
        Generate context from a local repository
        
        Args:
            repo_path: Path to local repository
            output_path: Path to save context file
            
        Returns:
            Path to generated context file
        """
        print(f"\n{'='*60}")
        print(f"🚀 Repository Context Pipeline (Local)")
        print(f"{'='*60}\n")
        
        # Step 1: Analyze repository
        analysis = self.analyzer.analyze_local_repo(repo_path)
        
        # Step 2: Generate context with LLM
        context = self.generator.generate_context(analysis)
        
        # Step 3: Add metadata header
        full_context = self._build_final_context(repo_path, analysis, context)
        
        # Step 4: Save to file
        output_file = self._save_context(full_context, output_path)
        
        print(f"\n{'='*60}")
        print(f"✅ Context generated successfully!")
        print(f"📄 Output: {output_file}")
        print(f"{'='*60}\n")
        
        return output_file
    
    def _build_final_context(self, source: str, analysis: dict, llm_context: str) -> str:
        """Build final context file with metadata header"""
        metadata = analysis['metadata']
        stats = analysis['stats']
        
        header = [
            "# Repository Context for AI Code Review",
            "",
            f"**Source:** {source}",
            f"**Generated:** {self._get_timestamp()}",
            f"**Languages:** {', '.join(metadata.get('languages', ['Unknown']))}",
            f"**Files Analyzed:** {stats['files_included']} (of {stats['total_files_found']} total)",
            "",
            "---",
            "",
        ]
        
        return '\n'.join(header) + llm_context
    
    def _save_context(self, context: str, output_path: str) -> str:
        """Save context to file"""
        output_file = Path(output_path)
        
        # Make sure directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Write context
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(context)
        
        print(f"💾 Saved context to: {output_file}")
        print(f"   Size: {len(context)} characters")
        
        return str(output_file)
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Generate repository context for AI code review",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate using OpenAI-compatible LLM (custom endpoint)
  python repo_context_pipeline.py \\
    --repo-url https://github.com/user/repo \\
    --output context.txt \\
    --provider openai \\
    --base-url http://10.201.24.88:6655/v1 \\
    --model qwen3_30b_deployed
  
  # Generate using Gemini
  python repo_context_pipeline.py \\
    --repo-path /path/to/repo \\
    --output context.txt \\
    --provider gemini \\
    --api-key your-gemini-key
  
  # Use local path with custom model
  python repo_context_pipeline.py \\
    --repo-path /path/to/repo \\
    --output context.txt \\
    --provider openai \\
    --base-url http://localhost:8000/v1
        """
    )
    
    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--repo-url',
        type=str,
        help='Git repository URL to analyze'
    )
    input_group.add_argument(
        '--repo-path',
        type=str,
        help='Local repository path to analyze'
    )
    
    # Output options
    parser.add_argument(
        '--output',
        type=str,
        required=True,
        help='Output file path for context'
    )
    
    # LLM Provider options
    parser.add_argument(
        '--provider',
        type=str,
        choices=['openai', 'gemini'],
        default='gemini',
        help='LLM provider to use (default: gemini)'
    )
    
    # OpenAI-compatible options
    parser.add_argument(
        '--base-url',
        type=str,
        help='Base URL for OpenAI-compatible API (required for --provider openai)'
    )
    
    parser.add_argument(
        '--model',
        type=str,
        help='Model name (default: qwen3_30b_deployed for OpenAI, gemini-flash-latest for Gemini)'
    )
    
    # API key (optional, falls back to env)
    parser.add_argument(
        '--api-key',
        type=str,
        help='API key (for Gemini) or use GEMINI_API_KEY env var'
    )
    
    # Generation parameters
    parser.add_argument(
        '--temperature',
        type=float,
        default=0.1,
        help='Generation temperature (default: 0.1)'
    )
    
    parser.add_argument(
        '--max-tokens',
        type=int,
        default=4000,
        help='Maximum tokens to generate (default: 4000)'
    )
    
    args = parser.parse_args()
    
    # Load environment variables
    load_dotenv()
    
    # Create LLM client based on provider
    if args.provider == 'openai':
        if not args.base_url:
            print("❌ Error: --base-url is required when using --provider openai")
            sys.exit(1)
        
        llm_client = create_llm_client(
            provider='openai',
            base_url=args.base_url,
            api_key=args.api_key or 'EMPTY',
            model=args.model or 'qwen3_30b_deployed',
            temperature=args.temperature,
            max_tokens=args.max_tokens
        )
    
    elif args.provider == 'gemini':
        api_key = args.api_key or os.getenv('GEMINI_API_KEY')
        if not api_key:
            print("❌ Error: GEMINI_API_KEY not found in environment or --api-key argument")
            sys.exit(1)
        
        llm_client = create_llm_client(
            provider='gemini',
            api_key=api_key,
            model=args.model or 'gemini-flash-latest',
            temperature=args.temperature,
            max_output_tokens=args.max_tokens
        )
    
    # Initialize pipeline
    pipeline = ContextPipeline(llm_client=llm_client)
    
    # Run pipeline
    try:
        if args.repo_url:
            pipeline.generate_from_url(args.repo_url, args.output)
        else:
            pipeline.generate_from_local(args.repo_path, args.output)
    except KeyboardInterrupt:
        print("\n\n⚠️ Pipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
