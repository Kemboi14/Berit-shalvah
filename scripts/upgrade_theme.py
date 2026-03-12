import sys
import xmlrpc.client

url = "http://localhost:8069"
db = "berit_odoo"
username = "admin"
password = "admin"

print(f"Connecting to {url} ...")

common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
try:
    uid = common.authenticate(db, username, password, {})
    if not uid:
        print("ERROR: Authentication failed. Check username/password.")
        sys.exit(1)
    print(f"Authenticated as UID: {uid}")
except Exception as e:
    print(f"ERROR connecting to Odoo: {e}")
    sys.exit(1)

models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

# Find the berit_theme module record
print("\n=== Looking up berit_theme ===")
try:
    result = models.execute_kw(
        db,
        uid,
        password,
        "ir.module.module",
        "search_read",
        [[["name", "=", "berit_theme"]]],
        {"fields": ["name", "state", "latest_version"], "limit": 1},
    )
    if not result:
        print("ERROR: berit_theme not found in ir.module.module.")
        print("Run check_theme.py first to register and install it.")
        sys.exit(1)

    r = result[0]
    module_id = r["id"]
    print(
        f"  Found: id={module_id}  state={r['state']}  version={r.get('latest_version', 'n/a')}"
    )
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

# Mark module as 'to upgrade'
print("\n=== Marking berit_theme for upgrade ===")
try:
    models.execute_kw(
        db,
        uid,
        password,
        "ir.module.module",
        "button_upgrade",
        [[module_id]],
    )
    print("  button_upgrade() called — module queued for upgrade.")
except Exception as e:
    print(f"  button_upgrade() error: {e}")
    sys.exit(1)

# Apply the upgrade immediately
print("\n=== Applying upgrade immediately ===")
try:
    models.execute_kw(
        db,
        uid,
        password,
        "base.module.upgrade",
        "upgrade_module",
        [[]],
    )
    print("  upgrade_module() completed successfully!")
except Exception as e:
    # Some Odoo versions don't expose base.module.upgrade via RPC.
    # Fall back to button_immediate_upgrade on the module itself.
    print(
        f"  upgrade_module() not available ({e}), trying button_immediate_upgrade ..."
    )
    try:
        models.execute_kw(
            db,
            uid,
            password,
            "ir.module.module",
            "button_immediate_upgrade",
            [[module_id]],
        )
        print("  button_immediate_upgrade() completed successfully!")
    except Exception as e2:
        print(f"  button_immediate_upgrade() error: {e2}")
        print(
            "\n  Could not trigger upgrade via RPC. "
            "Please restart Odoo and update the module manually:\n"
            "  Apps → search 'Berit Shalvah Theme' → Upgrade"
        )
        sys.exit(1)

# Confirm final state
print("\n=== Final module state ===")
try:
    final = models.execute_kw(
        db,
        uid,
        password,
        "ir.module.module",
        "search_read",
        [[["name", "=", "berit_theme"]]],
        {"fields": ["name", "state", "latest_version"], "limit": 1},
    )
    if final:
        r = final[0]
        print(
            f"  name={r['name']}  state={r['state']}  version={r.get('latest_version', 'n/a')}"
        )
        if r["state"] == "installed":
            print("\n  Theme upgraded successfully!")
            print("  Hard-refresh your browser (Ctrl+Shift+R) to load the new CSS.")
    else:
        print("  Could not read final state.")
except Exception as e:
    print(f"  Error reading final state: {e}")
