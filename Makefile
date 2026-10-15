IMAGE ?= rtl-debug-agent:dev
RUN   := docker run --rm -v "$(CURDIR)":/work -w /work $(IMAGE)

.PHONY: image shell smoke

image:
	docker build -f docker/Dockerfile -t $(IMAGE) .

shell:
	docker run --rm -it -v "$(CURDIR)":/work -w /work $(IMAGE) bash

# Phase 1 acceptance: the FIFO passes its cocotb test, and EQY rejects a hand-edited copy.
smoke:
	$(RUN) bash smoke/run.sh
