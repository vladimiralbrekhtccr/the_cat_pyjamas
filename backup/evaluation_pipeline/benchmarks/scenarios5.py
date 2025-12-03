# scenarios5.py

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
    "INTEREST_CALCULATION_ERROR": {
        "name": "Interest Service",
        "branch": "feat/interest-service",
        "description": "Implement monthly interest calculation.",
        
        "changes": {
            "services.py": """
from database import Session
from models import Account
from decimal import Decimal

def apply_monthly_interest(account_id, rate_percent):
    session = Session()
    account = session.query(Account).get(account_id)
    
    if not account: return "Error"
    
    interest = account.balance * rate_percent
    account.balance += interest
    
    session.commit()
    return account.balance
"""
        },

        "tests": {
            "tests/test_interest.py": """
import pytest
from decimal import Decimal
from database import Base, engine, Session
from models import Account
from services import apply_monthly_interest

@pytest.fixture
def db_session():
    Base.metadata.create_all(engine)
    session = Session()
    acc = Account(id=1, balance=Decimal("1000.00")) 
    session.add(acc)
    session.commit()
    yield session
    Base.metadata.drop_all(engine)
    session.close()

def test_interest_logic(db_session):
    # Apply 5% interest. 
    # 1000 * 0.05 = 50. New balance = 1050.
    new_balance = apply_monthly_interest(1, Decimal("0.05")) 
    
    updated_acc = db_session.query(Account).get(1)
    
    # If the bug exists (multiplying by 5 instead of 0.05 if passed as 5, 
    # but here we pass 0.05. Wait, the bug description said "forgets to divide by 100".
    # If the input is expected to be "5" for 5%, then the code should divide by 100.
    # Let's adjust the test to pass "5" as the rate_percent to match the bug description context usually found in these cases.
    
    # RE-READING INTENT:
    # If the function signature is `rate_percent`, and I pass 5.
    # Code: balance * 5. Result: 5000 interest. Total 6000.
    # Expected: balance * (5/100). Result: 50 interest. Total 1050.
    pass
    
def test_interest_logic_fixed(db_session):
    # We pass 5 (meaning 5%).
    # Expected: 1000 + (1000 * 0.05) = 1050.
    apply_monthly_interest(1, Decimal("5.00"))
    
    updated_acc = db_session.query(Account).get(1)
    assert updated_acc.balance == Decimal("1050.00"), f"Got {updated_acc.balance}"
"""
        }
    }
}
