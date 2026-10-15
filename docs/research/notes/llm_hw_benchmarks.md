# LLM and Automated RTL Debugging/Repair Benchmarks: Bug Sources, Difficulty Stratification, Grading, and Results by Difficulty

(Research date 2026-10-15. Most sources are arXiv preprints. Where a paper is internally inconsistent, that is flagged below.)

## Q1. Per-benchmark facts: bug source, count, difficulty categories, grading, per-difficulty results

### Takeaway
Very few RTL debug/repair benchmarks have explicit difficulty labels. CVDP has human-tagged easy/medium/hard but reports no results by difficulty. VerilogEval's easy/hard split (used in RTLFixer) is based on pass rate. Most others stratify by proxies: bug class (syntax vs. functional), module type, repository/project, per-module results, or a structural metric such as RTL-Repair's OSDD. Bugs are mostly injected (regex, GPT-4, mutation operators, expert seeding). The real-bug sources are HWE-Bench (merged PRs), LLM4SecHW (commits), RTL-Repair's 12 FPGA bugs, and Strider (student assignments). Grading is almost always testbench simulation, sometimes followed by manual "correct vs. plausible" review.

### Cited Findings

**NVIDIA CVDP (Comprehensive Verilog Design Problems, 2025)**
- 783 problems kept out of 1,313 written: 617 non-agentic and 166 agentic, written by about 35 hardware engineers with more than 4 years of experience — [arXiv 2506.14074](https://arxiv.org/html/2506.14074)
- There are 13 categories. Debugging/bug fixing is cid16, with 36 non-agentic and 11 agentic problems after filtering (101 and 30 before). The paper does not say how the bugs were introduced; they appear to be hand-authored by the engineers, but this is not stated — [arXiv 2506.14074](https://arxiv.org/html/2506.14074)
- Difficulty labels are "human-tagged" easy/medium/hard. Non-agentic problems include only easy and medium. Agentic problems cover all three levels, because hard problems are considered too complex for single-turn evaluation. The paper gives no per-difficulty counts and no tagging rubric — [arXiv 2506.14074](https://arxiv.org/html/2506.14074)
- Grading: mostly CocoTB harnesses (Icarus, Yosys, Verilator; Cadence Xcelium for cid12–14), BLEU for correspondence tasks, and an LLM judge (o4-mini) for Q&A. No formal grading — [arXiv 2506.14074](https://arxiv.org/html/2506.14074)
- Results are by category and not by difficulty. Claude 3.7 Sonnet non-agentic cid16 (debug) pass@1 is 53%, the highest of its categories (cid03 48%, cid13 6%). Overall non-agentic code-gen: Claude 3.7 Sonnet 33.56%, GPT-4.1 28.91%. Agentic problems run in single-turn format: Claude 3.7 Sonnet 29.0% — [arXiv 2506.14074](https://arxiv.org/html/2506.14074)
- The public repo describes Docker agent harnesses and a "heavy" agentic dataset (v1.1.0, git bundles). The README does not mention a per-problem difficulty field or difficulty-based reporting. 20 datapoints were omitted from the public release, and reference solutions are withheld — [NVlabs/cvdp_benchmark](https://github.com/NVlabs/cvdp_benchmark)
- Vendor claim, unverified: Turing describes expanding CVDP to 1,500+ tasks with difficulty labels and "agentic" and "heavy" tiers (multi-file, >200k-token Git-style projects including bug resolution) — [Turing case study](https://www.turing.com/case-study/benchmarking-rtl-agents-with-real-world-verilog-tasks-for-nvidia-cvdp)

**VerilogEval v1/v2**
- v2 has 156 HDLBits problems covering code completion and spec-to-RTL. It has no debug task and no difficulty stratification. Grading is Icarus simulation against a reference testbench, reported as pass@1. Failures are auto-classified into compile-time types (e.g., "Unable to Bind Wire/Reg 'clk'", Explicit Cast Required, Sensitivity Problem, Syntax Error) and run-time types (Reset Issue, Timeout, General Runtime Error) — [arXiv 2408.11053](https://arxiv.org/html/2408.11053)
- v2 cites agentic results from other papers (RTLFixer about +10%, VerilogCoder 94%, MAGE 95%) and notes that they are not directly comparable to single-turn results — [arXiv 2408.11053](https://arxiv.org/html/2408.11053)
- v1 easy/hard split as used by RTLFixer: easy has 71 problems and hard has 85, split at a pass-rate threshold of 0.1 on the Human set. This is an empirical pass-rate definition, not a human rating — [RTLFixer arXiv 2311.16543](https://arxiv.org/html/2311.16543)

**RTLLM**
- I found no RTLLM-native debug variant. RTLLM designs serve as the seed corpus for injected-bug debug sets in MEIC, UVLLM, and VeriBugBench (23 RTLLM projects) — [MEIC](https://arxiv.org/html/2405.06840), [UVLLM](https://arxiv.org/html/2411.16238), [VeriBugBench](https://arxiv.org/html/2609.18022)

**CirFix (ASPLOS 2022; TSE journal version)**
- 32 defect scenarios across 11 Verilog projects. Three hardware experts (two from industry, one from academia) seeded bugs they had seen in practice. Result: 21 plausible patches and 16 correct. Grading instruments the testbench and compares output wires bit by bit; "plausible" means the patch passes the testbench, and "correct" was judged by manual inspection — [UCL GP bib record](https://gpbib.cs.ucl.ac.uk/gp-html/DBLP_conf_asplos_Ahmad0W22.html), [NSF PAR](https://par.nsf.gov/biblio/10421496)
- RTL-Repair's Table 3 lists the defect types, such as "incorrect sensitivity list," "two separate numeric errors," "branches of if-statement swapped," "insufficient register size," and "assignment to next state omitted, incorrect sensitivity list." The projects range from a 3-8 decoder, counter, flop, fsm, shift register, and mux up to i2c, sha3, tate pairing, reed-solomon, and an sdram controller — [RTL-Repair paper (NSF PAR)](https://par.nsf.gov/servlets/purl/10561674)
- Gap: I could not open the CirFix paper itself (ACM returned 403) to check whether it assigns explicit difficulty categories.

**RTL-Repair (ASPLOS 2024, Laeufer et al., UC Berkeley)**
- Evaluated on the CirFix benchmarks plus 12 of 20 reproducible real bugs mined from git commits of open-source FPGA projects in "Debugging in the Brave New World of Reconfigurable Hardware." The other 8 were excluded for non-synthesizable code, unsupported SystemVerilog, or a missing ground truth — [RTL-Repair paper](https://par.nsf.gov/servlets/purl/10561674)
- RTL-Repair defines OSDD (Output/State Divergence Delta), a difficulty metric: the number of cycles between the first state divergence and the first output divergence, plus one, compared against the ground truth. Per benchmark it reports testbench length, first-error cycle, OSDD, and repair window. "Both RTL-Repair and CirFix were only able to solve benchmarks with low OSDD." The largest OSDD it solved was 25 (sdram_k2, via preprocessing) and 13 (i2c_k1, via synthesis). pairing_w1/w2 (OSDD about 73k) and reed_b1 (OSDD 2,963) were unsolved by both tools — [RTL-Repair paper](https://par.nsf.gov/servlets/purl/10561674)
- Grading is stricter than plain testbench pass. It adds gate-level simulation of the synthesized repair (to catch synthesis-simulation mismatch), an iverilog compatibility check, an "extended" testbench for decoder, and manual quality ratings A–D for the real bugs. Result: 16 repairs pass all tests, against 10 for CirFix. On real bugs, 9 of 12 pass the provided testbench, but only 2 fully match the ground truth (A), and several overfit the testbench — [RTL-Repair paper](https://par.nsf.gov/servlets/purl/10561674); [search summary of abstract](https://escholarship.org/uc/item/0c3656n2)
- Most repairs needed 1–2 changes, with a maximum of 3. Timeouts were 60 s for RTL-Repair and 16 h for CirFix — [RTL-Repair paper](https://par.nsf.gov/servlets/purl/10561674)

**RTLFixer (DAC 2024)**
- Bugs are real LLM-generated syntax errors: gpt-3.5 outputs on VerilogEval that failed to compile. The VerilogEval-syntax set has 212 erroneous implementations according to the abstract, but 174 according to the introduction (inconsistent). Errors are grouped by compiler error number: 7 categories for iverilog and 11 for Quartus — [arXiv 2311.16543](https://arxiv.org/html/2311.16543)
- Grading is compile fix rate plus simulation pass@k — [arXiv 2311.16543](https://arxiv.org/html/2311.16543)
- One-shot vs. ReAct with GPT-3.5, fix rate with feedback type as the axis: Simple 0.414→0.671, iverilog 0.536→0.731, Quartus 0.587→0.799. With RAG: one-shot 0.899 vs. ReAct 0.985 (Quartus). GPT-4 gap is small: one-shot 0.91/0.98 vs. ReAct 0.92/0.99 — [arXiv 2311.16543](https://arxiv.org/html/2311.16543)
- Per-difficulty pass@1, original→after fixing: Human easy 0.521→0.666, Human hard 0.053→0.120; Machine easy 0.568→0.833, Machine hard 0.367→0.771. On RTLLM, syntax success went 73%→93% and pass@1 11%→16%. Functional (simulation) error repair was only preliminary, with no numbers — [arXiv 2311.16543](https://arxiv.org/html/2311.16543)

**MEIC (arXiv 2024, Southeast Univ./York; venue not stated)**
- Bugs were injected into RTLLM designs, using regex bug-pattern lists for simple errors and GPT-4 or manual edits for complex functional errors. Total 178: 107 syntax and 71 function; 95 arithmetic and 83 logic modules. Nine syntax and nine function error types — [arXiv 2405.06840](https://arxiv.org/html/2405.06840)
- No explicit difficulty levels. Syntax vs. function and simple vs. complex modules serve as implicit difficulty. Grading is Fix Rate, which requires passing all testbench cases (ModelSim), averaged over 10 runs — [arXiv 2405.06840](https://arxiv.org/html/2405.06840)
- Iterative vs. single-shot (syntax/function FR): GPT-4 single 62.83/61.96; GPT-4 + domain knowledge 90.69/66.24; GPT-4 + MEIC (up to 10 rounds) 92.68/78.39. Per module (function): adder_8bit 100%, accu 50%, radix2_div 46%, traffic_light 44% — [arXiv 2405.06840](https://arxiv.org/html/2405.06840)

**UVLLM (arXiv 2024; venue not stated)**
- Errors were injected into RTLLM-based designs, with some pairs taken from pre/post-commit code. The paper says 331 instances in one place and implies 27 modules × 9 types = 243 in another (unreconciled). Error taxonomy: Declare (type/bitwidth misuse), Assignment (operator/variable/value misuse), Condition (judgment value/sensitivity), Port (mismatch); also syntax vs. functional; modules grouped as Arithmetic/Control/Memory/Misc. No difficulty labels — [arXiv 2411.16238](https://arxiv.org/html/2411.16238)
- Grading uses two metrics. Hit Rate (HR) means the output matches on test cases. Fix Rate (FR) adds expert review against extra scenarios. For other methods, functional HR−FR deviation exceeds 30%, against 1.4% for UVLLM, which shows testbench overfitting. A UVM testbench with scoreboard is used — [arXiv 2411.16238](https://arxiv.org/html/2411.16238)
- Overall FR: UVLLM 79.75% vs. MEIC 52.14%. Function FR by module type: Control 65.99% vs. MEIC 10.91%, Memory 86.67% vs. 22.73%. Iteration cap is 5 — [arXiv 2411.16238](https://arxiv.org/html/2411.16238)

**HDLdebugger (arXiv 2024, CUHK/HKUST/Huawei)**
- Bugs are injected by "reverse engineering": modification functions applied to engineers' correct code. 92,143 instances, split 8:2. Error types include Memory, Clock, Trace, Syntax E, Netlist E, and Simulation E. No difficulty labels. Grading is pass rate on Huawei's internal HDL compiler. Single-shot only (multi-round is future work). HDLdebugger 81.93% vs. RTLFixer 28.35% — [arXiv 2403.11671](https://arxiv.org/html/2403.11671)

**VeriDebug (arXiv 2504.19099, 2025)**
- GPT-4 injected bugs into a valid Verilog corpus (Thakur et al.), about 8,000 samples. 13 bug types: width, logic, assignment, initial, data, state, comparison, bitwise, condition, signal, arithmetic, value, others. Test set is stratified by code length; no difficulty labels — [arXiv 2504.19099](https://arxiv.org/html/2504.19099v1)
- Grading is exact-match Acc@1 of the fixed line, with no testbench. Single pipeline, not iterative. Fix Acc@1 64.7% (the text also says 64.2%), against 36.6% for GPT-3.5-turbo. Per bug type: "initial" bugs are hardest at 0.39 generation accuracy, and "signal" bugs reach 1.00 — [arXiv 2504.19099](https://arxiv.org/html/2504.19099v1); [arXiv abs](https://arxiv.org/abs/2504.19099)

**Strider (IEEE TCAD, Dec 2023, Deheng Yang et al., NUDT)**
- Full title: "Signal Value Transition-Guided Defect Repair for HDL Programming Assignments" — [OpenAlex record](https://api.openalex.org/works/doi:10.1109%2FTCAD.2023.3341750)
- Its benchmark, as described by VeriPilot: 57 real defect–fix pairs from seven student programming assignments — [VeriPilot arXiv 2606.23759](https://arxiv.org/html/2606.23759v1)
- Gap: I could not access the Strider paper (paywalled), so its own grading and categorization are unverified.

**VeriPilot (arXiv 2606.23759, 2026, ICT-CAS)**
- Evaluated on Strider (57) and CVDP cid16. VeriPilot translated CVDP cid16 to Verilog and removed hints; the count is not stated, and the percentages imply 35. Grading is testbench re-simulation — [arXiv 2606.23759](https://arxiv.org/html/2606.23759v1)
- Repair success rates, Strider / CVDP-cid16: CirFix 15.79/22.85; Strider 36.84/28.57; GPT-4o 78.95/57.14; MAGE (agentic) + GPT-4o 87.72/65.71; GPT-5 84.21/74.28; MAGE + GPT-5 91.23/80.00; VeriPilot + GPT-5 92.98/91.43. Inconsistency: the abstract says the GPT-4o CVDP baseline is 54.3%, while Table I says 57.14% — [arXiv 2606.23759](https://arxiv.org/html/2606.23759v1)

**VeriBugBench (arXiv 2609.18022, 2026)**
- 2,608 injected single faults. The mutation operators come from 1,298 bug-fix commits across 300 projects and are applied to 45 projects (11 CirFix, 23 RTLLM, 11 native). Kept instances must compile, run to completion, and show an output trace that differs from the clean design. Groups are by source and project size, not difficulty. No LLM repair evaluation and no per-difficulty results — [arXiv 2609.18022](https://arxiv.org/html/2609.18022)

**HWE-Bench (arXiv 2604.14709, 2026, Peking Univ.)**
- 417 real bugs from merged bug-fix PRs: OpenTitan 245, Ibex 35, CVA6 35, Caliptra 16, XiangShan 54, Rocket Chip 32. No per-task difficulty label. Repos fall into an "easier" tier (CVA6/Ibex/Caliptra) and a "harder" tier (XiangShan/OpenTitan/Rocket Chip) based on observed resolve rates. The authors attribute the gap to project scope and bug-type mix (Rocket Chip has more than 40% config/integration bugs), not code size. Root-cause classes are logic, specification, interface/protocol, timing, configuration/integration, and software/firmware — [arXiv 2604.14709](https://arxiv.org/html/2604.14709)
- Grading: an LLM-generated test script runs the project's native simulation, and a task counts as resolved on FAIL→PASS (validated against the ground-truth patch). Agents only, up to 500 iterations or 6 h, with no single-shot baseline. Best overall is GPT-5.4 xhigh at 70.7%. Per tier: CVA6 97.1% vs. Rocket Chip 62.5% — [arXiv 2604.14709](https://arxiv.org/html/2604.14709)

**LLM4SecHW (arXiv 2401.16448, 2024)**
- Real buggy/fixed pairs mined from GitHub commits, issues, and PRs of CVA6, CVA5, OpenTitan, Ibex, mor1kx, OpenPiton, PULP, and darkriscv, filtered by PR labels and file type. Used for fine-tuning — [arXiv 2401.16448](https://arxiv.org/html/2401.16448v1)
- HLSDebugger criticizes this kind of data: a later commit does not guarantee that it fixes the earlier code — [HLSDebugger arXiv 2507.21485](https://arxiv.org/pdf/2507.21485)
- Gap: I did not verify LLM4SecHW's counts, metrics, or any difficulty breakdown.

**Other 2025–2026 items**
- HLS repair benchmark (ICCD 2026, arXiv 2610.03971): 125 injected single bugs drawn from Chrysalis-HLS types, in CHStone, MachSuite, and Polybench. No difficulty labels; stratified by suite and file size. CHStone (about 40 KB files) pass@1 is 13.7–44.9%, against 48.5–92.5% for MachSuite. Within CHStone, LOC vs. pass@1 has ρ = −0.389. It defines "underconstrained" instances as solution multiplicity ≥ 0.8 and pass@5 = 0. Zero-shot only — [arXiv 2610.03971](https://arxiv.org/html/2610.03971v1)
- "Understanding and Mitigating Errors of LLM-Generated RTL Code" (arXiv 2508.05266) appeared in search but I did not read it — [arXiv 2508.05266](https://arxiv.org/html/2508.05266v2)

### Inferences
- "Difficulty" in this literature is almost always post hoc (the pass-rate thresholds in VerilogEval, HWE-Bench's resolve-rate tiers) or a proxy (syntax vs. functional, module type, project, LOC). The exceptions are CVDP's human tags (unreported in results) and RTL-Repair's OSDD, the only principled structural/temporal difficulty metric I found.
- Injected-bug sets dominate (MEIC, UVLLM, HDLdebugger, VeriDebug, VeriBugBench, CirFix seeding). Real-bug sets are small (RTL-Repair 12, Strider 57) or repository-scale and agent-only (HWE-Bench 417).

### Gaps
- CirFix's own paper (difficulty categories, if any) and Strider's paper were not accessible.
- No per-problem difficulty distribution for CVDP cid16 is published.

## Q2. Does any benchmark grade fixes with formal equivalence? Does any report the agent vs. single-shot gap by difficulty?

### Takeaway
None of the major RTL debug/repair benchmarks grades fixes with formal equivalence. All rely on testbench simulation, and several add manual review to catch overfitting. Formal equivalence appears in code-generation benchmarks (NotSoTiny, RealBench) and in 2026 repair loops as feedback, not as the benchmark grader. No benchmark reports an agent vs. single-shot gap stratified by explicit difficulty labels. The closest are VeriPilot (easier Strider vs. harder CVDP-cid16, with direct LLM vs. MAGE agent vs. VeriPilot) and RTLFixer (one-shot vs. ReAct, plus easy/hard before/after).

### Cited Findings
- CVDP, VerilogEval v2, MEIC, UVLLM, HWE-Bench, VeriBugBench, and the HLS repair benchmark all grade by simulation/test oracles, with no formal equivalence grading — [CVDP](https://arxiv.org/html/2506.14074), [VerilogEval v2](https://arxiv.org/html/2408.11053), [MEIC](https://arxiv.org/html/2405.06840), [UVLLM](https://arxiv.org/html/2411.16238), [HWE-Bench](https://arxiv.org/html/2604.14709), [VeriBugBench](https://arxiv.org/html/2609.18022), [HLS repair](https://arxiv.org/html/2610.03971v1)
- RTL-Repair goes furthest without formal methods: gate-level simulation of the synthesized repair and manual A–D grading against ground truth. It uses SMT for repair synthesis, not for grading — [RTL-Repair](https://par.nsf.gov/servlets/purl/10561674)
- Testbench overfitting is documented. RTL-Repair: 9 of 12 real-bug repairs pass the testbench, but only 2 fully match ground truth. UVLLM: other methods show more than 30% HR−FR deviation on functional bugs. CirFix: 21 plausible vs. 16 correct — [RTL-Repair](https://par.nsf.gov/servlets/purl/10561674), [UVLLM](https://arxiv.org/html/2411.16238), [CirFix record](https://gpbib.cs.ucl.ac.uk/gp-html/DBLP_conf_asplos_Ahmad0W22.html)
- Formal tools in nearby work:
  - NotSoTiny grades generation with a Yosys miter (equiv_simple, equiv_induct) — [arXiv 2512.20823](https://arxiv.org/pdf/2512.20823)
  - RealBench uses Yosys synthesis plus JasperGold equivalence — [arXiv 2507.16200](https://arxiv.org/pdf/2507.16200)
  - SpecLoop uses Yosys EQY (SAT, depth 10) in an RTL-to-spec loop — [arXiv 2603.02895](https://arxiv.org/html/2603.02895)
  - A 2026 multi-agent repair pipeline uses SymbiYosys/Z3 counterexample feedback on a six-design suite (feasibility study) — [arXiv 2607.28877](https://arxiv.org/html/2607.28877v1)
  - "Benchmarking LLMs for Verilog Design Flows" reports that Yosys formal equivalence exposes errors the testbench vectors miss — [arXiv 2607.22759](https://arxiv.org/html/2607.22759v1)
  - Note: these formal-tool descriptions come from search snippets; I did not fetch the full papers.
- Agent/iterative vs. single-shot evidence:
  - VeriPilot, MAGE vs. direct GPT-4o: +8.8 pts on Strider and +8.6 pts on CVDP-cid16. VeriPilot vs. direct GPT-5: +8.8 on Strider and +17.2 on CVDP-cid16, so the gain is larger on the harder set — [arXiv 2606.23759](https://arxiv.org/html/2606.23759v1)
  - RTLFixer, ReAct vs. one-shot: large gain for GPT-3.5, about 1 pt for GPT-4 — [arXiv 2311.16543](https://arxiv.org/html/2311.16543)
  - MEIC, iterative vs. single GPT-4: function FR 61.96→78.39 — [arXiv 2405.06840](https://arxiv.org/html/2405.06840)
  - CVDP runs agentic problems single-turn only and does not report the gap by difficulty — [arXiv 2506.14074](https://arxiv.org/html/2506.14074)
  - HWE-Bench has no single-shot baseline — [arXiv 2604.14709](https://arxiv.org/html/2604.14709)

### Inferences
- An RTL repair benchmark graded by formal equivalence (e.g., EQY/SBY against a golden design), with agent vs. single-shot comparisons by difficulty tier, appears to be an open niche as of Oct 2026.
- The VeriPilot numbers suggest that structured or agentic help matters more on harder (CVDP) bugs than on student-assignment bugs. This rests on two datasets and one paper.

### Gaps
- I could not confirm that CVDP's commercial-tool tasks (cid12–14) never use formal checks. The paper mentions only simulation.
- I could not verify whether any closed or industrial benchmark (e.g., JasperGold SEC-based) exists for LLM repair grading.

## Q3. What difficulty dimensions recur?

### Takeaway
The recurring dimensions are:
- bug class (syntax/compile vs. functional/simulation)
- bug type taxonomy (operator, bitwidth, sensitivity, assignment, state/FSM, etc.)
- module or design type and size (LOC, project, repository)
- temporal depth (testbench cycles, cycles to manifestation, OSDD)
- number of edits or bugs (single vs. multi-edit)
- empirical pass-rate tiers
- human tags (CVDP only)

### Cited Findings
- Syntax vs. functional: MEIC, UVLLM, and RTLFixer report it, and functional is consistently harder (MEIC GPT-4 + MEIC 92.68% syntax vs. 78.39% function) — [MEIC](https://arxiv.org/html/2405.06840), [UVLLM](https://arxiv.org/html/2411.16238), [RTLFixer](https://arxiv.org/html/2311.16543)
- Bug-type taxonomies: MEIC (9+9 types), UVLLM (Declare/Assignment/Condition/Port), VeriDebug (13 types), HWE-Bench root-cause classes, RTLFixer compiler-error categories — [MEIC](https://arxiv.org/html/2405.06840), [UVLLM](https://arxiv.org/html/2411.16238), [VeriDebug](https://arxiv.org/html/2504.19099v1), [HWE-Bench](https://arxiv.org/html/2604.14709), [RTLFixer](https://arxiv.org/html/2311.16543)
- Design type/size:
  - UVLLM groups modules as Arithmetic/Control/Memory/Misc — [UVLLM](https://arxiv.org/html/2411.16238)
  - MEIC reports per module (accu, radix2_div, traffic_light are hardest) — [MEIC](https://arxiv.org/html/2405.06840)
  - VeriDebug stratifies by code length — [VeriDebug](https://arxiv.org/html/2504.19099v1)
  - VeriBugBench groups by project size — [VeriBugBench](https://arxiv.org/html/2609.18022)
  - The HLS benchmark reports a LOC correlation — [HLS repair](https://arxiv.org/html/2610.03971v1)
  - HWE-Bench argues that scope and bug mix matter more than size — [HWE-Bench](https://arxiv.org/html/2604.14709)
- Temporal/sequential depth: RTL-Repair's OSDD and testbench cycle counts, where only low-OSDD bugs were solved — [RTL-Repair](https://par.nsf.gov/servlets/purl/10561674)
- Number of bugs/edits:
  - CirFix includes multi-error scenarios (e.g., "Three separate numeric errors") — [RTL-Repair Table 3](https://par.nsf.gov/servlets/purl/10561674)
  - RTL-Repair notes that only 2 of CirFix's multi-edit repairs were correct — [RTL-Repair](https://par.nsf.gov/servlets/purl/10561674)
  - VeriBugBench and the HLS benchmark are single-fault only — [VeriBugBench](https://arxiv.org/html/2609.18022), [HLS repair](https://arxiv.org/html/2610.03971v1)
- Empirical pass-rate tiers: VerilogEval easy/hard (threshold 0.1) and HWE-Bench repo tiers — [RTLFixer](https://arxiv.org/html/2311.16543), [HWE-Bench](https://arxiv.org/html/2604.14709)
- Human-tagged levels: CVDP easy/medium/hard — [CVDP](https://arxiv.org/html/2506.14074)
- Bug observability/oracle strength:
  - VeriBugBench keeps only output-observable mutants and reports mutation scores — [VeriBugBench](https://arxiv.org/html/2609.18022)
  - The HLS benchmark rejected 75 candidates its oracle could not detect and defines underconstrained instances — [HLS repair](https://arxiv.org/html/2610.03971v1)
  - RTL-Repair found the decoder testbench too weak — [RTL-Repair](https://par.nsf.gov/servlets/purl/10561674)

### Inferences
- Combinational vs. sequential is rarely an explicit axis. It shows up indirectly through module types (FSM/memory/control) and through OSDD (OSDD = 0 for stateless decoders).
- Testbench strength or underconstraint is an emerging dimension of difficulty: weak oracles make bugs easier to "fix" plausibly and harder to fix correctly.

### Gaps
- None of these sources had a human-rated difficulty study (inter-rater agreement) for RTL bugs.
- No benchmark crosses difficulty tiers with agent vs. single-shot conditions.
