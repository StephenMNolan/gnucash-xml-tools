#!/usr/bin/env python3
"""
GnuCash Report Generator - Complete Single-File Version V7

TABLE OF CONTENTS:
==================
1. Utilities Module (gnucash_utils)
   - Date parsing with abbreviations (BPY, EPM, TODAY, etc.)
   - Period generation (monthly/quarterly ranges)
   - Value formatting and mathematical operations
   - GnuCash-specific parsing (dates, values)

2. XML Reader Module (gnucash_xml_reader)
   - GnuCash XML file parsing (gzipped and uncompressed)
   - Account hierarchy and metadata extraction
   - Transaction cache building (base and filtered)
   - Performance-optimized cache generation

3. Markup Parser Module (gnucash_markup_parser)
   - Report definition file parsing
   - Comment and escape sequence handling
   - Configuration validation and defaults
   - Report element structure building

4. Calculator Module (gnucash_calculator)
   - Account value calculation with filters
   - SUM row aggregation
   - CALC formula evaluation
   - Recursive subaccount handling

5. CSV Output Module (gnucash_csv_output)
   - Clean CSV generation for spreadsheets
   - Proper quoting and formatting
   - Auto-spacing logic
   - TOTAL and AVERAGE columns

6. Main Program (gnucash_report_generator)
   - Command-line argument parsing
   - Module orchestration
   - Debug and CSV output modes
   - Performance-optimized workflow
"""

import sys
import os
import argparse
import xml.etree.ElementTree as ET
import gzip
import re
from datetime import datetime, timedelta
import calendar
from decimal import Decimal
from collections import defaultdict


# ============================================================================
# MODULE 1: UTILITIES
# ============================================================================

"""
GnuCash Report Generator - Utilities Module V3

HIGH-LEVEL OVERVIEW:
This module contains shared utility functions used across the entire application.
These are general-purpose tools that don't belong to any specific domain:
- Date parsing (with abbreviations like BPY, EPM, TODAY, etc.)
- Period generation (converting date ranges into monthly/quarterly periods)
- Value formatting (displaying numbers with totals)
- Mathematical operations (applying *, /, +, - to value lists)

All functions are pure/stateless - they take inputs and return outputs with
no side effects. This makes them easy to test and reuse.
"""


def parse_date(date_str):
    """
    Parse date from string, supporting YYYY-MM-DD format or abbreviations.
    
    Supported abbreviations (case-insensitive):
        TODAY - Current date
        
        Beginning of periods:
        BPY - Beginning of Previous Year (Jan 1)
        BPQ - Beginning of Previous Quarter
        BPM - Beginning of Previous Month
        BY  - Beginning of current Year (Jan 1)
        BQ  - Beginning of current Quarter
        BM  - Beginning of current Month
        
        End of periods:
        EPY - End of Previous Year (Dec 31)
        EPQ - End of Previous Quarter
        EPM - End of Previous Month
        EY  - End of current Year (Dec 31)
        EQ  - End of current Quarter
        EM  - End of current Month
    
    Args:
        date_str: Date string in YYYY-MM-DD or abbreviation format
        
    Returns:
        datetime.date: Parsed date
        
    Raises:
        ValueError: If format is invalid
    """
    date_str = date_str.strip().upper()
    today = datetime.now().date()
    
    # Handle simple abbreviations
    if date_str == 'TODAY':
        return today
    
    # Beginning of Previous periods
    if date_str == 'BPY':
        return datetime(today.year - 1, 1, 1).date()
    
    if date_str == 'BPQ':
        current_quarter = (today.month - 1) // 3 + 1
        if current_quarter == 1:
            prev_quarter = 4
            year = today.year - 1
        else:
            prev_quarter = current_quarter - 1
            year = today.year
        month = (prev_quarter - 1) * 3 + 1
        return datetime(year, month, 1).date()
    
    if date_str == 'BPM':
        if today.month == 1:
            return datetime(today.year - 1, 12, 1).date()
        else:
            return datetime(today.year, today.month - 1, 1).date()
    
    # Beginning of current periods
    if date_str == 'BY':
        return datetime(today.year, 1, 1).date()
    
    if date_str == 'BQ':
        current_quarter = (today.month - 1) // 3 + 1
        month = (current_quarter - 1) * 3 + 1
        return datetime(today.year, month, 1).date()
    
    if date_str == 'BM':
        return datetime(today.year, today.month, 1).date()
    
    # End of Previous periods
    if date_str == 'EPY':
        return datetime(today.year - 1, 12, 31).date()
    
    if date_str == 'EPQ':
        current_quarter = (today.month - 1) // 3 + 1
        if current_quarter == 1:
            prev_quarter = 4
            year = today.year - 1
        else:
            prev_quarter = current_quarter - 1
            year = today.year
        month = prev_quarter * 3
        last_day = calendar.monthrange(year, month)[1]
        return datetime(year, month, last_day).date()
    
    if date_str == 'EPM':
        if today.month == 1:
            year = today.year - 1
            month = 12
        else:
            year = today.year
            month = today.month - 1
        last_day = calendar.monthrange(year, month)[1]
        return datetime(year, month, last_day).date()
    
    # End of current periods
    if date_str == 'EY':
        return datetime(today.year, 12, 31).date()
    
    if date_str == 'EQ':
        current_quarter = (today.month - 1) // 3 + 1
        month = current_quarter * 3
        last_day = calendar.monthrange(today.year, month)[1]
        return datetime(today.year, month, last_day).date()
    
    if date_str == 'EM':
        last_day = calendar.monthrange(today.year, today.month)[1]
        return datetime(today.year, today.month, last_day).date()
    
    # Try parsing as YYYY-MM-DD
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(
            f"Invalid date format: '{date_str}'. "
            f"Use YYYY-MM-DD or abbreviation (TODAY, BPY, EPY, BY, EY, etc.)"
        )


def get_period_ranges(start_date, end_date, period_type):
    """
    Generate list of (start, end) date tuples for each period.
    
    Args:
        start_date: First date to include (datetime.date)
        end_date: Last date to include (datetime.date)
        period_type: 'm' for monthly, 'q' for quarterly
        
    Returns:
        list: [(start_date, end_date), ...] for each period
        
    Example:
        Monthly from Jan to Mar 2025:
        [(2025-01-01, 2025-01-31), (2025-02-01, 2025-02-28), (2025-03-01, 2025-03-31)]
    """
    ranges = []
    current_date = start_date
    
    if period_type == 'm':
        # Monthly periods
        while current_date <= end_date:
            # First day of current month
            period_start = current_date.replace(day=1)
            
            # Last day of current month
            last_day = calendar.monthrange(current_date.year, current_date.month)[1]
            period_end = current_date.replace(day=last_day)
            
            # Clip to overall range
            period_start = max(period_start, start_date)
            period_end = min(period_end, end_date)
            
            ranges.append((period_start, period_end))
            
            # Move to next month
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
    
    elif period_type == 'q':
        # Quarterly periods
        while current_date <= end_date:
            # Determine which quarter we're in
            quarter = (current_date.month - 1) // 3 + 1
            
            # First month of quarter
            first_month = (quarter - 1) * 3 + 1
            period_start = current_date.replace(month=first_month, day=1)
            
            # Last month of quarter
            last_month = quarter * 3
            last_day = calendar.monthrange(current_date.year, last_month)[1]
            period_end = current_date.replace(month=last_month, day=last_day)
            
            # Clip to overall range
            period_start = max(period_start, start_date)
            period_end = min(period_end, end_date)
            
            ranges.append((period_start, period_end))
            
            # Move to next quarter
            if quarter == 4:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                next_month = last_month + 1
                current_date = current_date.replace(month=next_month)
    
    return ranges


def get_period_labels(start_date, end_date, period_type):
    """
    Generate human-readable labels for each period.
    
    Args:
        start_date: First date (datetime.date)
        end_date: Last date (datetime.date)
        period_type: 'm' for monthly, 'q' for quarterly
        
    Returns:
        list: ['Jan 2025', 'Feb 2025', ...] or ['1Q 2025', '2Q 2025', ...]
    """
    ranges = get_period_ranges(start_date, end_date, period_type)
    labels = []
    
    for period_start, period_end in ranges:
        if period_type == 'm':
            # Monthly: "Jan 2025"
            labels.append(period_start.strftime('%b %Y'))
        elif period_type == 'q':
            # Quarterly: "1Q 2025"
            quarter = (period_start.month - 1) // 3 + 1
            labels.append(f"{quarter}Q {period_start.year}")
    
    return labels


