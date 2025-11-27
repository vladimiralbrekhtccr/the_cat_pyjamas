# commit_simulator.py
"""
Simple commit simulator - creates realistic code changes and posts a comment.
"""

import os
import time
import gitlab
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

GITLAB_URL = "https://gitlab.com"
PROJECT_ID = "vladimiralbrekhtccr-group/confluent-kafka-go-temp-123456"
BRANCH_NAME = "feature/full-mr-replay"

class CommitSimulator:
    def __init__(self):
        self.gl = gitlab.Gitlab(GITLAB_URL, private_token=os.getenv("GITLAB_TOKEN_USER"))
        self.project = self.gl.projects.get(PROJECT_ID)
        print(f"🔗 Connected as USER to: {self.project.name_with_namespace}")
    
    def find_open_mr(self):
        """Find the open MR for the branch"""
        mrs = self.project.mergerequests.list(
            state='opened',
            source_branch=BRANCH_NAME,
            get_all=False
        )
        if mrs:
            return mrs[0]
        return None
    
    def create_simple_commit(self):
        """Create a simple code improvement commit"""
        print(f"\n📝 Creating a code improvement commit on {BRANCH_NAME}...")
        
        file_path = 'schemaregistry/serde/avrov2/avro_util.go'
        
        # Get current file content
        try:
            file = self.project.files.get(file_path=file_path, ref=BRANCH_NAME)
            current_content = file.decode().decode('utf-8')
        except Exception as e:
            print(f"   ❌ Could not fetch file: {e}")
            return None
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Add a simple comment improvement
        new_comment = f'''
// Code review improvement - {timestamp}
// Added better error handling and validation
'''
        
        # Just append to the end of the file
        new_content = current_content + new_comment
        
        data = {
            'branch': BRANCH_NAME,
            'commit_message': f'refactor: improve error handling comments',
            'actions': [
                {
                    'action': 'update',
                    'file_path': file_path,
                    'content': new_content,
                }
            ]
        }
        
        try:
            commit = self.project.commits.create(data)
            print(f"   ✅ Commit created: {commit.id[:8]}")
            print(f"   📄 File: {file_path}")
            print(f"   📝 Message: {commit.message}")
            return commit
        except Exception as e:
            print(f"   ❌ Failed to create commit: {e}")
            return None
    
    def post_user_comment(self, commit):
        """Post a simple comment from the user about the commit"""
        print(f"\n💬 Posting user comment...")
        
        # Find the open MR
        mr = self.find_open_mr()
        if not mr:
            print(f"   ⚠️ No open MR found")
            return False
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Simple user comment about the commit
        comment_body = f"""Just pushed some improvements to the error handling! 

Added better comments and validation. Let me know if this looks good. 👍

*Posted at {timestamp}*"""
        
        try:
            mr.notes.create({'body': comment_body})
            print(f"   ✅ Comment posted to MR !{mr.iid}")
            return True
        except Exception as e:
            print(f"   ❌ Failed to post comment: {e}")
            return False

if __name__ == "__main__":
    simulator = CommitSimulator()
    
    # Step 1: Create commit
    commit = simulator.create_simple_commit()
    
    if commit:
        print(f"\n⏳ Waiting 2 seconds...")
        time.sleep(2)
        
        # Step 2: Post user comment
        simulator.post_user_comment(commit)
        
        print(f"\n🎉 Done! The friendly commit agent should detect this commit.")