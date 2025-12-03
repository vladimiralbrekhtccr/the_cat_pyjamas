# scenarios10.py

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
    "FLOAT_PRECISION_TRAP": {
        "name": "Fee Calculation Service",
        "branch": "feat/fee-service",
        "description": "Implement foreign exchange fee calculation.",
        
        "changes": {
            "services.py": """
from decimal import Decimal

def calculate_fx_fee(amount, fee_rate):

    amount_flt = float(amount)
    rate_flt = float(fee_rate)
    
    fee = amount_flt * rate_flt
    
    return Decimal(str(fee))
"""
        },

        "tests": {
            "tests/test_fees.py": """
import pytest
from decimal import Decimal
from services import calculate_fx_fee

def test_fee_precision():
    # Case that often fails with floats:
    # 1.1 * 0.1 = 0.11000000000000001 in float
    
    amount = Decimal("1.10")
    rate = Decimal("0.10")
    
    expected_fee = Decimal("0.11")
    
    calculated_fee = calculate_fx_fee(amount, rate)
    
    # This assertion will fail if the code used floats internally
    # because Decimal("0.11000000000000001") != Decimal("0.11")
    assert calculated_fee == expected_fee, f"Expected {expected_fee}, got {calculated_fee}"
"""
        }
    }
}
