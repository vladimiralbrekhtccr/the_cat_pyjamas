### CONFIG ###
GITLAB_URL = "https://gitlab.com"
PROJECT_ID = "vladimiralbrekhtccr-group/confluent-kafka-go-temp-123456"
SOURCE_BRANCH = "feature/full-mr-replay"
CHECK_INTERVAL = 10
DEFAULT_LOCAL_URL = "http://localhost:6655/v1"
MIN_VALID_SUGGESTIONS = 2
SIMILARITY_THRESHOLD = 0.85

LEAD_MAX_RETRIES = 10
ARCHITECT_MAX_RETRIES = 10
FRIENDLY_MAX_RETRIES = 10

TARGET_COMMITS = [
    "4efe69fe8b19ec300d297febd5c1b9a48d90a3c3",
    "d6fc67e3aa4b83a7a106ec45a75ba10133f1db81"
]

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
    if not snippet:
        return None
        
    norm_snippet = normalize_code(snippet)
    
    added_lines = [l for l in diff_lines_db if l['file'] == filename and l['is_added']]
    
    if not added_lines:
        logging.warning(f"No added lines found in {filename}")
        return None
    
    best_match = None
    best_score = 0
    
    for entry in added_lines:
        if entry['normalized'] == norm_snippet:
            logging.info(f"   ✓ Exact match on line {entry['line_num']}")
            return entry['line_num']
    
    for entry in added_lines:
        score = similarity_score(norm_snippet, entry['normalized'])
        if score > best_score:
            best_score = score
            best_match = entry
    
    if best_score >= SIMILARITY_THRESHOLD:
        logging.info(f"   🔍 Fuzzy match: {best_score:.2f} on line {best_match['line_num']}")
        logging.info(f"      Expected: {snippet[:60]}...")
        logging.info(f"      Got: {best_match['raw'][:60]}...")
        return best_match['line_num']
    
    logging.warning(f"   ❌ No match found (best score: {best_score:.2f})")
    return None

