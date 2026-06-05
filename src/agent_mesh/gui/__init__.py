"""GUI admin / operator console (Streamlit).

The console is the operator-facing surface for the mesh. It complements the CLI/
code-based administration path (Makefile targets, gcloud/wrangler scripts,
manifest validation, schema export, migrations, smoke/E2E tests).

The rendering layer (Streamlit) is imported lazily inside ``admin_app.main`` so
the package stays importable in a minimal environment (tests, CI). The read-model
helpers in ``admin_console`` are pure Python and testable without Streamlit.
"""
