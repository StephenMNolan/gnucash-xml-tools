#!/usr/bin/env python3
"""
GnuCash Account Tree Viewer
Displays account hierarchy with GUIDs in a DOS-style tree format
Parses GnuCash XML files directly (no external dependencies needed)
"""

import xml.etree.ElementTree as ET
import gzip
import sys
import os
import argparse

# sys.stdout.reconfigure(encoding='utf-8')  # Python 3.7+
# sys.stderr.reconfigure(encoding='utf-8')

# GnuCash XML namespaces
NS = {
    'gnc': 'http://www.gnucash.org/XML/gnc',
    'act': 'http://www.gnucash.org/XML/act',
    'book': 'http://www.gnucash.org/XML/book',
    'slot': 'http://www.gnucash.org/XML/slot'
}

class Account:
    """Represents a GnuCash account"""
    def __init__(self, name, guid, parent_guid=None, hidden=False):
        self.name = name
        self.guid = guid
        self.parent_guid = parent_guid
        self.hidden = hidden
        self.children = []
    
    def add_child(self, child):
        self.children.append(child)
        self.children.sort(key=lambda a: a.name)

def parse_gnucash_file(filename):
    """
    Parse GnuCash XML file (handles both gzipped and uncompressed)
    Returns dictionary of accounts keyed by GUID
    """
    # Try to open as gzipped first, fall back to regular file
    try:
        with gzip.open(filename, 'rt', encoding='utf-8') as f:
            tree = ET.parse(f)
    except (gzip.BadGzipFile, OSError):
        with open(filename, 'r', encoding='utf-8') as f:
            tree = ET.parse(f)
    
    root = tree.getroot()
    accounts = {}
    
    # Find all account elements
    for account_elem in root.findall('.//gnc:account', NS):
        # Extract account name
        name_elem = account_elem.find('act:name', NS)
        name = name_elem.text if name_elem is not None else "Unknown"
        
        # Extract GUID
        guid_elem = account_elem.find('act:id', NS)
        guid = guid_elem.text if guid_elem is not None else "no-guid"
        
        # Extract parent GUID (if exists)
        parent_elem = account_elem.find('act:parent', NS)
        parent_guid = parent_elem.text if parent_elem is not None else None
        
        # Check if account is hidden (stored in slots)
        hidden = False
        slots_elem = account_elem.find('act:slots', NS)
        if slots_elem is not None:
            for slot in slots_elem.findall('slot', NS):
                key_elem = slot.find('slot:key', NS)
                if key_elem is not None and key_elem.text == 'hidden':
                    value_elem = slot.find('slot:value', NS)
                    if value_elem is not None and value_elem.text == 'true':
                        hidden = True
                        break
        
        # Create account object
        account = Account(name, guid, parent_guid, hidden)
        accounts[guid] = account
    
    return accounts

def build_tree(accounts):
    """
    Build parent-child relationships between accounts
    Returns root account
    """
    # Build parent-child relationships
    for guid, account in accounts.items():
        if account.parent_guid and account.parent_guid in accounts:
            parent = accounts[account.parent_guid]
            parent.add_child(account)
    
    # Find root account (has no parent)
    for account in accounts.values():
        if account.parent_guid is None:
            return account
    
    return None

def print_account_tree(account, prefix="", is_last=True, show_guid=True, show_hidden=True):
    """
    Recursively print account tree in DOS tree style
    
    Args:
        account: Account object to print
        prefix: String prefix for tree drawing
        is_last: Boolean indicating if this is the last child
        show_guid: Boolean to show/hide GUIDs
        show_hidden: Boolean to show/hide hidden accounts
    """
    # Skip hidden accounts and all their descendants if not showing hidden
    if account.hidden and not show_hidden:
        return
    
    # Determine the connector characters
    connector = "L-- " if is_last else "+-- "
    
    # Build the account display string
    account_str = account.name
    
    # Add [HIDDEN] flag if account is hidden and we're showing hidden accounts
    if account.hidden and show_hidden:
        account_str = f"[HIDDEN] {account_str}"
    
    # Add GUID if requested
    if show_guid:
        account_str = f"{account_str} [{account.guid}]"
    
    # Print current account
    print(f"{prefix}{connector}{account_str}")
    
    # Prepare prefix for children
    if is_last:
        child_prefix = prefix + "    "
    else:
        child_prefix = prefix + "|   "
    
    # Filter children based on show_hidden setting
    visible_children = [child for child in account.children 
                       if show_hidden or not child.hidden]
    
    # Recursively print each visible child
    for i, child in enumerate(visible_children):
        is_last_child = (i == len(visible_children) - 1)
        print_account_tree(child, child_prefix, is_last_child, show_guid, show_hidden)

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description='Display GnuCash account tree with GUIDs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python gnucash_tree.py myfile.gnucash
  python gnucash_tree.py myfile.gnucash --no-guid
  python gnucash_tree.py myfile.gnucash --no-hidden
  python gnucash_tree.py myfile.gnucash --no-guid --no-hidden
        ''')
    
    parser.add_argument('filename', help='Path to GnuCash file')
    parser.add_argument('--no-guid', action='store_true', 
                        help='Hide GUIDs in output')
    parser.add_argument('--no-hidden', action='store_true',
                        help='Hide hidden accounts and their descendants')
    
    args = parser.parse_args()
    
    gnucash_file = os.path.abspath(args.filename)
    
    if not os.path.exists(gnucash_file):
        print(f"Error: File '{gnucash_file}' not found.")
        sys.exit(1)
    
    try:
        print(f"Opening {gnucash_file}...")
        print("Parsing XML...")
        
        # Parse the GnuCash file
        accounts = parse_gnucash_file(gnucash_file)
        
        # Determine display settings
        show_guid = not args.no_guid
        show_hidden = not args.no_hidden
        
        print(f"Found {len(accounts)} accounts")
        print("\nGnuCash Account Tree")
        print("=" * 80)
        
        # Build and print tree
        root = build_tree(accounts)
        
        if root:
            # Print root
            root_str = root.name
            if show_guid:
                root_str = f"{root_str} [{root.guid}]"
            print(root_str)
            
            # Filter root children based on show_hidden setting
            visible_children = [child for child in root.children 
                              if show_hidden or not child.hidden]
            
            # Print visible children
            for i, child in enumerate(visible_children):
                is_last = (i == len(visible_children) - 1)
                print_account_tree(child, "", is_last, show_guid, show_hidden)
        else:
            print("Error: Could not find root account")
        
        print("\n" + "=" * 80)
        print("Done!")
        
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()