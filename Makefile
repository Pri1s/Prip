IMAGE ?= rtl-debug-agent:dev
RUN   := docker run --rm -v "$(CURDIR)":/work -w /work $(IMAGE)

.PHONY: image shell smoke corpus-check grader-validate bugs bugs-check subset subset-check mutator-test grader-test grade-check

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

# Phase 3b: pick the frozen eval set (180 bugs, stratified by kind and depth) and a disjoint
# 30-bug dev set from the pool. Refuses to replace an existing eval set unless FORCE=1.
subset:
	$(RUN) python mutator/subset.py $(if $(FORCE),--force)

# Re-verifies the eval/dev sets: pool unchanged, quotas and caps, disjoint, reproducible.
subset-check:
	$(RUN) python tools/subset_check.py

# Unit tests for the mutation operators.
mutator-test:
	$(RUN) python -m pytest -q -p no:cacheprovider mutator/test_operators.py

# Unit tests for the grader: reading SBY proof logs, combining the formal verdict with the
# reference test, scoring localization, and the patch source rules.
grader-test:
	$(RUN) python -m pytest -q -p no:cacheprovider grader/test_equiv.py grader/test_grade.py

# Phase 4b: the full grading flow (formal proof + hidden reference test + localization) on every
# eval and dev bug: the golden repair PASSes with an exact line, the unchanged bug FAILs, correct
# rewrites PASS, and patches PDR proves equivalent but simulation rejects FAIL.
grade-check:
	$(RUN) python tools/grade_check.py
