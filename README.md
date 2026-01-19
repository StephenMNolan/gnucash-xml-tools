# GnuCash XML Tools

A collection of Python utilities for viewing, analyzing, and manipulating GnuCash XML data files. These tools provide command-line and GUI interfaces to work with GnuCash files without requiring the main GnuCash application to be running.

## Why These Tools?

While GnuCash is powerful accounting software, there are times when you need to:
- Quickly view your account structure without opening the full application
- Generate custom financial reports with flexible formatting and calculations
- Reorder transactions on the same date to fix running balances
- Batch process hidden account statuses
- Modify account names programmatically for better report organization
- Work with GnuCash files in automated workflows

These tools fill those gaps by working directly with the GnuCash XML file format.

## Available Tools

### 📊 [Account Tree Viewers](gnucash-tree-viewer-command-line/)

Two complementary tools for visualizing your GnuCash account hierarchy:

- **[Command-Line Tree Viewer](gnucash-tree-viewer-command-line/)**: Fast, text-based visualization of your account tree. Perfect for quick checks, terminal workflows, and scripting. Shows account types, balances, and hidden status in a clean tree format.

- **[GUI Tree Viewer](gnucash-tree-viewer-gui/)**: Interactive graphical viewer with expandable/collapsible tree structure. Ideal for exploring complex account hierarchies with visual feedback.

### 📈 [Report Generator](gnucash-report-generator/)

A powerful tool for generating custom financial reports from GnuCash XML files:

- **Custom Report Definitions**: Define reports using an intuitive text-based markup language
- **Flexible Time Periods**: Monthly or quarterly reporting with date abbreviations (BY, EPM, TODAY, etc.)
- **Advanced Filtering**: Filter by account, regex patterns on descriptions/notes, recursive account aggregation
- **Mathematical Operations**: Apply operations like `* 90%`, `/ 12` to any account
- **Calculated Fields**: Create formulas using references to other rows
- **CSV Export**: Professional spreadsheet-ready output with proper formatting
- **Debug Mode**: Detailed breakdown showing all intermediate calculations

### 🔄 [Transaction Sorter](gnucash-transaction-sorter/)

A powerful graphical tool for reordering transactions within an account on a specific date:

- **Visual Reordering**: Simple up/down buttons to change transaction order
- **Running Balance Display**: See real-time balance calculations as you reorder
- **Safe File Handling**: Automatic backups and lock file management
- **Smart Account Selection**: Tree view showing only accounts with sortable transactions
- **Persistent Configuration**: Remembers your last file, account, and window position
- **Change Detection**: Prompts before discarding unsaved changes

Perfect for fixing transaction order when multiple transactions occur on the same date and you need the running balance to reflect the correct sequence.

### 🔧 [Account Management Tools](gnucash-propagate-hidden/)

Utilities for managing account visibility and organization:

- **[Hidden Status Propagator](gnucash-propagate-hidden/)**: Automatically propagates the "hidden" flag from parent accounts to all their children. Ensures consistent visibility throughout your account tree.

- **[Account Name Prefixer](gnucash-prepend-x/)**: Prepends a customizable prefix (default: "X ") to hidden account names, making them sort to the end of reports and easy to filter out.

## Quick Start

Each tool is self-contained in its own directory with detailed documentation. General usage pattern:

```bash
# Clone the repository
git clone https://github.com/StephenMNolan/gnucash-xml-tools.git
cd gnucash-xml-tools

# Navigate to the tool you want
cd gnucash-propagate-hidden

# Read the specific README
cat README.md

# Run the tool (dry-run by default)
python gnucash_propagate_hidden.py ~/Documents/myfile.gnucash

# Apply changes when ready
python gnucash_propagate_hidden.py ~/Documents/myfile.gnucash --apply
```

## Common Workflows

### Workflow 1: Generate Custom Financial Reports

Create flexible, period-based reports with filtering and calculations:

```bash
cd gnucash-report-generator

# Create a report definition file (see documentation for syntax)
# Then generate your report
python gnucash_report_generator.py my_report.txt

# View debug output to verify calculations
python gnucash_report_generator.py my_report.txt --debug

# Output to custom file
python gnucash_report_generator.py my_report.txt --stdout > custom.csv
```

### Workflow 2: Fix Transaction Order and Running Balance

When you have multiple transactions on the same date and need to reorder them:

```bash
cd gnucash-transaction-sorter

# Run the Transaction Sorter
python gnucash_transaction_sorter.py

# 1. Select your GnuCash file
# 2. Choose the account
# 3. Pick the date with multiple transactions
# 4. Use up/down buttons to reorder
# 5. Watch the running balance update in real-time
# 6. Click "Commit Changes" to save
```

