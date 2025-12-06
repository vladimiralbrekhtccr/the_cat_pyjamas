### CONFIG ###
GITLAB_URL = "https://gitlab.com"
PROJECT_ID = "vladimiralbrekhtccr-group/confluent-kafka-go-temp-123456"
SOURCE_BRANCH = None
CHECK_INTERVAL = 10
DEFAULT_LOCAL_URL = "http://localhost:6655/v1"
MIN_VALID_SUGGESTIONS = 2
SIMILARITY_THRESHOLD = 0.85

LEAD_MAX_RETRIES = 30
ARCHITECT_MAX_RETRIES = 30
FRIENDLY_MAX_RETRIES = 30

### IMPORTS ###
import os
import sys
import time
import json
import gitlab
import argparse
import re
import logging
from dotenv import load_dotenv
from datetime import datetime
from difflib import SequenceMatcher

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from core import prompts
from core.llm_providers import GeminiProvider, OpenAIProvider

load_dotenv()

logging.basicConfig(
    filename='bot_listener.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

### FUNCTIONS ###
def log_llm_interaction(agent_name, prompt, response, parsed_json=None, error=None):
    log_msg = f"\n{'='*40}\nAGENT: {agent_name}\n{'='*40}\n"
    log_msg += f"--- INPUT PROMPT ---\n{prompt}\n"
    log_msg += f"--- RAW OUTPUT ---\n{response}\n"
    if error:
        log_msg += f"--- ERROR ---\n{error}\n"
    if parsed_json:
        log_msg += f"--- PARSED JSON ---\n{json.dumps(parsed_json, indent=2)}\n"
    logging.info(log_msg)

def similarity_score(a, b):
    return SequenceMatcher(None, a, b).ratio()

def normalize_code(code):
    return re.sub(r'\s+', '', code.strip())

def extract_diff_lines(diff_list):
    lines_db = []
    for change in diff_list:
        if not change['new_path'].endswith(('.go', '.py', '.js', '.java', '.cpp')):
            continue
            
        curr = 0
        for line in change['diff'].split('\n'):
            if line.startswith('@@'):
                try:
                    curr = int(line.split('+')[1].split(',')[0]) - 1
                except:
                    pass
                continue
            
            if line.startswith('-'):
                continue
            
            if line.startswith('diff') or line.startswith('index') or line.startswith('+++') or line.startswith('---'):
                continue
            
            curr += 1
            
            is_added = line.startswith('+')
            code_content = line[1:] if line else ""
            
            lines_db.append({
                'file': change['new_path'],
                'line_num': curr,
                'raw': code_content,
                'normalized': normalize_code(code_content),
                'is_added': is_added,
                'is_context': not is_added and line.startswith(' ')
            })
    
    return lines_db

def find_best_match(snippet, diff_lines_db, filename):
    if not snippet: return None
        
    norm_snippet = normalize_code(snippet)
    
    added_lines = [l for l in diff_lines_db if l['file'] == filename and l['is_added']]
    context_lines = [l for l in diff_lines_db if l['file'] == filename and l['is_context']]
    all_candidates = added_lines + context_lines
    
    if not all_candidates:
        return None
    
    best_match = None
    best_score = 0
    
    for entry in all_candidates:
        if entry['normalized'] == norm_snippet:
            logging.info(f"   ✓ Exact match on line {entry['line_num']}")
            return entry['line_num']
    
    for entry in all_candidates:
        score = similarity_score(norm_snippet, entry['normalized'])
        if score > best_score:
            best_score = score
            best_match = entry
    
    if best_score >= SIMILARITY_THRESHOLD:
        logging.info(f"   🔍 Fuzzy match: {best_score:.2f} on line {best_match['line_num']}")
        return best_match['line_num']
    
    return None

class UnifiedBot:
    def __init__(self, provider_type="gemini", local_url=DEFAULT_LOCAL_URL):
        self.gl = gitlab.Gitlab(GITLAB_URL, private_token=os.getenv("GITLAB_TOKEN"))
        self.project = None # Do NOT fetch project here to avoid startup crash
        self.mr_states = {}

        if provider_type == "local":
            print(f"🔌 Connecting to Local LLM at: {local_url}")
            self.llm = OpenAIProvider(
                api_key="EMPTY",
                base_url=local_url,
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

    def _ensure_project_connection(self):
        """Attempts to connect to the project. Returns True if successful."""
        if self.project:
            return True
            
        try:
            self.project = self.gl.projects.get(PROJECT_ID)
            print(f"✅ Successfully connected to project: {self.project.name_with_namespace}")
            return True
        except Exception as e:
            # Short error message for 404 to keep logs clean
            if "404" in str(e):
                print(f"⚠️  Project '{PROJECT_ID}' not found. Retrying in {CHECK_INTERVAL}s...")
            else:
                print(f"⚠️  Connection error: {e}. Retrying in {CHECK_INTERVAL}s...")
            return False

    def _extract_json_block(self, text, type_hint=dict):
        if not text: return None
        
        candidates = []
        if type_hint == dict:
            match = re.search(r'(\{.*\})', text, re.DOTALL)
            if match: candidates.append(match.group(1))
        
        if type_hint == list:
            match = re.search(r'(\[.*\])', text, re.DOTALL)
            if match: candidates.append(match.group(1))
            
        cleaned = text.strip()
        if "```" in cleaned:
            cleaned = re.sub(r'```(?:json)?(.*?)```', r'\1', cleaned, flags=re.DOTALL).strip()
        candidates.append(cleaned)
        
        for candidate in candidates:
            candidate = re.sub(r',\s*\}', '}', candidate)
            candidate = re.sub(r',\s*\]', ']', candidate)
            try:
                data = json.loads(candidate, strict=False)
                if isinstance(data, type_hint): return data
            except: continue
        return None

    def check_history(self, mr):
        """
        Checks what the bot has already done.
        Returns:
          - initial_done (bool): Has Lead Agent posted?
          - last_bot_sha (str): The SHA of the last commit the bot reviewed (Friendly or Initial).
        """
        initial_done = False
        last_bot_sha = None
        
        try:
            # Check comments
            notes = mr.notes.list(per_page=50)
            
            for note in notes:
                # 1. Check for Initial Review
                if "### 🤖 AI Lead Summary" in note.body:
                    initial_done = True
                    # If we found initial review, assume it covered the MR SHA at that time.
                    # We can't easily get the SHA from the note, so we'll fallback to current unless friendly review found.
                    if not last_bot_sha:
                        # Fallback: if we only see initial review, assume we are up to date unless new commit comes
                        last_bot_sha = mr.sha 

                # 2. Check for Friendly Review (more recent)
                # We look for: "**Commit:** `abcdef12`"
                if "### 👋 Friendly Code Review" in note.body:
                    match = re.search(r'\*\*Commit:\*\* `([a-f0-9]+)`', note.body)
                    if match:
                        sha = match.group(1)
                        # We want to track the MOST RECENT commit the bot saw.
                        # Since we iterate notes (usually newest first), the first one we find is likely the latest.
                        if not last_bot_sha: # Only grab the first one we see (newest)
                            # We need full SHA, but we only have short SHA. 
                            # We will assume if we see this comment, we processed *that* commit.
                            # To be safe, we will fetch the full SHA from the commit list later if needed,
                            # but for now, let's just mark that we have done *something*.
                            last_bot_sha = sha 

        except Exception as e:
            print(f"   ⚠️ Error checking MR history: {e}")
            
        return initial_done, last_bot_sha

    def get_mr_diff_from_commits(self, mr):
        diff_text = ""
        diff_list = []
        try:
            commits = mr.commits()
            for commit in commits:
                commit_obj = self.project.commits.get(commit.id)
                commit_diff = commit_obj.diff()
                for change in commit_diff:
                    if change['new_path'].endswith(('.go', '.py', '.js', '.java', '.cpp')):
                        diff_text += f"File: {change['new_path']}\nDiff:\n{change['diff']}\n\n"
                        already_exists = any(d['new_path'] == change['new_path'] and d['diff'] == change['diff'] for d in diff_list)
                        if not already_exists: diff_list.append(change)
        except Exception as e:
            print(f"   ⚠️ Error fetching MR commits: {e}")
        return diff_text, diff_list

    def get_commit_diff(self, commit_sha):
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

    def run_initial_summary(self, mr, diff_text):
        print(f"   📝 [Initial] Tech Lead generating summary...")
        prompt_input = f"TITLE: {mr.title}\nDESC: {mr.description}\nDIFF:\n{diff_text}"
        
        data = None
        for i in range(LEAD_MAX_RETRIES):
            response = self.llm.ask(prompts.LEAD_SYSTEM_PROMPT, prompt_input)
            data = self._extract_json_block(response, type_hint=dict)
            log_llm_interaction(f"TECH LEAD (Attempt {i+1})", prompt_input, response, data)

            if data:
                print(f"      ✅ Valid JSON on attempt {i+1}")
                break
            print(f"      ⚠️ Invalid JSON. Retry {i+1}...")
            time.sleep(1)
        
        if not data:
            print(f"   ❌ Failed to parse Lead JSON.")
            return {}

        try:
            valid_labels = ['ready-for-merge', 'needs-review', 'changes-requested']
            labels_to_add = [l for l in data.get('labels_to_add', []) if l in valid_labels]
            if labels_to_add:
                mr.labels = labels_to_add
                mr.save()

            body = (
                f"### 🤖 AI Lead Summary\n\n"
                f"**TL;DR:** {data.get('tldr', 'N/A')}\n\n"
                f"{data.get('review_summary', '')}\n\n"
                f"**Risk:** {data.get('risk_assessment', 'UNKNOWN')}\n"
                f"**Decision:** **{data.get('final_decision', 'N/A')}**\n"
            )
            mr.notes.create({'body': body})
            return data
        except Exception as e:
            print(f"   ❌ Error posting Summary: {e}")
            return {}

    def run_initial_suggestions(self, mr, diff_text, diff_list, lead_context):
        print(f"   🔧 [Initial] Architect Agent finding bugs...")
        
        instructions = lead_context.get('architect_instructions', 'Find critical bugs.')
        print(f"      ℹ️ Instructions: {instructions[:60]}...")
        
        diff_lines_db = extract_diff_lines(diff_list)
        added_only = [e for e in diff_lines_db if e['is_added']]
        if not added_only:
            print(f"      ⚠️ No added lines found in diff")
            return []
        
        prompt_input = (
            f"CTO DIRECTIVES: \"{instructions}\"\n\n"
            f"CRITICAL RULES:\n"
            f"1. Copy 'bad_code_snippet' EXACTLY from the diff lines\n"
            f"2. Include ALL whitespace exactly as shown\n\n"
            f"FULL DIFF:\n{diff_text}"
        )
        
        for attempt in range(ARCHITECT_MAX_RETRIES):
            if attempt > 0:
                print(f"      🔄 Retry {attempt+1}/{ARCHITECT_MAX_RETRIES}")
                time.sleep(2)
            
            response = self.llm.ask(prompts.ARCHITECT_SYSTEM_PROMPT, prompt_input)
            bugs = self._extract_json_block(response, type_hint=list)
            
            if bugs is None:
                wrapper = self._extract_json_block(response, type_hint=dict)
                if wrapper and 'bugs' in wrapper and isinstance(wrapper['bugs'], list):
                    bugs = wrapper['bugs']
            
            log_llm_interaction(f"ARCHITECT (Attempt {attempt+1})", prompt_input, response, bugs)
            
            if not bugs:
                print(f"      ⚠️ JSON Parsing Failed or Empty")
                continue

            ver = mr.diffs.list()[0]
            base_sha, head_sha, start_sha = ver.base_commit_sha, ver.head_commit_sha, ver.start_commit_sha
            
            valid_batch_items = []
            
            for bug in bugs:
                target_line = find_best_match(bug.get('bad_code_snippet'), diff_lines_db, bug.get('file_path'))
                
                if target_line:
                    bug['target_line'] = target_line
                    valid_batch_items.append(bug)
                else:
                    print(f"      ⚠️ No match: '{bug.get('bad_code_snippet', '')[:30]}...'")

            if len(valid_batch_items) >= MIN_VALID_SUGGESTIONS:
                print(f"      ✅ Accepted! {len(valid_batch_items)} valid suggestions")
                posted = 0
                for bug in valid_batch_items:
                    body = (
                        f"🚨 **{bug.get('severity', 'HIGH')}**\n\n"
                        f"{bug.get('description', '')}\n\n"
                        f"```suggestion\n{bug.get('suggested_fix', '')}\n```"
                    )
                    pos = {
                        'base_sha': base_sha, 'start_sha': start_sha, 'head_sha': head_sha,
                        'position_type': 'text', 'new_path': bug['file_path'], 'new_line': bug['target_line']
                    }
                    try:
                        mr.discussions.create({'body': body, 'position': pos})
                        posted += 1
                        print(f"         📌 Posted line {bug['target_line']}")
                    except Exception as e:
                        print(f"         ❌ API Error: {e}")
                
                if posted > 0:
                    return valid_batch_items
            else:
                print(f"      ⚠️ Only {len(valid_batch_items)} valid (Need {MIN_VALID_SUGGESTIONS})")

        print(f"      ❌ Failed after {ARCHITECT_MAX_RETRIES} attempts")
        return []

    def run_friendly_commit_review(self, mr, commit_sha, previous_context=None):
        print(f"   👋 [Friendly] Reviewing commit {commit_sha[:8]}...")
        diff_text, commit = self.get_commit_diff(commit_sha)
        
        if not diff_text: return

        context_str = ""
        if previous_context:
            lead_sum = previous_context.get('lead_summary', {}).get('review_summary', 'N/A')
            bugs = previous_context.get('architect_issues', [])
            
            context_str = f"\n\nPREVIOUS REVIEW CONTEXT:\nTech Lead Summary: {lead_sum}\n"
            if bugs:
                context_str += "Previously Reported Critical Issues:\n"
                for i, bug in enumerate(bugs):
                    context_str += f"{i+1}. {bug.get('issue_type')}: {bug.get('description')}\n"
            context_str += "\nYOUR GOAL: Check if the new commit fixes these issues or introduces new ones.\n"

        commit_context = f"COMMIT: {commit_sha[:8]}\nAUTHOR: {commit.author_name}\nMSG: {commit.message}\n{context_str}\nCHANGES:\n{diff_text}"
        
        for i in range(FRIENDLY_MAX_RETRIES):
            response = self.llm.ask(prompts.FRIENDLY_COMMIT_PROMPT, commit_context)
            data = self._extract_json_block(response, type_hint=dict)
            log_llm_interaction(f"FRIENDLY (Attempt {i+1})", commit_context, response, data)
            
            if data:
                try:
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
                    print(f"      ✅ Review posted")
                    return
                except: pass
            time.sleep(1)

    def start_listening(self):
        print(f"\n👂 Unified Listener Started")
        print(f"   Repo: {PROJECT_ID}")
        print(f"   URL: {GITLAB_URL}")
        
        # Initial connection check
        self._ensure_project_connection()
        
        while True:
            try:
                if not self.project:
                    if not self._ensure_project_connection():
                        time.sleep(CHECK_INTERVAL)
                        continue

                mrs = self.project.mergerequests.list(state='opened', get_all=True)
                if mrs:
                    for mr in mrs:
                        # --- INITIAL STATE LOADING ---
                        if mr.iid not in self.mr_states:
                            # Check history to sync state
                            initial_done, last_bot_sha = self.check_history(mr)
                            
                            self.mr_states[mr.iid] = {
                                'initial_done': initial_done, 
                                'last_sha': last_bot_sha if last_bot_sha else mr.sha,
                                'context': {} 
                            }
                            
                            # If we found history, we are "caught up" to at least that point.
                            # If last_bot_sha matches current mr.sha, we do nothing.
                            # If last_bot_sha differs (short sha vs long sha issue handled loosely),
                            # we might trigger a friendly review if we are not careful.
                            # Best safe guard: if initial_done is true, we set last_sha to mr.sha
                            # to avoid reviewing OLD commits.
                            if initial_done:
                                self.mr_states[mr.iid]['last_sha'] = mr.sha
                                print(f"   ✅ MR !{mr.iid} synced. Waiting for NEW commits...")

                        # --- LOGIC FLOW ---
                        state = self.mr_states[mr.iid]
                        current_sha = mr.sha

                        # 1. Initial Review (Only if never done)
                        if not state['initial_done']:
                            print(f"\n🆕 Initial Review MR !{mr.iid}: {mr.title}")
                            diff_text, diff_list = self.get_mr_diff_from_commits(mr)
                            if diff_text:
                                lead_data = self.run_initial_summary(mr, diff_text)
                                time.sleep(1)
                                bug_list = self.run_initial_suggestions(mr, diff_text, diff_list, lead_data)
                                state['context'] = {
                                    'lead_summary': lead_data,
                                    'architect_issues': bug_list
                                }
                            state['initial_done'] = True
                            state['last_sha'] = current_sha
                        
                        # 2. Friendly Review (Only on NEW commits)
                        elif state['last_sha'] != current_sha:
                            print(f"\n🔄 New commit MR !{mr.iid}")
                            context = state.get('context', {})
                            self.run_friendly_commit_review(mr, current_sha, previous_context=context)
                            state['last_sha'] = current_sha
                            
                time.sleep(CHECK_INTERVAL)

            except gitlab.exceptions.GitlabGetError as e:
                if e.response_code == 404:
                    print(f"❌ Project lost (404). Attempting to reconnect...")
                    self.project = None
                else:
                    print(f"❌ GitLab API Error: {e}")
                time.sleep(CHECK_INTERVAL)
            except Exception as e:
                print(f"❌ Unexpected Error: {e}")
                time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", type=str, default="gemini")
    parser.add_argument("--local_url", type=str, default=DEFAULT_LOCAL_URL)
    args = parser.parse_args()
    bot = UnifiedBot(provider_type=args.provider, local_url=args.local_url)
    bot.start_listening()