def format_values_with_total(values):
    """
    Format list of Decimal values with total for debug display.
    
    Args:
        values: List of Decimal values
        
    Returns:
        str: "1.00, 2.00, 3.00  | Total: 6.00"
    """
    values_str = ', '.join(f"{float(v):.2f}" for v in values)
    total = sum(values)
    return f"{values_str}  | Total: {float(total):.2f}"


def apply_operation(values, operation):
    """
    Apply mathematical operation to each value in list.
    
    Args:
        values: List of Decimal values
        operation: Tuple of (operator, operand) where:
            operator: '*', '/', '+', '-', '%'
            operand: Decimal value
            
    Returns:
        list: New list of Decimal values after operation
        
    Examples:
        apply_operation([100, 200], ('*', Decimal('0.9'))) -> [90, 180]
        apply_operation([100, 200], ('/', Decimal('12'))) -> [8.33, 16.67]
    """
    operator, operand = operation
    result = []
    
    for value in values:
        if operator == '*':
            new_value = value * operand
        elif operator == '/':
            new_value = value / operand if operand != 0 else Decimal('0')
        elif operator == '+':
            new_value = value + operand
        elif operator == '-':
            new_value = value - operand
        elif operator == '%':
            new_value = value * operand
        else:
            new_value = value
        
        # Round to 2 decimal places for financial data
        new_value = new_value.quantize(Decimal('0.01'))
        result.append(new_value)
    
    return result


def parse_gnucash_date(date_str):
    """
    Parse GnuCash's date format from XML.
    
    GnuCash stores dates in ISO 8601 format with timezone info, like:
    "2025-01-15 00:00:00 -0600"
    
    Args:
        date_str: Date string from GnuCash XML
        
    Returns:
        datetime.date: Parsed date (time and timezone ignored)
    """
    # Take just the date part (first 10 characters: YYYY-MM-DD)
    date_part = date_str[:10]
    return datetime.strptime(date_part, '%Y-%m-%d').date()


def parse_gnucash_value(value_str):
    """
    Parse GnuCash's value format from XML.
    
    GnuCash stores monetary values as fractions, like:
    "12345/100" means $123.45
    
    Args:
        value_str: Value string from GnuCash XML (format: "numerator/denominator")
        
    Returns:
        Decimal: Parsed monetary value with 2 decimal precision
    """
    parts = value_str.split('/')
    if len(parts) == 2:
        numerator = Decimal(parts[0])
        denominator = Decimal(parts[1])
        value = numerator / denominator
        # Round to 2 decimal places for financial data
        return value.quantize(Decimal('0.01'))
    else:
        return Decimal('0')


# ============================================================================
# MODULE 2: XML READER
# ============================================================================

"""
GnuCash Report Generator - XML Reader Module V3

HIGH-LEVEL OVERVIEW:
This module handles all interaction with GnuCash XML files. It reads the XML
(handling both gzipped and uncompressed formats), parses account information
(names, GUIDs, types, hierarchy), and builds transaction caches for fast lookups.

PERFORMANCE OPTIMIZATION:
Instead of building filtered caches on-demand (multiple passes through transactions),
we analyze the report definition upfront to identify all required filter/regex
combinations, then build all caches in a single optimized pass. This reduces
report generation time dramatically for complex reports with many filters.

All functions return simple data structures (dicts, lists, objects) with no
side effects, making them easy to test and reuse.
"""

# GnuCash XML namespaces - required for finding elements in the XML structure
NS = {
    'gnc': 'http://www.gnucash.org/XML/gnc',
    'act': 'http://www.gnucash.org/XML/act',
    'book': 'http://www.gnucash.org/XML/book',
    'slot': 'http://www.gnucash.org/XML/slot',
    'ts': 'http://www.gnucash.org/XML/ts',
    'trn': 'http://www.gnucash.org/XML/trn',
    'split': 'http://www.gnucash.org/XML/split'
}


class Account:
    """
    Represents a single GnuCash account with its metadata.
    
    Attributes:
        name: Display name of the account (e.g., "Checking")
        guid: Unique 32-character hex identifier
        parent_guid: GUID of parent account (None for root)
        account_type: GnuCash type (INCOME, EXPENSE, ASSET, LIABILITY, etc.)
    """
    def __init__(self, name, guid, parent_guid=None, account_type=None):
        self.name = name
        self.guid = guid
        self.parent_guid = parent_guid
        self.account_type = account_type


class CacheKey:
    """
    Represents a unique cache requirement for filtered transaction data.
    
    Used to identify distinct filter/regex combinations so we can build
    each cache exactly once, even if multiple report rows use the same filters.
    """
    def __init__(self, account_guid, filter_guid=None, regex_include=None, regex_exclude=None):
        self.account_guid = account_guid
        self.filter_guid = filter_guid
        # Convert lists to tuples for hashability
        self.regex_include = tuple(regex_include) if regex_include else None
        self.regex_exclude = tuple(regex_exclude) if regex_exclude else None
    
    def __eq__(self, other):
        if not isinstance(other, CacheKey):
            return False
        return (self.account_guid == other.account_guid and
                self.filter_guid == other.filter_guid and
                self.regex_include == other.regex_include and
                self.regex_exclude == other.regex_exclude)
    
    def __hash__(self):
        return hash((self.account_guid, self.filter_guid, 
                    self.regex_include, self.regex_exclude))
    
    def __repr__(self):
        parts = [f"account={self.account_guid[:8]}"]
        if self.filter_guid:
            parts.append(f"filter={self.filter_guid[:8]}")
        if self.regex_include:
            parts.append(f"include={self.regex_include}")
        if self.regex_exclude:
            parts.append(f"exclude={self.regex_exclude}")
        return f"CacheKey({', '.join(parts)})"


def parse_gnucash_file(filename):
    """
    Read and parse a GnuCash XML file, extracting all account information.
    
    Args:
        filename: Path to GnuCash file (.gnucash or .xml)
        
    Returns:
        tuple: (accounts_dict, tree) where:
            - accounts_dict: {guid_string: Account_object}
            - tree: ElementTree object for transaction processing
            
    Raises:
        FileNotFoundError: If file doesn't exist
        ET.ParseError: If XML is malformed
    """
    # Try gzipped format first (most common), fall back to plain XML
    try:
        with gzip.open(filename, 'rt', encoding='utf-8') as f:
            tree = ET.parse(f)
    except (gzip.BadGzipFile, OSError):
        with open(filename, 'r', encoding='utf-8') as f:
            tree = ET.parse(f)
    
    root = tree.getroot()
    accounts = {}
    
    # Find all account elements in the XML structure
    for account_elem in root.findall('.//gnc:account', NS):
        name_elem = account_elem.find('act:name', NS)
        name = name_elem.text if name_elem is not None else "Unknown"
        
        guid_elem = account_elem.find('act:id', NS)
        guid = guid_elem.text if guid_elem is not None else "no-guid"
        
        parent_elem = account_elem.find('act:parent', NS)
        parent_guid = parent_elem.text if parent_elem is not None else None
        
        type_elem = account_elem.find('act:type', NS)
        account_type = type_elem.text if type_elem is not None else None
        
        accounts[guid] = Account(name, guid, parent_guid, account_type)
    
    return accounts, tree


def get_account_path(account, accounts):
    """
    Build full account path by walking up the parent hierarchy.
    
    Args:
        account: Account object to build path for
        accounts: Dictionary of all accounts {guid: Account}
        
    Returns:
        str: Colon-separated path (e.g., "Assets:Bank:Checking")
    """
    path_parts = [account.name]
    current = account
    
    while current.parent_guid is not None:
        parent = accounts.get(current.parent_guid)
        if parent is None:
            break
        if parent.parent_guid is not None:
            path_parts.insert(0, parent.name)
        current = parent
    
    return ':'.join(path_parts)


def get_account_display_name(guid, accounts, name_format):
    """
    Get account display name according to format setting.
    
    Args:
        guid: Account GUID to look up
        accounts: Dictionary of all accounts
        name_format: Either 'full_path' or 'name_only'
        
    Returns:
        str: Formatted account name or error message if GUID not found
    """
    if guid not in accounts:
        return f"<UNKNOWN GUID: {guid}>"
    
    account = accounts[guid]
    
    if name_format == 'name_only':
        return account.name
    else:
        return get_account_path(account, accounts)


