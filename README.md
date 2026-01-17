# GnuCash Report Generator

A powerful Python tool for generating custom financial reports from GnuCash XML files. Create flexible, period-based reports with filtering, calculations, and CSV export - all defined in a simple text-based markup language.

## Features

- **Custom Report Definitions**: Define reports using an intuitive markup language
- **Flexible Time Periods**: Monthly or quarterly reporting with date abbreviations (BY, EPM, TODAY, etc.)
- **Advanced Filtering**: 
  - Filter transactions by account (FILTER)
  - Filter by regex patterns on descriptions/notes (REGEX)
  - Recursive account aggregation (ACCOUNTS)
- **Mathematical Operations**: Apply operations like `* 90%`, `/ 12`, etc. to any account
- **Calculated Fields**: Create formulas using references to other rows (CALC)
- **Auto-summing**: Automatic subtotals and totals (SUM)
- **Clean CSV Output**: Professional spreadsheet-ready output with proper formatting
- **Performance Optimized**: Intelligent caching system for fast report generation
- **Debug Mode**: Detailed breakdown showing all intermediate calculations

## Requirements

- Python 3.6+
- GnuCash file in XML format (.gnucash or .xml)
- No external dependencies (uses only Python standard library)

## Installation

Simply download `gnucash_report_generator.py` and make it executable:

```bash
# Linux/macOS
chmod +x gnucash_report_generator.py

# Or run with python3 on any platform
python3 gnucash_report_generator.py
```


## Quick Start

1. Create a report definition file (see `report_definition.txt` for template)
2. Run the generator:

```bash
# Generate CSV report
python gnucash_report_generator.py my_report.txt

# Use specific GnuCash file
python gnucash_report_generator.py my_report.txt /path/to/finances.gnucash

# View debug output
python gnucash_report_generator.py my_report.txt --debug

# Output to stdout (for piping)
python gnucash_report_generator.py my_report.txt --stdout > custom.csv
```

## Report Definition Syntax

### Configuration Section

All configuration fields are optional with sensible defaults:

```
START_DATE: BPY              # Beginning of previous year (default: BY)
END_DATE: EPY                # End of previous year (default: EY)
PERIOD: m                    # Monthly (m) or quarterly (q) - default: m
ACCOUNT_NAME: name_only      # name_only or full_path - default: name_only
GNUCASH_FILE: ./MyFinances.gnucash
CSV_FILE: output.csv
INVERT_INCOME: true          # Show income as positive - default: true
```

### Date Abbreviations

**Current Period:**
- `TODAY` - Current date
- `BY` - Beginning of Year (Jan 1)
- `BQ` - Beginning of Quarter
- `BM` - Beginning of Month
- `EY` - End of Year (Dec 31)
- `EQ` - End of Quarter
- `EM` - End of Month

**Previous Period:**
- `BPY` - Beginning of Previous Year
- `BPQ` - Beginning of Previous Quarter
- `BPM` - Beginning of Previous Month
- `EPY` - End of Previous Year
- `EPQ` - End of Previous Quarter
- `EPM` - End of Previous Month

### Report Commands

#### SECTION: Section Title
Creates a section header in the report.
```
SECTION: Income & Expenses
```

#### TITLE: Column Header Text
Creates a title row with period labels.
```
TITLE: Gross Income
```

#### ACCOUNT: guid [operation] | Optional Label
Pulls data for a single account.
```
ACCOUNT: 1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p
ACCOUNT: 1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p | Salary
ACCOUNT: 1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p * 90% | Reduced Amount
ACCOUNT: 1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p / 12 | Monthly Average
```

#### ACCOUNTS: guid [operation] | Optional Label
Includes account and all subaccounts recursively.
```
ACCOUNTS: 1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p | Total Medical
```

#### FILTER: guid
Must follow ACCOUNT/ACCOUNTS. Only includes transactions involving the filter account.
```
ACCOUNT: 401k_account_guid
FILTER: payroll_account_guid
```

#### REGEX: "pattern" [-"exclude"]
Must follow ACCOUNT/ACCOUNTS. Filter by transaction description/notes (case-insensitive).
```
REGEX: "CD"                              # Contains "CD"
REGEX: "T-Note|T-Bond"                   # Contains T-Note OR T-Bond
REGEX: -"Redemption"                     # Does NOT contain Redemption
REGEX: "Treasury" "Note"                 # Contains BOTH Treasury AND Note
REGEX: "T-Note|T-Bond" -"Redemption"     # (T-Note OR T-Bond) AND NOT Redemption
```

