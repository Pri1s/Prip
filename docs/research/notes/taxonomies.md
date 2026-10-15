# Taxonomies and classifications of RTL (Verilog/VHDL/SystemVerilog) bugs

Scope note: these notes catalogue bug taxonomies from the literature, the data behind each one, exact category names and frequencies where available, and how practical each is to assign automatically to single-fault, source-level mutants of small Verilog-2005 designs (the target benchmark: about 15 designs, about 70% sequential, mutants made by operators and filtered with a SymbiYosys equivalence miter). HWE-Bench and VeriBugBench are covered only briefly, for comparison.

Verification legend: **[full text]** means I read the paper's own text (PDF extracted locally or HTML). **[abstract/secondary]** means I saw only an abstract, a search snippet, or a third-party summary. Treat those claims as less certain.

---

## Q1. Empirical studies of real-world hardware bugs: category names and frequencies

### Takeaway
Six empirical schemes are usable. Three are syntactic fix-pattern taxonomies: Sudhakrishnan et al. (MSR 2008), Meng et al. (J. Supercomputing 2025), and the OpenTitan AST study. Two are root-cause/symptom taxonomies: Al-Asaad/Van Campenhout et al. (DLX/PUMA design errors) and Ma et al. (FPGA bugs, ASPLOS 2022). One is a difficulty-only split (CirFix, ASPLOS 2022). Errata studies (SPECS, RemembERR) and CWE classify at the architectural or security level and fit small single-module designs poorly. Every study agrees that assignment and expression errors dominate (roughly 30–55% of fixes), conditional/if errors come next (roughly 18–25%), and sensitivity-list or edge errors are rare (single-digit percent).

### Cited Findings