def identify_required_caches(elements):
    """
    Scan report elements to find all unique filter/regex combinations needed.
    
    This allows us to build all caches upfront in optimized passes rather than
    on-demand during calculation, significantly improving performance.
    
    Args:
        elements: List of ReportElement objects from parser
        
    Returns:
        set: Set of CacheKey objects representing unique cache requirements
    """
    required_caches = set()
    
    for elem in elements:
        if isinstance(elem, AccountElement):
            # Check if this account needs filtered/regex cache
            if elem.filter_guid or elem.regex_include or elem.regex_exclude:
                cache_key = CacheKey(
                    elem.guid,
                    elem.filter_guid,
                    elem.regex_include,
                    elem.regex_exclude
                )
                required_caches.add(cache_key)
    
    return required_caches


def build_transaction_cache(tree, period_ranges, account_guids):
    """
    Build a cache of transaction values organized by account and period.
    
    This is the base cache with no filters applied - just raw account totals.
    
    Args:
        tree: ElementTree object from parse_gnucash_file
        period_ranges: List of (start_date, end_date) tuples for each period
        account_guids: Set of account GUIDs we care about
        
    Returns:
        dict: {account_guid: {period_idx: Decimal_value}}
    """
    cache = defaultdict(lambda: defaultdict(lambda: Decimal('0')))
    
    root = tree.getroot()
    
    for trn_elem in root.findall('.//gnc:transaction', NS):
        date_posted_elem = trn_elem.find('.//trn:date-posted/ts:date', NS)
        if date_posted_elem is None:
            continue
        
        trn_date = parse_gnucash_date(date_posted_elem.text)
        
        period_idx = None
        for idx, (start, end) in enumerate(period_ranges):
            if start <= trn_date <= end:
                period_idx = idx
                break
        
        if period_idx is None:
            continue
        
        for split_elem in trn_elem.findall('.//trn:split', NS):
            split_account_elem = split_elem.find('split:account', NS)
            if split_account_elem is None:
                continue
            
            split_guid = split_account_elem.text
            
            if split_guid not in account_guids:
                continue
            
            value_elem = split_elem.find('split:value', NS)
            if value_elem is not None:
                value = parse_gnucash_value(value_elem.text)
                cache[split_guid][period_idx] += value
    
    return cache


def transaction_matches_regex(trn_elem, include_patterns, exclude_patterns):
    """
    Test if a transaction matches regex filter criteria.
    
    Args:
        trn_elem: Transaction XML element
        include_patterns: List of patterns that ALL must match (AND)
        exclude_patterns: List of patterns where NONE can match (NOT)
        
    Returns:
        bool: True if transaction passes all filters
    """
    desc_elem = trn_elem.find('trn:description', NS)
    description = desc_elem.text if desc_elem is not None else ""
    
    notes_elem = trn_elem.find('trn:notes', NS)
    notes = notes_elem.text if notes_elem is not None else ""
    
    search_text = f"{description} {notes}"
    
    if exclude_patterns:
        for pattern in exclude_patterns:
            if re.search(pattern, search_text, re.IGNORECASE):
                return False
    
    if include_patterns:
        for pattern in include_patterns:
            if not re.search(pattern, search_text, re.IGNORECASE):
                return False
    
    return True


def build_all_filtered_caches(tree, period_ranges, required_caches):
    """
    Build all filtered transaction caches in optimized passes.
    
    Instead of scanning transactions separately for each filter combination,
    we make intelligent passes through the data, building multiple caches
    simultaneously when possible.
    
    Args:
        tree: ElementTree from GnuCash file
        period_ranges: List of (start_date, end_date) tuples
        required_caches: Set of CacheKey objects to build
        
    Returns:
        dict: {CacheKey: {period_idx: Decimal_total}}
    """
    if not required_caches:
        return {}
    
    # Initialize storage for all caches
    filtered_caches = {}
    for cache_key in required_caches:
        filtered_caches[cache_key] = defaultdict(lambda: Decimal('0'))
    
    root = tree.getroot()
    
    # Single pass through all transactions, applying filters as we go
    for trn_elem in root.findall('.//gnc:transaction', NS):
        # Get transaction date
        date_posted_elem = trn_elem.find('.//trn:date-posted/ts:date', NS)
        if date_posted_elem is None:
            continue
        
        trn_date = parse_gnucash_date(date_posted_elem.text)
        
        # Find which period this belongs to
        period_idx = None
        for idx, (start, end) in enumerate(period_ranges):
            if start <= trn_date <= end:
                period_idx = idx
                break
        
        if period_idx is None:
            continue
        
        # Get all splits for this transaction (needed for filter checks)
        splits = list(trn_elem.findall('.//trn:split', NS))
        
        # Check each cache requirement to see if this transaction applies
        for cache_key in required_caches:
            # Check FILTER: transaction must touch the filter account
            if cache_key.filter_guid:
                has_filter_split = False
                for split_elem in splits:
                    split_account_elem = split_elem.find('split:account', NS)
                    if split_account_elem is not None and split_account_elem.text == cache_key.filter_guid:
                        has_filter_split = True
                        break
                
                if not has_filter_split:
                    continue
            
            # Check REGEX: transaction description/notes must match
            if cache_key.regex_include or cache_key.regex_exclude:
                include_list = list(cache_key.regex_include) if cache_key.regex_include else []
                exclude_list = list(cache_key.regex_exclude) if cache_key.regex_exclude else []
                
                if not transaction_matches_regex(trn_elem, include_list, exclude_list):
                    continue
            
            # Transaction passes all filters for this cache - add splits for target account
            for split_elem in splits:
                split_account_elem = split_elem.find('split:account', NS)
                if split_account_elem is None:
                    continue
                
                if split_account_elem.text != cache_key.account_guid:
                    continue
                
                value_elem = split_elem.find('split:value', NS)
                if value_elem is not None:
                    value = parse_gnucash_value(value_elem.text)
                    filtered_caches[cache_key][period_idx] += value
    
    return filtered_caches


# ============================================================================
# MODULE 3: MARKUP PARSER
# ============================================================================

r"""
GnuCash Report Generator - Markup Parser Module V8

HIGH-LEVEL OVERVIEW:
This module parses report definition files written in our custom markup language.
It reads the text file line by line, recognizing commands like SECTION:, ACCOUNT:,
FILTER:, REGEX:, etc., and builds a structured representation of the report.

The parser handles:
- Comment stripping (preserving escaped # characters)
- Escape sequence processing (\# becomes #, \\ becomes \)
- Configuration validation (dates, periods, required fields)
- Configuration defaults (BY/EY for dates, monthly periods, name_only display)
- Reference tracking ([1], [2], etc. for use in CALC formulas)
- Syntax validation (FILTER must follow ACCOUNT, etc.)

Output is a ReportConfig object and a list of ReportElement objects that
represent the report structure. This data is then processed by other modules
to generate actual values and output.
"""


class ReportConfig:
    """
    Configuration settings for a report.
    
    Attributes:
        start_date: First day to include in report (defaults to BY - beginning of year)
        end_date: Last day to include in report (defaults to EY - end of year)
        period: 'm' for monthly or 'q' for quarterly (default: 'm')
        account_name: 'full_path' or 'name_only' for account display (default: 'name_only')
        gnucash_file: Path to GnuCash file (optional, can override on command line)
        csv_file: Path to CSV output file (optional, defaults to input filename with .csv extension)
        invert_income: Boolean, whether to flip sign of INCOME accounts (default True)
    """
    def __init__(self):
        self.start_date = None
        self.end_date = None
        self.period = 'm'  # Default to monthly
        self.account_name = 'name_only'  # Default to name only
        self.gnucash_file = None
        self.csv_file = None
        self.invert_income = True  # Default to user-friendly positive income


class ReportElement:
    """
    Base class for all report elements.
    
    Attributes:
        line_num: Line number in source file (for error reporting)
        reference: Optional [n] reference number for use in CALC formulas
    """
    def __init__(self, line_num):
        self.line_num = line_num
        self.reference = None  # [n] reference if present


class SectionElement(ReportElement):
    """Section header (e.g., SECTION: Income & Deductions)"""
    def __init__(self, line_num, title):
        super().__init__(line_num)
        self.title = title


