IMAGE ?= rtl-debug-agent:dev
RUN   := docker run --rm -v "$(CURDIR)":/work -w /work $(IMAGE)

.PHONY: image shell smoke corpus-check grader-validate bugs bugs-check mutator-test

image:
	docker build -f docker/Dockerfile -t $(IMAGE) .

shell:
	docker run --rm -it -v "$(CURDIR)":/work -w /work $(IMAGE) bash

# Phase 1 acceptance: the FIFO passes its cocotb test, and the grader proves it equal to itself
# and rejects two hand-edited copies.
smoke:
	$(RUN) bash smoke/run.sh

# Phase 2 acceptance: every design lints, passes its reference test, is proved equal to itself by
# the grader, and the grader rejects each of its known-bad controls.
# Limit to some designs with: make corpus-check DESIGNS="op_unit token_bucket"
corpus-check:
	$(RUN) python tools/corpus_check.py $(DESIGNS)

# Grader validation: labeled buggy and equivalent variants must all get the expected verdict.
# Limit to some suites with: make grader-validate SUITES="fifo op_unit"
grader-validate:
	$(RUN) python tools/validate_grader.py $(SUITES)

# Phase 3a: mutate every golden design, keep only mutants the grader proves buggy (and that
# simulation confirms), and write bugs/ (buggy RTL, manifest.jsonl answer key, REPORT.md).
# Limit to some designs with: make bugs DESIGNS="token_bucket"
bugs:
	$(RUN) python mutator/generate.py $(DESIGNS)

# Re-verifies the committed bug pool: hashes, exact reversible edits, opaque IDs, every bug still
# FAILs, golden and sample equivalent rewrites PASS.
bugs-check:
	$(RUN) python tools/bugs_check.py $(DESIGNS)

# Unit tests for the mutation operators.
mutator-test:
	$(RUN) python -m pytest -q -p no:cacheprovider mutator/test_operators.py
