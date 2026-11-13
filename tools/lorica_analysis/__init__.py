"""Lexical C/C++ source analysis for Lorica's assertion-style checks (stdlib only).

Pipeline: lexer (tokens, directives, comments) -> preprocess (conditional groups)
-> extract (functions and unparsed regions; the API other analyses build on)
-> complexity (metrics) -> gate (thresholds, baseline, suppressions) -> report
(text and JSON). sources selects and reads the input files. The command line is
tools/lorica_analyze.py. Specification: spec/feature/source-analysis.md.
"""
