# GnuCash Hidden Status Propagator

A Python utility that automatically propagates the "hidden" status from parent accounts to all their descendant accounts in GnuCash files.

## Problem

In GnuCash, when you hide a parent account, its child accounts remain visible unless you manually hide each one. This tool solves that problem by automatically hiding all descendants of any hidden parent account, making your account tree cleaner and more consistent.

## Features

- **Safe**: Creates automatic timestamped backups before making any changes
- **Smart**: Handles both gzipped and plain XML GnuCash files
- **Preview**: Dry-run mode shows what will change before applying
- **Recursive**: Propagates hidden status through entire account hierarchies
- **Non-destructive**: Only adds hidden slots, never removes existing data

## Requirements

- Python 3.6 or higher
- No external dependencies (uses only standard library)

## Installation

Simply download the script:

```bash
wget https://raw.githubusercontent.com/YOUR_USERNAME/gnucash-hidden-propagator/main/gnucash_propagate_hidden.py
chmod +x gnucash_propagate_hidden.py
```

Or clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/gnucash-hidden-propagator.git
cd gnucash-hidden-propagator
```

## Usage

### Dry Run (Preview Changes)

First, see what would change without modifying your file:

```bash
python gnucash_propagate_hidden.py myfile.gnucash
```

This will output something like:

```
Opening myfile.gnucash...
Parsing accounts...

WOULD MAKE 3 changes:
  Set HIDDEN: Assets:Investments:Old 401k
  Set HIDDEN: Assets:Investments:Old 401k:Stock Fund
  Set HIDDEN: Assets:Investments:Old 401k:Bond Fund

This was a DRY RUN. No changes were made.
To apply these changes, run with --apply flag
```

### Apply Changes

Once you're satisfied with the preview, apply the changes:

```bash
python gnucash_propagate_hidden.py myfile.gnucash --apply
```

The script will:
1. Create a backup file (e.g., `myfile.gnucash.backup_20250117_143022`)
2. Modify your GnuCash file to hide the appropriate accounts
3. Preserve the file format (gzipped or plain XML)

## How It Works

1. Parses your GnuCash file to build the account hierarchy
2. Identifies all accounts that have the `hidden` flag set to `true`
3. Recursively finds all descendant accounts of hidden parents
4. Adds the hidden slot to each descendant account that isn't already hidden
5. Writes the changes back while preserving file format and structure

## Safety

- **Automatic backups**: Every time you use `--apply`, a timestamped backup is created
- **Dry-run first**: The default mode shows changes without applying them
- **Non-destructive**: Only adds hidden slots to accounts, never removes data
- **Format preserving**: Maintains your file's compression and XML structure

## Examples

Hide all descendants of archived accounts:

```bash
# Preview
python gnucash_propagate_hidden.py ~/Documents/finances.gnucash

# Apply if it looks good
python gnucash_propagate_hidden.py ~/Documents/finances.gnucash --apply
```

## Troubleshooting

**File not found error**: Make sure the path to your GnuCash file is correct.

**Already has hidden=true**: The script skips accounts that are already hidden and notes this in the output.

**Parse error**: Ensure your GnuCash file is valid XML. Try opening it in GnuCash first to verify it's not corrupted.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - feel free to use and modify as needed.

## Disclaimer

This tool modifies your GnuCash files. While it creates backups automatically, always ensure you have your own backups before running any file modification tool. Use at your own risk.

## Support

If you encounter issues or have questions, please open an issue on GitHub.