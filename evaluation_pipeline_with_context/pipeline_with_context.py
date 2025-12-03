import os
import sys
import time
import json
import shutil
import tempfile
import subprocess
import re
import gitlab
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Add context_pipeline to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../context_pipeline'))
from llm_client import create_llm_client
from repo_analyzer import RepoAnalyzer
from context_generator import ContextGenerator

# --- IMPORTS ---
import prompts_with_context as prompts

load_dotenv()

# --- CONFIGURATION ---
GITLAB_URL = "https://gitlab.com"
GROUP_PATH = "vladimiralbrekhtccr-group"
MODEL_BIG = "gemini-flash-latest"
MODEL_SMALL = "gemini-flash-latest"


class UnifiedPipelineWithContext:
    """Modified pipeline that generates repository context before code review"""
    
    def __init__(self):
        self.gl = gitlab.Gitlab(GITLAB_URL, private_token=os.getenv("GITLAB_TOKEN_TESTING"))
        self.gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        self.project = None
        self.local_temp_dir = tempfile.mkdtemp()
        print(f"📁 Local Test Environment created at: {self.local_temp_dir}")
        
        # Create logs directory for prompts
        self.logs_dir = os.path.join(os.path.dirname(__file__), 'prompt_logs')
        os.makedirs(self.logs_dir, exist_ok=True)
        self.current_scenario = None
        
        # Initialize context generation components
        llm_client = create_llm_client(
            provider='gemini',
            api_key=os.environ.get("GEMINI_API_KEY"),
            model=MODEL_BIG
        )
        self.context_generator = ContextGenerator(llm_client=llm_client)
        self.repo_analyzer = RepoAnalyzer(max_file_size_kb=100, max_total_files=50)
        self.repo_context_cache = {}  # Cache context per scenario

    def cleanup(self, project_name_filter="bank-unified"):
        """Delete old repos to keep GitLab clean"""
        print("🧹 Cleaning up old projects...")
        projects = self.gl.projects.list(search=project_name_filter, get_all=True)
        for p in projects:
            if project_name_filter in p.name:
                try:
                    p.delete()
                    print(f"   ✅ Deleted {p.name}")
                    time.sleep(0.5)
                except:
                    pass
    
    def log_prompt(self, agent_name: str, system_prompt: str, user_prompt: str, model: str):
        """Log prompts to file for debugging and analysis"""
        if not self.current_scenario:
            return
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{self.current_scenario}_{agent_name}_{timestamp}.json"
        filepath = os.path.join(self.logs_dir, filename)
        
        log_data = {
            "scenario": self.current_scenario,
            "agent": agent_name,
            "model": model,
            "timestamp": timestamp,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "total_length": len(system_prompt) + len(user_prompt)
        }
        
        with open(filepath, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        print(f"    📝 Logged prompt to: {filename}")

    def _ask_gemini(self, system_prompt, user_content, temperature=0.1, model_name="gemini-2.0-flash"):
        """Call Gemini API and return raw text response"""
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=system_prompt),
                    types.Part.from_text(text=user_content),
                ],
            )
        ]
        
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=4000,
            thinking_config={'thinking_budget': 0}
        )
        
        full_text = ""
        try:
            for chunk in self.gemini_client.models.generate_content_stream(
                model=model_name,
                contents=contents,
                config=config
            ):
                full_text += chunk.text
            return full_text
        except Exception as e:
            print(f"   ❌ Gemini API Error: {e}")
            return ""

    def generate_repo_context(self, scenario_key, local_repo_path):
        """
        Generate repository context for the scenario
        
        Args:
            scenario_key: Unique scenario identifier
            local_repo_path: Path to local repository
            
        Returns:
            Context string or empty if generation fails
        """
        # Check cache first
        if scenario_key in self.repo_context_cache:
            print(f"   📋 Using cached context for {scenario_key}")
            return self.repo_context_cache[scenario_key]
        
        print(f"\n📊 [Context Generation] Analyzing repository...")
        
        try:
            # Analyze repository
            analysis = self.repo_analyzer.analyze_local_repo(local_repo_path)
            print(f"   ✅ Analyzed {analysis['stats']['files_included']} files")
            
            # Generate context
            context = self.context_generator.generate_context(analysis)
            
            # Cache it
            self.repo_context_cache[scenario_key] = context
            
            print(f"   ✅ Generated {len(context)} character context")
            return context
            
        except Exception as e:
            print(f"   ❌ Context generation failed: {e}")
            return ""

    def setup_repo_and_mr(self, scenario_name, scenario_data, base_files):
        """Create GitLab project, commit files via API, and create MR"""
        print(f"\n1️⃣  [Setup] Creating GitLab Repo & MR...")
        project_name = f"{scenario_name}-{int(time.time())}"
        
        # Create GitLab project
        try:
            group = self.gl.groups.get(GROUP_PATH)
            self.project = self.gl.projects.create({'name': project_name, 'namespace_id': group.id})
        except:
            self.project = self.gl.projects.create({'name': project_name})
        
        print(f"   ✅ Created: {self.project.web_url}")
        time.sleep(1)
        
        # 1. Setup MAIN Branch with base files + tests
        files_to_commit = base_files.copy()
        files_to_commit.update(scenario_data['tests'])
        
        actions = [{'action': 'create', 'file_path': k, 'content': v} for k, v in files_to_commit.items()]
        
        self.project.commits.create({
            'branch': 'main',
            'commit_message': 'Init: Base architecture and tests',
            'actions': actions
        })
        time.sleep(1)
        
        # 2. Setup Feature Branch with buggy code
        branch_name = scenario_data['branch']
        self.project.branches.create({'branch': branch_name, 'ref': 'main'})
        
        change_actions = []
        for f_path, f_content in scenario_data['changes'].items():
            change_actions.append({
                'action': 'create',
                'file_path': f_path,
                'content': f_content
            })
        
        self.project.commits.create({
            'branch': branch_name,
            'commit_message': f"feat: {scenario_data['name']} implementation",
            'actions': change_actions
        })
        
        # 3. Create MR
        mr = self.project.mergerequests.create({
            'source_branch': branch_name,
            'target_branch': 'main',
            'title': f"Feat: {scenario_data['name']}",
            'description': scenario_data['description'],
            'remove_source_branch': True
        })
        print(f"   ✅ MR created: {mr.web_url}")
        
        # **GENERATE REPOSITORY CONTEXT HERE**
        # Clone repo locally for context analysis
        tmp_dir = tempfile.mkdtemp()
        clone_url = self.project.http_url_to_repo.replace(
            'https://', 
            f'https://oauth2:{os.getenv("GITLAB_TOKEN_TESTING")}@'
        )
        subprocess.run(['git', 'clone', clone_url, tmp_dir], 
                      check=True, capture_output=True)
        
        repo_context = self.generate_repo_context(scenario_name, tmp_dir)
        
        # Cleanup temp clone
        shutil.rmtree(tmp_dir, ignore_errors=True)
        
        # Store context for later use
        self.repo_context = repo_context
        
        # Prepare file map
        full_file_map = files_to_commit.copy()
        full_file_map.update(scenario_data['changes'])
        
        return mr, full_file_map

    def run_local_tests(self, file_map, stage_name):
        """Run pytest on test files by writing file_map contents to temp dir"""
        print(f"\n    🧪 [{stage_name}] Writing files and running Pytest...")
        
        # Write files from file_map (content strings) to local_temp_dir
        for filename, content in file_map.items():
            path = os.path.join(self.local_temp_dir, filename)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                f.write(content)
            print(f"       📄 Wrote: {filename}")
        
        try:
            # Set PYTHONPATH to include the temp dir
            # This ensures tests inside /tests/ can import files from root /
            env = os.environ.copy()
            env["PYTHONPATH"] = self.local_temp_dir
            
            print(f"       🔍 Running pytest in: {self.local_temp_dir}")
            print(f"       🔍 PYTHONPATH set to: {self.local_temp_dir}")
            
            # Run Pytest with more verbose output
            result = subprocess.run(
                ["pytest", ".", "-v", "--tb=short"], 
                cwd=self.local_temp_dir, 
                env=env,
                capture_output=True, 
                text=True,
                timeout=15
            )
            
            output = result.stdout + result.stderr
            success = (result.returncode == 0)
            
            # Show test output for debugging
            print(f"\n       📋 Test Output:")
            print("       " + "\n       ".join(output.split('\n')[:20]))  # First 20 lines
            
            # Parse results
            passed, failed, total = 0, 0, 0
            
            pass_match = re.search(r'(\d+) passed', output)
            fail_match = re.search(r'(\d+) failed', output)
            err_match  = re.search(r'(\d+) error', output)
            
            if pass_match: passed = int(pass_match.group(1))
            if fail_match: failed = int(fail_match.group(1))
            if err_match:  failed += int(err_match.group(1))
            
            total = passed + failed
            
            if total == 0 and not success: 
                total, failed = 1, 1  # Syntax error fallback
                print(f"       ⚠️  No tests collected - likely import/syntax error")
            
            print(f"       ✅ Passed: {passed}/{total}")
            print(f"       ❌ Failed: {failed}/{total}")
            
            return {
                "success": success,
                "output": output,
                "passed": passed,
                "failed": failed,
                "errors": 0
            }
            
        except Exception as e:
            print(f"       ❌ Error running tests: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "output": str(e), "passed": 0, "failed": 0, "errors": 1}
        
        result = subprocess.run(
            ['pytest', test_file, '-v', '--tb=short'],
            capture_output=True,
            text=True
        )
        
        output = result.stdout + result.stderr
        
        # Parse pytest output
        passed = len(re.findall(r'PASSED', output))
        failed = len(re.findall(r'FAILED', output))
        errors = len(re.findall(r'ERROR', output))
        
        print(f"       ✅ Passed: {passed}")
        print(f"       ❌ Failed: {failed}")
        print(f"       ⚠️  Errors: {errors}")
        
        return {"passed": passed, "failed": failed, "errors": errors}

    def agent_lead_summary(self, mr):
        """Tech Lead reviews MR and provides strategic assessment"""
        print(f"\n2️⃣  [Agent Lead] Executive Review...")
        mr_full = self.project.mergerequests.get(mr.iid)
        changes = mr_full.changes()
        
        diff_context = ""
        for c in changes['changes']:
            diff_context += f"File: {c['new_path']}\n{c['diff']}\n"
        
        lead_input = f"""
        MR TITLE: {mr.title}
        MR DESCRIPTION: {mr.description}
        
        CODE DIFF:
        {diff_context}
        """
        
        # Log the prompt
        self.log_prompt("lead", prompts.LEAD_SYSTEM_PROMPT, lead_input, MODEL_BIG)
        
        response = self._ask_gemini(prompts.LEAD_SYSTEM_PROMPT, lead_input, model_name=MODEL_BIG)
        
        try:
            lead_context = json.loads(response)
            print(f"    📝 Decision: {lead_context.get('final_decision', 'N/A')}")
            print(f"    ⚠️  Risk: {lead_context.get('risk_assessment', 'N/A')}")
            return lead_context
        except Exception as e:
            print(f"    ❌ Lead Agent Error: {e}")
            return {
                'final_decision': 'CHANGES_REQUESTED',
                'architect_instructions': 'Review for critical bugs.'
            }

    def agent_architect_review(self, mr, scenario_key, lead_context):
        """
        Principal Architect reviews code with repository context
        **KEY MODIFICATION: Includes repo context in the prompt**
        """
        print(f"\n🧠 [Agent Architect] Analyzing Logic WITH CONTEXT...")
        mr_full = self.project.mergerequests.get(mr.iid)
        changes = mr_full.changes()
        
        diff_context = ""
        for c in changes['changes']:
            diff_context += f"File: {c['new_path']}\n{c['diff']}\n"
        
        # Debug output
        if not diff_context.strip():
            print(f"    ⚠️  WARNING: No diff found in MR changes!")
            print(f"    Changes structure: {changes.keys()}")
            
        cto_instructions = lead_context.get('architect_instructions', 'Review for critical logic errors.')
        print(f"    ℹ️  CTO Directives: {cto_instructions}")
        print(f"    📚 Context Length: {len(self.repo_context)} chars")
        print(f"    📝 Diff Length: {len(diff_context)} chars")

        # **MODIFIED: Include repository context in the prompt**
        architect_input = f"""
### REPOSITORY CONTEXT (Reference Only)
{self.repo_context}

### CTO DIRECTIVES
{cto_instructions}

### CODE DIFF TO FIX
{diff_context}
"""
        
        # Log the prompt
        self.log_prompt("architect", prompts.ARCHITECT_SYSTEM_PROMPT, architect_input, MODEL_SMALL)
        
        response = self._ask_gemini(prompts.ARCHITECT_SYSTEM_PROMPT, architect_input, model_name=MODEL_SMALL)
        collected_fixes = []
        
        if not response:
            print(f"    ❌ Empty response from Gemini")
            return []
        
        try:
            # Try to extract JSON from markdown code blocks if present
            json_text = response.strip()
            if '```json' in json_text:
                # Extract from ```json ... ``` block
                start = json_text.find('```json') + 7
                end = json_text.find('```', start)
                json_text = json_text[start:end].strip()
            elif '```' in json_text:
                # Extract from ``` ... ``` block
                start = json_text.find('```') + 3
                end = json_text.find('```', start)
                json_text = json_text[start:end].strip()
            
            issues = json.loads(json_text)
            print(f"    🔍 Found {len(issues)} issues.")
            
            # Only try to post comments if there are issues
            if len(issues) == 0:
                return []
            
            ver = mr_full.diffs.list()[0]
            base_sha, head_sha, start_sha = ver.base_commit_sha, ver.head_commit_sha, ver.start_commit_sha
            
            for issue in issues:
                collected_fixes.append(issue)
                target_line = self._find_line_in_diff(changes['changes'], issue['file_path'], issue['bad_code_snippet'])
                if target_line:
                    body = (
                        f"🛑 **{issue['issue_type']}**\n\n"
                        f"{issue['description']}\n"
                        f"```suggestion\n{issue['suggested_fix']}\n```"
                    )
                    pos = {
                        'base_sha': base_sha, 'start_sha': start_sha, 'head_sha': head_sha, 
                        'position_type': 'text', 'new_path': issue['file_path'], 'new_line': target_line
                    }
                    try:
                        mr_full.discussions.create({'body': body, 'position': pos})
                        print(f"      ✅ Comment posted on {issue['file_path']}:{target_line}")
                    except Exception as e:
                        print(f"      ⚠️ Failed to post comment: {e}")
            return collected_fixes
            
        except json.JSONDecodeError as e:
            print(f"    ❌ JSON Parse Error: {e}")
            print(f"    📄 First 500 chars of response:")
            print(f"    {response[:500]}")
            return []
        except Exception as e:
            print(f"    ❌ Architect Agent Error: {e}")
            print(f"    📄 First 500 chars of response:")
            print(f"    {response[:500]}")
            return []

    def _find_line_in_diff(self, diff_list, filename, snippet):
        """Find line number in diff for a code snippet"""
        clean_snippet = snippet.strip().replace(" ", "").replace("\t", "")
        for change in diff_list:
            if change['new_path'] == filename:
                curr = 0
                for line in change['diff'].split('\n'):
                    if line.startswith('@@'):
                        try:
                            curr = int(line.split('+')[1].split(',')[0]) - 1
                        except:
                            pass
                        continue
                    if not line.startswith('-'):
                        if line.startswith('+'):
                            curr += 1
                            clean_line = line[1:].strip().replace(" ", "").replace("\t", "")
                            if clean_snippet in clean_line:
                                return curr
                        elif not line.startswith('diff') and not line.startswith('index'):
                            curr += 1
        return None

    def apply_fixes_commit_and_merge(self, mr, file_map, fixes, scenario_data):
        """Apply fixes from architect via LLM integration, commit via API, and merge"""
        print(f"\n3️⃣  [Apply Fixes] Implementing suggestions...")
        
        if not fixes:
            print("    ⚠️ No fixes to apply")
            return {"success": False, "output": "No fixes provided", "passed": 0, "failed": 0, "errors": 0}

        # 1. Group fixes by file
        fixes_by_file = {}
        for fix in fixes:
            path = fix['file_path']
            if path not in fixes_by_file: 
                fixes_by_file[path] = []
            fixes_by_file[path].append(fix)

        files_to_update = {}

        # 2. Use LLM to apply changes (matching original pipeline)
        for path, file_fixes in fixes_by_file.items():
            if path not in file_map:
                print(f"    ⚠️  Warning: Fix targets {path}, but file not found. Skipping.")
                continue

            print(f"    🤖 AI integrating {len(file_fixes)} fixes into {path}...")
            original_content = file_map[path]
            
            suggestions_text = ""
            for i, f in enumerate(file_fixes):
                suggestions_text += f"--- FIX #{i+1} ({f['issue_type']}) ---\n"
                suggestions_text += f"Replace:\n{f['bad_code_snippet']}\n"
                suggestions_text += f"With:\n{f['suggested_fix']}\n\n"
            
            integration_prompt = f"""
            You are a strict code integration engine.
            Your task is to apply specific bug fixes to a Python file.

            ORIGINAL CODE:
            ```python
            {original_content}
            ```

            FIXES TO APPLY:
            {suggestions_text}

            INSTRUCTIONS:
            1. Apply the "With" code over the "Replace" code.
            2. If the new code introduces types (like 'Decimal') or modules that are not imported, you MUST add the import at the top of the file.
            3. Do NOT change any other logic, variable names, or formatting.
            4. Output the COMPLETE, valid Python file.
            5. Do not output markdown code blocks, just the raw code.
            """
            
            new_content = self._ask_gemini("You are a code integration tool.", integration_prompt, model_name=MODEL_SMALL, temperature=0.0)
            file_map[path] = new_content  # UPDATE FILE_MAP - critical!
            files_to_update[path] = new_content

        if not files_to_update:
            print("    ❌ No files were updated by AI. Skipping Merge.")
            return {"success": False, "output": "AI generation failed", "passed": 0, "failed": 0, "errors": 0}

        # 3. Commit via GitLab API (not local git)
        print(f"    📤 Committing {len(files_to_update)} fixed files to GitLab...")
        
        branch_name = scenario_data['branch']
        
        actions = []
        for f_path, f_content in files_to_update.items():
            actions.append({'action': 'update', 'file_path': f_path, 'content': f_content})
            
        try:
            self.project.commits.create({
                'branch': branch_name,
                'commit_message': 'fix: apply AI suggestions (automated)',
                'actions': actions
            })
            print("    ✅ Changes pushed to feature branch.")
            time.sleep(2)
        except Exception as e:
            print(f"    ❌ Git Commit failed: {e}")
            return {"success": False, "output": f"Git Commit failed: {e}", "passed": 0, "failed": 0, "errors": 0}

        # 4. Merge MR
        print(f"    🔀 Merging MR {mr.iid} into Main...")
        try:
            mr_obj = self.project.mergerequests.get(mr.iid)
            mr_obj.merge()
            attempts = 0
            while mr_obj.state != 'merged' and attempts < 10:
                print("       Waiting for merge...")
                time.sleep(2)
                mr_obj = self.project.mergerequests.get(mr.iid)
                attempts += 1
            if mr_obj.state != 'merged':
                print(f"    ⚠️  Merge state is '{mr_obj.state}', attempting to proceed with tests anyway...")
            else:
                print("    ✅ MR Merged successfully.")
        except Exception as e:
            print(f"    ❌ Merge failed: {e}")
        
        # 5. Run tests on UPDATED file_map (critical!)
        return self.run_local_tests(file_map, "POST-MERGE")

    def post_benchmark_results(self, mr, pre_result, post_result):
        """Post comparison of test results to MR"""
        print(f"\n4️⃣  [Results] Posting benchmark...")
        
        body = f"""
## 🧪 Test Results

### Before AI Fixes:
- ✅ Passed: {pre_result['passed']}
- ❌ Failed: {pre_result['failed']}
- ⚠️  Errors: {pre_result['errors']}

### After AI Fixes:
- ✅ Passed: {post_result['passed']}
- ❌ Failed: {post_result['failed']}
- ⚠️  Errors: {post_result['errors']}

### Verdict:
"""
        if post_result['failed'] == 0 and post_result['errors'] == 0:
            body += "✅ **ALL TESTS PASSED** - AI fixes successful!"
        else:
            body += "⚠️ Some tests still failing - needs review"
        
        mr_full = self.project.mergerequests.get(mr.iid)
        mr_full.notes.create({'body': body})
        print("    ✅ Results posted")

    def finish(self):
        """Cleanup"""
        try:
            shutil.rmtree(self.local_temp_dir)
            print("\n👋 Cleaned up local temp files.")
        except:
            pass


# Copy the same loader and main from original pipeline
def load_benchmarks_with_base_files(folder_path="benchmarks"):
    """Load benchmark scenarios from Python files"""
    all_cases = []
    
    if not os.path.exists(folder_path):
        print(f"❌ Folder '{folder_path}' not found")
        return []
    
    for filename in sorted(os.listdir(folder_path)):
        if filename.endswith('.py') and filename.startswith('scenarios'):
            filepath = os.path.join(folder_path, filename)
            
            try:
                with open(filepath, 'r') as f:
                    code = f.read()
                
                local_vars = {}
                exec(code, {}, local_vars)
                
                scenarios = local_vars.get('BENCHMARK_SCENARIOS', {})
                base_files = local_vars.get('BASE_REPO_FILES', {})
                
                for scenario_key, scenario_data in scenarios.items():
                    all_cases.append({
                        "id": scenario_key,
                        "data": scenario_data,
                        "base_files": base_files,
                        "filename": filename
                    })
                    
            except Exception as e:
                print(f"⚠️ Error loading {filename}: {e}")
                continue
    
    return all_cases


if __name__ == "__main__":
    all_cases = load_benchmarks_with_base_files("benchmarks")
    
    if not all_cases:
        print("❌ No scenarios found")
        exit()

    print(f"\n🚀 STARTING SUITE WITH CONTEXT: {len(all_cases)} Scenarios Queued.")
    
    stats = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "details": []}
    start_time_total = time.time()

    for index, case in enumerate(all_cases):
        stats["total"] += 1
        scenario_key = case["id"]
        scenario_data = case["data"]
        base_files = case["base_files"]
        
        print(f"\n" + "="*60)
        print(f"▶️  RUNNING CASE {index+1}/{len(all_cases)}: {scenario_key}")
        print(f"    Source: {case['filename']}")
        print("="*60)

        pipeline = UnifiedPipelineWithContext()
        pipeline.current_scenario = scenario_key  # Set for logging
        case_result = "ERROR"
        mr_link = "N/A"
        
        try:
            pipeline.cleanup(project_name_filter = scenario_key)
            
            mr, file_map = pipeline.setup_repo_and_mr(scenario_key, scenario_data, base_files)
            mr_link = mr.web_url
            
            pre_result = pipeline.run_local_tests(file_map, "PRE-FIX")
            lead_context = pipeline.agent_lead_summary(mr)
            fixes = pipeline.agent_architect_review(mr, scenario_key, lead_context)
            
            pipeline.apply_fixes_commit_and_merge(mr, file_map, fixes, scenario_data)
            
            post_result = pipeline.run_local_tests(file_map, "POST-FIX")
            pipeline.post_benchmark_results(mr, pre_result, post_result)
            
            if post_result['failed'] == 0 and post_result['errors'] == 0:
                case_result = "PASS"
                stats["passed"] += 1
                print(f"    🏆 SCENARIO PASSED (WITH CONTEXT)")
            else:
                case_result = "FAIL"
                stats["failed"] += 1
                print(f"    💀 SCENARIO FAILED (WITH CONTEXT)")
                
        except Exception as e:
            case_result = "CRASH"
            stats["errors"] += 1
            print(f"    ❌ CRASH: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            pipeline.finish()
            stats["details"].append({"scenario": scenario_key, "result": case_result, "mr_url": mr_link})
            time.sleep(2)
    
    # Summary
    duration = time.time() - start_time_total
    print("\n" + "="*60)
    print("🏁  SUITE COMPLETE (WITH CONTEXT)")
    print("="*60)
    print(f"⏱️  Duration: {duration:.2f}s")
    print(f"✅ Passed: {stats['passed']}/{stats['total']}")
    print(f"❌ Failed: {stats['failed']}/{stats['total']}")
    print(f"⚠️  Errors: {stats['errors']}/{stats['total']}")
    print("\nDetails:")
    for det in stats["details"]:
        icon = "✅" if det['result'] == "PASS" else ("❌" if det['result'] == "FAIL" else "⚠️")
        print(f"{icon} {det['scenario']:<30} | {det['result']} | {det['mr_url']}")