**1. Sudhakrishnan (spelled "Sudhakrishnan" in the PDF), Madhavan, Whitehead, Renau, "Understanding Bug Fix Patterns in Verilog", MSR 2008, pp. 39–42 [full text]**
- Data: the bug-fix history of 4 OpenCores Verilog projects (UART16550, OC8051, OR1K, Mem_ctrl). Bug-fix revisions were found by keyword search ("bug", "fixed") of CVS logs; buggy/fixed hunk pairs were then diffed and classified manually. The method follows Kai Pan's Java bug-fix-pattern work. — [MSR'08 PDF](https://masc.soe.ucsc.edu/docs/msr08.pdf)
- Excluded: changes to comments, synthesis directives, includes, params, cleanup, and formatting. — [MSR'08 PDF](https://masc.soe.ucsc.edu/docs/msr08.pdf)
- 25 patterns in 7 categories. Exact names and short names: — [MSR'08 PDF](https://masc.soe.ucsc.edu/docs/msr08.pdf)
  - **IF (if-related):** Addition of else related branch (IF_ABR); Addition of if branch (IF_APC); Change of if condition expression (IF_CC); Removal of else branch (IF_RBR); Removal of if branch (IF_RMV)
  - **MI (module instantiation):** different number of ports (MI_DNP); different values for the ports (MI_DCP)
  - **MD (module declaration):** different number of ports (MD_DNP)
  - **AS (assignment):** Change of expression for non-blocking assignment (NB_CE); for blocking assignment (B_CE); for assign statement (ASG_CE); Assign statement added/removed (ASG_ADD/ASG_RMV); Non-blocking statement added/removed (NB_ADD/NB_RMV); Blocking statement added/removed (B_ADD/B_RMV)
  - **SW (switch/case):** Addition or removal of case branches (SW_ABRP)
  - **CF ("class field", i.e. declarations):** Addition/removal of reg (RG_ADD/RG_RMV); Addition/removal of wire (WR_ADD/WR_RMV)
  - **AL (always):** Sensitivity list changes (AL_SE); Always added (AL_ADD); Always removed (AL_RMV)
- Category totals as pattern-instance counts (% of each project's instances), from Table 2. The table text is partly garbled; I re-checked these counts so that each column sums to its project total (128, 121, 108, 169): — [MSR'08 PDF](https://masc.soe.ucsc.edu/docs/msr08.pdf)

  | Category | UART16550 (n=128) | OC8051 (n=121) | OR1K (n=108) | Mem_ctrl (n=169) |
  |---|---|---|---|---|
  | AS | 70 (54.6%) | 53 (44%) | 40 (37%) | 49 (29%) |
  | IF | 31 (24%) | 27 (22.3%) | 19 (18%) | 43 (25%) |
  | CF | 6 (4.7%) | 18 (15%) | 17 (16%) | 22 (13%) |
  | AL | 10 (7.8%) | 9 (7.5%) | 3 (2.8%) | 35 (21%) |
  | MI | 2 (1.6%) | 6 (4.9%) | 16 (15%) | 10 (6%) |
  | MD | 4 (3.1%) | 5 (4.1%) | 11 (10%) | 7 (4.1%) |
  | SW | 5 | 3 | 2 | 3 (1.77%) |
- Headline ranges from the paper: assignment 29–55%, if 18–25%, MD+MI 4.7–25%, class field 4.7–16%, always 2.8–21%, case 1.8–4.6%. Only AS and IF ranks are consistent across projects. The sensitivity-list pattern (AL_SE) is small: 1, 2, 1, and 11 instances. — [MSR'08 PDF](https://masc.soe.ucsc.edu/docs/msr08.pdf)
- Many high-frequency patterns are additions (ASG_ADD 28 in UART; IF_APC; AL_ADD 20 in Mem_ctrl). The original bug was therefore missing logic, not wrong logic. — [MSR'08 PDF](https://masc.soe.ucsc.edu/docs/msr08.pdf)
- The paper cites Van Campenhout et al. (TODAES 1998) as the closest prior work and calls that taxonomy "ambiguous" compared with its own. — [MSR'08 PDF](https://masc.soe.ucsc.edu/docs/msr08.pdf)

**2. Al-Asaad, Van Campenhout, Hayes, Mudge, Brown: design-error collection, "High-Level Design Verification of Microprocessors via Error Modeling" (HLDVT'97 workshop version; journal version in ACM TODAES 3(4), 1998) [full text of workshop version]**
- Data: CVS was modified to prompt designers with a multiple-choice questionnaire at every commit (motivation, detection method, bug class, narrative). This makes it a designer-self-labeled, prospective dataset. Sources were four VLSI class projects implementing the DLX processor and the PUMA processor's fixed- and floating-point units, all in Verilog. — [hldvt97.pdf](https://www.ece.ucdavis.edu/~halasaad/Data/hldvt97.pdf)
- Questionnaire classes: combinational logic (wrong signal source, missing input(s), unconnected input(s)/output(s), conflicting outputs, wrong gate/module type, missing instance); sequential logic (extra/missing latch/flipflop, extra/missing state, wrong next state, other FSM error); statement (if, case, always); declaration; port list; expression/RHS (missing/extra term/factor, missing/extra inversion, wrong operator, wrong constant, completely wrong); buses (wrong bus width, wrong bit order); Verilog syntax error; conceptual error. — [hldvt97.pdf](https://www.ece.ucdavis.edu/~halasaad/Data/hldvt97.pdf)
- Table 1 relative frequencies (%), DLX / PUMA: Wrong signal source 29.9/28.4; Conceptual error 39.0/19.1; Case statement 0.0/10.1; Gate or module input 11.2/9.8; Wrong gate/module type 12.1/0.0; Wrong constant 0.4/5.7; Logical expression wrong 0.0/5.5; Missing input(s) 0.0/5.2; Verilog syntax error 0.0/3.0; Bit width error 0.0/2.2; If statement 1.1/1.6; Declaration statement 0.0/1.6; Always statement 0.4/1.4; FSM error 3.1/0.3; Wrong operator 1.7/0.3; Others 1.1/5.8. — [hldvt97.pdf](https://www.ece.ucdavis.edu/~halasaad/Data/hldvt97.pdf)
- The paper notes that compilers and synthesis tools already catch syntax, declaration, and port-list errors, plus bus width and sensitivity-list errors. — [hldvt97.pdf](https://www.ece.ucdavis.edu/~halasaad/Data/hldvt97.pdf)
- A follow-up article, "Collection and Analysis of Microprocessor Design Errors", IEEE Design & Test 17(4), 2000, pp. 51–60, exists, but I did not see its contents. — [search summary via dblp](https://dblp.org/pid/33/2813) [abstract/secondary]

**3. Ma, Zuo, Loughlin, Zhang, Quinn, Kasikci, "Debugging in the Brave New World of Reconfigurable Hardware", ASPLOS 2022 [full text]**
- Data: 68 functional bugs across 19 FPGA designs. Sources were HARP/HardCloud apps (SHA512, Reed-Solomon, grayscale), the Optimus hypervisor, ZipCPU-site designs (SDSPI, Xilinx AXI endpoints, FFT), popular GitHub FPGA projects (WiFi, GPGPU, two RISC-V CPUs, a Bitcoin miner, a NIC, libraries), and an FP adder. Bugs were mined from commits and issues and inspected manually. 20 bugs are reproducible in a public testbed. Timing (physical) bugs were excluded. — [NSF PAR PDF](https://par.nsf.gov/servlets/purl/10355397)
- 3 classes and 13 subclasses, modeled on Li et al.'s software bug study. Multi-class bugs go to "the most related and specific subclass". — [NSF PAR PDF](https://par.nsf.gov/servlets/purl/10355397)
  - **Data Mis-Access (28 bugs, 41%):** Buffer Overflow 5; Bit Truncation 12; Misindexing 5; Endianness Mismatch 1; Failure-to-Update 5 (forgetting to assign a signal, including on reset or initialization)
  - **Communication (17, 25%):** Deadlock 3; Producer-Consumer Mismatch 3; Signal Asynchrony 10 (data and valid, or two operands, not updated in the same cycle); Use-Without-Valid 1
  - **Semantic (23, 34%):** Protocol Violation 3; API Misuse 3 (e.g. swapped port connections); Incomplete Implementation 7; Erroneous Expression 10 (5 control-flow, 5 data-flow)
  - Symptoms column: App Stuck / Data Loss / Incorrect Output / External. — [NSF PAR PDF](https://par.nsf.gov/servlets/purl/10355397)
- RTL-Repair later reused 12 of the 20 reproducible bugs (IDs D4, D8, D9, D11, D12, D13, C1, C3, C4, S1.R, S1.B, S2, S3). — [RTL-Repair, ASPLOS'24 (NSF PAR)](https://par.nsf.gov/servlets/purl/10561674)

**4. CirFix: Ahmad, Huang, Weimer, ASPLOS 2022 [full text]**
- Data: 32 defect scenarios in 11 Verilog projects: 6 course projects and 5 OpenCores/GitHub cores such as i2c, sha3, tate_pairing, reed_solomon_decoder, and sdram_controller. Defects were transplanted by 3 hardware experts (2 industry, 1 academia, 19 years combined), based on real bugs they had seen. Experts were asked for variety that matches real-life frequency. — [CirFix PDF](https://par.nsf.gov/servlets/purl/10421496); [CirFix GP-bib](https://gpbib.cs.ucl.ac.uk/gp-html/DBLP_conf_asplos_Ahmad0W22.html)
- The only classification is by difficulty: **Category 1 ("easy")**, simpler, higher-level mistakes, 19 defects; **Category 2 ("hard")**, more intricate errors needing more effort to diagnose or fix, 13 defects. The expert labeled each defect. — [CirFix PDF](https://par.nsf.gov/servlets/purl/10421496)
- Repair templates cover 4 "defect categories". Three come from Sudhakrishnan et al.'s top patterns; one ("Numeric") comes from the authors' experience. — [CirFix PDF](https://par.nsf.gov/servlets/purl/10421496)
  - **Conditionals:** negate a condition
  - **Sensitivity Lists:** trigger on negedge, posedge, any change, or level
  - **Assignments:** blocking↔non-blocking
  - **Numeric:** increment or decrement an identifier by 1
- Defect descriptions in Table 3 (cat): decoder "Two separate numeric errors" (1), "Incorrect assignment" (2); counter "Incorrect sensitivity list" (1), "Incorrect reset" (1), "Incorrect incremental of counter" (1); flip_flop "Incorrect conditional" (1), "Branches of if-statement swapped" (1); fsm_full "Incorrect case statement" (1), "Incorrectly blocking assignments" (1), "Assignment to next state and default in case statement omitted" (2), "Assignment to next state omitted, incorrect sensitivity list" (2); lshift_reg "Incorrect blocking assignment" (1), "Incorrect conditional" (1), "Incorrect sensitivity list" (1); mux_4_1 "1 bit instead of 4 bit output" (1), "Hex instead of binary constants" (1), "Three separate numeric errors" (2); i2c "Incorrect sensitivity list" (2), "Incorrect address assignment" (2), "No command acknowledgement" (2); sha3 "Off-by-one error in loop" (1), "Incorrect bitwise negation" (1), "Incorrect assignment to wires" (2), "Skipped buffer overflow check" (2); tate_pairing "Incorrect logic for bitshifting" (1), "Incorrect operator for bitshifting" (1), "Incorrect instantiation of modules" (2); reed_solomon "Insufficient register size for decimal values" (1), "Incorrect sensitivity list for reset" (2); sdram "Numeric error in definitions" (1), "Incorrect case statement" (2), "Incorrect assignments to registers during synchronous reset" (2). — [CirFix PDF](https://par.nsf.gov/servlets/purl/10421496)
- Results: 21/32 plausible repairs, 16/32 correct. — [CirFix PDF](https://par.nsf.gov/servlets/purl/10421496)

**5. RTL-Repair: Laeufer, Fajardo, Ahuja, Iyer, Nikolić, Sen, ASPLOS 2024 [full text]**
- It has no bug taxonomy of its own. It classifies bugs implicitly by which of 3 symbolic templates repairs them: **Replace Literals**, **Add Guard**, **Conditional Overwrite**. A lint-driven preprocessing step fixes blocking/non-blocking misuse. On CirFix, the templates do not overlap: "only a single repair template per benchmark generates a repair". Each template fixes 3–4 benchmarks, and preprocessing alone fixes 5. — [RTL-Repair PDF](https://par.nsf.gov/servlets/purl/10561674)
- On the real bugs from Ma et al.: 12 of 20 were usable (the rest had non-synthesizable or SystemVerilog code, or no ground truth). 9 of 12 passed the testbench. Fix quality was graded A–D: 2 matched ground truth, 1 partially, 4 overfit, 3 differed strongly. — [RTL-Repair PDF](https://par.nsf.gov/servlets/purl/10561674)

**6. Meng, Ji, Zhang, He, Yang, Chen, Wang, Yu, Zhao, Wu, "RTL design flaws revisited: a data-driven study of systematic bug patterns in Verilog code", J. Supercomputing 81(14):1321, 2025 [secondary: read via VeriBugBench's summary; the Springer page was paywalled or redirected]**
- Data: an AST-based tool over more than 300 open-source Verilog projects and more than 15,000 commits yielded more than 1,000 bug-fix commits. — [ResearchGate/Springer listing via search](https://www.researchgate.net/publication/395387474_Rtl_design_flaws_revisited_a_data-driven_study_of_systematic_bug_patterns_in_Verilog_code) [abstract/secondary]
- VeriBugBench states: 1,298 bug-fix commit records from 300 projects. The taxonomy has 8,756 expression-level and 12,786 statement/root-level AST edit-action records. Each edit is ⟨action ∈ {update, insert, delete, move}, node, context⟩. — [VeriBugBench arXiv 2609.18022](https://arxiv.org/pdf/2609.18022)
- Expression-level distribution, as reported in VeriBugBench Table I: — [VeriBugBench](https://arxiv.org/pdf/2609.18022)
  - InfixExpression/PrefixExpression/TERNARY: 4,710 (53.79%)
  - MemberAccessing/DOWNTO (bit-select/part-select): 1,873 (21.39%)
  - Assignment: 1,325 (15.13%)
  - RISING/FALLING (edge): 287 (3.28%)
  - HdlDirection (port direction): 112 (1.28%)
  - FunctionCall and PARAMETRIZATION: the remaining 449 records (≈5.1%, my arithmetic)
- This is a purely syntactic taxonomy, assigned automatically from AST diffs. — [VeriBugBench](https://arxiv.org/pdf/2609.18022)

**7. OpenTitan security-bug study, "An Investigation of Hardware Security Bug Characteristics in Open-Source Projects", arXiv 2402.00684 (2024) [HTML, read through a summarizing fetch]**
- Data: 516 OpenTitan GitHub issues, of which 235 were RTL bugs (45.5%). After removing those with no findable fix or that were not design bugs, 170 remained. Security vs. functional was labeled manually using the C/I/A threat model; 52.9% are security bugs (the abstract says 53%). — [arXiv HTML](https://arxiv.org/html/2402.00684); [abstract](https://arxiv.org/abs/2402.00684)
- Security impact (multi-label): Confidentiality 34 (37.8%), Integrity 47 (52.2%), Availability 43 (47.8%). The Cryptography IP group (aes, keymgr, hmac, kmac, csrng, edn) holds the most security bugs. — [arXiv HTML](https://arxiv.org/html/2402.00684)
- AST (Slang) node types changed by the fix, as % of fixes: assignments 50.1%, conditional 24.8%, always_ff 23.2%, ternary 14.3%, hierarchy instantiation 12.4%, generate 5.6%, always_comb 4.3%, module declaration 1.2%. "No proportional difference" between functional and security fixes. 55% of fixes touch only one file. — [arXiv HTML](https://arxiv.org/html/2402.00684); [abstract](https://arxiv.org/abs/2402.00684)
- Authors: a reference list cites them as "Ah-kiow and Tan (2024)"; I did not confirm this on the arXiv page. — [search summary](https://arxiv.org/pdf/2402.00684) [secondary]

**8. Processor errata studies (architectural level)**
- **SPECS** (Hicks, Sturton, King, Smith; ASPLOS 2015) [full text]: of 301 AMD errata (2006–2013), 28 are security-critical. They fall into 5 classes: IU (invalid register update) 64%, with sub-types IL (illegal) and IX (incorrect); EI (execute incorrect instruction) 14%; MA (arbitrary memory access) 11%; IR (incorrect results) 7%; XR (exception related) 4%. — [hicks15.pdf](https://bob.cs.ucdavis.edu/assets/dl/hicks15.pdf)
- **RemembERR** (Solt, Jattke, Razavi; MICRO 2022) [full text]: 2,563 errata from all Intel Core and AMD CPUs since 2008, merged to 1,128 unique errata. Each is annotated with **Triggers** (conjunctive), **Contexts**, and **Observable effects** (disjunctive), on abstract and class levels, 60 categories in total. Trigger classes: Trg_MBR (boundary), Trg_MOP (memory op), Trg_FLT (exceptions/faults), Trg_PRV (privilege transitions), Trg_CFG (dynamic config), Trg_POW (power states), Trg_EXT (external: reset, PCIe, USB, DRAM, IOMMU, bus), Trg_FEA (features). Context classes: Ctx_PRV, Ctx_FEA, Ctx_PHY. Effect classes include Eff_HNG, Eff_FLT, Eff_CRP, Eff_EXT. — [RemembERR PDF](https://comsec.ethz.ch/wp-content/files/rememberr_micro22.pdf); [repo](https://github.com/comsec-group/rememberr)
- **Phoenix** (Sarangi, Tiwari, Torrellas; MICRO 2006) characterized RTL defects in 10 processors and found the memory subsystem especially problematic. I did not find exact percentages. — [Illinois IDEALS](https://www.ideals.illinois.edu/items/11293); [MIT Tech Review](https://www.technologyreview.com/2007/04/10/225995/efficient-hardware-repair/) [secondary]

**9. Security weakness taxonomy: CWE Hardware Design view (CWE-1194)**
- Categories: 1195 Manufacturing & Life Cycle; 1196 Security Flow; 1197 Integration; 1198 Privilege Separation & Access Control; 1199 General Circuit & Logic Design; 1201 Core & Compute; 1202 Memory & Storage; 1203 Peripherals/On-chip Fabric/IO; 1205 Security Primitives & Crypto; 1206 Power/Clock/Thermal/Reset; 1207 Debug & Test. The page was truncated, so the list may be incomplete. — [CWE-1194](https://cwe.mitre.org/data/definitions/1194.html)
- CWE-1199 members: 1209 Failure to Disable Reserved Bits; 1221 Incorrect Register Defaults or Module Parameters; 1223 Race Condition for Write-Once Attributes; 1224 Improper Restriction of Write-Once Bit Fields; 1231 Improper Prevention of Lock Bit Modification; 1232 Improper Lock Behavior After Power State Transition; 1233 Security-Sensitive Hardware Controls with Missing Lock Bit Protection; 1234 Hardware Internal or Debug Modes Allow Override of Locks; 1245 Improper FSMs in Hardware Logic; 1250 Improper Preservation of Consistency Between Independent Representations of Shared State; 1253 Incorrect Selection of Fuse Values; 1254 Incorrect Comparison Logic Granularity; 1261 Improper Handling of Single Event Upsets; 1298 Hardware Logic Contains Race Conditions. MITRE marks the category itself as prohibited for mapping; the member CWEs should be used instead. — [CWE-1199](https://cwe.mitre.org/data/definitions/1199.html)
- Hack@DAC: I found no official per-bug CWE table. Papers cite individual instances, e.g. CWE-1191 (JTAG checks only the low 32 bits of a secret) and CWE-1233 (DMA registers without lock bit) in the Hack@DAC'21 OpenPiton SoC. The CWEAT static analysis reported 53 potential weaknesses, 11 confirmed, and lacked a complete ground-truth list. — [LASHED arXiv 2504.21770](https://arxiv.org/pdf/2504.21770); [CWEAT arXiv 2209.01291](https://arxiv.org/pdf/2209.01291) [abstract/secondary]

**10. HWE-Bench and VeriBugBench (for comparison only)**
- HWE-Bench labels bugs by "dominant failure mode": functional logic errors, specification deviations, interface and protocol violations, timing and synchronization issues, configuration or integration errors, plus a small software/firmware group (SW: HW Config, SW: HW Interact, SW: FW Logic). Labels come from a "semantic filter, implemented as an LLM-based classification agent". Logic is the largest category; Spec dominates in CVA6 and Ibex; OpenTitan is the most diverse. — [HWE-Bench arXiv 2604.14709](https://arxiv.org/abs/2604.14709) (read from the PDF text)
- VeriBugBench: 19 inverse operators in 5 families (Expression, Bit-vector & access, Assignment, Timing, Port), derived from Meng et al. — [VeriBugBench](https://arxiv.org/pdf/2609.18022)

### Inferences
- Across the four syntactic studies (MSR'08, Meng 2025, OpenTitan 2024, Al-Asaad's "wrong signal source"/expression rows), the most robust shape is that expression/assignment RHS errors are the plurality (29–55%), conditionals come next (≈18–25%), and edge/sensitivity errors are a few percent. A mutant benchmark whose operator mix is far from this (for example, many edge flips) would not be "realistic" by any of these baselines.
- Omission ("missing assignment / missing if branch / missing reset", Ma's Failure-to-Update and Incomplete Implementation, MSR'08's *_ADD patterns) is a large real-world class. Replace-only operators (Certitude/MCY style) cannot produce it; delete operators can.
- Al-Asaad's "Conceptual error" (19–39%) and Ma's "Incomplete Implementation" (10%) are, by definition, not single-token mutants. Single-fault mutant benchmarks systematically leave this mass out, and the notes should say so.

### Gaps
- I could not open Meng et al. (Springer) directly. Its statement-level distribution (12,786 records) and any semantic labels are known only via VeriBugBench.
- I did not retrieve the IEEE D&T 2000 "Collection and Analysis of Microprocessor Design Errors" breakdown, or Velev's ITC-era collection of formal-verification bugs.
- No exact percentages from Phoenix (MICRO 2006) or Narayanasamy et al. (ICCD 2006) errata studies.
- No complete Hack@DAC bug-to-CWE list was found. The HardFails (arXiv 1812.00197) bug-property classes (black-box abstraction, timing flow, non-register state) were seen only in a search snippet. — [HardFails](https://arxiv.org/pdf/1812.00197) [secondary]

---

## Q2. Hardware mutation operator sets and whether they map to a taxonomy

### Takeaway
Operator sets fall into three tiers. (a) Netlist or port-level fault models: Yosys/MCY `mutate`, Certitude port faults, and Al-Asaad's INV/SSL. These map to the classic design-error models, not to source-level taxonomies. (b) Source-level operator-swap sets: Fellner et al., LintLLM, the TODAES 2025 LLM-debugging paper. These are syntactic and have no stated empirical basis. (c) Empirically grounded sets: CirFix templates (from MSR'08), VeriBugBench's 19 operators (from Meng 2025), and BugGen's 8 LLM mutation classes. Only CirFix and VeriBugBench state an explicit mapping to an empirical taxonomy.

### Cited Findings
- **Yosys `mutate` / MCY:** MCY mutates individual signals in a post-synthesis netlist and keeps only mutants that formal checking shows can change outputs. — [MCY docs](https://mcy.readthedocs.io/en/latest/)
- `mutate` modes in the source: `inv` (invert a cell port bit), `const0`/`const1` (force a bit to a constant), `cnot0`/`cnot1` (XOR/XNOR a port bit with another bit of the same port), and `none`. Selection uses `-list N` even sampling with weighted queues (weight_pq_w/b/c/s, module-level variants) and coverage weighting (weight_cover default 500, pick_cover_prcnt 80). — [yosys mutate.cc](https://raw.githubusercontent.com/YosysHQ/yosys/main/passes/sat/mutate.cc)
- **Al-Asaad/Van Campenhout error models** derived from their bug data: MSE (module substitution), MCE (module count), BOE (bus order), BCE (bus count), BSE (bus source, i.e. wrong signal source), and BDE (bus driver). For behavioral code: LCE (case label count), ESE (expression structure: extra/missing term, inversion, wrong operator, wrong constant), SCE (state count), and NSE (next-state error). Each model points back to numbered error categories in Table 1, for example BSE → cat. 1 and ESE → cats. 3, 6, 7, 11, 15. — [hldvt97.pdf](https://www.ece.ucdavis.edu/~halasaad/Data/hldvt97.pdf)
- **Certitude (Synopsys, from Certess):** faults include port faults (stuck-at-0, stuck-at-1, negated), condition faults (forced true, forced false, negated), dead-code faults (dead assignment, dead else), and operator swaps. Results are classed as Non-Activated / Non-Propagated / Non-Detected / Detected. — [DVCon "Who's watching the watchmen"](https://dvcon-proceedings.org/wp-content/uploads/whos-watching-the-watchmen-the-time-has-come-to-objectively-measure-the-quality-of-your-verification.pdf); [Design-Reuse brief](https://us.design-reuse.com/articles/20223/functional-qualification.html) [secondary; not the full vendor fault list]
- **Fellner, Tabaei Befrouei, Weissenbacher, "Mutation Testing with Hyperproperties"** (SEFM 2019 / SoSyM 2021) [full text], Verilog operators:
  - Arithmetic: exchange binary +/−; exchange unary +/−
  - Relations: exchange ==/!=; exchange <, ≤, >, ≥
  - Boolean: exchange !/~; drop !/~; exchange &&, ||, &, |, XOR, XNOR
  - Assignments: exchange = and <=
  - Constants: integer c → 0, 1, c+1, c−1; bit-vector → all-0s or all-1s
  - Source: — [arXiv 1907.07368](https://arxiv.org/pdf/1907.07368)
- In the same paper, model checking found that **33.21% of Verilog mutants were equivalent on average** (σ 32.47%, range 0–95.3%) across 16 Verilog models. The average mutation score was 56.82%. — [arXiv 1907.07368](https://arxiv.org/pdf/1907.07368)
- **CirFix templates** (Conditionals / Sensitivity Lists / Assignments / Numeric) are explicitly mapped to MSR'08's top patterns. — [CirFix PDF](https://par.nsf.gov/servlets/purl/10421496)
- **VeriBugBench**: 19 operators, each the inverse of an empirical repair edit:
  - Expression: ExprUpdate, ExprInsert, ExprDelete
  - Bit-vector & access: PartselectUpdate/Insert/Delete; PointerUpdate/Insert/Delete
  - Assignment: NSubUpdate, NSubInsert, NSubDelete, NSubMove; AssignN2B, AssignB2N
  - Timing: EdgeFlip, EdgeInsert, EdgeDelete
  - Port: IOFlip
  - Source: — [VeriBugBench](https://arxiv.org/pdf/2609.18022)
- **BugGen** (Jasper, Luu et al., Texas A&M + Infineon, arXiv 2506.10501): LLM agents mutate OpenTitan IPs using a "mutation index" of 8 classes: Missing assignment; Bitwise corruption; Logic bug; Wrong assignment; Incorrect data size; Adjacent field swap; Loop modification; FSM transition error. Of 1,000 mutations: 538 detected, 358 syntax failures, 104 undetected. No per-class distribution is reported. — [BugGen HTML](https://arxiv.org/html/2506.10501v1)
- **LintLLM** (arXiv 2502.10815): 13 injection rules (e.g. input↔output, reg↔wire, posedge↔negedge, width change). The benchmark has 11 defect categories with counts summing to 90: Syntax Structure 6; Signal Usage 13; Sensitivity List 16; Reserved words 3; Race or Hazard 11; Port Type 4; Operators 7; Module Instances 8; Logic Synthesis 6; Combinational or Sequential 2; Bit width Usage 14. The rules are not explicitly mapped to the categories. — [LintLLM HTML](https://arxiv.org/html/2502.10815v1)
- **"LLM-assisted Bug Identification and Correction for Verilog HDL"** (ACM, DOI 10.1145/3733237): 9 operators (logical, relational, arithmetic, constant, conditional, stuck-at, …), extending a 5-operator set from prior work. — [ACM DL](https://dl.acm.org/doi/full/10.1145/3733237) [secondary: search snippet only]
- **FixBench-RTL** (AsianHOST 2025): 100 cases labeled Syntax / Functional / Security-relevant, from LLM synthesis, GitHub fixes, and targeted injection. — [FixBench-RTL PDF](https://ece.k-state.edu/research/hardware-security/papers/AsianHOST2025_Fixbench_RTL.pdf) [secondary: search snippet only]
- **Dictionary-Guided Mutation Operators for Automated HDL Repair** (Mastora and Sullivan, arXiv 2609.01775): category-constrained token substitution, insertion, and deletion from ANTLR-derived, design-specific vocabularies; evaluated on CirFix (14 correct repairs). The abstract gives no taxonomy. — [arXiv abs](https://arxiv.org/abs/2609.01775) [abstract only]

### Inferences
- MCY's `inv` and `const0/1` are exactly Al-Asaad's INV and SSL modeled errors. In Al-Asaad's DLX decode-stage experiment, tests that fully covered INV or SSL errors caught 92% of the actual design errors. Netlist-level operators are therefore a reasonable test-adequacy proxy, but labels for them can only be classic error-model names (INV/SSL/BSE), not source-level patterns. — data from [hldvt97.pdf Table 2](https://www.ece.ucdavis.edu/~halasaad/Data/hldvt97.pdf)
- For a source-level Verilog-2005 operator set, the cleanest deterministic label vocabulary is a union of three taxonomies, each keyed directly by the operator:
  - VeriBugBench/Meng construct families (Expression / Bit-vector & access / Assignment / Timing / Port)
  - MSR'08 pattern short names (e.g. relational swap inside an `if` condition → IF_CC; RHS change of `<=` → NB_CE; delete of `assign` → inverse of ASG_ADD)
  - Al-Asaad expression/RHS sub-classes (wrong operator, wrong constant, missing/extra term, missing/extra inversion, wrong signal source)
- Fellner et al.'s 33% equivalent-mutant rate gives a prior for how much a SymbiYosys miter will discard. It depends heavily on the design (0–95%).

### Gaps
- No public, authoritative Certitude fault-type catalogue was found; only conference slides were.
- VHDL mutation-operator papers (e.g. Al-Hayek/Robach-era VHDL work, SystemC mutation by Bombieri et al.) were not retrieved.
- BugGen's per-class validation accuracy (its Fig. 2) was not available as text.

---

## Q3. Syntactic vs. semantic/behavioral taxonomies, and which can be assigned by rule

### Takeaway
Syntactic taxonomies (MSR'08, Meng/VeriBugBench, the OpenTitan AST study, Fellner/LintLLM operator classes, CirFix templates) can be assigned deterministically from the mutation operator plus its AST context. Semantic taxonomies (Ma et al., HWE-Bench, CWE, SPECS, RemembERR) were all labeled by humans or an LLM. They are only partly derivable by rule, and even two human labelers agreed only about 80% of the time (RemembERR). Al-Asaad's scheme is a hybrid: designers self-reported it, but most of its leaf classes are syntactic enough to derive by rule.

### Cited Findings
- MSR'08 says its fix patterns were "manually define[d]", but it frames them as "automatically extractable", and Pan's Java equivalents were extracted automatically. — [MSR'08 PDF](https://masc.soe.ucsc.edu/docs/msr08.pdf)
- Meng/VeriBugBench and the OpenTitan study assign syntactic categories fully automatically from AST diffs (ASTDiff; Slang visitor node counts). — [VeriBugBench](https://arxiv.org/pdf/2609.18022); [OpenTitan study](https://arxiv.org/html/2402.00684)
- Ma et al. clustered by root cause and symptom manually. They say bugs can belong to several classes ("a buffer overflow may arise because of an erroneous expression") and settled this by choosing the "most related and specific subclass". — [NSF PAR PDF](https://par.nsf.gov/servlets/purl/10355397)
- HWE-Bench uses an LLM-based classification agent (the "semantic filter") to assign its five root-cause classes. I did not see an agreement or validation statistic in the text I read. — [HWE-Bench](https://arxiv.org/abs/2604.14709)
- RemembERR: two humans classified independently and resolved mismatches. Agreement was "generally above 80%". Mismatches came from human error, imprecise errata text, and ambiguous categories. Conservative regular-expression filtering cut decisions from 1,128×60 = 67,680 to 2,064 per human; a regex highlighting tool reduced effort to about 30 hours per human. — [RemembERR PDF](https://comsec.ethz.ch/wp-content/files/rememberr_micro22.pdf)
- OpenTitan security vs. functional was labeled manually, consulting the fix when the report was unclear. — [arXiv HTML](https://arxiv.org/html/2402.00684)
- CirFix Cat 1/2 is expert judgement with no operational definition beyond "simpler, higher-level" vs. "more intricate". — [CirFix PDF](https://par.nsf.gov/servlets/purl/10421496)
- Certitude's Activated/Propagated/Detected classes are behavioral and computed automatically from simulation. They classify the testbench's response to a fault, not the fault itself. — [DVCon slides](https://dvcon-proceedings.org/wp-content/uploads/whos-watching-the-watchmen-the-time-has-come-to-objectively-measure-the-quality-of-your-verification.pdf)

### Inferences: practicality per taxonomy for the target benchmark (single-fault source mutants, small Verilog-2005, SBY-filtered)

| Taxonomy | Type | Auto-assignable from operator? | Notes for this benchmark |
|---|---|---|---|
| Meng 2025 / VeriBugBench families | syntactic | **Yes, deterministic** | 1:1 with operator family; has published real-world prevalence (53.8/21.4/15.1/3.3/1.3%) for weighting |
| MSR'08 25 patterns / 7 categories | syntactic (fix-side) | **Yes**, with AST context (enclosing if/case/always/assign; `=` vs `<=`) | Invert direction (fix ADD ↔ mutant delete). CF (reg/wire add/remove) and MD/MI port-count patterns are mostly irrelevant for single-module mutants that must stay equivalent at the I/O level |
| Al-Asaad/Van Campenhout leaf classes | mixed | **Mostly yes**: wrong operator, wrong constant, missing/extra inversion, missing/extra term, wrong signal source, bit width, if/case/always statement. **Partly**: FSM error (needs FSM detection, e.g. via Yosys FSM extraction). **No**: conceptual error | Has empirical DLX/PUMA frequencies; old, small, student and research CPUs |
| Ma et al. 3×13 | semantic/root-cause | **Partial by rule**: Bit Truncation ← width/part-select ops; Misindexing ← index/part-select update; Erroneous Expression (control vs data) ← expression op inside condition vs RHS; Failure-to-Update ← assignment delete or reset-branch mutation; API Misuse ← port-connection swap. **Needs LLM/human**: Signal Asynchrony, Use-Without-Valid, Producer-Consumer, Deadlock, Protocol Violation (need valid/ready or protocol semantics); Incomplete Implementation (not producible by single mutants) | Best real-bug semantic scheme for small designs; communication subclasses are rare in single-module benchmarks without handshakes |
| HWE-Bench 5 classes | semantic (dominant failure mode) | **Weak**: almost all single-token mutants fall under "functional logic". Timing/Sync can be approximated by rule (edge, sensitivity, `=`↔`<=`, register-stage changes). Spec deviation and Config/Integration need a spec or multi-file context | Low discriminative power at this scale |
| CWE-1194/1199 | security weakness | **Mostly N/A**. Rule-mappable edge cases: reset-value mutation → CWE-1221 (Incorrect Register Defaults); FSM next-state mutation → CWE-1245; comparison-width mutation → CWE-1254 | Only meaningful if designs carry security assets |
| SPECS / RemembERR | architectural (errata) | **No**: written for ISA-level or system-level behavior | RemembERR's trigger/context/effect framing is reusable conceptually, and can be computed from SBY counterexample traces (see Q4) |
| CirFix Cat 1/2 | difficulty, expert | **No** (subjective) | Replace with measured difficulty proxies |
| Certitude A/P/D | behavioral (testbench response) | **Yes**, by simulation | SBY miter filtering already guarantees each mutant is distinguishable at outputs. Testbench-relative A/P/D can be added if a reference testbench exists |

### Gaps
- No study reports inter-rater agreement for Ma et al.'s or HWE-Bench's labels. Only RemembERR (errata) reports agreement figures.
- No paper was found that evaluates LLM-assigned RTL bug root-cause labels against human labels.

---

## Q4. Validated mappings between syntactic patterns and semantic root causes

### Takeaway
I found no study that quantitatively validates a mapping from syntactic fix or mutation pattern to semantic root cause for RTL. What exists falls into three groups:
- **Hand-made mappings with partial empirical support.** Al-Asaad's error models map to error categories, and coverage experiments show that INV/SSL-adequate tests catch 92% of actual DLX decode errors. CirFix templates map to MSR'08 patterns.
- **Disjoint template coverage.** RTL-Repair's three templates each repair a disjoint subset of bugs, which acts as an implicit partition.
- **Contrary evidence.** The OpenTitan finding of "no proportional difference" in AST node types between functional and security fixes suggests that syntax alone does not predict semantic class.

### Cited Findings
- Al-Asaad et al. map each error model to Table 1 category numbers: BSE → 1; ESE → 3, 6, 7, 11, 15; SCE/NSE → 14; MSE → 5; BCE → 4, 8. They state that conceptual errors "cannot be easily modeled" but often show up as combinations of modeled errors. — [hldvt97.pdf](https://www.ece.ucdavis.edu/~halasaad/Data/hldvt97.pdf)
- DLX decode-stage coverage (Table 2): tests targeting INV covered 100% INV, 82% SSL, and 92% actual errors. Tests targeting SSL covered 100% INV, 100% SSL, and 92% actual. Tests targeting actual errors covered only 72% INV and 53% SSL. — [hldvt97.pdf](https://www.ece.ucdavis.edu/~halasaad/Data/hldvt97.pdf)
- RTL-Repair: "the repair templates do not overlap; only a single repair template per benchmark generates a repair". — [RTL-Repair PDF](https://par.nsf.gov/servlets/purl/10561674)
- OpenTitan: functional and security fixes show "no proportional difference" across AST node types. — [arXiv HTML](https://arxiv.org/html/2402.00684)
- Ma et al. give per-subclass "Fixes" descriptions that act as informal semantic-to-syntactic mappings. Examples: misindexing → "correcting the index"; erroneous expression → "correcting the erroneous expression"; API misuse → "changing signal connections and the module's configuration"; signal asynchrony → add a delay register so valid and data line up. — [NSF PAR PDF](https://par.nsf.gov/servlets/purl/10355397)
- VeriBugBench maps empirical repair edits ⟨action, node, context⟩ to inverse operators. This is a syntactic-to-syntactic mapping, not a semantic one. — [VeriBugBench](https://arxiv.org/pdf/2609.18022)
- RemembERR treats triggers as conjunctive and observations as disjunctive. It uses the number of necessary trigger conditions as a proxy for how hard a bug is to trigger. — [RemembERR PDF](https://comsec.ethz.ch/wp-content/files/rememberr_micro22.pdf)

### Inferences (proposals, not findings)
- A defensible approach for the target benchmark is to use **two label layers plus measured behavior**:
  1. A deterministic syntactic label: operator → Meng/VeriBugBench family, MSR'08 pattern, and Al-Asaad leaf class.
  2. A rule-derived semantic label using static context available from Yosys/AST. Examples:
     - mutation inside the reset branch → "reset/initialization" (Ma Failure-to-Update; CWE-1221)
     - mutation in FSM next-state logic → "FSM error" (Al-Asaad 14; CWE-1245)
     - width or part-select change → Bit Truncation/Misindexing
     - edge, sensitivity, or `=`/`<=` change → Timing/Sync
     - mutation inside an `if`/`case` condition → control-flow Erroneous Expression
     - mutation in an RHS → data-flow Erroneous Expression
     - everything else → functional logic
  3. Automatically computed behavioral attributes from the SymbiYosys miter counterexample, analogous to Certitude A/P/D and RemembERR triggers: minimum cycles to output divergence (BMC depth), whether divergence needs reset or a particular input sequence, number of diverging outputs, and combinational vs. sequential.
- If an LLM is used to assign HWE-Bench- or Ma-style semantic classes, the evidence above (RemembERR ≈80% human-human agreement; Ma's acknowledged multi-class ambiguity) suggests validating it against a hand-labeled subset and reporting agreement (e.g. Cohen's κ) rather than trusting the labels outright.
- For small, mostly sequential Verilog-2005 designs, Ma's Communication class and HWE-Bench's Interface/Spec/Config classes will be sparsely populated. A semantic taxonomy that stops there will give a degenerate distribution, with most mutants labeled "Erroneous Expression" or "Functional logic".

### Gaps
- No paper found that measures how well syntactic mutation operators predict human-assigned semantic root causes for RTL, or how well LLM-assigned labels agree with humans on RTL bugs.
- No study found that relates syntactic class to empirical debugging difficulty (e.g. time-to-fix or LLM repair rate per class) beyond CirFix's coarse Cat 1/2 results and RTL-Repair's per-template counts.
