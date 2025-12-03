# bot_mr_listener.py
"""
Monitors for new MRs and automatically posts initial review (comment + suggestions).
This script runs continuously and checks for new MRs every 10 seconds.
Uses a local OpenAI-compatible model (e.g., vLLM/Qwen).
"""

import os
import time
import re
import gitlab
import openai  # Changed from google.genai
from dotenv import load_dotenv
from datetime import datetime
import prompts

load_dotenv()

# GitLab Config
GITLAB_URL = "https://gitlab.com"
PROJECT_ID = "vladimiralbrekhtccr-group/confluent-kafka-go-temp-123456"
SOURCE_BRANCH = "feature/full-mr-replay"
CHECK_INTERVAL = 10  # seconds

# Local Model Config
LOCAL_API_URL = "http://localhost:6655/v1"
MODEL_NAME = "qwen3_30b_deployed"

# Target commits to review
TARGET_COMMITS = [
    "4efe69fe8b19ec300d297febd5c1b9a48d90a3c3",  # Minor cleanup
    "d6fc67e3aa4b83a7a106ec45a75ba10133f1db81"   # DGS-22899 Fix support for wrapped Avro unions
]


# ==============================================================================
# CLASS 1: COMMENT AGENT (Bot posts summary comment)
# ==============================================================================
class CommentAgent:
    """AI agent that posts high-level review comments using GITLAB_TOKEN"""
    
    def __init__(self):
        self.gl = gitlab.Gitlab(GITLAB_URL, private_token=os.getenv("GITLAB_TOKEN"))
        
        # Initialize OpenAI Client for Local Model
        self.client = openai.Client(
            base_url=LOCAL_API_URL, 
            api_key="EMPTY"
        )
        
        self.project = self.gl.projects.get(PROJECT_ID)
        
        try:
            bot_user = self.gl.user
            print(f"🤖 CommentAgent: Connected as {bot_user.name} (@{bot_user.username})")
        except:
            print(f"🤖 CommentAgent: Connected as BOT")
    
    def _ask_local_model(self, system_prompt, user_content):
        """Call Local Model API with streaming"""
        print(f"   🧠 Sending request to {MODEL_NAME}...")
        
        start_time = time.perf_counter()
        
        try:
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
                max_tokens=4000,
                stream=True
            )

            full_text = ""
            first_token_time = None
            
            # Process stream
            print("   ⏳ Stream: ", end="", flush=True)
            for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    
                    # Calculate TTFT (Time To First Token)
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                        ttft = first_token_time - start_time
                        # We print this nicely later or just log it
                        # print(f"[TTFT: {ttft:.3f}s]", end="") 
                    
                    print(content, end="", flush=True)
                    full_text += content
            
            print("\n") # Newline after stream finishes
            return full_text

        except Exception as e:
            print(f"\n   ❌ Local Model API Error: {e}")
            return ""
    
    def _extract_tag(self, text, tag_name):
        """Extract content from XML-style tags"""
        pattern = f"<{tag_name}>(.*?)</{tag_name}>"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else None
    
    def get_diff_for_commits(self, commits):
        """Extract diff only for specified commits"""
        diff_text = ""
        
        for commit_sha in commits:
            try:
                commit = self.project.commits.get(commit_sha)
                commit_diff = commit.diff()
                
                for change in commit_diff:
                    filename = change['new_path']
                    if filename.endswith(".go"):
                        diff_text += f"File: {filename}\nCommit: {commit_sha[:8]}\nDiff:\n{change['diff']}\n\n"
                        
            except Exception as e:
                print(f"   ⚠️ Warning: Could not get diff for {commit_sha[:8]}: {e}")
        
        return diff_text
    
    def _get_commit_title(self, commit_sha):
        """Get commit title"""
        try:
            commit = self.project.commits.get(commit_sha)
            return commit.title
        except:
            return "Unknown commit"
    
    def post_review_comment(self, mr_iid, diff_text, commits):
        """Generate and post high-level review comment"""
        print(f"   💬 Generating summary comment...")
        
        commit_info = "\n".join([f"- {sha[:8]}" for sha in commits])
        
        # Use the new local model method
        response = self._ask_local_model(
            prompts.LEAD_SYSTEM_PROMPT,
            f"TITLE: Real World Bug: Confluent Kafka PR #1493\n\nCOMMITS REVIEWED:\n{commit_info}\n\nDIFF:\n{diff_text}"
        )
        
        if not response:
            print("   ❌ Empty response from Model")
            return False
        
        # Parse response
        summary = self._extract_tag(response, 'summary')
        risk = self._extract_tag(response, 'risk')
        decision = self._extract_tag(response, 'decision')
        status_label = self._extract_tag(response, 'status_label')
        
        if not summary:
            print("   ❌ Failed to parse response (missing XML tags)")
            return False
        
        # Validate status label
        valid_labels = ['ready-for-merge', 'needs-review', 'changes-requested']
        if status_label and status_label in valid_labels:
            final_label = status_label
        else:
            final_label = 'needs-review'
            print(f"   ⚠️ Invalid label, defaulting to 'needs-review'")
        
        commit_list = "\n".join([f"- `{sha[:8]}` {self._get_commit_title(sha)}" for sha in commits])
        
        # Create comment body
        body = (
            f"### 🤖 AI Lead Summary\n\n"
            f"{summary}\n\n"
            f"**Commits Reviewed:**\n{commit_list}\n\n"
            f"**Risk Assessment:** {risk or 'N/A'}\n"
            f"**Decision:** **{decision or 'N/A'}**\n"
            f"**Status:** `{final_label}`\n\n"
            f"---\n"
            f"*Automated review by Local AI Assistant ({MODEL_NAME})*"
        )
        
        # Post comment
        try:
            mr = self.project.mergerequests.get(mr_iid)
            mr.notes.create({'body': body})
            
            # Set label
            mr.labels = [final_label]
            mr.save()
            
            print(f"   ✅ Comment posted. Decision: {decision}, Label: {final_label}")
            return True
            
        except Exception as e:
            print(f"   ❌ Failed to post comment: {e}")
            return False


