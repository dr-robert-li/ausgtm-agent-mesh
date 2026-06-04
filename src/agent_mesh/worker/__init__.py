"""Long-running execution plane (Cloud Run Jobs / Worker Pools).

The worker consumes dispatched task ids, runs the AG2 orchestration adapter, and
pauses at approval gates for write actions. State is persisted in the repository
so runs can exceed 60 minutes and resume after an approval decision.
"""
