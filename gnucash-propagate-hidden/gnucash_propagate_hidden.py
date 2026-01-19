#!/usr/bin/env python3
"""
GnuCash Hidden Status Propagator V6
Applies hidden status to all descendants of hidden parent accounts
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
    
    for guid, account in accounts.items():
        if account.parent_guid and account.parent_guid in accounts:
            parent = accounts[account.parent_guid]
            parent.add_child(account)
    
    return accounts

def get_account_path(account, accounts):
    """Build full account path like 'Assets:Bank:Checking'"""
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

def collect_accounts_to_hide(account, accounts_to_hide, accounts):
    """Recursively collect accounts that need to be hidden"""
    if account.hidden:
        for child in account.children:
            if not child.hidden:
                full_path = get_account_path(child, accounts)
                accounts_to_hide[child.guid] = full_path
                # Mark as hidden for recursive processing
                child.hidden = True
            # Always recurse to children of hidden accounts
            collect_accounts_to_hide(child, accounts_to_hide, accounts)
    else:
        for child in account.children:
            collect_accounts_to_hide(child, accounts_to_hide, accounts)

def add_hidden_slot_to_xml(xml_content, guid, account_name):
    """Add hidden slot to an account in the XML text"""
    # Find the account with this GUID - must be in an <act:id> tag specifically
    # Not in a split or transaction reference
    account_pattern = rf'(<gnc:account version="2\.0\.0">)((?:(?!<gnc:account).)*?<act:id type="guid">{re.escape(guid)}</act:id>.*?)(</gnc:account>)'
    
    match = re.search(account_pattern, xml_content, re.DOTALL)
    if not match:
        print(f"Warning: Could not find account {account_name} ({guid}) in XML")
        return xml_content
    
    account_start = match.group(1)
    account_middle = match.group(2)
    account_end = match.group(3)
    
    # Verify this is the right account by checking the GUID is in <act:id> tag
    if f'<act:id type="guid">{guid}</act:id>' not in account_middle:
        print(f"Warning: GUID found but not in act:id tag for {account_name}")
        return xml_content
    
    # Check if this account already has a hidden slot - if so, skip it
    if re.search(r'<slot:key>hidden</slot:key>\s*<slot:value[^>]*>true</slot:value>', account_middle):
        print(f"  Note: {account_name} already has hidden=true, skipping")
        return xml_content
    
    # Check if this account already has act:slots
    if '<act:slots>' in account_middle:
        # Find the closing </act:slots> tag and insert the hidden slot before it
        # Need to be careful to find the right </act:slots> (not one nested in a slot value)
        
        # Split at </act:slots> - we want the LAST one in this account
        parts = account_middle.rsplit('</act:slots>', 1)
        if len(parts) == 2:
            before_close = parts[0]
            after_close = parts[1]
            
            # Add the hidden slot with proper indentation
            hidden_slot = '''    <slot>
      <slot:key>hidden</slot:key>
      <slot:value type="string">true</slot:value>
    </slot>
'''
            new_account_middle = before_close + '\n' + hidden_slot + '  </act:slots>' + after_close
            new_account_block = account_start + new_account_middle + account_end
            xml_content = xml_content.replace(match.group(0), new_account_block)
        else:
            print(f"Warning: Could not find </act:slots> in account {account_name}")
    else:
        # Need to add entire act:slots section
        # Insert before <act:parent> if it exists, otherwise before </gnc:account>
        if '<act:parent' in account_middle:
            # Find where to insert (before <act:parent>)
            parent_match = re.search(r'(\s*)(<act:parent)', account_middle)
            if parent_match:
                indent = parent_match.group(1)
                insert_pos = account_middle.find(parent_match.group(0))
                
                slots_section = f'''{indent}<act:slots>
{indent}  <slot>
{indent}    <slot:key>hidden</slot:key>
{indent}    <slot:value type="string">true</slot:value>
{indent}  </slot>
{indent}</act:slots>
'''
                new_account_middle = account_middle[:insert_pos] + slots_section + account_middle[insert_pos:]
                new_account_block = account_start + new_account_middle + account_end
                xml_content = xml_content.replace(match.group(0), new_account_block)
        else:
            # Insert before </gnc:account>
            slots_section = '''  <act:slots>
    <slot>
      <slot:key>hidden</slot:key>
      <slot:value type="string">true</slot:value>
    </slot>
  </act:slots>
'''
            new_account_middle = account_middle + '\n' + slots_section
            new_account_block = account_start + new_account_middle + account_end
            xml_content = xml_content.replace(match.group(0), new_account_block)
    
    return xml_content

def main():
    parser = argparse.ArgumentParser(
        description='Propagate hidden status to all descendants of hidden accounts',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Dry run (show what would change)
  python gnucash_propagate_hidden.py myfile.gnucash
  
  # Actually make changes
  python gnucash_propagate_hidden.py myfile.gnucash --apply
        ''')
    
    parser.add_argument('filename', help='Path to GnuCash file')
    parser.add_argument('--apply', action='store_true',
                        help='Actually apply changes (default is dry-run)')
    
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
        
        # Find root account
        root_account = None
        for account in accounts.values():
            if account.parent_guid is None:
                root_account = account
                break
        
        if not root_account:
            print("Error: Could not find root account")
            sys.exit(1)
        
        # Collect accounts that need to be hidden
        accounts_to_hide = {}
        collect_accounts_to_hide(root_account, accounts_to_hide, accounts)
        
        if accounts_to_hide:
            print(f"\n{'WOULD MAKE' if not args.apply else 'MADE'} {len(accounts_to_hide)} changes:")
            for guid, path in accounts_to_hide.items():
                print(f"  Set HIDDEN: {path}")
            
            if args.apply:
                # Create backup
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_file = f"{gnucash_file}.backup_{timestamp}"
                print(f"\nCreating backup: {backup_file}")
                shutil.copy2(gnucash_file, backup_file)
                
                # Modify the XML content by adding hidden slots
                print(f"Writing changes to {gnucash_file}...")
                modified_xml = xml_content
                for guid, path in accounts_to_hide.items():
                    modified_xml = add_hidden_slot_to_xml(modified_xml, guid, path)
                
                # Write back to file
                if is_gzipped:
                    with gzip.open(gnucash_file, 'wt', encoding='utf-8') as f:
                        f.write(modified_xml)
                else:
                    with open(gnucash_file, 'w', encoding='utf-8') as f:
                        f.write(modified_xml)
                
                print("Done! Changes applied successfully.")
            else:
                print("\nThis was a DRY RUN. No changes were made.")
                print("To apply these changes, run with --apply flag")
        else:
            print("\nNo changes needed. All accounts are already consistent.")
    
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