class TitleElement(ReportElement):
    """Title row showing period headers (e.g., TITLE: Gross Income)"""
    def __init__(self, line_num, text):
        super().__init__(line_num)
        self.text = text


class AccountElement(ReportElement):
    """
    Account data row with optional filters and operations.
    
    Attributes:
        guid: GnuCash account GUID (32 hex characters)
        label: Custom label or None (use account name from GnuCash)
        operation: Tuple of (operator, value) or None (e.g., ('*', Decimal('0.9')))
        recursive: Boolean, True if ACCOUNTS: (include subaccounts)
        filter_guid: GUID to filter transactions by, or None
        regex_include: List of regex patterns (all must match)
        regex_exclude: List of regex patterns (none can match)
    """
    def __init__(self, line_num, guid, label=None, operation=None, recursive=False):
        super().__init__(line_num)
        self.guid = guid
        self.label = label
        self.operation = operation
        self.recursive = recursive
        self.filter_guid = None
        self.regex_include = []
        self.regex_exclude = []


class PlaceholderElement(ReportElement):
    """
    Manually entered values (not from GnuCash).
    
    Attributes:
        description: Text label for the row
        values: List of Decimal values, one per period
    """
    def __init__(self, line_num, description, values):
        super().__init__(line_num)
        self.description = description
        self.values = values


class SumElement(ReportElement):
    """Sum of rows since last SUM/CALC/TITLE"""
    def __init__(self, line_num, description):
        super().__init__(line_num)
        self.description = description


class CalcElement(ReportElement):
    """
    Calculated row using formula with [n] references.
    
    Attributes:
        description: Text label for the row
        formula: String like "[1] - [2] - [3]" referencing other rows
    """
    def __init__(self, line_num, description, formula):
        super().__init__(line_num)
        self.description = description
        self.formula = formula


class BlankElement(ReportElement):
    """Blank row for spacing"""
    def __init__(self, line_num):
        super().__init__(line_num)


def process_escape_sequences(text):
    r"""
    Convert escape sequences to their literal characters.
    
    Args:
        text: String potentially containing \# or \\
        
    Returns:
        str: Text with escape sequences processed
        
    Recognized sequences:
        \# -> # (literal hash, not a comment)
        \\ -> \ (literal backslash)
    """
    result = []
    i = 0
    
    while i < len(text):
        # Check if this is start of escape sequence
        if text[i] == '\\' and i + 1 < len(text):
            next_char = text[i + 1]
            if next_char in ['#', '\\']:
                # Valid escape sequence - add the escaped character
                result.append(next_char)
                i += 2  # Skip both backslash and next char
            else:
                # Not a recognized escape - keep the backslash
                result.append(text[i])
                i += 1
        else:
            result.append(text[i])
            i += 1
    
    return ''.join(result)


def strip_comments(line):
    r"""
    Remove comments from line, preserving # inside quotes or after backslash.
    
    Args:
        line: Raw line from file
        
    Returns:
        str: Line with comments removed, whitespace stripped
        
    Logic:
        - Track whether we're inside quotes
        - Recognize \# as escaped (not a comment marker)
        - Stop at first unescaped, unquoted # character
    """
    # in_quotes: Boolean tracking if we're currently inside "quoted text"
    in_quotes = False
    result = []
    i = 0
    
    while i < len(line):
        char = line[i]
        
        # Check for escape sequence before processing the character
        if char == '\\' and i + 1 < len(line):
            next_char = line[i + 1]
            if next_char in ['#', '\\']:
                # This is \# or \\ - keep both characters for later processing
                result.append(char)
                result.append(next_char)
                i += 2
                continue
        
        # Track whether we're inside quotes
        if char == '"':
            in_quotes = not in_quotes
            result.append(char)
            i += 1
        elif char == '#' and not in_quotes:
            # Found unescaped comment outside quotes - stop here
            break
        else:
            result.append(char)
            i += 1
    
    return ''.join(result).strip()


def parse_operation(op_str):
    """
    Parse mathematical operation from string.
    
    Args:
        op_str: String like "* 90%" or "/ 12"
        
    Returns:
        tuple: (operator, operand) where operator is char and operand is Decimal
        None: If string doesn't match expected format
        
    Examples:
        "* 90%" -> ('*', Decimal('0.9'))
        "/ 12" -> ('/', Decimal('12'))
        "+ 100" -> ('+', Decimal('100'))
    """
    op_str = op_str.strip()
    
    # Match pattern: operator followed by optional whitespace and value
    # Operator: * / % + -
    match = re.match(r'^([*/%+-])\s*(.+)', op_str)
    if not match:
        return None
    
    operator = match.group(1)
    value_str = match.group(2).strip()
    
    # Handle percentage: "90%" becomes 0.9
    if value_str.endswith('%'):
        value = Decimal(value_str[:-1]) / 100
    else:
        value = Decimal(value_str)
    
    return (operator, value)


