"""
Repository Analyzer - Extract structure and content from git repositories
"""
import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import mimetypes


class RepoAnalyzer:
    """Analyzes git repositories to extract relevant context for LLM review"""
    
    # File extensions to include in analysis
    CODE_EXTENSIONS = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rb', '.php',
        '.c', '.cpp', '.h', '.hpp', '.cs', '.swift', '.kt', '.rs', '.scala',
        '.sh', '.bash', '.sql', '.r', '.m', '.ml', '.ex', '.exs', '.clj',
        '.vim', '.lua', '.pl', '.pm'
    }
    
    DOC_EXTENSIONS = {'.md', '.rst', '.txt', '.adoc', '.org'}
    CONFIG_EXTENSIONS = {
        '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
        '.xml', '.properties', '.env.example'
    }
    
    # Directories to ignore
    IGNORE_DIRS = {
        '.git', 'node_modules', '__pycache__', '.pytest_cache', 'venv', '.venv',
        'env', 'dist', 'build', 'target', '.tox', '.mypy_cache', '.ruff_cache',
        'coverage', '.coverage', 'htmlcov', '.idea', '.vscode', '.vs',
        'vendor', 'deps', '_build', '.gradle', 'bin', 'obj', 'out',
        'eggs', '.eggs', 'wheels', 'lib', 'lib64'
    }
    
    # Priority files (always include if present)
    PRIORITY_FILES = {
        'README.md', 'README.rst', 'README.txt', 'README',
        'CONTRIBUTING.md', 'CONTRIBUTING.rst',
        'ARCHITECTURE.md', 'DESIGN.md',
        'package.json', 'requirements.txt', 'go.mod', 'Cargo.toml',
        'pom.xml', 'build.gradle', 'setup.py', 'pyproject.toml',
        'Makefile', 'Dockerfile', 'docker-compose.yml'
    }
    
    def __init__(self, max_file_size_kb: int = 100, max_total_files: int = 100):
        """
        Initialize analyzer
        
        Args:
            max_file_size_kb: Maximum size of individual files to process
            max_total_files: Maximum total files to include in analysis
        """
        self.max_file_size_bytes = max_file_size_kb * 1024
        self.max_total_files = max_total_files
        self.temp_dir = None
        
    def clone_repo(self, repo_url: str) -> str:
        """
        Clone git repository to temporary directory
        
        Args:
            repo_url: Git repository URL
            
        Returns:
            Path to cloned repository
        """
        print(f"📥 Cloning repository: {repo_url}")
        self.temp_dir = tempfile.mkdtemp(prefix='repo_context_')
        
        try:
            subprocess.run(
                ['git', 'clone', '--depth', '1', repo_url, self.temp_dir],
                check=True,
                capture_output=True,
                text=True
            )
            print(f"   ✅ Cloned to: {self.temp_dir}")
            return self.temp_dir
        except subprocess.CalledProcessError as e:
            print(f"   ❌ Clone failed: {e.stderr}")
            raise
    
    def analyze_local_repo(self, repo_path: str) -> Dict:
        """
        Analyze a local repository (already cloned)
        
        Args:
            repo_path: Path to local repository
            
        Returns:
            Dictionary with repository analysis results
        """
        print(f"📊 Analyzing repository: {repo_path}")
        
        repo_path_obj = Path(repo_path).resolve()
        if not repo_path_obj.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")
        
        # Gather all files
        all_files = self._scan_directory(repo_path_obj)
        print(f"   📁 Found {len(all_files)} relevant files")
        
        # Categorize files
        categorized = self._categorize_files(all_files)
        
        # Prioritize and limit files
        selected_files = self._select_files(categorized)
        print(f"   ✅ Selected {len(selected_files)} files for context")
        
        # Extract content
        file_contents = self._extract_contents(selected_files, repo_path_obj)
        
        # Detect project metadata
        metadata = self._detect_metadata(repo_path_obj, categorized)
        
        return {
            'repo_path': str(repo_path_obj),
            'metadata': metadata,
            'file_tree': self._build_tree(all_files, repo_path_obj),
            'files': file_contents,
            'stats': {
                'total_files_found': len(all_files),
                'files_included': len(selected_files),
                'languages': metadata.get('languages', [])
            }
        }
    
    def _scan_directory(self, repo_path: Path) -> List[Path]:
        """Recursively scan directory for relevant files"""
        relevant_files = []
        
        for root, dirs, files in os.walk(repo_path):
            # Remove ignored directories from traversal
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]
            
            root_path = Path(root)
            for file in files:
                file_path = root_path / file
                
                # Skip hidden files (except priority files)
                if file.startswith('.') and file not in self.PRIORITY_FILES:
                    continue
                
                # Check file extension or priority
                ext = file_path.suffix.lower()
                is_relevant = (
                    ext in self.CODE_EXTENSIONS or
                    ext in self.DOC_EXTENSIONS or
                    ext in self.CONFIG_EXTENSIONS or
                    file in self.PRIORITY_FILES
                )
                
                if is_relevant:
                    # Check file size
                    try:
                        if file_path.stat().st_size <= self.max_file_size_bytes:
                            relevant_files.append(file_path)
                    except OSError:
                        continue
        
        return relevant_files
    
    def _categorize_files(self, files: List[Path]) -> Dict[str, List[Path]]:
        """Categorize files by type"""
        categorized = {
            'priority': [],
            'docs': [],
            'code': [],
            'config': [],
            'other': []
        }
        
        for file_path in files:
            filename = file_path.name
            ext = file_path.suffix.lower()
            
            if filename in self.PRIORITY_FILES:
                categorized['priority'].append(file_path)
            elif ext in self.DOC_EXTENSIONS:
                categorized['docs'].append(file_path)
            elif ext in self.CODE_EXTENSIONS:
                categorized['code'].append(file_path)
            elif ext in self.CONFIG_EXTENSIONS:
                categorized['config'].append(file_path)
            else:
                categorized['other'].append(file_path)
        
        return categorized
    
    def _select_files(self, categorized: Dict[str, List[Path]]) -> List[Path]:
        """Select files to include based on priority and limits"""
        selected = []
        remaining_slots = self.max_total_files
        
        # Always include priority files
        selected.extend(categorized['priority'][:remaining_slots])
        remaining_slots -= len(selected)
        
        if remaining_slots <= 0:
            return selected
        
        # Include docs
        docs_to_add = min(len(categorized['docs']), remaining_slots // 4)
        selected.extend(categorized['docs'][:docs_to_add])
        remaining_slots -= docs_to_add
        
        # Include config files
        config_to_add = min(len(categorized['config']), remaining_slots // 4)
        selected.extend(categorized['config'][:config_to_add])
        remaining_slots -= config_to_add
        
        # Fill rest with code files
        selected.extend(categorized['code'][:remaining_slots])
        
        return selected
    
    def _extract_contents(self, files: List[Path], repo_path: Path) -> List[Dict]:
        """Extract file contents and metadata"""
        file_data = []
        
        for file_path in files:
            try:
                # Try to read as text
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                relative_path = file_path.relative_to(repo_path)
                
                file_data.append({
                    'path': str(relative_path),
                    'full_path': str(file_path),
                    'extension': file_path.suffix,
                    'size': file_path.stat().st_size,
                    'content': content,
                    'line_count': content.count('\n') + 1 if content else 0
                })
            except Exception as e:
                print(f"   ⚠️ Could not read {file_path.name}: {e}")
                continue
        
        return file_data
    
    def _build_tree(self, files: List[Path], repo_path: Path) -> str:
        """Build a tree representation of the file structure"""
        # Get all unique directories
        dirs = set()
        for file_path in files:
            relative = file_path.relative_to(repo_path)
            for parent in relative.parents:
                if str(parent) != '.':
                    dirs.add(str(parent))
        
        # Build simple tree
        tree_lines = [f"📁 {repo_path.name}/"]
        
        # Add directories
        sorted_dirs = sorted(dirs)
        for dir_path in sorted_dirs[:20]:  # Limit to top 20 dirs
            tree_lines.append(f"  📁 {dir_path}/")
        
        return '\n'.join(tree_lines)
    
    def _detect_metadata(self, repo_path: Path, categorized: Dict) -> Dict:
        """Detect project type, languages, and other metadata"""
        metadata = {
            'project_name': repo_path.name,
            'languages': set(),
            'frameworks': [],
            'has_tests': False
        }
        
        # Detect languages from file extensions
        for file_path in categorized.get('code', []):
            ext = file_path.suffix.lower()
            lang_map = {
                '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
                '.go': 'Go', '.java': 'Java', '.rb': 'Ruby', '.php': 'PHP',
                '.rs': 'Rust', '.cpp': 'C++', '.c': 'C', '.cs': 'C#',
                '.swift': 'Swift', '.kt': 'Kotlin', '.scala': 'Scala'
            }
            if ext in lang_map:
                metadata['languages'].add(lang_map[ext])
        
        metadata['languages'] = list(metadata['languages'])
        
        # Detect test files
        for file_path in categorized.get('code', []):
            filename = file_path.name.lower()
            if 'test' in filename or filename.startswith('test_'):
                metadata['has_tests'] = True
                break
        
        # Detect frameworks from priority files
        for file_path in categorized.get('priority', []):
            filename = file_path.name
            if filename == 'package.json':
                metadata['frameworks'].append('Node.js/npm')
            elif filename == 'requirements.txt' or filename == 'pyproject.toml':
                metadata['frameworks'].append('Python')
            elif filename == 'go.mod':
                metadata['frameworks'].append('Go')
            elif filename == 'Cargo.toml':
                metadata['frameworks'].append('Rust')
        
        return metadata
    
    def cleanup(self):
        """Clean up temporary directory"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                print(f"🧹 Cleaned up temp directory")
            except Exception as e:
                print(f"⚠️ Cleanup warning: {e}")
