# scenarios12.py

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
    "OBJECT_REFERENCE_TRAP": {
        "name": "Account Template Service",
        "branch": "feat/account-templates",
        "description": "Implement account creation from templates.",
        
        "changes": {
            "services.py": """
class AccountConfig:
    def __init__(self, name, settings):
        self.name = name
        self.settings = settings # Dictionary

# Global Template
STANDARD_TEMPLATE = AccountConfig("Standard", {"limit": 1000, "currency": "USD"})

def create_custom_account(new_name, custom_limit):

    new_acc = STANDARD_TEMPLATE 
    
    new_acc.name = new_name
    new_acc.settings["limit"] = custom_limit
    
    return new_acc
"""
        },

        "tests": {
            "tests/test_template.py": """
import pytest
from services import create_custom_account, STANDARD_TEMPLATE

def test_template_integrity():
    # Verify initial state
    assert STANDARD_TEMPLATE.name == "Standard"
    assert STANDARD_TEMPLATE.settings["limit"] == 1000
    
    # Create a custom account
    custom = create_custom_account("Premium", 5000)
    
    # Verify custom account
    assert custom.name == "Premium"
    assert custom.settings["limit"] == 5000
    
    # Verify TEMPLATE is UNCHANGED
    # This will fail because the function modified the global object reference
    assert STANDARD_TEMPLATE.name == "Standard", f"Template name corrupted to {STANDARD_TEMPLATE.name}"
    assert STANDARD_TEMPLATE.settings["limit"] == 1000, f"Template limit corrupted to {STANDARD_TEMPLATE.settings['limit']}"
"""
        }
    }
}