def parse_report_definition(filename):
    """
    Parse report definition markup file into structured data.
    
    Args:
        filename: Path to report definition text file
        
    Returns:
        tuple: (config, elements, references) where:
            - config: ReportConfig object with settings
            - elements: List of ReportElement objects (report structure)
            - references: Dict mapping [n] numbers to line numbers
            
    Raises:
        ValueError: For syntax errors, missing config, invalid values
        FileNotFoundError: If file doesn't exist
        
    Configuration Defaults:
        - START_DATE: BY (beginning of current year)
        - END_DATE: EY (end of current year)
        - PERIOD: m (monthly)
        - ACCOUNT_NAME: name_only
        - INVERT_INCOME: true
        
    Validation performed:
        - [n] references are unique
        - FILTER/REGEX follow ACCOUNT/ACCOUNTS
        - CALC formulas reference defined [n] values
    """
    config = ReportConfig()
    elements = []
    
    # references: Dict mapping reference number to line number where defined
    # Used to validate CALC formulas and detect duplicates
    references = {}
    
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    line_num = 0
    
    # last_account: Tracks most recent ACCOUNT/ACCOUNTS element
    # Needed because FILTER/REGEX must immediately follow an account
    last_account = None
    
    for line in lines:
        line_num += 1
        
        # Process line: strip comments, then process escape sequences
        # Order matters: \# must be preserved during comment stripping
        line = strip_comments(line)
        line = process_escape_sequences(line)
        line = line.strip()
        
        # Skip empty lines
        if not line:
            continue
        
        # Check for [n] reference prefix before command
        # current_reference: Integer reference number or None
        current_reference = None
        ref_match = re.match(r'^\[(\d+)\]\s+(.+)', line)
        if ref_match:
            current_reference = int(ref_match.group(1))
            line = ref_match.group(2)  # Remove [n] from line
            
            # Validate reference is unique
            if current_reference in references:
                raise ValueError(
                    f"Line {line_num}: Duplicate reference [{current_reference}] "
                    f"(already used on line {references[current_reference]})"
                )
        
        # Parse configuration lines (key: value format)
        # Must not start with known command keywords
        if ':' in line and not line.startswith((
            'SECTION:', 'TITLE:', 'ACCOUNT:', 'ACCOUNTS:', 
            'SUM:', 'CALC:', 'PLACEHOLDER:', 'BLANK:', 'FILTER:', 'REGEX:'
        )):
            key, value = line.split(':', 1)
            key = key.strip().upper()
            value = value.strip()
            
            if key == 'START_DATE':
                config.start_date = parse_date(value)
            elif key == 'END_DATE':
                config.end_date = parse_date(value)
            elif key == 'PERIOD':
                value = value.lower()  # Accept M, m, Q, q
                if value not in ['m', 'q']:
                    raise ValueError(f"Line {line_num}: PERIOD must be 'm' or 'q', got '{value}'")
                config.period = value
            elif key == 'ACCOUNT_NAME':
                value_lower = value.lower()  # Case-insensitive
                if value_lower not in ['full_path', 'name_only']:
                    raise ValueError(
                        f"Line {line_num}: ACCOUNT_NAME must be 'full_path' or 'name_only', got '{value}'"
                    )
                config.account_name = value_lower
            elif key == 'GNUCASH_FILE':
                config.gnucash_file = value
            elif key == 'CSV_FILE':
                config.csv_file = value
            elif key == 'INVERT_INCOME':
                value_lower = value.lower()  # Case-insensitive
                if value_lower in ['true', 'yes', '1']:
                    config.invert_income = True
                elif value_lower in ['false', 'no', '0']:
                    config.invert_income = False
                else:
                    raise ValueError(
                        f"Line {line_num}: INVERT_INCOME must be 'true' or 'false', got '{value}'"
                    )
            continue
        
        # Parse SECTION: header
        if line.startswith('SECTION:'):
            title = line[8:].strip()
            elem = SectionElement(line_num, title)
            elem.reference = current_reference
            if current_reference:
                references[current_reference] = line_num
            elements.append(elem)
            last_account = None  # FILTER/REGEX can't follow SECTION
            continue
        
        # Parse TITLE: row header
        if line.startswith('TITLE:'):
            text = line[6:].strip()
            elem = TitleElement(line_num, text)
            elem.reference = current_reference
            if current_reference:
                references[current_reference] = line_num
            elements.append(elem)
            last_account = None  # FILTER/REGEX can't follow TITLE
            continue
        
        # Parse ACCOUNT: or ACCOUNTS: (with subaccounts)
        if line.startswith('ACCOUNT:') or line.startswith('ACCOUNTS:'):
            # recursive: True if ACCOUNTS: (include subaccounts)
            recursive = line.startswith('ACCOUNTS:')
            content = line[9:].strip() if recursive else line[8:].strip()
            
            # Split on | to separate GUID+operation from optional label
            if '|' in content:
                parts = content.split('|', 1)
                guid_and_op = parts[0].strip()
                label = parts[1].strip()
            else:
                guid_and_op = content
                label = None
            
            # Check for mathematical operation in the GUID portion
            # operation: Tuple of (operator, value) or None
            operation = None
            guid = guid_and_op
            
            # Look for operators in the GUID string
            for op in ['*', '/', '+', '-', '%']:
                if op in guid_and_op:
                    parts = guid_and_op.split(op, 1)
                    guid = parts[0].strip()
                    operation = parse_operation(op + parts[1])
                    break
            
            elem = AccountElement(line_num, guid, label, operation, recursive)
            elem.reference = current_reference
            if current_reference:
                references[current_reference] = line_num
            elements.append(elem)
            last_account = elem  # Track for FILTER/REGEX
            continue
        
        # Parse FILTER: must follow ACCOUNT/ACCOUNTS
        if line.startswith('FILTER:'):
            if last_account is None:
                raise ValueError(f"Line {line_num}: FILTER must follow ACCOUNT or ACCOUNTS")
            
            guid = line[7:].strip()
            last_account.filter_guid = guid
            continue
        
        # Parse REGEX: must follow ACCOUNT/ACCOUNTS
        if line.startswith('REGEX:'):
            if last_account is None:
                raise ValueError(f"Line {line_num}: REGEX must follow ACCOUNT or ACCOUNTS")
            
            patterns = line[6:].strip()
            
            # Parse quoted patterns with optional - prefix for exclusion
            # Pattern format: "include" or -"exclude"
            # Can have multiple: "pattern1" "pattern2" -"exclude"
            pattern_regex = r'(-?)"([^"]+)"'
            for match in re.finditer(pattern_regex, patterns):
                is_exclude = match.group(1) == '-'
                pattern = match.group(2)
                
                if is_exclude:
                    last_account.regex_exclude.append(pattern)
                else:
                    last_account.regex_include.append(pattern)
            continue
        
        # Parse PLACEHOLDER: manual values
        if line.startswith('PLACEHOLDER:'):
            content = line[12:].strip()
            if '|' not in content:
                raise ValueError(
                    f"Line {line_num}: PLACEHOLDER requires format: "
                    "PLACEHOLDER: description | val1,val2,..."
                )
            
            description, values_str = content.split('|', 1)
            description = description.strip()
            
            # Parse comma-separated values
            values = [Decimal(v.strip()) for v in values_str.split(',')]
            
            elem = PlaceholderElement(line_num, description, values)
            elem.reference = current_reference
            if current_reference:
                references[current_reference] = line_num
            elements.append(elem)
            last_account = None
            continue
        
        # Parse SUM: sum rows since last SUM/CALC/TITLE
        if line.startswith('SUM:'):
            description = line[4:].strip()
            elem = SumElement(line_num, description)
            elem.reference = current_reference
            if current_reference:
                references[current_reference] = line_num
            elements.append(elem)
            last_account = None
            continue
        
        # Parse CALC: formula with [n] references
        if line.startswith('CALC:'):
            content = line[5:].strip()
            if '|' not in content:
                raise ValueError(
                    f"Line {line_num}: CALC requires format: CALC: description | formula"
                )
            
            description, formula = content.split('|', 1)
            description = description.strip()
            formula = formula.strip()
            
            # Validate that all [n] references in formula are defined
            # ref_pattern: Regex to find [1], [2], etc. in formula
            ref_pattern = r'\[(\d+)\]'
            for match in re.finditer(ref_pattern, formula):
                ref_num = int(match.group(1))
                if ref_num not in references:
                    raise ValueError(
                        f"Line {line_num}: Formula references undefined [{ref_num}]"
                    )
            
            elem = CalcElement(line_num, description, formula)
            elem.reference = current_reference
            if current_reference:
                references[current_reference] = line_num
            elements.append(elem)
            last_account = None
            continue
        
        # Parse BLANK: empty row
        if line.upper() == 'BLANK:':
            elem = BlankElement(line_num)
            elements.append(elem)
            last_account = None
            continue
        
        # If we got here, line doesn't match any known command
        raise ValueError(f"Line {line_num}: Unrecognized command: {line}")
    
    # Apply defaults for missing configuration fields
    if config.start_date is None:
        config.start_date = parse_date('BY')  # Default to beginning of current year
    if config.end_date is None:
        config.end_date = parse_date('EY')  # Default to end of current year
    # period and account_name already have defaults set in ReportConfig.__init__()
    
    # Validate PLACEHOLDER value counts match expected number of periods
    period_ranges = get_period_ranges(config.start_date, config.end_date, config.period)
    expected_periods = len(period_ranges)
    
    for elem in elements:
        if isinstance(elem, PlaceholderElement):
            if len(elem.values) != expected_periods:
                raise ValueError(
                    f"Line {elem.line_num}: PLACEHOLDER has {len(elem.values)} values "
                    f"but report has {expected_periods} periods. "
                    f"Expected format: value1,value2,...,value{expected_periods}"
                )
    
    return config, elements, references


# ============================================================================
# MODULE 4: CALCULATOR
# ============================================================================

"""
GnuCash Report Generator - Calculator Module V13

HIGH-LEVEL OVERVIEW:
This module takes the parsed report structure and GnuCash data and calculates
actual monetary values for each element. It handles:
- Retrieving raw account values from transaction cache
- Applying FILTER and REGEX using pre-built filtered caches
- Handling ACCOUNTS: (recursive subaccount aggregation)
- Applying mathematical operations (*, /, +, -, %)
- Calculating SUM rows (sum of previous rows)
- Evaluating CALC formulas with [n] references
- Storing calculated values for use by CALC formulas

PERFORMANCE OPTIMIZATION:
Uses pre-built filtered caches instead of building them on-demand, eliminating
redundant passes through transaction data.

All calculations use Decimal for precision (financial data must be exact).
"""


def get_descendant_guids(account_guid, accounts):
    """
    Find all descendant account GUIDs for a given account.
    
    Args:
        account_guid: Starting account GUID
        accounts: Dictionary of all accounts {guid: Account}
        
    Returns:
        list: All GUIDs including the starting account and all children/grandchildren/etc.
    """
    guids = [account_guid]
    
    def add_children(parent_guid):
        for acc_guid, account in accounts.items():
            if account.parent_guid == parent_guid:
                guids.append(acc_guid)
                add_children(acc_guid)
    
    add_children(account_guid)
    return guids


