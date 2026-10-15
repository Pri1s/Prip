# Hardware/RTL bug depth metrics vs. detection, localization, and repair difficulty

Scope note: Evidence is graded as **(a) EMPIRICAL**: numbers that link a depth/latency measure to difficulty; **(b) QUALITATIVE**: claims or design rationales without a measured correlation; **(c) NOTHING FOUND**. "Depth" here covers minimum counterexample (CEX) length, sequential depth, activation-to-observation latency, error detection latency (EDL), propagation distance, and trace length. All numbers below come from primary PDFs or arXiv pages that I read during this session, except where marked "snippet-only" or "unverified".

## Q1. Has any study measured (with numbers) a correlation between CEX length / bug depth / detection latency and localization accuracy, repair success, or debugging time?

### Takeaway
No study I found reports a statistical correlation coefficient. The strongest empirical evidence is **RTL-Repair's Output/State Divergence Delta (OSDD)** table (ASPLOS 2024). It gives per-bug state-to-output divergence distance alongside repair outcome for RTL-Repair and CirFix. Every bug with OSDD > 25 cycles went unrepaired by both tools, although many low-OSDD bugs also failed. The QED/post-silicon line (Mitra group) treats short error detection latency as a precondition for localization. That link holds by construction (trace or recorder window size). They measured that QED shortens latency, but they never measured debug time as a function of latency.

### Cited Findings

