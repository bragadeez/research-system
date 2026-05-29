import sys
import os

print(f"Executable Path: {sys.executable}")
print(f"Python Version: {sys.version}")
try:
    import loguru
    print("Loguru found at:", loguru.__file__)
except ImportError:
    print("Loguru NOT found in this environment.")