### Workflow 3: Clean Up Archived Accounts

When you have old accounts you want to hide from reports:

```bash
# 1. Manually hide parent accounts in GnuCash (e.g., "Old 401k", "Closed Accounts")
# 2. Close GnuCash
# 3. Propagate hidden status to all children
cd gnucash-propagate-hidden
python gnucash_propagate_hidden.py ~/myfile.gnucash --apply

# 4. Prefix all hidden accounts for report filtering
cd ../gnucash-prepend-x
python gnucash_prepend_x.py ~/myfile.gnucash --apply

# 5. Reopen in GnuCash - all archived accounts now prefixed with "X "
```

### Workflow 4: Quick Account Structure Review

When you need to see your account structure without opening GnuCash:

```bash
# View in terminal
cd gnucash-tree-viewer-command-line
python gnucash_tree_viewer.py ~/myfile.gnucash

# Or use the GUI for interactive exploration
cd ../gnucash-tree-viewer-gui
python gnucash_gui_tree.py ~/myfile.gnucash
```

## Requirements

- **Python 3.6+** (developed and tested with Python 3.14)
- **tkinter** for GUI tools (usually included with Python)
- **No external dependencies** - all tools use Python standard library only
- **Tested on macOS** - should work on Linux and Windows but not extensively tested

## Safety Features

All modification tools include:
- ✅ **Automatic timestamped backups** before any changes
- ✅ **Dry-run mode by default** - preview changes before applying
- ✅ **Format preservation** - maintains gzip compression and XML structure
- ✅ **Non-destructive operations** - only add data, never remove
- ✅ **Lock file management** - prevents concurrent file access (Transaction Sorter)

## File Format Support

These tools work with:
- GnuCash XML files (`.gnucash` extension)
- Both compressed (gzipped) and uncompressed formats
- GnuCash 2.x and 3.x file formats (and likely newer versions)

**Note:** These tools do **not** support:
- SQL-based GnuCash files (SQLite, MySQL, PostgreSQL)
- Binary formats
- Scheduled transactions or price tables (viewing tools only show accounts and balances)

## Tool Comparison

| Tool | Purpose | Modifies File | GUI | Best For |
|------|---------|---------------|-----|----------|
| **Command-Line Viewer** | View account tree | ❌ No | ❌ No | Quick lookups, scripts |
| **GUI Viewer** | Browse account tree | ❌ No | ✅ Yes | Exploring complex trees |
| **Report Generator** | Create custom reports | ❌ No | ❌ No | Financial analysis, CSV export |
| **Transaction Sorter** | Reorder transactions | ✅ Yes | ✅ Yes | Fixing running balances |
| **Hidden Propagator** | Cascade hidden flag | ✅ Yes | ❌ No | Batch hiding accounts |
| **Name Prefixer** | Prefix account names | ✅ Yes | ❌ No | Report organization |

## Contributing

Contributions are welcome! Each tool is independent, so you can:
- Improve existing tools
- Add new utilities for GnuCash XML manipulation
- Enhance documentation
- Report bugs or request features

Please open an issue or submit a pull request.

## Development Notes

These tools were created to solve specific workflow needs when working with GnuCash files. They:
- Parse XML directly using Python's `xml.etree.ElementTree`
- Handle GnuCash's namespace structure
- Preserve all existing data and formatting
- Use regex for precise XML manipulation where needed

If you're developing your own GnuCash tools, the source code may serve as useful examples of working with the GnuCash XML format.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Disclaimer

These tools modify GnuCash files directly. While they create automatic backups and have been tested extensively, always maintain your own backups of financial data. Use at your own risk.

GnuCash is a trademark of the GnuCash development team. These tools are independent utilities and are not affiliated with or endorsed by the GnuCash project.

## Resources

- [GnuCash Official Website](https://www.gnucash.org/)
- [GnuCash Documentation](https://www.gnucash.org/docs.phtml)
- [GnuCash XML File Format](https://wiki.gnucash.org/wiki/GnuCash_XML_format)

## Support

For issues or questions about these tools:
- Open an issue on GitHub
- Check individual tool READMEs for specific documentation
- Review the source code - it's well-commented

For GnuCash itself:
- Visit [GnuCash Support](https://www.gnucash.org/support.phtml)
- Join the [GnuCash mailing lists](https://lists.gnucash.org/mailman/listinfo)