**(a) EMPIRICAL: RTL-Repair (Laeufer, Fajardo, Ahuja, Iyer, Nikolić, Sen; ASPLOS '24)**
- The paper defines the **OSDD**. Run the ground-truth and buggy designs from the same state on the same inputs. OSDD is the number of steps from the first *state* divergence to the first *output* divergence, plus one. It is 0 if state never diverges (the bug is in the output logic only). — [RTL-Repair PDF (NSF PAR)](https://par.nsf.gov/servlets/purl/10561674)
- Table 2 lists testbench (TB) length, first-error cycle, OSDD, repair window, and RTL-Repair/CirFix outcomes for 30 CirFix-suite benchmarks (two unclocked i2c benchmarks are excluded). Selected rows (TB cycles / first error / OSDD / RTL-Repair / CirFix):
  - i2c_k1: 171957 / 1238 / 13 / correct / correct
  - sdram_k2: 636 / 64 / 25 / correct / no repair
  - fsm_s1: 37 / 10 / 11 / correct / incorrect
  - pairing_w1: 74149 / 74119 / **73346** / no repair / no repair
  - pairing_w2: 74149 / 74119 / **74109** / no repair / no repair
  - reed_b1: 166166 / 2967 / **2963** / no repair / no repair
  - pairing_k1: 74149 / 775 / 2 / no repair / no repair
  - Many OSDD = 1 bugs are also unrepaired (e.g., fsm_w1, mux_k1, sha3_w1/r1, sdram_w1).
  - Source: [RTL-Repair PDF](https://par.nsf.gov/servlets/purl/10561674)
  - Symbol caveat: the Table 2 legend did not extract cleanly. I read ✔/✖/○ as correct / incorrect / no repair, matching the legends of the paper's other tables (Table 5: "✔ generated correct repair, ✖ generated incorrect repair, ○ no repair generated").
- Authors' statements:
  - "The benchmark with the largest OSDD that was successfully repaired is sdram_k2, with an OSDD of 25". That bug was solved by static preprocessing with no unrolling. The next-largest is i2c_k1 (OSDD 13), which the unrolling synthesizer solved.
  - "Both RTL-Repair and CirFix were only able to solve benchmarks with low OSDD. High OSDD benchmarks are difficult because both tools try to reason about the execution of the system."
  - Source: [RTL-Repair PDF](https://par.nsf.gov/servlets/purl/10561674)
- "For all benchmarks repaired by RTL-Repair's synthesis engine, the OSDD provides a lower bound for how far the repair window needs to be expanded into the past." There is one stated exception: i2c_k1 needed only a window of 4 despite OSDD 13, because the buggy register was "updated only four cycles in the past". So the true determinant is the distance to the last relevant state update, not the first divergence. — [RTL-Repair PDF](https://par.nsf.gov/servlets/purl/10561674)
- OSDD = 0 does not mean easy. The decoder benchmarks are stateless (OSDD 0), but they still need wide windows ([0..10], [0..20]) "because future information needs to be taken into account", i.e., several input cycles are required to reveal all bugs. decoder_w2 (OSDD 0) got an incorrect repair. — [RTL-Repair PDF](https://par.nsf.gov/servlets/purl/10561674)
- Adaptive windowing design facts:
  - It starts symbolic unrolling at the first output divergence, with past and future window sizes of 0.
  - It grows the past window in steps of 2.
  - The maximum window is 32 cycles, after which it gives up.
  - It "went from timing out after one hour to being repaired in less than ten seconds" on one long-testbench benchmark.
  - One sdram failure (D12/D11 discussion) occurred because a different SMT solver's guard choice led to "a new failure outside the maximum repair window size".
  - Source: [RTL-Repair PDF](https://par.nsf.gov/servlets/purl/10561674)
- Related-work claim: prior symbolic hardware-repair approaches "focus on bugs that appear after one or two cycles of execution" and cannot handle long-running testbenches. — [RTL-Repair PDF](https://par.nsf.gov/servlets/purl/10561674)

**(a) EMPIRICAL but by construction: IFRA (Park, Mitra; post-silicon localization)**
- In the IFRA tech report (v1.2, Dec 2008), injected errors are split into two classes:
  - Case 3: "short error latency, where recorders successfully capture the history from error injection to failure manifestation".
  - Case 4: "long error latency, where 1024-entry recorders fail to capture the history". These are "pessimistically report[ed]" as "completely missed".
  - Source: [IFRA TR 1.2 (Stanford)](https://web.stanford.edu/group/rsg_csl/twiki/pub/Public/ValidationProjectsPublications/IFRA_TR_1.2.pdf)
- Results over 800 injections (cases 3+4): exactly localized 75%, correct with candidates 21%, completely missed 4%. The report does **not** say what fraction of the 4% are long-latency cases, and it does not break accuracy down by latency. Errors that did not trigger within 100K cycles were excluded. — [IFRA TR 1.2](https://web.stanford.edu/group/rsg_csl/twiki/pub/Public/ValidationProjectsPublications/IFRA_TR_1.2.pdf)

**(a) EMPIRICAL (latency reduction only, not difficulty): QED / Fast QED / Symbolic QED**
- Fast QED (Lin, Eswaran S, Kumar, Rentschler, Mitra; DATE 2015):
  - Traditional post-silicon tests "can incur very long error detection latencies, up to billions of clock cycles".
  - QED shortens these "to only few hundred or thousand clock cycles".
  - Fast QED retains latency benefits with "error detection latencies less than 7 thousand clock cycles, and detects most bugs with error detection latencies of only a few hundred cycles".
  - Source: [Fast QED, DATE 2015 PDF](https://past.date-conference.com/proceedings-archive/2015/pdf/1012.pdf)
- Symbolic QED (Singh, Lin, Barrett, Mitra; arXiv 1711.06541), OpenSPARC T2. Table 1 gives [min, avg, max] values:

  | Bug class | Trace length (instructions) | Trace length (cycles) | BMC runtime (min) | Detected and localized |
  |---|---|---|---|---|
  | Core | [3,3,3] | [13,15,16] | [22,46,90] | 100% |
  | Uncore | [3,4,4] | [14,22,29] | [78,164,188] | 100% |
  | Power management | [5,5,5] | [17,19,22] | [205,266,333] | 100% |

  - Traces are "up to 6 orders of magnitude shorter than traditional post-silicon validation tests … and up to 5 orders of magnitude shorter than QED tests".
  - A deadlock bug detected via a 10 s timeout corresponds to an EDL of "12 billion clock cycles" for the original test.
  - Source: [SQED arXiv PDF](https://arxiv.org/pdf/1711.06541)
  - Note: localization success is 100% everywhere and trace lengths vary little. There is no variance in which to measure a depth-vs-localization correlation. Debugging time against trace length is not measured.
- S2QED (Fadiheh, Urdahl, Nuthakki, Mitra, Barrett, Stoffel, Kunz; DATE 2018):
  - SQED's BMC runtime rises steeply with unrolling bound k on the Aquarius core: k=10 4:49, k=12 1:46:33, k=14 42:14:51.
  - S2QED can catch a bug "which needs an activation sequence of 14 instructions, with a bug trace of only one instruction". Original SQED "cannot detect this class of bugs".
  - Source: [S2QED DATE 2018 PDF (Barrett page)](https://theory.stanford.edu/~barrett/pubs/FUN+18.pdf)
  - This links depth to *formal detection cost*, not to debugging.
- E-QED (electrical bugs):
  - Localization narrows to "18 flip-flops on average for a design with ~1 Million flip-flops" in ~9 hours. That figure comes from a Mitra keynote abstract (snippet-only, not checked against the paper's tables): [HVC 2017 keynote](https://research.ibm.com/haifa/conferences/hvc2017/mitra.shtml).
  - The E-QED paper relies on QED tests typically achieving EDL ≤ 1,000 cycles. — [E-QED arXiv 1707.07671](https://arxiv.org/pdf/1707.07671) (snippet-level)

**(a) EMPIRICAL (proxy: combinational vs. sequential tier): Pecker (arXiv 2603.02583, Mar 2026)**
- Pecker defines "timing misalignment" as the gap between "the cycle in which a buggy statement is activated and the cycle in which its effect becomes observable at the output".
- Its benchmark of 12 designs and 41 bugs is tiered:
  - Easy: combinational (decoder, alu).
  - Medium: sequential (counter, lshift, led_controller, arbiter, fsm_full, fsm_16).
  - Hard: industrial (sdram_controller, sha3, i2c, reed_decoder).
- Baseline Top-5 accuracy drops on the medium (sequential) tier: Tarsel "from 92% to 56%", Wit-HW "from 75% to 44%", while Pecker drops "only 6%".
- Overall Top-1/3/5: Pecker 51/80/85%; Wit-HW 39/44/49%.
- Accuracy is **not** stratified by measured activation-to-observation latency. The paper's EMPC activation-cycle estimate matches the ground truth at an "average match ratio of 88%".
- Source: [Pecker arXiv HTML](https://arxiv.org/html/2603.02583v1)

**(b) QUALITATIVE**
- SQED: post-silicon bug localization challenges "are primarily caused by long error detection latencies"; "It is extremely difficult to trace that far back". Trace buffers typically record "only a few (~1,000) clock cycles". Long traces contain "extraneous instructions". — [SQED arXiv PDF](https://arxiv.org/pdf/1711.06541)
- Fast QED: "For bugs with error detection latencies longer than a few thousand clock cycles, it is extremely difficult to trace too far back in system operation history for debugging". — [Fast QED DATE 2015](https://past.date-conference.com/proceedings-archive/2015/pdf/1012.pdf)
- A Stanford QED dissertation abstract: long EDL "severely limits the effectiveness of existing post-silicon validation and debug approaches". — [Stanford purl](https://purl.stanford.edu/kq850gw1530) (snippet-only)
- S2QED: "the length of the bug trace strongly affects the complexity of the proof". — [S2QED PDF](https://theory.stanford.edu/~barrett/pubs/FUN+18.pdf)
- RTL-Repair grounds its adaptive windowing in developer practice: "human developers often start investigating a bug by looking at the signal values around the cycle where the first violation occurred … may assume that the state of the circuit a couple of cycles before the bug manifests is correct". This is an observation, not a user study. — [RTL-Repair PDF](https://par.nsf.gov/servlets/purl/10561674)
- Wit-HW (arXiv 2508.14414), brief:
  - It recasts localization as witness-test generation plus Ochiai SBFL over 41 bugs.
  - Its table includes asynchrony-type bugs, but results are not stratified by depth.
  - Source: [Wit-HW arXiv](https://arxiv.org/pdf/2508.14414) (snippet-level)

### Inferences
- From RTL-Repair Table 2 (my own tally, not stated by the authors): of the 27 rows with defined OSDD, the 3 with OSDD > 25 (73346, 74109, 2963) were repaired by 0/3 tools. Rows with OSDD ≤ 25: RTL-Repair correct on 16/24, CirFix correct on 7/24. So OSDD behaves like a **necessary-but-not-sufficient** condition. High OSDD predicts failure, but low OSDD does not predict success.
- The high-OSDD bugs all come from the largest designs with the longest testbenches (pairing: 74,149 cycles; reed: 166,166 cycles). Depth and design scale are confounded, and n = 3.
- First-error cycle (absolute time to first failure) is a weak predictor in that table. i2c_k1 failed at cycle 1238 and was repaired. pairing_k1 failed at cycle 775 with OSDD 2 and was not. The *relative* distance (state divergence to output divergence) is what the authors found informative.
- In the QED line, the depth-to-localizability link holds by construction. Localization tools (trace buffers ~1K cycles, IFRA 1024-entry recorders) fail when latency exceeds their window. Measured benefits are latency reductions and "localized in N hours". No paper there regresses debug time on latency.

### Gaps
- No human-subject study was found that measures debugging time against CEX length, EDL, or OSDD for hardware.
- No correlation coefficients (Spearman, Kendall, logistic) were found in any hardware paper for depth vs. localization or repair success.
- Not verified: Lonsing et al. FMCAD 2020; "Boosting the bounds of Symbolic QED" (believed Ganesan et al., DATE 2018); the ICCAD 2019 CoSA+SQED paper. I did not open them, so their titles, venues, and contents are unverified. I found no evidence that they measure debugging effort against trace length.
- BackSpace (De Paula et al.): not checked this session.
- IFRA CACM full text: returned 403, so a latency-stratified breakdown (if any) is unverified.
- CirFix (Ahmad et al., ASPLOS 2022): its own paper was not opened. CirFix outcomes here come only via RTL-Repair Table 2.

## Q2. How do LLM-based RTL debuggers report difficulty, and does any show success decreasing with cycles-to-failure or sequential depth?

### Takeaway
None of the LLM debuggers checked stratifies success by cycles-to-failure, CEX depth, or sequential depth. Difficulty is reported as aggregate pass rates, bug-type categories (syntax vs. functional, timing), code size, or benchmark tiers. Several 2025–2026 tools (VeriPilot, Pecker) build in temporal reasoning (earliest divergent cycle, activation-cycle estimation) and claim gains on "deep" designs, but give no depth-binned numbers.

### Cited Findings
- **VeriPilot** (Wang, Liu, Zhang, Zhang, Cheng, Li, Li; arXiv 2606.23759, Jun 2026):
  - It halts simulation at the "earliest divergent cycle" and builds a "state frontier" of earliest mismatched sequential states.
  - It claims the strongest gains "on complex Verilog designs with deep control and data dependencies", but does **not** stratify by divergence cycle or dependency depth.
  - Repair success: VeriPilot(GPT-4o) 91.23% on the Strider benchmark (57 pairs) and 85.71% on the CVDP cid16 debug subset. Standalone GPT-4o: 78.95% and 57.14%.
  - Internal inconsistency: the abstract says GPT-4o rose "from 54.3% to 85.71%", Table I gives 57.14% for the baseline, and the introduction says 77.1%.
  - Source: [VeriPilot arXiv HTML](https://arxiv.org/html/2606.23759v1)
- **Pecker** (2026): accuracy drops for prior localizers from combinational to sequential tiers, per Q1. — [Pecker](https://arxiv.org/html/2603.02583v1)
- **UVLLM**: on 331 error-injected instances it fixes 86.99% of syntax errors and 71.92% of functional errors, with a 10.42x average speedup over MEIC. No depth breakdown found. — [UVLLM arXiv 2411.16238](https://arxiv.org/pdf/2411.16238) (snippet-level)
- **MEIC** (ICCAD 2024): dataset of 178 common RTL programming errors; no depth stratification found. — [MEIC ACM DL](https://dl.acm.org/doi/10.1145/3676536.3676801) (snippet-level)
- **ARSP** (arXiv 2508.16517):
  - 77.92% pass@1, outperforming Strider and MEIC.
  - Its figure shows debugging success rate "decreases as the code scale increases". The difficulty axis is code size, not depth.
  - Source: [ARSP arXiv PDF](https://arxiv.org/pdf/2508.16517) (snippet-level)
- **Fixbench-RTL** (AsianHOST 2025):
  - LLMs do well on syntax but struggle with functional errors and real GitHub-issue bugs (Qwen2.5-Coder-32B ~10% repair on those).
  - Injected bugs "tend to be subtle".
  - No temporal-depth axis.
  - Source: [Fixbench-RTL PDF](https://ece.k-state.edu/research/hardware-security/papers/AsianHOST2025_Fixbench_RTL.pdf) (snippet-level)
- **ChipBench** (arXiv 2601.21448): its debugging tasks include a "timing" category (wrong-cycle values, blocking vs. non-blocking confusion). The category is labeled, but cycles-to-failure is not measured. — [ChipBench](https://arxiv.org/html/2601.21448v2) (snippet-level)
- **CVDP** (arXiv 2506.14074): 783 problems in 13 categories, with debugging as a category. Difficulty labels are easy/medium/hard tiers, not depth. — [CVDP arXiv](https://arxiv.org/pdf/2506.14074) (snippet-level)
- **Generation-side signals (not debugging)**:
  - A 2026 benchmarking study gives an example of LLM RTL lagging the reference "by one clock cycle", missed by linting and simple tests. — [Benchmarking LLMs for Verilog Design Flows, arXiv 2607.22759](https://arxiv.org/html/2607.22759v1) (snippet-level)
  - Feedback-driven generation work found machine-benchmark sequential problems *more* successful than combinational ones. So "sequential = harder" is not universal for generation. — [arXiv 2411.11856](https://arxiv.org/html/2411.11856v3) (snippet-level)

### Inferences
- The LLM-RTL-debug literature has adopted "earliest divergence cycle" as a working concept (VeriPilot, Pecker, RTL-Repair's window). But it has not yet published per-bug depth-vs-success curves. A paper that did so would be filling an open gap.
- Combinational-vs-sequential tier drops (Pecker) are the closest LLM/SBFL-era evidence. They are confounded with design size and LOC, since the tiers also differ in size.

### Gaps
- No LLM study was found that reports success as a function of cycles-to-failure, OSDD, CEX length, or register depth.
- Not opened this session: HDLdebugger, VeriDebug, RTLFixer (syntax-only, so likely irrelevant to depth), Strider's own paper, and VerilogEval/RTLLM debug splits.

## Q3. Is minimum counterexample depth from a miter/BMC used anywhere as a difficulty metric for benchmark construction?

### Takeaway
I found no benchmark that uses BMC/miter minimum CEX depth as a difficulty stratifier. Miters and equivalence checking are used for *correctness checking* and *output-divergence filtering*, not for difficulty grading. The closest construct is RTL-Repair's OSDD, which is computed by simulation against a golden design and reported per benchmark but not used to build a benchmark.

### Cited Findings
- **VeriBugBench** (Meng et al.; arXiv 2609.18022, Sep 2026): 2,608 instances across 45 projects, built by AST mutation, compilation, and simulation with output-divergence filtering.
  - It reports trace-diversity metrics: line coverage 73.57→76.77%, singleton-line trace uniqueness 0.1886→0.2445, temporal state entropy 1.57→1.94.
  - It does **not** define difficulty, does not use BMC/CEX depth, and evaluates no LLMs.
  - It notes qualitatively that a sequential defect "may require a temporal activation sequence and several cycles of propagation".
  - Source: [VeriBugBench arXiv HTML](https://arxiv.org/html/2609.18022v1)
- **NotSoTiny** (arXiv 2512.20823): builds a Yosys miter (XNOR of outputs) to check generated modules against golden references. It is used for correctness, not difficulty. — [NotSoTiny](https://arxiv.org/pdf/2512.20823) (snippet-level)
- **FormalRTL** (arXiv 2603.08738): feeds equivalence-checker CEXs to a debugging agent. CEX length is not reported as a difficulty metric. — [FormalRTL](https://arxiv.org/html/2603.08738v1) (snippet-level)
- **Open-source LLM-driven formal pipeline** (arXiv 2607.28877): uses formal CEX traces as the repair signal. "One of six benchmarks is repaired reliably". Failure modes include "temporal-logic bugs". — [arXiv 2607.28877](https://arxiv.org/html/2607.28877v1) (snippet-level)
- **RTL-Repair OSDD**: a per-benchmark, simulation-derived depth measure, computed post hoc for analysis. — [RTL-Repair PDF](https://par.nsf.gov/servlets/purl/10561674)

### Inferences
- Using "minimum miter-BMC CEX depth" as a benchmark difficulty axis appears to be **novel** (absence of evidence after targeted searches, not proof). The nearest precedents are OSDD (RTL-Repair) and earliest-divergence-cycle (VeriPilot/Pecker).
- Min CEX depth from a miter measures the *shortest* activation+propagation sequence from reset. That differs from first failure in a given testbench (RTL-Repair's "First Error" column). Bugs with low min-depth can still surface late in a weak testbench (e.g., i2c_k1's first error at cycle 1238).

### Gaps
- BugGen and the CirFix benchmark construction details were not opened. It is unverified whether they record any depth metric.

## Q4. Known confounds

### Takeaway
Depth measures are entangled with design size and testbench length, and with the formal tool's cost (BMC runtime grows steeply with the bound). They also depend on the specific stimulus (simulation first-failure vs. formal minimum). Combinational bugs can have depth 0 yet still need multi-cycle observation.

### Cited Findings
- **Size/testbench confound**: the only very-high-OSDD bugs in RTL-Repair Table 2 are in the largest benchmarks with the longest testbenches (pairing 74,149 TB cycles; reed 166,166 TB cycles). — [RTL-Repair PDF](https://par.nsf.gov/servlets/purl/10561674)
- **Code-size confound for LLMs**: ARSP reports success falling with code scale. — [ARSP](https://arxiv.org/pdf/2508.16517) (snippet-level)
- **Pecker tiers**: tiers mix sequentiality with LOC (combinational 25–37 LOC vs. industrial 420–4,366 LOC). — [Pecker](https://arxiv.org/html/2603.02583v1)
- **BMC depth vs. formal detection cost**:
  - SQED runtime on Aquarius rose from 4:49 (k=10) to 1:46:33 (k=12) to 42:14:51 (k=14). — [S2QED PDF](https://theory.stanford.edu/~barrett/pubs/FUN+18.pdf)
  - On OpenSPARC T2, BMC runtime grew across bug classes with longer traces (core 22–90 min; power management 205–333 min). This is also confounded by which subsystem is loaded. — [SQED arXiv PDF](https://arxiv.org/pdf/1711.06541)
- **Activation vs. observation decoupling**: S2QED shows a bug needing a 14-instruction activation sequence can be exposed by a 1-instruction trace from a symbolic initial state. So "CEX length" depends on the initial-state assumption (reset vs. symbolic). — [S2QED PDF](https://theory.stanford.edu/~barrett/pubs/FUN+18.pdf)
- **State-update recency vs. divergence distance**: in i2c_k1 the buggy register diverged 12 cycles before manifestation, but was "updated only four cycles in the past". Repair needed only 4 cycles of context. — [RTL-Repair PDF](https://par.nsf.gov/servlets/purl/10561674)
- **Zero-depth but multi-cycle observation**: stateless decoder bugs (OSDD 0) required repair windows of 10–20 cycles because multiple input vectors are needed to reveal the bug. — [RTL-Repair PDF](https://par.nsf.gov/servlets/purl/10561674)
- **Testbench strength**: "first error" depends on stimulus. Fast QED shows the same bugs have EDL of up to billions of cycles under original tests vs. hundreds to thousands under QED tests. — [Fast QED DATE 2015](https://past.date-conference.com/proceedings-archive/2015/pdf/1012.pdf)

### Inferences
- Any depth-vs-difficulty analysis should control for:
  - design size (LOC or flip-flop count) and testbench length
  - bug class (output-logic vs. state-update vs. control/FSM)
  - stimulus: report both formal min-depth and simulation first-failure cycle
- Partial correlation or stratified analysis would be needed. Raw correlations will likely be inflated by design size.

### Gaps
- No paper was found that disentangles depth from design size statistically.
- No paper was found that compares BMC min-CEX depth with simulation detection latency for the same bug set.
