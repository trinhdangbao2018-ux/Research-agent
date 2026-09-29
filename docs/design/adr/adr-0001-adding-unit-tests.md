# ADR-0001: Unit test and integration test
Date: 2026-09-26

## Status
Proposed

## Context
The unit/module can sometimes contain errors, or bugs. Adding unit test helps catch bug sooner and debug easier.
Every test don't necessary need to go through composition.build now
Still keep integration test from the final-module-layout.md to check the whole architecture

## Decision
- Unit test: test each module directly, right after writing it.
- Integration test (test_full_run etc.): still goes through composition.build, to check the wiring.

## Consequence
- Update the test rule in final-module-layout.md.
- test_full_run.py is still needed.
