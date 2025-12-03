# benchmarks/scenario_precision.py

# --- BASE FILES (Shared Environment) ---
BASE_REPO_FILES = {
    "README.md": "# Global Forex Banking System\nEnsure all currency operations use high-precision math.",
    
    "database.py": """
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
# In-memory SQLite for speed
engine = create_engine('sqlite:///:memory:')
Session = sessionmaker(bind=engine)
Base = declarative_base()
""",

    "models.py": """
from sqlalchemy import Column, Integer, String, Numeric, ForeignKey
from database import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String)

class Wallet(Base):
    __tablename__ = 'wallets'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    currency = Column(String(3)) # USD, EUR, JPY
    # Numeric(14, 4) allows 4 decimal places for precise forex rates
    balance = Column(Numeric(14, 4), default=0)
"""
}

# --- THE BENCHMARK ---
BENCHMARK_SCENARIOS = {
    "FOREX_PRECISION_CASCADE": {
        "name": "Forex Exchange Service",
        "branch": "feat/currency-exchange",
        "description": "Implement currency exchange with fees. Warning: High precision required.",
        
        "changes": {
            # FILE 1: The Utils (Source of the 'Dirty' Types)
            "currency_utils.py": """
# Helper to simulate fetching live rates
# TRAP: These are raw Python floats. 
# If multiplied by Decimal, result becomes float.
def get_live_rate(from_curr, to_curr):
    rates = {
        ('USD', 'EUR'): 0.92,  # 1 USD = 0.92 EUR
        ('EUR', 'USD'): 1.08,
        ('USD', 'JPY'): 150.55,
    }
    return rates.get((from_curr, to_curr), 1.0)

# TRAP: Fee is a float
def get_platform_fee():
    return 0.015 # 1.5% fee
""",

            # FILE 2: The Service (The Logic Flaw)
            "exchange_service.py": """
from database import Session
from models import Wallet
from currency_utils import get_live_rate, get_platform_fee
from decimal import Decimal

def execute_exchange(user_id, from_curr, to_curr, amount_str):
    session = Session()
    
    # 1. Fetch Wallets
    src_wallet = session.query(Wallet).filter_by(user_id=user_id, currency=from_curr).first()
    tgt_wallet = session.query(Wallet).filter_by(user_id=user_id, currency=to_curr).first()
    
    if not src_wallet or not tgt_wallet:
        return "Wallet not found"

    # Input is string, converted to Decimal (Good start)
    amount = Decimal(amount_str)
    
    if src_wallet.balance < amount:
        return "Insufficient funds"

    # 2. Get Rates (TRAP: Returns float)
    rate = get_live_rate(from_curr, to_curr)
    fee_pct = get_platform_fee()
    
    # 3. Calculate
    # BUG: Decimal * Float = Float. 
    # Python will NOT auto-convert float to Decimal here, it downgrades precision.
    converted_raw = amount * rate
    
    # Calculate Fee
    fee_amount = converted_raw * fee_pct
    final_amount = converted_raw - fee_amount
    
    # 4. Update DB Objects
    # src_wallet.balance is Decimal. amount is Decimal. Result: Decimal. (Safe)
    src_wallet.balance -= amount
    
    # tgt_wallet.balance is Decimal. final_amount is FLOAT. 
    # Result: tgt_wallet.balance becomes FLOAT in Python memory.
    tgt_wallet.balance += final_amount
    
    session.commit()
    
    # We return the object to let tests inspect the in-memory state
    return tgt_wallet.balance
"""
        },

        # --- EXTENSIVE TESTS ---
        "tests": {
            "tests/test_types.py": """
import pytest
from decimal import Decimal
from database import Base, engine, Session
from models import User, Wallet
from exchange_service import execute_exchange

@pytest.fixture
def db_setup():
    Base.metadata.create_all(engine)
    session = Session()
    u = User(id=1, name="Trader Joe")
    w1 = Wallet(user_id=1, currency="USD", balance=Decimal("1000.0000"))
    w2 = Wallet(user_id=1, currency="EUR", balance=Decimal("0.0000"))
    session.add_all([u, w1, w2])
    session.commit()
    yield session
    Base.metadata.drop_all(engine)

def test_strict_decimal_integrity(db_setup):
    '''
    This test fails if the resulting balance is a python float.
    Financial apps cannot tolerate floating point binary errors.
    '''
    # Exchange 100 USD to EUR
    # Rate 0.92, Fee 1.5%
    # Math: 100 * 0.92 = 92.0
    # Fee: 92.0 * 0.015 = 1.38
    # Final: 90.62
    
    result_balance = execute_exchange(1, "USD", "EUR", "100.00")
    
    # 1. Check Type (The most common AI failure point)
    assert isinstance(result_balance, Decimal), \
        f"CRITICAL: Balance became type {type(result_balance)}. Must be Decimal."

    # 2. Check Value match
    expected = Decimal("90.6200") 
    # We use quantized comparison to ignore deep precision mismatches if logic is correct
    assert result_balance.quantize(Decimal("1.0000")) == expected
""",

            "tests/test_math_drift.py": """
import pytest
from decimal import Decimal
from database import Base, engine, Session
from models import User, Wallet
from exchange_service import execute_exchange

# Setup specific for checking float drift
@pytest.fixture
def float_trap_setup():
    Base.metadata.create_all(engine)
    session = Session()
    u = User(id=99, name="Math Tester")
    # A number that plays poorly with binary floats
    w1 = Wallet(user_id=99, currency="USD", balance=Decimal("123456.7891")) 
    w2 = Wallet(user_id=99, currency="JPY", balance=Decimal("0.0000"))
    session.add_all([u, w1, w2])
    session.commit()
    yield
    Base.metadata.drop_all(engine)

def test_floating_point_artifacts(float_trap_setup):
    '''
    If floats are used, multiplying large numbers often results in 
    micro-errors (e.g., .99999999991 instead of .0000).
    '''
    # USD -> JPY is rate 150.55
    # Fee 1.5%
    
    final_balance = execute_exchange(99, "USD", "JPY", "10000.00")
    
    # Expected Math:
    # 10,000 * 150.55 = 1,505,500
    # Fee: 1,505,500 * 0.015 = 22,582.5
    # Net: 1,482,917.5
    
    expected = Decimal("1482917.5")
    
    # If the code used floats, we might see 1482917.5000000002 or similar
    # Converting that drift back to Decimal creates a 'dirty' Decimal.
    
    # This assertion checks strictly that we have a clean number
    assert final_balance == expected, f"Floating point drift detected! Got {final_balance}"
"""
        }
    }
}