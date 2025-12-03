# scenarios6.py

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
    "CURRENCY_CONVERSION_ERROR": {
        "name": "Currency Service",
        "branch": "feat/currency-service",
        "description": "Implement currency conversion for international transfers.",
        
        "changes": {
            "services.py": """
from decimal import Decimal

# Mock rates
RATES = {
    "USD": Decimal("1.0"),
    "EUR": Decimal("0.85"), # 1 USD = 0.85 EUR
    "GBP": Decimal("0.75")  # 1 USD = 0.75 GBP
}

def convert_currency(amount, from_currency, to_currency):
    if from_currency not in RATES or to_currency not in RATES:
        return None
        
    
    if from_currency == "USD" and to_currency == "EUR":
        return amount / RATES["EUR"]
        
    
    base_amount = amount / RATES[from_currency]
    return base_amount * RATES[to_currency]
"""
        },

        "tests": {
            "tests/test_currency.py": """
import pytest
from decimal import Decimal
from services import convert_currency

def test_usd_to_eur():
    # 100 USD should be 85 EUR
    result = convert_currency(Decimal("100.00"), "USD", "EUR")
    
    # 100 * 0.85 = 85.00
    # Bug implementation: 100 / 0.85 = 117.64...
    
    expected = Decimal("85.00")
    assert abs(result - expected) < Decimal("0.01"), f"Expected {expected}, got {result}"

def test_eur_to_usd():
    # 85 EUR should be 100 USD
    result = convert_currency(Decimal("85.00"), "EUR", "USD")
    expected = Decimal("100.00")
    assert abs(result - expected) < Decimal("0.01"), f"Expected {expected}, got {result}"
"""
        }
    }
}