def calculate_account_values(elem, period_ranges, accounts, config, 
                            transaction_cache, filtered_caches):
    """
    Calculate period values for an AccountElement.
    
    This handles:
    - Raw account values (from base cache)
    - ACCOUNTS: recursive subaccount aggregation
    - FILTER: using pre-built filtered cache
    - REGEX: using pre-built filtered cache
    - Mathematical operations (* 90%, / 12, etc.)
    - Account type inversion (INCOME accounts flip sign if configured)
    - Invalid GUID detection
    
    Args:
        elem: AccountElement to calculate
        period_ranges: List of (start_date, end_date) tuples
        accounts: Dictionary of all accounts
        config: ReportConfig with settings
        transaction_cache: Pre-built base cache {account_guid: {period_idx: value}}
        filtered_caches: Pre-built filtered caches {CacheKey: {period_idx: value}}
        
    Returns:
        dict: {
            'raw': [Decimal, ...],           # Raw values before processing
            'filtered': [Decimal, ...],       # After FILTER (if present)
            'regex_filtered': [Decimal, ...], # After REGEX (if present)
            'final': [Decimal, ...],         # After all operations
            'valid': bool                     # True if GUID was found
        }
    """
    num_periods = len(period_ranges)
    result = {}
    
    # Check if the primary GUID is valid
    if elem.guid not in accounts:
        zero_values = [Decimal('0')] * num_periods
        result['raw'] = zero_values
        result['final'] = zero_values
        result['valid'] = False
        return result
    
    result['valid'] = True
    
    # Determine which account GUIDs to include
    if elem.recursive:
        target_guids = get_descendant_guids(elem.guid, accounts)
    else:
        target_guids = [elem.guid]
    
    # Calculate raw values (sum across all target accounts)
    raw_values = []
    for period_idx in range(num_periods):
        period_total = Decimal('0')
        for guid in target_guids:
            value = transaction_cache.get(guid, {}).get(period_idx, Decimal('0'))
            period_total += value
        raw_values.append(period_total)
    
    # Apply account type inversion if configured
    if config.invert_income and elem.guid in accounts:
        account = accounts[elem.guid]
        if account.account_type == 'INCOME':
            raw_values = [-v for v in raw_values]
    
    result['raw'] = raw_values
    working_values = raw_values
    
    # Apply FILTER and/or REGEX using pre-built caches
    if elem.filter_guid or elem.regex_include or elem.regex_exclude:
        # Build cache key for lookup
        cache_key = CacheKey(
            elem.guid,
            elem.filter_guid,
            elem.regex_include,
            elem.regex_exclude
        )
        
        # Look up pre-built filtered cache
        if cache_key in filtered_caches:
            filtered_values = []
            for period_idx in range(num_periods):
                value = filtered_caches[cache_key].get(period_idx, Decimal('0'))
                
                # Apply inversion to filtered values
                if config.invert_income and accounts[elem.guid].account_type == 'INCOME':
                    value = -value
                
                filtered_values.append(value)
            
            # Store in appropriate result key based on what filters were applied
            if elem.regex_include or elem.regex_exclude:
                result['regex_filtered'] = filtered_values
            elif elem.filter_guid:
                result['filtered'] = filtered_values
            
            working_values = filtered_values
    
    # Apply mathematical operation if specified
    if elem.operation:
        final_values = apply_operation(working_values, elem.operation)
        result['final'] = final_values
    else:
        result['final'] = working_values
    
    return result


def calculate_sum_values(elem, elements, stored_values, num_periods):
    """
    Calculate SUM row by adding up previous rows.
    
    Sum includes all ACCOUNT, PLACEHOLDER, SUM, and CALC rows since:
    - Last SUM
    - Last CALC
    - Last TITLE
    (whichever came most recently)
    
    Args:
        elem: SumElement to calculate
        elements: List of all report elements
        stored_values: Dict mapping element -> calculated values
        num_periods: Number of periods in report
        
    Returns:
        list: Decimal values, one per period
    """
    sum_values = [Decimal('0')] * num_periods
    
    elem_idx = elements.index(elem)
    
    for i in range(elem_idx - 1, -1, -1):
        prev_elem = elements[i]
        
        # Stop at boundaries (but don't include them in the sum)
        if isinstance(prev_elem, (TitleElement, SumElement, CalcElement)):
            break
        
        # Skip non-data elements
        if isinstance(prev_elem, (SectionElement, BlankElement)):
            continue
        
        # Sum AccountElements
        if isinstance(prev_elem, AccountElement):
            if prev_elem in stored_values:
                values = stored_values[prev_elem]['final']
                for period_idx in range(num_periods):
                    sum_values[period_idx] += values[period_idx]
        
        # Sum PlaceholderElements (values stored directly in element)
        elif isinstance(prev_elem, PlaceholderElement):
            values = prev_elem.values
            for period_idx in range(num_periods):
                sum_values[period_idx] += values[period_idx]
    
    return sum_values


def calculate_calc_values(elem, stored_values, references, elements, num_periods):
    """
    Evaluate CALC formula with [n] references.
    
    Process:
    1. Find all [n] references in formula
    2. Look up values for each referenced row
    3. Substitute values for each period
    4. Handle percentage signs (convert % to /100)
    5. Evaluate arithmetic expression
    
    Args:
        elem: CalcElement with formula like "[1] - [2] - [3]"
        stored_values: Dict mapping elements to calculated values
        references: Dict mapping [n] -> line_num
        elements: List of all report elements
        num_periods: Number of periods in report
        
    Returns:
        list: Decimal values, one per period
    """
    ref_pattern = r'\[(\d+)\]'
    ref_numbers = [int(m.group(1)) for m in re.finditer(ref_pattern, elem.formula)]
    
    ref_elements = {}
    for ref_num in ref_numbers:
        for e in elements:
            if hasattr(e, 'reference') and e.reference == ref_num:
                ref_elements[ref_num] = e
                break
    
    calc_values = []
    for period_idx in range(num_periods):
        formula_str = elem.formula
        
        for ref_num in ref_numbers:
            if ref_num in ref_elements:
                ref_elem = ref_elements[ref_num]
                
                if isinstance(ref_elem, AccountElement):
                    value = stored_values[ref_elem]['final'][period_idx]
                elif isinstance(ref_elem, PlaceholderElement):
                    value = ref_elem.values[period_idx]
                elif isinstance(ref_elem, (SumElement, CalcElement)):
                    value = stored_values[ref_elem][period_idx]
                else:
                    value = Decimal('0')
                
                formula_str = formula_str.replace(f'[{ref_num}]', str(float(value)))
        
        # Handle percentage signs: convert "X%" to "(X/100)"
        formula_str = re.sub(r'(\d+(?:\.\d+)?)%', r'(\1/100)', formula_str)
        
        try:
            result = Decimal(str(eval(formula_str)))
            result = result.quantize(Decimal('0.01'))
            calc_values.append(result)
        except Exception:
            calc_values.append(Decimal('0'))
    
    return calc_values


# ============================================================================
# MODULE 5: CSV OUTPUT
# ============================================================================

"""
GnuCash Report Generator - CSV Output Module V9

HIGH-LEVEL OVERVIEW:
This module handles generating clean CSV output suitable for importing into
spreadsheets. It takes the calculated report data and formats it according to
standard CSV conventions with proper quoting and formatting.

CSV Format:
- SECTION rows: section name only, other columns blank
- TITLE rows: title, then period labels, then "TOTAL"
- Data rows: description (quoted), values (one per period), total
- BLANK rows: completely empty
- Auto-spacing: 2 blanks before SECTION, 1 before TITLE
- Quoting: Fields with commas, quotes, or special chars are quoted

All monetary values formatted to 2 decimal places with no currency symbols
or thousands separators (Excel/Sheets will handle that formatting).
"""


def quote_csv_field(text):
    """
    Quote a CSV field if it contains commas, quotes, or newlines.
    
    Args:
        text: String to potentially quote
        
    Returns:
        str: Quoted string if special chars present, otherwise original
        
    CSV quoting rules:
        - If field contains comma, quote, or newline -> wrap in quotes
        - If field contains quotes -> escape them by doubling them
        - Numbers don't need quoting
        
    Examples:
        Simple text -> Simple text (no quoting needed)
        Text, with comma -> Wrapped in quotes
        Text with "quotes" -> Quotes are doubled and wrapped
    """
    # Check if quoting is needed
    if ',' in text or '"' in text or '\n' in text:
        # Escape existing quotes by doubling them
        escaped = text.replace('"', '""')
        return f'"{escaped}"'
    return text


