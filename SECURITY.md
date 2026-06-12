# Security policy

## Supported versions

The latest release on PyPI is supported. Pre-1.0-rc versions receive
fixes only via upgrading.

## Reporting a vulnerability

Please use **GitHub private vulnerability reporting**: on
https://github.com/bcllcc/modulor go to *Security → Report a
vulnerability*. Do not open public issues for security problems.

You can expect an acknowledgement within 7 days. Confirmed
vulnerabilities are fixed in a patch release and credited (unless you
prefer otherwise).

## Scope notes

- Modulor's kernel executes **no network calls, no shell commands and no
  dynamic code from documents**. Parameter expressions are evaluated by
  an AST-whitelisted interpreter (`modulor/expr.py`) with no builtins —
  escape findings there are very much in scope.
- Documents are plain JSON; the importer treats DXF input as untrusted
  (fuzzed, budgeted). Crash-on-parse findings are in scope.
- **Extensions are out of the sandboxless trust boundary by design**:
  installing a plugin runs its code (see docs/PLUGINS.md §2.5). "A
  malicious plugin can do bad things" is not a vulnerability; "a plugin
  can corrupt core invariants without doing anything privileged" is.
