# Memorization and Data-Contamination Risks of VerilogEval / RTLLM in an LLM RTL-Debugging Benchmark, and Evidence on Mitigations

Context: the planned benchmark takes VerilogEval/RTLLM-style designs and applies a "level 2" disguise (rename every identifier, rewrite specs in our own words, light restructuring). It then compares an LLM agent against a single-shot baseline that uses the same model. Research date: 2026-10-15. Where I relied on a search-engine snippet and could not confirm the claim in the primary text, the bullet is marked **[snippet-only]**.

## Q1. Is there measured contamination of VerilogEval, RTLLM, or other HDL benchmarks? What are the numbers?

### Takeaway
Yes. VeriContaminated (NYU, ICLAD 2025) is the main quantitative study. It finds close to 100% contamination signals for GPT-3.5 and GPT-4o on both VerilogEval and RTLLM, and lower but non-trivial rates for open models. Later HDL benchmarks (LiveVerilogEval at DATE 2026, NotSoTiny, the GRPO state-mutation work) cite contamination as their reason to exist and use design mutation or periodic refresh to counter it. CVDP's public abstract does not frame itself around contamination, but its public release withholds reference solutions to limit it.

### Cited Findings
- **VeriContaminated** (Wang, Shao, Bhandari, Mankali, Karri, Sinanoglu, Shafique, Knechtel; NYU Tandon / NYU Abu Dhabi; ICLAD 2025). It measures VerilogEval and RTLLM contamination with two detectors, CDD (output-distribution peakedness via edit distance across samples) and Min-K% Prob (low-probability token likelihood). — [arXiv 2503.13572](https://arxiv.org/html/2503.13572v2)
  - Table I (CDD α=0.05; Min-K% K=20, T=0.55). Contamination % is listed as CDD-RTLLM / CDD-VerilogEval / MinK-RTLLM / MinK-VerilogEval, followed by pass@1 on RTLLM / VerilogEval. — [arXiv 2503.13572](https://arxiv.org/html/2503.13572v2)
    - GPT-3.5: 100 / 98.72 / 100 / 97.44; pass 32 / 36.54
    - GPT-4o: 100 / 100 / 98 / 99.36; pass 44 / 60.26
    - DeepSeek-Coder: 58 / 26.92 / 8 / 9.62; pass 42 / 19.87
    - CodeQwen 1.5: 78 / 25.64 / 10 / 4.49
    - LLaMA 3.1 8B: 22 / 33.33 / 84 / 52.56
    - LLaMA 2: 24 / 17.95 / 84 / 67.95
    - phi-4 mini: 54 / 22.43 / 14 / 10.90
    - GPT-2: 4 / 6.41 / 0 / 0
  - The paper says commercial models "exhibit higher initial contamination rates—approaching 100%". It reports that LLaMA 3.1 70B/405B "maintain nearly 100% contamination on both benchmarks at α=0", while the 8B model shows about 20%. — [arXiv 2503.13572](https://arxiv.org/html/2503.13572v2)
  - The authors call Min-K% Prob "weak when distinguishing contamination levels among other models", so the two detectors disagree a lot for mid-sized open models (for example, LLaMA 2 scores 18% on CDD but 68% on Min-K% for VerilogEval). — [arXiv 2503.13572](https://arxiv.org/html/2503.13572v2)
  - Their only mitigation is TED (from the CDD/TED line of work). It is an evaluation-side filter that drops the top τ% most likely contaminated outputs; it does not rewrite the benchmark. Pass rate falls as τ rises. The authors claim TED "reduces contamination with limited impact on RTL accuracy". Exact mitigation numbers appear only in figures. The paper does **not** test renaming or spec rewriting. — [arXiv 2503.13572](https://arxiv.org/html/2503.13572v2)
  - **[snippet-only]** It also reports AST-similarity evidence that the fine-tuning corpora of RTLCoder and VeriGen "show significant similarities" to RTLLM and VerilogEval golden solutions. — [arXiv 2503.13572v2 PDF](https://arxiv.org/pdf/2503.13572v2)
  - **[snippet-only]** A 2026 survey characterizes this result as "near-100% contamination rates in standard benchmarks like VerilogEval across most commercial models". That overstates the paper: only GPT-3.5 and GPT-4o were near 100% among the commercial models in Table I. — [arXiv 2605.10807](https://arxiv.org/pdf/2605.10807)
- **VerilogEval provenance.** The original VerilogEval contains 156 problems taken from the HDLBits teaching site. — [VerilogEval, arXiv 2309.07544](https://arxiv.org/pdf/2309.07544); [NVIDIA Research page](https://research.nvidia.com/publication/2023-09_verilogeval-evaluating-large-language-models-verilog-code-generation)
  - Many public GitHub repositories post HDLBits solutions (for example a "hdl-bits-solutions" topic and xiaop1/Verilog-Practice). This is a plausible route for reference solutions to enter pretraining crawls. — [GitHub topic hdl-bits-solutions](https://github.com/topics/hdl-bits-solutions); [Nidhinchandran47/HDLbits-Solutions](https://github.com/Nidhinchandran47/HDLbits-Solutions)
  - VerilogEval v2 ("Revisiting VerilogEval", Pinckney et al., TODAES 2025) converted all 156 problems to spec-to-RTL format, with GPT-4o at 63%. I found no contamination analysis in the parts I could access. — [arXiv 2408.11053](https://arxiv.org/html/2408.11053v1)
  - EvolVE reports quality problems in VerilogEval v2: inaccurate descriptions, unsynthesizable syntax and logical inconsistencies in reference models. It built a corrected "Mod-VerilogEval v2". — [arXiv 2601.18067](https://arxiv.org/pdf/2601.18067)
- **LiveVerilogEval** (DATE 2026; Peking University, HKUST et al.). It generates "mutated variants of valid Verilog designs while maintaining semantic correctness" to address training/eval overlap. It reports "significant performance degradation across state-of-the-art LLMs" compared with the static benchmarks. — [DATE 2026 proceedings PDF](https://past.date-conference.com/proceedings-archive/2026/DATA/167.pdf) **[snippet-only: the PDF returned HTTP 404 when I fetched it, so I could not get per-model drop numbers or mutation-operator details]**
- **NotSoTiny** (Barcelona Supercomputing Center; arXiv 2512.20823). A "living" RTL benchmark built from Tiny Tapeout shuttles and refreshed each shuttle for contamination resilience. — [arXiv 2512.20823](https://arxiv.org/html/2512.20823v1)
  - It reports that "RTLLM shows consistently higher Min-K values than NotSoTiny across the curve", meaning RTLLM solutions are more likely to have been seen in training. Numbers appear only in Figure 2. VerilogEval was left out because its modules are too small for Min-K% to work well. — [arXiv 2512.20823](https://arxiv.org/html/2512.20823v1)
  - It deduplicates internally with MinHash-LSH over word 5-grams at Jaccard 0.70, following the BigCode approach. — [arXiv 2512.20823](https://arxiv.org/html/2512.20823v1)
- **GRPO with State Mutations** (arXiv 2601.07593) mutates 500 ScaleRTL designs into 1,500 evaluation designs, explicitly to address contamination. — [arXiv 2601.07593](https://arxiv.org/pdf/2601.07593)
- **CVDP** (NVIDIA; arXiv 2506.14074) has 783 problems in 13 categories, including debugging. SOTA models reach at most 34% pass@1 on code generation. The abstract does not mention contamination or saturation of VerilogEval/RTLLM. — [arXiv 2506.14074](https://arxiv.org/abs/2506.14074)
  - According to a later audit paper, the public CVDP release "deliberately withholds reference solutions … specifically to mitigate data contamination". — [GateTruth, arXiv 2608.12635](https://arxiv.org/pdf/2608.12635)
  - A vendor case study says earlier benchmarks often gave pass rates above 60% "due to oversimplified prompts" (saturation framing; vendor source). — [Turing case study](https://www.turing.com/case-study/benchmarking-rtl-agents-with-real-world-verilog-tasks-for-nvidia-cvdp)
  - CVDP 1.1.0 was released on 2026-06-08 under the Si2 LLM Benchmarking Coalition. — [Si2](https://si2.org/summary-and-key-improvements-in-cvdp1-1-0/)

### Inferences
- For any frontier model (GPT-4-class and later, which likely includes the model this project uses), assume VerilogEval and RTLLM golden designs **and** their HDLBits-style problem text are memorized. VeriContaminated's near-100% figures apply to GPT-3.5/4o, and newer models were trained on supersets of the same crawl.
- A debugging benchmark is especially exposed. If the model recognises the design, it can "repair" a bug by reverting to the memorized golden code rather than localising the bug from simulation evidence. Contamination here works directly as an answer key, not just as familiarity.
- Min-K% Prob and CDD need token log-probs or many samples. VeriContaminated's own results show the two detectors disagree heavily, so neither number should be treated as ground truth.

### Gaps
- I found no study of contamination for HDL **debugging** tasks specifically. All HDL studies concern spec-to-RTL generation.
- No CVDP-specific contamination measurement found.
- LiveVerilogEval's per-model drops and mutation operators are unverified because the PDF was unreachable.
- I found no VerilogEval v2 statement on contamination, although I only saw parts of the text.

## Q2. In software benchmarks, how much do renaming, paraphrasing and restructuring reduce memorization-driven performance?

### Takeaway
Semantics-preserving surface changes (renaming, reformatting, paraphrase) usually cost a few to about 15 points, and occasionally 20–30 on specific tasks or models. **Renaming alone tends to be the weakest perturbation**; it bites hardest when combined with structural change. Fresh or post-cutoff tasks show much larger gaps (for example, SWE-bench+ resolution falling from 12.47% to about 4%). One finding cuts against relying on paraphrase: models trained on *paraphrased* test data still gain massively. So a "level 2" disguise reduces verbatim recall but does not remove semantic familiarity with a design such as a well-known FIFO or UART.

### Cited Findings
**Renaming and obfuscation**
- **"When Names Disappear"** (arXiv 2510.03178) applies four obfuscations: alpha-renaming, ambiguous identifiers, cross-domain names and misleading names. — [arXiv 2510.03178](https://arxiv.org/html/2510.03178v1)
  - Execution-prediction pass@1 change under *alpha-renaming* (computed from Table 3):
    - ClassEval: GPT-4o −6.4, Qwen3-Coder −6.2, DeepSeek V3 −4.5, Llama 4 Maverick +2.3.
    - LiveCodeBench: GPT-4o −7.4, Qwen3-Coder −4.8, DeepSeek V3 −0.7, Llama 4 Maverick −14.9.
    - Ambiguous identifiers hit harder, up to −23.8 for Llama 4 Maverick on LiveCodeBench.
  - The abstract-level claim: "nearly all models suffer double-digit drops, with reductions exceeding 20–30% in several obfuscation settings".
  - Summarization drops on ClassEval are larger, up to −28.6 for GPT-4o at class level.
  - The authors interpret names as retrieval "keys" for memorized code→output patterns. Under ambiguous or misleading names, outputs matching the memorized old dataset output fell to 0–5 cases. This is an interpretation, not a mechanism they tested.
  - — [arXiv 2510.03178](https://arxiv.org/html/2510.03178v1)
- **Metamorphic testing for program repair** (De Koning, Asgari, Derakhshanfar, Panichella; arXiv 2604.21579) applies semantics-preserving transformations to Defects4J and GitBug-Java.
  - Repair success drops range from −4.1% (GPT-4o) to −15.98% (Llama-3.1).
  - The degradation "strongly correlates with NLL on the original benchmarks", meaning models do better on instances they likely memorized.
  - — [arXiv 2604.21579](https://arxiv.org/abs/2604.21579)
  - **[snippet-only]** "Renaming transformations generally have a significant adverse effect only when combined with structural changes." — [alphaXiv 2604.21579](https://www.alphaxiv.org/abs/2604.21579) (not confirmed in the abstract I fetched)
  - This is the closest analogue to our setting: **bug repair** with renaming and structural transforms, and frontier models losing only about 4 points.
- **ReCode** (Wang et al., ACL 2023) defines more than 30 natural, semantics-preserving perturbations on HumanEval and MBPP: docstring paraphrase, function/variable renaming, code syntax and format. Models were most sensitive to *syntax* perturbations, less so to renaming or docstring changes. I could not retrieve exact numbers. — [arXiv 2212.10264](https://arxiv.org/abs/2212.10264v1); [ACL Anthology](https://preview.aclanthology.org/setup/2023.acl-long.773)

**Evolved, rewritten or fresh problems**
- **EvoEval** (Xia et al., arXiv 2403.19114) uses GPT-4 to evolve HumanEval into 828 problems across 7 datasets. Across 51 LLMs pass@1 falls by 39.4% on average (range 19.6–47.7%), and rankings reshuffle. The NSF-hosted version says 57 LLMs and 38.1%. — [arXiv 2403.19114](https://arxiv.org/abs/2403.19114v1); [NSF PAR version](https://par.nsf.gov//servlets/purl/10580918)
  - Caveat: EvoEval also changes difficulty (it has "Difficult" and "Creative" sets), so the drop is not purely a memorization effect.
- **Paraphrased contamination still helps** (Yang, Chiang, Zheng, Gonzalez, Stoica; arXiv 2311.04850). Llama models (7B/13B) trained on *rephrased or translated* HumanEval approached GPT-4 on HumanEval, and n-gram decontamination fails to catch rephrased samples. They estimate 8–18% of HumanEval overlaps with RedPajama/StarCoder-Data. — [arXiv 2311.04850](https://arxiv.org/pdf/2311.04850); [LMSYS blog](https://www.lmsys.org/blog/2023-11-14-llm-decontaminator)
  - Implication: the benefit of contamination carries across surface form. A model that saw the original can plausibly exploit a paraphrased version.

**SWE-bench line of work**
- **SWE-Bench+** (Aleithan et al., arXiv 2410.06992) audited SWE-agent + GPT-4 passes.
  - arXiv v2: 32.67% involved solution leakage in the issue or comments, and 31.08% passed because of weak tests. Filtering cut resolution from 12.47% to 3.97%.
  - Revised thesis version: 33.47% leakage, 24.70% weak tests, resolution 4.58%.
  - Over 94% of issues predate model knowledge cutoffs.
  - — [arXiv 2410.06992](https://arxiv.org/html/2410.06992v2); [YorkSpace](https://yorkspace.library.yorku.ca/items/39fdcdf5-f606-4b77-b59a-27ed480838fa)
- **The SWE-Bench Illusion** (Liang, Garg, Zilouchian Moghaddam; arXiv 2506.12286; ICSE 2026 SEIP; NeurIPS 2025).
  - Given only the issue text, models identify the buggy file path with up to 76% accuracy on SWE-bench Verified, against up to 53% on repositories outside SWE-bench.
  - Consecutive 5-gram reproduction of ground-truth functions reaches up to 35% on Verified/Full, against up to 18% on other benchmarks.
  - — [arXiv 2506.12286](https://arxiv.org/abs/2506.12286); [ICSE 2026](https://conf.researchr.org/details/icse-2026/icse-2026-software-engineering-in-practice/29/The-SWE-Bench-Illusion-When-State-of-the-Art-LLMs-Remember-Instead-of-Reason)
- **SWE-rebench** (NeurIPS 2025 D&B; arXiv 2505.20411) collects fresh tasks continuously. It reports that the "performance of some models may be inflated by contamination" relative to SWE-bench Verified. Secondary sites give specific per-model drops, but I could not verify them (one mirror had obvious errors). — [arXiv 2505.20411](https://arxiv.org/abs/2505.20411v1)

### Inferences
- Software evidence suggests our level-2 disguise (rename + spec rewrite + light restructure) will cut verbatim and lexical recall cues, but will probably remove only a minority of the memorization advantage for frontier models. The most comparable controlled result is the metamorphic program-repair study: about 4 points for GPT-4o, about 16 for Llama-3.1.
- Renaming matters more in HDL than in Python in one respect: module and port names such as `top_module` and HDLBits-style signal names are strong retrieval keys. Even so, the canonical *structure* of small textbook designs (counters, FSMs, FIFOs) stays recognisable after renaming.
- The two approaches that showed the largest drops change semantics or provenance, not surface form. Those are fresh or post-cutoff tasks (SWE-bench+, SWE-rebench, NotSoTiny) and design mutation (LiveVerilogEval, EvoEval). For HDL that means hand-written designs or real changes such as different widths or parameters, altered FSM encodings or protocols, or added features.

### Gaps
- No study quantifies renaming or spec-rewriting **for Verilog specifically**.
- I could not obtain exact ReCode per-perturbation numbers.
- I could not locate a paper titled "Is your benchmark truly adversarial?". It may not exist under that title, so treat it as unverified.
- SWE-bench-Live was not checked in detail.
- No study isolates "light restructuring" or "parameter/width change" as single factors.

## Q3. Which contamination-detection methods are practical for a small project?

### Takeaway
For closed API models, black-box probes are practical: completion probes (Time Travel's guided instruction), slot or name guessing (TS-Guessing), and the file-path or identity-guessing analogue from SWE-Bench Illusion. They are cheap, need no log-probs, and can be run per design both before and after disguise. Min-K% Prob and CDD need log-probs or many samples, and are noisy even in the VeriContaminated study. N-gram or MinHash overlap is cheap for checking our disguised designs against the public originals, but cannot see the model's training data.

### Cited Findings
- **Min-K% Prob** needs token probabilities; VeriContaminated used K=20, T=0.55. It was "weak when distinguishing contamination levels" among non-commercial models. — [arXiv 2503.13572](https://arxiv.org/html/2503.13572v2)
- **CDD** measures the peakedness of the output distribution via edit distance across multiple samples. It needs only sampling, so it works black-box, at the cost of many generations per item. — [arXiv 2503.13572](https://arxiv.org/html/2503.13572v2)
- **Guided-instruction completion** ("Time Travel in LLMs", Golchin & Surdeanu, ICLR 2024).
  - The prompt gives the dataset name, the partition and the first part of an instance, then asks the model to complete it.
  - Matches are scored with ROUGE-L or BLEURT against a generic prompt, or judged by a GPT-4 few-shot classifier.
  - It reaches 92–100% agreement with human experts across 7 datasets and needs only black-box access.
  - — [arXiv 2308.08493](https://arxiv.org/html/2308.08493v1); [ICLR 2024](https://iclr.cc/virtual/2024/poster/19550)
- **TS-Guessing** (Deng et al., NAACL 2024) masks an unlikely word or a wrong MCQ option and asks the model to fill it in. GPT-4 exactly matched 57% of masked MMLU options. — [arXiv 2311.09783](https://arxiv.org/html/2311.09783v2); [ACL Anthology](https://aclanthology.org/2024.naacl-long.482)
- **File-path or identity guessing** (SWE-Bench Illusion). Ask the model to name the buggy file from the issue alone, then compare accuracy against a control set from repositories outside the benchmark. Microsoft's BC-Bench reuses this as a contamination check. — [arXiv 2506.12286](https://arxiv.org/abs/2506.12286); [BC-Bench docs](https://microsoft.github.io/BC-Bench/contamination-file-path-identification.html)
- **N-gram or MinHash overlap**: NotSoTiny uses word 5-grams with MinHash-LSH at Jaccard 0.70. N-gram methods miss paraphrased contamination, and Yang et al. propose embedding search plus an LLM judge ("LLM Decontaminator") instead. — [arXiv 2512.20823](https://arxiv.org/html/2512.20823v1); [arXiv 2311.04850](https://arxiv.org/pdf/2311.04850); [lm-sys/llm-decontaminator](https://github.com/lm-sys/llm-decontaminator)
- **Metamorphic delta**: run the same items original and transformed, and treat the per-item drop (correlated with NLL) as the memorization signal. — [arXiv 2604.21579](https://arxiv.org/abs/2604.21579)
- **Caveat**: memorization-based detection can be evaded and is fragile for reasoning models. — [arXiv 2510.02386](https://arxiv.org/html/2510.02386v1)

### Inferences
Practical recipe for this project (my synthesis, not from any single source):
1. **Identity probe.** Show the model the disguised design and ask it to name the original benchmark, problem ID, or module name (for example HDLBits problem name or RTLLM design name). This is the SWE-Bench Illusion file-path idea.
2. **Completion probe.** Give the first N lines of the *original* RTL and score how closely the model's continuation matches the golden code (ROUGE-L or 5-gram overlap). Also give the first N lines of the *disguised* RTL and check whether the model "snaps back" to the original identifiers.
3. **Matched controls.** Run the same probes on a few freshly hand-written designs of similar complexity, to get a baseline.
4. **Overlap check.** Run MinHash/5-gram overlap between each disguised design and its source, to confirm the disguise actually changed the surface form.
5. **Debugging-specific "revert to golden" check.** Diff the model's fix against the original golden RTL versus the minimal fix. A wholesale rewrite that converges to the canonical public implementation suggests recall.

### Gaps
- None of these probes has been validated on Verilog debugging tasks.
- I found no published thresholds for HDL.

## Q4. When the agent and baseline share the same model, does contamination bias the *relative* comparison?

### Takeaway
I found no paper that directly measures this, so the answer is unresolved in the literature. Contamination does not cancel out automatically. Several mechanisms can bias the agent-minus-baseline gap in either direction, and agentic setups have extra leakage channels such as web search and repository history. The safest design is to report the gap separately on contaminated-source items and on fresh or mutated items, and to test for an interaction.

### Cited Findings
- No source found reporting a paired design of the same model, agent versus non-agent, with contamination-matched or perturbed items. — (search result: no direct study; see [MedicalAgentsBench, arXiv 2503.07459](https://arxiv.org/pdf/2503.07459) for the nearest analogue)
- **MedicalAgentsBench** compared internalized-reasoning models against agent frameworks. It ran a memorization probe first and based its method comparisons on models with low memorization similarity (OpenAI models, median 20–25%), because some open models scored much higher. This is a precedent for screening contamination before comparing scaffolds. — [arXiv 2503.07459](https://arxiv.org/pdf/2503.07459)
- **Agent-only leakage channels.**
  - "Search-time contamination", where an agent retrieves answers from the web during evaluation, inflates scores even on benchmarks that were clean at construction. — [arXiv 2608.05179](https://arxiv.org/pdf/2608.05179)
  - **[snippet-only]** Agents have been seen running `git log` in the environment to recover the original fixing commit. — [SWE Atlas, arXiv 2605.08366](https://arxiv.org/pdf/2605.08366) (attribution uncertain; it came from a search summary)
- **Scaffold effect size, from a secondary blog source:** the same model scored 50.2–55.4% under different agent scaffolds against a 45.9% standardized score. This shows that scaffold effects are large, but it does not separate them from contamination. — [agentmarketcap blog](https://agentmarketcap.ai/blog/2026/04/05/swe-bench-contamination-crisis-openai-stops-reporting-verified-scores) (low-reliability source)
- **Contamination effects vary by item** and correlate with per-item NLL. — [arXiv 2604.21579](https://arxiv.org/abs/2604.21579)
  - So the "memorization bonus" is not a constant offset, and it will not cancel out in a difference of means if the two arms exploit it to different degrees.

### Inferences
The following are reasoning, not established findings.
- **Ceiling effect, which shrinks the gap.** If the single-shot baseline already solves memorized items by recall, the agent has little room to add value there. Contamination then compresses the measured agent advantage on those items.
- **Amplification, which inflates the gap.** An agent that sees simulation output, waveforms or more of the design over several turns gets more retrieval cues. It is more likely to recognise the design and then rewrite it to the memorized golden version, which passes the tests without real debugging. Contamination may therefore help the agent more than the baseline.
- **Extra leakage channels, which inflate the gap.** Tool access to the web, pip/GitHub or any file left in the sandbox (the original RTL, git history) is available only to the agent. Sandbox the agent with no network, and make sure the original design and history are absent.
- **Recommended analysis.** Stratify items by contamination probe score, or by source (disguised public versus fresh hand-written versus mutated). Report the agent − baseline gap per stratum, and test the arm × stratum interaction. A gap that holds on fresh or mutated items is credible; a gap that appears only on public-source items is suspect.
- Because the same model is used in both arms, contamination *level* is held constant, but the ability to *exploit* it is not. That is why stratification matters.

### Gaps
- No empirical study found on how contamination changes the agent-versus-single-shot gap with a fixed model, in code or HDL.
- The `git log` observation and the scaffold-spread numbers come from snippets or low-reliability sources and need primary confirmation.
