# benchmarks/scenario_transaction.py

# --- BASE FILES (The "Legacy" System) ---
BASE_REPO_FILES = {
    "README.md": "# Transaction Core System\n\nHandles money movement between accounts.",
    
    "database.py": """
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
engine = create_engine('sqlite:///:memory:')
Session = sessionmaker(bind=engine)
Base = declarative_base()
""",

    "models.py": """
from sqlalchemy import Column, Integer, Numeric, String, ForeignKey
from sqlalchemy.sql import func
from database import Base

class Account(Base):
    __tablename__ = 'accounts'
    id = Column(Integer, primary_key=True)
    holder = Column(String)
    balance = Column(Numeric(10, 2), default=0)

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id = Column(Integer, primary_key=True)
    message = Column(String)
    amount = Column(Numeric(10, 2))
""",

    # The original file that the MR will MODIFY
    "transfer_service.py": """
from models import Account, AuditLog

def process_transfer(session, from_id, to_id, amount):
    # OLD LEGACY CODE - Unsafe, no limits
    # The new feature branch aims to replace this with safe logic
    sender = session.query(Account).get(from_id)
    receiver = session.query(Account).get(to_id)
    
    sender.balance -= amount
    receiver.balance += amount
    session.commit()
    return True
"""
}

# --- THE BENCHMARK ---
BENCHMARK_SCENARIOS = {
    "DIRTY_SESSION_ROLLBACK": {
        "name": "Safe Transfer Logic",
        "branch": "refactor/safe-transfers",
        "description": "Refactor transfer service to include limit checks and audit logging.",
        
        # CHANGED: Supports creating NEW files and UPDATING existing ones
        "changes": {
            # 1. NEW FILE: Validator Logic
            "validators.py": """
def check_transfer_limits(amount, tier="STANDARD"):
    if tier == "STANDARD" and amount > 1000:
        return False, "Transfer limit exceeded for Standard Tier"
    if amount <= 0:
        return False, "Amount must be positive"
    return True, "OK"
""",

            # 2. MODIFIED FILE: The Refactored Service
            "transfer_service.py": """
from models import Account, AuditLog
from validators import check_transfer_limits

def process_transfer(session, from_id, to_id, amount):
    '''
    Refactored transfer logic with validation.
    Args:
        session: An active SQLAlchemy session
    '''
    sender = session.query(Account).get(from_id)
    receiver = session.query(Account).get(to_id)
    
    if not sender or not receiver:
        return "User not found"

    
    sender.balance -= amount
    
    log = AuditLog(message=f"Transfer from {from_id} to {to_id}", amount=amount)
    session.add(log)
    
    is_valid, msg = check_transfer_limits(amount)
    
    if not is_valid:
        return f"Error: {msg}"
        

    receiver.balance += amount
    
    try:
        session.commit()
        return "Success"
    except Exception as e:
        session.rollback()
        return f"Database Error: {e}"
"""
        },

        # --- TESTS ---
        "tests": {
            # Test 1: Helper logic (Smoke test)
            "tests/test_validators.py": """
from validators import check_transfer_limits
def test_limits():
    assert check_transfer_limits(500)[0] == True
    assert check_transfer_limits(1500)[0] == False
""",

            # Test 2: The Logic Trap
            "tests/test_service_safety.py": """
import pytest
from decimal import Decimal
from database import Base, engine, Session
from models import Account, AuditLog
from transfer_service import process_transfer

@pytest.fixture
def db_session():
    Base.metadata.create_all(engine)
    session = Session()
    # Setup: Alice has 5000, Bob has 0
    alice = Account(id=1, holder="Alice", balance=Decimal("5000.00"))
    bob = Account(id=2, holder="Bob", balance=Decimal("0.00"))
    session.add_all([alice, bob])
    session.commit()
    
    yield session
    
    session.close()
    Base.metadata.drop_all(engine)

def test_transfer_limit_enforcement_integrity(db_session):
    '''
    Scenario: Alice tries to transfer 2000. Limit is 1000.
    Expected: returns Error, Alice's balance remains 5000.
    '''
    
    # 1. Attempt Transfer (Should fail)
    result = process_transfer(db_session, 1, 2, Decimal("2000.00"))
    
    # Check return string
    assert "Error" in result, "Should return error message for high amount"
    assert "limit exceeded" in result.lower()
    
    # 2. INTEGRITY CHECK
    # We inspect the object currently attached to the session.
    alice = db_session.query(Account).get(1)
    
    # If the bug exists:
    # process_transfer did: alice.balance -= 2000 (Memory becomes 3000)
    # Then returned "Error"
    # But did NOT rollback.
    # So 'alice' in this session still thinks balance is 3000.
    
    assert alice.balance == Decimal("5000.00"), \
        f"CRITICAL: Session Dirty! Balance is {alice.balance} (Should be 5000). The service modified state before validating."

def test_audit_log_cleanup(db_session):
    '''
    Ensure failed transfers don't leave phantom audit logs in the session.
    '''
    process_transfer(db_session, 1, 2, Decimal("2000.00"))
    
    # If rollback wasn't called, session.new might still contain the AuditLog object
    # waiting to be committed next time someone calls commit().
    
    # Using db_session.new checks for pending inserts
    pending_logs = [obj for obj in db_session.new if isinstance(obj, AuditLog)]
    
    assert len(pending_logs) == 0, \
        "CRITICAL: Found pending AuditLog objects in session after failed transfer! Rollback missing."
"""
        }
    }
}