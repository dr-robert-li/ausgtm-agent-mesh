"""Streamlit admin / operator console entrypoint.

Run locally with ``make run-gui`` (``streamlit run src/agent_mesh/gui/admin_app.py``)
or deploy to Cloud Run. Streamlit is imported lazily inside ``main`` so this
module is importable without Streamlit installed (the importability test relies
on this); the read-model helpers live in ``admin_console`` and are pure Python.

Sections covered (operator surfaces): task monitoring, approvals, toolpack
registry, MCP server registry, AI-BOM, budget/model routing, memory/context,
self-improvement proposals, deployment checks, and Langfuse trace links/health.
This is a scaffold: it renders the registries and config that are available
in-process and clearly marks panels that require a live Postgres/Langfuse backend.
"""

from __future__ import annotations

from agent_mesh.gui.admin_console import (
    ADMIN_SECTIONS,
    model_routing_view,
    observability_view,
    stack_view,
    toolpack_view,
)


def main() -> None:  # pragma: no cover - requires streamlit + a display loop
    import streamlit as st

    st.set_page_config(page_title="Agent Mesh Admin", layout="wide")
    st.title("Agent Mesh — Admin / Operator Console")
    st.caption(
        "LangChain + LangGraph + Deep Agents + Langfuse variant. "
        "CLI/code administration lives in the Makefile and scripts/."
    )

    with st.sidebar:
        st.header("Stack")
        for k, v in stack_view().items():
            st.write(f"**{k}**: {v}")
        section_titles = {s.title: s for s in ADMIN_SECTIONS}
        choice = st.radio("Section", list(section_titles))
        section = section_titles[choice]

    st.subheader(section.title)
    st.write(section.description)

    if section.key == "toolpacks":
        st.dataframe(toolpack_view())
    elif section.key == "budget":
        st.json(model_routing_view())
    elif section.key == "observability":
        st.json(observability_view())
    elif section.key in {"tasks", "approvals", "aibom", "memory", "improve"}:
        st.info(
            "This panel reads from the durable Postgres store. Configure "
            "DATABASE_URL and a repository backend to populate it. The in-memory "
            "POC repository is per-process and not shared with this console."
        )
    elif section.key == "mcp":
        st.info(
            "MCP server registry. Claude Desktop and Claude Code are first-class "
            "clients; Codex, OpenCode, and Pi connect later via the same MCP/tool "
            "boundary."
        )
    elif section.key == "deploy":
        st.info(
            "Run `make schemas`, `make test`, and `make smoke` for deployment "
            "readiness checks. Manifest validation and schema export are CLI tasks."
        )


if __name__ == "__main__":  # pragma: no cover
    main()
