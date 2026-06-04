import sys
import os

# Add current directory to sys.path
sys.path.append(os.getcwd())

try:
    import shared_functions
    print("Import shared_functions successful")
except ImportError as e:
    print(f"Import failed: {e}")
except Exception as e:
    print(f"An error occurred: {e}")
