"""
set_dashboard_password.py

Run this once (and any time you want to change the dashboard login) to set
the owner username/password for the web dashboard.

    python set_dashboard_password.py

It writes DASHBOARD_USERNAME and DASHBOARD_PASSWORD_HASH into your .env file.
The plaintext password is never stored anywhere - only a bcrypt hash is.
"""
import getpass
import os
import re
import sys

try:
    import bcrypt
except ImportError:
    print("bcrypt is not installed. Run: pip install bcrypt --break-system-packages")
    sys.exit(1)

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def read_env_lines():
    if not os.path.exists(ENV_PATH):
        return []
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        return f.readlines()


def write_env_value(lines, key, value):
    pattern = re.compile(rf"^{re.escape(key)}\s*=")
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f"{key}={value}\n"
            return lines
    lines.append(f"{key}={value}\n")
    return lines


def main():
    print("=== Discord Bot Dashboard - set owner credentials ===\n")

    username = input("Dashboard username [admin]: ").strip() or "admin"

    while True:
        password = getpass.getpass("Dashboard password (min 8 chars): ")
        if len(password) < 8:
            print("Password must be at least 8 characters. Try again.\n")
            continue
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords did not match. Try again.\n")
            continue
        break

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    lines = read_env_lines()
    lines = write_env_value(lines, "DASHBOARD_USERNAME", username)
    # bcrypt hashes contain '$' which is fine in .env values as long as unquoted
    lines = write_env_value(lines, "DASHBOARD_PASSWORD_HASH", hashed)

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"\nSaved. Dashboard username set to '{username}'.")
    print("Start the bot with DASHBOARD_ENABLED=true in .env, then log in at")
    print("http://127.0.0.1:5000 (or whatever DASHBOARD_HOST/PORT you set).")


if __name__ == "__main__":
    main()
