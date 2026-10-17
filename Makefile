IMAGE ?= rtl-debug-agent:dev
# Containers that mount the repo never see .env (the API key): an empty file is mounted over it.
MOUNT := -v "$(CURDIR)":/work $(if $(wildcard .env),-v "$(CURDIR)/docker/no_env":/work/.env:ro) -w /work
RUN   := docker run --rm $(MOUNT) $(IMAGE)
# The tool server (and later the agent loop) runs on the host, outside the sandbox.
HOST_PY ?= .venv/bin/python

.PHONY: image shell smoke corpus-check grader-validate bugs bugs-check subset subset-check mutator-test grader-test grade-check \
        host-venv tools-test tools-check agent-test agent-pilot bugs-multi probe bugs-multi-eval eval-haiku \
        bestof-tune bestof-tune-k2 eval-bestof exposure eval-nosim

image:
	docker build -f docker/Dockerfile -t $(IMAGE) .

shell:
	docker run --rm -it $(MOUNT) $(IMAGE) bash

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
	$(RUN) python -m pytest -q -p no:cacheprovider mutator/test_operators.py mutator/test_combine.py

# Unit tests for the grader: reading SBY proof logs, combining the formal verdict with the
# reference test, scoring localization, and the patch source rules.
grader-test:
	$(RUN) python -m pytest -q -p no:cacheprovider grader/test_equiv.py grader/test_grade.py

# Phase 4b: the full grading flow (formal proof + hidden reference test + localization) on every
# eval and dev bug: the golden repair PASSes with an exact line, the unchanged bug FAILs, correct
# rewrites PASS, and patches PDR proves equivalent but simulation rejects FAIL.
grade-check:
	$(RUN) python tools/grade_check.py

# Host-side Python environment for the tool server (MCP SDK) and its tests.
host-venv:
	python3 -m venv .venv
	$(HOST_PY) -m pip install -q -r requirements-host.txt

# Phase 5: tool-server tests against a real sandbox (escape attempts, timeouts, budget, MCP stdio).
tools-test:
	$(HOST_PY) -m pytest -q -p no:cacheprovider toolserver/test_toolserver.py

# Phase 5 end to end: a scripted client drives the tool server over MCP on the 30 dev bugs
# (golden fix and unchanged submissions), then the runs are graded in the container.
tools-check:
	$(HOST_PY) tools/tools_check.py

# Phase 6a: agent loop, single-shot baseline and OpenRouter client, against a fake API (no cost;
# agent tests use the real tool server and sandbox).
agent-test:
	$(HOST_PY) -m pytest -q -p no:cacheprovider agent/test_agent.py

# Phase 6a pilot: agent + baseline on the 30 dev bugs, one run each, graded, with cost projected
# for the full eval. Spends money: needs OPENROUTER_API_KEY.
agent-pilot:
	$(HOST_PY) -m agent.eval --set dev --repeats 1 --out runs/pilot

# Phase 6c difficulty probe: three-bug variants of the pool (2 per design, seeded) -> bugs/multi/.
bugs-multi:
	$(RUN) python mutator/combine.py $(DESIGNS)

# Phase 6c: the fresh three-bug eval set (12 per design, new seed, no probe or dev components).
bugs-multi-eval:
	$(RUN) python mutator/combine.py --set eval $(DESIGNS)

# Phase 6c: single-shot baseline only, on the cells of the 2x2 (model x single/three bugs), then a
# table in bugs/multi/PROBE.md. Spends money (about $1.50): needs OPENROUTER_API_KEY.
HAIKU ?= anthropic/claude-haiku-5.5
probe:
	$(HOST_PY) -m agent.eval --bugs bugs/multi/probe_set.json --arms baseline --out runs/probe/sonnet-multi
	$(HOST_PY) -m agent.eval --set dev --arms baseline --baseline-model $(HAIKU) --out runs/probe/haiku-single
	$(HOST_PY) -m agent.eval --bugs bugs/multi/probe_set.json --arms baseline --baseline-model $(HAIKU) --out runs/probe/haiku-multi
	$(HOST_PY) tools/probe_report.py

# Phase 6c eval: agent vs single-shot baseline on the three-bug eval set, both on Haiku 5.5.
# REPEATS=1 first to measure cost; rerun with REPEATS=3 to add runs 2 and 3 (finished runs are kept).
REPEATS ?= 3
eval-haiku:
	$(HOST_PY) -m agent.eval --bugs bugs/multi_eval/eval_set.json --repeats $(REPEATS) --workers 6 \
		--agent-model $(HAIKU) --baseline-model $(HAIKU) --out runs/eval-haiku

# Phase 6d: cost-matched best-of-k baseline. Tune temperature (k=3) on the dev three-bug set, then
# tools/bestof_tune.py applies the pre-set rule and freezes k / temperature in agent/config.json.
# Spends money (about $0.7): needs OPENROUTER_API_KEY.
bestof-tune:
	for t in 0.2 0.7 1.0; do \
		$(HOST_PY) -m agent.eval --bugs bugs/multi/probe_set.json --arms bestof --baseline-model $(HAIKU) \
			--bestof-k 3 --bestof-temp $$t --workers 6 --out runs/bestof-tune/k3-t$$t || exit 1; \
	done
	$(HOST_PY) tools/bestof_tune.py

# Only if bestof-tune says k=3 is over the cost cap: k=2 at the chosen temperature.
bestof-tune-k2:
	$(HOST_PY) -m agent.eval --bugs bugs/multi/probe_set.json --arms bestof --baseline-model $(HAIKU) \
		--bestof-k 2 --bestof-temp $(T) --workers 6 --out runs/bestof-tune/k2-t$(T)
	$(HOST_PY) tools/bestof_tune.py

# Phase 6d eval: the frozen best-of-k baseline on the three-bug eval set, repeats paired with
# runs/eval-haiku's agent runs, then the three-arm comparison.
BESTOF_REPEATS ?= 2
eval-bestof:
	$(HOST_PY) -m agent.eval --bugs bugs/multi_eval/eval_set.json --arms bestof --repeats $(BESTOF_REPEATS) \
		--workers 6 --baseline-model $(HAIKU) --out runs/eval-haiku-bestof
	$(HOST_PY) tools/compare_arms.py runs/eval-haiku runs/eval-haiku-bestof

# Phase 6b exposure: replay every run's own tests on buggy and golden RTL in fresh sandboxes
# (host; no API cost), then the comparison with the exposure funnel.
exposure:
	$(HOST_PY) tools/replay_exposure.py runs/eval-haiku runs/eval-haiku-bestof
	$(HOST_PY) tools/compare_arms.py runs/eval-haiku runs/eval-haiku-bestof

# Phase 6d ablation: the agent without run_cocotb (same model, budgets, eval set; prompt changed
# only where it needs simulation), repeats paired with runs/eval-haiku's agent runs.
NOSIM_REPEATS ?= 2
eval-nosim:
	$(HOST_PY) -m agent.eval --bugs bugs/multi_eval/eval_set.json --arms nosim --repeats $(NOSIM_REPEATS) \
		--workers 6 --agent-model $(HAIKU) --out runs/eval-haiku-nosim
	$(HOST_PY) tools/compare_arms.py runs/eval-haiku runs/eval-haiku-bestof runs/eval-haiku-nosim
