# scenarios4.py

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
    "TRANSFER_FUNDS_LOGIC_ERROR": {
        "name": "Transfer Service",
        "branch": "feat/transfer-service",
        "description": "Implement fund transfer between accounts.",
        
        "changes": {
            "services.py": """
from database import Session
from models import Account

def transfer_funds(from_id, to_id, amount):
    session = Session()
    sender = session.query(Account).get(from_id)
    receiver = session.query(Account).get(to_id)
    
    if not sender or not receiver: return "Error"
    if sender.balance < amount: return "Insufficient Funds"
    
    sender.balance -= amount
    receiver.balance -= amount 
    
    session.commit()
    return True
"""
        },

        "tests": {
            "tests/test_transfer.py": """
import pytest
from decimal import Decimal
from database import Base, engine, Session
from models import Account
from services import transfer_funds

@pytest.fixture
def db_session():
    Base.metadata.create_all(engine)
    session = Session()
    sender = Account(id=1, balance=Decimal("100.00")) 
    receiver = Account(id=2, balance=Decimal("50.00"))
    session.add(sender)
    session.add(receiver)
    session.commit()
    yield session
    Base.metadata.drop_all(engine)
    session.close()

def test_transfer_logic(db_session):
    # Transfer 30 from 1 to 2. 
    # Sender: 100 - 30 = 70
    # Receiver: 50 + 30 = 80
    result = transfer_funds(1, 2, Decimal("30.00")) 
    
    sender = db_session.query(Account).get(1)
    receiver = db_session.query(Account).get(2)
    
    assert sender.balance == Decimal("70.00"), f"Sender Balance: {sender.balance}"
    assert receiver.balance == Decimal("80.00"), f"Receiver Balance: {receiver.balance}"
"""
        }
    }
}
