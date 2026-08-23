"""Testkonfiguration: DB in Temp-Verzeichnis umleiten, bevor app.* importiert."""
import os
import tempfile

os.environ.setdefault("NETDIAG_DATA_DIR", tempfile.mkdtemp(prefix="netdiag-test-"))
