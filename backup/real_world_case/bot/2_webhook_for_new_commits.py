# friendly_commit_agent.py
"""
Friendly agent that monitors new commits AFTER initial MR review.
Only reviews commits added by users AFTER the bot's first review.
"""

import os
import time
import re
import gitlab
from dotenv import load_dotenv
from datetime import datetime
from google import genai
from google.genai import types
from prompts import FRIENDLY_COMMIT_PROMPT

load_dotenv()

GITLAB_URL = "https://gitlab.com"
PROJECT_ID = "vladimiralbrekhtccr-group/confluent-kafka-go-temp-123456"
BRANCH_NAME = "feature/full-mr-replay"
CHECK_INTERVAL = 10  # seconds
GEMINI_MODEL = "gemini-flash-latest"


class FriendlyCommitAgent:
    """Reviews new commits added after MR creation"""
    
    def __init__(self):
        self.gl = gitlab.Gitlab(GITLAB_URL, private_token=os.getenv("GITLAB_TOKEN"))
        self.gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        self.project = self.gl.projects.get(PROJECT_ID)
        self.tracked_mrs = {}  # {mr_iid: last_seen_commit_sha}
        
        try:
            bot_user = self.gl.user
            print(f"🤖 FriendlyCommitAgent: Connected as {bot_user.name} (@{bot_user.username})")
        except:
            print(f"🤖 FriendlyCommitAgent: Connected as BOT")
        
        print(f"   Project: {self.project.name_with_namespace}")
    
    def find_open_mrs(self):
        """Find all open MRs for the branch"""
        try:
            mrs = self.project.mergerequests.list(
                state='opened',
                source_branch=BRANCH_NAME,
                get_all=False
            )
            return mrs
        except:
            return []
    
    def initialize_mr_tracking(self, mr):
        """Initialize tracking for a new MR (skip existing commits)"""
        try:
            mr_obj = self.project.mergerequests.get(mr.iid)
            current_sha = mr_obj.sha
            self.tracked_mrs[mr.iid] = current_sha
            print(f"   📌 Started tracking MR !{mr.iid} at commit {current_sha[:8]}")
            print(f"      Will review NEW commits only")
            return True
        except Exception as e:
            print(f"   ❌ Could not initialize MR !{mr.iid}: {e}")
            return False
    
    def check_for_new_commit(self, mr):
        """Check if MR has a new commit"""
        try:
            mr_obj = self.project.mergerequests.get(mr.iid)
            latest_sha = mr_obj.sha
            last_seen_sha = self.tracked_mrs[mr.iid]
            
            if latest_sha != last_seen_sha:
                return latest_sha
            return None
        except Exception as e:
            print(f"   ❌ Error checking commits for MR !{mr.iid}: {e}")
            return None
    
    def get_commit_diff(self, commit_sha):
        """Get the diff for a specific commit"""
        try:
            commit = self.project.commits.get(commit_sha)
            commit_diff = commit.diff()
            
            diff_text = ""
            for change in commit_diff:
                filename = change['new_path']
                if filename.endswith(('.go', '.py', '.js', '.java', '.cpp', '.c', '.rs')):
                    diff_text += f"File: {filename}\nDiff:\n{change['diff']}\n\n"
            
            return diff_text, commit
        except Exception as e:
            print(f"      ❌ Error fetching diff: {e}")
            return None, None
    
    def _ask_gemini(self, system_prompt, user_content):
        """Call Gemini API"""
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
            temperature=0.3,
            max_output_tokens=1000,
            thinking_config={'thinking_budget': 0}
        )
        
        full_text = ""
        try:
            for chunk in self.gemini_client.models.generate_content_stream(
                model=GEMINI_MODEL,
                contents=contents,
                config=config
            ):
                full_text += chunk.text
            return full_text
        except Exception as e:
            print(f"      ❌ Gemini API Error: {e}")
            return ""
    
    def _extract_tag(self, text, tag_name):
        """Extract content from XML-style tags"""
        pattern = f"<{tag_name}>(.*?)</{tag_name}>"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else None
    
    def review_commit(self, commit_sha, mr_iid):
        """Review a new commit and post friendly feedback"""
        print(f"      🔍 Reviewing new commit {commit_sha[:8]}...")
        
        diff_text, commit = self.get_commit_diff(commit_sha)
        
        if not diff_text or not commit:
            print(f"      ⚠️ No code changes found")
            return
        
        commit_context = f"""
COMMIT: {commit_sha[:8]}
AUTHOR: {commit.author_name}
MESSAGE: {commit.message}
DATE: {commit.committed_date}

CHANGES:
{diff_text}
"""
        
        response = self._ask_gemini(FRIENDLY_COMMIT_PROMPT, commit_context)
        
        if not response:
            return
        
        summary = self._extract_tag(response, 'summary')
        feedback = self._extract_tag(response, 'feedback')
        risk = self._extract_tag(response, 'risk')
        status_label = self._extract_tag(response, 'status_label')
        
        if not summary:
            print(f"      ❌ Failed to parse AI response")
            return
        
        # Validate label
        valid_labels = ['ready-for-merge', 'needs-review', 'changes-requested']
        final_label = status_label if status_label in valid_labels else 'needs-review'
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        comment_body = f"""### 👋 Friendly Code Review

**Commit:** `{commit_sha[:8]}`  
**Author:** {commit.author_name}  
**Time:** {timestamp}

---

**Summary:** {summary}

**Feedback:** {feedback}

**Risk:** {risk or 'N/A'}  
**Status:** `{final_label}`

---
*Automated review by AI Assistant* 🤖
"""
        
        try:
            mr = self.project.mergerequests.get(mr_iid)
            mr.notes.create({'body': comment_body})
            mr.labels = [final_label]
            mr.save()
            print(f"      ✅ Posted friendly review. Label: {final_label}")
        except Exception as e:
            print(f"      ❌ Failed to post: {e}")
    
    def run(self):
        """Main loop: monitor for new commits"""
        print(f"\n👂 Starting Friendly Commit Agent...")
        print(f"   Monitoring branch: {BRANCH_NAME}")
        print(f"   Checking every {CHECK_INTERVAL} seconds")
        print(f"   Press Ctrl+C to stop\n")
        
        try:
            while True:
                timestamp = datetime.now().strftime('%H:%M:%S')
                
                # Find open MRs
                mrs = self.find_open_mrs()
                
                if not mrs:
                    print(f"[{timestamp}] ⚠️  No open MRs found")
                    time.sleep(CHECK_INTERVAL)
                    continue
                
                # Process each MR
                for mr in mrs:
                    # Initialize tracking if this is a new MR
                    if mr.iid not in self.tracked_mrs:
                        print(f"\n[{timestamp}] 📋 Found MR !{mr.iid} - {mr.title}")
                        self.initialize_mr_tracking(mr)
                        continue
                    
                    # Check for new commits
                    new_commit = self.check_for_new_commit(mr)
                    
                    if new_commit:
                        print(f"\n[{timestamp}] 🆕 NEW COMMIT in MR !{mr.iid}")
                        self.review_commit(new_commit, mr.iid)
                        self.tracked_mrs[mr.iid] = new_commit
                
                print(f"[{timestamp}] ✓ Check complete")
                time.sleep(CHECK_INTERVAL)
                
        except KeyboardInterrupt:
            print("\n\n👋 Friendly Commit Agent stopped")
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")


if __name__ == "__main__":
    agent = FriendlyCommitAgent()
    agent.run()
