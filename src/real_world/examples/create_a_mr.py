"""
Generation of the MR
"""

import os
import time
import re
from dotenv import load_dotenv
import gitlab

load_dotenv()

# --- CONFIGURATION ---
GITLAB_URL = "https://gitlab.com"
PROJECT_ID = "vladimiralbrekhtccr-group/confluent-kafka-go-temp-123456"
SOURCE_BRANCH = "feature/full-mr-replay"
TARGET_BRANCH = "main"

# Specific commits to include in the MR
TARGET_COMMITS = [
    "4efe69fe8b19ec300d297febd5c1b9a48d90a3c3",  # Minor cleanup
    "d6fc67e3aa4b83a7a106ec45a75ba10133f1db81"   # DGS-22899 Fix support for wrapped Avro unions
]


# ==============================================================================
# MR CREATOR
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

def run_pipeline():
    creator = MRCreator()
    creator.cleanup_old_mrs()
    mr = creator.create_mr()
    
    if not mr:
        print("\n❌ Failed to create MR. Exiting.")
        return

if __name__ == "__main__":
    run_pipeline()