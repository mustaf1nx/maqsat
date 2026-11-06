"""Create the first admin securely without a publicly accessible registration form."""
import argparse
import getpass
from sqlalchemy import select
from .db import SessionLocal
from .models import User
from .security import USERNAME_RE, hash_password

def main():
    p = argparse.ArgumentParser(description='MAQSAT account management')
    p.add_argument('command', choices=['create-admin'])
    p.add_argument('--username', required=True)
    p.add_argument('--name', default='Administrator')
    args = p.parse_args()
    username = args.username.strip().lower()
    if not USERNAME_RE.fullmatch(username):
        p.error('Username: 3-32 lowercase Latin letters, digits, _ or -')
    password = getpass.getpass('New password (10+ characters): ')
    confirm = getpass.getpass('Repeat password: ')
    if password != confirm:
        p.error('Passwords do not match')
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == username)):
            p.error('Username already exists')
        db.add(User(username=username, display_name=args.name, password_hash=hash_password(password), is_admin=True))
        db.commit()
    print(f'Admin {username} created. Do not share credentials.')

if __name__ == '__main__': main()
