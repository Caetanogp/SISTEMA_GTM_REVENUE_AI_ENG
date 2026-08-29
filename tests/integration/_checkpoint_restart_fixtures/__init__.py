"""Standalone scripts run as subprocesses by test_langgraph_checkpoint_restart.py.

Not a test module - pytest never imports this package. Each script here runs as its own OS
process (see the parent test for why: proving checkpoint survival requires an actual process
boundary, not just two objects in the same pytest run) and is invoked with
`sys.executable <script> <thread_id> <postgres_dsn>`.
"""
