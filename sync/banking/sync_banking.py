#!/usr/bin/env python3
"""
Banking / Finance → Life OS Sync

Supports multiple import methods:
1. CSV bank statement import (most banks support this)
2. PDF statement parsing (basic)
3. Wise API (for Wise/TransferWise users)
4. Manual entry via Google Sheets → CSV export

The goal: get all transactions into life/finance/log.yaml so Claude
can analyze spending, track budget, and give insights.

Usage:
    # Import from bank CSV:
    python sync_banking.py --input ~/Downloads/statement.csv --bank maybank
    python sync_banking.py --input ~/Downloads/statement.csv --bank cimb
    python sync_banking.py --input ~/Downloads/statement.csv --bank generic

    # Import from Google Sheets CSV (manual tracking):
    python sync_banking.py --input ~/Downloads/expenses.csv --bank sheets

    # Import from Wise API:
    python sync_banking.py --source wise --days 30
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / ".config"
RAW_DIR = BASE_DIR / "data" / "raw" / "banking"
FINANCE_LOG = BASE_DIR / "life" / "finance" / "log.yaml"


# ── Auto-categorization ─────────────────────────────────────────────────────

CATEGORY_RULES = {
    'food': [
        'grab food', 'foodpanda', 'shopee food', 'restaurant', 'cafe', 'coffee',
        'starbucks', 'mcdonald', 'kfc', 'pizza', 'sushi', 'nasi', 'makan',
        'grocery', 'grocer', 'jaya grocer', 'village grocer', 'cold storage',
        'tesco', 'aeon', 'mydin', 'baker', 'deli',
    ],
    'transport': [
        'grab', 'gojek', 'uber', 'mrt', 'lrt', 'rapidkl', 'parking',
        'petronas', 'shell', 'petron', 'caltex', 'fuel', 'petrol',
        'toll', 'touch n go', 'tng', 'smart tag',
    ],
    'housing': [
        'rent', 'rental', 'mortgage', 'condo', 'apartment', 'property',
    ],
    'utilities': [
        'tenaga', 'tnb', 'air selangor', 'indah water', 'unifi', 'maxis',
        'digi', 'celcom', 'umobile', 'time', 'electric', 'water bill',
        'internet', 'phone bill',
    ],
    'subscriptions': [
        'netflix', 'spotify', 'youtube', 'disney', 'apple', 'google storage',
        'claude', 'chatgpt', 'openai', 'notion', 'figma', 'github',
        'adobe', 'canva', 'amazon prime', 'hbo',
    ],
    'health': [
        'pharmacy', 'doctor', 'clinic', 'hospital', 'dental', 'guardian',
        'watson', 'gym', 'fitness first', 'anytime fitness', 'supplement',
    ],
    'entertainment': [
        'cinema', 'gsc', 'tgv', 'movie', 'concert', 'game', 'steam',
        'playstation', 'xbox', 'nintendo',
    ],
    'shopping': [
        'shopee', 'lazada', 'zalora', 'uniqlo', 'h&m', 'ikea', 'mr diy',
        'daiso', 'amazon',
    ],
    'education': [
        'udemy', 'coursera', 'book', 'kindle', 'course', 'tuition',
        'university', 'college',
    ],
    'transfer': [
        'transfer', 'duitnow', 'ibg', 'instant transfer',
    ],
    'income': [
        'salary', 'payroll', 'commission', 'bonus', 'dividend', 'interest',
        'refund', 'cashback',
    ],
}


def auto_categorize(description: str, amount: float) -> str:
    """Guess transaction category from description."""
    desc_lower = description.lower()

    # Income is positive
    if amount > 0:
        for keyword in CATEGORY_RULES['income']:
            if keyword in desc_lower:
                return 'income'
        return 'income'

    # Expenses
    for category, keywords in CATEGORY_RULES.items():
        if category == 'income':
            continue
        for keyword in keywords:
            if keyword in desc_lower:
                return category

    return 'misc'


# ── Bank CSV Parsers ─────────────────────────────────────────────────────────

def parse_maybank_csv(filepath: Path) -> list:
    """Parse Maybank (Malaysia) CSV statement."""
    transactions = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = row.get('Date', row.get('Transaction Date', ''))
            desc = row.get('Description', row.get('Transaction Description', ''))
            debit = row.get('Debit', row.get('Amount (Debit)', ''))
            credit = row.get('Credit', row.get('Amount (Credit)', ''))

            amount = 0
            if credit and credit.strip():
                amount = float(credit.replace(',', ''))
            elif debit and debit.strip():
                amount = -float(debit.replace(',', ''))

            if date and desc:
                transactions.append({
                    'date': parse_date(date),
                    'description': desc.strip(),
                    'amount': amount,
                    'category': auto_categorize(desc, amount),
                })
    return transactions


def parse_cimb_csv(filepath: Path) -> list:
    """Parse CIMB (Malaysia) CSV statement."""
    transactions = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = row.get('Date', row.get('Txn Date', ''))
            desc = row.get('Description', row.get('Txn Description', ''))
            amount_str = row.get('Amount', row.get('Txn Amount', '0'))

            try:
                amount = float(amount_str.replace(',', '').replace('DR', '-').replace('CR', ''))
            except ValueError:
                continue

            if date and desc:
                transactions.append({
                    'date': parse_date(date),
                    'description': desc.strip(),
                    'amount': amount,
                    'category': auto_categorize(desc, amount),
                })
    return transactions


def parse_generic_csv(filepath: Path) -> list:
    """Parse any CSV with common column names."""
    transactions = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = [h.lower() for h in (reader.fieldnames or [])]

        # Find the right columns
        date_col = next((h for h in reader.fieldnames or [] if h.lower() in
                         ['date', 'transaction date', 'txn date', 'posting date']), None)
        desc_col = next((h for h in reader.fieldnames or [] if h.lower() in
                         ['description', 'transaction description', 'memo', 'details', 'narration']), None)
        amount_col = next((h for h in reader.fieldnames or [] if h.lower() in
                           ['amount', 'txn amount', 'value']), None)
        debit_col = next((h for h in reader.fieldnames or [] if h.lower() in
                          ['debit', 'withdrawal', 'dr']), None)
        credit_col = next((h for h in reader.fieldnames or [] if h.lower() in
                           ['credit', 'deposit', 'cr']), None)

        if not date_col or not desc_col:
            print(f"ERROR: Can't detect columns. Found: {reader.fieldnames}")
            print("Expected: Date, Description, Amount (or Debit/Credit)")
            return []

        for row in reader:
            date = row.get(date_col, '')
            desc = row.get(desc_col, '')

            if amount_col:
                try:
                    amount = float(row[amount_col].replace(',', '').replace('$', '').replace('RM', ''))
                except (ValueError, KeyError):
                    continue
            elif debit_col and credit_col:
                debit = row.get(debit_col, '').strip()
                credit = row.get(credit_col, '').strip()
                if credit:
                    amount = float(credit.replace(',', ''))
                elif debit:
                    amount = -float(debit.replace(',', ''))
                else:
                    continue
            else:
                continue

            if date and desc:
                transactions.append({
                    'date': parse_date(date),
                    'description': desc.strip(),
                    'amount': amount,
                    'category': auto_categorize(desc, amount),
                })
    return transactions


def parse_sheets_csv(filepath: Path) -> list:
    """Parse Google Sheets expense tracking export."""
    return parse_generic_csv(filepath)


# ── Wise API ─────────────────────────────────────────────────────────────────

def sync_wise(days: int = 30) -> list:
    """Sync from Wise (TransferWise) API."""
    if not requests:
        print("Install requests: pip install requests")
        return []

    config_file = CONFIG_DIR / "wise_config.json"
    token = os.environ.get('WISE_TOKEN', '')

    if config_file.exists():
        with open(config_file) as f:
            config = json.load(f)
            token = config.get('token', token)

    if not token:
        print("ERROR: No Wise API token found.")
        print("1. Go to https://wise.com/settings/api-tokens")
        print("2. Create a read-only token")
        print('3. Save to .config/wise_config.json: {"token": "YOUR_TOKEN"}')
        return []

    headers = {'Authorization': f'Bearer {token}'}

    # Get profiles
    resp = requests.get('https://api.wise.com/v1/profiles', headers=headers)
    resp.raise_for_status()
    profiles = resp.json()

    if not profiles:
        print("No Wise profiles found.")
        return []

    profile_id = profiles[0]['id']
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%dT00:00:00.000Z')
    until = datetime.now().strftime('%Y-%m-%dT23:59:59.999Z')

    # Get accounts
    resp = requests.get(
        f'https://api.wise.com/v4/profiles/{profile_id}/balances?types=STANDARD',
        headers=headers
    )
    resp.raise_for_status()
    accounts = resp.json()

    transactions = []
    for account in accounts:
        account_id = account['id']
        currency = account['currency']

        resp = requests.get(
            f'https://api.wise.com/v3/profiles/{profile_id}/borderless-accounts/{account_id}/statement.json',
            headers=headers,
            params={'currency': currency, 'intervalStart': since, 'intervalEnd': until}
        )
        if resp.status_code != 200:
            continue

        for txn in resp.json().get('transactions', []):
            transactions.append({
                'date': txn['date'][:10],
                'description': txn.get('details', {}).get('description', txn.get('referenceNumber', '')),
                'amount': txn['amount']['value'],
                'currency': txn['amount']['currency'],
                'category': auto_categorize(
                    txn.get('details', {}).get('description', ''),
                    txn['amount']['value']
                ),
                'source': 'wise',
            })

    return transactions


# ── Utilities ────────────────────────────────────────────────────────────────

def parse_date(date_str: str) -> str:
    """Try multiple date formats and return YYYY-MM-DD."""
    formats = [
        '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y',
        '%d %b %Y', '%d %B %Y', '%Y%m%d', '%d.%m.%Y',
    ]
    date_str = date_str.strip()
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return date_str  # Return as-is if can't parse


def save_transactions(transactions: list, source: str):
    """Save transactions to raw storage and finance log."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Save raw
    raw_file = RAW_DIR / f"{source}_{datetime.now().strftime('%Y%m%d')}.json"
    with open(raw_file, 'w') as f:
        json.dump(transactions, f, indent=2)

    # Save as YAML for Claude
    finance_dir = BASE_DIR / "life" / "finance"
    finance_dir.mkdir(parents=True, exist_ok=True)
    log_path = finance_dir / f"bank-{source}-data.yaml"

    header = (
        f"# Banking Data - {source}\n"
        f"# Last sync: {datetime.now().isoformat()}\n"
        f"# Transactions: {len(transactions)}\n\n"
        "transactions:\n"
    )

    yaml_entries = ""
    for txn in sorted(transactions, key=lambda x: x['date']):
        yaml_entries += f"  - date: \"{txn['date']}\"\n"
        yaml_entries += f"    amount: {txn['amount']}\n"
        yaml_entries += f"    category: \"{txn['category']}\"\n"
        desc = txn['description'].replace('"', "'")
        yaml_entries += f"    description: \"{desc}\"\n"
        if 'currency' in txn:
            yaml_entries += f"    currency: \"{txn['currency']}\"\n"
        yaml_entries += "\n"

    log_path.write_text(header + yaml_entries, encoding='utf-8')

    # Summary
    income = sum(t['amount'] for t in transactions if t['amount'] > 0)
    expenses = sum(t['amount'] for t in transactions if t['amount'] < 0)
    print(f"\n  Transactions: {len(transactions)}")
    print(f"  Income:   +{income:.2f}")
    print(f"  Expenses: {expenses:.2f}")
    print(f"  Net:      {income + expenses:.2f}")
    print(f"\n  Raw: {raw_file}")
    print(f"  Log: {log_path}")


