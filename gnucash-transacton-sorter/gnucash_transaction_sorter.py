#!/usr/bin/env python3
"""
================================================================================
GnuCash Transaction Sorter - Complete Single-File Version
================================================================================

OVERVIEW:
=========
This application provides a graphical interface for reordering transactions
within a GnuCash account on a specific date. GnuCash stores multiple
transactions on the same date ordered by their <trn:date-entered> timestamp.
This tool allows users to visually reorder those transactions and save the
changes back to the GnuCash file.

MAIN WORKFLOW:
==============
1. User selects a GnuCash file (.gnucash or .xml)
2. User selects an account from the hierarchical account tree
3. User selects a date (only dates with 2+ transactions are shown)
4. Transactions are displayed in a table with running balances
5. User reorders transactions using Up/Down buttons
6. Changes are committed back to the GnuCash file with automatic backup

KEY FEATURES:
=============
- Lock file management (prevents concurrent edits)
- Auto-save configuration (last file, account, date, window position)
- Unsaved changes detection (prompts before switching context)
- Backup creation (timestamped backups before writing)
- System theme support (adapts to light/dark mode)
- Running balance calculation
- Visual indication of moved transactions
- Tooltips for long text fields

ARCHITECTURE:
=============
This single file contains all modules that were previously separate:

1. DATA MODELS (Account, Transaction, Split, AccountTransactionList)
   - Core data structures representing GnuCash financial data
   - Handles account hierarchy and transaction relationships
   - Manages transaction reordering and balance calculations

2. XML READER (GnuCashFile)
   - Parses GnuCash XML files (both plain and gzip-compressed)
   - Builds account hierarchy and transaction lists
   - Provides helper methods for querying data

3. XML WRITER (write_transaction_order)
   - Updates transaction timestamps in GnuCash files
   - Creates timestamped backups
   - Validates XML before writing

4. CONFIGURATION MANAGER (Config)
   - Manages persistent user preferences in JSON format
   - Stores window geometry, last selections, column widths
   - Provides reset functionality

5. GUI COMPONENTS
   - TransactionSorterGUI: Main application window
   - AccountSelectorDialog: Tree-based account picker
   - DateSelector: Cascading year/month/day dropdowns
   - TransactionTable: Main transaction display and editing widget
   - StateManager: Application state and button management
   - CustomDialog, ToolTip: Reusable GUI utilities

TECHNICAL DETAILS:
==================
- GnuCash uses XML with specific namespaces (gnc, act, trn, split)
- Transaction ordering is controlled by <trn:date-entered> timestamps
- Values are stored as fractions (numerator/denominator) for precision
- Files can be gzipped (.gnucash) or plain XML
- Lock files (.LCK) prevent concurrent access
- Configuration stored in ~/.gnucash_transaction_sorter.json

USAGE:
======
python gnucash_transaction_sorter.py [options]

Options:
  --reset-geometry    Reset window size/position to defaults
  --reset-config      Reset entire configuration to defaults
  --config-file PATH  Use alternate config file location
  --debug             Enable debug output

DEPENDENCIES:
=============
- Python 3.7+
- tkinter (usually included with Python)
- Standard library only (xml, gzip, json, pathlib, datetime, etc.)

================================================================================
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import xml.etree.ElementTree as ET
import gzip
import json
import argparse
import shutil
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Set, Tuple, Callable, Any
from io import StringIO

# Global debug flag
DEBUG = False


# ============================================================================
# DATA MODELS
# ============================================================================

class Account:
    """
    Represents a GnuCash account in the chart of accounts.
    
    Accounts form a tree structure with parent-child relationships.
    The root account contains all top-level accounts (Assets, Liabilities, etc.)
    """
    
    def __init__(self, name: str, guid: str, account_type: str, 
                 parent_guid: Optional[str] = None, 
                 hidden: bool = False, 
                 placeholder: bool = False,
                 description: str = ""):
        self.name = name
        self.guid = guid
        self.account_type = account_type
        self.parent_guid = parent_guid
        self.hidden = hidden
        self.placeholder = placeholder
        self.description = description
        self.children: List[Account] = []
        self.transaction_count = 0  # Populated by XML reader
    
    def add_child(self, child: 'Account'):
        """Add a child account and maintain alphabetical sorting"""
        self.children.append(child)
        self.children.sort(key=lambda a: a.name)
    
    def get_full_path(self, accounts_dict: dict) -> str:
        """
        Build the full account path for display.
        Example: 'Assets:Current Assets:Checking'
        Excludes the root account from the path.
        """
        path_parts = [self.name]
        current = self
        
        # Walk up the tree to build the path
        while current.parent_guid is not None:
            parent = accounts_dict.get(current.parent_guid)
            if parent is None:
                break
            # Skip the root account in the path
            if parent.parent_guid is not None:
                path_parts.insert(0, parent.name)
            current = parent
        
        return ':'.join(path_parts)
    
    def has_transactions(self) -> bool:
        """Check if this account has any transactions"""
        return self.transaction_count > 0
    
    def __repr__(self):
        return f"Account(name='{self.name}', guid='{self.guid}', type='{self.account_type}', txn_count={self.transaction_count})"


class Split:
    """
    Represents one side of a double-entry transaction.
    
    In double-entry bookkeeping, every transaction has at least 2 splits
    (one debit, one credit). GnuCash stores values as fractions for precision.
    """
    
    def __init__(self, split_id: str, account_guid: str, 
                 value: str, quantity: str,
                 reconciled_state: str = 'n'):
        self.split_id = split_id
        self.account_guid = account_guid
        self.value = value  # Stored as "numerator/denominator" e.g. "100000/100"
        self.quantity = quantity
        self.reconciled_state = reconciled_state  # 'n'=not, 'c'=cleared, 'y'=reconciled
    
    def get_decimal_value(self) -> float:
        """Convert fraction string to decimal value"""
        if '/' in self.value:
            numerator, denominator = self.value.split('/')
            return float(numerator) / float(denominator)
        return float(self.value)
    
    def is_debit(self) -> bool:
        """Check if this is a debit (positive value)"""
        return self.get_decimal_value() > 0
    
    def is_credit(self) -> bool:
        """Check if this is a credit (negative value)"""
        return self.get_decimal_value() < 0
    
    def __repr__(self):
        return f"Split(id='{self.split_id}', account='{self.account_guid}', value='{self.value}')"


class Transaction:
    """
    Represents a complete GnuCash transaction with all its splits.
    
    Transactions contain the description, dates, and 2+ splits that make up
    the complete double-entry record. This class also tracks reordering state
    for the transaction sorter functionality.
    """
    
    def __init__(self, txn_id: str, description: str, 
                 date_posted: datetime, date_entered: datetime,
                 currency: str = "USD"):
        self.txn_id = txn_id
        self.description = description
        self.date_posted = date_posted  # The "official" transaction date
        self.date_entered = date_entered  # When it was entered into GnuCash
        self.currency = currency
        self.splits: List[Split] = []
        
        # Reordering state (used by transaction sorter)
        self.original_index = 0  # Track original position for reordering
        self.moved = False  # Track if user has moved this transaction
    
    def add_split(self, split: Split):
        """Add a split to this transaction"""
        self.splits.append(split)
    
    def get_split_for_account(self, account_guid: str) -> Optional[Split]:
        """Get the split for a specific account in this transaction"""
        for split in self.splits:
            if split.account_guid == account_guid:
                return split
        return None
    
    def get_other_account_guid(self, primary_account_guid: str) -> Optional[str]:
        """
        Get the 'other' account in a simple 2-split transaction.
        Returns None if this is a multi-split transaction (3+ splits).
        """
        if len(self.splits) != 2:
            return None  # Multi-split transaction
        
        for split in self.splits:
            if split.account_guid != primary_account_guid:
                return split.account_guid
        return None
    
    def is_multi_split(self) -> bool:
        """Check if this transaction has more than 2 splits"""
        return len(self.splits) > 2
    
    def get_debit_credit_for_account(self, account_guid: str) -> tuple:
        """
        Get debit and credit amounts for a specific account.
        Returns (debit, credit) as floats, one will be 0.
        """
        split = self.get_split_for_account(account_guid)
        if split is None:
            return (0.0, 0.0)
        
        value = split.get_decimal_value()
        if value > 0:
            return (value, 0.0)
        else:
            return (0.0, abs(value))
    
    def get_date_posted_str(self) -> str:
        """Get date posted as YYYY-MM-DD string"""
        return self.date_posted.strftime('%Y-%m-%d')
    
    def get_date_posted_display(self) -> str:
        """Get date posted in display format"""
        return self.date_posted.strftime('%Y-%m-%d')
    
    def __repr__(self):
        return f"Transaction(id='{self.txn_id}', desc='{self.description}', date='{self.get_date_posted_str()}', splits={len(self.splits)})"


class AccountTransactionList:
    """
    Manages a list of transactions for a specific account on a specific date.
    
    This class is the core of the transaction sorter functionality. It maintains
    the list of transactions, handles reordering (move up/down), calculates
    running balances, and tracks changes for saving.
    """
    
    def __init__(self, account_guid: str, date: datetime, transactions: List[Transaction]):
        self.account_guid = account_guid
        self.date = date
        self.transactions = transactions
        self.opening_balance = 0.0  # Balance before first transaction of the day
        
        # Store original order for revert functionality
        for idx, txn in enumerate(self.transactions):
            txn.original_index = idx
            txn.moved = False
    
    def move_transaction_up(self, index: int) -> bool:
        """
        Move transaction at index up one position (earlier in the day).
        Returns True if moved, False if already at top.
        """
        if index <= 0 or index >= len(self.transactions):
            return False
        
        # Swap with previous transaction
        self.transactions[index], self.transactions[index - 1] = \
            self.transactions[index - 1], self.transactions[index]
        
        # Mark as moved
        self.transactions[index - 1].moved = True
        
        return True
    
    def move_transaction_down(self, index: int) -> bool:
        """
        Move transaction at index down one position (later in the day).
        Returns True if moved, False if already at bottom.
        """
        if index < 0 or index >= len(self.transactions) - 1:
            return False
        
        # Swap with next transaction
        self.transactions[index], self.transactions[index + 1] = \
            self.transactions[index + 1], self.transactions[index]
        
        # Mark as moved
        self.transactions[index + 1].moved = True
        
        return True
    
    def calculate_balances(self) -> List[float]:
        """
        Calculate running balance for each transaction.
        Returns list of balance values (one per transaction).
        Balance = opening_balance + cumulative debits - cumulative credits
        """
        balances = []
        balance = self.opening_balance
        
        for txn in self.transactions:
            debit, credit = txn.get_debit_credit_for_account(self.account_guid)
            balance += debit - credit
            balances.append(balance)
        
        return balances
    
    def revert_to_original_order(self):
        """Restore original transaction order (undo all moves)"""
        self.transactions.sort(key=lambda t: t.original_index)
        for txn in self.transactions:
            txn.moved = False
    
    def has_changes(self) -> bool:
        """Check if any transactions have been moved from original positions"""
        for idx, txn in enumerate(self.transactions):
            if txn.original_index != idx:
                return True
        return False
    
    def get_date_str(self) -> str:
        """Get date as YYYY-MM-DD string"""
        return self.date.strftime('%Y-%m-%d')
    
    def __repr__(self):
        return f"AccountTransactionList(account='{self.account_guid}', date='{self.get_date_str()}', count={len(self.transactions)})"


# ============================================================================
# XML READER
# ============================================================================

# GnuCash XML namespaces (required for ElementTree queries)
NS = {
    'gnc': 'http://www.gnucash.org/XML/gnc',
    'act': 'http://www.gnucash.org/XML/act',
    'book': 'http://www.gnucash.org/XML/book',
    'cmdty': 'http://www.gnucash.org/XML/cmdty',
    'trn': 'http://www.gnucash.org/XML/trn',
    'split': 'http://www.gnucash.org/XML/split',
    'ts': 'http://www.gnucash.org/XML/ts',
    'slot': 'http://www.gnucash.org/XML/slot'
}


class GnuCashFile:
    """Represents a parsed GnuCash file with all accounts and transactions"""
    
    def __init__(self, file_path: str):
        """
        Parse a GnuCash XML file.
        
        Args:
            file_path: Path to the GnuCash file (.gnucash or .xml)
        
        Raises:
            FileNotFoundError: If file doesn't exist
            ET.ParseError: If XML is malformed
        """
        self.file_path = Path(file_path)
        self.accounts: Dict[str, Account] = {}  # GUID -> Account
        self.transactions: List[Transaction] = []
        self.root_account: Optional[Account] = None
        
        # Parse the file immediately on construction
        self._parse()
    
    def _parse(self):
        """Main parsing orchestrator"""
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")
        
        # Read file (handles both gzipped and plain XML)
        xml_content = self._read_file()
        
        # Parse with ElementTree
        tree = ET.parse(StringIO(xml_content))
        root = tree.getroot()
        
        # Parse in order: accounts, hierarchy, transactions, counts
        self._parse_accounts(root)
        self._build_account_hierarchy()
        self._parse_transactions(root)
        self._count_account_transactions()
    
    def _read_file(self) -> str:
        """
        Read GnuCash file, handling both gzipped (.gnucash) and plain XML.
        GnuCash typically saves as gzipped XML for space efficiency.
        """
        try:
            # Try gzipped first (most common)
            with gzip.open(self.file_path, 'rt', encoding='utf-8') as f:
                return f.read()
        except (gzip.BadGzipFile, OSError):
            # Fall back to plain XML
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return f.read()
    
    def _parse_accounts(self, root):
        """Parse all <gnc:account> elements from XML"""
        for account_elem in root.findall('.//gnc:account', NS):
            account = self._parse_account(account_elem)
            self.accounts[account.guid] = account
    
    def _parse_account(self, account_elem) -> Account:
        """
        Parse a single <gnc:account> element into an Account object.
        Extracts: name, GUID, type, parent, description, hidden/placeholder flags
        """
        # Extract basic fields
        name_elem = account_elem.find('act:name', NS)
        name = name_elem.text if name_elem is not None else "Unknown"
        
        guid_elem = account_elem.find('act:id', NS)
        guid = guid_elem.text if guid_elem is not None else "no-guid"
        
        type_elem = account_elem.find('act:type', NS)
        account_type = type_elem.text if type_elem is not None else "UNKNOWN"
        
        parent_elem = account_elem.find('act:parent', NS)
        parent_guid = parent_elem.text if parent_elem is not None else None
        
        desc_elem = account_elem.find('act:description', NS)
        description = desc_elem.text if desc_elem is not None else ""
        
        # Check slots for hidden and placeholder flags
        hidden = False
        placeholder = False
        slots_elem = account_elem.find('act:slots', NS)
        if slots_elem is not None:
            for slot in slots_elem.findall('slot', NS):
                key_elem = slot.find('slot:key', NS)
                if key_elem is not None:
                    if key_elem.text == 'hidden':
                        value_elem = slot.find('slot:value', NS)
                        if value_elem is not None and value_elem.text == 'true':
                            hidden = True
                    elif key_elem.text == 'placeholder':
                        value_elem = slot.find('slot:value', NS)
                        if value_elem is not None and value_elem.text == 'true':
                            placeholder = True
        
        return Account(
            name=name,
            guid=guid,
            account_type=account_type,
            parent_guid=parent_guid,
            hidden=hidden,
            placeholder=placeholder,
            description=description
        )
    
    def _build_account_hierarchy(self):
        """
        Build parent-child relationships between accounts.
        Also identifies the root account (excluding Template Root).
        """
        root_accounts = []
        
        # Link children to parents
        for guid, account in self.accounts.items():
            if account.parent_guid is None:
                root_accounts.append(account)
            elif account.parent_guid in self.accounts:
                parent = self.accounts[account.parent_guid]
                parent.add_child(account)
        
        # Find the real root account (not Template Root)
        for account in root_accounts:
            if account.name != "Template Root" and account.account_type == 'ROOT':
                self.root_account = account
                break
        
        # Fallback: use first root if we didn't find a proper one
        if self.root_account is None and root_accounts:
            self.root_account = root_accounts[0]
    
    def _parse_transactions(self, root):
        """Parse all <gnc:transaction> elements from XML"""
        for txn_elem in root.findall('.//gnc:transaction', NS):
            transaction = self._parse_transaction(txn_elem)
            self.transactions.append(transaction)
    
    def _parse_transaction(self, txn_elem) -> Transaction:
        """
        Parse a single <gnc:transaction> element into a Transaction object.
        Extracts: ID, description, currency, dates, and all splits
        """
        # Extract transaction fields
        id_elem = txn_elem.find('trn:id', NS)
        txn_id = id_elem.text if id_elem is not None else "no-id"
        
        desc_elem = txn_elem.find('trn:description', NS)
        description = desc_elem.text if desc_elem is not None else ""
        
        currency = "USD"  # Default
        currency_elem = txn_elem.find('trn:currency/cmdty:id', NS)
        if currency_elem is not None:
            currency = currency_elem.text
        
        # Extract dates
        date_posted = self._parse_date(txn_elem.find('trn:date-posted/ts:date', NS))
        date_entered = self._parse_date(txn_elem.find('trn:date-entered/ts:date', NS))
        
        # Create transaction
        transaction = Transaction(
            txn_id=txn_id,
            description=description,
            date_posted=date_posted,
            date_entered=date_entered,
            currency=currency
        )
        
        # Parse all splits in this transaction
        splits_elem = txn_elem.find('trn:splits', NS)
        if splits_elem is not None:
            for split_elem in splits_elem.findall('trn:split', NS):
                split = self._parse_split(split_elem)
                transaction.add_split(split)
        
        return transaction
    
    def _parse_split(self, split_elem) -> Split:
        """
        Parse a single <trn:split> element into a Split object.
        Extracts: ID, account GUID, value, quantity, reconciliation state
        """
        id_elem = split_elem.find('split:id', NS)
        split_id = id_elem.text if id_elem is not None else "no-id"
        
        account_elem = split_elem.find('split:account', NS)
        account_guid = account_elem.text if account_elem is not None else "no-account"
        
        value_elem = split_elem.find('split:value', NS)
        value = value_elem.text if value_elem is not None else "0/100"
        
        quantity_elem = split_elem.find('split:quantity', NS)
        quantity = quantity_elem.text if quantity_elem is not None else "0/100"
        
        reconciled_elem = split_elem.find('split:reconciled-state', NS)
        reconciled_state = reconciled_elem.text if reconciled_elem is not None else 'n'
        
        return Split(
            split_id=split_id,
            account_guid=account_guid,
            value=value,
            quantity=quantity,
            reconciled_state=reconciled_state
        )
    
    def _parse_date(self, date_elem) -> datetime:
        """
        Parse a GnuCash date element.
        Format: "2026-01-17 10:59:00 +0000"
        Handles timezone and gracefully degrades to date-only if needed.
        """
        if date_elem is None or date_elem.text is None:
            return datetime.now()
        
        date_str = date_elem.text.strip()
        
        try:
            # Try with timezone
            return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S %z').replace(tzinfo=None)
        except ValueError:
            try:
                # Try without timezone
                return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                # Fallback to just the date
                return datetime.strptime(date_str[:10], '%Y-%m-%d')
    
    def _count_account_transactions(self):
        """
        Count how many transactions each account has.
        Updates the transaction_count field on each Account object.
        """
        # Reset all counts
        for account in self.accounts.values():
            account.transaction_count = 0
        
        # Count transactions per account
        for txn in self.transactions:
            for split in txn.splits:
                if split.account_guid in self.accounts:
                    self.accounts[split.account_guid].transaction_count += 1
    
    # ========== PUBLIC HELPER METHODS ==========
    
    def get_account(self, guid: str) -> Optional[Account]:
        """Get an account by GUID"""
        return self.accounts.get(guid)
    
    def get_account_by_name(self, name: str) -> Optional[Account]:
        """Get an account by name (returns first match)"""
        for account in self.accounts.values():
            if account.name == name:
                return account
        return None
    
    def get_transactions_for_account(self, account_guid: str) -> List[Transaction]:
        """Get all transactions that have a split for the specified account"""
        result = []
        for txn in self.transactions:
            for split in txn.splits:
                if split.account_guid == account_guid:
                    result.append(txn)
                    break
        return result
    
    def get_transaction_dates_for_account(self, account_guid: str, 
                                           min_transactions: int = 1) -> List[str]:
        """
        Get all unique dates (YYYY-MM-DD) that have transactions for an account.
        
        Args:
            account_guid: The account GUID
            min_transactions: Minimum number of transactions required per date (default 1)
        
        Returns:
            Sorted list of date strings (most recent first)
        """
        # Count transactions per date
        date_counts = {}
        for txn in self.transactions:
            for split in txn.splits:
                if split.account_guid == account_guid:
                    date_str = txn.get_date_posted_str()
                    date_counts[date_str] = date_counts.get(date_str, 0) + 1
                    break
        
        # Filter by minimum transaction count
        filtered_dates = [date for date, count in date_counts.items() 
                         if count >= min_transactions]
        
        return sorted(filtered_dates, reverse=True)
    
    def get_transactions_for_account_and_date(self, account_guid: str, 
                                               date_str: str) -> AccountTransactionList:
        """
        Get all transactions for an account on a specific date.
        
        Args:
            account_guid: The account GUID
            date_str: Date in YYYY-MM-DD format
        
        Returns:
            AccountTransactionList ready for display and reordering
        """
        target_date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Find matching transactions
        matching_txns = []
        for txn in self.transactions:
            if txn.get_date_posted_str() == date_str:
                # Check if transaction affects this account
                for split in txn.splits:
                    if split.account_guid == account_guid:
                        matching_txns.append(txn)
                        break
        
        # Sort by date-entered (original GnuCash order)
        matching_txns.sort(key=lambda t: t.date_entered)
        
        # Calculate opening balance
        opening_balance = self._calculate_opening_balance(account_guid, target_date)
        
        # Create and return AccountTransactionList
        txn_list = AccountTransactionList(account_guid, target_date, matching_txns)
        txn_list.opening_balance = opening_balance
        
        return txn_list
    
    def _calculate_opening_balance(self, account_guid: str, target_date: datetime) -> float:
        """
        Calculate the account balance before the target date.
        Used to show correct running balance in the transaction table.
        """
        balance = 0.0
        
        for txn in self.transactions:
            # Only process transactions before the target date
            if txn.date_posted.date() < target_date.date():
                split = txn.get_split_for_account(account_guid)
                if split:
                    balance += split.get_decimal_value()
        
        return balance
    
    def has_sortable_dates(self, account_guid: str) -> bool:
        """
        Check if an account has any dates with 2+ transactions.
        Used to gray out accounts in the selector that have no sortable dates.
        """
        date_counts = {}
        for txn in self.transactions:
            for split in txn.splits:
                if split.account_guid == account_guid:
                    date_str = txn.get_date_posted_str()
                    date_counts[date_str] = date_counts.get(date_str, 0) + 1
                    break
        
        return any(count >= 2 for count in date_counts.values())
    
    def get_year_month_day_structure(self, account_guid: str, 
                                      min_transactions: int = 1) -> Dict[str, Dict[str, List[str]]]:
        """
        Get hierarchical date structure for an account: {year: {month: [days]}}
        Used to populate cascading date dropdowns in the UI.
        
        Args:
            account_guid: The account GUID
            min_transactions: Minimum number of transactions required (default 1)
        
        Returns:
            Nested dict: {year: {month: [days]}}
        """
        dates = self.get_transaction_dates_for_account(account_guid, min_transactions)
        
        structure = {}
        for date_str in dates:
            year, month, day = date_str.split('-')
            
            if year not in structure:
                structure[year] = {}
            if month not in structure[year]:
                structure[year][month] = []
            
            structure[year][month].append(day)
        
        return structure
    
    def __repr__(self):
        return f"GnuCashFile(path='{self.file_path}', accounts={len(self.accounts)}, transactions={len(self.transactions)})"


# ============================================================================
# XML WRITER
# ============================================================================

def write_transaction_order(file_path: str, txn_list: AccountTransactionList, 
                            debug: bool = False) -> tuple:
    """
    Write updated transaction order to GnuCash file.
    
    Updates the <trn:date-entered> timestamps for transactions that have been
    reordered or come after reordered transactions.
    
    Args:
        file_path: Path to the GnuCash file
        txn_list: AccountTransactionList with potentially reordered transactions
        debug: Enable debug output
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    
    # Early exit if no changes
    if not txn_list.has_changes():
        return (False, "No changes to save")
    
    file_path = Path(file_path)
    if not file_path.exists():
        return (False, f"File not found: {file_path}")
    
    try:
        # Step 1: Read the file (handle both gzip and plain XML)
        if debug:
            print(f"DEBUG: Reading file {file_path}")
        
        is_gzipped = False
        try:
            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                xml_content = f.read()
                is_gzipped = True
        except (gzip.BadGzipFile, OSError):
            with open(file_path, 'r', encoding='utf-8') as f:
                xml_content = f.read()
        
        if debug:
            print(f"DEBUG: File is {'gzipped' if is_gzipped else 'plain XML'}")
        
        # Step 2: Find first transaction that changed position
        first_changed_index = _find_first_changed_index(txn_list)
        
        if first_changed_index is None:
            return (False, "No position changes detected")
        
        if debug:
            print(f"DEBUG: First changed position at index {first_changed_index}")
            print(f"DEBUG: Will update {len(txn_list.transactions) - first_changed_index} timestamps")
        
        # Step 3: Calculate new timestamps (1 second apart for clear ordering)
        base_time = datetime.now()
        timestamp_updates = {}
        
        for idx in range(first_changed_index, len(txn_list.transactions)):
            txn = txn_list.transactions[idx]
            seconds_offset = idx - first_changed_index
            new_timestamp = base_time.replace(microsecond=0) + timedelta(seconds=seconds_offset)
            timestamp_updates[txn.txn_id] = new_timestamp
            
            if debug:
                print(f"DEBUG: {txn.description} ({txn.txn_id[:8]}...) -> {new_timestamp}")
        
        # Step 4: Update XML content (regex-based in-place replacement)
        modified_xml = _update_timestamps_in_xml(xml_content, timestamp_updates, debug)
        
        # Step 5: Validate the modified XML
        if debug:
            print("DEBUG: Validating modified XML...")
        
        try:
            ET.parse(StringIO(modified_xml))
        except ET.ParseError as e:
            return (False, f"Modified XML is invalid: {e}")
        
        # Step 6: Create backup (GnuCash naming convention)
        backup_path = _create_backup(file_path, debug)
        if debug:
            print(f"DEBUG: Created backup at {backup_path}")
        
        # Step 7: Write modified file (preserve gzip format)
        if debug:
            print(f"DEBUG: Writing modified file...")
        
        if is_gzipped:
            with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                f.write(modified_xml)
        else:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(modified_xml)
        
        if debug:
            print("DEBUG: Write successful!")
        
        return (True, None)
        
    except Exception as e:
        import traceback
        error_msg = f"Error writing file: {e}\n{traceback.format_exc()}"
        return (False, error_msg)


