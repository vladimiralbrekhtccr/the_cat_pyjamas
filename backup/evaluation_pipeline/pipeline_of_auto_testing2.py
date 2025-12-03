import os
import time
import json
import shutil
import tempfile
import subprocess
import re  # <--- FIX 1: Added missing import
import gitlab
from dotenv import load_dotenv
from google import genai
from google.genai import types

# --- IMPORTS ---
import prompts_old as prompts
#import scenarios2 as scenarios 
import glob
import importlib.util
import sys

load_dotenv()

# --- CONFIGURATION ---
GITLAB_URL = "https://gitlab.com"
GROUP_PATH = "vladimiralbrekhtccr-group" #"the_cat_pyjamas" 
# Ensure these models exist in your API access
MODEL_BIG = "gemini-2.0-flash" 
MODEL_SMALL = "gemini-2.0-flash-lite"

class UnifiedPipeline:
    
    def __init__(self):
        self.gl = gitlab.Gitlab(GITLAB_URL, private_token=os.getenv("GITLAB_TOKEN_TESTING"))
        self.gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        self.project = None
        self.local_temp_dir = tempfile.mkdtemp()
        print(f"📁 Local Test Environment created at:\n    {self.local_temp_dir}")

    def cleanup(self, project_name_filter="bank-unified"):
        """Delete old repos to keep GitLab clean."""
        print("\n🧹 [Cleanup] Checking for old projects...")
        try:
            projects = self.gl.projects.list(search=project_name_filter, simple=True)
            for p in projects:
                print(f"   - Deleting {p.name}...")
                p.delete()
            time.sleep(2)
        except Exception as e:
            print(f"   Warning during cleanup: {e}")

    # --- FIX 2: Renamed 'model' to 'model_name' to match calls later in script ---
    # --- FIX 3: Removed 'thinkingConfig' to prevent API errors on standard Flash models ---
    def _ask_gemini(self, system_prompt, user_content, temperature=0.1, model_name="gemini-2.0-flash"):
        max_retries = 3
        attempt = 0
        base_delay = 2  # Seconds

        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=system_prompt), types.Part.from_text(text=user_content)],
            )
        ]
        
        config = types.GenerateContentConfig( 
            temperature=temperature, 
            max_output_tokens=2000, 
            #thinkingConfig = { "thinkingBudget": 0, }, 
            )
        while attempt < max_retries:
            try:
                full_text = ""
                # Stream the response
                for chunk in self.gemini_client.models.generate_content_stream(model=model_name, contents=contents, config=config):
                    # --- FIX 1: Check if text exists before concatenating ---
                    if chunk.text: 
                        full_text += chunk.text
                
                # If we got here, generation was successful
                clean_text = full_text.strip()
                
                # Robust Markdown Cleaning
                if clean_text.startswith("```python"):
                    clean_text = clean_text[9:].strip()
                elif clean_text.startswith("```json"):
                    clean_text = clean_text[7:].strip()
                elif clean_text.startswith("```"):
                    clean_text = clean_text[3:].strip()
                    
                if clean_text.endswith("```"):
                    clean_text = clean_text[:-3].strip()
                    
                return clean_text

            except Exception as e:
                attempt += 1
                print(f"    ⚠️ API Error (Attempt {attempt}/{max_retries}): {e}")
                
                if attempt < max_retries:
                    sleep_time = base_delay * (2 ** (attempt - 1)) # Exponential backoff: 2, 4, 8...
                    print(f"       Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    print("    ❌ Max retries reached. Returning empty JSON.")
                    return "{}" # Return valid JSON string to prevent json.loads crash later
    # --- 1. SETUP REPO ---
# --- 1. SETUP REPO (Updated to accept specific Base Files) ---
    def setup_repo_and_mr(self, scenario_name, scenario_data, base_files):
        project_name = f"{scenario_name}-{int(time.time())}"
        
        print(f"\n🏗️  Creating Repo: {project_name}...")
        
        try:
            group = self.gl.groups.get(GROUP_PATH)
            self.project = self.gl.projects.create({'name': project_name, 'namespace_id': group.id})
        except:
            self.project = self.gl.projects.create({'name': project_name})

        # 1. Setup MAIN Branch 
        # Use the specific BASE_FILES passed from the loaded module
        files_to_commit = base_files.copy()
        files_to_commit.update(scenario_data['tests'])
        
        actions = [{'action': 'create', 'file_path': k, 'content': v} for k, v in files_to_commit.items()]
        
        self.project.commits.create({
            'branch': 'main',
            'commit_message': 'Init: Base architecture and tests',
            'actions': actions
        })
        time.sleep(1)

        # 2. Setup Feature Branch
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
        
        print(f"✅  Repo Ready: {self.project.web_url}")
        
        # Prepare file map
        full_file_map = files_to_commit.copy()
        full_file_map.update(scenario_data['changes'])
        
        return mr, full_file_map
    # --- 2. LOCAL TESTING ENGINE ---
# --- 2. LOCAL TESTING ENGINE ---
    def run_local_tests(self, file_map, stage_name):
        print(f"\n🧪 [{stage_name}] Writing files and running Pytest...")
        
        # Write files
        for filename, content in file_map.items():
            path = os.path.join(self.local_temp_dir, filename)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                f.write(content)
        
        try:
            # --- FIX: Set PYTHONPATH to include the temp dir ---
            # This ensures tests inside /tests/ can import files from root /
            env = os.environ.copy()
            env["PYTHONPATH"] = self.local_temp_dir
            
            # Run Pytest
            result = subprocess.run(
                ["pytest", ".", "-v"], 
                cwd=self.local_temp_dir, 
                env=env, # <--- Pass the modified environment here
                capture_output=True, 
                text=True,
                timeout=15
            )
            
            output = result.stdout + result.stderr
            success = (result.returncode == 0)
            
            # PARSE RESULTS
            passed, failed, total = 0, 0, 0
            
            pass_match = re.search(r'(\d+) passed', output)
            fail_match = re.search(r'(\d+) failed', output)
            err_match  = re.search(r'(\d+) error', output)
            
            if pass_match: passed = int(pass_match.group(1))
            if fail_match: failed = int(fail_match.group(1))
            if err_match:  failed += int(err_match.group(1)) 
            
            total = passed + failed
            
            if total == 0 and not success: total, failed = 1, 1 # Syntax error fallback
            
            score_str = f"{passed}/{total}"
            print(f"   Status: {'PASSED' if success else 'FAILED'} ({score_str})")

            return {
                "success": success,
                "output": output,
                "passed_count": passed,
                "total_count": total,
                "score_str": score_str
            }

        except Exception as e:
            print(f"   Error running tests: {e}")
            return {"success": False, "output": str(e), "passed_count": 0, "total_count": 0, "score_str": "Error"}

    # --- 3. AGENT: LEAD (Summary) ---
    def agent_lead_summary(self, mr):
        print(f"\n👔 [Agent Lead] reviewing MR...")
        mr_full = self.project.mergerequests.get(mr.iid)
        changes = mr_full.changes()
        diff_text = "\n".join([c['diff'] for c in changes['changes']])
        
        prompt_input = f"TITLE: {mr.title}\nDESC: {mr.description}\nDIFF:\n{diff_text}"
        response = self._ask_gemini(prompts.LEAD_SYSTEM_PROMPT, prompt_input, model_name=MODEL_BIG)
        
        try:
            res = json.loads(response)
            
            # Add Labels
            mr_full.labels = res.get('labels_to_add', [])
            mr_full.save()
            
            # Post Comment
            body = (
                f"### 📋 Executive Summary\n\n"
                f"**TL;DR:** {res['tldr']}\n"
                f"**Risk Level:** {res['risk_assessment']}\n\n"
                f"{res['review_summary']}\n\n"
                f"**Decision:** {res['final_decision']}"
            )
            mr_full.notes.create({'body': body})
            print(f"    ✅ Summary posted.")
            return res
        except Exception as e:
            print(f"    ❌ Lead Agent failed: {e}")
            return {}

    # --- 4. AGENT: ARCHITECT (Inline Fixes) ---
    def agent_architect_review(self, mr, scenario_key, lead_context):
        print(f"\n🧠 [Agent Architect] Analyzing Logic...")
        mr_full = self.project.mergerequests.get(mr.iid)
        changes = mr_full.changes()
        
        diff_context = ""
        for c in changes['changes']:
            diff_context += f"File: {c['new_path']}\n{c['diff']}\n"
            
        cto_instructions = lead_context.get('architect_instructions', 'Review for critical logic errors.')
        print(f"    ℹ️  CTO Directives: {cto_instructions}")

        architect_input = f"""
        CTO DIRECTIVES:
        "{cto_instructions}"
        
        CODE DIFF TO FIX:
        {diff_context}
        """
        
        response = self._ask_gemini(prompts.ARCHITECT_SYSTEM_PROMPT, architect_input, model_name=MODEL_SMALL)
        collected_fixes = []
        
        try:
            issues = json.loads(response)
            print(f"    🔍 Found {len(issues)} issues.")
            
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
            
        except Exception as e:
            print(f"    ❌ Architect Agent Error: {e}")
            return []

    def _find_line_in_diff(self, diff_list, filename, snippet):
        snippet = snippet.strip()
        for change in diff_list:
            if change['new_path'] == filename:
                curr = 0
                for line in change['diff'].split('\n'):
                    if line.startswith('@@'):
                        try: curr = int(line.split('+')[1].split(',')[0]) - 1
                        except: pass
                    if line.startswith('+') and not line.startswith('+++'):
                        curr += 1
                        if snippet in line.strip(): return curr
        return None
    # --- 5. APPLY FIXES, COMMIT & MERGE (Updated to use scenario_data) ---
    def apply_fixes_commit_and_merge(self, mr, file_map, fixes, scenario_data):
        print(f"\n🛠️  [Pipeline] Applying fixes via LLM Integration & Git Merge...")
        
        if not fixes:
            return {"success": False, "output": "No fixes provided", "passed_count": 0, "total_count": 0, "score_str": "N/A"}

        # 1. Group fixes by file
        fixes_by_file = {}
        for fix in fixes:
            path = fix['file_path']
            if path not in fixes_by_file: fixes_by_file[path] = []
            fixes_by_file[path].append(fix)

        files_to_update = {} 

        # 2. Iterate and ask LLM to apply changes
        for path, file_fixes in fixes_by_file.items():
            if path not in file_map:
                print(f"⚠️ Warning: Fix targets {path}, but file not found. Skipping.")
                continue

            print(f"    ... AI integrating {len(file_fixes)} fixes into {path}...")
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
            file_map[path] = new_content
            files_to_update[path] = new_content

        if not files_to_update:
            print("    ❌ No files were updated by AI. Skipping Merge.")
            return {"success": False, "output": "AI generation failed", "passed_count": 0, "total_count": 0, "score_str": "0/0"}

        # 3. Commit Changes
        print(f"    📤 Committing {len(files_to_update)} fixed files to GitLab...")
        
        # USE THE PASSED DATA, NOT GLOBAL LOOKUP
        branch_name = scenario_data['branch']
        
        actions = []
        for f_path, f_content in files_to_update.items():
            actions.append({ 'action': 'update', 'file_path': f_path, 'content': f_content })
            
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
            return {"success": False, "output": f"Git Commit failed: {e}", "passed_count": 0, "total_count": 0, "score_str": "Error"}

        # 4. Merge
        print(f"    🔀 Merging MR {mr.iid} into Main...")
        try:
            mr = self.project.mergerequests.get(mr.iid)
            mr.merge()
            attempts = 0
            while mr.state != 'merged' and attempts < 10:
                print("       Waiting for merge...")
                time.sleep(2)
                mr = self.project.mergerequests.get(mr.iid)
                attempts += 1
            if mr.state != 'merged':
                print(f"    ⚠️ Merge state is '{mr.state}', attempting to proceed with tests anyway...")
            else:
                print("    ✅ MR Merged successfully.")
        except Exception as e:
            print(f"    ❌ Merge failed: {e}")
        
        return self.run_local_tests(file_map, "POST-MERGE")
    # --- 6. FINAL REPORTING ---
    def post_benchmark_results(self, mr, pre_result, post_result):
        print(f"\n📊 [Pipeline] Posting Benchmark Results to GitLab...")
        
        pre_icon = "🟢" if pre_result['success'] else "🔴"
        post_icon = "🟢" if post_result['success'] else "🔴"
        final_success = post_result['success']
        final_icon = "🏆" if final_success else "💀"
        
        pre_log = pre_result['output'][-800:].replace("```", "")
        post_log = post_result['output'][-800:].replace("```", "")

        table = (
            f"### 🧪 Automated Benchmark Report\n\n"
            f"| Stage | Status | Score | Details |\n"
            f"|-------|:------:|:-----:|---------|\n"
            f"| **Pre-Fix** | {pre_icon} {'Passed' if pre_result['success'] else 'Failed'} | **{pre_result['score_str']}** | Original Code |\n"
            f"| **Post-Fix** | {post_icon} {'Passed' if post_result['success'] else 'Failed'} | **{post_result['score_str']}** | AI Auto-Fix |\n\n"
            f"**Conclusion:** {final_icon} **{'BENCHMARK PASSED' if final_success else 'BENCHMARK FAILED'}**\n\n"
            f"<details><summary>🔍 View Test Logs</summary>\n\n"
            f"**Pre-Fix Output:**\n```\n{pre_log}\n```\n\n"
            f"**Post-Fix Output:**\n```\n{post_log}\n```\n"
            f"</details>"
        )
        
        try:
            mr.notes.create({'body': table})
            print("    ✅ Benchmark Report Posted.")
        except Exception as e:
            print(f"    ❌ Failed to post report: {e}")

    def finish(self):
        try:
            shutil.rmtree(self.local_temp_dir)
            print("\n👋 Cleaned up local temp files.")
        except: pass



# ======================================================
# DYNAMIC SCENARIO LOADER
# ======================================================
def load_benchmarks_with_base_files(folder_path="benchmarks"):
    """
    Loads .py files. Expects each file to have:
    1. BENCHMARK_SCENARIOS (Dict with 1 key)
    2. BASE_REPO_FILES (Dict)
    """
    loaded_cases = []
    
    if not os.path.exists(folder_path):
        print(f"⚠️ Folder '{folder_path}' not found.")
        return []

    file_paths = glob.glob(os.path.join(folder_path, "*.py"))
    print(f"\n📂 Loading benchmarks from '{folder_path}'...")

    for file_path in file_paths:
        module_name = os.path.basename(file_path).replace(".py", "")
        if module_name.startswith("__"): continue 

        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Check if module has required attributes
            if hasattr(module, "BENCHMARK_SCENARIOS") and hasattr(module, "BASE_REPO_FILES"):
                # Extract the single test case from this file
                for key, data in module.BENCHMARK_SCENARIOS.items():
                    loaded_cases.append({
                        "id": key,
                        "data": data,
                        "base_files": module.BASE_REPO_FILES,
                        "filename": module_name
                    })
                    print(f"   🔹 Loaded: {key} (from {module_name}.py)")
            else:
                print(f"   ⚠️ Skipping {module_name}: Missing BENCHMARK_SCENARIOS or BASE_REPO_FILES")
                
        except Exception as e:
            print(f"   ❌ Error loading {file_path}: {e}")

    return loaded_cases
if __name__ == "__main__":
    
    # 1. Load Scenarios
    # Create a folder named 'benchmarks' in root and put your python files there
    all_cases = load_benchmarks_with_base_files("benchmarks")
    
    if not all_cases:
        print("❌ No scenarios found. Please create a 'benchmarks' folder with scenario files.")
        exit()

    print(f"\n🚀 STARTING SUITE: {len(all_cases)} Scenarios Queued.")
    
    stats = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "details": []}
    start_time_total = time.time()

    # 2. Iterate through loaded cases
    for index, case in enumerate(all_cases):
        stats["total"] += 1
        scenario_key = case["id"]
        scenario_data = case["data"]
        base_files = case["base_files"]
        
        print(f"\n" + "="*60)
        print(f"▶️  RUNNING CASE {index+1}/{len(all_cases)}: {scenario_key}")
        print(f"    Source: {case['filename']}")
        print("="*60)

        pipeline = UnifiedPipeline()
        case_result = "ERROR"
        mr_link = "N/A"
        
        try:
            pipeline.cleanup(project_name_filter = scenario_key)
            
            # PASS THE SPECIFIC BASE FILES & DATA HERE
            mr, file_map = pipeline.setup_repo_and_mr(scenario_key, scenario_data, base_files)
            mr_link = mr.web_url
            
            print("    🧪 Running Pre-Fix Tests...")
            pre_result = pipeline.run_local_tests(file_map, "PRE-FIX")
            
            print("    🤖 Running AI Agents...")
            lead_context = pipeline.agent_lead_summary(mr)
            fixes = pipeline.agent_architect_review(mr, scenario_key, lead_context)
            
            print("    🛠️  Fixing and Merging...")
            # PASS THE SPECIFIC DATA HERE
            post_result = pipeline.apply_fixes_commit_and_merge(mr, file_map, fixes, scenario_data)
            
            pipeline.post_benchmark_results(mr, pre_result, post_result)
            
            if post_result['success']:
                case_result = "PASS"
                stats["passed"] += 1
                print(f"    🏆 SCENARIO PASSED")
            else:
                case_result = "FAIL"
                stats["failed"] += 1
                print(f"    💀 SCENARIO FAILED")

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
    print("🏁  SUITE COMPLETE")
    print("="*60)
    print(f"⏱️  Duration: {duration:.2f}s")
    print(f"📊  Total: {stats['total']} | ✅ Pass: {stats['passed']} | ❌ Fail: {stats['failed']} | ⚠️ Err: {stats['errors']}")
    for det in stats["details"]:
        icon = "✅" if det['result'] == "PASS" else ("❌" if det['result'] == "FAIL" else "⚠️")
        print(f"{icon} {det['scenario']:<30} | {det['result']} | {det['mr_url']}")