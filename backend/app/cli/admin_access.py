import argparse
import secrets
import sys

from app.core.constants import UserRole
from app.db.session import SessionLocal
from app.models.user import User
from app.services.social_gate import create_admin_bootstrap_invite
from sqlalchemy import func


def count_admins() -> int:
    with SessionLocal() as session:
        return int(session.query(func.count(User.id)).filter(User.role == UserRole.ADMIN, User.is_active.is_(True)).scalar() or 0)


def create_bootstrap_invite(*, note: str, force: bool) -> str:
    with SessionLocal() as session:
        admin_count = int(session.query(func.count(User.id)).filter(User.role == UserRole.ADMIN, User.is_active.is_(True)).scalar() or 0)
        if admin_count > 0 and not force:
            raise RuntimeError("Active admin account already exists. Refusing bootstrap invite.")

        invite = create_admin_bootstrap_invite(
            session,
            note=note,
            invite_quota=50,
        )
        session.commit()
        session.refresh(invite)
        return invite.code


def main() -> int:
    parser = argparse.ArgumentParser(description="NextBoo admin access helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap-invite", help="Create first admin invite when no admin exists")
    bootstrap_parser.add_argument("--note", default="Initial bootstrap admin invite")

    rescue_parser = subparsers.add_parser("rescue-invite", help="Create emergency admin invite")
    rescue_parser.add_argument("--note", default="Rescue admin invite")
    rescue_parser.add_argument("--force", action="store_true")

    count_parser = subparsers.add_parser("count-admins", help="Print active admin count")
    count_parser.add_argument("--plain", action="store_true")

    args = parser.parse_args()

    try:
        if args.command == "count-admins":
            total = count_admins()
            print(total if args.plain else f"active_admins={total}")
            return 0

        if args.command == "bootstrap-invite":
            code = create_bootstrap_invite(note=args.note, force=False)
            print(code)
            return 0

        if args.command == "rescue-invite":
            if not args.force:
                raise RuntimeError("Rescue invite requires --force")
            note = f"{args.note} #{secrets.token_hex(4)}"
            code = create_bootstrap_invite(note=note, force=True)
            print(code)
            return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
