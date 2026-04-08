#!/usr/bin/env python3
"""
Finance Processor - Reads raw vault data → writes to life/finance/

Reads bank CSVs and transaction data from the vault, auto-categorizes,
and writes unified finance logs for Claude.

Usage:
    python processors/process_finance.py
    python processors/process_finance.py --month 2026-04
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VAULT_DIR = BASE_DIR / "vault" / "banking"
OUTPUT_DIR = BASE_DIR / "life" / "finance"

# ── Category Rules ───────────────────────────────────────────────────────────

CATEGORY_RULES = {
    'food': [
        'grab food', 'foodpanda', 'shopee food', 'restaurant', 'cafe', 'coffee',
        'starbucks', 'mcdonald', 'kfc', 'pizza', 'sushi', 'nasi',
        'grocery', 'jaya grocer', 'village grocer', 'cold storage',
        'tesco', 'aeon', 'mydin', 'baker',
    ],
    'transport': [
        'grab', 'gojek', 'mrt', 'lrt', 'rapidkl', 'parking',
        'petronas', 'shell', 'petron', 'fuel', 'petrol',
        'toll', 'touch n go', 'tng', 'smart tag',
    ],
    'housing': ['rent', 'rental', 'mortgage', 'condo'],
    'utilities': [
        'tenaga', 'tnb', 'air selangor', 'indah water', 'unifi', 'maxis',
        'digi', 'celcom', 'umobile', 'time', 'electric', 'internet', 'phone',
    ],
    'subscriptions': [
        'netflix', 'spotify', 'youtube', 'disney', 'apple', 'google storage',
        'claude', 'chatgpt', 'notion', 'figma', 'github', 'adobe', 'canva',
        'toggl', 'hbo', 'amazon prime',
    ],
    'health': [
        'pharmacy', 'doctor', 'clinic', 'hospital', 'dental', 'guardian',
        'watson', 'gym', 'fitness', 'supplement',
    ],
    'entertainment': ['cinema', 'gsc', 'tgv', 'movie', 'concert', 'game', 'steam'],
    'shopping': ['shopee', 'lazada', 'zalora', 'uniqlo', 'h&m', 'ikea', 'mr diy', 'amazon'],
    'education': ['udemy', 'coursera', 'book', 'kindle', 'course'],
    'transfer': ['transfer', 'duitnow', 'ibg'],
    'income': ['salary', 'payroll', 'commission', 'bonus', 'dividend', 'refund', 'cashback'],
}


def auto_categorize(description: str, amount: float) -> str:
    desc_lower = description.lower()
    if amount > 0:
        for keyword in CATEGORY_RULES['income']:
            if keyword in desc_lower:
                return 'income'
        return 'income'
    for category, keywords in CATEGORY_RULES.items():
        if category == 'income':
            continue
        for keyword in keywords:
            if keyword in desc_lower:
                return category
    return 'misc'


def parse_date(date_str: str) -> str:
    formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%d %b %Y', '%d.%m.%Y']
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return date_str.strip()


# ── Load from Vault ──────────────────────────────────────────────────────────

def load_vault_transactions() -> list:
    """Load all transaction data from vault/banking/."""
    if not VAULT_DIR.exists():
        return []

    transactions = []

    # Load JSON files (from API syncs)
    for f in VAULT_DIR.glob('*.json'):
        with open(f) as fh:
            data = json.load(fh)
            if isinstance(data, list):
                transactions.extend(data)

    # Load CSV files (bank statements)
    for f in VAULT_DIR.glob('*.csv'):
        with open(f, 'r', encoding='utf-8-sig') as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                continue

            headers = {h.lower(): h for h in reader.fieldnames}

            date_col = next((headers[h] for h in ['date', 'transaction date', 'txn date', 'posting date']
                            if h in headers), None)
            desc_col = next((headers[h] for h in ['description', 'transaction description', 'memo', 'details', 'narration']
                            if h in headers), None)
            amount_col = next((headers[h] for h in ['amount', 'txn amount', 'value']
                              if h in headers), None)
            debit_col = next((headers[h] for h in ['debit', 'withdrawal', 'dr']
                             if h in headers), None)
            credit_col = next((headers[h] for h in ['credit', 'deposit', 'cr']
                              if h in headers), None)

            if not date_col or not desc_col:
                continue

            for row in reader:
                date = parse_date(row.get(date_col, ''))
                desc = row.get(desc_col, '').strip()

                if amount_col:
                    try:
                        amount = float(row[amount_col].replace(',', '').replace('RM', '').replace('$', ''))
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

                transactions.append({
                    'date': date,
                    'description': desc,
                    'amount': amount,
                    'category': auto_categorize(desc, amount),
                    'source': f.stem,
                })

    return transactions


# ── Output ───────────────────────────────────────────────────────────────────

def write_finance_log(transactions: list, month_filter: str = None):
    """Write processed transactions to life/finance/."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if month_filter:
        transactions = [t for t in transactions if t['date'].startswith(month_filter)]

    # Sort by date
    transactions.sort(key=lambda x: x['date'])

    # Group by month
    by_month = defaultdict(list)
    for t in transactions:
        month = t['date'][:7]
        by_month[month].append(t)

    # Write per-month files
    for month, txns in by_month.items():
        income = sum(t['amount'] for t in txns if t['amount'] > 0)
        expenses = sum(t['amount'] for t in txns if t['amount'] < 0)

        by_category = defaultdict(float)
        for t in txns:
            if t['amount'] < 0:
                by_category[t['category']] += abs(t['amount'])

        filepath = OUTPUT_DIR / f"transactions-{month}.yaml"
        lines = [
            f"# Transactions - {month}\n",
            f"# Processed: {datetime.now().isoformat()}\n",
            f"# Source: vault/banking/\n\n",
            f"month: \"{month}\"\n",
            f"income: {income:.2f}\n",
            f"expenses: {expenses:.2f}\n",
            f"net: {income + expenses:.2f}\n\n",
            "by_category:\n",
        ]
        for cat, total in sorted(by_category.items(), key=lambda x: -x[1]):
            lines.append(f"  {cat}: {total:.2f}\n")

        lines.append(f"\ntransactions:\n")
        for t in txns:
            desc = t['description'].replace('"', "'")
            lines.append(f"  - date: \"{t['date']}\"\n")
            lines.append(f"    amount: {t['amount']:.2f}\n")
            lines.append(f"    category: \"{t['category']}\"\n")
            lines.append(f"    description: \"{desc}\"\n")
            lines.append(f"\n")

        filepath.write_text(''.join(lines), encoding='utf-8')
        print(f"  {month}: {len(txns)} transactions, income={income:.0f}, expenses={expenses:.0f}")

    print(f"\n  Total: {len(transactions)} transactions across {len(by_month)} months")


def main():
    parser = argparse.ArgumentParser(description="Process vault banking data → life/finance/")
    parser.add_argument('--month', '-m', help='Filter to specific month (YYYY-MM)')
    args = parser.parse_args()

    print("Processing finance data from vault...")
    transactions = load_vault_transactions()
    if not transactions:
        print("  No transaction data found in vault/banking/")
        print("  Drop your bank CSV files there or run sync/banking/sync_banking.py")
        return

    write_finance_log(transactions, month_filter=args.month)
    print("\nFinance processing complete!")


if __name__ == '__main__':
    main()
