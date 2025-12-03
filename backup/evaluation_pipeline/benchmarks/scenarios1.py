# scenarios.py

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
    "DEPOSIT_LOGIC_ERROR_1": {
        "name": "Deposit Service",
        "branch": "feat/deposit-service",
        "description": "Implement deposit functionality with currency checks.",
        
        # CHANGED: Supports multiple files to be added/modified in the Feature Branch
        "changes": {
            "services.py": """
from database import Session
from models import Account

def deposit_funds(account_id, amount):
    session = Session()
    account = session.query(Account).get(account_id)
    if not account: return "Error"
    
    account.balance = amount 
    
    session.commit()
    return account.balance
""",
            "utils.py": """
def validate_currency(amount):
    if amount < 0:
        return False
    return True
"""
        },

        # CHANGED: Supports multiple test files (Committed to Main)
        "tests": {
            "tests/test_services.py": """
import pytest
from decimal import Decimal
from database import Base, engine, Session
from models import Account
from services import deposit_funds

@pytest.fixture
def db_session():
    Base.metadata.create_all(engine)
    session = Session()
    acc = Account(id=1, balance=Decimal("100.00")) 
    session.add(acc)
    session.commit()
    yield session
    Base.metadata.drop_all(engine)
    session.close()

def test_deposit_logic(db_session):
    # Deposit 50. Should result in 150.
    new_balance = deposit_funds(1, Decimal("50.00")) 
    updated_acc = db_session.query(Account).get(1)
    assert updated_acc.balance == Decimal("150.00"), f"Got {updated_acc.balance}"
""",
            "tests/test_utils.py": """
from utils import validate_currency
def test_validation():
    assert validate_currency(10) == True
    assert validate_currency(-5) == False
"""
        }
    }
}