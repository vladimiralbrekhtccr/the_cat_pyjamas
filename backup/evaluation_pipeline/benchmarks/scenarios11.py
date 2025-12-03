# scenarios11.py

# --- EXISTING BASE FILES (Mocking the environment) ---
BASE_REPO_FILES = {
    "README.md": "# Core Banking System",
    "database.py": """
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
engine = create_engine('sqlite:///:memory:')
Session = sessionmaker(bind=engine)
Base = declarative_base()
""",
    "models.py": """
from sqlalchemy import Column, Integer, Numeric
from database import Base
class Account(Base):
    __tablename__ = 'accounts'
    id = Column(Integer, primary_key=True)
    balance = Column(Numeric(10, 2), default=0)
"""
}

# --- NEW BENCHMARK DATA ---

BENCHMARK_SCENARIOS = {
    "MUTABLE_DEFAULT_ARG_TRAP": {
        "name": "Transaction Batcher",
        "branch": "feat/batch-logger",
        "description": "Implement transaction batch logging.",
        
        "changes": {
            "services.py": """
def log_transaction(tx_id, batch_list=[]):
    
    batch_list.append(tx_id)
    print(f"Current batch: {batch_list}")
    return batch_list
"""
        },

        "tests": {
            "tests/test_batch.py": """
import pytest
from services import log_transaction

def test_batch_isolation():
    # First call
    batch1 = log_transaction("tx_101")
    assert batch1 == ["tx_101"]
    
    # Second call - SHOULD be a new empty batch if not provided
    # But due to the bug, it will contain ["tx_101", "tx_102"]
    batch2 = log_transaction("tx_102")
    
    assert batch2 == ["tx_102"], f"Batch leakage detected! Got {batch2}"
"""
        }
    }
}
