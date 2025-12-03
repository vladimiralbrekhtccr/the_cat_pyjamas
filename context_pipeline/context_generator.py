"""
Context Generator - Use LLM to generate repository context summaries
"""
from typing import Dict, Optional
from llm_client import BaseLLMClient, GeminiClient, OpenAICompatibleClient


class ContextGenerator:
    """Uses LLM to generate structured repository context"""
    
    CONTEXT_SYSTEM_PROMPT = """You are an expert code analyst creating concise repository context for AI-powered code review.

Your goal is to provide essential context that will help an AI reviewer understand:
1. What this codebase does
2. Key architectural patterns and conventions
3. Important files and their purposes
4. Technologies and dependencies used

Be CONCISE. Focus on information that would help review code changes, not exhaustive documentation.

Generate context in the following structured format:

# Repository Overview
[2-3 sentence description of what this project does and its purpose]

# Tech Stack
- Languages: [list]
- Frameworks: [list]
- Key Dependencies: [list if identifiable]

# Architecture & Structure
[Brief description of code organization and key directories]

# Code Conventions & Patterns
[Important coding patterns, naming conventions, or architectural decisions visible in the code]

# Key Files
[List 5-10 most important files with brief purpose]

# Important Context for Reviewers
[2-3 critical things a code reviewer should know when reviewing changes to this codebase]
"""

    def __init__(self, llm_client: BaseLLMClient):
        """
        Initialize context generator
        
        Args:
            llm_client: LLM client instance (can be GeminiClient, OpenAICompatibleClient, etc.)
        """
        self.llm_client = llm_client
    
    def generate_context(self, repo_analysis: Dict) -> str:
        """
        Generate repository context from analysis results
        
        Args:
            repo_analysis: Dictionary from RepoAnalyzer.analyze_local_repo()
            
        Returns:
            Generated context as text
        """
        print("🤖 Generating repository context with LLM...")
        client_info = self.llm_client.get_client_info()
        print(f"   Using: {client_info['type']} - {client_info['model']}")
        
        # Build prompt with repository information
        user_prompt = self._build_prompt(repo_analysis)
        
        # Call LLM
        try:
            response = self.llm_client.generate(self.CONTEXT_SYSTEM_PROMPT, user_prompt)
            print(f"   ✅ Generated context ({len(response)} characters)")
            return response
        except Exception as e:
            print(f"   ❌ Error generating context: {e}")
            # Fallback to basic context
            return self._generate_basic_context(repo_analysis)
    
    def _build_prompt(self, repo_analysis: Dict) -> str:
        """Build prompt from repository analysis"""
        metadata = repo_analysis['metadata']
        files = repo_analysis['files']
        stats = repo_analysis['stats']
        
        # Start with metadata
        prompt_parts = [
            f"Repository: {metadata['project_name']}",
            f"Languages: {', '.join(metadata.get('languages', ['Unknown']))}",
            f"Total files analyzed: {stats['files_included']}/{stats['total_files_found']}",
            "",
            "## File Structure",
            repo_analysis['file_tree'],
            ""
        ]
        
        # Add README if present
        readme_files = [f for f in files if 'README' in f['path'].upper()]
        if readme_files:
            readme = readme_files[0]
            content = readme['content'][:3000]  # Limit README size
            prompt_parts.extend([
                "## README Content",
                "```",
                content,
                "```",
                ""
            ])
        
        # Add key configuration files
        config_files = [f for f in files if f['path'] in [
            'package.json', 'requirements.txt', 'go.mod', 'Cargo.toml',
            'pyproject.toml', 'pom.xml', 'build.gradle'
        ]]
        
        if config_files:
            prompt_parts.append("## Configuration Files")
            for cfg in config_files[:3]:
                content = cfg['content'][:500]  # Limit config file size
                prompt_parts.extend([
                    f"### {cfg['path']}",
                    "```",
                    content,
                    "```",
                    ""
                ])
        
        # Add sample code files
        code_files = [f for f in files if f['extension'] in [
            '.py', '.js', '.ts', '.go', '.java', '.rb', '.rs'
        ]]
        
        if code_files:
            prompt_parts.append("## Sample Code Files")
            # Take up to 5 code files
            for code_file in code_files[:5]:
                content = code_file['content'][:800]  # Limit code sample size
                prompt_parts.extend([
                    f"### {code_file['path']} ({code_file['line_count']} lines)",
                    "```",
                    content,
                    "```",
                    ""
                ])
        
        prompt_parts.extend([
            "",
            "Based on the above repository information, generate a concise context summary following the specified format."
        ])
        
        return '\n'.join(prompt_parts)
    
    def _generate_basic_context(self, repo_analysis: Dict) -> str:
        """Generate basic context without LLM (fallback)"""
        metadata = repo_analysis['metadata']
        stats = repo_analysis['stats']
        files = repo_analysis['files']
        
        context_parts = [
            "# Repository Context (Basic)",
            "",
            f"**Repository:** {metadata['project_name']}",
            f"**Languages:** {', '.join(metadata.get('languages', ['Unknown']))}",
            f"**Files Analyzed:** {stats['files_included']}",
            "",
            "## File Structure",
            repo_analysis['file_tree'],
            "",
            "## Key Files",
        ]
        
        # List important files
        for file_data in files[:15]:
            context_parts.append(f"- `{file_data['path']}` ({file_data['line_count']} lines)")
        
        context_parts.extend([
            "",
            "## README Content",
        ])
        
        # Add README if present
        readme_files = [f for f in files if 'README' in f['path'].upper()]
        if readme_files:
            context_parts.append(readme_files[0]['content'][:2000])
        else:
            context_parts.append("No README found")
        
        return '\n'.join(context_parts)
