"""
Sample buggy Python file for testing the CodeReview AI static analyzer.
This file intentionally contains multiple issues across all rule categories.
DO NOT fix these — they exist for demonstration purposes.
"""

import os
import json

# Rule 1: Hardcoded secret
api_key = "sk-proj-abc123def456ghi789jkl012mno345pqr678stu"
database_password = "MyS3cureP@ssw0rd!2024"

# Rule 2: SQL injection
def get_user(user_id):
    import sqlite3
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
    return cursor.fetchone()

# Rule 3: Unused variable
def calculate_total(items):
    subtotal = sum(items)
    tax_rate = 0.08  # This is never used
    discount = 0  # This is also never used
    return subtotal

# Rule 4: Bare/broad exception handling
def risky_operation():
    try:
        result = 1 / 0
    except:
        pass

def another_risky():
    try:
        data = json.loads("{invalid}")
    except Exception:
        pass

# Rule 5: Missing null check
def process_response(data):
    value = data.get("result")
    # Oops — value could be None if "result" key is missing
    print(value.strip())

# Rule 6: Potential infinite loop
def bad_worker():
    while True:
        print("Working...")
        # No break, return, or exit — this runs forever

# Rule 7: Mutable default argument
def append_item(item, items=[]):
    items.append(item)
    return items

def track_events(event, log={}):
    log[event] = True
    return log

# Rule 8: Inconsistent naming conventions
def get_user_name():
    return "Alice"

def getUserAge():
    return 30

def calculate_total_price():
    return 99.99

def formatOutputString():
    return "formatted"