# ==============================================================================
# CLASS 2: SUGGESTIONS AGENT (Bot posts inline suggestions)
# ==============================================================================
class SuggestionsAgent:
    """AI agent that posts inline code suggestions using GITLAB_TOKEN"""
    
    def __init__(self):
        self.gl = gitlab.Gitlab(GITLAB_URL, private_token=os.getenv("GITLAB_TOKEN"))
        
        # Initialize OpenAI Client for Local Model
        self.client = openai.Client(
            base_url=LOCAL_API_URL, 
            api_key="EMPTY"
        )
        
        self.project = self.gl.projects.get(PROJECT_ID)
        
        try:
            bot_user = self.gl.user
            print(f"🤖 SuggestionsAgent: Connected as {bot_user.name} (@{bot_user.username})")
        except:
            print(f"🤖 SuggestionsAgent: Connected as BOT")
    
    def _ask_local_model(self, system_prompt, user_content):
        """Call Local Model API with streaming"""
        print(f"   🧠 Sending request to {MODEL_NAME}...")
        
        start_time = time.perf_counter()
        
        try:
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
                max_tokens=4000,
                stream=True
            )

            full_text = ""
            first_token_time = None
            
            print("   ⏳ Stream: ", end="", flush=True)
            for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    
                    print(content, end="", flush=True)
                    full_text += content
            
            print("\n")
            return full_text

        except Exception as e:
            print(f"\n   ❌ Local Model API Error: {e}")
            return ""
    
    def _extract_tag(self, text, tag_name):
        """Extract content from XML-style tags"""
        pattern = f"<{tag_name}>(.*?)</{tag_name}>"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else None
    
    def _extract_all_bugs(self, text):
        """Extract all <bug> blocks"""
        bug_pattern = r"<bug>(.*?)</bug>"
        bugs = re.findall(bug_pattern, text, re.DOTALL)
        
        parsed_bugs = []
        for bug_text in bugs:
            bug_dict = {
                'file_path': self._extract_tag(bug_text, 'file'),
                'line': self._extract_tag(bug_text, 'line'),
                'type': self._extract_tag(bug_text, 'type'),
                'severity': self._extract_tag(bug_text, 'severity'),
                'confidence': self._extract_tag(bug_text, 'confidence'),
                'production_impact': self._extract_tag(bug_text, 'production_impact'),
                'description': self._extract_tag(bug_text, 'description'),
                'fix': self._extract_tag(bug_text, 'fix'),
            }
            if bug_dict['file_path'] and bug_dict['line'] and bug_dict['description']:
                parsed_bugs.append(bug_dict)
        
        return parsed_bugs
    
    def _filter_bugs(self, bugs):
        """Filter bugs to only show high-impact issues"""
        filtered = []
        
        for bug in bugs:
            severity = bug.get('severity', '').upper()
            confidence = bug.get('confidence', '').upper()
            
            if severity not in ['CRITICAL', 'HIGH']:
                continue
            
            if confidence != 'HIGH':
                continue
            
            if not bug.get('production_impact'):
                continue
            
            filtered.append(bug)
        
        return filtered
    
    def get_diff_for_commits(self, commits):
        """Extract diff for specified commits with full change objects"""
        diff_text = ""
        all_changes = []
        
        for commit_sha in commits:
            try:
                commit = self.project.commits.get(commit_sha)
                commit_diff = commit.diff()
                
                for change in commit_diff:
                    filename = change['new_path']
                    if filename.endswith(".go"):
                        diff_text += f"File: {filename}\nCommit: {commit_sha[:8]}\nDiff:\n{change['diff']}\n\n"
                        all_changes.append(change)
                        
            except Exception as e:
                print(f"   ⚠️ Warning: Could not get diff for {commit_sha[:8]}: {e}")
        
        return diff_text, all_changes
    
    def _find_line(self, diff_list, filename, snippet):
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
    
    def post_suggestions(self, mr_iid, diff_text, diff_list, commits):
        """Generate and post inline code suggestions"""
        print(f"   🔍 Analyzing code...")
        
        commit_context = ", ".join([sha[:8] for sha in commits])
        context_prompt = (
            prompts.ARCHITECT_SYSTEM_PROMPT +
            f"\n\nCODE CONTEXT: This is Golang code from a Kafka client library (confluent-kafka-go)."
            f"\nReviewing commits: {commit_context}"
        )
        
        # Use the new local model method
        response = self._ask_local_model(context_prompt, diff_text)
        
        if not response:
            print("   ❌ Empty response from Model")
            return 0
        
        if '<no-bugs-found/>' in response or '<no-bugs-found>' in response:
            print("   ✅ No critical bugs detected")
            return 0
        
        # Parse and filter bugs
        all_bugs = self._extract_all_bugs(response)
        
        if not all_bugs:
            print("   ⚠️ Failed to parse bug blocks")
            return 0
        
        filtered_bugs = self._filter_bugs(all_bugs)
        
        if not filtered_bugs:
            print("   ✅ All bugs filtered out")
            return 0
        
        # Get MR diff info
        mr = self.project.mergerequests.get(mr_iid)
        ver = mr.diffs.list()[0]
        base, head, start = ver.base_commit_sha, ver.head_commit_sha, ver.start_commit_sha
        
        # Post suggestions
        posted_count = 0
        for bug in filtered_bugs:
            target_line = self._find_line(diff_list, bug['file_path'], bug['line'])
            
            if target_line:
                body = (
                    f"🚨 **{bug.get('severity', 'HIGH')} - {bug.get('type', 'Bug')}**\n\n"
                    f"**Production Impact:**\n"
                    f"{bug.get('production_impact', 'N/A')}\n\n"
                    f"**Technical Details:**\n"
                    f"{bug['description']}\n\n"
                    f"**Suggested Fix:**\n"
                    f"```suggestion\n{bug['fix']}\n```"
                )
                pos = {
                    'base_sha': base,
                    'start_sha': start,
                    'head_sha': head,
                    'position_type': 'text',
                    'new_path': bug['file_path'],
                    'new_line': target_line
                }
                try:
                    mr.discussions.create({'body': body, 'position': pos})
                    posted_count += 1
                except Exception as e:
                    print(f"   ⚠️ GitLab API Error: {e}")
        
        print(f"   ✅ Posted {posted_count}/{len(filtered_bugs)} suggestions")
        return posted_count


