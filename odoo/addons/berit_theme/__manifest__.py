# -*- coding: utf-8 -*-
{
    "name": "Berit Shalvah Theme",
    "version": "1.3",
    "category": "Themes/Backend",
    "summary": "Custom backend theme matching the Berit Shalvah Django portal UI",
    "description": """
Berit Shalvah Financial Services — Custom Odoo 19 Backend Theme
===============================================================

Matches the brand identity of the Django client portal.

Colours
-------
  Navy   #1B3A6B  primary
  Blue   #2E6DA4  secondary / links
  Gold   #F5A623  accent
  Teal   #0D9488  success
  Red    #DC2626  danger
  Amber  #D97706  warning

NOTE (Odoo 19 compatibility)
----------------------------
In Odoo 19 the SCSS compilation pipeline loads helpers (functions, mixins,
o-to-rem, etc.) AFTER web._assets_primary_variables.  Injecting anything into
_assets_primary_variables that references those helpers — or that overrides
variables used in Bootstrap arithmetic — causes layout distortion or SCSS
compile errors.

Therefore this theme does NOT touch _assets_primary_variables at all.
All styling is applied via a plain CSS file appended to web.assets_backend,
which runs after the full SCSS bundle has already been compiled and cannot
interfere with any layout calculations.
""",
    "author": "Berit Shalvah Financial Services Ltd",
    "website": "https://beritshalvah.co.ke",
    "license": "LGPL-3",
    "depends": ["web"],
    "assets": {
        # Append plain CSS to the backend bundle.
        # This runs after Odoo's compiled SCSS so our colour rules win
        # via normal CSS cascade (or !important where needed), without
        # ever touching the SCSS compile step.
        "web.assets_backend": [
            "berit_theme/static/src/css/berit_theme.css",
        ],
    },
    "installable": True,
    "auto_install": False,
    "application": False,
}
