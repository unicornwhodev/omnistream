# Local execution utilities

Generic Windows Kit launch, host resource budgets, scene restoration, native capture and verified spooling utilities. Configure machine paths and credentials outside the repository.

The hidden launcher can use `bounded_kit_launcher.py`, `bounded_process.py` and `host_budget.py` to own the process tree and enforce the configured limits.

Run the focused local unit tests for the utility being changed. CPU unit checks do not establish native Kit, GPU or Codex-host acceptance.
