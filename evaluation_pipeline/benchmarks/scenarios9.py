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
from sqlalchemy import Column, Integer, Numeric, String, Boolean
from database import Base
class Account(Base):
    __tablename__ = 'accounts'
    id = Column(Integer, primary_key=True)
    balance = Column(Numeric(10, 2), default=0)
    is_frozen = Column(Boolean, default=False)
"""
}

# --- NEW BENCHMARK DATA ---

BENCHMARK_SCENARIOS = {
    "TRANSFER_LOGIC_ERROR_10": {
        "name": "Transfer Service",
        "branch": "feat/transfer-service",
        "description": "Implement fund transfer functionality between accounts with validation.",
        
        "changes": {
            "services.py": """
from database import Session
from models import Account
from validators import validate_transfer

def transfer_funds(from_account_id, to_account_id, amount):
    session = Session()
    
    from_account = session.query(Account).get(from_account_id)
    to_account = session.query(Account).get(to_account_id)
    
    if not from_account or not to_account:
        return {"success": False, "error": "Account not found"}
    
    validation = validate_transfer(from_account, to_account, amount)
    if not validation["valid"]:
        return {"success": False, "error": validation["reason"]}
    
    from_account.balance = from_account.balance - amount
    
    session.commit()
    return {
        "success": True,
        "from_balance": from_account.balance,
        "to_balance": to_account.balance
    }
""",
            "validators.py": """
from decimal import Decimal

def validate_transfer(from_account, to_account, amount):
    if amount <= 0:
        return {"valid": False, "reason": "Amount must be positive"}
    


    if from_account.balance > amount:
        return {"valid": True, "reason": None}
    else:
        return {"valid": False, "reason": "Insufficient funds"}
"""
        },

        "tests": {
            "tests/test_services.py": """
import pytest
from decimal import Decimal
from database import Base, engine, Session
from models import Account
from services import transfer_funds

@pytest.fixture
def db_session():
    Base.metadata.create_all(engine)
    session = Session()
    sender = Account(id=1, balance=Decimal("500.00"), is_frozen=False)
    receiver = Account(id=2, balance=Decimal("100.00"), is_frozen=False)
    session.add_all([sender, receiver])
    session.commit()
    yield session
    Base.metadata.drop_all(engine)
    session.close()

def test_transfer_success(db_session):
    result = transfer_funds(1, 2, Decimal("200.00"))
    
    sender = db_session.query(Account).get(1)
    receiver = db_session.query(Account).get(2)
    
    assert result["success"] is True
    assert sender.balance == Decimal("300.00"), f"Sender should have 300, got {sender.balance}"
    assert receiver.balance == Decimal("300.00"), f"Receiver should have 300, got {receiver.balance}"

def test_transfer_exact_balance(db_session):
    # Transfer entire balance (500.00)
    result = transfer_funds(1, 2, Decimal("500.00"))
    
    assert result["success"] is True, f"Transfer of exact balance should succeed, got {result}"
    
    sender = db_session.query(Account).get(1)
    assert sender.balance == Decimal("0.00")

def test_transfer_insufficient_funds(db_session):
    result = transfer_funds(1, 2, Decimal("1000.00"))
    
    assert result["success"] is False
    
    sender = db_session.query(Account).get(1)
    assert sender.balance == Decimal("500.00"), "Balance should be unchanged"
""",
            "tests/test_validators.py": """
import pytest
from decimal import Decimal
from database import Base, engine, Session
from models import Account
from validators import validate_transfer

@pytest.fixture
def db_session():
    Base.metadata.create_all(engine)
    session = Session()
    normal = Account(id=1, balance=Decimal("500.00"), is_frozen=False)
    frozen = Account(id=2, balance=Decimal("200.00"), is_frozen=True)
    session.add_all([normal, frozen])
    session.commit()
    yield session
    Base.metadata.drop_all(engine)
    session.close()

def test_frozen_sender_rejected(db_session):
    frozen = db_session.query(Account).get(2)
    normal = db_session.query(Account).get(1)
    
    result = validate_transfer(frozen, normal, Decimal("50.00"))
    assert result["valid"] is False, "Frozen accounts should not send funds"

def test_frozen_receiver_rejected(db_session):
    normal = db_session.query(Account).get(1)
    frozen = db_session.query(Account).get(2)
    
    result = validate_transfer(normal, frozen, Decimal("50.00"))
    assert result["valid"] is False, "Cannot transfer to frozen accounts"

def test_negative_amount_rejected(db_session):
    acc1 = db_session.query(Account).get(1)
    acc2 = db_session.query(Account).get(2)
    
    result = validate_transfer(acc1, acc2, Decimal("-100.00"))
    assert result["valid"] is False
"""
        }
    }
}