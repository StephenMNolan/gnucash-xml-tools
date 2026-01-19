#!/usr/bin/env python3
"""
GnuCash Account Name Prefixer for Hidden Accounts V3
Prepends 'X ' to hidden account names to hide them from reports while keeping visible in tree
CREATES A BACKUP before modifying the file
"""

import xml.etree.ElementTree as ET
import gzip
import sys
import os
import argparse
from datetime import datetime
import shutil
import re

# GnuCash XML namespaces
NS = {
    'gnc': 'http://www.gnucash.org/XML/gnc',
    'act': 'http://www.gnucash.org/XML/act',
    'book': 'http://www.gnucash.org/XML/book',
    'slot': 'http://www.gnucash.org/XML/slot'
}

class Account:
    """Represents a GnuCash account"""
    def __init__(self, name, guid, parent_guid, hidden, element):
        self.name = name
        self.guid = guid
        self.parent_guid = parent_guid
        self.hidden = hidden
        self.element = element
        self.children = []
    
    def add_child(self, child):
        self.children.append(child)

def is_account_hidden(account_elem):
    """Check if an account has hidden=true in its slots"""
    slots_elem = account_elem.find('act:slots', NS)
    if slots_elem is not None:
        for slot in slots_elem.findall('slot', NS):
            key_elem = slot.find('slot:key', NS)
            if key_elem is not None and key_elem.text == 'hidden':
                value_elem = slot.find('slot:value', NS)
                if value_elem is not None and value_elem.text == 'true':
                    return True
    return False

def parse_accounts(tree):
    """Parse all accounts and build parent-child relationships"""
    root = tree.getroot()
    accounts = {}
    
    # Parse all accounts
    for account_elem in root.findall('.//gnc:account', NS):
        name_elem = account_elem.find('act:name', NS)
        name = name_elem.text if name_elem is not None else "Unknown"
        
        guid_elem = account_elem.find('act:id', NS)
        guid = guid_elem.text if guid_elem is not None else "no-guid"
        
        parent_elem = account_elem.find('act:parent', NS)
        parent_guid = parent_elem.text if parent_elem is not None else None
        
        hidden = is_account_hidden(account_elem)
        
        account = Account(name, guid, parent_guid, hidden, account_elem)
        accounts[guid] = account
    
    # Build parent-child relationships
    for guid, account in accounts.items():
        if account.parent_guid and account.parent_guid in accounts:
            parent = accounts[account.parent_guid]
            parent.add_child(account)
    
    return accounts

def get_account_path(account, accounts):
    """Build full account path like 'Assets:Bank:Checking'"""
    path_parts = [account.name]
    current = account
    
    # Walk up the tree to build the path
    while current.parent_guid is not None:
        parent = accounts.get(current.parent_guid)
        if parent is None:
            break
        # Skip the root account in the path
        if parent.parent_guid is not None:
            path_parts.insert(0, parent.name)
        current = parent
    
    return ':'.join(path_parts)

def rename_account_in_xml(xml_content, guid, old_name, new_name):
    """Rename an account in the XML text"""
    # Find the account with this GUID - must be in an <act:id> tag specifically
    # Not in a split or transaction reference
    account_pattern = rf'(<gnc:account version="2\.0\.0">)((?:(?!<gnc:account).)*?<act:id type="guid">{re.escape(guid)}</act:id>.*?)(</gnc:account>)'
    
    match = re.search(account_pattern, xml_content, re.DOTALL)
    if not match:
        print(f"Warning: Could not find account {old_name} ({guid}) in XML")
        return xml_content
    
    account_start = match.group(1)
    account_middle = match.group(2)
    account_end = match.group(3)
    
    # Verify this is the right account by checking the GUID is in <act:id> tag
    if f'<act:id type="guid">{guid}</act:id>' not in account_middle:
        print(f"Warning: GUID found but not in act:id tag for {old_name}")
        return xml_content
    
    # Find and replace the account name
    # The name is in <act:name>...</act:name>
    # We need to find what the name actually looks like in XML (may have entities like &amp;)
    name_tag_pattern = r'<act:name>(.*?)</act:name>'
    name_match = re.search(name_tag_pattern, account_middle)
    
    if name_match:
        xml_old_name = name_match.group(1)
        # Create new name by replacing the old name portion with the new prefix
        # The xml_old_name might have entities like &amp; for &
        xml_new_name = xml_old_name.replace(old_name, new_name)
        # But we also need to handle if old_name has & and xml has &amp;
        import html
        xml_old_name_unescaped = html.unescape(xml_old_name)
        if xml_old_name_unescaped == old_name:
            # The XML name matches when unescaped, so apply prefix to the XML version
            xml_new_name = new_name.replace(old_name, xml_old_name)
        
        new_account_middle = account_middle.replace(f'<act:name>{xml_old_name}</act:name>', 
                                                     f'<act:name>{xml_new_name}</act:name>')
        new_account_block = account_start + new_account_middle + account_end
        xml_content = xml_content.replace(match.group(0), new_account_block)
    else:
        print(f"Warning: Could not find <act:name> tag in account block for {old_name}")
    
    return xml_content

