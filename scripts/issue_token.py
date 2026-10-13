"""Issues a JWT for a seeded user. Local/test environments only: there is no login endpoint.

Usage: python scripts/issue_token.py cliente1988 [--role merchant] [--ttl 3600]
"""

import argparse
import sys

from app.api.auth import ROLES, create_token
from app.core.config import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("user_id")
    parser.add_argument("--role", choices=ROLES, default="merchant")
    parser.add_argument("--ttl", type=int, default=3600)
    args = parser.parse_args()
    if get_settings().app_env == "production":
        print("issue_token is disabled in production", file=sys.stderr)
        return 1
    print(create_token(args.user_id, args.role, args.ttl))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