#### PLACEHOLDER: Description | val1,val2,val3,...
Manually entered values (not from GnuCash).
```
PLACEHOLDER: Manual Adjustment | 100.00,150.00,200.00
```

#### SUM: Description
Sums all rows since last SUM/CALC/TITLE.
```
SUM: Total Income
```

#### CALC: Description | formula
Performs calculations using [n] references.
```
CALC: Net Income | [1] - [2] - [3]
CALC: Percentage | [1] / [2] * 100
CALC: Depletion | [1] * 15%
```

#### [n] Reference Prefix
Mark any row for use in CALC formulas.
```
[1] SUM: Total Income
[2] ACCOUNT: abc123... | Medical Insurance
[3] CALC: After Insurance | [1] - [2]
```

#### BLANK:
Insert a blank row (rarely needed due to auto-spacing).

## Example Report Definition

```
# Annual Income Statement
START_DATE: BPY
END_DATE: EPY
PERIOD: m
ACCOUNT_NAME: name_only

SECTION: Income

TITLE: Salary Income
ACCOUNT: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx | Primary Job
ACCOUNT: yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy | Side Income
[1] SUM: Total Salary

TITLE: Investment Income
ACCOUNT: zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz | Interest
FILTER: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  # Only from primary brokerage
REGEX: "CD"  # Certificate of Deposit interest only
ACCOUNT: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb | Dividends
[2] SUM: Total Investment Income

[3] CALC: Total Income | [1] + [2]

SECTION: Expenses

TITLE: Housing
ACCOUNTS: cccccccccccccccccccccccccccccccc | All Housing Costs
[4] SUM: Total Housing

TITLE: Summary
CALC: Net Income | [3] - [4]
```

## Output Format

The generator produces clean CSV files with:
- Section headers
- Period columns (e.g., "Jan 2025", "Feb 2025", or "1Q 2025", "2Q 2025")
- TOTAL column (sum across all periods)
- AVERAGE column (average per period)
- Proper CSV quoting for fields with special characters
- Auto-spacing for readability

Example output:
```csv
Income & Expenses

Income,Jan 2025,Feb 2025,Mar 2025,,TOTAL,AVERAGE
Salary,5000.00,5000.00,5000.00,,15000.00,5000.00
Bonus,0.00,0.00,1000.00,,1000.00,333.33
Total Income,5000.00,5000.00,6000.00,,16000.00,5333.33
```

## Debug Mode

Run with `--debug` to see detailed information:
- Configuration settings
- All account GUIDs and names
- Raw values before filtering
- Values after each filter/operation
- Cache building statistics
- Full transaction matching details

```bash
python gnucash_report_generator.py report_definition.txt --debug
```

## Finding Account GUIDs

Account GUIDs are 32-character hexadecimal identifiers. To find them simply use one of the Account Tree Viewer utilities in this repository. Or do it the hard way:

1. Open your uncompressed GnuCash file in a text editor
2. Search for the account name
3. Look for the `<act:id>` tag near the account name
4. Copy the GUID (e.g., `1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p`)

## Performance

The generator uses an optimized caching system:
- Identifies all required filters upfront
- Builds all caches in a single pass through transactions
- Significantly faster than on-demand cache building
- Handles large GnuCash files efficiently

## Architecture

The program consists of six integrated modules:

1. **Utilities** - Date parsing, period generation, value formatting
2. **XML Reader** - GnuCash file parsing, account hierarchy, transaction caching
3. **Markup Parser** - Report definition parsing and validation
4. **Calculator** - Value computation with filters and operations
5. **CSV Output** - Clean spreadsheet-ready formatting
6. **Main Program** - Orchestration and command-line interface

## Error Handling

The generator provides clear error messages for:
- Invalid GUIDs (account not found)
- Syntax errors in report definitions (with line numbers)
- Missing configuration files
- Invalid date formats
- Mismatched period counts in PLACEHOLDER values
- Undefined references in CALC formulas

## Tips and Best Practices

1. **Use Comments**: Add `#` comments to document your report definitions
2. **Test Incrementally**: Start with a simple report and add complexity
3. **Use Debug Mode**: Verify filters and operations are working correctly
4. **Organize**: Use SECTION headers to group related data
5. **Validate**: Check TOTAL columns to ensure calculations are correct

## Limitations

- Works only with GnuCash XML format (not SQL database format)
- Requires all referenced accounts to exist in the GnuCash file
- PLACEHOLDER values must match the number of periods exactly
- CALC formulas use Python's `eval()` (basic arithmetic only)

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

This project is released under the MIT License. See LICENSE file for details.
