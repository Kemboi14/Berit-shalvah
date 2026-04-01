# Odoo Model Fixes Summary

## Issues Fixed

### 1. `interest_rate` field — Required Computed Field Error
**File:** `odoo/addons/berit_loan/models/loan_application.py` (line 54-62)

**Problem:**
- Field was declared as `required=True` AND `compute="_compute_interest_rate"` with `store=True`
- Computed+stored fields should NEVER be `required` because they are auto-populated
- When `loan_amount` is `0` or unset, the compute returns `0.0`, which is falsy in Python
- Odoo's ORM treats falsy values as "missing" and rejects the record with: *"Missing required value for Interest Rate (%)"*

**Solution:**
Removed `required=True` from the field definition. The field is auto-computed and always has a value (≥0).

**Before:**
```python
interest_rate = fields.Float(
    string="Interest Rate (%)",
    required=True,  # ← REMOVED
    compute="_compute_interest_rate",
    store=True,
    tracking=True,
)
```

**After:**
```python
interest_rate = fields.Float(
    string="Interest Rate (%)",
    compute="_compute_interest_rate",
    store=True,
    tracking=True,
    help="Auto-computed from loan amount tier. 20% for ≤99k, down to 5% for >1M.",
)
```

---

### 2. `total_due` field — Required Computed Field Error
**File:** `odoo/addons/berit_loan/models/repayment_schedule.py` (line 22-28)

**Problem:**
Same as issue #1: `required=True` on a computed+stored field caused false "missing value" errors.

**Solution:**
Removed `required=True`. The field is always computed as `principal_amount + interest_amount`.

**Before:**
```python
total_due = fields.Float(
    string="Total Due (KES)",
    required=True,  # ← REMOVED
    compute="_compute_total_due",
    store=True,
)
```

**After:**
```python
total_due = fields.Float(
    string="Total Due (KES)",
    compute="_compute_total_due",
    store=True,
    help="Auto-computed as principal + interest. Never set this manually.",
)
```

---

### 3. `_compute_days_overdue` — TypeError on Date Comparison
**File:** `odoo/addons/berit_loan/models/repayment_schedule.py` (line 73-93)

**Problem:**
- During onchange evaluation, unset Date fields return `False` (not `None`)
- Code attempted `False < datetime.date`, causing: *TypeError: '<' not supported between instances of 'bool' and 'datetime.date'*
- This error occurred when creating a new repayment schedule before `due_date` was filled in

**Solution:**
Added a truthiness guard on `schedule.due_date` before the date comparison.

**Before:**
```python
@api.depends("due_date", "status", "amount_paid")
def _compute_days_overdue(self):
    """Compute days overdue"""
    today = fields.Date.today()
    for schedule in self:
        if schedule.status == "pending" and schedule.due_date < today:  # ← crashes if due_date is False
            schedule.days_overdue = (today - schedule.due_date).days
        else:
            schedule.days_overdue = 0
```

**After:**
```python
@api.depends("due_date", "status", "amount_paid")
def _compute_days_overdue(self):
    """Compute days overdue.

    ``due_date`` is a stored Date field, but during onchange evaluation
    Odoo may call this compute before the field is populated — in that
    case the field value is ``False`` (not ``None``).  Guard against that
    so we never attempt a ``False < date`` comparison.
    """
    today = fields.Date.today()
    for schedule in self:
        if (
            schedule.due_date  # ← Guard prevents False comparison
            and schedule.status == "pending"
            and schedule.due_date < today
        ):
            schedule.days_overdue = (today - schedule.due_date).days
        else:
            schedule.days_overdue = 0
```

---

## How to Apply These Fixes

### Option 1: Automatic (Recommended)
The changes have already been applied to the source files. To load them into Odoo:

1. **Stop Odoo:**
   ```bash
   pkill -9 -f odoo-bin
   sleep 2
   ```

2. **Clear Python bytecode cache:**
   ```bash
   find odoo/addons/berit_loan -name '*.pyc' -delete
   find odoo/addons/berit_loan -name '__pycache__' -type d -exec rm -rf {} +
   ```

3. **Restart Odoo with module update:**
   ```bash
   cd /home/nick/berit-shalvah
   source odoo_env/bin/activate
   python -m odoo.bin --config=odoo/odoo.conf --db-filter=^berit_odoo$ --gevent-port=8072 -u berit_loan --workers=4
   ```

   The `-u berit_loan` flag forces Odoo to reload the `berit_loan` module and re-sync all field definitions from the Python code.

4. **Wait for initialization** (2-3 minutes), then verify the fixes are active via the web UI.

### Option 2: Manual via RPC
If you prefer not to restart Odoo, you can attempt an RPC upgrade (though Python code changes may not reload):

```bash
source odoo_env/bin/activate
python scripts/upgrade_theme.py  # Reuse the same pattern for berit_loan
```

However, **this will not reload Python code**. The bytecode-cached old code will still run. A full Odoo restart is necessary to pick up Python changes.

---

## Testing the Fixes

After restarting Odoo:

1. **Create a new loan application:**
   - Open **Loan > Loan Applications > New**
   - Fill in: Applicant, Loan Amount (e.g., 50,000), Duration (e.g., 6 months)
   - The **Interest Rate (%)** should auto-populate without errors (e.g., 20%)

2. **Create a repayment schedule:**
   - Open a loan and navigate to the **Repayment** tab
   - Click **New** to add a repayment record
   - As you fill in fields, **Days Overdue** should compute without crashing

3. **Check Odoo logs** for any SCSS or other errors:
   ```bash
   tail -f logs/odoo.log
   ```

---

## Key Takeaways

- **Never use `required=True` on computed+stored fields.** The compute method is what populates the value.
- **Always guard Date field comparisons** with a truthiness check when the field might be unset (`False` in Odoo).
- **Python code changes require an Odoo restart**, not just an RPC module upgrade. Use `-u module_name` flag.
- **Clear bytecode cache** (`*.pyc`, `__pycache__`) before restarting to ensure fresh imports.

---

## Related Files Modified

- `odoo/addons/berit_loan/models/loan_application.py` — removed `required=True` from `interest_rate`
- `odoo/addons/berit_loan/models/repayment_schedule.py` — removed `required=True` from `total_due`, added guard in `_compute_days_overdue`
- `django_portal/templates/accounts/login.html` — removed broken password reset links
