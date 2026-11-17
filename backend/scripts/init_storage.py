"""Create the media bucket if it doesn't exist (idempotent; retries while storage boots).

    python -m scripts.init_storage
"""

import sys
import time

from botocore.exceptions import BotoCoreError, ClientError

from app.core import storage
from app.core.config import settings


def main(attempts: int = 30) -> int:
    for i in range(1, attempts + 1):
        try:
            storage.ensure_bucket()
            print(f"bucket '{settings.S3_BUCKET}' ready at {settings.S3_ENDPOINT_URL}")
            return 0
        except (BotoCoreError, ClientError) as exc:
            print(f"storage not ready ({i}/{attempts}): {exc}", file=sys.stderr)
            time.sleep(2)
    return 1


if __name__ == "__main__":
    sys.exit(main())
