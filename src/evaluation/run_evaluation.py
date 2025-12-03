import os
import sys
import time
import json
import shutil
import tempfile
import subprocess
import re
import gitlab
import glob
import importlib.util
import argparse
from dotenv import load_dotenv

# --- PATH SETUP TO IMPORT CORE ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from core import prompts
from core.llm_providers import GeminiProvider, OpenAIProvider

load_dotenv()

# --- CONFIGURATION DEFAULTS ---
GITLAB_URL = "https://gitlab.com"
DEFAULT_GROUP = "evaluation_pipeline_test" 
DEFAULT_LOCAL_URL = "http://localhost:6655/v1"

class UnifiedPipeline:
    
    def __init__(self, provider_type="gemini", group_path=DEFAULT_GROUP, local_url=DEFAULT_LOCAL_URL):
        self.gl = gitlab.Gitlab(GITLAB_URL, private_token=os.getenv("GITLAB_TOKEN_TESTING"))
        self.local_temp_dir = tempfile.mkdtemp()
        self.project = None
        self.group_path = group_path 
        
        # 1. GET USER ID FROM ENV (for safe concurrent running)
        self.user_id = os.getenv("GITLAB_USER_ID", "anon")

        # 2. INITIALIZE CHOSEN PROVIDER
        if provider_type == "local":
            print(f"🔌 Connecting to Local LLM at: {local_url}")
            self.llm = OpenAIProvider(
                api_key="EMPTY", 
                base_url=local_url,  # <--- USES THE ARGUMENT HERE
                model_name="qwen3_30b_deployed" # You might want to param this too eventually
            )
        elif provider_type == "openai":
            self.llm = OpenAIProvider(
                api_key=os.getenv("OPENAI_API_KEY"), 
                base_url="https://api.openai.com/v1", 
                model_name="gpt-4-turbo"
            )
        else: # Default to Gemini
            self.llm = GeminiProvider(
                api_key=os.getenv("GEMINI_API_KEY"),
                model_name="gemini-flash-latest"
            )

        print(f"📁 Local Test Environment created at:\n    {self.local_temp_dir}")
        print(f"🏢 Target GitLab Group: {self.group_path}")

    def cleanup(self, project_name_filter="bank-unified"):
        """Delete old repos belonging to this specific user."""
        user_specific_filter = f"{project_name_filter}-{self.user_id}"
        
        print(f"\n🧹 [Cleanup] Checking for old projects matching: '{user_specific_filter}'...")
        try:
            projects = self.gl.projects.list(search=user_specific_filter, simple=True, get_all=False)
            for p in projects:
                if self.user_id in p.name:
                    print(f"   - Deleting {p.name}...")
                    p.delete()
            time.sleep(2)
        except Exception as e:
            print(f"   Warning during cleanup: {e}")

    # --- WRAPPER FOR LLM ---
    def ask_llm(self, system_prompt, user_content, temperature=0.1):
        return self.llm.ask(system_prompt, user_content, temperature)

    # --- 1. SETUP REPO ---
    def setup_repo_and_mr(self, scenario_name, scenario_data, base_files):
        project_name = f"{scenario_name}-{self.user_id}-{int(time.time())}"
        
        print(f"\n🏗️  Creating Repo: {project_name}...")
        
        try:
            group = self.gl.groups.get(self.group_path)
            self.project = self.gl.projects.create({'name': project_name, 'namespace_id': group.id})
        except Exception as e:
            print(f"⚠️  Could not create project in group '{self.group_path}': {e}")
            print(f"    Falling back to User Namespace...")
            self.project = self.gl.projects.create({'name': project_name})

        # 1. Setup MAIN Branch 
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
    def run_local_tests(self, file_map, stage_name):
        print(f"\n🧪 [{stage_name}] Writing files and running Pytest...")
        
        for filename, content in file_map.items():
            path = os.path.join(self.local_temp_dir, filename)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                f.write(content)
        
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = self.local_temp_dir
            
            result = subprocess.run(
                ["pytest", ".", "-v"], 
                cwd=self.local_temp_dir, 
                env=env,
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
            if total == 0 and not success: total, failed = 1, 1
            
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
        
        response = self.ask_llm(prompts.LEAD_SYSTEM_PROMPT, prompt_input)
        
        try:
            res = json.loads(response)
            
            mr_full.labels = res.get('labels_to_add', [])
            mr_full.save()
            
            body = (
                f"### 📋 Executive Summary\n\n"
                f"**TL;DR:** {res.get('tldr', 'N/A')}\n"
                f"**Risk Level:** {res.get('risk_assessment', 'N/A')}\n\n"
                f"{res.get('review_summary', '')}\n\n"
                f"**Decision:** {res.get('final_decision', 'N/A')}"
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

        architect_input = f"CTO DIRECTIVES: \"{cto_instructions}\"\n\nCODE DIFF TO FIX:\n{diff_context}"
        
        response = self.ask_llm(prompts.ARCHITECT_SYSTEM_PROMPT, architect_input)
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
                        f"🛑 **{issue.get('issue_type', 'Bug')}**\n\n"
                        f"{issue.get('description', 'Fix needed')}\n"
                        f"```suggestion\n{issue.get('suggested_fix', '')}\n```"
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

    # --- 5. APPLY FIXES, COMMIT & MERGE ---
    def apply_fixes_commit_and_merge(self, mr, file_map, fixes, scenario_data):
        print(f"\n🛠️  [Pipeline] Applying fixes via LLM Integration & Git Merge...")
        
        if not fixes:
            return {"success": False, "output": "No fixes provided", "passed_count": 0, "total_count": 0, "score_str": "N/A"}

        fixes_by_file = {}
        for fix in fixes:
            path = fix['file_path']
            if path not in fixes_by_file: fixes_by_file[path] = []
            fixes_by_file[path].append(fix)

        files_to_update = {} 

        for path, file_fixes in fixes_by_file.items():
            if path not in file_map:
                continue

            print(f"    ... AI integrating {len(file_fixes)} fixes into {path}...")
            original_content = file_map[path]
            
            suggestions_text = ""
            for i, f in enumerate(file_fixes):
                suggestions_text += f"--- FIX #{i+1} ({f.get('issue_type','Issue')}) ---\n"
                suggestions_text += f"Replace:\n{f.get('bad_code_snippet','')}\n"
                suggestions_text += f"With:\n{f.get('suggested_fix','')}\n\n"
            
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
            2. Output the COMPLETE, valid Python file.
            3. Do not output markdown code blocks, just the raw code.
            """
            
            new_content = self.ask_llm("You are a code integration tool.", integration_prompt, temperature=0.0)
            file_map[path] = new_content
            files_to_update[path] = new_content

        if not files_to_update:
            return {"success": False, "output": "AI generation failed", "passed_count": 0, "total_count": 0, "score_str": "0/0"}

        print(f"    📤 Committing {len(files_to_update)} fixed files to GitLab...")
        branch_name = scenario_data['branch']
        actions = [{'action': 'update', 'file_path': f, 'content': c} for f, c in files_to_update.items()]
            
        try:
            self.project.commits.create({
                'branch': branch_name,
                'commit_message': 'fix: apply AI suggestions (automated)',
                'actions': actions
            })
            time.sleep(2) 
        except Exception as e:
            print(f"    ❌ Git Commit failed: {e}")
            return {"success": False, "output": f"Error: {e}", "passed_count": 0, "total_count": 0, "score_str": "Error"}

        print(f"    🔀 Merging MR {mr.iid} into Main...")
        try:
            mr = self.project.mergerequests.get(mr.iid)
            mr.merge()
            attempts = 0
            while mr.state != 'merged' and attempts < 10:
                time.sleep(2)
                mr = self.project.mergerequests.get(mr.iid)
                attempts += 1
        except Exception as e:
            print(f"    ❌ Merge failed: {e}")
        
        return self.run_local_tests(file_map, "POST-MERGE")

    # --- 6. FINAL REPORTING ---
    def post_benchmark_results(self, mr, pre_result, post_result):
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
        except: pass

    def finish(self):
        try:
            shutil.rmtree(self.local_temp_dir)
        except: pass

# ======================================================
# DYNAMIC SCENARIO LOADER
# ======================================================
def load_benchmarks_with_base_files(folder_path):
    loaded_cases = []
    if not os.path.exists(folder_path): return []

    file_paths = glob.glob(os.path.join(folder_path, "*.py"))
    
    for file_path in file_paths:
        module_name = os.path.basename(file_path).replace(".py", "")
        if module_name.startswith("__"): continue 

        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            if hasattr(module, "BENCHMARK_SCENARIOS") and hasattr(module, "BASE_REPO_FILES"):
                for key, data in module.BENCHMARK_SCENARIOS.items():
                    loaded_cases.append({
                        "id": key,
                        "data": data,
                        "base_files": module.BASE_REPO_FILES,
                        "filename": module_name
                    })
        except Exception as e:
            print(f"   ❌ Error loading {file_path}: {e}")

    return loaded_cases

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", type=str, default="gemini", choices=["gemini", "local", "openai"], help="Which LLM to use")
    
    # NEW ARGUMENT FOR LOCAL URL
    parser.add_argument("--local_url", type=str, default="http://localhost:6655/v1", help="Base URL for local LLM")

    # Default to Environment Variable, if not set, default to hardcoded string
    default_group = os.getenv("GITLAB_GROUP_PATH", "evaluation_pipeline_test")
    parser.add_argument("--group_path", type=str, default=default_group, help="GitLab Group namespace to create repos in")
    
    args = parser.parse_args()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    benchmarks_dir = os.path.join(current_dir, "benchmarks")
    all_cases = load_benchmarks_with_base_files(benchmarks_dir)
    
    if not all_cases:
        print(f"❌ No scenarios found in {benchmarks_dir}")
        exit()

    print(f"\n🚀 STARTING SUITE using [{args.provider.upper()}] in Group [{args.group_path}]")
    
    stats = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "details": []}
    
    for index, case in enumerate(all_cases):
        stats["total"] += 1
        print(f"\n▶️  RUNNING CASE {index+1}/{len(all_cases)}: {case['id']}")
        
        # Initialize tracking vars for this loop iteration
        mr_link = "N/A"
        case_result = "ERROR"

        # PASS LOCAL URL HERE
        pipeline = UnifiedPipeline(
            provider_type=args.provider, 
            group_path=args.group_path,
            local_url=args.local_url 
        )
        
        try:
            pipeline.cleanup(project_name_filter=case['id'])
            mr, file_map = pipeline.setup_repo_and_mr(case['id'], case['data'], case['base_files'])
            
            mr_link = mr.web_url

            pre_result = pipeline.run_local_tests(file_map, "PRE-FIX")
            
            lead_context = pipeline.agent_lead_summary(mr)
            fixes = pipeline.agent_architect_review(mr, case['id'], lead_context)
            
            post_result = pipeline.apply_fixes_commit_and_merge(mr, file_map, fixes, case['data'])
            
            pipeline.post_benchmark_results(mr, pre_result, post_result)
            
            if post_result['success']:
                stats["passed"] += 1
                case_result = "PASS"
                print(f"    🏆 SCENARIO PASSED")
            else:
                stats["failed"] += 1
                case_result = "FAIL"
                print(f"    💀 SCENARIO FAILED")

        except Exception as e:
            stats["errors"] += 1
            case_result = "CRASH"
            print(f"    ❌ CRASH: {e}")
        
        finally:
            pipeline.finish()
            stats["details"].append({
                "scenario": case['id'], 
                "result": case_result, 
                "mr_url": mr_link
            })
            time.sleep(2)

    print(f"\n" + "="*80)
    print(f"🏁  SUITE COMPLETE")
    print("="*80)
    print(f"📊  Total: {stats['total']} | ✅ Pass: {stats['passed']} | ❌ Fail: {stats['failed']} | ⚠️ Err: {stats['errors']}")
    print("-" * 80)
    
    print(f"{'STATUS':<8} | {'SCENARIO ID':<40} | {'MR LINK'}")
    print("-" * 80)
    for det in stats["details"]:
        icon = "✅" if det['result'] == "PASS" else ("❌" if det['result'] == "FAIL" else "⚠️")
        print(f"{icon} {det['result']:<5} | {det['scenario']:<40} | {det['mr_url']}")
    print("-" * 80)
    print(f"\n🏁  COMPLETE. Pass: {stats['passed']} | Fail: {stats['failed']}")