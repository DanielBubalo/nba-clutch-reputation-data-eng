import json
import time
import requests
from paths import cached_data_dir

# Errors worth retrying: the NBA API timing out, dropping the connection,
# or returning a non-JSON page when it's throttling
RETRYABLE_ERRORS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    json.decoder.JSONDecodeError,
)


class ExtractionError(Exception):
    """Raised when API calls still fail after all retries."""


# Calls fetch(*args), retrying with exponential backoff (2s, 4s, 8s) on transient errors
def fetch_with_retry(fetch, *args, retries: int = 4, base_delay: float = 2.0):
    for attempt in range(1, retries + 1):
        try:
            return fetch(*args)
        except RETRYABLE_ERRORS as error:
            if attempt == retries:
                raise
            wait = base_delay * 2 ** (attempt - 1)
            print(
                f"Attempt {attempt} failed ({type(error).__name__}), retrying in {wait:.0f}s"
            )
            time.sleep(wait)


# Writes a failure manifest and stops the run if anything failed; clears old manifests on success
def raise_if_failures(failures: list, name: str) -> None:
    manifest_dir = cached_data_dir / "failures"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{name}.json"

    if not failures:
        manifest_path.unlink(missing_ok=True)
        return

    manifest_path.write_text(json.dumps(failures, indent=2))
    raise ExtractionError(
        f"{len(failures)} {name} calls failed after retries. "
        f"See {manifest_path}. Rerun to retry the failed calls."
    )
