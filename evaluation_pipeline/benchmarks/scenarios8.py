# scenarios.py

# --- EXISTING BASE FILES (Mocking the environment) ---
BASE_REPO_FILES = {
    "README.md": "# Core Banking System\n\nEnterprise-grade banking application with account management, transactions, and audit logging.",
    "database.py": """
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import contextmanager

engine = create_engine('sqlite:///:memory:', echo=False)
Session = sessionmaker(bind=engine)
Base = declarative_base()

@contextmanager
def get_session():
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
""",
    "models.py": """
from sqlalchemy import Column, Integer, Numeric, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Account(Base):
    __tablename__ = 'accounts'
    id = Column(Integer, primary_key=True)
    account_number = Column(String(20), unique=True, nullable=False)
    balance = Column(Numeric(12, 2), default=0)
    account_type = Column(String(20), default='standard')  # standard, premium, business
    daily_withdrawal_limit = Column(Numeric(10, 2), default=1000)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    transactions = relationship("Transaction", back_populates="account")

class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    transaction_type = Column(String(20), nullable=False)  # withdrawal, deposit, fee
    amount = Column(Numeric(12, 2), nullable=False)
    fee_amount = Column(Numeric(10, 2), default=0)
    balance_after = Column(Numeric(12, 2), nullable=False)
    status = Column(String(20), default='completed')  # pending, completed, failed, reversed
    description = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    account = relationship("Account", back_populates="transactions")

class DailyWithdrawalTracker(Base):
    __tablename__ = 'daily_withdrawal_tracker'
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    withdrawal_date = Column(DateTime, nullable=False)
    total_withdrawn = Column(Numeric(12, 2), default=0)
""",
    "exceptions.py": """
class BankingException(Exception):
    pass

class InsufficientFundsError(BankingException):
    pass

class AccountNotFoundError(BankingException):
    pass

class AccountInactiveError(BankingException):
    pass

class DailyLimitExceededError(BankingException):
    pass

class InvalidAmountError(BankingException):
    pass

class TransactionFailedError(BankingException):
    pass
"""
}

# --- NEW BENCHMARK DATA ---