def _find_first_changed_index(txn_list: AccountTransactionList) -> Optional[int]:
    """
    Find the index of the first transaction that changed position.
    
    We only need to update timestamps from this point onward, since
    GnuCash orders by date-entered and earlier transactions are unaffected.
    
    Returns None if no transactions changed position.
    """
    for idx, txn in enumerate(txn_list.transactions):
        if txn.original_index != idx:
            return idx
    return None


def _create_backup(file_path: Path, debug: bool = False) -> Path:
    """
    Create a timestamped backup of the file using GnuCash naming convention.
    Format: originalfile.gnucash.YYYYMMDDHHMMSS.gnucash
    """
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    backup_path = file_path.parent / f"{file_path.name}.{timestamp}.gnucash"
    
    shutil.copy2(file_path, backup_path)
    return backup_path


def _update_timestamps_in_xml(xml_content: str, timestamp_updates: dict, 
                               debug: bool = False) -> str:
    """
    Update transaction date-entered timestamps in XML content.
    
    Uses regex to find and replace <trn:date-entered> timestamps for
    specific transaction IDs. This preserves all XML formatting and structure.
    
    Args:
        xml_content: The XML file content as string
        timestamp_updates: Dict mapping transaction_id to new datetime
        debug: Enable debug output
    
    Returns:
        Modified XML content with updated timestamps
    """
    modified_xml = xml_content
    
    for txn_id, new_timestamp in timestamp_updates.items():
        # Format timestamp for GnuCash: "YYYY-MM-DD HH:MM:SS +0000"
        timestamp_str = new_timestamp.strftime('%Y-%m-%d %H:%M:%S +0000')
        
        # Find the transaction block with this ID
        # Pattern matches entire transaction element, finding the one with matching ID
        pattern = rf'(<gnc:transaction version="2\.0\.0">)((?:(?!<gnc:transaction).)*?<trn:id type="guid">{re.escape(txn_id)}</trn:id>.*?)(</gnc:transaction>)'
        
        match = re.search(pattern, modified_xml, re.DOTALL)
        if not match:
            if debug:
                print(f"DEBUG: Warning - could not find transaction {txn_id[:8]}...")
            continue
        
        txn_start = match.group(1)
        txn_middle = match.group(2)
        txn_end = match.group(3)
        
        # Find and replace the date-entered timestamp within this transaction
        date_entered_pattern = r'(<trn:date-entered>\s*<ts:date>)([^<]+)(</ts:date>\s*</trn:date-entered>)'
        
        def replace_timestamp(m):
            return m.group(1) + timestamp_str + m.group(3)
        
        new_txn_middle = re.sub(date_entered_pattern, replace_timestamp, txn_middle)
        
        # Verify we actually replaced something
        if new_txn_middle == txn_middle:
            if debug:
                print(f"DEBUG: Warning - no date-entered found for transaction {txn_id[:8]}...")
            continue
        
        # Replace the transaction block in the XML
        new_txn_block = txn_start + new_txn_middle + txn_end
        modified_xml = modified_xml.replace(match.group(0), new_txn_block, 1)
    
    return modified_xml


