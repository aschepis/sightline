"""PyInstaller runtime hook for tqdm library.

This hook patches tqdm.contrib.concurrent.ensure_lock to handle the 'disabled_tqdm'
class that huggingface_hub uses. In frozen applications, this class causes an
AttributeError because it lacks the expected _lock attribute handling.
"""

import sys

# Apply patch both in PyInstaller bundles and regular Python environments
# The disabled_tqdm issue can occur in both contexts
if True:  # Always apply the patch
    try:
        # Import the module to patch
        import tqdm.contrib.concurrent
        import threading
        from contextlib import contextmanager

        # Debug output to verify hook execution
        # print("DEBUG: PyInstaller runtime hook for tqdm starting...", file=sys.stderr)

        _orig_ensure_lock = tqdm.contrib.concurrent.ensure_lock

        @contextmanager
        def _patched_ensure_lock(tqdm_class, lock_name="_lock"):
            """
            Patched ensure_lock that handles the 'disabled_tqdm' class.

            When huggingface_hub disables progress bars (often in frozen apps),
            it uses a disabled_tqdm class that causes crashes in ensure_lock
            because it doesn't support the lock attribute operations.
            """
            # Handle the special disabled_tqdm class by name
            class_name = getattr(tqdm_class, "__name__", "")
            if class_name == "disabled_tqdm":
                # Create and yield a fresh lock. Since the progress bar is disabled,
                # strict locking semantics across threads are likely not critical,
                # but we need to return a valid context manager.
                lock = threading.Lock()
                lock.acquire()
                try:
                    yield lock
                finally:
                    lock.release()
                return

            # Also handle the case where the class doesn't have the _lock attribute
            # This can happen with disabled_tqdm or other custom tqdm classes
            if not hasattr(tqdm_class, lock_name):
                # If the class doesn't have the lock attribute, yield a fresh lock
                # This prevents AttributeError when ensure_lock tries to delete it
                lock = threading.Lock()
                lock.acquire()
                try:
                    yield lock
                finally:
                    lock.release()
                return

            # Try to call the original function, but catch AttributeError
            # in case it still fails (defensive programming)
            try:
                # The original ensure_lock is a context manager, so we delegate to it
                with _orig_ensure_lock(tqdm_class, lock_name) as lock:
                    yield lock
            except AttributeError as e:
                # If the original function fails with AttributeError (likely _lock missing),
                # yield a fresh lock as fallback
                if lock_name in str(e) or "_lock" in str(e):
                    lock = threading.Lock()
                    lock.acquire()
                    try:
                        yield lock
                    finally:
                        lock.release()
                else:
                    # Re-raise if it's a different AttributeError
                    raise

        tqdm.contrib.concurrent.ensure_lock = _patched_ensure_lock
        # print("DEBUG: Successfully patched tqdm.contrib.concurrent.ensure_lock", file=sys.stderr)

    except ImportError:
        # tqdm might not be present or used, which is fine
        pass
    except Exception as e:
        print(f"Warning: Failed to patch tqdm runtime hook: {e}", file=sys.stderr)