# ==============================================================================
# MR LISTENER CLASS
# ==============================================================================
class MRListener:
    """Monitors for new MRs and triggers automated review"""
    
    def __init__(self):
        self.gl = gitlab.Gitlab(GITLAB_URL, private_token=os.getenv("GITLAB_TOKEN"))
        self.project = self.gl.projects.get(PROJECT_ID)
        self.reviewed_mrs = set()  # Track which MRs we've already reviewed
        
        print(f"🔗 Connected to: {self.project.name_with_namespace}")
    
    def find_new_mrs(self):
        """Find MRs that haven't been reviewed yet"""
        mrs = self.project.mergerequests.list(
            state='opened',
            source_branch=SOURCE_BRANCH,
            get_all=False
        )
        
        new_mrs = []
        for mr in mrs:
            if mr.iid not in self.reviewed_mrs:
                new_mrs.append(mr)
        
        return new_mrs
    
    def review_mr(self, mr):
        """Perform initial review on an MR"""
        print(f"\n🆕 New MR detected: !{mr.iid} - {mr.title}")
        print(f"   🔗 {mr.web_url}")
        
        # Phase 1: Post comment
        print("\n   📝 Phase 1: Posting summary comment...")
        comment_agent = CommentAgent()
        diff_text = comment_agent.get_diff_for_commits(TARGET_COMMITS)
        
        if diff_text:
            comment_agent.post_review_comment(mr.iid, diff_text, TARGET_COMMITS)
        else:
            print("   ⚠️ No diff found for comment")
        
        # Wait a bit
        time.sleep(2)
        
        # Phase 2: Post suggestions
        print("\n   🔧 Phase 2: Posting inline suggestions...")
        suggestions_agent = SuggestionsAgent()
        diff_text, diff_list = suggestions_agent.get_diff_for_commits(TARGET_COMMITS)
        
        if diff_text:
            suggestions_agent.post_suggestions(mr.iid, diff_text, diff_list, TARGET_COMMITS)
        else:
            print("   ⚠️ No diff found for suggestions")
        
        # Mark as reviewed
        self.reviewed_mrs.add(mr.iid)
        print(f"\n✅ MR !{mr.iid} review complete")
    
    def run(self):
        """Main loop: check for new MRs periodically"""
        print(f"\n👂 Starting MR Listener...")
        print(f"   Monitoring branch: {SOURCE_BRANCH}")
        print(f"   Checking every {CHECK_INTERVAL} seconds")
        print(f"   Model: {MODEL_NAME} @ {LOCAL_API_URL}")
        print(f"   Press Ctrl+C to stop\n")
        
        try:
            while True:
                timestamp = datetime.now().strftime('%H:%M:%S')
                
                # Find new MRs
                new_mrs = self.find_new_mrs()
                
                if new_mrs:
                    print(f"[{timestamp}] 🎯 Found {len(new_mrs)} new MR(s)")
                    for mr in new_mrs:
                        self.review_mr(mr)
                else:
                    print(f"[{timestamp}] ✓ No new MRs")
                
                time.sleep(CHECK_INTERVAL)
                
        except KeyboardInterrupt:
            print("\n\n👋 MR Listener stopped by user")
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")


if __name__ == "__main__":
    listener = MRListener()
    listener.run()