# ============================================================================
# CONFIGURATION MANAGER
# ============================================================================

class Config:
    """Manages application configuration with automatic persistence"""
    
    # Default configuration values (used for new installs and resets)
    DEFAULT_CONFIG = {
        'last_file': '',
        'last_account_guid': '',
        'last_date': '',  # Format: YYYY-MM-DD
        'window_geometry': {
            'width': 1200,
            'height': 700,
            'x': None,  # None means center on screen
            'y': None
        },
        'column_widths': {
            'description': 250,
            'transfer': 250,
            'debit': 100,
            'credit': 100,
            'balance': 120
        }
    }
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize config manager and load saved configuration.
        
        Args:
            config_path: Path to config file. If None, uses default location
                        (~/.gnucash_transaction_sorter.json)
        """
        if config_path is None:
            # Default location in user's home directory
            home = Path.home()
            self.config_path = home / '.gnucash_transaction_sorter.json'
        else:
            self.config_path = Path(config_path)
        
        # Start with defaults, then merge in saved values
        self.config = self.DEFAULT_CONFIG.copy()
        self._load()
    
    def _load(self):
        """Load configuration from file, merging with defaults"""
        if not self.config_path.exists():
            # Config file doesn't exist yet - use defaults
            return
        
        try:
            with open(self.config_path, 'r') as f:
                loaded_config = json.load(f)
            
            # Merge loaded config with defaults (handles schema changes)
            self._merge_config(loaded_config)
            
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load config from {self.config_path}: {e}")
            print("Using default configuration")
    
    def _merge_config(self, loaded_config: Dict[str, Any]):
        """
        Merge loaded config with defaults, preserving structure.
        This ensures new config keys are added even if the saved config is old.
        """
        for key, value in self.DEFAULT_CONFIG.items():
            if key in loaded_config:
                if isinstance(value, dict):
                    # Merge nested dictionaries (e.g., window_geometry)
                    self.config[key] = {**value, **loaded_config[key]}
                else:
                    self.config[key] = loaded_config[key]
    
    def save(self):
        """Save configuration to file (auto-called by setters)"""
        try:
            # Create parent directory if it doesn't exist
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            
        except IOError as e:
            print(f"Warning: Could not save config to {self.config_path}: {e}")
    
    def reset_to_defaults(self):
        """Reset all configuration to default values"""
        self.config = self.DEFAULT_CONFIG.copy()
        self.save()
    
    def reset_geometry(self):
        """Reset only window geometry to defaults (keeps other settings)"""
        self.config['window_geometry'] = self.DEFAULT_CONFIG['window_geometry'].copy()
        self.save()
    
    # Convenience getters and setters (all setters auto-save)
    
    def get_last_file(self) -> str:
        """Get the last opened file path"""
        return self.config.get('last_file', '')
    
    def set_last_file(self, file_path: str):
        """Set the last opened file path and save"""
        self.config['last_file'] = file_path
        self.save()
    
    def get_last_account_guid(self) -> str:
        """Get the last selected account GUID"""
        return self.config.get('last_account_guid', '')
    
    def set_last_account_guid(self, guid: str):
        """Set the last selected account GUID and save"""
        self.config['last_account_guid'] = guid
        self.save()
    
    def get_last_date(self) -> str:
        """Get the last selected date (YYYY-MM-DD format)"""
        return self.config.get('last_date', '')
    
    def set_last_date(self, date_str: str):
        """Set the last selected date and save"""
        self.config['last_date'] = date_str
        self.save()
    
    def get_window_geometry(self) -> Dict[str, Optional[int]]:
        """Get window geometry dict (width, height, x, y)"""
        return self.config.get('window_geometry', self.DEFAULT_CONFIG['window_geometry']).copy()
    
    def set_window_geometry(self, width: int, height: int, x: int, y: int):
        """Set window geometry and save"""
        self.config['window_geometry'] = {
            'width': width,
            'height': height,
            'x': x,
            'y': y
        }
        self.save()
    
    def get_column_widths(self) -> Dict[str, int]:
        """Get column widths dict for transaction table"""
        return self.config.get('column_widths', self.DEFAULT_CONFIG['column_widths']).copy()
    
    def set_column_width(self, column: str, width: int):
        """Set width for a specific column and save"""
        if 'column_widths' not in self.config:
            self.config['column_widths'] = self.DEFAULT_CONFIG['column_widths'].copy()
        
        self.config['column_widths'][column] = width
        self.save()
    
    def is_geometry_valid(self, screen_width: int, screen_height: int) -> bool:
        """
        Check if saved window geometry is valid for current screen.
        Returns False if window would be completely off-screen.
        """
        geom = self.get_window_geometry()
        
        # If position is None, window will be centered - that's always valid
        if geom['x'] is None or geom['y'] is None:
            return True
        
        # Check if window would be completely off-screen
        x, y = geom['x'], geom['y']
        width, height = geom['width'], geom['height']
        
        # Window is off-screen if its entire area is outside screen bounds
        if x + width < 0 or x > screen_width:
            return False
        if y + height < 0 or y > screen_height:
            return False
        
        return True
    
    def __repr__(self):
        return f"Config(path='{self.config_path}')"


def parse_arguments():
    """
    Parse command-line arguments for the application.
    
    Supports:
    - --reset-geometry: Reset window size/position if it's off-screen
    - --reset-config: Reset entire configuration to defaults
    - --config-file: Use alternate config file location
    - --debug: Enable debug output
    """
    parser = argparse.ArgumentParser(
        description='GnuCash Transaction Sorter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Normal usage
  python gnucash_transaction_sorter.py
  
  # Reset window geometry if it's off-screen
  python gnucash_transaction_sorter.py --reset-geometry
  
  # Reset entire configuration
  python gnucash_transaction_sorter.py --reset-config
  
  # Enable debug output
  python gnucash_transaction_sorter.py --debug
        '''
    )
    
    parser.add_argument('--reset-geometry', action='store_true',
                        help='Reset window size and position to defaults')
    parser.add_argument('--reset-config', action='store_true',
                        help='Reset entire configuration to defaults')
    parser.add_argument('--config-file', type=str,
                        help='Use alternate config file location')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug output')
    
    return parser.parse_args()


# ============================================================================
# GUI UTILITIES
# ============================================================================

class ToolTip:
    """
    Simple tooltip implementation for tkinter widgets.
    
    Displays helpful text when user hovers over a widget.
    Automatically positions near the cursor.
    """
    
    def __init__(self, widget, text):
        """
        Create tooltip for a widget.
        
        Args:
            widget: The tkinter widget to attach tooltip to
            text: The tooltip text to display
        """
        self.widget = widget
        self.text = text
        self.tooltip = None
        
        # Bind hover events
        self.widget.bind("<Enter>", self.show)
        self.widget.bind("<Leave>", self.hide)
    
    def show(self, event=None):
        """Show the tooltip near the cursor"""
        if self.tooltip or not self.text:
            return
        
        # Calculate position near cursor
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        
        # Create tooltip window
        self.tooltip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)  # No window decorations
        tw.wm_geometry(f"+{x}+{y}")
        
        # Create label with tooltip text
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                        background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                        font=("TkDefaultFont", 9))
        label.pack()
    
    def hide(self, event=None):
        """Hide the tooltip"""
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None


class CustomDialog:
    """
    Custom modal dialog with configurable button labels.
    
    Used for dialogs that need more meaningful button text than
    the standard Yes/No/OK/Cancel options.
    """
    
    def __init__(self, parent, title: str, message: str, 
                 button1_text: str, button2_text: str, icon: str = 'info'):
        """
        Create custom dialog with two buttons.
        
        Args:
            parent: Parent window
            title: Dialog title
            message: Dialog message text
            button1_text: Text for first button (default action)
            button2_text: Text for second button
            icon: Icon type ('info', 'warning', 'error', 'question')
        """
        self.result = None
        
        # Create modal dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Main frame
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Icon and message frame
        msg_frame = ttk.Frame(main_frame)
        msg_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        # Icon (use tkinter's built-in bitmaps - cross-platform safe)
        try:
            icon_bitmap = self._get_icon_bitmap(icon)
            icon_label = tk.Label(msg_frame, bitmap=icon_bitmap)
            icon_label.pack(side=tk.LEFT, padx=(0, 15))
        except tk.TclError:
            # Fallback if bitmap not available - use text
            icon_text = self._get_icon_text(icon)
            icon_label = ttk.Label(msg_frame, text=icon_text, 
                                  font=('TkDefaultFont', 24, 'bold'))
            icon_label.pack(side=tk.LEFT, padx=(0, 15))
        
        # Message
        msg_label = ttk.Label(msg_frame, text=message, wraplength=300)
        msg_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        # Buttons (right to left: button2, button1)
        ttk.Button(button_frame, text=button2_text, 
                  command=lambda: self._on_button_click(2)).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text=button1_text, 
                  command=lambda: self._on_button_click(1)).pack(side=tk.RIGHT)
        
        # Center on parent
        self._center_on_parent(parent)
        
        # Bind Enter key to button1 (default action)
        self.dialog.bind('<Return>', lambda e: self._on_button_click(1))
        
        # Bind Escape key to button2
        self.dialog.bind('<Escape>', lambda e: self._on_button_click(2))
    
    def _get_icon_bitmap(self, icon: str) -> str:
        """Get tkinter built-in bitmap name for icon type (cross-platform)"""
        icons = {
            'info': 'info',
            'warning': 'warning',
            'error': 'error',
            'question': 'question'
        }
        return icons.get(icon, 'info')
    
    def _get_icon_text(self, icon: str) -> str:
        """Get text fallback for icon (if bitmaps not available)"""
        icons = {
            'info': '(i)',
            'warning': '(!)',
            'error': '(X)',
            'question': '(?)'
        }
        return icons.get(icon, '(i)')
    
    def _on_button_click(self, button_num: int):
        """Handle button click"""
        self.result = button_num
        self.dialog.destroy()
    
    def _center_on_parent(self, parent):
        """Center dialog on parent window"""
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")
    
    def show(self) -> int:
        """
        Show dialog and return result.
        
        Returns:
            1 if button1 clicked, 2 if button2 clicked
        """
        self.dialog.wait_window()
        return self.result if self.result else 1  # Default to button1


class StateManager:
    """
    Manages application state and UI updates for the main GUI.
    
    This class is given references to the GUI's widgets and methods,
    allowing it to handle state-related logic independently.
    """
    
    def __init__(self, gui_ref):
        """
        Initialize state manager with reference to main GUI.
        
        Args:
            gui_ref: Reference to TransactionSorterGUI instance
        """
        self.gui = gui_ref
    
    def check_unsaved_changes(self) -> bool:
        """
        Check for unsaved changes before changing context.
        Prompts user to save, revert, or cancel the operation.
        
        Returns:
            True if OK to proceed (saved or reverted)
            False if user cancelled
        """
        if not self.gui.txn_table.has_changes():
            return True
        
        # Show dialog with Yes/No/Cancel options
        result = messagebox.askyesnocancel(
            "Unsaved Changes",
            "You have unsaved changes. Do you want to save before switching?"
        )
        
        if result is None:  # Cancel
            return False
        elif result:  # Yes - save changes
            self.gui._commit_changes()
            # Check if save was successful
            return not self.gui.txn_table.has_changes()
        else:  # No - revert changes
            self.gui.txn_table.revert()
            self.update_button_states()
            return True
    
    def update_button_states(self):
        """
        Update enabled/disabled state of all buttons based on current state.
        
        Updates:
        - Revert/Commit buttons (enabled if changes exist)
        - Changes label (shows warning if unsaved changes)
        - Up/Down buttons (enabled based on selection position)
        """
        has_changes = self.gui.txn_table.has_changes()
        
        # Revert and Commit buttons
        state = 'normal' if has_changes else 'disabled'
        self.gui.revert_button.config(state=state)
        self.gui.commit_button.config(state=state)
        
        # Changes warning label
        if has_changes:
            self.gui.changes_label.config(text="● Unsaved changes")
        else:
            self.gui.changes_label.config(text="")
        
        # Up/Down buttons (based on selection)
        selected_row = self.gui.txn_table.get_selected_row()
        txn_count = self.gui.txn_table.get_transaction_count()
        
        if selected_row is not None and txn_count > 0:
            # Up enabled if not at top
            self.gui.up_button.config(state='normal' if selected_row > 0 else 'disabled')
            # Down enabled if not at bottom
            self.gui.down_button.config(state='normal' if selected_row < txn_count - 1 else 'disabled')
        else:
            # No selection - disable both
            self.gui.up_button.config(state='disabled')
            self.gui.down_button.config(state='disabled')
    
    def auto_load(self):
        """
        Auto-load last file and selections on startup.
        Only loads if the file exists and is accessible.
        """
        last_file = self.gui.config.get_last_file()
        if last_file and Path(last_file).exists():
            self.gui.file_entry.insert(0, last_file)
            self.gui._load_file()
    
    def restore_last_account(self):
        """
        Try to restore last selected account, or select first usable account.
        
        Preference order:
        1. Last selected account (if it exists and has sortable dates)
        2. First account with sortable dates
        """
        last_guid = self.gui.config.get_last_account_guid()
        
        # Try to restore last account
        if last_guid and self.gui.gc_file and last_guid in self.gui.gc_file.accounts:
            account = self.gui.gc_file.get_account(last_guid)
            if account and account.has_transactions():
                self.gui._set_current_account(account)
                self.gui._load_dates_for_account()
                return
        
        # Otherwise, find first account with transactions
        self.select_first_account_with_transactions()
    
    def select_first_account_with_transactions(self):
        """
        Find and select the first account that has sortable dates.
        Useful when no last account is saved or the saved account is invalid.
        """
        if not self.gui.gc_file:
            return
        
        for account in self.gui.gc_file.accounts.values():
            if account.has_transactions() and self.gui.gc_file.has_sortable_dates(account.guid):
                self.gui._set_current_account(account)
                self.gui._load_dates_for_account()
                return
    
    def release_lock(self):
        """
        Release the lock file if we have one.
        Lock files prevent multiple instances from editing the same GnuCash file.
        """
        if self.gui.lock_file and self.gui.lock_file.exists():
            try:
                self.gui.lock_file.unlink()
                if DEBUG:
                    print(f"DEBUG: Removed lock file: {self.gui.lock_file}")
            except Exception as e:
                if DEBUG:
                    print(f"DEBUG: Error removing lock file: {e}")
            finally:
                self.gui.lock_file = None


# ============================================================================
# DATE SELECTOR WIDGET
# ============================================================================

class DateSelector:
    """Widget for selecting dates with cascading dropdowns and navigation"""
    
    def __init__(self, parent, on_date_changed: Callable[[str], None], debug: bool = False):
        """
        Initialize date selector widget.
        
        Args:
            parent: Parent tkinter frame
            on_date_changed: Callback function called when date changes
                            Receives date string in YYYY-MM-DD format
            debug: Enable debug output
        """
        self.parent = parent
        self.on_date_changed = on_date_changed
        self.debug = debug
        
        # State variables
        self.gc_file: Optional[GnuCashFile] = None
        self.account_guid: str = ""
        self.current_date: str = ""
        self.available_dates: List[str] = []  # Sorted list of YYYY-MM-DD strings
        
        # Create UI widgets
        self._create_widgets()
    
    def _create_widgets(self):
        """Create date selection widgets (label, dropdowns, navigation buttons)"""
        # Date label
        ttk.Label(self.parent, text="Date:").pack(side=tk.LEFT, padx=(20, 5))
        
        # Year dropdown
        self.year_var = tk.StringVar()
        self.year_combo = ttk.Combobox(self.parent, textvariable=self.year_var,
                                       width=8, state='disabled')
        self.year_combo.pack(side=tk.LEFT, padx=2)
        self.year_combo.bind('<<ComboboxSelected>>', self._on_year_selected)
        
        # Month dropdown
        self.month_var = tk.StringVar()
        self.month_combo = ttk.Combobox(self.parent, textvariable=self.month_var,
                                        width=10, state='disabled')
        self.month_combo.pack(side=tk.LEFT, padx=2)
        self.month_combo.bind('<<ComboboxSelected>>', self._on_month_selected)
        
        # Day dropdown
        self.day_var = tk.StringVar()
        self.day_combo = ttk.Combobox(self.parent, textvariable=self.day_var,
                                      width=8, state='disabled')
        self.day_combo.pack(side=tk.LEFT, padx=2)
        self.day_combo.bind('<<ComboboxSelected>>', self._on_day_selected)
        
        # Navigation buttons
        self.prev_button = ttk.Button(self.parent, text="<", width=3,
                                      command=self._previous_date, state='disabled')
        self.prev_button.pack(side=tk.LEFT, padx=(10, 2))
        
        self.next_button = ttk.Button(self.parent, text=">", width=3,
                                      command=self._next_date, state='disabled')
        self.next_button.pack(side=tk.LEFT, padx=2)
    
    def set_account(self, account_guid: str, gc_file: GnuCashFile):
        """
        Set the account and load available dates.
        Only loads dates with 2+ transactions (sortable dates).
        
        Args:
            account_guid: Account GUID to load dates for
            gc_file: GnuCash file object
        """
        self.account_guid = account_guid
        self.gc_file = gc_file
        self.current_date = ""
        
        # Get dates with 2+ transactions (sortable dates only)
        self.available_dates = self.gc_file.get_transaction_dates_for_account(
            self.account_guid, min_transactions=2
        )
        
        if not self.available_dates:
            self._disable_all()
            return
        
        # Get hierarchical date structure for dropdowns
        date_structure = self.gc_file.get_year_month_day_structure(
            self.account_guid, min_transactions=2
        )
        
        # Populate year dropdown with available years
        years = sorted(date_structure.keys(), reverse=True)  # Most recent first
        self.year_combo['values'] = years
        self.year_combo.config(state='readonly')
        
        # Auto-select most recent year
        if years:
            self.year_var.set(years[0])
            self._on_year_selected()
    
    def set_date(self, date_str: str):
        """
        Set the date from a YYYY-MM-DD string (programmatic selection).
        Used when restoring last selected date from config.
        
        Args:
            date_str: Date in YYYY-MM-DD format
        """
        if date_str not in self.available_dates:
            if self.debug:
                print(f"DEBUG: Date {date_str} not in available dates")
            return
        
        year, month, day = date_str.split('-')
        
        # Set year (triggers month population)
        self.year_var.set(year)
        self._on_year_selected(trigger_callback=False)
        
        # Set month (triggers day population)
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        month_formatted = f"{month} ({month_names[int(month)-1]})"
        self.month_var.set(month_formatted)
        self._on_month_selected(trigger_callback=False)
        
        # Set day (triggers callback)
        self.day_var.set(day)
        self._on_day_selected(trigger_callback=True)
    
    def get_current_date(self) -> str:
        """Get the currently selected date (YYYY-MM-DD)"""
        return self.current_date
    
    def _disable_all(self):
        """Disable all date selection widgets (no dates available)"""
        self.year_combo.config(state='disabled')
        self.month_combo.config(state='disabled')
        self.day_combo.config(state='disabled')
        self.prev_button.config(state='disabled')
        self.next_button.config(state='disabled')
    
    def _on_year_selected(self, event=None, trigger_callback: bool = True):
        """Handle year selection → populate months"""
        year = self.year_var.get()
        if not year or not self.gc_file:
            return
        
        # Filter available_dates to get months in this year
        year_dates = [date for date in self.available_dates if date.startswith(year)]
        months = sorted(set(date.split('-')[1] for date in year_dates), reverse=True)
        
        # Format months as "MM (Name)"
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        formatted_months = [f"{m} ({month_names[int(m)-1]})" for m in months]
        
        self.month_combo['values'] = formatted_months
        self.month_combo.config(state='readonly')
        
        # Auto-select most recent month
        if formatted_months:
            self.month_var.set(formatted_months[0])
            self._on_month_selected(trigger_callback=trigger_callback)
    
    def _on_month_selected(self, event=None, trigger_callback: bool = True):
        """Handle month selection → populate days"""
        month_str = self.month_var.get()
        year = self.year_var.get()
        
        if not month_str or not year:
            return
        
        # Extract month number from "MM (Name)" format
        if ' ' in month_str:
            month = month_str.split(' ')[0]  # "01 (Jan)" -> "01"
        elif '-' in month_str:
            month = month_str.split('-')[0]  # "01-Jan" -> "01" (legacy fallback)
        else:
            month = month_str  # Just the number
        
        # Filter available_dates to get days in this year-month
        month_prefix = f"{year}-{month}"
        days_in_month = [date.split('-')[2] for date in self.available_dates
                        if date.startswith(month_prefix)]
        
        if not days_in_month:
            if self.debug:
                print(f"DEBUG: No valid days found for {month_prefix}")
            return
        
        self.day_combo['values'] = days_in_month
        self.day_combo.config(state='readonly')
        
        # Auto-select most recent day
        if days_in_month:
            self.day_var.set(days_in_month[0])
            self._on_day_selected(trigger_callback=trigger_callback)
    
    def _on_day_selected(self, event=None, trigger_callback: bool = True):
        """Handle day selection → update current_date and trigger callback"""
        day = self.day_var.get()
        month_str = self.month_var.get()
        year = self.year_var.get()
        
        if not day or not month_str or not year:
            if self.debug:
                print("DEBUG: Day selection incomplete")
            return
        
        # Extract month number from "MM (Name)" format
        if ' ' in month_str:
            month = month_str.split(' ')[0]
        elif '-' in month_str:
            month = month_str.split('-')[0]
        else:
            month = month_str
        
        # Build complete date string
        self.current_date = f"{year}-{month}-{day}"
        
        if self.debug:
            print(f"DEBUG: Selected date: {self.current_date}")
        
        # Update navigation button states
        self._update_navigation_buttons()
        
        # Trigger callback to load transactions
        if trigger_callback:
            self.on_date_changed(self.current_date)
    
    def _previous_date(self):
        """Navigate to previous date (chronologically earlier)"""
        if not self.current_date or not self.available_dates:
            return
        
        try:
            current_index = self.available_dates.index(self.current_date)
            # available_dates is sorted newest first, so next index is older
            if current_index < len(self.available_dates) - 1:
                new_date = self.available_dates[current_index + 1]
                self.set_date(new_date)
        except ValueError:
            pass
    
    def _next_date(self):
        """Navigate to next date (chronologically later)"""
        if not self.current_date or not self.available_dates:
            return
        
        try:
            current_index = self.available_dates.index(self.current_date)
            # available_dates is sorted newest first, so previous index is newer
            if current_index > 0:
                new_date = self.available_dates[current_index - 1]
                self.set_date(new_date)
        except ValueError:
            pass
    
    def _update_navigation_buttons(self):
        """Update state of previous/next date buttons based on position"""
        if not self.current_date or not self.available_dates:
            self.prev_button.config(state='disabled')
            self.next_button.config(state='disabled')
            return
        
        try:
            current_index = self.available_dates.index(self.current_date)
            
            # Previous button (go to older date)
            if current_index < len(self.available_dates) - 1:
                self.prev_button.config(state='normal')
            else:
                self.prev_button.config(state='disabled')
            
            # Next button (go to newer date)
            if current_index > 0:
                self.next_button.config(state='normal')
            else:
                self.next_button.config(state='disabled')
        except ValueError:
            self.prev_button.config(state='disabled')
            self.next_button.config(state='disabled')


# ============================================================================
# TRANSACTION TABLE WIDGET
# ============================================================================

class TransactionTable:
    """Widget for displaying and reordering transactions"""
    
    def __init__(self, parent, gc_file: GnuCashFile, config, 
                 on_selection_changed: Callable, 
                 on_changes_made: Callable,
                 debug: bool = False):
        """
        Initialize transaction table widget.
        
        Args:
            parent: Parent tkinter frame
            gc_file: GnuCash file object (for looking up account names)
            config: Config object for column widths
            on_selection_changed: Callback when selection changes
            on_changes_made: Callback when transactions are moved
            debug: Enable debug output
        """
        self.parent = parent
        self.gc_file = gc_file
        self.config = config
        self.on_selection_changed = on_selection_changed
        self.on_changes_made = on_changes_made
        self.debug = debug
        
        # State variables
        self.txn_list: Optional[AccountTransactionList] = None
        self.current_account_guid: str = ""
        self.selected_row: Optional[int] = None
        self.tooltip_window: Optional[tk.Toplevel] = None
        
        # Create UI widgets
        self._create_widgets()
    
    def _create_widgets(self):
        """Create table widgets (tree view with scrollbars)"""
        # Scrollbars
        y_scroll = ttk.Scrollbar(self.parent, orient=tk.VERTICAL)
        y_scroll.grid(row=0, column=1, sticky='ns')
        
        x_scroll = ttk.Scrollbar(self.parent, orient=tk.HORIZONTAL)
        x_scroll.grid(row=1, column=0, sticky='ew')
        
        # Transaction tree view
        columns = ('description', 'transfer', 'debit', 'credit', 'balance')
        self.tree = ttk.Treeview(self.parent, columns=columns, show='headings',
                                yscrollcommand=y_scroll.set,
                                xscrollcommand=x_scroll.set,
                                selectmode='browse')
        self.tree.grid(row=0, column=0, sticky='nsew')
        
        y_scroll.config(command=self.tree.yview)
        x_scroll.config(command=self.tree.xview)
        
        # Configure columns with saved widths
        col_widths = self.config.get_column_widths()
        
        self.tree.heading('description', text='Description')
        self.tree.column('description', width=col_widths.get('description', 250))
        
        self.tree.heading('transfer', text='Transfer')
        self.tree.column('transfer', width=col_widths.get('transfer', 250))
        
        self.tree.heading('debit', text='Debit')
        self.tree.column('debit', width=col_widths.get('debit', 100), anchor='e')
        
        self.tree.heading('credit', text='Credit')
        self.tree.column('credit', width=col_widths.get('credit', 100), anchor='e')
        
        self.tree.heading('balance', text='Balance')
        self.tree.column('balance', width=col_widths.get('balance', 120), anchor='e')
        
        # Configure tags for styling (adapt to light/dark mode)
        self._configure_tags()
        
        # Bind events
        self.tree.bind('<<TreeviewSelect>>', self._on_selection)
        self.tree.bind('<Motion>', self._show_tooltip)
        self.tree.bind('<Leave>', self._hide_tooltip)
    
    def _configure_tags(self):
        """Configure tree tags with appropriate colors for light/dark mode"""
        style = ttk.Style()
        bg_color = style.lookup('Treeview', 'background')
        
        # For moved items, use subtle highlight color
        if bg_color and bg_color.startswith('#'):
            bg_val = int(bg_color[1:], 16)
            if bg_val < 0x808080:  # Dark background
                moved_bg = '#3a3a2a'  # Slightly yellowish in dark mode
            else:  # Light background
                moved_bg = '#ffffcc'  # Yellow in light mode
        else:
            moved_bg = '#ffffcc'  # Fallback
        
        self.tree.tag_configure('moved', background=moved_bg)
    
    def load_transactions(self, txn_list: AccountTransactionList, account_guid: str):
        """
        Load transactions into the table.
        
        Args:
            txn_list: AccountTransactionList to display
            account_guid: GUID of the account (for looking up transfer accounts)
        """
        self.txn_list = txn_list
        self.current_account_guid = account_guid
        self.selected_row = None
        self.refresh()
    
    def refresh(self):
        """Refresh the table display (redraws all rows)"""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        if not self.txn_list:
            return
        
        # Calculate running balances
        balances = self.txn_list.calculate_balances()
        
        # Insert each transaction as a row
        for idx, (txn, balance) in enumerate(zip(self.txn_list.transactions, balances)):
            # Get debit and credit amounts for this account
            debit, credit = txn.get_debit_credit_for_account(self.current_account_guid)
            
            # Get transfer account name
            other_guid = txn.get_other_account_guid(self.current_account_guid)
            if other_guid and other_guid in self.gc_file.accounts:
                transfer = self.gc_file.accounts[other_guid].get_full_path(self.gc_file.accounts)
            elif txn.is_multi_split():
                transfer = "--Split Transaction--"
            else:
                transfer = "Unknown"
            
            # Format amounts (empty string if zero)
            debit_str = f"{debit:.2f}" if debit > 0 else ""
            credit_str = f"{credit:.2f}" if credit > 0 else ""
            balance_str = f"{balance:.2f}"
            
            # Determine styling tag
            tag = 'moved' if txn.moved else ''
            
            # Insert row
            self.tree.insert('', 'end',
                           values=(txn.description, transfer, debit_str, credit_str, balance_str),
                           tags=(tag,))
    
    def move_up(self) -> bool:
        """
        Move selected transaction up one position (earlier in the day).
        Returns True if moved, False if already at top.
        """
        if self.selected_row is None or not self.txn_list:
            return False
        
        if self.txn_list.move_transaction_up(self.selected_row):
            self.refresh()
            # Reselect the moved item (now at selected_row - 1)
            self.tree.selection_set(self.tree.get_children()[self.selected_row - 1])
            self.tree.see(self.tree.get_children()[self.selected_row - 1])
            self.selected_row -= 1
            self.on_changes_made()
            return True
        return False
    
    def move_down(self) -> bool:
        """
        Move selected transaction down one position (later in the day).
        Returns True if moved, False if already at bottom.
        """
        if self.selected_row is None or not self.txn_list:
            return False
        
        if self.txn_list.move_transaction_down(self.selected_row):
            self.refresh()
            # Reselect the moved item (now at selected_row + 1)
            self.tree.selection_set(self.tree.get_children()[self.selected_row + 1])
            self.tree.see(self.tree.get_children()[self.selected_row + 1])
            self.selected_row += 1
            self.on_changes_made()
            return True
        return False
    
    def revert(self):
        """Revert to original transaction order"""
        if not self.txn_list:
            return
        
        self.txn_list.revert_to_original_order()
        self.refresh()
    
    def has_changes(self) -> bool:
        """Check if there are unsaved changes"""
        return self.txn_list and self.txn_list.has_changes()
    
    def get_selected_row(self) -> Optional[int]:
        """Get the currently selected row index (0-based)"""
        return self.selected_row
    
    def get_transaction_count(self) -> int:
        """Get number of transactions in the table"""
        return len(self.txn_list.transactions) if self.txn_list else 0
    
    def _on_selection(self, event=None):
        """Handle selection change event"""
        selection = self.tree.selection()
        if selection:
            self.selected_row = self.tree.index(selection[0])
        else:
            self.selected_row = None
        
        self.on_selection_changed()
    
    def _show_tooltip(self, event):
        """Show tooltip for long text in description or transfer columns"""
        region = self.tree.identify_region(event.x, event.y)
        if region != 'cell':
            self._hide_tooltip()
            return
        
        column = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        
        # Only show tooltip for description (#1) and transfer (#2) columns
        if not row_id or column not in ('#1', '#2'):
            self._hide_tooltip()
            return
        
        values = self.tree.item(row_id, 'values')
        if not values:
            self._hide_tooltip()
            return
        
        col_index = int(column[1:]) - 1
        text = values[col_index] if col_index < len(values) else ""
        
        # Only show tooltip for long text
        if len(text) < 30:
            self._hide_tooltip()
            return
        
        # Create tooltip window
        if self.tooltip_window:
            self._hide_tooltip()
        
        x = event.x_root + 15
        y = event.y_root + 10
        
        self.tooltip_window = tw = tk.Toplevel(self.tree)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        # Use system colors
        style = ttk.Style()
        bg_color = style.lookup('Treeview', 'background')
        fg_color = style.lookup('Treeview', 'foreground')
        
        tooltip_bg = bg_color if bg_color else '#ffffe0'
        tooltip_fg = fg_color if fg_color else 'black'
        
        label = tk.Label(tw, text=text, justify=tk.LEFT,
                        background=tooltip_bg, foreground=tooltip_fg,
                        relief=tk.FLAT, borderwidth=0,
                        font=("TkDefaultFont", 9), wraplength=400, 
                        padx=15, pady=10,
                        highlightthickness=1, highlightbackground=tooltip_fg)
        label.pack()
    
    def _hide_tooltip(self, event=None):
        """Hide tooltip window"""
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


# ============================================================================
# ACCOUNT SELECTOR DIALOG
# ============================================================================

class AccountSelectorDialog:
    """Modal dialog for selecting an account from the tree"""
    
    def __init__(self, parent, gc_file: GnuCashFile, current_guid: str = ""):
        """
        Create account selector dialog.
        
        Args:
            parent: Parent window
            gc_file: GnuCashFile object with accounts loaded
            current_guid: Currently selected account GUID (optional)
        """
        self.result = None
        self.gc_file = gc_file
        self.current_guid = current_guid
        
        # Create modal dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Select Account")
        self.dialog.geometry("500x650")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Create UI components
        self._create_widgets()
        
        # Center dialog on parent
        self._center_on_parent(parent)
    
    def _create_widgets(self):
        """Create all dialog widgets"""
        # Main container
        main_frame = ttk.Frame(self.dialog, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Checkbox for showing hidden accounts
        self.show_hidden_var = tk.BooleanVar(value=False)
        checkbox_frame = ttk.Frame(main_frame)
        checkbox_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Checkbutton(checkbox_frame, text="Show hidden accounts",
                       variable=self.show_hidden_var,
                       command=self._refresh_tree).pack(side=tk.LEFT)
        
        # Create tree view with scrollbars
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        tree_scroll_y = ttk.Scrollbar(tree_frame)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.tree = ttk.Treeview(tree_frame,
                                 yscrollcommand=tree_scroll_y.set,
                                 xscrollcommand=tree_scroll_x.set,
                                 selectmode='browse')
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        tree_scroll_y.config(command=self.tree.yview)
        tree_scroll_x.config(command=self.tree.xview)
        
        # Configure tree tags for styling (adapt to light/dark mode)
        self._configure_tree_tags()
        
        # Build account tree
        self._build_tree()
        
        # Bind selection events
        self.tree.bind('<Double-Button-1>', self._on_select)
        self.tree.bind('<Return>', self._on_select)
        
        # Bottom buttons
        button_frame = ttk.Frame(self.dialog, padding=10)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Select", command=self._on_select).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self._on_cancel).pack(side=tk.RIGHT)
    
    def _configure_tree_tags(self):
        """Configure tree tags with appropriate colors for light/dark mode"""
        style = ttk.Style()
        fg_color = style.lookup('Treeview', 'foreground')
        
        # For accounts with no sortable dates, use appropriate gray
        if fg_color and fg_color.startswith('#'):
            fg_val = int(fg_color[1:], 16)
            if fg_val > 0x808080:  # Light foreground (dark mode)
                gray_color = '#808080'  # Medium gray for dark mode
            else:  # Dark foreground (light mode)
                gray_color = '#999999'  # Light gray for light mode
        else:
            gray_color = 'gray'  # Fallback
        
        self.tree.tag_configure('no_transactions', foreground=gray_color)
        # 'has_transactions' uses system default - don't configure it
    
    def _build_tree(self):
        """Build the account tree from GnuCash data"""
        if not self.gc_file.root_account:
            if DEBUG:
                print("DEBUG: No root account found!")
            return
        
        if DEBUG:
            print(f"DEBUG: Root account: {self.gc_file.root_account.name}")
            print(f"DEBUG: Root has {len(self.gc_file.root_account.children)} children")
        
        # Insert all top-level children (Assets, Liabilities, Income, Expenses, Equity)
        for child in self.gc_file.root_account.children:
            if DEBUG:
                print(f"DEBUG: Processing child: {child.name}, type: {child.account_type}")
            self._insert_account('', child, is_top_level=True)
    
    def _insert_account(self, parent_id, account: Account, is_top_level: bool = False):
        """
        Recursively insert account and its children into tree.
        
        Args:
            parent_id: Parent tree item ID (empty string for root)
            account: Account object to insert
            is_top_level: True if this is a top-level account (Assets, etc.)
        """
        # Skip hidden accounts if checkbox not checked
        show_hidden = self.show_hidden_var.get()
        if account.hidden and not show_hidden:
            return
        
        # Determine if account has transactions and sortable dates
        has_txns = account.has_transactions()
        has_sortable = has_txns and self.gc_file.has_sortable_dates(account.guid)
        
        # Create display name with [HIDDEN] tag if applicable
        display_name = account.name
        if account.hidden:
            display_name = f"[HIDDEN] {account.name}"
        
        # Determine styling tag
        tag = 'has_transactions' if has_sortable else 'no_transactions'
        
        # Insert account node
        # Store GUID and has_sortable flag in values for later retrieval
        account_id = self.tree.insert(parent_id, 'end', text=display_name,
                                     values=(account.guid, has_sortable),
                                     tags=(tag,), open=is_top_level)
        
        # Recursively insert children
        for child in account.children:
            self._insert_account(account_id, child, is_top_level=False)
    
    def _refresh_tree(self):
        """Refresh tree when show hidden checkbox changes (preserves state)"""
        # Save current state
        expanded_items = self._get_expanded_items()
        selected_item_path = self._get_selected_item_path()
        
        # Rebuild tree
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        self._build_tree()
        
        # Restore state
        self._restore_expanded_items(expanded_items)
        self._restore_selected_item(selected_item_path)
    
    def _get_item_path(self, item):
        """Get the path to an item as a list of account GUIDs"""
        path = []
        current = item
        while current:
            values = self.tree.item(current, 'values')
            if values:
                path.insert(0, values[0])  # GUID is first value
            current = self.tree.parent(current)
        return path
    
    def _get_expanded_items(self):
        """Get paths of all expanded items (for state preservation)"""
        expanded = set()
        
        def collect_expanded(item):
            if self.tree.item(item, 'open'):
                path = tuple(self._get_item_path(item))
                if path:
                    expanded.add(path)
            for child in self.tree.get_children(item):
                collect_expanded(child)
        
        for item in self.tree.get_children():
            collect_expanded(item)
        
        return expanded
    
    def _get_selected_item_path(self):
        """Get the path of the currently selected item"""
        selection = self.tree.selection()
        if selection:
            return tuple(self._get_item_path(selection[0]))
        return None
    
    def _find_item_by_path(self, path):
        """Find an item in the tree by its GUID path"""
        if not path:
            return None
        
        def search_children(parent, remaining_path):
            if not remaining_path:
                return parent
            
            target_guid = remaining_path[0]
            for child in self.tree.get_children(parent):
                values = self.tree.item(child, 'values')
                if values and values[0] == target_guid:
                    return search_children(child, remaining_path[1:])
            return None
        
        # Start from root items
        for root_item in self.tree.get_children():
            values = self.tree.item(root_item, 'values')
            if values and values[0] == path[0]:
                return search_children(root_item, path[1:])
        
        return None
    
    def _restore_expanded_items(self, expanded_paths):
        """Restore the expanded state of items"""
        for path in expanded_paths:
            item = self._find_item_by_path(path)
            if item:
                self.tree.item(item, open=True)
    
    def _restore_selected_item(self, selected_path):
        """Restore the selected item"""
        if selected_path:
            item = self._find_item_by_path(selected_path)
            if item:
                self.tree.selection_set(item)
                self.tree.see(item)
    
    def _on_select(self, event=None):
        """Handle account selection (double-click or button)"""
        selection = self.tree.selection()
        if selection:
            item = selection[0]
            values = self.tree.item(item, 'values')
            if values and len(values) >= 2:
                guid = values[0]
                has_sortable = values[1] == 'True'
                
                # Prevent selection of accounts with no sortable dates
                if not has_sortable:
                    messagebox.showwarning("No Sortable Dates",
                                          "This account has no dates with multiple transactions to sort.")
                    return
                
                self.result = guid
                self.dialog.destroy()
    
    def _on_cancel(self):
        """Handle cancel button"""
        self.result = None
        self.dialog.destroy()
    
    def _center_on_parent(self, parent):
        """Center dialog on parent window"""
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")
    
    def show(self):
        """Show dialog and return result (account GUID or None)"""
        self.dialog.wait_window()
        return self.result


# ============================================================================
# MAIN GUI
# ============================================================================

class TransactionSorterGUI:
    """Main GUI for GnuCash Transaction Sorter"""
    
    def __init__(self, root, config: Config):
        """
        Initialize the main GUI.
        
        Args:
            root: Tkinter root window
            config: Config object for persistent settings
        """
        self.root = root
        self.config = config
        self.gc_file: Optional[GnuCashFile] = None
        self.current_account_guid: str = ""
        self.lock_file: Optional[Path] = None  # Track .LCK file for file locking
        
        # Initialize state manager (handles state-related logic)
        self.state_manager = StateManager(self)
        
        # Set window title
        self.root.title("GnuCash Transaction Sorter")
        
        # Set window icon (if icon.png exists in same folder)
        icon_path = Path(__file__).parent / 'icon.png'
        if icon_path.exists():
            try:
                icon = tk.PhotoImage(file=icon_path)
                self.root.iconphoto(True, icon)
            except Exception:
                pass  # Silently ignore if icon can't be loaded
        
        # Apply saved geometry or defaults
        self._apply_window_geometry()
        
        # Make window resizable
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        
        # Create UI components
        self._create_widgets()
        
        # Bind window close event
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Auto-load last file if it exists
        self.state_manager.auto_load()
    
    def _apply_window_geometry(self):
        """Apply saved window geometry or center with defaults"""
        geom = self.config.get_window_geometry()
        width, height = geom['width'], geom['height']
        
        # Check if geometry is valid for current screen
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        if self.config.is_geometry_valid(screen_width, screen_height) and geom['x'] is not None:
            # Use saved position
            self.root.geometry(f"{width}x{height}+{geom['x']}+{geom['y']}")
        else:
            # Center on screen
            x = (screen_width - width) // 2
            y = (screen_height - height) // 2
            self.root.geometry(f"{width}x{height}+{x}+{y}")
    
    def _create_widgets(self):
        """Create all GUI widgets (main orchestrator)"""
        main_frame = ttk.Frame(self.root)
        main_frame.grid(row=0, column=0, sticky='nsew')
        main_frame.rowconfigure(2, weight=1)  # Transaction area expands
        main_frame.columnconfigure(0, weight=1)
        
        # Create UI sections
        self._create_file_bar(main_frame)
        self._create_selection_bar(main_frame)
        self._create_transaction_area(main_frame)
        self._create_button_bar(main_frame)
        self._create_status_bar(main_frame)
    
    def _create_file_bar(self, parent):
        """Create file selection bar at top"""
        file_frame = ttk.Frame(parent, padding=5)
        file_frame.grid(row=0, column=0, sticky='ew')
        file_frame.columnconfigure(1, weight=1)  # Entry expands
        
        ttk.Label(file_frame, text="GnuCash File:").grid(row=0, column=0, padx=5)
        
        # File entry (clickable to browse)
        self.file_entry = ttk.Entry(file_frame, cursor='hand2')
        self.file_entry.grid(row=0, column=1, sticky='ew', padx=5)
        self.file_entry.bind('<Button-1>', lambda e: self._browse_file())
        
        ttk.Button(file_frame, text="Browse", width=10,
                  command=self._browse_file).grid(row=0, column=2, padx=5)
    
    def _create_selection_bar(self, parent):
        """Create account and date selection bar"""
        sel_frame = ttk.Frame(parent, padding=5)
        sel_frame.grid(row=1, column=0, sticky='ew')
        sel_frame.columnconfigure(1, weight=1)  # Account entry expands
        
        # Account selection
        ttk.Label(sel_frame, text="Account:").grid(row=0, column=0, sticky='w', padx=5)
        
        self.account_entry = ttk.Entry(sel_frame, width=50, state='readonly', cursor='hand2')
        self.account_entry.grid(row=0, column=1, sticky='ew', padx=5)
        self.account_entry.bind('<Button-1>', lambda e: self._select_account())
        
        self.account_button = ttk.Button(sel_frame, text="Select", width=10,
                                        command=self._select_account, state='disabled')
        self.account_button.grid(row=0, column=2, padx=5)
        
        # Date selection (cascading dropdowns)
        date_frame = ttk.Frame(sel_frame)
        date_frame.grid(row=1, column=0, columnspan=3, sticky='w', pady=(5, 0))
        
        self.date_selector = DateSelector(date_frame, self._on_date_changed, DEBUG)
    
    def _create_transaction_area(self, parent):
        """Create transaction table and reorder buttons"""
        txn_frame = ttk.Frame(parent, padding=5)
        txn_frame.grid(row=2, column=0, sticky='nsew')
        txn_frame.rowconfigure(0, weight=1)
        txn_frame.columnconfigure(0, weight=1)
        
        # Transaction table container
        table_frame = ttk.Frame(txn_frame)
        table_frame.grid(row=0, column=0, sticky='nsew')
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        
        # Create transaction table
        self.txn_table = TransactionTable(
            table_frame, 
            None,  # gc_file will be set when file is loaded
            self.config,
            self._on_transaction_selection_changed,
            self.state_manager.update_button_states,
            DEBUG
        )
        
        # Reorder buttons (Up/Down)
        button_frame = ttk.Frame(txn_frame)
        button_frame.grid(row=0, column=1, sticky='ns', padx=(5, 0))
        button_frame.rowconfigure(0, weight=1)  # Top spacer
        button_frame.rowconfigure(3, weight=1)  # Bottom spacer
        
        self.up_button = ttk.Button(button_frame, text="↑ Up", 
                                    command=self._move_up, state='disabled', width=8)
        self.up_button.grid(row=1, column=0, pady=5)
        
        self.down_button = ttk.Button(button_frame, text="↓ Down", 
                                      command=self._move_down, state='disabled', width=8)
        self.down_button.grid(row=2, column=0, pady=5)
    
    def _create_button_bar(self, parent):
        """Create bottom button bar with Revert and Commit buttons"""
        button_frame = ttk.Frame(parent, padding=5)
        button_frame.grid(row=3, column=0, sticky='ew')
        
        # Right-aligned buttons
        self.commit_button = ttk.Button(button_frame, text="Commit Changes", 
                                       command=self._commit_changes, state='disabled')
        self.commit_button.pack(side=tk.RIGHT, padx=5)
        
        self.revert_button = ttk.Button(button_frame, text="Revert", 
                                       command=self._revert_changes, state='disabled')
        self.revert_button.pack(side=tk.RIGHT, padx=5)
        
        # Changes indicator label
        self.changes_label = ttk.Label(button_frame, text="", foreground='orange')
        self.changes_label.pack(side=tk.RIGHT, padx=20)
    
    def _create_status_bar(self, parent):
        """Create status bar at bottom"""
        self.status_var = tk.StringVar(value="No file loaded")
        status_bar = ttk.Label(parent, textvariable=self.status_var, 
                              relief=tk.SUNKEN, anchor=tk.W, padding=(5, 2))
        status_bar.grid(row=4, column=0, sticky='ew')
    
    # ========== EVENT HANDLERS ==========
    
    def _browse_file(self):
        """Open file browser to select GnuCash file"""
        # Check for unsaved changes before switching files
        if not self.state_manager.check_unsaved_changes():
            return
        
        filename = filedialog.askopenfilename(
            title="Select GnuCash File",
            filetypes=[
                ("GnuCash Files", "*.gnucash *.gnc"),
                ("All Files", "*.*")
            ]
        )
        if filename:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, filename)
            self._load_file()
    
    def _load_file(self):
        """Load selected GnuCash file"""
        file_path = self.file_entry.get().strip()
        if not file_path:
            messagebox.showwarning("No File", "Please select a GnuCash file")
            return
        
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            messagebox.showerror("File Not Found", f"File not found: {file_path}")
            return
        
        # Check for existing lock file
        lock_file = Path(str(file_path_obj) + '.LCK')
        if lock_file.exists():
            messagebox.showerror("File Locked",
                               f"This file is already open in GnuCash or another application.\n\n"
                               f"Lock file exists: {lock_file.name}\n\n"
                               f"Please close the file in the other application before opening it here.")
            return
        
        try:
            self.status_var.set("Loading file...")
            self.root.update()
            
            # Release any existing lock
            self.state_manager.release_lock()
            
            # Create new lock file
            try:
                lock_file.touch()
                self.lock_file = lock_file
                if DEBUG:
                    print(f"DEBUG: Created lock file: {lock_file}")
            except Exception as e:
                messagebox.showerror("Lock Error",
                                   f"Could not create lock file:\n{e}\n\n"
                                   f"The file may be read-only or you may not have write permissions.")
                return
            
            # Load the GnuCash file
            self.gc_file = GnuCashFile(file_path)
            self.txn_table.gc_file = self.gc_file
            self.config.set_last_file(file_path)
            
            self.status_var.set(f"Loaded {len(self.gc_file.accounts)} accounts, "
                               f"{len(self.gc_file.transactions)} transactions")
            
            # Enable account selection
            self.account_button.config(state='normal')
            
            # Try to restore last account or select first usable one
            self.state_manager.restore_last_account()
            
        except Exception as e:
            self.state_manager.release_lock()  # Release lock if loading failed
            messagebox.showerror("Error", f"Error loading file: {e}")
            self.status_var.set("Error loading file")
    
    def _select_account(self):
        """Show account selection dialog"""
        if not self.gc_file:
            if DEBUG:
                print("DEBUG: No gc_file loaded!")
            return
        
        # Check for unsaved changes before switching accounts
        if not self.state_manager.check_unsaved_changes():
            return
        
        if DEBUG:
            print(f"DEBUG: Opening account selector")
        
        dialog = AccountSelectorDialog(self.root, self.gc_file, self.current_account_guid)
        result = dialog.show()
        
        if result:
            account = self.gc_file.get_account(result)
            if account:
                self._set_current_account(account)
                self.config.set_last_account_guid(result)
                self._load_dates_for_account()
    
    def _set_current_account(self, account: Account):
        """Set the current account and update UI"""
        self.current_account_guid = account.guid
        full_path = account.get_full_path(self.gc_file.accounts)
        
        # Update account entry
        self.account_entry.config(state='normal')
        self.account_entry.delete(0, tk.END)
        self.account_entry.insert(0, full_path)
        self.account_entry.config(state='readonly')
    
    def _load_dates_for_account(self):
        """Load available dates for selected account"""
        if not self.gc_file or not self.current_account_guid:
            return
        
        # Set account in date selector (populates dropdowns)
        self.date_selector.set_account(self.current_account_guid, self.gc_file)
        
        # Try to restore last selected date
        last_date = self.config.get_last_date()
        if last_date:
            self.date_selector.set_date(last_date)
    
    def _on_date_changed(self, date_str: str):
        """Handle date change from date selector"""
        # Check for unsaved changes before switching dates
        if not self.state_manager.check_unsaved_changes():
            # User cancelled - date selector will keep showing current date
            return
        
        if DEBUG:
            print(f"DEBUG: Date changed to {date_str}")
        
        self.config.set_last_date(date_str)
        self._load_transactions(date_str)
    
    def _load_transactions(self, date_str: str):
        """Load transactions for current account and date"""
        if not self.gc_file or not self.current_account_guid:
            return
        
        try:
            # Get transactions from GnuCash file
            txn_list = self.gc_file.get_transactions_for_account_and_date(
                self.current_account_guid, date_str
            )
            
            # Load into table
            self.txn_table.load_transactions(txn_list, self.current_account_guid)
            
            self.status_var.set(f"Loaded {self.txn_table.get_transaction_count()} "
                               f"transactions for {date_str}")
            
            self.state_manager.update_button_states()
            
        except Exception as e:
            if DEBUG:
                print(f"DEBUG: Error loading transactions: {e}")
                import traceback
                traceback.print_exc()
            messagebox.showerror("Error", f"Error loading transactions: {e}")
    
    def _on_transaction_selection_changed(self):
        """Handle transaction selection change"""
        self.state_manager.update_button_states()
    
    def _move_up(self):
        """Move selected transaction up (earlier in day)"""
        self.txn_table.move_up()
        self.state_manager.update_button_states()
    
    def _move_down(self):
        """Move selected transaction down (later in day)"""
        self.txn_table.move_down()
        self.state_manager.update_button_states()
    
    def _revert_changes(self):
        """Revert to original transaction order"""
        if messagebox.askyesno("Revert Changes", 
                              "Are you sure you want to revert all changes?"):
            self.txn_table.revert()
            self.status_var.set("Changes reverted")
            self.state_manager.update_button_states()
    
    def _commit_changes(self):
        """Commit changes to GnuCash file"""
        if not self.txn_table.has_changes():
            return
        
        if not self.gc_file:
            messagebox.showerror("Error", "No file loaded")
            return
        
        # Confirm with user
        num_changes = sum(1 for txn in self.txn_table.txn_list.transactions if txn.moved)
        if not messagebox.askyesno("Commit Changes",
                                   f"Save changes to {num_changes} transaction(s)?"):
            return
        
        # Write changes to file
        file_path = self.file_entry.get().strip()
        success, error = write_transaction_order(file_path, self.txn_table.txn_list, DEBUG)
        
        if success:
            # Clear moved flags (changes are now saved)
            for txn in self.txn_table.txn_list.transactions:
                txn.moved = False
                txn.original_index = self.txn_table.txn_list.transactions.index(txn)
            
            self.txn_table.refresh()
            self.state_manager.update_button_states()
            self.status_var.set("Changes saved successfully")
            
            # Show success dialog with Continue/Exit options
            result = CustomDialog(
                self.root,
                "Changes Saved",
                "Changes saved successfully!",
                "Continue",
                "Exit"
            ).show()
            
            # If user chose Exit (button 2), close the application
            if result == 2:
                self._on_close()
        else:
            messagebox.showerror("Error", f"Failed to save changes:\n\n{error}")
            self.status_var.set("Error saving changes")
    
    def _on_close(self):
        """Handle window close event"""
        # Save window geometry
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.config.set_window_geometry(width, height, x, y)
        
        # Check for unsaved changes
        if self.txn_table.has_changes():
            result = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before exiting?"
            )
            if result is None:  # Cancel
                return
            elif result:  # Yes - save
                self._commit_changes()
        
        # Release lock file
        self.state_manager.release_lock()
        
        self.root.destroy()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point"""
    global DEBUG
    
    # Parse command-line arguments
    args = parse_arguments()
    
    # Set debug flag
    DEBUG = getattr(args, 'debug', False)
    
    # Load or create config
    config = Config(args.config_file if hasattr(args, 'config_file') else None)
    
    # Handle reset flags
    if args.reset_config:
        print("Resetting configuration to defaults...")
        config.reset_to_defaults()
        print("Configuration reset complete.")
        return
    
    if args.reset_geometry:
        print("Resetting window geometry to defaults...")
        config.reset_geometry()
        print("Window geometry reset complete.")
    
    # Create and run GUI
    root = tk.Tk()
    app = TransactionSorterGUI(root, config)
    root.mainloop()


if __name__ == "__main__":
    main()