def process_hidden_accounts(accounts, prefix, xml_content, dry_run=True):
    """Find all hidden accounts and prefix their names"""
    changes = []
    modified_xml = xml_content
    
    for guid, account in accounts.items():
        if account.hidden:
            current_name = account.name
            
            # Check if already prefixed
            if not current_name.startswith(prefix):
                new_name = f"{prefix}{current_name}"
                
                if not dry_run:
                    modified_xml = rename_account_in_xml(modified_xml, guid, current_name, new_name)
                
                full_path = get_account_path(account, accounts)
                changes.append(f"  {full_path}")
                changes.append(f"    {current_name} → {new_name}")
                
                # Update our tracking
                account.name = new_name
    
    return changes, modified_xml

def main():
    parser = argparse.ArgumentParser(
        description='Prepend prefix to hidden account names to hide them from reports',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Dry run (show what would change)
  python gnucash_prepend_x.py myfile.gnucash
  
  # Actually make changes
  python gnucash_prepend_x.py myfile.gnucash --apply
  
  # Use custom prefix
  python gnucash_prepend_x.py myfile.gnucash --prefix "z_" --apply
        ''')
    
    parser.add_argument('filename', help='Path to GnuCash file')
    parser.add_argument('--apply', action='store_true',
                        help='Actually apply changes (default is dry-run)')
    parser.add_argument('--prefix', default='X ',
                        help='Prefix to add to account names (default: "X ")')
    
    args = parser.parse_args()
    
    gnucash_file = os.path.abspath(args.filename)
    
    if not os.path.exists(gnucash_file):
        print(f"Error: File '{gnucash_file}' not found.")
        sys.exit(1)
    
    try:
        print(f"Opening {gnucash_file}...")
        
        # Read the file and determine if it's gzipped
        is_gzipped = False
        xml_content = None
        
        try:
            with gzip.open(gnucash_file, 'rt', encoding='utf-8') as f:
                xml_content = f.read()
                is_gzipped = True
        except (gzip.BadGzipFile, OSError):
            with open(gnucash_file, 'r', encoding='utf-8') as f:
                xml_content = f.read()
        
        # Parse with ElementTree for analysis only
        from io import StringIO
        tree = ET.parse(StringIO(xml_content))
        
        print("Parsing accounts...")
        accounts = parse_accounts(tree)
        
        # Count hidden accounts
        hidden_count = sum(1 for acc in accounts.values() if acc.hidden)
        print(f"Found {len(accounts)} total accounts, {hidden_count} are hidden")
        
        # Process hidden accounts
        changes, modified_xml = process_hidden_accounts(accounts, args.prefix, xml_content, dry_run=not args.apply)
        
        if changes:
            print(f"\n{'WOULD MAKE' if not args.apply else 'MADE'} {len(changes)//2} changes:")
            for change in changes:
                print(change)
            
            if args.apply:
                # Create backup
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_file = f"{gnucash_file}.backup_{timestamp}"
                print(f"\nCreating backup: {backup_file}")
                shutil.copy2(gnucash_file, backup_file)
                
                # Write modified file
                print(f"Writing changes to {gnucash_file}...")
                if is_gzipped:
                    with gzip.open(gnucash_file, 'wt', encoding='utf-8') as f:
                        f.write(modified_xml)
                else:
                    with open(gnucash_file, 'w', encoding='utf-8') as f:
                        f.write(modified_xml)
                
                print("Done! Changes applied successfully.")
                print(f"\nNote: Hidden accounts prefixed with '{args.prefix}' will be sorted to the")
                print("end of reports and can be easily filtered out.")
            else:
                print("\nThis was a DRY RUN. No changes were made.")
                print("To apply these changes, run with --apply flag")
        else:
            print("\nNo changes needed. All hidden accounts already have the prefix.")
    
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