def print_csv_output(config, elements, stored_values, period_labels, accounts=None):
    """
    Generate CSV output ready for spreadsheet import.
    
    Output format:
    - SECTION rows: section name in first column, rest blank
    - TITLE rows: title in first column, period labels in remaining columns
    - Data rows: description, values per period, total
    - BLANK rows: completely empty
    - Auto-spacing: 2 blanks before SECTION (except first), 1 before TITLE
    
    Args:
        config: ReportConfig object with settings
        elements: List of ReportElement objects (report structure)
        stored_values: Dict mapping elements to their calculated values
        period_labels: List of period label strings (e.g., ['Jan 2025', 'Feb 2025', ...])
        accounts: Dict of account data from GnuCash (optional, for account names)
        
    Output:
        Prints CSV to stdout (suitable for redirection to file)
        
    Example CSV output:
        Income & Expenses
        
        Income,Jan 2025,Feb 2025,Mar 2025,TOTAL
        Salary,5000.00,5000.00,5000.00,15000.00
        Bonus,0.00,0.00,1000.00,1000.00
        Total Income,5000.00,5000.00,6000.00,16000.00
    """
    # Track whether we need spacing before next element
    # last_was_section: True if previous element was a SECTION (skip blank before TITLE)
    last_was_section = False
    # first_section: True until we output first SECTION (no blanks before first)
    first_section = True
    
    # Process each element in order
    for elem in elements:
        # Auto-spacing rules
        if isinstance(elem, SectionElement):
            # 2 blank rows before SECTION (except first one)
            if not first_section:
                print()  # First blank
                print()  # Second blank
            first_section = False
            last_was_section = True
            
        elif isinstance(elem, TitleElement):
            # 1 blank row before TITLE (except first after SECTION)
            if not last_was_section:
                print()
            last_was_section = False
            
        else:
            # Any other element - reset spacing flags
            last_was_section = False
        
        # Output the element based on its type
        if isinstance(elem, SectionElement):
            # Section: name in first column, rest blank
            # No period columns for SECTION rows
            print(quote_csv_field(elem.title))
        
        elif isinstance(elem, TitleElement):
            # Title row: description, then period headers, then blank, TOTAL, AVERAGE
            # periods_str: Comma-separated list of period labels
            periods_str = ','.join(period_labels)
            print(f"{quote_csv_field(elem.text)},{periods_str},,TOTAL,AVERAGE")
        
        elif isinstance(elem, AccountElement):
            # Account row: description, values, total
            if elem in stored_values:
                # Check if this is an invalid GUID
                if not stored_values[elem].get('valid', True):
                    # Invalid GUID - show error message with no values
                    print(f"{quote_csv_field('<Invalid GUID>')}")
                    continue
                
                # Get final values after all transformations (filters, regex, operations)
                values = stored_values[elem]['final']
                
                # Determine description for first column
                # Priority: custom label > account name from GnuCash > placeholder
                if elem.label:
                    description = elem.label
                elif accounts:
                    description = get_account_display_name(elem.guid, accounts, config.account_name)
                else:
                    # No account data - show truncated GUID as placeholder
                    description = f"<Account {elem.guid[:8]}...>"
                
                # Format values: comma-separated, 2 decimal places
                values_str = ','.join(f"{float(v):.2f}" for v in values)
                total = sum(values)
                average = total / len(values) if len(values) > 0 else Decimal('0')
                print(f"{quote_csv_field(description)},{values_str},,{float(total):.2f},{float(average):.2f}")
        
        elif isinstance(elem, PlaceholderElement):
            # Placeholder: description and manually provided values
            values_str = ','.join(f"{float(v):.2f}" for v in elem.values)
            total = sum(elem.values)
            average = total / len(elem.values) if len(elem.values) > 0 else Decimal('0')
            print(f"{quote_csv_field(elem.description)},{values_str},,{float(total):.2f},{float(average):.2f}")
        
        elif isinstance(elem, SumElement):
            # Sum row: description and calculated sum values
            if elem in stored_values:
                values = stored_values[elem]
                values_str = ','.join(f"{float(v):.2f}" for v in values)
                total = sum(values)
                average = total / len(values) if len(values) > 0 else Decimal('0')
                print(f"{quote_csv_field(elem.description)},{values_str},,{float(total):.2f},{float(average):.2f}")
        
        elif isinstance(elem, CalcElement):
            # Calc row: description and calculated formula values
            if elem in stored_values:
                values = stored_values[elem]
                values_str = ','.join(f"{float(v):.2f}" for v in values)
                total = sum(values)
                average = total / len(values) if len(values) > 0 else Decimal('0')
                print(f"{quote_csv_field(elem.description)},{values_str},,{float(total):.2f},{float(average):.2f}")
        
        elif isinstance(elem, BlankElement):
            # Completely empty row (no commas, nothing)
            print()


# ============================================================================
# MODULE 6: MAIN PROGRAM
# ============================================================================

"""
GnuCash Report Generator - Main Program V3

HIGH-LEVEL OVERVIEW:
This is the orchestrator that brings all the modules together to generate reports.
It follows this flow:

1. Parse command line arguments
2. Parse the report definition file (markup)
3. Load the GnuCash XML file
4. **OPTIMIZED**: Identify all required filter/regex combinations upfront
5. Build all transaction caches in optimized passes (base + all filters)
6. Process each report element in order:
   - Calculate values using pre-built caches
   - Store results for later reference (CALC formulas)
7. Output final report (debug or CSV mode)

PERFORMANCE OPTIMIZATION:
Instead of building filtered caches on-demand during calculation (which causes
multiple passes through all transactions), we analyze the report definition first,
identify all required caches, and build them all upfront in a single optimized pass.

The program has two modes:
- Debug mode: Shows detailed breakdown with all intermediate values
- CSV mode: Clean output ready for spreadsheet import
"""


def print_debug_output(config, elements, references, accounts, tree, 
                       transaction_cache, filtered_caches, stored_values):
    """
    Print detailed debug output showing report structure and all calculated values.
    
    Args:
        config: ReportConfig object
        elements: List of ReportElement objects
        references: Dict of [n] -> line_num
        accounts: Dict of account data
        tree: XML tree
        transaction_cache: Pre-built base transaction cache
        filtered_caches: Pre-built filtered caches
        stored_values: Dict mapping elements to their calculated values
    """
    print("=" * 80)
    print("REPORT CONFIGURATION")
    print("=" * 80)
    print(f"START_DATE: {config.start_date}")
    print(f"END_DATE: {config.end_date}")
    print(f"PERIOD: {config.period}")
    print(f"ACCOUNT_NAME: {config.account_name}")
    print(f"INVERT_INCOME: {config.invert_income}")
    if config.gnucash_file:
        print(f"GNUCASH_FILE: {config.gnucash_file}")
    if config.csv_file:
        print(f"CSV_FILE: {config.csv_file}")
    
    if accounts:
        print(f"\nGnuCash file loaded: {len(accounts)} accounts found")
    
    labels = get_period_labels(config.start_date, config.end_date, config.period)
    print(f"\nPERIODS ({len(labels)}): {', '.join(labels)}")
    
    # Show cache statistics
    if filtered_caches:
        print(f"\nPERFORMANCE: Built {len(filtered_caches)} filtered caches upfront")
    
    print("\n" + "=" * 80)
    print("REPORT STRUCTURE")
    print("=" * 80)
    
    for elem in elements:
        if isinstance(elem, SectionElement):
            indent = 0
        elif isinstance(elem, TitleElement):
            indent = 1
        else:
            indent = 2
        
        prefix = "  " * indent
        ref_str = f"[{elem.reference}] " if elem.reference else ""
        
        if isinstance(elem, SectionElement):
            print(f"\n{ref_str}SECTION: {elem.title}")
        
        elif isinstance(elem, TitleElement):
            print(f"\n{prefix}{ref_str}TITLE: {elem.text}")
        
        elif isinstance(elem, AccountElement):
            account_type = "ACCOUNTS" if elem.recursive else "ACCOUNT"
            subaccount_note = " (and subaccounts)" if elem.recursive else ""
            print(f"{prefix}{ref_str}{account_type}: {elem.guid}{subaccount_note}")
            
            if elem.label:
                label_display = elem.label
            elif accounts:
                label_display = get_account_display_name(elem.guid, accounts, config.account_name)
            else:
                label_display = f"<{config.account_name}>"
            
            print(f"{prefix}  Label: {label_display}")
            
            if elem in stored_values:
                values_dict = stored_values[elem]
                
                # Check validity
                if not values_dict.get('valid', True):
                    print(f"{prefix}  ERROR: Invalid GUID - account not found in GnuCash file")
                    continue
                
                if 'raw' in values_dict:
                    print(f"{prefix}  Values (raw): {format_values_with_total(values_dict['raw'])}")
                
                if elem.filter_guid:
                    print(f"{prefix}  FILTER: {elem.filter_guid}")
                    if accounts:
                        filter_name = get_account_display_name(elem.filter_guid, accounts, config.account_name)
                        print(f"{prefix}    Filter account: {filter_name}")
                    
                    if 'filtered' in values_dict:
                        print(f"{prefix}    Values (filtered): {format_values_with_total(values_dict['filtered'])}")
                
                if elem.regex_include or elem.regex_exclude:
                    if elem.regex_include:
                        print(f"{prefix}  REGEX Include: {elem.regex_include}")
                    if elem.regex_exclude:
                        print(f"{prefix}  REGEX Exclude: {elem.regex_exclude}")
                    
                    if 'regex_filtered' in values_dict:
                        print(f"{prefix}    Values (regex filtered): {format_values_with_total(values_dict['regex_filtered'])}")
                
                if elem.operation:
                    op, val = elem.operation
                    print(f"{prefix}  Operation: {op} {val}")
                
                if 'final' in values_dict:
                    print(f"{prefix}  Values (final): {format_values_with_total(values_dict['final'])}")
        
        elif isinstance(elem, PlaceholderElement):
            print(f"{prefix}{ref_str}PLACEHOLDER: {elem.description}")
            print(f"{prefix}  Values: {format_values_with_total(elem.values)}")
            if len(elem.values) != len(labels):
                print(f"{prefix}  WARNING: Expected {len(labels)} values, got {len(elem.values)}")
        
        elif isinstance(elem, SumElement):
            print(f"{prefix}{ref_str}SUM: {elem.description}")
            if elem in stored_values:
                print(f"{prefix}  Values: {format_values_with_total(stored_values[elem])}")
        
        elif isinstance(elem, CalcElement):
            print(f"{prefix}{ref_str}CALC: {elem.description}")
            print(f"{prefix}  Formula: {elem.formula}")
            if elem in stored_values:
                print(f"{prefix}  Values: {format_values_with_total(stored_values[elem])}")
        
        elif isinstance(elem, BlankElement):
            print(f"{prefix}BLANK")
    
    print("\n" + "=" * 80)
    print(f"REFERENCES ({len(references)})")
    print("=" * 80)
    for ref_num in sorted(references.keys()):
        print(f"[{ref_num}] defined on line {references[ref_num]}")
    
    print("\n" + "=" * 80)
    print("VALIDATION: PASSED")
    print("=" * 80)


