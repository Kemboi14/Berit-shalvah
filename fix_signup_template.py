import os
import re

TEMPLATES_DIR = "django_portal/templates"


def fix_template_file(path):
    with open(path, "r") as f:
        content = f.read()

    original = content

    # Fix broken {{ ... }} tags split across lines
    # Pattern: {{ ... <newline> ... }} — join them onto one line
    content = re.sub(
        r"\{\{([^}]*)\n(\s*)([^}]*)\}\}",
        lambda m: "{{ " + (m.group(1) + " " + m.group(3)).strip() + " }}",
        content,
    )

    # Fix broken {% ... %} tags split across lines
    # Pattern: {% ... <newline> ... %} — join them onto one line
    content = re.sub(
        r"\{%([^%]*)\n(\s*)([^%]*?)%\}",
        lambda m: "{% " + (m.group(1) + " " + m.group(3)).strip() + " %}",
        content,
    )

    # Run a second pass — some may need two rounds
    content = re.sub(
        r"\{\{([^}]*)\n(\s*)([^}]*)\}\}",
        lambda m: "{{ " + (m.group(1) + " " + m.group(3)).strip() + " }}",
        content,
    )
    content = re.sub(
        r"\{%([^%]*)\n(\s*)([^%]*?)%\}",
        lambda m: "{% " + (m.group(1) + " " + m.group(3)).strip() + " %}",
        content,
    )

    if content != original:
        with open(path, "w") as f:
            f.write(content)
        return True
    return False


def verify_file(path):
    with open(path, "r") as f:
        content = f.read()
    broken_var = re.findall(r"\{\{[^}]*$", content, re.MULTILINE)
    broken_tag = re.findall(r"\{%[^%]*$", content, re.MULTILINE)
    return broken_var, broken_tag


changed = []
clean = []
errors = []

for root, dirs, files in os.walk(TEMPLATES_DIR):
    # Skip __pycache__ etc.
    dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
    for fname in files:
        if not fname.endswith(".html"):
            continue
        fpath = os.path.join(root, fname)
        try:
            was_fixed = fix_template_file(fpath)
            broken_vars, broken_tags = verify_file(fpath)
            rel = os.path.relpath(fpath, TEMPLATES_DIR)
            if broken_vars or broken_tags:
                errors.append((rel, broken_vars, broken_tags))
            elif was_fixed:
                changed.append(rel)
            else:
                clean.append(rel)
        except Exception as e:
            errors.append((fpath, [str(e)], []))

print(f"\n{'=' * 60}")
print(f"FIXED ({len(changed)} files):")
for f in changed:
    print(f"  ✓ {f}")

print(f"\nALREADY CLEAN ({len(clean)} files):")
for f in clean:
    print(f"  - {f}")

if errors:
    print(f"\nSTILL BROKEN ({len(errors)} files):")
    for f, bv, bt in errors:
        print(f"  ✗ {f}")
        for x in bv:
            print(f"      broken {{{{: {x!r:.80}")
        for x in bt:
            print(f"      broken {{%: {x!r:.80}")
else:
    print(f"\n✅ All templates are clean — no broken multi-line tags remaining.")

print(f"{'=' * 60}\n")
