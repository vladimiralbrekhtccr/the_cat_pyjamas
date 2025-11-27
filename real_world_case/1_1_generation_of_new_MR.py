# 1 Step: 
# Initial MR + Comment + Suggestions
"""
Complete AI Code Review Pipeline with 3 independent classes:
1. MRCreator - Creates MR as a real developer (uses GITLAB_TOKEN_USER)
2. CommentAgent - Posts high-level summary comment (uses GITLAB_TOKEN)
3. SuggestionsAgent - Posts inline code suggestions (uses GITLAB_TOKEN)
"""

import os
import time
import re
from dotenv import load_dotenv
from google import genai
from google.genai import types
import gitlab

import prompts 

load_dotenv()

# --- CONFIGURATION ---
GITLAB_URL = "https://gitlab.com"
PROJECT_ID = "vladimiralbrekhtccr-group/confluent-kafka-go-temp-123456"
SOURCE_BRANCH = "feature/full-mr-replay"
TARGET_BRANCH = "main"
GEMINI_MODEL = "gemini-flash-latest"

# Specific commits to include in the MR
TARGET_COMMITS = [
    "4efe69fe8b19ec300d297febd5c1b9a48d90a3c3",  # Minor cleanup
    "d6fc67e3aa4b83a7a106ec45a75ba10133f1db81"   # DGS-22899 Fix support for wrapped Avro unions
]


# ==============================================================================
# CLASS 1: MR CREATOR (User creates MR)
# ==============================================================================
class MRCreator:
    """Creates Merge Requests as a real developer using GITLAB_TOKEN_USER"""
    
    def __init__(self):
        self.gl = gitlab.Gitlab(GITLAB_URL, private_token=os.getenv("GITLAB_TOKEN_USER"))
        self.project = self.gl.projects.get(PROJECT_ID)
        
        try:
            user = self.gl.user
            print(f"👤 MRCreator: Connected as {user.name} (@{user.username})")
        except:
            print(f"👤 MRCreator: Connected as USER")
    
    def cleanup_old_mrs(self):
        """Delete any existing open MRs for the branch"""
        print(f"\n🧹 Cleaning up old MRs on '{SOURCE_BRANCH}'...")
        existing_mrs = self.project.mergerequests.list(
            state='opened',
            source_branch=SOURCE_BRANCH
        )
        
        for old_mr in existing_mrs:
            print(f"   🗑️  Deleting MR !{old_mr.iid}...")
            old_mr.delete()
            time.sleep(2)
        
        if not existing_mrs:
            print(f"   ✓ No old MRs to clean up")
    
    def create_mr(self):
        """Create a new MR"""
        print(f"\n📝 Creating Merge Request...")
        
        try:
            mr = self.project.mergerequests.create({
                'source_branch': SOURCE_BRANCH,
                'target_branch': TARGET_BRANCH,
                'title': 'Real World Bug: Confluent Kafka PR #1493',
                'description': f'''## Description
This PR fixes support for wrapped Avro unions in the serialization library.

### Included Commits
- `{TARGET_COMMITS[0][:8]}` - Minor cleanup
- `{TARGET_COMMITS[1][:8]}` - DGS-22899 Fix support for wrapped Avro unions

### Changes
- Added proper handling for wrapped union types
- Added comprehensive test coverage
- Fixed type resolution logic

Please can someone review this?
---
*MR created by developer*
''',
                'remove_source_branch': False
            })
            
            print(f"   ✅ MR !{mr.iid} created")
            print(f"   🔗 {mr.web_url}")
            return mr
            
        except Exception as e:
            print(f"   ❌ Failed to create MR: {e}")
            return None
    
    def get_mr_info(self):
        """Get information about the open MR"""
        mrs = self.project.mergerequests.list(
            state='opened',
            source_branch=SOURCE_BRANCH
        )
        
        if mrs:
            mr = mrs[0]
            return {
                'iid': mr.iid,
                'title': mr.title,
                'url': mr.web_url
            }
        return None


