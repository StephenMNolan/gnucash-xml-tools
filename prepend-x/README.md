# GnuCash Account Name Prefixer for Hidden Accounts

A Python utility that prepends a prefix (default: "X ") to hidden account names in GnuCash files, making them sort to the end of reports and easy to filter out.

## Problem

GnuCash's "hidden" account flag keeps accounts visible in the account tree while hiding them from some views. However, hidden accounts still appear in many reports and can clutter your financial analysis. This tool solves that by prefixing hidden account names so they:

- Sort to the end of alphabetically-ordered reports
- Can be easily filtered out using name-based filters
- Remain visible in the account tree for reference
- Are clearly marked as inactive/archived

## Features

- **Safe**: Creates automatic timestamped backups before making any changes
- **Smart**: Handles both gzipped and plain XML GnuCash files
- **Preview**: Dry-run mode shows what will change before applying
- **Customizable**: Use any prefix you want (default is "X ")
- **Idempotent**: Won't re-prefix accounts that already have the prefix
- **Format-preserving**: Maintains file compression and XML structure

## Requirements

- Python 3.6 or higher
- No external dependencies (uses only standard library)

## Installation

Simply download the script:

```bash
wget https://raw.githubusercontent.com/YOUR_USERNAME/gnucash-account-prefixer/main/gnucash_prepend_x.py
chmod +x gnucash_prepend_x.py
```

Or clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/gnucash-account-prefixer.git
cd gnucash-account-prefixer
```

## Usage

### Dry Run (Preview Changes)

First, see what would change without modifying your file:

```bash
python gnucash_prepend_x.py myfile.gnucash
```

This will output something like:

```
Opening myfile.gnucash...
Parsing accounts...
Found 127 total accounts, 8 are hidden

WOULD MAKE 8 changes:
  Assets:Investments:Old 401k
    Old 401k → X Old 401k
  Assets:Investments:Old 401k:Stock Fund
    Stock Fund → X Stock Fund
  Expenses:Subscriptions:Unused Service
    Unused Service → X Unused Service
  ...

This was a DRY RUN. No changes were made.
To apply these changes, run with --apply flag
```

### Apply Changes

Once you're satisfied with the preview, apply the changes:

```bash
python gnucash_prepend_x.py myfile.gnucash --apply
```

### Custom Prefix

Want to use a different prefix? No problem:

```bash
# Use underscore prefix for different sorting
python gnucash_prepend_x.py myfile.gnucash --prefix "z_" --apply

# Use brackets for visual distinction
python gnucash_prepend_x.py myfile.gnucash --prefix "[archived] " --apply
```

## How It Works

1. Parses your GnuCash file to identify all accounts
2. Checks each account's hidden slot to find hidden accounts
3. For each hidden account, prepends the specified prefix to its name
4. Writes the changes back while preserving file format and structure
5. Handles XML entities properly (like `&amp;` for `&`)

## Why This Helps

After running this tool with the default "X " prefix:

- **Reports**: Hidden accounts sort to the end (X comes after most letters)
- **Filtering**: Easy to exclude with filters like "name does not start with X"
- **Clarity**: Immediately obvious which accounts are archived/inactive
- **Compatibility**: Works with all GnuCash report formats

## Safety

- **Automatic backups**: Every time you use `--apply`, a timestamped backup is created
- **Dry-run first**: The default mode shows changes without applying them
- **Idempotent**: Safe to run multiple times—won't double-prefix
- **Format preserving**: Maintains your file's compression and XML structure

## Examples

Standard workflow with default "X " prefix:

```bash
# Preview changes
python gnucash_prepend_x.py ~/Documents/finances.gnucash

# Apply if it looks good
python gnucash_prepend_x.py ~/Documents/finances.gnucash --apply
```

Use with custom prefix for special sorting:

```bash
# Use "zzz_" to ensure accounts are absolutely last
python gnucash_prepend_x.py myfile.gnucash --prefix "zzz_" --apply
```

## Combining with Other Tools

This tool works great with `gnucash_propagate_hidden.py`:

1. First, use `gnucash_propagate_hidden.py` to hide all child accounts of hidden parents
2. Then use `gnucash_prepend_x.py` to prefix all those hidden accounts

```bash
# Step 1: Propagate hidden status
python gnucash_propagate_hidden.py myfile.gnucash --apply

# Step 2: Prefix all hidden accounts
python gnucash_prepend_x.py myfile.gnucash --apply
```

## Troubleshooting

**File not found error**: Make sure the path to your GnuCash file is correct.

**"Already have the prefix"**: The script found accounts that already start with your prefix and skipped them. This is normal and safe.

**Parse error**: Ensure your GnuCash file is valid XML. Try opening it in GnuCash first to verify it's not corrupted.

**Special characters in names**: The script handles XML entities properly, so accounts with `&`, `<`, `>`, etc. should work fine.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - feel free to use and modify as needed.

## Disclaimer

This tool modifies your GnuCash files. While it creates backups automatically, always ensure you have your own backups before running any file modification tool. Use at your own risk.

## Support

If you encounter issues or have questions, please open an issue on GitHub.