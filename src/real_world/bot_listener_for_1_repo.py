# src/real_world/bot_listener.py

import os
import sys
import time
import json
import gitlab
import argparse
from dotenv import load_dotenv
from datetime import datetime

# --- PATH SETUP TO IMPORT CORE ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from core import prompts
from core.llm_providers import GeminiProvider, OpenAIProvider

load_dotenv()

# --- CONFIGURATION ---
GITLAB_URL = "https://gitlab.com"
PROJECT_ID = "vladimiralbrekhtccr-group/confluent-kafka-go-temp-123456" 
SOURCE_BRANCH = "feature/full-mr-replay"
CHECK_INTERVAL = 10 

# Hardcoded commits for the Initial Demo Review
TARGET_COMMITS = [
    "4efe69fe8b19ec300d297febd5c1b9a48d90a3c3", 
    "d6fc67e3aa4b83a7a106ec45a75ba10133f1db81"
]

class UnifiedBot:
    
    def __init__(self, provider_type="gemini"):
        # 1. Setup GitLab
        self.gl = gitlab.Gitlab(GITLAB_URL, private_token=os.getenv("GITLAB_TOKEN"))
        self.project = self.gl.projects.get(PROJECT_ID)
        
        # 2. State Management
        # Stores: { mr_iid: { 'initial_done': bool, 'last_sha': str } }
        self.mr_states = {}

        # 3. Setup LLM Provider
        if provider_type == "local":
            self.llm = OpenAIProvider(
                api_key="EMPTY", 
                base_url="http://localhost:6655/v1", 
                model_name="qwen3_30b_deployed"
            )
        elif provider_type == "openai":
            self.llm = OpenAIProvider(
                api_key=os.getenv("OPENAI_API_KEY"), 
                base_url="https://api.openai.com/v1", 
                model_name="gpt-4-turbo"
            )
        else:
            self.llm = GeminiProvider(
                api_key=os.getenv("GEMINI_API_KEY"),
                model_name="gemini-flash-latest"
            )
            
        try:
            user = self.gl.user
            print(f"🤖 UnifiedBot: Connected as {user.username}")
        except:
            print(f"🤖 UnifiedBot: Connected as BOT")
        print(f"🧠 Brain: {provider_type.upper()}")

    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def check_if_initial_review_exists(self, mr):
        """
        Scans MR comments to see if the Lead Agent already posted.
        Returns True if found.
        """
        try:
            # Check last 50 notes
            notes = mr.notes.list(per_page=50)
            for note in notes:
                if "### 🤖 AI Lead Summary" in note.body:
                    return True
        except Exception as e:
            print(f"   ⚠️ Error checking MR history: {e}")
        return False

    def get_initial_diff_text(self, commits):
        """Get diffs for the Initial Review (Target Commits)"""
        diff_text = ""
        diff_list = []
        for commit_sha in commits:
            try:
                commit = self.project.commits.get(commit_sha)
                commit_diff = commit.diff()
                for change in commit_diff:
                    if change['new_path'].endswith(".go"):
                        diff_text += f"File: {change['new_path']}\nDiff:\n{change['diff']}\n\n"
                        diff_list.append(change)
            except Exception as e:
                print(f"   ⚠️ Error fetching commit {commit_sha}: {e}")
        return diff_text, diff_list

    def get_commit_diff(self, commit_sha):
        """Get diff for a single new commit (Friendly Review)"""
        try:
            commit = self.project.commits.get(commit_sha)
            commit_diff = commit.diff()
            diff_text = ""
            for change in commit_diff:
                if change['new_path'].endswith(('.go', '.py', '.js', '.java', '.cpp')):
                    diff_text += f"File: {change['new_path']}\nDiff:\n{change['diff']}\n\n"
            return diff_text, commit
        except Exception as e:
            print(f"      ❌ Error fetching diff: {e}")
            return None, None

    def _find_line_in_diff(self, diff_list, filename, snippet):
        clean_snippet = snippet.strip().replace(" ", "")
        for change in diff_list:
            if change['new_path'] == filename:
                curr = 0
                for line in change['diff'].split('\n'):
                    if line.startswith('@@'):
                        try: curr = int(line.split('+')[1].split(',')[0]) - 1
                        except: pass
                        continue
                    if not line.startswith('-'):
                        if line.startswith('+'):
                            curr += 1
                            if clean_snippet in line[1:].strip().replace(" ", ""): return curr
                        elif not line.startswith('diff') and not line.startswith('index'):
                            curr += 1
        return None

    # =========================================================================
    # AGENT PHASES
    # =========================================================================

    def run_initial_summary(self, mr, diff_text):
        print(f"   📝 [Initial] Tech Lead generating summary...")
        prompt_input = f"TITLE: {mr.title}\nDESC: {mr.description}\nDIFF:\n{diff_text}"
        
        # 1. Ask Lead Agent
        response = self.llm.ask(prompts.LEAD_SYSTEM_PROMPT, prompt_input)
        
        try:
            data = json.loads(response)
            
            # 2. Apply Labels
            valid_labels = ['ready-for-merge', 'needs-review', 'changes-requested']
            labels_to_add = [l for l in data.get('labels_to_add', []) if l in valid_labels]
            if labels_to_add:
                mr.labels = labels_to_add
                mr.save()

            # 3. Post Summary
            body = (
                f"### 🤖 AI Lead Summary\n\n"
                f"**TL;DR:** {data.get('tldr', 'N/A')}\n\n"
                f"{data.get('review_summary', '')}\n\n"
                f"**Risk:** {data.get('risk_assessment', 'UNKNOWN')}\n"
                f"**Decision:** **{data.get('final_decision', 'N/A')}**\n"
            )
            mr.notes.create({'body': body})
            
            # 4. RETURN DATA (This contains 'architect_instructions')
            return data 
        except Exception as e:
            print(f"   ❌ Error in Summary Agent: {e}")
            return {}

    def run_initial_suggestions(self, mr, diff_text, diff_list, lead_context):
        print(f"   🔧 [Initial] Architect Agent finding bugs...")
        
        # 1. Extract Instructions from Lead Context (This ensures the connection!)
        instructions = lead_context.get('architect_instructions', 'Find critical bugs.')
        print(f"      ℹ️ Instructions: {instructions[:60]}...")
        
        prompt_input = f"CTO DIRECTIVES: \"{instructions}\"\n\nCODE DIFF:\n{diff_text}"
        response = self.llm.ask(prompts.ARCHITECT_SYSTEM_PROMPT, prompt_input)
        
        try:
            bugs = json.loads(response)
            if not bugs: return

            ver = mr.diffs.list()[0]
            base_sha, head_sha, start_sha = ver.base_commit_sha, ver.head_commit_sha, ver.start_commit_sha
            
            count = 0
            for bug in bugs:
                target_line = self._find_line_in_diff(diff_list, bug['file_path'], bug['bad_code_snippet'])
                if target_line:
                    body = (
                        f"🚨 **{bug.get('severity', 'HIGH')}**\n\n"
                        f"{bug.get('description', '')}\n\n"
                        f"```suggestion\n{bug.get('suggested_fix', '')}\n```"
                    )
                    pos = {
                        'base_sha': base_sha, 'start_sha': start_sha, 'head_sha': head_sha,
                        'position_type': 'text', 'new_path': bug['file_path'], 'new_line': target_line
                    }
                    try: 
                        mr.discussions.create({'body': body, 'position': pos})
                        count += 1
                    except: pass
            print(f"      ✅ Posted {count} suggestions.")
        except Exception: pass

    def run_friendly_commit_review(self, mr, commit_sha):
        print(f"   👋 [Friendly] Reviewing new commit {commit_sha[:8]}...")
        diff_text, commit = self.get_commit_diff(commit_sha)
        
        if not diff_text:
            print(f"      ⚠️ No relevant code changes.")
            return

        commit_context = f"COMMIT: {commit_sha[:8]}\nAUTHOR: {commit.author_name}\nMSG: {commit.message}\nCHANGES:\n{diff_text}"
        response = self.llm.ask(prompts.FRIENDLY_COMMIT_PROMPT, commit_context)
        
        try:
            data = json.loads(response)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            label = data.get('status_label', 'needs-review')
            
            comment_body = (
                f"### 👋 Friendly Code Review\n\n"
                f"**Commit:** `{commit_sha[:8]}` by {commit.author_name}\n"
                f"**Time:** {timestamp}\n\n"
                f"**Feedback:** {data.get('feedback', '')}\n\n"
                f"**Status:** `{label}`\n\n"
                f"*Automated review by AI Assistant* 🤖"
            )
            
            mr.notes.create({'body': comment_body})
            
            if label in ['ready-for-merge', 'needs-review', 'changes-requested']:
                mr.labels = [label]
                mr.save()
                
            print(f"      ✅ Friendly review posted.")
        except Exception as e:
            print(f"      ❌ Friendly Error: {e}")

    # =========================================================================
    # MAIN LOOP
    # =========================================================================
    def start_listening(self):
        print(f"\n👂 Unified Listener Started.")
        print(f"   Source Branch: {SOURCE_BRANCH}")
        print(f"   Polling: {CHECK_INTERVAL}s")
        
        while True:
            try:
                timestamp = datetime.now().strftime('%H:%M:%S')
                
                # Fetch open MRs
                mrs = self.project.mergerequests.list(state='opened', source_branch=SOURCE_BRANCH, get_all=False)
                
                if mrs:
                    for mr in mrs:
                        current_sha = mr.sha
                        
                        # 1. Initialize State (If new to this script session)
                        if mr.iid not in self.mr_states:
                            print(f"\n[{timestamp}] 📋 Found MR !{mr.iid}")
                            
                            # CHECK GITLAB HISTORY
                            already_reviewed = self.check_if_initial_review_exists(mr)
                            
                            self.mr_states[mr.iid] = {
                                'initial_done': already_reviewed,
                                # If already reviewed, set last_sha to CURRENT so we wait for NEXT commit
                                'last_sha': current_sha if already_reviewed else None
                            }
                            
                            if already_reviewed:
                                print(f"   ✅ Initial review found in history. Waiting for new commits...")

                        state = self.mr_states[mr.iid]

                        # 2. Logic Flow
                        if not state['initial_done']:
                            # --- SCENARIO A: INITIAL REVIEW (Demo Mode) ---
                            print(f"\n🆕 Performing Initial Review on MR !{mr.iid}")
                            
                            # Use TARGET_COMMITS for the demo replay
                            diff_text, diff_list = self.get_initial_diff_text(TARGET_COMMITS)
                            
                            if diff_text:
                                lead_context = self.run_initial_summary(mr, diff_text)
                                time.sleep(1)
                                self.run_initial_suggestions(mr, diff_text, diff_list, lead_context)
                                print(f"✅ Initial Review Complete.")
                            
                            # Mark done and track current SHA
                            state['initial_done'] = True
                            state['last_sha'] = current_sha
                        
                        elif state['last_sha'] != current_sha:
                            # --- SCENARIO B: NEW COMMIT ADDED (Friendly Mode) ---
                            print(f"\n🔄 New commit detected on MR !{mr.iid} (Old: {state['last_sha'][:8]} -> New: {current_sha[:8]})")
                            
                            self.run_friendly_commit_review(mr, current_sha)
                            
                            # Update SHA
                            state['last_sha'] = current_sha
                        
                else:
                    pass

                time.sleep(CHECK_INTERVAL)

            except KeyboardInterrupt:
                print("\n👋 Stopping.")
                break
            except Exception as e:
                print(f"❌ Loop Error: {e}")
                time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", type=str, default="gemini", choices=["gemini", "local", "openai"], help="LLM Provider")
    args = parser.parse_args()

    bot = UnifiedBot(provider_type=args.provider)
    bot.start_listening()