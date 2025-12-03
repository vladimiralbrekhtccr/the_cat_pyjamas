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
from sqlalchemy import Column, Integer, Numeric, String
from database import Base
class Account(Base):
    __tablename__ = 'accounts'
    id = Column(Integer, primary_key=True)
    balance = Column(Numeric(10, 2), default=0)
    account_type = Column(String(20), default='standard')
"""
}

# --- NEW BENCHMARK DATA ---

BENCHMARK_SCENARIOS = {
    "WITHDRAWAL_LOGIC_ERROR_8": {
        "name": "Withdrawal Service",
        "branch": "feat/withdrawal-service",
        "description": "Implement withdrawal functionality with balance validation and transaction fees.",
        
        "changes": {
            "services.py": """
from database import Session
from models import Account
from fees import calculate_withdrawal_fee

def withdraw_funds(account_id, amount):
    session = Session()
    account = session.query(Account).get(account_id)
    if not account: return "Error: Account not found"
    
    fee = calculate_withdrawal_fee(account.account_type, amount)
    total_deduction = amount + fee
    
    account.balance = account.balance - total_deduction
    
    session.commit()
    return {"new_balance": account.balance, "fee_charged": fee}
""",
            "fees.py": """
from decimal import Decimal

def calculate_withdrawal_fee(account_type, amount):
    fee_rate = Decimal("0.01")
    return amount * fee_rate
"""
        },

        "tests": {
            "tests/test_services.py": """
import pytest
from decimal import Decimal
from database import Base, engine, Session
from models import Account
from services import withdraw_funds

@pytest.fixture
def db_session():
    Base.metadata.create_all(engine)
    session = Session()
    acc = Account(id=1, balance=Decimal("200.00"), account_type='standard')
    session.add(acc)
    session.commit()
    yield session
    Base.metadata.drop_all(engine)
    session.close()

def test_withdrawal_insufficient_funds(db_session):
    # Attempt to withdraw more than available balance
    result = withdraw_funds(1, Decimal("500.00"))
    updated_acc = db_session.query(Account).get(1)
    # Balance should remain unchanged when insufficient funds
    assert updated_acc.balance == Decimal("200.00"), f"Expected 200.00, got {updated_acc.balance}"

def test_withdrawal_success(db_session):
    # Withdraw 50 with 1% fee (0.50), total deduction 50.50
    result = withdraw_funds(1, Decimal("50.00"))
    updated_acc = db_session.query(Account).get(1)
    assert updated_acc.balance == Decimal("149.50"), f"Expected 149.50, got {updated_acc.balance}"
""",
            "tests/test_fees.py": """
import pytest
from decimal import Decimal
from fees import calculate_withdrawal_fee

def test_standard_account_fee():
    fee = calculate_withdrawal_fee('standard', Decimal("100.00"))
    assert fee == Decimal("1.00"), f"Standard fee should be 1%, got {fee}"

def test_premium_account_no_fee():
    fee = calculate_withdrawal_fee('premium', Decimal("100.00"))
    assert fee == Decimal("0.00"), f"Premium accounts should have 0% fee, got {fee}"
"""
        }
    }
}