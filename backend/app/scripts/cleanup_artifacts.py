"""Retry a bounded batch of committed successful submission artifacts."""
import argparse
import logging

from app.services.artifact_cleanup import cleanup_successful_artifacts
from app.storage import LocalArtifactStorage


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    logging.basicConfig(level=logging.INFO)
    count = cleanup_successful_artifacts(storage=LocalArtifactStorage(), limit=args.limit)
    logging.info("Artifact cleanup completed: deleted=%s", count)


if __name__ == "__main__":
    main()