# ==============================================================================
# CLASS 2: COMMENT AGENT (Bot posts summary comment)
# ==============================================================================
class CommentAgent:
    """AI agent that posts high-level review comments using GITLAB_TOKEN"""
    
    def __init__(self):
        self.gl = gitlab.Gitlab(GITLAB_URL, private_token=os.getenv("GITLAB_TOKEN"))
        self.gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        self.project = self.gl.projects.get(PROJECT_ID)
        
        try:
            bot_user = self.gl.user
            print(f"🤖 CommentAgent: Connected as {bot_user.name} (@{bot_user.username})")
        except:
            print(f"🤖 CommentAgent: Connected as BOT")
    
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
            temperature=0.1,
            max_output_tokens=4000,
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
            print(f"   ❌ Gemini API Error: {e}")
            return ""
    
    def _extract_tag(self, text, tag_name):
        """Extract content from XML-style tags"""
        pattern = f"<{tag_name}>(.*?)</{tag_name}>"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else None
    
    def get_diff_for_commits(self, commits):
        """Extract diff only for specified commits"""
        print(f"\n📂 Extracting diff for commits:")
        for commit_sha in commits:
            print(f"   - {commit_sha[:8]}")
        
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
        print(f"\n💬 Generating summary comment for MR !{mr_iid}...")
        
        commit_info = "\n".join([f"- {sha[:8]}" for sha in commits])
        
        response = self._ask_gemini(
            prompts.LEAD_SYSTEM_PROMPT,
            f"TITLE: Real World Bug: Confluent Kafka PR #1493\n\nCOMMITS REVIEWED:\n{commit_info}\n\nDIFF:\n{diff_text}"
        )
        
        if not response:
            print("   ❌ Empty response from Gemini")
            return False
        
        # Parse response
        summary = self._extract_tag(response, 'summary')
        risk = self._extract_tag(response, 'risk')
        decision = self._extract_tag(response, 'decision')
        labels_text = self._extract_tag(response, 'labels')
        
        if not summary:
            print("   ❌ Failed to parse response")
            return False
        
        labels = [l.strip() for l in labels_text.split('\n') if l.strip()] if labels_text else []
        commit_list = "\n".join([f"- `{sha[:8]}` {self._get_commit_title(sha)}" for sha in commits])
        
        # Create comment body
        body = (
            f"### 🤖 AI Lead Summary\n\n"
            f"{summary}\n\n"
            f"**Commits Reviewed:**\n{commit_list}\n\n"
            f"**Risk Assessment:** {risk or 'N/A'}\n"
            f"**Decision:** **{decision or 'N/A'}**\n\n"
            f"---\n"
            f"*Automated review by AI Assistant*"
        )
        
        # Post comment
        try:
            mr = self.project.mergerequests.get(mr_iid)
            mr.notes.create({'body': body})
            
            if labels:
                mr.labels = labels
                mr.save()
            
            print(f"   ✅ Comment posted. Decision: {decision}")
            return True
            
        except Exception as e:
            print(f"   ❌ Failed to post comment: {e}")
            return False


