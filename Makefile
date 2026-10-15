IMAGE ?= rtl-debug-agent:dev
RUN   := docker run --rm -v "$(CURDIR)":/work -w /work $(IMAGE)

.PHONY: image shell smoke corpus-check

image:
	docker build -f docker/Dockerfile -t $(IMAGE) .

shell:
	docker run --rm -it -v "$(CURDIR)":/work -w /work $(IMAGE) bash

# Phase 1 acceptance: the FIFO passes its cocotb test, and EQY rejects a hand-edited copy.
smoke:
	$(RUN) bash smoke/run.sh

# Phase 2 acceptance: every design lints, passes its reference test, and EQY-proves equal to itself.
# Limit to some designs with: make corpus-check DESIGNS="op_unit token_bucket"
corpus-check:
	$(RUN) python tools/corpus_check.py $(DESIGNS)
