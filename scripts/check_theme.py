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

# First, discover available fields on ir.module.module
print("\n=== Available fields on ir.module.module ===")
try:
    fields_info = models.execute_kw(
        db,
        uid,
        password,
        "ir.module.module",
        "fields_get",
        [],
        {"attributes": ["string", "type"]},
    )
    relevant = {
        k: v
        for k, v in fields_info.items()
        if any(
            x in k
            for x in ["state", "name", "install", "summary", "version", "category"]
        )
    }
    for k, v in sorted(relevant.items()):
        print(f"  {k}: {v['type']} ({v['string']})")
except Exception as e:
    print(f"  Could not get fields: {e}")

# Search for ALL berit modules using safe fields
print("\n=== All 'berit' modules in DB ===")
try:
    result = models.execute_kw(
        db,
        uid,
        password,
        "ir.module.module",
        "search_read",
        [[["name", "like", "berit"]]],
        {"fields": ["name", "state", "summary", "latest_version"], "limit": 50},
    )
    if result:
        for r in result:
            print(
                f"  name={r['name']}  state={r['state']}  version={r.get('latest_version', '')}  summary={r.get('summary', '')}"
            )
    else:
        print("  (none found — berit_theme has NOT been scanned into the DB yet)")
except Exception as e:
    print(f"  Error: {e}")

# Check if berit_theme specifically exists
print("\n=== Looking for berit_theme specifically ===")
try:
    exact = models.execute_kw(
        db,
        uid,
        password,
        "ir.module.module",
        "search_read",
        [[["name", "=", "berit_theme"]]],
        {"fields": ["name", "state", "summary", "latest_version"], "limit": 1},
    )
    if exact:
        r = exact[0]
        print(f"  FOUND: state={r['state']}  version={r.get('latest_version', '')}")
    else:
        print("  NOT FOUND in ir.module.module — needs 'Update Apps List'")
except Exception as e:
    print(f"  Error: {e}")

# Trigger Update Apps List programmatically
print("\n=== Triggering 'Update Apps List' now ===")
try:
    models.execute_kw(db, uid, password, "ir.module.module", "update_list", [])
    print("  update_list() called successfully")
except Exception as e:
    print(f"  update_list() error: {e}")

# Check again after update
print("\n=== berit_theme after update_list ===")
try:
    exact2 = models.execute_kw(
        db,
        uid,
        password,
        "ir.module.module",
        "search_read",
        [[["name", "=", "berit_theme"]]],
        {"fields": ["name", "state", "summary", "latest_version"], "limit": 1},
    )
    if exact2:
        r = exact2[0]
        print(f"  FOUND: state={r['state']}  version={r.get('latest_version', '')}")
        if r["state"] == "uninstalled":
            print("\n  Module is ready. Attempting install now...")
            try:
                module_id = r["id"]
                models.execute_kw(
                    db,
                    uid,
                    password,
                    "ir.module.module",
                    "button_immediate_install",
                    [[module_id]],
                )
                print("  Install triggered successfully! Refresh your browser.")
            except Exception as e:
                print(f"  Install error: {e}")
        elif r["state"] == "installed":
            print("  Module is already installed!")
        else:
            print(f"  Module state is '{r['state']}' — may need manual action.")
    else:
        print("  STILL NOT FOUND after update_list.")
        print("  Odoo cannot see the berit_theme folder in its addons path.")
        print("  Verify that /home/nick/berit-shalvah/odoo/addons is listed in")
        print("  odoo.conf under addons_path AND that Odoo was restarted after")
        print("  the manifest was fixed.")
except Exception as e:
    print(f"  Error: {e}")

# Show ir.config_parameter web base url to confirm which Odoo we hit
print("\n=== Sanity check: web.base.url ===")
try:
    param = models.execute_kw(
        db,
        uid,
        password,
        "ir.config_parameter",
        "search_read",
        [[["key", "=", "web.base.url"]]],
        {"fields": ["key", "value"], "limit": 1},
    )
    if param:
        print(f"  {param[0]['key']} = {param[0]['value']}")
    else:
        print("  (not set)")
except Exception as e:
    print(f"  Could not read config params: {e}")
