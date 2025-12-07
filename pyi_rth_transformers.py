"""PyInstaller runtime hook for transformers library.

This hook patches the transformers.utils.auto_docstring module to handle
the case where file paths don't have the expected structure when running
in a PyInstaller bundle. The auto_docstring code tries to parse file paths
to determine model names, but PyInstaller changes the path structure.

We need to patch this at the lowest level possible - directly modifying
the source of the error before any transformers code runs.
"""

import sys
import os

# Only apply patch when running in PyInstaller bundle
if hasattr(sys, '_MEIPASS'):
    # Debug: Log that we're attempting the patch
    print("DEBUG: PyInstaller runtime hook for transformers starting...", file=sys.stderr)

    try:
        # Import the problematic module FIRST in this runtime hook
        # This ensures we can patch it before the main application imports it
        import transformers.utils.auto_docstring as auto_docstring

        print("DEBUG: Successfully imported transformers.utils.auto_docstring", file=sys.stderr)

        # Get the module's globals dictionary - this is where the function actually lives
        # when it's called with a bare name like get_model_name(func)
        module_globals = auto_docstring.__dict__

        # Store the original function
        _original_get_model_name = module_globals['get_model_name']

        print(f"DEBUG: Original get_model_name function: {_original_get_model_name}", file=sys.stderr)

        def patched_get_model_name(func):
            """Safely get model name, handling PyInstaller path structure issues."""
            try:
                # Get the file path
                if hasattr(func, '__code__'):
                    path = func.__code__.co_filename
                elif hasattr(func, '__func__'):
                    path = func.__func__.__code__.co_filename
                else:
                    return ""

                # In PyInstaller, paths may not have the expected structure
                # Safely check if we have enough path components
                parts = path.split(os.path.sep)

                # Original code expects at least 4 components to access [-3]
                if len(parts) < 4:
                    return ""

                # Now call original function - it should work or we catch the error
                return _original_get_model_name(func)

            except (IndexError, AttributeError, KeyError, ValueError) as e:
                # If anything goes wrong, return empty string
                # This is safe because this function is only used for docstring generation
                return ""

        # Patch it in the module's globals dict - this is crucial for bare name lookups
        module_globals['get_model_name'] = patched_get_model_name

        # Also patch it as a module attribute for good measure
        auto_docstring.get_model_name = patched_get_model_name

        # Ensure sys.modules has the patched version too
        if 'transformers.utils.auto_docstring' in sys.modules:
            sys.modules['transformers.utils.auto_docstring'].__dict__['get_model_name'] = patched_get_model_name

        print("DEBUG: Successfully patched get_model_name function", file=sys.stderr)

    except Exception as e:
        # If patching fails, print warning but don't crash
        print(f"ERROR: Failed to patch transformers auto_docstring: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
