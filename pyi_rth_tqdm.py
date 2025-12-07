"""PyInstaller runtime hook for tqdm library.

This hook patches tqdm.contrib.concurrent.ensure_lock to handle the 'disabled_tqdm'
class that huggingface_hub uses. In frozen applications, this class causes an
AttributeError because it lacks the expected _lock attribute handling.
"""

import sys

# Only apply patch when running in PyInstaller bundle
if hasattr(sys, '_MEIPASS'):
    try:
        # Import the module to patch
        import tqdm.contrib.concurrent
        import threading
        
        # Debug output to verify hook execution
        # print("DEBUG: PyInstaller runtime hook for tqdm starting...", file=sys.stderr)
        
        _orig_ensure_lock = tqdm.contrib.concurrent.ensure_lock

        def _patched_ensure_lock(tqdm_class, lock_name="_lock"):
            """
            Patched ensure_lock that handles the 'disabled_tqdm' class.
            
            When huggingface_hub disables progress bars (often in frozen apps),
            it uses a disabled_tqdm class that causes crashes in ensure_lock
            because it doesn't support the lock attribute operations.
            """
            # Handle the special disabled_tqdm class
            if getattr(tqdm_class, "__name__", "") == "disabled_tqdm":
                # Return a fresh lock. Since the progress bar is disabled,
                # strict locking semantics across threads are likely not critical,
                # but we need to return a valid context manager (Lock object).
                return threading.Lock()
            
            return _orig_ensure_lock(tqdm_class, lock_name)

        tqdm.contrib.concurrent.ensure_lock = _patched_ensure_lock
        # print("DEBUG: Successfully patched tqdm.contrib.concurrent.ensure_lock", file=sys.stderr)
        
    except ImportError:
        # tqdm might not be present or used, which is fine
        pass
    except Exception as e:
        print(f"Warning: Failed to patch tqdm runtime hook: {e}", file=sys.stderr)