class UnifiedBot:
    def __init__(self, provider_type="gemini", local_url=DEFAULT_LOCAL_URL):
        self.gl = gitlab.Gitlab(GITLAB_URL, private_token=os.getenv("GITLAB_TOKEN"))
        self.project = self.gl.projects.get(PROJECT_ID)
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

    def _extract_json_block(self, text):
        if not text:
            return None
        
        try:
            start = text.find('[')
            end = text.rfind(']') + 1
            if start != -1 and end > start:
                candidate = text[start:end]
                candidate = re.sub(r',\s*\]', ']', candidate)
                return json.loads(candidate, strict=False)
        except:
            pass

        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end > start:
                candidate = text[start:end]
                candidate = re.sub(r',\s*\}', '}', candidate)
                return json.loads(candidate, strict=False)
        except:
            pass

        try:
            cleaned = text.strip()
            if "```" in cleaned:
                match = re.search(r'```(?:json)?(.*?)```', cleaned, re.DOTALL)
                if match:
                    cleaned = match.group(1).strip()
            
            cleaned = re.sub(r',\s*\]', ']', cleaned)
            cleaned = re.sub(r',\s*\}', '}', cleaned)
            
            return json.loads(cleaned, strict=False)
        except:
            return None

    def check_if_initial_review_exists(self, mr):
        try:
            notes = mr.notes.list(per_page=50)
            for note in notes:
                if "### 🤖 AI Lead Summary" in note.body:
                    return True
        except Exception as e:
            print(f"   ⚠️ Error checking MR history: {e}")
        return False

    def get_initial_diff_text(self, commits):
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
            data = self._extract_json_block(response)
            
            log_llm_interaction(f"TECH LEAD (Attempt {i+1}/{LEAD_MAX_RETRIES})", prompt_input, response, data)

            if data and isinstance(data, dict) and 'tldr' in data:
                print(f"      ✅ Valid JSON on attempt {i+1}")
                break
            print(f"      ⚠️ Invalid JSON. Retry {i+1}/{LEAD_MAX_RETRIES}...")
            if i < LEAD_MAX_RETRIES - 1:
                time.sleep(1)
        
        if not data:
            print(f"   ❌ Failed to parse Lead JSON after {LEAD_MAX_RETRIES} attempts")
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
            logging.error(f"Post Summary Error: {e}")
            return {}

    def run_initial_suggestions(self, mr, diff_text, diff_list, lead_context):
        print(f"   🔧 [Initial] Architect Agent finding bugs...")
        
        instructions = lead_context.get('architect_instructions', 'Find critical bugs.')
        print(f"      ℹ️ Instructions: {instructions[:60]}...")
        
        diff_lines_db = extract_diff_lines(diff_list)
        
        added_only = [e for e in diff_lines_db if e['is_added']]
        if not added_only:
            print(f"      ⚠️ No added lines found in diff")
            return
        
        sample_lines = "\n".join([
            f"Line {e['line_num']}: {e['raw'][:80]}"
            for e in added_only[:5]
        ])
        
        prompt_input = (
            f"CTO DIRECTIVES: \"{instructions}\"\n\n"
            f"CRITICAL RULES:\n"
            f"1. Copy 'bad_code_snippet' EXACTLY from lines starting with '+' in the diff\n"
            f"2. Do NOT include the '+' prefix in your snippet\n"
            f"3. Include ALL whitespace/tabs exactly as shown\n\n"
            f"Example ADDED lines from this diff:\n{sample_lines}\n\n"
            f"FULL DIFF:\n{diff_text}"
        )
        
        failed_snippets = []
        
        for attempt in range(ARCHITECT_MAX_RETRIES):
            if attempt > 0:
                print(f"      🔄 Retry {attempt+1}/{ARCHITECT_MAX_RETRIES}")
                if failed_snippets:
                    feedback = "\nPREVIOUS FAILURES (copy EXACTLY from diff):\n"
                    for snip in failed_snippets[-3:]:
                        feedback += f"❌ '{snip[:50]}...'\n"
                    prompt_input = f"{prompt_input}\n\n{feedback}"
                time.sleep(2)
            
            response = self.llm.ask(prompts.ARCHITECT_SYSTEM_PROMPT, prompt_input)
            bugs = self._extract_json_block(response)
            
            log_llm_interaction(f"ARCHITECT (Attempt {attempt+1}/{ARCHITECT_MAX_RETRIES})", prompt_input, response, bugs)
            
            if bugs is None:
                print(f"      ⚠️ JSON Parsing Failed")
                continue
            
            if not isinstance(bugs, list):
                if isinstance(bugs, dict) and 'bugs' in bugs:
                    bugs = bugs['bugs']
                else:
                    print(f"      ⚠️ Expected list, got {type(bugs)}")
                    continue

            if not bugs:
                print(f"      ✅ No bugs found")
                return

            ver = mr.diffs.list()[0]
            base_sha, head_sha, start_sha = ver.base_commit_sha, ver.head_commit_sha, ver.start_commit_sha
            
            valid_batch_items = []
            failed_snippets.clear()
            
            for bug in bugs:
                target_line = find_best_match(
                    bug.get('bad_code_snippet'),
                    diff_lines_db,
                    bug.get('file_path')
                )
                
                if target_line:
                    bug['target_line'] = target_line
                    valid_batch_items.append(bug)
                else:
                    snippet = bug.get('bad_code_snippet', '')
                    failed_snippets.append(snippet)
                    print(f"      ⚠️ No match: {snippet[:40]}... in {bug.get('file_path')}")

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
                        'base_sha': base_sha,
                        'start_sha': start_sha,
                        'head_sha': head_sha,
                        'position_type': 'text',
                        'new_path': bug['file_path'],
                        'new_line': bug['target_line']
                    }
                    try:
                        mr.discussions.create({'body': body, 'position': pos})
                        posted += 1
                        print(f"         📌 Posted line {bug['target_line']}")
                    except gitlab.exceptions.GitlabCreateError as e:
                        error_msg = str(e)
                        print(f"         ❌ GitLab API Error on line {bug['target_line']}: {error_msg}")
                        logging.error(f"Failed to post comment: {error_msg}\nPosition: {pos}")
                    except Exception as e:
                        print(f"         ❌ Unexpected Error: {e}")
                        logging.exception("Comment post failed")
                
                if posted > 0:
                    print(f"      🏁 Total posted: {posted}/{len(valid_batch_items)}")
                    return
                else:
                    print(f"      ⚠️ All comments failed to post. Retrying...")
            else:
                print(f"      ⚠️ Only {len(valid_batch_items)} valid (need {MIN_VALID_SUGGESTIONS})")

        print(f"      ❌ Failed after {ARCHITECT_MAX_RETRIES} attempts")

    def run_friendly_commit_review(self, mr, commit_sha):
        print(f"   👋 [Friendly] Reviewing commit {commit_sha[:8]}...")
        diff_text, commit = self.get_commit_diff(commit_sha)
        
        if not diff_text:
            print(f"      ⚠️ No relevant changes")
            return

        commit_context = f"COMMIT: {commit_sha[:8]}\nAUTHOR: {commit.author_name}\nMSG: {commit.message}\nCHANGES:\n{diff_text}"
        
        data = None
        for i in range(FRIENDLY_MAX_RETRIES):
            response = self.llm.ask(prompts.FRIENDLY_COMMIT_PROMPT, commit_context)
            data = self._extract_json_block(response)
            
            log_llm_interaction(f"FRIENDLY (Attempt {i+1}/{FRIENDLY_MAX_RETRIES})", commit_context, response, data)
            
            if data and isinstance(data, dict):
                print(f"      ✅ Valid JSON on attempt {i+1}")
                break
            print(f"      ⚠️ Invalid JSON. Retry {i+1}/{FRIENDLY_MAX_RETRIES}...")
            if i < FRIENDLY_MAX_RETRIES - 1:
                time.sleep(1)
        
        if not data:
            print(f"      ❌ Failed to parse JSON after {FRIENDLY_MAX_RETRIES} attempts")
            return

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
        except Exception as e:
            print(f"      ❌ Error: {e}")
            logging.exception("Friendly review failed")

    def start_listening(self):
        print(f"\n👂 Unified Listener Started")
        print(f"   Source Branch: {SOURCE_BRANCH}")
        print(f"   Polling: {CHECK_INTERVAL}s")
        print(f"   Min suggestions: {MIN_VALID_SUGGESTIONS}")
        print(f"   Retry limits: Lead={LEAD_MAX_RETRIES}, Architect={ARCHITECT_MAX_RETRIES}, Friendly={FRIENDLY_MAX_RETRIES}")
        print(f"   Similarity threshold: {SIMILARITY_THRESHOLD}")
        
        while True:
            try:
                timestamp = datetime.now().strftime('%H:%M:%S')
                mrs = self.project.mergerequests.list(
                    state='opened',
                    source_branch=SOURCE_BRANCH,
                    get_all=False
                )
                
                if mrs:
                    for mr in mrs:
                        current_sha = mr.sha
                        
                        if mr.iid not in self.mr_states:
                            print(f"\n[{timestamp}] 📋 Found MR !{mr.iid}")
                            already_reviewed = self.check_if_initial_review_exists(mr)
                            self.mr_states[mr.iid] = {
                                'initial_done': already_reviewed,
                                'last_sha': current_sha if already_reviewed else None
                            }
                            if already_reviewed:
                                print(f"   ✅ Initial review exists. Monitoring...")

                        state = self.mr_states[mr.iid]

                        if not state['initial_done']:
                            print(f"\n🆕 Initial Review MR !{mr.iid}")
                            diff_text, diff_list = self.get_initial_diff_text(TARGET_COMMITS)
                            if diff_text:
                                lead_context = self.run_initial_summary(mr, diff_text)
                                time.sleep(2)
                                self.run_initial_suggestions(mr, diff_text, diff_list, lead_context)
                                print(f"✅ Initial Review Complete")
                            state['initial_done'] = True
                            state['last_sha'] = current_sha
                        
                        elif state['last_sha'] != current_sha:
                            print(f"\n🔄 New commit MR !{mr.iid} ({state['last_sha'][:8]} -> {current_sha[:8]})")
                            self.run_friendly_commit_review(mr, current_sha)
                            state['last_sha'] = current_sha

                time.sleep(CHECK_INTERVAL)

            except KeyboardInterrupt:
                print("\n👋 Stopping")
                break
            except Exception as e:
                print(f"❌ Loop Error: {e}")
                logging.exception("Fatal Loop Error")
                time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", type=str, default="gemini",
                       choices=["gemini", "local", "openai"])
    parser.add_argument("--local_url", type=str, default=DEFAULT_LOCAL_URL)
    
    args = parser.parse_args()
    bot = UnifiedBot(provider_type=args.provider, local_url=args.local_url)
    bot.start_listening()