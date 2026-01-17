# GnuCash Account Tree Viewer

A lightweight command-line utility for visualizing GnuCash account hierarchies in a tree format with GUIDs. Perfect for developers, database administrators, or anyone who needs to inspect GnuCash account structures and their unique identifiers.

## Features

- **Zero Dependencies**: Uses only Python standard library (no external packages required)
- **Tree Visualization**: Displays accounts in an intuitive ASCII tree structure
- **GUID Display**: Shows account GUIDs for database work and API integration
- **Hidden Account Detection**: Identifies and optionally filters hidden accounts
- **Format Support**: Handles both compressed (.gnucash) and uncompressed XML files
- **Cross-Platform**: Works on Windows, macOS, and Linux

## Requirements

- Python 3.6 or higher
- A GnuCash file (`.gnucash` or uncompressed XML format)

## Installation

Simply download `gnucash_tree.py` and make it executable:

```bash
# Linux/macOS
chmod +x gnucash_tree.py

# Or run with python3 on any platform
python3 gnucash_tree.py
```

## Usage

### Basic Usage

Display the full account tree with GUIDs:

```bash
python3 gnucash_tree.py myfile.gnucash
```

### Command-Line Options

```bash
python3 gnucash_tree.py <filename> [options]

Options:
  --no-guid     Hide GUIDs in output
  --no-hidden   Hide hidden accounts and their descendants
```

### Examples

Show accounts without GUIDs:
```bash
python3 gnucash_tree.py myfile.gnucash --no-guid
```

Show only visible accounts:
```bash
python3 gnucash_tree.py myfile.gnucash --no-hidden
```

Show only visible accounts without GUIDs:
```bash
python3 gnucash_tree.py myfile.gnucash --no-guid --no-hidden
```

## Sample Output

```
GnuCash Account Tree
================================================================================
Root Account [1234567890abcdef1234567890abcdef]
+-- Assets [a1b2c3d4e5f6...]
|   +-- Current Assets [f6e5d4c3b2a1...]
|   |   +-- Checking Account [1a2b3c4d5e6f...]
|   |   L-- Savings Account [6f5e4d3c2b1a...]
|   L-- Fixed Assets [9f8e7d6c5b4a...]
+-- Liabilities [b2c3d4e5f6a1...]
|   L-- Credit Card [c3d4e5f6a1b2...]
+-- Income [d4e5f6a1b2c3...]
+-- Expenses [e5f6a1b2c3d4...]
L-- Equity [f6a1b2c3d4e5...]
================================================================================
```

With `--no-hidden` option, hidden accounts are excluded from the tree, and the last *visible* account in each branch correctly displays the "L--" connector.

## Use Cases

- **Database Integration**: Quickly find account GUIDs for SQL queries or custom reports
- **API Development**: Reference account GUIDs when working with GnuCash APIs
- **Account Auditing**: Review your account structure and identify hidden accounts
- **Documentation**: Generate visual account hierarchy diagrams for documentation
- **Migration Planning**: Understand account relationships before data migration

## How It Works

The script parses GnuCash's XML file format directly using Python's built-in `xml.etree.ElementTree` module. It:

1. Detects and handles gzip-compressed files automatically
2. Extracts account names, GUIDs, parent relationships, and hidden status
3. Builds a hierarchical tree structure
4. Renders the tree with ASCII art characters

## Limitations

- Read-only: This tool only reads GnuCash files; it never modifies them
- XML Format Only: Works with GnuCash XML files (most common format)
- No SQL Backend Support: Does not read from GnuCash SQL databases

## Troubleshooting

### Character Encoding Issues

The tree uses basic ASCII characters ("+", "|", "L", "-") for maximum compatibility across platforms and terminal types. If you see garbled characters, your terminal encoding may need adjustment, but the standard ASCII should work on any system.

### File Not Found

Ensure you provide the correct path to your GnuCash file:
```bash
python3 gnucash_tree.py /full/path/to/myfile.gnucash
```

### Parse Errors

If you encounter XML parse errors, your GnuCash file may be corrupted or in an unsupported format. Try opening it in GnuCash first to verify it's valid.

## Contributing

Contributions are welcome! Feel free to submit issues or pull requests for:

- Additional command-line options
- Enhanced filtering capabilities
- Export to other formats (JSON, CSV, etc.)
- Performance improvements

## License

This project is released under the MIT License. See LICENSE file for details.

## Author

Created to help developers and power users work more efficiently with GnuCash account structures.

## Acknowledgments

- GnuCash project for maintaining excellent XML documentation
- The Python community for robust standard library XML tools