# ==============================================================================
# CLASS 3: SUGGESTIONS AGENT (Bot posts inline suggestions)
# ==============================================================================
class SuggestionsAgent:
    """AI agent that posts inline code suggestions using GITLAB_TOKEN"""
    
    def __init__(self):
        self.gl = gitlab.Gitlab(GITLAB_URL, private_token=os.getenv("GITLAB_TOKEN"))
        self.gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        self.project = self.gl.projects.get(PROJECT_ID)
        
        try:
            bot_user = self.gl.user
            print(f"🤖 SuggestionsAgent: Connected as {bot_user.name} (@{bot_user.username})")
        except:
            print(f"🤖 SuggestionsAgent: Connected as BOT")
    
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
            temperature=0.1,
            max_output_tokens=4000,
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
            print(f"   ❌ Gemini API Error: {e}")
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
        print(f"\n📂 Extracting diff for commits:")
        for commit_sha in commits:
            print(f"   - {commit_sha[:8]}")
        
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
        print(f"\n🔍 Analyzing code for MR !{mr_iid}...")
        
        commit_context = ", ".join([sha[:8] for sha in commits])
        context_prompt = (
            prompts.ARCHITECT_SYSTEM_PROMPT +
            f"\n\nCODE CONTEXT: This is Golang code from a Kafka client library (confluent-kafka-go)."
            f"\nReviewing commits: {commit_context}"
        )
        
        response = self._ask_gemini(context_prompt, diff_text)
        
        if not response:
            print("   ❌ Empty response from Gemini")
            return 0
        
        if '<no-bugs-found/>' in response or '<no-bugs-found>' in response:
            print("   ✅ No critical bugs detected")
            return 0
        
        # Parse and filter bugs
        all_bugs = self._extract_all_bugs(response)
        print(f"   📋 Raw bugs found: {len(all_bugs)}")
        
        if not all_bugs:
            print("   ⚠️ Failed to parse bug blocks")
            return 0
        
        filtered_bugs = self._filter_bugs(all_bugs)
        print(f"   🔍 Critical bugs after filtering: {len(filtered_bugs)}")
        
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
                    print(f"      ✅ {bug['file_path']}:{target_line} ({bug['severity']})")
                except Exception as e:
                    print(f"      ⚠️ GitLab API Error: {e}")
            else:
                print(f"      ⚠️ Line not found: '{bug['line'][:40]}...'")
        
        print(f"   ✅ Posted {posted_count}/{len(filtered_bugs)} suggestions")
        return posted_count


# ==============================================================================
# MAIN PIPELINE ORCHESTRATOR
# ==============================================================================
def run_pipeline():
    """Run the complete AI code review pipeline"""
    
    ### First Part of making MR


    print("=" * 70)
    print("🚀 AI CODE REVIEW PIPELINE")
    print("=" * 70)
    
    # PHASE 1: User creates MR
    print("\n" + "=" * 70)
    print("PHASE 1: CREATE MERGE REQUEST")
    print("=" * 70)
    
    creator = MRCreator()
    creator.cleanup_old_mrs()
    mr = creator.create_mr()
    
    if not mr:
        print("\n❌ Failed to create MR. Exiting.")
        return
    
    
    ## SECOND part of checking MR and providing commits


    # mr_iid = 31
    
    # # Wait for GitLab to process
    # print("\n⏳ Waiting 3 seconds for GitLab...")
    # time.sleep(3)
    
    # # PHASE 2: Bot posts comment
    # print("\n" + "=" * 70)
    # print("PHASE 2: POST SUMMARY COMMENT")
    # print("=" * 70)
    
    # comment_agent = CommentAgent()
    # diff_text = comment_agent.get_diff_for_commits(TARGET_COMMITS)
    
    # if diff_text:
    #     comment_agent.post_review_comment(mr_iid, diff_text, TARGET_COMMITS)
    # else:
    #     print("   ⚠️ No diff found")
    
    # # Wait a bit
    # print("\n⏳ Waiting 2 seconds...")
    # time.sleep(2)
    
    # # PHASE 3: Bot posts suggestions
    # print("\n" + "=" * 70)
    # print("PHASE 3: POST INLINE SUGGESTIONS")
    # print("=" * 70)
    
    # suggestions_agent = SuggestionsAgent()
    # diff_text, diff_list = suggestions_agent.get_diff_for_commits(TARGET_COMMITS)
    
    # if diff_text:
    #     suggestions_agent.post_suggestions(mr_iid, diff_text, diff_list, TARGET_COMMITS)
    # else:
    #     print("   ⚠️ No diff found")


if __name__ == "__main__":
    run_pipeline()