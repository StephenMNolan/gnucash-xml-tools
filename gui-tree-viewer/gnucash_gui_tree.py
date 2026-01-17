#!/usr/bin/env python3
"""
GnuCash Account Tree GUI Viewer V15
Displays account hierarchy in a graphical tree view with GUID display and copy functionality
"""

import xml.etree.ElementTree as ET
import gzip
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# GnuCash XML namespaces
NS = {
    'gnc': 'http://www.gnucash.org/XML/gnc',
    'act': 'http://www.gnucash.org/XML/act',
    'book': 'http://www.gnucash.org/XML/book',
    'slot': 'http://www.gnucash.org/XML/slot'
}


class Account:
    """Represents a GnuCash account"""
    def __init__(self, name, guid, parent_guid=None, hidden=False, placeholder=False):
        self.name = name
        self.guid = guid
        self.parent_guid = parent_guid
        self.hidden = hidden
        self.placeholder = placeholder
        self.children = []
    
    def add_child(self, child):
        self.children.append(child)
        self.children.sort(key=lambda a: a.name)


class GnuCashTreeViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("GnuCash Account Tree Viewer")
        self.root.geometry("900x700")
        
        # Store accounts and current file
        self.accounts = {}
        self.current_file = None
        
        # Create GUI
        self.create_widgets()
        
    def create_widgets(self):
        # Top frame for file selection
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X, side=tk.TOP)
        
        ttk.Label(top_frame, text="GnuCash File:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.file_entry = ttk.Entry(top_frame, width=60)
        self.file_entry.pack(side=tk.LEFT, padx=(0, 5), fill=tk.X, expand=True)
        
        ttk.Button(top_frame, text="Browse...", command=self.browse_file).pack(side=tk.LEFT)
        
        # Options frame
        options_frame = ttk.Frame(self.root, padding="10")
        options_frame.pack(fill=tk.X, side=tk.TOP)
        
        self.show_hidden_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Show hidden accounts", 
                       variable=self.show_hidden_var,
                       command=self.refresh_tree).pack(side=tk.LEFT)
        
        # Middle frame for tree view
        tree_frame = ttk.Frame(self.root, padding="10")
        tree_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP)
        
        # Create tree view with scrollbars
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
        
        # Configure tags for styling placeholder accounts
        self.tree.tag_configure('placeholder', foreground='gray', font=('TkDefaultFont', 10, 'italic'))
        
        # Bind selection event
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        
        # Bottom frame for GUID display
        bottom_frame = ttk.LabelFrame(self.root, text="Selected Account GUID", padding="10")
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=10)
        
        guid_inner_frame = ttk.Frame(bottom_frame)
        guid_inner_frame.pack(fill=tk.X)
        
        self.guid_entry = ttk.Entry(guid_inner_frame, font=("Courier", 10))
        self.guid_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.guid_entry.config(state='readonly')
        
        self.copy_button = ttk.Button(guid_inner_frame, text="Copy to Clipboard", 
                                      command=self.copy_guid, state='disabled')
        self.copy_button.pack(side=tk.LEFT)
        
        # Status bar
        self.status_var = tk.StringVar(value="No file loaded")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, 
                              relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        
    def browse_file(self):
        """Open file browser dialog and auto-load the selected file"""
        filename = filedialog.askopenfilename(
            title="Select GnuCash File",
            filetypes=[
                ("GnuCash Files", "*.gnucash *.gnc"),
                ("XML Files", "*.xml"),
                ("All Files", "*.*")
            ]
        )
        if filename:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, filename)
            # Auto-load the file
            self.load_file()
            
    def parse_gnucash_file(self, filename):
        """Parse GnuCash XML file (handles both gzipped and uncompressed)"""
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
            
            # Check if account is hidden
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
            
            # Create account object
            account = Account(name, guid, parent_guid, hidden, placeholder)
            accounts[guid] = account
        
        return accounts
    
    def build_tree(self, accounts):
        """Build parent-child relationships between accounts"""
        # Clear existing children first
        for account in accounts.values():
            account.children = []
        
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
    
    def load_file(self):
        """Load and parse the GnuCash file"""
        filename = self.file_entry.get().strip()
        
        if not filename:
            messagebox.showwarning("No File", "Please select a GnuCash file")
            return
        
        if not os.path.exists(filename):
            messagebox.showerror("File Not Found", f"File '{filename}' not found")
            return
        
        try:
            self.status_var.set("Loading file...")
            self.root.update()
            
            # Parse the file
            self.accounts = self.parse_gnucash_file(filename)
            self.current_file = filename
            
            # Build and display tree
            self.refresh_tree()
            
            self.status_var.set(f"Loaded {len(self.accounts)} accounts from {os.path.basename(filename)}")
            
        except ET.ParseError as e:
            messagebox.showerror("Parse Error", f"Error parsing XML: {e}")
            self.status_var.set("Error loading file")
        except Exception as e:
            messagebox.showerror("Error", f"Error loading file: {e}")
            self.status_var.set("Error loading file")
    
    def refresh_tree(self):
        """Refresh the tree view with current settings"""
        if not self.accounts:
            return
        
        # Save the currently expanded items and selection
        expanded_items = self.get_expanded_item_paths()
        selected_item_path = self.get_selected_item_path()
        
        # Clear existing tree
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Build tree structure
        root_account = self.build_tree(self.accounts)
        
        if root_account:
            # Insert root
            root_tags = ['placeholder'] if root_account.placeholder else []
            root_id = self.tree.insert('', 'end', text=root_account.name, 
                                      values=(root_account.guid, root_account.placeholder),
                                      tags=root_tags, open=True)
            
            # Insert children recursively
            for child in root_account.children:
                self.insert_account(root_id, child)
            
            # Restore expanded state and selection
            self.restore_expanded_items(expanded_items)
            self.restore_selected_item(selected_item_path)
    
    def insert_account(self, parent_id, account):
        """Recursively insert account and children into tree"""
        show_hidden = self.show_hidden_var.get()
        
        # Skip hidden accounts if not showing them
        if account.hidden and not show_hidden:
            return
        
        # Create display name
        display_name = account.name
        if account.hidden:
            display_name = f"[HIDDEN] {display_name}"
        
        # Determine tags for styling
        tags = []
        if account.placeholder:
            tags.append('placeholder')
        
        # Insert this account - store both GUID and placeholder status
        account_id = self.tree.insert(parent_id, 'end', text=display_name,
                                     values=(account.guid, account.placeholder), 
                                     tags=tags, open=False)
        
        # Insert children
        for child in account.children:
            self.insert_account(account_id, child)
    
    def on_tree_select(self, event):
        """Handle tree selection event"""
        selection = self.tree.selection()
        if selection:
            item = selection[0]
            values = self.tree.item(item, 'values')
            if values:
                guid = values[0]
                # Update GUID entry (placeholder accounts are now selectable too)
                self.guid_entry.config(state='normal')
                self.guid_entry.delete(0, tk.END)
                self.guid_entry.insert(0, guid)
                self.guid_entry.config(state='readonly')
                self.copy_button.config(state='normal')
    
    def copy_guid(self):
        """Copy GUID to clipboard"""
        guid = self.guid_entry.get()
        if guid:
            self.root.clipboard_clear()
            self.root.clipboard_append(guid)
            self.status_var.set(f"Copied GUID to clipboard: {guid}")
            # Flash the button to provide feedback
            self.copy_button.config(text="Copied!")
            self.root.after(1000, lambda: self.copy_button.config(text="Copy to Clipboard"))
    
    def get_item_path(self, item):
        """Get the path to an item as a list of account names"""
        path = []
        current = item
        while current:
            values = self.tree.item(current, 'values')
            if values:
                # Use GUID to identify the account uniquely
                path.insert(0, values[0])  # GUID
            current = self.tree.parent(current)
        return path
    
    def get_expanded_item_paths(self):
        """Get paths of all expanded items"""
        expanded = set()
        
        def collect_expanded(item):
            if self.tree.item(item, 'open'):
                path = tuple(self.get_item_path(item))
                if path:
                    expanded.add(path)
            for child in self.tree.get_children(item):
                collect_expanded(child)
        
        for item in self.tree.get_children():
            collect_expanded(item)
        
        return expanded
    
    def get_selected_item_path(self):
        """Get the path of the currently selected item"""
        selection = self.tree.selection()
        if selection:
            return tuple(self.get_item_path(selection[0]))
        return None
    
    def find_item_by_path(self, path):
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
        
        # Start from root
        for root_item in self.tree.get_children():
            values = self.tree.item(root_item, 'values')
            if values and values[0] == path[0]:
                return search_children(root_item, path[1:])
        
        return None
    
    def restore_expanded_items(self, expanded_paths):
        """Restore the expanded state of items"""
        for path in expanded_paths:
            item = self.find_item_by_path(path)
            if item:
                self.tree.item(item, open=True)
    
    def restore_selected_item(self, selected_path):
        """Restore the selected item"""
        if selected_path:
            item = self.find_item_by_path(selected_path)
            if item:
                self.tree.selection_set(item)
                self.tree.see(item)  # Scroll to make it visible


def main():
    root = tk.Tk()
    app = GnuCashTreeViewer(root)
    root.mainloop()


if __name__ == "__main__":
    main()