def process_report_elements(config, elements, references, accounts, tree, 
                            period_ranges, transaction_cache, filtered_caches):
    """
    Calculate values for all report elements in order.
    
    Args:
        config: ReportConfig object
        elements: List of ReportElement objects
        references: Dict of reference numbers to line numbers
        accounts: Dict of account data from GnuCash
        tree: XML tree from GnuCash file
        period_ranges: List of (start_date, end_date) tuples
        transaction_cache: Pre-built base transaction cache
        filtered_caches: Pre-built filtered caches {CacheKey: {period_idx: value}}
        
    Returns:
        dict: Maps elements to their calculated values
    """
    stored_values = {}
    num_periods = len(period_ranges)
    
    for elem in elements:
        if isinstance(elem, AccountElement):
            if accounts and tree:
                values_dict = calculate_account_values(
                    elem, period_ranges, accounts, config, 
                    transaction_cache, filtered_caches
                )
                stored_values[elem] = values_dict
            else:
                stored_values[elem] = {
                    'raw': [Decimal('0')] * num_periods,
                    'final': [Decimal('0')] * num_periods,
                    'valid': True
                }
        
        elif isinstance(elem, SumElement):
            sum_values = calculate_sum_values(elem, elements, stored_values, num_periods)
            stored_values[elem] = sum_values
        
        elif isinstance(elem, CalcElement):
            calc_values = calculate_calc_values(elem, stored_values, references, elements, num_periods)
            stored_values[elem] = calc_values
    
    return stored_values


def main():
    """
    Main program flow with optimized cache building.
    """
    parser = argparse.ArgumentParser(
        description='Generate reports from GnuCash files using custom report definitions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Generate CSV to file (default behavior)
  python gnucash_report_generator.py report_definition.txt
  
  # Output saved to report_definition.csv (or CSV_FILE if specified)
  
  # Override output location with --stdout
  python gnucash_report_generator.py report_definition.txt --stdout > custom.csv
  
  # Use specific GnuCash file (overrides file in definition)
  python gnucash_report_generator.py report_definition.txt Finances.gnucash
  
  # Show detailed debug output instead of CSV
  python gnucash_report_generator.py report_definition.txt --debug
        ''')
    
    parser.add_argument('definition', help='Path to report definition file')
    parser.add_argument('gnucash_file', nargs='?', 
                       help='Path to GnuCash file (optional if specified in definition)')
    parser.add_argument('--debug', action='store_true', 
                       help='Show detailed debug output instead of CSV')
    parser.add_argument('--stdout', action='store_true',
                       help='Output CSV to stdout instead of file (allows piping)')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.definition):
        print(f"Error: Report definition file '{args.definition}' not found.", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Step 1: Parse report definition
        print("Parsing report definition...", file=sys.stderr)
        config, elements, references = parse_report_definition(args.definition)
        
        # Step 2: Determine GnuCash file
        gnucash_file = args.gnucash_file if args.gnucash_file else config.gnucash_file
        
        # Step 3: Generate period ranges (needed regardless of whether we have GnuCash file)
        period_ranges = get_period_ranges(config.start_date, config.end_date, config.period)
        
        # Step 4: Load GnuCash file if specified
        accounts = None
        tree = None
        transaction_cache = None
        filtered_caches = {}
        
        if gnucash_file:
            if not os.path.exists(gnucash_file):
                print(f"Warning: GnuCash file '{gnucash_file}' not found.", file=sys.stderr)
                print("Continuing with placeholder values...", file=sys.stderr)
            else:
                print(f"Loading GnuCash file: {gnucash_file}...", file=sys.stderr)
                accounts, tree = parse_gnucash_file(gnucash_file)
                
                # Step 5: OPTIMIZATION - Identify all required caches upfront
                print("Analyzing report for cache requirements...", file=sys.stderr)
                required_filter_caches = identify_required_caches(elements)
                
                if required_filter_caches:
                    print(f"Building {len(required_filter_caches)} filtered caches...", file=sys.stderr)
                
                # Step 6: Build base transaction cache
                print("Building base transaction cache...", file=sys.stderr)
                account_guids = set(accounts.keys())
                transaction_cache = build_transaction_cache(tree, period_ranges, account_guids)
                
                # Step 7: Build all filtered caches in optimized passes
                if required_filter_caches:
                    filtered_caches = build_all_filtered_caches(tree, period_ranges, required_filter_caches)
                    print("All caches built successfully.", file=sys.stderr)
                else:
                    print("No filtered caches needed.", file=sys.stderr)
        else:
            print("Warning: No GnuCash file specified.", file=sys.stderr)
            print("Continuing with placeholder values...", file=sys.stderr)
        
        # Step 8: Process all elements and calculate values
        print("Calculating values...", file=sys.stderr)
        stored_values = process_report_elements(
            config, elements, references, accounts, tree, 
            period_ranges, transaction_cache, filtered_caches
        )
        
        # Step 9: Output results
        if args.debug:
            print_debug_output(config, elements, references, accounts, tree, 
                              transaction_cache, filtered_caches, stored_values)
        else:
            period_labels = get_period_labels(config.start_date, config.end_date, config.period)
            
            if args.stdout:
                print_csv_output(config, elements, stored_values, period_labels, accounts)
            else:
                if config.csv_file:
                    csv_filename = config.csv_file
                else:
                    base = os.path.splitext(args.definition)[0]
                    csv_filename = base + '.csv'
                
                print(f"Writing CSV output to: {csv_filename}", file=sys.stderr)
                
                original_stdout = sys.stdout
                try:
                    with open(csv_filename, 'w', encoding='utf-8') as f:
                        sys.stdout = f
                        print_csv_output(config, elements, stored_values, period_labels, accounts)
                finally:
                    sys.stdout = original_stdout
                
                print(f"CSV report generated successfully: {csv_filename}", file=sys.stderr)
        
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()