BENCHMARK_SCENARIOS = {
    "WITHDRAWAL_SERVICE_COMPREHENSIVE_9": {
        "name": "Comprehensive Withdrawal Service",
        "branch": "feat/withdrawal-service-v2",
        "description": "Implement full withdrawal functionality with balance validation, tiered fees, daily limits, transaction logging, and audit trail.",
        
        "changes": {
            "services/withdrawal_service.py": """
from decimal import Decimal
from datetime import datetime, date
from database import Session, get_session
from models import Account, Transaction, DailyWithdrawalTracker
from services.fee_calculator import FeeCalculator
from services.limit_checker import DailyLimitChecker
from services.transaction_logger import TransactionLogger
from exceptions import (
    InsufficientFundsError, AccountNotFoundError, 
    AccountInactiveError, DailyLimitExceededError, InvalidAmountError
)

class WithdrawalService:
    def __init__(self):
        self.fee_calculator = FeeCalculator()
        self.limit_checker = DailyLimitChecker()
        self.transaction_logger = TransactionLogger()
    
    def withdraw(self, account_id: int, amount: Decimal, description: str = None) -> dict:
        if amount <= 0:
            raise InvalidAmountError("Withdrawal amount must be positive")
        
        session = Session()
        try:
            account = session.query(Account).get(account_id)
            
            if not account:
                raise AccountNotFoundError(f"Account {account_id} not found")
                        
            fee = self.fee_calculator.calculate_withdrawal_fee(
                account.account_type, 
                amount
            )
            total_deduction = amount + fee
            
            if account.balance < amount:
                raise InsufficientFundsError(
                    f"Insufficient funds. Available: {account.balance}, Requested: {amount}"
                )
            
            account.balance = account.balance - total_deduction
            
            daily_total = self.limit_checker.get_today_withdrawals(session, account_id)
            if daily_total + amount > account.daily_withdrawal_limit:
                raise DailyLimitExceededError(
                    f"Daily limit exceeded. Limit: {account.daily_withdrawal_limit}"
                )
            
            self.limit_checker.record_withdrawal(session, account_id, amount)
            
            transaction = self.transaction_logger.log_withdrawal(
                session=session,
                account_id=account_id,
                amount=amount,
                fee=fee,
                balance_after=account.balance,
                description=description
            )
            
            session.commit()
            
            return {
                "success": True,
                "transaction_id": transaction.id,
                "amount_withdrawn": amount,
                "fee_charged": fee,
                "new_balance": account.balance,
                "description": description
            }
            
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()
    
    def get_withdrawal_history(self, account_id: int, limit: int = 10) -> list:
        session = Session()
        try:
            transactions = session.query(Transaction).filter(
                Transaction.account_id == account_id,
                Transaction.transaction_type == 'withdrawal'
            ).order_by(Transaction.created_at.desc()).limit(limit).all()
            
            return transactions
        finally:
            session.close()
    
    def reverse_withdrawal(self, transaction_id: int, reason: str) -> dict:
        session = Session()
        try:
            transaction = session.query(Transaction).get(transaction_id)
            
            if not transaction:
                raise TransactionFailedError(f"Transaction {transaction_id} not found")
            
            if transaction.status == 'reversed':
                raise TransactionFailedError("Transaction already reversed")
            
            account = session.query(Account).get(transaction.account_id)
            
            account.balance = account.balance + transaction.amount
            transaction.status = 'reversed'
            
            session.commit()
            
            return {
                "success": True,
                "refunded_amount": transaction.amount,
                "new_balance": account.balance
            }
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()
""",
            "services/fee_calculator.py": """
from decimal import Decimal, ROUND_HALF_UP

class FeeCalculator:
    FEE_RATES = {
        'standard': Decimal("0.015"),    # 1.5%
        'premium': Decimal("0.005"),     # 0.5%
        'business': Decimal("0.010"),    # 1.0%
    }
    
    MINIMUM_FEES = {
        'standard': Decimal("1.00"),
        'premium': Decimal("0.00"),
        'business': Decimal("2.00"),
    }
    
    MAXIMUM_FEES = {
        'standard': Decimal("50.00"),
        'premium': Decimal("25.00"),
        'business': Decimal("100.00"),
    }
    
    FREE_WITHDRAWAL_THRESHOLD = Decimal("100.00")
    
    def calculate_withdrawal_fee(self, account_type: str, amount: Decimal) -> Decimal:
        if amount > self.FREE_WITHDRAWAL_THRESHOLD:
            return Decimal("0.00")
        

        rate = self.FEE_RATES.get(account_type, Decimal("0.025"))
        
        calculated_fee = (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        min_fee = self.MINIMUM_FEES.get(account_type, Decimal("1.00"))
        max_fee = self.MAXIMUM_FEES.get(account_type, Decimal("50.00"))
        
        fee = min(calculated_fee, max_fee)
        fee = max(fee, min_fee)
        
        return fee
    
    def calculate_expedited_fee(self, base_amount: Decimal) -> Decimal:
        # Flat fee for expedited/emergency withdrawals
        return Decimal("15.00")
    
    def get_fee_estimate(self, account_type: str, amount: Decimal) -> dict:
        fee = self.calculate_withdrawal_fee(account_type, amount)
        return {
            "withdrawal_amount": amount,
            "fee_amount": fee,
            "total_deduction": amount + fee,
            "fee_percentage": (fee / amount * 100).quantize(Decimal("0.01")) if amount > 0 else Decimal("0")
        }
""",
            "services/limit_checker.py": """
from decimal import Decimal
from datetime import datetime, date, timedelta
from models import DailyWithdrawalTracker, Account

class DailyLimitChecker:
    
    def get_today_withdrawals(self, session, account_id: int) -> Decimal:
        today_start = datetime.combine(date.today(), datetime.min.time())
        today_end = datetime.combine(date.today(), datetime.max.time())
        
        tracker = session.query(DailyWithdrawalTracker).filter(
            DailyWithdrawalTracker.account_id == account_id,
            DailyWithdrawalTracker.withdrawal_date >= today_start,
            DailyWithdrawalTracker.withdrawal_date <= today_end
        ).first()
        
        if tracker:
            return tracker.total_withdrawn
        return None
    
    def record_withdrawal(self, session, account_id: int, amount: Decimal) -> None:
        today_start = datetime.combine(date.today(), datetime.min.time())
        today_end = datetime.combine(date.today(), datetime.max.time())
        
        tracker = session.query(DailyWithdrawalTracker).filter(
            DailyWithdrawalTracker.account_id == account_id,
            DailyWithdrawalTracker.withdrawal_date >= today_start,
            DailyWithdrawalTracker.withdrawal_date <= today_end
        ).first()
        
        if tracker:
            tracker.total_withdrawn = tracker.total_withdrawn + amount
        else:
            tracker = DailyWithdrawalTracker(
                account_id=account_id,
                withdrawal_date=datetime.utcnow(),
                total_withdrawn=amount
            )
            session.add(tracker)
    
    def get_remaining_daily_limit(self, session, account_id: int) -> Decimal:
        account = session.query(Account).get(account_id)
        if not account:
            return Decimal("0")
        
        today_withdrawn = self.get_today_withdrawals(session, account_id)
        
        remaining = account.daily_withdrawal_limit - today_withdrawn
        return max(remaining, Decimal("0"))
    
    def can_withdraw(self, session, account_id: int, amount: Decimal) -> tuple:
        remaining = self.get_remaining_daily_limit(session, account_id)
        
        if amount <= remaining:
            return True, None
        else:
            return False, f"Exceeds daily limit. Remaining: {remaining}"
    
    def reset_daily_limits(self, session) -> int:
        yesterday = datetime.combine(date.today() - timedelta(days=1), datetime.max.time())
        
        deleted = session.query(DailyWithdrawalTracker).filter(
            DailyWithdrawalTracker.withdrawal_date < yesterday
        ).delete()
        
        return deleted
""",
            "services/transaction_logger.py": """
from decimal import Decimal
from datetime import datetime
from models import Transaction, Account

class TransactionLogger:
    
    def log_withdrawal(self, session, account_id: int, amount: Decimal, 
                       fee: Decimal, balance_after: Decimal, description: str = None) -> Transaction:
        
        transaction = Transaction(
            account_id=account_id,
            transaction_type='withdrawal',
            amount=amount,
            fee_amount=fee,
            balance_after=balance_after,
            status='completed',
            description=description or "ATM Withdrawal",
            created_at=datetime.utcnow()
        )
        session.add(transaction)
        
        return transaction
    
    def log_deposit(self, session, account_id: int, amount: Decimal,
                    balance_after: Decimal, description: str = None) -> Transaction:
        
        transaction = Transaction(
            account_id=account_id,
            transaction_type='deposit',
            amount=amount,
            fee_amount=Decimal("0"),
            balance_after=balance_after,
            status='completed',
            description=description or "Deposit",
            created_at=datetime.utcnow()
        )
        session.add(transaction)
        return transaction
    
    def log_fee(self, session, account_id: int, fee_amount: Decimal,
                balance_after: Decimal, related_transaction_id: int = None) -> Transaction:
        
        transaction = Transaction(
            account_id=account_id,
            transaction_type='fee',
            amount=fee_amount,
            fee_amount=Decimal("0"),
            balance_after=balance_after,
            status='completed',
            description=f"Service fee for transaction #{related_transaction_id}" if related_transaction_id else "Service fee",
            created_at=datetime.utcnow()
        )
        session.add(transaction)
        return transaction
    
    def get_account_statement(self, session, account_id: int, 
                               start_date: datetime = None, end_date: datetime = None) -> list:
        query = session.query(Transaction).filter(Transaction.account_id == account_id)
        
        if start_date:
            query = query.filter(Transaction.created_at >= start_date)
        if end_date:
            query = query.filter(Transaction.created_at <= end_date)
        
        transactions = query.all()
        
        return [{
            "id": t.id,
            "type": t.transaction_type,
            "amount": str(t.amount),
            "fee": str(t.fee_amount),
            "balance_after": str(t.balance_after),
            "status": t.status,
            "description": t.description,
            "date": t.created_at.isoformat()
        } for t in transactions]
    
    def calculate_total_fees_collected(self, session, account_id: int = None) -> Decimal:
        query = session.query(Transaction).filter(Transaction.status == 'completed')
        
        if account_id:
            query = query.filter(Transaction.account_id == account_id)
        
        transactions = query.all()
        
        total = sum(t.fee_amount for t in transactions)
        return total or Decimal("0")
""",
            "services/__init__.py": """
from services.withdrawal_service import WithdrawalService
from services.fee_calculator import FeeCalculator
from services.limit_checker import DailyLimitChecker
from services.transaction_logger import TransactionLogger

__all__ = ['WithdrawalService', 'FeeCalculator', 'DailyLimitChecker', 'TransactionLogger']
"""
        },

        "tests": {
            "tests/__init__.py": "",
            
            "tests/conftest.py": """
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from database import Base, engine, Session
from models import Account, Transaction, DailyWithdrawalTracker

@pytest.fixture
def db_session():
    Base.metadata.create_all(engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)

@pytest.fixture
def standard_account(db_session):
    account = Account(
        id=1,
        account_number="STD-001",
        balance=Decimal("1000.00"),
        account_type='standard',
        daily_withdrawal_limit=Decimal("500.00"),
        is_active=True
    )
    db_session.add(account)
    db_session.commit()
    return account

@pytest.fixture
def premium_account(db_session):
    account = Account(
        id=2,
        account_number="PRM-001",
        balance=Decimal("5000.00"),
        account_type='premium',
        daily_withdrawal_limit=Decimal("2000.00"),
        is_active=True
    )
    db_session.add(account)
    db_session.commit()
    return account

@pytest.fixture
def business_account(db_session):
    account = Account(
        id=3,
        account_number="BUS-001",
        balance=Decimal("25000.00"),
        account_type='business',
        daily_withdrawal_limit=Decimal("10000.00"),
        is_active=True
    )
    db_session.add(account)
    db_session.commit()
    return account

@pytest.fixture
def inactive_account(db_session):
    account = Account(
        id=4,
        account_number="INA-001",
        balance=Decimal("500.00"),
        account_type='standard',
        daily_withdrawal_limit=Decimal("500.00"),
        is_active=False
    )
    db_session.add(account)
    db_session.commit()
    return account

@pytest.fixture
def low_balance_account(db_session):
    account = Account(
        id=5,
        account_number="LOW-001",
        balance=Decimal("10.00"),
        account_type='standard',
        daily_withdrawal_limit=Decimal("500.00"),
        is_active=True
    )
    db_session.add(account)
    db_session.commit()
    return account

@pytest.fixture
def account_with_history(db_session):
    account = Account(
        id=6,
        account_number="HST-001",
        balance=Decimal("2000.00"),
        account_type='standard',
        daily_withdrawal_limit=Decimal("1000.00"),
        is_active=True
    )
    db_session.add(account)
    db_session.commit()
    
    # Add some transaction history
    for i in range(5):
        txn = Transaction(
            account_id=6,
            transaction_type='withdrawal',
            amount=Decimal("50.00"),
            fee_amount=Decimal("1.00"),
            balance_after=Decimal(str(2000 - (i+1)*51)),
            status='completed',
            description=f"Test withdrawal {i+1}",
            created_at=datetime.utcnow() - timedelta(days=i)
        )
        db_session.add(txn)
    
    db_session.commit()
    return account

@pytest.fixture  
def account_near_daily_limit(db_session):
    account = Account(
        id=7,
        account_number="LMT-001",
        balance=Decimal("5000.00"),
        account_type='standard',
        daily_withdrawal_limit=Decimal("500.00"),
        is_active=True
    )
    db_session.add(account)
    
    # Already withdrawn 450 today
    tracker = DailyWithdrawalTracker(
        account_id=7,
        withdrawal_date=datetime.utcnow(),
        total_withdrawn=Decimal("450.00")
    )
    db_session.add(tracker)
    db_session.commit()
    return account
""",

            "tests/test_withdrawal_service.py": """
import pytest
from decimal import Decimal
from services.withdrawal_service import WithdrawalService
from exceptions import (
    InsufficientFundsError, AccountNotFoundError,
    AccountInactiveError, DailyLimitExceededError, InvalidAmountError
)

class TestWithdrawalBasic:
    
    def test_successful_withdrawal(self, db_session, standard_account):
        service = WithdrawalService()
        result = service.withdraw(1, Decimal("50.00"))
        
        assert result["success"] is True
        assert result["amount_withdrawn"] == Decimal("50.00")
        assert "transaction_id" in result
        
        # Verify balance updated correctly (50 + fee deducted)
        db_session.refresh(standard_account)
        assert standard_account.balance < Decimal("950.00")
    
    def test_withdrawal_with_description(self, db_session, standard_account):
        service = WithdrawalService()
        result = service.withdraw(1, Decimal("100.00"), description="ATM - Main Street")
        
        assert result["success"] is True
        assert result["description"] == "ATM - Main Street"
    
    def test_withdrawal_zero_amount_fails(self, db_session, standard_account):
        service = WithdrawalService()
        
        with pytest.raises(InvalidAmountError):
            service.withdraw(1, Decimal("0.00"))
    
    def test_withdrawal_negative_amount_fails(self, db_session, standard_account):
        service = WithdrawalService()
        
        with pytest.raises(InvalidAmountError):
            service.withdraw(1, Decimal("-50.00"))
    
    def test_withdrawal_nonexistent_account(self, db_session):
        service = WithdrawalService()
        
        with pytest.raises(AccountNotFoundError):
            service.withdraw(9999, Decimal("50.00"))


class TestWithdrawalInsufficientFunds:
    
    def test_insufficient_funds_exact_balance(self, db_session, standard_account):
        service = WithdrawalService()
        
        # Account has 1000.00, try to withdraw exactly 1000.00
        # Should fail because fee will make total > balance
        with pytest.raises(InsufficientFundsError):
            service.withdraw(1, Decimal("1000.00"))
    
    def test_insufficient_funds_over_balance(self, db_session, standard_account):
        service = WithdrawalService()
        
        with pytest.raises(InsufficientFundsError):
            service.withdraw(1, Decimal("2000.00"))
    
    def test_insufficient_funds_with_fee_consideration(self, db_session, low_balance_account):
        service = WithdrawalService()
        
        # Account has 10.00, withdrawal of 9.50 + fee should fail
        # Fee on 9.50 for standard account: min fee is 1.00
        # Total would be 10.50, exceeds 10.00 balance
        with pytest.raises(InsufficientFundsError):
            service.withdraw(5, Decimal("9.50"))
    
    def test_balance_unchanged_on_failed_withdrawal(self, db_session, low_balance_account):
        service = WithdrawalService()
        original_balance = low_balance_account.balance
        
        try:
            service.withdraw(5, Decimal("500.00"))
        except InsufficientFundsError:
            pass
        
        db_session.refresh(low_balance_account)
        assert low_balance_account.balance == original_balance


class TestWithdrawalInactiveAccount:
    
    def test_inactive_account_withdrawal_rejected(self, db_session, inactive_account):
        service = WithdrawalService()
        
        # Inactive accounts should not allow withdrawals
        with pytest.raises(AccountInactiveError):
            service.withdraw(4, Decimal("50.00"))
    
    def test_inactive_account_balance_unchanged(self, db_session, inactive_account):
        service = WithdrawalService()
        original_balance = inactive_account.balance
        
        try:
            service.withdraw(4, Decimal("50.00"))
        except (AccountInactiveError, Exception):
            pass
        
        db_session.refresh(inactive_account)
        assert inactive_account.balance == original_balance


class TestWithdrawalDailyLimits:
    
    def test_within_daily_limit(self, db_session, standard_account):
        service = WithdrawalService()
        
        # Daily limit is 500, withdraw 200
        result = service.withdraw(1, Decimal("200.00"))
        assert result["success"] is True
    
    def test_exceeds_daily_limit_single_transaction(self, db_session, standard_account):
        service = WithdrawalService()
        
        # Daily limit is 500, try to withdraw 600
        with pytest.raises(DailyLimitExceededError):
            service.withdraw(1, Decimal("600.00"))
    
    def test_exceeds_daily_limit_cumulative(self, db_session, account_near_daily_limit):
        service = WithdrawalService()
        
        # Already withdrawn 450 today, limit is 500
        # Trying to withdraw 100 more should fail
        with pytest.raises(DailyLimitExceededError):
            service.withdraw(7, Decimal("100.00"))
    
    def test_exactly_at_daily_limit(self, db_session, account_near_daily_limit):
        service = WithdrawalService()
        
        # Already withdrawn 450, limit is 500
        # Withdrawing exactly 50 should succeed
        result = service.withdraw(7, Decimal("50.00"))
        assert result["success"] is True
    
    def test_balance_unchanged_when_limit_exceeded(self, db_session, account_near_daily_limit):
        service = WithdrawalService()
        original_balance = account_near_daily_limit.balance
        
        try:
            service.withdraw(7, Decimal("200.00"))
        except DailyLimitExceededError:
            pass
        
        db_session.refresh(account_near_daily_limit)
        assert account_near_daily_limit.balance == original_balance


class TestWithdrawalHistory:
    
    def test_get_withdrawal_history(self, db_session, account_with_history):
        service = WithdrawalService()
        history = service.get_withdrawal_history(6, limit=10)
        
        assert len(history) == 5
    
    def test_withdrawal_history_serializable(self, db_session, account_with_history):
        service = WithdrawalService()
        history = service.get_withdrawal_history(6)
        
        # History should be serializable (dict/list), not SQLAlchemy objects
        # This tests that we can access attributes outside session
        for item in history:
            assert hasattr(item, 'amount') or isinstance(item, dict)
            # If it's a dict, we can serialize it
            if isinstance(item, dict):
                import json
                json.dumps(item)  # Should not raise


class TestWithdrawalReversal:
    
    def test_successful_reversal(self, db_session, standard_account):
        service = WithdrawalService()
        
        # First make a withdrawal
        result = service.withdraw(1, Decimal("100.00"))
        transaction_id = result["transaction_id"]
        balance_after_withdrawal = result["new_balance"]
        fee_charged = result["fee_charged"]
        
        # Now reverse it
        reversal = service.reverse_withdrawal(transaction_id, "Customer request")
        
        assert reversal["success"] is True
        # Should refund amount + fee
        expected_refund = Decimal("100.00") + fee_charged
        expected_balance = balance_after_withdrawal + expected_refund
        assert reversal["new_balance"] == expected_balance
    
    def test_reversal_includes_fee_refund(self, db_session, standard_account):
        service = WithdrawalService()
        
        original_balance = standard_account.balance
        
        result = service.withdraw(1, Decimal("100.00"))
        transaction_id = result["transaction_id"]
        
        service.reverse_withdrawal(transaction_id, "Error correction")
        
        db_session.refresh(standard_account)
        # After reversal, balance should be back to original
        assert standard_account.balance == original_balance
    
    def test_double_reversal_fails(self, db_session, standard_account):
        service = WithdrawalService()
        
        result = service.withdraw(1, Decimal("100.00"))
        transaction_id = result["transaction_id"]
        
        # First reversal succeeds
        service.reverse_withdrawal(transaction_id, "First reversal")
        
        # Second reversal should fail
        from exceptions import TransactionFailedError
        with pytest.raises(TransactionFailedError):
            service.reverse_withdrawal(transaction_id, "Second reversal")
    
    def test_reversal_nonexistent_transaction(self, db_session):
        service = WithdrawalService()
        
        from exceptions import TransactionFailedError
        with pytest.raises(TransactionFailedError):
            service.reverse_withdrawal(99999, "Does not exist")
""",

            "tests/test_fee_calculator.py": """
import pytest
from decimal import Decimal
from services.fee_calculator import FeeCalculator

class TestFeeCalculatorBasic:
    
    def test_standard_account_fee_rate(self):
        calculator = FeeCalculator()
        fee = calculator.calculate_withdrawal_fee('standard', Decimal("200.00"))
        
        # 1.5% of 200 = 3.00
        expected = Decimal("3.00")
        assert fee == expected, f"Expected {expected}, got {fee}"
    
    def test_premium_account_fee_rate(self):
        calculator = FeeCalculator()
        fee = calculator.calculate_withdrawal_fee('premium', Decimal("200.00"))
        
        # 0.5% of 200 = 1.00
        expected = Decimal("1.00")
        assert fee == expected, f"Expected {expected}, got {fee}"
    
    def test_business_account_fee_rate(self):
        calculator = FeeCalculator()
        fee = calculator.calculate_withdrawal_fee('business', Decimal("200.00"))
        
        # 1.0% of 200 = 2.00, but minimum for business is 2.00
        expected = Decimal("2.00")
        assert fee == expected, f"Expected {expected}, got {fee}"


class TestFeeCalculatorMinimums:
    
    def test_standard_minimum_fee(self):
        calculator = FeeCalculator()
        fee = calculator.calculate_withdrawal_fee('standard', Decimal("10.00"))
        
        # 1.5% of 10 = 0.15, but minimum is 1.00
        assert fee == Decimal("1.00")
    
    def test_premium_no_minimum_fee(self):
        calculator = FeeCalculator()
        fee = calculator.calculate_withdrawal_fee('premium', Decimal("10.00"))
        
        # 0.5% of 10 = 0.05, premium minimum is 0.00
        assert fee == Decimal("0.05")
    
    def test_business_minimum_fee(self):
        calculator = FeeCalculator()
        fee = calculator.calculate_withdrawal_fee('business', Decimal("50.00"))
        
        # 1.0% of 50 = 0.50, but business minimum is 2.00
        assert fee == Decimal("2.00")


class TestFeeCalculatorMaximums:
    
    def test_standard_maximum_fee(self):
        calculator = FeeCalculator()
        fee = calculator.calculate_withdrawal_fee('standard', Decimal("10000.00"))
        
        # 1.5% of 10000 = 150, but maximum is 50.00
        assert fee == Decimal("50.00")
    
    def test_premium_maximum_fee(self):
        calculator = FeeCalculator()
        fee = calculator.calculate_withdrawal_fee('premium', Decimal("10000.00"))
        
        # 0.5% of 10000 = 50, but maximum is 25.00
        assert fee == Decimal("25.00")
    
    def test_business_maximum_fee(self):
        calculator = FeeCalculator()
        fee = calculator.calculate_withdrawal_fee('business', Decimal("50000.00"))
        
        # 1.0% of 50000 = 500, but maximum is 100.00
        assert fee == Decimal("100.00")


class TestFeeCalculatorThreshold:
    
    def test_below_free_threshold(self):
        calculator = FeeCalculator()
        fee = calculator.calculate_withdrawal_fee('standard', Decimal("50.00"))
        
        # Below 100.00 threshold, fee applies
        assert fee > Decimal("0.00")
    
    def test_at_free_threshold(self):
        calculator = FeeCalculator()
        fee = calculator.calculate_withdrawal_fee('standard', Decimal("100.00"))
        
        # At exactly 100.00, should be free
        assert fee == Decimal("0.00")
    
    def test_above_free_threshold(self):
        calculator = FeeCalculator()
        fee = calculator.calculate_withdrawal_fee('standard', Decimal("150.00"))
        
        # Above 100.00 threshold, should be free
        assert fee == Decimal("0.00")


class TestFeeCalculatorUnknownAccountType:
    
    def test_unknown_account_type_raises_error(self):
        calculator = FeeCalculator()
        
        # Unknown account type should raise error, not silently use default
        with pytest.raises(ValueError):
            calculator.calculate_withdrawal_fee('invalid_type', Decimal("100.00"))
    
    def test_empty_account_type_raises_error(self):
        calculator = FeeCalculator()
        
        with pytest.raises(ValueError):
            calculator.calculate_withdrawal_fee('', Decimal("100.00"))
    
    def test_none_account_type_raises_error(self):
        calculator = FeeCalculator()
        
        with pytest.raises((ValueError, TypeError)):
            calculator.calculate_withdrawal_fee(None, Decimal("100.00"))


class TestFeeEstimate:
    
    def test_fee_estimate_structure(self):
        calculator = FeeCalculator()
        estimate = calculator.get_fee_estimate('standard', Decimal("200.00"))
        
        assert "withdrawal_amount" in estimate
        assert "fee_amount" in estimate
        assert "total_deduction" in estimate
        assert "fee_percentage" in estimate
    
    def test_fee_estimate_calculation(self):
        calculator = FeeCalculator()
        estimate = calculator.get_fee_estimate('standard', Decimal("200.00"))
        
        assert estimate["withdrawal_amount"] == Decimal("200.00")
        assert estimate["total_deduction"] == estimate["withdrawal_amount"] + estimate["fee_amount"]
""",

            "tests/test_limit_checker.py": """
import pytest
from decimal import Decimal
from datetime import datetime, date, timedelta
from services.limit_checker import DailyLimitChecker
from models import DailyWithdrawalTracker
from database import Session

class TestDailyLimitCheckerBasic:
    
    def test_get_today_withdrawals_none(self, db_session, standard_account):
        checker = DailyLimitChecker()
        
        # No withdrawals today
        total = checker.get_today_withdrawals(db_session, 1)
        
        # Should return Decimal("0"), not None
        assert total == Decimal("0")
        assert isinstance(total, Decimal)
    
    def test_get_today_withdrawals_with_history(self, db_session, account_near_daily_limit):
        checker = DailyLimitChecker()
        
        total = checker.get_today_withdrawals(db_session, 7)
        assert total == Decimal("450.00")
    
    def test_record_withdrawal_new_tracker(self, db_session, standard_account):
        checker = DailyLimitChecker()
        
        checker.record_withdrawal(db_session, 1, Decimal("100.00"))
        db_session.commit()
        
        total = checker.get_today_withdrawals(db_session, 1)
        assert total == Decimal("100.00")
    
    def test_record_withdrawal_existing_tracker(self, db_session, account_near_daily_limit):
        checker = DailyLimitChecker()
        
        checker.record_withdrawal(db_session, 7, Decimal("25.00"))
        db_session.commit()
        
        total = checker.get_today_withdrawals(db_session, 7)
        assert total == Decimal("475.00")


class TestRemainingDailyLimit:
    
    def test_remaining_limit_no_withdrawals(self, db_session, standard_account):
        checker = DailyLimitChecker()
        
        remaining = checker.get_remaining_daily_limit(db_session, 1)
        assert remaining == Decimal("500.00")
    
    def test_remaining_limit_partial_usage(self, db_session, account_near_daily_limit):
        checker = DailyLimitChecker()
        
        remaining = checker.get_remaining_daily_limit(db_session, 7)
        assert remaining == Decimal("50.00")
    
    def test_remaining_limit_fully_used(self, db_session, standard_account):
        checker = DailyLimitChecker()
        
        # Use up the entire limit
        checker.record_withdrawal(db_session, 1, Decimal("500.00"))
        db_session.commit()
        
        remaining = checker.get_remaining_daily_limit(db_session, 1)
        assert remaining == Decimal("0.00")
    
    def test_remaining_limit_nonexistent_account(self, db_session):
        checker = DailyLimitChecker()
        
        remaining = checker.get_remaining_daily_limit(db_session, 9999)
        assert remaining == Decimal("0")


class TestCanWithdraw:
    
    def test_can_withdraw_within_limit(self, db_session, standard_account):
        checker = DailyLimitChecker()
        
        can_withdraw, message = checker.can_withdraw(db_session, 1, Decimal("200.00"))
        
        assert can_withdraw is True
        assert message is None
    
    def test_cannot_withdraw_exceeds_limit(self, db_session, account_near_daily_limit):
        checker = DailyLimitChecker()
        
        can_withdraw, message = checker.can_withdraw(db_session, 7, Decimal("100.00"))
        
        assert can_withdraw is False
        assert "Exceeds daily limit" in message
    
    def test_can_withdraw_exact_remaining(self, db_session, account_near_daily_limit):
        checker = DailyLimitChecker()
        
        can_withdraw, message = checker.can_withdraw(db_session, 7, Decimal("50.00"))
        
        assert can_withdraw is True


class TestResetDailyLimits:
    
    def test_reset_removes_old_trackers(self, db_session, standard_account):
        checker = DailyLimitChecker()
        
        # Add old tracker
        old_tracker = DailyWithdrawalTracker(
            account_id=1,
            withdrawal_date=datetime.utcnow() - timedelta(days=3),
            total_withdrawn=Decimal("200.00")
        )
        db_session.add(old_tracker)
        db_session.commit()
        
        deleted = checker.reset_daily_limits(db_session)
        db_session.commit()
        
        assert deleted >= 1
    
    def test_reset_keeps_today_trackers(self, db_session, account_near_daily_limit):
        checker = DailyLimitChecker()
        
        # Today's tracker should remain
        checker.reset_daily_limits(db_session)
        db_session.commit()
        
        total = checker.get_today_withdrawals(db_session, 7)
        assert total == Decimal("450.00")
""",

            "tests/test_transaction_logger.py": """
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from services.transaction_logger import TransactionLogger
from models import Transaction

class TestTransactionLoggerBasic:
    
    def test_log_withdrawal(self, db_session, standard_account):
        logger = TransactionLogger()
        
        txn = logger.log_withdrawal(
            session=db_session,
            account_id=1,
            amount=Decimal("100.00"),
            fee=Decimal("1.50"),
            balance_after=Decimal("898.50"),
            description="Test withdrawal"
        )
        db_session.commit()
        
        assert txn.id is not None
        assert txn.transaction_type == 'withdrawal'
        assert txn.amount == Decimal("100.00")
        assert txn.fee_amount == Decimal("1.50")
    
    def test_log_deposit(self, db_session, standard_account):
        logger = TransactionLogger()
        
        txn = logger.log_deposit(
            session=db_session,
            account_id=1,
            amount=Decimal("500.00"),
            balance_after=Decimal("1500.00")
        )
        db_session.commit()
        
        assert txn.transaction_type == 'deposit'
        assert txn.fee_amount == Decimal("0")
    
    def test_log_fee_separately(self, db_session, standard_account):
        logger = TransactionLogger()
        
        # First log a withdrawal
        withdrawal_txn = logger.log_withdrawal(
            session=db_session,
            account_id=1,
            amount=Decimal("100.00"),
            fee=Decimal("1.50"),
            balance_after=Decimal("898.50")
        )
        db_session.commit()
        
        # Then log fee separately (audit requirement)
        fee_txn = logger.log_fee(
            session=db_session,
            account_id=1,
            fee_amount=Decimal("1.50"),
            balance_after=Decimal("898.50"),
            related_transaction_id=withdrawal_txn.id
        )
        db_session.commit()
        
        assert fee_txn.transaction_type == 'fee'
        assert f"#{withdrawal_txn.id}" in fee_txn.description


class TestAccountStatement:
    
    def test_statement_returns_ordered_results(self, db_session, account_with_history):
        logger = TransactionLogger()
        
        statement = logger.get_account_statement(db_session, 6)
        
        # Should be ordered by date (most recent first or chronological)
        dates = [item["date"] for item in statement]
        sorted_dates = sorted(dates, reverse=True)
        
        assert dates == sorted_dates, "Statement should be ordered by date descending"
    
    def test_statement_date_filtering(self, db_session, account_with_history):
        logger = TransactionLogger()
        
        # Get only last 2 days
        start_date = datetime.utcnow() - timedelta(days=2)
        statement = logger.get_account_statement(db_session, 6, start_date=start_date)
        
        assert len(statement) <= 3  # Should only have recent transactions
    
    def test_statement_serializable_format(self, db_session, account_with_history):
        logger = TransactionLogger()
        
        statement = logger.get_account_statement(db_session, 6)
        
        import json
        # Should be JSON serializable
        json_str = json.dumps(statement)
        assert json_str is not None


class TestFeeCalculations:
    
    def test_total_fees_collected(self, db_session, account_with_history):
        logger = TransactionLogger()
        
        total_fees = logger.calculate_total_fees_collected(db_session, account_id=6)
        
        # 5 transactions with 1.00 fee each
        assert total_fees == Decimal("5.00")
    
    def test_total_fees_excludes_reversed(self, db_session, standard_account):
        logger = TransactionLogger()
        
        # Log a transaction
        txn = logger.log_withdrawal(
            session=db_session,
            account_id=1,
            amount=Decimal("100.00"),
            fee=Decimal("5.00"),
            balance_after=Decimal("895.00")
        )
        db_session.commit()
        
        # Now mark it as reversed
        txn.status = 'reversed'
        db_session.commit()
        
        # Total fees should not include reversed transaction
        total_fees = logger.calculate_total_fees_collected(db_session, account_id=1)
        assert total_fees == Decimal("0.00"), "Reversed transaction fees should not be counted"
    
    def test_total_fees_all_accounts(self, db_session, account_with_history, standard_account):
        logger = TransactionLogger()
        
        # Add another transaction to different account
        logger.log_withdrawal(
            session=db_session,
            account_id=1,
            amount=Decimal("50.00"),
            fee=Decimal("2.00"),
            balance_after=Decimal("948.00")
        )
        db_session.commit()
        
        # Get total across all accounts
        total_fees = logger.calculate_total_fees_collected(db_session)
        
        # 5 x 1.00 from history + 2.00 from new
        assert total_fees == Decimal("7.00")
"""
        }
    }
}