# ── Main ─────────────────────────────────────────────────────────────────────

BANK_PARSERS = {
    'maybank': parse_maybank_csv,
    'cimb': parse_cimb_csv,
    'generic': parse_generic_csv,
    'sheets': parse_sheets_csv,
}


def main():
    parser = argparse.ArgumentParser(description="Sync banking data → Life OS")
    parser.add_argument('--input', '-i', help='Path to bank CSV statement')
    parser.add_argument('--bank', choices=list(BANK_PARSERS.keys()) + ['wise'],
                        default='generic', help='Bank format')
    parser.add_argument('--source', help='Data source for Wise API')
    parser.add_argument('--days', type=int, default=30, help='Days back for API sync')
    args = parser.parse_args()

    if args.bank == 'wise' or args.source == 'wise':
        print("Syncing from Wise API...")
        transactions = sync_wise(args.days)
        if transactions:
            save_transactions(transactions, 'wise')
    elif args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"ERROR: {args.input} not found")
            sys.exit(1)

        print(f"Parsing {args.bank} CSV: {input_path.name}")
        parse_fn = BANK_PARSERS[args.bank]
        transactions = parse_fn(input_path)
        if transactions:
            save_transactions(transactions, args.bank)
        else:
            print("No transactions found. Check file format.")
    else:
        print("ERROR: Provide --input (CSV path) or --bank wise")
        sys.exit(1)

    print("\nBanking sync complete!")


if __name__ == '__main__':
    main()
